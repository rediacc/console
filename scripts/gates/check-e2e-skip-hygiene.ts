#!/usr/bin/env node
/**
 * Static half of the E2E zero-skip contract (runtime half: run-e2e.sh
 * --fail-on-skip).
 *
 * WHY. The E2E suites are topology-partitioned: worker tests live flat under
 * tests/, and each specialized topology lives in its own subdir (tests/ceph,
 * tests/kube, tests/migrate, tests/ops-lifecycle) with a dedicated
 * playwright.<topology>.config.ts that scopes to it. The BASE
 * playwright.config.ts drives the E2E Workers job and matches `NN-*.test.ts`
 * recursively, so any topology subdir it does NOT list in `testIgnore` gets
 * COLLECTED and then skipped at runtime for lack of that topology — dishonest
 * "skipped" lines that look like coverage but actually run in another job.
 *
 * That is exactly what happened: `testIgnore` excluded ceph but never kube or
 * migrate (added later), so 38 kube/migrate tests were collected-then-skipped
 * in every E2E Workers run. The runtime gate catches it after the fact; this
 * gate makes it impossible to reintroduce: every test-bearing subdir of
 * tests/ MUST be excluded by the base config's testIgnore.
 *
 * CONVENTION ENCODED. A subdirectory of packages/e2e-tests/tests/ that
 * contains *.test.ts files is topology-specific and has its own config; the
 * base config must ignore it. If a subdir is ever meant to run in the base
 * worker job, add it to BASE_ALLOWED below with a reason.
 *
 * SECOND DIRECTION (every test is SELECTED somewhere). The first direction
 * only proves the base config does not collect topology suites. It cannot see
 * the opposite loss: a `*.test.ts` that NO playwright*.config.ts selects, which
 * is never run by anything and still reads as coverage (ops-lifecycle was in
 * exactly that state). So every `*.test.ts` under tests/ must be selected by
 * at least one config (inside its testDir, matched by a testMatch, not caught
 * by that config's testIgnore) or be named in DELIBERATE_OMISSIONS with a
 * reason. The omission list lives in this file, so dropping an entry fails the
 * gate rather than hiding the file.
 *
 * TEST SEAM. E2E_HYGIENE_ROOT overrides the repo root.
 *
 * ---- gate ----
 * step: Check E2E skip hygiene (no collected-then-skipped suites)
 * needs: node
 * lane: quality-content
 * ---- end gate ----
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { envRoot } from '../lib/repo-root.js';

// ANCHORED ON THIS FILE, not on the caller's working directory. This read `process.env.E2E_HYGIENE_ROOT ?? process.cwd()`, which check:ci-gate-cwd-independence did not see: its pattern only matched cwd as the FIRST argument of path.resolve/join, so the commonest shape of its own rule passed. The seam is preserved -- E2E_HYGIENE_ROOT still overrides -- but the default is derived
// from this file's location.
const ROOT = envRoot('E2E_HYGIENE_ROOT');
const E2E = join(ROOT, 'packages/e2e-tests');
const TESTS_DIR = join(E2E, 'tests');
const BASE_CONFIG = join(E2E, 'playwright.config.ts');

// Subdirs that intentionally run in the base worker config (none today). Add here with a reason if a non-topology subdir is ever introduced.
const BASE_ALLOWED = new Set<string>();

function hasTestFiles(dir: string): boolean {
  let found = false;
  const walk = (d: string): void => {
    for (const entry of readdirSync(d)) {
      const p = join(d, entry);
      if (statSync(p).isDirectory()) walk(p);
      else if (entry.endsWith('.test.ts')) found = true;
    }
  };
  walk(dir);
  return found;
}

function topologySubdirs(): string[] {
  return readdirSync(TESTS_DIR)
    .filter((e) => statSync(join(TESTS_DIR, e)).isDirectory())
    .filter((e) => hasTestFiles(join(TESTS_DIR, e)))
    .filter((e) => !BASE_ALLOWED.has(e))
    .sort();
}

/** Extract the string entries of the base config's testIgnore array. */
function baseTestIgnore(): string[] {
  const src = readFileSync(BASE_CONFIG, 'utf8');
  const m = src.match(/testIgnore:\s*\[([^\]]*)\]/s);
  if (!m) {
    console.error(`FAIL: could not find a testIgnore array in ${BASE_CONFIG}`);
    process.exit(1);
  }
  return [...m[1].matchAll(/['"`]([^'"`]+)['"`]/g)].map((x) => x[1]);
}

// Test files no config selects ON PURPOSE, keyed by path relative to packages/e2e-tests/tests, each with the reason it stays unselected.
const DELIBERATE_OMISSIONS = new Map<string, string>([
  [
    'ops-lifecycle/18-ops-lifecycle.test.ts',
    'DESTRUCTIVE: stops/resets the very VMs the shared bridge topology uses, so no CI job may select it; run it locally by pointing Playwright at the file.',
  ],
]);

function allTestFiles(dir: string, prefix = ''): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir).sort()) {
    const p = join(dir, entry);
    const rel = prefix ? `${prefix}/${entry}` : entry;
    if (statSync(p).isDirectory()) out.push(...allTestFiles(p, rel));
    else if (entry.endsWith('.test.ts')) out.push(rel);
  }
  return out;
}

function globToRegExp(glob: string): RegExp {
  const body = glob
    .replace(/[.+^${}()|\\]/g, '\\$&')
    .replace(/\*\*\//g, '\u0000')
    .replace(/\*\*/g, '\u0001')
    .replace(/\*/g, '[^/]*')
    .replace(/\u0000/g, '(?:.*/)?')
    .replace(/\u0001/g, '.*');
  return new RegExp(`^${body}$`);
}

function quoted(src: string): string[] {
  return [...src.matchAll(/['"`]([^'"`]+)['"`]/g)].map((x) => x[1]);
}

/** String entries of every `key: [..]` / `key: '..'` occurrence (top level and per project). */
function configValues(src: string, key: string): string[] {
  const out: string[] = [];
  const re = new RegExp(`\\b${key}:\\s*(\\[[^\\]]*\\]|['"\`][^'"\`]+['"\`])`, 'g');
  for (const m of src.matchAll(re)) out.push(...quoted(m[1]));
  return out;
}

/** Test files (relative to tests/) that this one config selects. */
function selectedBy(configPath: string, files: string[]): Set<string> {
  const src = readFileSync(configPath, 'utf8');
  const dirM = src.match(/testDir:\s*['"]\.\/tests(?:\/([^'"]+))?['"]/);
  if (!dirM) return new Set();
  const sub = dirM[1] ? `${dirM[1].replace(/\/$/, '')}/` : '';
  const declared = configValues(src, 'testMatch').map(globToRegExp);
  // No testMatch means Playwright's own default, every *.spec / *.test script.
  const matchers = declared.length > 0 ? declared : [/\.(?:spec|test)\.[cm]?[jt]sx?$/];
  const ignorers = configValues(src, 'testIgnore').map(globToRegExp);
  const selected = new Set<string>();
  for (const f of files) {
    if (!f.startsWith(sub)) continue;
    const inDir = f.slice(sub.length);
    const hit = (re: RegExp): boolean => re.test(inDir) || re.test(inDir.split('/').pop() ?? inDir);
    if (!matchers.some(hit)) continue;
    if (ignorers.some((re) => re.test(f) || re.test(`tests/${f}`) || re.test(inDir))) continue;
    selected.add(f);
  }
  return selected;
}

function unselectedTests(): string[] {
  const files = allTestFiles(TESTS_DIR);
  const configs = readdirSync(E2E)
    .filter((e) => /^playwright.*\.config\.ts$/.test(e))
    .map((e) => join(E2E, e));
  const selected = new Set<string>();
  for (const c of configs) for (const f of selectedBy(c, files)) selected.add(f);
  return files.filter((f) => !selected.has(f) && !DELIBERATE_OMISSIONS.has(f));
}

function main(): void {
  const subdirs = topologySubdirs();
  const ignores = baseTestIgnore();
  const covered = (sub: string): boolean =>
    ignores.some((g) => g === `**/${sub}/**` || g === `${sub}/**` || g.includes(`/${sub}/`));

  const missing = subdirs.filter((s) => !covered(s));

  console.log('E2E skip-hygiene: base playwright.config.ts vs topology subdirs');
  console.log('='.repeat(60));
  console.log(`  topology subdirs: ${subdirs.join(', ') || '(none)'}`);
  console.log(`  base testIgnore : ${ignores.join(', ')}`);

  if (missing.length > 0) {
    console.error('');
    console.error(`FAIL: ${missing.length} topology subdir(s) NOT excluded by the base config:`);
    for (const s of missing) console.error(`  tests/${s}/  -> add '**/${s}/**' to testIgnore`);
    console.error('');
    console.error('Without the exclusion the E2E Workers job collects these and skips them');
    console.error('(invisible coverage loss). Each has its own playwright.<topology>.config.ts.');
    process.exit(1);
  }
  const orphans = unselectedTests();
  if (orphans.length > 0) {
    console.error('');
    console.error(
      `FAIL: ${orphans.length} test file(s) selected by NO playwright*.config.ts and not in DELIBERATE_OMISSIONS:`
    );
    for (const f of orphans) console.error(`  tests/${f}`);
    console.error('');
    console.error('A test no config selects never runs. Select it from a config, or name it in');
    console.error('DELIBERATE_OMISSIONS with the reason it stays unselected.');
    process.exit(1);
  }
  console.log('');
  console.log(`OK: all ${subdirs.length} topology subdir(s) excluded from the base worker run.`);
}

main();

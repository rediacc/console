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
 * TEST SEAM. E2E_HYGIENE_ROOT overrides the repo root.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = process.env.E2E_HYGIENE_ROOT ?? process.cwd();
const E2E = join(ROOT, 'packages/e2e-tests');
const TESTS_DIR = join(E2E, 'tests');
const BASE_CONFIG = join(E2E, 'playwright.config.ts');

// Subdirs that intentionally run in the base worker config (none today).
// Add here with a reason if a non-topology subdir is ever introduced.
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
  console.log('');
  console.log(`OK: all ${subdirs.length} topology subdir(s) excluded from the base worker run.`);
}

main();

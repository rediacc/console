#!/usr/bin/env node
/**
 * e2e-tests coverage gate — FORWARD direction (live-config membership).
 *
 * This is the TypeScript half of .ci/scripts/quality/check-e2e-coverage.sh.
 * The shell entry still owns Phase 3 (the reverse "dispatched verbs must still
 * exist" scan, which deliberately reads ALL files including dark ones). This
 * half answers the forward question — "is every shipped renet function actually
 * exercised by a suite CI RUNS?" — and it is in TypeScript for one reason: bash
 * cannot honestly parse a playwright config to learn which test files a job
 * selects. The old bash forward pass globbed every `.ts` under src/ + tests/,
 * so a verb mentioned only in a DARK file (a suite no config selects, a harness
 * method no live test calls) counted as covered. That is precisely how
 * kube_node_remove (declared in KubeMethods.ts, called by no test) and the
 * kube-registry anchor (self-gated behind an env var set nowhere) passed a gate
 * whose whole job was to notice them.
 *
 * The honest question is membership in the LIVE set, so this gate computes it:
 *
 *   1. LIVE-CONFIG REGISTRY — the explicit list of playwright configs CI runs,
 *      cross-checked against the workflows so it cannot silently rot (a config
 *      a workflow runs but the registry omits, or vice versa, FAILS the gate).
 *   2. SELECTED-FILE EXPANSION — import each registered config (honoring the CI
 *      branch of conditional `projects`, evaluated with CI=1) and resolve every
 *      project's testDir + testMatch − testIgnore into a concrete file set:
 *      LIVE_TESTS. Only these files can confer coverage.
 *   3. HARNESS METHOD MAP — parse src/utils/bridge/methods/*.ts into
 *      (methodName → dispatched verb). A verb is covered by a method ONLY when
 *      `.methodName(` is CALLED from a LIVE_TESTS file (or, one hop, from a
 *      helper under src/utils/bridge/helpers that a live test reaches). A method
 *      that is merely DECLARED — the dead-coverage failure mode — does not count.
 *   4. COVERAGE — a renet function counts as covered when its raw verb literal
 *      or its CLI space-form appears in a LIVE_TESTS file, OR rule 3 resolves it.
 *      Everything else must sit on the BLOCKER-gated allowlist, or the gate fails.
 *
 * The gate PRINTS its own coverage limits (configs in the registry, files
 * expanded, helper-indirection hops) so it cannot overstate what it measured —
 * a gate that lies about its reach is the disease this repo keeps finding.
 *
 * Usage:
 *   npx tsx scripts/check-e2e-coverage.ts
 *   (invoked by .ci/scripts/quality/check-e2e-coverage.sh)
 *
 * Exit codes:
 *   0 - Every non-allowlisted renet function is covered by a LIVE suite
 *   1 - A function is uncovered (and unlisted), OR the registry/workflow drift
 *       self-check failed, OR the allowlist has an invalid/stale BLOCKER
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { globSync } from 'glob';
import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..');

// Every root is overridable via an E2E_COV_* env var so the gate-fixture test
// (.ci/scripts/test/gates/test-e2e-coverage.sh) can point the exact production
// code at a controlled fixture tree — the "prove the instrument" discipline.
// Unset, they resolve to the real repo paths, so production behaviour is
// identical whether or not the overrides exist.
const E2E_DIR = process.env.E2E_COV_E2E_DIR ?? path.join(REPO_ROOT, 'packages/e2e-tests');
const FUNCTIONS_FILE =
  process.env.E2E_COV_FUNCTIONS_FILE ??
  path.join(REPO_ROOT, 'packages/shared/src/renet-contract/data/functions.generated.ts');
const METHODS_DIR = path.join(E2E_DIR, 'src/utils/bridge/methods');
const HELPERS_DIR = path.join(E2E_DIR, 'src/utils/bridge/helpers');
const WORKFLOWS_DIR = process.env.E2E_COV_WORKFLOWS_DIR ?? path.join(REPO_ROOT, '.github/workflows');
const ALLOWLIST_FILE = process.env.E2E_COV_ALLOWLIST ?? path.join(REPO_ROOT, '.e2e-coverage-allowlist');

const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const RESET = '\x1b[0m';

/**
 * The configs CI actually executes. `playwright.config.ts` is the DEFAULT config
 * (the bare `run-e2e.sh` call, no --config flag); the rest are named on a
 * `--config` flag in a workflow. `playwright.image.config.ts` is deliberately
 * ABSENT — no workflow runs it (suite 20 is local-only) — and the self-check
 * below fails the moment a workflow starts running a config not listed here, so
 * this array cannot drift out of sync with reality.
 */
const PRODUCTION_REGISTRY: { file: string; isDefault: boolean }[] = [
  { file: 'playwright.config.ts', isDefault: true },
  { file: 'playwright.ceph.config.ts', isDefault: false },
  { file: 'playwright.ceph-workers.config.ts', isDefault: false },
  { file: 'playwright.k8s.config.ts', isDefault: false },
  { file: 'playwright.k8s-ceph.config.ts', isDefault: false },
  { file: 'playwright.k8s-multinode.config.ts', isDefault: false },
  { file: 'playwright.migrate.config.ts', isDefault: false },
];

/**
 * The registry is overridable for the fixture test via E2E_COV_REGISTRY, a
 * comma-separated list where a `:default` suffix marks the default (no --config)
 * config, e.g. "playwright.a.config.ts,playwright.b.config.ts:default".
 */
function loadRegistry(): { file: string; isDefault: boolean }[] {
  const override = process.env.E2E_COV_REGISTRY;
  if (!override) return PRODUCTION_REGISTRY;
  return override
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((entry) => {
      const isDefault = entry.endsWith(':default');
      return { file: isDefault ? entry.slice(0, -':default'.length) : entry, isDefault };
    });
}

const LIVE_CONFIG_REGISTRY = loadRegistry();

/** Method-signature keywords that are NOT harness methods. */
const METHOD_NAME_STOPLIST = new Set([
  'constructor',
  'if',
  'for',
  'while',
  'switch',
  'catch',
  'return',
  'function',
  'testFunction',
]);

function fail(msg: string): never {
  console.log(`${RED}✗${RESET} ${msg}`);
  process.exit(1);
}

function rel(p: string): string {
  return path.relative(REPO_ROOT, p);
}

// ── 1. Live-config registry ↔ workflow self-check ────────────────────────────

/**
 * Scan .github/workflows/*.yml for the two ways a config is invoked:
 *   - `run-e2e.sh --config playwright.X.config.ts`  → a NAMED config
 *   - `run-e2e.sh` with no --config on the same line → the DEFAULT config
 * The gate fails if a workflow runs a config the registry omits, if the registry
 * names a config no workflow runs, or if the registry claims a default that no
 * bare run-e2e.sh invocation backs.
 */
function selfCheckRegistry(): void {
  const namedInWorkflows = new Set<string>();
  let bareDefaultSeen = false;
  const configFlagRe = /--config\s+(playwright[.\w-]*\.config\.ts)/g;

  const workflowFiles = fs.existsSync(WORKFLOWS_DIR)
    ? globSync('*.yml', { cwd: WORKFLOWS_DIR, absolute: true })
    : [];
  for (const wf of workflowFiles) {
    const content = fs.readFileSync(wf, 'utf-8');
    for (const line of content.split('\n')) {
      if (!line.includes('run-e2e.sh')) continue;
      const configs = [...line.matchAll(configFlagRe)].map((m) => m[1]!);
      if (configs.length === 0) {
        // A run-e2e.sh invocation with no --config drives the default config.
        bareDefaultSeen = true;
      } else {
        for (const c of configs) namedInWorkflows.add(c);
      }
    }
  }

  const registryNamed = new Set(
    LIVE_CONFIG_REGISTRY.filter((c) => !c.isDefault).map((c) => c.file),
  );
  const registryHasDefault = LIVE_CONFIG_REGISTRY.some((c) => c.isDefault);

  const problems: string[] = [];
  for (const c of namedInWorkflows) {
    if (!registryNamed.has(c)) {
      problems.push(
        `  - '${c}' is run by a workflow (--config) but is MISSING from LIVE_CONFIG_REGISTRY`,
      );
    }
  }
  for (const c of registryNamed) {
    if (!namedInWorkflows.has(c)) {
      problems.push(
        `  - '${c}' is in LIVE_CONFIG_REGISTRY but NO workflow runs it (--config) — remove it or wire it`,
      );
    }
  }
  if (registryHasDefault && !bareDefaultSeen) {
    problems.push(
      `  - LIVE_CONFIG_REGISTRY marks a default config but no workflow calls run-e2e.sh without --config`,
    );
  }

  if (problems.length > 0) {
    console.log(`${RED}✗${RESET} Live-config registry drifted from the workflows:\n`);
    for (const p of problems) console.log(p);
    console.log(
      `\nThe registry in scripts/check-e2e-coverage.ts must list exactly the configs CI runs.`,
    );
    console.log(
      `Named configs come from '--config <file>' in .github/workflows/*.yml; the default`,
    );
    console.log(`config is the bare 'run-e2e.sh' call. Reconcile the two and re-run.`);
    process.exit(1);
  }

  console.log(
    `${GREEN}✓${RESET} Live-config registry matches the workflows ` +
      `(${registryNamed.size} named + 1 default; ${workflowFiles.length} workflow files scanned)`,
  );
}

// ── 2. Selected-file expansion ───────────────────────────────────────────────

interface PlaywrightProject {
  name?: string;
  testDir?: string;
  testMatch?: string | RegExp | (string | RegExp)[];
  testIgnore?: string | RegExp | (string | RegExp)[];
}
interface PlaywrightConfig {
  testDir?: string;
  testMatch?: string | RegExp | (string | RegExp)[];
  testIgnore?: string | RegExp | (string | RegExp)[];
  projects?: PlaywrightProject[];
}

const DEFAULT_TEST_MATCH = '**/*.@(spec|test).?(c|m)[jt]s?(x)';

function toPatternArray(
  v: string | RegExp | (string | RegExp)[] | undefined,
): { globs: string[]; regexes: RegExp[] } {
  const globs: string[] = [];
  const regexes: RegExp[] = [];
  if (v === undefined) return { globs, regexes };
  for (const item of Array.isArray(v) ? v : [v]) {
    if (typeof item === 'string') globs.push(item);
    else regexes.push(item);
  }
  return { globs, regexes };
}

/**
 * Resolve one playwright config into the concrete test files it selects.
 * Conditional `projects` arrays (the `process.env.CI ? [] : [...]` idiom) are
 * evaluated with CI=1 already set in env, so we see exactly the CI selection.
 */
async function expandConfig(configFile: string): Promise<string[]> {
  const abs = path.join(E2E_DIR, configFile);
  const mod = (await import(pathToFileURL(abs).href)) as { default: PlaywrightConfig };
  const cfg = mod.default;
  const configDir = path.dirname(abs);
  const selected = new Set<string>();

  const projects: PlaywrightProject[] =
    cfg.projects && cfg.projects.length > 0 ? cfg.projects : [{}];

  for (const project of projects) {
    const testDirRel = project.testDir ?? cfg.testDir ?? '.';
    const testDirAbs = path.resolve(configDir, testDirRel);
    if (!fs.existsSync(testDirAbs)) continue;

    const match = toPatternArray(project.testMatch ?? cfg.testMatch ?? DEFAULT_TEST_MATCH);
    const ignore = toPatternArray(project.testIgnore ?? cfg.testIgnore);

    // A RegExp testMatch/testIgnore cannot be expressed as a glob; fail closed
    // rather than silently under- or over-select (honesty over convenience).
    if (match.regexes.length > 0 || ignore.regexes.length > 0) {
      fail(
        `Config ${configFile} uses a RegExp testMatch/testIgnore — this gate only ` +
          `understands string globs. Extend expandConfig() to evaluate it, or the ` +
          `coverage set is a lie.`,
      );
    }

    // glob applies testIgnore via its own `ignore` option (minimatch semantics,
    // matched against the path relative to cwd=testDir — the same base playwright
    // resolves testIgnore against), so `**/ceph/**` drops the ceph subtree.
    const candidates = globSync(match.globs, {
      cwd: testDirAbs,
      absolute: true,
      nodir: true,
      ignore: ignore.globs.length > 0 ? ignore.globs : undefined,
    });
    for (const file of candidates) selected.add(file);
  }

  return [...selected];
}

// ── 3. Harness method map ────────────────────────────────────────────────────

const METHOD_SIG_RE =
  /^ {2}(?:public |private |protected |readonly |static )*(?:async )?([a-z][A-Za-z0-9_]*)\s*[(=<]/;
const FUNCTION_LITERAL_RE = /function:\s*'([a-z0-9_]+)'/;

/** Top-level (2-space-indented) method names declared in a helper file. */
function parseHelperMethodNames(text: string): string[] {
  const names: string[] = [];
  for (const line of text.split('\n')) {
    const sig = line.match(METHOD_SIG_RE);
    if (sig && !METHOD_NAME_STOPLIST.has(sig[1]!)) names.push(sig[1]!);
  }
  return names;
}

/** methodName → dispatched verb, parsed from src/utils/bridge/methods/*.ts. */
function buildMethodMap(): Map<string, string> {
  const map = new Map<string, string>();
  const files = globSync('*.ts', { cwd: METHODS_DIR, absolute: true });
  for (const file of files) {
    const lines = fs.readFileSync(file, 'utf-8').split('\n');
    let currentMethod: string | null = null;
    for (const line of lines) {
      const sig = line.match(METHOD_SIG_RE);
      if (sig && !METHOD_NAME_STOPLIST.has(sig[1]!)) {
        currentMethod = sig[1]!;
        continue;
      }
      const lit = line.match(FUNCTION_LITERAL_RE);
      if (lit && currentMethod) {
        // First verb wins per method; a method dispatches exactly one verb.
        if (!map.has(currentMethod)) map.set(currentMethod, lit[1]!);
      }
    }
  }
  return map;
}

// ── main ─────────────────────────────────────────────────────────────────────

function extractRenetFunctions(): string[] {
  const content = fs.readFileSync(FUNCTIONS_FILE, 'utf-8');
  const lines = content.split('\n');
  const fns: string[] = [];
  let inArray = false;
  for (const line of lines) {
    if (/RENET_FUNCTIONS\s*=\s*\[/.test(line)) {
      inArray = true;
      continue;
    }
    if (inArray && /\]\s*as\s+const/.test(line)) break;
    if (inArray) {
      const m = line.match(/'([a-z0-9_]+)'/);
      if (m) fns.push(m[1]!);
    }
  }
  return fns;
}

/**
 * The CI-matrix opt-in flags. A suite gated behind one of these still RUNS on
 * the leg that sets it, so a file it selects is genuine live coverage. We expand
 * every config with ALL of them ON, yielding the UNION of what any CI leg
 * selects — the honest "covered by CI" set. Under-counting here (a real suite
 * looking dark because a new leg flag is missing) surfaces as a LOUD false-red,
 * never a silent false-green, so this list failing behind the workflows is
 * self-announcing. Keep it in sync with the `include:` matrix env in
 * ct-tests.yml (FULL_INTEGRATION today; add CLI_SUITE when suite 23 lands).
 * NOTE: suites gated on `process.env.CI` directly (test-20 image-build) stay
 * excluded regardless — CI truthiness already drops them.
 */
const CI_LEG_ENABLE_FLAGS: Record<string, string> = {
  CI: '1',
  FULL_INTEGRATION: '1',
};

async function main(): Promise<void> {
  // Evaluate every conditional config under the maximal CI selection.
  for (const [k, v] of Object.entries(CI_LEG_ENABLE_FLAGS)) process.env[k] = v;

  console.log('e2e-tests coverage gate — forward (live-config membership)');
  console.log('============================================================\n');

  if (!fs.existsSync(FUNCTIONS_FILE)) fail(`Functions file not found: ${rel(FUNCTIONS_FILE)}`);
  if (!fs.existsSync(E2E_DIR)) fail(`e2e-tests directory not found: ${rel(E2E_DIR)}`);

  selfCheckRegistry();

  // Expand the registry into LIVE_TESTS.
  const liveTestFiles = new Set<string>();
  const perConfigCounts: string[] = [];
  for (const { file } of LIVE_CONFIG_REGISTRY) {
    const files = await expandConfig(file);
    for (const f of files) liveTestFiles.add(f);
    perConfigCounts.push(`${file} → ${files.length}`);
  }
  const liveFiles = [...liveTestFiles];
  console.log(
    `${GREEN}✓${RESET} Expanded ${LIVE_CONFIG_REGISTRY.length} live configs into ` +
      `${liveFiles.length} distinct test file(s):`,
  );
  for (const line of perConfigCounts) console.log(`    ${line}`);
  console.log('');

  // Read live-test contents once.
  const liveTestText = new Map<string, string>();
  for (const f of liveFiles) liveTestText.set(f, fs.readFileSync(f, 'utf-8'));
  const anyLiveTest = (needle: string): boolean => {
    for (const text of liveTestText.values()) if (text.includes(needle)) return true;
    return false;
  };

  // Method map + helper-indirection (one hop).
  const methodMap = buildMethodMap();
  const helperFiles = fs.existsSync(HELPERS_DIR)
    ? globSync('*.ts', { cwd: HELPERS_DIR, absolute: true })
    : [];

  // A helper file confers coverage ONLY when a live test actually reaches it —
  // i.e. a live test calls one of the helper's own methods (`.helperMethod(`).
  // This is the single level of indirection the tree needs: suite 17 drives
  // `runner.repositoryCommit(...)`, a RepositoryHelpers method that shells out
  // `renet repository commit` (a space-form dispatch, not a `function:` literal),
  // so that helper's space-forms are genuine live coverage. A helper NO live
  // test touches confers nothing (fail closed). BridgeTestRunner.ts is NOT a
  // helper and is never in this set — counting its re-export delegations is
  // exactly the dead-coverage this gate exists to reject.
  const liveHelperText = new Map<string, string>();
  for (const f of helperFiles) {
    const text = fs.readFileSync(f, 'utf-8');
    const helperMethods = parseHelperMethodNames(text);
    if (helperMethods.some((name) => anyLiveTest(`.${name}(`))) {
      liveHelperText.set(f, text);
    }
  }

  // Literal / space-form coverage searches live tests PLUS live helper files.
  const anyLive = (needle: string): boolean => {
    if (anyLiveTest(needle)) return true;
    for (const text of liveHelperText.values()) if (text.includes(needle)) return true;
    return false;
  };
  // A verb-METHOD (declared in methods/*.ts) is called-live when `.methodName(`
  // appears in a live test, or one hop out in a live helper.
  const methodCalledLive = (methodName: string): boolean => anyLiveTest(`.${methodName}(`);
  const methodCalledViaHelper = (methodName: string): boolean => {
    for (const text of liveHelperText.values()) if (text.includes(`.${methodName}(`)) return true;
    return false;
  };
  let helperHopVerbs = 0;

  const fns = extractRenetFunctions();
  if (fns.length === 0) fail('No functions extracted from RENET_FUNCTIONS — parsing broke');

  // Allowlist (BLOCKER-gated, shared validator).
  const allowEntries = parseBlockeredList(ALLOWLIST_FILE, '#');
  const blockerFailures = verifyAllBlockers(allowEntries, rel(ALLOWLIST_FILE));
  if (blockerFailures.length > 0) {
    console.log(`${RED}✗${RESET} ${rel(ALLOWLIST_FILE)} has invalid BLOCKER(s):\n`);
    for (const f of blockerFailures) console.log(f + '\n');
    process.exit(1);
  }
  const allowlist = new Set(allowEntries.map((e) => e.entry));

  const coveredBy = (fn: string): 'literal' | 'space' | 'method' | 'helper' | null => {
    if (anyLive(fn)) return 'literal';
    if (anyLive(fn.replace(/_/g, ' '))) return 'space';
    // Method map: any method dispatching this verb, called from a live test.
    for (const [methodName, verb] of methodMap) {
      if (verb !== fn) continue;
      if (methodCalledLive(methodName)) return 'method';
      if (methodCalledViaHelper(methodName)) return 'helper';
    }
    return null;
  };

  const missing: string[] = [];
  const staleAllowlisted: string[] = [];
  for (const fn of fns) {
    const how = coveredBy(fn);
    if (how === 'helper') helperHopVerbs++;
    if (how) {
      // Burn-down enforcement: a covered verb must NOT also be allowlisted.
      if (allowlist.has(fn)) staleAllowlisted.push(fn);
      continue;
    }
    if (allowlist.has(fn)) continue;
    missing.push(fn);
  }

  // Coverage-limits disclosure (the anti-overstatement clause).
  console.log('Coverage limits (what this gate actually measured):');
  console.log(`  - live configs in registry:        ${LIVE_CONFIG_REGISTRY.length}`);
  console.log(`  - live test files expanded:         ${liveFiles.length}`);
  console.log(`  - harness verb-methods mapped:      ${methodMap.size}`);
  console.log(
    `  - live helper files (1 hop):        ${liveHelperText.size} of ${helperFiles.length}`,
  );
  console.log(`  - verbs resolved via a helper hop:  ${helperHopVerbs} (one level max)`);
  console.log(`  - renet functions checked:          ${fns.length}`);
  console.log(`  - allowlisted (legacy debt):        ${allowlist.size}\n`);

  let failed = false;

  if (staleAllowlisted.length > 0) {
    failed = true;
    console.log(
      `${RED}✗${RESET} ${staleAllowlisted.length} allowlist entr(ies) are now covered by a ` +
        `live suite — the debt is paid, remove them from ${rel(ALLOWLIST_FILE)}:`,
    );
    for (const fn of staleAllowlisted) console.log(`    - ${fn}`);
    console.log('');
  }

  if (missing.length > 0) {
    failed = true;
    console.log(
      `${RED}✗${RESET} ${missing.length} renet function(s) exercised by NO live suite:\n`,
    );
    for (const fn of missing) console.log(`    - ${fn}`);
    console.log('');
    console.log('A function counts as covered when a LIVE suite (one CI runs) either:');
    console.log(`  • mentions its verb literal ('${missing[0]}') or CLI form`);
    console.log(`    ('${missing[0]!.replace(/_/g, ' ')}'), OR`);
    console.log('  • CALLS the harness method that dispatches it (a declared-but-uncalled');
    console.log('    method does NOT count — that is the dead-coverage this gate closes).');
    console.log(`If the function genuinely cannot be covered yet, add it to`);
    console.log(`${rel(ALLOWLIST_FILE)} with a substantive '# BLOCKER: <reason>'.`);
    console.log('');
  }

  if (failed) process.exit(1);

  console.log(
    `${GREEN}✓${RESET} All ${fns.length - allowlist.size} enforced renet functions are ` +
      `covered by a live suite (${allowlist.size} legacy names allowlisted)`,
  );
}

main().catch((err) => {
  console.error(`${YELLOW}check-e2e-coverage.ts crashed:${RESET}`, err);
  process.exit(1);
});

#!/usr/bin/env node
/**
 * e2e-tests coverage gate — FORWARD direction (live-config membership).
 *
 * This is the TypeScript half of .ci/scripts/quality/check_e2e_coverage.py.
 * The Python entry point owns Phase 3 (the reverse "dispatched verbs must still
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
 *   3. HARNESS METHOD MAP — parse src/utils/renet-functions/methods/*.ts into
 *      (methodName → dispatched verb). A verb is covered by a method ONLY when
 *      `.methodName(` is CALLED from a LIVE_TESTS file (or, one hop, from a
 *      helper under src/utils/renet-functions/helpers that a live test reaches). A method
 *      that is merely DECLARED — the dead-coverage failure mode — does not count.
 *   4. COVERAGE — a renet function counts as covered when its raw verb literal
 *      or its CLI space-form appears in a LIVE_TESTS file, OR rule 3 resolves it.
 *      Everything else must sit on the BLOCKER-gated allowlist, or the gate fails.
 *      The subject set is RENET_FUNCTIONS plus every RENET_BRIDGE_FUNCTIONS name
 *      (box G1 of agent/plans/PLAN-jobs-backup-real-machine-tests.md): reading
 *      only the public list left internal verbs such as repository_migrate and
 *      repository_gc unchecked behind an "all covered" line. forwardSubjects()
 *      states why every bridge entry counts as a machine function, and
 *      bridgeReadProblems() refuses a bridge read too small to mean anything.
 *
 * The controls in runControls() run FIRST on every invocation, before any
 * verdict is computed from the helpers they prove.
 *
 * The gate PRINTS its own coverage limits (configs in the registry, files
 * expanded, helper-indirection hops) so it cannot overstate what it measured —
 * a gate that lies about its reach is the disease this repo keeps finding.
 *
 * Usage:
 *   npx tsx scripts/gates/check-e2e-coverage.ts
 *   (invoked by .ci/rediacc_ci/quality/e2e_coverage.py through FORWARD_ARGV)
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
import { parseBlockeredList, verifyAllBlockers } from '../lib/blocker-validator.js';
import { policyPath } from '../lib/policy-paths.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..', '..');

// Every root is overridable via an E2E_COV_* env var so the gate-fixture test (.ci/rediacc_ci/tests/gates/test_gate_e2e_coverage.py) can point the exact production code at a controlled fixture tree — the "prove the instrument" discipline. Unset, they resolve to the real repo paths, so production behaviour is identical whether or not the overrides exist.
const E2E_DIR = process.env.E2E_COV_E2E_DIR ?? path.join(REPO_ROOT, 'packages/e2e-tests');
const FUNCTIONS_FILE =
  process.env.E2E_COV_FUNCTIONS_FILE ??
  path.join(REPO_ROOT, 'packages/shared/src/renet-contract/data/functions.generated.ts');
const METHODS_DIR = path.join(E2E_DIR, 'src/utils/renet-functions/methods');
const HELPERS_DIR = path.join(E2E_DIR, 'src/utils/renet-functions/helpers');
const WORKFLOWS_DIR =
  process.env.E2E_COV_WORKFLOWS_DIR ?? path.join(REPO_ROOT, '.github/workflows');
const ALLOWLIST_FILE =
  process.env.E2E_COV_ALLOWLIST ?? policyPath('.e2e-coverage-allowlist', REPO_ROOT);

const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const RESET = '\x1b[0m';

/**
 * The configs CI actually executes. `playwright.config.ts` is the DEFAULT config
 * (the e2e runner called with no --config flag); the rest are named on a
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
  { file: 'playwright.backup-browse-at.config.ts', isDefault: false },
  // Suite 26 (box J6 of agent/plans/PLAN-backup-program.md): the chunk-store backup suite, run by its own ct-tests.yml job.
  { file: 'playwright.backup-storage.config.ts', isDefault: false },
  // Suite 31 (box K10 of agent/plans/PLAN-backup-program.md): the 50 GiB large-repo nightly, run by the standalone ct-backup-perf.yml.
  { file: 'playwright.backup-large-repo.config.ts', isDefault: false },
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
 * Scan .github/workflows/*.yml for the two ways a config is invoked through the
 * e2e runner (`python3 -m rediacc_ci.testrun.e2e`, or its bash twin `run-e2e.sh`):
 *   - the runner with `--config playwright.X.config.ts` → a NAMED config
 *   - the runner with no --config in the same command    → the DEFAULT config
 * A command is one logical shell line: backslash continuations are joined first,
 * so a call folded across lines is read whole, and comment lines are skipped, so
 * prose that names the runner is not mistaken for a bare default-config call.
 * The gate fails if a workflow runs a config the registry omits, if the registry
 * names a config no workflow runs, or if the registry claims a default that no
 * bare runner invocation backs.
 */
const E2E_RUNNER_RE = /(?:\brediacc_ci\.testrun\.e2e\b|\brun-e2e\.sh\b)/;

function logicalShellLines(content: string): string[] {
  const out: string[] = [];
  let pending = '';
  for (const raw of content.split('\n')) {
    if (/^\s*#/.test(raw)) {
      if (pending) out.push(pending);
      pending = '';
      continue;
    }
    if (/\\\s*$/.test(raw)) {
      pending += `${raw.replace(/\\\s*$/, '')} `;
      continue;
    }
    out.push(pending + raw);
    pending = '';
  }
  if (pending) out.push(pending);
  return out;
}

function selfCheckRegistry(): void {
  const namedInWorkflows = new Set<string>();
  let bareDefaultSeen = false;
  let runnerCalls = 0;
  const configFlagRe = /--config\s+(playwright[.\w-]*\.config\.ts)/g;

  const workflowFiles = fs.existsSync(WORKFLOWS_DIR)
    ? globSync('*.yml', { cwd: WORKFLOWS_DIR, absolute: true })
    : [];
  for (const wf of workflowFiles) {
    const content = fs.readFileSync(wf, 'utf-8');
    for (const line of logicalShellLines(content)) {
      if (!E2E_RUNNER_RE.test(line)) continue;
      runnerCalls++;
      const configs = [...line.matchAll(configFlagRe)].map((m) => m[1]!);
      if (configs.length === 0) {
        // A runner invocation with no --config drives the default config.
        bareDefaultSeen = true;
      } else {
        for (const c of configs) namedInWorkflows.add(c);
      }
    }
  }

  const registryNamed = new Set(
    LIVE_CONFIG_REGISTRY.filter((c) => !c.isDefault).map((c) => c.file)
  );
  const registryHasDefault = LIVE_CONFIG_REGISTRY.some((c) => c.isDefault);

  const problems: string[] = [];
  for (const c of namedInWorkflows) {
    if (!registryNamed.has(c)) {
      problems.push(
        `  - '${c}' is run by a workflow (--config) but is MISSING from LIVE_CONFIG_REGISTRY`
      );
    }
  }
  for (const c of registryNamed) {
    if (!namedInWorkflows.has(c)) {
      problems.push(
        `  - '${c}' is in LIVE_CONFIG_REGISTRY but NO workflow runs it (--config) — remove it or wire it`
      );
    }
  }
  if (registryHasDefault && !bareDefaultSeen) {
    problems.push(
      `  - LIVE_CONFIG_REGISTRY marks a default config but no workflow calls the e2e runner without --config`
    );
  }

  if (problems.length > 0) {
    console.log(`${RED}✗${RESET} Live-config registry drifted from the workflows:\n`);
    for (const p of problems) console.log(p);
    console.log(
      `\nThe registry in scripts/gates/check-e2e-coverage.ts must list exactly the configs CI runs.`
    );
    console.log(
      `Named configs come from '--config <file>' in .github/workflows/*.yml; the default`
    );
    console.log(
      `config is a runner call with no --config (rediacc_ci.testrun.e2e or run-e2e.sh). Reconcile the two and re-run.`
    );
    process.exit(1);
  }

  console.log(
    `${GREEN}✓${RESET} Live-config registry matches the workflows ` +
      `(${registryNamed.size} named + 1 default; ${runnerCalls} runner call(s) in ${workflowFiles.length} workflow files)`
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

function toPatternArray(v: string | RegExp | (string | RegExp)[] | undefined): {
  globs: string[];
  regexes: RegExp[];
} {
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
          `coverage set is a lie.`
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

/** methodName → dispatched verb, parsed from src/utils/renet-functions/methods/*.ts. */
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

/**
 * Every quoted name in `<name> = [ ... ] as const`, in file order, or null when
 * the array is absent or never closes.
 *
 * It reads the whole bracket SPAN, not one line at a time. The line state
 * machine it replaces opened on the assignment line and skipped the rest of
 * that line, so a one-line array (`X = ['a', 'b'] as const;`, the shape the
 * gate's own fixture test writes) yielded nothing and then ran on into the next
 * array. Null and empty are different answers on purpose: "no such array" is a
 * stale contract, "an empty one" is a broken parse, and the caller words them
 * differently.
 */
export function extractConstArray(content: string, name: string): string[] | null {
  const open = new RegExp(`\\b${name}\\s*=\\s*\\[`).exec(content);
  if (!open) return null;
  const rest = content.slice(open.index + open[0].length);
  const close = /\]\s*as\s+const\b/.exec(rest);
  if (!close) return null;
  return [...rest.slice(0, close.index).matchAll(/'([a-z0-9_]+)'/g)].map((m) => m[1]!);
}

/**
 * WHICH BRIDGE ENTRIES ARE MACHINE FUNCTIONS: all of them, and the rule is
 * read off the generated contract rather than chosen.
 *
 * RENET_BRIDGE_FUNCTIONS is emitted from renet's command Registry (every name
 * `functions once --function <name>` resolves), and every Registry entry is a
 * CommandBuilder that builds a `sudo renet ...` argv executed on the target
 * machine. The generated metadata offers no field that marks any entry
 * otherwise: every RENET_FUNCTIONS entry's FUNCTION_REQUIREMENTS row carries
 * `machine: true` (93 of 93 when this was written), and the bridge-only
 * remainder (internal and experimental verbs, plus the schema-less alias
 * ceph_clone_create) carries no requirements row at all, so excluding a prefix
 * such as daemon_* or machine_check_* would be an unchecked choice that
 * silently drops verbs from the gate. Fail toward checking: the forward subject
 * is the union, and a verb that genuinely cannot run in CI goes on the
 * allowlist with its reason, where it stays visible.
 */
export function forwardSubjects(
  publicFns: string[],
  bridgeFns: string[]
): { subjects: string[]; bridgeOnly: string[] } {
  const pub = new Set(publicFns);
  const bridgeOnly = [...new Set(bridgeFns)].filter((n) => !pub.has(n));
  return { subjects: [...new Set([...publicFns, ...bridgeOnly])], bridgeOnly };
}

/**
 * The anti-vacuity refusal for the bridge read. Empty means sound.
 *
 * Three shapes of a read that would make the widened gate check less than it
 * claims: the array is absent (a contract that predates it), it is shorter
 * than the floor (a parse that stopped early), or it is missing a PUBLIC name.
 * The last is a structural invariant of the generator, not a heuristic: the
 * public list is the schema'd subset of the same Registry, so a public name the
 * bridge read lacks means the read is truncated, whatever its length.
 */
export function bridgeReadProblems(
  publicFns: string[],
  bridgeFns: string[] | null,
  floor: number
): string[] {
  if (bridgeFns === null) {
    return [
      'RENET_BRIDGE_FUNCTIONS was not found in the contract, so no bridge verb is checked. Regenerate: private/renet/bin/renet functions generate-types --output packages/shared/src/renet-contract/data --version dev',
    ];
  }
  const problems: string[] = [];
  if (bridgeFns.length < floor) {
    problems.push(
      `read ${bridgeFns.length} name(s) from RENET_BRIDGE_FUNCTIONS, below the floor of ${floor}; the parse stopped early or the contract collapsed, and a green here would check almost nothing`
    );
  }
  const bridge = new Set(bridgeFns);
  const absent = publicFns.filter((n) => !bridge.has(n));
  if (absent.length > 0) {
    problems.push(
      `${absent.length} RENET_FUNCTIONS name(s) are missing from the RENET_BRIDGE_FUNCTIONS read (first: ${absent[0]}); the bridge list is the whole Registry, so the read is truncated`
    );
  }
  return problems;
}

/**
 * The production floor. 173 bridge names when it was set (93 public plus 80
 * internal and experimental); 150 leaves room for a legitimate retirement
 * wave and still refuses a parse that read a fraction. A fixture contract
 * (E2E_COV_FUNCTIONS_FILE) is tiny by design, so there the floor is 1 unless
 * E2E_COV_BRIDGE_FLOOR says otherwise; the public-subset check above still
 * applies to it in full.
 */
const PRODUCTION_BRIDGE_FLOOR = 150;
function bridgeFloor(): number {
  const raw = process.env.E2E_COV_BRIDGE_FLOOR;
  if (raw !== undefined) {
    const n = Number(raw);
    if (!Number.isInteger(n) || n < 1)
      fail(`E2E_COV_BRIDGE_FLOOR must be a positive integer, got '${raw}'`);
    return n;
  }
  return process.env.E2E_COV_FUNCTIONS_FILE ? 1 : PRODUCTION_BRIDGE_FLOOR;
}

/**
 * Allowlist entries that name no forward subject at all. The covered-and-listed
 * check cannot see these: a verb renet deleted is neither covered nor missing,
 * so its entry would sit in the list forever, excusing nothing.
 */
export function unknownAllowlistEntries(allowlist: Iterable<string>, subjects: string[]): string[] {
  const known = new Set(subjects);
  return [...allowlist].filter((e) => !known.has(e)).sort((a, b) => a.localeCompare(b));
}

/**
 * The controls, run FIRST on every invocation. They prove the pure helpers
 * above in both directions (something that must fire beside something that
 * must not) before any verdict is computed from them, so a regression in the
 * instrument fails as a broken instrument rather than reading as coverage.
 */
export function runControls(): string[] {
  const failures: string[] = [];
  let ran = 0;
  const check = (label: string, got: unknown, want: unknown): void => {
    ran++;
    if (JSON.stringify(got) !== JSON.stringify(want)) {
      failures.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
    }
  };
  const multi =
    "export const RENET_FUNCTIONS = [\n  'a',\n] as const;\n" +
    "export const RENET_BRIDGE_FUNCTIONS = [\n  'a',\n  'b',\n] as const;\n" +
    "export const LATER = ['z'] as const;\n";
  check('multi-line array is read whole', extractConstArray(multi, 'RENET_BRIDGE_FUNCTIONS'), [
    'a',
    'b',
  ]);
  check('MIRROR: a later array is not read into it', extractConstArray(multi, 'RENET_FUNCTIONS'), [
    'a',
  ]);
  check(
    'one-line array is read whole',
    extractConstArray(
      "export const RENET_BRIDGE_FUNCTIONS = ['a', 'b', 'c'] as const;\n",
      'RENET_BRIDGE_FUNCTIONS'
    ),
    ['a', 'b', 'c']
  );
  check(
    'MIRROR: an absent array is null, not empty',
    extractConstArray('export const X = [] as const;', 'RENET_BRIDGE_FUNCTIONS'),
    null
  );
  check(
    'MIRROR: RENET_FUNCTIONS does not match inside another name',
    extractConstArray("NOT_RENET_FUNCTIONS = ['q'] as const;", 'RENET_FUNCTIONS'),
    null
  );
  check('bridge-only names are the extra ones', forwardSubjects(['a'], ['a', 'b']).bridgeOnly, [
    'b',
  ]);
  check('MIRROR: subjects carry no duplicate', forwardSubjects(['a'], ['a', 'b']).subjects, [
    'a',
    'b',
  ]);
  check('vacuity fires on an absent array', bridgeReadProblems(['a'], null, 1).length, 1);
  check('vacuity fires below the floor', bridgeReadProblems(['a'], ['a'], 2).length, 1);
  check(
    'vacuity fires on a truncated read',
    bridgeReadProblems(['a', 'b'], ['a', 'c'], 1).length,
    1
  );
  check('MIRROR: a sound read raises nothing', bridgeReadProblems(['a'], ['a', 'b'], 2), []);
  check('unknown allowlist entry is named', unknownAllowlistEntries(['gone', 'a'], ['a']), [
    'gone',
  ]);
  check('MIRROR: a known allowlist entry is not', unknownAllowlistEntries(['a'], ['a']), []);
  const CONTROL_FLOOR = 13;
  if (ran < CONTROL_FLOOR)
    failures.push(`only ${ran} control(s) ran, below the floor of ${CONTROL_FLOOR}`);
  return failures;
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
  // Suite 24 (cluster licensing). Set by the `Run E2E Tests (K8s Multinode)` step in ct-tests.yml, which starts an account server for it.
  //
  // WHAT THIS FLAG DOES NOT CLAIM. That step also passes `--grep-invert "licensing on the fleet"`, so suite 24's VM tier is excluded
  // from the run while its ACCOUNT tier executes. Config expansion resolves
  // FILES, not test titles, so this list cannot express that split: it counts the whole file as live. That over-count is inert TODAY and was checked rather than assumed: the only bridge method suite 24 calls is `executeViaBridge`, which dispatches no renet verb and appears in the method map for none, so the file confers no verb coverage in either tier. If the VM tier ever grows a
  // `w1.<verb>Method(` call, that call would start counting as covered by a run that never executes it, and this entry must be revisited.
  CLUSTER_LICENSING_SUITE: '1',
};

/**
 * ── 5. Dark suites (box J5 of agent/plans/PLAN-backup-program.md) ──────────
 *
 * The verb check above asks "is every shipped verb exercised by a live suite";
 * it cannot see a SUITE that no CI job runs when every verb it drives happens
 * to be covered elsewhere, or allowlisted. Suite 26 was exactly that: its config
 * (playwright.backup-storage.config.ts) is in no workflow, its default-config
 * project is gated behind BACKUP_STORAGE_SUITE=1, which no workflow sets, and the
 * gate stayed green. So every test file under tests/ must be selected by a live
 * config, or be named here with a `BLOCKER:` reason. An entry whose file goes
 * live, or no longer exists, fails as stale, so this list only shrinks.
 *
 * Suite 26 is deliberately ABSENT: the gate fails on it until box J6 wires it
 * into CI (its config in a workflow and LIVE_CONFIG_REGISTRY, or
 * BACKUP_STORAGE_SUITE=1 in a workflow and CI_LEG_ENABLE_FLAGS).
 *
 * Overridable via E2E_COV_DARK_SUITES (a JSON object, path relative to the e2e
 * directory -> reason) for the fixture test.
 */
const PRODUCTION_DARK_SUITES: Record<string, string> = {
  'tests/20-image-build.test.ts':
    'BLOCKER: suite 20 builds VM images at about 35 minutes per test and no CI runner carries the image toolchain; it runs locally through playwright.image.config.ts (packages/e2e-tests/README.md "Deliberately not in CI", item 3).',
  'tests/23-cli-migrate-routing.test.ts':
    'BLOCKER: CLI_SUITE is declared empty on every ct-tests.yml matrix leg until a local two-worker validation of its rdc argv and machine registration lands (plan phase 5; the comment above the E2E Workers `include:` matrix names the one-line switch).',
  'tests/ops-lifecycle/18-ops-lifecycle.test.ts':
    'BLOCKER: these tests stop, start and reset the shared fleet the other suites run on, so no config selects them; ci-ops-test.yml drives ops setup, check, up, status and down on throwaway VMs, and the reset path (OpsManager.resetVMs) has no CI run at all.',
};
const DARK_REASON_MIN = 40;

function loadDarkSuites(): Record<string, string> {
  const override = process.env.E2E_COV_DARK_SUITES;
  if (override === undefined) return PRODUCTION_DARK_SUITES;
  const parsed: unknown = JSON.parse(override);
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    fail('E2E_COV_DARK_SUITES is not a JSON object of path -> reason');
  }
  return parsed as Record<string, string>;
}

/**
 * Every test file under tests/ that no live config selects, judged against the
 * dark-suite list. Pure over its inputs so the counts it returns are the ones
 * printed. `allTests` and `liveTests` are absolute paths.
 */
export function darkSuiteFindings(
  allTests: string[],
  liveTests: Set<string>,
  exempt: Record<string, string>,
  e2eDir: string
): { dark: string[]; problems: string[]; exempted: number } {
  const problems: string[] = [];
  const dark: string[] = [];
  let exempted = 0;
  const existing = new Set(allTests.map((f) => path.relative(e2eDir, f)));
  for (const file of allTests) {
    if (liveTests.has(file)) continue;
    const key = path.relative(e2eDir, file);
    if (key in exempt) {
      exempted++;
      continue;
    }
    dark.push(key);
  }
  for (const [key, reason] of Object.entries(exempt)) {
    if (!existing.has(key)) {
      problems.push(
        `  - dark-suite entry '${key}' names no test file under tests/ (stale: delete it)`
      );
    } else if (liveTests.has(path.join(e2eDir, key))) {
      problems.push(
        `  - dark-suite entry '${key}' is now selected by a live config (debt paid: delete it)`
      );
    }
    if (
      typeof reason !== 'string' ||
      !reason.startsWith('BLOCKER:') ||
      reason.length < DARK_REASON_MIN
    ) {
      problems.push(
        `  - dark-suite entry '${key}' needs a reason starting 'BLOCKER:' of ${DARK_REASON_MIN}+ characters`
      );
    }
  }
  return { dark, problems, exempted };
}

/**
 * Blank out `//` and block comments, preserving line structure.
 *
 * Line count is preserved so any position-based reporting stays honest, and
 * strings are left alone on purpose: see the note at the call site.
 */
export function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, lead) => lead + ' '.repeat(m.length - lead.length));
}

async function main(): Promise<void> {
  // Evaluate every conditional config under the maximal CI selection.
  for (const [k, v] of Object.entries(CI_LEG_ENABLE_FLAGS)) process.env[k] = v;

  console.log('e2e-tests coverage gate — forward (live-config membership)');
  console.log('============================================================\n');

  const controlFailures = runControls();
  if (controlFailures.length > 0) {
    console.log(
      `${RED}✗${RESET} The gate's own controls failed, so the instrument is broken and no verdict below would mean anything:\n`
    );
    for (const f of controlFailures) console.log(`  - ${f}`);
    process.exit(1);
  }

  if (!fs.existsSync(FUNCTIONS_FILE)) fail(`Functions file not found: ${rel(FUNCTIONS_FILE)}`);
  if (!fs.existsSync(E2E_DIR)) fail(`e2e-tests directory not found: ${rel(E2E_DIR)}`);

  // Read the contract and refuse a vacuous bridge read BEFORE any coverage is computed from it.
  const contract = fs.readFileSync(FUNCTIONS_FILE, 'utf-8');
  const publicFns = extractConstArray(contract, 'RENET_FUNCTIONS') ?? [];
  if (publicFns.length === 0) fail('No functions extracted from RENET_FUNCTIONS: parsing broke');
  const bridgeFns = extractConstArray(contract, 'RENET_BRIDGE_FUNCTIONS');
  const floor = bridgeFloor();
  const bridgeProblems = bridgeReadProblems(publicFns, bridgeFns, floor);
  if (bridgeProblems.length > 0) {
    console.log(
      `${RED}✗${RESET} The bridge-function read is not sound, so the forward check would cover less than it claims:\n`
    );
    for (const p of bridgeProblems) console.log(`  - ${p}`);
    process.exit(1);
  }
  const { subjects: fns, bridgeOnly } = forwardSubjects(publicFns, bridgeFns!);
  console.log(
    `${GREEN}✓${RESET} Read ${bridgeFns!.length} bridge function(s) (floor ${floor}): ` +
      `${publicFns.length} public + ${bridgeOnly.length} bridge-only, all machine functions\n`
  );

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
      `${liveFiles.length} distinct test file(s):`
  );
  for (const line of perConfigCounts) console.log(`    ${line}`);
  console.log('');

  // Dark suites: every test file under tests/ must be live or named with a BLOCKER.
  const testsDir = path.join(E2E_DIR, 'tests');
  const allTests = fs.existsSync(testsDir)
    ? globSync(DEFAULT_TEST_MATCH, { cwd: testsDir, absolute: true, nodir: true }).sort((a, b) =>
        a.localeCompare(b)
      )
    : [];
  if (allTests.length === 0) {
    fail(
      `Discovered ZERO test files under ${rel(testsDir)}; the dark-suite check is not seeing the tree, so its green would mean nothing`
    );
  }
  const darkConfigs = (globSync('playwright*.config.ts', { cwd: E2E_DIR }) as string[])
    .filter((c) => !LIVE_CONFIG_REGISTRY.some((r) => r.file === c))
    .sort((a, b) => a.localeCompare(b));
  const darkSuites = darkSuiteFindings(allTests, liveTestFiles, loadDarkSuites(), E2E_DIR);
  let darkFailed = false;
  if (darkSuites.problems.length > 0) {
    darkFailed = true;
    console.log(
      `${RED}✗${RESET} The dark-suite list in scripts/gates/check-e2e-coverage.ts is stale:\n`
    );
    for (const p of darkSuites.problems) console.log(p);
    console.log('');
  }
  if (darkSuites.dark.length > 0) {
    darkFailed = true;
    console.log(
      `${RED}✗${RESET} ${darkSuites.dark.length} e2e suite file(s) that NO CI job runs (no live config selects them):\n`
    );
    for (const f of darkSuites.dark) console.log(`    - ${f}`);
    console.log('');
    console.log(`  Configs no workflow runs: ${darkConfigs.join(', ') || '(none)'}`);
    console.log('  Wire the suite into CI: put its config on a workflow step (--config) and in');
    console.log('  LIVE_CONFIG_REGISTRY, or set its enable flag in the workflow and in');
    console.log('  CI_LEG_ENABLE_FLAGS. Only a suite that genuinely cannot run in CI goes into');
    console.log("  PRODUCTION_DARK_SUITES, with a 'BLOCKER:' reason.");
    console.log('');
  }
  if (!darkFailed) {
    console.log(
      `${GREEN}✓${RESET} Every one of ${allTests.length} e2e test file(s) is selected by a live config ` +
        `(${darkSuites.exempted} dark by BLOCKER; configs no workflow runs: ${darkConfigs.join(', ') || 'none'})\n`
    );
  }

  // Read live-test contents once, WITH COMMENTS STRIPPED.
  //
  // A comment cannot exercise anything. Counting one as coverage is not a near-miss, it is the opposite of what this gate is for, and it happened: a storage test asserted that a RETIREMENT MESSAGE names its replacement, and the verb literal inside that assertion plus the comment explaining it made `backup_restore` look exercised. The gate then demanded its allowlist entry be
  // deleted as a debt paid, which would have recorded coverage that does not exist in the very file that tracks coverage that does not exist.
  //
  // STRING LITERALS ARE DELIBERATELY KEPT. A test that really drives a verb usually names it in a string -- `exec('rdc backup restore ...')` -- so excluding strings would blind the gate to genuine coverage. Comments are the part that can never be evidence.
  const liveTestText = new Map<string, string>();
  for (const f of liveFiles) liveTestText.set(f, stripComments(fs.readFileSync(f, 'utf-8')));
  const anyLiveTest = (needle: string): boolean => {
    for (const text of liveTestText.values()) if (text.includes(needle)) return true;
    return false;
  };

  // Method map + helper-indirection (one hop).
  const methodMap = buildMethodMap();
  const helperFiles = fs.existsSync(HELPERS_DIR)
    ? globSync('*.ts', { cwd: HELPERS_DIR, absolute: true })
    : [];

  // A helper file confers coverage ONLY when a live test actually reaches it — i.e. a live test calls one of the helper's own methods (`.helperMethod(`). This is the single level of indirection the tree needs: suite 17 drives `runner.repositoryCommit(...)`, a RepositoryHelpers method that shells out `renet repository commit` (a space-form dispatch, not a `function:` literal), so
  // that helper's space-forms are genuine live coverage. A helper NO live test touches confers nothing (fail closed). RenetFunctionsTestRunner.ts is NOT a helper and is never in this set — counting its re-export delegations is exactly the dead-coverage this gate exists to reject.
  const liveHelperText = new Map<string, string>();
  for (const f of helperFiles) {
    const text = stripComments(fs.readFileSync(f, 'utf-8'));
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
  // A verb-METHOD (declared in methods/*.ts) is called-live when `.methodName(` appears in a live test, or one hop out in a live helper.
  const methodCalledLive = (methodName: string): boolean => anyLiveTest(`.${methodName}(`);
  const methodCalledViaHelper = (methodName: string): boolean => {
    for (const text of liveHelperText.values()) if (text.includes(`.${methodName}(`)) return true;
    return false;
  };
  let helperHopVerbs = 0;

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
  console.log(
    `  - e2e test files under tests/:      ${allTests.length} (${darkSuites.dark.length} dark, ${darkSuites.exempted} dark by BLOCKER)`
  );
  console.log(`  - harness verb-methods mapped:      ${methodMap.size}`);
  console.log(
    `  - live helper files (1 hop):        ${liveHelperText.size} of ${helperFiles.length}`
  );
  console.log(`  - verbs resolved via a helper hop:  ${helperHopVerbs} (one level max)`);
  console.log(
    `  - renet functions checked:          ${fns.length} (${publicFns.length} public + ${bridgeOnly.length} bridge-only)`
  );
  console.log(`  - allowlisted:                      ${allowlist.size}\n`);

  let failed = darkFailed;

  const unknownAllowed = unknownAllowlistEntries(allowlist, fns);
  if (unknownAllowed.length > 0) {
    failed = true;
    console.log(
      `${RED}✗${RESET} ${unknownAllowed.length} allowlist entr(ies) name no renet function in ` +
        `RENET_FUNCTIONS or RENET_BRIDGE_FUNCTIONS; the verb is gone, so delete the entry from ${rel(ALLOWLIST_FILE)}:`
    );
    for (const fn of unknownAllowed) console.log(`    - ${fn}`);
    console.log('');
  }

  if (staleAllowlisted.length > 0) {
    failed = true;
    console.log(
      `${RED}✗${RESET} ${staleAllowlisted.length} allowlist entr(ies) are now covered by a ` +
        `live suite — the debt is paid, remove them from ${rel(ALLOWLIST_FILE)}:`
    );
    for (const fn of staleAllowlisted) console.log(`    - ${fn}`);
    console.log('');
  }

  if (missing.length > 0) {
    failed = true;
    console.log(
      `${RED}✗${RESET} ${missing.length} renet function(s) exercised by NO live suite:\n`
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
      `covered by a live suite (${allowlist.size} allowlisted by BLOCKER)`
  );
}

main().catch((err) => {
  console.error(`${YELLOW}check-e2e-coverage.ts crashed:${RESET}`, err);
  process.exit(1);
});

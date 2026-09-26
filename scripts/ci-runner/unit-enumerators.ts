/**
 * T2.8. A test lane's units are not lock entries -- adding one gates.lock entry per
 * Playwright spec, Go package or pytest file would distort `npm run ci`'s own manifest by
 * hundreds of rows for gates that are not check gates at all. Each test lane instead
 * declares an ENUMERATOR here: a function that inspects the real tree (or shells out to
 * the same tool CI would run) and returns `{id, mutex?, needs?}` per unit, in the exact
 * shape `shardPlan` (`scripts/ci-runner/lanes.ts`) already consumes as `ShardInput` --
 * `weight` and `ci` are filled in by the caller, which knows the lane and the shard count,
 * not by the enumerator, which only knows what units exist.
 *
 * READ-ONLY, LIKE `laneCapabilities`. An enumerator inspects the tree or asks a tool to
 * list what it would run (`--list`, `go list`, a frontmatter read); none of them build,
 * launch a browser, start a daemon or run a single test. `shardPlan` takes their output
 * unchanged, so its refusals (an empty shard, a unit split across shards, a lost unit)
 * stay the correctness backbone for test lanes exactly as they are for `quality-code`.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

export interface Unit {
  id: string;
  /** Mutual-exclusion group; two units sharing one never land in different shards' concurrent leg (`shardPlan` merges them into one unit). */
  mutex?: string;
  /** Ordering edges, id-to-id, INSIDE this lane's own unit set. */
  needs?: string[];
}

export type UnitEnumerator = (repoRoot: string) => Promise<Unit[]>;

function run(cmd: string, args: readonly string[], cwd: string): string {
  return execFileSync(cmd, args, { cwd, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
}

/**
 * `test-renet-go`. One unit per Go package under `pkg/` and `cmd/`, from `go list` itself
 * rather than a hand-rolled directory walk -- `go list` is the one authority on what a
 * `go test ./...` invocation would actually build, build tags and all. Measured against the
 * real tree 2026-09-26: 83 packages, matching this plan's own section 3 count.
 *
 * NO MUTEX GROUP YET for the subscription/root/btrfs/eBPF/CSI packages T2.14 pins to one
 * leg -- that pinning is T2.14's own box (the renet submodule PR), not this enumerator's;
 * adding an unverified guess at which packages need it would be exactly the kind of
 * speculative extra the operator's constraint on this dispatch rules out.
 */
export async function renetGoUnits(repoRoot: string): Promise<Unit[]> {
  const cwd = path.join(repoRoot, 'private', 'renet');
  const out = run('go', ['list', './pkg/...', './cmd/...'], cwd);
  const ids = out
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  if (ids.length === 0) {
    throw new Error(
      `VACUOUS: renetGoUnits: "go list ./pkg/... ./cmd/..." in ${cwd} returned no packages.`
    );
  }
  return ids.map((id) => ({ id }));
}

/**
 * `test-renet-integration`. One unit per pytest file under `tests/integration`, by file
 * listing rather than `pytest --collect-only`: the files ARE the units the plan's own table
 * asks for ("pytest file (14 in `private/renet/tests/integration`)"), and a file listing
 * needs no Python environment to be correct, matching `laneCapabilities`'s own "no
 * dependency in the fast lane" reasoning for why it hand-parses YAML instead of importing a
 * parser.
 */
export async function renetIntegrationUnits(repoRoot: string): Promise<Unit[]> {
  const dir = path.join(repoRoot, 'private', 'renet', 'tests', 'integration');
  const files = fs
    .readdirSync(dir)
    .filter((f) => f.startsWith('test_') && f.endsWith('.py'))
    .sort();
  if (files.length === 0) {
    throw new Error(`VACUOUS: renetIntegrationUnits: ${dir} holds no test_*.py file.`);
  }
  return files.map((f) => ({ id: `renet-integration:${f}` }));
}

const TUTORIAL_DOC_RE = /^tutorial-(.+)\.mdx$/;
const ORDER_RE = /^order:\s*(\d+)\s*$/m;

/**
 * `ops-tutorials`. One unit per tutorial, independent -- per the operator's D-W4 revision
 * ("make every tutorial self-contained, then shard by tutorial", replacing the earlier
 * contiguous-segment and `needs`-chained design this box's own text still describes -- the
 * later ruling supersedes it). Order and membership come from the SAME source
 * `.ci/tutorials/run-sequence.sh` already treats as the single source of truth: the `order:`
 * frontmatter of `packages/www/src/content/docs/en/tutorial-*.mdx`, cross-checked one-to-one
 * against `.ci/tutorials/tutorial-<slug>.sh`. A doc with no script, or a script with no doc,
 * is drift there and a refusal here, for the same reason.
 */
export async function opsTutorialUnits(repoRoot: string): Promise<Unit[]> {
  const docsDir = path.join(repoRoot, 'packages', 'www', 'src', 'content', 'docs', 'en');
  const scriptsDir = path.join(repoRoot, '.ci', 'tutorials');
  const pairs: { order: number; slug: string }[] = [];
  for (const name of fs.readdirSync(docsDir)) {
    const m = TUTORIAL_DOC_RE.exec(name);
    if (m === null) continue;
    const slug = m[1] as string;
    const text = fs.readFileSync(path.join(docsDir, name), 'utf-8');
    const orderMatch = ORDER_RE.exec(text);
    if (orderMatch === null) {
      throw new Error(`opsTutorialUnits: ${name} has no "order:" frontmatter.`);
    }
    pairs.push({ order: Number(orderMatch[1]), slug });
  }
  if (pairs.length === 0) {
    throw new Error(`VACUOUS: opsTutorialUnits: ${docsDir} holds no tutorial-*.mdx file.`);
  }
  pairs.sort((a, b) => a.order - b.order);
  const drift: string[] = [];
  for (const { slug } of pairs) {
    if (!fs.existsSync(path.join(scriptsDir, `tutorial-${slug}.sh`))) {
      drift.push(`doc tutorial-${slug}.mdx has no script tutorial-${slug}.sh`);
    }
  }
  for (const f of fs.readdirSync(scriptsDir)) {
    const m = /^tutorial-(.+)\.sh$/.exec(f);
    if (m === null) continue;
    if (!pairs.some((p) => p.slug === (m[1] as string))) {
      drift.push(`script ${f} has no doc tutorial-${m[1] as string}.mdx`);
    }
  }
  if (drift.length > 0) {
    throw new Error(
      `opsTutorialUnits: docs/scripts drift:\n${drift.map((d) => `  - ${d}`).join('\n')}`
    );
  }
  // No `needs`: D-W4 makes every tutorial self-contained, so units are independent.
  return pairs.map(({ slug }) => ({ id: `tutorial:${slug}` }));
}

/**
 * `test-account-e2e`. One unit per spec file (99 measured 2026-09-26), except every file
 * under `10-stripe/` folds into ONE mutex unit: the plan's own table records that only the
 * leg holding that unit may start `stripe listen`, because two listeners on one sandbox
 * both receive every webhook.
 */
export async function accountE2eUnits(repoRoot: string): Promise<Unit[]> {
  const dir = path.join(repoRoot, 'private', 'account', 'e2e', 'tests');
  const files: string[] = [];
  const walk = (rel: string): void => {
    for (const entry of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
      const childRel = rel === '' ? entry.name : `${rel}/${entry.name}`;
      if (entry.isDirectory()) walk(childRel);
      else if (entry.isFile() && entry.name.endsWith('.test.ts')) files.push(childRel);
    }
  };
  walk('');
  if (files.length === 0) {
    throw new Error(`VACUOUS: accountE2eUnits: ${dir} holds no *.test.ts file.`);
  }
  files.sort();
  return files.map((f) => ({
    id: `account-e2e:${f}`,
    // 10-stripe and 12-stripe-e2e both drive the one real Stripe sandbox, so they share a leg (CI run 36277725732 scattered 12-stripe-e2e with no webhook forwarder).
    mutex:
      f.startsWith('10-stripe/') || f.startsWith('12-stripe-e2e/')
        ? 'account-e2e-stripe-sandbox'
        : undefined,
  }));
}

interface PlaywrightListSuite {
  suites?: PlaywrightListSuite[];
  specs?: { file?: string }[];
}
interface PlaywrightListReport {
  suites?: PlaywrightListSuite[];
}

function collectFiles(suite: PlaywrightListSuite, into: Set<string>): void {
  for (const spec of suite.specs ?? []) {
    if (typeof spec.file === 'string' && spec.file !== '') into.add(spec.file);
  }
  for (const child of suite.suites ?? []) collectFiles(child, into);
}

/**
 * `test-e2e-workers`. One unit per spec FILE (not per test), read from Playwright's own
 * `--list --reporter=json` rather than a directory walk, so a file excluded by the config's
 * own `testMatch`/`testIgnore` cannot silently appear as a unit that never runs. Verified
 * against the real tree 2026-09-26: 26 files, no browsers launched (`--list` only
 * enumerates).
 *
 * `13-postgres-fork-isolation`'s own 3-describe split (the plan's per-job table) is T2.12's
 * dependency-probe work, not this enumerator's -- it is one unit here until that lands.
 */
export async function e2eWorkersUnits(repoRoot: string): Promise<Unit[]> {
  const cwd = path.join(repoRoot, 'packages', 'e2e-tests');
  const out = run('npx', ['playwright', 'test', '--list', '--reporter=json'], cwd);
  let parsed: PlaywrightListReport;
  try {
    parsed = JSON.parse(out) as PlaywrightListReport;
  } catch (err) {
    throw new Error(
      `e2eWorkersUnits: "playwright test --list --reporter=json" did not print JSON: ${err instanceof Error ? err.message : String(err)}`
    );
  }
  const files = new Set<string>();
  for (const suite of parsed.suites ?? []) collectFiles(suite, files);
  if (files.size === 0) {
    throw new Error('e2eWorkersUnits: playwright --list enumerated zero spec files.');
  }
  return [...files].sort().map((f) => ({ id: `e2e-workers:${f}` }));
}

const TESTPATHS_RE = /testpaths\s*=\s*\[([^\]]*)\]/;

/**
 * `quality-pytest`. One unit per `test_*.py` file under every root `pyproject.toml`'s
 * `[tool.pytest.ini_options].testpaths` names -- read from that file rather than run
 * through pytest itself, because pytest is not guaranteed to be installed wherever this
 * enumerator runs (`check_pytest.py`'s own docstring: exit 77 means "not available", not
 * "failed"), while the config file always is. A root appearing twice (`.ci/rediacc_ci/tests`
 * and its own `.../tests/gates` subdirectory are both listed, deliberately, per
 * `pyproject.toml`'s comment on why) is de-duplicated by absolute path, so a file under both
 * is one unit, not two.
 */
export async function qualityPytestUnits(repoRoot: string): Promise<Unit[]> {
  const pyproject = fs.readFileSync(path.join(repoRoot, 'pyproject.toml'), 'utf-8');
  const m = TESTPATHS_RE.exec(pyproject);
  if (m === null) {
    throw new Error(
      'qualityPytestUnits: pyproject.toml has no [tool.pytest.ini_options].testpaths.'
    );
  }
  const roots = [...(m[1] as string).matchAll(/"([^"]+)"/g)].map((mm) => mm[1] as string);
  if (roots.length === 0) {
    throw new Error('VACUOUS: qualityPytestUnits: testpaths parsed to zero roots.');
  }
  const seen = new Map<string, string>();
  const walk = (dir: string): void => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile() && entry.name.startsWith('test_') && entry.name.endsWith('.py')) {
        seen.set(fs.realpathSync(full), path.relative(repoRoot, full));
      }
    }
  };
  for (const root of roots) {
    const dir = path.join(repoRoot, root);
    if (fs.existsSync(dir)) walk(dir);
  }
  if (seen.size === 0) {
    throw new Error(`qualityPytestUnits: testpaths ${roots.join(', ')} hold no test_*.py file.`);
  }
  return [...seen.values()].sort().map((rel) => ({ id: `pytest:${rel}` }));
}

const BATTERY_LIST_RE = /^([WST])\s+(\S+)\s*$/;

/**
 * `quality-gate-tests`. One unit per driver file `.ci/rediacc_ci/battery.py --list` names
 * (its own enumeration of `.ci/scripts/test/gates/*`, verified live 2026-09-26: 5 drivers,
 * no pytest needed -- the battery is not a pytest suite). Its `W`/`S` bucket is the exact
 * isolation contract `scripts/ci-runner/pool.ts`'s own header documents for gate `mutex` and
 * `reads`: a writer mutates shared tree state and a scanner reads it, so neither may
 * overlap with a writer OR with each other's writer -- one mutex group covers every `W` and
 * `S` unit; `T` units carry none.
 */
export async function qualityGateTestsUnits(repoRoot: string): Promise<Unit[]> {
  const out = run('python3', ['.ci/rediacc_ci/battery.py', '--list'], repoRoot);
  const units: Unit[] = [];
  for (const line of out.split('\n')) {
    const m = BATTERY_LIST_RE.exec(line);
    if (m === null) continue;
    const bucket = m[1] as string;
    const name = m[2] as string;
    units.push({
      id: `battery:${name}`,
      mutex: bucket === 'T' ? undefined : 'battery-exclusive',
    });
  }
  if (units.length === 0) {
    throw new Error('VACUOUS: qualityGateTestsUnits: "battery.py --list" named zero drivers.');
  }
  return units;
}

/** The 7 T2.7 test lanes, each to its enumerator. A lane absent here has no enumerator yet. */
export const LANE_ENUMERATORS: Readonly<Record<string, UnitEnumerator>> = {
  'test-e2e-workers': e2eWorkersUnits,
  'test-account-e2e': accountE2eUnits,
  'test-renet-go': renetGoUnits,
  'test-renet-integration': renetIntegrationUnits,
  'quality-pytest': qualityPytestUnits,
  'quality-gate-tests': qualityGateTestsUnits,
  'ops-tutorials': opsTutorialUnits,
};

export async function unitsFrom(lane: string, repoRoot: string): Promise<Unit[]> {
  const enumerator = LANE_ENUMERATORS[lane];
  if (enumerator === undefined) {
    throw new Error(
      `unitsFrom: lane "${lane}" has no declared enumerator. Known lanes: ` +
        `${Object.keys(LANE_ENUMERATORS).sort().join(', ')}.`
    );
  }
  return enumerator(repoRoot);
}

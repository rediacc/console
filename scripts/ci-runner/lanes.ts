import { readFileSync } from 'node:fs';
import path from 'node:path';

/**
 * Which quality job a gate can run in, DERIVED from the workflow rather than typed here.
 *
 * WHY THIS EXISTS. A gate's job is chosen by hand today, and a wrong choice is silent
 * until CI: check:ci-docker-npm-pins landed in `quality-static`, which checks out no
 * submodules, so `private/account/Dockerfile` dropped out of its enumeration and its
 * two entirely correct exclusions were reported as dead entries (CI job 100870135489).
 * check_syncpack_sources.py carries the identical scar from its own first run. Both
 * gates enumerate with `--recurse-submodules`; neither could say so anywhere a tool
 * would read.
 *
 * ONLY THE COST ORDER IS DECLARED HERE. Capabilities are read out of ci-quality.yml on
 * every call, because a table of them would be a second copy of the workflow and would
 * drift the first time a job changed. A lane whose job is no longer in the file is
 * REFUSED rather than skipped -- a missing lane silently narrows placement, which is
 * how a gate ends up somewhere cheaper and blinder than it needs.
 *
 * The cost order is cheapest-first: slim runners with no node before ubuntu-latest,
 * and within those, fewer setup steps before more. Placement picks the FIRST lane whose
 * capabilities are a superset of the gate's needs, so a gate that needs nothing lands
 * in the cheapest lane and one that needs submodules cannot land in a lane without them.
 */

/** Cheapest first. A job absent from the workflow is an error, never a skip. */
const LANE_ORDER = [
  'quality-static',
  'quality-branch',
  'quality-submodule-branches',
  'quality-code',
  'quality-content',
  'quality-i18n',
  'quality-security',
  'quality-packages',
  'quality-www-build',
  'quality-go',
] as const;

export interface LaneCapabilities {
  job: string;
  /** '' when the job declares none (it inherits the workflow default). */
  runsOn: string;
  timeoutMinutes: number | null;
  /** Every submodule path the job checks out; ['*'] when it takes all of them. */
  submodules: string[];
  /** setup-workspace ran, so node and the workspace deps are present. */
  node: boolean;
  /** Extra toolchains this job installs. */
  tools: string[];
}

const JOB_RE = /^ {2}([A-Za-z0-9_-]+):\s*$/;

/**
 * Capabilities of every job in one workflow, parsed by hand.
 *
 * A hand parser rather than PyYAML/`yaml`: this must run in the fast lane with no
 * dependency, and a gate that imports one dies with ModuleNotFoundError on a clean
 * runner while passing locally -- check:ci-python-gate-deps caught exactly that on a
 * gate written earlier tonight.
 */
export function laneCapabilities(workflowText: string): Map<string, LaneCapabilities> {
  const out = new Map<string, LaneCapabilities>();
  let job: LaneCapabilities | null = null;
  let inJobs = false;

  for (const raw of workflowText.split('\n')) {
    if (/^jobs:\s*$/.test(raw)) {
      inJobs = true;
      continue;
    }
    if (!inJobs) continue;
    if (raw !== '' && !/^\s/.test(raw) && !raw.startsWith('#')) break;

    const m = JOB_RE.exec(raw);
    if (m) {
      job = {
        job: m[1],
        runsOn: '',
        timeoutMinutes: null,
        submodules: [],
        node: false,
        tools: [],
      };
      out.set(m[1], job);
      continue;
    }
    if (job === null) continue;
    // PROSE IS NOT A CAPABILITY, and this module nearly shipped believing it was. The first version matched `PyYAML` and `setup-go` anywhere in the job, and quality-code MENTIONS both in comments ("ruff was pinned twice, PyYAML four times", "actions/setup-go adds that directory itself") while installing neither. It would therefore have placed a yaml-needing gate in a job with no
    // PyYAML -- the exact silent mis-placement this file exists to prevent, committed by the file itself. Caught by checking the derived table against the workflow instead of trusting it.
    if (/^\s*#/.test(raw)) continue;

    const runsOn = /^\s{4}runs-on:\s*(\S+)\s*$/.exec(raw);
    if (runsOn) job.runsOn = runsOn[1];

    const timeout = /^\s{4}timeout-minutes:\s*(\d+)\s*$/.exec(raw);
    if (timeout) job.timeoutMinutes = Number(timeout[1]);

    // `submodules: true` on a checkout takes every submodule; a targeted
    // `git submodule update --init <path>` takes exactly one. Both are real, and conflating them is how a gate needing renet lands in the job that only takes account (quality-i18n does exactly that).
    if (/^\s+submodules:\s*(true|'true'|"true"|recursive)\s*$/.test(raw)) job.submodules = ['*'];
    const targeted = /git submodule update --init(?:\s+--depth\s+\d+)?\s+(private\/[\w-]+)/.exec(
      raw
    );
    if (targeted && !job.submodules.includes('*') && !job.submodules.includes(targeted[1])) {
      job.submodules.push(targeted[1]);
    }

    if (/^\s+(?:-\s+)?uses:\s*\.\/\.github\/actions\/setup-workspace/.test(raw)) job.node = true;
    if (/^\s+(?:-\s+)?uses:\s*actions\/setup-go/.test(raw) && !job.tools.includes('go')) {
      job.tools.push('go');
    }
    if (/pip install[^\n]*\bruff\b/.test(raw) && !job.tools.includes('ruff')) {
      job.tools.push('ruff');
    }
    if (/pip install[^\n]*PyYAML/.test(raw) && !job.tools.includes('python-yaml')) {
      job.tools.push('python-yaml');
    }
  }
  return out;
}

/** Does this lane provide everything the gate asked for? */
/**
 * Needs a lane does not have to PROVIDE, because the binder installs them into the
 * emitted step itself.
 *
 * THE CAPABILITY MODEL IS AUTHORITATIVE, and this is what that decision costs. A gate
 * declaring `python-yaml` was refused every lane, because `laneCapabilities` derives
 * what a lane offers from workflow STRUCTURE (a setup step, a submodule checkout, a
 * tool install listed as its own step) and cannot see a `python3 -m pip install` inside
 * another step's `run:` block. Two gates were therefore reported as impossible to
 * place while the workflow already installs PyYAML for them at ci-quality.yml:273 and
 * :295 -- lines the binder's own ACQUIRE table emits.
 *
 * So placement asks the wrong question for these needs. "Does this lane already have
 * PyYAML" is unanswerable from structure; "can the emitted step install it" is answered
 * by the ACQUIRE table, and the answer is yes. An acquirable need is therefore not a
 * placement constraint. It is still a NEED: it is carried on the gate, and `emitStep`
 * still writes the install ahead of the command, so nothing is acquired by accident.
 *
 * Kept as a NAMED SET rather than "anything not recognised": an unknown need must
 * still refuse placement, or a typo in a header would silently place a gate anywhere.
 */
export const ACQUIRABLE: readonly string[] = ['python-yaml', 'python-mypy'];

export function satisfies(lane: LaneCapabilities, needs: readonly string[]): boolean {
  return needs.every((need) => {
    if (ACQUIRABLE.includes(need)) return true;
    if (need === 'submodules') return lane.submodules.length > 0;
    if (need.startsWith('private/')) {
      return lane.submodules.includes('*') || lane.submodules.includes(need);
    }
    if (need === 'node') return lane.node;
    return lane.tools.includes(need);
  });
}

/**
 * The cheapest lane that can run this gate, or a refusal saying what is missing.
 *
 * A LANE NAMED IN LANE_ORDER BUT ABSENT FROM THE WORKFLOW IS AN ERROR. Skipping it
 * would quietly narrow the choice and push gates into lanes they do not belong in,
 * which is the failure this module exists to prevent -- so the table cannot rot
 * silently against the file it describes.
 */
export function placeGate(
  caps: Map<string, LaneCapabilities>,
  needs: readonly string[]
): { lane: string } | { error: string } {
  const missing = LANE_ORDER.filter((j) => !caps.has(j));
  if (missing.length > 0) {
    return {
      error:
        `LANE_ORDER names ${missing.join(', ')}, which the workflow no longer defines. ` +
        'Placement cannot be trusted until the list and the file agree.',
    };
  }
  for (const j of LANE_ORDER) {
    const lane = caps.get(j);
    if (lane && satisfies(lane, needs)) return { lane: j };
  }
  return { error: `no lane provides all of: ${needs.join(', ')}` };
}

/**
 * Test lanes beyond ci-quality.yml (spec W, T2.7).
 *
 * DELIBERATELY SEPARATE FROM `LANE_ORDER`. `LANE_ORDER` and `placeGate` answer "which
 * QUALITY lane should this check gate run in", and cost-order placement there means any
 * lane whose capabilities are a superset of a gate's needs is a valid home for it.
 * `test-e2e-workers` checks out every submodule and has node -- a superset of nearly
 * every gate's needs -- so adding it to `LANE_ORDER` would let an ordinary `check:*` gate
 * satisfy-and-land inside a 40-minute VM job instead of a quality lane, which is a
 * mis-placement this file's own placeGate docstring exists to prevent. Test lanes are not
 * placement candidates: they are fixed homes for an entire pre-existing job's test suite,
 * looked up by name, never chosen by capability match.
 *
 * This registry exists only so `shardPlan` and its callers (the T3.1 lane-budget gate,
 * `npm run ci -- --lane`) can find the ONE workflow file that defines a given lane, now
 * that lanes live in more than `ci-quality.yml`. A lane absent from the workflow it names
 * here is not an error at THIS layer -- `laneCapabilities` simply returns no entry for it,
 * and `shardPlan`'s own "lane is not a job in the workflow" refusal catches it exactly as
 * it does today for `quality-*`. That is deliberate: `test-renet-go`, `test-renet-integration`,
 * `quality-pytest`, `quality-gate-tests` and `ops-tutorials` do not exist as separate jobs
 * yet (T2.14/T2.15/T2.16 split them out of `test-renet` and `quality-security`), so this
 * table names where they WILL live and stays inert -- same shape as a `SHARD_COUNTS` entry
 * for a lane the workflow does not yet define.
 */
export const TEST_LANE_WORKFLOWS: Readonly<Record<string, string>> = {
  'test-e2e-workers': '.github/workflows/ct-tests.yml',
  'test-account-e2e': '.github/workflows/ct-tests.yml',
  'test-renet-go': '.github/workflows/ct-tests.yml',
  'test-renet-integration': '.github/workflows/ct-tests.yml',
  'quality-pytest': '.github/workflows/ci-quality.yml',
  'quality-gate-tests': '.github/workflows/ci-quality.yml',
  'ops-tutorials': '.github/workflows/ci-ops-test.yml',
};

/**
 * `laneCapabilities()` over every workflow a test/quality lane can live in, merged into
 * one map keyed by job name -- the same key `shardPlan` and `placeGate` already index on.
 *
 * REFUSES A JOB-NAME COLLISION ACROSS FILES rather than letting the later file silently
 * win. Every workflow in this repo names its jobs distinctly today (measured: no job id
 * repeats between `ci.yml`, `ci-quality.yml`, `ct-tests.yml` and `ci-ops-test.yml`), so a
 * collision means two files were merged that were never meant to be, or a job was renamed
 * in one without the other -- either way a silent overwrite would let one job's runner and
 * timeout stand in for the other's.
 *
 * `workflows` is `{path: text}` rather than a `TEST_LANE_WORKFLOWS`-shaped map, so a caller
 * building it decides once which files to read (and reads each exactly once, even when
 * several lanes share one file) instead of this function re-deriving that from the
 * registry above.
 */
export function mergeLaneCapabilities(
  workflows: Readonly<Record<string, string>>
): Map<string, LaneCapabilities> {
  const out = new Map<string, LaneCapabilities>();
  for (const [path, text] of Object.entries(workflows)) {
    for (const [job, cap] of laneCapabilities(text)) {
      const already = out.get(job);
      if (already !== undefined) {
        throw new Error(
          `mergeLaneCapabilities: job "${job}" is defined in more than one of the given ` +
            `workflows (at least one is "${path}"). Lane lookup by job name is ambiguous ` +
            'while that holds, and every caller here indexes lanes by job name alone.'
        );
      }
      out.set(job, cap);
    }
  }
  return out;
}

/* -------------------------------------------------------------------------
 * SHARDING (T-SCHED B1). Pure: reads the lock and the derived lane table, and
 * writes nothing.
 * ---------------------------------------------------------------------- */

/**
 * The slice of a lock entry the planner reads.
 *
 * STRUCTURAL RATHER THAN `GateSpec` ON PURPOSE. A `GateSpec` carries `run`,
 * `leaves` and a dozen fields the planner has no opinion about, and requiring
 * them would mean every fixture in a control had to invent them -- which is how
 * a control ends up asserting over an object shaped like nothing the tree holds.
 * `GateSpec` is assignable to this, so the real lock drives it unchanged.
 */
export interface ShardInput {
  id: string;
  /** Mutual-exclusion groups. Two entries sharing one never split apart. */
  mutex?: string[];
  /** Ordering edges. An edge INSIDE the lane is a co-location constraint. */
  needs?: string[];
  /** Declared elastic width (gate-spec `cores`). Its `min` prices a gate in the count currency below; the lock no longer carries a `weight`. */
  cores?: { min: number; max: number | 'all' };
  heavy?: boolean;
  slow?: boolean;
  ci: { kind: string; job?: string; step?: string };
}

/** One matrix leg: the gates one runner will execute, in order. */
export interface Shard {
  lane: string;
  /** 1-based, so it reads the way the Actions UI numbers a matrix leg. */
  index: number;
  /** How many legs the lane has in total, carried so a leg can say `2 of 5`. */
  of: number;
  /** Straight off the lane, never re-derived: the matrix must not change these. */
  runsOn: string;
  timeoutMinutes: number | null;
  /** Topologically ordered: a `needs` target always precedes its dependent. */
  ids: string[];
  weight: number;
  slow: number;
  heavy: number;
}

/**
 * NOT exported: `ShardPlan.lanes` is how a caller reaches it, and knip counts an
 * export nothing imports as a finding. T-SCHED B2 may need to name the type; add
 * the keyword back in the change that does, not before.
 */
interface LaneShards {
  lane: string;
  /** Registered steps this lane holds in the lock. Printed as the receipt. */
  entries: number;
  /** Indivisible units after mutex and within-lane `needs` merging. */
  units: number;
  /** Units this lane merged out of existence; `entries - units`. */
  merged: number;
  shards: Shard[];
}

export interface ShardPlan {
  lanes: LaneShards[];
}

interface Unit {
  key: string;
  ids: string[];
  /** Count-currency cost: the sum of each member's declared `cores.min` (default 1). Used only for ids with no measured duration and no `durations` map to price them from. */
  weight: number;
  slow: number;
  heavy: number;
  /** Why these ids are one unit, for the refusal message. */
  reasons: string[];
}

function laneJobOf(entry: ShardInput): string | null {
  return entry.ci.kind === 'step' ? (entry.ci.job ?? null) : null;
}

/**
 * Union-find over entry ids. Small and local: the alternative is pulling a
 * dependency into a module whose whole point is that it has none.
 */
class Merge {
  private readonly parent = new Map<string, string>();
  find(x: string): string {
    let root = this.parent.get(x) ?? x;
    if (!this.parent.has(x)) this.parent.set(x, x);
    while (root !== (this.parent.get(root) ?? root)) {
      root = this.parent.get(root) as string;
    }
    let cur = x;
    while (cur !== root) {
      const next = this.parent.get(cur) as string;
      this.parent.set(cur, root);
      cur = next;
    }
    return root;
  }
  union(a: string, b: string): void {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) this.parent.set(ra, rb);
  }
}

/**
 * Order a unit's ids so a `needs` target precedes its dependent.
 *
 * CI STEPS RUN IN FILE ORDER, so a shard's id list IS its execution order. A
 * plan that put `check:ci-seo` ahead of `build:www` in the same shard would emit
 * a lane that fails on the first run, and the failure would look like a broken
 * gate rather than a broken plan.
 *
 * Kahn, with the lane's lock order as the tiebreak, so the emitted order is a
 * function of the lock alone and two runs of the planner cannot disagree.
 */
function orderUnit(
  ids: string[],
  byId: Map<string, ShardInput>,
  rank: Map<string, number>
): string[] | { error: string } {
  const inUnit = new Set(ids);
  const indeg = new Map<string, number>();
  const dependents = new Map<string, string[]>();
  for (const id of ids) {
    indeg.set(id, 0);
    dependents.set(id, []);
  }
  for (const id of ids) {
    for (const need of byId.get(id)?.needs ?? []) {
      if (!inUnit.has(need)) continue;
      indeg.set(id, (indeg.get(id) as number) + 1);
      (dependents.get(need) as string[]).push(id);
    }
  }
  const ready = ids
    .filter((id) => indeg.get(id) === 0)
    .sort((a, b) => (rank.get(a) ?? 0) - (rank.get(b) ?? 0));
  const out: string[] = [];
  while (ready.length > 0) {
    const next = ready.shift() as string;
    out.push(next);
    for (const dep of dependents.get(next) ?? []) {
      const left = (indeg.get(dep) as number) - 1;
      indeg.set(dep, left);
      if (left === 0) {
        ready.push(dep);
        ready.sort((a, b) => (rank.get(a) ?? 0) - (rank.get(b) ?? 0));
      }
    }
  }
  if (out.length !== ids.length) {
    const stuck = ids.filter((id) => !out.includes(id)).sort();
    return {
      error:
        `a \`needs\` cycle inside one shard unit: ${stuck.join(', ')}. ` +
        'No execution order exists, so no shard can hold them.',
    };
  }
  return out;
}

/**
 * HOW MANY SHARDS EACH LANE GETS. The ONE generated source, read by the matrix
 * emitter and by the `quality-complete` aggregator alike.
 *
 * WHY ONE CONSTANT AND NOT TWO. A matrix that declares five legs and an
 * aggregator that expects four is green whenever the fifth leg silently fails
 * to be created, which is exactly the shape `ci_job_aggregation.py` calls out:
 * "either half alone is dead". Both halves therefore read THIS, and
 * `check:ci-quality-complete` asserts the workflow agrees with it.
 *
 * B2 PROVED THE OBVIOUS CANDIDATE WRONG BEFORE FILLING THIS (2026-09-09).
 *
 * `quality-security` was populated at x4 on the strength of holding 166 of the lock's 477
 * registered steps -- the largest lane by a wide margin -- and then BACKED OUT, because
 * lock entries are not workflow steps. Measured on the real workflow:
 *
 *     quality-code 98 steps   quality-static 60   quality-content 42
 *     quality-go 22           quality-security 19
 *
 * The lane with 166 entries has NINETEEN steps. 149 of those entries are the gate-test
 * battery, which is ONE hand-written step, and gate-bind can only conjunct the 13 steps
 * inside its emitted region. Sharding it x4 would have left `Quality-gate unit tests` --
 * the most expensive step in the lane -- running on all four legs, turning the largest
 * cost in the job into four copies of itself. A matrix that multiplies the dominant step
 * is slower than no matrix at all.
 *
 * SO THE RANKING INVERTS: by the measure that matters, `quality-code` (98 steps, and 99
 * lock entries, so nearly every entry IS its own step) is the target, not
 * `quality-security` (5th). The x8 floor recorded here before D1 was an artifact of
 * counting heavy LOCK IDS: the five `check:lint*` ids are one `Lint` step, and once
 * `shardPlan` merges a shared step into one unit the heavy-UNIT count is 4.
 *
 * THE MECHANISM: `shardAssignment` in scripts/gate-bind.ts computes each gate's leg from
 * this constant via the same `shardPlan` that `check:ci-quality-complete` re-runs, and
 * `rewriteRegions` ANDs `matrix.shard == N` onto any header `when`. A lane absent from
 * here yields nothing and its steps emit exactly as they did before.
 *
 * POPULATED 2026-09-20, `quality-code` AT FOUR, AND EVERY TERM OF THAT IS MEASURED.
 *
 * Candidates, ranked by the only currency that decides this -- how much of the lane sits
 * inside the emitted region, where a conjunct can reach it. Lock entries joined to
 * `.ci/cache/gate-durations.json` at the floor-of-recent the tier oracle uses
 * (scripts/gates/check-gate-manifest.ts:513):
 *
 *     lane               entries  region steps  replicated  region s  replicated s
 *     quality-code           102            65    33 (32%)      1139           476
 *     quality-static          58            55      3 (5%)       294            30
 *     quality-content         43            31    12 (28%)       136            51
 *     quality-www-build       16             7     9 (56%)        53           129
 *     quality-i18n            40             8    32 (80%)        28           309
 *     quality-security       166            13   153 (92%)        54          3253
 *
 * `quality-code` is the only lane carrying wall clock worth dividing. It is also the ONLY
 * lane ever measured on a real runner rather than locally -- 568 s and 644 s against a
 * `timeout-minutes: 15` budget, runs 34811039022 and 34740890431 -- and the two models
 * agree on the ratio, which is what makes the local figures usable here: real-CI
 * arithmetic puts x4 at 1.46x, the local floor sums put it at 1.49x.
 *
 * FOUR IS THE FLOOR AND THE KNEE AT ONCE. `shardPlan` refuses x2 and x3 outright ("4 heavy
 * gate(s) but only 3 shard(s)"), so four is the smallest realisable count. Above it the
 * return collapses, because the `Lint` unit bounds the makespan: x5 measures 1.49x, x6
 * 1.72x and x8 1.74x, each for more runners than the lane can use.
 *
 * `quality-static` is the better-DISTRIBUTED lane (5% replicated, no heavy) and is
 * deliberately not here: it runs on `ubuntu-slim`, whose minimal image is the reason
 * `check_commands.py:169` and `shell_size.py:57` exist, and D4's receipt step is a `node`
 * invocation. A lane whose receipt cannot run is a lane whose shards cannot report.
 */
export const SHARD_COUNTS: Readonly<Record<string, number>> = { 'quality-code': 4 };

/**
 * T-SCHED B2 D2. The ceiling on a sharded lane's REPLICATED share -- lock entries whose
 * `ci.step` gate-bind does not emit inside the lane's region, so no conjunct can ever
 * reach them and they run on EVERY leg. A fraction in (0, 1], one entry per key in
 * `SHARD_COUNTS` (`shardAssignment` refuses a lane present in one and absent from the
 * other, the same both-directions discipline `SHARD_COUNTS` itself is held to).
 *
 * WHY THIS HAS TO BE ARITHMETIC AND NOT A HUMAN NOTICING. `quality-security` was hand-
 * picked as B2's first target on the strength of holding 166 of the lock's then-477
 * entries, then backed out once `SHARD_COUNTS` populated it and `gate-bind --write` ran:
 * 149 of those 166 are `Quality-gate unit tests`, one hand-written step outside any
 * region, so the matrix would have multiplied the lane's single most expensive step by
 * every leg -- slower than no matrix, and nothing short of running it caught it. A
 * declared ceiling turns that into a refusal at `--write` time, before a single runner
 * is added: quality-security's replicated share is ~153/166, about 92%, so any ceiling
 * under that refuses it without a human having to re-derive the arithmetic by hand.
 *
 * `quality-code`'s own share, measured against the live lock and the live region: 33 of
 * 102 entries, 32.4%. The ceiling is set at 0.35 rather than at the measurement, so a
 * single new hand-written step does not red the gate, and three do. It is not slack for
 * its own sake: the same 33 entries carry 476 s of the lane's 1615 s, and the two changes
 * that would move them into the region (splitting the composite `Lint` step, and giving
 * `check:types` and `check:ci-dead-bash` declarations) are the prerequisite for raising
 * this lane's ceiling past 1.46x. Lowering this number is how that progress gets ratcheted.
 */
export const SHARD_REPLICATED_MAX: Readonly<Record<string, number>> = { 'quality-code': 0.35 };

/**
 * Shard each named lane, or REFUSE and say why.
 *
 * THE REFUSALS ARE THE POINT, and each of the five exists because its silent
 * form reports green having run nothing:
 *
 *   1. A lane the workflow no longer defines. Same reasoning as `placeGate`: a
 *      missing lane must not narrow anything quietly.
 *   2. A lane with ZERO entries in the lock. The plan is then not seeing the
 *      tree, and every shard it emits would be a runner that checks nothing.
 *   3. More shards than the lane has INDIVISIBLE UNITS. The box says "more
 *      shards than gates must REFUSE"; units is the stricter and correct
 *      threshold, because a mutex group and a `needs` chain are each one unit
 *      no matter how many gates they hold. An empty shard is a green job that
 *      ran nothing, which is the whole failure this programme is about.
 *   4. A single unit holding more than one `heavy` gate. Then no plan at all
 *      satisfies "heavy at most one per shard", and saying so is better than
 *      quietly relaxing the rule the caller asked for.
 *   5. More `heavy` gates in the lane than shards asked for. Same rule, the
 *      aggregate half; the message names the minimum that would work.
 *
 * THE LANE'S SET IS EVERY REGISTERED STEP, not every `gate: true` entry. Seven
 * lock entries are steps with `gate: false` (check:lint, check:i18n,
 * check:ci-i18n-cross-locale, check:ci-seo, check:ci-redirects, build:www and
 * check:ci-quality-gates, measured 2026-09-09). Each one still occupies a step in
 * its job, so a plan that dropped them would emit a lane missing work CI runs
 * today, and `build:www` in particular is what twelve other entries `needs`.
 *
 * THE BOX NAMES THREE RULES AND THE TREE HAS A FOURTH. `mutex`, `heavy` and
 * `weight`/`slow` are the declared three. Measured on gates.lock.json, twelve
 * entries in `quality-www-build` declare `needs: [build:www]` and `build:www`
 * is a step in that same lane, so a plan honouring only the three would put a
 * gate in a runner that never built the thing it validates. A within-lane
 * `needs` edge is therefore a co-location constraint here, exactly like a
 * mutex group.
 */
/**
 * T2.9. Measured cost per id (milliseconds, p90), read from `.ci/config/lane-durations.json`.
 * OPTIONAL and additive: `shardPlan`'s fourth argument, defaulting to none, so every
 * existing call site (today, all of them) keeps balancing on `weight` exactly as before.
 *
 * A UNIT'S COST FALLS BACK TO `weight` UNLESS EVERY ONE OF ITS MEMBER IDS HAS A MEASURED
 * DURATION. A unit is one indivisible thing after `shardPlan`'s own mutex/step/needs
 * merge, so packing it by a PARTIAL sum (three of five merged ids measured, two not) would
 * understate its real cost by exactly the unmeasured share -- worse than the honest
 * `weight` fallback, which at least does not pretend precision it does not have. `quality-
 * code` has zero entries in `lane-durations.json` today (T3.2, not yet run), so every one
 * of its units falls back to `weight` and its plan is BYTE-IDENTICAL to a call with no
 * `durations` argument at all -- the selftest control below asserts exactly that.
 */
function unitCost(unit: Unit, durations: Readonly<Record<string, number>> | undefined): number {
  if (durations !== undefined) {
    let sum = 0;
    for (const id of unit.ids) {
      const ms = durations[id];
      if (ms === undefined) {
        sum = -1;
        break;
      }
      sum += ms;
    }
    if (sum >= 0) return sum;
  }
  return unit.weight;
}

/**
 * THE CURRENCY, after the lock lost `weight` (operator ruling 2026-10-05). Two currencies never mix in one lane: milliseconds when a `durations` map prices the lane, otherwise a count (one per gate, or its declared `cores.min`). `withMeasuredFallback` is what keeps them apart. A map that prices SOME of a lane's units used to leave the rest at a count of 1 beside the others' 10,000 ms, so an unmeasured gate weighed nothing and LPT stacked them all in one shard; an unmeasured member now costs the MEDIAN measured member of the lane, a neutral guess in the same unit. A lane the map prices not at all (no id matches) stays in counts, byte-identical to no map.
 */
function withMeasuredFallback(
  entries: readonly ShardInput[],
  durations: Readonly<Record<string, number>> | undefined
): Readonly<Record<string, number>> | undefined {
  if (durations === undefined) return undefined;
  const measured = entries
    .map((e) => durations[e.id])
    .filter((ms): ms is number => typeof ms === 'number' && Number.isFinite(ms) && ms > 0)
    .sort((a, b) => a - b);
  if (measured.length === 0) return durations;
  const median = measured[Math.floor(measured.length / 2)] as number;
  const out: Record<string, number> = { ...durations };
  for (const e of entries) if (out[e.id] === undefined) out[e.id] = median;
  return out;
}

/**
 * The measured CI step p90 of each gate, in milliseconds, from a parsed `.ci/config/lane-durations.json` (`gate_step_p90_seconds`), as `shardPlan`'s `durations` argument. A shard plan priced by count put 21 s and 216 s of measured step time into two `quality-code` legs of equal count (PLAN-prepush-full-cpu, writer F), so every planner of the committed legs prices by this map: gate-bind's emitter, check-quality-complete's verifier, check-lane-budget's committed-plan control and the runner's own scheduling fallback. The three file readers share `measuredStepDurations` below, because a planner that priced by count beside one that priced by this map could never agree (check-lane-budget's control did exactly that from 00fa66691 until it moved here). Absent, malformed or non-positive entries are left out, and `shardPlan` then costs those gates at the lane's median.
 */
export function stepDurationsMs(laneDurations: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  const raw = (laneDurations as { gate_step_p90_seconds?: Record<string, unknown> } | null)
    ?.gate_step_p90_seconds;
  for (const [id, s] of Object.entries(raw ?? {})) {
    if (typeof s === 'number' && Number.isFinite(s) && s > 0) out[id] = s * 1000;
  }
  return out;
}

/** `stepDurationsMs` over `<root>/.ci/config/lane-durations.json`, the LIVE measurement and nothing else; {} when the file cannot be read, which prices every lane by count. Only gate-bind's re-plan decision reads this directly; every other planner reads `measuredStepDurations`. */
export function liveStepDurations(root: string): Record<string, number> {
  try {
    return stepDurationsMs(
      JSON.parse(readFileSync(path.join(root, '.ci', 'config', 'lane-durations.json'), 'utf-8'))
    );
  } catch {
    return {};
  }
}

/**
 * The prices every planner of the COMMITTED legs uses: `liveStepDurations`, with each sharded lane's ids priced instead at the snapshot its committed manifest recorded (`pricedMs`, see `stickyShardPlan`). gate-bind keeps a committed plan whose re-plan would gain under `RESHARD_MIN_GAIN_MS`, and the plan it keeps was priced by an older `lane-durations.json`; a verifier that re-planned at today's prices would then disagree with the legs CI really ran. Planning at the snapshot reproduces the committed legs exactly, because a lane's plan reads the prices of that lane's ids and nothing else. A lane whose manifest has no snapshot keeps the live prices.
 */
export function measuredStepDurations(root: string): Record<string, number> {
  const snapshots: Readonly<Record<string, number | null>>[] = [];
  for (const lane of Object.keys(SHARD_COUNTS)) {
    const priced = readPricedSnapshot(root, lane);
    if (priced !== undefined) snapshots.push(priced);
  }
  return overlayPricing(liveStepDurations(root), snapshots);
}

/** The `pricedMs` snapshot of `<root>/.ci/config/shards/<lane>.json`, or undefined when the file, or the field, is absent or malformed. */
function readPricedSnapshot(
  root: string,
  lane: string
): Readonly<Record<string, number | null>> | undefined {
  try {
    const file = JSON.parse(
      readFileSync(path.join(root, '.ci', 'config', 'shards', `${lane}.json`), 'utf-8')
    ) as { pricedMs?: unknown };
    return pricedSnapshotOf(file.pricedMs);
  } catch {
    return undefined;
  }
}

/** A manifest's `pricedMs` field as a snapshot, or undefined when it is not an object of positive numbers and nulls. */
export function pricedSnapshotOf(raw: unknown): Record<string, number | null> | undefined {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const out: Record<string, number | null> = {};
  for (const [id, ms] of Object.entries(raw as Record<string, unknown>)) {
    if (ms === null) out[id] = null;
    else if (typeof ms === 'number' && Number.isFinite(ms) && ms > 0) out[id] = ms;
    else return undefined;
  }
  return out;
}

/** `live` with every id a snapshot names priced at the snapshot's value instead; a null there means "unpriced when the plan was made", so the id is left out and `shardPlan` costs it at the lane median, exactly as it did then. Pure. */
export function overlayPricing(
  live: Readonly<Record<string, number>>,
  snapshots: readonly Readonly<Record<string, number | null>>[]
): Record<string, number> {
  const out: Record<string, number> = { ...live };
  for (const snapshot of snapshots) {
    for (const [id, ms] of Object.entries(snapshot)) {
      if (ms === null) delete out[id];
      else out[id] = ms;
    }
  }
  return out;
}

/**
 * THE RE-PLAN HYSTERESIS (#d901ba82). gate-bind replaces a sharded lane's committed legs only when the fresh plan's WORST leg is at least this much cheaper than the committed plan's worst leg, both priced at today's measurement. Below it, the committed plan stays byte for byte.
 *
 * MEASURED 2026-10-06 over every commit that rewrote `.ci/config/shards/quality-code.json`: the four lane-durations refreshes of 2026-10-05/06 (7fe78ca13, ca285d61d, f288a0d4e, 6fe24d1cb) each reshuffled the legs (112-130 manifest lines, 74-92 ci-quality.yml lines) for a worst-leg gain of 0.0, 0.0, 0.0 and 0.7 s against a 121 s worst leg, while the one re-plan that mattered, 00fa66691, cut the worst leg from 221 s to 121 s. 15 s sits two orders of magnitude above the churn and well under the real gain, and is 12% of today's worst leg. Same spirit as check-lane-budget's `REBALANCE_ADVISORY_MIN` (30 s, advisory, other lanes); its own constant, because this one decides a write.
 */
export const RESHARD_MIN_GAIN_MS = 15_000;

/** The per-leg ceiling, in minutes, a committed leg is held to. check-lane-budget's `PER_LEG_BUDGET_MIN` is this constant; a sharded lane's leg is also held to its job's `timeout-minutes` when that is lower. */
export const SHARD_LEG_CAP_MIN = 12;

/** A committed plan, as `stickyShardPlan` reads it: the manifest's legs and its pricing snapshot. */
export interface ShardAnchor {
  legs: readonly { index: number; ids: readonly string[] }[];
  pricedMs?: Readonly<Record<string, number | null>>;
}

/** Each leg's cost in the planner's own currency (`withMeasuredFallback`'s milliseconds, else count) at `durations`. An id outside the lane costs nothing here; `committedPlanFindings` is what names it. Pure. */
export function legCostsMs(
  lane: string,
  lock: readonly ShardInput[],
  legs: readonly { ids: readonly string[] }[],
  durations: Readonly<Record<string, number>> | undefined
): number[] {
  const entries = lock.filter((e) => laneJobOf(e) === lane);
  const byId = new Map(entries.map((e) => [e.id, e]));
  const priced = withMeasuredFallback(entries, durations);
  return legs.map((leg) =>
    leg.ids.reduce((sum, id) => {
      const entry = byId.get(id);
      if (entry === undefined) return sum;
      return sum + (priced?.[id] ?? Math.max(1, entry.cores?.min ?? 1));
    }, 0)
  );
}

/** Everything structurally wrong with a committed plan for `lane` at `want` legs: a leg count or index that is off, an empty leg, a lane gate in no leg, a gate in two legs, an id the lane does not hold. Empty means the shape is sound; `stickyShardPlan` still replays it through the planner for the rules this cannot see (mutex, needs, heavy). Pure. */
export function committedPlanFindings(
  lane: string,
  lock: readonly ShardInput[],
  anchor: ShardAnchor,
  want: number
): string[] {
  const findings: string[] = [];
  if (anchor.legs.length !== want) {
    findings.push(
      `${lane}: committed plan has ${anchor.legs.length} leg(s), the lane asks for ${want}`
    );
  }
  const indexes = anchor.legs.map((l) => l.index).sort((a, b) => a - b);
  if (indexes.some((index, i) => index !== i + 1)) {
    findings.push(
      `${lane}: committed leg indexes are ${indexes.join(', ')}, not 1..${anchor.legs.length}`
    );
  }
  const laneIds = new Set(lock.filter((e) => laneJobOf(e) === lane).map((e) => e.id));
  const legOf = new Map<string, number>();
  for (const leg of anchor.legs) {
    if (leg.ids.length === 0) findings.push(`${lane}: committed leg ${leg.index} is EMPTY`);
    for (const id of leg.ids) {
      const prior = legOf.get(id);
      if (prior !== undefined) {
        findings.push(`${lane}: ${id} is in committed legs ${prior} and ${leg.index}`);
      } else {
        legOf.set(id, leg.index);
      }
      if (!laneIds.has(id)) {
        findings.push(`${lane}: committed leg ${leg.index} holds ${id}, which the lane does not`);
      }
    }
  }
  for (const id of [...laneIds].sort()) {
    if (!legOf.has(id)) findings.push(`${lane}: ${id} is in no committed leg`);
  }
  return findings;
}

/** `stickyShardPlan`'s answer: the shards to emit, the pricing snapshot to record beside them, and why. */
export interface StickyShardPlan {
  shards: Shard[];
  pricedMs: Record<string, number | null>;
  kept: boolean;
  /** One line naming why the committed plan was kept or replaced. */
  reason: string;
  /** What made the committed plan unusable, when that is why it was replaced. */
  findings: string[];
  /** Committed worst leg minus fresh worst leg at live prices; null with no usable committed plan. */
  gainMs: number | null;
}

/**
 * The plan gate-bind emits for one sharded lane: the COMMITTED plan unless it is unusable or a fresh plan beats its worst leg by `minGainMs`.
 *
 * Unusable means any of: no committed plan or no `pricedMs` snapshot; a `committedPlanFindings` finding (a gate missing, a gate in two legs, a leg count off); the planner, re-run at the snapshot's prices, no longer producing exactly these legs (the lock changed a gate, a mutex, a `needs` edge or a heavy flag); a leg over `legCapMs` at live prices. A fresh plan records the live prices of the lane's ids as its snapshot; a kept plan keeps its own. Pure.
 */
export function stickyShardPlan(
  lock: readonly ShardInput[],
  caps: ReadonlyMap<string, LaneCapabilities>,
  lane: string,
  want: number,
  live: Readonly<Record<string, number>>,
  anchor: ShardAnchor | undefined,
  minGainMs: number = RESHARD_MIN_GAIN_MS,
  legCapMs: number = SHARD_LEG_CAP_MIN * 60_000
): StickyShardPlan | { error: string } {
  const freshPlan = shardPlan(lock, caps, { [lane]: want }, live);
  if ('error' in freshPlan) return { error: freshPlan.error };
  const fresh = (freshPlan.lanes[0] as LaneShards).shards;
  const laneIds = lock.filter((e) => laneJobOf(e) === lane).map((e) => e.id);
  const livePriced: Record<string, number | null> = {};
  for (const id of [...laneIds].sort()) livePriced[id] = live[id] ?? null;
  const replan = (reason: string, findings: string[] = [], gainMs: number | null = null) => ({
    shards: fresh,
    pricedMs: livePriced,
    kept: false,
    reason,
    findings,
    gainMs,
  });
  if (anchor === undefined) return replan('no committed plan');
  const findings = committedPlanFindings(lane, lock, anchor, want);
  if (anchor.pricedMs === undefined) {
    findings.push(`${lane}: committed plan records no pricing snapshot (pricedMs)`);
  }
  if (findings.length > 0) return replan('the committed plan is unusable', findings);
  const replayPlan = shardPlan(
    lock,
    caps,
    { [lane]: want },
    overlayPricing(live, [anchor.pricedMs ?? {}])
  );
  if ('error' in replayPlan) {
    return replan('the committed plan is unusable', [
      `${lane}: replay refused: ${replayPlan.error}`,
    ]);
  }
  const replay = (replayPlan.lanes[0] as LaneShards).shards;
  const sameLegs =
    replay.length === anchor.legs.length &&
    replay.every(
      (s) =>
        JSON.stringify(anchor.legs.find((l) => l.index === s.index)?.ids ?? null) ===
        JSON.stringify(s.ids)
    );
  if (!sameLegs) {
    return replan('the committed plan is unusable', [
      `${lane}: the planner no longer produces the committed legs at their own recorded prices, so the lock changed under them`,
    ]);
  }
  const cap = caps.get(lane)?.timeoutMinutes;
  const capMs = Math.min(legCapMs, cap === null || cap === undefined ? Infinity : cap * 60_000);
  const committedCosts = legCostsMs(lane, lock, anchor.legs, live);
  const over = committedCosts
    .map((ms, i) => ({ ms, index: anchor.legs[i]?.index }))
    .filter((leg) => leg.ms > capMs);
  if (over.length > 0) {
    return replan(
      'the committed plan is unusable',
      over.map(
        (leg) =>
          `${lane}: committed leg ${leg.index} costs ${(leg.ms / 1000).toFixed(1)} s, over its ${(capMs / 1000).toFixed(0)} s cap`
      )
    );
  }
  const freshWorst = Math.max(...legCostsMs(lane, lock, fresh, live));
  const gainMs = Math.max(...committedCosts) - freshWorst;
  if (gainMs >= minGainMs) {
    return replan(
      `a fresh plan cuts the worst leg by ${(gainMs / 1000).toFixed(1)} s (threshold ${(minGainMs / 1000).toFixed(0)} s)`,
      [],
      gainMs
    );
  }
  return {
    shards: replay,
    pricedMs: { ...(anchor.pricedMs ?? {}) },
    kept: true,
    reason: `kept: a fresh plan would cut the worst leg by ${(gainMs / 1000).toFixed(1)} s, under the ${(minGainMs / 1000).toFixed(0)} s threshold`,
    findings: [],
    gainMs,
  };
}

export function shardPlan(
  lock: readonly ShardInput[],
  caps: ReadonlyMap<string, LaneCapabilities>,
  shards: Readonly<Record<string, number>>,
  durations?: Readonly<Record<string, number>>
): ShardPlan | { error: string } {
  const laneNames = Object.keys(shards).sort();
  if (laneNames.length === 0) {
    return {
      error:
        'shardPlan was asked to shard no lanes at all. An empty plan is not a plan; ' +
        'name the lanes and how many shards each gets.',
    };
  }
  if (lock.length === 0) {
    return {
      error:
        'shardPlan was handed an EMPTY lock, so it cannot see the tree. Every shard it ' +
        'produced would be a runner with nothing to run.',
    };
  }

  const byId = new Map<string, ShardInput>();
  for (const entry of lock) byId.set(entry.id, entry);

  const out: LaneShards[] = [];
  for (const lane of laneNames) {
    const want = shards[lane] as number;
    if (!Number.isInteger(want) || want < 1) {
      return {
        error: `lane ${lane}: ${String(want)} is not a shard count; it must be an integer >= 1.`,
      };
    }
    if (!caps.has(lane)) {
      return {
        error:
          `lane ${lane} is not a job in the workflow, so its runner and timeout cannot be ` +
          'derived. Sharding a lane nothing defines would emit a matrix leg CI refuses.',
      };
    }
    const cap = caps.get(lane) as LaneCapabilities;

    const entries = lock.filter((e) => laneJobOf(e) === lane);
    if (entries.length === 0) {
      return {
        error:
          `lane ${lane} has ZERO entries in the lock. That is not an empty lane, it is a ` +
          'planner that is not seeing the tree, and its shards would report green having ' +
          'run nothing.',
      };
    }
    const rank = new Map<string, number>();
    entries.forEach((e, i) => rank.set(e.id, i));
    const laneIds = new Set(entries.map((e) => e.id));

    // MERGE. Mutex groups, then step-sharing, then within-lane `needs`.
    const merge = new Merge();
    for (const e of entries) merge.find(e.id);
    const groups = new Map<string, string[]>();
    for (const e of entries) {
      for (const m of e.mutex ?? []) {
        const members = groups.get(m) ?? [];
        members.push(e.id);
        groups.set(m, members);
      }
    }
    const reasonFor = new Map<string, string[]>();
    for (const [group, members] of groups) {
      for (const id of members.slice(1)) merge.union(members[0] as string, id);
      if (members.length > 1) {
        const root = merge.find(members[0] as string);
        const list = reasonFor.get(root) ?? [];
        list.push(`mutex ${group}`);
        reasonFor.set(root, list);
      }
    }
    // STEP-SHARING (T-SCHED B2 D1). Several ids can ride ONE emitted workflow step (`check:lint`, `check:lint:cli`, ... all inside `ci-quality.yml`'s single `Lint` step) -- the ids are one `run:` block in one shell, so a shard boundary between them is unrealisable: gate-bind attaches exactly one conjunct per STEP, never per id. Union them before `needs`, so a needs edge landing on
    // a step-sharing id still walks to the right unit. A shared-step unit's heavy peak is ONE, the same treatment `concurrentHeavy` below already gives a mutex-only unit and for the same reason: today they genuinely run together in one process, one runner, never concurrently with themselves. `mergedByNeeds` (below) only marks a unit that also carries a needs edge, so a pure
    // step-shared unit is untouched by the `overloaded` refusal without a separate exemption.
    const stepGroups = new Map<string, string[]>();
    for (const e of entries) {
      if (e.ci.kind !== 'step' || !e.ci.step) continue;
      const members = stepGroups.get(e.ci.step) ?? [];
      members.push(e.id);
      stepGroups.set(e.ci.step, members);
    }
    for (const [step, members] of stepGroups) {
      for (const id of members.slice(1)) merge.union(members[0] as string, id);
      if (members.length > 1) {
        const root = merge.find(members[0] as string);
        const list = reasonFor.get(root) ?? [];
        list.push(`one step "${step}"`);
        reasonFor.set(root, list);
      }
    }
    let needsEdges = 0;
    // MEMBERS, NOT ROOTS. Recording `merge.find(e.id)` here was wrong and my own anti-silencer control caught it: union-find roots MOVE as later unions land, so a root captured mid-loop can name a set that no longer exists by the end, and the needs-merged unit then slips past the refusal below. Resolve the roots once, after every union is in.
    const needsMembers: string[] = [];
    for (const e of entries) {
      for (const need of e.needs ?? []) {
        if (!laneIds.has(need)) continue;
        needsEdges += 1;
        merge.union(e.id, need);
        needsMembers.push(e.id);
      }
    }
    const mergedByNeeds = new Set(needsMembers.map((id) => merge.find(id)));

    const units = new Map<string, Unit>();
    for (const e of entries) {
      const root = merge.find(e.id);
      const unit = units.get(root) ?? {
        key: root,
        ids: [],
        weight: 0,
        slow: 0,
        heavy: 0,
        reasons: [],
      };
      unit.ids.push(e.id);
      unit.weight += Math.max(1, e.cores?.min ?? 1);
      unit.slow += e.slow ? 1 : 0;
      unit.heavy += e.heavy ? 1 : 0;
      units.set(root, unit);
    }
    for (const [root, list] of reasonFor) {
      const unit = units.get(merge.find(root));
      if (unit) unit.reasons.push(...list);
    }
    const unitList = [...units.values()];

    if (want > unitList.length) {
      const biggest = unitList.reduce((a, b) => (b.ids.length > a.ids.length ? b : a));
      return {
        error:
          `lane ${lane}: ${want} shards asked for, but the lane holds only ${unitList.length} ` +
          `indivisible unit(s) (${entries.length} entries, ${groups.size} mutex group(s), ` +
          `${needsEdges} within-lane needs edge(s); largest unit ${biggest.ids.length}). ` +
          'At least one shard would be EMPTY, and an empty shard is a job that reports green ' +
          'having run nothing. Ask for at most ' +
          `${unitList.length}.`,
      };
    }

    // A MUTEX GROUP'S MEMBERS NEVER COEXIST, so two heavies inside one are not two heavies at once. `gate-spec.ts:44` defines mutex as "no two gates sharing a group overlap", and `heavy` bounds CONCURRENT heap (`--heavy-limit`) -- so a unit whose only reason for being indivisible is a mutex group has a peak of ONE heavy however many it holds, and refusing it would be refusing
    // arithmetic.
    //
    // MEASURED 2026-09-09: this is not hypothetical. `quality-go`'s `account-vitest` group holds `check:ci-account-server` and `check:ci-account-scope-audit`, both heavy, and the first version of this refusal made that lane unshardable at EVERY shard count. The two never run together, so nothing was ever at risk.
    //
    // A unit merged by `needs` is the opposite case and still refuses: co-location without exclusion means both really are resident.
    const overloaded = unitList.find((u) => u.heavy > 1 && mergedByNeeds.has(u.key));
    if (overloaded) {
      return {
        error:
          `lane ${lane}: ${overloaded.ids.length} gate(s) are one indivisible unit ` +
          `(${overloaded.reasons.join('; ') || 'needs edges'}) and ${overloaded.heavy} of them are ` +
          `heavy: ${overloaded.ids.sort().join(', ')}. No shard count satisfies "heavy at most ` +
          'one per shard" while that unit stays whole. Split the group or drop a heavy flag.',
      };
    }
    // Concurrent heavies, for the same reason: a mutex-only unit contributes ONE.
    const concurrentHeavy = (u: Unit): number =>
      u.heavy > 1 && !mergedByNeeds.has(u.key) ? 1 : u.heavy;
    const heavyTotal = unitList.reduce((n, u) => n + concurrentHeavy(u), 0);
    if (heavyTotal > want) {
      return {
        error:
          `lane ${lane}: ${heavyTotal} heavy gate(s) but only ${want} shard(s), and heavy is ` +
          `capped at one per shard. Ask for at least ${heavyTotal} shards, or drop a heavy flag.`,
      };
    }

    // BALANCE. Longest-processing-time first: the achievable floor is the heaviest single unit, so it has to be placed while every shard is still empty. `slow` breaks a cost tie because a slow gate is the one whose real cost the count currency is least likely to describe.
    //
    // T2.9: the currency is `unitCost` (measured p90 milliseconds when every member id of the unit has one, else `weight`), not `weight` directly. For every lane measured so far (`durations` absent, or present with no entries matching this lane's ids -- true of `quality-code` until T3.2 runs) `unitCost` returns exactly `unit.weight` for every unit, so this ordering and the packing below stay unchanged.
    const priced = withMeasuredFallback(entries, durations);
    const ordered = [...unitList].sort((a, b) => {
      const costB = unitCost(b, priced);
      const costA = unitCost(a, priced);
      if (costB !== costA) return costB - costA;
      if (b.slow !== a.slow) return b.slow - a.slow;
      if (b.ids.length !== a.ids.length) return b.ids.length - a.ids.length;
      return (rank.get(a.ids[0] as string) ?? 0) - (rank.get(b.ids[0] as string) ?? 0);
    });

    const bins: Unit[][] = Array.from({ length: want }, () => []);
    const binCost = new Array<number>(want).fill(0);
    const binHeavy = new Array<number>(want).fill(0);
    for (const unit of ordered) {
      // PEAK, NOT RAW COUNT. A mutex- or step-merged unit's `heavy` field is a sum over ids that never run at once (one mutex group, one `run:` block), so packing and the shard's own receipt must use `concurrentHeavy(unit)` here, the same peak the refusal above is computed against -- using the raw sum would both refuse a bin for a unit that only ever holds one heavy process and
      // report a shard's `heavy` count higher than what can ever be resident.
      const peak = concurrentHeavy(unit);
      const cost = unitCost(unit, priced);
      let pick = -1;
      for (let i = 0; i < want; i += 1) {
        if (peak > 0 && binHeavy[i] > 0) continue;
        if (pick === -1 || (binCost[i] as number) < (binCost[pick] as number)) pick = i;
      }
      if (pick === -1) {
        return {
          error:
            `lane ${lane}: no shard can take ${unit.ids.join(', ')} without a second heavy gate. ` +
            'This is a planner bug, not a declaration problem; the heavy arithmetic above should ' +
            'have refused first.',
        };
      }
      (bins[pick] as Unit[]).push(unit);
      binCost[pick] = (binCost[pick] as number) + cost;
      binHeavy[pick] = (binHeavy[pick] as number) + peak;
    }

    const shardList: Shard[] = [];
    for (let i = 0; i < want; i += 1) {
      const held = bins[i] as Unit[];
      const ids: string[] = [];
      for (const unit of held.sort(
        (a, b) => (rank.get(a.ids[0] as string) ?? 0) - (rank.get(b.ids[0] as string) ?? 0)
      )) {
        const seq = orderUnit(unit.ids, byId, rank);
        if ('error' in seq) return { error: `lane ${lane}: ${seq.error}` };
        ids.push(...seq);
      }
      shardList.push({
        lane,
        index: i + 1,
        of: want,
        runsOn: cap.runsOn,
        timeoutMinutes: cap.timeoutMinutes,
        ids,
        // `binCost`, not a raw weight sum: identical to `weight` for every lane with no matching `durations` entries (every lane today), and the real packing currency once T3.2 populates `.ci/config/lane-durations.json` for a lane.
        weight: binCost[i] as number,
        slow: held.reduce((n, u) => n + u.slow, 0),
        heavy: binHeavy[i] as number,
      });
    }

    // THE ACCEPTANCE, RE-ASSERTED BY THE PLANNER ITSELF. These three cannot fire given the arithmetic above, and they are here anyway: the day the packer changes, the caller finds out from a refusal rather than from a lane that quietly stopped running eleven gates.
    const seen = new Set<string>();
    for (const shard of shardList) {
      if (shard.ids.length === 0) {
        return {
          error:
            `lane ${lane}: shard ${shard.index} of ${want} came out EMPTY. An empty shard is a ` +
            'runner that reports green having run nothing.',
        };
      }
      for (const id of shard.ids) {
        if (seen.has(id)) {
          return {
            error: `lane ${lane}: ${id} landed in more than one shard; shards must be disjoint.`,
          };
        }
        seen.add(id);
      }
    }
    if (seen.size !== entries.length) {
      const lost = entries.map((e) => e.id).filter((id) => !seen.has(id));
      return {
        error:
          `lane ${lane}: the shards cover ${seen.size} of ${entries.length} entries. ` +
          `Missing: ${lost.sort().join(', ')}. A gate in no shard runs nowhere.`,
      };
    }

    out.push({
      lane,
      entries: entries.length,
      units: unitList.length,
      merged: entries.length - unitList.length,
      shards: shardList,
    });
  }

  return { lanes: out };
}

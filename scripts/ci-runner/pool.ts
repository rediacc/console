/**
 * The scheduler: a worker pool over the gate manifest.
 *
 * CI parallelises the same work at JOB level, ten lanes grouped by what each
 * needs on disk, and gets isolation for free because every lane is a separate
 * runner. One machine with one tree does not get that, so the facts CI never
 * had to write down are declared per gate instead: `needs` for ordering, and
 * `mutex` / `reads` for shared mutable resources (the per-package dist trees,
 * private/renet/bin, the account vitest state, packages/www/dist, and the
 * working tree itself).
 *
 * Longest-first dequeuing is what makes the flattened battery pay off: the
 * achievable floor is the longest single gate, not the sum, so the critical
 * path has to start in the first wave.
 *
 * ---------------------------------------------------------------------------
 * THE ISOLATION CONTRACT (W2.4b). Defined here ONCE and implemented identically
 * by the other scheduler in this repo, `.ci/rediacc_ci/battery.py`.
 *
 *   A gate names the shared resources it touches. `mutex: [r]` is an EXCLUSIVE
 *   claim on r; `reads: [r]` is a SHARED claim on the same r. Two gates may
 *   overlap unless one of them holds r exclusively and the other holds r at
 *   all. Shared never conflicts with shared. One namespace, two claim strengths:
 *   a multiple-readers / single-writer lock, keyed on strings.
 *
 * WHY A SECOND CLAIM STRENGTH EXISTS AT ALL, since exclusive-only was enough
 * for the five build resources this file was written for. The hazard the
 * gate-test battery actually has is asymmetric: two of those tests WRITE into
 * the real tree (they drive code that hardcodes the real tree and offers no
 * fixture seam), while a dozen others RECURSIVELY ENUMERATE the same
 * directories. A file appearing or vanishing mid-`cp -r` is a hard error under
 * `set -euo pipefail`, so writer-versus-scanner must be excluded -- but
 * scanner-versus-scanner must NOT be, or twenty-one read-only tests serialise
 * for nothing. An exclusive-only mutex can express one of those or the other,
 * never both, which is precisely why the battery keeps a three-set
 * scheduler instead of declaring anything.
 *
 * WHAT THE TWO SCHEDULERS DID BEFORE THIS, and it is worth stating plainly
 * because they disagreed for months without anything noticing. The battery
 * carried the membership as two hand-maintained NAME LISTS inside the runner
 * (WRITER_TESTS, SCANNER_TESTS) and honoured them. The manifest carried nothing:
 * measured 2026-09-06 at commit ac817a647, all three real-tree writers --
 * gate-test:gate-paths-exist, gate-test:gate-anti-vacuity,
 * gate-test:generate-tag-inputs -- are registered with NO mutex, and zero of the
 * 147 qualityGateTest entries carry one. So `npm run ci` schedules exactly the
 * combination the battery's own header calls "a flake manufactured by the
 * runner", while the CI step that runs the same 147 tests is protected. The
 * isolation was real in one scheduler and absent in the other, and the only
 * thing keeping the difference invisible is that the two are rarely both hot.
 *
 * The resource names are PATH-SCOPED (`tree:<dir>`), so the declaration says
 * what a gate touches rather than which bucket someone put it in, and a new
 * gate declares itself instead of being added to a list in a runner. Two gates
 * hold the declarations to the code: check:ci-pool-writer-safety for gate
 * tests, and check:ci-gate-tree-writes for gates, where an exclusive `tree:`
 * claim must come with a `writesTree` reason (gate-spec.ts).
 * ---------------------------------------------------------------------------
 *
 * See agent/plans/PLAN-npm-ci-parallel-parity.md sections 3 and 4.2.
 */

import type { ExecOutcome } from './exec';
import type { GateSpec } from './manifest';

/**
 * `blocked` is a gate that COULD NOT RUN, as distinct from one that ran and
 * judged the code red. A missing toolchain is not evidence about the code, and
 * conflating the two is what makes a pre-push lane unusable: measured
 * 2026-08-27, ten of twelve reds on a normal developer tree were ambient, three
 * of them purely "this machine lacks ruff / workers-types".
 *
 * It is NOT a skip. A gate that opts into this must exit CANNOT_RUN
 * deliberately and say what is missing; the default for any other non-zero exit
 * is still `fail`. And it stays visible: the footer counts it, the receipt
 * records it, and the pre-push guard WARNS on it rather than staying quiet --
 * "a linter that cannot run is a gate that cannot fail" remains true, so this
 * makes that state loud rather than forgiving it.
 */
type GateStatus = 'ok' | 'fail' | 'blocked' | 'skipped';

/**
 * Exit code a gate uses to say "I could not run", borrowed from the POSIX
 * convention automake uses for a skipped test. Chosen because it cannot collide
 * with a real verdict: 1 is a finding, 2 is usage, 124 is a timeout, 127 is
 * not-found (which is a genuine breakage, not a considered "cannot run").
 */
// NOT exported: nothing outside this module imports it, and knip's --treat-config-hints-as-errors counts an unused export as a finding. The shell gates that exit 77 (check-python-lint.sh, shfmt.sh) cannot import a TypeScript constant anyway, so the value is duplicated there as a literal
// with this comment as its reference point.
const CANNOT_RUN = 77;

export interface GateResult {
  id: string;
  /** Mirrors GateSpec.gate: false nodes are prerequisites, not validations. */
  gate: boolean;
  status: GateStatus;
  ms: number;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  /** The exact command to re-run this gate by hand. */
  rerun: string;
  /** On a skip: which dependency killed it, or that --fail-fast stopped the run. */
  reason?: string;
  /** On a zero-exit gate the runner failed anyway; see exec.ts vacuityCheck. */
  vacuity?: string;
  /** CPU of the gate's reaped process tree (exec.ts RUSAGE_WRAPPER); run.ts may raise it from the /proc sampler. */
  cpuMs?: number;
  /** Peak summed RSS of the gate's tree from the /proc sampler capture, when one exists. */
  rssMb?: number;
  /** The sampler's CPU exceeded `times` by more than 20%: descendants escaped the reap, and cpuMs holds the larger value. */
  undercount?: boolean;
  /**
   * Epoch ms: when every `needs` was satisfied (the gate entered the ready queue), when it was launched, and when its process settled. Measurement only (PLAN-ci-quick-cpu-scheduling 2.3); nothing schedules on them.
   */
  readyAt?: number;
  startAt?: number;
  endAt?: number;
  /** The last admission check that held a ready gate back before it launched (see HoldReason). Absent when it launched on first sight. */
  blockedBy?: HoldReason;
}

/**
 * Which admission rule the pool runs (agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.2). `slots` is the rule the pool has always had: `jobs` slots, one per gate unless it declares `weight`, longest wall first. `cores` packs against a core budget from each gate's measured CPU, and is kept beside `slots` for A/B and rollback.
 */
export type Sched = 'slots' | 'cores';

/**
 * Why a ready gate was held back. `slot` and `heavy` are the slots rule's; `cpu`, `mem` and `count` are the core budget's three dimensions; `reservation` is a gate that would fit now but would delay the reserved start of a wider gate ahead of it (EASY backfill); `claim` is the isolation contract, the same in both.
 */
export type HoldReason = 'slot' | 'heavy' | 'claim' | 'cpu' | 'mem' | 'count' | 'reservation';

/** What the duration cache measured for one gate (run.ts DurationRecord, reduced). */
export interface GateCost {
  /** Median CPU ms over the recent passing runs. */
  cpuMs?: number;
  /** The least-contended recent wall ms: the floor of `recent`, since load only ever adds time. */
  wallMs?: number;
  /** The largest recent peak RSS, MB. */
  rssMb?: number;
}

/** The `cores` rule's budget. */
export interface CoreBudget {
  /** C: cores the pool may fill, availableParallelism() - 1 by default. */
  cores: number;
  /** Over-admission allowed on top of C, since d(g) is a median and gates idle between phases. */
  epsilon: number;
  /** K: concurrent gate processes, 2C by default, so a pool of I/O-bound gates cannot fork without bound. */
  maxProcs: number;
  /** M: MB of memory the pool may hold, 0.75 x MemAvailable at start by default. */
  memMb: number;
  /** EASY-backfill reservations; on unless a simulator control turns them off to show the starvation they prevent. */
  reserve?: boolean;
}

export interface PoolOptions {
  jobs: number;
  heavyLimit: number;
  failFast: boolean;
  /** Expected ms per id, for longest-first ordering. Missing ids fall back. */
  durations: Map<string, number>;
  exec: (spec: GateSpec) => Promise<ExecOutcome>;
  onStart?: (spec: GateSpec) => void;
  onFinish?: (result: GateResult) => void;
  /** Default `slots`. `cores` needs `budget`; `costs` feeds it, and a gate missing from it is scheduled on its hand-written `weight`. */
  sched?: Sched;
  budget?: CoreBudget;
  costs?: Map<string, GateCost>;
}

/** A gate as the admission step sees it: every number it budgets, already derived. */
export interface Candidate {
  id: string;
  /** Slots it takes under `slots` (effWeight). */
  slots: number;
  /** d(g) under `cores`. */
  cores: number;
  memMb: number;
  /** Predicted wall, for a reservation's start time. */
  estMs: number;
  /** Counts against heavyLimit: every `heavy` gate under `slots`, only an unmeasured one under `cores`. */
  heavy: boolean;
  mutex: readonly string[];
  reads: readonly string[];
}

export interface RunningGate {
  gate: Candidate;
  /** Predicted end, epoch ms (start + estMs). */
  endsAt: number;
}

export interface AdmitConfig {
  sched: Sched;
  jobs: number;
  heavyLimit: number;
  budget?: CoreBudget;
}

export interface Admission {
  /** In launch order. */
  launch: Candidate[];
  /** Every gate the pass held back, with the check that held it. A gate the idle branch then launched anyway still appears here, as it always has. */
  held: [string, HoldReason][];
  /** The EASY reservation this pass made, if any: which gate, and its predicted start. */
  reservation?: { id: string; at: number };
}

// Float sums of fractional cores must not turn an exact fit into a refusal.
const FIT_TOLERANCE = 1e-9;

/**
 * ONE ADMISSION PASS, pure, shared by runPool and scripts/ci-runner/sim.ts so the simulator tests the rule the pool runs rather than a copy of it. `ready` must already be in priority order; `running` includes nothing launched by this pass.
 *
 * `slots` is the pool's original loop moved here verbatim: slot budget, then heavyLimit, then claims, in that order, every gate in rank order.
 *
 * `cores` admits g when its claims pass, heavyLimit passes (unmeasured heavy gates only), sum(d) + d(g) <= C(1+epsilon), running < K, sum(m) + m(g) <= M, and no reservation is delayed. The first gate that fails a budget check reserves the moment enough running gates are predicted to end for it to fit; a later gate may then run only if it is predicted to finish before that moment or fits inside what the reserved gate leaves spare at it. Without the reservation a d-8 gate behind a stream of one-core gates never sees 8 free cores at once.
 *
 * Both rules end in the same progress guarantee: nothing running and nothing admitted means the head of the queue runs anyway, alone, whatever its size. A gate wider than the whole budget would otherwise hang the pool.
 */
export function admit(
  ready: readonly Candidate[],
  running: readonly RunningGate[],
  cfg: AdmitConfig,
  now: number
): Admission {
  const heldExclusive = new Set<string>();
  const heldShared = new Map<string, number>();
  const live: RunningGate[] = [];
  let slots = 0;
  let heavy = 0;
  let cores = 0;
  let mem = 0;
  const occupy = (r: RunningGate): void => {
    live.push(r);
    slots += r.gate.slots;
    if (r.gate.heavy) heavy += 1;
    cores += r.gate.cores;
    mem += r.gate.memMb;
    for (const res of r.gate.mutex) heldExclusive.add(res);
    for (const res of r.gate.reads) heldShared.set(res, (heldShared.get(res) ?? 0) + 1);
  };
  for (const r of running) occupy(r);

  // THE CONTRACT (header): an exclusive claim conflicts with any claim on the same resource; a shared claim conflicts only with an exclusive one.
  const blockedByClaim = (g: Candidate): boolean =>
    g.mutex.some((r) => heldExclusive.has(r) || (heldShared.get(r) ?? 0) > 0) ||
    g.reads.some((r) => heldExclusive.has(r));

  const launch: Candidate[] = [];
  const held: [string, HoldReason][] = [];
  const go = (g: Candidate): void => {
    occupy({ gate: g, endsAt: now + g.estMs });
    launch.push(g);
  };
  let reservation: Admission['reservation'];

  if (cfg.sched === 'slots') {
    for (const g of ready) {
      if (slots + g.slots > cfg.jobs) {
        held.push([g.id, 'slot']);
        continue;
      }
      if (g.heavy && heavy >= cfg.heavyLimit) {
        held.push([g.id, 'heavy']);
        continue;
      }
      if (blockedByClaim(g)) {
        held.push([g.id, 'claim']);
        continue;
      }
      go(g);
    }
  } else {
    const b = cfg.budget;
    if (b === undefined)
      throw new Error('ci-runner: internal error, --sched cores without a budget');
    const cap = b.cores * (1 + b.epsilon);
    // What the reserved gate leaves spare at its predicted start, in all three dimensions.
    let spare: { at: number; cores: number; mem: number; procs: number } | undefined;
    const reserve = (g: Candidate): void => {
      const ends = live
        .map((r) => ({ at: Math.max(r.endsAt, now), gate: r.gate }))
        .sort((x, y) => x.at - y.at);
      let freeCores = cap - cores;
      let freeMem = b.memMb - mem;
      let freeProcs = b.maxProcs - live.length;
      let at = now;
      const fits = (): boolean =>
        freeCores + FIT_TOLERANCE >= g.cores && freeMem >= g.memMb && freeProcs >= 1;
      // Release predicted ends in order until g fits. A gate wider than the budget never fits and reserves the moment the pool drains, which is where the progress guarantee admits it.
      for (const e of ends) {
        if (fits()) break;
        at = e.at;
        freeCores += e.gate.cores;
        freeMem += e.gate.memMb;
        freeProcs += 1;
      }
      spare = {
        at,
        cores: freeCores - g.cores,
        mem: freeMem - g.memMb,
        procs: freeProcs - 1,
      };
      reservation = { id: g.id, at };
    };

    for (const g of ready) {
      if (blockedByClaim(g)) {
        held.push([g.id, 'claim']);
        continue;
      }
      if (g.heavy && heavy >= cfg.heavyLimit) {
        held.push([g.id, 'heavy']);
        continue;
      }
      const over: HoldReason | undefined =
        cores + g.cores > cap + FIT_TOLERANCE
          ? 'cpu'
          : live.length + 1 > b.maxProcs
            ? 'count'
            : mem + g.memMb > b.memMb
              ? 'mem'
              : undefined;
      if (over !== undefined) {
        held.push([g.id, over]);
        if (spare === undefined && b.reserve !== false) reserve(g);
        continue;
      }
      if (spare !== undefined && now + g.estMs > spare.at) {
        // Runs past the reserved start, so it must fit inside what the reserved gate leaves spare there.
        if (g.cores > spare.cores + FIT_TOLERANCE || g.memMb > spare.mem || spare.procs < 1) {
          held.push([g.id, 'reservation']);
          continue;
        }
        spare.cores -= g.cores;
        spare.mem -= g.memMb;
        spare.procs -= 1;
      }
      go(g);
    }
  }

  if (running.length === 0 && launch.length === 0) {
    // Nothing is in flight and nothing was admissible: the budget is smaller than the head of the queue. Admit it anyway rather than spin. No claim can be the blocker here, since nothing holds one -- but the predicate is still consulted rather than assumed, because "cannot happen" is how a stall turns into a silent over-admission that violates the very exclusion this branch is
    // bypassing.
    const head = ready.find((g) => !blockedByClaim(g));
    if (head !== undefined) go(head);
  }
  return { launch, held, reservation };
}

/**
 * Derive every gate's Candidate and the priority order, for either rule. Shared with sim.ts for the same reason as admit().
 *
 * `slots`: longest expected wall first, as it always was; weight clamped to [1, jobs].
 *
 * `cores`: d(g) = clamp(median cpu / least-contended wall, 0.25, C) for a measured gate; `weight ?? 1` unclamped for an unmeasured one (a weight above C is still admitted, alone, by the progress guarantee). Memory is the largest measured peak RSS, else 4 GB for `heavy` and 0.5 GB otherwise. Priority is max(bottom level over `needs`, cpu), both in ms: with one-core gates and no edges it reduces to the slots rule's longest-first, and a wide gate like check:test-shared (33.6 cpu-s over 4.8 s) moves to the first wave instead of starting last.
 */
export function planAdmission(
  specs: readonly GateSpec[],
  opts: Pick<PoolOptions, 'jobs' | 'durations' | 'sched' | 'budget' | 'costs'>
): { byId: Map<string, Candidate>; rank: (a: GateSpec, b: GateSpec) => number } {
  const position = new Map(specs.map((spec, i) => [spec.id, i]));
  // A missing or corrupt duration cache must never fail the run, so an unknown gate is simply assumed cheap-ish and sorts late.
  const expected = (spec: GateSpec): number =>
    opts.durations.get(spec.id) ?? (spec.weight ?? 1) * 5000;
  // Clamped: a gate declaring more weight than the whole budget would never be admissible and would hang the pool at --jobs 1.
  const effWeight = (spec: GateSpec): number =>
    Math.min(Math.max(1, spec.weight ?? 1), Math.max(1, opts.jobs));
  const byPosition = (a: GateSpec, b: GateSpec): number =>
    (position.get(a.id) ?? 0) - (position.get(b.id) ?? 0);
  const byId = new Map<string, Candidate>();

  if ((opts.sched ?? 'slots') === 'slots') {
    for (const spec of specs) {
      byId.set(spec.id, {
        id: spec.id,
        slots: effWeight(spec),
        cores: effWeight(spec),
        memMb: 0,
        estMs: expected(spec),
        heavy: spec.heavy === true,
        mutex: spec.mutex ?? [],
        reads: sharedClaims(spec),
      });
    }
    return {
      byId,
      rank: (a, b) => expected(b) - expected(a) || byPosition(a, b),
    };
  }

  const c = Math.max(1, opts.budget?.cores ?? opts.jobs);
  const cpuMs = new Map<string, number>();
  for (const spec of specs) {
    const cost = opts.costs?.get(spec.id);
    const measured = cost?.cpuMs !== undefined && cost.wallMs !== undefined && cost.wallMs > 0;
    const d = measured
      ? Math.min(Math.max((cost.cpuMs ?? 0) / (cost.wallMs ?? 1), 0.25), c)
      : Math.max(0.25, spec.weight ?? 1);
    const estMs = opts.durations.get(spec.id) ?? cost?.wallMs ?? (spec.weight ?? 1) * 5000;
    cpuMs.set(spec.id, measured ? (cost.cpuMs ?? 0) : d * estMs);
    byId.set(spec.id, {
      id: spec.id,
      slots: effWeight(spec),
      cores: d,
      memMb: cost?.rssMb ?? (spec.heavy === true ? 4096 : 512),
      estMs,
      heavy: spec.heavy === true && !measured,
      mutex: spec.mutex ?? [],
      reads: sharedClaims(spec),
    });
  }

  // Bottom level: a gate's own predicted wall plus the longest chain of dependents behind it, within this pool's specs.
  const dependents = new Map<string, string[]>();
  for (const spec of specs) {
    for (const need of spec.needs ?? []) {
      if (!byId.has(need)) continue;
      dependents.set(need, [...(dependents.get(need) ?? []), spec.id]);
    }
  }
  const bottom = new Map<string, number>();
  const visiting = new Set<string>();
  const level = (id: string): number => {
    const hit = bottom.get(id);
    if (hit !== undefined) return hit;
    if (visiting.has(id)) throw new Error(`ci-runner: dependency cycle through ${id}`);
    visiting.add(id);
    let tail = 0;
    for (const dep of dependents.get(id) ?? []) tail = Math.max(tail, level(dep));
    visiting.delete(id);
    const own = (byId.get(id)?.estMs ?? 0) + tail;
    bottom.set(id, own);
    return own;
  };
  const priority = new Map(
    specs.map((spec) => [spec.id, Math.max(level(spec.id), cpuMs.get(spec.id) ?? 0)])
  );
  return {
    byId,
    rank: (a, b) => (priority.get(b.id) ?? 0) - (priority.get(a.id) ?? 0) || byPosition(a, b),
  };
}

function mustGet(byId: Map<string, GateSpec>, id: string): GateSpec {
  const spec = byId.get(id);
  if (spec === undefined) throw new Error(`ci-runner: internal error, unknown gate id ${id}`);
  return spec;
}

function indexById(all: readonly GateSpec[]): Map<string, GateSpec> {
  const byId = new Map<string, GateSpec>();
  for (const spec of all) {
    if (byId.has(spec.id)) throw new Error(`ci-runner: duplicate manifest id: ${spec.id}`);
    byId.set(spec.id, spec);
  }
  return byId;
}

/**
 * A cycle would deadlock the pool with no diagnostic, which is the worst
 * possible way for a manifest bug to present. Detect it over the WHOLE
 * manifest at graph-build time and print the path.
 */
function assertAcyclic(all: readonly GateSpec[], byId: Map<string, GateSpec>): void {
  const done = new Set<string>();
  const onStack = new Set<string>();
  const trail: string[] = [];

  const visit = (id: string): void => {
    if (done.has(id)) return;
    if (onStack.has(id)) {
      const from = trail.indexOf(id);
      const cycle = [...trail.slice(from), id].join(' -> ');
      throw new Error(`ci-runner: dependency cycle in the manifest: ${cycle}`);
    }
    onStack.add(id);
    trail.push(id);
    for (const need of byId.get(id)?.needs ?? []) visit(need);
    trail.pop();
    onStack.delete(id);
    done.add(id);
  };

  for (const spec of all) visit(spec.id);
}

/**
 * Validate the manifest and expand a selection into the set the pool will run:
 * the selected gates plus the transitive closure of their `needs`.
 *
 * The closure is what makes `gate: false` nodes work. build:packages and
 * build:www validate nothing, so they are never selected directly; they run
 * only because something that needs them was selected. Returned in manifest
 * order so the summary is stable across runs.
 */
export function buildGraph(all: readonly GateSpec[], selected: ReadonlySet<string>): GateSpec[] {
  const byId = indexById(all);

  for (const spec of all) {
    for (const need of spec.needs ?? []) {
      if (!byId.has(need)) {
        throw new Error(`ci-runner: ${spec.id} needs '${need}', which is not a manifest id`);
      }
    }
  }
  assertAcyclic(all, byId);

  const keep = new Set<string>();
  const add = (id: string): void => {
    if (keep.has(id)) return;
    keep.add(id);
    for (const need of mustGet(byId, id).needs ?? []) add(need);
  };
  for (const id of selected) {
    if (!byId.has(id)) throw new Error(`ci-runner: selection names unknown gate '${id}'`);
    add(id);
  }

  return all.filter((spec) => keep.has(spec.id));
}

/**
 * Shared claims, read structurally rather than off the type.
 *
 * `mutex` has been a declared `GateSpec` field since the pool was written;
 * `reads` is the other half of the isolation contract and its declaration lands
 * with the registry change that populates it (see the W2.4b proposal). Reading
 * it structurally means this scheduler already honours the field the day the
 * data arrives, and behaves exactly as it does today until then -- an absent
 * `reads` is an empty claim set, which is the same graph the pool has always
 * built. It is NOT a compatibility shim to keep around: once gate-spec.ts
 * declares `reads?: string[]`, this function collapses to `spec.reads ?? []`.
 */
function sharedClaims(spec: GateSpec): readonly string[] {
  const declared = (spec as GateSpec & { reads?: unknown }).reads;
  return Array.isArray(declared) ? declared.filter((r): r is string => typeof r === 'string') : [];
}

export async function runPool(
  specs: readonly GateSpec[],
  opts: PoolOptions
): Promise<GateResult[]> {
  const byId = indexById(specs);
  const results = new Map<string, GateResult>();
  const unstarted = new Set(specs.map((spec) => spec.id));
  const running = new Map<string, Promise<{ id: string; outcome: ExecOutcome; endAt: number }>>();
  // What admit() sees of each running gate. The claims live inside the candidates: admit() rebuilds the held sets from this list on every pass -- exclusive as a set, shared as a COUNT, because any number of readers may hold one and the last one out has to be the one that releases it. Rebuilding rather than incrementing is what makes a plain Set impossible to get wrong here.
  const inFlight = new Map<string, RunningGate>();
  // Timestamps and the last hold-back reason, recorded on the side so the admission logic reads exactly as it did before they existed.
  const readyAt = new Map<string, number>();
  const startAt = new Map<string, number>();
  const blockedBy = new Map<string, HoldReason>();
  let stopped = false;

  const sched = opts.sched ?? 'slots';
  const { byId: candidates, rank } = planAdmission(specs, opts);
  const candidate = (id: string): Candidate => {
    const c = candidates.get(id);
    if (c === undefined) throw new Error(`ci-runner: internal error, no candidate for ${id}`);
    return c;
  };
  const cfg: AdmitConfig = {
    sched,
    jobs: opts.jobs,
    heavyLimit: opts.heavyLimit,
    budget: opts.budget,
  };

  const record = (result: GateResult): void => {
    results.set(result.id, result);
    unstarted.delete(result.id);
    opts.onFinish?.(result);
  };

  const skip = (spec: GateSpec, reason: string): GateResult => ({
    id: spec.id,
    gate: spec.gate,
    status: 'skipped',
    ms: 0,
    exitCode: null,
    stdout: '',
    stderr: '',
    rerun: spec.run,
    reason,
  });

  const launch = (spec: GateSpec): void => {
    unstarted.delete(spec.id);
    const now = Date.now();
    const gate = candidate(spec.id);
    inFlight.set(spec.id, { gate, endsAt: now + gate.estMs });
    startAt.set(spec.id, now);
    opts.onStart?.(spec);
    running.set(
      spec.id,
      opts.exec(spec).then((outcome) => ({ id: spec.id, outcome, endAt: Date.now() }))
    );
  };

  while (unstarted.size > 0 || running.size > 0) {
    // A dependency that failed poisons its dependents transitively, so run the propagation to a fixpoint. Reporting them as skipped rather than passed is what keeps a broken prerequisite from reading as green.
    let changed = true;
    while (changed) {
      changed = false;
      for (const id of [...unstarted]) {
        const spec = mustGet(byId, id);
        const dead = (spec.needs ?? []).find((need) => {
          const r = results.get(need);
          return r !== undefined && r.status !== 'ok';
        });
        if (dead !== undefined) {
          record(skip(spec, `needs ${dead}`));
          changed = true;
        }
      }
    }

    if (stopped) {
      for (const id of [...unstarted]) record(skip(mustGet(byId, id), 'not run (--fail-fast)'));
    }

    const ready = [...unstarted]
      .map((id) => mustGet(byId, id))
      .filter((spec) => (spec.needs ?? []).every((need) => results.get(need)?.status === 'ok'))
      .sort(rank);

    const now = Date.now();
    for (const spec of ready) if (!readyAt.has(spec.id)) readyAt.set(spec.id, now);

    const pass = admit(
      ready.map((spec) => candidate(spec.id)),
      [...inFlight.values()],
      cfg,
      now
    );
    for (const [id, why] of pass.held) blockedBy.set(id, why);
    for (const gate of pass.launch) launch(mustGet(byId, gate.id));

    if (running.size === 0 && unstarted.size > 0) {
      // admit() already ran the progress guarantee, so work outstanding with nothing in flight means no ready gate was admissible even alone.
      throw new Error('ci-runner: internal error, pool stalled with work outstanding');
    }

    if (running.size === 0) continue;

    const { id, outcome, endAt } = await Promise.race(running.values());
    const spec = mustGet(byId, id);
    running.delete(id);
    inFlight.delete(id);

    // A vacuity finding always means `fail`, even at CANNOT_RUN: a gate that claims it cannot run AND trips the anti-vacuity oracle is not a machine missing a tool, it is a gate lying about what it did.
    const cannotRun = outcome.code === CANNOT_RUN && outcome.vacuity === undefined;
    const failed = !cannotRun && (outcome.code !== 0 || outcome.vacuity !== undefined);
    record({
      id,
      gate: spec.gate,
      status: cannotRun ? 'blocked' : failed ? 'fail' : 'ok',
      ms: outcome.ms,
      exitCode: outcome.code,
      stdout: outcome.stdout,
      stderr: outcome.stderr,
      rerun: spec.run,
      vacuity: outcome.vacuity,
      cpuMs: outcome.cpuMs,
      readyAt: readyAt.get(id),
      startAt: startAt.get(id),
      endAt,
      blockedBy: blockedBy.get(id),
    });
    if (failed && opts.failFast) stopped = true;
  }

  // Manifest order, not completion order: the exit code and the summary must be identical across runs even though the scheduling never is.
  return specs.map((spec) => {
    const result = results.get(spec.id);
    if (result === undefined)
      throw new Error(`ci-runner: internal error, no result for ${spec.id}`);
    return result;
  });
}

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

import type { ExecOutcome, Grant } from './exec';
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
  /** The cores the pool granted this gate at launch, exported to its process as CI_RUNNER_CORES (exec.ts). Absent on a gate that never launched. */
  grantedCores?: number;
  /** The gate declared an elastic `cores` range, so `grantedCores` was sized by the area rule rather than rounded from a measured width. */
  elastic?: boolean;
  /** Set only when the gate launched with more cores than the lease tokens it held: its bounded `lease` hold expired (or it was wider than the whole budget), so it ran past another run's tokens rather than wait without end. The footer names every one. */
  overLease?: { granted: number; held: number };
  /** The gate was killed at its kill timer (gate-timeout.ts); the limit in ms. Always with status `fail` and exitCode null. */
  timedOutMs?: number;
}

/**
 * Which admission rule the pool runs (agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.2). `slots` is the rule the pool has always had: `jobs` slots, one per gate (an elastic gate takes its grant's worth), longest wall first. `cores` packs against a core budget from each gate's measured CPU, and is kept beside `slots` for A/B and rollback.
 */
export type Sched = 'slots' | 'cores';

/**
 * Why a ready gate was held back. `slot` and `heavy` are the slots rule's; `cpu`, `mem` and `count` are the core budget's three dimensions; `reservation` is a gate that would fit now but would delay the reserved start of a wider gate ahead of it (EASY backfill); `claim` is the isolation contract, the same in both; `lease` is the machine-wide core lease (lease-client.ts) holding fewer free cores than the gate needs, so another run on this machine has them.
 */
export type HoldReason =
  | 'slot'
  | 'heavy'
  | 'claim'
  | 'cpu'
  | 'mem'
  | 'count'
  | 'reservation'
  | 'lease';

/** What the duration cache measured for one gate (run.ts DurationRecord, reduced). */
export interface GateCost {
  /** Median CPU ms over the recent passing runs. */
  cpuMs?: number;
  /** The least-contended recent wall ms: the floor of `recent`, since load only ever adds time. */
  wallMs?: number;
  /** The largest recent peak RSS, MB. */
  rssMb?: number;
  /** An elastic gate's median cpu / wall / grant: the share of each granted core it keeps busy. Stored per core so one run at 20 workers does not teach the scheduler the gate is 20 wide. */
  perCore?: number;
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
  /** The critical-path floor on elastic grants (`needWidth`); on unless a simulator control turns it off to show the one-wide critical gate it prevents. */
  floor?: boolean;
}

export interface PoolOptions {
  jobs: number;
  heavyLimit: number;
  failFast: boolean;
  /** Expected ms per id, for longest-first ordering. Missing ids fall back. */
  durations: Map<string, number>;
  /** Spawn one gate with the grant the pool sized for it (exec.ts `execGate`). */
  exec: (spec: GateSpec, grant: Grant) => Promise<ExecOutcome>;
  onStart?: (spec: GateSpec) => void;
  onFinish?: (result: GateResult) => void;
  /** Default `slots`. `cores` needs `budget`; `costs` feeds it, and a gate missing from it is budgeted at one core. */
  sched?: Sched;
  budget?: CoreBudget;
  costs?: Map<string, GateCost>;
  /** The machine-wide core lease (lease-client.ts). Absent means the pool owns the whole budget, the same as a lease that degraded to the whole machine. */
  lease?: PoolLease;
  /** How often a pool with a gate held by the lease re-reads it, ms (default LEASE_POLL_MS). The selftest shortens it. */
  leasePollMs?: number;
}

/** What the lease reports before a pass. Every field is Infinity when nothing is leased. */
export interface LeaseView {
  /** Cores the pool may still start on beyond `inUse`: the broker's free tokens plus the slack of tokens this run already holds. */
  free: number;
  /** This run's fair share of the machine, ceil(total / live runs), live runs counting this one. */
  share: number;
  /** Tokens in the machine-wide pool. */
  total: number;
}

/**
 * WHY A WIDE GRANT WAITS 2 s AFTER THE RUN OPENS (B11, agent/plans/PLAN-prepush-full-cpu.md part 4). A run's share counts only the runs registered when it reads the lease, and two pre-pushes started together register a few hundred ms apart: the first would read itself alone and take every token. Two seconds covers a broker's spawn and handshake on a loaded machine, and costs a lone run of a 900 s pytest two seconds.
 */
export const SETTLE_MS = 2000;

/** How often a pool with a lease-held gate re-reads the lease, since another run's release raises no event here. One second keeps a broker round trip per second at most, against gates that run minutes. */
export const LEASE_POLL_MS = 1000;

/**
 * What runPool needs of the machine-wide core lease, implemented by lease-client.ts. Kept as an interface here so the pool, the simulator and the selftest never spawn a broker.
 */
export interface PoolLease {
  /** True when the grants are backed by a lease (a broker, or one this process inherited), so a child must not lease the same cores again (CI_CORE_LEASE_HELD). */
  readonly held: boolean;
  /** When the run registered with the lease, epoch ms, for the settle (SETTLE_MS). Absent when nothing is leased, which never settles. */
  readonly openedAt?: number;
  /** The lease's free cores, this run's share and the pool's total (LeaseView); every field Infinity when nothing is leased. */
  available(inUse: number): Promise<LeaseView>;
  /** Hold exactly ceil(cores) tokens, acquiring or releasing the difference; returns the tokens held afterwards (Infinity when nothing is leased). A short acquire is not an error: the caller reads the count. */
  reconcile(cores: number): Promise<number>;
}

/** An elastic declaration as admit() sees it: `max` resolved (`'all'` is Infinity), and what it knows of the gate's work. */
interface ElasticPlan {
  min: number;
  max: number;
  /** Predicted CPU work in core-ms, roughly the same at any width. */
  workMs: number;
  /** Share of each granted core the gate keeps busy (GateCost.perCore), 1 when unmeasured. */
  perCore: number;
  /** True when workMs is measured; false means the wall is unknown at any width, and the gate's estMs is used as is. */
  measured: boolean;
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
  /** Predicted CPU in core-ms, for the area term of every elastic grant (`elasticGrant`). */
  cpuMs: number;
  /** Set on a gate declaring `cores: {min, max}`; its `cores`, `slots` and `estMs` are then decided at admission. */
  elastic?: ElasticPlan;
  /** Set by admit() on every launched gate: the cores exported to its process. */
  grant?: number;
  /** Set by admit() on a gate it launched past the lease: its bounded `lease` hold expired, or it is wider than the whole budget and the pool is empty. Only such a gate may start on more cores than the tokens it got (fitToLease). */
  pastLease?: boolean;
  /** Under `cores`: the core-ms of budget the gate occupies at any width, work / perCore for a measured elastic gate and cpuMs otherwise. The horizon's area term (`horizonMs`). */
  areaMs?: number;
  /** Under `cores`: its predicted wall at the widest grant it can get, min(max, C) for a measured elastic gate and estMs otherwise. The irreducible part of any chain through it. */
  minWallMs?: number;
  /** Under `cores`: the longest chain of `needs` dependents behind it, by their minWallMs. */
  tailMs?: number;
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
  /** Cores the machine-wide lease can still give this pool (PoolLease.available, read before the pass). Absent means unbounded. Honoured by `cores` only; `slots` is the rollback rule and keeps its fixed width. */
  leaseFree?: number;
  /** Every gate not yet launched, ready or waiting on `needs`: the area term's backlog (their summed cpuMs) and the horizon the critical-path floor sizes against (`horizonMs`). Absent means an empty backlog and no floor. */
  pending?: readonly Candidate[];
  /** This run's share of the lease, ceil(total / live runs) (LeaseView.share). Caps every elastic grant and the area rule's C; fixed-width gates are not capped, so a run whose neighbour leaves cores idle can still fill them. Absent means unbounded. */
  leaseShare?: number;
  /** The lease's token total, for the settle's ceil(T / 2). */
  leaseTotal?: number;
  /** Epoch ms before which no elastic grant above ceil(leaseTotal / 2) is made (SETTLE_MS after the run registered). Absent means no settle. */
  settleUntil?: number;
  /** Epoch ms each gate was first held with `lease`, the start of its bounded hold. A gate absent here starts its bound now. */
  leaseHeldSince?: ReadonlyMap<string, number>;
}

export interface Admission {
  /** In launch order. */
  launch: Candidate[];
  /** Every gate the pass held back, with the check that held it. A gate the idle branch then launched anyway still appears here, as it always has. */
  held: [string, HoldReason][];
  /** The EASY reservation this pass made, if any: which gate, and its predicted start. */
  reservation?: { id: string; at: number };
  /** The earliest moment a timed hold (a bounded `lease` hold, or the settle) ends; the pool re-reads the lease by then even when nothing of its own ends. */
  wakeAt?: number;
}

// Float sums of fractional cores must not turn an exact fit into a refusal.
const FIT_TOLERANCE = 1e-9;

/**
 * THE AREA RULE (agent/plans/PLAN-prepush-full-cpu.md part 1): the widest grant k an elastic gate may take while leaving the rest of the pass the cores it needs. The rest needs `other` core-ms (every other gate still unstarted or running), spread over the elastic gate's predicted wall at k; so k <= C - other / wall(k).
 *
 * With a measured gate, wall(k) = work / (perCore x k), which makes the bound linear in k: k = floor(C / (1 + other x perCore / work)). An unmeasured gate has no wall model at any width, so its planning wall stands in: k = floor(C - other / estMs). Either can fall below 1, and the caller clamps to the declared `min`.
 *
 * Worked against the plan's numbers: C 23, a pytest of about 7,866 cpu-s at perCore 1 beside 818 cpu-s of fast gates gives floor(23 / 1.104) = 20, so pytest starts near 20 workers and the fast gates fill the rest.
 */
function areaGrant(el: ElasticPlan, estMs: number, c: number, otherCpuMs: number): number {
  const raw =
    el.measured && el.workMs > 0
      ? c / (1 + (Math.max(0, otherCpuMs) * el.perCore) / el.workMs)
      : c - Math.max(0, otherCpuMs) / Math.max(1, estMs);
  return Math.floor(raw + FIT_TOLERANCE);
}

/** An elastic gate's predicted wall at a grant of k: the work model when measured, else its planning wall unchanged. */
function elasticWall(el: ElasticPlan, estMs: number, k: number): number {
  return el.measured && el.workMs > 0 ? el.workMs / (el.perCore * Math.max(1, k)) : estMs;
}

/**
 * How long a gate the lease is short for may wait before it runs past the lease anyway: its wall at its fair share, work / (perCore x share) for a measured elastic gate, else its planning wall. A run that waited that long has lost no more than it would have by sharing from the start, and an unbounded wait would turn a neighbour that never releases into a hang.
 */
function fairWall(g: Candidate, share: number): number {
  const el = g.elastic;
  return el?.measured === true && el.workMs > 0
    ? el.workMs / (el.perCore * Math.max(1, share))
    : g.estMs;
}

/**
 * The grant an elastic candidate takes now: the area rule clamped to [min, min(max, free)], or undefined when fewer than `min` cores are free (the caller holds it and reserves its start). `free` is already the smaller of the core budget's room and the lease's.
 */
function elasticGrant(
  g: Candidate,
  c: number,
  otherCpuMs: number,
  free: number,
  need?: number
): number | undefined {
  const el = g.elastic;
  if (el === undefined) return undefined;
  const ceiling = Math.min(el.max, Math.floor(free + FIT_TOLERANCE));
  if (ceiling < el.min) return undefined;
  return Math.max(
    el.min,
    Math.min(Math.max(areaGrant(el, g.estMs, c, otherCpuMs), need ?? 0), ceiling)
  );
}

/**
 * How far past the horizon a gate may run before the floor widens it. The horizon is a lower bound the pool never reaches exactly (integer widths, median costs, gates idling between phases), so a gate predicted within 10% of it is not what decides the makespan; without the slack the floor's ceil() overshoots the area rule on every pass, taking the last core a fixed-width gate needed (C 8, a 40 cpu-s gate beside four 1 s gates: 8 cores and a 6 s makespan against the area rule's 7 and 5.7 s).
 */
const FLOOR_SLACK = 0.1;

/**
 * The per-core share below which a gate's wall model is not trusted: work / (perCore x k) assumes the gate gets faster with every core it is granted, and a gate that kept less than half of each granted core busy has shown it does not. check:types:incremental's one sample, 0.07 at a wide grant, models a 558 s wall at three cores for a gate measured at 8-41 s. Such a gate is planned at its measured wall and gets no floor, so the floor never widens a gate more cores cannot speed up.
 */
const SCALES_PER_CORE = 0.5;

/** True when an elastic plan's wall model (elasticWall) can be trusted for planning: measured work and a per-core share of at least SCALES_PER_CORE. */
function scales(el: ElasticPlan | undefined): el is ElasticPlan {
  return el?.measured === true && el.workMs > 0 && el.perCore >= SCALES_PER_CORE;
}

/**
 * THE HORIZON (agent/plans/PLAN-prepush-full-cpu.md, the 2026-10-06 tail fix): a lower bound on when the work still outstanding can finish on `c` cores, the larger of
 *
 *   area   (sum of every pending gate's areaMs + every running gate's cores x predicted time left) / c, and
 *   chain  the longest of: a pending gate's minWallMs + tailMs, a running gate's time left + tailMs, and, per EXCLUSIVE resource, the minWallMs of every pending holder plus the time left of the running one, since gates sharing a `mutex` run one after another.
 *
 * The exclusive-resource term is the one the 2026-10-06 run proved: check:ci-account-server, check:ci-test-account-web and check:ci-account-scope-audit share `mutex: ['account-vitest']`, about 1,160 core-s between them, and ran one after another at one core each for 924 s of a 979 s run while every other gate had finished by 460 s. Neither the area rule nor the `needs` bottom level could see that chain.
 */
function horizonMs(
  pending: readonly Candidate[],
  running: readonly RunningGate[],
  now: number,
  c: number
): number {
  let area = 0;
  let chain = 0;
  const serial = new Map<string, number>();
  const onResources = (mutex: readonly string[], ms: number): void => {
    for (const r of mutex) serial.set(r, (serial.get(r) ?? 0) + ms);
  };
  for (const g of pending) {
    const wall = g.minWallMs ?? g.estMs;
    area += g.areaMs ?? g.cpuMs;
    chain = Math.max(chain, wall + (g.tailMs ?? 0));
    onResources(g.mutex, wall);
  }
  for (const r of running) {
    const left = Math.max(0, r.endsAt - now);
    area += r.gate.cores * left;
    chain = Math.max(chain, left + (r.gate.tailMs ?? 0));
    onResources(r.gate.mutex, left);
  }
  for (const ms of serial.values()) chain = Math.max(chain, ms);
  return Math.max(area / Math.max(1, c), chain);
}

/**
 * THE CRITICAL-PATH FLOOR: the fewest cores that bring a measured elastic gate, and the gates it must run in series with, inside the horizon. The area rule alone is a proportional share, k = C x area(g) / area(everything), and floors to one core for every mid-size gate beside a large backlog; a gate the rest of the run waits on must not be one of them.
 *
 *   need = ceil(A / (H x (1 + FLOOR_SLACK) - F - tail)), clamped to [min, min(max, C)]
 *
 * A is the areaMs of this gate plus every pending measured elastic gate sharing one of its exclusive resources (they run one after another, and each takes this same width when its turn comes); F is the wall of the fixed-width (or unmeasured) gates in that group plus the time left of the one running; tail is its `needs` chain. A gate with no exclusive resource and no tail reduces to ceil(area(g) / H'), the width that fits it under the horizon. An unmeasured gate has no wall model, so it gets no floor (undefined), and neither does a gate the slots rule sizes.
 */
function needWidth(
  g: Candidate,
  pending: readonly Candidate[],
  running: readonly RunningGate[],
  now: number,
  horizon: number,
  c: number
): number | undefined {
  const el = g.elastic;
  if (!scales(el)) return undefined;
  const widest = Math.max(el.min, Math.min(el.max, Math.floor(c + FIT_TOLERANCE)));
  let area = el.workMs / el.perCore;
  let fixed = 0;
  if (g.mutex.length > 0) {
    const shares = (o: Candidate): boolean => o.mutex.some((r) => g.mutex.includes(r));
    for (const o of pending) {
      if (o.id === g.id || !shares(o)) continue;
      const oel = o.elastic;
      if (scales(oel)) area += oel.workMs / oel.perCore;
      else fixed += o.estMs;
    }
    for (const r of running) if (shares(r.gate)) fixed += Math.max(0, r.endsAt - now);
  }
  const room = horizon * (1 + FLOOR_SLACK) - fixed - (g.tailMs ?? 0);
  if (room <= 0) return widest;
  return Math.max(el.min, Math.min(widest, Math.ceil(area / room - FIT_TOLERANCE)));
}

/**
 * Fit an admitted gate to the tokens its launch actually got (`got`, from PoolLease.reconcile less what the running gates use). A gate that got its width runs as admitted; an elastic one short of it narrows to what it got when that still meets its `min`. Otherwise it is held (undefined) -- unless admit() launched it past the lease (`pastLease`), and then it runs at max(min, got) with the excess recorded, the one way a grant exceeds the tokens held. Shared with sim.ts so the simulator launches the way the pool does.
 */
export function fitToLease(
  gate: Candidate,
  got: number
): { gate: Candidate; over?: { granted: number; held: number } } | undefined {
  if (got + FIT_TOLERANCE >= gate.cores) return { gate };
  const el = gate.elastic;
  const k = Math.floor(got + FIT_TOLERANCE);
  if (el !== undefined && k >= el.min) return { gate: sizedAt(gate, k) };
  if (gate.pastLease !== true) return undefined;
  const fitted = el !== undefined ? sizedAt(gate, Math.max(el.min, k)) : gate;
  return {
    gate: fitted,
    over: {
      granted: fitted.grant ?? Math.max(1, Math.round(fitted.cores)),
      held: Math.max(0, Math.round(got * 100) / 100),
    },
  };
}

/** The candidate an elastic gate becomes at a grant of k: k cores and k slots budgeted, its wall re-predicted at k. */
function sizedAt(g: Candidate, k: number): Candidate {
  const el = g.elastic;
  if (el === undefined) return g;
  return { ...g, cores: k, slots: k, estMs: elasticWall(el, g.estMs, k), grant: k };
}

/**
 * ONE ADMISSION PASS, pure, shared by runPool and scripts/ci-runner/sim.ts so the simulator tests the rule the pool runs rather than a copy of it. `ready` must already be in priority order; `running` includes nothing launched by this pass.
 *
 * `slots` is the pool's original loop moved here verbatim: slot budget, then heavyLimit, then claims, in that order, every gate in rank order.
 *
 * `cores` admits g when its claims pass, heavyLimit passes (unmeasured heavy gates only), sum(d) + d(g) <= C(1+epsilon), running < K, sum(m) + m(g) <= M, and no reservation is delayed. The first gate that fails a budget check reserves the moment enough running gates are predicted to end for it to fit; a later gate may then run only if it is predicted to finish before that moment or fits inside what the reserved gate leaves spare at it. Without the reservation a d-8 gate behind a stream of one-core gates never sees 8 free cores at once.
 *
 * Both rules end in the same progress guarantee: nothing running and nothing admitted means the head of the queue runs anyway, alone, whatever its size. A gate wider than the whole budget would otherwise hang the pool.
 *
 * ELASTIC GATES (a declared `cores: {min, max}`) are sized here, not before the run: `elasticGrant` applies the area rule against what is free at this moment, the granted candidate is what every later check and the running set budget, and `grant` on each launched candidate is the number exported to the gate's process. Under `cores` the lease (`leaseFree`) is a fourth dimension: a gate wider than what the machine-wide lease can still give is held with `lease`, and an elastic gate reserves its start at its `min`. On an empty pool an elastic head takes max(min, what is free).
 *
 * THE SHARE (B11, agent/plans/PLAN-prepush-full-cpu.md part 4). Counting free tokens alone is first-come-takes-all: two runs started a second apart measured 23 cores against one. So an elastic grant is capped at `leaseShare`, ceil(T / live runs), and the area rule splits that share rather than the whole budget; fixed-width gates take what is free, so a neighbour's idle cores still get used. An elastic gate the lease would cut below min(its own grant, ceil(share / 2)) is held with `lease` for at most its fair wall (fairWall) and then runs at max(min, what is free), past the lease if it must. The progress guarantee never bypasses such a hold before its bound, and before `settleUntil` no elastic grant exceeds ceil(T / 2), so two runs started together both register before either takes a wide grant. `wakeAt` tells the pool when the earliest of these holds ends.
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
  let leaseLeft = cfg.leaseFree ?? Number.POSITIVE_INFINITY;
  const share = cfg.leaseShare ?? Number.POSITIVE_INFINITY;
  // Timed holds: gate id -> the moment its hold ends. The progress guarantee skips these, and the earliest is `wakeAt`.
  const timed = new Map<string, number>();
  const leaseSince = (id: string): number => cfg.leaseHeldSince?.get(id) ?? now;
  const go = (g: Candidate): void => {
    // A gate with no elastic range is told its budgeted width, rounded, never less than one core: a child tool sized by granted_cores() then sees the share the pool budgeted it.
    const launched = g.grant !== undefined ? g : { ...g, grant: Math.max(1, Math.round(g.cores)) };
    occupy({ gate: launched, endsAt: now + launched.estMs });
    leaseLeft -= launched.cores;
    launch.push(launched);
  };
  let reservation: Admission['reservation'];
  // The area term's "everyone else": the backlog (which still counts every gate this pass launches, since they were unstarted when it was summed) less the candidate itself, plus what the gates already running are predicted to burn before they end.
  let runningLeftMs = 0;
  for (const r of running) runningLeftMs += r.gate.cores * Math.max(0, r.endsAt - now);
  const pending = cfg.pending ?? [];
  let backlogCpuMs = 0;
  for (const g of pending) backlogCpuMs += g.cpuMs;
  const otherCpu = (g: Candidate): number => Math.max(0, backlogCpuMs - g.cpuMs) + runningLeftMs;
  // The floor's C is the area rule's: this run's share of the lease, never the whole machine, so two runs split it the way B11 does. One horizon per pass, from the state the pass started in.
  const floorC = Math.min(cfg.budget?.cores ?? cfg.jobs, share);
  const horizon =
    cfg.sched === 'cores' && cfg.budget?.floor !== false && pending.length > 0
      ? horizonMs(pending, running, now, floorC)
      : undefined;
  const needOf = (g: Candidate): number | undefined =>
    horizon === undefined ? undefined : needWidth(g, pending, running, now, horizon, floorC);
  // WHETHER ANOTHER RUN HOLDS LEASE TOKENS: total - free - this run's own in use (free already counts the slack of tokens this run holds). Without one, a lease short of a gate's width is this run's own gates holding the tokens, which is the core budget's business, not a neighbour's: before 2026-10-06 the bounded B11 hold fired on it, and a lone run's pytest waited 209 s for
  // tokens its own one-core gates held (the budget's 10% epsilon admits 26.4 cores against 24 tokens, so the lease always reads short of what the budget allows).
  const neighbour =
    cfg.leaseFree !== undefined &&
    cfg.leaseTotal !== undefined &&
    cfg.leaseTotal - cfg.leaseFree - cores >= 1 - FIT_TOLERANCE;

  if (cfg.sched === 'slots') {
    for (const g0 of ready) {
      let g = g0;
      if (g0.elastic !== undefined) {
        const k = elasticGrant(g0, cfg.jobs, otherCpu(g0), cfg.jobs - slots);
        if (k === undefined) {
          held.push([g0.id, 'slot']);
          continue;
        }
        g = sizedAt(g0, k);
      }
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
    // A run can never hold more lease tokens than the lease has, so under a lease the epsilon stops at its total: before 2026-10-06 the budget admitted 26.4 cores against 24 tokens, and every pass read the lease as short of what the budget allowed.
    const budgetCap = b.cores * (1 + b.epsilon);
    const cap = Math.min(budgetCap, cfg.leaseTotal ?? Number.POSITIVE_INFINITY);
    // What the reserved gate leaves spare at its predicted start, in all three dimensions.
    let spare: { at: number; cores: number; mem: number; procs: number } | undefined;
    // When g would fit, releasing the running gates' predicted ends in order, and what would be free then. Pure, so the floor can price a wait before deciding to take one.
    const whenFits = (g: Candidate): { at: number; cores: number; mem: number; procs: number } => {
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
      return { at, cores: freeCores, mem: freeMem, procs: freeProcs };
    };
    const reserve = (g: Candidate): void => {
      const f = whenFits(g);
      spare = {
        at: f.at,
        cores: f.cores - g.cores,
        mem: f.mem - g.memMb,
        procs: f.procs - 1,
      };
      reservation = { id: g.id, at: f.at };
    };

    for (const g0 of ready) {
      if (blockedByClaim(g0)) {
        held.push([g0.id, 'claim']);
        continue;
      }
      if (g0.heavy && heavy >= cfg.heavyLimit) {
        held.push([g0.id, 'heavy']);
        continue;
      }
      let g = g0;
      if (g0.elastic !== undefined) {
        const el = g0.elastic;
        // The area rule splits this run's share, not the whole budget.
        const c = floorC;
        const other = otherCpu(g0);
        const need = needOf(g0);
        // What the run's own budget and share allow. With no neighbour on the lease, its tokens are this run's own budget too (see `neighbour`).
        const budgetRoom = Math.min(cap - cores, share);
        const ownRoom = neighbour ? budgetRoom : Math.min(budgetRoom, leaseLeft);
        // Named for what binds: the lease (its free tokens, or its total under the budget's epsilon) or the core budget itself.
        const short: HoldReason =
          ownRoom + FIT_TOLERANCE < Math.min(budgetCap - cores, share) ? 'lease' : 'cpu';
        const own = elasticGrant(g0, c, other, ownRoom, need);
        if (own === undefined) {
          held.push([g0.id, short]);
          if (spare === undefined && b.reserve !== false)
            reserve(sizedAt(g0, Math.max(el.min, Math.min(need ?? el.min, Math.floor(c)))));
          continue;
        }
        if (need !== undefined && own < need) {
          // THE FLOOR WAITS ONLY WHEN WAITING ENDS SOONER. Started now the gate runs at `own`; held, it starts at its reserved moment at `need`. Whichever predicted end is earlier wins, so a critical gate is never parked behind a long one-core gate to save a core.
          const wide = sizedAt(g0, need);
          const narrow = sizedAt(g0, own);
          if (b.reserve !== false && whenFits(wide).at + wide.estMs < now + narrow.estMs) {
            held.push([g0.id, short]);
            if (spare === undefined) reserve(wide);
            continue;
          }
        }
        // Only a neighbour's tokens can make the lease shorter than `own` here; without one, k is own.
        const k = neighbour
          ? elasticGrant(g0, c, other, Math.min(budgetRoom, leaseLeft), need)
          : own;
        if ((k ?? 0) < Math.min(own, Math.ceil(share / 2))) {
          // Another run holds the tokens. Waiting for them beats starting at `min` (B11: one token against 23, a 6x wall), but only up to the fair wall.
          const until = leaseSince(g0.id) + fairWall(g0, c);
          if (now < until) {
            held.push([g0.id, 'lease']);
            timed.set(g0.id, until);
            if (spare === undefined && b.reserve !== false) reserve(sizedAt(g0, el.min));
            continue;
          }
          g = { ...sizedAt(g0, k ?? el.min), pastLease: true };
        } else {
          const width = k ?? el.min;
          if (
            cfg.settleUntil !== undefined &&
            now < cfg.settleUntil &&
            width > Math.ceil((cfg.leaseTotal ?? Number.POSITIVE_INFINITY) / 2)
          ) {
            // The settle (SETTLE_MS): a run that may not yet see its neighbour does not take more than half the machine. The reservation is at the width it is waiting to take, not its `min`: reserved at `min`, the rest of the first wave took every other core inside the settle's 2 s, and the widest gate of the run started late or narrow.
            held.push([g0.id, 'lease']);
            timed.set(g0.id, cfg.settleUntil);
            if (spare === undefined && b.reserve !== false) reserve(sizedAt(g0, width));
            continue;
          }
          g = sizedAt(g0, width);
        }
      }
      const over: HoldReason | undefined =
        cores + g.cores > cap + FIT_TOLERANCE
          ? 'cpu'
          : g.cores > leaseLeft + FIT_TOLERANCE && g.pastLease !== true
            ? 'lease'
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
        // Runs past the reserved start, so it must fit inside what the reserved gate leaves spare there. An elastic gate first narrows to what is spare, when that still meets its `min`.
        const narrow = Math.floor(spare.cores + FIT_TOLERANCE);
        if (
          g0.elastic !== undefined &&
          g.cores > spare.cores + FIT_TOLERANCE &&
          narrow >= g0.elastic.min
        )
          g = sizedAt(g0, narrow);
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
    // A timed hold is not a stall: it ends by itself, and the pool re-reads the lease by then. Forcing it here is exactly the B11 defect, a gate started on one token beside a neighbour holding 23.
    const head = ready.find((g) => !blockedByClaim(g) && !timed.has(g.id));
    const leaseHeld =
      head !== undefined && held.some(([id, why]) => id === head.id && why === 'lease');
    // A fixed-width head the lease holds waits out its own planning wall the same way before it runs past the lease.
    const until = head !== undefined && leaseHeld ? leaseSince(head.id) + head.estMs : now;
    if (head !== undefined && now < until) timed.set(head.id, until);
    else if (head?.elastic !== undefined) {
      const c = Math.min(
        cfg.sched === 'slots' ? cfg.jobs : (cfg.budget?.cores ?? cfg.jobs),
        cfg.sched === 'slots' ? Number.POSITIVE_INFINITY : share
      );
      const room =
        cfg.sched === 'slots'
          ? cfg.jobs
          : Math.min(
              c * (1 + (cfg.budget?.epsilon ?? 0)),
              cfg.leaseFree ?? Number.POSITIVE_INFINITY
            );
      const el = head.elastic;
      go({
        ...sizedAt(
          head,
          Math.max(
            el.min,
            Math.min(
              Math.max(areaGrant(el, head.estMs, c, otherCpu(head)), needOf(head) ?? 0),
              el.max,
              Math.floor(room + FIT_TOLERANCE)
            )
          )
        ),
        pastLease: true,
      });
    } else if (head !== undefined) go({ ...head, pastLease: true });
  }
  const wakeAt = timed.size > 0 ? Math.min(...timed.values()) : undefined;
  return { launch, held, reservation, wakeAt };
}

/**
 * Derive every gate's Candidate and the priority order, for either rule. Shared with sim.ts for the same reason as admit().
 *
 * `slots`: longest expected wall first, as it always was; one slot per gate, and an elastic gate's slots decided at admission.
 *
 * `cores`: d(g) = clamp(median cpu / least-contended wall, 0.25, C) for a measured gate; one core for an unmeasured one. An elastic gate (`cores: {min, max}`) carries an ElasticPlan instead, and its width is decided at admission by the area rule; its planning `cores` is its `min` until then. Memory is the largest measured peak RSS, else 4 GB for `heavy` and 0.5 GB otherwise. Priority is max(bottom level over `needs`, cpu), both in ms: with one-core gates and no edges it reduces to the slots rule's longest-first, and a wide gate like check:test-shared (33.6 cpu-s over 4.8 s) moves to the first wave instead of starting last.
 */
export function planAdmission(
  specs: readonly GateSpec[],
  opts: Pick<PoolOptions, 'jobs' | 'durations' | 'sched' | 'budget' | 'costs'>
): { byId: Map<string, Candidate>; rank: (a: GateSpec, b: GateSpec) => number } {
  const position = new Map(specs.map((spec, i) => [spec.id, i]));
  // A missing or corrupt duration cache must never fail the run, so an unknown gate is simply assumed cheap-ish and sorts late.
  const expected = (spec: GateSpec): number => opts.durations.get(spec.id) ?? 5000;
  // An elastic gate's planning width is its floor, clamped so a `min` above the whole budget cannot make it inadmissible at --jobs 1.
  const effWidth = (spec: GateSpec): number =>
    Math.min(Math.max(1, spec.cores?.min ?? 1), Math.max(1, opts.jobs));
  const elasticOf = (
    spec: GateSpec,
    estMs: number,
    cost: GateCost | undefined
  ): ElasticPlan | undefined => {
    if (spec.cores === undefined) return undefined;
    const measured = cost?.cpuMs !== undefined && cost.cpuMs > 0;
    return {
      min: Math.max(1, spec.cores.min),
      max: spec.cores.max === 'all' ? Number.POSITIVE_INFINITY : spec.cores.max,
      workMs: measured ? (cost?.cpuMs ?? 0) : effWidth(spec) * estMs,
      // A per-core share above 1 is a tool that oversubscribes its grant, below 0.05 a measurement of nothing; either would steer the area term on noise.
      perCore: Math.min(1.5, Math.max(0.05, cost?.perCore ?? 1)),
      measured,
    };
  };
  const byPosition = (a: GateSpec, b: GateSpec): number =>
    (position.get(a.id) ?? 0) - (position.get(b.id) ?? 0);
  const byId = new Map<string, Candidate>();

  if ((opts.sched ?? 'slots') === 'slots') {
    for (const spec of specs) {
      const estMs = expected(spec);
      const elastic = elasticOf(spec, estMs, opts.costs?.get(spec.id));
      byId.set(spec.id, {
        id: spec.id,
        slots: effWidth(spec),
        cores: effWidth(spec),
        memMb: 0,
        estMs,
        heavy: spec.heavy === true,
        mutex: spec.mutex ?? [],
        reads: sharedClaims(spec),
        cpuMs: elastic?.workMs ?? effWidth(spec) * estMs,
        elastic,
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
    const estMs = opts.durations.get(spec.id) ?? cost?.wallMs ?? 5000;
    const elastic = elasticOf(spec, estMs, cost);
    // An elastic gate's measured cpu/wall is the width of whatever grant it last ran at, so it is not its d: its planning width is its floor until admit() sizes it.
    const d =
      elastic !== undefined
        ? effWidth(spec)
        : measured
          ? Math.min(Math.max((cost.cpuMs ?? 0) / (cost.wallMs ?? 1), 0.25), c)
          : 1;
    const work = elastic?.workMs ?? (measured ? (cost.cpuMs ?? 0) : d * estMs);
    cpuMs.set(spec.id, work);
    byId.set(spec.id, {
      id: spec.id,
      slots: effWidth(spec),
      cores: d,
      memMb: cost?.rssMb ?? (spec.heavy === true ? 4096 : 512),
      estMs,
      heavy: spec.heavy === true && !measured,
      mutex: spec.mutex ?? [],
      reads: sharedClaims(spec),
      cpuMs: work,
      elastic,
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
  // THE PLAN FIELDS the horizon reads (horizonMs): each gate's area, its wall at the widest grant it can get, and the `needs` chain behind it at those walls.
  const all = [...byId.values()];
  for (const g of all) {
    const el = g.elastic;
    g.areaMs = scales(el) ? el.workMs / el.perCore : g.cpuMs;
    g.minWallMs = scales(el)
      ? elasticWall(el, g.estMs, Math.max(el.min, Math.min(el.max, c)))
      : g.estMs;
  }
  const tails = new Map<string, number>();
  const tailOf = (id: string): number => {
    const hit = tails.get(id);
    if (hit !== undefined) return hit;
    if (visiting.has(id)) throw new Error(`ci-runner: dependency cycle through ${id}`);
    visiting.add(id);
    let tail = 0;
    for (const dep of dependents.get(id) ?? [])
      tail = Math.max(tail, (byId.get(dep)?.minWallMs ?? 0) + tailOf(dep));
    visiting.delete(id);
    tails.set(id, tail);
    return tail;
  };
  for (const g of all) g.tailMs = tailOf(g.id);
  // RANK BY THE WALL A GATE WILL HAVE, NOT THE ONE IT LAST HAD. A measured elastic gate's planning wall is its wall at the width the pool plans to give it (the area rule, floored by needWidth against the whole run's horizon), not the duration cache's ewma, which is the wall of whatever grant it last ran at: check:ci-account-server's 173 s ewma was learned running wide, and at the one core the area
  // rule then gave it, it took 667 s.
  let totalCpu = 0;
  for (const g of all) totalCpu += g.cpuMs;
  const horizon0 = horizonMs(all, [], 0, c);
  for (const g of all) {
    const el = g.elastic;
    if (!scales(el)) continue;
    const widest = Math.max(el.min, Math.min(el.max, Math.floor(c + FIT_TOLERANCE)));
    const planned = Math.max(
      el.min,
      Math.min(
        widest,
        Math.max(
          areaGrant(el, g.estMs, c, totalCpu - g.cpuMs),
          opts.budget?.floor === false ? 0 : (needWidth(g, all, [], 0, horizon0, c) ?? 0)
        )
      )
    );
    g.estMs = elasticWall(el, g.estMs, planned);
  }
  // A gate sharing an EXCLUSIVE resource is on a chain as long as every holder's wall together, whichever of them starts first, so each ranks at least that high.
  const serial = new Map<string, number>();
  for (const g of all) for (const r of g.mutex) serial.set(r, (serial.get(r) ?? 0) + g.estMs);
  const priority = new Map(
    specs.map((spec) => {
      const g = byId.get(spec.id);
      let group = 0;
      for (const r of g?.mutex ?? []) group = Math.max(group, serial.get(r) ?? 0);
      return [spec.id, Math.max(level(spec.id), group, cpuMs.get(spec.id) ?? 0)];
    })
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

  const grants = new Map<string, number>();
  const lease = opts.lease;
  const pollMs = opts.leasePollMs ?? LEASE_POLL_MS;
  // When each gate was first held by the lease: the start of its bounded hold (admit's leaseHeldSince).
  const leaseSince = new Map<string, number>();
  const overLease = new Map<string, { granted: number; held: number }>();
  const holdForLease = (id: string, at: number): void => {
    blockedBy.set(id, 'lease');
    if (!leaseSince.has(id)) leaseSince.set(id, at);
  };
  const coresInUse = (): number => {
    let sum = 0;
    for (const r of inFlight.values()) sum += r.gate.cores;
    return sum;
  };

  // `gate` is the candidate admit() launched, carrying its grant. The lease is drawn here, at launch (fitToLease): a short acquire narrows an elastic gate to what was actually got, and below its `min` the tokens go back and the gate waits with `lease`, whether or not anything runs. Only a gate admit() launched past the lease starts on more than it got, and that is recorded.
  const launch = async (spec: GateSpec, admitted: Candidate): Promise<boolean> => {
    let gate = admitted;
    if (lease !== undefined && sched === 'cores') {
      const before = coresInUse();
      const held = await lease.reconcile(before + gate.cores);
      const fit = fitToLease(gate, held - before);
      if (fit === undefined) {
        await lease.reconcile(before);
        holdForLease(spec.id, Date.now());
        return false;
      }
      if (fit.gate.cores + FIT_TOLERANCE < gate.cores)
        await lease.reconcile(before + fit.gate.cores);
      gate = fit.gate;
      if (fit.over !== undefined) overLease.set(spec.id, fit.over);
    }
    unstarted.delete(spec.id);
    const now = Date.now();
    inFlight.set(spec.id, { gate, endsAt: now + gate.estMs });
    startAt.set(spec.id, now);
    const grant = gate.grant ?? Math.max(1, Math.round(gate.cores));
    grants.set(spec.id, grant);
    opts.onStart?.(spec);
    running.set(
      spec.id,
      opts
        .exec(spec, { cores: grant, leaseHeld: lease?.held === true })
        .then((outcome) => ({ id: spec.id, outcome, endAt: Date.now() }))
    );
    return true;
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

    const pending = [...unstarted].map(candidate);
    const view =
      lease !== undefined && sched === 'cores' && ready.length > 0
        ? await lease.available(coresInUse())
        : undefined;
    const finite = (n: number | undefined): number | undefined =>
      n === undefined || n === Number.POSITIVE_INFINITY ? undefined : n;
    const pass = admit(
      ready.map((spec) => candidate(spec.id)),
      [...inFlight.values()],
      {
        ...cfg,
        pending,
        leaseFree: finite(view?.free),
        leaseShare: finite(view?.share),
        leaseTotal: finite(view?.total),
        settleUntil:
          view !== undefined && lease?.openedAt !== undefined
            ? lease.openedAt + SETTLE_MS
            : undefined,
        leaseHeldSince: leaseSince,
      },
      now
    );
    let leaseWait = false;
    for (const [id, why] of pass.held) {
      if (why === 'lease') {
        holdForLease(id, now);
        leaseWait = true;
      } else blockedBy.set(id, why);
    }
    for (const gate of pass.launch)
      if (!(await launch(mustGet(byId, gate.id), gate))) leaseWait = true;
    // Another run's release raises no event in this process, so a pool with a gate the lease holds re-reads it on a timer: by the earliest timed hold's end, and at least every pollMs.
    const nap = leaseWait
      ? Math.max(1, Math.min(pollMs, (pass.wakeAt ?? Number.POSITIVE_INFINITY) - Date.now()))
      : undefined;

    if (running.size === 0 && unstarted.size > 0 && ready.length > 0) {
      if (nap !== undefined) {
        await new Promise((resolve) => setTimeout(resolve, nap));
        continue;
      }
      // admit() already ran the progress guarantee, and the lease holds nothing here, so work outstanding with nothing in flight means no ready gate was admissible even alone.
      throw new Error('ci-runner: internal error, pool stalled with work outstanding');
    }
    if (running.size === 0 && unstarted.size > 0) {
      throw new Error('ci-runner: internal error, pool stalled: nothing ready, nothing running');
    }

    if (running.size === 0) continue;

    let timer: NodeJS.Timeout | undefined;
    const settledOrTick = await Promise.race([
      ...running.values(),
      ...(nap === undefined
        ? []
        : [
            new Promise<undefined>((resolve) => {
              timer = setTimeout(() => resolve(undefined), nap);
            }),
          ]),
    ]);
    if (timer !== undefined) clearTimeout(timer);
    if (settledOrTick === undefined) continue;
    const { id, outcome, endAt } = settledOrTick;
    const spec = mustGet(byId, id);
    running.delete(id);
    const settled = inFlight.get(id);
    inFlight.delete(id);
    if (lease !== undefined && sched === 'cores') await lease.reconcile(coresInUse());

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
      grantedCores: grants.get(id),
      elastic: settled?.gate.elastic !== undefined ? true : undefined,
      overLease: overLease.get(id),
      timedOutMs: outcome.timedOutMs,
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

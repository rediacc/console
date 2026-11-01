/**
 * A discrete-event simulator of the gate pool, for the scheduler's own tests (agent/plans/PLAN-ci-quick-cpu-scheduling.md section 3).
 *
 * It drives the SAME admit() and planAdmission() runPool drives, so a finding here is a finding about the pool, not about a model of it. Each simulated gate has a true width d (cores it keeps busy) and a true uncontended wall; the machine has P cores, and when the running gates ask for more than P each one progresses at P / sum(d) of its full speed (processor sharing). Idle
 * core-seconds are P x makespan minus the busy integral, the same quantity the footer reads off /proc/stat.
 *
 * An ELASTIC gate (`elastic: {min, max}`, agent/plans/PLAN-prepush-full-cpu.md part 1) has a fixed amount of work, d x wall core-ms, and runs at whatever width admit() grants it: its true width is the grant and its true wall work / grant, under the same processor sharing above P.
 *
 * The estimates the scheduler sees are the truth by default (a measured gate) or nothing at all (an unmeasured one, budgeted at one core, or at its `min` when elastic), so the tests below judge the admission rule rather than the quality of a cache.
 *
 * Run directly for the comparison table: `npx tsx scripts/ci-runner/sim.ts`.
 */
import { isEntryPoint } from '../lib/entry-point.js';
import type { GateSpec } from './manifest';
import {
  admit,
  BORROW_WALL_MS,
  type BorrowSpan,
  type Candidate,
  type CoreBudget,
  fitToLease,
  type GateCost,
  type IdleReader,
  LEASE_POLL_MS,
  type PoolOptions,
  planAdmission,
  RECLAIM_HEADROOM,
  RECLAIM_POLL_MS,
  RECLAIM_WINDOW_MS,
  reclaimableCores,
  runPool,
  type Sched,
  type ScheduleOrder,
  SETTLE_MS,
} from './pool';
import { type CpuTick, idleCoreMsBetween } from './report';

interface SimGate {
  id: string;
  /** True width: cores the gate keeps busy while it runs. */
  cores: number;
  /** True uncontended wall, ms. */
  wallMs: number;
  memMb?: number;
  needs?: string[];
  /** Declared elastic range; `cores` x `wallMs` is then the gate's work, and its width is the grant. */
  elastic?: { min: number; max: number | 'all' };
  /** An elastic gate's share of each granted core it keeps busy (GateCost.perCore), default 1: at a grant of k its wall is work / (perCore x k). */
  perCore?: number;
  heavy?: boolean;
  mutex?: string[];
  reads?: string[];
  /**
   * What the scheduler is TOLD, when it differs from the truth: the duration cache's planning wall (`estMs`, the ewma), its least-contended wall, CPU and per-core share. Absent fields fall back to the truth. This is the seam that models a stale cache: an elastic gate whose ewma was learned at a width it no longer gets.
   */
  est?: { estMs?: number; wallMs?: number; cpuMs?: number; perCore?: number };
  /** Default true: the scheduler sees cpu = cores x wall, wall and memMb as measured. False: it sees nothing. */
  measured?: boolean;
  /** What the gate really keeps busy as it progresses: from `atFrac` of its work on, `cores` instead of its width. Models a wide gate that goes quiet, which the budget cannot see. Its progress is unchanged. */
  phases?: { atFrac: number; cores: number }[];
}

interface SimConfig {
  sched: Sched;
  /** P: the machine's cores, for processor sharing and the idle integral. */
  machineCores: number;
  jobs: number;
  heavyLimit: number;
  budget: CoreBudget;
  /** Record a violation whenever two or more running gates' budgeted cores exceed this (cores rule only). */
  capCheck?: number;
  /** The learned order (rank.ts), passed to planAdmission exactly as runPool passes it. */
  order?: ScheduleOrder;
  /** Feed admit() the idle this simulated machine measures, and re-read it on RECLAIM_POLL_MS, as runPool does when it has an `idleCoreMs`. Off is the budget alone. */
  conserve?: boolean;
}

/** Several runs on one machine drawing from one token pool, the way core_lease.py's broker serves them. */
interface RunsConfig extends SimConfig {
  /** T: the lease's tokens. Each run reads free, share ceil(T / live runs) and total before every pass, and settles SETTLE_MS from its start. */
  tokens: number;
  /** How often a run with a lease-held gate re-reads the lease, ms (default LEASE_POLL_MS). */
  pollMs?: number;
}

/** One run: the gates it schedules and when it registers with the lease. */
interface SimRun {
  id: string;
  startMs: number;
  gates: readonly SimGate[];
}

interface SimResult {
  makespanMs: number;
  idleCoreS: number;
  starts: Map<string, number>;
  ends: Map<string, number>;
  readyAt: Map<string, number>;
  capViolations: number;
  /** The cores admit() granted each gate at launch. */
  grants: Map<string, number>;
  /** Gates admit() ever held with `lease`. */
  leaseHeld: Set<string>;
  /** Gates that launched past the lease: granted cores and tokens held (GateResult.overLease). */
  overLease: Map<string, { granted: number; held: number }>;
  /** Gates admit() launched into measured idle, with the cores each took. */
  borrowed: Map<string, number>;
  /** The most cores every gate on the machine really wanted at one moment. */
  peakDemand: number;
  /** The integral of demand above the machine's cores: how much the machine was oversubscribed, and for how long. */
  overCoreS: number;
}

/** A run's result inside simulateRuns: its own gates, plus when it ended and the machine's idle core-seconds from t = 0 to that end. */
interface RunResult extends SimResult {
  endMs: number;
  idleToEndCoreS: number;
}

const EPS_MS = 1e-6;

function specOf(g: SimGate): GateSpec {
  return {
    id: g.id,
    run: 'true',
    gate: true,
    needs: g.needs,
    leaves: [],
    cores: g.elastic,
    heavy: g.heavy,
    mutex: g.mutex,
    reads: g.reads,
    ci: {
      kind: 'local-only',
      blocker: 'BLOCKER: synthetic scheduler-simulator fixture, never part of the real gate set',
    },
  };
}

/** One run's scheduler state, as runPool keeps it. */
function runState(run: SimRun, cfg: SimConfig) {
  const specs = run.gates.map(specOf);
  const truth = new Map(run.gates.map((g) => [g.id, g]));
  const costs = new Map<string, GateCost>();
  const durations = new Map<string, number>();
  for (const g of run.gates) {
    if (g.measured === false) {
      // Unmeasured: no CPU, but the runner still has whatever wall the cache holds for it (`est`), as run.ts's costsFrom does for a gate with a duration record and no cpu sample.
      if (g.est?.estMs !== undefined) durations.set(g.id, g.est.estMs);
      if (g.est?.wallMs !== undefined) costs.set(g.id, { wallMs: g.est.wallMs });
      continue;
    }
    costs.set(g.id, {
      cpuMs: g.est?.cpuMs ?? g.cores * g.wallMs,
      wallMs: g.est?.wallMs ?? g.wallMs,
      rssMb: g.memMb ?? 512,
      perCore: g.elastic !== undefined ? (g.est?.perCore ?? g.perCore ?? 1) : undefined,
    });
    durations.set(g.id, g.est?.estMs ?? g.wallMs);
  }
  const { byId, rank } = planAdmission(specs, {
    jobs: cfg.jobs,
    durations,
    sched: cfg.sched,
    budget: cfg.budget,
    costs,
    order: cfg.order,
  });
  const cand = (id: string): Candidate => {
    const c = byId.get(id);
    if (c === undefined) throw new Error(`sim: no candidate for ${id}`);
    return c;
  };
  return {
    run,
    specs,
    truth,
    rank,
    cand,
    starts: new Map<string, number>(),
    ends: new Map<string, number>(),
    readyAt: new Map<string, number>(),
    // Remaining work of each running gate, in ms of full-speed wall, and the candidate admit() launched it as (an elastic gate's carries its grant).
    running: new Map<string, number>(),
    launched: new Map<string, Candidate>(),
    grants: new Map<string, number>(),
    leaseHeld: new Set<string>(),
    leaseSince: new Map<string, number>(),
    overLease: new Map<string, { granted: number; held: number }>(),
    borrowed: new Map<string, number>(),
    borrows: new Map<string, BorrowSpan>(),
    /** Full-speed wall each running gate started with, to place its `phases`. */
    totals: new Map<string, number>(),
    /** Lease tokens this run holds. */
    tokens: 0,
    /** Next moment this run re-reads the lease on its own timer. */
    wake: Number.POSITIVE_INFINITY,
    dirty: true,
    done: false,
    endMs: 0,
    busyAtEnd: 0,
    capViolations: 0,
  };
}
type RunState = ReturnType<typeof runState>;

/**
 * The engine under simulate() and simulateRuns(). Each run passes through admit() only at the moments runPool would: when it starts, when one of its own gates ends, and on its lease timer. Under a lease (`tokens`) a launch draws tokens the way PoolLease.reconcile does and is fitted by the pool's own fitToLease; without one the passes see no lease at all, as before the lease existed.
 */
function engine(
  runs: readonly SimRun[],
  cfg: SimConfig & { tokens?: number; pollMs?: number }
): {
  makespanMs: number;
  idleCoreS: number;
  peakDemand: number;
  overCoreS: number;
  runs: Map<string, RunState>;
} {
  const states = runs.map((r) => runState(r, cfg));
  const pollMs = cfg.pollMs ?? LEASE_POLL_MS;
  const leased = cfg.tokens !== undefined;
  const total = cfg.tokens ?? Number.POSITIVE_INFINITY;
  let t = 0;
  let busy = 0;
  let peakDemand = 0;
  let over = 0;
  // What the simulated machine measured, newest last, kept no further back than one window: the seam run.ts fills from /proc/stat.
  const history: { from: number; to: number; idle: number }[] = [];
  const idleCoreMs = (fromMs: number, toMs: number): number | undefined => {
    if (history.length === 0 || (history[0]?.from ?? 0) > fromMs + EPS_MS) return undefined;
    let sum = 0;
    for (const h of history) {
      sum += h.idle * Math.max(0, Math.min(h.to, toMs) - Math.max(h.from, fromMs));
    }
    return sum;
  };
  const started = (s: RunState): boolean => s.run.startMs <= t + EPS_MS;
  const freeTokens = (): number => total - states.reduce((sum, s) => sum + s.tokens, 0);
  // True width while running: the grant for an elastic gate, the declared d otherwise, or what its current phase really keeps busy.
  const width = (s: RunState, id: string): number => {
    const g = s.truth.get(id);
    const total = s.totals.get(id) ?? 0;
    const done = total > 0 ? 1 - (s.running.get(id) ?? 0) / total : 0;
    let phase: number | undefined;
    for (const p of g?.phases ?? []) if (done + 1e-12 >= p.atFrac) phase = p.cores;
    if (phase !== undefined) return phase;
    return g?.elastic !== undefined ? (s.grants.get(id) ?? 1) : (g?.cores ?? 0);
  };
  // Time until this gate's next phase boundary, at full speed; infinite past its last.
  const toPhase = (s: RunState, id: string): number => {
    const total = s.totals.get(id) ?? 0;
    const left = s.running.get(id) ?? 0;
    let next = Number.POSITIVE_INFINITY;
    for (const p of s.truth.get(id)?.phases ?? []) {
      const gap = left - total * (1 - p.atFrac);
      if (gap > EPS_MS) next = Math.min(next, gap);
    }
    return next;
  };
  const inUse = (s: RunState): number => {
    let sum = 0;
    for (const id of s.running.keys()) sum += (s.launched.get(id) ?? s.cand(id)).cores;
    return sum;
  };
  // lease-client.ts reconcile: hold ceil(cores) tokens, acquiring only what is free.
  const reconcile = (s: RunState, cores: number): number => {
    const want = Math.max(0, Math.ceil(cores - 1e-9));
    if (s.tokens < want) s.tokens += Math.max(0, Math.min(want - s.tokens, freeTokens()));
    else s.tokens = want;
    return s.tokens;
  };

  const pass = (s: RunState): void => {
    s.dirty = false;
    s.wake = Number.POSITIVE_INFINITY;
    const ready = s.specs
      .filter((spec) => !s.starts.has(spec.id) && (spec.needs ?? []).every((n) => s.ends.has(n)))
      .sort(s.rank);
    for (const spec of ready) if (!s.readyAt.has(spec.id)) s.readyAt.set(spec.id, t);
    const pending = s.specs.filter((spec) => !s.starts.has(spec.id)).map((spec) => s.cand(spec.id));
    const live = states.filter((o) => started(o) && !o.done).length;
    const borrowable = cfg.conserve
      ? reclaimableCores(t, idleCoreMs, [...s.borrows.values()], leased ? live : 1)
      : undefined;
    const result = admit(
      ready.map((spec) => s.cand(spec.id)),
      [...s.running.keys()].map((id) => {
        const g = s.launched.get(id) ?? s.cand(id);
        return { gate: g, endsAt: (s.starts.get(id) ?? 0) + g.estMs };
      }),
      {
        sched: cfg.sched,
        jobs: cfg.jobs,
        heavyLimit: cfg.heavyLimit,
        budget: cfg.budget,
        pending,
        borrowable,
        ...(leased
          ? {
              leaseFree: freeTokens() + Math.max(0, s.tokens - inUse(s)),
              leaseShare: Math.ceil(total / Math.max(1, live)),
              leaseTotal: total,
              settleUntil: s.run.startMs + SETTLE_MS,
              leaseHeldSince: s.leaseSince,
            }
          : {}),
      },
      t
    );
    let leaseWait = false;
    const holdForLease = (id: string): void => {
      leaseWait = true;
      s.leaseHeld.add(id);
      if (!s.leaseSince.has(id)) s.leaseSince.set(id, t);
    };
    for (const [id, why] of result.held) if (why === 'lease') holdForLease(id);
    for (const admitted of result.launch) {
      let g = admitted;
      if (leased) {
        const before = inUse(s);
        const fit = fitToLease(g, reconcile(s, before + g.cores) - before);
        if (fit === undefined) {
          reconcile(s, before);
          holdForLease(g.id);
          continue;
        }
        g = fit.gate;
        reconcile(s, before + g.cores);
        if (fit.over !== undefined) s.overLease.set(g.id, fit.over);
      }
      s.starts.set(g.id, t);
      s.launched.set(g.id, g);
      s.grants.set(g.id, g.grant ?? 1);
      if (g.borrowed !== undefined) {
        s.borrowed.set(g.id, g.borrowed);
        s.borrows.set(g.id, { from: t, cores: g.borrowed });
      }
      const tg = s.truth.get(g.id);
      const full =
        tg?.elastic !== undefined
          ? (tg.cores * tg.wallMs) / ((tg.perCore ?? 1) * Math.max(1, g.grant ?? 1))
          : (tg?.wallMs ?? 0);
      s.running.set(g.id, full);
      s.totals.set(g.id, full);
    }
    if (leaseWait)
      s.wake = t + Math.max(1, Math.min(pollMs, (result.wakeAt ?? Number.POSITIVE_INFINITY) - t));
    if (
      cfg.conserve &&
      result.held.some(([, why]) => why === 'cpu' || why === 'reservation' || why === 'lease')
    )
      s.wake = Math.min(s.wake, t + RECLAIM_POLL_MS);
    if (cfg.sched === 'cores' && cfg.capCheck !== undefined && s.running.size > 1) {
      let budgeted = 0;
      for (const id of s.running.keys()) budgeted += (s.launched.get(id) ?? s.cand(id)).cores;
      if (budgeted > cfg.capCheck + 1e-9) s.capViolations += 1;
    }
    if (s.running.size === 0 && s.wake === Number.POSITIVE_INFINITY)
      throw new Error(`sim: run ${s.run.id} stalled at ${t} ms`);
  };

  t = Math.min(...states.map((s) => s.run.startMs));
  while (states.some((s) => !s.done)) {
    for (const s of states) if (!s.done && started(s) && (s.dirty || s.wake <= t + EPS_MS)) pass(s);

    let demand = 0;
    for (const s of states) for (const id of s.running.keys()) demand += width(s, id);
    const rate = demand > 0 ? Math.min(1, cfg.machineCores / demand) : 1;
    let step = Number.POSITIVE_INFINITY;
    for (const s of states) {
      for (const [id, left] of s.running) {
        step = Math.min(step, left / rate, toPhase(s, id) / rate);
      }
      if (!started(s)) step = Math.min(step, s.run.startMs - t);
      else if (!s.done) step = Math.min(step, s.wake - t);
    }
    if (!Number.isFinite(step)) throw new Error(`sim: every run stalled at ${t} ms`);
    peakDemand = Math.max(peakDemand, demand);
    over += Math.max(0, demand - cfg.machineCores) * step;
    if (cfg.conserve && step > 0) {
      history.push({ from: t, to: t + step, idle: Math.max(0, cfg.machineCores - demand) });
      while ((history[1]?.to ?? Number.POSITIVE_INFINITY) < t + step - RECLAIM_WINDOW_MS - 1)
        history.shift();
    }
    t += step;
    busy += Math.min(cfg.machineCores, demand) * step;
    for (const s of states) {
      let ended = false;
      for (const [id, left] of s.running) {
        const rest = left - step * rate;
        if (rest <= EPS_MS) {
          s.running.delete(id);
          s.ends.set(id, t);
          const span = s.borrows.get(id);
          if (span !== undefined) span.to = t;
          ended = true;
        } else s.running.set(id, rest);
      }
      if (ended) {
        s.dirty = true;
        if (leased) reconcile(s, inUse(s));
      }
      if (!s.done && s.ends.size === s.specs.length) {
        // The run exits: its broker closes, its tokens and its registration go with it.
        s.done = true;
        s.tokens = 0;
        s.endMs = t;
        s.busyAtEnd = busy;
      }
    }
  }
  return {
    makespanMs: t,
    idleCoreS: (cfg.machineCores * t - busy) / 1000,
    peakDemand,
    overCoreS: over / 1000,
    runs: new Map(states.map((s) => [s.run.id, s])),
  };
}

function resultOf(
  s: RunState,
  makespanMs: number,
  idleCoreS: number,
  peakDemand: number,
  overCoreS: number
): SimResult {
  return {
    borrowed: s.borrowed,
    peakDemand,
    overCoreS,
    makespanMs,
    idleCoreS,
    starts: s.starts,
    ends: s.ends,
    readyAt: s.readyAt,
    capViolations: s.capViolations,
    grants: s.grants,
    leaseHeld: s.leaseHeld,
    overLease: s.overLease,
  };
}

function simulate(gates: readonly SimGate[], cfg: SimConfig): SimResult {
  const out = engine([{ id: 'run', startMs: 0, gates }], cfg);
  const s = out.runs.get('run');
  if (s === undefined) throw new Error('sim: the single run vanished');
  return resultOf(s, out.makespanMs, out.idleCoreS, out.peakDemand, out.overCoreS);
}

/**
 * N runs sharing one token pool (agent/plans/PLAN-prepush-full-cpu.md part 4, B11), each scheduled by the same admit() as simulate(), all under one processor-sharing machine. Gate ids must be unique across runs.
 */
export function simulateRuns(
  runs: readonly SimRun[],
  cfg: RunsConfig
): { makespanMs: number; idleCoreS: number; runs: Map<string, RunResult> } {
  const out = engine(runs, cfg);
  const results = new Map<string, RunResult>();
  for (const [id, s] of out.runs)
    results.set(id, {
      ...resultOf(s, s.endMs - s.run.startMs, out.idleCoreS, out.peakDemand, out.overCoreS),
      endMs: s.endMs,
      idleToEndCoreS: (cfg.machineCores * s.endMs - s.busyAtEnd) / 1000,
    });
  return { makespanMs: out.makespanMs, idleCoreS: out.idleCoreS, runs: results };
}

/** What predictMakespan needs of the run: the same planning inputs runPool gets. */
type PlanInputs = Pick<
  PoolOptions,
  'jobs' | 'heavyLimit' | 'durations' | 'sched' | 'budget' | 'costs' | 'order'
>;

/**
 * THE RUNNER'S SAFETY CHECK (agent/plans/PLAN-gate-scheduling-learned.md section 5): the makespan of one graph under one order, simulated through the same admit() and planAdmission() runPool drives, with each gate's TRUTH set to exactly what the scheduler is told (its planning wall, its measured width), so two orders are compared on the same estimates and the difference is the order's alone. No lease: the lone-run shape, the same for both orders. `needs` outside the graph are dropped, as buildGraph has already pulled in every prerequisite that runs.
 */
export function predictMakespan(
  specs: readonly GateSpec[],
  plan: PlanInputs,
  machineCores: number
): { makespanMs: number; starts: Map<string, number> } {
  const inGraph = new Set(specs.map((s) => s.id));
  const sched = plan.sched ?? 'slots';
  const gates: SimGate[] = specs.map((spec) => {
    const cost = plan.costs?.get(spec.id);
    const estMs = plan.durations.get(spec.id) ?? cost?.wallMs ?? 5000;
    const measured =
      sched === 'cores' &&
      cost?.cpuMs !== undefined &&
      cost.cpuMs > 0 &&
      cost.wallMs !== undefined &&
      cost.wallMs > 0;
    const base = {
      id: spec.id,
      needs: (spec.needs ?? []).filter((n) => inGraph.has(n)),
      elastic: spec.cores,
      heavy: spec.heavy,
      mutex: spec.mutex,
      reads: spec.reads,
      memMb: cost?.rssMb ?? (spec.heavy === true ? 4096 : 512),
    };
    if (!measured) {
      const width = Math.max(1, spec.cores?.min ?? 1);
      return {
        ...base,
        cores: width,
        wallMs: estMs,
        measured: false,
        est: { estMs: plan.durations.get(spec.id), wallMs: cost?.wallMs },
      };
    }
    const cpuMs = cost?.cpuMs ?? 0;
    const wallMs = cost?.wallMs ?? estMs;
    const c = Math.max(1, plan.budget?.cores ?? plan.jobs);
    return {
      ...base,
      // Truth = the plan: a fixed-width gate keeps d cores busy for its planning wall; an elastic one carries its measured work.
      cores:
        spec.cores !== undefined
          ? cpuMs / Math.max(1, estMs)
          : Math.min(Math.max(cpuMs / wallMs, 0.25), c),
      wallMs: estMs,
      perCore: spec.cores !== undefined ? (cost?.perCore ?? 1) : undefined,
      est: { estMs, wallMs, cpuMs, perCore: cost?.perCore },
    };
  });
  const r = simulate(gates, {
    sched,
    machineCores: Math.max(1, machineCores),
    jobs: plan.jobs,
    heavyLimit: plan.heavyLimit,
    budget: plan.budget ?? {
      cores: plan.jobs,
      epsilon: 0,
      maxProcs: 2 * plan.jobs,
      memMb: Number.POSITIVE_INFINITY,
    },
    order: plan.order,
  });
  return { makespanMs: r.makespanMs, starts: r.starts };
}

/** A small deterministic generator, so every run of the selftest simulates the same mix. */
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

/** Section 3's mix: 60 I/O gates at d 0.2, 8 wide gates at d 6, 120 one-core gates, and an 18 s chain behind an 8 s build that 20 of the one-core gates also need. */
function syntheticMix(): SimGate[] {
  const r = rng(20260930);
  const between = (lo: number, hi: number): number => Math.round(lo + r() * (hi - lo));
  const gates: SimGate[] = [
    { id: 'build', cores: 4, wallMs: 8000 },
    { id: 'chain-1', cores: 1, wallMs: 10000, needs: ['build'] },
    { id: 'chain-2', cores: 1, wallMs: 8000, needs: ['chain-1'] },
  ];
  for (let i = 0; i < 60; i += 1)
    gates.push({ id: `io-${i}`, cores: 0.2, wallMs: between(1000, 4000) });
  for (let i = 0; i < 8; i += 1)
    gates.push({ id: `wide-${i}`, cores: 6, wallMs: between(4000, 6000) });
  for (let i = 0; i < 120; i += 1) {
    gates.push({
      id: `one-${i}`,
      cores: 1,
      wallMs: between(1000, 8000),
      needs: i < 20 ? ['build'] : undefined,
    });
  }
  return gates;
}

/** This machine's shape: 24 cores, slots 22 (availableParallelism() - 2), C 23, K 46, M 29 GB. */
const P24 = {
  machineCores: 24,
  jobs: 22,
  heavyLimit: 5,
  budget: { cores: 23, epsilon: 0.1, maxProcs: 46, memMb: 29 * 1024 },
};

/**
 * The scheduler's tests, each with its control. Returns failures (empty when green) and the assertion count, for run.ts's selftest.
 */
export function schedulerSelftest(): { failures: string[]; assertions: number; table: string[] } {
  const failures: string[] = [];
  const table: string[] = [];
  let assertions = 0;
  const check = (ok: boolean, message: string): void => {
    assertions += 1;
    if (!ok) failures.push(message);
  };
  const line = (name: string, r: SimResult): void => {
    table.push(
      `${name.padEnd(28)} makespan ${(r.makespanMs / 1000).toFixed(1).padStart(6)} s   idle ${r.idleCoreS.toFixed(1).padStart(7)} core-s`
    );
  };

  // 1. THE MIX: cores cuts idle core-seconds by at least 30% with no worse makespan, and never exceeds C(1+epsilon) (capCheck at exactly that).
  const mix = syntheticMix();
  const cap = P24.budget.cores * (1 + P24.budget.epsilon);
  const slots = simulate(mix, { ...P24, sched: 'slots' });
  const cores = simulate(mix, { ...P24, sched: 'cores', capCheck: cap });
  line('mix, slots', slots);
  line('mix, cores', cores);
  check(
    cores.idleCoreS <= 0.7 * slots.idleCoreS,
    `cores must cut idle core-seconds by >= 30% on the synthetic mix: slots ${slots.idleCoreS.toFixed(1)}, cores ${cores.idleCoreS.toFixed(1)}`
  );
  check(
    cores.makespanMs <= slots.makespanMs,
    `cores must not lengthen the synthetic mix: slots ${slots.makespanMs.toFixed(0)} ms, cores ${cores.makespanMs.toFixed(0)} ms`
  );
  check(
    cores.capViolations === 0,
    `cores over-admitted past C(1+eps) ${cores.capViolations} time(s)`
  );
  const firstWide = Math.min(
    ...mix.filter((g) => g.id.startsWith('wide-')).map((g) => cores.starts.get(g.id) ?? Infinity)
  );
  check(
    firstWide === 0,
    `a wide gate must start in the first wave under cores, first started at ${firstWide} ms`
  );

  // 2. CONTROL: epsilon infinite must fire the same cap assertion, or the zero above proves nothing.
  const unbounded = simulate(mix, {
    ...P24,
    sched: 'cores',
    budget: { ...P24.budget, epsilon: Number.POSITIVE_INFINITY },
    capCheck: cap,
  });
  check(
    unbounded.capViolations > 0,
    'CONTROL: epsilon = infinity must trip the C(1+eps) cap assertion'
  );

  // 3. CONTROL: all one-core gates, budget equal to the slot count -- cores reduces to the slots rule's longest-first, within 1%.
  const r1 = rng(7);
  const flat: SimGate[] = Array.from({ length: 150 }, (_, i) => ({
    id: `flat-${i}`,
    cores: 1,
    wallMs: Math.round(1000 + r1() * 7000),
  }));
  const flatSlots = simulate(flat, { ...P24, sched: 'slots' });
  const flatCores = simulate(flat, {
    ...P24,
    sched: 'cores',
    budget: { ...P24.budget, cores: P24.jobs, epsilon: 0 },
  });
  line('all one-core, slots 22', flatSlots);
  line('all one-core, cores C=22', flatCores);
  check(
    Math.abs(flatCores.makespanMs - flatSlots.makespanMs) <= 0.01 * flatSlots.makespanMs,
    `all-one-core: cores must be within 1% of slots, got ${flatCores.makespanMs.toFixed(0)} vs ${flatSlots.makespanMs.toFixed(0)} ms`
  );

  // 4. NO RESERVATION STARVES A d-8 GATE: it becomes ready at 3 s behind a stream of staggered one-core gates. With reservations it starts once 8 cores' worth of predicted ends have passed; the control without them sees at most ~2 free cores at any pass, until the stream drains.
  const r2 = rng(11);
  const stream: SimGate[] = [
    { id: 'gate0', cores: 1, wallMs: 3000 },
    { id: 'wide8', cores: 8, wallMs: 6000, needs: ['gate0'] },
    ...Array.from({ length: 300 }, (_, i) => ({
      id: `s-${i}`,
      cores: 1,
      wallMs: Math.round(3000 + r2() * 2000),
    })),
  ];
  const waited = (r: SimResult): number =>
    (r.starts.get('wide8') ?? 0) - (r.readyAt.get('wide8') ?? 0);
  const reserved = simulate(stream, { ...P24, sched: 'cores' });
  const unreserved = simulate(stream, {
    ...P24,
    sched: 'cores',
    budget: { ...P24.budget, reserve: false },
  });
  table.push(
    `d-8 gate waited: ${(waited(reserved) / 1000).toFixed(1)} s with reservations, ${(waited(unreserved) / 1000).toFixed(1)} s without`
  );
  check(
    waited(reserved) <= 5000,
    `a reserved d-8 gate must start within one one-core wall (5 s) of ready, waited ${waited(reserved).toFixed(0)} ms`
  );
  check(
    waited(unreserved) > 20000,
    `CONTROL: without reservations the d-8 gate must starve behind the stream, waited only ${waited(unreserved).toFixed(0)} ms`
  );

  // 5. d > C STILL RUNS ON AN IDLE POOL: an unmeasured gate whose declared `min` is 8, on a 5-core machine (C 4), is admitted alone and the pool finishes.
  const small = {
    machineCores: 5,
    jobs: 3,
    heavyLimit: 2,
    budget: { cores: 4, epsilon: 0.1, maxProcs: 8, memMb: 8192 },
  };
  const huge = simulate(
    [
      { id: 'huge', cores: 8, wallMs: 4000, elastic: { min: 8, max: 8 }, measured: false },
      ...Array.from({ length: 10 }, (_, i) => ({ id: `h-${i}`, cores: 1, wallMs: 1000 })),
    ],
    { ...small, sched: 'cores' }
  );
  check(
    huge.starts.get('huge') === 0 && huge.ends.has('huge') && huge.ends.size === 11,
    `a gate wider than C must be admitted on an idle pool, started at ${huge.starts.get('huge')}`
  );
  const hugeEnd = huge.ends.get('huge') ?? 0;
  check(
    [...huge.starts].every(([id, s]) => id === 'huge' || s >= hugeEnd - EPS_MS),
    'a gate wider than C runs alone: nothing may start beside it'
  );

  // 6. MEMORY: two 20 GB gates under M = 32 GB never overlap; the control at M = 64 GB shows the check can see an overlap.
  const fat: SimGate[] = [
    { id: 'fat-a', cores: 1, wallMs: 5000, memMb: 20480 },
    { id: 'fat-b', cores: 1, wallMs: 5000, memMb: 20480 },
    ...Array.from({ length: 10 }, (_, i) => ({ id: `m-${i}`, cores: 1, wallMs: 2000, memMb: 256 })),
  ];
  const overlap = (r: SimResult): boolean =>
    (r.starts.get('fat-b') ?? 0) < (r.ends.get('fat-a') ?? 0) - EPS_MS &&
    (r.starts.get('fat-a') ?? 0) < (r.ends.get('fat-b') ?? 0) - EPS_MS;
  const m32 = simulate(fat, { ...P24, sched: 'cores', budget: { ...P24.budget, memMb: 32768 } });
  const m64 = simulate(fat, { ...P24, sched: 'cores', budget: { ...P24.budget, memMb: 65536 } });
  check(!overlap(m32), 'two 20 GB gates must never overlap under M = 32 GB');
  check(
    overlap(m64),
    'CONTROL: two 20 GB gates must overlap under M = 64 GB, or the check cannot see one'
  );

  // 7. THE AREA RULE ON THE PLAN'S NUMBERS (PLAN-prepush-full-cpu part 1): a pytest of 7,866 cpu-s beside 818 cpu-s of one-core gates on C 23. It starts at t=0 with the area rule's 20 cores, never over-admits, and the pass beats the same work held at the old static `-n 8` (the control, a range of exactly 8) on makespan and on idle core-seconds.
  const fast: SimGate[] = Array.from({ length: 160 }, (_, i) => ({
    id: `f-${i}`,
    cores: 1,
    wallMs: 818_000 / 160,
  }));
  const pytest = (range: { min: number; max: number | 'all' }): SimGate => ({
    id: 'pytest',
    cores: 1,
    wallMs: 7_866_000,
    elastic: range,
  });
  const elastic = simulate([pytest({ min: 2, max: 'all' }), ...fast], {
    ...P24,
    sched: 'cores',
    capCheck: cap,
  });
  const fixed8 = simulate([pytest({ min: 8, max: 8 }), ...fast], { ...P24, sched: 'cores' });
  line('pytest elastic, cores', elastic);
  line('pytest fixed 8, cores', fixed8);
  table.push(
    `pytest grant at t=${elastic.starts.get('pytest')} ms: ${elastic.grants.get('pytest')}`
  );
  check(
    elastic.starts.get('pytest') === 0 && elastic.grants.get('pytest') === 20,
    `pytest must start at t=0 with the area rule's 20 cores of C 23, got ${elastic.grants.get('pytest')} at ${elastic.starts.get('pytest')} ms`
  );
  check(
    elastic.capViolations === 0,
    `the elastic pass over-admitted ${elastic.capViolations} time(s)`
  );
  check(
    elastic.makespanMs < 0.6 * fixed8.makespanMs && elastic.idleCoreS < fixed8.idleCoreS,
    `CONTROL: the elastic grant must beat a static 8 workers: elastic ${(elastic.makespanMs / 1000).toFixed(0)} s, fixed ${(fixed8.makespanMs / 1000).toFixed(0)} s`
  );
  // 8. A `min` WIDER THAN WHAT IS FREE HOLDS THE GATE, never shrinks below it: a min-6 gate behind five running one-core gates on C 8 waits for cores and then runs at >= 6.
  const held = simulate(
    [
      ...Array.from({ length: 5 }, (_, i) => ({ id: `b-${i}`, cores: 1, wallMs: 10_000 })),
      { id: 'late', cores: 1, wallMs: 1000, needs: ['b-0'] },
      { id: 'wide', cores: 6, wallMs: 3000, elastic: { min: 6, max: 'all' as const } },
    ],
    {
      machineCores: 9,
      jobs: 8,
      heavyLimit: 2,
      budget: { cores: 8, epsilon: 0, maxProcs: 16, memMb: 32768 },
      sched: 'cores',
    }
  );
  check(
    (held.grants.get('wide') ?? 0) >= 6,
    `an elastic gate must never run below its min, granted ${held.grants.get('wide')}`
  );

  // RUNS SHARING ONE LEASE (B11, PLAN-prepush-full-cpu part 4): 24 tokens, C the lease total, a pytest of the measured shape (10,600 cpu-s at 0.85 per core, min 2, max all).
  const leaseCfg: RunsConfig = {
    machineCores: 24,
    jobs: 22,
    heavyLimit: 5,
    budget: { cores: 24, epsilon: 0.1, maxProcs: 48, memMb: 29 * 1024 },
    sched: 'cores',
    tokens: 24,
  };
  const pyWork = 10_600_000;
  const pyPerCore = 0.85;
  const py = (id: string, needs?: string[], work = pyWork): SimGate => ({
    id,
    cores: 1,
    wallMs: work,
    perCore: pyPerCore,
    elastic: { min: 2, max: 'all' },
    needs,
  });
  // A run's wall at its fair share of two runs.
  const fair2 = pyWork / (pyPerCore * 12);
  const runOf = (out: ReturnType<typeof simulateRuns>, id: string): RunResult => {
    const r = out.runs.get(id);
    if (r === undefined) throw new Error(`sim: no run ${id}`);
    return r;
  };
  const sinceRegistered = (r: RunResult, start: number, gate: string): number =>
    (r.ends.get(gate) ?? Number.POSITIVE_INFINITY) - start;

  // 9. TWO PYTESTS STARTED 0.8 s APART split the tokens: both grants <= 12, both walls (from registering) within 1.2x the fair wall.
  const pair = simulateRuns(
    [
      { id: 'a', startMs: 0, gates: [py('a:pytest')] },
      { id: 'b', startMs: 800, gates: [py('b:pytest')] },
    ],
    leaseCfg
  );
  const pa = runOf(pair, 'a');
  const pb = runOf(pair, 'b');
  table.push(
    `two pytests 0.8 s apart: grants ${pa.grants.get('a:pytest')} and ${pb.grants.get('b:pytest')}, walls ${(sinceRegistered(pa, 0, 'a:pytest') / 1000).toFixed(0)} s and ${(sinceRegistered(pb, 800, 'b:pytest') / 1000).toFixed(0)} s (fair ${(fair2 / 1000).toFixed(0)} s)`
  );
  check(
    (pa.grants.get('a:pytest') ?? 99) <= 12 && (pb.grants.get('b:pytest') ?? 99) <= 12,
    `two pytests started together must each be granted <= 12 of 24, got ${pa.grants.get('a:pytest')} and ${pb.grants.get('b:pytest')}`
  );
  check(
    sinceRegistered(pa, 0, 'a:pytest') <= 1.2 * fair2 &&
      sinceRegistered(pb, 800, 'b:pytest') <= 1.2 * fair2,
    `both pytests must finish within 1.2x the fair wall ${fair2.toFixed(0)} ms, got ${sinceRegistered(pa, 0, 'a:pytest').toFixed(0)} and ${sinceRegistered(pb, 800, 'b:pytest').toFixed(0)}`
  );

  // 10. THE LOST RACE: b registers after a launched wide, so it holds with `lease` (never starts at `min` on no tokens), starts when a releases, and finishes within 2x the fair wall of registering.
  const race = simulateRuns(
    [
      { id: 'a', startMs: 0, gates: [py('a:pytest')] },
      { id: 'b', startMs: 10_000, gates: [py('b:pytest')] },
    ],
    leaseCfg
  );
  const ra = runOf(race, 'a');
  const rb = runOf(race, 'b');
  table.push(
    `lost race: a granted ${ra.grants.get('a:pytest')}, b held ${rb.leaseHeld.has('b:pytest')}, b started ${((rb.starts.get('b:pytest') ?? 0) / 1000).toFixed(0)} s at ${rb.grants.get('b:pytest')}, b wall ${(sinceRegistered(rb, 10_000, 'b:pytest') / 1000).toFixed(0)} s`
  );
  check(
    (ra.grants.get('a:pytest') ?? 0) > 12 && rb.leaseHeld.has('b:pytest'),
    `CONTROL: a lone run must launch wide and the late run must be held by the lease, got a ${ra.grants.get('a:pytest')}, b held ${rb.leaseHeld.has('b:pytest')}`
  );
  check(
    (rb.starts.get('b:pytest') ?? 0) >= (ra.ends.get('a:pytest') ?? 0) - EPS_MS &&
      sinceRegistered(rb, 10_000, 'b:pytest') <= 2 * fair2 &&
      rb.overLease.size === 0,
    `the late pytest must wait for the release and finish within 2x fair (${(2 * fair2).toFixed(0)} ms), started ${rb.starts.get('b:pytest')} at ${rb.grants.get('b:pytest')}, wall ${sinceRegistered(rb, 10_000, 'b:pytest').toFixed(0)} ms`
  );

  // 11. THE BOUND: a's holder takes every token and never ends; b's pytest still launches within its fair wall plus one poll, past the lease and recorded as such.
  const bound = simulateRuns(
    [
      { id: 'a', startMs: 0, gates: [{ id: 'a:holder', cores: 24, wallMs: 1e9 }] },
      { id: 'b', startMs: 1000, gates: [py('b:pytest')] },
    ],
    leaseCfg
  );
  const bb = runOf(bound, 'b');
  const boundStart = (bb.starts.get('b:pytest') ?? Number.POSITIVE_INFINITY) - 1000;
  table.push(
    `bound: b launched ${(boundStart / 1000).toFixed(1)} s after registering beside a holder that never ends (fair ${(fair2 / 1000).toFixed(1)} s), over ${JSON.stringify(bb.overLease.get('b:pytest'))}`
  );
  check(
    boundStart <= fair2 + LEASE_POLL_MS + EPS_MS && bb.overLease.has('b:pytest'),
    `a lease hold must end within its fair wall plus one poll (${(fair2 + LEASE_POLL_MS).toFixed(0)} ms) and record the over-grant, launched after ${boundStart.toFixed(0)} ms, over ${JSON.stringify(bb.overLease.get('b:pytest'))}`
  );

  // 12. THE SURVIVOR GROWS: b (started first) and a split the tokens; once b exits, a's next elastic gate is granted the whole pool.
  const grow = simulateRuns(
    [
      { id: 'b', startMs: 0, gates: [py('b:short', undefined, 2_000_000)] },
      {
        id: 'a',
        startMs: 500,
        gates: [py('a:first', undefined, 6_000_000), py('a:second', ['a:first'], 2_400_000)],
      },
    ],
    leaseCfg
  );
  const ga = runOf(grow, 'a');
  const gb = runOf(grow, 'b');
  table.push(
    `survivor: a:first ${ga.grants.get('a:first')}, b ${gb.grants.get('b:short')}, a:second after b exited ${ga.grants.get('a:second')}`
  );
  check(
    (ga.grants.get('a:first') ?? 99) <= 12 && gb.endMs < (ga.starts.get('a:second') ?? 0),
    `CONTROL: a's first gate must share with b, and b must exit before a's second gate, got ${ga.grants.get('a:first')}, b ended ${gb.endMs}`
  );
  check(
    ga.grants.get('a:second') === 24,
    `after its neighbour exits a run's next elastic gate must take the whole pool of 24, got ${ga.grants.get('a:second')}`
  );

  // 13. WORK CONSERVATION: b (passing first) holds two long one-core gates; a's 220 one-core gates are not capped at the share, so they fill the 22 tokens b leaves and the machine idles near zero while a runs.
  const conserve = simulateRuns(
    [
      {
        id: 'b',
        startMs: 0,
        gates: [
          { id: 'b:long-0', cores: 1, wallMs: 400_000 },
          { id: 'b:long-1', cores: 1, wallMs: 400_000 },
        ],
      },
      {
        id: 'a',
        startMs: 0,
        gates: Array.from({ length: 220 }, (_, i) => ({
          id: `a:one-${i}`,
          cores: 1,
          wallMs: 5000,
        })),
      },
    ],
    leaseCfg
  );
  const ca = runOf(conserve, 'a');
  table.push(
    `work conservation: a ended ${(ca.endMs / 1000).toFixed(1)} s, machine idle to then ${ca.idleToEndCoreS.toFixed(1)} core-s`
  );
  check(
    ca.idleToEndCoreS <= 0.05 * 24 * (ca.endMs / 1000),
    `fixed-width gates must fill what a neighbour leaves: idle ${ca.idleToEndCoreS.toFixed(1)} core-s over a's ${(ca.endMs / 1000).toFixed(1)} s`
  );

  // 14. THE MUTEX CHAIN (the 2026-10-06 tail): a pytest-shaped gate, three elastic vitest suites sharing one exclusive resource (865, 283 and 5 cpu-s, the first with a stale 173 s cache wall learned when it ran wide), and 150 one-core gates. The area rule gave each suite one core, so the three ran one after another for 1,153 s while everything else had finished. The floor must size the chain under the horizon; the control plants the
  // old one-wide grant (the floor off) and must fail the same checks, or they prove nothing.
  const chainMix = (): SimGate[] => [
    { id: 'big', cores: 1, wallMs: 7_000_000, elastic: { min: 2, max: 'all' } },
    {
      id: 'acct-server',
      cores: 1,
      wallMs: 865_000,
      elastic: { min: 1, max: 'all' },
      mutex: ['vitest'],
      est: { estMs: 173_000 },
    },
    {
      id: 'acct-web',
      cores: 1,
      wallMs: 283_000,
      elastic: { min: 1, max: 'all' },
      mutex: ['vitest'],
    },
    {
      id: 'acct-audit',
      cores: 1,
      wallMs: 5_000,
      elastic: { min: 1, max: 'all' },
      mutex: ['vitest'],
    },
    ...Array.from({ length: 150 }, (_, i) => ({ id: `c-${i}`, cores: 1, wallMs: 20_000 })),
  ];
  // The bound no schedule beats: all the work over the machine's cores.
  const chainBound = (7_000_000 + 1_153_000 + 3_000_000) / P24.machineCores;
  const floored = simulate(chainMix(), { ...P24, sched: 'cores', capCheck: cap });
  const unfloored = simulate(chainMix(), {
    ...P24,
    sched: 'cores',
    budget: { ...P24.budget, floor: false },
  });
  line('mutex chain, floor', floored);
  line('mutex chain, no floor (ctl)', unfloored);
  const chainEnd = (r: SimResult): number =>
    Math.max(...['acct-server', 'acct-web', 'acct-audit'].map((id) => r.ends.get(id) ?? 0));
  table.push(
    `mutex chain: acct-server granted ${floored.grants.get('acct-server')} at ${((floored.starts.get('acct-server') ?? 0) / 1000).toFixed(0)} s, chain ends ${(chainEnd(floored) / 1000).toFixed(0)} s; floor off: ${unfloored.grants.get('acct-server')}, ${(chainEnd(unfloored) / 1000).toFixed(0)} s (bound ${(chainBound / 1000).toFixed(0)} s)`
  );
  const chainHolds = (r: SimResult): boolean =>
    (r.grants.get('acct-server') ?? 0) >= 2 &&
    (r.starts.get('acct-server') ?? Number.POSITIVE_INFINITY) === 0 &&
    r.makespanMs <= 1.15 * chainBound;
  check(
    chainHolds(floored) && floored.capViolations === 0,
    `a critical mutex chain must start at t=0 at least two wide and the run end within 1.15x the work bound ${(chainBound / 1000).toFixed(0)} s: acct-server ${floored.grants.get('acct-server')} at ${floored.starts.get('acct-server')} ms, makespan ${(floored.makespanMs / 1000).toFixed(0)} s, cap violations ${floored.capViolations}`
  );
  check(
    !chainHolds(unfloored) && unfloored.grants.get('acct-server') === 1,
    `CONTROL: with the floor off the critical chain must be planted one wide and fail the same check, got ${unfloored.grants.get('acct-server')} wide, makespan ${(unfloored.makespanMs / 1000).toFixed(0)} s`
  );

  // 15. A LONE RUN IS NEVER HELD BY ITS OWN TOKENS: one run on a 24-token lease, a pytest-shaped gate beside 300 one-core gates. Before 2026-10-06 the settle reserved only `min`, the first wave took the rest, and the bounded B11 hold then treated this run's own one-core gates as a neighbour: pytest waited 209 s in the live run. It must start the moment the settle ends (the settle's own 2 s hold is the only wait), at least half the machine
  // wide. The control adds a real neighbour holding 20 tokens for 60 s, and the same gate must then miss its settle end, so the check can see a lease hold.
  const lonePy: SimGate = {
    id: 'solo:pytest',
    cores: 1,
    wallMs: 8_000_000,
    perCore: 0.8,
    elastic: { min: 2, max: 'all' },
  };
  const loneOnes = Array.from({ length: 300 }, (_, i) => ({
    id: `solo:one-${i}`,
    cores: 1,
    wallMs: 10_000,
  }));
  const solo = runOf(
    simulateRuns([{ id: 'solo', startMs: 0, gates: [lonePy, ...loneOnes] }], leaseCfg),
    'solo'
  );
  const crowded = runOf(
    simulateRuns(
      [
        { id: 'other', startMs: 0, gates: [{ id: 'other:holder', cores: 20, wallMs: 60_000 }] },
        { id: 'solo', startMs: 1000, gates: [lonePy, ...loneOnes] },
      ],
      leaseCfg
    ),
    'solo'
  );
  // Start relative to the run's own registration (the crowded run registers at 1 s).
  const settled = (r: RunResult, registered: number): boolean =>
    (r.starts.get('solo:pytest') ?? Number.POSITIVE_INFINITY) - registered <= SETTLE_MS + EPS_MS &&
    (r.grants.get('solo:pytest') ?? 0) >= 12;
  table.push(
    `lone run on a lease: pytest started ${((solo.starts.get('solo:pytest') ?? 0) / 1000).toFixed(1)} s at ${solo.grants.get('solo:pytest')}; beside a 20-token neighbour: ${(((crowded.starts.get('solo:pytest') ?? 0) - 1000) / 1000).toFixed(1)} s after registering at ${crowded.grants.get('solo:pytest')}`
  );
  check(
    settled(solo, 0),
    `a lone run's widest gate must start by the settle's end (${SETTLE_MS} ms) at >= 12 of 24, not wait on its own gates' tokens: started ${solo.starts.get('solo:pytest')} ms at ${solo.grants.get('solo:pytest')}`
  );
  check(
    !settled(crowded, 1000) && crowded.leaseHeld.has('solo:pytest'),
    `CONTROL: beside a neighbour holding 20 of 24 tokens the same gate must be held with \`lease\` past its settle, started ${crowded.starts.get('solo:pytest')} ms at ${crowded.grants.get('solo:pytest')}`
  );

  // 16. A GATE THAT DOES NOT SCALE GETS NO FLOOR AND KEEPS ITS MEASURED WALL: check:types:incremental's one per-core sample was 0.07, which models 558 s at three cores for a gate measured at 8-41 s. Planned at a 0.07 share, its planning wall must stay the cache's; the control at a 0.9 share must be re-planned from the work model, or the check cannot tell the two apart.
  const planned = (perCore: number): number => {
    const spec = specOf({ id: 'lazy', cores: 1, wallMs: 1, elastic: { min: 1, max: 'all' } });
    const plan = planAdmission([spec], {
      jobs: 22,
      durations: new Map([['lazy', 23_000]]),
      sched: 'cores',
      budget: P24.budget,
      costs: new Map([['lazy', { cpuMs: 120_000, wallMs: 8_000, perCore }]]),
    });
    return plan.byId.get('lazy')?.estMs ?? Number.NaN;
  };
  check(
    planned(0.07) === 23_000,
    `an elastic gate keeping 7% of each core busy must keep its cached 23 s planning wall, got ${planned(0.07)} ms`
  );
  check(
    planned(0.9) !== 23_000,
    `CONTROL: at a 0.9 share the planning wall must come from the work model, got ${planned(0.9)} ms`
  );

  // 17. THE WIDE GATE THAT GOES QUIET (ci:quick run 39, 2026-11-01: 735 s under 3 busy cores with 76 gates ready). A pytest-shaped gate is granted about half the machine by the area rule; its predicted wall is a quarter of its true one, and from there on it keeps 0.4 of a core busy. 300 gates a little wider than what the grant leaves free queue behind it, the way check:types and check:ci-format-scope did at 9 and 23 cores, with one gate as wide as the machine. The area rule balances the backlog against the wide gate's PREDICTED wall, so a queue that fits drains before the tail; what is left for the tail is what does not fit. On the budget alone everything held waits for the true end, and no gate ending means no pass at all. With the idle measured, the queue drains into it, while the machine-wide gate, which no reading can fit, still waits for its reservation.
  const quietTotal = 4_000_000;
  const quietEst = 1_000_000;
  const quietAt = quietEst / quietTotal;
  const tailMix = (
    phases: SimGate['phases'],
    opts: {
      prefix?: string;
      machineWide?: boolean;
      queued?: number;
      queuedCores?: number;
      queuedWallMs?: number;
      total?: number;
      est?: number;
    } = {}
  ): SimGate[] => {
    const prefix = opts.prefix ?? '';
    return [
      {
        id: `${prefix}wide`,
        cores: 1,
        wallMs: opts.total ?? quietTotal,
        elastic: { min: 2, max: 'all' },
        est: { cpuMs: opts.est ?? quietEst, wallMs: 200_000, estMs: 200_000, perCore: 1 },
        phases,
      },
      ...(opts.machineWide === false
        ? []
        : [{ id: `${prefix}machine-wide`, cores: 24, wallMs: 6_000 }]),
      ...Array.from({ length: opts.queued ?? 300 }, (_, i) => ({
        id: `${prefix}q-${i}`,
        cores: opts.queuedCores ?? 13,
        wallMs: opts.queuedWallMs ?? 200,
      })),
    ];
  };
  const lastQueued = (r: SimResult, prefix = ''): number =>
    Math.max(
      ...[...r.ends].filter(([id]) => id.startsWith(`${prefix}q-`)).map(([, end]) => end),
      0
    );
  const onLease = (gates: SimGate[], conserve: boolean): RunResult =>
    runOf(simulateRuns([{ id: 'r', startMs: 0, gates }], { ...leaseCfg, conserve }), 'r');
  const quietOff = onLease(tailMix([{ atFrac: quietAt, cores: 0.4 }]), false);
  const quietOn = onLease(tailMix([{ atFrac: quietAt, cores: 0.4 }]), true);
  const wideEnd = quietOff.ends.get('wide') ?? 0;
  const quietFrom = quietAt * wideEnd;
  table.push(
    `wide gate quiet from ${(quietFrom / 1000).toFixed(0)} s, ends ${(wideEnd / 1000).toFixed(0)} s, grant ${quietOff.grants.get('wide')}`
  );
  table.push(
    `  budget alone:   last queued gate ends ${(lastQueued(quietOff) / 1000).toFixed(0)} s, makespan ${(quietOff.makespanMs / 1000).toFixed(0)} s, idle ${quietOff.idleCoreS.toFixed(0)} core-s, borrowed ${quietOff.borrowed.size}`
  );
  table.push(
    `  idle measured:  last queued gate ends ${(lastQueued(quietOn) / 1000).toFixed(0)} s, makespan ${(quietOn.makespanMs / 1000).toFixed(0)} s, idle ${quietOn.idleCoreS.toFixed(0)} core-s, borrowed ${quietOn.borrowed.size}, peak demand ${quietOn.peakDemand.toFixed(1)}`
  );
  check(
    lastQueued(quietOff) >= wideEnd - EPS_MS && quietOff.borrowed.size === 0,
    `CONTROL: on the budget alone the queue must wait out the quiet wide gate, last queued end ${lastQueued(quietOff).toFixed(0)} ms against its end ${wideEnd.toFixed(0)} ms`
  );
  check(
    lastQueued(quietOn) <= quietFrom + 90_000,
    `a held queue must drain into a quiet wide gate's real idle within 90 s of it going quiet at ${quietFrom.toFixed(0)} ms, last queued end ${lastQueued(quietOn).toFixed(0)} ms`
  );
  check(
    quietOn.grants.get('wide') === quietOff.grants.get('wide') &&
      (quietOn.starts.get('machine-wide') ?? 0) >= (quietOn.ends.get('wide') ?? 0) - EPS_MS,
    `borrowing must not change the wide grant, and a gate wider than the reading must still wait for its reservation: grants ${quietOff.grants.get('wide')} and ${quietOn.grants.get('wide')}, machine-wide started ${quietOn.starts.get('machine-wide')} ms`
  );
  check(
    quietOn.peakDemand <= P24.machineCores + 1e-6 && quietOn.overCoreS === 0,
    `a borrow into a gate that stays quiet must never oversubscribe, peak demand ${quietOn.peakDemand.toFixed(2)}, over ${quietOn.overCoreS.toFixed(1)} core-s`
  );

  // 18. CONTROL: THE SAME GATE REALLY BUSY. The budget's picture is true, so the reading finds at most what the budget left, and nothing beyond the machine is ever started. The wide gate must not lose wall to a borrow.
  const busyOff = onLease(tailMix(undefined), false);
  const busyOn = onLease(tailMix(undefined), true);
  table.push(
    `  really busy:    wide ends ${((busyOn.ends.get('wide') ?? 0) / 1000).toFixed(0)} s (budget alone ${((busyOff.ends.get('wide') ?? 0) / 1000).toFixed(0)} s), peak demand ${busyOn.peakDemand.toFixed(1)}, over ${busyOn.overCoreS.toFixed(1)} core-s, borrowed ${busyOn.borrowed.size}`
  );
  check(
    busyOn.peakDemand <= P24.machineCores + 1e-6 && busyOn.overCoreS === 0,
    `a wide gate that really is busy must not be oversubscribed, peak demand ${busyOn.peakDemand.toFixed(2)} on ${P24.machineCores} cores, over ${busyOn.overCoreS.toFixed(1)} core-s`
  );
  check(
    (busyOn.ends.get('wide') ?? 0) <= (busyOff.ends.get('wide') ?? 0) + EPS_MS,
    `borrowing beside a busy wide gate must not slow it, ${busyOn.ends.get('wide')} against ${busyOff.ends.get('wide')} ms`
  );

  // The same again with a queue of one-core gates, which the reading could admit: past the wide gate's predicted end the stale reservation holds them, and what they may then borrow is the cores really idle, so the machine fills and stops there.
  const busyOnes = onLease(
    tailMix(undefined, { machineWide: true, queued: 2000, queuedCores: 1, queuedWallMs: 500 }),
    true
  );
  table.push(
    `  busy, one-core: borrowed ${busyOnes.borrowed.size}, peak demand ${busyOnes.peakDemand.toFixed(1)}, over ${busyOnes.overCoreS.toFixed(1)} core-s`
  );
  check(
    busyOnes.peakDemand <= P24.machineCores + 1e-6 && busyOnes.overCoreS === 0,
    `one-core gates borrowing beside a busy wide gate must stop at the machine, peak demand ${busyOnes.peakDemand.toFixed(2)}, over ${busyOnes.overCoreS.toFixed(1)} core-s`
  );

  // 19. THE WAKE: the wide gate goes quiet for 15 s, long enough for the reading to settle and the queue to borrow, then wakes with the borrowers still running. The oversubscription this causes is the rule's whole debt, so it is bounded by what could be borrowed at once for as long as a borrower may run, and the wide gate pays only that.
  const wakeTotal = 80_000_000;
  const wakeEst = 40_000_000;
  const wakeFrom = wakeEst / wakeTotal;
  const wakeMix = (): SimGate[] =>
    tailMix(
      [
        { atFrac: wakeFrom, cores: 0.4 },
        { atFrac: wakeFrom + 15_000 / 4_210_000, cores: 19 },
      ],
      {
        machineWide: false,
        queued: 120,
        queuedCores: 2,
        queuedWallMs: 40_000,
        total: wakeTotal,
        est: wakeEst,
      }
    );
  const wakeOff = onLease(wakeMix(), false);
  const wakeOn = onLease(wakeMix(), true);
  const overBound = ((P24.machineCores - RECLAIM_HEADROOM) * BORROW_WALL_MS) / 1000;
  table.push(
    `  wakes mid-tail: wide ends ${((wakeOn.ends.get('wide') ?? 0) / 1000).toFixed(0)} s (budget alone ${((wakeOff.ends.get('wide') ?? 0) / 1000).toFixed(0)} s), peak demand ${wakeOn.peakDemand.toFixed(1)}, over ${wakeOn.overCoreS.toFixed(0)} core-s (bound ${overBound.toFixed(0)}), borrowed ${wakeOn.borrowed.size}`
  );
  check(
    wakeOn.overCoreS > 0 && wakeOn.borrowed.size > 0,
    `CONTROL: the wake case must really catch borrowers running, or its bound proves nothing: over ${wakeOn.overCoreS.toFixed(1)} core-s, borrowed ${wakeOn.borrowed.size}`
  );
  check(
    wakeOn.overCoreS <= overBound,
    `a wake must cost at most the borrowed cores for one borrow wall, ${overBound.toFixed(0)} core-s, got ${wakeOn.overCoreS.toFixed(1)}`
  );
  check(
    (wakeOn.ends.get('wide') ?? 0) <= (wakeOff.ends.get('wide') ?? 0) + BORROW_WALL_MS,
    `a wake must delay the wide gate by at most one borrow wall, ${wakeOn.ends.get('wide')} against ${wakeOff.ends.get('wide')} ms`
  );

  // 20. A RESERVATION IS STILL HONOURED: a fixed d-20 gate holds the budget and goes quiet; a d-20 gate behind it reserves its end, and 30 one-core gates of 45 s are ready. A borrow holds no budget, so the reserved gate starts the moment the holder ends, the same moment as with no borrowing at all. The one-core gates are predicted to run past that moment, so past the 4 cores the reservation leaves spare the budget alone keeps them waiting.
  const reservedMix = (): SimGate[] => [
    { id: 'holder', cores: 20, wallMs: 40_000, phases: [{ atFrac: 0.05, cores: 0.5 }] },
    { id: 'reserved', cores: 20, wallMs: 10_000 },
    ...Array.from({ length: 30 }, (_, i) => ({ id: `res-${i}`, cores: 1, wallMs: 45_000 })),
  ];
  const resOff = onLease(reservedMix(), false);
  const resOn = onLease(reservedMix(), true);
  table.push(
    `  reservation:    reserved gate starts ${((resOn.starts.get('reserved') ?? 0) / 1000).toFixed(1)} s (budget alone ${((resOff.starts.get('reserved') ?? 0) / 1000).toFixed(1)} s), borrowed ${resOn.borrowed.size}, makespan ${(resOn.makespanMs / 1000).toFixed(0)} s (budget alone ${(resOff.makespanMs / 1000).toFixed(0)} s)`
  );
  check(
    (resOn.starts.get('reserved') ?? 0) <= (resOff.starts.get('reserved') ?? 0) + EPS_MS &&
      resOn.borrowed.size > 0,
    `borrowers must not move a reserved start: ${resOn.starts.get('reserved')} against ${resOff.starts.get('reserved')} ms, borrowed ${resOn.borrowed.size}`
  );

  // 21. TWO RUNS, ONE IDLE: each has a quiet wide gate and a queue. Each reads the same machine, so each may spend only its half (the pure line in 22 holds the split), and a borrow takes no token, so the neighbour's grant and its budget are what they were. What the lease does with two runs on its own is unchanged, including the over-lease the bounded hold already admits; the borrow may add nothing to it.
  const twoMix = (prefix: string): SimGate[] =>
    tailMix([{ atFrac: 0.05, cores: 0.4 }], { prefix, machineWide: false, queuedCores: 6 });
  const twoRuns = (conserve: boolean): { a: RunResult; b: RunResult } => {
    const out = simulateRuns(
      [
        { id: 'a', startMs: 0, gates: twoMix('a:') },
        { id: 'b', startMs: 0, gates: twoMix('b:') },
      ],
      { ...leaseCfg, conserve }
    );
    return { a: runOf(out, 'a'), b: runOf(out, 'b') };
  };
  const twoOff = twoRuns(false);
  const twoOn = twoRuns(true);
  table.push(
    `  two runs:       grants ${twoOn.a.grants.get('a:wide')} and ${twoOn.b.grants.get('b:wide')}, b's queue ends ${(lastQueued(twoOn.b, 'b:') / 1000).toFixed(0)} s (budget alone ${(lastQueued(twoOff.b, 'b:') / 1000).toFixed(0)} s), borrowed ${twoOn.a.borrowed.size} and ${twoOn.b.borrowed.size}, peak demand ${twoOn.a.peakDemand.toFixed(1)} (budget alone ${twoOff.a.peakDemand.toFixed(1)}), over ${twoOn.a.overCoreS.toFixed(1)} core-s (budget alone ${twoOff.a.overCoreS.toFixed(1)})`
  );
  check(
    twoOn.a.grants.get('a:wide') === twoOff.a.grants.get('a:wide') &&
      twoOn.b.grants.get('b:wide') === twoOff.b.grants.get('b:wide'),
    "a borrow takes no token, so neither run's grant may move"
  );
  check(
    twoOn.b.borrowed.size > 0 && lastQueued(twoOn.b, 'b:') < lastQueued(twoOff.b, 'b:'),
    `the run the lease starves must borrow and finish sooner: borrowed ${twoOn.b.borrowed.size}, queue end ${lastQueued(twoOn.b, 'b:')} against ${lastQueued(twoOff.b, 'b:')} ms`
  );
  check(
    twoOn.a.peakDemand <= twoOff.a.peakDemand + 1e-6 &&
      twoOn.a.overCoreS <= twoOff.a.overCoreS + 1e-6,
    `two runs borrowing must add no oversubscription: peak ${twoOn.a.peakDemand.toFixed(2)} against ${twoOff.a.peakDemand.toFixed(2)}, over ${twoOn.a.overCoreS.toFixed(2)} against ${twoOff.a.overCoreS.toFixed(2)} core-s`
  );

  // 22. THE READING, PURE. Each line is a way the figure could lie.
  const steady =
    (idle: number): ((from: number, to: number) => number) =>
    (from, to) =>
      idle * (to - from);
  const T = 100_000;
  check(
    reclaimableCores(T, steady(20), [], 1) === 19,
    `20 idle cores less the headroom must read 19, got ${reclaimableCores(T, steady(20), [], 1)}`
  );
  check(reclaimableCores(T, () => undefined, [], 1) === 0, 'no reading must never read as idle');
  check(
    reclaimableCores(T, steady(20), [], 2) === 9,
    `two runs split 20 idle into 10, less the headroom 9, got ${reclaimableCores(T, steady(20), [], 2)}`
  );
  check(
    reclaimableCores(T, (from, to) => (to > T - 2_000 ? 2 : 20) * (to - from), [], 1) === 1,
    `one busy bucket must be the whole figure: the idle has to hold across the window, got ${reclaimableCores(T, (from, to) => (to > T - 2_000 ? 2 : 20) * (to - from), [], 1)}`
  );
  check(
    reclaimableCores(T, steady(15), [{ from: T - 60_000, cores: 5 }], 1) === 14,
    `a borrower running through the window is added back and then subtracted, reading the 15 really idle less the headroom, got ${reclaimableCores(T, steady(15), [{ from: T - 60_000, cores: 5 }], 1)}`
  );
  check(
    reclaimableCores(T, steady(0), [{ from: T - 60_000, to: T - 50_000, cores: 5 }], 1) === 0,
    'a borrower that ended before the window must add nothing back'
  );

  // 23. WHO MAY BORROW, PURE: a long gate stays on the budget; a claim held elsewhere, the process count and memory all still refuse.
  const cand = (id: string, over: Partial<Candidate> = {}): Candidate => ({
    id,
    slots: 1,
    cores: 1,
    memMb: 100,
    estMs: 5_000,
    heavy: false,
    mutex: [],
    reads: [],
    cpuMs: 5_000,
    ...over,
  });
  const fullBudget = { cores: 24, epsilon: 0, maxProcs: 48, memMb: 10_000 };
  const holderGate = {
    gate: cand('holder', { cores: 24, grant: 24, mutex: ['res'] }),
    endsAt: 1_000_000,
  };
  const admitWith = (
    ready: Candidate[],
    borrowable: number | undefined,
    budget = fullBudget
  ): Set<string> =>
    new Set(
      admit(
        ready,
        [holderGate],
        { sched: 'cores', jobs: 24, heavyLimit: 5, budget, borrowable },
        0
      ).launch.map((g) => g.id)
    );
  check(
    admitWith([cand('short')], undefined).size === 0,
    'CONTROL: with no reading a full budget must still hold a one-core gate'
  );
  check(admitWith([cand('short')], 5).has('short'), 'a short gate must borrow from measured idle');
  check(
    !admitWith([cand('long', { estMs: BORROW_WALL_MS + 1 })], 20).has('long'),
    'a gate predicted past the borrow wall must stay on the budget'
  );
  check(
    !admitWith([cand('narrow', { cores: 4 })], 3).has('narrow'),
    'a gate wider than the reading must not borrow'
  );
  check(
    admitWith([cand('a'), cand('b'), cand('c')], 2).size === 2,
    'a pass must spend the reading once, not once per gate'
  );
  check(
    !admitWith([cand('claim', { reads: ['res'] })], 20).has('claim'),
    "a borrower must still respect a running gate's exclusive claim"
  );
  check(
    !admitWith([cand('procs')], 20, { ...fullBudget, maxProcs: 1 }).has('procs'),
    'a borrower must still count against K'
  );
  check(
    !admitWith([cand('fat', { memMb: 20_000 })], 20).has('fat'),
    'a borrower must still count against M'
  );
  const borrowedLaunch = admit(
    [cand('short', { cores: 3 })],
    [holderGate],
    { sched: 'cores', jobs: 24, heavyLimit: 5, budget: fullBudget, borrowable: 5 },
    0
  ).launch[0];
  check(
    borrowedLaunch?.cores === 0 && borrowedLaunch?.grant === 3 && borrowedLaunch?.borrowed === 3,
    `a borrow holds no budget and its process is told its real width: ${JSON.stringify(borrowedLaunch)}`
  );

  return { failures, assertions, table };
}

/**
 * THE BORROW THROUGH THE REAL POOL LOOP (pool.ts reclaimableCores). A one-core gate behind a full budget: nothing ends until it starts, or a timer gives up, so only the pool's own idle poll can launch it. schedulerSelftest drives admit() and cannot see that wake. The control has no reading, and the same gate waits out the whole wide gate. Returns failures.
 */
export async function reclaimLoopSelftest(): Promise<string[]> {
  const failures: string[] = [];
  const specs: GateSpec[] = [
    specOf({ id: 'quiet-wide', cores: 4, wallMs: 60_000 }),
    specOf({ id: 'quiet-small', cores: 1, wallMs: 1_000 }),
  ];
  const drive = async (
    idleCoreMs: IdleReader | undefined
  ): Promise<{ order: string[]; told: Map<string, number>; borrowed: number | undefined }> => {
    const order: string[] = [];
    const told = new Map<string, number>();
    let release: () => void = () => {};
    const smallStarted = new Promise<void>((resolve) => {
      release = resolve;
    });
    const results = await runPool(specs, {
      jobs: 4,
      heavyLimit: 1,
      failFast: false,
      durations: new Map([
        ['quiet-wide', 60_000],
        ['quiet-small', 1_000],
      ]),
      sched: 'cores',
      budget: { cores: 4, epsilon: 0, maxProcs: 8, memMb: 64 * 1024 },
      costs: new Map<string, GateCost>([
        ['quiet-wide', { cpuMs: 240_000, wallMs: 60_000 }],
        ['quiet-small', { cpuMs: 1_000, wallMs: 1_000 }],
      ]),
      idleCoreMs,
      reclaimPollMs: 10,
      exec: async (spec, grant) => {
        order.push(spec.id);
        told.set(spec.id, grant.cores);
        if (spec.id === 'quiet-small') release();
        else
          await Promise.race([
            smallStarted,
            new Promise<void>((resolve) => setTimeout(resolve, 300)),
          ]);
        order.push(`${spec.id}:end`);
        return { code: 0, stdout: '', stderr: '', ms: 1 };
      },
    });
    return {
      order,
      told,
      borrowed: results.find((r) => r.id === 'quiet-small')?.borrowed,
    };
  };
  const on = await drive((from, to) => 3 * (to - from));
  if (
    !(
      on.order.indexOf('quiet-small') < on.order.indexOf('quiet-wide:end') &&
      on.told.get('quiet-small') === 1 &&
      on.borrowed === 1
    )
  )
    failures.push(
      `the pool's idle poll must start a held gate in measured idle while the wide gate runs, told 1 core and recorded as borrowed, got ${JSON.stringify(on.order)} ${JSON.stringify([...on.told])} borrowed ${on.borrowed}`
    );
  const off = await drive(undefined);
  if (
    !(off.order.indexOf('quiet-small') > off.order.indexOf('quiet-wide:end')) ||
    off.borrowed !== undefined
  )
    failures.push(
      `CONTROL: with no idle reading the same gate must wait out the wide gate, got ${JSON.stringify(off.order)}`
    );
  // The reading itself: half idle of 24 between two ticks; a window older than the first tick, and one past a stopped sampler, must both read as nothing.
  const ticks: CpuTick[] = [
    { t: 1000, busy: 0, idle: 0, iowait: 0, total: 0 },
    { t: 3000, busy: 50, idle: 50, iowait: 0, total: 100 },
  ];
  if (idleCoreMsBetween(ticks, 24, 1000, 3000) !== 12 * 2000)
    failures.push(
      `half idle on 24 cores over 2 s must read 24,000 core-ms, got ${idleCoreMsBetween(ticks, 24, 1000, 3000)}`
    );
  if (idleCoreMsBetween(ticks, 24, 500, 3000) !== undefined)
    failures.push('a window older than the first tick must read as no reading');
  if (idleCoreMsBetween(ticks, 24, 2000, 9000) !== undefined)
    failures.push('a window past a stopped sampler must read as no reading');
  return failures;
}

if (isEntryPoint(import.meta.filename)) {
  const { failures, assertions, table } = schedulerSelftest();
  const loop = await reclaimLoopSelftest();
  for (const row of table) process.stdout.write(`${row}\n`);
  for (const f of [...failures, ...loop]) process.stderr.write(`FAIL: ${f}\n`);
  process.stdout.write(
    `sim: ${assertions - failures.length}/${assertions} assertions hold, pool loop ${loop.length === 0 ? 'holds' : 'FAILS'}\n`
  );
  process.exitCode = failures.length + loop.length > 0 ? 1 : 0;
}

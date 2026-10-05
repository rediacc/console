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
import { fileURLToPath } from 'node:url';
import type { GateSpec } from './manifest';
import { admit, type CoreBudget, type GateCost, planAdmission, type Sched } from './pool';

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
  heavy?: boolean;
  mutex?: string[];
  /** Default true: the scheduler sees cpu = cores x wall, wall and memMb as measured. False: it sees nothing. */
  measured?: boolean;
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
    ci: {
      kind: 'local-only',
      blocker: 'BLOCKER: synthetic scheduler-simulator fixture, never part of the real gate set',
    },
  };
}

function simulate(gates: readonly SimGate[], cfg: SimConfig): SimResult {
  const specs = gates.map(specOf);
  const truth = new Map(gates.map((g) => [g.id, g]));
  const costs = new Map<string, GateCost>();
  const durations = new Map<string, number>();
  for (const g of gates) {
    if (g.measured === false) continue;
    costs.set(g.id, {
      cpuMs: g.cores * g.wallMs,
      wallMs: g.wallMs,
      rssMb: g.memMb ?? 512,
      perCore: g.elastic !== undefined ? 1 : undefined,
    });
    durations.set(g.id, g.wallMs);
  }
  const { byId, rank } = planAdmission(specs, {
    jobs: cfg.jobs,
    durations,
    sched: cfg.sched,
    budget: cfg.budget,
    costs,
  });
  const cand = (id: string) => {
    const c = byId.get(id);
    if (c === undefined) throw new Error(`sim: no candidate for ${id}`);
    return c;
  };

  const starts = new Map<string, number>();
  const ends = new Map<string, number>();
  const readyAt = new Map<string, number>();
  // Remaining work of each running gate, in ms of full-speed wall, and the candidate admit() launched it as (an elastic gate's carries its grant).
  const running = new Map<string, number>();
  const launched = new Map<string, ReturnType<typeof cand>>();
  const grants = new Map<string, number>();
  // True width while running: the grant for an elastic gate, the declared d otherwise.
  const width = (id: string): number =>
    truth.get(id)?.elastic !== undefined ? (grants.get(id) ?? 1) : (truth.get(id)?.cores ?? 0);
  let t = 0;
  let busy = 0;
  let capViolations = 0;

  while (ends.size < gates.length) {
    const ready = specs
      .filter((s) => !starts.has(s.id) && (s.needs ?? []).every((n) => ends.has(n)))
      .sort(rank);
    for (const s of ready) if (!readyAt.has(s.id)) readyAt.set(s.id, t);
    let backlogCpuMs = 0;
    for (const s of specs) if (!starts.has(s.id)) backlogCpuMs += cand(s.id).cpuMs;
    const pass = admit(
      ready.map((s) => cand(s.id)),
      [...running.keys()].map((id) => {
        const g = launched.get(id) ?? cand(id);
        return { gate: g, endsAt: (starts.get(id) ?? 0) + g.estMs };
      }),
      {
        sched: cfg.sched,
        jobs: cfg.jobs,
        heavyLimit: cfg.heavyLimit,
        budget: cfg.budget,
        backlogCpuMs,
      },
      t
    );
    for (const g of pass.launch) {
      starts.set(g.id, t);
      launched.set(g.id, g);
      grants.set(g.id, g.grant ?? 1);
      const tg = truth.get(g.id);
      running.set(
        g.id,
        tg?.elastic !== undefined
          ? (tg.cores * tg.wallMs) / Math.max(1, g.grant ?? 1)
          : (tg?.wallMs ?? 0)
      );
    }
    if (cfg.sched === 'cores' && cfg.capCheck !== undefined && running.size > 1) {
      let budgeted = 0;
      for (const id of running.keys()) budgeted += (launched.get(id) ?? cand(id)).cores;
      if (budgeted > cfg.capCheck + 1e-9) capViolations += 1;
    }
    if (running.size === 0) throw new Error(`sim: pool stalled at ${t} ms`);

    let demand = 0;
    for (const id of running.keys()) demand += width(id);
    const rate = Math.min(1, cfg.machineCores / demand);
    let step = Number.POSITIVE_INFINITY;
    for (const left of running.values()) step = Math.min(step, left / rate);
    t += step;
    busy += Math.min(cfg.machineCores, demand) * step;
    for (const [id, left] of running) {
      const rest = left - step * rate;
      if (rest <= EPS_MS) {
        running.delete(id);
        ends.set(id, t);
      } else running.set(id, rest);
    }
  }
  return {
    makespanMs: t,
    idleCoreS: (cfg.machineCores * t - busy) / 1000,
    starts,
    ends,
    readyAt,
    capViolations,
    grants,
  };
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

  return { failures, assertions, table };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { failures, assertions, table } = schedulerSelftest();
  for (const row of table) process.stdout.write(`${row}\n`);
  for (const f of failures) process.stderr.write(`FAIL: ${f}\n`);
  process.stdout.write(`sim: ${assertions - failures.length}/${assertions} assertions hold\n`);
  process.exitCode = failures.length > 0 ? 1 : 0;
}

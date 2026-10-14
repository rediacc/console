/**
 * The learned scheduler's end-to-end controls (agent/plans/PLAN-gate-scheduling-learned.md T7, T8, T9), run from run.ts --selftest. Each module carries its own unit controls (rank.ts rankSelftest, ledger.ts ledgerSelftest, report.ts streamSelftest); this file holds the three that cross modules:
 *
 *   T7  THE PROPERTY: over every archived receipt timeline in .ci/cache/receipts/ (read-only) and seeded synthetic mixes, the order the runner would use is never slower in simulation than today's by more than WALL_SLACK_MS. CONTROL: with pinning disabled, at least one mix is slower, so the safety check is what holds the property and not the mixes.
 *   T8  THE STAGE STOP, through a real runner process: a planted preflight red stops the run with exit 3, kills the long gate, streams RED / PREFLIGHT / STOPPED, writes run-end `receipt: none` and leaves the receipt file byte-identical. CONTROL: the same run without the flag goes to the end.
 *   T9  NO GATE ID in ledger.ts or rank.ts. CONTROL: a planted id must be found.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { processAlive } from './exec';
import { GATES, type GateSpec } from './manifest';
import { type CoreBudget, type GateCost, planAdmission } from './pool';
import { type ModelV1, planRanking, type RankingDecision, WALL_SLACK_MS } from './rank';
import { predictMakespan } from './sim';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');

/** The archived receipts the property test replays: the newest by mtime. Each is about a second of simulation per order tried, and the newest carry this machine's current gate set; older ones add runtime, not shapes. */
const ARCHIVE_SAMPLE = 12;

/** The seeded mixes T7 always replays. */
const SEEDED_MIXES = [20261008, 7, 42];

/** This machine's shape, as sim.ts P24 states it: 24 cores, C 23, K 46, M 29 GB. */
const P24 = { machineCores: 24, jobs: 22, heavyLimit: 5 };
const P24_BUDGET: CoreBudget = { cores: 23, epsilon: 0.1, maxProcs: 46, memMb: 29 * 1024 };

function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

/** One schedulable mix: the specs, the planning numbers the runner would have, and which gates went red. */
interface Mix {
  name: string;
  specs: GateSpec[];
  durations: Map<string, number>;
  costs: Map<string, GateCost>;
  failed: Set<string>;
}

function fixtureSpec(id: string, extra: Partial<GateSpec> = {}): GateSpec {
  return {
    id,
    run: 'true',
    gate: true,
    leaves: [],
    ci: {
      kind: 'local-only',
      blocker: 'BLOCKER: synthetic property-test fixture, never part of the real gate set',
    },
    ...extra,
  };
}

/** A receipt's timeline as a mix: every launched gate at its measured wall and granted width, with the manifest's needs, mutex and elastic range where the gate still exists. */
function mixFromReceipt(file: string): Mix | undefined {
  let doc: {
    timeline?: Record<string, { start: number; end: number; cores?: number }>;
    failed?: string[];
  };
  try {
    doc = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return undefined;
  }
  const tl = doc.timeline;
  if (tl === undefined || Object.keys(tl).length === 0) return undefined;
  const byId = new Map(GATES.map((g) => [g.id, g]));
  const ids = new Set(Object.keys(tl));
  const specs: GateSpec[] = [];
  const durations = new Map<string, number>();
  const costs = new Map<string, GateCost>();
  for (const [id, t] of Object.entries(tl)) {
    const real = byId.get(id);
    specs.push(
      fixtureSpec(id, {
        gate: real?.gate ?? true,
        needs: (real?.needs ?? []).filter((n) => ids.has(n)),
        mutex: real?.mutex,
        cores: real?.cores,
      })
    );
    const wall = Math.max(1, t.end - t.start);
    const width = Math.max(1, t.cores ?? 1);
    durations.set(id, wall);
    costs.set(id, {
      wallMs: wall,
      cpuMs: wall * width,
      perCore: real?.cores !== undefined ? 1 : undefined,
    });
  }
  return {
    name: path.basename(file).slice(0, 9),
    specs,
    durations,
    costs,
    failed: new Set(doc.failed ?? []),
  };
}

/** A seeded mix in the 2026-10-08 shape: two long gates (one elastic), a mutex chain, a build with dependents, and many short gates, a few of them hot. */
function seededMix(seed: number): Mix {
  const r = rng(seed);
  const between = (lo: number, hi: number): number => Math.round(lo + r() * (hi - lo));
  const specs: GateSpec[] = [];
  const durations = new Map<string, number>();
  const costs = new Map<string, GateCost>();
  const failed = new Set<string>();
  const add = (id: string, wall: number, width: number, extra: Partial<GateSpec> = {}): void => {
    specs.push(fixtureSpec(id, extra));
    durations.set(id, wall);
    costs.set(id, {
      wallMs: wall,
      cpuMs: wall * width,
      perCore: extra.cores !== undefined ? 1 : undefined,
    });
  };
  add('mix:long-elastic', between(600_000, 900_000), 12, { cores: { min: 2, max: 'all' } });
  add('mix:long', between(300_000, 450_000), 1);
  for (let i = 0; i < 3; i += 1)
    add(`mix:chain-${i}`, between(60_000, 200_000), 1, { mutex: ['fx-chain'] });
  add('mix:build', between(30_000, 70_000), 4, { gate: false });
  for (let i = 0; i < 10; i += 1)
    add(`mix:dep-${i}`, between(5_000, 40_000), 1, { needs: ['mix:build'] });
  for (let i = 0; i < 150; i += 1) {
    const id = `mix:short-${i}`;
    add(id, between(500, 60_000), r() < 0.2 ? 2 : 1);
    if (r() < 0.04) failed.add(id);
  }
  return { name: `seed ${seed}`, specs, durations, costs, failed };
}

/** A model over a mix: the gates that went red hot, the rest cool, a few short ones in the clock set. Deterministic per mix. */
function modelFor(mix: Mix, seed: number): ModelV1 {
  const r = rng(seed);
  const gates: ModelV1['gates'] = {};
  const clock: string[] = [];
  for (const s of mix.specs) {
    const wall = mix.durations.get(s.id) ?? 5000;
    gates[s.id] = {
      obs: 20,
      p_red: mix.failed.has(s.id) ? 0.5 : r() * 0.05,
      p_red_by_class: {},
      wall_ms: wall,
      class: 'real',
    };
    if (s.gate && wall < 30_000 && clock.length < 3 && r() < 0.05) clock.push(s.id);
  }
  return {
    v: 1,
    built_at: 'fixture',
    cold_start: { on: false, reason: '' },
    runs: 20,
    gates,
    clock_set: clock,
    clusters: [],
    associations: {},
  };
}

function decide(
  mix: Mix,
  model: ModelV1,
  opts: { iterations?: number; longPins?: boolean } = {}
): RankingDecision {
  const ids = new Set(mix.specs.map((s) => s.id));
  const plan = {
    ...P24,
    durations: mix.durations,
    sched: 'cores' as const,
    budget: P24_BUDGET,
    costs: mix.costs,
  };
  return planRanking(
    {
      model,
      ids: mix.specs.map((s) => s.id),
      gates: new Set(mix.specs.filter((s) => s.gate).map((s) => s.id)),
      needs: new Map(mix.specs.map((s) => [s.id, (s.needs ?? []).filter((n) => ids.has(n))])),
      mutex: new Map(mix.specs.map((s) => [s.id, s.mutex ?? []])),
      wallMs: (id) => mix.durations.get(id),
      width: (id) => {
        const c = mix.costs.get(id);
        return c?.cpuMs !== undefined && c.wallMs !== undefined
          ? Math.max(1, c.cpuMs / c.wallMs)
          : 1;
      },
      cores: P24_BUDGET.cores,
      classes: [],
    },
    (order) => predictMakespan(mix.specs, { ...plan, order }, P24.machineCores),
    opts
  );
}

/** Every lock id that occurs in `text` as a whole token. */
// A gate id with a colon (`check:x`) cannot be an English word, so any whole-token use names it. A colon-less id (the `pins` entry point) is also an ordinary word, so only a quoted use (a string literal naming it) counts as naming the gate.
function gateIdsIn(text: string, ids: readonly string[]): string[] {
  const esc = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return ids.filter((id) =>
    id.includes(':')
      ? new RegExp(`(?<![A-Za-z0-9:_.-])${esc(id)}(?![A-Za-z0-9:_-])`).test(text)
      : new RegExp(`['"\`]${esc(id)}['"\`]`).test(text)
  );
}

export async function learnedSelftest(): Promise<{
  failures: string[];
  assertions: number;
  table: string[];
}> {
  const failures: string[] = [];
  const table: string[] = [];
  let assertions = 0;
  const check = (ok: boolean, message: string): void => {
    assertions += 1;
    if (!ok) failures.push(message);
  };

  // T9: NO GATE ID IN THE SCHEDULER'S LEARNED HALF.
  {
    let ids: string[] = [];
    try {
      ids = (
        JSON.parse(fs.readFileSync(path.join(HERE, 'gates.lock.json'), 'utf8')) as { id: string }[]
      ).map((e) => e.id);
    } catch {
      ids = [];
    }
    check(ids.length >= 100, `T9 must read the lock's ids to mean anything, read ${ids.length}`);
    for (const file of ['ledger.ts', 'rank.ts']) {
      const text = fs.readFileSync(path.join(HERE, file), 'utf8');
      check(text.length > 1000, `T9: ${file} must be read whole, got ${text.length} bytes`);
      const found = gateIdsIn(text, ids);
      check(
        found.length === 0,
        `T9: ${file} names gate id(s) ${found.join(', ')}; derive them from model.json or the lock instead`
      );
      const colonless = ids.find((id) => !id.includes(':'));
      if (colonless) {
        check(
          gateIdsIn(`${text}\nconst g = '${colonless}';\n`, ids).includes(colonless),
          `T9 CONTROL: the colon-less id ${colonless} quoted in ${file} must be found`
        );
        check(
          !gateIdsIn(`// five ${colonless} and the order\n`, ids).includes(colonless),
          `T9 CONTROL: the colon-less id ${colonless} as a plain word must not count as a gate name`
        );
      }
      const planted = gateIdsIn(`${text}\n// ${ids[ids.length - 1]}\n`, ids);
      check(
        planted.includes(ids[ids.length - 1] ?? ''),
        `T9 CONTROL: an id planted into ${file} must be found, found ${planted.join(', ')}`
      );
    }
    check(
      gateIdsIn('x check:types:incremental y', [
        'check:types',
        'check:types:incremental',
      ]).join() === 'check:types:incremental',
      'T9 CONTROL: an id is matched as a whole token, so a longer id does not report its prefix'
    );
  }

  // THE POOL HONOURS THE ORDER, in both closures, and an absent order is today's comparator untouched.
  {
    const specs = ['po:long', 'po:mid', 'po:cheap', 'po:pre'].map((id) => fixtureSpec(id));
    const durations = new Map([
      ['po:long', 90_000],
      ['po:mid', 30_000],
      ['po:cheap', 1_000],
      ['po:pre', 2_000],
    ]);
    const order = {
      pinned: new Set(['po:long']),
      preflight: ['po:pre'],
      value: new Map([
        ['po:cheap', 0.5],
        ['po:mid', 0.01],
      ]),
    };
    for (const sched of ['slots', 'cores'] as const) {
      const plan = { jobs: 4, durations, sched, budget: P24_BUDGET };
      const today = [...specs]
        .sort(planAdmission(specs, plan).rank)
        .map((s) => s.id)
        .join();
      const learned = [...specs]
        .sort(planAdmission(specs, { ...plan, order }).rank)
        .map((s) => s.id)
        .join();
      check(
        today === 'po:long,po:mid,po:pre,po:cheap',
        `${sched}: today's order is longest first, got ${today}`
      );
      check(
        learned === 'po:long,po:pre,po:cheap,po:mid',
        `${sched}: the learned order must run pinned, then preflight, then by value, got ${learned}`
      );
      check(
        [...specs]
          .sort(planAdmission(specs, { ...plan, order: undefined }).rank)
          .map((s) => s.id)
          .join() === today,
        `CONTROL ${sched}: an undefined order must be today's order exactly`
      );
    }
  }

  // T7: THE PROPERTY over archived timelines and seeded mixes.
  {
    const dir = path.join(REPO_ROOT, '.ci', 'cache', 'receipts');
    let archived: string[] = [];
    try {
      archived = fs
        .readdirSync(dir)
        .filter((n) => n.endsWith('.json'))
        .map((n) => ({ f: path.join(dir, n), m: fs.statSync(path.join(dir, n)).mtimeMs }))
        .sort((a, b) => b.m - a.m)
        .slice(0, ARCHIVE_SAMPLE)
        .map((x) => x.f);
    } catch {
      archived = [];
    }
    const mixes: Mix[] = [
      ...archived.map(mixFromReceipt).filter((m): m is Mix => m !== undefined),
      ...SEEDED_MIXES.map(seededMix),
    ];
    const fromArchive = mixes.length - SEEDED_MIXES.length;
    const nonEmpty = mixes.filter((m) => m.specs.length > 0).length;
    check(
      // The floor on T7's NON-EMPTY mixes: every seeded one must carry gates to schedule, so fewer means the property was checked over nothing (VACUOUS).
      nonEmpty >= SEEDED_MIXES.length,
      `T7 must simulate at least ${SEEDED_MIXES.length} mixes that carry gates to schedule, got ${nonEmpty} of ${mixes.length}`
    );
    let on = 0;
    let slowerUnpinned = 0;
    for (const [i, mix] of mixes.entries()) {
      const model = modelFor(mix, 1000 + i);
      const d = decide(mix, model);
      const finalMs = d.on ? d.rankedMs : (d.baseMs ?? 0);
      const baseMs = d.baseMs ?? 0;
      if (d.on) on += 1;
      check(
        finalMs <= baseMs + WALL_SLACK_MS,
        `T7: mix ${mix.name} would run ${((finalMs - baseMs) / 1000).toFixed(1)}s slower than today's order`
      );
      if (d.on) {
        // The decision's number is the simulator's, not a copy: re-simulating the chosen order gives the same makespan.
        const again = predictMakespan(
          mix.specs,
          {
            ...P24,
            durations: mix.durations,
            sched: 'cores',
            budget: P24_BUDGET,
            costs: mix.costs,
            order: d.order,
          },
          P24.machineCores
        );
        check(
          again.makespanMs === d.rankedMs,
          `T7: mix ${mix.name} re-simulated ${again.makespanMs} against the decision's ${d.rankedMs}`
        );
      }
      const ctl = decide(mix, model, { iterations: 0, longPins: false });
      if (!ctl.on) slowerUnpinned += 1;
      table.push(
        `ranking ${mix.name.padEnd(10)} today ${(baseMs / 1000).toFixed(0).padStart(5)} s, learned ${d.on ? `${(d.rankedMs / 1000).toFixed(0).padStart(5)} s ON (pinned ${d.order.pinned.size}, safety pins ${d.pinsAdded.length}, preflight ${d.order.preflight.length})` : `OFF (${d.reason})`}; unpinned control ${ctl.on ? 'within slack' : ctl.reason}`
      );
    }
    table.push(
      `ranking property: ${mixes.length} mix(es) (${fromArchive} archived, ${SEEDED_MIXES.length} seeded), ${on} ranked ON, ${slowerUnpinned} slower with pinning disabled`
    );
    check(
      on > 0,
      "T7: ranking must stay ON for at least one mix, or the property holds only because the order is always today's"
    );
    check(
      slowerUnpinned > 0,
      'T7 CONTROL: with pinning disabled at least one mix must simulate slower, or the safety check is not what holds the property'
    );
  }

  // T8: THE STAGE STOP through a real runner process.
  if (process.platform !== 'win32') {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-runner-stage-'));
    try {
      const ledgerDir = path.join(dir, 'ledger');
      fs.mkdirSync(ledgerDir);
      const g = (pr: number, wall: number) => ({
        obs: 20,
        p_red: pr,
        p_red_by_class: {},
        wall_ms: wall,
        class: 'real',
      });
      fs.writeFileSync(
        path.join(ledgerDir, 'model.json'),
        JSON.stringify({
          v: 1,
          built_at: 'fixture',
          cold_start: { on: false, reason: '' },
          runs: 20,
          gates: {
            'selftest:stage-red': g(0.9, 200),
            'selftest:stage-ok': g(0.1, 300),
            'selftest:stage-long': g(0, 20_000),
          },
          clock_set: ['selftest:stage-red', 'selftest:stage-ok'],
          clusters: [],
          associations: {},
          companions: [],
        })
      );
      const receipt = path.join(dir, 'receipt.json');
      const receiptBytes = '{"whole": true, "planted": "must stay byte-identical"}\n';
      fs.writeFileSync(receipt, receiptBytes);
      const env: NodeJS.ProcessEnv = { ...process.env, REDIACC_GATE_LEDGER_DIR: ledgerDir };
      delete env.CI_RUNNER_CACHE;
      delete env.CI_RUNNER_MANIFEST;
      const run = (name: string, longSecs: number, extra: string[]) => {
        const pidFile = path.join(dir, `${name}.pid`);
        const manifest = path.join(dir, `${name}.json`);
        fs.writeFileSync(
          manifest,
          JSON.stringify([
            fixtureSpec('selftest:stage-long', {
              run: `echo $BASHPID > ${pidFile}; exec sleep ${longSecs}`,
            }),
            fixtureSpec('selftest:stage-red', {
              run: "sleep 0.5; echo '::finding::fx/stage-red-key' >&2; exit 1",
            }),
            fixtureSpec('selftest:stage-ok', { run: 'sleep 0.5' }),
          ])
        );
        const events = path.join(dir, `${name}.events.jsonl`);
        const child = spawn(
          process.execPath,
          [
            '--import',
            'tsx',
            path.join(HERE, 'run.ts'),
            '--manifest',
            manifest,
            '--jobs',
            '4',
            '--sched',
            'slots',
            '--events',
            events,
            '--receipt-out',
            receipt,
            ...extra,
          ],
          { cwd: REPO_ROOT, env, stdio: ['ignore', 'pipe', 'pipe'] }
        );
        const out: string[] = [];
        const t0 = Date.now();
        child.stdout.on('data', (c: Buffer) => out.push(c.toString()));
        child.stderr.on('data', (c: Buffer) => out.push(c.toString()));
        return new Promise<{
          code: number | null;
          out: string;
          events: Record<string, unknown>[];
          pidFile: string;
          ms: number;
        }>((resolve) => {
          const dog = setTimeout(() => child.kill('SIGKILL'), 40_000);
          child.on('close', (code) => {
            clearTimeout(dog);
            let evs: Record<string, unknown>[] = [];
            try {
              evs = fs
                .readFileSync(events, 'utf8')
                .trim()
                .split('\n')
                .map((l) => JSON.parse(l) as Record<string, unknown>);
            } catch {
              evs = [];
            }
            resolve({ code, out: out.join(''), events: evs, pidFile, ms: Date.now() - t0 });
          });
        });
      };
      const [stopped, control] = await Promise.all([
        run('stop', 30, ['--stop-on-stage-red=preflight']),
        run('control', 2, []),
      ]);
      const longPid = Number(
        fs.existsSync(stopped.pidFile) ? fs.readFileSync(stopped.pidFile, 'utf8').trim() : 'NaN'
      );
      const longAlive = processAlive(longPid);
      check(
        /^ranking: ON /m.test(stopped.out),
        `T8: the fixture model must rank the run, output: ${stopped.out.slice(0, 600)}`
      );
      check(
        stopped.code === 3,
        `T8: a preflight red must stop the run with exit 3, got ${stopped.code}; output: ${stopped.out.slice(-800)}`
      );
      check(
        /^RED selftest:stage-red \S+s at \S+s \[preflight\] ::finding::fx\/stage-red-key rerun: /m.test(
          stopped.out
        ),
        `T8: the red must stream one RED line with its stage and first finding, output: ${stopped.out.slice(0, 800)}`
      );
      check(
        /^PREFLIGHT done at \d+s: 2 gate\(s\), 1 red$/m.test(stopped.out),
        'T8: preflight must print its done line'
      );
      check(
        /STOPPED after PREFLIGHT/.test(stopped.out) && /--narrow --print/.test(stopped.out),
        'T8: the stop must name itself and print the narrow command'
      );
      // Dead AND early: the long gate sleeps 30 s, so a run that let it finish would also leave its pid dead.
      check(
        Number.isInteger(longPid) && !longAlive && stopped.ms < 20_000,
        `T8: the stop must kill the 30 s gate, pid ${longPid} alive ${longAlive}, run took ${stopped.ms} ms`
      );
      check(
        fs.readFileSync(receipt, 'utf8') === receiptBytes,
        'T8: a stopped run must leave the receipt file byte-identical'
      );
      const kinds = stopped.events.map((e) => e.ev).join();
      const end = stopped.events.at(-1);
      check(
        kinds === 'run-start,gate-red,stage-done,run-end' &&
          end?.receipt === 'none' &&
          end?.exit === 3,
        `T8: the events stream must be run-start, gate-red, stage-done, run-end (receipt none, exit 3), got ${JSON.stringify(stopped.events)}`
      );
      check(
        control.code === 1 &&
          !/STOPPED/.test(control.out) &&
          /^RED selftest:stage-red /m.test(control.out),
        `T8 CONTROL: without --stop-on-stage-red the same run must stream the red and go to the end (exit 1), got ${control.code}`
      );
      check(
        control.events.at(-1)?.ev === 'run-end' && control.events.at(-1)?.exit === 1,
        `T8 CONTROL: the finished run must end its events with run-end exit 1, got ${JSON.stringify(control.events.at(-1))}`
      );
      // THE WIRE, end to end, once gate_ledger.py exists: what the real writer stored for the stopped run is a run row, the red's fail, the killed gate's cancel, and a last end row cut short. Both runs share the fixture ledger, so the stopped one is found by its end row.
      if (fs.existsSync(path.join(REPO_ROOT, '.ci', 'rediacc_ci', 'ci', 'gate_ledger.py'))) {
        const rows = fs
          .readdirSync(ledgerDir)
          .filter((n) => /^outcomes-\d{4}-\d{2}\.jsonl$/.test(n))
          .flatMap((n) => fs.readFileSync(path.join(ledgerDir, n), 'utf8').trim().split('\n'))
          .filter(Boolean)
          .map((l) => JSON.parse(l) as Record<string, unknown>);
        const cutEnd = rows.find((r) => r.t === 'end' && r.exit === 3);
        const mine = rows.filter((r) => r.id === cutEnd?.run || r.run === cutEnd?.run);
        const g = (gate: string) => mine.find((r) => r.t === 'g' && r.gate === gate);
        check(
          cutEnd?.cut === true &&
            mine[0]?.t === 'run' &&
            mine.at(-1)?.t === 'end' &&
            g('selftest:stage-red')?.outcome === 'fail' &&
            g('selftest:stage-long')?.outcome === 'cancel' &&
            typeof g('selftest:stage-red')?.t0_ms === 'number',
          `T8: the real ledger writer must store run, fail, cancel and a last cut end row for the stopped run, got ${JSON.stringify(mine).slice(0, 900)}`
        );
        check(
          !/gate ledger writer/.test(stopped.out) && !/gate ledger writer/.test(control.out),
          `T8: the real ledger writer must accept every row (no degradation warning), output: ${stopped.out.slice(-600)}`
        );
      }
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }
  return { failures, assertions, table };
}

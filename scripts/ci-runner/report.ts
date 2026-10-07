/**
 * Output: quiet on success, complete on failure.
 *
 * TWO DELIBERATE CHOICES, both against the instinct to tidy up.
 *
 * Failure blocks stream the moment a gate fails rather than being held to the
 * end, because an agent tailing a fifteen-minute run should see the first red
 * as it happens.
 *
 * Captured output is printed UNMODIFIED and UNTRUNCATED: no indentation, no
 * head/tail elision. Twenty failing gates is a lot of text, and that is
 * accepted -- truncation is how a diagnostic becomes useless, and the whole
 * point of the runner is that one run surfaces every failure instead of the
 * `&&` chain's first one.
 *
 * See agent/plans/PLAN-npm-ci-parallel-parity.md section 4.4.
 */
import type { GateSpec } from './manifest';
import type { GateResult } from './pool';

/** One cumulative reading of the machine's CPU counters (/proc/stat's aggregate line, or os.cpus() off Linux). Units are whatever the source counts in; only ratios are used. */
export interface CpuTick {
  /** Epoch ms of the reading. */
  t: number;
  busy: number;
  idle: number;
  /** Always 0 off Linux, where os.cpus() has no iowait. */
  iowait: number;
  total: number;
}

/**
 * Where the run's CPU went (agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.3). MEASUREMENT ONLY: nothing schedules on it yet. The per-5 s strip is what shows the tail -- the pool full and busy early, then fewer cores as the long gates drain.
 */
export interface Utilisation {
  /** Logical CPUs the counters cover, which is the whole machine, not the pool's slot count. */
  cores: number;
  /** Share of all cores' time spent busy between the first and last tick, 0..1. */
  busyFrac: number;
  busyCoreS: number;
  idleCoreS: number;
  iowaitCoreS: number;
  /** Sum of the gates' own cpuMs, in core-seconds, and how many gates reported one. */
  gatesCpuS: number;
  gatesMeasured: number;
  /** Gates whose /proc sampler saw more CPU than `times` did (descendants that escaped the reap). */
  undercount: string[];
  /** Mean busy cores in each 5 s bucket from the start of the run. */
  strip: number[];
  /** The longest `needs` chain by measured ms, and its gates in order. */
  criticalPathMs: number;
  criticalPath: string[];
  /** gatesCpuS / cores, in ms: the wall the gates' CPU cannot beat on this machine. */
  cpuFloorMs: number;
  floorMs: number;
  /** wall / floor. */
  wallOverFloor: number;
  /** The five longest waits between ready and launched. */
  queueDelays: { id: string; ms: number; blockedBy: string }[];
  /** How many gates each admission check last held back (pool.ts HoldReason), so a `cores` run shows whether cpu, memory, the process count or a reservation was the constraint. */
  heldBack: Record<string, number>;
}

const STRIP_MS = 5000;

/** One gate's place in the run, in ms from the run's start: when its `needs` were met, when it launched, when it settled, and the cores it was granted. */
export interface GateTiming {
  ready?: number;
  start: number;
  end: number;
  cores?: number;
}

/**
 * THE TIMELINE (2026-10-06): every launched gate's start and end relative to the run's start, so a slow run's tail can be read rather than inferred. The diagnosis that motivated it reconstructed start times from end minus duration and placed check:ci-account-server at about 280 s; the profile captures showed it at 0.6 s, one core wide, with check:ci-test-account-web queued behind it on their shared `account-vitest` mutex. Gates that never launched (skipped) have no entry. Keys in manifest order, so the block is stable across identical runs.
 */
export function timelineOf(
  results: readonly GateResult[],
  startedAt: number
): Record<string, GateTiming> {
  const out: Record<string, GateTiming> = {};
  for (const r of results) {
    if (r.startAt === undefined || r.endAt === undefined) continue;
    const t: GateTiming = { start: r.startAt - startedAt, end: r.endAt - startedAt };
    if (r.readyAt !== undefined) t.ready = r.readyAt - startedAt;
    if (r.grantedCores !== undefined) t.cores = r.grantedCores;
    out[r.id] = t;
  }
  return out;
}

/** How many of the last gates to finish the footer names with their timing. */
const TAIL_ROWS = 12;

/** Longest path over `needs`, weighting each gate by its measured ms; a gate that did not run weighs 0. */
export function criticalPath(
  specs: readonly GateSpec[],
  results: readonly GateResult[]
): { ms: number; ids: string[] } {
  const ms = new Map(results.map((r) => [r.id, r.ms]));
  const byId = new Map(specs.map((s) => [s.id, s]));
  const memo = new Map<string, { ms: number; ids: string[] }>();
  const walk = (id: string): { ms: number; ids: string[] } => {
    const hit = memo.get(id);
    if (hit !== undefined) return hit;
    let best = { ms: 0, ids: [] as string[] };
    for (const need of byId.get(id)?.needs ?? []) {
      const sub = walk(need);
      if (sub.ms > best.ms) best = sub;
    }
    const own = { ms: best.ms + (ms.get(id) ?? 0), ids: [...best.ids, id] };
    memo.set(id, own);
    return own;
  };
  let top = { ms: 0, ids: [] as string[] };
  for (const s of specs) {
    const p = walk(s.id);
    if (p.ms > top.ms) top = p;
  }
  return top;
}

/** Fold the CPU ticks and the per-gate timings into the footer's numbers. Undefined when fewer than two ticks exist (a run shorter than one sampling interval says nothing about utilisation). */
export function utilisation(
  ticks: readonly CpuTick[],
  cores: number,
  results: readonly GateResult[],
  cp: { ms: number; ids: string[] },
  wallMs: number
): Utilisation | undefined {
  if (ticks.length < 2 || cores < 1) return undefined;
  const first = ticks[0];
  const last = ticks[ticks.length - 1];
  const dTotal = last.total - first.total;
  const spanS = (last.t - first.t) / 1000;
  if (dTotal <= 0 || spanS <= 0) return undefined;
  const coreS = (d: number): number => (d / dTotal) * cores * spanS;

  // Each bucket reads the tick nearest its two edges; a bucket with no tick inside it repeats nothing and reads 0.
  const strip: number[] = [];
  for (let edge = first.t; edge < last.t; edge += STRIP_MS) {
    const inside = ticks.filter((k) => k.t >= edge && k.t <= edge + STRIP_MS);
    const a = inside[0];
    const b = inside[inside.length - 1];
    if (a === undefined || b === undefined || b.total <= a.total) {
      strip.push(0);
      continue;
    }
    strip.push(((b.busy - a.busy) / (b.total - a.total)) * cores);
  }

  const measured = results.filter((r) => r.cpuMs !== undefined);
  const gatesCpuS = measured.reduce((sum, r) => sum + (r.cpuMs ?? 0), 0) / 1000;
  const cpuFloorMs = (gatesCpuS / cores) * 1000;
  const floorMs = Math.max(cp.ms, cpuFloorMs);
  const queueDelays = results
    .filter((r) => r.readyAt !== undefined && r.startAt !== undefined)
    .map((r) => ({
      id: r.id,
      ms: (r.startAt ?? 0) - (r.readyAt ?? 0),
      blockedBy: r.blockedBy ?? 'none',
    }))
    // Under 100 ms is the spawn cost of the gates launched just before it in the same pass, not a wait.
    .filter((d) => d.ms >= 100)
    .sort((a, b) => b.ms - a.ms)
    .slice(0, 5);

  const heldBack: Record<string, number> = {};
  for (const r of results) {
    if (r.blockedBy !== undefined) heldBack[r.blockedBy] = (heldBack[r.blockedBy] ?? 0) + 1;
  }

  return {
    cores,
    busyFrac: (last.busy - first.busy) / dTotal,
    busyCoreS: coreS(last.busy - first.busy),
    idleCoreS: coreS(last.idle - first.idle),
    iowaitCoreS: coreS(last.iowait - first.iowait),
    gatesCpuS,
    gatesMeasured: measured.length,
    undercount: results.filter((r) => r.undercount === true).map((r) => r.id),
    strip,
    criticalPathMs: cp.ms,
    criticalPath: cp.ids,
    cpuFloorMs,
    floorMs,
    wallOverFloor: floorMs > 0 ? wallMs / floorMs : 0,
    queueDelays,
    heldBack,
  };
}

export interface ReporterOptions {
  /** Column width for gate ids, so the streamed lines align. */
  idWidth: number;
  /** Human-readable stream. */
  out: (text: string) => void;
  /** Machine-readable document sink, used only by footer() under --json. */
  jsonOut?: (text: string) => void;
}

export interface RunMeta {
  jobs: number;
  failFast: boolean;
  /** Human description of a partial selection, e.g. "--only check:ci-*". */
  selection?: string;
  wallMs: number;
  /** Absent when no CPU ticks were taken (the selftest, a sub-interval run). */
  util?: Utilisation;
  /** The core budget, stated in the header under `--sched cores`; absent under `slots`, whose header is unchanged. */
  sched?: string;
  /** Epoch ms the run started, for the footer's tail timeline. Absent prints no timeline. */
  startedAt?: number;
}

const RULE = '='.repeat(64);

function secs(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

function gates(n: number): string {
  return n === 1 ? '1 gate' : `${n} gates`;
}

function why(result: GateResult): string {
  if (result.timedOutMs !== undefined)
    return `TIMED OUT at its ${secs(result.timedOutMs)} limit, process group killed`;
  if (result.vacuity !== undefined) return `exit 0 but ${result.vacuity}`;
  if (result.exitCode === null) return 'killed';
  return `exit ${result.exitCode}`;
}

export function createReporter(opts: ReporterOptions) {
  const pad = (id: string): string => id.padEnd(opts.idWidth);

  return {
    header(gateCount: number, meta: RunMeta): void {
      const mode = meta.failFast ? 'fail-fast' : 'keep-going';
      opts.out(
        meta.sched === undefined
          ? `ci-runner: ${gates(gateCount)}, ${meta.jobs} workers, ${mode}\n`
          : `ci-runner: ${gates(gateCount)}, ${meta.sched}, ${mode}\n`
      );
      // A partial run reporting green is the vacuity failure this whole design exists to prevent, so the selection is stated loudly at both ends of the output and carried in the JSON as partial:true.
      if (meta.selection !== undefined) {
        opts.out(`ci-runner: PARTIAL RUN, selection: ${meta.selection}\n`);
      }
    },

    // Under --verbose, and always under --json, where this stream is stderr and is the only live trace a CI log has: housekeeping's capture sat silent for 863 s on 2026-10-06 with no line naming the gate it was waiting on. At --jobs 1 a five-minute gate otherwise looks exactly like a hang. `at` is seconds from the run's start, `limit` the gate's kill timer.
    start(id: string, at?: { sinceStartMs: number; limitMs?: number }): void {
      if (at === undefined) {
        opts.out(`  ..    ${pad(id)}\n`);
        return;
      }
      const limit = at.limitMs === undefined ? '' : `, limit ${secs(at.limitMs)}`;
      opts.out(`  ..    ${pad(id)} started at ${secs(at.sinceStartMs)}${limit}\n`);
    },

    finish(result: GateResult): void {
      if (result.status === 'ok') {
        opts.out(`  ok    ${pad(result.id)} ${secs(result.ms).padStart(7)}\n`);
        return;
      }
      if (result.status === 'skipped') {
        opts.out(`  SKIP  ${pad(result.id)}         ${result.reason ?? ''}\n`);
        return;
      }
      // BLOCKED IS NOT FAIL, AND THE PER-GATE LINE MUST SAY SO. The footer counted the two separately from the start while this line still printed FAIL for both, so a run read "8 failed" above nine FAIL lines. A status that is only honest in the summary is not honest: the reader scanning for what to fix is reading THESE lines.
      if (result.status === 'blocked') {
        opts.out(`BLOCK ${pad(result.id)} ${secs(result.ms).padStart(7)}   could not run here\n`);
        opts.out('  --- why ---\n');
        const why_ = (result.stderr || result.stdout).trim();
        opts.out(
          why_ === '' ? '  (said nothing, which is itself a defect)\n' : ensureNewline(why_)
        );
        opts.out('\n');
        return;
      }
      opts.out(`FAIL  ${pad(result.id)} ${secs(result.ms).padStart(7)}   ${why(result)}\n`);
      opts.out(`  rerun: ${result.rerun}\n`);
      opts.out('  --- stdout ---\n');
      opts.out(result.stdout === '' ? '  (stdout was empty)\n' : ensureNewline(result.stdout));
      opts.out('  --- stderr ---\n');
      opts.out(result.stderr === '' ? '  (stderr was empty)\n' : ensureNewline(result.stderr));
      opts.out('\n');
    },

    footer(results: readonly GateResult[], meta: RunMeta): number {
      const failed = results.filter((r) => r.status === 'fail');
      const skipped = results.filter((r) => r.status === 'skipped');
      const blocked = results.filter((r) => r.status === 'blocked');
      const ok = results.filter((r) => r.status === 'ok');
      const serialMs = results.reduce((sum, r) => sum + r.ms, 0);
      const speedup = meta.wallMs > 0 ? serialMs / meta.wallMs : 0;
      // BLOCKED DOES NOT REDDEN THE RUN. A gate that could not run has said nothing about the code, and treating "this machine lacks ruff" as a finding is what turns a pre-push lane into a wall nobody keeps. It is never silent though -- it is counted below, listed by name with the gate's own message, and recorded in the receipt for the guard to warn on. Under CI the toolchain is
      // present, so a gate exiting CANNOT_RUN there is a broken lane and shows up as a plain non-zero to the workflow.
      const exitCode = failed.length > 0 || skipped.length > 0 ? 1 : 0;

      opts.out(`${RULE}\n`);
      opts.out(
        `${gates(results.length)}: ${ok.length} ok, ${failed.length} failed, ${skipped.length} skipped` +
          (blocked.length > 0 ? `, ${blocked.length} BLOCKED (could not run)` : '') +
          `     wall ${secs(meta.wallMs)} (serial ${secs(serialMs)}, ${speedup.toFixed(1)}x)\n`
      );
      if (meta.selection !== undefined) {
        opts.out(`PARTIAL RUN, selection: ${meta.selection}. This is NOT a full gate run.\n`);
      }
      opts.out(`${RULE}\n`);

      const slowest = [...results].sort((a, b) => b.ms - a.ms).slice(0, 8);
      if (slowest.length > 0 && slowest[0].ms > 0) {
        opts.out('slowest:\n');
        for (const r of slowest) {
          if (r.ms === 0) continue;
          opts.out(`  ${secs(r.ms).padStart(7)}  ${r.id}\n`);
        }
      }

      // THE GRANTS (agent/plans/PLAN-prepush-full-cpu.md part 1): every elastic gate with the cores it was told, so a run that starved its widest gate says so in one line.
      const elastic = results.filter((r) => r.elastic === true && r.grantedCores !== undefined);
      if (elastic.length > 0) {
        opts.out(
          `elastic grants: ${elastic.map((r) => `${r.id} ${r.grantedCores} core(s)`).join(', ')}\n`
        );
      }

      // THE TAIL, with times: the last gates to finish, each with when it was ready, launched and ended (s from the run's start) and its cores. The full timeline is in the receipt (`timeline`) and in --json's per-gate startAt/endAt.
      if (meta.startedAt !== undefined) {
        const timeline = timelineOf(results, meta.startedAt);
        const tail = Object.entries(timeline)
          .sort((a, b) => b[1].end - a[1].end)
          .slice(0, TAIL_ROWS);
        if (tail.length > 0) {
          opts.out('last to finish (ready / start -> end, s from run start; cores):\n');
          for (const [id, t] of tail) {
            const ready = t.ready === undefined ? '     -' : secs(t.ready).padStart(6);
            opts.out(
              `  ${ready} / ${secs(t.start).padStart(6)} -> ${secs(t.end).padStart(6)}  ${String(t.cores ?? '-').padStart(2)}  ${id}\n`
            );
          }
        }
      }

      const u = meta.util;
      if (u !== undefined) {
        const cs = (n: number): string => `${n.toFixed(1)} core-s`;
        opts.out(
          `cpu (whole machine, other work included): ${u.cores} cores, busy ${(u.busyFrac * 100).toFixed(1)}% (${cs(u.busyCoreS)}); ` +
            `idle ${cs(u.idleCoreS)}, iowait ${cs(u.iowaitCoreS)}; ` +
            `gates' own cpu ${cs(u.gatesCpuS)} over ${gates(u.gatesMeasured)}` +
            (u.undercount.length > 0 ? `, ${u.undercount.length} undercount` : '') +
            '\n'
        );
        opts.out(`busy cores per 5s: ${u.strip.map((n) => n.toFixed(1)).join(' ')}\n`);
        opts.out(
          `floor max(CP ${secs(u.criticalPathMs)}, cpu ${secs(u.cpuFloorMs)}) = ${secs(u.floorMs)}; ` +
            `wall = ${u.wallOverFloor.toFixed(2)} x floor\n`
        );
        if (u.criticalPath.length > 0) opts.out(`  critical path: ${u.criticalPath.join(' > ')}\n`);
        const held = Object.entries(u.heldBack).sort((a, b) => b[1] - a[1]);
        if (held.length > 0) {
          opts.out(
            `held back (last reason): ${held.map(([why, n]) => `${why} ${n}`).join(', ')}\n`
          );
        }
        if (u.queueDelays.length > 0) {
          opts.out('queue delays (ready to launched):\n');
          for (const d of u.queueDelays) {
            opts.out(`  ${secs(d.ms).padStart(7)}  ${d.id} (${d.blockedBy})\n`);
          }
        }
      }

      // Named apart from FAILED, with the limit, so a hang is never read as an ordinary red and the reader sees which timer to question.
      const timedOut = results.filter((r) => r.timedOutMs !== undefined);
      if (timedOut.length > 0) {
        opts.out('TIMED OUT (killed at the limit; scripts/ci-runner/gate-timeout.ts):\n');
        for (const r of timedOut)
          opts.out(`  ${pad(r.id)}  after ${secs(r.ms)}, limit ${secs(r.timedOutMs ?? 0)}\n`);
      }
      if (failed.length > 0) {
        opts.out('FAILED:\n');
        for (const r of failed) opts.out(`  ${pad(r.id)}  ${r.rerun}\n`);
      }
      if (skipped.length > 0) {
        opts.out('SKIPPED:\n');
        for (const r of skipped) opts.out(`  ${pad(r.id)}  ${r.reason ?? ''}\n`);
      }
      if (blocked.length > 0) {
        // Named, with the gate's own words. The whole point of the status is that the reader can tell a missing tool from a real finding, and that distinction is only visible if the reason is printed.
        opts.out('BLOCKED (could not run here; NOT a verdict on the code):\n');
        for (const r of blocked) {
          const why = (r.stderr || r.stdout).trim().split('\n').filter(Boolean).slice(-3);
          opts.out(`  ${pad(r.id)}\n`);
          for (const line of why) opts.out(`      ${line}\n`);
        }
      }
      if (failed.length > 0) {
        opts.out('rerun all failures:\n');
        opts.out(`  ${failed.map((r) => r.rerun).join(' && ')}\n`);
      }
      opts.out(`${RULE}\n`);

      opts.jsonOut?.(
        `${JSON.stringify(
          {
            partial: meta.selection !== undefined,
            selection: meta.selection ?? null,
            jobs: meta.jobs,
            sched: meta.sched ?? 'slots',
            failFast: meta.failFast,
            wallMs: meta.wallMs,
            serialMs,
            ok: ok.length,
            failed: failed.length,
            blocked: blocked.length,
            skipped: skipped.length,
            timedOut: timedOut.map((r) => r.id),
            exitCode,
            utilisation: meta.util ?? null,
            gates: results,
          },
          null,
          2
        )}\n`
      );

      return exitCode;
    },
  };
}

function ensureNewline(text: string): string {
  return text.endsWith('\n') ? text : `${text}\n`;
}

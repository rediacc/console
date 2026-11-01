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
import fs from 'node:fs';
import path from 'node:path';
import { receiptFindings } from './findings';
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
 * Idle core-ms over [fromMs, toMs], from the ticks spanning it at the machine's measured idle share; undefined when no pair of ticks covers it (the sampler has not run long enough, or has stalled), because no reading must never read as idle. iowait is not counted as idle: those cores have work parked on them. Ticks are in time order, and the search runs from the newest since the pool only asks about the last few seconds.
 */
export function idleCoreMsBetween(
  ticks: readonly CpuTick[],
  cores: number,
  fromMs: number,
  toMs: number
): number | undefined {
  // The sampler reads every 500 ms; a bucket's edges may sit up to one reading past the ticks that bracket them, and anything later means the sampler stopped.
  const SLACK_MS = 1000;
  let end: CpuTick | undefined;
  let start: CpuTick | undefined;
  for (let i = ticks.length - 1; i >= 0; i -= 1) {
    const tick = ticks[i];
    if (tick === undefined) continue;
    if (end === undefined && tick.t <= toMs) end = tick;
    if (tick.t <= fromMs) {
      start = tick;
      break;
    }
  }
  if (end === undefined || start === undefined || toMs - end.t > SLACK_MS || end.t <= start.t)
    return undefined;
  const total = end.total - start.total;
  if (total <= 0) return undefined;
  return ((end.idle - start.idle) / total) * cores * (toMs - fromMs);
}

/**
 * Where the run's CPU went (agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.3). The footer's figures are measurement only; the one thing that schedules on the ticks is `idleCoreMsBetween`, the reading behind the pool's borrow (pool.ts reclaimableCores). The per-5 s strip is what shows the tail -- the pool full and busy early, then fewer cores as the long gates drain.
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

      // THE BORROWS (pool.ts reclaimableCores): the gates that started past the budget, in measured idle, so a run that leaned on it says so.
      const borrowed = results.filter((r) => r.borrowed !== undefined);
      if (borrowed.length > 0) {
        opts.out(
          `borrowed idle cores: ${borrowed.length} gate(s), ${borrowed.reduce((sum, r) => sum + (r.borrowed ?? 0), 0).toFixed(1)} core(s) in all: ${borrowed
            .slice(0, 12)
            .map((r) => r.id)
            .join(', ')}${borrowed.length > 12 ? ', ...' : ''}\n`
        );
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

// ---------------------------------------------------------------- the stream (agent/plans/PLAN-gate-scheduling-learned.md section 5, T8)

/** Which part of a ranked run a gate belongs to. An unranked run, and every pinned gate, is `tail`. */
export type Stage = 'preflight' | 'stage1' | 'tail';

/** An error-looking line: what a reader scanning a RED line wants first when the gate printed no finding key. */
const ERROR_LINE_RE =
  /\b(error|errors|fail|failed|failure|refus\w*|missing|not found|stale|drift)\b|✗|ERR!/i;
/** A RED line stays one terminal line: the first error is cut at this many characters. */
const FIRST_ERROR_MAX = 160;
/** The ESC byte, built as findings.ts builds it, so no control character sits in a regex literal. */
const ANSI = new RegExp(`${String.fromCharCode(27)}\\[[0-9;?]*[A-Za-z]`, 'g');

/** The first `::finding::` key, else the first error-looking line, else the first non-empty line, else the exit; one line, cut at FIRST_ERROR_MAX. */
export function firstError(
  r: Pick<GateResult, 'id' | 'status' | 'stdout' | 'stderr' | 'exitCode' | 'timedOutMs'>
): string {
  const keys = receiptFindings([{ ...r, status: 'fail' }], () => {})[r.id];
  const cut = (t: string): string =>
    t.length > FIRST_ERROR_MAX ? `${t.slice(0, FIRST_ERROR_MAX - 3)}...` : t;
  if (keys !== null && keys !== undefined && keys.length > 0) return cut(`::finding::${keys[0]}`);
  const lines = `${r.stderr}\n${r.stdout}`
    .replace(ANSI, '')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l !== '');
  const hit = lines.find((l) => ERROR_LINE_RE.test(l)) ?? lines[0];
  if (hit !== undefined) return cut(hit);
  return why(r as GateResult);
}

/** `RED <id> <wall>s at <t>s [preflight|stage1|tail] <first error> rerun: <cmd>`: one grep-able line per red, printed the moment it lands. */
export function redLine(r: GateResult, atMs: number, stage: Stage): string {
  return `RED ${r.id} ${secs(r.ms)} at ${secs(atMs)} [${stage}] ${firstError(r)} rerun: ${r.rerun}\n`;
}

/** One entry of .ci/config/carried-reds.json v2, as the stop rule reads it. */
export interface CarriedEntry {
  gate: string;
  findings: string[] | '*';
}

/** carried-reds.json's `carried` list; [] when the text is absent or unreadable, so an unreadable file covers nothing and every red stops the run. */
export function parseCarried(text: string | undefined): CarriedEntry[] {
  if (text === undefined) return [];
  try {
    const doc = JSON.parse(text) as { carried?: unknown };
    if (!Array.isArray(doc.carried)) return [];
    return doc.carried.flatMap((e): CarriedEntry[] => {
      const x = e as { gate?: unknown; findings?: unknown };
      if (typeof x.gate !== 'string') return [];
      if (x.findings === '*') return [{ gate: x.gate, findings: '*' }];
      if (Array.isArray(x.findings) && x.findings.every((k) => typeof k === 'string'))
        return [{ gate: x.gate, findings: x.findings as string[] }];
      return [];
    });
  } catch {
    return [];
  }
}

/** A red the push guard would carry: its gate is carried whole (`*`), or every key it printed is carried. Keys `null` (nothing parsable) are never covered by a keyed entry. */
export function coveredByCarried(
  id: string,
  keys: string[] | null,
  carried: readonly CarriedEntry[]
): boolean {
  const e = carried.find((c) => c.gate === id);
  if (e === undefined) return false;
  if (e.findings === '*') return true;
  if (keys === null) return false;
  const set = new Set(e.findings);
  return keys.every((k) => set.has(k));
}

/** The `--events` sink: JSON lines, appended synchronously so an event lands before the line it describes is acted on. */
export interface EventSink {
  readonly file: string | undefined;
  emit(ev: Record<string, unknown>): void;
}

/** A sink at `file` (undefined: no sink). A write that fails warns ONCE and disables the sink; events never change a verdict. */
export function openEventSink(file: string | undefined, warn: (text: string) => void): EventSink {
  let dead = file === undefined;
  return {
    file,
    emit(ev: Record<string, unknown>): void {
      if (dead || file === undefined) return;
      try {
        // tree-write: safe the sink is --events (refused unless absolute) or <receipt dir>/ci-quick-events/, the scratch cache beside the receipt
        fs.mkdirSync(path.dirname(file), { recursive: true });
        // tree-write: safe the same events file the line above made the directory for
        fs.appendFileSync(file, `${JSON.stringify(ev)}\n`);
      } catch (e) {
        dead = true;
        warn(
          `ci-runner: WARNING: the events stream ${file} could not be written (${(e as Error).message}); it is off for the rest of this run\n`
        );
      }
    },
  };
}

/** What the stream asks of the runner after one gate settles: nothing, or stop on a stage's uncovered reds. */
export interface StageStop {
  stage: 'preflight' | 'stage1';
  reds: string[];
}

interface StreamOptions {
  run: string;
  out: (text: string) => void;
  events: EventSink;
  /** The ranked stages; undefined (ranking off) makes every gate `tail` and no stage line is printed. */
  stages?: { preflight: readonly string[]; stage1: readonly string[] };
  carried: readonly CarriedEntry[];
  /** `--stop-on-stage-red[=preflight|1]`: the stage whose completion with an uncovered red stops the run. */
  stopAt?: 'preflight' | '1';
}

/**
 * The per-gate stream: a RED line and a gate-red event for every red, and a `PREFLIGHT done` / `STAGE1 done` line plus a stage-done event when each stage has settled. Stage 1's line counts preflight and stage 1 together, since stage 1 is defined by the expected reds the two hold between them. Returns a StageStop when `stopAt`'s stage has settled with a red the carried set does not cover.
 */
export function createStream(opts: StreamOptions) {
  const pre = new Set(opts.stages?.preflight ?? []);
  const s1 = new Set([...(opts.stages?.stage1 ?? []), ...pre]);
  const settled = new Set<string>();
  const reds = new Set<string>();
  const uncovered = new Set<string>();
  const done = { preflight: pre.size === 0, stage1: s1.size === pre.size };
  const stageOf = (id: string): Stage =>
    pre.has(id) ? 'preflight' : s1.has(id) ? 'stage1' : 'tail';
  const all = (set: ReadonlySet<string>): boolean => [...set].every((id) => settled.has(id));
  const inSet = (set: ReadonlySet<string>, from: ReadonlySet<string>): string[] =>
    [...from].filter((id) => set.has(id));
  const report = (
    name: 'preflight' | 'stage1',
    set: ReadonlySet<string>,
    atMs: number
  ): StageStop | undefined => {
    const r = inSet(set, reds);
    opts.out(
      `${name === 'preflight' ? 'PREFLIGHT' : 'STAGE1'} done at ${Math.round(atMs / 1000)}s: ${set.size} gate(s), ${r.length} red\n`
    );
    opts.events.emit({
      ev: 'stage-done',
      run: opts.run,
      stage: name,
      t_ms: atMs,
      gates: set.size,
      red: r,
    });
    const stopHere =
      (opts.stopAt === 'preflight' && name === 'preflight') ||
      (opts.stopAt === '1' && name === 'stage1');
    const open = inSet(set, uncovered);
    return stopHere && open.length > 0 ? { stage: name, reds: open } : undefined;
  };
  return {
    stageOf,
    finish(r: GateResult, atMs: number): StageStop | undefined {
      settled.add(r.id);
      if (r.status === 'fail') {
        const stage = stageOf(r.id);
        reds.add(r.id);
        const keys = receiptFindings([r], () => {})[r.id] ?? null;
        if (!coveredByCarried(r.id, keys, opts.carried)) uncovered.add(r.id);
        opts.out(redLine(r, atMs, stage));
        opts.events.emit({
          ev: 'gate-red',
          run: opts.run,
          gate: r.id,
          t_ms: atMs,
          wall_ms: r.ms,
          stage,
          carried: !uncovered.has(r.id),
          first_error: firstError(r),
          rerun: r.rerun,
        });
      }
      let stop: StageStop | undefined;
      if (!done.preflight && all(pre)) {
        done.preflight = true;
        stop = report('preflight', pre, atMs);
      }
      if (!done.stage1 && all(s1)) {
        done.stage1 = true;
        stop ??= report('stage1', s1, atMs);
      }
      return stop;
    },
  };
}

/** The stream's controls, driven with synthetic results; run from run.ts --selftest. */
export function streamSelftest(): { failures: string[]; assertions: number } {
  const failures: string[] = [];
  let assertions = 0;
  const check = (ok: boolean, message: string): void => {
    assertions += 1;
    if (!ok) failures.push(message);
  };
  const res = (id: string, status: GateResult['status'], stdout = '', stderr = ''): GateResult => ({
    id,
    gate: true,
    status,
    ms: 1500,
    exitCode: status === 'fail' ? 1 : 0,
    stdout,
    stderr,
    rerun: `npm run ${id}`,
  });
  check(
    firstError(res('fx:k', 'fail', 'noise\n::finding::rule/abc\n', 'error: later')) ===
      '::finding::rule/abc',
    'the first finding key leads the RED line'
  );
  check(
    firstError(res('fx:e', 'fail', 'building...\nok 3 files\n', 'ERROR: the lock is stale')) ===
      'ERROR: the lock is stale',
    'with no key, the first error-looking line leads'
  );
  check(firstError(res('fx:q', 'fail')) === 'exit 1', 'CONTROL: a silent red says its exit');
  check(
    redLine(res('fx:a', 'fail', '', 'Error: x'), 41_000, 'preflight') ===
      'RED fx:a 1.5s at 41.0s [preflight] Error: x rerun: npm run fx:a\n',
    `the RED line format, got ${JSON.stringify(redLine(res('fx:a', 'fail', '', 'Error: x'), 41_000, 'preflight'))}`
  );
  const carried = parseCarried(
    JSON.stringify({
      version: 2,
      carried: [
        { gate: 'fx:c', findings: ['k1'] },
        { gate: 'fx:w', findings: '*' },
      ],
    })
  );
  check(coveredByCarried('fx:c', ['k1'], carried), 'a red whose keys are all carried is covered');
  check(!coveredByCarried('fx:c', ['k1', 'k2'], carried), 'CONTROL: one new key uncovers it');
  check(
    !coveredByCarried('fx:c', null, carried),
    'CONTROL: no parsable keys is never covered by a keyed entry'
  );
  check(coveredByCarried('fx:w', null, carried), "a '*' entry covers its gate whatever it printed");
  check(parseCarried('{').length === 0, 'CONTROL: an unreadable carried-reds covers nothing');

  // The stage lines and the stop, with events captured.
  const run = (stopAt: 'preflight' | '1' | undefined, carry: CarriedEntry[]) => {
    const lines: string[] = [];
    const events: Record<string, unknown>[] = [];
    const st = createStream({
      run: 'r',
      out: (t) => lines.push(t),
      events: { file: undefined, emit: (e) => events.push(e) },
      stages: { preflight: ['fx:p1', 'fx:p2'], stage1: ['fx:s1'] },
      carried: carry,
      stopAt,
    });
    const stops = [
      st.finish(res('fx:p1', 'ok'), 10_000),
      st.finish(res('fx:p2', 'fail', '::finding::k1\n'), 41_000),
      st.finish(res('fx:t', 'fail'), 50_000),
      st.finish(res('fx:s1', 'ok'), 60_000),
    ];
    return { lines: lines.join(''), events, stops };
  };
  const plain = run(undefined, []);
  check(
    /^RED fx:p2 1\.5s at 41\.0s \[preflight\] ::finding::k1 rerun: npm run fx:p2$/m.test(
      plain.lines
    ) && /^RED fx:t .* \[tail\] /m.test(plain.lines),
    `every red streams one RED line with its stage, got ${plain.lines}`
  );
  check(
    /^PREFLIGHT done at 41s: 2 gate\(s\), 1 red$/m.test(plain.lines) &&
      /^STAGE1 done at 60s: 3 gate\(s\), 1 red$/m.test(plain.lines),
    `each stage prints its done line once it settles, got ${plain.lines}`
  );
  check(
    plain.events.map((e) => `${e.ev}:${e.stage ?? ''}`).join() ===
      'gate-red:preflight,stage-done:preflight,gate-red:tail,stage-done:stage1',
    `the events stream carries gate-red and stage-done in order, got ${JSON.stringify(plain.events)}`
  );
  check(
    plain.stops.every((x) => x === undefined),
    'CONTROL: without --stop-on-stage-red nothing stops'
  );
  const stopPre = run('preflight', []);
  check(
    stopPre.stops[1]?.stage === 'preflight' && stopPre.stops[1]?.reds.join() === 'fx:p2',
    `--stop-on-stage-red=preflight must stop when preflight settles red, got ${JSON.stringify(stopPre.stops)}`
  );
  const stop1 = run('1', []);
  check(
    stop1.stops[1] === undefined && stop1.stops[3]?.stage === 'stage1',
    `--stop-on-stage-red=1 must wait for stage 1, got ${JSON.stringify(stop1.stops)}`
  );
  const carriedRun = run('preflight', [{ gate: 'fx:p2', findings: ['k1'] }]);
  check(
    carriedRun.stops.every((x) => x === undefined),
    `CONTROL: a red the carried keys cover must not stop the run, got ${JSON.stringify(carriedRun.stops)}`
  );
  const unranked = createStream({
    run: 'r',
    out: () => {},
    events: { file: undefined, emit: () => {} },
    carried: [],
    stopAt: '1',
  });
  check(
    unranked.stageOf('fx:any') === 'tail' &&
      unranked.finish(res('fx:any', 'fail'), 1) === undefined,
    'with ranking off every gate is tail and no stage can stop the run'
  );
  return { failures, assertions };
}

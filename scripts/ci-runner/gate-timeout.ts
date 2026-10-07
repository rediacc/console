/**
 * THE PER-GATE KILL TIMER, and the one place its numbers live.
 *
 * WHY IT EXISTS. Before it the runner waited on every gate for as long as the gate cared to run. On 2026-10-06 and 2026-10-07 housekeeping.yml's `Gate cost capture` (a serial `run.ts --quick --jobs 1 --json`) sat silent until GitHub cancelled the job at fifteen minutes, against a healthy 277.5 s; the only trace of which gate was running was the runner's orphan list (`check:ci-docs-browse-invariants`, a 0.5 s gate, then `check:ci-no-client-key-composition`). One gate that never exits stalled the whole capture, and nothing named it.
 *
 * WHAT THE NUMBER IS. A gate's limit is GATE_TIMEOUT_FACTOR times the slowest thing ever measured of it (the committed CI step p90 in lane-durations.json, this machine's ewma, and the largest of its recent passing walls), never below GATE_TIMEOUT_FLOOR_MS. A gate measured nowhere gets the floor, or GATE_TIMEOUT_UNMEASURED_SLOW_MS when it is declared `slow`. `--gate-timeout <s>` replaces every limit for one run.
 *
 * WHY THESE VALUES, from the measurements they rest on (2026-10-07):
 *   - the fast tier's budget is 10 s (check-gate-manifest.ts BUDGET_MS); the slowest fast gate on the capture runner is 8.6 s serial (gate-costs.json build:cli), and the worst contended local sample of a lane gate is 42.7 s (check:types:incremental). A 300 s floor is seven times that sample.
 *   - the capture's healthy wall is 277.5 s and its job allows 900 s: one hung fast gate now ends at the floor plus KILL_GRACE_MS, about 585 s, and the capture still reports.
 *   - the slowest gate the CI table knows is check:ci-pytest at a 529.2 s step p90, so its limit is about 35 minutes: a timer, not a budget. Nothing here judges whether a gate is fast enough; the tier oracle does that.
 *   - a slow gate never measured anywhere (a new gate in a fresh clone) gets 30 minutes, since its floor could be anything up to pytest's.
 */
import type { GateSpec } from './manifest';

/** No measured gate is killed sooner than this. */
export const GATE_TIMEOUT_FLOOR_MS = 300_000;
/** Headroom over the slowest measurement: load and a cold cache only ever add time. */
export const GATE_TIMEOUT_FACTOR = 4;
/** A gate declared `slow` with no measurement anywhere. */
export const GATE_TIMEOUT_UNMEASURED_SLOW_MS = 1_800_000;
/** SIGTERM to the gate's process group, then SIGKILL after this; the runner settles the gate after twice this even when a descendant that left the group still holds its pipes. */
export const KILL_GRACE_MS = 5_000;

/**
 * The kill timer for one gate, in ms. `measuredMs` is the slowest measurement known of it, undefined when there is none; `overrideMs` is `--gate-timeout`, which wins outright.
 */
export function gateTimeoutMs(
  spec: Pick<GateSpec, 'slow'>,
  measuredMs: number | undefined,
  overrideMs?: number
): number {
  if (overrideMs !== undefined) return overrideMs;
  if (measuredMs === undefined || !Number.isFinite(measuredMs) || measuredMs <= 0)
    return spec.slow === true ? GATE_TIMEOUT_UNMEASURED_SLOW_MS : GATE_TIMEOUT_FLOOR_MS;
  return Math.max(GATE_TIMEOUT_FLOOR_MS, Math.ceil(GATE_TIMEOUT_FACTOR * measuredMs));
}

/** The slowest of several measurements of one gate, ignoring absent and non-positive ones; undefined when none is usable. */
export function slowestMeasurement(...ms: readonly (number | undefined)[]): number | undefined {
  const kept = ms.filter((n): n is number => n !== undefined && Number.isFinite(n) && n > 0);
  return kept.length === 0 ? undefined : Math.max(...kept);
}

/** Selftest for the pure part: both directions of every branch. Returns the assertion count, or throws with the first failure. */
export function gateTimeoutSelftest(): number {
  const cases: [string, number, number][] = [
    ['an unmeasured fast gate gets the floor', gateTimeoutMs({}, undefined), GATE_TIMEOUT_FLOOR_MS],
    [
      'an unmeasured slow gate gets the slow default',
      gateTimeoutMs({ slow: true }, undefined),
      GATE_TIMEOUT_UNMEASURED_SLOW_MS,
    ],
    ['a 2 s gate is held up to the floor', gateTimeoutMs({}, 2_000), GATE_TIMEOUT_FLOOR_MS],
    [
      'a 529.2 s gate gets FACTOR x its measurement',
      gateTimeoutMs({ slow: true }, 529_200),
      Math.ceil(GATE_TIMEOUT_FACTOR * 529_200),
    ],
    [
      '--gate-timeout wins over a measurement',
      gateTimeoutMs({ slow: true }, 529_200, 1_000),
      1_000,
    ],
    ['a zero measurement counts as none', gateTimeoutMs({}, 0), GATE_TIMEOUT_FLOOR_MS],
    ['the slowest measurement is the max', slowestMeasurement(3, undefined, 7, 0) ?? -1, 7],
    ['no usable measurement is undefined', slowestMeasurement(undefined, 0) ?? -1, -1],
  ];
  for (const [what, got, want] of cases)
    if (got !== want) throw new Error(`gate-timeout: ${what}: got ${got}, want ${want}`);
  return cases.length;
}

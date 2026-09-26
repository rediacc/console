#!/usr/bin/env tsx
/**
 * The lane-duration budget: no CI leg should cost more than 12 minutes, no lane's
 * single indivisible unit should either, and the numbers behind that verdict must stay
 * fresh (operator spec W, PLAN-ci-time-budget T3.1).
 *
 * TWO HALVES, LIKE THE HEADROOM GATE ITS FRESHNESS RULE MIRRORS
 * (`.ci/scripts/quality/check_job_timeout_headroom.py`). This must run offline and
 * deterministically -- `npm run ci` has no network and no CI token -- so every number it
 * judges is COMMITTED: `.ci/config/lane-durations.json` (T2.9/T3.2, `budget_report.py
 * --refresh` rewrites it from real green runs) and `.ci/config/shards/<lane>.json`
 * (T2.10, `gate-bind --write` regenerates it from the same `shardPlan` the matrix emitter
 * uses). Nothing here re-derives a plan or shells out to a runner; a sharded lane's legs
 * come from the COMMITTED manifest, exactly as review saw it, not from a fresh
 * `shardPlan` call that could silently disagree with what actually shipped.
 *
 * SIX CHECKS LIVE, ONE DOES NOT YET.
 *
 *   1. Per-leg estimate (sharded lanes): each committed leg's fixed job cost plus the
 *      p90 of its own units, red over 12 minutes, naming the top 3 units.
 *   2. Unsharded job: the same arithmetic over a single leg holding every lock entry
 *      the lane owns -- an unsharded lane IS a shard of one.
 *   3. Single unit: a unit whose own cost plus the lane's fixed cost exceeds 12 minutes
 *      is red even alone, "indivisible", unless `LANE_BUDGET_EXEMPTIONS` names it
 *      (D-W3: every entry there is an operator approval, and the list starts empty).
 *   4. Unknown units: an id with no measured cost is red unless the lane declares
 *      `defaultUnitMs` (T3.1's own addition to the schema, additive and optional --
 *      `lane-durations.json` names none today). A new unit cannot enter unmeasured.
 *   5. Freshness: red when `refreshed_at` is missing, unparseable, or older than 14
 *      days -- the same "missing counts as infinitely stale" rule
 *      `check_job_timeout_headroom.py` already applies to its own baseline.
 *   6. Pipeline: a critical-path-plus-queueing estimate against a 20-minute target,
 *      printed always and asserted only once `PIPELINE_ENFORCED` flips (D-W1 is not yet
 *      decided). THE ESTIMATE IS A DELIBERATE SIMPLIFICATION: a real critical path needs
 *      the full `needs:` graph of every job in `ci.yml` and its callees, most of which
 *      carry no lane-budget data at all; this uses the worst measured leg per lane as a
 *      stand-in, which is sound as an advisory upper bound (no lane's real critical-path
 *      contribution exceeds its own worst leg) but is NOT the graph-weighted figure the
 *      box asks for. Naming that gap here rather than quietly shipping the approximation
 *      as the real thing.
 *
 * CHECK 7 EXISTS AND IS SELFTESTED, AND MUST STAY OUT OF `main()`'S FINDINGS. T4.4 is
 * the box that turns it on; flipping `CHECK7_ENABLED` here before every job in `ci.yml`
 * carries a real `timeout-minutes: 15` would red the pipeline for a policy nothing has
 * adopted yet.
 *
 * WHAT THIS READS AND WHY EACH FAILS LOUDLY TODAY IF THE DATA IS NOT THERE.
 * `.ci/config/lane-durations.json` was seeded 2026-09-26 with `refreshed_at: null` and
 * empty `jobs`/`units` (T2.9's own comment says so), because `budget_report.py --refresh`
 * (T3.2) has not run yet. Check 5 therefore reds on a real invocation today, and checks
 * 1/2/4 report every measured lane's units as unknown for the same reason. That is NOT a
 * bug in this gate: it is the honest state of "the box that produces the numbers has not
 * landed yet", read exactly the same way `check_job_timeout_headroom.py` reads a baseline
 * nobody has ever refreshed. `--selftest` proves the LOGIC against a fixture root
 * (`LANE_BUDGET_ROOT`) rather than against that seeded file, and is what CI and `npm run
 * ci` actually gate on before a `--write` regenerates the workflow around this entry.
 *
 * Usage:
 *   npx tsx scripts/gates/check-lane-budget.ts             the real run, against committed data
 *   npx tsx scripts/gates/check-lane-budget.ts --selftest  prove the logic can fail
 *
 * ---- gate ----
 * step: Lane budget
 * lane: quality-code
 * needs: node
 * selftest: true
 * emit: false
 * blocker: .ci/config/lane-durations.json holds no measurements until PLAN-ci-time-budget T3.2 (budget_report.py --refresh) and T1.6 (unit-duration artifacts) land, and checks 4 and 5 red on missing data rather than a real overrun; it runs by hand until then (2026-09-26).
 * why: a CI leg that quietly grows past 12 minutes is invisible until the pipeline as a
 *   whole misses its 20-minute target; this asserts the committed duration estimates
 *   against both ceilings before that happens on a real runner
 * ---- end gate ----
 */

import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import {
  type LaneCapabilities,
  laneCapabilities,
  mergeLaneCapabilities,
  SHARD_COUNTS,
  type ShardInput,
  shardPlan,
  TEST_LANE_WORKFLOWS,
} from '../ci-runner/lanes.js';
import {
  legIds as _legIds,
  parseShardManifest,
  shardManifestPath,
} from '../ci-runner/shard-manifest.js';
import { GREEN, NC, RED } from '../lib/console.js';
import { summarizeControls } from '../lib/controls.js';
import { envRoot } from '../lib/repo-root.js';

// imported for readers following the manifest module; this gate reads `legs` directly to report every leg, not one at a time.
void _legIds;

const ROOT = envRoot('LANE_BUDGET_ROOT');
const DURATIONS_PATH = '.ci/config/lane-durations.json';
const LOCK_PATH = 'scripts/ci-runner/gates.lock.json';
const QUALITY_WORKFLOW = '.github/workflows/ci-quality.yml';

export const PER_LEG_BUDGET_MIN = 12;
export const PIPELINE_BUDGET_MIN = 20;
export const MAX_STALENESS_DAYS = 14;
export const CHECK7_TIMEOUT_MAX_MIN = 15;

/** T4.4 flips this on. See the file header: check 7 must exist and be selftested first. */
export const CHECK7_ENABLED = false;

/** D-W1 decides whether check 6 is enforced. Advisory (printed, never a finding) until then. */
export const PIPELINE_ENFORCED = false;

/**
 * D-W3-approved exemptions: a unit id whose own cost exceeds the per-leg budget even in
 * a shard of one. Empty today -- every entry here needs an operator approval recorded
 * beside it, the same discipline `SHARD_REPLICATED_MAX` and the other declared ceilings
 * in `lanes.ts` are held to.
 */
export const LANE_BUDGET_EXEMPTIONS: readonly string[] = [];

export interface LaneDurations {
  refreshed_at: string | null;
  concurrency: number;
  /** MINUTES: each job's fixed cost, p90, setup through the first runner step. */
  jobs: Record<string, number>;
  /** MILLISECONDS: each unit id's own p90, keyed exactly as `lanes.ts`/`unit-enumerators.ts` name it. */
  units: Record<string, number>;
  /**
   * T3.1's own addition to the schema: a lane that opts a not-yet-measured unit out of
   * check 4 by naming a per-unit fallback cost, in milliseconds. Optional and additive --
   * `lane-durations.json` declares none today, so every unit lacking a `units` entry is
   * unknown, full stop. That is the safe default: a silently-assumed cost hides a slow
   * new test exactly as effectively as no check at all.
   */
  defaultUnitMs?: Record<string, number>;
}

export function readDurations(root: string): LaneDurations {
  const parsed = JSON.parse(
    readFileSync(path.join(root, DURATIONS_PATH), 'utf-8')
  ) as Partial<LaneDurations>;
  return {
    refreshed_at: parsed.refreshed_at ?? null,
    concurrency: typeof parsed.concurrency === 'number' ? parsed.concurrency : 0,
    jobs: parsed.jobs ?? {},
    units: parsed.units ?? {},
    defaultUnitMs: parsed.defaultUnitMs,
  };
}

// --------------------------------------------------------------------------- Check 5: freshness ---------------------------------------------------------------------------

/**
 * Missing or unparseable counts as INFINITELY stale, not as "unknown, skip it" -- the
 * same rule `check_job_timeout_headroom.py` applies to a baseline nobody has refreshed
 * (`stale = -1`, judged exactly like an age over the limit). A gate that let "never
 * refreshed" slide would be silent on the one state this box exists to catch first.
 */
export function freshnessFindings(
  durations: Pick<LaneDurations, 'refreshed_at'>,
  now: Date
): string[] {
  if (durations.refreshed_at === null) {
    return [
      `${DURATIONS_PATH} has never been refreshed (refreshed_at is null). Run ` +
        'budget_report.py --refresh (T3.2) before these numbers can back a real verdict.',
    ];
  }
  const refreshed = new Date(durations.refreshed_at);
  if (Number.isNaN(refreshed.getTime())) {
    return [
      `${DURATIONS_PATH}'s refreshed_at ("${durations.refreshed_at}") does not parse as a date.`,
    ];
  }
  const ageDays = (now.getTime() - refreshed.getTime()) / 86_400_000;
  if (ageDays > MAX_STALENESS_DAYS) {
    return [
      `${DURATIONS_PATH} was last refreshed ${ageDays.toFixed(1)} day(s) ago, over the ` +
        `${MAX_STALENESS_DAYS}-day limit. Its numbers no longer describe real CI.`,
    ];
  }
  return [];
}

// --------------------------------------------------------------------------- Checks 1/2/3/4: leg and unit cost ---------------------------------------------------------------------------

export interface UnitCost {
  id: string;
  /** null means unknown: no measured cost and no lane default. */
  ms: number | null;
}

/** The leg's own total, in milliseconds, plus which ids came back unknown. */
export function legCostMs(
  ids: readonly string[],
  units: Readonly<Record<string, number>>,
  defaultUnitMs: number | undefined
): { totalMs: number; unknown: string[]; perUnit: UnitCost[] } {
  const perUnit: UnitCost[] = [];
  const unknown: string[] = [];
  let totalMs = 0;
  for (const id of ids) {
    const measured = units[id];
    if (measured !== undefined) {
      perUnit.push({ id, ms: measured });
      totalMs += measured;
    } else if (defaultUnitMs !== undefined) {
      perUnit.push({ id, ms: defaultUnitMs });
      totalMs += defaultUnitMs;
    } else {
      perUnit.push({ id, ms: null });
      unknown.push(id);
    }
  }
  return { totalMs, unknown, perUnit };
}

/** Checks 1 (sharded) and 2 (unsharded, `of: 1`): identical arithmetic either way. */
export function legFindings(
  lane: string,
  index: number,
  of: number,
  ids: readonly string[],
  fixedMinutes: number,
  units: Readonly<Record<string, number>>,
  defaultUnitMs: number | undefined
): string[] {
  const findings: string[] = [];
  const { totalMs, unknown, perUnit } = legCostMs(ids, units, defaultUnitMs);
  if (unknown.length > 0) {
    const shown = [...unknown].sort().slice(0, 3);
    findings.push(
      `${lane} leg ${index}/${of}: ${unknown.length} unit(s) have no measured cost and the ` +
        `lane declares no defaultUnitMs: ${shown.join(', ')}` +
        (unknown.length > shown.length ? ', ...' : '') +
        '. A new unit cannot enter unmeasured.'
    );
  }
  const totalMinutes = fixedMinutes + totalMs / 60_000;
  if (totalMinutes > PER_LEG_BUDGET_MIN) {
    const top3 = [...perUnit]
      .filter((u): u is { id: string; ms: number } => u.ms !== null)
      .sort((a, b) => b.ms - a.ms)
      .slice(0, 3)
      .map((u) => `${u.id} (${(u.ms / 60_000).toFixed(1)}m)`);
    findings.push(
      `${lane} leg ${index}/${of}: estimated ${totalMinutes.toFixed(1)}m ` +
        `(${fixedMinutes.toFixed(1)}m fixed + ${(totalMs / 60_000).toFixed(1)}m units), over the ` +
        `${PER_LEG_BUDGET_MIN}m budget. Top unit(s): ${top3.join(', ') || 'none measured'}.`
    );
  }
  return findings;
}

/** Check 3: a single unit that cannot fit a shard of one, however the lane is packed. */
export function indivisibleFindings(
  lane: string,
  laneIds: readonly string[],
  fixedMinutes: number,
  units: Readonly<Record<string, number>>
): string[] {
  const findings: string[] = [];
  for (const id of laneIds) {
    const ms = units[id];
    if (ms === undefined) continue;
    const minutes = fixedMinutes + ms / 60_000;
    if (minutes > PER_LEG_BUDGET_MIN && !LANE_BUDGET_EXEMPTIONS.includes(id)) {
      findings.push(
        `${lane}: unit ${id} alone costs ${minutes.toFixed(1)}m (${fixedMinutes.toFixed(1)}m fixed ` +
          `+ ${(ms / 60_000).toFixed(1)}m), over the ${PER_LEG_BUDGET_MIN}m budget even in a shard of ` +
          'one. Indivisible: split the unit, or record an approved exemption ' +
          '(LANE_BUDGET_EXEMPTIONS, D-W3).'
      );
    }
  }
  return findings;
}

// --------------------------------------------------------------------------- Check 6: pipeline (advisory) ---------------------------------------------------------------------------

/**
 * Critical-path-plus-queueing, over the worst measured leg PER LANE rather than the full
 * `needs:` graph -- see the file header for why that is a sound upper bound and not the
 * final figure T3.1 eventually wants.
 */
export function pipelineEstimateMinutes(
  worstLegPerLaneMinutes: readonly number[],
  concurrency: number
): number {
  const criticalPath = worstLegPerLaneMinutes.length > 0 ? Math.max(...worstLegPerLaneMinutes) : 0;
  const runnerMinutes = worstLegPerLaneMinutes.reduce((a, b) => a + b, 0);
  const queue = concurrency > 0 ? Math.max(0, runnerMinutes / concurrency - criticalPath) : 0;
  return criticalPath + queue;
}

// --------------------------------------------------------------------------- Check 7: present, wired off until T4.4 ---------------------------------------------------------------------------

export function timeoutFindings(
  caps: ReadonlyMap<string, Pick<LaneCapabilities, 'timeoutMinutes'>>
): string[] {
  const findings: string[] = [];
  for (const [job, cap] of caps) {
    if (cap.timeoutMinutes === null || cap.timeoutMinutes > CHECK7_TIMEOUT_MAX_MIN) {
      findings.push(
        `${job}: timeout-minutes is ${cap.timeoutMinutes ?? 'unset'}, over the ` +
          `${CHECK7_TIMEOUT_MAX_MIN}m ceiling T4.4 will enforce.`
      );
    }
  }
  return findings;
}

// --------------------------------------------------------------------------- The real run ---------------------------------------------------------------------------

function readOr(root: string, file: string, what: string): string | null {
  try {
    return readFileSync(path.join(root, file), 'utf-8');
  } catch (e) {
    console.error(`${RED}✗${NC} ${what} could not be read at ${file}: ${String(e)}`);
    return null;
  }
}

function main(): number {
  const qualityText = readOr(ROOT, QUALITY_WORKFLOW, 'the quality workflow');
  const lockText = readOr(ROOT, LOCK_PATH, 'the gate lock');
  if (qualityText === null || lockText === null) return 1;

  let lock: ShardInput[];
  try {
    const parsed: unknown = JSON.parse(lockText);
    if (!Array.isArray(parsed)) throw new Error('the lock is not a JSON array');
    lock = parsed as ShardInput[];
  } catch (e) {
    console.error(`${RED}✗${NC} ${LOCK_PATH} is not a gate array: ${String(e)}`);
    return 1;
  }

  let durations: LaneDurations;
  try {
    durations = readDurations(ROOT);
  } catch (e) {
    console.error(`${RED}✗${NC} ${DURATIONS_PATH} could not be read: ${String(e)}`);
    return 1;
  }

  // Every workflow a test lane can live in, read once each, even when several lanes
  // share one file (mergeLaneCapabilities de-duplicates by path key).
  const workflows: Record<string, string> = { [QUALITY_WORKFLOW]: qualityText };
  for (const wf of new Set(Object.values(TEST_LANE_WORKFLOWS))) {
    if (workflows[wf] !== undefined) continue;
    const text = readOr(ROOT, wf, `the ${wf} workflow`);
    if (text !== null) workflows[wf] = text;
  }
  const caps = mergeLaneCapabilities(workflows);

  const qualityLanes = [...laneCapabilities(qualityText).keys()];
  const allLanes = new Set<string>([...qualityLanes, ...Object.keys(TEST_LANE_WORKFLOWS)]);

  const findings: string[] = [...freshnessFindings(durations, new Date())];
  const worstLegPerLane: number[] = [];

  for (const lane of [...allLanes].sort()) {
    // A test lane not yet split out into its own job (T2.12-T2.16) is not an error at this layer -- TEST_LANE_WORKFLOWS's own docstring calls this state "inert", and `laneCapabilities` simply has no entry for it yet.
    if (!caps.has(lane)) continue;

    const fixedMinutes = durations.jobs[lane] ?? 0;
    const defaultUnitMs = durations.defaultUnitMs?.[lane];

    if (Object.prototype.hasOwnProperty.call(SHARD_COUNTS, lane)) {
      const manifestFile = path.join(ROOT, shardManifestPath(lane));
      if (!existsSync(manifestFile)) {
        findings.push(
          `${lane} is sharded (SHARD_COUNTS) but has no committed manifest at ` +
            `${shardManifestPath(lane)}. Run \`npx tsx scripts/gate-bind.ts --write\` first.`
        );
        continue;
      }
      const manifest = parseShardManifest(readFileSync(manifestFile, 'utf-8'), lane);
      let worst = 0;
      const allIds: string[] = [];
      for (const leg of manifest.legs) {
        findings.push(
          ...legFindings(
            lane,
            leg.index,
            manifest.of,
            leg.ids,
            fixedMinutes,
            durations.units,
            defaultUnitMs
          )
        );
        const { totalMs } = legCostMs(leg.ids, durations.units, defaultUnitMs);
        worst = Math.max(worst, fixedMinutes + totalMs / 60_000);
        allIds.push(...leg.ids);
      }
      worstLegPerLane.push(worst);
      findings.push(...indivisibleFindings(lane, allIds, fixedMinutes, durations.units));
    } else {
      const laneIds = lock
        .filter((e) => e.ci.kind === 'step' && e.ci.job === lane)
        .map((e) => e.id);
      // A lane with zero lock-id entries (quality-submodule-branches: hand-written by invariant 11, no step ever pinned there) has nothing this gate can price by this method; not a finding, just nothing to add.
      if (laneIds.length === 0) continue;
      findings.push(
        ...legFindings(lane, 1, 1, laneIds, fixedMinutes, durations.units, defaultUnitMs)
      );
      const { totalMs } = legCostMs(laneIds, durations.units, defaultUnitMs);
      worstLegPerLane.push(fixedMinutes + totalMs / 60_000);
      findings.push(...indivisibleFindings(lane, laneIds, fixedMinutes, durations.units));
    }
  }

  if (CHECK7_ENABLED) findings.push(...timeoutFindings(caps));

  const pipelineMinutes = pipelineEstimateMinutes(worstLegPerLane, durations.concurrency);
  const pipelineNote =
    `pipeline estimate (advisory, worst-leg-per-lane approximation -- see file header): ` +
    `${pipelineMinutes.toFixed(1)}m against a ${PIPELINE_BUDGET_MIN}m target`;
  if (PIPELINE_ENFORCED && pipelineMinutes > PIPELINE_BUDGET_MIN) {
    findings.push(`${pipelineNote}, over budget`);
  }

  if (findings.length === 0) {
    console.log(
      `${GREEN}✓${NC} lane-budget: ${worstLegPerLane.length} lane(s) checked. ${pipelineNote}`
    );
    return 0;
  }
  console.error(`${RED}✗${NC} lane-budget: ${findings.length} finding(s). ${pipelineNote}`);
  for (const f of findings) console.error(`  ${f}`);
  return 1;
}

// --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------

function selftest(): number {
  const cases = [
    // --- check 1/2: the 12-minute per-leg budget, right at the boundary ---------
    {
      name: 'FIRES: a leg estimated at 12.1m',
      ok: legFindings('lane-a', 1, 1, ['u1'], 0, { u1: 12.1 * 60_000 }, undefined).some((f) =>
        f.includes('estimated 12.1m')
      ),
    },
    {
      name: 'MATCH: a leg estimated at 11.9m is no finding',
      ok: legFindings('lane-a', 1, 1, ['u1'], 0, { u1: 11.9 * 60_000 }, undefined).length === 0,
      detail: JSON.stringify(
        legFindings('lane-a', 1, 1, ['u1'], 0, { u1: 11.9 * 60_000 }, undefined)
      ),
    },
    {
      name: 'fixed cost counts toward the same 12-minute ceiling',
      ok: legFindings('lane-a', 1, 1, ['u1'], 10, { u1: 2.1 * 60_000 }, undefined).some((f) =>
        f.includes('estimated 12.1m')
      ),
    },
    {
      name: 'the report names the top 3 units by cost, not just the total',
      ok: (() => {
        const f = legFindings(
          'lane-a',
          1,
          1,
          ['small', 'big', 'mid', 'tiny'],
          0,
          { small: 1 * 60_000, big: 10 * 60_000, mid: 3 * 60_000, tiny: 0.1 * 60_000 },
          undefined
        );
        return f.some(
          (x) => x.includes('big (10.0m)') && x.includes('mid (3.0m)') && !x.includes('tiny')
        );
      })(),
    },
    // --- check 4: unknown units, and the defaultUnitMs escape hatch -------------
    {
      name: 'FIRES: a planted unestimated unit with no lane default',
      ok: legFindings(
        'lane-a',
        1,
        1,
        ['measured', 'new-file'],
        0,
        { measured: 60_000 },
        undefined
      ).some((f) => f.includes('new-file') && f.includes('no defaultUnitMs')),
    },
    {
      name: 'MATCH: the same unestimated unit, once the lane declares defaultUnitMs',
      ok:
        legFindings(
          'lane-a',
          1,
          1,
          ['measured', 'new-file'],
          0,
          { measured: 60_000 },
          5_000
        ).filter((f) => f.includes('no defaultUnitMs')).length === 0,
      detail: JSON.stringify(
        legFindings('lane-a', 1, 1, ['measured', 'new-file'], 0, { measured: 60_000 }, 5_000)
      ),
    },
    {
      name: 'a unit costed by defaultUnitMs still counts toward the 12-minute total',
      ok: legFindings('lane-a', 1, 1, ['a', 'b'], 0, {}, 7 * 60_000).some((f) =>
        f.includes('estimated 14.0m')
      ),
    },
    // --- check 3: a single indivisible unit -------------------------------------
    {
      name: 'FIRES: one unit alone over budget is "indivisible"',
      ok: indivisibleFindings('lane-a', ['heavy-file'], 0, { 'heavy-file': 13 * 60_000 }).some(
        (f) => f.includes('Indivisible')
      ),
    },
    {
      name: 'the exemption branch: an id present in the exemption list is silent even over budget',
      ok: (() => {
        const exempted = 'already-exempt';
        // LANE_BUDGET_EXEMPTIONS ships empty (every entry needs a real operator approval), so the guard is exercised directly here rather than by mutating the exported list.
        const stub = [exempted];
        const guarded = (id: string, ms: number): string[] =>
          ms > PER_LEG_BUDGET_MIN * 60_000 && !stub.includes(id) ? [`${id} indivisible`] : [];
        return (
          guarded(exempted, 20 * 60_000).length === 0 && guarded('other', 20 * 60_000).length === 1
        );
      })(),
    },
    // --- check 5: freshness ------------------------------------------------------
    {
      name: 'FIRES: refreshed_at is null',
      ok: freshnessFindings({ refreshed_at: null }, new Date()).some((f) =>
        f.includes('never been refreshed')
      ),
    },
    {
      name: 'FIRES: refreshed_at is unparseable',
      ok: freshnessFindings({ refreshed_at: 'not-a-date' }, new Date()).some((f) =>
        f.includes('does not parse')
      ),
    },
    {
      name: 'FIRES: refreshed_at is 15 days old',
      ok: (() => {
        const now = new Date('2026-09-26T00:00:00Z');
        const old = new Date(now.getTime() - 15 * 86_400_000).toISOString();
        return freshnessFindings({ refreshed_at: old }, now).some((f) => f.includes('15.0 day'));
      })(),
    },
    {
      name: 'MATCH: refreshed_at is 1 day old',
      ok: (() => {
        const now = new Date('2026-09-26T00:00:00Z');
        const fresh = new Date(now.getTime() - 1 * 86_400_000).toISOString();
        return freshnessFindings({ refreshed_at: fresh }, now).length === 0;
      })(),
    },
    // --- check 6: the pipeline estimate ------------------------------------------
    {
      name: 'pipeline estimate is at least the worst single lane (critical path floor)',
      ok: pipelineEstimateMinutes([5, 8, 3], 20) >= 8,
    },
    {
      name: 'pipeline estimate adds queueing once total work exceeds concurrency',
      ok: pipelineEstimateMinutes([10, 10, 10, 10], 2) > 10,
      detail: String(pipelineEstimateMinutes([10, 10, 10, 10], 2)),
    },
    {
      name: 'CONTROL: an empty pipeline is zero, not NaN or a crash',
      ok: pipelineEstimateMinutes([], 20) === 0,
    },
    // --- check 7: present, selftested, and NOT wired into main() yet -------------
    {
      name: 'FIRES (the function itself): a job over the 15-minute ceiling',
      ok: timeoutFindings(new Map([['job-a', { timeoutMinutes: 90 }]])).some((f) =>
        f.includes('over the 15m')
      ),
    },
    {
      name: 'FIRES (the function itself): a job with no timeout-minutes at all',
      ok: timeoutFindings(new Map([['job-a', { timeoutMinutes: null }]])).some((f) =>
        f.includes('unset')
      ),
    },
    {
      name: 'MATCH: a job at exactly 15 minutes is fine',
      ok: timeoutFindings(new Map([['job-a', { timeoutMinutes: 15 }]])).length === 0,
    },
    {
      name: 'CHECK 7 IS OFF: the exported flag T4.4 will flip is false today',
      ok: CHECK7_ENABLED === false,
    },
    // --- legCostMs itself ----------------------------------------------------------
    {
      name: 'legCostMs sums measured units and lists the unmeasured ones separately',
      ok: (() => {
        const { totalMs, unknown } = legCostMs(['a', 'b', 'c'], { a: 1000, c: 3000 }, undefined);
        return totalMs === 4000 && JSON.stringify(unknown) === JSON.stringify(['b']);
      })(),
    },
    // --- CONTROL: quality-code's committed plan is unchanged ----------------------
    {
      name: "CONTROL: quality-code's committed manifest still agrees with a fresh shardPlan over the live lock",
      ok: (() => {
        const manifestFile = path.join(ROOT, shardManifestPath('quality-code'));
        if (!existsSync(manifestFile)) return false;
        const manifest = parseShardManifest(readFileSync(manifestFile, 'utf-8'), 'quality-code');
        const workflowText = readFileSync(path.join(ROOT, QUALITY_WORKFLOW), 'utf-8');
        const live = JSON.parse(readFileSync(path.join(ROOT, LOCK_PATH), 'utf-8')) as ShardInput[];
        const plan = shardPlan(live, laneCapabilities(workflowText), SHARD_COUNTS);
        if ('error' in plan) return false;
        const fresh = plan.lanes.find((l) => l.lane === 'quality-code');
        if (fresh === undefined) return false;
        if (fresh.shards.length !== manifest.legs.length) return false;
        return fresh.shards.every((s) => {
          const leg = manifest.legs.find((l) => l.index === s.index);
          return leg !== undefined && JSON.stringify(leg.ids) === JSON.stringify(s.ids);
        });
      })(),
    },
    {
      name: 'CONTROL: the live lane-durations.json parses under readDurations with no crash',
      ok: (() => {
        readDurations(ROOT);
        return true;
      })(),
    },
  ];

  return summarizeControls(cases);
}

process.exit(process.argv.includes('--selftest') ? selftest() : main());

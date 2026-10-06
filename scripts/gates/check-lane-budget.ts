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
 * --refresh` rewrites it from real green runs), the `.ci/config/shards/<lane>.json` manifests
 * and `.ci/tutorials/run-sequence.sh`'s `MEASURED_SHARD_SIZES`. Only quality-code's manifest is
 * generated (`gate-bind --write`, from `shardPlan` over `SHARD_COUNTS`, which names no other
 * lane); every test-lane manifest is packed by hand, and so is the OPS Provision split. Nothing
 * here re-derives a plan or shells out to a runner; a lane's legs come from what is COMMITTED,
 * exactly as review saw it, not from a fresh `shardPlan` call that could silently disagree
 * with what actually shipped.
 *
 * SEVEN CHECKS, ALL LIVE (check 7 since T4.4, 2026-09-30).
 *
 *   1. Per-leg estimate: each committed leg's fixed job cost plus the p90 of its own
 *      units, red over 12 minutes, naming the top 3 units. Every lane with a committed
 *      `.ci/config/shards/<lane>.json` is priced from it (quality-code, quality-pytest and
 *      the test lanes), whether or not `SHARD_COUNTS` names it.
 *   2. Unsharded job: a quality lane with no manifest is a shard of one over its lock
 *      entries. Every OTHER runner job in `ci.yml` and its callees is judged on its whole-job
 *      p90 (`job_p90_minutes`, keyed by Actions display name and mapped back per call site
 *      by `displayNamePattern`), against 12 or against its `JOB_BUDGET_CAPS` ceiling (the
 *      2026-09-28 ruling); a job with no p90 is UNCHECKED, which is a finding. A priced
 *      lane's matrix legs are judged in the lane and skipped here.
 *   3. Single unit: a unit whose own cost plus the lane's fixed cost exceeds 12 minutes
 *      is red even alone, "indivisible", unless `LANE_BUDGET_EXEMPTIONS` names it (D-W3).
 *      An exemption whose test file or job has gone is itself a finding.
 *   4. Unknown units: an id with no measured cost is red unless the lane declares
 *      `defaultUnitMs`. A new unit cannot enter unmeasured.
 *   5. Freshness: red when `refreshed_at` is missing, unparseable, or older than 14
 *      days -- the same "missing counts as infinitely stale" rule
 *      `check_job_timeout_headroom.py` already applies to its own baseline.
 *   6. Pipeline: a critical-path-plus-queueing estimate against D-W1's 35-minute target,
 *      printed always and never a finding (`PIPELINE_ENFORCED`). THE ESTIMATE IS A
 *      DELIBERATE SIMPLIFICATION: it uses the worst leg per lane (plus each judged job) as
 *      a stand-in for the full `needs:` graph, which is a sound advisory upper bound on
 *      any one lane's critical-path contribution but NOT the graph-weighted figure the box
 *      eventually wants.
 *
 *   7. Timeouts (T4.1/T4.4): every runner job in `ci.yml` and its callees, read once per
 *      defining workflow, declares a job-level `timeout-minutes` of 15 or less; the two
 *      `JOB_BUDGET_CAPS` jobs are read against their ruling timeouts (K8s Ceph 25, K8s
 *      Multinode 30). Unset, or a value that resolves to no number, is red. A
 *      `${{ matrix.<key> }}` value resolves to the largest `<key>:` the job's strategy sets.
 *
 * A RED REAL RUN IS MEASURED OVERRUN, NOT A GATE DEFECT. Since budget_report.py writes
 * manifest-shaped unit ids and `job_p90_minutes` (2026-09-28), what the real run reports is
 * a leg or job whose measured cost is over its ceiling, a job no sampled run completed
 * successfully (UNCHECKED; operator ruling 2026-09-29 on #5a954657: unknown stays red), or
 * a job whose `timeout-minutes` is over 15. The fix is in the lane, the workflow or an
 * operator ruling, never here. `--selftest` proves the logic against fixtures and the real
 * exemption and cap tables.
 *
 * PARALLEL LANES (`unitParallelism`). quality-pytest runs `pytest -n <cores> --dist loadgroup`
 * per leg, `-n` sized from the leg machine's cores at launch (check_pytest.py `jobs()`, no static
 * width since 2026-10-05). `budget_report --refresh` DERIVES the value from the lane job's `runs-on`
 * label and its documented vCPU count (4 on ubuntu-latest), keeping the prior value when it cannot;
 * nothing hand-writes it. Its per-file serial p90s are divided by the workers and floored at the largest
 * xdist group (enumerator `mutex`, plus a module-level `XDIST_GROUP`). Serial arithmetic
 * put those legs at 30-41m against a measured 8-12m.
 *
 * MEASURED LEGS. A priced lane's legs are judged twice: the unit-sum estimate (checks 1/4)
 * and the leg's own measured p90 by display name.
 *
 * VARIANT LEGS (`variantCosts`, 2026-09-28). One fixed cost per lane cannot price E2E Workers:
 * its globalSetup VM reset alone runs 1.5 minutes on debian and 3-4 on fedora, opensuse and
 * oracle, and budget_report's unit p90s sum test durations, which leave out beforeAll and
 * afterAll work. A lane named in `variantCosts` is priced once per matrix variant, with that
 * variant's own fixed cost, per-leg extras and per-unit wall costs; `VARIANT_PRICED_LANES` must
 * have an entry, because a lane that loses its entry (a hand edit, a refresh that measured
 * nothing and had no prior value) would otherwise fall back to the single fixed cost and under-price every leg by 3-5 minutes. The
 * OPS Provision lane (`ops-tutorials`, job `ops-vm-provision`) is priced the same way, its legs
 * the contiguous slices `run-sequence.sh` cuts (`CONTIGUOUS_LANES`). `--table` prints each
 * variant leg's prediction beside its measured p90, which is how the model is validated.
 *
 * REBALANCE (`--rebalance <lane>`, 2026-09-28). The three hand-packed test lanes drift back over budget as their tests change, so `--rebalance` re-plans one on this gate's own pricing (`legMinutes`, per variant), which is what keeps the balance and the verdict from disagreeing: quality-pytest by LPT over indivisible blocks (a mutex group is one block), test-e2e-workers by exact branch and bound on the worst leg over every distro, ops-tutorials exhaustively over contiguous slice sizes.
 * The placement rules are data, `lane-durations.json`'s `rebalanceConstraints` (together, onLeg, notOnLeg, each with its reason). Local search then evens the other legs, and the committed plan is kept unless some leg, compared worst first, improves by more than REBALANCE_WRITE_EPS_MIN, so a second run over a written plan is a no-op.
 * It prints the before/after table and the diff, writes only with `--write`, and refuses a rule no plan can meet or a unit with no measured cost, naming them. The real run reds a committed plan that breaks a rule and prints "rebalance available" when the worst leg would gain more than REBALANCE_ADVISORY_MIN; that line is advisory, not a finding.
 *
 * Usage:
 *   npx tsx scripts/gates/check-lane-budget.ts             the real run, against committed data
 *   npx tsx scripts/gates/check-lane-budget.ts --table     the same, plus predicted vs measured per variant leg
 *   npx tsx scripts/gates/check-lane-budget.ts --selftest  prove the logic can fail
 *   npx tsx scripts/gates/check-lane-budget.ts --rebalance <lane> [--write]
 *       re-plan quality-pytest, test-e2e-workers or ops-tutorials on this model; dry run unless --write
 *
 * ---- gate ----
 * step: Lane budget
 * lane: quality-code
 * needs: node
 * selftest: true
 * emit: false
 * blocker: the live run's one remaining finding is check 2 on the three E2E Probe jobs (aggregate, list-files, probe-file), which run only on a PR labelled e2e-dependency-probe and have no measured p90 yet; #591 carries the label, and the budget_report --refresh after its run lets this line, the manifest's gate: true and the quality-code step land together (worklist #eaddeba0)
 * why: a CI leg that quietly grows past 12 minutes is invisible until the pipeline as a
 *   whole misses its 35-minute target (D-W1); this asserts the committed duration estimates
 *   against both ceilings before that happens on a real runner
 * ---- end gate ----
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import {
  laneCapabilities,
  measuredStepDurations,
  mergeLaneCapabilities,
  SHARD_COUNTS,
  SHARD_LEG_CAP_MIN,
  type ShardInput,
  shardPlan,
  TEST_LANE_WORKFLOWS,
} from '../ci-runner/lanes.js';
import {
  legIds as _legIds,
  buildShardManifest,
  parseShardManifest,
  shardManifestPath,
} from '../ci-runner/shard-manifest.js';
import { LANE_ENUMERATORS } from '../ci-runner/unit-enumerators.js';
import { GREEN, NC, RED } from '../lib/console.js';
import { summarizeControls } from '../lib/controls.js';
import { envRoot } from '../lib/repo-root.js';

// imported for readers following the manifest module; this gate reads `legs` directly to report every leg, not one at a time.
void _legIds;

const ROOT = envRoot('LANE_BUDGET_ROOT');
const DURATIONS_PATH = '.ci/config/lane-durations.json';
const LOCK_PATH = 'scripts/ci-runner/gates.lock.json';
const QUALITY_WORKFLOW = '.github/workflows/ci-quality.yml';
const CI_WORKFLOW = '.github/workflows/ci.yml';

/** The one per-leg ceiling: gate-bind's re-plan hysteresis (`stickyShardPlan`) holds a committed shard leg to the same number. */
export const PER_LEG_BUDGET_MIN = SHARD_LEG_CAP_MIN;
/** D-W1 as revised 2026-09-25 (Operator rulings): GitHub Free, 20 concurrent jobs, a pipeline target of about 35 minutes, not 20. */
export const PIPELINE_BUDGET_MIN = 35;
export const MAX_STALENESS_DAYS = 14;
export const CHECK7_TIMEOUT_MAX_MIN = 15;

/** T4.4 (2026-09-30): check 7 is on. The selftest pins it on, so turning it off is a visible edit, not a drift. */
export const CHECK7_ENABLED = true;

/** Check 6 stays advisory: D-W1's text makes it red only once the P4 run-level cancel lands. Printed always, never a finding. */
export const PIPELINE_ENFORCED = false;

/**
 * Check 3's operator-approved exemptions: a unit whose own cost exceeds the per-leg budget
 * even in a shard of one. Every entry names the ruling that approved it, and nothing else
 * may be added without one. `unit` is the spec path under `packages/e2e-tests/tests/`,
 * matched against a unit id either exactly or as its `<lane>:` suffix; `job` is the job that
 * runs it. The liveness check in `main()` reds an entry whose file or job no longer exists,
 * so a deleted test cannot leave a silent hole behind it.
 */
export interface UnitExemption {
  unit: string;
  job: string;
  ruling: string;
}
export const LANE_BUDGET_EXEMPTIONS: readonly UnitExemption[] = [
  {
    unit: 'kube/17-multinode-cluster.test.ts',
    job: 'test-e2e-k8s-multinode',
    ruling:
      'D-W3 (operator, 2026-09-25): one 10.9-min test stays whole; T2.18 dropped (PLAN-ci-time-budget, Operator rulings)',
  },
  {
    unit: 'kube/15-k8s-repo.test.ts',
    job: 'test-e2e-k8s',
    ruling:
      'D-W3 (operator, 2026-09-25): one 7.3-min test stays whole; T2.18 dropped (PLAN-ci-time-budget, Operator rulings)',
  },
];

export function unitExemption(
  id: string,
  exemptions: readonly UnitExemption[] = LANE_BUDGET_EXEMPTIONS
): UnitExemption | undefined {
  return exemptions.find((e) => id === e.unit || id.endsWith(`:${e.unit}`));
}

/**
 * Check 2's job-level caps: a named job judged against its own p90 ceiling instead of the
 * 12-minute budget. The two jobs the 2026-09-28 ruling kept exempt (E2E Ceph, E2E Ceph
 * Workers and E2E K8s LEFT the list that day and are judged at 12 like every other job),
 * plus E2E Ceph Workers non-apt by ruling #fc4f34f8 (2026-09-30). Nothing is added without a
 * ruling. `timeoutMinutes` is the ruling's `timeout-minutes` for the job, read by check 7.
 */
export interface JobCap {
  job: string;
  p90Minutes: number;
  timeoutMinutes: number;
  ruling: string;
}
export const JOB_BUDGET_CAPS: readonly JobCap[] = [
  {
    job: 'validate-promote',
    p90Minutes: 15,
    timeoutMinutes: 20,
    ruling:
      '#641f4f0e (2026-10-06, deferral DEFAULT executed): main promotes the whole edge channel (1,123 objects, growing), main measured 11.2-14.6 min for a month and 15.7 twice (run 37394654719); timeout 20',
  },
  {
    job: 'test-e2e-k8s-ceph',
    p90Minutes: 20,
    timeoutMinutes: 25,
    ruling:
      'Exemption caps 2026-09-28 (#d5ba825c DEFAULT executed): p90 20 / timeout 25, revisited after 10 runs',
  },
  {
    job: 'test-e2e-k8s-multinode',
    p90Minutes: 25,
    timeoutMinutes: 30,
    ruling:
      'Exemption caps 2026-09-28 (#d5ba825c DEFAULT executed): p90 25 / timeout 30, revisited after 10 runs',
  },
  {
    job: 'test-e2e-ceph-workers-rpm',
    p90Minutes: 16,
    timeoutMinutes: 20,
    ruling:
      'Operator ruling #fc4f34f8 (ASKED 2026-09-30T10:38Z): E2E Ceph Workers non-apt p90 16 / timeout 20 (measured p90 fedora 13.6, opensuse 12.5, oracle 15.5)',
  },
  {
    job: 'test-e2e-workers',
    p90Minutes: 12,
    timeoutMinutes: 20,
    ruling:
      'Operator ruling #153aace7 (ASKED 2026-09-30T11:21Z): timeout 20, measured max 15.0 with 48 of 2442 legs over 12; p90 budget unchanged at 12',
  },
  {
    job: 'test-e2e-ceph-workers',
    p90Minutes: 12,
    timeoutMinutes: 20,
    ruling:
      'Operator ruling #153aace7 (ASKED 2026-09-30T11:21Z): timeout 20, measured max 15.1; p90 budget unchanged at 12',
  },
  {
    job: 'build-renet',
    p90Minutes: 12,
    timeoutMinutes: 20,
    ruling:
      'Operator ruling #2847e1b3 (ASKED 2026-09-30T11:21Z): timeout 20, the cold main-push build took 16.7 (run 36670172984); p90 budget unchanged at 12',
  },
];

/*
 * D-W2 (2026-09-30): every job of ci.yml and its callees is budgeted HERE, "Stage Artifacts"
 * and "Validate Promotion" included. `check_job_timeout_headroom.py` skips a job this graph
 * reaches (its `lane_budgeted_names`) and keeps the 1.5x rule only for jobs outside it.
 */

export interface LaneDurations {
  refreshed_at: string | null;
  concurrency: number;
  /** MINUTES: each job's fixed cost, p90, setup through the first runner step. */
  jobs: Record<string, number>;
  /** MILLISECONDS: each unit id's own p90, keyed exactly as `lanes.ts`/`unit-enumerators.ts` name it. */
  units: Record<string, number>;
  /**
   * T3.1's own addition to the schema: a lane that opts a not-yet-measured unit out of
   * check 4 by naming a per-unit fallback cost, in milliseconds. Hand-authored and preserved
   * by `budget_report.py --refresh`; each value's derivation is in the file's `$comment`.
   * A lane NOT named here keeps the safe default: every unit lacking a `units` entry is
   * unknown, full stop.
   */
  defaultUnitMs?: Record<string, number>;
  /**
   * MINUTES: a job's whole-job p90 (success-only), keyed by its Actions DISPLAY NAME
   * ("Tests + Infra / E2E K8s Ceph", "Quality / Pytest (2/3)"), written by
   * `budget_report.py --refresh`. `displayNamePattern` maps each key back to a job id: a
   * priced lane's matrix legs are judged in the lane, every other job in check 2, and a job
   * no key matches is UNCHECKED.
   */
  job_p90_minutes?: Record<string, number>;
  /**
   * How many units a lane's leg runs AT ONCE (T3.1, 2026-09-28). A lane absent here runs its
   * units one after another. Each value's source is cited in the file's `$comment`.
   */
  unitParallelism?: Record<string, number>;
  /** Per-matrix-variant leg pricing, `{lane: {variant: VariantCost}}` (see the file header and the JSON's `$comment`). */
  variantCosts?: Record<string, Record<string, VariantCost>>;
  /** The placement rules `--rebalance` honours and the real run enforces on the committed plan, `{lane: RebalanceConstraints}` (hand-authored; `budget_report.py --refresh` preserves it). */
  rebalanceConstraints?: Record<string, RebalanceConstraints>;
}

/** One matrix variant's measured costs: `fixedMinutes` every leg pays, `legExtraMinutes` keyed by leg index, and `units` in ms, which override the top-level `units` for this variant. */
export interface VariantCost {
  fixedMinutes: number;
  legExtraMinutes?: Record<string, number>;
  units?: Record<string, number>;
}

/** The lanes whose legs are priced per variant; a missing `variantCosts` entry for one is a finding, not a fall back. */
export const VARIANT_PRICED_LANES: readonly string[] = ['test-e2e-workers', 'ops-tutorials'];

/**
 * A lane whose legs are contiguous slices of its enumerator's ordered units rather than a
 * committed manifest, and the job that runs it. `run-sequence.sh` slices by
 * `MEASURED_SHARD_SIZES` only while the sizes sum to the unit count, and by ceil(total / N)
 * otherwise; `contiguousLegs` mirrors both branches.
 */
export interface ContiguousLane {
  job: string;
  sizesFile: string;
}
export const CONTIGUOUS_LANES: Readonly<Record<string, ContiguousLane>> = {
  'ops-tutorials': { job: 'ops-vm-provision', sizesFile: '.ci/tutorials/run-sequence.sh' },
};

/** `MEASURED_SHARD_SIZES=(7 3 5 3)` from a shell script, or null when the array is absent. */
export function parseShardSizes(text: string): number[] | null {
  const m = /^\s*MEASURED_SHARD_SIZES=\(([\d\s]+)\)/m.exec(text);
  if (m === null) return null;
  const sizes = (m[1] as string).trim().split(/\s+/).map(Number);
  return sizes.length > 0 && sizes.every((n) => Number.isInteger(n) && n > 0) ? sizes : null;
}

/** `run-sequence.sh`'s slicing, both branches: the measured sizes when they cover every unit, else ceil(total / of) per leg. */
export function contiguousLegs(
  ids: readonly string[],
  sizes: readonly number[],
  of: number
): { index: number; ids: string[] }[] {
  const measured = sizes.length === of && sizes.reduce((a, b) => a + b, 0) === ids.length;
  const legs: { index: number; ids: string[] }[] = [];
  let start = 0;
  for (let i = 1; i <= of; i++) {
    const chunk = measured ? (sizes[i - 1] as number) : Math.ceil(ids.length / of);
    const from = measured ? start : (i - 1) * chunk;
    legs.push({ index: i, ids: ids.slice(from, from + chunk) });
    start += chunk;
  }
  return legs;
}

/** The matrix variant a display name carries before its leg: "fedora-43" in "(fedora-43, 1/8)"; null for "(3/3)" or no suffix. */
export function variantOf(label: string): string | null {
  const m = /\(([^,()]+), \d+\/\d+\)$/.exec(label);
  return m === null ? null : (m[1] as string).trim();
}

/** A leg's fixed minutes and unit table under one variant: its own fixed cost plus the leg's extra, its own unit costs over the lane's. */
export function variantLegInputs(
  variant: VariantCost,
  legIndex: number,
  units: Readonly<Record<string, number>>
): { fixedMinutes: number; units: Record<string, number> } {
  return {
    fixedMinutes: variant.fixedMinutes + (variant.legExtraMinutes?.[String(legIndex)] ?? 0),
    units: { ...units, ...(variant.units ?? {}) },
  };
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
    job_p90_minutes: parsed.job_p90_minutes,
    unitParallelism: parsed.unitParallelism,
    variantCosts: parsed.variantCosts,
    rebalanceConstraints: parsed.rebalanceConstraints,
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

/**
 * A lane whose leg runs several units at once (quality-pytest: `pytest -n <workers> --dist
 * loadgroup`). Every unit in one mutex group runs on ONE worker, one after another, so
 * whichever group is largest is a floor the other workers cannot help with.
 */
export interface LegParallelism {
  workers: number;
  /** The mutex group a unit belongs to, or undefined when it distributes freely. */
  groupOf: (id: string) => string | undefined;
}

/**
 * A leg's unit time under parallelism: the larger of (every known unit's cost / workers)
 * and the largest mutex group's serial cost. With no parallelism, or one worker, it is the
 * plain serial sum `legCostMs` returns. `bound` names which of the two decided it.
 */
export function parallelLegMs(
  perUnit: readonly UnitCost[],
  parallel: LegParallelism | undefined
): { ms: number; bound: string } {
  let serial = 0;
  for (const u of perUnit) serial += u.ms ?? 0;
  if (parallel === undefined || parallel.workers <= 1) return { ms: serial, bound: 'serial' };
  const groups = new Map<string, number>();
  for (const u of perUnit) {
    const g = parallel.groupOf(u.id);
    if (g !== undefined) groups.set(g, (groups.get(g) ?? 0) + (u.ms ?? 0));
  }
  const spread = serial / parallel.workers;
  let worstGroup: [string, number] | undefined;
  for (const entry of groups)
    if (worstGroup === undefined || entry[1] > worstGroup[1]) worstGroup = entry;
  if (worstGroup !== undefined && worstGroup[1] > spread) {
    return {
      ms: worstGroup[1],
      bound: `mutex group ${worstGroup[0]} runs serially on one of ${parallel.workers} workers`,
    };
  }
  return { ms: spread, bound: `${parallel.workers} workers` };
}

/** One leg's predicted minutes: its fixed cost plus its units under the lane's parallelism. The single formula the verdict (`priceLeg`) and `--rebalance` both price with. */
export function legMinutes(
  ids: readonly string[],
  fixedMinutes: number,
  units: Readonly<Record<string, number>>,
  defaultUnitMs: number | undefined,
  parallel: LegParallelism | undefined
): number {
  return (
    fixedMinutes + parallelLegMs(legCostMs(ids, units, defaultUnitMs).perUnit, parallel).ms / 60_000
  );
}

/** Checks 1 (sharded) and 2 (unsharded, `of: 1`): identical arithmetic either way. */
export function legFindings(
  lane: string,
  index: number,
  of: number,
  ids: readonly string[],
  fixedMinutes: number,
  units: Readonly<Record<string, number>>,
  defaultUnitMs: number | undefined,
  parallel?: LegParallelism
): string[] {
  const findings: string[] = [];
  const { unknown, perUnit } = legCostMs(ids, units, defaultUnitMs);
  const { ms: totalMs, bound } = parallelLegMs(perUnit, parallel);
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
        `(${fixedMinutes.toFixed(1)}m fixed + ${(totalMs / 60_000).toFixed(1)}m units` +
        `${parallel !== undefined && parallel.workers > 1 ? `, ${bound}` : ''}), over the ` +
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
  units: Readonly<Record<string, number>>,
  exemptions: readonly UnitExemption[] = LANE_BUDGET_EXEMPTIONS,
  parallel?: LegParallelism
): string[] {
  const findings: string[] = [];
  // Under parallelism the indivisible thing is a MUTEX GROUP (one worker, serially); an ungrouped file's items spread, so its floor is its cost over the workers.
  if (parallel !== undefined && parallel.workers > 1) {
    const groups = new Map<string, number>();
    for (const id of laneIds) {
      const ms = units[id];
      if (ms === undefined) continue;
      const g = parallel.groupOf(id);
      const key = g === undefined ? id : `mutex group ${g}`;
      groups.set(key, (groups.get(key) ?? 0) + (g === undefined ? ms / parallel.workers : ms));
    }
    for (const [key, ms] of groups) {
      const minutes = fixedMinutes + ms / 60_000;
      if (minutes > PER_LEG_BUDGET_MIN && unitExemption(key, exemptions) === undefined) {
        findings.push(
          `${lane}: ${key} alone costs ${minutes.toFixed(1)}m even across ${parallel.workers} ` +
            `workers, over the ${PER_LEG_BUDGET_MIN}m budget. Indivisible: split it, or record ` +
            'an approved exemption (LANE_BUDGET_EXEMPTIONS, D-W3).'
        );
      }
    }
    return findings;
  }
  for (const id of laneIds) {
    const ms = units[id];
    if (ms === undefined) continue;
    const minutes = fixedMinutes + ms / 60_000;
    if (minutes > PER_LEG_BUDGET_MIN && unitExemption(id, exemptions) === undefined) {
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

/**
 * Check 2 over a job that is not a priced lane: its whole-job p90 against 12 minutes, or
 * against its own cap when `JOB_BUDGET_CAPS` names it. A capped job over its CAP is red too:
 * the ruling is a ceiling, not a waiver.
 */
export function jobBudgetFindings(
  jobP90Minutes: Readonly<Record<string, number>>,
  caps: readonly JobCap[] = JOB_BUDGET_CAPS
): string[] {
  return judgeJobSamples(
    Object.entries(jobP90Minutes).map(([job, minutes]) => ({ job, label: job, minutes })),
    caps
  );
}

/** One measured p90 for one job: `label` is the Actions display name it was measured under (a matrix job has one per combination). */
export interface JobSample {
  job: string;
  label: string;
  minutes: number;
}

export function judgeJobSamples(
  samples: readonly JobSample[],
  caps: readonly JobCap[] = JOB_BUDGET_CAPS
): string[] {
  const findings: string[] = [];
  for (const { job, label, minutes } of [...samples].sort((a, b) =>
    a.label.localeCompare(b.label)
  )) {
    const cap = caps.find((c) => c.job === job);
    const limit = cap?.p90Minutes ?? PER_LEG_BUDGET_MIN;
    if (minutes > limit) {
      findings.push(
        cap === undefined
          ? `job ${job}${label === job ? '' : ` ("${label}")`}: p90 ${minutes.toFixed(1)}m, over the ${PER_LEG_BUDGET_MIN}m budget. ` +
              'Shard it, cut its fixed cost, or get an operator ruling into JOB_BUDGET_CAPS.'
          : `job ${job}${label === job ? '' : ` ("${label}")`}: p90 ${minutes.toFixed(1)}m, over its exemption cap of ${limit}m ` +
              `(${cap.ruling}).`
      );
    }
  }
  return findings;
}

export interface WorkflowJob {
  id: string;
  /** The reusable workflow this job calls, or null for a job that runs on a runner itself. */
  uses: string | null;
  /** Its `name:`, quotes stripped; the id when it declares none (the Actions default). */
  name: string;
  hasMatrix: boolean;
  /**
   * Check 7: the job-level `timeout-minutes:` as written (comment stripped), or null when the
   * job declares none. A step-level timeout is not a job's and is never read here.
   */
  timeoutRaw: string | null;
  /**
   * `timeoutRaw` as minutes: a literal number, or `${{ matrix.<key> }}` resolved to the LARGEST
   * `<key>: <n>` the job's own `strategy:` block declares (every leg must fit, so the worst leg
   * is the job's timeout). Null when unset or when it resolves to no number, which check 7
   * reds either way: a timeout nobody can read is not a timeout under 15.
   */
  timeoutMinutes: number | null;
}

/** A workflow's jobs, in order, each with its `name:`, its `uses:`, whether it has a matrix, and its job-level `timeout-minutes`. Hand-parsed for the same reason `laneCapabilities` is. */
export function workflowJobs(text: string): WorkflowJob[] {
  const out: WorkflowJob[] = [];
  // Per job (same index as `out`): every numeric `<key>: <n>` inside its strategy block, for a `${{ matrix.<key> }}` timeout.
  const strategyNumbers: Map<string, number[]>[] = [];
  let inJobs = false;
  let inStrategy = false;
  for (const raw of text.split('\n')) {
    if (/^jobs:\s*$/.test(raw)) {
      inJobs = true;
      continue;
    }
    if (!inJobs) continue;
    if (raw !== '' && !/^\s/.test(raw) && !raw.startsWith('#')) break;
    const job = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(raw);
    if (job) {
      out.push({
        id: job[1] as string,
        uses: null,
        name: job[1] as string,
        hasMatrix: false,
        timeoutRaw: null,
        timeoutMinutes: null,
      });
      strategyNumbers.push(new Map());
      inStrategy = false;
      continue;
    }
    const last = out[out.length - 1];
    if (last === undefined) continue;
    const uses = /^ {4}uses:\s*\.\/(\.github\/workflows\/[A-Za-z0-9_.-]+\.ya?ml)/.exec(raw);
    if (uses) last.uses = uses[1] as string;
    const name = /^ {4}name:\s*(.+?)\s*$/.exec(raw);
    if (name) last.name = (name[1] as string).replace(/^(['"])(.*)\1$/, '$2');
    const timeout = /^ {4}timeout-minutes:\s*(.*?)\s*(?:#.*)?$/.exec(raw);
    if (timeout) last.timeoutRaw = (timeout[1] as string).replace(/^(['"])(.*)\1$/, '$2');
    if (/^ {4}\S/.test(raw)) inStrategy = /^ {4}strategy:\s*$/.test(raw);
    else if (inStrategy) {
      if (/^ {6}matrix:/.test(raw)) last.hasMatrix = true;
      const kv = /^\s+(?:-\s+)?([A-Za-z0-9_-]+):\s*['"]?(\d+(?:\.\d+)?)['"]?\s*(?:#.*)?$/.exec(raw);
      if (kv) {
        const nums = strategyNumbers[strategyNumbers.length - 1] as Map<string, number[]>;
        nums.set(kv[1] as string, [...(nums.get(kv[1] as string) ?? []), Number(kv[2])]);
      }
    }
  }
  out.forEach((j, i) => {
    j.timeoutMinutes = resolveTimeoutMinutes(j.timeoutRaw, strategyNumbers[i] ?? new Map());
  });
  return out;
}

/** `timeoutRaw` to minutes (see `WorkflowJob.timeoutMinutes`). */
export function resolveTimeoutMinutes(
  rawValue: string | null,
  strategyNumbers: ReadonlyMap<string, readonly number[]>
): number | null {
  if (rawValue === null) return null;
  if (/^\d+(?:\.\d+)?$/.test(rawValue)) return Number(rawValue);
  const m = /^\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}$/.exec(rawValue);
  const values = m === null ? undefined : strategyNumbers.get(m[1] as string);
  return values === undefined || values.length === 0 ? null : Math.max(...values);
}

/**
 * The Actions API's display name for a job, as a pattern: every caller's `name:` joined by
 * " / " (a called workflow's job reports as "<caller name> / <its own name>"), each
 * `${{ ... }}` template matching any text, and a matrix job whose `name:` carries no template
 * allowed the " (<values>)" suffix Actions appends itself ("Code (1)"). The TypeScript twin of
 * `budget_report.py`'s `_display_name_pattern`, which writes `job_p90_minutes` under exactly
 * these names; this end maps them back to job ids rather than making the producer guess ids.
 */
export function displayNamePattern(
  chain: readonly string[],
  name: string,
  hasMatrix: boolean
): RegExp {
  const esc = (t: string): string => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const TEMPLATE = /\$\{\{[^}]*\}\}/;
  const own = TEMPLATE.test(name)
    ? name.split(new RegExp(TEMPLATE.source, 'g')).map(esc).join('[^,()]+')
    : esc(name) + (hasMatrix ? '(?: \\([^)]*\\))?' : '');
  return new RegExp(`^${[...chain.map(esc), own].join(' / ')}$`);
}

/** Every measured display name one job id reports under, across all of its call sites. */
export function samplesForJob(
  sites: readonly { id: string; pattern: RegExp }[],
  measured: Readonly<Record<string, number>>,
  job: string
): JobSample[] {
  const out: JobSample[] = [];
  for (const site of sites) {
    if (site.id !== job) continue;
    for (const [label, minutes] of Object.entries(measured)) {
      if (site.pattern.test(label)) out.push({ job, label, minutes });
    }
  }
  return out;
}

/**
 * Which runner jobs check 2 judges: not a priced lane (its matrix legs are judged per leg in
 * the lane); every other job by each display-name sample it has, and a job with none is
 * UNCHECKED.
 */
export function checkTwoPartition(
  runnerJobs: readonly string[],
  priced: ReadonlySet<string>,
  samplesFor: (job: string) => JobSample[]
): { judged: JobSample[]; unchecked: string[] } {
  const judged: JobSample[] = [];
  const unchecked: string[] = [];
  for (const job of runnerJobs) {
    if (priced.has(job)) continue;
    const samples = samplesFor(job);
    if (samples.length === 0) unchecked.push(job);
    else judged.push(...samples);
  }
  return { judged, unchecked };
}

/** The matrix leg index a display name carries: "(3/3)", "(ubuntu-24.04, 2/8)", "(1)". 1 when there is none (an unsharded job is a leg of one). */
export function legIndexOf(label: string): number {
  const m = /(?:\(|, )(\d+)(?:\/\d+)?\)$/.exec(label);
  return m === null ? 1 : Number(m[1]);
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

// --------------------------------------------------------------------------- Check 7: every runner job's timeout-minutes (T4.4) ---------------------------------------------------------------------------

/** One runner job as check 7 reads it: `file` is the workflow that defines it (a job id two callees share is two entries). */
export interface TimeoutSite {
  file: string;
  job: string;
  timeoutRaw: string | null;
  timeoutMinutes: number | null;
}

/**
 * Check 7 (T4.1/T4.4): every runner job in `ci.yml` and its callees declares a job-level
 * `timeout-minutes` of 15 or less, or of its `JOB_BUDGET_CAPS` ruling timeout (K8s Ceph 25,
 * K8s Multinode 30). `timeout-minutes` is the only per-job kill Actions has, so a job without
 * one runs to the 360-minute platform default: unset is red, and so is a value no reader can
 * resolve to a number.
 */
export function timeoutFindings(
  sites: readonly TimeoutSite[],
  jobCaps: readonly JobCap[] = JOB_BUDGET_CAPS
): string[] {
  const findings: string[] = [];
  for (const s of sites) {
    const cap = jobCaps.find((c) => c.job === s.job);
    const ceiling = cap?.timeoutMinutes ?? CHECK7_TIMEOUT_MAX_MIN;
    const why = cap === undefined ? '' : ` (${cap.ruling})`;
    if (s.timeoutRaw === null) {
      findings.push(
        `check 7: ${s.file} job ${s.job} declares no timeout-minutes, so nothing kills it before ` +
          `the 360m platform default; set one of ${ceiling} or less${why}.`
      );
    } else if (s.timeoutMinutes === null) {
      findings.push(
        `check 7: ${s.file} job ${s.job} has timeout-minutes "${s.timeoutRaw}", which resolves to no ` +
          `number; write a literal of ${ceiling} or less, or a matrix key every leg sets${why}.`
      );
    } else if (s.timeoutMinutes > ceiling) {
      findings.push(
        `check 7: ${s.file} job ${s.job} has timeout-minutes ${s.timeoutMinutes}, over the ` +
          `${ceiling}m ceiling${why}.`
      );
    }
  }
  return findings;
}

// --------------------------------------------------------------------------- Rebalance: the committed split against the best one this model finds ---------------------------------------------------------------------------

/** The placement rules a rebalanced plan must honour, read from `lane-durations.json`'s `rebalanceConstraints` (each entry carries its reason in `why`). `together` puts its units on one leg, `onLeg` pins a unit to a leg, `notOnLeg` keeps a unit off one; legs are 1-based. */
export interface RebalanceConstraints {
  together?: { units: string[]; why?: string }[];
  onLeg?: { unit: string; leg: number; why?: string }[];
  notOnLeg?: { unit: string; leg: number; why?: string }[];
}

/** How each rebalanced lane is searched and where its unit set comes from. `assign` places indivisible blocks on any allowed leg; `contiguous` picks slice sizes over the enumerator's order, the way `run-sequence.sh` cuts them. `unitSource: 'manifest'` is for E2E Workers, whose enumerator lists the `--also` suites and not the `#part` buckets the manifest runs (check-shard-manifest-coverage.ts reconciles the two). */
export const REBALANCE_LANES: Readonly<
  Record<string, { shape: 'assign' | 'contiguous'; unitSource: 'enumerator' | 'manifest' }>
> = {
  'quality-pytest': { shape: 'assign', unitSource: 'enumerator' },
  'test-e2e-workers': { shape: 'assign', unitSource: 'manifest' },
  'ops-tutorials': { shape: 'contiguous', unitSource: 'enumerator' },
};

/** The normal run prints "rebalance available" only past this many minutes of gain on the worst leg. Advisory: PLAN-ci-time-budget makes no finding of it. */
export const REBALANCE_ADVISORY_MIN = 0.5;
/** A rebalanced plan replaces the committed one only when some leg, compared worst first, improves by more than this many minutes; a smaller gain is diff noise, and holding the committed plan below it is what keeps a second run a no-op. */
export const REBALANCE_WRITE_EPS_MIN = 0.01;
const SEARCH_EPS_MIN = 1e-6;
/** Exact branch and bound runs only up to this many blocks (E2E Workers has 20); quality-pytest's ~500 get LPT plus local search. */
const BNB_MAX_BLOCKS = 40;
const BNB_NODE_LIMIT = 1_000_000;
/** Local search stops after the step that takes its candidate count past this, and says so (`capped`). A count, not a clock, so a capped result is reproducible; quality-pytest converges in under 1.5M per run. */
const LOCAL_SEARCH_MAX_EVALUATIONS = 10_000_000;
/** The work the live quality-pytest rebalance may spend, both local-search runs together; the BUDGET control holds it. Measured 1,795,571 on 2026-09-29 (516 blocks, 16 + 2 steps). */
export const QUALITY_PYTEST_EVALUATION_BUDGET = 4_000_000;

/** One lane's pricing inputs, per variant and leg, built from exactly what `priceLegs` reads, so a plan's minutes here are the verdict's minutes. A lane with no `variantCosts` has one variant named ''. */
export interface LaneModel {
  lane: string;
  of: number;
  variants: { name: string; fixedByLeg: number[]; units: Record<string, number> }[];
  defaultUnitMs: number | undefined;
  parallel: LegParallelism | undefined;
}

export function laneModel(
  lane: string,
  of: number,
  durations: Pick<LaneDurations, 'jobs' | 'units' | 'defaultUnitMs' | 'variantCosts'>,
  parallel: LegParallelism | undefined
): LaneModel {
  const legs = Array.from({ length: of }, (_, i) => i + 1);
  const cost = durations.variantCosts?.[lane];
  const variants =
    cost === undefined
      ? [
          {
            name: '',
            fixedByLeg: legs.map(() => durations.jobs[lane] ?? 0),
            units: durations.units,
          },
        ]
      : Object.entries(cost)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([name, c]) => ({
            name,
            fixedByLeg: legs.map((i) => variantLegInputs(c, i, durations.units).fixedMinutes),
            units: variantLegInputs(c, 1, durations.units).units,
          }));
  return { lane, of, variants, defaultUnitMs: durations.defaultUnitMs?.[lane], parallel };
}

/** Every leg's minutes under every variant, `[variant][leg]`, each from `legMinutes`. */
export function planMinutes(model: LaneModel, legs: readonly (readonly string[])[]): number[][] {
  return model.variants.map((v) =>
    legs.map((ids, i) =>
      legMinutes(ids, v.fixedByLeg[i] ?? 0, v.units, model.defaultUnitMs, model.parallel)
    )
  );
}

/** Negative when `a` is the better plan: both leg-cost lists sorted worst first, and the first pair differing by more than `eps` decides. */
export function compareCosts(a: readonly number[], b: readonly number[], eps: number): number {
  const x = [...a].sort((p, q) => q - p);
  const y = [...b].sort((p, q) => q - p);
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = (x[i] as number) - (y[i] as number);
    if (Math.abs(d) > eps) return d;
  }
  return 0;
}

/** `kind: 'unknown'` is a unit with no measured cost (check 4 names it too); `'unsatisfiable'` is a constraint no plan can meet. */
export class RebalanceError extends Error {
  constructor(
    readonly kind: 'unknown' | 'unsatisfiable',
    message: string
  ) {
    super(message);
  }
}

/** The rules a plan breaks, one line each; an empty list is a plan the runner can run. */
export function constraintViolations(
  c: RebalanceConstraints,
  legs: readonly (readonly string[])[]
): string[] {
  const legOf = new Map<string, number>();
  legs.forEach((ids, i) => {
    for (const id of ids) legOf.set(id, i + 1);
  });
  const out: string[] = [];
  for (const t of c.together ?? []) {
    const at = t.units.map((u) => legOf.get(u));
    if (new Set(at).size > 1)
      out.push(
        `together (${t.why ?? 'no reason given'}): ${t.units.map((u, i) => `${u} on leg ${at[i] ?? 'none'}`).join(', ')}`
      );
  }
  for (const p of c.onLeg ?? []) {
    const at = legOf.get(p.unit);
    if (at !== p.leg)
      out.push(
        `onLeg (${p.why ?? 'no reason given'}): ${p.unit} must be on leg ${p.leg}, is on leg ${at ?? 'none'}`
      );
  }
  for (const p of c.notOnLeg ?? []) {
    if (legOf.get(p.unit) === p.leg)
      out.push(`notOnLeg (${p.why ?? 'no reason given'}): ${p.unit} must not be on leg ${p.leg}`);
  }
  return out;
}

/** Refuses rules that name a unit the lane does not hold or a leg it does not have: a stale rule is not a satisfied one. */
function staticConstraintProblems(
  c: RebalanceConstraints,
  ids: ReadonlySet<string>,
  of: number
): string[] {
  const out: string[] = [];
  const named = [
    ...(c.together ?? []).flatMap((t) => t.units.map((u) => ({ rule: 'together', unit: u }))),
    ...(c.onLeg ?? []).map((p) => ({ rule: 'onLeg', unit: p.unit })),
    ...(c.notOnLeg ?? []).map((p) => ({ rule: 'notOnLeg', unit: p.unit })),
  ];
  for (const n of named)
    if (!ids.has(n.unit)) out.push(`${n.rule} names ${n.unit}, which the lane does not hold`);
  for (const p of [...(c.onLeg ?? []), ...(c.notOnLeg ?? [])])
    if (!Number.isInteger(p.leg) || p.leg < 1 || p.leg > of)
      out.push(`${p.unit}: leg ${p.leg} is outside 1..${of}`);
  return out;
}

/** Each unit's cost per variant, or a refusal naming every unit (and variant) with none. */
function unitCostsOrThrow(model: LaneModel, ids: readonly string[]): Map<string, number[]> {
  const out = new Map<string, number[]>();
  const unknown: string[] = [];
  for (const id of ids) {
    const per = model.variants.map(
      (v) => legCostMs([id], v.units, model.defaultUnitMs).perUnit[0]?.ms ?? null
    );
    const missing = model.variants.filter((_, i) => per[i] === null).map((v) => v.name || 'all');
    if (missing.length > 0)
      unknown.push(model.variants.length > 1 ? `${id} (${missing.join(', ')})` : id);
    out.set(
      id,
      per.map((x) => x ?? 0)
    );
  }
  if (unknown.length > 0)
    throw new RebalanceError(
      'unknown',
      `${model.lane}: ${unknown.length} unit(s) have no measured cost and the lane declares no defaultUnitMs, so no plan can be priced: ${unknown.sort().join(', ')}`
    );
  return out;
}

export interface RebalanceResult {
  lane: string;
  shape: 'assign' | 'contiguous';
  variants: string[];
  /** The committed plan, or null when it cannot be priced as a candidate (see `coverage`). */
  committed: string[][] | null;
  committedMinutes: number[][] | null;
  /** Rules the committed plan breaks. */
  violations: string[];
  /** Units the committed plan misses or names beyond the lane's set. */
  coverage: string[];
  rebalanced: string[][];
  rebalancedMinutes: number[][];
  /** False when the committed plan is kept: nothing beats it by more than REBALANCE_WRITE_EPS_MIN. */
  changed: boolean;
  /** Committed worst leg minus rebalanced worst leg, in minutes; null when there is no valid committed plan. */
  gainMinutes: number | null;
  search: string;
  /** Candidate plans the search priced: local-search candidates for `assign`, splits for `contiguous`. A count, not a clock, so the budget control over it is reproducible. */
  evaluations: number;
}

interface Block {
  ids: string[];
  /** Serial ms per variant. */
  ms: number[];
  /** Largest mutex group's serial ms inside the block, per variant (0 when none). */
  groupMs: number[];
  /** Per 0-based leg: may this block sit there. */
  allowed: boolean[];
}

/** The indivisible blocks: every unit of one mutex group (the model's own `groupOf`) plus every `together` rule, merged by union-find, each with its allowed legs. */
function buildBlocks(model: LaneModel, ids: readonly string[], c: RebalanceConstraints): Block[] {
  const costs = unitCostsOrThrow(model, ids);
  const parent = new Map<string, string>(ids.map((id) => [id, id]));
  const find = (x: string): string => {
    let r = x;
    while (parent.get(r) !== r) r = parent.get(r) as string;
    parent.set(x, r);
    return r;
  };
  const union = (a: string, b: string): void => {
    const [ra, rb] = [find(a), find(b)].sort();
    if (ra !== rb) parent.set(rb as string, ra as string);
  };
  const grouped = model.parallel !== undefined && model.parallel.workers > 1;
  const groupOf = (id: string): string | undefined =>
    grouped ? model.parallel?.groupOf(id) : undefined;
  const firstInGroup = new Map<string, string>();
  for (const id of ids) {
    const g = groupOf(id);
    if (g === undefined) continue;
    const first = firstInGroup.get(g);
    if (first === undefined) firstInGroup.set(g, id);
    else union(first, id);
  }
  for (const t of c.together ?? [])
    for (const u of t.units.slice(1)) union(t.units[0] as string, u);
  const byRoot = new Map<string, string[]>();
  for (const id of [...ids].sort()) byRoot.set(find(id), [...(byRoot.get(find(id)) ?? []), id]);
  const blocks: Block[] = [];
  for (const members of byRoot.values()) {
    const allowed = Array.from({ length: model.of }, () => true);
    for (const p of c.onLeg ?? [])
      if (members.includes(p.unit))
        allowed.forEach((_, i) => (allowed[i] = allowed[i] && i === p.leg - 1));
    for (const p of c.notOnLeg ?? []) if (members.includes(p.unit)) allowed[p.leg - 1] = false;
    if (!allowed.some(Boolean))
      throw new RebalanceError(
        'unsatisfiable',
        `${model.lane}: no leg can hold ${members.join(' + ')}: its onLeg/notOnLeg/together rules exclude every leg of ${model.of}`
      );
    const ms = model.variants.map((_, v) =>
      members.reduce((a, id) => a + (costs.get(id)?.[v] ?? 0), 0)
    );
    const groupMs = model.variants.map((_, v) => {
      const sums = new Map<string, number>();
      for (const id of members) {
        const g = groupOf(id);
        if (g !== undefined) sums.set(g, (sums.get(g) ?? 0) + (costs.get(id)?.[v] ?? 0));
      }
      return Math.max(0, ...sums.values());
    });
    blocks.push({ ids: members, ms, groupMs, allowed });
  }
  return blocks;
}

/**
 * The search state for an `assign` lane: which leg each block is on, and per leg and variant its serial ms and largest group, priced by the same `max(serial / workers, largest group)` rule `parallelLegMs` applies. The search only steers by these numbers; every figure reported or compared against the committed plan is re-priced by `planMinutes`, and a disagreement between the two throws.
 */
class AssignState {
  readonly assign: number[];
  private readonly serial: number[][];
  private readonly grouped: number[];
  constructor(
    private readonly model: LaneModel,
    private readonly blocks: readonly Block[],
    assign: readonly number[]
  ) {
    this.assign = [...assign];
    this.serial = Array.from({ length: model.of }, () => model.variants.map(() => 0));
    blocks.forEach((b, i) => {
      const leg = this.serial[assign[i] as number] as number[];
      b.ms.forEach((ms, v) => (leg[v] = (leg[v] as number) + ms));
    });
    this.grouped = blocks.flatMap((b, i) => (b.groupMs.some((x) => x > 0) ? [i] : []));
  }
  legCost(leg: number, v: number): number {
    const serial = this.serial[leg]?.[v] ?? 0;
    const p = this.model.parallel;
    let ms = serial;
    if (p !== undefined && p.workers > 1) {
      let worst = 0;
      for (const b of this.grouped)
        if (this.assign[b] === leg) worst = Math.max(worst, this.blocks[b]?.groupMs[v] ?? 0);
      ms = Math.max(serial / p.workers, worst);
    }
    return (this.model.variants[v]?.fixedByLeg[leg] ?? 0) + ms / 60_000;
  }
  costs(): number[] {
    const out: number[] = [];
    for (let leg = 0; leg < this.model.of; leg++)
      for (let v = 0; v < this.model.variants.length; v++) out.push(this.legCost(leg, v));
    return out;
  }
  count(leg: number): number {
    return this.assign.filter((l) => l === leg).length;
  }
  move(block: number, to: number): void {
    const from = this.assign[block] as number;
    const b = this.blocks[block] as Block;
    b.ms.forEach((ms, v) => {
      (this.serial[from] as number[])[v] = ((this.serial[from] as number[])[v] as number) - ms;
      (this.serial[to] as number[])[v] = ((this.serial[to] as number[])[v] as number) + ms;
    });
    this.assign[block] = to;
  }
}

/** The search's order on plans: the `[leg x variant]` costs sorted worst first, each rounded to a whole number of SEARCH_EPS_MIN, compared exactly. Unlike `compareCosts` with an eps, which skips near-equal pairs and so is not transitive, this is a total order, so a descent on it cannot cycle: with three legs balanced to within 2e-6 minutes, the eps comparison once let one swap beat the plan it undid, and the search flipped that pair until the step cap, about 90 ms a step. */
function searchKey(costs: readonly number[]): number[] {
  return costs.map((c) => Math.round(c / SEARCH_EPS_MIN)).sort((p, q) => q - p);
}

function keyLess(a: readonly number[], b: readonly number[]): boolean {
  for (let i = 0; i < a.length; i++) {
    const d = (a[i] as number) - (b[i] as number);
    if (d !== 0) return d < 0;
  }
  return false;
}

interface LocalSearchResult {
  assign: number[];
  steps: number;
  /** Candidate plans priced: the deterministic work measure the budget control holds. */
  evaluations: number;
  capped: boolean;
}

/**
 * Steepest descent over single moves and pairwise swaps on `searchKey`; a local optimum is a fixed point, which is what makes a second run reproduce the first. No move empties a leg. Each step re-sums every leg from scratch (no drift across steps), then prices each candidate by its delta on the two legs it touches, O(variants) apiece: per leg and variant the serial ms and the two largest group ms, so taking a block out and putting another in needs no rescan. A swap of two blocks with identical costs changes nothing and is not priced.
 */
function localSearch(
  model: LaneModel,
  blocks: readonly Block[],
  start: readonly number[],
  maxEvaluations: number
): LocalSearchResult {
  const L = model.of;
  const V = model.variants.length;
  const w = model.parallel !== undefined && model.parallel.workers > 1 ? model.parallel.workers : 1;
  const assign = [...start];
  const counts = new Array<number>(L).fill(0);
  for (const leg of assign) counts[leg] = (counts[leg] as number) + 1;
  const serial = Array.from({ length: L }, () => new Array<number>(V).fill(0));
  const top1 = Array.from({ length: L }, () => new Array<number>(V).fill(0));
  const top1Of = Array.from({ length: L }, () => new Array<number>(V).fill(-1));
  const top2 = Array.from({ length: L }, () => new Array<number>(V).fill(0));
  const legCost = (leg: number, v: number, s: number, g: number): number =>
    (model.variants[v]?.fixedByLeg[leg] ?? 0) + (w > 1 ? Math.max(s / w, g) : s) / 60_000;
  /** Leg `leg`, variant `v`, with block `out` taken off it and block `into` put on it (-1 for neither). */
  const priced = (leg: number, v: number, out: number, into: number): number => {
    let s = (serial[leg] as number[])[v] as number;
    let g =
      (top1Of[leg] as number[])[v] === out && out >= 0
        ? ((top2[leg] as number[])[v] as number)
        : ((top1[leg] as number[])[v] as number);
    if (out >= 0) s -= (blocks[out] as Block).ms[v] as number;
    if (into >= 0) {
      s += (blocks[into] as Block).ms[v] as number;
      g = Math.max(g, (blocks[into] as Block).groupMs[v] as number);
    }
    return legCost(leg, v, s, g);
  };
  const cand = new Array<number>(L * V).fill(0);
  let evaluations = 0;
  let steps = 0;
  let capped = false;
  for (;;) {
    for (let leg = 0; leg < L; leg++)
      for (let v = 0; v < V; v++) {
        (serial[leg] as number[])[v] = 0;
        (top1[leg] as number[])[v] = 0;
        (top1Of[leg] as number[])[v] = -1;
        (top2[leg] as number[])[v] = 0;
      }
    blocks.forEach((b, i) => {
      const leg = assign[i] as number;
      for (let v = 0; v < V; v++) {
        (serial[leg] as number[])[v] =
          ((serial[leg] as number[])[v] as number) + (b.ms[v] as number);
        const g = b.groupMs[v] as number;
        if (g > ((top1[leg] as number[])[v] as number)) {
          (top2[leg] as number[])[v] = (top1[leg] as number[])[v] as number;
          (top1[leg] as number[])[v] = g;
          (top1Of[leg] as number[])[v] = i;
        } else if (g > ((top2[leg] as number[])[v] as number)) (top2[leg] as number[])[v] = g;
      }
    });
    const base: number[] = [];
    for (let leg = 0; leg < L; leg++) for (let v = 0; v < V; v++) base.push(priced(leg, v, -1, -1));
    const startKey = searchKey(base);
    let bestKey = startKey;
    let pick: { a: number; to: number; b: number } | undefined;
    const consider = (a: number, to: number, b: number): void => {
      const from = assign[a] as number;
      for (let i = 0; i < base.length; i++) cand[i] = base[i] as number;
      for (let v = 0; v < V; v++) {
        cand[from * V + v] = priced(from, v, a, b);
        cand[to * V + v] = priced(to, v, b, a);
      }
      evaluations++;
      const key = searchKey(cand);
      if (keyLess(key, bestKey)) {
        bestKey = key;
        pick = { a, to, b };
      }
    };
    for (let a = 0; a < blocks.length; a++) {
      const from = assign[a] as number;
      if ((counts[from] as number) <= 1) continue;
      for (let to = 0; to < L; to++)
        if (to !== from && (blocks[a] as Block).allowed[to]) consider(a, to, -1);
    }
    for (let a = 0; a < blocks.length; a++) {
      const ba = blocks[a] as Block;
      for (let b = a + 1; b < blocks.length; b++) {
        const la = assign[a] as number;
        const lb = assign[b] as number;
        const bb = blocks[b] as Block;
        if (la === lb || !ba.allowed[lb] || !bb.allowed[la]) continue;
        let same = true;
        for (let v = 0; v < V && same; v++)
          same = ba.ms[v] === bb.ms[v] && ba.groupMs[v] === bb.groupMs[v];
        if (!same) consider(a, lb, b);
      }
    }
    if (pick === undefined) break;
    steps++;
    const from = assign[pick.a] as number;
    assign[pick.a] = pick.to;
    if (pick.b >= 0) assign[pick.b] = from;
    else {
      counts[from] = (counts[from] as number) - 1;
      counts[pick.to] = (counts[pick.to] as number) + 1;
    }
    if (evaluations >= maxEvaluations) {
      capped = true;
      break;
    }
  }
  return { assign, steps, evaluations, capped };
}

/** Longest-processing-time first: blocks by descending worst-variant cost, each onto the allowed leg whose worst variant stays cheapest; then every still-empty leg takes the smallest block a leg with two or more can spare. */
function lpt(model: LaneModel, blocks: readonly Block[]): number[] {
  const order = blocks
    .map((b, i) => ({ i, key: Math.max(...b.ms) }))
    .sort((x, y) => y.key - x.key || x.i - y.i)
    .map((x) => x.i);
  const s = new AssignState(
    model,
    blocks,
    blocks.map((b) => b.allowed.indexOf(true))
  );
  const placed = new Set<number>();
  // AssignState starts with every block placed; LPT re-places them one by one onto whichever leg is cheapest among those holding only already-placed blocks.
  const loads = Array.from({ length: model.of }, () => model.variants.map(() => 0));
  const cost = (leg: number, extra: Block): number =>
    Math.max(
      ...model.variants.map((v, vi) => {
        const serial = (loads[leg]?.[vi] ?? 0) + (extra.ms[vi] ?? 0);
        let worst = extra.groupMs[vi] ?? 0;
        for (const p of placed)
          if (s.assign[p] === leg) worst = Math.max(worst, blocks[p]?.groupMs[vi] ?? 0);
        const w =
          model.parallel !== undefined && model.parallel.workers > 1 ? model.parallel.workers : 1;
        return (v.fixedByLeg[leg] ?? 0) + (w > 1 ? Math.max(serial / w, worst) : serial) / 60_000;
      })
    );
  for (const i of order) {
    const b = blocks[i] as Block;
    let bestLeg = -1;
    let bestCost = Number.POSITIVE_INFINITY;
    for (let leg = 0; leg < model.of; leg++) {
      if (!b.allowed[leg]) continue;
      const c = cost(leg, b);
      if (c < bestCost - SEARCH_EPS_MIN) {
        bestCost = c;
        bestLeg = leg;
      }
    }
    s.move(i, bestLeg);
    placed.add(i);
    b.ms.forEach(
      (ms, v) =>
        ((loads[bestLeg] as number[])[v] = ((loads[bestLeg] as number[])[v] as number) + ms)
    );
  }
  for (let leg = 0; leg < model.of; leg++) {
    if (s.count(leg) > 0) continue;
    const donor = order
      .slice()
      .reverse()
      .find((i) => (blocks[i] as Block).allowed[leg] && s.count(s.assign[i] as number) > 1);
    if (donor === undefined)
      throw new RebalanceError(
        'unsatisfiable',
        `${model.lane}: leg ${leg + 1} can hold no block without emptying another; the lane has too few placeable blocks for ${model.of} legs`
      );
    s.move(donor, leg);
  }
  return [...s.assign];
}

/** Legs no rule tells apart (same fixed cost under every variant, same allowed blocks): the search tries only the first empty one of a class, and the relabel keeps each new leg on the old index it overlaps most. */
function legClasses(model: LaneModel, blocks: readonly Block[]): string[] {
  return Array.from({ length: model.of }, (_, leg) =>
    JSON.stringify([
      model.variants.map((v) => v.fixedByLeg[leg]),
      blocks.map((b) => b.allowed[leg]),
    ])
  );
}

/** Exact min-max by branch and bound: blocks by descending cost, a branch pruned once any leg reaches the incumbent, empty interchangeable legs tried once. Returns a strictly better assignment than `incumbentMax`, or null, and whether the node limit cut the search short. */
function branchAndBound(
  model: LaneModel,
  blocks: readonly Block[],
  incumbentMax: number
): { assign: number[] | null; nodes: number; capped: boolean } {
  const order = blocks
    .map((b, i) => ({ i, key: Math.max(...b.ms) }))
    .sort((x, y) => y.key - x.key || x.i - y.i)
    .map((x) => x.i);
  const classes = legClasses(model, blocks);
  const V = model.variants.length;
  const w = model.parallel !== undefined && model.parallel.workers > 1 ? model.parallel.workers : 1;
  const serial = Array.from({ length: model.of }, () => new Array<number>(V).fill(0));
  const worst = Array.from({ length: model.of }, () => new Array<number>(V).fill(0));
  const count = new Array<number>(model.of).fill(0);
  const assign = new Array<number>(blocks.length).fill(-1);
  const legMax = (leg: number): number => {
    let m = 0;
    for (let v = 0; v < V; v++) {
      const s = (serial[leg] as number[])[v] as number;
      const g = (worst[leg] as number[])[v] as number;
      m = Math.max(
        m,
        (model.variants[v]?.fixedByLeg[leg] ?? 0) + (w > 1 ? Math.max(s / w, g) : s) / 60_000
      );
    }
    return m;
  };
  // A floor no plan beats: per variant, the average leg once all fixed cost and all unit cost is spread evenly.
  let floor = 0;
  for (let v = 0; v < V; v++) {
    const fixed = (model.variants[v]?.fixedByLeg ?? []).reduce((a, b) => a + b, 0);
    const units = blocks.reduce((a, b) => a + (b.ms[v] ?? 0), 0) / w;
    floor = Math.max(floor, (fixed + units / 60_000) / model.of);
  }
  let bestMax = incumbentMax;
  let best: number[] | null = null;
  let nodes = 0;
  let capped = false;
  // Unit ms per variant still to place, for the capacity bound below.
  const remaining = model.variants.map((_, v) => blocks.reduce((a, b) => a + (b.ms[v] ?? 0), 0));
  // The capacity bound: under the incumbent every leg has room for (bestMax - fixed) x workers minutes of serial work, since a leg costs at least fixed + serial / workers; when the room left across all legs is less than the work left, no completion beats the incumbent.
  const roomShort = (): boolean => {
    for (let v = 0; v < V; v++) {
      let room = 0;
      for (let leg = 0; leg < model.of; leg++) {
        const cap =
          (bestMax - SEARCH_EPS_MIN - (model.variants[v]?.fixedByLeg[leg] ?? 0)) * 60_000 * w;
        room += Math.max(0, cap - ((serial[leg] as number[])[v] as number));
      }
      if (room < (remaining[v] as number)) return true;
    }
    return false;
  };
  const dfs = (depth: number, empty: number): void => {
    if (capped || bestMax <= floor + SEARCH_EPS_MIN || roomShort()) return;
    if (++nodes > BNB_NODE_LIMIT) {
      capped = true;
      return;
    }
    if (depth === order.length) {
      if (empty > 0) return;
      let m = 0;
      for (let leg = 0; leg < model.of; leg++) m = Math.max(m, legMax(leg));
      if (m < bestMax - SEARCH_EPS_MIN) {
        bestMax = m;
        best = [...assign];
      }
      return;
    }
    if (order.length - depth < empty) return;
    const i = order[depth] as number;
    const b = blocks[i] as Block;
    const triedEmpty = new Set<string>();
    const options: { leg: number; cost: number }[] = [];
    for (let leg = 0; leg < model.of; leg++) {
      if (!b.allowed[leg]) continue;
      if (count[leg] === 0) {
        if (triedEmpty.has(classes[leg] as string)) continue;
        triedEmpty.add(classes[leg] as string);
      }
      const saveS = [...(serial[leg] as number[])];
      const saveW = [...(worst[leg] as number[])];
      for (let v = 0; v < V; v++) {
        (serial[leg] as number[])[v] = (saveS[v] as number) + (b.ms[v] as number);
        (worst[leg] as number[])[v] = Math.max(saveW[v] as number, b.groupMs[v] as number);
      }
      const cost = legMax(leg);
      serial[leg] = saveS;
      worst[leg] = saveW;
      if (cost < bestMax - SEARCH_EPS_MIN) options.push({ leg, cost });
    }
    options.sort((x, y) => x.cost - y.cost || x.leg - y.leg);
    for (const { leg } of options) {
      const saveS = [...(serial[leg] as number[])];
      const saveW = [...(worst[leg] as number[])];
      for (let v = 0; v < V; v++) {
        (serial[leg] as number[])[v] = (saveS[v] as number) + (b.ms[v] as number);
        (worst[leg] as number[])[v] = Math.max(saveW[v] as number, b.groupMs[v] as number);
      }
      const wasEmpty = count[leg] === 0;
      count[leg] = (count[leg] as number) + 1;
      assign[i] = leg;
      b.ms.forEach((ms, v) => (remaining[v] = (remaining[v] as number) - ms));
      dfs(depth + 1, empty - (wasEmpty ? 1 : 0));
      b.ms.forEach((ms, v) => (remaining[v] = (remaining[v] as number) + ms));
      assign[i] = -1;
      count[leg] = (count[leg] as number) - 1;
      serial[leg] = saveS;
      worst[leg] = saveW;
      if (capped) return;
    }
  };
  dfs(0, model.of);
  return { assign: best, nodes, capped };
}

/** The committed plan as one leg per block, or null when a block is split across legs, placed on a leg it may not use, or missing. */
function committedAssign(
  blocks: readonly Block[],
  legs: readonly (readonly string[])[]
): number[] | null {
  const legOf = new Map<string, number>();
  legs.forEach((ids, i) => {
    for (const id of ids) legOf.set(id, i);
  });
  const out: number[] = [];
  for (const b of blocks) {
    const at = new Set(b.ids.map((id) => legOf.get(id)));
    const leg = [...at][0];
    if (at.size !== 1 || leg === undefined || !b.allowed[leg]) return null;
    out.push(leg);
  }
  return out;
}

function coverageProblems(ids: readonly string[], legs: readonly (readonly string[])[]): string[] {
  const want = new Set(ids);
  const have = legs.flat();
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of have) {
    if (!want.has(id)) out.push(`${id} is committed but not in the lane's unit set`);
    if (seen.has(id)) out.push(`${id} is committed on more than one leg`);
    seen.add(id);
  }
  for (const id of ids)
    if (!seen.has(id)) out.push(`${id} is in the lane's unit set but on no committed leg`);
  legs.forEach((l, i) => {
    if (l.length === 0) out.push(`committed leg ${i + 1} is empty`);
  });
  return out;
}

/** Picks the rebalanced plan over the committed one only when it is better by more than REBALANCE_WRITE_EPS_MIN on some leg (worst first), and fills in the result. */
function settle(
  model: LaneModel,
  shape: 'assign' | 'contiguous',
  committed: string[][] | null,
  violations: string[],
  coverage: string[],
  candidate: string[][],
  search: string,
  evaluations: number
): RebalanceResult {
  const valid = committed !== null && violations.length === 0 && coverage.length === 0;
  const committedMinutes =
    committed === null || coverage.length > 0 ? null : planMinutes(model, committed);
  const candidateMinutes = planMinutes(model, candidate);
  const keep =
    valid &&
    committedMinutes !== null &&
    compareCosts(candidateMinutes.flat(), committedMinutes.flat(), REBALANCE_WRITE_EPS_MIN) >= 0;
  const rebalanced = keep ? (committed as string[][]) : candidate;
  const rebalancedMinutes = keep ? (committedMinutes as number[][]) : candidateMinutes;
  const worst = (m: number[][]): number => Math.max(...m.flat());
  return {
    lane: model.lane,
    shape,
    variants: model.variants.map((v) => v.name),
    committed: coverage.length > 0 ? null : committed,
    committedMinutes,
    violations,
    coverage,
    rebalanced,
    rebalancedMinutes,
    changed: !keep,
    gainMinutes:
      valid && committedMinutes !== null
        ? worst(committedMinutes) - worst(rebalancedMinutes)
        : null,
    search,
    evaluations,
  };
}

/** An `assign` lane: LPT, then exact branch and bound when the lane is small, then local search from both that and the committed plan; the better survivor is kept only if it beats the committed plan (see `settle`). */
export function rebalanceAssign(
  model: LaneModel,
  ids: readonly string[],
  c: RebalanceConstraints,
  committed: string[][] | null,
  maxEvaluations = LOCAL_SEARCH_MAX_EVALUATIONS
): RebalanceResult {
  const problems = staticConstraintProblems(c, new Set(ids), model.of);
  if (problems.length > 0)
    throw new RebalanceError('unsatisfiable', `${model.lane}: ${problems.join('; ')}`);
  const blocks = buildBlocks(model, ids, c);
  if (blocks.length < model.of)
    throw new RebalanceError(
      'unsatisfiable',
      `${model.lane}: ${blocks.length} indivisible block(s) cannot fill ${model.of} legs`
    );
  const coverage = committed === null ? ['no committed plan'] : coverageProblems(ids, committed);
  const violations = committed === null ? [] : constraintViolations(c, committed);
  const toLegs = (assign: readonly number[]): string[][] =>
    Array.from({ length: model.of }, (_, leg) =>
      blocks.flatMap((b, i) => (assign[i] === leg ? b.ids : [])).sort()
    );
  const fastMax = (assign: readonly number[]): number =>
    Math.max(...new AssignState(model, blocks, assign).costs());

  let start = lpt(model, blocks);
  let search = `LPT over ${blocks.length} block(s)`;
  if (blocks.length <= BNB_MAX_BLOCKS) {
    const bnb = branchAndBound(model, blocks, fastMax(start) + SEARCH_EPS_MIN * 2);
    if (bnb.assign !== null) start = bnb.assign;
    search = `branch and bound over ${blocks.length} block(s), ${bnb.nodes} node(s), ${bnb.capped ? `CAPPED at ${BNB_NODE_LIMIT}: best found, not proven optimal` : 'min-max proven'}`;
  }
  const runs = [localSearch(model, blocks, start, maxEvaluations)];
  const fromCommitted =
    committed !== null && coverage.length === 0 ? committedAssign(blocks, committed) : null;
  if (fromCommitted !== null)
    runs.unshift(localSearch(model, blocks, fromCommitted, maxEvaluations));
  let pick = (runs[0] as LocalSearchResult).assign;
  for (const run of runs.slice(1)) {
    const a = searchKey(new AssignState(model, blocks, run.assign).costs());
    const b = searchKey(new AssignState(model, blocks, pick).costs());
    if (keyLess(a, b)) pick = run.assign;
  }
  const evaluations = runs.reduce((n, r) => n + r.evaluations, 0);
  const cappedRuns = runs.filter((r) => r.capped).length;
  search += `, then local search (moves and swaps): ${runs.map((r) => r.steps).join(' + ')} step(s), ${evaluations} evaluation(s)${cappedRuns > 0 ? `, CAPPED at ${maxEvaluations} evaluations in ${cappedRuns} run(s): best found, not a local optimum` : ''}`;

  // The search priced by its own aggregates; the exact model must agree to the millisecond, or the two have diverged and no number here can be trusted.
  const fast = new AssignState(model, blocks, pick).costs();
  const exact = planMinutes(model, toLegs(pick));
  for (let leg = 0; leg < model.of; leg++)
    for (let v = 0; v < model.variants.length; v++) {
      const f = fast[leg * model.variants.length + v] as number;
      const e = (exact[v] as number[])[leg] as number;
      if (Math.abs(f - e) > 1e-6)
        throw new Error(
          `${model.lane}: the search priced leg ${leg + 1} at ${f} and legMinutes at ${e}; they must agree`
        );
    }
  return settle(
    model,
    'assign',
    committed,
    violations,
    coverage,
    relabel(model, blocks, toLegs(pick), committed),
    search,
    evaluations
  );
}

/** Renumbers interchangeable legs so each new leg keeps the committed index it shares most units with; the costs do not change, only the diff shrinks. */
function relabel(
  model: LaneModel,
  blocks: readonly Block[],
  legs: string[][],
  committed: string[][] | null
): string[][] {
  if (committed === null) return legs;
  const classes = legClasses(model, blocks);
  const out = legs.map((l) => [...l]);
  for (const cls of new Set(classes)) {
    const members = classes.flatMap((c, i) => (c === cls ? [i] : []));
    const pairs: { n: number; o: number; overlap: number }[] = [];
    for (const n of members)
      for (const o of members) {
        const old = new Set(committed[o] ?? []);
        pairs.push({ n, o, overlap: (legs[n] ?? []).filter((id) => old.has(id)).length });
      }
    pairs.sort((a, b) => b.overlap - a.overlap || a.o - b.o || a.n - b.n);
    const usedN = new Set<number>();
    const usedO = new Set<number>();
    for (const p of pairs) {
      if (usedN.has(p.n) || usedO.has(p.o)) continue;
      usedN.add(p.n);
      usedO.add(p.o);
      out[p.o] = [...(legs[p.n] ?? [])];
    }
  }
  return out;
}

/** A `contiguous` lane: every split of the ordered units into `of` non-empty slices (C(n-1, of-1) of them; 680 for 18 tutorials in 4), the rule-abiding one with the best worst-first cost list, kept only if it beats the committed split. */
export function rebalanceContiguous(
  model: LaneModel,
  ids: readonly string[],
  c: RebalanceConstraints,
  committed: string[][] | null
): RebalanceResult {
  const problems = staticConstraintProblems(c, new Set(ids), model.of);
  if (problems.length > 0)
    throw new RebalanceError('unsatisfiable', `${model.lane}: ${problems.join('; ')}`);
  unitCostsOrThrow(model, ids);
  const coverage = committed === null ? ['no committed plan'] : coverageProblems(ids, committed);
  const violations = committed === null ? [] : constraintViolations(c, committed);
  let best: { legs: string[][]; costs: number[] } | undefined;
  let tried = 0;
  const sizes: number[] = [];
  const walk = (left: number, legsLeft: number): void => {
    if (legsLeft === 1) {
      sizes.push(left);
      const legs = contiguousLegs(ids, sizes, model.of).map((l) => l.ids);
      tried++;
      if (constraintViolations(c, legs).length === 0) {
        const costs = planMinutes(model, legs).flat();
        if (best === undefined || compareCosts(costs, best.costs, SEARCH_EPS_MIN) < 0)
          best = { legs, costs };
      }
      sizes.pop();
      return;
    }
    for (let n = 1; n <= left - (legsLeft - 1); n++) {
      sizes.push(n);
      walk(left - n, legsLeft - 1);
      sizes.pop();
    }
  };
  if (ids.length >= model.of) walk(ids.length, model.of);
  if (best === undefined)
    throw new RebalanceError(
      'unsatisfiable',
      `${model.lane}: none of the ${tried} contiguous split(s) of ${ids.length} unit(s) into ${model.of} slices meets the rules (${[
        ...(c.together ?? []).map((t) => `together ${t.units.join(' + ')}`),
        ...(c.onLeg ?? []).map((p) => `${p.unit} on leg ${p.leg}`),
        ...(c.notOnLeg ?? []).map((p) => `${p.unit} off leg ${p.leg}`),
      ].join('; ')})`
    );
  const found: { legs: string[][] } = best;
  return settle(
    model,
    'contiguous',
    committed,
    violations,
    coverage,
    found.legs,
    `exhaustive over ${tried} contiguous split(s)`,
    tried
  );
}

interface RebalanceInput {
  model: LaneModel;
  ids: string[];
  constraints: RebalanceConstraints;
  committed: string[][] | null;
  /** Writes a plan to the file the runner reads and returns its path. */
  write: (legs: string[][]) => string;
}

async function loadRebalanceInput(lane: string, durations: LaneDurations): Promise<RebalanceInput> {
  const spec = REBALANCE_LANES[lane];
  if (spec === undefined)
    throw new Error(
      `--rebalance: ${lane} is not a rebalanced lane (${Object.keys(REBALANCE_LANES).join(', ')})`
    );
  const parallel = await laneParallelism(lane, durations);
  const constraints = durations.rebalanceConstraints?.[lane] ?? {};
  const enumerate = async (): Promise<string[]> => {
    const enumerator = LANE_ENUMERATORS[lane];
    if (enumerator === undefined) throw new Error(`--rebalance: ${lane} has no unit enumerator`);
    return (await enumerator(ROOT)).map((u) => u.id);
  };
  if (spec.shape === 'contiguous') {
    const contiguous = CONTIGUOUS_LANES[lane];
    if (contiguous === undefined)
      throw new Error(`--rebalance: ${lane} is not in CONTIGUOUS_LANES`);
    const file = path.join(ROOT, contiguous.sizesFile);
    const text = readFileSync(file, 'utf-8');
    const sizes = parseShardSizes(text);
    if (sizes === null)
      throw new Error(`--rebalance: no MEASURED_SHARD_SIZES in ${contiguous.sizesFile}`);
    const ids = await enumerate();
    return {
      model: laneModel(lane, sizes.length, durations, parallel),
      ids,
      constraints,
      committed: contiguousLegs(ids, sizes, sizes.length).map((l) => l.ids),
      write: (legs) => {
        const line = `MEASURED_SHARD_SIZES=(${legs.map((l) => l.length).join(' ')})`;
        writeFileSync(file, text.replace(/MEASURED_SHARD_SIZES=\([\d\s]+\)/, line));
        return contiguous.sizesFile;
      },
    };
  }
  const manifestFile = path.join(ROOT, shardManifestPath(lane));
  const manifest = parseShardManifest(readFileSync(manifestFile, 'utf-8'), lane);
  const committed = [...manifest.legs].sort((a, b) => a.index - b.index).map((l) => [...l.ids]);
  const ids =
    spec.unitSource === 'enumerator' ? await enumerate() : [...new Set(committed.flat())].sort();
  return {
    model: laneModel(lane, manifest.of, durations, parallel),
    ids,
    constraints,
    committed,
    write: (legs) => {
      const file = buildShardManifest(
        lane,
        legs.map((l, i) => ({ index: i + 1, of: manifest.of, ids: l }))
      );
      writeFileSync(manifestFile, `${JSON.stringify(file, null, 2)}\n`);
      return shardManifestPath(lane);
    },
  };
}

async function rebalanceLane(
  lane: string,
  durations: LaneDurations
): Promise<{ result: RebalanceResult; input: RebalanceInput }> {
  const input = await loadRebalanceInput(lane, durations);
  const shape = REBALANCE_LANES[lane]?.shape;
  const result =
    shape === 'contiguous'
      ? rebalanceContiguous(input.model, input.ids, input.constraints, input.committed)
      : rebalanceAssign(input.model, input.ids, input.constraints, input.committed);
  return { result, input };
}

/** The dry-run report: per leg and variant the committed and rebalanced minutes, the worst leg of each, and which units move. */
export function formatRebalance(r: RebalanceResult): string[] {
  const out: string[] = [];
  const n = r.rebalanced.length;
  out.push(
    `rebalance ${r.lane} (${r.shape}, ${n} legs, ${r.variants.length} variant(s)): ${r.search}`
  );
  out.push(
    `${'leg'.padEnd(5)}${'variant'.padEnd(16)}${'units'.padStart(11)}  ${'committed'.padStart(9)}  ${'rebalanced'.padStart(10)}  delta`
  );
  r.variants.forEach((variant, v) => {
    for (let leg = 0; leg < n; leg++) {
      const before = r.committedMinutes?.[v]?.[leg];
      const after = r.rebalancedMinutes[v]?.[leg] as number;
      const units = `${r.committed?.[leg]?.length ?? '-'}->${r.rebalanced[leg]?.length ?? 0}`;
      out.push(
        `${`${leg + 1}/${n}`.padEnd(5)}${(variant || '-').padEnd(16)}${units.padStart(11)}  ` +
          `${before === undefined ? '-'.padStart(9) : before.toFixed(2).padStart(9)}  ${after.toFixed(2).padStart(10)}  ` +
          `${before === undefined ? '' : `${after - before >= 0 ? '+' : ''}${(after - before).toFixed(2)}`}${after > PER_LEG_BUDGET_MIN ? '  OVER' : ''}`
      );
    }
  });
  const worstAfter = Math.max(...r.rebalancedMinutes.flat());
  const worstBefore = r.committedMinutes === null ? null : Math.max(...r.committedMinutes.flat());
  out.push(
    `worst leg: committed ${worstBefore === null ? '-' : `${worstBefore.toFixed(2)}m`}, rebalanced ${worstAfter.toFixed(2)}m` +
      (r.gainMinutes === null ? '' : `, gain ${r.gainMinutes.toFixed(2)}m`)
  );
  for (const v of r.violations) out.push(`committed plan breaks a rule: ${v}`);
  for (const c of r.coverage) out.push(`committed plan coverage: ${c}`);
  if (!r.changed) {
    out.push(
      `no change: nothing beats the committed plan by more than ${REBALANCE_WRITE_EPS_MIN}m on any leg`
    );
    return out;
  }
  if (r.shape === 'contiguous') {
    out.push(
      `diff: MEASURED_SHARD_SIZES (${r.committed?.map((l) => l.length).join(' ') ?? '-'}) -> (${r.rebalanced.map((l) => l.length).join(' ')})`
    );
  }
  const before = new Map<string, number>();
  r.committed?.forEach((l, i) => {
    for (const id of l) before.set(id, i + 1);
  });
  const moves: string[] = [];
  r.rebalanced.forEach((l, i) => {
    for (const id of l)
      if (before.get(id) !== i + 1)
        moves.push(`  ${id}: leg ${before.get(id) ?? 'none'} -> ${i + 1}`);
  });
  out.push(`diff: ${moves.length} unit(s) move`, ...moves.sort());
  return out;
}

async function rebalanceMain(lane: string, write: boolean): Promise<number> {
  let durations: LaneDurations;
  try {
    durations = readDurations(ROOT);
  } catch (e) {
    console.error(`${RED}✗${NC} ${DURATIONS_PATH} could not be read: ${String(e)}`);
    return 1;
  }
  if (REBALANCE_LANES[lane] === undefined) {
    console.error(
      `${RED}✗${NC} --rebalance: ${lane} is not a rebalanced lane; one of ${Object.keys(REBALANCE_LANES).join(', ')}`
    );
    return 2;
  }
  let outcome: { result: RebalanceResult; input: RebalanceInput };
  try {
    outcome = await rebalanceLane(lane, durations);
  } catch (e) {
    console.error(
      `${RED}✗${NC} --rebalance ${lane}: ${e instanceof Error ? e.message : String(e)}`
    );
    return 1;
  }
  const { result, input } = outcome;
  for (const line of formatRebalance(result)) console.log(line);
  if (!write) {
    console.log(
      result.changed
        ? 'DRY RUN: nothing written; --write applies the plan above.'
        : 'DRY RUN: nothing to write.'
    );
    return 0;
  }
  if (!result.changed) {
    console.log(`${GREEN}✓${NC} --write: the committed plan stands; nothing written.`);
    return 0;
  }
  const after = constraintViolations(input.constraints, result.rebalanced);
  if (after.length > 0) {
    console.error(`${RED}✗${NC} --write refused: the rebalanced plan breaks ${after.join('; ')}`);
    return 1;
  }
  const file = input.write(result.rebalanced);
  console.log(`${GREEN}✓${NC} wrote ${file}`);
  if (result.shape === 'contiguous')
    console.log(
      `note: the comment above MEASURED_SHARD_SIZES in ${file} cites the old split's predictions; revise it to the table above.`
    );
  return 0;
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

const XDIST_DECL_RE = /^XDIST_GROUP\s*=\s*(?:["']([^"']+)["']|xdist_groups\.REAL_TREE_GROUP)/m;

/**
 * A lane's `LegParallelism`, or undefined when `unitParallelism` does not name it. Mutex
 * groups come from two places, both read-only and offline:
 *   - the lane's own enumerator (`unit-enumerators.ts`), whose `mutex` carries every group
 *     that spans more than one file (quality-pytest's `PYTEST_XDIST_MUTEX_GROUPS`);
 *   - for `pytest:` units, a module-level `XDIST_GROUP = ...` in the file itself, which pins
 *     the whole module to one worker (`.ci/rediacc_ci/xdist_groups.py`, "THE ESCAPE HATCH")
 *     even when no other file shares the group.
 * The enumerator's name wins for a file in both, so one resource is never two groups.
 */
async function laneParallelism(
  lane: string,
  durations: LaneDurations
): Promise<LegParallelism | undefined> {
  const workers = durations.unitParallelism?.[lane];
  if (workers === undefined) return undefined;
  const groups = new Map<string, string>();
  const enumerator = LANE_ENUMERATORS[lane];
  if (enumerator !== undefined) {
    for (const u of await enumerator(ROOT)) if (u.mutex !== undefined) groups.set(u.id, u.mutex);
  }
  const declared = new Map<string, string | null>();
  const groupOf = (id: string): string | undefined => {
    const known = groups.get(id);
    if (known !== undefined) return known;
    if (!id.startsWith('pytest:')) return undefined;
    if (!declared.has(id)) {
      const file = path.join(ROOT, id.slice('pytest:'.length));
      const m = existsSync(file) ? XDIST_DECL_RE.exec(readFileSync(file, 'utf-8')) : null;
      declared.set(id, m === null ? null : `xdist:${m[1] ?? 'real-tree'}`);
    }
    return declared.get(id) ?? undefined;
  };
  return { workers, groupOf };
}

async function main(): Promise<number> {
  const qualityText = readOr(ROOT, QUALITY_WORKFLOW, 'the quality workflow');
  const lockText = readOr(ROOT, LOCK_PATH, 'the gate lock');
  const ciText = readOr(ROOT, CI_WORKFLOW, 'the top-level CI workflow');
  if (qualityText === null || lockText === null || ciText === null) return 1;

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
    if (text === null) return 1;
    workflows[wf] = text;
  }
  const caps = mergeLaneCapabilities(workflows);

  // Every job that occupies a runner: ci.yml's own, plus every job of every reusable workflow it calls, transitively. A caller job (`uses:`) is not a runner itself.
  // Walked PER CALL SITE, not per file: ci-build-docker.yml is called three times under three caller names, and each call reports under its own display name.
  const runnerJobSet = new Set<string>();
  const sites: { id: string; pattern: RegExp }[] = [];
  // Check 7 reads each runner job once per DEFINING file, not per call site: ci-build-docker.yml's three callers share one timeout-minutes line.
  const timeoutSites = new Map<string, TimeoutSite>();
  const walk = (
    file: string,
    text: string,
    chain: readonly string[],
    stack: readonly string[]
  ): boolean => {
    for (const j of workflowJobs(text)) {
      if (j.uses === null) {
        runnerJobSet.add(j.id);
        sites.push({ id: j.id, pattern: displayNamePattern(chain, j.name, j.hasMatrix) });
        timeoutSites.set(`${file}\0${j.id}`, {
          file,
          job: j.id,
          timeoutRaw: j.timeoutRaw,
          timeoutMinutes: j.timeoutMinutes,
        });
        continue;
      }
      if (stack.includes(j.uses)) continue;
      const callee = workflows[j.uses] ?? readOr(ROOT, j.uses, `the ${j.uses} workflow`);
      if (callee === null) return false;
      workflows[j.uses] = callee;
      if (!walk(j.uses, callee, [...chain, j.name], [...stack, file])) return false;
    }
    return true;
  };
  if (!walk(CI_WORKFLOW, ciText, [], [])) return 1;
  // A job id two callees both define (test-linux-x64: ct-install-methods.yml and ct-update-flow.yml) is one id with two call sites; each site's display name is its own sample.
  const runnerJobs = [...runnerJobSet];
  const measured = durations.job_p90_minutes ?? {};
  const matchedLabels = new Set<string>();
  const samplesFor = (job: string): JobSample[] => {
    const out = samplesForJob(sites, measured, job);
    for (const x of out) matchedLabels.add(x.label);
    return out;
  };
  if (runnerJobs.length === 0) {
    console.error(
      `${RED}✗${NC} ${CI_WORKFLOW} and its callees parsed to zero jobs; the gate is not seeing the ` +
        'workflows, and its green would mean nothing.'
    );
    return 1;
  }

  const qualityLanes = [...laneCapabilities(qualityText).keys()];
  const allLanes = new Set<string>([...qualityLanes, ...Object.keys(TEST_LANE_WORKFLOWS)]);

  const findings: string[] = [...freshnessFindings(durations, new Date())];
  const worstLegPerLane: number[] = [];
  const priced = new Set<string>();
  const inert: string[] = [];
  const parallelLanes: string[] = [];
  let legCount = 0;
  let unitCount = 0;
  let measuredCount = 0;
  let defaultedCount = 0;

  const priceLeg = (
    lane: string,
    index: number,
    of: number,
    ids: readonly string[],
    fixedMinutes: number,
    defaultUnitMs: number | undefined,
    parallel: LegParallelism | undefined,
    units: Readonly<Record<string, number>> = durations.units
  ): number => {
    findings.push(
      ...legFindings(lane, index, of, ids, fixedMinutes, units, defaultUnitMs, parallel)
    );
    const { perUnit } = legCostMs(ids, units, defaultUnitMs);
    legCount += 1;
    unitCount += ids.length;
    for (const u of perUnit) {
      if (units[u.id] !== undefined) measuredCount += 1;
      else if (u.ms !== null) defaultedCount += 1;
    }
    return legMinutes(ids, fixedMinutes, units, defaultUnitMs, parallel);
  };

  // Every variant leg's prediction, kept for the model-vs-measured comparison (`--table`, and the drift figure in the summary line).
  const predictions: {
    lane: string;
    job: string;
    variant: string;
    index: number;
    of: number;
    minutes: number;
  }[] = [];

  // Prices every leg of a lane, once per variant when `variantCosts` names the lane, and returns the worst estimate; check 3 runs per variant too, against that variant's own fixed cost.
  const priceLegs = (
    lane: string,
    job: string,
    legs: readonly { index: number; ids: readonly string[] }[],
    of: number,
    fixedMinutes: number,
    defaultUnitMs: number | undefined,
    parallel: LegParallelism | undefined
  ): number => {
    const allIds = legs.flatMap((l) => [...l.ids]);
    const variants = durations.variantCosts?.[lane];
    if (variants === undefined) {
      if (VARIANT_PRICED_LANES.includes(lane)) {
        findings.push(
          `${lane}: ${DURATIONS_PATH} has no variantCosts entry, so its legs are priced with one ` +
            `${fixedMinutes.toFixed(1)}m fixed cost that leaves out the per-variant VM setup. ` +
            'budget_report.py --refresh drops the hand-authored field; restore it from git history ' +
            "or re-derive it by the recipe in the file's $comment."
        );
      }
      let worst = 0;
      for (const leg of legs) {
        worst = Math.max(
          worst,
          priceLeg(lane, leg.index, of, leg.ids, fixedMinutes, defaultUnitMs, parallel)
        );
      }
      findings.push(
        ...indivisibleFindings(lane, allIds, fixedMinutes, durations.units, undefined, parallel)
      );
      return worst;
    }
    let worst = 0;
    for (const [variant, cost] of Object.entries(variants).sort(([a], [b]) => a.localeCompare(b))) {
      for (const leg of legs) {
        const inputs = variantLegInputs(cost, leg.index, durations.units);
        const minutes = priceLeg(
          `${lane} (${variant})`,
          leg.index,
          of,
          leg.ids,
          inputs.fixedMinutes,
          defaultUnitMs,
          parallel,
          inputs.units
        );
        predictions.push({ lane, job, variant, index: leg.index, of, minutes });
        worst = Math.max(worst, minutes);
      }
      findings.push(
        ...indivisibleFindings(
          `${lane} (${variant})`,
          allIds,
          cost.fixedMinutes,
          variantLegInputs(cost, 0, durations.units).units,
          undefined,
          parallel
        )
      );
    }
    return worst;
  };

  // A priced lane's legs are ALSO judged on what they measured (job_p90_minutes, one sample per matrix combination), so an estimate that misses real cost (VM setup inside the runner step) cannot hide a leg that is over. Grouped per leg: the worst combination is named, with how many were over.
  const measuredLegFindings = (lane: string, of: number): number => {
    const byLeg = new Map<number, JobSample[]>();
    for (const sample of samplesFor(lane)) {
      const ofIn = /\/(\d+)\)$/.exec(sample.label);
      // A sample from before the lane's current shard count ("Pytest (1/2)" once it is 3 legs) describes a plan that no longer ships.
      if (ofIn !== null && Number(ofIn[1]) !== of) continue;
      const idx = legIndexOf(sample.label);
      byLeg.set(idx, [...(byLeg.get(idx) ?? []), sample]);
    }
    let worst = 0;
    for (const [idx, list] of [...byLeg].sort(([x], [y]) => x - y)) {
      const over = list.filter((x) => x.minutes > PER_LEG_BUDGET_MIN);
      const top = [...list].sort((x, y) => y.minutes - x.minutes)[0] as JobSample;
      worst = Math.max(worst, top.minutes);
      if (over.length > 0) {
        findings.push(
          `${lane} leg ${idx}/${of}: MEASURED p90 ${top.minutes.toFixed(1)}m ("${top.label}"), ` +
            `over the ${PER_LEG_BUDGET_MIN}m budget` +
            (list.length > 1
              ? ` (${over.length} of ${list.length} matrix combination(s) over)`
              : '') +
            '.'
        );
      }
    }
    return worst;
  };

  for (const lane of [...allLanes].sort()) {
    const contiguous = CONTIGUOUS_LANES[lane];
    const job = contiguous?.job ?? lane;
    // A lane named in TEST_LANE_WORKFLOWS whose job does not exist is inert by that table's own docstring; it is printed below, never silently dropped.
    if (!caps.has(job)) {
      inert.push(lane);
      continue;
    }

    const fixedMinutes = durations.jobs[lane] ?? 0;
    const defaultUnitMs = durations.defaultUnitMs?.[lane];
    const manifestFile = path.join(ROOT, shardManifestPath(lane));
    let parallel: LegParallelism | undefined;
    try {
      parallel = await laneParallelism(lane, durations);
    } catch (e) {
      findings.push(
        `${lane}: its mutex groups could not be read, so its parallel estimate would be a guess: ${String(e)}`
      );
      continue;
    }
    if (parallel !== undefined) parallelLanes.push(`${lane} x${parallel.workers}`);

    // A committed manifest IS the shipped plan, whether or not the lane is in SHARD_COUNTS: the test lanes are sharded from theirs (T2.12-T2.15), so pricing them by lock entries would price nothing.
    if (existsSync(manifestFile)) {
      const manifest = parseShardManifest(readFileSync(manifestFile, 'utf-8'), lane);
      const worst = priceLegs(
        lane,
        job,
        manifest.legs,
        manifest.of,
        fixedMinutes,
        defaultUnitMs,
        parallel
      );
      priced.add(job);
      worstLegPerLane.push(Math.max(worst, measuredLegFindings(job, manifest.of)));
      continue;
    }
    // A contiguous lane's legs are the slices its runner cuts from the enumerator's order, read from the committed sizes.
    if (contiguous !== undefined) {
      const enumerator = LANE_ENUMERATORS[lane];
      const sizesText = readOr(ROOT, contiguous.sizesFile, `${lane}'s shard sizes`);
      const sizes = sizesText === null ? null : parseShardSizes(sizesText);
      if (enumerator === undefined || sizes === null) {
        findings.push(
          `${lane}: its legs cannot be read (${enumerator === undefined ? 'no unit enumerator' : `no MEASURED_SHARD_SIZES in ${contiguous.sizesFile}`}), so job ${job} is priced by nothing.`
        );
        continue;
      }
      const ids = (await enumerator(ROOT)).map((u) => u.id);
      const legs = contiguousLegs(ids, sizes, sizes.length);
      const worst = priceLegs(lane, job, legs, sizes.length, fixedMinutes, defaultUnitMs, parallel);
      priced.add(job);
      worstLegPerLane.push(Math.max(worst, measuredLegFindings(job, sizes.length)));
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(SHARD_COUNTS, lane)) {
      findings.push(
        `${lane} is sharded (SHARD_COUNTS) but has no committed manifest at ` +
          `${shardManifestPath(lane)}. Run \`npx tsx scripts/gate-bind.ts --write\` first.`
      );
      continue;
    }
    const laneIds = lock.filter((e) => e.ci.kind === 'step' && e.ci.job === lane).map((e) => e.id);
    // A lane with zero lock entries and no manifest (quality-submodule-branches) has no units to price; it falls through to check 2's job-level set below rather than vanishing.
    if (laneIds.length === 0) continue;
    priced.add(lane);
    worstLegPerLane.push(
      Math.max(
        priceLeg(lane, 1, 1, laneIds, fixedMinutes, defaultUnitMs, parallel),
        measuredLegFindings(lane, 1)
      )
    );
    findings.push(
      ...indivisibleFindings(lane, laneIds, fixedMinutes, durations.units, undefined, parallel)
    );
  }

  // The committed plan against the rebalanced one, per rebalanced lane: a broken rule is a finding, a gain over REBALANCE_ADVISORY_MIN is an advisory line, a unit with no cost is left to check 4, which already names it.
  const rebalanceNotes: string[] = [];
  for (const lane of Object.keys(REBALANCE_LANES).sort()) {
    if (inert.includes(lane)) continue;
    try {
      const { result } = await rebalanceLane(lane, durations);
      for (const v of result.violations)
        findings.push(`${lane}: the committed plan breaks a rebalanceConstraints rule: ${v}`);
      if (result.gainMinutes !== null && result.gainMinutes > REBALANCE_ADVISORY_MIN)
        rebalanceNotes.push(
          `rebalance available: ${lane}, ${result.gainMinutes.toFixed(2)} min (npx tsx scripts/gates/check-lane-budget.ts --rebalance ${lane})`
        );
    } catch (e) {
      if (e instanceof RebalanceError && e.kind === 'unknown') continue;
      findings.push(
        `${lane}: --rebalance cannot plan it: ${e instanceof Error ? e.message : String(e)}`
      );
    }
  }

  if (priced.size === 0 || unitCount === 0) {
    console.error(
      `${RED}✗${NC} lane-budget priced ${priced.size} lane(s) and ${unitCount} unit(s); the gate is ` +
        'not seeing the lanes, and its green would mean nothing.'
    );
    return 1;
  }

  // Check 2 over every runner job that is not a priced lane, by the display names budget_report measured it under. A priced lane's matrix legs were judged above, per leg, and are skipped here.
  const { judged: judgedSamples, unchecked } = checkTwoPartition(runnerJobs, priced, samplesFor);
  const judgedJobs = new Set(judgedSamples.map((x) => x.job));
  findings.push(...judgeJobSamples(judgedSamples));
  if (unchecked.length > 0) {
    const shown = [...unchecked].sort();
    findings.push(
      `check 2: ${unchecked.length} job(s) in ${CI_WORKFLOW} and its callees are UNCHECKED: no ` +
        `job_p90_minutes entry in ${DURATIONS_PATH} matches their display name. A job that ` +
        'never ran successfully in the sampled runs has no p90, and unknown is not within ' +
        `budget: ${shown.join(', ')}.`
    );
  }
  const unmatched = Object.keys(measured).filter((l) => !matchedLabels.has(l));

  // Exemption liveness: an entry whose test file or job is gone is a hole, not an approval.
  const jobSet = runnerJobSet;
  for (const e of LANE_BUDGET_EXEMPTIONS) {
    if (!existsSync(path.join(ROOT, 'packages', 'e2e-tests', 'tests', e.unit))) {
      findings.push(
        `LANE_BUDGET_EXEMPTIONS names ${e.unit}, which no longer exists under ` +
          'packages/e2e-tests/tests. Delete the entry.'
      );
    }
    if (!jobSet.has(e.job)) {
      findings.push(
        `LANE_BUDGET_EXEMPTIONS places ${e.unit} in job ${e.job}, which no workflow defines.`
      );
    }
  }
  for (const c of JOB_BUDGET_CAPS) {
    if (!jobSet.has(c.job)) {
      findings.push(`JOB_BUDGET_CAPS names job ${c.job}, which no workflow defines. Delete it.`);
    }
  }

  const timeoutList = [...timeoutSites.values()];
  if (CHECK7_ENABLED) findings.push(...timeoutFindings(timeoutList));

  // The model against reality: each variant leg's prediction beside the p90 measured under the same variant, leg and leg count. Advisory; `--table` prints every row.
  const compared = predictions.map((p) => {
    const sample = samplesForJob(sites, measured, p.job).find(
      (x) =>
        variantOf(x.label) === p.variant &&
        legIndexOf(x.label) === p.index &&
        x.label.endsWith(`/${p.of})`)
    );
    return { ...p, measured: sample?.minutes ?? null };
  });
  const deltas = compared.flatMap((c) => (c.measured === null ? [] : [c.minutes - c.measured]));
  const driftNote =
    deltas.length === 0
      ? 'model vs measured: no variant leg has a measured p90'
      : `model vs measured: max |delta| ${Math.max(...deltas.map(Math.abs)).toFixed(2)}m over ` +
        `${deltas.length} variant leg(s)`;
  if (process.argv.includes('--table')) {
    console.log('lane                 variant         leg   predicted  measured p90  delta');
    for (const c of compared) {
      console.log(
        `${c.lane.padEnd(20)} ${c.variant.padEnd(15)} ${`${c.index}/${c.of}`.padEnd(5)} ` +
          `${c.minutes.toFixed(2).padStart(9)}  ${(c.measured === null ? '-' : c.measured.toFixed(1)).padStart(12)}  ` +
          `${c.measured === null ? '' : (c.minutes - c.measured >= 0 ? '+' : '') + (c.minutes - c.measured).toFixed(2)}` +
          `${c.minutes > PER_LEG_BUDGET_MIN ? '  OVER' : ''}`
      );
    }
  }

  const pipelineMinutes = pipelineEstimateMinutes(
    [...worstLegPerLane, ...judgedSamples.map((x) => x.minutes)],
    durations.concurrency
  );
  const pipelineNote =
    `pipeline estimate (advisory, worst-leg-per-lane approximation -- see file header): ` +
    `${pipelineMinutes.toFixed(1)}m against a ${PIPELINE_BUDGET_MIN}m target`;
  if (PIPELINE_ENFORCED && pipelineMinutes > PIPELINE_BUDGET_MIN) {
    findings.push(`${pipelineNote}, over budget`);
  }

  const shape =
    `${priced.size} lane(s), ${legCount} leg(s), ${unitCount} unit(s) ` +
    `(${measuredCount} measured, ${defaultedCount} by defaultUnitMs), ` +
    `parallel: ${parallelLanes.join(', ') || 'none'}, ` +
    `${judgedJobs.size}/${runnerJobs.length - priced.size} other job(s) judged ` +
    `(${judgedSamples.length} display-name sample(s); ${unmatched.length} measured name(s) match no current job), ` +
    `${LANE_BUDGET_EXEMPTIONS.length} unit exemption(s), ${JOB_BUDGET_CAPS.length} job cap(s), ` +
    `${timeoutList.length} job timeout-minutes read (check 7); ` +
    `inert: ${inert.join(', ') || 'none'}; ${driftNote}; ` +
    `rebalance: ${rebalanceNotes.length} lane(s) over the ${REBALANCE_ADVISORY_MIN}m advisory`;
  for (const note of rebalanceNotes) console.log(`advisory: ${note}`);
  if (findings.length === 0) {
    console.log(`${GREEN}✓${NC} lane-budget: ${shape}. ${pipelineNote}`);
    return 0;
  }
  console.error(
    `${RED}✗${NC} lane-budget: ${findings.length} finding(s); ${shape}. ${pipelineNote}`
  );
  for (const f of findings) console.error(`  ${f}`);
  return 1;
}

// --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------

/** A check-7 fixture site in `wf.yml`, its minutes resolved the way `workflowJobs` resolves a literal. */
function t7(job: string, timeoutRaw: string | null): TimeoutSite {
  return {
    file: 'wf.yml',
    job,
    timeoutRaw,
    timeoutMinutes: resolveTimeoutMinutes(timeoutRaw, new Map()),
  };
}

/** A one-variant fixture lane, `fx`, with no fixed cost: a and b cost 10 minutes, c and d 1, e and f 2, unless `minutes` says otherwise. */
function rbModel(
  of: number,
  minutes: Record<string, number> = { a: 10, b: 10, c: 1, d: 1, e: 2, f: 2 }
): LaneModel {
  const units = Object.fromEntries(Object.entries(minutes).map(([k, m]) => [k, m * 60_000]));
  return laneModel('fx', of, { jobs: {}, units, variantCosts: undefined }, undefined);
}

/** `<kind>: <message>` of the RebalanceError a call throws, or '' when it returns. */
function rebalanceRefusal(call: () => unknown): string {
  try {
    call();
    return '';
  } catch (e) {
    return e instanceof RebalanceError ? `${e.kind}: ${e.message}` : `other: ${String(e)}`;
  }
}

/** Per live rebalanced lane: the committed plan breaks no rule, the rebalanced plan is never worse than it, and feeding the rebalanced plan back in as committed changes nothing. */
async function liveRebalanceControls(
  durations: LaneDurations
): Promise<{ name: string; ok: boolean; detail?: string }[]> {
  const out: { name: string; ok: boolean; detail?: string }[] = [];
  for (const lane of Object.keys(REBALANCE_LANES).sort()) {
    try {
      const { result, input } = await rebalanceLane(lane, durations);
      const again =
        REBALANCE_LANES[lane]?.shape === 'contiguous'
          ? rebalanceContiguous(input.model, input.ids, input.constraints, result.rebalanced)
          : rebalanceAssign(input.model, input.ids, input.constraints, result.rebalanced);
      out.push({
        name: `STABLE (live ${lane}): the committed plan breaks no rule, the rebalanced one is no worse, and a second run over it changes nothing`,
        ok:
          result.violations.length === 0 &&
          (result.gainMinutes ?? -1) >= 0 &&
          !again.changed &&
          JSON.stringify(again.rebalanced) === JSON.stringify(result.rebalanced),
        detail: JSON.stringify({
          violations: result.violations,
          gain: result.gainMinutes,
          secondChanged: again.changed,
        }),
      });
      if (lane === 'quality-pytest') {
        // The cap the BUDGET control relies on, shown to fire: one evaluation allowed, so each run stops after its first step and says so.
        const tight = rebalanceAssign(
          input.model,
          input.ids,
          input.constraints,
          input.committed,
          1
        );
        out.push({
          name: `FIRES (live ${lane}): a local search held to 1 evaluation stops after one step and reports CAPPED, not a local optimum`,
          ok: tight.search.includes('CAPPED') && tight.evaluations < result.evaluations,
          detail: `${tight.evaluations} evaluation(s); ${tight.search}`,
        });
        out.push({
          name: `BUDGET (live ${lane}): the rebalance reaches a local optimum within ${QUALITY_PYTEST_EVALUATION_BUDGET} candidate evaluations, so a search that stops converging is a red control, not a hang`,
          ok:
            result.evaluations > 0 &&
            result.evaluations <= QUALITY_PYTEST_EVALUATION_BUDGET &&
            !result.search.includes('CAPPED'),
          detail: `${result.evaluations} evaluation(s); ${result.search}`,
        });
      }
    } catch (e) {
      out.push({ name: `STABLE (live ${lane})`, ok: false, detail: String(e) });
    }
  }
  return out;
}

async function selftest(): Promise<number> {
  // The live OPS Provision slicing, read the way main() reads it, for the measured-branch control below.
  const opsIds = (await LANE_ENUMERATORS['ops-tutorials']?.(ROOT))?.map((u) => u.id) ?? [];
  const opsSizes = parseShardSizes(
    readFileSync(path.join(ROOT, CONTIGUOUS_LANES['ops-tutorials']?.sizesFile ?? ''), 'utf-8')
  );
  const liveDurations = readDurations(ROOT);
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
      name: 'MATCH: a D-W3-exempt unit over budget alone is silent (the real exemption list)',
      ok:
        indivisibleFindings(
          'test-e2e-k8s-multinode',
          ['e2e-k8s:kube/17-multinode-cluster.test.ts'],
          2,
          { 'e2e-k8s:kube/17-multinode-cluster.test.ts': 10.9 * 60_000 }
        ).length === 0,
    },
    {
      name: 'FIRES: the same cost on a unit the exemption list does not name',
      ok: indivisibleFindings('test-e2e-k8s', ['e2e-k8s:kube/99-other.test.ts'], 2, {
        'e2e-k8s:kube/99-other.test.ts': 10.9 * 60_000,
      }).some((f) => f.includes('Indivisible')),
    },
    {
      name: 'CONTROL: every unit exemption and job cap names its ruling',
      ok:
        LANE_BUDGET_EXEMPTIONS.every((e) => /D-W3/.test(e.ruling)) &&
        JOB_BUDGET_CAPS.every((c) => /2026-09-28|#[0-9a-f]{8}/.test(c.ruling)),
    },
    // --- check 2: job-level p90 and the 2026-09-28 exemption caps ----------------
    {
      name: 'MATCH: an exempt job (E2E K8s Ceph) at 19.8m is under its 20m cap',
      ok: jobBudgetFindings({ 'test-e2e-k8s-ceph': 19.8 }).length === 0,
    },
    {
      name: 'MATCH: an exempt job (E2E K8s Multinode) at 23.0m is under its 25m cap',
      ok: jobBudgetFindings({ 'test-e2e-k8s-multinode': 23.0 }).length === 0,
    },
    {
      name: 'FIRES: an exempt job over its OWN cap (K8s Ceph at 20.1m) is red, naming the ruling',
      ok: jobBudgetFindings({ 'test-e2e-k8s-ceph': 20.1 }).some(
        (f) => f.includes('exemption cap of 20m') && f.includes('2026-09-28')
      ),
    },
    {
      name: 'FIRES: a NON-exempt job over 12 (E2E Ceph at 14.3m; it left the list 2026-09-28)',
      ok: jobBudgetFindings({ 'test-e2e-ceph': 14.3 }).some((f) => f.includes('over the 12m')),
    },
    {
      name: 'FIRES: a non-exempt job at 12.1m, and MATCH: the same job at 11.9m',
      ok:
        jobBudgetFindings({ 'test-e2e-k8s': 12.1 }).length === 1 &&
        jobBudgetFindings({ 'test-e2e-k8s': 11.9 }).length === 0,
    },
    {
      name: 'workflowJobs: a caller job is marked by its uses:, a runner job is not; name and matrix are read',
      ok: (() => {
        const jobs = workflowJobs(
          "on: push\njobs:\n  a:\n    name: 'Tests + Infra'\n    uses: ./.github/workflows/x.yml\n  b:\n    runs-on: ubuntu-latest\n    strategy:\n      matrix:\n        shard: [1, 2]\n  c:\n    name: C\n    env:\n      matrix: no\n"
        );
        return (
          JSON.stringify(jobs) ===
          JSON.stringify([
            {
              id: 'a',
              uses: '.github/workflows/x.yml',
              name: 'Tests + Infra',
              hasMatrix: false,
              timeoutRaw: null,
              timeoutMinutes: null,
            },
            {
              id: 'b',
              uses: null,
              name: 'b',
              hasMatrix: true,
              timeoutRaw: null,
              timeoutMinutes: null,
            },
            {
              id: 'c',
              uses: null,
              name: 'C',
              hasMatrix: false,
              timeoutRaw: null,
              timeoutMinutes: null,
            },
          ])
        );
      })(),
    },
    // --- parallelism: a leg with N workers, and a mutex group bounding it ---------
    {
      name: 'MATCH: 8 units of 10m on 8 workers is 10m (+1m fixed = 11m), no finding',
      ok:
        legFindings(
          'lane-p',
          1,
          1,
          ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
          1,
          Object.fromEntries(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((k) => [k, 10 * 60_000])),
          undefined,
          { workers: 8, groupOf: () => undefined }
        ).length === 0,
    },
    {
      name: 'FIRES: the same leg on 4 workers is 20m + 1m, and the finding names the workers',
      ok: legFindings(
        'lane-p',
        1,
        1,
        ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
        1,
        Object.fromEntries(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((k) => [k, 10 * 60_000])),
        undefined,
        { workers: 4, groupOf: () => undefined }
      ).some((f) => f.includes('estimated 21.0m') && f.includes('4 workers')),
    },
    {
      name: 'CONTROL: with no parallelism the same leg is the serial 81m',
      ok: legFindings(
        'lane-p',
        1,
        1,
        ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
        1,
        Object.fromEntries(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((k) => [k, 10 * 60_000])),
        undefined
      ).some((f) => f.includes('estimated 81.0m')),
    },
    {
      name: 'FIRES: a mutex group (2 x 6m on one worker) bounds a 4-worker leg at 12m + 0.5m fixed',
      ok: (() => {
        const units = { g1: 6 * 60_000, g2: 6 * 60_000, f1: 60_000, f2: 60_000, f3: 60_000 };
        const groupOf = (id: string): string | undefined => (id.startsWith('g') ? 'G' : undefined);
        const bounded = legFindings('lane-p', 1, 1, Object.keys(units), 0.5, units, undefined, {
          workers: 4,
          groupOf,
        });
        const free = legFindings('lane-p', 1, 1, Object.keys(units), 0.5, units, undefined, {
          workers: 4,
          groupOf: () => undefined,
        });
        return (
          bounded.some((f) => f.includes('estimated 12.5m') && f.includes('mutex group G')) &&
          free.length === 0
        );
      })(),
    },
    {
      name: 'FIRES: check 3 under parallelism judges the GROUP as the indivisible thing',
      ok:
        indivisibleFindings('lane-p', ['g1', 'g2'], 1, { g1: 6 * 60_000, g2: 6 * 60_000 }, [], {
          workers: 4,
          groupOf: () => 'G',
        }).some((f) => f.includes('mutex group G')) &&
        indivisibleFindings('lane-p', ['g1', 'g2'], 1, { g1: 6 * 60_000, g2: 6 * 60_000 }, [], {
          workers: 4,
          groupOf: () => undefined,
        }).length === 0,
    },
    // --- display names: Actions API name back to job id --------------------------
    {
      name: 'display name: a called job is "<caller> / <name>", exact, not a prefix',
      ok: (() => {
        const re = displayNamePattern(['Tests + Infra'], 'E2E K8s Ceph', false);
        return (
          re.test('Tests + Infra / E2E K8s Ceph') &&
          !re.test('Tests + Infra / E2E K8s Ceph Workers') &&
          !re.test('E2E K8s Ceph')
        );
      })(),
    },
    {
      name: 'display name: a matrix job with no template takes the " (<values>)" suffix, and its leg index is read',
      ok: (() => {
        const re = displayNamePattern(['Quality'], 'Code', true);
        return (
          re.test('Quality / Code (3)') &&
          re.test('Quality / Code') &&
          legIndexOf('Quality / Code (3)') === 3 &&
          legIndexOf('Tests + Infra / E2E Workers (fedora-43, 6/8)') === 6 &&
          legIndexOf('OPS Tests / OPS Check (linux-arm64)') === 1
        );
      })(),
    },
    {
      name: 'display name: one template value never swallows another job\'s two ("(linux-amd64, 2/4)" is not "(${{ matrix.name }})")',
      ok: (() => {
        const qemu = displayNamePattern(['OPS Tests'], 'OPS Provision (${{ matrix.name }})', true);
        const vm = displayNamePattern(
          ['OPS Tests'],
          'OPS Provision (${{ matrix.name }}, ${{ matrix.shard }}/${{ matrix.shard_of }})',
          true
        );
        const label = 'OPS Tests / OPS Provision (linux-amd64, 2/4)';
        return (
          !qemu.test(label) &&
          vm.test(label) &&
          qemu.test('OPS Tests / OPS Provision (macos-intel)')
        );
      })(),
    },
    {
      name: 'check 2: a capped job is judged through its display name; a priced matrix lane is skipped; an unmatched job is UNCHECKED',
      ok: (() => {
        const sites = [
          {
            id: 'test-e2e-k8s-ceph',
            pattern: displayNamePattern(['Tests + Infra'], 'E2E K8s Ceph', false),
          },
          { id: 'quality-code', pattern: displayNamePattern(['Quality'], 'Code', true) },
          {
            id: 'test-e2e-ceph',
            pattern: displayNamePattern(['Tests + Infra'], 'E2E Ceph', false),
          },
          { id: 'never-ran', pattern: displayNamePattern([], 'Never Ran', false) },
        ];
        const measured = {
          'Tests + Infra / E2E K8s Ceph': 19.8,
          'Quality / Code (1)': 30,
          'Tests + Infra / E2E Ceph': 14.3,
        };
        const part = checkTwoPartition(
          sites.map((x) => x.id),
          new Set(['quality-code']),
          (job) => samplesForJob(sites, measured, job)
        );
        const f = judgeJobSamples(part.judged);
        return (
          part.judged.every((x) => x.job !== 'quality-code') &&
          JSON.stringify(part.unchecked) === JSON.stringify(['never-ran']) &&
          f.length === 1 &&
          (f[0] ?? '').includes('test-e2e-ceph ("Tests + Infra / E2E Ceph")')
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
    // --- check 7: every runner job's timeout-minutes, read from the workflow text ---
    {
      name: 'FIRES (the function itself): a job over the 15-minute ceiling',
      ok: timeoutFindings([t7('job-a', '90')]).some((f) => f.includes('over the 15m')),
    },
    {
      name: 'FIRES (the function itself): a job with no timeout-minutes at all',
      ok: timeoutFindings([t7('job-a', null)]).some((f) =>
        f.includes('declares no timeout-minutes')
      ),
    },
    {
      name: 'MATCH: a job at exactly 15 minutes is fine',
      ok: timeoutFindings([t7('job-a', '15')]).length === 0,
    },
    {
      name: 'check 7 reads a capped job against its ruling timeout (K8s Ceph 25, K8s Multinode 30), not 15',
      ok:
        timeoutFindings([t7('test-e2e-k8s-multinode', '30'), t7('test-e2e-k8s-ceph', '25')])
          .length === 0 &&
        timeoutFindings([t7('test-e2e-k8s-multinode', '31')]).some((f) =>
          f.includes('over the 30m ceiling')
        ) &&
        timeoutFindings([t7('test-e2e-k8s-ceph', '26')]).some((f) =>
          f.includes('over the 25m ceiling')
        ),
    },
    {
      name: 'E2E Ceph Workers non-apt (#fc4f34f8): p90 16.1 is red naming the ruling, 16.0 is not; timeout 20 accepted, 21 red',
      ok:
        jobBudgetFindings({ 'test-e2e-ceph-workers-rpm': 16.1 }).some(
          (f) => f.includes('exemption cap of 16m') && f.includes('#fc4f34f8')
        ) &&
        jobBudgetFindings({ 'test-e2e-ceph-workers-rpm': 16.0 }).length === 0 &&
        timeoutFindings([t7('test-e2e-ceph-workers-rpm', '20')]).length === 0 &&
        timeoutFindings([t7('test-e2e-ceph-workers-rpm', '21')]).some(
          (f) => f.includes('over the 20m ceiling') && f.includes('#fc4f34f8')
        ),
    },
    {
      name: 'FIRES (from workflow text): a job with no timeout-minutes and a job at 16 are red; a job at 15 and a step-level 90 are not',
      ok: (() => {
        const wf =
          'on: push\njobs:\n' +
          '  bare:\n    runs-on: ubuntu-latest\n    steps:\n      - run: x\n        timeout-minutes: 5\n' +
          '  over:\n    runs-on: ubuntu-latest\n    timeout-minutes: 16\n' +
          '  ok:\n    runs-on: ubuntu-latest\n    timeout-minutes: 15 # the T4.1 ceiling\n    steps:\n      - run: y\n        timeout-minutes: 90\n';
        const f = timeoutFindings(
          workflowJobs(wf).map((j) => ({
            file: 'wf.yml',
            job: j.id,
            timeoutRaw: j.timeoutRaw,
            timeoutMinutes: j.timeoutMinutes,
          }))
        );
        return (
          f.length === 2 &&
          f.some((x) => x.includes('job bare declares no timeout-minutes')) &&
          f.some((x) => x.includes('job over has timeout-minutes 16'))
        );
      })(),
    },
    {
      name: 'a ${{ matrix.timeout }} timeout resolves to the LARGEST leg (ci-build-cli shape), and one naming no matrix key is red',
      ok: (() => {
        const wf =
          'on: push\njobs:\n  cli:\n    runs-on: x\n    timeout-minutes: ${{ matrix.timeout }}\n    strategy:\n      matrix:\n        include:\n          - os: a\n            timeout: 15\n          - os: b\n            timeout: 20\n' +
          '  odd:\n    runs-on: x\n    timeout-minutes: ${{ inputs.t }}\n';
        const jobs = workflowJobs(wf);
        const f = timeoutFindings(
          jobs.map((j) => ({
            file: 'wf.yml',
            job: j.id,
            timeoutRaw: j.timeoutRaw,
            timeoutMinutes: j.timeoutMinutes,
          }))
        );
        return (
          jobs[0]?.timeoutMinutes === 20 &&
          f.some((x) => x.includes('job cli has timeout-minutes 20')) &&
          f.some((x) => x.includes('job odd') && x.includes('resolves to no number'))
        );
      })(),
    },
    {
      name: 'CHECK 6 IS ADVISORY: the flag stays false (D-W1 text)',
      ok: PIPELINE_ENFORCED === false,
    },
    {
      name: 'CHECK 7 IS ON (T4.4): the flag is true',
      ok: CHECK7_ENABLED === true,
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
        const plan = shardPlan(
          live,
          laneCapabilities(workflowText),
          SHARD_COUNTS,
          measuredStepDurations(ROOT)
        );
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
    // --- variant legs: per-variant fixed cost, leg extras and unit overrides -------
    {
      name: 'variantOf reads the matrix variant before the leg, and nothing from a plain leg label',
      ok:
        variantOf('Tests + Infra / E2E Workers (fedora-43, 1/8)') === 'fedora-43' &&
        variantOf('OPS Tests / OPS Provision (linux-amd64, 2/4)') === 'linux-amd64' &&
        variantOf('Quality / Pytest (3/3)') === null &&
        variantOf('Tests + Infra / E2E Ceph') === null,
    },
    {
      name: "variantLegInputs adds the leg's extra to the variant's fixed cost, and its units override the lane's",
      ok: (() => {
        const cost: VariantCost = {
          fixedMinutes: 7,
          legExtraMinutes: { '1': 3 },
          units: { a: 120_000 },
        };
        const leg1 = variantLegInputs(cost, 1, { a: 60_000, b: 30_000 });
        const leg2 = variantLegInputs(cost, 2, { a: 60_000, b: 30_000 });
        return (
          leg1.fixedMinutes === 10 &&
          leg2.fixedMinutes === 7 &&
          leg1.units.a === 120_000 &&
          leg1.units.b === 30_000
        );
      })(),
    },
    {
      name: 'FIRES: a leg under 12 on the lane-wide fixed cost is over 12 on its slow variant (the VM reset the old model left out)',
      ok: (() => {
        const units = { u: 5 * 60_000 };
        const slow = variantLegInputs({ fixedMinutes: 7.6 }, 1, units);
        return (
          legFindings('lane-v', 1, 8, ['u'], 3.2, units, undefined).length === 0 &&
          legFindings('lane-v (slow)', 1, 8, ['u'], slow.fixedMinutes, slow.units, undefined).some(
            (f) => f.includes('estimated 12.6m')
          )
        );
      })(),
    },
    {
      name: 'parseShardSizes reads the bash array, and refuses a missing or non-numeric one',
      ok:
        JSON.stringify(parseShardSizes('    MEASURED_SHARD_SIZES=(7 3 5 3)\n')) ===
          JSON.stringify([7, 3, 5, 3]) &&
        parseShardSizes('SIZES=(1 2)') === null &&
        parseShardSizes('MEASURED_SHARD_SIZES=(a b)') === null,
    },
    {
      name: "contiguousLegs slices by the sizes when they cover every unit, and by ceil(total / N) otherwise (run-sequence.sh's two branches)",
      ok: (() => {
        const ids = ['a', 'b', 'c', 'd', 'e'];
        const sized = contiguousLegs(ids, [3, 1, 1], 3).map((l) => l.ids.join(''));
        const fallback = contiguousLegs(ids, [3, 1], 3).map((l) => l.ids.join(''));
        return (
          JSON.stringify(sized) === JSON.stringify(['abc', 'd', 'e']) &&
          JSON.stringify(fallback) === JSON.stringify(['ab', 'cd', 'e'])
        );
      })(),
    },
    {
      name: 'CONTROL: the live variantCosts prices every VARIANT_PRICED_LANES lane (budget_report --refresh drops the field)',
      ok: VARIANT_PRICED_LANES.every(
        (lane) => Object.keys(liveDurations.variantCosts?.[lane] ?? {}).length > 0
      ),
    },
    // --- --rebalance: a planted imbalance, a refused rule, and a second run that changes nothing ---
    {
      name: 'FIRES: a planted imbalance (both 10m units on one leg) is rebalanced, and the gain is past the advisory line',
      ok: (() => {
        const r = rebalanceAssign(rbModel(2), ['a', 'b', 'c', 'd'], {}, [
          ['a', 'b'],
          ['c', 'd'],
        ]);
        return (
          r.changed &&
          (r.gainMinutes ?? 0) > REBALANCE_ADVISORY_MIN &&
          Math.max(...r.rebalancedMinutes.flat()) === 11
        );
      })(),
    },
    {
      name: 'MATCH: an already balanced plan is kept as committed, gain 0',
      ok: (() => {
        const r = rebalanceAssign(rbModel(2), ['a', 'b', 'c', 'd'], {}, [
          ['a', 'c'],
          ['b', 'd'],
        ]);
        return (
          !r.changed &&
          r.gainMinutes === 0 &&
          JSON.stringify(r.rebalanced) ===
            JSON.stringify([
              ['a', 'c'],
              ['b', 'd'],
            ])
        );
      })(),
    },
    {
      name: 'STABLE: a rebalanced fixture plan, fed back as the committed one, comes back unchanged',
      ok: (() => {
        const ids = ['a', 'b', 'c', 'd', 'e', 'f'];
        const first = rebalanceAssign(rbModel(3), ids, {}, [ids.slice(0, 4), ['e'], ['f']]);
        const second = rebalanceAssign(rbModel(3), ids, {}, first.rebalanced);
        return (
          first.changed &&
          !second.changed &&
          JSON.stringify(second.rebalanced) === JSON.stringify(first.rebalanced)
        );
      })(),
    },
    {
      name: 'REFUSED: together(a, b) with a pinned to leg 1 and b to leg 2 is unsatisfiable',
      ok: rebalanceRefusal(() =>
        rebalanceAssign(
          rbModel(2),
          ['a', 'b', 'c', 'd'],
          {
            together: [{ units: ['a', 'b'] }],
            onLeg: [
              { unit: 'a', leg: 1 },
              { unit: 'b', leg: 2 },
            ],
          },
          null
        )
      ).startsWith('unsatisfiable: fx: no leg can hold a + b'),
    },
    {
      name: 'REFUSED: a rule naming a leg the lane does not have, or a unit it does not hold',
      ok:
        rebalanceRefusal(() =>
          rebalanceAssign(
            rbModel(2),
            ['a', 'b', 'c', 'd'],
            { onLeg: [{ unit: 'a', leg: 3 }] },
            null
          )
        ).includes('leg 3 is outside 1..2') &&
        rebalanceRefusal(() =>
          rebalanceAssign(
            rbModel(2),
            ['a', 'b', 'c', 'd'],
            { notOnLeg: [{ unit: 'zz', leg: 1 }] },
            null
          )
        ).includes('names zz, which the lane does not hold'),
    },
    {
      name: 'REFUSED: a contiguous pin no slice can meet (the first unit pinned to leg 2)',
      ok: rebalanceRefusal(() =>
        rebalanceContiguous(rbModel(3), ['a', 'b', 'c'], { onLeg: [{ unit: 'a', leg: 2 }] }, null)
      ).startsWith('unsatisfiable: fx: none of the 1 contiguous split(s)'),
    },
    {
      name: 'REFUSED: a unit with no measured cost, named, and the lane declares no defaultUnitMs',
      ok: rebalanceRefusal(() =>
        rebalanceAssign(rbModel(2), ['a', 'b', 'c', 'new-unit'], {}, null)
      ).startsWith(
        'unknown: fx: 1 unit(s) have no measured cost and the lane declares no defaultUnitMs, so no plan can be priced: new-unit'
      ),
    },
    {
      name: 'FIRES: a committed plan breaking notOnLeg is reported, and the rebalanced plan obeys the rule even at a cost',
      ok: (() => {
        const c: RebalanceConstraints = {
          notOnLeg: [
            { unit: 'a', leg: 1 },
            { unit: 'b', leg: 1 },
          ],
        };
        const r = rebalanceAssign(rbModel(2), ['a', 'b', 'c', 'd'], c, [
          ['a', 'c'],
          ['b', 'd'],
        ]);
        return (
          r.violations.length === 1 &&
          r.changed &&
          r.gainMinutes === null &&
          constraintViolations(c, r.rebalanced).length === 0 &&
          JSON.stringify(r.rebalanced) ===
            JSON.stringify([
              ['c', 'd'],
              ['a', 'b'],
            ])
        );
      })(),
    },
    {
      name: 'a mutex group is indivisible under parallelism: g1 and g2 share a leg even when splitting them would balance better',
      ok: (() => {
        const units = { g1: 6 * 60_000, g2: 6 * 60_000, f1: 6 * 60_000, f2: 6 * 60_000 };
        const model = laneModel(
          'fx',
          2,
          { jobs: {}, units, variantCosts: undefined },
          { workers: 2, groupOf: (id) => (id.startsWith('g') ? 'G' : undefined) }
        );
        const r = rebalanceAssign(model, Object.keys(units), {}, null);
        return r.rebalanced.some((l) => l.includes('g1') && l.includes('g2'));
      })(),
    },
    {
      name: 'branch and bound finds the brute-force min-max over two variants with a leg-1 extra',
      ok: (() => {
        const ids = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];
        const ms = (xs: number[]): Record<string, number> =>
          Object.fromEntries(ids.map((id, i) => [id, (xs[i] as number) * 60_000]));
        const durations = {
          jobs: {},
          units: {},
          variantCosts: {
            fx: {
              v1: {
                fixedMinutes: 1,
                legExtraMinutes: { '1': 2 },
                units: ms([5, 4, 3, 3, 2, 2, 1]),
              },
              v2: { fixedMinutes: 2, units: ms([1, 2, 5, 4, 3, 1, 2]) },
            },
          },
        };
        const model = laneModel('fx', 3, durations, undefined);
        let brute = Number.POSITIVE_INFINITY;
        for (let code = 0; code < 3 ** ids.length; code++) {
          const legs: string[][] = [[], [], []];
          let x = code;
          for (const id of ids) {
            (legs[x % 3] as string[]).push(id);
            x = Math.floor(x / 3);
          }
          if (legs.some((l) => l.length === 0)) continue;
          brute = Math.min(brute, Math.max(...planMinutes(model, legs).flat()));
        }
        const r = rebalanceAssign(model, ids, {}, null);
        return Math.abs(Math.max(...r.rebalancedMinutes.flat()) - brute) < 1e-9;
      })(),
    },
    {
      name: 'a contiguous pin costs what it must: pinning c to leg 1 forces the worse (3 1) split over the free (2 2)',
      ok: (() => {
        const ids = ['a', 'b', 'c', 'd'];
        const free = rebalanceContiguous(rbModel(2, { a: 1, b: 1, c: 1, d: 1 }), ids, {}, null);
        const pinned = rebalanceContiguous(
          rbModel(2, { a: 1, b: 1, c: 1, d: 1 }),
          ids,
          { onLeg: [{ unit: 'c', leg: 1 }] },
          null
        );
        return (
          JSON.stringify(free.rebalanced.map((l) => l.length)) === '[2,2]' &&
          JSON.stringify(pinned.rebalanced.map((l) => l.length)) === '[3,1]'
        );
      })(),
    },
    {
      name: 'CONTROL: the live rebalanceConstraints names both hand-kept rules (18/19 together, 06 off leg 1)',
      ok: (() => {
        const c = liveDurations.rebalanceConstraints ?? {};
        return (
          (c['test-e2e-workers']?.together ?? []).some(
            (t) =>
              t.units.some((u) => u.includes('18-ops')) &&
              t.units.some((u) => u.includes('19-rustfs'))
          ) &&
          (c['test-e2e-workers']?.notOnLeg ?? []).some(
            (p) => p.unit.includes('06-daemon') && p.leg === 1
          )
        );
      })(),
    },
    ...(await liveRebalanceControls(liveDurations)),
    {
      // run-sequence.sh falls back to the equal-count split when MEASURED_SHARD_SIZES stops summing to the tutorial count, and the gate prices that fallback without a finding, so this is where a stale split shows.
      name: 'CONTROL: the live OPS Provision sizes cover every tutorial, so run-sequence.sh takes its measured branch and not the ceil(total / N) fallback',
      ok:
        opsSizes !== null &&
        opsIds.length > 0 &&
        opsSizes.reduce((a, b) => a + b, 0) === opsIds.length,
      detail: `sizes ${JSON.stringify(opsSizes)} over ${opsIds.length} tutorials`,
    },
  ];

  return summarizeControls(cases);
}

const rebalanceAt = process.argv.indexOf('--rebalance');
if (process.argv.includes('--selftest')) process.exit(await selftest());
else if (rebalanceAt !== -1) {
  const lane = process.argv[rebalanceAt + 1];
  if (lane === undefined || lane.startsWith('--')) {
    console.error(`--rebalance needs a lane: ${Object.keys(REBALANCE_LANES).join(', ')}`);
    process.exit(2);
  }
  process.exit(await rebalanceMain(lane, process.argv.includes('--write')));
} else process.exit(await main());

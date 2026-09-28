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
 * CHECK 7 EXISTS AND IS SELFTESTED, AND MUST STAY OUT OF `main()`'S FINDINGS. T4.4 is
 * the box that turns it on; flipping `CHECK7_ENABLED` here before every job in `ci.yml`
 * carries a real `timeout-minutes: 15` would red the pipeline for a policy nothing has
 * adopted yet. The two capped jobs are read against their ruling timeouts (25, 30).
 *
 * WHY THE REAL RUN IS RED, AND WHY THAT IS THE POINT. Since budget_report.py writes
 * manifest-shaped unit ids and `job_p90_minutes` (2026-09-28), what the real run reports is
 * MEASURED overrun: E2E Workers legs, the E2E Ceph/K8s jobs, OPS Provision legs, and jobs no
 * sampled run completed successfully (UNCHECKED). Those are spec W's P2 exit, not defects
 * here. `--selftest` proves the logic against fixtures and the real exemption and cap
 * tables.
 *
 * PARALLEL LANES (`unitParallelism`). quality-pytest runs `pytest -n 4 --dist loadgroup` per
 * leg, so its per-file serial p90s are divided by the workers and floored at the largest
 * xdist group (enumerator `mutex`, plus a module-level `XDIST_GROUP`). Serial arithmetic
 * put those legs at 30-41m against a measured 8-12m.
 *
 * MEASURED LEGS. A priced lane's legs are judged twice: the unit-sum estimate (checks 1/4)
 * and the leg's own measured p90 by display name. The estimate alone missed E2E Workers,
 * whose runner step spends most of its time on VM setup no unit is charged for.
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
 * blocker: the real run is red on MEASURED overrun, not on this gate or its data: E2E Workers legs, E2E Ceph, Ceph Workers, K8s and Migrate over 12, K8s Ceph and K8s Multinode over their 2026-09-28 caps, OPS Provision legs, and jobs no sampled PR run completed successfully (UNCHECKED). It runs by hand until spec W's P2 exit holds (2026-09-28).
 * why: a CI leg that quietly grows past 12 minutes is invisible until the pipeline as a
 *   whole misses its 35-minute target (D-W1); this asserts the committed duration estimates
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

export const PER_LEG_BUDGET_MIN = 12;
/** D-W1 as revised 2026-09-25 (Operator rulings): GitHub Free, 20 concurrent jobs, a pipeline target of about 35 minutes, not 20. */
export const PIPELINE_BUDGET_MIN = 35;
export const MAX_STALENESS_DAYS = 14;
export const CHECK7_TIMEOUT_MAX_MIN = 15;

/** T4.4 flips this on. See the file header: check 7 must exist and be selftested first. */
export const CHECK7_ENABLED = false;

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
 * 12-minute budget. Exactly the two jobs the 2026-09-28 ruling kept exempt; E2E Ceph, E2E
 * Ceph Workers and E2E K8s LEFT the list that day and are judged at 12 like every other job.
 * `timeoutMinutes` is the ruling's `timeout-minutes` for the job, read by check 7 once T4.4
 * turns it on.
 */
export interface JobCap {
  job: string;
  p90Minutes: number;
  timeoutMinutes: number;
  ruling: string;
}
export const JOB_BUDGET_CAPS: readonly JobCap[] = [
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
];

/**
 * D-W2: "Stage Artifacts" (`cd-stage.yml`'s `stage`, called from `ci.yml`'s `stage-artifacts`)
 * and "Validate Promotion" (`ci.yml`'s `validate-promote`) are budgeted by
 * `check_job_timeout_headroom.py` against `lane-durations.json`'s `job_max_seconds`, not by
 * this gate. Named here so the split is printed every run rather than being a silent gap.
 */
export const HEADROOM_GATE_JOBS: readonly string[] = ['stage', 'validate-promote'];

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
}

/** A workflow's jobs, in order, each with its `name:`, its `uses:` and whether it has a matrix. Hand-parsed for the same reason `laneCapabilities` is. */
export function workflowJobs(text: string): WorkflowJob[] {
  const out: WorkflowJob[] = [];
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
      out.push({ id: job[1] as string, uses: null, name: job[1] as string, hasMatrix: false });
      inStrategy = false;
      continue;
    }
    const last = out[out.length - 1];
    if (last === undefined) continue;
    const uses = /^ {4}uses:\s*\.\/(\.github\/workflows\/[A-Za-z0-9_.-]+\.ya?ml)/.exec(raw);
    if (uses) last.uses = uses[1] as string;
    const name = /^ {4}name:\s*(.+?)\s*$/.exec(raw);
    if (name) last.name = (name[1] as string).replace(/^(['"])(.*)\1$/, '$2');
    if (/^ {4}\S/.test(raw)) inStrategy = /^ {4}strategy:\s*$/.test(raw);
    else if (inStrategy && /^ {6}matrix:/.test(raw)) last.hasMatrix = true;
  }
  return out;
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
 * the lane), not a D-W2 headroom job; every other job by each display-name sample it has, and
 * a job with none is UNCHECKED.
 */
export function checkTwoPartition(
  runnerJobs: readonly string[],
  priced: ReadonlySet<string>,
  samplesFor: (job: string) => JobSample[]
): { judged: JobSample[]; unchecked: string[]; headroom: string[] } {
  const judged: JobSample[] = [];
  const unchecked: string[] = [];
  const headroom: string[] = [];
  for (const job of runnerJobs) {
    if (priced.has(job)) continue;
    if (HEADROOM_GATE_JOBS.includes(job)) {
      headroom.push(job);
      continue;
    }
    const samples = samplesFor(job);
    if (samples.length === 0) unchecked.push(job);
    else judged.push(...samples);
  }
  return { judged, unchecked, headroom };
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

// --------------------------------------------------------------------------- Check 7: present, wired off until T4.4 ---------------------------------------------------------------------------

export function timeoutFindings(
  caps: ReadonlyMap<string, Pick<LaneCapabilities, 'timeoutMinutes'>>,
  jobCaps: readonly JobCap[] = JOB_BUDGET_CAPS
): string[] {
  const findings: string[] = [];
  for (const [job, cap] of caps) {
    const ceiling = jobCaps.find((c) => c.job === job)?.timeoutMinutes ?? CHECK7_TIMEOUT_MAX_MIN;
    if (cap.timeoutMinutes === null || cap.timeoutMinutes > ceiling) {
      findings.push(
        `${job}: timeout-minutes is ${cap.timeoutMinutes ?? 'unset'}, over the ` +
          `${ceiling}m ceiling T4.4 will enforce.`
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

  // Every job that occupies a runner: ci.yml's own, plus every job of every reusable
  // workflow it calls, transitively. A caller job (`uses:`) is not a runner itself.
  // Walked PER CALL SITE, not per file: ci-build-docker.yml is called three times under three caller names, and each call reports under its own display name.
  const runnerJobSet = new Set<string>();
  const sites: { id: string; pattern: RegExp }[] = [];
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
    parallel: LegParallelism | undefined
  ): number => {
    findings.push(
      ...legFindings(lane, index, of, ids, fixedMinutes, durations.units, defaultUnitMs, parallel)
    );
    const { perUnit } = legCostMs(ids, durations.units, defaultUnitMs);
    legCount += 1;
    unitCount += ids.length;
    for (const u of perUnit) {
      if (durations.units[u.id] !== undefined) measuredCount += 1;
      else if (u.ms !== null) defaultedCount += 1;
    }
    return fixedMinutes + parallelLegMs(perUnit, parallel).ms / 60_000;
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
    // A lane named in TEST_LANE_WORKFLOWS whose job does not exist yet (ops-tutorials, T2.16) is inert by that table's own docstring; it is printed below, never silently dropped.
    if (!caps.has(lane)) {
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
      let worst = 0;
      const allIds: string[] = [];
      for (const leg of manifest.legs) {
        worst = Math.max(
          worst,
          priceLeg(lane, leg.index, manifest.of, leg.ids, fixedMinutes, defaultUnitMs, parallel)
        );
        allIds.push(...leg.ids);
      }
      priced.add(lane);
      worstLegPerLane.push(Math.max(worst, measuredLegFindings(lane, manifest.of)));
      findings.push(
        ...indivisibleFindings(lane, allIds, fixedMinutes, durations.units, undefined, parallel)
      );
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

  if (priced.size === 0 || unitCount === 0) {
    console.error(
      `${RED}✗${NC} lane-budget priced ${priced.size} lane(s) and ${unitCount} unit(s); the gate is ` +
        'not seeing the lanes, and its green would mean nothing.'
    );
    return 1;
  }

  // Check 2 over every runner job that is not a priced lane, by the display names budget_report measured it under. A priced lane's matrix legs were judged above, per leg, and are skipped here.
  const {
    judged: judgedSamples,
    unchecked,
    headroom,
  } = checkTwoPartition(runnerJobs, priced, samplesFor);
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

  if (CHECK7_ENABLED) findings.push(...timeoutFindings(caps));

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
    `${judgedJobs.size}/${runnerJobs.length - priced.size - headroom.length} other job(s) judged ` +
    `(${judgedSamples.length} display-name sample(s); ${unmatched.length} measured name(s) match no current job), ` +
    `${LANE_BUDGET_EXEMPTIONS.length} unit exemption(s), ${JOB_BUDGET_CAPS.length} job cap(s); ` +
    `left to check_job_timeout_headroom.py (D-W2): ${headroom.join(', ') || 'none'}; ` +
    `inert: ${inert.join(', ') || 'none'}`;
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
        JOB_BUDGET_CAPS.every((c) => /2026-09-28/.test(c.ruling)),
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
            { id: 'a', uses: '.github/workflows/x.yml', name: 'Tests + Infra', hasMatrix: false },
            { id: 'b', uses: null, name: 'b', hasMatrix: true },
            { id: 'c', uses: null, name: 'C', hasMatrix: false },
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
      name: 'check 7 reads a capped job against its ruling timeout (K8s Multinode 30), not 15',
      ok:
        timeoutFindings(new Map([['test-e2e-k8s-multinode', { timeoutMinutes: 30 }]])).length ===
          0 &&
        timeoutFindings(new Map([['test-e2e-k8s-multinode', { timeoutMinutes: 31 }]])).length === 1,
    },
    {
      name: 'CHECK 6 IS ADVISORY: the flag stays false (D-W1 text)',
      ok: PIPELINE_ENFORCED === false,
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

if (process.argv.includes('--selftest')) process.exit(selftest());
else process.exit(await main());

/**
 * The cost and cell-size arithmetic behind `--rpo` and `rdc backup churn` (D-cost, D-cells).
 *
 * Pure functions over the churn probe's record (`renet backup churn-probe`, function
 * `backup_churn_probe`), so the CLI verbs and the strategy's pre-enable estimate print one number.
 * Nothing here reaches a machine or the account: a probe measures, these functions only price it.
 */

const MIB = 1024 * 1024;
const GIB = 1024 ** 3;

/** R2's prices, USD: Class A (put, list) and Class B (get, head) per million, storage per GB-month. */
export const R2_PRICES = {
  classAPerMillion: 4.5,
  classBPerMillion: 0.36,
  storagePerGbMonth: 0.015,
} as const;

/** Days a chunk no kept snapshot can restore waits before it is deleted (the account's grace). */
export const DEFAULT_GRACE_DAYS = 7;
/** Unchanged hashes a run samples for the exists check (decision O3). */
export const DEFAULT_SAMPLED_HASHES = 16;
/** Commit HEADs, the manifest body read and the prune read each run: the fixed part of Class B. */
const FIXED_CLASS_B_PER_RUN = 4;
/** A month is 30 days for the estimate, as in the plan's table. */
const DAYS_PER_MONTH = 30;
/** The churn cap is twice the plan's quota (D-safeguard). */
const CHURN_CAP_FACTOR = 2;
/** Prunes are deferred past this many cells on a grid (the collapse cap, D-cells). */
export const COLLAPSE_CAP_CELLS = 262_144;

/** One repository's line of probe output. Mirrors `ChurnProbeRecord` in renet's backup_churn_probe.go. */
export interface ChurnProbeRecord {
  guid: string;
  /** `measured`, `baseline` (a first observation: not zero churn), `skipped`, `failed` or `forgotten`. */
  status: string;
  reason?: string;
  probedAt: string;
  intervalSeconds: number;
  imageBytes: number;
  changedBytes: number;
  changedExtents: number;
  extentSizeHistogram?: { label: string; upToBytes?: number; count: number }[];
  /** Bytes a fixed grid would upload, keyed by cell size (`1MiB`, `2MiB`, `4MiB`, `8MiB`). */
  projectedUploadBytes?: Record<string, number>;
  /** Cells a fixed grid would touch, keyed the same way. */
  projectedCells?: Record<string, number>;
}

export interface RpoCostInput {
  /** `N`: cells that change per run. */
  changedCells: number;
  /** `C`: bytes per cell. */
  cellBytes: number;
  /** The declared target, in seconds: one run per target. */
  targetSeconds: number;
  /** `W`: days of history the customer keeps (the `keepWithin` window). */
  windowDays: number;
  /** `G`: grace days; the account's 7 unless told otherwise. */
  graceDays?: number;
  /** `s`: sampled unchanged hashes a run asks about. */
  sampledHashes?: number;
  /** The plan's quota, to price the churn cap against. */
  quotaBytes?: number;
}

export interface RpoCostEstimate {
  runsPerDay: number;
  classAPerRun: number;
  classBPerRun: number;
  monthlyClassA: number;
  monthlyClassB: number;
  monthlyClassAUsd: number;
  monthlyClassBUsd: number;
  /** Charged to the customer's quota. */
  windowGiB: number;
  /** Absorbed by Rediacc, up to the cap. */
  waitingGiB: number;
  windowUsd: number;
  waitingUsd: number;
  storageUsd: number;
  totalUsd: number;
  /** Present when a quota was given. */
  cap?: {
    capGiB: number;
    /** Waiting storage at steady state. */
    steadyWaitingGiB: number;
    /** Steady-state waiting at or under the cap: a stream faster than hourly is never refused. */
    sustainable: boolean;
    /** Days of waiting accrual to reach the cap; null when nothing accrues. */
    daysToCap: number | null;
  };
}

/**
 * The monthly price of a declared target (D-cost), for N changed cells per run.
 *
 * ```
 * A_run = N + 1 (manifest) + 1/k (index; k = runs an hour, never below one put per run)
 * B_run = N + s + 4
 * window GiB  = N x C x r x W     (charged)
 * waiting GiB = N x C x r x G     (absorbed)
 * ```
 * GiB are priced as GB, as in the plan. The base image and older kept points are excluded, and N
 * is taken as the same on every run.
 */
export function estimateRpoCost(input: RpoCostInput): RpoCostEstimate {
  const graceDays = input.graceDays ?? DEFAULT_GRACE_DAYS;
  const sampled = input.sampledHashes ?? DEFAULT_SAMPLED_HASHES;
  const runsPerDay = 86_400 / input.targetSeconds;
  const runsPerHour = 3600 / input.targetSeconds;
  const classAPerRun = input.changedCells + 1 + Math.min(1, 1 / runsPerHour);
  const classBPerRun = input.changedCells + sampled + FIXED_CLASS_B_PER_RUN;
  const monthlyClassA = classAPerRun * runsPerDay * DAYS_PER_MONTH;
  const monthlyClassB = classBPerRun * runsPerDay * DAYS_PER_MONTH;
  const bytesPerDay = input.changedCells * input.cellBytes * runsPerDay;
  const windowGiB = (bytesPerDay * input.windowDays) / GIB;
  const waitingGiB = (bytesPerDay * graceDays) / GIB;
  const monthlyClassAUsd = (monthlyClassA * R2_PRICES.classAPerMillion) / 1e6;
  const monthlyClassBUsd = (monthlyClassB * R2_PRICES.classBPerMillion) / 1e6;
  const windowUsd = windowGiB * R2_PRICES.storagePerGbMonth;
  const waitingUsd = waitingGiB * R2_PRICES.storagePerGbMonth;
  const storageUsd = windowUsd + waitingUsd;
  const estimate: RpoCostEstimate = {
    runsPerDay,
    classAPerRun,
    classBPerRun,
    monthlyClassA,
    monthlyClassB,
    monthlyClassAUsd,
    monthlyClassBUsd,
    windowGiB,
    waitingGiB,
    windowUsd,
    waitingUsd,
    storageUsd,
    totalUsd: monthlyClassAUsd + monthlyClassBUsd + storageUsd,
  };
  if (input.quotaBytes !== undefined) {
    const capGiB = (input.quotaBytes * CHURN_CAP_FACTOR) / GIB;
    const waitingPerDayGiB = bytesPerDay / GIB;
    estimate.cap = {
      capGiB,
      steadyWaitingGiB: waitingGiB,
      sustainable: waitingGiB <= capGiB,
      daysToCap: waitingPerDayGiB > 0 ? capGiB / waitingPerDayGiB : null,
    };
  }
  return estimate;
}

/** What the measured samples say, and what they do not. */
export interface ChurnSummary {
  /** Measured records: the only ones that say anything about churn. */
  samples: number;
  /** First observations. A baseline has nothing to compare against and is not a zero-churn sample. */
  baselines: number;
  skipped: number;
  failed: number;
  /** Mean cells touched per run, by cell size; undefined with no measured sample. */
  changedCellsPerRun?: Record<string, number>;
  /** The largest sample, by cell size: the figure a cap check should hold against. */
  maxChangedCellsPerRun?: Record<string, number>;
  /** Mean bytes a fixed grid would upload per run, by cell size. */
  uploadBytesPerRun?: Record<string, number>;
  /** Mean seconds between the compared snapshots. */
  intervalSeconds?: number;
  imageBytes?: number;
  recommendation?: CellRecommendation;
}

/** Which rule of D-cells decided the cell size. */
export type CellRule = 'idle' | 'scattered-small' | 'clustered-large' | 'default' | 'collapse-cap';

export interface CellRecommendation {
  cellBytes: number;
  rule: CellRule;
  /** Share of the 4 MiB bytes that 1 MiB saves, in percent; present for `scattered-small` and `collapse-cap`. */
  savedPercent?: number;
}

function meanBy(
  records: ChurnProbeRecord[],
  pick: (r: ChurnProbeRecord) => Record<string, number> | undefined,
  reduce: 'mean' | 'max'
): Record<string, number> {
  const out: Record<string, number> = {};
  const labels = new Set(records.flatMap((r) => Object.keys(pick(r) ?? {})));
  for (const label of labels) {
    const values = records.map((r) => pick(r)?.[label] ?? 0);
    out[label] =
      reduce === 'max' ? Math.max(...values) : values.reduce((a, b) => a + b, 0) / values.length;
  }
  return out;
}

/**
 * Fold a run of probe records into a summary. Only `measured` records are samples: a `baseline`,
 * a `skipped` or a `failed` record reports no changed bytes because nothing was compared, and
 * reading that as "no churn" would price an idle repository for a busy one. With no measured
 * sample the figures are absent, never zero.
 */
export function summarizeChurn(records: ChurnProbeRecord[]): ChurnSummary {
  const measured = records.filter((r) => r.status === 'measured');
  const summary: ChurnSummary = {
    samples: measured.length,
    baselines: records.filter((r) => r.status === 'baseline').length,
    skipped: records.filter((r) => r.status === 'skipped').length,
    failed: records.filter((r) => r.status === 'failed').length,
  };
  if (measured.length === 0) return summary;
  summary.changedCellsPerRun = meanBy(measured, (r) => r.projectedCells, 'mean');
  summary.maxChangedCellsPerRun = meanBy(measured, (r) => r.projectedCells, 'max');
  summary.uploadBytesPerRun = meanBy(measured, (r) => r.projectedUploadBytes, 'mean');
  summary.intervalSeconds =
    measured.reduce((sum, r) => sum + r.intervalSeconds, 0) / measured.length;
  const last = measured[measured.length - 1];
  summary.imageBytes = last.imageBytes;
  summary.recommendation = recommendCellSize({
    imageBytes: last.imageBytes,
    projectedUploadBytes: summary.uploadBytesPerRun,
    projectedCells: summary.changedCellsPerRun,
  });
  return summary;
}

/** 1 MiB wins when it uploads at most this share of what 4 MiB would. */
const SMALL_CELL_SHARE = 0.5;
/** 8 MiB wins when it uploads at most this share more bytes than 4 MiB while it needs this share of the puts or fewer. */
const LARGE_CELL_BYTE_SLACK = 1.05;
const LARGE_CELL_PUT_SHARE = 0.6;

/**
 * The cell size D-cells recommends from a probe's projections.
 *
 * - 1 MiB when it saves at least half of the 4 MiB bytes (scattered small writes), unless the grid
 *   would pass the collapse cap, where prunes are deferred;
 * - 8 MiB when it uploads no more bytes and needs far fewer puts (clustered large writes);
 * - otherwise the 4 MiB default.
 */
export function recommendCellSize(input: {
  imageBytes: number;
  projectedUploadBytes: Partial<Record<string, number>>;
  projectedCells: Partial<Record<string, number>>;
}): CellRecommendation {
  const four = input.projectedUploadBytes['4MiB'] ?? 0;
  if (four <= 0) return { cellBytes: 4 * MIB, rule: 'idle' };

  const one = input.projectedUploadBytes['1MiB'];
  if (one !== undefined && one <= four * SMALL_CELL_SHARE) {
    const savedPercent = Math.round((1 - one / four) * 100);
    if (input.imageBytes / MIB > COLLAPSE_CAP_CELLS) {
      return { cellBytes: 4 * MIB, rule: 'collapse-cap', savedPercent };
    }
    return { cellBytes: MIB, rule: 'scattered-small', savedPercent };
  }

  const eight = input.projectedUploadBytes['8MiB'];
  const fourCells = input.projectedCells['4MiB'] ?? 0;
  const eightCells = input.projectedCells['8MiB'] ?? 0;
  if (
    eight !== undefined &&
    eight <= four * LARGE_CELL_BYTE_SLACK &&
    fourCells > 0 &&
    eightCells <= fourCells * LARGE_CELL_PUT_SHARE
  ) {
    return { cellBytes: 8 * MIB, rule: 'clustered-large' };
  }
  return { cellBytes: 4 * MIB, rule: 'default' };
}

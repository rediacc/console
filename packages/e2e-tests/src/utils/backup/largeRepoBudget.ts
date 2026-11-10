/**
 * The budget suite 31 (box K10) holds an incremental snapshot of a large repository to.
 *
 * Pure on purpose: the suite feeds it the snapshot records it measured, and the unit test feeds it
 * hand-made ones, so every direction (a clean record gives nothing, each way of going wrong gives
 * a violation) is proven without a 50 GiB repository.
 */

export const MIB = 1024 * 1024;
export const GIB = 1024 * MIB;

/** Cells of slack for the filesystem's own metadata writes (suite 26 measured 5 extra cells for a 4 KiB write, FS_METADATA_CELLS = 8 there; a 256 MiB write touches more extents). */
export const METADATA_CELL_SLACK = 32;

/** The incremental may take at most this fraction of the seed's time. */
const INCR_TIME_RATIO = 0.1;

/** Absolute cap on the incremental, so a slow seed cannot loosen the ratio. */
export const INCR_TIME_CAP_MS = 180_000;

/** The seed must have uploaded at least this fraction of the bytes it wrote. */
const SEED_UPLOAD_FLOOR = 0.98;

export interface SnapshotMeasure {
  durationMs: number;
  bytesUploaded: number;
  chunksUploaded: number;
  rehashReason?: string;
}

export interface LargeRepoBudgetInput {
  seed: SnapshotMeasure;
  incr: SnapshotMeasure;
  /** Bytes the test wrote between the two snapshots. */
  changedBytes: number;
  /** Bytes the seed wrote. */
  seedBytes: number;
  /** The chunk size the snapshot record reports (`cellBytes`). */
  cellBytes: number;
}

/** The absolute cap applies from this seed size up; below it the budget is purely proportional. */
export const CAP_FLOOR_BYTES = 20 * GIB;

/** Multiplier on the changed-bytes share of the seed, so measurement noise does not fail a healthy anchor path. */
export const INCR_SHARE_HEADROOM = 1.5;

/**
 * The incremental's time budget in ms, clipped to the cap when the seed is at least 20 GiB (or its size is not given).
 *
 * Snapshot time is linear in bytes (the hash cap plus upload), so a healthy incremental takes about
 * changedBytes / seedBytes of the seed's time. A fixed 10% ratio is unsatisfiable once the change
 * is more than a tenth of the seed (a 256 MiB change on the 2 GiB vm:check seed is 12%, measured
 * 12379 ms against 10124 ms). The ratio is therefore the larger of INCR_TIME_RATIO and the changed
 * share times INCR_SHARE_HEADROOM. At 20 GiB and up the share is a few percent at most (0.5% at
 * 50 GiB), the 10% ratio wins, and the nightly budget is unchanged. A full rehash takes about the
 * seed's whole time, far over either ratio, so the control stays separable.
 */
export const incrTimeBudgetMs = (
  seedDurationMs: number,
  seedBytes?: number,
  changedBytes?: number
): number => {
  const share =
    seedBytes !== undefined && seedBytes > 0 && changedBytes !== undefined && changedBytes > 0
      ? (changedBytes / seedBytes) * INCR_SHARE_HEADROOM
      : 0;
  const proportional = Math.max(INCR_TIME_RATIO, share) * seedDurationMs;
  if (seedBytes !== undefined && seedBytes < CAP_FLOOR_BYTES) return proportional;
  return Math.min(INCR_TIME_CAP_MS, proportional);
};

/** Time one seed file may take, per GiB written (a 4M-block direct-I/O dd on a worker VM measures well under half this). */
const SEED_FILE_MS_PER_GIB = 120_000;

/** The limit for one seed file of `bytes` bytes. */
export const seedFileLimitMs = (bytes: number): number =>
  Math.ceil((bytes / GIB) * SEED_FILE_MS_PER_GIB);

/** A message when seed file `index` (0-based) of `total` took longer than its limit; undefined otherwise. */
export const seedFileViolation = (
  index: number,
  total: number,
  bytes: number,
  elapsedMs: number
): string | undefined =>
  elapsedMs > seedFileLimitMs(bytes)
    ? `seed file ${index} of ${total} took ${elapsedMs} ms, over its ${seedFileLimitMs(bytes)} ms limit`
    : undefined;

/** What must hold about the SEED snapshot: the 50 GiB really went up, so the later ratio compares against a real full upload. */
export const seedViolations = (seed: SnapshotMeasure, seedBytes: number): string[] => {
  const out: string[] = [];
  if (!(seedBytes > 0)) out.push(`seedBytes is ${seedBytes}; the test wrote nothing to compare`);
  if (seed.bytesUploaded < SEED_UPLOAD_FLOOR * seedBytes) {
    out.push(
      `the seed uploaded ${seed.bytesUploaded} bytes, under ${SEED_UPLOAD_FLOOR * 100}% of the ${seedBytes} written; the time ratio would compare against a partial upload`
    );
  }
  if (!(seed.durationMs > 0)) out.push(`the seed reports durationMs ${seed.durationMs}`);
  return out;
};

/** Every way an incremental snapshot of a large repository can miss its budget; empty means it met it. */
export const largeRepoBudgetViolations = (input: LargeRepoBudgetInput): string[] => {
  const { seed, incr, changedBytes, cellBytes } = input;
  const out = seedViolations(seed, input.seedBytes);
  if (!(cellBytes > 0)) {
    out.push(`cellBytes is ${cellBytes}; the byte and chunk bounds cannot be computed`);
    return out;
  }
  if (incr.rehashReason) {
    out.push(
      `the incremental fell back to a full rehash (rehashReason "${incr.rehashReason}"); the anchor path was not used`
    );
  }
  const slackBytes = METADATA_CELL_SLACK * cellBytes;
  if (incr.bytesUploaded < changedBytes) {
    out.push(
      `the incremental uploaded ${incr.bytesUploaded} bytes, under the ${changedBytes} written; the change was not seen`
    );
  }
  if (incr.bytesUploaded > changedBytes + slackBytes) {
    out.push(
      `the incremental uploaded ${incr.bytesUploaded} bytes, over ${changedBytes} + ${slackBytes} slack; it re-sent unchanged data`
    );
  }
  const chunkCeiling = Math.ceil(changedBytes / cellBytes) + METADATA_CELL_SLACK;
  if (incr.chunksUploaded > chunkCeiling) {
    out.push(
      `the incremental uploaded ${incr.chunksUploaded} chunks, over the ${chunkCeiling} ceiling`
    );
  }
  const budget = incrTimeBudgetMs(seed.durationMs, input.seedBytes, changedBytes);
  if (incr.durationMs > budget) {
    const capped = input.seedBytes >= CAP_FLOOR_BYTES;
    const capNote = capped
      ? `, capped at ${INCR_TIME_CAP_MS} ms from 20 GiB`
      : ', no cap under 20 GiB';
    out.push(
      `the incremental took ${incr.durationMs} ms, over the ${budget} ms budget (${Math.round((budget / seed.durationMs) * 1000) / 10}% of the ${seed.durationMs} ms seed${capNote})`
    );
  }
  return out;
};

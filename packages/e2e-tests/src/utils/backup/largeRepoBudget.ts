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

/** The incremental's time budget in ms: the smaller of the cap and a tenth of the seed. */
export const incrTimeBudgetMs = (seedDurationMs: number): number =>
  Math.min(INCR_TIME_CAP_MS, INCR_TIME_RATIO * seedDurationMs);

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
  const budget = incrTimeBudgetMs(seed.durationMs);
  if (incr.durationMs > budget) {
    out.push(
      `the incremental took ${incr.durationMs} ms, over the ${budget} ms budget (min of ${INCR_TIME_CAP_MS} and ${INCR_TIME_RATIO * 100}% of the ${seed.durationMs} ms seed)`
    );
  }
  return out;
};

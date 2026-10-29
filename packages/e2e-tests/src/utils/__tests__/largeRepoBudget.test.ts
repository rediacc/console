import { describe, expect, it } from 'vitest';
import {
  GIB,
  INCR_TIME_CAP_MS,
  incrTimeBudgetMs,
  type LargeRepoBudgetInput,
  largeRepoBudgetViolations,
  METADATA_CELL_SLACK,
  MIB,
  seedViolations,
} from '../backup/largeRepoBudget';

const CELL = 4 * MIB;
const SEED_BYTES = 50 * GIB;
const CHANGED = 256 * MIB;

/** A record that meets every bound: a 50 GiB seed in 30 minutes, then a 256 MiB change in 20 s. */
const clean = (): LargeRepoBudgetInput => ({
  seed: {
    durationMs: 1_800_000,
    bytesUploaded: SEED_BYTES,
    chunksUploaded: SEED_BYTES / CELL,
  },
  incr: {
    durationMs: 20_000,
    bytesUploaded: CHANGED + 5 * CELL,
    chunksUploaded: CHANGED / CELL + 5,
  },
  changedBytes: CHANGED,
  seedBytes: SEED_BYTES,
  cellBytes: CELL,
});

describe('largeRepoBudgetViolations', () => {
  it('gives nothing for a clean record', () => {
    expect(largeRepoBudgetViolations(clean())).toEqual([]);
  });

  it('flags a full re-upload (bytes and chunks)', () => {
    const input = clean();
    input.incr.bytesUploaded = SEED_BYTES;
    input.incr.chunksUploaded = SEED_BYTES / CELL;
    const found = largeRepoBudgetViolations(input);
    expect(found.some((v) => v.includes('re-sent unchanged data'))).toBe(true);
    expect(found.some((v) => v.includes('chunks, over'))).toBe(true);
  });

  it('flags a set rehashReason', () => {
    const input = clean();
    input.incr.rehashReason = 'anchor-missing';
    const found = largeRepoBudgetViolations(input);
    expect(found).toHaveLength(1);
    expect(found[0]).toContain('anchor-missing');
  });

  it('flags a time over 10% of the seed', () => {
    const input = clean();
    input.seed.durationMs = 600_000;
    input.incr.durationMs = 61_000;
    expect(largeRepoBudgetViolations(input).some((v) => v.includes('budget'))).toBe(true);
    input.incr.durationMs = 60_000;
    expect(largeRepoBudgetViolations(input)).toEqual([]);
  });

  it('caps the time at 180 s however slow the seed was', () => {
    const input = clean();
    input.seed.durationMs = 10_000_000;
    expect(incrTimeBudgetMs(input.seed.durationMs)).toBe(INCR_TIME_CAP_MS);
    input.incr.durationMs = INCR_TIME_CAP_MS + 1;
    expect(largeRepoBudgetViolations(input).some((v) => v.includes('budget'))).toBe(true);
  });

  it('flags an upload smaller than the change', () => {
    const input = clean();
    input.incr.bytesUploaded = CHANGED - 1;
    const found = largeRepoBudgetViolations(input);
    expect(found.some((v) => v.includes('change was not seen'))).toBe(true);
  });

  it('accepts the exact edges of the byte and chunk bounds, and flags one past them', () => {
    const input = clean();
    input.incr.bytesUploaded = CHANGED + METADATA_CELL_SLACK * CELL;
    input.incr.chunksUploaded = CHANGED / CELL + METADATA_CELL_SLACK;
    expect(largeRepoBudgetViolations(input)).toEqual([]);
    input.incr.bytesUploaded += 1;
    input.incr.chunksUploaded += 1;
    expect(largeRepoBudgetViolations(input)).toHaveLength(2);
  });

  it('refuses a record it cannot compute bounds for', () => {
    const input = clean();
    input.cellBytes = 0;
    expect(largeRepoBudgetViolations(input).some((v) => v.includes('cellBytes'))).toBe(true);
  });

  it('reports every violation at once, not the first', () => {
    const input = clean();
    input.incr = {
      durationMs: 900_000,
      bytesUploaded: SEED_BYTES,
      chunksUploaded: SEED_BYTES / CELL,
      rehashReason: 'journal-lost',
    };
    expect(largeRepoBudgetViolations(input).length).toBeGreaterThanOrEqual(4);
  });
});

describe('seedViolations', () => {
  it('gives nothing for a seed that uploaded what it wrote', () => {
    expect(seedViolations(clean().seed, SEED_BYTES)).toEqual([]);
  });

  it('flags a seed under 98% of the bytes written, and passes exactly 98%', () => {
    const seed = clean().seed;
    seed.bytesUploaded = 0.98 * SEED_BYTES;
    expect(seedViolations(seed, SEED_BYTES)).toEqual([]);
    seed.bytesUploaded = 0.98 * SEED_BYTES - 1;
    expect(seedViolations(seed, SEED_BYTES)).toHaveLength(1);
  });

  it('flags a seed that wrote nothing, so an empty comparison cannot pass', () => {
    expect(seedViolations(clean().seed, 0).length).toBeGreaterThan(0);
  });

  it('feeds the nightly control: a record with an anchor-deleted rehash is a violation', () => {
    const input = clean();
    input.incr = {
      durationMs: 400_000,
      bytesUploaded: CELL,
      chunksUploaded: 1,
      rehashReason: 'anchor-missing',
    };
    expect(largeRepoBudgetViolations(input).length).toBeGreaterThan(0);
  });
});

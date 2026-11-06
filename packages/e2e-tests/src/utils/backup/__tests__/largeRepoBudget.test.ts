import { describe, expect, it } from 'vitest';
import {
  CAP_FLOOR_BYTES,
  GIB,
  INCR_TIME_CAP_MS,
  incrTimeBudgetMs,
  largeRepoBudgetViolations,
  seedFileLimitMs,
  seedFileViolation,
} from '../largeRepoBudget';

describe('incrTimeBudgetMs below the cap floor', () => {
  it('is purely proportional at 2 GiB: a slow seed is not clipped to the cap', () => {
    const seedMs = 10_000_000;
    expect(incrTimeBudgetMs(seedMs, 2 * GIB)).toBe(1_000_000);
    expect(incrTimeBudgetMs(seedMs, 2 * GIB)).toBeGreaterThan(INCR_TIME_CAP_MS);
  });

  it('applies the cap from 20 GiB up', () => {
    expect(CAP_FLOOR_BYTES).toBe(20 * GIB);
    expect(incrTimeBudgetMs(10_000_000, 20 * GIB)).toBe(INCR_TIME_CAP_MS);
    expect(incrTimeBudgetMs(10_000_000, 50 * GIB)).toBe(INCR_TIME_CAP_MS);
    expect(incrTimeBudgetMs(10_000_000, 20 * GIB - 1)).toBe(1_000_000);
  });

  it('keeps the cap when no seed size is given', () => {
    expect(incrTimeBudgetMs(10_000_000)).toBe(INCR_TIME_CAP_MS);
  });
});

describe('per-seed-file time guard', () => {
  it('scales the limit per GiB', () => {
    expect(seedFileLimitMs(2 * GIB)).toBe(2 * seedFileLimitMs(GIB));
  });

  it('is silent within the limit and names the file index past it', () => {
    expect(seedFileViolation(3, 20, GIB, seedFileLimitMs(GIB))).toBeUndefined();
    const v = seedFileViolation(3, 20, GIB, seedFileLimitMs(GIB) + 1);
    expect(v).toContain('seed file 3 of 20');
  });
});

describe('the time-budget violation message', () => {
  const seed = { durationMs: 100_000, bytesUploaded: 100, chunksUploaded: 1 };
  const incr = { durationMs: 50_000, bytesUploaded: 10, chunksUploaded: 1 };
  const input = { seed, incr, changedBytes: 10, cellBytes: 1024 };

  it('names no cap for a seed under 20 GiB', () => {
    const msg = largeRepoBudgetViolations({ ...input, seedBytes: 100 }).find((v) =>
      v.includes('budget')
    );
    expect(msg).toContain('no cap under 20 GiB');
    expect(msg).not.toContain('capped at');
  });

  it('names the cap from 20 GiB up', () => {
    const msg = largeRepoBudgetViolations({ ...input, seedBytes: 20 * GIB }).find((v) =>
      v.includes('budget')
    );
    expect(msg).toContain(`capped at ${INCR_TIME_CAP_MS} ms from 20 GiB`);
  });
});

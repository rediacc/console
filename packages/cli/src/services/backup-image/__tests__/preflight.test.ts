import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  allocatedBytesOf,
  checkSpace,
  computeSpaceNeed,
  FAT_FS_TYPE,
  probeSparse,
  SPACE_MARGIN_MIN,
  spaceMargin,
} from '../preflight.js';

const GiB = 1024 ** 3;
const A = 100 * GiB;
const U = 30 * GiB;
const margin = spaceMargin(A);

describe('computeSpaceNeed (Design 5 table)', () => {
  it('margin is 1 percent of A, at least 256 MiB', () => {
    expect(margin).toBe(Math.ceil(A * 0.01));
    expect(spaceMargin(GiB)).toBe(SPACE_MARGIN_MIN);
  });

  it('fresh sparse needs U', () => {
    expect(computeSpaceNeed({ apparent: A, allocated: U, localExists: false, sparse: true })).toBe(
      U + margin
    );
  });

  it('fresh non-sparse needs A', () => {
    expect(computeSpaceNeed({ apparent: A, allocated: U, localExists: false, sparse: false })).toBe(
      A + margin
    );
  });

  it('existing partial: min(full, A - L)', () => {
    const base = { apparent: A, allocated: U, localExists: true };
    // L = 10 GiB: A - L = 90 GiB, sparse full = 30 GiB -> 30 GiB
    expect(computeSpaceNeed({ ...base, localAllocated: 10 * GiB, sparse: true })).toBe(U + margin);
    // non-sparse: min(100, 90) = 90 GiB
    expect(computeSpaceNeed({ ...base, localAllocated: 10 * GiB, sparse: false })).toBe(
      90 * GiB + margin
    );
  });

  it('existing complete needs only the margin', () => {
    const base = { apparent: A, allocated: U, localExists: true };
    expect(computeSpaceNeed({ ...base, localAllocated: A, sparse: false })).toBe(margin);
    expect(computeSpaceNeed({ ...base, localAllocated: 2 * A, sparse: true })).toBe(margin);
  });
});

describe('checkSpace', () => {
  const fs =
    (bavail: number, type = 0xef53) =>
    async () => ({ type, bsize: 4096, bavail });

  it('passes with room and refuses without', async () => {
    const input = { dir: '/x', apparent: A, allocated: U, localExists: false, sparse: true };
    const exact = await checkSpace(input, { statfs: fs(Math.ceil((U + margin) / 4096)) });
    expect(exact.ok).toBe(true);
    const short = await checkSpace(input, { statfs: fs(Math.floor((U + margin) / 4096) - 1) });
    expect(short.ok).toBe(false);
    const roomy = await checkSpace(input, { statfs: fs(Math.ceil((U + margin + GiB) / 4096)) });
    expect(roomy).toMatchObject({ ok: true, need: U + margin });
    const tight = await checkSpace(input, { statfs: fs(1000) });
    expect(tight).toMatchObject({ ok: false, reason: 'insufficient-space', free: 1000 * 4096 });
  });

  it('refuses FAT with an apparent size of 5 GiB', async () => {
    const r = await checkSpace(
      { dir: '/x', apparent: 5 * GiB, allocated: GiB, localExists: false, sparse: true },
      { statfs: fs(10 ** 9, FAT_FS_TYPE), platform: 'linux' }
    );
    expect(r).toMatchObject({ ok: false, reason: 'fat32-file-limit' });
  });

  it('accepts FAT below the 4 GiB file limit', async () => {
    const r = await checkSpace(
      { dir: '/x', apparent: 3 * GiB, allocated: GiB, localExists: false, sparse: true },
      { statfs: fs(10 ** 9, FAT_FS_TYPE), platform: 'linux' }
    );
    expect(r.ok).toBe(true);
  });
});

describe('probeSparse and allocatedBytesOf', () => {
  it('returns a boolean and leaves no probe file behind', () => {
    const dir = mkdtempSync(join(tmpdir(), 'probe-'));
    try {
      expect(typeof probeSparse(dir)).toBe('boolean');
      expect(readdirSync(dir)).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('answers false instead of throwing when the directory is missing', () => {
    const dir = mkdtempSync(join(tmpdir(), 'probe-'));
    try {
      expect(probeSparse(join(dir, 'absent'))).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('uses blocks * 512, or the size when blocks are unknown', () => {
    expect(allocatedBytesOf({ size: 1000, blocks: 8 })).toBe(4096);
    expect(allocatedBytesOf({ size: 1000 })).toBe(1000);
  });
});

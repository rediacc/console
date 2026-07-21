import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import {
  BLOCK_SIZE,
  type DeltaIndex,
  buildIndex,
  bytesToFetch,
  matchBlocks,
  reconstruct,
  remoteRanges,
  sha256Hex,
} from '../update/delta.js';

/**
 * These tests model the real shape of an rdc release: a large, unchanging
 * embedded payload plus a small head that changes every build. The point is not
 * that reconstruction works on random data, but that it recovers the shared
 * payload locally and downloads only the part that actually changed.
 */

let dir: string;

beforeAll(async () => {
  dir = await fs.mkdtemp(join(tmpdir(), 'rdc-delta-'));
});

afterAll(async () => {
  await fs.rm(dir, { recursive: true, force: true });
});

/**
 * Deterministic filler, independent per seed.
 *
 * NOT an LCG: a linear congruential generator is a bijection over 2^32, so
 * different seeds are just different starting points on ONE cycle. Two "random"
 * regions generated that way are shifted views of the same stream, and the
 * rolling matcher legitimately matches them — which is how the first version of
 * this fixture managed to make the matcher look broken when it was working.
 * Hash chaining gives genuinely unrelated streams while staying reproducible.
 */
function filler(seed: number, len: number): Uint8Array {
  const out = Buffer.alloc(len);
  let written = 0;
  let counter = 0;
  while (written < len) {
    const chunk = createHash('sha256').update(`${seed}:${counter++}`).digest();
    const n = Math.min(chunk.length, len - written);
    chunk.copy(out, written, 0, n);
    written += n;
  }
  return new Uint8Array(out);
}

async function indexOf(name: string, bytes: Uint8Array): Promise<DeltaIndex> {
  const p = join(dir, name);
  await fs.writeFile(p, bytes);
  return buildIndex(p);
}

/** Serve ranges out of the target buffer, counting what was actually fetched. */
function server(target: Uint8Array) {
  let fetched = 0;
  return {
    get fetched() {
      return fetched;
    },
    fetchRange: async (start: number, end: number) => {
      fetched += end - start;
      return target.subarray(start, end);
    },
  };
}

describe('delta updates', () => {
  it('reconstructs a new release byte-for-byte from the previous one', async () => {
    // 40 blocks of shared "embedded payload", with a changed head and tail.
    const payload = filler(1, BLOCK_SIZE * 40);
    const oldBin = new Uint8Array(BLOCK_SIZE * 42);
    oldBin.set(filler(2, BLOCK_SIZE), 0);
    oldBin.set(payload, BLOCK_SIZE);
    oldBin.set(filler(3, BLOCK_SIZE), BLOCK_SIZE * 41);

    const newBin = new Uint8Array(BLOCK_SIZE * 42);
    newBin.set(filler(9, BLOCK_SIZE), 0); // rebuilt code
    newBin.set(payload, BLOCK_SIZE); // unchanged payload
    newBin.set(filler(8, BLOCK_SIZE), BLOCK_SIZE * 41);

    const index = await indexOf('new-1', newBin);
    const sources = matchBlocks(index, oldBin);
    const srv = server(newBin);
    const got = await reconstruct(index, oldBin, sources, srv.fetchRange);

    expect(sha256Hex(got)).toBe(index.sha256);
    expect(Buffer.from(got).equals(Buffer.from(newBin))).toBe(true);

    // The 40 shared blocks must have come from disk, not the network.
    const local = sources.filter((s) => s.kind === 'local').length;
    expect(local).toBe(40);
    expect(srv.fetched).toBe(BLOCK_SIZE * 2);
  });

  it('still matches shared payload when it shifts to a different offset', async () => {
    // The rolling checksum exists precisely so an insertion does not defeat
    // matching by pushing every subsequent block out of alignment.
    const payload = filler(5, BLOCK_SIZE * 20);
    const oldBin = new Uint8Array(BLOCK_SIZE * 21);
    oldBin.set(payload, BLOCK_SIZE);

    const shift = 1234; // not a block multiple
    const newBin = new Uint8Array(shift + payload.length);
    newBin.set(filler(7, shift), 0);
    newBin.set(payload, shift);

    const index = await indexOf('new-2', newBin);
    const sources = matchBlocks(index, oldBin);
    const got = await reconstruct(index, oldBin, sources, server(newBin).fetchRange);

    expect(sha256Hex(got)).toBe(index.sha256);
    expect(sources.some((s) => s.kind === 'local')).toBe(true);
  });

  it('falls back to fetching everything when nothing matches', async () => {
    const oldBin = filler(11, BLOCK_SIZE * 4);
    const newBin = filler(22, BLOCK_SIZE * 4);

    const index = await indexOf('new-3', newBin);
    const sources = matchBlocks(index, oldBin);
    const srv = server(newBin);
    const got = await reconstruct(index, oldBin, sources, srv.fetchRange);

    expect(sha256Hex(got)).toBe(index.sha256);
    expect(sources.every((s) => s.kind === 'remote')).toBe(true);
    expect(srv.fetched).toBe(newBin.length);
  });

  it('handles a trailing partial block', async () => {
    const tail = 777;
    const payload = filler(31, BLOCK_SIZE * 3);
    const oldBin = new Uint8Array(BLOCK_SIZE * 3 + tail);
    oldBin.set(payload, 0);
    oldBin.set(filler(32, tail), BLOCK_SIZE * 3);

    const newBin = new Uint8Array(BLOCK_SIZE * 3 + tail);
    newBin.set(payload, 0);
    newBin.set(filler(32, tail), BLOCK_SIZE * 3);

    const index = await indexOf('new-4', newBin);
    expect(index.totalSize % BLOCK_SIZE).not.toBe(0);

    const sources = matchBlocks(index, oldBin);
    const srv = server(newBin);
    const got = await reconstruct(index, oldBin, sources, srv.fetchRange);

    expect(sha256Hex(got)).toBe(index.sha256);
    // Identical files must need no network at all, tail included.
    expect(srv.fetched).toBe(0);
  });

  it('rejects a short range rather than assembling a corrupt file', async () => {
    const oldBin = filler(41, BLOCK_SIZE * 2);
    const newBin = filler(42, BLOCK_SIZE * 2);
    const index = await indexOf('new-5', newBin);
    const sources = matchBlocks(index, oldBin);

    await expect(
      reconstruct(index, oldBin, sources, async (start, end) => newBin.subarray(start, end - 1))
    ).rejects.toThrow(/expected/);
  });

  it('stays fast on large repeated-byte runs (zero-padding pathology)', async () => {
    // Real binaries carry large zero-padded regions. Every offset inside such
    // a run produces the SAME weak checksum, which used to make the matcher
    // (a) re-walk the full duplicate-candidate list at every one of millions
    // of offsets, and (b) — in the trailing-block scan, which ignored the
    // stored weak checksum entirely — compute a tail-sized sha256 at EVERY
    // byte offset of the local file. On an input this size that took minutes
    // (a release-sized local projected to hours); the fix must finish in
    // well under a second.
    const zeroBlocks = 64;
    const payload = filler(61, BLOCK_SIZE * 4);
    const tail = filler(62, 50_000);

    const newBin = new Uint8Array(BLOCK_SIZE * (zeroBlocks + 4) + tail.length);
    newBin.set(payload, BLOCK_SIZE * zeroBlocks);
    newBin.set(tail, BLOCK_SIZE * (zeroBlocks + 4));

    const zeroRun = BLOCK_SIZE * 128; // 8 MiB zero run in the local file
    const oldBin = new Uint8Array(zeroRun + payload.length + tail.length);
    oldBin.set(payload, zeroRun);
    oldBin.set(tail, zeroRun + payload.length); // tail at the END: worst case for a brute-force tail scan

    const index = await indexOf('new-7', newBin);
    const t0 = performance.now();
    const sources = matchBlocks(index, oldBin);
    const elapsed = performance.now() - t0;

    // Everything — zero blocks, payload, and the short tail — exists locally.
    expect(sources.every((s) => s.kind === 'local')).toBe(true);
    const srv = server(newBin);
    const got = await reconstruct(index, oldBin, sources, srv.fetchRange);
    expect(sha256Hex(got)).toBe(index.sha256);
    expect(srv.fetched).toBe(0);

    // Generous bound (CI headroom): the fix takes ~0.1s here, the pathological
    // version took minutes.
    expect(elapsed).toBeLessThan(10_000);
  }, 30_000);

  it('coalesces adjacent missing blocks into one range', async () => {
    const newBin = filler(51, BLOCK_SIZE * 6);
    const index = await indexOf('new-6', newBin);
    const sources = matchBlocks(index, new Uint8Array(0));
    const ranges = remoteRanges(index, sources);

    expect(ranges).toHaveLength(1);
    expect(ranges[0]).toEqual({ start: 0, end: newBin.length });
    expect(bytesToFetch(ranges)).toBe(newBin.length);
  });
});

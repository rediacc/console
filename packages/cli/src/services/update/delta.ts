/**
 * Range-based delta updates for the rdc self-executable.
 *
 * WHY: every update is a full re-download of a ~500MB single-file executable,
 * and the edge channel releases on every merge to main. Almost all of that
 * payload is the embedded third-party binaries (k3s, zot, the CSI sidecars,
 * rclone, criu, rsync), which change on the order of once a month, while the Go
 * and JavaScript code changes every merge. So the bytes that actually differ
 * between two consecutive releases are a small fraction of the file.
 *
 * WHY THIS SHAPE, and not `zstd --patch-from`: a patch is per (from, to) pair.
 * On a channel that releases per merge that matrix explodes, and anyone on an
 * older version is stranded with no patch path. A block index is ONE artifact
 * per release and lets a client at ANY prior version reconstruct, because the
 * matching is done against whatever bytes it happens to have locally.
 *
 * The algorithm is rsync's: the index carries a weak rolling checksum and a
 * strong hash per fixed-size block of the NEW file. The client slides a window
 * over its CURRENT binary, cheaply rejects non-matches with the rolling
 * checksum, confirms survivors with the strong hash, and downloads only the
 * blocks it could not find locally.
 *
 * PREREQUISITE: the embedded payloads must be byte-reproducible, which is why
 * they are compressed with zstd (no embedded timestamp). Under gzip, two builds
 * of a byte-identical binary differed in the MTIME header field, so no block
 * would ever have matched and every delta would have degenerated to a full
 * download.
 *
 * SAFETY: reconstruction is never trusted on its own. The caller verifies the
 * assembled file against the sha256 already published in the release manifest,
 * exactly as it does for a full download, and falls back to a full download on
 * any mismatch.
 */

import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';

/** Fixed block size. 64 KiB over a ~500MB target is ~8k blocks, a ~400KB index. */
export const BLOCK_SIZE = 64 * 1024;

/** Modulus for the rolling checksum halves (rsync uses 2^16). */
const M = 65536;

/** Layout version of the published index. Bumped only on a breaking change. */
export const DELTA_FORMAT_VERSION = 1;

/** Per block, in order: [weak rolling checksum, strong hash prefix (hex)]. */
type DeltaBlock = [number, string];

export interface DeltaIndex {
  /**
   * Layout version. Deliberately typed `number` rather than the literal: an
   * index reaches a client by being parsed from the network, so its value is
   * whatever the server sent. Typing it as the literal would make the client's
   * version check look like a tautology to the compiler and invite deleting the
   * one guard that keeps a future format out of an old client.
   */
  formatVersion: number;
  blockSize: number;
  totalSize: number;
  /** sha256 of the complete target file, for the caller's final verification. */
  sha256: string;
  /** Per block, in order: [weak rolling checksum, strong hash prefix (hex)]. */
  blocks: DeltaBlock[];
}

/** Strong hash of a block: a sha256 prefix. Weak+strong collisions are then
 *  negligible, and the whole-file sha256 remains the actual guarantee. */
function strongHash(buf: Uint8Array): string {
  return createHash('sha256').update(buf).digest('hex').slice(0, 16);
}

/** rsync's weak rolling checksum over a buffer slice. */
function weakChecksum(buf: Uint8Array, start: number, end: number): number {
  let a = 0;
  let b = 0;
  for (let i = start; i < end; i++) {
    a += buf[i];
    b += (end - i) * buf[i];
  }
  return (a % M) + M * (b % M);
}

/**
 * Build the index for a target file. Run at release time, published beside the
 * binary.
 */
export async function buildIndex(filePath: string): Promise<DeltaIndex> {
  const data = await fs.readFile(filePath);
  const blocks: DeltaBlock[] = [];
  for (let off = 0; off < data.length; off += BLOCK_SIZE) {
    const end = Math.min(off + BLOCK_SIZE, data.length);
    blocks.push([weakChecksum(data, off, end), strongHash(data.subarray(off, end))]);
  }
  return {
    formatVersion: DELTA_FORMAT_VERSION,
    blockSize: BLOCK_SIZE,
    totalSize: data.length,
    sha256: createHash('sha256').update(data).digest('hex'),
    blocks,
  };
}

/** Where a given target block's bytes can be taken from. */
type BlockSource = { kind: 'local'; offset: number } | { kind: 'remote' };

/**
 * State shared by the steps of one matchBlocks run.
 *
 * It exists so the scan can be split into named steps without threading a dozen
 * positional arguments through each of them. Nothing here is read per byte
 * offset: the rolling loop lifts what it needs into locals first, because a
 * property load repeated ~600 million times is not free.
 */
interface ScanContext {
  local: Uint8Array;
  blocks: DeltaBlock[];
  sources: BlockSource[];
  blockSize: number;
  totalSize: number;
  /**
   * weak checksum -> UNRESOLVED target block indices sharing it. Entries are
   * pruned as blocks resolve — that pruning is load-bearing, see pruneResolved.
   */
  byWeak: Map<number, number[]>;
  /**
   * Fast reject table over the LOW half of the weak checksum (which is a % M).
   *
   * This is load-bearing for performance, not a micro-optimisation. The scan
   * visits every byte offset of the local binary — ~600 million of them for a
   * release-sized file — and a Map lookup at each one does not finish in any
   * reasonable time (measured: still running after 10 minutes). A single typed
   * array read rejects virtually every offset before the Map is ever consulted.
   */
  seen: Uint8Array;
  /**
   * How many live byWeak entries share each low half, so `seen` can be cleared
   * as entries are pruned and a repeated-content run stops paying even the Map
   * lookup once its blocks are resolved.
   */
  lowRefs: Uint32Array;
  /**
   * Strong hash of a uniform window (one byte value repeated across the whole
   * window), keyed by that byte. WHY: a large zero-padded (or any
   * repeated-byte) region makes every offset inside it produce the same weak
   * checksum. If that weak collides with an unresolved target block, the naive
   * path computes a 64KiB sha256 at EVERY offset of the run — millions of
   * hashes, tens of GB hashed. The memo reduces that to one hash per distinct
   * byte value.
   */
  uniformStrong: Map<number, string>;
}

/** Index the full-size target blocks by weak checksum, with the reject tables. */
function buildWeakTables(
  blocks: DeltaBlock[],
  fullBlockCount: number
): Pick<ScanContext, 'byWeak' | 'seen' | 'lowRefs'> {
  const byWeak = new Map<number, number[]>();
  const seen = new Uint8Array(M);
  const lowRefs = new Uint32Array(M);
  for (let i = 0; i < fullBlockCount; i++) {
    const w = blocks[i][0];
    const list = byWeak.get(w);
    if (list) {
      list.push(i);
      continue;
    }
    byWeak.set(w, [i]);
    const low = w % M;
    seen[low] = 1;
    lowRefs[low]++;
  }
  return { byWeak, seen, lowRefs };
}

/** A rolling window's two sums, plus its trailing run of identical bytes. */
interface RollingWindow {
  a: number;
  b: number;
  /**
   * Length of the run of identical bytes ending at the window's LAST byte. When
   * it reaches the window length the window is one repeated byte, which is what
   * makes the uniform-window memos usable (see ScanContext.uniformStrong).
   */
  runLen: number;
}

/**
 * Compute the window sums from scratch at `start`. Needed at the top of a scan
 * and after each block-sized skip, where rolling by one byte is not possible.
 */
function primeWindow(local: Uint8Array, start: number, len: number): RollingWindow {
  let a = 0;
  let b = 0;
  for (let i = 0; i < len; i++) {
    const v = local[start + i];
    a += v;
    b += (len - i) * v;
  }
  const last = start + len - 1;
  let runLen = 1;
  while (runLen < len && local[last - runLen] === local[last]) runLen++;
  return { a, b, runLen };
}

/**
 * Prune resolved blocks out of a candidate list. Without this, a run of
 * repeated content (every offset hitting the same weak) re-walks a candidate
 * list of already-resolved duplicates at each of millions of offsets:
 * O(run length × duplicate count).
 */
function pruneResolved(ctx: ScanContext, candidates: number[], weak: number, low: number): void {
  const rest = candidates.filter((bi) => ctx.sources[bi].kind !== 'local');
  if (rest.length === 0) {
    ctx.byWeak.delete(weak);
    if (--ctx.lowRefs[low] === 0) ctx.seen[low] = 0;
  } else {
    ctx.byWeak.set(weak, rest);
  }
}

/**
 * Settle a window that survived the `seen` fast reject: look up its full weak
 * checksum and, on a hit, confirm the candidates with the strong hash. Returns
 * how many target blocks this offset newly resolved — usually 0, since the low
 * half alone is a coarse filter.
 */
function confirmAtWindow(
  ctx: ScanContext,
  off: number,
  low: number,
  b: number,
  uniform: boolean
): number {
  const weak = low + M * (b & (M - 1));
  const candidates = ctx.byWeak.get(weak);
  if (!candidates) return 0;

  const { local, blocks, sources, blockSize, uniformStrong } = ctx;
  let strong = uniform ? uniformStrong.get(local[off]) : undefined;
  if (strong === undefined) {
    strong = strongHash(local.subarray(off, off + blockSize));
    if (uniform) uniformStrong.set(local[off], strong);
  }

  let hits = 0;
  for (const bi of candidates) {
    if (strong === blocks[bi][1]) {
      sources[bi] = { kind: 'local', offset: off };
      hits++;
    }
  }
  if (hits > 0) pruneResolved(ctx, candidates, weak, low);
  return hits;
}

/**
 * Roll a blockSize window forward from `start` until it lands on a confirmed
 * match. Returns that offset and how many blocks it resolved, or `hits: 0` once
 * the local buffer is exhausted.
 *
 * This is the hot loop — it runs once per byte of the local binary — so the
 * tables it consults are lifted into locals and every offset is rejected by a
 * single typed-array read before anything more expensive is reached.
 */
function rollToNextMatch(ctx: ScanContext, start: number): { off: number; hits: number } {
  const { local, blockSize, seen } = ctx;
  const lastOff = local.length - blockSize;
  let { a, b, runLen } = primeWindow(local, start, blockSize);
  let off = start;
  for (;;) {
    // a and b are the true sums for the window at `off`; both stay
    // non-negative by construction and well inside the exact-integer range
    // of a double. M is 2^16, so `& (M - 1)` is `% M` on these values.
    const low = a & (M - 1);
    const hits = seen[low] === 0 ? 0 : confirmAtWindow(ctx, off, low, b, runLen >= blockSize);
    if (hits > 0) return { off, hits };
    if (off === lastOff) return { off, hits: 0 };
    // Roll the window forward by one byte.
    const out = local[off];
    const inc = local[off + blockSize];
    a = a - out + inc;
    b = b - blockSize * out + a;
    runLen = inc === local[off + blockSize - 1] ? runLen + 1 : 1;
    off++;
  }
}

/**
 * Rolling scan over the full-size blocks.
 *
 * After every confirmed match the next window starts blockSize bytes later —
 * rsync's skip: those bytes are consumed by the match. Besides skipping
 * blockSize-1 pointless offsets per match, this is what makes a scan of an
 * identical file linear in blocks rather than bytes hashed. Windows overlapping
 * the consumed bytes could in principle match some OTHER block, but rsync
 * accepts that trade and so do we: unmatched blocks are simply fetched.
 */
function scanFullBlocks(ctx: ScanContext, fullBlockCount: number): void {
  const { local, blockSize } = ctx;
  let off = 0;
  let resolved = 0;
  while (resolved < fullBlockCount && off + blockSize <= local.length) {
    const hit = rollToNextMatch(ctx, off);
    if (hit.hits === 0) return;
    resolved += hit.hits;
    off = hit.off + blockSize;
  }
}

/** Everything the tail scan needs about the one block it is hunting for. */
interface TailTarget {
  local: Uint8Array;
  tailLen: number;
  weak: number;
  strong: string;
  /**
   * Same repeated-byte guard as the main scan: inside a uniform run every
   * offset repeats the identical window, so remember per byte value whether
   * that window already failed the strong check.
   */
  uniformMiss: Uint8Array;
}

/** Does the tail-length window at `off` hold the tail block's exact bytes? */
function tailHit(t: TailTarget, off: number, a: number, b: number, runLen: number): boolean {
  if ((a & (M - 1)) + M * (b & (M - 1)) !== t.weak) return false;
  const { local, tailLen, uniformMiss } = t;
  const uniform = runLen >= tailLen;
  if (uniform && uniformMiss[local[off]] !== 0) return false;
  if (strongHash(local.subarray(off, off + tailLen)) === t.strong) return true;
  if (uniform) uniformMiss[local[off]] = 1;
  return false;
}

/**
 * The trailing short block. It needs its own scan because a rolling window
 * of a different length has an unrelated checksum — but the index DOES store
 * the tail's weak checksum (buildIndex computes it at the tail's length), so
 * the same weak-first rolling rejection applies here. The first version of
 * this loop went straight to the strong hash at every offset: a ~60KB sha256
 * per byte of the local file, ~25 minutes for a 50MB local (measured), which
 * is what made matchBlocks appear to hang.
 */
function matchTailBlock(ctx: ScanContext, fullBlockCount: number): void {
  const { local, blocks, sources, blockSize, totalSize } = ctx;
  const tailLen = totalSize - fullBlockCount * blockSize;
  if (tailLen === 0 || local.length < tailLen) return;

  const ti = blocks.length - 1;
  const target: TailTarget = {
    local,
    tailLen,
    weak: blocks[ti][0],
    strong: blocks[ti][1],
    uniformMiss: new Uint8Array(256),
  };

  let { a, b, runLen } = primeWindow(local, 0, tailLen);
  let off = 0;
  for (;;) {
    if (tailHit(target, off, a, b, runLen)) {
      sources[ti] = { kind: 'local', offset: off };
      return;
    }
    off++;
    if (off + tailLen > local.length) return;
    // Roll the tail-length window forward by one byte.
    const out = local[off - 1];
    const inc = local[off + tailLen - 1];
    a = a - out + inc;
    b = b - tailLen * out + a;
    runLen = inc === local[off + tailLen - 2] ? runLen + 1 : 1;
  }
}

/**
 * Find, for each block of the target, an offset in `local` holding those exact
 * bytes. Blocks with no local match must be fetched.
 *
 * Only FULL-SIZE blocks are matched by rolling scan. The final short block (if
 * the file is not a whole multiple of blockSize) is matched separately, because
 * a rolling window of a different length has an unrelated checksum.
 */
export function matchBlocks(index: DeltaIndex, local: Uint8Array): BlockSource[] {
  const { blockSize, blocks, totalSize } = index;
  const fullBlockCount = Math.floor(totalSize / blockSize);
  const sources: BlockSource[] = blocks.map(() => ({ kind: 'remote' }));
  const ctx: ScanContext = {
    local,
    blocks,
    sources,
    blockSize,
    totalSize,
    uniformStrong: new Map<number, string>(),
    ...buildWeakTables(blocks, fullBlockCount),
  };

  scanFullBlocks(ctx, fullBlockCount);
  matchTailBlock(ctx, fullBlockCount);

  return sources;
}

/** A contiguous run of target bytes that must be fetched. */
export interface RemoteRange {
  start: number;
  end: number;
}

/** Coalesce the remote blocks into as few byte ranges as possible. */
export function remoteRanges(index: DeltaIndex, sources: BlockSource[]): RemoteRange[] {
  const { blockSize, totalSize } = index;
  const ranges: RemoteRange[] = [];
  for (let i = 0; i < sources.length; i++) {
    if (sources[i].kind !== 'remote') continue;
    const start = i * blockSize;
    let j = i;
    while (j + 1 < sources.length && sources[j + 1].kind === 'remote') j++;
    ranges.push({ start, end: Math.min((j + 1) * blockSize, totalSize) });
    i = j;
  }
  return ranges;
}

/** Bytes that would have to be downloaded for this plan. */
export function bytesToFetch(ranges: RemoteRange[]): number {
  return ranges.reduce((n, r) => n + (r.end - r.start), 0);
}

/**
 * Assemble the target from locally matched blocks plus fetched ranges.
 *
 * `fetchRange` is injected so this is testable offline and so the caller owns
 * transport policy (timeouts, retries, and the 206-vs-200 check).
 */
export async function reconstruct(
  index: DeltaIndex,
  local: Uint8Array,
  sources: BlockSource[],
  fetchRange: (start: number, end: number) => Promise<Uint8Array>
): Promise<Uint8Array> {
  const out = new Uint8Array(index.totalSize);

  for (let i = 0; i < sources.length; i++) {
    const src = sources[i];
    if (src.kind !== 'local') continue;
    const start = i * index.blockSize;
    const len = Math.min(index.blockSize, index.totalSize - start);
    out.set(local.subarray(src.offset, src.offset + len), start);
  }

  for (const r of remoteRanges(index, sources)) {
    const bytes = await fetchRange(r.start, r.end);
    if (bytes.length !== r.end - r.start) {
      throw new Error(
        `delta: range ${r.start}-${r.end} returned ${bytes.length} bytes, expected ${r.end - r.start}`
      );
    }
    out.set(bytes, r.start);
  }

  return out;
}

/** sha256 of a buffer, hex. */
export function sha256Hex(buf: Uint8Array): string {
  return createHash('sha256').update(buf).digest('hex');
}

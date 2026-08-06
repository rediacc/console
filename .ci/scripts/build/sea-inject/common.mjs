/**
 * Shared primitives for the SEA injectors (see index.mjs for the why).
 *
 * The single most important thing in this file is streamBlob(): every format
 * backend copies the blob through it, so "never buffer the blob" is enforced in
 * one place instead of being re-implemented (and eventually got wrong) three
 * times.
 */
import fs from 'node:fs';
import { Buffer } from 'node:buffer';

/** Blob copy granularity. Peak RSS is a small constant multiple of this. */
export const COPY_CHUNK = 8 * 1024 * 1024;

export function alignUp(value, alignment) {
  if (alignment <= 1) return value;
  const rem = value % alignment;
  return rem === 0 ? value : value + (alignment - rem);
}

export function readAt(fd, length, position) {
  const buf = Buffer.alloc(length);
  let done = 0;
  while (done < length) {
    const got = fs.readSync(fd, buf, done, length - done, position + done);
    if (got <= 0) throw new Error(`short read at offset ${position + done}`);
    done += got;
  }
  return buf;
}

export function writeAll(fd, buf, position) {
  let done = 0;
  while (done < buf.length) {
    done += fs.writeSync(fd, buf, done, buf.length - done, position + done);
  }
}

export function writeZeros(fd, length, position) {
  if (length <= 0) return;
  const zeros = Buffer.alloc(Math.min(length, COPY_CHUNK));
  let done = 0;
  while (done < length) {
    const n = Math.min(zeros.length, length - done);
    writeAll(fd, zeros.subarray(0, n), position + done);
    done += n;
  }
}

/**
 * Copy `length` bytes from srcPath into fd at dstOffset, in fixed-size chunks.
 *
 * This is the whole reason this tooling exists. postject reads the blob into a
 * single wasm32 heap allocation and amplifies it ~11.6x, which is why a ~561MB
 * blob is unreachable for it. Do not "simplify" this to readFileSync.
 */
export function streamBlob(fd, srcPath, dstOffset, length) {
  const srcFd = fs.openSync(srcPath, 'r');
  try {
    const buf = Buffer.allocUnsafe(COPY_CHUNK);
    let src = 0;
    while (src < length) {
      const want = Math.min(COPY_CHUNK, length - src);
      const got = fs.readSync(srcFd, buf, 0, want, src);
      if (got <= 0) throw new Error(`short read from ${srcPath} at ${src}`);
      writeAll(fd, buf.subarray(0, got), dstOffset + src);
      src += got;
    }
  } finally {
    fs.closeSync(srcFd);
  }
}

/**
 * Copy `length` bytes from one offset to another *within the same file*,
 * chunked. Used by the Mach-O backend to slide __LINKEDIT, which is tens of MB.
 * Copies back-to-front when the ranges overlap and the destination is higher,
 * so an overlapping move does not eat its own tail.
 */
export function moveRange(fd, srcOffset, dstOffset, length) {
  if (length <= 0 || srcOffset === dstOffset) return;
  const buf = Buffer.allocUnsafe(COPY_CHUNK);
  const overlaps = dstOffset > srcOffset && dstOffset < srcOffset + length;
  if (overlaps) {
    let done = 0;
    while (done < length) {
      const n = Math.min(COPY_CHUNK, length - done);
      const from = srcOffset + length - done - n;
      let got = 0;
      while (got < n) {
        const r = fs.readSync(fd, buf, got, n - got, from + got);
        if (r <= 0) throw new Error(`short read at ${from + got}`);
        got += r;
      }
      writeAll(fd, buf.subarray(0, n), dstOffset + length - done - n);
      done += n;
    }
    return;
  }
  let done = 0;
  while (done < length) {
    const n = Math.min(COPY_CHUNK, length - done);
    let got = 0;
    while (got < n) {
      const r = fs.readSync(fd, buf, got, n - got, srcOffset + done + got);
      if (r <= 0) throw new Error(`short read at ${srcOffset + done + got}`);
      got += r;
    }
    writeAll(fd, buf.subarray(0, n), dstOffset + done);
    done += n;
  }
}

/**
 * Locate the `0` byte of the `<fuse>:0` sentinel that node compiles in, scanning
 * in overlapping chunks so a sentinel straddling a chunk boundary is still
 * found. Requires exactly one match: zero means the binary is not SEA-capable
 * or has already been injected, more than one means we cannot tell which is the
 * real fuse.
 *
 * Callers must run this BEFORE mutating anything, so a bad input leaves the
 * binary byte-identical instead of half-injected. Note that a fuse flipped to
 * `1` with no findable resource does not error at runtime — it segfaults — so
 * "fail before writing" is the only safe ordering.
 */
export function findSentinelFuse(fd, searchLimit, fuse) {
  const needle = Buffer.from(`${fuse}:0`, 'latin1');
  const overlap = needle.length - 1;
  const buf = Buffer.alloc(COPY_CHUNK + overlap);
  const hits = [];
  let pos = 0;
  while (pos < searchLimit) {
    const want = Math.min(buf.length, searchLimit - pos);
    const got = fs.readSync(fd, buf, 0, want, pos);
    if (got <= 0) break;
    const window = buf.subarray(0, got);
    let from = 0;
    for (;;) {
      const idx = window.indexOf(needle, from);
      if (idx < 0) break;
      hits.push(pos + idx);
      from = idx + 1;
    }
    pos += COPY_CHUNK;
  }
  if (hits.length === 0) {
    throw new Error(
      `sentinel fuse ${fuse}:0 not found (not a SEA-capable node, or already injected)`
    );
  }
  if (hits.length > 1) {
    throw new Error(
      `sentinel fuse ${fuse}:0 found ${hits.length} times; cannot tell which is the real fuse`
    );
  }
  return hits[0] + needle.length - 1;
}

/**
 * Durable file-write primitives of the repo image state: a fsynced 0600 temp file, an exclusive
 * publish that works with or without hard links, and a directory fsync. Used by the state file and
 * by the lock file in `state.ts`.
 */

import { closeSync, fsyncSync, linkSync, openSync, unlinkSync, writeSync } from 'node:fs';

export function fsyncDir(dir: string): void {
  try {
    const fd = openSync(dir, 'r');
    try {
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
  } catch {
    // Directory fsync is unsupported on some platforms (Windows); the rename already happened.
  }
}

export interface WriteHooks {
  /** Test seam: runs after the temp file is durable and before the rename. */
  beforeRename?: () => void;
}

/**
 * Writes all of `body` to `fd`. writeSync may write fewer bytes than asked (a full disk mid-write);
 * the rest is written in further calls, and a call that writes nothing throws instead of looping.
 */
export function writeFully(
  fd: number,
  body: string,
  write: (fd: number, buf: Buffer, offset: number, length: number) => number = writeSync
): void {
  const buf = Buffer.from(body, 'utf8');
  let offset = 0;
  while (offset < buf.length) {
    const n = write(fd, buf, offset, buf.length - offset);
    if (n <= 0) throw new Error(`short write: ${offset} of ${buf.length} bytes written`);
    offset += n;
  }
}

export function unlinkQuietly(path: string): void {
  try {
    unlinkSync(path);
  } catch {
    // Already gone.
  }
}

/** Errors a filesystem without hard links (exFAT, FAT32, some network mounts) answers `link()` with. */
const NO_HARDLINK_CODES = new Set(['EPERM', 'ENOTSUP', 'EOPNOTSUPP', 'ENOSYS']);

/**
 * Publishes `body` at `dest` exclusively: a hard link of the durable temp file when the filesystem
 * has hard links, else an O_EXCL create of `dest` written in place. Both refuse with EEXIST when
 * `dest` exists. The fallback can show `dest` briefly empty, which `readLock` reads as an unreadable
 * lock and refuses, never as a free one. A crash inside that window leaves the empty file behind,
 * which `clearDeadHolder` takes over once it is older than `UNREADABLE_LOCK_GRACE_MS`.
 */
export function publishExclusive(tmp: string, dest: string, body: string): void {
  try {
    linkSync(tmp, dest);
    return;
  } catch (error) {
    if (!NO_HARDLINK_CODES.has((error as NodeJS.ErrnoException).code ?? '')) throw error;
  }
  writeDurableTemp(dest, body);
}

/** Writes `body` to a new 0600 file, fsynced; the file is removed again when any step fails. */
export function writeDurableTemp(tmp: string, body: string): void {
  const fd = openSync(tmp, 'wx', 0o600);
  try {
    try {
      writeFully(fd, body);
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
  } catch (error) {
    unlinkQuietly(tmp);
    throw error;
  }
}

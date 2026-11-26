import { lstatSync, readdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { getTempPath } from './platform.js';

/** A temp key, known_hosts or launch script this old belongs to no live session. */
export const STALE_TEMP_MAX_AGE_MS = 12 * 60 * 60 * 1000;

/** The names this tool gives its temp files (tempFiles.ts: prefix, 16 hex digits, extension). */
const OWN_TEMP_NAMES: readonly RegExp[] = [
  /^ssh-key-[0-9a-f]{16}\.pem$/,
  /^known_hosts-[0-9a-f]{16}$/,
  /^rdc-term-[0-9a-f]{16}\.cmd$/,
];

/** Whether `path` is a regular file of this user's whose mtime is past the age limit. */
function isStaleOwnFile(path: string, now: number): boolean {
  const stat = lstatSync(path);
  const uid = process.getuid?.();
  const mine = uid === undefined || stat.uid === uid;
  return stat.isFile() && mine && now - stat.mtimeMs >= STALE_TEMP_MAX_AGE_MS;
}

/**
 * Deletes this tool's own ssh-key-*.pem, known_hosts-* and rdc-term-*.cmd
 * files older than `STALE_TEMP_MAX_AGE_MS` from the temp directory. Closing an
 * external terminal's window ends cmd before its cleanup line runs, and the
 * parent has already released the files, so this sweep is what collects them.
 * Only regular files owned by the current user are touched; any error is
 * ignored. Returns the paths removed.
 */
export function sweepStaleTermTempFiles(dir = getTempPath(), now = Date.now()): string[] {
  const removed: string[] = [];
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch {
    return removed;
  }
  for (const name of names.filter((n) => OWN_TEMP_NAMES.some((pattern) => pattern.test(n)))) {
    const path = join(dir, name);
    try {
      if (!isStaleOwnFile(path, now)) continue;
      rmSync(path, { force: true });
      removed.push(path);
    } catch {
      // Gone already or not ours to remove.
    }
  }
  return removed;
}

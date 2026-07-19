/**
 * A cross-process advisory lock, held as a directory containing a `pid` file.
 *
 * `mkdir` is the atomic primitive: it either creates or fails with EEXIST, with
 * no read-then-write window. The `pid` file is what makes the lock recoverable:
 * a process that dies without releasing leaves a directory nobody would ever be
 * able to remove otherwise, so a holder whose pid is gone is treated as stale and
 * reclaimed.
 *
 * Deliberately dependency-free (node builtins only). Callers translate
 * `LockTimeoutError` into whatever user-facing error class they use; importing
 * the CLI's error types here would invert the layering.
 */

import * as fs from 'node:fs/promises';
import * as path from 'node:path';

const isLockAlreadyHeldError = (e: unknown): e is NodeJS.ErrnoException =>
  e instanceof Error && 'code' in e && e.code === 'EEXIST';

/** Whatever could be learned about the process currently holding a lock. */
export interface LockHolder {
  /** The holder's pid, or null when the `pid` file is missing or unreadable. */
  pid: number | null;
  /** How long the lock has been held, from the lock directory's mtime. */
  heldForMs: number | null;
  /** The holder's command line (Linux `/proc` only), best-effort. */
  command: string | null;
}

export interface AcquireLockOptions {
  /** Absolute epoch ms after which acquisition gives up. */
  deadline: number;
  pollMs: number;
  /**
   * Called at most ONCE, the first time a live holder blocks acquisition.
   *
   * Exists so a caller can tell the user WHY nothing is happening. Without it,
   * contention is indistinguishable from a hang: the operator watches a spinner
   * with no clue another process is ahead of them.
   */
  onWait?: (holder: LockHolder) => void;
}

/** Acquisition gave up because another live process still holds the lock. */
export class LockTimeoutError extends Error {
  constructor(
    readonly lockPath: string,
    readonly holder: LockHolder
  ) {
    super(`Timed out waiting for lock: ${lockPath}`);
    this.name = 'LockTimeoutError';
  }
}

const MAX_COMMAND_CHARS = 120;

async function readHolderPid(pidPath: string): Promise<number | null> {
  try {
    const pid = Number.parseInt((await fs.readFile(pidPath, 'utf-8')).trim(), 10);
    return Number.isNaN(pid) ? null : pid;
  } catch {
    return null;
  }
}

function isPidAlive(pid: number): boolean {
  try {
    // Signal 0 checks for existence without delivering anything.
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/**
 * Describe the lock's current holder. Every field is independently best-effort:
 * diagnostics must never be the reason acquiring a lock fails.
 */
export async function readLockHolder(lockPath: string): Promise<LockHolder> {
  const pid = await readHolderPid(path.join(lockPath, 'pid'));

  let heldForMs: number | null = null;
  try {
    heldForMs = Math.max(0, Date.now() - (await fs.stat(lockPath)).mtimeMs);
  } catch {
    /* lock released underneath us */
  }

  let command: string | null = null;
  if (pid !== null) {
    try {
      const raw = await fs.readFile(`/proc/${pid}/cmdline`, 'utf-8');
      const joined = raw.replaceAll('\0', ' ').trim();
      if (joined) {
        command =
          joined.length > MAX_COMMAND_CHARS ? `${joined.slice(0, MAX_COMMAND_CHARS)}…` : joined;
      }
    } catch {
      /* not Linux, or the process is gone, or /proc is restricted */
    }
  }

  return { pid, heldForMs, command };
}

async function tryCreateLock(lockPath: string): Promise<boolean> {
  try {
    await fs.mkdir(lockPath);
    await fs.writeFile(path.join(lockPath, 'pid'), String(process.pid));
    return true;
  } catch (error) {
    if (!isLockAlreadyHeldError(error)) throw error;
    return false;
  }
}

/**
 * Drop the lock directory when its holder is gone, so a process that died
 * mid-run does not block every future one. Returns whether it reclaimed.
 */
async function reclaimIfStale(lockPath: string): Promise<boolean> {
  const pid = await readHolderPid(path.join(lockPath, 'pid'));
  if (pid !== null && isPidAlive(pid)) return false;
  await fs.rm(lockPath, { recursive: true, force: true });
  return true;
}

/** Report the holder to the caller, never letting a bad callback break the lock. */
async function notifyWait(lockPath: string, onWait: (holder: LockHolder) => void): Promise<void> {
  try {
    onWait(await readLockHolder(lockPath));
  } catch {
    // A broken progress renderer must not break lock acquisition.
  }
}

export async function acquireLocalLock(
  lockPath: string,
  options: AcquireLockOptions
): Promise<void> {
  const { deadline, pollMs, onWait } = options;
  let notified = false;

  while (!(await tryCreateLock(lockPath))) {
    if (await reclaimIfStale(lockPath)) continue;

    if (!notified && onWait) {
      notified = true;
      await notifyWait(lockPath, onWait);
    }

    if (Date.now() >= deadline) {
      throw new LockTimeoutError(lockPath, await readLockHolder(lockPath));
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

export async function releaseLocalLock(lockPath: string): Promise<void> {
  await fs.rm(lockPath, { recursive: true, force: true });
}

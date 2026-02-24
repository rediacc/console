import { promises as fs } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, join } from 'node:path';
import lockfile from 'proper-lockfile';

const REDIACC_DIR = join(homedir(), '.rediacc');
export const STAGED_UPDATE_DIR = join(REDIACC_DIR, 'staged-update');
export const UPDATE_STATE_FILE = join(REDIACC_DIR, 'update-state.json');

const UPDATE_LOCK_FILE = join(REDIACC_DIR, 'update.lock');

export type PlatformKey =
  | 'linux-x64'
  | 'linux-arm64'
  | 'mac-x64'
  | 'mac-arm64'
  | 'win-x64'
  | 'win-arm64';

/**
 * Detect if running as a Node.js Single Executable Application (SEA).
 * SEA binaries have the executable basename starting with 'rdc'.
 */
export function isSEA(): boolean {
  const execName = basename(process.execPath)
    .toLowerCase()
    .replace(/\.exe$/, '');
  return execName.startsWith('rdc');
}

/**
 * Check if auto-update should be disabled based on environment.
 */
export function isUpdateDisabled(): boolean {
  // Explicit opt-out
  if (process.env.RDC_DISABLE_AUTOUPDATE === '1') return true;

  // CI environments
  if (process.env.CI === 'true') return true;

  // Binary in build/dist/node_modules path
  const execDir = dirname(process.execPath);
  if (/[/\\](node_modules|dist|build)[/\\]?/i.test(execDir)) return true;

  return false;
}

/**
 * Get the platform key for the current system.
 */
export function getPlatformKey(): PlatformKey | null {
  let arch: 'x64' | 'arm64' | null;
  if (process.arch === 'x64') {
    arch = 'x64';
  } else if (process.arch === 'arm64') {
    arch = 'arm64';
  } else {
    return null;
  }

  switch (process.platform) {
    case 'linux':
      return `linux-${arch}` as PlatformKey;
    case 'darwin':
      return `mac-${arch}` as PlatformKey;
    case 'win32':
      return `win-${arch}` as PlatformKey;
    default:
      return null;
  }
}

/**
 * Get the path to the old binary that may exist after a previous update.
 */
export function getOldBinaryPath(): string {
  const execPath = process.execPath;
  const ext = process.platform === 'win32' ? '.exe' : '';
  const base = execPath.replace(/\.exe$/, '');
  return `${base}.old${ext}`;
}

/**
 * Clean up old binary from a previous update (best-effort, never throws).
 */
export async function cleanupOldBinary(): Promise<void> {
  try {
    const oldPath = getOldBinaryPath();
    await fs.unlink(oldPath);
  } catch {
    // Ignore errors - file may not exist or may still be locked
  }
}

/**
 * Acquire the update lock file.
 * Returns a release function on success, or null if already locked.
 */
export async function acquireUpdateLock(): Promise<(() => Promise<void>) | null> {
  try {
    await fs.mkdir(dirname(UPDATE_LOCK_FILE), { recursive: true });
    // Ensure lock file exists (proper-lockfile requires it)
    try {
      await fs.access(UPDATE_LOCK_FILE);
    } catch {
      await fs.writeFile(UPDATE_LOCK_FILE, '', { mode: 0o600 });
    }

    const release = await lockfile.lock(UPDATE_LOCK_FILE, {
      stale: 300000, // 5 minutes (updates can involve large downloads)
      retries: 0, // Don't wait — skip if already locked
    });

    return async () => {
      try {
        await release();
      } catch {
        // Ignore release errors (lock may already be stale/released)
      }
    };
  } catch {
    return null;
  }
}

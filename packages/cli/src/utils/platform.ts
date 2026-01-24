import { mkdir, readFile, rm, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';

const FALLBACK_TEMP_DIR = '/tmp';

const LOCK_FILE = path.join(
  process.env.HOME ?? process.env.USERPROFILE ?? FALLBACK_TEMP_DIR,
  '.rediacc',
  'update.lock'
);

/**
 * Returns true if the current process is running as a Single Executable Application (SEA).
 * SEA binaries are named `rdc`, `rdc.exe`, or `rdc-<platform>-<arch>`.
 */
export function isSEA(): boolean {
  const base = path.basename(process.execPath).toLowerCase();
  return base.startsWith('rdc') && !base.startsWith('node');
}

/**
 * Returns true if auto-update should be disabled.
 * Disabled in CI, when env var is set, or when running from dev paths.
 */
export function isUpdateDisabled(): boolean {
  if (process.env.RDC_DISABLE_AUTOUPDATE === '1') return true;
  if (process.env.CI === 'true') return true;

  const execPath = process.execPath.replaceAll('\\', '/');
  if (execPath.includes('/node_modules/')) return true;
  if (execPath.includes('/dist/')) return true;
  if (execPath.includes('/build/')) return true;

  return false;
}

export type PlatformKey =
  | 'linux-x64'
  | 'linux-arm64'
  | 'mac-x64'
  | 'mac-arm64'
  | 'win-x64'
  | 'win-arm64';

/**
 * Returns the platform key for the current OS/arch combination.
 * Returns null if the platform is unsupported.
 */
export function getPlatformKey(): PlatformKey | null {
  const platform = process.platform;
  const arch = process.arch;

  if (arch !== 'x64' && arch !== 'arm64') return null;

  switch (platform) {
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
 * Returns the path for the old binary during self-replacement.
 * On Windows, strips `.exe` and adds `.old.exe`.
 * On other platforms, appends `.old`.
 */
export function getOldBinaryPath(execPath: string): string {
  if (process.platform === 'win32') {
    const withoutExt = execPath.replace(/\.exe$/i, '');
    return `${withoutExt}.old.exe`;
  }
  return `${execPath}.old`;
}

/**
 * Attempts to acquire the update lock file.
 * Returns true if the lock was acquired, false if another update is in progress.
 */
export async function acquireUpdateLock(): Promise<boolean> {
  const content = await readFile(LOCK_FILE, 'utf-8').catch(() => null);
  if (content) {
    const pid = Number.parseInt(content.trim(), 10);
    if (!Number.isNaN(pid) && isProcessAlive(pid)) {
      return false;
    }
  }

  const lockDir = path.dirname(LOCK_FILE);
  await mkdir(lockDir, { recursive: true });
  await writeFile(LOCK_FILE, String(process.pid), 'utf-8');
  return true;
}

/**
 * Releases the update lock file.
 */
export async function releaseUpdateLock(): Promise<void> {
  await unlink(LOCK_FILE).catch(() => {});
}

/**
 * Removes the old binary left over from a previous update.
 */
export async function cleanupOldBinary(oldPath: string): Promise<void> {
  await rm(oldPath, { force: true });
}

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

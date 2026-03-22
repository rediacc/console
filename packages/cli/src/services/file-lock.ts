import * as fs from 'node:fs/promises';
import * as path from 'node:path';

const isLockAlreadyHeldError = (e: unknown): e is NodeJS.ErrnoException =>
  e instanceof Error && 'code' in e && e.code === 'EEXIST';

async function isLockStale(pidPath: string): Promise<boolean> {
  try {
    const pid = Number.parseInt((await fs.readFile(pidPath, 'utf-8')).trim(), 10);
    if (Number.isNaN(pid)) return true;
    process.kill(pid, 0);
    return false;
  } catch {
    return true;
  }
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

export async function acquireLocalLock(
  lockPath: string,
  deadline: number,
  pollMs: number
): Promise<void> {
  const pidPath = path.join(lockPath, 'pid');
  while (!(await tryCreateLock(lockPath))) {
    if (await isLockStale(pidPath)) {
      await fs.rm(lockPath, { recursive: true, force: true });
      continue;
    }
    if (Date.now() >= deadline) {
      throw new Error(`Timed out waiting for local renet provision lock: ${lockPath}`);
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

export async function releaseLocalLock(lockPath: string): Promise<void> {
  await fs.rm(lockPath, { recursive: true, force: true });
}

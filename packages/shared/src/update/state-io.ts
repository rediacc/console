import { promises as fs } from 'node:fs';
import { dirname } from 'node:path';

/**
 * Read versioned local state from disk. Returns defaults on missing/corrupt file.
 *
 * Constrained only to `schemaVersion`, which is the sole field this function
 * reads. It previously required the full UpdateStateBase shape, which shut out
 * every other kind of local bookkeeping — the atomic-write and
 * corrupt-file-fallback behaviour here is generic, and a second copy of it
 * elsewhere would be free to drift.
 */
export async function readUpdateState<T extends { schemaVersion: number }>(
  filePath: string,
  defaults: T
): Promise<T> {
  try {
    const raw = await fs.readFile(filePath, 'utf-8');
    const parsed = JSON.parse(raw);
    if (parsed?.schemaVersion === 1) {
      return parsed as T;
    }
    return { ...defaults };
  } catch {
    return { ...defaults };
  }
}

/**
 * Write update state atomically (temp + rename). Permissions 0o600.
 */
export async function writeUpdateState<T>(filePath: string, state: T): Promise<void> {
  await fs.mkdir(dirname(filePath), { recursive: true });
  const tmpPath = `${filePath}.${Date.now()}.tmp`;
  await fs.writeFile(tmpPath, JSON.stringify(state, null, 2), { mode: 0o600 });
  await fs.rename(tmpPath, filePath);
}

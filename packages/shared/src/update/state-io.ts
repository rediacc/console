import { promises as fs } from 'node:fs';
import { dirname } from 'node:path';
import type { UpdateStateBase } from './types';

/**
 * Read update state from disk. Returns default state on missing/corrupt file.
 */
export async function readUpdateState<T extends UpdateStateBase>(
  filePath: string,
  defaults: T
): Promise<T> {
  try {
    const raw = await fs.readFile(filePath, 'utf-8');
    const parsed = JSON.parse(raw);
    if (parsed && parsed.schemaVersion === 1) {
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

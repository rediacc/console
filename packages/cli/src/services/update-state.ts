import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import type { CliUpdateState } from '@rediacc/shared/update';
import {
  readUpdateState as readState,
  writeUpdateState as writeState,
} from '@rediacc/shared/update';
import { STAGED_UPDATE_DIR, UPDATE_STATE_FILE } from '../utils/platform.js';

const DEFAULT_STATE: CliUpdateState = {
  schemaVersion: 1,
  lastCheckAt: null,
  lastAttemptAt: null,
  pendingUpdate: null,
  consecutiveFailures: 0,
  lastError: null,
};

/**
 * Read update state from disk. Returns default state on missing/corrupt file.
 */
export async function readUpdateState(): Promise<CliUpdateState> {
  return readState(UPDATE_STATE_FILE, DEFAULT_STATE);
}

/**
 * Write update state atomically (temp + rename). Permissions 0o600.
 */
export async function writeUpdateState(state: CliUpdateState): Promise<void> {
  return writeState(UPDATE_STATE_FILE, state);
}

/**
 * Get the staged binary path for a given version.
 */
export function getStagedBinaryPath(version: string): string {
  const ext = process.platform === 'win32' ? '.exe' : '';
  return join(STAGED_UPDATE_DIR, `rdc-${version}${ext}`);
}

/**
 * Remove non-matching staged files and old .tmp files. Best-effort, never throws.
 */
export async function cleanupStaleStagedFiles(state: CliUpdateState): Promise<void> {
  try {
    await fs.mkdir(STAGED_UPDATE_DIR, { recursive: true });
    const entries = await fs.readdir(STAGED_UPDATE_DIR);
    const keepName = state.pendingUpdate
      ? (state.pendingUpdate.stagedPath.split('/').pop() ??
        state.pendingUpdate.stagedPath.split('\\').pop())
      : null;

    for (const entry of entries) {
      if (entry === keepName) continue;
      await fs.unlink(join(STAGED_UPDATE_DIR, entry)).catch(() => {});
    }
  } catch {
    // Best-effort cleanup
  }
}

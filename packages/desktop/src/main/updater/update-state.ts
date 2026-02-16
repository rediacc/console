import { join } from 'node:path';
import { app } from 'electron';
import type { DesktopUpdateState } from '@rediacc/shared/update';
import {
  readUpdateState as readState,
  writeUpdateState as writeState,
} from '@rediacc/shared/update';

const STATE_FILE = join(app.getPath('home'), '.rediacc', 'update-state-desktop.json');

const DEFAULT_STATE: DesktopUpdateState = {
  schemaVersion: 1,
  lastCheckAt: null,
  lastAttemptAt: null,
  consecutiveFailures: 0,
  lastError: null,
  lastDownloadedVersion: null,
  consecutiveInstallFailures: 0,
};

export async function readDesktopUpdateState(): Promise<DesktopUpdateState> {
  return readState(STATE_FILE, DEFAULT_STATE);
}

export async function writeDesktopUpdateState(state: DesktopUpdateState): Promise<void> {
  return writeState(STATE_FILE, state);
}

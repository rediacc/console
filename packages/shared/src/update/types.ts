/** Common update state fields shared between CLI and desktop. */
export interface UpdateStateBase {
  schemaVersion: 1;
  lastCheckAt: string | null;
  lastAttemptAt: string | null;
  consecutiveFailures: number;
  lastError: string | null;
}

/** CLI-specific pending update info. */
export interface PendingUpdate {
  version: string;
  stagedPath: string;
  sha256: string;
  platformKey: string;
  downloadedAt: string;
  releaseNotesUrl?: string;
  applyAttempts?: number;
}

/** Full CLI update state. */
export interface CliUpdateState extends UpdateStateBase {
  pendingUpdate: PendingUpdate | null;
}

/** Desktop update state (no staging — electron-updater manages downloads). */
export interface DesktopUpdateState extends UpdateStateBase {
  /** Version of the last downloaded update (electron-updater manages the file). */
  lastDownloadedVersion: string | null;
  /** Number of times install has been attempted for the current downloaded update. */
  consecutiveInstallFailures: number;
}

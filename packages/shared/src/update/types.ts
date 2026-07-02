/** Release channel for CLI/desktop updates (stable, edge, or pr-N for previews). */
export type ReleaseChannel = string;

/** Common update state fields shared between CLI and desktop. */
export interface UpdateStateBase {
  schemaVersion: 1;
  lastCheckAt: string | null;
  lastAttemptAt: string | null;
  consecutiveFailures: number;
  lastError: string | null;
  channel?: ReleaseChannel;
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

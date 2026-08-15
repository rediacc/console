/**
 * Host-local last-backup-activity bookkeeping (`state.backupRuns`).
 *
 * A convenience record of the most recent chunk-store backup/restore/verify the
 * CLI drove for each repo, keyed by repo name. It is NOT the source of truth for
 * anything: scheduled runs commit their manifests from the machine with no CLI
 * present, and the account server's ledger is authoritative for billing and the
 * manifest index. This only lets `rdc backup` reads show what THIS host last did.
 *
 * Lives in the config's `state` bucket (not a sidecar file) for the same reasons
 * as `state.licenseRefresh`: config state is mocked, versioned, inspectable, and
 * travels with the config it describes. Written through `updateState`, so it
 * never bumps the version counter and is stripped from any push (R2-F2).
 */

import { configFileStorage } from '../../adapters/config-file-storage.js';
import { configService } from '../config/config-resources.js';

/**
 * 'snapshot' is the chunk-store write path. 'backup' is the retired rclone
 * push: nothing writes it any more, and it stays in the union only so run
 * histories recorded before the cutover still parse. Never emit it.
 */
type BackupRunKind = 'backup' | 'snapshot' | 'restore' | 'verify';

export interface BackupRunRecord {
  lastRunAt: string;
  kind: BackupRunKind;
  status: string;
  snapshotId?: string;
  storedBytes?: number;
  addedBytes?: number;
  error?: string;
}

/**
 * Record the outcome of a backup/restore/verify the CLI just drove for a repo.
 *
 * Best-effort: this is non-authoritative host-local convenience state (the server
 * ledger is the truth), so a failure to persist it must NEVER fail the backup or
 * restore it merely annotates — same doctrine as the DR nudge and telemetry.
 */
export async function recordBackupRun(
  repoName: string,
  record: Omit<BackupRunRecord, 'lastRunAt'> & { lastRunAt?: string }
): Promise<void> {
  const entry: BackupRunRecord = {
    ...record,
    lastRunAt: record.lastRunAt ?? new Date().toISOString(),
  };
  try {
    const configName = configService.getEffectiveConfigName();
    await configFileStorage.updateState(configName, (config) => ({
      ...config,
      state: {
        ...(config.state ?? {}),
        backupRuns: {
          ...(config.state?.backupRuns ?? {}),
          [repoName]: entry,
        },
      },
    }));
  } catch {
    // swallow: the run already happened; losing the local note is harmless.
  }
}

/**
 * `rdc backup purge <repo-ref>`: delete a repository's whole backup lineage from the chunk store
 * at once, keeping the repository itself. The same account call `repo delete --purge-backups`
 * makes (DELETE /backups/lineages/:guid), without the repository delete around it: no machine is
 * reached and the config record is only read.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { resolveRepoRefLocal } from '../utils/repo-target.js';
import type { BackupManifestsResponse } from './backup-storage.js';
import { lineageOf } from './backup-storage-browse.js';

/** The slice of GET /backups/usage this command reads: one lineage's stored bytes and chunks. */
interface LineageUsageRow {
  lineageGuid: string;
  storedBytes: number;
  chunkCount: number;
}

/** One round of DELETE /backups/lineages/:guid: the account deletes a bounded batch and says whether any remains. */
interface LineagePurgeResponse {
  lineageGuid: string;
  done: boolean;
  freedBytes: number;
  deletedSnapshots: number;
  deletedChunks: number;
  deletedBytes: number;
  remainingChunks?: number;
}

/** Guard against a server that never reports done: 200 rounds of the account's 5,000-object batch is a million objects. */
const MAX_PURGE_ROUNDS = 200;

/**
 * Repeat the account's bounded lineage delete until it reports done, printing progress per round
 * (stderr). The account's contract: a round that is not done reports freedBytes 0 and deletedSnapshots 0,
 * and the final round carries the lineage totals the ledger freed, so those two come from the final
 * round alone while chunk and byte counts are summed. A response with no `done` field (an older server,
 * one call per delete) is the final round. Rounds are idempotent, so
 * a failed run is finished by running the command again.
 */
export async function purgeLineageRounds(
  name: string,
  lineage: string,
  formatBytes: (bytes: number) => string
): Promise<LineagePurgeResponse> {
  let deletedChunks = 0;
  let deletedBytes = 0;
  for (let round = 1; round <= MAX_PURGE_ROUNDS; round++) {
    const result = await accountServerFetch<LineagePurgeResponse>(
      `/account/api/v1/backups/lineages/${encodeURIComponent(lineage)}`,
      { method: 'DELETE' }
    );
    deletedChunks += result.deletedChunks;
    deletedBytes += result.deletedBytes;
    if (result.done !== false) return { ...result, deletedChunks, deletedBytes };
    outputService.info(
      t('commands.backup.purge.progress', {
        name,
        round,
        chunks: deletedChunks,
        bytes: formatBytes(deletedBytes),
      })
    );
  }
  throw new Error(t('commands.backup.purge.tooManyRounds', { name, rounds: MAX_PURGE_ROUNDS }));
}

interface PurgeOptions {
  dryRun?: boolean;
  yes?: boolean;
}

/** What the store holds for one lineage right now. A lineage absent from usage holds nothing. */
async function lineageFootprint(
  lineage: string
): Promise<{ storedBytes: number; chunkCount: number }> {
  const usage = await accountServerFetch<{ lineages: LineageUsageRow[] }>(
    '/account/api/v1/backups/usage'
  );
  const row = usage.lineages.find((l) => l.lineageGuid === lineage);
  return { storedBytes: row?.storedBytes ?? 0, chunkCount: row?.chunkCount ?? 0 };
}

/** The post-purge usage read: a failure after a successful DELETE is reported, never fatal. */
async function footprintAfterPurge(
  lineage: string
): Promise<{ storedBytes: number; chunkCount: number } | undefined> {
  try {
    return await lineageFootprint(lineage);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    outputService.warn(t('commands.backup.purge.usageUnavailable', { error: message }));
    return undefined;
  }
}

/** The config record behind the ref, read only. Unknown repos and forks are refused here, before any account call. */
async function resolvePurgeTarget(repoRef: string): Promise<{ repoKey: string; lineage: string }> {
  const { repoKey } = await resolveRepoRefLocal(repoRef);
  const repo = await configService.getRepository(repoKey);
  if (!repo) {
    throw new ValidationError(t('commands.backup.purge.notFound', { name: repoKey }));
  }
  await assertCommandPolicy(CMD.BACKUP_PURGE, repoKey);
  // A fork's lineage is its parent's: purging it would take the parent's backups with it.
  if (repo.grandGuid && repo.grandGuid !== repo.repositoryGuid) {
    throw new ValidationError(t('commands.backup.purge.forkRefused', { name: repoKey }));
  }
  return { repoKey, lineage: lineageOf(repo) };
}

/** Typed-name confirmation: anything but the exact repository name cancels. */
async function confirmByName(repoKey: string, snapshots: number, bytes: string): Promise<boolean> {
  const { askInput } = await import('../utils/prompt.js');
  const answer = await askInput(
    t('commands.backup.purge.confirm', { name: repoKey, count: snapshots, bytes }),
    /[\s\S]*/
  );
  return answer === repoKey;
}

async function runBackupPurge(repoRef: string, options: PurgeOptions): Promise<void> {
  const { repoKey, lineage } = await resolvePurgeTarget(repoRef);
  // A Free License (or no login) has no hosted store to purge: say so instead of a token error.
  assertHostedBackupAccount();
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const format = getOutputFormat();

  const [history, before] = await Promise.all([
    accountServerFetch<BackupManifestsResponse>(
      `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
    ),
    lineageFootprint(lineage),
  ]);
  const snapshots = history.manifests.length;
  const plan = {
    repository: repoKey,
    lineageGuid: lineage,
    snapshots,
    storedBytes: before.storedBytes,
    chunkCount: before.chunkCount,
  };

  if (options.dryRun) {
    if (format !== 'table') {
      outputService.print({ dryRun: true, ...plan }, format);
      return;
    }
    outputService.info(
      t('commands.backup.purge.dryRun', {
        name: repoKey,
        lineage,
        count: snapshots,
        bytes: formatSizeBytes(before.storedBytes),
        chunks: before.chunkCount,
      })
    );
    return;
  }

  // The usage and manifests reads answer empty for an unknown lineage, but the DELETE answers 404 for one with neither: say so instead of sending a DELETE that cannot succeed.
  if (snapshots === 0 && before.storedBytes === 0 && before.chunkCount === 0) {
    outputService.info(t('commands.backup.purge.nothingStored', { name: repoKey }));
    return;
  }

  if (
    !options.yes &&
    !(await confirmByName(repoKey, snapshots, formatSizeBytes(before.storedBytes)))
  ) {
    outputService.info(t('status.cancelled'));
    return;
  }

  const purged = await purgeLineageRounds(repoKey, lineage, formatSizeBytes);
  // The usage row before and after is the evidence for the stored chunk count.
  const after = await footprintAfterPurge(lineage);

  if (format !== 'table') {
    outputService.print({ ...plan, purged, after: after ?? null }, format);
    return;
  }
  outputService.success(
    t('commands.backup.purge.success', {
      name: repoKey,
      count: purged.deletedSnapshots,
      bytes: formatSizeBytes(purged.freedBytes),
    })
  );
  if (after) {
    outputService.info(
      t('commands.backup.purge.usageDelta', {
        beforeBytes: formatSizeBytes(before.storedBytes),
        beforeChunks: before.chunkCount,
        afterBytes: formatSizeBytes(after.storedBytes),
        afterChunks: after.chunkCount,
      })
    );
  }
}

/** Register `backup purge <repo-ref> [--dry-run] [-y]`. */
export function registerBackupPurge(backup: Command): void {
  backup
    .command('purge')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.purge.description'))
    .summary(t('commands.backup.purge.descriptionShort'))
    .option('--dry-run', t('options.dryRun'))
    .option('-y, --yes', t('options.yes'))
    .action(async (repoRef: string, options: PurgeOptions) => {
      try {
        await runBackupPurge(repoRef, options);
      } catch (error) {
        handleError(error);
      }
    });
}

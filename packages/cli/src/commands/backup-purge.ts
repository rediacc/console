/**
 * `rdc backup purge <repo-ref>`: delete a repository's whole backup lineage from the chunk store
 * at once, keeping the repository itself. The same account call `repo delete --purge-backups`
 * makes (DELETE /backups/lineages/:guid), without the repository delete around it: no machine is
 * reached and the config record is only read.
 *
 * `rdc backup purge --lineage <guid>`: the same call for a lineage whose repository is gone from
 * the config (deleted without `--purge-backups`), named by the id `backup usage` lists. A lineage
 * a config repository still owns is refused and goes through the repo-ref form, which knows forks.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat } from '../types/index.js';
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
  /** Set (with HTTP 202) when a delayed-deletion window holds the purge: nothing was deleted, and it runs at `purgeAfter` unless cancelled. */
  delayed?: boolean;
  code?: string;
  purgeAfter?: string;
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
 *
 * A delayed answer (a delayed-deletion window above 0: HTTP 202, `delayed` true, `done` false) ends the
 * loop at once: it deleted nothing, and another round would only read the same due time, 200 times,
 * and then throw.
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
    if (result.delayed || result.done !== false) return { ...result, deletedChunks, deletedBytes };
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
  cancel?: boolean;
  lineage?: string;
}

/** `YYYY-MM-DD HH:MM` (UTC) of an ISO instant. */
const minuteOf = (iso: string): string => iso.replace('T', ' ').slice(0, 16);

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

/** What a purge acts on: the display name (the repository, or the lineage id itself) and the lineage. */
interface PurgeTarget {
  repoKey: string;
  lineage: string;
  byLineage: boolean;
}

/** The command that cancels a delayed purge of this target, as the operator types it. */
function cancelCommand(target: PurgeTarget): string {
  return target.byLineage
    ? `rdc backup purge --lineage ${target.lineage} --cancel`
    : `rdc backup purge ${target.repoKey} --cancel`;
}

/** The config record behind the ref, read only. Unknown repos and forks are refused here, before any account call. */
async function resolvePurgeTarget(repoRef: string): Promise<PurgeTarget> {
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
  return { repoKey, lineage: lineageOf(repo), byLineage: false };
}

/**
 * The `--lineage` target: the id itself, refused while a repository in this config still owns it
 * (that repository's purge goes through its ref) and checked against the agent policy like any
 * purge. The owner check reads this config only; the server's delayed purge window is what a
 * purge from another config falls back on. A `--cancel` skips the owner check: cancelling deletes
 * nothing, and the cancel `repo delete --purge-backups` prints must run while a fork of the
 * deleted repository still holds the lineage.
 */
async function resolveLineageTarget(lineage: string, cancel: boolean): Promise<PurgeTarget> {
  const owner = cancel
    ? undefined
    : (await configService.listRepositories()).find((r) => lineageOf(r.config) === lineage);
  if (owner) {
    throw new ValidationError(
      t('commands.backup.purge.lineageOwned', { lineage, name: owner.name })
    );
  }
  await assertCommandPolicy(CMD.BACKUP_PURGE, undefined, lineage);
  return { repoKey: lineage, lineage, byLineage: true };
}

/** Exactly one of `<repo-ref>` and `--lineage` names what is purged. */
function purgeTarget(repoRef: string | undefined, options: PurgeOptions): Promise<PurgeTarget> {
  if (Boolean(repoRef) === Boolean(options.lineage)) {
    throw new ValidationError(t('commands.backup.purge.targetRequired'));
  }
  return options.lineage
    ? resolveLineageTarget(options.lineage, Boolean(options.cancel))
    : resolvePurgeTarget(repoRef ?? '');
}

/** Typed-name confirmation: anything but the exact repository name (or lineage id) cancels. */
async function confirmByName(
  target: PurgeTarget,
  snapshots: number,
  bytes: string
): Promise<boolean> {
  const { askInput } = await import('../utils/prompt.js');
  const key = target.byLineage
    ? 'commands.backup.purge.confirmLineage'
    : 'commands.backup.purge.confirm';
  const answer = await askInput(
    t(key, { name: target.repoKey, count: snapshots, bytes }),
    /[\s\S]*/
  );
  return answer === target.repoKey;
}

/** `purge --cancel`: undo a purge a delayed-deletion window is holding. Nothing is deleted or read besides the cancel. */
async function runCancelPurge(repoKey: string, lineage: string): Promise<void> {
  assertHostedBackupAccount();
  const result = await accountServerFetch<{ lineageGuid: string; cancelled: boolean }>(
    `/account/api/v1/backups/lineages/${encodeURIComponent(lineage)}/purge/cancel`,
    { method: 'POST' }
  );
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(result, format);
    return;
  }
  if (result.cancelled) {
    outputService.success(t('commands.backup.purge.cancelled', { name: repoKey }));
  } else {
    outputService.info(t('commands.backup.purge.nothingWaiting', { name: repoKey }));
  }
}

/** `--dry-run`: the plan as structured output, or the one sentence of what would be purged. */
function printDryRun(
  plan: {
    repository: string;
    lineageGuid: string;
    snapshots: number;
    storedBytes: number;
    chunkCount: number;
  },
  format: OutputFormat,
  formatBytes: (bytes: number) => string
): void {
  if (format !== 'table') {
    outputService.print({ dryRun: true, ...plan }, format);
    return;
  }
  outputService.info(
    t('commands.backup.purge.dryRun', {
      name: plan.repository,
      lineage: plan.lineageGuid,
      count: plan.snapshots,
      bytes: formatBytes(plan.storedBytes),
      chunks: plan.chunkCount,
    })
  );
}

async function runBackupPurge(repoRef: string | undefined, options: PurgeOptions): Promise<void> {
  if (options.cancel && options.dryRun) {
    throw new ValidationError(t('commands.backup.purge.cancelExclusive'));
  }
  const target = await purgeTarget(repoRef, options);
  const { repoKey, lineage } = target;
  if (options.cancel) {
    await runCancelPurge(repoKey, lineage);
    return;
  }
  // A Free License (or no login) has no hosted store to purge: say so instead of a token error.
  assertHostedBackupAccount();
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const format = getOutputFormat();

  const [history, before] = await Promise.all([
    accountServerFetch<BackupManifestsResponse>(
      // One row is enough: `total` is the lineage's whole count and rides the first page of a named lineage.
      `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}&limit=1`
    ),
    lineageFootprint(lineage),
  ]);
  // The listing is capped per page, so its length understates a long history; the server's count does not.
  const snapshots = history.total ?? history.manifests.length;
  const plan = {
    repository: repoKey,
    lineageGuid: lineage,
    snapshots,
    storedBytes: before.storedBytes,
    chunkCount: before.chunkCount,
  };

  if (options.dryRun) {
    printDryRun(plan, format, formatSizeBytes);
    return;
  }

  // The usage and manifests reads answer empty for an unknown lineage, but the DELETE answers 404 for one with neither: say so instead of sending a DELETE that cannot succeed.
  if (snapshots === 0 && before.storedBytes === 0 && before.chunkCount === 0) {
    outputService.info(t('commands.backup.purge.nothingStored', { name: repoKey }));
    return;
  }

  if (
    !options.yes &&
    !(await confirmByName(target, snapshots, formatSizeBytes(before.storedBytes)))
  ) {
    outputService.info(t('status.cancelled'));
    return;
  }

  const purged = await purgeLineageRounds(repoKey, lineage, formatSizeBytes);
  const cancel = cancelCommand(target);
  await reportPurged({ repoKey, lineage, plan, before, purged, format, cancel });
}

interface PurgeReport {
  repoKey: string;
  lineage: string;
  plan: Record<string, unknown>;
  before: { storedBytes: number; chunkCount: number };
  purged: LineagePurgeResponse;
  format: OutputFormat;
  /** The command that cancels a delayed purge, named in the delayed warning. */
  cancel: string;
}

/** What the operator is told once the rounds end: held (delayed), or done with the usage before and after. */
async function reportPurged(report: PurgeReport): Promise<void> {
  const { repoKey, lineage, plan, before, purged, format, cancel } = report;
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  // A delayed answer deleted nothing: say when it runs and how to stop it, and skip the success line and the usage delta, which would claim bytes that are still stored and charged.
  if (purged.delayed) {
    if (format !== 'table') {
      outputService.print({ ...plan, purged }, format);
      return;
    }
    outputService.warn(
      t('commands.backup.purge.delayed', {
        name: repoKey,
        when: purged.purgeAfter ? minuteOf(purged.purgeAfter) : '-',
        cancel,
      })
    );
    return;
  }
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

/** Register `backup purge [repo-ref] [--lineage <guid>] [--dry-run] [-y] [--cancel]`. */
export function registerBackupPurge(backup: Command): void {
  backup
    .command('purge')
    .argument('[repo-ref]', t('options.repoRef'))
    .summary(t('commands.backup.purge.descriptionShort'))
    .description(t('commands.backup.purge.description'))
    .option('--lineage <guid>', t('commands.backup.purge.optionLineage'))
    .option('--dry-run', t('options.dryRun'))
    .option('-y, --yes', t('options.yes'))
    .option('--cancel', t('commands.backup.purge.optionCancel'))
    .action(async (repoRef: string | undefined, options: PurgeOptions) => {
      try {
        await runBackupPurge(repoRef, options);
      } catch (error) {
        handleError(error);
      }
    });
}

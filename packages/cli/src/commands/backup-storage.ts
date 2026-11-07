/**
 * `rdc backup usage | manifests | verify`, the read side of the content-addressed
 * chunk-store backup (spec/02). `usage` and `manifests` are control-plane READS
 * through the account tunnel (`accountServerFetch`, so the request is
 * E2E-sealed); they need the `backup:read` scope
 * on the presented token. `verify` is executor-side: it runs the renet
 * `backup_verify` verb on the machine that holds the repo, the machine, not the
 * server, owns the anchor and the cell data. `verify --store` is the exception,
 * a control-plane call: the server re-hashes the lineage's stored chunks.
 */

import { BACKUP_BROWSE_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { recordBackupRun } from '../services/backup/backup-runs-state.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { planStep } from '../services/jobs/steps.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef, resolveRepoRefLocal } from '../utils/repo-target.js';
import { registerBackupCheck } from './backup-check.js';
import { registerBackupChurn } from './backup-churn.js';
import { registerBackupImmutability } from './backup-immutability.js';
import { registerBackupReconcile } from './backup-reconcile.js';
import { registerBackupRepair } from './backup-repair.js';
import { registerBackupRetention, registerBackupSnapshots } from './backup-retention-commands.js';
import { RENET_NO_LISTING_EXIT, resolveLineage, runBrowseAt } from './backup-storage-browse.js';
import { registerBackupSnapshot } from './backup-storage-snapshot.js';
import { runStoreVerify } from './backup-store-verify.js';
import { registerBackupTocKey } from './backup-toc-key.js';

/** GET /backups/usage, subscription aggregate + per-lineage breakdown. */
interface BackupUsageResponse {
  subscriptionId: string;
  /** The physical total the store holds: live plus waiting. */
  storedBytes: number;
  /** What kept versions can restore: the figure the quota counts. */
  liveBytes: number;
  /** What no kept version can restore, waiting out its grace. Not charged. */
  waitingBytes: number;
  waitingChunks: number;
  /** Waiting bytes above this refuse a stream committing faster than hourly. */
  churnCapBytes: number;
  churnCapped: boolean;
  chunkCount: number;
  usageAdjustment: number;
  leasedBytes: number;
  activeLeases: number;
  usedBytes: number;
  quotaBytes: number;
  overLimit: boolean;
  retentionStartedAt: string | null;
  lineages: {
    lineageGuid: string;
    storedBytes: number;
    liveBytes: number;
    waitingBytes: number;
    chunkCount: number;
    logicalBytes: number;
    updatedAt: string;
  }[];
}

/** GET /backups/manifests and GET /backups/snapshots/resolve: one committed snapshot. */
export interface BackupManifestEntry {
  snapshotId: string;
  lineageGuid: string;
  streamId: string;
  parentSnapshotId?: string | null;
  cellSizeBytes: number;
  totalBytes: number;
  addedBytes: number;
  addedChunkCount: number;
  hasIndex?: boolean;
  createdAt: string;
  /** What the commit declared; null on a row from before the field existed. */
  consistency?: string | null;
  /** Set on a delayed delete, which still restores until `deleteAfter`. */
  deletedAt?: string | null;
  deleteAfter?: string | null;
}

/**
 * A page of the server-side snapshot index, newest first. `nextBefore` is the `before` of the
 * next page (null on the last); `total` is the lineage's row count, sent on the first page of one
 * named lineage only. `backup restore --at` does not read this listing: it resolves a time through
 * GET /backups/snapshots/resolve (backup-restore-chunk.ts), because the page is capped.
 */
export interface BackupManifestsResponse {
  manifests: BackupManifestEntry[];
  nextBefore?: string | null;
  total?: number;
}

/** `backup usage`, quota vs stored bytes, plus per-repo (lineage) usage. */
function registerBackupUsage(backup: Command): void {
  backup
    .command('usage')
    .description(t('commands.backup.usage.description'))
    .action(async () => {
      try {
        assertHostedBackupAccount();
        outputService.info(t('commands.backup.usage.fetching'));
        const usage = await accountServerFetch<BackupUsageResponse>(
          '/account/api/v1/backups/usage'
        );

        const format = getOutputFormat();
        if (format !== 'table') {
          outputService.print(usage, format);
          return;
        }

        const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
        outputService.info(
          t('commands.backup.usage.summary', {
            used: formatSizeBytes(usage.usedBytes),
            quota: formatSizeBytes(usage.quotaBytes),
            live: formatSizeBytes(usage.liveBytes),
            leased: formatSizeBytes(usage.leasedBytes),
            chunks: usage.chunkCount,
            over: usage.overLimit ? t('commands.backup.usage.overLimit') : '',
          })
        );
        // Waiting storage is not charged: it is named so the stored total is not read as the bill.
        if (usage.waitingBytes > 0 || usage.waitingChunks > 0) {
          outputService.info(
            t('commands.backup.usage.waiting', {
              waiting: formatSizeBytes(usage.waitingBytes),
              chunks: usage.waitingChunks,
              cap: formatSizeBytes(usage.churnCapBytes),
            })
          );
        }
        if (usage.churnCapped) {
          outputService.warn(
            t('commands.backup.usage.throttled', { cap: formatSizeBytes(usage.churnCapBytes) })
          );
        }

        if (usage.lineages.length === 0) {
          outputService.print(t('commands.backup.usage.empty'));
          return;
        }

        const resolve = createGuidResolver(await loadGuidMap());
        const rows = usage.lineages
          .map((l) => ({
            repo: resolve(l.lineageGuid),
            lineage: l.lineageGuid,
            live: formatSizeBytes(l.liveBytes),
            waiting: formatSizeBytes(l.waitingBytes),
            stored: formatSizeBytes(l.storedBytes),
            logical: formatSizeBytes(l.logicalBytes),
            chunks: l.chunkCount,
            updated: l.updatedAt.replace('T', ' ').replace(/\..*$/, ''),
          }))
          .sort((a, b) => a.repo.localeCompare(b.repo));

        const columns = [
          { key: 'repo', header: 'Repo' },
          { key: 'lineage', header: 'Lineage' },
          { key: 'live', header: 'Live', align: 'right' as const },
          { key: 'waiting', header: 'Waiting', align: 'right' as const },
          { key: 'stored', header: 'Stored', align: 'right' as const },
          { key: 'logical', header: 'Logical', align: 'right' as const },
          { key: 'chunks', header: 'Chunks', align: 'right' as const },
          { key: 'updated', header: 'Updated' },
        ];
        outputService.print(outputService.format(rows, format, columns));
      } catch (error) {
        handleError(error);
      }
    });
}

interface ManifestsOptions {
  limit?: string;
  before?: string;
  includeDeleted?: boolean;
}

/** The query parameters `backup manifests` was asked for: none unless a flag names one. */
function manifestsQuery(options: ManifestsOptions): string[] {
  const query: string[] = [];
  if (options.limit !== undefined) {
    if (!/^[1-9]\d*$/.test(options.limit)) {
      throw new ValidationError(
        t('commands.backup.manifests.limitInvalid', { value: options.limit })
      );
    }
    query.push(`limit=${options.limit}`);
  }
  if (options.before) query.push(`before=${encodeURIComponent(options.before)}`);
  if (options.includeDeleted) query.push('includeDeleted=1');
  return query;
}

/** `YYYY-MM-DD HH:MM` of an ISO instant. */
const minuteOf = (iso: string): string => iso.replace('T', ' ').slice(0, 16);

/** `backup manifests [repo-ref]`, the server snapshot index, optionally scoped. */
function registerBackupManifests(backup: Command): void {
  backup
    .command('manifests')
    .argument('[repo-ref]', t('options.repoRef'))
    .description(t('commands.backup.manifests.description'))
    .option('--limit <n>', t('commands.backup.manifests.optionLimit'))
    .option('--before <cursor>', t('commands.backup.manifests.optionBefore'))
    .option('--include-deleted', t('commands.backup.manifests.optionIncludeDeleted'))
    .action(async (repoRef: string | undefined, options: ManifestsOptions) => {
      try {
        const query = manifestsQuery(options);
        // Scope to one lineage (grand GUID) when a repo is named. Config-local resolution only, the index lives on the server, not on a machine.
        const lineage = repoRef ? await resolveLineage(repoRef) : undefined;

        assertHostedBackupAccount();
        outputService.info(t('commands.backup.manifests.fetching'));
        if (lineage) query.unshift(`lineage=${encodeURIComponent(lineage)}`);
        const result = await accountServerFetch<BackupManifestsResponse>(
          `/account/api/v1/backups/manifests${query.length > 0 ? `?${query.join('&')}` : ''}`
        );

        // The lineage GUID is the grand repo's GUID, and every fork of it shares that GUID, so a fork's snapshots resolve to the grand's name. An unknown lineage resolves to null (`-o json`) or its short GUID (table).
        const resolve = createGuidResolver(await loadGuidMap());
        const nameOf = (lineage: string): string | null => {
          const name = resolve(lineage);
          return name === lineage ? null : name;
        };
        const repoOf = (lineage: string): string => nameOf(lineage) ?? lineage.slice(0, 8);
        // Newest first, by parsed time: ISO strings with and without fractional seconds do not order correctly as text.
        // An unparseable createdAt counts as the oldest, so the comparator never returns NaN and the order stays deterministic.
        const createdMs = (createdAt: string): number => Date.parse(createdAt) || 0;
        const sorted = [...result.manifests].sort(
          (a, b) => createdMs(b.createdAt) - createdMs(a.createdAt)
        );

        const format = getOutputFormat();
        if (format !== 'table') {
          // Every wire field stays; `repo` is the one addition.
          outputService.print(
            { ...result, manifests: sorted.map((m) => ({ ...m, repo: nameOf(m.lineageGuid) })) },
            format
          );
          return;
        }
        if (sorted.length === 0) {
          outputService.print(t('commands.backup.manifests.empty'));
          return;
        }

        const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
        // Ids read `<timestamp>Z-<hash>`: the timestamp is the Snapshot column already, so the short form is the first 8 hash characters. Full ids stay in `-o json`.
        const shortId = (id: string): string => (id.split('-').pop() ?? id).slice(0, 8);
        const rows = sorted.map((m) => ({
          repo: repoOf(m.lineageGuid),
          snapshot: m.createdAt.replace('T', ' ').replace(/\..*$/, '').replace(/Z$/, ''),
          id: shortId(m.snapshotId),
          parent: m.parentSnapshotId ? shortId(m.parentSnapshotId) : '-',
          total: formatSizeBytes(m.totalBytes),
          added: `${formatSizeBytes(m.addedBytes)} / ${m.addedChunkCount}`,
          index: m.hasIndex ? 'yes' : 'no',
          consistency: m.consistency ?? '-',
          // A delayed delete still restores until it is due, so the cell says when, not "deleted".
          state: m.deleteAfter ? `deleting after ${minuteOf(m.deleteAfter)}` : '-',
        }));

        const columns = [
          { key: 'repo', header: 'Repo' },
          { key: 'snapshot', header: 'Snapshot' },
          { key: 'id', header: 'Id' },
          { key: 'parent', header: 'Parent' },
          { key: 'total', header: 'Total', align: 'right' as const },
          { key: 'added', header: 'Added / chunks', align: 'right' as const },
          { key: 'index', header: 'Index' },
          { key: 'consistency', header: 'Consistency' },
          { key: 'state', header: 'State' },
        ];
        outputService.print(outputService.format(rows, format, columns));
        // The listing is paged newest first: the cursor of the next page is named, never left to be guessed.
        if (result.nextBefore) {
          outputService.info(
            t('commands.backup.manifests.more', {
              shown: sorted.length,
              total: result.total ?? sorted.length,
              before: result.nextBefore,
            })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * `backup browse <repo-ref> [--path] [--at <time|snapshot>]` -- list what a repository
 * contains. With `--at`, the listing comes from the chunk store (`backup_browse_at`).
 *
 * Without `--at`, a LOCAL read on the machine holding the image. A manifest maps grid
 * cells to the hash of their CIPHERTEXT, so it carries no filesystem information and no
 * listing is derivable from it; the only way to list files from an image is to open
 * it and walk it, which is what renet does here. A chunk-store listing exists only
 * when the snapshot stored one at snapshot time, and that is the `--at` path.
 *
 * Uses resolveRepoRef, not resolveRepoRefLocal: unlike `backup manifests`,
 * which reads the server index, this must reach a machine to read an image.
 */
function registerBackupBrowse(backup: Command): void {
  backup
    .command('browse')
    .argument('<repo-ref>', t('options.repoRef'))
    // .summary is the one-liner `--help` lists; .description is the long form a
    // reader sees on the command's own page. The long one carries the keyfile precondition and the chunk-store limit, which is too much for a list.
    .summary(t('commands.backup.browse.descriptionShort'))
    .description(t('commands.backup.browse.description'))
    .option('--path <subdir>', t('commands.backup.browse.optionPath'))
    .option('--depth <n>', t('commands.backup.browse.optionDepth'))
    .option('--limit <n>', t('commands.backup.browse.optionLimit'))
    .option('--at <time|snapshot>', t('commands.backup.browse.optionAt'))
    .option('--from <storeId>', t('commands.backup.browse.optionFrom'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        repoRef: string,
        options: {
          path?: string;
          depth?: string;
          limit?: string;
          at?: string;
          from?: string;
          debug?: boolean;
        }
      ) => {
        try {
          if (options.from !== undefined && !options.at) {
            throw new ValidationError(t('commands.backup.browse.fromNeedsAt'));
          }
          const { repoKey, machineName } = await resolveRepoRef(repoRef);
          let snapshotId = '';
          let result: Awaited<ReturnType<typeof executeRepoFunction>>;
          // The listing print is the job's step (PLAN-detached-jobs J17), so a ticket handed back early prints nothing half-done.
          const limit = options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT;
          if (options.at) {
            ({ result, snapshotId } = await runBrowseAt(repoKey, machineName, options.at, options));
          } else {
            result = await executeRepoFunction(
              'backup_browse',
              repoKey,
              machineName,
              {
                path: options.path ?? '',
                depth: options.depth ?? BACKUP_BROWSE_DEFAULTS.DEPTH,
                limit,
              },
              // captureOutput for the same reason as backup verify: the listing IS the answer, and without it the step detector drops the verb's JSON and browse exits 0 with EMPTY stdout.
              {
                debug: options.debug,
                captureOutput: true,
                job: {
                  verb: 'backup browse',
                  steps: [planStep('renderBackupBrowse', { repo: repoKey, snapshot: '', limit })],
                },
              },
              {
                starting: t('commands.backup.browse.starting', { name: repoKey }),
                completed: t('commands.backup.browse.completed', { name: repoKey }),
                failed: t('commands.backup.browse.failed', { name: repoKey }),
              }
            );
          }

          // A job that outlived the attach window printed its ticket, and its listing renders from `rdc job wait`.
          // Exit 18: the snapshot has no stored listing (an older snapshot, or one taken without a listing). A distinct code, as with 16, so a script can tell "no listing there" from "it broke".
          if (options.at && result.exitCode === RENET_NO_LISTING_EXIT) {
            outputService.warn(
              t('commands.backup.browse.noListing', { name: repoKey, snapshot: snapshotId })
            );
            setExitCode(RENET_NO_LISTING_EXIT);
          }
          // executeRepoFunction already rendered the failure (envelope and exit code), and a success printed the listing as the job's step.
        } catch (error) {
          handleError(error);
        }
      }
    );
}

/**
 * `backup verify <repo> [--deep] [--store]`. Without `--store`, executor-side
 * anchor verification on the machine. With `--store`, the server re-downloads
 * every chunk the repo's lineage references and re-hashes it, so a flipped or
 * lost object in the store is named by its hash; exit 1 when any is.
 */
function registerBackupVerify(backup: Command): void {
  backup
    .command('verify')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.verify.description'))
    .option('--deep', t('commands.backup.verify.optionDeep'))
    .option('--store', t('commands.backup.verify.optionStore'))
    .option('--restore-test', t('commands.backup.verify.optionRestoreTest'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        repoRef: string,
        options: { deep?: boolean; store?: boolean; restoreTest?: boolean; debug?: boolean }
      ) => {
        try {
          // A restore test is its own check, with its own verdict on the snapshot; mixing it with the anchor or store checks would blur which verdict was printed.
          if (options.restoreTest) {
            if (options.deep || options.store) {
              throw new ValidationError(t('commands.backup.verify.restoreTestExclusive'));
            }
            const { runRestoreTest } = await import('./backup-restore-test.js');
            await runRestoreTest(repoRef);
            return;
          }
          // `--deep` re-hashes the machine's cells and `--store` re-hashes the server's chunks: two different checks, and one of them would be dropped silently.
          if (options.deep && options.store) {
            throw new ValidationError(t('commands.backup.verify.deepStoreExclusive'));
          }
          if (options.store) {
            const { repoKey } = await resolveRepoRefLocal(repoRef);
            const verdict = await runStoreVerify(await resolveLineage(repoRef));
            const format = getOutputFormat();
            outputService.print(verdict, format === 'table' ? 'json' : format);
            // A lineage with no stored chunks verified nothing: it is not recorded or reported as verified.
            if (verdict.checked === 0) {
              outputService.warn(t('commands.backup.verify.storeEmpty', { name: repoKey }));
              await recordBackupRun(repoKey, { kind: 'verify', status: 'empty' });
              setExitCode(1);
              return;
            }
            const clean = verdict.missing.length === 0 && verdict.corrupt.length === 0;
            await recordBackupRun(repoKey, {
              kind: 'verify',
              status: clean ? 'verified' : 'mismatch',
            });
            if (!clean) setExitCode(1);
            return;
          }
          const { repoKey, machineName } = await resolveRepoRef(repoRef);
          const level = options.deep ? 'full' : 'spot';
          await executeRepoFunction(
            'backup_verify',
            repoKey,
            machineName,
            { level },
            // captureOutput: the verdict IS the answer here. Without it the step detector drops the verb's JSON and `backup verify` exits 0 with EMPTY stdout whether the anchor verified or mismatched, which is the one thing an operator must be able to tell apart.
            {
              debug: options.debug,
              captureOutput: true,
              // The verdict print and the run record are steps on the job's ticket, so nothing says "verified" before the job has verified anything (PLAN-detached-jobs J4). The verdict is structured data, printed as structured data in every mode. On a failure executeRepoFunction renders the failure (envelope and exit code), and renet's
              // verdict rides its output tail; printing the verdict too would put a SECOND JSON document on stdout, so no failure step prints.
              job: {
                verb: 'backup verify',
                steps: [
                  planStep('reportVerifyVerdict', { repo: repoKey, level }),
                  // The status is read from renet's verdict on both outcomes, so a `no-backup` run never records `verified`.
                  planStep('recordVerifyVerdict', { repo: repoKey }),
                  planStep('recordVerifyVerdictFailed', { repo: repoKey }),
                ],
              },
            },
            {
              starting: t('commands.backup.verify.starting', { name: repoKey, level }),
              completed: t('commands.backup.verify.completed', { name: repoKey }),
              failed: t('commands.backup.verify.failed', { name: repoKey }),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
}

export { snapshotUploadParams } from './backup-storage-snapshot.js';
export { runStoreVerify, type StoreVerifyVerdict } from './backup-store-verify.js';

/** Register the chunk-store backup reads + verification under `rdc backup`. */
export function registerBackupStorageCommands(backup: Command): void {
  registerBackupUsage(backup);
  registerBackupManifests(backup);
  registerBackupVerify(backup);
  registerBackupBrowse(backup);
  registerBackupSnapshot(backup);
  registerBackupRetention(backup);
  registerBackupSnapshots(backup);
  registerBackupImmutability(backup);
  registerBackupChurn(backup);
  registerBackupReconcile(backup);
  registerBackupRepair(backup);
  registerBackupCheck(backup);
  registerBackupTocKey(backup);
}

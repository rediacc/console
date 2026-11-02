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
import { getOutputFormat, handleError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef, resolveRepoRefLocal } from '../utils/repo-target.js';
import { registerBackupReconcile } from './backup-reconcile.js';
import { registerBackupRetention, registerBackupSnapshots } from './backup-retention-commands.js';
import { RENET_NO_LISTING_EXIT, resolveLineage, runBrowseAt } from './backup-storage-browse.js';
import { isLiveMountListing, parseBrowseResult } from './backup-storage-parser.js';
import { registerBackupSnapshot } from './backup-storage-snapshot.js';

/** GET /backups/usage, subscription aggregate + per-lineage breakdown. */
interface BackupUsageResponse {
  subscriptionId: string;
  storedBytes: number;
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
    chunkCount: number;
    logicalBytes: number;
    updatedAt: string;
  }[];
}

/** GET /backups/manifests, the server-side snapshot index. */
interface BackupManifestEntry {
  snapshotId: string;
  lineageGuid: string;
  streamId: string;
  parentSnapshotId?: string;
  cellSizeBytes: number;
  totalBytes: number;
  addedBytes: number;
  addedChunkCount: number;
  hasIndex?: boolean;
  createdAt: string;
}
/**
 * Exported because `backup restore --at` resolves a TIME against this same
 * index (backup.ts::resolveSnapshotAt). One declaration, not two: a
 * hand-written twin of a wire shape is how the two sides drift apart while both
 * stay green.
 */
export interface BackupManifestsResponse {
  manifests: BackupManifestEntry[];
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
          `Used ${formatSizeBytes(usage.usedBytes)} of ${formatSizeBytes(usage.quotaBytes)}` +
            ` (stored ${formatSizeBytes(usage.storedBytes)}, leased ${formatSizeBytes(usage.leasedBytes)}` +
            `, ${usage.chunkCount} chunks)${usage.overLimit ? '  OVER LIMIT' : ''}`
        );

        if (usage.lineages.length === 0) {
          outputService.print(t('commands.backup.usage.empty'));
          return;
        }

        const resolve = createGuidResolver(await loadGuidMap());
        const rows = usage.lineages
          .map((l) => ({
            repo: resolve(l.lineageGuid),
            lineage: l.lineageGuid,
            stored: formatSizeBytes(l.storedBytes),
            logical: formatSizeBytes(l.logicalBytes),
            chunks: l.chunkCount,
            updated: l.updatedAt.replace('T', ' ').replace(/\..*$/, ''),
          }))
          .sort((a, b) => a.repo.localeCompare(b.repo));

        const columns = [
          { key: 'repo', header: 'Repo' },
          { key: 'lineage', header: 'Lineage' },
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

/** `backup manifests [repo-ref]`, the server snapshot index, optionally scoped. */
function registerBackupManifests(backup: Command): void {
  backup
    .command('manifests')
    .argument('[repo-ref]', t('options.repoRef'))
    .description(t('commands.backup.manifests.description'))
    .action(async (repoRef: string | undefined) => {
      try {
        // Scope to one lineage (grand GUID) when a repo is named. Config-local resolution only, the index lives on the server, not on a machine.
        const lineage = repoRef ? await resolveLineage(repoRef) : undefined;

        assertHostedBackupAccount();
        outputService.info(t('commands.backup.manifests.fetching'));
        const query = lineage ? `?lineage=${encodeURIComponent(lineage)}` : '';
        const result = await accountServerFetch<BackupManifestsResponse>(
          `/account/api/v1/backups/manifests${query}`
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
        }));

        const columns = [
          { key: 'repo', header: 'Repo' },
          { key: 'snapshot', header: 'Snapshot' },
          { key: 'id', header: 'Id' },
          { key: 'parent', header: 'Parent' },
          { key: 'total', header: 'Total', align: 'right' as const },
          { key: 'added', header: 'Added / chunks', align: 'right' as const },
          { key: 'index', header: 'Index' },
        ];
        outputService.print(outputService.format(rows, format, columns));
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
    .option('--debug', t('options.debug'))
    .action(
      async (
        repoRef: string,
        options: {
          path?: string;
          depth?: string;
          limit?: string;
          at?: string;
          debug?: boolean;
        }
      ) => {
        try {
          const { repoKey, machineName } = await resolveRepoRef(repoRef);
          let snapshotId = '';
          let result: Awaited<ReturnType<typeof executeRepoFunction>>;
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
                limit: options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT,
              },
              // captureOutput for the same reason as backup verify: the listing IS the answer, and without it the step detector drops the verb's JSON and browse exits 0 with EMPTY stdout.
              { debug: options.debug, captureOutput: true },
              {
                starting: t('commands.backup.browse.starting', { name: repoKey }),
                completed: t('commands.backup.browse.completed', { name: repoKey }),
                failed: t('commands.backup.browse.failed', { name: repoKey }),
              }
            );
          }

          // Exit 18: the snapshot has no stored listing (an older snapshot, or one taken without a listing). A distinct code, as with 16, so a script can tell "no listing there" from "it broke".
          if (options.at && result.exitCode === RENET_NO_LISTING_EXIT) {
            outputService.warn(
              t('commands.backup.browse.noListing', { name: repoKey, snapshot: snapshotId })
            );
            setExitCode(RENET_NO_LISTING_EXIT);
            return;
          }

          // executeRepoFunction already rendered the failure (envelope and exit code).
          // Falling through would throw "no listing" and print a SECOND envelope, so stdout would stop being one JSON document.
          if (!result.success) return;
          const listing = parseBrowseResult(result.stdout);
          if (!listing) {
            throw new Error(`browse returned no listing for "${repoKey}"`);
          }
          // A listing walked from the live mount (a repository with no autostart keyfile) can differ slightly from the stored image, and the operator is told so before reading it.
          if (options.at && isLiveMountListing(listing)) {
            outputService.warn(
              t('commands.backup.browse.liveMountListing', { snapshot: snapshotId })
            );
          }
          if (listing.entries.length === 0) {
            outputService.info(t('commands.backup.browse.empty', { name: repoKey }));
            return;
          }

          const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
          const rows = listing.entries.map((e) => ({
            name: e.path,
            type: e.type,
            size: e.type === 'file' ? formatSizeBytes(e.size) : '-',
            modified: e.modTime.replace('T', ' ').replace(/\..*$/, ''),
          }));
          // Columns are name/type/size/modified, byte-for-byte what the retired `storage browse` produced, so an operator who lost that verb gets the same shape back rather than a new one to learn.
          outputService.print(
            outputService.format(rows, getOutputFormat(), [
              { key: 'name', header: 'Name' },
              { key: 'type', header: 'Type' },
              { key: 'size', header: 'Size', align: 'right' as const },
              { key: 'modified', header: 'Modified' },
            ])
          );
          // A truncated listing that does not say so is how somebody concludes a file is absent from a backup when it is present.
          if (listing.truncated) {
            outputService.warn(
              t('commands.backup.browse.truncated', {
                limit: options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT,
              })
            );
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}

/** POST /backups/verify, level `chunks`: one capped page of the lineage's re-hashed chunks. */
interface BackupChunkVerifyResponse {
  subscriptionId: string;
  chunks: {
    lineageGuid: string;
    checked: number;
    missing: string[];
    corrupt: string[];
    nextAfter: string | null;
  };
}

/** The `backup verify --store` verdict: every referenced chunk of the lineage, re-hashed by the server. */
export interface StoreVerifyVerdict {
  lineageGuid: string;
  checked: number;
  missing: string[];
  corrupt: string[];
}

/**
 * Walk the server's chunk verify for one lineage, page by page, until the
 * cursor runs out. Each page re-hashes at most the server's cap
 * (BACKUP_VERIFY_CHUNKS_MAX), so a large lineage is many requests.
 */
export async function runStoreVerify(lineageGuid: string): Promise<StoreVerifyVerdict> {
  assertHostedBackupAccount();
  const verdict: StoreVerifyVerdict = { lineageGuid, checked: 0, missing: [], corrupt: [] };
  let after: string | undefined;
  const sent = new Set<string>();
  for (;;) {
    const page = await accountServerFetch<BackupChunkVerifyResponse>(
      '/account/api/v1/backups/verify',
      { method: 'POST', body: { lineageGuid, level: 'chunks', after } }
    );
    verdict.checked += page.chunks.checked;
    verdict.missing.push(...page.chunks.missing);
    verdict.corrupt.push(...page.chunks.corrupt);
    if (!page.chunks.nextAfter) return verdict;
    // A cursor already sent, the last one or any earlier (A, B, A), would loop forever on a misbehaving server.
    if (sent.has(page.chunks.nextAfter) || page.chunks.nextAfter === after) {
      throw new Error(`backup verify --store: the server repeated cursor ${page.chunks.nextAfter}`);
    }
    after = page.chunks.nextAfter;
    sent.add(after);
  }
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
    .option('--debug', t('options.debug'))
    .action(
      async (repoRef: string, options: { deep?: boolean; store?: boolean; debug?: boolean }) => {
        try {
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
                  planStep('reportVerifyVerdict', { level }),
                  planStep('recordBackupRun', {
                    repo: repoKey,
                    kind: 'verify',
                    status: 'verified',
                  }),
                  planStep('recordBackupRunFailed', {
                    repo: repoKey,
                    kind: 'verify',
                    status: 'mismatch',
                  }),
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

/** Register the chunk-store backup reads + verification under `rdc backup`. */
export function registerBackupStorageCommands(backup: Command): void {
  registerBackupUsage(backup);
  registerBackupManifests(backup);
  registerBackupVerify(backup);
  registerBackupBrowse(backup);
  registerBackupSnapshot(backup);
  registerBackupRetention(backup);
  registerBackupSnapshots(backup);
  registerBackupReconcile(backup);
}

/** Helpers for `backup browse --at` and the lineage a repo record belongs to, split out of backup-storage.ts. */

import { BACKUP_BROWSE_DEFAULTS } from '@rediacc/shared/config/defaults';
import { t } from '../i18n/index.js';
import {
  executeWithStoreFallback,
  pickStores,
  storeParam,
} from '../services/backup/backup-store-pick.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRefLocal } from '../utils/repo-target.js';
import { isLiveMountListing, parseBrowseResult } from './backup-storage-parser.js';

/** The renet `backup browse-at` and `restore-path` verbs exit 18 when the snapshot's listing cannot serve the request. Propagated verbatim, like the quota refusal's 16. */
export const RENET_NO_LISTING_EXIT = 18;

/** The lineage (grand) GUID of a repo record: a fork shares its parent's lineage. */
export function lineageOf(repo: { grandGuid?: string; repositoryGuid: string }): string {
  return repo.grandGuid ?? repo.repositoryGuid;
}

/**
 * The lineage (grand) GUID a repo ref belongs to. ONE implementation, shared by
 * `manifests` and `retention`: both address the server-side index by lineage,
 * and a second copy of this resolution is how the two commands would come to
 * disagree about which repo the operator named.
 */
export async function resolveLineage(repoRef: string): Promise<string> {
  const { repoKey } = await resolveRepoRefLocal(repoRef);
  const repo = await configService.getRepository(repoKey);
  if (!repo) {
    throw new Error(`Repository "${repoKey}" not found in this config.`);
  }
  return lineageOf(repo);
}

/**
 * `backup browse --at`: list a stored snapshot from the chunk store instead of the
 * mounted image. Resolves the time or snapshot id to a snapshot id inside each store it
 * tries, then runs the renet `backup_browse_at` verb, which reads that listing object.
 */
export async function runBrowseAt(
  repoKey: string,
  machineName: string,
  at: string,
  options: { path?: string; depth?: string; limit?: string; from?: string; debug?: boolean }
): Promise<{ result: Awaited<ReturnType<typeof executeRepoFunction>>; snapshotId: string }> {
  const repo = await configService.getRepository(repoKey);
  if (!repo) {
    throw new Error(`Repository "${repoKey}" not found in this config.`);
  }
  if (!repo.credential) {
    throw new ValidationError(t('commands.backup.browse.atNeedsCredential', { name: repoKey }));
  }
  const lineage = lineageOf(repo);
  // Dynamic: backup.ts statically imports backup-storage.ts, which imports this file, so a static import back would close a cycle.
  const { resolveSnapshotAt } = await import('./backup.js');
  // A store that fails for its own reasons (a 5xx, a refused grant) hands the listing to the next ranked one, and each store tried resolves the time inside itself.
  const pick = await pickStores(lineage, options.from);
  const failedMessage = t('commands.backup.browse.failed', { name: repoKey });
  const { result, snapshotId } = await executeWithStoreFallback(
    pick,
    // A listing is read from the snapshot, so a time with no listing falls back to the nearest one that has it.
    (store) => resolveSnapshotAt(lineage, at, { anyStream: true }, { indexed: true, store }),
    (store, snapshotId) =>
      executeRepoFunction(
        'backup_browse_at',
        repoKey,
        machineName,
        {
          lineage,
          at: snapshotId,
          path: options.path ?? '',
          depth: options.depth ?? BACKUP_BROWSE_DEFAULTS.DEPTH,
          limit: options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT,
          ...storeParam(store),
        },
        {
          debug: options.debug,
          captureOutput: true,
          failureIsAnswer: true,
          job: {
            verb: 'backup browse',
            steps: [
              planStep('renderBackupBrowse', {
                repo: repoKey,
                snapshot: snapshotId,
                limit: options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT,
              }),
            ],
          },
        },
        {
          starting: t('commands.backup.browse.startingAt', { name: repoKey, snapshot: snapshotId }),
          completed: t('commands.backup.browse.completed', { name: repoKey }),
          failed: failedMessage,
        }
      ),
    failedMessage
  );
  return { result, snapshotId };
}

/** What the render step needs to say about the job that listed: the repo, the snapshot of `--at`, and the row cap. */
export interface BrowseRenderContext {
  repo: string;
  /** The snapshot id of `--at`; empty for a browse of the live image. */
  snapshot: string;
  limit: string;
}

/**
 * Print the listing a `backup_browse` or `backup_browse_at` job produced. It is the job's `renderBackupBrowse` step, so
 * a ticket handed back early prints nothing half-done, and `rdc job wait` renders it from the spooled output.
 */
export async function renderBrowseListing(
  stdout: string | undefined,
  ctx: BrowseRenderContext
): Promise<void> {
  const listing = parseBrowseResult(stdout);
  if (!listing) {
    throw new Error(`browse returned no listing for "${ctx.repo}"`);
  }
  // A listing walked from the live mount (a repository with no autostart keyfile) can differ slightly from the stored image, and the operator is told so before reading it.
  if (ctx.snapshot && isLiveMountListing(listing)) {
    outputService.warn(t('commands.backup.browse.liveMountListing', { snapshot: ctx.snapshot }));
  }
  if (listing.entries.length === 0) {
    outputService.info(t('commands.backup.browse.empty', { name: ctx.repo }));
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
    outputService.warn(t('commands.backup.browse.truncated', { limit: ctx.limit }));
  }
}

bindStepHandler('renderBackupBrowse', ({ output, params }) =>
  renderBrowseListing(output, {
    repo: String(params.repo),
    snapshot: String(params.snapshot),
    limit: String(params.limit),
  })
);

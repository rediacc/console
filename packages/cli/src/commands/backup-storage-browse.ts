/** Helpers for `backup browse --at` and the lineage a repo record belongs to, split out of backup-storage.ts. */

import { BACKUP_BROWSE_DEFAULTS } from '@rediacc/shared/config/defaults';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { ValidationError } from '../utils/errors.js';
import { executeRepoFunction } from '../utils/repo-executor.js';

/** The lineage (grand) GUID of a repo record: a fork shares its parent's lineage. */
export function lineageOf(repo: { grandGuid?: string; repositoryGuid: string }): string {
  return repo.grandGuid ?? repo.repositoryGuid;
}

/**
 * `backup browse --at`: list a stored snapshot from the chunk store instead of the
 * mounted image. Resolves the time or snapshot id to a snapshot id first, then runs
 * the renet `backup_browse_at` verb, which reads the snapshot's listing object.
 */
export async function runBrowseAt(
  repoKey: string,
  machineName: string,
  at: string,
  options: { path?: string; depth?: string; limit?: string; debug?: boolean }
): Promise<{ result: Awaited<ReturnType<typeof executeRepoFunction>>; snapshotId: string }> {
  const repo = await configService.getRepository(repoKey);
  if (!repo) {
    throw new Error(`Repository "${repoKey}" not found in this config.`);
  }
  if (!repo.credential) {
    throw new ValidationError(t('commands.backup.browse.atNeedsCredential', { name: repoKey }));
  }
  const lineage = lineageOf(repo);
  // Dynamic: backup.ts statically imports this file.
  const { resolveSnapshotAt } = await import('./backup.js');
  const snapshotId = await resolveSnapshotAt(lineage, at);
  const result = await executeRepoFunction(
    'backup_browse_at',
    repoKey,
    machineName,
    {
      lineage,
      at: snapshotId,
      path: options.path ?? '',
      depth: options.depth ?? BACKUP_BROWSE_DEFAULTS.DEPTH,
      limit: options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT,
    },
    { debug: options.debug, captureOutput: true },
    {
      starting: t('commands.backup.browse.startingAt', { name: repoKey, snapshot: snapshotId }),
      completed: t('commands.backup.browse.completed', { name: repoKey }),
      failed: t('commands.backup.browse.failed', { name: repoKey }),
    }
  );
  return { result, snapshotId };
}

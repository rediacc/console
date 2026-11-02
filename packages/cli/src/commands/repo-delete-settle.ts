/**
 * What a successful `repo delete` does to the config entry and to the repository's cloud backups,
 * split out of repo-create-delete.ts.
 */

import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { purgeLineageRounds } from './backup-purge.js';

export type DeletedRepoConfig = {
  repositoryGuid: string;
  grandGuid?: string;
  pushState?: Record<string, unknown>;
};

/** A fork carries a grand lineage distinct from its own GUID. */
export function isFork(repoConfig: DeletedRepoConfig): boolean {
  return !!repoConfig.grandGuid && repoConfig.grandGuid !== repoConfig.repositoryGuid;
}

/**
 * Machines other than the one just deleted from that hold a pushed copy, as
 * recorded by `repo push` in `pushState`. A repo lives on its placement machine
 * only; the push record is the sole evidence of another holder.
 */
function otherHolders(repoConfig: DeletedRepoConfig, machineName: string): string[] {
  return Object.keys(repoConfig.pushState ?? {}).filter((m) => m !== machineName);
}

/**
 * Settle the config entry after a successful delete and say what happened. The
 * message matches the outcome: archived (moved), dropped (a fork with no other
 * holder, its credential is the parent's so nothing is lost), or retained with
 * the true reason (pushed copies elsewhere, or a grand repo whose credential
 * backups restore with).
 */
export async function settleConfigEntry(
  name: string,
  machineName: string,
  repoConfig: DeletedRepoConfig,
  archiveConfig: boolean
): Promise<void> {
  // A fork with no other holder is archived like --archive-config rather than removed: the name is free for a re-fork, and the archived record keeps the repository GUID that a restore of the fork's backups needs.
  const holders = otherHolders(repoConfig, machineName);
  if (archiveConfig || (holders.length === 0 && isFork(repoConfig))) {
    await configService.archiveRepository(name);
    outputService.info(t('commands.repo.delete.archived', { repository: name }));
    outputService.info(t('commands.repo.delete.restoreHint', { guid: repoConfig.repositoryGuid }));
    return;
  }
  if (holders.length > 0) {
    outputService.info(
      t('commands.repo.delete.configRetainedElsewhere', {
        repository: name,
        machines: holders.join(', '),
      })
    );
  } else {
    outputService.info(t('commands.repo.delete.configRetained', { repository: name }));
  }
  outputService.info(t('commands.repo.delete.archiveHint', { repository: name }));
}

/**
 * What `repo delete` does to the repository's cloud backups (plan F8).
 *
 * Default: the lineage is marked orphaned on the server, which keeps its newest snapshots for the
 * orphan window and then expires them. `--purge-backups` deletes them now. A fork shares its
 * parent's lineage, so a fork delete leaves the lineage alone, and a purge for one is refused
 * before anything is deleted.
 */
export async function settleCloudBackups(
  name: string,
  repoConfig: DeletedRepoConfig,
  purgeBackups: boolean
): Promise<void> {
  if (isFork(repoConfig)) return;
  const lineage = repoConfig.grandGuid ?? repoConfig.repositoryGuid;
  const path = `/account/api/v1/backups/lineages/${encodeURIComponent(lineage)}`;
  if (purgeBackups) {
    const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
    const purged = await purgeLineageRounds(name, lineage, formatSizeBytes);
    outputService.info(
      t('commands.repo.delete.backupsPurged', {
        repository: name,
        count: purged.deletedSnapshots,
        bytes: formatSizeBytes(purged.freedBytes),
      })
    );
    return;
  }
  // No account token means no cloud backups were ever possible from this config: nothing to orphan, nothing to say.
  if (getSubscriptionTokenState().kind !== 'ready') return;
  try {
    const orphan = await accountServerFetch<{ orphanExpiresAt: string }>(`${path}/orphan`, {
      method: 'POST',
    });
    outputService.info(
      t('commands.repo.delete.backupsOrphaned', {
        repository: name,
        expires: orphan.orphanExpiresAt.slice(0, 10),
      })
    );
  } catch (error) {
    outputService.warn(
      t('commands.repo.delete.backupsOrphanFailed', {
        repository: name,
        reason: error instanceof Error ? error.message : String(error),
      })
    );
  }
}

/**
 * Tell the account server the deleted repository's license is retired, so its license summary stops
 * counting it. Best effort: a failure warns and never fails the delete.
 */
export async function settleRepoLicense(
  name: string,
  repoConfig: DeletedRepoConfig
): Promise<void> {
  // No account token means no license was ever issued from this config: nothing to retire, nothing to say.
  if (getSubscriptionTokenState().kind !== 'ready') return;
  try {
    await accountServerFetch(
      `/account/api/v1/licenses/repos/${encodeURIComponent(repoConfig.repositoryGuid)}/retire`,
      { method: 'POST' }
    );
  } catch (error) {
    outputService.warn(
      t('commands.repo.delete.licenseRetireFailed', {
        repository: name,
        reason: error instanceof Error ? error.message : String(error),
      })
    );
  }
}

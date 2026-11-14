import type { ArchivedRepository, RepositoryConfig } from '../../types/index.js';
import {
  assertNoCredentialCollision,
  assertRestoredForkKeyIsExplicit,
  restoreArchivedRecord,
} from './config-resources-resolve.js';

/**
 * Move the archived record with `guid` back into `repos` under `name` (default: its archived name),
 * removing it from `deletedRepos`. Both collections are mutated; the caller persists them.
 * Returns the name the repository is live under.
 */
export function takeArchivedRepository(
  repos: Record<string, RepositoryConfig>,
  deletedRepos: ArchivedRepository[],
  guid: string,
  name?: string
): string {
  const index = deletedRepos.findIndex((r) => r.repositoryGuid === guid);
  if (index === -1) throw new Error(`Archived repository with GUID "${guid}" not found`);

  const archived = deletedRepos[index];
  const restoredName = name ?? archived.name;
  assertRestoredForkKeyIsExplicit(archived, restoredName);

  if (restoredName in repos)
    throw new Error(
      `Repository "${restoredName}" already exists. Use --name to specify a different name.`
    );
  const repoConfig = restoreArchivedRecord(archived);
  // This write bypasses addRepository, but the record it makes LIVE is subject to the same GUID-keyed credential map.
  assertNoCredentialCollision(repos, restoredName, repoConfig);
  repos[restoredName] = repoConfig;

  deletedRepos.splice(index, 1);
  return restoredName;
}

/**
 * How long an archived record is kept before an archive write drops it: the account server's
 * BACKUP_ORPHAN_RETENTION_DAYS (private/account/src/services/backup-gc.service.ts). A deleted
 * repository's lineage is orphaned on delete and deleted whole after that window, so past it the
 * archived credential decrypts nothing the server still holds, and the image's prune grace
 * (`defaults.pruneGraceDays`, 7 days) is long over. `rdc config prune` still expires sooner.
 */
export const ARCHIVE_RETENTION_DAYS = 90;

/** The newest fork records an archive write keeps per repository name. */
export const ARCHIVED_FORKS_PER_NAME = 10;

const MS_PER_DAY = 24 * 60 * 60 * 1000;

function isForkRecord(record: ArchivedRepository): boolean {
  return !!record.grandGuid && record.grandGuid !== record.repositoryGuid;
}

/**
 * The archive after an archive write, bounded so a repeated fork/delete or create/delete cycle cannot grow it without limit (vm:check left 663 records named `vmcheck-base` in one config).
 *
 * The archive exists so `config repository restore <guid>` can bring a record back, and so a backup taken before the delete stays decryptable: what a restore needs is the GUID plus the LUKS credential. Records are keyed by GUID, and every create and fork mints a new one, so a repeat never replaces an older record and deduping by GUID bounds nothing. Two rules bound it:
 *
 * - Any record older than ARCHIVE_RETENTION_DAYS is dropped (see there for why nothing a restore can use is lost).
 * - Fork records beyond the newest ARCHIVED_FORKS_PER_NAME per repository name are dropped. A fork's credential is its parent's (repo-fork.ts registers it so), so no key material goes with it, and a fork's backups ride the parent's lineage (repo-delete-settle.ts settleCloudBackups), which the parent's own record keeps. Grand records are never capped by count: each holds the only copy of a credential its orphaned backups need.
 *
 * A record with an unparseable `deletedAt` is kept. Order is preserved. `rdc config prune --gone-machine-repos` does not apply this: its buckets are selected one by one, and archive expiry belongs to the archives bucket.
 */
export function boundArchive(
  records: ArchivedRepository[],
  now: number = Date.now()
): ArchivedRepository[] {
  const cutoff = now - ARCHIVE_RETENTION_DAYS * MS_PER_DAY;
  const fresh = records.filter((r) => !(Date.parse(r.deletedAt) < cutoff));
  const forksByName = new Map<string, ArchivedRepository[]>();
  for (const record of fresh) {
    // An unparseable deletedAt has no age to rank by, so the record is kept rather than counted toward the cap.
    if (!isForkRecord(record) || Number.isNaN(Date.parse(record.deletedAt))) continue;
    const list = forksByName.get(record.name) ?? [];
    list.push(record);
    forksByName.set(record.name, list);
  }
  const dropped = new Set<ArchivedRepository>();
  for (const list of forksByName.values()) {
    // Newest first; records archived in the same millisecond rank by list position, later appended being newer.
    const newestFirst = list
      .map((record, index) => ({ record, index, at: Date.parse(record.deletedAt) }))
      .sort((a, b) => b.at - a.at || b.index - a.index)
      .map((entry) => entry.record);
    for (const record of newestFirst.slice(ARCHIVED_FORKS_PER_NAME)) dropped.add(record);
  }
  return fresh.filter((r) => !dropped.has(r));
}

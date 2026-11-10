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

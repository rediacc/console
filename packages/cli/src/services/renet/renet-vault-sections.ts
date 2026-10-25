export interface RepoEntryConfig {
  guid: string;
  name: string;
  networkId?: number;
  /** The family's grand GUID; absent or equal to `guid` on a grand. */
  grandGuid?: string;
  /**
   * File-mode secrets to materialize on the host at deploy time. Renet's
   * repository_up reads these from the vault payload and writes them to
   * /var/run/rediacc/net-<networkID>/secrets/<NAME>. Tmpfs only; never enters
   * the LUKS image; never inherited by forks.
   */
  secretFiles?: { name: string; value: string }[];
}

const GUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** A bare family name addresses the family's grand, whatever tag the grand is stored under. */
function findGrandByBareName(
  bareName: string,
  repositoryConfigs: Record<string, RepoEntryConfig>
): RepoEntryConfig | undefined {
  return Object.entries(repositoryConfigs).find(
    ([key, config]) =>
      key.split(':')[0] === bareName && (!config.grandGuid || config.grandGuid === config.guid)
  )?.[1];
}

/** A repo ref resolves to its config entry by key, then by GUID; a ref that is itself a GUID needs no entry. */
function findRepoConfig(
  repoRef: string,
  repositoryConfigs?: Record<string, RepoEntryConfig>
): RepoEntryConfig | undefined {
  if (!repositoryConfigs) return undefined;
  return (
    repositoryConfigs[repoRef] ??
    Object.values(repositoryConfigs).find((config) => config.guid === repoRef) ??
    findGrandByBareName(repoRef, repositoryConfigs)
  );
}

/** The GUID a single-repo verb addresses: config entry, else the caller's guid param, else a ref that is itself a GUID. A bare name is never promoted to a GUID. */
function resolveRepoGuid(
  repoRef: string,
  params: Record<string, unknown>,
  repoConfig: RepoEntryConfig | undefined
): string {
  if (repoConfig) return repoConfig.guid;
  if (typeof params.guid === 'string' && params.guid !== '') return params.guid;
  if (GUID_PATTERN.test(repoRef)) return repoRef;
  throw new Error(
    `Repository "${repoRef}" has no GUID in the active config; refusing to use the name as the GUID`
  );
}

/** Build a single repository entry from config and params, keyed by GUID with the friendly name as `name`. */
function buildSingleRepoEntry(
  repoGuid: string,
  repoName: string,
  params: Record<string, unknown>,
  repoConfig: RepoEntryConfig | undefined
): Record<string, unknown> {
  const repoEntry: Record<string, unknown> = {
    guid: repoGuid,
    name: repoName,
  };
  const networkId = repoConfig?.networkId ?? params.network_id;
  if (networkId !== undefined && networkId !== '' && networkId !== 0) {
    repoEntry.network_id = typeof networkId === 'number' ? networkId : Number(networkId);
  }
  if (repoConfig?.secretFiles && repoConfig.secretFiles.length > 0) {
    repoEntry.secret_files = repoConfig.secretFiles;
  }
  return repoEntry;
}

/** Build repository entries for all repos in config (multi-repo mode). */
function buildAllRepoEntries(
  repositoryConfigs: Record<string, RepoEntryConfig>
): Record<string, unknown> {
  const repositories: Record<string, unknown> = {};
  for (const [name, config] of Object.entries(repositoryConfigs)) {
    const repoEntry: Record<string, unknown> = {
      guid: config.guid,
      name,
    };
    if (config.networkId !== undefined && config.networkId !== 0) {
      repoEntry.network_id = config.networkId;
    }
    if (config.secretFiles && config.secretFiles.length > 0) {
      repoEntry.secret_files = config.secretFiles;
    }
    repositories[name] = repoEntry;
  }
  return repositories;
}

/**
 * `repoGuid` is the vault's `task.repository`; `repoName` is the friendly name the caller passed, carried as `task.repo_name` and the entry's `name`.
 */
export function buildRepositories(
  params: Record<string, unknown>,
  repositoryConfigs?: Record<string, RepoEntryConfig>
): { repoGuid: string; repoName: string; repositories: Record<string, unknown> } {
  const repoRef = (params.repository ?? '') as string;

  if (repoRef) {
    const repoConfig = findRepoConfig(repoRef, repositoryConfigs);
    const repoGuid = resolveRepoGuid(repoRef, params, repoConfig);
    const repoName = repoConfig?.name ?? repoRef;
    return {
      repoGuid,
      repoName,
      repositories: {
        [repoGuid]: buildSingleRepoEntry(repoGuid, repoName, params, repoConfig),
      },
    };
  }

  if (repositoryConfigs) {
    return { repoGuid: '', repoName: '', repositories: buildAllRepoEntries(repositoryConfigs) };
  }

  return { repoGuid: '', repoName: '', repositories: {} };
}

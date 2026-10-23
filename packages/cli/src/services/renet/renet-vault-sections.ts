export interface RepoEntryConfig {
  guid: string;
  name: string;
  networkId?: number;
  /**
   * File-mode secrets to materialize on the host at deploy time. Renet's
   * repository_up reads these from the vault payload and writes them to
   * /var/run/rediacc/net-<networkID>/secrets/<NAME>. Tmpfs only; never enters
   * the LUKS image; never inherited by forks.
   */
  secretFiles?: { name: string; value: string }[];
}

function buildStorageSection(vault: Record<string, unknown>): Record<string, unknown> | null {
  const provider = String(vault.provider ?? '');
  if (!provider) return null;

  const section: Record<string, unknown> = { backend: provider };
  if (vault.bucket) section.bucket = String(vault.bucket);
  if (vault.region) section.region = String(vault.region);
  if (vault.folder !== undefined && vault.folder !== null) {
    section.folder = String(vault.folder);
  }

  const parameters: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(vault)) {
    if (['provider', 'bucket', 'region', 'folder'].includes(key)) continue;
    parameters[key] = value;
  }
  if (Object.keys(parameters).length > 0) {
    section.parameters = parameters;
  }

  return section;
}

export function buildStorageSystems(
  storages: Record<string, { vaultContent: Record<string, unknown> }> | undefined
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  if (!storages) return result;
  for (const [name, storage] of Object.entries(storages)) {
    const section = buildStorageSection(storage.vaultContent);
    if (section) result[name] = section;
  }
  return result;
}

/** Build a single repository entry from config and params. */
function buildSingleRepoEntry(
  repoName: string,
  params: Record<string, unknown>,
  repositoryConfigs?: Record<string, RepoEntryConfig>
): Record<string, unknown> {
  const repoConfig = repositoryConfigs?.[repoName];
  const repoEntry: Record<string, unknown> = {
    guid: repoConfig?.guid ?? (typeof params.guid === 'string' ? params.guid : repoName),
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

export function buildRepositories(
  params: Record<string, unknown>,
  repositoryConfigs?: Record<string, RepoEntryConfig>
): { repoName: string; repositories: Record<string, unknown> } {
  const repoName = (params.repository ?? '') as string;

  if (repoName) {
    return {
      repoName,
      repositories: { [repoName]: buildSingleRepoEntry(repoName, params, repositoryConfigs) },
    };
  }

  if (repositoryConfigs) {
    return { repoName, repositories: buildAllRepoEntries(repositoryConfigs) };
  }

  return { repoName, repositories: {} };
}

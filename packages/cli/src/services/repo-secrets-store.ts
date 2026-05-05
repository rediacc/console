/**
 * Per-repo secrets storage primitives.
 *
 * Plain functions over a ResourceState-shaped object. Kept out of
 * config-resources.ts so that file stays under the 512-line cap. The
 * configService class methods are thin wrappers that look up the repo
 * key and delegate here.
 *
 * Mutation gating (--current digest, agent allowlist) lives at the
 * command layer (commands/repo-secret.ts), not here — these helpers
 * just touch the in-memory map and persist via setRepositories.
 */

import type { RepositoryConfig, SecretEntry, SecretMode } from '../types/index.js';

interface ResourceStateLike {
  getRepositories(): Record<string, RepositoryConfig>;
  setRepositories(next: Record<string, RepositoryConfig>): Promise<void>;
}

/** Read a single secret, or undefined if absent. */
export function readRepositorySecret(
  repo: RepositoryConfig | undefined,
  key: string
): SecretEntry | undefined {
  return repo?.secrets?.[key];
}

/** Return secret keys + modes (never values), sorted alphabetically. */
export function listRepositorySecretKeyModes(
  repo: RepositoryConfig | undefined
): { key: string; mode: SecretMode }[] {
  if (!repo?.secrets) return [];
  return Object.entries(repo.secrets)
    .map(([key, entry]) => ({ key, mode: entry.mode }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

/** Set or overwrite a secret on the named repo. */
export async function writeRepositorySecret(
  state: ResourceStateLike,
  repoKey: string,
  key: string,
  entry: SecretEntry
): Promise<void> {
  const repos = state.getRepositories();
  const repo = repos[repoKey];
  repo.secrets = { ...(repo.secrets ?? {}), [key]: entry };
  await state.setRepositories(repos);
}

/** Remove a secret. Throws if the key does not exist. */
export async function deleteRepositorySecret(
  state: ResourceStateLike,
  repoRef: string,
  repoKey: string,
  key: string
): Promise<void> {
  const repos = state.getRepositories();
  const repo = repos[repoKey];
  if (!repo.secrets || !(key in repo.secrets)) {
    throw new Error(`Secret "${key}" not found on repository "${repoRef}"`);
  }
  const next = { ...repo.secrets };
  delete next[key];
  repo.secrets = Object.keys(next).length > 0 ? next : undefined;
  await state.setRepositories(repos);
}

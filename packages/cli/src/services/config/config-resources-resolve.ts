/**
 * Strict destructive-target resolution for repo destructive commands
 * (`repo delete`, `repo promote`, `config repository remove`). See issue
 * #495. The resolver fails closed on bare-ref ambiguity so destructive
 * commands cannot silently target a fork registered under the grand's slot.
 *
 * Kept as a separate module so the resolver logic stays small and testable
 * and `config-resources.ts` stays under its max-lines budget.
 */

import type { ArchivedRepository, RepositoryConfig } from '../../types/index.js';
import { parseRepoRef, RESERVED_GRAND_TAG } from '../../utils/config-schema.js';

/** A repository whose base name matches an operator's `--name` query. */
export interface RepoCandidate {
  key: string;
  kind: 'grand' | 'fork';
  guid: string;
}

/**
 * Thrown when a bare `--name` matches more than one config key (e.g. grand +
 * fork share the base name). Destructive commands surface this to force the
 * operator to supply an explicit `<name>:<tag>`.
 */
export class AmbiguousRepoTargetError extends Error {
  candidates: RepoCandidate[];
  constructor(ref: string, candidates: RepoCandidate[]) {
    const lines = candidates
      .map((c) => `  - ${c.key}  (${c.kind}; guid=${c.guid.slice(0, 8)})`)
      .join('\n');
    super(
      `"${ref}" is ambiguous — multiple repositories share this base name:\n${lines}\nRe-run with an explicit --name <name>:<tag> to target one.`
    );
    this.name = 'AmbiguousRepoTargetError';
    this.candidates = candidates;
  }
}

/** Collect every config entry that shares the given base repo name. */
function collectCandidates(
  repos: Record<string, RepositoryConfig>,
  baseName: string
): RepoCandidate[] {
  const out: RepoCandidate[] = [];
  for (const [key, cfg] of Object.entries(repos)) {
    if (parseRepoRef(key).name !== baseName) continue;
    const isFork = !!(cfg.grandGuid && cfg.grandGuid !== cfg.repositoryGuid);
    out.push({ key, kind: isFork ? 'fork' : 'grand', guid: cfg.repositoryGuid });
  }
  return out;
}

/** Same exact-key + `:latest` fallback as `getRepositoryKey`. */
export function resolveExactOrLatest(
  repos: Record<string, RepositoryConfig>,
  ref: string,
  isBare: boolean
): string | undefined {
  if (ref in repos) return ref;
  if (isBare) {
    const latestKey = `${ref}:${RESERVED_GRAND_TAG}`;
    if (latestKey in repos) return latestKey;
  }
  return undefined;
}

/**
 * True iff this config entry is a fork. A fork has a `grandGuid` pointing
 * at a different repository (its production source). A grand repo either
 * lacks `grandGuid` or has it equal to its own `repositoryGuid`.
 */
function isForkConfig(cfg: RepositoryConfig): boolean {
  return !!(cfg.grandGuid && cfg.grandGuid !== cfg.repositoryGuid);
}

/**
 * Build the GUID → canonical "name:tag" map. Config keys may be bare
 * ("erpnext") or composite ("demo:latest"); we always emit the canonical form
 * without double-tagging composite keys.
 */
export function buildGuidMap(repos: Record<string, RepositoryConfig>): Record<string, string> {
  const map: Record<string, string> = {};
  for (const [repoName, repoConfig] of Object.entries(repos)) {
    const tag = repoConfig.tag ?? RESERVED_GRAND_TAG;
    const { name: baseName } = parseRepoRef(repoName);
    map[repoConfig.repositoryGuid] = `${baseName}:${tag}`;
  }
  return map;
}

/**
 * Build the archive record for a repository being deleted.
 *
 * Archives exist to preserve identity (`repositoryGuid` plus the LUKS
 * credential), so a backup taken before the delete stays decryptable. Deploy-time
 * `secrets` are out of scope and are scrubbed here so they cannot survive a
 * delete-then-restore cycle; `ArchivedRepositorySchema.omit({secrets})` mirrors
 * that at the schema layer. Runtime status riding along is harmless: the archive
 * schema strips it on reload.
 */
export function buildArchivedRecord(repoKey: string, rec: RepositoryConfig): ArchivedRepository {
  const colon = repoKey.indexOf(':');
  const base = colon === -1 ? repoKey : repoKey.slice(0, colon);
  const tag = rec.tag ?? (colon === -1 ? RESERVED_GRAND_TAG : repoKey.slice(colon + 1));
  const { secrets: _secrets, ...record } = rec;
  void _secrets;
  return { ...record, name: base, tag, deletedAt: new Date().toISOString() };
}

/**
 * Refuse a second LIVE record that reuses another record's `repositoryGuid`
 * under a DIFFERENT credential.
 *
 * {@link buildCredentialsMap} is keyed by GUID, so such a pair does not fail
 * loudly: one credential silently wins the single map slot for both records and
 * the loser's LUKS image stops unlocking. Which one wins depends on iteration
 * order over the config keys, so the same config is mountable or not depending
 * on the alphabetical position of a name the operator chose.
 *
 * Archived records live in `resources.deletedRepositories`, never in the
 * repositories dict this scans, so they are exempt by construction.
 */
export function assertNoCredentialCollision(
  repos: Record<string, RepositoryConfig>,
  key: string,
  config: RepositoryConfig
): void {
  if (!config.credential) return;
  for (const [otherKey, other] of Object.entries(repos)) {
    if (otherKey === key) continue;
    if (other.repositoryGuid !== config.repositoryGuid) continue;
    if (!other.credential || other.credential === config.credential) continue;
    throw new Error(
      `Cannot register "${key}": it reuses the repositoryGuid of "${otherKey}" ` +
        `(${config.repositoryGuid}) under a different credential. Credentials are ` +
        `keyed by GUID, so one of the two repositories would become unmountable. ` +
        `Give "${key}" the same credential as "${otherKey}", or a GUID of its own.`
    );
  }
}

/**
 * Refuse to restore a fork under a bare `<name>` or `<name>:latest` key —
 * either would shadow / collide with the grand and re-create the #495
 * ambiguity. No-op for non-fork archives.
 */
export function assertRestoredForkKeyIsExplicit(
  archived: { name: string; grandGuid?: string; repositoryGuid: string },
  restoredName: string
): void {
  if (!archived.grandGuid || archived.grandGuid === archived.repositoryGuid) return;
  const { name: base, tag } = parseRepoRef(restoredName);
  if (!restoredName.includes(':') || tag === RESERVED_GRAND_TAG) {
    throw new Error(
      `Cannot restore fork "${archived.name}" under "${restoredName}" — forks must use an explicit non-"latest" tag (e.g. "${base}:restored"). Pass --new-name <name>:<tag>.`
    );
  }
}

/**
 * Strict resolver. Fails closed on ambiguity. Pure: callers pass the
 * already-loaded `repos` dict so this needs no service-state plumbing.
 */
export function resolveDestructiveTargetFromRepos(
  repos: Record<string, RepositoryConfig>,
  repoRef: string
): { key: string; config: RepositoryConfig } {
  const isBare = !repoRef.includes(':');
  const baseName = parseRepoRef(repoRef).name;
  const candidates = collectCandidates(repos, baseName);

  if (isBare && candidates.length > 1) {
    throw new AmbiguousRepoTargetError(repoRef, candidates);
  }

  const resolvedKey = resolveExactOrLatest(repos, repoRef, isBare);
  if (!resolvedKey) {
    if (isBare && candidates.length === 1) {
      throw new Error(
        `Repository "${repoRef}" not found — did you mean "${candidates[0].key}"? Re-run with --name ${candidates[0].key}.`
      );
    }
    throw new Error(`Repository "${repoRef}" not found in context`);
  }

  const resolved = repos[resolvedKey];
  if (isBare && isForkConfig(resolved)) {
    throw new AmbiguousRepoTargetError(repoRef, candidates);
  }
  return { key: resolvedKey, config: resolved };
}

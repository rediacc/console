/**
 * Tristate classification of a repository on a machine.
 *
 * - `grand`: top-level repo, registered in the local CLI config without a
 *   parent (i.e. `grandGuid` empty).
 * - `fork`: a copy-on-write fork of another repo. Identified either via the
 *   local config (`grandGuid` is set) or via the renet `.interim/state`
 *   mirror (`is_fork: true`). Either source is authoritative; both should
 *   agree once the mirror is populated.
 * - `unknown`: not in local config AND no fork-marked mirror. Most often a
 *   pre-mirror orphan (legacy fork created before the mirror code shipped),
 *   or a stale grand whose config entry was deleted. We refuse to guess; the
 *   operator should run the mirror backfill or remove the directory if it's
 *   genuinely orphaned.
 *
 * The decision order is intentional: local config wins over the mirror
 * because the operator's CLI config is the source of truth for "what they
 * intend the repo to be" — the mirror is a server-side observation that's
 * useful as a fallback only when the local registry is silent.
 */
export type RepoTypeClassification = 'grand' | 'fork' | 'unknown';

/** Local-config view of a repo, keyed by GUID. */
export interface ConfigRepoEntry {
  /** Set when the repo is a fork (its parent's GUID). Empty/missing for grand repos. */
  grandGuid?: string;
}

/** Renet-side view of a repo (subset of the `repository_list` payload). */
export interface RenetRepoView {
  /** Mirror-derived flag. Only `true` when the .interim mirror said is_fork=true. */
  is_fork?: boolean;
}

/**
 * Classify a repo as `grand` / `fork` / `unknown` using the operator's local
 * config first, then the renet mirror as fallback. Pass `undefined` for
 * `cfg` when the GUID is not in local config.
 */
export function classifyRepoType(
  renet: RenetRepoView,
  cfg: ConfigRepoEntry | undefined
): RepoTypeClassification {
  if (cfg) {
    return cfg.grandGuid ? 'fork' : 'grand';
  }
  if (renet.is_fork) {
    return 'fork';
  }
  return 'unknown';
}

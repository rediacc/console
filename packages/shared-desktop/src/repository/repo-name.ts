/**
 * Helpers for parsing composite repository names of the form `<parent>:<tag>`.
 * Forked repos use the composite shape (e.g. "gitlab:demo-erp"); grand repos
 * use the bare name.
 *
 * Renet on the machine treats the suffix as REDIACC_REPO_TAG and the prefix
 * as REDIACC_REPO_NAME, so any client-side derivation of either field must
 * round-trip cleanly to the same values.
 */

/** Returns the parent portion of a composite repo name. */
export function parentRepoName(repoName: string): string {
  const idx = repoName.indexOf(':');
  return idx >= 0 ? repoName.slice(0, idx) : repoName;
}

/**
 * Returns the tag portion of a composite repo name, or `fallback` when the
 * input is a bare grand repo name without a colon.
 */
export function repoTagFromName(repoName: string, fallback: string): string {
  const idx = repoName.indexOf(':');
  return idx >= 0 ? repoName.slice(idx + 1) : fallback;
}

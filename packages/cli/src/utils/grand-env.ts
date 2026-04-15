/**
 * Parsing helpers for the REDIACC_ALLOW_GRAND_REPO env var.
 *
 * Accepts one of:
 *   - unset / empty      -> no access
 *   - `*`                -> wildcard (all repos, machine-level access)
 *   - `<repo>`           -> single repo
 *   - `<repo1>,<repo2>`  -> comma-separated list (whitespace around entries trimmed)
 *   - mixed with `*`     -> still wildcard (e.g. `mail,*,web`)
 *
 * Repo-name matching is case-sensitive, matching the historical `===` comparisons.
 */

function parseGrandEnv(raw: string | undefined): { wildcard: boolean; repos: Set<string> } {
  if (!raw) return { wildcard: false, repos: new Set() };
  const parts = raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const wildcard = parts.includes('*');
  const repos = new Set(parts.filter((p) => p !== '*'));
  return { wildcard, repos };
}

/** True if the env grants access to the given repo (wildcard or listed). Case-sensitive. */
export function isRepoAllowedByGrandEnv(repoName: string): boolean {
  const { wildcard, repos } = parseGrandEnv(process.env.REDIACC_ALLOW_GRAND_REPO);
  return wildcard || repos.has(repoName);
}

/** True if any entry is `*`. Used for machine-level gates that a repo list cannot unlock. */
export function isGrandEnvWildcard(): boolean {
  return parseGrandEnv(process.env.REDIACC_ALLOW_GRAND_REPO).wildcard;
}

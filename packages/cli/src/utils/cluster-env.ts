/**
 * Parsing helpers for the REDIACC_ALLOW_CLUSTER_OPS env var.
 *
 * Accepts one of:
 *   - unset / empty         -> no access
 *   - `*`                   -> wildcard (all clusters, including not-yet-created ones)
 *   - `<cluster>`           -> single cluster
 *   - `<cluster1>,<cluster2>` -> comma-separated list (whitespace around entries trimmed)
 *   - mixed with `*`        -> still wildcard (e.g. `prod,*,edge`)
 *
 * Cluster-name matching is case-sensitive, matching the grand-env convention.
 * A name-list entry matches `cluster create` when the target --name matches the
 * entry; `*` covers a create because no cluster exists yet.
 *
 * This is the parser half of the cluster-ops override. Legitimacy (that the
 * operator set the var BEFORE the agent started, not the agent itself) is
 * proven separately by isOverrideLegitimate(OVERRIDE_VAR_CLUSTER).
 */

function parseClusterEnv(raw: string | undefined): { wildcard: boolean; clusters: Set<string> } {
  if (!raw) return { wildcard: false, clusters: new Set() };
  const parts = raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const wildcard = parts.includes('*');
  const clusters = new Set(parts.filter((p) => p !== '*'));
  return { wildcard, clusters };
}

/** True if the env grants access to the given cluster (wildcard or listed). Case-sensitive. */
export function isClusterAllowedByEnv(clusterName: string): boolean {
  const { wildcard, clusters } = parseClusterEnv(process.env.REDIACC_ALLOW_CLUSTER_OPS);
  return wildcard || clusters.has(clusterName);
}

/** True if any entry is `*`. Used for gates a cluster list cannot unlock. */
export function isClusterEnvWildcard(): boolean {
  return parseClusterEnv(process.env.REDIACC_ALLOW_CLUSTER_OPS).wildcard;
}

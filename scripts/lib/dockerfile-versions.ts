/**
 * Parse `ARG <BASE>_VERSION=<version>` pins out of a Dockerfile.
 *
 * The Dockerfile is the single source of truth for the versions of the binaries
 * renet embeds (criu, rsync, rclone, zot, k3s, the CSI sidecars). Two gates read
 * these pins and must agree on how they are parsed, so the parser lives here
 * rather than being copied:
 *   - check-embed-credits.ts   — asserts the pins match embed.go + the credits
 *     inventories (consistency).
 *   - check-embed-asset-freshness.ts — asserts the pins are not stale vs upstream
 *     (freshness).
 *
 * A `_VERSION` ARG commonly appears more than once (once per build stage / arch);
 * every occurrence must carry the same value, which the caller can enforce via
 * the returned `conflicts`.
 */
export interface DockerfileVersions {
  /** base name (lowercased, e.g. "k3s", "csiprovisioner") -> version string */
  versions: Map<string, string>;
  /** human-readable messages for ARGs that disagree with themselves */
  conflicts: string[];
}

export function parseDockerfileVersions(src: string): DockerfileVersions {
  const versions = new Map<string, string>();
  const conflicts: string[] = [];
  const re = /^ARG\s+([A-Z0-9]+)_VERSION=(\S+)/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    const base = m[1].toLowerCase();
    const version = m[2];
    const existing = versions.get(base);
    if (existing !== undefined && existing !== version) {
      conflicts.push(
        `Dockerfile: conflicting ${m[1]}_VERSION values ('${existing}' vs '${version}')`
      );
    }
    versions.set(base, version);
  }
  return { versions, conflicts };
}

/**
 * The embedded-binary inventory: each asset baked into the renet image and
 * where its upstream releases live.
 *
 * Extracted from scripts/check-embed-asset-freshness.ts so the suppression
 * liveness probe can reuse it. That script calls main() at module scope, so it
 * cannot be imported for its constants without running the whole freshness
 * check (network included).
 *
 * `base` matches the Dockerfile `ARG <BASE>_VERSION` key produced by
 * parseDockerfileVersions(), lowercased. snapshotter and snapshot-controller
 * both ship from the one external-snapshotter repo.
 */

export interface EmbedAssetSource {
  /** Dockerfile ARG base, lowercased (matches parseDockerfileVersions keys). */
  base: string;
  display: string;
  kind: 'github' | 'rsync-index';
  /** owner/repo for github sources. */
  repo?: string;
}

export const EMBED_ASSET_SOURCES: EmbedAssetSource[] = [
  { base: 'criu', display: 'CRIU', kind: 'github', repo: 'checkpoint-restore/criu' },
  { base: 'rsync', display: 'rsync', kind: 'rsync-index' },
  { base: 'zot', display: 'zot', kind: 'github', repo: 'project-zot/zot' },
  { base: 'k3s', display: 'k3s', kind: 'github', repo: 'k3s-io/k3s' },
  {
    base: 'csiprovisioner',
    display: 'csi-provisioner',
    kind: 'github',
    repo: 'kubernetes-csi/external-provisioner',
  },
  {
    base: 'csisnapshotter',
    display: 'csi-snapshotter',
    kind: 'github',
    repo: 'kubernetes-csi/external-snapshotter',
  },
  {
    base: 'snapshotcontroller',
    display: 'snapshot-controller',
    kind: 'github',
    repo: 'kubernetes-csi/external-snapshotter',
  },
];

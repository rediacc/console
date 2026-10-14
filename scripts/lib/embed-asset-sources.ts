/**
 * The embedded-binary inventory: each asset baked into the renet image and
 * where its upstream releases live, READ FROM THE PIN REGISTRY.
 *
 * The `embed:<base>` entries of .ci/config/pins.json are the inventory; this
 * module only shapes them for check-embed-asset-freshness.ts and the suppression
 * liveness probe (which is why it stays a separate module: that gate calls main()
 * at module scope, so it cannot be imported for its constants without running the
 * whole freshness check, network included). Adding an asset is one registry
 * entry, and check:ci-pin-registry refuses a Dockerfile ARG no entry claims.
 *
 * `base` matches the Dockerfile `ARG <BASE>_VERSION` key produced by
 * parseDockerfileVersions(), lowercased, and is the part of the registry id after
 * `embed:`. snapshotter and snapshot-controller both ship from the one
 * external-snapshotter repo.
 */
import { entriesFor, idName, loadRegistry, type PinEntry } from './pins/registry.js';

export interface EmbedAssetSource {
  /** Dockerfile ARG base, lowercased (matches parseDockerfileVersions keys). */
  base: string;
  display: string;
  kind: 'github' | 'rsync-index';
  /** owner/repo for github sources. */
  repo?: string;
}

function toSource(e: PinEntry): EmbedAssetSource {
  const base = idName(e);
  if (e.source.type === 'rsync-index') return { base, display: e.name, kind: 'rsync-index' };
  if (e.source.type === 'github-release' && e.source.repo)
    return { base, display: e.name, kind: 'github', repo: e.source.repo };
  throw new Error(
    `.ci/config/pins.json ${e.id}: the embed driver reads a github-release or rsync-index source, not ${e.source.type}`
  );
}

export const EMBED_ASSET_SOURCES: EmbedAssetSource[] = entriesFor(loadRegistry(), 'embed').map(
  toSource
);

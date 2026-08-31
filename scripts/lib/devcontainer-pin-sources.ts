/**
 * The devcontainer pin inventory: each third-party tool pinned by an
 * `ARG <BASE>_VERSION` in .devcontainer/Dockerfile that a gate should watch, and
 * where its upstream releases live.
 *
 * Extracted from scripts/check-devcontainer-pin-freshness.ts for the same reason
 * embed-asset-sources.ts was extracted from its gate: that script calls main() at
 * module scope, so scripts/check-suppression-liveness.ts cannot import it for the
 * constants without running the whole freshness check, network included.
 *
 * `base` matches the key parseDockerfileVersions() produces, lowercased. NOTE its
 * regex is /^ARG\s+([A-Z0-9]+)_VERSION=/ -- the base carries NO UNDERSCORE. So
 * BW_VERSION -> "bw" and GLAB_VERSION -> "glab", but AGENT_BROWSER_VERSION does
 * not match at all and would need the shared parser widened first.
 *
 * WHY ONLY ONE ENTRY. The devcontainer image also pins glab (1.90.0), bottom
 * (0.12.3), agent-browser (0.26.0), openvscode-server (1.109.5) and a ttyd image
 * tag, and none of them is watched by anything either. They are absent here on
 * purpose, not by oversight: every one is already behind upstream, so seeding
 * them would turn the change that introduced this gate into a "bump five
 * unrelated tools" change nobody asked for, and a gate that is red on the day it
 * lands is a gate somebody disables. Adding one later is one entry plus,
 * ideally, its hashArgs. That is the whole migration.
 */

export interface DevcontainerPinHashArg {
  /** The Dockerfile ARG holding this asset's sha256, e.g. "BW_SHA256_AMD64". */
  arg: string;
  /** Release-asset filename for a given version. */
  asset: (version: string) => string;
}

export interface DevcontainerPinSource {
  /** Dockerfile ARG base, lowercased (matches parseDockerfileVersions keys). */
  base: string;
  display: string;
  /** owner/repo on github.com. */
  repo: string;
  /**
   * Release-tag prefix, e.g. "cli-v". REQUIRED, and it is the reason this gate
   * cannot reuse the embed gate's /releases/latest call: bitwarden/clients is a
   * monorepo whose "latest release" is whichever of web/desktop/browser/cli
   * shipped most recently. Filtering the release LIST by this prefix is the only
   * way to ask "what is the newest CLI?".
   */
  tagPrefix: string;
  /**
   * Per-arch sha256 ARGs to rewrite alongside the version. Optional: a pin with
   * no hashes (the tools listed in the header, if they are ever added) simply
   * omits it. When present, `--upgrade` refuses to rewrite the version unless it
   * can resolve EVERY digest -- a tree with a new version and a stale hash does
   * not build, and an upgrade path that hands back a broken build is worse than
   * no upgrade path.
   */
  hashArgs?: Record<string, DevcontainerPinHashArg>;
}

export const DEVCONTAINER_PIN_SOURCES: DevcontainerPinSource[] = [
  {
    base: 'bw',
    display: 'Bitwarden CLI',
    repo: 'bitwarden/clients',
    tagPrefix: 'cli-v',
    hashArgs: {
      amd64: { arg: 'BW_SHA256_AMD64', asset: (v) => `bw-linux-${v}.zip` },
      arm64: { arg: 'BW_SHA256_ARM64', asset: (v) => `bw-linux-arm64-${v}.zip` },
    },
  },
];

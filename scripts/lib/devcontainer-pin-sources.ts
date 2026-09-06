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
 * WHY NOT EVERY PIN. The devcontainer image also pins glab (1.90.0), bottom
 * (0.12.3), agent-browser (0.26.0), openvscode-server (1.109.5) and a ttyd image
 * tag, and none of them is watched by anything either. They are absent here on
 * purpose, not by oversight: every one is already behind upstream, so seeding
 * them would turn the change that introduced this gate into a "bump five
 * unrelated tools" change nobody asked for, and a gate that is red on the day it
 * lands is a gate somebody disables. Adding one later is one entry plus,
 * ideally, its hashArgs. That is the whole migration.
 *
 * (That paragraph opened "WHY ONLY ONE ENTRY" when this file held bw alone. The
 * count has moved twice since; the REASONING is what was worth keeping, so only
 * the heading changed.)
 *
 * THE GO TOOLS, added when .devcontainer/Dockerfile stopped installing them at
 * `@latest`. Three of the five are watchable and two are not, and the two are
 * the interesting half:
 *
 *   staticcheck  dominikh/go-tools tags its RELEASES by date (2026.2.1) while
 *                the Go MODULE version of the same build is v0.8.1. `go install`
 *                speaks module versions, so v0.8.1 is what the Dockerfile pins,
 *                and isNewer() comparing 2026.2.1 against 0.8.1 would report a
 *                stale pin on every run forever. A watcher that is always red is
 *                worse than none.
 *   goimports    lives in golang/tools, which publishes 89 releases and every
 *                one of them is tagged `gopls/*` (measured 2026-09-06 over the
 *                newest 100). goimports is versioned by the x/tools module
 *                (v0.49.0) and has no release of its own to compare against, so
 *                there is nothing here for tagPrefix to select. Watching it would
 *                need a tag-list source rather than a release-list one, which is
 *                a different fetch than this gate makes.
 *
 * gopls IS watchable despite sharing that repo, precisely because `gopls/v` is
 * the prefix those 89 releases carry -- the same monorepo problem tagPrefix was
 * built for below, which is why it needed no new machinery.
 */

/* NOT exported: `DevcontainerPinSource.hashArgs` is its only reference, and it is in
   this file. knip runs with `--treat-config-hints-as-errors`, so an export nobody
   imports is a hard CI failure, not a warning. */
interface DevcontainerPinHashArg {
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
  {
    base: 'bws',
    display: 'Bitwarden Secrets Manager CLI',
    repo: 'bitwarden/sdk-sm',
    tagPrefix: 'bws-v',
    hashArgs: {
      amd64: { arg: 'BWS_SHA256_AMD64', asset: (v) => `bws-x86_64-unknown-linux-gnu-${v}.zip` },
      arm64: { arg: 'BWS_SHA256_ARM64', asset: (v) => `bws-aarch64-unknown-linux-gnu-${v}.zip` },
    },
  },
  // The Go tools below carry NO hashArgs, and that is the documented "a pin with
  // no hashes simply omits it" case rather than an oversight: `go install`
  // verifies every module against the Go checksum database, which is a stronger
  // guarantee than a sha256 we recorded ourselves. .ci/scripts/lib/toolchain.sh
  // makes the identical argument for shfmt.
  {
    base: 'gopls',
    display: 'gopls (Go language server)',
    repo: 'golang/tools',
    // NOT "v". Every release in this repo is a gopls one, and its tag is
    // `gopls/v0.23.0` -- the module version with a directory prefix. Stripping
    // exactly this prefix is what yields the value the Dockerfile ARG holds.
    tagPrefix: 'gopls/v',
  },
  {
    base: 'dlv',
    display: 'Delve (Go debugger)',
    repo: 'go-delve/delve',
    tagPrefix: 'v',
  },
  {
    // GOLANGCILINT_VERSION, no underscore: parseDockerfileVersions' base is
    // /[A-Z0-9]+/, so a GOLANGCI_LINT_VERSION ARG would not be parsed and this
    // entry would match nothing. See the note in .devcontainer/Dockerfile.
    base: 'golangcilint',
    display: 'golangci-lint',
    repo: 'golangci/golangci-lint',
    tagPrefix: 'v',
  },
];

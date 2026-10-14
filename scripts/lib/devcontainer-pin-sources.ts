/**
 * The devcontainer pin inventory: each third-party tool pinned by an
 * `ARG <BASE>_VERSION` in .devcontainer/Dockerfile that a gate should watch, and
 * where its upstream releases live, READ FROM THE PIN REGISTRY.
 *
 * Extracted from scripts/gates/check-devcontainer-pin-freshness.ts for the same reason
 * embed-asset-sources.ts was extracted from its gate: that script calls main() at
 * module scope, so scripts/gates/check-suppression-liveness.ts cannot import it for the
 * constants without running the whole freshness check, network included.
 *
 * `base` matches the key parseDockerfileVersions() produces, lowercased. NOTE its
 * regex is /^ARG\s+([A-Z0-9]+)_VERSION=/ -- the base carries NO UNDERSCORE. So
 * BW_VERSION -> "bw" and GLAB_VERSION -> "glab", but AGENT_BROWSER_VERSION does
 * not match at all and would need the shared parser widened first.
 *
 * WHERE THE LIST LIVES. The `devcontainer:<tool>` entries of .ci/config/pins.json
 * are the inventory, and this gate watches the ones whose entry lists
 * `check:ci-devcontainer-pins` in its `gates`. The image also pins staticcheck,
 * goimports, codex, gemini-cli, glab, bottom, agent-browser and openvscode-server;
 * each is a registry entry too, unwatched here because every one was already
 * behind upstream when this gate landed and a gate red on the day it lands is a
 * gate somebody disables. Watching one is adding the gate id to its entry, plus
 * `sha256:<arch>` sites with an `asset` when it carries hashes.
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

import { entriesFor, loadRegistry, type PinEntry } from './pins/registry.js';

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

const DOCKERFILE = '.devcontainer/Dockerfile';

function toSource(e: PinEntry): DevcontainerPinSource {
  const fail = (why: string): never => {
    throw new Error(`.ci/config/pins.json ${e.id}: ${why}`);
  };
  const own = e.sites.filter((s) => s.repo === '.' && s.file === DOCKERFILE && s.arg);
  const version = own.find((s) => s.role === 'version')?.arg;
  if (!version?.endsWith('_VERSION'))
    fail(`needs a version site on ARG <BASE>_VERSION in ${DOCKERFILE}`);
  if (e.source.type !== 'github-release' || !e.source.repo || e.source.tagPrefix === undefined)
    fail('the devcontainer gate reads a github-release source with a repo and a tagPrefix');
  const hashArgs: Record<string, DevcontainerPinHashArg> = {};
  for (const s of own.filter((x) => x.role.startsWith('sha256:'))) {
    const template = s.asset ?? fail(`site ARG ${s.arg} has no asset filename`);
    hashArgs[s.role.slice('sha256:'.length)] = {
      arg: s.arg as string,
      asset: (v) => template.replaceAll('{version}', v),
    };
  }
  return {
    base: (version as string).slice(0, -'_VERSION'.length).toLowerCase(),
    display: e.name,
    repo: e.source.repo as string,
    tagPrefix: e.source.tagPrefix as string,
    ...(Object.keys(hashArgs).length > 0 ? { hashArgs } : {}),
  };
}

export const DEVCONTAINER_PIN_SOURCES: DevcontainerPinSource[] = entriesFor(
  loadRegistry(),
  'devcontainer'
)
  .filter((e) => e.gates.includes('check:ci-devcontainer-pins'))
  .map(toSource);

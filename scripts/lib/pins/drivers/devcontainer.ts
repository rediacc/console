/**
 * The devcontainer driver: the `devcontainer:<tool>` pins of .devcontainer/Dockerfile, the
 * eight ARGs outside the freshness gate's list included (staticcheck, goimports, codex,
 * gemini-cli, glab, bottom, agent-browser, openvscode-server), and every other site their
 * registry entries place (the web image's agent-browser ARG, renet's lint.sh golangci-lint,
 * start-vscode.sh's default) (agent/plans/PLAN-pins-command.md T7).
 *
 * It replaces `check:ci-devcontainer-pins --upgrade`'s rewrite, with the same rule kept
 * and widened: a tool that carries sha256 pins moves only when the release publishes a digest
 * for EVERY hashed asset, because a new version beside a stale hash is an image that fails
 * `sha256sum -c -` at build. The digests are the release API's own `digest` field (GitHub
 * publishes no independent trust root for these assets), found by the `asset` filename each
 * `sha256:<arch>` site names.
 *
 * A pin installed with `go install` (its registry entry names a `goModule`) takes only a release
 * whose go.mod `go` directive builds on the image's Go: GO_VERSION in .devcontainer/toolchain.env
 * with GOTOOLCHAIN=local (worklist #e023eb0d, scripts/lib/pins/go-directive.ts). A newer release
 * is answered with an ineligible verdict naming the Go it needs, so the core takes the newest one
 * that builds; a go.mod the proxy does not answer refuses the pin (fail closed).
 *
 * What the driver cannot do, it says: a `none` source (glab, published on gitlab.com) is not
 * compared, and the proving `docker build` stays the operator's, since the image only changes
 * when ci-build-docker.yml runs on the merge.
 */

import { NotCompared, UnreadableListing } from '../../upstream.js';
import {
  type DriverContext,
  type Inspection,
  leafCurrent,
  type PinDriver,
  type PinPlan,
  PlanRefused,
  planLeafSites,
  type Release,
} from '../driver.js';
import { goNeeds, goTooNew, imageGoVersion, needsGoWhy, TOOLCHAIN_ENV } from '../go-directive.js';
import { idName, type PinEntry, siteMatches } from '../registry.js';
import { checkSites, digestFor, hashSites } from './toolchain-plan.js';
import {
  byNewest,
  type Dated,
  type GhRelease,
  githubReleases,
  goModuleVersions,
  newerThan,
  npmVersions,
  type Upstream,
} from './toolchain-upstream.js';

/**
 * Selftest mutants: `half-hash` moves the version when a digest is missing and keeps the old hash;
 * `ignore-go` offers a goModule release whatever Go its go.mod needs (the driver before 2026-10-19).
 */
export const DEVCONTAINER_MUTANTS = ['half-hash', 'ignore-go'] as const;
export type DevcontainerMutant = (typeof DEVCONTAINER_MUTANTS)[number];

function refusal(err: unknown): PlanRefused {
  if (err instanceof PlanRefused) return err;
  if (err instanceof NotCompared || err instanceof UnreadableListing)
    return new PlanRefused(err.message);
  throw err;
}

/** Every release of the entry's source, newest first, with the digests a GitHub source publishes. */
async function releasesOf(
  up: Upstream,
  entry: PinEntry,
  current: string | null
): Promise<Array<Dated & { digests?: Map<string, string> }>> {
  const s = entry.source;
  const who = entry.name;
  if (s.type === 'github-release' && s.repo)
    return githubReleases(up, s.repo, s.tagPrefix ?? '', who, current);
  if (s.type === 'npm-registry' && s.package) return npmVersions(up, s.package, who);
  if (s.type === 'go-list' && s.module) return goModuleVersions(up, s.module, who, current);
  if (s.type === 'none') throw new Error(s.reason ?? 'the registry names no source');
  throw new Error(`the devcontainer driver cannot read a ${s.type} source`);
}

/** The image's Go, read from the tree being bumped; a tree that names none refuses the pin. */
function imageGo(entry: PinEntry, ctx: DriverContext): string {
  const have = imageGoVersion(ctx.read({ repo: '.', file: TOOLCHAIN_ENV }));
  if (have === null)
    throw new PlanRefused(
      `${entry.id}: ${TOOLCHAIN_ENV} names no GO_VERSION, so the Go a release needs cannot be compared with the image's`
    );
  return have;
}

/** Null when `version` of a goModule pin builds on Go `have`, else why it does not. Throws when the proxy does not answer. */
async function goBlocker(
  up: Upstream,
  entry: PinEntry,
  version: string,
  have: string
): Promise<string | null> {
  const mod = entry.goModule as string;
  const need = await goNeeds((url) => up.text(url, entry.name), mod, version);
  return goTooNew(need, have) ? needsGoWhy(mod, version, need, have) : null;
}

export function createDevcontainerDriver(
  up: Upstream,
  mutant: DevcontainerMutant | null = null
): PinDriver {
  async function inspect(entry: PinEntry, ctx: DriverContext): Promise<Inspection> {
    const current = leafCurrent(entry, ctx);
    const all = await releasesOf(up, entry, current);
    const releases = newerThan(byNewest(all), current).map(
      (r): Release => ({ version: r.version, publishedMs: r.publishedMs })
    );
    if (entry.goModule !== undefined && releases.length > 0) {
      const have = imageGo(entry, ctx);
      for (const r of releases) {
        const why = mutant === 'ignore-go' ? null : await goBlocker(up, entry, r.version, have);
        if (why !== null) r.verdict = { eligible: false, why };
      }
    }
    return { current, releases };
  }

  async function plan(entry: PinEntry, to: Release, ctx: DriverContext): Promise<PinPlan> {
    try {
      checkSites(entry, entry.sites, ctx.read);
      const current = leafCurrent(entry, ctx);
      if (entry.goModule !== undefined && mutant !== 'ignore-go') {
        const why = await goBlocker(up, entry, to.version, imageGo(entry, ctx));
        if (why !== null) throw new PlanRefused(`${entry.id}: ${why}`);
      }
      const values: Record<string, string> = { version: to.version };
      const hashed = hashSites(entry);
      if (hashed.length > 0) {
        const hit = (await releasesOf(up, entry, current)).find((r) => r.version === to.version);
        const digests = (hit as GhRelease | undefined)?.digests ?? new Map<string, string>();
        for (const site of hashed) {
          try {
            values[site.role] = digestFor(site, to.version, digests);
          } catch (err) {
            if (mutant !== 'half-hash' || !(err instanceof PlanRefused)) throw err;
            const old = ctx.read(site);
            values[site.role] = (old === null ? undefined : siteMatches(site, old)[0]?.value) ?? '';
          }
        }
      }
      const { writes, changes } = planLeafSites(entry, values, ctx);
      return { entry, from: current, to, writes, steps: [], changes };
    } catch (err) {
      throw refusal(err);
    }
  }

  return { name: 'devcontainer', inspect, plan, holdKey: (e) => idName(e) };
}

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

/** Selftest mutants: `half-hash` moves the version when a digest is missing and keeps the old hash. */
export const DEVCONTAINER_MUTANTS = ['half-hash'] as const;
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

export function createDevcontainerDriver(
  up: Upstream,
  mutant: DevcontainerMutant | null = null
): PinDriver {
  async function inspect(entry: PinEntry, ctx: DriverContext): Promise<Inspection> {
    const current = leafCurrent(entry, ctx);
    const all = await releasesOf(up, entry, current);
    return {
      current,
      releases: newerThan(byNewest(all), current).map(
        (r): Release => ({ version: r.version, publishedMs: r.publishedMs })
      ),
    };
  }

  async function plan(entry: PinEntry, to: Release, ctx: DriverContext): Promise<PinPlan> {
    try {
      checkSites(entry, entry.sites, ctx.read);
      const current = leafCurrent(entry, ctx);
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

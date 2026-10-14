/**
 * The planning helpers the embed, devcontainer and toolchain drivers share: the site-count
 * check that refuses a whole pin, the hold lookup, and the digest lookup for a `sha256:<arch>`
 * site (agent/plans/PLAN-pins-command.md Design 3).
 */
import type { DriverContext } from '../driver.js';
import { keyOf, PlanRefused } from '../driver.js';
import { type PinEntry, type PinSite, type RepoPath, siteMatches } from '../registry.js';

/**
 * Refuse unless every site matches exactly `expect` times in the text `read` answers. A site
 * that moved (zero) or was duplicated (two) is a finding before any byte is planned.
 */
export function checkSites(
  entry: PinEntry,
  sites: PinSite[],
  read: (p: RepoPath) => string | null
): void {
  for (const [i, site] of sites.entries()) {
    const where = `${entry.id} site ${i} (${keyOf(site)}, ${site.role})`;
    const text = read(site);
    if (text === null) throw new PlanRefused(`${where}: the file does not exist`);
    const n = siteMatches(site, text).length;
    if (n !== site.expect)
      throw new PlanRefused(
        `${where}: matches ${n} time(s), the registry expects ${site.expect}; nothing is written for ${entry.id}`
      );
  }
}

/** The values the `version`-role sites of `sites` hold in the text `read` answers. */
export function versionValues(sites: PinSite[], read: (p: RepoPath) => string | null): string[] {
  return sites
    .filter((s) => s.role === 'version')
    .flatMap((s) => {
      const text = read(s);
      return text === null ? [] : siteMatches(s, text).map((m) => m.value);
    });
}

/**
 * True when `key` has a live line in the entry's first hold file: a line whose first token is
 * the key, unless its `expires YYYY-MM-DD` has passed. The core reads the hold of the entry it
 * bumps; a driver that moves a second entry in the same plan reads that entry's hold here.
 */
export function isHeld(ctx: DriverContext, entry: PinEntry, key: string, nowMs: number): boolean {
  const file = entry.holds[0];
  if (!file) return false;
  const text = ctx.read({ repo: '.', file });
  if (text === null) return false;
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (t === '' || t.startsWith('#') || t.split(/\s+/)[0] !== key) continue;
    const expires = /expires (\d{4}-\d\d-\d\d)/.exec(t)?.[1];
    if (expires === undefined || Date.parse(`${expires}T00:00:00Z`) > nowMs) return true;
  }
  return false;
}

/**
 * The sha256 a `sha256:<arch>` site takes for `version`, from the release's published digests
 * by the site's `asset` filename. A site with no asset, or a release with no digest for it,
 * refuses the pin: a new version beside a stale hash is a tree that fails `sha256sum -c -`.
 */
export function digestFor(site: PinSite, version: string, digests: Map<string, string>): string {
  const where = `${keyOf(site)} (${site.role})`;
  if (!site.asset)
    throw new PlanRefused(
      `${where}: the registry site names no release asset, so its sha256 cannot be resolved`
    );
  const asset = site.asset.replaceAll('{version}', version);
  const digest = digests.get(asset);
  if (!digest || !/^[0-9a-f]{64}$/.test(digest))
    throw new PlanRefused(
      `${where}: release ${version} publishes no sha256 digest for ${asset}; refusing to move the version without its hash`
    );
  return digest;
}

/** The sites of an entry that carry a hash. */
export const hashSites = (entry: PinEntry): PinSite[] =>
  entry.sites.filter((s) => s.role.startsWith('sha256:'));

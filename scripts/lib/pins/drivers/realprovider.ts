/**
 * The `real-provider` driver of `npm run pins`: the Bitwarden browser extension and the
 * vaultwarden image the real-provider spec loads (private/account/e2e/real-provider.lock.json;
 * PLAN-pins-command T8, survey item 9).
 *
 * A BUMP IS `npm run real-provider:bump`, WRAPPED, NOT RE-IMPLEMENTED. The lock records far
 * more than the two registry sites (the asset URL, the release tag, the image index digest,
 * one binary hash per architecture, the publish time), every one of them computed from bytes
 * the script downloads and verifies, so a plan that rewrote only `version` and `sha256`
 * would leave the lock lying. The driver therefore plans no file contents: it plans one
 * step, `npm run real-provider:bump -- --<pin> <version>` in private/account/e2e, which may
 * write the lock file and nothing else.
 *
 * IT CANNOT BE VERIFIED BY THE GATES. check:ci-real-provider-pins compares the lock with
 * upstream; whether the new extension still behaves (PRF answers, the walks) is only
 * observed by the spec against live providers. The plan's change line says so, and the
 * message draft carries it: run `npm run test:real-provider` in private/account/e2e before
 * the commit. The bump script itself refuses a draft, a pre-release and a release inside the
 * window; the core's release-age judgement is applied first, on `published_at`.
 *
 * SOURCES: `github-release` with a `tagPrefix` (`browser-v` for the extension, none for
 * vaultwarden); only a published full release with a dotted version after the prefix counts.
 */
import type { Inspection, PinDriver, PinPlan, Release } from '../driver.js';
import { leafCurrent } from '../driver.js';
import { cmpVersion, type Deps, leafKey, realDeps, requireSource } from './shared.js';

const VERSION = /^\d+\.\d+\.\d+$/;
const PAGES = 5;

interface GhRelease {
  tag_name?: unknown;
  published_at?: unknown;
  draft?: unknown;
  prerelease?: unknown;
}

export function realProviderDriver(depsFor: (root: string) => Deps = realDeps): PinDriver {
  return {
    name: 'real-provider',
    async inspect(entry, ctx): Promise<Inspection> {
      requireSource(entry);
      const { repo, tagPrefix } = entry.source;
      if (entry.source.type !== 'github-release' || !repo)
        throw new Error('the real-provider driver reads github-release sources');
      const deps = depsFor(ctx.root);
      const current = leafCurrent(entry, ctx);
      const found = new Map<string, Release>();
      for (let page = 1; page <= PAGES; page++) {
        const j = (await deps.github(
          `/repos/${repo}/releases?per_page=100&page=${page}`,
          repo
        )) as GhRelease[];
        if (!Array.isArray(j)) throw new Error(`${repo}: the releases list is not an array`);
        for (const r of j) {
          const tag = typeof r.tag_name === 'string' ? r.tag_name : '';
          if (r.draft === true || r.prerelease === true || !tag.startsWith(tagPrefix ?? ''))
            continue;
          const version = tag.slice((tagPrefix ?? '').length);
          if (!VERSION.test(version)) continue;
          const at = typeof r.published_at === 'string' ? Date.parse(r.published_at) : Number.NaN;
          found.set(version, { version, publishedMs: Number.isNaN(at) ? null : at });
        }
        if (j.length < 100 || (current !== null && found.has(current))) break;
      }
      if (found.size === 0)
        throw new Error(`${repo}: no published ${tagPrefix ?? ''}<x.y.z> release found`);
      const releases = [...found.values()]
        .filter((r) => current === null || cmpVersion(r.version, current) > 0)
        .sort((a, b) => cmpVersion(b.version, a.version));
      return { current, releases };
    },
    plan(entry, to, ctx): Promise<PinPlan> {
      const flag = leafKey(entry);
      const lock = entry.sites[0];
      const from = leafCurrent(entry, ctx);
      return Promise.resolve({
        entry,
        from,
        to,
        writes: [],
        steps: [
          {
            label: `real-provider:bump (${flag})`,
            run: `npm run real-provider:bump -- --${flag} ${to.version}`,
            cwd: 'private/account/e2e',
            writes: [{ repo: lock.repo, file: lock.file }],
          },
        ],
        changes: [
          `${lock.repo}/${lock.file}: ${flag} ${from} -> ${to.version} (url, digests and publishedAt computed by real-provider:bump from verified downloads); NEEDS LIVE VERIFICATION: run \`npm run test:real-provider\` in private/account/e2e before committing`,
        ],
      });
    },
    holdKey: leafKey,
  };
}

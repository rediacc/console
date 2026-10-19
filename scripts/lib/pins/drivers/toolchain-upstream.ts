/**
 * What the embed, devcontainer and toolchain drivers read from upstream, and the one seam that
 * lets their selftests read a fixture instead (agent/plans/PLAN-pins-command.md Design 3).
 *
 * Each reader answers a list of the releases NEWER than the pinned value, newest first, with the
 * publish instant the release-age window judges. A reader never decides eligibility: the core
 * judges `publishedMs` through scripts/lib/release-age.ts, so a source that carries no date
 * answers null and the core defers the release (an unknown age fails closed).
 *
 * Every request goes through scripts/lib/upstream.ts, so the retry budget, the token handling
 * and the wording of an unreachable finding are the ones every freshness gate uses. A request
 * that was not answered throws NotCompared, and an answer that cannot be used throws
 * UnreadableListing; the driver turns either into a refusal or an "uncompared" view.
 */
import crypto from 'node:crypto';
import { WK_GH_API_BASE } from '../../../../packages/shared/src/config/well-known.generated.js';
import { githubApiHeaders } from '../../github-token.js';
import {
  askUpstream,
  type Failure,
  NotCompared,
  retryUpstream,
  UnreadableListing,
} from '../../upstream.js';

const USER_AGENT = 'rediacc-pins';

/** The network the three drivers read, so a selftest answers from a fixture. */
export interface Upstream {
  json(url: string, who: string): Promise<unknown>;
  text(url: string, who: string): Promise<string>;
  /** The Last-Modified instant of a resource (HEAD), or null when the host sends none or the request fails. */
  lastModified(url: string, who: string): Promise<number | null>;
  /**
   * The sha256 of the bytes at `url`, for an upstream that publishes no digest beside its
   * assets (AWS's versioned aws CLI installers): the driver downloads the asset and hashes it.
   * Optional, so a fixture that never names such an asset needs no answer for it.
   */
  sha256?(url: string, who: string): Promise<string>;
}

/** A whole installer is tens of megabytes, so its download gets far more than the 15 s listing budget. */
const ASSET_TIMEOUT_MS = 300_000;

/** One GET of a binary asset, hashed as it arrives; a non-2xx or a dropped connection is a failed attempt. */
async function hashOnce(url: string, who: string): Promise<{ value: string } | Failure> {
  try {
    const res = await fetch(url, {
      headers: headersFor(url),
      signal: AbortSignal.timeout(ASSET_TIMEOUT_MS),
    });
    if (!res.ok || res.body === null)
      return {
        what: `HTTP ${res.status} for ${who}`,
        retry: res.status >= 500 || res.status === 429,
        status: res.status,
        retryAfterS: null,
        unreachable: false,
      };
    const hash = crypto.createHash('sha256');
    for await (const chunk of res.body) hash.update(chunk);
    return { value: hash.digest('hex') };
  } catch (err) {
    const what = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
    return { what, retry: true, status: null, retryAfterS: null, unreachable: true };
  }
}

const headersFor = (url: string): Record<string, string> =>
  url.startsWith(`${WK_GH_API_BASE}/`)
    ? githubApiHeaders(USER_AGENT)
    : { 'User-Agent': USER_AGENT };

/** Ask once per URL for the life of the run: inspect and plan read the same listing. */
function memo<T>(cache: Map<string, Promise<T>>, key: string, make: () => Promise<T>): Promise<T> {
  let hit = cache.get(key);
  if (!hit) {
    hit = make();
    cache.set(key, hit);
  }
  return hit;
}

export function networkUpstream(): Upstream {
  const bodies = new Map<string, Promise<string>>();
  const dates = new Map<string, Promise<number | null>>();
  const text = (url: string, who: string): Promise<string> =>
    memo(bodies, url, async () => (await askUpstream({ url, headers: headersFor(url), who })).body);
  return {
    text,
    async json(url, who) {
      const body = await text(url, who);
      try {
        return JSON.parse(body);
      } catch {
        throw new UnreadableListing(`${new URL(url).host}${new URL(url).pathname}: not JSON`);
      }
    },
    lastModified: (url, who) =>
      memo(dates, url, async () => {
        try {
          const head = await askUpstream({ url, headers: headersFor(url), who, method: 'HEAD' });
          const raw = head.headers.get('last-modified');
          const ms = raw === null ? Number.NaN : Date.parse(raw);
          return Number.isNaN(ms) ? null : ms;
        } catch (err) {
          if (err instanceof NotCompared) return null;
          throw err;
        }
      }),
    sha256: (url, who) =>
      memo(bodies, `sha256:${url}`, () => {
        const u = new URL(url);
        return retryUpstream({ asked: `GET ${u.host}${u.pathname}`, host: u.host, who }, () =>
          hashOnce(url, who)
        );
      }),
  };
}

/** The GitHub REST API path as a full URL. */
export const gh = (apiPath: string): string => `${WK_GH_API_BASE}${apiPath}`;

// ---- versions -------------------------------------------------------------------------------

/** A release version this tool will take: dotted numbers and an optional build suffix (`1.37.1+k3s1`). */
const STABLE = /^\d+(?:\.\d+)+(?:\+[0-9A-Za-z.]+)?$/;
export const isStable = (v: string): boolean => STABLE.test(v);

function segments(v: string): number[] {
  const [core, meta = ''] = v.replace(/^v/i, '').split('+');
  return [
    ...core.split(/[.-]/).map((s) => Number.parseInt(s, 10) || 0),
    Number.parseInt(meta.replace(/\D/g, ''), 10) || 0,
  ];
}

/** Negative when a < b, positive when a > b. The comparison the embed and devcontainer gates use. */
export function compareVersions(a: string, b: string): number {
  const x = segments(a);
  const y = segments(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

/** Newest first. */
export const byNewest = <T extends { version: string }>(list: T[]): T[] =>
  [...list].sort((a, b) => compareVersions(b.version, a.version));

export const newerThan = <T extends { version: string }>(list: T[], current: string | null): T[] =>
  current === null ? list : list.filter((r) => compareVersions(r.version, current) > 0);

// ---- GitHub releases and tags ---------------------------------------------------------------

export interface GhRelease {
  version: string;
  publishedMs: number | null;
  /** Release asset filename -> bare sha256 hex, from the API's `digest` field. */
  digests: Map<string, string>;
}

interface RawRelease {
  tag_name?: string;
  published_at?: string;
  draft?: boolean;
  prerelease?: boolean;
  assets?: Array<{ name?: string; digest?: string }>;
}

/**
 * Stable releases of a repository whose tag starts with `prefix`, newest first. The list
 * endpoint, never /releases/latest: on a monorepo that answers with whichever component shipped
 * last. A repository that tags without cutting releases (CRIU) answers an empty list, and the
 * tags are read instead, each dated by its commit; only the `current`-newer ones are dated, so
 * the fallback costs a request per candidate rather than per tag.
 */
export async function githubReleases(
  up: Upstream,
  repo: string,
  prefix: string,
  who: string,
  current: string | null
): Promise<GhRelease[]> {
  const raw = await up.json(gh(`/repos/${repo}/releases?per_page=100`), who);
  if (!Array.isArray(raw)) throw new UnreadableListing('the response is not a release list');
  const out: GhRelease[] = [];
  for (const r of raw as Array<RawRelease | null>) {
    if (!r?.tag_name || r.draft || r.prerelease || !r.tag_name.startsWith(prefix)) continue;
    const version = r.tag_name.slice(prefix.length);
    if (!isStable(version)) continue;
    const digests = new Map<string, string>();
    for (const a of r.assets ?? [])
      if (a.name && a.digest?.startsWith('sha256:'))
        digests.set(a.name, a.digest.slice('sha256:'.length));
    out.push({
      version,
      publishedMs: r.published_at ? Date.parse(r.published_at) : null,
      digests,
    });
  }
  if (out.length > 0) return byNewest(out);
  return githubTags(up, repo, prefix, who, current);
}

async function githubTags(
  up: Upstream,
  repo: string,
  prefix: string,
  who: string,
  current: string | null
): Promise<GhRelease[]> {
  const tags = await up.json(gh(`/repos/${repo}/tags?per_page=100`), who);
  if (!Array.isArray(tags)) throw new UnreadableListing('the response is not a tag list');
  const found = (tags as Array<{ name?: string } | null>)
    .map((t) => t?.name ?? '')
    .filter((n) => n.startsWith(prefix) && isStable(n.slice(prefix.length)))
    .map((n) => ({ tag: n, version: n.slice(prefix.length) }));
  if (found.length === 0)
    throw new UnreadableListing(`no released tag starting with "${prefix}" in the newest 100`);
  const candidates = newerThan(byNewest(found), current).slice(0, 5);
  const out: GhRelease[] = [];
  for (const c of candidates) {
    const commit = (await up.json(
      gh(`/repos/${repo}/commits/${encodeURIComponent(c.tag)}`),
      who
    )) as { commit?: { committer?: { date?: string } } } | null;
    const date = commit?.commit?.committer?.date;
    out.push({
      version: c.version,
      publishedMs: date ? Date.parse(date) : null,
      digests: new Map(),
    });
  }
  return out;
}

// ---- other sources --------------------------------------------------------------------------

export interface Dated {
  version: string;
  publishedMs: number | null;
}

/** npm registry: every stable `x.y.z`, dated by the `time` map. */
export async function npmVersions(up: Upstream, pkg: string, who: string): Promise<Dated[]> {
  const doc = (await up.json(`https://registry.npmjs.org/${pkg.replace('/', '%2F')}`, who)) as {
    versions?: Record<string, unknown>;
    time?: Record<string, string>;
  } | null;
  if (!doc?.versions || !doc.time) throw new UnreadableListing(`${pkg}: no versions or time map`);
  return byNewest(
    Object.keys(doc.versions)
      .filter((v) => /^\d+\.\d+\.\d+$/.test(v))
      .map((v) => ({ version: v, publishedMs: doc.time?.[v] ? Date.parse(doc.time[v]) : null }))
  );
}

/** PyPI: every stable release, dated by its earliest upload; a release whose files are all yanked is skipped. */
export async function pypiVersions(up: Upstream, pkg: string, who: string): Promise<Dated[]> {
  const doc = (await up.json(`https://pypi.org/pypi/${pkg}/json`, who)) as {
    releases?: Record<string, Array<{ upload_time_iso_8601?: string; yanked?: boolean }>>;
  } | null;
  if (!doc?.releases) throw new UnreadableListing(`${pkg}: no releases map`);
  const out: Dated[] = [];
  for (const [v, files] of Object.entries(doc.releases)) {
    if (!/^\d+(?:\.\d+)+$/.test(v)) continue;
    const live = files.filter((f) => !f.yanked && f.upload_time_iso_8601);
    if (live.length === 0) continue;
    const times = live.map((f) => Date.parse(f.upload_time_iso_8601 as string));
    out.push({ version: v, publishedMs: Math.min(...times) });
  }
  return byNewest(out);
}

/** The Go module proxy escapes capitals as `!lower`. */
const escapeModule = (m: string): string => m.replace(/[A-Z]/g, (c) => `!${c.toLowerCase()}`);

/** Go proxy: stable `vX.Y.Z` module versions (no pre-release, no +incompatible), newest `limit` dated by `.info`. */
export async function goModuleVersions(
  up: Upstream,
  mod: string,
  who: string,
  current: string | null,
  limit = 5
): Promise<Dated[]> {
  const base = `https://proxy.golang.org/${escapeModule(mod)}/@v`;
  const list = await up.text(`${base}/list`, who);
  const versions = list
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => /^v\d+\.\d+\.\d+$/.test(l))
    .map((l) => ({ version: l.slice(1), tag: l }));
  if (versions.length === 0)
    throw new UnreadableListing(`${mod}: the proxy lists no stable version`);
  const out: Dated[] = [];
  for (const c of newerThan(byNewest(versions), current).slice(0, limit)) {
    const info = (await up.json(`${base}/${c.tag}.info`, who)) as { Time?: string } | null;
    out.push({ version: c.version, publishedMs: info?.Time ? Date.parse(info.Time) : null });
  }
  return out;
}

/** The newest `limit` rsync tarballs in the Samba source index, each dated by its Last-Modified. */
export async function rsyncVersions(
  up: Upstream,
  who: string,
  current: string | null,
  limit = 5
): Promise<Dated[]> {
  const index = 'https://download.samba.org/pub/rsync/src/';
  const html = await up.text(index, who);
  const found = [
    ...new Set([...html.matchAll(/rsync-(\d+\.\d+\.\d+)\.tar\.gz/g)].map((m) => m[1])),
  ];
  if (found.length === 0) throw new UnreadableListing('no rsync tarballs found in the index');
  const out: Dated[] = [];
  for (const c of newerThan(byNewest(found.map((version) => ({ version }))), current).slice(
    0,
    limit
  ))
    out.push({
      version: c.version,
      publishedMs: await up.lastModified(`${index}rsync-${c.version}.tar.gz`, who),
    });
  return out;
}

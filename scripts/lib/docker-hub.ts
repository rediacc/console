/**
 * Docker Hub's repository and tag addressing, the one place a tag's digest is read, and the one
 * read path every Docker Hub caller shares.
 *
 * Two readers share it: the `docker` driver of `npm run pins` (scripts/lib/pins/drivers/
 * docker.ts), which lists a pin's candidate tags and resolves the digest a bump writes beside the
 * tag, and check:ci-docker-image-freshness, which lists each FROM pin's tags and proves every
 * `<image>:<tag>@sha256:<digest>` line in the tree still agrees with what Docker Hub serves for
 * that tag. Both read through `hubReader()` below; neither keeps its own parser or transport.
 *
 * WHICH DIGEST. `GET /v2/repositories/<repo>/tags/<tag>` answers a top-level `digest`, the
 * multi-arch INDEX digest, the same value `docker buildx imagetools inspect <image>:<tag>`
 * prints as `Manifest.Digest` and the one a `FROM <image>:<tag>@sha256:...` line must carry.
 * The per-architecture digests under `images[]` are NOT it: pinning one of those makes every
 * other architecture fail to pull. So only the top-level field is read, and anything else
 * (absent, malformed, an `images[]`-only answer) is null, which every caller treats as a
 * refusal, never as agreement.
 *
 * WHY ONE TRANSPORT. ci:quick runs check:ci-docker-image-freshness and check:ci-pin-freshness at
 * once. Each kept its own transport, so the same tag listing was read once per pin and once per
 * gate, in parallel, and on 2026-11-21 the pair failed a push receipt with HTTP 429 although each
 * passed alone. Measured that day: the gate sent DOCKERHUB_TOKEN (a `dckr_pat_` personal access
 * token) raw as a Bearer, which Hub answers 401 on every request, so each read cost a 401 plus an
 * anonymous retry against the 180-per-window anonymous budget (50 requests for 25 answers); the
 * driver read anonymously and re-listed the same URL for every pin of an image (156 requests, 25
 * of them 429). The same token exchanged at /v2/users/login is a JWT Hub serves at 600.
 *
 * WHAT THE READ PATH DOES, and what it never does:
 *  - ONE TOKEN PER CREDENTIAL. DOCKERHUB_USERNAME with DOCKERHUB_TOKEN (or DOCKERHUB_PASSWORD) is
 *    exchanged once for a JWT, kept on disk (mode 0600, in the gitignored cache) until 60 s
 *    before its `exp`, and reused by every read and every process. A token with no username
 *    cannot be exchanged and is not sent: a raw PAT is always a 401 (measured), so sending it only
 *    spent anonymous budget. A JWT a read refuses (401/403) is dropped and the read retried
 *    anonymously, so a rejected credential is never worse than none.
 *  - ONE FETCH PER URL. An answer is cached on disk under .ci/cache/registry/, keyed by the URL's
 *    sha256, for HUB_CACHE_TTL_MS, and shared across gates and runs. Concurrent readers of one URL
 *    take a lock file per key (`open(..., 'wx')`), so the second reader waits for the first and
 *    then reads its answer instead of asking Hub again. In one process, concurrent reads of a URL
 *    share one promise.
 *  - ONLY A 200 IS CACHED. A 429, a 5xx, a 404, a body that is not JSON: none is ever written as
 *    an answer, and an answer older than its TTL (or dated in the future) is never served.
 *  - A 429 IS WAITED OUT ONLY WITHIN A BUDGET. Retry-After (seconds or a date), RateLimit-Reset
 *    (seconds) and Hub's X-RateLimit-Reset (epoch seconds) name when the limit clears; a wait that
 *    fits what remains of HUB_WAIT_BUDGET_MS for the process is slept once and the read retried,
 *    else the read is unknown at once. The limit is recorded beside the cache (at most
 *    LIMIT_RECORD_MAX_MS ahead), so a parallel gate stops asking instead of spending the same
 *    budget; that record only ever makes a read unknown, never an answer.
 *  - Credential and disk cache are for the real Hub origin only. A stub base (DOCKER_HUB_API_BASE)
 *    gets neither, so a test server's canned answer is never cached and no credential leaves.
 */

import { createHash, randomBytes } from 'node:crypto';
import {
  closeSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync,
  writeSync,
} from 'node:fs';
import path from 'node:path';
import { REPO_ROOT } from './repo-root.js';

/** The Docker Hub API host a caller uses when no stub base is set. */
export const HUB_DEFAULT_BASE = 'https://hub.docker.com';

const DIGEST = /^sha256:[0-9a-f]{64}$/;

/**
 * The Docker Hub repository path of an image reference (`node` -> `library/node`,
 * `docker.io/foo/bar` -> `foo/bar`), or null for an image served by another registry
 * (a first path component carrying a dot, `mcr.microsoft.com/...`, `ghcr.io/...`). Pure.
 */
export function hubRepo(image: string): string | null {
  if (image.includes('.') && !image.startsWith('docker.io/')) return null;
  const bare = image.replace(/^docker\.io\//, '');
  return bare.includes('/') ? bare : `library/${bare}`;
}

/** The per-tag endpoint, whose answer carries the tag's index `digest`. Pure. */
export function hubTagUrl(base: string, repo: string, tag: string): string {
  return `${base.replace(/\/+$/, '')}/v2/repositories/${repo}/tags/${encodeURIComponent(tag)}`;
}

/**
 * The index digest of a per-tag answer: its top-level `digest` when that is exactly
 * `sha256:<64 hex>`, else null. `images[]` is never consulted (see WHICH DIGEST). Pure.
 */
export function parseTagDigest(json: unknown): string | null {
  if (typeof json !== 'object' || json === null || Array.isArray(json)) return null;
  const d = (json as { digest?: unknown }).digest;
  return typeof d === 'string' && DIGEST.test(d) ? d : null;
}

// ---- the shared read path ------------------------------------------------------------------

/** How long a cached tag listing or tag answer is served before it is read again. */
export const HUB_CACHE_TTL_MS = 6 * 60 * 60 * 1000;
/** The most one process sleeps on Hub's rate limit and on transient backoff, summed over every read. */
export const HUB_WAIT_BUDGET_MS = 60_000;
/** The cache directory: gitignored scratch (`.ci/cache/` in .gitignore). */
export const HUB_CACHE_DIR = path.join(REPO_ROOT, '.ci', 'cache', 'registry');
const HTTP_TIMEOUT_MS = 15_000;
const LOCK_POLL_MS = 100;
/** Tries for a network error, a timeout or a 5xx, with BACKOFF_MS between them. */
const TRANSIENT_TRIES = 3;
const BACKOFF_MS = [2_000, 4_000];
/** A lock older than this is a dead holder's. A live holder can sleep the whole wait budget and then spend a request timeout on every try, so the bound sits above that worst case, never at a guess of "a few requests". */
export const LOCK_STALE_MS = HUB_WAIT_BUDGET_MS + TRANSIENT_TRIES * HTTP_TIMEOUT_MS + 30_000;
/** A JWT is not used within this long of its `exp`. */
const TOKEN_MARGIN_MS = 60_000;
/** The life assumed for a JWT whose `exp` cannot be read. */
const TOKEN_FALLBACK_MS = 5 * 60_000;
/** A 429 with no header naming when it clears is recorded for this long. */
const LIMIT_DEFAULT_MS = 2_000;
/** The furthest ahead a recorded limit reaches, so a far-future reset header cannot silence reads for a day. */
const LIMIT_RECORD_MAX_MS = 15 * 60_000;

export type HubRead =
  | { ok: true; json: unknown; source: 'network' | 'disk' | 'memory' }
  | { ok: false; why: string; status: number | null };

export interface HubReadStats {
  /** GETs sent to Hub for answers (each retry counts). */
  network: number;
  /** Answers served from the disk cache, a parallel reader's included. */
  disk: number;
  /** Reads that joined a read of the same URL already in flight in this process. */
  memory: number;
  /** Token exchanges sent, and JWTs reused from disk. */
  tokenMints: number;
  tokenReuse: number;
  /** 429 answers seen, and reads refused because a recorded limit had not cleared. */
  rateLimited: number;
  limitedSkips: number;
  waitedMs: number;
}

export interface HubReaderOptions {
  fetch?: typeof fetch;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  /** null: no disk cache (in-process sharing still applies). */
  cacheDir?: string | null;
  ttlMs?: number;
  waitBudgetMs?: number;
  /** null: read anonymously. Default: DOCKERHUB_USERNAME with DOCKERHUB_TOKEN or DOCKERHUB_PASSWORD. */
  credentials?: { username: string; secret: string } | null;
  /** The Hub origin that alone gets the credential and the disk cache. */
  origin?: string;
}

export interface HubReader {
  /** One GET. `maxAgeMs` below the TTL asks for a newer answer (0: always the network, then cached). */
  read(url: string, opts?: { maxAgeMs?: number }): Promise<HubRead>;
  stats: HubReadStats;
  /** What the run did, for a gate's last line: requests, cache hits, token, limits. */
  summary(): string;
  /** Why the reads are anonymous when a credential was half-supplied, or why nothing is cached; else null. */
  credentialNote(): string | null;
}

const sha = (s: string): string => createHash('sha256').update(s).digest('hex');

/** The instant a 429 says its limit clears, from Retry-After, RateLimit-Reset or X-RateLimit-Reset; null when none says. Pure. */
export function limitClearsAt(headers: Headers, nowMs: number): number | null {
  const at: number[] = [];
  const ra = headers.get('retry-after')?.trim();
  if (ra !== undefined) {
    if (/^\d+$/.test(ra)) at.push(nowMs + Number(ra) * 1000);
    else {
      const d = Date.parse(ra);
      if (!Number.isNaN(d)) at.push(d);
    }
  }
  const rl = headers.get('ratelimit-reset')?.trim();
  if (rl !== undefined && /^\d+$/.test(rl)) at.push(nowMs + Number(rl) * 1000);
  const xr = headers.get('x-ratelimit-reset')?.trim();
  if (xr !== undefined && /^\d+$/.test(xr)) {
    const n = Number(xr);
    // Hub sends epoch seconds; a small number is a delta from a server that sends that instead.
    at.push(n > 1_000_000_000 ? n * 1000 : nowMs + n * 1000);
  }
  return at.length === 0 ? null : Math.max(...at);
}

/** The `exp` of a JWT in ms, or null when the token carries none readable. Pure. */
export function jwtExpiryMs(token: string): number | null {
  const part = token.split('.')[1];
  if (part === undefined) return null;
  try {
    const exp = (JSON.parse(Buffer.from(part, 'base64url').toString('utf8')) as { exp?: unknown })
      .exp;
    return typeof exp === 'number' && Number.isFinite(exp) ? exp * 1000 : null;
  } catch {
    return null;
  }
}

function envCredentials(): { username: string; secret: string } | null {
  const username = process.env.DOCKERHUB_USERNAME;
  const secret = process.env.DOCKERHUB_TOKEN || process.env.DOCKERHUB_PASSWORD;
  return username && secret ? { username, secret } : null;
}

function readJsonFile(file: string): unknown {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

/** Write through a unique temp name and a rename, so a reader never sees half a file. */
function writeAtomic(file: string, body: string, mode = 0o644): void {
  const tmp = `${file}.${process.pid}.${randomBytes(4).toString('hex')}.tmp`;
  writeFileSync(tmp, body, { mode });
  renameSync(tmp, file);
}

function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === 'EPERM';
  }
}

export function createHubReader(o: HubReaderOptions = {}): HubReader {
  const doFetch = o.fetch ?? fetch;
  const now = o.now ?? Date.now;
  const sleep = o.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const ttl = o.ttlMs ?? HUB_CACHE_TTL_MS;
  const budgetTotal = o.waitBudgetMs ?? HUB_WAIT_BUDGET_MS;
  let budget = budgetTotal;
  const origin = new URL(o.origin ?? HUB_DEFAULT_BASE).origin;
  const creds = o.credentials === undefined ? envCredentials() : o.credentials;
  let dir: string | null = o.cacheDir === undefined ? HUB_CACHE_DIR : o.cacheDir;
  const stats: HubReadStats = {
    network: 0,
    disk: 0,
    memory: 0,
    tokenMints: 0,
    tokenReuse: 0,
    rateLimited: 0,
    limitedSkips: 0,
    waitedMs: 0,
  };
  const inflight = new Map<string, Promise<HubRead>>();
  const memLimit = new Map<string, { untilMs: number; why: string }>();
  const credKey = creds ? sha(`${creds.username}\0${creds.secret}`).slice(0, 16) : '';
  let tokenOnce: Promise<string | null> | null = null;
  let tokenLabel = creds ? 'token' : 'anonymous';
  let note: string | null =
    !creds && process.env.DOCKERHUB_TOKEN && o.credentials === undefined
      ? 'DOCKERHUB_TOKEN is set without DOCKERHUB_USERNAME, so it cannot be exchanged for a Hub API token (a raw token is always HTTP 401); reading anonymously'
      : null;

  const ensureDir = (): string | null => {
    if (dir === null) return null;
    try {
      mkdirSync(dir, { recursive: true });
      return dir;
    } catch {
      note = `${note ? `${note}; ` : ''}the cache directory ${dir} cannot be created, so nothing is cached`;
      dir = null;
      return null;
    }
  };
  const tokenFile = (d: string): string => path.join(d, `token-${credKey}.json`);
  const limitFile = (d: string, who: string): string =>
    path.join(d, `ratelimit-${sha(who).slice(0, 16)}.json`);
  const sleepFor = async (ms: number): Promise<void> => {
    budget -= ms;
    stats.waitedMs += ms;
    await sleep(ms);
  };

  /** Run `fn` holding the lock for `key`, or return `early()` as soon as it answers while waiting. */
  async function withLock<T>(key: string, early: () => T | null, fn: () => Promise<T>): Promise<T> {
    const d = ensureDir();
    if (d === null) return fn();
    const lock = path.join(d, `${key}.lock`);
    for (;;) {
      try {
        const fd = openSync(lock, 'wx');
        writeSync(fd, String(process.pid));
        closeSync(fd);
        break;
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code !== 'EEXIST') return fn();
      }
      const got = early();
      if (got !== null) return got;
      let stale: boolean;
      try {
        const pid = Number(readFileSync(lock, 'utf8'));
        stale =
          // The file system's clock, never the injected one: a lock's mtime is a real instant.
          Date.now() - statSync(lock).mtimeMs > LOCK_STALE_MS ||
          (Number.isInteger(pid) && pid > 0 && pid !== process.pid && !pidAlive(pid));
      } catch {
        // Released between the open and the read: try again at once.
        continue;
      }
      if (stale) {
        try {
          unlinkSync(lock);
        } catch {
          // Another waiter broke it first.
        }
        continue;
      }
      await new Promise<void>((r) => setTimeout(r, LOCK_POLL_MS));
    }
    try {
      const got = early();
      return got !== null ? got : await fn();
    } finally {
      try {
        unlinkSync(lock);
      } catch {
        // Broken as stale by a waiter; nothing to release.
      }
    }
  }

  const cachedAnswer = (file: string, url: string, maxAge: number): HubRead | null => {
    const c = readJsonFile(file) as { url?: unknown; fetchedAtMs?: unknown; json?: unknown } | null;
    if (c === null || c.url !== url || typeof c.fetchedAtMs !== 'number') return null;
    const age = now() - c.fetchedAtMs;
    if (age < 0 || age >= maxAge) return null;
    return { ok: true, json: c.json, source: 'disk' };
  };

  /** The recorded limit for `who` that has not cleared yet (this process's, or a parallel reader's), or null. */
  const activeLimit = (who: string): { untilMs: number; why: string } | null => {
    const d = dir === null ? null : ensureDir();
    const onDisk = d === null ? null : readJsonFile(limitFile(d, who));
    for (const l of [memLimit.get(who), onDisk] as Array<{
      untilMs?: unknown;
      why?: unknown;
    } | null>)
      if (l && typeof l.untilMs === 'number' && l.untilMs > now())
        return { untilMs: l.untilMs, why: typeof l.why === 'string' ? l.why : 'HTTP 429' };
    return null;
  };
  const recordLimit = (who: string, untilMs: number): void => {
    const rec = { untilMs: Math.min(untilMs, now() + LIMIT_RECORD_MAX_MS), why: 'HTTP 429' };
    memLimit.set(who, rec);
    const d = ensureDir();
    if (d !== null) writeAtomic(limitFile(d, who), `${JSON.stringify(rec)}\n`);
  };

  async function mintToken(): Promise<string | null> {
    if (!creds) return null;
    const d = ensureDir();
    const fromDisk = (): string | null => {
      if (d === null) return null;
      const t = readJsonFile(tokenFile(d)) as { token?: unknown; expMs?: unknown } | null;
      return t &&
        typeof t.token === 'string' &&
        typeof t.expMs === 'number' &&
        t.expMs - TOKEN_MARGIN_MS > now()
        ? t.token
        : null;
    };
    const reused = fromDisk();
    if (reused !== null) {
      stats.tokenReuse++;
      return reused;
    }
    return withLock(
      `token-${credKey}`,
      () => {
        const t = fromDisk();
        if (t !== null) stats.tokenReuse++;
        return t;
      },
      async () => {
        stats.tokenMints++;
        try {
          const r = await doFetch(`${origin}/v2/users/login`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ username: creds.username, password: creds.secret }),
            signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
          });
          if (!r.ok) {
            tokenLabel = `anonymous after the token exchange answered HTTP ${r.status}`;
            return null;
          }
          const token = ((await r.json()) as { token?: unknown }).token;
          if (typeof token !== 'string' || token === '') {
            tokenLabel = 'anonymous after the token exchange answered no token';
            return null;
          }
          const expMs = jwtExpiryMs(token) ?? now() + TOKEN_FALLBACK_MS;
          if (d !== null) writeAtomic(tokenFile(d), `${JSON.stringify({ token, expMs })}\n`, 0o600);
          return token;
        } catch (e) {
          tokenLabel = `anonymous after the token exchange failed (${(e as Error).name})`;
          return null;
        }
      }
    );
  }

  const dropToken = (): void => {
    tokenOnce = Promise.resolve(null);
    tokenLabel = 'anonymous after the token was rejected';
    const d = dir === null ? null : ensureDir();
    if (d !== null)
      try {
        unlinkSync(tokenFile(d));
      } catch {
        // Already gone.
      }
  };

  /** One answer from the network: transient retries, one bounded 429 wait, a refused JWT dropped once. */
  async function fromNetwork(url: string, onHub: boolean): Promise<HubRead> {
    let transient = 0;
    let waited429 = false;
    let refused = false;
    for (;;) {
      const bearer = onHub && creds ? await (tokenOnce ??= mintToken()) : null;
      const label = bearer ? 'token' : onHub ? tokenLabel : 'anonymous';
      const who = bearer && creds ? `user:${creds.username}` : 'anonymous';
      const limit = onHub ? activeLimit(who) : null;
      if (limit !== null) {
        const wait = limit.untilMs - now();
        if (waited429 || wait > budget) {
          stats.limitedSkips++;
          return {
            ok: false,
            why: `${limit.why} (${label}; the limit clears ${new Date(limit.untilMs).toISOString()}, past the ${Math.round(budgetTotal / 1000)} s wait budget)`,
            status: 429,
          };
        }
        waited429 = true;
        await sleepFor(wait);
      }
      let r: Response;
      try {
        stats.network++;
        r = await doFetch(url, {
          headers: {
            Accept: 'application/json',
            ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
          },
          signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
        });
      } catch (e) {
        const b = BACKOFF_MS[transient] ?? 0;
        if (++transient < TRANSIENT_TRIES && b <= budget) {
          await sleepFor(b);
          continue;
        }
        return { ok: false, why: `${(e as Error).name} (${label})`, status: null };
      }
      if (r.ok) {
        try {
          return { ok: true, json: await r.json(), source: 'network' };
        } catch {
          return {
            ok: false,
            why: `HTTP ${r.status} with a body that is not JSON (${label})`,
            status: r.status,
          };
        }
      }
      if ((r.status === 401 || r.status === 403) && bearer && !refused) {
        refused = true;
        dropToken();
        continue;
      }
      if (r.status === 429) {
        stats.rateLimited++;
        const clears = limitClearsAt(r.headers, now()) ?? now() + LIMIT_DEFAULT_MS;
        if (onHub) recordLimit(who, clears);
        const wait = Math.max(0, clears - now());
        if (!waited429 && wait <= budget) {
          waited429 = true;
          await sleepFor(wait);
          // The record is for parallel readers; this read has had its one wait.
          memLimit.delete(who);
          continue;
        }
        return {
          ok: false,
          why: `HTTP 429 (${label}; the limit clears ${new Date(clears).toISOString()}${waited429 ? ', after one wait' : `, past the ${Math.round(budgetTotal / 1000)} s wait budget`})`,
          status: 429,
        };
      }
      if (r.status >= 500) {
        const b = BACKOFF_MS[transient] ?? 0;
        if (++transient < TRANSIENT_TRIES && b <= budget) {
          await sleepFor(b);
          continue;
        }
      }
      return { ok: false, why: `HTTP ${r.status} (${label})`, status: r.status };
    }
  }

  async function readOnce(url: string, maxAge: number): Promise<HubRead> {
    let onHub: boolean;
    try {
      onHub = new URL(url).origin === origin;
    } catch {
      return { ok: false, why: 'not a URL', status: null };
    }
    const d = onHub ? ensureDir() : null;
    if (d === null) return fromNetwork(url, onHub);
    const key = sha(url);
    const file = path.join(d, `${key}.json`);
    const hit = (): HubRead | null => {
      const h = cachedAnswer(file, url, maxAge);
      if (h !== null) stats.disk++;
      return h;
    };
    return (
      hit() ??
      withLock(key, hit, async () => {
        const got = await fromNetwork(url, onHub);
        if (got.ok)
          writeAtomic(file, `${JSON.stringify({ url, fetchedAtMs: now(), json: got.json })}\n`);
        return got;
      })
    );
  }

  return {
    stats,
    credentialNote: () => note,
    read(url, opts = {}) {
      const maxAge = Math.min(opts.maxAgeMs ?? ttl, ttl);
      if (maxAge < ttl) return readOnce(url, maxAge);
      const joined = inflight.get(url);
      if (joined !== undefined) {
        stats.memory++;
        return joined;
      }
      const p = readOnce(url, maxAge).finally(() => inflight.delete(url));
      inflight.set(url, p);
      return p;
    },
    summary() {
      const s = stats;
      return (
        `Docker Hub reads: ${s.network} request(s) sent, ${s.disk} answered from the cache (${dir ?? 'disabled'}, TTL ${Math.round(ttl / 3_600_000)} h), ${s.memory} shared in-process; ` +
        `token ${creds ? `${s.tokenMints} minted, ${s.tokenReuse} reused` : 'none (anonymous)'}; ${s.rateLimited} HTTP 429, ${s.limitedSkips} read(s) refused on a recorded limit, waited ${Math.round(s.waitedMs / 1000)} s`
      );
    },
  };
}

let shared: HubReader | null = null;
/** The process's one reader of the real Hub, created on first use. */
export function hubReader(): HubReader {
  shared ??= createHubReader();
  return shared;
}

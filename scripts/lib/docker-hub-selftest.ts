/**
 * Controls for the shared Docker Hub read path (docker-hub.ts `createHubReader`), run against a
 * fake registry: a fetch that answers from a script, counts every request per URL, and holds each
 * answer for a few milliseconds so two readers really overlap. Two reader instances over one cache
 * directory stand for two gates. The clock and the sleep are fake, so a Retry-After of minutes
 * costs nothing and the wait each case asks for is read back exactly.
 *
 * check:ci-docker-image-freshness runs these with its own controls (every run, before it reads
 * the tree); `npx tsx scripts/lib/docker-hub-selftest.ts` runs them alone.
 */
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import {
  createHubReader,
  type HubReaderOptions,
  HUB_WAIT_BUDGET_MS,
  jwtExpiryMs,
  LOCK_STALE_MS,
  limitClearsAt,
} from './docker-hub.js';
import { isEntryPoint } from './entry-point.js';

const HUB = 'https://hub.test';
const A = `${HUB}/v2/repositories/library/node/tags?page_size=100&name=slim`;
const B = `${HUB}/v2/repositories/library/node/tags/26-slim`;
const T0 = Date.parse('2026-11-21T12:00:00Z');

interface Answer {
  status: number;
  body?: unknown;
  headers?: Record<string, string>;
}

/** A fake registry: per-URL scripted answers (the last one repeats), with every request recorded. */
function fakeHub(script: Record<string, Answer[]>, opts: { throws?: boolean } = {}) {
  const calls: Array<{ url: string; auth: string | null; method: string; body: string | null }> =
    [];
  const fetchImpl = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const h = new Headers(init?.headers);
    calls.push({
      url,
      auth: h.get('authorization'),
      method: init?.method ?? 'GET',
      body: typeof init?.body === 'string' ? init.body : null,
    });
    await new Promise((r) => setTimeout(r, 15));
    if (opts.throws) throw Object.assign(new Error('offline'), { name: 'TypeError' });
    const list = script[url] ?? [{ status: 404, body: {} }];
    const n = calls.filter((c) => c.url === url).length;
    const a = list[Math.min(n - 1, list.length - 1)];
    return new Response(a.body === undefined ? '' : JSON.stringify(a.body), {
      status: a.status,
      headers: a.headers,
    });
  }) as typeof fetch;
  return { fetchImpl, calls, gets: (url: string) => calls.filter((c) => c.url === url).length };
}

function clock(start = T0) {
  const c = { t: start, slept: [] as number[] };
  return {
    c,
    now: () => c.t,
    sleep: async (ms: number) => {
      c.slept.push(ms);
      c.t += ms;
    },
  };
}

const jwt = (expS: number): string =>
  `h.${Buffer.from(JSON.stringify({ exp: expS })).toString('base64url')}.s`;

export async function hubReaderCases(): Promise<Array<{ label: string; ok: boolean }>> {
  const out: Array<{ label: string; ok: boolean }> = [];
  const check = (label: string, ok: boolean) => out.push({ label, ok });
  const dirs: string[] = [];
  const tmp = (): string => {
    const d = mkdtempSync(path.join(os.tmpdir(), 'hub-cache-'));
    dirs.push(d);
    return d;
  };
  const reader = (o: HubReaderOptions) => createHubReader({ origin: HUB, credentials: null, ...o });
  const ok200 = (body: unknown): Answer[] => [{ status: 200, body }];

  try {
    // Two gates in parallel, one cache directory: one GET.
    {
      const hub = fakeHub({ [A]: ok200({ results: [{ name: '26-slim' }] }) });
      const dir = tmp();
      const k = clock();
      const g1 = reader({ fetch: hub.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      const g2 = reader({ fetch: hub.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      const [r1, r2] = await Promise.all([g1.read(A), g2.read(A)]);
      check(
        'two readers (two gates) over one cache directory fetch a URL once between them, and both get the answer',
        hub.gets(A) === 1 && r1.ok && r2.ok && g1.stats.disk + g2.stats.disk === 1
      );
      const left = readdirSync(dir).filter((f) => f.endsWith('.lock') || f.endsWith('.tmp'));
      check('no lock or temp file is left behind', left.length === 0);
      // A fresh cached value is reused without the network.
      const g3 = reader({ fetch: hub.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      const r3 = await g3.read(A);
      check(
        'a third reader inside the TTL is answered from disk with no request',
        r3.ok && r3.source === 'disk' && hub.gets(A) === 1 && g3.stats.network === 0
      );
      // An expired value is read again.
      k.c.t += 6 * 3_600_000 + 1;
      const g4 = reader({ fetch: hub.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      const r4 = await g4.read(A);
      check(
        'CONTROL: an answer past its TTL is never served: the reader asks again',
        r4.ok && r4.source === 'network' && hub.gets(A) === 2
      );
      const g5 = reader({ fetch: hub.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      await g5.read(A, { maxAgeMs: 0 });
      check(
        'maxAgeMs 0 (a plan about to write) goes to the network even with a fresh answer cached',
        hub.gets(A) === 3
      );
    }
    // CONTROL for the parallel case: with no shared directory the same pair sends two GETs, so the
    // one-GET result above is the cache's doing and not the fake's.
    {
      const hub = fakeHub({ [A]: ok200({ results: [] }) });
      const k = clock();
      const g1 = reader({ fetch: hub.fetchImpl, cacheDir: null, now: k.now, sleep: k.sleep });
      const g2 = reader({ fetch: hub.fetchImpl, cacheDir: null, now: k.now, sleep: k.sleep });
      await Promise.all([g1.read(A), g2.read(A)]);
      check(
        'CONTROL: two readers with no shared cache send two GETs (the counter sees doubles)',
        hub.gets(A) === 2
      );
      const g = reader({ fetch: hub.fetchImpl, cacheDir: null, now: k.now, sleep: k.sleep });
      await Promise.all([g.read(A), g.read(A), g.read(A)]);
      check(
        'three concurrent reads of one URL in one process share a single GET',
        hub.gets(A) === 3 && g.stats.memory === 2
      );
    }
    // 429 with Retry-After: one bounded wait, then unknown; and never cached.
    {
      const hub = fakeHub({
        [A]: [{ status: 429, headers: { 'retry-after': '5' } }],
      });
      const dir = tmp();
      const k = clock();
      const g = reader({ fetch: hub.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      const r = await g.read(A);
      check(
        'a 429 with Retry-After 5 waits exactly 5 s once, asks again, and on a second 429 reports unknown naming the 429',
        !r.ok && r.why.includes('HTTP 429') && k.c.slept.join() === '5000' && hub.gets(A) === 2
      );
      const files = readdirSync(dir).filter((f) => !f.startsWith('ratelimit-'));
      check('CONTROL: a 429 is never written to the cache as an answer', files.length === 0);
      k.c.t += 60_000;
      const hub2 = fakeHub({ [A]: ok200({ results: [] }) });
      const g2 = reader({ fetch: hub2.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      const r2 = await g2.read(A);
      check(
        'after a 429 a later reader asks the network again, and its 200 is cached',
        r2.ok && r2.source === 'network' && hub2.gets(A) === 1
      );
    }
    {
      const hub = fakeHub({
        [A]: [
          { status: 429, headers: { 'retry-after': '3' } },
          { status: 200, body: { results: [] } },
        ],
      });
      const k = clock();
      const g = reader({ fetch: hub.fetchImpl, cacheDir: tmp(), now: k.now, sleep: k.sleep });
      const r = await g.read(A);
      check(
        'a 429 whose Retry-After fits the budget is waited out and the retry answers',
        r.ok && k.c.slept.join() === '3000'
      );
    }
    {
      const hub = fakeHub({
        [A]: [{ status: 429, headers: { 'retry-after': '120' } }],
        [B]: ok200({}),
      });
      const dir = tmp();
      const k = clock();
      const g = reader({ fetch: hub.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      const r = await g.read(A);
      check(
        'CONTROL: a 429 asking for 120 s, past the 60 s budget, is unknown at once with no sleep (bounded)',
        !r.ok && r.why.includes('HTTP 429') && k.c.slept.length === 0 && hub.gets(A) === 1
      );
      const g2 = reader({ fetch: hub.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep });
      const r2 = await g2.read(B);
      check(
        'a parallel reader honours the recorded limit: unknown, with no request sent',
        !r2.ok && r2.status === 429 && hub.gets(B) === 0 && g2.stats.limitedSkips === 1
      );
      const hub3 = fakeHub({
        [A]: [{ status: 429, headers: { 'retry-after': '8' } }],
        [B]: [{ status: 429, headers: { 'retry-after': '8' } }],
      });
      const m = reader({
        fetch: hub3.fetchImpl,
        cacheDir: null,
        now: k.now,
        sleep: k.sleep,
        waitBudgetMs: 10_000,
      });
      const before = k.c.slept.length;
      await m.read(A);
      await m.read(B);
      const slept = k.c.slept.slice(before).reduce((x, y) => x + y, 0);
      check(
        'the wait budget is per process: two 8 s waits do not fit a 10 s budget',
        slept === 8000 && m.stats.waitedMs === 8000
      );
    }
    // Offline and expired cache stay honest.
    {
      const dir = tmp();
      const k = clock();
      const up = fakeHub({ [A]: ok200({ results: [] }) });
      await reader({ fetch: up.fetchImpl, cacheDir: dir, now: k.now, sleep: k.sleep }).read(A);
      k.c.t += 7 * 3_600_000;
      const down = fakeHub({}, { throws: true });
      const r = await reader({
        fetch: down.fetchImpl,
        cacheDir: dir,
        now: k.now,
        sleep: k.sleep,
      }).read(A);
      check(
        'CONTROL: offline with only an expired answer cached is unknown, never the stale answer',
        !r.ok && r.why.includes('TypeError') && down.gets(A) === 3
      );
    }
    // One token per credential, reused across readers; a raw secret is never a Bearer.
    {
      const token = jwt(Math.floor(T0 / 1000) + 3600);
      const hub = fakeHub({
        [`${HUB}/v2/users/login`]: ok200({ token }),
        [A]: ok200({ results: [] }),
        [B]: ok200({ digest: `sha256:${'a'.repeat(64)}` }),
      });
      const dir = tmp();
      const k = clock();
      const credentials = { username: 'u', secret: 'dckr_pat_x' };
      const g1 = reader({
        fetch: hub.fetchImpl,
        cacheDir: dir,
        now: k.now,
        sleep: k.sleep,
        credentials,
      });
      const g2 = reader({
        fetch: hub.fetchImpl,
        cacheDir: dir,
        now: k.now,
        sleep: k.sleep,
        credentials,
      });
      await Promise.all([g1.read(A), g2.read(B)]);
      const data = hub.calls.filter((c) => c.method === 'GET');
      check(
        'two readers with one credential mint one token between them and send it on every read',
        hub.gets(`${HUB}/v2/users/login`) === 1 &&
          data.length === 2 &&
          data.every((c) => c.auth === `Bearer ${token}`)
      );
      check(
        'CONTROL: the raw secret is never sent as a Bearer',
        !hub.calls.some((c) => c.auth?.includes('dckr_pat_x'))
      );
      const files = readdirSync(dir).filter((f) => f.startsWith('token-'));
      check(
        'the token is kept on disk under a name that carries neither the username nor the secret',
        files.length === 1 && !files[0].includes('u.') && !files[0].includes('dckr')
      );
      k.c.t += 3600_000;
      const g3 = reader({
        fetch: hub.fetchImpl,
        cacheDir: dir,
        now: k.now,
        sleep: k.sleep,
        credentials,
        ttlMs: 1,
      });
      await g3.read(A);
      check(
        'CONTROL: a token at its expiry is minted again, not reused',
        hub.gets(`${HUB}/v2/users/login`) === 2
      );
    }
    {
      const hub = fakeHub({
        [`${HUB}/v2/users/login`]: ok200({ token: jwt(Math.floor(T0 / 1000) + 3600) }),
        [A]: [{ status: 401 }, { status: 200, body: { results: [] } }],
      });
      const k = clock();
      const g = reader({
        fetch: hub.fetchImpl,
        cacheDir: tmp(),
        now: k.now,
        sleep: k.sleep,
        credentials: { username: 'u', secret: 's' },
      });
      const r = await g.read(A);
      const gets = hub.calls.filter((c) => c.url === A);
      check(
        'a token a read refuses is dropped and the read retried anonymously (a rejected credential is never worse than none)',
        r.ok && gets.length === 2 && gets[0].auth !== null && gets[1].auth === null
      );
    }
    {
      const saved = { u: process.env.DOCKERHUB_USERNAME, t: process.env.DOCKERHUB_TOKEN };
      delete process.env.DOCKERHUB_USERNAME;
      process.env.DOCKERHUB_TOKEN = 'dckr_pat_y';
      try {
        const hub = fakeHub({ [A]: ok200({ results: [] }) });
        const g = createHubReader({ origin: HUB, fetch: hub.fetchImpl, cacheDir: null });
        await g.read(A);
        check(
          'DOCKERHUB_TOKEN without DOCKERHUB_USERNAME is named and not sent (a raw token is always a 401)',
          (g.credentialNote() ?? '').includes('without DOCKERHUB_USERNAME') &&
            hub.calls.every((c) => c.auth === null)
        );
      } finally {
        if (saved.u === undefined) delete process.env.DOCKERHUB_USERNAME;
        else process.env.DOCKERHUB_USERNAME = saved.u;
        if (saved.t === undefined) delete process.env.DOCKERHUB_TOKEN;
        else process.env.DOCKERHUB_TOKEN = saved.t;
      }
    }
    // A stub origin gets no credential and no disk cache.
    {
      const stub = 'http://127.0.0.1:9/v2/repositories/library/node/tags/26-slim';
      const hub = fakeHub({
        [`${HUB}/v2/users/login`]: ok200({ token: jwt(Math.floor(T0 / 1000) + 3600) }),
        [stub]: ok200({}),
      });
      const dir = tmp();
      const k = clock();
      const g = reader({
        fetch: hub.fetchImpl,
        cacheDir: dir,
        now: k.now,
        sleep: k.sleep,
        credentials: { username: 'u', secret: 's' },
      });
      await g.read(stub);
      check(
        'a URL off the Hub origin (a stub) is read with no credential and never cached',
        hub.calls.every((c) => c.auth === null) &&
          hub.gets(`${HUB}/v2/users/login`) === 0 &&
          readdirSync(dir).length === 0
      );
    }
    // The pure helpers.
    check(
      'Retry-After seconds, Retry-After as a date, RateLimit-Reset and an epoch X-RateLimit-Reset all name the instant; no header names none',
      limitClearsAt(new Headers({ 'retry-after': '7' }), T0) === T0 + 7000 &&
        limitClearsAt(new Headers({ 'retry-after': new Date(T0 + 9000).toUTCString() }), T0) ===
          T0 + 9000 &&
        limitClearsAt(new Headers({ 'ratelimit-reset': '4' }), T0) === T0 + 4000 &&
        limitClearsAt(new Headers({ 'x-ratelimit-reset': String(T0 / 1000 + 30) }), T0) ===
          T0 + 30_000 &&
        limitClearsAt(new Headers(), T0) === null
    );
    check(
      'a JWT `exp` is read, and a token with none reads null',
      jwtExpiryMs(jwt(100)) === 100_000 && jwtExpiryMs('opaque') === null
    );
    // A live holder can sleep the whole wait budget and then spend three 15 s request timeouts, so a lock younger than that is never a dead holder's (review 0b9643fc.3). The literals are the bound's own inputs, spelled out so a later edit back to a smaller number goes red.
    check(
      "a lock goes stale only after a live holder's worst case: the wait budget plus three request timeouts",
      LOCK_STALE_MS > HUB_WAIT_BUDGET_MS + 3 * 15_000 && LOCK_STALE_MS > 90_000
    );
  } finally {
    for (const d of dirs) rmSync(d, { recursive: true, force: true });
  }
  return out;
}

if (isEntryPoint(import.meta.filename)) {
  const cases = await hubReaderCases();
  for (const c of cases) console.log(`  ${c.ok ? 'PASS' : 'FAIL'}  ${c.label}`);
  const bad = cases.filter((c) => !c.ok).length;
  console.log(
    bad === 0
      ? `\n${cases.length}/${cases.length} controls pass`
      : `\n${bad} of ${cases.length} failed`
  );
  process.exit(bad === 0 ? 0 : 1);
}

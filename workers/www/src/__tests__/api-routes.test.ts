import { createHmac } from 'node:crypto';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { WK_SITE_ORIGIN } from '../../../../packages/shared/src/config/well-known.generated.js';
import { lookupKey, normalizeDomain } from '../enterprise-lookup';
import worker from '../index';

const SITE = new URL(WK_SITE_ORIGIN).host;
const PEPPER = 'test-pepper';

type Env = Parameters<typeof worker.fetch>[1];

function kv(entries: Record<string, string>): KVNamespace {
  return {
    get: vi.fn((key: string) => Promise.resolve(entries[key] ?? null)),
  } as unknown as KVNamespace;
}

function env(extra: Record<string, unknown> = {}): Env {
  const ASSETS = { fetch: vi.fn(() => Promise.resolve(new Response('asset'))) };
  return { ASSETS, ...extra } as unknown as Env;
}

function lookup(body: unknown, e: Env, method = 'POST'): Promise<Response> {
  const raw = typeof body === 'string' ? body : JSON.stringify(body);
  return worker.fetch(
    new Request(`https://${SITE}/api/enterprise-lookup`, {
      method,
      headers: { 'content-type': 'application/json' },
      body: method === 'POST' ? raw : undefined,
    }),
    e
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('GET /api/geo', () => {
  test('answers the edge country with no-store', async () => {
    const req = new Request(`https://${SITE}/api/geo`);
    Object.defineProperty(req, 'cf', { value: { country: 'DE' } });
    const res = await worker.fetch(req, env());
    expect(res.status).toBe(200);
    expect(res.headers.get('cache-control')).toBe('no-store');
    expect(await res.json()).toEqual({ country: 'DE' });
  });

  test('answers null when Cloudflare has no country', async () => {
    const res = await worker.fetch(new Request(`https://${SITE}/api/geo`), env());
    expect(await res.json()).toEqual({ country: null });
  });

  test('treats XX and T1 as unknown', async () => {
    for (const country of ['XX', 'T1']) {
      const req = new Request(`https://${SITE}/api/geo`);
      Object.defineProperty(req, 'cf', { value: { country } });
      expect(await (await worker.fetch(req, env())).json()).toEqual({ country: null });
    }
  });
});

describe('normalizeDomain', () => {
  test('lowercases and drops one trailing dot', () => {
    expect(normalizeDomain(' Acme.Example. ')).toBe('acme.example');
  });
  test('refuses an address, a single label and non-strings', () => {
    expect(normalizeDomain('a@acme.example')).toBeNull();
    expect(normalizeDomain('localhost')).toBeNull();
    expect(normalizeDomain(42)).toBeNull();
    expect(normalizeDomain('-a.example')).toBeNull();
  });
  test('punycodes a unicode name like the writer does', () => {
    expect(normalizeDomain('Bücher.example')).toBe('xn--bcher-kva.example');
  });
});

describe('lookupKey', () => {
  test('is the hex HMAC-SHA256 of the domain under the pepper', async () => {
    const want = createHmac('sha256', PEPPER).update('acme.example').digest('hex');
    expect(await lookupKey(PEPPER, 'acme.example')).toBe(want);
  });
});

describe('POST /api/enterprise-lookup', () => {
  // Siteverify answers success for the token 'good' only; every lookup env carries the secret.
  const SECRET = { CLOUDFLARE_TURNSTILE_SECRET_KEY: 's' };
  const siteverify = () =>
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        const ok = (init.body as FormData).get('response') === 'good';
        return Promise.resolve(new Response(JSON.stringify({ success: ok })));
      })
    );

  test('a hit answers the host and a miss answers the same shape', async () => {
    siteverify();
    const key = await lookupKey(PEPPER, 'acme.example');
    const e = env({
      ENTERPRISE_LOOKUP: kv({ [key]: 'acme.rediacc.cloud' }),
      ENTERPRISE_LOOKUP_PEPPER: PEPPER,
      ...SECRET,
    });
    const hit = await lookup({ domain: 'ACME.example', turnstileToken: 'good' }, e);
    expect(hit.headers.get('cache-control')).toBe('no-store');
    expect(await hit.json()).toEqual({ host: 'acme.rediacc.cloud' });
    const miss = await lookup({ domain: 'unknown.example', turnstileToken: 'good' }, e);
    expect(await miss.json()).toEqual({ host: null });
    const bad = await lookup({ domain: 'not a domain', turnstileToken: 'good' }, e);
    expect(bad.status).toBe(200);
    expect(await bad.json()).toEqual({ host: null });
  });

  test('refuses other methods and bodies that are not JSON objects', async () => {
    const e = env({ ENTERPRISE_LOOKUP: kv({}), ENTERPRISE_LOOKUP_PEPPER: PEPPER, ...SECRET });
    expect((await lookup(null, e, 'GET')).status).toBe(405);
    expect((await lookup('{nope', e)).status).toBe(400);
    expect((await lookup('null', e)).status).toBe(400);
    expect((await lookup('x'.repeat(5000), e)).status).toBe(400);
    // The cap counts bytes: 700 three-byte characters are 2100 bytes but 700 UTF-16 units.
    expect((await lookup(JSON.stringify({ domain: '€'.repeat(700) }), e)).status).toBe(400);
  });

  test('is unavailable without the binding, the pepper or the Turnstile secret', async () => {
    expect((await lookup({ domain: 'a.example' }, env(SECRET))).status).toBe(503);
    expect(
      (await lookup({ domain: 'a.example' }, env({ ENTERPRISE_LOOKUP: kv({}), ...SECRET }))).status
    ).toBe(503);
    // Review 11ccb9e8.1: no secret means no anonymous lookups, not an open route.
    const noSecret = env({ ENTERPRISE_LOOKUP: kv({}), ENTERPRISE_LOOKUP_PEPPER: PEPPER });
    expect((await lookup({ domain: 'a.example', turnstileToken: 'good' }, noSecret)).status).toBe(
      503
    );
  });

  test('checks Turnstile on every lookup', async () => {
    siteverify();
    const e = env({ ENTERPRISE_LOOKUP: kv({}), ENTERPRISE_LOOKUP_PEPPER: PEPPER, ...SECRET });
    expect((await lookup({ domain: 'a.example' }, e)).status).toBe(403);
    expect((await lookup({ domain: 'a.example', turnstileToken: 'bad' }, e)).status).toBe(403);
    const ok = await lookup({ domain: 'a.example', turnstileToken: 'good' }, e);
    expect(ok.status).toBe(200);
    expect(await ok.json()).toEqual({ host: null });
  });

  test('answers 429 when the rate limiter refuses', async () => {
    const e = env({
      ENTERPRISE_LOOKUP: kv({}),
      ENTERPRISE_LOOKUP_PEPPER: PEPPER,
      ...SECRET,
      LOOKUP_RATE_LIMIT: { limit: () => Promise.resolve({ success: false }) },
    });
    expect((await lookup({ domain: 'a.example' }, e)).status).toBe(429);
  });
});

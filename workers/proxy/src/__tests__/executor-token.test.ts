/**
 * The issued executor token, the container egress allowlist with its bearer swap, and `/v1/ready` (agent/plans/PLAN-proxy-cd-six-targets.md box P1).
 *
 * Adversarial: each test plays the container (or a poller) trying to get something it must not, and the ISSUER and ACCOUNT bindings are fakes that count every call.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@cloudflare/containers', () => ({
  ContainerProxy: class {},
  Container: class {
    static outboundByHost: unknown;
    constructor(
      readonly ctx: unknown,
      readonly env: unknown
    ) {}
  },
  getContainer: () => ({ fetch: () => Promise.resolve(new Response('container')) }),
}));

import { forwardAccountEgress } from '../egress';
import worker, { type Env, ExecutorContainer } from '../index';
import {
  type ExecutorIssuerRpc,
  FAILURE_BACKOFF_MS,
  type IssuedToken,
  IssuerError,
  issuedToken,
  resetIssuedTokenCache,
} from '../issued-token';
import { READY_CACHE_MS, readiness, resetReadyCache } from '../ready';

const ACCOUNT_URL = 'https://account.test';
const ISSUED = 'rdt_issued_executor_token';
const PLACEHOLDER = 'rediacc-executor-placeholder';
const CALLER = 'rdt_caller_token';
const HOST = 'http://account.internal';
const API = `${HOST}/account/api/v1`;
const VERSION_ID = '5b0e7d5c-0000-4000-8000-000000000001';

interface CountingIssuer {
  binding: Service<ExecutorIssuerRpc>;
  issues: number;
  fetches: number;
}

function countingIssuer(answer: () => Promise<IssuedToken>): CountingIssuer {
  const counts: CountingIssuer = { binding: null as never, issues: 0, fetches: 0 };
  counts.binding = {
    issue: () => {
      counts.issues += 1;
      return answer();
    },
    fetch: () => {
      counts.fetches += 1;
      return Promise.resolve(new Response('issuer fetch must never be called', { status: 500 }));
    },
  } as unknown as Service<ExecutorIssuerRpc>;
  return counts;
}

function minting(lifeMs = 45 * 60_000): CountingIssuer {
  return countingIssuer(() =>
    Promise.resolve({ token: ISSUED, expiresAt: new Date(Date.now() + lifeMs).toISOString() })
  );
}

interface CountingAccount {
  binding: Fetcher;
  seen: Request[];
}

function countingAccount(
  answer: (req: Request) => Response = () => Response.json({})
): CountingAccount {
  const seen: Request[] = [];
  const binding = {
    fetch: (input: Request | string, init?: RequestInit) => {
      const req = input instanceof Request ? input : new Request(input, init);
      seen.push(req);
      return Promise.resolve(answer(req));
    },
  } as unknown as Fetcher;
  return { binding, seen };
}

function env(issuer: CountingIssuer, account: CountingAccount, extra: Partial<Env> = {}): Env {
  return {
    EXECUTOR: null as never,
    ACCOUNT_URL,
    ACCOUNT: account.binding,
    ISSUER: issuer.binding,
    ...extra,
  };
}

function egress(path: string, init: RequestInit = {}): Request {
  return new Request(`${API}${path}`, init);
}

const BEARER_PATHS = [
  '/proxy/introspect',
  '/licenses/audit-events',
  '/configs/executor-token',
  '/configs/executor-grant',
] as const;

/** Requests the allowlist must refuse, each with the reason code it logs. */
const REFUSED: [string, Request, string][] = [
  ['an unlisted account path', egress('/admin/users'), 'route-not-allowed'],
  ['a path outside the account API', new Request(`${HOST}/admin/secrets`), 'route-not-allowed'],
  ['an issuer-looking path', egress('/executor/issue', { method: 'POST' }), 'route-not-allowed'],
  ['GET on a POST-only executor path', egress('/proxy/introspect'), 'route-not-allowed'],
  [
    'POST on the config pull',
    egress('/configs/cfg-1', { method: 'POST', body: '{}' }),
    'route-not-allowed',
  ],
  ['a nested config path', egress('/configs/cfg-1/members'), 'route-not-allowed'],
  ['an encoded slash in the config id', egress('/configs/cfg%2F1'), 'route-not-allowed'],
  [
    'DELETE on telemetry config',
    egress('/telemetry/config', { method: 'DELETE' }),
    'route-not-allowed',
  ],
  [
    'a query on an executor path',
    egress('/proxy/introspect?as=admin', {
      method: 'POST',
      headers: { authorization: `Bearer ${PLACEHOLDER}` },
    }),
    'query-not-allowed',
  ],
  ['an unknown query on the config pull', egress('/configs/cfg-1?all=1'), 'query-not-allowed'],
  [
    'a caller token on an executor path',
    egress('/proxy/introspect', { method: 'POST', headers: { authorization: `Bearer ${CALLER}` } }),
    'bearer-not-placeholder',
  ],
  [
    'the placeholder in a different spelling',
    egress('/licenses/audit-events', {
      method: 'POST',
      headers: { authorization: `bearer ${PLACEHOLDER}` },
    }),
    'bearer-not-placeholder',
  ],
  [
    'the issued token itself, replayed',
    egress('/configs/executor-grant', {
      method: 'POST',
      headers: { authorization: `Bearer ${ISSUED}` },
    }),
    'bearer-not-placeholder',
  ],
  [
    'no Authorization on an executor path',
    egress('/configs/executor-token', { method: 'POST' }),
    'bearer-missing',
  ],
];

beforeEach(() => {
  resetIssuedTokenCache();
  resetReadyCache();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('container egress allowlist', () => {
  for (const [name, req, reason] of REFUSED) {
    it(`refuses ${name} with 403 ${reason}, forwards nothing and mints nothing`, async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      const issuer = minting();
      const account = countingAccount();
      const publicFetch = vi.fn(() => Promise.resolve(new Response('escaped')));
      vi.stubGlobal('fetch', publicFetch);

      const response = await forwardAccountEgress(req, env(issuer, account));

      expect(response.status).toBe(403);
      expect(await response.json()).toMatchObject({ reason });
      expect(account.seen).toEqual([]);
      expect(publicFetch).not.toHaveBeenCalled();
      expect(issuer.issues).toBe(0);
      expect(issuer.fetches).toBe(0);
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining(`account egress refused: ${reason}`)
      );
    });
  }

  for (const path of BEARER_PATHS) {
    it(`swaps the placeholder for the issued token on POST ${path}, and the placeholder never leaves`, async () => {
      const issuer = minting();
      const account = countingAccount();
      const response = await forwardAccountEgress(
        egress(path, {
          method: 'POST',
          headers: { authorization: `Bearer ${PLACEHOLDER}`, 'content-type': 'application/json' },
          body: JSON.stringify({ sessionId: 's-1' }),
        }),
        env(issuer, account)
      );

      expect(response.status).toBe(200);
      expect(account.seen).toHaveLength(1);
      const sent = account.seen[0] as Request;
      expect(sent.url).toBe(`${ACCOUNT_URL}/account/api/v1${path}`);
      expect(sent.headers.get('authorization')).toBe(`Bearer ${ISSUED}`);
      expect(JSON.stringify([...sent.headers])).not.toContain(PLACEHOLDER);
      expect(await sent.json()).toEqual({ sessionId: 's-1' });
    });
  }

  const OPEN: [string, Request][] = [
    [
      'GET telemetry/config',
      egress('/telemetry/config', { headers: { authorization: `Bearer ${CALLER}` } }),
    ],
    [
      'GET .well-known/server-info',
      egress('/.well-known/server-info', { headers: { authorization: `Bearer ${PLACEHOLDER}` } }),
    ],
    [
      'GET configs/<id>?teamId=',
      egress('/configs/cfg_1-A?teamId=team-1', {
        headers: { authorization: `Bearer ${PLACEHOLDER}`, 'x-config-token': 'ct-1' },
      }),
    ],
  ];
  for (const [name, req] of OPEN) {
    it(`forwards ${name} with no Authorization at all, and mints nothing`, async () => {
      const issuer = minting();
      const account = countingAccount();
      const response = await forwardAccountEgress(req, env(issuer, account));

      expect(response.status).toBe(200);
      expect(account.seen).toHaveLength(1);
      expect(account.seen[0]?.headers.get('authorization')).toBeNull();
      expect(issuer.issues).toBe(0);
    });
  }

  it('keeps the X-Config-Token and the teamId query on the config pull', async () => {
    const account = countingAccount();
    await forwardAccountEgress(
      egress('/configs/cfg-1?teamId=team-1', { headers: { 'x-config-token': 'ct-1' } }),
      env(minting(), account)
    );
    expect(account.seen[0]?.url).toBe(`${ACCOUNT_URL}/account/api/v1/configs/cfg-1?teamId=team-1`);
    expect(account.seen[0]?.headers.get('x-config-token')).toBe('ct-1');
  });

  it('no egress request ever reaches the ISSUER: with a warm token, every path counts zero issuer calls', async () => {
    const issuer = minting();
    const account = countingAccount();
    const e = env(issuer, account);
    await issuedToken(e.ISSUER);
    expect(issuer.issues).toBe(1);

    for (const [, req] of REFUSED) await forwardAccountEgress(req.clone(), e);
    for (const path of BEARER_PATHS) {
      await forwardAccountEgress(
        egress(path, {
          method: 'POST',
          headers: { authorization: `Bearer ${PLACEHOLDER}` },
          body: '{}',
        }),
        e
      );
    }
    for (const [, req] of OPEN) await forwardAccountEgress(req.clone(), e);

    expect(issuer.issues).toBe(1);
    expect(issuer.fetches).toBe(0);
    // Every forward that left went to ACCOUNT, and only the allowlisted ones did.
    expect(account.seen).toHaveLength(BEARER_PATHS.length + OPEN.length);
  });

  it('answers 503 issuer-refused on an executor path when no token can be had, forwarding nothing', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const account = countingAccount();
    const issuer = countingIssuer(() => Promise.reject(new Error('subscription lapsed')));
    const response = await forwardAccountEgress(
      egress('/proxy/introspect', {
        method: 'POST',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
      }),
      env(issuer, account)
    );
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ reason: 'issuer-refused' });
    expect(account.seen).toEqual([]);
  });

  it('the container env holds the placeholder, never the issued token, after a swap', async () => {
    const issuer = minting();
    const account = countingAccount();
    const e = env(issuer, account);
    await forwardAccountEgress(
      egress('/proxy/introspect', {
        method: 'POST',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
      }),
      e
    );
    const vars = new ExecutorContainer({} as never, e).envVars;
    expect(vars.REDIACC_TOKEN).toBe(PLACEHOLDER);
    expect(JSON.stringify(vars)).not.toContain(ISSUED);
  });
});

describe('issued token cache', () => {
  const T0 = Date.parse('2026-10-25T12:00:00Z');
  const LIFE = 1_000_000;

  it('renews exactly once at 80% of life under 10 concurrent requests', async () => {
    let clock = T0;
    let serial = 0;
    const issuer = countingIssuer(async () => {
      serial += 1;
      // Yield, so the concurrent callers really overlap the in-flight issue().
      await new Promise((resolve) => setTimeout(resolve, 5));
      return { token: `tok-${serial}`, expiresAt: new Date(clock + LIFE).toISOString() };
    });
    const now = () => clock;
    const burst = () =>
      Promise.all(Array.from({ length: 10 }, () => issuedToken(issuer.binding, now)));

    expect(new Set(await burst())).toEqual(new Set(['tok-1']));
    expect(issuer.issues).toBe(1);

    clock = T0 + 0.8 * LIFE - 1;
    expect(new Set(await burst())).toEqual(new Set(['tok-1']));
    expect(issuer.issues).toBe(1);

    clock = T0 + 0.8 * LIFE;
    expect(new Set(await burst())).toEqual(new Set(['tok-2']));
    expect(issuer.issues).toBe(2);
  });

  it('serves the unexpired token when a renewal fails, and refuses once it has expired', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    let clock = T0;
    let answer = (): Promise<IssuedToken> =>
      Promise.resolve({ token: ISSUED, expiresAt: new Date(clock + LIFE).toISOString() });
    const issuer = countingIssuer(() => answer());
    const now = () => clock;
    await issuedToken(issuer.binding, now);
    answer = () => Promise.reject(new Error('down'));
    clock = T0 + 0.9 * LIFE;
    expect(await issuedToken(issuer.binding, now)).toBe(ISSUED);
    clock = T0 + LIFE;
    await expect(issuedToken(issuer.binding, now)).rejects.toMatchObject({
      reason: 'issuer-refused',
    });
  });

  const MALFORMED: [string, unknown][] = [
    ['an empty token', { token: '', expiresAt: '2099-01-01T00:00:00Z' }],
    ['a missing expiry', { token: ISSUED }],
    ['an unparseable expiry', { token: ISSUED, expiresAt: 'soon' }],
    ['an expiry in the past', { token: ISSUED, expiresAt: '2000-01-01T00:00:00Z' }],
    ['no answer', undefined],
  ];
  for (const [name, answer] of MALFORMED) {
    it(`refuses ${name} as issuer-malformed`, async () => {
      const issuer = countingIssuer(() => Promise.resolve(answer as IssuedToken));
      await expect(issuedToken(issuer.binding)).rejects.toMatchObject({
        reason: 'issuer-malformed',
      });
    });
  }

  it('refuses no binding as no-issuer', async () => {
    await expect(issuedToken(undefined)).rejects.toBeInstanceOf(IssuerError);
  });
});

describe('/v1/ready', () => {
  function introspecting(answer: Record<string, unknown> | number): CountingAccount {
    return countingAccount(() =>
      typeof answer === 'number' ? new Response('no', { status: answer }) : Response.json(answer)
    );
  }
  const ACTIVE = { active: true, scopes: ['proxy:exec', 'audit:write'], orgId: 'org-1' };
  const metadata = { CF_VERSION_METADATA: { id: VERSION_ID, tag: '', timestamp: '' } };

  async function ready(e: Env): Promise<{ status: number; body: unknown }> {
    const response = await worker.fetch(new Request('https://proxy.test/v1/ready'), e);
    return { status: response.status, body: await response.json() };
  }

  it('answers 200 with the worker version after introspecting the issued token itself', async () => {
    const account = introspecting(ACTIVE);
    const result = await ready(env(minting(), account, metadata));

    expect(result).toEqual({ status: 200, body: { ready: true, workerVersion: VERSION_ID } });
    expect(account.seen).toHaveLength(1);
    const sent = account.seen[0] as Request;
    expect(sent.url).toBe(`${ACCOUNT_URL}/account/api/v1/proxy/introspect`);
    expect(sent.headers.get('authorization')).toBe(`Bearer ${ISSUED}`);
    expect(await sent.json()).toEqual({ token: ISSUED, self: true });
  });

  it('answers 503 issuer-refused when the issuer throws, without asking the account server', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const account = introspecting(ACTIVE);
    const issuer = countingIssuer(() => Promise.reject(new Error('owner is not admin')));
    const result = await ready(env(issuer, account, metadata));

    expect(result).toEqual({ status: 503, body: { ready: false, reason: 'issuer-refused' } });
    expect(account.seen).toEqual([]);
  });

  it('carries an ISSUER_ reason code into the readiness reason, but never free text', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const coded = countingIssuer(() => Promise.reject(new Error('ISSUER_ROLE_REVOKED')));
    expect(await ready(env(coded, introspecting(ACTIVE), metadata))).toEqual({
      status: 503,
      body: { ready: false, reason: 'issuer-refused:ISSUER_ROLE_REVOKED' },
    });
    resetIssuedTokenCache();
    resetReadyCache();
    const text = countingIssuer(() => Promise.reject(new Error('ISSUER_X for org acme')));
    expect(await ready(env(text, introspecting(ACTIVE), metadata))).toEqual({
      status: 503,
      body: { ready: false, reason: 'issuer-refused' },
    });
  });

  it('asks a failing issuer at most once per backoff window, then again after it', async () => {
    let clock = 1_000;
    const now = () => clock;
    const issuer = countingIssuer(() => Promise.reject(new Error('ISSUER_ROLE_REVOKED')));
    for (let i = 0; i < 5; i += 1) {
      await expect(issuedToken(issuer.binding, now)).rejects.toMatchObject({
        reason: 'issuer-refused:ISSUER_ROLE_REVOKED',
      });
    }
    expect(issuer.issues).toBe(1);
    clock += FAILURE_BACKOFF_MS;
    await expect(issuedToken(issuer.binding, now)).rejects.toBeInstanceOf(IssuerError);
    expect(issuer.issues).toBe(2);
  });

  const NOT_READY: [string, Record<string, unknown> | number, string][] = [
    ['an inactive token', { active: false }, 'inactive'],
    [
      'a token without proxy:exec',
      { active: true, scopes: ['audit:write'] },
      'no-proxy-exec-scope',
    ],
    [
      'a token without audit:write',
      { active: true, scopes: ['proxy:exec'] },
      'no-audit-write-scope',
    ],
    ['an introspection failure', 403, 'introspect-http-403'],
  ];
  for (const [name, answer, reason] of NOT_READY) {
    it(`answers 503 ${reason} for ${name}`, async () => {
      vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      expect(await ready(env(minting(), introspecting(answer), metadata))).toEqual({
        status: 503,
        body: { ready: false, reason },
      });
    });
  }

  it('answers 503 no-version-metadata without the [version_metadata] binding, and mints nothing', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const issuer = minting();
    expect(await ready(env(issuer, introspecting(ACTIVE)))).toEqual({
      status: 503,
      body: { ready: false, reason: 'no-version-metadata' },
    });
    expect(issuer.issues).toBe(0);
  });

  it('caches the answer for 30 s, ready or not, so polling cannot drive mints or introspections', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    let clock = 1_000;
    const now = () => clock;
    const issuer = countingIssuer(() => Promise.reject(new Error('down')));
    const account = introspecting(ACTIVE);
    const e = env(issuer, account, metadata);

    await Promise.all(Array.from({ length: 10 }, () => readiness(e, now)));
    clock += READY_CACHE_MS - 1;
    expect((await readiness(e, now)).status).toBe(503);
    expect(issuer.issues).toBe(1);

    clock += 1;
    await readiness(e, now);
    expect(issuer.issues).toBe(2);
  });

  it('needs no caller token: an unauthenticated poll is answered', async () => {
    const result = await ready(env(minting(), introspecting(ACTIVE), metadata));
    expect(result.status).toBe(200);
  });
});

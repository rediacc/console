/**
 * The proxy Worker: routing, the auth gate, and what it hands the container.
 *
 * Plain vitest in Node rather than @cloudflare/vitest-pool-workers: the Worker's
 * whole surface is a fetch handler and one Container subclass, so a stub
 * Container (which, like the real one, keeps the `env` it was constructed with)
 * and a stubbed global fetch for the account server are enough. The real
 * @cloudflare/containers module imports `cloudflare:workers`, which exists only
 * inside workerd, so it is replaced here.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const routed = vi.hoisted(() => ({ tenants: [] as string[] }));

vi.mock('@cloudflare/containers', () => ({
  Container: class {
    constructor(
      readonly ctx: unknown,
      readonly env: unknown
    ) {}
  },
  getContainer: (_binding: unknown, name: string) => {
    routed.tenants.push(name);
    return { fetch: () => Promise.resolve(Response.json({ from: 'container', tenant: name })) };
  },
}));

import worker, { type Env, ExecutorContainer } from '../index';

const ACCOUNT_URL = 'https://account.test';
const EXECUTOR_TOKEN = 'rdt_executor_secret';
const CALLER = 'rdt_caller';

function env(overrides: Partial<Env> = {}): Env {
  return {
    // Never dereferenced: getContainer is the stub above.
    EXECUTOR: null as never,
    ACCOUNT_URL,
    EXECUTOR_TOKEN,
    ...overrides,
  };
}

/** The account server's introspection answer for CALLER. */
let introspection: Record<string, unknown> | 'http-500';
const accountFetch = vi.fn((url: string | URL, init?: RequestInit) => {
  expect(String(url)).toBe(`${ACCOUNT_URL}/account/api/v1/proxy/introspect`);
  const auth = new Headers(init?.headers).get('authorization');
  const { token } = JSON.parse(String(init?.body)) as { token: string };
  if (auth !== `Bearer ${EXECUTOR_TOKEN}`)
    return Promise.resolve(new Response('no', { status: 401 }));
  if (introspection === 'http-500') return Promise.resolve(new Response('boom', { status: 500 }));
  return Promise.resolve(Response.json(token === CALLER ? introspection : { active: false }));
});

function request(path: string, token?: string): Request {
  return new Request(`https://proxy.test${path}`, {
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });
}

beforeEach(() => {
  routed.tenants = [];
  accountFetch.mockClear();
  introspection = { active: true, scopes: ['proxy:exec'], orgId: 'org-1', teamId: 'team-1' };
  vi.stubGlobal('fetch', accountFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('introspection transport', () => {
  it('goes through the ACCOUNT service binding when bound, never a same-zone public fetch', async () => {
    const publicFetch = vi.fn(() =>
      Promise.resolve(new Response('same-zone origin', { status: 522 }))
    );
    vi.stubGlobal('fetch', publicFetch);
    const bound = vi.fn((url: string | URL, init?: RequestInit) => accountFetch(url, init));
    const res = await worker.fetch(
      request('/v1/server-info', CALLER),
      env({ ACCOUNT: { fetch: bound } as unknown as Fetcher })
    );
    expect(publicFetch).not.toHaveBeenCalled();
    expect(bound).toHaveBeenCalledTimes(1);
    expect(res.status).not.toBe(401);
  });

  it('CONTROL: the same request without the binding uses the public fetch, and a same-zone failure is a 401', async () => {
    const publicFetch = vi.fn(() =>
      Promise.resolve(new Response('same-zone origin', { status: 522 }))
    );
    vi.stubGlobal('fetch', publicFetch);
    const res = await worker.fetch(request('/v1/server-info', CALLER), env());
    expect(publicFetch).toHaveBeenCalledTimes(1);
    expect(res.status).toBe(401);
  });
});

describe('/v1/health', () => {
  it('is answered by the Worker, without introspection or a container', async () => {
    const response = await worker.fetch(request('/v1/health'), env());

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true });
    expect(accountFetch).not.toHaveBeenCalled();
    expect(routed.tenants).toEqual([]);
  });
});

describe('the auth gate', () => {
  const refusals: [string, string | undefined, Record<string, unknown> | 'http-500'][] = [
    ['a missing token', undefined, { active: true, scopes: ['proxy:exec'], orgId: 'org-1' }],
    ['an inactive token', CALLER, { active: false, scopes: ['proxy:exec'], orgId: 'org-1' }],
    [
      'a token without proxy:exec',
      CALLER,
      { active: true, scopes: ['license:read'], orgId: 'org-1' },
    ],
    ['a token with no scopes at all', CALLER, { active: true, orgId: 'org-1' }],
    ['a token with no org', CALLER, { active: true, scopes: ['proxy:exec'] }],
    ['an unknown token', 'rdt_stranger', { active: true, scopes: ['proxy:exec'], orgId: 'org-1' }],
    ['an introspection failure', CALLER, 'http-500'],
  ];

  for (const [name, token, answer] of refusals) {
    it(`refuses ${name} with 401 and starts no container`, async () => {
      introspection = answer;
      const response = await worker.fetch(request('/v1/server-info', token), env());

      expect(response.status).toBe(401);
      expect(routed.tenants).toEqual([]);
    });
  }

  it('answers 401, not 500, when the Worker has no EXECUTOR_TOKEN, and never introspects', async () => {
    const response = await worker.fetch(
      request('/v1/server-info', CALLER),
      env({ EXECUTOR_TOKEN: undefined as unknown as string })
    );

    expect(response.status).toBe(401);
    // Without the guard the Worker would introspect with "Bearer undefined".
    expect(accountFetch).not.toHaveBeenCalled();
    expect(routed.tenants).toEqual([]);
  });
});

describe('tenant routing', () => {
  it('keys the container by org:team', async () => {
    const response = await worker.fetch(request('/v1/command', CALLER), env());

    expect(response.status).toBe(200);
    expect(routed.tenants).toEqual(['org-1:team-1']);
    expect(await response.json()).toEqual({ from: 'container', tenant: 'org-1:team-1' });
  });

  it('collapses an org with no team to org:default', async () => {
    introspection = { active: true, scopes: ['proxy:exec'], orgId: 'org-2', teamId: null };
    await worker.fetch(request('/v1/command', CALLER), env());

    introspection = { active: true, scopes: ['proxy:exec'], orgId: 'org-3' };
    await worker.fetch(request('/v1/command', CALLER), env());

    expect(routed.tenants).toEqual(['org-2:default', 'org-3:default']);
  });

  it('introspects with the Worker token, never the caller token', async () => {
    await worker.fetch(request('/v1/command', CALLER), env());

    const init = accountFetch.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get('authorization')).toBe(`Bearer ${EXECUTOR_TOKEN}`);
    expect(JSON.parse(String(init?.body))).toEqual({ token: CALLER });
  });
});

describe('ExecutorContainer (B1)', () => {
  it('hands the container its account token and account server', () => {
    const container = new ExecutorContainer({} as never, env());

    // `rdc serve` exits at boot without REDIACC_TOKEN (packages/cli/src/commands/serve.ts).
    expect(container.envVars).toEqual({
      REDIACC_TOKEN: EXECUTOR_TOKEN,
      REDIACC_ACCOUNT_SERVER: ACCOUNT_URL,
    });
  });

  it('keeps the sleep timeout at the budgeted two minutes', () => {
    expect(new ExecutorContainer({} as never, env()).sleepAfter).toBe('2m');
  });
});

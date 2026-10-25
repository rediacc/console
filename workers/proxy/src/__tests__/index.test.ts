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
/** The real library's handler registry: an inherited static setter files handlers under the class name, and ContainerProxy reads them back by that name. */
const outboundRegistry = vi.hoisted(() => new Map<string, Record<string, unknown>>());

vi.mock('@cloudflare/containers', () => ({
  ContainerProxy: class {},
  Container: class {
    static get outboundByHost(): Record<string, unknown> | undefined {
      return outboundRegistry.get(this.name);
    }
    static set outboundByHost(handlers: Record<string, unknown>) {
      outboundRegistry.set(this.name, handlers);
    }
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

import worker, { type Env, ExecutorContainer, forwardAccountEgress } from '../index';

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
      REDIACC_REGION: 'eu',
    });
  });

  it('passes the configured region to the container', () => {
    expect(new ExecutorContainer({} as never, env({ REGION: 'us' })).envVars.REDIACC_REGION).toBe(
      'us'
    );
  });

  it('keeps the sleep timeout at the budgeted two minutes', () => {
    expect(new ExecutorContainer({} as never, env()).sleepAfter).toBe('2m');
  });
});

/** The host src/index.ts intercepts; a literal because the Worker module may export only entrypoints. */
const ACCOUNT_EGRESS_HOST = 'account.internal';

describe('container account egress (bench Phase 2, 2026-10-24)', () => {
  function boundEnv(seen: Request[]): Env {
    const binding = {
      fetch: (input: Request) => {
        seen.push(input);
        return Promise.resolve(Response.json({ via: 'binding' }));
      },
    };
    return env({ ACCOUNT: binding as unknown as Fetcher });
  }

  it('points the container at the intercepted host when the Worker holds the ACCOUNT binding', () => {
    const container = new ExecutorContainer({} as never, boundEnv([]));
    expect(container.envVars.REDIACC_ACCOUNT_SERVER).toBe(`http://${ACCOUNT_EGRESS_HOST}`);
  });

  it('files its handler in the library registry, where ContainerProxy looks it up, for exactly that host', () => {
    // An own `outboundByHost` property would shadow the setter and leave the registry empty (the bench 530).
    expect(Object.hasOwn(ExecutorContainer, 'outboundByHost')).toBe(false);
    expect(Object.keys(outboundRegistry.get('ExecutorContainer') ?? {})).toEqual([
      ACCOUNT_EGRESS_HOST,
    ]);
  });

  it('forwards an intercepted account call over the binding, keeping method, path, query, headers and body', async () => {
    const seen: Request[] = [];
    const intercepted = new Request(
      `http://${ACCOUNT_EGRESS_HOST}/account/api/v1/proxy/introspect?x=1`,
      {
        method: 'POST',
        headers: { authorization: `Bearer ${EXECUTOR_TOKEN}`, host: ACCOUNT_EGRESS_HOST },
        body: JSON.stringify({ token: CALLER }),
      }
    );
    // Precondition: the input really carries the Host the forward must drop.
    expect(intercepted.headers.get('host')).toBe(ACCOUNT_EGRESS_HOST);
    const response = await forwardAccountEgress(intercepted, boundEnv(seen));

    expect(await response.json()).toEqual({ via: 'binding' });
    expect(accountFetch).not.toHaveBeenCalled();
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe(`${ACCOUNT_URL}/account/api/v1/proxy/introspect?x=1`);
    expect(seen[0]?.method).toBe('POST');
    expect(seen[0]?.headers.get('authorization')).toBe(`Bearer ${EXECUTOR_TOKEN}`);
    // The container's Host names account.internal; carried onward it breaks a public fetch at DNS.
    expect(seen[0]?.headers.get('host')).toBeNull();
    expect(await seen[0]?.json()).toEqual({ token: CALLER });
  });

  it('without the binding, forwards over a public fetch to ACCOUNT_URL (wrangler dev)', async () => {
    const forwarded = vi.fn((_input: Request) => Promise.resolve(Response.json({ via: 'fetch' })));
    vi.stubGlobal('fetch', forwarded);

    const response = await forwardAccountEgress(
      new Request(`http://${ACCOUNT_EGRESS_HOST}/account/api/v1/configs/executor-token`),
      env()
    );

    expect(await response.json()).toEqual({ via: 'fetch' });
    expect(forwarded.mock.calls[0]?.[0].url).toBe(
      `${ACCOUNT_URL}/account/api/v1/configs/executor-token`
    );
  });

  it('refuses a path outside the account API and forwards nothing', async () => {
    const seen: Request[] = [];
    const response = await forwardAccountEgress(
      new Request(`http://${ACCOUNT_EGRESS_HOST}/admin/secrets`),
      boundEnv(seen)
    );

    expect(response.status).toBe(403);
    expect(seen).toEqual([]);
  });
});

describe('span attributes (telemetry export T14)', () => {
  const PROBE = '0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d';

  function traced(): { ctx: ExecutionContext; attrs: Record<string, unknown> } {
    const attrs: Record<string, unknown> = {};
    const ctx = {
      tracing: {
        getActiveSpan: () => ({
          setAttribute: (key: string, value: unknown) => {
            attrs[key] = value;
          },
        }),
      },
    } as unknown as ExecutionContext;
    return { ctx, attrs };
  }

  function probed(path: string, token?: string, probe: string = PROBE): Request {
    const headers: Record<string, string> = { 'x-rediacc-probe': probe };
    if (token) headers.authorization = `Bearer ${token}`;
    return new Request(`https://proxy.test${path}`, { headers });
  }

  it('health: region, environment, probe and outcome health', async () => {
    const { ctx, attrs } = traced();
    await worker.fetch(probed('/v1/health'), env(), ctx);

    expect(attrs).toEqual({
      'rediacc.region': 'eu',
      'deployment.environment': 'production',
      'rediacc.probe': PROBE,
      'rediacc.proxy.outcome': 'health',
    });
  });

  it('forwarded: outcome forwarded, with the configured region and environment', async () => {
    const { ctx, attrs } = traced();
    await worker.fetch(
      probed('/v1/server-info', CALLER),
      env({ REGION: 'us', ENVIRONMENT: 'edge' }),
      ctx
    );

    expect(attrs['rediacc.proxy.outcome']).toBe('forwarded');
    expect(attrs['rediacc.region']).toBe('us');
    expect(attrs['deployment.environment']).toBe('edge');
  });

  const reasons: [string, string | undefined, Record<string, unknown> | 'http-500', string][] = [
    ['no token', undefined, { active: true }, 'no-bearer'],
    ['inactive', CALLER, { active: false }, 'inactive'],
    ['no org', CALLER, { active: true, scopes: ['proxy:exec'] }, 'no-org'],
    ['no scope', CALLER, { active: true, orgId: 'org-1', scopes: [] }, 'no-proxy-exec-scope'],
    ['introspection failure', CALLER, 'http-500', 'introspect-http-500'],
  ];
  for (const [name, token, answer, reason] of reasons) {
    it(`refused (${name}): outcome refused:${reason}`, async () => {
      introspection = answer;
      const { ctx, attrs } = traced();
      const response = await worker.fetch(probed('/v1/server-info', token), env(), ctx);

      expect(response.status).toBe(401);
      expect(attrs['rediacc.proxy.outcome']).toBe(`refused:${reason}`);
    });
  }

  it('records no probe for a header that is not a UUID', async () => {
    const { ctx, attrs } = traced();
    await worker.fetch(probed('/v1/health', undefined, 'rdt_caller'), env(), ctx);

    expect(attrs).not.toHaveProperty('rediacc.probe');
  });

  it('no token, org, team or tenant value lands in any attribute or log line, on any outcome', async () => {
    const secrets = [CALLER, EXECUTOR_TOKEN, 'org-1', 'team-1', 'org-1:team-1'];
    const all: Record<string, unknown>[] = [];
    const logged: string[] = [];
    // Logs leave the platform too (wrangler.toml and wrangler.bench.toml name a logs destination),
    // so every console line written during the walk is checked with the attributes.
    for (const level of ['log', 'info', 'warn', 'error', 'debug'] as const) {
      vi.spyOn(console, level).mockImplementation((...args: unknown[]) => {
        logged.push(args.map(String).join(' '));
      });
    }
    for (const [path, token] of [
      ['/v1/health', undefined],
      ['/v1/server-info', CALLER],
      ['/v1/server-info', 'rdt_stranger'],
      ['/v1/server-info', undefined],
    ] as const) {
      const { ctx, attrs } = traced();
      await worker.fetch(probed(path, token), env(), ctx);
      all.push(attrs);
    }
    // The walk must cover every outcome, or "on any outcome" is not what this proves.
    const outcomes = all.map((attrs) => String(attrs['rediacc.proxy.outcome']));
    expect(outcomes).toContain('health');
    expect(outcomes).toContain('forwarded');
    expect(outcomes.some((outcome) => outcome.startsWith('refused:'))).toBe(true);
    // The refusals log their reason, so the log half of the check has lines to read.
    expect(logged.some((line) => line.includes('caller refused'))).toBe(true);
    const serialized = JSON.stringify([all, logged]);
    for (const secret of secrets) expect(serialized).not.toContain(secret);
  });

  it('runs untraced when the host supplies no tracing API', async () => {
    const response = await worker.fetch(request('/v1/health'), env(), {} as ExecutionContext);
    expect(response.status).toBe(200);
  });
});

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
    static get outboundHandlers(): Record<string, unknown> | undefined {
      return outboundRegistry.get(`handlers:${this.name}`);
    }
    static set outboundHandlers(handlers: Record<string, unknown>) {
      outboundRegistry.set(`handlers:${this.name}`, handlers);
    }
    constructor(
      readonly ctx: unknown,
      readonly env: unknown
    ) {}
  },
  getContainer: (_binding: unknown, name: string) => {
    routed.tenants.push(name);
    return {
      pin: () => Promise.resolve(),
      fetch: () => Promise.resolve(Response.json({ from: 'container', tenant: name })),
    };
  },
}));

import { forwardAccountEgress as forward } from '../egress';
import worker, { type Env, ExecutorContainer } from '../index';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';
import { executorEnv as executorEnvVars } from '../org-executor';
import { resetReadyCache } from '../ready';

const ACCOUNT_URL = 'https://account.test';
/** What the fake ISSUER mints; the Worker introspects with it. */
const ISSUED = 'rdt_issued_secret';
/** The literal the container holds (src/egress.ts EXECUTOR_TOKEN_PLACEHOLDER). */
const PLACEHOLDER = 'rediacc-executor-placeholder';
const CALLER = 'rdt_caller';
/** The org every forwarded egress call below is made for. */
const ORG = 'org-1';
const forwardAccountEgress = (request: Request, e: Env): Promise<Response> =>
  forward(request, e, ORG);

/** An ISSUER binding that mints ISSUED for 45 minutes, or throws when `refuse` is set. */
function fakeIssuer(refuse = false): Service<ExecutorIssuerRpc> {
  return {
    route: (token: string) => {
      if (refuse) return Promise.reject(new Error('owner lost admin'));
      if (introspection === 'http-500') return Promise.reject(new Error('boom'));
      const answer = token === CALLER ? introspection : { active: false };
      const scopes = (answer.scopes as string[] | undefined) ?? [];
      return Promise.resolve(
        answer.active && answer.orgId && scopes.includes('proxy:exec')
          ? { orgId: answer.orgId as string, placement: 0 }
          : { refused: 'route-refused' }
      );
    },
    issue: () =>
      refuse
        ? Promise.reject(new Error('owner lost admin'))
        : Promise.resolve({
            token: ISSUED,
            expiresAt: new Date(Date.now() + 45 * 60_000).toISOString(),
          }),
    fetch: () => Promise.reject(new Error('the issuer has no fetch')),
  } as unknown as Service<ExecutorIssuerRpc>;
}

function env(overrides: Partial<Env> = {}): Env {
  return {
    // Never dereferenced: getContainer is the stub above.
    EXECUTOR: null as never,
    ACCOUNT_URL,
    ISSUER: fakeIssuer(),
    ...overrides,
  };
}

/** The account server's introspection answer for CALLER. */
let introspection: Record<string, unknown> | 'http-500';
const accountFetch = vi.fn((url: string | URL, init?: RequestInit) => {
  expect(String(url)).toBe(`${ACCOUNT_URL}/account/api/v1/proxy/introspect`);
  const auth = new Headers(init?.headers).get('authorization');
  const { token } = JSON.parse(String(init?.body)) as { token: string };
  if (auth !== `Bearer ${ISSUED}`) return Promise.resolve(new Response('no', { status: 401 }));
  if (introspection === 'http-500') return Promise.resolve(new Response('boom', { status: 500 }));
  return Promise.resolve(Response.json(token === CALLER ? introspection : { active: false }));
});

function request(path: string, token?: string): Request {
  return new Request(`https://proxy.test${path}`, {
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });
}

beforeEach(() => {
  resetIssuedTokenCache();
  resetReadyCache();
  routed.tenants = [];
  accountFetch.mockClear();
  introspection = {
    active: true,
    scopes: ['proxy:exec'],
    orgId: 'org-1',
    teamId: 'team-1',
  };
  vi.stubGlobal('fetch', accountFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
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
  const refusals: [string, string | undefined, Record<string, unknown>][] = [
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
  ];

  for (const [name, token, answer] of refusals) {
    it(`refuses ${name} with 401 and starts no container`, async () => {
      introspection = answer;
      const response = await worker.fetch(request('/v1/server-info', token), env());

      expect(response.status).toBe(401);
      expect(routed.tenants).toEqual([]);
    });
  }

  for (const [name, issuer, answer] of [
    ['the issuer refuses', fakeIssuer(true), undefined],
    ['there is no ISSUER binding', undefined, undefined],
    ['the issuer route call throws', fakeIssuer(), 'http-500' as const],
  ] as const) {
    it(`answers 503, not 401 or 500, when ${name}, and never introspects`, async () => {
      if (answer) introspection = answer;
      const response = await worker.fetch(
        request('/v1/server-info', CALLER),
        env({ ISSUER: issuer })
      );

      expect(response.status).toBe(503);
      // Without the guard the Worker would introspect with "Bearer undefined".
      expect(accountFetch).not.toHaveBeenCalled();
      expect(routed.tenants).toEqual([]);
    });
  }
});

describe('ExecutorContainer (B1)', () => {
  it('hands the container the placeholder token, the intercepted account host and its pinned org, never a real token', async () => {
    // A warm cache is the worst case: the issued token exists in the isolate when the container is built.
    await worker.fetch(request('/v1/command', CALLER), env());
    const vars = executorEnvVars(env(), ORG);

    // `rdc serve` exits at boot without REDIACC_TOKEN (packages/cli/src/commands/serve.ts).
    expect(vars).toEqual({
      REDIACC_TOKEN: PLACEHOLDER,
      REDIACC_ACCOUNT_SERVER: `http://${ACCOUNT_EGRESS_HOST}`,
      REDIACC_REGION: 'eu',
      REDIACC_EXECUTOR_ORG_ID: ORG,
    });
    expect(JSON.stringify(vars)).not.toContain(ISSUED);
  });

  it('passes the configured region to the container', () => {
    expect(executorEnvVars(env({ REGION: 'us' }), ORG).REDIACC_REGION).toBe('us');
  });

  it('keeps the sleep timeout at the budgeted two minutes', () => {
    expect(new ExecutorContainer({} as never, env()).sleepAfter).toBe('2m');
  });
});

describe('the main module exports (wrangler deploy, workerd start)', () => {
  it('exports every bound Durable Object class and the AccountEgress entrypoint, and nothing that is not a class', async () => {
    const main = await import('../index');
    // wrangler refuses a deploy whose bound Durable Objects are not exported (its error says the Worker depends on Durable Objects that the entrypoint file does not export), and OrgExecutor reaches the egress through ctx.exports.AccountEgress.
    for (const name of [
      'ExecutorContainer',
      'OrgExecutor',
      'ExecutorCapacity',
      'AccountEgress',
      'ContainerProxy',
    ]) {
      expect(typeof (main as Record<string, unknown>)[name], name).toBe('function');
    }
    // workerd treats every export of the main module as an entrypoint and refuses to start on a plain value.
    for (const [name, value] of Object.entries(main)) {
      if (name === 'default') continue;
      expect(typeof value, name).toBe('function');
      expect(String(value).startsWith('class'), name).toBe(true);
    }
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

  it('points the container at the intercepted host with or without the ACCOUNT binding', () => {
    for (const e of [boundEnv([]), env()]) {
      expect(executorEnvVars(e, ORG).REDIACC_ACCOUNT_SERVER).toBe(`http://${ACCOUNT_EGRESS_HOST}`);
    }
  });

  it('files the accountEgress named handler in the library registry, and no static per-host handler', () => {
    // An own `outboundHandlers` property would shadow the setter and leave the registry empty (the bench 530).
    expect(Object.hasOwn(ExecutorContainer, 'outboundHandlers')).toBe(false);
    expect(Object.keys(outboundRegistry.get('handlers:ExecutorContainer') ?? {})).toEqual([
      'accountEgress',
    ]);
    expect(outboundRegistry.has('ExecutorContainer')).toBe(false);
  });

  it('forwards an intercepted account call over the binding, keeping method, path, headers and body, with the issued token', async () => {
    const seen: Request[] = [];
    const intercepted = new Request(
      `http://${ACCOUNT_EGRESS_HOST}/account/api/v1/proxy/introspect`,
      {
        method: 'POST',
        headers: {
          authorization: `Bearer ${PLACEHOLDER}`,
          host: ACCOUNT_EGRESS_HOST,
          'x-trace': 'kept',
        },
        body: JSON.stringify({ token: CALLER }),
      }
    );
    // Precondition: the input really carries the Host the forward must drop.
    expect(intercepted.headers.get('host')).toBe(ACCOUNT_EGRESS_HOST);
    const response = await forwardAccountEgress(intercepted, boundEnv(seen));

    expect(await response.json()).toEqual({ via: 'binding' });
    expect(accountFetch).not.toHaveBeenCalled();
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe(`${ACCOUNT_URL}/account/api/v1/proxy/introspect`);
    expect(seen[0]?.method).toBe('POST');
    expect(seen[0]?.headers.get('authorization')).toBe(`Bearer ${ISSUED}`);
    expect(seen[0]?.headers.get('x-trace')).toBe('kept');
    // The container's Host names account.internal; carried onward it breaks a public fetch at DNS.
    expect(seen[0]?.headers.get('host')).toBeNull();
    expect(await seen[0]?.json()).toEqual({ token: CALLER });
  });

  it('without the binding, forwards over a public fetch to ACCOUNT_URL (wrangler dev)', async () => {
    const forwarded = vi.fn((_input: Request) => Promise.resolve(Response.json({ via: 'fetch' })));
    vi.stubGlobal('fetch', forwarded);

    const response = await forwardAccountEgress(
      new Request(`http://${ACCOUNT_EGRESS_HOST}/account/api/v1/configs/executor-token`, {
        method: 'POST',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
        body: '{}',
      }),
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

  const reasons: [string, string | undefined, Record<string, unknown>, string][] = [
    ['no token', undefined, { active: true }, 'no-bearer'],
    ['inactive', CALLER, { active: false }, 'route-refused'],
    ['no org', CALLER, { active: true, scopes: ['proxy:exec'] }, 'route-refused'],
    ['no scope', CALLER, { active: true, orgId: 'org-1', scopes: [] }, 'route-refused'],
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

  it('issuer route failure: 503 with outcome refused:issuer-route-failed', async () => {
    introspection = 'http-500';
    const { ctx, attrs } = traced();
    const response = await worker.fetch(probed('/v1/server-info', CALLER), env(), ctx);

    expect(response.status).toBe(503);
    expect(attrs['rediacc.proxy.outcome']).toBe('refused:issuer-route-failed');
  });

  it('logs a telemetry-probe line for a probed request, and none for a non-UUID header', async () => {
    const log = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { ctx } = traced();
    await worker.fetch(probed('/v1/health'), env(), ctx);
    expect(log).toHaveBeenCalledWith(`telemetry-probe ${PROBE}`);

    log.mockClear();
    await worker.fetch(probed('/v1/health', undefined, 'rdt_caller'), env(), traced().ctx);
    expect(log).not.toHaveBeenCalledWith(expect.stringContaining('telemetry-probe'));
    log.mockRestore();
  });

  it('records no probe for a header that is not a UUID', async () => {
    const { ctx, attrs } = traced();
    await worker.fetch(probed('/v1/health', undefined, 'rdt_caller'), env(), ctx);

    expect(attrs).not.toHaveProperty('rediacc.probe');
  });

  /** What a log line would carry for one console argument: an Error (also one nested in an object) keeps its message, an object its fields, and nothing throws. */
  function asLogText(arg: unknown): string {
    if (typeof arg === 'string') return arg;
    if (arg instanceof Error) return `${arg.name}: ${arg.message}`;
    try {
      const json: string | undefined = JSON.stringify(arg, (_key, value: unknown) =>
        value instanceof Error ? `${value.name}: ${value.message}` : value
      );
      return json ?? String(arg);
    } catch {
      // A circular object, or one with no Object.prototype, has no usable text; the walk still sees that a line was written.
      try {
        return String(arg);
      } catch {
        return '[unprintable]';
      }
    }
  }

  it('no token, org, team or tenant value lands in any attribute or log line, on any outcome', async () => {
    const secrets = [CALLER, ISSUED, 'org-1', 'team-1', 'org-1:team-1'];
    const all: Record<string, unknown>[] = [];
    const logged: string[] = [];
    // Logs leave the platform too (wrangler.toml and wrangler.bench.toml name a logs destination),
    // so every console line written during the walk is checked with the attributes.
    for (const level of ['log', 'info', 'warn', 'error', 'debug'] as const) {
      vi.spyOn(console, level).mockImplementation((...args: unknown[]) => {
        logged.push(args.map(asLogText).join(' '));
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

  it('an empty REGION or ENVIRONMENT var falls back to the defaults, on the span and for the executor', async () => {
    const { ctx, attrs } = traced();
    await worker.fetch(probed('/v1/health'), env({ REGION: '', ENVIRONMENT: '' }), ctx);
    expect(attrs['rediacc.region']).toBe('eu');
    expect(attrs['deployment.environment']).toBe('production');
    expect(executorEnvVars(env({ REGION: '' }), ORG).REDIACC_REGION).toBe('eu');
  });

  it('logs the probe uuid in the same lowercase form as the rediacc.probe attribute', async () => {
    const lines: string[] = [];
    vi.spyOn(console, 'warn').mockImplementation((...args: unknown[]) => {
      lines.push(args.map(String).join(' '));
    });
    const { ctx, attrs } = traced();
    await worker.fetch(probed('/v1/health', undefined, PROBE.toUpperCase()), env(), ctx);
    expect(attrs['rediacc.probe']).toBe(PROBE.toLowerCase());
    expect(lines).toContain(`telemetry-probe ${PROBE.toLowerCase()}`);
  });

  it('runs untraced when the host supplies no tracing API', async () => {
    const response = await worker.fetch(request('/v1/health'), env(), {} as ExecutionContext);
    expect(response.status).toBe(200);
  });
});

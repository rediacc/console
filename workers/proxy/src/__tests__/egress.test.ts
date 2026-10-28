/**
 * The `accountEgress` named handler and the `AccountEgress` entrypoint (box W3, Design A): the instance and org checks that run before the allowlist and before the issuer (agent/plans/PLAN-console-executor-multi-org.md box W1, MU1), and the entrypoint's placement check and egress-unreachable report route (agent/plans/PLAN-org-executor-connect-timeout-relocate.md box E7).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('cloudflare:workers', () => ({
  WorkerEntrypoint: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
}));

import { AccountEgress, accountEgress, EXECUTOR_TOKEN_PLACEHOLDER } from '../egress';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';
import type { EgressReportAnswer } from '../org-executor';

const API = 'http://account.internal/account/api/v1';

/** `idFromName(name).toString()` is `id:<name>`, which is what the library reports as `containerId` for that instance (`this.ctx.id.toString()`, dist/lib/container.js). */
const EXECUTOR = {
  idFromName: (name: string) => ({ toString: () => `id:${name}` }),
};

function setup() {
  const seen: Request[] = [];
  const state = { issues: [] as string[], fetches: 0, relocates: 0 };
  const issuer = {
    relocate: () => {
      state.relocates += 1;
      return Promise.reject(new Error('the egress never relocates'));
    },
    issue: (orgId: string) => {
      state.issues.push(orgId);
      return Promise.resolve({
        token: `rdt_for_${orgId}`,
        expiresAt: new Date(Date.now() + 45 * 60_000).toISOString(),
      });
    },
    fetch: () => {
      state.fetches += 1;
      return Promise.reject(new Error('never'));
    },
  } as unknown as Service<ExecutorIssuerRpc>;
  const account = {
    fetch: (r: Request) => {
      seen.push(r);
      return Promise.resolve(Response.json({}));
    },
  } as unknown as Fetcher;
  const env = {
    EXECUTOR,
    ACCOUNT_URL: 'https://account.test',
    ACCOUNT: account,
    ISSUER: issuer,
  };
  return { env, seen, state };
}

function introspect(): Request {
  return new Request(`${API}/proxy/introspect`, {
    method: 'POST',
    headers: { authorization: `Bearer ${EXECUTOR_TOKEN_PLACEHOLDER}` },
    body: '{}',
  });
}

beforeEach(() => {
  resetIssuedTokenCache();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

describe('accountEgress identity checks', () => {
  const cases: [string, unknown, string][] = [
    ['no ctx at all', undefined, 'org-param-missing'],
    ['no params', { containerId: 'id:org-a', className: 'ExecutorContainer' }, 'org-param-missing'],
    [
      'an empty org param',
      { containerId: 'id:', className: 'x', params: { orgId: '' } },
      'org-param-missing',
    ],
    [
      'a non-string org param',
      { containerId: 'id:7', className: 'x', params: { orgId: 7 } },
      'org-param-missing',
    ],
    [
      'params naming another org than the container id',
      { containerId: 'id:org-b', className: 'x', params: { orgId: 'org-a' } },
      'container-org-mismatch',
    ],
    [
      'a missing container id',
      { className: 'x', params: { orgId: 'org-a' } },
      'container-org-mismatch',
    ],
  ];

  for (const [name, ctx, reason] of cases) {
    it(`refuses ${name} with 403 ${reason}, before the issuer is called and with nothing forwarded`, async () => {
      const { env, seen, state } = setup();
      const response = await accountEgress(introspect(), env, ctx as never);

      expect(response.status).toBe(403);
      expect(await response.json()).toMatchObject({ reason });
      expect(state.issues).toEqual([]);
      expect(state.fetches).toBe(0);
      expect(seen).toEqual([]);
    });
  }

  it('forwards for the matching instance with that org issued token, and mints only for that org', async () => {
    const { env, seen, state } = setup();
    const response = await accountEgress(introspect(), env, {
      containerId: 'id:org-a',
      className: 'ExecutorContainer',
      params: { orgId: 'org-a' },
    });

    expect(response.status).toBe(200);
    expect(state.issues).toEqual(['org-a']);
    expect(seen[0]?.headers.get('authorization')).toBe('Bearer rdt_for_org-a');
  });

  it('two instances get two different org tokens, never each other', async () => {
    const { env, seen } = setup();
    for (const org of ['org-a', 'org-b']) {
      await accountEgress(introspect(), env, {
        containerId: `id:${org}`,
        className: 'ExecutorContainer',
        params: { orgId: org },
      });
    }

    expect(seen.map((r) => r.headers.get('authorization'))).toEqual([
      'Bearer rdt_for_org-a',
      'Bearer rdt_for_org-b',
    ]);
  });

  it('has no report route: the egress-unreachable report is refused 403 route-not-allowed, with nothing forwarded', async () => {
    const { env, seen, state } = setup();
    const response = await accountEgress(
      new Request('http://account.internal/executor/v1/egress-unreachable', { method: 'POST' }),
      env,
      { containerId: 'id:org-a', className: 'ExecutorContainer', params: { orgId: 'org-a' } }
    );

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ reason: 'route-not-allowed' });
    expect(state.issues).toEqual([]);
    expect(seen).toEqual([]);
  });

  it('still applies the allowlist after the identity checks pass', async () => {
    const { env, seen, state } = setup();
    const response = await accountEgress(new Request(`${API}/admin/users`), env, {
      containerId: 'id:org-a',
      className: 'x',
      params: { orgId: 'org-a' },
    });

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({
      reason: 'route-not-allowed',
    });
    expect(state.issues).toEqual([]);
    expect(seen).toEqual([]);
  });
});

/** Props for org-a's executor at placement 0, as OrgExecutor binds them. */
const OWN = { orgId: 'org-a', placement: 0, containerId: 'id:org-a:p0' };

describe('AccountEgress entrypoint (props and containerId checks)', () => {
  /** The entrypoint over ORG_EXECUTOR, whose stubs answer `recordEgressUnreachable` with `report` (or throw when it is an Error). */
  function entry(
    props: unknown,
    report: EgressReportAnswer | Error = { ok: true, count: 1, threshold: 3, relocated: false }
  ) {
    const { env, seen, state } = setup();
    const reports: { id: string; orgId: string; placement: number }[] = [];
    const attrs: Record<string, unknown> = {};
    const { EXECUTOR: _legacy, ...rest } = env;
    const durable = {
      ...rest,
      ORG_EXECUTOR: {
        ...EXECUTOR,
        get: (id: { toString(): string }) => ({
          recordEgressUnreachable: (orgId: string, placement: number) => {
            reports.push({ id: id.toString(), orgId, placement });
            return report instanceof Error ? Promise.reject(report) : Promise.resolve(report);
          },
        }),
      },
    };
    const ctx = {
      props,
      tracing: {
        getActiveSpan: () => ({ setAttribute: (k: string, v: unknown) => (attrs[k] = v) }),
      },
    };
    const Ctor = AccountEgress as unknown as new (
      ctx: unknown,
      env: unknown
    ) => { fetch(r: Request): Promise<Response> };
    return { egress: new Ctor(ctx, durable), seen, state, reports, attrs };
  }
  const refused: [string, unknown, string][] = [
    ['no props', undefined, 'org-param-missing'],
    ['empty props', {}, 'org-param-missing'],
    ['an empty orgId', { orgId: '', placement: 0, containerId: 'id::p0' }, 'org-param-missing'],
    ['a non-string orgId', { orgId: 7, placement: 0, containerId: 'id:7:p0' }, 'org-param-missing'],
    ['a missing containerId', { orgId: 'org-a', placement: 0 }, 'org-param-missing'],
    ['a missing placement', { orgId: 'org-a', containerId: 'id:org-a:p0' }, 'org-param-missing'],
    [
      'a placement that is not a non-negative integer',
      { orgId: 'org-a', placement: -1, containerId: 'id:org-a:p-1' },
      'org-param-missing',
    ],
    [
      "props naming another org's containerId",
      { orgId: 'org-a', placement: 0, containerId: 'id:org-b:p0' },
      'container-org-mismatch',
    ],
    [
      'props whose placement does not match containerId',
      { orgId: 'org-a', placement: 1, containerId: 'id:org-a:p0' },
      'container-org-mismatch',
    ],
    [
      'a containerId named by the org alone',
      { orgId: 'org-a', placement: 0, containerId: 'id:org-a' },
      'container-org-mismatch',
    ],
    [
      'a containerId that is not an id',
      { orgId: 'org-a', placement: 0, containerId: '' },
      'container-org-mismatch',
    ],
  ];
  for (const [name, props, reason] of refused) {
    it(`refuses ${name} with 403 before any issuer call`, async () => {
      const { egress, seen, state, reports } = entry(props);
      for (const request of [introspect(), unreachable()]) {
        const response = await egress.fetch(request);

        expect(response.status).toBe(403);
        expect(await response.json()).toMatchObject({ reason });
      }
      expect(state.issues).toEqual([]);
      expect(state.fetches).toBe(0);
      expect(reports).toEqual([]);
      expect(seen).toEqual([]);
    });
  }

  it('forwards for matching props with that org issued token only', async () => {
    const { egress, seen, state } = entry(OWN);
    const response = await egress.fetch(introspect());

    expect(response.status).toBe(200);
    expect(state.issues).toEqual(['org-a']);
    expect(seen[0]?.headers.get('authorization')).toBe('Bearer rdt_for_org-a');
  });

  it('applies the allowlist after the checks pass', async () => {
    const { egress, seen, state } = entry(OWN);
    const response = await egress.fetch(new Request(`${API}/admin/users`));

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ reason: 'route-not-allowed' });
    expect(state.issues).toEqual([]);
    expect(seen).toEqual([]);
  });

  it('refuses the E2E tunnel 403 route-not-allowed, before the issuer and with nothing forwarded', async () => {
    // The CLI's core audit flush sends `POST tunnel` with the placeholder sealed inside the envelope (bench tail, 2026-10-28): the swap cannot reach it, and the tunnel re-dispatches to any route, so admitting it would void the allowlist.
    const { egress, seen, state } = entry(OWN);
    const response = await egress.fetch(
      new Request(`${API}/tunnel`, {
        method: 'POST',
        headers: { 'content-type': 'application/x-rediacc-encrypted' },
        body: JSON.stringify({ v: 1, eph: 'x', ct: 'y' }),
      })
    );

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ reason: 'route-not-allowed' });
    expect(state.issues).toEqual([]);
    expect(seen).toEqual([]);
  });

  it('refuses a bearer call that is not the placeholder, before the issuer', async () => {
    const { egress, seen, state } = entry(OWN);
    const response = await egress.fetch(
      new Request(`${API}/proxy/introspect`, {
        method: 'POST',
        headers: { authorization: 'Bearer real-token' },
        body: '{}',
      })
    );

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ reason: 'bearer-not-placeholder' });
    expect(state.issues).toEqual([]);
    expect(seen).toEqual([]);
  });
});

function unreachable(path = '/executor/v1/egress-unreachable', method = 'POST'): Request {
  return new Request(`http://account.internal${path}`, { method });
}

describe('AccountEgress egress-unreachable report route', () => {
  function entry(report: EgressReportAnswer | Error) {
    const { env, seen, state } = setup();
    const reports: { id: string; orgId: string; placement: number }[] = [];
    const attrs: Record<string, unknown> = {};
    const accountCalls = { count: 0 };
    const durable = {
      ACCOUNT_URL: env.ACCOUNT_URL,
      ACCOUNT: {
        fetch: (r: Request) => {
          accountCalls.count += 1;
          return env.ACCOUNT.fetch(r);
        },
      },
      ISSUER: env.ISSUER,
      ORG_EXECUTOR: {
        ...EXECUTOR,
        get: (id: { toString(): string }) => ({
          recordEgressUnreachable: (orgId: string, placement: number) => {
            reports.push({ id: id.toString(), orgId, placement });
            return report instanceof Error ? Promise.reject(report) : Promise.resolve(report);
          },
        }),
      },
    };
    const ctx = {
      props: OWN,
      tracing: {
        getActiveSpan: () => ({ setAttribute: (k: string, v: unknown) => (attrs[k] = v) }),
      },
    };
    const Ctor = AccountEgress as unknown as new (
      ctx: unknown,
      env: unknown
    ) => { fetch(r: Request): Promise<Response> };
    return { egress: new Ctor(ctx, durable), seen, state, reports, attrs, accountCalls };
  }

  it('calls recordEgressUnreachable once on its own instance, makes zero ACCOUNT and zero ISSUER calls, and answers without ok', async () => {
    const t = entry({ ok: true, count: 2, threshold: 3, relocated: false });
    const response = await t.egress.fetch(unreachable());

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ count: 2, threshold: 3, relocated: false });
    expect(t.reports).toEqual([{ id: 'id:org-a:p0', orgId: 'org-a', placement: 0 }]);
    expect(t.accountCalls.count).toBe(0);
    expect(t.seen).toEqual([]);
    expect(t.state.issues).toEqual([]);
    expect(t.state.relocates).toBe(0);
    expect(t.state.fetches).toBe(0);
    expect(t.attrs['rediacc.proxy.outcome']).toBe('egress-unreachable');
  });

  it('records relocated on the span when the report moved the org', async () => {
    const t = entry({ ok: true, count: 3, threshold: 3, relocated: true });
    const response = await t.egress.fetch(unreachable());

    expect(await response.json()).toEqual({ count: 3, threshold: 3, relocated: true });
    expect(t.attrs['rediacc.proxy.outcome']).toBe('relocated');
    expect(t.accountCalls.count).toBe(0);
    expect(t.state.issues).toEqual([]);
    expect(t.state.relocates).toBe(0);
  });

  it('a report the instance refuses is a 403 with its reason; an instance that cannot be reached is a 503', async () => {
    const refusedReport = entry({ ok: false, reason: 'report-org-conflict' });
    const refused = await refusedReport.egress.fetch(unreachable());
    expect(refused.status).toBe(403);
    expect(await refused.json()).toMatchObject({ reason: 'report-org-conflict' });

    const unreachableObject = entry(new Error('do unreachable'));
    const failed = await unreachableObject.egress.fetch(unreachable());
    expect(failed.status).toBe(503);
    expect(await failed.json()).toMatchObject({ reason: 'report-failed' });

    for (const t of [refusedReport, unreachableObject]) {
      expect(t.accountCalls.count).toBe(0);
      expect(t.state.issues).toEqual([]);
      expect(t.state.relocates).toBe(0);
    }
  });

  it('only a POST with no query is the report: a GET or a query falls to the allowlist and is refused', async () => {
    for (const request of [
      unreachable('/executor/v1/egress-unreachable', 'GET'),
      unreachable('/executor/v1/egress-unreachable?org=org-b'),
    ]) {
      const t = entry({ ok: true, count: 1, threshold: 3, relocated: false });
      const response = await t.egress.fetch(request);

      expect(response.status).toBe(403);
      expect(await response.json()).toMatchObject({ reason: 'route-not-allowed' });
      expect(t.reports).toEqual([]);
      expect(t.accountCalls.count).toBe(0);
    }
  });
});

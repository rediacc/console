/**
 * The `AccountEgress` entrypoint (box W3, Design A): the instance and org checks that run before the allowlist and before the issuer (agent/plans/PLAN-console-executor-multi-org.md box W1, MU1), and the entrypoint's placement check and egress-unreachable report route (agent/plans/PLAN-org-executor-connect-timeout-relocate.md box E7).
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

import { AccountEgress, EXECUTOR_TOKEN_PLACEHOLDER } from '../egress';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';
import type { EgressReportAnswer } from '../org-executor';

const API = 'http://account.internal/account/api/v1';

/** `idFromName(name).toString()` is `id:<name>`, which is what OrgExecutor passes as `containerId` for that instance (`this.ctx.id.toString()`). */
const NAMES = {
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

/** Props for org-a's executor at placement 0, as OrgExecutor binds them. */
const OWN = { orgId: 'org-a', placement: 0, containerId: 'id:org-a:p0' };

describe('AccountEgress entrypoint (props and containerId checks)', () => {
  /** The entrypoint over ORG_EXECUTOR, whose stubs answer `recordEgressUnreachable` with `report` (or throw when it is an Error). */
  function entry(
    props: unknown,
    report: EgressReportAnswer | Error = {
      ok: true,
      count: 1,
      threshold: 3,
      relocated: false,
      counted: true,
      probe: 'reachable',
    }
  ) {
    const { env, seen, state } = setup();
    const reports: { id: string; orgId: string; placement: number }[] = [];
    const attrs: Record<string, unknown> = {};
    const durable = {
      ...env,
      ORG_EXECUTOR: {
        ...NAMES,
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

const TARGET = { host: '203.0.113.7', port: 22 };

function unreachable(
  path = '/executor/v1/egress-unreachable',
  method = 'POST',
  body: string | undefined = JSON.stringify(TARGET)
): Request {
  return new Request(`http://account.internal${path}`, {
    method,
    ...(method === 'POST' && body !== undefined
      ? { body, headers: { 'content-type': 'application/json' } }
      : {}),
  });
}

/** An answered report, counted on a reachable probe unless overridden. */
function answered(
  over: Partial<Extract<EgressReportAnswer, { ok: true }>> = {}
): EgressReportAnswer {
  return {
    ok: true,
    count: 1,
    threshold: 3,
    relocated: false,
    counted: true,
    probe: 'reachable',
    ...over,
  };
}

describe('AccountEgress egress-unreachable report route', () => {
  function entry(report: EgressReportAnswer | Error) {
    const { env, seen, state } = setup();
    const reports: { id: string; orgId: string; placement: number; target?: unknown }[] = [];
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
        ...NAMES,
        get: (id: { toString(): string }) => ({
          recordEgressUnreachable: (orgId: string, placement: number, target?: unknown) => {
            reports.push({ id: id.toString(), orgId, placement, target });
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
    const t = entry(answered({ count: 2 }));
    const response = await t.egress.fetch(unreachable());

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      count: 2,
      threshold: 3,
      relocated: false,
      counted: true,
      probe: 'reachable',
    });
    expect(t.reports).toEqual([
      { id: 'id:org-a:p0', orgId: 'org-a', placement: 0, target: TARGET },
    ]);
    expect(t.accountCalls.count).toBe(0);
    expect(t.seen).toEqual([]);
    expect(t.state.issues).toEqual([]);
    expect(t.state.relocates).toBe(0);
    expect(t.state.fetches).toBe(0);
    expect(t.attrs['rediacc.proxy.outcome']).toBe('egress-unreachable');
  });

  it('records relocated on the span when the report moved the org', async () => {
    const t = entry(answered({ count: 3, relocated: true }));
    const response = await t.egress.fetch(unreachable());

    expect(await response.json()).toEqual({
      count: 3,
      threshold: 3,
      relocated: true,
      counted: true,
      probe: 'reachable',
    });
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
      const t = entry(answered());
      const response = await t.egress.fetch(request);

      expect(response.status).toBe(403);
      expect(await response.json()).toMatchObject({ reason: 'route-not-allowed' });
      expect(t.reports).toEqual([]);
      expect(t.accountCalls.count).toBe(0);
    }
  });

  it('a report the probe did not count records target-unreachable and passes the verdict through', async () => {
    const t = entry(answered({ count: 0, counted: false, probe: 'target-unreachable' }));
    const response = await t.egress.fetch(unreachable());

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      count: 0,
      threshold: 3,
      relocated: false,
      counted: false,
      probe: 'target-unreachable',
    });
    expect(t.attrs['rediacc.proxy.outcome']).toBe('target-unreachable');
  });

  it('no body, or an empty one, is a report with no target', async () => {
    const bodiless = new Request('http://account.internal/executor/v1/egress-unreachable', {
      method: 'POST',
    });
    for (const request of [bodiless, unreachable(undefined, 'POST', '')]) {
      const t = entry(answered({ count: 0, counted: false, probe: 'skipped' }));
      const response = await t.egress.fetch(request);

      expect(response.status).toBe(200);
      expect(t.reports).toHaveLength(1);
      expect(t.reports[0]).toMatchObject({ id: 'id:org-a:p0', orgId: 'org-a', placement: 0 });
      expect(t.reports[0].target).toBeUndefined();
      expect(t.attrs['rediacc.proxy.outcome']).toBe('target-unreachable');
    }
  });

  const invalid: [string, string][] = [
    ['bad JSON', '{"host":'],
    ['a body that is not an object', '"203.0.113.7"'],
    ['a missing port', JSON.stringify({ host: '203.0.113.7' })],
    ['a port out of range', JSON.stringify({ host: '203.0.113.7', port: 70000 })],
    [
      'a body over 512 bytes',
      JSON.stringify({ host: '203.0.113.7', port: 22, pad: 'x'.repeat(600) }),
    ],
  ];
  it.each(invalid)('%s is 400 report-target-invalid with no RPC', async (_name, body) => {
    const t = entry(answered());
    const response = await t.egress.fetch(unreachable(undefined, 'POST', body));

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ reason: 'report-target-invalid' });
    expect(t.reports).toEqual([]);
    expect(t.accountCalls.count).toBe(0);
    expect(t.attrs['rediacc.proxy.outcome']).toBe('refused:report-target-invalid');
  });

  const refusedTargets: [string, unknown][] = [
    ['a private IPv4 host', { host: '192.168.1.10', port: 22 }],
    ['loopback', { host: '127.0.0.1', port: 22 }],
    ['localhost', { host: 'localhost', port: 22 }],
    ['IPv6 loopback', { host: '::1', port: 22 }],
    ['port 25', { host: '203.0.113.7', port: 25 }],
  ];
  it.each(refusedTargets)('%s is 403 report-target-refused with no RPC', async (_name, body) => {
    const t = entry(answered());
    const response = await t.egress.fetch(unreachable(undefined, 'POST', JSON.stringify(body)));

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ reason: 'report-target-refused' });
    expect(t.reports).toEqual([]);
    expect(t.accountCalls.count).toBe(0);
    expect(t.attrs['rediacc.proxy.outcome']).toBe('refused:report-target-refused');
  });

  it('never logs the reported address', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const t = entry(answered());
    await t.egress.fetch(
      unreachable(undefined, 'POST', JSON.stringify({ host: '10.1.2.3', port: 22 }))
    );
    await t.egress.fetch(unreachable());
    expect(warn.mock.calls.flat().join(' ')).not.toMatch(/10\.1\.2\.3|203\.0\.113\.7/);
  });
});

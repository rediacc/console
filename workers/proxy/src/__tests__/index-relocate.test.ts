/**
 * The proxy Worker re-routing a relocated org (PLAN-org-executor-connect-timeout-relocate box E7): a pin answered `EXECUTOR_RELOCATED` asks the issuer's route again, once.
 *
 * The same harness as src/__tests__/index.test.ts: a stub ORG_EXECUTOR namespace and a stubbed global fetch for the account server.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import worker, { type Env } from '../index';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';
import type { PinAnswer } from '../org-executor';
import * as placementModule from '../placement';
import { resetReadyCache } from '../ready';

const ACCOUNT_URL = 'https://account.test';
/** What the fake ISSUER mints; the Worker introspects with it. */
const ISSUED = 'rdt_issued_secret';
const CALLER = 'rdt_caller';
/** The org every route below answers. */
const ORG = 'org-1';

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

describe('re-routing a relocated org (PLAN-org-executor-connect-timeout-relocate box E7)', () => {
  /** An ISSUER whose route answers org-1 at each placement in `placements` in turn (the last one repeats); `undefined` stands for an answer without one. */
  function placedIssuer(placements: (number | undefined)[]): {
    binding: Service<ExecutorIssuerRpc>;
    routes: number;
  } {
    const state = { binding: null as never as Service<ExecutorIssuerRpc>, routes: 0 };
    state.binding = {
      route: () => {
        const placement = placements[Math.min(state.routes, placements.length - 1)];
        state.routes += 1;
        return Promise.resolve(
          placement === undefined ? { orgId: ORG } : { orgId: ORG, placement }
        );
      },
      issue: () => Promise.reject(new Error('the front door never mints')),
    } as unknown as Service<ExecutorIssuerRpc>;
    return state;
  }

  /** ORG_EXECUTOR whose stubs answer `EXECUTOR_RELOCATED` for every name in `retired`, and ok otherwise; records each name a pin reached. */
  function namespace(retired: Set<string>): { binding: Env['ORG_EXECUTOR']; pinned: string[] } {
    const pinned: string[] = [];
    const binding = {
      idFromName: (name: string) => ({ name }),
      get: ({ name }: { name: string }) => ({
        oomAt: () => Promise.resolve(undefined),
        oomHeavyAt: () => Promise.resolve(undefined),
        pin: (_orgId: string, _placement: number, size: 'light' | 'heavy'): Promise<PinAnswer> => {
          pinned.push(name);
          return Promise.resolve(
            retired.has(name)
              ? { ok: false, code: 'EXECUTOR_RELOCATED', reason: 'retired' }
              : { ok: true, size, egressUnreachableRecent: false }
          );
        },
        fetch: () => Promise.resolve(Response.json({ from: 'org-executor', name })),
      }),
    } as unknown as Env['ORG_EXECUTOR'];
    return { binding, pinned };
  }

  function durable(issuer: Service<ExecutorIssuerRpc>, executors: Env['ORG_EXECUTOR']): Env {
    return env({ ISSUER: issuer, ORG_EXECUTOR: executors });
  }

  it('a stub answering EXECUTOR_RELOCATED makes the Worker ask route again, and the next pin reaches org-1:p2', async () => {
    const issuer = placedIssuer([1, 2]);
    const executors = namespace(new Set([`${ORG}:p1`]));
    const response = await worker.fetch(
      request('/v1/command', CALLER),
      durable(issuer.binding, executors.binding)
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ from: 'org-executor', name: `${ORG}:p2` });
    expect(issuer.routes).toBe(2);
    expect(executors.pinned).toEqual([`${ORG}:p1`, `${ORG}:p2`]);
  });

  it('re-routes at most once: a second EXECUTOR_RELOCATED is a 503 EXECUTOR_START_FAILED', async () => {
    const issuer = placedIssuer([1, 2, 3]);
    const executors = namespace(new Set([`${ORG}:p1`, `${ORG}:p2`]));
    const response = await worker.fetch(
      request('/v1/command', CALLER),
      durable(issuer.binding, executors.binding)
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
    expect(issuer.routes).toBe(2);
    expect(executors.pinned).toEqual([`${ORG}:p1`, `${ORG}:p2`]);
  });

  it('a route that still names the retired placement is a 503 EXECUTOR_START_FAILED with no second pin', async () => {
    const issuer = placedIssuer([1, 1]);
    const executors = namespace(new Set([`${ORG}:p1`]));
    const response = await worker.fetch(
      request('/v1/command', CALLER),
      durable(issuer.binding, executors.binding)
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ code: 'EXECUTOR_START_FAILED' });
    expect(executors.pinned).toEqual([`${ORG}:p1`]);
  });

  it('a missing placement answers 503 with outcome refused:route-placement-missing and pins nothing', async () => {
    const issuer = placedIssuer([undefined]);
    const executors = namespace(new Set());
    const attrs: Record<string, unknown> = {};
    const ctx = {
      tracing: {
        getActiveSpan: () => ({ setAttribute: (k: string, v: unknown) => (attrs[k] = v) }),
      },
    } as unknown as ExecutionContext;
    const response = await worker.fetch(
      request('/v1/command', CALLER),
      durable(issuer.binding, executors.binding),
      ctx
    );

    expect(response.status).toBe(503);
    expect(attrs['rediacc.proxy.outcome']).toBe('refused:route-placement-missing');
    expect(executors.pinned).toEqual([]);
  });

  it('mutant: an executorName that drops the placement turns the re-route case red', async () => {
    const mutant = vi
      .spyOn(placementModule, 'executorName')
      .mockImplementation((orgId: string) => orgId);
    try {
      const issuer = placedIssuer([1, 2]);
      const executors = namespace(new Set([`${ORG}:p1`]));
      const response = await worker.fetch(
        request('/v1/command', CALLER),
        durable(issuer.binding, executors.binding)
      );
      // The re-route case's own assertions, inverted: under the mutant no request reaches org-1:p2.
      expect(mutant).toHaveBeenCalled();
      expect(await response.json()).not.toEqual({ from: 'org-executor', name: `${ORG}:p2` });
      expect(executors.pinned).not.toContain(`${ORG}:p2`);
    } finally {
      mutant.mockRestore();
    }
  });
});

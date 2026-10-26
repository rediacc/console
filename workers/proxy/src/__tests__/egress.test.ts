/**
 * The `accountEgress` named handler: the instance and org checks that run before the allowlist and before the issuer (agent/plans/PLAN-console-executor-multi-org.md box W1, MU1).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { accountEgress, EXECUTOR_TOKEN_PLACEHOLDER } from '../egress';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';

const API = 'http://account.internal/account/api/v1';

/** `idFromName(name).toString()` is `id:<name>`, which is what the library reports as `containerId` for that instance (`this.ctx.id.toString()`, dist/lib/container.js). */
const EXECUTOR = {
  idFromName: (name: string) => ({ toString: () => `id:${name}` }),
};

function setup() {
  const seen: Request[] = [];
  const state = { issues: [] as string[], fetches: 0 };
  const issuer = {
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

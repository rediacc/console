/**
 * The container's road to `POST /configs/agent-session` (agent/plans/PLAN-rmcp-agent-grants.md box AG-X, Design 4): the executor opens an agent grant under its own issued bearer, so the route is an executor-bearer call, and the allowlist still refuses every neighbour of it.
 *
 * Adversarial like executor-token.test.ts: each case plays the container, and ISSUER and ACCOUNT are fakes that count every call.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { forwardAccountEgress as forward } from '../egress';
import type { Env } from '../index';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';
import { ACCOUNT_EGRESS_HOST } from '../org-executor-support';

const ACCOUNT_URL = 'https://account.test';
const ISSUED = 'rdt_issued_executor_token';
const PLACEHOLDER = 'rediacc-executor-placeholder';
const API = `http://${ACCOUNT_EGRESS_HOST}/account/api/v1`;
const ORG = 'org-1';

function setup() {
  const seen: Request[] = [];
  const counts = { issues: 0 };
  const issuer = {
    issue: () => {
      counts.issues += 1;
      return Promise.resolve({
        token: ISSUED,
        expiresAt: new Date(Date.now() + 45 * 60_000).toISOString(),
      });
    },
    fetch: () =>
      Promise.resolve(new Response('issuer fetch must never be called', { status: 500 })),
  } as unknown as Service<ExecutorIssuerRpc>;
  const account = {
    fetch: (input: Request | string, init?: RequestInit) => {
      seen.push(input instanceof Request ? input : new Request(input, init));
      return Promise.resolve(Response.json({}));
    },
  } as unknown as Fetcher;
  const env = { ACCOUNT_URL, ACCOUNT: account, ISSUER: issuer } as unknown as Env;
  return { env, seen, counts };
}

beforeEach(() => {
  resetIssuedTokenCache();
  vi.restoreAllMocks();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

describe('agent-session through the container egress', () => {
  it('swaps the placeholder for the issued token on POST /configs/agent-session', async () => {
    const { env, seen, counts } = setup();
    const response = await forward(
      new Request(`${API}/configs/agent-session`, {
        method: 'POST',
        headers: { authorization: `Bearer ${PLACEHOLDER}`, 'content-type': 'application/json' },
        body: JSON.stringify({ grantId: 'g_1', authTag: 'tag' }),
      }),
      env,
      ORG
    );
    expect(response.status).toBe(200);
    expect(counts.issues).toBe(1);
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe(`${ACCOUNT_URL}/account/api/v1/configs/agent-session`);
    expect(seen[0]?.headers.get('authorization')).toBe(`Bearer ${ISSUED}`);
    expect(JSON.stringify([...(seen[0]?.headers ?? [])])).not.toContain(PLACEHOLDER);
  });

  const REFUSED: [string, Request, string][] = [
    [
      'DELETE on the agent-session route',
      new Request(`${API}/configs/agent-session`, {
        method: 'DELETE',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
      }),
      'route-not-allowed',
    ],
    [
      'a sibling agent route (grant creation)',
      new Request(`${API}/agent-grants`, {
        method: 'POST',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
        body: '{}',
      }),
      'route-not-allowed',
    ],
    [
      'a nested path under agent-session',
      new Request(`${API}/configs/agent-session/extra`, {
        method: 'POST',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
        body: '{}',
      }),
      'route-not-allowed',
    ],
    [
      'a query on agent-session',
      new Request(`${API}/configs/agent-session?as=admin`, {
        method: 'POST',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
        body: '{}',
      }),
      'query-not-allowed',
    ],
    [
      'a caller token on agent-session',
      new Request(`${API}/configs/agent-session`, {
        method: 'POST',
        headers: { authorization: 'Bearer rdt_caller_token' },
        body: '{}',
      }),
      'bearer-not-placeholder',
    ],
    [
      'no Authorization on agent-session',
      new Request(`${API}/configs/agent-session`, { method: 'POST', body: '{}' }),
      'bearer-missing',
    ],
  ];
  for (const [name, request, reason] of REFUSED) {
    it(`refuses ${name} with 403 ${reason}, forwarding and minting nothing`, async () => {
      const { env, seen, counts } = setup();
      const response = await forward(request, env, ORG);
      expect(response.status).toBe(403);
      expect(await response.json()).toMatchObject({ reason });
      expect(seen).toEqual([]);
      expect(counts.issues).toBe(0);
    });
  }
});

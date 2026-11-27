/**
 * The container's road to the three executor licence routes (agent/plans/PLAN-proxied-licence-tunnel-auth-fix.md, box PL2, Design 6): activate, batch activate and retire travel as executor-bearer calls, and the allowlist still refuses the tunnel, the CLI's own licence routes, and every malformed neighbour of the retire path.
 *
 * Adversarial like agent-session-egress.test.ts: each case plays the container, and ISSUER and ACCOUNT are fakes that count every call. The controls come first.
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
const GUID = '0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d';

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

function post(path: string, headers: Record<string, string> = {}): Request {
  return new Request(`${API}${path}`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${PLACEHOLDER}`,
      'content-type': 'application/json',
      ...headers,
    },
    body: JSON.stringify({ onBehalfOfTokenId: 'tok_principal' }),
  });
}

beforeEach(() => {
  resetIssuedTokenCache();
  vi.restoreAllMocks();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

async function expectRefused(request: Request, reason: string): Promise<void> {
  const { env, seen, counts } = setup();
  const response = await forward(request, env, ORG);
  expect(response.status).toBe(403);
  expect(await response.json()).toMatchObject({ reason });
  expect(seen).toEqual([]);
  expect(counts.issues).toBe(0);
}

describe('controls: what stays refused', () => {
  it('refuses the E2E tunnel route-not-allowed', async () => {
    await expectRefused(post('/tunnel'), 'route-not-allowed');
  });
  it("refuses the CLI's own activate-repo route route-not-allowed", async () => {
    await expectRefused(post('/licenses/activate-repo'), 'route-not-allowed');
  });
  it("refuses the CLI's own retire route route-not-allowed", async () => {
    await expectRefused(post(`/licenses/repos/${GUID}/retire`), 'route-not-allowed');
  });
});

describe('executor licence routes through the container egress', () => {
  const ADMITTED: [string, string][] = [
    ['activate-repo', '/proxy/licenses/activate-repo'],
    ['activate-repo-batch', '/proxy/licenses/activate-repo-batch'],
    ['retire', `/proxy/licenses/repos/${GUID}/retire`],
  ];
  for (const [name, path] of ADMITTED) {
    it(`swaps the placeholder for the issued token on POST ${name}`, async () => {
      const { env, seen, counts } = setup();
      const response = await forward(post(path), env, ORG);
      expect(response.status).toBe(200);
      expect(counts.issues).toBe(1);
      expect(seen).toHaveLength(1);
      expect(seen[0]?.url).toBe(`${ACCOUNT_URL}/account/api/v1${path}`);
      expect(seen[0]?.headers.get('authorization')).toBe(`Bearer ${ISSUED}`);
      expect(JSON.stringify([...(seen[0]?.headers ?? [])])).not.toContain(PLACEHOLDER);
    });
  }

  const REFUSED: [string, Request, string][] = [
    [
      'a retire with a non-UUID segment',
      post('/proxy/licenses/repos/not-a-uuid/retire'),
      'route-not-allowed',
    ],
    [
      'a retire with an upper-case UUID',
      post(`/proxy/licenses/repos/${GUID.toUpperCase()}/retire`),
      'route-not-allowed',
    ],
    [
      'a retire with a nested segment',
      post(`/proxy/licenses/repos/${GUID}/x/retire`),
      'route-not-allowed',
    ],
    [
      'a retire with a query',
      post(`/proxy/licenses/repos/${GUID}/retire?teamId=x`),
      'query-not-allowed',
    ],
    ['an activate with a query', post('/proxy/licenses/activate-repo?x=1'), 'query-not-allowed'],
    [
      'a GET on activate-repo',
      new Request(`${API}/proxy/licenses/activate-repo`, {
        method: 'GET',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
      }),
      'route-not-allowed',
    ],
    [
      'a DELETE on retire',
      new Request(`${API}/proxy/licenses/repos/${GUID}/retire`, {
        method: 'DELETE',
        headers: { authorization: `Bearer ${PLACEHOLDER}` },
      }),
      'route-not-allowed',
    ],
    [
      'a caller token on activate-repo',
      post('/proxy/licenses/activate-repo', { authorization: 'Bearer rdt_caller_token' }),
      'bearer-not-placeholder',
    ],
  ];
  for (const [name, request, reason] of REFUSED) {
    it(`refuses ${name} with 403 ${reason}, forwarding and minting nothing`, async () => {
      await expectRefused(request, reason);
    });
  }
});

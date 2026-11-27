/**
 * The container's road to the account server's executor router (agent/plans/PLAN-executor-account-routes.md, box EA3, Design 6): every pair of `EXECUTOR_ACCOUNT_PAIRS` travels as an executor-bearer call with the placeholder swapped and the `X-Rediacc-On-Behalf-Of` principal header forwarded, each with its own query set; the tunnel, the CLI's own paths of the same calls and PL1's removed `/proxy/licenses` routes stay refused. The parity test holds the egress list equal to the shared table entry for entry.
 *
 * Adversarial like agent-session-egress.test.ts: each case plays the container, and ISSUER and ACCOUNT are fakes that count every call. The controls come first.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  EXECUTOR_ACCOUNT_ROUTES,
  EXECUTOR_SEGMENT_PATTERNS,
  type ExecutorSegmentType,
} from '../../../../packages/shared/src/subscription/executor-account-routes.js';
import { EXECUTOR_ACCOUNT_PAIRS, forwardAccountEgress as forward } from '../egress';
import type { Env } from '../index';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';
import { ACCOUNT_EGRESS_HOST } from '../org-executor-support';

const ACCOUNT_URL = 'https://account.test';
const ISSUED = 'rdt_issued_executor_token';
const PLACEHOLDER = 'rediacc-executor-placeholder';
const API = `http://${ACCOUNT_EGRESS_HOST}/account/api/v1`;
const EXEC = '/proxy/account';
const ORG = 'org-1';
const PRINCIPAL = 'tok_principal';
const GUID = '0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d';
const MACHINE = 'ab'.repeat(32);
const LINEAGE = 'lin-0001';
const SNAPSHOT = 'snap-0001';

/** A real value for each typed segment, matching the shared pattern. */
const SAMPLE: Record<ExecutorSegmentType, string> = {
  lineage: LINEAGE,
  snapshot: SNAPSHOT,
  machine: MACHINE,
  uuid: GUID,
};

/** An inner template with every typed segment filled by its sample. */
function fill(inner: string): string {
  return inner
    .split('/')
    .map((segment) =>
      segment.startsWith(':') ? SAMPLE[segment.slice(1) as ExecutorSegmentType] : segment
    )
    .join('/');
}

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

/** A container request on `path` (under /account/api/v1) with the placeholder bearer and the principal header. */
function send(method: string, path: string, headers: Record<string, string> = {}): Request {
  const hasBody = method !== 'GET' && method !== 'HEAD';
  return new Request(`${API}${path}`, {
    method,
    headers: {
      authorization: `Bearer ${PLACEHOLDER}`,
      'x-rediacc-on-behalf-of': PRINCIPAL,
      ...(hasBody ? { 'content-type': 'application/json' } : {}),
      ...headers,
    },
    ...(hasBody ? { body: JSON.stringify({ probe: true }) } : {}),
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
  const CONTROLS: [string, Request][] = [
    ['the E2E tunnel', send('POST', '/tunnel')],
    ["the CLI's own GET backups/usage", send('GET', '/backups/usage')],
    ["the CLI's own POST licenses/activate-repo", send('POST', '/licenses/activate-repo')],
    ["the CLI's own licence retire", send('POST', `/licenses/repos/${GUID}/retire`)],
    [
      "PL1's removed POST proxy/licenses/activate-repo",
      send('POST', '/proxy/licenses/activate-repo'),
    ],
    [
      "PL1's removed POST proxy/licenses/activate-repo-batch",
      send('POST', '/proxy/licenses/activate-repo-batch'),
    ],
    ["PL1's removed licence retire", send('POST', `/proxy/licenses/repos/${GUID}/retire`)],
    ['an unlisted executor route (api-tokens)', send('GET', `${EXEC}/api-tokens`)],
    ['an unlisted executor route (backups/session)', send('GET', `${EXEC}/backups/session`)],
    ['the executor mount root', send('GET', EXEC)],
  ];
  for (const [name, request] of CONTROLS) {
    it(`refuses ${name} 403 route-not-allowed`, async () => {
      await expectRefused(request, 'route-not-allowed');
    });
  }
});

describe('every executor account pair through the container egress', () => {
  for (const route of EXECUTOR_ACCOUNT_ROUTES) {
    const path = `${EXEC}/${fill(route.inner)}`;
    it(`admits ${route.method} ${route.inner} with the placeholder swapped and the principal forwarded`, async () => {
      const { env, seen, counts } = setup();
      const response = await forward(send(route.method, path), env, ORG);
      expect(response.status).toBe(200);
      expect(counts.issues).toBe(1);
      expect(seen).toHaveLength(1);
      const out = seen[0];
      expect(out?.method).toBe(route.method);
      expect(out?.url).toBe(`${ACCOUNT_URL}/account/api/v1${path}`);
      expect(out?.headers.get('authorization')).toBe(`Bearer ${ISSUED}`);
      expect(out?.headers.get('x-rediacc-on-behalf-of')).toBe(PRINCIPAL);
      expect(JSON.stringify([...(out?.headers ?? [])])).not.toContain(PLACEHOLDER);
      if (route.method !== 'GET') expect(await out?.text()).toBe('{"probe":true}');
    });
  }

  for (const route of EXECUTOR_ACCOUNT_ROUTES.filter((r) => r.query.length > 0)) {
    const path = `${EXEC}/${fill(route.inner)}`;
    it(`admits ${route.method} ${route.inner} with its whole query set, forwarded intact`, async () => {
      const query = route.query.map((name, index) => `${name}=v${index}`).join('&');
      const { env, seen } = setup();
      const response = await forward(send(route.method, `${path}?${query}`), env, ORG);
      expect(response.status).toBe(200);
      expect(seen[0]?.url).toBe(`${ACCOUNT_URL}/account/api/v1${path}?${query}`);
    });
  }
});

describe('refusals on the executor account pairs', () => {
  const REFUSED: [string, Request, string][] = [
    ['a POST on GET backups/usage', send('POST', `${EXEC}/backups/usage`), 'route-not-allowed'],
    [
      'a PUT on backups/immutability (immutability set is not served)',
      send('PUT', `${EXEC}/backups/immutability`),
      'route-not-allowed',
    ],
    [
      'a DELETE on a snapshot (snapshots delete is not served)',
      send('DELETE', `${EXEC}/backups/snapshots/${SNAPSHOT}`),
      'route-not-allowed',
    ],
    ['a GET on POST backups/verify', send('GET', `${EXEC}/backups/verify`), 'route-not-allowed'],
    [
      'a lineage segment of 65 characters',
      send('GET', `${EXEC}/backups/stores/lineage/${'a'.repeat(65)}`),
      'route-not-allowed',
    ],
    [
      'a lineage segment with an underscore',
      send('DELETE', `${EXEC}/backups/lineages/lin_1`),
      'route-not-allowed',
    ],
    [
      'a lineage segment with an encoded slash',
      send('POST', `${EXEC}/backups/lineages/a%2Fb/orphan`),
      'route-not-allowed',
    ],
    [
      'a nested snapshot segment',
      send('POST', `${EXEC}/backups/snapshots/${SNAPSHOT}/x/undelete`),
      'route-not-allowed',
    ],
    [
      'a machine id of 63 hex characters',
      send('POST', `${EXEC}/licenses/machines/${MACHINE.slice(1)}/deactivate`),
      'route-not-allowed',
    ],
    [
      'a machine id that is not hex',
      send('POST', `${EXEC}/licenses/machines/${'z'.repeat(64)}/deactivate`),
      'route-not-allowed',
    ],
    [
      'a retire with an upper-case UUID',
      send('POST', `${EXEC}/licenses/repos/${GUID.toUpperCase()}/retire`),
      'route-not-allowed',
    ],
    [
      'a retire with a non-UUID segment',
      send('POST', `${EXEC}/licenses/repos/not-a-uuid/retire`),
      'route-not-allowed',
    ],
    [
      'a trailing slash on backups/usage',
      send('GET', `${EXEC}/backups/usage/`),
      'route-not-allowed',
    ],
    [
      'a teamId query on the manifests read',
      send('GET', `${EXEC}/backups/manifests?lineage=${LINEAGE}&teamId=x`),
      'query-not-allowed',
    ],
    [
      'a repeated lineage on the manifests read',
      send('GET', `${EXEC}/backups/manifests?lineage=a&lineage=b`),
      'query-not-allowed',
    ],
    [
      'a manifests-only name on the resolve read',
      send('GET', `${EXEC}/backups/snapshots/resolve?lineage=a&limit=1`),
      'query-not-allowed',
    ],
    [
      'an extra name on the retention read',
      send('GET', `${EXEC}/backups/retention?lineage=a&before=x`),
      'query-not-allowed',
    ],
    ['any query on backups/usage', send('GET', `${EXEC}/backups/usage?x=1`), 'query-not-allowed'],
    [
      'a teamId query on the licence report',
      send('GET', `${EXEC}/licenses/report?teamId=t`),
      'query-not-allowed',
    ],
    [
      'a query on the licence retire',
      send('POST', `${EXEC}/licenses/repos/${GUID}/retire?teamId=x`),
      'query-not-allowed',
    ],
    [
      'a caller token on backups/usage',
      send('GET', `${EXEC}/backups/usage`, { authorization: 'Bearer rdt_caller_token' }),
      'bearer-not-placeholder',
    ],
    [
      'a caller token on licence activate',
      send('POST', `${EXEC}/licenses/activate-repo`, { authorization: 'Bearer rdt_caller_token' }),
      'bearer-not-placeholder',
    ],
  ];
  for (const [name, request, reason] of REFUSED) {
    it(`refuses ${name} with 403 ${reason}, forwarding and minting nothing`, async () => {
      await expectRefused(request, reason);
    });
  }

  it('refuses a pair with no Authorization 403 bearer-missing', async () => {
    const request = new Request(`${API}${EXEC}/backups/status`, {
      headers: { 'x-rediacc-on-behalf-of': PRINCIPAL },
    });
    await expectRefused(request, 'bearer-missing');
  });
});

describe('parity with the shared executor account-route table', () => {
  /** The egress pattern the shared template implies: the executor prefix, then each segment literal or its shared pattern's body. */
  function expectedPattern(inner: string): RegExp {
    const body = inner
      .split('/')
      .map((segment) => {
        if (!segment.startsWith(':')) return segment;
        const source = EXECUTOR_SEGMENT_PATTERNS[segment.slice(1) as ExecutorSegmentType].source;
        return source.replace(/^\^/, '').replace(/\$$/, '');
      })
      .join('/');
    return new RegExp(`^/account/api/v1/proxy/account/${body}$`);
  }

  it('lists exactly the shared entries, in order', () => {
    expect(EXECUTOR_ACCOUNT_PAIRS).toHaveLength(EXECUTOR_ACCOUNT_ROUTES.length);
  });

  EXECUTOR_ACCOUNT_ROUTES.forEach((route, index) => {
    it(`pair ${index} matches ${route.method} ${route.inner}: method, pattern and query set`, () => {
      const pair = EXECUTOR_ACCOUNT_PAIRS[index];
      expect(pair?.method).toBe(route.method);
      expect(pair?.pattern.source).toBe(expectedPattern(route.inner).source);
      expect(pair?.pattern.flags).toBe('');
      expect([...(pair?.query ?? [])]).toEqual([...route.query]);
    });
  });
});

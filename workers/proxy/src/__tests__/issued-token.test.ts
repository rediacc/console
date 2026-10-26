/**
 * The per-org issued-token cache (agent/plans/PLAN-console-executor-multi-org.md box W2): single flight, failure backoff and the LRU bound, each per org.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { forwardAccountEgress } from '../egress';
import {
  dropIssuedToken,
  type ExecutorIssuerRpc,
  FAILURE_BACKOFF_MS,
  type IssuedToken,
  IssuerError,
  issuedToken,
  MAX_CACHED_ORGS,
  resetIssuedTokenCache,
} from '../issued-token';

const T0 = Date.parse('2026-10-26T12:00:00Z');
const LIFE = 45 * 60_000;

/** An issuer that records every issue() call by org and answers `answer(orgId, serial)`. */
function issuerOf(answer: (orgId: string, serial: number) => Promise<IssuedToken>): {
  binding: Service<ExecutorIssuerRpc>;
  calls: string[];
} {
  const calls: string[] = [];
  const binding = {
    issue: (orgId: string) => {
      calls.push(orgId);
      return answer(orgId, calls.length);
    },
  } as unknown as Service<ExecutorIssuerRpc>;
  return { binding, calls };
}

/** Answers `tok-<org>-<serial>` after a yield, so concurrent callers really overlap. */
function minting(clock: () => number = () => T0) {
  return issuerOf(async (orgId, serial) => {
    await new Promise((resolve) => setTimeout(resolve, 2));
    return { token: `tok-${orgId}-${serial}`, expiresAt: new Date(clock() + LIFE).toISOString() };
  });
}

beforeEach(() => {
  resetIssuedTokenCache();
  vi.restoreAllMocks();
});

describe('per-org issued token cache', () => {
  it('makes exactly one mint per org under 10 concurrent requests each for orgs A and B', async () => {
    const issuer = minting();
    const now = () => T0;
    const burst = (org: string) =>
      Array.from({ length: 10 }, () => issuedToken(issuer.binding, org, now));
    const [a, b] = await Promise.all([Promise.all(burst('org-a')), Promise.all(burst('org-b'))]);

    expect([...issuer.calls].sort((x, y) => x.localeCompare(y))).toEqual(['org-a', 'org-b']);
    expect(new Set(a).size).toBe(1);
    expect(new Set(b).size).toBe(1);
  });

  it("never returns org A's token for org B", async () => {
    const issuer = minting();
    const a = await issuedToken(issuer.binding, 'org-a', () => T0);
    const b = await issuedToken(issuer.binding, 'org-b', () => T0);

    expect(a).toContain('org-a');
    expect(b).toContain('org-b');
    expect(b).not.toBe(a);
    expect(await issuedToken(issuer.binding, 'org-a', () => T0)).toBe(a);
    expect(await issuedToken(issuer.binding, 'org-b', () => T0)).toBe(b);
    expect(issuer.calls).toEqual(['org-a', 'org-b']);
  });

  it("does not let org A's refusal backoff delay org B, and lifts it after the window", async () => {
    let clock = T0;
    const now = () => clock;
    const issuer = issuerOf((orgId, serial) =>
      orgId === 'org-a'
        ? Promise.reject(new Error('ISSUER_ORG_BLOCKED'))
        : Promise.resolve({
            token: `tok-${orgId}-${serial}`,
            expiresAt: new Date(clock + LIFE).toISOString(),
          })
    );
    for (let i = 0; i < 5; i += 1) {
      await expect(issuedToken(issuer.binding, 'org-a', now)).rejects.toMatchObject({
        reason: 'issuer-refused:ISSUER_ORG_BLOCKED',
      });
    }
    expect(issuer.calls).toEqual(['org-a']);

    // B is asked at once, inside A's backoff window.
    expect(await issuedToken(issuer.binding, 'org-b', now)).toBe('tok-org-b-2');
    expect(issuer.calls).toEqual(['org-a', 'org-b']);

    clock += FAILURE_BACKOFF_MS;
    await expect(issuedToken(issuer.binding, 'org-a', now)).rejects.toBeInstanceOf(IssuerError);
    expect(issuer.calls).toEqual(['org-a', 'org-b', 'org-a']);
  });

  it('evicts the least recently used org when the 65th arrives', async () => {
    const issuer = minting();
    const now = () => T0;
    for (let i = 0; i < MAX_CACHED_ORGS; i += 1) await issuedToken(issuer.binding, `org-${i}`, now);
    expect(issuer.calls).toHaveLength(MAX_CACHED_ORGS);

    // org-0 is used again, so org-1 is now the least recently used.
    await issuedToken(issuer.binding, 'org-0', now);
    await issuedToken(issuer.binding, 'org-new', now);
    expect(issuer.calls).toHaveLength(MAX_CACHED_ORGS + 1);

    await issuedToken(issuer.binding, 'org-0', now);
    await issuedToken(issuer.binding, 'org-2', now);
    expect(issuer.calls).toHaveLength(MAX_CACHED_ORGS + 1);

    await issuedToken(issuer.binding, 'org-1', now);
    expect(issuer.calls).toHaveLength(MAX_CACHED_ORGS + 2);
    expect(issuer.calls.at(-1)).toBe('org-1');
  });

  it("drops one org's entry on request, and only that org's", async () => {
    const issuer = minting();
    const now = () => T0;
    await issuedToken(issuer.binding, 'org-a', now);
    await issuedToken(issuer.binding, 'org-b', now);
    dropIssuedToken('org-a');
    dropIssuedToken('org-unknown');

    await issuedToken(issuer.binding, 'org-b', now);
    expect(issuer.calls).toEqual(['org-a', 'org-b']);
    expect(await issuedToken(issuer.binding, 'org-a', now)).toBe('tok-org-a-3');
    expect(issuer.calls).toEqual(['org-a', 'org-b', 'org-a']);
  });

  it('serves the unexpired token when a renewal fails, per org', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    let clock = T0;
    const outage: { down: boolean } = { down: false };
    const issuer = issuerOf((orgId) =>
      outage.down
        ? Promise.reject(new Error('down'))
        : Promise.resolve({
            token: `tok-${orgId}`,
            expiresAt: new Date(clock + LIFE).toISOString(),
          })
    );
    const now = () => clock;
    await issuedToken(issuer.binding, 'org-a', now);
    outage.down = true;
    clock = T0 + 0.9 * LIFE;
    expect(await issuedToken(issuer.binding, 'org-a', now)).toBe('tok-org-a');
    await expect(issuedToken(issuer.binding, 'org-b', now)).rejects.toMatchObject({
      reason: 'issuer-refused',
    });
  });

  it('refuses no binding as no-issuer', async () => {
    await expect(issuedToken(undefined, 'org-a')).rejects.toMatchObject({ reason: 'no-issuer' });
  });
});

describe('a 401 on a bearer route', () => {
  it("drops that org's token only, so the next call mints again", async () => {
    // The egress reads the real clock, so the issuer's expiry follows it.
    const issuer = minting(Date.now);
    // Only org-a's token is refused by the account server.
    const refused = new Set(['org-a']);
    let current = '';
    const account = {
      fetch: () =>
        Promise.resolve(new Response('{}', { status: refused.has(current) ? 401 : 200 })),
    } as unknown as Fetcher;
    const env = {
      EXECUTOR: null as never,
      ACCOUNT_URL: 'https://account.test',
      ACCOUNT: account,
      ISSUER: issuer.binding,
    };
    const send = (org: string) => {
      current = org;
      return forwardAccountEgress(
        new Request('http://account.internal/account/api/v1/licenses/audit-events', {
          method: 'POST',
          headers: { authorization: 'Bearer rediacc-executor-placeholder' },
          body: '{}',
        }),
        env,
        org
      );
    };
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    await send('org-a');
    await send('org-b');
    expect(issuer.calls).toEqual(['org-a', 'org-b']);

    refused.clear();
    await send('org-a');
    await send('org-b');
    expect(issuer.calls).toEqual(['org-a', 'org-b', 'org-a']);
  });
});

/**
 * Grant resolution on the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md RW-T3, Design 4): the cache around the account's `resolveGrant`, its TTL, the purge a pushed revocation makes, and the `/internal/revoke` route that carries it.
 */

import { describe, expect, it, vi } from 'vitest';
import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_MCP_EU_HOST,
} from '../../../../packages/shared/src/config/well-known.generated.js';
import { deriveAuthTag } from '../../../../packages/shared/src/config-crypto/agent-grant.js';
import { type CallDeps, callTool } from '../call.js';
import {
  createGrantResolver,
  GRANT_CACHE_TTL_MS,
  type GrantsBinding,
  type ResolvedGrantWire,
} from '../resolve.js';
import { handleRevoke } from '../revoke.js';
import { createMcpTransport } from '../transport.js';
import { bearerFor, SECRET_BYTES } from './helpers/grant.js';

const GRANT_ID = 'eu_grant_t3';
const T0 = Date.UTC(2026, 10, 25, 12, 0, 0);

function wire(overrides: Partial<ResolvedGrantWire> = {}): ResolvedGrantWire {
  return {
    grantId: GRANT_ID,
    state: 'active',
    orgId: 'org-t3',
    placement: 2,
    tier: 'standard',
    userId: 'user-t3',
    teamId: null,
    configId: 'cfg-t3',
    region: 'eu',
    scope: { readOnly: true, tools: ['repo_list'] },
    expiresAt: new Date(T0 + 7 * 86_400_000).toISOString(),
    ...overrides,
  };
}

/** A binding that answers from `answer()` and counts its calls. */
function binding(answer: () => ResolvedGrantWire | null | Promise<ResolvedGrantWire | null>) {
  const calls: Array<{ grantId: string; authTag: string }> = [];
  const grants: GrantsBinding = {
    resolveGrant: (grantId, authTag) => {
      calls.push({ grantId, authTag });
      return Promise.resolve(answer());
    },
  };
  return { grants, calls };
}

describe('grant resolver cache', () => {
  it('serves an active answer from the cache for 30 s and asks the account again after', async () => {
    let now = T0;
    const { grants, calls } = binding(() => wire());
    const resolver = createGrantResolver(grants, () => now);
    const tag = await deriveAuthTag(SECRET_BYTES);

    const first = await resolver(GRANT_ID, tag);
    now = T0 + GRANT_CACHE_TTL_MS - 1;
    const second = await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(1);
    expect(second).toBe(first);
    expect(first).toMatchObject({
      grantId: GRANT_ID,
      state: 'active',
      orgId: 'org-t3',
      placement: 2,
      tier: 'standard',
      userId: 'user-t3',
      scope: { readOnly: true, tools: ['repo_list'], machines: null, repos: null },
    });

    now = T0 + GRANT_CACHE_TTL_MS;
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(2);
  });

  it('caches for min(30 s, expiresAt - now): a grant ending in 10 s is asked again after 10 s', async () => {
    let now = T0;
    const { grants, calls } = binding(() =>
      wire({ expiresAt: new Date(T0 + 10_000).toISOString() })
    );
    const resolver = createGrantResolver(grants, () => now);
    const tag = await deriveAuthTag(SECRET_BYTES);

    await resolver(GRANT_ID, tag);
    now = T0 + 9_999;
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(1);
    now = T0 + 10_000;
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(2);
  });

  it('does not cache an answer whose expiry has passed, or a grant that ended', async () => {
    const now = T0;
    const answers = [
      wire({ expiresAt: new Date(T0 - 1).toISOString() }),
      wire({ state: 'revoked', reason: 'revoked' }),
    ];
    const { grants, calls } = binding(() => answers[calls.length - 1]);
    const resolver = createGrantResolver(grants, () => now);
    const tag = await deriveAuthTag(SECRET_BYTES);

    await resolver(GRANT_ID, tag);
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(2);
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(3);
  });

  it("keys the cache by tag: another tag is asked, never served the first tag's entry", async () => {
    const { grants, calls } = binding(() => wire());
    const resolver = createGrantResolver(grants, () => T0);
    await resolver(GRANT_ID, await deriveAuthTag(SECRET_BYTES));
    await resolver(GRANT_ID, 'some-other-tag');
    expect(calls).toHaveLength(2);
  });

  it('answers null for an unknown grant and for an answer naming another grant', async () => {
    const resolver = createGrantResolver(binding(() => null).grants, () => T0);
    expect(await resolver(GRANT_ID, 'tag')).toBeNull();
    const mismatched = createGrantResolver(
      binding(() => wire({ grantId: 'eu_someone_else' })).grants,
      () => T0
    );
    expect(await mismatched(GRANT_ID, 'tag')).toBeNull();
  });

  it('a purge drops the entry, so the next call asks the account', async () => {
    const { grants, calls } = binding(() => wire());
    const resolver = createGrantResolver(grants, () => T0);
    const tag = await deriveAuthTag(SECRET_BYTES);
    await resolver(GRANT_ID, tag);
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(1);

    expect(resolver.purge(GRANT_ID)).toBe(1);
    expect(resolver.purge('eu_other')).toBe(0);
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(2);
  });

  it('a purge voids a lookup already in flight, so a slow stale answer is not cached', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const state: { slow: boolean } = { slow: true };
    const { grants, calls } = binding(async () => {
      if (state.slow) await gate;
      return wire();
    });
    const resolver = createGrantResolver(grants, () => T0);
    const tag = await deriveAuthTag(SECRET_BYTES);
    const inFlight = resolver(GRANT_ID, tag);
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    resolver.purge(GRANT_ID);
    state.slow = false;
    release?.();
    await inFlight;
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(2);
  });

  it('fresh skips the cache and does not write it', async () => {
    const { grants, calls } = binding(() => wire());
    const resolver = createGrantResolver(grants, () => T0);
    const tag = await deriveAuthTag(SECRET_BYTES);
    await resolver.fresh(GRANT_ID, tag);
    await resolver.fresh(GRANT_ID, tag);
    expect(calls).toHaveLength(2);
    await resolver(GRANT_ID, tag);
    expect(calls).toHaveLength(3);
  });
});

describe('a revoked grant', () => {
  const deps: CallDeps = {
    executor: undefined,
    reauthUrl: (id) => `https://account.test/account/mcp/authorize?grant=${id}`,
  };

  it('is still served from the cache until the purge, then refused on the next call', async () => {
    const account: { revoked: boolean } = { revoked: false };
    const { grants } = binding(() =>
      account.revoked ? wire({ state: 'revoked', reason: 'revoked' }) : wire()
    );
    const resolver = createGrantResolver(grants, () => T0);
    const tag = await deriveAuthTag(SECRET_BYTES);

    // Cached while active; the account revokes the grant afterwards.
    await resolver(GRANT_ID, tag);
    account.revoked = true;
    expect((await resolver(GRANT_ID, tag))?.state).toBe('active');

    const response = await handleRevoke(
      new Request('https://mcp.test/internal/revoke', {
        method: 'POST',
        headers: { authorization: 'Bearer revoke-secret' },
        body: JSON.stringify({ grantId: GRANT_ID }),
      }),
      { token: 'revoke-secret', resolver }
    );
    expect(response.status).toBe(204);

    const after = await resolver(GRANT_ID, tag);
    expect(after?.state).toBe('revoked');
    if (!after) throw new Error('grant not resolved');
    const refused = await callTool(deps, { grant: after, secret: 's' }, 'repo_list', {});
    expect(refused.isError).toBe(true);
    expect(refused.structuredContent).toMatchObject({ code: 'REDIACC_GRANT_REVOKED' });
  });
});

describe('POST /internal/revoke', () => {
  const resolver = () => createGrantResolver(binding(() => wire()).grants, () => T0);
  const post = (headers: Record<string, string>, body: string, method = 'POST') =>
    new Request('https://mcp.test/internal/revoke', {
      method,
      headers,
      body: method === 'POST' ? body : undefined,
    });

  it('answers 404 when the Worker has no secret, so the path looks absent', async () => {
    const res = await handleRevoke(post({ authorization: 'Bearer x' }, '{}'), {
      token: undefined,
      resolver: resolver(),
    });
    expect(res.status).toBe(404);
  });

  it('refuses a missing, wrong or non-bearer credential with 401 and purges nothing', async () => {
    const r = resolver();
    const tag = await deriveAuthTag(SECRET_BYTES);
    await r(GRANT_ID, tag);
    const body = JSON.stringify({ grantId: GRANT_ID });
    for (const headers of [
      {} as Record<string, string>,
      { authorization: 'Bearer wrong' },
      { authorization: 'Basic abc' },
    ]) {
      const res = await handleRevoke(post(headers, body), { token: 'revoke-secret', resolver: r });
      expect(res.status).toBe(401);
    }
    expect(r.purge(GRANT_ID)).toBe(1);
  });

  it('refuses a malformed body and a method other than POST', async () => {
    const options = { token: 'revoke-secret', resolver: resolver() };
    const auth = { authorization: 'Bearer revoke-secret' };
    expect((await handleRevoke(post(auth, 'not json'), options)).status).toBe(400);
    expect((await handleRevoke(post(auth, '{}'), options)).status).toBe(400);
    expect((await handleRevoke(post(auth, '{"grantId":"a b"}'), options)).status).toBe(400);
    expect((await handleRevoke(post(auth, '', 'GET'), options)).status).toBe(405);
  });
});

describe('a failing grant lookup', () => {
  it('answers 503 with Retry-After, not the 401 that sends a client to sign in again', async () => {
    const worker = createMcpTransport({
      host: WK_MCP_EU_HOST,
      serverVersion: '0.0.0-test',
      accountUrl: WK_ACCOUNT_DEFAULT_ORIGIN,
      resolveGrant: () => Promise.reject(new Error('account unreachable')),
      executor: undefined,
    });
    const response = await worker.fetch(
      new Request(`https://${WK_MCP_EU_HOST}/g/${GRANT_ID}`, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${bearerFor(GRANT_ID)}`,
          'content-type': 'application/json',
        },
        body: '{}',
      })
    );
    expect(response.status).toBe(503);
    expect(response.headers.get('retry-after')).toBe('5');
  });
});

/**
 * Pushed grant revocation at the proxy (agent/plans/PLAN-rmcp-agent-grants.md Design 5, box AG-S5): `OrgExecutor.revokeGrant` forwards the grant id to the container's revoke route through the same forward as every call, a request already in flight completes while the next one is refused, and an idle org (no container) is not started for it.
 *
 * The container is the harness fake (src/__tests__/helpers/org-executor-harness.ts); its app keeps a revoked set the way the real session store does.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('cloudflare:workers', () => {
  class Base {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  }
  return { DurableObject: Base, WorkerEntrypoint: Base };
});

import { isRevokeGrantPath, REVOKE_GRANT_PATH } from '../org-executor-mcp';
import { flush, harness, ORG, openStream, T0 } from './helpers/org-executor-harness';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(T0);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('OrgExecutor.revokeGrant', () => {
  it('posts only the grant id to the container revoke route', async () => {
    const h = harness();
    await h.ready;
    let seen: { path: string; method: string; body: string } | undefined;
    h.container.app = async (request) => {
      seen = {
        path: new URL(request.url).pathname,
        method: request.method,
        body: await request.text(),
      };
      return Response.json({ dropped: true });
    };
    await h.executor.pin(ORG, 0, 'light');
    expect(await h.executor.revokeGrant('eu_grant1')).toEqual({ ok: true, dropped: true });
    expect(seen).toEqual({
      path: REVOKE_GRANT_PATH,
      method: 'POST',
      body: JSON.stringify({ grantId: 'eu_grant1' }),
    });
  });

  it('answers the container own dropped field: false when it held no session for the grant', async () => {
    const h = harness();
    await h.ready;
    h.container.app = () => Response.json({ dropped: false });
    await h.executor.pin(ORG, 0, 'light');
    expect(await h.executor.revokeGrant('eu_grant1')).toEqual({ ok: true, dropped: false });
  });

  it('answers 502 EXECUTOR_FAILED when the container answers 200 with a body that is not JSON', async () => {
    const h = harness();
    await h.ready;
    h.container.app = () => new Response('<html>ok</html>', { status: 200 });
    await h.executor.pin(ORG, 0, 'light');
    expect(await h.executor.revokeGrant('eu_grant1')).toEqual({
      ok: false,
      code: 'EXECUTOR_FAILED',
      status: 502,
    });
  });

  it('answers 502 EXECUTOR_FAILED for a 200 with an empty body, not dropped:true (review 530c463a.2)', async () => {
    const h = harness();
    await h.ready;
    h.container.app = () => new Response('', { status: 200 });
    await h.executor.pin(ORG, 0, 'light');
    expect(await h.executor.revokeGrant('eu_grant1')).toEqual({
      ok: false,
      code: 'EXECUTOR_FAILED',
      status: 502,
    });
  });

  it('starts nothing when no container runs: there is no session to drop', async () => {
    const h = harness();
    await h.ready;
    expect(await h.executor.revokeGrant('eu_grant1')).toEqual({ ok: true, dropped: false });
    expect(h.container.starts).toHaveLength(0);
  });

  it('answers the container refusal code', async () => {
    const h = harness();
    await h.ready;
    h.container.app = () => Response.json({ code: 'EXECUTOR_FAILED' }, { status: 500 });
    await h.executor.pin(ORG, 0, 'light');
    expect(await h.executor.revokeGrant('eu_grant1')).toEqual({
      ok: false,
      code: 'EXECUTOR_FAILED',
      status: 500,
    });
  });

  it('lets a request in flight finish while the next one is refused', async () => {
    const h = harness();
    await h.ready;
    const revoked = new Set<string>();
    const stream = openStream();
    h.container.app = async (request) => {
      const { pathname, searchParams } = new URL(request.url);
      if (pathname === REVOKE_GRANT_PATH) {
        revoked.add(((await request.json()) as { grantId: string }).grantId);
        return Response.json({ dropped: true });
      }
      if (revoked.has(searchParams.get('grant') ?? '')) {
        return Response.json({ code: 'GRANT_REVOKED' }, { status: 403 });
      }
      return stream.response;
    };
    await h.executor.pin(ORG, 0, 'light');
    const inFlight = await h.executor.fetch(new Request('https://proxy/v1/command?grant=g1'));
    await flush();
    expect(await h.executor.revokeGrant('g1')).toEqual({ ok: true, dropped: true });
    const next = await h.executor.fetch(new Request('https://proxy/v1/command?grant=g1'));
    expect(next.status).toBe(403);
    // The first request still reads its body to the end.
    stream.close();
    expect(await inFlight.text()).toContain('"line":1');
  });

  it('refuses every spelling of the revoke route on the public forward', async () => {
    const h = harness();
    await h.ready;
    let reached = 0;
    h.container.app = () => {
      reached += 1;
      return new Response('reached');
    };
    await h.executor.pin(ORG, 0, 'light');
    for (const path of [
      REVOKE_GRANT_PATH,
      '/v1/mcp/%72evoke',
      '//v1/mcp/revoke',
      '/v1//mcp/revoke/',
    ]) {
      const response = await h.executor.fetch(
        new Request(`https://proxy${path}`, { method: 'POST', body: '{"grantId":"g1"}' })
      );
      expect(response.status, path).toBe(404);
    }
    expect(reached).toBe(0);
    expect(await (await h.executor.fetch(new Request('https://proxy/v1/command'))).text()).toBe(
      'reached'
    );
  });
});

describe('isRevokeGrantPath', () => {
  it('fails closed on a pathname that does not decode, and passes an ordinary one', () => {
    expect(isRevokeGrantPath('/v1/mcp/revoke%')).toBe(true);
    expect(isRevokeGrantPath('/v1/command%')).toBe(true);
    expect(isRevokeGrantPath('/v1/command')).toBe(false);
  });
});

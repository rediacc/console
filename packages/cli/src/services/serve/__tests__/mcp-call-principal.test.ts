/**
 * A hosted MCP tool call in container mode acts for its principal on account calls (PLAN-proxied-licence-tunnel-auth-fix PL3,
 * PLAN-executor-account-routes EA4): `dispatcher` hands the grant's token id to the real `dispatchCommand`, whose container wrap
 * makes `accountServerFetch` send the call plain to the executor route with that token in `X-Rediacc-On-Behalf-Of`. The
 * Commander tree is replaced by one command that makes the licence call.
 */

import { WK_ACCOUNT_EGRESS_HOST } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const GUID = '11111111-1111-4111-8111-111111111111';

vi.mock('../../../cli.js', async () => {
  const { retireRepoLicense } = await import('../../account/license-retire.js');
  return {
    createCli: () => {
      const program = new Command('rdc');
      program.exitOverride();
      program.command('retire-probe').action(async () => {
        await retireRepoLicense(GUID);
      });
      return program;
    },
  };
});
vi.mock('../../account/subscription-auth.js', async (importOriginal) => {
  const wk = await import('@rediacc/shared/config/well-known.generated');
  return {
    ...(await importOriginal<typeof import('../../account/subscription-auth.js')>()),
    getSubscriptionTokenState: () => ({
      kind: 'ready',
      serverUrl: `http://${wk.WK_ACCOUNT_EGRESS_HOST}`,
      token: { token: 'PLACEHOLDER' },
    }),
  };
});

import type { AgentGrantHandle } from '../agent-grant-session.js';
import { dispatcher } from '../mcp-call-dispatch.js';

const fetchMock = vi.fn();

function run(tokenId: string | undefined) {
  const handle = {
    grantId: 'g',
    principal: { userId: 'u', orgId: 'o', userEmail: 'e@x', ...(tokenId ? { tokenId } : {}) },
    config: {},
  } as unknown as AgentGrantHandle;
  const call = {
    deps: { executor: {}, auth: {} },
    busy: { track: <T>(fn: () => Promise<T>) => fn() },
    handle,
    requestId: 'r1',
    windowMs: 5000,
  };
  const prepared = {
    entry: { pathKey: 'retire-probe', machineOption: null, machinePositional: null },
    argv: ['retire-probe'],
  };
  return dispatcher(
    call as never,
    { params: {}, positionals: {} } as never
  )({
    prepared,
    background: false,
    onEvent: () => undefined,
  } as never);
}

beforeEach(() => {
  fetchMock
    .mockReset()
    .mockResolvedValue(
      new Response(JSON.stringify({ retired: true, repositoryGuid: GUID }), { status: 200 })
    );
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe('hosted MCP call in container mode', () => {
  it('carries the grant principal into the licence call', async () => {
    const outcome = await run('tok-mcp');
    expect(outcome.result.success).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `http://${WK_ACCOUNT_EGRESS_HOST}/account/api/v1/proxy/account/licenses/repos/${GUID}/retire`
    );
    expect(init.method).toBe('POST');
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer PLACEHOLDER');
    expect(headers['X-Rediacc-On-Behalf-Of']).toBe('tok-mcp');
    expect(init.body).toBeUndefined();
  });

  it('control: a principal with no token id fails the call named and sends nothing', async () => {
    const outcome = await run(undefined);
    expect(outcome.result.success).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

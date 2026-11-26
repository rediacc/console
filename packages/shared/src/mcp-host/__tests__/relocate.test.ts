/**
 * `EXECUTOR_RELOCATED` on the hosted Worker (item 413abaf3 of PLAN-rmcp-remote-worker.md): an executor that retired after its org moved answers `EXECUTOR_RELOCATED`; the Worker resolves the grant again past the cache and forwards once to the new placement.
 */
import { describe, expect, it, vi } from 'vitest';
import { ATTACH_WINDOW_MS, type CallDeps, callTool, type GrantCaller } from '../call.js';
import type { McpCallAnswer, McpCallRouting } from '../executor.js';
import { activeGrant } from './helpers/grant.js';

const GRANT_ID = 'eu_grant_reloc';
const OK: McpCallAnswer = {
  ok: true,
  answer: { result: { content: [{ type: 'text', text: 'ran' }], isError: false } },
};
const RELOCATED: McpCallAnswer = { ok: false, code: 'EXECUTOR_RELOCATED', status: 503 };

function setup(
  answerFor: (routing: McpCallRouting) => McpCallAnswer,
  refreshed: () => ReturnType<typeof activeGrant> | null | Promise<never>
) {
  const routings: McpCallRouting[] = [];
  const refreshes: number[] = [];
  const deps: CallDeps = {
    executor: {
      call: (routing) => {
        routings.push(routing);
        return Promise.resolve(answerFor(routing));
      },
    },
    reauthUrl: () => 'https://account.test/reauth',
    refreshGrant: () => {
      refreshes.push(1);
      return Promise.resolve(refreshed());
    },
  };
  const caller: GrantCaller = { grant: activeGrant(GRANT_ID, { placement: 1 }), secret: 's' };
  return { deps, caller, routings, refreshes };
}

describe('EXECUTOR_RELOCATED', () => {
  it('resolves the grant again and forwards once to the new placement', async () => {
    const { deps, caller, routings, refreshes } = setup(
      (routing) => (routing.placement === 1 ? RELOCATED : OK),
      () => activeGrant(GRANT_ID, { placement: 2 })
    );
    const result = await callTool(deps, caller, 'repo_list', {});
    expect(result.isError).toBe(false);
    expect(refreshes).toHaveLength(1);
    expect(routings.map((r) => r.placement)).toEqual([1, 2]);
  });

  it('gives up with SERVER_ERROR and the code when the new placement relocates too', async () => {
    const { deps, caller, routings } = setup(
      () => RELOCATED,
      () => activeGrant(GRANT_ID, { placement: 2 })
    );
    const result = await callTool(deps, caller, 'repo_list', {});
    expect(routings).toHaveLength(2);
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({
      code: 'SERVER_ERROR',
      executorCode: 'EXECUTOR_RELOCATED',
    });
  });

  it('does not forward again when the account still names the same placement', async () => {
    const { deps, caller, routings } = setup(
      () => RELOCATED,
      () => activeGrant(GRANT_ID, { placement: 1 })
    );
    const result = await callTool(deps, caller, 'repo_list', {});
    expect(routings).toHaveLength(1);
    expect(result.structuredContent).toMatchObject({ executorCode: 'EXECUTOR_RELOCATED' });
  });

  it('answers the code, with no retry, when the grant ended meanwhile or the lookup fails', async () => {
    const ended = setup(
      () => RELOCATED,
      () => activeGrant(GRANT_ID, { placement: 2, state: 'revoked' })
    );
    expect(
      (await callTool(ended.deps, ended.caller, 'repo_list', {})).structuredContent
    ).toMatchObject({
      executorCode: 'EXECUTOR_RELOCATED',
    });
    expect(ended.routings).toHaveLength(1);

    const failing = setup(
      () => RELOCATED,
      () => Promise.reject(new Error('account unreachable'))
    );
    expect(
      (await callTool(failing.deps, failing.caller, 'repo_list', {})).structuredContent
    ).toMatchObject({
      executorCode: 'EXECUTOR_RELOCATED',
    });
    expect(failing.routings).toHaveLength(1);
  });

  it('does not refresh for any other refusal, or without a refresh hook', async () => {
    const capacity = setup(
      () => ({ ok: false, code: 'EXECUTOR_CAPACITY', status: 503 }),
      () => activeGrant(GRANT_ID, { placement: 2 })
    );
    await callTool(capacity.deps, capacity.caller, 'repo_list', {});
    expect(capacity.refreshes).toHaveLength(0);

    const bare = setup(
      () => RELOCATED,
      () => activeGrant(GRANT_ID, { placement: 2 })
    );
    const result = await callTool(
      { ...bare.deps, refreshGrant: undefined },
      bare.caller,
      'repo_list',
      {}
    );
    expect(bare.routings).toHaveLength(1);
    expect(result.structuredContent).toMatchObject({ executorCode: 'EXECUTOR_RELOCATED' });
  });

  it('stops waiting on a lookup that outlasts the window and answers the relocation code', async () => {
    vi.useFakeTimers();
    try {
      const slow = setup(
        () => RELOCATED,
        () => new Promise<never>(() => undefined)
      );
      const pending = callTool(slow.deps, slow.caller, 'repo_list', {});
      await vi.advanceTimersByTimeAsync(ATTACH_WINDOW_MS);
      const result = await pending;
      expect(slow.routings).toHaveLength(1);
      expect(result.structuredContent).toMatchObject({ executorCode: 'EXECUTOR_RELOCATED' });
    } finally {
      vi.useRealTimers();
    }
  });
});

/**
 * Confirmation on the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md RW-T5, Design 6): the executor's `NEEDS_CONFIRMATION` becomes an `input_required` result with a sealed `requestState` for a client that declared elicitation, and the `confirm` argument path for one that did not. A state that is tampered with, expired, replayed, bound to another user or grant, or minted for other arguments is refused, and nothing is forwarded.
 */
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { isInputRequiredResult } from '@modelcontextprotocol/server';
import { CLIENT_CAPABILITIES_META_KEY, type Server } from '@modelcontextprotocol/server';
import { describe, expect, it } from 'vitest';
import { WK_ACCOUNT_DEFAULT_ORIGIN, WK_MCP_EU_HOST } from '../../config/well-known.generated.js';
import { type CallDeps, type CallInput, callToolStep, type GrantCaller } from '../call.js';
import { CONFIRM_TTL_MS, createConfirmation, hashArgs } from '../confirm.js';
import type { McpCallAnswer, McpCallForward } from '../executor.js';
import { MemoryRateLimiter } from '../rate.js';
import { createMcpTransport, declaresFormElicitation } from '../transport.js';
import { activeGrant, bearerFor, resolverFor } from './helpers/grant.js';

const TOOL = 'repo_delete';
const ARGS = { repo: 'shop', machine: 'm1' };
const NEEDS: McpCallAnswer = {
  ok: true,
  answer: {
    result: {
      content: [{ type: 'text', text: 'repo_delete would change a grand repo.' }],
      structuredContent: {
        code: 'NEEDS_CONFIRMATION',
        message: 'repo_delete would change a grand repo.',
        decisionCode: 'CONFIRMATION_REQUIRED',
        next: { confirm: { argument: 'confirm', value: 'shop' } },
      },
      isError: true,
    },
  },
};
const DONE: McpCallAnswer = {
  ok: true,
  answer: { result: { content: [{ type: 'text', text: 'deleted' }], isError: false } },
};

function setup(options: { withConfirm?: boolean } = {}) {
  let now = 10_000_000;
  const forwards: McpCallForward[] = [];
  const rate = new MemoryRateLimiter(() => now);
  const deps: CallDeps = {
    executor: {
      call: (_routing, forward) => {
        forwards.push(forward);
        return Promise.resolve(forward.args.confirm === undefined ? NEEDS : DONE);
      },
    },
    reauthUrl: () => 'https://account.test/reauth',
    rate,
    confirm:
      options.withConfirm === false
        ? undefined
        : createConfirmation({ key: 'worker-secret', now: () => now }),
  };
  const caller = (userId = 'user-a', grantId = 'eu_grant_conf'): GrantCaller => ({
    grant: activeGrant(grantId, { userId }),
    secret: 's',
  });
  return {
    deps,
    forwards,
    caller,
    advance: (ms: number) => {
      now += ms;
    },
  };
}

const ASKS: CallInput = { elicitation: true };
const YES = { confirm: { action: 'accept', content: { confirm: true } } };

/** The first call: returns the sealed state the client would echo. */
async function firstRound(s: ReturnType<typeof setup>, args = ARGS) {
  const result = await callToolStep(s.deps, s.caller(), TOOL, args, ASKS);
  if (!isInputRequiredResult(result)) throw new Error('expected input_required');
  const state = result.requestState;
  if (!state) throw new Error('no requestState');
  return { result, state };
}

const retry = (state: string, responses: Record<string, unknown> = YES): CallInput => ({
  elicitation: true,
  requestState: state,
  inputResponses: responses,
});

describe('confirmation by elicitation', () => {
  it('asks the client with a sealed state, and forwards the retry with confirm added', async () => {
    const s = setup();
    const { result, state } = await firstRound(s);
    expect(result.inputRequests?.confirm).toMatchObject({ method: 'elicitation/create' });
    expect(JSON.stringify(result)).toContain('repo_delete would change a grand repo.');
    expect(state).not.toContain('shop');
    expect(s.forwards).toHaveLength(1);

    const done = await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry(state));
    expect(isInputRequiredResult(done)).toBe(false);
    expect(done).toMatchObject({ isError: false });
    expect(s.forwards).toHaveLength(2);
    expect(s.forwards[1].args).toEqual({ ...ARGS, confirm: 'shop' });
  });

  it('ignores a confirm argument the eliciting client sends itself and asks the user', async () => {
    const s = setup();
    const result = await callToolStep(
      s.deps,
      s.caller(),
      TOOL,
      { ...ARGS, confirm: 'shop' },
      ASKS
    );
    expect(isInputRequiredResult(result)).toBe(true);
    expect(s.forwards).toHaveLength(1);
    expect(s.forwards[0].args).toEqual(ARGS);
  });

  it('forwards the sealed value, not the client confirm, once the user accepts', async () => {
    const s = setup();
    const { state } = await firstRound(s);
    const done = await callToolStep(
      s.deps,
      s.caller(),
      TOOL,
      { ...ARGS, confirm: 'other' },
      retry(state)
    );
    expect(done).toMatchObject({ isError: false });
    expect(s.forwards[1].args).toEqual({ ...ARGS, confirm: 'shop' });
  });

  it('keeps the confirm argument for a client that cannot be asked', async () => {
    const s = setup();
    const done = await callToolStep(
      s.deps,
      s.caller(),
      TOOL,
      { ...ARGS, confirm: 'shop' },
      { elicitation: false }
    );
    expect(done).toMatchObject({ isError: false });
    expect(s.forwards[0].args).toEqual({ ...ARGS, confirm: 'shop' });
  });

  it('refuses a tampered state and forwards nothing', async () => {
    const s = setup();
    const { state } = await firstRound(s);
    const flipped = `${state.slice(0, -2)}${state.endsWith('AA') ? 'BB' : 'AA'}`;
    for (const bad of [flipped, `x${state}`, 'not-a-state', '']) {
      const refused = await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry(bad));
      expect(refused).toMatchObject({
        isError: true,
        structuredContent: { code: 'INVALID_REQUEST' },
      });
    }
    expect(s.forwards).toHaveLength(1);
  });

  it('refuses an expired state', async () => {
    const s = setup();
    const { state } = await firstRound(s);
    s.advance(CONFIRM_TTL_MS + 1);
    const refused = await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry(state));
    expect(refused).toMatchObject({
      isError: true,
      structuredContent: { code: 'INVALID_REQUEST' },
    });
    expect(s.forwards).toHaveLength(1);
  });

  it('accepts a state once: the replay is refused', async () => {
    const s = setup();
    const { state } = await firstRound(s);
    expect(await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry(state))).toMatchObject({
      isError: false,
    });
    const replay = await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry(state));
    expect(replay).toMatchObject({ isError: true, structuredContent: { code: 'INVALID_REQUEST' } });
    expect(s.forwards).toHaveLength(2);
  });

  it('refuses a state presented under another user or another grant', async () => {
    const s = setup();
    const { state } = await firstRound(s);
    const otherUser = await callToolStep(s.deps, s.caller('user-b'), TOOL, ARGS, retry(state));
    expect(otherUser).toMatchObject({
      isError: true,
      structuredContent: { code: 'INVALID_REQUEST' },
    });
    const otherGrant = await callToolStep(
      s.deps,
      s.caller('user-a', 'eu_grant_other'),
      TOOL,
      ARGS,
      retry(state)
    );
    expect(otherGrant).toMatchObject({
      isError: true,
      structuredContent: { code: 'INVALID_REQUEST' },
    });
    expect(s.forwards).toHaveLength(1);
    // The refusals did not burn it: the owner can still use it.
    expect(await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry(state))).toMatchObject({
      isError: false,
    });
  });

  it('refuses a state for another tool or for changed arguments', async () => {
    const s = setup();
    const { state } = await firstRound(s);
    const changed = await callToolStep(
      s.deps,
      s.caller(),
      TOOL,
      { ...ARGS, repo: 'other' },
      retry(state)
    );
    expect(changed).toMatchObject({
      isError: true,
      structuredContent: { code: 'INVALID_REQUEST' },
    });
    const otherTool = await callToolStep(s.deps, s.caller(), 'repo_down', ARGS, retry(state));
    expect(otherTool).toMatchObject({
      isError: true,
      structuredContent: { code: 'INVALID_REQUEST' },
    });
    expect(s.forwards).toHaveLength(1);
  });

  it('forwards nothing when the user declines or the response is missing', async () => {
    const s = setup();
    const { state } = await firstRound(s);
    const declined = await callToolStep(
      s.deps,
      s.caller(),
      TOOL,
      ARGS,
      retry(state, { confirm: { action: 'decline' } })
    );
    expect(declined).toMatchObject({ isError: true, structuredContent: { code: 'POLICY_DENIED' } });
    // A decline spends the state; the next case needs its own.
    const second = await firstRound(s);
    const unchecked = await callToolStep(
      s.deps,
      s.caller(),
      TOOL,
      ARGS,
      retry(second.state, { confirm: { action: 'accept', content: { confirm: false } } })
    );
    expect(unchecked).toMatchObject({
      isError: true,
      structuredContent: { code: 'POLICY_DENIED' },
    });
    expect(s.forwards).toHaveLength(2);
  });

  it('does not burn the state when the retry is refused for the rate budget', async () => {
    const s = setup();
    const { state } = await firstRound(s);
    // Five calls in flight: the retry cannot take a slot.
    const limiter = s.deps.rate as MemoryRateLimiter;
    const held = [];
    for (let i = 0; i < 5; i += 1) held.push(await limiter.acquire('eu_grant_conf'));
    const busy = await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry(state));
    expect(busy).toMatchObject({ structuredContent: { code: 'REDIACC_RATE_LIMITED' } });
    for (const slot of held) if (slot.ok) await slot.release();
    expect(await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry(state))).toMatchObject({
      isError: false,
    });
  });
});

describe('confirmation by argument', () => {
  it('names the confirm argument and its value for a client that cannot be asked', async () => {
    const s = setup();
    const result = await callToolStep(s.deps, s.caller(), TOOL, ARGS, { elicitation: false });
    expect(isInputRequiredResult(result)).toBe(false);
    if (isInputRequiredResult(result)) return;
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({
      code: 'NEEDS_CONFIRMATION',
      confirmArgument: 'confirm',
    });
    const text = JSON.stringify(result.content);
    expect(text).toContain('confirm set to \\"shop\\"');
  });

  it('serves the retry that carries confirm, through the executor as an ordinary call', async () => {
    const s = setup();
    const done = await callToolStep(
      s.deps,
      s.caller(),
      TOOL,
      { ...ARGS, confirm: 'shop' },
      { elicitation: false }
    );
    expect(done).toMatchObject({ isError: false });
    expect(s.forwards[0].args).toEqual({ ...ARGS, confirm: 'shop' });
  });

  it('serves a client that declared elicitation the same way when the Worker has no key', async () => {
    const s = setup({ withConfirm: false });
    const result = await callToolStep(s.deps, s.caller(), TOOL, ARGS, ASKS);
    expect(isInputRequiredResult(result)).toBe(false);
    expect(result).toMatchObject({
      isError: true,
      structuredContent: { code: 'NEEDS_CONFIRMATION' },
    });
  });

  it('refuses an echoed state when the Worker has no key to open it', async () => {
    const s = setup({ withConfirm: false });
    const refused = await callToolStep(s.deps, s.caller(), TOOL, ARGS, retry('anything'));
    expect(refused).toMatchObject({
      isError: true,
      structuredContent: { code: 'INVALID_REQUEST' },
    });
    expect(s.forwards).toHaveLength(0);
  });
});

describe('hashArgs', () => {
  it('ignores key order and the confirm argument, and sees every other change', async () => {
    const base = await hashArgs({ a: 1, b: { c: [1, 2], d: 'x' } });
    expect(await hashArgs({ b: { d: 'x', c: [1, 2] }, a: 1 })).toBe(base);
    expect(await hashArgs({ a: 1, b: { c: [1, 2], d: 'x' }, confirm: true })).toBe(base);
    expect(await hashArgs({ a: 2, b: { c: [1, 2], d: 'x' } })).not.toBe(base);
    expect(await hashArgs({ a: 1, b: { c: [2, 1], d: 'x' } })).not.toBe(base);
  });
});

describe('through the SDK client and the Worker transport', () => {
  async function connectClient(
    elicits: boolean,
    answer: 'accept' | 'decline',
    era: '2026-07-28' | 'legacy' = '2026-07-28'
  ) {
    const s = setup();
    const grantId = 'eu_grant_sdk';
    const worker = createMcpTransport({
      host: WK_MCP_EU_HOST,
      serverVersion: '0.0.0-test',
      accountUrl: WK_ACCOUNT_DEFAULT_ORIGIN,
      resolveGrant: resolverFor([activeGrant(grantId, { userId: 'user-sdk' })]),
      executor: s.deps.executor,
      rate: s.deps.rate,
      confirm: s.deps.confirm,
    });
    const asked: unknown[] = [];
    const client = new Client(
      { name: 'rw-t5', version: '0.0.0' },
      {
        versionNegotiation: era === 'legacy' ? { mode: 'legacy' } : { mode: { pin: era } },
        ...(elicits ? { capabilities: { elicitation: { form: {} } } } : {}),
      }
    );
    if (elicits) {
      client.setRequestHandler('elicitation/create', (request) => {
        asked.push(request.params);
        return Promise.resolve(
          answer === 'accept'
            ? { action: 'accept' as const, content: { confirm: true } }
            : { action: 'decline' as const }
        );
      });
    }
    await client.connect(
      new StreamableHTTPClientTransport(new URL(`https://${WK_MCP_EU_HOST}/g/${grantId}`), {
        fetch: (input, init) => {
          const request = new Request(input, init);
          request.headers.set('authorization', `Bearer ${bearerFor(grantId)}`);
          return worker.fetch(request);
        },
      })
    );
    return { client, asked, forwards: s.forwards };
  }

  it('a client that declared elicitation is asked once, and its yes reaches the executor as confirm', async () => {
    const { client, asked, forwards } = await connectClient(true, 'accept');
    const result = await client.callTool({ name: TOOL, arguments: ARGS });
    await client.close();
    expect(asked).toHaveLength(1);
    expect(result.isError).toBe(false);
    expect(forwards.map((f) => f.args)).toEqual([ARGS, { ...ARGS, confirm: 'shop' }]);
  });

  it('a 2025-era client is not asked, since the stateless legacy leg keeps no initialize-time capabilities', async () => {
    const { client, asked, forwards } = await connectClient(true, 'accept', 'legacy');
    const result = await client.callTool({ name: TOOL, arguments: ARGS });
    await client.close();
    expect(asked).toHaveLength(0);
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({ confirmArgument: 'confirm' });
    expect(forwards).toHaveLength(1);
  });

  it('a 2025-era client without elicitation gets the confirm-argument refusal', async () => {
    const { client, forwards } = await connectClient(false, 'accept', 'legacy');
    const result = await client.callTool({ name: TOOL, arguments: ARGS });
    await client.close();
    expect(result.isError).toBe(true);
    expect(forwards).toHaveLength(1);
  });

  it('a decline stops the call before the second forward', async () => {
    const { client, forwards } = await connectClient(true, 'decline');
    const result = await client.callTool({ name: TOOL, arguments: ARGS });
    await client.close();
    expect(result.isError).toBe(true);
    expect(forwards).toHaveLength(1);
  });

  it('a client without elicitation gets the confirm-argument refusal', async () => {
    const { client, forwards } = await connectClient(false, 'accept');
    const result = await client.callTool({ name: TOOL, arguments: ARGS });
    await client.close();
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({
      code: 'NEEDS_CONFIRMATION',
      confirmArgument: 'confirm',
    });
    expect(forwards).toHaveLength(1);
  });
});

describe('declaresFormElicitation reads both client generations', () => {
  const serverWith = (elicitation?: object) =>
    ({
      getClientCapabilities: () => (elicitation ? { elicitation } : undefined),
    }) as unknown as Server;
  const requestWith = (elicitation?: object) => ({
    mcpReq: {
      envelope: elicitation ? { [CLIENT_CAPABILITIES_META_KEY]: { elicitation } } : undefined,
    },
  });

  it('reads the per-request envelope of a 2026-07-28 client when initialize left nothing', () => {
    expect(declaresFormElicitation(serverWith(), requestWith({ form: {} }))).toBe(true);
  });

  it('reads the initialize-time capabilities of a 2025-era client', () => {
    expect(declaresFormElicitation(serverWith({}), requestWith())).toBe(true);
  });

  it('prefers the envelope over the initialize-time capabilities', () => {
    expect(declaresFormElicitation(serverWith({ form: {} }), requestWith({ url: {} }))).toBe(false);
  });

  it('is false for a client that declared nothing', () => {
    expect(declaresFormElicitation(serverWith(), requestWith())).toBe(false);
  });
});

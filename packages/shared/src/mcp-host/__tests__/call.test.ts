/**
 * `tools/call` on the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md RW-T2, Design 1 and 7): the forward over the `EXECUTOR` binding, the 50-second window, the job handle, the paging pass-through, and the scope check in front of it.
 *
 * The forwarding cases drive the real SDK v2 client through the Worker's fetch face; the timing cases call `callTool` directly under fake timers, since the client's own request timers would race the fake clock.
 */

import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WK_ACCOUNT_DEFAULT_ORIGIN, WK_MCP_EU_HOST } from '../../config/well-known.generated.js';
import {
  ATTACH_WINDOW_MS,
  type CallDeps,
  callTool,
  EXECUTOR_ATTACH_MS,
  type GrantCaller,
  MAX_RESULT_SIZE_CHARS,
} from '../call.js';
import type {
  ExecutorBinding,
  McpCallAnswer,
  McpCallForward,
  McpCallRouting,
} from '../executor.js';
import type { GrantScope } from '../scope.js';
import { createMcpTransport } from '../transport.js';
import { activeGrant, bearerFor, resolverFor, secretTextOf } from './helpers/grant.js';

const HOST = WK_MCP_EU_HOST;
const GRANT_ID = 'eu_grant_t2';
/** base64url(S) of the test grant: anywhere but the forward body is a leak. */
const SECRET = secretTextOf(GRANT_ID);
const FULL: GrantScope = { readOnly: false, tools: null, machines: null, repos: null };

const grantWith = (scope: GrantScope) =>
  activeGrant(GRANT_ID, { scope, orgId: 'org-t2', placement: 3, tier: 'high' });

function caller(scope: GrantScope = FULL): GrantCaller {
  return { grant: grantWith(scope), secret: SECRET };
}

const reauthUrl = (grantId: string) =>
  `${WK_ACCOUNT_DEFAULT_ORIGIN}/account/mcp/authorize?grant=${grantId}`;

interface Recorded {
  routing: McpCallRouting;
  forward: McpCallForward;
}

/** An executor binding that records each call and answers with `answer`. */
function fakeExecutor(answer: (forward: McpCallForward) => Promise<McpCallAnswer>) {
  const calls: Recorded[] = [];
  const executor: ExecutorBinding = {
    call: (routing, forward) => {
      calls.push({ routing, forward });
      return answer(forward);
    },
  };
  return { executor, calls };
}

const resultAnswer = (result: unknown): Promise<McpCallAnswer> =>
  Promise.resolve({ ok: true, answer: { result } });

/** A client whose HTTP goes straight into the Worker, recording every response body it reads. */
async function connect(executor: ExecutorBinding, scope: GrantScope = FULL, bodies: string[] = []) {
  const worker = createMcpTransport({
    host: HOST,
    serverVersion: '0.0.0-test',
    accountUrl: WK_ACCOUNT_DEFAULT_ORIGIN,
    resolveGrant: resolverFor([grantWith(scope)]),
    executor,
    newRequestId: () => 'req-fixed',
  });
  const fetchViaWorker = async (input: string | URL | Request, init?: RequestInit) => {
    const request = new Request(input, init);
    request.headers.set('authorization', `Bearer ${bearerFor(GRANT_ID)}`);
    const response = await worker.fetch(request);
    bodies.push(await response.clone().text());
    return response;
  };
  const client = new Client(
    { name: 'rw-t2', version: '0.0.0' },
    { versionNegotiation: { mode: { pin: '2026-07-28' } } }
  );
  await client.connect(
    new StreamableHTTPClientTransport(new URL(`https://${HOST}/g/${GRANT_ID}`), {
      fetch: fetchViaWorker,
    })
  );
  return client;
}

describe('tools/call forwarding', () => {
  it('S travels only in the forward body, never in the routing or back to the client', async () => {
    const { executor, calls } = fakeExecutor(() =>
      resultAnswer({ content: [{ type: 'text', text: '{"success":true}' }], isError: false })
    );
    const bodies: string[] = [];
    const client = await connect(executor, FULL, bodies);
    const result = await client.callTool({ name: 'repo_list', arguments: { machine: 'm1' } });
    await client.close();

    expect(result.isError).toBe(false);
    expect(calls).toHaveLength(1);
    expect(calls[0].forward).toEqual({
      grantId: GRANT_ID,
      secret: SECRET,
      tool: 'repo_list',
      args: { machine: 'm1' },
      requestId: 'req-fixed',
      attachMs: EXECUTOR_ATTACH_MS,
    });
    expect(calls[0].routing).toEqual({ orgId: 'org-t2', placement: 3, tier: 'high' });
    expect(JSON.stringify(calls[0].routing)).not.toContain(SECRET);
    expect(bodies.join('\n')).not.toContain(SECRET);
  });

  it("the registry's paging cursor survives the forward unchanged, and a pageable tool announces its result size", async () => {
    const page = {
      content: [
        { type: 'text', text: 'x'.repeat(1000) },
        { type: 'text', text: '{"paging":{"page":2,"pages":3,"totalChars":250000,"cursor":3}}' },
      ],
      isError: false,
    };
    const { executor, calls } = fakeExecutor(() => resultAnswer(page));
    const client = await connect(executor);
    const paged = await client.callTool({
      name: 'job_logs',
      arguments: { 'job-id': 'j1', page: 2 },
    });
    const plain = await client.callTool({ name: 'repo_list', arguments: {} });
    await client.close();

    expect(calls[0].forward.args).toEqual({ 'job-id': 'j1', page: 2 });
    expect(paged.content).toEqual(page.content);
    expect(paged._meta?.['anthropic/maxResultSizeChars']).toBe(MAX_RESULT_SIZE_CHARS);
    // Control: a tool with no page argument carries no size announcement.
    expect(plain._meta?.['anthropic/maxResultSizeChars']).toBeUndefined();
  });

  it('a tool outside the grant scope is refused before any forward', async () => {
    const { executor, calls } = fakeExecutor(() =>
      resultAnswer({ content: [{ type: 'text', text: 'ran' }], isError: false })
    );
    const client = await connect(executor, { ...FULL, tools: ['repo_list'] });
    const outside = await client.callTool({ name: 'repo_up', arguments: { ref: 'shop' } });
    // config_list is a local-surface tool: the hosted server does not serve it at all.
    const notProxy = await client.callTool({ name: 'config_list', arguments: {} });
    const inside = await client.callTool({ name: 'repo_list', arguments: {} });
    await client.close();

    expect(outside.isError).toBe(true);
    expect(outside.structuredContent).toMatchObject({ code: 'POLICY_DENIED' });
    expect(notProxy.structuredContent).toMatchObject({ code: 'INVALID_REQUEST' });
    // Control: the admitted tool is forwarded, and it is the only one.
    expect(inside.isError).toBe(false);
    expect(calls.map((c) => c.forward.tool)).toEqual(['repo_list']);
  });

  it('a read-only grant refuses a destructive tool', async () => {
    const { executor, calls } = fakeExecutor(() =>
      resultAnswer({ content: [{ type: 'text', text: 'ran' }], isError: false })
    );
    const result = await callTool(
      { executor, reauthUrl },
      caller({ ...FULL, readOnly: true }),
      'repo_delete',
      { ref: 'shop' }
    );
    expect(result.structuredContent).toMatchObject({ code: 'POLICY_DENIED' });
    expect(calls).toHaveLength(0);
  });
});

describe('the 50-second window', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  /** Settle `promise` under fake timers, advancing the clock by `ms` first. Returns the value and whether it settled before the advance ended. */
  async function settledAfter<T>(promise: Promise<T>, ms: number) {
    let settled = false;
    void promise.then(() => {
      settled = true;
    });
    await vi.advanceTimersByTimeAsync(ms);
    return { settled, value: settled ? await promise : undefined };
  }

  function delayed(ms: number, answer: McpCallAnswer): Promise<McpCallAnswer> {
    return new Promise((resolve) => setTimeout(() => resolve(answer), ms));
  }

  it('asks the container to answer inside the window', () => {
    expect(EXECUTOR_ATTACH_MS).toBeLessThan(ATTACH_WINDOW_MS);
    expect(ATTACH_WINDOW_MS).toBeLessThanOrEqual(50_000);
  });

  it('a long job returns its handle within the window', async () => {
    vi.useFakeTimers();
    const { executor, calls } = fakeExecutor(() =>
      delayed(EXECUTOR_ATTACH_MS, { ok: true, answer: { job: { jobId: 'job-42', machine: 'm1' } } })
    );
    const pending = callTool({ executor, reauthUrl }, caller(), 'repo_up', { ref: 'shop' });
    const { settled, value } = await settledAfter(pending, EXECUTOR_ATTACH_MS);
    expect(settled).toBe(true);
    expect(calls[0].forward.attachMs).toBe(EXECUTOR_ATTACH_MS);
    expect(value?.isError).toBe(false);
    expect(value?.structuredContent).toEqual({
      jobId: 'job-42',
      machine: 'm1',
      next: 'job_status',
    });
  });

  it('an executor that says nothing gets TIMEOUT at the window, naming job_list', async () => {
    vi.useFakeTimers();
    const { executor } = fakeExecutor(() => new Promise<McpCallAnswer>(() => undefined));
    const pending = callTool({ executor, reauthUrl }, caller(), 'repo_up', { ref: 'shop' });
    expect((await settledAfter(pending, ATTACH_WINDOW_MS - 1)).settled).toBe(false);
    const { settled, value } = await settledAfter(pending, 1);
    expect(settled).toBe(true);
    expect(value?.structuredContent).toMatchObject({ code: 'TIMEOUT', next: 'job_list' });
  });

  it('job_wait through the Worker returns within 50 s, with its own answer or a call-again', async () => {
    vi.useFakeTimers();
    const status = { content: [{ type: 'text', text: '{"state":"running"}' }], isError: false };
    const answering = fakeExecutor(() =>
      delayed(EXECUTOR_ATTACH_MS, { ok: true, answer: { result: status } })
    );
    const answered = await settledAfter(
      callTool({ executor: answering.executor, reauthUrl }, caller(), 'job_wait', {
        'job-id': 'j1',
      }),
      EXECUTOR_ATTACH_MS
    );
    expect(answered.settled).toBe(true);
    expect(answered.value?.content).toEqual(status.content);

    const silent = fakeExecutor(() => new Promise<McpCallAnswer>(() => undefined));
    const waited = await settledAfter(
      callTool({ executor: silent.executor, reauthUrl }, caller(), 'job_wait', { 'job-id': 'j1' }),
      50_000
    );
    expect(waited.settled).toBe(true);
    expect(waited.value?.structuredContent).toMatchObject({ code: 'TIMEOUT', next: 'job_wait' });
  });
});

describe('an ended grant with an unusable account origin', () => {
  it('answers its code without a link instead of throwing', async () => {
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const ended = { grant: activeGrant(GRANT_ID, { state: 'expired' }), secret: SECRET };
    const result = await callTool(
      {
        executor: undefined,
        reauthUrl: () => {
          throw new TypeError('Invalid URL');
        },
      },
      ended,
      'repo_list',
      {}
    );
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({ code: 'REDIACC_GRANT_EXPIRED' });
    expect(result.structuredContent).not.toHaveProperty('reauthUrl');
    expect(logged).toHaveBeenCalledTimes(1);
    expect(String(logged.mock.calls[0]?.[0])).toContain('account origin is misconfigured');
    logged.mockRestore();
  });
});

describe('executor refusals', () => {
  const deps = (answer: () => Promise<McpCallAnswer>): CallDeps => ({
    executor: { call: answer },
    reauthUrl,
  });

  it('maps a capacity refusal, a throw, a missing binding and a bad shape to SERVER_ERROR', async () => {
    const capacity = await callTool(
      deps(() => Promise.resolve({ ok: false, code: 'EXECUTOR_CAPACITY', status: 503 })),
      caller(),
      'repo_list',
      {}
    );
    expect(capacity.structuredContent).toMatchObject({
      code: 'SERVER_ERROR',
      executorCode: 'EXECUTOR_CAPACITY',
      retryAfterSeconds: 30,
    });
    const thrown = await callTool(
      deps(() => Promise.reject(new Error('binding down'))),
      caller(),
      'repo_list',
      {}
    );
    expect(thrown.structuredContent).toMatchObject({ code: 'SERVER_ERROR' });
    // A throw can follow delivery, so the text must not read as "never ran".
    expect(JSON.stringify(thrown.content)).toContain('may have run');
    const unbound = await callTool({ executor: undefined, reauthUrl }, caller(), 'repo_list', {});
    expect(unbound.structuredContent).toMatchObject({ code: 'SERVER_ERROR' });
    const shapeless = await callTool(
      deps(() => Promise.resolve({ ok: true, answer: { nothing: 1 } })),
      caller(),
      'repo_list',
      {}
    );
    expect(shapeless.structuredContent).toMatchObject({ code: 'SERVER_ERROR' });
  });
});

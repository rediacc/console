/**
 * The proxy side of a hosted MCP `tools/call` (agent/plans/PLAN-rmcp-remote-worker.md RW-T2, Design 1 and 7): the `McpExecutor` entrypoint pins the grant's org at the placement the MCP Worker resolved, and `OrgExecutor.mcpCall` posts the forward to the container's MCP call route as the request body.
 *
 * The container is the harness fake (src/__tests__/helpers/org-executor-harness.ts); the entrypoint test drives a stub ORG_EXECUTOR namespace.
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

import { type Env, McpExecutor } from '../index';
import { MCP_CALL_PATH, type McpCallAnswer, type McpCallForward } from '../org-executor';
import { executorName } from '../placement';
import { harness, ORG, T0 } from './helpers/org-executor-harness';

/** A recognisable stand-in for base64url(S): any URL, header or log line holding it is a leak. */
const SECRET = 'U2VjcmV0LW9mLXRoZS1hZ2VudC1ncmFudC0zMi1ieXRlcw';

function forward(overrides: Partial<McpCallForward> = {}): McpCallForward {
  return {
    grantId: 'eu_grant1',
    secret: SECRET,
    tool: 'job_logs',
    args: { 'job-id': 'j1', page: 2 },
    requestId: 'req-1',
    attachMs: 45_000,
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(T0);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('OrgExecutor.mcpCall', () => {
  it('posts the forward as the body of the MCP call route: S is in the body and in no URL or header', async () => {
    const h = harness();
    await h.ready;
    let seen:
      | { url: string; method: string; headers: [string, string][]; body: string }
      | undefined;
    const page = {
      result: {
        content: [
          { type: 'text', text: 'line 100001...' },
          { type: 'text', text: '{"paging":{"page":2,"pages":3,"totalChars":250000,"cursor":3}}' },
        ],
        isError: false,
      },
    };
    h.container.app = async (request) => {
      seen = {
        url: request.url,
        method: request.method,
        headers: [...request.headers.entries()],
        body: await request.text(),
      };
      return Response.json(page);
    };
    await h.executor.pin(ORG, 0, 'light');
    const answer = await h.executor.mcpCall(forward());

    expect(seen?.method).toBe('POST');
    expect(new URL(seen?.url ?? '').pathname).toBe(MCP_CALL_PATH);
    expect(seen?.url).not.toContain(SECRET);
    expect(JSON.stringify(seen?.headers)).not.toContain(SECRET);
    expect(JSON.parse(seen?.body ?? '{}')).toEqual(forward());
    // The container's answer, paging cursor included, comes back untouched.
    expect(answer).toEqual({ ok: true, answer: page });
    expect(JSON.stringify((console.warn as ReturnType<typeof vi.fn>).mock.calls)).not.toContain(
      SECRET
    );
  });

  it('answers the container refusal code, and EXECUTOR_START_FAILED when no container runs', async () => {
    const h = harness();
    await h.ready;
    expect(await h.executor.mcpCall(forward())).toEqual({
      ok: false,
      code: 'EXECUTOR_START_FAILED',
      status: 503,
    });
    h.container.app = () => Response.json({ code: 'EXECUTOR_SESSION_UNKNOWN' }, { status: 401 });
    await h.executor.pin(ORG, 0, 'light');
    expect(await h.executor.mcpCall(forward())).toEqual({
      ok: false,
      code: 'EXECUTOR_SESSION_UNKNOWN',
      status: 401,
    });
    h.container.app = () => new Response('not json', { status: 200 });
    expect(await h.executor.mcpCall(forward())).toEqual({
      ok: false,
      code: 'EXECUTOR_FAILED',
      status: 502,
    });
  });

  it('refuses every spelling of the MCP call route on the public forward, which never reaches the container', async () => {
    const h = harness();
    await h.ready;
    let reached = 0;
    h.container.app = () => {
      reached += 1;
      return new Response('reached');
    };
    await h.executor.pin(ORG, 0, 'light');
    for (const path of [MCP_CALL_PATH, '/v1/mcp/%63all', '//v1/mcp/call', '/v1//mcp/call/']) {
      const response = await h.executor.fetch(
        new Request(`https://proxy${path}`, { method: 'POST', body: JSON.stringify(forward()) })
      );
      expect(response.status, path).toBe(404);
    }
    expect(reached).toBe(0);
    // Control: an ordinary route still reaches the container.
    expect(await (await h.executor.fetch(new Request('https://proxy/v1/command'))).text()).toBe(
      'reached'
    );
  });
});

describe('the McpExecutor entrypoint', () => {
  interface Seen {
    names: string[];
    pins: [string, number, string][];
    calls: McpCallForward[];
  }

  function envWith(pin: { ok: boolean; code?: string }, seen: Seen, answer: McpCallAnswer): Env {
    return {
      ACCOUNT_URL: 'https://account.test',
      ORG_EXECUTOR: {
        idFromName: (name: string) => ({ name }),
        get: (id: { name: string }) => {
          seen.names.push(id.name);
          return {
            oomAt: () => Promise.resolve(undefined),
            oomHeavyAt: () => Promise.resolve(undefined),
            pin: (orgId: string, placement: number, size: string) => {
              seen.pins.push([orgId, placement, size]);
              return Promise.resolve(
                pin.ok
                  ? { ok: true, size, egressUnreachableRecent: false }
                  : { ok: false, code: pin.code, reason: 'test' }
              );
            },
            mcpCall: (f: McpCallForward) => {
              seen.calls.push(f);
              return Promise.resolve(answer);
            },
            fetch: () => Promise.reject(new Error('mcp calls never use fetch')),
          };
        },
      } as unknown as Env['ORG_EXECUTOR'],
    };
  }

  const entry = (env: Env) => new McpExecutor({} as ExecutionContext, env);

  it("pins the grant's org at the resolved placement and hands the forward to its OrgExecutor", async () => {
    const seen: Seen = { names: [], pins: [], calls: [] };
    const answer: McpCallAnswer = { ok: true, answer: { job: { jobId: 'j9', machine: 'm1' } } };
    const result = await entry(envWith({ ok: true }, seen, answer)).call(
      { orgId: 'org-7', placement: 2 },
      forward()
    );
    expect(result).toEqual(answer);
    expect(seen.names).toEqual([executorName('org-7', 2)]);
    expect(seen.pins).toEqual([['org-7', 2, 'light']]);
    expect(seen.calls).toEqual([forward()]);
  });

  it('answers a refused pin or bad routing with a code and never calls the container', async () => {
    const seen: Seen = { names: [], pins: [], calls: [] };
    const answer: McpCallAnswer = { ok: true, answer: {} };
    expect(
      await entry(envWith({ ok: false, code: 'EXECUTOR_CAPACITY' }, seen, answer)).call(
        { orgId: 'org-7', placement: 0 },
        forward()
      )
    ).toEqual({ ok: false, code: 'EXECUTOR_CAPACITY', status: 503 });
    expect(
      await entry(envWith({ ok: true }, seen, answer)).call(
        { orgId: 'org-7', placement: -1 },
        forward()
      )
    ).toEqual({ ok: false, code: 'EXECUTOR_START_FAILED', status: 503 });
    expect(
      await entry({ ACCOUNT_URL: 'https://account.test' }).call(
        { orgId: 'org-7', placement: 0 },
        forward()
      )
    ).toEqual({ ok: false, code: 'EXECUTOR_START_FAILED', status: 503 });
    expect(seen.calls).toEqual([]);
  });
});

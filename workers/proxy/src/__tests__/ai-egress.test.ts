/**
 * `AiEgress` (agent/plans/PLAN-console-ai-credits.md AC5, D1 and D5 to D7): the model allowlist, the reserve before any forward, the `max_tokens` clamp, forced usage reporting, the metadata, the abort and commit, and the `ai.internal` intercept registered beside `account.internal`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('cloudflare:workers', () => ({
  WorkerEntrypoint: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
}));

import { PRICE_TABLE_VERSION } from '../../../../packages/shared/src/ai-credits/index.js';
import {
  AI_COMPAT_PATH,
  AI_CONVERSATION_HEADER,
  AI_USER_HEADER,
  AiEgress,
  type CreditReserveAnswer,
  type CreditReserveRequest,
  type CreditTokenCounts,
  gatewayUrl,
  MAX_AI_BODY_BYTES,
} from '../ai-egress';
import { AI_EGRESS_HOST, registerEgress } from '../org-executor-support';
import { executorName } from '../placement';

const ORG = 'org-a';
const MODEL = 'workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast';
const ACCOUNT = 'acct1';
const GATEWAY = 'rediacc-eu';
const TOKEN = 'aig-secret';

const NAMES = { idFromName: (name: string) => ({ toString: () => `id:${name}` }) };

interface Calls {
  reserves: { orgId: string; request: CreditReserveRequest }[];
  commits: { orgId: string; reservationId: string; usage?: CreditTokenCounts }[];
  releases: { orgId: string; reservationId: string }[];
  upstream: { url: string; headers: Headers; body: Record<string, unknown> }[];
}

interface Options {
  reserve?: (request: CreditReserveRequest) => CreditReserveAnswer | Promise<CreditReserveAnswer>;
  upstream?: (request: Request) => Response | Promise<Response>;
  props?: Record<string, unknown> | undefined;
  env?: Record<string, unknown>;
}

function setup(options: Options = {}) {
  const calls: Calls = { reserves: [], commits: [], releases: [], upstream: [] };
  const pending: Promise<unknown>[] = [];
  const credits = {
    reserve: async (orgId: string, request: CreditReserveRequest) => {
      calls.reserves.push({ orgId, request });
      return (
        (await options.reserve?.(request)) ?? {
          ok: true as const,
          reservationId: request.reservationId,
          credits: 100,
          maxTokens: 512,
          priceVersion: PRICE_TABLE_VERSION,
        }
      );
    },
    commit: (orgId: string, reservationId: string, usage?: CreditTokenCounts) => {
      calls.commits.push({ orgId, reservationId, ...(usage ? { usage } : {}) });
      return Promise.resolve({ ok: true });
    },
    release: (orgId: string, reservationId: string) => {
      calls.releases.push({ orgId, reservationId });
      return Promise.resolve(true);
    },
  };
  vi.stubGlobal('fetch', async (input: string | Request, init?: RequestInit) => {
    const request = new Request(input, init);
    calls.upstream.push({
      url: request.url,
      headers: request.headers,
      body: JSON.parse(await request.clone().text()) as Record<string, unknown>,
    });
    return (
      (await options.upstream?.(request)) ??
      Response.json({
        choices: [],
        usage: { prompt_tokens: 12, completion_tokens: 34 },
      })
    );
  });
  const ctx = {
    props:
      'props' in options
        ? options.props
        : { orgId: ORG, placement: 0, containerId: `id:${executorName(ORG, 0)}` },
    waitUntil: (promise: Promise<unknown>) => {
      pending.push(promise);
    },
  };
  const env = {
    ORG_EXECUTOR: NAMES,
    CREDITS: credits,
    AI_GATEWAY_TOKEN: TOKEN,
    AI_GATEWAY_ID: GATEWAY,
    AI_GATEWAY_ACCOUNT_ID: ACCOUNT,
    ...options.env,
  };
  const egress = new AiEgress(ctx as never, env as never);
  const settle = async () => {
    await Promise.all(pending);
  };
  return { egress, calls, settle };
}

function chat(
  body: unknown,
  headers: Record<string, string | undefined> = {},
  path = AI_COMPAT_PATH
) {
  return new Request(`http://ai.internal${path}`, {
    method: 'POST',
    headers: {
      [AI_USER_HEADER]: 'user-1',
      [AI_CONVERSATION_HEADER]: 'conv-1',
      ...headers,
    },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

const valid = (extra: Record<string, unknown> = {}) => ({
  model: MODEL,
  messages: [{ role: 'user', content: 'hi' }],
  ...extra,
});

async function codeOf(response: Response): Promise<unknown> {
  return ((await response.json()) as { code?: unknown }).code;
}

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('AiEgress props and route', () => {
  it('refuses a call whose props are missing, and one whose container is not this org instance', async () => {
    const none = setup({ props: undefined });
    const missing = await none.egress.fetch(chat(valid()));
    expect(missing.status).toBe(403);
    expect(await codeOf(missing)).toBe('org-param-missing');

    const other = setup({ props: { orgId: ORG, placement: 0, containerId: 'id:someone-else' } });
    const mismatch = await other.egress.fetch(chat(valid()));
    expect(mismatch.status).toBe(403);
    expect(await codeOf(mismatch)).toBe('container-org-mismatch');
    expect(other.calls.reserves).toHaveLength(0);
  });

  it.each([
    ['GET', AI_COMPAT_PATH],
    ['POST', '/compat/embeddings'],
    ['POST', `${AI_COMPAT_PATH}/extra`],
    ['POST', `${AI_COMPAT_PATH}?x=1`],
  ])('admits only POST %s: %s is refused before any reservation', async (method, path) => {
    const { egress, calls } = setup();
    const response = await egress.fetch(
      new Request(`http://ai.internal${path}`, {
        method,
        ...(method === 'POST' ? { body: '{}' } : {}),
      })
    );
    expect(response.status).toBe(403);
    expect(await codeOf(response)).toBe('route-not-allowed');
    expect(calls.reserves).toHaveLength(0);
    expect(calls.upstream).toHaveLength(0);
  });

  it('answers 503 ai-unconfigured without the binding or any gateway setting', async () => {
    for (const missing of [
      'CREDITS',
      'AI_GATEWAY_TOKEN',
      'AI_GATEWAY_ID',
      'AI_GATEWAY_ACCOUNT_ID',
    ]) {
      const { egress, calls } = setup({ env: { [missing]: undefined } });
      const response = await egress.fetch(chat(valid()));
      expect(response.status, missing).toBe(503);
      expect(await codeOf(response), missing).toBe('ai-unconfigured');
      expect(calls.upstream).toHaveLength(0);
    }
  });
});

describe('AiEgress admission', () => {
  it('refuses a model absent from the price table before any reservation', async () => {
    const { egress, calls } = setup();
    const response = await egress.fetch(chat(valid({ model: 'openai/gpt-2' })));
    expect(response.status).toBe(403);
    expect(await codeOf(response)).toBe('model-not-allowed');
    expect(calls.reserves).toHaveLength(0);
    expect(calls.upstream).toHaveLength(0);
  });

  it.each([
    ['not JSON', '{nope'],
    ['an array', '[]'],
    ['no model', JSON.stringify({ messages: [] })],
    ['no messages', JSON.stringify({ model: MODEL })],
    ['max_tokens 0', JSON.stringify(valid({ max_tokens: 0 }))],
    ['max_tokens a string', JSON.stringify(valid({ max_tokens: '5' }))],
  ])('refuses a body that is %s as invalid-request', async (_name, body) => {
    const { egress, calls } = setup();
    const response = await egress.fetch(chat(body));
    expect(response.status).toBe(400);
    expect(await codeOf(response)).toBe('invalid-request');
    expect(calls.reserves).toHaveLength(0);
  });

  it('refuses a call without a valid user and conversation header', async () => {
    const { egress, calls } = setup();
    for (const headers of [
      { [AI_USER_HEADER]: '' },
      { [AI_CONVERSATION_HEADER]: 'bad id with spaces' },
    ]) {
      const response = await egress.fetch(chat(valid(), headers));
      expect(response.status).toBe(400);
    }
    expect(calls.reserves).toHaveLength(0);
  });

  it('refuses a body past the cap with 413 and reserves nothing', async () => {
    const { egress, calls } = setup();
    const big = valid({ pad: 'x'.repeat(MAX_AI_BODY_BYTES) });
    const response = await egress.fetch(chat(big));
    expect(response.status).toBe(413);
    expect(await codeOf(response)).toBe('body-too-large');
    expect(calls.reserves).toHaveLength(0);
  });
});

describe('AiEgress reserve', () => {
  it('reserves for the pinned org with the body size and the requested cap, never an org from the request', async () => {
    const { egress, calls } = setup();
    const body = valid({ max_tokens: 100, org_id: 'org-evil' });
    const request = chat(body, { 'x-org-id': 'org-evil' });
    await egress.fetch(request);
    const [reserve] = calls.reserves;
    expect(reserve?.orgId).toBe(ORG);
    expect(reserve?.request).toMatchObject({
      userId: 'user-1',
      conversationId: 'conv-1',
      model: MODEL,
      maxTokens: 100,
      bodyBytes: new TextEncoder().encode(JSON.stringify(body)).byteLength,
    });
  });

  it.each([
    ['PLAN_NOT_ENTITLED', 403],
    ['ORG_BLOCKED', 403],
    ['GLOBAL_PAUSED', 403],
    ['INSUFFICIENT_CREDITS', 402],
    ['DAILY_CAP', 429],
    ['TOO_MANY_STREAMS', 429],
    ['CONVERSATION_TOKEN_CAP', 429],
    ['LOOP_DEPTH', 429],
  ] as const)(
    'answers the ledger refusal %s with %i and never reaches the gateway',
    async (code, status) => {
      const { egress, calls } = setup({ reserve: () => ({ ok: false, code }) });
      const response = await egress.fetch(chat(valid()));
      expect(response.status).toBe(status);
      expect(await codeOf(response)).toBe(code);
      expect(calls.upstream).toHaveLength(0);
      expect(calls.commits).toHaveLength(0);
    }
  );

  it('fails closed with 503 when the ledger cannot answer', async () => {
    const { egress, calls } = setup({
      reserve: () => Promise.reject(new Error('ledger down')),
    });
    const response = await egress.fetch(chat(valid()));
    expect(response.status).toBe(503);
    expect(await codeOf(response)).toBe('ledger-unavailable');
    expect(calls.upstream).toHaveLength(0);
  });
});

describe('AiEgress forward', () => {
  it('sends the clamped max_tokens the ledger granted, whatever the request asked for', async () => {
    const { egress, calls } = setup({
      reserve: (request) => ({
        ok: true,
        reservationId: request.reservationId,
        credits: 5,
        maxTokens: 8192,
        priceVersion: PRICE_TABLE_VERSION,
      }),
    });
    await egress.fetch(chat(valid({ max_tokens: 1_000_000 })));
    expect(calls.upstream[0]?.body.max_tokens).toBe(8192);
  });

  it('adds the clamp when the request names none, and clamps max_completion_tokens in place', async () => {
    const one = setup();
    await one.egress.fetch(chat(valid()));
    expect(one.calls.upstream[0]?.body.max_tokens).toBe(512);
    expect(one.calls.upstream[0]?.body).not.toHaveProperty('max_completion_tokens');

    const two = setup();
    await two.egress.fetch(chat(valid({ max_completion_tokens: 999_999 })));
    expect(two.calls.upstream[0]?.body.max_completion_tokens).toBe(512);
    expect(two.calls.upstream[0]?.body).not.toHaveProperty('max_tokens');
  });

  it('forces usage reporting on for a stream, keeping other stream options', async () => {
    const { egress, calls } = setup();
    await egress.fetch(
      chat(valid({ stream: true, stream_options: { include_usage: false, other: 1 } }))
    );
    expect(calls.upstream[0]?.body.stream_options).toEqual({ include_usage: true, other: 1 });
  });

  it('sends the gateway URL, the secret and the five metadata entries, and none of the container headers', async () => {
    const { egress, calls } = setup();
    await egress.fetch(
      chat(valid(), { authorization: 'Bearer container-secret', cookie: 'a=b', 'x-extra': '1' })
    );
    const sent = calls.upstream[0];
    expect(sent?.url).toBe(gatewayUrl(ACCOUNT, GATEWAY));
    expect(sent?.url).toBe(
      `https://gateway.ai.cloudflare.com/v1/${ACCOUNT}/${GATEWAY}/compat/chat/completions`
    );
    expect(sent?.headers.get('cf-aig-authorization')).toBe(`Bearer ${TOKEN}`);
    expect(sent?.headers.get('authorization')).toBeNull();
    expect(sent?.headers.get('cookie')).toBeNull();
    expect(sent?.headers.get('x-extra')).toBeNull();
    const metadata = JSON.parse(sent?.headers.get('cf-aig-metadata') ?? '{}') as Record<
      string,
      unknown
    >;
    expect(Object.keys(metadata).sort((a, b) => a.localeCompare(b))).toEqual([
      'conversation_id',
      'org_id',
      'price_version',
      'reservation_id',
      'user_id',
    ]);
    expect(metadata).toMatchObject({
      org_id: ORG,
      user_id: 'user-1',
      conversation_id: 'conv-1',
      price_version: PRICE_TABLE_VERSION,
    });
    expect(metadata.reservation_id).toBe(
      (calls.reserves[0] as { request: CreditReserveRequest }).request.reservationId
    );
  });
});

describe('AiEgress commit and release', () => {
  it('commits the usage of a JSON answer once and returns the answer untouched', async () => {
    const { egress, calls, settle } = setup();
    const response = await egress.fetch(chat(valid()));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      choices: [],
      usage: { prompt_tokens: 12, completion_tokens: 34 },
    });
    await settle();
    expect(calls.commits).toHaveLength(1);
    expect(calls.commits[0]).toMatchObject({
      orgId: ORG,
      usage: { promptTokens: 12, completionTokens: 34 },
    });
    expect(calls.releases).toHaveLength(0);
  });

  it('commits in full (usage dropped) when a JSON answer outgrows the usage buffer, and passes it through whole', async () => {
    const filler = 'x'.repeat(4 * 1024 * 1024 + 1024);
    const answer = JSON.stringify({
      choices: [{ message: { content: filler } }],
      usage: { prompt_tokens: 5, completion_tokens: 6 },
    });
    const { egress, calls, settle } = setup({
      upstream: () => new Response(answer, { headers: { 'content-type': 'application/json' } }),
    });
    const response = await egress.fetch(chat(valid()));
    expect((await response.text()).length).toBe(answer.length);
    await settle();
    expect(calls.commits).toHaveLength(1);
    expect(calls.commits[0]).not.toHaveProperty('usage');
    expect(calls.releases).toHaveLength(0);
  });

  const sse = (lines: string[]) =>
    new Response(`${lines.join('\n\n')}\n\n`, {
      headers: { 'content-type': 'text/event-stream' },
    });

  it('commits the last usage chunk of a stream, split across reads', async () => {
    const encoder = new TextEncoder();
    const text =
      'data: {"choices":[{"delta":{"content":"a"}}]}\n\n' +
      'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":9}}\n\n' +
      'data: [DONE]\n\n';
    const bytes = encoder.encode(text);
    const cut = 70;
    const { egress, calls, settle } = setup({
      upstream: () =>
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(bytes.slice(0, cut));
              controller.enqueue(bytes.slice(cut));
              controller.close();
            },
          }),
          { headers: { 'content-type': 'text/event-stream' } }
        ),
    });
    const response = await egress.fetch(chat(valid({ stream: true })));
    expect(await response.text()).toBe(text);
    await settle();
    expect(calls.commits).toHaveLength(1);
    expect(calls.commits[0]?.usage).toEqual({ promptTokens: 7, completionTokens: 9 });
  });

  it('commits in full (no usage) when a stream ends without a usage chunk', async () => {
    const { egress, calls, settle } = setup({
      upstream: () => sse(['data: {"choices":[{"delta":{"content":"a"}}]}', 'data: [DONE]']),
    });
    await (await egress.fetch(chat(valid({ stream: true })))).text();
    await settle();
    expect(calls.commits).toHaveLength(1);
    expect(calls.commits[0]).not.toHaveProperty('usage');
  });

  it('commits once with the usage seen so far when the container cancels the stream', async () => {
    const encoder = new TextEncoder();
    const { egress, calls, settle } = setup({
      upstream: () =>
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":1}}\n\n'
                )
              );
            },
          }),
          { headers: { 'content-type': 'text/event-stream' } }
        ),
    });
    const response = await egress.fetch(chat(valid({ stream: true })));
    const reader = (response.body as ReadableStream<Uint8Array>).getReader();
    await reader.read();
    await reader.cancel();
    await settle();
    expect(calls.commits).toHaveLength(1);
    expect(calls.commits[0]?.usage).toEqual({ promptTokens: 3, completionTokens: 1 });
  });

  it('passes the request abort signal to the gateway fetch', async () => {
    let signal: AbortSignal | undefined;
    const { egress } = setup({
      upstream: (request) => {
        signal = request.signal;
        return Response.json({});
      },
    });
    const controller = new AbortController();
    const request = new Request(`http://ai.internal${AI_COMPAT_PATH}`, {
      method: 'POST',
      headers: { [AI_USER_HEADER]: 'user-1', [AI_CONVERSATION_HEADER]: 'conv-1' },
      body: JSON.stringify(valid()),
      signal: controller.signal,
    });
    await egress.fetch(request);
    controller.abort();
    expect(signal?.aborted).toBe(true);
  });

  it('releases the reservation and answers 502 when the gateway cannot be reached', async () => {
    const { egress, calls, settle } = setup({
      upstream: () => Promise.reject(new Error('connect failed')),
    });
    const response = await egress.fetch(chat(valid()));
    expect(response.status).toBe(502);
    expect(await codeOf(response)).toBe('upstream-unreachable');
    await settle();
    expect(calls.releases).toHaveLength(1);
    expect(calls.commits).toHaveLength(0);
  });

  it('releases the reservation and passes a gateway error status through', async () => {
    const { egress, calls, settle } = setup({
      upstream: () => new Response('{"error":"rate"}', { status: 429 }),
    });
    const response = await egress.fetch(chat(valid()));
    expect(response.status).toBe(429);
    await settle();
    expect(calls.releases).toHaveLength(1);
    expect(calls.commits).toHaveLength(0);
  });
});

describe('the ai.internal intercept', () => {
  function intercepts(exported: Record<string, unknown>) {
    const registered: { host: string; binding: unknown }[] = [];
    const container = {
      interceptOutboundHttp: (host: string, binding: unknown) => {
        registered.push({ host, binding });
        return Promise.resolve();
      },
    };
    const ctx = { id: { toString: () => 'id:x' }, exports: exported };
    return { registered, run: () => registerEgress(ctx as never, container as never, ORG, 0) };
  }

  it('registers ai.internal to AiEgress beside account.internal, with the same props', async () => {
    const account = vi.fn((options: { props: unknown }) => ({ via: 'account', ...options }));
    const ai = vi.fn((options: { props: unknown }) => ({ via: 'ai', ...options }));
    const { registered, run } = intercepts({ AccountEgress: account, AiEgress: ai });
    await run();
    expect(registered.map((entry) => entry.host).sort((a, b) => a.localeCompare(b))).toEqual([
      'account.internal',
      AI_EGRESS_HOST,
    ]);
    expect(AI_EGRESS_HOST).toBe('ai.internal');
    const props = { orgId: ORG, placement: 0, containerId: 'id:x' };
    expect(account).toHaveBeenCalledWith({ props });
    expect(ai).toHaveBeenCalledWith({ props });
  });

  it('still fails the start when AccountEgress is missing', async () => {
    const { run } = intercepts({ AiEgress: vi.fn() });
    await expect(run()).rejects.toThrow('egress-entrypoint-missing');
  });
});

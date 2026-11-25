/**
 * Provider adapter (AP5 of PLAN-console-ai-providers) against a local mock HTTP
 * server speaking Anthropic Messages and OpenAI chat, both streaming a tool call.
 *
 * The profile keeps its real public https base URL, so the D5 guard sees what
 * production sees; the fetch handed to the adapter then sends the guarded
 * request to the mock server on loopback.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import type { AddressInfo } from 'node:net';
import type { Profile } from '@rediacc/shared/ai';
import { jsonSchema, streamText, tool } from 'ai';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { createProviderModel, guardedFetch, ProviderProfileError } from '../provider.js';

interface Recorded {
  method: string;
  path: string;
  headers: IncomingMessage['headers'];
  body: Record<string, unknown>;
}

const recorded: Recorded[] = [];
let server: Server;
let origin = '';

function sse(res: ServerResponse, frames: string[]): void {
  res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' });
  for (const frame of frames) res.write(frame);
  res.end();
}

function anthropicStream(res: ServerResponse): void {
  const event = (type: string, data: Record<string, unknown>) =>
    `event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`;
  sse(res, [
    event('message_start', {
      message: {
        id: 'msg_1',
        type: 'message',
        role: 'assistant',
        model: 'claude-test',
        content: [],
        stop_reason: null,
        stop_sequence: null,
        usage: { input_tokens: 12, output_tokens: 1 },
      },
    }),
    event('content_block_start', {
      index: 0,
      content_block: { type: 'tool_use', id: 'toolu_1', name: 'echo_nonce', input: {} },
    }),
    event('content_block_delta', {
      index: 0,
      delta: { type: 'input_json_delta', partial_json: '{"nonce":' },
    }),
    event('content_block_delta', {
      index: 0,
      delta: { type: 'input_json_delta', partial_json: '"n-4242"}' },
    }),
    event('content_block_stop', { index: 0 }),
    event('message_delta', {
      delta: { stop_reason: 'tool_use', stop_sequence: null },
      usage: { output_tokens: 9 },
    }),
    event('message_stop', {}),
  ]);
}

function openaiStream(res: ServerResponse): void {
  const chunk = (delta: Record<string, unknown>, finish: string | null) =>
    `data: ${JSON.stringify({
      id: 'chatcmpl-1',
      object: 'chat.completion.chunk',
      created: 1_764_000_000,
      model: 'gpt-test',
      choices: [{ index: 0, delta, finish_reason: finish }],
    })}\n\n`;
  sse(res, [
    chunk(
      {
        role: 'assistant',
        tool_calls: [
          {
            index: 0,
            id: 'call_1',
            type: 'function',
            function: { name: 'echo_nonce', arguments: '' },
          },
        ],
      },
      null
    ),
    chunk({ tool_calls: [{ index: 0, function: { arguments: '{"nonce":' } }] }, null),
    chunk({ tool_calls: [{ index: 0, function: { arguments: '"n-4242"}' } }] }, null),
    chunk({}, 'tool_calls'),
    `data: ${JSON.stringify({
      id: 'chatcmpl-1',
      object: 'chat.completion.chunk',
      created: 1_764_000_000,
      model: 'gpt-test',
      choices: [],
      usage: { prompt_tokens: 12, completion_tokens: 9, total_tokens: 21 },
    })}\n\n`,
    'data: [DONE]\n\n',
  ]);
}

/** The mock provider: two streaming endpoints, a redirect, and the redirect's target. */
function respond(path: string, res: ServerResponse): void {
  const routes: Record<string, () => void> = {
    '/v1/messages': () => anthropicStream(res),
    '/v1/chat/completions': () => openaiStream(res),
    // A loopback target the test fetch can reach, so following the redirect would be observable.
    '/v1/redirect/chat/completions': () => {
      res.writeHead(307, { location: `${origin}/v1/leak` });
      res.end();
    },
    '/v1/leak': () => {
      res.writeHead(200);
      res.end('{}');
    },
  };
  const route = routes[path];
  if (route) {
    route();
    return;
  }
  res.writeHead(404);
  res.end();
}

beforeAll(async () => {
  server = createServer((req, res) => {
    let raw = '';
    req.on('data', (part: Buffer) => {
      raw += part.toString('utf8');
    });
    req.on('end', () => {
      const path = req.url ?? '';
      recorded.push({
        method: req.method ?? '',
        path,
        headers: req.headers,
        body: raw ? (JSON.parse(raw) as Record<string, unknown>) : {},
      });
      respond(path, res);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

afterEach(() => {
  recorded.length = 0;
  delete process.env.ANTHROPIC_API_KEY;
});

/** Sends a guarded request to the mock server, keeping its path and query. */
const toMock: typeof fetch = (input, init) => {
  const url = new URL(input instanceof Request ? input.url : input);
  return fetch(`${origin}${url.pathname}${url.search}`, init);
};

const CAPS = { tools: true, streaming: true, parallelToolCalls: false, vision: false };

function anthropicProfile(over: Partial<Profile> = {}): Profile {
  return {
    format: 'anthropic-messages',
    baseURL: 'https://api.anthropic.example/v1',
    key: 'sk-ant-mock',
    authScheme: 'x-api-key',
    model: 'claude-test',
    capabilities: CAPS,
    ...over,
  } as Profile;
}

function openaiProfile(over: Partial<Profile> = {}): Profile {
  return {
    format: 'openai-chat',
    baseURL: 'https://llm.openai.example/v1',
    key: 'sk-oai-mock',
    authScheme: 'bearer',
    model: 'gpt-test',
    capabilities: CAPS,
    ...over,
  } as Profile;
}

const echoNonce = tool({
  description: 'Echo the nonce back.',
  inputSchema: jsonSchema<{ nonce: string }>({
    type: 'object',
    properties: { nonce: { type: 'string' } },
    required: ['nonce'],
    additionalProperties: false,
  }),
});

async function runTurn(profile: Profile) {
  const result = streamText({
    model: createProviderModel(profile, { fetch: toMock }),
    prompt: 'Call echo_nonce with nonce n-4242.',
    maxOutputTokens: 256,
    tools: { echo_nonce: echoNonce },
  });
  const parts: string[] = [];
  for await (const part of result.fullStream) parts.push(part.type);
  return { toolCalls: await result.toolCalls, finishReason: await result.finishReason, parts };
}

describe('anthropic-messages profile', () => {
  it('streams a tool call from the Messages endpoint with the x-api-key header', async () => {
    const turn = await runTurn(anthropicProfile());
    expect(turn.toolCalls.map((c) => [c.toolName, c.input])).toEqual([
      ['echo_nonce', { nonce: 'n-4242' }],
    ]);
    expect(turn.finishReason).toBe('tool-calls');
    expect(turn.parts).toContain('tool-input-delta');

    expect(recorded).toHaveLength(1);
    const [req] = recorded;
    expect(req.method).toBe('POST');
    expect(req.path).toBe('/v1/messages');
    expect(req.headers['x-api-key']).toBe('sk-ant-mock');
    expect(req.headers.authorization).toBeUndefined();
    expect(req.body.model).toBe('claude-test');
    expect(req.body.stream).toBe(true);
  });

  it('sends the key as a bearer token when the profile says so', async () => {
    await runTurn(anthropicProfile({ authScheme: 'bearer' }));
    expect(recorded[0].headers.authorization).toBe('Bearer sk-ant-mock');
    expect(recorded[0].headers['x-api-key']).toBeUndefined();
  });

  it('never sends ANTHROPIC_API_KEY on a byokOnly profile, only its gateway header', async () => {
    process.env.ANTHROPIC_API_KEY = 'sk-ant-from-the-environment';
    const byok = anthropicProfile({
      byokOnly: true,
      headers: { 'cf-aig-authorization': 'Bearer gw-token' },
    });
    delete (byok as { key?: string }).key;
    await runTurn(byok);
    const headers = recorded[0].headers;
    expect(headers['cf-aig-authorization']).toBe('Bearer gw-token');
    expect(headers['x-api-key']).toBeUndefined();
    expect(headers.authorization).toBeUndefined();
    expect(JSON.stringify(headers)).not.toContain('sk-ant-from-the-environment');
  });
});

describe('openai-chat profile', () => {
  it('streams a tool call from the chat completions endpoint with a bearer key and profile headers', async () => {
    const turn = await runTurn(openaiProfile({ headers: { 'x-portkey-config': 'cfg-1' } }));
    expect(turn.toolCalls.map((c) => [c.toolName, c.input])).toEqual([
      ['echo_nonce', { nonce: 'n-4242' }],
    ]);
    expect(turn.finishReason).toBe('tool-calls');

    const [req] = recorded;
    expect(req.path).toBe('/v1/chat/completions');
    expect(req.headers.authorization).toBe('Bearer sk-oai-mock');
    expect(req.headers['x-portkey-config']).toBe('cfg-1');
    expect(req.body.model).toBe('gpt-test');
    expect(req.body.stream).toBe(true);
    expect(req.body.tools).toEqual([
      expect.objectContaining({
        type: 'function',
        function: expect.objectContaining({ name: 'echo_nonce' }),
      }),
    ]);
  });

  it('sends the key as x-api-key when the profile says so', async () => {
    await runTurn(openaiProfile({ authScheme: 'x-api-key' }));
    expect(recorded[0].headers['x-api-key']).toBe('sk-oai-mock');
    expect(recorded[0].headers.authorization).toBeUndefined();
  });
});

describe('the D5 guard', () => {
  it.each([
    ['account.internal', 'https://account.internal/v1'],
    ['loopback', 'https://127.0.0.1/v1'],
    ['RFC 1918', 'https://192.168.1.10/v1'],
    ['plain http', 'http://api.anthropic.example/v1'],
  ])('refuses to build a model for a %s base URL', (_label, baseURL) => {
    expect(() => createProviderModel(anthropicProfile({ baseURL }), { fetch: toMock })).toThrow(
      ProviderProfileError
    );
    expect(recorded).toEqual([]);
  });

  it('refuses a profile header that collides with the auth header', () => {
    expect(() =>
      createProviderModel(openaiProfile({ headers: { Authorization: 'Bearer other' } }))
    ).toThrow(/collides with the bearer auth header/);
  });

  it('re-runs the guard on each request URL at call time, before anything is sent', async () => {
    const send = guardedFetch(openaiProfile(), toMock);
    await expect(send('https://10.0.0.5/v1/chat/completions', { method: 'POST' })).rejects.toThrow(
      /private network address/
    );
    await expect(
      send('https://elsewhere.example/v1/chat/completions', { method: 'POST' })
    ).rejects.toThrow(/outside the profile's baseURL/);
    expect(recorded).toEqual([]);
    // control: a URL under the profile's base URL goes out
    const ok = await send('https://llm.openai.example/v1/chat/completions', {
      method: 'POST',
      body: '{}',
    });
    expect(ok.status).toBe(200);
    expect(recorded).toHaveLength(1);
  });

  it('refuses a Request object, whose method and body it would not forward', async () => {
    const send = guardedFetch(openaiProfile(), toMock);
    const request = new Request('https://llm.openai.example/v1/chat/completions', {
      method: 'POST',
      body: '{}',
    });
    await expect(send(request)).rejects.toThrow(/takes a URL and an init/);
    expect(recorded).toEqual([]);
  });

  it('refuses a redirect instead of following it with the key', async () => {
    const send = guardedFetch(openaiProfile(), toMock);
    await expect(
      send('https://llm.openai.example/v1/redirect/chat/completions', {
        method: 'POST',
        body: '{}',
      })
    ).rejects.toThrow();
    expect(recorded.map((r) => r.path)).toEqual(['/v1/redirect/chat/completions']);
  });
});

/**
 * Tool-calling smoke (D12 and AP8 of PLAN-console-ai-providers).
 *
 * Mock models script each step of the turn: the passing case calls
 * `echo_nonce` with the nonce and then streams a final message; every other
 * script must fail with a reason naming what was missing, and a provider error
 * must surface its HTTP status and message.
 */
import type { Profile } from '@rediacc/shared/ai';
import { APICallError, simulateReadableStream } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';
import { describe, expect, it } from 'vitest';
import { runSmoke, SMOKE_TOOL_NAME, smokeProfile } from '../smoke.js';

/** A part of a mock model's stream, read off the mock itself rather than a package the CLI does not declare. */
type StreamPart =
  Awaited<ReturnType<MockLanguageModelV4['doStream']>>['stream'] extends ReadableStream<infer P>
    ? P
    : never;

const NONCE = 'n-0123456789abcdef';

const USAGE = {
  inputTokens: { total: 10, noCache: 10, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 5, text: 5, reasoning: undefined },
};

function finish(unified: 'stop' | 'tool-calls'): StreamPart {
  return { type: 'finish', usage: USAGE, finishReason: { unified, raw: unified } };
}

function step(parts: StreamPart[]) {
  return {
    stream: simulateReadableStream({
      chunks: [{ type: 'stream-start', warnings: [] } as StreamPart, ...parts],
    }),
  };
}

function toolCallStep(toolName: string, input: Record<string, unknown>) {
  const json = JSON.stringify(input);
  return step([
    { type: 'tool-input-start', id: 'call-1', toolName },
    { type: 'tool-input-delta', id: 'call-1', delta: json },
    { type: 'tool-input-end', id: 'call-1' },
    { type: 'tool-call', toolCallId: 'call-1', toolName, input: json },
    finish('tool-calls'),
  ]);
}

function textStep(text: string) {
  return step([
    { type: 'text-start', id: 't-1' },
    { type: 'text-delta', id: 't-1', delta: text },
    { type: 'text-end', id: 't-1' },
    finish('stop'),
  ]);
}

function model(steps: ReturnType<typeof step>[]) {
  return new MockLanguageModelV4({ doStream: steps });
}

let clock = 1_000;
const now = () => {
  clock += 25;
  return clock;
};

describe('runSmoke', () => {
  it('passes on an echo_nonce call carrying the nonce followed by a streamed final message', async () => {
    const mock = model([
      toolCallStep(SMOKE_TOOL_NAME, { nonce: NONCE }),
      textStep('Nonce echoed.'),
    ]);
    const result = await runSmoke(mock, { nonce: NONCE, now });
    expect(result).toEqual({ ok: true, latencyMs: 25, observed: { tools: true, streaming: true } });

    // One tool offered, the nonce in the prompt, and the tool result handed back in step two.
    expect(mock.doStreamCalls).toHaveLength(2);
    const [first, second] = mock.doStreamCalls;
    expect(first.tools?.map((t) => t.name)).toEqual([SMOKE_TOOL_NAME]);
    expect(JSON.stringify(first.prompt)).toContain(NONCE);
    expect(first.maxOutputTokens).toBe(512);
    expect(JSON.stringify(second.prompt)).toContain('tool-result');
  });

  it('fails a model that skips the tool and answers directly', async () => {
    const mock = model([textStep('I would rather not call tools.')]);
    const result = await runSmoke(mock, { nonce: NONCE, now });
    expect(result).toMatchObject({
      ok: false,
      reason: 'no-tool-call',
      observed: { tools: false, streaming: true },
    });
    expect(mock.doStreamCalls).toHaveLength(1);
  });

  it('fails a call carrying another value', async () => {
    const mock = model([toolCallStep(SMOKE_TOOL_NAME, { nonce: 'n-guess' }), textStep('Done.')]);
    expect(await runSmoke(mock, { nonce: NONCE, now })).toMatchObject({
      ok: false,
      reason: 'wrong-nonce',
      observed: { tools: true },
    });
  });

  it('fails a turn that stops after the tool result without a final message', async () => {
    const mock = model([toolCallStep(SMOKE_TOOL_NAME, { nonce: NONCE }), textStep('   ')]);
    expect(await runSmoke(mock, { nonce: NONCE, now })).toMatchObject({
      ok: false,
      reason: 'no-final-message',
    });
  });

  it('fails with the provider status and message on a provider error, without retrying', async () => {
    let calls = 0;
    const mock = new MockLanguageModelV4({
      doStream: () => {
        calls += 1;
        throw new APICallError({
          message: 'invalid x-api-key',
          url: 'https://api.anthropic.example/v1/messages',
          requestBodyValues: {},
          statusCode: 401,
          isRetryable: false,
        });
      },
    });
    expect(await runSmoke(mock, { nonce: NONCE, now })).toMatchObject({
      ok: false,
      reason: 'provider-error',
      status: 401,
      message: 'invalid x-api-key',
    });

    const overloaded = new MockLanguageModelV4({
      doStream: () => {
        calls += 1;
        throw new APICallError({
          message: 'Overloaded',
          url: 'https://api.anthropic.example/v1/messages',
          requestBodyValues: {},
          statusCode: 529,
          isRetryable: true,
        });
      },
    });
    calls = 0;
    expect(await runSmoke(overloaded, { nonce: NONCE, now })).toMatchObject({
      reason: 'provider-error',
      status: 529,
    });
    expect(calls).toBe(1);
  });

  it('draws a fresh nonce per run when none is given', async () => {
    const prompts: string[] = [];
    for (let i = 0; i < 2; i += 1) {
      const mock = model([textStep('no tools')]);
      await runSmoke(mock);
      prompts.push(JSON.stringify(mock.doStreamCalls[0].prompt));
    }
    const nonces = prompts.map((p) => /n-[0-9a-f]{16}/.exec(p)?.[0]);
    expect(nonces[0]).toBeDefined();
    expect(nonces[0]).not.toBe(nonces[1]);
  });
});

describe('smokeProfile', () => {
  it('fails a refused profile without sending a request', async () => {
    let sent = 0;
    const profile = {
      format: 'openai-chat',
      baseURL: 'https://account.internal/v1',
      key: 'sk-test',
      authScheme: 'bearer',
      model: 'gpt-test',
      capabilities: { tools: true, streaming: true, parallelToolCalls: false, vision: false },
    } as Profile;
    const result = await smokeProfile(profile, {
      fetch: () => {
        sent += 1;
        return Promise.resolve(new Response('{}'));
      },
    });
    expect(result).toMatchObject({ ok: false, reason: 'profile-refused' });
    expect(result.ok ? '' : result.message).toMatch(/internal host/);
    expect(sent).toBe(0);
  });
});

/**
 * The loop's call of the bug-report offer (AF4 of agent/plans/PLAN-console-ai-feedback.md): each
 * failed tool run is judged once, an offer streams as a `feedback_offer` event, and a refused or
 * successful call never reaches the decision.
 */

import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import { APICallError, simulateReadableStream, tool } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import {
  decideFeedbackOffer,
  type FeedbackOfferDeps,
  type FeedbackRunRecord,
  runFeedbackClassify,
} from '../feedback-offer.js';
import { runAiTurn } from '../loop.js';

type StreamPart =
  Awaited<ReturnType<MockLanguageModelV4['doStream']>>['stream'] extends ReadableStream<infer P>
    ? P
    : never;

const USAGE = {
  inputTokens: { total: 1, noCache: 1, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 1, text: 1, reasoning: undefined },
};

function step(parts: StreamPart[]) {
  return {
    stream: simulateReadableStream({
      chunks: [{ type: 'stream-start', warnings: [] } as StreamPart, ...parts],
    }),
  };
}

const callStep = (id: string) =>
  step([
    { type: 'tool-call', toolCallId: id, toolName: 'run_cmd', input: '{}' },
    { type: 'finish', usage: USAGE, finishReason: { unified: 'tool-calls', raw: 'tool_use' } },
  ]);

const doneStep = () =>
  step([{ type: 'finish', usage: USAGE, finishReason: { unified: 'stop', raw: 'end_turn' } }]);

const RUN: FeedbackRunRecord = {
  runId: 'conv:t1',
  pathKey: 'repo up',
  state: 'failed',
  exitCode: 1,
  errorCode: 'INTERNAL_ERROR',
};

interface TurnOptions {
  steps?: ReturnType<typeof step>[];
  runIdOf?: (toolCallId: string) => string;
  draft?: FeedbackOfferDeps['draft'];
  emit?: (event: AiEvent) => void;
  abortSignal?: AbortSignal;
}

function turn(output: unknown, options: TurnOptions = {}) {
  const events: AiEvent[] = [];
  const loadRun = vi.fn(async (_runId: string) => RUN);
  const deps: FeedbackOfferDeps = {
    errorCodes: [{ code: 'INTERNAL_ERROR', origin: 'rediacc' }],
    settings: {},
    env: { cliVersion: '1.2.3', os: 'linux', arch: 'x64' },
    loadRun,
    openTail: async () => '',
    classify: async () => ({ offer: false, reason: 'unused' }),
    draft: options.draft ?? (async () => ({ message: 'repo up crashed' })),
    judged: new Set(),
  };
  const model = new MockLanguageModelV4({
    doStream: options.steps ?? [callStep('t1'), doneStep()],
  });
  const run = () =>
    runAiTurn({
      model,
      tools: {
        run_cmd: tool({ inputSchema: z.object({}), execute: async () => output }),
      },
      messages: [{ role: 'user', content: 'bring it up' }],
      emit: (event) => {
        events.push(event);
        options.emit?.(event);
      },
      issueApproval: () => 'token',
      ...(options.abortSignal ? { abortSignal: options.abortSignal } : {}),
      feedback: { deps, runIdOf: options.runIdOf ?? ((toolCallId) => `conv:${toolCallId}`) },
    });
  return { run, events, loadRun, model };
}

describe('the loop and the bug-report offer', () => {
  it('judges a failed run once and streams the offer with the run id', async () => {
    const { run, events, loadRun } = turn({ status: 'failed', exitCode: 1, output: '' });
    await run();
    expect(loadRun).toHaveBeenCalledTimes(1);
    expect(loadRun).toHaveBeenCalledWith('conv:t1');
    const offers = events.filter((e) => e.type === 'feedback_offer');
    expect(offers).toMatchObject([{ type: 'feedback_offer', runId: 'conv:t1' }]);
  });

  it('never judges a call that succeeded or was refused', async () => {
    for (const output of [{ status: 'ok', exitCode: 0, output: '' }, { status: 'refused' }]) {
      const { run, events, loadRun } = turn(output);
      await run();
      expect(loadRun).not.toHaveBeenCalled();
      expect(events.some((e) => e.type === 'feedback_offer')).toBe(false);
    }
  });

  it('judges each distinct failed call, and a run that fails under one id twice only once', async () => {
    const steps = () => [callStep('t1'), callStep('t2'), doneStep()];
    const failed = { status: 'failed', exitCode: 1, output: '' };
    const distinct = turn(failed, { steps: steps() });
    await distinct.run();
    expect(distinct.loadRun.mock.calls.map(([id]) => id)).toEqual(['conv:t1', 'conv:t2']);
    expect(distinct.events.filter((e) => e.type === 'feedback_offer')).toHaveLength(2);

    const same = turn(failed, { steps: steps(), runIdOf: () => 'conv:same' });
    await same.run();
    expect(same.loadRun).toHaveBeenCalledTimes(1);
    expect(same.events.filter((e) => e.type === 'feedback_offer')).toHaveLength(1);
  });

  it('does not wait for the offer, nor emit it, once the client has disconnected', async () => {
    const controller = new AbortController();
    const { run, events } = turn(
      { status: 'failed', exitCode: 1, output: '' },
      {
        abortSignal: controller.signal,
        // A draft that never answers: a turn that waits on it never ends.
        draft: () => new Promise(() => undefined),
        emit: (event) => {
          if (event.type === 'tool_result') controller.abort();
        },
      }
    );
    await run();
    expect(events.some((e) => e.type === 'feedback_offer')).toBe(false);
  }, 2000);

  it('keeps a failing emit of the offer from turning the turn into an error', async () => {
    const { run, events } = turn(
      { status: 'failed', exitCode: 1, output: '' },
      {
        emit: (event) => {
          if (event.type === 'feedback_offer') throw new Error('stream closed');
        },
      }
    );
    await run();
    expect(events.some((e) => e.type === 'error')).toBe(false);
  });
});

describe('the loop around the model', () => {
  it('tells the model its tools run CLI commands', async () => {
    const { run, model } = turn({ status: 'ok', exitCode: 0, output: '' });
    await run();
    const system = model.doStreamCalls[0]?.prompt.find((m) => m.role === 'system');
    expect(system?.content).toContain('which run CLI commands.');
    expect(system?.content).not.toContain('rdc commands');
  });

  it('names a provider status in the error, and no status when the code is 0', async () => {
    const messages: string[] = [];
    for (const statusCode of [429, 0]) {
      const events: AiEvent[] = [];
      await runAiTurn({
        model: new MockLanguageModelV4({
          doStream: () => {
            throw new APICallError({
              message: 'slow down',
              url: 'https://api.example',
              requestBodyValues: {},
              statusCode,
            });
          },
        }),
        tools: {},
        messages: [{ role: 'user', content: 'hi' }],
        emit: (event) => events.push(event),
        issueApproval: () => 'token',
      });
      const error = events.find((e) => e.type === 'error');
      messages.push(error?.type === 'error' ? error.message : '');
    }
    expect(messages).toEqual([
      'The AI provider answered 429: slow down',
      'The AI provider answered with an error: slow down',
    ]);
  });
});

describe('the bug-report offer scrubs what leaves it', () => {
  const SECRET = 'abcdefgh12345678ZYXW';

  function deps(over: Partial<FeedbackOfferDeps>): FeedbackOfferDeps {
    return {
      errorCodes: [{ code: 'INTERNAL_ERROR', origin: 'rediacc' }],
      settings: {},
      env: { cliVersion: '1.2.3', os: 'linux', arch: 'x64' },
      loadRun: async () => ({ ...RUN, pathKey: `repo up Bearer ${SECRET}` }),
      openTail: async () => '',
      classify: async () => ({ offer: false, reason: 'unused' }),
      draft: async () => ({ message: 'm' }),
      judged: new Set(),
      ...over,
    };
  }

  it('hands the models a path key that has passed scrubText', async () => {
    const seen: string[] = [];
    await decideFeedbackOffer(
      'run-1',
      deps({
        draft: (record) => {
          seen.push(record.pathKey);
          return Promise.resolve({ message: 'm' });
        },
      })
    );
    expect(seen).toHaveLength(1);
    expect(seen[0]).toContain('repo up');
    expect(seen[0]).not.toContain(SECRET);
  });

  it('scrubs the provider error a failed classify call gives as its reason', async () => {
    const model = new MockLanguageModelV4({
      doGenerate: () => {
        throw new Error(`rejected Bearer ${SECRET}`);
      },
    });
    const verdict = await runFeedbackClassify(
      {
        format: 'anthropic-messages',
        baseURL: 'https://api.anthropic.com',
        authScheme: 'x-api-key',
        model: 'm',
        capabilities: { tools: true, streaming: true, parallelToolCalls: true, vision: false },
      },
      { pathKey: 'repo up', tail: '' },
      { model }
    );
    expect(verdict.offer).toBe(false);
    expect(verdict.reason).toContain('The classifier could not be asked');
    expect(verdict.reason).not.toContain(SECRET);
  });
});

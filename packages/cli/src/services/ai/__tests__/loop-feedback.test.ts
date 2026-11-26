/**
 * The loop's call of the bug-report offer (AF4 of agent/plans/PLAN-console-ai-feedback.md): each
 * failed tool run is judged once, an offer streams as a `feedback_offer` event, and a refused or
 * successful call never reaches the decision.
 */

import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import { simulateReadableStream, tool } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import type { FeedbackOfferDeps, FeedbackRunRecord } from '../feedback-offer.js';
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

function turn(output: unknown) {
  const events: AiEvent[] = [];
  const loadRun = vi.fn(async (_runId: string) => RUN);
  const deps: FeedbackOfferDeps = {
    errorCodes: [{ code: 'INTERNAL_ERROR', origin: 'rediacc' }],
    settings: {},
    env: { cliVersion: '1.2.3', os: 'linux', arch: 'x64' },
    loadRun,
    openTail: async () => '',
    classify: async () => ({ offer: false, reason: 'unused' }),
    draft: async () => ({ message: 'repo up crashed' }),
    judged: new Set(),
  };
  const run = () =>
    runAiTurn({
      model: new MockLanguageModelV4({ doStream: [callStep('t1'), doneStep()] }),
      tools: {
        run_cmd: tool({ inputSchema: z.object({}), execute: async () => output }),
      },
      messages: [{ role: 'user', content: 'bring it up' }],
      emit: (event) => events.push(event),
      issueApproval: () => 'token',
      feedback: { deps, runIdOf: (toolCallId) => `conv:${toolCallId}` },
    });
  return { run, events, loadRun };
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
});

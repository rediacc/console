/**
 * The model's UI tools (AI3 of agent/plans/PLAN-console-ai-assistant.md): `plan` and `present`
 * stream as their own typed events in place of a tool call and result, run nothing, and their
 * names are never a registry tool's.
 */

import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import { AiEventSchema } from '@rediacc/shared/cli-contract/wire';
import { listProxyTools } from '@rediacc/shared/mcp/registry';
import { simulateReadableStream } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';
import { describe, expect, it } from 'vitest';
import { runAiTurn } from '../loop.js';
import { PLAN_TOOL, PRESENT_TOOL, UI_TOOL_NAMES, uiEventOf } from '../ui-tools.js';

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

function callStep(toolName: string, input: unknown, id: string) {
  return step([
    { type: 'tool-call', toolCallId: id, toolName, input: JSON.stringify(input) },
    { type: 'finish', usage: USAGE, finishReason: { unified: 'tool-calls', raw: 'tool_use' } },
  ]);
}

const doneStep = () =>
  step([{ type: 'finish', usage: USAGE, finishReason: { unified: 'stop', raw: 'end_turn' } }]);

const PLAN = { steps: [{ title: 'Fork shop' }, { title: 'Bring the fork up' }] };
const TABLE = { card: { type: 'table', columns: ['repo', 'state'], rows: [['shop', 'up']] } };

describe('the UI tools', () => {
  it('reserve names no registry tool uses', () => {
    const registry = new Set(listProxyTools().map((t) => t.name));
    for (const name of UI_TOOL_NAMES) expect(registry.has(name)).toBe(false);
  });

  it('turn a plan and a present call into typed events that parse on the wire', () => {
    const plan = uiEventOf({ toolCallId: 'p1', toolName: PLAN_TOOL, input: PLAN });
    expect(plan).toEqual({ type: 'plan', toolCallId: 'p1', steps: PLAN.steps });
    const present = uiEventOf({ toolCallId: 'p2', toolName: PRESENT_TOOL, input: TABLE });
    expect(present).toEqual({ type: 'present', toolCallId: 'p2', card: TABLE.card });
    for (const event of [plan, present]) expect(AiEventSchema.parse(event)).toEqual(event);
  });

  it('give no event for an input outside the schema, or for another tool', () => {
    expect(uiEventOf({ toolCallId: 'x', toolName: PLAN_TOOL, input: { steps: [] } })).toBeNull();
    const bad = { card: { type: 'table', columns: [], rows: [] } };
    expect(uiEventOf({ toolCallId: 'x', toolName: PRESENT_TOOL, input: bad })).toBeNull();
    expect(uiEventOf({ toolCallId: 'x', toolName: 'repo_up', input: PLAN })).toBeNull();
  });

  it('stream from the loop as plan and present events, with no tool_call or tool_result', async () => {
    const events: AiEvent[] = [];
    const mock = new MockLanguageModelV4({
      doStream: [callStep(PLAN_TOOL, PLAN, 'p1'), callStep(PRESENT_TOOL, TABLE, 'p2'), doneStep()],
    });
    await runAiTurn({
      model: mock,
      tools: {},
      messages: [{ role: 'user', content: 'show me' }],
      emit: (event) => events.push(event),
      issueApproval: () => {
        throw new Error('a UI tool never asks for an approval');
      },
    });
    const types = events.map((e) => e.type);
    expect(types).toEqual(['plan', 'present', 'usage', 'finish']);
    expect(mock.doStreamCalls).toHaveLength(3);
  });
});

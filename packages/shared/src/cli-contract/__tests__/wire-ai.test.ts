/** The AI chat additions to the proxy wire (agent/plans/PLAN-console-ai-providers.md D8, AP3). */
import { describe, expect, it } from 'vitest';
import { AiEventSchema, PROXY_ROUTES, StreamLineSchema } from '../wire.js';

const aiEvents = [
  { type: 'text_delta', text: 'hello' },
  { type: 'tool_call', toolCallId: 'tc1', name: 'repo_status', input: { machine: 'm1' } },
  { type: 'tool_result', toolCallId: 'tc1', ok: true, output: 'up' },
  {
    type: 'approval_required',
    toolCallId: 'tc2',
    name: 'repo_down',
    input: { ref: 'shop:trial' },
    approvalToken: 'tok',
    command: { pathKey: 'repo down', params: {}, positionals: { ref: 'shop:trial' } },
    risk: 'destructive',
    reason: 'destructive',
  },
  { type: 'plan', toolCallId: 'tc3', steps: [{ title: 'Fork shop' }] },
  {
    type: 'present',
    toolCallId: 'tc4',
    card: { type: 'status', tone: 'ok', text: 'All repos are up.' },
  },
  { type: 'usage', inputTokens: 10, outputTokens: 4 },
  { type: 'finish', reason: 'stop' },
  { type: 'error', message: 'provider refused', code: 'AI_PROVIDER' },
] as const;

describe('AiEventSchema', () => {
  it.each(aiEvents)('round-trips $type', (event) => {
    expect(AiEventSchema.parse(event)).toEqual(event);
  });

  it('refuses an unknown type and a tool call without its id', () => {
    expect(AiEventSchema.safeParse({ type: 'thought', text: 'x' }).success).toBe(false);
    expect(AiEventSchema.safeParse({ type: 'tool_call', name: 'repo_status' }).success).toBe(false);
  });

  it('refuses an approval request without its token, its command or its risk', () => {
    const full = aiEvents[3];
    for (const field of ['approvalToken', 'command', 'risk'] as const) {
      const rest = Object.fromEntries(Object.entries(full).filter(([key]) => key !== field));
      expect(AiEventSchema.safeParse(rest).success).toBe(false);
    }
    expect(AiEventSchema.safeParse({ ...full, risk: 'harmless' }).success).toBe(false);
  });
});

describe('StreamLineSchema ai line', () => {
  it('parses a kind ai line and refuses one whose event is not an AiEvent', () => {
    const line = { kind: 'ai', ai: { type: 'text_delta', text: 'hi' } };
    expect(StreamLineSchema.parse(line)).toEqual(line);
    expect(StreamLineSchema.safeParse({ kind: 'ai', ai: { type: 'log', msg: 'x' } }).success).toBe(
      false
    );
  });

  it('carries the tool call id on a forwarded event line, and an event line without it is unchanged', () => {
    const tagged = {
      kind: 'event',
      event: { type: 'step_start', name: 'pull' },
      toolCallId: 'tc1',
    };
    expect(StreamLineSchema.parse(tagged)).toEqual(tagged);
    const plain = { kind: 'event', event: { type: 'log', msg: 'x' } };
    expect(StreamLineSchema.parse(plain)).toEqual(plain);
    expect(StreamLineSchema.safeParse({ ...tagged, toolCallId: '' }).success).toBe(false);
  });

  it('still parses every existing stream line unchanged', () => {
    const existing = [
      { kind: 'event', event: { type: 'output', msg: 'x' }, line: 3 },
      {
        kind: 'result',
        result: { success: true, exitCode: 0, durationMs: 5 },
        stdout: 'ok',
        stderr: '',
      },
      { kind: 'job', jobId: 'j1', machine: 'm1', sinceLine: 2 },
      { kind: 'heartbeat', ts: '2026-11-23T10:00:00Z' },
    ];
    for (const line of existing) {
      const parsed = StreamLineSchema.parse(line);
      expect(parsed).toMatchObject(line);
      expect(parsed).not.toHaveProperty('toolCallId');
    }
  });
});

describe('PROXY_ROUTES ai routes', () => {
  it('names the chat and test routes', () => {
    expect(PROXY_ROUTES.aiChat).toBe('/v1/ai/chat');
    expect(PROXY_ROUTES.aiTest).toBe('/v1/ai/test');
  });
});

import { describe, expect, it } from 'vitest';
import { StreamLineSchema } from '../../../cli-contract/wire.js';
import {
  getScript,
  pickScript,
  SCRIPT_IDS,
  scriptModelSteps,
  scriptNdjson,
  scriptStreamLines,
} from '../index.js';

describe('scripted AI provider', () => {
  it('ships the six scripts the plan names', () => {
    expect([...SCRIPT_IDS]).toEqual([
      'text',
      'tool-calls',
      'approval',
      'refusal',
      'feedback-offer',
      'provider-error',
    ]);
  });

  it.each(SCRIPT_IDS)('%s: every line parses as a stream line and ends with one finish', (id) => {
    const lines = scriptStreamLines(getScript(id));
    for (const line of lines) expect(StreamLineSchema.safeParse(line).success).toBe(true);
    const finishes = lines.filter((line) => line.kind === 'ai' && line.ai.type === 'finish');
    expect(finishes).toHaveLength(1);
    expect(lines.at(-1)).toEqual(finishes[0]);
  });

  it.each(SCRIPT_IDS)('%s: two replays are byte-identical', (id) => {
    expect(scriptNdjson(getScript(id))).toBe(scriptNdjson(getScript(id)));
    expect(JSON.stringify(scriptModelSteps(getScript(id)))).toBe(
      JSON.stringify(scriptModelSteps(getScript(id)))
    );
  });

  it('tags a tool call renet events with its call id, between the call and its result', () => {
    const kinds = scriptStreamLines(getScript('tool-calls')).map((line) =>
      line.kind === 'ai'
        ? line.ai.type
        : `${line.kind}:${'toolCallId' in line ? line.toolCallId : ''}`
    );
    const call = kinds.indexOf('tool_call');
    const result = kinds.indexOf('tool_result');
    expect(kinds.slice(call + 1, result)).toEqual([
      'event:scripted-call-1',
      'event:scripted-call-1',
    ]);
    expect(kinds.slice(-2)).toEqual(['usage', 'finish']);
  });

  it('ends the turn at an approval request without a tool result', () => {
    const lines = scriptStreamLines(getScript('approval'));
    const types = lines.map((line) => (line.kind === 'ai' ? line.ai.type : line.kind));
    expect(types).toContain('approval_required');
    expect(types).not.toContain('tool_call');
    expect(types).not.toContain('tool_result');
    expect(lines.at(-1)).toEqual({
      kind: 'ai',
      ai: { type: 'finish', reason: 'approval_required' },
    });
  });

  it('answers a provider error with a coded error line and no text', () => {
    expect(scriptStreamLines(getScript('provider-error'))).toEqual([
      {
        kind: 'ai',
        ai: {
          type: 'error',
          message: 'provider returned 401: invalid x-api-key',
          code: 'PROVIDER_ERROR',
        },
      },
      { kind: 'ai', ai: { type: 'finish', reason: 'error' } },
    ]);
    expect(getScript('provider-error').smoke).toMatchObject({
      ok: false,
      reason: 'provider-error',
      status: 401,
    });
  });

  it('renders one model step per provider round trip, the tool input as JSON', () => {
    const steps = scriptModelSteps(getScript('tool-calls'));
    expect(steps).toHaveLength(2);
    expect(steps[0][0]).toEqual({ type: 'stream-start', warnings: [] });
    expect(steps[0]).toContainEqual({
      type: 'tool-call',
      toolCallId: 'scripted-call-1',
      toolName: 'machine_list',
      input: '{}',
    });
    expect(steps[0].at(-1)).toMatchObject({
      type: 'finish',
      finishReason: { unified: 'tool-calls' },
    });
    expect(steps[1].at(-1)).toMatchObject({ type: 'finish', finishReason: { unified: 'stop' } });
    expect(scriptModelSteps(getScript('provider-error'))).toEqual([
      [
        { type: 'stream-start', warnings: [] },
        { type: 'error', error: { statusCode: 401, message: 'invalid x-api-key' } },
      ],
    ]);
  });

  it('picks by profile name, then by a script: message, else the text script', () => {
    expect(pickScript({ profile: 'refusal' }).id).toBe('refusal');
    expect(pickScript({ profile: 'main', lastUserMessage: 'script:approval' }).id).toBe('approval');
    expect(pickScript({ lastUserMessage: ' script: tool-calls ' }).id).toBe('tool-calls');
    expect(pickScript({ lastUserMessage: 'script:unknown' }).id).toBe('text');
    expect(pickScript({}).id).toBe('text');
  });
});

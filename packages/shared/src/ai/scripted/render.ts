/**
 * Two renderings of one script (scripts.ts): the NDJSON stream lines the loop host would emit
 * for it (served by the TEST_MODE console mock), and the per-step stream parts an AI SDK mock
 * model replays (for the executor unit tests). Both are pure functions of the script.
 *
 * The model parts are typed structurally, so this package stays free of the `ai` dependency;
 * they match the LanguageModel stream part shapes `MockLanguageModelV4` accepts.
 */
import type { AiEvent, StreamLine } from '../../cli-contract/wire.js';
import type { AiScript, ScriptPart, ScriptStep } from './scripts.js';

/** The finish reason of a script whose last step names none. */
const DEFAULT_FINISH = 'stop';

/** The code an `error` line carries when the provider refused the call. */
export const SCRIPTED_PROVIDER_ERROR_CODE = 'PROVIDER_ERROR';

/** Split a text into word-sized deltas, each keeping its trailing space, so a stream has several. */
function deltas(text: string): string[] {
  return text.match(/\S+\s*/g) ?? [text];
}

const aiLine = (ai: AiEvent): StreamLine => ({ kind: 'ai', ai });

/** The lines one script part yields; `ends` marks an approval request, which ends the turn (D9). */
function partLines(part: ScriptPart): { lines: StreamLine[]; ends: boolean } {
  if (part.type === 'text') {
    return {
      lines: deltas(part.text).map((text) => aiLine({ type: 'text_delta', text })),
      ends: false,
    };
  }
  const { toolCallId, toolName: name, input, outcome } = part;
  if (outcome.kind === 'approval') {
    // The TEST_MODE stream has no executor ledger behind it: the token is a fixed, unredeemable value.
    const approval: AiEvent = {
      type: 'approval_required',
      toolCallId,
      name,
      input,
      approvalToken: `scripted:${toolCallId}`,
      command: { pathKey: name.replaceAll('_', ' '), params: {}, positionals: { ...input } },
      risk: 'caution',
    };
    return { lines: [aiLine(approval)], ends: true };
  }
  return {
    lines: [
      aiLine({ type: 'tool_call', toolCallId, name, input }),
      ...(outcome.events ?? []).map((event): StreamLine => ({ kind: 'event', event, toolCallId })),
      aiLine({ type: 'tool_result', toolCallId, ok: outcome.ok, output: outcome.output }),
    ],
    ends: false,
  };
}

/** The lines of every step up to an approval request, with the token totals and finish reason. */
function stepLines(steps: ScriptStep[]) {
  const lines: StreamLine[] = [];
  let inputTokens = 0;
  let outputTokens = 0;
  for (const step of steps) {
    inputTokens += step.usage.inputTokens;
    outputTokens += step.usage.outputTokens;
    for (const part of step.parts) {
      const rendered = partLines(part);
      lines.push(...rendered.lines);
      if (rendered.ends) return { lines, inputTokens, outputTokens, reason: 'approval_required' };
    }
  }
  return { lines, inputTokens, outputTokens, reason: steps.at(-1)?.finish ?? DEFAULT_FINISH };
}

/**
 * The stream lines of one turn: text deltas, tool calls with their tagged renet events and
 * results, an approval request that ends the turn, one usage total and a finish line. A provider
 * error yields an `error` line and a finish with reason `error`.
 */
export function scriptStreamLines(script: AiScript): StreamLine[] {
  if (script.error) {
    return [
      aiLine({
        type: 'error',
        message: `provider returned ${script.error.status}: ${script.error.message}`,
        code: SCRIPTED_PROVIDER_ERROR_CODE,
      }),
      aiLine({ type: 'finish', reason: 'error' }),
    ];
  }
  const { lines, inputTokens, outputTokens, reason } = stepLines(script.steps);
  return [
    ...lines,
    aiLine({ type: 'usage', inputTokens, outputTokens }),
    aiLine({ type: 'finish', reason }),
  ];
}

/** The NDJSON body of a scripted turn, one JSON line per stream line. */
export function scriptNdjson(script: AiScript): string {
  return scriptStreamLines(script)
    .map((line) => `${JSON.stringify(line)}\n`)
    .join('');
}

/** One stream part of a mock model step, in the LanguageModel stream part shape. */
export type ScriptModelPart =
  | { type: 'stream-start'; warnings: [] }
  | { type: 'text-start'; id: string }
  | { type: 'text-delta'; id: string; delta: string }
  | { type: 'text-end'; id: string }
  | { type: 'tool-input-start'; id: string; toolName: string }
  | { type: 'tool-input-delta'; id: string; delta: string }
  | { type: 'tool-input-end'; id: string }
  | { type: 'tool-call'; toolCallId: string; toolName: string; input: string }
  | {
      type: 'finish';
      usage: {
        inputTokens: {
          total: number;
          noCache: number;
          cacheRead: undefined;
          cacheWrite: undefined;
        };
        outputTokens: { total: number; text: number; reasoning: undefined };
      };
      finishReason: { unified: 'stop' | 'tool-calls'; raw: string };
    }
  | { type: 'error'; error: { statusCode: number; message: string } };

function stepParts(step: ScriptStep, index: number): ScriptModelPart[] {
  const parts: ScriptModelPart[] = [{ type: 'stream-start', warnings: [] }];
  step.parts.forEach((part, partIndex) => {
    if (part.type === 'text') {
      const id = `text-${index}-${partIndex}`;
      parts.push({ type: 'text-start', id });
      for (const delta of deltas(part.text)) parts.push({ type: 'text-delta', id, delta });
      parts.push({ type: 'text-end', id });
      return;
    }
    const input = JSON.stringify(part.input);
    parts.push(
      { type: 'tool-input-start', id: part.toolCallId, toolName: part.toolName },
      { type: 'tool-input-delta', id: part.toolCallId, delta: input },
      { type: 'tool-input-end', id: part.toolCallId },
      { type: 'tool-call', toolCallId: part.toolCallId, toolName: part.toolName, input }
    );
  });
  parts.push({
    type: 'finish',
    usage: {
      inputTokens: {
        total: step.usage.inputTokens,
        noCache: step.usage.inputTokens,
        cacheRead: undefined,
        cacheWrite: undefined,
      },
      outputTokens: {
        total: step.usage.outputTokens,
        text: step.usage.outputTokens,
        reasoning: undefined,
      },
    },
    finishReason: { unified: step.finish, raw: step.finish },
  });
  return parts;
}

/**
 * The stream parts of each model step, one array per `doStream` call. A provider error is a
 * single step that starts and then errors with the provider's status and message.
 */
export function scriptModelSteps(script: AiScript): ScriptModelPart[][] {
  if (script.error) {
    return [
      [
        { type: 'stream-start', warnings: [] },
        {
          type: 'error',
          error: { statusCode: script.error.status, message: script.error.message },
        },
      ],
    ];
  }
  return script.steps.map(stepParts);
}

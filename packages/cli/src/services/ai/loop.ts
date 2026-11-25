/**
 * The AI loop host (AP7 of PLAN-console-ai-providers, D3, D8 and D11): one chat turn on a provider
 * model, streamed as `ai` events.
 *
 * The turn is the AI SDK's own tool loop, bounded by the executor: at most {@link MAX_TOOL_STEPS}
 * model steps per turn, a per-turn output token cap, and an abort that reaches the provider stream
 * and every running tool when the client disconnects. A tool result that asks for confirmation
 * (`approval_required`, tools.ts) ends the turn after that step. A provider failure is an `error`
 * event, never a thrown error, so the NDJSON stream always ends with a line the client can read.
 *
 * The turn knows nothing about principals, grants or configs: the route that hosts it builds the
 * tools (tools.ts) from the verified session and passes them in, with `issueApproval`, which mints
 * the single-use token (approvals.ts) each `approval_required` event carries. The UI tools
 * (ui-tools.ts) are offered beside them, and their calls stream as typed `plan` and `present`
 * events in place of a `tool_call`/`tool_result` pair.
 */

import type { AiApprovalCommand, AiEvent } from '@rediacc/shared/cli-contract/wire';
import {
  APICallError,
  isStepCount,
  type LanguageModel,
  type ModelMessage,
  streamText,
  type ToolSet,
} from 'ai';
import { approvalResultOf, stopOnApproval, toolResultEventOf } from './tools.js';
import { UI_TOOL_NAMES, uiEventOf, uiTools } from './ui-tools.js';
import { TOOL_OUTPUT_RULE } from './untrusted.js';

/** D11: tool steps per turn. */
export const MAX_TOOL_STEPS = 12;

/** D11: the per-turn output token cap when the caller names none. */
export const DEFAULT_MAX_OUTPUT_TOKENS = 8192;

/** The `finish` reason of a turn that stopped on {@link MAX_TOOL_STEPS} with the model still calling tools. */
export const STEP_LIMIT_REASON = 'step-limit';

/** The `error` code of a failure the provider answered with an HTTP status. */
export const AI_PROVIDER_ERROR = 'AI_PROVIDER_ERROR';

const SYSTEM_PROMPT = [
  'You operate infrastructure for the user through the tools offered, which run CLI commands.',
  'Call a tool only when the request needs it, and keep answers short.',
  'Before several commands, call plan with the steps; for a table, a status or a choice, call present.',
  TOOL_OUTPUT_RULE,
].join(' ');

type StreamPart = { type: string; [key: string]: unknown };

export interface AiTurnInput {
  model: LanguageModel;
  tools: ToolSet;
  messages: ModelMessage[];
  /** The per-turn output token cap; {@link DEFAULT_MAX_OUTPUT_TOKENS} when absent. */
  maxOutputTokens?: number;
  /** Aborted when the client disconnects; stops the provider stream and the running tools. */
  abortSignal?: AbortSignal;
  emit: (event: AiEvent) => void;
  /** Mints the single-use token of one held tool call, bound by the host to its principal and conversation. */
  issueApproval: (request: { toolCallId: string; command: AiApprovalCommand }) => string;
}

function errorEvent(error: unknown): AiEvent {
  if (APICallError.isInstance(error)) {
    return {
      type: 'error',
      message: `The AI provider answered ${error.statusCode ?? 'with an error'}: ${error.message}`,
      code: AI_PROVIDER_ERROR,
    };
  }
  return { type: 'error', message: error instanceof Error ? error.message : String(error) };
}

function numberOf(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

/** Fold the stream parts of a turn into events, in arrival order. */
class TurnFold {
  steps = 0;
  lastStepReason = '';
  aborted = false;
  failed = false;

  constructor(private readonly input: AiTurnInput) {}

  part(part: StreamPart): void {
    const { emit } = this.input;
    switch (part.type) {
      case 'text-delta':
        emit({ type: 'text_delta', text: String(part.text) });
        break;
      case 'tool-call':
        // A UI tool's call streams as its own event once its result arrives.
        if (UI_TOOL_NAMES.has(String(part.toolName))) break;
        emit({
          type: 'tool_call',
          toolCallId: String(part.toolCallId),
          name: String(part.toolName),
          input: part.input,
        });
        break;
      case 'tool-result':
        this.toolResult(part);
        break;
      case 'tool-error':
        // A tool that threw (an audit record that could not be delivered, a cancelled run): the model reads the failure, and so does the client.
        emit({
          type: 'tool_result',
          toolCallId: String(part.toolCallId),
          ok: false,
          output: {
            status: 'failed',
            error: part.error instanceof Error ? part.error.message : String(part.error),
          },
        });
        break;
      case 'finish-step':
        this.steps += 1;
        this.lastStepReason = String((part.finishReason as unknown) ?? '');
        break;
      case 'finish':
        this.finish(part);
        break;
      case 'abort':
        this.aborted = true;
        break;
      case 'error':
        this.failed = true;
        emit(errorEvent(part.error));
        break;
      default:
        break;
    }
  }

  private toolResult(part: StreamPart): void {
    const toolCallId = String(part.toolCallId);
    const toolName = String(part.toolName);
    if (UI_TOOL_NAMES.has(toolName)) {
      const event = uiEventOf({ toolCallId, toolName, input: part.input });
      if (event) this.input.emit(event);
      return;
    }
    const approval = approvalResultOf(part.output);
    if (!approval) {
      this.input.emit(toolResultEventOf({ toolCallId, output: part.output }));
      return;
    }
    this.input.emit({
      type: 'approval_required',
      toolCallId,
      name: toolName,
      input: part.input,
      approvalToken: this.input.issueApproval({ toolCallId, command: approval.command }),
      command: approval.command,
      risk: approval.risk,
      reason: approval.reason,
    });
  }

  private finish(part: StreamPart): void {
    const usage = (part.totalUsage ?? {}) as { inputTokens?: unknown; outputTokens?: unknown };
    this.input.emit({
      type: 'usage',
      inputTokens: numberOf(usage.inputTokens),
      outputTokens: numberOf(usage.outputTokens),
    });
    const capped = this.lastStepReason === 'tool-calls' && this.steps >= MAX_TOOL_STEPS;
    this.input.emit({
      type: 'finish',
      reason: capped ? STEP_LIMIT_REASON : String(part.finishReason ?? ''),
    });
  }
}

/** Run one chat turn, emitting `ai` events; resolves when the turn has ended, however it ended. */
export async function runAiTurn(input: AiTurnInput): Promise<void> {
  const fold = new TurnFold(input);
  try {
    const result = streamText({
      model: input.model,
      system: SYSTEM_PROMPT,
      messages: input.messages,
      // The registry tools win a name clash; none is called plan or present (ui-tools.test.ts).
      tools: { ...uiTools(), ...input.tools },
      stopWhen: [isStepCount(MAX_TOOL_STEPS), stopOnApproval],
      maxOutputTokens: input.maxOutputTokens ?? DEFAULT_MAX_OUTPUT_TOKENS,
      // The customer's provider decides when to back off; a retry here would hide a rate limit from the page.
      maxRetries: 0,
      abortSignal: input.abortSignal,
    });
    for await (const part of result.fullStream) {
      if (input.abortSignal?.aborted) break;
      fold.part(part as StreamPart);
    }
  } catch (error) {
    if (!input.abortSignal?.aborted) input.emit(errorEvent(error));
  }
}

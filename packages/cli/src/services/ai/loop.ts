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
 * tools (tools.ts) from the verified session and passes them in.
 *
 * This module also holds the two in-process stores the mode and approval routes write to
 * ({@link AiConversationStore}, {@link AiApprovalLedger}); both are RAM only and keyed by the
 * verified principal, so one user can never read or redeem another's conversation.
 */

import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import { getMcpTool } from '@rediacc/shared/mcp/registry';
import {
  APICallError,
  isStepCount,
  type LanguageModel,
  type ModelMessage,
  streamText,
  type ToolSet,
} from 'ai';
import type { AiApprovalSubmit, AiApprovalVerdict, AiMode } from '../serve/ai-routes.js';
import type { SessionPrincipal } from '../serve/sessions.js';
import { aiEventOfToolResult, stopOnApproval } from './tools.js';
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
  'You operate infrastructure for the user through the tools offered, which run rdc commands.',
  'Call a tool only when the request needs it, and keep answers short.',
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
  /** Called for an `approval_required` event, so the approval ledger can expect its answer. */
  onApprovalRequired?: (event: Extract<AiEvent, { type: 'approval_required' }>) => void;
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
    const event = aiEventOfToolResult({
      toolCallId: String(part.toolCallId),
      toolName: String(part.toolName),
      input: part.input,
      output: part.output,
    });
    this.input.emit(event);
    if (event.type === 'approval_required') this.input.onApprovalRequired?.(event);
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
      tools: input.tools,
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

/** The mode a conversation starts in (D4 of PLAN-console-ai-assistant): every action asks. */
const DEFAULT_MODE: AiMode = 'ask';

const keyOf = (principal: SessionPrincipal, conversationId: string): string =>
  `${principal.orgId}\u0000${principal.userId}\u0000${conversationId}`;

/** The autonomy mode of each conversation, per verified principal. */
export class AiConversationStore {
  private readonly modes = new Map<string, AiMode>();

  set(principal: SessionPrincipal, conversationId: string, mode: AiMode): void {
    this.modes.set(keyOf(principal, conversationId), mode);
  }

  get(principal: SessionPrincipal, conversationId: string): AiMode {
    return this.modes.get(keyOf(principal, conversationId)) ?? DEFAULT_MODE;
  }
}

/** How long a pending approval waits for its answer. */
const APPROVAL_TTL_MS = 15 * 60 * 1000;

export const AI_APPROVAL_UNKNOWN = 'AI_APPROVAL_UNKNOWN';
export const AI_APPROVAL_COMMAND_MISMATCH = 'AI_APPROVAL_COMMAND_MISMATCH';

interface PendingApproval {
  pathKey: string;
  expiresAtMs: number;
}

/**
 * The approvals a turn asked for, single use. An answer redeems exactly the (principal,
 * conversation, tool call) the loop ended a turn on, and only for the command that call named.
 */
export class AiApprovalLedger {
  private readonly pending = new Map<string, PendingApproval>();

  constructor(private readonly now: () => number = Date.now) {}

  /** Record that `toolName`'s call `toolCallId` of this conversation waits for an answer. */
  expect(
    principal: SessionPrincipal,
    conversationId: string,
    event: Extract<AiEvent, { type: 'approval_required' }>
  ): void {
    const now = this.now();
    for (const [key, entry] of this.pending) if (entry.expiresAtMs <= now) this.pending.delete(key);
    const pathKey = getMcpTool(event.name)?.command;
    if (pathKey === undefined) return;
    this.pending.set(`${keyOf(principal, conversationId)}\u0000${event.toolCallId}`, {
      pathKey,
      expiresAtMs: now + APPROVAL_TTL_MS,
    });
  }

  submit(answer: AiApprovalSubmit): Promise<AiApprovalVerdict> {
    const key = `${keyOf(answer.principal, answer.conversationId)}\u0000${answer.toolCallId}`;
    const entry = this.pending.get(key);
    if (!entry || entry.expiresAtMs <= this.now()) {
      this.pending.delete(key);
      return Promise.resolve({
        ok: false,
        status: 404,
        code: AI_APPROVAL_UNKNOWN,
        message: 'No approval is pending for this tool call.',
      });
    }
    if (entry.pathKey !== answer.command.pathKey) {
      return Promise.resolve({
        ok: false,
        status: 409,
        code: AI_APPROVAL_COMMAND_MISMATCH,
        message: 'The answer names another command than the one the model asked to run.',
      });
    }
    this.pending.delete(key);
    return Promise.resolve({ ok: true });
  }
}

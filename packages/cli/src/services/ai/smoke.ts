/**
 * Tool-calling smoke (D12 and AP8 of PLAN-console-ai-providers): the test the
 * settings page runs after a profile is saved.
 *
 * One turn offers a single tool, `echo_nonce`, and asks the model to call it
 * with a fresh random nonce and then answer. The smoke passes only when the
 * model calls `echo_nonce` with that nonce and streams a final message after
 * the tool result. A provider error fails it with the provider's HTTP status
 * and message; a model that skips the tool, sends another value or stops
 * without a final message fails it with a reason naming which. The result is
 * returned to the caller, never stored.
 */
import { randomBytes } from 'node:crypto';
import type { Profile } from '@rediacc/shared/ai';
import { APICallError, isStepCount, jsonSchema, type LanguageModel, streamText, tool } from 'ai';
import {
  createProviderModel,
  type ProviderModelOptions,
  ProviderProfileError,
} from './provider.js';

export const SMOKE_TOOL_NAME = 'echo_nonce';

/** Output cap of the smoke turn: a tool call and one short sentence. */
const SMOKE_MAX_OUTPUT_TOKENS = 512;

export type SmokeFailureReason =
  | 'profile-refused'
  | 'provider-error'
  | 'no-tool-call'
  | 'wrong-nonce'
  | 'no-final-message';

/** What the turn showed the endpoint can do, whatever the verdict. */
export interface SmokeObserved {
  /** The model called a tool. */
  tools: boolean;
  /** Text or tool input arrived as incremental deltas. */
  streaming: boolean;
}

export type SmokeResult =
  | { ok: true; latencyMs: number; observed: SmokeObserved }
  | {
      ok: false;
      reason: SmokeFailureReason;
      message: string;
      /** The provider's HTTP status, on a provider error that carried one. */
      status?: number;
      latencyMs: number;
      observed: SmokeObserved;
    };

export interface SmokeOptions {
  /** The value the model must echo; a fresh random one when omitted. */
  nonce?: string;
  abortSignal?: AbortSignal;
  /** Clock for the latency figure. */
  now?: () => number;
}

interface SmokeFailure {
  reason: SmokeFailureReason;
  message: string;
  status?: number;
}

/** What the turn's stream showed, folded part by part. */
interface TurnState {
  observed: SmokeObserved;
  /** The `nonce` input of every echo_nonce call. */
  echoed: unknown[];
  toolResultSeen: boolean;
  /** Text streamed after the tool result. */
  finalText: string;
  error: unknown;
}

type StreamPart = { type: string; [key: string]: unknown };

function newNonce(): string {
  return `n-${randomBytes(8).toString('hex')}`;
}

function systemPrompt(nonce: string): string {
  return [
    'This is a connectivity test of a tool-calling endpoint.',
    `Call the ${SMOKE_TOOL_NAME} tool exactly once with nonce "${nonce}".`,
    'After the tool result arrives, reply with one short sentence.',
  ].join(' ');
}

function failureOf(error: unknown): { message: string; status?: number } {
  if (APICallError.isInstance(error)) {
    return { message: error.message, status: error.statusCode };
  }
  return { message: error instanceof Error ? error.message : String(error) };
}

function observe(state: TurnState, part: StreamPart): void {
  switch (part.type) {
    case 'text-delta':
      state.observed.streaming = true;
      if (state.toolResultSeen) state.finalText += String(part.text);
      break;
    case 'tool-input-delta':
      state.observed.streaming = true;
      break;
    case 'tool-call':
      state.observed.tools = true;
      if (part.toolName === SMOKE_TOOL_NAME) {
        state.echoed.push((part.input as { nonce?: unknown } | undefined)?.nonce);
      }
      break;
    case 'tool-result':
      state.toolResultSeen = true;
      break;
    case 'error':
      state.error ??= part.error;
      break;
    default:
      break;
  }
}

/** The verdict of a finished turn: the first missing piece in turn order, or null on a pass. */
function verdictOf(state: TurnState, nonce: string): SmokeFailure | null {
  if (state.error !== undefined) return { reason: 'provider-error', ...failureOf(state.error) };
  if (state.echoed.length === 0) {
    return { reason: 'no-tool-call', message: `the model did not call ${SMOKE_TOOL_NAME}` };
  }
  // Every call must carry the nonce: a wrong value beside the right one is still a model that cannot repeat what it was given.
  if (!state.echoed.every((echoed) => echoed === nonce)) {
    return {
      reason: 'wrong-nonce',
      message: `the model called ${SMOKE_TOOL_NAME} without the nonce it was given`,
    };
  }
  if (state.finalText.trim() === '') {
    return {
      reason: 'no-final-message',
      message: 'the model streamed no final message after the tool result',
    };
  }
  return null;
}

const echoNonce = tool({
  description: 'Echo the nonce back to the caller.',
  inputSchema: jsonSchema<{ nonce: string }>({
    type: 'object',
    properties: { nonce: { type: 'string' } },
    required: ['nonce'],
    additionalProperties: false,
  }),
  execute: ({ nonce }) => ({ nonce }),
});

/** Run the smoke turn against an already built model. */
export async function runSmoke(
  model: LanguageModel,
  options: SmokeOptions = {}
): Promise<SmokeResult> {
  const nonce = options.nonce ?? newNonce();
  const now = options.now ?? Date.now;
  const started = now();
  const state: TurnState = {
    observed: { tools: false, streaming: false },
    echoed: [],
    toolResultSeen: false,
    finalText: '',
    error: undefined,
  };

  try {
    const result = streamText({
      model,
      system: systemPrompt(nonce),
      prompt: `Run the test now: call ${SMOKE_TOOL_NAME} with nonce "${nonce}".`,
      tools: { [SMOKE_TOOL_NAME]: echoNonce },
      // The tool call, then the final message.
      stopWhen: isStepCount(2),
      maxOutputTokens: SMOKE_MAX_OUTPUT_TOKENS,
      // A smoke reports the first answer; a retry would hide a rate limit or an overload.
      maxRetries: 0,
      abortSignal: options.abortSignal,
    });
    for await (const part of result.fullStream) observe(state, part as StreamPart);
  } catch (error) {
    state.error ??= error;
  }

  const latencyMs = now() - started;
  const failure = verdictOf(state, nonce);
  if (failure === null) return { ok: true, latencyMs, observed: state.observed };
  return {
    ok: false,
    reason: failure.reason,
    message: failure.message,
    ...(failure.status === undefined ? {} : { status: failure.status }),
    latencyMs,
    observed: state.observed,
  };
}

/** Build the model of `profile` and run the smoke; a refused profile fails without a request. */
export async function smokeProfile(
  profile: Profile,
  options: SmokeOptions & ProviderModelOptions = {}
): Promise<SmokeResult> {
  let model: LanguageModel;
  try {
    model = createProviderModel(profile, { fetch: options.fetch });
  } catch (error) {
    if (!(error instanceof ProviderProfileError)) throw error;
    return {
      ok: false,
      reason: 'profile-refused',
      message: error.message,
      latencyMs: 0,
      observed: { tools: false, streaming: false },
    };
  }
  return runSmoke(model, options);
}

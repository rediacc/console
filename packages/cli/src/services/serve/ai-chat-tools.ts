/**
 * The chat half of ai-routes.ts: the tool-call jobs, the per-turn tool host, the tool set a turn hands the model, the grant open and the smoke refusal. Moved out so the route module stays under the line budget; the routes themselves and their request schemas stay in ai-routes.ts.
 */

import { type AiConfigs, type Profile } from '@rediacc/shared/ai';
import { getCommand } from '@rediacc/shared/cli-contract';
import {
  type AiApprovalCommand,
  type AiEvent,
  type StreamLine,
} from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { listProxyTools } from '@rediacc/shared/mcp/registry';
import { jsonSchema, type LanguageModel, type ModelMessage, type ToolSet, tool } from 'ai';
import { ProviderProfileError } from '../ai/provider.js';
import type { TranscriptTurn } from '../ai/recorder.js';
import { type SmokeResult } from '../ai/smoke.js';
import {
  type AiToolContext,
  type AiToolGate,
  type AiToolResult,
  requestOf,
  runAiTool,
} from '../ai/tools.js';
import { fenceUntrusted } from '../ai/untrusted.js';
import type { ForensicsTicket } from '../forensics/client.js';
import {
  type AgentGrantHandle,
  AgentSessionRefused,
  AgentSessionUnavailable,
} from './agent-grant-session.js';
import type { ChatRequest } from './ai-request-schemas.js';
import type { AiChatRecording } from './ai-route-types.js';
import { type BusyCounter } from './busy.js';
import type { ServeDeps } from './deps.js';
import { dispatcher, HandedBack } from './mcp-call-dispatch.js';
import { globRefusal, scopeAdmitsTool } from './mcp-call-scope.js';
import type { SessionPrincipal } from './sessions.js';

/** Refusal code of the chat route when the request's agent grant cannot be opened. */
export const AI_GRANT_UNAVAILABLE = 'AI_GRANT_UNAVAILABLE';

/** How long one tool call may run before its turn gives up on it (a started job is handed back sooner). */
const TOOL_WINDOW_MS = 5 * 60 * 1000;

export const NO_GRANT_OVERRIDES = { allowGrandRepos: false, allowClusterOps: false } as const;

/** One chat's verified session: who the tools run as, and the config and scope they run in. */
export interface ChatSession {
  handle: AgentGrantHandle;
  sources: AiConfigs;
}

/** The model a chat runs on, and the profile it came from (the judge reads the profile). */
export interface BuiltModel {
  model: LanguageModel;
  profile: Profile;
}

/** A session, or the refusal that answers the request instead. */
export type OpenedChat =
  | { session: ChatSession }
  | { refusal: { error: string; code: string }; status: 400 | 403 | 503 };

/** A request id the job machinery accepts, from a conversation and a model-chosen tool call id. */
export function toolRequestId(conversationId: string, toolCallId: string): string {
  return `${conversationId}:${toolCallId}`.replaceAll(/[^A-Za-z0-9_.:-]/g, '_').slice(0, 200);
}

/** `work`, or a rejection when `signal` aborts first; the work itself keeps running to its own end. */
function untilAborted<T>(work: Promise<T>, signal: AbortSignal | undefined): Promise<T> {
  if (!signal) return work;
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new Error('The chat was cancelled.'));
    if (signal.aborted) abort();
    signal.addEventListener('abort', abort, { once: true });
    work.then(resolve, reject).finally(() => signal.removeEventListener('abort', abort));
  });
}

/** How one turn is recorded: its opening messages before the model runs, its reply after; neither rejects. */
export interface TurnRecord {
  opening: () => Promise<void>;
  reply: (text: string, model: string | undefined) => Promise<void>;
}

/** The record of a turn that is not recorded. */
const UNRECORDED: TurnRecord = {
  opening: () => Promise.resolve(),
  reply: () => Promise.resolve(),
};

/** How a chat on the caller's own session records its turn; a no-op for one that records none. */
export function turnRecordOf(
  recording: AiChatRecording | undefined,
  principal: SessionPrincipal,
  config: RdcConfig,
  body: ChatRequest,
  configSessionId: string | undefined
): TurnRecord {
  if (!recording || body.grant) return UNRECORDED;
  const key = recording.keyOf(principal, config, configSessionId);
  if (typeof key === 'string') {
    recording.onUnrecorded?.(key, body.conversationId);
    return UNRECORDED;
  }
  const turn: TranscriptTurn = {
    principal,
    conversationId: body.conversationId,
    messages: body.messages,
    key,
  };
  return {
    opening: () => recording.transcripts.opening(turn),
    reply: (text, model) => recording.transcripts.reply(turn, text, model),
  };
}

/** The text an assistant reply streamed, folded from the turn's events. */
export function replyFold() {
  let text = '';
  return {
    take(event: AiEvent): void {
      if (event.type === 'text_delta') text += event.text;
    },
    text: () => text,
  };
}

/** A machine job a tool call started. */
export interface StartedJob {
  jobId: string;
  machine: string;
}

/**
 * The machine jobs of one tool call, cancelled when the chat aborts. Once the call settles without
 * an abort, a job it handed back is the user's to follow and is never cancelled; once the chat has
 * aborted, every job the still-running command announces is cancelled on arrival.
 */
class ToolCallJobs {
  private readonly jobs: StartedJob[] = [];
  /** Empty while the call runs, then `aborted` or `settled`, whichever came first. */
  private readonly phase = new Set<'aborted' | 'settled'>();

  constructor(
    signal: AbortSignal | undefined,
    private readonly cancel: (job: StartedJob) => void
  ) {
    if (!signal) return;
    const abort = () => {
      if (this.phase.size > 0) return;
      this.phase.add('aborted');
      for (const job of this.jobs) this.cancel(job);
    };
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, { once: true });
  }

  started(jobId: string, machine: string | undefined): void {
    if (this.phase.has('settled') || !machine) return;
    const job = { jobId, machine };
    this.jobs.push(job);
    if (this.phase.has('aborted')) this.cancel(job);
  }

  /** The call answered; without an abort its jobs are no longer the turn's to cancel. */
  settled(): void {
    if (this.phase.size === 0) this.phase.add('settled');
  }
}

export interface ChatToolHost {
  deps: ServeDeps;
  busy: BusyCounter;
  session: ChatSession;
  conversationId: string;
  forward: (line: StreamLine) => void;
  gate: AiToolGate;
  /** Cancel one job of an aborted chat: authorized and audited as `job cancel`; never rejects. */
  cancelJob: (job: StartedJob) => void;
  /** The turn's single-use forensics read ticket, shared by every tool call of the turn (D8). */
  forensicsTicket?: ForensicsTicket;
}

/** The argv the judge reads: the path, the positionals in order, then each option as `--name value`. */
export function judgeArgvOf(command: AiApprovalCommand): string[] {
  const argv = [...command.pathKey.split(' ')];
  for (const value of Object.values(command.positionals)) argv.push(String(value));
  for (const [name, value] of Object.entries(command.params)) {
    if (value === true) argv.push(`--${name}`);
    else if (value !== false && value !== undefined) argv.push(`--${name}`, String(value));
  }
  return argv;
}

type RegistryTool = ReturnType<typeof listProxyTools>[number];

/** One model-requested call: the grant's globs, then `runAiTool` (prepare, decide, dispatch with audit). */
async function runChatTool(
  host: ChatToolHost,
  entry: RegistryTool,
  input: Record<string, unknown>,
  call: { toolCallId: string; abortSignal?: AbortSignal }
): Promise<AiToolResult> {
  const { handle } = host.session;
  const command = getCommand(entry.command);
  if (!command) return await runAiTool(unrunnable(host), entry, input, call);
  const request = requestOf(entry, command, input);
  const outside = await globRefusal(handle.scope, command, request, handle.config);
  if (outside) return { status: 'refused', code: 'POLICY_DENIED', reason: outside };
  const jobs = new ToolCallJobs(call.abortSignal, host.cancelJob);
  const dispatch = dispatcher(
    {
      deps: host.deps,
      busy: host.busy,
      handle,
      requestId: toolRequestId(host.conversationId, call.toolCallId),
      windowMs: TOOL_WINDOW_MS,
      onJobStarted: (jobId, machine) => jobs.started(jobId, machine),
      ...(host.forensicsTicket ? { forensicsTicket: host.forensicsTicket } : {}),
    },
    request
  );
  try {
    return await runAiTool(
      {
        ...unrunnable(host),
        run: (run) => untilAborted(dispatch(run), call.abortSignal),
      },
      entry,
      input,
      call
    );
  } catch (error) {
    if (!(error instanceof HandedBack)) throw error;
    const where = error.machine ? ` on ${error.machine}` : '';
    return {
      status: 'ok',
      exitCode: 0,
      output: fenceUntrusted(
        `The command started job ${error.jobId}${where} and keeps running; follow it with the job tools.`
      ).text,
    };
  } finally {
    jobs.settled();
  }
}

/** The tool context minus a dispatcher: its `run` refuses, so a call that has none can never dispatch. */
function unrunnable(host: ChatToolHost): AiToolContext {
  const { handle } = host.session;
  return {
    principal: handle.principal,
    config: handle.config,
    // The agent principal: set here from the verified session, never from the request body.
    agentGrant: handle.overrides,
    authorize: host.deps.authorize,
    run: () => Promise.reject(new Error('This tool call has no dispatcher.')),
    onEvent: (toolCallId, event) => host.forward({ kind: 'event', event, toolCallId }),
    gate: host.gate,
  };
}

/** The AI SDK tool set of one chat: the proxy-surface registry tools the session's scope admits. */
export function chatTools(host: ChatToolHost): ToolSet {
  const tools: ToolSet = {};
  for (const entry of listProxyTools()) {
    if (!scopeAdmitsTool(host.session.handle.scope, entry)) continue;
    tools[entry.name] = tool({
      description: entry.description,
      inputSchema: jsonSchema<Record<string, unknown>>(entry.inputSchema),
      execute: (input, options) =>
        runChatTool(host, entry, input, {
          toolCallId: options.toolCallId,
          ...(options.abortSignal ? { abortSignal: options.abortSignal } : {}),
        }),
    });
  }
  return tools;
}

export function messagesOf(body: {
  messages: { role: 'user' | 'assistant'; content: string }[];
}): ModelMessage[] {
  return body.messages.map((m) => ({ role: m.role, content: m.content }));
}

/** The smoke result of a profile the adapter refused to build, in the smoke's own shape. */
export function refusedSmoke(error: ProviderProfileError): SmokeResult {
  return {
    ok: false,
    reason: 'profile-refused',
    message: error.message,
    latencyMs: 0,
    observed: { tools: false, streaming: false },
  };
}

/** The grant session of a grant-bound chat, or the refusal that answers it. */
export async function openGrant(
  deps: ServeDeps,
  grant: { grantId: string; secret: string }
): Promise<OpenedChat> {
  if (!deps.agentGrants) {
    return {
      status: 400,
      refusal: { error: 'This executor serves no agent grants.', code: AI_GRANT_UNAVAILABLE },
    };
  }
  try {
    const handle = await deps.agentGrants.acquire(grant.grantId, grant.secret);
    return { session: { handle, sources: { team: handle.config.ai } } };
  } catch (error) {
    if (error instanceof AgentSessionRefused) {
      return { status: 403, refusal: { error: error.message, code: AI_GRANT_UNAVAILABLE } };
    }
    if (error instanceof AgentSessionUnavailable) {
      return { status: 503, refusal: { error: error.message, code: AI_GRANT_UNAVAILABLE } };
    }
    throw error;
  }
}

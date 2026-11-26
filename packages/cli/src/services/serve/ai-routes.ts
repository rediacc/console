/**
 * The executor's AI mode and approval routes (AI5 of agent/plans/PLAN-console-ai-assistant.md, D4
 * and D6). The account Worker forwards both from its session routes (`AI_EXECUTOR_ROUTES` in
 * private/account/src/routes/console-ai.ts) under the caller's executor bearer and config session.
 *
 * `POST /v1/ai/mode` changes a conversation's autonomy mode. The executor enforces the mode, so it
 * hears the change first and refuses a mode the org or team policy disabled (`aiModesDisabled`,
 * read from the same effective policy every command is authorized against); the account stores the
 * mode only once this route accepted it.
 *
 * `POST /v1/ai/approval` takes the user's answer to one `approval_required` event. The account ran
 * plan 2's server step-up before forwarding an approval it judged destructive or grand, and names
 * the method in `stepUpMethod`. The executor does not take that judgment on trust: it resolves the
 * command's target from its own config, and an approval of a destructive command or of a grand-repo
 * target without a step-up method is refused here, whatever the browser claimed about `grand`. The
 * single-use token itself is redeemed by the approval ledger (`AiApprovals`, services/ai/approvals.ts),
 * bound to the principal, the conversation, the tool call and the argv hash; every answer is
 * audited (approval-audit.ts), and an approval whose record cannot be delivered is withdrawn. An
 * approval of a `caution` command may ask to be remembered: an exact allow rule for that argv in that
 * conversation, never a pattern, and never for a destructive or grand-repo command.
 *
 * `POST /v1/ai/chat` runs one chat turn (AP7 of agent/plans/PLAN-console-ai-providers.md) and
 * answers NDJSON: `ai` lines from the loop (services/ai/loop.ts) and the renet `event` lines of each
 * tool call, tagged with its call id. The profile is resolved from the session's configs (D3), and
 * every tool call runs under an agent principal the route sets, never one the body names (D9), then
 * through the conversation's autonomy gate (services/ai/autonomy.ts), the Auto-mode judge included. A
 * chat bound to an agent grant (`grant` in the body) takes the grant's session: its config, its
 * opt-ins and its scope, through the same grant sessions `POST /v1/mcp/call` uses. The client
 * leaving aborts the provider stream and every running tool, and cancels each machine job a tool
 * call of the turn started (`renet job cancel`, authorized and audited as `job cancel`). A command
 * runs in-process between its machine calls, where nothing interrupts it: a job it starts after the
 * abort is cancelled as soon as it is announced, so it may run for that moment.
 *
 * A chat on the caller's own session is recorded (services/ai/recorder.ts `AiTranscripts`): the
 * turn's new messages are sealed under the session key and posted before the model runs, because
 * the account's approval route answers only in a conversation whose row they created, and the
 * reply is posted once the turn ends. A grant-bound chat belongs to no user and is not recorded.
 *
 * `POST /v1/ai/transcribe?profile=<name>` takes one recording the account relays unread (AI10, D12)
 * and answers `{ text }` from the resolved profile's OpenAI-compatible transcription endpoint. An
 * Anthropic Messages or Rediacc tier profile has none and is refused with
 * `AI_TRANSCRIBE_UNSUPPORTED`; the audio is held only for the one provider call.
 *
 * `POST /v1/ai/test` runs the tool-calling smoke of the resolved profile (D12) and answers its
 * verdict as JSON; nothing is stored.
 */

import { type AiConfigs, isRediaccProfile, type Profile, resolveProfile } from '@rediacc/shared/ai';
import { STEP_UP_METHODS } from '@rediacc/shared/auth';
import { getCommand } from '@rediacc/shared/cli-contract';
import {
  type AiApprovalCommand,
  type AiEvent,
  PROXY_ROUTES,
  type StreamLine,
} from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { type LanguageModel } from 'ai';
import type { Context, Hono } from 'hono';
import { streamText } from 'hono/streaming';
import { z } from 'zod';
import { auditJudgment, auditModeChange, auditRefusal } from '../ai/approval-audit.js';
import type { AiApprovals } from '../ai/approvals.js';
import { autonomyHold, effectiveMode } from '../ai/autonomy.js';
import {
  buildJudgeInput,
  createJudgeTally,
  type JudgeInput,
  type JudgeVerdict,
  judgeInAutoMode,
  judgeModelOf,
  runJudge,
} from '../ai/judge.js';
import { runAiTurn } from '../ai/loop.js';
import {
  createProviderModel,
  type ProviderModelOptions,
  ProviderProfileError,
} from '../ai/provider.js';
import type { AiTranscripts, TranscriptKey, TranscriptTurn } from '../ai/recorder.js';
import { runSmoke } from '../ai/smoke.js';
import { type AiGateCall, type AiToolGate } from '../ai/tools.js';
import {
  AI_TRANSCRIBE_FAILED,
  AI_TRANSCRIBE_UNSUPPORTED,
  MAX_TRANSCRIBE_BYTES,
  supportsTranscription,
  TRANSCRIBE_AUDIO_TYPES,
  TranscriptionFailed,
  transcribeAudio,
} from '../ai/transcribe.js';
import { ForensicsTicket } from '../forensics/client.js';
import { type AgentGrantHandle } from './agent-grant-session.js';
import {
  BadAiRequest,
  disabledModesFor,
  judgeApproval,
  recordApproval,
  recordRefusal,
} from './ai-approval.js';
import {
  type BuiltModel,
  type ChatSession,
  type ChatToolHost,
  chatTools,
  judgeArgvOf,
  messagesOf,
  NO_GRANT_OVERRIDES,
  type OpenedChat,
  openGrant,
  refusedSmoke,
  type StartedJob,
  type TurnRecord,
  toolRequestId,
  UNRECORDED,
} from './ai-chat-tools.js';
import {
  type ChatRequest,
  ChatRequestSchema,
  IdSchema,
  TestRequestSchema,
} from './ai-request-schemas.js';
import { type BusyCounter, createBusyCounter } from './busy.js';
import type { ExecutorAuditEvent, ServeDeps } from './deps.js';
import { cancelOnMachine, type JobRouteHelpers } from './job-routes.js';
import type { SessionPrincipal } from './sessions.js';

/** The issue text when the schema names none. */
const UNNAMED_ISSUE = 'invalid';

/** Route paths; the account Worker's `AI_EXECUTOR_ROUTES` names the same two. */
export const AI_ROUTES = {
  mode: '/v1/ai/mode',
  approval: '/v1/ai/approval',
  chat: PROXY_ROUTES.aiChat,
  test: PROXY_ROUTES.aiTest,
  transcribe: '/v1/ai/transcribe',
} as const;

/** A `?profile=` of the transcription route, as the chat body's `profile` is checked. */
const TranscribeProfileSchema = z.string().min(1).max(128);

function audioTypeOf(header: string | undefined) {
  const type = (header ?? '').split(';')[0]?.trim().toLowerCase() ?? '';
  return TRANSCRIBE_AUDIO_TYPES.find((known) => known === type);
}

interface Recording {
  type: (typeof TRANSCRIBE_AUDIO_TYPES)[number];
  profile: string | undefined;
  audio: Uint8Array<ArrayBuffer>;
}

/** The answer to a profile the transcription guard refused or a provider refusal; anything else is rethrown. */
function transcriptionRefusal(error: unknown): { body: Record<string, string>; status: 422 | 502 } {
  if (error instanceof ProviderProfileError) {
    return { status: 422, body: { error: error.message, code: AI_PROFILE_UNRESOLVED } };
  }
  if (!(error instanceof TranscriptionFailed)) throw error;
  return { status: 502, body: { error: error.message, code: AI_TRANSCRIBE_FAILED } };
}

/** The recording of a transcription request, or the refusal of a malformed one. */
async function readRecording(
  c: Context
): Promise<Recording | { refusal: { error: string; code?: string }; status: 413 | 415 }> {
  const type = audioTypeOf(c.req.header('content-type'));
  if (!type) {
    return {
      status: 415,
      refusal: {
        error: `Transcription takes ${TRANSCRIBE_AUDIO_TYPES.join(', ')}`,
        code: AI_TRANSCRIBE_UNSUPPORTED,
      },
    };
  }
  const raw = c.req.query('profile');
  const name = raw === undefined ? undefined : TranscribeProfileSchema.safeParse(raw);
  if (name && !name.success) throw new BadAiRequest('Malformed AI request: profile: invalid');
  const audio = new Uint8Array(await c.req.arrayBuffer());
  if (audio.byteLength === 0 || audio.byteLength > MAX_TRANSCRIBE_BYTES) {
    return { status: 413, refusal: { error: `A recording is 1 to ${MAX_TRANSCRIBE_BYTES} bytes` } };
  }
  return { type, profile: name?.data, audio };
}

const AI_MODES = ['ask', 'auto', 'skip'] as const;
export type AiMode = (typeof AI_MODES)[number];

/** Refusal codes these routes answer with. */
export const AI_MODE_DISABLED = 'AI_MODE_DISABLED';

const ModeRequestSchema = z.strictObject({
  conversationId: IdSchema,
  mode: z.enum(AI_MODES),
});

const ApprovedCommandSchema = z.strictObject({
  pathKey: z.string().min(1).max(256),
  params: z.record(z.string(), z.unknown()).default({}),
  positionals: z.record(z.string(), z.unknown()).default({}),
});

/** What the account forwards: its own `grand` input is not among the fields, the executor decides it. */
const ApprovalRequestSchema = z.strictObject({
  conversationId: IdSchema,
  toolCallId: z.string().min(1).max(256),
  approvalToken: z.string().min(1).max(4096),
  decision: z.enum(['approve', 'reject']),
  command: ApprovedCommandSchema,
  stepUpMethod: z.enum(STEP_UP_METHODS).nullable(),
  /** Remember an exact allow rule for this argv in this conversation (a `caution` command only). */
  remember: z.boolean().optional(),
});

type ApprovalRequest = z.infer<typeof ApprovalRequestSchema>;

export type { ApprovalRequest };

/** Where the loop keeps each conversation's mode (D4) and exact allow rules; the autonomy gate reads both. */
interface AiConversationModes {
  set(principal: SessionPrincipal, conversationId: string, mode: AiMode): void;
  get(principal: SessionPrincipal, conversationId: string): AiMode;
  allowExact(principal: SessionPrincipal, conversationId: string, command: AiApprovalCommand): void;
  allowsExact(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): boolean;
}

/** One approval answer as the executor verified it. */
export interface AiApprovalSubmit extends Omit<ApprovalRequest, 'stepUpMethod' | 'remember'> {
  principal: SessionPrincipal;
  stepUpMethod: ApprovalRequest['stepUpMethod'];
  /** The command is destructive and the run is not a preview. */
  destructive: boolean;
  /** The executor resolved the target to a grand repo (or an unresolved one) off the ops VMs. */
  grand: boolean;
}

export type AiApprovalVerdict =
  | { ok: true }
  | { ok: false; status: 403 | 404 | 409; code: string; message: string };

/** The chat host's own seams; every one has a production default. */
export interface AiChatDeps {
  /** The AI SDK model of a profile; `createProviderModel` when absent. Tests pass a mock model. */
  createModel?: (profile: Profile, options?: ProviderModelOptions) => LanguageModel;
  /**
   * The profile sources of a request, team over shared (D3). Absent: the session's own config is the
   * only source. The container tier lends the second config when it loads both.
   */
  aiConfigs?: (
    principal: SessionPrincipal,
    config: RdcConfig,
    configSessionId?: string
  ) => Promise<AiConfigs>;
  /** Counts a running tool as a running dispatch, as `/v1/command` does. */
  busy?: BusyCounter;
  /** The per-turn output token cap when the profile names none; the loop's default when absent. */
  maxOutputTokens?: number;
  /** The Auto-mode judge of a profile; `runJudge` on the profile's judge model when absent. */
  judge?: (profile: Profile, input: JudgeInput) => Promise<JudgeVerdict>;
  /** Records each turn of a chat on the caller's own session; absent, no turn is recorded. */
  recording?: AiChatRecording;
  /** `renet job cancel` of one job, run inside the turn's config scope; `cancelOnMachine` when absent. */
  cancelJob?: (machine: string, jobId: string) => Promise<unknown>;
  /** The fetch provider transcription goes out through, behind the profile guard; `fetch` when absent. */
  transcribeFetch?: typeof globalThis.fetch;
}

/** Where a chat's turns are recorded, and the session key each is sealed under. */
export interface AiChatRecording {
  transcripts: AiTranscripts;
  /** The key a turn of this session is sealed under, or why the session has none. */
  keyOf: (
    principal: SessionPrincipal,
    config: RdcConfig,
    configSessionId: string | undefined
  ) => TranscriptKey | string;
  /** Told why a turn was not recorded. */
  onUnrecorded?: (reason: string, conversationId: string) => void;
}

export interface AiRouteDeps {
  modes: AiConversationModes;
  approvals: AiApprovals;
  chat?: AiChatDeps;
}

/** Refusal codes of the chat and test routes. */
export const AI_PROFILE_UNRESOLVED = 'AI_PROFILE_UNRESOLVED';

export function registerAiRoutes(
  app: Hono,
  deps: ServeDeps,
  /** What server.ts lends these routes: the same helpers the job routes take. */
  helpers: JobRouteHelpers,
  ai: AiRouteDeps
): void {
  const chatBusy = createBusyCounter();
  const judgeTally = createJudgeTally();

  /** Authenticate, parse, and open the config of the request's session. */
  async function admit<T>(c: Context, schema: z.ZodType<T>) {
    const principal = await helpers.authenticate(c.req.header('authorization'));
    const parsed = schema.safeParse(await c.req.json().catch(() => null));
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      const where = issue?.path.length ? `${issue.path.join('.')}: ` : '';
      throw new BadAiRequest(`Malformed AI request: ${where}${issue?.message ?? UNNAMED_ISSUE}`);
    }
    const session = helpers.configSession(c.req.header('x-config-session'));
    if (session) deps.sessions.sessionForExec(principal, session);
    const config = await deps.loadConfig(principal, session);
    return { principal, body: parsed.data, config, configSessionId: session };
  }

  function refusal(c: Context, error: unknown) {
    if (error instanceof BadAiRequest) return c.json({ error: error.message }, 400);
    const { status, message, code } = helpers.statusFor(error);
    return c.json({ error: message, ...(code ? { code } : {}) }, status);
  }

  app.post(AI_ROUTES.mode, async (c) => {
    try {
      const { principal, body, config } = await admit(c, ModeRequestSchema);
      const disabled = disabledModesFor(config, principal);
      if ((disabled as readonly string[]).includes(body.mode)) {
        await auditRefusal(deps.audit, { principal, destructive: false });
        return c.json(
          {
            error: `The ${body.mode} mode is disabled by your organization's policy (aiModesDisabled).`,
            code: AI_MODE_DISABLED,
            disabled,
          },
          403
        );
      }
      const previous = ai.modes.get(principal, body.conversationId);
      ai.modes.set(principal, body.conversationId, body.mode);
      if (previous !== body.mode) {
        await auditModeChange(deps.audit, { principal, destructive: false, mode: body.mode });
      }
      return c.json({ conversationId: body.conversationId, mode: body.mode });
    } catch (error) {
      return refusal(c, error);
    }
  });

  app.post(AI_ROUTES.approval, async (c) => {
    try {
      const { principal, body, config } = await admit(c, ApprovalRequestSchema);
      const judged = await judgeApproval(body, helpers.requestScopedConfig(config));
      if ('refusal' in judged) {
        await recordRefusal(deps.audit, principal, body, judged.refusal);
        return c.json(judged.refusal, 403);
      }
      const { grand, destructive } = judged;

      const { remember, ...answer } = body;
      const verdict = await ai.approvals.submit({ ...answer, principal, destructive, grand });
      if (!verdict.ok) {
        return c.json({ error: verdict.message, code: verdict.code }, verdict.status);
      }
      await recordApproval(deps.audit, ai.approvals, principal, body, judged);
      if (remember && body.decision === 'approve' && !destructive && !grand) {
        ai.modes.allowExact(principal, body.conversationId, body.command);
      }
      return c.json(
        {
          conversationId: body.conversationId,
          toolCallId: body.toolCallId,
          decision: body.decision,
          stepUpMethod: body.stepUpMethod,
        },
        200,
        { 'Cache-Control': 'no-store' }
      );
    } catch (error) {
      return refusal(c, error);
    }
  });

  /** The chat's session: the grant's when the body names one, else the caller's own config. */
  async function openChat(
    principal: SessionPrincipal,
    config: RdcConfig,
    grant: ChatRequest['grant'],
    configSessionId: string | undefined
  ): Promise<OpenedChat> {
    if (grant) return await openGrant(deps, grant);
    const handle: AgentGrantHandle = {
      grantId: '',
      principal,
      scope: { readOnly: false },
      overrides: NO_GRANT_OVERRIDES,
      config: helpers.requestScopedConfig(config) ?? config,
    };
    const sources = await profileSources(principal, config, configSessionId);
    return { session: { handle, sources } };
  }

  async function profileSources(
    principal: SessionPrincipal,
    config: RdcConfig,
    configSessionId: string | undefined
  ): Promise<AiConfigs> {
    return (await ai.chat?.aiConfigs?.(principal, config, configSessionId)) ?? { team: config.ai };
  }

  /** The ids a Rediacc tier call is billed under: the authenticated person and the chat's conversation. */
  const rediaccOf = (
    principal: SessionPrincipal,
    conversationId: string
  ): ProviderModelOptions => ({
    rediacc: { userId: principal.userId, conversationId },
  });

  const modelOf = (profile: Profile, options: ProviderModelOptions): LanguageModel =>
    (ai.chat?.createModel ?? createProviderModel)(profile, options);

  /** The Auto-mode judge: the seam when given, else the profile's judge model. */
  const judgeOf = (profile: Profile, options: ProviderModelOptions) => (input: JudgeInput) => {
    if (ai.chat?.judge) return ai.chat.judge(profile, input);
    const createModel = ai.chat?.createModel;
    const judgeProfile = { ...profile, model: judgeModelOf(profile) };
    if (createModel) return runJudge(profile, input, { model: createModel(judgeProfile, options) });
    // A Rediacc tier profile carries no key and needs the ids; runJudge cannot supply them.
    if (isRediaccProfile(profile)) {
      return runJudge(profile, input, { model: createProviderModel(judgeProfile, options) });
    }
    return runJudge(profile, input);
  };

  /** The Auto-mode judge's verdict on one call the policy allowed; true for an allow. */
  async function judged(
    principal: SessionPrincipal,
    profile: Profile,
    body: ChatRequest,
    call: AiGateCall
  ): Promise<boolean> {
    const input = buildJudgeInput(messagesOf(body), {
      pathKey: call.command.pathKey,
      argv: judgeArgvOf(call.command),
      target: {
        ...(call.target.machine ? { machine: call.target.machine } : {}),
        ...(call.target.repo ? { repo: call.target.repo } : {}),
      },
      severity: call.entry.severity,
      decision: { allowed: true },
    });
    const judgment = await judgeInAutoMode({
      conversationId: `${principal.orgId}\u0000${principal.userId}\u0000${body.conversationId}`,
      input,
      judge: judgeOf(profile, rediaccOf(principal, body.conversationId)),
      tally: judgeTally,
      setAskMode: () => ai.modes.set(principal, body.conversationId, 'ask'),
    });
    await auditJudgment(deps.audit, {
      principal,
      requestId: toolRequestId(body.conversationId, call.toolCallId),
      call,
      judgment,
    });
    return judgment.verdict.verdict === 'allow';
  }

  /**
   * The autonomy gate of one turn: the conversation's mode as the policy admits it, the exact
   * allow rules, the judge in Auto mode, and the grants approved tokens left.
   */
  function chatGate(session: ChatSession, profile: Profile, body: ChatRequest): AiToolGate {
    const { principal, config } = session.handle;
    const { conversationId } = body;
    const disabled = disabledModesFor(config, principal);
    return {
      takeGrant: (command) => ai.approvals.takeGrant(principal, conversationId, command),
      hold: (call) =>
        autonomyHold({
          mode: effectiveMode(ai.modes.get(principal, conversationId), disabled),
          risk: call.risk,
          pathKey: call.command.pathKey,
          exactlyAllowed: ai.modes.allowsExact(principal, conversationId, call.command),
          judge: () => judged(principal, profile, body, call),
        }),
    };
  }

  /**
   * `renet job cancel` of one job an aborted chat started, as the cancel route runs it: authorized
   * for the session's principal, recorded as `started` before it runs (and skipped when that record
   * cannot be delivered), then recorded with its outcome.
   */
  async function cancelAudited(handle: AgentGrantHandle, job: StartedJob): Promise<void> {
    const { principal, config, overrides } = handle;
    const commandPath = 'job cancel';
    deps.authorize({
      principal,
      commandPath,
      config,
      machineName: job.machine,
      agentGrant: overrides,
    });
    const startedAt = Date.now();
    const event = (success: boolean, outcome?: 'started'): ExecutorAuditEvent => ({
      principal,
      commandPath,
      machineName: job.machine,
      params: { id: job.jobId },
      success,
      exitCode: success ? 0 : 1,
      durationMs: outcome ? 0 : Date.now() - startedAt,
      destructive: getCommand(commandPath)?.destructive ?? true,
      ...(outcome ? { outcome } : {}),
    });
    await deps.audit?.(event(true, 'started'));
    const cancel = ai.chat?.cancelJob ?? cancelOnMachine;
    const ok = await helpers
      .withRequestConfig(helpers.requestScopedConfig(config), () => cancel(job.machine, job.jobId))
      .then(
        () => true,
        () => false
      );
    await deps.audit?.(event(ok));
  }

  const chatHost = (
    session: ChatSession,
    conversationId: string,
    forward: ChatToolHost['forward'],
    gate: AiToolGate,
    forensicsTicket?: string
  ): ChatToolHost => ({
    ...(forensicsTicket ? { forensicsTicket: new ForensicsTicket(forensicsTicket) } : {}),
    deps,
    busy: ai.chat?.busy ?? chatBusy,
    session,
    conversationId,
    forward,
    gate,
    // The client has left, so a cancel that fails has nobody to answer; its audit record carries the outcome.
    cancelJob: (job) => {
      cancelAudited(session.handle, job).catch(() => undefined);
    },
  });

  /** The text an assistant reply streamed, folded from the turn's events. */
  function replyFold() {
    let text = '';
    return {
      take(event: AiEvent): void {
        if (event.type === 'text_delta') text += event.text;
      },
      text: () => text,
    };
  }

  /** Stream one turn as NDJSON; the client leaving aborts the provider stream and the running tools. */
  function streamChat(
    c: Context,
    built: BuiltModel,
    session: ChatSession,
    body: ChatRequest,
    record: TurnRecord
  ) {
    const { model, profile } = built;
    const abort = new AbortController();
    c.req.raw.signal.addEventListener('abort', () => abort.abort(), { once: true });
    const maxOutputTokens = profile.maxOutputTokens ?? ai.chat?.maxOutputTokens;
    return streamText(c, async (stream) => {
      stream.onAbort(() => abort.abort());
      const forward = (line: StreamLine) => {
        stream.write(`${JSON.stringify(line)}\n`).catch(() => undefined);
      };
      // Before the model runs: a held call is approvable only in a conversation the store holds.
      await record.opening();
      const reply = replyFold();
      const gate = chatGate(session, profile, body);
      await runAiTurn({
        model,
        tools: chatTools(
          chatHost(session, body.conversationId, forward, gate, body.forensicsTicket)
        ),
        messages: messagesOf(body),
        ...(maxOutputTokens ? { maxOutputTokens } : {}),
        abortSignal: abort.signal,
        emit: (event) => {
          reply.take(event);
          forward({ kind: 'ai', ai: event });
        },
        issueApproval: ({ toolCallId, command }) =>
          ai.approvals.issue(session.handle.principal, body.conversationId, toolCallId, command),
      });
      await record.reply(reply.text(), profile.model);
    });
  }

  /** How a chat on the caller's own session records its turn; a no-op for one that records none. */
  function turnRecordOf(
    principal: SessionPrincipal,
    config: RdcConfig,
    body: ChatRequest,
    configSessionId: string | undefined
  ): TurnRecord {
    const recording = ai.chat?.recording;
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

  /** The model of the profile a request resolves to, or the refusal that answers it. */
  function buildModel(
    sources: AiConfigs,
    name: string | undefined,
    options: ProviderModelOptions
  ): BuiltModel | { refusal: { error: string; code: string }; status: 404 | 422 } {
    const resolved = resolveProfile(sources, name);
    if (!resolved.ok) {
      return { status: 404, refusal: { error: resolved.message, code: AI_PROFILE_UNRESOLVED } };
    }
    try {
      return { model: modelOf(resolved.profile, options), profile: resolved.profile };
    } catch (error) {
      if (!(error instanceof ProviderProfileError)) throw error;
      return { status: 422, refusal: { error: error.message, code: AI_PROFILE_UNRESOLVED } };
    }
  }

  app.post(AI_ROUTES.chat, async (c) => {
    try {
      const { principal, body, config, configSessionId } = await admit(c, ChatRequestSchema);
      const opened = await openChat(principal, config, body.grant, configSessionId);
      if ('refusal' in opened) return c.json(opened.refusal, opened.status);
      const { session } = opened;
      const built = buildModel(
        session.sources,
        body.profile,
        rediaccOf(principal, body.conversationId)
      );
      if ('refusal' in built) return c.json(built.refusal, built.status);
      const record = turnRecordOf(principal, config, body, configSessionId);
      return streamChat(c, built, session, body, record);
    } catch (error) {
      return refusal(c, error);
    }
  });

  /** The provider's transcript of one recording, or the refusal that answers it. */
  async function transcription(
    profile: Profile,
    recording: Recording,
    signal: AbortSignal
  ): Promise<{ body: Record<string, string>; status: 200 | 422 | 502 }> {
    if (!supportsTranscription(profile)) {
      return {
        status: 422,
        body: {
          error: 'This profile has no transcription endpoint; pick an OpenAI-compatible profile.',
          code: AI_TRANSCRIBE_UNSUPPORTED,
        },
      };
    }
    try {
      const fetch = ai.chat?.transcribeFetch;
      const text = await transcribeAudio(profile, recording.audio, recording.type, {
        ...(fetch ? { fetch } : {}),
        signal,
      });
      return { status: 200, body: { text } };
    } catch (error) {
      return transcriptionRefusal(error);
    }
  }

  app.post(AI_ROUTES.transcribe, async (c) => {
    try {
      const principal = await helpers.authenticate(c.req.header('authorization'));
      const recording = await readRecording(c);
      if ('refusal' in recording) return c.json(recording.refusal, recording.status);
      const configSessionId = helpers.configSession(c.req.header('x-config-session'));
      if (configSessionId) deps.sessions.sessionForExec(principal, configSessionId);
      const config = await deps.loadConfig(principal, configSessionId);
      const sources = await profileSources(principal, config, configSessionId);
      const resolved = resolveProfile(sources, recording.profile);
      if (!resolved.ok) {
        return c.json({ error: resolved.message, code: AI_PROFILE_UNRESOLVED }, 404);
      }
      const answer = await transcription(resolved.profile, recording, c.req.raw.signal);
      return c.json(answer.body, answer.status, { 'Cache-Control': 'no-store' });
    } catch (error) {
      return refusal(c, error);
    }
  });

  app.post(AI_ROUTES.test, async (c) => {
    try {
      const { principal, body, config, configSessionId } = await admit(c, TestRequestSchema);
      const sources = await profileSources(principal, config, configSessionId);
      const resolved = resolveProfile(sources, body.profile);
      if (!resolved.ok) {
        return c.json({ error: resolved.message, code: AI_PROFILE_UNRESOLVED }, 404);
      }
      try {
        return c.json(
          await runSmoke(modelOf(resolved.profile, rediaccOf(principal, 'smoke-test')), {
            abortSignal: c.req.raw.signal,
          })
        );
      } catch (error) {
        if (!(error instanceof ProviderProfileError)) throw error;
        return c.json(refusedSmoke(error));
      }
    } catch (error) {
      return refusal(c, error);
    }
  });
}

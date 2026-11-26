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
 * `POST /v1/ai/test` runs the tool-calling smoke of the resolved profile (D12) and answers its
 * verdict as JSON; nothing is stored.
 */

import { type AiConfigs, isRediaccProfile, type Profile, resolveProfile } from '@rediacc/shared/ai';
import { isPreviewRun, isStepUpMethod, STEP_UP_METHODS } from '@rediacc/shared/auth';
import { getCommand } from '@rediacc/shared/cli-contract';
import {
  type AiApprovalCommand,
  type AiEvent,
  PROXY_ROUTES,
  type StreamLine,
} from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { listProxyTools } from '@rediacc/shared/mcp/registry';
import {
  type AiDisableableMode,
  disabledAiModes,
  type EffectivePolicy,
  mergePolicies,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';
import { jsonSchema, type LanguageModel, type ModelMessage, type ToolSet, tool } from 'ai';
import type { Context, Hono } from 'hono';
import { streamText } from 'hono/streaming';
import { z } from 'zod';
import { auditApproval } from '../ai/approval-audit.js';
import type { AiApprovals } from '../ai/approvals.js';
import { autonomyHold, effectiveMode, isGrandTarget } from '../ai/autonomy.js';
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
import { runSmoke, type SmokeResult } from '../ai/smoke.js';
import {
  type AiGateCall,
  type AiToolContext,
  type AiToolGate,
  type AiToolResult,
  requestOf,
  runAiTool,
} from '../ai/tools.js';
import { fenceUntrusted } from '../ai/untrusted.js';
import { boundEffectivePolicy } from '../config/policy-record.js';
import {
  type AgentGrantHandle,
  AgentSessionRefused,
  AgentSessionUnavailable,
} from './agent-grant-session.js';
import { type BusyCounter, createBusyCounter } from './busy.js';
import { prepareCommand } from './command-dispatch.js';
import type { ExecutorAuditEvent, ServeDeps } from './deps.js';
import { cancelOnMachine, type JobRouteHelpers } from './job-routes.js';
import { dispatcher, HandedBack } from './mcp-call-dispatch.js';
import { globRefusal, scopeAdmitsTool } from './mcp-call-scope.js';
import { clusterSubjectOf, resolveExecutorTarget } from './policy.js';
import type { SessionPrincipal } from './sessions.js';

/** The issue text when the schema names none. */
const UNNAMED_ISSUE = 'invalid';

/** Route paths; the account Worker's `AI_EXECUTOR_ROUTES` names the same two. */
export const AI_ROUTES = {
  mode: '/v1/ai/mode',
  approval: '/v1/ai/approval',
  chat: PROXY_ROUTES.aiChat,
  test: PROXY_ROUTES.aiTest,
} as const;

const AI_MODES = ['ask', 'auto', 'skip'] as const;
export type AiMode = (typeof AI_MODES)[number];

/** Refusal codes these routes answer with. */
export const AI_MODE_DISABLED = 'AI_MODE_DISABLED';
export const AI_APPROVAL_STEPUP_REQUIRED = 'AI_APPROVAL_STEPUP_REQUIRED';

const IdSchema = z
  .string()
  .min(1)
  .max(128)
  .regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/);

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

/** Where the loop keeps each conversation's mode (D4) and exact allow rules; the autonomy gate reads both. */
export interface AiConversationModes {
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

/** A request these routes refuse before any policy work. */
class BadAiRequest extends Error {}

/**
 * The effective policy the config carries: the policy records bound to a remote config, else the
 * `policy` field of a local-file config (the same sources serve/policy.ts authorizes against). A
 * malformed local document disables nothing here; authorize() refuses every command under it.
 */
function effectivePolicyOf(config: RdcConfig): EffectivePolicy | null {
  const bound = boundEffectivePolicy(config);
  if (bound) return bound;
  if (config.remote !== undefined || config.policy === undefined) return null;
  const parsed = PolicyDocumentSchema.safeParse(config.policy);
  return parsed.success ? mergePolicies(parsed.data) : null;
}

/** The modes the policy disables for this caller (D6), in `AI_DISABLEABLE_MODES` order. */
function disabledModesFor(config: RdcConfig, principal: SessionPrincipal): AiDisableableMode[] {
  const effective = effectivePolicyOf(config);
  if (!effective) return [];
  return disabledAiModes(effective, {
    userEmail: principal.userEmail,
    ...(principal.teamSlug ? { teamSlug: principal.teamSlug } : {}),
  });
}

function stringOf(name: string | null, bag: Record<string, unknown>): string | undefined {
  const value = name ? bag[name] : undefined;
  return typeof value === 'string' ? value : undefined;
}

/**
 * What the executor itself makes of an approval: whether the command is destructive (and not a
 * preview) and whether its target is a grand repo, and the refusal of an approval of either that
 * names no step-up method.
 */
async function judgeApproval(
  body: ApprovalRequest,
  config: RdcConfig | undefined
): Promise<{ grand: boolean; destructive: boolean } | { refusal: Record<string, unknown> }> {
  const { pathKey, params, positionals } = body.command;
  const { entry } = prepareCommand(pathKey, params, positionals);
  const target = await resolveExecutorTarget(
    entry,
    {
      ref: stringOf(entry.repoOption, params) ?? stringOf(entry.repoPositional, positionals),
      machine:
        stringOf(entry.machineOption, params) ?? stringOf(entry.machinePositional, positionals),
      subject: clusterSubjectOf(entry, positionals),
    },
    config
  );
  const grand = isGrandTarget(target);
  const destructive = entry.severity === 'destructive' && !isPreviewRun(entry, params);
  const needsStepUp = body.decision === 'approve' && (grand || destructive);
  if (!needsStepUp || isStepUpMethod(body.stepUpMethod)) return { grand, destructive };
  const why = grand ? `targets the grand repo "${target.repo?.name}"` : 'is destructive';
  return {
    refusal: {
      error: `Approving "rdc ${pathKey}" needs a fresh re-authentication: the command ${why}.`,
      code: AI_APPROVAL_STEPUP_REQUIRED,
      grand,
      destructive,
    },
  };
}

const MAX_MESSAGES = 200;
const MAX_MESSAGE_CHARS = 100_000;
const GRANT_ID = /^[A-Za-z0-9_-]{1,128}$/;
const ProfileNameSchema = z.string().min(1).max(128);

/**
 * What the browser sends. Not strict on purpose: a field this schema does not name (a `kind`, a
 * `principal`, an `agentGrant`) is dropped before anything reads the body, so none of them can
 * reach the principal the tools run as.
 */
const ChatRequestSchema = z.object({
  conversationId: IdSchema,
  messages: z
    .array(
      z.object({ role: z.enum(['user', 'assistant']), content: z.string().max(MAX_MESSAGE_CHARS) })
    )
    .min(1)
    .max(MAX_MESSAGES)
    .refine((messages) => messages.at(-1)?.role === 'user', {
      message: "the last message must be the user's",
    }),
  profile: ProfileNameSchema.optional(),
  grant: z
    .strictObject({ grantId: z.string().regex(GRANT_ID), secret: z.string().min(1).max(256) })
    .optional(),
});

type ChatRequest = z.infer<typeof ChatRequestSchema>;

const TestRequestSchema = z.object({ profile: ProfileNameSchema.optional() });

/** Refusal codes of the chat and test routes. */
export const AI_PROFILE_UNRESOLVED = 'AI_PROFILE_UNRESOLVED';
export const AI_GRANT_UNAVAILABLE = 'AI_GRANT_UNAVAILABLE';

/** How long one tool call may run before its turn gives up on it (a started job is handed back sooner). */
const TOOL_WINDOW_MS = 5 * 60 * 1000;

const NO_GRANT_OVERRIDES = { allowGrandRepos: false, allowClusterOps: false } as const;

/** One chat's verified session: who the tools run as, and the config and scope they run in. */
interface ChatSession {
  handle: AgentGrantHandle;
  sources: AiConfigs;
}

/** The model a chat runs on, and the profile it came from (the judge reads the profile). */
interface BuiltModel {
  model: LanguageModel;
  profile: Profile;
}

/** A session, or the refusal that answers the request instead. */
type OpenedChat =
  | { session: ChatSession }
  | { refusal: { error: string; code: string }; status: 400 | 403 | 503 };

/** A request id the job machinery accepts, from a conversation and a model-chosen tool call id. */
function toolRequestId(conversationId: string, toolCallId: string): string {
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
interface TurnRecord {
  opening: () => Promise<void>;
  reply: (text: string, model: string | undefined) => Promise<void>;
}

/** The record of a turn that is not recorded. */
const UNRECORDED: TurnRecord = {
  opening: () => Promise.resolve(),
  reply: () => Promise.resolve(),
};

/** A machine job a tool call started. */
interface StartedJob {
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

interface ChatToolHost {
  deps: ServeDeps;
  busy: BusyCounter;
  session: ChatSession;
  conversationId: string;
  forward: (line: StreamLine) => void;
  gate: AiToolGate;
  /** Cancel one job of an aborted chat: authorized and audited as `job cancel`; never rejects. */
  cancelJob: (job: StartedJob) => void;
}

/** The argv the judge reads: the path, the positionals in order, then each option as `--name value`. */
function judgeArgvOf(command: AiApprovalCommand): string[] {
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
function chatTools(host: ChatToolHost): ToolSet {
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

function messagesOf(body: ChatRequest): ModelMessage[] {
  return body.messages.map((m) => ({ role: m.role, content: m.content }));
}

/** The smoke result of a profile the adapter refused to build, in the smoke's own shape. */
function refusedSmoke(error: ProviderProfileError): SmokeResult {
  return {
    ok: false,
    reason: 'profile-refused',
    message: error.message,
    latencyMs: 0,
    observed: { tools: false, streaming: false },
  };
}

/** The grant session of a grant-bound chat, or the refusal that answers it. */
async function openGrant(
  deps: ServeDeps,
  grant: NonNullable<ChatRequest['grant']>
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
        return c.json(
          {
            error: `The ${body.mode} mode is disabled by your organization's policy (aiModesDisabled).`,
            code: AI_MODE_DISABLED,
            disabled,
          },
          403
        );
      }
      ai.modes.set(principal, body.conversationId, body.mode);
      return c.json({ conversationId: body.conversationId, mode: body.mode });
    } catch (error) {
      return refusal(c, error);
    }
  });

  /** Audit one redeemed answer; an approval whose record cannot be delivered loses its grant. */
  async function recordApproval(
    principal: SessionPrincipal,
    body: ApprovalRequest,
    judged: { destructive: boolean }
  ): Promise<void> {
    try {
      await auditApproval(deps.audit, {
        principal,
        decision: body.decision,
        destructive: judged.destructive,
        requestId: toolRequestId(body.conversationId, body.toolCallId),
      });
    } catch (error) {
      ai.approvals.revokeGrant(principal, body.conversationId, body.command);
      throw error;
    }
  }

  app.post(AI_ROUTES.approval, async (c) => {
    try {
      const { principal, body, config } = await admit(c, ApprovalRequestSchema);
      const judged = await judgeApproval(body, helpers.requestScopedConfig(config));
      if ('refusal' in judged) return c.json(judged.refusal, 403);
      const { grand, destructive } = judged;

      const { remember, ...answer } = body;
      const verdict = await ai.approvals.submit({ ...answer, principal, destructive, grand });
      if (!verdict.ok) {
        return c.json({ error: verdict.message, code: verdict.code }, verdict.status);
      }
      await recordApproval(principal, body, judged);
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
    gate: AiToolGate
  ): ChatToolHost => ({
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
        tools: chatTools(chatHost(session, body.conversationId, forward, gate)),
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

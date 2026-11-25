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
 * single-use token itself is redeemed by the approval ledger the loop owns (`AiApprovals`), bound
 * to the conversation and the command.
 *
 * `POST /v1/ai/chat` runs one chat turn (AP7 of agent/plans/PLAN-console-ai-providers.md) and
 * answers NDJSON: `ai` lines from the loop (services/ai/loop.ts) and the renet `event` lines of each
 * tool call, tagged with its call id. The profile is resolved from the session's configs (D3), and
 * every tool call runs under an agent principal the route sets, never one the body names (D9). A
 * chat bound to an agent grant (`grant` in the body) takes the grant's session: its config, its
 * opt-ins and its scope, through the same grant sessions `POST /v1/mcp/call` uses. The client
 * leaving aborts the provider stream and every running tool.
 *
 * `POST /v1/ai/test` runs the tool-calling smoke of the resolved profile (D12) and answers its
 * verdict as JSON; nothing is stored.
 */

import { type AiConfigs, type Profile, resolveProfile } from '@rediacc/shared/ai';
import { isPreviewRun, isStepUpMethod, STEP_UP_METHODS } from '@rediacc/shared/auth';
import { getCommand } from '@rediacc/shared/cli-contract';
import { type AiEvent, PROXY_ROUTES, type StreamLine } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { listProxyTools } from '@rediacc/shared/mcp/registry';
import {
  type AiDisableableMode,
  type DecisionTarget,
  disabledAiModes,
  type EffectivePolicy,
  mergePolicies,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';
import { jsonSchema, type LanguageModel, type ModelMessage, type ToolSet, tool } from 'ai';
import type { Context, Hono } from 'hono';
import { streamText } from 'hono/streaming';
import { z } from 'zod';
import { runAiTurn } from '../ai/loop.js';
import { createProviderModel, ProviderProfileError } from '../ai/provider.js';
import { runSmoke, type SmokeResult } from '../ai/smoke.js';
import { type AiToolContext, type AiToolResult, requestOf, runAiTool } from '../ai/tools.js';
import { fenceUntrusted } from '../ai/untrusted.js';
import { boundEffectivePolicy } from '../config/policy-record.js';
import {
  type AgentGrantHandle,
  AgentSessionRefused,
  AgentSessionUnavailable,
} from './agent-grant-session.js';
import { type BusyCounter, createBusyCounter } from './busy.js';
import { prepareCommand } from './command-dispatch.js';
import type { ServeDeps } from './deps.js';
import type { JobRouteHelpers } from './job-routes.js';
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
});

type ApprovalRequest = z.infer<typeof ApprovalRequestSchema>;

/** Where the loop keeps each conversation's mode (D4); the autonomy gate reads it. */
export interface AiConversationModes {
  set(principal: SessionPrincipal, conversationId: string, mode: AiMode): void;
}

/** One approval answer as the executor verified it. */
export interface AiApprovalSubmit extends Omit<ApprovalRequest, 'stepUpMethod'> {
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

/** The single-use approval tokens the loop issued, bound to (conversation, command). */
export interface AiApprovals {
  submit(answer: AiApprovalSubmit): Promise<AiApprovalVerdict>;
  /** A chat turn ended on this approval request: the ledger expects its answer. */
  expect(
    principal: SessionPrincipal,
    conversationId: string,
    event: Extract<AiEvent, { type: 'approval_required' }>
  ): void;
}

/** The chat host's own seams; every one has a production default. */
export interface AiChatDeps {
  /** The AI SDK model of a profile; `createProviderModel` when absent. Tests pass a mock model. */
  createModel?: (profile: Profile) => LanguageModel;
  /**
   * The profile sources of a request, team over shared (D3). Absent: the session's own config is the
   * only source. The container tier lends the second config when it loads both.
   */
  aiConfigs?: (principal: SessionPrincipal, config: RdcConfig) => Promise<AiConfigs>;
  /** Counts a running tool as a running dispatch, as `/v1/command` does. */
  busy?: BusyCounter;
  /** The per-turn output token cap; the loop's default when absent. */
  maxOutputTokens?: number;
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

/** A grand-repo target as the grand-repo rule reads it: unresolved counts as grand; ops VMs never do. */
function isGrandTarget(target: DecisionTarget): boolean {
  return !!target.repo && target.repo.state !== 'fork' && !target.isOpsVm;
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

interface ChatToolHost {
  deps: ServeDeps;
  busy: BusyCounter;
  session: ChatSession;
  conversationId: string;
  forward: (line: StreamLine) => void;
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
  const dispatch = dispatcher(
    {
      deps: host.deps,
      busy: host.busy,
      handle,
      requestId: toolRequestId(host.conversationId, call.toolCallId),
      windowMs: TOOL_WINDOW_MS,
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
    return { principal, body: parsed.data, config };
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

  app.post(AI_ROUTES.approval, async (c) => {
    try {
      const { principal, body, config } = await admit(c, ApprovalRequestSchema);
      const judged = await judgeApproval(body, helpers.requestScopedConfig(config));
      if ('refusal' in judged) return c.json(judged.refusal, 403);
      const { grand, destructive } = judged;

      const verdict = await ai.approvals.submit({ ...body, principal, destructive, grand });
      if (!verdict.ok) {
        return c.json({ error: verdict.message, code: verdict.code }, verdict.status);
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
    grant: ChatRequest['grant']
  ): Promise<OpenedChat> {
    if (grant) return await openGrant(deps, grant);
    const handle: AgentGrantHandle = {
      grantId: '',
      principal,
      scope: { readOnly: false },
      overrides: NO_GRANT_OVERRIDES,
      config: helpers.requestScopedConfig(config) ?? config,
    };
    return { session: { handle, sources: await profileSources(principal, config) } };
  }

  async function profileSources(
    principal: SessionPrincipal,
    config: RdcConfig
  ): Promise<AiConfigs> {
    return (await ai.chat?.aiConfigs?.(principal, config)) ?? { team: config.ai };
  }

  const modelOf = (profile: Profile): LanguageModel =>
    (ai.chat?.createModel ?? createProviderModel)(profile);

  const chatHost = (
    session: ChatSession,
    conversationId: string,
    forward: ChatToolHost['forward']
  ) => ({
    deps,
    busy: ai.chat?.busy ?? chatBusy,
    session,
    conversationId,
    forward,
  });

  /** Stream one turn as NDJSON; the client leaving aborts the provider stream and the running tools. */
  function streamChat(c: Context, model: LanguageModel, session: ChatSession, body: ChatRequest) {
    const abort = new AbortController();
    c.req.raw.signal.addEventListener('abort', () => abort.abort(), { once: true });
    return streamText(c, async (stream) => {
      stream.onAbort(() => abort.abort());
      const forward = (line: StreamLine) => {
        stream.write(`${JSON.stringify(line)}\n`).catch(() => undefined);
      };
      await runAiTurn({
        model,
        tools: chatTools(chatHost(session, body.conversationId, forward)),
        messages: messagesOf(body),
        ...(ai.chat?.maxOutputTokens ? { maxOutputTokens: ai.chat.maxOutputTokens } : {}),
        abortSignal: abort.signal,
        emit: (event) => forward({ kind: 'ai', ai: event }),
        onApprovalRequired: (event) =>
          ai.approvals.expect(session.handle.principal, body.conversationId, event),
      });
    });
  }

  /** The model of the profile a request resolves to, or the refusal that answers it. */
  function buildModel(
    sources: AiConfigs,
    name: string | undefined
  ): { model: LanguageModel } | { refusal: { error: string; code: string }; status: 404 | 422 } {
    const resolved = resolveProfile(sources, name);
    if (!resolved.ok) {
      return { status: 404, refusal: { error: resolved.message, code: AI_PROFILE_UNRESOLVED } };
    }
    try {
      return { model: modelOf(resolved.profile) };
    } catch (error) {
      if (!(error instanceof ProviderProfileError)) throw error;
      return { status: 422, refusal: { error: error.message, code: AI_PROFILE_UNRESOLVED } };
    }
  }

  app.post(AI_ROUTES.chat, async (c) => {
    try {
      const { principal, body, config } = await admit(c, ChatRequestSchema);
      const opened = await openChat(principal, config, body.grant);
      if ('refusal' in opened) return c.json(opened.refusal, opened.status);
      const { session } = opened;
      const built = buildModel(session.sources, body.profile);
      if ('refusal' in built) return c.json(built.refusal, built.status);
      const { model } = built;
      return streamChat(c, model, session, body);
    } catch (error) {
      return refusal(c, error);
    }
  });

  app.post(AI_ROUTES.test, async (c) => {
    try {
      const { principal, body, config } = await admit(c, TestRequestSchema);
      const resolved = resolveProfile(await profileSources(principal, config), body.profile);
      if (!resolved.ok) {
        return c.json({ error: resolved.message, code: AI_PROFILE_UNRESOLVED }, 404);
      }
      try {
        return c.json(await runSmoke(modelOf(resolved.profile), { abortSignal: c.req.raw.signal }));
      } catch (error) {
        if (!(error instanceof ProviderProfileError)) throw error;
        return c.json(refusedSmoke(error));
      }
    } catch (error) {
      return refusal(c, error);
    }
  });
}

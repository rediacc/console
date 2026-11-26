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
 * every tool call runs under the verified caller's principal (the grant's agent principal for a
 * grant-bound chat) and the agent overrides (no grand repos, no cluster operations), all set by the
 * route and never taken from the body (D9), then through the conversation's autonomy gate (services/ai/autonomy.ts), the Auto-mode judge included. A
 * chat bound to an agent grant (`grant` in the body) takes the grant's session: its config, its
 * opt-ins and its scope, through the same grant sessions `POST /v1/mcp/call` uses. The client
 * leaving aborts the provider stream and every running tool, and cancels each machine job a tool
 * call of the turn started (`renet job cancel`, authorized and audited as `job cancel`; a cancel that fails, its
 * `started` record included, is warned, since nobody is left to answer). A command
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
 * `POST /v1/ai/tasks` starts the chat body as a background task (AX6, D5): the same turn on the
 * conversation's mode and gate, run detached from the request and recorded as an `ai.task` plan-4
 * run, one task per conversation and two live per user (`AI_TASK_LIMIT` past that). A held command
 * pauses the task as `needs_approval` until the approval route approves it (a rejection ends it),
 * and a session whose key expired ends it `failed`. `GET /v1/ai/tasks` lists the caller's tasks,
 * `GET /v1/ai/tasks/:conversationId` reads one with its events, and `POST .../cancel` stops one.
 *
 * `POST /v1/ai/test` runs the tool-calling smoke of the resolved profile (D12) and answers its
 * verdict as JSON; nothing is stored.
 */

import { type AiConfigs, type Profile, resolveProfile } from '@rediacc/shared/ai';
import { getCommand } from '@rediacc/shared/cli-contract';
import { type AiEvent, PROXY_ROUTES, type StreamLine } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { type LanguageModel } from 'ai';
import type { Context, Hono } from 'hono';
import { streamText } from 'hono/streaming';
import { z } from 'zod';
import { auditJudgment, auditModeChange, auditRefusal } from '../ai/approval-audit.js';
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
import { runSmoke } from '../ai/smoke.js';
import { type AiGateCall, type AiToolGate } from '../ai/tools.js';
import { outputService } from '../core/output.js';
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
  replyFold,
  type StartedJob,
  type TurnRecord,
  toolRequestId,
  turnRecordOf,
} from './ai-chat-tools.js';
import { type ChatRequest, ChatRequestSchema, TestRequestSchema } from './ai-request-schemas.js';
import {
  AI_MODE_DISABLED,
  AI_PROFILE_UNRESOLVED,
  type AiRouteDeps,
  ApprovalRequestSchema,
  ModeRequestSchema,
} from './ai-route-types.js';
import {
  AI_TASK_ROUTES,
  type PreparedTask,
  registerTaskRoutes,
  TASK_RESUME_MESSAGE,
} from './ai-task-routes.js';
import { readRecording, transcription } from './ai-transcribe-route.js';
import { createBusyCounter } from './busy.js';
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
  ...AI_TASK_ROUTES,
} as const;

export {
  AI_MODE_DISABLED,
  AI_PROFILE_UNRESOLVED,
  type AiApprovalSubmit,
  type AiApprovalVerdict,
  type AiChatDeps,
  type AiChatRecording,
  type AiMode,
  type AiRouteDeps,
  type ApprovalRequest,
} from './ai-route-types.js';

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
    return { principal, body: parsed.data, ...(await sessionOf(c, principal)) };
  }

  /** The config of the request's session, once the principal owns it (shared by every route, the transcription one included). */
  async function sessionOf(c: Context, principal: SessionPrincipal) {
    const configSessionId = helpers.configSession(c.req.header('x-config-session'));
    if (configSessionId) deps.sessions.sessionForExec(principal, configSessionId);
    return { config: await deps.loadConfig(principal, configSessionId), configSessionId };
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
        try {
          await auditModeChange(deps.audit, { principal, destructive: false, mode: body.mode });
        } catch (error) {
          // No record, no change: the mode goes back to what the audit trail still says.
          ai.modes.set(principal, body.conversationId, previous);
          throw error;
        }
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
      await tasks.answer(principal, body.conversationId, body.decision === 'approve');
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

  /** The ids a Rediacc tier call is billed under: the authenticated person and a conversation (the smoke route names the fixed `smoke-test`). */
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
    // The same builder as the chat's, so a Rediacc tier judge is billed to the caller's ids too.
    try {
      return runJudge(profile, input, {
        model: modelOf({ ...profile, model: judgeModelOf(profile) }, options),
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      return Promise.resolve<JudgeVerdict>({
        verdict: 'block',
        reason: `The judge could not be asked: ${detail}`.slice(0, 2000),
      });
    }
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
    const requestId = toolRequestId(body.conversationId, call.toolCallId);
    try {
      await auditJudgment(deps.audit, { principal, requestId, call, judgment });
    } catch (error) {
      // The judge already fell back to Ask, so the mode record is shipped on its own: the call still fails, the mode change is not left unrecorded.
      if (judgment.fallback) {
        await auditModeChange(deps.audit, {
          principal,
          requestId,
          destructive: call.entry.severity === 'destructive',
          mode: 'ask',
        }).catch((modeError: unknown) => {
          // Both records are lost and the mode is already Ask in memory: the judge failure is what the call answers, so the second loss is warned instead of dropped.
          const why = modeError instanceof Error ? modeError.message : String(modeError);
          outputService.warn(
            `AI judge fell back to Ask in conversation ${body.conversationId}, and the mode record could not be delivered: ${why}`
          );
        });
      }
      throw error;
    }
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
    // The client has left, so a failed cancel has nobody to answer; it is warned, and a cancel that ran carries its outcome in the audit record.
    cancelJob: (job) => {
      cancelAudited(session.handle, job).catch((error: unknown) => {
        const why = error instanceof Error ? error.message : String(error);
        outputService.warn(
          `AI chat aborted: job ${job.jobId} on ${job.machine} was not cancelled and may still run: ${why}`
        );
      });
    },
  });

  /** One turn of a chat or a task: recorded, gated and run, its events handed to `emit`. */
  async function runTurn(
    turn: { built: BuiltModel; session: ChatSession; body: ChatRequest; record: TurnRecord },
    io: {
      signal: AbortSignal;
      emit: (event: AiEvent) => void;
      forward: (line: StreamLine) => void;
      /** The user message of a turn that resumes after an approval. */
      resume?: string;
    }
  ): Promise<void> {
    const { built, session, body, record } = turn;
    const { model, profile } = built;
    const maxOutputTokens = profile.maxOutputTokens ?? ai.chat?.maxOutputTokens;
    // Before the model runs: a held call is approvable only in a conversation the store holds.
    if (!io.resume) await record.opening();
    const reply = replyFold();
    const messages = messagesOf(body);
    if (io.resume) messages.push({ role: 'user', content: io.resume });
    await runAiTurn({
      model,
      tools: chatTools(
        chatHost(
          session,
          body.conversationId,
          io.forward,
          chatGate(session, profile, body),
          body.forensicsTicket
        )
      ),
      messages,
      ...(maxOutputTokens ? { maxOutputTokens } : {}),
      abortSignal: io.signal,
      emit: (event) => {
        reply.take(event);
        io.emit(event);
      },
      issueApproval: ({ toolCallId, command }) =>
        ai.approvals.issue(session.handle.principal, body.conversationId, toolCallId, command),
    });
    await record.reply(reply.text(), profile.model);
  }

  /** Stream one turn as NDJSON; the client leaving aborts the provider stream and the running tools. */
  function streamChat(c: Context, turn: Parameters<typeof runTurn>[0]) {
    const abort = new AbortController();
    c.req.raw.signal.addEventListener('abort', () => abort.abort(), { once: true });
    return streamText(c, async (stream) => {
      stream.onAbort(() => abort.abort());
      const forward = (line: StreamLine) => {
        stream.write(`${JSON.stringify(line)}\n`).catch(() => undefined);
      };
      await runTurn(turn, {
        signal: abort.signal,
        forward,
        emit: (event) => forward({ kind: 'ai', ai: event }),
      });
    });
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
      const record = turnRecordOf(ai.chat?.recording, principal, config, body, configSessionId);
      return streamChat(c, { built, session, body, record });
    } catch (error) {
      return refusal(c, error);
    }
  });

  /** The turn a task starts from the request body, or the refusal that answers it. */
  async function prepareTask(c: Context): Promise<PreparedTask | Response> {
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
    const turn = {
      built,
      session,
      body,
      record: turnRecordOf(ai.chat?.recording, principal, config, body, configSessionId),
    };
    return {
      principal,
      conversationId: body.conversationId,
      configSessionId,
      step: ({ signal, emit, resumed }) =>
        runTurn(turn, {
          signal,
          emit,
          forward: () => undefined,
          ...(resumed ? { resume: TASK_RESUME_MESSAGE } : {}),
        }),
    };
  }

  const tasks = registerTaskRoutes(app, { deps, helpers, refusal, prepare: prepareTask });

  app.post(AI_ROUTES.transcribe, async (c) => {
    try {
      const principal = await helpers.authenticate(c.req.header('authorization'));
      const recording = await readRecording(c);
      if ('refusal' in recording) return c.json(recording.refusal, recording.status);
      const { config, configSessionId } = await sessionOf(c, principal);
      const sources = await profileSources(principal, config, configSessionId);
      const resolved = resolveProfile(sources, recording.profile);
      if (!resolved.ok) {
        return c.json({ error: resolved.message, code: AI_PROFILE_UNRESOLVED }, 404);
      }
      const answer = await transcription(
        resolved.profile,
        recording,
        c.req.raw.signal,
        ai.chat?.transcribeFetch
      );
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

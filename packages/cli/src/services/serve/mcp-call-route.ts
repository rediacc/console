/**
 * `POST /v1/mcp/call`: one hosted MCP `tools/call` under an agent grant
 * (agent/plans/PLAN-rmcp-agent-grants.md Design 4, PLAN-rmcp-remote-worker.md Design 1).
 *
 * The MCP Worker forwards `{grantId, secret, tool, args, requestId, attachMs}` through the proxy's
 * `McpExecutor` RPC (workers/proxy/src/org-executor.ts `mcpCall`), and this route answers
 * `{result: CallToolResult}` or `{job: {jobId, machine}}`. It is reachable only through that RPC: the
 * Durable Object's public forward refuses the path, and it is registered in the container tier alone, so
 * the route carries no bearer of its own. The agent secret `secret` arrives in the body and is handed to
 * the grant session (agent-grant-session.ts) and nowhere else: not to a log line, an audit event or an error.
 *
 * Every call takes the executor's own path, in its order, so a hosted call and the same command typed at
 * `/v1/command` get the same checks (D18):
 *
 *   1. the grant session opens or is rebuilt from `secret`, and its config is brought to the store's version;
 *   2. the tool must be a proxy-surface registry tool the grant's scope admits (read-only flag, tool list);
 *   3. the grant's machine and repo globs must admit the target the command resolves to (mcp-call-scope.ts);
 *   4. `runAiTool` (services/ai/tools.ts) prepares the command (`prepareCommand`) and asks `authorize`, the
 *      enforcement point of `decide`, with the grant's opt-ins, before anything is dispatched;
 *   5. a mutating command is audited as `started` first and is refused when that cannot be delivered, then
 *      runs against the session's config and has its outcome audited (mcp-call-dispatch.ts).
 *
 * Time: the container answers within `attachMs`. A run that has started a job by then answers its job
 * handle and keeps running, and `job_wait` answers its latest status at the ceiling.
 */

import type { CallToolResult } from '@modelcontextprotocol/server';
import { getCommand } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { getMcpTool, type McpToolEntry } from '@rediacc/shared/mcp/registry';
import type { Hono } from 'hono';
import { z } from 'zod';
import { JOB_WAIT_CEILING_MS, JOB_WAIT_INTERVAL_MS } from '../../commands/mcp/custom-tools.js';
import { type AiToolResult, requestOf, runAiTool } from '../ai/tools.js';
import {
  type AgentGrantHandle,
  AgentSessionRefused,
  AgentSessionUnavailable,
} from './agent-grant-session.js';
import { AUDIT_UNAVAILABLE, AuditUnavailableError } from './audit.js';
import type { BusyCounter } from './busy.js';
import type { DispatchOutcome } from './command-dispatch.js';
import type { ServeDeps } from './deps.js';
import { dispatcher, HandedBack, WindowPassed } from './mcp-call-dispatch.js';
import {
  type Envelope,
  envelopeOf,
  GRANT_ENDED,
  isPageable,
  jobFinished,
  toolError,
} from './mcp-call-result.js';
import { globRefusal, scopeAdmitsTool } from './mcp-call-scope.js';
import { pageOf } from './result-page.js';

const GRANT_ID = /^[A-Za-z0-9_-]{1,128}$/;

/** What the MCP Worker posts (workers/mcp/src/executor.ts `McpCallForward`). Strict: no field can smuggle anything in. */
const McpCallRequestSchema = z.strictObject({
  grantId: z.string().regex(GRANT_ID),
  secret: z.string().min(1).max(256),
  tool: z.string().min(1).max(200),
  args: z.record(z.string(), z.unknown()),
  requestId: z.string().min(1).max(256),
  attachMs: z.number().int().min(1).max(120_000),
});

export interface McpCallRouteOptions {
  busy: BusyCounter;
}

/** The pause between two `job_wait` reads, with the test override REDIACC_MCP_JOB_WAIT_INTERVAL_MS (a positive integer), as the heartbeat's REDIACC_PROXY_HEARTBEAT_MS. */
function jobWaitIntervalMs(): number {
  const raw = process.env.REDIACC_MCP_JOB_WAIT_INTERVAL_MS;
  const positive = raw !== undefined && /^[1-9]\d*$/.test(raw);
  return positive ? Number.parseInt(raw, 10) : JOB_WAIT_INTERVAL_MS;
}

/** One tool call's pieces. */
interface CallContext {
  deps: ServeDeps;
  options: McpCallRouteOptions;
  handle: AgentGrantHandle;
  entry: McpToolEntry;
  requestId: string;
  attachMs: number;
}

/** What one call answers: a result for the Worker to pass on, or the handle of a job that outlived the window. */
type Answer = { result: CallToolResult } | { job: { jobId: string; machine?: string } };

/** A finished dispatch, or the answer that ends the call before or without one. */
type Ran = { outcome: DispatchOutcome; command: string } | Answer;

const withDecision = (answer: Extract<AiToolResult, { code: string }>) => ({
  decisionCode: answer.code,
  ...(answer.next ? { next: answer.next } : {}),
});

/** The answer for a call `runAiTool` did not run: `decide` refused it, `prepareCommand` rejected it, or it needs confirmation. */
function heldAnswer(
  answer: Extract<AiToolResult, { status: 'refused' | 'approval_required' }>
): Answer {
  if (answer.status === 'approval_required') {
    return { result: toolError('NEEDS_CONFIRMATION', answer.reason, withDecision(answer)) };
  }
  const code = answer.code === 'COMMAND_REJECTED' ? 'INVALID_REQUEST' : 'POLICY_DENIED';
  return { result: toolError(code, answer.reason, withDecision(answer)) };
}

/** The answer for what the dispatch threw: the window, an unrecordable change, or (rethrown) a fault. */
function thrownAnswer(error: unknown, call: CallContext): Answer {
  if (error instanceof HandedBack) {
    return { job: { jobId: error.jobId, ...(error.machine ? { machine: error.machine } : {}) } };
  }
  if (error instanceof WindowPassed) {
    const seconds = Math.round(call.attachMs / 1000);
    return {
      result: toolError(
        'TIMEOUT',
        `The command did not finish within ${seconds} s and started no job to follow; check its effect before retrying.`
      ),
    };
  }
  if (error instanceof AuditUnavailableError) {
    return {
      result: toolError(
        AUDIT_UNAVAILABLE,
        `The executor refuses "rdc ${call.entry.command}": its audit record could not be delivered (${error.message}), and a change it cannot record is not made. Retry when the account server is reachable.`
      ),
    };
  }
  throw error;
}

/** Steps 4 and 5 for one call: `runAiTool` decides and, when allowed, runs the dispatch. */
async function guarded(
  call: CallContext,
  request: ReturnType<typeof requestOf>,
  toolArgs: Record<string, unknown>
): Promise<Ran> {
  const { handle, entry } = call;
  let captured: DispatchOutcome | undefined;
  const dispatch = dispatcher(
    {
      deps: call.deps,
      busy: call.options.busy,
      handle,
      requestId: call.requestId,
      windowMs: call.attachMs,
    },
    request
  );
  try {
    const answer = await runAiTool(
      {
        principal: handle.principal,
        config: handle.config,
        agentGrant: handle.overrides,
        authorize: call.deps.authorize,
        run: async (run) => {
          captured = await dispatch(run);
          return captured;
        },
      },
      entry,
      toolArgs,
      { toolCallId: call.requestId }
    );
    if (answer.status === 'refused' || answer.status === 'approval_required') {
      return heldAnswer(answer);
    }
    return captured ? { outcome: captured, command: entry.command } : { result: GRANT_ENDED };
  } catch (error) {
    return thrownAnswer(error, call);
  }
}

/** Steps 3 to 5 for one call. */
async function runTool(call: CallContext, args: Record<string, unknown>): Promise<Ran> {
  const { entry, handle } = call;
  const command = getCommand(entry.command);
  if (!command) {
    return { result: toolError('INVALID_REQUEST', `There is no tool named ${entry.name}.`) };
  }
  const { page: _page, ...toolArgs } = args;
  const request = requestOf(entry, command, toolArgs);
  const refusal = await globRefusal(handle.scope, command, request, handle.config);
  if (refusal) return { result: toolError('POLICY_DENIED', refusal) };
  return await guarded(call, request, toolArgs);
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** The job handle of a dispatch that handed its ticket back, or undefined for one that finished. */
function jobOf(outcome: DispatchOutcome): Answer | undefined {
  const { jobId, state } = outcome.result;
  if (state !== 'running' || !jobId) return undefined;
  return { job: { jobId, ...(outcome.machineName ? { machine: outcome.machineName } : {}) } };
}

/** One tool's envelope as a result: the requested page of it, an error when the command failed. */
function resultOf(
  call: CallContext,
  args: Record<string, unknown>,
  outcome: DispatchOutcome,
  command: string,
  extra: Partial<Envelope> = {}
): CallToolResult {
  const page = typeof args.page === 'number' ? args.page : 1;
  const envelope = { ...envelopeOf(outcome, command), ...extra };
  return pageOf(JSON.stringify(envelope, null, 2), page, isPageable(call.entry), !envelope.success);
}

/**
 * `job_wait`: repeat `job status` until the job is terminal, the read fails, or the next read would pass the
 * ceiling (Design 5), each read a full call through the same checks.
 */
async function waitForJob(call: CallContext, args: Record<string, unknown>): Promise<Answer> {
  const started = Date.now();
  const ceiling = Math.min(call.attachMs, JOB_WAIT_CEILING_MS);
  const interval = jobWaitIntervalMs();
  for (;;) {
    const ran = await runTool(call, args);
    if (!('outcome' in ran)) return ran;
    const { outcome, command } = ran;
    const waited = Date.now() - started;
    const envelope = envelopeOf(outcome, command);
    if (!envelope.success || jobFinished(envelope)) {
      return { result: resultOf(call, args, outcome, command, { waited_ms: waited }) };
    }
    if (waited + interval >= ceiling) {
      const hint = { waited_ms: waited, next: 'job_wait', nextPollSeconds: interval / 1000 };
      return { result: resultOf(call, args, outcome, command, hint) };
    }
    await sleep(interval);
  }
}

/** The answer of one call, as the Worker passes it on. */
async function answerCall(call: CallContext, args: Record<string, unknown>): Promise<Answer> {
  if (call.entry.name === 'job_wait') return await waitForJob(call, args);
  const ran = await runTool(call, args);
  if (!('outcome' in ran)) return ran;
  return jobOf(ran.outcome) ?? { result: resultOf(call, args, ran.outcome, ran.command) };
}

/** An HTTP answer, or the grant handle step 1 produced. */
type Opened = { handle: AgentGrantHandle } | { status: 200 | 502; body: unknown };

/** Step 1: open or rebuild the grant session, and say what a refused or unavailable account means for the call. */
async function openGrant(
  sessions: NonNullable<ServeDeps['agentGrants']>,
  grantId: string,
  secret: string
): Promise<Opened> {
  try {
    return { handle: await sessions.acquire(grantId, secret) };
  } catch (error) {
    if (error instanceof AgentSessionRefused) return { status: 200, body: { result: GRANT_ENDED } };
    if (error instanceof AgentSessionUnavailable) {
      return { status: 502, body: { error: error.message, code: 'EXECUTOR_FAILED' } };
    }
    throw error;
  }
}

/** The refusal of a tool this server does not serve: a local tool names its registry reason (D57: it reads the caller's own disk or needs a terminal), any other name is unknown. */
function unservedTool(tool: string, entry: McpToolEntry | undefined): CallToolResult {
  const refusal = entry
    ? `The tool ${tool} runs only on the caller's own machine: ${entry.localReason ?? 'it is not served remotely'}`
    : `There is no tool named ${tool} on this server.`;
  return toolError('INVALID_REQUEST', refusal);
}

/** Register `POST /v1/mcp/call`. Container tier only: see the module doc. */
export function registerMcpCallRoute(
  app: Hono,
  deps: ServeDeps,
  options: McpCallRouteOptions
): void {
  const sessions = deps.agentGrants;
  if (deps.mode !== 'container' || !sessions) return;

  app.post(PROXY_ROUTES.mcpCall, async (c) => {
    const parsed = McpCallRequestSchema.safeParse(await c.req.json().catch(() => null));
    if (!parsed.success) {
      return c.json({ error: 'The call is malformed.', code: 'INVALID_REQUEST' }, 400);
    }
    const { grantId, secret, tool, args, requestId, attachMs } = parsed.data;

    const entry = getMcpTool(tool);
    if (entry?.surface !== 'proxy') return c.json({ result: unservedTool(tool, entry) });
    const opened = await openGrant(sessions, grantId, secret);
    if (!('handle' in opened)) return c.json(opened.body, opened.status);
    const { handle } = opened;
    if (!scopeAdmitsTool(handle.scope, entry)) {
      const outside = toolError('POLICY_DENIED', `The tool ${tool} is outside this grant's scope.`);
      return c.json({ result: outside });
    }
    return c.json(await answerCall({ deps, options, handle, entry, requestId, attachMs }, args));
  });
}

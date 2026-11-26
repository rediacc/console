/**
 * `tools/call` for the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 1 and 6 to 8).
 *
 * A call is checked against the grant's scope and its one config (D55), takes a slot of the grant's rate limiter, and is forwarded over the `EXECUTOR` binding to the grant's org executor with `{grantId, secret, tool, args, requestId, attachMs}` as the RPC body: the agent secret never reaches a URL. The container's grant session runs decide() and the command and answers either a tool result, already paged the way the local stdio server pages (D18), or the handle of a job that outlived the window.
 *
 * Limits and confirmation: a call over the grant's budget is refused with `REDIACC_RATE_LIMITED` before anything is forwarded (Design 8). When the executor answers `NEEDS_CONFIRMATION`, a client that declared elicitation gets an `input_required` result whose `requestState` is sealed to the grant, user, tool and arguments (src/confirm.ts), and the retry is forwarded with `confirm` added once the state opens; any other client gets the refusal naming the `confirm` argument (Design 6). When the executor answers `EXECUTOR_RELOCATED`, the org's placement moved: the grant is resolved again past the cache (within the same window; a lookup that outlasts it leaves the relocation answer standing) and the call is forwarded once more, to the new placement.
 *
 * Time (D15): the Worker waits at most ATTACH_WINDOW_MS in all, the first forward, the grant lookup after a relocation and the retry included, well inside the 60 s budget of the strictest clients, and asks the container to answer by EXECUTOR_ATTACH_MS so a job handle or a `job_wait` status lands inside that window. Paging: `args.page` reaches the container unchanged and the result, its cursor included, comes back unchanged; a tool whose schema takes `page` carries `_meta["anthropic/maxResultSizeChars"]` so a client that caps results lower accepts a whole page.
 */
import {
  type CallToolResult,
  type InputRequiredResult,
  inputRequired,
  isInputRequiredResult,
} from '@modelcontextprotocol/server';
import { getMcpTool, type McpToolEntry } from '../mcp/registry.js';
import { type Confirmation, hashArgs } from './confirm.js';
import type { ExecutorBinding, McpCallAnswer, McpCallForward } from './executor.js';
import type { Acquired, RateLimiter } from './rate.js';
import { type GrantContext, type GrantState, scopeAdmitsTool } from './scope.js';

/** The longest one `tools/call` waits on the executor. */
export const ATTACH_WINDOW_MS = 50_000;

/** When the container is asked to answer: early enough that its answer crosses back inside ATTACH_WINDOW_MS. */
export const EXECUTOR_ATTACH_MS = 45_000;

/** The result size a pageable tool announces: a page (100,000 characters) and its paging block fit under it, and it equals claude.ai's 150,000-character cap. */
export const MAX_RESULT_SIZE_CHARS = 150_000;

const MAX_RESULT_META = 'anthropic/maxResultSizeChars';

/** The seconds a capacity refusal asks a client to wait, as the proxy's `Retry-After` does. */
const CAPACITY_RETRY_SECONDS = 30;

/** The seconds a call whose executor answered `EXECUTOR_RELOCATED` asks a client to wait before retrying. */
const RELOCATED_RETRY_SECONDS = 5;

/** A resolved grant and the agent secret that opened it (base64url of `S`), held for the one request only. */
export interface GrantCaller {
  grant: GrantContext;
  secret: string;
}

export interface CallDeps {
  executor: ExecutorBinding | undefined;
  /** A fresh id per call; `crypto.randomUUID` unless a test pins it. */
  newRequestId?: () => string;
  /** The page where the user authorizes `grantId` again; the URL carries the grant id and nothing else. */
  reauthUrl: (grantId: string) => string;
  /** The per-grant limits (Design 8); without it a call is not limited, which only a test or a Worker deployed without the binding runs. */
  rate?: RateLimiter;
  /** Seals and opens confirmation state (Design 6); without it the `confirm` argument serves every client. */
  confirm?: Confirmation;
  /** The grant resolved again past the cache, for the retry after `EXECUTOR_RELOCATED`. */
  refreshGrant?: (caller: GrantCaller) => Promise<GrantContext | null>;
}

/** What the request around a `tools/call` carries: whether the client declared elicitation, and the round-trip fields of a retry. */
export interface CallInput {
  elicitation: boolean;
  /** The `inputResponses` of the retried request. */
  inputResponses?: Record<string, unknown>;
  /** The `requestState` of the retried request, as the client echoed it. */
  requestState?: string;
}

/** The code and the wording for a grant that stopped serving (Design 5). */
const ENDED: Record<Exclude<GrantState, 'active'>, { code: string; why: string }> = {
  expired: { code: 'REDIACC_GRANT_EXPIRED', why: 'This grant has expired.' },
  revoked: { code: 'REDIACC_GRANT_REVOKED', why: 'This grant was revoked.' },
  key_rotated: {
    code: 'REDIACC_KEY_ROTATED',
    why: "This grant stopped working when the config store's key was rotated.",
  },
};

/** The `tools/call` answer under a grant that stopped serving: the code and, when the link can be built, the re-authorization link with a line telling the model to hand it to the user. */
function grantEnded(grant: GrantContext, state: Exclude<GrantState, 'active'>, deps: CallDeps) {
  const { code, why } = ENDED[state];
  const expiredAt = grant.endedAt ?? grant.expiresAt;
  let reauthUrl: string;
  try {
    reauthUrl = deps.reauthUrl(grant.grantId);
  } catch (error) {
    // A misconfigured account origin must not turn the answer into a throw: the code still tells the client the grant ended.
    console.error(
      `mcp: the account origin is misconfigured, so the re-authorization link cannot be built: ${error instanceof Error ? error.message : String(error)}`
    );
    return toolError(code, `${why} Ask the user to authorize the agent again.`, { expiredAt });
  }
  return toolError(
    code,
    `${why} Give the user this link to authorize the agent again: ${reauthUrl}`,
    { reauthUrl, expiredAt }
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** An `isError` result whose `structuredContent` carries the code, the message, and any extra fields. */
export function toolError(
  code: string,
  message: string,
  extra: Record<string, unknown> = {}
): CallToolResult {
  return {
    content: [{ type: 'text', text: message }],
    structuredContent: { code, message, ...extra },
    isError: true,
  };
}

function isPageable(entry: McpToolEntry): boolean {
  const properties = entry.inputSchema.properties;
  return isRecord(properties) && 'page' in properties;
}

function withSizeMeta(entry: McpToolEntry, result: CallToolResult): CallToolResult {
  if (!isPageable(entry)) return result;
  return { ...result, _meta: { ...result._meta, [MAX_RESULT_META]: MAX_RESULT_SIZE_CHARS } };
}

/** The result for a job that outlived the window: its id and the tool that follows it. */
function jobHandle(job: Record<string, unknown>): CallToolResult | undefined {
  if (typeof job.jobId !== 'string' || job.jobId === '') return undefined;
  const handle = {
    jobId: job.jobId,
    ...(typeof job.machine === 'string' ? { machine: job.machine } : {}),
    next: 'job_status',
  };
  return {
    content: [{ type: 'text', text: JSON.stringify(handle, null, 2) }],
    structuredContent: handle,
    isError: false,
  };
}

/** Read the container's answer: a tool result passes through, a job becomes its handle, anything else is a server error. */
function fromAnswer(entry: McpToolEntry, answer: McpCallAnswer): CallToolResult {
  if (!answer.ok) {
    if (answer.code === 'EXECUTOR_CAPACITY') {
      return toolError('SERVER_ERROR', 'No executor capacity is free right now; retry shortly.', {
        executorCode: answer.code,
        retryAfterSeconds: CAPACITY_RETRY_SECONDS,
      });
    }
    if (answer.code === 'EXECUTOR_RELOCATED') {
      return toolError('SERVER_ERROR', 'The executor moved to a new placement; retry the call.', {
        executorCode: answer.code,
        retryAfterSeconds: RELOCATED_RETRY_SECONDS,
      });
    }
    return toolError('SERVER_ERROR', 'The executor refused the call.', {
      executorCode: answer.code,
    });
  }
  const body = answer.answer;
  if (isRecord(body) && isRecord(body.result) && Array.isArray(body.result.content)) {
    return withSizeMeta(entry, body.result as CallToolResult);
  }
  const handle = isRecord(body) && isRecord(body.job) ? jobHandle(body.job) : undefined;
  return handle ?? toolError('SERVER_ERROR', 'The executor answered in an unknown shape.');
}

/** The answer when the executor said nothing inside the window. */
function windowPassed(tool: string): CallToolResult {
  const seconds = ATTACH_WINDOW_MS / 1000;
  if (tool === 'job_wait') {
    return toolError(
      'TIMEOUT',
      `No job status within ${seconds} s; call job_wait again with the same job id.`,
      {
        next: 'job_wait',
      }
    );
  }
  return toolError(
    'TIMEOUT',
    `The executor did not answer within ${seconds} s; a job it started is listed by job_list.`,
    { next: 'job_list' }
  );
}

type Outcome = { answer: McpCallAnswer } | 'window-passed';

/** `call`'s answer, or 'window-passed' when `windowMs` ends first. */
async function withinWindow<T extends object>(
  call: Promise<T>,
  windowMs: number
): Promise<T | 'window-passed'> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const passed = new Promise<'window-passed'>((resolve) => {
    timer = setTimeout(() => resolve('window-passed'), windowMs);
  });
  try {
    return await Promise.race([call, passed]);
  } finally {
    clearTimeout(timer);
  }
}

/** The answer for a call over the grant's budget (Design 8). */
function rateLimited(reason: 'calls' | 'concurrent', retryAfterSeconds: number): CallToolResult {
  const why =
    reason === 'calls'
      ? 'This grant made too many calls in the last minute.'
      : 'This grant has too many calls running at once.';
  return toolError('REDIACC_RATE_LIMITED', `${why} Retry in ${retryAfterSeconds} s.`, {
    retryAfterSeconds,
    limit: reason,
  });
}

function structured(result: CallToolResult): Record<string, unknown> {
  return isRecord(result.structuredContent) ? result.structuredContent : {};
}

function messageOf(result: CallToolResult, fallback: string): string {
  const message = structured(result).message;
  return typeof message === 'string' ? message : fallback;
}

/** The `confirm` value the executor's refusal names, when it names one. */
function confirmValueOf(result: CallToolResult): string | undefined {
  const next = structured(result).next;
  if (!isRecord(next) || !isRecord(next.confirm)) return undefined;
  return typeof next.confirm.value === 'string' ? next.confirm.value : undefined;
}

function needsConfirmation(result: CallToolResult): boolean {
  return result.isError === true && structured(result).code === 'NEEDS_CONFIRMATION';
}

/** Whether the retry of a confirmation carries the user's yes. */
function confirmedByUser(responses: Record<string, unknown> | undefined): boolean {
  const reply = responses?.confirm;
  return (
    isRecord(reply) &&
    reply.action === 'accept' &&
    isRecord(reply.content) &&
    reply.content.confirm === true
  );
}

/** The refusal for a client that cannot be asked: it names the `confirm` argument the retry carries. */
function confirmByArgument(tool: string, result: CallToolResult): CallToolResult {
  const value = confirmValueOf(result);
  const shown = value === undefined ? 'true' : JSON.stringify(value);
  const how = `To proceed, ask the user, then call ${tool} again with the same arguments and confirm set to ${shown}.`;
  return toolError(
    'NEEDS_CONFIRMATION',
    `${messageOf(result, 'This call needs confirmation.')} ${how}`,
    {
      ...structured(result),
      confirmArgument: 'confirm',
    }
  );
}

/** The `input_required` result that asks the user, or undefined when this Worker cannot seal a state for the grant. */
async function askUser(
  deps: CallDeps,
  grant: GrantContext,
  tool: string,
  args: Record<string, unknown>,
  result: CallToolResult
): Promise<InputRequiredResult | undefined> {
  if (!(deps.confirm && deps.rate && grant.userId)) return undefined;
  let requestState: string;
  try {
    requestState = await deps.confirm.seal(
      { grantId: grant.grantId, userId: grant.userId, tool, argsHash: await hashArgs(args) },
      confirmValueOf(result)
    );
  } catch {
    // A state that cannot be sealed falls back to the `confirm` argument; the call still gets its answer.
    return undefined;
  }
  return inputRequired({
    inputRequests: {
      confirm: inputRequired.elicit({
        message: messageOf(result, `Confirm ${tool}?`),
        requestedSchema: {
          type: 'object',
          properties: { confirm: { type: 'boolean', title: 'Confirm' } },
          required: ['confirm'],
        },
      }),
    },
    requestState,
  });
}

/** The echoed state of a retry: the `confirm` value to forward, or the refusal. */
async function openConfirmation(
  deps: CallDeps,
  grant: GrantContext,
  tool: string,
  args: Record<string, unknown>,
  input: CallInput
): Promise<{ value: string | true } | { refused: CallToolResult }> {
  const stale = toolError(
    'INVALID_REQUEST',
    'The confirmation is no longer valid; call the tool again to be asked again.'
  );
  if (!(deps.confirm && deps.rate && grant.userId) || input.requestState === undefined) {
    return { refused: stale };
  }
  let opened: Awaited<ReturnType<Confirmation['open']>>;
  try {
    opened = await deps.confirm.open(
      input.requestState,
      { grantId: grant.grantId, userId: grant.userId, tool, argsHash: await hashArgs(args) },
      deps.rate
    );
  } catch {
    return {
      refused: toolError('SERVER_ERROR', 'The confirmation could not be checked; retry shortly.'),
    };
  }
  if (!opened.ok) return { refused: stale };
  if (!confirmedByUser(input.inputResponses)) {
    return { refused: toolError('POLICY_DENIED', 'The user did not confirm the call.') };
  }
  return { value: opened.confirmValue ?? true };
}

const UNANSWERED = (): CallToolResult =>
  // The RPC can fail after the executor accepted the call, so the tool may have run: the answer says so rather than inviting a blind retry (sibling of review 6eaea08c.1).
  toolError(
    'SERVER_ERROR',
    'The executor did not answer; the tool may have run. Check its effect before retrying.'
  );

const routingOf = (grant: GrantContext) => ({
  orgId: grant.orgId,
  placement: grant.placement,
  ...(grant.tier === undefined ? {} : { tier: grant.tier }),
});

/** One forward, waiting at most what is left of the window; undefined when the RPC itself failed. */
async function sendOnce(
  executor: ExecutorBinding,
  grant: GrantContext,
  forward: McpCallForward,
  startedAt: number
): Promise<Outcome | undefined> {
  try {
    return await withinWindow(
      executor.call(routingOf(grant), forward).then((answer) => ({ answer })),
      Math.max(0, ATTACH_WINDOW_MS - (Date.now() - startedAt))
    );
  } catch {
    return undefined;
  }
}

/**
 * The grant at its new placement when `outcome` is `EXECUTOR_RELOCATED` and the account now names a different, active placement; null otherwise. The pin refused before anything ran, so a second forward cannot repeat an effect, and a fresh answer naming the same placement would meet the same retired instance.
 */
async function relocatedGrant(
  deps: CallDeps,
  caller: GrantCaller,
  grant: GrantContext,
  outcome: Outcome,
  startedAt: number
): Promise<GrantContext | null> {
  if (outcome === 'window-passed' || outcome.answer.ok) return null;
  if (outcome.answer.code !== 'EXECUTOR_RELOCATED' || !deps.refreshGrant) return null;
  let fresh: GrantContext | null;
  try {
    // The lookup spends what is left of the window too: a slow account answers as if the placement had not moved.
    const looked = await withinWindow(
      deps.refreshGrant(caller).then((found) => ({ found })),
      Math.max(0, ATTACH_WINDOW_MS - (Date.now() - startedAt))
    );
    if (looked === 'window-passed') return null;
    fresh = looked.found;
  } catch {
    return null;
  }
  return fresh?.state === 'active' && fresh.placement !== grant.placement ? fresh : null;
}

/** The forward and, after `EXECUTOR_RELOCATED`, one more to the new placement. */
async function forwardWithRelocation(
  deps: CallDeps,
  caller: GrantCaller,
  executor: ExecutorBinding,
  forward: McpCallForward
): Promise<{ outcome: Outcome; grant: GrantContext } | { refused: CallToolResult }> {
  const startedAt = Date.now();
  let grant = caller.grant;
  let outcome = await sendOnce(executor, grant, forward, startedAt);
  if (!outcome) return { refused: UNANSWERED() };
  const moved = await relocatedGrant(deps, caller, grant, outcome, startedAt);
  if (moved) {
    grant = moved;
    outcome = await sendOnce(executor, grant, forward, startedAt);
    if (!outcome) return { refused: UNANSWERED() };
  }
  return { outcome, grant };
}

/** The forward, the answer, and what a `NEEDS_CONFIRMATION` answer turns into for this client. */
async function forwardCall(
  deps: CallDeps,
  caller: GrantCaller,
  entry: McpToolEntry,
  args: Record<string, unknown>,
  forwardArgs: Record<string, unknown>,
  input: CallInput
): Promise<CallToolResult | InputRequiredResult> {
  const executor = deps.executor;
  if (!executor) return toolError('SERVER_ERROR', 'This server has no executor binding.');
  const forwarded = await forwardWithRelocation(deps, caller, executor, {
    grantId: caller.grant.grantId,
    secret: caller.secret,
    tool: entry.name,
    args: forwardArgs,
    requestId: (deps.newRequestId ?? (() => crypto.randomUUID()))(),
    attachMs: EXECUTOR_ATTACH_MS,
  });
  if ('refused' in forwarded) return forwarded.refused;
  const { outcome, grant } = forwarded;
  if (outcome === 'window-passed') return windowPassed(entry.name);
  const result = fromAnswer(entry, outcome.answer);
  if (!(needsConfirmation(result) && input.elicitation)) {
    return needsConfirmation(result) ? confirmByArgument(entry.name, result) : result;
  }
  return (
    (await askUser(deps, grant, entry.name, args, result)) ?? confirmByArgument(entry.name, result)
  );
}

/** The argument names that select a config: the CLI's global `--config` and the spellings a client may use for it. */
const CONFIG_ARGUMENTS = ['config', 'config_id', 'configId'] as const;

/** The refusal when an argument names a config other than the grant's own (D55, Design 4), or undefined. The check runs before a slot is taken and before anything is forwarded. */
function configRefusal(
  grant: GrantContext,
  args: Record<string, unknown>
): CallToolResult | undefined {
  for (const key of CONFIG_ARGUMENTS) {
    const named = args[key];
    if (named === undefined || named === null) continue;
    if (typeof named !== 'string' || named !== grant.configId) {
      return toolError(
        'REDIACC_GRANT_SCOPE',
        'This grant serves one config; the call names another. Remove the config argument or ask the user for a grant on that config.',
        { argument: key }
      );
    }
  }
  return undefined;
}

/** The tool the call names, or the refusal that answers it before anything is spent. */
function admit(
  deps: CallDeps,
  grant: GrantContext,
  name: string,
  args: Record<string, unknown>
): McpToolEntry | CallToolResult {
  if (grant.state !== 'active') return grantEnded(grant, grant.state, deps);
  const entry = getMcpTool(name);
  if (entry?.surface !== 'proxy') {
    return toolError('INVALID_REQUEST', `There is no tool named ${name} on this server.`);
  }
  if (!scopeAdmitsTool(grant.scope, entry)) {
    return toolError('POLICY_DENIED', `The tool ${name} is outside this grant's scope.`);
  }
  const outOfConfig = configRefusal(grant, args);
  if (outOfConfig) return outOfConfig;
  if (!deps.executor) return toolError('SERVER_ERROR', 'This server has no executor binding.');
  return entry;
}

/** A slot of the grant's budget: the way to give it back (none without a limiter), or the refusal. */
async function takeSlot(
  deps: CallDeps,
  grantId: string
): Promise<{ release?: () => Promise<void> } | { refused: CallToolResult }> {
  if (!deps.rate) return {};
  let slot: Acquired;
  try {
    slot = await deps.rate.acquire(grantId);
  } catch {
    // The limiter is the budget's only enforcer, so a call it cannot count is refused, not let through.
    return {
      refused: toolError('SERVER_ERROR', 'The rate limiter is unavailable; retry shortly.'),
    };
  }
  return slot.ok
    ? { release: slot.release }
    : { refused: rateLimited(slot.reason, slot.retryAfterSeconds) };
}

/** `args` without its `confirm` entry. */
function withoutConfirm(args: Record<string, unknown>): Record<string, unknown> {
  const { confirm: _dropped, ...rest } = args;
  return rest;
}

/** One `tools/call` under `caller`'s grant. Never throws: every failure is an `isError` result with a code. The result is `input_required` only when `input.elicitation` is set. */
export async function callToolStep(
  deps: CallDeps,
  caller: GrantCaller,
  name: string,
  args: Record<string, unknown>,
  input: CallInput
): Promise<CallToolResult | InputRequiredResult> {
  const { grant } = caller;
  const entry = admit(deps, grant, name, args);
  if ('content' in entry) return entry;
  const slot = await takeSlot(deps, grant.grantId);
  if ('refused' in slot) return slot.refused;
  try {
    // A client that can be asked never skips the user's yes by sending `confirm` itself: the value reaches the executor only through the sealed state.
    let forwardArgs = input.elicitation ? withoutConfirm(args) : args;
    if (input.requestState !== undefined) {
      // After the slot, so a call over budget does not burn the state it carries.
      const opened = await openConfirmation(deps, grant, name, args, input);
      if ('refused' in opened) return opened.refused;
      forwardArgs = { ...args, confirm: opened.value };
    }
    return await forwardCall(deps, caller, entry, args, forwardArgs, input);
  } finally {
    // A release that fails costs the slot its lease (src/rate.ts SLOT_LEASE_MS), never the answer.
    await slot.release?.().catch(() => undefined);
  }
}

/** `callToolStep` for a caller that cannot be asked questions: the answer is always a plain tool result. */
export async function callTool(
  deps: CallDeps,
  caller: GrantCaller,
  name: string,
  args: Record<string, unknown>
): Promise<CallToolResult> {
  const result = await callToolStep(deps, caller, name, args, { elicitation: false });
  return isInputRequiredResult(result)
    ? toolError('SERVER_ERROR', 'The server asked for input a plain call cannot give.')
    : result;
}

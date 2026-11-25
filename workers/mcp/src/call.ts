/**
 * `tools/call` for the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 1 and 7).
 *
 * A call is checked against the grant's scope, then forwarded over the `EXECUTOR` binding to the grant's org executor with `{grantId, secret, tool, args, requestId, attachMs}` as the RPC body: the agent secret never reaches a URL. The container's grant session runs decide() and the command and answers either a tool result, already paged the way the local stdio server pages (D18), or the handle of a job that outlived the window.
 *
 * Time (D15): the Worker waits at most ATTACH_WINDOW_MS for the answer, well inside the 60 s budget of the strictest clients, and asks the container to answer by EXECUTOR_ATTACH_MS so a job handle or a `job_wait` status lands inside that window. Paging: `args.page` reaches the container unchanged and the result, its cursor included, comes back unchanged; a tool whose schema takes `page` carries `_meta["anthropic/maxResultSizeChars"]` so a client that caps results lower accepts a whole page.
 */
import type { CallToolResult } from '@modelcontextprotocol/server';
import { getMcpTool, type McpToolEntry } from '../../../packages/shared/src/mcp/registry.js';
import type { ExecutorBinding, McpCallAnswer } from './executor.js';
import { type GrantContext, scopeAdmitsTool } from './scope.js';

/** The longest one `tools/call` waits on the executor. */
export const ATTACH_WINDOW_MS = 50_000;

/** When the container is asked to answer: early enough that its answer crosses back inside ATTACH_WINDOW_MS. */
export const EXECUTOR_ATTACH_MS = 45_000;

/** The result size a pageable tool announces: a page (100,000 characters) and its paging block fit under it, and it stays under claude.ai's 150,000-character cap. */
export const MAX_RESULT_SIZE_CHARS = 150_000;

const MAX_RESULT_META = 'anthropic/maxResultSizeChars';

/** The seconds a capacity refusal asks a client to wait, as the proxy's `Retry-After` does. */
const CAPACITY_RETRY_SECONDS = 30;

/** A resolved grant and the agent secret that opened it (base64url of `S`), held for the one request only. */
export interface GrantCaller {
  grant: GrantContext;
  secret: string;
}

export interface CallDeps {
  executor: ExecutorBinding | undefined;
  /** A fresh id per call; `crypto.randomUUID` unless a test pins it. */
  newRequestId?: () => string;
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

async function withinWindow(call: Promise<McpCallAnswer>): Promise<Outcome> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const passed = new Promise<'window-passed'>((resolve) => {
    timer = setTimeout(() => resolve('window-passed'), ATTACH_WINDOW_MS);
  });
  try {
    return await Promise.race([call.then((answer) => ({ answer })), passed]);
  } finally {
    clearTimeout(timer);
  }
}

/** One `tools/call` under `caller`'s grant. Never throws: every failure is an `isError` result with a code. */
export async function callTool(
  deps: CallDeps,
  caller: GrantCaller,
  name: string,
  args: Record<string, unknown>
): Promise<CallToolResult> {
  const entry = getMcpTool(name);
  if (entry?.surface !== 'proxy') {
    return toolError('INVALID_REQUEST', `There is no tool named ${name} on this server.`);
  }
  const { grant } = caller;
  if (!scopeAdmitsTool(grant.scope, entry)) {
    return toolError('POLICY_DENIED', `The tool ${name} is outside this grant's scope.`);
  }
  if (!deps.executor) return toolError('SERVER_ERROR', 'This server has no executor binding.');
  const forward = {
    grantId: grant.grantId,
    secret: caller.secret,
    tool: name,
    args,
    requestId: (deps.newRequestId ?? (() => crypto.randomUUID()))(),
    attachMs: EXECUTOR_ATTACH_MS,
  };
  const routing = {
    orgId: grant.orgId,
    placement: grant.placement,
    ...(grant.tier === undefined ? {} : { tier: grant.tier }),
  };
  let outcome: Outcome;
  try {
    outcome = await withinWindow(deps.executor.call(routing, forward));
  } catch {
    return toolError('SERVER_ERROR', 'The executor could not be reached.');
  }
  return outcome === 'window-passed' ? windowPassed(name) : fromAnswer(entry, outcome.answer);
}

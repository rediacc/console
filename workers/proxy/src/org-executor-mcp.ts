/**
 * The hosted MCP `tools/call` leg of OrgExecutor (agent/plans/PLAN-rmcp-remote-worker.md Design 1 and 7): the container route, the body the MCP Worker hands over, and the answer it gets back.
 */

/**
 * The container route a hosted MCP `tools/call` reaches (agent/plans/PLAN-rmcp-remote-worker.md Design 1): the container's grant session (PLAN-rmcp-agent-grants.md Design 4) runs decide() and the command for the grant the body names.
 *
 * Only `mcpCall` reaches it, from the MCP Worker over the `McpExecutor` entrypoint (src/index.ts), which no public request can address. The public forward refuses it like the busy route, so the MCP Worker's scope and rate checks cannot be stepped around with a proxy token.
 */
export const MCP_CALL_PATH = '/v1/mcp/call';

/**
 * What the MCP Worker hands the container for one `tools/call`. The agent secret `secret` (base64url of `S`) travels in this body and nowhere else: never in a URL, a header or a log line.
 */
export interface McpCallForward {
  grantId: string;
  /** base64url of the agent secret `S`, from which the container derives the grant's keys (PLAN-rmcp-agent-grants.md Design 1). */
  secret: string;
  /** The registry tool name, e.g. `repo_list`. */
  tool: string;
  /** The tool arguments as the client sent them, `page` included: the container pages, the Worker passes the cursor through. */
  args: Record<string, unknown>;
  /** One id per call, for the audit record and the logs. */
  requestId: string;
  /** The container answers within this many milliseconds: a run still going by then answers its job handle, and `job_wait` answers its latest status. */
  attachMs: number;
}

/**
 * The answer of `mcpCall`. `answer` is the container's JSON body, passed through untouched (the proxy routes, it does not interpret); a refusal carries the Durable Object's or the container's code.
 */
export type McpCallAnswer =
  | { ok: true; answer: unknown }
  | { ok: false; code: string; status: number };

/** Whether `pathname` reaches the container's MCP call route, decoded and with repeated and trailing slashes folded the way the container's router reads it; a pathname that does not decode fails closed. */
export function isMcpCallPath(pathname: string): boolean {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return true;
  }
  return decoded.replace(/\/{2,}/g, '/').replace(/\/+$/, '') === MCP_CALL_PATH;
}

/** The code of a refused or failed container answer: the body's `code` when it names one, else a code for the HTTP status. */
async function answerCode(response: Response): Promise<string> {
  const body = (await response.json().catch(() => undefined)) as { code?: unknown } | undefined;
  return typeof body?.code === 'string' && body.code !== '' ? body.code : 'EXECUTOR_FAILED';
}

/**
 * One hosted MCP `tools/call`: POST the forward to the container's MCP call route as the request body through `send` (the Durable Object's forward, with its in-flight count and lease), and hand back the container's JSON answer untouched.
 */
export async function callMcp(
  forward: McpCallForward,
  send: (request: Request) => Promise<Response>
): Promise<McpCallAnswer> {
  const request = new Request(`http://container${MCP_CALL_PATH}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(forward),
  });
  const response = await send(request);
  if (!response.ok) return { ok: false, code: await answerCode(response), status: response.status };
  try {
    return { ok: true, answer: await response.json() };
  } catch {
    return { ok: false, code: 'EXECUTOR_FAILED', status: 502 };
  }
}

/**
 * The container route a pushed grant revocation reaches (agent/plans/PLAN-rmcp-agent-grants.md Design 5, box AG-S5): the container drops the grant's session and its cached config. Only `revokeGrant` reaches it; the public forward refuses it like the MCP call route.
 */
export const REVOKE_GRANT_PATH = '/v1/mcp/revoke';

/** The answer of `revokeGrant`: `dropped` is false when no container ran, or when the container reported it held no session for the grant. */
export type RevokeGrantAnswer =
  | { ok: true; dropped: boolean }
  | { ok: false; code: string; status: number };

/** Whether `pathname` reaches the revoke route, decoded and slash-folded like the container's router; a pathname that does not decode fails closed. */
export function isRevokeGrantPath(pathname: string): boolean {
  try {
    return (
      decodeURIComponent(pathname)
        .replace(/\/{2,}/g, '/')
        .replace(/\/+$/, '') === REVOKE_GRANT_PATH
    );
  } catch {
    return true;
  }
}

/** POST the revocation to the container's revoke route through `send` (the Durable Object's forward). The container's own `dropped` is the answer; a JSON answer that names none (an older container) counts as dropped, since the route was reached, and an answer that is not JSON is a 502 `EXECUTOR_FAILED` like `callMcp`'s. */
export async function callRevoke(
  grantId: string,
  send: (request: Request) => Promise<Response>
): Promise<RevokeGrantAnswer> {
  const response = await send(
    new Request(`http://container${REVOKE_GRANT_PATH}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ grantId }),
    })
  );
  if (!response.ok) return { ok: false, code: await answerCode(response), status: response.status };
  let answer: { dropped?: unknown } | undefined;
  try {
    answer = (await response.json()) as { dropped?: unknown } | undefined;
  } catch {
    return { ok: false, code: 'EXECUTOR_FAILED', status: 502 };
  }
  return { ok: true, dropped: answer?.dropped !== false };
}

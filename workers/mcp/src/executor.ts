/**
 * The `EXECUTOR` service binding: the proxy Worker's `McpExecutor` entrypoint (workers/proxy/src/index.ts), which pins the grant's org executor and posts the forward to its container (agent/plans/PLAN-rmcp-remote-worker.md Design 1).
 *
 * The shapes below are the wire contract of that RPC. They mirror `McpCallRouting` in workers/proxy/src/index.ts and `McpCallForward` and `McpCallAnswer` in workers/proxy/src/org-executor.ts; the two Workers build apart, so each side's tests pin the shape it sends or receives (src/__tests__/call.test.ts here, workers/proxy/src/__tests__/mcp-call.test.ts there).
 */

/** Where the call runs: the org and executor placement the grant resolved to. */
export interface McpCallRouting {
  orgId: string;
  placement: number;
  tier?: string;
}

/** The body the container receives. `secret` (base64url of `S`) is carried here and nowhere else. */
export interface McpCallForward {
  grantId: string;
  secret: string;
  tool: string;
  args: Record<string, unknown>;
  requestId: string;
  /** The container answers within this many milliseconds: a run still going answers its job handle, `job_wait` its latest status. */
  attachMs: number;
}

/** The container's JSON answer, untouched by the proxy, or the code of a refusal. */
export type McpCallAnswer =
  | { ok: true; answer: unknown }
  | { ok: false; code: string; status: number };

export interface ExecutorBinding {
  call(routing: McpCallRouting, forward: McpCallForward): Promise<McpCallAnswer>;
}

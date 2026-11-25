/**
 * The remote MCP Worker, one per region at `mcp.<region>.rediacc.cloud` (agent/plans/PLAN-rmcp-remote-worker.md).
 *
 * The transport, the `tools/call` forward and the bearer path are complete; grant resolution (RW-T3) supplies `resolveGrant` and the OAuth provider (RW-A1) `verifyAccessToken`. Until they land, every grant resolves to nothing and each MCP request is answered 401, which is the answer an unknown grant gets anyway (Design 5).
 */
import type { ExecutorBinding } from './executor.js';
import { createMcpTransport, type McpTransport } from './transport.js';

export interface Env {
  REGION: string;
  ENVIRONMENT: string;
  MCP_HOST: string;
  /** The region's account origin: the host of a re-authorization link. */
  ACCOUNT_URL: string;
  /** The proxy Worker's `McpExecutor` entrypoint (Design 1); bound per region by the deploy (RW-D2). */
  EXECUTOR?: ExecutorBinding;
}

/** Placeholder until the deploy injects the release version (RW-D2). */
const SERVER_VERSION = '0.0.0-dev';

let transport: McpTransport | undefined;

function transportFor(env: Env): McpTransport {
  transport ??= createMcpTransport({
    host: env.MCP_HOST,
    serverVersion: SERVER_VERSION,
    accountUrl: env.ACCOUNT_URL,
    resolveGrant: async () => null,
    executor: env.EXECUTOR,
  });
  return transport;
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return transportFor(env).fetch(request);
  },
};

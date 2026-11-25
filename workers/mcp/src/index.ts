/**
 * The remote MCP Worker, one per region at `mcp.<region>.rediacc.cloud` (agent/plans/PLAN-rmcp-remote-worker.md).
 *
 * The transport is complete; the credential side is not wired yet: grant resolution (RW-T3) and the bearer and OAuth paths (RW-T4, RW-A1) supply `resolveGrant`. Until they land, every grant resolves to nothing and each MCP request is answered 401, which is the answer an unknown grant gets anyway (Design 5).
 */
import { createMcpTransport, type McpTransport } from './transport.js';

export interface Env {
  REGION: string;
  ENVIRONMENT: string;
  MCP_HOST: string;
}

/** Placeholder until the deploy injects the release version (RW-D2). */
const SERVER_VERSION = '0.0.0-dev';

let transport: McpTransport | undefined;

function transportFor(env: Env): McpTransport {
  transport ??= createMcpTransport({
    host: env.MCP_HOST,
    serverVersion: SERVER_VERSION,
    resolveGrant: async () => null,
  });
  return transport;
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return transportFor(env).fetch(request);
  },
};

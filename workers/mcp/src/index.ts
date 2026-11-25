/**
 * The remote MCP Worker, one per region at `mcp.<region>.rediacc.cloud` (agent/plans/PLAN-rmcp-remote-worker.md).
 *
 * The transport, the `tools/call` forward, the bearer path, grant resolution (src/resolve.ts over the `GRANTS` binding), the rate limits (the `RATE` Durable Object) and confirmation are in place; the OAuth provider (RW-A1) supplies `verifyAccessToken`. A Worker deployed without `GRANTS` resolves every grant to nothing, so each MCP request is answered 401, which is the answer an unknown grant gets anyway (Design 5). `/internal/revoke` purges the grant cache (src/revoke.ts).
 */
import { createConfirmation } from './confirm.js';
import type { ExecutorBinding } from './executor.js';
import { doRateLimiter, MemoryRateLimiter, type RateNamespace } from './rate.js';
import { createGrantResolver, type GrantResolver, type GrantsBinding } from './resolve.js';
import { handleRevoke, REVOKE_PATH } from './revoke.js';
import { createMcpTransport, type McpTransport } from './transport.js';

export { GrantRateObject } from './rate.js';

export interface Env {
  REGION: string;
  ENVIRONMENT: string;
  MCP_HOST: string;
  /** The region's account origin: the host of a re-authorization link. */
  ACCOUNT_URL: string;
  /** The proxy Worker's `McpExecutor` entrypoint (Design 1); bound per region by the deploy (RW-D2). */
  EXECUTOR?: ExecutorBinding;
  /** The account Worker's `ExecutorIssuer` entrypoint, whose `resolveGrant` answers a grant (Design 4). */
  GRANTS?: GrantsBinding;
  /** The per-grant rate-limit Durable Object (Design 8); absent, limits hold per isolate only. */
  RATE?: RateNamespace;
  /** Worker secret sealing confirmation state (Design 6); absent, every client confirms through the `confirm` argument. */
  CONFIRM_KEY?: string;
  /** Worker secret the account presents to `/internal/revoke`; absent, the route answers 404. */
  INTERNAL_REVOKE_TOKEN?: string;
}

/** Placeholder until the deploy injects the release version (RW-D2). */
const SERVER_VERSION = '0.0.0-dev';

let transport: McpTransport | undefined;
let resolver: GrantResolver | undefined;

function resolverFor(env: Env): GrantResolver {
  const grants = env.GRANTS;
  resolver ??= createGrantResolver(grants ?? { resolveGrant: async () => null });
  return resolver;
}

function transportFor(env: Env): McpTransport {
  const grants = resolverFor(env);
  transport ??= createMcpTransport({
    host: env.MCP_HOST,
    serverVersion: SERVER_VERSION,
    accountUrl: env.ACCOUNT_URL,
    resolveGrant: grants,
    refreshGrant: grants.fresh,
    executor: env.EXECUTOR,
    rate: env.RATE ? doRateLimiter(env.RATE) : new MemoryRateLimiter(),
    confirm: env.CONFIRM_KEY ? createConfirmation({ key: env.CONFIRM_KEY }) : undefined,
  });
  return transport;
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname === REVOKE_PATH) {
      return handleRevoke(request, {
        token: env.INTERNAL_REVOKE_TOKEN,
        resolver: resolverFor(env),
      });
    }
    return transportFor(env).fetch(request);
  },
};

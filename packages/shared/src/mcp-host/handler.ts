/**
 * The remote MCP Worker, one per region at `mcp.<region>.rediacc.cloud` (agent/plans/PLAN-rmcp-remote-worker.md).
 *
 * The transport, the `tools/call` forward, the bearer path, grant resolution (resolve.ts over the `GRANTS` binding), the rate limits (the `RATE` Durable Object) and confirmation are in place; the OAuth authorization server (oauth/, RW-A1) supplies `verifyAccessToken` and owns the authorize, token, register and metadata routes. A Worker deployed without `OAUTH_KV` or `AUTH_REQUEST_KEY` serves no OAuth route and answers every OAuth access token as invalid. A Worker deployed without `GRANTS` resolves every grant to nothing, so each MCP request is answered 401, which is the answer an unknown grant gets anyway (Design 5). `/internal/revoke` purges the grant cache (revoke.ts). A request at `/g/<id>` whose id carries another region's prefix is answered `REDIACC_WRONG_REGION` with that region's URL before anything else runs (oauth/region.ts, Design 12).
 */

import { createConfirmation } from './confirm.js';
import type { ExecutorBinding } from './executor.js';
import type { HostExecutionContext, HostKvNamespace } from './host-types.js';
import { type MetricsDataset, messageOf, outcomeOf, recordCall, toolOf } from './metrics.js';
import { createOAuth, type OAuth } from './oauth/index.js';
import { wrongRegionResponse } from './oauth/region.js';
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
  /** The OAuth provider's store, one namespace per region (Design 12); absent, no OAuth route is served. */
  OAUTH_KV?: HostKvNamespace;
  /** Worker secret signing the `authRequest` handles of `/authorize` (Design 2); absent, no OAuth route is served. */
  AUTH_REQUEST_KEY?: string;
  /** Worker secret the account presents to `/internal/revoke`; absent, the route answers 404. */
  INTERNAL_REVOKE_TOKEN?: string;
  /** The Analytics Engine dataset of per-grant call counters (Design 10); absent, nothing is recorded. */
  MCP_METRICS?: MetricsDataset;
}

/** Placeholder until the deploy injects the release version (RW-D2). */
const SERVER_VERSION = '0.0.0-dev';

let transport: McpTransport | undefined;
let resolver: GrantResolver | undefined;
let oauth: OAuth | undefined;

function resolverFor(env: Env): GrantResolver {
  const grants = env.GRANTS;
  resolver ??= createGrantResolver(grants ?? { resolveGrant: async () => null });
  return resolver;
}

/** The authorization server of this isolate, or undefined while `OAUTH_KV` or `AUTH_REQUEST_KEY` is not bound. */
function oauthFor(env: Env): OAuth | undefined {
  if (!env.OAUTH_KV || !env.AUTH_REQUEST_KEY) return undefined;
  oauth ??= createOAuth({
    host: env.MCP_HOST,
    region: env.REGION,
    accountUrl: env.ACCOUNT_URL,
    authRequestKey: env.AUTH_REQUEST_KEY,
    resolveGrant: resolverFor(env).fresh,
  });
  return oauth;
}

function transportFor(env: Env): McpTransport {
  const grants = resolverFor(env);
  const auth = oauthFor(env);
  transport ??= createMcpTransport({
    host: env.MCP_HOST,
    serverVersion: SERVER_VERSION,
    accountUrl: env.ACCOUNT_URL,
    resolveGrant: grants,
    refreshGrant: grants.fresh,
    verifyAccessToken:
      auth && env.OAUTH_KV ? auth.verifyAccessToken({ OAUTH_KV: env.OAUTH_KV }) : undefined,
    executor: env.EXECUTOR,
    rate: env.RATE ? doRateLimiter(env.RATE) : new MemoryRateLimiter(),
    confirm: env.CONFIRM_KEY ? createConfirmation({ key: env.CONFIRM_KEY }) : undefined,
  });
  return transport;
}

const GRANT_PATH = /^\/g\/([A-Za-z0-9_-]{1,64})$/;

/** Record one `tools/call` after it answered: the counters of Design 10, written off the request path. */
async function observeCall(
  env: Env,
  grantId: string,
  request: Request,
  response: Response,
  startedAt: number
): Promise<void> {
  const latencyMs = Date.now() - startedAt;
  try {
    const tool = toolOf(await request.json());
    if (tool === undefined) return;
    let code = `HTTP_${response.status}`;
    if (response.ok) code = outcomeOf(messageOf(await response.text()));
    // A request the transport refused with 401 never proved its grant id, so it is not an index.
    recordCall(env.MCP_METRICS, {
      grantId: response.status === 401 ? undefined : grantId,
      region: env.REGION,
      tool,
      code,
      latencyMs,
    });
  } catch {
    // An unreadable body is not a counted call.
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: HostExecutionContext): Promise<Response> {
    if (new URL(request.url).pathname === REVOKE_PATH) {
      return handleRevoke(request, {
        token: env.INTERNAL_REVOKE_TOKEN,
        resolver: resolverFor(env),
      });
    }
    // A grant of another region is refused before any lookup, OAuth state or executor call (Design 12).
    const elsewhere = wrongRegionResponse(request, { host: env.MCP_HOST, region: env.REGION });
    if (elsewhere) return elsewhere;
    const auth = oauthFor(env);
    if (auth && env.OAUTH_KV) {
      const answered = await auth.fetch(request, { OAUTH_KV: env.OAUTH_KV }, ctx);
      if (answered) return answered;
    }
    const grantId = GRANT_PATH.exec(new URL(request.url).pathname)?.[1];
    if (!env.MCP_METRICS || grantId === undefined || request.method !== 'POST') {
      return transportFor(env).fetch(request);
    }
    const startedAt = Date.now();
    const seen = request.clone();
    const response = await transportFor(env).fetch(request);
    const observed = observeCall(env, grantId, seen, response.clone(), startedAt);
    // `waitUntil` keeps the isolate alive for the counter without delaying the answer.
    if (typeof ctx.waitUntil === 'function') ctx.waitUntil(observed);
    else await observed;
    return response;
  },
};

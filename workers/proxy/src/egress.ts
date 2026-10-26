/**
 * The container's only road to the account server, and the allowlist on it.
 *
 * The container boots with REDIACC_TOKEN set to EXECUTOR_TOKEN_PLACEHOLDER, never a real token, and addresses the account server as `http://account.internal`, which `ExecutorContainer.outboundByHost` routes here. This function forwards exactly the method and path pairs `rdc serve --mode container` calls (agent/plans/PLAN-proxy-cd-six-targets.md, Context, "Paths the container calls"):
 *
 *   - the four executor-bearer calls require `Authorization: Bearer <placeholder>` exactly, and leave with the issued token in its place;
 *   - the three unauthenticated calls leave with no Authorization at all;
 *   - anything else is answered 403 with a logged reason code, and nothing is forwarded;
 *   - an allowed bearer call is answered 503 with the reason code (`no-issuer`, `issuer-refused`, `issuer-refused:ISSUER_<CODE>` for a coded account refusal, or `issuer-malformed`) when no issued token can be had, and nothing is forwarded.
 *
 * Every forward goes to ACCOUNT (or, without that binding, to ACCOUNT_URL under `wrangler dev`). The ISSUER binding is used only through `issuedToken()`, which calls `issue(orgId)` and nothing else: no container request is ever sent to it. A refused request is decided before any token is obtained, so the container cannot drive the issuer by sending garbage.
 */

import { dropIssuedToken, type ExecutorIssuerRpc, IssuerError, issuedToken } from './issued-token';

/** The value REDIACC_TOKEN carries in the container. It authenticates nothing anywhere; the egress swaps it for the issued token. */
export const EXECUTOR_TOKEN_PLACEHOLDER = 'rediacc-executor-placeholder';

const API = '/account/api/v1';

/** The executor-bearer calls, as `METHOD path`. */
const BEARER_ROUTES: ReadonlySet<string> = new Set([
  `POST ${API}/proxy/introspect`,
  `POST ${API}/licenses/audit-events`,
  `POST ${API}/configs/executor-token`,
  `POST ${API}/configs/executor-grant`,
]);

/** The unauthenticated calls with a fixed path, as `METHOD path`. */
const OPEN_ROUTES: ReadonlySet<string> = new Set([
  `GET ${API}/telemetry/config`,
  `GET ${API}/.well-known/server-info`,
]);

/** The config pull, `GET configs/<id>` with an `X-Config-Token`, optionally `?teamId=`. */
const CONFIG_PULL_RE = /^\/account\/api\/v1\/configs\/[A-Za-z0-9_-]{1,128}$/;

type Route = 'bearer' | 'open';

/** The kind of route a request is, or the reason code it is refused with. */
export function classifyEgress(method: string, url: URL): Route | { refused: string } {
  const route = routeOf(method, url.pathname);
  if (route === undefined) return { refused: 'route-not-allowed' };
  const names = [...url.searchParams.keys()];
  const allowed =
    route.query === 'teamId'
      ? names.length === 0 || (names.length === 1 && names[0] === 'teamId')
      : url.search === '';
  return allowed ? route.kind : { refused: 'query-not-allowed' };
}

/** The allowlisted route a method and path are, with the query it admits. */
function routeOf(
  method: string,
  path: string
): { kind: Route; query: 'none' | 'teamId' } | undefined {
  const key = `${method} ${path}`;
  if (BEARER_ROUTES.has(key)) return { kind: 'bearer', query: 'none' };
  if (OPEN_ROUTES.has(key)) return { kind: 'open', query: 'none' };
  if (method === 'GET' && CONFIG_PULL_RE.test(path)) return { kind: 'open', query: 'teamId' };
  return undefined;
}

/** The env slice the egress reads. */
export interface EgressEnv {
  /** Only `idFromName` is used: the instance identity the egress cross-checks (agent/plans/PLAN-console-executor-multi-org.md, Design item 1.3). */
  EXECUTOR: { idFromName(name: string): { toString(): string } };
  ACCOUNT_URL: string;
  ACCOUNT?: Fetcher;
  ISSUER?: Service<ExecutorIssuerRpc>;
}

/** Log a refusal by reason code, method and path only (never a header or a body), then answer it. */
function refuseEgress(reason: string, method: string, url: URL, status = 403): Response {
  console.warn(`proxy: account egress refused: ${reason} ${method} ${url.pathname.slice(0, 200)}`);
  return Response.json({ error: 'refused by the executor egress', reason }, { status });
}

/** The issued token's Authorization value for a request that presented exactly the placeholder, or the refusal. Refusals are decided before the issuer is asked. */
async function issuedBearer(
  auth: string | null,
  env: EgressEnv,
  orgId: string
): Promise<string | { refused: string; status: number }> {
  if (auth === null) return { refused: 'bearer-missing', status: 403 };
  if (auth !== `Bearer ${EXECUTOR_TOKEN_PLACEHOLDER}`) {
    return { refused: 'bearer-not-placeholder', status: 403 };
  }
  try {
    return `Bearer ${await issuedToken(env.ISSUER, orgId)}`;
  } catch (error) {
    return {
      refused: error instanceof IssuerError ? error.reason : 'issuer-refused',
      status: 503,
    };
  }
}

/** The params `ExecutorContainer.pin` installs with `setOutboundByHost`: set by Durable Object code, never by the container. */
export interface AccountEgressParams {
  orgId: string;
}

/** What @cloudflare/containers hands a named outbound handler (dist/lib/container.d.ts `OutboundHandlerContext`): `containerId` is `this.ctx.id.toString()` of the calling instance. */
export interface AccountEgressContext {
  containerId: string;
  className: string;
  params?: Partial<AccountEgressParams>;
}

/**
 * The `accountEgress` named outbound handler.
 *
 * It requires `ctx.params.orgId` and requires the calling instance to be exactly the Durable Object named for that org (`ctx.containerId === env.EXECUTOR.idFromName(orgId).toString()`), so an instance can only ever obtain its own org's issued token. Both checks run before the allowlist and before the issuer is asked: a refusal here counts zero issuer calls.
 */
export async function accountEgress(
  request: Request,
  env: EgressEnv,
  ctx: AccountEgressContext | undefined
): Promise<Response> {
  const url = new URL(request.url);
  const orgId = ctx?.params?.orgId;
  if (typeof orgId !== 'string' || orgId === '') {
    return refuseEgress('org-param-missing', request.method, url);
  }
  if (ctx?.containerId !== env.EXECUTOR.idFromName(orgId).toString()) {
    return refuseEgress('container-org-mismatch', request.method, url);
  }
  return await forwardAccountEgress(request, env, orgId);
}

/** The account server no longer accepts this org's issued token (revoked, rotated): forget it so the next call mints afresh. */
function dropTokenOnRefusal(route: Route, response: Response, orgId: string): void {
  if (route === 'bearer' && response.status === 401) dropIssuedToken(orgId);
}

/** Forward one intercepted container request for the account server, when the allowlist admits it. */
export async function forwardAccountEgress(
  request: Request,
  env: EgressEnv,
  orgId: string
): Promise<Response> {
  const url = new URL(request.url);
  const route = classifyEgress(request.method, url);
  if (typeof route !== 'string') return refuseEgress(route.refused, request.method, url);

  // Fresh headers without `host`: copied from the container's request it still names account.internal, and a public fetch carrying it fails at DNS with a 530 (bench, 2026-10-24, the first deploy of this forward).
  const headers = new Headers(request.headers);
  headers.delete('host');
  headers.delete('cookie');
  headers.delete('authorization');
  if (route === 'bearer') {
    const swapped = await issuedBearer(request.headers.get('authorization'), env, orgId);
    if (typeof swapped !== 'string') {
      return refuseEgress(swapped.refused, request.method, url, swapped.status);
    }
    headers.set('authorization', swapped);
  }

  const hasBody = request.method !== 'GET' && request.method !== 'HEAD';
  const forwarded = new Request(`${env.ACCOUNT_URL}${url.pathname}${url.search}`, {
    method: request.method,
    headers,
    ...(hasBody ? { body: await request.arrayBuffer() } : {}),
    redirect: 'manual',
  });
  const via = env.ACCOUNT ? 'binding' : 'fetch';
  const response = await (env.ACCOUNT ? env.ACCOUNT.fetch(forwarded) : fetch(forwarded));
  dropTokenOnRefusal(route, response, orgId);
  // A failed call logs its path and transport only, never a header or a body: this is what `wrangler tail` shows when a container call fails.
  if (!response.ok) {
    console.warn(
      `proxy: account egress ${request.method} ${url.pathname} via ${via} -> ${response.status}`
    );
  }
  return response;
}

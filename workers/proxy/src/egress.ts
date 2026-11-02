/**
 * The container's only road to the account server, and the allowlist on it.
 *
 * The container boots with REDIACC_TOKEN set to EXECUTOR_TOKEN_PLACEHOLDER, never a real token, and addresses the account server as `http://account.internal`, which `OrgExecutor` routes here (`interceptOutboundHttp`, to the `AccountEgress` entrypoint). This function forwards exactly the method and path pairs `rdc serve --mode container` calls (agent/plans/PLAN-proxy-cd-six-targets.md, Context, "Paths the container calls"):
 *
 *   - the four executor-bearer calls require `Authorization: Bearer <placeholder>` exactly, and leave with the issued token in its place;
 *   - the three unauthenticated calls leave with no Authorization at all;
 *   - anything else is answered 403 with a logged reason code, and nothing is forwarded;
 *   - an allowed bearer call is answered 503 with the reason code (`no-issuer`, `issuer-refused`, `issuer-refused:ISSUER_<CODE>` for a coded account refusal, or `issuer-malformed`) when no issued token can be had, and nothing is forwarded.
 *
 * Every forward goes to ACCOUNT (or, without that binding, to ACCOUNT_URL under `wrangler dev`). The ISSUER binding is used only through `issuedToken()`, which calls `issue(orgId)` and nothing else: no container request is ever sent to it. A refused request is decided before any token is obtained, so the container cannot drive the issuer by sending garbage.
 *
 * `POST /account/api/v1/tunnel`, the CLI's E2E tunnel, is refused on purpose (`route-not-allowed`). Its bearer is sealed inside the envelope, so the placeholder swap cannot reach it and the account server would refuse the placeholder anyway; and the tunnel re-dispatches to any route, so admitting it would void this allowlist. The one container caller seen (bench `wrangler tail`, 2026-10-28) is the CLI's core audit flush (packages/cli/src/services/core/audit.ts via accountServerFetch), which the container tier's own audit (packages/cli/src/services/serve/audit.ts, the allowlisted `licenses/audit-events`) already covers.
 *
 * One request is answered here rather than forwarded: `AccountEgress` answers the executor's egress-unreachable report (`POST /executor/v1/egress-unreachable`) itself, from its own OrgExecutor.
 */

import { WorkerEntrypoint } from 'cloudflare:workers';
import { dropIssuedToken, type ExecutorIssuerRpc, IssuerError, issuedToken } from './issued-token';
import type { EgressReportAnswer, ExecutorEgressProps } from './org-executor';
import { executorName, placementOf } from './placement';
import { type ProbeTarget, probeTarget, type TargetRefusal } from './reachability';
import { activeSpan } from './span';

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
function classifyEgress(method: string, url: URL): Route | { refused: string } {
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

/** The env slice the forward reads. */
export interface ForwardEnv {
  ACCOUNT_URL: string;
  ACCOUNT?: Fetcher;
  ISSUER?: Service<ExecutorIssuerRpc>;
}

/** The executor's report that it could not reach a machine: a JSON `{ host, port }` body (or none, from an older executor), no query, answered by `AccountEgress` and never forwarded (agent/plans/PLAN-org-executor-connect-timeout-relocate.md Design items 3 and 7, and E13). */
const EGRESS_UNREACHABLE_PATH = '/executor/v1/egress-unreachable';
/** The most of a report body read; a longer one is refused as `report-target-invalid`. */
const MAX_REPORT_BODY_BYTES = 512;

/** The slice of an OrgExecutor stub the egress calls: only the report. */
interface EgressReporter {
  recordEgressUnreachable(
    orgId: string,
    placement: number,
    target?: ProbeTarget
  ): Promise<EgressReportAnswer>;
}

/** The body as text, or undefined once it passes `max` bytes. */
async function boundedText(request: Request, max: number): Promise<string | undefined> {
  if (request.body === null) return '';
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      await reader.cancel().catch(() => undefined);
      return undefined;
    }
    chunks.push(value);
  }
  const joined = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    joined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(joined);
}

/** The report's target: undefined for an empty body, else the admitted `{ host, port }` or why it is refused. */
async function reportTarget(request: Request): Promise<ProbeTarget | TargetRefusal | undefined> {
  let text: string | undefined;
  try {
    text = await boundedText(request, MAX_REPORT_BODY_BYTES);
  } catch {
    return { refused: 'report-target-invalid' };
  }
  if (text === undefined) return { refused: 'report-target-invalid' };
  if (text.trim() === '') return undefined;
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { refused: 'report-target-invalid' };
  }
  return probeTarget(value);
}

/** The env slice `AccountEgress` reads: the instance cross-check against the ORG_EXECUTOR namespace, and the report on the calling instance itself. */
export interface DurableEgressEnv extends ForwardEnv {
  ORG_EXECUTOR: {
    idFromName(name: string): { toString(): string };
    get(id: { toString(): string }): EgressReporter;
  };
}

/** Log a refusal by reason code, method and path only (never a header or a body), then answer it. */
function refuseEgress(reason: string, method: string, url: URL, status = 403): Response {
  console.warn(`proxy: account egress refused: ${reason} ${method} ${url.pathname.slice(0, 200)}`);
  return Response.json({ error: 'refused by the executor egress', reason }, { status });
}

/** The issued token's Authorization value for a request that presented exactly the placeholder, or the refusal. Refusals are decided before the issuer is asked. */
async function issuedBearer(
  auth: string | null,
  env: ForwardEnv,
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

/**
 * The egress entrypoint (Design A): `OrgExecutor` binds it through `ctx.exports.AccountEgress({ props: { orgId, placement, containerId } })` and `interceptOutboundHttp` routes `account.internal` to that stub.
 *
 * Props are set only by Durable Object code, so the container cannot choose them. A request is refused 403 before the allowlist and before the issuer when the props are absent or malformed (`org-param-missing`), or when `containerId` is not `env.ORG_EXECUTOR.idFromName(executorName(orgId, placement)).toString()` (`container-org-mismatch`): an instance can only ever obtain its own org's issued token, and only report for itself.
 *
 * After those checks, `POST /executor/v1/egress-unreachable` with no query is answered here. Its body, at most 512 bytes of JSON `{ host, port }`, names the machine the executor could not reach: a malformed one is 400 `report-target-invalid` and a private or loopback address, localhost or port 25 is 403 `report-target-refused`, both before any RPC; an empty body is a report with no target, which never counts. An admitted report is `recordEgressUnreachable` on the calling instance, `{ count, threshold, relocated, counted, probe }` back to the executor, and the span outcome `relocated` when the report moved the org, `target-unreachable` when it did not count, else `egress-unreachable`. It never reaches ACCOUNT and never calls the issuer. Everything else is `forwardAccountEgress`, so the allowlist and the placeholder swap are `forwardAccountEgress`.
 *
 * Not bound in any wrangler config (box G2 fences that): it is reached only through `ctx.exports`.
 */
export class AccountEgress extends WorkerEntrypoint<
  DurableEgressEnv,
  Partial<ExecutorEgressProps>
> {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const { orgId, placement, containerId } = this.ctx.props ?? {};
    const valid = placementOf(placement);
    if (
      typeof orgId !== 'string' ||
      orgId === '' ||
      valid === undefined ||
      typeof containerId !== 'string'
    ) {
      return refuseEgress('org-param-missing', request.method, url);
    }
    const self = this.env.ORG_EXECUTOR.idFromName(executorName(orgId, valid));
    if (containerId !== self.toString()) {
      return refuseEgress('container-org-mismatch', request.method, url);
    }
    if (
      request.method === 'POST' &&
      url.pathname === EGRESS_UNREACHABLE_PATH &&
      url.search === ''
    ) {
      return await this.reportUnreachable(request, self, orgId, valid, url);
    }
    return await forwardAccountEgress(request, this.env, orgId);
  }

  /** Count the report on the calling instance and answer the executor without `ok`. A refused target is a 400 or 403 with no RPC, a refused report a 403 with its reason, an instance that cannot be reached a 503. */
  private async reportUnreachable(
    request: Request,
    self: { toString(): string },
    orgId: string,
    placement: number,
    url: URL
  ): Promise<Response> {
    const span = activeSpan(this.ctx);
    const target = await reportTarget(request);
    if (target !== undefined && 'refused' in target) {
      span?.setAttribute('rediacc.proxy.outcome', `refused:${target.refused}`);
      const status = target.refused === 'report-target-invalid' ? 400 : 403;
      return refuseEgress(target.refused, 'POST', url, status);
    }
    let answer: EgressReportAnswer;
    try {
      answer = await this.env.ORG_EXECUTOR.get(self).recordEgressUnreachable(
        orgId,
        placement,
        target
      );
    } catch {
      span?.setAttribute('rediacc.proxy.outcome', 'egress-unreachable');
      return refuseEgress('report-failed', 'POST', url, 503);
    }
    span?.setAttribute('rediacc.proxy.outcome', reportOutcome(answer));
    if (!answer.ok) return refuseEgress(answer.reason, 'POST', url);
    const { count, threshold, relocated, counted, probe } = answer;
    return Response.json({ count, threshold, relocated, counted, probe });
  }
}

/** The span outcome of an answered report. */
function reportOutcome(answer: EgressReportAnswer): string {
  if (!answer.ok) return 'egress-unreachable';
  if (answer.relocated) return 'relocated';
  return answer.counted ? 'egress-unreachable' : 'target-unreachable';
}

/**
 * A 401 on a bearer route means the account server no longer accepts this org's cached token (a root block revoked it, or it was rotated): forget it and resend once with a freshly issued one, so the first call after an unblock does not fail (ML0 on bench, 2026-10-26: 2 of 8 probes within a minute of an unblock answered 401). A second 401 is returned as it is, and its token is forgotten too. The resend cannot duplicate a write: every bearer route answers 401 only from `apiTokenAuth`, before its handler runs (private/account/src/middleware/api-token.ts).
 */
async function resendWithFreshToken(
  request: Request,
  url: URL,
  env: ForwardEnv,
  orgId: string,
  headers: Headers,
  send: () => Promise<Response>
): Promise<Response> {
  dropIssuedToken(orgId);
  const reissued = await issuedBearer(request.headers.get('authorization'), env, orgId);
  if (typeof reissued !== 'string') {
    return refuseEgress(reissued.refused, request.method, url, reissued.status);
  }
  headers.set('authorization', reissued);
  const response = await send();
  if (response.status === 401) dropIssuedToken(orgId);
  return response;
}

/** Forward one intercepted container request for the account server, when the allowlist admits it. */
export async function forwardAccountEgress(
  request: Request,
  env: ForwardEnv,
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
  const body = hasBody ? await request.arrayBuffer() : undefined;
  const send = (): Promise<Response> => {
    const forwarded = new Request(`${env.ACCOUNT_URL}${url.pathname}${url.search}`, {
      method: request.method,
      headers,
      ...(body ? { body } : {}),
      redirect: 'manual',
    });
    return env.ACCOUNT ? env.ACCOUNT.fetch(forwarded) : fetch(forwarded);
  };
  const via = env.ACCOUNT ? 'binding' : 'fetch';
  let response = await send();
  if (route === 'bearer' && response.status === 401) {
    response = await resendWithFreshToken(request, url, env, orgId, headers, send);
  }
  // A failed call logs its path and transport only, never a header or a body: this is what `wrangler tail` shows when a container call fails.
  if (!response.ok) {
    console.warn(
      `proxy: account egress ${request.method} ${url.pathname} via ${via} -> ${response.status}`
    );
  }
  return response;
}

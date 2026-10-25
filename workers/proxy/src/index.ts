/**
 * The executor's container placement.
 *
 * A thin Worker in front of a Container that runs `rdc serve --mode container`.
 * The Worker does exactly two jobs and no more:
 *
 *   1. Decide WHICH container instance a request belongs to. The Durable Object
 *      id is derived from org:team, so one team's commands always land on the
 *      same warm instance. That is what makes the SSH connection pool and the
 *      decrypted-config cache worth having: a cold instance per command would
 *      throw both away every time.
 *
 *   2. Forward the request, untouched, and stream the response back. The Worker
 *      never inspects a command, never sees a config key, and never terminates
 *      the NDJSON stream. It is routing, not policy. Policy lives in the
 *      executor, where the encrypted config can actually be read.
 *
 * The Worker cannot derive org:team by itself without trusting the caller, so it
 * asks the account server whose token this is (the same introspection endpoint
 * the executor uses). Trusting a client-supplied team header here would let any
 * caller pick which tenant's warm container, and therefore which tenant's cached
 * config, to be routed to.
 */

import { Container, getContainer } from '@cloudflare/containers';

// Outbound interception (ExecutorContainer.outboundByHost) runs through this entrypoint; without the re-export a container start fails with "ctx.exports.ContainerProxy is undefined".
export { ContainerProxy } from '@cloudflare/containers';

export interface Env {
  EXECUTOR: DurableObjectNamespace<ExecutorContainer>;
  /** Account server base URL, e.g. https://eu.rediacc.com */
  ACCOUNT_URL: string;
  /** This executor fleet's own account token, carrying proxy:exec. */
  EXECUTOR_TOKEN: string;
  /**
   * Service binding to the regional account worker. `proxy.eu.rediacc.com` and `eu.rediacc.com` share a zone, and a Worker's `fetch()` to a same-zone hostname does not reach another Worker on that zone, so on the first Phase 2 deploy (2026-09-24) every introspection failed and every caller got 401. The binding is the path the www worker already uses (workers/www/wrangler.toml `[[services]]`); `fetch(ACCOUNT_URL)` remains only for a deploy without it.
   */
  ACCOUNT?: Fetcher;
  /** Region label for telemetry (`rediacc.region`, and `REDIACC_REGION` for the executor); `eu` when unset. */
  REGION?: string;
  /** Deployment environment for telemetry (`deployment.environment`); `production` when unset. */
  ENVIRONMENT?: string;
}

const DEFAULT_REGION = 'eu';
const DEFAULT_ENVIRONMENT = 'production';
const PROBE_HEADER = 'x-rediacc-probe';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The slice of the Workers runtime `Span` the proxy uses (the account Worker's middleware/tracing.ts declares the same). */
interface RuntimeSpan {
  setAttribute(key: string, value: boolean | number | string): unknown;
}

interface RuntimeTracing {
  getActiveSpan(): RuntimeSpan | undefined;
}

/** The runtime's active span, which Workers Observability exports to the `destinations` in wrangler.toml; undefined when the host supplies no tracing (tests, wrangler dev without it). */
function activeSpan(ctx: ExecutionContext | undefined): RuntimeSpan | undefined {
  try {
    return (ctx as unknown as { tracing?: RuntimeTracing } | undefined)?.tracing?.getActiveSpan?.();
  } catch {
    return undefined;
  }
}

/** Identity attributes only: never a token, org id, team id or tenant key. */
function tagRequest(span: RuntimeSpan | undefined, request: Request, env: Env): void {
  if (!span) return;
  span.setAttribute('rediacc.region', env.REGION || DEFAULT_REGION);
  span.setAttribute('deployment.environment', env.ENVIRONMENT || DEFAULT_ENVIRONMENT);
  const probe = request.headers.get(PROBE_HEADER);
  if (probe && UUID_RE.test(probe)) span.setAttribute('rediacc.probe', probe.toLowerCase());
}

/**
 * The environment `rdc serve --mode container` boots with.
 *
 * `rdc serve` refuses to start without REDIACC_TOKEN (packages/cli/src/commands/serve.ts), and it verifies callers, pulls configs and posts audit events against REDIACC_ACCOUNT_SERVER. The Worker's own EXECUTOR_TOKEN is the first; the second is ACCOUNT_URL, or `http://account.internal` when the Worker holds the ACCOUNT binding (ACCOUNT_EGRESS_HOST says why). Nothing else hands them to the container, so an instance built without them exits at boot.
 */
export function executorEnvVars(env: Env): Record<string, string> {
  return {
    REDIACC_TOKEN: env.EXECUTOR_TOKEN,
    REDIACC_ACCOUNT_SERVER: env.ACCOUNT ? `http://${ACCOUNT_EGRESS_HOST}` : env.ACCOUNT_URL,
    REDIACC_REGION: env.REGION || DEFAULT_REGION,
  };
}

/**
 * The host the container addresses the account server by when the Worker holds the ACCOUNT binding.
 *
 * EXECUTOR_TOKEN is bound to Cloudflare IP ranges, and a container's own public egress is outside them: on bench (2026-10-24) every introspection, executor-token request, config pull and audit post the container made to ACCOUNT_URL got 403 "outside Cloudflare ranges" while the Worker's own binding calls answered 200. So the container talks to this name instead, `ExecutorContainer.outboundByHost` intercepts it, and `forwardAccountEgress` sends it over the binding, where the account worker's CloudflareInternal entrypoint admits the `cloudflare`-bound token. The name resolves nowhere, so an egress that somehow escaped interception fails at DNS rather than carrying the token over plain HTTP to the internet. Not exported: workerd treats every export of the main module as an entrypoint and refuses to start on a plain string (caught by check:ci-proxy-wrangler-dev-e2e).
 */
const ACCOUNT_EGRESS_HOST = 'account.internal';

/** Forward one intercepted container request for ACCOUNT_EGRESS_HOST to the account server, over the binding when there is one. Only account API paths pass. */
export async function forwardAccountEgress(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (!url.pathname.startsWith('/account/')) {
    return Response.json({ error: 'only account paths are forwarded' }, { status: 403 });
  }
  // Fresh headers without `host`: copied from the container's request it still names account.internal, and a public fetch carrying it fails at DNS with a 530 (bench, 2026-10-24, the first deploy of this forward).
  const headers = new Headers(request.headers);
  headers.delete('host');
  const hasBody = request.method !== 'GET' && request.method !== 'HEAD';
  const forwarded = new Request(`${env.ACCOUNT_URL}${url.pathname}${url.search}`, {
    method: request.method,
    headers,
    ...(hasBody ? { body: await request.arrayBuffer() } : {}),
    redirect: 'manual',
  });
  const via = env.ACCOUNT ? 'binding' : 'fetch';
  const response = await (env.ACCOUNT ? env.ACCOUNT.fetch(forwarded) : fetch(forwarded));
  // A failed call logs its path and transport only, never a header or a body: this is what `wrangler tail` shows when a container call fails.
  if (!response.ok) {
    console.warn(
      `proxy: account egress ${request.method} ${url.pathname} via ${via} -> ${response.status}`
    );
  }
  return response;
}

export class ExecutorContainer extends Container<Env> {
  // The container's account traffic, routed through the Worker's binding (ACCOUNT_EGRESS_HOST says why). An ASSIGNMENT in a static block, never a `static outboundByHost = ...` field: @cloudflare/containers keeps the handlers in a registry behind an inherited static setter keyed by class name, and under ES2022 define semantics a field becomes an own property that shadows the setter, so the registry stays empty, ContainerProxy finds no handler and the request falls through to a plain fetch of account.internal that dies at DNS with a 530 (bench, 2026-10-24, two deploys).
  static {
    ExecutorContainer.outboundByHost = {
      [ACCOUNT_EGRESS_HOST]: (request: Request, env: unknown) =>
        forwardAccountEgress(request, env as Env),
    };
  }

  /** `rdc serve` listens here. */
  defaultPort = 8080;

  /**
   * Idle timeout before the instance sleeps.
   *
   * Long enough that a session of console work reuses one warm executor, short
   * enough that an idle tenant stops costing memory. Billing is dominated by
   * provisioned memory rather than active CPU, so a few minutes of idle is cheap
   * and a cold start (1 to 3 seconds, plus rebuilding the SSH pool) is not.
   */
  sleepAfter = '2m';

  // A class field runs after super(), so this.env is already the Worker's env here.
  envVars = executorEnvVars(this.env);
}

interface Introspection {
  active: boolean;
  scopes?: string[];
  orgId?: string;
  teamId?: string | null;
}

/**
 * Resolve the tenant behind a token, via the account server.
 *
 * Returns null for anything that is not an active proxy:exec token in a real
 * org. The Worker deliberately learns nothing else: it needs a routing key, not
 * an identity. The executor does the real verification again on its own.
 */
/**
 * Log WHY a caller was refused, as a reason code only (never a token), then answer it as a Refusal.
 *
 * Every refusal used to be a silent null, so the first Phase 2 deploy (2026-09-24) could say only "401" while its cause stayed invisible even in `wrangler tail`.
 */
function refuse(reason: string): Refusal {
  console.warn(`proxy: caller refused: ${reason}`);
  return { reason };
}

interface Refusal {
  reason: string;
}

async function resolveTenant(request: Request, env: Env): Promise<string | Refusal> {
  const auth = request.headers.get('authorization');
  const token = auth?.replace(/^Bearer\s+/i, '').trim();
  if (!token) return refuse('no-bearer');
  // Without its own token the Worker cannot ask who a caller is. Refuse as unauthenticated rather than introspecting with "Bearer undefined" (or throwing a 500).
  if (!env.EXECUTOR_TOKEN) return refuse('no-executor-token');

  const url = `${env.ACCOUNT_URL}/account/api/v1/proxy/introspect`;
  const init: RequestInit = {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.EXECUTOR_TOKEN}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({ token }),
  };
  const response = env.ACCOUNT ? await env.ACCOUNT.fetch(url, init) : await fetch(url, init);

  if (!response.ok) return refuse(`introspect-http-${response.status}`);

  // json<T>() rather than an `as` assertion: @cloudflare/workers-types declares `json<T>(): Promise<T>`, so the type parameter is the supported way to name the shape. The assertion form inferred T from its own target and was
  // therefore a no-op that @typescript-eslint/no-unnecessary-type-assertion
  // flagged the moment workers/ entered the lint scope (2026-09-06).
  const body = await response.json<Introspection>();
  if (!body.active) return refuse('inactive');
  if (!body.orgId) return refuse('no-org');
  if (!body.scopes?.includes('proxy:exec')) return refuse('no-proxy-exec-scope');

  // One warm executor per team. An org with no teams collapses to one instance, which is the right default for a small tenant.
  return `${body.orgId}:${body.teamId ?? 'default'}`;
}

export default {
  async fetch(request: Request, env: Env, ctx?: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const span = activeSpan(ctx);
    tagRequest(span, request, env);

    if (url.pathname === '/v1/health') {
      span?.setAttribute('rediacc.proxy.outcome', 'health');
      return Response.json({ ok: true });
    }

    const tenant = await resolveTenant(request, env);
    if (typeof tenant !== 'string') {
      span?.setAttribute('rediacc.proxy.outcome', `refused:${tenant.reason}`);
      return Response.json(
        { error: 'This request carried no usable token for the executor.' },
        { status: 401 }
      );
    }

    // Same tenant, same instance, every time.
    span?.setAttribute('rediacc.proxy.outcome', 'forwarded');
    const container = getContainer(env.EXECUTOR, tenant);
    return container.fetch(request);
  },
};

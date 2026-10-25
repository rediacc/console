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
import { EXECUTOR_TOKEN_PLACEHOLDER, forwardAccountEgress } from './egress';
import { type ExecutorIssuerRpc, IssuerError, issuedToken } from './issued-token';
import { readiness } from './ready';

// Outbound interception (ExecutorContainer.outboundByHost) runs through this entrypoint; without the re-export a container start fails with "ctx.exports.ContainerProxy is undefined".
export { ContainerProxy } from '@cloudflare/containers';

export interface Env {
  EXECUTOR: DurableObjectNamespace<ExecutorContainer>;
  /** Account server base URL, e.g. https://eu.rediacc.com */
  ACCOUNT_URL: string;
  /**
   * Service binding to the regional account Worker's `ExecutorIssuer` entrypoint, which mints this executor's short-lived account token (`proxy:exec` and `audit:write`) on each `issue()` call. src/issued-token.ts caches the token and renews it at 80% of its life. The container never sees it: it holds a placeholder that src/egress.ts swaps on the way out.
   */
  ISSUER?: Service<ExecutorIssuerRpc>;
  /** The `[version_metadata]` binding: `/v1/ready` answers its `id` as `workerVersion`, so a deploy smoke can tell the new version from one still rolling out. */
  CF_VERSION_METADATA?: WorkerVersionMetadata;
  /**
   * Service binding to the regional account worker. `proxy.eu.rediacc.com` and `eu.rediacc.com` share a zone, and a Worker's `fetch()` to a same-zone hostname does not reach another Worker on that zone, so on the first Phase 2 deploy (2026-09-24) every introspection failed and every caller got 401. The binding is the path the www worker already uses (workers/www/wrangler.toml `[[services]]`); `fetch(ACCOUNT_URL)` remains only for a deploy without it.
   */
  ACCOUNT?: Fetcher;
  /** Region label for telemetry (`rediacc.region`, and `REDIACC_REGION` for the executor); `eu` when unset or empty. */
  REGION?: string;
  /** Deployment environment for telemetry (`deployment.environment`); `production` when unset or empty. */
  ENVIRONMENT?: string;
}

const DEFAULT_REGION = 'eu';
const DEFAULT_ENVIRONMENT = 'production';

/** A configured var, or the fallback when the var is unset or empty (an empty [vars] entry means unset). */
function configured(value: string | undefined, fallback: string): string {
  return value === undefined || value === '' ? fallback : value;
}
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
  span.setAttribute('rediacc.region', configured(env.REGION, DEFAULT_REGION));
  span.setAttribute('deployment.environment', configured(env.ENVIRONMENT, DEFAULT_ENVIRONMENT));
  const probe = request.headers.get(PROBE_HEADER);
  if (probe && UUID_RE.test(probe)) {
    span.setAttribute('rediacc.probe', probe.toLowerCase());
    console.warn(`telemetry-probe ${probe.toLowerCase()}`);
  }
}

/**
 * The environment `rdc serve --mode container` boots with.
 *
 * `rdc serve` refuses to start without REDIACC_TOKEN (packages/cli/src/commands/serve.ts), and it verifies callers, pulls configs and posts audit events against REDIACC_ACCOUNT_SERVER. REDIACC_TOKEN is a fixed placeholder that authenticates nothing: the container's account calls all go to `http://account.internal` (ACCOUNT_EGRESS_HOST says why), and src/egress.ts swaps the placeholder for the issued token on the four calls that need it. No real token ever enters the container's environment. Nothing else hands these to the container, so an instance built without them exits at boot.
 */
export function executorEnvVars(env: Env): Record<string, string> {
  return {
    REDIACC_TOKEN: EXECUTOR_TOKEN_PLACEHOLDER,
    REDIACC_ACCOUNT_SERVER: `http://${ACCOUNT_EGRESS_HOST}`,
    REDIACC_REGION: configured(env.REGION, DEFAULT_REGION),
  };
}

/**
 * The host the container addresses the account server by.
 *
 * A container's own public egress is outside Cloudflare's ranges: on bench (2026-10-24) every introspection, executor-token request, config pull and audit post the container made to ACCOUNT_URL got 403 "outside Cloudflare ranges" while the Worker's own binding calls answered 200. So the container talks to this name instead, `ExecutorContainer.outboundByHost` intercepts it, and `forwardAccountEgress` (src/egress.ts) checks it against the allowlist, swaps the placeholder for the issued token, and sends it over the ACCOUNT binding (or to ACCOUNT_URL under `wrangler dev`, which has no binding). The name resolves nowhere, so an egress that somehow escaped interception fails at DNS rather than reaching the internet. Not exported: workerd treats every export of the main module as an entrypoint and refuses to start on a plain string (caught by check:ci-proxy-wrangler-dev-e2e).
 */
const ACCOUNT_EGRESS_HOST = 'account.internal';

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
 * Log WHY a caller was refused, as a reason code only (never a token), then answer it as a Refusal.
 *
 * Every refusal used to be a silent null, so the first Phase 2 deploy (2026-09-24) could say only "401" while its cause stayed invisible even in `wrangler tail`.
 */
function refuse(reason: string, unavailable = false): Refusal {
  console.warn(`proxy: caller refused: ${reason}`);
  return { reason, unavailable };
}

interface Refusal {
  reason: string;
  /** The Worker could not obtain its own token: a 503, not the caller's 401. */
  unavailable: boolean;
}

/**
 * Resolve the tenant behind a token, via the account server.
 *
 * Returns a Refusal for anything that is not an active proxy:exec token in a real
 * org. The Worker deliberately learns nothing else: it needs a routing key, not
 * an identity. The executor does the real verification again on its own.
 */
async function resolveTenant(request: Request, env: Env): Promise<string | Refusal> {
  const auth = request.headers.get('authorization');
  const token = auth?.replace(/^Bearer\s+/i, '').trim();
  if (!token) return refuse('no-bearer');
  // Without its own issued token the Worker cannot ask who a caller is. The executor's credentials are the Worker's problem, not the caller's, so this refusal answers 503.
  let executorToken: string;
  try {
    executorToken = await issuedToken(env.ISSUER);
  } catch (error) {
    return refuse(error instanceof IssuerError ? error.reason : 'issuer-refused', true);
  }

  const url = `${env.ACCOUNT_URL}/account/api/v1/proxy/introspect`;
  const init: RequestInit = {
    method: 'POST',
    headers: {
      authorization: `Bearer ${executorToken}`,
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

    if (url.pathname === '/v1/ready') {
      const answer = await readiness(env);
      span?.setAttribute(
        'rediacc.proxy.outcome',
        answer.status === 200 ? 'ready' : `not-ready:${answer.body.reason}`
      );
      return Response.json(answer.body, { status: answer.status });
    }

    const tenant = await resolveTenant(request, env);
    if (typeof tenant !== 'string') {
      span?.setAttribute('rediacc.proxy.outcome', `refused:${tenant.reason}`);
      if (tenant.unavailable) {
        return Response.json(
          { error: 'The executor could not obtain its own account token.' },
          { status: 503 }
        );
      }
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

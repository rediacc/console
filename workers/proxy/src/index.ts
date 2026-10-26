/**
 * The executor's container placement.
 *
 * A thin Worker in front of a Container that runs `rdc serve --mode container`.
 * The Worker does exactly two jobs and no more:
 *
 *   1. Decide WHICH container instance a request belongs to. The Durable Object
 *      id is derived from the org alone, so one org's commands always land on the
 *      same warm instance, and no other org's ever does. That is what makes the SSH connection pool and the
 *      decrypted-config cache worth having: a cold instance per command would
 *      throw both away every time.
 *
 *   2. Forward the request, untouched, and stream the response back. The Worker
 *      never inspects a command, never sees a config key, and never terminates
 *      the NDJSON stream. It is routing, not policy. Policy lives in the
 *      executor, where the encrypted config can actually be read.
 *
 * The Worker cannot derive the org by itself without trusting the caller, so it
 * asks the account Worker whose token this is (`ExecutorIssuer.route`). Trusting a client-supplied team header here would let any
 * caller pick which tenant's warm container, and therefore which tenant's cached
 * config, to be routed to.
 */

import { Container, getContainer } from '@cloudflare/containers';
import { accountEgress, EXECUTOR_TOKEN_PLACEHOLDER } from './egress';
import { type ExecutorIssuerRpc, IssuerError } from './issued-token';
import { readiness } from './ready';

// Outbound interception (ExecutorContainer.outboundByHost) runs through this entrypoint; without the re-export a container start fails with "ctx.exports.ContainerProxy is undefined".
export { ContainerProxy } from '@cloudflare/containers';

export interface Env {
  EXECUTOR: DurableObjectNamespace<ExecutorContainer>;
  /** Account server base URL, e.g. https://eu.rediacc.com */
  ACCOUNT_URL: string;
  /**
   * Service binding to the regional account Worker's `ExecutorIssuer` entrypoint: `route(bearer)` names the caller's org, and `issue(orgId)` mints that org's short-lived account token (`proxy:exec` and `audit:write`). src/issued-token.ts caches the tokens per org. The container never sees one: it holds a placeholder that src/egress.ts swaps on the way out.
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
 * The environment `rdc serve --mode container` boots with: exactly these four names.
 *
 * REDIACC_TOKEN is a fixed placeholder that authenticates nothing: the container's account calls all go to `http://account.internal` (ACCOUNT_EGRESS_HOST says why), and src/egress.ts swaps the placeholder for the org's issued token on the four calls that need it. No real token ever enters the container's environment. REDIACC_EXECUTOR_ORG_ID is the org the executor is pinned to (the executor refuses a caller of any other org). It is set by Durable Object code in `ExecutorContainer.pin`, never by the container or the caller.
 */
export function executorEnvVars(env: Env, orgId: string): Record<string, string> {
  return {
    REDIACC_TOKEN: EXECUTOR_TOKEN_PLACEHOLDER,
    REDIACC_ACCOUNT_SERVER: `http://${ACCOUNT_EGRESS_HOST}`,
    REDIACC_REGION: configured(env.REGION, DEFAULT_REGION),
    REDIACC_EXECUTOR_ORG_ID: orgId,
  };
}

/**
 * The host the container addresses the account server by.
 *
 * A container's own public egress is outside Cloudflare's ranges: on bench (2026-10-24) every introspection, executor-token request, config pull and audit post the container made to ACCOUNT_URL got 403 "outside Cloudflare ranges" while the Worker's own binding calls answered 200. So the container talks to this name instead, `ExecutorContainer.pin` installs the `accountEgress` handler for it, and `accountEgress` (src/egress.ts) checks the instance and org, checks the request against the allowlist, swaps the placeholder for the org's issued token, and sends it over the ACCOUNT binding (or to ACCOUNT_URL under `wrangler dev`, which has no binding). The name resolves nowhere, so an egress that somehow escaped interception fails at DNS rather than reaching the internet. Not exported: workerd treats every export of the main module as an entrypoint and refuses to start on a plain string (caught by check:ci-proxy-wrangler-dev-e2e).
 */
const ACCOUNT_EGRESS_HOST = 'account.internal';

/** What a failed container start says when the target is at max_instances. MU2 (agent/plans/PLAN-console-executor-multi-org.md) records the real text on bench; until then this matches the likely wordings and anything else is a start failure, never silently a capacity answer. */
const CAPACITY_ERROR =
  /capacity|max(?:imum)?[_ -]?instances|instance limit|too many (?:containers|instances)|quota/i;

export class ExecutorContainer extends Container<Env> {
  // The named outbound handlers. An ASSIGNMENT in a static block, never a `static outboundHandlers = ...` field: @cloudflare/containers keeps the handlers in a registry behind an inherited static setter keyed by class name, and under ES2022 define semantics a field becomes an own property that shadows the setter, so the registry stays empty, ContainerProxy finds no handler and the request falls through to a plain fetch of account.internal that dies at DNS with a 530 (bench, 2026-10-24, two deploys). There is deliberately no static outboundByHost: an instance that was never pinned has no handler for account.internal and its call is refused.
  static {
    ExecutorContainer.outboundHandlers = {
      accountEgress: (request: Request, env: unknown, ctx: unknown) =>
        accountEgress(request, env as Env, ctx as Parameters<typeof accountEgress>[2]),
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

  /** The org this instance serves, set once by `pin`. */
  private pinnedOrg: string | undefined;

  /**
   * Pin this instance to one org and start its container. Called by the Worker with the org `ExecutorIssuer.route` named, before it forwards a request.
   *
   * The instance must be the Durable Object named for `orgId`, so an org that is not this instance's own name cannot be pinned; a second pin with another org is refused. The container starts with the per-instance env (MU3: `startOptions.envVars` replaces the class-level `envVars` wholesale in @cloudflare/containers 0.3.7, it is not merged, so all four names are passed) and `account.internal` is routed to `accountEgress` with `{ orgId }`.
   */
  async pin(orgId: string): Promise<void> {
    if (typeof orgId !== 'string' || orgId === '') throw new Error('pin-org-invalid');
    if (!this.ctx.id.equals(this.env.EXECUTOR.idFromName(orgId))) {
      throw new Error('pin-id-mismatch');
    }
    if (this.pinnedOrg !== undefined && this.pinnedOrg !== orgId) {
      throw new Error('pin-org-conflict');
    }
    this.pinnedOrg = orgId;
    const envVars = executorEnvVars(this.env, orgId);
    // A later start (after the instance slept) that does not go through `pin` still carries the org.
    this.envVars = envVars;
    await this.setOutboundByHost(ACCOUNT_EGRESS_HOST, 'accountEgress', {
      orgId,
    });
    await this.startAndWaitForPorts({ startOptions: { envVars } });
  }
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
 * Resolve the org behind a token, via the account Worker's `ExecutorIssuer.route`.
 *
 * Returns a Refusal for anything that is not an active proxy:exec token of an entitled org. The Worker deliberately learns nothing else: it needs a routing key, not an identity. The executor does the real verification again on its own.
 */
async function resolveTenant(request: Request, env: Env): Promise<string | Refusal> {
  const auth = request.headers.get('authorization');
  const token = auth?.replace(/^Bearer\s+/i, '').trim();
  if (!token) return refuse('no-bearer');
  if (!env.ISSUER) return refuse('no-issuer', true);
  // An issuer that cannot be reached is the Worker's problem, not the caller's: a 503, not a 401.
  let answer: Awaited<ReturnType<ExecutorIssuerRpc['route']>>;
  try {
    answer = await env.ISSUER.route(token);
  } catch (error) {
    return refuse(error instanceof IssuerError ? error.reason : 'issuer-route-failed', true);
  }
  const orgId: unknown = (answer as { orgId?: unknown } | undefined)?.orgId;
  if (typeof orgId !== 'string' || orgId === '') return refuse('route-refused');
  // One warm executor per org: the Durable Object name is the org alone.
  return orgId;
}

/** Pin the org's instance and start it. Answers undefined on success, else the response for a failed start. */
async function startExecutor(
  container: { pin(orgId: string): Promise<void> },
  orgId: string,
  span: RuntimeSpan | undefined
): Promise<Response | undefined> {
  try {
    await container.pin(orgId);
    return undefined;
  } catch (error) {
    const message = error instanceof Error ? error.message : '';
    if (CAPACITY_ERROR.test(message)) {
      console.warn('proxy: executor start refused: capacity');
      span?.setAttribute('rediacc.proxy.outcome', 'capacity');
      return Response.json(
        {
          error: 'No executor capacity is free right now.',
          code: 'EXECUTOR_CAPACITY',
        },
        { status: 503, headers: { 'retry-after': '30' } }
      );
    }
    console.warn('proxy: executor start failed');
    span?.setAttribute('rediacc.proxy.outcome', 'start-failed');
    return Response.json(
      {
        error: 'The executor could not be started.',
        code: 'EXECUTOR_START_FAILED',
      },
      { status: 503 }
    );
  }
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
          { error: 'The executor could not resolve this caller.' },
          { status: 503 }
        );
      }
      return Response.json(
        { error: 'This request carried no usable token for the executor.' },
        { status: 401 }
      );
    }

    // Same org, same instance, every time.
    const container = getContainer(env.EXECUTOR, tenant);
    const failed = await startExecutor(container, tenant, span);
    if (failed) return failed;
    span?.setAttribute('rediacc.proxy.outcome', 'forwarded');
    return container.fetch(request);
  },
};

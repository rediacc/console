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
import type { ExecutorCapacity } from './capacity';
import { accountEgress } from './egress';
import { type ExecutorIssuerRpc, IssuerError } from './issued-token';
import {
  ACCOUNT_EGRESS_HOST,
  type ExecutorRefusalCode,
  executorEnv,
  type OrgExecutor,
  type PinAnswer,
} from './org-executor';
import { readiness } from './ready';
import {
  chooseSize,
  type ExecutorTier,
  heavyFullFallback,
  oomRecent,
  type SizeChoice,
  tierOf,
} from './sizing';

// Every export of the main module is an entrypoint or a Durable Object class: workerd refuses to start on a plain value, and wrangler refuses a deploy whose bound Durable Object classes are not exported here.
// Outbound interception (ExecutorContainer.outboundByHost) runs through this entrypoint; without the re-export a container start fails with "ctx.exports.ContainerProxy is undefined".
export { ContainerProxy } from '@cloudflare/containers';
// The cap coordinator, bound as EXECUTOR_CAPACITY.
export { ExecutorCapacity } from './capacity';
// The `durable_object` backend's egress, reached through `ctx.exports.AccountEgress` by OrgExecutor (Design A).
export { AccountEgress } from './egress';
// The `durable_object` backend's per-org executor, bound as ORG_EXECUTOR.
export { OrgExecutor } from './org-executor';

export interface Env {
  /** The legacy backend (the @cloudflare/containers `ExecutorContainer`), routed to when EXECUTOR_BACKEND is `container`. */
  EXECUTOR: DurableObjectNamespace<ExecutorContainer>;
  /** The `durable_object` backend (src/org-executor.ts), routed to when EXECUTOR_BACKEND is `durable`. A version routed to it without the binding refuses with EXECUTOR_START_FAILED. */
  ORG_EXECUTOR?: DurableObjectNamespace<OrgExecutor>;
  /** The target's cap coordinator (src/capacity.ts); OrgExecutor holds a lease on it for each running container. */
  EXECUTOR_CAPACITY?: DurableObjectNamespace<ExecutorCapacity>;
  /**
   * Which backend this version routes every request to: `durable` for ORG_EXECUTOR, anything else (`container`, unset) for EXECUTOR. Generated per target by proxy_configs.py `BACKEND_BY_TARGET`. Chosen per version, never per request, so one version never routes an org to both backends.
   */
  EXECUTOR_BACKEND?: string;
  /** The coordinator's cap and heavy sub-cap, decimal strings (src/capacity.ts `capFrom`). */
  EXECUTOR_CAP?: string;
  EXECUTOR_HEAVY_CAP?: string;
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
 * The legacy backend's container. The environment it boots with is src/org-executor.ts `executorEnv`, the same four names OrgExecutor starts with: REDIACC_TOKEN is a fixed placeholder that authenticates nothing, and REDIACC_EXECUTOR_ORG_ID is set here by Durable Object code in `pin`, never by the container or the caller.
 *
 * The container addresses the account server as ACCOUNT_EGRESS_HOST (`account.internal`). A container's own public egress is outside Cloudflare's ranges: on bench (2026-10-24) every introspection, executor-token request, config pull and audit post the container made to ACCOUNT_URL got 403 "outside Cloudflare ranges" while the Worker's own binding calls answered 200. So `pin` installs the `accountEgress` handler for that name, and `accountEgress` (src/egress.ts) checks the instance and org, checks the request against the allowlist, swaps the placeholder for the org's issued token, and sends it over the ACCOUNT binding (or to ACCOUNT_URL under `wrangler dev`, which has no binding). The name resolves nowhere, so an egress that somehow escaped interception fails at DNS rather than reaching the internet.
 */
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
    const envVars = executorEnv(this.env, orgId);
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
interface Tenant {
  orgId: string;
  tier: ExecutorTier;
}

async function resolveTenant(request: Request, env: Env): Promise<Tenant | Refusal> {
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
  const routed = answer as { orgId?: unknown; tier?: unknown } | undefined;
  const orgId = routed?.orgId;
  if (typeof orgId !== 'string' || orgId === '') return refuse('route-refused');
  // One warm executor per org: the Durable Object name is the org alone. A missing tier (an older account Worker) is `standard`.
  return { orgId, tier: tierOf(routed?.tier) };
}

/** The 503 for a refused start. Only EXECUTOR_CAPACITY carries `Retry-After: 30`, and its outcome is `capacity`. */
function startRefused(code: ExecutorRefusalCode, span: RuntimeSpan | undefined): Response {
  if (code === 'EXECUTOR_CAPACITY') {
    console.warn('proxy: executor start refused: capacity');
    span?.setAttribute('rediacc.proxy.outcome', 'capacity');
    return Response.json(
      { error: 'No executor capacity is free right now.', code },
      { status: 503, headers: { 'retry-after': '30' } }
    );
  }
  console.warn('proxy: executor start failed');
  span?.setAttribute('rediacc.proxy.outcome', 'start-failed');
  return Response.json({ error: 'The executor could not be started.', code }, { status: 503 });
}

/** Pin the legacy backend's instance and start it. Answers undefined on success, else the response for a failed start. Any failure is EXECUTOR_START_FAILED: only the coordinator of the `durable` backend answers capacity, and error text is never guessed at. */
async function startLegacyExecutor(
  container: { pin(orgId: string): Promise<void> },
  orgId: string,
  span: RuntimeSpan | undefined
): Promise<Response | undefined> {
  try {
    await container.pin(orgId);
    return undefined;
  } catch {
    return startRefused('EXECUTOR_START_FAILED', span);
  }
}

/** The legacy backend: the org's ExecutorContainer, pinned and started, then forwarded to. */
async function viaContainer(
  request: Request,
  env: Env,
  tenant: Tenant,
  span: RuntimeSpan | undefined
): Promise<Response> {
  // Same org, same instance, every time.
  const container = getContainer(env.EXECUTOR, tenant.orgId);
  const failed = await startLegacyExecutor(container, tenant.orgId, span);
  if (failed) return failed;
  span?.setAttribute('rediacc.proxy.outcome', 'forwarded');
  return container.fetch(request);
}

/** The slice of an OrgExecutor stub the Worker calls. */
interface OrgExecutorStub {
  oomAt(): Promise<number | undefined>;
  oomHeavyAt(): Promise<number | undefined>;
  pin(orgId: string, size: SizeChoice['size']): Promise<PinAnswer>;
  fetch(request: Request): Promise<Response>;
}

/**
 * Size the start (src/sizing.ts) and pin the org's OrgExecutor. A heavy start the coordinator refuses as `heavy-full` is retried LIGHT only for an org that is HEAVY by its tier alone; an OOM-flagged org gets the capacity refusal. Throws when the Durable Object cannot be reached.
 */
async function pinSized(
  stub: OrgExecutorStub,
  tenant: Tenant,
  span: RuntimeSpan | undefined
): Promise<PinAnswer> {
  const choice = chooseSize(tenant.tier, await stub.oomAt(), Date.now());
  span?.setAttribute('rediacc.proxy.size', choice.size);
  const answer = await stub.pin(tenant.orgId, choice.size);
  if (answer.ok || answer.code !== 'EXECUTOR_CAPACITY' || answer.reason !== 'heavy-full') {
    return answer;
  }
  const fallback = heavyFullFallback(choice);
  if (fallback === undefined) return answer;
  span?.setAttribute('rediacc.proxy.size', fallback);
  return await stub.pin(tenant.orgId, fallback);
}

/** Whether the org's heavy container ran out of memory within OOM_WINDOW_MS: nothing larger exists, so the request is still served and only the outcome says so. A Durable Object that cannot answer is not an OOM. */
async function heavyOomRecent(stub: OrgExecutorStub, size: SizeChoice['size']): Promise<boolean> {
  if (size !== 'heavy') return false;
  try {
    return oomRecent(await stub.oomHeavyAt(), Date.now());
  } catch {
    return false;
  }
}

/** The `durable_object` backend: the org's OrgExecutor, sized, pinned and forwarded to. Every refusal is the coordinator's or the Durable Object's code, never a guess. */
async function viaOrgExecutor(
  request: Request,
  env: Env,
  tenant: Tenant,
  span: RuntimeSpan | undefined
): Promise<Response> {
  const namespace = env.ORG_EXECUTOR;
  if (!namespace) return startRefused('EXECUTOR_START_FAILED', span);
  const stub = namespace.get(namespace.idFromName(tenant.orgId)) as unknown as OrgExecutorStub;
  let answer: PinAnswer;
  try {
    answer = await pinSized(stub, tenant, span);
  } catch {
    return startRefused('EXECUTOR_START_FAILED', span);
  }
  if (!answer.ok) return startRefused(answer.code, span);
  // The size the container runs on, which a running container keeps from its start.
  span?.setAttribute('rediacc.proxy.size', answer.size);
  span?.setAttribute(
    'rediacc.proxy.outcome',
    (await heavyOomRecent(stub, answer.size)) ? 'oom-heavy' : 'forwarded'
  );
  return stub.fetch(request);
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
    if ('reason' in tenant) {
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

    // The backend is the version's, never the request's (Design item 2).
    return env.EXECUTOR_BACKEND === 'durable'
      ? viaOrgExecutor(request, env, tenant, span)
      : viaContainer(request, env, tenant, span);
  },
};

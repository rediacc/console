/**
 * The executor's container placement.
 *
 * A thin Worker in front of the per-org `OrgExecutor` Durable Object, whose container runs `rdc serve --mode container`.
 * The Worker does exactly two jobs and no more:
 *
 *   1. Decide WHICH container instance a request belongs to. The Durable Object
 *      name is derived from the org and its placement
 *      (src/placement.ts `executorName`), so one org's commands always land on the
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

import type { ExecutorCapacity } from './capacity';
import { type ExecutorIssuerRpc, IssuerError } from './issued-token';
import type { ExecutorRefusalCode, OrgExecutor, PinAnswer } from './org-executor';
import { executorName, placementOf } from './placement';
import { readiness } from './ready';
import {
  chooseSize,
  type ExecutorTier,
  heavyFullFallback,
  oomRecent,
  type SizeChoice,
  tierOf,
} from './sizing';
import { activeSpan, type RuntimeSpan } from './span';

// Every export of the main module is an entrypoint or a Durable Object class: workerd refuses to start on a plain value, and wrangler refuses a deploy whose bound Durable Object classes are not exported here.
// The cap coordinator, bound as EXECUTOR_CAPACITY.
export { ExecutorCapacity } from './capacity';
// The egress, reached through `ctx.exports.AccountEgress` by OrgExecutor (Design A).
export { AccountEgress } from './egress';
// The per-org executor, bound as ORG_EXECUTOR.
export { OrgExecutor } from './org-executor';

export interface Env {
  /** The per-org executor (src/org-executor.ts). A version deployed without the binding refuses with EXECUTOR_START_FAILED. */
  ORG_EXECUTOR?: DurableObjectNamespace<OrgExecutor>;
  /** The target's cap coordinator (src/capacity.ts); OrgExecutor holds a lease on it for each running container. */
  EXECUTOR_CAPACITY?: DurableObjectNamespace<ExecutorCapacity>;
  /** The coordinator's cap and heavy sub-cap, decimal strings (src/capacity.ts `capFrom`). */
  EXECUTOR_CAP?: string;
  EXECUTOR_HEAVY_CAP?: string;
  /** Account server base URL, e.g. https://eu.rediacc.com */
  ACCOUNT_URL: string;
  /**
   * Service binding to the regional account Worker's `ExecutorIssuer` entrypoint: `route(bearer)` names the caller's org and its executor placement, `issue(orgId)` mints that org's short-lived account token (`proxy:exec` and `audit:write`), and `relocate(orgId, fromPlacement)` is called only by OrgExecutor when its container keeps failing to reach a machine. src/issued-token.ts caches the tokens per org. The container never sees one: it holds a placeholder that src/egress.ts swaps on the way out.
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
  /** The org's executor placement (D1 `organizations.executor_placement`): the Durable Object is `executorName(orgId, placement)`. */
  placement: number;
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
  const routed = answer as { orgId?: unknown; tier?: unknown; placement?: unknown } | undefined;
  const orgId = routed?.orgId;
  if (typeof orgId !== 'string' || orgId === '') return refuse('route-refused');
  // Never guessed as 0, because 0 may be the very object the org moved away from. An account Worker without migration 0068 answers no placement: the Worker's problem, so a 503.
  const placement = placementOf(routed?.placement);
  if (placement === undefined) return refuse('route-placement-missing', true);
  // A missing tier is `standard`.
  return { orgId, tier: tierOf(routed?.tier), placement };
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

/** The slice of an OrgExecutor stub the Worker calls, typed from the class itself so a signature change there fails the typecheck here. */
type OrgExecutorStub = Pick<OrgExecutor, 'oomAt' | 'oomHeavyAt' | 'pin'> & {
  fetch(request: Request): Promise<Response>;
};

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
  const answer = await stub.pin(tenant.orgId, tenant.placement, choice.size);
  if (answer.ok || answer.code !== 'EXECUTOR_CAPACITY' || answer.reason !== 'heavy-full') {
    return answer;
  }
  const fallback = heavyFullFallback(choice);
  if (fallback === undefined) return answer;
  span?.setAttribute('rediacc.proxy.size', fallback);
  return await stub.pin(tenant.orgId, tenant.placement, fallback);
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

/** The org's OrgExecutor at its placement, sized and pinned. Throws when the Durable Object cannot be reached. */
async function pinAtPlacement(
  namespace: NonNullable<Env['ORG_EXECUTOR']>,
  tenant: Tenant,
  span: RuntimeSpan | undefined
): Promise<{ stub: OrgExecutorStub; answer: PinAnswer }> {
  const name = executorName(tenant.orgId, tenant.placement);
  const stub = namespace.get(namespace.idFromName(name)) as unknown as OrgExecutorStub;
  return { stub, answer: await pinSized(stub, tenant, span) };
}

/** After an `EXECUTOR_RELOCATED` pin: the tenant at its new placement, when the issuer now names a higher one for the same org, else undefined. */
async function relocatedTenant(
  request: Request,
  env: Env,
  tenant: Tenant
): Promise<Tenant | undefined> {
  const again = await resolveTenant(request, env);
  if ('reason' in again) return undefined;
  if (again.orgId !== tenant.orgId || again.placement <= tenant.placement) return undefined;
  return again;
}

/** The outcome of a forwarded request: `egress-unreachable` while the container's latest egress-unreachable report is recent, `oom-heavy` for a heavy container that recently ran out of memory, else `forwarded`. */
async function forwardOutcome(
  stub: OrgExecutorStub,
  answer: Extract<PinAnswer, { ok: true }>
): Promise<string> {
  if (answer.egressUnreachableRecent) return 'egress-unreachable';
  return (await heavyOomRecent(stub, answer.size)) ? 'oom-heavy' : 'forwarded';
}

/**
 * The org's OrgExecutor at its placement, sized, pinned and forwarded to. Every refusal is the coordinator's or the Durable Object's code, never a guess.
 *
 * An `EXECUTOR_RELOCATED` pin means the instance retired after the org moved (agent/plans/PLAN-org-executor-connect-timeout-relocate.md Design item 7): the issuer is asked once more, and the request is re-routed once when the placement went up. Anything else, including a second `EXECUTOR_RELOCATED`, is a 503 EXECUTOR_START_FAILED.
 */
async function viaOrgExecutor(
  request: Request,
  env: Env,
  tenant: Tenant,
  span: RuntimeSpan | undefined
): Promise<Response> {
  const namespace = env.ORG_EXECUTOR;
  if (!namespace) return startRefused('EXECUTOR_START_FAILED', span);
  let pinned: { stub: OrgExecutorStub; answer: PinAnswer };
  try {
    pinned = await pinAtPlacement(namespace, tenant, span);
    if (!pinned.answer.ok && pinned.answer.code === 'EXECUTOR_RELOCATED') {
      const moved = await relocatedTenant(request, env, tenant);
      if (moved === undefined) return startRefused('EXECUTOR_START_FAILED', span);
      pinned = await pinAtPlacement(namespace, moved, span);
    }
  } catch {
    return startRefused('EXECUTOR_START_FAILED', span);
  }
  const { stub, answer } = pinned;
  if (!answer.ok) {
    return startRefused(
      answer.code === 'EXECUTOR_RELOCATED' ? 'EXECUTOR_START_FAILED' : answer.code,
      span
    );
  }
  // The size the container runs on, which a running container keeps from its start.
  span?.setAttribute('rediacc.proxy.size', answer.size);
  span?.setAttribute('rediacc.proxy.outcome', await forwardOutcome(stub, answer));
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

    return viaOrgExecutor(request, env, tenant, span);
  },
};

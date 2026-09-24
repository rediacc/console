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
}

/**
 * The environment `rdc serve --mode container` boots with.
 *
 * `rdc serve` refuses to start without REDIACC_TOKEN (packages/cli/src/commands/serve.ts), and it verifies callers, pulls configs and posts audit events against REDIACC_ACCOUNT_SERVER. The Worker's own EXECUTOR_TOKEN and ACCOUNT_URL are those two values; nothing else hands them to the container, so an instance built without them exits at boot.
 */
export function executorEnvVars(env: Env): Record<string, string> {
  return {
    REDIACC_TOKEN: env.EXECUTOR_TOKEN,
    REDIACC_ACCOUNT_SERVER: env.ACCOUNT_URL,
  };
}

export class ExecutorContainer extends Container<Env> {
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
 * Log WHY a caller was refused, as a reason code only (never a token), then answer null.
 *
 * Every refusal used to be a silent null, so the first Phase 2 deploy (2026-09-24) could say only "401" while its cause stayed invisible even in `wrangler tail`.
 */
function refuse(reason: string): null {
  console.warn(`proxy: caller refused: ${reason}`);
  return null;
}

async function resolveTenant(request: Request, env: Env): Promise<string | null> {
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
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/v1/health') {
      return Response.json({ ok: true });
    }

    const tenant = await resolveTenant(request, env);
    if (!tenant) {
      return Response.json(
        { error: 'This request carried no usable token for the executor.' },
        { status: 401 }
      );
    }

    // Same tenant, same instance, every time.
    const container = getContainer(env.EXECUTOR, tenant);
    return container.fetch(request);
  },
};

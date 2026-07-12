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
}

export class ExecutorContainer extends Container {
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
  sleepAfter = '4m';

  envVars = {
    REDIACC_EXECUTOR_MODE: 'container',
  };
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
async function resolveTenant(request: Request, env: Env): Promise<string | null> {
  const auth = request.headers.get('authorization');
  const token = auth?.replace(/^Bearer\s+/i, '').trim();
  if (!token) return null;

  const response = await fetch(`${env.ACCOUNT_URL}/account/api/v1/proxy/introspect`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.EXECUTOR_TOKEN}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({ token }),
  });

  if (!response.ok) return null;

  const body = (await response.json()) as Introspection;
  if (!body.active || !body.orgId) return null;
  if (!body.scopes?.includes('proxy:exec')) return null;

  // One warm executor per team. An org with no teams collapses to one instance,
  // which is the right default for a small tenant.
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

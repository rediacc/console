/**
 * `POST /v1/mcp/revoke` on a DAEMON executor (agent/plans/PLAN-rmcp-agent-grants.md Design 5, box AG-OP1).
 *
 * On Cloudflare the proxy's `OrgExecutor.revokeGrant` posts the revocation to the container, which registers
 * the route inside the container tier (mcp-call-route.ts) with no bearer, since only the Durable Object can
 * reach it. A daemon is a network service: the account server's push arrives over HTTP through the per-org
 * executor resolver, so this route takes a bearer, asks the account server whose it is (as every other
 * daemon route does) and admits only an owner or admin of the org the sessions serve. A refused caller never
 * learns whether the grant is held.
 */

import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { Hono } from 'hono';
import { z } from 'zod';
import { AuthError } from './auth.js';
import type { ServeDeps } from './deps.js';

const REVOKE_ROLES = new Set(['owner', 'admin']);

/** The grant id alone, never the secret. */
const RevokeRequestSchema = z.strictObject({ grantId: z.string().regex(/^[A-Za-z0-9_-]{1,128}$/) });

function bearerOf(header: string | undefined): string | undefined {
  const match = /^Bearer\s+(\S+)$/i.exec(header?.trim() ?? '');
  return match?.[1];
}

/** The refusal for a caller who may not revoke, or undefined when the bearer is an owner or admin of `orgId`. */
async function refusal(
  deps: ServeDeps,
  orgId: string,
  header: string | undefined
): Promise<{ status: 401 | 403; error: string } | undefined> {
  const token = bearerOf(header);
  if (!token) return { status: 401, error: 'This request carried no token.' };
  try {
    const principal = await deps.auth.verify(token);
    const admitted = principal.orgId === orgId && REVOKE_ROLES.has(principal.orgRole);
    return admitted ? undefined : { status: 403, error: 'This token cannot revoke agent grants.' };
  } catch (error) {
    if (error instanceof AuthError) return { status: error.status, error: error.message };
    throw error;
  }
}

/** Register the daemon's revoke route. A container, or a daemon that serves no grants, registers nothing. */
export function registerAgentGrantRevokeRoute(app: Hono, deps: ServeDeps): void {
  const sessions = deps.agentGrants;
  if (deps.mode !== 'daemon' || !sessions) return;

  app.post(PROXY_ROUTES.mcpRevoke, async (c) => {
    const refused = await refusal(deps, sessions.orgId, c.req.header('authorization'));
    if (refused) return c.json({ error: refused.error }, refused.status);
    const parsed = RevokeRequestSchema.safeParse(await c.req.json().catch(() => null));
    if (!parsed.success) {
      return c.json({ error: 'The revocation is malformed.', code: 'INVALID_REQUEST' }, 400);
    }
    return c.json({ dropped: sessions.revoke(parsed.data.grantId) });
  });
}

/**
 * Grants for the Worker suites: a fixed agent secret, its bearer, and a resolver that answers a grant only for the auth tag that secret derives, the way the account Worker's `resolveGrant` does (agent/plans/PLAN-rmcp-remote-worker.md Design 4).
 */
import { deriveAuthTag, formatAgentBearer } from '../../../config-crypto/agent-grant.js';
import type { GrantContext, GrantScope } from '../../scope.js';
import type { ResolveGrant } from '../../transport.js';

export const FULL_SCOPE: GrantScope = { readOnly: false, tools: null, machines: null, repos: null };

/** 32 fixed bytes: the agent secret `S` of every grant these suites build. */
export const SECRET_BYTES = new Uint8Array(32).map((_, i) => (i * 37 + 11) % 256);

export function bearerFor(grantId: string, secret: Uint8Array = SECRET_BYTES): string {
  return formatAgentBearer(grantId, secret);
}

/** The base64url text of `S`, as a forward body carries it. */
export function secretTextOf(grantId: string, secret: Uint8Array = SECRET_BYTES): string {
  const bearer = bearerFor(grantId, secret);
  return bearer.slice(bearer.indexOf('.') + 1);
}

/** An active grant of org `org-test` at placement 0, expiring in 2099. */
export function activeGrant(grantId: string, overrides: Partial<GrantContext> = {}): GrantContext {
  return {
    grantId,
    state: 'active',
    expiresAt: '2099-01-01T00:00:00.000Z',
    scope: FULL_SCOPE,
    orgId: 'org-test',
    placement: 0,
    ...overrides,
  };
}

/** A resolver that knows `grants`, each opened by SECRET_BYTES' tag only; it records every lookup. */
export function resolverFor(grants: GrantContext[]): ResolveGrant & { lookups: string[] } {
  const lookups: string[] = [];
  const resolve = async (grantId: string, authTag: string) => {
    lookups.push(grantId);
    const grant = grants.find((g) => g.grantId === grantId);
    if (!grant) return null;
    return authTag === (await deriveAuthTag(SECRET_BYTES)) ? grant : null;
  };
  return Object.assign(resolve, { lookups });
}

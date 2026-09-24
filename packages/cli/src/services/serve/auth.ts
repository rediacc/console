/**
 * Who is calling the executor.
 *
 * The executor never trusts a client-supplied identity. It takes the bearer
 * token the client presented and asks the account server whose it is
 * (POST /proxy/introspect), authenticating that question with its OWN token.
 * The account server answers only for tokens in the executor's organization,
 * and reports a foreign token exactly like a nonexistent one.
 *
 * The resolved principal is what policy is evaluated against and what the audit
 * event is attributed to, which is the whole point: attribution comes from the
 * server, not from anything the caller can assert.
 */

import type { SessionPrincipal } from './sessions.js';

/** How long a resolved identity is trusted before re-asking the account server. */
const CACHE_TTL_MS = 60_000;

/** The scope the executor's OWN token needs to record what it ran. */
export const AUDIT_WRITE_SCOPE = 'audit:write';

/** Whether the executor can record an audit event, and if not, why. */
export type AuditCapability = { ok: true } | { ok: false; reason: string };

export interface IntrospectionResponse {
  active: boolean;
  scopes?: string[];
  teamId?: string | null;
  orgId?: string;
  createdByUserId?: string;
  userEmail?: string;
  orgRole?: string;
  /** The presented token's own id, which the audit event is attributed to. */
  tokenId?: string;
}

export interface AuthVerifierOptions {
  /** Base URL of the account server, e.g. https://eu.rediacc.com */
  accountUrl: string;
  /** The executor's own token. Must carry the proxy:exec scope. */
  executorToken: string;
  /** Scope a client token must hold to submit commands. */
  requiredScope?: string;
  fetchImpl?: typeof fetch;
  now?: () => number;
}

interface CacheEntry {
  principal: SessionPrincipal;
  expiresAt: number;
}

export class AuthError extends Error {
  constructor(
    message: string,
    readonly status: 401 | 403
  ) {
    super(message);
    this.name = 'AuthError';
  }
}

export class AuthVerifier {
  private readonly cache = new Map<string, CacheEntry>();
  private auditCapability: { value: AuditCapability; expiresAt: number } | undefined;
  private readonly accountUrl: string;
  private readonly executorToken: string;
  private readonly requiredScope: string;
  private readonly fetchImpl: typeof fetch;
  private readonly now: () => number;

  constructor(options: AuthVerifierOptions) {
    this.accountUrl = options.accountUrl.replace(/\/+$/, '');
    this.executorToken = options.executorToken;
    this.requiredScope = options.requiredScope ?? 'proxy:exec';
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
    this.now = options.now ?? Date.now;
  }

  /**
   * Resolve the identity behind a client's bearer token.
   *
   * Cached briefly, because a warm container fields many commands per session
   * and re-introspecting each one would add a round trip to every command
   * without changing the answer. The cache is short enough that a revoked token
   * stops working within a minute.
   */
  async verify(bearerToken: string): Promise<SessionPrincipal> {
    const cached = this.cache.get(bearerToken);
    if (cached && cached.expiresAt > this.now()) {
      return cached.principal;
    }

    const response = await this.fetchImpl(`${this.accountUrl}/account/api/v1/proxy/introspect`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${this.executorToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ token: bearerToken }),
    });

    if (!response.ok) {
      throw new AuthError(
        `The executor could not verify this token with the account server (${response.status}).`,
        401
      );
    }

    const body = (await response.json()) as IntrospectionResponse;
    const principal = this.toPrincipal(body);

    this.cache.set(bearerToken, { principal, expiresAt: this.now() + CACHE_TTL_MS });
    return principal;
  }

  /**
   * Whether the executor's own token may write audit events.
   *
   * Found by introspecting the executor's token itself, so a token minted
   * without `audit:write` is caught BEFORE a command runs rather than by the
   * account server rejecting the event after it ran (the Phase 1 trial ran
   * `repo status` and could only log the 403 afterwards). Any failure to learn
   * the scopes counts as "cannot audit": the caller fails closed on it.
   * Cached like a principal, so a token fixed in the portal is picked up within
   * a minute.
   */
  async canWriteAudit(): Promise<AuditCapability> {
    const cached = this.auditCapability;
    if (cached && cached.expiresAt > this.now()) return cached.value;

    const value = await this.probeAuditCapability();
    this.auditCapability = { value, expiresAt: this.now() + CACHE_TTL_MS };
    return value;
  }

  private async probeAuditCapability(): Promise<AuditCapability> {
    let body: IntrospectionResponse;
    try {
      const response = await this.fetchImpl(`${this.accountUrl}/account/api/v1/proxy/introspect`, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${this.executorToken}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({ token: this.executorToken }),
      });
      if (!response.ok) {
        return {
          ok: false,
          reason: `the account server would not report the executor token's scopes (${response.status})`,
        };
      }
      body = (await response.json()) as IntrospectionResponse;
    } catch (error) {
      return {
        ok: false,
        reason: `the account server could not be asked for the executor token's scopes (${error instanceof Error ? error.message : String(error)})`,
      };
    }
    if (!body.active) return { ok: false, reason: 'the executor token is not active' };
    if (!body.scopes?.includes(AUDIT_WRITE_SCOPE)) {
      return { ok: false, reason: `the executor token lacks the "${AUDIT_WRITE_SCOPE}" scope` };
    }
    return { ok: true };
  }

  /** Forget a token, e.g. after the account server rejects it downstream. */
  invalidate(bearerToken: string): void {
    this.cache.delete(bearerToken);
  }

  private toPrincipal(body: IntrospectionResponse): SessionPrincipal {
    // A revoked, expired, unknown, or foreign-org token all look the same here, deliberately: the executor must not become an oracle for token discovery.
    if (!body.active) {
      throw new AuthError('This token is not valid for the executor.', 401);
    }
    if (!body.scopes?.includes(this.requiredScope)) {
      throw new AuthError(
        `This token lacks the "${this.requiredScope}" scope, so it cannot run commands through the executor.`,
        403
      );
    }
    if (!body.orgId || !body.createdByUserId || !body.userEmail) {
      throw new AuthError(
        'The account server returned an incomplete identity for this token.',
        401
      );
    }

    return {
      orgId: body.orgId,
      teamId: body.teamId ?? null,
      userId: body.createdByUserId,
      userEmail: body.userEmail,
      orgRole: normalizeRole(body.orgRole),
      // Carried into the audit event as onBehalfOfTokenId, so the account server attributes the command to THIS token's user rather than to the executor's own audit credential. Without it every proxied command is logged against the executor fleet, not the person who ran it.
      tokenId: body.tokenId,
    };
  }
}

/**
 * An unrecognized role is treated as the least privileged one.
 *
 * This matters: the policy default for a missing document allows owners and
 * admins and denies members, so a role we cannot parse must land on the DENY
 * side rather than accidentally granting owner rights.
 */
function normalizeRole(role: string | undefined): 'owner' | 'admin' | 'member' {
  return role === 'owner' || role === 'admin' ? role : 'member';
}

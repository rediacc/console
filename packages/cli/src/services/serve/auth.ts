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

import { ValidationError } from '../../utils/errors.js';
import { deadlineFetch, describeFetchError } from './account-fetch.js';
import type { SessionPrincipal } from './sessions.js';

/**
 * How long a resolved identity is trusted before re-asking the account server,
 * at most: an entry never outlives the token's own `expiresAt`.
 */
const CACHE_TTL_MS = 60_000;

/**
 * The most resolved identities held at once. Past it the least recently used
 * entry goes, so a flood of distinct bearers costs a bounded amount of memory.
 */
export const VERIFIER_CACHE_MAX_ENTRIES = 1_024;

/** The scope the executor's OWN token needs to record what it ran. */
const AUDIT_WRITE_SCOPE = 'audit:write';

/** Whether the executor can record an audit event, and if not, why. */
export type AuditCapability = { ok: true } | { ok: false; reason: string };

export interface IntrospectionResponse {
  active: boolean;
  scopes?: string[];
  teamId?: string | null;
  /** Slug of the token's team; policy `teams` rules are keyed by it. */
  teamSlug?: string;
  orgId?: string;
  createdByUserId?: string;
  userEmail?: string;
  orgRole?: string;
  /** The presented token's own id, which the audit event is attributed to. */
  tokenId?: string;
  /** ISO instant the presented token expires; absent for a token with no expiry. */
  expiresAt?: string;
}

export interface AuthVerifierOptions {
  /** Base URL of the account server, e.g. https://eu.rediacc.cloud */
  accountUrl: string;
  /** The executor's own token. Must carry the proxy:exec scope. */
  executorToken: string;
  /** Scope a client token must hold to submit commands. */
  requiredScope?: string;
  /** The org this executor serves. A principal of any other org is refused as an inactive token. */
  pinnedOrgId?: string;
  fetchImpl?: typeof fetch;
  now?: () => number;
}

interface CacheEntry {
  principal: SessionPrincipal;
  expiresAt: number;
}

/** The env name that pins a container executor to one org. */
const PINNED_ORG_ENV = 'REDIACC_EXECUTOR_ORG_ID';

/**
 * The org a container executor is pinned to by its environment. Container mode
 * refuses to boot without it; a daemon learns its org from its own token
 * instead (`resolveExecutorOrgId`).
 */
export function resolvePinnedOrgId(
  mode: 'daemon' | 'container',
  env: NodeJS.ProcessEnv
): string | undefined {
  if (mode !== 'container') return undefined;
  const orgId = env[PINNED_ORG_ENV]?.trim();
  if (!orgId) {
    throw new ValidationError(
      `The container executor must be pinned to one organization. Set ${PINNED_ORG_ENV} to its organization id.`
    );
  }
  return orgId;
}

/**
 * The org this executor serves, so that it can be pinned to it and open agent grant
 * sessions (agent/plans/PLAN-rmcp-agent-grants.md Design 8). A container reads its pin from
 * the environment. A daemon asks the account server whose its own token is (a `self`
 * introspection): the account answers only for tokens of that one org, so the token's org is
 * the org of the store the daemon enrolled in and the only org it can ever serve. A daemon
 * whose own token the account server will not report refuses to boot, naming why.
 */
export async function resolveExecutorOrgId(
  mode: 'daemon' | 'container',
  env: NodeJS.ProcessEnv,
  own: { accountUrl: string; executorToken: string; fetchImpl?: typeof fetch }
): Promise<string> {
  const pinned = resolvePinnedOrgId(mode, env);
  if (pinned !== undefined) return pinned;
  const fetchImpl = deadlineFetch(own.fetchImpl ?? globalThis.fetch);
  const refuse = (why: string) =>
    new ValidationError(`The daemon could not learn its organization: ${why}.`);
  let body: IntrospectionResponse;
  try {
    const response = await fetchImpl(
      `${own.accountUrl.replace(/\/+$/, '')}/account/api/v1/proxy/introspect`,
      {
        method: 'POST',
        headers: {
          authorization: `Bearer ${own.executorToken}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({ token: own.executorToken, self: true }),
      }
    );
    if (!response.ok) {
      throw refuse(`the account server answered ${response.status} for its own token`);
    }
    body = (await response.json()) as IntrospectionResponse;
  } catch (error) {
    if (error instanceof ValidationError) throw error;
    throw refuse(`the account server could not be asked (${describeFetchError(error)})`);
  }
  if (!body.active) throw refuse('its own token is not active');
  if (!body.orgId) throw refuse('the account server named no organization for its own token');
  return body.orgId;
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
  private readonly pinnedOrgId: string | undefined;
  private readonly fetchImpl: typeof fetch;
  private readonly now: () => number;

  constructor(options: AuthVerifierOptions) {
    this.accountUrl = options.accountUrl.replace(/\/+$/, '');
    this.executorToken = options.executorToken;
    this.requiredScope = options.requiredScope ?? 'proxy:exec';
    this.pinnedOrgId = options.pinnedOrgId;
    this.fetchImpl = deadlineFetch(options.fetchImpl ?? globalThis.fetch);
    this.now = options.now ?? Date.now;
  }

  /**
   * Resolve the identity behind a client's bearer token.
   *
   * Cached briefly, because a warm container fields many commands per session
   * and re-introspecting each one would add a round trip to every command
   * without changing the answer. An entry lives `CACHE_TTL_MS` or until the
   * token's own expiry, whichever comes first, so a revoked token stops working
   * within a minute and an expired one at its expiry. The cache is an LRU of at
   * most `VERIFIER_CACHE_MAX_ENTRIES`; an expired entry is dropped when read.
   */
  async verify(bearerToken: string): Promise<SessionPrincipal> {
    const cached = this.cache.get(bearerToken);
    if (cached) {
      this.cache.delete(bearerToken);
      if (cached.expiresAt > this.now()) {
        // Re-insert to mark it most recently used (Map keeps insertion order).
        this.cache.set(bearerToken, cached);
        return cached.principal;
      }
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

    const now = this.now();
    let entryExpiresAt = now + CACHE_TTL_MS;
    if (body.expiresAt !== undefined) {
      const tokenExpiresAt = Date.parse(body.expiresAt);
      if (Number.isNaN(tokenExpiresAt)) {
        throw new AuthError(
          'The account server returned an unreadable expiry for this token.',
          401
        );
      }
      entryExpiresAt = Math.min(entryExpiresAt, tokenExpiresAt);
    }
    // A token the account server calls active but whose expiry has already
    // passed on this clock is refused like an inactive one, never answered.
    if (entryExpiresAt <= now) {
      throw new AuthError('This token is not valid for the executor.', 401);
    }
    this.remember(bearerToken, { principal, expiresAt: entryExpiresAt });
    return principal;
  }

  /** Number of resolved identities currently held; exposed for the bound's test. */
  get cacheSize(): number {
    return this.cache.size;
  }

  private remember(bearerToken: string, entry: CacheEntry): void {
    this.cache.set(bearerToken, entry);
    while (this.cache.size > VERIFIER_CACHE_MAX_ENTRIES) {
      const oldest = this.cache.keys().next();
      if (oldest.done) break;
      this.cache.delete(oldest.value);
    }
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
        body: JSON.stringify({ token: this.executorToken, self: true }),
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
        reason: `the account server could not be asked for the executor token's scopes (${describeFetchError(error)})`,
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
    // Defence in depth: the account server already answers inactive for a foreign org, and a pinned executor says the same thing if it ever does not.
    if (this.pinnedOrgId !== undefined && body.orgId !== this.pinnedOrgId) {
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
      ...(body.teamId && body.teamSlug ? { teamSlug: body.teamSlug } : {}),
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

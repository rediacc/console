/**
 * The grant resolver of the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 4).
 *
 * One RPC to the account Worker's `resolveGrant` answers a grant for `(grantId, authTag)`. An answer that says the grant is active is cached per `(grantId, sha256(authTag))` for `min(30 s, expiresAt - now)`, so a burst of calls costs one lookup and the cache never outlives the grant. An answer that says the grant ended is never cached: the call after a revocation reaches the account and is refused. A pushed revocation calls `purge(grantId)` (through `/internal/revoke`, src/revoke.ts), which drops every entry of that grant and also discards a lookup still in flight, so a slow answer that began before the purge cannot repopulate the cache.
 *
 * The cache lives in one isolate's memory: a purge reaches the isolate that received it, and any other isolate serves its entry until the TTL (30 s at most) ends.
 */
import type { GrantContext, GrantScope, GrantState } from './scope.js';
import type { ResolveGrant } from './transport.js';

/** The longest an active answer is cached. */
export const GRANT_CACHE_TTL_MS = 30_000;

/** Entries kept per isolate; the oldest goes first. */
const CACHE_LIMIT = 1_000;

/**
 * What the account Worker's `resolveGrant` answers: `ResolvedGrant` in
 * private/account/src/services/executor-issuer.service.ts. The Workers build apart, so this mirrors the fields the Worker reads and the account test pins the shape it sends.
 */
export interface ResolvedGrantWire {
  grantId: string;
  state: GrantState;
  /** Why a grant that exists does not serve; detail that stays out of every answer. */
  reason?: string;
  orgId: string;
  placement: number;
  tier: 'standard' | 'high';
  userId: string;
  teamId: string | null;
  configId: string;
  region: string;
  scope: { readOnly: boolean; tools?: string[]; machines?: string[]; repos?: string[] };
  expiresAt: string;
  endedAt?: string;
}

/** The `GRANTS` service binding: the account Worker's `ExecutorIssuer` entrypoint. A null answer is an unknown grant, another region's grant or a wrong tag, which the account does not tell apart. */
export interface GrantsBinding {
  resolveGrant(grantId: string, authTag: string): Promise<ResolvedGrantWire | null>;
}

export interface GrantResolver extends ResolveGrant {
  /** The same lookup with the cache skipped and not written: for a caller that needs the account's current answer. */
  fresh: ResolveGrant;
  /** Drop every cached answer of `grantId` and void lookups already in flight; returns how many entries went. */
  purge: (grantId: string) => number;
}

function scopeOf(scope: ResolvedGrantWire['scope']): GrantScope {
  return {
    readOnly: scope.readOnly,
    tools: scope.tools ?? null,
    machines: scope.machines ?? null,
    repos: scope.repos ?? null,
  };
}

/** The transport's view of an account answer. */
export function grantContextOf(wire: ResolvedGrantWire): GrantContext {
  return {
    grantId: wire.grantId,
    state: wire.state,
    expiresAt: wire.expiresAt,
    ...(wire.endedAt === undefined ? {} : { endedAt: wire.endedAt }),
    scope: scopeOf(wire.scope),
    orgId: wire.orgId,
    placement: wire.placement,
    tier: wire.tier,
    userId: wire.userId,
    configId: wire.configId,
  };
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

interface Entry {
  grant: GrantContext;
  until: number;
}

/** Active answers by `(grantId, tag)`, with the purge generations that keep a stale lookup out. */
class GrantCache {
  private readonly entries = new Map<string, Entry>();
  private readonly generations = new Map<string, number>();

  constructor(private readonly now: () => number) {}

  get(key: string): GrantContext | undefined {
    const hit = this.entries.get(key);
    if (hit && hit.until > this.now()) return hit.grant;
    this.entries.delete(key);
    return undefined;
  }

  generationOf(grantId: string): number {
    return this.generations.get(grantId) ?? 0;
  }

  /** Keep an active answer for min(30 s, expiresAt - now), unless the grant was purged since the lookup began at `generation`. */
  put(key: string, grant: GrantContext, generation: number): void {
    const ttl = Math.min(GRANT_CACHE_TTL_MS, Date.parse(grant.expiresAt) - this.now());
    if (ttl <= 0 || this.generationOf(grant.grantId) !== generation) return;
    if (this.entries.size >= CACHE_LIMIT) {
      const oldest = this.entries.keys().next().value;
      if (oldest !== undefined) this.entries.delete(oldest);
    }
    this.entries.set(key, { grant, until: this.now() + ttl });
  }

  purge(grantId: string): number {
    this.generations.set(grantId, this.generationOf(grantId) + 1);
    let dropped = 0;
    for (const key of [...this.entries.keys()]) {
      if (key.startsWith(`${grantId}:`)) {
        this.entries.delete(key);
        dropped += 1;
      }
    }
    return dropped;
  }
}

export function createGrantResolver(
  binding: GrantsBinding,
  now: () => number = Date.now
): GrantResolver {
  const cache = new GrantCache(now);

  const lookup = async (grantId: string, authTag: string): Promise<GrantContext | null> => {
    const wire = await binding.resolveGrant(grantId, authTag);
    // Defense in depth: an answer for another grant must never stand for this one.
    return wire && wire.grantId === grantId ? grantContextOf(wire) : null;
  };

  const resolve: ResolveGrant = async (grantId, authTag) => {
    const key = `${grantId}:${await sha256Hex(authTag)}`;
    const hit = cache.get(key);
    if (hit) return hit;
    const generation = cache.generationOf(grantId);
    const grant = await lookup(grantId, authTag);
    if (grant?.state === 'active') cache.put(key, grant, generation);
    return grant;
  };

  return Object.assign(resolve, {
    fresh: lookup,
    purge: (grantId: string) => cache.purge(grantId),
  });
}

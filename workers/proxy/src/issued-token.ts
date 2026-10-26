/**
 * The executor's account token, issued by the account Worker over the ISSUER service binding.
 *
 * The account Worker's `ExecutorIssuer` entrypoint mints a short-lived token (scopes `proxy:exec` and `audit:write`, ip binding `service-binding`) for one org on each `issue(orgId)` call (agent/plans/PLAN-proxy-cd-six-targets.md, Design items 3 and 5; agent/plans/PLAN-console-executor-multi-org.md, Design item 2). No long-lived token is configured anywhere: the Worker asks for an org's token when it first needs it, keeps it in module scope per org (at most MAX_CACHED_ORGS, least recently used forgotten first), and asks again at 80% of its life.
 *
 * A failed renewal is remembered per org for FAILURE_BACKOFF_MS, so a failing issuer is asked at most once per window however many requests arrive.
 *
 * One isolate renews once per org: concurrent requests for an org that find the token due share a single in-flight `issue()` call. A renewal that fails while the cached token has not yet expired keeps serving the cached token, and the first request after the FAILURE_BACKOFF_MS window tries again.
 *
 * The token value is never logged and never handed to the container (src/egress.ts swaps it in on the way out).
 */

/** What `ExecutorIssuer.issue()` answers: the token and its expiry as an ISO 8601 instant. */
export interface IssuedToken {
  token: string;
  expiresAt: string;
}

/** The RPC surface of the account Worker's `ExecutorIssuer` entrypoint. */
export interface ExecutorIssuerRpc extends Rpc.WorkerEntrypointBranded {
  issue(orgId: string): Promise<IssuedToken>;
  route(bearer: string): Promise<{ orgId: string } | { refused: string }>;
  /** Writes nothing: whether the issuer env parses and D1 answers, and what a token it issues would carry. */
  probe(): Promise<{ ok: true; scopes: string[]; ttlMs: number }>;
}

/** The share of a token's life after which it is renewed. */
export const RENEW_AT_FRACTION = 0.8;

/** How long a failed issue() is remembered: every refusal is audited by the issuer, so a failing issuer must not be asked once per request. */
export const FAILURE_BACKOFF_MS = 5000;

/** The shape of an account issuer refusal that is safe to surface: a bare reason code. */
const ISSUER_CODE = /^ISSUER_[A-Z_]+$/;

/** Why no token could be had, as a reason code (never a token). */
export class IssuerError extends Error {
  constructor(
    readonly reason:
      | 'no-issuer'
      | 'issuer-refused'
      | 'issuer-malformed'
      | `issuer-refused:${string}`
  ) {
    super(reason);
    this.name = 'IssuerError';
  }
}

interface Cached {
  token: string;
  expiresAt: number;
  renewAt: number;
}

/** Everything remembered for one org. Keyed by org: a token minted for one org is never returned for another. */
interface OrgState {
  cached?: Cached;
  inflight?: Promise<Cached>;
  failure?: { error: IssuerError; until: number };
}

/** The most orgs one isolate remembers; the least recently used is forgotten past this. */
export const MAX_CACHED_ORGS = 64;

// A Map iterates in insertion order, so re-inserting on use keeps the least recently used org first.
const states = new Map<string, OrgState>();

/** The org's state, created if absent, and marked most recently used. Creating the 65th evicts the least recently used. */
function touch(orgId: string): OrgState {
  let state = states.get(orgId);
  if (state) {
    states.delete(orgId);
  } else {
    state = {};
    if (states.size >= MAX_CACHED_ORGS) {
      const oldest = states.keys().next();
      if (!oldest.done) states.delete(oldest.value);
    }
  }
  states.set(orgId, state);
  return state;
}

/** Forget every org's token, in-flight renewal and backoff. Tests only: an isolate never needs it. */
export function resetIssuedTokenCache(): void {
  states.clear();
}

/** Forget one org's cached token and backoff, after the account server answered 401 for it: the next request mints afresh. An in-flight renewal is left to finish. */
export function dropIssuedToken(orgId: string): void {
  const state = states.get(orgId);
  if (!state) return;
  delete state.cached;
  delete state.failure;
  if (!state.inflight) states.delete(orgId);
}

/** How many orgs are remembered. Tests only. */
export function issuedTokenOrgCount(): number {
  return states.size;
}

/** Epoch milliseconds of an ISO 8601 expiry, or NaN for anything else. */
function parseExpiry(value: unknown): number {
  return typeof value === 'string' ? Date.parse(value) : Number.NaN;
}

async function mint(
  issuer: Service<ExecutorIssuerRpc>,
  orgId: string,
  now: () => number
): Promise<Cached> {
  const issuedAt = now();
  let answer: IssuedToken;
  try {
    answer = await issuer.issue(orgId);
  } catch (error) {
    // The issuer's message is its reason code (ISSUER_ORG_NOT_FOUND, ISSUER_REGION_UNSET, ISSUER_ORG_BLOCKED, ISSUER_SUBSCRIPTION_INACTIVE, ISSUER_ORG_NOT_ENTITLED, ISSUER_STORE_UNSUPPORTED) and is carried through;
    // any other message may name the org or the owner, so only the bare reason leaves this function.
    const message = error instanceof Error ? error.message : '';
    throw new IssuerError(
      ISSUER_CODE.test(message) ? `issuer-refused:${message}` : 'issuer-refused'
    );
  }
  const token: unknown = answer?.token;
  const expiresAt = parseExpiry(answer?.expiresAt);
  if (typeof token !== 'string' || token === '' || !(expiresAt > issuedAt)) {
    throw new IssuerError('issuer-malformed');
  }
  return {
    token,
    expiresAt,
    renewAt: issuedAt + RENEW_AT_FRACTION * (expiresAt - issuedAt),
  };
}

/**
 * The org's current issued token: the cached one before 80% of its life, otherwise a fresh one.
 *
 * Throws IssuerError when there is no binding, or when the issuer refuses or answers malformed and no unexpired token is cached for that org. One org's refusal never blocks another org.
 */
export async function issuedToken(
  issuer: Service<ExecutorIssuerRpc> | undefined,
  orgId: string,
  now: () => number = Date.now
): Promise<string> {
  if (!issuer) throw new IssuerError('no-issuer');
  const state = touch(orgId);
  const { cached } = state;
  if (cached && now() < cached.renewAt) return cached.token;
  const { failure } = state;
  if (failure && now() < failure.until) return staleOrThrow(cached, failure.error, now());
  let { inflight } = state;
  if (!inflight) {
    const started: Promise<Cached> = mint(issuer, orgId, now)
      .then((fresh) => {
        state.cached = fresh;
        delete state.failure;
        return fresh;
      })
      .finally(() => {
        if (state.inflight === started) delete state.inflight;
      });
    state.inflight = started;
    inflight = started;
  }
  try {
    return (await inflight).token;
  } catch (error) {
    if (error instanceof IssuerError) {
      state.failure = { error, until: now() + FAILURE_BACKOFF_MS };
    }
    return staleOrThrow(state.cached, error, now());
  }
}

/** After a failed renewal: the cached token while it has not expired, otherwise the failure as an IssuerError. */
function staleOrThrow(cached: Cached | undefined, error: unknown, at: number): string {
  const reason = error instanceof IssuerError ? error.reason : 'issuer-refused';
  if (cached && at < cached.expiresAt) {
    console.warn(`proxy: executor token renewal failed (${reason}); serving the unexpired token`);
    return cached.token;
  }
  throw new IssuerError(reason);
}

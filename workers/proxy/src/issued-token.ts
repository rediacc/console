/**
 * The executor's account token, issued by the account Worker over the ISSUER service binding.
 *
 * The account Worker's `ExecutorIssuer` entrypoint mints a short-lived token (scopes `proxy:exec` and `audit:write`, ip binding `service-binding`) on each `issue()` call (agent/plans/PLAN-proxy-cd-six-targets.md, Design items 3 and 5). No long-lived token is configured anywhere: the Worker asks for one when it first needs it, keeps it in module scope, and asks again at 80% of its life.
 *
 * A failed renewal is remembered for FAILURE_BACKOFF_MS, so a failing issuer is asked at most once per window however many requests arrive.
 *
 * One isolate renews once: concurrent requests that find the token due share a single in-flight `issue()` call. A renewal that fails while the cached token has not yet expired keeps serving the cached token, and the next request tries again.
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
  issue(): Promise<IssuedToken>;
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

let cached: Cached | undefined;
let inflight: Promise<Cached> | undefined;
let failure: { error: IssuerError; until: number } | undefined;

/** Forget the cached token and any in-flight renewal. Tests only: an isolate never needs it. */
export function resetIssuedTokenCache(): void {
  cached = undefined;
  inflight = undefined;
  failure = undefined;
}

/** Epoch milliseconds of an ISO 8601 expiry, or NaN for anything else. */
function parseExpiry(value: unknown): number {
  return typeof value === 'string' ? Date.parse(value) : Number.NaN;
}

async function mint(issuer: Service<ExecutorIssuerRpc>, now: () => number): Promise<Cached> {
  const issuedAt = now();
  let answer: IssuedToken;
  try {
    answer = await issuer.issue();
  } catch (error) {
    // The issuer's message is its reason code (ISSUER_OWNER_UNKNOWN, ISSUER_ROLE_REVOKED, ...) and is carried through;
    // any other message may name the org or the owner, so only the bare reason leaves this function.
    const message = error instanceof Error ? error.message : '';
    throw new IssuerError(ISSUER_CODE.test(message) ? `issuer-refused:${message}` : 'issuer-refused');
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
 * The current issued token: the cached one before 80% of its life, otherwise a fresh one.
 *
 * Throws IssuerError when there is no binding, or when the issuer refuses or answers malformed and no unexpired token is cached.
 */
export async function issuedToken(
  issuer: Service<ExecutorIssuerRpc> | undefined,
  now: () => number = Date.now
): Promise<string> {
  if (!issuer) throw new IssuerError('no-issuer');
  if (cached && now() < cached.renewAt) return cached.token;
  if (failure && now() < failure.until) return staleOrThrow(failure.error, now());
  inflight ??= mint(issuer, now)
    .then((fresh) => {
      cached = fresh;
      failure = undefined;
      return fresh;
    })
    .finally(() => {
      inflight = undefined;
    });
  try {
    return (await inflight).token;
  } catch (error) {
    if (error instanceof IssuerError) failure = { error, until: now() + FAILURE_BACKOFF_MS };
    return staleOrThrow(error, now());
  }
}

/** After a failed renewal: the cached token while it has not expired, otherwise the failure as an IssuerError. */
function staleOrThrow(error: unknown, at: number): string {
  const reason = error instanceof IssuerError ? error.reason : 'issuer-refused';
  if (cached && at < cached.expiresAt) {
    console.warn(`proxy: executor token renewal failed (${reason}); serving the unexpired token`);
    return cached.token;
  }
  throw new IssuerError(reason);
}

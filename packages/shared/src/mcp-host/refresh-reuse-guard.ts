/**
 * Refresh-token reuse detection layered in front of an OAuth token endpoint.
 *
 * `@cloudflare/workers-oauth-provider` 1.3.0 rotates refresh tokens but keeps the
 * previous one valid as a retry grace, and never revokes a grant on reuse: a
 * replayed, already-rotated token is either accepted (and displaces the legitimate
 * successor) or refused with the grant left alive. The plan requires the OAuth 2.1
 * section 4.3.1 behaviour for public clients instead: a refresh token presented a
 * second time revokes the whole grant, every access and refresh token in it.
 *
 * The guard records each refresh token the endpoint accepted (as a SHA-256 marker,
 * never the token) and, when one comes back, revokes its grant through the
 * callback before the library sees the request. It holds no library internals, so
 * it wraps the library unmodified on both hosts.
 *
 * Limit: the check and the record are two KV operations, so two concurrent uses of
 * the same token can both pass before either is recorded; on Cloudflare KV, which
 * is eventually consistent across locations, that window is wider. The marker is a
 * best-effort detector, not a lock.
 */

/** The KV calls the guard makes; Workers KV and SqliteKvNamespace both satisfy it. */
export interface RefreshReuseGuardKv {
  get(key: string): Promise<string | null>;
  put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void>;
}

export type FetchLike<Env, Ctx> = (request: Request, env: Env, ctx: Ctx) => Promise<Response>;

export interface RefreshReuseGuardOptions<Env> {
  /** Path of the token endpoint, e.g. `/oauth/token`. */
  tokenPath: string;
  /** The store for used-token markers, usually the provider's own `OAUTH_KV`. */
  kv: (env: Env) => RefreshReuseGuardKv;
  /** Revokes the grant and every token issued under it. */
  revokeGrant: (env: Env, grantId: string, userId: string) => Promise<void>;
  /** How long a marker lives; at least the refresh token's own lifetime. */
  markerTtlSeconds: number;
}

/** KV key prefix of the used-token markers. */
export const REFRESH_USED_PREFIX = 'refresh-used:';

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

function invalidGrant(description: string): Response {
  return new Response(JSON.stringify({ error: 'invalid_grant', error_description: description }), {
    status: 400,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
    },
  });
}

interface PresentedRefreshToken {
  token: string;
  userId: string;
  grantId: string;
}

/** The refresh token a token-endpoint request presents, or null for any other request. */
async function presentedRefreshToken(
  request: Request,
  tokenPath: string
): Promise<PresentedRefreshToken | null> {
  const isForm = (request.headers.get('Content-Type') ?? '').startsWith(
    'application/x-www-form-urlencoded'
  );
  if (request.method !== 'POST' || new URL(request.url).pathname !== tokenPath || !isForm) {
    return null;
  }
  const body = new URLSearchParams(await request.clone().text());
  const token = body.get('refresh_token');
  if (body.get('grant_type') !== 'refresh_token' || !token) return null;
  const parts = token.split(':');
  if (parts.length !== 3) return null;
  const [userId, grantId] = parts as [string, string, string];
  return { token, userId, grantId };
}

export function withRefreshReuseGuard<Env, Ctx>(
  inner: FetchLike<Env, Ctx>,
  options: RefreshReuseGuardOptions<Env>
): FetchLike<Env, Ctx> {
  return async (request, env, ctx) => {
    const presented = await presentedRefreshToken(request, options.tokenPath);
    if (!presented) return inner(request, env, ctx);
    const { token: refreshToken, userId, grantId } = presented;
    const kv = options.kv(env);
    const marker = `${REFRESH_USED_PREFIX}${userId}:${grantId}:${await sha256Hex(refreshToken)}`;
    if ((await kv.get(marker)) !== null) {
      await options.revokeGrant(env, grantId, userId);
      return invalidGrant('Refresh token reuse detected; the grant has been revoked');
    }
    const response = await inner(request, env, ctx);
    if (response.ok) {
      await kv.put(marker, '1', { expirationTtl: options.markerTtlSeconds });
    }
    return response;
  };
}

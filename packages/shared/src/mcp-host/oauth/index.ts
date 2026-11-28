/**
 * The OAuth authorization server of the hosted MCP Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 2, box RW-A1).
 *
 * `@cloudflare/workers-oauth-provider` serves what the protocol fixes: the RFC 8414 metadata (S256 only, `iss` in responses, Client ID Metadata Documents), `/oauth/token` (code exchange, rotating refresh tokens, revocation) and `/register` (dynamic client registration, the fallback for a client without a metadata document). The library runs unmodified on Workers and Node (RW-OP0), and `withRefreshReuseGuard` (packages/shared/src/mcp-host) adds what the library lacks: a refresh token presented a second time revokes the whole grant. Around it this module adds:
 *
 * - `/authorize`: parses the request through the library (client, exact `redirect_uri` with loopback on any port, PKCE), keeps it in KV behind a signed single-use handle (./handle.ts) and redirects to the account page `/account/mcp/authorize?authRequest=<handle>`. Nothing secret is in that URL.
 * - `GET /authorize/request`: answers the page `{clientName, clientDomain, clientId}` for a handle, with CORS for the portal origin only.
 * - `POST /authorize/complete`: the page's form post `{authRequest, grantId, S}`. The grant is resolved with the tag derived from `S`, which proves the poster holds the secret and that the grant serves; then the library's `completeAuthorization` runs with props `{grantId, S, userId, orgId}` (the library encrypts props at rest) and the browser is redirected to the client with the code.
 * - the per-grant RFC 9728 document `/.well-known/oauth-protected-resource/g/<grantId>`.
 * - the SSRF guard (./ssrf.ts) in front of every request that names a client by URL.
 *
 * Audience. The library keeps one protected resource per authorization server, fixed at construction, so every token's audience is this Worker's origin. A client that sends `resource=https://<host>/g/<grantId>` (the URL it connects to) is mapped to that audience here, and the grant id it named is remembered with the request: `/authorize/complete` refuses a grant other than the one named. A token is bound to its grant through its props, and `verifyAccessToken` refuses a token for any grant id but the one in the URL it is presented at.
 *
 * Lifetime (D54). `tokenExchangeCallback` looks the grant up uncached at every code exchange and every refresh: a grant that no longer serves (expired, revoked, key rotated) is answered `invalid_grant`, which also revokes the OAuth grant, and an access token never outlives the grant (`accessTokenTTL` is `min(1 h, time left)`). The refresh token of a new OAuth grant lives `min(30 days, time left)` and the library's fixed lifetime then holds across refreshes, so no refresh token outlasts the Rediacc grant. The library takes no refresh-token lifetime under 60 s, so one with less than a minute left lives that minute and meets the callback's refusal.
 *
 * Region (D58). With `region` set, a grant id that is not prefixed `<region>_` is never accepted as a `resource`, as the grant of `/authorize/complete`, in metadata or in a token's URL, so no OAuth state binds across regions.
 *
 * Not here: the per-config scope (src/call.ts, RW-SCOPE) and the on-premise store adapters (RW-KV, RW-OP*).
 */

import {
  AuthorizationError,
  type AuthRequest,
  CimdFetchError,
  OAuthAuthorizationServer,
  OAuthError,
  type TokenExchangeCallbackOptions,
  type TokenExchangeCallbackResult,
} from '@cloudflare/workers-oauth-provider';
import { deriveAuthTag } from '../../config-crypto/agent-grant.js';
import type { AccessTokenCheck, VerifyAccessToken } from '../credential.js';
import { openBearer } from '../credential.js';
import type { HostExecutionContext, HostKvNamespace } from '../host-types.js';
import { withRefreshReuseGuard } from '../refresh-reuse-guard.js';
import type { GrantContext } from '../scope.js';
import type { ResolveGrant } from '../transport.js';
import { createAuthRequestStore, type HandleKv, type StoredAuthRequest } from './handle.js';
import { grantServedHere } from './region.js';
import {
  type ClientUrlGuard,
  ClientUrlRefused,
  createClientUrlGuard,
  dohResolver,
  type HostResolver,
} from './ssrf.js';

/** The bindings the OAuth layer reads. */
export interface OAuthEnv {
  /** The provider's store, one namespace per region (Design 12). */
  OAUTH_KV: HostKvNamespace;
}

export interface OAuthOptions {
  /** The Worker's public host, e.g. mcp.eu.rediacc.cloud. */
  host: string;
  /** The Worker's region; grants of any other region are refused. Unset on-premise, which is one region. */
  region?: string;
  /** The region's account origin: where the authorize page lives, and the one browser origin allowed to read `/authorize/request`. */
  accountUrl: string;
  /** Worker secret signing the `authRequest` handles. */
  authRequestKey: string;
  /** Resolve a grant uncached: `/authorize/complete` must see a revoked grant at once. */
  resolveGrant: ResolveGrant;
  /** Resolves a client URL's host for the SSRF guard; the default asks DNS-over-HTTPS. */
  resolveHost?: HostResolver;
  /** Tests pin the clock of the guard's cache. */
  now?: () => number;
}

export interface OAuth {
  /** Answer a request the OAuth layer owns, or null for any other route. */
  fetch(request: Request, env: OAuthEnv, ctx: HostExecutionContext): Promise<Response | null>;
  /** The access-token check the transport takes (src/credential.ts). */
  verifyAccessToken(env: OAuthEnv): VerifyAccessToken;
}

export const AUTHORIZE_PATH = '/authorize';
export const AUTHORIZE_REQUEST_PATH = '/authorize/request';
export const AUTHORIZE_COMPLETE_PATH = '/authorize/complete';
export const TOKEN_PATH = '/oauth/token';
export const REGISTER_PATH = '/register';
const AUTH_SERVER_METADATA_PREFIX = '/.well-known/oauth-authorization-server';
const RESOURCE_METADATA_PREFIX = '/.well-known/oauth-protected-resource/g/';

/** The one scope this server grants: the grant's own scope filters tools (src/scope.ts), so OAuth carries no finer one. */
export const MCP_SCOPE = 'mcp';
export const ACCESS_TOKEN_TTL_SECONDS = 3600;
/** The longest a grant lives (Design 4); each token is capped at its grant's own expiry. */
export const REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 3600;
/** The library takes no refresh-token lifetime under this. */
const MIN_REFRESH_TTL_SECONDS = 60;

const GRANT_ID = /^[A-Za-z0-9_-]{1,64}$/;
const RESOURCE_PATH = /^\/g\/([A-Za-z0-9_-]{1,64})$/;
const SECRET_TEXT = /^[A-Za-z0-9_-]{43}$/;

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers },
  });
}

function oauthError(status: number, error: string, description: string): Response {
  return json(status, { error, error_description: description });
}

function isFormPost(request: Request): boolean {
  return (
    request.method === 'POST' &&
    (request.headers.get('content-type') ?? '').startsWith('application/x-www-form-urlencoded')
  );
}

/** The grant id a `resource` value names (`https://<host>/g/<id>`), or null when it names anything else. */
function grantOfResource(
  host: string,
  region: string | undefined,
  value: string | null
): string | null {
  if (value === null) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.host !== host || url.search !== '' || url.hash !== '') {
      return null;
    }
    const grantId = RESOURCE_PATH.exec(url.pathname)?.[1] ?? null;
    return grantId !== null && grantServedHere(grantId, region) ? grantId : null;
  } catch {
    return null;
  }
}

/** The client id a request presents, when it presents one as a URL. */
async function clientUrlOf(request: Request, path: string): Promise<string | null> {
  const url = new URL(request.url);
  let clientId: string | null = null;
  if (path === AUTHORIZE_PATH && request.method === 'GET') {
    clientId = url.searchParams.get('client_id');
  } else if (path === TOKEN_PATH && isFormPost(request)) {
    clientId = new URLSearchParams(await request.clone().text()).get('client_id');
  }
  return clientId !== null && /^https?:\/\//i.test(clientId) ? clientId : null;
}

/** The request with `resource=https://<host>/g/<id>` replaced by the audience this server holds, and the grant id it named. */
async function withCanonicalResource(
  request: Request,
  host: string,
  region: string | undefined,
  audience: string
): Promise<{ request: Request; grantId: string | null }> {
  const url = new URL(request.url);
  const path = url.pathname;
  if (path === AUTHORIZE_PATH && request.method === 'GET') {
    const grantId = grantOfResource(host, region, url.searchParams.get('resource'));
    if (grantId === null) return { request, grantId: null };
    url.searchParams.set('resource', audience);
    return { request: new Request(url, request), grantId };
  }
  if (path === TOKEN_PATH && isFormPost(request)) {
    const body = new URLSearchParams(await request.clone().text());
    const grantId = grantOfResource(host, region, body.get('resource'));
    if (grantId === null) return { request, grantId: null };
    body.set('resource', audience);
    const headers = new Headers(request.headers);
    headers.delete('content-length');
    return {
      request: new Request(request.url, { method: 'POST', headers, body: body.toString() }),
      grantId,
    };
  }
  return { request, grantId: null };
}

function methodNotAllowed(): Response {
  return json(405, { error: 'method_not_allowed' });
}

/** The exact paths that reach the library's side, `/authorize` among them: this module answers that one with the library's request parser. */
const LIBRARY_PATHS: ReadonlySet<string> = new Set([AUTHORIZE_PATH, TOKEN_PATH, REGISTER_PATH]);

function describeError(error: unknown): Response {
  if (error instanceof CimdFetchError) {
    return oauthError(400, 'invalid_client', 'The client metadata document could not be resolved.');
  }
  if (error instanceof AuthorizationError) {
    return oauthError(400, error.code, error.description);
  }
  return oauthError(400, 'invalid_request', 'The authorization request is not valid.');
}

export function createOAuth(options: OAuthOptions): OAuth {
  const { host } = options;
  const clock = options.now ?? Date.now;
  const audience = `https://${host}`;
  const portalOrigin = new URL(options.accountUrl).origin;
  const guard: ClientUrlGuard = createClientUrlGuard(
    options.resolveHost ?? dohResolver,
    options.now
  );

  /** The grant behind an OAuth grant's props, looked up uncached; null when it is unknown, 'failed' when the lookup itself failed. */
  async function liveGrant(props: unknown): Promise<GrantContext | null | 'failed'> {
    const { grantId, S } = (props ?? {}) as { grantId?: unknown; S?: unknown };
    const bearer =
      typeof grantId === 'string' && typeof S === 'string'
        ? openBearer(`rmcp_${grantId}.${S}`)
        : null;
    if (!bearer) return null;
    try {
      const grant = await options.resolveGrant(bearer.grantId, await deriveAuthTag(bearer.secret));
      return grant?.grantId === bearer.grantId ? grant : null;
    } catch {
      return 'failed';
    }
  }

  /** The seconds the grant has left, or the refusal when it does not serve (an unknown, ended or expired grant). */
  function secondsLeft(grant: GrantContext | null): number {
    const left = grant ? Math.floor((Date.parse(grant.expiresAt) - clock()) / 1000) : 0;
    if (grant?.state !== 'active' || !(left > 0)) {
      throw new OAuthError('invalid_grant', { description: 'The grant does not serve.' });
    }
    return left;
  }

  /** The token lifetimes of one code exchange or refresh (D54), or the refusal that ends the OAuth grant. */
  async function capToGrant(
    exchange: TokenExchangeCallbackOptions<OAuthEnv>
  ): Promise<TokenExchangeCallbackResult | undefined> {
    if (exchange.grantType !== 'authorization_code' && exchange.grantType !== 'refresh_token') {
      return undefined;
    }
    const grant = await liveGrant(exchange.props);
    if (grant === 'failed') {
      throw new OAuthError('temporarily_unavailable', {
        description: 'The grant could not be checked; try again.',
        statusCode: 503,
        headers: { 'Retry-After': '5' },
      });
    }
    const left = secondsLeft(grant);
    const refreshTokenTTL = Math.max(
      MIN_REFRESH_TTL_SECONDS,
      Math.min(REFRESH_TOKEN_TTL_SECONDS, left)
    );
    return {
      accessTokenTTL: Math.min(ACCESS_TOKEN_TTL_SECONDS, left),
      // The library applies this at the code exchange only; a refresh keeps the grant's fixed lifetime.
      refreshTokenTTL,
    };
  }

  const server = new OAuthAuthorizationServer<OAuthEnv>({
    issuer: audience,
    authorizeEndpoint: AUTHORIZE_PATH,
    tokenEndpoint: TOKEN_PATH,
    clientRegistrationEndpoint: REGISTER_PATH,
    resources: [audience],
    scopesSupported: [MCP_SCOPE],
    accessTokenTTL: ACCESS_TOKEN_TTL_SECONDS,
    refreshTokenTTL: REFRESH_TOKEN_TTL_SECONDS,
    clientIdMetadataDocumentEnabled: true,
    tokenExchangeCallback: (exchange) => capToGrant(exchange),
  });

  const library = withRefreshReuseGuard<OAuthEnv, HostExecutionContext>(
    (request, env, ctx) => server.fetch(request, env, ctx as Parameters<typeof server.fetch>[2]),
    {
      tokenPath: TOKEN_PATH,
      kv: (env) => env.OAUTH_KV,
      revokeGrant: (env, grantId, userId) => server.getOAuthApi(env).revokeGrant(grantId, userId),
      markerTtlSeconds: REFRESH_TOKEN_TTL_SECONDS,
    }
  );

  function stores(env: OAuthEnv) {
    return createAuthRequestStore(env.OAUTH_KV as unknown as HandleKv, options.authRequestKey);
  }

  /** `GET /authorize`: validate, keep the request, send the browser to the account page. */
  async function authorize(request: Request, env: OAuthEnv): Promise<Response> {
    const { request: canonical, grantId } = await withCanonicalResource(
      request,
      host,
      options.region,
      audience
    );
    let authRequest: AuthRequest;
    try {
      authRequest = await server.getOAuthApi(env).parseAuthRequest(canonical);
    } catch (error) {
      return describeError(error);
    }
    const handle = await stores(env).put({
      authRequest,
      ...(grantId === null ? {} : { resourceGrantId: grantId }),
    });
    const page = new URL('/account/mcp/authorize', options.accountUrl);
    page.searchParams.set('authRequest', handle);
    return new Response(null, {
      status: 302,
      headers: { location: page.toString(), 'cache-control': 'no-store' },
    });
  }

  function portalCors(request: Request): Record<string, string> {
    return request.headers.get('origin') === portalOrigin
      ? { 'access-control-allow-origin': portalOrigin, vary: 'Origin' }
      : { vary: 'Origin' };
  }

  /** `GET /authorize/request`: who is asking, for the account page. */
  async function describe(request: Request, env: OAuthEnv): Promise<Response> {
    const cors = portalCors(request);
    const handle = new URL(request.url).searchParams.get('authRequest') ?? '';
    const stored = await stores(env).peek(handle);
    if (!stored) return json(404, { error: 'invalid_request' }, cors);
    try {
      const consent = await server.getOAuthApi(env).describeConsent(stored.authRequest);
      return json(
        200,
        {
          clientName: consent.clientName,
          // A registered client has no verified domain: show where the tokens go instead.
          clientDomain: consent.clientDomain ?? consent.redirectHost,
          clientId: consent.clientId,
        },
        cors
      );
    } catch (error) {
      const failed = describeError(error);
      return json(failed.status, { error: 'invalid_request' }, cors);
    }
  }

  /** The refusal for a post that did not come from the account page as a form, or null. */
  function postRefusal(request: Request): Response | null {
    const origin = request.headers.get('origin');
    if (origin !== null && origin !== portalOrigin) {
      return oauthError(
        403,
        'access_denied',
        'The authorization was not posted by the account page.'
      );
    }
    return isFormPost(request)
      ? null
      : oauthError(400, 'invalid_request', 'A form post is required.');
  }

  /** The fields of the account page's form post, or the refusal. */
  async function completionForm(
    request: Request
  ): Promise<{ handle: string; grantId: string; secret: string } | Response> {
    const refusal = postRefusal(request);
    if (refusal) return refusal;
    const fields = new URLSearchParams(await request.text());
    const grantId = fields.get('grantId') ?? '';
    const secret = fields.get('S') ?? '';
    if (
      !GRANT_ID.test(grantId) ||
      !grantServedHere(grantId, options.region) ||
      !SECRET_TEXT.test(secret)
    ) {
      return oauthError(400, 'invalid_request', 'The grant is not valid.');
    }
    return { handle: fields.get('authRequest') ?? '', grantId, secret };
  }

  /** The grant `grantId` when `secret` opens it and it serves, or the refusal. */
  async function servingGrant(grantId: string, secret: string): Promise<GrantContext | Response> {
    const bearer = openBearer(`rmcp_${grantId}.${secret}`);
    if (!bearer) return oauthError(400, 'invalid_request', 'The grant is not valid.');
    const tag = await deriveAuthTag(bearer.secret);
    const looked = await options.resolveGrant(grantId, tag).then(
      (grant) => ({ grant }),
      () => null
    );
    if (looked === null) {
      return oauthError(
        503,
        'temporarily_unavailable',
        'The grant could not be checked; try again.'
      );
    }
    const { grant } = looked;
    return grant?.grantId === grantId && grant.state === 'active'
      ? grant
      : oauthError(400, 'access_denied', 'The grant does not serve.');
  }

  /** Complete the stored request for `grant` and send the browser back to the client with its code. */
  async function finish(
    env: OAuthEnv,
    stored: StoredAuthRequest,
    grant: GrantContext,
    secret: string
  ): Promise<Response> {
    try {
      const { redirectTo } = await server.getOAuthApi(env).completeAuthorization({
        request: stored.authRequest,
        userId: encodeURIComponent(grant.userId ?? grant.grantId),
        metadata: { grantId: grant.grantId },
        scope: [MCP_SCOPE],
        props: { grantId: grant.grantId, S: secret, userId: grant.userId, orgId: grant.orgId },
        // One OAuth grant per Rediacc grant: an earlier grant of the same user and client (another config) must stay valid.
        revokeExistingGrants: false,
      });
      return new Response(null, {
        status: 303,
        headers: { location: redirectTo, 'cache-control': 'no-store' },
      });
    } catch (error) {
      return describeError(error);
    }
  }

  const unknownRequest = () =>
    oauthError(400, 'invalid_request', 'The authorization request is unknown or used.');

  /** The refusal when the request is gone, or the post names a grant other than the one the client asked for. */
  function requestRefusal(stored: StoredAuthRequest | null, grantId: string): Response | null {
    if (!stored) return unknownRequest();
    if (stored.resourceGrantId !== undefined && stored.resourceGrantId !== grantId) {
      return oauthError(400, 'invalid_target', 'The grant is not the one the client asked for.');
    }
    return null;
  }

  /** `POST /authorize/complete`: the account page's form post finishes the request. */
  async function complete(request: Request, env: OAuthEnv): Promise<Response> {
    const posted = await completionForm(request);
    if (posted instanceof Response) return posted;
    const { handle, grantId, secret } = posted;
    const store = stores(env);
    const stored = await store.peek(handle);
    const refusal = requestRefusal(stored, grantId);
    if (refusal || !stored) return refusal ?? unknownRequest();
    const grant = await servingGrant(grantId, secret);
    if (grant instanceof Response) return grant;
    // The handle is used up only after the grant checked out, so a wrong secret does not burn it.
    return (await store.take(handle)) ? finish(env, stored, grant, secret) : unknownRequest();
  }

  /** The RFC 9728 document of one grant's resource URL. */
  function resourceMetadata(request: Request, path: string): Response {
    const grantId = path.slice(RESOURCE_METADATA_PREFIX.length);
    if (
      request.method !== 'GET' ||
      !GRANT_ID.test(grantId) ||
      !grantServedHere(grantId, options.region)
    ) {
      return json(404, { error: 'not_found' });
    }
    return json(
      200,
      {
        resource: `${audience}/g/${grantId}`,
        authorization_servers: [audience],
        bearer_methods_supported: ['header'],
        scopes_supported: [MCP_SCOPE],
      },
      { 'access-control-allow-origin': '*', 'cache-control': 'public, max-age=300' }
    );
  }

  /** The CORS preflight and the read of `/authorize/request`. */
  function authorizeRequest(request: Request, env: OAuthEnv): Promise<Response> | Response {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: { ...portalCors(request), 'access-control-allow-methods': 'GET' },
      });
    }
    return request.method === 'GET' ? describe(request, env) : methodNotAllowed();
  }

  /** The pre-check every request naming its client by URL passes before the library fetches the document. */
  async function refusedClientUrl(request: Request, path: string): Promise<Response | null> {
    const clientUrl = await clientUrlOf(request, path);
    if (clientUrl === null) return null;
    try {
      await guard.assertPublic(clientUrl);
      return null;
    } catch (error) {
      if (error instanceof ClientUrlRefused)
        return oauthError(400, 'invalid_client', error.message);
      throw error;
    }
  }

  /** The routes that reach the library, after the guard and the resource mapping; `/authorize` uses the library's parser, not its router. */
  async function viaLibrary(
    request: Request,
    path: string,
    env: OAuthEnv,
    ctx: HostExecutionContext
  ): Promise<Response> {
    const refused = await refusedClientUrl(request, path);
    if (refused) return refused;
    if (path === AUTHORIZE_PATH) {
      return request.method === 'GET' ? authorize(request, env) : methodNotAllowed();
    }
    const { request: canonical } = await withCanonicalResource(
      request,
      host,
      options.region,
      audience
    );
    return library(canonical, env, ctx);
  }

  type Route = readonly [
    matches: (path: string) => boolean,
    handle: (
      request: Request,
      env: OAuthEnv,
      ctx: HostExecutionContext
    ) => Response | Promise<Response>,
  ];
  const routes: readonly Route[] = [
    [
      (path) => path.startsWith(RESOURCE_METADATA_PREFIX),
      (request) => resourceMetadata(request, new URL(request.url).pathname),
    ],
    [(path) => path === AUTHORIZE_REQUEST_PATH, authorizeRequest],
    [
      (path) => path === AUTHORIZE_COMPLETE_PATH,
      (request, env) => (request.method === 'POST' ? complete(request, env) : methodNotAllowed()),
    ],
    [
      (path) => LIBRARY_PATHS.has(path) || path.startsWith(AUTH_SERVER_METADATA_PREFIX),
      (request, env, ctx) => viaLibrary(request, new URL(request.url).pathname, env, ctx),
    ],
  ];

  /** The access token check: valid only for the grant the URL names, which the token's props must name too. */
  async function checkAccessToken(
    env: OAuthEnv,
    token: string,
    resource: string
  ): Promise<AccessTokenCheck> {
    const grantId = grantOfResource(host, options.region, resource);
    if (grantId === null) return { status: 'invalid' };
    // The library answers null for an unknown, expired, revoked and wrong-audience token alike.
    const valid = await server.validateToken<{ grantId?: string; S?: string }>(
      audience,
      token,
      env
    );
    if (!valid || valid.props.grantId !== grantId || typeof valid.props.S !== 'string') {
      return { status: 'invalid' };
    }
    return { status: 'valid', grantId, secret: valid.props.S };
  }

  return {
    async fetch(request, env, ctx) {
      const path = new URL(request.url).pathname;
      const route = routes.find(([matches]) => matches(path));
      return route ? await route[1](request, env, ctx) : null;
    },

    verifyAccessToken: (env) => (token, resource) => checkAccessToken(env, token, resource),
  };
}

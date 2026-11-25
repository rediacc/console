/**
 * One Worker entry for the OAuth portability spike, run unchanged on both hosts:
 * bundled by esbuild into Miniflare (Cloudflare) and imported in-process on Node
 * behind the `cloudflare:workers` shim. `REUSE_GUARD` = '1' wraps the token
 * endpoint with the refresh-reuse guard; '0' leaves the library on its own.
 * The module exports only its handler: workerd refuses any other export.
 */
import { getOAuthApi, OAuthProvider } from '@cloudflare/workers-oauth-provider';
import { type RefreshReuseGuardKv, withRefreshReuseGuard } from '../../refresh-reuse-guard.js';

export interface SpikeEnv {
  OAUTH_KV: RefreshReuseGuardKv;
  REUSE_GUARD: string;
  OAUTH_PROVIDER?: {
    parseAuthRequest(request: Request): Promise<{ scope: string[] } & Record<string, unknown>>;
    completeAuthorization(options: {
      request: unknown;
      userId: string;
      metadata: unknown;
      scope: string[];
      props: unknown;
    }): Promise<{ redirectTo: string }>;
  };
}

interface SpikeCtx {
  props?: unknown;
}

const SPIKE_USER_ID = 'spike-user';
const TOKEN_PATH = '/oauth/token';
const SPIKE_ORIGIN = 'https://mcp.spike.test';
const REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 3600;

const providerOptions = {
  apiRoute: '/api',
  apiHandler: {
    fetch(_request: Request, _env: SpikeEnv, ctx: SpikeCtx) {
      return Promise.resolve(Response.json({ props: ctx.props }));
    },
  },
  defaultHandler: {
    async fetch(request: Request, env: SpikeEnv) {
      const url = new URL(request.url);
      if (url.pathname !== '/authorize' || !env.OAUTH_PROVIDER) {
        return new Response('not found', { status: 404 });
      }
      const authRequest = await env.OAUTH_PROVIDER.parseAuthRequest(request);
      const { redirectTo } = await env.OAUTH_PROVIDER.completeAuthorization({
        request: authRequest,
        userId: SPIKE_USER_ID,
        metadata: {},
        scope: authRequest.scope,
        props: { userId: SPIKE_USER_ID },
      });
      return new Response(null, {
        status: 302,
        headers: { Location: redirectTo },
      });
    },
  },
  authorizeEndpoint: '/authorize',
  tokenEndpoint: TOKEN_PATH,
  clientRegistrationEndpoint: '/register',
  scopesSupported: ['mcp:read', 'offline_access'],
  refreshTokenTTL: REFRESH_TOKEN_TTL_SECONDS,
  resourceMetadata: {
    resource: `${SPIKE_ORIGIN}/api`,
    authorization_servers: [SPIKE_ORIGIN],
  },
};

const provider = new OAuthProvider(providerOptions as never);

type ProviderFetch = (request: Request, env: SpikeEnv, ctx: SpikeCtx) => Promise<Response>;
const providerFetch: ProviderFetch = (request, env, ctx) =>
  (provider as unknown as { fetch: ProviderFetch }).fetch(request, env, ctx);

const guardedFetch = withRefreshReuseGuard<SpikeEnv, SpikeCtx>(providerFetch, {
  tokenPath: TOKEN_PATH,
  kv: (env) => env.OAUTH_KV,
  revokeGrant: (env, grantId, userId) =>
    getOAuthApi(providerOptions as never, env as never).revokeGrant(grantId, userId),
  markerTtlSeconds: REFRESH_TOKEN_TTL_SECONDS,
});

export default {
  fetch(request: Request, env: SpikeEnv, ctx: SpikeCtx): Promise<Response> {
    return env.REUSE_GUARD === '1'
      ? guardedFetch(request, env, ctx)
      : providerFetch(request, env, ctx);
  },
};

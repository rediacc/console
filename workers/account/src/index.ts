import { WorkerEntrypoint } from 'cloudflare:workers';
import accountApp from '../../../private/account/src/entry/cloudflare.js';

interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
  /** The executor proxy service binding (wrangler.eu.toml); read by the console route. */
  EXECUTOR?: Fetcher;
  [key: string]: unknown;
}

// Mirrors packages/www/public/_headers. Applied to every response served from this worker (SPA HTML, static assets, API JSON, redirects, 404). Responses that already declare a Content-Security-Policy (the invoice PDF routes —
// private/account/src/routes/{root,portal}-invoices.ts) keep their stricter
// per-route policy untouched.
const SECURITY_HEADERS: Record<string, string> = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  // Permissions-Policy must keep WebAuthn (passkey) open or @simplewebauthn/browser calls fail under future Cloudflare-edge tightening. Stripe redirects via window.location.assign which is a top-level navigation not gated by Permissions-Policy.
  'Permissions-Policy':
    'camera=(), microphone=(), geolocation=(), payment=(self), publickey-credentials-get=(self), publickey-credentials-create=(self)',
  'Content-Security-Policy': [
    "default-src 'self'",
    "script-src 'self' https://challenges.cloudflare.com",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self' https://challenges.cloudflare.com",
    "frame-src 'self' https://challenges.cloudflare.com",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    'upgrade-insecure-requests',
  ].join('; '),
};

function withSecurityHeaders(response: Response): Response {
  if (response.headers.has('content-security-policy')) {
    return response;
  }
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
    headers.set(name, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

/** The account portal's asset response for a path under /account. */
function serveAccountPortal(request: Request, url: URL, env: Env): Promise<Response> {
  // Static files (JS, CSS, SVG, fonts): serve directly from assets
  if (/\.\w+$/.test(url.pathname)) {
    return env.ASSETS.fetch(request);
  }
  // SPA routes: rewrite to /account/ so assets serves index.html. Don't use /account/index.html -- Cloudflare pretty URLs 307-redirects it.
  if (url.pathname !== '/account' && url.pathname !== '/account/') {
    const spaRequest = new Request(new URL('/account/', url.origin), request);
    return env.ASSETS.fetch(spaRequest);
  }
  return env.ASSETS.fetch(request);
}

/**
 * The account API for Workers in this Cloudflare account, reached ONLY through a service binding that names it (`entrypoint = "CloudflareInternal"` in the caller's `[[services]]` block; workers/proxy is the one caller). Cloudflare routes every internet request to the default export below, never to a named entrypoint, so a request here never left Cloudflare's network, and the app is told so (private/account/src/utils/request.ts markServiceBindingEnv): a 'cloudflare'-bound API token is then accepted although a binding request carries no client address. A binding without `entrypoint` (workers/www's ACCOUNT, which forwards the public contact/newsletter forms on behalf of internet clients) keeps reaching the default export, unmarked.
 */
export class CloudflareInternal extends WorkerEntrypoint<Env> {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/account/api/')) {
      return withSecurityHeaders(new Response('Not Found', { status: 404 }));
    }
    return withSecurityHeaders(
      await accountApp.fetchViaServiceBinding(request, this.env, this.ctx)
    );
  }
}

/**
 * The executor token issuer, reached ONLY through a service binding that names it (`entrypoint = "ExecutorIssuer"` in workers/proxy/wrangler.<target>.toml's ISSUER block). One RPC method, `issue()`, with no arguments and no `fetch`, so nothing a caller sends can steer what is minted: each call mints a fresh short-lived token for the ROOT_EMAIL user's org, after re-checking that user's role and the org's subscription; the TTL, scopes, ip binding and issuer key are defined in private/account/src/services/executor-issuer.service.ts and not repeated here. A refusal rejects with the reason code as the message and is audited as `executor_token.refused`.
 */
export class ExecutorIssuer extends WorkerEntrypoint<Env> {
  issue(): Promise<{ token: string; expiresAt: string }> {
    return accountApp.issueExecutorToken(this.env);
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Account portals (eu/us/asia/bench + edge variants) are logged-in apps, not public content — keep them out of every search index.
    if (url.pathname === '/robots.txt') {
      return withSecurityHeaders(
        new Response('User-agent: *\nDisallow: /\n', {
          headers: {
            'content-type': 'text/plain; charset=utf-8',
            'cache-control': 'public, max-age=86400',
          },
        })
      );
    }

    // Account API: delegate to Hono app (handles auth, billing, configs, webhooks, etc.)
    if (url.pathname.startsWith('/account/api/') || url.pathname === '/account/api') {
      return withSecurityHeaders(await accountApp.fetch(request, env, ctx));
    }

    // Account SPA: serve portal assets
    if (url.pathname === '/account' || url.pathname.startsWith('/account/')) {
      return withSecurityHeaders(await serveAccountPortal(request, url, env));
    }

    // Root -> redirect to account portal
    if (url.pathname === '/' || url.pathname === '') {
      return withSecurityHeaders(
        Response.redirect(new URL('/account/', url.origin).toString(), 302)
      );
    }

    return withSecurityHeaders(new Response('Not Found', { status: 404 }));
  },

  // Cron entrypoint. Every deployed region reaches the account app's scheduled work through here, so forgetting this re-export silently disables it: the nightly event_log retention sweep never ran in any region until this line existed, because this module used to export `fetch` alone while the handler sat unreachable in private/account/src/entry/cloudflare.ts. The [triggers]
  // block in every wrangler.*.toml is the other half; both are gated by
  // private/account/tests/integration/cron-wiring.test.ts.
  scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext): void {
    // No `as never` here: the Hono entry declares `env: CloudflareEnv` and this worker's Env satisfies it, so the cast was load-bearing for nothing and
    // @typescript-eslint/no-unnecessary-type-assertion said so as soon as
    // workers/ entered the lint scope (2026-09-06). Keeping it would have hidden any real future divergence between the two Env shapes behind `never`.
    accountApp.scheduled(controller, env, ctx);
  },
};

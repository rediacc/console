import accountApp from '../../../private/account/src/entry/cloudflare.js';

interface Env {
  ASSETS: Fetcher;
  [key: string]: unknown;
}

// Mirrors packages/www/public/_headers. Applied to every response served from
// this worker (SPA HTML, static assets, API JSON, redirects, 404). Responses
// that already declare a Content-Security-Policy (the invoice PDF routes —
// private/account/src/routes/{root,portal}-invoices.ts) keep their stricter
// per-route policy untouched.
const SECURITY_HEADERS: Record<string, string> = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  // Permissions-Policy must keep WebAuthn (passkey) open or @simplewebauthn/browser
  // calls fail under future Cloudflare-edge tightening. Stripe redirects via
  // window.location.assign which is a top-level navigation not gated by Permissions-Policy.
  'Permissions-Policy':
    'camera=(), microphone=(), geolocation=(), payment=(self), publickey-credentials-get=(self), publickey-credentials-create=(self)',
  'Content-Security-Policy': [
    "default-src 'self'",
    "script-src 'self' https://challenges.cloudflare.com",
    "style-src 'self' 'unsafe-inline'",
    'img-src \'self\' data:',
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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Account portals (eu/us/asia/bench + edge variants) are logged-in apps,
    // not public content — keep them out of every search index.
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
      return withSecurityHeaders(await accountApp.fetch(request, env));
    }

    // Account SPA: serve portal assets
    if (url.pathname === '/account' || url.pathname.startsWith('/account/')) {
      // Static files (JS, CSS, SVG, fonts): serve directly from assets
      if (/\.\w+$/.test(url.pathname)) {
        return withSecurityHeaders(await env.ASSETS.fetch(request));
      }
      // SPA routes: rewrite to /account/ so assets serves index.html.
      // Don't use /account/index.html -- Cloudflare pretty URLs 307-redirects it.
      if (url.pathname !== '/account' && url.pathname !== '/account/') {
        const spaRequest = new Request(new URL('/account/', url.origin), request);
        return withSecurityHeaders(await env.ASSETS.fetch(spaRequest));
      }
      return withSecurityHeaders(await env.ASSETS.fetch(request));
    }

    // Root -> redirect to account portal
    if (url.pathname === '/' || url.pathname === '') {
      return withSecurityHeaders(
        Response.redirect(new URL('/account/', url.origin).toString(), 302)
      );
    }

    return withSecurityHeaders(new Response('Not Found', { status: 404 }));
  },
};

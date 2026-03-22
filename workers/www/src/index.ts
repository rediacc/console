import { drizzle } from 'drizzle-orm/d1';
import { createApp } from '../../../private/account/src/app.js';
import * as schema from '../../../private/account/src/db/schema.js';
import { envSchema } from '../../../private/account/src/types/env.js';
import type { Database } from '../../../private/account/src/db/index.js';

interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Preview origin rewriting
// ---------------------------------------------------------------------------
// On non-production hostnames (e.g. pr-397.rediacc.workers.dev), rewrite
// https://www.rediacc.com → the current origin in all text responses so that
// install commands, canonical URLs, sitemaps, etc. reflect the preview domain.
// Production traffic is unaffected — the worker only handles /account/* routes
// in production (via run_worker_first), so this code path is never reached.
// ---------------------------------------------------------------------------

const PRODUCTION_ORIGIN = 'https://www.rediacc.com';

const REWRITABLE_TYPES = [
  'text/html',
  'text/plain',
  'text/xml',
  'application/xml',
  'application/json',
  'application/rss+xml',
  'application/javascript',
  'text/javascript',
  'text/css',
];

function shouldRewrite(contentType: string | null): boolean {
  if (!contentType) return false;
  return REWRITABLE_TYPES.some((t) => contentType.startsWith(t));
}

async function rewriteOrigin(response: Response, origin: string): Promise<Response> {
  if (!shouldRewrite(response.headers.get('content-type'))) return response;

  const body = await response.text();
  const rewritten = body.includes(PRODUCTION_ORIGIN)
    ? body.replaceAll(PRODUCTION_ORIGIN, origin)
    : body;

  return new Response(rewritten, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

// ---------------------------------------------------------------------------

const accountApp = createApp(
  (c) => {
    const ctx = c as { env: Record<string, unknown> };
    return envSchema.parse(ctx.env);
  },
  (c) => {
    const ctx = c as { env: Env };
    return drizzle(ctx.env.DB, { schema }) as unknown as Database;
  }
);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const isPreview = url.hostname !== 'www.rediacc.com';

    // Handle account API requests directly (account server embedded)
    if (url.pathname.startsWith('/account/api/') || url.pathname === '/account/api') {
      return accountApp.fetch(request, env);
    }

    // Serve account SPA for /account/* routes
    if (url.pathname === '/account' || url.pathname.startsWith('/account/')) {
      // Static files (JS, CSS, SVG, etc.): serve from assets directly
      if (/\.\w+$/.test(url.pathname)) {
        return env.ASSETS.fetch(request);
      }
      // SPA routes: rewrite to /account/ so assets serves index.html.
      // Don't use /account/index.html — Cloudflare pretty URLs 307-redirects it.
      if (url.pathname !== '/account' && url.pathname !== '/account/') {
        const spaRequest = new Request(new URL('/account/', url.origin), request);
        const response = await env.ASSETS.fetch(spaRequest);
        return isPreview ? rewriteOrigin(response, url.origin) : response;
      }
      const response = await env.ASSETS.fetch(request);
      return isPreview ? rewriteOrigin(response, url.origin) : response;
    }

    // All other routes — served from static assets.
    // In preview, run_worker_first = ["/*"] routes everything through here.
    // In production, this path is only reached for /account/* (handled above).
    const response = await env.ASSETS.fetch(request);
    return isPreview ? rewriteOrigin(response, url.origin) : response;
  },
};

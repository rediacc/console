import { findSmartRedirect } from './smart-redirect';
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

export const REWRITABLE_TYPES = [
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

// Install scripts are served with content-types outside REWRITABLE_TYPES
// (application/x-sh, or no content-type for .ps1). Bypass the MIME check
// so the channel default is still rewritten on preview hosts.
export const REWRITABLE_PATHS = ['/install.sh', '/install.ps1'];

export function shouldRewrite(contentType: string | null, pathname: string): boolean {
  if (REWRITABLE_PATHS.includes(pathname)) return true;
  if (!contentType) return false;
  return REWRITABLE_TYPES.some((t) => contentType.startsWith(t));
}

/** Extract release channel from hostname (pr-420 | edge | stable). */
export function getChannel(hostname: string): string {
  const match = hostname.match(/^([^.]+)\.rediacc\./);
  return match ? match[1] : 'stable';
}

export async function rewriteOrigin(response: Response, url: URL, channel: string): Promise<Response> {
  if (!shouldRewrite(response.headers.get('content-type'), url.pathname)) return response;

  let body = await response.text();
  const origin = url.origin;

  // Rewrite production origin -> preview origin
  if (body.includes(PRODUCTION_ORIGIN)) {
    body = body.replaceAll(PRODUCTION_ORIGIN, origin);
  }

  // Rewrite install script defaults so CLI uses the preview channel
  // and auto-connects to the preview account server.
  // Bash: ${REDIACC_CHANNEL:-stable}  PowerShell: } else { "stable" }
  body = body.replaceAll('REDIACC_CHANNEL:-stable', `REDIACC_CHANNEL:-${channel}`);
  body = body.replaceAll('REDIACC_SERVER_URL:-}', `REDIACC_SERVER_URL:-${origin}}`);
  body = body.replaceAll('} else { "stable" }', `} else { "${channel}" }`);

  // Rewrite channel references in website HTML (install commands baked at build time)
  for (const format of ['apt', 'rpm', 'apk', 'archlinux', 'cli', 'npm']) {
    body = body.replaceAll(`releases.rediacc.com/${format}/stable`, `releases.rediacc.com/${format}/${channel}`);
  }
  body = body.replaceAll('elite/cli:stable', `elite/cli:${channel}`);

  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

// ---------------------------------------------------------------------------

// Non-prod hostnames (edge, PR previews) should not be indexed — sitemaps and
// canonical links still point at www.rediacc.com after rewriteOrigin(), so
// letting crawlers in would create duplicate-content noise.
export function buildDisallowRobots(): Response {
  return new Response('User-agent: *\nDisallow: /\n', {
    headers: {
      'content-type': 'text/plain; charset=utf-8',
      'cache-control': 'public, max-age=86400',
    },
  });
}

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
    const channel = getChannel(url.hostname);

    if (url.pathname === '/robots.txt' && isPreview) {
      return buildDisallowRobots();
    }

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
        return isPreview ? rewriteOrigin(response, url, channel) : response;
      }
      const response = await env.ASSETS.fetch(request);
      return isPreview ? rewriteOrigin(response, url, channel) : response;
    }

    // All other routes — served from static assets.
    // run_worker_first = ["/*"] routes everything through here.
    const response = await env.ASSETS.fetch(request);

    // Smart 404 redirect: score-based fuzzy matching against known routes
    if (response.status === 404) {
      const redirect = await findSmartRedirect(url.pathname, env.ASSETS);
      if (redirect) {
        console.log(JSON.stringify({ event: 'smart-redirect', from: url.pathname, to: redirect.url, score: redirect.score }));
        return new Response(null, {
          status: 302,
          headers: { Location: new URL(redirect.url, url.origin).toString(), 'X-Redirect-Reason': 'smart-404' },
        });
      }
    }

    return isPreview ? rewriteOrigin(response, url, channel) : response;
  },
};

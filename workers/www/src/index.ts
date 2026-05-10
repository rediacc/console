import { findSmartRedirect } from './smart-redirect';
import { applyRedirect } from './redirect-aliases';
import { drizzle } from 'drizzle-orm/d1';
import { createApp } from '../../../private/account/src/app.js';
import * as schema from '../../../private/account/src/db/schema.js';
import { envSchema } from '../../../private/account/src/types/env.js';
import type { Database } from '../../../private/account/src/db/index.js';

interface Env {
  ASSETS: Fetcher;
  // Only bound in PR previews (deploy-www.sh mints account-db-pr-N and
  // injects the binding via wrangler.preview.toml). On stable / edge,
  // /account/api/* is served by the regional workers, so DB is absent
  // here and the branch below 410s.
  DB?: D1Database;
  // Service binding to the EU regional account worker. Used to forward the
  // public marketing endpoints (contact submit, newsletter subscribe) so
  // the forms on www.rediacc.com / edge.rediacc.com can reach a DB-bound
  // backend without cross-origin CORS. Bound on stable + edge wrangler
  // configs, absent on PR previews (which serve via env.DB instead).
  ACCOUNT?: Fetcher;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Preview origin rewriting
// ---------------------------------------------------------------------------
// On non-stable hostnames (edge.rediacc.com, pr-397.rediacc.workers.dev), rewrite
// https://www.rediacc.com → the current origin in all text responses so that
// install commands, canonical URLs, sitemaps, etc. reflect the preview domain.
// Stable (www.rediacc.com) traffic is unaffected — on that hostname isPreview
// is false and rewriteOrigin() is skipped.
// ---------------------------------------------------------------------------

const WWW_ORIGIN = 'https://www.rediacc.com';

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

  // Rewrite canonical www origin -> current preview origin
  if (body.includes(WWW_ORIGIN)) {
    body = body.replaceAll(WWW_ORIGIN, origin);
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
    if (!ctx.env.DB) {
      throw new Error('DB binding not configured on this worker; /account/api is not served here');
    }
    return drizzle(ctx.env.DB, { schema }) as unknown as Database;
  }
);

// ---------------------------------------------------------------------------
// 404 recovery — normalization + curated redirect table
// ---------------------------------------------------------------------------
// Google indexed historical URLs with trailing slashes, .html/.md suffixes,
// and lang-prefixed paths. Normalize first, then look up in the curated
// ./redirects.json table. See redirect-aliases.ts.

const SUPPORTED_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh', 'et', 'ko', 'pt', 'it'] as const;
const DEFAULT_LANG = 'en';

/**
 * Normalize a URL pathname to the canonical form we emit in static builds:
 * no trailing slash, no .html/.md suffix, lowercase. Returns the normalized
 * path and a flag indicating whether anything changed (so the caller can 301
 * to the canonical URL).
 *
 * Leaves percent-encoded sequences untouched — lowercasing a path like
 * `/es/blog/tags/configuraci%C3%B3n` would re-encode to `%c3%b3` and
 * trigger a redirect loop against Cloudflare ASSETS (which re-encodes
 * back to uppercase per RFC 3986's recommendation). We lowercase only
 * outside percent-encoded triples.
 */
export function normalizePath(pathname: string): { path: string; changed: boolean } {
  let p = pathname;

  // Strip trailing slash (except root "/")
  if (p.length > 1 && p.endsWith('/')) {
    p = p.replace(/\/+$/, '');
  }

  // Strip .html / .md suffix Google sometimes indexed
  p = p.replace(/\.(html|md)$/i, '');

  // Collapse double slashes
  p = p.replace(/\/{2,}/g, '/');

  // Lowercase outside percent-encoded sequences only. A %XX triple is
  // case-insensitive per RFC 3986 but ASSETS normalizes to uppercase;
  // lowercasing the whole string would loop.
  p = p.replace(/(%[0-9a-fA-F]{2})|([^%]+)/g, (_, enc, plain) =>
    enc ? enc : (plain as string).toLowerCase()
  );

  return { path: p, changed: p !== pathname };
}

/**
 * Split /en/docs/foo into lang="en" + pathWithoutLang="/docs/foo".
 * If no language prefix, returns { lang: null, pathWithoutLang: path }.
 */
export function detectLanguage(path: string): { lang: string | null; pathWithoutLang: string } {
  const m = path.match(/^\/([a-z]{2})(\/.*|$)/);
  if (m && (SUPPORTED_LANGUAGES as readonly string[]).includes(m[1])) {
    return { lang: m[1], pathWithoutLang: m[2] || '/' };
  }
  return { lang: null, pathWithoutLang: path };
}

function buildRedirectResponse(target: string, status: 301, reason: string): Response {
  return new Response(null, {
    status,
    headers: {
      Location: target,
      'X-Redirect-Reason': reason,
      'Cache-Control': 'public, max-age=3600',
    },
  });
}

function buildGoneResponse(rationale: string): Response {
  return new Response(null, {
    status: 410,
    headers: {
      'X-Redirect-Reason': 'curated-410',
      'X-Redirect-Rationale': rationale.slice(0, 200),
      'Cache-Control': 'public, max-age=3600',
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const isPreview = url.hostname !== 'www.rediacc.com';
    const channel = getChannel(url.hostname);

    if (url.pathname === '/robots.txt' && isPreview) {
      return buildDisallowRobots();
    }

    // Account API: served here only on PR previews (env.DB bound by
    // deploy-www.sh). On stable / edge the regional workers serve it.
    // Public marketing endpoints (contact submit, newsletter subscribe)
    // are forwarded via the ACCOUNT service binding so the forms on
    // www.rediacc.com keep working; everything else 410s so the SPA
    // region picker routes authenticated traffic to the right region.
    if (url.pathname.startsWith('/account/api/') || url.pathname === '/account/api') {
      if (env.DB) {
        return accountApp.fetch(request, env);
      }
      const isPublicMarketingEndpoint =
        url.pathname.startsWith('/account/api/v1/contact/') ||
        url.pathname.startsWith('/account/api/v1/newsletter/');
      if (isPublicMarketingEndpoint && env.ACCOUNT) {
        return env.ACCOUNT.fetch(request);
      }
      return new Response(
        JSON.stringify({
          error: 'gone',
          message: 'Account API is served by regional workers (eu/us/asia.rediacc.com).',
        }),
        { status: 410, headers: { 'content-type': 'application/json; charset=utf-8' } }
      );
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

    // Static-asset paths are case-sensitive (Vite hashes like client.BzZdRM54.js,
    // fonts like Inter-Regular.woff2). normalizePath() below would lowercase
    // them and 301 to a filename that doesn't exist on disk — breaking CSS,
    // fonts, and dynamic imports. Serve directly from ASSETS before normalizing.
    if (/^\/(assets|fonts|images|videos|scripts|styles|_astro)\//.test(url.pathname)) {
      const response = await env.ASSETS.fetch(request);
      return isPreview ? rewriteOrigin(response, url, channel) : response;
    }

    // -----------------------------------------------------------------------
    // 404 recovery: normalize path, then consult the curated redirect table.
    // -----------------------------------------------------------------------

    // Root -> default language. Replaces the old public/_redirects rule which
    // Workers don't process (that was a Cloudflare Pages feature).
    if (url.pathname === '/') {
      const target = new URL(`/${DEFAULT_LANG}${url.search}`, url.origin);
      return buildRedirectResponse(target.toString(), 301, 'root-to-default-lang');
    }

    // Step 1: normalize (strip trailing slash, .html/.md, lowercase).
    // If the canonical form differs, 301 to it immediately.
    const normalized = normalizePath(url.pathname);
    if (normalized.changed) {
      const canonical = new URL(normalized.path + url.search, url.origin);
      return buildRedirectResponse(canonical.toString(), 301, 'canonicalize');
    }

    // Step 2: detect language prefix, strip for lookup.
    const { lang, pathWithoutLang } = detectLanguage(url.pathname);

    // Step 3: curated table lookup (exact, then pattern).
    // Decode percent-encoded chars so UTF-8 keys (e.g. /blog/tags/configuración)
    // match regardless of whether the request came in encoded form.
    let lookupPath = pathWithoutLang;
    try {
      lookupPath = decodeURIComponent(pathWithoutLang);
    } catch {
      /* malformed encoding — fall back to raw */
    }
    const alias = applyRedirect(lookupPath);
    if (alias) {
      if (alias.status === 410 || alias.to === null) {
        return buildGoneResponse(alias.rationale);
      }
      // Preserve language prefix if present, else use default
      const targetLang = lang ?? DEFAULT_LANG;
      // If the target starts with /account, don't add lang (Worker-served SPA)
      const targetPath = alias.to.startsWith('/account') ? alias.to : `/${targetLang}${alias.to}`;
      // Self-redirect guard: if the redirect would land on the same URL (e.g.,
      // /en/checkout/success → /en/checkout/success), fall through to ASSETS
      // so the user lands on the actual page instead of looping.
      if (targetPath !== url.pathname) {
        const target = new URL(targetPath + url.search, url.origin);
        return buildRedirectResponse(target.toString(), 301, `curated-${alias.via}`);
      }
    }

    // Step 4: static asset fetch.
    // run_worker_first = ["/*"] routes everything through here.
    const response = await env.ASSETS.fetch(request);

    // Step 5: on 404, consult the fuzzy smart-redirect fallback.
    if (response.status === 404) {
      const redirect = await findSmartRedirect(url.pathname, env.ASSETS);
      if (redirect) {
        console.log(JSON.stringify({ event: 'smart-redirect', from: url.pathname, to: redirect.url, score: redirect.score }));
        return new Response(null, {
          status: 301,
          headers: { Location: new URL(redirect.url, url.origin).toString(), 'X-Redirect-Reason': 'smart-404' },
        });
      }
      // Log unmatched 404s for future alias-table maintenance.
      console.log(JSON.stringify({ event: 'redirect-miss', path: url.pathname }));
    }

    return isPreview ? rewriteOrigin(response, url, channel) : response;
  },
};

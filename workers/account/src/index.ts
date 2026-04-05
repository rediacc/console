import accountApp from '../../../private/account/src/entry/cloudflare.js';

interface Env {
  ASSETS: Fetcher;
  [key: string]: unknown;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Health check + Account API: delegate to Hono app
    if (url.pathname === '/health' || url.pathname.startsWith('/account/api/') || url.pathname === '/account/api') {
      return accountApp.fetch(request, env);
    }

    // Account SPA: serve portal assets
    if (url.pathname === '/account' || url.pathname.startsWith('/account/')) {
      // Static files (JS, CSS, SVG, fonts): serve directly from assets
      if (/\.\w+$/.test(url.pathname)) {
        return env.ASSETS.fetch(request);
      }
      // SPA routes: rewrite to /account/ so assets serves index.html.
      // Don't use /account/index.html -- Cloudflare pretty URLs 307-redirects it.
      if (url.pathname !== '/account' && url.pathname !== '/account/') {
        const spaRequest = new Request(new URL('/account/', url.origin), request);
        return env.ASSETS.fetch(spaRequest);
      }
      return env.ASSETS.fetch(request);
    }

    // Root -> redirect to account portal
    if (url.pathname === '/' || url.pathname === '') {
      return Response.redirect(new URL('/account/', url.origin).toString(), 302);
    }

    return new Response('Not Found', { status: 404 });
  },
};

interface Env {
  ACCOUNT_SERVER: Fetcher;
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Proxy /account/api/* to account-server without path rewriting.
    // The account server's Hono routes are mounted at /account/api/v1 (not /api/v1),
    // so the full path must be preserved through the service binding.
    if (url.pathname.startsWith('/account/api/') || url.pathname === '/account/api') {
      return env.ACCOUNT_SERVER.fetch(request);
    }

    // Serve account SPA for /account/* routes
    if (url.pathname === '/account' || url.pathname.startsWith('/account/')) {
      const response = await env.ASSETS.fetch(request);
      // SPA fallback: if no static file found, serve /account/index.html
      if (response.status === 404) {
        const spaUrl = new URL('/account/index.html', url.origin);
        return env.ASSETS.fetch(new Request(spaUrl, request));
      }
      return response;
    }

    return env.ASSETS.fetch(request);
  },
};

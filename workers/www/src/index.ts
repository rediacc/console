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
        return env.ASSETS.fetch(spaRequest);
      }
      return env.ASSETS.fetch(request);
    }

    return env.ASSETS.fetch(request);
  },
};

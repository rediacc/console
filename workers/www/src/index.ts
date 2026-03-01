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
      const response = await env.ASSETS.fetch(request);
      if (response.status === 404) {
        const spaUrl = new URL('/account/index.html', url.origin);
        return env.ASSETS.fetch(new Request(spaUrl, request));
      }
      return response;
    }

    return env.ASSETS.fetch(request);
  },
};

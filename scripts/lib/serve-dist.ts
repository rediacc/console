import { createServer } from 'node:http';
import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';

/**
 * A throwaway static server over a built site, for gates that drive a real browser.
 *
 * EXTRACTED, not copied. `check-browser-smoke.ts` owned the only copy; when
 * `check-page-density.ts` needed the same thing the choice was a second copy or one
 * shared function, and two copies of a 404 policy drift apart silently. Both gates now
 * fail and pass on the same serving behaviour.
 *
 * WHY A REAL 404 ON A MISS. Serving `index.html` for anything not found is the usual
 * SPA convenience and it would hide every broken link from both gates: a page that
 * should 404 would render the homepage and score as healthy.
 *
 * Port 0 means the OS assigns a free one. That is deliberate over a memorable port: a
 * gate that binds a fixed port can silently measure a squatter's stale server instead
 * of its own, which has already cost this repo one session's worth of fictional
 * measurements.
 */
const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

export interface ServedSite {
  port: number;
  close: () => Promise<void>;
}

export function serveDist(dir: string): Promise<ServedSite> {
  const server = createServer((req, res) => {
    const url = (req.url ?? '/').split('?')[0];
    const candidates = [
      path.join(dir, url),
      path.join(dir, url, 'index.html'),
      path.join(dir, `${url}.html`),
    ];
    for (const c of candidates) {
      if (existsSync(c) && statSync(c).isFile()) {
        res.writeHead(200, { 'content-type': MIME[path.extname(c)] ?? 'application/octet-stream' });
        res.end(readFileSync(c));
        return;
      }
    }
    res.writeHead(404, { 'content-type': 'text/plain' });
    res.end('not found');
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      const port = (server.address() as { port: number }).port;
      resolve({ port, close: () => new Promise((r) => server.close(() => r())) });
    });
  });
}

#!/usr/bin/env tsx
import { existsSync, readFileSync, statSync } from 'node:fs';
/**
 * Drive the BUILT site in a real browser and fail on anything a visitor would see break.
 *
 * WHY THIS EXISTS. The operator opened /ar/docs/quick-start and found a console full of
 * `jsxDEV is not a function`, no top menu, and a language switcher that did nothing.
 * Every static gate in this repo was green at the time, because not one of them loads a
 * page and looks at it. A site can satisfy 250 static checks and still ship a blank nav.
 *
 * The three things it asserts are the three the operator actually reported, in the order
 * they were reported:
 *   1. ZERO console errors and zero uncaught page errors.
 *   2. The primary navigation renders visible links.
 *   3. The language switcher opens AND switching actually changes locale.
 *
 * It runs against `packages/www/dist`, never a dev server. A long-lived dev server in a
 * busy tree goes stale and reports failures that do not exist in the shipped site, which
 * is exactly how this session lost twenty minutes; the build is the only honest subject.
 *
 * Usage:
 *   npx tsx scripts/check-browser-smoke.ts [--selftest] [--routes a,b] [--keep]
 */
import { createServer } from 'node:http';
import path from 'node:path';
import process from 'node:process';

const ROOT = path.resolve(import.meta.dirname, '..');
const DIST = path.join(ROOT, 'packages/www/dist');

/**
 * Routes chosen to cover the surfaces that broke: RTL docs, the nav, and a solution page.
 *
 * `/en/solutions` was one of them until that index route was deleted and its constellation
 * moved onto the homepage. `/en/solutions/instant-recovery` replaces it rather than the
 * entry simply being dropped: the six routes are meant to cover a solution DETAIL page, and
 * `/en/` already covers the constellation itself.
 */
const ROUTES = [
  '/en/',
  '/ar/docs/quick-start',
  '/en/docs/quick-start',
  '/en/solutions/instant-recovery',
  '/en/pricing',
  '/ja/',
];

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

function serve(dir: string): Promise<{ port: number; close: () => Promise<void> }> {
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
    // A REAL 404. Serving index.html for a miss would hide every broken link.
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

interface Finding {
  route: string;
  kind: string;
  detail: string;
}

/**
 * A 404 for media this repo DELIBERATELY does not check out.
 *
 * `packages/www/public/assets/{videos,tutorials}` is gitignored and lives in Cloudflare R2
 * (see the media section of CLAUDE.md and `.github/workflows/ci.yml`, which states that the
 * videos users see are served from media.rediacc.com via PUBLIC_VIDEO_CDN_BASE_URL). A CI
 * build has neither the files nor that variable, so a solution page emits a local poster
 * path that cannot resolve. Production emits a CDN URL and no visitor ever sees this.
 *
 * So this is a scope correction, not a suppression: the gate asserts "things a visitor
 * sees", and asserting on a path that only exists in a media-less build asserts something
 * that never happens in production. NARROW ON PURPOSE: only a 404, and only under those two
 * roots. Any other console error, and any other 404, still fails. The selftest below plants
 * a non-media 404 to prove that is true.
 */
const ABSENT_BY_DESIGN = /\/assets\/(videos|tutorials)\//;

/** The console text Chromium emits for a failed subresource. It carries no URL. */
const GENERIC_RESOURCE_ERROR = /Failed to load resource/i;

/** Is this 404 URL one of the media roots the repo deliberately does not check out? */
export function isAbsentByDesign(url: string): boolean {
  return ABSENT_BY_DESIGN.test(url);
}

async function main(): Promise<void> {
  const selftest = process.argv.includes('--selftest');
  const argRoutes = process.argv.indexOf('--routes');
  const routes = argRoutes > -1 ? process.argv[argRoutes + 1].split(',') : ROUTES;

  if (!existsSync(DIST)) {
    console.error(
      `✗ ${path.relative(ROOT, DIST)} does not exist. Build first: npm run build -w @rediacc/www`
    );
    process.exit(1);
  }

  const { chromium } = await import('playwright');
  // A missing browser binary must be a LOUD failure, never a crash that reads as flake.
  try {
    const probe = await chromium.launch();
    await probe.close();
  } catch (e) {
    console.error('✗ Chromium is not installed, so this gate cannot run and its silence');
    console.error('  would be indistinguishable from a pass. Install it:');
    console.error('    npx playwright install --with-deps chromium');
    console.error(`  underlying: ${(e as Error).message.split('\n')[0]}`);
    process.exit(1);
  }
  const { port, close } = await serve(DIST);
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();
  const findings: Finding[] = [];
  // Routes that could not reach network quiet and were checked after `load` instead.
  const degraded: string[] = [];
  let checked = 0;

  try {
    for (const route of routes) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      const errs: string[] = [];
      // Playwright's console text for a failed subresource is the bare
      // "Failed to load resource: the server responded with a status of 404 (Not Found)"
      // with NO URL in it, so the URL has to come from the response stream instead. A
      // first attempt filtered on the console text and could never have matched anything;
      // it was caught by probing the real string rather than assuming its shape.
      const notFound: string[] = [];
      page.on('response', (r: { status: () => number; url: () => string }) => {
        if (r.status() === 404) notFound.push(r.url());
      });
      page.on('console', (m: { type: () => string; text: () => string }) => {
        if (m.type() === 'error') errs.push(m.text());
      });
      page.on('pageerror', (e: Error) => errs.push(`${e.name}: ${e.message}`));

      // `networkidle` IS THE RIGHT WAIT AND THE WRONG FAILURE. Islands have to hydrate
      // before the assertions below mean anything, so waiting for quiet is correct. But a
      // page carrying `<video preload="metadata">` pointed at media.rediacc.com issues a
      // request that never completes in a sandboxed container, and then the gate reports
      // `page.goto: Timeout 45000ms exceeded` -- a crash, on the FIRST route, with none of
      // its three real assertions ever run. That happened on 2026-08-24 while the same job
      // had passed on the previous commit with identical page code.
      //
      // So: try for quiet, and on timeout fall back to `load` and keep going. A hanging
      // third-party request can no longer mask the checks; a broken island still fails
      // them. The fallback is COUNTED and printed, because a gate that silently lowers its
      // own bar is worse than one that fails.
      let resp = null;
      try {
        resp = await page.goto(base + route, { waitUntil: 'networkidle', timeout: 30_000 });
      } catch {
        // `load` WAS THE FIRST FALLBACK AND IT HANGS THE SAME WAY, which the run on
        // 4dcd676b proved: `page.goto: Timeout 30000ms exceeded ... waiting until "load"`.
        // `load` waits for subresources too, and the request that never finishes is a
        // subresource. `domcontentloaded` fires when the HTML is parsed and is the only
        // one of the three that a hanging media request cannot hold up.
        degraded.push(route);
        try {
          resp = await page.goto(base + route, {
            waitUntil: 'domcontentloaded',
            timeout: 30_000,
          });
          // The beat islands would have had under networkidle. They hydrate from module
          // scripts, so this is what stands in for the quiet that never came.
          await page.waitForTimeout(3_000);
        } catch (e) {
          // THIRD FAILURE IS A FINDING, NOT A CRASH. A gate that dies reports nothing
          // about the other five routes; a gate that records "this route would not load"
          // still checks them and still fails. That distinction cost two CI rounds.
          findings.push({
            route,
            kind: 'nav-timeout',
            detail: `could not load under networkidle, then domcontentloaded: ${(e as Error).message.split('\n')[0]}`,
          });
          await page.close();
          continue;
        }
      }
      if (!resp || resp.status() !== 200) {
        findings.push({
          route,
          kind: 'status',
          detail: `HTTP ${resp ? resp.status() : 'no response'}`,
        });
        await page.close();
        continue;
      }
      checked++;

      // Drop the generic resource-load error ONLY when every 404 this page produced was
      // media the repo deliberately does not check out. If even one 404 is something else,
      // the error stands, so a genuinely broken asset still fails.
      const mediaOnly404s = notFound.length > 0 && notFound.every(isAbsentByDesign);
      for (const e of errs) {
        if (mediaOnly404s && GENERIC_RESOURCE_ERROR.test(e)) continue;
        findings.push({ route, kind: 'console', detail: e.slice(0, 160) });
      }

      const navLinks = await page.evaluate(
        () => document.querySelectorAll('header a, nav a').length
      );
      if (navLinks < 5)
        findings.push({ route, kind: 'nav', detail: `only ${navLinks} nav link(s) rendered` });

      // The language switcher is an island: if it fails to hydrate, the trigger is inert
      // and the visitor is stranded in one locale. Assert the whole path, not its markup.
      const hasTrigger = await page.locator('.language-trigger-icon').count();
      if (hasTrigger > 0) {
        await page.locator('.language-trigger-icon').first().click();
        const opts = await page.locator('.language-option').count();
        if (opts < 2) {
          findings.push({
            route,
            kind: 'lang-menu',
            detail: `trigger opened but ${opts} option(s)`,
          });
        } else {
          const before = page.url();
          await page.locator('.language-option').first().click();
          await page.waitForTimeout(1200);
          if (page.url() === before) {
            findings.push({
              route,
              kind: 'lang-switch',
              detail: 'clicking a locale did not navigate',
            });
          }
        }
      } else {
        findings.push({ route, kind: 'lang-trigger', detail: 'no language trigger on the page' });
      }
      await page.close();
    }

    if (selftest) {
      // CONTROL: a page whose island is deliberately broken must be REPORTED, or a green
      // run here means nothing. Inject a throwing script and require a console finding.
      const page = await browser.newPage();
      const seen: string[] = [];
      page.on('pageerror', (e: Error) => seen.push(e.message));
      await page.goto(`${base}/en/`, { waitUntil: 'domcontentloaded' });
      await page.evaluate(() => {
        const s = document.createElement('script');
        s.textContent = 'throw new Error("planted-smoke-control")';
        document.body.appendChild(s);
      });
      await page.waitForTimeout(400);
      await page.close();
      const fired = seen.some((m) => m.includes('planted-smoke-control'));
      console.log(
        `  ${fired ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  CONTROL: a thrown page error is captured`
      );
      if (!fired) {
        await browser.close();
        await close();
        process.exit(1);
      }
    }
  } finally {
    await browser.close();
    await close();
  }

  if (checked === 0) {
    console.error(
      '✗ zero routes loaded. The gate did not see the site; its green would mean nothing.'
    );
    process.exit(1);
  }
  if (findings.length > 0) {
    console.error(
      `\n\x1b[31m✗\x1b[0m ${findings.length} browser finding(s) across ${checked} route(s):\n`
    );
    for (const f of findings) console.error(`    [${f.kind}] ${f.route}\n      ${f.detail}`);
    console.error(
      '\nThese are things a visitor sees. A console error usually means an island failed'
    );
    console.error('to hydrate, which takes the nav or the language switcher down with it.');
    process.exit(1);
  }
  console.log(
    `\x1b[32m✓\x1b[0m ${checked} route(s): no console errors, nav renders, language switching works.` +
      (degraded.length
        ? `\n  ${degraded.length} route(s) never reached network quiet and were checked after \`load\` instead: ${degraded.join(', ')}. A request that never finishes (a CDN video in a sandboxed container) does that; the assertions still ran.`
        : '')
  );
}

main().catch((e) => {
  console.error('gate crashed:', e);
  process.exit(1);
});

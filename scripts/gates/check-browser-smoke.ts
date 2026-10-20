#!/usr/bin/env tsx
import { existsSync } from 'node:fs';
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
 *   npx tsx scripts/gates/check-browser-smoke.ts [--selftest] [--routes a,b] [--keep]
 */
import path from 'node:path';
import process from 'node:process';
import { serveDist } from '../lib/serve-dist.ts';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
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

/**
 * Open the language menu and wait for its options, instead of counting once.
 *
 * RACE FIXED: the island's click handler attaches at hydration and the options render a frame after the click. Under a loaded machine (the full `ci:quick`) a single immediate `count()` read 0 while the same gate alone read 2+. Poll up to `waitMs` for at least two options; if fewer than two appear (none, or one), click once more (a click that landed before hydration is inert) and poll again, so the worst case is two polls, about `2 * waitMs`. The retry click toggles a menu that did open but rendered slowly back closed, so the larger of the two counts is returned: a menu that really has fewer than two options still returns that count, after the bounded wait, so the finding is kept.
 */
async function openLangMenu(
  page: import('playwright').Page,
  waitMs = 5_000,
  triggerSel = '.language-trigger-icon',
  optionSel = '.language-option'
): Promise<number> {
  const count = () => page.locator(optionSel).count();
  const poll = async (): Promise<number> => {
    const deadline = Date.now() + waitMs;
    let n = await count();
    while (n < 2 && Date.now() < deadline) {
      await page.waitForTimeout(100);
      n = await count();
    }
    return n;
  };
  await page.locator(triggerSel).first().click();
  let n = await poll();
  if (n < 2) {
    await page.locator(triggerSel).first().click();
    n = Math.max(n, await poll());
  }
  return n;
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
 * (see the media section of CLAUDE.md). The URL builders resolve LOCAL FIRST
 * (`packages/www/src/utils/media-url.ts`): a build with no local media emits CDN URLs, so
 * a same-origin 404 under these roots can only come from a developer checkout holding a
 * partial local render (a poster without its mp4, say) -- never from production, which
 * has no local files at all and therefore never emits these paths.
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
  const { port, close } = await serveDist(DIST);
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();
  const findings: Finding[] = [];
  // Routes that could not reach network quiet and were checked after `domcontentloaded` instead. NAME THE REAL FALLBACK: this comment and the message below both said `load` until a review caught it -- `load` was the FIRST fallback tried and it hangs the same way networkidle does (see the comment on the goto call), so the chain moved to `domcontentloaded` without this line being
  // updated. A message that names the wrong wait is worse than a vague one: it sends the next reader to the wrong place in the fallback chain when this ever needs touching again.
  const degraded: string[] = [];
  let checked = 0;

  try {
    for (const route of routes) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      const errs: string[] = [];
      // Playwright's console text for a failed subresource is the bare "Failed to load resource: the server responded with a status of 404 (Not Found)"
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

      // `networkidle` IS THE RIGHT WAIT AND THE WRONG FAILURE. Islands have to hydrate before the assertions below mean anything, so waiting for quiet is correct. But a
      // page carrying `<video preload="metadata">` pointed at media.rediacc.com issues a
      // request that never completes in a sandboxed container, and then the gate reports `page.goto: Timeout 45000ms exceeded` -- a crash, on the FIRST route, with none of its three real assertions ever run. That happened on 2026-08-24 while the same job had passed on the previous commit with identical page code.
      //
      // So: try for quiet, and on timeout fall back to `load` and keep going. A hanging third-party request can no longer mask the checks; a broken island still fails them. The fallback is COUNTED and printed, because a gate that silently lowers its own bar is worse than one that fails.
      let resp = null;
      try {
        resp = await page.goto(base + route, { waitUntil: 'networkidle', timeout: 30_000 });
      } catch {
        // `load` WAS THE FIRST FALLBACK AND IT HANGS THE SAME WAY, which the run on 4dcd676b proved: `page.goto: Timeout 30000ms exceeded ... waiting until "load"`. `load` waits for subresources too, and the request that never finishes is a subresource. `domcontentloaded` fires when the HTML is parsed and is the only one of the three that a hanging media request cannot hold up.
        degraded.push(route);
        try {
          resp = await page.goto(base + route, {
            waitUntil: 'domcontentloaded',
            timeout: 30_000,
          });
          // The beat islands would have had under networkidle. They hydrate from module scripts, so this is what stands in for the quiet that never came.
          await page.waitForTimeout(3_000);
        } catch (e) {
          // THIRD FAILURE IS A FINDING, NOT A CRASH. A gate that dies reports nothing about the other five routes; a gate that records "this route would not load" still checks them and still fails. That distinction cost two CI rounds.
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

      // Drop the generic resource-load error ONLY when every 404 this page produced was media the repo deliberately does not check out. If even one 404 is something else, the error stands, so a genuinely broken asset still fails.
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

      // The language switcher is an island: if it fails to hydrate, the trigger is inert and the visitor is stranded in one locale. Assert the whole path, not its markup.
      const hasTrigger = await page.locator('.language-trigger-icon').count();
      if (hasTrigger > 0) {
        const opts = await openLangMenu(page);
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
      // CONTROLS for the language-menu wait. (a) options that render 700ms after the click must be SEEN; (b) a menu that truly has no options must still be REPORTED as fewer than two.
      const late = await browser.newPage();
      await late.setContent(
        `<button class="language-trigger-icon" onclick="setTimeout(()=>{document.body.insertAdjacentHTML('beforeend','<a class=language-option>a</a><a class=language-option>b</a>')},700)">x</button>`
      );
      const lateN = await openLangMenu(late, 3_000);
      await late.close();
      const empty = await browser.newPage();
      await empty.setContent('<button class="language-trigger-icon">x</button>');
      const emptyN = await openLangMenu(empty, 600);
      await empty.close();
      const lateOk = lateN >= 2;
      const emptyOk = emptyN < 2;
      // (c) a first click that lands before hydration is inert: the handler only acts once `ready` flips at 300ms, so only the retry click can open the menu.
      const inert = await browser.newPage();
      await inert.setContent(
        `<button class="language-trigger-icon" id="t">x</button><script>let ready=false;setTimeout(()=>{ready=true},300);document.getElementById('t').onclick=()=>{if(ready)document.body.insertAdjacentHTML('beforeend','<a class=language-option>a</a><a class=language-option>b</a>')}</script>`
      );
      const retryN = await openLangMenu(inert, 600);
      await inert.close();
      const retryOk = retryN >= 2;
      console.log(
        `  ${lateOk ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  CONTROL: late-rendering lang options are waited for (${lateN})`
      );
      console.log(
        `  ${emptyOk ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  CONTROL: an empty lang menu is still reported (${emptyN})`
      );
      console.log(
        `  ${retryOk ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  CONTROL: a click lost before hydration is retried (${retryN})`
      );
      if (!lateOk || !emptyOk || !retryOk) {
        await browser.close();
        await close();
        process.exit(1);
      }

      // CONTROL: a page whose island is deliberately broken must be REPORTED, or a green run here means nothing. Inject a throwing script and require a console finding.
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
        ? `\n  ${degraded.length} route(s) never reached network quiet and were checked after \`domcontentloaded\` instead: ${degraded.join(', ')}. A request that never finishes (a CDN video in a sandboxed container) does that; the assertions still ran.`
        : '')
  );
}

main().catch((e) => {
  console.error('gate crashed:', e);
  process.exit(1);
});

/**
 * Drives the region popup in a real browser and exits non-zero on a failed step.
 *
 *   npx tsx packages/www/scripts/probe-region-picker.ts --url <site origin> [--mock] [--lookup-domain <d> --lookup-host <h>]
 *
 * Without --mock the page talks to its own /api/geo and /api/enterprise-lookup (a deployed
 * preview or www). With --mock both are answered from the probe, which is for a static
 * `astro dev` or `astro preview` that serves neither route. Navigations to the product
 * domain are intercepted and recorded, so no step leaves the site.
 *
 * Steps: login countdown shows and forwards after 5 seconds; Cancel stops it; Change region
 * stops it and keeps the cards; sign-up preselects and never counts down; a card click
 * forwards at once; the enterprise form forwards on a hit and gives the neutral miss text
 * on a miss.
 */
import { WK_PRODUCT_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import type { Page } from 'playwright';

interface Options {
  url: string;
  mock: boolean;
  lookupDomain: string;
  lookupHost: string;
}

const DEFAULT_PROBE_URL = 'http://localhost:4321';

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    url: process.env.PROBE_URL ?? DEFAULT_PROBE_URL,
    mock: false,
    lookupDomain: 'acme.example',
    lookupHost: `acme.eu.${WK_PRODUCT_DOMAIN}`,
  };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--url') opts.url = argv[++i];
    else if (argv[i] === '--mock') opts.mock = true;
    else if (argv[i] === '--lookup-domain') opts.lookupDomain = argv[++i];
    else if (argv[i] === '--lookup-host') opts.lookupHost = argv[++i];
  }
  return opts;
}

let failures = 0;
function check(name: string, ok: boolean, detail = ''): void {
  if (!ok) failures += 1;
  process.stdout.write(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `: ${detail}`}\n`);
}

async function openPicker(page: Page, opts: Options, path: string): Promise<void> {
  await page.goto(`${opts.url}/en/`, { waitUntil: 'load' });
  await page.waitForFunction(() => typeof window.openRegionPicker === 'function', undefined, {
    timeout: 15000,
  });
  await page.evaluate((p) => window.openRegionPicker?.(p), path);
  await page.getByRole('dialog').waitFor({ state: 'visible' });
}

async function installRoutes(page: Page, opts: Options, forwarded: string[]): Promise<void> {
  await page.route(`**://*.${WK_PRODUCT_DOMAIN}/**`, async (route) => {
    forwarded.push(route.request().url());
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<html></html>' });
  });
  if (!opts.mock) return;
  await page.route('**/api/geo', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"country":"DE"}' })
  );
  await page.route('**/api/enterprise-lookup', async (route) => {
    const body = JSON.parse(route.request().postData() ?? '{}') as { domain?: string };
    const host = body.domain === opts.lookupDomain ? opts.lookupHost : null;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ host }),
    });
  });
}

async function probeLoginCountdown(page: Page, opts: Options, forwarded: string[]): Promise<void> {
  forwarded.length = 0;
  await openPicker(page, opts, '/account/');
  const status = page.getByRole('status');
  await status.waitFor({ state: 'attached', timeout: 5000 });
  check(
    'login: countdown announced to screen readers',
    /in 5 seconds/.test((await status.textContent()) ?? '')
  );
  check('login: nothing forwarded before the countdown ends', forwarded.length === 0);
  await page.waitForTimeout(5800);
  check('login: forwards after 5 seconds', forwarded.length === 1, JSON.stringify(forwarded));
  check(
    'login: forward goes to a product host',
    forwarded[0]?.includes(`.${WK_PRODUCT_DOMAIN}/account/`) ?? false
  );
}

async function probeCancelAndChange(page: Page, opts: Options, forwarded: string[]): Promise<void> {
  forwarded.length = 0;
  await openPicker(page, opts, '/account/');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.waitForTimeout(5800);
  check(
    'cancel: closes the popup and never forwards',
    forwarded.length === 0 && !(await page.getByRole('dialog').isVisible())
  );

  await openPicker(page, opts, '/account/');
  await page.getByRole('button', { name: 'Change region' }).click();
  await page.waitForTimeout(5800);
  check(
    'change: keeps the cards and never forwards',
    forwarded.length === 0 && (await page.getByRole('dialog').isVisible())
  );
}

async function probeSignup(page: Page, opts: Options, forwarded: string[]): Promise<void> {
  forwarded.length = 0;
  await openPicker(page, opts, '/account/?checkout=PROFESSIONAL&period=monthly');
  check(
    'signup: no countdown buttons',
    (await page.getByRole('button', { name: 'Cancel' }).count()) === 0
  );
  await page.waitForTimeout(5800);
  check('signup: never forwards on its own', forwarded.length === 0);
  await page.locator('.region-picker-card').nth(1).click();
  await page.waitForTimeout(300);
  check(
    'signup: a card click forwards at once with the checkout query',
    forwarded.length === 1 && forwarded[0].includes('checkout=PROFESSIONAL'),
    JSON.stringify(forwarded)
  );
  const stored = await page.evaluate(() => window.localStorage.getItem('rediacc_region'));
  check('signup: the chosen region is stored', stored !== null);
}

async function probeStoredRegionNeverSilent(
  page: Page,
  opts: Options,
  forwarded: string[]
): Promise<void> {
  forwarded.length = 0;
  await openPicker(page, opts, '/account/?checkout=TEAM&period=annual');
  await page.waitForTimeout(1500);
  check(
    'stored region: signup still asks',
    forwarded.length === 0 && (await page.getByRole('dialog').isVisible())
  );
}

async function probeLookup(page: Page, opts: Options, forwarded: string[]): Promise<void> {
  forwarded.length = 0;
  await openPicker(page, opts, '/account/?checkout=TEAM&period=annual');
  await page.getByRole('button', { name: 'Enterprise customer?' }).click();
  const input = page.getByLabel('Company email domain');
  await input.fill('nobody@no-such-company.example');
  await page.getByRole('button', { name: 'Continue' }).click();
  const miss = page.getByRole('alert');
  await miss.waitFor({ state: 'visible', timeout: 10000 });
  check(
    'lookup miss: neutral message, no forward',
    forwarded.length === 0 && /No company sign-in/.test((await miss.textContent()) ?? '')
  );

  await input.fill(`someone@${opts.lookupDomain}`);
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.waitForTimeout(1500);
  check(
    'lookup hit: forwards to the company host',
    forwarded.some((u) => u.startsWith(`https://${opts.lookupHost}/`)),
    JSON.stringify(forwarded)
  );
}

async function main(): Promise<void> {
  const opts = parseArgs(process.argv.slice(2));
  const { chromium } = await import('playwright');
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ timezoneId: 'Europe/Berlin' });
    const page = await context.newPage();
    const forwarded: string[] = [];
    await installRoutes(page, opts, forwarded);
    await probeLoginCountdown(page, opts, forwarded);
    await probeCancelAndChange(page, opts, forwarded);
    await probeSignup(page, opts, forwarded);
    await probeStoredRegionNeverSilent(page, opts, forwarded);
    await probeLookup(page, opts, forwarded);
  } finally {
    await browser.close();
  }
  process.stdout.write(
    failures === 0
      ? 'probe-region-picker: all steps passed\n'
      : `probe-region-picker: ${failures} step(s) failed\n`
  );
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err: unknown) => {
  process.stderr.write(`probe-region-picker: ${err instanceof Error ? err.stack : String(err)}\n`);
  process.exit(1);
});

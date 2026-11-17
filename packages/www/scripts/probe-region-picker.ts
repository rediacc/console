/**
 * Drives the region popup in a real browser and exits non-zero on a failed step.
 *
 *   npx tsx packages/www/scripts/probe-region-picker.ts (--url <site origin> | <site origin>) [--mock] [--lookup-domain <d> --lookup-host <h>]
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
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { WK_PRODUCT_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import type { Page } from 'playwright';

export interface Options {
  url: string;
  mock: boolean;
  lookupDomain: string;
  lookupHost: string;
}

const DEFAULT_PROBE_URL = 'http://localhost:4321';

/** The label of the lookup field, as the popup renders it (en.json regionPicker.lookup.label). */
export const LOOKUP_LABEL = 'Work email';

/** The key the popup writes the chosen region under. */
export const REGION_STORAGE_KEY = 'rediacc_region';

export class UsageError extends Error {}

/** The usage line a refused argument prints under its reason. */
export const USAGE_LINE =
  'usage: probe-region-picker (--url <site origin> | <site origin>) [--mock] [--lookup-domain <d> --lookup-host <h>]';

/**
 * True when this module is the script being run. Both sides go through realpath, so a symlinked
 * path to the script still runs `main()`: a string compare would exit 0 with no step executed.
 */
export function isEntryPoint(argv1: string | undefined, moduleUrl: string): boolean {
  if (!argv1) return false;
  // The script's own path must resolve: if it cannot, main() would never run and the process would exit 0 with no step executed.
  const self = realpathSync(fileURLToPath(moduleUrl));
  try {
    return realpathSync(argv1) === self;
  } catch {
    return false;
  }
}

const VALUE_FLAGS = ['--url', '--lookup-domain', '--lookup-host'] as const;

/** A bare host (`pr-1.rediacc.workers.dev`) is an https origin; anything with a scheme is kept. */
function originOf(raw: string): string {
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`;
  return withScheme.replace(/\/+$/, '');
}

export function parseArgs(argv: string[], env: NodeJS.ProcessEnv = process.env): Options {
  const opts: Options = {
    url: env.PROBE_URL ?? DEFAULT_PROBE_URL,
    mock: false,
    lookupDomain: 'acme.example',
    lookupHost: `acme.eu.${WK_PRODUCT_DOMAIN}`,
  };
  let positional: string | undefined;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--mock') {
      opts.mock = true;
    } else if ((VALUE_FLAGS as readonly string[]).includes(arg)) {
      const value = argv[++i];
      if (value === undefined || value.startsWith('--'))
        throw new UsageError(`${arg} needs a value`);
      if (arg === '--url') opts.url = originOf(value);
      else if (arg === '--lookup-domain') opts.lookupDomain = value;
      else opts.lookupHost = value;
    } else if (arg.startsWith('--')) {
      throw new UsageError(`unknown argument ${arg}`);
    } else if (positional === undefined) {
      positional = arg;
    } else {
      throw new UsageError(`unexpected extra argument ${arg}`);
    }
  }
  if (positional !== undefined) {
    if (argv.includes('--url')) throw new UsageError('give the origin once: --url or positional');
    opts.url = originOf(positional);
  }
  return opts;
}

/**
 * The in-page spy, as a plain string so no transpiler helper can leak into the page: it reports
 * every localStorage write to the probe through `window.probeReportStored`. A card click
 * forwards to the product host, so the page that comes next is another origin and its
 * localStorage no longer holds the key: the write is read as it happens instead.
 */
export const STORAGE_SPY_SOURCE = `(() => {
  const original = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key, value) {
    window.probeReportStored(String(key), String(value));
    return original.call(this, key, value);
  };
})();`;

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

async function installRoutes(
  page: Page,
  opts: Options,
  forwarded: string[],
  stored: Map<string, string>
): Promise<void> {
  await page.exposeFunction('probeReportStored', (key: string, value: string) => {
    stored.set(key, value);
  });
  await page.addInitScript(STORAGE_SPY_SOURCE);
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

async function probeSignup(
  page: Page,
  opts: Options,
  forwarded: string[],
  stored: Map<string, string>
): Promise<void> {
  forwarded.length = 0;
  stored.clear();
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
  check('signup: the chosen region is stored', stored.has(REGION_STORAGE_KEY));
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
  const input = page.getByLabel(LOOKUP_LABEL);
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
    const stored = new Map<string, string>();
    await installRoutes(page, opts, forwarded, stored);
    await probeLoginCountdown(page, opts, forwarded);
    await probeCancelAndChange(page, opts, forwarded);
    await probeSignup(page, opts, forwarded, stored);
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

if (isEntryPoint(process.argv[1], import.meta.url)) {
  main().catch((err: unknown) => {
    if (err instanceof UsageError) {
      process.stderr.write(`probe-region-picker: ${err.message}\n${USAGE_LINE}\n`);
      process.exit(2);
    }
    process.stderr.write(
      `probe-region-picker: ${err instanceof Error ? err.stack : String(err)}\n`
    );
    process.exit(1);
  });
}

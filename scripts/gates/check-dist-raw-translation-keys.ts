#!/usr/bin/env tsx
/**
 * No BUILT www page may show a reader a raw translation key.
 *
 * WHY THIS EXISTS. https://www.rediacc.com/en/pricing rendered the literal text
 * `pages.pricing.plans.free.name` and `pages.pricing.plans.free.description` in all 13
 * locales (2026-11-17). `CfPricingCard.astro` builds `t(`pages.pricing.plans.${plan.id}.name`)`,
 * the shared PLAN_ORDER gained FREE, and `t()` answers a miss by returning the key. Every
 * i18n gate stayed green, because every one of them reads SOURCE: key-usage skips a
 * template key with a `${...}` in it, dead-keys and completeness compare catalogs to
 * catalogs. The build printed "Translation key not found" 39 times and exited 0.
 *
 * So the subject here is the OUTPUT, `packages/www/dist/**\/*.html`, which is what a reader
 * and a crawler see, whatever path the key took to get there (a template key, a prop, a
 * helper, a docs `{{t:...}}` placeholder that did not resolve).
 *
 * WHAT COUNTS AS A RAW KEY. A dotted token of three or more segments whose first two
 * segments name a BRANCH of en.json (`pages.pricing`, `common.buttons`), and whose full
 * path is NOT itself a branch. That last clause is what keeps a namespace string serialized
 * into an island's props (`pages.partners.form`) from reading as a leak, while a leaf
 * (`common.buttons.getStarted`, a key rendered instead of its value) and an unresolved path
 * under a real branch (`pages.pricing.plans.free.name`) both fire. A hostname such as
 * `docs.rediacc.com` never fires, since `docs` is not a top-level branch.
 *
 * WHAT IS NOT SCANNED. The bodies of executable `<script>` and `<style>` elements, where a
 * key-shaped token is code, not copy. `application/ld+json` IS scanned: the pricing leak
 * reached the Offer structured data too, and a crawler reads that block.
 *
 * Usage:
 *   npx tsx scripts/gates/check-dist-raw-translation-keys.ts [--selftest]
 *
 * ---- gate ----
 * step: Raw translation keys
 * needs: node
 * selftest: true
 * lane: quality-www-build
 * slow: true
 * ---- end gate ----
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { globSync } from 'glob';
import { GREEN, NC, RED } from '../lib/console.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { type ControlCase, summarizeControls } from '../lib/controls.js';
import { refuseFindings } from '../lib/findings-report.js';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
// THE SEAM, driven by controls() below (distControls): RAW_KEYS_DIST points the scan at a
// scratch dist so a planted leak never touches the real build output.
const DIST = process.env.RAW_KEYS_DIST ?? path.join(ROOT, 'packages/www/dist');
// VACUITY FLOOR. Every one of the 13 locales builds at least its own home page, so a dist holding fewer html pages than that is a build that lost locales, not a small site. A lower bound, not a measurement: the real dist holds far more.
const MIN_PAGES = 13;
const EN_JSON = path.join(ROOT, 'packages/www/src/i18n/translations/en.json');

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

function isBranch(v: Json | undefined): boolean {
  return typeof v === 'object' && v !== null;
}

function resolve(catalog: Json, dotted: string): Json | undefined {
  let cur: Json | undefined = catalog;
  for (const seg of dotted.split('.')) {
    if (!isBranch(cur)) return undefined;
    cur = (cur as Record<string, Json>)[seg];
  }
  return cur;
}

/** Blank executable script and style bodies; keep JSON-LD, which a crawler reads as copy. */
export function stripCode(html: string): string {
  return html
    .replace(/<script\b([^>]*)>[\s\S]*?<\/script>/gi, (whole, attrs: string) =>
      /type\s*=\s*["']?application\/ld\+json/i.test(attrs) ? whole : ''
    )
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '');
}

const TOKEN = /(?<![\w.\-/])[a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9_]+){2,}(?![\w\-/]|\.[A-Za-z0-9_])/g;
const DOCS_PLACEHOLDER = /\{\{t:[a-zA-Z]+\.[a-zA-Z0-9_.]+\}\}/g;

/** Every raw key in one page's html, deduplicated, in first-seen order. */
export function rawKeysIn(html: string, en: Json): string[] {
  const text = stripCode(html);
  const found = new Set<string>();
  for (const m of text.matchAll(TOKEN)) {
    const token = m[0];
    const segs = token.split('.');
    if (!isBranch(resolve(en, segs.slice(0, 2).join('.')))) continue;
    if (isBranch(resolve(en, token))) continue;
    found.add(token);
  }
  for (const m of text.matchAll(DOCS_PLACEHOLDER)) found.add(m[0]);
  return [...found];
}

function controls(): ControlCase[] {
  const en: Json = {
    pages: { pricing: { plans: { pro: { name: 'Pro' } } }, partners: { form: { a: 'A' } } },
    common: { buttons: { getStarted: 'Get started' } },
  };
  const keys = (html: string) => rawKeysIn(html, en).join(',');
  const cases: [string, string, string][] = [
    // [name, html, expected findings]
    [
      'CONTROL: an unresolved key under a real branch fires (the 2026-11-17 leak)',
      '<h3 class="cf-plan-name">pages.pricing.plans.free.name</h3>',
      'pages.pricing.plans.free.name',
    ],
    [
      'CONTROL: a leaf key rendered instead of its value fires',
      '<a>common.buttons.getStarted</a>',
      'common.buttons.getStarted',
    ],
    [
      'CONTROL: a leak inside JSON-LD fires, since a crawler reads it',
      '<script type="application/ld+json">{"name":"pages.pricing.plans.free.name"}</script>',
      'pages.pricing.plans.free.name',
    ],
    [
      'CONTROL: an unresolved docs placeholder fires',
      '<p>{{t:cli.docs.sectionTitles.backup}}</p>',
      '{{t:cli.docs.sectionTitles.backup}}',
    ],
    ['SILENT: a correct page has no finding', '<h3>Pro</h3><a>Get started</a>', ''],
    [
      'SILENT: a namespace string in island props is a branch, not a leak',
      '<astro-island props="{&quot;ns&quot;:[0,&quot;pages.partners.form&quot;]}"></astro-island>',
      '',
    ],
    [
      'SILENT: a hostname under no top-level branch is not a key',
      '<a href="https://docs.rediacc.com/x">docs.rediacc.com</a>',
      '',
    ],
    [
      'SILENT: a key-shaped token inside an executable script is code',
      '<script>const k = "pages.pricing.plans.free.name";</script>',
      '',
    ],
    ['SILENT: a two-segment token is never a key leak', '<p>pages.pricing</p>', ''],
  ];
  return cases.map(([name, html, want]) => {
    const got = keys(html);
    return {
      name,
      ok: got === want,
      detail: `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`,
    };
  });
}

/**
 * The mutation run: the real gate, as a process, over a scratch dist. A leak planted there
 * must exit 1 naming the key; a clean page must exit 0. Skipped when RAW_KEYS_DIST is
 * already set, which is the child's own run (it would otherwise spawn itself forever).
 */
function distControls(): ControlCase[] {
  if (process.env.RAW_KEYS_DIST !== undefined) return [];
  const run = (html: string, pages: number = MIN_PAGES) => {
    const dir = mkdtempSync(path.join(os.tmpdir(), 'raw-keys-dist-'));
    try {
      mkdirSync(path.join(dir, 'en'), { recursive: true });
      writeFileSync(path.join(dir, 'en', 'index.html'), html);
      // Filler pages bring the scratch dist up to `pages`, so the control exercises the leak verdict and not the vacuity floor.
      for (let i = 1; i < pages; i++)
        writeFileSync(path.join(dir, 'en', `filler-${i}.html`), '<p>Professional</p>');
      return spawnSync('npx', ['tsx', import.meta.filename], {
        encoding: 'utf8',
        env: { ...process.env, RAW_KEYS_DIST: dir },
      });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  };
  const leak = 'pages.pricing.plans.zzzControl.name';
  const bad = run(`<h3>${leak}</h3>`);
  const good = run('<h3>Professional</h3>');
  const thin = run('<h3>Professional</h3>', MIN_PAGES - 1);
  return [
    {
      name: 'CONTROL: the gate process exits 1 and names a leak planted in a scratch dist',
      ok: bad.status === 1 && `${bad.stdout}${bad.stderr}`.includes(leak),
      detail: `status ${bad.status}`,
    },
    {
      name: 'SILENT: the gate process exits 0 on a clean scratch dist',
      ok: good.status === 0,
      detail: `status ${good.status}`,
    },
    {
      name: 'CONTROL: a scratch dist one page under the floor exits 1 and says VACUOUS',
      ok: thin.status === 1 && `${thin.stdout}${thin.stderr}`.includes('VACUOUS'),
      detail: `status ${thin.status}`,
    },
  ];
}

function main(): void {
  const selftestOnly = process.argv.includes('--selftest');
  console.log('raw-translation-keys gate controls');
  const rc = summarizeControls([...controls(), ...distControls()]);
  if (rc !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }
  if (selftestOnly) process.exit(0);

  if (!existsSync(DIST)) {
    console.error(
      `${RED}✗${NC} ${path.relative(ROOT, DIST)} does not exist. Build first: npm run build:www`
    );
    process.exit(1);
  }
  const en = JSON.parse(readFileSync(EN_JSON, 'utf8')) as Json;
  const pages = globSync('**/*.html', { cwd: DIST, absolute: true });
  if (pages.length < MIN_PAGES) {
    console.error(
      `${RED}✗${NC} VACUOUS: ${pages.length} html page(s) under ${path.relative(ROOT, DIST)}, floor ${MIN_PAGES}; the gate verified nothing.`
    );
    process.exit(1);
  }

  const findings: string[] = [];
  for (const page of [...pages].sort((a, b) => a.localeCompare(b))) {
    for (const key of rawKeysIn(readFileSync(page, 'utf8'), en)) {
      findings.push(`${path.relative(DIST, page)}: ${key}`);
    }
  }
  if (findings.length > 0) {
    refuseFindings({
      header: `\n${RED}✗${NC} ${findings.length} raw translation key(s) rendered in built pages:\n`,
      items: findings,
      limit: 40,
      remedy: [
        '\nEach is a key t() could not resolve, shown to the reader in place of copy. Add the',
        'key to packages/www/src/i18n/translations/en.json and the 12 locales, or stop asking',
        'for it (a dynamic `${...}` key whose varying part gained a value nobody translated).',
      ],
    });
  }
  console.log(`${GREEN}✓${NC} ${pages.length} built page(s): no raw translation key rendered.`);
}

if (isEntryPoint(import.meta.filename)) main();

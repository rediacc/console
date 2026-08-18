#!/usr/bin/env tsx
/**
 * How much JavaScript the homepage makes a visitor download and parse.
 *
 * THE NUMBER TODAY: 7,043,755 decoded bytes, of which `assets/react.*.js` alone is
 * 6,708,716. That single chunk exists because `packages/www/src/i18n/utils.ts` STATICALLY
 * imports all thirteen locale catalogs, so every visitor in every language receives all
 * thirteen. For comparison, measured the same way on the same day: claude.com ships
 * 1,267,131 B and anthropic.com 305,858 B.
 *
 * THE BUDGET IS 500,000 B AND IT IS DELIBERATELY SET WHERE THE FIX LANDS, not where the
 * site is. This gate is RED on purpose until Wave 1 chunks the locales, and it is red by a
 * factor of fourteen, which is the honest description of the gap. A budget set just above
 * today's figure would be a gate that ratifies the defect.
 *
 * IT WALKS THE IMPORT GRAPH, WHICH IS THE ONLY WAY THE FIGURE IS TRUE. The homepage's own
 * HTML references six small scripts totalling about 41 kB and not one byte of React. The
 * 6.7 MB arrives transitively: an `<astro-island component-url="/assets/Navigation.*.js">`
 * imports a chunk, which imports the React chunk. Summing the `<script src>` tags would
 * report 41 kB and pass a 500 kB budget while the page shipped seven megabytes -- a green
 * gate over the exact defect it was written for.
 *
 * EVERY LOCALE IS BUDGETED, not just English. The locale set comes from `@rediacc/locales`,
 * and a homepage missing for a declared locale is a hard error rather than a locale that
 * quietly scores zero.
 *
 * Usage:
 *   tsx scripts/check-client-bundle-budget.ts [--dist <dir>] [--budget <bytes>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { SITE_LOCALES } from '@rediacc/locales';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_DIST = 'packages/www/dist';

/**
 * The scorecard target for this program: homepage decoded JavaScript under 500,000 B.
 * Wave 1 (locale chunking) is what brings the figure under it.
 */
const DEFAULT_BUDGET = 500_000;

/** A homepage that pulls in less than this is not a lean page, it is an unresolved graph. */
const MIN_BYTES = 5_000;

export interface BundleMeasurement {
  page: string;
  bytes: number;
  files: { url: string; bytes: number }[];
  missing: string[];
}

/** Static and dynamic import specifiers of a built ES module or an inline module script. */
function importSpecifiers(source: string): string[] {
  const out: string[] = [];
  for (const m of source.matchAll(/\bfrom\s*["']([^"']+)["']/g)) out.push(m[1]);
  for (const m of source.matchAll(/\bimport\s*\(\s*["']([^"']+)["']/g)) out.push(m[1]);
  for (const m of source.matchAll(/\bimport\s+["']([^"']+)["']/g)) out.push(m[1]);
  return out;
}

/** Resolve a specifier seen inside `fromUrl` to a site-absolute URL, or null if external. */
function resolveSpecifier(spec: string, fromUrl: string): string | null {
  if (spec.startsWith('/')) return spec;
  if (spec.startsWith('./') || spec.startsWith('../')) {
    return `/${path.posix.normalize(path.posix.join(path.posix.dirname(fromUrl.slice(1)), spec))}`;
  }
  // A bare specifier or an absolute URL: not served from this build.
  return null;
}

export function measurePage(dist: string, pageRel: string): BundleMeasurement {
  const html = fs.readFileSync(path.join(dist, pageRel), 'utf-8');
  const entries = new Set<string>();

  // THREE ENTRY SHAPES, and the last two are where the weight is.
  //   `src="..."`            classic scripts
  //   `component-url="..."`  the island's component chunk
  //   `renderer-url="..."`   the client renderer (React) the island boots with
  for (const m of html.matchAll(/(?:src|component-url|renderer-url)\s*=\s*"([^"]+\.m?js)"/g)) {
    if (m[1].startsWith('/')) entries.add(m[1]);
  }
  // Inline module scripts import their chunks by URL.
  for (const m of html.matchAll(/<script[^>]*type="module"[^>]*>([\s\S]*?)<\/script>/g)) {
    for (const spec of importSpecifiers(m[1])) {
      if (spec.startsWith('/')) entries.add(spec);
    }
  }

  const seen = new Set<string>();
  const missing: string[] = [];
  const files: { url: string; bytes: number }[] = [];
  const stack = [...entries];

  while (stack.length > 0) {
    const url = stack.pop()!;
    if (seen.has(url)) continue;
    seen.add(url);
    const abs = path.join(dist, url.replace(/^\//, ''));
    if (!fs.existsSync(abs)) {
      missing.push(url);
      continue;
    }
    const bytes = fs.statSync(abs).size;
    files.push({ url, bytes });
    for (const spec of importSpecifiers(fs.readFileSync(abs, 'utf-8'))) {
      const resolved = resolveSpecifier(spec, url);
      if (resolved) stack.push(resolved);
    }
  }

  return {
    page: pageRel,
    bytes: files.reduce((a, f) => a + f.bytes, 0),
    files: files.sort((a, b) => b.bytes - a.bytes),
    missing,
  };
}

function selftest(): boolean {
  const failures: string[] = [];
  const check = (name: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}${detail ? `\n        ${detail}` : ''}`);
      failures.push(name);
    }
  };

  const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'bundle-budget-'));
  fs.mkdirSync(path.join(dist, 'assets'), { recursive: true });
  fs.mkdirSync(path.join(dist, 'en'), { recursive: true });

  const write = (rel: string, body: string) => fs.writeFileSync(path.join(dist, rel), body);
  // A leaf chunk that is ONLY reachable transitively, and is by far the largest thing on
  // the page. This is the fixture's whole point: it stands in for react.*.js, which no
  // <script src> on the real homepage names.
  write('assets/heavy.js', `export const x = "${'x'.repeat(50_000)}";`);
  write('assets/mid.js', 'import { x } from "./heavy.js";\nexport const y = x;');
  write('assets/island.js', 'import { y } from "./mid.js";\nexport default () => y;');
  write('assets/client.js', 'export const boot = 1;');
  fs.mkdirSync(path.join(dist, 'scripts'), { recursive: true });
  write('scripts/small.js', 'console.log(1);');
  write(
    'en/index.html',
    `<html><body>
      <script src="/scripts/small.js"></script>
      <astro-island component-url="/assets/island.js" renderer-url="/assets/client.js"></astro-island>
      <script type="module">import "/assets/client.js";</script>
    </body></html>`
  );

  const m = measurePage(dist, 'en/index.html');
  const heavy = m.files.find((f) => f.url === '/assets/heavy.js');
  check(
    'PLANT: a chunk reachable ONLY through two levels of import is counted',
    Boolean(heavy),
    JSON.stringify(m.files.map((f) => f.url))
  );
  check(
    'the total is the sum of the whole graph, not of the <script src> tags',
    m.bytes > 50_000,
    String(m.bytes)
  );
  check(
    'an island component-url is an entry point',
    m.files.some((f) => f.url === '/assets/island.js')
  );
  check(
    'a renderer-url is an entry point',
    m.files.some((f) => f.url === '/assets/client.js')
  );
  check(
    'a classic script tag is an entry point',
    m.files.some((f) => f.url === '/scripts/small.js')
  );
  check('nothing is double counted', new Set(m.files.map((f) => f.url)).size === m.files.length);
  check('nothing resolved is reported missing', m.missing.length === 0, JSON.stringify(m.missing));

  // The measured figure must sit strictly between the two budgets the real gate could be
  // given, so the `bytes > budget` comparison in main() has a true and a false case on
  // this very fixture rather than only on the repo's build.
  check(
    'the fixture measures ABOVE a tight budget (the fire case)',
    m.bytes > 40_000,
    String(m.bytes)
  );
  check(
    'the fixture measures BELOW a loose budget (the pass case)',
    m.bytes < 10_000_000,
    String(m.bytes)
  );

  // An external script must not be counted or reported as missing.
  write(
    'en/external.html',
    '<html><body><script src="https://plausible.example.com/js/p.js"></script></body></html>'
  );
  const ext = measurePage(dist, 'en/external.html');
  check(
    'a third-party script is neither counted nor reported missing (control)',
    ext.bytes === 0 && ext.missing.length === 0,
    JSON.stringify(ext)
  );

  // A referenced chunk that does not exist must be LOUD, not silently zero.
  write('en/broken.html', '<html><body><script src="/assets/gone.js"></script></body></html>');
  check(
    'a referenced chunk that is absent is reported, not counted as zero',
    measurePage(dist, 'en/broken.html').missing.includes('/assets/gone.js')
  );

  fs.rmSync(dist, { recursive: true, force: true });
  if (failures.length > 0) {
    console.error(`\n✗ ${failures.length} self-test failure(s)`);
    return false;
  }
  return true;
}

function main(): void {
  const argv = process.argv.slice(2);
  const arg = (name: string): string | undefined => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };

  if (argv.includes('--selftest')) process.exit(selftest() ? 0 : 1);
  if (!argv.includes('--skip-control') && !selftest()) process.exit(1);

  const dist = path.resolve(arg('--dist') ?? path.join(REPO_ROOT, DEFAULT_DIST));
  const budget = Number(arg('--budget') ?? DEFAULT_BUDGET);

  if (!fs.existsSync(dist)) {
    console.error(
      `✗ Refusing to run: no build output at ${dist}. Run \`npm run build:www\` first.\n` +
        `  An absent build weighs nothing, which is not the same as a light page.`
    );
    process.exit(1);
  }

  // The locale universe is @rediacc/locales. A homepage missing for a declared locale is a
  // hard error: scoring zero for a locale nobody built reads exactly like scoring well.
  const pages = SITE_LOCALES.map((l) => ({ locale: l, rel: path.join(l, 'index.html') }));
  const absent = pages.filter((p) => !fs.existsSync(path.join(dist, p.rel)));
  if (absent.length > 0) {
    console.error(
      `✗ Refusing to run: ${absent.length} declared locale(s) have no homepage in the build: ` +
        `${absent.map((a) => a.locale).join(', ')}.`
    );
    process.exit(1);
  }

  const measured = pages.map((p) => ({ locale: p.locale, ...measurePage(dist, p.rel) }));

  const starved = measured.filter((m) => m.bytes < MIN_BYTES);
  if (starved.length > 0) {
    console.error(
      `✗ Refusing to run: ${starved.length} homepage(s) resolved to under ${MIN_BYTES} bytes of ` +
        `JavaScript (${starved.map((s) => `${s.locale}=${s.bytes}`).join(', ')}).\n` +
        `  The import graph did not resolve; a near-zero figure is a broken measurement, not ` +
        `a lean page.`
    );
    process.exit(1);
  }

  const missing = measured.flatMap((m) => m.missing.map((u) => `${m.locale}: ${u}`));
  const over = measured.filter((m) => m.bytes > budget);

  if (over.length === 0 && missing.length === 0) {
    const worst = measured.reduce((a, b) => (a.bytes > b.bytes ? a : b));
    console.log(
      `✓ Every locale homepage is within the ${budget.toLocaleString()} B budget ` +
        `(worst: ${worst.locale} at ${worst.bytes.toLocaleString()} B across ${worst.files.length} file(s)).`
    );
    return;
  }

  if (missing.length > 0) {
    console.error(`✗ ${missing.length} referenced chunk(s) do not exist in the build:`);
    for (const m of missing.slice(0, 10)) console.error(`    ${m}`);
    console.error('');
  }

  if (over.length > 0) {
    console.error(
      `✗ ${over.length} of ${measured.length} locale homepage(s) exceed the ` +
        `${budget.toLocaleString()} B decoded-JavaScript budget:\n`
    );
    for (const m of over.sort((a, b) => b.bytes - a.bytes)) {
      console.error(
        `  /${m.locale}/  ${m.bytes.toLocaleString()} B  ` +
          `(${(m.bytes / budget).toFixed(1)}x budget, ${m.files.length} file(s))`
      );
    }
    const worst = over.reduce((a, b) => (a.bytes > b.bytes ? a : b));
    console.error(`\n  Largest chunks on /${worst.locale}/:`);
    for (const f of worst.files.slice(0, 5)) {
      console.error(`    ${f.bytes.toLocaleString()} B  ${f.url}`);
    }
    console.error(
      `\npackages/www/src/i18n/utils.ts imports all thirteen locale catalogs STATICALLY, so\n` +
        `every visitor downloads every language. Chunk them per locale and this figure drops\n` +
        `by roughly the twelve catalogs nobody on the page can read.`
    );
  }
  process.exit(1);
}

main();

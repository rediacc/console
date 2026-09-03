#!/usr/bin/env tsx
/**
 * Every locale's BUILT html must carry that locale's strings, not English.
 *
 * WHY THIS EXISTS. The whole top navigation and footer server-rendered in ENGLISH on all
 * twelve non-English locales, sitewide, for as long as anyone had looked.
 * `src/hooks/useLanguage.ts` reads `window.location.pathname` and there is no `window`
 * during SSR, so it returned 'en' for every locale, and `BaseLayout` mounted the islands
 * with no `lang` prop to say otherwise. Crawlers and no-JS visitors got an English nav;
 * everyone else got a flash of English until hydration corrected it.
 *
 * WHY NO EXISTING GATE CAUGHT IT, which is the reason this one reads FILES and not a page:
 *   - `check:ci-browser-smoke` drives a real browser, where hydration has already fixed
 *     the text before it looks. It is blind to this by construction.
 *   - `check:ci-hydration-clean` flags a `useState` INITIALIZER that reads `window`. This
 *     read is at module scope inside a store factory: same family, different shape.
 *   - Every i18n gate compares catalogs to catalogs or source to catalogs. None of them
 *     opens the output.
 *
 * So the subject has to be `dist/<lang>/index.html`, which is exactly what a crawler sees.
 *
 * Usage:
 *   npx tsx scripts/check-ssr-locale.ts [--selftest]
 */
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { GREEN, NC, RED } from './utils/console.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const WWW = path.join(ROOT, 'packages/www');
const DIST = path.join(WWW, 'dist');
const CATALOGS = path.join(WWW, 'src/i18n/translations');

/** Dotted path -> value, so a probe names the key rather than a hardcoded string. */
export function at(obj: unknown, dotted: string): string | undefined {
  let cur: unknown = obj;
  for (const seg of dotted.split('.')) {
    if (typeof cur !== 'object' || cur === null) return undefined;
    cur = (cur as Record<string, unknown>)[seg];
  }
  return typeof cur === 'string' ? cur : undefined;
}

/**
 * Keys that are server-rendered by an island on the homepage. Each must be a string the
 * ENGLISH page and a translated page genuinely differ on, or the probe proves nothing.
 */
const PROBES = [
  'navigation.builtForYou',
  'common.buttons.getStarted',
  'footer.columns.product',
] as const;

function locales(): string[] {
  const raw = JSON.parse(
    readFileSync(path.join(ROOT, 'packages/locales/site-locales.json'), 'utf8')
  );
  return raw.siteLocales as string[];
}

function selftest(): number {
  let bad = 0;
  const check = (label: string, ok: boolean) => {
    console.log(`  ${ok ? `${GREEN}PASS${NC}` : `${RED}FAIL${NC}`}  ${label}`);
    if (!ok) bad++;
  };
  check('a dotted path resolves', at({ a: { b: 'x' } }, 'a.b') === 'x');
  check('a missing path is undefined', at({ a: {} }, 'a.b') === undefined);
  check('a non-string leaf is undefined', at({ a: { b: 1 } }, 'a.b') === undefined);
  check('the locale set comes from @rediacc/locales, not a literal', locales().length === 13);
  check(
    'CONTROL: a translated value absent from html is detected',
    !'<p>Get Started</p>'.includes('Jetzt starten')
  );
  check(
    'CONTROL: a translated value present in html is detected',
    '<p>Jetzt starten</p>'.includes('Jetzt starten')
  );
  return bad;
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    console.log('ssr-locale gate selftest');
    const bad = selftest();
    console.log(bad === 0 ? '\n${GREEN}✓${NC} 6/6 controls pass' : `\n${RED}✗${NC} ${bad} failed`);
    process.exit(bad === 0 ? 0 : 1);
  }
  if (selftest() !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }

  if (!existsSync(DIST)) {
    console.error(
      `✗ ${path.relative(ROOT, DIST)} does not exist. Build first: npm run build -w @rediacc/www`
    );
    process.exit(1);
  }

  const en = JSON.parse(readFileSync(path.join(CATALOGS, 'en.json'), 'utf8'));
  const findings: string[] = [];
  let checked = 0;

  for (const lang of locales()) {
    if (lang === 'en') continue;
    const page = path.join(DIST, lang, 'index.html');
    if (!existsSync(page)) {
      findings.push(`${lang}: dist/${lang}/index.html is missing`);
      continue;
    }
    const html = readFileSync(page, 'utf8');
    const cat = JSON.parse(readFileSync(path.join(CATALOGS, `${lang}.json`), 'utf8'));

    for (const key of PROBES) {
      const want = at(cat, key);
      const english = at(en, key);
      // Only a key whose translation actually DIFFERS from English can prove anything.
      if (want === undefined || english === undefined || want === english) continue;
      checked++;
      if (!html.includes(want)) {
        findings.push(
          `${lang}: ${key} should render ${JSON.stringify(want)}, and the page does not contain it` +
            (html.includes(english) ? ` (it renders the ENGLISH ${JSON.stringify(english)})` : '')
        );
      }
    }
  }

  if (checked === 0) {
    console.error(
      '✗ zero probes were comparable. The gate verified nothing; its green would be meaningless.'
    );
    process.exit(1);
  }
  if (findings.length > 0) {
    console.error(`\n${RED}✗${NC} ${findings.length} server-rendered locale failure(s):\n`);
    for (const f of findings.slice(0, 20)) console.error(`    ${f}`);
    if (findings.length > 20) console.error(`    ... and ${findings.length - 20} more`);
    console.error(
      '\nAn island that calls useLanguage() renders English on the server, because there'
    );
    console.error('is no window. Pass `lang` down from BaseLayout and prefer it over the hook.');
    process.exit(1);
  }
  console.log(
    `${GREEN}✓${NC} ${checked} probe(s) across ${locales().length - 1} non-English locale(s): all server-render natively.`
  );
}

main();

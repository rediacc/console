#!/usr/bin/env node
/**
 * Generates `packages/www/src/i18n/client/<locale>.json` for every site locale.
 *
 * WHY THIS EXISTS
 *
 * `src/i18n/utils.ts` statically imports all thirteen locale catalogs (9.28 MB on disk).
 * Until 2026-08 `src/i18n/react.ts` reached that module, so `useTranslation` in eighteen
 * hydrated islands dragged every catalog into the shared React vendor chunk that BaseLayout
 * loads on every route: 6,708,716 bytes of one asset, 89.5% of the homepage's shipped
 * JavaScript, with Korean, Arabic, Russian and Japanese marketing copy downloaded to read
 * the English homepage.
 *
 * The islands do not need it. Sixteen of the eighteen reach at most 40 leaves each. Two,
 * MegaMenu and Sidebar, used to call `to(\`pages.solutionPages.${contentKey}\`)` and read a
 * single field off the result, which pulled 6,660 leaves apiece. Those two now ask for
 * `...hero.title` directly, and what the client genuinely needs is the allowlist below:
 * about 316 leaves, roughly 14 KB for `en` and 224 KB for all thirteen.
 *
 * OUTPUT IS COMMITTED, ON PURPOSE. A generated artifact nobody can diff is how the search
 * index went stale. `check-client-i18n-freshness.ts` fails the build on drift.
 *
 * Run: `npm run i18n:generate-client -w @rediacc/www`
 */

import { SITE_LOCALES, type SiteLocale } from '@rediacc/locales';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const wwwRoot = path.resolve(scriptDir, '..');
const translationsDir = path.join(wwwRoot, 'src', 'i18n', 'translations');
const srcDir = path.join(wwwRoot, 'src');

/**
 * Two bundles, because a string that only one route needs must not ride the chunk every
 * route loads.
 *
 *   client        reached from `useTranslation`      (src/i18n/react.ts)
 *   client-route  reached from `useRouteTranslation` (src/i18n/react-route.ts)
 *
 * The hook an island calls decides which bundle it is checked against, so the split is read
 * off the source rather than maintained by hand.
 */
const BUNDLES = {
  client: { hook: 'useTranslation', dir: path.join(wwwRoot, 'src', 'i18n', 'client') },
  'client-route': {
    hook: 'useRouteTranslation',
    dir: path.join(wwwRoot, 'src', 'i18n', 'client-route'),
  },
} as const;

type BundleName = keyof typeof BUNDLES;

/**
 * The keys shipped to the browser, per bundle.
 *
 * A `*` matches exactly one path segment. Everything under a listed path comes along, so
 * `contactModal` brings its whole subtree.
 *
 * DERIVED FROM the `.tsx` files that call a translation hook, and CHECKED against them
 * below: every statically resolvable `t()` / `ta()` / `to()` key in an island must land
 * inside ITS bundle's allowlist, or generation fails. Adding an island key without adding
 * it here is a build failure, not a page that renders "navigation.somethingNew" in
 * production. Using an every-route key from a route-scoped island fails the same way.
 *
 * The dynamic call sites cannot be resolved statically. Each one's literal prefix is listed
 * here and smoke-checked below:
 *   client
 *     contactModal.subjects.${s}                       ContactModal, ContactForm
 *     navigation.${titleKey}                           PersonaMegaMenu
 *     pages.solutionPages.${contentKey}.hero.title     MegaMenu, Sidebar
 *   client-route
 *     hero.install.tabs.${key}                         InstallMethods, DownloadsList
 *     pages.downloads.architectures.${file.arch}       DownloadsList
 *     pages.downloads.platforms.${activePlatform}      DownloadsList
 *     pages.install.methods.${method.id}.title         InstallMethods
 *     pages.partners.form.howHeardOptions.${option}    PartnerApplicationForm
 *     pages.partners.form.partnerTypeOptions.${type}   PartnerApplicationForm
 */
const CLIENT_KEY_PATHS: Record<BundleName, readonly string[]> = {
  client: [
    'captchaRequired',
    'common',
    'contactModal',
    // LearnMenu renders the six docs categories by their translated LABEL while
    // routing on the English identifier. It is a client island, so without this
    // the panel shipped "documentation.categories.tutorials" as visible text --
    // caught in the browser, not by the type checker, because an unresolved t()
    // key is a perfectly valid string.
    'documentation.categories',
    'footer',
    'navigation',
    'newsletter',
    'pages.solutionPages.leadMagnetButton',
    'pages.solutionPages.leadMagnetModal',
    'pages.solutionPages.*.hero.title',
    'regionPicker',
    'solutions.categories',
  ],
  'client-route': ['hero.install.tabs', 'pages.downloads', 'pages.install', 'pages.partners.form'],
};

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

function fail(message: string): never {
  process.stderr.write(`\n\x1b[31mFAIL\x1b[0m  generate-client-i18n: ${message}\n\n`);
  process.exit(1);
}

function isContainer(value: unknown): value is Json[] | { [k: string]: Json } {
  return typeof value === 'object' && value !== null;
}

/** Child keys of an object or array, in source order. */
function childKeys(value: Json[] | { [k: string]: Json }): string[] {
  return Array.isArray(value) ? value.map((_, i) => String(i)) : Object.keys(value);
}

function childAt(value: Json[] | { [k: string]: Json }, key: string): Json | undefined {
  if (Array.isArray(value)) {
    const index = Number(key);
    return Number.isInteger(index) && index >= 0 && index < value.length ? value[index] : undefined;
  }
  return Object.prototype.hasOwnProperty.call(value, key) ? value[key] : undefined;
}

/**
 * Expand one allowlist path against a catalog into concrete dotted paths.
 * Returns [] when nothing matches, which the caller treats as an error.
 */
function expand(catalog: Json, pattern: string): string[] {
  const segments = pattern.split('.');
  let frontier: { node: Json; path: string[] }[] = [{ node: catalog, path: [] }];
  for (const segment of segments) {
    const next: { node: Json; path: string[] }[] = [];
    for (const { node, path: here } of frontier) {
      if (!isContainer(node)) continue;
      const keys = segment === '*' ? childKeys(node) : [segment];
      for (const key of keys) {
        const child = childAt(node, key);
        if (child === undefined) continue;
        next.push({ node: child, path: [...here, key] });
      }
    }
    frontier = next;
  }
  return frontier.map((f) => f.path.join('.'));
}

/** Every leaf path under a dotted path, in source order. */
function leavesUnder(catalog: Json, dotted: string): string[] {
  const node = dotted.split('.').reduce<Json | undefined>((current, key) => {
    if (current === undefined || !isContainer(current)) return undefined;
    return childAt(current, key);
  }, catalog);
  if (node === undefined) return [];
  const out: string[] = [];
  const walk = (value: Json, prefix: string): void => {
    if (isContainer(value)) {
      for (const key of childKeys(value)) {
        walk(childAt(value, key) as Json, `${prefix}.${key}`);
      }
      return;
    }
    out.push(prefix);
  };
  walk(node, dotted);
  return out;
}

/** Copy one dotted path from `source` into `target`, creating containers as needed. */
function graft(source: Json, target: { [k: string]: Json }, dotted: string): boolean {
  const segments = dotted.split('.');

  // Resolve the source once, keeping every node on the way. The SHAPE of each container is
  // decided by the source, so an array in en.json stays an array in the slice.
  // An array in en.json must stay an array in the slice, or `ta()` breaks on it.
  const chain: Json[] = [source];
  let cursor: Json = source;
  for (const segment of segments) {
    if (!isContainer(cursor)) return false;
    const next = childAt(cursor, segment);
    if (next === undefined) return false;
    cursor = next;
    chain.push(next);
  }

  let node: { [k: string]: Json } | Json[] = target;
  for (let i = 0; i < segments.length - 1; i++) {
    const segment = segments[i];
    const key: string | number = Array.isArray(node) ? Number(segment) : segment;
    // Explicit annotation: without it TS7022 fires, because `existing` feeds
    // `isContainer`, which narrows back onto `existing` itself, and the inferred
    // type ends up referencing its own initializer.
    const existing: Json | undefined = (node as Record<string | number, Json>)[key];
    let child: { [k: string]: Json } | Json[];
    if (isContainer(existing)) {
      child = existing;
    } else {
      child = Array.isArray(chain[i + 1]) ? [] : {};
      (node as Record<string | number, Json>)[key] = child;
    }
    node = child;
  }

  const last = segments[segments.length - 1];
  const lastKey = Array.isArray(node) ? Number(last) : last;
  (node as Record<string | number, Json>)[lastKey] = chain[segments.length];
  return true;
}

function readCatalog(locale: SiteLocale): Json {
  const file = path.join(translationsDir, `${locale}.json`);
  if (!fs.existsSync(file)) {
    fail(
      `${path.relative(wwwRoot, file)} is missing.\n` +
        `        @rediacc/locales declares ${SITE_LOCALES.length} site locales ` +
        `(${SITE_LOCALES.join(', ')}) and every one of them must have a catalog.\n` +
        `        Restore it with: git checkout -- ${path.relative(process.cwd(), file)}`
    );
  }
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8')) as Json;
  } catch (error) {
    fail(`${path.relative(wwwRoot, file)} is not valid JSON: ${(error as Error).message}`);
  }
}

// ─── The slice ────────────────────────────────────────────────────────────────

const english = readCatalog('en');

/** Expanded once against English, so every locale of a bundle ships the SAME key set. */
function wantedKeys(bundle: BundleName): string[] {
  const wanted: string[] = [];
  for (const pattern of CLIENT_KEY_PATHS[bundle]) {
    const matches = expand(english, pattern);
    if (matches.length === 0) {
      fail(
        `CLIENT_KEY_PATHS.${bundle} entry "${pattern}" matches nothing in en.json.\n` +
          `        The allowlist has drifted from the English catalog. Either the key was ` +
          `renamed or removed, or the entry is a typo.`
      );
    }
    for (const match of matches) {
      for (const leaf of leavesUnder(english, match)) {
        if (!wanted.includes(leaf)) wanted.push(leaf);
      }
    }
  }
  return wanted;
}

const WANTED: Record<BundleName, string[]> = {
  client: wantedKeys('client'),
  'client-route': wantedKeys('client-route'),
};

/**
 * A key may live in exactly ONE bundle. Two copies would ship the same string twice and,
 * worse, would let an every-route island keep working after its key moved to the route
 * bundle, so the coverage check below would stop meaning anything.
 */
const overlap = WANTED.client.filter((k) => WANTED['client-route'].includes(k));
if (overlap.length > 0) {
  fail(
    `${overlap.length} key(s) are in BOTH bundles:\n` +
      overlap
        .slice(0, 10)
        .map((k) => `          ${k}`)
        .join('\n') +
      `\n        Put each key in exactly one of CLIENT_KEY_PATHS.client / .client-route.`
  );
}

function buildSlice(bundle: BundleName, locale: SiteLocale): string {
  const catalog = readCatalog(locale);
  const slice: { [k: string]: Json } = {};
  const missing: string[] = [];
  for (const leaf of WANTED[bundle]) {
    if (!graft(catalog, slice, leaf)) missing.push(leaf);
  }
  if (missing.length > 0) {
    fail(
      `${locale}.json is missing ${missing.length} key(s) the browser needs for the ` +
        `${bundle} bundle:\n` +
        missing
          .slice(0, 10)
          .map((k) => `          ${k}`)
          .join('\n') +
        (missing.length > 10 ? `\n          ... and ${missing.length - 10} more` : '') +
        `\n        Fix the locale catalog (check-translation-completeness names the same ` +
        `gap), do not narrow the allowlist.`
    );
  }
  return `${JSON.stringify(slice, null, 2)}\n`;
}

/** bundle -> locale -> file contents. Exported so the freshness gate compares without writing. */
export function buildClientCatalogs(): Map<BundleName, Map<SiteLocale, string>> {
  const out = new Map<BundleName, Map<SiteLocale, string>>();
  for (const bundle of Object.keys(BUNDLES) as BundleName[]) {
    const perLocale = new Map<SiteLocale, string>();
    for (const locale of SITE_LOCALES) perLocale.set(locale, buildSlice(bundle, locale));
    out.set(bundle, perLocale);
  }
  return out;
}

/** bundle -> the directory its catalogs live in. */
export const CLIENT_DIRS: Record<BundleName, string> = {
  client: BUNDLES.client.dir,
  'client-route': BUNDLES['client-route'].dir,
};

export type ClientBundleName = BundleName;

// ─── The control: the allowlist must cover the islands ────────────────────────

function listFiles(dir: string, extension: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listFiles(full, extension));
    else if (entry.name.endsWith(extension)) out.push(full);
  }
  return out;
}

/**
 * The islands, grouped by the hook they call. Derived, never listed, because a hand-written
 * list is exactly the shape that let ar/ja/ru/zh go unprotected for months.
 *
 * A file that calls BOTH hooks is an error: its keys would have to live in both bundles,
 * which the overlap check above forbids.
 */
function islandsByBundle(): Map<BundleName, string[]> {
  const out = new Map<BundleName, string[]>();
  for (const bundle of Object.keys(BUNDLES) as BundleName[]) out.set(bundle, []);

  for (const file of listFiles(srcDir, '.tsx')) {
    const content = fs.readFileSync(file, 'utf8');
    const hooks = (Object.keys(BUNDLES) as BundleName[]).filter((bundle) =>
      new RegExp(`\\b${BUNDLES[bundle].hook}\\s*\\(`).test(content)
    );
    if (hooks.length === 0) continue;
    if (hooks.length > 1) {
      fail(
        `${path.relative(wwwRoot, file)} calls more than one translation hook ` +
          `(${hooks.map((h) => BUNDLES[h].hook).join(', ')}).\n` +
          `        An island belongs to exactly one bundle.`
      );
    }
    out.get(hooks[0])!.push(file);
  }
  return out;
}

/** `const NS = 'dotted.string'` in this file, whatever it is called. */
function namespaceVars(content: string): Map<string, string> {
  const found = new Map<string, string>();
  const re = /\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*['"]([^'"\s]*\.[^'"\s]*)['"]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(content)) !== null) {
    if (!found.has(m[1])) found.set(m[1], m[2]);
  }
  return found;
}

interface IslandKey {
  key: string;
  dynamic: boolean;
}

function extractIslandKeys(content: string): IslandKey[] {
  const keys: IslandKey[] = [];
  const vars = namespaceVars(content);

  const direct = /\b(t[ao]?)\(\s*['"]([^'"]+)['"]\s*[,)]/g;
  let m: RegExpExecArray | null;
  while ((m = direct.exec(content)) !== null) {
    keys.push({ key: m[2], dynamic: false });
  }

  // Template literals: `${NS}.suffix`, `literal.${expr}...`, or a mix of both.
  const template = /\b(t[ao]?)\(\s*`([^`]+)`/g;
  while ((m = template.exec(content)) !== null) {
    let raw = m[2];
    for (const [name, value] of vars) {
      raw = raw.replaceAll(`\${${name}}`, value);
    }
    if (!raw.includes('${')) {
      keys.push({ key: raw, dynamic: false });
      continue;
    }
    // Keep the literal prefix that precedes the first interpolation.
    const literal = raw.slice(0, raw.indexOf('${')).replace(/\.$/, '');
    if (literal.length > 0) keys.push({ key: literal, dynamic: true });
  }

  return keys;
}

function checkIslandCoverage(): void {
  const uncovered: string[] = [];

  for (const [bundle, files] of islandsByBundle()) {
    const wanted = WANTED[bundle];
    const shipped = new Set(wanted);
    const shippedPrefixes = new Set<string>();
    for (const leaf of wanted) {
      const parts = leaf.split('.');
      for (let i = 1; i <= parts.length; i++) shippedPrefixes.add(parts.slice(0, i).join('.'));
    }

    for (const file of files) {
      const where = path.relative(wwwRoot, file);
      for (const { key, dynamic } of extractIslandKeys(fs.readFileSync(file, 'utf8'))) {
        if (dynamic) {
          // A dynamic key is covered when SOMETHING under its literal prefix ships.
          if (!shippedPrefixes.has(key)) {
            uncovered.push(`[${bundle}] ${where}: \`${key}.\${...}\` (dynamic prefix)`);
          }
          continue;
        }
        // A static key is covered when it ships as a leaf, or its whole subtree ships.
        const coversSubtree = wanted.some((leaf) => leaf.startsWith(`${key}.`));
        if (!shipped.has(key) && !coversSubtree) {
          // Only complain about keys that actually exist in English. A key missing from
          // en.json entirely is check-translation-key-usage's finding, not this script's.
          if (leavesUnder(english, key).length > 0) {
            uncovered.push(`[${bundle}] ${where}: ${key}`);
          }
        }
      }
    }
  }

  if (uncovered.length > 0) {
    fail(
      `${uncovered.length} translation key(s) used by a hydrated island are NOT in that ` +
        `island's bundle.\n` +
        `        They would render as the raw key string in the browser.\n\n` +
        uncovered.map((u) => `          ${u}`).join('\n') +
        `\n\n        Add the missing path(s) to the right half of CLIENT_KEY_PATHS in ` +
        `packages/www/scripts/generate-client-i18n.ts and regenerate.`
    );
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

function main(): void {
  checkIslandCoverage();

  const catalogs = buildClientCatalogs();
  let grandTotal = 0;

  for (const [bundle, perLocale] of catalogs) {
    const dir = CLIENT_DIRS[bundle];
    fs.mkdirSync(dir, { recursive: true });

    // Remove any stale file: a locale dropped from @rediacc/locales must not linger, and
    // resolveClientCatalogs throws on an unexpected one.
    for (const entry of fs.readdirSync(dir)) {
      if (!entry.endsWith('.json')) continue;
      const locale = entry.slice(0, -'.json'.length);
      if (!(SITE_LOCALES as readonly string[]).includes(locale)) {
        fs.unlinkSync(path.join(dir, entry));
        process.stdout.write(`  removed stale ${bundle}/${entry}\n`);
      }
    }

    let total = 0;
    for (const [locale, contents] of perLocale) {
      fs.writeFileSync(path.join(dir, `${locale}.json`), contents, 'utf8');
      total += Buffer.byteLength(contents);
    }
    grandTotal += total;
    process.stdout.write(
      `  ${bundle.padEnd(13)} ${SITE_LOCALES.length} locales x ${WANTED[bundle].length} keys, ` +
        `${total} B\n`
    );
  }

  process.stdout.write(`\nGenerated ${grandTotal} B into src/i18n/{client,client-route}/\n`);
}

// Run only when invoked as a script. The freshness gate imports this module for
// `buildClientCatalogs` and must not have it write files as a side effect.
if (path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) main();

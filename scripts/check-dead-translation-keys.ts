#!/usr/bin/env tsx
/**
 * English translation keys that no code path can ever reach.
 *
 * THE DIRECTION NOTHING WAS CHECKING. `scripts/check-translation-key-usage.ts` walks
 * SOURCE to CATALOG: every `t('x')` must exist in `en.json`, which catches a key that
 * would render as a raw string. Nothing walked CATALOG to SOURCE, so a key that exists and
 * is referenced by nothing was invisible in every direction: it is present, so the usage
 * gate passes; it is translated, so completeness passes; its value differs from English in
 * every locale, so the untranslated gate passes. Dead weight is the one property none of
 * them can express.
 *
 * WHAT IS DEAD TODAY: 300 English leaves across 110 branches, including the whole of
 * `pages.pricing.plans.*.features` and 55 `ui.*` leaves under pricing and disaster
 * recovery. Each dead leaf is also carried in twelve other catalogs, translated at cost,
 * re-naturalized whenever English changes, and shipped in the 6.7 MB client bundle. One of
 * them reads "Includes $9,999 setup credit", which is the kind of string that is only
 * harmless while it stays unreachable.
 *
 * HOW REACHABILITY IS DECIDED, AND WHERE IT IS DELIBERATELY GENEROUS. Every reference the
 * site can make is collected as a PATTERN, and a key is reachable if any pattern equals it
 * or is a prefix of it. Three shapes produce patterns:
 *   1. a literal call -- `t('a.b')`, `ta("a.b")`, `to('a.b')`;
 *   2. a template call -- `t(`${ns}.a.b`)`, where `ns` is resolved from its declaration in
 *      the same file, INCLUDING a template declaration such as
 *      `const ns = `pages.resourcesBrief.${deckKey}``, which becomes
 *      `pages.resourcesBrief.*`. Resolving only string-literal namespaces was this gate's
 *      first version, and it reported 222 keys as dead that a template namespace reaches
 *      perfectly well. Every one of them was a false positive, and false positives are
 *      what get a gate switched off;
 *   3. any dotted string of three or more segments appearing anywhere in the sources,
 *      which covers config tables that carry key paths as data
 *      (`src/config/install.ts`'s `labelKey: 'hero.install.tabs.linux'`), and `{{t:key}}`
 *      placeholders in markdown.
 * An unresolved interpolation becomes `*`, matching ONE segment. Generosity is the right
 * bias here: a false positive costs a real translation, while a missed dead key costs
 * nothing but bytes.
 *
 * A KEY REPORTED HERE THAT IS ACTUALLY REACHED IS A BUG IN THIS FILE, NOT A CANDIDATE FOR
 * AN ALLOWLIST. It means the site reaches a key by a shape the extractor cannot see, and
 * the fix is to teach the extractor that shape, so the next key reached the same way is
 * covered too.
 *
 * Usage:
 *   tsx scripts/check-dead-translation-keys.ts [--root <dir>] [--selftest] [--list]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WWW_SRC = 'packages/www/src';
const EN_JSON = 'packages/www/src/i18n/translations/en.json';
const SOURCE_EXTS = ['.astro', '.tsx', '.ts', '.js', '.mjs', '.md', '.mdx'];

/** Floors. Either one failing means the scan lost its input, not that the site is clean. */
const MIN_SOURCE_FILES = 50;
const MIN_PATTERNS = 200;

export interface DeadBranch {
  branch: string;
  leaves: string[];
}

function walk(dir: string, out: string[] = []): string[] {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs
    .readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.name.startsWith('.') || entry.name === 'node_modules') continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs, out);
    else if (SOURCE_EXTS.some((e) => entry.name.endsWith(e))) out.push(abs);
  }
  return out;
}

/** Dotted paths of every leaf, arrays indexed numerically as the runtime resolves them. */
export function leafKeys(value: unknown, prefix = '', out: string[] = []): string[] {
  if (Array.isArray(value)) {
    value.forEach((v, i) => leafKeys(v, prefix ? `${prefix}.${i}` : String(i), out));
  } else if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      leafKeys(v, prefix ? `${prefix}.${k}` : k, out);
    }
  } else if (prefix) out.push(prefix);
  return out;
}

/** `${anything}` becomes a single-segment wildcard. */
const wildcard = (s: string): string => s.replace(/\$\{[^}]*\}/g, '*');

/**
 * Namespace constants declared in one file, whatever they are named.
 *
 * The name is NOT hard-coded: this repo has shipped `ns`, `PAGE_KEY` and `NS` for the same
 * job, and a gate that knew two of the three was blind to every call in the file using the
 * third. A dotted value is the requirement, which is what keeps `const TITLE = 'Partners'`
 * from being mistaken for a namespace.
 */
export function namespaceVars(src: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of src.matchAll(
    /\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*['"]([^'"\s]*\.[^'"\s]*)['"]/g
  )) {
    if (!out.has(m[1])) out.set(m[1], m[2]);
  }
  for (const m of src.matchAll(
    /\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*`([^`]*\.[^`]*)`/g
  )) {
    if (!out.has(m[1])) out.set(m[1], wildcard(m[2]));
  }
  return out;
}

/**
 * Identifiers bound to a locale catalog by a STATIC IMPORT, e.g.
 * `import en from '../i18n/translations/en.json'`. Keys reached as `en.a.b` never
 * pass through t(), so every t()-shaped pattern above is blind to them. This was
 * not hypothetical: `announcement.enabled` is read exactly this way in
 * AnnouncementBar.astro and the gate reported it as reachable by no code path.
 */
export function catalogImportVars(src: string): string[] {
  const out: string[] = [];
  for (const m of src.matchAll(
    /\bimport\s+([A-Za-z_$][\w$]*)\s+from\s+['"][^'"]*\/translations\/[A-Za-z-]+\.json['"]/g
  ))
    out.push(m[1]);
  return out;
}

export function referencePatterns(src: string): string[] {
  const pats: string[] = [];
  const ns = namespaceVars(src);

  for (const m of src.matchAll(/\bt[ao]?\(\s*['"]([^'"]+)['"]/g)) pats.push(m[1]);
  for (const m of src.matchAll(/\bt[ao]?\(\s*`([^`]+)`/g)) {
    pats.push(
      wildcard(
        m[1].replace(/\$\{([A-Za-z_$][\w$]*)\}/g, (whole, name: string) => ns.get(name) ?? whole)
      )
    );
  }
  for (const m of src.matchAll(/\{\{t:([^}\s]+)\}\}/g)) pats.push(m[1]);
  // Key paths carried as DATA in a config table, and template key paths built inline.
  for (const m of src.matchAll(/['"]([a-zA-Z][\w]*(?:\.[a-zA-Z][\w]*){2,})['"]/g)) pats.push(m[1]);
  for (const m of src.matchAll(/`([a-zA-Z][\w]*(?:\.[a-zA-Z_${}][\w${}]*){2,})`/g)) {
    pats.push(
      wildcard(
        m[1].replace(/\$\{([A-Za-z_$][\w$]*)\}/g, (whole, name: string) => ns.get(name) ?? whole)
      )
    );
  }
  // Keys reached by property access on a statically imported catalog: `en.a.b.c`.
  for (const v of catalogImportVars(src)) {
    const re = new RegExp(`\\b${v}\\.([A-Za-z][\\w]*(?:\\.[A-Za-z][\\w]*)*)`, 'g');
    for (const m of src.matchAll(re)) pats.push(m[1]);
  }
  return pats;
}

/** A pattern matches a key when it equals it or is a prefix of it. `*` spans one segment. */
export function buildMatcher(patterns: Iterable<string>): (key: string) => boolean {
  const exact = new Set<string>();
  const prefixes: string[] = [];
  const wild: RegExp[] = [];
  for (const p of patterns) {
    if (p.includes('*')) {
      wild.push(new RegExp(`^${p.split('*').map(escapeRe).join('[^.]+')}(\\.|$)`));
    } else {
      exact.add(p);
      prefixes.push(`${p}.`);
    }
  }
  const prefixSet = new Set(prefixes);
  return (key: string): boolean => {
    if (exact.has(key)) return true;
    // Walk the key's own ancestors rather than every pattern: 9,190 keys against 1,300
    // patterns is 12 million comparisons, and each key has fewer than ten ancestors.
    const parts = key.split('.');
    for (let i = 1; i <= parts.length; i++) {
      if (prefixSet.has(`${parts.slice(0, i).join('.')}.`)) return true;
      if (exact.has(parts.slice(0, i).join('.'))) return true;
    }
    return wild.some((r) => r.test(key));
  };
}

const escapeRe = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function selftest(): boolean {
  const failures: string[] = [];
  const check = (name: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}${detail ? `\n        ${detail}` : ''}`);
      failures.push(name);
    }
  };

  const reach = (src: string, key: string) => buildMatcher(referencePatterns(src))(key);

  // THE PLANT: an orphan key, reachable by nothing.
  const SRC = `const ns = 'pages.pricing';
export const P = () => <h1>{t(\`\${ns}.hero.title\`)}</h1>;`;
  check(
    'PLANT: a key nothing references is unreachable',
    !reach(SRC, 'pages.pricing.orphan.title')
  );
  check(
    'a key reached through a string namespace is reachable (control)',
    reach(SRC, 'pages.pricing.hero.title')
  );

  // The false-positive class that the first version produced: a TEMPLATE namespace.
  const TMPL = 'const ns = `pages.resourcesBrief.${deckKey}`;\nconst x = t(`${ns}.title`);';
  check(
    'a key reached through a TEMPLATE namespace is reachable (control)',
    reach(TMPL, 'pages.resourcesBrief.ransomwareSurvival.title')
  );
  // A template namespace deliberately vouches for its whole subtree (see the header: the
  // deck key is data, so every deck under it is reachable). What it must NOT do is reach
  // past its own prefix -- a wildcard segment is one segment, never a free pass.
  check(
    'a template namespace covers its own subtree (control)',
    reach(TMPL, 'pages.resourcesBrief.ransomwareSurvival.sections.0.body')
  );
  check(
    'a template namespace does NOT vouch for a different branch',
    !reach(TMPL, 'pages.pricing.plans.pro.name')
  );

  const DYNAMIC = "const ns = 'pages.pricing';\nconst n = t(`${ns}.plans.${p.id}.name`);";
  check(
    'a dynamic segment makes every sibling reachable (control)',
    reach(DYNAMIC, 'pages.pricing.plans.pro.name') &&
      reach(DYNAMIC, 'pages.pricing.plans.free.name')
  );
  check(
    'a dynamic segment does NOT make an unrelated leaf reachable',
    !reach(DYNAMIC, 'pages.pricing.plans.pro.features.0')
  );

  check(
    'a key carried as config DATA is reachable (control)',
    reach("{ key: 'linux', labelKey: 'hero.install.tabs.linux' }", 'hero.install.tabs.linux')
  );
  check(
    'a {{t:key}} placeholder in markdown is reachable (control)',
    reach('Some docs text {{t:docs.cli.overview}} more text', 'docs.cli.overview')
  );
  check(
    'a `to()` subtree reference covers its children (control)',
    reach("const o = to('pages.company.mission');", 'pages.company.mission.belief')
  );

  // A different key with a matching SUFFIX must not be laundered as reachable, or half the
  // dead keys in the tree would look alive.
  check(
    'a similarly named key elsewhere does not make this one reachable',
    !reach("const x = t('layout.meta.siteName');", 'common.siteName')
  );

  // The leaf walker must see arrays, because `items.0.text` is how most content is stored.
  check(
    'array elements are leaf keys',
    leafKeys({ a: { items: ['x', 'y'] } }).join(',') === 'a.items.0,a.items.1',
    leafKeys({ a: { items: ['x', 'y'] } }).join(',')
  );

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dead-keys-'));
  fs.writeFileSync(path.join(tmp, 'A.astro'), SRC);
  {
    const imp =
      "import en from '../i18n/translations/en.json';\nconst on = en.announcement.enabled === true;";
    check(
      'a key read off a statically imported catalog is reachable (control)',
      reach(imp, 'announcement.enabled')
    );
    check(
      'a static catalog import does NOT vouch for an unrelated branch',
      !reach(imp, 'pages.contact.form.submit')
    );
    check(
      'a non-catalog import of the same shape is ignored',
      !reach(
        "import en from '../data/en.json';\nconst on = en.announcement.enabled;",
        'announcement.enabled'
      )
    );
  }
  check('the walker finds source files on disk', walk(tmp).length === 1);
  fs.rmSync(tmp, { recursive: true, force: true });

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

  const base = path.resolve(arg('--root') ?? REPO_ROOT);
  const enPath = path.join(base, EN_JSON);
  const srcDir = path.join(base, WWW_SRC);
  if (!fs.existsSync(enPath) || !fs.existsSync(srcDir)) {
    console.error(
      `✗ Refusing to run: need both ${enPath} and ${srcDir}.\n` +
        `  With either missing, every key would look dead or every key would look alive.`
    );
    process.exit(1);
  }

  const keys = leafKeys(JSON.parse(fs.readFileSync(enPath, 'utf-8')));
  const files = walk(srcDir);
  const patterns = new Set<string>();
  for (const file of files) {
    for (const p of referencePatterns(fs.readFileSync(file, 'utf-8'))) patterns.add(p);
  }

  if (files.length < MIN_SOURCE_FILES || patterns.size < MIN_PATTERNS) {
    console.error(
      `✗ Refusing to run: ${files.length} source file(s) yielded ${patterns.size} reference ` +
        `pattern(s), below the floors of ${MIN_SOURCE_FILES} and ${MIN_PATTERNS}.\n` +
        `  With no patterns, EVERY key is dead -- a failure that looks like a catastrophic ` +
        `finding rather than a broken scan.`
    );
    process.exit(1);
  }

  const reachable = buildMatcher(patterns);
  const dead = keys.filter((k) => !reachable(k));

  if (argv.includes('--list')) {
    for (const k of dead) console.log(k);
    return;
  }

  if (dead.length === 0) {
    console.log(
      `✓ All ${keys.length} English translation key(s) are reachable from ${files.length} ` +
        `source file(s) (${patterns.size} reference pattern(s)).`
    );
    return;
  }

  // Group by the shallowest branch that holds only dead leaves, so 46 sibling leaves read
  // as one decision to make rather than 46.
  const byBranch = new Map<string, string[]>();
  for (const k of dead) {
    const branch = k.split('.').slice(0, 3).join('.');
    byBranch.set(branch, [...(byBranch.get(branch) ?? []), k]);
  }

  console.error(
    `✗ ${dead.length} English translation key(s) in ${byBranch.size} branch(es) are reachable ` +
      `by no code path, out of ${keys.length} key(s):\n`
  );
  for (const [branch, list] of [...byBranch]
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, 30)) {
    console.error(`  ${branch}  (${list.length})`);
    for (const k of list.slice(0, 3)) console.error(`    ${k}`);
    if (list.length > 3) console.error(`    ... and ${list.length - 3} more`);
  }
  if (byBranch.size > 30) console.error(`  ... and ${byBranch.size - 30} more branch(es)`);
  console.error(
    `\nEach of these is also carried in twelve other catalogs, translated, re-naturalized on\n` +
      `every English change, and shipped to every visitor. Delete the branch from all 13\n` +
      `catalogs, or wire it up.\n` +
      `Full list: npx tsx scripts/check-dead-translation-keys.ts --list\n` +
      `If a key IS reached and is listed here, the reference shape is one this gate cannot\n` +
      `see: extend referencePatterns() rather than allowlisting the key.`
  );
  process.exit(1);
}

main();

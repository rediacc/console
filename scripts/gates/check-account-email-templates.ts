#!/usr/bin/env node
// ---- gate ---- kind: shared-step step: i18n needs: node, submodules id: check:ci-i18n-account-email-templates lane: quality-i18n ---- end gate ----

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { SITE_LOCALES } from '@rediacc/locales';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.join(__dirname, '..', '..');
const TEMPLATE_DIR = submodulePath('private/account/src/email/templates');
const LOCALES_DIR = submodulePath('private/account/src/i18n/locales');
const LANGUAGES = SITE_LOCALES;
const TEMPLATE_FILES = [
  'auth.ts',
  'billing.ts',
  'contact.ts',
  'newsletter.ts',
  'organization.ts',
  'partner.ts',
  'partner-certification.ts',
  'partner-deals.ts',
  'partner-eval.ts',
  'partner-license.ts',
  'security.ts',
  // Added 2026-09-07. Both were on disk and NOT in this list, so this gate was checking 11 of the 13 real templates and saying nothing about the other two.
  'delegation-cert-renewal-alert.ts',
  'lead-magnet.ts',
  'legal.ts',
  // Added 2026-11-12 (PLAN-account-notices E1): the one digest shape, plural-aware through tCount.
  'digest.ts',
];

/** The CLDR plural categories `Intl.PluralRules` can select. */
const PLURAL_CATEGORIES = new Set(['zero', 'one', 'two', 'few', 'many', 'other']);

/**
 * A PLURAL GROUP is an object whose keys are all CLDR categories and include `other`, read by
 * `tCount(key, count)` in private/account/src/i18n/index.ts as `<key>.<category>` with a
 * fallback to `<key>.other`. English holds one/other, Russian one/few/many/other, Japanese
 * other alone, so the generic "every English key exists in every locale" rule cannot apply to
 * a group's leaves: each locale instead holds `.other` plus exactly the categories its own
 * plural rules produce, and nothing outside the CLDR set.
 */
function pluralGroups(input: unknown, prefix = ''): string[] {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return [];
  const entries = Object.entries(input as Record<string, unknown>);
  const keys = entries.map(([k]) => k);
  if (
    keys.length > 0 &&
    keys.includes('other') &&
    keys.every((k) => PLURAL_CATEGORIES.has(k)) &&
    entries.every(([, v]) => typeof v === 'string')
  ) {
    return [prefix];
  }
  return entries.flatMap(([key, value]) => pluralGroups(value, prefix ? `${prefix}.${key}` : key));
}

function nodeAt(tree: unknown, dotted: string): unknown {
  let current: unknown = tree;
  for (const part of dotted.split('.')) {
    if (!current || typeof current !== 'object' || Array.isArray(current)) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

/** Findings for one locale's plural groups, against the groups English declares. */
function pluralFindings(lang: string, englishTree: unknown, localeTree: unknown): string[] {
  const required = new Intl.PluralRules(lang).resolvedOptions().pluralCategories;
  const out: string[] = [];
  for (const group of pluralGroups(englishTree)) {
    const node = nodeAt(localeTree, group);
    if (!node || typeof node !== 'object' || Array.isArray(node)) {
      out.push(`${lang}/emails.json: missing plural group "${group}"`);
      continue;
    }
    const have = node as Record<string, unknown>;
    for (const category of new Set(['other', ...required])) {
      if (typeof have[category] !== 'string') {
        out.push(`${lang}/emails.json: plural group "${group}" lacks "${category}"`);
      }
    }
    for (const key of Object.keys(have)) {
      if (!PLURAL_CATEGORIES.has(key)) {
        out.push(`${lang}/emails.json: plural group "${group}" holds non-CLDR key "${key}"`);
      }
    }
  }
  return out;
}

/**
 * The plural check must be able to FIRE before its green means anything: a planted locale
 * whose group lacks `.other` (and Russian's `few`) has to produce findings, and a complete one
 * none. Run on every invocation, so a refactor that blinds the check fails the gate itself.
 */
function pluralControlFailures(): string[] {
  const english = { g: { h: { one: '{{count}} x', other: '{{count}} xs' } } };
  const missingOther = pluralFindings('ru', english, {
    g: { h: { one: 'a', few: 'b', many: 'c' } },
  });
  const complete = pluralFindings('ru', english, {
    g: { h: { one: 'a', few: 'b', many: 'c', other: 'd' } },
  });
  const japanese = pluralFindings('ja', english, { g: { h: { other: 'a' } } });
  const out: string[] = [];
  if (!missingOther.some((f) => f.includes('lacks "other"'))) {
    out.push('CONTROL: a plural group without "other" was not reported; the plural check is blind');
  }
  if (complete.length > 0 || japanese.length > 0) {
    out.push(
      `CONTROL: a complete plural group was reported: ${[...complete, ...japanese].join('; ')}`
    );
  }
  return out;
}

/**
 * Files in TEMPLATE_DIR that are NOT templates, named so the drift check below can
 * tell "not a template" from "template nobody listed".
 *
 * `shared.ts` is the region/footer helper the templates import; it exports no
 * template and has no locale keys to check.
 */
const TEMPLATE_DIR_NON_TEMPLATES = new Set(['shared.ts']);

/**
 * Templates that ARE templates but are knowingly not locale-backed yet.
 *
 * BLOCKER: `delegation-cert-renewal-alert.ts` renders English-only. It calls
 * `renderCommonLayout('en', ...)` with the locale hardcoded and uses no `t()` call
 * at all, so it has no keys for the other twelve locales to be missing. Found
 * 2026-09-07 the first time it was ever checked: it had been absent from
 * TEMPLATE_FILES since it was written, which is precisely what the drift refusal
 * below now prevents.
 *
 * It is NOT excluded to make the gate quiet. It is listed here so the gap is a
 * named entry a reader can act on, rather than a file nothing mentions. The fix
 * belongs in private/account, which is out of scope for the change that found this.
 * Remove this entry the moment the template takes a locale.
 */
const NOT_YET_LOCALIZED = new Set(['delegation-cert-renewal-alert.ts']);

/**
 * THE LIST ABOVE MUST COVER THE DIRECTORY, and until 2026-09-07 nothing said so.
 *
 * A hand-written inventory of a directory goes stale the moment someone adds a
 * file, and the failure is silent in the worst direction: the gate keeps passing
 * while quietly checking less than it did. Measured on the day this was added, the
 * list held 11 names against 13 real templates, so `delegation-cert-renewal-alert`
 * and `lead-magnet` had never been checked in any locale.
 *
 * This is the same class as `POLICY_FILES` in scripts/lib/policy-paths.ts, which
 * had 15 names against 16 files on disk on the same day. Both were found by
 * sweeping for the class rather than the instance.
 */
/**
 * The floor, added 2026-09-09 because this gate could report success having checked
 * NOTHING.
 *
 * `private/account` is a SUBMODULE. A checkout without it initialised leaves TEMPLATE_DIR
 * absent, and the line below used to `return []` on that -- an empty finding list, which
 * every caller reads as a clean tree. The same silence covered a populated submodule whose
 * templates had moved: an empty `onDisk` produces no `unlisted` and no `absent`, so the
 * gate ticked over a directory it had never read.
 *
 * TEN AND NOT THIRTEEN. Thirteen is today's count and a floor equal to the live number
 * turns every legitimate deletion into a gate failure, which is how a floor gets deleted
 * rather than lowered. Ten is under the current corpus and far above the zero and one that
 * a broken path produces.
 */
const MIN_TEMPLATES = 10;

function refuseIfListDrifted(): string[] {
  if (!fs.existsSync(TEMPLATE_DIR)) {
    return [
      `VACUOUS: ${path.relative(ROOT_DIR, TEMPLATE_DIR)} does not exist, so this gate ` +
        'checked no template at all. private/account is a submodule; initialise it, or ' +
        'repoint TEMPLATE_DIR. An absent corpus is a refusal, never a pass.',
    ];
  }
  const onDisk = fs
    .readdirSync(TEMPLATE_DIR)
    .filter((f) => f.endsWith('.ts') && !TEMPLATE_DIR_NON_TEMPLATES.has(f));
  if (onDisk.length < MIN_TEMPLATES) {
    return [
      `VACUOUS: ${path.relative(ROOT_DIR, TEMPLATE_DIR)} yielded ${onDisk.length} ` +
        `template(s), below the floor of ${MIN_TEMPLATES}. The directory moved or the ` +
        'filter stopped matching; either way every check below would pass on an empty set.',
    ];
  }
  const listed = new Set<string>(TEMPLATE_FILES);
  const unlisted = onDisk.filter((f) => !listed.has(f));
  const absent = TEMPLATE_FILES.filter((f) => !fs.existsSync(path.join(TEMPLATE_DIR, f)));
  const out: string[] = [];
  for (const f of unlisted) {
    out.push(
      `${f} is in ${path.relative(ROOT_DIR, TEMPLATE_DIR)} but not in TEMPLATE_FILES, ` +
        'so this gate never checks it. Add it, or add it to TEMPLATE_DIR_NON_TEMPLATES ' +
        'with a reason if it is a helper rather than a template.'
    );
  }
  for (const f of absent) {
    out.push(`TEMPLATE_FILES names ${f}, which is not on disk. Remove it or restore the file.`);
  }
  return out;
}
function flattenKeys(input: unknown, prefix = ''): string[] {
  if (typeof input === 'string') {
    return [prefix];
  }
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    return [];
  }
  return Object.entries(input).flatMap(([key, value]) =>
    flattenKeys(value, prefix ? `${prefix}.${key}` : key)
  );
}

function readJson(filePath: string): Record<string, unknown> {
  return JSON.parse(fs.readFileSync(filePath, 'utf8')) as Record<string, unknown>;
}

function findUsedTranslationKeys(content: string): Set<string> {
  const keys = new Set<string>();
  // THE WORD BOUNDARY IS LOAD-BEARING. Without it `t\(` matches the tail of ANY identifier ending in t, so `renderCommonLayout('en', ...)` in delegation-cert-renewal-alert.ts was read as the translation call `t('en')` and reported as `references missing email locale key "en"`. Found 2026-09-07, when that file was added to TEMPLATE_FILES after never having been checked: a false
  // finding that had been waiting for its first reader.
  for (const match of content.matchAll(/(?<![A-Za-z0-9_$])t\(\s*`([^`]+)`/g)) {
    keys.add(match[1]);
  }
  for (const match of content.matchAll(/(?<![A-Za-z0-9_$])t\(\s*'([^']+)'/g)) {
    keys.add(match[1]);
  }
  return keys;
}

/**
 * Does this file render an email?
 *
 * THE LITERAL-KEY TEST IS NOT SUFFICIENT, found 2026-09-07 the moment two templates
 * that had never been checked were added to TEMPLATE_FILES.
 * `delegation-cert-renewal-alert.ts` exports two renderers returning `RenderedEmail`
 * and contains ZERO literal `subject:`/`html:`/`text:` keys, because it composes its
 * envelope through `renderCommonLayout` in `shared.ts`. The old test called that a
 * missing contract, which was the checker being wrong about a correct file rather
 * than the file being wrong.
 *
 * So either shape counts: the literal envelope, or a declared `RenderedEmail` return.
 * Both are the contract; only one of them is written inline.
 */
function hasRenderedEmailContract(content: string): boolean {
  const normalized = content.replace(/\s+/g, ' ');
  const literalEnvelope =
    normalized.includes('subject:') && normalized.includes('html:') && normalized.includes('text:');
  const delegatedEnvelope = /:\s*RenderedEmail\b/.test(normalized);
  return literalEnvelope || delegatedEnvelope;
}

/**
 * Findings for one locale: every English key outside a plural group exists, and each plural
 * group holds the categories the locale's rules select. The plural call lives here, not in
 * main(), so the control below fails if it is dropped.
 */
function localeFindings(lang: string, englishTree: unknown, localeTree: unknown): string[] {
  const englishPluralGroups = new Set(pluralGroups(englishTree));
  const inPluralGroup = (key: string) => englishPluralGroups.has(key.replace(/\.[^.]+$/, ''));
  const localeKeys = new Set(flattenKeys(localeTree));
  const out: string[] = [];
  for (const key of flattenKeys(englishTree)) {
    if (inPluralGroup(key)) continue;
    if (!localeKeys.has(key)) out.push(`${lang}/emails.json: missing key "${key}"`);
  }
  out.push(...pluralFindings(lang, englishTree, localeTree));
  return out;
}

/**
 * Findings for the key names one template names outside t(): the plural fields (tCount's
 * first argument, and `subjectKey` / `headingKey` in ANY template file, reserved for plural
 * groups) and the plain fields (`fixedSubjectKey`, `titleKey`, `leadKey`, `consequenceKey`,
 * `manageNoteKey`, `key`).
 */
function templateKeyFindings(
  fileName: string,
  content: string,
  englishKeys: ReadonlySet<string>,
  englishPluralGroups: ReadonlySet<string>
): string[] {
  const errors: string[] = [];
  // A dotted value only: `key: 'passwordReset' | ...` in auth.ts is a type, not a lookup.
  for (const match of content.matchAll(
    /(?:(?<![A-Za-z0-9_$])tCount\(\s*|\b(?:subject|heading)Key:\s*)'([^'.]+\.[^']+)'/g
  )) {
    if (!englishPluralGroups.has(match[1])) {
      errors.push(`${fileName}: "${match[1]}" is used as a plural group but en has none`);
    }
  }
  for (const match of content.matchAll(
    /\b(?:fixedSubject|title|lead|consequence|manageNote)Key:\s*'([^'.]+\.[^']+)'|\bkey:\s*'([^'.]+\.[^']+)'/g
  )) {
    const key = match[1] ?? match[2];
    if (!englishKeys.has(key)) {
      errors.push(`${fileName}: references missing email locale key "${key}"`);
    }
  }

  return errors;
}

/** Plants for the key-name checks and the plural wiring; each must be reported or stay silent. */
function keyControlFailures(): string[] {
  const out: string[] = [];
  const keys = new Set(['a.title', 'a.lead']);
  const groups = new Set(['n.items']);
  const run = (src: string) => templateKeyFindings('t.ts', src, keys, groups);
  if (!run("const x = { fixedSubjectKey: 'a.missing' };").some((f) => f.includes('a.missing'))) {
    out.push('CONTROL: a fixedSubjectKey naming no English key was not reported');
  }
  if (!run("const x = { titleKey: 'a.nope' };").some((f) => f.includes('a.nope'))) {
    out.push('CONTROL: a titleKey naming no English key was not reported');
  }
  if (!run("const x = { subjectKey: 'a.title' };").some((f) => f.includes('plural group'))) {
    out.push('CONTROL: a subjectKey naming a non-plural key was not reported');
  }
  if (!run("tCount('a.title', 2)").some((f) => f.includes('plural group'))) {
    out.push('CONTROL: a tCount of a non-plural key was not reported');
  }
  const clean = run(
    "const x = { fixedSubjectKey: 'a.title', subjectKey: 'n.items', key: 'a.lead' };"
  );
  if (clean.length > 0) out.push(`CONTROL: valid key names were reported: ${clean.join('; ')}`);
  const english = { a: { title: 'T' }, n: { items: { one: '1', other: 'n' } } };
  if (
    !localeFindings('de', english, { a: { title: 'T' }, n: { items: { other: 'n' } } }).some((f) =>
      f.includes('lacks "one"')
    )
  ) {
    out.push('CONTROL: localeFindings no longer applies the plural check');
  }
  if (
    !localeFindings('de', english, { n: { items: { one: '1', other: 'n' } } }).some((f) =>
      f.includes('missing key "a.title"')
    )
  ) {
    out.push('CONTROL: localeFindings no longer reports a missing key');
  }
  return out;
}

function main(): void {
  console.log('Account Email Template Validation');
  console.log('============================================================\n');

  if (!requireSubmodule('account email template validation', [TEMPLATE_DIR, LOCALES_DIR])) {
    console.log('');
    return;
  }

  const errors: string[] = [];

  // FIRST, before any per-template work: a stale inventory makes every check below
  // pass while covering less than it claims, which is the failure mode that hid two
  // unchecked templates until 2026-09-07.
  errors.push(...refuseIfListDrifted());

  errors.push(...pluralControlFailures());
  errors.push(...keyControlFailures());

  const englishTree = readJson(path.join(LOCALES_DIR, 'en', 'emails.json'));
  const englishKeys = new Set(flattenKeys(englishTree));
  const englishPluralGroups = new Set(pluralGroups(englishTree));

  for (const lang of LANGUAGES) {
    const localeTree = readJson(path.join(LOCALES_DIR, lang, 'emails.json'));
    errors.push(...localeFindings(lang, englishTree, localeTree));
  }

  for (const fileName of TEMPLATE_FILES) {
    if (NOT_YET_LOCALIZED.has(fileName)) continue;
    const filePath = path.join(TEMPLATE_DIR, fileName);
    const content = fs.readFileSync(filePath, 'utf8');
    const usedKeys = findUsedTranslationKeys(content);

    if (!hasRenderedEmailContract(content)) {
      errors.push(`${fileName}: expected template renderer with subject/html/text output`);
    }

    if (usedKeys.size === 0) {
      errors.push(
        `${fileName}: no translation keys found; template files must render locale-backed content`
      );
    }

    if (/subject:\s*['"`]/.test(content)) {
      errors.push(`${fileName}: subject must come from locale keys, not a hardcoded literal`);
    }

    if (/text:\s*['"`]/.test(content)) {
      errors.push(
        `${fileName}: text body must come from locale-backed rendering, not a hardcoded literal`
      );
    }

    for (const key of usedKeys) {
      const concreteKey = key.includes('${') ? null : key;
      if (concreteKey && !englishKeys.has(concreteKey)) {
        errors.push(`${fileName}: references missing email locale key "${concreteKey}"`);
      }
    }

    errors.push(...templateKeyFindings(fileName, content, englishKeys, englishPluralGroups));
  }

  if (errors.length > 0) {
    console.log('\u001B[31mErrors:\u001B[0m');
    for (const error of errors) {
      console.log(`  \u001B[31m✗\u001B[0m ${error}`);
    }
    console.log('\n\u001B[31m✗ Account email template validation FAILED\u001B[0m');
    process.exit(1);
  }

  console.log('\u001B[32m✓\u001B[0m Account email templates and locales are valid\n');
}

main();

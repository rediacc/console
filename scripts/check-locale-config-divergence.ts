#!/usr/bin/env tsx
/**
 * A locale catalog is a translation of English, not a fork of it.
 *
 * THE DEFECT THIS EXISTS FOR. `announcement.enabled` is `false` in
 * packages/www/src/i18n/translations/en.json and `true` in all twelve other catalogs, so
 * the site's announcement bar is off for English readers and on for everyone else. Nobody
 * decided that. It is what happens when a non-text value is carried through a translation
 * pass: the translator has no reason to look at a boolean, and nothing downstream compares
 * it back.
 *
 * WHY NO EXISTING GATE SEES IT, PRECISELY. There is a gate that looks at exactly these
 * leaves -- `.ci/scripts/quality/check_i18n_value_types.py` -- and it compares TYPES.
 * `false` and `true` are both booleans, so it passes, and it passes for the same reason a
 * `0` diverging to `9999` would pass. Every other i18n gate is worse placed still: they
 * compare a locale against English and REPORT VALUES THAT MATCH (untranslated text), which
 * is the exact opposite predicate. A boolean that matches English is correct; a boolean
 * that differs is the bug. No instrument in the repo asked that question.
 *
 * WHAT COUNTS AS CONFIG, AND WHY THE LINE IS DRAWN AT "NOT A STRING". A string is
 * translatable by definition and MUST be allowed to differ -- that is the whole point of a
 * locale file, and a gate that flagged a differing string would fire on every correctly
 * translated key in the repo. A boolean, a number and a null are not translatable in any
 * language: they are feature flags, reference indices, counts and thresholds that were
 * copied along with the text. So the predicate is narrow and total: every non-string leaf
 * in English must be byte-equal in every locale.
 *
 * THE SECOND CONTROL IS AS IMPORTANT AS THE FIRST. The selftest plants a boolean flip and
 * requires a finding, AND plants a locale where only a translated string differs and
 * requires silence. Without the second, the first version of this gate would have reported
 * roughly 6,600 findings per locale and been switched off within a day.
 *
 * Usage:
 *   tsx scripts/check-locale-config-divergence.ts [--root <dir>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { isSiteLocale, SITE_LOCALES } from '@rediacc/locales';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/**
 * Every locale root in the repo, with the layout its tree actually has. Same table shape
 * as scripts/check-i18n-cross-locale.ts, and for the same reason: a root that is not in
 * the table is indistinguishable in the output from a root that is clean.
 *
 * The three non-www roots hold ZERO non-string leaves today, so they contribute no
 * comparisons. They are scanned anyway: the day someone adds a flag to the CLI catalogs is
 * the day this gate needs to already be watching them, and a root added later is a root
 * that was unwatched in between.
 */
const LOCALE_ROOTS: readonly { root: string; layout: 'dir' | 'flat' }[] = [
  { root: 'packages/www/src/i18n/translations', layout: 'flat' },
  { root: 'packages/cli/src/i18n/locales', layout: 'dir' },
  { root: 'private/account/web/src/i18n/locales', layout: 'dir' },
  { root: 'private/account/src/i18n/locales', layout: 'dir' },
];

const SOURCE_LOCALE = 'en';

type Primitive = string | number | boolean | null;

export interface Divergence {
  root: string;
  locale: string;
  /** The ENGLISH catalog the key was read from. Findings group by this, so one diverging
   *  key reads as one entry with twelve locales under it rather than twelve entries. */
  sourceFile: string;
  /** The locale catalog that disagrees. */
  file: string;
  key: string;
  english: Primitive;
  actual: Primitive;
}

/** Flatten to dotted keys keeping EVERY primitive leaf, arrays included as `.0`, `.1`. */
function flattenPrimitives(
  value: unknown,
  prefix = '',
  out: Record<string, Primitive> = {}
): Record<string, Primitive> {
  if (Array.isArray(value)) {
    value.forEach((v, i) => flattenPrimitives(v, prefix ? `${prefix}.${i}` : String(i), out));
  } else if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      flattenPrimitives(v, prefix ? `${prefix}.${k}` : k, out);
    }
  } else {
    out[prefix] = value as Primitive;
  }
  return out;
}

const readJson = (file: string): unknown => JSON.parse(fs.readFileSync(file, 'utf-8'));

/** locale -> (catalog file name -> absolute path). Sidecar dotfiles are never locales. */
function localeCatalogs(root: string, layout: 'dir' | 'flat'): Map<string, Map<string, string>> {
  const out = new Map<string, Map<string, string>>();
  for (const entry of fs.readdirSync(root).sort()) {
    if (entry.startsWith('.')) continue;
    const abs = path.join(root, entry);
    if (layout === 'flat') {
      if (!entry.endsWith('.json')) continue;
      out.set(entry.slice(0, -'.json'.length), new Map([['catalog.json', abs]]));
    } else {
      if (!fs.statSync(abs).isDirectory()) continue;
      const files = new Map<string, string>();
      for (const f of fs.readdirSync(abs).sort()) {
        if (f.endsWith('.json')) files.set(f, path.join(abs, f));
      }
      out.set(entry, files);
    }
  }
  return out;
}

export function findConfigDivergence(
  root: string,
  layout: 'dir' | 'flat'
): { findings: Divergence[]; compared: number } {
  if (!fs.existsSync(root)) return { findings: [], compared: 0 };
  const catalogs = localeCatalogs(root, layout);

  // The locale universe is @rediacc/locales, never readdirSync. A stray directory would
  // otherwise be compared against English and reported as twelve divergences, and a
  // missing one would be silently skipped -- the second is the dangerous half.
  for (const locale of catalogs.keys()) {
    if (!isSiteLocale(locale)) {
      throw new Error(
        `"${locale}" under ${root} is not a site locale.\n` +
          `Site locales come from @rediacc/locales: ${SITE_LOCALES.join(', ')}.`
      );
    }
  }
  const absent = SITE_LOCALES.filter((l) => !catalogs.has(l));
  if (absent.length > 0) {
    throw new Error(
      `${root} is missing ${absent.length} site locale(s): ${absent.join(', ')}.\n` +
        `Zero comparisons for a locale reads exactly like zero divergences for it.`
    );
  }

  const english = catalogs.get(SOURCE_LOCALE);
  if (!english) throw new Error(`${root} has no ${SOURCE_LOCALE} catalog.`);

  const findings: Divergence[] = [];
  let compared = 0;

  for (const [fileName, enPath] of english) {
    const enFlat = flattenPrimitives(readJson(enPath));
    // STRINGS ARE TRANSLATABLE AND ARE NOT COMPARED. This one line is the whole
    // false-positive story; see the header.
    const config = Object.entries(enFlat).filter(([, v]) => typeof v !== 'string');
    if (config.length === 0) continue;

    for (const [locale, files] of catalogs) {
      if (locale === SOURCE_LOCALE) continue;
      const localePath = files.get(fileName);
      // A missing catalog file is check-translation-completeness's finding, not this
      // gate's; reporting it here would double-report one defect in two voices.
      if (!localePath) continue;
      const localeFlat = flattenPrimitives(readJson(localePath));
      for (const [key, enValue] of config) {
        if (!(key in localeFlat)) continue;
        compared++;
        if (localeFlat[key] !== enValue) {
          findings.push({
            root,
            locale,
            sourceFile: path.basename(enPath),
            file: path.basename(localePath),
            key,
            english: enValue,
            actual: localeFlat[key],
          });
        }
      }
    }
  }
  return { findings, compared };
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

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'locale-config-'));
  const CLEAN = {
    announcement: { enabled: false, text: 'Start free for 14 days' },
    hero: { title: 'Recovery in seconds', refs: [1, 2, 3] },
  };
  const TRANSLATED = {
    announcement: { enabled: false, text: 'Starten Sie 14 Tage kostenlos' },
    hero: { title: 'Wiederherstellung in Sekunden', refs: [1, 2, 3] },
  };
  const write = (locale: string, o: unknown) =>
    fs.writeFileSync(path.join(root, `${locale}.json`), JSON.stringify(o));
  const reseed = () => {
    for (const l of SITE_LOCALES) write(l, l === 'en' ? CLEAN : TRANSLATED);
  };
  const scan = () => findConfigDivergence(root, 'flat');

  reseed();
  const clean = scan();
  // PLANT TWO, and it is the one that decides whether this gate survives contact with the
  // repo: every catalog above carries a fully translated string for every key, and the
  // gate must be silent. A gate that reported those would fire ~6,600 times per locale.
  check(
    'translated strings are NOT reported (control)',
    clean.findings.length === 0,
    JSON.stringify(clean.findings.slice(0, 3))
  );
  check(
    'the clean run actually compared something',
    clean.compared > 0,
    `compared=${clean.compared}`
  );

  // PLANT ONE: the real defect, byte for byte.
  write('de', {
    ...TRANSLATED,
    announcement: { enabled: true, text: TRANSLATED.announcement.text },
  });
  const flipped = scan();
  check(
    'a boolean flipped away from English is reported',
    flipped.findings.length === 1 &&
      flipped.findings[0].locale === 'de' &&
      flipped.findings[0].sourceFile === 'en.json' &&
      flipped.findings[0].key === 'announcement.enabled' &&
      flipped.findings[0].english === false &&
      flipped.findings[0].actual === true,
    JSON.stringify(flipped.findings)
  );
  reseed();

  write('fr', { ...TRANSLATED, hero: { title: TRANSLATED.hero.title, refs: [1, 2, 9] } });
  const numeric = scan();
  check(
    'a number diverging inside an array is reported',
    numeric.findings.length === 1 && numeric.findings[0].key === 'hero.refs.2',
    JSON.stringify(numeric.findings)
  );
  reseed();

  const throwsWith = (fn: () => unknown): unknown => {
    try {
      fn();
      return null;
    } catch (e) {
      return e;
    }
  };
  fs.writeFileSync(path.join(root, 'nl.json'), JSON.stringify(TRANSLATED));
  check('a catalog that is not a site locale is a hard error', throwsWith(scan) instanceof Error);
  fs.rmSync(path.join(root, 'nl.json'));

  fs.rmSync(path.join(root, 'ko.json'));
  check(
    'a missing site locale is a hard error, not a silent skip',
    throwsWith(scan) instanceof Error
  );

  fs.rmSync(root, { recursive: true, force: true });
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
  const roots = LOCALE_ROOTS.map((r) => ({ ...r, abs: path.join(base, r.root) })).filter((r) =>
    fs.existsSync(r.abs)
  );
  if (roots.length === 0) {
    console.error(
      `✗ Refusing to run: none of the ${LOCALE_ROOTS.length} locale roots exist under ${base}.`
    );
    process.exit(1);
  }

  let findings: Divergence[] = [];
  let compared = 0;
  try {
    for (const r of roots) {
      const res = findConfigDivergence(r.abs, r.layout);
      findings = findings.concat(res.findings.map((f) => ({ ...f, root: r.root })));
      compared += res.compared;
    }
  } catch (e) {
    console.error(`✗ ${(e as Error).message}`);
    process.exit(1);
  }

  // FLOOR. "Zero divergences" and "zero leaves compared" print the same checkmark unless
  // the count is asserted. There are 721 non-string leaves in the www catalogs alone, so
  // a run that compares nothing means the flattener or the roots have broken.
  if (compared === 0) {
    console.error(
      `✗ Refusing to run: ${roots.length} locale root(s) yielded ZERO non-string leaves to\n` +
        `  compare. A gate that compared nothing must not report that nothing diverged.`
    );
    process.exit(1);
  }

  if (findings.length === 0) {
    console.log(
      `✓ No config divergence: ${compared} non-string leaf comparison(s) across ${roots.length} locale root(s).`
    );
    return;
  }

  console.error(
    `✗ ${findings.length} non-string value(s) differ from English across ${compared} comparison(s):\n`
  );
  const byKey = new Map<string, Divergence[]>();
  for (const f of findings) {
    const k = `${f.root}/${f.sourceFile}:${f.key}`;
    byKey.set(k, [...(byKey.get(k) ?? []), f]);
  }
  for (const [key, list] of [...byKey].sort((a, b) => b[1].length - a[1].length)) {
    console.error(`  ${key}`);
    console.error(`    English: ${JSON.stringify(list[0].english)}`);
    for (const f of list.slice(0, 12))
      console.error(`    ${f.locale}: ${JSON.stringify(f.actual)}`);
    if (list.length > 12) console.error(`    ... and ${list.length - 12} more locale(s)`);
  }
  console.error(
    '\nThese are not translations. A boolean, a number or a null carries the same meaning in\n' +
      'every language, so a locale that disagrees with English is a config fork nobody chose.\n' +
      'Decide the value in en.json and copy it to every locale.'
  );
  process.exit(1);
}

main();

#!/usr/bin/env tsx
/**
 * Catch German text that was copied verbatim into a locale that is not German.
 *
 * WHY THIS EXISTS ALONGSIDE check-i18n-cross-locale.ts. That gate identifies the
 * LANGUAGE of a string from function words, which is the right instrument for
 * telling French from German. But it can only look at locales it has a function-word
 * list for (`if (!STOPWORDS[locale]) continue`), and that list covers de/fr/es/it/pt/tr
 * only. Arabic, Japanese, Korean, Russian, Chinese and Estonian are skipped outright,
 * and those are exactly where the damage was: 94-95 German values sitting in each of
 * account-web's ar, ja, ru and zh. No gate in the repo could see them, because every
 * other i18n check compares a locale against ENGLISH and German is not English.
 *
 * THE SIGNAL HERE IS EQUALITY, NOT VOCABULARY. A value that is byte-identical to the
 * German value for the same key, and differs from the English one, was copied from
 * German. That predicate alone is far too loose (699 hits, nearly all junk: "200 GB",
 * "2,4 TB", "Rediacc (btrfs CoW)"), so three filters run on top of it, each one
 * measured against the real tree rather than reasoned about:
 *
 *   1. SUBSTANCE. After stripping {{placeholders}}, HTML tags and URLs the value must
 *      hold at least two alphabetic words of three letters or more. Kills every unit,
 *      version number and bare-token string.
 *   2. NOT SHARED BY THE CROWD. A value that most other locales also carry is a
 *      language-neutral string, not a leak: a citation ("Veeam Data Protection Trends
 *      Report 2021 [1]" is identical in all eleven non-English locales), a product
 *      name, a command line. Real contamination is shared only with the other
 *      locales that were contaminated from the same source.
 *   3. LANGUAGE EVIDENCE, chosen per script. For a locale written in a non-Latin
 *      script, a value containing not one character of that script IS the evidence:
 *      an Arabic string with no Arabic in it is not Arabic. For a Latin-script locale
 *      the value must carry German markers (function words, ß, the German opening
 *      quote, umlauted or German-suffixed words), because Latin-script neighbours
 *      legitimately share whole strings.
 *
 * Measured on the tree at authoring time: 379 findings, all four contaminated
 * account-web locales, zero findings in packages/www and packages/cli. Every filter
 * above was added because dropping it produced false positives that are listed by
 * name in this comment, not because it seemed prudent.
 *
 * THE BASELINE ONLY SHRINKS. Known contamination is listed in the baseline file so
 * the gate lands green and fails on anything NEW. A baseline entry that is no longer
 * contaminated is a hard ERROR, not a silent pass, so fixing a key forces its removal
 * and the file cannot rot into a permanent suppression list.
 *
 * Usage:
 *   tsx scripts/check-locale-de-contamination.ts [--root <dir>] [--baseline <file>]
 *   tsx scripts/check-locale-de-contamination.ts --selftest
 *   tsx scripts/check-locale-de-contamination.ts --write-baseline   (drain/reseed)
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { DEFAULT_LOCALE, isSiteLocale, SITE_LOCALES } from '@rediacc/locales';

import {
  baselineAdditions,
  renderRefusal,
  sharedSelftestCases,
  writeBaselineVerdict,
} from './lib/shrink-only-baseline.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const DEFAULT_BASELINE = 'scripts/data/locale-de-contamination-baseline.json';

/** Locale trees in this repo. `dir` = one directory per locale; `flat` = one file per locale. */
const LOCALE_ROOTS: { root: string; layout: 'dir' | 'flat' }[] = [
  { root: 'packages/www/src/i18n/translations', layout: 'flat' },
  { root: 'packages/cli/src/i18n/locales', layout: 'dir' },
  { root: 'private/account/web/src/i18n/locales', layout: 'dir' },
  { root: 'private/account/src/i18n/locales', layout: 'dir' },
];

const SOURCE_LOCALE = 'de';
const ENGLISH_LOCALE = DEFAULT_LOCALE;

/**
 * German function words. Same role as check-i18n-cross-locale's list, but this one is
 * only ever asked "is this German?", never "which of twelve languages is this?", so it
 * can afford to be broader without the discriminative-overlap pruning that file needs.
 */
const GERMAN_FUNCTION_WORDS = new Set([
  'aber',
  'alle',
  'als',
  'auf',
  'aus',
  'bei',
  'beim',
  'bereits',
  'bitte',
  'das',
  'dass',
  'dem',
  'den',
  'der',
  'des',
  'diese',
  'dieser',
  'dieses',
  'durch',
  'ein',
  'eine',
  'einen',
  'einer',
  'eines',
  'für',
  'haben',
  'hat',
  'hier',
  'ihre',
  'ihren',
  'ist',
  'kann',
  'kein',
  'keine',
  'können',
  'muss',
  'müssen',
  'nach',
  'nicht',
  'noch',
  'nur',
  'oder',
  'sich',
  'sie',
  'sind',
  'über',
  'und',
  'unter',
  'vom',
  'von',
  'wenn',
  'werden',
  'wird',
  'wurde',
  'wurden',
  'zum',
  'zur',
]);

/** German noun/verb endings. Long words only, so Romance cognates in -ion do not trip it. */
const GERMAN_SUFFIX = /(ungen|ung|keit|heit|schaft|lich|ieren|iert|isch)$/i;

/**
 * The writing system each non-Latin locale is supposed to use. A value in one of these
 * locales that contains none of its own script cannot be a translation into it.
 */
const NATIVE_SCRIPT: Record<string, RegExp> = {
  ar: /[؀-ۿݐ-ݿ]/,
  ja: /[぀-ヿ一-鿿]/,
  ko: /[가-힯ᄀ-ᇿ]/,
  ru: /[Ѐ-ӿ]/,
  zh: /[一-鿿]/,
};

// A typo here is silent otherwise: `NATIVE_SCRIPT.jp` would never match the `ja` file, so
// `ja` would fall to the German-marker path and lose its strongest signal. Checked at
// module load against the one declaration of the locale set.
for (const key of Object.keys(NATIVE_SCRIPT)) {
  if (!isSiteLocale(key)) {
    throw new Error(
      `NATIVE_SCRIPT names "${key}", which is not a site locale. ` +
        `Known: ${SITE_LOCALES.join(', ')}.`
    );
  }
}

export type Finding = { root: string; locale: string; file: string; key: string; value: string };
type LocaleData = Record<string, Record<string, string>>;

function flatten(
  obj: unknown,
  prefix = '',
  out: Record<string, string> = {}
): Record<string, string> {
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const q = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === 'object') flatten(v, q, out);
      else if (typeof v === 'string') out[q] = v;
    }
  }
  return out;
}

/** Drop the parts of a value that carry no language: placeholders, markup, URLs. */
function textOf(value: string): string {
  return value
    .replace(/\{\{[^}]*\}\}/g, ' ')
    .replace(/<[^>]*>/g, ' ')
    .replace(/https?:\/\/\S+/g, ' ');
}

function latinWords(text: string): string[] {
  return text.split(/[^A-Za-zÀ-ÖØ-öø-ÿ]+/).filter((w) => w.length >= 3);
}

function looksGerman(text: string): boolean {
  // ß and the German opening quote „ are German and nothing else we ship. The English
  // curly quote “ deliberately is NOT in here: it appears in English-language citations
  // that every locale carries verbatim, and including it produced exactly that false
  // positive in es, fr and tr.
  if (/[ß„]/.test(text)) return true;
  const words = latinWords(text);
  if (words.some((w) => GERMAN_FUNCTION_WORDS.has(w.toLowerCase()))) return true;
  if (words.some((w) => w.length >= 6 && /[äöüÄÖÜ]/.test(w))) return true;
  return words.some((w) => w.length >= 7 && GERMAN_SUFFIX.test(w));
}

function readLocale(root: string, layout: 'dir' | 'flat', locale: string): LocaleData {
  const parse = (file: string): Record<string, string> | null => {
    try {
      return flatten(JSON.parse(fs.readFileSync(file, 'utf-8')));
    } catch (e) {
      // A malformed locale file is another gate's problem. Anything else -- a bad
      // regex, a missing helper -- is a bug HERE, and swallowing it would make this
      // gate report zero findings while looking healthy.
      if (e instanceof SyntaxError) return null;
      throw e;
    }
  };
  if (layout === 'flat') {
    const file = path.join(root, `${locale}.json`);
    if (!fs.existsSync(file)) return {};
    const flat = parse(file);
    return flat ? { [`${locale}.json`]: flat } : {};
  }
  const dir = path.join(root, locale);
  if (!fs.existsSync(dir)) return {};
  const out: LocaleData = {};
  for (const name of fs.readdirSync(dir)) {
    if (!name.endsWith('.json')) continue;
    const flat = parse(path.join(dir, name));
    if (flat) out[name] = flat;
  }
  return out;
}

/**
 * The locales present in a root, cross-checked against `@rediacc/locales`.
 *
 * Deriving the set from `readdirSync` alone means the gate scans whatever is on disk and
 * cannot tell a deliberate subset from a stale copy or a typo. The declared set is the
 * one in `packages/locales`, which the rest of the repo already builds against, so a
 * fourteenth locale added there turns every root that lacks it red immediately.
 */
function listLocales(root: string, layout: 'dir' | 'flat'): string[] {
  const found =
    layout === 'flat'
      ? fs
          .readdirSync(root)
          // Dot-prefixed files are sidecar manifests, not locales.
          // packages/www/src/i18n/translations holds `.naturalized-hashes.json` and
          // `.translation-hashes.json`, 2.2 MB of CRC data that this gate was reading and
          // flattening as if they were two extra locales on every run. Harmless in
          // findings -- no key of theirs matches a German key -- but they counted towards
          // `targets`, which is the DENOMINATOR of the crowd filter, so the exemption
          // threshold was computed against 14 locales where 12 exist.
          .filter((f) => !f.startsWith('.') && f.endsWith('.json'))
          .map((f) => f.slice(0, -'.json'.length))
          .sort()
      : fs
          .readdirSync(root)
          .filter((d) => !d.startsWith('.') && fs.statSync(path.join(root, d)).isDirectory())
          .sort();

  for (const locale of found) {
    if (!isSiteLocale(locale)) {
      throw new Error(
        `${root} holds "${locale}", which is not a site locale. ` +
          `Known: ${SITE_LOCALES.join(', ')}. Declare it in packages/locales/index.js, ` +
          `or remove it from the locale root.`
      );
    }
  }
  const present = new Set(found);
  const absent = SITE_LOCALES.filter((l) => !present.has(l));
  if (absent.length > 0) {
    throw new Error(
      `${root} is missing ${absent.length} site locale(s): ${absent.join(', ')}. ` +
        `The gate would compare them against nothing and report no contamination, which ` +
        `is the same checkmark as finding none.`
    );
  }
  return found;
}

export function findGermanContamination(root: string, layout: 'dir' | 'flat'): Finding[] {
  if (!fs.existsSync(root)) return [];
  const locales = listLocales(root, layout);
  if (!locales.includes(SOURCE_LOCALE) || !locales.includes(ENGLISH_LOCALE)) return [];

  const data: Record<string, LocaleData> = Object.fromEntries(
    locales.map((l) => [l, readLocale(root, layout, l)])
  );
  const german = data[SOURCE_LOCALE] ?? {};
  const english = data[ENGLISH_LOCALE] ?? {};
  // In the flat layout each locale's keys live under its OWN filename, so the German
  // file for a www key is de.json while the target's is ar.json. Normalise that here,
  // otherwise every flat-layout lookup misses and the gate silently finds nothing.
  const fileIn = (locale: string, file: string): string =>
    layout === 'flat' ? `${locale}.json` : file;

  const targets = locales.filter((l) => l !== SOURCE_LOCALE && l !== ENGLISH_LOCALE);
  const findings: Finding[] = [];

  for (const locale of targets) {
    const native = NATIVE_SCRIPT[locale];
    for (const [file, entries] of Object.entries(data[locale] ?? {})) {
      for (const [key, value] of Object.entries(entries)) {
        const germanValue = german[fileIn(SOURCE_LOCALE, file)]?.[key];
        if (germanValue === undefined || value !== germanValue) continue;
        const englishValue = english[fileIn(ENGLISH_LOCALE, file)]?.[key];
        if (englishValue !== undefined && value === englishValue) continue;

        const text = textOf(value);
        if (latinWords(text).length < 2) continue;

        // POSITIVE LANGUAGE EVIDENCE, computed before the crowd filter so the crowd
        // filter can be conditioned on it. (Named for the predicate, not the language:
        // `german` is already the German CATALOG in this scope.)
        const isGermanText = looksGerman(text);

        // NOT SHARED BY THE CROWD -- but only for values carrying no evidence of being a
        // specific language.
        //
        // This filter was unconditional, and that hid 59 genuinely corrupted keys. Most
        // of account-web's team.json was German across ar, ja, ru and zh IDENTICALLY,
        // and "identical in four locales" is exactly what the filter reads as
        // "language-neutral string". It is the wrong reading: a citation or a product
        // name is shared because it belongs to no language, whereas shared CORRUPTION is
        // shared because one bad translation pass wrote the same German into all four.
        // The two are told apart by asking whether the value looks German -- which is
        // already computed above and was simply not consulted here.
        //
        // The exemption therefore applies only when the value is NOT identifiable German.
        // A citation ("Veeam Data Protection Trends Report 2021") still passes; a German
        // sentence in four locales no longer does.
        if (!isGermanText) {
          const shared = targets.filter(
            (o) => o !== locale && data[o]?.[fileIn(o, file)]?.[key] === value
          ).length;
          if (shared * 2 >= targets.length - 1) continue;
        }

        const contaminated = native ? !native.test(value) : isGermanText;
        if (!contaminated) continue;
        findings.push({ root, locale, file, key, value });
      }
    }
  }
  return findings;
}

const idOf = (f: Finding): string => `${f.root}|${f.locale}|${f.file}|${f.key}`;

function loadBaseline(file: string): string[] {
  if (!fs.existsSync(file)) return [];
  const parsed: unknown = JSON.parse(fs.readFileSync(file, 'utf-8'));
  if (!Array.isArray(parsed)) {
    throw new Error(`${file} must contain a JSON array of finding ids.`);
  }
  return parsed.map(String);
}

/**
 * Plant the defect and require the detector to report it, then plant each known false
 * positive and require it NOT to. Runs inline on every invocation, because a control
 * that only runs behind a flag nothing passes is not a control.
 */
function selftest(): boolean {
  const failures: string[] = [];
  const check = (name: string, actual: unknown, expected: unknown): void => {
    if (JSON.stringify(actual) === JSON.stringify(expected)) console.log(`  PASS  ${name}`);
    else {
      console.error(
        `  FAIL  ${name}\n        expected ${JSON.stringify(expected)}\n        got      ${JSON.stringify(actual)}`
      );
      failures.push(name);
    }
  };

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'locale-de-'));
  const write = (locale: string, obj: unknown): void => {
    fs.mkdirSync(path.join(root, locale), { recursive: true });
    fs.writeFileSync(path.join(root, locale, 'app.json'), JSON.stringify(obj));
  };
  const GERMAN = 'Keine Aktivität gefunden.';
  const CITE = 'Veeam Trends Report 2021';

  /**
   * All THIRTEEN site locales. The gate cross-checks each root against
   * `@rediacc/locales` now, so a fixture holding eight is a hard error rather than a
   * scan -- which is the property under test: a root missing a locale compares it
   * against nothing and reports no contamination, the same checkmark as finding none.
   */
  const NATIVE: Record<string, string> = {
    en: 'No activity found.',
    de: GERMAN,
    ar: 'لم يتم العثور على نشاط.',
    ja: 'アクティビティが見つかりません。',
    ru: 'Активность не найдена.',
    zh: '未找到活动。',
    ko: '활동을 찾을 수 없습니다.',
    fr: 'Aucune activité trouvée.',
    es: 'No se encontró actividad.',
    pt: 'Nenhuma atividade encontrada.',
    it: 'Nessuna attività trovata.',
    tr: 'Etkinlik bulunamadı.',
    et: 'Tegevusi ei leitud.',
  };
  const base: Record<string, Record<string, string>> = Object.fromEntries(
    Object.entries(NATIVE).map(([locale, empty]) => [
      locale,
      { empty, size: '200 GB', cite: locale === 'en' ? `${CITE} [1]` : CITE },
    ])
  );
  const reseed = (): void => {
    for (const [locale, obj] of Object.entries(base)) write(locale, obj);
  };
  const keys = (): string[] =>
    findGermanContamination(root, 'dir').map((f) => `${f.locale}:${f.key}`);

  reseed();
  check(
    'a clean tree of all thirteen site locales reports nothing (control)',
    findGermanContamination(root, 'dir').length,
    0
  );

  // THE PLANTED DEFECT: German dropped into the Arabic file.
  write('ar', { ...base.ar, empty: GERMAN });
  check('German text planted in the Arabic file is reported', keys(), ['ar:empty']);
  reseed();

  // Same defect in a Latin-script locale, where the script test cannot help and the
  // German-marker path has to carry it.
  write('fr', { ...base.fr, empty: GERMAN });
  check('German text planted in the French file is reported', keys(), ['fr:empty']);
  reseed();

  // SHARED CORRUPTION, which the crowd filter used to swallow whole.
  //
  // The same German value written into ar, ja, ru and zh by one bad translation pass
  // looks, to an unconditional "most locales carry this" test, exactly like a
  // language-neutral string. It is not, and the difference is measurable: this value
  // carries German function words. It hid 59 genuinely corrupted keys in account-web's
  // team.json before the filter learned to consult that evidence.
  for (const locale of ['ar', 'ja', 'ru', 'zh']) write(locale, { ...base[locale], empty: GERMAN });
  check('one German value shared by four locales is reported, not exempted as neutral', keys(), [
    'ar:empty',
    'ja:empty',
    'ru:empty',
    'zh:empty',
  ]);
  reseed();

  // The three false-positive classes that the first drafts reported, each pinned so a
  // future loosening of a filter fails here instead of in someone's review.
  check(
    'a unit shared with German is not reported (control)',
    findGermanContamination(root, 'dir').filter((f) => f.key === 'size').length,
    0
  );
  check(
    'an English citation every locale carries is not reported (control)',
    findGermanContamination(root, 'dir').filter((f) => f.key === 'cite').length,
    0
  );
  write('tr', { ...base.tr, product: 'Rediacc btrfs CoW' });
  write('de', { ...base.de, product: 'Rediacc btrfs CoW' });
  write('en', { ...base.en, product: 'Rediacc Copy-on-Write' });
  check(
    'a product name shared with German is not reported (control)',
    findGermanContamination(root, 'dir').filter((f) => f.key === 'product').length,
    0
  );
  reseed();

  // THE LOCALE SET. The universe is @rediacc/locales, never readdirSync.
  const throwsWith = (fn: () => unknown): unknown => {
    try {
      fn();
      return null;
    } catch (e) {
      return e;
    }
  };
  write('nl', { empty: 'Geen activiteit gevonden.' });
  check(
    'a directory that is not a site locale is a hard error',
    String(throwsWith(() => findGermanContamination(root, 'dir'))).includes('not a site locale'),
    true
  );
  fs.rmSync(path.join(root, 'nl'), { recursive: true, force: true });

  fs.rmSync(path.join(root, 'it'), { recursive: true, force: true });
  check(
    'a site locale with no directory is a hard error, not a silent zero-file scan',
    String(throwsWith(() => findGermanContamination(root, 'dir'))).includes(
      'missing 1 site locale(s): it'
    ),
    true
  );
  reseed();

  // Flat layout (packages/www), where the German values live in de.json rather than in
  // a same-named file. Getting this wrong finds nothing while looking healthy.
  const flatRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'locale-de-flat-'));
  const writeFlat = (locale: string, obj: unknown): void =>
    fs.writeFileSync(path.join(flatRoot, `${locale}.json`), JSON.stringify(obj));
  for (const [locale, empty] of Object.entries(NATIVE)) writeFlat(locale, { empty });
  writeFlat('ru', { empty: GERMAN });
  check(
    'the flat www layout is scanned, not silently skipped',
    findGermanContamination(flatRoot, 'flat').map((f) => `${f.locale}:${f.key}`),
    ['ru:empty']
  );

  fs.rmSync(root, { recursive: true, force: true });
  fs.rmSync(flatRoot, { recursive: true, force: true });

  // THE SHRINK-ONLY COMPOSITION RULE, shared with every other baselined gate here.
  for (const c of sharedSelftestCases()) check(c.name, c.ok, true);

  if (failures.length > 0) {
    console.error(`\n${failures.length} self-test failure(s)`);
    return false;
  }
  console.log('  check-locale-de-contamination self-test passed\n');
  return true;
}

function main(): void {
  const argv = process.argv.slice(2);
  const arg = (name: string): string | undefined => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };

  if (argv.includes('--selftest')) {
    process.exit(selftest() ? 0 : 1);
  }
  // Control first, always. Same reasoning as check-i18n-cross-locale.ts: a gate whose
  // fire-proof never runs is indistinguishable from a gate that always passes.
  if (!argv.includes('--skip-control') && !selftest()) process.exit(1);

  const base = path.resolve(arg('--root') ?? REPO_ROOT);
  const baselineFile = path.resolve(arg('--baseline') ?? path.join(base, DEFAULT_BASELINE));

  const present = LOCALE_ROOTS.map((r) => ({ ...r, abs: path.join(base, r.root) })).filter((r) =>
    fs.existsSync(r.abs)
  );
  if (present.length === 0) {
    console.error(
      `Refusing to run: none of the ${LOCALE_ROOTS.length} locale roots exist under ${base}.\n` +
        `A scan over zero locale trees would report "no contamination" while checking nothing.`
    );
    process.exit(1);
  }

  const findings = present.flatMap((r) => findGermanContamination(r.abs, r.layout));
  for (const f of findings) f.root = path.relative(base, f.root);

  if (argv.includes('--write-baseline')) {
    const ids = findings.map(idOf).sort();

    // COMPOSITION. This file's header is the one OTHER gates cite as the model for "the
    // baseline only shrinks", and it did not enforce that on the write path either: the
    // reseed below was unconditional, so a drain could shed findings, absorb a fresh one,
    // and print a smaller number. Being the precedent is exactly why it had to be fixed.
    const had = fs.existsSync(baselineFile);
    const previous = loadBaseline(baselineFile);
    const verdict = writeBaselineVerdict({
      baselineExists: had,
      firstSeedFlag: argv.includes('--first-seed'),
      additions: had ? baselineAdditions(previous, ids) : [],
    });
    if (verdict !== null) {
      console.error(
        `✗ ${renderRefusal(verdict, {
          baselineLabel: path.relative(base, baselineFile),
          noun: 'contaminated value',
          previousCount: previous.length,
          newCount: ids.length,
        })}`
      );
      process.exit(1);
    }

    fs.mkdirSync(path.dirname(baselineFile), { recursive: true });
    fs.writeFileSync(baselineFile, `${JSON.stringify(ids, null, 2)}\n`);
    console.log(
      `Wrote ${ids.length} baselined finding(s) to ${path.relative(base, baselineFile)} ` +
        `(${previous.length} before, ${previous.filter((i) => !ids.includes(i)).length} drained, 0 added).`
    );
    return;
  }

  const baseline = new Set(loadBaseline(baselineFile));
  const fresh = findings.filter((f) => !baseline.has(idOf(f)));
  const live = new Set(findings.map(idOf));
  const stale = [...baseline].filter((id) => !live.has(id));

  if (fresh.length === 0 && stale.length === 0) {
    console.log(
      `No new German contamination across ${present.length} locale root(s). ` +
        `${baseline.size} known finding(s) still baselined.`
    );
    return;
  }

  if (fresh.length > 0) {
    console.error(`${fresh.length} value(s) were copied from the German locale:\n`);
    const byLocale = new Map<string, Finding[]>();
    for (const f of fresh) {
      const k = `${f.root} / ${f.locale}`;
      byLocale.set(k, [...(byLocale.get(k) ?? []), f]);
    }
    for (const [where, list] of [...byLocale].sort((a, b) => b[1].length - a[1].length)) {
      console.error(`  ${where}  (${list.length})`);
      for (const f of list.slice(0, 5)) {
        const shown = f.value.length > 60 ? `${f.value.slice(0, 57)}...` : f.value;
        console.error(`    ${f.file}:${f.key} = ${JSON.stringify(shown)}`);
      }
      if (list.length > 5) console.error(`    ... and ${list.length - 5} more`);
    }
    console.error(
      '\nThese values are byte-identical to the German locale and differ from English.\n' +
        'Translate them from the ENGLISH source. Baselining a NEW finding is not the fix:\n' +
        `${DEFAULT_BASELINE} exists to record the backlog, not to absorb fresh breakage.`
    );
  }

  if (stale.length > 0) {
    console.error(
      `\n${stale.length} baselined finding(s) are already fixed. The baseline only shrinks,\n` +
        `so remove them: npx tsx scripts/check-locale-de-contamination.ts --write-baseline\n`
    );
    for (const id of stale.slice(0, 10)) console.error(`    ${id}`);
    if (stale.length > 10) console.error(`    ... and ${stale.length - 10} more`);
  }
  process.exit(1);
}

main();

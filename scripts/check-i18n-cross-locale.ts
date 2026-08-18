#!/usr/bin/env tsx
/**
 * Catch a locale that contains ANOTHER locale's text.
 *
 * WHY THIS IS ITS OWN GATE. Every other i18n check is a STAR: each locale is compared
 * only against English — `no-untranslated-values` (`strValue === englishValue`),
 * `cross-language-consistency` and `translation-coverage` (`sourceLanguage: 'en'`),
 * `interpolation-consistency` (`englishFile`), `scripts/check-i18n-untranslated.ts`
 * (`const SOURCE = 'en'`). Nothing ever compares two non-English locales.
 *
 * So German sitting in the French file is invisible BY CONSTRUCTION: it differs from
 * English, therefore every check passes. That is not hypothetical — it shipped. The
 * account portal had ~520 German strings spread across fr, es and tr, including
 * `admin.json:activity.customerFilterPlaceholder = "Nach Kunden-ID filtern..."` in all
 * three. All three locales were inside the enforced set the whole time, so this was never
 * a coverage problem that widening the language list would have fixed.
 *
 * HOW IT AVOIDS FALSE POSITIVES. It identifies the LANGUAGE of each string from function
 * words, rather than asking whether two locales happen to match. That distinction is not
 * academic: a first version compared values across locales and reported 136 false
 * positives on the es/pt pair alone, because Spanish and Portuguese legitimately share
 * whole strings ("cancelado", "Máquinas"), as do German and French ("Abonnement"). A
 * string is reported only when another language's function words are present AND the
 * locale's own are not — two independent signals, so a shared loanword cannot trip it.
 *
 * WHY IT COVERS ALL TWELVE LOCALES NOW. The first version carried
 * `if (!STOPWORDS[locale]) continue`, which meant ar, ja, ko, ru, zh and et were walked
 * past in silence — and that is precisely where the damage was: 379 German values sat in
 * account-web's ar, ja, ru and zh while this gate printed a checkmark. A skip is
 * indistinguishable from a pass in the output, so there is no longer a skip. Every locale
 * directory on disk must be modellable, by one of two instruments:
 *
 *   FUNCTION WORDS, for Latin-script locales (de/es/et/fr/it/pt/tr). Unchanged.
 *   WRITING SYSTEM, for ar/ja/ko/ru/zh. A stopword list is a Latin-alphabet instrument
 *     and cannot be built for these; instead, a value holding not one character of its
 *     own script is not a translation into it. Paired with the function-word signal, so
 *     a Latin product name standing alone still scores zero and is not reported.
 *
 * A locale that fits neither is a HARD ERROR naming the locale, never a skip.
 *
 * ENGLISH IS NOW A DETECTABLE SOURCE TOO. There was no `en` stopword list, so English
 * left sitting in a translated locale — the ordinary residue of a half-finished
 * translation pass — was invisible by construction, the same shape of blindness the
 * missing locales had.
 *
 * Usage:
 *   tsx scripts/check-i18n-cross-locale.ts [--root <dir>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { DEFAULT_LOCALE, isSiteLocale, SITE_LOCALES } from '@rediacc/locales';
import {
  assertDetectionCoverage,
  DISCRIMINATIVE,
  flatten,
  identify,
  NATIVE_SCRIPT,
  norm,
  STOPWORDS,
  stripNonLanguage,
  UnmodelledLocaleError,
} from './lib/language-detect.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/**
 * Locale roots to scan, each with the shape its tree actually has.
 *
 * `dir`  -- one DIRECTORY per locale, holding several .json files. Three of the four.
 * `flat` -- one FILE per locale (`en.json`, `de.json`, ...). This is packages/www.
 *
 * WHY packages/www WAS MISSING, AND WHY THAT WAS INVISIBLE. This table used to name the
 * cli and account trees only, so the single largest locale tree in the repo -- 13 catalogs
 * of roughly 6,600 leaves each -- was never cross-checked at all. Nothing reported that:
 * the gate walked the roots it was given, found them clean, and printed a checkmark. A
 * root that is not in the table is indistinguishable in the output from a root that is
 * clean, which is the same shape as the `if (!STOPWORDS[locale]) continue` skip this file
 * already removed once. The layout difference is why it was easy to leave out and is now
 * modelled rather than worked around.
 */
const LOCALE_ROOTS: readonly { root: string; layout: 'dir' | 'flat' }[] = [
  { root: 'packages/cli/src/i18n/locales', layout: 'dir' },
  { root: 'private/account/web/src/i18n/locales', layout: 'dir' },
  { root: 'private/account/src/i18n/locales', layout: 'dir' },
  { root: 'packages/www/src/i18n/translations', layout: 'flat' },
];

const SOURCE_LOCALE = DEFAULT_LOCALE;
/** Short strings carry too few function words to identify a language from. */
const MIN_LENGTH = 12;

type Finding = {
  root: string;
  locale: string;
  detected: string;
  file: string;
  key: string;
  value: string;
};

/**
 * A locale directory on disk that is not a site locale. Thrown, never skipped.
 *
 * The locale universe is `@rediacc/locales`, not whatever `readdirSync` happens to
 * return. A directory outside that set is either a typo or a locale someone added
 * without declaring it, and both must be loud: the gate would otherwise judge it with
 * whatever detection data it happened to have, or none.
 */
class UnknownLocaleDirError extends Error {
  constructor(
    readonly locale: string,
    readonly root: string
  ) {
    super(
      `Directory "${locale}" under ${root} is not a site locale.\n` +
        `Site locales come from @rediacc/locales: ${SITE_LOCALES.join(', ')}.\n` +
        `If this is a new locale, declare it in packages/locales/index.js (and index.d.ts) ` +
        `and give it detection data here. If it is not a locale, it does not belong in a ` +
        `locale root.`
    );
    this.name = 'UnknownLocaleDirError';
  }
}

/** A site locale whose directory is missing from a root the gate is scanning. */
class MissingLocaleDirError extends Error {
  constructor(
    readonly locales: string[],
    readonly root: string
  ) {
    super(
      `${root} is missing a directory for ${locales.length} site locale(s): ${locales.join(', ')}.\n` +
        `The gate would scan zero files for them and report nothing, which is the same ` +
        `checkmark as finding nothing. Add the directory, or remove the locale from ` +
        `packages/locales/index.js.`
    );
    this.name = 'MissingLocaleDirError';
  }
}

/**
 * Every locale in a root, with the files that belong to it. One function for both
 * layouts, so the locale-set cross-check below cannot be accidentally applied to only
 * one of them.
 */
function localeFiles(root: string, layout: 'dir' | 'flat'): Map<string, string[]> {
  const out = new Map<string, string[]>();
  // Dotfiles are sidecars, never locales: packages/www/src/i18n/translations carries
  // `.translation-hashes.json`, `.naturalized-hashes.json` and a `.lock` beside the 13
  // catalogs. The exclusion is narrow ON PURPOSE -- a locale code is two letters and can
  // never begin with a dot, so this cannot hide one, while a blanket "ignore what I do
  // not recognise" would defeat the UnknownLocaleDirError below.
  const isSidecar = (entry: string) => entry.startsWith('.');
  if (layout === 'flat') {
    for (const entry of fs.readdirSync(root).sort()) {
      if (isSidecar(entry) || !entry.endsWith('.json')) continue;
      out.set(entry.slice(0, -'.json'.length), [path.join(root, entry)]);
    }
    return out;
  }
  for (const entry of fs.readdirSync(root).sort()) {
    if (isSidecar(entry) || !fs.statSync(path.join(root, entry)).isDirectory()) continue;
    out.set(
      entry,
      fs
        .readdirSync(path.join(root, entry))
        .filter((f) => f.endsWith('.json'))
        .map((f) => path.join(root, entry, f))
    );
  }
  return out;
}

export function findCrossLocaleContamination(
  root: string,
  layout: 'dir' | 'flat' = 'dir'
): Finding[] {
  if (!fs.existsSync(root)) return [];
  const byLocale = localeFiles(root, layout);
  const locales = [...byLocale.keys()];

  // Cross-check the tree against the DECLARED locale set, in both directions. Deriving
  // the universe from readdirSync alone is how a gate ends up quietly scanning whatever
  // happens to be on disk: a stray directory gets judged with no detection data, and a
  // declared locale with no directory gets scanned zero times and reports nothing.
  for (const locale of locales) {
    if (!isSiteLocale(locale)) throw new UnknownLocaleDirError(locale, root);
  }
  const present = new Set(locales);
  const absent = SITE_LOCALES.filter((l) => !present.has(l));
  if (absent.length > 0) throw new MissingLocaleDirError([...absent], root);

  const findings: Finding[] = [];
  for (const locale of locales) {
    if (locale === SOURCE_LOCALE) continue;
    // Coverage itself was asserted at startup against @rediacc/locales, so by here every
    // site locale has one instrument or the other and there is no skip left to take.
    const native = NATIVE_SCRIPT[locale];
    for (const abs of byLocale.get(locale) ?? []) {
      const file = path.basename(abs);
      let flat: Record<string, string>;
      try {
        flat = flatten(JSON.parse(fs.readFileSync(abs, 'utf-8')));
      } catch (e) {
        // ONLY a malformed locale file is another gate's problem. Anything else — a
        // missing helper, a bad regex — is a bug in THIS file, and swallowing it makes
        // the gate silently report zero findings. That exact mistake happened here.
        if (e instanceof SyntaxError) continue;
        throw e;
      }
      for (const [key, value] of Object.entries(flat)) {
        if (value.length < MIN_LENGTH) continue;
        // A bibliographic citation is a VERBATIM quotation of a source document, and
        // scholarly convention keeps the title in the language it was published in.
        // "Verizon, \"2024 Data Breach Investigations Report\"" sitting in zh.json is
        // correct, not contamination, and translating it would make the source
        // unfindable. 1,047 of this gate's 1,060 findings were exactly this, which is
        // enough noise to get the whole gate suppressed by the next session that meets
        // it. The exemption is deliberately structural (the citation branch) rather
        // than heuristic, and it withdraws ONLY the identical-to-English signal: a
        // citation carrying a THIRD language's function words still fires, which the
        // control below pins.
        const text = stripNonLanguage(value);
        const id = identify(text);
        // Narrowed to the ENGLISH case only: an English-language source quoted in a
        // reference list is correct. A citation that has picked up GERMAN function
        // words in the French file is still contamination and still fires, which is
        // what keeps this from being a blanket hole in the citation branch.
        if (id && id.lang === 'en' && isCitationKey(key)) continue;
        // SIGNAL ONE, for every locale: another language's function words are present.
        // Two of them, so a single shared loanword cannot trip it.
        if (!id || id.lang === locale || id.score < 2) continue;
        // SIGNAL TWO, chosen per script. Both forms answer the same question — "is any
        // of this locale's own language actually here?" — and requiring the answer to be
        // no is what keeps a cognate, a loanword or a Latin product name from firing.
        if (native) {
          // A value written in the locale's own script is a translation into it, whatever
          // Latin words it also carries. A Chinese string naming "Rediacc" is Chinese.
          if (native.test(text)) continue;
        } else {
          const words = new Set(norm(text).split(/[^a-z]+/));
          const own = [...(DISCRIMINATIVE[locale] ?? [])].filter((w) => words.has(norm(w))).length;
          if (own > 0) continue;
        }
        findings.push({
          root,
          locale,
          detected: id.lang,
          file,
          key,
          value: value.length > 60 ? `${value.slice(0, 57)}...` : value,
        });
      }
    }
  }
  return findings;
}

/**
 * A reference-list entry: `...references.items.<n>.<field>`. Structural on purpose,
 * because "looks like a citation" heuristics (a year, a quoted title, a publisher)
 * match ordinary marketing copy too.
 */
export function isCitationKey(key: string): boolean {
  return /(^|\.)references\.items\.\d+(\.|$)/.test(key);
}

function selftest(): void {
  const failures: string[] = [];
  const check = (name: string, actual: unknown, expected: unknown) => {
    if (JSON.stringify(actual) === JSON.stringify(expected)) console.log(`  PASS  ${name}`);
    else {
      console.error(
        `  FAIL  ${name}\n        expected ${JSON.stringify(expected)}\n        got      ${JSON.stringify(actual)}`
      );
      failures.push(name);
    }
  };

  const GERMAN = 'Bitte wählen Sie eine Option aus der Liste';
  const FRENCH = 'Veuillez choisir une option dans la liste pour vous';
  const SPANISH = 'Por favor elija una de las opciones para este cliente';
  const PORTUGUESE = 'Por favor escolha uma das opcoes para este cliente';
  const ENGLISH = 'Please choose an option from the list of machines';

  /**
   * One fixture carrying ALL THIRTEEN site locales, correctly translated.
   *
   * It has to be all thirteen: the gate now cross-checks the tree against
   * `@rediacc/locales` in both directions, so a fixture holding five locales is a
   * MissingLocaleDirError rather than a scan. That is the property under test, not an
   * inconvenience — a partial tree is exactly the shape that used to scan nothing and
   * report a checkmark.
   */
  const CLEAN: Record<string, string> = {
    en: ENGLISH,
    de: GERMAN,
    es: SPANISH,
    fr: FRENCH,
    ja: 'リストからマシンを選択してください',
    ar: 'الرجاء اختيار خيار من قائمة الأجهزة',
    ru: 'Пожалуйста, выберите вариант из списка машин',
    tr: 'Lütfen makine listesinden bir seçenek seçin',
    zh: '请从机器列表中选择一个选项',
    et: 'Palun vali nimekirjast üks masin, kõik seaded salvestatakse',
    ko: '목록에서 시스템을 선택하십시오',
    pt: PORTUGUESE,
    it: 'Si prega di scegliere una delle opzioni per questo cliente',
  };

  /** `throwsWith`, bound to the flat fixture. Declared here because the flat cases run
   *  before the generic helper below it. */
  let flatRootForThrow = '';
  const throwsWithFlat = (): unknown => {
    try {
      findCrossLocaleContamination(flatRootForThrow, 'flat');
      return null;
    } catch (e) {
      return e;
    }
  };

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'i18n-cross-'));
  const write = (l: string, o: unknown) => {
    fs.mkdirSync(path.join(root, l), { recursive: true });
    fs.writeFileSync(path.join(root, l, 'app.json'), JSON.stringify(o));
  };
  const reseed = () => {
    for (const [l, v] of Object.entries(CLEAN)) write(l, { pick: v });
  };
  const pairs = () => findCrossLocaleContamination(root).map((f) => `${f.locale}<-${f.detected}`);

  reseed();
  check(
    'all thirteen site locales, correctly translated, report nothing (control)',
    findCrossLocaleContamination(root).length,
    0
  );

  // ---------------------------------------------------------------------------------
  // Latin-script detection: function words. The original bug was German in the French
  // file, invisible to every other gate because it is not English.
  // ---------------------------------------------------------------------------------
  write('fr', { pick: GERMAN });
  check('German text sitting in the French file is reported', pairs(), ['fr<-de']);
  reseed();

  // Control: es and pt legitimately share near-identical strings. The first version of
  // this gate reported 136 of these; it must report none. Both are in CLEAN already, so
  // the clean-tree control above covers it — this pins the specific pair.
  check(
    'es/pt near-identical strings are not reported (control)',
    findCrossLocaleContamination(root).filter((f) => f.locale === 'pt' || f.locale === 'es').length,
    0
  );

  // Citations: an English source quoted in a reference list is correct and must not
  // fire, but the exemption must not become a hiding place for a third language.
  reseed();
  write('fr', { pick: CLEAN.fr, references: { items: [{ text: ENGLISH }] } });
  check(
    'an ENGLISH citation in the French file is not reported (control)',
    findCrossLocaleContamination(root).filter((f) => f.locale === 'fr').length,
    0
  );
  reseed();
  write('fr', { pick: CLEAN.fr, references: { items: [{ text: GERMAN }] } });
  check(
    'a GERMAN citation in the French file IS still reported',
    findCrossLocaleContamination(root)
      .filter((f) => f.locale === 'fr')
      .map((f) => f.detected),
    ['de']
  );
  reseed();
  write('fr', { pick: ENGLISH, references: { items: [{ text: ENGLISH }] } });
  check(
    'the exemption does NOT cover a non-citation sibling',
    findCrossLocaleContamination(root).filter(
      (f) => f.locale === 'fr' && !f.key.includes('references')
    ).length,
    1
  );
  reseed();

  write('fr', { pick: ENGLISH });
  check('English mash in the French file is reported', pairs(), ['fr<-en']);
  reseed();

  // ---------------------------------------------------------------------------------
  // Script-evidence detection: the six locales the old `!STOPWORDS[locale] continue`
  // walked past in silence. Every planted defect below was UNDETECTABLE before this
  // file grew a second instrument.
  // ---------------------------------------------------------------------------------
  write('ja', { pick: GERMAN });
  check('German planted in the Japanese file is reported', pairs(), ['ja<-de']);
  reseed();

  write('ru', { pick: ENGLISH });
  check('English planted in the Russian file is reported', pairs(), ['ru<-en']);
  reseed();

  // Control for the script signal. A Chinese value naming Latin products IS Chinese, and
  // a value that is nothing but product syntax carries no function words to score with.
  // Without both, the script rule would report every brand string in five locales.
  write('zh', {
    pick: '请在 Rediacc 控制台中选择 Copy-on-Write 快照',
    bare: 'Rediacc Copy-on-Write BTRFS',
  });
  check(
    'Latin product names inside Chinese are not reported (control)',
    findCrossLocaleContamination(root).length,
    0
  );
  reseed();

  // ---------------------------------------------------------------------------------
  // THE FLAT LAYOUT: one FILE per locale, which is what packages/www uses. This root was
  // absent from LOCALE_ROOTS entirely, so the largest locale tree in the repo -- 13
  // catalogs of roughly 6,600 leaves -- was never cross-checked. The cases below drive
  // the SAME detector through the flat reader, and the locale-set cross-check with it,
  // so "we added the root" and "the root is actually scanned" are not the same claim.
  // ---------------------------------------------------------------------------------
  const flatRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'i18n-cross-flat-'));
  flatRootForThrow = flatRoot;
  const writeFlat = (l: string, o: unknown) =>
    fs.writeFileSync(path.join(flatRoot, `${l}.json`), JSON.stringify(o));
  const reseedFlat = () => {
    for (const [l, v] of Object.entries(CLEAN)) writeFlat(l, { pick: v });
  };
  const flatPairs = () =>
    findCrossLocaleContamination(flatRoot, 'flat').map((f) => `${f.locale}<-${f.detected}`);

  reseedFlat();
  check(
    'flat layout: thirteen correct catalogs report nothing (control)',
    findCrossLocaleContamination(flatRoot, 'flat').length,
    0
  );

  writeFlat('it', { pick: FRENCH });
  check('flat layout: French planted in it.json is reported', flatPairs(), ['it<-fr']);
  reseedFlat();

  writeFlat('it', { pick: ENGLISH });
  check('flat layout: English left in it.json is reported', flatPairs(), ['it<-en']);
  reseedFlat();

  // The locale-set cross-check must apply to files exactly as it applies to directories,
  // or the flat root would silently accept a stray catalog or a deleted locale.
  fs.writeFileSync(path.join(flatRoot, 'nl.json'), JSON.stringify({ pick: 'Kies een optie' }));
  check(
    'flat layout: a catalog that is not a site locale is a hard error',
    throwsWithFlat() instanceof UnknownLocaleDirError,
    true
  );
  fs.rmSync(path.join(flatRoot, 'nl.json'));

  fs.rmSync(path.join(flatRoot, 'ko.json'));
  const flatMissing = throwsWithFlat();
  check(
    'flat layout: a site locale with no catalog is a hard error',
    flatMissing instanceof MissingLocaleDirError && flatMissing.locales.join(',') === 'ko',
    true
  );
  fs.rmSync(flatRoot, { recursive: true, force: true });

  // ---------------------------------------------------------------------------------
  // THE LOCALE SET ITSELF. The universe is @rediacc/locales, never readdirSync and never
  // the STOPWORDS keys — hand-maintaining an implicit locale set is what produced the
  // original hole. All three failures below are hard errors, never skips.
  // ---------------------------------------------------------------------------------
  const throwsWith = (fn: () => unknown): unknown => {
    try {
      fn();
      return null;
    } catch (e) {
      return e;
    }
  };

  write('nl', { pick: 'Kies een optie uit de lijst met machines' });
  check(
    'a directory that is not a site locale is a hard error',
    throwsWith(() => findCrossLocaleContamination(root)) instanceof UnknownLocaleDirError,
    true
  );
  fs.rmSync(path.join(root, 'nl'), { recursive: true, force: true });

  fs.rmSync(path.join(root, 'it'), { recursive: true, force: true });
  const missing = throwsWith(() => findCrossLocaleContamination(root));
  check(
    'a site locale with no directory is a hard error, not a silent zero-file scan',
    missing instanceof MissingLocaleDirError && missing.locales.join(',') === 'it',
    true
  );
  reseed();

  // The startup assertion, driven with doctored data so a REAL gap and a TEST gap take
  // the identical code path. Removing a list must fail; this is the "we shipped a
  // fourteenth locale and forgot its detection data" case, and it must be red on day one
  // rather than the next time someone looks at a locale tree.
  const withoutKorean = Object.fromEntries(
    Object.entries(NATIVE_SCRIPT).filter(([l]) => l !== 'ko')
  );
  const gap = throwsWith(() => assertDetectionCoverage(STOPWORDS, withoutKorean));
  check(
    'a site locale with no detection data is a hard error at startup',
    gap instanceof UnmodelledLocaleError && gap.locales.join(',') === 'ko',
    true
  );

  // A typo in a detection key is silent otherwise: NATIVE_SCRIPT.jp would never match the
  // `ja` directory, and `ja` would read as covered while being skipped.
  check(
    'detection data naming a non-site locale is a hard error at startup',
    throwsWith(() =>
      assertDetectionCoverage({ ...STOPWORDS, nl: ['de', 'het'] }, NATIVE_SCRIPT)
    ) instanceof Error,
    true
  );

  // The real data must satisfy the real assertion, or every case above is theatre.
  check(
    'the shipped detection data covers every non-English site locale',
    throwsWith(() => assertDetectionCoverage(STOPWORDS, NATIVE_SCRIPT)),
    null
  );

  fs.rmSync(root, { recursive: true, force: true });
  if (failures.length) {
    console.error(`\n✗ ${failures.length} self-test failure(s)`);
    process.exit(1);
  }
  console.log('\n✓ check-i18n-cross-locale self-test passed');
}

function main(): void {
  const argv = process.argv.slice(2);
  if (argv.includes('--selftest')) return selftest();

  // CONTROL FIRST, ALWAYS. This selftest plants German inside a French file and
  // requires the detector to report it. It used to run only behind --selftest,
  // and NOTHING invoked that flag: `check:ci-i18n-cross-locale` runs this file
  // bare, so the one proof that this gate can FIRE was dead code. A gate whose
  // fire-proof never runs is indistinguishable from a gate that always passes,
  // which is exactly the defect class this file was written to catch.
  //
  // Running it inline turns "did the control fire" into "did the gate exit 0",
  // which CI already checks. Same shape as scripts/check-schema-coverage.ts.
  // Cost is a few temp files and milliseconds.
  if (!argv.includes('--skip-control')) selftest();

  const rootIdx = argv.indexOf('--root');
  const base = rootIdx >= 0 ? path.resolve(argv[rootIdx + 1]) : REPO_ROOT;

  const roots = LOCALE_ROOTS.map((r) => ({ ...r, abs: path.join(base, r.root) })).filter((r) =>
    fs.existsSync(r.abs)
  );
  if (roots.length === 0) {
    console.error(`✗ Refusing to run: none of the locale roots exist under ${base}.`);
    process.exit(1);
  }

  let findings: Finding[];
  try {
    findings = roots.flatMap((r) => findCrossLocaleContamination(r.abs, r.layout));
  } catch (e) {
    // An unmodelled locale is a defect in THIS gate's coverage, so it gets its own clean
    // diagnostic rather than a stack trace: the reader has to know which locale, and what
    // to add, without opening the file.
    // A locale-set mismatch is a defect in THIS gate's coverage, so it gets a clean
    // diagnostic rather than a stack trace: the reader has to know which locale and what
    // to add without opening the file.
    const known =
      e instanceof UnknownLocaleDirError ||
      e instanceof MissingLocaleDirError ||
      e instanceof UnmodelledLocaleError;
    if (!known) throw e;
    console.error(`✗ ${(e as Error).message}`);
    process.exit(1);
  }
  if (findings.length === 0) {
    console.log(`✓ No cross-locale contamination across ${roots.length} locale root(s).`);
    return;
  }

  console.error(
    `✗ ${findings.length} value(s) appear in two locales that should not share them:\n`
  );
  const byPair = new Map<string, Finding[]>();
  for (const f of findings) {
    const k = `${f.locale} contains ${f.detected}`;
    byPair.set(k, [...(byPair.get(k) ?? []), f]);
  }
  for (const [pair, list] of [...byPair].sort((a, b) => b[1].length - a[1].length)) {
    console.error(`  ${pair}  (${list.length})`);
    const shown = process.argv.includes('--all') ? list.length : 5;
    for (const f of list.slice(0, shown))
      console.error(`    ${f.file}:${f.key} = ${JSON.stringify(f.value)}`);
    if (list.length > shown)
      console.error(`    ... and ${list.length - shown} more (--all prints every one)`);
  }
  console.error(
    "\nOne locale contains another locale's text. Translate from the ENGLISH source, not\n" +
      'from the twin. No other i18n gate can see this: they all compare against English only.'
  );
  process.exit(1);
}

main();

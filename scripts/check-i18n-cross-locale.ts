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
import { DEFAULT_LOCALE, NON_ENGLISH_LOCALES, SITE_LOCALES, isSiteLocale } from '@rediacc/locales';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Locale roots to scan. Each must contain one directory per locale. */
const LOCALE_ROOTS = [
  'packages/cli/src/i18n/locales',
  'private/account/web/src/i18n/locales',
  'private/account/src/i18n/locales',
];

const SOURCE_LOCALE = DEFAULT_LOCALE;
/** Short strings carry too few function words to identify a language from. */
const MIN_LENGTH = 12;

type Finding = { root: string; locale: string; detected: string; file: string; key: string; value: string };

/**
 * A locale directory on disk that is not a site locale. Thrown, never skipped.
 *
 * The locale universe is `@rediacc/locales`, not whatever `readdirSync` happens to
 * return. A directory outside that set is either a typo or a locale someone added
 * without declaring it, and both must be loud: the gate would otherwise judge it with
 * whatever detection data it happened to have, or none.
 */
class UnknownLocaleDirError extends Error {
  constructor(readonly locale: string, readonly root: string) {
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
  constructor(readonly locales: string[], readonly root: string) {
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
 * A site locale with no way to judge it. Thrown AT STARTUP, before any scanning.
 *
 * WHY STARTUP AND NOT PER-VALUE. The skip this replaces (`if (!STOPWORDS[locale])
 * continue`) is how 379 German values lived in account-web's ar, ja, ru and zh while
 * this gate reported a checkmark. Checking coverage lazily, as each locale is reached,
 * has the same shape of hole: a locale absent from every tree on the day would never
 * reach the check. Deriving the requirement from @rediacc/locales and asserting it before
 * the first file is opened makes "we shipped a fourteenth locale and forgot its detection
 * data" a red gate on day one, with no tree needed to trigger it.
 */
class UnmodelledLocaleError extends Error {
  constructor(readonly locales: string[]) {
    super(
      `${locales.length} site locale(s) have no detection data: ${locales.join(', ')}.\n` +
        `Every non-English site locale needs a function-word list in STOPWORDS (Latin ` +
        `script) or a writing system in NATIVE_SCRIPT (non-Latin).\n` +
        `Skipping a locale silently is how ar/ja/ru/zh carried 379 German values through ` +
        `a green gate.`
    );
    this.name = 'UnmodelledLocaleError';
  }
}

/**
 * Function words that are frequent in one language and rare in the others we ship.
 * Deliberately small and high-precision: this answers "is this text German?", which is
 * the question that matters, rather than "do two locales match?" — the latter is useless
 * here because Spanish and Portuguese legitimately share whole strings ("cancelado",
 * "Máquinas"), as do German and French for loanwords ("Abonnement"). Matching on identical
 * values produced 136 false positives on the es/pt pair alone.
 */
const STOPWORDS: Record<string, string[]> = {
  // `en` is never scanned as a TARGET (it is SOURCE_LOCALE), only ever as a DETECTED
  // language. Without it, English left sitting in a translated locale — the single most
  // common failure of a half-finished translation pass — was undetectable by
  // construction, exactly like German was before the de/fr/es/it/pt/tr lists existed.
  en: ['the', 'and', 'you', 'your', 'this', 'that', 'these', 'those', 'with', 'from', 'have', 'has', 'been', 'will', 'not', 'are', 'was', 'were', 'they', 'their', 'there', 'which', 'when', 'while', 'because', 'before', 'after', 'about', 'into', 'only', 'also', 'than', 'then', 'each', 'both', 'such', 'please', 'cannot', 'should', 'would', 'could', 'must'],
  de: ['nach', 'nicht', 'oder', 'wird', 'werden', 'einen', 'eine', 'sie', 'ihre', 'mit', 'für', 'sind', 'auf', 'aus', 'kann', 'muss', 'noch', 'wenn', 'durch', 'bitte', 'keine', 'dieser', 'diese'],
  fr: ['vous', 'votre', 'les', 'des', 'une', 'est', 'pas', 'pour', 'avec', 'dans', 'sur', 'par', 'que', 'qui', 'aux', 'ete', 'sont', 'cette', 'plus'],
  // 'more' used to sit here. It is an ENGLISH word, and it was the Spanish list's only
  // non-Spanish entry, so an English string anywhere scored one point towards "this is
  // Spanish". With an `en` list now present it would also have been pruned as
  // non-discriminative, silently weakening both lists. Removed rather than deduplicated.
  es: ['los', 'las', 'una', 'para', 'con', 'por', 'que', 'del', 'esta', 'este', 'son', 'como', 'pero', 'todos'],
  it: ['gli', 'una', 'per', 'con', 'che', 'del', 'della', 'sono', 'questo', 'questa', 'nel', 'alla'],
  pt: ['dos', 'das', 'uma', 'para', 'com', 'por', 'que', 'nao', 'sao', 'este', 'esta', 'pelo'],
  tr: ['ve', 'bir', 'icin', 'ile', 'bu', 'olarak', 'veya', 'daha', 'gerekli'],
  // Estonian. Deliberately excludes 'on' and 'see', which are ordinary English words:
  // an English string carrying them would have scored towards Estonian and been reported
  // under the wrong source language, blunting the diagnostic the operator acts on.
  et: ['ja', 'ei', 'ning', 'kõik', 'peab', 'saab', 'tuleb', 'palun', 'juba', 'ainult', 'nende', 'selle', 'kuid', 'või', 'siis', 'ega', 'pole', 'oma', 'kas', 'sest'],
};

/**
 * The writing system each non-Latin locale is supposed to use.
 *
 * These five have no function-word list and cannot get a useful one: a stopword list is
 * a Latin-alphabet instrument, and the words that would populate it are written in a
 * script the tokenizer does not split on. For them the evidence runs the other way — a
 * value holding not one character of its own script is not a translation into it, whatever
 * language it turns out to be. Same predicate as check-locale-de-contamination.ts, which
 * proved it against the 379 real findings; here it is paired with the function-word
 * signal so a Latin PRODUCT NAME standing alone cannot trip it.
 */
const NATIVE_SCRIPT: Record<string, RegExp> = {
  ar: /[؀-ۿݐ-ݿ]/,
  ja: /[぀-ヿ一-鿿]/,
  ko: /[가-힯ᄀ-ᇿ]/,
  ru: /[Ѐ-ӿ]/,
  zh: /[一-鿿]/,
};

/**
 * Terms that legitimately stay in Latin script in every locale. They are stripped BEFORE
 * function words are counted, because several of them tokenize into words that also sit
 * in a stopword list — "Copy-on-Write" and "Restart=on-failure" both yield "on", and a
 * value made of nothing but product syntax must score zero, not two.
 */
const TECHNICAL_TERMS = new Set([
  'rediacc', 'renet', 'docker', 'compose', 'btrfs', 'luks', 'ceph', 'rbd', 'osd', 'mon', 'mgr',
  'k3s', 'kubernetes', 'kubectl', 'systemd', 'ssh', 'sftp', 'rsync', 'rclone', 'criu', 'traefik',
  'http', 'https', 'tcp', 'udp', 'dns', 'tls', 'ssl', 'json', 'yaml', 'toml', 'api', 'url', 'uri',
  'cli', 'sdk', 'guid', 'uuid', 'sha', 'crc', 'pem', 'vlan', 'nat', 'wireguard', 'vpn', 'cpu',
  'gpu', 'ram', 'ssd', 'nvme', 'iops', 'linux', 'windows', 'macos', 'ubuntu', 'debian', 'fedora',
  'github', 'gitlab', 'nextcloud', 'postgres', 'postgresql', 'mysql', 'redis', 'mongodb', 'nginx',
  'copy', 'write', 'read', 'root', 'sudo', 'bash', 'git', 'npm', 'node', 'python', 'golang',
]);

/**
 * Every non-English site locale must be judgeable by one instrument or the other, and
 * every piece of detection data must name a real site locale.
 *
 * Runs AT MODULE LOAD, so it fires with no locale tree present at all. That is the point:
 * the locale universe comes from `@rediacc/locales`, which is the same declaration the
 * rest of the repo builds against, so adding a fourteenth locale there turns this gate red
 * immediately rather than the next time someone happens to look.
 */
export function assertDetectionCoverage(
  stopwords: Record<string, string[]>,
  nativeScript: Record<string, RegExp>
): void {
  // A typo in a detection key is silent otherwise: `NATIVE_SCRIPT.jp` would simply never
  // match the `ja` directory, and the locale would read as covered while being skipped.
  for (const key of [...Object.keys(stopwords), ...Object.keys(nativeScript)]) {
    if (!isSiteLocale(key)) {
      throw new Error(
        `Detection data names "${key}", which is not a site locale.\n` +
          `Known: ${SITE_LOCALES.join(', ')}. Fix the typo, or declare the locale in ` +
          `packages/locales/index.js.`
      );
    }
  }
  const uncovered = NON_ENGLISH_LOCALES.filter((l) => !stopwords[l] && !nativeScript[l]);
  if (uncovered.length > 0) throw new UnmodelledLocaleError([...uncovered]);
}

/** Drop every span that carries no natural language, then every protected technical term. */
function stripNonLanguage(value: string): string {
  return value
    .replace(/\{\{[^}]*\}\}/g, ' ')
    .replace(/%[-+ #0]*[\d.*]*(?:\[\d+\])?[a-zA-Z]/g, ' ')
    .replace(/<[^>]*>/g, ' ')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/`[^`]*`/g, ' ')
    .replace(/(?:^|[^\w-])--?[A-Za-z][\w-]*/g, ' ')
    .replace(/[A-Za-z_][\w.]*=[^\s,)]+/g, ' ')
    .replace(/[A-Za-z]\w*(?:-\w+)+/g, ' ')
    .replace(/\d+/g, ' ');
}

function flatten(obj: unknown, prefix = '', out: Record<string, string> = {}): Record<string, string> {
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const q = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === 'object') flatten(v, q, out);
      else if (typeof v === 'string') out[q] = v;
    }
  }
  return out;
}

/**
 * Words claimed by more than one language are useless for telling those languages apart,
 * and they are exactly what produced the first round of false positives: "por" and "todos"
 * sat in both the Spanish and Portuguese lists, so correct Portuguese scored as Spanish.
 * Rather than hand-curate the overlap away and get it wrong again, drop it mechanically.
 */
const DISCRIMINATIVE: Record<string, Set<string>> = (() => {
  const counts = new Map<string, number>();
  for (const words of Object.values(STOPWORDS)) {
    for (const w of new Set(words)) counts.set(w, (counts.get(w) ?? 0) + 1);
  }
  return Object.fromEntries(
    Object.entries(STOPWORDS).map(([lang, words]) => [
      lang,
      new Set(words.filter((w) => counts.get(w) === 1)),
    ])
  );
})();

// STARTUP, not lazily. Nothing below this line runs if a site locale is unmodellable.
assertDetectionCoverage(STOPWORDS, NATIVE_SCRIPT);

const norm = (s: string) =>
  s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

/** The prose words of a value: markup, syntax and protected technical terms removed. */
function contentWords(text: string): string[] {
  return norm(text)
    .split(/[^a-z]+/)
    .filter((w) => w.length > 1 && !TECHNICAL_TERMS.has(w));
}

/** Score how strongly a string looks like each language. Returns the best match, or null. */
function identify(text: string): { lang: string; score: number } | null {
  const words = contentWords(text);
  if (words.length < 3) return null;
  const set = new Set(words);
  let best: { lang: string; score: number } | null = null;
  for (const [lang, stops] of Object.entries(DISCRIMINATIVE)) {
    const score = [...stops].filter((w) => set.has(norm(w))).length;
    if (score > 0 && (!best || score > best.score)) best = { lang, score };
  }
  return best;
}

export function findCrossLocaleContamination(root: string): Finding[] {
  if (!fs.existsSync(root)) return [];
  const locales = fs
    .readdirSync(root)
    .filter((d) => fs.statSync(path.join(root, d)).isDirectory())
    .sort();

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
    for (const file of fs.readdirSync(path.join(root, locale))) {
      if (!file.endsWith('.json')) continue;
      let flat: Record<string, string>;
      try {
        flat = flatten(JSON.parse(fs.readFileSync(path.join(root, locale, file), 'utf-8')));
      } catch (e) {
        // ONLY a malformed locale file is another gate's problem. Anything else — a
        // missing helper, a bad regex — is a bug in THIS file, and swallowing it makes
        // the gate silently report zero findings. That exact mistake happened here.
        if (e instanceof SyntaxError) continue;
        throw e;
      }
      for (const [key, value] of Object.entries(flat)) {
        if (value.length < MIN_LENGTH) continue;
        const text = stripNonLanguage(value);
        const id = identify(text);
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

function selftest(): void {
  const failures: string[] = [];
  const check = (name: string, actual: unknown, expected: unknown) => {
    if (JSON.stringify(actual) === JSON.stringify(expected)) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}\n        expected ${JSON.stringify(expected)}\n        got      ${JSON.stringify(actual)}`);
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
  check('all thirteen site locales, correctly translated, report nothing (control)',
    findCrossLocaleContamination(root).length, 0);

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
  check('es/pt near-identical strings are not reported (control)',
    findCrossLocaleContamination(root).filter((f) => f.locale === 'pt' || f.locale === 'es').length, 0);

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
  check('Latin product names inside Chinese are not reported (control)',
    findCrossLocaleContamination(root).length, 0);
  reseed();

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
  check('a directory that is not a site locale is a hard error',
    throwsWith(() => findCrossLocaleContamination(root)) instanceof UnknownLocaleDirError, true);
  fs.rmSync(path.join(root, 'nl'), { recursive: true, force: true });

  fs.rmSync(path.join(root, 'it'), { recursive: true, force: true });
  const missing = throwsWith(() => findCrossLocaleContamination(root));
  check('a site locale with no directory is a hard error, not a silent zero-file scan',
    missing instanceof MissingLocaleDirError && missing.locales.join(',') === 'it', true);
  reseed();

  // The startup assertion, driven with doctored data so a REAL gap and a TEST gap take
  // the identical code path. Removing a list must fail; this is the "we shipped a
  // fourteenth locale and forgot its detection data" case, and it must be red on day one
  // rather than the next time someone looks at a locale tree.
  const withoutKorean = Object.fromEntries(
    Object.entries(NATIVE_SCRIPT).filter(([l]) => l !== 'ko')
  );
  const gap = throwsWith(() => assertDetectionCoverage(STOPWORDS, withoutKorean));
  check('a site locale with no detection data is a hard error at startup',
    gap instanceof UnmodelledLocaleError && gap.locales.join(',') === 'ko', true);

  // A typo in a detection key is silent otherwise: NATIVE_SCRIPT.jp would never match the
  // `ja` directory, and `ja` would read as covered while being skipped.
  check('detection data naming a non-site locale is a hard error at startup',
    throwsWith(() => assertDetectionCoverage({ ...STOPWORDS, nl: ['de', 'het'] }, NATIVE_SCRIPT)) instanceof Error, true);

  // The real data must satisfy the real assertion, or every case above is theatre.
  check('the shipped detection data covers every non-English site locale',
    throwsWith(() => assertDetectionCoverage(STOPWORDS, NATIVE_SCRIPT)), null);

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

  const roots = LOCALE_ROOTS.map((r) => path.join(base, r)).filter((r) => fs.existsSync(r));
  if (roots.length === 0) {
    console.error(`✗ Refusing to run: none of the locale roots exist under ${base}.`);
    process.exit(1);
  }

  let findings: Finding[];
  try {
    findings = roots.flatMap(findCrossLocaleContamination);
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

  console.error(`✗ ${findings.length} value(s) appear in two locales that should not share them:\n`);
  const byPair = new Map<string, Finding[]>();
  for (const f of findings) {
    const k = `${f.locale} contains ${f.detected}`;
    byPair.set(k, [...(byPair.get(k) ?? []), f]);
  }
  for (const [pair, list] of [...byPair].sort((a, b) => b[1].length - a[1].length)) {
    console.error(`  ${pair}  (${list.length})`);
    for (const f of list.slice(0, 5)) console.error(`    ${f.file}:${f.key} = ${JSON.stringify(f.value)}`);
    if (list.length > 5) console.error(`    ... and ${list.length - 5} more`);
  }
  console.error(
    '\nOne locale contains another locale\'s text. Translate from the ENGLISH source, not\n' +
      'from the twin. No other i18n gate can see this: they all compare against English only.'
  );
  process.exit(1);
}

main();

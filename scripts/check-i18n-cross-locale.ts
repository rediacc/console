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
 * Usage:
 *   tsx scripts/check-i18n-cross-locale.ts [--root <dir>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Locale roots to scan. Each must contain one directory per locale. */
const LOCALE_ROOTS = [
  'packages/cli/src/i18n/locales',
  'private/account/web/src/i18n/locales',
  'private/account/src/i18n/locales',
];

const SOURCE_LOCALE = 'en';
/** Short strings carry too few function words to identify a language from. */
const MIN_LENGTH = 12;

type Finding = { root: string; locale: string; detected: string; file: string; key: string; value: string };

/**
 * Function words that are frequent in one language and rare in the others we ship.
 * Deliberately small and high-precision: this answers "is this text German?", which is
 * the question that matters, rather than "do two locales match?" — the latter is useless
 * here because Spanish and Portuguese legitimately share whole strings ("cancelado",
 * "Máquinas"), as do German and French for loanwords ("Abonnement"). Matching on identical
 * values produced 136 false positives on the es/pt pair alone.
 */
const STOPWORDS: Record<string, string[]> = {
  de: ['nach', 'nicht', 'oder', 'wird', 'werden', 'einen', 'eine', 'sie', 'ihre', 'mit', 'für', 'sind', 'auf', 'aus', 'kann', 'muss', 'noch', 'wenn', 'durch', 'bitte', 'keine', 'dieser', 'diese'],
  fr: ['vous', 'votre', 'les', 'des', 'une', 'est', 'pas', 'pour', 'avec', 'dans', 'sur', 'par', 'que', 'qui', 'aux', 'ete', 'sont', 'cette', 'plus'],
  es: ['los', 'las', 'una', 'para', 'con', 'por', 'que', 'del', 'esta', 'este', 'son', 'como', 'more', 'pero', 'todos'],
  it: ['gli', 'una', 'per', 'con', 'che', 'del', 'della', 'sono', 'questo', 'questa', 'nel', 'alla'],
  pt: ['dos', 'das', 'uma', 'para', 'com', 'por', 'que', 'nao', 'sao', 'este', 'esta', 'pelo'],
  tr: ['ve', 'bir', 'icin', 'ile', 'bu', 'olarak', 'veya', 'daha', 'gerekli'],
};

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

const norm = (s: string) =>
  s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

/** Score how strongly a string looks like each language. Returns the best match, or null. */
function identify(value: string): { lang: string; score: number } | null {
  const words = norm(value).split(/[^a-z]+/).filter((w) => w.length > 1);
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

  const findings: Finding[] = [];
  for (const locale of locales) {
    if (locale === SOURCE_LOCALE || !STOPWORDS[locale]) continue;
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
        const id = identify(value);
        // Only report when another language's function words are present AND this
        // locale's own are not — two clear signals, so a shared loanword cannot trip it.
        if (!id || id.lang === locale || id.score < 2) continue;
        // Require the locale's OWN discriminative words to be entirely absent. Two
        // independent signals — foreign words present, native words absent — is what keeps
        // a shared loanword or a cognate from tripping the gate.
        const words = new Set(norm(value).split(/[^a-z]+/));
        const own = [...(DISCRIMINATIVE[locale] ?? [])].filter((w) => words.has(norm(w))).length;
        if (own > 0) continue;
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
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'i18n-cross-'));
  const write = (l: string, o: unknown) => {
    fs.mkdirSync(path.join(root, l), { recursive: true });
    fs.writeFileSync(path.join(root, l, 'app.json'), JSON.stringify(o));
  };

  const GERMAN = 'Bitte wählen Sie eine Option aus der Liste';
  const FRENCH = 'Veuillez choisir une option dans la liste pour vous';
  const SPANISH = 'Por favor elija una de las opciones para este cliente';
  const PORTUGUESE = 'Por favor escolha uma das opcoes para este cliente';

  // The real bug: German text sitting in the French file.
  write('en', { pick: 'Please choose an option from the list' });
  write('de', { pick: GERMAN });
  write('fr', { pick: GERMAN });
  write('es', { pick: SPANISH });
  const found = findCrossLocaleContamination(root);
  check(
    'detects German text sitting in the French file',
    found.map((f) => `${f.locale}<-${f.detected}:${f.key}`),
    ['fr<-de:pick']
  );

  // Control: correct French must NOT be reported.
  write('fr', { pick: FRENCH });
  check('correct French is not reported (control)', findCrossLocaleContamination(root).length, 0);

  // Control: es and pt legitimately share near-identical strings. The first version of
  // this gate reported 136 of these; it must report none.
  write('pt', { pick: PORTUGUESE });
  check(
    'es/pt near-identical strings are not reported (control)',
    findCrossLocaleContamination(root).filter((f) => f.locale === 'pt' || f.locale === 'es').length,
    0
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

  const roots = LOCALE_ROOTS.map((r) => path.join(base, r)).filter((r) => fs.existsSync(r));
  if (roots.length === 0) {
    console.error(`✗ Refusing to run: none of the locale roots exist under ${base}.`);
    process.exit(1);
  }

  const findings = roots.flatMap(findCrossLocaleContamination);
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

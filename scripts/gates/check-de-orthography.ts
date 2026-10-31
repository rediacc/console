#!/usr/bin/env tsx
/**
 * Gate: German catalog strings carry umlauts and ß, never their ASCII transliterations.
 *
 * WHY THIS EXISTS. Commit 5bafc6a4 restored 638 ASCII transliterations in
 * packages/www/src/i18n/translations/de.json ("fuer", "ueber", "koennen",
 * "Gewaehrleistungen", "ausschliesslich", "Groesse"). Every i18n gate passed with them
 * in place: check-locale-de-contamination.ts compares locales for EQUALITY, the
 * cross-locale gate identifies a language from function words, and the hash, ledger
 * and placeholder gates ask whether a locale is in step with English. None of them
 * reads German spelling, so "fuer" was as valid as "für".
 *
 * THE LIST IS EXPLICIT, NEVER A GENERIC ae/oe/ue REGEX. German writes those vowel pairs
 * legitimately all the time: "neue", "Quelle", "Steuer", "aktuell", "Dauer", "zuerst",
 * "anzueignen", "Risikoexposition", "Kontoeinstellungen", "Nettoeinkommen". A generic
 * pattern fires on every one of them (measured on the tree at authoring time: 125
 * distinct legitimate words). Each entry in TRANSLITERATIONS below is a STEM whose
 * ASCII spelling has no legitimate German or English reading, so it may match anywhere
 * inside a word: German compounds put the defect mid-word ("Zellgroesse",
 * "Uebersetzungsschluessel", "ordnungsgemaess"), and a word-start anchor would miss them.
 * Adding a stem means checking it against the real corpus first; the selftest pins the
 * legitimate words above so a loose stem fails here, not in review.
 *
 * SWISS ORTHOGRAPHY IS OUT OF SCOPE. The `de` catalogs are de-DE, where "schliesslich"
 * and "Massnahme" are wrong. "gross" and "ausser" are deliberately NOT listed: "gross"
 * is an English word ("gross margin") and "aus" + "Server" compounds make "ausser" a
 * false positive in technical prose.
 *
 * WHAT IS SKIPPED before matching: {{placeholders}}, {single} ICU/i18next slots, Go
 * format verbs (%s, %.12s), HTML tags, URLs, backtick code spans, and identifier-shaped
 * tokens (anything holding `_`, `/`, or a dotted path), so a key name or a file path
 * quoted in a message is never read as German prose.
 *
 * THE CORPUS, one root per German catalog in the repo:
 *   packages/www/src/i18n/translations/de.json         (flat)
 *   packages/cli/src/i18n/locales/de/*.json            (dir)
 *   private/account/web/src/i18n/locales/de/*.json     (dir, submodule)
 *   private/account/src/i18n/locales/de/*.json         (dir, submodule)
 *   private/renet/pkg/i18n/locales/de.go               (go: message.SetString literals)
 * The first four are the LOCALE_ROOTS of check-locale-de-contamination.ts,
 * check-i18n-cross-locale.ts and check-locale-config-divergence.ts; none exports them
 * (each runs main() on import), so the list is repeated here as a fourth copy. renet has no JSON source for German: de.go IS the catalog and
 * is edited directly.
 *
 * EXIT CODES
 *   0  clean; the success line prints how many strings and roots were read
 *   1  at least one transliteration (or a failed control)
 *   2  no verdict: a root holds zero German strings, a catalog will not parse, or the
 *      whole corpus is empty. A scan over nothing is not a pass.
 * A private submodule that is not checked out is a NOT CHECKED line locally and a hard
 * failure in CI (scripts/lib/submodule-presence.ts).
 *
 * Usage:
 *   tsx scripts/gates/check-de-orthography.ts             (controls, then the real tree)
 *   tsx scripts/gates/check-de-orthography.ts --selftest  (controls only)
 *   tsx scripts/gates/check-de-orthography.ts --root <dir>
 *
 * ---- gate ----
 * step: German orthography
 * needs: node, submodules
 * lane: quality-content
 * ---- end gate ----
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { type ControlCase, runControls } from '../lib/controls.js';
import { exitWithMainIfEntryPoint } from '../lib/entry-point.js';
import { reportFindings } from '../lib/findings-report.js';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

/**
 * Anti-vacuity floor over the whole corpus read from the real tree. The www catalog alone holds about 5,700 German strings, so 2,000 survives real churn and any one private root being absent locally, while a collapsed reader (a changed key shape, a wrong directory) falls far below it and is refused instead of reported clean. Fixture trees under --root are small by design and are exempt.
 */
export const MIN_GERMAN_STRINGS = 2000;

export type Layout = 'flat' | 'dir' | 'go';
export interface GermanRoot {
  /** Repo-relative path: the de.json file, the de/ directory, or the de.go file. */
  rel: string;
  layout: Layout;
}

export const GERMAN_ROOTS: readonly GermanRoot[] = [
  { rel: 'packages/www/src/i18n/translations/de.json', layout: 'flat' },
  { rel: 'packages/cli/src/i18n/locales/de', layout: 'dir' },
  { rel: 'private/account/web/src/i18n/locales/de', layout: 'dir' },
  { rel: 'private/account/src/i18n/locales/de', layout: 'dir' },
  { rel: 'private/renet/pkg/i18n/locales/de.go', layout: 'go' },
];

/**
 * One transliteration class: an ASCII stem (lower case) and its correct spelling.
 * Grouped by the character the stem loses, so a reader sees which rule a finding broke.
 */
export interface Transliteration {
  stem: string;
  fix: string;
  group: 'ae->ä' | 'oe->ö' | 'ue->ü' | 'ss->ß';
}

const T = (group: Transliteration['group'], pairs: [string, string][]): Transliteration[] =>
  pairs.map(([stem, fix]) => ({ stem, fix, group }));

/**
 * The strict list. Every stem was checked against the five catalogs and the English
 * vocabulary for a legitimate reading before it was added. Order matters only for
 * suggestions: longer stems sharing a prefix come first so "ausschliess" is not
 * half-rewritten by "schliess" (both produce the same text, but the finding names the
 * longer, more specific stem).
 */
export const TRANSLITERATIONS: readonly Transliteration[] = [
  ...T('ae->ä', [
    ['waehr', 'währ'], // während, Gewähr, Gewährleistung, Währung
    ['spaet', 'spät'], // später, verspätet
    ['aender', 'änder'], // ändern, Änderung, geändert, unverändert
    ['waehl', 'wähl'], // wählen, ausgewählt
    ['naechst', 'nächst'], // nächste
    ['laeuf', 'läuf'], // läuft, Läufe
    ['haelt', 'hält'], // enthält, erhält, behält
    ['haeng', 'häng'], // hängen, abhängig, eingehängt
    ['staendig', 'ständig'], // vollständig, zuständig
    ['saetz', 'sätz'], // zusätzlich, Datensätze
    ['traeg', 'träg'], // Einträge, Verträge
    ['itaet', 'ität'], // Integrität, Qualität, Kapazität
    ['schaed', 'schäd'], // beschädigt, schädlich
    ['faeng', 'fäng'], // anfänglich, Empfänger
    ['laeng', 'läng'], // länger, Länge
    ['klaer', 'klär'], // erklären, Erklärung
    ['faehig', 'fähig'], // fähig, Fähigkeit
    ['aeuss', 'äuß'], // äußern, äußerst
  ]),
  ...T('oe->ö', [
    ['koenn', 'könn'], // können, könnte
    ['moeg', 'mög'], // möglich, Möglichkeit, Vermögen
    ['groess', 'größ'], // Größe, vergrößern (both letters transliterated)
    ['oeffn', 'öffn'], // öffnen
    ['oeffentlich', 'öffentlich'],
    ['loesch', 'lösch'], // löschen
    ['loesung', 'lösung'], // Lösung
    ['loest', 'löst'], // gelöst, aufgelöst
    ['aufloes', 'auflös'], // Auflösung
    ['hoer', 'hör'], // gehören, hören
    ['woech', 'wöch'], // wöchentlich
    ['foerd', 'förd'], // befördern, fördern
    ['noet', 'nöt'], // nötig, benötigt
  ]),
  ...T('ue->ü', [
    ['fuer', 'für'], // für, dafür, hierfür
    ['fuehr', 'führ'], // führen, ausführen, Ausführung
    ['ueber', 'über'], // über, gegenüber, überprüfen, Übersetzung
    ['muess', 'müss'], // müssen
    ['duerf', 'dürf'], // dürfen
    ['pruef', 'prüf'], // prüfen, Prüfung
    ['schluess', 'schlüss'], // Schlüssel, verschlüsseln, Abschlüsse
    ['rueck', 'rück'], // zurück, Rückgabe, vorrücken
    ['gueltig', 'gültig'], // gültig, ungültig, endgültig
    ['fueg', 'füg'], // verfügbar, hinzufügen
    ['stuetz', 'stütz'], // unterstützt, gestützt
    ['schuetz', 'schütz'], // schützen, schreibgeschützt
    ['spruech', 'sprüch'], // widersprüchlich
    ['natuerl', 'natürl'], // natürlich
    ['kuerz', 'kürz'], // kürzlich, kürzen
    ['wuensch', 'wünsch'], // wünschen
    ['guenst', 'günst'], // günstig
    ['frueh', 'früh'], // früh, frühere
  ]),
  ...T('ss->ß', [
    ['ausschliess', 'ausschließ'], // ausschließlich
    ['schliess', 'schließ'], // schließen, schließlich, einschließlich
    ['massnahm', 'maßnahm'], // Maßnahme
    ['ausserhalb', 'außerhalb'], // listed whole: bare "ausser" collides with aus + Server compounds
    ['gemaess', 'gemäß'], // gemäß, ordnungsgemäß (also loses its umlaut)
    ['maessig', 'mäßig'], // regelmäßig
    ['gröss', 'größ'], // Größe written with the umlaut but not the ß
  ]),
];

export interface Finding {
  file: string;
  key: string;
  word: string;
  suggestion: string;
  stems: string[];
}

/** Remove the parts of a value that are not German prose. */
export function proseOf(value: string): string {
  // A single-brace slot is a one-word BRANCH (prose) after a plural key ("one {fuer}",
  // "=0 {fuer}"). In an ICU message a select key is a branch too, when it follows the selector
  // (", select,") or the previous branch's closing brace ("male {fuer}", "female {fuer}").
  // Anywhere else the slot is a placeholder: "Hallo {name}", and outside ICU also
  // "{count} Dateien {name}".
  const icu = /,\s*(?:select|plural|selectordinal)\s*,/.test(value);
  const slot = icu
    ? /(?<!(?:(?:,\s*(?:select|plural|selectordinal)\s*,|\})\s*(?:\w+|=\d+)|\b(?:zero|one|two|few|many|other)|=\d+)\s*)\{[^{}\s]*\}/g
    : /(?<!(?:\b(?:zero|one|two|few|many|other)|=\d+)\s*)\{[^{}\s]*\}/g;
  return (
    value
      .replace(/\{\{[^}]*\}\}/g, ' ')
      // Outside ICU a single-brace slot is a placeholder ("{name}"), except after a plural key.
      .replace(slot, ' ')
      .replace(/<[^>]*>/g, ' ')
      .replace(/https?:\/\/\S+/g, ' ')
      .replace(/`[^`]*`/g, ' ')
      // The verb letter must not run into more letters, so "5 % fuer alle" stays prose while
      // Go's space flag ("% d", "% x") is still a directive.
      .replace(/%[-+# 0-9.*]*[a-zA-Z](?![A-Za-z])/g, ' ')
      // Identifier-shaped tokens: snake_case keys, paths, dotted names, flags. A single
      // slash between words ("fuer/gegen") is prose and stays; a path has two, or a root.
      .replace(/\S*_\S*/g, ' ')
      .replace(/\S*\/\S*\/\S*/g, ' ')
      .replace(/(^|\s)[.~]?\/\S*/g, ' ')
      // Every segment starts lower case: "machine.name", "config.json". A capital after the
      // dot ("Hallo.Fuer alle") is a sentence with a missing space, and stays scanned.
      .replace(/\b[a-z][A-Za-z0-9]*(?:\.[a-z][A-Za-z0-9]*)+\b/g, ' ')
      // A flag starts at whitespace. Unanchored, this pattern ate the tail of every
      // hyphenated compound ("Probe-Laeufen", "fstab-Aenderung") and hid it from the scan.
      .replace(/(^|\s)--?[A-Za-z][\w-]*/g, ' ')
  );
}

function matchCase(original: string, replacement: string): string {
  if (original.length > 1 && original === original.toUpperCase()) return replacement.toUpperCase();
  const first = original.charAt(0);
  if (first !== first.toLowerCase()) {
    return replacement.charAt(0).toUpperCase() + replacement.slice(1);
  }
  return replacement;
}

/** Every transliterated word in one value, with its suggested spelling. */
export function scanValue(value: string): { word: string; suggestion: string; stems: string[] }[] {
  const out: { word: string; suggestion: string; stems: string[] }[] = [];
  for (const word of proseOf(value).match(/[A-Za-zÀ-ÖØ-öø-ÿ]+/g) ?? []) {
    const lower = word.toLowerCase();
    const stems = TRANSLITERATIONS.filter((t) => lower.includes(t.stem));
    if (stems.length === 0) continue;
    let suggestion = word;
    for (const t of stems) {
      suggestion = suggestion.replace(new RegExp(t.stem, 'gi'), (m) => matchCase(m, t.fix));
    }
    // In capitals ß is written SS ("EINSCHLIESSLICH" is correct German), and
    // "ß".toUpperCase() is "SS", so such a word rewrites to itself. A rewrite that changes
    // nothing is not a defect; "GEMAESS" still rewrites (to "GEMÄSS") and still fires.
    if (suggestion === word) continue;
    out.push({ word, suggestion, stems: stems.map((t) => t.stem) });
  }
  return out;
}

function flatten(node: unknown, prefix: string, out: Record<string, string>): void {
  if (typeof node === 'string') out[prefix] = node;
  else if (Array.isArray(node))
    node.forEach((v, i) => flatten(v, prefix ? `${prefix}.${i}` : String(i), out));
  else if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node)) flatten(v, prefix ? `${prefix}.${k}` : k, out);
  }
}

/** Decode one Go interpreted string literal body (the bytes between the quotes). */
function goUnquote(body: string): string {
  return JSON.parse(`"${body.replace(/\\x([0-9a-fA-F]{2})/g, '\\u00$1')}"`) as string;
}

/** A Go string literal: interpreted ("...", groups 1) or raw (`...`, group 2). */
const GO_LIT = '(?:"((?:[^"\\\\]|\\\\.)*)"|`([^`]*)`)';
/** Tag is a bare identifier or a dotted one (language.German). */
const SET_STRING = new RegExp(
  `message\\.SetString\\(\\s*[\\w.]+\\s*,\\s*${GO_LIT}\\s*,\\s*${GO_LIT}\\s*\\)`,
  'g'
);
const SET_STRING_CALL = /message\.SetString\(/g;

/**
 * Read every SetString pair of a de.go text. Refuses (NoVerdict, VACUOUS-style) when the
 * file holds more `message.SetString(` call sites than the pattern matched: a call in a
 * shape the pattern does not know is an unread string, and a green over it means nothing.
 */
export function readGoCatalog(text: string, label: string): Record<string, string> {
  const flat: Record<string, string> = {};
  let matched = 0;
  for (const m of text.matchAll(SET_STRING)) {
    matched += 1;
    try {
      const key = m[1] !== undefined ? goUnquote(m[1]) : m[2];
      flat[key] = m[3] !== undefined ? goUnquote(m[3]) : m[4];
    } catch (e) {
      throw new NoVerdict(
        `${label}: cannot decode the literal for ${m[1] ?? m[2]}: ${(e as Error).message}`
      );
    }
  }
  const calls = [...text.matchAll(SET_STRING_CALL)].length;
  if (calls > matched) {
    throw new NoVerdict(
      `VACUOUS: ${label} has ${calls} message.SetString( call sites but only ${matched} were read; ${calls - matched} are in a shape this gate does not parse, so their German is unread. Teach SET_STRING the new shape.`
    );
  }
  return flat;
}

/** Thrown when a catalog exists but cannot be read; main() turns it into exit 2. */
export class NoVerdict extends Error {}

/** Read one root into `file -> key -> value`. Throws NoVerdict on unreadable input. */
export function readRoot(abs: string, layout: Layout): Record<string, Record<string, string>> {
  const parseJson = (file: string): Record<string, string> => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch (e) {
      throw new NoVerdict(`${file} does not parse as JSON: ${(e as Error).message}`);
    }
    const flat: Record<string, string> = {};
    flatten(parsed, '', flat);
    return flat;
  };
  if (layout === 'flat') return { [abs]: parseJson(abs) };
  if (layout === 'go') {
    return { [abs]: readGoCatalog(fs.readFileSync(abs, 'utf8'), abs) };
  }
  const out: Record<string, Record<string, string>> = {};
  for (const name of fs.readdirSync(abs).sort()) {
    if (name.endsWith('.json')) out[path.join(abs, name)] = parseJson(path.join(abs, name));
  }
  return out;
}

/** Scan read catalogs. Returns the findings and the number of strings read. */
export function scanCatalogs(
  catalogs: Record<string, Record<string, string>>,
  base: string
): {
  findings: Finding[];
  strings: number;
} {
  const findings: Finding[] = [];
  let strings = 0;
  for (const [file, entries] of Object.entries(catalogs)) {
    for (const [key, value] of Object.entries(entries)) {
      strings += 1;
      for (const hit of scanValue(value)) {
        findings.push({ file: path.relative(base, file), key, ...hit });
      }
    }
  }
  return { findings, strings };
}

// ------------------------------------------------------------------------------- controls

function controls(): ControlCase[] {
  const cases: ControlCase[] = [];
  const words = (v: string): string[] => scanValue(v).map((h) => h.word);
  const sugg = (v: string): string[] => scanValue(v).map((h) => h.suggestion);
  const eq = (name: string, actual: unknown, expected: unknown): void => {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    cases.push({
      name,
      ok,
      detail: ok
        ? undefined
        : `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    });
  };

  // MUST FIRE: one planted transliteration per class, each with its suggestion.
  eq(
    'ae->ä: "Gewaehrleistungen" fires and suggests "Gewährleistungen"',
    sugg('Keine Gewaehrleistungen.'),
    ['Gewährleistungen']
  );
  eq('oe->ö: "koennen" fires and suggests "können"', sugg('Sie koennen das.'), ['können']);
  eq('oe->ö: "benoetigt" fires and suggests "benötigt"', sugg('Upload benoetigt ein Manifest'), [
    'benötigt',
  ]);
  eq('ue->ü: "fuer" and "ueber" fire', sugg('fuer alle ueber 18'), ['für', 'über']);
  eq('ss->ß: "ausschliesslich" fires and suggests "ausschließlich"', sugg('ausschliesslich hier'), [
    'ausschließlich',
  ]);
  eq('two classes in one word: "Groesse" suggests "Größe"', sugg('Die Groesse'), ['Größe']);
  eq(
    'mid-compound: "Uebersetzungsschluessel" suggests "Übersetzungsschlüssel"',
    sugg('Uebersetzungsschluessel'),
    ['Übersetzungsschlüssel']
  );
  eq('upper case is preserved: "FUER" suggests "FÜR"', sugg('NUR FUER ADMINS'), ['FÜR']);
  eq(
    'capitals write ß as SS: "EINSCHLIESSLICH" and "SCHLIESST" stay green',
    words('EINSCHLIESSLICH SCHLIESST'),
    []
  );
  eq('capitals still need umlauts: "GEMAESS" suggests "GEMÄSS"', sugg('GEMAESS ABSATZ'), [
    'GEMÄSS',
  ]);

  // MUST NOT FIRE: legitimate German vowel pairs, and English, that a generic regex hits.
  const clean =
    'neue Quelle Steuer aktuell Dauer zuerst anzueignen Risikoexposition Kontoeinstellungen Nettoeinkommen Massendaten queue request daemon gross';
  eq(
    'legitimate ae/oe/ue/ss words stay green (neue, Quelle, Steuer, aktuell ...)',
    words(clean),
    []
  );
  eq(
    'correctly spelled umlauts stay green',
    words('für über können Größe ausschließlich gemäß'),
    []
  );

  // SKIPPED REGIONS: a transliteration inside markup or code is not prose.
  eq(
    '{{placeholders}}, tags, URLs, code spans and identifiers are skipped',
    words(
      '{{fuer}} <a href="x">ok</a> https://x.de/ueber `koennen` gewaehr_key /etc/fuer a/b/ueber'
    ),
    []
  );
  eq('a prose word next to a skipped region still fires', words('{{n}} fuer <b>x</b>'), ['fuer']);
  eq('a single slash between words is prose: "fuer/gegen" fires', words('fuer/gegen'), ['fuer']);
  eq('a hyphenated compound is prose: "Probe-Laeufen" fires', words('Probe-Laeufen messen'), [
    'Laeufen',
  ]);
  eq('a command-line flag is skipped: "--fuer-alle" stays green', words('mit --fuer-alle'), []);

  // REVIEW d0f72ae5: each control below fails against the rule it replaced.
  eq(
    'a percent sign then a word is not a directive: "5 % fuer alle" fires',
    words('5 % fuer alle'),
    ['fuer']
  );
  eq(
    'a real directive is still skipped: "%s fuer" and "%.12s" leave only the word',
    words('%s fuer %.12s'),
    ['fuer']
  );
  eq(
    'a one-word ICU branch is prose: "one {fuer}" fires',
    words('{n, plural, one {fuer} other {x}}'),
    ['fuer']
  );
  eq(
    'a one-word ICU select branch is prose: "male {fuer}" fires (review d2bb2559.1)',
    words('{g, select, male {fuer} other {x}}'),
    ['fuer']
  );
  eq(
    'CONTROL: a placeholder after a word in an ICU message stays skipped: "Hallo {fuer}, {n, plural, ...}" (review 34ac220b.1)',
    words('Hallo {fuer}, {n, plural, one {x} other {y}}'),
    []
  );
  eq(
    'CONTROL: outside ICU a placeholder after "} word" stays skipped: "{count} Dateien {fuer}" (review b7ee56a2.1)',
    words('{count} Dateien {fuer}'),
    []
  );
  eq(
    'a later select branch after a closing brace is prose: "female {fuer}" fires',
    words('{g, select, male {x} female {fuer} other {y}}'),
    ['fuer']
  );
  eq(
    'CONTROL: Go\'s space flag is still a directive: "% d Kopien" stays green (review d2bb2559.2)',
    words('% d Kopien'),
    []
  );
  eq(
    'a single-brace placeholder is still skipped: "{fuer}" stays green',
    words('Hallo {fuer} ok'),
    []
  );
  eq('a missing space after a period is prose: "Hallo.Fuer alle" fires', words('Hallo.Fuer alle'), [
    'Fuer',
  ]);
  eq(
    'a lower case dotted name is still skipped: "machine.fuer" stays green',
    words('see machine.fuer ok'),
    []
  );
  {
    const body = (rows: string): Record<string, string> => readGoCatalog(rows, 'fixture');
    eq(
      'SetString accepts a dotted tag and a backtick raw literal',
      body('message.SetString(language.German, "k", `Schluessel ungueltig`)\n'),
      { k: 'Schluessel ungueltig' }
    );
    let refusal = '';
    try {
      body('message.SetString(tag, "k", "ok")\nmessage.SetString(tag, key, "x")\n');
    } catch (e) {
      refusal = e instanceof NoVerdict ? e.message : '';
    }
    eq(
      'a SetString call the pattern cannot read is refused as VACUOUS',
      refusal.startsWith('VACUOUS:'),
      true
    );
  }

  // CORPUS: the reader and the empty-corpus verdict, on a temporary tree.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'de-ortho-'));
  try {
    const dir = path.join(tmp, 'de');
    fs.mkdirSync(dir);
    fs.writeFileSync(
      path.join(dir, 'app.json'),
      JSON.stringify({ a: { b: 'Groesse aendern' }, c: ['neue Quelle'] })
    );
    const r = scanCatalogs(readRoot(dir, 'dir'), tmp);
    eq(
      'a dir catalog is read, nested and array keys included',
      [r.strings, r.findings.map((f) => `${f.key}:${f.word}`)],
      [2, ['a.b:Groesse', 'a.b:aendern']]
    );

    const go = path.join(tmp, 'de.go');
    fs.writeFileSync(
      go,
      'message.SetString(tag, "k.one", "Schluessel \\"x\\" ungueltig")\nmessage.SetString(tag, "k.two", "neue Steuer")\n'
    );
    const g = scanCatalogs(readRoot(go, 'go'), tmp);
    eq(
      'a Go catalog is read through its SetString literals',
      [g.strings, g.findings.map((f) => f.word)],
      [2, ['Schluessel', 'ungueltig']]
    );

    const empty = path.join(tmp, 'empty');
    fs.mkdirSync(empty);
    eq(
      'an empty catalog directory reads zero strings (main() turns this into exit 2)',
      scanCatalogs(readRoot(empty, 'dir'), tmp).strings,
      0
    );

    fs.writeFileSync(path.join(empty, 'bad.json'), '{ not json');
    let threw = false;
    try {
      readRoot(empty, 'dir');
    } catch (e) {
      threw = e instanceof NoVerdict;
    }
    eq('an unparseable catalog is NoVerdict, never a silent zero', threw, true);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  return cases;
}

// ----------------------------------------------------------------------------------- main

function main(argv: string[]): number {
  const failed = runControls(controls());
  if (failed > 0) {
    console.error(`✗ ${failed} control(s) failed; the gate cannot be trusted to read German.`);
    return 1;
  }
  if (argv.includes('--selftest')) {
    console.log('✓ check-de-orthography controls passed');
    return 0;
  }

  const rootIdx = argv.indexOf('--root');
  const base = rootIdx >= 0 ? path.resolve(argv[rootIdx + 1]) : REPO_ROOT;

  const scanned: string[] = [];
  const findings: Finding[] = [];
  let strings = 0;
  for (const root of GERMAN_ROOTS) {
    const privateRoot = root.rel.startsWith('private/') && base === REPO_ROOT;
    // submodulePath() honours SUBMODULE_PRESENCE_ROOT, the one seam the submodule tests use.
    const abs = privateRoot ? submodulePath(root.rel) : path.join(base, root.rel);
    if (privateRoot) {
      if (!requireSubmodule(`German orthography of ${root.rel}`, [abs])) continue;
    } else if (!fs.existsSync(abs)) {
      console.error(
        `✗ NO VERDICT: ${root.rel} does not exist. The German catalog moved, or --root is wrong.`
      );
      return 2;
    }
    let result: { findings: Finding[]; strings: number };
    try {
      result = scanCatalogs(readRoot(abs, root.layout), base);
    } catch (e) {
      if (!(e instanceof NoVerdict)) throw e;
      console.error(`✗ NO VERDICT: ${e.message}`);
      return 2;
    }
    if (result.strings === 0) {
      console.error(
        `✗ NO VERDICT: ${root.rel} holds zero German strings; a scan over it would pass while reading nothing.`
      );
      return 2;
    }
    scanned.push(`${root.rel} (${result.strings})`);
    strings += result.strings;
    findings.push(...result.findings);
  }

  if (strings === 0) {
    console.error('✗ NO VERDICT: zero German strings were read across every root.');
    return 2;
  }

  if (base === REPO_ROOT && strings < MIN_GERMAN_STRINGS) {
    console.error(
      `✗ VACUOUS: only ${strings} German strings were read from the real tree, floor ${MIN_GERMAN_STRINGS}; the catalog reader has collapsed, and a clean verdict over it would mean nothing.`
    );
    return 2;
  }

  if (findings.length === 0) {
    console.log(
      `✓ No transliterated German across ${strings} strings in ${scanned.length} root(s), ${TRANSLITERATIONS.length} stems checked:`
    );
    for (const s of scanned) console.log(`    ${s}`);
    return 0;
  }

  return reportFindings({
    header: `✗ ${findings.length} transliterated German word(s) across ${strings} strings:\n`,
    items: findings,
    limit: Infinity,
    indent: '  ',
    format: (f) => `${f.file}  ${f.key}  "${f.word}" -> "${f.suggestion}"  [${f.stems.join(', ')}]`,
    remedy: [
      '',
      'German catalogs are de-DE: write ä, ö, ü and ß, never ae, oe, ue or ss.',
      'Fix the value in the catalog named on each line (renet: edit de.go directly).',
      'If a word is a legitimate spelling the list does not know, narrow the stem in',
      'TRANSLITERATIONS (scripts/gates/check-de-orthography.ts) and add the word to the',
      'must-not-fire control; never exempt a catalog key.',
    ],
  });
}

exitWithMainIfEntryPoint(import.meta.filename, main);

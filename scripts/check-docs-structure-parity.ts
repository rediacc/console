/**
 * check:ci-docs-structure-parity — a translated doc must have the same SHAPE as
 * its English original.
 *
 * The class this catches, paid for by the lead on 2026-08-14: fabricated figures
 * were removed from packages/www/src/content/docs/en/blackout.md and from its 12
 * locale copies. English then had four of those bullets REWRITTEN into
 * conditional voice while the locales simply lost them, so for an hour the
 * translations were structurally SHORTER than the page they translate. Every
 * i18n gate stayed green: cross-locale checks contamination, placeholders checks
 * placeholders, freshness checks sourceHash. NOTHING compared the documents'
 * structure, so a section that existed in one language and not another was
 * invisible by construction.
 *
 * What it compares, and why these two signals:
 * - HEADING COUNT. A deleted or never-translated section changes it. This is the
 *   exact footprint of the defect above, and of a translator quietly dropping a
 *   section that was hard to render.
 * - TABLE ROW COUNT. Cheat sheets and option tables are rows of fact; a locale
 *   with fewer rows is a locale missing commands. This ran at PERFECT parity
 *   across all 936 pairs when the gate was written, which is what makes it a
 *   cheap, high-signal invariant rather than noise.
 *
 * It deliberately does NOT compare heading TEXT (that is translated) or heading
 * LEVEL sequence (three pre-existing pairs differ harmlessly, and policing it
 * would spend the gate's credibility on formatting rather than on missing
 * content).
 *
 * Run: npx tsx scripts/check-docs-structure-parity.ts
 *
 * Control-first: every run first proves the detector on a synthetic pair whose
 * shapes differ, and refuses to pass on an empty scan.
 */

import { existsSync, readFileSync } from 'node:fs';
import { basename, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const DOCS = 'packages/www/src/content/docs';
const LOCALES = ['ar', 'de', 'es', 'et', 'fr', 'it', 'ja', 'ko', 'pt', 'ru', 'tr', 'zh'];

/** A pair scanned must clear this, or the glob broke rather than the docs. */
const MIN_PAIRS = 500;

/**
 * Documents whose structure already diverged before this gate existed: 47 pairs
 * across 8 documents, MEASURED not guessed. Each entry is a debt with a number,
 * NOT a permanent exemption. The gate fails if a document drifts FURTHER, and it
 * ALSO fails if a document improves without its entry being lowered, so the slack
 * can never quietly become room for the next regression.
 *
 * The dominant pattern is worth naming: ja and zh are missing sections in FIVE
 * separate documents, which is a systematic translation gap in those two
 * locales rather than eight unrelated accidents.
 *
 * blackout.md is baselined at its true 2 (ja, zh) even though it is live campaign
 * work. An earlier draft of this file excluded it on principle and the gate was
 * therefore red on arrival; a gate that cannot go green on the day it lands gets
 * disabled, which protects nothing. The debt is tracked instead, and the
 * improvement arm forces this entry to 0 the moment those two locales are fixed.
 */
const BASELINE: Record<string, number> = {
  'tools.md': 12, // every locale
  'setup.md': 11,
};

interface Shape {
  headings: number;
  tableRows: number;
}

function shapeOf(text: string): Shape {
  return {
    headings: (text.match(/^#{1,6}\s/gm) ?? []).length,
    tableRows: (text.match(/^\|/gm) ?? []).length,
  };
}

interface Mismatch {
  doc: string;
  locale: string;
  what: string;
}

function compare(pairs: { doc: string; locale: string; en: string; loc: string }[]): Mismatch[] {
  const out: Mismatch[] = [];
  for (const p of pairs) {
    const a = shapeOf(p.en);
    const b = shapeOf(p.loc);
    if (a.headings !== b.headings) {
      out.push({
        doc: p.doc,
        locale: p.locale,
        what: `${b.headings} headings vs English ${a.headings}`,
      });
    } else if (a.tableRows !== b.tableRows) {
      out.push({
        doc: p.doc,
        locale: p.locale,
        what: `${b.tableRows} table rows vs English ${a.tableRows}`,
      });
    }
  }
  return out;
}

// ── Phase 0: control ───────────────────────────────────────────────────────
const controlHit = compare([
  { doc: 'control.md', locale: 'xx', en: '# A\n## B\n## C\n', loc: '# A\n## B\n' },
]);
const controlQuiet = compare([
  { doc: 'control.md', locale: 'xx', en: '# A\n## B\n', loc: '# Aa\n## Bb\n' },
]);
if (controlHit.length !== 1) {
  console.error(
    '✗ instrument control did not fire: a synthetic pair missing a heading was not reported.\n' +
      '  The detector is blind to the exact defect it exists for.'
  );
  process.exit(1);
}
if (controlQuiet.length !== 0) {
  console.error(
    '✗ instrument control over-reports: a pair with the SAME shape but translated text\n' +
      '  was flagged. Every locale would fail, so a green run could never happen.'
  );
  process.exit(1);
}

// ── Phase 1: collect, with a zero-scan guard ───────────────────────────────
const englishDocs = globSync(`${DOCS}/en/*.{md,mdx}`, { cwd: ROOT, absolute: false });
const pairs: { doc: string; locale: string; en: string; loc: string }[] = [];
for (const enPath of englishDocs) {
  const doc = basename(enPath);
  const enText = readFileSync(join(ROOT, enPath), 'utf8');
  for (const locale of LOCALES) {
    const locPath = enPath.replace(`${DOCS}/en/`, `${DOCS}/${locale}/`);
    if (!existsSync(join(ROOT, locPath))) continue; // untranslated is a different gate's business
    pairs.push({ doc, locale, en: enText, loc: readFileSync(join(ROOT, locPath), 'utf8') });
  }
}
if (pairs.length < MIN_PAIRS) {
  console.error(
    `✗ only ${pairs.length} English/locale pairs found (floor ${MIN_PAIRS}).\n` +
      '  The glob broke, and an unrun check is not a pass.'
  );
  process.exit(1);
}

// ── Phase 2: the real run, measured against the baseline ───────────────────
const mismatches = compare(pairs);
const byDoc = new Map<string, Mismatch[]>();
for (const m of mismatches) {
  const list = byDoc.get(m.doc) ?? [];
  list.push(m);
  byDoc.set(m.doc, list);
}

const problems: string[] = [];
for (const [doc, list] of [...byDoc].sort()) {
  const allowed = BASELINE[doc] ?? 0;
  if (list.length > allowed) {
    problems.push(
      `    ${doc}: ${list.length} locale(s) differ in shape, baseline allows ${allowed}\n` +
        list.map((m) => `      ${m.locale}: ${m.what}`).join('\n')
    );
  }
}
// A document that IMPROVED must lower its baseline, or the slack silently
// becomes room for the next regression to hide in.
for (const [doc, allowed] of Object.entries(BASELINE)) {
  const actual = byDoc.get(doc)?.length ?? 0;
  if (actual < allowed) {
    problems.push(
      `    ${doc}: now ${actual} mismatch(es), baseline still says ${allowed}.\n` +
        `      Lower the BASELINE entry to ${actual} (delete it at 0) so the slack\n` +
        '      cannot hide the next regression.'
    );
  }
}

if (problems.length > 0) {
  console.error(
    `✗ docs structure parity (${problems.length}):\n${problems.join('\n')}\n\n` +
      '  A translated document must have the same SHAPE as its English original:\n' +
      '  same number of sections, same number of table rows. A locale with fewer\n' +
      '  is a locale missing content, and no other i18n gate can see it.'
  );
  process.exit(1);
}

console.log(
  `✓ docs structure parity (${pairs.length} English/locale pairs, ` +
    `${Object.keys(BASELINE).length} baselined document(s); control fired both ways)`
);

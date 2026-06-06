#!/usr/bin/env tsx
/**
 * check-i18n-naturalization — blocking gate for translation naturalization freshness.
 *
 * The naturalization pipeline (private/growth/i18n_pipeline) records, per
 * (language, key), the English CRC32 a translation was last naturalized against, in
 *   packages/www/src/i18n/translations/.naturalized-hashes.json
 *
 * This gate FAILS (exit 1) on EITHER of:
 *  1. STALENESS — a key that was already naturalized has gone stale: its current English
 *     value's CRC32 differs from the recorded one (English changed without re-naturalizing).
 *     Checked for EVERY language present in the ledger (not just one).
 *  2. COVERAGE — a maintained locale (any <lang>.json in the translations dir) is missing
 *     from the ledger or near-empty. Once any language is substantially naturalized it sets
 *     the reference; every maintained locale must reach COVERAGE_FLOOR of that reference so
 *     no language is silently left literal. (Never-naturalized INDIVIDUAL keys are still not
 *     failed — only a whole language being absent/near-empty is.)
 *
 * Fix a failure: regenerate hashes, then re-naturalize ONLY the changed keys:
 *   npm run i18n:generate-hashes
 *   npm run i18n:naturalize-status            # see the exact stale keys
 *   (private/growth/i18n_pipeline) ./run.sh --lang <lang> --surface <surface>
 *
 * See docs/i18n/CONVENTIONS.md.
 *
 * Flags: --report  (verbose per-language breakdown; same exit semantics)
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { flattenAndHash } from './utils/crc32.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TRANSLATIONS_DIR = path.join(__dirname, '../packages/www/src/i18n/translations');
const EN_FILE = path.join(TRANSLATIONS_DIR, 'en.json');
const LEDGER_FILE = path.join(TRANSLATIONS_DIR, '.naturalized-hashes.json');
const DOC = 'docs/i18n/CONVENTIONS.md';

// A maintained locale must reach this fraction of the best-covered language's naturalized
// key count, otherwise it counts as "missing or near-empty". Generous on purpose: every
// language naturalizes ~the same translatable key set, so the real signal is a whole
// language being absent or barely started, not minor per-language count differences.
const COVERAGE_FLOOR = 0.5;

const report = process.argv.includes('--report');

/** Maintained non-English locales = every `<xx>.json` in the translations dir (auto-syncs
 *  with whatever locales the site ships; no hardcoded language list to drift). */
function maintainedLocales(): string[] {
  return fs
    .readdirSync(TRANSLATIONS_DIR)
    .map((f) => /^([a-z]{2})\.json$/.exec(f)?.[1])
    .filter((l): l is string => !!l && l !== 'en')
    .sort();
}

function main(): number {
  if (!fs.existsSync(LEDGER_FILE)) {
    console.log('[i18n-naturalization] no ledger yet — nothing naturalized; skipping.');
    return 0;
  }
  const en = JSON.parse(fs.readFileSync(EN_FILE, 'utf-8')) as Record<string, unknown>;
  const current = flattenAndHash(en, ''); // { "flat.key": "crc32" }
  let ledger: { languages?: Record<string, Record<string, string>> };
  try {
    ledger = JSON.parse(fs.readFileSync(LEDGER_FILE, 'utf-8'));
  } catch (e) {
    console.error(`[i18n-naturalization] could not parse ${LEDGER_FILE}: ${e}`);
    return 1;
  }
  if (!ledger || typeof ledger !== 'object' || typeof ledger.languages !== 'object' || ledger.languages === null) {
    console.log('[i18n-naturalization] ledger has no languages map; nothing to check.');
    return 0;
  }
  const languages = ledger.languages;

  let staleTotal = 0;
  let orphanTotal = 0;
  const staleByLang: Record<string, string[]> = {};
  const langCount: Record<string, number> = {};

  for (const [lang, keys] of Object.entries(languages)) {
    if (!keys || typeof keys !== 'object') continue; // skip malformed language entry
    const stale: string[] = [];
    let orphan = 0;
    for (const [key, recordedCrc] of Object.entries(keys)) {
      const cur = current[key];
      if (cur === undefined) {
        orphan++; // English key deleted — dead ledger entry (not fatal)
        continue;
      }
      if (cur !== recordedCrc) stale.push(key);
    }
    if (stale.length) staleByLang[lang] = stale;
    staleTotal += stale.length;
    orphanTotal += orphan;
    langCount[lang] = Object.keys(keys).length;
  }

  // -- Coverage floor: every maintained locale must reach COVERAGE_FLOOR of the
  //    best-covered language, so no language is silently left literal/untouched. ----
  const targeted = maintainedLocales();
  const maxCount = Math.max(0, ...Object.values(langCount));
  const floor = Math.floor(COVERAGE_FLOOR * maxCount);
  const coverageFails: string[] = []; // langs missing or near-empty (only once a reference exists)
  if (maxCount > 0) {
    for (const lang of targeted) {
      if ((langCount[lang] ?? 0) < floor) coverageFails.push(lang);
    }
  }

  if (report) {
    for (const lang of targeted) {
      const n = langCount[lang] ?? 0;
      const st = staleByLang[lang]?.length ?? 0;
      const mark = n === 0 ? '✗ not naturalized'
        : coverageFails.includes(lang) ? `✗ below floor (${n} < ${floor})`
        : st ? `${st} STALE` : 'ok';
      console.log(`  ${lang}: ${n} naturalized, ${mark}`);
    }
    if (orphanTotal) {
      console.log(`\n${orphanTotal} ledger entries reference deleted English keys ` +
        `(harmless; cleaned on next run).`);
    }
    console.log(`\nCoverage floor: ${Math.round(COVERAGE_FLOOR * 100)}% of the best-covered ` +
      `language (${maxCount} keys) = ${floor}. Individual never-naturalized keys (the ` +
      `backlog within a language) are not failed — only a whole language being absent/near-empty.`);
  }

  if (staleTotal === 0 && coverageFails.length === 0) {
    console.log(`[i18n-naturalization] OK — all ${targeted.length} maintained locales ` +
      `covered and fresh.`);
    return 0;
  }

  if (staleTotal > 0) {
    console.error(`\n[i18n-naturalization] ${staleTotal} naturalized translation(s) are ` +
      `STALE: their English changed but they were not re-naturalized.\n`);
    for (const [lang, keys] of Object.entries(staleByLang)) {
      console.error(`  [${lang}] ${keys.length} stale:`);
      for (const k of keys.slice(0, 8)) console.error(`    ~ ${k}`);
      if (keys.length > 8) console.error(`    ... and ${keys.length - 8} more`);
    }
    console.error(`\nTo fix: re-naturalize ONLY the changed keys (do not re-do everything):`);
    console.error(`  npm run i18n:generate-hashes && npm run i18n:naturalize-status`);
    console.error(`  cd private/growth/i18n_pipeline && ./run.sh --lang <lang> --surface <surface>`);
  }
  if (coverageFails.length > 0) {
    console.error(`\n[i18n-naturalization] ${coverageFails.length} maintained locale(s) are ` +
      `missing or near-empty (below ${floor} keys, the ${Math.round(COVERAGE_FLOOR * 100)}% floor):`);
    for (const lang of coverageFails) {
      console.error(`  ✗ ${lang}: ${langCount[lang] ?? 0} naturalized`);
    }
    console.error(`\nTo fix: naturalize the whole language:`);
    console.error(`  cd private/growth/i18n_pipeline && ./run.sh --lang <lang> --batch --model haiku`);
  }
  console.error(`See ${DOC}.`);
  return 1;
}

// Set exitCode rather than process.exit() so stdout/stderr flush fully in CI.
process.exitCode = main();

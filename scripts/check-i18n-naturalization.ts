#!/usr/bin/env tsx
/**
 * check-i18n-naturalization — blocking gate for translation naturalization freshness.
 *
 * The naturalization pipeline (private/growth/i18n_pipeline) records, per
 * (language, key), the English CRC32 a translation was last naturalized against, in
 *   packages/www/src/i18n/translations/.naturalized-hashes.json
 *
 * This gate FAILS (exit 1) when a key that was already naturalized has gone STALE:
 * its current English value's CRC32 differs from the recorded one (English changed
 * without re-naturalizing). It does NOT fail keys that were never naturalized — that
 * backlog shrinks as more languages/surfaces are naturalized.
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

const report = process.argv.includes('--report');

function main(): number {
  if (!fs.existsSync(LEDGER_FILE)) {
    console.log('[i18n-naturalization] no ledger yet — nothing naturalized; skipping.');
    return 0;
  }
  const en = JSON.parse(fs.readFileSync(EN_FILE, 'utf-8')) as Record<string, unknown>;
  const current = flattenAndHash(en, ''); // { "flat.key": "crc32" }
  const ledger = JSON.parse(fs.readFileSync(LEDGER_FILE, 'utf-8')) as {
    languages?: Record<string, Record<string, string>>;
  };
  const languages = ledger.languages ?? {};

  let staleTotal = 0;
  let orphanTotal = 0;
  const staleByLang: Record<string, string[]> = {};

  for (const [lang, keys] of Object.entries(languages)) {
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
    if (report) {
      console.log(`  ${lang}: ${Object.keys(keys).length} naturalized, ` +
        `${stale.length} STALE, ${orphan} orphaned`);
    }
  }

  if (orphanTotal && report) {
    console.log(`\n${orphanTotal} ledger entries reference deleted English keys ` +
      `(harmless; will be cleaned on next run).`);
  }

  if (staleTotal === 0) {
    console.log(`[i18n-naturalization] OK — all naturalized translations are fresh.`);
    return 0;
  }

  console.error(`\n[i18n-naturalization] ${staleTotal} naturalized translation(s) are ` +
    `STALE: their English changed but they were not re-naturalized.\n`);
  for (const [lang, keys] of Object.entries(staleByLang)) {
    console.error(`  [${lang}] ${keys.length} stale:`);
    for (const k of keys.slice(0, 8)) console.error(`    ~ ${k}`);
    if (keys.length > 8) console.error(`    ... and ${keys.length - 8} more`);
  }
  console.error(`\nTo fix: re-naturalize ONLY the changed keys (do not re-do everything):`);
  console.error(`  npm run i18n:generate-hashes`);
  console.error(`  npm run i18n:naturalize-status`);
  console.error(`  cd private/growth/i18n_pipeline && ./run.sh --lang <lang> --surface <surface>`);
  console.error(`See ${DOC}.`);
  return 1;
}

process.exit(main());

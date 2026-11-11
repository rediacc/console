#!/usr/bin/env tsx
/**
 * i18n-stamp-keys: record a naturalization fingerprint for hand-naturalized www keys that
 * live OUTSIDE the pipeline's surfaces.
 *
 * WHY THIS EXISTS. `check-i18n-ledger-growth.ts` requires every NEW English key to arrive
 * with a fingerprint in `.naturalized-hashes.json` for every locale. The only stamping tool
 * was `private/growth/i18n_pipeline ./run.sh --mark-done --group <selector>`, and that
 * pipeline only knows the homepage/marketing/persona/solution surfaces: on the legal pages
 * it printed "0 stamped, 0 failed parity, 0 stale scanned, 2027 orphans" (measured
 * 2026-11-11 with `--lang de --group pages.termsOfService`). A key no tool can stamp keeps
 * the growth gate red forever, which invites exactly the `--all-stale` shortcut that once
 * stamped 23,561 keys to close 12.
 *
 * WHAT IT WRITES. The fingerprint is the English CRC32 computed by `flattenAndHash` from
 * scripts/lib/crc32.ts, the same function `check-i18n-naturalization.ts` compares against,
 * keyed by the same dotted flat key (array indices as `.0`). Existing ledger entries are
 * never rewritten and never reordered: new entries are appended per language, and the file
 * is re-serialized in the pipeline's own shape (two-space indent, non-ASCII unescaped,
 * trailing newline). An already-stamped key is left alone whether fresh or stale; restamping
 * a stale key would hide the very drift the naturalization gate exists to report.
 *
 * WHAT IT REFUSES, per key: a missing or empty locale value; a value byte-identical to
 * English unless the key is structural (`.id` anchors, `.slug`) or the value carries no
 * letters at all; a {{placeholder}} set that differs from English. Refused keys are listed
 * and left unstamped, and the run exits 1, mirroring the pipeline's --mark-done contract.
 * It refuses an empty prefix: there is no whole-catalog mode.
 *
 * Usage:
 *   npm run i18n:stamp-keys -- --prefix <key-prefix> [--prefix ...] [--lang <l> ...] [--write]
 *
 * Without --write it lists what would be stamped and writes nothing.
 *
 * Exit codes: 0 every targeted key stamped or already stamped; 1 a key was refused or a file
 * could not be read; 2 usage error.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DEFAULT_LOCALE, isSiteLocale, NON_ENGLISH_LOCALES } from '@rediacc/locales';
import { flattenAndHash } from '../lib/crc32.js';
import { isEntryPoint } from '../lib/entry-point.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_TRANSLATIONS_DIR = path.join(HERE, '../../packages/www/src/i18n/translations');
const LEDGER_NAME = '.naturalized-hashes.json';

type Json = Record<string, unknown>;
export type Ledger = Json & { languages?: Record<string, Record<string, string>> };

/** Same walk as flattenAndHash, keeping the string values instead of their CRCs. */
export function flattenValues(node: unknown, prefix = '', out: Record<string, string> = {}) {
  if (Array.isArray(node)) {
    node.forEach((v, i) => flattenValues(v, prefix ? `${prefix}.${i}` : String(i), out));
  } else if (node !== null && typeof node === 'object') {
    for (const [k, v] of Object.entries(node as Json)) {
      flattenValues(v, prefix ? `${prefix}.${k}` : k, out);
    }
  } else if (typeof node === 'string') {
    out[prefix] = node;
  }
  return out;
}

const PLACEHOLDER = /\{\{[^}]*\}\}/g;
const placeholders = (s: string) => (s.match(PLACEHOLDER) ?? []).sort().join('\u0000');

/** A value byte-identical to English is acceptable only where translating it is wrong. */
export function identicalAllowed(key: string, value: string): boolean {
  if (/\.(id|slug)$/.test(key)) return true; // anchors and URL slugs stay byte-identical
  return !/\p{L}/u.test(value); // numbers, symbols, punctuation only
}

export function underPrefix(key: string, prefixes: readonly string[]): boolean {
  return prefixes.some((p) => key === p || key.startsWith(`${p}.`));
}

export interface LangPlan {
  stamp: [string, string][];
  refused: { key: string; reason: string }[];
  alreadyStamped: number;
}

/**
 * The whole judgement, pure so the control drives the same code the CLI does.
 * `enHashes` must come from flattenAndHash so the fingerprint is the gate's own.
 */
export function planStamps(input: {
  enValues: Record<string, string>;
  enHashes: Record<string, string>;
  localeValues: Record<string, Record<string, string>>;
  ledger: Ledger;
  prefixes: readonly string[];
  langs: readonly string[];
}): Record<string, LangPlan> {
  validatePrefixes(input.prefixes);
  const keys = Object.keys(input.enHashes).filter((k) => underPrefix(k, input.prefixes));
  const plans: Record<string, LangPlan> = {};
  for (const lang of input.langs) {
    const stamped = input.ledger.languages?.[lang] ?? {};
    const loc = input.localeValues[lang] ?? {};
    const plan: LangPlan = { stamp: [], refused: [], alreadyStamped: 0 };
    for (const key of keys) {
      if (key in stamped) {
        plan.alreadyStamped++;
        continue;
      }
      const en = input.enValues[key];
      const tr = loc[key];
      if (typeof tr !== 'string' || !tr.trim()) {
        plan.refused.push({ key, reason: 'locale value missing or empty' });
      } else if (tr === en && !identicalAllowed(key, tr)) {
        plan.refused.push({ key, reason: `identical to English: ${JSON.stringify(en)}` });
      } else if (placeholders(tr) !== placeholders(en)) {
        plan.refused.push({ key, reason: 'placeholder set differs from English' });
      } else {
        plan.stamp.push([key, input.enHashes[key]]);
      }
    }
    plans[lang] = plan;
  }
  return plans;
}

export function validatePrefixes(prefixes: readonly string[]): void {
  if (prefixes.length === 0) throw new Error('at least one --prefix is required');
  for (const p of prefixes) {
    if (!p.trim() || p.startsWith('.') || p.endsWith('.')) {
      throw new Error(`refusing prefix ${JSON.stringify(p)}: no whole-catalog mode exists`);
    }
  }
}

/** Append new entries per language; never rewrites or reorders an existing one. */
export function applyStamps(ledger: Ledger, plans: Record<string, LangPlan>): void {
  ledger.languages ??= {};
  for (const [lang, plan] of Object.entries(plans)) {
    const entries = (ledger.languages[lang] ??= {});
    for (const [key, crc] of plan.stamp) {
      if (!(key in entries)) entries[key] = crc;
    }
  }
}

export const serializeLedger = (ledger: Ledger) => `${JSON.stringify(ledger, null, 2)}\n`;

interface Args {
  prefixes: string[];
  langs: string[];
  write: boolean;
}

export function parseArgs(argv: readonly string[]): Args {
  const args: Args = { prefixes: [], langs: [], write: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--write') args.write = true;
    else if (a === '--prefix' || a === '--lang') {
      const v = argv[++i];
      if (v === undefined) throw new Error(`${a} needs a value`);
      (a === '--prefix' ? args.prefixes : args.langs).push(v);
    } else throw new Error(`unknown argument: ${a}`);
  }
  validatePrefixes(args.prefixes);
  for (const l of args.langs) {
    if (!isSiteLocale(l) || l === DEFAULT_LOCALE) {
      throw new Error(`--lang ${l} is not a non-English site locale (@rediacc/locales)`);
    }
  }
  if (args.langs.length === 0) args.langs = [...NON_ENGLISH_LOCALES];
  return args;
}

export function run(argv: readonly string[], dir = DEFAULT_TRANSLATIONS_DIR): number {
  let args: Args;
  try {
    args = parseArgs(argv);
  } catch (e) {
    process.stderr.write(`i18n-stamp-keys: ${(e as Error).message}\n`);
    return 2;
  }
  const read = (name: string) => JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8'));
  const enTree = read('en.json') as Json;
  const ledgerPath = path.join(dir, LEDGER_NAME);
  const ledgerRaw = fs.readFileSync(ledgerPath, 'utf8');
  const ledger = JSON.parse(ledgerRaw) as Ledger;
  if (serializeLedger(JSON.parse(ledgerRaw) as Ledger) !== ledgerRaw) {
    process.stderr.write(
      `i18n-stamp-keys: ${ledgerPath} is not in the pipeline's serialized shape; refusing ` +
        'to rewrite it (a write would reformat unrelated lines).\n'
    );
    return 1;
  }
  const localeValues: Record<string, Record<string, string>> = {};
  for (const l of args.langs) {
    const file = path.join(dir, `${l}.json`);
    if (!fs.existsSync(file)) {
      process.stderr.write(`i18n-stamp-keys: ${file} does not exist for site locale ${l}\n`);
      return 1;
    }
    localeValues[l] = flattenValues(read(`${l}.json`));
  }
  const enHashes = flattenAndHash(enTree, '');
  const plans = planStamps({
    enValues: flattenValues(enTree),
    enHashes,
    localeValues,
    ledger,
    prefixes: args.prefixes,
    langs: args.langs,
  });
  const matched = Object.keys(enHashes).filter((k) => underPrefix(k, args.prefixes)).length;
  if (matched === 0) {
    process.stderr.write(
      `i18n-stamp-keys: no English key under ${args.prefixes.join(', ')}; nothing to stamp.\n`
    );
    return 1;
  }

  let refusedTotal = 0;
  const verb = args.write ? 'stamped' : 'would stamp';
  for (const lang of args.langs) {
    const p = plans[lang];
    refusedTotal += p.refused.length;
    process.stdout.write(
      `  ${lang}: ${verb} ${p.stamp.length}, already stamped ${p.alreadyStamped}, ` +
        `refused ${p.refused.length}\n`
    );
    if (!args.write) for (const [k] of p.stamp) process.stdout.write(`    + ${k}\n`);
    for (const r of p.refused) process.stdout.write(`    ! ${r.key}: ${r.reason}\n`);
  }
  if (args.write) {
    applyStamps(ledger, plans);
    const next = serializeLedger(ledger);
    if (next !== ledgerRaw) fs.writeFileSync(ledgerPath, next);
  } else {
    process.stdout.write('dry run: nothing written (pass --write to stamp)\n');
  }
  if (refusedTotal > 0) {
    process.stderr.write(
      `i18n-stamp-keys: ${refusedTotal} key(s) refused and left unstamped; fix the locale ` +
        'value from the English source, then rerun.\n'
    );
    return 1;
  }
  return 0;
}

if (isEntryPoint(import.meta.filename)) process.exitCode = run(process.argv.slice(2));

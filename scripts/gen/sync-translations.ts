#!/usr/bin/env node
/**
 * Translation Sync Script
 *
 * Adds the keys English has and a locale lacks, with the English value as placeholder.
 * It is insertion-only and byte-preserving: a file with nothing missing is not written,
 * and a file with a delta gets only the missing members spliced in, at the position its
 * own order convention dictates (see scripts/lib/i18n/json-splice.ts). Existing values,
 * key order, indentation and escaping are never rewritten, with one exception: a locale
 * leaf whose English counterpart became an object or array takes English's shape, because
 * a string cannot stand where English now has a container. Keys a locale has and English
 * lacks are reported, never deleted: removal is the documented manual procedure.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SITE_LOCALES } from '@rediacc/locales';
import { countLeaves, extraPaths, type JsonValue, spliceMissing } from '../lib/i18n/json-splice.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SOURCE_LANG = 'en';
const TARGET_LANGS = SITE_LOCALES.filter((l) => l !== SOURCE_LANG);
/** A directory-layout locale tree with no English namespace file is not being seen; refuse rather than report a clean sync. */
const MIN_NAMESPACES = 1;

export interface LocaleConfig {
  name: string;
  dir: string;
  /** Flat layout: translations are {dir}/{lang}.json instead of {dir}/{lang}/*.json */
  flatFiles?: boolean;
}

const LOCALE_CONFIGS: LocaleConfig[] = [
  {
    name: 'cli',
    dir: path.join(__dirname, '../../packages/cli/src/i18n/locales'),
  },
  {
    name: 'www',
    dir: path.join(__dirname, '../../packages/www/src/i18n/translations'),
    flatFiles: true,
  },
  {
    name: 'account-web',
    dir: path.join(__dirname, '../../private/account/web/src/i18n/locales'),
  },
  {
    name: 'account-emails',
    dir: path.join(__dirname, '../../private/account/src/i18n/locales'),
  },
];

/**
 * The locale set has one source (@rediacc/locales). A tree that lacks a site locale, or
 * carries one the registry does not know, is an error: a skip is how locales go unprotected.
 */
function assertLocaleSet(name: string, found: string[]): void {
  const want = [...TARGET_LANGS].sort((a, b) => a.localeCompare(b));
  const have = [...found].sort((a, b) => a.localeCompare(b));
  if (want.join() !== have.join()) {
    throw new Error(
      `[${name}] locale set differs from @rediacc/locales: expected ${want.join(', ')}; found ${have.join(', ')}`
    );
  }
}

/**
 * The single write site. The target is whatever locale file the caller's config names, so a
 * run against the repo tree rewrites the repo locales; the control calls syncLocaleDir only
 * with a mkdtemp fixture.
 */
function writeLocaleFile(file: string, text: string): void {
  // tree-write: safe the target is the caller's locale file: the repo locales only when syncLocaleDir is given a repo config, as main() does; the check:ci-i18n-sync control gives it a mkdtemp fixture
  fs.mkdirSync(path.dirname(file), { recursive: true });
  // tree-write: safe same target as the mkdir above: the caller's locale file, a mkdtemp fixture under the control
  fs.writeFileSync(file, text);
}

/** Sync one target file; returns leaves added and extra paths. Writes only on a real delta. */
function syncFile(
  langFile: string,
  source: JsonValue
): { added: number; extras: string[]; written: boolean } {
  if (!fs.existsSync(langFile)) {
    writeLocaleFile(langFile, JSON.stringify(source, null, 2) + '\n');
    return { added: countLeaves(source), extras: [], written: true };
  }
  const text = fs.readFileSync(langFile, 'utf-8');
  const result = spliceMissing(text, source);
  const extras = extraPaths(JSON.parse(text) as JsonValue, source);
  if (result.text !== text) writeLocaleFile(langFile, result.text);
  return { added: result.added, extras, written: result.text !== text };
}

export function syncLocaleDir(config: LocaleConfig): { added: number; extras: number } {
  const { name, dir, flatFiles } = config;
  let totalAdded = 0;
  let totalExtras = 0;
  const report = (label: string, r: { added: number; extras: string[] }) => {
    totalAdded += r.added;
    totalExtras += r.extras.length;
    if (r.added > 0) console.log(`   ${label}: +${r.added} added`);
    for (const x of r.extras) console.log(`   ${label}: extra key not in English (kept): ${x}`);
  };

  if (flatFiles) {
    const enFile = path.join(dir, `${SOURCE_LANG}.json`);
    if (!fs.existsSync(enFile)) {
      console.log(`\nSkipping ${name}: English file not found at ${enFile}`);
      return { added: 0, extras: 0 };
    }
    const languages = fs
      .readdirSync(dir)
      .filter((f) => f !== `${SOURCE_LANG}.json` && !f.startsWith('.') && f.endsWith('.json'))
      .map((f) => f.replace('.json', ''));
    assertLocaleSet(name, languages);
    console.log(`\n[${name}] Directory: ${dir}`);
    const english = JSON.parse(fs.readFileSync(enFile, 'utf-8')) as JsonValue;
    for (const lang of languages) {
      report(lang, syncFile(path.join(dir, `${lang}.json`), english));
    }
    return { added: totalAdded, extras: totalExtras };
  }

  const englishDir = path.join(dir, SOURCE_LANG);
  if (!fs.existsSync(englishDir)) {
    console.log(`\nSkipping ${name}: English directory not found at ${englishDir}`);
    return { added: 0, extras: 0 };
  }
  const languages = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== SOURCE_LANG)
    .map((d) => d.name);
  assertLocaleSet(name, languages);
  console.log(`\n[${name}] Locales directory: ${dir}`);
  const namespaces = fs
    .readdirSync(englishDir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.replace('.json', ''));
  if (namespaces.length < MIN_NAMESPACES) {
    throw new Error(
      `[${name}] VACUOUS: ${englishDir} lists ${namespaces.length} namespace file(s), floor ${MIN_NAMESPACES}; a sync over nothing would print success and sync nothing`
    );
  }
  for (const namespace of namespaces) {
    const english = JSON.parse(
      fs.readFileSync(path.join(englishDir, `${namespace}.json`), 'utf-8')
    ) as JsonValue;
    for (const lang of languages) {
      report(`${namespace}/${lang}`, syncFile(path.join(dir, lang, `${namespace}.json`), english));
    }
  }
  return { added: totalAdded, extras: totalExtras };
}

async function main(): Promise<void> {
  console.log('Translation Sync Script\n');
  console.log(`Source language: ${SOURCE_LANG}`);
  console.log('\u2500'.repeat(60));
  let totalAdded = 0;
  let totalExtras = 0;
  for (const config of LOCALE_CONFIGS) {
    const result = syncLocaleDir(config);
    totalAdded += result.added;
    totalExtras += result.extras;
  }
  console.log('\n' + '\u2500'.repeat(60));
  console.log(`\nSync complete!`);
  console.log(`   Total keys added: ${totalAdded}`);
  console.log(`   Extra keys kept (not in English): ${totalExtras}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((err: unknown) => {
    console.error(err);
    process.exit(1);
  });
}

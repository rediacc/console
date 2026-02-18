#!/usr/bin/env node
/**
 * Translation Sync Script
 *
 * Syncs missing translation keys from English (source of truth) to all other languages.
 * Missing keys are filled with English values as placeholders.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SOURCE_LANG = 'en';

interface LocaleConfig {
  name: string;
  dir: string;
  /** Flat layout: translations are {dir}/{lang}.json instead of {dir}/{lang}/*.json */
  flatFiles?: boolean;
}

const LOCALE_CONFIGS: LocaleConfig[] = [
  {
    name: 'web',
    dir: path.join(__dirname, '../packages/web/src/i18n/locales'),
  },
  {
    name: 'cli',
    dir: path.join(__dirname, '../packages/cli/src/i18n/locales'),
  },
  {
    name: 'www',
    dir: path.join(__dirname, '../packages/www/src/i18n/translations'),
    flatFiles: true,
  },
];

type TranslationValue = string | TranslationObject;
type TranslationObject = Record<string, TranslationValue>;

/**
 * Recursively sort object keys alphabetically
 */
function sortKeys(obj: TranslationValue): TranslationValue {
  if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
    return obj;
  }

  const sorted: TranslationObject = {};
  const keys = Object.keys(obj).sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
  );

  for (const key of keys) {
    sorted[key] = sortKeys(obj[key]);
  }

  return sorted;
}

/**
 * Deep merge source into target, only adding missing keys
 * Handles structure mismatches by preferring source structure
 */
function mergeTranslations(target: TranslationObject, source: TranslationObject): TranslationObject {
  const result = { ...target };

  for (const [key, value] of Object.entries(source)) {
    if (!(key in result)) {
      // Key missing in target - add from source
      result[key] = value;
    } else {
      const sourceIsObject = typeof value === 'object' && value !== null && !Array.isArray(value);
      const targetIsObject =
        typeof result[key] === 'object' && result[key] !== null && !Array.isArray(result[key]);

      if (sourceIsObject && targetIsObject) {
        // Both are objects - merge recursively
        result[key] = mergeTranslations(
          result[key] as TranslationObject,
          value as TranslationObject
        );
      } else if (sourceIsObject && !targetIsObject) {
        // Source is object but target is not - use source structure
        result[key] = value;
      }
      // If both are strings/primitives, keep target value (existing translation)
    }
  }

  return result;
}

/**
 * Remove keys from target that don't exist in source
 */
function removeExtraKeys(target: TranslationObject, source: TranslationObject): TranslationObject {
  const result: TranslationObject = {};

  for (const [key, value] of Object.entries(target)) {
    if (!(key in source)) {
      // Key doesn't exist in source - skip (remove)
      continue;
    }

    if (
      typeof value === 'object' &&
      value !== null &&
      !Array.isArray(value) &&
      typeof source[key] === 'object' &&
      source[key] !== null &&
      !Array.isArray(source[key])
    ) {
      // Both are objects - recurse
      result[key] = removeExtraKeys(
        value as TranslationObject,
        source[key] as TranslationObject
      );
    } else {
      // Keep the value
      result[key] = value;
    }
  }

  return result;
}

/**
 * Count keys in an object recursively
 */
function countKeys(obj: TranslationObject): number {
  let count = 0;

  for (const [, value] of Object.entries(obj)) {
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      count += countKeys(value as TranslationObject);
    } else {
      count += 1;
    }
  }

  return count;
}

function syncLocaleDir(config: LocaleConfig): { added: number; removed: number } {
  const { name, dir, flatFiles } = config;

  // Flat layout: {dir}/en.json, {dir}/fr.json, etc.
  if (flatFiles) {
    const enFile = path.join(dir, `${SOURCE_LANG}.json`);
    if (!fs.existsSync(enFile)) {
      console.log(`\nSkipping ${name}: English file not found at ${enFile}`);
      return { added: 0, removed: 0 };
    }

    const languages = fs
      .readdirSync(dir)
      .filter((f) => f !== `${SOURCE_LANG}.json` && !f.startsWith('.') && f.endsWith('.json'))
      .map((f) => f.replace('.json', ''));

    console.log(`\n[${name}] Directory: ${dir}`);
    console.log(`[${name}] Target languages: ${languages.join(', ')}`);

    const englishContent = JSON.parse(fs.readFileSync(enFile, 'utf-8')) as TranslationObject;
    const englishKeyCount = countKeys(englishContent);
    console.log(`\n${SOURCE_LANG}.json (${englishKeyCount} keys in English)`);

    let totalAdded = 0;
    let totalRemoved = 0;

    for (const lang of languages) {
      const langFile = path.join(dir, `${lang}.json`);
      let langContent: TranslationObject = {};
      if (fs.existsSync(langFile)) {
        langContent = JSON.parse(fs.readFileSync(langFile, 'utf-8')) as TranslationObject;
      }

      const beforeCount = countKeys(langContent);
      const cleaned = removeExtraKeys(langContent, englishContent);
      const afterCleanCount = countKeys(cleaned);
      const removed = beforeCount - afterCleanCount;
      const merged = mergeTranslations(cleaned, englishContent);
      const afterMergeCount = countKeys(merged);
      const added = afterMergeCount - afterCleanCount;
      const sorted = sortKeys(merged) as TranslationObject;
      fs.writeFileSync(langFile, JSON.stringify(sorted, null, 2) + '\n');

      if (added > 0 || removed > 0) {
        console.log(`   ${lang}: +${added} added, -${removed} removed`);
        totalAdded += added;
        totalRemoved += removed;
      }
    }

    return { added: totalAdded, removed: totalRemoved };
  }

  // Directory layout: {dir}/en/*.json, {dir}/fr/*.json, etc.
  const englishDir = path.join(dir, SOURCE_LANG);

  if (!fs.existsSync(englishDir)) {
    console.log(`\nSkipping ${name}: English directory not found at ${englishDir}`);
    return { added: 0, removed: 0 };
  }

  // Get all language directories
  const languages = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== SOURCE_LANG)
    .map((d) => d.name);

  console.log(`\n[${name}] Locales directory: ${dir}`);
  console.log(`[${name}] Target languages: ${languages.join(', ')}`);

  // Get all English locale files
  const namespaces = fs
    .readdirSync(englishDir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.replace('.json', ''));

  console.log(`[${name}] Namespaces: ${namespaces.join(', ')}`);

  let totalAdded = 0;
  let totalRemoved = 0;

  for (const namespace of namespaces) {
    const englishFile = path.join(englishDir, `${namespace}.json`);
    const englishContent = JSON.parse(fs.readFileSync(englishFile, 'utf-8')) as TranslationObject;
    const englishKeyCount = countKeys(englishContent);

    console.log(`\n${namespace}.json (${englishKeyCount} keys in English)`);

    for (const lang of languages) {
      const langDir = path.join(dir, lang);
      const langFile = path.join(langDir, `${namespace}.json`);

      let langContent: TranslationObject = {};
      if (fs.existsSync(langFile)) {
        langContent = JSON.parse(fs.readFileSync(langFile, 'utf-8')) as TranslationObject;
      }

      const beforeCount = countKeys(langContent);

      // Remove extra keys not in English
      const cleaned = removeExtraKeys(langContent, englishContent);
      const afterCleanCount = countKeys(cleaned);
      const removed = beforeCount - afterCleanCount;

      // Merge missing keys from English
      const merged = mergeTranslations(cleaned, englishContent);
      const afterMergeCount = countKeys(merged);
      const added = afterMergeCount - afterCleanCount;

      // Sort keys alphabetically
      const sorted = sortKeys(merged) as TranslationObject;

      // Write back
      fs.writeFileSync(langFile, JSON.stringify(sorted, null, 2) + '\n');

      if (added > 0 || removed > 0) {
        console.log(`   ${lang}: +${added} added, -${removed} removed`);
        totalAdded += added;
        totalRemoved += removed;
      }
    }
  }

  return { added: totalAdded, removed: totalRemoved };
}

async function main(): Promise<void> {
  console.log('Translation Sync Script\n');
  console.log(`Source language: ${SOURCE_LANG}`);
  console.log('\u2500'.repeat(60));

  let totalAdded = 0;
  let totalRemoved = 0;

  for (const config of LOCALE_CONFIGS) {
    const result = syncLocaleDir(config);
    totalAdded += result.added;
    totalRemoved += result.removed;
  }

  console.log('\n' + '\u2500'.repeat(60));
  console.log(`\nSync complete!`);
  console.log(`   Total keys added: ${totalAdded}`);
  console.log(`   Total keys removed: ${totalRemoved}`);
}

main().catch(console.error);

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
const LOCALES_DIR = path.join(__dirname, '../packages/web/src/i18n/locales');
const SOURCE_LANG = 'en';

/**
 * Recursively sort object keys alphabetically
 */
function sortKeys(obj) {
  if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
    return obj;
  }

  const sorted = {};
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
function mergeTranslations(target, source) {
  const result = { ...target };

  for (const [key, value] of Object.entries(source)) {
    if (!(key in result)) {
      // Key missing in target - add from source
      result[key] = value;
    } else {
      const sourceIsObject = typeof value === 'object' && value !== null && !Array.isArray(value);
      const targetIsObject = typeof result[key] === 'object' && result[key] !== null && !Array.isArray(result[key]);

      if (sourceIsObject && targetIsObject) {
        // Both are objects - merge recursively
        result[key] = mergeTranslations(result[key], value);
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
function removeExtraKeys(target, source) {
  const result = {};

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
      result[key] = removeExtraKeys(value, source[key]);
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
function countKeys(obj, prefix = '') {
  let count = 0;

  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      count += countKeys(value, `${prefix}${key}.`);
    } else {
      count += 1;
    }
  }

  return count;
}

async function main() {
  console.log('🌐 Translation Sync Script\n');
  console.log(`Source language: ${SOURCE_LANG}`);
  console.log(`Locales directory: ${LOCALES_DIR}\n`);

  // Get all language directories
  const languages = fs.readdirSync(LOCALES_DIR, { withFileTypes: true })
    .filter(d => d.isDirectory() && d.name !== SOURCE_LANG)
    .map(d => d.name);

  console.log(`Target languages: ${languages.join(', ')}\n`);

  // Get all English locale files
  const englishDir = path.join(LOCALES_DIR, SOURCE_LANG);
  const namespaces = fs.readdirSync(englishDir)
    .filter(f => f.endsWith('.json'))
    .map(f => f.replace('.json', ''));

  console.log(`Namespaces: ${namespaces.join(', ')}\n`);
  console.log('─'.repeat(60));

  let totalAdded = 0;
  let totalRemoved = 0;

  for (const namespace of namespaces) {
    const englishFile = path.join(englishDir, `${namespace}.json`);
    const englishContent = JSON.parse(fs.readFileSync(englishFile, 'utf-8'));
    const englishKeyCount = countKeys(englishContent);

    console.log(`\n📁 ${namespace}.json (${englishKeyCount} keys in English)`);

    for (const lang of languages) {
      const langDir = path.join(LOCALES_DIR, lang);
      const langFile = path.join(langDir, `${namespace}.json`);

      let langContent = {};
      let existed = false;

      if (fs.existsSync(langFile)) {
        langContent = JSON.parse(fs.readFileSync(langFile, 'utf-8'));
        existed = true;
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
      const sorted = sortKeys(merged);

      // Write back
      fs.writeFileSync(langFile, JSON.stringify(sorted, null, 2) + '\n');

      if (added > 0 || removed > 0) {
        console.log(`   ${lang}: +${added} added, -${removed} removed`);
        totalAdded += added;
        totalRemoved += removed;
      }
    }
  }

  console.log('\n' + '─'.repeat(60));
  console.log(`\n✅ Sync complete!`);
  console.log(`   Total keys added: ${totalAdded}`);
  console.log(`   Total keys removed: ${totalRemoved}`);
}

main().catch(console.error);

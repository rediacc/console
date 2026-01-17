#!/usr/bin/env node
/**
 * Translation Hash Generation Script for WWW
 *
 * Generates CRC32 hashes for all English translation values.
 * The hash manifest (.translation-hashes.json) is used by ESLint
 * to detect when English values change, indicating stale translations.
 *
 * WWW uses a single file per language: translations/{lang}.json
 *
 * Usage:
 *   node scripts/generate-translation-hashes.js
 *   npm run i18n:generate-hashes
 *   npm run i18n:update-hashes (alias)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TRANSLATIONS_DIR = path.join(__dirname, '../src/i18n/translations');
const HASH_FILENAME = '.translation-hashes.json';
const SOURCE_LANG = 'en';

/**
 * Calculate CRC32 hash of a string (IEEE polynomial)
 * Returns 8-character lowercase hex string
 */
const crc32Table = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c;
  }
  return table;
})();

function crc32(str) {
  let crc = 0xffffffff;
  for (let i = 0; i < str.length; i++) {
    const byte = str.charCodeAt(i) & 0xff;
    crc = crc32Table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return ((crc ^ 0xffffffff) >>> 0).toString(16).padStart(8, '0');
}

/**
 * Flatten a JSON object and calculate hashes for all string values
 */
function flattenAndHash(obj, prefix = '') {
  const hashes = {};

  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(hashes, flattenAndHash(value, fullPath));
    } else if (typeof value === 'string') {
      hashes[fullPath] = crc32(value);
    }
  }

  return hashes;
}

/**
 * Sort object keys alphabetically
 */
function sortObjectKeys(obj) {
  const sorted = {};
  const keys = Object.keys(obj).sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
  );
  for (const key of keys) {
    sorted[key] = obj[key];
  }
  return sorted;
}

async function main() {
  console.log('Translation Hash Generation (WWW)');
  console.log(''.padEnd(60, '='));
  console.log();

  const englishFilePath = path.join(TRANSLATIONS_DIR, `${SOURCE_LANG}.json`);

  if (!fs.existsSync(englishFilePath)) {
    console.error(`Error: English translation file not found at ${englishFilePath}`);
    process.exit(1);
  }

  console.log(`Reading: ${englishFilePath}`);

  const englishContent = JSON.parse(fs.readFileSync(englishFilePath, 'utf-8'));
  const hashes = flattenAndHash(englishContent);

  // Note: We intentionally omit timestamps to reduce merge conflicts
  const manifest = {
    $meta: {
      algorithm: 'crc32',
      sourceLanguage: SOURCE_LANG,
      keyCount: Object.keys(hashes).length,
    },
    hashes: sortObjectKeys(hashes),
  };

  const outputPath = path.join(TRANSLATIONS_DIR, HASH_FILENAME);
  fs.writeFileSync(outputPath, JSON.stringify(manifest, null, 2) + '\n');

  console.log();
  console.log(''.padEnd(60, '='));
  console.log('Generation complete!');
  console.log();
  console.log(`  Keys hashed: ${Object.keys(hashes).length}`);
  console.log(`  Output: ${outputPath}`);
  console.log();
  console.log('Hash manifest is now up-to-date.');
  console.log('Commit this file along with your translation changes.');
}

main().catch((err) => {
  console.error('Error generating hashes:', err);
  process.exit(1);
});

#!/usr/bin/env node
/**
 * Translation Hash Generation Script
 *
 * Generates CRC32 hashes for all English translation values.
 * The hash manifest (.translation-hashes.json) is used by ESLint
 * to detect when English values change, indicating stale translations.
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

// Configuration for each locale directory
const LOCALE_CONFIGS = [
  {
    name: 'web',
    dir: path.join(__dirname, '../packages/web/src/i18n/locales'),
    // Web has multiple namespace files (common.json, auth.json, etc.)
    multipleNamespaces: true,
  },
  {
    name: 'cli',
    dir: path.join(__dirname, '../packages/cli/src/i18n/locales'),
    // CLI has single file per language (cli.json)
    multipleNamespaces: false,
  },
];

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

/**
 * Process a locale directory and generate hash manifest
 */
function processLocaleDir(config) {
  const { name, dir, multipleNamespaces } = config;
  const englishDir = path.join(dir, SOURCE_LANG);

  if (!fs.existsSync(englishDir)) {
    console.log(`   Skipping ${name}: English directory not found at ${englishDir}`);
    return null;
  }

  const allHashes = {};

  if (multipleNamespaces) {
    // Web: Process each namespace file (common.json, auth.json, etc.)
    const files = fs.readdirSync(englishDir).filter(f => f.endsWith('.json'));

    for (const file of files) {
      const namespace = file.replace('.json', '');
      const filePath = path.join(englishDir, file);
      const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));

      // Prefix keys with namespace (e.g., common.welcome, auth.login)
      const hashes = flattenAndHash(content, namespace);
      Object.assign(allHashes, hashes);
    }
  } else {
    // CLI: Process single file per language
    const files = fs.readdirSync(englishDir).filter(f => f.endsWith('.json'));

    for (const file of files) {
      const filePath = path.join(englishDir, file);
      const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));

      // No namespace prefix for CLI (flat keys)
      const hashes = flattenAndHash(content, '');
      Object.assign(allHashes, hashes);
    }
  }

  return allHashes;
}

/**
 * Write hash manifest file
 */
function writeHashManifest(dir, hashes, name) {
  // Note: We intentionally omit timestamps to reduce merge conflicts
  const manifest = {
    $meta: {
      algorithm: 'crc32',
      sourceLanguage: SOURCE_LANG,
      keyCount: Object.keys(hashes).length,
    },
    hashes: sortObjectKeys(hashes),
  };

  const outputPath = path.join(dir, HASH_FILENAME);
  fs.writeFileSync(outputPath, JSON.stringify(manifest, null, 2) + '\n');

  console.log(`   ${name}: ${Object.keys(hashes).length} keys -> ${outputPath}`);
  return outputPath;
}

async function main() {
  console.log('Translation Hash Generation');
  console.log(''.padEnd(60, '='));
  console.log();

  const results = [];

  for (const config of LOCALE_CONFIGS) {
    console.log(`Processing ${config.name}...`);

    const hashes = processLocaleDir(config);
    if (hashes) {
      const outputPath = writeHashManifest(config.dir, hashes, config.name);
      results.push({ name: config.name, path: outputPath, keyCount: Object.keys(hashes).length });
    }
  }

  console.log();
  console.log(''.padEnd(60, '='));
  console.log('Generation complete!');
  console.log();

  for (const result of results) {
    console.log(`  ${result.name}: ${result.keyCount} keys hashed`);
  }

  console.log();
  console.log('Hash manifests are now up-to-date.');
  console.log('Commit these files along with your translation changes.');
}

main().catch((err) => {
  console.error('Error generating hashes:', err);
  process.exit(1);
});

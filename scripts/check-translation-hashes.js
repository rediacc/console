#!/usr/bin/env node
/**
 * Pre-commit check: Verify translation hash manifests are up-to-date
 *
 * This script compares current English translation hashes with stored manifests.
 * If they differ, it means English values changed but hashes weren't regenerated.
 *
 * Usage:
 *   node scripts/check-translation-hashes.js
 *   npm run i18n:check-hashes
 *
 * Exit codes:
 *   0 - All hashes are up-to-date
 *   1 - Hash mismatch detected (need to run i18n:generate-hashes)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// CRC32 implementation (IEEE polynomial)
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

function checkLocaleDir(name, localeDir, useNamespacePrefix = true) {
  const hashFile = path.join(localeDir, '.translation-hashes.json');
  const errors = [];

  if (!fs.existsSync(hashFile)) {
    errors.push(`Hash manifest not found: ${hashFile}`);
    return errors;
  }

  const manifest = JSON.parse(fs.readFileSync(hashFile, 'utf-8'));
  const storedHashes = manifest.hashes || {};

  // Get all English JSON files in the locale directory
  const enDir = path.join(localeDir, 'en');
  if (!fs.existsSync(enDir)) {
    errors.push(`English locale directory not found: ${enDir}`);
    return errors;
  }

  const currentHashes = {};
  const jsonFiles = fs.readdirSync(enDir).filter((f) => f.endsWith('.json'));

  for (const file of jsonFiles) {
    // Web: use namespace prefix (common.welcome, auth.login)
    // CLI: no namespace prefix (flat keys)
    const namespace = useNamespacePrefix ? file.replace('.json', '') : '';
    const content = JSON.parse(fs.readFileSync(path.join(enDir, file), 'utf-8'));
    const fileHashes = flattenAndHash(content, namespace);
    Object.assign(currentHashes, fileHashes);
  }

  // Compare hashes
  const staleKeys = [];
  const newKeys = [];

  for (const [key, hash] of Object.entries(currentHashes)) {
    if (!(key in storedHashes)) {
      newKeys.push(key);
    } else if (storedHashes[key] !== hash) {
      staleKeys.push(key);
    }
  }

  if (staleKeys.length > 0) {
    errors.push(`[${name}] English values changed for ${staleKeys.length} key(s):`);
    staleKeys.slice(0, 5).forEach((k) => errors.push(`  - ${k}`));
    if (staleKeys.length > 5) {
      errors.push(`  ... and ${staleKeys.length - 5} more`);
    }
  }

  if (newKeys.length > 0) {
    errors.push(`[${name}] New keys not in hash manifest: ${newKeys.length}`);
    newKeys.slice(0, 5).forEach((k) => errors.push(`  - ${k}`));
    if (newKeys.length > 5) {
      errors.push(`  ... and ${newKeys.length - 5} more`);
    }
  }

  return errors;
}

function main() {
  const errors = [];

  // Check web locales (uses namespace prefixes like common.welcome, auth.login)
  const webLocales = path.join(__dirname, '../packages/web/src/i18n/locales');
  if (fs.existsSync(webLocales)) {
    errors.push(...checkLocaleDir('web', webLocales, true));
  }

  // Check CLI locales (no namespace prefix - flat keys)
  const cliLocales = path.join(__dirname, '../packages/cli/src/i18n/locales');
  if (fs.existsSync(cliLocales)) {
    errors.push(...checkLocaleDir('cli', cliLocales, false));
  }

  if (errors.length > 0) {
    console.error('Translation hash check FAILED:\n');
    errors.forEach((e) => console.error(e));
    console.error('\nTo fix, run: npm run i18n:generate-hashes');
    process.exit(1);
  }

  console.log('Translation hashes are up-to-date.');
  process.exit(0);
}

main();

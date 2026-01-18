#!/usr/bin/env node
/**
 * Pre-commit check: Verify translation hash manifests are up-to-date
 *
 * This script compares current English translation hashes with stored manifests.
 * If they differ, it means English values changed but hashes weren't regenerated.
 *
 * Usage:
 *   npx tsx scripts/check-translation-hashes.ts
 *   npm run i18n:check-hashes
 *
 * Exit codes:
 *   0 - All hashes are up-to-date
 *   1 - Hash mismatch detected (need to run i18n:generate-hashes)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { flattenAndHash } from './utils/crc32.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

interface HashManifest {
  hashes: Record<string, string>;
}

function checkLocaleDir(name: string, localeDir: string, useNamespacePrefix = true): string[] {
  const hashFile = path.join(localeDir, '.translation-hashes.json');
  const errors: string[] = [];

  if (!fs.existsSync(hashFile)) {
    errors.push(`Hash manifest not found: ${hashFile}`);
    return errors;
  }

  const manifest = JSON.parse(fs.readFileSync(hashFile, 'utf-8')) as HashManifest;
  const storedHashes = manifest.hashes || {};

  // Get all English JSON files in the locale directory
  const enDir = path.join(localeDir, 'en');
  if (!fs.existsSync(enDir)) {
    errors.push(`English locale directory not found: ${enDir}`);
    return errors;
  }

  const currentHashes: Record<string, string> = {};
  const jsonFiles = fs.readdirSync(enDir).filter((f) => f.endsWith('.json'));

  for (const file of jsonFiles) {
    // Web: use namespace prefix (common.welcome, auth.login)
    // CLI: no namespace prefix (flat keys)
    const namespace = useNamespacePrefix ? file.replace('.json', '') : '';
    const content = JSON.parse(
      fs.readFileSync(path.join(enDir, file), 'utf-8')
    ) as Record<string, unknown>;
    const fileHashes = flattenAndHash(content, namespace);
    Object.assign(currentHashes, fileHashes);
  }

  // Compare hashes
  const staleKeys: string[] = [];
  const newKeys: string[] = [];

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

function main(): void {
  const errors: string[] = [];

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

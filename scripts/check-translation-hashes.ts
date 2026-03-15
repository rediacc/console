#!/usr/bin/env node
/**
 * Pre-commit check: Verify translation hash manifests are up-to-date
 *
 * This script compares current English translation hashes with stored manifests.
 * If they differ, it means English values changed but hashes weren't regenerated.
 *
 * When sourceCommit is available in the manifest, the script shows what changed
 * (old value → new value) so AI systems and humans know exactly what to update
 * in translations.
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
import {
  diffJsonTranslations,
  flattenJson,
  getFileAtCommit,
  type TranslationChange,
} from './utils/translation-diff.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

interface HashManifest {
  $meta?: {
    sourceCommit?: string;
  };
  hashes: Record<string, string>;
}

interface LocaleCheckConfig {
  name: string;
  dir: string;
  useNamespacePrefix: boolean;
  flatFiles: boolean;
}

const LOCALE_CONFIGS: LocaleCheckConfig[] = [
  { name: 'web', dir: path.join(__dirname, '../packages/web/src/i18n/locales'), useNamespacePrefix: true, flatFiles: false },
  { name: 'cli', dir: path.join(__dirname, '../packages/cli/src/i18n/locales'), useNamespacePrefix: false, flatFiles: false },
  { name: 'www', dir: path.join(__dirname, '../packages/www/src/i18n/translations'), useNamespacePrefix: false, flatFiles: true },
  { name: 'account-web', dir: path.join(__dirname, '../private/account/web/src/i18n/locales'), useNamespacePrefix: true, flatFiles: false },
  { name: 'account-emails', dir: path.join(__dirname, '../private/account/src/i18n/locales'), useNamespacePrefix: false, flatFiles: false },
];

function loadEnglishFlat(config: LocaleCheckConfig): Record<string, string> | null {
  if (config.flatFiles) {
    const enFile = path.join(config.dir, 'en.json');
    if (!fs.existsSync(enFile)) return null;
    const content = JSON.parse(fs.readFileSync(enFile, 'utf-8')) as Record<string, unknown>;
    return flattenJson(content, '');
  }

  const enDir = path.join(config.dir, 'en');
  if (!fs.existsSync(enDir)) return null;

  const result: Record<string, string> = {};
  const jsonFiles = fs.readdirSync(enDir).filter((f) => f.endsWith('.json'));

  for (const file of jsonFiles) {
    const namespace = config.useNamespacePrefix ? file.replace('.json', '') : '';
    const content = JSON.parse(
      fs.readFileSync(path.join(enDir, file), 'utf-8')
    ) as Record<string, unknown>;
    Object.assign(result, flattenJson(content, namespace));
  }

  return result;
}

/**
 * Try to load the old English translations from git using sourceCommit.
 */
function loadOldEnglishFlat(config: LocaleCheckConfig, sourceCommit: string): Record<string, string> | null {
  const relDir = path.relative(REPO_ROOT, config.dir);

  if (config.flatFiles) {
    const relPath = `${relDir}/en.json`;
    const content = getFileAtCommit(REPO_ROOT, sourceCommit, relPath);
    if (!content) return null;
    try {
      return flattenJson(JSON.parse(content) as Record<string, unknown>, '');
    } catch {
      return null;
    }
  }

  // For directory-based locales, we need to know which files existed at that commit.
  // Simplified: try the same files that exist now.
  const enDir = path.join(config.dir, 'en');
  if (!fs.existsSync(enDir)) return null;

  const result: Record<string, string> = {};
  const jsonFiles = fs.readdirSync(enDir).filter((f) => f.endsWith('.json'));

  for (const file of jsonFiles) {
    const relPath = `${relDir}/en/${file}`;
    const content = getFileAtCommit(REPO_ROOT, sourceCommit, relPath);
    if (!content) continue;
    try {
      const namespace = config.useNamespacePrefix ? file.replace('.json', '') : '';
      Object.assign(result, flattenJson(JSON.parse(content) as Record<string, unknown>, namespace));
    } catch {
      // skip unparseable files
    }
  }

  return Object.keys(result).length > 0 ? result : null;
}

function checkLocaleDir(config: LocaleCheckConfig): string[] {
  const hashFile = path.join(config.dir, '.translation-hashes.json');
  const errors: string[] = [];

  if (!fs.existsSync(hashFile)) {
    errors.push(`Hash manifest not found: ${hashFile}`);
    return errors;
  }

  const manifest = JSON.parse(fs.readFileSync(hashFile, 'utf-8')) as HashManifest;
  const storedHashes = manifest.hashes || {};
  const sourceCommit = manifest.$meta?.sourceCommit;

  // Compute current hashes using the same algorithm as the generator
  const currentFlat = loadEnglishFlat(config);
  if (!currentFlat) {
    errors.push(`English source not found for ${config.name}`);
    return errors;
  }
  const currentHashes: Record<string, string> = {};
  // Re-compute using flattenAndHash (CRC32) for hash comparison
  if (config.flatFiles) {
    const enFile = path.join(config.dir, 'en.json');
    const content = JSON.parse(fs.readFileSync(enFile, 'utf-8')) as Record<string, unknown>;
    Object.assign(currentHashes, flattenAndHash(content, ''));
  } else {
    const enDir = path.join(config.dir, 'en');
    const jsonFiles = fs.readdirSync(enDir).filter((f) => f.endsWith('.json'));
    for (const file of jsonFiles) {
      const namespace = config.useNamespacePrefix ? file.replace('.json', '') : '';
      const content = JSON.parse(
        fs.readFileSync(path.join(enDir, file), 'utf-8')
      ) as Record<string, unknown>;
      Object.assign(currentHashes, flattenAndHash(content, namespace));
    }
  }

  // Find stale and new keys
  const staleKeys: string[] = [];
  const newKeys: string[] = [];

  for (const [key, hash] of Object.entries(currentHashes)) {
    if (!(key in storedHashes)) {
      newKeys.push(key);
    } else if (storedHashes[key] !== hash) {
      staleKeys.push(key);
    }
  }

  const deletedKeys: string[] = [];
  for (const key of Object.keys(storedHashes)) {
    if (!(key in currentHashes)) {
      deletedKeys.push(key);
    }
  }

  if (staleKeys.length === 0 && newKeys.length === 0 && deletedKeys.length === 0) {
    return errors;
  }

  // Try to compute detailed diff using sourceCommit
  let diffChanges: TranslationChange[] | null = null;
  if (sourceCommit && (staleKeys.length > 0 || deletedKeys.length > 0)) {
    const oldFlat = loadOldEnglishFlat(config, sourceCommit);
    if (oldFlat) {
      diffChanges = diffJsonTranslations(oldFlat, currentFlat);
    }
  }

  if (staleKeys.length > 0) {
    errors.push(`[${config.name}] English values changed for ${staleKeys.length} key(s):`);

    if (diffChanges) {
      // Show old → new values from diff
      const modifiedChanges = diffChanges.filter(
        (c) => c.type === 'modified' && staleKeys.includes(c.key)
      );
      for (const c of modifiedChanges.slice(0, 10)) {
        errors.push(`  ~ ${c.key}`);
        errors.push(`    old: ${JSON.stringify(c.oldValue)}`);
        errors.push(`    new: ${JSON.stringify(c.newValue)}`);
        errors.push(`    → Update this key in all non-English languages`);
      }
      if (modifiedChanges.length > 10) {
        errors.push(`  ... and ${modifiedChanges.length - 10} more modified keys`);
      }
    } else {
      // Fallback: just list keys
      staleKeys.slice(0, 5).forEach((k) => errors.push(`  - ${k}`));
      if (staleKeys.length > 5) {
        errors.push(`  ... and ${staleKeys.length - 5} more`);
      }
    }
  }

  if (newKeys.length > 0) {
    errors.push(`[${config.name}] New keys not in hash manifest: ${newKeys.length}`);
    for (const k of newKeys.slice(0, 5)) {
      errors.push(`  + ${k}: ${JSON.stringify(currentFlat[k])}`);
      errors.push(`    → Translate and add to all non-English languages`);
    }
    if (newKeys.length > 5) {
      errors.push(`  ... and ${newKeys.length - 5} more`);
    }
  }

  if (deletedKeys.length > 0) {
    errors.push(`[${config.name}] Keys removed from English: ${deletedKeys.length}`);
    for (const k of deletedKeys.slice(0, 5)) {
      errors.push(`  - ${k}`);
      errors.push(`    → Delete this key from all non-English languages`);
    }
    if (deletedKeys.length > 5) {
      errors.push(`  ... and ${deletedKeys.length - 5} more`);
    }
  }

  return errors;
}

function main(): void {
  const errors: string[] = [];

  for (const config of LOCALE_CONFIGS) {
    if (fs.existsSync(config.dir)) {
      errors.push(...checkLocaleDir(config));
    }
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

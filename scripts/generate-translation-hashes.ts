#!/usr/bin/env node
/**
 * Translation Hash Generation Script
 *
 * Generates CRC32 hashes for all English translation values.
 * The hash manifest (.translation-hashes.json) is used by ESLint
 * to detect when English values change, indicating stale translations.
 *
 * Usage:
 *   npx tsx scripts/generate-translation-hashes.ts
 *   npm run i18n:generate-hashes
 *   npm run i18n:update-hashes (alias)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { flattenAndHash } from './utils/crc32.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

interface LocaleConfig {
  name: string;
  dir: string;
  multipleNamespaces: boolean;
  /** Flat layout: translations are {dir}/{lang}.json instead of {dir}/{lang}/*.json */
  flatFiles?: boolean;
}

interface HashManifest {
  $meta: {
    algorithm: string;
    sourceLanguage: string;
    keyCount: number;
  };
  hashes: Record<string, string>;
}

interface ProcessResult {
  name: string;
  path: string;
  keyCount: number;
}

// Configuration for each locale directory
const LOCALE_CONFIGS: LocaleConfig[] = [
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
  {
    name: 'www',
    dir: path.join(__dirname, '../packages/www/src/i18n/translations'),
    // WWW has flat files: {lang}.json directly in dir (no subdirectories)
    multipleNamespaces: false,
    flatFiles: true,
  },
];

const HASH_FILENAME = '.translation-hashes.json';
const SOURCE_LANG = 'en';

/**
 * Sort object keys alphabetically
 */
function sortObjectKeys(obj: Record<string, string>): Record<string, string> {
  const sorted: Record<string, string> = {};
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
function processLocaleDir(config: LocaleConfig): Record<string, string> | null {
  const { name, dir, multipleNamespaces, flatFiles } = config;

  // Flat layout: {dir}/en.json instead of {dir}/en/*.json
  if (flatFiles) {
    const enFile = path.join(dir, `${SOURCE_LANG}.json`);
    if (!fs.existsSync(enFile)) {
      console.log(`   Skipping ${name}: English file not found at ${enFile}`);
      return null;
    }
    const content = JSON.parse(fs.readFileSync(enFile, 'utf-8')) as Record<string, unknown>;
    return flattenAndHash(content, '');
  }

  const englishDir = path.join(dir, SOURCE_LANG);

  if (!fs.existsSync(englishDir)) {
    console.log(`   Skipping ${name}: English directory not found at ${englishDir}`);
    return null;
  }

  const allHashes: Record<string, string> = {};

  if (multipleNamespaces) {
    // Web: Process each namespace file (common.json, auth.json, etc.)
    const files = fs.readdirSync(englishDir).filter((f) => f.endsWith('.json'));

    for (const file of files) {
      const namespace = file.replace('.json', '');
      const filePath = path.join(englishDir, file);
      const content = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as Record<string, unknown>;

      // Prefix keys with namespace (e.g., common.welcome, auth.login)
      const hashes = flattenAndHash(content, namespace);
      Object.assign(allHashes, hashes);
    }
  } else {
    // CLI: Process single file per language
    const files = fs.readdirSync(englishDir).filter((f) => f.endsWith('.json'));

    for (const file of files) {
      const filePath = path.join(englishDir, file);
      const content = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as Record<string, unknown>;

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
function writeHashManifest(dir: string, hashes: Record<string, string>, name: string): string {
  // Note: We intentionally omit timestamps to reduce merge conflicts
  const manifest: HashManifest = {
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

async function main(): Promise<void> {
  console.log('Translation Hash Generation');
  console.log(''.padEnd(60, '='));
  console.log();

  const results: ProcessResult[] = [];

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

main().catch((err: unknown) => {
  console.error('Error generating hashes:', err);
  process.exit(1);
});

#!/usr/bin/env node
/**
 * WWW-Only Translation Key Validation
 *
 * Validates that all {{t:key}} references in www documentation are actually
 * used by the web application. This ensures translation keys added to locales
 * are not orphaned (only used by documentation, not the actual UI).
 *
 * Principle:
 *   Translation keys in packages/web/src/i18n/locales/ should ONLY be added
 *   if they are used by the web application. The www documentation should
 *   reference existing web keys, not create new ones.
 *
 * Usage:
 *   npx tsx scripts/check-www-only-translations.ts
 *
 * Exit codes:
 *   0 - All www translation keys are used by web
 *   1 - Some keys are www-only (not used by web)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration
const DOCS_DIR = path.join(__dirname, '../packages/www/src/content/docs');
const WEB_SRC_DIR = path.join(__dirname, '../packages/web/src');
const SHARED_SRC_DIR = path.join(__dirname, '../packages/shared/src');
const LOCALES_DIR = path.join(__dirname, '../packages/web/src/i18n/locales/en');

// Pattern for {{t:namespace.key}} in docs
const DOC_KEY_PATTERN = /\{\{t:([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}\}/g;

/**
 * Known dynamic key patterns used in the web application.
 * These patterns use template literals like t(`vaultEditor.fields.${entityType}.${fieldName}.label`)
 * and cannot be detected statically. Keys matching these patterns are considered "used".
 */
const DYNAMIC_KEY_PATTERNS = [
  // VaultEditor dynamically constructs field keys: t(`vaultEditor.fields.${entityType}.${fieldName}.label`)
  /^common\.vaultEditor\.fields\.[A-Z_]+\.[a-zA-Z_]+\.(label|description|placeholder|helpText)$/,
  // Storage provider fields: t(`storageProviders.${provider}.fields.${fieldName}.label`)
  /^storageProviders\.storageProviders\.[a-zA-Z]+\.fields\.[a-zA-Z_]+\.(label|placeholder|helpText)$/,
  // Function params are accessed dynamically in FunctionSelectionModal and related components
  // Pattern: functions.functions.<function_name>.params.<param_name>.(label|description|placeholder|help)
  /^functions\.functions\.[a-zA-Z_]+\.params\.[a-zA-Z_]+\.(label|description|placeholder|help)$/,
  // Function checkbox options
  /^functions\.checkboxOptions\.[a-zA-Z]+$/,
];

/**
 * Extract all {{t:key}} from documentation files
 */
function extractDocsKeys(): Set<string> {
  const keys = new Set<string>();

  if (!fs.existsSync(DOCS_DIR)) {
    return keys;
  }

  const mdFiles = globSync(`${DOCS_DIR}/**/*.md`);

  for (const file of mdFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    let match: RegExpExecArray | null;
    const pattern = new RegExp(DOC_KEY_PATTERN.source, 'g');

    while ((match = pattern.exec(content)) !== null) {
      // Combine namespace.keyPath
      keys.add(`${match[1]}.${match[2]}`);
    }
  }

  return keys;
}

/**
 * Recursively get all keys from a nested object, building dot-notation paths
 */
function getAllKeysFromObject(
  obj: Record<string, unknown>,
  prefix = ''
): string[] {
  const keys: string[] = [];

  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;

    if (typeof value === 'string') {
      keys.push(fullKey);
    } else if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...getAllKeysFromObject(value as Record<string, unknown>, fullKey));
    }
  }

  return keys;
}

/**
 * Get all available translation keys from locale files
 */
function getAllLocaleKeys(): Set<string> {
  const keys = new Set<string>();

  if (!fs.existsSync(LOCALES_DIR)) {
    return keys;
  }

  const jsonFiles = globSync(`${LOCALES_DIR}/*.json`);

  for (const file of jsonFiles) {
    const namespace = path.basename(file, '.json');

    try {
      const content = JSON.parse(fs.readFileSync(file, 'utf-8')) as Record<string, unknown>;
      const fileKeys = getAllKeysFromObject(content);

      for (const key of fileKeys) {
        keys.add(`${namespace}.${key}`);
      }
    } catch {
      console.error(`Failed to parse ${file}`);
    }
  }

  return keys;
}

/**
 * Extract translation keys used in web source files
 * Handles namespaced usage: useTranslation('namespace') + t('key')
 */
function extractWebKeys(): Set<string> {
  const keys = new Set<string>();

  const sourceFiles = [
    ...globSync(`${WEB_SRC_DIR}/**/*.{ts,tsx}`),
    ...globSync(`${SHARED_SRC_DIR}/**/*.{ts,tsx}`),
  ];

  // Pattern to find useTranslation calls
  const useTranslationPattern = /useTranslation\(\s*['"]([a-zA-Z]+)['"]/g;
  // Pattern to find t() calls - captures the key
  const tCallPattern = /\bt\(\s*['"`]([a-zA-Z][a-zA-Z0-9_.]*)['"` ]/g;
  // Pattern for t() with array of namespaces: useTranslation(['ns1', 'ns2'])
  const useTranslationArrayPattern = /useTranslation\(\s*\[([^\]]+)\]/g;
  // Pattern for full qualified keys: t('namespace:key')
  const fullKeyPattern = /\bt\(\s*['"`]([a-zA-Z]+):([a-zA-Z0-9_.]+)['"` ]/g;

  for (const file of sourceFiles) {
    const content = fs.readFileSync(file, 'utf-8');

    // Find all namespaces used in this file
    const namespaces = new Set<string>();
    let match: RegExpExecArray | null;

    // Single namespace usage
    const nsPattern = new RegExp(useTranslationPattern.source, 'g');
    while ((match = nsPattern.exec(content)) !== null) {
      namespaces.add(match[1]);
    }

    // Array namespace usage
    const nsArrayPattern = new RegExp(useTranslationArrayPattern.source, 'g');
    while ((match = nsArrayPattern.exec(content)) !== null) {
      const arrayContent = match[1];
      const nsMatches = arrayContent.match(/['"]([a-zA-Z]+)['"]/g);
      if (nsMatches) {
        for (const nsMatch of nsMatches) {
          namespaces.add(nsMatch.replace(/['"]/g, ''));
        }
      }
    }

    // Find all t() calls
    const tPattern = new RegExp(tCallPattern.source, 'g');
    while ((match = tPattern.exec(content)) !== null) {
      const key = match[1];

      // If key already has namespace (contains :), add directly
      if (key.includes(':')) {
        const [ns, keyPath] = key.split(':');
        keys.add(`${ns}.${keyPath}`);
      } else {
        // Add key with each namespace found in this file
        for (const namespace of namespaces) {
          keys.add(`${namespace}.${key}`);
        }

        // Also add common/default namespace combinations
        // Some files might use Trans component or other patterns
        if (namespaces.size === 0) {
          // If no namespace found, try common ones
          for (const ns of ['common', 'auth', 'resources', 'functions', 'queue', 'system', 'machines', 'organization', 'settings', 'storageProviders', 'ceph']) {
            keys.add(`${ns}.${key}`);
          }
        }
      }
    }

    // Handle fully qualified keys (namespace:key)
    const fullPattern = new RegExp(fullKeyPattern.source, 'g');
    while ((match = fullPattern.exec(content)) !== null) {
      keys.add(`${match[1]}.${match[2]}`);
    }
  }

  return keys;
}

/**
 * Check if a key exists in locale files
 */
function keyExistsInLocales(key: string, localeKeys: Set<string>): boolean {
  return localeKeys.has(key);
}

/**
 * Check if a key matches any known dynamic pattern
 */
function matchesDynamicPattern(key: string): boolean {
  return DYNAMIC_KEY_PATTERNS.some((pattern) => pattern.test(key));
}

/**
 * Find keys used in docs that don't exist in locales OR aren't used in web
 */
function findWwwOnlyKeys(
  docsKeys: Set<string>,
  webKeys: Set<string>,
  localeKeys: Set<string>
): string[] {
  const wwwOnlyKeys: string[] = [];

  for (const key of docsKeys) {
    // Key must exist in locale files
    if (!keyExistsInLocales(key, localeKeys)) {
      // Key doesn't exist in locales at all - might be a typo in docs
      // This is caught by check-docs-inline-translations.ts
      continue;
    }

    // Check if key matches a known dynamic pattern (dynamically accessed in web)
    if (matchesDynamicPattern(key)) {
      continue;
    }

    // Check if key is used in web source
    if (!webKeys.has(key)) {
      wwwOnlyKeys.push(key);
    }
  }

  return wwwOnlyKeys.sort();
}

/**
 * Main validation function
 */
function main(): void {
  console.log('WWW-Only Translation Key Validation');
  console.log('============================================================\n');

  // Check if docs directory exists
  if (!fs.existsSync(DOCS_DIR)) {
    console.log('\x1b[33m!\x1b[0m Docs directory not found, skipping www-only check');
    process.exit(0);
  }

  console.log('Extracting translation keys from documentation...');
  const docsKeys = extractDocsKeys();
  console.log(`  Found ${docsKeys.size} unique key(s) in docs\n`);

  console.log('Loading all keys from locale files...');
  const localeKeys = getAllLocaleKeys();
  console.log(`  Found ${localeKeys.size} total key(s) in locale files\n`);

  console.log('Extracting translation keys from web source...');
  const webKeys = extractWebKeys();
  console.log(`  Found ${webKeys.size} unique key(s) in web source\n`);

  console.log('Comparing keys...\n');
  const wwwOnlyKeys = findWwwOnlyKeys(docsKeys, webKeys, localeKeys);

  if (wwwOnlyKeys.length > 0) {
    console.log('\x1b[31mWWW-Only Keys Found:\x1b[0m');
    console.log(
      'These keys exist in locale files and are used in documentation,\n' +
        'but are NOT used in the web application source code.\n'
    );

    for (const key of wwwOnlyKeys.slice(0, 30)) {
      console.log(`  \x1b[31m✗\x1b[0m {{t:${key}}}`);
    }

    if (wwwOnlyKeys.length > 30) {
      console.log(`  ... and ${wwwOnlyKeys.length - 30} more`);
    }

    console.log(
      '\n\x1b[31m✗\x1b[0m WWW-only translation validation FAILED\n' +
        `Found ${wwwOnlyKeys.length} key(s) that are only used in www, not in web.\n\n` +
        'To fix:\n' +
        '  1. Find an existing key in web source that matches your intent\n' +
        '  2. Or hardcode the text directly in the documentation\n' +
        '  3. Do NOT add new keys to web locales just for documentation\n'
    );
    process.exit(1);
  }

  if (docsKeys.size === 0) {
    console.log(
      '\x1b[32m✓\x1b[0m No inline translation keys found in documentation (none to validate)\n'
    );
  } else {
    console.log(
      `\x1b[32m✓\x1b[0m All ${docsKeys.size} documentation key(s) are used by the web application\n`
    );
  }

  process.exit(0);
}

main();

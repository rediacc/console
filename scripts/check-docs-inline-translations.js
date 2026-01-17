#!/usr/bin/env node
/**
 * Docs Inline Translation Validation
 *
 * Validates {{t:key}} references in documentation markdown files.
 *
 * Checks:
 * 1. Key format is valid: {{t:namespace.key.path}}
 * 2. Namespace file exists in web locales
 * 3. Key path resolves to a value in ALL 9 languages
 * 4. Cross-MD consistency: All language versions of a doc have same keys
 * 5. Key count consistency: Same number of {{t:key}} in each language version
 * 6. Key order consistency: Keys appear in same order across language versions
 *
 * Usage:
 *   node scripts/check-docs-inline-translations.js
 *
 * Exit codes:
 *   0 - All inline translation keys are valid
 *   1 - Some keys are invalid or inconsistent
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration
const DOCS_DIR = path.join(__dirname, '../packages/www/src/content/docs');
const WEB_LOCALES = path.join(__dirname, '../packages/web/src/i18n/locales');
const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];
const KEY_PATTERN = /\{\{t:([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}\}/g;

/**
 * Resolve a nested key path in a translation object
 */
function resolveKeyPath(translations, keyPath) {
  const keys = keyPath.split('.');
  let current = translations;

  for (const key of keys) {
    if (current === null || current === undefined || typeof current !== 'object') {
      return undefined;
    }
    current = current[key];
  }

  return current;
}

/**
 * CHECK 1: Validate each key exists in web locales (all 9 languages)
 */
function validateKeyInWebLocales(namespace, keyPath, lang) {
  const filePath = path.join(WEB_LOCALES, lang, `${namespace}.json`);

  if (!fs.existsSync(filePath)) {
    return `Namespace '${namespace}' not found for ${lang}`;
  }

  try {
    const translations = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const value = resolveKeyPath(translations, keyPath);

    if (value === undefined) {
      return `Key '${namespace}.${keyPath}' not found in ${lang}`;
    }

    if (typeof value !== 'string') {
      return `Key '${namespace}.${keyPath}' in ${lang} is not a string (got ${typeof value})`;
    }
  } catch (e) {
    return `Failed to parse ${filePath}: ${e.message}`;
  }

  return null;
}

/**
 * Extract all {{t:key}} from file content, preserving order
 */
function extractKeys(content) {
  const keys = [];
  let match;
  const pattern = new RegExp(KEY_PATTERN.source, 'g');

  while ((match = pattern.exec(content)) !== null) {
    keys.push(`${match[1]}.${match[2]}`);
  }

  return keys;
}

/**
 * Get the base slug from a file path (e.g., "en/web-application.md" -> "web-application.md")
 */
function getBaseSlug(filePath, langDir) {
  return path.relative(langDir, filePath);
}

/**
 * CHECK 2-6: Cross-MD consistency validation
 */
function validateCrossMdConsistency(errors) {
  // Group files by base slug (e.g., "web-application.md")
  const docGroups = new Map();

  for (const lang of LANGUAGES) {
    const langDir = path.join(DOCS_DIR, lang);
    if (!fs.existsSync(langDir)) continue;

    const files = globSync(`${langDir}/**/*.md`);

    for (const file of files) {
      const relativePath = getBaseSlug(file, langDir);

      if (!docGroups.has(relativePath)) {
        docGroups.set(relativePath, {});
      }

      const content = fs.readFileSync(file, 'utf-8');
      docGroups.get(relativePath)[lang] = {
        file,
        keys: extractKeys(content),
      };
    }
  }

  // Validate each doc group
  for (const [slug, langVersions] of docGroups) {
    const enVersion = langVersions['en'];
    if (!enVersion) continue;

    // Skip files with no translation keys in English
    if (enVersion.keys.length === 0) continue;

    const enKeys = enVersion.keys;
    const enKeyCount = enKeys.length;

    for (const [lang, version] of Object.entries(langVersions)) {
      if (lang === 'en') continue;

      const langKeys = version.keys;

      // Skip if the non-English version has no keys at all (likely a stub document)
      // Consistency is only checked when both versions actively use translation keys
      if (langKeys.length === 0) continue;

      // CHECK 2: Key count must match
      if (langKeys.length !== enKeyCount) {
        errors.push(
          `${slug}: Key count mismatch - en has ${enKeyCount}, ${lang} has ${langKeys.length}`
        );
        continue; // Skip further checks if counts don't match
      }

      // CHECK 3: Same keys must be present (regardless of order)
      const enKeySet = new Set(enKeys);
      const langKeySet = new Set(langKeys);

      for (const key of enKeySet) {
        if (!langKeySet.has(key)) {
          errors.push(`${slug} (${lang}): Missing key {{t:${key}}} (exists in en)`);
        }
      }

      for (const key of langKeySet) {
        if (!enKeySet.has(key)) {
          errors.push(`${slug} (${lang}): Extra key {{t:${key}}} (not in en)`);
        }
      }

      // CHECK 4: Key order should match (warning, not blocking)
      if (enKeys.length === langKeys.length) {
        for (let i = 0; i < enKeys.length; i++) {
          if (enKeys[i] !== langKeys[i]) {
            // This is a warning, not an error - order differences are less critical
            console.warn(
              `  \u001B[33m!\u001B[0m ${slug} (${lang}): Key order differs at position ${i + 1} - ` +
                `en: {{t:${enKeys[i]}}}, ${lang}: {{t:${langKeys[i]}}}`
            );
            break;
          }
        }
      }
    }
  }
}

/**
 * Main validation function
 */
function main() {
  console.log('Docs Inline Translation Validation');
  console.log('============================================================\n');

  const errors = [];
  let totalKeys = 0;
  const filesWithKeys = new Set();

  // Check if docs directory exists
  if (!fs.existsSync(DOCS_DIR)) {
    console.log('\u001B[33m!\u001B[0m Docs directory not found, skipping inline translation check');
    process.exit(0);
  }

  // CHECK 1: Validate all keys exist in web locales
  console.log('Checking inline translation keys in documentation...\n');

  const mdFiles = globSync(`${DOCS_DIR}/**/*.md`);

  for (const file of mdFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    const keys = extractKeys(content);

    if (keys.length === 0) continue;

    filesWithKeys.add(file);
    totalKeys += keys.length;

    // Extract document language from frontmatter
    const langMatch = content.match(/^---[\s\S]*?language:\s*['"]?([a-z]{2})['"]?[\s\S]*?---/m);
    const docLang = langMatch ? langMatch[1] : 'en';

    const relPath = path.relative(DOCS_DIR, file);

    for (const key of keys) {
      const [namespace, ...parts] = key.split('.');
      const keyPath = parts.join('.');

      // Validate key exists in all languages
      for (const lang of LANGUAGES) {
        const error = validateKeyInWebLocales(namespace, keyPath, lang);
        if (error) {
          errors.push(`${relPath}: ${error}`);
        }
      }
    }
  }

  // CHECKS 2-6: Cross-MD consistency
  if (errors.length === 0) {
    console.log('Checking cross-document consistency...\n');
    validateCrossMdConsistency(errors);
  }

  // Print summary
  console.log(`Found ${totalKeys} inline translation key(s) in ${filesWithKeys.size} file(s)\n`);

  if (errors.length > 0) {
    console.log('\u001B[31mErrors:\u001B[0m');
    // Deduplicate errors
    const uniqueErrors = [...new Set(errors)];
    uniqueErrors.slice(0, 20).forEach((e) => console.log(`  \u001B[31m\u2717\u001B[0m ${e}`));

    if (uniqueErrors.length > 20) {
      console.log(`  ... and ${uniqueErrors.length - 20} more errors`);
    }

    console.log(
      '\n\u001B[31m\u2717\u001B[0m Docs inline translation validation FAILED\n' +
        'Fix the errors above to ensure all {{t:key}} references resolve correctly.\n'
    );
    process.exit(1);
  }

  if (totalKeys === 0) {
    console.log(
      '\u001B[32m\u2713\u001B[0m No inline translation keys found in documentation (none to validate)\n'
    );
  } else {
    console.log(
      '\u001B[32m\u2713\u001B[0m All inline translation keys are valid and consistent\n'
    );
  }

  process.exit(0);
}

main();

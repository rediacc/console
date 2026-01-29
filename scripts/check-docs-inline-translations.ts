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
 * 6. Line number alignment: Each key must appear on the same line number(s) across all languages
 *    (within-line order may differ due to natural language sentence structure)
 *
 * Usage:
 *   npx tsx scripts/check-docs-inline-translations.ts
 *
 * Exit codes:
 *   0 - All inline translation keys are valid
 *   1 - Some keys are invalid or inconsistent (including line number mismatches)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration
const DOCS_DIR = path.join(__dirname, '../packages/www/src/content/docs');
const WEB_LOCALES = path.join(__dirname, '../packages/web/src/i18n/locales');
const CLI_LOCALES = path.join(__dirname, '../packages/cli/src/i18n/locales');
const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'] as const;
const KEY_PATTERN = /\{\{t:([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}\}/g;

type Language = (typeof LANGUAGES)[number];

interface KeyLocation {
  key: string;
  line: number;
}

interface LangVersionInfo {
  file: string;
  keys: string[];
  keyLocations: KeyLocation[];
}

type DocGroup = Record<Language, LangVersionInfo>;

/**
 * Resolve a nested key path in a translation object
 */
function resolveKeyPath(
  translations: Record<string, unknown>,
  keyPath: string
): unknown {
  const keys = keyPath.split('.');
  let current: unknown = translations;

  for (const key of keys) {
    if (current === null || current === undefined || typeof current !== 'object') {
      return undefined;
    }
    current = (current as Record<string, unknown>)[key];
  }

  return current;
}

/**
 * CHECK 1: Validate each key exists in locales (web + CLI, all 9 languages)
 *
 * Searches web locales first, then CLI locales as fallback.
 * Both web and CLI locales exist for all 9 languages.
 */
function validateKeyInLocales(
  namespace: string,
  keyPath: string,
  lang: Language
): string | null {
  const paths = [
    path.join(WEB_LOCALES, lang, `${namespace}.json`),
    path.join(CLI_LOCALES, lang, `${namespace}.json`),
  ];

  for (const localePath of paths) {
    if (!fs.existsSync(localePath)) continue;
    try {
      const translations = JSON.parse(
        fs.readFileSync(localePath, 'utf-8')
      ) as Record<string, unknown>;
      const value = resolveKeyPath(translations, keyPath);

      if (value === undefined) continue;

      if (typeof value !== 'string') {
        return `Key '${namespace}.${keyPath}' in ${lang} is not a string (got ${typeof value})`;
      }

      return null; // found and valid
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      return `Failed to parse ${localePath}: ${message}`;
    }
  }

  return `Key '${namespace}.${keyPath}' not found in ${lang} (checked web + CLI locales)`;
}

/**
 * Extract all {{t:key}} from file content, preserving order
 */
function extractKeys(content: string): string[] {
  const keys: string[] = [];
  let match: RegExpExecArray | null;
  const pattern = new RegExp(KEY_PATTERN.source, 'g');

  while ((match = pattern.exec(content)) !== null) {
    keys.push(`${match[1]}.${match[2]}`);
  }

  return keys;
}

/**
 * Extract all {{t:key}} with their line numbers
 */
function extractKeyLocations(content: string): KeyLocation[] {
  const locations: KeyLocation[] = [];
  const lines = content.split('\n');
  const pattern = new RegExp(KEY_PATTERN.source, 'g');

  for (let lineNum = 0; lineNum < lines.length; lineNum++) {
    const line = lines[lineNum];
    let match: RegExpExecArray | null;
    pattern.lastIndex = 0;

    while ((match = pattern.exec(line)) !== null) {
      locations.push({
        key: `${match[1]}.${match[2]}`,
        line: lineNum + 1, // 1-indexed line numbers
      });
    }
  }

  return locations;
}

/**
 * Get the base slug from a file path (e.g., "en/web-application.md" -> "web-application.md")
 */
function getBaseSlug(filePath: string, langDir: string): string {
  return path.relative(langDir, filePath);
}

/**
 * CHECK 2-6: Cross-MD consistency validation
 */
function validateCrossMdConsistency(errors: string[]): void {
  // Group files by base slug (e.g., "web-application.md")
  const docGroups = new Map<string, Partial<DocGroup>>();

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
      docGroups.get(relativePath)![lang] = {
        file,
        keys: extractKeys(content),
        keyLocations: extractKeyLocations(content),
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
    const enKeyLocations = enVersion.keyLocations;

    // Build a map of key -> set of line numbers for English
    const enKeyLines = new Map<string, Set<number>>();
    for (const loc of enKeyLocations) {
      if (!enKeyLines.has(loc.key)) {
        enKeyLines.set(loc.key, new Set());
      }
      enKeyLines.get(loc.key)!.add(loc.line);
    }

    for (const [lang, version] of Object.entries(langVersions) as Array<
      [Language, LangVersionInfo]
    >) {
      if (lang === 'en') continue;

      const langKeys = version.keys;
      const langKeyLocations = version.keyLocations;

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

      // CHECK 4: Line number alignment - each key must appear on the same line(s)
      // Build a map of key -> set of line numbers for this language
      const langKeyLines = new Map<string, Set<number>>();
      for (const loc of langKeyLocations) {
        if (!langKeyLines.has(loc.key)) {
          langKeyLines.set(loc.key, new Set());
        }
        langKeyLines.get(loc.key)!.add(loc.line);
      }

      // Compare line numbers for each key
      for (const [key, enLines] of enKeyLines) {
        const langLines = langKeyLines.get(key);
        if (!langLines) continue; // Already caught by missing key check

        // Sort line numbers for comparison
        const enLinesSorted = [...enLines].sort((a, b) => a - b);
        const langLinesSorted = [...langLines].sort((a, b) => a - b);

        // Check if line numbers match
        if (
          enLinesSorted.length !== langLinesSorted.length ||
          !enLinesSorted.every((line, i) => line === langLinesSorted[i])
        ) {
          errors.push(
            `${slug} (${lang}): Key {{t:${key}}} line mismatch - ` +
              `en: line(s) ${enLinesSorted.join(', ')}, ${lang}: line(s) ${langLinesSorted.join(', ')}`
          );
        }
      }
    }
  }
}

/**
 * Main validation function
 */
function main(): void {
  console.log('Docs Inline Translation Validation');
  console.log('============================================================\n');

  const errors: string[] = [];
  let totalKeys = 0;
  const filesWithKeys = new Set<string>();

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

    const relPath = path.relative(DOCS_DIR, file);

    for (const key of keys) {
      const [namespace, ...parts] = key.split('.');
      const keyPath = parts.join('.');

      for (const lang of LANGUAGES) {
        const error = validateKeyInLocales(namespace, keyPath, lang);
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

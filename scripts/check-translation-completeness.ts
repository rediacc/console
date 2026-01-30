#!/usr/bin/env node
/**
 * Translation Completeness Check
 *
 * Validates that translations are actually translated (not just English placeholders).
 * This complements check-translation-hashes.ts which only checks hash freshness.
 *
 * Checks:
 * 1. All languages have all keys (sync check)
 * 2. Non-English files don't have English values (untranslated placeholders)
 *
 * Usage:
 *   npx tsx scripts/check-translation-completeness.ts
 *   npm run check:i18n:completeness
 *
 * Exit codes:
 *   0 - All translations are complete
 *   1 - Some translations are missing or untranslated
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration
const MAX_UNTRANSLATED_PERCENT = 0; // Error if ANY strings are untranslated - all must be translated
const MIN_STRING_LENGTH = 4; // Only check strings longer than this (skip "OK", "No", etc.)

// Strings that are intentionally the same across languages (brand names, technical terms)
const ALLOWED_IDENTICAL = new Set([
  // Brand names
  'Rediacc',
  'Rediaccfile',
  'Renet',
  'Node.js',
  'GitHub',
  'Docker',
  'Kubernetes',
  'VS Code',
  'Visual Studio Code',
  'Intel',
  'Oracle',
  'Azure',
  'Backblaze',
  'Cloudflare',
  'Ceph',
  // Storage provider brand names (keep as-is globally)
  'Dropbox',
  '1Fichier',
  'FileFabric',
  'HiDrive',
  'Jottacloud',
  'Koofr',
  'Linkbox',
  'Mail.ru Cloud',
  'OpenDrive',
  'pCloud',
  'PikPak',
  'Pixeldrain',
  'QingStor',
  'Quatrix',
  'Storj',
  'Uloz.to',
  'Uptobox',
  'Wasabi',
  'GoFile',
  'Seafile',
  'SugarSync',
  'WebDAV',
  // Operating systems
  'Linux',
  'macOS',
  'Windows',
  'Ubuntu',
  'Debian',
  // Technical acronyms
  'SSH',
  'API',
  'URL',
  'JSON',
  'YAML',
  'CSV',
  'UUID',
  'ID',
  'IP',
  'TCP',
  'UDP',
  'HTTP',
  'HTTPS',
  'WebSocket',
  'OAuth',
  'JWT',
  'TOTP',
  'QR',
  'PDF',
  'CLI',
  'GUI',
  'ARM',
  'AMD64',
  'x64',
  'x86',
  'RBD',
  'OSD',
  'MON',
  'MDS',
  'RADOS',
  'CRUSH',
  // Technical terms often kept in English
  'Terminal',
  'Cluster',
  'Clone',
  'Snapshot',
  'Image',
  'Pool',
  'Token',
  'Datastore',
  'Disk',
  'Memory',
  'Status',
  // International words (same or very similar across languages)
  'Installation',
  'Description',
  'Error',
  'VS Code Integration',
  'System',
  'Region',
  'Version',
  'Global',
  'Local',
  'Hostname',
  'Kernel',
  'Machine',
  'Machines',
  'machines',
  'Important',
  'Actions',
  'Action',
  'Simple',
  'Message',
  'Configuration',
  'Ports',
  'Interface',
  'Model',
  'Services',
  'services',
  'Accessible',
  'Grand',
  'plugin',
  'plugins',
  'image',
  'clone',
]);

// Patterns for strings that should not be translated (placeholders, format strings)
const PLACEHOLDER_PATTERNS: RegExp[] = [
  /placeholder$/i, // Keys ending in "placeholder"
  /^https?:\/\//, // URLs
  /^[a-z0-9._-]+@[a-z0-9.-]+\.[a-z]+$/i, // Emails
  /^[a-z0-9.-]+\.(com|net|org|io|me|ru|cn)$/i, // Domains
  /^\d{4,}$/, // Numeric codes like 000000
  /^ocid1\./, // Oracle Cloud IDs
  /^\/[a-z]+\//, // Paths
  /\.(json|yaml|xml|txt|log|conf)$/i, // File extensions
  /^(docker|npm|git|ssh|curl|wget|sudo|rclone)\s/, // Commands
  /^\{\{[^}]+\}\}$/, // Template-only strings
  /^[A-Z]\{\{/, // Format strings starting with letter + template
  /^v\{\{version\}\}$/, // Version format
  /^P\{\{level\}\}/, // Priority format
  /^\s*(Token|Docker|Disk|Memory|Datastore|System):\s*\{\{/, // Status lines with template
  /^  [A-Z][a-z]+:\s*\{\{/, // Indented status lines
  /^  VS Code:\s*\{\{/, // VS Code status line
  /^(Token|Team|Machine|Repository|Platform|Installation|Error):$/, // Simple labels ending with colon
  /^\n?(System|Repositories):$/, // Section headers
  /^  Known Hosts:\s*\{\{/, // Known hosts line
  /^SSH test \{\{/, // SSH test result
  /^Action \(\{\{/, // Action format
  /^\{\{count\}\}\s+\w+$/, // Simple count templates like "{{count}} machines"
  /^\n?Error:\s*\{\{error\}\}$/, // Error templates
  /^minutes$/, // Time unit labels
  /^Cancelling\.\.\.$/i, // Progress indicator
];

type TranslationValue = string | TranslationObject;
type TranslationObject = Record<string, TranslationValue>;

interface LanguageStats {
  total: number;
  untranslated: number;
  untranslatedPercent: string;
  missing: number;
  missingPercent: string;
  untranslatedKeys: string[];
}

interface CheckResult {
  errors: string[];
  warnings: string[];
  stats?: Record<string, LanguageStats>;
}

function flatten(obj: TranslationObject, prefix = ''): Record<string, TranslationValue> {
  const result: Record<string, TranslationValue> = {};
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      Object.assign(result, flatten(value as TranslationObject, fullKey));
    } else {
      result[fullKey] = value;
    }
  }
  return result;
}

function shouldSkipValue(value: TranslationValue, key = ''): boolean {
  if (typeof value !== 'string') return true;
  if (value.length <= MIN_STRING_LENGTH) return true;
  if (ALLOWED_IDENTICAL.has(value)) return true;
  // Check placeholder patterns
  for (const pattern of PLACEHOLDER_PATTERNS) {
    if (pattern.test(key) || pattern.test(value)) return true;
  }
  return false;
}

function checkLocaleDir(name: string, localeDir: string): CheckResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  const enDir = path.join(localeDir, 'en');
  if (!fs.existsSync(enDir)) {
    errors.push(`[${name}] English locale directory not found: ${enDir}`);
    return { errors, warnings };
  }

  // Load English translations
  const enKeys: Record<string, TranslationValue> = {};
  const enFiles = fs.readdirSync(enDir).filter((f) => f.endsWith('.json'));

  for (const file of enFiles) {
    const content = JSON.parse(
      fs.readFileSync(path.join(enDir, file), 'utf-8')
    ) as TranslationObject;
    const flat = flatten(content);
    for (const [key, value] of Object.entries(flat)) {
      enKeys[key] = value;
    }
  }

  const totalEnKeys = Object.keys(enKeys).length;

  // Get all language directories
  const languages = fs
    .readdirSync(localeDir)
    .filter(
      (d) => d !== 'en' && !d.startsWith('.') && fs.statSync(path.join(localeDir, d)).isDirectory()
    );

  const stats: Record<string, LanguageStats> = {};

  for (const lang of languages) {
    const langDir = path.join(localeDir, lang);
    const langKeys: Record<string, TranslationValue> = {};
    let untranslated = 0;
    let missing = 0;

    // Load language translations
    for (const file of enFiles) {
      const langFile = path.join(langDir, file);
      if (!fs.existsSync(langFile)) {
        // Count all keys from this file as missing
        const enContent = JSON.parse(
          fs.readFileSync(path.join(enDir, file), 'utf-8')
        ) as TranslationObject;
        missing += Object.keys(flatten(enContent)).length;
        continue;
      }

      const content = JSON.parse(fs.readFileSync(langFile, 'utf-8')) as TranslationObject;
      const flat = flatten(content);
      Object.assign(langKeys, flat);
    }

    // Check for untranslated strings
    const untranslatedKeys: string[] = [];
    for (const [key, enValue] of Object.entries(enKeys)) {
      if (!(key in langKeys)) {
        missing++;
      } else if (langKeys[key] === enValue && !shouldSkipValue(enValue, key)) {
        untranslated++;
        untranslatedKeys.push(key);
      }
    }

    const total = totalEnKeys;
    const untranslatedPercent = ((untranslated / total) * 100).toFixed(1);
    const missingPercent = ((missing / total) * 100).toFixed(1);

    stats[lang] = {
      total,
      untranslated,
      untranslatedPercent,
      missing,
      missingPercent,
      untranslatedKeys: untranslatedKeys.slice(0, 5), // First 5 for display
    };

    // Report issues
    if (missing > 0) {
      errors.push(`[${name}/${lang}] Missing ${missing} keys (${missingPercent}%)`);
    }

    if (Number.parseFloat(untranslatedPercent) > MAX_UNTRANSLATED_PERCENT) {
      errors.push(
        `[${name}/${lang}] ${untranslated} untranslated strings (${untranslatedPercent}%) - exceeds ${MAX_UNTRANSLATED_PERCENT}% threshold`
      );
      if (untranslatedKeys.length > 0) {
        untranslatedKeys.slice(0, 3).forEach((k) => errors.push(`    - ${k}`));
        if (untranslatedKeys.length > 3) {
          errors.push(`    ... and ${untranslatedKeys.length - 3} more`);
        }
      }
    } else if (untranslated > 0) {
      warnings.push(
        `[${name}/${lang}] ${untranslated} untranslated strings (${untranslatedPercent}%)`
      );
    }
  }

  return { errors, warnings, stats };
}

function main(): void {
  console.log('Translation Completeness Check');
  console.log('============================================================\n');

  const allErrors: string[] = [];
  const allWarnings: string[] = [];

  // Check web locales
  const webLocales = path.join(__dirname, '../packages/web/src/i18n/locales');
  if (fs.existsSync(webLocales)) {
    console.log('Checking web translations...');
    const { errors, warnings, stats } = checkLocaleDir('web', webLocales);
    allErrors.push(...errors);
    allWarnings.push(...warnings);

    if (stats) {
      for (const [lang, data] of Object.entries(stats)) {
        const status =
          data.missing > 0 || Number.parseFloat(data.untranslatedPercent) > MAX_UNTRANSLATED_PERCENT
            ? '\u001B[31m\u2717\u001B[0m'
            : data.untranslated > 0
              ? '\u001B[33m!\u001B[0m'
              : '\u001B[32m\u2713\u001B[0m';
        console.log(
          `  ${status} ${lang}: ${data.untranslated} untranslated (${data.untranslatedPercent}%)`
        );
      }
    }
    console.log('');
  }

  // Check CLI locales
  const cliLocales = path.join(__dirname, '../packages/cli/src/i18n/locales');
  if (fs.existsSync(cliLocales)) {
    console.log('Checking CLI translations...');
    const { errors, warnings, stats } = checkLocaleDir('cli', cliLocales);
    allErrors.push(...errors);
    allWarnings.push(...warnings);

    if (stats) {
      for (const [lang, data] of Object.entries(stats)) {
        const status =
          data.missing > 0 || Number.parseFloat(data.untranslatedPercent) > MAX_UNTRANSLATED_PERCENT
            ? '\u001B[31m\u2717\u001B[0m'
            : data.untranslated > 0
              ? '\u001B[33m!\u001B[0m'
              : '\u001B[32m\u2713\u001B[0m';
        console.log(
          `  ${status} ${lang}: ${data.untranslated} untranslated (${data.untranslatedPercent}%)`
        );
      }
    }
    console.log('');
  }

  // Print warnings
  if (allWarnings.length > 0) {
    console.log('Warnings:');
    allWarnings.forEach((w) => console.log(`  \u001B[33m!\u001B[0m ${w}`));
    console.log('');
  }

  // Print errors and exit
  if (allErrors.length > 0) {
    console.log('Errors:');
    allErrors.forEach((e) => console.log(`  \u001B[31m\u2717\u001B[0m ${e}`));
    console.log('\nTo fix missing keys, run: npm run i18n:sync');
    console.log('Untranslated strings need manual translation or AI assistance.\n');
    process.exit(1);
  }

  console.log(
    `\u001B[32m\u2713\u001B[0m All translations are complete (threshold: ${MAX_UNTRANSLATED_PERCENT}% untranslated allowed)`
  );
  process.exit(0);
}

main();

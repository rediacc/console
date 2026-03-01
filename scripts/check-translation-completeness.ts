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
  // Category names (kept in English across all locales for sidebar grouping)
  'Reference',
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
  // Package manager / installer names (kept in English globally)
  'APT',
  'DNF',
  'Homebrew',
  'AppImage',
  'Downloads',
  'Contact',
  'Solutions',
  'Legal',
  'General',
  'Professional',
  'Repositories',
  'docker',
  'section',
  // International words identical across many languages
  'Standard',
  'Binary',
  'Documentation',
  'Platform',
  'Cookies',
  'Priority',
  'Premium',
  'Enterprise',
  'Multi-Cloud',
  'MULTI-CLOUD',
  // Solution page technical terms
  'BTRFS COW',
  'AES-256-GCM',
  'SHA-256',
  'AES-256',
  'Live',
  'Down',
  // ROI calculator
  'SMB',
  'ROI Calculator',
  'Mid-Market',
  'Large Enterprise',
  // Persona page identifiers
  'CTO',
  'ARCHITECTURE',
  // Architecture / download labels (technical, not translated)
  'Intel (x64)',
  'ARM64',
  'ARMv7',
  'Apple Silicon (ARM64)',
  'Rediacc Desktop & CLI',
  // Package manager labels (brand names + OS names)
  'Debian/Ubuntu (.deb)',
  'APT (Debian / Ubuntu)',
  'DNF (Fedora / RHEL)',
  'Homebrew (macOS / Linux)',
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
  /^(docker|npm|git|ssh|curl|wget|sudo|rclone|rdc)\s/, // Commands
  /\.id$/, // Section anchor IDs (e.g. sections.introduction.id = "introduction")
  /\.cardClass$/, // CSS class names in solution pages
  /\.icon$/, // Icon identifiers
  /\.command$/, // CLI command strings in bottomCta/hero sections
  /\.ctaSlug$/, // CTA slug identifiers for persona pages
  /^~?\$[\d,.]+$/, // Dollar amounts ($0, $990, ~$200, $18,000)
  /^@\w+$/, // Social handles (@rediacc)
  /\.cloneVisual\.\w+\.title$/, // Visual diagram labels (dev-sarah, feature-auth-v2, etc.)
  /\.cloneVisual\.\w+\.status$/, // Visual diagram status labels
  /\.cloneVisual\.arrow\.(label|time)$/, // Visual arrow annotations
  /\.cloneVisual\.\w+\.patchInfo$/, // Patch info strings in visual diagrams
  /\.cloneVisual\.\w+\.size$/, // Size labels in visual diagrams
  /\.calculator\.withResults\.\w+$/, // Calculator result values
  /\.calculator\.withAnnual$/, // Annual calculator values
  /\.techDiff\.rediaccLabel$/, // Rediacc label with technical suffix (brand + tech term)
  /\.imageModal\.indicator$/, // Template format string {{current}} / {{total}}
  /^[\d,]+$/, // Comma-separated numbers (5,000 etc.)
  /\bRediacc\b.*\b(btrfs|CoW|Copy-on-Write|send\/receive)\b/, // Rediacc + technical term combos
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
  /^@\w+$/, // Social media handles (@rediacc)
  /^\{\{current\}\}\s*\/\s*\{\{total\}\}$/, // Pagination templates
  /\.id$/, // Keys ending in .id (HTML anchors, must stay English)
  /\.key$/, // Keys ending in .key (metric/data keys)
  /^(Intel|Apple Silicon|ARM)\b/, // Architecture labels
  /^ARM\w*$/, // ARM variants
  /\(x64\)|\(ARM64\)|\(\.deb\)|\(\.rpm\)/, // Architecture/file type suffixes
  /^(APT|APK|DNF|Homebrew|Pacman)\s*\(/, // Package manager labels with OS in parens
  /^Debian\/Ubuntu/, // Distro-specific labels
  /^Rediacc\s+(Desktop|CLI)/, // Product sub-names
  /^\$[\d,]+$/, // Price values like $19,999
  /^[\d,]+$/, // Numeric values like 5,000
  /^\d+\s*(GB|TB|MB|KB)\+?$/, // Storage sizes like 10 GB, 1 TB+
  /\.\w+\.(price|jobsPerMonth|repoSize)$/, // Pricing technical values (key pattern)
  /\.label$/, // Form labels (often identical: "Name *", "Email *")
  /\| Rediacc$/, // Page titles with brand suffix (e.g., "Downloads | Rediacc")
  /^\d+\.\d+\s/, // Numbered sections like "2.4 Cookies"
  /\(portable\)$/, // Technical descriptions like "AppImage (portable)"
  /\(64-bit\)$/, // Architecture labels like "x64 (64-bit)"
  /\.subsections\.\w+\.title$/, // Legal subsection titles (often kept in English)
  /\.badgeLabels\./, // Badge labels (often identical: "Standard", "Priority")
  /^\d+\.\s+\w+$/, // Numbered section titles like "1. Introduction", "1. Overview"
  /^~?\d+\s+minutes?$/, // Time durations like "~15 minutes", "30 minutes"
  /\.(rpo|rto)$/, // Recovery point/time objective values (technical metrics)
  /\.cardClass$/, // CSS class identifiers (sealed, restored, verified, down, config, compliant)
  /\.icon$/, // Icon identifiers (lock-arrow, refresh-arrow, etc.)
  /\.command$/, // CLI command examples (rdc clone, rdc backup, etc.)
  /^\d+\s*GB\s*·/, // Storage with annotation like "380 GB · locked"
  /^~?\$[\d,]+$/, // Currency values like ~$200
  /^\$[\d,]+\/mo$/, // Monthly prices like $4,500/mo, $1,440/mo, $33K/mo, $4.2K/mo
  /^\$[\d,.]+K?\/mo$/, // Monthly prices with K suffix
  /^<\d+\s+min$/, // Time values like <5 min, <4 min
  /^\d+m\s+\d+s$/, // Duration values like 3m 47s, 4m 12s, 3m 12s
  /^\d+\s+min$/, // Duration like 38 min
  /^\d+x\/year$/, // Frequency like 1x/year, 52x/year
  /^(Primary|Secondary)\s*\([a-z]+-[a-z]+-\d+\)$/, // Cloud region labels
  /^(AWS|Hetzner)\s*\([a-z0-9-]+\)$/, // Cloud provider labels with region
  /^(AES-256|SHA-256|AES-256-GCM)$/, // Encryption algorithm names
  /^BTRFS\s+COW$/, // Technical label
  /^Zero-knowledge$/, // Technical concept kept in English
  /^daily-\d{4}-\d{2}-\d{2}$/, // Date-based snapshot names
  /^\d{2}:\d{2}\s+UTC$/, // UTC timestamps
  /\.cloneVisual\.arrow\.time$/, // Visual arrow timing values (technical)
  /^Live$/, // Status labels kept short
  /^Down$/, // Status labels kept short
  /^brew$/, // Package manager command
  /^\d+\/\d+\s+healthy$/, // Health status like 8/8 healthy
  /^dev-sarah$/i, // Example dev environment name
  /^Dev-Sarah$/i, // Example dev environment name
  /^patch-test$/, // Example clone name
  /^(sealed|restored|verified|down|config|compliant)$/, // CSS class values
  /^24\/7$/, // Always-on indicator
  /\.rediaccLabel$/, // Rediacc technical labels (e.g., "Rediacc (btrfs CoW)")
  /^Rediacc\s+\(/, // Rediacc product labels with technical details
  /^Rediacc\s+\w+$/, // Rediacc product sub-labels (e.g., "Rediacc Retention", "Rediacc Verification")
  /\.patchInfo$/, // Patch info display strings (technical, kept in English)
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

function checkLocaleDir(name: string, localeDir: string, flatFiles = false): CheckResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  // Load English translations
  const enKeys: Record<string, TranslationValue> = {};
  let languages: string[];

  if (flatFiles) {
    // Flat layout: {dir}/en.json, {dir}/fr.json, etc.
    const enFile = path.join(localeDir, 'en.json');
    if (!fs.existsSync(enFile)) {
      errors.push(`[${name}] English file not found: ${enFile}`);
      return { errors, warnings };
    }
    const content = JSON.parse(fs.readFileSync(enFile, 'utf-8')) as TranslationObject;
    const flat = flatten(content);
    for (const [key, value] of Object.entries(flat)) {
      enKeys[key] = value;
    }
    languages = fs
      .readdirSync(localeDir)
      .filter((f) => f !== 'en.json' && !f.startsWith('.') && f.endsWith('.json'))
      .map((f) => f.replace('.json', ''));
  } else {
    // Directory layout: {dir}/en/*.json
    const enDir = path.join(localeDir, 'en');
    if (!fs.existsSync(enDir)) {
      errors.push(`[${name}] English locale directory not found: ${enDir}`);
      return { errors, warnings };
    }
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
    languages = fs
      .readdirSync(localeDir)
      .filter(
        (d) => d !== 'en' && !d.startsWith('.') && fs.statSync(path.join(localeDir, d)).isDirectory()
      );
  }

  const totalEnKeys = Object.keys(enKeys).length;
  const stats: Record<string, LanguageStats> = {};

  for (const lang of languages) {
    const langKeys: Record<string, TranslationValue> = {};
    let untranslated = 0;
    let missing = 0;

    // Load language translations
    if (flatFiles) {
      const langFile = path.join(localeDir, `${lang}.json`);
      if (!fs.existsSync(langFile)) {
        missing = totalEnKeys;
      } else {
        const content = JSON.parse(fs.readFileSync(langFile, 'utf-8')) as TranslationObject;
        const flat = flatten(content);
        Object.assign(langKeys, flat);
      }
    } else {
      const enDir = path.join(localeDir, 'en');
      const enFiles = fs.readdirSync(enDir).filter((f) => f.endsWith('.json'));
      const langDir = path.join(localeDir, lang);
      for (const file of enFiles) {
        const langFile = path.join(langDir, file);
        if (!fs.existsSync(langFile)) {
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

  // Check WWW locales (flat files: {lang}.json)
  const wwwLocales = path.join(__dirname, '../packages/www/src/i18n/translations');
  if (fs.existsSync(wwwLocales)) {
    console.log('Checking WWW translations...');
    const { errors, warnings, stats } = checkLocaleDir('www', wwwLocales, true);
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

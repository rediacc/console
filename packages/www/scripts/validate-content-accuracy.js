#!/usr/bin/env node
/**
 * Content Accuracy Validation Script
 *
 * Validates that CLI commands and URLs in content files are correct.
 * Complements validate-docs-cli-usage.js (code fences) and
 * validate-landing-cli-usage.js (structured terminal blocks) by checking:
 *
 * Rules:
 * - docs-inline-cli-invalid: rdc commands in markdown prose (outside code fences)
 * - json-cli-command-invalid: rdc commands in translation JSON string values (--strict only)
 * - invalid-rediacc-url: URLs with rediacc domains not in the allowlist
 *
 * Usage:
 *   node scripts/validate-content-accuracy.js           # docs + URLs (CI default)
 *   node scripts/validate-content-accuracy.js --strict   # also check JSON translation strings
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseRdcCommand } from './lib/cli-reference-catalog.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, '..');
const DOCS_DIR = path.join(ROOT_DIR, 'src', 'content', 'docs');
const TRANSLATIONS_DIR = path.join(ROOT_DIR, 'src', 'i18n', 'translations');

const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

// Auto-generated docs validated separately by validate-cli-docs.js
const EXCLUDED_DOC_SLUGS = new Set([
  'cli-application.md',
  'cli-application-cloud.md',
  'web-application.md',
]);

// Commands that exist in the CLI but are not exported to command-tree.json
const TREE_UNLISTED_COMMANDS = new Set(['shortcuts']);

// Valid *.rediacc.com domains
const VALID_REDIACC_DOMAINS = new Set(['www.rediacc.com', 'releases.rediacc.com']);

// Regex to extract rdc commands from inline backticks
const BACKTICK_RDC_RE = /`(rdc\s[^`]+)`/g;
// Regex to extract rdc commands from JSON string values
const JSON_RDC_RE = /\brdc\s+\S+[^"']*/g;
// Regex to match URLs with rediacc in the domain
const REDIACC_URL_RE = /https?:\/\/([a-z0-9.-]*rediacc[a-z0-9.-]*\.[a-z]{2,})(\/[^\s"'`)\]]*)?/gi;

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  yellow: (s) => `\x1b[33m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function addError(errors, rule, file, line, message, matchedText, suggestion) {
  errors.push({ rule, file, line, message, matchedText, suggestion });
}

// ---------------------------------------------------------------------------
// Rule 1: docs-inline-cli-invalid (markdown docs, inline text outside fences)
// ---------------------------------------------------------------------------

function extractInlineRdcCommands(content, file) {
  const commands = [];
  const lines = content.split(/\r?\n/);
  let inFence = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;

    // Extract from inline backticks: `rdc machine info prod`
    BACKTICK_RDC_RE.lastIndex = 0;
    let match;
    while ((match = BACKTICK_RDC_RE.exec(line)) !== null) {
      commands.push({ text: match[1].trim(), line: i + 1, file });
    }
  }

  return commands;
}

// ---------------------------------------------------------------------------
// Rule 2: json-cli-command-invalid (translation JSON string values)
// ---------------------------------------------------------------------------

function extractJsonRdcCommands(jsonContent, file) {
  const commands = [];
  const lines = jsonContent.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.includes('rdc ')) continue;

    JSON_RDC_RE.lastIndex = 0;
    let match;
    while ((match = JSON_RDC_RE.exec(line)) !== null) {
      let text = match[0].trim();
      text = text.replace(/[",}\]]+$/, '').trim();
      text = text.replace(/\.\s*$/, '').trim();
      if (text.split(/\s+/).length >= 2) {
        commands.push({ text, line: i + 1, file });
      }
    }
  }

  return commands;
}

// ---------------------------------------------------------------------------
// Shared CLI command validation
// ---------------------------------------------------------------------------

// Inline docs legitimately mention commands without full arguments.
// Only report errors that indicate a genuinely wrong command or flag.
const INLINE_REPORTABLE_REASONS = new Set([
  'unknown-command',
  'unknown-option',
  'unknown-global-option',
]);

function validateRdcCommands(commands, errors, rule) {
  for (const cmd of commands) {
    let text = cmd.text.replace(/^\$\s*/, '');
    // Stop at pipes, redirects, semicolons
    text = text
      .split(/\s*[|;>&]/)
      .shift()
      .trim();
    // Strip trailing prose punctuation
    text = text.replace(/[.,:;!?)}\]]+$/, '').trim();

    if (!text.startsWith('rdc ')) continue;

    // Skip glob/wildcard patterns (e.g. "rdc machine info *")
    if (/[*?]/.test(text)) continue;

    const tokens = text.split(/\s+/);

    // Skip if the command position has angle-bracket placeholder (e.g. "rdc --flag <command>")
    const firstNonFlag = tokens.slice(1).find((t) => !t.startsWith('-'));
    if (firstNonFlag && firstNonFlag.startsWith('<')) continue;

    // Allow commands that exist but aren't in the command tree export
    const rootCmd = tokens.find((t) => !t.startsWith('-') && t !== 'rdc');
    if (rootCmd && TREE_UNLISTED_COMMANDS.has(rootCmd)) continue;

    const parsed = parseRdcCommand(text);
    if (!parsed.ok && INLINE_REPORTABLE_REASONS.has(parsed.reason)) {
      const message = formatParseError(parsed);
      const suggestion = suggestedFix(parsed);
      addError(errors, rule, cmd.file, cmd.line, message, text, suggestion);
    }
  }
}

function formatParseError(parsed) {
  switch (parsed.reason) {
    case 'unknown-global-option':
      return `Unknown global option: ${parsed.flag}`;
    case 'unknown-command':
      return `Unknown command: rdc ${parsed.near}`;
    case 'unknown-option':
      return `Unknown option ${parsed.flag} for "rdc ${parsed.commandPath}"`;
    default:
      return `Invalid command (${parsed.reason || 'unknown'})`;
  }
}

function suggestedFix(parsed) {
  if (parsed.reason === 'unknown-command') return 'Use a valid rdc subcommand (see rdc --help)';
  if (parsed.reason === 'unknown-option')
    return `Remove or replace unsupported option ${parsed.flag}`;
  return null;
}

// ---------------------------------------------------------------------------
// Rule 3: invalid-rediacc-url
// ---------------------------------------------------------------------------

function extractRediaccUrls(content, file) {
  const urls = [];
  const lines = content.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    REDIACC_URL_RE.lastIndex = 0;
    let match;
    while ((match = REDIACC_URL_RE.exec(line)) !== null) {
      const domain = match[1].toLowerCase();
      const fullUrl = match[0];
      urls.push({ domain, fullUrl, line: i + 1, file });
    }
  }

  return urls;
}

function validateUrls(urls, errors) {
  for (const entry of urls) {
    if (!VALID_REDIACC_DOMAINS.has(entry.domain)) {
      addError(
        errors,
        'invalid-rediacc-url',
        entry.file,
        entry.line,
        `Invalid rediacc domain: ${entry.domain}`,
        entry.fullUrl,
        `Use one of: ${[...VALID_REDIACC_DOMAINS].join(', ')}`
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function listMarkdownFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((f) => f.endsWith('.md') && !EXCLUDED_DOC_SLUGS.has(f));
}

function groupByRule(errors) {
  const grouped = new Map();
  for (const error of errors) {
    if (!grouped.has(error.rule)) grouped.set(error.rule, []);
    grouped.get(error.rule).push(error);
  }
  return grouped;
}

function printSummary(errors, warnings) {
  console.log(colors.bold('Content Accuracy Validation'));
  console.log('='.repeat(60));

  if (errors.length === 0 && warnings.length === 0) {
    console.log(colors.green('✓ All content accuracy checks passed.'));
    console.log('='.repeat(60));
    return 0;
  }

  // Print errors
  if (errors.length > 0) {
    const grouped = groupByRule(errors);
    for (const [rule, items] of grouped.entries()) {
      console.log(colors.red(`\n[${rule}] (${items.length} errors)`));
      console.log(colors.dim('-'.repeat(40)));
      for (const item of items) {
        console.log(colors.red(`  ✗ ${item.file}:${item.line}`));
        console.log(colors.dim(`    ${item.message}`));
        console.log(colors.cyan(`    → ${item.matchedText}`));
        if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
      }
    }
  }

  // Print warnings
  if (warnings.length > 0) {
    const grouped = groupByRule(warnings);
    for (const [rule, items] of grouped.entries()) {
      console.log(colors.yellow(`\n[${rule}] (${items.length} warnings)`));
      console.log(colors.dim('-'.repeat(40)));
      for (const item of items) {
        console.log(colors.yellow(`  ⚠ ${item.file}:${item.line}`));
        console.log(colors.dim(`    ${item.message}`));
        console.log(colors.cyan(`    → ${item.matchedText}`));
        if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
      }
    }
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  const parts = [];
  if (errors.length > 0) parts.push(colors.red(`${errors.length} errors`));
  if (warnings.length > 0) parts.push(colors.yellow(`${warnings.length} warnings`));
  console.log(`SUMMARY: ${parts.join(', ')}`);
  console.log('='.repeat(60));
  return errors.length > 0 ? 1 : 0;
}

function main() {
  const args = process.argv.slice(2);
  const strict = args.includes('--strict');
  const help = args.includes('--help') || args.includes('-h');

  if (help) {
    console.log(`
Usage: node scripts/validate-content-accuracy.js [options]

Options:
  --strict    Also validate CLI commands in translation JSON (warnings → errors)
  --help, -h  Show this help message

Rules (always enforced):
  docs-inline-cli-invalid   rdc commands in markdown prose must be valid
  invalid-rediacc-url       rediacc URLs must use valid domains

Rules (--strict only — otherwise warnings):
  json-cli-command-invalid  rdc commands in translation JSON strings must be valid
`);
    process.exit(0);
  }

  console.log(colors.dim(`Scanning content in ${ROOT_DIR}/src/...`));
  if (strict) console.log(colors.yellow('Strict mode: JSON translation CLI errors will fail CI'));

  const errors = [];
  const warnings = [];

  // Scan markdown docs — always enforced
  for (const lang of LANGUAGES) {
    const langDir = path.join(DOCS_DIR, lang);
    const slugs = listMarkdownFiles(langDir);

    for (const slug of slugs) {
      const fullPath = path.join(langDir, slug);
      const content = fs.readFileSync(fullPath, 'utf-8');
      const file = `docs/${lang}/${slug}`;

      const rdcCommands = extractInlineRdcCommands(content, file);
      validateRdcCommands(rdcCommands, errors, 'docs-inline-cli-invalid');

      const urls = extractRediaccUrls(content, file);
      validateUrls(urls, errors);
    }
  }

  // Scan translation JSON files
  for (const lang of LANGUAGES) {
    const jsonPath = path.join(TRANSLATIONS_DIR, `${lang}.json`);
    if (!fs.existsSync(jsonPath)) continue;

    const content = fs.readFileSync(jsonPath, 'utf-8');
    const file = `translations/${lang}.json`;

    // CLI commands: errors in strict mode, warnings otherwise
    const rdcCommands = extractJsonRdcCommands(content, file);
    const target = strict ? errors : warnings;
    validateRdcCommands(rdcCommands, target, 'json-cli-command-invalid');

    // URLs: always enforced
    const urls = extractRediaccUrls(content, file);
    validateUrls(urls, errors);
  }

  process.exit(printSummary(errors, warnings));
}

main();

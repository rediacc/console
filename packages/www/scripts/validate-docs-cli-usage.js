#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';
import {
  mergeContinuationLines,
  parseRdcCommand,
  SHELL_FENCE_LANGS,
  TARGET_DOC_CATEGORIES,
} from './lib/cli-reference-catalog.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DOCS_DIR = path.resolve(__dirname, '../src/content/docs');
const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function listMarkdownFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((file) => file.endsWith('.md'));
}

function getTargetSlugs() {
  const slugs = [];
  for (const slug of listMarkdownFiles(path.join(DOCS_DIR, 'en'))) {
    const fullPath = path.join(DOCS_DIR, 'en', slug);
    const raw = fs.readFileSync(fullPath, 'utf-8');
    const parsed = matter(raw);
    const category = parsed.data?.category;
    // Skip auto-generated docs (validated by validate-cli-docs.js)
    if (parsed.data?.generated) continue;
    if (typeof category === 'string' && TARGET_DOC_CATEGORIES.has(category)) {
      slugs.push(slug);
    }
  }
  return slugs;
}

function addError(errors, rule, file, line, message, commandText, suggestion) {
  errors.push({ rule, file, line, message, commandText, suggestion });
}

function formatError(parsed) {
  switch (parsed.reason) {
    case 'unknown-global-option':
      return `Unknown global option: ${parsed.flag}`;
    case 'unknown-command':
      return `Unknown command path near: ${parsed.near}`;
    case 'unknown-option':
      return `Unknown option ${parsed.flag} for command "rdc ${parsed.commandPath}"`;
    case 'missing-required-args':
      return `Missing required positional arguments for "rdc ${parsed.commandPath}"`;
    case 'missing-reference-entry':
      return `No CLI reference entry for "rdc ${parsed.commandPath}"`;
    default:
      return `Invalid command usage (${parsed.reason || 'unknown'})`;
  }
}

function suggestedFix(parsed) {
  if (parsed.reason === 'unknown-option') {
    return `Remove or replace unsupported option ${parsed.flag}`;
  }
  if (parsed.reason === 'unknown-command') {
    return 'Use a command from cli-application reference';
  }
  if (parsed.reason === 'missing-required-args') {
    return 'Provide all required positional arguments';
  }
  if (parsed.reason === 'missing-reference-entry') {
    return 'Regenerate CLI docs and ensure command exists in reference';
  }
  return null;
}

function validateCodeFences(content, file, errors) {
  const lines = content.split(/\r?\n/);
  let inFence = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    if (line.startsWith('```')) {
      const lang = line.slice(3).trim().toLowerCase();
      inFence = SHELL_FENCE_LANGS.has(lang);
      continue;
    }

    if (!inFence) continue;
    if (!line || line.startsWith('#') || !line.startsWith('rdc')) continue;

    const merged = mergeContinuationLines(lines, i);
    const commandText = merged.command;
    i = merged.endIndex;

    const parsed = parseRdcCommand(commandText);
    if (!parsed.ok && parsed.reason !== 'not-rdc') {
      addError(
        errors,
        'docs-cli-command-invalid',
        file,
        i + 1,
        formatError(parsed),
        commandText,
        suggestedFix(parsed)
      );
    }
  }
}

function groupByRule(errors) {
  const grouped = new Map();
  for (const error of errors) {
    if (!grouped.has(error.rule)) grouped.set(error.rule, []);
    grouped.get(error.rule).push(error);
  }
  return grouped;
}

function printSummary(errors) {
  console.log(colors.bold('Docs CLI Usage Validation'));
  console.log('='.repeat(60));

  if (errors.length === 0) {
    console.log(colors.green('✓ All targeted docs command examples are valid.'));
    console.log('='.repeat(60));
    return 0;
  }

  const grouped = groupByRule(errors);
  for (const [rule, items] of grouped.entries()) {
    console.log(colors.red(`\n[${rule}] (${items.length} errors)`));
    console.log(colors.dim('-'.repeat(40)));
    for (const item of items) {
      console.log(colors.red(`  ✗ ${item.file}:${item.line}`));
      console.log(colors.dim(`    ${item.message}`));
      console.log(colors.cyan(`    → ${item.commandText}`));
      if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
    }
  }

  console.log('\n' + '='.repeat(60));
  console.log(colors.red(`✗ Validation failed (${errors.length} errors)`));
  console.log('='.repeat(60));
  return 1;
}

function main() {
  const targetSlugs = getTargetSlugs();
  const errors = [];

  for (const lang of LANGUAGES) {
    for (const slug of targetSlugs) {
      const fullPath = path.join(DOCS_DIR, lang, slug);
      if (!fs.existsSync(fullPath)) continue;

      const raw = fs.readFileSync(fullPath, 'utf-8');
      const file = `docs/${lang}/${slug}`;
      validateCodeFences(raw, file, errors);
    }
  }

  process.exit(printSummary(errors));
}

main();

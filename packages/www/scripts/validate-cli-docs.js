#!/usr/bin/env node
/**
 * CLI Documentation Validator
 *
 * Validates that the generated cli-application.md files are fresh and consistent
 * across all supported languages.
 *
 * Rules:
 * - cli-doc-freshness: Re-generates in memory and diffs against file on disk (all languages)
 * - cli-doc-generated-marker: File must contain the auto-generated comment (all languages)
 * - cli-doc-supplement-paths: Every path in docs.supplements must match a command in cli.json
 *
 * Usage:
 *   node packages/www/scripts/validate-cli-docs.js
 *
 * Exit codes:
 *   0 - All checks passed
 *   1 - Validation failed
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// All supported languages
const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

// Path helpers
function getCliJsonPath(lang) {
  return path.resolve(__dirname, `../../cli/src/i18n/locales/${lang}/cli.json`);
}

function getDocPath(lang) {
  return path.resolve(__dirname, `../src/content/docs/${lang}/cli-application.md`);
}

const GENERATOR_PATH = path.resolve(__dirname, './generate-cli-docs.js');

const AUTO_GENERATED_MARKER = '<!-- THIS FILE IS AUTO-GENERATED. Do not edit manually. -->';

// ANSI colors
const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  yellow: (s) => `\x1b[33m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

/**
 * Resolve a dotted path in an object
 */
function getNestedValue(obj, dotPath) {
  const parts = dotPath.split('.');
  let current = obj;
  for (const part of parts) {
    if (current === null || current === undefined || typeof current !== 'object') return undefined;
    current = current[part];
  }
  return current;
}

/**
 * Walk all command paths in docs.supplements (skipping known supplement-only keys)
 */
function walkSupplementPaths(obj, prefix = '') {
  const paths = [];
  const supplementKeys = ['tip', 'warning', 'note', 'afterDescription'];

  for (const [key, value] of Object.entries(obj)) {
    if (supplementKeys.includes(key)) continue;

    const currentPath = prefix ? `${prefix}.${key}` : key;

    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      // Check if this is a leaf supplement node (all keys are supplement keys)
      const childKeys = Object.keys(value);
      const isLeafSupplement = childKeys.every((k) => supplementKeys.includes(k));

      if (!isLeafSupplement) {
        // Has nested command paths — recurse
        paths.push(...walkSupplementPaths(value, currentPath));
      } else {
        // Leaf supplement node — the path itself should exist in cli.json
        paths.push(currentPath);
      }
    }
  }
  return paths;
}

async function main() {
  console.log(colors.bold('CLI Documentation Validation'));
  console.log('=' .repeat(60) + '\n');

  const errors = [];

  // Import the generate function
  const { generate } = await import(GENERATOR_PATH);
  const cliJsonEn = JSON.parse(fs.readFileSync(getCliJsonPath('en'), 'utf-8'));

  // ── Rule 1: cli-doc-freshness (all languages) ──
  console.log('Checking cli-doc-freshness...');

  for (const lang of LANGUAGES) {
    const docPath = getDocPath(lang);

    if (!fs.existsSync(docPath)) {
      errors.push({
        rule: 'cli-doc-freshness',
        message: `${lang}/cli-application.md does not exist`,
        suggestion: 'Run: npm run generate:cli-docs -w @rediacc/www',
      });
    } else {
      const expected = generate(lang, cliJsonEn);
      const actual = fs.readFileSync(docPath, 'utf-8');

      if (expected !== actual) {
        errors.push({
          rule: 'cli-doc-freshness',
          message: `${lang}/cli-application.md: generated output differs from file on disk`,
          suggestion: 'Run: npm run generate:cli-docs -w @rediacc/www',
        });
      } else {
        console.log(colors.green(`  ✓ ${lang}/cli-application.md is up to date`));
      }
    }
  }

  // ── Rule 2: cli-doc-generated-marker (all languages) ──
  console.log('Checking cli-doc-generated-marker...');

  for (const lang of LANGUAGES) {
    const docPath = getDocPath(lang);

    if (fs.existsSync(docPath)) {
      const content = fs.readFileSync(docPath, 'utf-8');
      if (!content.includes(AUTO_GENERATED_MARKER)) {
        errors.push({
          rule: 'cli-doc-generated-marker',
          message: `${lang}/cli-application.md is missing the auto-generated marker comment`,
          suggestion: `File must contain: ${AUTO_GENERATED_MARKER}`,
        });
      } else {
        console.log(colors.green(`  ✓ ${lang}/cli-application.md: auto-generated marker present`));
      }
    }
  }

  // ── Rule 3: cli-doc-supplement-paths ──
  console.log('Checking cli-doc-supplement-paths...');

  const docsSupplements = cliJsonEn.docs?.supplements;
  if (docsSupplements) {
    const supplementPaths = walkSupplementPaths(docsSupplements);
    let orphanCount = 0;

    for (const supPath of supplementPaths) {
      // Check in commands.* namespace
      const commandValue = getNestedValue(cliJsonEn.commands, supPath);
      if (commandValue === undefined) {
        orphanCount++;
        errors.push({
          rule: 'cli-doc-supplement-paths',
          message: `Supplement path "docs.supplements.${supPath}" has no matching command in cli.json`,
          suggestion: `Remove or update the path in the docs.supplements section of cli.json`,
        });
      }
    }

    if (orphanCount === 0) {
      console.log(colors.green('  ✓ All supplement paths match cli.json commands'));
    }
  }

  // ── Summary ──
  console.log('\n' + '='.repeat(60));

  if (errors.length === 0) {
    console.log(colors.green('✓ All CLI documentation checks passed\n'));
    process.exit(0);
  }

  // Group errors by rule
  const grouped = {};
  for (const err of errors) {
    if (!grouped[err.rule]) grouped[err.rule] = [];
    grouped[err.rule].push(err);
  }

  for (const [rule, ruleErrors] of Object.entries(grouped)) {
    console.log(colors.red(`\n[${rule}] (${ruleErrors.length} error${ruleErrors.length === 1 ? '' : 's'})`));
    console.log(colors.dim('-'.repeat(40)));
    for (const err of ruleErrors) {
      console.log(colors.red(`  ✗ ${err.message}`));
      if (err.suggestion) {
        console.log(colors.cyan(`    → ${err.suggestion}`));
      }
    }
  }

  console.log(
    '\n' + colors.red(`✗ CLI documentation validation FAILED (${errors.length} error${errors.length === 1 ? '' : 's'})\n`)
  );
  process.exit(1);
}

main();

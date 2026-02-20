#!/usr/bin/env node
/**
 * Content Validation Script
 *
 * Validates translation parity and consistency across blog and docs content.
 *
 * Rules:
 * - content-parity: All English posts/docs must exist in all languages
 * - language-mismatch: Frontmatter `language` must match directory
 * - orphan-translation: File exists in non-English but not in English (deleted or renamed)
 * - missing-required-field: Required frontmatter fields must be present
 */

import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, '..');
const CONTENT_DIR = path.join(ROOT_DIR, 'src', 'content');

const SUPPORTED_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];
const SOURCE_LANGUAGE = 'en';
const COLLECTIONS = ['blog', 'docs'];

// English-only paths (permanently excluded - no translations needed)
const EXCLUSIONS = {
  docs: ['cli/'], // CLI API reference docs are English-only
};

// Required frontmatter fields per collection (must match Astro content schema)
const REQUIRED_FIELDS = {
  blog: ['title', 'description', 'publishedDate', 'author', 'category', 'tags'],
  docs: ['title', 'description'],
};

// Valid enum values per collection (must match Astro content schema)
const ENUM_VALUES = {
  blog: {
    category: ['tutorial', 'announcement', 'guide', 'case-study', 'other'],
  },
};

// Array fields that must be non-empty
const ARRAY_FIELDS = {
  blog: ['tags'],
};

// ANSI colors
const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  yellow: (s) => `\x1b[33m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

/**
 * Get all markdown files in a collection for a specific language
 */
function getFilesForLanguage(collection, lang) {
  const langDir = path.join(CONTENT_DIR, collection, lang);
  if (!fs.existsSync(langDir)) {
    return [];
  }

  const files = [];
  const exclusions = EXCLUSIONS[collection] || [];

  function walkDir(dir, relativePath = '') {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(relativePath, entry.name);

      // Check exclusions
      if (exclusions.some((exc) => entryPath.startsWith(exc))) {
        continue;
      }

      if (entry.isDirectory()) {
        walkDir(path.join(dir, entry.name), entryPath);
      } else if (entry.name.endsWith('.md')) {
        files.push({
          filename: entry.name,
          relativePath: entryPath,
          fullPath: path.join(dir, entry.name),
        });
      }
    }
  }

  walkDir(langDir);
  return files;
}

/**
 * Parse frontmatter from a file
 */
function parseFrontmatter(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    const { data } = matter(content);
    return data;
  } catch {
    return null;
  }
}

function isValidSourceHash(value) {
  return typeof value === 'string' && /^[a-f0-9]{16}$/i.test(value.trim());
}

/**
 * Validate all content
 */
function validateContent(_strict = false) {
  const errors = [];
  const warnings = [];

  for (const collection of COLLECTIONS) {
    const englishFiles = getFilesForLanguage(collection, SOURCE_LANGUAGE);
    const englishSlugs = new Set(englishFiles.map((f) => f.relativePath));

    // Check each language
    for (const lang of SUPPORTED_LANGUAGES) {
      if (lang === SOURCE_LANGUAGE) continue;

      const langFiles = getFilesForLanguage(collection, lang);
      const langSlugs = new Set(langFiles.map((f) => f.relativePath));

      // Check for missing translations (content-parity)
      for (const englishFile of englishFiles) {
        if (!langSlugs.has(englishFile.relativePath)) {
          errors.push({
            rule: 'content-parity',
            severity: 'error',
            file: `${collection}/${lang}/${englishFile.relativePath}`,
            message: `Missing translation for "${englishFile.relativePath}"`,
            suggestion: `Create ${collection}/${lang}/${englishFile.relativePath}`,
          });
        }
      }

      // Check each file in this language
      for (const file of langFiles) {
        const frontmatter = parseFrontmatter(file.fullPath);
        const relativeFile = `${collection}/${lang}/${file.relativePath}`;

        // Check for orphan files (exists in translation but not in English)
        if (!englishSlugs.has(file.relativePath)) {
          errors.push({
            rule: 'orphan-translation',
            severity: 'error',
            file: relativeFile,
            message: `No English equivalent for "${file.relativePath}" (deleted or renamed from English)`,
            suggestion: `Delete this file or create ${collection}/en/${file.relativePath}`,
          });
        }

        // Check frontmatter language field
        if (frontmatter) {
          if (frontmatter.translationPending === true && !frontmatter.translationPendingReason) {
            errors.push({
              rule: 'translation-pending-reason',
              severity: 'error',
              file: relativeFile,
              message:
                'translationPending=true requires translationPendingReason with a concrete explanation',
              suggestion: 'Add translationPendingReason to frontmatter',
            });
          }

          if (frontmatter.sourceHash && !isValidSourceHash(frontmatter.sourceHash)) {
            errors.push({
              rule: 'invalid-source-hash',
              severity: 'error',
              file: relativeFile,
              message: `Invalid sourceHash "${frontmatter.sourceHash}" (expected 16 hex chars)`,
              suggestion: 'Set sourceHash to a 16-character hexadecimal hash',
            });
          }

          if (frontmatter.language && frontmatter.language !== lang) {
            errors.push({
              rule: 'language-mismatch',
              severity: 'error',
              file: relativeFile,
              message: `Frontmatter language "${frontmatter.language}" doesn't match directory "${lang}"`,
              suggestion: `Change frontmatter language to "${lang}"`,
            });
          }

          // Check required fields
          const requiredFields = REQUIRED_FIELDS[collection] || [];
          for (const field of requiredFields) {
            if (!frontmatter[field]) {
              errors.push({
                rule: 'missing-required-field',
                severity: 'error',
                file: relativeFile,
                message: `Missing required field "${field}"`,
                suggestion: `Add "${field}" to frontmatter`,
              });
            }
          }

          // Check enum fields
          const enumFields = ENUM_VALUES[collection] || {};
          for (const [field, validValues] of Object.entries(enumFields)) {
            if (frontmatter[field] && !validValues.includes(frontmatter[field])) {
              errors.push({
                rule: 'invalid-enum-value',
                severity: 'error',
                file: relativeFile,
                message: `Invalid value "${frontmatter[field]}" for field "${field}"`,
                suggestion: `Use one of: ${validValues.join(', ')}`,
              });
            }
          }

          // Check array fields are non-empty
          const arrayFields = ARRAY_FIELDS[collection] || [];
          for (const field of arrayFields) {
            if (
              frontmatter[field] &&
              (!Array.isArray(frontmatter[field]) || frontmatter[field].length === 0)
            ) {
              errors.push({
                rule: 'invalid-array-field',
                severity: 'error',
                file: relativeFile,
                message: `Field "${field}" must be a non-empty array`,
                suggestion: `Add at least one item to "${field}"`,
              });
            }
          }
        }
      }
    }

    // Also validate English files for required fields, enums, and arrays
    for (const file of englishFiles) {
      const frontmatter = parseFrontmatter(file.fullPath);
      const relativeFile = `${collection}/${SOURCE_LANGUAGE}/${file.relativePath}`;

      if (frontmatter) {
        if (frontmatter.translationPending === true && !frontmatter.translationPendingReason) {
          errors.push({
            rule: 'translation-pending-reason',
            severity: 'error',
            file: relativeFile,
            message:
              'translationPending=true requires translationPendingReason with a concrete explanation',
            suggestion: 'Add translationPendingReason to frontmatter',
          });
        }

        const requiredFields = REQUIRED_FIELDS[collection] || [];
        for (const field of requiredFields) {
          if (!frontmatter[field]) {
            errors.push({
              rule: 'missing-required-field',
              severity: 'error',
              file: relativeFile,
              message: `Missing required field "${field}"`,
              suggestion: `Add "${field}" to frontmatter`,
            });
          }
        }

        // Check enum fields for English
        const enumFields = ENUM_VALUES[collection] || {};
        for (const [field, validValues] of Object.entries(enumFields)) {
          if (frontmatter[field] && !validValues.includes(frontmatter[field])) {
            errors.push({
              rule: 'invalid-enum-value',
              severity: 'error',
              file: relativeFile,
              message: `Invalid value "${frontmatter[field]}" for field "${field}"`,
              suggestion: `Use one of: ${validValues.join(', ')}`,
            });
          }
        }

        // Check array fields for English
        const arrayFields = ARRAY_FIELDS[collection] || [];
        for (const field of arrayFields) {
          if (
            frontmatter[field] &&
            (!Array.isArray(frontmatter[field]) || frontmatter[field].length === 0)
          ) {
            errors.push({
              rule: 'invalid-array-field',
              severity: 'error',
              file: relativeFile,
              message: `Field "${field}" must be a non-empty array`,
              suggestion: `Add at least one item to "${field}"`,
            });
          }
        }
      }
    }
  }

  return { errors, warnings };
}

/**
 * Group issues by rule
 */
function groupByRule(issues) {
  const grouped = {};
  for (const issue of issues) {
    if (!grouped[issue.rule]) {
      grouped[issue.rule] = [];
    }
    grouped[issue.rule].push(issue);
  }
  return grouped;
}

/**
 * Print validation results
 */
function printResults(errors, warnings, strict) {
  console.log('\n' + colors.bold('='.repeat(60)));
  console.log(colors.bold('CONTENT VALIDATION RESULTS'));
  console.log(colors.bold('='.repeat(60)) + '\n');

  const groupedErrors = groupByRule(errors);
  const groupedWarnings = groupByRule(warnings);

  // Print errors
  for (const [rule, issues] of Object.entries(groupedErrors)) {
    console.log(colors.red(`[${rule}] (${issues.length} errors)`));
    console.log(colors.dim('-'.repeat(40)));
    for (const issue of issues) {
      console.log(colors.red(`  \u2717 ${issue.file}`));
      console.log(colors.dim(`    ${issue.message}`));
      if (issue.suggestion) {
        console.log(colors.cyan(`    \u2192 ${issue.suggestion}`));
      }
    }
    console.log('');
  }

  // Print warnings
  for (const [rule, issues] of Object.entries(groupedWarnings)) {
    console.log(colors.yellow(`[${rule}] (${issues.length} warnings)`));
    console.log(colors.dim('-'.repeat(40)));
    for (const issue of issues) {
      console.log(colors.yellow(`  \u26a0 ${issue.file}`));
      console.log(colors.dim(`    ${issue.message}`));
      if (issue.suggestion) {
        console.log(colors.cyan(`    \u2192 ${issue.suggestion}`));
      }
    }
    console.log('');
  }

  // Summary
  console.log(colors.bold('='.repeat(60)));
  const errorCount = errors.length;
  const warningCount = warnings.length;

  if (errorCount === 0 && warningCount === 0) {
    console.log(colors.green('\u2714 All content validation passed!'));
  } else {
    const summaryParts = [];
    if (errorCount > 0) {
      summaryParts.push(colors.red(`${errorCount} error${errorCount === 1 ? '' : 's'}`));
    }
    if (warningCount > 0) {
      summaryParts.push(colors.yellow(`${warningCount} warning${warningCount === 1 ? '' : 's'}`));
    }
    console.log(`SUMMARY: ${summaryParts.join(', ')}`);
  }
  console.log(colors.bold('='.repeat(60)) + '\n');

  // Exit code
  if (errorCount > 0) {
    return 1;
  }
  if (strict && warningCount > 0) {
    return 1;
  }
  return 0;
}

/**
 * Main
 */
function main() {
  const args = process.argv.slice(2);
  const strict = args.includes('--strict');
  const help = args.includes('--help') || args.includes('-h');

  if (help) {
    console.log(`
Usage: node validate-content.js [options]

Options:
  --strict    Treat warnings as errors (exit code 1)
  --help, -h  Show this help message

Rules:
  content-parity         All English content must exist in all languages
  language-mismatch      Frontmatter language must match directory
  orphan-translation     File exists in translation but not in English (deleted or renamed)
  missing-required-field Required frontmatter fields must be present
  invalid-enum-value     Enum fields must use valid values (e.g., category)
  invalid-array-field    Array fields must be non-empty (e.g., tags)

Exclusions:
  - docs/en/cli/              (CLI API reference, English-only by design)
`);
    process.exit(0);
  }

  console.log(colors.dim(`Validating content in ${CONTENT_DIR}...`));
  console.log(colors.dim(`Languages: ${SUPPORTED_LANGUAGES.join(', ')}`));
  console.log(colors.dim(`Collections: ${COLLECTIONS.join(', ')}`));
  if (strict) {
    console.log(colors.yellow('Strict mode enabled: warnings will cause failure'));
  }

  const { errors, warnings } = validateContent(strict);
  const exitCode = printResults(errors, warnings, strict);
  process.exit(exitCode);
}

main();

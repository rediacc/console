#!/usr/bin/env node
/**
 * Content Validation Script
 *
 * Validates translation parity and consistency across blog and docs content.
 *
 * Rules:
 * - content-parity: All English posts/docs must exist in all languages
 * - language-mismatch: Frontmatter `language` must match directory
 * - localized-filename: Filenames must be English slugs across all languages
 * - orphan-file: File exists in non-English but not in English
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
  docs: ['cli/'], // CLI API reference is technical docs, English-only by design
};

// Required frontmatter fields per collection
const REQUIRED_FIELDS = {
  blog: ['title', 'description', 'publishedDate'],
  docs: ['title', 'description'],
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

/**
 * Check if a filename is localized (not using English slug)
 */
function isLocalizedFilename(filename, englishFiles) {
  const slug = filename.replace('.md', '');
  const englishSlugs = englishFiles.map((f) => f.filename.replace('.md', ''));
  return !englishSlugs.includes(slug);
}

/**
 * Find the likely English equivalent for a localized filename
 */
function findEnglishEquivalent(localizedFilename, frontmatter, englishFiles) {
  // Try to match by title similarity or content
  if (!frontmatter || !frontmatter.title) return null;

  // For now, we can't automatically detect - user needs to rename manually
  return null;
}

/**
 * Validate all content
 */
function validateContent(strict = false) {
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
          // Could be a localized filename or a true orphan
          if (isLocalizedFilename(file.filename, englishFiles)) {
            errors.push({
              rule: 'localized-filename',
              severity: 'error',
              file: relativeFile,
              message: `Localized filename "${file.filename}" should use English slug`,
              suggestion: `Rename to match English equivalent and update frontmatter`,
            });
          } else {
            warnings.push({
              rule: 'orphan-file',
              severity: 'warning',
              file: relativeFile,
              message: `File exists in ${lang} but not in English source`,
              suggestion: `Either create English version or remove this file`,
            });
          }
        }

        // Check frontmatter language field
        if (frontmatter) {
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
        }
      }
    }

    // Also validate English files for required fields
    for (const file of englishFiles) {
      const frontmatter = parseFrontmatter(file.fullPath);
      const relativeFile = `${collection}/${SOURCE_LANGUAGE}/${file.relativePath}`;

      if (frontmatter) {
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
  localized-filename     Filenames must use English slugs across all languages
  orphan-file            File exists in translation but not in English
  missing-required-field Required frontmatter fields must be present

Exclusions:
  - docs/en/cli/  (CLI API reference, English-only by design)
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

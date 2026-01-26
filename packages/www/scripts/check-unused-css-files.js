#!/usr/bin/env node
/**
 * Unused CSS Files Checker
 *
 * Detects CSS files that are not imported/referenced in source files.
 * Knip cannot detect unused CSS files, so this script fills that gap.
 *
 * Usage: node scripts/check-unused-css-files.js
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, '..');

// CSS directories to scan
const CSS_DIRS = [
  { dir: path.join(ROOT_DIR, 'public', 'styles'), type: 'public' },
  { dir: path.join(ROOT_DIR, 'src', 'styles'), type: 'src' },
];

// Source file patterns to search for imports
const SOURCE_EXTENSIONS = ['.astro', '.tsx', '.ts', '.js', '.html'];

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
 * Get all CSS files in a directory
 */
function getCssFiles(dir) {
  if (!fs.existsSync(dir)) {
    return [];
  }

  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.css'))
    .map((f) => ({
      name: f,
      fullPath: path.join(dir, f),
    }));
}

/**
 * Get all source files recursively
 */
function getSourceFiles(dir, files = []) {
  if (!fs.existsSync(dir)) {
    return files;
  }

  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);

    // Skip node_modules, dist, and hidden directories
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name.startsWith('.')) {
        continue;
      }
      // Skip content directory (markdown files)
      if (entry.name === 'content') {
        continue;
      }
      getSourceFiles(fullPath, files);
    } else if (SOURCE_EXTENSIONS.some((ext) => entry.name.endsWith(ext))) {
      files.push(fullPath);
    }
  }

  return files;
}

/**
 * Escape special regex characters
 */
function escapeRegex(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Check if a CSS file is imported/referenced in any source file
 */
function findCssUsage(cssFileName, cssType, sourceFiles) {
  // Patterns to search for:
  // - import './styles/foo.css'
  // - import '../styles/foo.css'
  // - href="/styles/foo.css"
  // - href="./styles/foo.css"
  // - @import 'foo.css'

  const escapedName = escapeRegex(cssFileName);

  const patterns = [
    // ES6 imports (relative paths)
    new RegExp(`import\\s+["'][^"']*${escapedName}["']`),
    // Link href (public CSS)
    new RegExp(`href=["'][^"']*${escapedName}["']`),
    // CSS @import
    new RegExp(`@import\\s+["'][^"']*${escapedName}["']`),
    // Dynamic imports
    new RegExp(`import\\([^)]*${escapedName}[^)]*\\)`),
  ];

  for (const filePath of sourceFiles) {
    const content = fs.readFileSync(filePath, 'utf-8');

    for (const pattern of patterns) {
      if (pattern.test(content)) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Main function
 */
function main() {
  console.log(colors.dim('Checking for unused CSS files...'));

  // Get all source files
  const sourceFiles = [
    ...getSourceFiles(path.join(ROOT_DIR, 'src')),
    ...getSourceFiles(path.join(ROOT_DIR, 'public')),
  ];

  console.log(colors.dim(`Scanning ${sourceFiles.length} source files for CSS imports...`));

  // Find unused CSS files
  const unusedFiles = [];

  for (const { dir, type } of CSS_DIRS) {
    const cssFiles = getCssFiles(dir);

    for (const cssFile of cssFiles) {
      if (!findCssUsage(cssFile.name, type, sourceFiles)) {
        unusedFiles.push({
          name: cssFile.name,
          fullPath: cssFile.fullPath,
          relativePath: path.relative(ROOT_DIR, cssFile.fullPath),
          type,
        });
      }
    }
  }

  // Report results
  console.log('\n' + colors.bold('='.repeat(60)));
  console.log(colors.bold('UNUSED CSS FILES REPORT'));
  console.log(colors.bold('='.repeat(60)) + '\n');

  if (unusedFiles.length === 0) {
    console.log(colors.green('All CSS files are imported/referenced.'));
    console.log(colors.bold('='.repeat(60)) + '\n');
    process.exit(0);
  }

  // Group by type
  const publicFiles = unusedFiles.filter((f) => f.type === 'public');
  const srcFiles = unusedFiles.filter((f) => f.type === 'src');

  if (publicFiles.length > 0) {
    console.log(colors.yellow('public/styles/:'));
    for (const file of publicFiles) {
      console.log(colors.red(`  ${file.name}`));
    }
    console.log('');
  }

  if (srcFiles.length > 0) {
    console.log(colors.yellow('src/styles/:'));
    for (const file of srcFiles) {
      console.log(colors.red(`  ${file.name}`));
    }
    console.log('');
  }

  console.log(colors.bold('='.repeat(60)));
  console.log(
    `${colors.red(`${unusedFiles.length} unused CSS file${unusedFiles.length === 1 ? '' : 's'}`)} found`
  );
  console.log(colors.dim('These CSS files are not imported or referenced in any source file.'));
  console.log(colors.dim('Consider removing them or adding imports if they are needed.'));
  console.log(colors.bold('='.repeat(60)) + '\n');

  process.exit(1);
}

main();

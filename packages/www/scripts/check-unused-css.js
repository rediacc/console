#!/usr/bin/env node
/**
 * Unused CSS Classes Checker
 *
 * Detects CSS class selectors that are not used in source files.
 * Knip cannot detect unused CSS classes, so this script fills that gap.
 *
 * Usage: node scripts/check-unused-css.js
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, '..');

// CSS directories to scan
const CSS_DIRS = [
  path.join(ROOT_DIR, 'public', 'styles'),
  path.join(ROOT_DIR, 'src', 'styles'),
];

// Source file patterns to search for class usage
const SOURCE_EXTENSIONS = ['.astro', '.tsx', '.ts', '.js'];

// Dynamic class patterns that are applied via JavaScript or conditionally
// These should be whitelisted as they may not appear literally in source
const DYNAMIC_CLASS_PATTERNS = [
  /^active$/, // navigation highlighting
  /^error$/, // form validation
  /^selected$/, // search results
  /^open$/, // sidebar state
  /^closed$/, // sidebar state
  /^fade-in$/, // animations
  /^fade-out$/, // animations
  /^loaded$/, // body state
  /^loading$/, // loading states
  /^visible$/, // visibility toggles
  /^hidden$/, // visibility toggles
  /^expanded$/, // accordion states
  /^collapsed$/, // accordion states
  /^toc-level-[2-6]$/, // dynamic TOC levels
  /^h[1-6]$/, // heading level classes
  /^no-js$/, // JavaScript detection
  /^js$/, // JavaScript detection
];

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
 * Extract CSS class selectors from a CSS file
 * Returns array of { className, line, file }
 */
function extractCssClasses(cssFilePath) {
  const content = fs.readFileSync(cssFilePath, 'utf-8');
  const lines = content.split('\n');
  const classes = [];

  // Match class selectors: .class-name
  // Handles: .class, .class:hover, .class::before, .parent .child, etc.
  const classRegex = /\.([a-zA-Z_-][a-zA-Z0-9_-]*)/g;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let match;

    // Skip lines that are comments
    if (line.trim().startsWith('/*') || line.trim().startsWith('*')) {
      continue;
    }

    while ((match = classRegex.exec(line)) !== null) {
      const className = match[1];

      // Skip CSS custom property references (var(--foo))
      if (line.includes(`var(--${className})`)) {
        continue;
      }

      classes.push({
        className,
        line: i + 1,
        file: cssFilePath,
      });
    }
  }

  return classes;
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
 * Check if a class name matches any dynamic pattern
 */
function isDynamicClass(className) {
  return DYNAMIC_CLASS_PATTERNS.some((pattern) => pattern.test(className));
}

/**
 * Search for class usage in source files
 */
function findClassUsage(className, sourceFiles) {
  // Patterns to search for:
  // - class="foo" or class='foo'
  // - className="foo" or className='foo'
  // - className={`foo`} or className={"foo"}
  // - "foo" or 'foo' in template literals
  // - classList.add('foo'), classList.toggle('foo'), etc.

  const patterns = [
    // HTML/JSX class attributes
    new RegExp(`class(?:Name)?=["'\`][^"'\`]*\\b${escapeRegex(className)}\\b[^"'\`]*["'\`]`),
    // Template literals and string concatenation
    new RegExp(`["'\`]${escapeRegex(className)}["'\`]`),
    // classList methods
    new RegExp(`classList\\.(add|remove|toggle|contains)\\([^)]*["'\`]${escapeRegex(className)}["'\`]`),
    // Direct string references (for dynamic classes)
    new RegExp(`\\b${escapeRegex(className)}\\b`),
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
 * Escape special regex characters
 */
function escapeRegex(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Main function
 */
function main() {
  console.log(colors.dim('Checking for unused CSS classes...'));
  console.log(colors.dim(`CSS directories: ${CSS_DIRS.map((d) => path.relative(ROOT_DIR, d)).join(', ')}`));

  // Collect all CSS classes
  const allClasses = [];
  for (const cssDir of CSS_DIRS) {
    if (!fs.existsSync(cssDir)) {
      continue;
    }

    const cssFiles = fs.readdirSync(cssDir).filter((f) => f.endsWith('.css'));

    for (const cssFile of cssFiles) {
      const cssFilePath = path.join(cssDir, cssFile);
      const classes = extractCssClasses(cssFilePath);
      allClasses.push(...classes);
    }
  }

  // Deduplicate classes (same class might appear multiple times)
  const uniqueClasses = new Map();
  for (const cls of allClasses) {
    const key = cls.className;
    if (!uniqueClasses.has(key)) {
      uniqueClasses.set(key, cls);
    }
  }

  console.log(colors.dim(`Found ${uniqueClasses.size} unique CSS classes`));

  // Get all source files
  const sourceFiles = [
    ...getSourceFiles(path.join(ROOT_DIR, 'src')),
    ...getSourceFiles(path.join(ROOT_DIR, 'public', 'scripts')),
  ];

  console.log(colors.dim(`Scanning ${sourceFiles.length} source files for usage...`));

  // Find unused classes
  const unusedClasses = [];
  for (const [className, cls] of uniqueClasses) {
    // Skip dynamic classes
    if (isDynamicClass(className)) {
      continue;
    }

    // Check if class is used
    if (!findClassUsage(className, sourceFiles)) {
      unusedClasses.push(cls);
    }
  }

  // Report results
  console.log('\n' + colors.bold('='.repeat(60)));
  console.log(colors.bold('UNUSED CSS CLASSES REPORT'));
  console.log(colors.bold('='.repeat(60)) + '\n');

  if (unusedClasses.length === 0) {
    console.log(colors.green('No unused CSS classes detected.'));
    console.log(colors.bold('='.repeat(60)) + '\n');
    process.exit(0);
  }

  // Group by file
  const byFile = {};
  for (const cls of unusedClasses) {
    const relativePath = path.relative(ROOT_DIR, cls.file);
    if (!byFile[relativePath]) {
      byFile[relativePath] = [];
    }
    byFile[relativePath].push(cls);
  }

  for (const [file, classes] of Object.entries(byFile)) {
    console.log(colors.red(`${file}:`));
    for (const cls of classes) {
      console.log(colors.dim(`  Line ${cls.line}: `) + colors.yellow(`.${cls.className}`));
    }
    console.log('');
  }

  console.log(colors.bold('='.repeat(60)));
  console.log(`${colors.red(`${unusedClasses.length} unused CSS class${unusedClasses.length === 1 ? '' : 'es'}`)} found`);
  console.log(colors.dim('Note: Some classes may be used dynamically and are whitelisted.'));
  console.log(colors.dim('Edit DYNAMIC_CLASS_PATTERNS in this script to add more patterns.'));
  console.log(colors.bold('='.repeat(60)) + '\n');

  process.exit(1);
}

main();

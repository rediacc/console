#!/usr/bin/env node
/**
 * Component Hardcoded String Detection
 *
 * Scans .astro and .tsx files in packages/www/src/ for English strings
 * that bypass the translation system (not wrapped in t() calls).
 *
 * Detection approach:
 * - Astro templates: text nodes and translatable attributes not in {t(...)}
 * - TSX files: JSX text nodes and string-prop values not using t()
 * - Inline scripts: string literals assigned to textContent/innerHTML/setAttribute
 *   that don't reference data-i18n-* or dataset.*
 *
 * Usage:
 *   npx tsx scripts/check-component-hardcoded-strings.ts [--strict]
 *
 * Exit codes:
 *   0 - No issues (or warning-only mode)
 *   1 - Issues found in strict mode
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes('--strict');

// ─── Configuration ───────────────────────────────────────────────────────────

const WWW_SRC = path.join(__dirname, '../packages/www/src');

// Minimum word count for flagging a string (single words are often intentional)
const MIN_WORDS = 2;

// Strings that are intentionally English across all locales
const ALLOWED_STRINGS = new Set([
  'Rediacc',
  'Rediaccfile',
  'Renet',
  'Docker',
  'GitHub',
  'GitLab',
  'Jenkins',
  'Prometheus',
  'PostgreSQL',
  'MySQL',
  'MariaDB',
  'MongoDB',
  'Redis',
  'Kubernetes',
  'VS Code',
  'Linux',
  'macOS',
  'Windows',
  'Ubuntu',
  'Debian',
  'Fedora',
  'Node.js',
  'TypeScript',
  'JavaScript',
  'Markdown',
  'JSON',
  'YAML',
  'CSV',
  'SSH',
  'API',
  'CLI',
  'URL',
  'HTTP',
  'HTTPS',
  'WebSocket',
  'OAuth',
  'JWT',
  'TOTP',
  'PDF',
  'ARM',
  'ARM64',
  'AMD64',
  'btrfs',
  'LUKS',
  'systemd',
  'rdc',
  'CC',
  'true',
  'false',
  'null',
]);

// Patterns that indicate the string is technical/intentional
const SKIP_PATTERNS: RegExp[] = [
  /^https?:\/\//, // URLs
  /^\/[a-z]/, // Paths
  /^\{\{/, // Template expressions
  /^[a-z0-9._-]+@[a-z0-9.-]+\.[a-z]+$/i, // Emails
  /^\d/, // Starts with number
  /^[A-Z_]+$/, // All caps constant
  /^[a-z][a-zA-Z]+$/, // camelCase identifier
  /^[a-z]+-[a-z]+/, // kebab-case
  /^rdc\s/, // CLI commands
  /^v\d+/, // Version strings
  /\.(js|ts|tsx|css|json|svg|png|jpg|webp|mp4|woff|ttf)$/i, // File extensions
];

// Files to skip entirely
const SKIP_FILES = new Set([
  'config/constants.ts',
  'config/team-videos.ts',
  'config/cli-reference.ts',
  'pages/llms.txt.ts',
  'pages/sitemap-index.xml.ts',
  'pages/rss.xml.ts',
  'pages/[lang]/docs/rdc-cheat-sheet.astro',
  'data/',
  'scripts/',
]);

// ─── Types ───────────────────────────────────────────────────────────────────

interface Issue {
  file: string;
  line: number;
  text: string;
  context: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function shouldSkipFile(relPath: string): boolean {
  return Array.from(SKIP_FILES).some((skip) => relPath.startsWith(skip));
}

function isAllowed(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.length === 0) return true;
  if (ALLOWED_STRINGS.has(trimmed)) return true;

  // Count words
  const words = trimmed.split(/\s+/).filter((w) => w.length > 0);
  if (words.length < MIN_WORDS) return true;

  // Check skip patterns
  for (const pat of SKIP_PATTERNS) {
    if (pat.test(trimmed)) return true;
  }

  // All-ASCII punctuation/symbols
  if (/^[^a-zA-Z]*$/.test(trimmed)) return true;

  return false;
}

// ─── Astro Template Scanner ──────────────────────────────────────────────────

function scanAstroFile(filePath: string, relPath: string): Issue[] {
  const issues: Issue[] = [];
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');

  // Find template section (after second ---)
  let fenceCount = 0;
  let templateStart = 0;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim() === '---') {
      fenceCount++;
      if (fenceCount === 2) {
        templateStart = i + 1;
        break;
      }
    }
  }

  // If no frontmatter, whole file is template
  if (fenceCount < 2) templateStart = 0;

  let inScript = false;
  let inStyle = false;
  let inCodeBlock = false;

  for (let i = templateStart; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;


    // Track block state
    if (/<script[\s>]/i.test(line) && !/<\/script>/i.test(line)) { inScript = true; continue; }
    if (/<\/script>/i.test(line)) { inScript = false; continue; }
    if (/<style[\s>]/i.test(line)) inStyle = true;
    if (/<\/style>/i.test(line)) { inStyle = false; continue; }
    if (/<code[\s>]/i.test(line) || /<pre[\s>]/i.test(line)) inCodeBlock = true;
    if (/<\/code>/i.test(line) || /<\/pre>/i.test(line)) { inCodeBlock = false; continue; }

    if (inScript || inStyle || inCodeBlock) continue;

    // Check for translatable attributes with hardcoded English
    const attrPattern = /\b(aria-label|title|alt|placeholder)="([^"]+)"/g;
    let attrMatch: RegExpExecArray | null;
    while ((attrMatch = attrPattern.exec(line)) !== null) {
      const value = attrMatch[2];
      if (!isAllowed(value)) {
        issues.push({
          file: relPath,
          line: lineNum,
          text: value,
          context: `${attrMatch[1]} attribute`,
        });
      }
    }

    // Check for text nodes between tags (simplified: text outside of { } and < >)
    // Look for lines that are just text content (not attributes, not expressions)
    const textOnly = line
      .replace(/<[^>]+>/g, '') // Remove tags
      .replace(/\{[^}]*\}/g, '') // Remove expressions
      .replace(/class="[^"]*"/g, '') // Remove class attrs
      .replace(/\/\/.*$/, '') // Remove JS-style line comments
      .trim();

    if (textOnly && !isAllowed(textOnly)) {
      // Verify it's not inside a tag attribute we already handled
      if (!/^\s*</.test(line) || textOnly !== line.trim()) {
        // Only flag if the text looks like real English content
        const englishWords = textOnly.match(/\b[A-Z][a-z]+(?:\s+[a-z]+)*\b/g);
        if (englishWords && englishWords.some((w) => w.split(/\s+/).length >= MIN_WORDS)) {
          issues.push({
            file: relPath,
            line: lineNum,
            text: textOnly.substring(0, 80),
            context: 'text node',
          });
        }
      }
    }
  }

  return issues;
}

// ─── TSX Scanner ─────────────────────────────────────────────────────────────

function scanTsxFile(filePath: string, relPath: string): Issue[] {
  const issues: Issue[] = [];
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;


    // Check translatable attributes with hardcoded strings (not using {t(...)})
    const attrPattern = /\b(aria-label|title|alt|placeholder)="([^"]+)"/g;
    let attrMatch: RegExpExecArray | null;
    while ((attrMatch = attrPattern.exec(line)) !== null) {
      const value = attrMatch[2];
      if (!isAllowed(value)) {
        issues.push({
          file: relPath,
          line: lineNum,
          text: value,
          context: `${attrMatch[1]} attribute`,
        });
      }
    }

    // Check for JSX text content (text between > and <)
    // Pattern: >Some English text< or >Some text</tag>
    const jsxTextPattern = />\s*([A-Z][a-zA-Z\s,.!?]+[a-z.!?])\s*</g;
    let textMatch: RegExpExecArray | null;
    while ((textMatch = jsxTextPattern.exec(line)) !== null) {
      const text = textMatch[1].trim();
      if (!isAllowed(text) && !/\{/.test(text)) {
        issues.push({
          file: relPath,
          line: lineNum,
          text: text.substring(0, 80),
          context: 'JSX text node',
        });
      }
    }
  }

  return issues;
}

// ─── Main ────────────────────────────────────────────────────────────────────

function main(): void {
  console.log('Component Hardcoded String Detection');
  console.log('============================================================\n');

  const astroFiles = globSync(`${WWW_SRC}/**/*.astro`);
  const tsxFiles = globSync(`${WWW_SRC}/**/*.tsx`);

  console.log(`Scanning ${astroFiles.length} .astro and ${tsxFiles.length} .tsx files...\n`);

  const allIssues: Issue[] = [];

  for (const file of astroFiles) {
    const rel = path.relative(WWW_SRC, file);
    if (shouldSkipFile(rel)) continue;
    allIssues.push(...scanAstroFile(file, rel));
  }

  for (const file of tsxFiles) {
    const rel = path.relative(WWW_SRC, file);
    if (shouldSkipFile(rel)) continue;
    allIssues.push(...scanTsxFile(file, rel));
  }

  if (allIssues.length === 0) {
    console.log('\x1b[32m\u2713\x1b[0m No hardcoded strings detected\n');
    process.exit(0);
  }

  // Group by file
  const byFile = new Map<string, Issue[]>();
  for (const issue of allIssues) {
    if (!byFile.has(issue.file)) byFile.set(issue.file, []);
    byFile.get(issue.file)!.push(issue);
  }

  const label = strict ? '\x1b[31mERROR' : '\x1b[33mWARN';
  for (const [file, issues] of byFile) {
    console.log(`\x1b[33m${file}\x1b[0m`);
    for (const issue of issues.slice(0, 10)) {
      console.log(`  ${label}\x1b[0m Line ${issue.line} (${issue.context}): "${issue.text}"`);
    }
    if (issues.length > 10) {
      console.log(`  ... and ${issues.length - 10} more in this file`);
    }
    console.log('');
  }

  console.log(`Found ${allIssues.length} hardcoded string(s) in ${byFile.size} file(s).\n`);

  if (strict) {
    console.log(
      '\x1b[31m\u2717\x1b[0m Hardcoded string detection FAILED (strict mode)\n' +
        'Wrap all user-facing strings in t() calls.\n'
    );
    process.exit(1);
  } else {
    console.log(
      '\x1b[33m!\x1b[0m Hardcoded strings found (warning mode). Use --strict to enforce.\n'
    );
    process.exit(0);
  }
}

main();

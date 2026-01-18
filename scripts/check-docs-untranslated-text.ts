#!/usr/bin/env node
/**
 * Untranslated Text Detection for Documentation
 *
 * Detects English text that was copy-pasted into non-English documentation files
 * without proper translation. This is a quality check to ensure all documentation
 * is properly localized.
 *
 * Detection patterns:
 * 1. Common English sentence starters: "Enter the", "Click the", "Select the", etc.
 * 2. Common English action words in instruction context
 * 3. Lines that should be translated but contain only ASCII/English words
 *
 * Usage:
 *   npx tsx scripts/check-docs-untranslated-text.ts
 *
 * Exit codes:
 *   0 - No untranslated text found
 *   1 - Untranslated text detected (blocking)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration
const DOCS_DIR = path.join(__dirname, '../packages/www/src/content/docs');

// Languages to check (excluding English)
const NON_ENGLISH_LANGS = ['ar', 'de', 'es', 'fr', 'ja', 'ru', 'tr', 'zh'] as const;

/**
 * Common English sentence patterns that indicate untranslated text.
 * These are instructional phrases commonly found in documentation.
 */
const ENGLISH_PATTERNS = [
  // Imperative sentences (instructions)
  /^[0-9]+\.\s+(Enter|Click|Select|Follow|Watch|See|Review|Check|Find|Use|Open|Close|Add|Remove|Create|Delete|Edit|Update|Save|Cancel|Confirm|Submit|Choose|Pick|Navigate|Go to|Access|View|Show|Hide|Enable|Disable|Toggle|Expand|Collapse|Scroll|Drag|Drop|Copy|Paste|Cut|Move|Resize|Refresh|Reload|Download|Upload|Import|Export|Install|Uninstall|Configure|Setup|Set up|Start|Stop|Pause|Resume|Run|Execute|Apply|Reset|Clear|Fill|Complete|Finish|Begin|Continue|Proceed|Return|Back|Next|Previous|Skip|Retry|Repeat|Undo|Redo)\s+the\b/i,

  // Common instruction patterns
  /\b(Click|Select|Enter|Choose|Pick|Use|Find|See|Watch|Review|Check)\s+the\s+\*\*/i,
  /\*\*\s*(button|option|field|menu|tab|link|icon|checkbox|dropdown|list|panel|section|window|dialog|modal|form|input|text|label|value|setting|configuration)\b/i,

  // Instruction endings
  /\b(button|option|field|section|window|dialog|form|panel|tab|menu)\s*\.$/i,
  /\b(if applicable|if needed|if necessary|as needed|when prompted|when required)\s*[.)]/i,

  // Common English phrases in documentation
  /\b(e\.g\.,|for example,|such as|including|note:|tip:|warning:|important:)\s/i,
  /\bthe following\b/i,
  /\bmake sure\b/i,
  /\byou can\b/i,
  /\byou will\b/i,
  /\byou should\b/i,
  /\bthis will\b/i,
  /\bthis is\b/i,
  /\bto (create|add|remove|delete|edit|update|view|access|open|close|enable|disable)\b/i,

  // Field/form instructions
  /\bin the\s+\*\*.*\*\*\s+(field|section|area|box|input)\b/i,
  /\bfrom the\s+\*\*.*\*\*\s+(menu|dropdown|list|options)\b/i,
];

/**
 * Lines that should be skipped (not checked for English text).
 * These include code blocks, frontmatter, image references, etc.
 */
const SKIP_PATTERNS = [
  /^---$/,                          // Frontmatter delimiter
  /^```/,                           // Code block
  /^>\s*\*\*/,                      // Blockquote with bold (often tips in English format)
  /^!\[/,                           // Image reference
  /^\*\(/,                          // Figure caption start
  /^#+\s/,                          // Headers (may intentionally be in English)
  /^\s*[-*]\s*\*\*{{t:/,           // List items with only translation keys
  /^[0-9]+\.\s+\*\*{{t:/,          // Numbered items with only translation keys
  /^\s*$/,                          // Empty lines
  /^\|/,                            // Table rows
  /^<!--/,                          // HTML comments
];

/**
 * Words/patterns that are acceptable in any language (technical terms, etc.)
 */
const ALLOWED_ENGLISH = [
  /\{\{t:[^}]+\}\}/,               // Translation keys
  /\*\*{{t:[^}]+}}\*\*/,           // Bold translation keys
  /`[^`]+`/,                        // Inline code
  /\b(JSON|CSV|API|URL|SSH|HTTP|HTTPS|SQL|HTML|CSS|JS|TS|UUID|ID|IP|DNS|TLS|SSL|VPN|VM|OS|CPU|RAM|GB|MB|KB|TB|GHz|MHz)\b/i,  // Technical acronyms
  /\b(docker|git|npm|node|bash|linux|windows|macos)\b/i,  // Technical product names
  /\b(setup|backup|deploy|fork|unmount|checkpoint)\b/i,   // Function names that might appear
  /\b(fx)\b/,                       // UI element names
  /\b(postgresql|mysql|mongodb|redis)\b/i,  // Database names
  /\d{4}-\d{2}-\d{2}/,             // Dates
  /\b\d+\s*(GB|MB|KB|TB)\b/i,      // Size values
];

interface UntranslatedLine {
  file: string;
  lang: string;
  lineNumber: number;
  content: string;
  pattern: string;
}

/**
 * Check if a line should be skipped from analysis
 */
function shouldSkipLine(line: string): boolean {
  return SKIP_PATTERNS.some((pattern) => pattern.test(line));
}

/**
 * Remove allowed English patterns from line for analysis
 */
function removeAllowedEnglish(line: string): string {
  let result = line;
  for (const pattern of ALLOWED_ENGLISH) {
    result = result.replace(new RegExp(pattern, 'gi'), ' ');
  }
  return result;
}

/**
 * Check if a line contains untranslated English text
 */
function detectUntranslatedText(line: string): string | null {
  if (shouldSkipLine(line)) {
    return null;
  }

  // Remove allowed English before checking
  const cleanedLine = removeAllowedEnglish(line);

  for (const pattern of ENGLISH_PATTERNS) {
    if (pattern.test(cleanedLine)) {
      return pattern.source.slice(0, 50) + '...';
    }
  }

  return null;
}

/**
 * Analyze a single documentation file for untranslated text
 */
function analyzeFile(filePath: string, lang: string): UntranslatedLine[] {
  const issues: UntranslatedLine[] = [];
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');

  let inCodeBlock = false;
  let inFrontmatter = false;
  let frontmatterCount = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNumber = i + 1;

    // Track frontmatter
    if (line === '---') {
      frontmatterCount++;
      if (frontmatterCount === 1) {
        inFrontmatter = true;
        continue;
      } else if (frontmatterCount === 2) {
        inFrontmatter = false;
        continue;
      }
    }

    if (inFrontmatter) {
      continue;
    }

    // Track code blocks
    if (line.startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      continue;
    }

    if (inCodeBlock) {
      continue;
    }

    const pattern = detectUntranslatedText(line);
    if (pattern) {
      issues.push({
        file: filePath,
        lang,
        lineNumber,
        content: line.trim().slice(0, 100) + (line.length > 100 ? '...' : ''),
        pattern,
      });
    }
  }

  return issues;
}

/**
 * Main validation function
 */
function main(): void {
  console.log('Untranslated Text Detection');
  console.log('============================================================\n');

  // Check if docs directory exists
  if (!fs.existsSync(DOCS_DIR)) {
    console.log('\x1b[33m!\x1b[0m Docs directory not found, skipping untranslated text check');
    process.exit(0);
  }

  const allIssues: UntranslatedLine[] = [];
  const issuesByLang = new Map<string, number>();

  console.log('Checking non-English documentation for untranslated text...\n');

  for (const lang of NON_ENGLISH_LANGS) {
    const langDir = path.join(DOCS_DIR, lang);
    if (!fs.existsSync(langDir)) {
      console.log(`  \x1b[33m!\x1b[0m ${lang}: Directory not found, skipping`);
      continue;
    }

    const mdFiles = globSync(`${langDir}/**/*.md`);
    let langIssues = 0;

    for (const file of mdFiles) {
      const issues = analyzeFile(file, lang);
      allIssues.push(...issues);
      langIssues += issues.length;
    }

    issuesByLang.set(lang, langIssues);

    if (langIssues > 0) {
      console.log(`  \x1b[31m✗\x1b[0m ${lang}: ${langIssues} untranslated line(s) found`);
    } else {
      console.log(`  \x1b[32m✓\x1b[0m ${lang}: No untranslated text detected`);
    }
  }

  console.log('');

  if (allIssues.length > 0) {
    console.log('\x1b[31mUntranslated Text Found:\x1b[0m\n');

    // Group by file
    const byFile = new Map<string, UntranslatedLine[]>();
    for (const issue of allIssues) {
      const relPath = path.relative(DOCS_DIR, issue.file);
      if (!byFile.has(relPath)) {
        byFile.set(relPath, []);
      }
      byFile.get(relPath)!.push(issue);
    }

    // Show first few issues per file
    let shown = 0;
    const maxToShow = 30;

    for (const [file, issues] of byFile) {
      if (shown >= maxToShow) break;

      console.log(`  \x1b[33m${file}\x1b[0m`);
      for (const issue of issues.slice(0, 5)) {
        if (shown >= maxToShow) break;
        console.log(`    Line ${issue.lineNumber}: ${issue.content}`);
        shown++;
      }
      if (issues.length > 5) {
        console.log(`    ... and ${issues.length - 5} more in this file`);
      }
      console.log('');
    }

    if (allIssues.length > maxToShow) {
      console.log(`  ... and ${allIssues.length - maxToShow} more issues\n`);
    }

    console.log(
      '\x1b[31m✗\x1b[0m Untranslated text detection FAILED\n' +
        `Found ${allIssues.length} line(s) with English text in non-English documentation.\n\n` +
        'To fix:\n' +
        '  1. Translate the English text to the appropriate language\n' +
        '  2. Or use translation keys {{t:namespace.key}} for UI labels\n' +
        '  3. Technical terms and code can remain in English\n'
    );
    process.exit(1);
  }

  console.log(
    '\x1b[32m✓\x1b[0m All non-English documentation appears to be properly translated\n'
  );
  process.exit(0);
}

main();

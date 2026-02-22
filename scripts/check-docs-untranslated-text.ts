#!/usr/bin/env node
/**
 * Untranslated Text Detection for Documentation
 *
 * Two detection layers:
 * 1. Pattern matching: detects common English instruction phrases
 * 2. Native character analysis: verifies non-English files contain characters
 *    from their expected script (Arabic, Cyrillic, CJK, etc.) and that
 *    Latin-script languages contain their distinctive diacritics
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

// =============================================================================
// PATTERN-BASED DETECTION (Layer 1)
// =============================================================================

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

// =============================================================================
// NATIVE CHARACTER ANALYSIS (Layer 2)
// =============================================================================

type ScriptType = 'non-latin' | 'latin';

interface LocaleCharConfig {
  scriptType: ScriptType;
  scriptName: string;
  nativeCharPattern: RegExp;
}

/**
 * Per-locale native character definitions.
 *
 * Non-Latin scripts: characters that MUST appear if the text is translated.
 * Latin scripts: diacritics/special chars distinctive to that language.
 */
const LOCALE_CHAR_CONFIG: Record<string, LocaleCharConfig> = {
  ar: {
    scriptType: 'non-latin',
    scriptName: 'Arabic',
    nativeCharPattern: /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/,
  },
  ja: {
    scriptType: 'non-latin',
    scriptName: 'Japanese',
    nativeCharPattern: /[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF]/,
  },
  ru: {
    scriptType: 'non-latin',
    scriptName: 'Cyrillic',
    nativeCharPattern: /[\u0400-\u04FF]/,
  },
  zh: {
    scriptType: 'non-latin',
    scriptName: 'Chinese',
    nativeCharPattern: /[\u4E00-\u9FFF\u3400-\u4DBF]/,
  },
  de: {
    scriptType: 'latin',
    scriptName: 'German',
    // äöüÄÖÜß
    nativeCharPattern: /[\u00E4\u00F6\u00FC\u00C4\u00D6\u00DC\u00DF]/,
  },
  es: {
    scriptType: 'latin',
    scriptName: 'Spanish',
    // ñáéíóúÑÁÉÍÓÚ¿¡
    nativeCharPattern: /[\u00F1\u00D1\u00E1\u00E9\u00ED\u00F3\u00FA\u00C1\u00C9\u00CD\u00D3\u00DA\u00BF\u00A1]/,
  },
  fr: {
    scriptType: 'latin',
    scriptName: 'French',
    // éèêëçàâùûôîïÉÈÊËÇÀÂÙÛÔÎÏ
    nativeCharPattern: /[\u00E9\u00E8\u00EA\u00EB\u00E7\u00E0\u00E2\u00F9\u00FB\u00F4\u00EE\u00EF\u00C9\u00C8\u00CA\u00CB\u00C7\u00C0\u00C2\u00D9\u00DB\u00D4\u00CE\u00CF]/,
  },
  tr: {
    scriptType: 'latin',
    scriptName: 'Turkish',
    // ğĞıİşŞçÇöÖüÜ
    nativeCharPattern: /[\u011E\u011F\u0130\u0131\u015E\u015F\u00E7\u00C7\u00F6\u00D6\u00FC\u00DC]/,
  },
};

// Thresholds for native character analysis
const NON_LATIN_MIN_BODY_CHARS = 200;
const NON_LATIN_MIN_NATIVE_PCT = 5;
const LATIN_MIN_BODY_CHARS = 500;
const FRONTMATTER_MIN_LENGTH = 50;

// =============================================================================
// TYPES
// =============================================================================

interface UntranslatedLine {
  file: string;
  lang: string;
  lineNumber: number;
  content: string;
  pattern: string;
}

interface NativeCharIssue {
  file: string;
  lang: string;
  kind: 'body-no-native' | 'body-low-native' | 'frontmatter-no-native';
  message: string;
}

// =============================================================================
// PATTERN-BASED DETECTION FUNCTIONS
// =============================================================================

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
 * Analyze a single documentation file for untranslated text (pattern matching)
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

// =============================================================================
// NATIVE CHARACTER ANALYSIS FUNCTIONS
// =============================================================================

/**
 * Extract prose text and frontmatter fields from a markdown file.
 * Excludes code blocks, inline code, image refs, table rows, HTML comments,
 * and markdown syntax (heading/list/blockquote markers, bold/italic).
 */
function extractTextParts(content: string): {
  bodyText: string;
  frontmatterTitle: string;
  frontmatterDescription: string;
  isTranslationPending: boolean;
  isGenerated: boolean;
} {
  const lines = content.split('\n');
  const bodyLines: string[] = [];
  let inCodeBlock = false;
  let inFrontmatter = false;
  let frontmatterCount = 0;
  let frontmatterTitle = '';
  let frontmatterDescription = '';
  let isTranslationPending = false;
  let isGenerated = false;
  let collectingDescription = false;

  for (const line of lines) {
    if (line === '---') {
      frontmatterCount++;
      if (frontmatterCount === 1) {
        inFrontmatter = true;
        continue;
      } else if (frontmatterCount === 2) {
        inFrontmatter = false;
        collectingDescription = false;
        continue;
      }
    }

    if (inFrontmatter) {
      // Parse title (single-line)
      const titleMatch = line.match(/^title:\s*["']?(.+?)["']?\s*$/);
      if (titleMatch) {
        frontmatterTitle = titleMatch[1];
        collectingDescription = false;
        continue;
      }
      // Parse description (single-line)
      const descMatch = line.match(/^description:\s*["'](.+?)["']\s*$/);
      if (descMatch) {
        frontmatterDescription = descMatch[1];
        collectingDescription = false;
        continue;
      }
      // Parse description (multi-line YAML: >- or |)
      const descStartMatch = line.match(/^description:\s*[>|]-?\s*$/);
      if (descStartMatch) {
        collectingDescription = true;
        frontmatterDescription = '';
        continue;
      }
      // Parse description (single-line without quotes)
      const descPlainMatch = line.match(/^description:\s+(.+)$/);
      if (descPlainMatch && !descPlainMatch[1].startsWith('>') && !descPlainMatch[1].startsWith('|')) {
        frontmatterDescription = descPlainMatch[1].replace(/^["']|["']$/g, '');
        collectingDescription = false;
        continue;
      }
      if (collectingDescription) {
        if (/^\s+\S/.test(line)) {
          frontmatterDescription += ' ' + line.trim();
        } else {
          collectingDescription = false;
        }
      }
      if (/^translationPending:\s*true/.test(line)) {
        isTranslationPending = true;
      }
      if (/^generated:\s*true/.test(line)) {
        isGenerated = true;
      }
      continue;
    }

    // Track code blocks
    if (line.startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) continue;

    // Skip non-prose lines
    if (/^\s*$/.test(line)) continue;
    if (/^<!--/.test(line)) continue;
    if (/^!\[/.test(line)) continue;
    if (/^\|/.test(line)) continue;

    // Clean markdown syntax, keep only prose text
    let cleaned = line;
    cleaned = cleaned.replace(/`[^`]+`/g, '');                    // Remove inline code
    cleaned = cleaned.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1');   // [text](url) -> text
    cleaned = cleaned.replace(/^#+\s*/, '');                      // Remove heading markers
    cleaned = cleaned.replace(/^\s*[-*+]\s+/, '');                // Remove list markers
    cleaned = cleaned.replace(/^\s*\d+\.\s+/, '');               // Remove numbered list markers
    cleaned = cleaned.replace(/^>\s*/, '');                       // Remove blockquote markers
    cleaned = cleaned.replace(/\*\*([^*]*)\*\*/g, '$1');         // Remove bold markers
    cleaned = cleaned.replace(/\*([^*]*)\*/g, '$1');             // Remove italic markers
    cleaned = cleaned.trim();

    if (cleaned.length > 0) {
      bodyLines.push(cleaned);
    }
  }

  return {
    bodyText: bodyLines.join(' '),
    frontmatterTitle: frontmatterTitle.trim(),
    frontmatterDescription: frontmatterDescription.trim(),
    isTranslationPending,
    isGenerated,
  };
}

/**
 * Count characters matching the native character pattern in a string.
 */
function countNativeChars(text: string, pattern: RegExp): number {
  const globalPattern = new RegExp(pattern.source, 'gu');
  const matches = text.match(globalPattern);
  return matches ? matches.length : 0;
}

/**
 * Analyze a file for native character presence.
 */
function analyzeNativeChars(filePath: string, lang: string): NativeCharIssue[] {
  const config = LOCALE_CHAR_CONFIG[lang];
  if (!config) return [];

  const content = fs.readFileSync(filePath, 'utf-8');
  const { bodyText, frontmatterTitle, frontmatterDescription, isTranslationPending, isGenerated } =
    extractTextParts(content);

  // Skip files marked as translation pending or auto-generated ({{t:key}} content)
  if (isTranslationPending || isGenerated) return [];

  const issues: NativeCharIssue[] = [];
  const bodyChars = bodyText.length;
  const nativeChars = countNativeChars(bodyText, config.nativeCharPattern);
  const nativePercent = bodyChars > 0 ? (nativeChars / bodyChars) * 100 : 0;

  // Body text check
  if (config.scriptType === 'non-latin') {
    if (bodyChars >= NON_LATIN_MIN_BODY_CHARS) {
      if (nativeChars === 0) {
        issues.push({
          file: filePath,
          lang,
          kind: 'body-no-native',
          message: `0 ${config.scriptName} characters in ${bodyChars} body chars (file appears completely untranslated)`,
        });
      } else if (nativePercent < NON_LATIN_MIN_NATIVE_PCT) {
        issues.push({
          file: filePath,
          lang,
          kind: 'body-low-native',
          message: `Only ${nativePercent.toFixed(1)}% ${config.scriptName} characters in ${bodyChars} body chars (expected >=${NON_LATIN_MIN_NATIVE_PCT}%)`,
        });
      }
    }
  } else {
    if (bodyChars >= LATIN_MIN_BODY_CHARS && nativeChars === 0) {
      issues.push({
        file: filePath,
        lang,
        kind: 'body-no-native',
        message: `0 ${config.scriptName} diacritics in ${bodyChars} body chars (file may be untranslated or diacritics stripped)`,
      });
    }
  }

  // Frontmatter check (title + description)
  // For Latin scripts this is a warning only — languages like German can
  // legitimately have long technical descriptions without diacritics.
  const fmText = `${frontmatterTitle} ${frontmatterDescription}`.trim();
  if (fmText.length >= FRONTMATTER_MIN_LENGTH) {
    const fmNative = countNativeChars(fmText, config.nativeCharPattern);
    if (fmNative === 0) {
      const charType = config.scriptType === 'non-latin' ? 'characters' : 'diacritics';
      issues.push({
        file: filePath,
        lang,
        kind: 'frontmatter-no-native',
        message: `Frontmatter (title+description) has 0 ${config.scriptName} ${charType} in ${fmText.length} chars`,
      });
    }
  }

  return issues;
}

// =============================================================================
// MAIN
// =============================================================================

function main(): void {
  console.log('Untranslated Text Detection');
  console.log('============================================================\n');

  if (!fs.existsSync(DOCS_DIR)) {
    console.log('\x1b[33m!\x1b[0m Docs directory not found, skipping untranslated text check');
    process.exit(0);
  }

  const allIssues: UntranslatedLine[] = [];
  const allNativeIssues: NativeCharIssue[] = [];

  console.log('Checking non-English documentation for untranslated text...\n');

  for (const lang of NON_ENGLISH_LANGS) {
    const langDir = path.join(DOCS_DIR, lang);
    if (!fs.existsSync(langDir)) {
      console.log(`  \x1b[33m!\x1b[0m ${lang}: Directory not found, skipping`);
      continue;
    }

    const mdFiles = globSync(`${langDir}/**/*.md`);
    let langPatternIssues = 0;

    for (const file of mdFiles) {
      const patternIssues = analyzeFile(file, lang);
      allIssues.push(...patternIssues);
      langPatternIssues += patternIssues.length;

      const nativeIssues = analyzeNativeChars(file, lang);
      allNativeIssues.push(...nativeIssues);
    }

    const langNativeErrors = allNativeIssues.filter((i) => i.lang === lang).length;
    const totalErrors = langPatternIssues + langNativeErrors;

    if (totalErrors > 0) {
      const parts: string[] = [];
      if (langPatternIssues > 0) parts.push(`${langPatternIssues} pattern match(es)`);
      if (langNativeErrors > 0) parts.push(`${langNativeErrors} native char error(s)`);
      console.log(`  \x1b[31m\u2717\x1b[0m ${lang}: ${parts.join(', ')}`);
    } else {
      console.log(`  \x1b[32m\u2713\x1b[0m ${lang}: No untranslated text detected`);
    }
  }

  console.log('');

  // Pattern-based report
  if (allIssues.length > 0) {
    console.log('\x1b[31mUntranslated Text Found (Pattern Matching):\x1b[0m\n');

    const byFile = new Map<string, UntranslatedLine[]>();
    for (const issue of allIssues) {
      const relPath = path.relative(DOCS_DIR, issue.file);
      if (!byFile.has(relPath)) {
        byFile.set(relPath, []);
      }
      byFile.get(relPath)!.push(issue);
    }

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
  }

  // Native character analysis report
  if (allNativeIssues.length > 0) {
    console.log('\x1b[31mNative Character Analysis:\x1b[0m\n');

    for (const issue of allNativeIssues) {
      const relPath = path.relative(DOCS_DIR, issue.file);
      console.log(`  \x1b[31m\u2717\x1b[0m ${relPath}: ${issue.message}`);
    }
    console.log('');
  }

  // Exit logic — all issues are errors
  const hasErrors = allIssues.length > 0 || allNativeIssues.length > 0;

  if (hasErrors) {
    const counts: string[] = [];
    if (allIssues.length > 0) counts.push(`${allIssues.length} line(s) with English text patterns`);
    if (allNativeIssues.length > 0) counts.push(`${allNativeIssues.length} native character error(s)`);

    console.log(
      '\x1b[31m\u2717\x1b[0m Untranslated text detection FAILED\n' +
        `Found ${counts.join(' and ')} in non-English documentation.\n\n` +
        'To fix:\n' +
        '  1. Translate the English text to the appropriate language\n' +
        '  2. Ensure native diacritics are preserved (e.g., Turkish \u00e7/\u015f/\u011f, Spanish \u00f1/\u00e1)\n' +
        '  3. Technical terms and code can remain in English\n' +
        '  4. Add translationPending: true to frontmatter if translation is in progress\n'
    );
    process.exit(1);
  }

  console.log(
    '\x1b[32m\u2713\x1b[0m All non-English documentation appears to be properly translated\n'
  );
  process.exit(0);
}

main();

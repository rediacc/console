#!/usr/bin/env node
/**
 * Untranslated Text Detection for Documentation
 *
 * Three detection layers:
 * 1. Pattern matching: detects common English instruction phrases
 * 2. Native character analysis: verifies non-English files contain characters
 *    from their expected script (Arabic, Cyrillic, CJK, etc.) and that
 *    Latin-script languages contain their distinctive diacritics
 * 3. Paragraph-level language identification (layer 3, added 2026-08-18)
 *
 * WHY LAYER 3 EXISTS: LAYERS 1 AND 2 WERE PROVEN DEAD TOGETHER. Appending four lines
 * of ordinary English prose to packages/www/src/content/docs/de/quick-start.md and
 * running this file printed "de: No untranslated text detected" and exited 0. Neither
 * layer could see it, and for different reasons:
 *
 *   Layer 1 is a hand-written phrase list. Ordinary prose that happens to use none of
 *     those ~25 phrases passes, and most prose does.
 *   Layer 2 is a WHOLE-FILE ratio. One untranslated paragraph inside an otherwise
 *     German file leaves the file's diacritic count far above zero, so the file reads
 *     as translated. The measurement is at the wrong granularity to see a block.
 *
 * Layer 3 measures at the granularity the defect has: the PARAGRAPH. It reuses the
 * detector from scripts/lib/language-detect.ts, the same two-independent-signals design
 * that check-i18n-cross-locale.ts fought its false positives down to -- another
 * language's function words must be PRESENT and the locale's own evidence ABSENT -- so a
 * loanword, a cognate, a product name or a technical term cannot trip it.
 *
 * Usage:
 *   npx tsx scripts/check-docs-untranslated-text.ts
 *
 * Exit codes:
 *   0 - No untranslated text found
 *   1 - Untranslated text detected (blocking)
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { NON_ENGLISH_LOCALES } from '@rediacc/locales';
import { globSync } from 'glob';
import {
  contentWords,
  DISCRIMINATIVE,
  identify,
  NATIVE_SCRIPT,
  norm,
  stripNonLanguage,
} from './lib/language-detect.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration
const DOCS_DIR = path.join(__dirname, '../packages/www/src/content/docs');

// Languages to check (excluding English)
const NON_ENGLISH_LANGS = NON_ENGLISH_LOCALES;

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
  // NOTE: "option"/"section" dropped — cross-language cognates (FR/ES/IT/DE "Option",
  // "section"/"sezione") false-positived on correctly-translated non-English docs.
  /\*\*\s*(button|field|menu|tab|link|icon|checkbox|dropdown|list|panel|window|dialog|modal|form|input|label|setting|configuration)\b/i,

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
  /^---$/, // Frontmatter delimiter
  /^```/, // Code block
  /^>\s*\*\*/, // Blockquote with bold (often tips in English format)
  /^!\[/, // Image reference
  /^\*\(/, // Figure caption start
  /^#+\s/, // Headers (may intentionally be in English)
  /^\s*[-*]\s*\*\*{{t:/, // List items with only translation keys
  /^[0-9]+\.\s+\*\*{{t:/, // Numbered items with only translation keys
  /^\s*$/, // Empty lines
  /^\|/, // Table rows
  /^<!--/, // HTML comments
];

/**
 * Words/patterns that are acceptable in any language (technical terms, etc.)
 */
const ALLOWED_ENGLISH = [
  /\{\{t:[^}]+\}\}/, // Translation keys
  /\*\*{{t:[^}]+}}\*\*/, // Bold translation keys
  /`[^`]+`/, // Inline code
  // A bold subcommand label, e.g. `**list:**`. These are COMMAND NAMES, not prose:
  // the generated CLI docs emit one per leaf, and `rdc backup list` is spelled "list"
  // in every language. Its siblings in the same file (**pull:**, **push:**, **status:**,
  // **restore:**, **purge:**) already pass; only **list:** ever tripped, and solely
  // because "list" also happens to be an English instruction word. Translating it would
  // document a command that does not exist.
  /^\*\*[a-z][a-z0-9-]*:\*\*$/,
  /\b(JSON|CSV|API|URL|SSH|HTTP|HTTPS|SQL|HTML|CSS|JS|TS|UUID|ID|IP|DNS|TLS|SSL|VPN|VM|OS|CPU|RAM|GB|MB|KB|TB|GHz|MHz)\b/i, // Technical acronyms
  /\b(docker|git|npm|node|bash|linux|windows|macos)\b/i, // Technical product names
  /\b(setup|backup|deploy|fork|unmount|checkpoint)\b/i, // Function names that might appear
  /\b(fx)\b/, // UI element names
  /\b(postgresql|mysql|mongodb|redis)\b/i, // Database names
  /\d{4}-\d{2}-\d{2}/, // Dates
  /\b\d+\s*(GB|MB|KB|TB)\b/i, // Size values
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
    nativeCharPattern:
      /[\u00F1\u00D1\u00E1\u00E9\u00ED\u00F3\u00FA\u00C1\u00C9\u00CD\u00D3\u00DA\u00BF\u00A1]/,
  },
  fr: {
    scriptType: 'latin',
    scriptName: 'French',
    // éèêëçàâùûôîïÉÈÊËÇÀÂÙÛÔÎÏ
    nativeCharPattern:
      /[\u00E9\u00E8\u00EA\u00EB\u00E7\u00E0\u00E2\u00F9\u00FB\u00F4\u00EE\u00EF\u00C9\u00C8\u00CA\u00CB\u00C7\u00C0\u00C2\u00D9\u00DB\u00D4\u00CE\u00CF]/,
  },
  tr: {
    scriptType: 'latin',
    scriptName: 'Turkish',
    // ğĞıİşŞçÇöÖüÜ
    nativeCharPattern: /[\u011E\u011F\u0130\u0131\u015E\u015F\u00E7\u00C7\u00F6\u00D6\u00FC\u00DC]/,
  },
  et: {
    scriptType: 'latin',
    scriptName: 'Estonian',
    // \u0161\u017E\u00F5\u00E4\u00F6\u00FC\u0160\u017D\u00D5\u00C4\u00D6\u00DC
    nativeCharPattern: /[\u0161\u017E\u00F5\u00E4\u00F6\u00FC\u0160\u017D\u00D5\u00C4\u00D6\u00DC]/,
  },
  ko: {
    scriptType: 'non-latin',
    scriptName: 'Korean',
    nativeCharPattern: /[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]/,
  },
  pt: {
    scriptType: 'latin',
    scriptName: 'Portuguese',
    // \u00E3\u00E1\u00E2\u00E0\u00E7\u00E9\u00EA\u00ED\u00F3\u00F4\u00F5\u00FA\u00FC\u00C3\u00C1\u00C2\u00C0\u00C7\u00C9\u00CA\u00CD\u00D3\u00D4\u00D5\u00DA\u00DC
    nativeCharPattern:
      /[\u00E3\u00E1\u00E2\u00E0\u00E7\u00E9\u00EA\u00ED\u00F3\u00F4\u00F5\u00FA\u00FC\u00C3\u00C1\u00C2\u00C0\u00C7\u00C9\u00CA\u00CD\u00D3\u00D4\u00D5\u00DA\u00DC]/,
  },
  it: {
    scriptType: 'latin',
    scriptName: 'Italian',
    // \u00E0\u00E8\u00E9\u00EC\u00ED\u00EE\u00F2\u00F3\u00F9\u00FA\u00C0\u00C8\u00C9\u00CC\u00CD\u00CE\u00D2\u00D3\u00D9\u00DA
    nativeCharPattern:
      /[\u00E0\u00E8\u00E9\u00EC\u00ED\u00EE\u00F2\u00F3\u00F9\u00FA\u00C0\u00C8\u00C9\u00CC\u00CD\u00CE\u00D2\u00D3\u00D9\u00DA]/,
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
  // Allow opting out of untranslated-text checks for starter/placeholder files
  // by adding `untranslated: true` to the frontmatter. Use sparingly.
  if (/^untranslated:\s*true\b/m.test(content.split(/^---$/m)[1] ?? '')) {
    return issues;
  }
  const lines = content.split('\n');

  let inCodeBlock = false;
  let inFrontmatter = false;
  let frontmatterCount = 0;
  let blankRun = 0;

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

    if (/^\s*$/.test(line)) {
      blankRun++;
      if (blankRun === 6) {
        issues.push({
          file: filePath,
          lang,
          lineNumber,
          content: '[blank line run]',
          pattern: 'excessive blank lines',
        });
      }
      continue;
    }
    blankRun = 0;

    if (line.trim() === '<!---->') {
      issues.push({
        file: filePath,
        lang,
        lineNumber,
        content: '<!---->',
        pattern: 'html comment padding',
      });
      continue;
    }

    if (/^\|/.test(line)) {
      if (/^\|[\s\-:|]+\|?\s*$/.test(line)) {
        continue;
      }
      const tableText = line.replace(/\|/g, ' ');
      const pattern = detectUntranslatedText(tableText);
      if (pattern) {
        issues.push({
          file: filePath,
          lang,
          lineNumber,
          content: line.trim().slice(0, 100) + (line.length > 100 ? '...' : ''),
          pattern,
        });
      }
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
  isGenerated: boolean;
} {
  const lines = content.split('\n');
  const bodyLines: string[] = [];
  let inCodeBlock = false;
  let inFrontmatter = false;
  let frontmatterCount = 0;
  let frontmatterTitle = '';
  let frontmatterDescription = '';
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
      if (
        descPlainMatch &&
        !descPlainMatch[1].startsWith('>') &&
        !descPlainMatch[1].startsWith('|')
      ) {
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
    cleaned = cleaned.replace(/`[^`]+`/g, ''); // Remove inline code
    cleaned = cleaned.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1'); // [text](url) -> text
    cleaned = cleaned.replace(/^#+\s*/, ''); // Remove heading markers
    cleaned = cleaned.replace(/^\s*[-*+]\s+/, ''); // Remove list markers
    cleaned = cleaned.replace(/^\s*\d+\.\s+/, ''); // Remove numbered list markers
    cleaned = cleaned.replace(/^>\s*/, ''); // Remove blockquote markers
    cleaned = cleaned.replace(/\*\*([^*]*)\*\*/g, '$1'); // Remove bold markers
    cleaned = cleaned.replace(/\*([^*]*)\*/g, '$1'); // Remove italic markers
    cleaned = cleaned.trim();

    if (cleaned.length > 0) {
      bodyLines.push(cleaned);
    }
  }

  return {
    bodyText: bodyLines.join(' '),
    frontmatterTitle: frontmatterTitle.trim(),
    frontmatterDescription: frontmatterDescription.trim(),
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
  // Honor `untranslated: true` frontmatter flag for starter/placeholder files
  if (/^untranslated:\s*true\b/m.test(content.split(/^---$/m)[1] ?? '')) {
    return [];
  }
  const { bodyText, frontmatterTitle, frontmatterDescription, isGenerated } =
    extractTextParts(content);

  // Skip auto-generated files ({{t:key}} content)
  if (isGenerated) return [];

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
// PARAGRAPH LANGUAGE IDENTIFICATION (Layer 3)
// =============================================================================

/**
 * A prose paragraph of a markdown file, with the source line it starts on.
 *
 * BLOCKS, not lines. A single line is too short to identify a language from with any
 * confidence (the detector needs three content words before it will answer at all), and
 * the whole file is too long to see one untranslated block inside. The paragraph is the
 * unit the defect actually arrives in.
 */
interface ProseBlock {
  lineNumber: number;
  text: string;
}

/**
 * Split a markdown file into prose blocks, dropping everything that is not natural
 * language: frontmatter, fenced code, tables, images, HTML comments, and the markdown
 * syntax itself. Headings are kept -- they are prose, and an untranslated heading is the
 * same defect -- but they terminate a block so a heading and its body are never fused.
 */
function extractProseBlocks(content: string): ProseBlock[] {
  const lines = content.split('\n');
  const blocks: ProseBlock[] = [];
  let current: string[] = [];
  let currentLine = 0;
  let inCodeBlock = false;
  let inFrontmatter = false;
  let frontmatterCount = 0;

  const flush = () => {
    if (current.length > 0) blocks.push({ lineNumber: currentLine, text: current.join(' ') });
    current = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line === '---') {
      frontmatterCount++;
      if (frontmatterCount === 1) inFrontmatter = true;
      else if (frontmatterCount === 2) inFrontmatter = false;
      flush();
      continue;
    }
    if (inFrontmatter) continue;
    if (line.startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      flush();
      continue;
    }
    if (inCodeBlock) continue;
    if (/^\s*$/.test(line) || /^<!--/.test(line) || /^!\[/.test(line) || /^\|/.test(line)) {
      flush();
      continue;
    }

    let cleaned = line;
    cleaned = cleaned.replace(/`[^`]*`/g, ' ');
    cleaned = cleaned.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1');
    cleaned = cleaned.replace(/^\s*#+\s*/, '');
    cleaned = cleaned.replace(/^\s*[-*+]\s+/, '');
    cleaned = cleaned.replace(/^\s*\d+\.\s+/, '');
    cleaned = cleaned.replace(/^>\s*/, '');
    cleaned = cleaned.replace(/\*\*([^*]*)\*\*/g, '$1');
    cleaned = cleaned.replace(/\*([^*]*)\*/g, '$1');
    cleaned = cleaned.trim();
    if (cleaned.length === 0) {
      flush();
      continue;
    }
    if (current.length === 0) currentLine = i + 1;
    current.push(cleaned);
    // A heading closes its own block: fusing it with the paragraph below would let a
    // translated body vouch for an untranslated heading and vice versa.
    if (/^\s*#/.test(line)) flush();
  }
  flush();
  return blocks;
}

/**
 * The number of content words a block must carry before it is judged at all.
 *
 * Twelve, not three. The detector itself answers from three, which is right for a UI
 * string but far too eager for documentation: a two-word caption or a short list item
 * made of loanwords would be identified as English on almost no evidence. Every
 * measured false positive during authoring sat below this floor.
 */
const MIN_BLOCK_CONTENT_WORDS = 12;

/**
 * How many of ANOTHER language's discriminative function words must be present.
 *
 * Three, one more than the cross-locale gate's two. Prose blocks are long enough that
 * two stray matches are cheap; requiring three keeps the signal where the defect is.
 */
const MIN_FOREIGN_SCORE = 3;

interface ForeignBlockIssue {
  file: string;
  lang: string;
  lineNumber: number;
  detected: string;
  score: number;
  excerpt: string;
}

/**
 * Report prose blocks written in a language that is not this file's locale.
 *
 * TWO INDEPENDENT SIGNALS, exactly as in scripts/lib/language-detect.ts:
 *   1. another language's discriminative function words are present, at least three;
 *   2. NONE of this locale's own evidence is present in the same block -- its script for
 *      ar/ja/ko/ru/zh, its function words or its diacritics for the Latin locales.
 * Requiring both is what separates "this paragraph was never translated" from "this
 * paragraph mentions Copy-on-Write and Docker Compose", and it is the design that took
 * the cross-locale gate from 136 false positives to zero.
 */
function analyzeProseBlocks(filePath: string, lang: string): ForeignBlockIssue[] {
  const content = fs.readFileSync(filePath, 'utf-8');
  if (/^untranslated:\s*true\b/m.test(content.split(/^---$/m)[1] ?? '')) return [];
  // `generated: true` files are {{t:key}} scaffolding, not prose.
  if (/^generated:\s*true\b/m.test(content.split(/^---$/m)[1] ?? '')) return [];

  const native = NATIVE_SCRIPT[lang];
  const own = DISCRIMINATIVE[lang] ?? new Set<string>();
  const diacritics = LOCALE_CHAR_CONFIG[lang]?.nativeCharPattern;
  const issues: ForeignBlockIssue[] = [];

  for (const block of extractProseBlocks(content)) {
    const text = stripNonLanguage(block.text);
    if (contentWords(text).length < MIN_BLOCK_CONTENT_WORDS) continue;

    const id = identify(text);
    if (!id || id.lang === lang || id.score < MIN_FOREIGN_SCORE) continue;

    if (native) {
      // Any of the locale's own script in the block means the block is in that locale,
      // whatever Latin technical vocabulary it also carries.
      if (native.test(text)) continue;
    } else {
      const words = new Set(norm(text).split(/[^a-z]+/));
      if ([...own].some((w) => words.has(norm(w)))) continue;
      if (diacritics?.test(block.text)) continue;
    }

    issues.push({
      file: filePath,
      lang,
      lineNumber: block.lineNumber,
      detected: id.lang,
      score: id.score,
      excerpt: block.text.length > 100 ? `${block.text.slice(0, 97)}...` : block.text,
    });
  }
  return issues;
}

/**
 * CONTROL. Plant the exact defect that proved this gate dead, and require layer 3 to
 * report it -- then plant the three shapes that must NOT fire.
 *
 * Runs INLINE on every invocation, never behind a flag. The reason is on the record in
 * this repo twice over: check-i18n-cross-locale.ts carried its fire-proof behind
 * `--selftest` and nothing ever passed the flag, and THIS file was green for its whole
 * life over a defect a four-line paste could produce. A control that only runs when
 * someone remembers to ask for it is not a control.
 */
function controlLayer3(): void {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'untranslated-control-'));
  const write = (name: string, body: string) => {
    const f = path.join(tmp, name);
    fs.writeFileSync(f, body);
    return f;
  };
  const failures: string[] = [];
  const expect = (name: string, actual: number, wanted: 'some' | 'none') => {
    const ok = wanted === 'some' ? actual > 0 : actual === 0;
    if (!ok) failures.push(`${name}: expected ${wanted}, got ${actual} finding(s)`);
  };

  const GERMAN_DOC = [
    '---',
    'title: Schnellstart',
    '---',
    '',
    '## Erste Schritte mit Rediacc',
    '',
    'Rediacc schützt Ihre Produktionsdaten mit sofortigen Wiederherstellungspunkten.',
    'Jedes Repository ist von jedem anderen isoliert, damit ein Fehler an einer Stelle',
    'sich niemals ausbreitet und Sie nichts überschreiben können.',
    '',
  ].join('\n');

  // THE PLANT: the literal paragraph that proved this gate dead on 2026-08-18.
  const ENGLISH_PARAGRAPH = [
    'Rediacc keeps your production data safe with instant recovery points. Every',
    'repository is isolated from every other one, so a mistake in one place never',
    'spreads. Recovery takes seconds rather than hours, and nothing is ever',
    'overwritten until you say so.',
  ].join('\n');

  expect(
    'a clean German document reports nothing',
    analyzeProseBlocks(write('clean.md', GERMAN_DOC), 'de').length,
    'none'
  );
  expect(
    'an English paragraph appended to a German document is reported',
    analyzeProseBlocks(write('planted.md', `${GERMAN_DOC}\n${ENGLISH_PARAGRAPH}\n`), 'de').length,
    'some'
  );
  expect(
    'an English paragraph appended to a Japanese document is reported',
    analyzeProseBlocks(
      write(
        'planted-ja.md',
        `---\ntitle: クイックスタート\n---\n\nRediacc は本番データを即時の復旧ポイントで保護します。各リポジトリは互いに分離されています。\n\n${ENGLISH_PARAGRAPH}\n`
      ),
      'ja'
    ).length,
    'some'
  );
  // FALSE-POSITIVE CONTROLS. Each of these is a shape that exists in the real tree and
  // must never be reported, or the gate gets suppressed instead of fixed.
  expect(
    'a fenced English code block inside a German document is not reported',
    analyzeProseBlocks(
      write(
        'code.md',
        `${GERMAN_DOC}\n\`\`\`bash\n# create the repository and then push it to the machine\nrdc repo create demo --tag latest\n\`\`\`\n`
      ),
      'de'
    ).length,
    'none'
  );
  expect(
    'a German paragraph dense with English product names is not reported',
    analyzeProseBlocks(
      write(
        'products.md',
        `${GERMAN_DOC}\nDer Docker Compose Stack nutzt BTRFS Copy-on-Write Snapshots und LUKS, damit Kubernetes und Ceph zusammenarbeiten können.\n`
      ),
      'de'
    ).length,
    'none'
  );

  fs.rmSync(tmp, { recursive: true, force: true });
  if (failures.length > 0) {
    console.error('\x1b[31m✗\x1b[0m Layer 3 CONTROL FAILED. This gate cannot detect the');
    console.error('  defect it exists for, so its verdict on the real tree means nothing.');
    for (const f of failures) console.error(`    ${f}`);
    process.exit(1);
  }
}

// =============================================================================
// MAIN
// =============================================================================

function main(): void {
  console.log('Untranslated Text Detection');
  console.log('============================================================\n');

  // CONTROL FIRST. If layer 3 cannot see the planted defect, nothing below is evidence.
  controlLayer3();

  // REFUSE, never skip. This used to print a warning and exit 0, which is root pattern 2
  // of .ci/scripts/test/gates/test-gate-anti-vacuity.sh: an assertion disabled when its
  // input is absent is indistinguishable in the output from an assertion that passed.
  if (!fs.existsSync(DOCS_DIR)) {
    console.error(
      `\x1b[31m✗\x1b[0m Refusing to run: the docs tree is missing (${DOCS_DIR}).\n` +
        `  A scan over zero files would report "properly translated" while checking nothing.`
    );
    process.exit(1);
  }

  const allIssues: UntranslatedLine[] = [];
  const allNativeIssues: NativeCharIssue[] = [];
  const allBlockIssues: ForeignBlockIssue[] = [];
  let filesScanned = 0;
  // frontmatter-no-native is warning-only for Latin scripts (a title/description can
  // legitimately lack diacritics, e.g. Italian "Architettura"); see analyzeNativeChars comment.
  const nativeWarnings: NativeCharIssue[] = [];

  console.log('Checking non-English documentation for untranslated text...\n');

  for (const lang of NON_ENGLISH_LANGS) {
    const langDir = path.join(DOCS_DIR, lang);
    if (!fs.existsSync(langDir)) {
      console.log(`  \x1b[33m!\x1b[0m ${lang}: Directory not found, skipping`);
      continue;
    }

    const mdFiles = globSync(`${langDir}/**/*.{md,mdx}`);
    let langPatternIssues = 0;
    filesScanned += mdFiles.length;

    for (const file of mdFiles) {
      const patternIssues = analyzeFile(file, lang);
      allIssues.push(...patternIssues);
      langPatternIssues += patternIssues.length;

      allBlockIssues.push(...analyzeProseBlocks(file, lang));

      const nativeIssues = analyzeNativeChars(file, lang);
      const isLatin = LOCALE_CHAR_CONFIG[lang]?.scriptType !== 'non-latin';
      for (const iss of nativeIssues) {
        if (iss.kind === 'frontmatter-no-native' && isLatin) nativeWarnings.push(iss);
        else allNativeIssues.push(iss);
      }
    }

    const langNativeErrors = allNativeIssues.filter((i) => i.lang === lang).length;
    const langBlockErrors = allBlockIssues.filter((i) => i.lang === lang).length;
    const totalErrors = langPatternIssues + langNativeErrors + langBlockErrors;

    if (totalErrors > 0) {
      const parts: string[] = [];
      if (langPatternIssues > 0) parts.push(`${langPatternIssues} pattern match(es)`);
      if (langNativeErrors > 0) parts.push(`${langNativeErrors} native char error(s)`);
      if (langBlockErrors > 0) parts.push(`${langBlockErrors} foreign-language paragraph(s)`);
      console.log(`  \x1b[31m\u2717\x1b[0m ${lang}: ${parts.join(', ')}`);
    } else {
      // State the FLOOR alongside the pass. A clean line that does not say what
      // it could not have seen is how a passing single-sentence plant gets read
      // as proof the gate is dead again, which is precisely the mistake that
      // was made against this gate once already.
      console.log(
        `  \x1b[32m\u2713\x1b[0m ${lang}: No untranslated text detected ` +
          `\x1b[2m(layer 3 floor: blocks under ${MIN_BLOCK_CONTENT_WORDS} words are not language-checked)\x1b[0m`
      );
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

  // Layer 3 report: paragraphs written in the wrong language.
  if (allBlockIssues.length > 0) {
    console.log('\x1b[31mForeign-Language Paragraphs (Layer 3):\x1b[0m\n');
    const byFile = new Map<string, ForeignBlockIssue[]>();
    for (const issue of allBlockIssues) {
      const rel = path.relative(DOCS_DIR, issue.file);
      byFile.set(rel, [...(byFile.get(rel) ?? []), issue]);
    }
    let shown = 0;
    for (const [file, issues] of [...byFile].sort((a, b) => b[1].length - a[1].length)) {
      if (shown >= 30) break;
      console.log(`  \x1b[33m${file}\x1b[0m  (${issues.length})`);
      for (const issue of issues.slice(0, 3)) {
        console.log(
          `    Line ${issue.lineNumber} reads as ${issue.detected} (score ${issue.score}): ${issue.excerpt}`
        );
        shown++;
      }
    }
    if (byFile.size > 30) console.log(`  ... and ${byFile.size - 30} more file(s)\n`);
    console.log('');
  }

  // Warnings (non-failing): Latin frontmatter without diacritics.
  if (nativeWarnings.length > 0) {
    console.log(`\x1b[33mWarnings (${nativeWarnings.length}, non-failing):\x1b[0m`);
    for (const issue of nativeWarnings.slice(0, 10)) {
      console.log(`  \x1b[33m!\x1b[0m ${path.relative(DOCS_DIR, issue.file)}: ${issue.message}`);
    }
    if (nativeWarnings.length > 10) console.log(`  ... and ${nativeWarnings.length - 10} more`);
    console.log('');
  }

  // FLOOR. A run that opened no files is not a pass. The docs tree exists (checked
  // above), so zero files means the glob or the locale set has gone wrong, and "found
  // nothing" would be indistinguishable from "checked nothing".
  const MIN_FILES = 100;
  if (filesScanned < MIN_FILES) {
    console.error(
      `\x1b[31m✗\x1b[0m Refusing to report: only ${filesScanned} file(s) scanned across ` +
        `${NON_ENGLISH_LANGS.length} locale(s), below the floor of ${MIN_FILES}.`
    );
    process.exit(1);
  }

  // Exit logic — pattern matches, native char issues and foreign paragraphs are errors
  const hasErrors = allIssues.length > 0 || allNativeIssues.length > 0 || allBlockIssues.length > 0;

  if (hasErrors) {
    const counts: string[] = [];
    if (allIssues.length > 0) counts.push(`${allIssues.length} line(s) with English text patterns`);
    if (allNativeIssues.length > 0)
      counts.push(`${allNativeIssues.length} native character error(s)`);
    if (allBlockIssues.length > 0)
      counts.push(`${allBlockIssues.length} paragraph(s) in the wrong language`);

    console.log(
      '\x1b[31m\u2717\x1b[0m Untranslated text detection FAILED\n' +
        `Found ${counts.join(' and ')} in non-English documentation.\n\n` +
        'To fix:\n' +
        '  1. Translate the English text to the appropriate language\n' +
        '  2. Ensure native diacritics are preserved (e.g., Turkish \u00e7/\u015f/\u011f, Spanish \u00f1/\u00e1)\n' +
        '  3. Technical terms and code can remain in English\n'
    );
    process.exit(1);
  }

  console.log(
    `\x1b[32m\u2713\x1b[0m All non-English documentation appears to be properly translated ` +
      `(${filesScanned} file(s) across ${NON_ENGLISH_LANGS.length} locale(s); layer-3 control fired)\n`
  );
  process.exit(0);
}

main();

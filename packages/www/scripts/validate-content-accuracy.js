#!/usr/bin/env node
/**
 * Content Accuracy Validation Script
 *
 * Validates that CLI commands and URLs in content files are correct.
 * Complements validate-docs-cli-usage.js (code fences) and
 * validate-landing-cli-usage.js (structured terminal blocks) by checking:
 *
 * Rules:
 * - docs-inline-cli-invalid: rdc commands in markdown prose (outside code fences)
 * - json-cli-command-invalid: rdc commands in translation JSON string values (--strict only)
 * - invalid-rediacc-url: URLs with rediacc domains not in the allowlist
 * - claim-overstatement: audit-trail wording the product does not back (docs, blog, translation JSON)
 *
 * Usage:
 *   node scripts/validate-content-accuracy.js           # docs + URLs (CI default)
 *   node scripts/validate-content-accuracy.js --strict   # also check JSON translation strings
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SITE_LOCALES } from '@rediacc/locales';
import {
  WK_RELEASES_ORIGIN,
  WK_SITE_ORIGIN,
} from '../../shared/src/config/well-known.generated.ts';
import { parseRdcCommand } from './lib/cli-reference-catalog.js';
import { findRegressions, loadBacklog, writeBacklog } from './lib/p7-backlog.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, '..');
const DOCS_DIR = path.join(ROOT_DIR, 'src', 'content', 'docs');
const BLOG_DIR = path.join(ROOT_DIR, 'src', 'content', 'blog');
const TRANSLATIONS_DIR = path.join(ROOT_DIR, 'src', 'i18n', 'translations');

const LANGUAGES = SITE_LOCALES;

// Auto-generated docs validated separately by validate-cli-docs.js
const EXCLUDED_DOC_SLUGS = new Set(['cli-application.md']);

// Commands that exist in the CLI but are not exported to command-tree.json
const TREE_UNLISTED_COMMANDS = new Set(['shortcuts']);

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');

// Product hosts the tracked deploy config defines: each region's account domain (regions.json) and each MCP Worker's custom domain (workers/mcp/wrangler.*.toml routes). Every host found there is accepted in docs and blog prose, so a config change that adds a domain also whitelists it for content. An empty result for either source throws, because a changed JSON shape or pattern would otherwise drop hosts silently.
export function productHosts(repoRoot = REPO_ROOT) {
  const hosts = [];
  const regions = JSON.parse(fs.readFileSync(path.join(repoRoot, 'regions.json'), 'utf8')).regions;
  for (const region of regions) hosts.push(region.domain);
  if (hosts.length === 0 || hosts.some((h) => typeof h !== 'string' || !h)) {
    throw new Error('regions.json yields no usable region domains');
  }
  const mcpHosts = [];
  const mcpDir = path.join(repoRoot, 'workers/mcp');
  for (const name of fs.readdirSync(mcpDir)) {
    if (!/^wrangler\..+\.toml$/.test(name)) continue;
    const toml = fs.readFileSync(path.join(mcpDir, name), 'utf8');
    for (const m of toml.matchAll(/pattern\s*=\s*"([a-z0-9.-]+)"/g)) mcpHosts.push(m[1]);
  }
  if (mcpHosts.length === 0) throw new Error('workers/mcp/wrangler.*.toml yield no route patterns');
  return [...hosts, ...mcpHosts];
}

// Valid rediacc hosts: the site, the releases host, and the product hosts above.
const VALID_REDIACC_DOMAINS = new Set([
  new URL(WK_SITE_ORIGIN).host,
  new URL(WK_RELEASES_ORIGIN).host,
  ...productHosts(),
]);

// Regex to extract rdc commands from inline backticks
const BACKTICK_RDC_RE = /`(rdc\s[^`]+)`/g;
// Regex to extract rdc commands from translation command fields
const JSON_COMMAND_FIELD_RE = /"command"\s*:\s*"([^"]*\brdc\s[^"]*)"/;
// Regex to match URLs with rediacc in the domain
const REDIACC_URL_RE = /https?:\/\/([a-z0-9.-]*rediacc[a-z0-9.-]*\.[a-z]{2,})(\/[^\s"'`)\]]*)?/gi;

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  yellow: (s) => `\x1b[33m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function addError(errors, rule, file, line, message, matchedText, suggestion) {
  errors.push({ rule, file, line, message, matchedText, suggestion });
}

// ---------------------------------------------------------------------------
// Rule 1: docs-inline-cli-invalid (markdown docs, inline text outside fences)
// ---------------------------------------------------------------------------

function extractInlineRdcCommands(content, file) {
  const commands = [];
  const lines = content.split(/\r?\n/);
  let inFence = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;

    // Extract from inline backticks: `rdc machine info prod`
    BACKTICK_RDC_RE.lastIndex = 0;
    for (const match of line.matchAll(BACKTICK_RDC_RE)) {
      commands.push({ text: match[1].trim(), line: i + 1, file });
    }
  }

  return commands;
}

// ---------------------------------------------------------------------------
// Rule 2: json-cli-command-invalid (translation JSON string values)
// ---------------------------------------------------------------------------

function extractJsonRdcCommands(jsonContent, file) {
  const commands = [];
  const lines = jsonContent.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.includes('"command"') || !line.includes('rdc ')) continue;

    const match = line.match(JSON_COMMAND_FIELD_RE);
    if (!match) continue;

    const text = match[1].trim();
    if (text.split(/\s+/).length >= 2) {
      commands.push({ text, line: i + 1, file });
    }
  }

  return commands;
}

// ---------------------------------------------------------------------------
// Shared CLI command validation
// ---------------------------------------------------------------------------

// Inline docs legitimately mention commands without full arguments. Only report errors that indicate a genuinely wrong command or flag.
const INLINE_REPORTABLE_REASONS = new Set([
  'unknown-command',
  'unknown-option',
  'unknown-global-option',
]);

function validateRdcCommands(commands, errors, rule) {
  for (const cmd of commands) {
    let text = cmd.text.replace(/^\$\s*/, '');
    // Stop at pipes, redirects, semicolons
    text = text
      .split(/\s*[|;>&]/)
      .shift()
      .trim();
    // Strip trailing prose punctuation
    text = text.replace(/[.,:;!?)}\]]+$/, '').trim();

    if (!text.startsWith('rdc ')) continue;

    // Skip glob/wildcard patterns (e.g. "rdc machine info *")
    if (/[*?]/.test(text)) continue;

    const tokens = text.split(/\s+/);

    // Skip if the command position has angle-bracket placeholder (e.g. "rdc --flag <command>")
    const firstNonFlag = tokens.slice(1).find((t) => !t.startsWith('-'));
    if (firstNonFlag?.startsWith('<')) continue;

    // Allow commands that exist but aren't in the command tree export
    const rootCmd = tokens.find((t) => !t.startsWith('-') && t !== 'rdc');
    if (rootCmd && TREE_UNLISTED_COMMANDS.has(rootCmd)) continue;

    const parsed = parseRdcCommand(text);
    if (!parsed.ok && INLINE_REPORTABLE_REASONS.has(parsed.reason)) {
      const message = formatParseError(parsed);
      const suggestion = suggestedFix(parsed);
      addError(errors, rule, cmd.file, cmd.line, message, text, suggestion);
    }
  }
}

/** Stand-in when the CLI parser rejects a command without naming a reason. */
const UNKNOWN_REASON = 'unknown';

function formatParseError(parsed) {
  switch (parsed.reason) {
    case 'unknown-global-option':
      return `Unknown global option: ${parsed.flag}`;
    case 'unknown-command':
      return `Unknown command: rdc ${parsed.near}`;
    case 'unknown-option':
      return `Unknown option ${parsed.flag} for "rdc ${parsed.commandPath}"`;
    default:
      return `Invalid command (${parsed.reason ?? UNKNOWN_REASON})`;
  }
}

function suggestedFix(parsed) {
  if (parsed.reason === 'unknown-command') return 'Use a valid rdc subcommand (see rdc --help)';
  if (parsed.reason === 'unknown-option')
    return `Remove or replace unsupported option ${parsed.flag}`;
  return null;
}

// ---------------------------------------------------------------------------
// Rule 3: invalid-rediacc-url
// ---------------------------------------------------------------------------

function extractRediaccUrls(content, file) {
  const urls = [];
  const lines = content.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    REDIACC_URL_RE.lastIndex = 0;
    for (const match of line.matchAll(REDIACC_URL_RE)) {
      const domain = match[1].toLowerCase();
      const fullUrl = match[0];
      urls.push({ domain, fullUrl, line: i + 1, file });
    }
  }

  return urls;
}

function validateUrls(urls, errors) {
  for (const entry of urls) {
    if (!VALID_REDIACC_DOMAINS.has(entry.domain)) {
      addError(
        errors,
        'invalid-rediacc-url',
        entry.file,
        entry.line,
        `Invalid rediacc domain: ${entry.domain}`,
        entry.fullUrl,
        `Use one of: ${[...VALID_REDIACC_DOMAINS].join(', ')}`
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Rule 4: claim-overstatement (docs, blog, translation JSON)
// ---------------------------------------------------------------------------

// Phrase arms. `forensic trail` and `forensic-grade` are refused outright; `hash-chained` is refused only within one sentence of `audit log` that names neither a per-org-and-day nor a day-file scope, because the server log is chained per org and day (PLAN-console-audit-r2 D5) and the workstation log is chained per file.
const FORENSIC_TRAIL_RE = /forensic[ -]trail/i;
const FORENSIC_GRADE_RE = /forensic[ -]grade/i;
const HASH_CHAINED_RE = /hash-chained/i;
const AUDIT_LOG_RE = /audit[ -]log/i;
const CHAIN_SCOPE_RE = /chained per org|per org and (?:per )?day|chained per file|day file/i;

// Each entry exempts one line (file suffix plus a substring of the line) and states why the claim holds there. An entry without a reason exempts nothing.
export const CLAIM_OVERSTATEMENT_ALLOWLIST = [
  {
    file: 'docs/en/ai-agents-safety.md',
    includes: '~/.config/rediacc/audit.log.jsonl',
    reason:
      'describes the local CLI audit file, where each line carries the sha256 of the previous line, which is the chain the sentence defines.',
  },
  {
    file: 'docs/en/ai-agents-safety.md',
    includes: 'a hash-chained audit log.',
    reason: 'front-matter summary of the same local CLI audit file.',
  },
  {
    file: 'docs/en/ai-agents-overview.md',
    includes: 'and the hash-chained audit log.',
    reason: 'points at the AI Agent Safety page, which documents the local CLI audit file chain.',
  },
  {
    file: 'blog/en/nis2-supply-chain-self-hosted.md',
    includes: 'rdc config audit verify',
    reason: 'names the CLI verifier that validates the local chain end to end.',
  },
  {
    file: 'blog/en/nis2-effectiveness-without-theatre.md',
    includes: 'workstation audit log',
    reason: 'scoped by the sentence to the operator workstation log, not the server log.',
  },
  {
    file: 'blog/en/nis2-effectiveness-without-theatre.md',
    includes: 'local workstation log is hash-chained',
    reason: 'scoped by the sentence to the local workstation log, verified by the CLI.',
  },
];

// An allowlist entry exempts only the hash-chained arm, and only when a line the sentence spans carries the substring; the forensic arms are never exempted.
function isClaimAllowlisted(file, lines, allowlist) {
  return allowlist.some(
    (entry) =>
      entry.reason &&
      file.endsWith(entry.file) &&
      lines.some((line) => line.includes(entry.includes))
  );
}

function overstatementArms(sentence) {
  const arms = [];
  if (FORENSIC_TRAIL_RE.test(sentence)) arms.push('forensic trail');
  if (FORENSIC_GRADE_RE.test(sentence)) arms.push('forensic-grade');
  if (
    HASH_CHAINED_RE.test(sentence) &&
    AUDIT_LOG_RE.test(sentence) &&
    !CHAIN_SCOPE_RE.test(sentence)
  ) {
    arms.push('hash-chained audit log');
  }
  return arms;
}

// Sentences are cut from each run of non-blank lines joined by single spaces, so a sentence wrapped across physical lines is still one sentence. A hit reports the line the sentence starts on.
function* sentencesWithLines(lines) {
  let i = 0;
  while (i < lines.length) {
    if (lines[i].trim() === '') {
      i++;
      continue;
    }
    const start = i;
    while (i < lines.length && lines[i].trim() !== '') i++;
    const block = lines.slice(start, i);
    const starts = [];
    let text = '';
    for (const line of block) {
      starts.push(text.length);
      text += `${line} `;
    }
    const lineAt = (offset) => {
      let n = 0;
      while (n + 1 < starts.length && starts[n + 1] <= offset) n++;
      return n;
    };
    let from = 0;
    for (const piece of text.split(/(?<=[.!?])\s+/)) {
      const at = text.indexOf(piece, from);
      from = at + piece.length;
      const first = lineAt(at + (piece.length - piece.trimStart().length));
      const last = lineAt(Math.max(at, from - 1));
      yield { sentence: piece, line: start + first + 1, spanned: block.slice(first, last + 1) };
    }
  }
}

export function findClaimOverstatements(content, file, allowlist = CLAIM_OVERSTATEMENT_ALLOWLIST) {
  const found = [];
  const lines = content.split(/\r?\n/);
  for (const { sentence, line, spanned } of sentencesWithLines(lines)) {
    const allowed = isClaimAllowlisted(file, spanned, allowlist);
    for (const arm of overstatementArms(sentence)) {
      if (allowed && arm === 'hash-chained audit log') continue;
      found.push({ file, line, arm, text: sentence.trim().slice(0, 160) });
    }
  }
  return found;
}

function validateClaims(content, file, errors) {
  for (const hit of findClaimOverstatements(content, file)) {
    addError(
      errors,
      'claim-overstatement',
      file,
      hit.line,
      `Overstated claim (${hit.arm})`,
      hit.text,
      'State the scope (per org and day for the server log, local file for the CLI log) or drop the claim'
    );
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function listMarkdownFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => (f.endsWith('.md') || f.endsWith('.mdx')) && !EXCLUDED_DOC_SLUGS.has(f));
}

function groupByRule(errors) {
  const grouped = new Map();
  for (const error of errors) {
    if (!grouped.has(error.rule)) grouped.set(error.rule, []);
    grouped.get(error.rule).push(error);
  }
  return grouped;
}

function printSummary(errors, warnings) {
  // Declared up front: the clean-run path below needs it too, so it cannot live further down.
  const BASELINE_PATH = path.resolve(__dirname, 'content-accuracy-baseline.json');

  console.log(colors.bold('Content Accuracy Validation'));
  console.log('='.repeat(60));

  // NOTE: a clean run must still reach the backlog check below. Zero errors against a non-empty baseline is the stale-entry case — short-circuiting here is what let 13 already-fixed entries sit in the baseline unnoticed, each one pre-authorising 16 future violations.
  if (errors.length === 0 && warnings.length === 0) {
    const stale = findRegressions(errors, loadBacklog(BASELINE_PATH));
    if (stale.length === 0) {
      console.log(colors.green('✓ All content accuracy checks passed.'));
      console.log('='.repeat(60));
      return 0;
    }
    console.log(colors.red('\n✗ Content is CLEAN but the P7 backlog still records violations:\n'));
    for (const r of stale) console.log(colors.red(`  ✗ ${r}`));
    console.log(
      colors.dim(
        '\n  Delete these entries. An entry that outlives its violations is not a debt record,\n' +
          '  it is a standing budget for the next breakage in that file.\n'
      )
    );
    console.log('='.repeat(60));
    return 1;
  }

  // Print errors
  if (errors.length > 0) {
    const grouped = groupByRule(errors);
    for (const [rule, items] of grouped.entries()) {
      console.log(colors.red(`\n[${rule}] (${items.length} errors)`));
      console.log(colors.dim('-'.repeat(40)));
      for (const item of items) {
        console.log(colors.red(`  ✗ ${item.file}:${item.line}`));
        console.log(colors.dim(`    ${item.message}`));
        console.log(colors.cyan(`    → ${item.matchedText}`));
        if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
      }
    }
  }

  // Print warnings
  if (warnings.length > 0) {
    const grouped = groupByRule(warnings);
    for (const [rule, items] of grouped.entries()) {
      console.log(colors.yellow(`\n[${rule}] (${items.length} warnings)`));
      console.log(colors.dim('-'.repeat(40)));
      for (const item of items) {
        console.log(colors.yellow(`  ⚠ ${item.file}:${item.line}`));
        console.log(colors.dim(`    ${item.message}`));
        console.log(colors.cyan(`    → ${item.matchedText}`));
        if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
      }
    }
  }

  // The frozen P7 backlog: see scripts/lib/p7-backlog.js for the BLOCKER and the self-destruct condition. The backlog is a RATCHET: a NEW doc or a GROWING count fails, and so does a count that FELL or an entry whose violations are all gone. (BASELINE_PATH is declared at the top of this function — the clean-run path above needs it as well.)
  if (process.argv.includes('--write-baseline')) {
    const { files, violations } = writeBacklog(BASELINE_PATH, errors);
    console.log(colors.yellow(`Wrote P7 backlog: ${files} files, ${violations} violations.`));
    return 0;
  }
  const regressions = findRegressions(errors, loadBacklog(BASELINE_PATH));

  // Summary
  console.log('\n' + '='.repeat(60));
  const parts = [];
  if (errors.length > 0) parts.push(colors.red(`${errors.length} errors`));
  if (warnings.length > 0) parts.push(colors.yellow(`${warnings.length} warnings`));
  console.log(`SUMMARY: ${parts.join(', ')}`);

  if (regressions.length > 0) {
    console.log(colors.red('\n✗ P7 backlog OUT OF SYNC (the ratchet turns both ways):\n'));
    for (const r of regressions) console.log(colors.red(`  ✗ ${r}`));
    console.log(
      colors.dim(
        '\n  A count that FELL, or an entry with no violations left, is RED on purpose: an entry\n' +
          '  above the real count pre-authorises that many future violations in that file. Lower\n' +
          '  it to the number shown, or delete the entry when it reaches 0.\n'
      )
    );
    console.log('='.repeat(60));
    return 1;
  }
  if (errors.length > 0) {
    console.log(
      colors.yellow(`⚠ ${errors.length} violation(s), ALL within the frozen P7 backlog.`)
    );
  }
  console.log('='.repeat(60));
  return 0;
}

function main() {
  const args = process.argv.slice(2);
  const strict = args.includes('--strict');
  const help = args.includes('--help') || args.includes('-h');

  if (help) {
    console.log(`
Usage: node scripts/validate-content-accuracy.js [options]

Options:
  --strict    Also validate CLI commands in translation JSON (warnings → errors)
  --help, -h  Show this help message

Rules (always enforced):
  docs-inline-cli-invalid   rdc commands in markdown prose must be valid
  invalid-rediacc-url       rediacc URLs must use valid domains
  claim-overstatement       no forensic trail, forensic-grade or unscoped hash-chained audit log

Rules (--strict only — otherwise warnings):
  json-cli-command-invalid  rdc commands in translation JSON strings must be valid
`);
    process.exit(0);
  }

  console.log(colors.dim(`Scanning content in ${ROOT_DIR}/src/...`));
  if (strict) console.log(colors.yellow('Strict mode: JSON translation CLI errors will fail CI'));

  const errors = [];
  const warnings = [];

  // Scan markdown docs — always enforced
  for (const lang of LANGUAGES) {
    const langDir = path.join(DOCS_DIR, lang);
    const slugs = listMarkdownFiles(langDir);

    for (const slug of slugs) {
      const fullPath = path.join(langDir, slug);
      const content = fs.readFileSync(fullPath, 'utf-8');
      const file = `docs/${lang}/${slug}`;

      const rdcCommands = extractInlineRdcCommands(content, file);
      validateRdcCommands(rdcCommands, errors, 'docs-inline-cli-invalid');

      const urls = extractRediaccUrls(content, file);
      validateUrls(urls, errors);

      validateClaims(content, file, errors);
    }

    const blogLangDir = path.join(BLOG_DIR, lang);
    for (const slug of listMarkdownFiles(blogLangDir)) {
      const content = fs.readFileSync(path.join(blogLangDir, slug), 'utf-8');
      validateClaims(content, `blog/${lang}/${slug}`, errors);
    }
  }

  // Scan translation JSON files
  for (const lang of LANGUAGES) {
    const jsonPath = path.join(TRANSLATIONS_DIR, `${lang}.json`);
    if (!fs.existsSync(jsonPath)) continue;

    const content = fs.readFileSync(jsonPath, 'utf-8');
    const file = `translations/${lang}.json`;

    // CLI commands: errors in strict mode, warnings otherwise
    const rdcCommands = extractJsonRdcCommands(content, file);
    const target = strict ? errors : warnings;
    validateRdcCommands(rdcCommands, target, 'json-cli-command-invalid');

    // URLs: always enforced
    const urls = extractRediaccUrls(content, file);
    validateUrls(urls, errors);

    validateClaims(content, file, errors);
  }

  process.exit(printSummary(errors, warnings));
}

// Compares real paths so a symlinked start still runs main(). A path that cannot be resolved throws, so the process exits non-zero instead of passing without checking anything.
export function invokedDirectly(argv1 = process.argv[1], metaUrl = import.meta.url) {
  if (!argv1) return false;
  return fs.realpathSync(fileURLToPath(metaUrl)) === fs.realpathSync(argv1);
}

if (invokedDirectly()) {
  main();
}

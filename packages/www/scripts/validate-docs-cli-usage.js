#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';
import {
  mergeContinuationLines,
  parseRdcCommand,
  SHELL_FENCE_LANGS,
  TARGET_DOC_CATEGORIES,
} from './lib/cli-reference-catalog.js';

// ---------------------------------------------------------------------------
// Positional-syntax pre-scan
//
// The existing `validateCodeFences` only checks shell-fenced lines that
// START with `rdc`. It misses:
//   - command substitution:  result=$(rdc machine query prod-1)
//   - inline prose:          "Claude Code runs: rdc machine query prod-1"
//   - markdown list items:   - `rdc machine query <machine>`
//   - table cells:           | ... `rdc machine query <machine>` ... |
//   - markdown fences:       copy-paste AGENTS.md templates nested in ```markdown
//
// The shared detector at scripts/lib/positional-cli-detector.ts derives the
// zero-positional command set from packages/cli/scripts/command-tree.json
// and scans any text blob for the positional-teaching pattern.
// ---------------------------------------------------------------------------

const COMMAND_TREE_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../cli/scripts/command-tree.json'
);

const FREEFORM_ARG_COMMAND_PATHS = new Set([
  'agent schema',
  'agent exec',
  'mcp capabilities',
  'mcp schema',
  'mcp exec',
  'run',
]);

const EXEMPT_COMMAND_PREFIXES = [
  'rdc auth',
  'rdc audit',
  'rdc bridge',
  'rdc organization',
  'rdc permission',
  'rdc protocol',
  'rdc queue',
  'rdc region',
  'rdc repository',
  'rdc team',
  'rdc user',
  'rdc ceph',
];

const MARKDOWN_FENCE_WHITELIST_PATTERNS = [
  /agents-md-template\.md$/,
  /ai-agents-.*\.md$/,
  /AGENTS\.md$/,
  /CLAUDE\.md$/,
];

const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const buildDetectionRegex = (commandPath) => {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  return new RegExp(`(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?=[<{\\["'a-zA-Z0-9])`);
};

const buildPlaceholderOnlyRegex = (commandPath) => {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  return new RegExp(
    `(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?=<[a-zA-Z_][\\w-]*>|\\{\\{[a-zA-Z_]\\w*\\}\\})`
  );
};

let cachedPaths = null;
const getPathsFromTree = () => {
  if (cachedPaths) return cachedPaths;
  const tree = JSON.parse(fs.readFileSync(COMMAND_TREE_PATH, 'utf-8'));
  const leaves = new Set();
  const all = new Set();
  const walk = (node, parts) => {
    if (parts.length > 0) {
      const commandPath = parts.join(' ');
      if (!FREEFORM_ARG_COMMAND_PATHS.has(commandPath)) {
        all.add(commandPath);
        const isLeaf = (node.subcommands ?? []).length === 0;
        if (isLeaf && (node.arguments ?? []).length === 0) {
          leaves.add(commandPath);
        }
      }
    }
    for (const sub of node.subcommands ?? []) walk(sub, [...parts, sub.name]);
  };
  walk(tree, []);
  cachedPaths = { leaves, all };
  return cachedPaths;
};

const scanPositional = (text) => {
  const { leaves, all } = getPathsFromTree();
  const leafEntries = [...leaves].sort((a, b) => b.length - a.length).map((p) => ({
    path: p,
    regex: buildDetectionRegex(p),
  }));
  const allEntries = [...all]
    .sort((a, b) => b.length - a.length)
    .map((p) => ({ path: p, regex: buildPlaceholderOnlyRegex(p) }));

  const violations = [];
  const lines = text.split(/\r?\n/);
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    if (!line.includes('rdc ')) continue;
    const seenPositions = new Set();
    const tryReport = (entry) => {
      const m = entry.regex.exec(line);
      if (!m) return;
      const rdcIndex = line.indexOf('rdc ', m.index);
      if (rdcIndex === -1) return;
      const trailing = line.slice(rdcIndex);
      if (EXEMPT_COMMAND_PREFIXES.some((p) => trailing.startsWith(p))) return;
      const afterPath = trailing.slice(`rdc ${entry.path} `.length);
      if (
        /^\[options\](?!\w)/.test(afterPath) ||
        /^\[command\.\.\.\](?!\w)/.test(afterPath) ||
        /^\[command\](?!\w)/.test(afterPath) ||
        /^\[komut\.\.\.\](?!\w)/.test(afterPath) ||
        /^\[seçenekler\](?!\w)/.test(afterPath)
      ) {
        return;
      }
      const posKey = `${rdcIndex}`;
      if (seenPositions.has(posKey)) return;
      seenPositions.add(posKey);
      violations.push({
        commandPath: entry.path,
        match: trailing.slice(0, Math.min(trailing.length, 80)),
        line: li + 1,
      });
    };
    for (const entry of leafEntries) tryReport(entry);
    for (const entry of allEntries) tryReport(entry);
  }
  return violations;
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DOCS_DIR = path.resolve(__dirname, '../src/content/docs');
const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function listMarkdownFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((file) => file.endsWith('.md'));
}

function getTargetSlugs() {
  const slugs = [];
  for (const slug of listMarkdownFiles(path.join(DOCS_DIR, 'en'))) {
    const fullPath = path.join(DOCS_DIR, 'en', slug);
    const raw = fs.readFileSync(fullPath, 'utf-8');
    const parsed = matter(raw);
    const category = parsed.data?.category;
    // Skip auto-generated docs (validated by validate-cli-docs.js)
    if (parsed.data?.generated) continue;
    if (typeof category === 'string' && TARGET_DOC_CATEGORIES.has(category)) {
      slugs.push(slug);
    }
  }
  return slugs;
}

function addError(errors, rule, file, line, message, commandText, suggestion) {
  errors.push({ rule, file, line, message, commandText, suggestion });
}

function formatError(parsed) {
  switch (parsed.reason) {
    case 'unknown-global-option':
      return `Unknown global option: ${parsed.flag}`;
    case 'unknown-command':
      return `Unknown command path near: ${parsed.near}`;
    case 'unknown-option':
      return `Unknown option ${parsed.flag} for command "rdc ${parsed.commandPath}"`;
    case 'missing-required-args':
      return `Missing required positional arguments for "rdc ${parsed.commandPath}"`;
    case 'missing-reference-entry':
      return `No CLI reference entry for "rdc ${parsed.commandPath}"`;
    case 'excess-positional-args':
      return `Unexpected positional argument(s) for "rdc ${parsed.commandPath}" (expected ${parsed.expected}, got ${parsed.actual})`;
    case 'missing-mandatory-option':
      return `Missing mandatory option ${parsed.flag} for "rdc ${parsed.commandPath}"`;
    default:
      return `Invalid command usage (${parsed.reason || 'unknown'})`;
  }
}

function suggestedFix(parsed) {
  if (parsed.reason === 'unknown-option') {
    return `Remove or replace unsupported option ${parsed.flag}`;
  }
  if (parsed.reason === 'unknown-command') {
    return 'Use a command from cli-application reference';
  }
  if (parsed.reason === 'missing-required-args') {
    return 'Provide all required positional arguments';
  }
  if (parsed.reason === 'missing-reference-entry') {
    return 'Regenerate CLI docs and ensure command exists in reference';
  }
  if (parsed.reason === 'excess-positional-args') {
    return 'Convert positional arguments to named options (e.g. --name)';
  }
  if (parsed.reason === 'missing-mandatory-option') {
    return `Add the required ${parsed.flag} option`;
  }
  return null;
}

function validateCodeFences(content, file, errors) {
  // First pass: full-content positional-syntax scan. Catches wrapped forms
  // (command substitution, inline prose, list items, table cells, markdown
  // fences) that the per-line shell-fence scanner below misses.
  for (const hit of scanPositional(content)) {
    addError(
      errors,
      'positional-syntax',
      file,
      hit.line,
      `Positional syntax for "rdc ${hit.commandPath}" — use named options instead`,
      hit.match,
      `Rewrite with --name or the command's documented flags (issue #446)`
    );
  }

  const lines = content.split(/\r?\n/);
  let inFence = false;
  const enterMarkdownFences = MARKDOWN_FENCE_WHITELIST_PATTERNS.some((p) => p.test(file));

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    if (line.startsWith('```')) {
      const lang = line.slice(3).trim().toLowerCase();
      const isShell = SHELL_FENCE_LANGS.has(lang);
      const isTemplateFence = enterMarkdownFences && (lang === 'markdown' || lang === '');
      inFence = isShell || isTemplateFence;
      continue;
    }

    if (!inFence) continue;
    if (!line || line.startsWith('#') || !line.startsWith('rdc')) continue;

    const merged = mergeContinuationLines(lines, i);
    let commandText = merged.command;
    i = merged.endIndex;

    // Normalise placeholders to dummy values so they're validated as real commands
    // instead of silently skipped. This catches wrong flag/positional syntax even
    // when the example uses <placeholder> tokens.
    commandText = commandText.replace(/<([a-zA-Z][\w-]*)>/g, 'PLACEHOLDER');

    const parsed = parseRdcCommand(commandText);
    if (!parsed.ok && parsed.reason !== 'not-rdc') {
      addError(
        errors,
        'docs-cli-command-invalid',
        file,
        i + 1,
        formatError(parsed),
        commandText,
        suggestedFix(parsed)
      );
    }
  }
}

function groupByRule(errors) {
  const grouped = new Map();
  for (const error of errors) {
    if (!grouped.has(error.rule)) grouped.set(error.rule, []);
    grouped.get(error.rule).push(error);
  }
  return grouped;
}

function printSummary(errors) {
  console.log(colors.bold('Docs CLI Usage Validation'));
  console.log('='.repeat(60));

  if (errors.length === 0) {
    console.log(colors.green('✓ All targeted docs command examples are valid.'));
    console.log('='.repeat(60));
    return 0;
  }

  const grouped = groupByRule(errors);
  for (const [rule, items] of grouped.entries()) {
    console.log(colors.red(`\n[${rule}] (${items.length} errors)`));
    console.log(colors.dim('-'.repeat(40)));
    for (const item of items) {
      console.log(colors.red(`  ✗ ${item.file}:${item.line}`));
      console.log(colors.dim(`    ${item.message}`));
      console.log(colors.cyan(`    → ${item.commandText}`));
      if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
    }
  }

  console.log('\n' + '='.repeat(60));
  console.log(colors.red(`✗ Validation failed (${errors.length} errors)`));
  console.log('='.repeat(60));
  return 1;
}

function main() {
  const targetSlugs = getTargetSlugs();
  const errors = [];

  for (const lang of LANGUAGES) {
    for (const slug of targetSlugs) {
      const fullPath = path.join(DOCS_DIR, lang, slug);
      if (!fs.existsSync(fullPath)) continue;

      const raw = fs.readFileSync(fullPath, 'utf-8');
      const file = `docs/${lang}/${slug}`;
      validateCodeFences(raw, file, errors);
    }
  }

  process.exit(printSummary(errors));
}

main();

#!/usr/bin/env npx tsx
/**
 * Validates CLI command examples across the monorepo against the command-tree.json ground truth.
 *
 * Complements packages/www/scripts/validate-docs-cli-usage.js which only covers www docs.
 * This script covers: CLAUDE.md, skill files, CLI help text, i18n locales, Go source, and other docs.
 *
 * Usage: npx tsx scripts/validate-cli-examples.ts
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { glob } from 'glob';

// Reuse the existing validation library from www package
import {
  mergeContinuationLines,
  parseRdcCommand,
  SHELL_FENCE_LANGS,
} from '../packages/www/scripts/lib/cli-reference-catalog.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// ---------------------------------------------------------------------------
// File targets (paths relative to repo root)
// ---------------------------------------------------------------------------
const TARGET_GLOBS = [
  // Root project docs
  'CLAUDE.md',
  'docs/**/*.md',
  '.claude/skills/rdc/*.md',

  // CLI source (help text strings)
  'packages/cli/src/cli.ts',
  'packages/cli/src/commands/**/*.ts',

  // i18n: only English locales (non-English mirror English and contain translated
  // prose that produces false positives; the i18n sync workflow propagates fixes)
  'packages/cli/src/i18n/locales/en/cli.json',
  'private/account/web/src/i18n/locales/en/**/*.json',

  // Account submodule
  'private/account/web/src/**/*.tsx',
  'private/account/CLAUDE.md',

  // Renet Go source
  'private/renet/cmd/renet/dev.go',
  'private/renet/cmd/renet/dev_init.go',

  // www: AGENTS.md, marp presentations, Astro components, templates
  // (www docs markdown is covered by validate-docs-cli-usage.js in the www package)
  'packages/www/public/AGENTS.md',
  'packages/www/src/marp/**/*.md',
  'packages/www/src/components/**/*.astro',
  'packages/json/templates/**/*.md',
];

// ---------------------------------------------------------------------------
// Placeholder normalisation
// ---------------------------------------------------------------------------

/**
 * Replace <placeholder> and {{template}} tokens with concrete dummy values
 * so that parseRdcCommand can properly validate the command structure.
 */
function normalisePlaceholders(text: string): string {
  let result = text;

  // Replace {{template}} vars (i18n interpolation)
  result = result.replace(/\{\{(\w+)\}\}/g, 'PLACEHOLDER');

  // Replace Go fmt verbs
  result = result.replace(/%[sdvfq]/g, 'PLACEHOLDER');

  // Replace <placeholder> tokens with dummy values
  result = result.replace(/<([a-zA-Z][\w-]*)>/g, 'PLACEHOLDER');

  // Remove [optional] tokens (e.g., [repo]) that aren't flags
  // Keep [--flag] and [-f] patterns intact
  result = result.replace(/\[([a-zA-Z][\w-]*)\]/g, '');

  return result;
}

// ---------------------------------------------------------------------------
// Context-aware skipping
// ---------------------------------------------------------------------------

/** Lines matching these patterns are intentionally showing wrong syntax. */
const SKIP_CONTEXT_PATTERNS = [
  /instead of/i,
  /\bNOT\b.*\bthis\b/i,
  /\bwrong\b/i,
  /\bdon['']?t use\b/i,
  /\bnever use\b/i,
];

function isSkippableContext(lines: string[], lineIndex: number): boolean {
  for (let i = Math.max(0, lineIndex - 2); i <= lineIndex; i++) {
    const line = lines[i];
    if (SKIP_CONTEXT_PATTERNS.some((pat) => pat.test(line))) {
      return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Error tracking
// ---------------------------------------------------------------------------

interface Violation {
  file: string;
  line: number;
  command: string;
  reason: string;
  detail: string;
}

function formatParsedError(parsed: ReturnType<typeof parseRdcCommand>): string {
  switch (parsed.reason) {
    case 'unknown-global-option':
      return `Unknown global option: ${parsed.flag}`;
    case 'unknown-command':
      return `Unknown command near: ${parsed.near}`;
    case 'unknown-option':
      return `Unknown option ${parsed.flag} for "rdc ${parsed.commandPath}"`;
    case 'missing-required-args':
      return `Missing required positional args for "rdc ${parsed.commandPath}"`;
    case 'missing-reference-entry':
      return `No CLI reference entry for "rdc ${parsed.commandPath}"`;
    case 'excess-positional-args':
      return `Excess positional arg(s) for "rdc ${parsed.commandPath}" (expected ${parsed.expected}, got ${parsed.actual})`;
    case 'missing-mandatory-option':
      return `Missing mandatory option ${parsed.flag} for "rdc ${parsed.commandPath}"`;
    default:
      return `Invalid command (${parsed.reason || 'unknown'})`;
  }
}

// ---------------------------------------------------------------------------
// Extractors
// ---------------------------------------------------------------------------

/**
 * Extract rdc commands from markdown shell code fences.
 */
function extractFromMarkdown(
  content: string,
  filePath: string,
  violations: Violation[]
): void {
  const lines = content.split(/\r?\n/);
  let inFence = false;

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();

    if (trimmed.startsWith('```')) {
      if (inFence) {
        inFence = false;
        continue;
      }
      const lang = trimmed.slice(3).trim().toLowerCase();
      inFence = SHELL_FENCE_LANGS.has(lang);
      continue;
    }

    if (!inFence) continue;
    if (!trimmed || trimmed.startsWith('#')) continue;

    // Strip leading $ prompt
    let command = trimmed;
    if (command.startsWith('$ ')) command = command.slice(2);

    if (!command.startsWith('rdc ') && command !== 'rdc') continue;
    if (isSkippableContext(lines, i)) continue;

    const merged = mergeContinuationLines(lines, i);
    let mergedCommand = merged.command;
    if (mergedCommand.startsWith('$ ')) mergedCommand = mergedCommand.slice(2);
    i = merged.endIndex;

    // Pass surrounding lines for cloud-only context detection
    const ctx = lines.slice(Math.max(0, i - 10), i + 1);
    validateCommand(mergedCommand, filePath, i + 1, violations, ctx);
  }
}

/**
 * Extract rdc commands from TypeScript source files (help text strings).
 */
function extractFromTypeScript(
  content: string,
  filePath: string,
  violations: Violation[]
): void {
  const lines = content.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Match patterns like:  $ rdc ...  in help text strings and JSX display
    const rdcMatches = line.matchAll(/\$\s+rdc\s+[^\n`'"]+/g);
    for (const match of rdcMatches) {
      let command = match[0].replace(/^\$\s+/, '').trim();
      // Strip everything from ${t( onwards (i18n template expressions)
      command = command.replace(/\s*\$\{.*$/, '').trim();
      // Strip trailing template literal/string artifacts
      command = command.replace(/\s*`.*$/, '').trim();
      // Strip HTML/XML tags (Astro, JSX)
      command = command.replace(/<\/?\w[^>]*>.*$/g, '').trim();
      if (!command.startsWith('rdc') || command.length < 5) continue;
      if (isSkippableContext(lines, i)) continue;

      validateCommand(command, filePath, i + 1, violations);
    }
  }
}

/**
 * Known top-level rdc subcommands for filtering real commands from prose.
 */
const KNOWN_SUBCOMMANDS = new Set([
  'agent', 'auth', 'audit', 'bridge', 'ceph', 'config', 'datastore',
  'doctor', 'machine', 'mcp', 'ops', 'organization', 'permission',
  'protocol', 'queue', 'region', 'repo', 'repository', 'shortcuts',
  'storage', 'subscription', 'team', 'term', 'update', 'user', 'vscode',
  'run',
]);

/**
 * Check if a string looks like a real CLI command (not prose that mentions rdc).
 * Commands start with `rdc <known-subcommand>` and don't contain non-Latin prose.
 */
function looksLikeCommand(text: string): boolean {
  const parts = text.trim().split(/\s+/);
  if (parts.length < 2 || parts[0] !== 'rdc') return false;

  // Second token must be a known subcommand
  if (!KNOWN_SUBCOMMANDS.has(parts[1])) return false;

  // Skip if the command text contains non-ASCII characters (translated prose)
  // Allow a few specific Unicode chars that might appear in placeholder names
  if (/[^\x00-\x7F]/.test(text.replace(/<[^>]+>/g, '').replace(/\{\{[^}]+\}\}/g, ''))) {
    return false;
  }

  return true;
}

/**
 * Extract rdc commands from JSON i18n files.
 *
 * JSON string values may contain command examples in patterns like:
 *   "Run: rdc repo up --name my-app -m server-1"
 *   "Example:\\n  rdc machine query --name server-1"
 *
 * We parse the full JSON, walk all string values, split on \\n boundaries,
 * and validate each line that looks like a CLI command.
 */
function extractFromJSON(
  content: string,
  filePath: string,
  violations: Violation[]
): void {
  let json: unknown;
  try {
    json = JSON.parse(content);
  } catch {
    return; // skip unparseable
  }

  // Build a line map so we can report approximate line numbers
  const lines = content.split(/\r?\n/);

  function findLineForKey(keyPath: string[]): number {
    // Simple heuristic: search for the last key in the path
    const lastKey = keyPath[keyPath.length - 1];
    const pattern = `"${lastKey}"`;
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes(pattern)) return i + 1;
    }
    return 0;
  }

  function walkValue(value: unknown, keyPath: string[]): void {
    if (typeof value === 'string') {
      // After JSON.parse, \\n in JSON becomes \n in JS. Split on actual newlines.
      const segments = value.split('\n');
      for (const segment of segments) {
        let trimmed = segment.trim();
        if (trimmed.startsWith('$ ')) trimmed = trimmed.slice(2).trim();
        if (!trimmed.startsWith('rdc ')) continue;

        // Strip trailing punctuation/formatting
        trimmed = trimmed.replace(/['"}\].,;:!]+$/, '').trim();

        if (!looksLikeCommand(trimmed)) continue;

        const line = findLineForKey(keyPath);
        validateCommand(trimmed, filePath, line, violations);
      }
    } else if (Array.isArray(value)) {
      for (let i = 0; i < value.length; i++) {
        walkValue(value[i], [...keyPath, String(i)]);
      }
    } else if (value && typeof value === 'object') {
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        walkValue(v, [...keyPath, k]);
      }
    }
  }

  walkValue(json, []);
}

/**
 * Extract rdc commands from Go source files (string literals).
 */
function extractFromGo(
  content: string,
  filePath: string,
  violations: Violation[]
): void {
  const lines = content.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Match rdc commands in Go string literals
    const rdcMatches = line.matchAll(/(?:"|`)([^"`]*rdc\s+[^"`]*)/g);
    for (const match of rdcMatches) {
      const fragment = match[1];
      // Split by \n for multi-line Go strings
      const parts = fragment.split('\\n');
      for (const part of parts) {
        let command = part.trim();
        // Strip leading whitespace
        command = command.replace(/^\s+/, '');
        if (!command.startsWith('rdc ')) continue;
        // Strip trailing inline comment
        command = command.replace(/\s{2,}#\s.*$/, '').trim();
        if (!looksLikeCommand(command)) continue;
        if (isSkippableContext(lines, i)) continue;

        validateCommand(command, filePath, i + 1, violations);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function validateCommand(
  rawCommand: string,
  filePath: string,
  line: number,
  violations: Violation[],
  contextLines?: string[]
): void {
  const normalised = normalisePlaceholders(rawCommand);

  // Skip pipe chains and redirections (just validate the rdc part)
  const pipeIndex = normalised.indexOf(' | ');
  const command = pipeIndex !== -1 ? normalised.slice(0, pipeIndex).trim() : normalised;

  // Skip if the command has shell variables or other non-parseable tokens
  if (/\$[A-Z_]/.test(command)) return;

  // Skip comma-separated command lists like "rdc repo up, rdc repo down"
  if (/,\s*rdc\s/.test(command)) return;

  // Skip em-dash separated text (prose, not commands)
  if (/\s[\u2014\u2013]\s/.test(command) || /\s--\s[a-z]/.test(command)) return;

  // Hidden or planned commands not yet in command-tree.json -- skip
  if (/^rdc\s+run\s/.test(command)) return;
  if (/^rdc\s+repo\s+snapshot\s/.test(command)) return;

  // Cloud-adapter-only commands should not appear in general docs without
  // qualification. Flag them in files that target local-adapter users.
  // Commands that require cloud adapter (authService.requireAuth() or provider.isCloud guard).
  // provision/deprovision use OpenTofu with local config -- NOT cloud-only.
  const CLOUD_ONLY_PATTERNS = [
    /^rdc\s+auth\s/,
    /^rdc\s+machine\s+test-connection\b/,
    /^rdc\s+machine\s+assign-bridge\b/,
    /^rdc\s+organization\s/,
    /^rdc\s+user\s/,
    /^rdc\s+team\s/,
    /^rdc\s+permission\s/,
    /^rdc\s+region\s/,
    /^rdc\s+bridge\s/,
    /^rdc\s+queue\s/,
    /^rdc\s+ceph\s/,
    /^rdc\s+audit\s/,
  ];
  // Files that are general-purpose (not cloud-specific docs). Cloud-only
  // commands in these files are flagged.
  const GENERAL_AUDIENCE_PATTERNS = [
    /CLAUDE\.md$/,
    /skills\/rdc\//,
    /AGENTS\.md$/,
    /cheat-sheet/,
    /templates\//,
  ];
  const isGeneralFile = GENERAL_AUDIENCE_PATTERNS.some((p) => p.test(filePath));
  if (isGeneralFile) {
    const cloudMatch = CLOUD_ONLY_PATTERNS.find((p) => p.test(command));
    if (cloudMatch) {
      // Allow cloud-only commands if the surrounding context marks them as cloud
      const hasCloudContext = (contextLines ?? []).some((l: string) =>
        /cloud|Cloud|CLOUD/.test(l)
      );
      if (!hasCloudContext) {
        violations.push({
          file: filePath,
          line,
          command: rawCommand,
          reason: 'cloud-only-in-general-docs',
          detail: `Cloud-adapter-only command in general-audience file`,
        });
        return;
      }
    }
  }

  const parsed = parseRdcCommand(command);
  if (parsed.ok) return;
  if (parsed.reason === 'not-rdc') return;

  // missing-reference-entry is expected for undocumented commands -- skip
  if (parsed.reason === 'missing-reference-entry') return;

  violations.push({
    file: filePath,
    line,
    command: rawCommand,
    reason: parsed.reason || 'unknown',
    detail: formatParsedError(parsed),
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const colors = {
  red: (s: string) => `\x1b[31m${s}\x1b[0m`,
  green: (s: string) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s: string) => `\x1b[36m${s}\x1b[0m`,
  dim: (s: string) => `\x1b[2m${s}\x1b[0m`,
  bold: (s: string) => `\x1b[1m${s}\x1b[0m`,
};

async function main(): Promise<void> {
  const violations: Violation[] = [];

  // Resolve all target files
  const files: string[] = [];
  for (const pattern of TARGET_GLOBS) {
    const matches = await glob(pattern, { cwd: ROOT, absolute: false });
    files.push(...matches);
  }

  // Deduplicate
  const uniqueFiles = [...new Set(files)].sort();

  console.log(colors.dim(`Scanning ${uniqueFiles.length} files...`));

  for (const relPath of uniqueFiles) {
    const absPath = path.join(ROOT, relPath);
    if (!fs.existsSync(absPath)) continue;

    const content = fs.readFileSync(absPath, 'utf-8');
    const ext = path.extname(relPath);

    if (ext === '.md') {
      extractFromMarkdown(content, relPath, violations);
    } else if (ext === '.ts' || ext === '.tsx' || ext === '.astro') {
      extractFromTypeScript(content, relPath, violations);
    } else if (ext === '.json') {
      extractFromJSON(content, relPath, violations);
    } else if (ext === '.go') {
      extractFromGo(content, relPath, violations);
    }
  }

  // Print results
  console.log(colors.bold('CLI Examples Validation'));
  console.log('='.repeat(60));

  if (violations.length === 0) {
    console.log(colors.green('All CLI command examples are valid.'));
    console.log('='.repeat(60));
    process.exit(0);
  }

  // Group by file
  const byFile = new Map<string, Violation[]>();
  for (const v of violations) {
    if (!byFile.has(v.file)) byFile.set(v.file, []);
    byFile.get(v.file)!.push(v);
  }

  for (const [file, items] of byFile) {
    console.log(colors.red(`\n${file} (${items.length} errors)`));
    console.log(colors.dim('-'.repeat(40)));
    for (const item of items) {
      console.log(colors.red(`  L${item.line}: ${item.detail}`));
      console.log(colors.cyan(`    ${item.command}`));
    }
  }

  console.log('\n' + '='.repeat(60));
  console.log(colors.red(`Validation failed (${violations.length} errors)`));
  console.log('='.repeat(60));
  process.exit(1);
}

main();

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
// Curated contract examples (also parsed and gated by the contract generator;
// validated here too so this script stays the one place that proves every
// `rdc …` line in the repo against the command tree)
import { COMMAND_EXAMPLES } from '../packages/cli/src/config/command-docs.ts';
// Reuse the existing validation library from www package
import {
  mergeContinuationLines,
  parseRdcCommand,
  SHELL_FENCE_LANGS,
} from '../packages/www/scripts/lib/cli-reference-catalog.js';

// Shared stale-command-path detector (commands that no longer exist)
import { scanShellText, scanSourceOptions, scanSourceText } from './lib/command-path-checker.ts';
// Shared positional-syntax detector (zero-positional commands)
import { scanText as scanPositional } from './lib/positional-cli-detector.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// ---------------------------------------------------------------------------
// File targets (paths relative to repo root)
// ---------------------------------------------------------------------------
const TARGET_GLOBS = [
  // Root project docs
  'CLAUDE.md',
  'docs/**/*.{md,mdx}',
  // The tracked agent notes tree follows docs/ here, and this is NOT optional
  // coverage. Plans are written in `rdc` commands, and this gate has already
  // earned its keep on one: PLAN-localize-cheat-sheet-rendering.md cited two
  // invocations that the parser REJECTS, and this scan is what caught them.
  // Moving plans out of docs/ without moving the glob would silence the gate on
  // exactly the file class where it has a proven catch -- a gate that keeps
  // passing because it stopped looking.
  //
  // Yes, this surfaces findings from session notes. That is the point: a plan
  // teaching a command that does not run is how the next session learns it.
  'agent/**/*.{md,mdx}',
  '.claude/skills/rdc/*.md',

  // CLI source (help text strings)
  'packages/cli/src/cli.ts',
  'packages/cli/src/commands/**/*.ts',
  'packages/cli/templates/**/docker-compose.yml',

  // i18n locales — ALL languages (positional-syntax drift surfaces in
  // translated `rdc …` fragments even when the surrounding prose is
  // correctly translated).
  // All 13 locales. et/ko/pt/it were absent and therefore never validated;
  // measured clean at the time they were added, so this closes a latent hole
  // rather than importing a backlog.
  'packages/cli/src/i18n/locales/{ar,de,en,es,et,fr,it,ja,ko,pt,ru,tr,zh}/cli.json',
  'private/account/web/src/i18n/locales/en/**/*.json',

  // Surfaces that carried real stale commands with NO gate at all. `.cast`
  // recordings are deliberately absent: validate-tutorial-cast-output.js
  // already gates those, and double-gating one surface with two engines means
  // two suppression records to keep honest.
  'packages/www/src/content/blog/**/*.{md,mdx}',
  'private/account/web/src/data/study-content/**/*.ts',
  // NOT tutorial-storyboard/**: each step carries BOTH `command` (an
  // abbreviated display label, e.g. "rdc machine add") and `commandFull` (the
  // runnable form with its arguments). This extractor reads raw strings and
  // cannot tell the two apart, so it reports the label as missing positional
  // args. The storyboards' real stale commands WERE fixed in this campaign;
  // gating them needs a field-aware extractor that reads only `commandFull`.
  // NOT exam-question-bank.json: its answers discuss commands in prose
  // ("rdc repo delete cryptographically erases the LUKS volume, and ..."),
  // which this extractor reads as a command with 14 positional args. Precision
  // over recall -- a gate that cries wolf gets suppressed, which is the exact
  // failure this campaign removed. Its one real defect is fixed by hand; gating
  // it needs an extractor that distinguishes a command from a sentence.

  // Account submodule
  'private/account/web/src/**/*.tsx',
  'private/account/CLAUDE.md',

  // Renet Go source
  'private/renet/cmd/renet/dev.go',
  'private/renet/cmd/renet/dev_init.go',

  // www: AGENTS.md, marp presentations, Astro components, templates
  // (www docs markdown is covered by validate-docs-cli-usage.js in the www package)
  'packages/www/public/AGENTS.md',
  'packages/www/src/marp/**/*.{md,mdx}',
  'packages/www/src/components/**/*.astro',
  'packages/json/templates/**/*.{md,mdx}',
];

/**
 * Files scanned for STALE COMMAND PATHS (commands that no longer exist).
 *
 * Deliberately wider than TARGET_GLOBS, which only reaches `commands/**` and so
 * never saw the error messages in `services/**` naming `rdc config machine setup`.
 * The other extractors stay on their narrower globs: they run the full option
 * validator, which needs a CLI reference entry, whereas this check only resolves
 * the command path and is safe to point at all source.
 */
const COMMAND_PATH_GLOBS = [
  'packages/cli/src/**/*.ts',
  'packages/shared/src/**/*.ts',
  'private/renet/cmd/**/*.go',
  'private/renet/pkg/**/*.go',
  '*.sh',
  'scripts/**/*.sh',
  '.ci/scripts/**/*.sh',
];

/** Tests assert on message text, including deliberately-wrong fixtures. */
const COMMAND_PATH_IGNORE = /(?:__tests__|\.test\.ts$|\.spec\.ts$)/;

/**
 * Files a scan must NOT read, because their content is EVIDENCE rather than instruction.
 *
 * BLOCKER: a verdict document quotes the broken syntax it is reporting. The P4 gate
 * review's design-tree finding IS the line `rdc ops   up down …` plus an explanation that
 * it parses as `rdc ops up` — so scanning it flags the review for containing the evidence
 * that makes the review true. Its findings are also not ours to edit: it is an independent
 * verdict, and rewriting it to satisfy a validator would destroy the only thing it is for.
 * Any FIX it prompted lands as a later commit, never as an edit to the report.
 */
/**
 * BLOCKER: these three carry KNOWN-BAD CLI syntax as their payload, not as advice.
 * `PLAN-lint-rule-matrix-probe.md` tabulates the fixture that each lint rule must
 * report on — `rdc repo list <name>` and `rdc config current <name>` are there
 * precisely BECAUSE they are positional violations, and the table is what proves
 * those two rules can fire. The two agent-hint plans hold the matcher's sample
 * corpus, where an entry is a verbatim operator sentence ("rdc config remote
 * enable fails with Decryption failed...") that happens to open with a command
 * name. Editing any of them to satisfy this validator would change the fixture or
 * the corpus, i.e. destroy the evidence, exactly as the P4 gate-review entry above
 * describes. Drop an entry if its document stops carrying bad syntax on purpose.
 */
const EXCLUDED_FILES = new Set<string>([
  'docs/design/spec/11-p4-gate-review.md',
  'agent/PLAN-lint-rule-matrix-probe.md',
  'agent/PLAN-agent-hints-implementation.md',
  'agent/PLAN-agent-hints-in-stop-hook.md',
]);

/**
 * Files that legitimately contain AGENTS.md-style copy-paste templates
 * inside ```markdown fences. Shell-fence-only scanning misses these. The
 * scanner enters the markdown fence for files matching these path hints.
 */
const MARKDOWN_FENCE_WHITELIST_PATTERNS = [
  /agents-md-template\.md$/,
  /ai-agents-.*\.md$/,
  /AGENTS\.md$/,
  /CLAUDE\.md$/,
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
 * Also enters ```markdown fences for AGENTS.md-template files that
 * deliberately nest CLI examples inside a markdown fence for copy-paste.
 */
function extractFromMarkdown(content: string, filePath: string, violations: Violation[]): void {
  const lines = content.split(/\r?\n/);
  let inFence = false;
  const enterMarkdownFences = MARKDOWN_FENCE_WHITELIST_PATTERNS.some((p) => p.test(filePath));

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();

    if (trimmed.startsWith('```')) {
      if (inFence) {
        inFence = false;
        continue;
      }
      const lang = trimmed.slice(3).trim().toLowerCase();
      const isShell = SHELL_FENCE_LANGS.has(lang);
      const isTemplateFence = enterMarkdownFences && (lang === 'markdown' || lang === '');
      inFence = isShell || isTemplateFence;
      continue;
    }

    if (!inFence) {
      // Even outside fences, we still want to catch positional-syntax
      // violations in prose (e.g., `- \`rdc machine query <machine>\``,
      // `Claude Code runs: rdc machine query prod-1`, table cells).
      checkPositionalSyntax(lines[i], filePath, i + 1, violations, lines);
      continue;
    }
    if (!trimmed || trimmed.startsWith('#')) {
      // Comments inside shell fences should still be checked for
      // positional syntax (they frequently contain example commands).
      checkPositionalSyntax(lines[i], filePath, i + 1, violations, lines);
      continue;
    }

    // Catch wrapped forms inside fences: result=$(rdc ...), `rdc ...`, etc.
    // These line-level checks fire BEFORE the strict parser path below.
    checkPositionalSyntax(lines[i], filePath, i + 1, violations, lines);

    // Strip leading $ prompt
    let command = trimmed;
    if (command.startsWith('$ ')) command = command.slice(2);
    command = normaliseInvocation(command);

    if (!command.startsWith('rdc ') && command !== 'rdc') continue;
    if (isSkippableContext(lines, i)) continue;

    const merged = mergeContinuationLines(lines, i);
    let mergedCommand = merged.command;
    if (mergedCommand.startsWith('$ ')) mergedCommand = mergedCommand.slice(2);
    mergedCommand = normaliseInvocation(mergedCommand);
    i = merged.endIndex;

    validateCommand(mergedCommand, filePath, i + 1, violations);
  }
}

/**
 * Normalise the WRAPPER invocation to the bare binary.
 *
 * ★ CLAUDE.md's own convention MANDATES `./rdc.sh …`, and this scanner's line filter was
 * `startsWith('rdc ')` — so it read the file and walked straight past every line the file
 * is made of. It reported zero because it had looked at nothing.
 *
 * check-cli-docs.ts:624 already carries a comment describing this exact class ("failed
 * startsWith('rdc'), and WAS SILENTLY DISCARDED. The scanner reported zero and had looked
 * at nothing. Half a fix is a fresh blind spot."). Someone diagnosed it, fixed ONE scanner,
 * and never applied it to the sibling. So: both wrappers, one place, both scanners.
 */
const WRAPPER_ONLY_FLAGS = /^\s*--(?:native|dev)\b/;

function normaliseInvocation(command: string): string {
  const m = /^(?:\.\/)?rdc\.sh(?=\s|$)/.exec(command);
  if (!m) return command;
  let rest = command.slice(m[0].length);
  // `./rdc.sh --native` / `--dev` are consumed BY THE WRAPPER and never reach the
  // CLI, so passing them to the parser would invent a new false-positive class while
  // fixing a blind spot. See rdc.sh:82.
  let stripped = true;
  while (stripped) {
    stripped = false;
    const f = WRAPPER_ONLY_FLAGS.exec(rest);
    if (f) {
      rest = rest.slice(f[0].length);
      stripped = true;
    }
  }
  return `rdc${rest}`;
}

/**
 * Scan a single line for positional-syntax violations — handles wrapped
 * forms that `extractFromMarkdown`'s strict line-start filter misses
 * (command substitution, inline prose, markdown list items, table cells).
 */
function checkPositionalSyntax(
  line: string,
  filePath: string,
  lineNumber: number,
  violations: Violation[],
  contextLines: string[]
): void {
  if (!line.includes('rdc ')) return;
  if (isSkippableContext(contextLines, lineNumber - 1)) return;
  const hits = scanPositional(line);
  for (const hit of hits) {
    violations.push({
      file: filePath,
      line: lineNumber,
      command: hit.match,
      reason: 'positional-syntax',
      detail: `Positional syntax for "rdc ${hit.commandPath}" — use named options instead`,
    });
  }
}

/**
 * Extract rdc commands from TypeScript source files (help text strings).
 */
function extractFromTypeScript(content: string, filePath: string, violations: Violation[]): void {
  const lines = content.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Match patterns like:  $ rdc ...  in help text strings and JSX display
    const rdcMatches = line.matchAll(/\$\s+(?:\.\/)?rdc(?:\.sh)?\s+[^\n`'"]+/g);
    for (const match of rdcMatches) {
      let command = match[0].replace(/^\$\s+/, '').trim();
      // Strip everything from ${t( onwards (i18n template expressions)
      command = command.replace(/\s*\$\{.*$/, '').trim();
      // Strip trailing template literal/string artifacts
      command = command.replace(/\s*`.*$/, '').trim();
      // Strip HTML/XML tags (Astro, JSX)
      command = command.replace(/<\/?\w[^>]*>.*$/g, '').trim();
      command = normaliseInvocation(command);
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
  'agent',
  'auth',
  'audit',
  'bridge',
  'ceph',
  'config',
  'datastore',
  'doctor',
  'machine',
  'mcp',
  'ops',
  'organization',
  'permission',
  'protocol',
  'queue',
  'region',
  'repo',
  'repository',
  'shortcuts',
  'storage',
  'subscription',
  'team',
  'term',
  'update',
  'user',
  'vscode',
  'run',
]);

/** Returns true if the string contains any character with code point above 127. */
function containsNonAscii(str: string): boolean {
  for (let i = 0; i < str.length; i++) {
    if (str.charCodeAt(i) > 127) return true;
  }
  return false;
}

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
  const cleaned = text.replace(/<[^>]+>/g, '').replace(/\{\{[^}]+\}\}/g, '');
  if (containsNonAscii(cleaned)) {
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
function extractFromJSON(content: string, filePath: string, violations: Violation[]): void {
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
function extractFromGo(content: string, filePath: string, violations: Violation[]): void {
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
  violations: Violation[]
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

  // `rdc run` is a real command, deliberately hidden from help and MCP (it is
  // the Rediaccfile escape hatch for debugging), so it is absent from
  // command-tree.json and cannot be parsed. The skip is justified.
  if (/^rdc\s+run\s/.test(command)) return;

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

/**
 * Validate the curated COMMAND_EXAMPLES registry (the source of the contract's
 * worked examples and the CLI help "Examples:" blocks) through the same parser
 * as every other example in the repo. The contract generator gates these too;
 * this keeps them covered even when nothing regenerates.
 */
function extractFromCommandDocs(violations: Violation[]): void {
  const relPath = 'packages/cli/src/config/command-docs.ts';
  const content = fs.readFileSync(path.join(ROOT, relPath), 'utf-8');
  const lines = content.split(/\r?\n/);
  const findLine = (command: string): number => {
    const index = lines.findIndex((l) => l.includes(command));
    return index === -1 ? 1 : index + 1;
  };

  for (const examples of Object.values(COMMAND_EXAMPLES)) {
    for (const example of examples) {
      validateCommand(example.command, relPath, findLine(example.command), violations);
    }
  }
}

/**
 * Whole-file positional-syntax scan. Uses the shared detector to catch any
 * `rdc <zero-positional-cmd> <token>` pattern anywhere in the file.
 */
function scanFileForPositional(content: string, filePath: string, violations: Violation[]): void {
  if (!content.includes('rdc ')) return;
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    if (isSkippableContext(lines, i)) continue;
    const hits = scanPositional(lines[i]);
    for (const hit of hits) {
      violations.push({
        file: filePath,
        line: i + 1,
        command: hit.match,
        reason: 'positional-syntax',
        detail: `Positional syntax for "rdc ${hit.commandPath}" — use named options instead (issue #446)`,
      });
    }
  }
}

/**
 * Scan source and shell for references to commands that no longer exist.
 *
 * Separate from the extractors above because it resolves only the command PATH
 * against command-tree.json — no option or reference-entry validation — which is
 * what lets it run over every source file rather than the curated doc globs.
 */
async function scanForStaleCommandPaths(violations: Violation[]): Promise<void> {
  const files: string[] = [];
  for (const pattern of COMMAND_PATH_GLOBS) {
    files.push(...(await glob(pattern, { cwd: ROOT, absolute: false })));
  }
  const unique = [...new Set(files)]
    .filter((f) => !EXCLUDED_FILES.has(f) && !COMMAND_PATH_IGNORE.test(f))
    .sort();

  for (const relPath of unique) {
    const absPath = path.join(ROOT, relPath);
    if (!fs.existsSync(absPath)) continue;
    const content = fs.readFileSync(absPath, 'utf-8');
    if (!content.includes('rdc')) continue;

    const hits = relPath.endsWith('.sh') ? scanShellText(content) : scanSourceText(content);
    for (const hit of hits) {
      violations.push({
        file: relPath,
        line: hit.line,
        command: hit.match,
        reason: 'stale-command-path',
        detail: hit.reason,
      });
    }

    // Options too: a real command named with a flag it does not accept is just
    // as broken as a command that does not exist, and shipped exactly that
    // (`rdc job logs --id <id>` -> "unknown option '--id'").
    if (!relPath.endsWith('.sh')) {
      for (const hit of scanSourceOptions(content)) {
        violations.push({
          file: relPath,
          line: hit.line,
          command: hit.match,
          reason: 'stale-command-option',
          detail: hit.reason,
        });
      }
    }
  }
}

/**
 * Remove duplicate violations (same file + line + reason + command snippet).
 * The whole-file pre-scan overlaps with narrow extractors on clean cases.
 */
function dedupeViolations(violations: Violation[]): void {
  const seen = new Set<string>();
  let writeIdx = 0;
  for (let i = 0; i < violations.length; i++) {
    const v = violations[i];
    const key = `${v.file}|${v.line}|${v.reason}|${v.command.trim()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    violations[writeIdx++] = v;
  }
  violations.length = writeIdx;
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

  // Deduplicate, minus the evidence documents (see EXCLUDED_FILES)
  const uniqueFiles = [...new Set(files)].filter((f) => !EXCLUDED_FILES.has(f)).sort();

  console.log(colors.dim(`Scanning ${uniqueFiles.length} files...`));

  for (const relPath of uniqueFiles) {
    const absPath = path.join(ROOT, relPath);
    if (!fs.existsSync(absPath)) continue;

    const content = fs.readFileSync(absPath, 'utf-8');
    const ext = path.extname(relPath);

    // Whole-file positional-syntax scan. Catches wrapped forms that the
    // narrow per-filetype extractors miss (command substitution, inline
    // prose, markdown list items, table cells, comments).
    scanFileForPositional(content, relPath, violations);

    if (ext === '.md') {
      extractFromMarkdown(content, relPath, violations);
    } else if (ext === '.ts' || ext === '.tsx' || ext === '.astro') {
      extractFromTypeScript(content, relPath, violations);
    } else if (ext === '.json') {
      extractFromJSON(content, relPath, violations);
    } else if (ext === '.go' || ext === '.yml' || ext === '.yaml') {
      extractFromGo(content, relPath, violations);
    }
  }

  // Stale command paths across all source + shell (wider glob, path-only check)
  await scanForStaleCommandPaths(violations);

  // Curated contract examples, through the same parser as everything above
  extractFromCommandDocs(violations);

  // Deduplicate: scanFileForPositional may overlap with narrow extractors
  dedupeViolations(violations);

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

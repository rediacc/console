/**
 * Shared detector for positional-CLI-syntax in docs/help-text.
 *
 * Single source-of-truth for:
 *   - which commands accept zero positional args (= anything after the command
 *     path that isn't a flag is a mistake)
 *   - detection regex builder
 *   - text scanner that handles wrapped forms ($(rdc ...), inline prose,
 *     markdown list items, table cells, etc.)
 *
 * Consumed by:
 *   - eslint-rules/i18n/no-positional-cli-syntax.js (JSON locale files)
 *   - eslint-rules/no-positional-cli-syntax-source.js (TS/TSX source strings)
 *   - scripts/validate-cli-examples.ts (generic repo-wide validator)
 *   - packages/www/scripts/validate-docs-cli-usage.js (www docs validator)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMMAND_TREE_PATH = path.resolve(
  __dirname,
  '../../packages/cli/scripts/command-tree.json'
);

// ---------------------------------------------------------------------------
// Types (mirror packages/cli/scripts/export-command-tree.ts shape)
// ---------------------------------------------------------------------------

interface OptionNode {
  flags: string;
  mandatory: boolean;
}

interface ArgumentNode {
  name: string;
  required: boolean;
  variadic: boolean;
}

interface CommandNode {
  name: string;
  options: OptionNode[];
  arguments: ArgumentNode[];
  subcommands: CommandNode[];
}

// ---------------------------------------------------------------------------
// Allowlist — commands whose positional arg is a freeform string (not a
// resource name that agents would otherwise positionalise by mistake).
// Leaving these off the zero-positional denylist.
// ---------------------------------------------------------------------------

const FREEFORM_ARG_COMMAND_PATHS = new Set<string>([
  'agent schema',
  'agent exec',
  'mcp capabilities',
  'mcp schema',
  'mcp exec',
  'run',
]);

// ---------------------------------------------------------------------------
// Exempt prefixes — cloud-adapter and legacy groups that legitimately use
// positional subcommands. Mirrors eslint.config.js `exemptCommandPrefixes`.
// ---------------------------------------------------------------------------

export const EXEMPT_COMMAND_PREFIXES = [
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

// ---------------------------------------------------------------------------
// Tree traversal
// ---------------------------------------------------------------------------

let cachedTree: CommandNode | null = null;
let cachedZeroPositional: Set<string> | null = null;
let cachedAllPaths: Set<string> | null = null;

export function getCommandTree(): CommandNode {
  if (cachedTree) return cachedTree;
  const raw = fs.readFileSync(COMMAND_TREE_PATH, 'utf-8');
  cachedTree = JSON.parse(raw) as CommandNode;
  return cachedTree;
}

/**
 * Return leaf command paths (e.g. "machine query", "repo up") that accept
 * zero positional arguments. For these, ANY non-flag token after the path
 * is a violation — including literals like `prod-1` or `hostinger`.
 */
export function getZeroPositionalCommands(): Set<string> {
  if (cachedZeroPositional) return cachedZeroPositional;
  const tree = getCommandTree();
  const out = new Set<string>();

  const walk = (node: CommandNode, pathParts: string[]): void => {
    if (pathParts.length > 0) {
      const commandPath = pathParts.join(' ');
      const isLeaf = node.subcommands.length === 0;
      if (
        isLeaf &&
        node.arguments.length === 0 &&
        !FREEFORM_ARG_COMMAND_PATHS.has(commandPath)
      ) {
        out.add(commandPath);
      }
    }
    for (const sub of node.subcommands) {
      walk(sub, [...pathParts, sub.name]);
    }
  };

  walk(tree, []);
  cachedZeroPositional = out;
  return out;
}

/**
 * Return ALL command paths (leaf + parent). Used for the
 * placeholder-after-parent check: a parent like `term` expects a
 * subcommand name as its next token; a `<placeholder>` or `{{interp}}`
 * can never be a subcommand name, so any such pattern is a violation.
 */
export function getAllCommandPaths(): Set<string> {
  if (cachedAllPaths) return cachedAllPaths;
  const tree = getCommandTree();
  const out = new Set<string>();

  const walk = (node: CommandNode, pathParts: string[]): void => {
    if (pathParts.length > 0) {
      const commandPath = pathParts.join(' ');
      if (!FREEFORM_ARG_COMMAND_PATHS.has(commandPath)) {
        out.add(commandPath);
      }
    }
    for (const sub of node.subcommands) {
      walk(sub, [...pathParts, sub.name]);
    }
  };

  walk(tree, []);
  cachedAllPaths = out;
  return out;
}

/** Reset the module cache. */
export function resetCache(): void {
  cachedTree = null;
  cachedZeroPositional = null;
  cachedAllPaths = null;
}

// ---------------------------------------------------------------------------
// Detection regex
// ---------------------------------------------------------------------------

const escapeRegex = (str: string): string =>
  str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Build a regex that matches a zero-positional command path followed by a
 * non-flag token — i.e. the exact pattern that teaches the wrong syntax.
 *
 * Matches (listed for reference, not enforced in code):
 *   rdc machine query <machine>
 *   rdc machine query {{name}}
 *   rdc machine query prod-1
 *   $(rdc machine query prod-1)
 *   `rdc machine query prod-1`
 *
 * Never matches `rdc machine query --name X` (flag follows command path)
 * or `rdc machine query` (no positional at all).
 */
export function buildDetectionRegex(commandPath: string): RegExp {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  // After the command path + whitespace, the next token must start with one
  // of these characters to count as "positional":
  //   <  {  [  "  '  alphanumeric
  // Prose separators (em-dash, en-dash, ampersand) and flags (`-`, `--`)
  // are NOT positional tokens — those match the negative universe.
  return new RegExp(
    `(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?=[<{\\["'a-zA-Z0-9])`
  );
}

/**
 * Regex that matches only when the next token is a placeholder (`<name>`)
 * or an i18n interpolation (`{{name}}`). Used for parent commands — a
 * parent legitimately expects a subcommand name next, but a placeholder
 * is never a valid subcommand name, so any such pattern teaches wrong
 * syntax.
 */
export function buildPlaceholderOnlyRegex(commandPath: string): RegExp {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  return new RegExp(
    `(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?=<[a-zA-Z_][\\w-]*>|\\{\\{[a-zA-Z_]\\w*\\}\\})`
  );
}

// ---------------------------------------------------------------------------
// Text scanner
// ---------------------------------------------------------------------------

export interface Violation {
  commandPath: string;
  match: string;
  line: number;
  column: number;
}

export interface ScanOptions {
  /**
   * Extra exempt prefixes beyond EXEMPT_COMMAND_PREFIXES (for file-level
   * overrides). Applied to the trimmed segment starting at the `rdc` token.
   */
  extraExemptPrefixes?: string[];
}

/**
 * Scan text for positional-syntax violations. Returns one entry per match.
 *
 * Two passes:
 *   1. Leaf commands (zero positional args): flag ANY non-flag next token.
 *   2. All commands (leaves + parents): flag placeholder (`<x>`) or
 *      interpolation (`{{x}}`) next token. A placeholder is never a
 *      valid subcommand name, so this pattern teaches wrong syntax
 *      regardless of whether the path is a leaf.
 */
export function scanText(text: string, opts: ScanOptions = {}): Violation[] {
  const exemptPrefixes = [
    ...EXEMPT_COMMAND_PREFIXES,
    ...(opts.extraExemptPrefixes ?? []),
  ];

  const leafEntries = [...getZeroPositionalCommands()]
    .sort((a, b) => b.length - a.length)
    .map((p) => ({
      path: p,
      regex: buildDetectionRegex(p),
    }));
  // Sort descending by path length so `repo autostart enable` matches
  // before `repo` (otherwise the shorter parent wins on regex dispatch).
  const allEntries = [...getAllCommandPaths()]
    .sort((a, b) => b.length - a.length)
    .map((p) => ({ path: p, regex: buildPlaceholderOnlyRegex(p) }));

  const violations: Violation[] = [];
  const lines = text.split(/\r?\n/);

  const report = (
    entry: { path: string; regex: RegExp },
    line: string,
    li: number,
    seenKeys: Set<string>
  ): void => {
    const m = entry.regex.exec(line);
    if (!m) return;
    const rdcIndex = line.indexOf('rdc ', m.index);
    if (rdcIndex === -1) return;
    const trailing = line.slice(rdcIndex);
    if (exemptPrefixes.some((p) => trailing.startsWith(p))) return;
    // Commander's conventional usage placeholders — these aren't teaching
    // positional syntax, they're the generic "takes options" / "variadic"
    // markers that Commander prints. Extract the token immediately after
    // the command path and skip if it matches.
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
    const snippet = trailing.slice(0, Math.min(trailing.length, 80));
    const key = `${li}:${rdcIndex}`;
    if (seenKeys.has(key)) return;
    seenKeys.add(key);
    violations.push({
      commandPath: entry.path,
      match: snippet,
      line: li + 1,
      column: rdcIndex + 1,
    });
  };

  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    if (!line.includes('rdc ')) continue;
    const seenKeys = new Set<string>();

    // Pass 1: leaf commands (zero positional) — any non-flag next token.
    for (const entry of leafEntries) report(entry, line, li, seenKeys);

    // Pass 2: any command path — placeholder/interpolation next token.
    // Longer paths first so we report the most specific match.
    for (const entry of allEntries) report(entry, line, li, seenKeys);
  }

  return violations;
}

/**
 * Convenience: scan a text blob and throw on first violation.
 */
export function assertNoPositional(
  text: string,
  context: string,
  opts?: ScanOptions
): void {
  const violations = scanText(text, opts);
  if (violations.length === 0) return;
  const first = violations[0];
  throw new Error(
    `${context}:${first.line}:${first.column} - positional syntax for '${first.commandPath}' (which requires named options): "${first.match}"`
  );
}

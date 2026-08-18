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
// Shared with the two ESLint rules; see eslint-rules/lib/cli-exempt-lists.js.
import {
  EXEMPT_COMMAND_PREFIXES as SHARED_EXEMPT_PREFIXES,
  FREEFORM_ARG_COMMAND_PATHS as SHARED_FREEFORM,
} from '../../eslint-rules/lib/cli-exempt-lists.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMMAND_TREE_PATH = path.resolve(__dirname, '../../packages/cli/scripts/command-tree.json');

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

const FREEFORM_ARG_COMMAND_PATHS = new Set<string>(SHARED_FREEFORM);

// ---------------------------------------------------------------------------
// Exempt prefixes — cloud-adapter and legacy groups that legitimately use
// positional subcommands. Mirrors eslint.config.js `exemptCommandPrefixes`.
// ---------------------------------------------------------------------------

const EXEMPT_COMMAND_PREFIXES: string[] = SHARED_EXEMPT_PREFIXES;

// ---------------------------------------------------------------------------
// Tree traversal
// ---------------------------------------------------------------------------

let cachedTree: CommandNode | null = null;
let cachedZeroPositional: Set<string> | null = null;
let cachedAllPaths: Set<string> | null = null;

function getCommandTree(): CommandNode {
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
function getZeroPositionalCommands(): Set<string> {
  if (cachedZeroPositional) return cachedZeroPositional;
  const tree = getCommandTree();
  const out = new Set<string>();

  const walk = (node: CommandNode, pathParts: string[]): void => {
    if (pathParts.length > 0) {
      const commandPath = pathParts.join(' ');
      const isLeaf = node.subcommands.length === 0;
      if (isLeaf && node.arguments.length === 0 && !FREEFORM_ARG_COMMAND_PATHS.has(commandPath)) {
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
 * Return PARENT command paths that take no positional of their own — the
 * placeholder-after-parent check: a parent like `term` expects a subcommand name
 * as its next token, and a `<placeholder>` or `{{interp}}` can never be a
 * subcommand name, so any such pattern is a violation.
 *
 * ★ This used to return ALL command paths, leaves included, and that made it
 * wrong the moment P4 gave leaves positional refs (R-P4-1, spec 03 §2.2). It
 * flagged `rdc datastore create <name>` — the CORRECT documented form — and told
 * the author that `datastore create` "accepts zero positional arguments", which
 * is simply false: it accepts `<datastore>`. The docstring above always said
 * "parent"; only the code said "all". A comment cannot fail, so nothing caught
 * the divergence until the tree changed underneath it.
 *
 * Two exclusions, both load-bearing:
 *   - a LEAF is never here (pass 1 already covers the zero-positional ones, and
 *     its lookahead includes `<`, so nothing is lost);
 *   - an ACTIONABLE parent that takes a positional is never here either
 *     (`repo replicate <ref>` keeps its bare create form, spec §5.4), because for
 *     those the placeholder is exactly right.
 */
function getPlaceholderOnlyParents(): Set<string> {
  if (cachedAllPaths) return cachedAllPaths;
  const tree = getCommandTree();
  const out = new Set<string>();

  const walk = (node: CommandNode, pathParts: string[]): void => {
    if (pathParts.length > 0) {
      const commandPath = pathParts.join(' ');
      const isParent = node.subcommands.length > 0;
      const takesPositional = node.arguments.length > 0;
      if (isParent && !takesPositional && !FREEFORM_ARG_COMMAND_PATHS.has(commandPath)) {
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

// ---------------------------------------------------------------------------
// Detection regex
// ---------------------------------------------------------------------------

const escapeRegex = (str: string): string => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

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
function buildDetectionRegex(commandPath: string): RegExp {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  // After the command path + whitespace, the next token must start with one
  // of these characters to count as "positional":
  //   <  {  [  "  '  alphanumeric
  // Prose separators (em-dash, en-dash, ampersand) and flags (`-`, `--`)
  // are NOT positional tokens — those match the negative universe.
  //
  // …and neither is a PROSE WORD THAT ENDS THE CLAUSE. German splits separable
  // verbs, so "run `rdc config reconcile`" is written "führen Sie rdc config
  // reconcile aus." — the particle "aus" lands after the command and read as an
  // argument. It is not one; the German is correct German. A real argument in these
  // strings is a placeholder (<name>, {{name}}), a quoted value, or value-shaped
  // (prod-1, s3-main) — never a bare run of letters immediately followed by
  // sentence punctuation. Dutch and the Nordic languages split verbs the same way,
  // so this is a class fix, not a one-off. Guarded by the fixtures in
  // scripts/lib/__tests__/positional-cli-detector.test.ts.
  return new RegExp(
    `(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?![\\p{L}]+[.,;:!?])(?=[<{\\["'a-zA-Z0-9])`,
    'u'
  );
}

/**
 * Regex that matches only when the next token is a placeholder (`<name>`)
 * or an i18n interpolation (`{{name}}`). Used for parent commands — a
 * parent legitimately expects a subcommand name next, but a placeholder
 * is never a valid subcommand name, so any such pattern teaches wrong
 * syntax.
 */
function buildPlaceholderOnlyRegex(commandPath: string): RegExp {
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
 * Two passes, and BOTH are about commands that accept no positional of their own:
 *   1. Leaf commands with zero positionals: flag ANY non-flag next token.
 *   2. Parent commands with zero positionals: flag only a placeholder (`<x>`) or
 *      interpolation (`{{x}}`) next token. A parent legitimately expects a
 *      subcommand name there, so a bare word is fine and only a placeholder is
 *      provably wrong.
 *
 * A command that DOES take a positional is in neither pass — after P4 that is
 * most of the tree, and `rdc repo up <repo-ref>` is the syntax we now want taught.
 */
export function scanText(text: string, opts: ScanOptions = {}): Violation[] {
  const exemptPrefixes = [...EXEMPT_COMMAND_PREFIXES, ...(opts.extraExemptPrefixes ?? [])];

  const leafEntries = [...getZeroPositionalCommands()]
    .sort((a, b) => b.length - a.length)
    .map((p) => ({
      path: p,
      regex: buildDetectionRegex(p),
    }));
  // Sort descending by path length so `repo autostart enable` matches
  // before `repo` (otherwise the shorter parent wins on regex dispatch).
  const parentEntries = [...getPlaceholderOnlyParents()]
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

    // Pass 2: parents with no positional — placeholder/interpolation next token.
    // Longer paths first so we report the most specific match.
    for (const entry of parentEntries) report(entry, line, li, seenKeys);
  }

  return violations;
}

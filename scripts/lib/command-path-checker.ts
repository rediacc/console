/**
 * Detects `rdc …` references naming commands that no longer exist.
 *
 * This is the counterpart to positional-cli-detector.ts: that one asks "are the
 * ARGUMENTS to a real command written the old way", this one asks "is the
 * COMMAND real at all". The P4 reshape moved most verbs, and the strings telling
 * operators what to run were left behind — `rdc config machine setup`,
 * `rdc machine query`, `./rdc.sh auth login`. Every one of those was shipped in
 * an error message or a --help block, so an operator following the instruction
 * lands on "unknown command".
 *
 * Ground truth is packages/cli/scripts/command-tree.json, which
 * `check:ci-command-tree` already keeps in sync with the registered commands.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

interface TreeNode {
  name: string;
  arguments?: unknown[];
  options?: { flags: string }[];
  subcommands?: TreeNode[];
}

/** path string ("machine status") -> node, for every command in the tree. */
let cachedNodes: Map<string, TreeNode> | null = null;

function commandNodes(): Map<string, TreeNode> {
  if (cachedNodes) return cachedNodes;
  const tree = JSON.parse(
    fs.readFileSync(path.join(ROOT, 'packages/cli/scripts/command-tree.json'), 'utf-8')
  ) as TreeNode;
  const nodes = new Map<string, TreeNode>();
  const walk = (node: TreeNode, prefix: string[]): void => {
    for (const sub of node.subcommands ?? []) {
      const next = [...prefix, sub.name];
      nodes.set(next.join(' '), sub);
      walk(sub, next);
    }
  };
  walk(tree, []);
  cachedNodes = nodes;
  return nodes;
}

/**
 * Words that follow a bare `rdc` in English prose rather than in an invocation.
 *
 * Needed because a reference is only recognisable by its shape, and prose about
 * the tool has the same shape as a command: ``rdc ops is not supported on …``
 * sits directly after a backtick, exactly like the real references do, so no
 * amount of quoting/prompt-cue detection separates them. Keep this list to
 * function words only — a noun here would silently mask a real stale command,
 * which is the one failure mode this checker exists to prevent.
 */
const PROSE_WORDS = new Set([
  'a',
  'an',
  'and',
  'are',
  'as',
  'be',
  'by',
  'can',
  'child',
  'do',
  'does',
  'for',
  'from',
  'has',
  'have',
  'if',
  'in',
  'into',
  'is',
  'it',
  'may',
  'must',
  'not',
  'on',
  'or',
  'process',
  'should',
  'that',
  'the',
  'this',
  'to',
  'was',
  'when',
  'will',
  'with',
]);

/** Commands that exist but are deliberately absent from the tree (hidden). */
const HIDDEN_COMMANDS = new Set(['run']);

export interface CommandPathHit {
  /** The matched text, e.g. "rdc config machine setup". */
  match: string;
  /** Why it is stale, phrased for the operator fixing it. */
  reason: string;
}

/**
 * Resolve a token sequence against the command tree.
 *
 * The LONGEST valid prefix is what matters. Matching the shortest instead
 * reports `rdc config backup-strategy set` as valid, because `config` alone is a
 * real command — which is precisely how these references survived until now.
 * Once the longest path is known, leftover tokens are either positional
 * arguments (fine, the node declares `arguments`) or a subcommand that does not
 * exist (stale).
 */
function classifyCommandPath(words: string[]): CommandPathHit | null {
  if (words.length === 0) return null;
  const nodes = commandNodes();

  let matchedLength = -1;
  let matchedNode: TreeNode | null = null;
  for (let i = words.length; i >= 1; i--) {
    const node = nodes.get(words.slice(0, i).join(' '));
    if (node) {
      matchedLength = i;
      matchedNode = node;
      break;
    }
  }

  if (matchedLength === -1 || !matchedNode) {
    if (PROSE_WORDS.has(words[0]) || HIDDEN_COMMANDS.has(words[0])) return null;
    return { match: words.join(' '), reason: `"${words[0]}" is not an rdc command` };
  }

  const leftover = words.slice(matchedLength);
  if (leftover.length === 0) return null;
  if (PROSE_WORDS.has(leftover[0])) return null;

  // A node that takes positional arguments legitimately has words after it.
  const takesArguments = (matchedNode.arguments ?? []).length > 0;
  const hasSubcommands = (matchedNode.subcommands ?? []).length > 0;
  if (!hasSubcommands || takesArguments) return null;

  const parent = words.slice(0, matchedLength).join(' ');
  return {
    match: words.slice(0, matchedLength + 1).join(' '),
    reason: `"${leftover[0]}" is not a subcommand of "rdc ${parent}"`,
  };
}

/** Longest command path we bother resolving; beyond this it is arguments. */
const MAX_PATH_WORDS = 4;

function tokensAfterRdc(raw: string): string[] {
  return raw.trim().split(/\s+/).slice(0, MAX_PATH_WORDS);
}

const SOURCE_PATTERN = /\brdc\s+([a-z][\w-]*(?:\s+[a-z][\w-]*)*)/g;

/**
 * Scan TypeScript/Go source for stale references.
 *
 * Comment-only lines are skipped: prose about the CLI lives in comments and is
 * not operator-facing, so flagging it is pure noise.
 */
export function scanSourceText(content: string): Array<CommandPathHit & { line: number }> {
  const hits: Array<CommandPathHit & { line: number }> = [];
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) continue;
    for (const match of lines[i].matchAll(SOURCE_PATTERN)) {
      const hit = classifyCommandPath(tokensAfterRdc(match[1]));
      if (hit) hits.push({ ...hit, line: i + 1 });
    }
  }
  return hits;
}

/**
 * `rdc` in COMMAND POSITION: line start, or after a shell separator.
 *
 * Shell scripts discuss the CLI in `echo`/`printf` strings constantly — a naive
 * scan of .sh files is ~1-in-6 precision, and every one of the false hits is
 * prose inside a quoted argument. Requiring command position is what makes
 * scanning shell viable at all. `--dev` / `--native` are consumed by the
 * rdc.sh wrapper and never reach the CLI, so they are skipped (see rdc.sh:82).
 */
const SHELL_COMMAND_POSITION =
  /(?:^|[;&|]{1,2}\s*|\$\(\s*|`\s*)\s*(?:\.\/)?rdc(?:\.sh)?\s+(?:--(?:dev|native)\s+)*([a-z][\w-]*(?:\s+[a-z][\w-]*)*)/g;

export function scanShellText(content: string): Array<CommandPathHit & { line: number }> {
  const hits: Array<CommandPathHit & { line: number }> = [];
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim().startsWith('#')) continue;
    for (const match of lines[i].matchAll(SHELL_COMMAND_POSITION)) {
      const hit = classifyCommandPath(tokensAfterRdc(match[1]));
      if (hit) hits.push({ ...hit, line: i + 1 });
    }
  }
  return hits;
}

// ---------------------------------------------------------------------------
// Option validation
//
// The path checker above answers "is this command real". It does not look at
// the OPTIONS, and that gap shipped a broken instruction: job-client.ts told
// operators to run `rdc job logs -m <machine> --id <jobId> --follow`, but
// `job logs` takes a POSITIONAL <job-id> and has no --id. Following the CLI's
// own printed hint produced `error: unknown option '--id'`.
//
// The ESLint rule `i18n/no-undefined-cli-flags` already validates flags inside
// i18n strings; these were hardcoded template literals, so nothing checked them.
// ---------------------------------------------------------------------------

/** Every flag spelling declared by one option entry ("-m, --machine <name>"). */
function optionFlags(option: { flags: string }): string[] {
  return option.flags.split(' <')[0].match(/-{1,2}[A-Za-z][\w-]*/g) ?? [];
}

let cachedGlobalFlags: Set<string> | null = null;

/**
 * Options accepted by ANY command: the root command's own options plus
 * Commander's built-in --help.
 *
 * Root options are global by construction — `--background` is registered on the
 * root and applied via a preAction hook, which is exactly why it appears in no
 * per-command option list and is so easy to miss.
 */
function globalFlags(): Set<string> {
  if (cachedGlobalFlags) return cachedGlobalFlags;
  const tree = JSON.parse(
    fs.readFileSync(path.join(ROOT, 'packages/cli/scripts/command-tree.json'), 'utf-8')
  ) as { options?: { flags: string }[] };
  const flags = new Set<string>(['--help', '-h']);
  for (const option of tree.options ?? []) {
    for (const flag of optionFlags(option)) flags.add(flag);
  }
  cachedGlobalFlags = flags;
  return flags;
}

/**
 * Trim a captured run down to ONE command.
 *
 * Prose routinely chains commands — "(1) rdc repo fork … (2) rdc repo push
 * --to …" — and without this the second command's flags get attributed to the
 * first, which reported `--to` as unknown on `repo fork`. Stopping at the next
 * `rdc`, at list punctuation, or at a sentence break keeps each command's flags
 * with the command that owns them.
 */
function firstCommandOnly(run: string): string {
  // `)` terminates too: "down it first (rdc repo down %s) or pass --force to
  // quiesce" would otherwise attribute --force (which belongs to the enclosing
  // sentence's OTHER command) to `repo down`.
  return run.split(/\brdc\s|[,;→)]|\.\s/)[0];
}

const COMMAND_RUN = /\brdc\s+([^'"`\n]+)/g;

/** Flags used against a command that does not declare them. */
export function scanSourceOptions(content: string): Array<CommandPathHit & { line: number }> {
  const hits: Array<CommandPathHit & { line: number }> = [];
  const nodes = commandNodes();
  const lines = content.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) continue;

    for (const match of lines[i].matchAll(COMMAND_RUN)) {
      const tokens = firstCommandOnly(match[1]).split(/\s+/).filter(Boolean);

      let matchedLength = 0;
      let node: TreeNode | null = null;
      for (let k = Math.min(MAX_PATH_WORDS, tokens.length); k >= 1; k--) {
        const found = nodes.get(tokens.slice(0, k).join(' '));
        if (found) {
          matchedLength = k;
          node = found;
          break;
        }
      }
      if (!node) continue;

      const allowed = new Set(globalFlags());
      for (const option of node.options ?? []) {
        for (const flag of optionFlags(option)) allowed.add(flag);
      }

      const commandPath = tokens.slice(0, matchedLength).join(' ');
      for (const raw of tokens.slice(matchedLength)) {
        // End-of-options: `rdc repo exec app -c web -- ls -la` hands everything
        // after `--` to the REMOTE command, so those tokens are not this
        // command's flags and must not be checked against its option list.
        if (raw === '--') break;
        const token = raw.split('=')[0];
        if (!/^-{1,2}[A-Za-z][\w-]*$/.test(token)) continue;
        if (allowed.has(token)) continue;
        hits.push({
          match: `rdc ${commandPath} ${token}`,
          reason: `"${token}" is not an option of "rdc ${commandPath}"`,
          line: i + 1,
        });
      }
    }
  }
  return hits;
}

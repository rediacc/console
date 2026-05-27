#!/usr/bin/env tsx
/**
 * check-cli-docs — validate `rdc` command references in markdown docs against
 * the authoritative CLI command tree (packages/cli/scripts/command-tree.json).
 *
 * Catches the class of regression fixed by hand in rediacc/console#490: a doc
 * that names a command/flag that does not exist (e.g. a renamed or removed
 * subcommand, or a stale flag). ESLint in this repo cannot lint markdown, so
 * this runs as a standalone `check:cli-docs` gate wired into CI Quality.
 *
 * Scope: `.claude/skills/rdc/*.md` and `packages/www/src/content/docs/en/*.md`.
 * Conservative by design — only high-signal violations are reported:
 *   - unknown subcommand: a token in command position that is not a registered
 *     subcommand, where the resolved node HAS subcommands and takes NO
 *     positional argument (so the token can't be an argument), and is not a
 *     placeholder (<x>, [x], {x}, $X, ...).
 *   - unknown long flag: a `--flag` not registered on the resolved command path
 *     (or globally).
 *
 * Usage:
 *   npx tsx scripts/check-cli-docs.ts            # report violations, exit 1 if any
 *   npx tsx scripts/check-cli-docs.ts --fix      # apply curated renames, then report
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TREE_PATH = path.join(ROOT, 'packages/cli/scripts/command-tree.json');

const DOC_GLOBS = [
  '.claude/skills/rdc',
  'packages/www/src/content/docs/en',
];
// reference.md is auto-generated from the live command tree — never hand-stale.
const EXCLUDE_FILES = new Set(['reference.md']);

// Root/global options not attached to per-command nodes in command-tree.json.
const GLOBAL_LONG_FLAGS = new Set([
  '--output',
  '--context',
  '--lang',
  '--version',
  '--help',
  '--help-all',
  '--quiet',
  '--config',
]);
// Global options that consume the following token as their value (so we skip it
// when locating the first real subcommand, e.g. `rdc --config prod machine …`).
const GLOBAL_VALUE_FLAGS = new Set(['--output', '--context', '--lang', '--config']);

// Curated renames applied by --fix: stale command prefixes whose current form is
// unambiguous (verified against `rdc <cmd> --help`). Keys/values are the tokens
// after `rdc`. Applied longest-key-first as a prefix replace.
const RENAMES: Record<string, string> = {
  'machine status': 'machine query',
  'machine deploy-backup': 'machine backup schedule',
  'repo destroy': 'repo delete',
  'repo sync push': 'repo sync upload',
  'repo sync pull': 'repo sync download',
  'repo up-all': 'repo up',
  'audit list': 'audit log',
  'organization list': 'organization info',
  'permission list': 'permission group list',
  'config set-ssh': 'config ssh set',
  'subscription refresh': 'subscription refresh activation',
  // push/pull moved from `repo backup` to top-level `repo`; the `a/b` shorthand
  // (`repo push/pull`) is then accepted by the slash-shorthand rule.
  'repo backup push/pull': 'repo push/pull',
};

const LONG_FLAG_RE = /^--[a-z][a-z0-9-]*/;

interface TreeNode {
  name?: string;
  options?: { flags: string }[];
  arguments?: { name: string; required: boolean; variadic: boolean }[];
  subcommands?: TreeNode[];
}

interface CmdNode {
  subcommands: Map<string, CmdNode>;
  longFlags: Set<string>;
  hasArgs: boolean;
  hasSubs: boolean;
}

function longFlagsOf(node: TreeNode): Set<string> {
  const flags = new Set<string>();
  for (const o of node.options ?? []) {
    const m = o.flags.match(/--[a-z][a-z0-9-]*/g);
    for (const f of m ?? []) {
      flags.add(f);
      // Commander negatable booleans: `--no-foo` makes `--foo` valid too.
      const neg = f.match(/^--no-(.+)$/);
      if (neg) flags.add('--' + neg[1]);
    }
  }
  return flags;
}

function buildCmd(node: TreeNode): CmdNode {
  const subcommands = new Map<string, CmdNode>();
  for (const sub of node.subcommands ?? []) {
    if (sub.name && sub.name !== 'help') subcommands.set(sub.name, buildCmd(sub));
  }
  return {
    subcommands,
    longFlags: longFlagsOf(node),
    hasArgs: (node.arguments?.length ?? 0) > 0,
    hasSubs: subcommands.size > 0,
  };
}

const tree: TreeNode = JSON.parse(fs.readFileSync(TREE_PATH, 'utf-8'));
const ROOT_CMD = buildCmd(tree);
for (const f of longFlagsOf(tree)) GLOBAL_LONG_FLAGS.add(f);

// Top-level shortcut commands that export-command-tree.ts drops via
// EXCLUDED_TOP_LEVEL (they alias subcommands, e.g. `rdc run` = function runner,
// `rdc login` = `auth login`, `rdc trace` = `queue trace`). They are real and
// take positional args, so register them as arg-accepting leaves to avoid false
// "unknown subcommand" reports. Keep in sync with EXCLUDED_TOP_LEVEL.
for (const name of ['run', 'login', 'logout', 'trace', 'cancel', 'retry']) {
  if (!ROOT_CMD.subcommands.has(name)) {
    ROOT_CMD.subcommands.set(name, {
      subcommands: new Map(),
      longFlags: new Set(),
      hasArgs: true,
      hasSubs: false,
    });
  }
}

// ─── cli.json command-key validation ───────────────────────────────────────
// The CLI docs (cli-application*.md) are generated from cli.json: a node with a
// `description` becomes a documented command. A stale command key (left after a
// command is renamed/removed) silently produces a doc section for a command that
// no longer exists. Catch those by checking every cli.json command-key path
// against the live command tree.
const CLI_JSON_PATH = path.join(ROOT, 'packages/cli/src/i18n/locales/en/cli.json');
// Real top-level command groups (camelCase keys map to kebab tree names).
const COMMAND_GROUPS = new Set([
  'agent', 'config', 'datastore', 'machine', 'mcp', 'repo', 'storage', 'vscode',
  'term', 'protocol', 'subscription', 'update', 'doctor', 'ops', 'auth',
  'organization', 'user', 'team', 'permission', 'region', 'bridge', 'repository',
  'queue', 'ceph', 'audit',
]);
const kebab = (s: string): string => s.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();

function validCommandPaths(): Set<string> {
  const paths = new Set<string>();
  const walk = (node: CmdNode, parts: string[]): void => {
    if (parts.length) paths.add(parts.join(' '));
    for (const [name, sub] of node.subcommands) walk(sub, [...parts, name]);
  };
  walk(ROOT_CMD, []);
  return paths;
}

function checkI18nCommandKeys(out: Violation[]): void {
  const valid = validCommandPaths();
  const cli = JSON.parse(fs.readFileSync(CLI_JSON_PATH, 'utf-8')) as {
    commands?: Record<string, unknown>;
  };
  const isCommand = (n: unknown): n is Record<string, unknown> =>
    typeof n === 'object' && n !== null && typeof (n as { description?: unknown }).description === 'string';
  const walk = (node: Record<string, unknown>, parts: string[]): void => {
    for (const [key, value] of Object.entries(node)) {
      if (typeof value !== 'object' || value === null) continue;
      const v = value as Record<string, unknown>;
      const partsNow = [...parts, key];
      if (isCommand(v) && COMMAND_GROUPS.has(partsNow[0])) {
        const cmdPath = partsNow.map(kebab).join(' ');
        if (!valid.has(cmdPath)) {
          const sugg = nearest(partsNow.at(-1) ?? '', [...ROOT_CMD.subcommands.keys()]);
          out.push({
            file: 'packages/cli/src/i18n/locales/en/cli.json',
            line: 0,
            command: `commands.${partsNow.join('.')}`,
            message: `stale command key \`commands.${partsNow.join('.')}\` → documents \`rdc ${cmdPath}\`, which is not a real command${sugg ? ` (did you mean \`${sugg}\`?)` : ''}. Remove the key (and its \`description\`) or correct it.`,
          });
        }
      }
      walk(v, partsNow);
    }
  };
  walk(cli.commands ?? {}, []);
}

function levenshtein(a: string, b: string): number {
  const dp = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 0; j <= b.length; j++) dp[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
      );
  return dp[a.length][b.length];
}

function nearest(token: string, candidates: Iterable<string>): string | null {
  let best: string | null = null;
  let bestD = Infinity;
  for (const c of candidates) {
    const d = levenshtein(token.replace(/^-+/, ''), c.replace(/^-+/, ''));
    if (d < bestD) {
      bestD = d;
      best = c;
    }
  }
  return best && bestD <= Math.max(2, Math.floor(token.length / 3)) ? best : null;
}

// A token that is a placeholder / not a literal subcommand or flag.
function isPlaceholder(tok: string): boolean {
  return (
    /^[<[{$]/.test(tok) ||
    /[>\]}]$/.test(tok) ||
    tok === '...' ||
    tok.includes('<') ||
    tok.includes('|') ||
    tok.startsWith('{{')
  );
}

// Shell operators that end the rdc invocation (rest is unrelated shell).
const SHELL_STOP = new Set(['|', '&&', '||', ';', '>', '>>', '2>', '2>&1', '&', '\\']);

interface Violation {
  file: string;
  line: number;
  command: string;
  message: string;
}

function validateInvocation(file: string, line: number, raw: string, out: Violation[]): void {
  const tokens = raw.split(/\s+/).filter(Boolean);
  if (tokens[0] !== 'rdc') return;
  let node = ROOT_CMD;
  const validFlags = new Set(GLOBAL_LONG_FLAGS);
  const pathParts: string[] = [];
  let i = 1;

  // Skip leading global options (and their values) before the subcommand.
  while (i < tokens.length && tokens[i].startsWith('-')) {
    const flag = tokens[i];
    if (GLOBAL_VALUE_FLAGS.has(flag.replace(/=.*/, '')) && !flag.includes('=')) i++;
    i++;
  }

  for (; i < tokens.length; i++) {
    const tok = tokens[i];
    if (SHELL_STOP.has(tok)) break;
    if (tok.startsWith('--')) {
      const flag = (tok.match(LONG_FLAG_RE) ?? [''])[0];
      if (flag && !validFlags.has(flag) && !node.longFlags.has(flag)) {
        const cmd = `rdc ${pathParts.join(' ')}`.trim();
        const sugg = nearest(flag, new Set([...validFlags, ...node.longFlags]));
        out.push({
          file,
          line,
          command: raw,
          message: `\`${cmd}\`: unknown flag \`${flag}\`${sugg ? ` (did you mean \`${sugg}\`?)` : ''}`,
        });
      }
      continue;
    }
    if (tok.startsWith('-')) continue; // short flag(s) — not validated (bundling-prone)
    // Command-position word.
    const sub = node.subcommands.get(tok);
    if (sub) {
      node = sub;
      pathParts.push(tok);
      for (const f of node.longFlags) validFlags.add(f);
      continue;
    }
    if (isPlaceholder(tok)) break; // positional placeholder — stop path resolution
    // `a/b` shorthand (e.g. `repo push/pull`): accept when every part is a valid
    // subcommand of this node — it means "a or b", not a single command.
    if (tok.includes('/')) {
      const parts = tok.split('/');
      if (parts.length > 1 && parts.every((p) => node.subcommands.has(p))) break;
    }
    // Unknown word in command position. Only high-signal: the node expects a
    // subcommand (has subs) and takes no positional argument, so this cannot be
    // a valid argument — it's a stale/typo'd subcommand.
    if (node.hasSubs && !node.hasArgs) {
      const cmd = `rdc ${pathParts.join(' ')}`.trim();
      const sugg = nearest(tok, node.subcommands.keys());
      out.push({
        file,
        line,
        command: raw,
        message: `\`${cmd}\`: unknown subcommand \`${tok}\`${sugg ? ` (did you mean \`${sugg}\`?)` : ''}`,
      });
    }
    break; // after the first unknown/positional, stop (rest are args)
  }
}

// Extract candidate `rdc ...` invocations from a markdown file, with line numbers.
function extractInvocations(content: string): { line: number; raw: string }[] {
  const lines = content.split('\n');
  const found: { line: number; raw: string }[] = [];
  let inFence = false;
  let fenceLang = '';
  const SHELL_LANGS = new Set(['', 'bash', 'sh', 'shell', 'console', 'zsh']);

  const pushFrom = (text: string, lineNo: number) => {
    // Normalize ./rdc.sh -> rdc and strip a leading prompt.
    const norm = text.replace(/\.\/rdc\.sh/g, 'rdc');
    const re = /(?:^|[\s`(])rdc\s+[^\n`]*/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(norm))) {
      const raw = m[0].replace(/^[\s`(]+/, '').trim();
      if (raw.startsWith('rdc')) found.push({ line: lineNo, raw });
    }
  };

  lines.forEach((lineText, idx) => {
    const lineNo = idx + 1;
    const fence = lineText.match(/^\s*```(\w*)/);
    if (fence) {
      if (inFence) {
        inFence = false;
      } else {
        inFence = true;
        fenceLang = fence[1].toLowerCase();
      }
      return;
    }
    if (inFence) {
      if (SHELL_LANGS.has(fenceLang)) {
        // Strip shell comments so prose inside `# … no rdc equivalent` isn't
        // parsed as a command.
        const code = lineText.replace(/(^|\s)#.*$/, '');
        pushFrom(code, lineNo);
      }
      return;
    }
    // Prose: only inline code spans containing rdc.
    const spanRe = /`([^`]+)`/g;
    let s: RegExpExecArray | null;
    while ((s = spanRe.exec(lineText))) {
      if (/(^|\s)(\.\/)?rdc(\.sh)?\s/.test(s[1])) pushFrom(s[1], lineNo);
    }
  });
  return found;
}

// Generated docs (cli-application*.md) are produced from cli.json by the doc
// generator and freshness-checked by `validate:cli-docs`; their command refs are
// the generator's responsibility, not a hand-authored concern. Skip them here so
// we don't double-cover (and so a stale cli.json key surfaces in that pipeline,
// not this one).
function isGenerated(absFile: string): boolean {
  const head = fs.readFileSync(absFile, 'utf-8').slice(0, 600);
  return head.includes('AUTO-GENERATED') || /^generated:\s*true/m.test(head);
}

function listMarkdown(dir: string): string[] {
  const abs = path.join(ROOT, dir);
  if (!fs.existsSync(abs)) return [];
  return fs
    .readdirSync(abs)
    .filter((f) => f.endsWith('.md') && !EXCLUDE_FILES.has(f))
    .map((f) => path.join(dir, f))
    .filter((rel) => !isGenerated(path.join(ROOT, rel)));
}

function applyFixes(absFile: string): boolean {
  const orig = fs.readFileSync(absFile, 'utf-8');
  let next = orig;
  for (const [from, to] of Object.entries(RENAMES).sort((a, b) => b[0].length - a[0].length)) {
    next = next.replaceAll(`rdc ${from}`, `rdc ${to}`);
    next = next.replaceAll(`./rdc.sh ${from}`, `./rdc.sh ${to}`);
  }
  if (next !== orig) {
    fs.writeFileSync(absFile, next);
    return true;
  }
  return false;
}

function main(): void {
  const fix = process.argv.includes('--fix');
  const files = DOC_GLOBS.flatMap(listMarkdown);
  const violations: Violation[] = [];
  let fixedCount = 0;

  for (const file of files) {
    const abs = path.join(ROOT, file);
    if (fix && applyFixes(abs)) fixedCount++;
    const content = fs.readFileSync(abs, 'utf-8');
    for (const { line, raw } of extractInvocations(content)) {
      validateInvocation(file, line, raw, violations);
    }
  }

  // Also catch stale command keys in cli.json (the source of generated CLI docs).
  checkI18nCommandKeys(violations);

  if (fix && fixedCount > 0) {
    console.log(`Applied curated renames in ${fixedCount} file(s).`);
  }

  if (violations.length === 0) {
    console.log(
      `✓ check-cli-docs: ${files.length} docs + cli.json command keys clean (no stale rdc references)`
    );
    return;
  }

  console.error(`✗ check-cli-docs: ${violations.length} stale rdc reference(s) found:\n`);
  for (const v of violations) {
    console.error(`  ${v.file}:${v.line}: ${v.message}`);
    console.error(`      in: ${v.command}`);
  }
  console.error(
    `\nFix the docs to match the CLI (see \`packages/cli/scripts/command-tree.json\`), or add a curated rename to scripts/check-cli-docs.ts and run with --fix.`
  );
  process.exit(1);
}

main();

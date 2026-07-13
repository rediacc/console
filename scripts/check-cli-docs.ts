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
import { cli } from '../packages/cli/src/cli.js';
import { EXCLUDED_TOP_LEVEL } from '../packages/cli/scripts/lib/command-tree-lib.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TREE_PATH = path.join(ROOT, 'packages/cli/scripts/command-tree.json');

const DOC_GLOBS = [
  '.claude/skills/rdc',
  'packages/www/src/content/docs/en',
  // Executable CI tutorial scripts. They were never covered, which is why the
  // reshape broke them silently — see listCheckableFiles().
  '.ci/tutorials',
  // Repo docs. See EXCLUDED_DIRS: docs/design/** is held out.
  'docs',
];

/**
 * Directories held out of the scan.
 *
 * ★ `docs/design/**` is the DESIGN RECORD. It deliberately quotes dead commands while ARGUING
 * about them — spec/03 §13 cites `rdc auth login`, `repo takeover`, `machine query` and
 * `config cert-cache pull` precisely BECAUSE they are the bugs it documents. Flagging those
 * citations is flagging the bug report for containing the bug.
 *
 * ★★ THIS EXCLUSION WAS ASSERTED IN A COMMENT AND NEVER IMPLEMENTED. The comment above the globs
 * said, in as many words, "docs/design/** ... is excluded" — and the code did not exclude it. It
 * is the seventh instance of the phase's own rule (§13.0), found in the phase's own tooling, by
 * the agent who kept quoting the rule, at the last minute of the last sweep, WHILE WRITING THE
 * SECTION ABOUT THE FIRST SIX. ★★★ A COMMENT CANNOT FAIL. If the people who spent a night hunting
 * this exact bug still shipped one, then "be more careful" was never the remedy. Only the code is.
 */
const EXCLUDED_DIRS = ['docs/design'];
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
// ★ P4 REVERSED SEVERAL OF THESE. The map used to carry
// `'machine status': 'machine query'` and `'subscription refresh': 'subscription
// refresh activation'` — both of which now point at commands that NO LONGER EXIST,
// because P4 renamed them in the OPPOSITE direction (`machine query` became
// `machine status`; the three `subscription refresh *` leaves collapsed into
// `subscription refresh`). Running `--fix` would have rewritten CORRECT docs into
// broken ones, which is worse than not having a fixer at all: the tool that repairs
// staleness would have been the thing introducing it.
//
// Only unambiguous CURRENT targets belong here, and every value is checked below
// against the live tree so this map can never again name a command that is gone.
const RENAMES: Record<string, string> = {
  'machine query': 'machine status',
  'machine deploy-backup': 'backup schedule',
  'repo destroy': 'repo delete',
  'repo sync push': 'repo sync upload',
  'repo sync pull': 'repo sync download',
  'repo takeover': 'repo promote',
  'config machine add': 'machine add',
  'config machine setup': 'machine setup',
  'config machine scan-keys': 'machine scan-keys',
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
  /** Single-letter short flags (`-m`). Bundles (`-abc`) are not modelled and not checked. */
  shortFlags: Set<string>;
  hasArgs: boolean;
  hasSubs: boolean;
}

function shortFlagsOf(node: TreeNode): Set<string> {
  const flags = new Set<string>();
  for (const o of node.options ?? []) {
    for (const f of o.flags.match(/(^|[\s,])-[A-Za-z](?![\w-])/g) ?? []) {
      flags.add(f.trim().replace(/^,/, '').trim());
    }
  }
  return flags;
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
    shortFlags: shortFlagsOf(node),
    hasArgs: (node.arguments?.length ?? 0) > 0,
    hasSubs: subcommands.size > 0,
  };
}

const tree: TreeNode = JSON.parse(fs.readFileSync(TREE_PATH, 'utf-8'));
const ROOT_CMD = buildCmd(tree);
for (const f of longFlagsOf(tree)) GLOBAL_LONG_FLAGS.add(f);

// Top-level commands that export-command-tree.ts drops via EXCLUDED_TOP_LEVEL.
// They are real and take positional args, so register them as arg-accepting
// leaves to avoid false "unknown subcommand" reports.
//
// IMPORTED, not re-listed. This used to be a hand-copy that had drifted to
// ['run', 'login', 'logout', 'trace', 'cancel', 'retry'] — five names that are
// not commands. Every one of them was therefore registered here as a VALID
// arg-accepting command, so this validator would have blessed a doc snippet like
// `rdc login --whatever` instead of reporting it. A stale allowlist in the gate
// that exists to catch stale docs is the worst place for one, and the only fix
// that holds is to make divergence impossible rather than to correct the copy.
// ★ THEIR REAL FLAGS, READ FROM THE LIVE COMMANDER TREE — NOT AN EMPTY SET, AND NOT A PERMISSIVE
// ONE. `run` is held out of the generated CONTRACT, not out of the CLI: it exists, and it has
// `-f/--function`, `-m/--machine`, `--param` and the rest. An EMPTY flag set made every flag on it
// read as unknown (it reported the CORRECT `rdc run -f <fn>` as an error). The tempting fix — let
// any flag through — would be a FAIL-OPEN: tomorrow a doc could teach `rdc run --parent` and this
// gate would bless it. ★★ CLOSING A FALSE POSITIVE BY OPENING A BLIND SPOT IS THE TRADE THIS PHASE
// REFUSED SIX TIMES. So ask the thing that decides: the live Commander tree.
for (const name of EXCLUDED_TOP_LEVEL) {
  if (ROOT_CMD.subcommands.has(name)) continue;
  const live = cli.commands.find((c) => c.name() === name);
  ROOT_CMD.subcommands.set(name, {
    subcommands: new Map(),
    longFlags: new Set((live?.options ?? []).map((o) => o.long).filter((f): f is string => !!f)),
    shortFlags: new Set((live?.options ?? []).map((o) => o.short).filter((f): f is string => !!f)),
    hasArgs: (live?.registeredArguments.length ?? 0) > 0 || !live,
    hasSubs: false,
  });
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

/**
 * Validate every `rdc ...` example embedded in an ENGLISH LOCALE VALUE, PER COMMAND.
 *
 * ★ NOTHING DID THIS, AND THE GAP HAD A BUG IN IT. Two checks look at these strings and
 * neither asks the right question:
 *   - `i18n/no-undefined-cli-flags` builds ONE GLOBAL SET of every flag on every command and
 *     asks "does this flag exist ANYWHERE?" So `rdc repo secret get --name X` PASSES, because
 *     `--name` exists on some other command entirely. It never resolves the flag against the
 *     command it is actually written on.
 *   - `checkI18nCommandKeys` (below) validates the command-key STRUCTURE of cli.json, never the
 *     `rdc ...` examples inside the VALUES.
 *
 * So `errors.precondition.next.options.confirm.run` shipped as
 *     "rdc repo secret get --name {{repository}} --key {{key}}"
 * when `repo secret get` takes a positional `<ref>` and only `--key`. It is the NEXT-STEP HINT
 * printed after a precondition failure: when something has already gone wrong, the CLI handed
 * the user a command that fails too. Byte-identical in all twelve locales.
 *
 * This reuses `validateInvocation` — the same per-command resolver the docs use — so a flag is
 * checked against the command it is written on, which is the only question worth asking.
 */
// English function words that can never name a command. A locale value is PROSE with commands
// embedded in it, so `rdc --help for architecture ...` puts "for" in command position. Without
// this the gate cries wolf, and a gate nobody trusts is a gate nobody runs.
const PROSE_WORDS = new Set([
  'for', 'to', 'and', 'or', 'the', 'a', 'an', 'is', 'was', 'with', 'in', 'on', 'if', 'then',
  'use', 'run', 'see', 'from', 'into', 'via', 'not', 'no', 'it', 'this', 'that',
]);

/** A token that ends a sentence, or is an English function word, is prose. */
const isProseToken = (token: string): boolean =>
  PROSE_WORDS.has(token.toLowerCase()) || /[.,;:)\]]$/.test(token);

/**
 * English locale values: validate every `rdc ...` example PER COMMAND (absolute check).
 * Non-English locales: validate COMMAND PARITY against English (relative check).
 *
 * ★ WHY THE TWO ARE DIFFERENT, AND WHY AN ABSOLUTE CHECK CANNOT WORK ON A LOCALE.
 * A locale value is PROSE with commands embedded, and the prose is translated. So
 * `rdc repo sync en su lugar:` (Spanish) puts "en" in command position, and
 * `rdc para usar la versión anterior` puts "para" there. An absolute checker reports both as
 * unknown subcommands. No list of English function words can fix that, and no list of TWELVE
 * languages' function words is a thing anyone should maintain.
 *
 * ★★ THE INVARIANT THAT DOES HOLD: A COMMAND NAME IS NEVER TRANSLATED. `repo up` is `repo up`
 * in every language, and so is `--name`. So for a given key, the command PATHS and FLAGS in the
 * locale must be exactly the ones in English. That is the same shape as placeholder parity, and
 * it is language-invariant: translated prose after a valid path simply ends the path, and is
 * ignored in both sides equally.
 *
 * This catches the real defect (a locale still saying `rdc repo up --name X -m Y` while English
 * says `rdc repo up {{repository}}`, or a locale still saying `repo takeover`) without ever
 * needing to know what a Spanish preposition looks like.
 */
const TOP_LEVEL = new Set(ROOT_CMD.subcommands.keys());

/** The (command path, flags) pairs of every real invocation in a string. */
function invocationShapes(value: string): string[] {
  const shapes: string[] = [];

  for (const { raw } of extractInvocations(value, true)) {
    const tokens = raw.split(/\s+/).slice(1); // drop "rdc"
    const flags: string[] = [];
    const parts: string[] = [];
    let node = ROOT_CMD;
    let started = false;

    for (const token of tokens) {
      if (token.startsWith('-')) {
        flags.push(token.split('=')[0].replace(/[.,;:)\]]+$/, ''));
        continue;
      }
      // ★ A COMMAND NAME IS ASCII. Japanese, Korean and Arabic attach punctuation and grammatical
      // particles DIRECTLY to it with no space — `rdc subscription login。`, `rdc repo sync를`,
      // `rdc subscription login،`. Splitting on whitespace yields `login。` / `sync를`, which
      // resolve to nothing, so the gate reported CORRECT Japanese and Korean as stale commands.
      // Take the leading ASCII run: anything non-ASCII glued to a command name is foreign
      // punctuation, never part of the name.
      const clean = (token.match(/^[A-Za-z0-9-]+/) ?? [''])[0];
      // The path ends at the first token that is not a subcommand of where we are. In a locale
      // that is usually where the translated prose begins, and that is exactly right.
      const next = clean ? node.subcommands.get(clean) : undefined;
      if (!next) break;
      if (!started && !TOP_LEVEL.has(clean)) break;
      started = true;
      parts.push(clean);
      node = next;
    }

    // Only invocations that actually name a command are compared. `rdc para usar ...` names
    // nothing, so it is prose in every language, including English.
    if (parts.length > 0) {
      shapes.push(`${parts.join(' ')} [${flags.sort().join(' ')}]`);
      continue;
    }

    // ★ THE HEAD RESOLVED TO NOTHING. Two very different things look like this:
    //   (a) PROSE — `rdc para usar la versión anterior` (a Spanish preposition), or English's own
    //       `rdc --help for architecture`. Not a command, never was.
    //   (b) A DEAD NOUN — `rdc auth login`. `auth` was a real top-level command until the cloud
    //       adapter was deleted. It is the single worst string in the catalogue: the CLI telling a
    //       user to run a noun that no longer exists.
    // Skipping both (the first attempt) means the FALSE-POSITIVE FILTER BLINDS THE GATE TO ITS MOST
    // SEVERE CASE. So record the unresolved head; the caller decides, using English as the
    // discriminator: if ENGLISH names a real command for this key and the LOCALE's head names
    // nothing, the locale is stale — prose does not replace a command, a dead noun does.
    const head = tokens.find((t) => !t.startsWith('-'))?.replace(/[.,;:)\]'"]+$/, '');
    if (head && /^[a-z][a-z0-9-]*$/.test(head)) shapes.push(`?${head}`);
  }

  return shapes.sort();
}

function checkI18nCommandExamples(out: Violation[]): void {
  const localesDir = path.join(ROOT, 'packages/cli/src/i18n/locales');
  const englishFile = path.join(localesDir, 'en', 'cli.json');
  const english = flattenStrings(JSON.parse(fs.readFileSync(englishFile, 'utf-8')));

  // English: the absolute check. Every command it names must exist, with valid flags.
  for (const [key, value] of Object.entries(english)) {
    for (const { raw: invocation } of extractInvocations(value, true)) {
      const before = out.length;
      validateInvocation(`packages/cli/src/i18n/locales/en/cli.json (${key})`, 0, invocation, out);
      for (let i = out.length - 1; i >= before; i--) {
        const match = out[i].message.match(/unknown subcommand `([^`]+)`/);
        if (match && isProseToken(match[1])) out.splice(i, 1);
      }
    }
  }

  // Every other locale: parity with English.
  for (const locale of fs.readdirSync(localesDir).sort()) {
    if (locale === 'en') continue;
    const file = path.join(localesDir, locale, 'cli.json');
    if (!fs.existsSync(file)) continue;

    for (const [key, value] of Object.entries(flattenStrings(JSON.parse(fs.readFileSync(file, 'utf-8'))))) {
      const source = english[key];
      if (source === undefined) continue;

      // ★ THE RULE IS SUBSET, NOT EQUALITY: a locale must not name a command that English does
      // NOT name. Naming FEWER is a legitimate stylistic choice (a translator may mention a
      // command once where English mentions it twice). Naming something ELSE is staleness or
      // invention, and it is always a bug — the locale is teaching a command the product does
      // not document, or no longer has.
      // ★★ ONLY RESOLVED COMMANDS ARE COMPARABLE ACROSS LANGUAGES. An unresolved head (`?word`)
      // is PROSE, and prose differs by language BY CONSTRUCTION: German's "Installieren Sie rdc
      // neu" yields `?neu`, English's "with an intact rdc installation" yields `?installation`.
      // Comparing those to each other manufactures a violation on every such key, in every
      // language, forever — no matter how perfect the translation. An earlier version did exactly
      // that: 72% of its output was noise, and it would have sent translators to "fix" strings
      // that were already correct.
      const wantResolved = new Set(invocationShapes(source).filter((sh) => !sh.startsWith('?')));
      const gotResolved = invocationShapes(value).filter((sh) => !sh.startsWith('?'));

      // RULE 1 — the locale must not name a RESOLVED command English does not name.
      const extra = gotResolved.filter((shape) => !wantResolved.has(shape));

      // RULE 2 — the dead-noun test (#76), kept as its OWN check rather than folded into rule 1.
      //
      // ★ IT REQUIRES AN UNRESOLVED INVOCATION, not merely the ABSENCE of a resolved one. "The
      // locale resolves nothing" is true both when it names a DEAD NOUN (`rdc auth login`) and when
      // THE EXTRACTOR SIMPLY FAILED TO SEE THE INVOCATION. Conflating those makes every extractor
      // blind spot come out as a confident accusation against a correct translation — which is
      // exactly what happened to Chinese. So the rule fires only on POSITIVE evidence: the locale
      // HAS an `rdc …` whose head resolves to nothing, while English names a real command.
      const localeHasUnresolvedInvocation = invocationShapes(value).some((sh) => sh.startsWith('?'));
      const lostTheCommand =
        wantResolved.size > 0 && gotResolved.length === 0 && localeHasUnresolvedInvocation;

      if (extra.length === 0 && !lostTheCommand) continue;

      const detail = lostTheCommand
        ? `      ${locale} names NO live command, but en names: ${[...wantResolved].join('  ')}\n` +
          '      (a dead noun resolves to nothing — e.g. `rdc auth login` after `auth` was deleted)'
        : `      ${locale} names: ${extra.join('  ')}\n` +
          `      en names:  ${[...wantResolved].join('  ') || '(none)'}`;

      out.push({
        file: `packages/cli/src/i18n/locales/${locale}/cli.json`,
        line: 0,
        message:
          `"${key}" names a command English does not. A command name is never translated, so a ` +
          `locale can only be stale or inventing here.\n${detail}`,
        snippet: key,
      });
    }
  }
}

/** Flatten a locale document to dotted key -> string. */
function flattenStrings(node: unknown, prefix = '', out: Record<string, string> = {}): Record<string, string> {
  if (typeof node === 'string') {
    out[prefix] = node;
    return out;
  }
  if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      flattenStrings(value, prefix ? `${prefix}.${key}` : key, out);
    }
  }
  return out;
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
  const validShort = new Set<string>(['-h', '-V', '-o', '-y']);
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
    if (tok.startsWith('-')) {
      // ★ SHORT FLAGS WERE NEVER VALIDATED ("bundling-prone") — and `-m` / `-r` are EXACTLY the
      // flags the P4 ref concept deleted. The checker was blind to the two most-removed flags in
      // the entire phase, which is how `rdc repo sync upload -m MACHINE -r REPO` survived in a
      // user-facing string. A SINGLE-letter short flag cannot be a bundle, so it is checkable;
      // multi-letter clusters (`-abc`) still are not, and are skipped.
      const short = tok.match(/^-([A-Za-z])$/);
      if (short && !node.shortFlags.has(`-${short[1]}`) && !validShort.has(`-${short[1]}`)) {
        const cmd = `rdc ${pathParts.join(' ')}`.trim();
        out.push({
          file,
          line,
          command: raw,
          message: `\`${cmd}\`: unknown short flag \`-${short[1]}\``,
        });
      }
      continue;
    }
    // Command-position word.
    const sub = node.subcommands.get(tok);
    if (sub) {
      node = sub;
      pathParts.push(tok);
      for (const f of node.longFlags) validFlags.add(f);
      for (const f of node.shortFlags) validShort.add(f);
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

/**
 * Extract candidate `rdc ...` invocations, with line numbers.
 *
 * `shellFile` switches the whole file into code mode. A markdown file only has
 * commands inside fences and backtick spans, but a SHELL SCRIPT is code on every
 * line and has neither. Reading a `.sh` with the markdown rules finds nothing —
 * which meant that simply adding `.ci/tutorials` to the globs would have been a
 * FALSE FIX: 337 `rdc` calls "covered" by a scanner that never looked at one of
 * them, and a green gate over a directory of scripts that no longer run.
 */
function extractInvocations(content: string, shellFile = false): { line: number; raw: string }[] {
  const lines = content.split('\n');
  const found: { line: number; raw: string }[] = [];
  let inFence = false;
  let fenceLang = '';
  const SHELL_LANGS = new Set(['', 'bash', 'sh', 'shell', 'console', 'zsh']);

  const pushFrom = (text: string, lineNo: number) => {
    // Normalize ./rdc.sh -> rdc and strip a leading prompt.
    const norm = text.replace(/\.\/rdc\.sh/g, 'rdc');
    // The preceding character may be a QUOTE. Shell scripts wrap commands in
    // helpers (`run_cmd "rdc repo up shop"`, and those strings are eval'd), so a
    // regex that only accepted start/space/backtick/paren skipped the majority of
    // the calls in .ci/tutorials — the gate would have gone green over scripts
    // that still failed at runtime. Covering a file is not the same as reading it.
    // ★ NOT AN ALLOWLIST OF DELIMITERS. This used to enumerate the characters allowed before `rdc`
    // (space, backtick, paren, quote) — and Chinese writes `请使用以下命令创建：rdc config init`, with a
    // FULL-WIDTH COLON and no space. `rdc` was therefore never extracted, the locale resolved no
    // command, and the dead-noun rule LAUNDERED THAT EXTRACTION MISS INTO A CONFIDENT ACCUSATION
    // that correct Chinese was stale. Every CJK and Arabic string was exposed to the same failure.
    // The real property is simply: `rdc` is a standalone token, i.e. not preceded by a word
    // character. State the property; do not enumerate the exceptions.
    const re = /(?<![\w-])rdc\s+[^\n`]*/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(norm))) {
      // ★ The strip class MUST match the match class. It did not: the match class was widened
      // to accept a QUOTE before `rdc` (for `run_cmd "rdc ..."`), but this strip still only
      // removed whitespace/backtick/paren — so a quoted invocation was matched, kept its leading
      // quote, failed `startsWith('rdc')`, and WAS SILENTLY DISCARDED. The scanner reported zero
      // and had looked at nothing. Half a fix is a fresh blind spot.
      const before = m.index > 0 ? norm[m.index - 1] : '';
      const opener = before === '"' || before === "'" ? before : '';
      let raw = m[0].trim();

      // ★ A QUOTED invocation ENDS AT ITS CLOSING QUOTE. Without this, `run_cmd "rdc config show"`
      // yields the token `show"` and the checker reports an unknown subcommand for a command that
      // is perfectly correct — the closing delimiter is not part of the command. A gate that
      // invents defects is as useless as one that misses them.
      if (opener === '"' || opener === "'") {
        const close = raw.indexOf(opener);
        if (close !== -1) raw = raw.slice(0, close).trim();
      }

      if (raw.startsWith('rdc')) found.push({ line: lineNo, raw });
    }
  };

  if (shellFile) {
    lines.forEach((lineText, idx) => {
      // Every line is code. Strip comments so prose in a `# …` note is not parsed.
      pushFrom(lineText.replace(/(^|\s)#.*$/, ''), idx + 1);
    });
    return found;
  }

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

/**
 * Files this validator reads, recursively.
 *
 * ★ Shell scripts are in scope, and that is not a nicety. `.ci/tutorials/` holds
 * ~14 EXECUTABLE scripts making 337 `rdc` calls, and they were in no glob here:
 * this validator only ever read `.md`, and only at the top level of a directory.
 * So when P4 deleted `term connect -m/-r`, those scripts started FAILING AT
 * RUNTIME and no gate said a word — the docs checker could not see the one kind
 * of file where a stale command is not a typo but a broken build. A validator's
 * blind spot is indistinguishable from a passing check.
 */
function listCheckableFiles(dir: string): string[] {
  const abs = path.join(ROOT, dir);
  if (!fs.existsSync(abs)) return [];

  const out: string[] = [];
  const walk = (relDir: string): void => {
    for (const entry of fs.readdirSync(path.join(ROOT, relDir), { withFileTypes: true })) {
      const rel = path.join(relDir, entry.name);
      if (entry.isDirectory()) {
        if (!EXCLUDED_DIRS.some((dir) => rel === dir || rel.startsWith(`${dir}/`))) walk(rel);
        continue;
      }
      const checkable = entry.name.endsWith('.md') || entry.name.endsWith('.sh');
      if (!checkable || EXCLUDE_FILES.has(entry.name)) continue;
      if (isGenerated(path.join(ROOT, rel))) continue;
      out.push(rel);
    }
  };
  walk(dir);
  return out;
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

/**
 * Every RENAMES target must be a command that actually exists.
 *
 * `--fix` REWRITES FILES from this map, so a stale target does not merely fail to
 * help: it edits correct documentation into broken documentation. That had already
 * happened (P4 reversed `machine query` -> `machine status`, and the map still
 * pointed the old way), so the invariant is asserted rather than commented.
 */
function assertRenameTargetsExist(): void {
  const valid = validCommandPaths();
  const dead = Object.entries(RENAMES)
    .filter(([, to]) => !valid.has(to))
    .map(([from, to]) => `  "${from}" -> "${to}" (target does not exist)`);

  if (dead.length > 0) {
    console.error(
      'check-cli-docs: RENAMES points at commands that do not exist. `--fix` would ' +
        'rewrite correct docs into broken ones:\n' +
        dead.join('\n')
    );
    process.exit(1);
  }
}

function main(): void {
  assertRenameTargetsExist();

  // ★ `--locales-only` runs ONLY the i18n checks (English absolute + per-locale command parity)
  // and skips the doc globs. It exists because the doc scan carries 309 SANCTIONED-RED www
  // violations (deferred to P7), and burying the i18n answer inside them makes the instrument
  // unreadable exactly when someone needs to read it. Same code, same source of truth — no second
  // copy of the logic, because a fourth hand-copy is the bug this repo has now found six times.
  if (process.argv.includes('--locales-only')) {
    const violations: Violation[] = [];
    checkI18nCommandKeys(violations);
    checkI18nCommandExamples(violations);

    if (violations.length === 0) {
      console.log('\x1b[32m✓\x1b[0m CLI i18n command parity holds (English absolute + 12 locales)');
      return;
    }

    console.error(
      `\x1b[31m✗\x1b[0m ${violations.length} CLI-command violation(s) in the i18n catalogue:\n`
    );
    for (const v of violations) {
      console.error(`  ${v.file}: ${v.message}`);
    }
    console.error(
      '\n  A command name is never translated. A locale naming a command English does not is ' +
        'stale or inventing.\n'
    );
    process.exit(1);
  }
  const fix = process.argv.includes('--fix');
  const files = DOC_GLOBS.flatMap(listCheckableFiles);
  const violations: Violation[] = [];
  let fixedCount = 0;

  for (const file of files) {
    const abs = path.join(ROOT, file);
    if (fix && applyFixes(abs)) fixedCount++;
    const content = fs.readFileSync(abs, 'utf-8');
    for (const { line, raw } of extractInvocations(content, file.endsWith('.sh'))) {
      validateInvocation(file, line, raw, violations);
    }
  }

  // Also catch stale command keys in cli.json (the source of generated CLI docs).
  checkI18nCommandKeys(violations);
  checkI18nCommandExamples(violations);

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

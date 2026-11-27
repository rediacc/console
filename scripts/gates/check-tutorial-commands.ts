/**
 * Validates every RUNNABLE rdc command in the tutorial storyboards against the
 * live CLI command tree.
 *
 * WHY THIS IS ITS OWN GATE. `validate-cli-examples.ts` extracts commands from
 * raw file text. That works for markdown and shell, and fails here: each
 * storyboard scene carries TWO command fields with different contracts —
 *
 *   "command":     "rdc machine add"                              <- display LABEL
 *   "commandFull": "rdc machine add <name> --ip <ip> --user <u>"  <- RUNNABLE
 *
 * A text extractor reads the label as a command missing its positional args and
 * reports a false positive. That noise is why the storyboards were dropped from
 * the text-based gate entirely, which left 12 genuinely broken commands
 * unguarded (`repo mount --name`, `repo fork --detach`, `repo policy set --name`,
 * and a `repo admin autostart list` missing its mandatory `-m`). Dropping a
 * surface because the instrument is wrong for it is how a gate stops being a gate.
 *
 * So this gate is FIELD-AWARE by construction: it parses the JSON structurally
 * and only ever validates `card.commandFull` and `teardownCommand`. It never
 * looks at `card.command`, which is *supposed* to be abbreviated.
 *
 * These are not cosmetic strings. `teardownCommand` is EXECUTED by the recording
 * harness, and `card.commandFull` is what build-account-onboarding.ts generates
 * into the account portal's first-run flow — the command a brand-new user copies
 * and runs.
 *
 * Parsing is delegated to parseRdcCommand from the shared cli-reference-catalog,
 * the same instrument every other CLI gate uses, so "valid" means one thing
 * repo-wide and a command-tree change lands here automatically.
 *
 *
 * A SECOND RULE rides the same gate: every rdc command in a `.ci/tutorials/*.sh` script must run
 * WITHOUT waiting for input (a prompt hangs the headless asciinema recording, and `2>/dev/null || true`
 * hides the question). Which commands prompt is derived from the CLI's own command tree: an option
 * whose description says it skips a confirmation IS the command saying it prompts. Unconditional
 * ("Skip confirmation prompt") needs the bypass always; batch-only ("... for batch ...") only with --all.
 *
 * The two rules are rows of RULES; `--selftest` plants a defect per rule and requires it to be found.
 *
 * ---- gate ----
 * step: Validate tutorial commands against the live CLI and for non-interactive runs
 * needs: node
 * selftest: true
 * lane: quality-content
 * ---- end gate ----
 */

import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { parseRdcCommand } from '../../packages/www/scripts/lib/cli-reference-catalog.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const STORYBOARD_DIR = path.join(ROOT, 'packages', 'www', 'src', 'data', 'tutorial-storyboard');
const TUTORIAL_DIR = path.join(ROOT, '.ci', 'tutorials');
const TREE_PATH = path.join(ROOT, 'packages', 'cli', 'scripts', 'command-tree.json');
const I18N_PATH = path.join(ROOT, 'packages', 'cli', 'src', 'i18n', 'locales', 'en', 'cli.json');

/** Only these keys hold a runnable command. `command` is a display label. */
const RUNNABLE_KEYS = new Set(['commandFull', 'teardownCommand']);
/** "Skip confirmation prompt" / "Skip confirmation for batch operations". */
const BYPASS_RE = /\b(skip|bypass|suppress|without)\b[^.]{0,40}\bconfirmation\b/i;
/** Only these prompt when operating on many things at once. */
const BATCH_ONLY_RE = /\bbatch\b/i;

/** One finding: where, what, and why. */
interface Finding {
  where: string;
  text: string;
  why: string;
}

/** What a rule scanned, so a rule that scanned nothing is a failure and not a pass. */
interface Result {
  scanned: number;
  findings: Finding[];
}

/** A rule of the gate: a name, the run, and the advice printed under a red. */
interface TutorialRule {
  name: string;
  advice: string[];
  run: () => Result;
}

interface PromptRule {
  /** Space-joined command path, e.g. "repo delete". */
  command: string;
  /** Accepted spellings, e.g. ["-y", "--yes"]. */
  flags: string[];
  batchOnly: boolean;
}

/** A source that cannot be scanned is one finding, never a silent pass. */
const vacuous = (where: string, why: string): Result => ({
  scanned: 0,
  findings: [{ where, text: '', why }],
});

/**
 * A teardown often chains commands with `;`. Splitting means the second command
 * is checked too — one of the original 12 defects was only visible past a `;`.
 */
function splitCommands(value: string): string[] {
  return value
    .split(';')
    .map((part) => part.trim())
    .filter((part) => part.startsWith('rdc '));
}

/** Walks a storyboard, collecting runnable commands and any that fail to parse. */
function walk(node: unknown, file: string, out: Finding[], counter: { total: number }): void {
  if (Array.isArray(node)) {
    for (const item of node) walk(item, file, out, counter);
    return;
  }
  if (!node || typeof node !== 'object') return;

  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    if (RUNNABLE_KEYS.has(key) && typeof value === 'string') {
      for (const command of splitCommands(value)) {
        counter.total += 1;
        const parsed = parseRdcCommand(command);
        if (parsed.ok || parsed.reason === 'not-rdc') continue;
        // `reason` is set on every `ok: false` return in parseRdcCommand (packages/www/scripts/lib/cli-reference-catalog.js: not-rdc, unknown-global-option, unknown-command, unknown-option), but the inferred union does not tie it to `ok`, so the guard above cannot narrow it. Asserted rather than defaulted: a `?? 'unknown'` here would invent a reason if a future return path ever
        // forgot one.
        out.push({
          where: file,
          text: command,
          why: `${parsed.reason as string}${parsed.flag ? ` (${parsed.flag})` : ''}`,
        });
      }
      continue;
    }
    walk(value, file, out, counter);
  }
}

/** Rule 1 over given storyboards. */
export function storyboardFindings(boards: { file: string; json: unknown }[]): Result {
  const findings: Finding[] = [];
  const counter = { total: 0 };
  for (const b of boards) walk(b.json, b.file, findings, counter);
  return { scanned: counter.total, findings };
}

function lookup(i18n: unknown, key: string | undefined): string {
  if (!key) return '';
  let cur: unknown = i18n;
  for (const part of key.split('.')) {
    if (cur && typeof cur === 'object' && part in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[part];
    } else return '';
  }
  return typeof cur === 'string' ? cur : '';
}

function flagNames(flags: string): string[] {
  return flags
    .split(',')
    .map((f) => f.trim().split(/\s+/)[0])
    .filter((f) => f.startsWith('-'));
}

/** Walk the command tree, collecting every command that admits it prompts. */
function collectPromptRules(
  node: Record<string, unknown>,
  i18n: unknown,
  trail: string[]
): PromptRule[] {
  const out: PromptRule[] = [];
  const name = node.name as string | undefined;
  const here = name ? [...trail, name] : trail;

  for (const opt of (node.options as Record<string, unknown>[] | undefined) ?? []) {
    const desc = lookup(i18n, opt.descriptionKey as string | undefined);
    if (!BYPASS_RE.test(desc)) continue;
    out.push({
      command: here.slice(1).join(' '),
      flags: flagNames(String(opt.flags ?? '')),
      batchOnly: BATCH_ONLY_RE.test(desc),
    });
  }
  for (const sub of (node.subcommands as Record<string, unknown>[] | undefined) ?? []) {
    out.push(...collectPromptRules(sub, i18n, here));
  }
  return out;
}

/**
 * Pull every `rdc …` invocation out of a shell line, including ones wrapped in
 * `run_cmd "…"`. Stops at a shell separator or a redirection, so `2>/dev/null`
 * is never mistaken for an argument.
 */
function extractInvocations(line: string): string[] {
  const out: string[] = [];
  // Quotes are KEPT here (tokenize strips them). Excluding them truncated `rdc machine prune "$M" … --force` at the first quote, hiding the flag that was already present and reporting a false positive.
  const re = /\brdc\s+[^\n;|&<>]*/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line)) !== null) {
    const text = m[0].trim();
    if (text) out.push(text);
  }
  return out;
}

/** Split into tokens, dropping quote characters the shell would not pass along. */
function tokenize(invocation: string): string[] {
  return invocation
    .split(/\s+/)
    .map((t) => t.replace(/^["']+|["']+$/g, ''))
    .filter(Boolean);
}

/** Rule 2 over given scripts, with the prompting commands already derived (longest path first). */
export function interactiveFindings(
  rules: PromptRule[],
  scripts: { file: string; text: string }[]
): Result {
  const findings: Finding[] = [];
  let checked = 0;
  for (const s of scripts) {
    s.text.split('\n').forEach((line, idx) => {
      if (line.trimStart().startsWith('#')) return;
      for (const invocation of extractInvocations(line)) {
        const rule = rules.find(
          (r) => invocation.startsWith(`rdc ${r.command} `) || invocation === `rdc ${r.command}`
        );
        if (!rule) continue;
        if (rule.batchOnly && !/\s--all\b/.test(invocation)) continue;
        checked += 1;
        if (rule.flags.some((f) => tokenize(invocation).includes(f))) continue;
        findings.push({
          where: `${s.file}:${idx + 1}`,
          text: invocation.slice(0, 90),
          why: `\`rdc ${rule.command}\` prompts; add ${rule.flags.join(' or ')}`,
        });
      }
    });
  }
  return { scanned: checked, findings };
}

function filesIn(dir: string, ext: string): string[] {
  return readdirSync(dir)
    .filter((f) => f.endsWith(ext))
    .sort();
}

/** The prompting commands of the live CLI, longest path first so "repo admin archive purge" wins over "repo". */
function livePromptRules(): PromptRule[] {
  const tree = JSON.parse(readFileSync(TREE_PATH, 'utf-8')) as Record<string, unknown>;
  const i18n: unknown = JSON.parse(readFileSync(I18N_PATH, 'utf-8'));
  return collectPromptRules(tree, i18n, [])
    .filter((r) => r.command && r.flags.length > 0)
    .sort((a, b) => b.command.length - a.command.length);
}

const RULES: TutorialRule[] = [
  {
    name: 'storyboard commands resolve against the live CLI',
    advice: [
      'These are runnable: teardownCommand is executed by the recording harness, and',
      'card.commandFull is generated into the account portal first-run flow.',
      'Fix them against `./rdc.sh <cmd> --help`, never from memory.',
    ],
    run: () => {
      const files = filesIn(STORYBOARD_DIR, '.json');
      if (files.length === 0) {
        return vacuous(
          path.relative(ROOT, STORYBOARD_DIR),
          'no storyboards found: the directory moved or emptied'
        );
      }
      const r = storyboardFindings(
        files.map((file) => ({
          file,
          json: JSON.parse(readFileSync(path.join(STORYBOARD_DIR, file), 'utf-8')) as unknown,
        }))
      );
      // Storyboards exist but expose no runnable command: the field names changed and the walker misses them.
      if (r.scanned === 0) {
        return vacuous(
          'storyboards',
          'found 0 runnable commandFull / teardownCommand fields: the schema likely changed'
        );
      }
      return r;
    },
  },
  {
    name: 'tutorial scripts run without waiting for input',
    advice: [
      'These run headless inside asciinema. A prompt hangs the recording forever,',
      'and `2>/dev/null || true` hides the question instead of preventing it.',
    ],
    run: () => {
      const rules = livePromptRules();
      if (rules.length === 0) {
        return vacuous(
          'command tree',
          'derived ZERO prompting commands: the tree or its i18n keys moved'
        );
      }
      const files = filesIn(TUTORIAL_DIR, '.sh');
      if (files.length === 0)
        return vacuous(path.relative(ROOT, TUTORIAL_DIR), 'no tutorial scripts found');
      return interactiveFindings(
        rules,
        files.map((file) => ({ file, text: readFileSync(path.join(TUTORIAL_DIR, file), 'utf-8') }))
      );
    },
  },
];

/** The control: each rule's planted defect must be found, and its clean twin must stay silent. */
function selftest(): number {
  let bad = 0;
  const check = (label: string, ok: boolean): void => {
    console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}`);
    if (!ok) bad += 1;
  };
  const board = (cmd: string, key = 'commandFull'): { file: string; json: unknown }[] => [
    { file: 'planted.json', json: { cards: [{ [key]: cmd }] } },
  ];
  check(
    'CONTROL: a storyboard command with an unknown option is found',
    storyboardFindings(board('rdc repo list --zzz-planted-flag')).findings.length === 1
  );
  check(
    'a display label (`command`) is never validated',
    storyboardFindings(board('rdc repo list --zzz-planted-flag', 'command')).scanned === 0
  );
  check(
    'a command after `;` in a teardown is checked',
    storyboardFindings(board('rdc repo list; rdc repo list --zzz-planted-flag', 'teardownCommand'))
      .findings.length === 1
  );
  const prompts: PromptRule[] = [
    { command: 'repo delete', flags: ['-y', '--yes'], batchOnly: false },
    { command: 'repo up', flags: ['-y'], batchOnly: true },
  ];
  const script = (text: string): { file: string; text: string }[] => [{ file: 'planted.sh', text }];
  check(
    'CONTROL: a prompting command with no bypass is found, even behind 2>/dev/null || true',
    interactiveFindings(prompts, script('rdc repo delete app 2>/dev/null || true')).findings
      .length === 1
  );
  check(
    'the bypass flag clears it',
    interactiveFindings(prompts, script('rdc repo delete app -y')).findings.length === 0
  );
  check(
    'a batch-only prompt is judged only with --all',
    interactiveFindings(prompts, script('rdc repo up app')).scanned === 0 &&
      interactiveFindings(prompts, script('rdc repo up --all')).findings.length === 1
  );
  check(
    'a comment line is skipped',
    interactiveFindings(prompts, script('# rdc repo delete app')).scanned === 0
  );
  return bad;
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    console.log('tutorial commands selftest');
    const bad = selftest();
    if (bad > 0) console.error(`✗ ${bad} selftest case(s) failed`);
    process.exitCode = bad > 0 ? 1 : 0;
    return;
  }
  let failed = 0;
  for (const rule of RULES) {
    const r = rule.run();
    console.log(`Tutorial: ${rule.name}`);
    console.log('='.repeat(60));
    console.log(`Scanned ${r.scanned} command(s).`);
    if (r.findings.length === 0) {
      console.log('✓ clean');
      console.log('');
      continue;
    }
    failed += 1;
    console.error(`✗ ${r.findings.length} finding(s):`);
    for (const f of r.findings) {
      console.error(`  ${f.where}`);
      if (f.text) console.error(`    ${f.text}`);
      console.error(`    → ${f.why}`);
    }
    console.error('');
    for (const line of rule.advice) console.error(line);
    console.error('');
  }
  if (failed > 0) process.exit(1);
}

main();

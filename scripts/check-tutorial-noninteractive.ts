#!/usr/bin/env node
/**
 * Every rdc command in a tutorial script must run WITHOUT waiting for input.
 *
 * WHY. `.ci/tutorials/*.sh` are executed inside asciinema on a headless bridge
 * VM. A command that stops to ask "are you sure?" never returns, and the usual
 * shell idioms actively hide it:
 *
 *     rdc repo delete my-app 2>/dev/null || true
 *
 * `2>/dev/null` swallows the question, and `|| true` cannot rescue a process
 * that never exits. This exact line hung a re-record for six hours on tutorial
 * 2 of 18, and it was present at 34 call sites across 15 of the 19 scripts --
 * so the recorder could never have finished, no matter what else was fixed.
 *
 * No other gate can see it. `check-cli-docs` and `check-tutorial-commands` ask
 * "is this a valid rdc command", and a prompting command is perfectly valid.
 * The failure is behavioural, and it only shows up as silence.
 *
 * WHICH COMMANDS. Derived from the CLI's own command tree, never a hardcoded
 * list -- an option whose description says it skips a confirmation IS the
 * command telling us it prompts. A new prompting command is covered the day it
 * lands, and a renamed flag cannot silently drop coverage.
 *
 * Two shapes exist, and the difference matters:
 *   - unconditional ("Skip confirmation prompt")        -> always require it
 *   - batch-only    ("Skip confirmation for batch ...") -> require only with --all
 * `repo up my-app` does not prompt; `repo up --all` does. Demanding -y on every
 * `repo up` would be noise, and a noisy gate gets suppressed.
 */

import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TUTORIAL_DIR = path.join(ROOT, '.ci', 'tutorials');
const TREE_PATH = path.join(ROOT, 'packages', 'cli', 'scripts', 'command-tree.json');
const I18N_PATH = path.join(ROOT, 'packages', 'cli', 'src', 'i18n', 'locales', 'en', 'cli.json');

/** "Skip confirmation prompt" / "Skip confirmation for batch operations". */
const BYPASS_RE = /\b(skip|bypass|suppress|without)\b[^.]{0,40}\bconfirmation\b/i;
/** Only these prompt when operating on many things at once. */
const BATCH_ONLY_RE = /\bbatch\b/i;

interface Rule {
  /** Space-joined command path, e.g. "repo delete". */
  command: string;
  /** Accepted spellings, e.g. ["-y", "--yes"]. */
  flags: string[];
  batchOnly: boolean;
}

interface Violation {
  file: string;
  line: number;
  command: string;
  need: string[];
  text: string;
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
function collectRules(node: Record<string, unknown>, i18n: unknown, trail: string[]): Rule[] {
  const out: Rule[] = [];
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
    out.push(...collectRules(sub, i18n, here));
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
  // Quotes are KEPT here (tokenize strips them). Excluding them truncated
  // `rdc machine prune "$M" … --force` at the first quote, hiding the flag that
  // was already present and reporting a false positive.
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

function main(): void {
  const tree = JSON.parse(readFileSync(TREE_PATH, 'utf-8')) as Record<string, unknown>;
  const i18n: unknown = JSON.parse(readFileSync(I18N_PATH, 'utf-8'));

  // Longest command path first, so "repo admin archive purge" wins over "repo".
  const rules = collectRules(tree, i18n, [])
    .filter((r) => r.command && r.flags.length > 0)
    .sort((a, b) => b.command.length - a.command.length);

  // Anti-vacuity: if the tree stops describing its prompts, this gate is blind.
  if (rules.length === 0) {
    console.error('[31m✗[0m Derived ZERO prompting commands from the command tree.');
    console.error('  Expected options described as "Skip confirmation …".');
    console.error('  The tree or its i18n keys moved — this gate would check nothing.');
    process.exit(1);
  }

  const files = readdirSync(TUTORIAL_DIR)
    .filter((f) => f.endsWith('.sh'))
    .sort();
  if (files.length === 0) {
    console.error(`[31m✗[0m No tutorial scripts in ${path.relative(ROOT, TUTORIAL_DIR)}`);
    process.exit(1);
  }

  const violations: Violation[] = [];
  let checked = 0;

  for (const file of files) {
    const lines = readFileSync(path.join(TUTORIAL_DIR, file), 'utf-8').split('\n');
    lines.forEach((line, idx) => {
      if (line.trimStart().startsWith('#')) return;
      for (const invocation of extractInvocations(line)) {
        const rule = rules.find(
          (r) => invocation.startsWith(`rdc ${r.command} `) || invocation === `rdc ${r.command}`
        );
        if (!rule) continue;
        if (rule.batchOnly && !/\s--all\b/.test(invocation)) continue;
        checked += 1;
        const tokens = tokenize(invocation);
        if (rule.flags.some((f) => tokens.includes(f))) continue;
        violations.push({
          file,
          line: idx + 1,
          command: rule.command,
          need: rule.flags,
          text: invocation.slice(0, 90),
        });
      }
    });
  }

  console.log('Tutorial Non-Interactive Command Check');
  console.log('='.repeat(60));
  console.log(
    `${rules.length} prompting command(s) derived from the CLI; ` +
      `${checked} guarded invocation(s) across ${files.length} script(s).`
  );
  console.log('');

  if (violations.length === 0) {
    console.log('[32m✓[0m Every prompting command passes its confirmation bypass.');
    return;
  }

  console.error(`[31m✗ ${violations.length} interactive command(s) in tutorial scripts:[0m`);
  for (const v of violations) {
    console.error(`  ${v.file}:${v.line}`);
    console.error(`    ${v.text}`);
    console.error(`    → \`rdc ${v.command}\` prompts; add ${v.need.join(' or ')}`);
  }
  console.error('');
  console.error('These run headless inside asciinema. A prompt hangs the recording forever,');
  console.error('and `2>/dev/null || true` hides the question instead of preventing it.');
  process.exit(1);
}

main();

#!/usr/bin/env node
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
 */

import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { parseRdcCommand } from '../packages/www/scripts/lib/cli-reference-catalog.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const STORYBOARD_DIR = path.join(ROOT, 'packages', 'www', 'src', 'data', 'tutorial-storyboard');

/** Only these keys hold a runnable command. `command` is a display label. */
const RUNNABLE_KEYS = new Set(['commandFull', 'teardownCommand']);

interface Violation {
  file: string;
  command: string;
  reason: string;
  flag?: string;
}

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

/** Walks the JSON, collecting runnable commands and any that fail to parse. */
function walk(node: unknown, file: string, out: Violation[], counter: { total: number }): void {
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
        // `reason` is set on every `ok: false` return in parseRdcCommand
        // (packages/www/scripts/lib/cli-reference-catalog.js: not-rdc,
        // unknown-global-option, unknown-command, unknown-option), but the
        // inferred union does not tie it to `ok`, so the guard above cannot
        // narrow it. Asserted rather than defaulted: a `?? 'unknown'` here
        // would invent a reason if a future return path ever forgot one.
        out.push({ file, command, reason: parsed.reason as string, flag: parsed.flag });
      }
      continue;
    }
    walk(value, file, out, counter);
  }
}

function main(): void {
  const files = readdirSync(STORYBOARD_DIR)
    .filter((f) => f.endsWith('.json'))
    .sort();

  // Anti-vacuity: an empty scan set must fail loudly rather than print a
  // checkmark. A gate that passes because it found nothing to check is the
  // exact failure this file was written to end.
  if (files.length === 0) {
    console.error(`[31m✗[0m No storyboards found in ${path.relative(ROOT, STORYBOARD_DIR)}`);
    console.error('  The directory moved or emptied — this gate would be checking nothing.');
    process.exit(1);
  }

  const violations: Violation[] = [];
  const counter = { total: 0 };

  for (const file of files) {
    const parsed: unknown = JSON.parse(readFileSync(path.join(STORYBOARD_DIR, file), 'utf-8'));
    walk(parsed, file, violations, counter);
  }

  console.log('Tutorial Storyboard Command Validation');
  console.log('='.repeat(60));
  console.log(`Scanned ${files.length} storyboard(s), ${counter.total} runnable command(s).`);
  console.log('(card.command display labels are deliberately NOT validated.)');
  console.log('');

  // Second anti-vacuity guard: storyboards exist but expose no runnable command,
  // which means the field names changed and the walker is silently missing them.
  if (counter.total === 0) {
    console.error(`[31m✗[0m Found 0 runnable commands across ${files.length} storyboard(s).`);
    console.error('  Expected card.commandFull / teardownCommand. The schema likely changed.');
    process.exit(1);
  }

  if (violations.length === 0) {
    console.log('[32m✓[0m All storyboard commands resolve against the live CLI.');
    return;
  }

  console.error(`[31m✗ ${violations.length} invalid command(s):[0m`);
  for (const v of violations) {
    console.error(`  ${v.file}`);
    console.error(`    ${v.command}`);
    console.error(`    → ${v.reason}${v.flag ? ` (${v.flag})` : ''}`);
  }
  console.error('');
  console.error('These are runnable: teardownCommand is executed by the recording harness, and');
  console.error('card.commandFull is generated into the account portal first-run flow.');
  console.error('Fix them against `./rdc.sh <cmd> --help`, never from memory.');
  process.exit(1);
}

main();

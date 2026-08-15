#!/usr/bin/env tsx
/**
 * RECOVERY FUNCTIONS MUST NOT RECEIVE A CANCELLABLE WORK CONTEXT.
 *
 * The defect this exists to prevent was live in production code. A cold backup
 * stops every container, snapshots, then restarts them. Both restart call sites
 * passed the WORK context, which `setupSyncPushInterrupt` cancels on SIGTERM --
 * simply how systemd stops a unit. Downstream, `orch.UpServices(ctx, ...)` and a
 * 30s `context.WithTimeout(ctx, ...)` both fail instantly on a dead context, so
 * the restart was a silent no-op and **every quiesced repository stayed stopped**.
 *
 * The snapshot-CLEANUP defer a few lines below already did it correctly, with a
 * fresh `context.Background()`, and even carried a comment explaining why. The
 * restart -- which matters far more than deleting a snapshot -- did not. Two
 * neighbouring operations, one right and one wrong, is what a class-level check
 * catches and a per-site fix does not.
 *
 * WHY A GATE AND NOT JUST THE UNIT TEST. There IS a mutation-proven unit test on
 * the restart seam, and it catches this exact bug. But it protects ONE call site.
 * Nothing stopped a new recovery call site from repeating the mistake, and the
 * runtime failure is invisible: the process is being torn down, the restart
 * returns without error, and the containers are simply gone in the morning.
 *
 * THE RULE. Every non-test call to a registered recovery function must pass a
 * context rooted at `context.Background()` or `context.TODO()` -- either inline,
 * or via a local created from one. Anything else fails.
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const RENET_DIR = path.join(CONSOLE_ROOT, 'private', 'renet');

/**
 * Functions that run to UNDO something and therefore must survive the
 * cancellation of whatever they are undoing.
 *
 * Add a function here the moment it acquires that property. The cost of a wrong
 * entry is a loud failure; the cost of a missing one is containers left down.
 */
const RECOVERY_FUNCTIONS = [
  'startColdBackupRepos', // brings quiesced repositories back up after a cold backup
];

/**
 * A context expression the work path cannot cancel.
 *
 * `context.WithCancel(context.Background())` is deliberately NOT here, and that
 * exclusion is the heart of the check. It is rooted at Background, so a naive
 * "is it rooted at Background" test passes it -- but it hands someone a cancel
 * func, and in this codebase that someone is the SIGTERM handler. Being rooted
 * at Background is not the property that matters; being un-cancellable BY THE
 * OPERATION BEING UNDONE is. A timeout-derived context cannot be cancelled early
 * by the work path, so it qualifies; a WithCancel one cannot be shown to.
 */
const FRESH_ROOT = /context\.(Background|TODO)\(\)/;
const FRESH_LOCAL = /context\.WithTimeout\(\s*context\.(Background|TODO)\(\)|=\s*context\.(Background|TODO)\(\)/;

interface Finding {
  file: string;
  line: number;
  fn: string;
  arg: string;
}

/**
 * True when `ident` is a local rooted at a fresh context within `src`.
 *
 * Matches the two shapes Go actually uses: a direct assignment, and the
 * `ctx, cancel := context.WithTimeout(context.Background(), d)` pair. A derived
 * context whose PARENT is fresh is itself fresh, which is the property that
 * matters -- a deadline is fine, an inherited cancellation is not.
 */
function isRootedAtFreshContext(functionBody: string, ident: string): boolean {
  const escaped = ident.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const assign = new RegExp(`\\b${escaped}\\b[^\\n]*:?=[^\\n]*`, 'g');
  for (const m of functionBody.matchAll(assign)) {
    if (FRESH_LOCAL.test(m[0])) return true;
  }
  return false;
}

/**
 * The body of the function containing `lineIndex`.
 *
 * Scoped deliberately. The first draft searched the WHOLE FILE for the
 * identifier, so a recovery call taking the work `ctx` was cleared by an
 * unrelated `ctx, cancel := context.WithCancel(context.Background())` seventy
 * lines earlier in a different function. The planted-defect proof caught it:
 * the gate reported green on the exact bug it was written for.
 */
function enclosingFunction(lines: string[], lineIndex: number): string {
  let start = 0;
  for (let i = lineIndex; i >= 0; i--) {
    if (/^func\s/.test(lines[i])) {
      start = i;
      break;
    }
  }
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (lines[i] === '}') {
      end = i;
      break;
    }
  }
  return lines.slice(start, end + 1).join('\n');
}

/**
 * The first argument of a call whose opening paren ends at `start`.
 *
 * Depth-aware, and that is the whole point: a naive "up to the first comma or
 * paren" split truncates `context.Background()` to `context.Background(`, which
 * then fails the fresh-root test and condemns correct code. The control caught
 * exactly that.
 */
function firstArgument(line: string, start: number): string {
  let depth = 0;
  for (let i = start; i < line.length; i++) {
    const c = line[i];
    if (c === '(' || c === '[' || c === '{') depth++;
    else if (c === ')' || c === ']' || c === '}') {
      if (depth === 0) return line.slice(start, i).trim();
      depth--;
    } else if (c === ',' && depth === 0) {
      return line.slice(start, i).trim();
    }
  }
  return line.slice(start).trim();
}

/**
 * Blank out comments so prose cannot be read as code.
 *
 * A doc comment in `pkg/coldbackup/sidecar.go` reads "Read by
 * startColdBackupRepos (and the router watchdog)", and the first draft of this
 * gate reported it as a recovery call taking a work context named
 * "and the router watchdog". A checker that cannot tell a mention from a call
 * cries wolf, and a gate that cries wolf gets disabled.
 *
 * Line-based and deliberately simple: it blanks `//` to end of line and spans
 * between block-comment markers. It does not model strings containing `//`,
 * which for Go source in this repo has no false-negative consequence -- a call
 * inside a string literal is not a call either.
 */
function stripComments(lines: string[]): string[] {
  let inBlock = false;
  return lines.map((line) => {
    let out = '';
    for (let i = 0; i < line.length; i++) {
      if (inBlock) {
        if (line.startsWith('*/', i)) {
          inBlock = false;
          i++;
        }
        out += ' ';
        continue;
      }
      if (line.startsWith('//', i)) return out + ' '.repeat(line.length - i);
      if (line.startsWith('/*', i)) {
        inBlock = true;
        out += '  ';
        i++;
        continue;
      }
      out += line[i];
    }
    return out;
  });
}

function scan(files: string[]): Finding[] {
  const findings: Finding[] = [];
  for (const file of files) {
    const src = fs.readFileSync(file, 'utf-8');
    const lines = stripComments(src.split('\n'));
    for (const fn of RECOVERY_FUNCTIONS) {
      const call = new RegExp(`(?<![\\w.])${fn}\\s*\\(`, 'g');
      lines.forEach((line, i) => {
        // The declaration is not a call.
        if (new RegExp(`func\\s+${fn}\\s*\\(`).test(line)) return;
        for (const m of line.matchAll(call)) {
          const arg = firstArgument(line, m.index + m[0].length);
          if (!arg) continue;
          if (FRESH_ROOT.test(arg)) continue;
          if (isRootedAtFreshContext(enclosingFunction(lines, i), arg)) continue;
          findings.push({ file: path.relative(CONSOLE_ROOT, file), line: i + 1, fn, arg });
        }
      });
    }
  }
  return findings;
}

function goFiles(root: string): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (e.name === 'vendor' || e.name === '.git' || e.name === 'node_modules') continue;
        walk(p);
      } else if (e.name.endsWith('.go') && !e.name.endsWith('_test.go')) {
        out.push(p);
      }
    }
  };
  walk(root);
  return out;
}

/**
 * Control: prove the detector fires before believing any clean run.
 *
 * Runs on EVERY invocation, including runs where the renet submodule is absent,
 * so "nothing to scan" can never be mistaken for "nothing wrong".
 */
function runControl(): string[] {
  const failures: string[] = [];
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'recovery-ctx-'));
  try {
    const bad = path.join(dir, 'bad.go');
    fs.writeFileSync(
      bad,
      ['package main', '', 'func run(ctx context.Context) {', '\tstartColdBackupRepos(ctx, ds, repos)', '}', ''].join('\n')
    );
    if (scan([bad]).length !== 1) {
      failures.push('the detector did NOT flag a recovery call taking a work context');
    }

    const good = path.join(dir, 'good.go');
    fs.writeFileSync(
      good,
      [
        'package main',
        '',
        'func run(ctx context.Context) {',
        '\trestartCtx, cancel := context.WithTimeout(context.Background(), d)',
        '\tdefer cancel()',
        '\tstartColdBackupRepos(restartCtx, ds, repos)',
        '\tstartColdBackupRepos(context.Background(), ds, repos)',
        '}',
        '',
      ].join('\n')
    );
    if (scan([good]).length !== 0) {
      failures.push('the detector flagged a correctly-rooted context, so it would fail forever and get deleted');
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  return failures;
}

function main(): void {
  console.log('Recovery functions must not receive a cancellable work context');
  console.log('='.repeat(62));

  const controlFailures = runControl();
  if (controlFailures.length > 0) {
    for (const f of controlFailures) console.error(`${RED}✗${NC} control: ${f}`);
    console.error(`${RED}✗${NC} the detector is broken, so a clean run would mean nothing.`);
    process.exit(1);
  }
  console.log(`${GREEN}✓${NC} control fired: a work context is flagged, a fresh-rooted one is not`);

  if (!fs.existsSync(path.join(RENET_DIR, 'go.mod'))) {
    console.log(`${YELLOW}⚠${NC} SKIPPED: the renet submodule is not checked out.`);
    console.log('  The control above still ran, so this is a stated skip, not a silent pass.');
    process.exit(0);
  }

  const files = goFiles(RENET_DIR);
  const findings = scan(files);

  if (findings.length > 0) {
    for (const f of findings) {
      console.error(`  ${RED}✗${NC} ${f.file}:${f.line}  ${f.fn}(${f.arg}, …)`);
    }
    console.error('');
    console.error(`${RED}✗${NC} ${findings.length} recovery call(s) take a context that may already be cancelled.`);
    console.error('  On SIGTERM the work context is dead, every call inside fails instantly, and the');
    console.error('  repositories stay STOPPED. Route the call through a wrapper that builds its own');
    console.error('  context from context.Background() with its own timeout, as restartColdRepos does');
    console.error('  in private/renet/cmd/renet/backup_cold_restart.go.');
    process.exit(1);
  }

  console.log(
    `${GREEN}✓${NC} ${files.length} Go file(s) scanned; every call to ${RECOVERY_FUNCTIONS.length} recovery function(s) is rooted at a fresh context`
  );
  process.exit(0);
}

main();

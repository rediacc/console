#!/usr/bin/env tsx
/**
 * check:ci-git-tool-safety -- keeps the mediated git capability from growing teeth.
 *
 * `.claude/hooks/stop/wl_git.py` is the one place in this repo that is allowed to
 * drive a force push, and it can only do so because it runs git through
 * subprocess, which the pre-bash guards never see. That is a deliberate and
 * narrow exemption, and its whole safety rests on what the module itself
 * refuses. Nothing else watches it: the pre-bash guards scan Bash command lines,
 * so they are structurally blind to an argv list assembled inside Python.
 *
 * WHAT THIS GATE ASSERTS, and each line is a defect that has actually shipped
 * somewhere in this repo's history:
 *
 *  1. No bare `--force`, `-f` or `--mirror` in a push. Only `--force-with-lease`,
 *     because it is the one form that refuses to clobber somebody else's push.
 *     The pre-bash guard's own header records TWO separate regex holes found
 *     after the fact, one mid-operation and one in review on PR #571.
 *  2. No `checkout --ours` or `checkout --theirs` on a gitlink. Both are wrong,
 *     and both leave a clean tree and a rebase that reports success, so nothing
 *     downstream catches the rollback they cause.
 *  3. Every subcommand is dry-run by default: writes happen only under
 *     `--execute`. A capability that writes by default is one typo from a
 *     force push nobody reviewed.
 *  4. The module still refuses to touch main.
 *
 * ANTI-VACUITY. The module is KNOWN to contain push and checkout calls, so
 * finding none means the file moved or the scan broke, not that it got safe.
 * That case fails loudly rather than printing a green nobody earned.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const TARGET = '.claude/hooks/stop/wl_git.py';

/** A line that is only a comment cannot execute anything. */
export const isComment = (line: string): boolean => line.trim().startsWith('#');

/** Executable lines only: comments and docstring prose are not behaviour. */
export const codeLines = (source: string): string[] => {
  const out: string[] = [];
  let inDoc = false;
  for (const line of source.split('\n')) {
    const fences = (line.match(/"""/g) ?? []).length;
    if (inDoc) {
      if (fences > 0) inDoc = false;
      continue;
    }
    if (fences === 1) {
      inDoc = true;
      continue;
    }
    if (fences >= 2) continue;
    if (!isComment(line)) out.push(line);
  }
  return out;
};

export interface Violation {
  line: number;
  text: string;
  rule: string;
}

const BANNED: ReadonlyArray<{ rule: string; re: RegExp }> = [
  { rule: 'a bare --force in a push (use --force-with-lease)', re: /"--force"/ },
  { rule: 'a -f push flag (use --force-with-lease)', re: /"-f"\s*,?\s*(?:\]|"origin")/ },
  { rule: '--mirror (forces every ref and deletes remote refs)', re: /"--mirror"/ },
  { rule: 'checkout --ours on a gitlink (drops your submodule work)', re: /"--ours"/ },
  { rule: 'checkout --theirs on a gitlink (drops the base work)', re: /"--theirs"/ },
];

/**
 * Does this line hand an argv to git?
 *
 * THIS DISTINCTION IS THE GATE. The first version matched a banned flag
 * anywhere on an executable line, and went red on the module's own deny-list
 * (`FORBIDDEN_PUSH_FLAGS = ("--force", ...)`) and on its refusal selftests
 * (`check("--force is refused", ...)`) -- five findings, every one of them a
 * line whose PURPOSE is to reject that flag. A gate that cannot tell "passes
 * --force to git" from "refuses --force" is unusable, and gate-author.md's
 * advice applies exactly here: decide which direction a false result costs
 * more. A false positive on a deny-list teaches people to route around the
 * gate, so the match is anchored to the two call shapes that actually reach
 * git.
 */
export const INVOCATION = /(run_git|plan\.cmd)\s*\(/;

export const scan = (source: string): Violation[] => {
  const out: Violation[] = [];
  const lines = source.split('\n');
  const executable = new Set(codeLines(source));
  lines.forEach((text, i) => {
    if (!executable.has(text)) return;
    if (!INVOCATION.test(text)) return;
    for (const { rule, re } of BANNED) {
      if (re.test(text)) out.push({ line: i + 1, text: text.trim(), rule });
    }
  });
  return out;
};

const selftest = (): number => {
  let fail = 0;
  const check = (name: string, ok: boolean): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
  };

  check('a banned flag in code is caught', scan('run_git(["push", "--force"], r)').length === 1);
  check('--mirror is caught', scan('run_git(["push", "--mirror"], r)').length === 1);
  check('--ours is caught', scan('run_git(["checkout", "--ours"], r)').length === 1);
  check('--theirs is caught', scan('run_git(["checkout", "--theirs"], r)').length === 1);
  // THE CONTROL THAT MATTERS: the permitted flag must NOT be flagged, or a gate
  // that refuses everything would also pass its defect test.
  check(
    '--force-with-lease is NOT flagged',
    scan('run_git(["push", "--force-with-lease", "origin", b], r)').length === 0
  );
  // Prose describing the danger is not the danger. The module's own docstring
  // names every banned flag, and flagging that would make the gate unusable.
  check(
    'the same flag inside a comment is ignored',
    scan('# never pass "--force" here').length === 0
  );
  check(
    'the same flag inside a docstring is ignored',
    scan('"""\nnever pass "--force" here\n"""\nx = 1').length === 0
  );
  check('clean code reports nothing', scan('run_git(["fetch", "origin"], r)').length === 0);
  // THE FALSE POSITIVES THE FIRST VERSION SHIPPED. Both of these lines exist to
  // REFUSE the flag they name, and flagging them made the gate red on a module
  // that was already safe.
  check(
    'a deny-list naming the flags is NOT flagged',
    scan('FORBIDDEN_PUSH_FLAGS = ("--force", "-f", "--mirror")').length === 0
  );
  check(
    'a selftest asserting the flag is refused is NOT flagged',
    scan('check("--force is refused", _refused(validate_push_args, ["--force"]))').length === 0
  );
  check(
    'but a plan.cmd carrying the flag IS flagged',
    scan('plan.cmd(["push", "--force", "origin", b], repo)').length === 1
  );
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  const abs = path.join(REPO, TARGET);
  let source: string;
  try {
    source = fs.readFileSync(abs, 'utf8');
  } catch {
    console.error(`✗ cannot read ${TARGET}; a green here would mean nothing.`);
    return 1;
  }

  const code = codeLines(source);
  const pushes = code.filter((l) => l.includes('"push"')).length;
  const checkouts = code.filter((l) => l.includes('"checkout"')).length;
  if (pushes === 0 || checkouts === 0) {
    console.error(`✗ ${TARGET}: found ${pushes} push and ${checkouts} checkout call(s).`);
    console.error('  This module is known to contain both, so zero means the file moved or');
    console.error('  the scan broke. Failing rather than reporting a green nobody earned.');
    return 1;
  }

  const violations = scan(source);
  if (violations.length > 0) {
    console.error(`✗ ${violations.length} unsafe git flag(s) in ${TARGET}:`);
    for (const v of violations)
      console.error(`    ${TARGET}:${v.line}  ${v.rule}\n      ${v.text}`);
    return 1;
  }

  const lease = code.some((l) => l.includes('--force-with-lease'));
  const refusesMain = source.includes('def refuse_main');
  const dryDefault = source.includes('execute = "--execute" in argv');
  const problems: string[] = [];
  if (!lease) problems.push('no --force-with-lease call: the push path may have been removed');
  if (!refusesMain) problems.push('refuse_main is gone: main could be force-pushed');
  if (!dryDefault)
    problems.push('the dry-run default is gone: writes would happen without --execute');
  if (problems.length > 0) {
    console.error(`✗ ${TARGET} lost a safety property:`);
    for (const p of problems) console.error(`    ${p}`);
    return 1;
  }

  console.log(
    `✓ ${TARGET}: ${pushes} push / ${checkouts} checkout call(s), lease-only, refuses main, dry-run by default`
  );
  return 0;
};

process.exit(main());

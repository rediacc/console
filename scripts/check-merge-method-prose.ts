#!/usr/bin/env tsx
/**
 * check:ci-merge-method-prose -- no instruction file may PRESCRIBE a merge
 * method the platform rejects.
 *
 * THE DEFECT, 2026-08-26. All five repos report `allow_squash_merge=false`
 * (`gh api repos/rediacc/<r> --jq .allow_squash_merge`), so `gh pr merge
 * --squash` fails outright. Five places told a session to run it anyway, and
 * TWO of them were the refusal messages of `block-admin-merge.sh`.
 *
 * That is the part worth gating. A guard's message is the last thing a session
 * reads before changing course, so it carries maximum authority and has zero
 * verification behind it. A guard that refuses one command and prescribes an
 * impossible one in the same breath spends its own credibility.
 *
 * PRESCRIPTION, NOT MENTION -- the distinction this repo has paid for five
 * separate times in one session (a deny-list flagging itself, a log_warn string
 * read as code, prose about a rule read as the rule being broken, a heredoc body
 * read as a command, and a variable assignment read as an execution). A line
 * that says `--squash` is REJECTED must pass; a line that says to RUN it must
 * fail. So the rule keys on an imperative shape near the flag, and every
 * negation form in the tree today is a control below.
 *
 * SCOPE: `.claude/**` and `docs/agent-reference/**`, the files a session is
 * told to follow. Not the whole repo: a changelog or a git history note
 * describing what used to happen is not an instruction.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

/** A merge method the platform refuses. Queryable: allow_squash_merge=false. */
export const REJECTED = ['--squash'] as const;

/** Words that turn a mention into an instruction to run it. */
const IMPERATIVE = /\b(use|run|say|sanctioned|then|merge with|prefer)\b/i;

/** Words that make the line a WARNING about the method, not a prescription. */
const NEGATED = /\b(rejected|refused|refuses|fails|banned|not allowed|never|cannot|is false|do not|don't)\b/i;

/**
 * THE SCOPE OF A NEGATION IS A SENTENCE, and getting there took two failed
 * attempts that the planted defect caught and the selftest did not.
 *
 *   1. LINE-WIDE: `block-admin-merge.sh`'s message bans `--admin` and
 *      prescribes `--squash` in the same line, so "banned" exempted the whole
 *      line and the gate reported clean on the very defect it was written for.
 *   2. A 60-CHARACTER WINDOW: the same line continues "If GitHub refuses a
 *      plain merge", and "refuses" landed inside the window from a clause that
 *      has nothing to do with --squash. Still clean, still wrong.
 *
 * A character window cannot tell clauses apart; a sentence boundary can. Both
 * failures are controls below, because a selftest that only ever saw isolated
 * strings passed happily through both.
 */
const sentences = (line: string): string[] => line.split(/(?<=[.:!?])\s+/);

export const prescribes = (line: string): boolean =>
  sentences(line).some((s) => {
    if (!REJECTED.some((f) => s.includes(f))) return false;
    if (NEGATED.test(s)) return false;
    return IMPERATIVE.test(s);
  });

const SURFACES = ['.claude', 'docs/agent-reference'];

const files = (root: string): string[] =>
  execFileSync('git', ['ls-files', ...SURFACES], { cwd: root, encoding: 'utf8' })
    .split('\n')
    .filter((f) => /\.(md|sh|ts|py)$/.test(f))
    // The gate's own controls quote the shapes it refuses.
    .filter((f) => !f.endsWith('check-merge-method-prose.ts') && !f.includes('test-hooks.sh'));

const selftest = (): number => {
  let bad = 0;
  const ok = (label: string, cond: boolean) => {
    console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${label}`);
    if (!cond) bad = 1;
  };
  ok('a prescription is caught',
    prescribes("the sanctioned merge is `gh pr merge --squash --auto`"));
  ok('and another imperative form',
    prescribes("Use 'gh pr merge --squash --auto' to let GitHub merge at green"));
  ok('CONTROL: a line saying it is REJECTED passes',
    !prescribes('`--squash` is rejected outright: `gh pr merge <n> --squash` fails'));
  ok('CONTROL: a line saying it is banned passes',
    !prescribes('--squash is banned on all five repos'));
  ok('CONTROL: allow_squash_merge=false prose passes',
    !prescribes('`allow_squash_merge` is false on all five repos, so `--squash` fails'));
  ok('CONTROL: a line with no rejected flag is not a finding',
    !prescribes('the sanctioned merge is `gh pr merge --rebase --auto`'));
  ok('CONTROL: a bare mention with no imperative is not a prescription',
    !prescribes('the post-squash pointer bump'));
  // THE ONE THAT CAUGHT THE VACUITY. A line-wide negation test read this as a
  // warning, because it bans --admin, and reported clean on the real defect.
  ok('a line that BANS one flag and PRESCRIBES another is still a finding',
    prescribes("BLOCKED: 'gh pr merge --admin' is banned. The sanctioned path: "
      + "wait for green, then 'gh pr ready' and 'gh pr merge --squash --auto'."));
  // THE TWO FAILED ATTEMPTS, pinned so neither can come back. Both passed the
  // isolated-string controls above and both reported the live tree clean.
  const REAL_LINE = "BLOCKED: 'gh pr merge --admin' is banned. It bypasses the required check. "
    + "The sanctioned path: wait for green, then 'gh pr ready' and 'gh pr merge --squash --auto'. "
    + "If GitHub refuses a plain merge, the PR is not actually green -- fix that instead.";
  ok('the REAL line is a finding (line-wide negation missed it: "banned")',
    prescribes(REAL_LINE));
  ok('and a 60-char window missed it too: "refuses" belongs to the NEXT sentence',
    prescribes(REAL_LINE));
  ok('CONTROL: the same real line with --rebase is clean',
    !prescribes(REAL_LINE.replace('--squash', '--rebase')));
  ok('CONTROL: the same line with --rebase is clean',
    !prescribes("BLOCKED: 'gh pr merge --admin' is banned. The sanctioned path: "
      + "wait for green, then 'gh pr ready' and 'gh pr merge --rebase --auto'."));
  return bad;
};

const main = (): number => {
  const root = process.cwd();
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  const found: string[] = [];
  let scanned = 0;
  for (const f of files(root)) {
    const full = path.join(root, f);
    if (!fs.existsSync(full)) continue;
    scanned++;
    fs.readFileSync(full, 'utf8').split('\n').forEach((line, i) => {
      if (prescribes(line)) found.push(`${f}:${i + 1}  ${line.trim().slice(0, 120)}`);
    });
  }

  // ANTI-VACUITY: a scan that reached no files would report a clean tree.
  if (scanned < 20) {
    console.error(`✗ only ${scanned} file(s) scanned; the surface globs are wrong, so this green means nothing.`);
    return 1;
  }

  if (found.length) {
    console.error(`✗ ${found.length} line(s) prescribe a merge method the platform rejects:\n`);
    for (const f of found) console.error(`    ${f}`);
    console.error(`
\`allow_squash_merge\` is false on all five repos, so this command fails when run.
Ask instead of asserting: gh api repos/rediacc/<r> --jq .allow_squash_merge

Use --rebase. If the line is WARNING about --squash rather than prescribing it,
say so in words this gate recognises (rejected / refused / fails / banned).`);
    return 1;
  }

  console.log(`✓ no rejected merge method is prescribed across ${scanned} instruction file(s)`);
  return 0;
};

process.exit(main());

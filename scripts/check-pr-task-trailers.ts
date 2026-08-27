#!/usr/bin/env tsx
/**
 * check:ci-pr-task-trailers -- every commit in a PR names the epic it belongs to.
 *
 * WHY. The review runs once per epic and selects that epic's commits with
 * `git log --grep='^PR-TASK: <id>'`. A commit carrying no trailer belongs to no
 * epic, so no review pass ever looks at it, and nothing says so. An unreviewed
 * change that nobody knows is unreviewed is strictly worse than a red gate.
 *
 * WHY CI AND NOT JUST THE HOOK. The local guard
 * (.claude/hooks/pre-bash/block-untagged-commit.sh) sees only the raw Bash
 * string, so `git commit -F file` and a command-substituted message are opaque
 * to it, and it deliberately allows what it cannot read rather than refusing a
 * commit it cannot judge. This is where the rule is actually enforced, against
 * the commits that really landed.
 *
 * IDS ARE CHECKED AGAINST THE PUBLISHED SNAPSHOT, not merely for shape. A typo'd
 * id is worse than a missing one: it looks tagged, passes a shape check, and
 * routes the commit to an epic that does not exist, so it is reviewed by nobody
 * while appearing accounted for.
 *
 * FAILS CLOSED. An unreadable commit list is not evidence that the commits are
 * tagged. check-claude-attribution.sh takes the same stance for the same reason
 * and even treats an empty list as a failed read.
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** A trailer must START a line; prose mentioning the token is not a trailer. */
export const trailerIds = (message: string): string[] => {
  const out: string[] = [];
  const re = /^[ \t]*PR-TASK:[ \t]*([0-9a-f]{6,32})[ \t]*$/gim;
  let m: RegExpExecArray | null;
  while ((m = re.exec(message)) !== null) out.push(m[1]);
  return out;
};

export const knownEpicIds = (snapshot: string): string[] => {
  const out: string[] = [];
  const re = /^`?PR-TASK:\s*([0-9a-f]{6,32})`?\s*$/gim;
  let m: RegExpExecArray | null;
  while ((m = re.exec(snapshot)) !== null) out.push(m[1]);
  return out;
};

export interface Verdict {
  sha: string;
  subject: string;
  problem: 'untagged' | 'unknown-epic';
  id?: string;
}

export const judge = (commits: { sha: string; message: string }[], known: string[]): Verdict[] => {
  const out: Verdict[] = [];
  for (const c of commits) {
    const subject = c.message.split('\n')[0].slice(0, 72);
    const ids = trailerIds(c.message);
    if (ids.length === 0) {
      out.push({ sha: c.sha, subject, problem: 'untagged' });
      continue;
    }
    for (const id of ids) {
      if (!known.includes(id)) out.push({ sha: c.sha, subject, problem: 'unknown-epic', id });
    }
  }
  return out;
};

const selftest = (): number => {
  let fail = 0;
  const check = (name: string, ok: boolean): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
  };

  check('a trailer on its own line is read', trailerIds('feat: x\n\nPR-TASK: abc123').length === 1);
  check('an indented trailer is read', trailerIds('feat: x\n\n  PR-TASK: abc123').length === 1);
  // CONTROL: the false positive that would make this gate useless in reverse.
  check(
    'prose mentioning it is NOT a trailer',
    trailerIds('feat: x, see PR-TASK docs').length === 0
  );
  check('mid-line is NOT a trailer', trailerIds('feat: x PR-TASK: abc123').length === 0);
  check('a short id is not accepted', trailerIds('PR-TASK: ab').length === 0);

  const known = ['abc123', 'def456'];
  check(
    'a tagged, known commit is clean',
    judge([{ sha: 's1', message: 'feat: x\n\nPR-TASK: abc123' }], known).length === 0
  );
  check(
    'an untagged commit is caught',
    judge([{ sha: 's1', message: 'feat: x' }], known)[0].problem === 'untagged'
  );
  // A typo'd id is the dangerous case: it LOOKS tagged.
  check(
    'a typo id is caught as unknown-epic',
    judge([{ sha: 's1', message: 'feat: x\n\nPR-TASK: aaa999' }], known)[0].problem ===
      'unknown-epic'
  );
  // Both trailers must be validated, not just the first. 'bbb111' is hex-shaped
  // and unknown; a non-hex id would never have been read as a trailer at all,
  // which is how the first version of this control passed vacuously.
  check(
    'several trailers all validated',
    judge([{ sha: 's1', message: 'x\n\nPR-TASK: abc123\nPR-TASK: bbb111' }], known).length === 1
  );
  check('no commits yields no verdicts', judge([], known).length === 0);
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  const branch =
    process.env.PR_HEAD_REF ||
    process.env.GITHUB_HEAD_REF ||
    (() => {
      try {
        return execFileSync('git', ['branch', '--show-current'], { encoding: 'utf8' }).trim();
      } catch {
        return '';
      }
    })();

  if (!branch || branch === 'main') {
    console.log(`- skipped: on ${branch || 'an unknown branch'}; trailers are a PR artefact`);
    return 0;
  }

  const snapPath = path.join(REPO, 'agent', 'pr', `${branch.replace(/\//g, '-')}.md`);
  if (!fs.existsSync(snapPath)) {
    console.error(`✗ no snapshot at agent/pr/${branch.replace(/\//g, '-')}.md`);
    console.error('  Without it there is no set of valid epic ids to check trailers against.');
    console.error(`  Run: worklist.py --publish <me> ${branch}`);
    return 1;
  }
  const known = knownEpicIds(fs.readFileSync(snapPath, 'utf8'));
  if (known.length === 0) {
    console.error('✗ the snapshot declares no epic, so no trailer could ever be valid.');
    return 1;
  }

  // Local range against origin/main; in CI the PR base is authoritative.
  const base = process.env.PR_BASE_REF || 'origin/main';

  // THE BASE REF MUST EXIST, AND IN CI IT OFTEN DOES NOT. `PR_BASE_REF` was set
  // correctly (`origin/main`) and the gate still died with
  // `fatal: ambiguous argument 'origin/main..HEAD': unknown revision` -- because
  // the PR checkout simply had not fetched that ref. Green on every developer
  // machine, where origin/main is always present; red in CI for a reason that
  // names the RANGE and not the missing fetch.
  //
  // So the gate carries its own precondition rather than trusting a workflow
  // step to have arranged it: a future edit to the checkout cannot silently
  // take this gate down with it. One fetch, best-effort, only when the ref is
  // genuinely absent.
  const resolves = (ref: string): boolean => {
    try {
      execFileSync('git', ['rev-parse', '--verify', '--quiet', `${ref}^{commit}`], {
        cwd: REPO,
        stdio: 'ignore',
      });
      return true;
    } catch {
      return false;
    }
  };
  if (!resolves(base)) {
    const remoteRef = base.startsWith('origin/') ? base.slice('origin/'.length) : base;
    try {
      execFileSync('git', ['fetch', '--no-tags', '--depth=200', 'origin', remoteRef], {
        cwd: REPO,
        stdio: 'ignore',
      });
    } catch {
      // Reported below by the range read, with the base named.
    }
    if (!resolves(base)) {
      console.error(`✗ base ref ${base} does not exist here, and fetching it failed.`);
      console.error('  The commit range cannot be computed, so no trailer can be judged.');
      console.error('  Failing closed: an unreadable range is not evidence the commits are tagged.');
      return 1;
    }
  }

  let raw: string;
  try {
    raw = execFileSync('git', ['log', `${base}..HEAD`, '--format=%H%x1f%B%x1e', '--no-merges'], {
      encoding: 'utf8',
      cwd: REPO,
    });
  } catch (err) {
    console.error(
      `✗ could not read the commit range ${base}..HEAD: ${(err as Error).message.split('\n')[0]}`
    );
    console.error('  Failing closed: an unreadable range is not evidence the commits are tagged.');
    return 1;
  }

  const commits = raw
    .split('\x1e')
    .map((r) => r.trim())
    .filter(Boolean)
    .map((r) => {
      const [sha, message] = r.split('\x1f');
      return { sha: (sha || '').trim(), message: message || '' };
    });

  if (commits.length === 0) {
    console.log(`- skipped: no commits in ${base}..HEAD`);
    return 0;
  }

  const bad = judge(commits, known);
  if (bad.length > 0) {
    console.error(
      `✗ ${bad.length} of ${commits.length} commit(s) are not attributable to an epic:`
    );
    for (const v of bad) {
      const why =
        v.problem === 'untagged'
          ? 'no PR-TASK trailer'
          : `PR-TASK: ${v.id} names no epic in the snapshot`;
      console.error(`    ${v.sha.slice(0, 9)}  ${why}\n      ${v.subject}`);
    }
    console.error('');
    console.error('  The review runs per epic and selects commits by trailer, so these would be');
    console.error('  reviewed by nobody. Known epics:');
    for (const k of known) console.error(`    ${k}`);
    return 1;
  }

  console.log(`✓ all ${commits.length} commit(s) name a known epic (${known.length} epic(s))`);
  return 0;
};

process.exit(main());

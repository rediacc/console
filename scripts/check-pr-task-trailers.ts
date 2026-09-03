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
 * string. As of 2026-08-27 it reads more of it than it used to -- a heredoc body
 * is in the command, and a `-F <file>` is on disk -- but a piped stdin and a
 * command-substituted message remain genuinely opaque, and it allows those
 * rather than refusing a commit it cannot judge. It also never sees a commit
 * made outside the model's Bash tool. This is where the rule is actually
 * enforced, against the commits that really landed.
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
import os from 'node:os';
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

  // BASE-REF RESOLUTION, the CI-only failure this gate died on: PR_BASE_REF was
  // set correctly and the ref was still absent from the checkout, so the gate
  // reported an "ambiguous argument" about the RANGE and said nothing about the
  // missing fetch. Both directions, against real git rather than a stub -- a
  // stub would only prove the helper's arithmetic, and the defect was that the
  // ref genuinely was not there.
  const canResolve = (ref: string): boolean => {
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
  check('a ref that exists resolves', canResolve('HEAD'));
  check(
    'CONTROL: a ref that cannot exist does NOT resolve, so the guard can fire',
    !canResolve('origin/zzz-no-such-ref-ever')
  );

  // THE SYNTHETIC MERGE COMMIT, and why `--no-merges` did not save us from it.
  // On PR #579 this gate reported GitHub's `refs/pull/N/merge` commit as an
  // untagged commit. The reflex reading is "--no-merges is missing"; it was
  // there. `--no-merges` counts PARENTS, and in a depth-1 checkout the merge
  // commit's parents are grafted away, so git sees a parentless root.
  //
  // Both directions against real git, in a scratch repo: a two-parent commit IS
  // excluded, and a parentless commit whose subject reads exactly like a merge
  // is NOT. Without the second control the fix below (name the tip explicitly)
  // looks like belt-and-braces instead of the actual repair.
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'prtask-'));
  const g = (...args: string[]): string =>
    execFileSync('git', args, { cwd: scratch, encoding: 'utf8' }).trim();
  try {
    g('init', '-q', '-b', 'main');
    g('config', 'user.email', 'g@example.invalid');
    g('config', 'user.name', 'gate');
    const empty = execFileSync('git', ['hash-object', '-t', 'tree', '-w', '--stdin'], {
      cwd: scratch,
      encoding: 'utf8',
      input: '',
    }).trim();
    const a = g('commit-tree', empty, '-m', 'a');
    const b = g('commit-tree', empty, '-p', a, '-m', 'b');
    const realMerge = g('commit-tree', empty, '-p', a, '-p', b, '-m', 'Merge b into a');
    const graftedMerge = g('commit-tree', empty, '-m', `Merge ${b} into ${a}`);
    const listed = (tip: string): string =>
      execFileSync('git', ['log', tip, '--no-merges', '--format=%s'], {
        cwd: scratch,
        encoding: 'utf8',
      });
    check(
      'a REAL merge commit is excluded by --no-merges',
      !listed(realMerge).split('\n').includes('Merge b into a')
    );
    check(
      'CONTROL: a PARENTLESS commit that reads as a merge is NOT excluded -- the #579 defect',
      listed(graftedMerge).startsWith('Merge ')
    );
    // The merge-base precondition, which stops a too-shallow range from
    // inventing findings instead of naming the missing depth.
    const orphan = g('commit-tree', empty, '-m', 'orphan');
    const hasBase = (x: string, y: string): boolean => {
      try {
        execFileSync('git', ['merge-base', x, y], { cwd: scratch, stdio: 'ignore' });
        return true;
      } catch {
        return false;
      }
    };
    // A BARE `git fetch origin <branch>` DOES NOT ALWAYS CREATE origin/<branch>.
    // It updates the remote-tracking ref only when the fetched ref matches
    // remote.origin.fetch, and actions/checkout configures a NARROW refspec on
    // a PR. Both directions against real git, because the whole tip fix rests
    // on this: with a narrow refspec the bare form leaves the tracking ref
    // absent, and the explicit form creates it.
    // The scratch repo's commits were built with commit-tree, so no branch
    // points at them yet; the fetch below needs a real refs/heads/main.
    g('branch', '-f', 'main', b);
    const narrow = fs.mkdtempSync(path.join(os.tmpdir(), 'prtask-clone-'));
    try {
      execFileSync('git', ['init', '-q', '-b', 'main', narrow], { stdio: 'ignore' });
      const n = (...args: string[]): void => {
        execFileSync('git', ['-C', narrow, ...args], { stdio: 'ignore' });
      };
      n('remote', 'add', 'origin', scratch);
      // The shape actions/checkout leaves behind: one refspec, not refs/heads/*.
      n('config', 'remote.origin.fetch', '+refs/heads/nothing:refs/remotes/origin/nothing');
      const tracks = (): boolean => {
        try {
          execFileSync('git', ['-C', narrow, 'rev-parse', '--verify', '--quiet', 'origin/main'], {
            stdio: 'ignore',
          });
          return true;
        } catch {
          return false;
        }
      };
      execFileSync('git', ['-C', narrow, 'fetch', '--no-tags', 'origin', 'main'], {
        stdio: 'ignore',
      });
      check('CONTROL: a BARE fetch under a narrow refspec leaves origin/main absent', !tracks());
      execFileSync(
        'git',
        ['-C', narrow, 'fetch', '--no-tags', 'origin', '+refs/heads/main:refs/remotes/origin/main'],
        { stdio: 'ignore' }
      );
      check('an EXPLICIT refspec creates it, which is what the gate now sends', tracks());
    } finally {
      fs.rmSync(narrow, { recursive: true, force: true });
    }

    check('two commits on one history share a merge base', hasBase(a, b));
    check('CONTROL: two unrelated roots do NOT, so the precondition can fire', !hasBase(b, orphan));
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true });
  }

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
      // AN EXPLICIT REFSPEC, not a bare branch name. `git fetch origin main`
      // only updates refs/remotes/origin/main when the fetched ref matches
      // remote.origin.fetch, and actions/checkout configures a NARROW refspec
      // (refs/pull/N/merge on a PR). A bare fetch there succeeds, writes
      // FETCH_HEAD, leaves origin/main absent -- and this gate would then fail
      // closed on every PR for a reason that reads like a broken checkout.
      execFileSync(
        'git',
        [
          'fetch',
          '--no-tags',
          '--depth=200',
          'origin',
          `+refs/heads/${remoteRef}:refs/remotes/origin/${remoteRef}`,
        ],
        { cwd: REPO, stdio: 'ignore' }
      );
    } catch {
      // Reported below by the range read, with the base named.
    }
    if (!resolves(base)) {
      console.error(`✗ base ref ${base} does not exist here, and fetching it failed.`);
      console.error('  The commit range cannot be computed, so no trailer can be judged.');
      console.error(
        '  Failing closed: an unreadable range is not evidence the commits are tagged.'
      );
      return 1;
    }
  }

  // AND SO MUST THE TIP, which is the failure that actually landed. Measured on
  // PR #579, run 33077…: this gate reported `1 of 1 commit(s) are not
  // attributable`, naming `55b982fc0  Merge f05ea28fc… into d7d9fa46…`. That is
  // GitHub's SYNTHETIC merge commit -- `refs/pull/N/merge`, the thing
  // actions/checkout puts at HEAD on a pull_request event -- and it belongs to
  // no epic because no human wrote it.
  //
  // `--no-merges` was already on the log call and did not exclude it. It could
  // not: the quality-code lane checks out at the default fetch-depth 1, so the
  // merge commit's parents are GRAFTED AWAY and git sees a parentless root, not
  // a merge. The same shallowness is why the range held one commit instead of
  // the branch's thirty -- fetching the base made `origin/main` resolvable
  // without making HEAD's ancestry present.
  //
  // Fixing it in the workflow (fetch-depth: 0) would work and is the wrong
  // place: it puts this gate's precondition in a shared lane where the next
  // person tuning checkout cost silently removes it. So the gate names its own
  // tip -- the PR's real head branch, fetched if absent -- exactly as it
  // already does for the base.
  let tip = 'HEAD';
  const headRef = process.env.PR_HEAD_REF || process.env.GITHUB_HEAD_REF || '';
  if (headRef) {
    const remoteTip = `origin/${headRef}`;
    if (!resolves(remoteTip)) {
      try {
        execFileSync(
          'git',
          [
            'fetch',
            '--no-tags',
            '--depth=200',
            'origin',
            `+refs/heads/${headRef}:refs/remotes/origin/${headRef}`,
          ],
          { cwd: REPO, stdio: 'ignore' }
        );
      } catch {
        // Reported immediately below, with the ref named.
      }
    }
    if (!resolves(remoteTip)) {
      console.error(`✗ head ref ${remoteTip} does not exist here, and fetching it failed.`);
      console.error("  HEAD on a pull_request checkout is GitHub's synthetic merge commit,");
      console.error('  which carries no trailer, so judging it would report a defect nobody made.');
      console.error('  Failing closed rather than judging the wrong commits.');
      return 1;
    }
    tip = remoteTip;
  }

  // A SHALLOW `A..B` IS NOT AN ERROR, IT IS A WRONG ANSWER. Both refs above are
  // fetched at depth 200, and if their merge base falls outside that window git
  // does not complain -- it lists everything reachable from the tip, which here
  // would report main's own untagged history as this PR's fault. Ask for the
  // merge base explicitly so the failure is the missing depth, named, rather
  // than two hundred invented findings.
  try {
    execFileSync('git', ['merge-base', base, tip], { cwd: REPO, stdio: 'ignore' });
  } catch {
    console.error(`✗ ${base} and ${tip} have no common ancestor in this checkout.`);
    console.error('  Both are fetched shallow (depth 200); their merge base is deeper than that.');
    console.error('  The range would list unrelated history, so no verdict here would be true.');
    return 1;
  }

  let raw: string;
  try {
    raw = execFileSync('git', ['log', `${base}..${tip}`, '--format=%H%x1f%B%x1e', '--no-merges'], {
      encoding: 'utf8',
      cwd: REPO,
    });
  } catch (err) {
    console.error(
      `✗ could not read the commit range ${base}..${tip}: ${(err as Error).message.split('\n')[0]}`
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
    // An OPEN PR always has at least one commit, so an empty range under CI is
    // a broken range, not a clean one. Reporting "skipped" there is the shape
    // this repo calls a gate that cannot fail: it prints a success line for the
    // exact topology defect it exists to survive.
    if (headRef) {
      console.error(`✗ ${base}..${tip} is empty, but a pull request always has commits.`);
      console.error('  Something is wrong with the range, not with the branch. Refusing to');
      console.error('  report "nothing to check" for a checkout whose history is not there.');
      return 1;
    }
    console.log(`- skipped: no commits in ${base}..${tip}`);
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

/**
 * Controls for scripts/lib/github-token.ts.
 *
 * THE FIRST DEFECT THIS PINS. Four gates read a GitHub token. Three wrote
 * `process.env.GITHUB_TOKEN || process.env.GH_TOKEN` by hand; check-external-links.ts
 * read only GITHUB_TOKEN. A session with just GH_TOKEN set therefore got an
 * unauthenticated run in exactly one gate and a normal one everywhere else -- which is
 * why every local gate-suite invocation was written with the SAME VALUE TWICE:
 *
 *     GH_TOKEN="$(gh auth token)" GITHUB_TOKEN="$(gh auth token)" npm run ci:quick
 *
 * Nobody could say which gate wanted which, so both were always set, and the one gate
 * that would have revealed the gap never could.
 *
 * THE SECOND DEFECT THIS PINS. With NEITHER name set the helper returned undefined and
 * the gates went out anonymous -- silently, with no warning, into a 60-request-per-hour
 * shared bucket. On 2026-09-16 a pr-babysit session driving PR #589 took a red on
 * `check:actions` from that rate limit while `gh auth login` credentials sat unused in
 * gh's own store. The fallback added for it is guarded here in all four directions:
 * env still wins, the fallback fires, a failure is still undefined, and the probe is
 * memoized -- plus an anti-vacuity control proving the memo reset used by the memo
 * assertions actually resets, because without that every one of them passes trivially.
 *
 * INJECTED READERS THROUGHOUT, deliberately. A control whose verdict depends on whether
 * the developer running it happens to be logged into `gh` is not a control: it would be
 * green on a laptop and red in CI for reasons having nothing to do with the code. The
 * one exception is the last case, which drives the REAL `execFileSync` path precisely
 * because nothing else proves those spawn options are wired correctly.
 *
 * Attached to check:ci-embed-asset-freshness because that gate runs in the pre-push lane:
 * a control deferred to full CI would not have caught this before the push either.
 */
import process from 'node:process';

import {
  type GhAuthTokenReader,
  ghCliToken,
  githubToken,
  hasGithubToken,
  resetGhCliTokenMemo,
} from '../lib/github-token.js';

let bad = 0;
const ck = (label: string, ok: boolean): void => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}`);
  if (!ok) bad += 1;
};
const env = (o: Record<string, string>): NodeJS.ProcessEnv => o as NodeJS.ProcessEnv;

/** A counting stand-in for `gh auth token`: give it stdout, or an Error to throw. */
const reader = (outcome: string | Error): { read: GhAuthTokenReader; calls: () => number } => {
  let calls = 0;
  return {
    read: () => {
      calls += 1;
      if (outcome instanceof Error) throw outcome;
      return outcome;
    },
    calls: () => calls,
  };
};
const NO_GH = (): Error => new Error('gh: command not found');

// ── The first defect: both names, one precedence ───────────────────────────
{
  const r = reader('from-gh');
  ck(
    'GH_TOKEN alone resolves -- the whole point',
    githubToken(env({ GH_TOKEN: 'a' }), r.read) === 'a' && r.calls() === 0
  );
}
{
  const r = reader('from-gh');
  ck(
    'GITHUB_TOKEN alone resolves, as CI provides it',
    githubToken(env({ GITHUB_TOKEN: 'b' }), r.read) === 'b' && r.calls() === 0
  );
}
{
  const r = reader('from-gh');
  ck(
    'GITHUB_TOKEN wins when both are set: in a workflow it is the job’s real credential',
    githubToken(env({ GH_TOKEN: 'a', GITHUB_TOKEN: 'b' }), r.read) === 'b' && r.calls() === 0
  );
}

// ── The second defect: the `gh auth token` fallback ────────────────────────
resetGhCliTokenMemo();
{
  const r = reader('from-gh');
  ck(
    'an ENV token must not even consult `gh` -- in CI this path must never spawn anything',
    githubToken(env({ GITHUB_TOKEN: 'b' }), r.read) === 'b' && r.calls() === 0
  );
}
resetGhCliTokenMemo();
ck(
  'no env token falls back to `gh auth token` -- the PR #589 rate-limit defect',
  githubToken(env({}), reader('from-gh').read) === 'from-gh'
);
resetGhCliTokenMemo();
ck(
  'CONTROL: neither env nor gh is undefined -- exactly the anonymous behaviour as before',
  githubToken(env({}), reader(NO_GH()).read) === undefined
);
resetGhCliTokenMemo();
ck(
  'CONTROL: `gh` printing nothing is not a token either',
  githubToken(env({}), reader('   \n').read) === undefined
);
resetGhCliTokenMemo();
ck(
  'an EMPTY value is not a token -- `VAR=` falls through to gh exactly like an unset VAR',
  githubToken(env({ GH_TOKEN: '' }), reader('from-gh').read) === 'from-gh'
);
resetGhCliTokenMemo();
ck(
  'CONTROL: ...and with `gh` unavailable too, `VAR=` is still undefined',
  githubToken(env({ GH_TOKEN: '' }), reader(NO_GH()).read) === undefined
);

// ── hasGithubToken agrees with githubToken on every one of those ───────────
resetGhCliTokenMemo();
{
  const gone = reader(NO_GH());
  const ok = !hasGithubToken(env({}), gone.read);
  resetGhCliTokenMemo();
  ck(
    'CONTROL: hasGithubToken agrees with githubToken in all three directions',
    ok &&
      hasGithubToken(env({ GH_TOKEN: 'a' }), reader(NO_GH()).read) &&
      hasGithubToken(env({}), reader('from-gh').read)
  );
}

// ── Memoization: four gates in one `npm run ci`, one spawn ─────────────────
resetGhCliTokenMemo();
{
  const r = reader('from-gh');
  const a = githubToken(env({}), r.read);
  const b = githubToken(env({}), r.read);
  const c = hasGithubToken(env({}), r.read);
  ck(
    'memoized: three resolutions, ONE `gh` spawn',
    r.calls() === 1 && a === 'from-gh' && b === 'from-gh' && c === true
  );
}
resetGhCliTokenMemo();
{
  const r = reader(NO_GH());
  githubToken(env({}), r.read);
  githubToken(env({}), r.read);
  hasGithubToken(env({}), r.read);
  ck(
    'a FAILED probe is memoized too -- a gh-less box pays one failed spawn, not one per call',
    r.calls() === 1
  );
}
resetGhCliTokenMemo();
{
  // ANTI-VACUITY. If resetGhCliTokenMemo() did nothing, every `calls() === 1`
  // above would pass for the wrong reason and this file would guard nothing.
  const r = reader('from-gh');
  githubToken(env({}), r.read);
  resetGhCliTokenMemo();
  githubToken(env({}), r.read);
  ck(
    'CONTROL: resetGhCliTokenMemo really clears, so the memo controls are not vacuous',
    r.calls() === 2
  );
}

// ── The REAL spawn path, whatever this box has ─────────────────────────────
resetGhCliTokenMemo();
{
  // Machine-dependent RESULT, machine-independent REQUIREMENT: logged in, logged out, or no `gh` at all, the default reader must return and never throw. This is the only case that exercises the actual execFileSync options.
  let threw = false;
  try {
    ghCliToken();
  } catch {
    threw = true;
  }
  ck('the REAL `gh auth token` probe returns rather than throwing, on any box', !threw);
  resetGhCliTokenMemo();
}

console.log(`${bad === 0 ? '✓' : '✗'} github-token controls: ${bad} failure(s)`);
process.exit(bad === 0 ? 0 : 1);

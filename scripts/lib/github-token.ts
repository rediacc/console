/**
 * The GitHub token, from either name — or from `gh` itself — in one place.
 *
 * WHY THIS EXISTS. Four gates read a token and three of them wrote
 * `process.env.GITHUB_TOKEN || process.env.GH_TOKEN` by hand. The fourth,
 * check-external-links.ts, read only `GITHUB_TOKEN` -- so a session with just
 * `GH_TOKEN` set got a silently unauthenticated run there and a normal one
 * everywhere else. That inconsistency is why every local invocation of the gate
 * suite was being written as
 *
 *     GH_TOKEN="$(gh auth token)" GITHUB_TOKEN="$(gh auth token)" npm run ci:quick
 *
 * -- the same value, twice, because nobody could say which gate wanted which.
 * One is now enough. In fact none is now enough; see the fallback below.
 *
 * BOTH NAMES STAY SUPPORTED, and that is not indecision. GitHub Actions injects
 * `GITHUB_TOKEN` and the `gh` CLI reads `GH_TOKEN` first; neither is ours to
 * rename. What was wrong was each call site deciding for itself.
 *
 * GITHUB_TOKEN is checked first to match `gh`'s own precedence being inverted in
 * CI: in a workflow, GITHUB_TOKEN is the job's real credential.
 *
 * THE `gh auth token` FALLBACK, and why an unset environment was the real bug.
 * With neither name set these gates did not fail and did not warn -- they sent an
 * ANONYMOUS request, and anonymous api.github.com is 60 requests per hour for the
 * whole machine. On 2026-09-16 a pr-babysit session driving PR #589 watched
 * `check:actions` go red on a rate limit, with a perfectly good credential sitting
 * in `gh`'s own store the whole time, because being logged in via `gh auth login`
 * had never been something this code could see. The operator should not have to
 * `export GITHUB_TOKEN=$(gh auth token)` by hand to make a local gate run mean
 * something.
 *
 * WHY THE FALLBACK IS SAFE:
 *   - It is LOCAL-DEV-ONLY in practice. Every workflow step injects
 *     `GITHUB_TOKEN: ${{ github.token }}`, so in CI the env branch answers first
 *     and `gh` is never invoked. Nothing about a CI run changes.
 *   - It NEVER THROWS and never blocks a gate. `gh` missing, `gh` not logged in,
 *     a non-zero exit, a hang -- every one of them lands on `undefined`, which is
 *     exactly the anonymous behaviour that exists today. This can only add a
 *     token, never remove one.
 *   - It is MEMOIZED for the life of the process. `githubToken()` is called
 *     per-request in some gates and `npm run ci` runs four of them, so an
 *     unmemoized shell-out would be thousands of `gh` spawns. The probe runs at
 *     most once, and a FAILED probe is cached too -- a machine without `gh` pays
 *     for one failed spawn, not one per call.
 *   - There is no recursion risk in asking `gh` for a token here: `gh auth token`
 *     prints `$GH_TOKEN`/`$GITHUB_TOKEN` when they are set, and we only reach it
 *     when neither is.
 */
import { execFileSync } from 'node:child_process';

/**
 * The raw shell-out: returns `gh auth token`'s stdout, or throws.
 *
 * Injectable so the controls can drive both outcomes without a real `gh` on the
 * box -- a control whose verdict depends on whether the developer happens to be
 * logged in is not a control.
 */
export type GhAuthTokenReader = () => string;

const runGhAuthToken: GhAuthTokenReader = () =>
  execFileSync('gh', ['auth', 'token'], {
    encoding: 'utf8',
    // stderr to /dev/null: "not logged in" is an ANSWER here, not an incident,
    // and printing it would make every gate run on a `gh`-less box look broken.
    stdio: ['ignore', 'pipe', 'ignore'],
    timeout: 10_000,
  });

/** Memoized probe result. `undefined` means "not probed yet"; the box holds the answer. */
let memo: { token: string | undefined } | undefined;

/**
 * The credential `gh auth login` stored, or `undefined` for any reason at all.
 *
 * Probed at most once per process -- including a failure, so a box without `gh`
 * pays one failed spawn rather than one per call site.
 */
export function ghCliToken(read: GhAuthTokenReader = runGhAuthToken): string | undefined {
  if (memo !== undefined) return memo.token;
  let token: string | undefined;
  try {
    const out = read().trim();
    token = out === '' ? undefined : out;
  } catch {
    // Not installed, not logged in, non-zero exit, timeout. All the same answer.
    token = undefined;
  }
  memo = { token };
  return token;
}

/**
 * Controls only: forget the memoized probe.
 *
 * The memo is deliberately shared between the real reader and an injected one --
 * that sharing is what makes the memoization observable from a control at all --
 * so a control that injects a fake must clear it again.
 */
export function resetGhCliTokenMemo(): void {
  memo = undefined;
}

export function githubToken(
  env: NodeJS.ProcessEnv = process.env,
  read?: GhAuthTokenReader
): string | undefined {
  // An empty value is not a token: `VAR=` must behave exactly like an unset VAR,
  // which here means falling through to `gh` rather than going out anonymous.
  const t = env.GITHUB_TOKEN || env.GH_TOKEN;
  if (t) return t;
  return ghCliToken(read);
}

/** True when a token is present under either name, or `gh` is logged in. */
export const hasGithubToken = (
  env: NodeJS.ProcessEnv = process.env,
  read?: GhAuthTokenReader
): boolean => githubToken(env, read) !== undefined;

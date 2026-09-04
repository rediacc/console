/**
 * The GitHub token, from either name, in one place.
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
 * One is now enough.
 *
 * BOTH NAMES STAY SUPPORTED, and that is not indecision. GitHub Actions injects
 * `GITHUB_TOKEN` and the `gh` CLI reads `GH_TOKEN` first; neither is ours to
 * rename. What was wrong was each call site deciding for itself.
 *
 * GITHUB_TOKEN is checked first to match `gh`'s own precedence being inverted in
 * CI: in a workflow, GITHUB_TOKEN is the job's real credential.
 */
export function githubToken(env: NodeJS.ProcessEnv = process.env): string | undefined {
  const t = env.GITHUB_TOKEN || env.GH_TOKEN;
  return t === '' ? undefined : t;
}

/** True when a token is present under either name. */
export const hasGithubToken = (env: NodeJS.ProcessEnv = process.env): boolean =>
  githubToken(env) !== undefined;

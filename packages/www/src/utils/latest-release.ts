import { GITHUB_REPO } from '../config/constants';
import type { GitHubRelease } from './release-parser';
import { githubToken } from '../../../../scripts/lib/github-token.ts';

/**
 * The latest GitHub release, fetched ONCE per build and shared by every locale.
 *
 * `downloads.astro` runs `getStaticPaths` over 13 locales, so the previous
 * per-page fetch hit an unauthenticated GitHub endpoint 13 times per build and
 * was rate-limited intermittently. Worse, its failure path was a DEV-gated
 * console.error, so production builds shipped an empty downloads page and
 * exited 0.
 *
 * This module memoises the promise, so all 13 pages await one request. It
 * deliberately does NOT swallow the failure: it resolves to null and lets the
 * caller decide, which is how the build can be made to fail.
 *
 * The token comes from `scripts/lib/github-token.ts`'s shared `githubToken()`
 * rather than reading `process.env.GITHUB_TOKEN` here a second time -- this
 * was the fifth independent reader of that env var found in one sweep of a
 * sibling bug, and the whole point of that helper existing is that a caller
 * does not get to decide for itself. This module runs only inside
 * `getStaticPaths`, which Astro executes in the Node build step, never in
 * client code, so importing a helper that may shell out to `gh auth token`
 * is safe here.
 */
let inflight: Promise<GitHubRelease | null> | undefined;

async function fetchOnce(): Promise<GitHubRelease | null> {
  const token = githubToken();
  const headers: Record<string, string> = { Accept: 'application/vnd.github+json' };
  if (token !== undefined && token !== '') headers.Authorization = `Bearer ${token}`;

  try {
    const response = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/releases/latest`, {
      headers,
    });
    if (!response.ok) {
      // Loud on purpose. The old code was silent here and that is the bug.
      console.error(`latest-release: GitHub responded ${response.status} ${response.statusText}`);
      return null;
    }
    return (await response.json()) as GitHubRelease;
  } catch (error) {
    console.error('latest-release: GitHub fetch failed:', error);
    return null;
  }
}

export function fetchLatestRelease(): Promise<GitHubRelease | null> {
  inflight ??= fetchOnce();
  return inflight;
}

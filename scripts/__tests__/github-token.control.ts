/**
 * Controls for scripts/lib/github-token.ts.
 *
 * THE DEFECT THIS PINS. Four gates read a GitHub token. Three wrote
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
 * Attached to check:ci-embed-asset-freshness because that gate runs in the pre-push lane:
 * a control deferred to full CI would not have caught this before the push either.
 */
import process from 'node:process';

import { githubToken, hasGithubToken } from '../lib/github-token.js';

let bad = 0;
const ck = (label: string, ok: boolean): void => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}`);
  if (!ok) bad += 1;
};
const env = (o: Record<string, string>): NodeJS.ProcessEnv => o as NodeJS.ProcessEnv;

ck('GH_TOKEN alone resolves -- the whole point', githubToken(env({ GH_TOKEN: 'a' })) === 'a');
ck(
  'GITHUB_TOKEN alone resolves, as CI provides it',
  githubToken(env({ GITHUB_TOKEN: 'b' })) === 'b'
);
ck(
  'GITHUB_TOKEN wins when both are set: in a workflow it is the job’s real credential',
  githubToken(env({ GH_TOKEN: 'a', GITHUB_TOKEN: 'b' })) === 'b'
);
ck('CONTROL: neither set is undefined', githubToken(env({})) === undefined);
ck(
  'CONTROL: an EMPTY value is not a token -- an unset var and `VAR=` must behave alike',
  githubToken(env({ GH_TOKEN: '' })) === undefined
);
ck(
  'CONTROL: hasGithubToken agrees with githubToken in both directions',
  !hasGithubToken(env({})) && hasGithubToken(env({ GH_TOKEN: 'a' }))
);

console.log(`${bad === 0 ? '✓' : '✗'} github-token controls: ${bad} failure(s)`);
process.exit(bad === 0 ? 0 : 1);

# Review 81805ca3: feat(cli): serve-side job poll body, argv builder and terminal audit ledger (PLAN-detached-jobs C5 prep for J6), and the account pointer for the web loop (C6)

Commit: 81805ca3bb8beafcddd430515aaaf2fbafdb06c1
Repo: console
Branch: 1023-1
Parent: eb31b1da9ac45d85f0ea77ffb37bd7a6beeac556
Patch-Id: 7a26919349ec3f71110bf07552406463d68551ef
Reviewed-At: 2026-10-29T13:49:25Z
Model: claude-haiku-5-5
Cost: $0.0062 USD, 1 call(s), 59.4s
Diff: 11855 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature why=New internal helpers only; the poll route and audit wiring land in J6, so no user-facing behaviour changes in this commit.
Dropped: 0
Body-Sig: a8bbfc0aa4965cd0

## Findings

### 81805ca3.1 [medium] packages/cli/src/services/serve/job-poll.ts:118
Anchor: in-diff
Claim: The `.filter((l) => l.trim() !== '')` drops blank lines before numbering, so if renet emits a blank line in the job stream, every later event is numbered one lower than its real index and nextLine lags; the next poll re-sends already-delivered events. No test covers blank lines.
Resolution: fixed b925c10ac5446c36ed3eb9c90b6ede082af89492 | d778be9d 2026-10-29T14:32:20Z

### 81805ca3.2 [medium] packages/cli/src/services/serve/job-poll.ts:91
Anchor: in-diff
Claim: If the last output line is the JSON literal `null` (e.g. stdout `null\n` with no trailer), JSON.parse succeeds with null and `raw.type` throws a TypeError instead of the JobPollParseError the contract promises for a missing trailer.
Resolution: fixed b925c10ac5446c36ed3eb9c90b6ede082af89492 | d778be9d 2026-10-29T14:32:20Z

### 81805ca3.3 [medium] packages/cli/src/services/serve/job-poll.ts:39
Anchor: in-diff
Claim: The nextLine doc says it is 'the count of lines received so far', but the code sets nextLine = sinceLine + count (an absolute index), so after a poll from line 10 that receives 2 lines nextLine is 12, not 2.
Resolution: fixed b925c10ac5446c36ed3eb9c90b6ede082af89492 | d778be9d 2026-10-29T14:32:21Z

### 81805ca3.4 [low] packages/cli/src/services/serve/job-poll.ts:129
Anchor: in-diff
Claim: bodySize re-runs JSON.stringify on the whole growing body for every line, so a page near the 256 KiB cap costs roughly 500 full serializations per poll; tracking running byte counts would avoid this.
Resolution: fixed b925c10ac5446c36ed3eb9c90b6ede082af89492 | d778be9d 2026-10-29T14:32:21Z

### 81805ca3.5 [low] packages/cli/src/services/serve/job-poll.ts:126
Anchor: in-diff
Claim: parseJobPollOutput uses opts.sinceLine unclamped for numbering while buildJobPollArgv clamps negative or non-finite values to 0, so a caller passing -3 gets argv since-line 0 but events numbered from -3 and a nextLine that does not match what renet returned.
Resolution: fixed b925c10ac5446c36ed3eb9c90b6ede082af89492 | d778be9d 2026-10-29T14:32:22Z

### 81805ca3.6 [low] private/account:1
Anchor: in-diff
Claim: The commit advances the private/account submodule pointer from d124c0d to 5eeafe7, but the commit message does not say what changed there and the target content is not in the diff, so it cannot be reviewed here.
Resolution: not-a-bug | the pointer target has its own review record at agent/reviews/1023-1/5eeafe7acda9eaefe43b852a043995b2fab9d7de.md:1 and the commit message names the C6 web loop | d778be9d 2026-10-29T14:20:48Z

# Review cead81df: fix(cli): racing client-id first runs agree, a failed job keeps its early errors, a lost poll follow keeps its last state

Commit: cead81dfc7ad8ba8f1e98e07b4b9dd89ca30fc88
Repo: console
Branch: 1104-1
Parent: 081cc84d34bfd5989412c4171e767472bc2b46df
Patch-Id: dbcf51de5f3615368c39add194c179ca7b519b92
Reviewed-At: 2026-11-06T04:57:06Z
Model: claude-haiku-5-5
Cost: $0.0049 USD, 1 call(s), 30.3s
Diff: 14972 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes three CLI defects: racing first-run client id, failed-job stderr losing early errors, and lost-poll span outcome. No new capability.
Dropped: 0
Body-Sig: 6674ba0a62358aa0

## Findings

### cead81df.1 [medium] packages/cli/src/services/account/license-machine.ts:177
Anchor: in-diff
Claim: When the id file already holds a corrupt value, two racing first runs both wait about 100ms in readRacedInstallId, find nothing valid, and each overwrite the file with their own generated id (no 'wx' flag), so they return different ids, which breaks the 'racing first runs agree' guarantee. A winner slower than about 100ms between create and write gets overwritten the same way.
Resolution: fixed 2d80662abd1348e9586411198808ee031d90451f | d778be9d 2026-11-06T21:33:27Z

### cead81df.2 [medium] packages/cli/src/services/executor/job-output-collector.ts:71
Anchor: in-diff
Claim: failedJobStderr prepends every error or warning line from stderr that is not in the tail, with no count cap (only a per-line width cap), so a failed job that logged many older error lines now returns an unbounded stderr where the tail used to be at most 20 lines; the diff does not show whether output.stderr is capped upstream.
Resolution: fixed 058f0e639f6117f9bcb72e99c9f266778b37fca4 | d778be9d 2026-11-06T21:33:27Z

### cead81df.3 [low] packages/cli/src/services/executor/proxy-client.ts:586
Anchor: in-diff
Claim: A follow lost after a non-terminal poll now writes that poll's state (e.g. 'running') into rediacc.job.outcome, while the returned lostOutcome is a failure, so telemetry consumers that read outcome as terminal see 'running' for a command that already ended.
Resolution: not-a-bug | packages/cli/src/services/executor/job-span.ts:19 the documented outcomes include running for a ticket handed back, and a lost follow keeps its ticket with the job still running; proxy-client-poll.test.ts:163 pins it | d778be9d 2026-11-06T21:33:28Z

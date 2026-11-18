# Review c29ab62a: fix(ci): the impact-reads trace ends when pytest does, kills what a test leaked, and stops every shard on SIGTERM

Commit: c29ab62a47d6fabbe3a0cb9965a88bbf8b1ac64c
Repo: console
Branch: 1104-1
Parent: d616eb96dd1ba07abf3db63a0f0073eb2526021a
Patch-Id: 5a07eba326d5d616e799b7e215de1a19709c0af6
Reviewed-At: 2026-11-18T13:42:52Z
Model: claude-haiku-5-5
Cost: $0.0096 USD, 1 call(s), 69.2s
Diff: 13830 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI tooling fix for pytest impact-read tracing; no user-facing product change.
Dropped: 0
Body-Sig: be53bdda38ac630e

## Findings

### c29ab62a.1 [medium] .ci/rediacc_ci/quality/pytest_impact_reads.py:555
Anchor: in-diff
Claim: A leaked process that calls setsid (a daemonising test helper) leaves the strace session, so the grace loop's _kill_session never reaches it; strace stays alive and the unbounded child.wait() blocks, so the hang this commit targets still occurs for that case.
Class: other
Resolution: open

### c29ab62a.2 [medium] .ci/rediacc_ci/quality/pytest_impact_reads.py:542
Anchor: in-diff
Claim: An exception raised by att.feed in the fold() thread now dies silently in the thread instead of reaching run_trace's finally; strace then blocks on a full, unread stderr pipe, pytest never writes its rc file, and the polling loop at 548-554 waits forever, where the old code raised and killed the group.
Class: swallowed-error
Resolution: open

### c29ab62a.3 [medium] .ci/rediacc_ci/quality/pytest_impact_reads.py:552
Anchor: in-diff
Claim: The orphan-kill branch (grace expiry, _kill_session with spare, break) and the 'outlived pytest under the trace and was killed' output at 562-565 have no unit test; the only check was a manual live run, so a regression there would not fail the suite.
Class: missing-control-test
Resolution: open

### c29ab62a.4 [medium] .ci/rediacc_ci/quality/pytest_impact_reads.py:735
Anchor: in-diff
Claim: The new SIGTERM path in cmd_trace (pool creation, except BaseException calling _kill_live, pool.shutdown in finally) is changed behaviour with no test in the diff, so a regression that waits on the shard threads again would pass the suite.
Class: missing-control-test
Resolution: open

### c29ab62a.5 [low] .ci/rediacc_ci/quality/pytest_impact_reads.py:506
Anchor: in-diff
Claim: A zombie member of the session has an empty cmdline, so _kill_session appends '' and the output line reads 'was killed: ' with no command name, which defeats the naming the commit describes.
Class: other
Resolution: open

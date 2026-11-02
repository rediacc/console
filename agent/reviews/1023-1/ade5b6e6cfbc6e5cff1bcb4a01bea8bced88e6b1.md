# Review ade5b6e6: fix(ci-trace): an empty `name:` value no longer captures the next line as the workflow name

Commit: ade5b6e6cfbc6e5cff1bcb4a01bea8bced88e6b1
Repo: console
Branch: 1023-1
Parent: 881583d08dcb9f440346d581988d2249d46cd0b2
Patch-Id: ff00cf519c419b102b3e9c92aebdb812c2492e6f
Reviewed-At: 2026-10-23T06:41:39Z
Model: claude-haiku-5-5
Cost: $0.0019 USD, 1 call(s), 12.7s
Diff: 2616 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes the empty-name capture bug in ci-trace's workflow name lookup; the CRLF regression is a reviewer finding, not a release change.
Dropped: 0
Body-Sig: cdedeffe8ce6f058

## Findings

### ade5b6e6.1 [medium] .ci/scripts/ci/ci-trace.py:1646
Anchor: in-diff
Claim: The new `_TOP_NAME` pattern `^name:[ \t]*(\S[^\n]*?)[ \t]*$` no longer strips a trailing `\r`, unlike the old `\s*$`. For a CRLF workflow file containing `name: Release\r\n`, the captured name becomes `Release\r`, so the --run name comparison fails. No test covers CRLF input.
Resolution: not-a-bug | .ci/scripts/ci/ci-trace.py:1662 reads with read_text, whose universal newlines turn CRLF into LF before _TOP_NAME runs; 7338d5b0 adds a CRLF test that passes on the current and the previous pattern alike | d778be9d 2026-10-23T07:11:31Z

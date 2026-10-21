# Review fb0fcb70: fix(hooks): verify-rebase names every same-subject candidate and a failed lookup

Commit: fb0fcb70d085240d9a81c662e2affbdfbdead487
Repo: console
Branch: 1020-1
Parent: c83c1814cb5b17739434665feb83a004bc076c1f
Patch-Id: f939aafead2e4974e1a79333310485aad6e31e6f
Reviewed-At: 2026-10-21T02:40:13Z
Model: claude-haiku-5-5
Cost: $0.0020 USD, 1 call(s), 21.6s
Diff: 3006 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Internal stop-hook diagnostics for verify-rebase; no product-facing behaviour changes.
Dropped: 0
Body-Sig: b25730cee425b131

## Findings

### fb0fcb70.1 [medium] .claude/hooks/stop/wl_git.py:1273
Anchor: in-diff
Claim: The new `if rc_n != 0:` branch that prints the failed-lookup rc has no test; the commit's only verification is the existing 12-test suite plus a live run, so a regression in either the failure row or the multi-candidate join (line 1284) would pass CI unnoticed.
Resolution: not-a-bug | .claude/rediacc_hooks/tests/test_hooks_trapguard.py:682 now pins the multi-candidate join; the rc row needs git log to fail on a range equivalent() just compared, which no fixture reproduces without faking git | d778be9d 2026-10-21T02:41:09Z

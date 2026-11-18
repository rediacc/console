# Review 283b5dbe: test(ci): repair two pytest fixtures gone stale after 1684f2ec and the gates.lock re-trace

Commit: 283b5dbe2ed72c1ccef9c07faedae4b8131b8fc0
Repo: console
Branch: 1104-1
Parent: 52bd29fe21ca855227aff1ce90477a37318f5dda
Patch-Id: e7aa7fb816d71e643716bfa57b57a3a3aaa8a094
Reviewed-At: 2026-11-18T08:00:13Z
Model: claude-haiku-5-5
Cost: $0.0033 USD, 1 call(s), 14.2s
Diff: 2505 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only fixture and parity repairs; no user-facing change.
Dropped: 0
Body-Sig: 941ad05395a2c3a7

## Findings

### 283b5dbe.1 [low] .ci/rediacc_ci/tests/gates/test_gate_incremental_receipt.py:73
Anchor: in-diff
Claim: The new call unpacks `extras, _ = G.v2_extra_lines(...)` and discards the second return value; if that value carries skipped or failed entries, the parity assertion on line 80 compares against a partial extras list without any signal. Not verifiable from the diff.
Class: swallowed-error
Resolution: open

### 283b5dbe.2 [low] .ci/rediacc_ci/tests/test_path_trace.py:128
Anchor: in-diff
Claim: The commit message calls .ci/policy/record-paths.json an 'empty' file, but the line writes {"version": 1, "records": []}, which has a version key as well as an empty records list.
Class: doc-contradicts-code
Resolution: open

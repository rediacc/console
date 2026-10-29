# Review dfc10e27: test(drills): the backup/license differential test normalizes the port-only legs n and o (red on the branch since 581206c7b)

Commit: dfc10e27fe7e335df38b9a8a9b4eaadd49bb1a43
Repo: console
Branch: 1023-1
Parent: f710ed4e74a5e799c413babdb51a475bf92d7b6d
Patch-Id: d923edfd844a16d1c9fbce31c74311b709f02049
Reviewed-At: 2026-10-29T17:28:43Z
Model: claude-haiku-5-5
Cost: $0.0018 USD, 1 call(s), 21.9s
Diff: 1382 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Test-only normalization fixing four red differential cases; no user-facing change.
Dropped: 0
Body-Sig: 7b9e2976f695cd8b

## Findings

### dfc10e27.1 [medium] .ci/rediacc_ci/tests/test_drills_backup_license.py:150
Anchor: in-diff
Claim: The unanchored text.replace(", n, o", "") runs on all normalized output, so if the port ever stops listing legs n and o, the differential still passes; this diff adds no test that the port itself still prints them.
Resolution: open

### dfc10e27.2 [low] .ci/rediacc_ci/tests/test_drills_backup_license.py:150
Anchor: in-diff
Claim: The replace matches raw substrings with no token boundary, so ",n,o" also strips the start of a longer token such as ",n,option", leaving "tion" behind; and a list where n and o come first ("n, o, a") is not normalized and still fails.
Resolution: open

### dfc10e27.3 [low] .ci/rediacc_ci/tests/test_drills_backup_license.py:149
Anchor: in-diff
Claim: The comment hard-codes the commit hash 581206c7b as the reason for the port-only legs, which will go stale and does not say what to change when the bash twin's leg list changes.
Resolution: open

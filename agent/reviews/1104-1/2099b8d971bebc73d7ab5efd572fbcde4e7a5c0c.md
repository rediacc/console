# Review 2099b8d9: feat(release): add release:local --branch-release for the shared edge Workers

Commit: 2099b8d971bebc73d7ab5efd572fbcde4e7a5c0c
Repo: console
Branch: 1104-1
Parent: 02287107b9ba35216b2fd47e26101d8bb9e1367f
Patch-Id: c746801d76d2159404e0a75f1dcab018c1c4d081
Reviewed-At: 2026-11-13T06:25:50Z
Model: claude-haiku-5-5
Cost: $0.0141 USD, 1 call(s), 63.4s
Diff: 74025 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds release:local --branch-release, a new capability for deploying a pushed branch head to the edge Workers.
Dropped: 0
Body-Sig: 2100aa78874e8817

## Findings

### 2099b8d9.1 [low] .ci/rediacc_ci/release/local.py:1247
Anchor: in-diff
Claim: branch_context discards the failure reason from heads(root) (`remote, _why = heads(root)`) and names the branch `unpushed` when the ls-remote read failed, so the dry-run line and the Worker's build metadata say HEAD is unpushed when only the read failed; the origin-main gate still refuses the run.
Class: swallowed-error
Resolution: fixed 01f2a26f115583b0c8e372acda5ee2b8b5efae2e | d778be9d 2026-11-13T06:31:20Z

### 2099b8d9.2 [low] .ci/rediacc_ci/release/local.py:1439
Anchor: in-diff
Claim: The comment says the gates row's argv is printed, but `if step.argv:` now prints the argv of every non-run row that has one (assist, seal, stage and the rest), so a dry run prints more child commands than the comment describes.
Class: doc-contradicts-code
Resolution: fixed 01f2a26f115583b0c8e372acda5ee2b8b5efae2e | d778be9d 2026-11-13T06:31:20Z

### 2099b8d9.3 [low] .ci/rediacc_ci/release/local.py:1378
Anchor: in-diff
Claim: dry_gates passes fetch=_ls_remote_main (an ls-remote read that fetches no objects) into the new branch-release ancestry check, so a dry run can judge origin/main's ancestry differently from the real run's fetch, which the commit does not test.
Class: missing-control-test
Resolution: fixed 01f2a26f115583b0c8e372acda5ee2b8b5efae2e | d778be9d 2026-11-13T06:31:20Z

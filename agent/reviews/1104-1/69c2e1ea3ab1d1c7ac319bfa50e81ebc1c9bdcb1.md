# Review 69c2e1ea: refactor(ci): Devbox.build_image is deleted, the pinned digest has no local build

Commit: 69c2e1ea3ab1d1c7ac319bfa50e81ebc1c9bdcb1
Repo: console
Branch: 1104-1
Parent: 2f0f54914bae2e63161410c35288bc0e97d6b395
Patch-Id: 3464851dc7a34e4b974695bf6e8b83303a1cd251
Reviewed-At: 2026-11-20T16:02:31Z
Model: claude-haiku-5-5
Cost: $0.0050 USD, 1 call(s), 21.3s
Diff: 454710 bytes, 5 files, truncated: yes
Unreviewed: .ci/rediacc_ci/tests/goldens/twins/lib.devbox.jsonl
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Deletes a retired CI-only build helper and its test steps; no user-facing behaviour changes.
Dropped: 0
Body-Sig: c263fba1f9881551

## Findings

### 69c2e1ea.1 [medium] .ci/rediacc_ci/tests/test_core_devbox.py:315
Anchor: in-diff
Claim: The run-image-match assertion now compares stdout to the port's own devbox.DEVBOX_IMAGE instead of the frozen twin's TWIN_DEVBOX_IMAGE, so if the port changes that constant this check follows it and still passes; the claim no longer pins the bash-side value the module docstring says twin claims must pin.
Class: missing-control-test
Resolution: fixed 0379bb9691be8de9e69bd4f89605c95c0d3a3afe | d778be9d 2026-11-20T16:04:06Z

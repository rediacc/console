# Review 5aecfcdc: fix(ci): the preview smoke reads PREVIEW_HAS_SIGNER from its env instead of a constant

Commit: 5aecfcdcaa23b9a13adb0ca5ea848dbe8130bcae
Repo: console
Branch: 1121-1
Parent: 098e7ab5a5e89e4f4f4ccf45fed07eca68e3ab41
Patch-Id: e94962e6f2983da18ab5e95d86dada3fc3f22db9
Reviewed-At: 2026-11-22T08:47:58Z
Model: claude-haiku-5-5
Cost: $0.0033 USD, 1 call(s), 12.2s
Diff: 4064 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI-only lint fix: the smoke script reads a flag from env instead of a constant. No user-facing change.
Dropped: 0
Body-Sig: cdc19c4cf2f63c29

## Findings

### 5aecfcdc.1 [low] .ci/scripts/test/smoke-test-preview.ts:48
Anchor: in-diff
Claim: The new comment says Box T1 sets PREVIEW_HAS_SIGNER=true in the smoke step's env, but this commit changes no workflow, so nothing sets the variable yet and the signer branch stays skipped until T1 lands.
Class: doc-contradicts-code
Resolution: open

### 5aecfcdc.2 [low] .ci/scripts/test/smoke-test-preview.ts:49
Anchor: in-diff
Claim: PREVIEW_HAS_SIGNER now comes from the env with a strict `=== 'true'` check, so a value such as '1', 'True' or 'yes' silently disables the signature and payload checks with no warning.
Class: other
Resolution: open

### 5aecfcdc.3 [low] .ci/scripts/test/smoke-test-preview.ts:49
Anchor: in-diff
Claim: The env-driven flag changes which checks run, and the commit adds no test or assertion that exercises either the unset or 'true' path.
Class: missing-control-test
Resolution: open

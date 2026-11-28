# Review 90577e42: feat(cli): pin and record a server's renet on its first preview replacement, and switch it back

Commit: 90577e4278fbe6e0ad6f2cfb2cce88dfdfc53a3e
Repo: console
Branch: 1121-1
Parent: dc4708fcdc25d738b0bf22e2e6256362ca233aba
Patch-Id: 247dc5cfb60ea4784a33535d2ddbd301be1ca807
Reviewed-At: 2026-11-23T08:58:33Z
Model: claude-haiku-5-5
Cost: $0.0104 USD, 1 call(s), 53.6s
Diff: 43024 bytes, 10 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=New preview switch-back and pin capability for the CLI provisioner; no user-facing bug fix in this commit.
Dropped: 0
Body-Sig: a9f9736e6d54360f

## Findings

### 90577e42.1 [medium] packages/cli/src/services/renet/renet-provisioner-types.ts:69
Anchor: in-diff
Claim: The uploadGuard doc says 'A throw aborts the provision before anything reaches the machine', but with previewTouch set the pin marker is written and preview.touched is recorded (renet-provisioner.ts:380) before uploadGuard runs (renet-provisioner.ts:385), so a guard refusal leaves the pin and the record behind.
Class: doc-contradicts-code
Resolution: not-a-bug | packages/cli/src/services/renet/__tests__/renet-preview-touch.test.ts:1 | d778be9d 2026-11-26T14:33:50Z

### 90577e42.2 [medium] packages/cli/src/services/preview/slot-ops.ts:20
Anchor: in-diff
Claim: The doc says a failure 'leaves the machine as it was', but the pin command runs before recordPreviewTouch; if the record write throws, the pin marker stays on the slot and the provision fails with the marker in place.
Class: doc-contradicts-code
Resolution: fixed 07bc0bfbf014bf6bd3de628fcdad7a79cb3da001 | d778be9d 2026-11-24T11:06:26Z

### 90577e42.3 [medium] packages/cli/src/services/renet/renet-execution.ts:285
Anchor: in-diff
Claim: previewTouchOption throws a ValidationError whenever a preview overlay exists and machineName is undefined, on every acquireRemoteRenet call, before the provisioner decides whether a replacement is needed, so a no-op provision of an unnamed machine now fails during a preview.
Class: other
Resolution: fixed e386cc46f6d7feba651aab3a2c9ba780a8106050 | d778be9d 2026-11-26T16:59:43Z

### 90577e42.4 [medium] packages/cli/src/services/preview/touch.ts:23
Anchor: in-diff
Claim: previewTouchOption's refusal for an unnamed or invalid machine name, and its no-overlay branch, have no test: the new test file only passes previewTouch directly to the provisioner and never calls this function.
Class: missing-control-test
Resolution: fixed 07bc0bfbf014bf6bd3de628fcdad7a79cb3da001 | d778be9d 2026-11-24T11:06:26Z

### 90577e42.5 [medium] packages/cli/src/services/renet/renet-provisioner.ts:325
Anchor: in-diff
Claim: switchBackToPinnedSlot is a new public method with no caller in this commit and no test; the TS wiring (lock path, the flock exit code, and refreshRouter after 'switched') is not exercised, since the shell tests cover only the body string.
Class: missing-control-test
Resolution: not-a-bug | packages/cli/src/services/renet/__tests__/renet-preview-touch.test.ts:1 | d778be9d 2026-11-26T14:33:50Z

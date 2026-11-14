# Review 9386fdfb: test(e2e): build suite 20 images with renet ops image build --os, for the five images renet supports

Commit: 9386fdfba6d0f8630bb6c64beefcff1c3abc0492
Repo: console
Branch: 1104-1
Parent: c1005a08ffba4935e703519d678cf78e7f7d45d7
Patch-Id: 411b1d592f13ca32d97a70587bce724597f6facc
Reviewed-At: 2026-11-07T17:45:35Z
Model: claude-haiku-5-5
Cost: $0.0050 USD, 1 call(s), 29.8s
Diff: 13308 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Test-only change to the e2e image helper and suite; no user-facing behaviour changes.
Dropped: 0
Body-Sig: 1811d89ac5638114

## Findings

### 9386fdfb.1 [medium] packages/e2e-tests/src/utils/image/ImageTestHelper.ts:82
Anchor: in-diff
Claim: The oracle-10 entry keeps variant 'ol9.4' while its URL is OL10U1, so any consumer of the variant field (for example an os-variant lookup in the build) gets the Oracle 9 value for an Oracle 10 image. Usage of the field is not visible in this diff.
Resolution: not-a-bug | private/renet/pkg/infra/opsconfig/images.go:75 the test table mirrors renet GetKVMImages, which itself uses virt-install variant ol9.4 for oracle-10; the e2e variant field is only logged (20-image-build.test.ts:58) | d778be9d 2026-11-07T17:46:49Z

### 9386fdfb.2 [medium] packages/e2e-tests/src/utils/image/ImageTestHelper.ts:91
Anchor: in-diff
Claim: The opensuse-16.0 entry keeps variant 'opensuse15.5' from the removed Leap 15.5 entry while its URL is Leap 16.0, so a consumer of the variant field gets the wrong release for this image.
Resolution: not-a-bug | private/renet/pkg/infra/opsconfig/images.go:87 renet GetKVMImages uses virt-install variant opensuse15.5 for opensuse-16.0; the test mirrors it and only logs the field (20-image-build.test.ts:92) | d778be9d 2026-11-07T17:46:49Z

### 9386fdfb.3 [medium] packages/e2e-tests/src/utils/image/ImageTestHelper.ts:355
Anchor: in-diff
Claim: listCustomImages no longer filters on the 'rediacc-' prefix, so it returns every .qcow2 or .img in disksPath, including base cloud images or unrelated files. Any caller that counts or deletes from this list (such as the cleanup helper, not visible in this diff) now acts on those files too.
Resolution: fixed dd5778e76715011e8eae2f3176adb2e1c65546b8 | d778be9d 2026-11-07T17:46:49Z

### 9386fdfb.4 [low] packages/e2e-tests/src/utils/image/ImageTestHelper.ts:246
Anchor: in-diff
Claim: The unknown-image fallback in getCustomImagePath now returns '<name>.qcow2' with no base-filename logic, which does not match the naming used for known images, so the two paths disagree.
Resolution: not-a-bug | packages/e2e-tests/src/utils/image/ImageTestHelper.ts:194 buildImage refuses an image name outside CONFIGURED_IMAGES before any path is used, so the unknown-name fallback in getCustomImagePath never names a file renet would write | d778be9d 2026-11-07T17:46:50Z

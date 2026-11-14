# Review 8ddacdc7: fix(shared): the delegation renew path carries the account API mount

Commit: 8ddacdc79a5dfdfec166fb7d766ad1aebf52df62
Repo: console
Branch: 1104-1
Parent: bcd870c33df109909140d384e5acbe3e38ab6adb
Patch-Id: 550c7ee3ff7c9f94822dbbaea7531c7c45297fe7
Reviewed-At: 2026-11-12T12:32:43Z
Model: claude-haiku-5-5
Cost: $0.0014 USD, 1 call(s), 9.6s
Diff: 1871 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes the renew request path so production stops returning 404; no new capability.
Dropped: 0
Body-Sig: 076b4679987ac46c

## Findings

### 8ddacdc7.1 [medium] packages/shared/src/subscription/constants.ts:437
Anchor: in-diff
Claim: The comment says changing one end without the other is a compile-time error, but DELEGATION_RENEW_PATH is a plain template-literal string, so a consumer still compiles if the upstream router keeps the old path; the mismatch only surfaces at runtime as a 404.
Class: doc-contradicts-code
Resolution: open

### 8ddacdc7.2 [medium] packages/shared/src/subscription/constants.ts:439
Anchor: in-diff
Claim: DELEGATION_RENEW_PATH changes from /api/v1/delegation/renew to /account/api/v1/delegation/renew with no test added; the listed verification (build, existing src/subscription suite, biome) would pass whether or not the value is correct, so nothing guards the path against regression.
Class: missing-control-test
Resolution: open

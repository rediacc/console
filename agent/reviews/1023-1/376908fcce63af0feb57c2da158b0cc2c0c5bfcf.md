# Review 376908fc: fix(license): the deactivate comment names the repair case; a test pins updatedAt on an untouched subscription

Commit: 376908fcce63af0feb57c2da158b0cc2c0c5bfcf
Repo: private/account
Branch: 1023-1
Parent: 00779b0308fcc68ee93e186f701115bb219a4f5d
Patch-Id: 7caa9a1cfd4d01693ac4b8844e352d0640f862f3
Reviewed-At: 2026-10-30T00:33:07Z
Model: claude-haiku-5-5
Cost: $0.0018 USD, 1 call(s), 15.1s
Diff: 3389 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs why=Comment wording and a test assertion only; no runtime behaviour change.
Dropped: 0
Body-Sig: 0f6a7cb1009acb67

## Findings

### 376908fc.1 [low] src/services/subscription.service.ts:482
Anchor: in-diff
Claim: The reflowed comment line '// an active one that still holds other activations, updatedAt included. Because it runs even when the delete' is about 115 characters, far longer than the surrounding wrapped lines, so the comment block is unevenly wrapped (style only).
Resolution: open

# Review ecf708cb: feat(renet): report the OS-enabled SIMD features in renet list

Commit: ecf708cb63bdef9ffc267d53893ee91c9ff4d8fd
Repo: private/renet
Branch: 1121-1
Parent: 654be995c5615fbd68463667f9ca046de06e716c
Patch-Id: 5dda4fc2c3800eee38fdbe1cbc448272730e6836
Reviewed-At: 2026-11-23T21:20:35Z
Model: claude-haiku-5-5
Cost: $0.0021 USD, 1 call(s), 12.5s
Diff: 5003 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds a new cpu_features JSON field reporting OS-enabled SIMD features in renet list output.
Dropped: 0
Body-Sig: b612c8531527cda1

## Findings

### ecf708cb.1 [medium] pkg/list/types.go:185
Anchor: in-diff
Claim: The cpuFeatureNames doc says a machine with no enabled features reports an empty list rather than an absent one, but CPUFeatures is tagged `json:"cpu_features,omitempty"`, so encoding/json omits the key whenever the non-nil empty slice has length 0; the field is absent in exactly that case.
Class: doc-contradicts-code
Resolution: open

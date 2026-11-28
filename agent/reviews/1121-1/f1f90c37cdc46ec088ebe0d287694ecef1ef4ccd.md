# Review f1f90c37: fix(gates): translation completeness recognizes i18next suffix plurals

Commit: f1f90c37cdc46ec088ebe0d287694ecef1ef4ccd
Repo: console
Branch: 1121-1
Parent: 5dbeeb5059dd2d9bc900c4f2bce08657037a79d1
Patch-Id: 4f47100f7cbec4c6118beaff89597537c6f436bb
Reviewed-At: 2026-11-24T09:08:41Z
Model: claude-haiku-5-5
Cost: $0.0066 USD, 1 call(s), 48.7s
Diff: 11135 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Dev-only CI gate false-positive fix; no user-facing change.
Dropped: 0
Body-Sig: aff88f17aaa1e6c4

## Findings

### f1f90c37.1 [low] scripts/gates/check-translation-completeness.ts:657
Anchor: in-diff
Claim: Any English `<k>_other` key with an English `<k>` or `<k>_<cat>` sibling makes `<k>` a suffix plural group, so a language's `<k>_<cat>` key that it selects (e.g. ru `source_one` when English has a non-plural `source` and `source_other`) is no longer reported as an orphan; the gate loses that detection for any such pair.
Class: other
Resolution: not-a-bug | scripts/gates/check-translation-completeness.ts:657 | d778be9d 2026-11-26T15:20:49Z

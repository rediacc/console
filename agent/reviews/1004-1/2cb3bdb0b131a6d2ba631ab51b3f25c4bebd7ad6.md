# Review 2cb3bdb0: fix(ci): housekeeping verifies a release is gone after deleting it, and reaps stale drafts

Commit: 2cb3bdb0b131a6d2ba631ab51b3f25c4bebd7ad6
Repo: console
Branch: 1004-1
Parent: 6328469c90483c42e03cc728aa87f35aa028f4a7
Patch-Id: 47977f9fea26424b473714ef7d7bf937de6e39b2
Reviewed-At: 2026-10-04T02:35:29Z
Model: claude-haiku-4-5-20251001
Cost: $0.1675 USD, 1 call(s), 181.1s
Diff: 17192 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,ci why=Fixes release cleanup gaps (stale drafts, unverified deletes) where v1.2.21 survived 57 runs. New deletion-by-ID code has jq injection risk if tags contain special chars.
Dropped: 0
Body-Sig: b9c0863aa3c4c46e

## Findings

### 2cb3bdb0.1 [medium] .ci/rediacc_ci/housekeeping/cleanup_versions.py:1245
Anchor: in-diff
Claim: Tag name is interpolated directly into jq filter without escaping (line 1245: '.[] | select(.tag_name == "%s") | .id' % tag). If a tag contains special characters like quotes or backslashes, this produces invalid jq syntax, causing the API call to fail and prevent deletion by ID, though the subsequent view check would still correctly fail the run.
Resolution: open

### 2cb3bdb0.2 [medium] .ci/scripts/housekeeping/cleanup-versions.sh:295
Anchor: in-diff
Claim: Tag name is interpolated directly into jq filter without escaping. Same issue as Python version: unquoted $tag in jq filter could cause jq syntax errors if tag contains special characters.
Resolution: open

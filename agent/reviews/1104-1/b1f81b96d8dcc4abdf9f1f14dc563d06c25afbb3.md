# Review b1f81b96: fix(account): answer 404 to a team-scoped token on another team's lineage stores

Commit: b1f81b96d8dcc4abdf9f1f14dc563d06c25afbb3
Repo: private/account
Branch: 1104-1
Parent: 55b83ed55e631316427d9bc28ada76355443b495
Patch-Id: af20c23390259a95286768da4b50594da192950c
Reviewed-At: 2026-11-07T16:48:46Z
Model: claude-haiku-5-5
Cost: $0.0023 USD, 1 call(s), 12.4s
Diff: 7698 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes a team-scope leak on GET /backups/stores/lineage/:lineageGuid, so a team-scoped token no longer learns which stores hold another team's lineage. No new capability.
Dropped: 0
Body-Sig: 93133907b69a7d21

## Findings

### b1f81b96.1 [low] tests/integration/backup-lineage-stores.test.ts:264
Anchor: in-diff
Claim: The new case checks only a foreign lineage (404) and an in-team lineage (200). Nothing asserts that a team-scoped token gets the same 404 for a lineage unknown to the subscription, although the helper comment and commit message say the 404 is the reply an unknown lineage gets. The diff does not show listLineageStores' reply for an unknown lineage, so that parity is unverified.
Resolution: not-a-bug | private/account/tests/integration/backup-store-replicate.test.ts:1 the team-token 404 for a lineage the subscription does not know is asserted in the replicate test file (f4b0ad7), since the lineage-stores test file was outside that writer files | d778be9d 2026-11-07T17:27:16Z

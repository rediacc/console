# Review c5aff3f2: feat(license): repo_license_issued carries the issuing principal

Commit: c5aff3f24d5cf86c8dff81bdb7ff679bc5e1bea6
Repo: private/account
Branch: 1121-1
Parent: 572fb33afab465350c092acd7847b1681117acd6
Patch-Id: f9f150da7b5752dd13ab626dc3e8ead3e00854ac
Reviewed-At: 2026-11-27T10:14:31Z
Model: claude-haiku-5-5
Cost: $0.0021 USD, 1 call(s), 8.6s
Diff: 8677 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds issuing-principal attribution (userId/actorTokenId) to repo_license_issued events; new audit capability with no user-facing break.
Dropped: 0
Body-Sig: 566b540610fd4e38

## Findings

### c5aff3f2.1 [medium] src/routes/license.ts:255
Anchor: in-diff
Claim: The CLI activate-repo and activate-repo-batch routes now pass the actor, but no test calls those HTTP routes. The new tests call subscriptionService directly, so dropping the actor line from either route would leave every test passing and no repo_license_issued event would carry the token or user.
Class: missing-control-test
Resolution: fixed edf20ec9deb217d23021d8b34dbf002574829e66 | d778be9d 2026-11-27T11:13:04Z

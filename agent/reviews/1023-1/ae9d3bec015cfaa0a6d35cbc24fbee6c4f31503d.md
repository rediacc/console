# Review ae9d3bec: feat(config): the rewrap helper for PLAN-config-server-key K4

Commit: ae9d3bec015cfaa0a6d35cbc24fbee6c4f31503d
Repo: private/account
Branch: 1023-1
Parent: 70718348dadcc2ba4ebfff666891ecf764725b4f
Patch-Id: e68aa6b30b55b153b59b6e4df908c481bfa6b260
Reviewed-At: 2026-10-27T12:54:00Z
Model: claude-haiku-5-5
Cost: $0.0027 USD, 1 call(s), 19.8s
Diff: 4717 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature why=New internal ops helper script for a key rewrap; no user-facing product change.
Dropped: 0
Body-Sig: 12d105bce9902ad0

## Findings

### ae9d3bec.1 [medium] scripts/rewrap-config-server-key.ts:81
Anchor: in-diff
Claim: The new rewrap() path re-seals stored secrets, but no test is added to the repo; the only verification is a one-off manual run under a temporary tsconfig that is not committed, so a later change to the sealing or AAD handling would not be caught.
Resolution: open

### ae9d3bec.2 [low] scripts/rewrap-config-server-key.ts:83
Anchor: in-diff
Claim: rewrap() does not reject duplicate store ids in one batch, so the same id can appear twice in the output and the caller must dedupe it.
Resolution: open

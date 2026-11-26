# Review 1ece75ef: fix(ci): an attribution repairs a commit whose PR-TASK trailer names no epic

Commit: 1ece75ef9d2fc2d9a2a2bb4f47dfe2aefb6a7568
Repo: console
Branch: 1121-1
Parent: aeaa5f836e9dfb57e8ea9fdb5f1e801459a255c0
Patch-Id: 95b1cc6b6f64a2905c497f24d1d4b0db1042235b
Reviewed-At: 2026-11-26T09:35:51Z
Model: claude-haiku-5-5
Cost: $0.0033 USD, 1 call(s), 19.9s
Diff: 5989 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI gate tooling and ledger entries only; no user-facing behaviour change.
Dropped: 0
Body-Sig: 02746fad451caaf8

## Findings

### 1ece75ef.1 [medium] scripts/gates/check-pr-task-trailers.ts:233
Anchor: in-diff
Claim: The REDUNDANT test only refuses when every trailer id is a known epic, so an attribution for a commit with one known and one unknown id (e.g. two PR-TASK lines) is accepted and the unknown id is then silently dropped by judge, widening the exemption beyond the commit message's 'names no known epic' scope.
Class: security
Resolution: not-a-bug | an attribution is a deliberate, reviewed repair entry that names its epic and a reason of at least 40 characters (scripts/gates/check-pr-task-trailers.ts:216-222); a commit carrying one known and one unknown id already belongs to the known epic, so attributing it repairs the typo rather than hiding it, and an attribution for a commit whose ids are all known stays REDUNDANT (check-pr-task-trailers. | d778be9d 2026-11-26T09:36:06Z

### 1ece75ef.2 [medium] scripts/gates/check-pr-task-trailers.ts:138
Anchor: in-diff
Claim: The comment says a trailer 'naming no epic' is repaired by an attribution, but line 139 skips every attributed commit, including one whose trailer mixes known and unknown ids, so the comment misstates the skip's scope.
Class: doc-contradicts-code
Resolution: fixed a5af803dac12d6a472fa47760fbf027a0d20c554 | d778be9d 2026-11-26T11:16:49Z

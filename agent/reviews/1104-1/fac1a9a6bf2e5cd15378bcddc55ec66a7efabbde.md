# Review fac1a9a6: test(cli): move the backup tests that asserted the single-endpoint, one-snapshot behavior to per-destination targets

Commit: fac1a9a6bf2e5cd15378bcddc55ec66a7efabbde
Repo: console
Branch: 1104-1
Parent: 89631b12071a70ce5dd8a1fa156b15b70e2ef18b
Patch-Id: 6cb9689567db9c6d4af72e02be86632faea07e2b
Reviewed-At: 2026-11-07T14:13:24Z
Model: claude-haiku-5-5
Cost: $0.0038 USD, 1 call(s), 25.4s
Diff: 9354 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=none why=Test-only change (3 test files); no user-facing behaviour change.
Dropped: 0
Body-Sig: 9dbf82d17d0e191a

## Findings

### fac1a9a6.1 [high] packages/cli/src/services/__tests__/backup-schedule-renet-contract.test.ts:262
Anchor: in-diff
Claim: Removing the twoDestinations matrix entry means the renet-contract gate can no longer fail for multi-destination strategies, while the chunkstore test in this same commit expects the generator to emit `--store offsite` for a non-home target that the renet source is said not to declare; a generator/renet mismatch on that flag now reaches production with no CI failure.
Resolution: open

### fac1a9a6.2 [medium] packages/cli/src/services/__tests__/backup-schedule-chunkstore.test.ts:126
Anchor: in-diff
Claim: The test title still says the destination cap is 'the tightest one winning', but the body now only asserts per-destination caps (12500000 for a, 6000000 for b); no assertion checks that the tighter cap wins on a single command, so that behaviour is untested and the title misstates what is checked.
Resolution: open

### fac1a9a6.3 [low] packages/cli/src/services/__tests__/backup-schedule-chunkstore.test.ts:163
Anchor: outside-diff
Claim: The test titled 'takes one snapshot per enabled destination' never sets or checks an enabled flag; it only passes two destinations with distinct targets, so the word 'enabled' describes behaviour the test does not exercise.
Resolution: open

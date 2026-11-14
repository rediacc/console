# Review 12d6a07f: feat(jobs): machine_prune runs the datastore prune then the unit prune as one function

Commit: 12d6a07fa68ac1daa5cef9ca2c6780292fd2fbee
Repo: private/renet
Branch: 1104-1
Parent: 5d9ea49d1582401b3a1ebf8a9bfee8a1e5a9b850
Patch-Id: 0d2e0ab977425e838b2e27de1bfb82c9e1e6375a
Reviewed-At: 2026-11-04T17:23:55Z
Model: claude-haiku-5-5
Cost: $0.0082 USD, 1 call(s), 34.4s
Diff: 48541 bytes, 21 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds a new renet subcommand, a new internal job function, and new i18n keys; no existing behaviour changed.
Dropped: 0
Body-Sig: 63c2afea39a90569

## Findings

### 12d6a07f.1 [medium] cmd/renet/repository_machine_prune.go:84
Anchor: in-diff
Claim: If the marker write for the units phase fails (stdout write error) after the datastore phase has run, `return err` skips the units phase and drops any datastore failure already collected in `errs`, contrary to the commit's 'a failed phase does not skip the other' contract.
Resolution: fixed 350cf7625a0f0c0b5ac3dd473c28a6aa2976b0fd | d778be9d 2026-11-06T04:52:24Z

### 12d6a07f.2 [low] pkg/functions/commands/machine_prune.go:8
Anchor: in-diff
Claim: The doc comment names the entry point as `rdc machine prune`, but the command this commit actually runs is `renet repository machine-prune`; the comment does not match the code it describes.
Resolution: fixed 0c19a80ccd08f6f0d403bb4f68065b267666b169 | d778be9d 2026-11-06T21:44:34Z

### 12d6a07f.3 [low] pkg/jobs/overlap.go:135
Anchor: in-diff
Claim: `machine_prune` is placed under the `// machine-shared: reads across repositories` heading yet mapped to ClassMachineExclusive, so the grouping comment contradicts the entry.
Resolution: fixed 95740306a1c956cd0bf3d280553dfa1abdc28a40 | d778be9d 2026-11-06T21:44:34Z

### 12d6a07f.4 [low] cmd/renet/repository_machine_prune_test.go:36
Anchor: in-diff
Claim: No test covers both phases failing (errors.Join path) or the marker-write error path, so the regression in the line-84 early return would not be caught.
Resolution: fixed 0c19a80ccd08f6f0d403bb4f68065b267666b169 | d778be9d 2026-11-06T21:44:35Z

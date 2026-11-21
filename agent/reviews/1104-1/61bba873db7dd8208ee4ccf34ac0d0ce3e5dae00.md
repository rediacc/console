# Review 61bba873: fix(cli): the job tests pass the repository gates, and backup-restore-path's tests follow the failure step

Commit: 61bba873db7dd8208ee4ccf34ac0d0ce3e5dae00
Repo: console
Branch: 1104-1
Parent: 2208d3d6a3b0456342bc3168a5b132b8d6f5dc17
Patch-Id: 51be46e2a5dd7838484a207395e386841bc50f7c
Reviewed-At: 2026-11-05T14:30:28Z
Model: claude-haiku-5-5
Cost: $0.0074 USD, 1 call(s), 23.4s
Diff: 35137 bytes, 16 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only changes, a CI env/doc registry addition, a carry-list entry and plan prose; no user-facing change.
Dropped: 0
Body-Sig: 06d6c763e4ceac3c

## Findings

### 61bba873.1 [medium] .ci/config/carried-reds.json:42
Anchor: in-diff
Claim: The commit adds PLAN-jobs-backup-real-machine-tests.md to the P-A1 carried-red list, so that plan's open-box finding no longer fails the gate. The reason says the entry is removed before any merge, but nothing in the diff enforces that removal, so the entry can outlive the backup push it was meant for.
Resolution: not-a-bug | .ci/config/carried-reds.json:2 CI still runs and fails every carried gate, so CI Complete blocks the merge | d778be9d 2026-11-06T05:35:59Z

### 61bba873.2 [medium] packages/cli/src/commands/__tests__/backup-restore-path.test.ts:258
Anchor: in-diff
Claim: The exit-18 test no longer runs the `backup restore --path` command. It calls the reportRestorePathFailure step handler directly with a hand-built exitCode of 18, so a regression that stops the failed job's exit code reaching that step would still pass this file.
Resolution: fixed 7bf39684e440dbce7b495abf8bd5f6f6c9d718f4 | d778be9d 2026-11-06T05:30:58Z

### 61bba873.3 [low] agent/plans/PLAN-ci-quick-cpu-scheduling.md:3
Anchor: in-diff
Claim: The added 'Updated: ... reread by d778be9d ... no box changed' stamps are attestations of review that the diff itself does not show. They appear to exist to satisfy check:ci-plan-housekeeping, so they carry no evidence of a real reread.
Resolution: not-a-bug | agent/plans/PLAN-ci-quick-cpu-scheduling.md:3 The Updated stamp is the form check_plan_housekeeping.py reads for a reread, and the claim it makes is checkable: `git log --oneline -- agent/plans/PLAN-ci-quick-cpu-scheduling.md` shows no box-changing commit after the stamp's date (the previous commits are the docs reconciliations bfb5c322e and c91f5d4c7). | d778be9d 2026-11-06T21:24:04Z

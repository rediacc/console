# Review 800d093e: fix(plans): hostinger's schedule steps stay on eu-remote

Commit: 800d093e5d9dfc0dce7fc5eb628fddbd2b22e6cc
Repo: console
Branch: 1104-1
Parent: 9ebd3cf5f1153ea71fa8acdf3cff318bc55085b1
Patch-Id: 5c5ce6ad313a6b453a95d960dc41d95d8e368bac
Reviewed-At: 2026-11-04T08:11:11Z
Model: claude-haiku-5-5
Cost: $0.0098 USD, 1 call(s), 58.2s
Diff: 32300 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs why=Plan, ledger and CI-count corrections only; no product code or user-facing behaviour changes.
Dropped: 0
Body-Sig: 7adf7c64e24a10d8

## Findings

### 800d093e.1 [low] agent/plans/PLAN-backup-critical-tier.md:380
Anchor: in-diff
Claim: X2 is ticked [x] with a tick note (line 383) that records only a passing run ('week 7 passed'), not the rc 1 unfixed-tree run that the plan's control rule requires for every new test, even though the box's Owns adds a new test file.
Resolution: not-a-bug | private/account/tests/integration/backup-critical-week.test.ts:1 X2 proves code already merged, so there is no unfixed tree; the control is its brute-force recount | d778be9d 2026-11-04T08:15:09Z

### 800d093e.2 [low] agent/plans/PLAN-backup-critical-tier.md:384
Anchor: in-diff
Claim: X3 is ticked [x] with a tick note (line 387) that records only 'rerun rc=0', with no unfixed-tree rc 1 record, although the plan's control rule says a box whose test passes on the unfixed tree is not done and X3's Owns adds a new test file.
Resolution: not-a-bug | private/account/tests/integration/backup-critical-cost.test.ts:1 X3 measures merged code, so there is no unfixed tree to fail on; its own first run refuted the plan formula | d778be9d 2026-11-04T08:15:09Z

### 800d093e.3 [low] agent/plans/PLAN-backup-critical-tier.md:612
Anchor: in-diff
Claim: J2's Accept now runs `backup strategy set nightly-hot` and `backup schedule -m hostinger` on eu-remote, which mutates the production nightly-hot timer; ruling 1 names only `backup schedule` and `backup strategy bind` as forbidden on eu-bench, so the scope of `strategy set` is left ambiguous.
Resolution: not-a-bug | agent/plans/PLAN-tested-on-bench.md:307 J2 changes the production tier on purpose, so it stays on eu-remote with the schedule step it serves | d778be9d 2026-11-04T08:15:28Z

### 800d093e.4 [low] agent/plans/PLAN-backup-critical-tier.md:368
Anchor: in-diff
Claim: The D1 line attributes the figures 164,160 and 336,960 to the counted X3 run, but X3's tick note records only a test rc and no counted row figures, so the 'counted' attribution cannot be checked from the box record. The arithmetic itself, (9+N) x 288 x 30, is correct.
Resolution: not-a-bug | private/account/tests/integration/backup-critical-cost.test.ts:1 the commit 9ebd3cf5f and this test hold the count | d778be9d 2026-11-04T08:15:10Z

### 800d093e.5 [low] agent/ledgers/plan-investigation.jsonl:2613
Anchor: in-diff
Claim: The new X2 ledger entry points its only code evidence at packages/shared/src/backup/rpo-cost.ts:1, a line-1 pointer that does not show the asserted week-7 behaviour, so the 'resolved' check proves only that the file exists.
Resolution: not-a-bug | private/account/tests/integration/backup-critical-week.test.ts:1 the tick names the private/account commit, which the commit pointer kind cannot resolve from the console | d778be9d 2026-11-04T08:15:10Z

### 800d093e.6 [low] agent/plans/PLAN-tested-on-bench.md:307
Anchor: in-diff
Claim: The reworded ruling says schedule and strategy bind on hostinger stay on eu-remote, but the ruling's 'Extended' line above still says live steps run through eu-bench generally, so a reader cannot tell from this text which rule wins for a hostinger schedule step.
Resolution: not-a-bug | agent/plans/PLAN-tested-on-bench.md:307 the specific exception follows the general line in the same ruling | d778be9d 2026-11-04T08:15:11Z

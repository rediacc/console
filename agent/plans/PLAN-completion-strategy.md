# Finish the big pieces: a completion strategy measured against the tree
Status: compacted
First-Seen: 2026-09-20
Owner: f4da5c2e
Full-Text-Blob: 08a8712b218e63ad5b3b42299abb6cd3f1d3ac16
Record-Sig: 49d077a4

## Why
The tooling transformation programme reported 62% box completion but 0 of 521 bash files deleted. The misleading metric masked that the real constraint was not ledger accrual (which already passed shadow verification for 81 of 82 pairs) but coverage — gate tests lacked ledgers to accrue from. The plan diagnosed this gap, identified a kill list of 72 boxes that could retire without
implementation, and proposed a 5-wave schedule prioritized by deletion value and constrained by seven contended singleton registrar files.

## Outcome
The plan entered execution 2026-09-09 and has been advancing under adopted ownership ([unresolved] as of 2026-09-20). Multiple boxes have been ticked and compacted across W7P4 (quality gates, 76 of 77 now Python), W9P2, W12P3.5, W7P5c (licensing census), and others. The plan remains active and in-progress; the kill list from section 2 has not been fully executed, and section 3's
accretion rule (G-A6) has not been wired into CI. The programme's observable progress metric (deletion) remains at zero files, while Python coverage in quality has advanced to 76 of 77 gates live.

## Lessons
- A box-count metric is decoupled from the work's actual axis (deletion). This plan carried three axes (ported, live, deleted) and correctly diagnosed that 62% of boxes meant nothing about progress on deletion. Monitor the work by what is actually gone, not what has been drafted.
- The measurement of a constraint changes the schedule. Coverage (writer work to record ledger rows) was orthogonal to accrual (merge throughput verifying existing rows). Conflating them would have scheduled the plan incorrectly — this split was what made parallelization possible.
- Seven contended singletons (package.json, gates.lock.json, ci-quality.yml, etc.) mean registrar-role serialization is the binding constraint past wave 3, not writer count. A schedule claiming otherwise is lying. Pin exactly one registrar per wave.
- Calendar-gated plan housekeeping (delete_days: 33, first red 2026-09-26) creates unmovable deadlines independent of parallelism. A 19-day plan absorbs new boxes faster than it closes them if the box-addition rate is not gated.
- An adopted plan carries prior ownership tag but may have different measurement regime from its predecessor. This plan's round 1 carried 83 ticked boxes that were "re-measured" and found to pin nine stale counts and four false premises. Preserve prior work, correct the numbers against the live tree.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: ready
Compacted-By: d778be9d
Compacted-At: 2026-09-20T17:54:19Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: agent/PLAN-tooling-transformation.md, .ci/scripts/quality/check_plan_boxes.py, .claude/hooks/stop/worklist.py, agent/PLAN-plan-file-lifecycle.md, agent/PLAN-env-to-bitwarden-v2.md, .ci/scripts/quality/check_secret_reachability.py, agent/archive/plans/PLAN-github-secrets-removal.md, .claude/hooks/stop/wl_store.py, CLAUDE.md, agent/PLAN-review-red-stop-hook-check.md, agent/PLAN-commit-author-identity.md, agent/PLAN-plyr-css-on-demand-loading.md, agent/PLAN-session-onboarding-marker.md, agent/archive/plans/PLAN-branch-aware-workflows.md, agent/PLAN-bws-rotation-on-failure.md
Gates: check:ci-language-policy, check:ci-plan-citations, check:ci-plan-housekeeping
Why-Source: model
Read-History: `git show 08a8712b218e63ad5b3b42299abb6cd3f1d3ac16` recovers the text; `git log --find-object=08a8712b218e63ad5b3b42299abb6cd3f1d3ac16 --all` names the commit

## History
- 2026-09-20T17:54:19Z compacted by d778be9d from `ready` (record-sig 49d077a4)

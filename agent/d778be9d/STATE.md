## SESSION d778be9d 2026-09-22T05:40:34Z

# d778be9d STATE (branch 0914-1, PR #589; local only, no push, PR-TASK: e87fa3ce trailer on every commit)

## Where things stand
HEAD 6c7bd6bb0. Landed since the plan move: 0bb1a4c15 (writers N+O: 7 twins+2 libs deleted, 9 workflow sparse-checkout cones fixed, run-legacy.sh verb census, ruling-7 widened to scripts/ops+drills+dev with 17 files/7244 lines frozen; plus check_plan_citations.py and check_plan_boxes.py both fixed for the same git-rename-blindness class, moved_from() shared via plan_lifecycle.py), d021d0cfb (the finished citation-repair plan moved to agent/plans/_done/), 6c7bd6bb0 (a stale domains.json citation to a deleted bash test file corrected). check:ci-plan-citations, check:ci-plan-boxes, check:ci-plan-folders all green with regression tests.
An Explore agent confirmed all 3 previously-uncertain run-legacy.sh verbs (dev, worktree, quality) are LIVE interactive-only entry points, same class as setup/devbox; no CI caller needed. Only the 7 already-confirmed-dead verbs (service, test, build, fix, check, pr, clean) need arm+body removal together (orphaned functions trip check:ci-dead-bash if done separately).
Writer P (ae1ee335dd012e805) is porting scripts/ops+drills+dev bash to Python (17 files, 7244 lines), reading .claude/agents/ops-vms.md first, skipping anything driving real VM/Ceph infra without a stub-driven test precedent; progress in scratchpad/p-progress.txt.

## Next action
1. When writer P reports: spot-check, git add -A the touched dirs, gen-docs --write if needed, prose baseline drain, gen:gates-lock if a registration changed, run the full ~27-gate set, commit by name with PR-TASK and a shape_cluster_diff quote.
2. Dispatch the legacy-router port: strip the 7 dead verbs (arm+body together) in one commit, then port the 5-8 live verbs (dev, worktree, quality, account, rotation, devbox, help) to Python one small batch at a time, each with a K=5 ledger and a stub-driven test before the bash is retired.
3. After that: .ci/docker/run-in-{web,render}.sh (port from scratch), the 8 unported bash gate tests (port to pytest), the 39-script real-run rehearsal (needs the operator's credentials, prepare a batched checklist first), then W1P6 deletes .ci/config/language-policy-baseline.json when every path is deleted or exempt.

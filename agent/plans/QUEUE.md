# Plan queue

The ordered queue of plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). One plan per PR by default. The first entry is the plan the live `MMDD-N` branch works: `.claude/hooks/post-bash/refresh_pr_body.py` writes it as the PR body's `Plan:` line once, and `rediacc_hooks.plan_gate.plan_merge_refusal` refuses the merge while that plan has an open box, unless the body carries an `Operational-Reason:` line.

Two lists, read in this order. `## Promoted` is hand-ordered by the operator and wins; no tool writes it, and an entry leaves it by hand when its PR merges. `## Generated` is rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` from live tracked plans with at least one open box: prerequisites first (`Depends-On:`, task refs and sub-plans like `PLAN-x.A0.md`, each prerequisite pulled ahead to the rank of what needs it), then held plans after unheld ones, prerequisites excepted, then in-progress plans before not-started ones, then operator Priority, AI Priority and path. Plans with no open box are listed under `### Not queued` with the reason, never as entries. Regenerate with `npm run check:ci-plan-record -- --update`; the same gate fails while the section is stale.

Entry format: `1. agent/plans/PLAN-<slug>.md`, optionally followed by ` -- <note>`. Only numbered entries inside the two sections are read.

## Promoted

1. agent/plans/PLAN-plan-priority-concurrency.md -- operator /ask 2026-10-03: X's last box, T12 prose
2. agent/plans/PLAN-ci-consolidation.md -- operator /ask 2026-10-04: "Next (pos 2)"; candidates 1, 3, 4, 6, 7 of agent/reports/consolidation-investigation-2026-10-04.md in one plan, one PR
3. agent/plans/PLAN-commit-as-you-go.md -- operator /ask 2026-10-03: T6 (the `nocommit:` tick arm Z depends on), with T0 and T9
4. agent/plans/PLAN-gate-drop-receipt-verify.md -- operator /ask 2026-10-04: "After commit-as-you-go"; ci:quick skipped a touched slow gate twice on 2026-10-03 and the push guard never noticed (#74f48292)
5. agent/plans/PLAN-config-team-scoping.md -- operator /ask 2026-10-03: T9 (the enforced matrix in DESIGN-CONFIG-STORAGE.md) and T10 (live smoke)
6. agent/plans/PLAN-plan-dependencies.md -- operator /ask 2026-10-03: the 9 open boxes
7. agent/plans/PLAN-remove-cross-session-messaging.md -- operator /ask 2026-10-03: Step 12

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-plan-per-pr-loop.md -- P1, approved, in progress (13 of 16 boxes ticked)
2. agent/plans/PLAN-stop-hook-one-plan-scope.md -- P1, approved, in progress (14 of 15 boxes ticked)
3. agent/plans/PLAN-retire-bash-oracles.A0.md -- P2, executing, not started
4. agent/plans/PLAN-plan-compaction-bindings.md -- P1, approved, not started
5. agent/plans/PLAN-plan-preflight.md -- P1, approved, not started
6. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, not started
7. agent/plans/PLAN-locale-techdiff-resync.md -- P2, ready, not started
8. agent/plans/PLAN-breakpoint-secret-shape.md -- P3, design, not started
9. agent/plans/PLAN-cloudflare-proxy.md -- P3, proposed, not started
10. agent/plans/PLAN-renet-fetch-hardening.md -- P3, draft, not started
11. agent/plans/PLAN-config-passkey-optional.md -- P0, held, in progress (3 of 4 boxes ticked)
12. agent/plans/PLAN-app-wide-org-selection.md -- P0, held, in progress (2 of 3 boxes ticked), dep-blocked
13. agent/plans/PLAN-config-handoff-relay-only.md -- P0, held, in progress (9 of 11 boxes ticked), dep-blocked
14. agent/plans/PLAN-token-ip-rebind.md -- P0, held, in progress (9 of 10 boxes ticked), dep-blocked
15. agent/plans/PLAN-config-sync-hardening.md -- P0, held, in progress (18 of 19 boxes ticked), dep-blocked
16. agent/plans/PLAN-haiku-model-routing.md -- P1, held, in progress (11 of 20 boxes ticked)
17. agent/plans/PLAN-secret-namespace-migration.md -- P1, held, in progress (29 of 34 boxes ticked)
18. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, held, in progress (16 of 17 boxes ticked)
19. agent/plans/PLAN-stop-hook-retro-20260925.md -- P1, held, in progress (5 of 10 boxes ticked)
20. agent/plans/PLAN-tooling-transformation.md -- P1, held, in progress (151 of 154 boxes ticked)
21. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, held, in progress (6 of 7 boxes ticked), dep-blocked
22. agent/plans/PLAN-w7p5a-real-run-dispatch.md -- P1, held, in progress (7 of 9 boxes ticked)
23. agent/plans/PLAN-account-env-to-bws.md -- P2, held, in progress (19 of 20 boxes ticked)
24. agent/plans/PLAN-retire-bash-oracles.md -- P2, held, in progress (4 of 15 boxes ticked), dep-blocked
25. agent/plans/PLAN-stop-hook-retro-20260924.md -- P2, held, in progress (22 of 23 boxes ticked)
26. agent/plans/PLAN-biome-only-lint.md -- P3, held, in progress (10 of 29 boxes ticked)
27. agent/plans/PLAN-env-to-bitwarden-v2.md -- P3, held, in progress (9 of 10 boxes ticked)
28. agent/plans/PLAN-stop-hook-rulings-campaign.md -- P3, held, in progress (1 of 17 boxes ticked)
29. agent/plans/PLAN-config-networkid-sync.md -- P1, held, not started, dep-blocked
30. agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- P3, held, not started
31. agent/plans/PLAN-ci-watch-enforcement.md -- P3, held, not started
32. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, held, not started
33. agent/plans/PLAN-trap-enforcement.md -- P3, held, not started
34. agent/plans/PLAN-uncommitted-work-exposure-check.md -- P3, held, not started

### Not queued

- agent/plans/PLAN-github-pr-review-restore.md -- all boxes ticked: close it
- agent/plans/PLAN-program-state-in-repo.md -- all boxes ticked: close it
- agent/plans/PLAN-rdc-readonly-mode.md -- all boxes ticked: close it
- agent/plans/PLAN-repair-prose-style-findings.md -- all boxes ticked: close it
- agent/plans/PLAN-scheduled-red-detector.md -- all boxes ticked: close it
- agent/plans/PLAN-stop-hook-focus-mode.md -- all boxes ticked: close it
- agent/plans/PLAN-typecheck-orphan-packages.md -- all boxes ticked: close it
<!-- queue:generated:end -->

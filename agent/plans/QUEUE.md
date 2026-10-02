# Plan queue

The ordered queue of plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). One plan per PR by default. The first entry is the plan the live `MMDD-N` branch works: `.claude/hooks/post-bash/refresh_pr_body.py` writes it as the PR body's `Plan:` line once, and `rediacc_hooks.plan_gate.plan_merge_refusal` refuses the merge while that plan has an open box, unless the body carries an `Operational-Reason:` line.

Two lists, read in this order. `## Promoted` is hand-ordered by the operator and wins; no tool writes it, and an entry leaves it by hand when its PR merges. `## Generated` is rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` from live tracked plans with at least one open box: prerequisites first (`Depends-On:`, task refs and sub-plans like `PLAN-x.A0.md`, each prerequisite pulled ahead to the rank of what needs it), then in-progress plans before not-started ones, then operator Priority, AI Priority and path; `Status: held` does not change the order. Plans with no open box are listed under `### Not queued` with the reason, never as entries. Regenerate with `npm run check:ci-plan-record -- --update`; the same gate fails while the section is stale.

Entry format: `1. agent/plans/PLAN-<slug>.md`, optionally followed by ` -- <note>`. Only numbered entries inside the two sections are read.

## Promoted

1. agent/plans/PLAN-plan-per-pr-loop.md -- PR #591 also carries PLAN-ci-verdict and PLAN-per-commit-review, so it merges with an Operational-Reason

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-haiku-model-routing.md -- P1, held, in progress (11 of 20 boxes ticked)
2. agent/plans/PLAN-rdc-readonly-mode.md -- P1, held, in progress (22 of 23 boxes ticked)
3. agent/plans/PLAN-secret-namespace-migration.md -- P1, held, in progress (29 of 34 boxes ticked)
4. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, held, in progress (16 of 17 boxes ticked)
5. agent/plans/PLAN-stop-hook-retro-20260925.md -- P1, held, in progress (5 of 10 boxes ticked)
6. agent/plans/PLAN-tooling-transformation.md -- P1, held, in progress (151 of 154 boxes ticked)
7. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, held, in progress (6 of 7 boxes ticked), dep-blocked
8. agent/plans/PLAN-w7p5a-real-run-dispatch.md -- P1, held, in progress (7 of 9 boxes ticked)
9. agent/plans/PLAN-account-env-to-bws.md -- P2, held, in progress (19 of 20 boxes ticked)
10. agent/plans/PLAN-stop-hook-focus-mode.md -- P2, held, in progress (7 of 8 boxes ticked)
11. agent/plans/PLAN-stop-hook-retro-20260924.md -- P2, held, in progress (22 of 23 boxes ticked)
12. agent/plans/PLAN-biome-only-lint.md -- P3, held, in progress (10 of 29 boxes ticked)
13. agent/plans/PLAN-env-to-bitwarden-v2.md -- P3, held, in progress (9 of 10 boxes ticked)
14. agent/plans/PLAN-repair-prose-style-findings.md -- P3, held, in progress (5 of 6 boxes ticked)
15. agent/plans/PLAN-stop-hook-rulings-campaign.md -- P3, held, in progress (1 of 17 boxes ticked)
16. agent/plans/PLAN-commit-as-you-go.md -- P0, held, not started
17. agent/plans/PLAN-config-passkey-optional.md -- P0, held, not started
18. agent/plans/PLAN-app-wide-org-selection.md -- P0, held, not started, dep-blocked
19. agent/plans/PLAN-config-handoff-relay-only.md -- P0, held, not started, dep-blocked
20. agent/plans/PLAN-token-ip-rebind.md -- P0, held, not started, dep-blocked
21. agent/plans/PLAN-config-sync-hardening.md -- P0, held, not started, dep-blocked
22. agent/plans/PLAN-config-networkid-sync.md -- P1, held, not started, dep-blocked
23. agent/plans/PLAN-config-team-scoping.md -- P1, held, not started, dep-blocked
24. agent/plans/PLAN-plan-dependencies.md -- P1, held, not started
25. agent/plans/PLAN-plan-priority-concurrency.md -- P1, held, not started, dep-blocked
26. agent/plans/PLAN-retire-bash-oracles.md -- P2, held, not started
27. agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- P3, held, not started
28. agent/plans/PLAN-ci-watch-enforcement.md -- P3, held, not started
29. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, held, not started
30. agent/plans/PLAN-trap-enforcement.md -- P3, held, not started
31. agent/plans/PLAN-uncommitted-work-exposure-check.md -- P3, held, not started

### Not queued

- agent/plans/PLAN-breakpoint-secret-shape.md -- no boxes yet: add boxes
- agent/plans/PLAN-cloudflare-proxy.md -- no boxes yet: add boxes
- agent/plans/PLAN-locale-techdiff-resync.md -- no boxes yet: add boxes
- agent/plans/PLAN-remove-cross-session-messaging.md -- no boxes yet: add boxes
- agent/plans/PLAN-renet-fetch-hardening.md -- no boxes yet: add boxes
- agent/plans/PLAN-retire-bash-oracles.A0.md -- no boxes yet: add boxes
- agent/plans/PLAN-typecheck-orphan-packages.md -- no boxes yet: add boxes
<!-- queue:generated:end -->

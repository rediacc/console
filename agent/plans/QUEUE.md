# Plan queue

The ordered queue of plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). One plan per PR by default. The first entry is the plan the live `MMDD-N` branch works: `.claude/hooks/post-bash/refresh_pr_body.py` writes it as the PR body's `Plan:` line once, and `rediacc_hooks.plan_gate.plan_merge_refusal` refuses the merge while that plan has an open box, unless the body carries an `Operational-Reason:` line.

Two lists, read in this order. `## Promoted` is hand-ordered by the operator and wins; no tool writes it, and an entry leaves it by hand when its PR merges. `## Generated` is rendered between the markers by `.claude/hooks/stop/wl_planqueue.py`: live tracked plans by `wl_planorder.plan_key` (dependency-blocked last, then Priority), open plans before `Status: held` ones, Promoted entries left out. A `--plan-tick` refreshes it, and `npm run check:ci-plan-record -- --update` regenerates it; that gate fails while the section differs from the render.

Entry format: `1. agent/plans/PLAN-<slug>.md`, optionally followed by ` -- <note>`. Only numbered entries inside the two sections are read.

## Promoted

1. agent/plans/PLAN-plan-per-pr-loop.md -- PR #591 also carries PLAN-ci-verdict and PLAN-per-commit-review, so it merges with an Operational-Reason

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-b2-emit-matrix.md -- P1, partially
2. agent/plans/PLAN-ci-gate-write-taint-scanners.md -- P1, active
3. agent/plans/PLAN-ci-verdict.md -- P1, approved
4. agent/plans/PLAN-stop-hook-continuity.md -- P1, executing
5. agent/plans/PLAN-locale-techdiff-resync.md -- P2, ready
6. agent/plans/PLAN-parallel-writer-roster.md -- P2, ready
7. agent/plans/PLAN-remove-cross-session-messaging.md -- P2, draft
8. agent/plans/PLAN-stop-hook-overhaul.md -- P2, ready
9. agent/plans/PLAN-typecheck-orphan-packages.md -- P2, ready
10. agent/plans/PLAN-breakpoint-secret-shape.md -- P3, design
11. agent/plans/PLAN-cloudflare-proxy.md -- P3, proposed
12. agent/plans/PLAN-renet-fetch-hardening.md -- P3, parked
13. agent/plans/PLAN-retire-bash-oracles.A0.md -- P3, no Status
14. agent/plans/PLAN-per-commit-review.md -- P1, approved, dep-blocked
15. agent/plans/PLAN-commit-as-you-go.md -- P0, held
16. agent/plans/PLAN-config-passkey-optional.md -- P0, held
17. agent/plans/PLAN-haiku-model-routing.md -- P1, held
18. agent/plans/PLAN-rdc-readonly-mode.md -- P1, held
19. agent/plans/PLAN-secret-namespace-migration.md -- P1, held
20. agent/plans/PLAN-stop-hook-focus-mode.md -- P1, held
21. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, held
22. agent/plans/PLAN-stop-hook-retro-20260925.md -- P1, held
23. agent/plans/PLAN-tooling-transformation.md -- P1, held
24. agent/plans/PLAN-w7p5a-real-run-dispatch.md -- P1, held
25. agent/plans/PLAN-account-env-to-bws.md -- P2, held
26. agent/plans/PLAN-retire-bash-oracles.md -- P2, held
27. agent/plans/PLAN-stop-hook-retro-20260924.md -- P2, held
28. agent/plans/PLAN-biome-only-lint.md -- P3, held
29. agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- P3, held
30. agent/plans/PLAN-ci-watch-enforcement.md -- P3, held
31. agent/plans/PLAN-env-to-bitwarden-v2.md -- P3, held
32. agent/plans/PLAN-repair-prose-style-findings.md -- P3, held
33. agent/plans/PLAN-stop-hook-rulings-campaign.md -- P3, held
34. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, held
35. agent/plans/PLAN-trap-enforcement.md -- P3, held
36. agent/plans/PLAN-uncommitted-work-exposure-check.md -- P3, held
37. agent/plans/PLAN-app-wide-org-selection.md -- P0, held, dep-blocked
38. agent/plans/PLAN-config-handoff-relay-only.md -- P0, held, dep-blocked
39. agent/plans/PLAN-config-sync-hardening.md -- P0, held, dep-blocked
40. agent/plans/PLAN-token-ip-rebind.md -- P0, held, dep-blocked
41. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, held, dep-blocked
42. agent/plans/PLAN-config-networkid-sync.md -- P1, held, dep-blocked
43. agent/plans/PLAN-config-team-scoping.md -- P1, held, dep-blocked
44. agent/plans/PLAN-plan-dependencies.md -- P1, held, dep-blocked
45. agent/plans/PLAN-plan-priority-concurrency.md -- P1, held, dep-blocked
<!-- queue:generated:end -->

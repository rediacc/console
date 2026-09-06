
## Plan census

Every `agent/PLAN-*.md`, one row, so the SessionStart and PostCompact plans
block can be printed from THIS file instead of opening all 83 of them. The
hook checks freshness with `stat` alone (path set plus byte size) and falls
back to reading the plans, loudly, when the two disagree.

| Plan | Status | lines | open | ticked | bytes |
|---|---|---|---|---|---|
| `agent/PLAN-add-chunkstore-backup-verb.md` | draft | 559 | 0 | 0 | 34871 |
| `agent/PLAN-add-js-extensions-shared.md` | draft | 617 | 0 | 0 | 31078 |
| `agent/PLAN-agent-hints-implementation.md` | ready | 699 | 0 | 0 | 37587 |
| `agent/PLAN-agent-hints-in-stop-hook.md` | superseded | 472 | 0 | 0 | 28843 |
| `agent/PLAN-ask-flow-preemptive-settled-check.md` | draft | 552 | 0 | 0 | 28343 |
| `agent/PLAN-backup-list-executor-fix.md` | step | 544 | 0 | 0 | 33411 |
| `agent/PLAN-backup-quota-delta-gc.md` | draft | 587 | 0 | 0 | 36384 |
| `agent/PLAN-backup-restore-target-license.md` | draft | 818 | 0 | 0 | 44224 |
| `agent/PLAN-branch-aware-workflows.md` | partially | 154 | 2 | 3 | 9633 |
| `agent/PLAN-breakpoint-secret-shape.md` | design | 68 | 0 | 0 | 3357 |
| `agent/PLAN-bump-k3s-upstream-1-36-4.md` | draft | 494 | 0 | 0 | 24922 |
| `agent/PLAN-bws-rotation-on-failure.md` | draft | 130 | 18 | 0 | 11127 |
| `agent/PLAN-chunk-store-browse-DECISION.md` | UNKNOWN | 149 | 0 | 0 | 7767 |
| `agent/PLAN-chunk-store-browse-engine.md` | proposal | 625 | 0 | 0 | 37512 |
| `agent/PLAN-chunk-store-browse-server.md` | design | 845 | 0 | 0 | 45072 |
| `agent/PLAN-chunkstore-restore.md` | draft | 634 | 0 | 0 | 36431 |
| `agent/PLAN-ci-trace-no-pr-branch.md` | done | 171 | 0 | 0 | 9783 |
| `agent/PLAN-ci-watch-enforcement.md` | draft | 283 | 0 | 0 | 15625 |
| `agent/PLAN-cli-em-dash-lint-gate.md` | done | 490 | 0 | 0 | 30094 |
| `agent/PLAN-cold-path.md` | done | 241 | 0 | 0 | 13073 |
| `agent/PLAN-commit-author-identity.md` | draft | 235 | 13 | 0 | 13995 |
| `agent/PLAN-consolidate-test-scaffolding.md` | done | 80 | 0 | 4 | 3941 |
| `agent/PLAN-docker-image-freshness-soak-filter.md` | done | 117 | 0 | 0 | 5584 |
| `agent/PLAN-duplication-angle.md` | implemented | 241 | 0 | 0 | 12492 |
| `agent/PLAN-durable-reports-and-push-inbox.md` | done | 813 | 0 | 0 | 46584 |
| `agent/PLAN-env-to-bitwarden-v2.md` | draft | 687 | 5 | 4 | 44971 |
| `agent/PLAN-env-to-bitwarden.md` | draft | 734 | 20 | 1 | 55240 |
| `agent/PLAN-fix-ci-contention-aware-timeouts.md` | done | 354 | 0 | 0 | 20483 |
| `agent/PLAN-fix-german-translation-artifacts.md` | done | 189 | 0 | 0 | 11264 |
| `agent/PLAN-fix-in-session-rule.md` | done | 620 | 0 | 0 | 28648 |
| `agent/PLAN-fix-tutorial-player-debug-hook-attachment.md` | done | 305 | 0 | 0 | 19395 |
| `agent/PLAN-git-history-media-rewrite.md` | ready | 321 | 0 | 0 | 15185 |
| `agent/PLAN-github-actions-workflow-run-trigger-fix.md` | done | 630 | 0 | 0 | 31610 |
| `agent/PLAN-github-secrets-removal.md` | draft | 580 | 13 | 1 | 46356 |
| `agent/PLAN-greenlight-verify-at-read.md` | done | 164 | 0 | 0 | 8649 |
| `agent/PLAN-handoff-sequence.md` | draft | 126 | 7 | 0 | 8365 |
| `agent/PLAN-hook-inventory-warn-guards.md` | landed | 89 | 0 | 0 | 4112 |
| `agent/PLAN-judge-gate-worthiness-and-surface-scope.md` | draft | 548 | 0 | 0 | 30552 |
| `agent/PLAN-lint-css-ci-wiring.md` | done | 470 | 0 | 0 | 27937 |
| `agent/PLAN-lint-rule-matrix-probe.md` | done | 593 | 0 | 0 | 36729 |
| `agent/PLAN-local-ci-gate-prerequisites.md` | landed | 102 | 0 | 0 | 4685 |
| `agent/PLAN-locale-techdiff-resync.md` | ready | 89 | 0 | 0 | 4531 |
| `agent/PLAN-localize-cheat-sheet-rendering.md` | accepted | 522 | 0 | 0 | 30042 |
| `agent/PLAN-migrate-command.md` | draft | 226 | 11 | 0 | 41130 |
| `agent/PLAN-nightly-retry-and-watchdog-noise.md` | done | 172 | 0 | 0 | 8909 |
| `agent/PLAN-npm-ci-parallel-parity.md` | done | 920 | 0 | 0 | 46148 |
| `agent/PLAN-plan-file-lifecycle.md` | ready | 456 | 3 | 10 | 28868 |
| `agent/PLAN-plyr-css-on-demand-loading.md` | draft | 138 | 11 | 0 | 7923 |
| `agent/PLAN-promote-mutation-runner.md` | done | 923 | 0 | 0 | 51701 |
| `agent/PLAN-rclone-decommission.md` | done | 394 | 0 | 0 | 20036 |
| `agent/PLAN-reggate-effort-cap.md` | designed | 317 | 0 | 0 | 16667 |
| `agent/PLAN-renet-fetch-hardening.md` | draft | 202 | 0 | 0 | 9309 |
| `agent/PLAN-require-testid-sweep.md` | done | 132 | 0 | 0 | 6900 |
| `agent/PLAN-resprofile-wave2.md` | approved | 137 | 0 | 0 | 8402 |
| `agent/PLAN-resumable-rebase-executor.md` | implemented | 202 | 0 | 0 | 9886 |
| `agent/PLAN-review-red-stop-hook-check.md` | done | 719 | 0 | 0 | 36616 |
| `agent/PLAN-rotation-gh-removal.md` | plan | 70 | 0 | 0 | 3905 |
| `agent/PLAN-runtime-caller-identity.md` | design | 607 | 0 | 0 | 32159 |
| `agent/PLAN-scope-gate-sort-collation.md` | draft | 191 | 0 | 0 | 9905 |
| `agent/PLAN-scope-gates-split.md` | approved | 241 | 0 | 0 | 21915 |
| `agent/PLAN-secret-names-one-to-one.md` | design | 455 | 9 | 3 | 31384 |
| `agent/PLAN-secret-namespace-migration.md` | partially | 2624 | 7 | 21 | 173053 |
| `agent/PLAN-sentence-aware-wrapping.md` | draft | 439 | 0 | 0 | 27072 |
| `agent/PLAN-session-onboarding-marker.md` | draft | 208 | 6 | 4 | 11725 |
| `agent/PLAN-shell-resource-profiling.md` | landed | 479 | 0 | 0 | 31637 |
| `agent/PLAN-skip-release-gates-r2-manifest.md` | done | 453 | 0 | 0 | 26375 |
| `agent/PLAN-ssr-nav-locale.md` | proposed | 90 | 0 | 0 | 4202 |
| `agent/PLAN-state-md-session-isolation.md` | done | 730 | 0 | 0 | 40069 |
| `agent/PLAN-stop-always-tier.md` | landed | 237 | 0 | 0 | 12453 |
| `agent/PLAN-stop-hook-cadence.md` | done | 273 | 0 | 0 | 14828 |
| `agent/PLAN-stop-plan-box-enforcement.md` | superseded | 143 | 6 | 0 | 8815 |
| `agent/PLAN-stop-report-queue.md` | done | 586 | 0 | 0 | 29536 |
| `agent/PLAN-subagent-idle-detection.md` | ready | 399 | 0 | 0 | 21501 |
| `agent/PLAN-subscription-status-error-swallowing.md` | done | 106 | 0 | 5 | 4621 |
| `agent/PLAN-sync-docker-latest-tag-with-releases.md` | done | 233 | 0 | 0 | 12208 |
| `agent/PLAN-test-advisor.md` | done | 132 | 0 | 0 | 6884 |
| `agent/PLAN-testing-surface-audit.md` | draft | 652 | 0 | 0 | 40304 |
| `agent/PLAN-trap-enforcement.md` | w | 820 | 0 | 0 | 49268 |
| `agent/PLAN-typecheck-orphan-packages.md` | ready | 84 | 0 | 0 | 4529 |
| `agent/PLAN-unify-trap-corpus.md` | superseded | 572 | 0 | 0 | 33769 |
| `agent/PLAN-wire-account-vitest-ci.md` | draft | 406 | 0 | 0 | 23112 |
| `agent/PLAN-worklist-ownership-continuity.md` | draft | 224 | 3 | 11 | 13033 |
| `agent/PLAN-www-bundle-determinism.md` | draft | 212 | 0 | 0 | 10993 |

83 plan(s), 17 carrying boxes. Regenerate with `npm run check:ci-plan-record -- --update`.

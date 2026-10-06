# Plan queue

The ordered queue of plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). One plan per PR by default; with `turbo: on` in `## Settings` the live PR keeps taking queued plans (agent/plans/PLAN-stop-hook-turbo.md). The first entry is the plan the live `MMDD-N` branch works: `.claude/hooks/post-bash/refresh_pr_body.py` writes it as the PR body's `Plan:` line once, and `rediacc_hooks.plan_gate.plan_merge_refusal` refuses the merge while that plan has an open box, unless the body carries an `Operational-Reason:` line.

Two lists, read in this order. `## Promoted` is hand-ordered by the operator and wins; no tool writes it, and an entry leaves it by hand when its PR merges. `## Generated` is rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` from live tracked plans with at least one open box: prerequisites first (`Depends-On:`, task refs and sub-plans like `PLAN-x.A0.md`, each prerequisite pulled ahead to the rank of what needs it), then held plans after unheld ones, prerequisites excepted, then in-progress plans before not-started ones, then operator Priority, AI Priority and path. Plans with no open box are listed under `### Not queued` with the reason, never as entries. Regenerate with `npm run check:ci-plan-record -- --update`; the same gate fails while the section is stale.

`## In flight`, between `## Settings` and `## Promoted`, says what the loop is working on now: the effective switches, every active focus, the live branch and its PR, each plan in the PR's plan set with its box progress and how it joined (the `Plan:` line, a turbo batch claim, an `Operational-Reason:` addition, a prerequisite), the branch's epics outside that set, live writers, leased items, and the next plan with its reason. The Stop hook and the `--queue-set` and `--focus` verbs render it between its markers from runtime state; no gate compares it, and no number in it is a list entry.

Entry format: `1. agent/plans/PLAN-<slug>.md`, optionally followed by ` -- <note>`. Only numbered entries inside the two sections are read.

## Settings

The switchboard for the Stop hook, read by `.claude/hooks/stop/wl_planqueue.py` (`settings`). One fenced block, `key: value` per line, an optional ` -- <note>` carrying the operator's reason. A missing key or a bad value falls back to the fail-safe default (hook on, turbo off) and `npm run check:ci-plan-record` names the problem. Change it with `worklist.py --queue-set <me> key=value ... [--note "<text>"]`, then commit this file.

What each key does (default in brackets):

- `stop_hook` (on): the whole Stop hook. `off` allows every stop with one notice and runs no check.
- `turbo` (off): `off` keeps one plan per PR. `on` hands each free writer slot the next eligible queued plan, which joins the live PR's `Plan:` line, and keeps going until turbo is switched off.
- `batch_size` (1): under turbo, the minimum number of finished plans before the PR is offered for merge. The merge itself never refuses a shorter PR.
- `plan_concurrency` (1): under turbo, the most unfinished plans in flight at once. The PR's own unfinished plans and the plans live writers serve count against it, so a free writer slot opens a new plan only below this ceiling.
- `writer_cap` (4): the most writer agents live at once. A spawn beyond it is refused (`block_agent_cap`), and the Stop hook blocks on a roster above it.
- `commit_remind_min` (15): minutes without a commit, while this session's own edits are still uncommitted, before the Stop hook and the post-tool hook remind it to commit the verified unit. A reminder, never a block (agent/plans/PLAN-fast-loop.md Part 2).
- `cadence` (on): lets a stop through after a demand when the session has reported something new, so the hook does not demand on every stop. Always-tier checks still block.
- `agent_hint` (on): names a specialist agent (`.claude/agents/*.md`) that matches the open work, including once after each compaction.
- `agent_pushback` (on): blocks a stop that declares work out of reach ("cannot be done here"), once per claim, and names the specialist agent that fits it when one clears the hint's confidence floor.
- `judge` (on): the LLM judge that reviews a stop when work remains. The env var `WORKLIST_JUDGE=on|off` overrides it, for tests.

A ` -- solo` note on a Promoted entry keeps that plan alone in its PR under turbo.

```stop-hook
stop_hook: on -- operator 2026-10-06: back on once PLAN-fast-loop completed
turbo: off -- operator 2026-10-04: turbo off; running writers finish, no new plans start
batch_size: 3 -- operator 2026-10-04: go in parallel as much as possible
plan_concurrency: 5 -- operator 2026-10-04: plan limit 5
writer_cap: 15 -- operator 2026-10-04: parallel limit 15
cadence: on
agent_hint: on
agent_pushback: on
judge: on
commit_remind_min: 15 -- operator 2026-10-06: PLAN-fast-loop Part 2 default
```

## In flight

What the loop is working on now, rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` (`refresh_inflight`) on every stop and on every `worklist.py --queue-set` or `--focus`. It is runtime state: rewritten only when it changes, never compared by `npm run check:ci-plan-record`, and a committed copy is a snapshot from its commit.

<!-- queue:inflight:begin -->
- Mode: stop_hook on; turbo off; batch_size 3; plan_concurrency 5; writer_cap 15; commit_remind_min 15; cadence on; agent_hint on; agent_pushback on; judge on.
- Focus: off.
- Branch: 1006-2, PR #597 open.
- Plans on the PR (1):
  - agent/plans/PLAN-fast-loop.md -- 19 of 19 boxes ticked, the PR body's `Plan:` line
- Work outside the PR's plans (1 epic(s)):
  - epic 97672f9f, no plan, 95 commit(s) on the branch, 0 open item(s): Operator 2026-10-06 follow-ups: regeneration guard, ci-trace root causes and main-red alert, ci:quick scheduler utilization, package retention, budget 5xx retry
- Writers: 0 live of writer_cap 15 (session d778be9d).
- Leased items: 4: #c5fe5295 (worker:684272, d778be9d), #de0d355c (worker:b5hugmupy, d778be9d), #eaf3d3f1 (worker:a3b301a2444ae6615, d778be9d), #f28caf3f (worker:b5hugmupy, d778be9d).
- Next plan: agent/plans/PLAN-ci-consolidation.md, Promoted entry 1 (solo); starts on the next branch after PR #597 merges.
<!-- queue:inflight:end -->

## Promoted

1. agent/plans/PLAN-ci-consolidation.md -- operator /ask 2026-10-04: "Next (pos 2)"; candidates 1, 3, 4, 6, 7 of agent/reports/consolidation-investigation-2026-10-04.md in one plan, one PR -- solo
2. agent/plans/PLAN-commit-as-you-go.md -- operator /ask 2026-10-03: T6 (the `nocommit:` tick arm Z depends on), with T0 and T9
3. agent/plans/PLAN-config-team-scoping.md -- operator /ask 2026-10-03: T9 (the enforced matrix in DESIGN-CONFIG-STORAGE.md) and T10 (live smoke)
4. agent/plans/PLAN-plan-dependencies.md -- operator /ask 2026-10-03: the 9 open boxes
5. agent/plans/PLAN-remove-cross-session-messaging.md -- operator /ask 2026-10-03: Step 12

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-config-passkey-optional.md -- P0, approved, in progress (3 of 4 boxes ticked)
2. agent/plans/PLAN-app-wide-org-selection.md -- P0, approved, in progress (2 of 3 boxes ticked), dep-blocked
3. agent/plans/PLAN-config-handoff-relay-only.md -- P0, draft, in progress (9 of 11 boxes ticked), dep-blocked
4. agent/plans/PLAN-token-ip-rebind.md -- P0, draft, in progress (9 of 10 boxes ticked), dep-blocked
5. agent/plans/PLAN-config-sync-hardening.md -- P0, draft, in progress (18 of 19 boxes ticked), dep-blocked
6. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
7. agent/plans/PLAN-plan-per-pr-loop.md -- P1, approved, in progress (15 of 16 boxes ticked)
8. agent/plans/PLAN-secret-namespace-migration.md -- P1, executing, in progress (29 of 34 boxes ticked)
9. agent/plans/PLAN-stop-hook-one-plan-scope.md -- P1, approved, in progress (14 of 15 boxes ticked)
10. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, executing, in progress (16 of 17 boxes ticked)
11. agent/plans/PLAN-tooling-transformation.md -- P1, ready, in progress (151 of 154 boxes ticked)
12. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked), dep-blocked
13. agent/plans/PLAN-w7p5a-real-run-dispatch.md -- P1, in-progress, in progress (7 of 9 boxes ticked)
14. agent/plans/PLAN-account-env-to-bws.md -- P2, draft, in progress (19 of 20 boxes ticked)
15. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, in progress (2 of 5 boxes ticked)
16. agent/plans/PLAN-retire-bash-oracles.A0.md -- P2, executing, not started
17. agent/plans/PLAN-retire-bash-oracles.md -- P2, approved, in progress (6 of 15 boxes ticked), dep-blocked
18. agent/plans/PLAN-stop-hook-retro-20260924.md -- P2, ready, in progress (22 of 23 boxes ticked)
19. agent/plans/PLAN-biome-only-lint.md -- P3, draft, in progress (10 of 29 boxes ticked)
20. agent/plans/PLAN-env-to-bitwarden-v2.md -- P3, draft, in progress (9 of 10 boxes ticked)
21. agent/plans/PLAN-stop-hook-rulings-campaign.md -- P3, draft, in progress (1 of 17 boxes ticked)
22. agent/plans/PLAN-deletion-budget.md -- P3 (operator), draft, not started
23. agent/plans/PLAN-config-networkid-sync.md -- P1, draft, not started, dep-blocked
24. agent/plans/PLAN-plan-compaction-bindings.md -- P1, approved, not started
25. agent/plans/PLAN-plan-preflight.md -- P1, approved, not started
26. agent/plans/PLAN-locale-techdiff-resync.md -- P2, ready, not started
27. agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- P3, proposed, not started
28. agent/plans/PLAN-ci-watch-enforcement.md -- P3, draft, not started
29. agent/plans/PLAN-cloudflare-proxy.md -- P3, proposed, not started
30. agent/plans/PLAN-plan-verbs.md -- P3, draft, not started
31. agent/plans/PLAN-renet-fetch-hardening.md -- P3, draft, not started
32. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, proposed, not started

### Not queued

- agent/plans/PLAN-fast-loop.md -- all boxes ticked: close it
- agent/plans/PLAN-github-pr-review-restore.md -- all boxes ticked: close it
- agent/plans/PLAN-prepush-full-cpu.md -- all boxes ticked: close it
- agent/plans/PLAN-program-state-in-repo.md -- all boxes ticked: close it
- agent/plans/PLAN-rdc-readonly-mode.md -- all boxes ticked: close it
- agent/plans/PLAN-repair-prose-style-findings.md -- all boxes ticked: close it
- agent/plans/PLAN-stop-hook-focus-mode.md -- all boxes ticked: close it
- agent/plans/PLAN-stop-hook-retro-20260925.md -- all boxes ticked: close it
- agent/plans/PLAN-stop-hook-turbo.md -- all boxes ticked: close it
- agent/plans/PLAN-typecheck-orphan-packages.md -- all boxes ticked: close it
<!-- queue:generated:end -->

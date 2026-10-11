# Plan queue

The ordered queue of plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). <!-- scope: pr.one-plan-per-pr -->One plan per PR by default; <!-- scope: pr.turbo-batch-end -->with `turbo: on` in `## Settings` the live PR keeps taking queued plans (agent/plans/PLAN-stop-hook-turbo.md), and with `turbo_push: batch-end` (the default) that batch is built and verified locally, then pushed once with one PR when it completes (agent/plans/PLAN-turbo-local-first.md); before then a push needs a `TURBO_PUSH_REASON` that `block_turbo_early_push` admits, and a `backup_push_h` backup push opens no PR. The first entry is the plan the live `MMDD-N` branch works: `.claude/hooks/post-bash/refresh_pr_body.py` writes it as the PR body's `Plan:` line once, and `rediacc_hooks.plan_gate.plan_merge_refusal` refuses the merge while that plan has an open box, unless the body carries an `Operational-Reason:` line.

Two lists, read in this order. `## Promoted` is hand-ordered by the operator and wins; no tool writes its entries, and an entry leaves it by hand when its PR merges. `## Generated` is rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` from live tracked plans with at least one open box: prerequisites first (`Depends-On:`, task refs and sub-plans like `PLAN-x.A0.md`, each prerequisite pulled ahead to the rank of what needs it), then held plans after unheld ones, prerequisites excepted, then in-progress plans before not-started ones, then operator Priority, AI Priority and path. Plans with no open box are listed under `### Not queued` with the reason, never as entries. Regenerate with `npm run check:ci-plan-record -- --update`; the same gate fails while the section is stale.

`## In flight`, between `## Settings` and `## Promoted`, says what the loop is working on now: the effective switches, every active focus, the live branch and its PR, each plan in the PR's plan set with its box progress and how it joined (the `Plan:` line, a turbo batch claim, an `Operational-Reason:` addition, a prerequisite), the branch's epics outside that set, live writers, leased items, and the next plan with its reason. The Stop hook and the `--queue-set` and `--focus` verbs render it between its markers from runtime state; no gate compares it, and no number in it is a list entry.

The progress block directly under `## Promoted` is generated, between the `queue:progress` markers: an overall line (plans done, boxes done, percentage) and one row per entry, keyed by the entry's own number, with its done/total box ratio. The counts come from the plan files by the merge gate's rule (`rediacc_hooks.plan_gate.open_boxes`, a `Moved-To:` stub followed), which check:ci-plan-boxes holds equal to `.ci/config/plan-boxes.json`. The Stop hook re-renders it on every run, as do `--queue-set`, `--focus` and the plan verbs (`--plan-tick`, `--plan-investigate`, `--plan-compact`, `--plan-revive`); `npm run check:ci-plan-record` fails while it disagrees with the plans, and `npm run check:ci-plan-record -- --update` rewrites it. Edit the entries below the block, never the block.

Entry format: `1. agent/plans/PLAN-<slug>.md`, optionally followed by ` -- <note>`. Only numbered entries inside the two sections are read; the progress block holds table rows, never entries.

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
- `turbo_push` (batch-end): under turbo, when the push and the PR happen. `batch-end` verifies the batch locally and pushes once when it completes, so the branch has no PR and no CI run until then. `pr` keeps the earlier behaviour: the PR opens at the first push and the batch joins it.
- `backup_push_h` (4): under `turbo_push: batch-end`, the age in hours of the oldest unpushed commit that makes the hook advise a backup push (`git push -u origin <branch>`, no PR, so no CI run). `0` turns the advice off.

A ` -- solo` note on a Promoted entry keeps that plan alone in its PR under turbo.

```stop-hook
stop_hook: off -- operator order 2026-10-11: "let's disable the stop hook for now and wait/complete the remaining sub-agents. pause pr-babysit for now as well."
turbo: off -- operator 2026-10-08: "let's disable turbo mode"
batch_size: 3 -- operator 2026-10-04: go in parallel as much as possible
plan_concurrency: 5 -- operator 2026-10-04: plan limit 5
writer_cap: 15 -- operator 2026-10-04: parallel limit 15
cadence: on
agent_hint: on
agent_pushback: on
judge: on
commit_remind_min: 15 -- operator 2026-10-06: PLAN-fast-loop Part 2 default
turbo_push: batch-end -- operator 2026-10-08: turbo completes plans locally, one push per batch
backup_push_h: 4 -- operator 2026-10-08: backup push valve, no PR
```

## In flight

What the loop is working on now, rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` (`refresh_inflight`) on every stop and on every `worklist.py --queue-set` or `--focus`. It is runtime state: rewritten only when it changes, never compared by `npm run check:ci-plan-record`, and a committed copy is a snapshot from its commit.

<!-- queue:inflight:begin -->
- Mode: stop_hook off; turbo off; turbo_push batch-end; batch_size 3; plan_concurrency 5; writer_cap 15; commit_remind_min 15; backup_push_h 4; cadence on; agent_hint on; agent_pushback on; judge on.
- Focus: off.
- Branch: 1008-1, no PR yet.
- Plans on the PR: none yet. The push that opens this branch's PR writes the queue head, agent/plans/PLAN-retire-bash-oracles.md, as its `Plan:` line unless the body names a plan first.
- Work outside the PR's plans (1 epic(s)):
  - epic 8ed364fe, plan agent/plans/PLAN-ci-consolidation.md, outside the set, 324 commit(s) on the branch, 0 open item(s): One registration verb, one freshness registry, one hook gh layer (PLAN-ci-consolidation)
- Writers: 1 live of writer_cap 15 (session d778be9d): worker:ad0f9f274a269c9cb.
- Leased items: 5: #05829121 (worker:ae5d3f07fbbb5a00c, d778be9d), #0c331972 (worker:ad0f9f274a269c9cb, d778be9d), #175470e9 (worker:a12e30f01457bf831, d778be9d), #20a3802a (worker:ad0f9f274a269c9cb, d778be9d), #9fb36ce4 (worker:a239d663cd52c1bfb, d778be9d).
- Next plan: agent/plans/PLAN-deferred-findings-block-merge.md, Promoted entry 2; starts after this branch's PR merges.
<!-- queue:inflight:end -->

## Promoted

<!-- queue:progress:begin -->
Promoted: 6 of 13 plans done, 141 of 170 boxes done (82%).

| # | Plan | Boxes done | State |
|---|---|---|---|
| 1 | PLAN-retire-bash-oracles.md | 15/15 | done |
| 2 | PLAN-deferred-findings-block-merge.md | 16/17 | 1 open |
| 3 | PLAN-ci-consolidation.md | 22/22 | done |
| 4 | PLAN-config-team-scoping.md | 10/11 | 1 open |
| 5 | PLAN-plan-dependencies.md | 12/12 | done |
| 6 | PLAN-remove-cross-session-messaging.md | 0/13 | 13 open |
| 7 | PLAN-config-passkey-optional.md | 3/4 | 1 open |
| 8 | PLAN-plan-per-pr-loop.md | 15/16 | 1 open |
| 9 | PLAN-stop-hook-retro-20260924.md | 23/23 | done |
| 10 | PLAN-cd-errors-in-ci.md | 5/6 | 1 open |
| 11 | PLAN-scope-mirrors.md | 11/11 | done |
| 12 | PLAN-lessons-registry.md | 9/9 | done |
| 13 | PLAN-inline-suppressions.md | 0/11 | 11 open |
<!-- queue:progress:end -->

1. agent/plans/PLAN-retire-bash-oracles.md -- operator 2026-10-08 ("move them to the head of promoted and complete"): this PR's plan; W11-B and its integration in flight
2. agent/plans/PLAN-deferred-findings-block-merge.md -- operator 2026-10-08 ("move them to the head of promoted and complete"): this PR's plan; M3 waits on Quality / Branch on the pushed head
3. agent/plans/PLAN-ci-consolidation.md -- operator /ask 2026-10-04: "Next (pos 2)"; candidates 1, 3, 4, 6, 7 of agent/reports/consolidation-investigation-2026-10-04.md in one plan, one PR -- solo
4. agent/plans/PLAN-config-team-scoping.md -- operator /ask 2026-10-03: T9 (the enforced matrix in DESIGN-CONFIG-STORAGE.md) and T10 (live smoke)
5. agent/plans/PLAN-plan-dependencies.md -- operator /ask 2026-10-03: the 9 open boxes
6. agent/plans/PLAN-remove-cross-session-messaging.md -- operator /ask 2026-10-03: Step 12
7. agent/plans/PLAN-config-passkey-optional.md -- operator 2026-10-08 melt-the-list: ALMOST-FINISHED, 1 of 4 boxes open, T4 pre-deploy production query then eu deploy and Bitwarden walk-through (unblocks the org-selection chain)
8. agent/plans/PLAN-plan-per-pr-loop.md -- operator 2026-10-08 melt-the-list: ALMOST-FINISHED, 1 of 16 boxes open, R1 root-cause the nightly Console CI failure on main (PLAN-ci-verdict is done, so ci-trace works)
9. agent/plans/PLAN-stop-hook-retro-20260924.md -- operator 2026-10-08 melt-the-list: ALMOST-FINISHED, 1 of 23 boxes open, R20260924.15 re-count the seven frictions on .blocklog and record before/after in Status
10. agent/plans/PLAN-cd-errors-in-ci.md -- operator 2026-10-08: catch CD errors at CI level; W1 is the housekeeping root fix due before the 03:00Z run
11. agent/plans/PLAN-scope-mirrors.md -- operator /ask 2026-10-04 (#e70faed1): queued after the Promoted entries; eight live drifts F1-F8 predicted
12. agent/plans/PLAN-lessons-registry.md -- operator /ask 2026-10-04 (#077d85c1): extends TRAPS.md and check:ci-trap-registry with content-checked Documented-In anchors
13. agent/plans/PLAN-inline-suppressions.md -- operator /ask 2026-10-08T10:48Z (#575d2992): ban inline lint/type suppressions; fix in code, deliberate patterns to linter config with BLOCKER reasons

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-app-wide-org-selection.md -- P0, approved, in progress (2 of 3 boxes ticked), dep-blocked
2. agent/plans/PLAN-config-handoff-relay-only.md -- P0, draft, in progress (9 of 11 boxes ticked), dep-blocked
3. agent/plans/PLAN-token-ip-rebind.md -- P0, draft, in progress (9 of 10 boxes ticked), dep-blocked
4. agent/plans/PLAN-config-sync-hardening.md -- P0, draft, in progress (18 of 19 boxes ticked), dep-blocked
5. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
6. agent/plans/PLAN-k3s-137-and-pr-conditions.md -- P1, approved, in progress (4 of 5 boxes ticked)
7. agent/plans/PLAN-secret-namespace-migration.md -- P1, executing, in progress (29 of 34 boxes ticked)
8. agent/plans/PLAN-stop-hook-one-plan-scope.md -- P1, approved, in progress (14 of 15 boxes ticked)
9. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, executing, in progress (16 of 17 boxes ticked)
10. agent/plans/PLAN-tooling-transformation.md -- P1, ready, in progress (152 of 154 boxes ticked)
11. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked), dep-blocked
12. agent/plans/PLAN-w7p5a-real-run-dispatch.md -- P1, in-progress, in progress (7 of 9 boxes ticked)
13. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, in progress (2 of 5 boxes ticked)
14. agent/plans/PLAN-biome-only-lint.md -- P3, draft, in progress (10 of 29 boxes ticked)
15. agent/plans/PLAN-stop-hook-rulings-campaign.md -- P3, draft, in progress (1 of 17 boxes ticked)
16. agent/plans/PLAN-deletion-budget.md -- P3 (operator), draft, not started
17. agent/plans/PLAN-config-networkid-sync.md -- P1, draft, not started, dep-blocked
18. agent/plans/PLAN-plan-compaction-bindings.md -- P1, approved, not started
19. agent/plans/PLAN-plan-preflight.md -- P1, approved, not started
20. agent/plans/PLAN-retire-bash-oracles.A0.md -- P2, executing, not started
21. agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- P3, proposed, not started
22. agent/plans/PLAN-ci-watch-enforcement.md -- P3, draft, not started
23. agent/plans/PLAN-cloudflare-proxy.md -- P3, proposed, not started
24. agent/plans/PLAN-lessons-registry-followups.md -- P3, draft, not started
25. agent/plans/PLAN-plan-verbs.md -- P3, draft, not started
26. agent/plans/PLAN-renet-fetch-hardening.md -- P3, draft, not started
27. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, proposed, not started

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

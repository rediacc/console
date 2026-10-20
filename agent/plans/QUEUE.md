# Plan queue

The ordered queue of plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). <!-- scope: pr.one-plan-per-pr -->One plan per PR by default; <!-- scope: pr.turbo-batch-end -->with `turbo: on` in `## Settings` the live PR keeps taking queued plans (agent/plans/PLAN-stop-hook-turbo.md), and with `turbo_push: batch-end` (the default) that batch is built and verified locally, then pushed once with one PR when it completes (agent/plans/PLAN-turbo-local-first.md); before then a push needs a `TURBO_PUSH_REASON` that `block_turbo_early_push` admits, and a `backup_push_h` backup push opens no PR. The first entry is the plan the live `MMDD-N` branch works: `.claude/hooks/post-bash/refresh_pr_body.py` writes it as the PR body's `Plan:` line once, and `rediacc_hooks.plan_gate.plan_merge_refusal` refuses the merge while that plan has an open box, unless the body carries an `Operational-Reason:` line.

Two lists, read in this order. `## Promoted` is hand-ordered by the operator and wins; no tool writes its entries, and an entry leaves it by hand when its PR merges. `## Generated` is rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` from live tracked plans with at least one open box: prerequisites first (`Depends-On:`, task refs and sub-plans like `PLAN-x.A0.md`, each prerequisite pulled ahead to the rank of what needs it), then held plans after unheld ones, prerequisites excepted, then in-progress plans before not-started ones, then operator Priority, AI Priority and path. Plans with no open box are listed under `### Not queued` with the reason, never as entries. Regenerate with `npm run check:ci-plan-record -- --update`; the same gate fails while the section is stale.

`## In flight`, between `## Settings` and `## Promoted`, says what the loop is working on now: the effective switches, every session's wind-down phase, the live branch and its PR, each plan in the PR's plan set with its box progress and how it joined (the `Plan:` line, a turbo batch claim, an `Operational-Reason:` addition, a prerequisite), the branch's epics outside that set, live writers, leased items, and the next plan with its reason. The Stop hook and the `--queue-set` and `--phase` verbs render it between its markers from runtime state; no gate compares it, and no number in it is a list entry.

The progress block directly under `## Promoted` is generated, between the `queue:progress` markers: an overall line (plans done, boxes done, percentage) and one row per entry, keyed by the entry's own number, with its done/total box ratio. The counts come from the plan files by the merge gate's rule (`rediacc_hooks.plan_gate.open_boxes`, a `Moved-To:` stub followed), which check:ci-plan-boxes holds equal to `.ci/config/plan-boxes.json`. The Stop hook re-renders it on every run, as do `--queue-set`, `--phase` and the plan verbs (`--plan-tick`, `--plan-investigate`, `--plan-compact`, `--plan-revive`); `npm run check:ci-plan-record` fails while it disagrees with the plans, and `npm run check:ci-plan-record -- --update` rewrites it. Edit the entries below the block, never the block.

Entry format: `1. agent/plans/PLAN-<slug>.md`, optionally followed by ` -- <note>`. Only numbered entries inside the two sections are read; the progress block holds table rows, never entries.

## Settings

The switchboard for the Stop hook, read by `.claude/hooks/stop/wl_planqueue.py` (`settings`). One fenced block, `key: value` per line, an optional ` -- <note>` carrying the operator's reason. It names one `effort` level (agent/plans/PLAN-stop-hook-effort.md); every other value resolves as that level's bundle in `.claude/config/effort.json`, then an explicit line here, which wins. A missing or bad `effort:` line is `high`, every check as before the dial existed, and any other bad line falls back to the level's value; `npm run check:ci-plan-record` names the problem. Change it with `worklist.py --queue-set <me> key=value ... [--note "<text>"]` (`key=` drops an override), then commit this file.

The levels, each a superset of the one before:

- `quiet`: the FLOOR only (`.claude/hooks/stop/wl_floor.py`: the hook cannot see, a broken watch, CI red or unreadable, a dead or over-cap writer, an unread report, a wait with no wake-up timer, STATE.md when compaction is due). No judge. There is no off switch; this is the quietest the hook gets.
- `low`: plus the mission: open items, the PR's plan, its finish line, its reviews, the turbo and loop orders.
- `smart`: plus owed work and record integrity; `no-remaining` and `out-of-sync` only advise; the judge runs without riders.
- `high`: every check, the full judge with its riders.
- `ultra`: `high` plus the throughput bundle (turbo on, writer_cap 15, plan_concurrency 5, batch_size 3).

`.claude/config/effort.json` gives every check its threshold (`{"block": <level>, "advise": <level>}`, or `floor`); moving a check between levels is an edit there, which the effort-table rule of `npm run check:ci-plan-record` keeps complete.

The overrides (each level's bundle value in brackets for `high`):

- `turbo` (off): `off` keeps one plan per PR. `on` hands each free writer slot the next eligible queued plan, which joins the live PR's `Plan:` line, and keeps going until turbo is switched off.
- `turbo_push` (batch-end): under turbo, when the push and the PR happen. `batch-end` verifies the batch locally and pushes once when it completes, so the branch has no PR and no CI run until then. `pr` keeps the earlier behaviour: the PR opens at the first push and the batch joins it.
- `batch_size` (1): under turbo, the minimum number of finished plans before the PR is offered for merge. The merge itself never refuses a shorter PR.
- `plan_concurrency` (1): under turbo, the most unfinished plans in flight at once. The PR's own unfinished plans and the plans live writers serve count against it, so a free writer slot opens a new plan only below this ceiling.
- `writer_cap` (4): the most writer agents live at once. A spawn beyond it is refused (`block_agent_cap`), and the Stop hook blocks on a roster above it.
- `commit_remind_min` (15): minutes without a commit, while this session's own edits are still uncommitted, before the Stop hook and the post-tool hook remind it to commit the verified unit. A reminder, never a block (agent/plans/PLAN-fast-loop.md Part 2).
- `backup_push_h` (4): under `turbo_push: batch-end`, the age in hours of the oldest unpushed commit that makes the hook advise a backup push (`git push -u origin <branch>`, no PR, so no CI run). `0` turns the advice off.
- `judge` (full): `off`, `core` (the LLM judge answers whether stopping is honest, with no regression sweep, proof, deferral audit, settle or admission riders) or `full`. The env var `WORKLIST_JUDGE=on|off` overrides it, for tests.
- `cadence`, `agent_hint`, `agent_pushback` (on): not fence keys of their own any more; the level decides them, and a line here still overrides. `cadence` lets a stop through after a demand when the session has reported something new; `agent_hint` names a specialist agent that matches the open work; `agent_pushback` blocks a stop that declares work out of reach and names the agent that fits.

A ` -- solo` note on a Promoted entry keeps that plan alone in its PR under turbo.

```stop-hook
effort: smart -- operator 2026-10-18: "let's make effort mode smart", agent/plans/PLAN-stop-hook-effort.md
turbo: on
batch_size: 3 -- operator 2026-10-04: go in parallel as much as possible
plan_concurrency: 5 -- operator 2026-10-04: plan limit 5
writer_cap: 15 -- operator 2026-10-04: parallel limit 15
commit_remind_min: 15 -- operator 2026-10-06: PLAN-fast-loop Part 2 default
turbo_push: batch-end -- operator 2026-10-08: turbo completes plans locally, one push per batch
backup_push_h: 4 -- operator 2026-10-08: backup push valve, no PR
```

## In flight

What the loop is working on now, rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` (`refresh_inflight`) on every stop and on every `worklist.py --queue-set` or `--phase`. It is runtime state: rewritten only when it changes, never compared by `npm run check:ci-plan-record`, and a committed copy is a snapshot from its commit.

<!-- queue:inflight:begin -->
- Mode: effort smart; turbo on; turbo_push batch-end; batch_size 3; plan_concurrency 5; writer_cap 15; commit_remind_min 15; backup_push_h 4; judge core; cadence on; agent_hint on; agent_pushback on.
- Phase: build.
- Branch: 1020-1, no PR yet.
- Plans on the PR (6):
  - agent/plans/PLAN-retire-bash-oracles.md -- 15 of 15 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-remove-cross-session-messaging.md -- 12 of 13 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-plan-per-pr-loop.md -- 15 of 16 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- 0 of 11 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-pins-command.md -- 12 of 13 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-backup-credential-isolation.md -- 7 of 8 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
- Work outside the PR's plans (1 epic(s)):
  - epic 8ed364fe, plan agent/plans/PLAN-ci-consolidation.md, outside the set, 41 commit(s) on the branch, 0 open item(s): One registration verb, one freshness registry, one hook gh layer (PLAN-ci-consolidation)
- Writers: 6 live of writer_cap 15 (session d778be9d): worker:a84e0105023eb3558, worker:ae9f6781138196fbd, worker:abe636d17a3124f33, worker:a7330bc6bd3369b74, worker:a8955422005420c12, worker:ade133c29ebccde78.
- Leased items: 9: #010ab22b (worker:a8955422005420c12, d778be9d), #0781a2a6 (worker:a7330bc6bd3369b74, d778be9d), #3929065f (worker:ade133c29ebccde78, d778be9d), #6efff24c (worker:abe636d17a3124f33, d778be9d), #95980422 (worker:a84e0105023eb3558, d778be9d), #b8eab778 (worker:a84e0105023eb3558, d778be9d), #beabcb8a (worker:ae9f6781138196fbd, d778be9d), #e8a7de6d (worker:abe636d17a3124f33, d778be9d), #f70e2876 (worker:ae9f6781138196fbd, d778be9d).
- Next plan: agent/plans/PLAN-vm-check.md, Generated entry 13 (no Promoted entry ahead of it has an open box); starts after this branch's PR merges.
<!-- queue:inflight:end -->

## Promoted

<!-- queue:progress:begin -->
Promoted: 13 of 17 plans done, 200 of 204 boxes done (98%).

| # | Plan | Boxes done | State |
|---|---|---|---|
| 1 | PLAN-retire-bash-oracles.md | 15/15 | done |
| 2 | PLAN-deferred-findings-block-merge.md | 17/17 | done |
| 3 | PLAN-ci-consolidation.md | 22/22 | done |
| 4 | PLAN-config-team-scoping.md | 11/11 | done |
| 5 | PLAN-plan-dependencies.md | 12/12 | done |
| 6 | PLAN-remove-cross-session-messaging.md | 12/13 | 1 open |
| 7 | PLAN-config-passkey-optional.md | 4/4 | done |
| 8 | PLAN-plan-per-pr-loop.md | 15/16 | 1 open |
| 9 | PLAN-stop-hook-retro-20260924.md | 23/23 | done |
| 10 | PLAN-cd-errors-in-ci.md | 6/6 | done |
| 11 | PLAN-scope-mirrors.md | 11/11 | done |
| 12 | PLAN-lessons-registry.md | 9/9 | done |
| 13 | PLAN-inline-suppressions.md | 11/11 | done |
| 14 | PLAN-stop-hook-effort.md | 7/7 | done |
| 15 | PLAN-stop-hook-effort-tuning.md | 7/7 | done |
| 16 | PLAN-pins-command.md | 12/13 | 1 open |
| 17 | PLAN-account-vm-check.md | 6/7 | 1 open |
<!-- queue:progress:end -->

1. agent/plans/PLAN-retire-bash-oracles.md -- operator 2026-10-08 ("move them to the head of promoted and complete"): this PR's plan; done, 15 of 15 boxes; leaves this list when PR #600 merges
2. agent/plans/PLAN-deferred-findings-block-merge.md -- operator 2026-10-08 ("move them to the head of promoted and complete"): this PR's plan; done, 17 of 17 boxes (M3 closed on PR #600 run 38451759370); leaves this list when PR #600 merges
3. agent/plans/PLAN-ci-consolidation.md -- operator /ask 2026-10-04: "Next (pos 2)"; done, 22 of 22 boxes; leaves this list when PR #600 merges -- solo
4. agent/plans/PLAN-config-team-scoping.md -- operator /ask 2026-10-03: done, 11 of 11 boxes (T10 closed on the bench smoke of 2026-10-13 and PR #600 run 38451759370); leaves this list when PR #600 merges
5. agent/plans/PLAN-plan-dependencies.md -- operator /ask 2026-10-03: done, 12 of 12 boxes; leaves this list when PR #600 merges
6. agent/plans/PLAN-remove-cross-session-messaging.md -- operator /ask 2026-10-03: 4 open, Step 9 (full hook suite), Step 10 (registries), the --poll box of Step 12 through the plan verbs, Step 13 (ci:quick and the live Stop check)
7. agent/plans/PLAN-config-passkey-optional.md -- operator 2026-10-08 melt-the-list: done, 4 of 4 boxes (T4 closed on CI spec 20-12 against the real Bitwarden extension, green on a hosted runner in PR #600 run 38451759370); leaves this list when PR #600 merges
8. agent/plans/PLAN-plan-per-pr-loop.md -- operator 2026-10-08 melt-the-list: 1 open, R1; the nightly red on main is root-caused (the plan_housekeeping selftest's fixed date, fixed by 2031437e7 on this branch) and R1 closes on a green scheduled run after the merge
9. agent/plans/PLAN-stop-hook-retro-20260924.md -- operator 2026-10-08 melt-the-list: done, 23 of 23 boxes; leaves this list when PR #600 merges
10. agent/plans/PLAN-cd-errors-in-ci.md -- operator 2026-10-08: catch CD errors at CI level; done, 6 of 6 boxes (the 10-07 replay is green in Quality / Pytest (1/3) of PR #600 run 38451759370); leaves this list when PR #600 merges
11. agent/plans/PLAN-scope-mirrors.md -- operator /ask 2026-10-04 (#e70faed1): done, 11 of 11 boxes; leaves this list when PR #600 merges
12. agent/plans/PLAN-lessons-registry.md -- operator /ask 2026-10-04 (#077d85c1): done, 9 of 9 boxes; leaves this list when PR #600 merges
13. agent/plans/PLAN-inline-suppressions.md -- operator /ask 2026-10-08T10:48Z (#575d2992): ban inline lint/type suppressions; 3 of 11 boxes ticked (WC1 e2e, WC2 account, WD1 renet); WD2 waits on run_renet.py validating BLOCKER comments; the config and sweep patches (P0), the .claude and .ci Python patches (WA, WB) and the shell markers are delivered and not yet landed; P2 and F follow them
14. agent/plans/PLAN-stop-hook-effort.md -- operator /ask 2026-10-14 (#d5506fb8): one effort level (quiet/low/smart/high/ultra) replaces the stop_hook, focus and turbo switches, with check thresholds in .claude/config/effort.json; "implement PLAN-stop-hook-effort.md now"; 0 of 7 boxes, writer on E1-E6
15. agent/plans/PLAN-stop-hook-effort-tuning.md -- operator 2026-10-14 (asked to plan it and then ask the implementation questions; /ask: tuner runs near compaction at about 85% through a sub-agent, demotions by one batched /ask, work = a commit or tick within 3 stops, promotions auto-apply): the effort table tunes itself from measured outcomes; depends on entry 14; 0 of 7 boxes
16. agent/plans/PLAN-pins-command.md -- operator 2026-10-14 (asked to extend the dependency tool so future sessions skip manual steps; /ask: "Approve, this PR", daily job artifact only, unwatched pins red at once, check:deps --upgrade deleted): one pin registry and one `npm run pins` command bump every pinned version, and every freshness gate names it; 0 of 13 boxes
17. agent/plans/PLAN-account-vm-check.md -- operator /ask 2026-10-15 (#c5305ed9: "Account drills via one runner", "Widen to deployed renet code"; on return "You can continue for the rest."): one vm:check runner, receipt and push guard prove renet, the CLI remote paths and private/account before a push; wave 1 (AV1-AV3) is written as patches now and lands with AV4/AV5 after PR #600 merges, since a schema-2 receipt alone would refuse every push; 0 of 7 boxes <!-- style-ok -->

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-app-wide-org-selection.md -- P0, approved, in progress (2 of 3 boxes ticked)
2. agent/plans/PLAN-config-handoff-relay-only.md -- P0, draft, in progress (9 of 11 boxes ticked), dep-blocked
3. agent/plans/PLAN-token-ip-rebind.md -- P0, draft, in progress (9 of 10 boxes ticked), dep-blocked
4. agent/plans/PLAN-config-sync-hardening.md -- P0, draft, in progress (18 of 19 boxes ticked), dep-blocked
5. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
6. agent/plans/PLAN-secret-namespace-migration.md -- P1, executing, in progress (29 of 34 boxes ticked)
7. agent/plans/PLAN-shell-sandbox-readonly-view.md -- P1, active, in progress (4 of 7 boxes ticked)
8. agent/plans/PLAN-stop-hook-one-plan-scope.md -- P1, approved, in progress (14 of 15 boxes ticked)
9. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, executing, in progress (16 of 17 boxes ticked)
10. agent/plans/PLAN-tooling-transformation.md -- P1, ready, in progress (153 of 154 boxes ticked)
11. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked), dep-blocked
12. agent/plans/PLAN-vm-check.md -- P1, approved, in progress (5 of 8 boxes ticked)
13. agent/plans/PLAN-w7p5a-real-run-dispatch.md -- P1, in-progress, in progress (7 of 9 boxes ticked)
14. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, in progress (2 of 5 boxes ticked)
15. agent/plans/PLAN-pin-awscli-toolchain-python-compatible.md -- P2, executing, in progress (6 of 7 boxes ticked)
16. agent/plans/PLAN-stop-hook-rulings-campaign.md -- P3, draft, in progress (3 of 17 boxes ticked)
17. agent/plans/PLAN-deletion-budget.md -- P3 (operator), draft, not started
18. agent/plans/PLAN-backup-program.md -- P1, approved, not started, dep-blocked
19. agent/plans/PLAN-config-networkid-sync.md -- P1, draft, not started, dep-blocked
20. agent/plans/PLAN-plan-compaction-bindings.md -- P1, approved, not started
21. agent/plans/PLAN-plan-preflight.md -- P1, approved, not started
22. agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- P3, proposed, not started
23. agent/plans/PLAN-ci-watch-enforcement.md -- P3, draft, not started
24. agent/plans/PLAN-cloudflare-proxy.md -- P3, proposed, not started
25. agent/plans/PLAN-lessons-registry-followups.md -- P3, draft, not started
26. agent/plans/PLAN-plan-verbs.md -- P3, draft, not started
27. agent/plans/PLAN-renet-fetch-hardening.md -- P3, draft, not started
28. agent/plans/PLAN-retire-bash-oracles.A0.md -- P3, executing, not started
29. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, proposed, not started

### Not queued

- agent/plans/PLAN-backup-credential-isolation.md -- all boxes ticked: close it
<!-- queue:generated:end -->

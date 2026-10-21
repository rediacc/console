# Plan queue

The ordered queue of plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). <!-- scope: pr.one-plan-per-pr -->One plan per PR by default; <!-- scope: pr.turbo-batch-end -->with `turbo: on` in `## Settings` the live PR keeps taking queued plans (agent/plans/PLAN-stop-hook-turbo.md), and with `turbo_push: batch-end` (the default) that batch is built and verified locally, then pushed once with one PR when it completes (agent/plans/PLAN-turbo-local-first.md); before then a push needs a `TURBO_PUSH_REASON` that `block_turbo_early_push` admits, and a `backup_push_h` backup push opens no PR. The first entry is the plan the live `MMDD-N` branch works: `.claude/hooks/post-bash/refresh_pr_body.py` writes it as the PR body's `Plan:` line once, and `rediacc_hooks.plan_gate.plan_merge_refusal` refuses the merge while that plan has an open box, unless the body carries an `Operational-Reason:` line.

Two lists, read in this order. `## Promoted` is hand-ordered by the operator and wins; no tool adds, reorders or edits its entries; an entry leaves when its plan moves (`check_plan_folders.py --move` retires it, and check:ci-plan-record RQ-MOVED refuses an entry that points at a moved stub). `## Generated` is rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` from live tracked plans with at least one open box: prerequisites first (`Depends-On:`, task refs and sub-plans like `PLAN-x.A0.md`, each prerequisite pulled ahead to the rank of what needs it), then held plans after unheld ones, prerequisites excepted, then in-progress plans before not-started ones, then operator Priority, AI Priority and path. Plans with no open box are listed under `### Not queued` with the reason, never as entries. Regenerate with `npm run check:ci-plan-record -- --update`; the same gate fails while the section is stale.

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
effort: low -- operator 2026-10-20: "let's make effort low", agent/plans/PLAN-stop-hook-effort.md
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
- Mode: effort low; turbo on; turbo_push batch-end; batch_size 3; plan_concurrency 5; writer_cap 15; commit_remind_min 15; backup_push_h 4; judge off; cadence on; agent_hint off; agent_pushback off.
- Phase: build.
- Branch: 1020-1, PR #601 open.
- Plans on the PR (12):
  - agent/plans/_done/PLAN-vm-check.md -- 8 of 8 boxes ticked, the PR body's `Plan:` line
  - agent/plans/_done/PLAN-account-vm-check.md -- 7 of 7 boxes ticked, added to the `Plan:` line under `Operational-Reason:`
  - agent/plans/_done/PLAN-tooling-transformation.md -- 154 of 154 boxes ticked, added to the `Plan:` line under `Operational-Reason:`
  - agent/plans/_done/PLAN-backup-credential-isolation.md -- 8 of 8 boxes ticked, a turbo batch claim on the `Plan:` line
  - agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- 11 of 11 boxes ticked, a turbo batch claim on the `Plan:` line
  - agent/plans/PLAN-shell-sandbox-readonly-view.md -- 6 of 7 boxes ticked, a turbo batch claim on the `Plan:` line
  - agent/plans/PLAN-pins-command.md -- 12 of 13 boxes ticked, a turbo batch claim on the `Plan:` line
  - agent/plans/PLAN-pin-awscli-toolchain-python-compatible.md -- 6 of 7 boxes ticked, added to the `Plan:` line under `Operational-Reason:`
  - agent/plans/PLAN-remove-cross-session-messaging.md -- 13 of 13 boxes ticked, added to the `Plan:` line under `Operational-Reason:`
  - agent/plans/PLAN-plan-per-pr-loop.md -- 15 of 16 boxes ticked, a turbo batch claim on the `Plan:` line
  - agent/plans/_done/PLAN-remove-cross-session-messaging.md -- 13 of 13 boxes ticked, a turbo pick named by the Stop hook, joining the `Plan:` line on the next push
  - agent/plans/PLAN-backup-program.md -- 0 of 186 boxes ticked, a turbo pick named by the Stop hook, joining the `Plan:` line on the next push
- Work outside the PR's plans (1 epic(s)):
  - epic 8ed364fe, plan agent/plans/PLAN-ci-consolidation.md, outside the set, 232 commit(s) on the branch, 0 open item(s): One registration verb, one freshness registry, one hook gh layer (PLAN-ci-consolidation)
- Writers: 1 live of writer_cap 15 (session d778be9d): worker:a5894c1f60a6f829c.
- Leased items: 2: #1a07399b (worker:a0e5991d10870b076, d778be9d), #86b5992c (worker:a5894c1f60a6f829c, d778be9d).
- Next plan: agent/plans/PLAN-backup-program.md, Promoted entry 4; a turbo pick joins this PR when a writer slot frees under plan_concurrency 5.
<!-- queue:inflight:end -->

## Promoted

<!-- queue:progress:begin -->
Promoted: 0 of 5 plans done, 33 of 230 boxes done (14%).

| # | Plan | Boxes done | State |
|---|---|---|---|
| 1 | PLAN-plan-per-pr-loop.md | 15/16 | 1 open |
| 2 | PLAN-pins-command.md | 12/13 | 1 open |
| 3 | PLAN-shell-sandbox-readonly-view.md | 6/7 | 1 open |
| 4 | PLAN-e2e-browse-at-ci.md | 0/8 | 8 open |
| 5 | PLAN-backup-program.md | 0/186 | 186 open |
<!-- queue:progress:end -->

1. agent/plans/PLAN-plan-per-pr-loop.md -- operator 2026-10-08 melt-the-list: last box is R1; the nightly red on main is root-caused (the plan_housekeeping selftest's fixed date, fixed by 2031437e7 on this branch) and R1 closes on a green scheduled run after the merge
2. agent/plans/PLAN-pins-command.md -- operator 2026-10-14 (asked to extend the dependency tool so future sessions skip manual steps; /ask: "Approve, this PR", daily job artifact only, unwatched pins red at once, check:deps --upgrade deleted): one pin registry and one `npm run pins` command bump every pinned version, and every freshness gate names it
3. agent/plans/PLAN-shell-sandbox-readonly-view.md -- operator /ask 2026-10-20T15:14Z ("bring its deps to the promoted area to start them first"): prerequisite of entry 5 (PLAN-backup-program), beside PLAN-account-vm-check (done 2026-10-20); closes the cross-repo integrity hole where a repo key holder can re-mode or re-time another repo's files
4. agent/plans/PLAN-e2e-browse-at-ci.md -- finding fix on this PR (worklist #1a07399b, 2026-10-21): the browse-at e2e tier passes on the local fleet but no workflow runs it; findings are fixed in the session that finds them
5. agent/plans/PLAN-backup-program.md -- operator 2026-10-20 ("move agent/plans/PLAN-backup-program.md to the promoted"): one backup program across renet, account, CLI and shared, ending in a live hostinger to eu R2 backup; P1; Depends-On PLAN-shell-sandbox-readonly-view.md and PLAN-account-vm-check.md (done 2026-10-20); released to writers by operator /ask ASKED:2026-10-20T15:14Z ("edit writers to go NOW")

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-app-wide-org-selection.md -- P0, approved, in progress (2 of 3 boxes ticked)
2. agent/plans/PLAN-config-handoff-relay-only.md -- P0, draft, in progress (9 of 11 boxes ticked), dep-blocked
3. agent/plans/PLAN-token-ip-rebind.md -- P0, draft, in progress (9 of 10 boxes ticked), dep-blocked
4. agent/plans/PLAN-config-sync-hardening.md -- P0, draft, in progress (18 of 19 boxes ticked), dep-blocked
5. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked)
6. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
7. agent/plans/PLAN-secret-namespace-migration.md -- P1, executing, in progress (29 of 34 boxes ticked)
8. agent/plans/PLAN-stop-hook-one-plan-scope.md -- P1, approved, in progress (14 of 15 boxes ticked)
9. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, executing, in progress (16 of 17 boxes ticked)
10. agent/plans/PLAN-w7p5a-real-run-dispatch.md -- P1, in-progress, in progress (7 of 9 boxes ticked)
11. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, in progress (2 of 5 boxes ticked)
12. agent/plans/PLAN-pin-awscli-toolchain-python-compatible.md -- P2, executing, in progress (6 of 7 boxes ticked)
13. agent/plans/PLAN-stop-hook-rulings-campaign.md -- P3, draft, in progress (3 of 17 boxes ticked)
14. agent/plans/PLAN-deletion-budget.md -- P3 (operator), draft, not started
15. agent/plans/PLAN-config-networkid-sync.md -- P1, draft, not started, dep-blocked
16. agent/plans/PLAN-plan-compaction-bindings.md -- P1, approved, not started
17. agent/plans/PLAN-plan-preflight.md -- P1, approved, not started
18. agent/plans/PLAN-backup-toc-exact-opt-in.md -- P3, proposed, not started, dep-blocked
19. agent/plans/PLAN-ci-watch-enforcement.md -- P3, draft, not started
20. agent/plans/PLAN-cloudflare-proxy.md -- P3, proposed, not started
21. agent/plans/PLAN-lessons-registry-followups.md -- P3, draft, not started
22. agent/plans/PLAN-plan-verbs.md -- P3, draft, not started
23. agent/plans/PLAN-renet-fetch-hardening.md -- P3, draft, not started
24. agent/plans/PLAN-retire-bash-oracles.A0.md -- P3, executing, not started
25. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, proposed, not started

### Not queued

- agent/plans/PLAN-chunk-store-browse-toc-and-remote.md -- all boxes ticked: close it
<!-- queue:generated:end -->

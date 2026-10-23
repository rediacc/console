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
effort: ultra -- operator 2026-10-23: back from the Claude Code update ("You will switch to ultra when I come back from update")
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
- Mode: effort ultra; turbo on; turbo_push batch-end; batch_size 3; plan_concurrency 5; writer_cap 15; commit_remind_min 15; backup_push_h 4; judge full; cadence on; agent_hint on; agent_pushback on.
- Phase: build.
- Branch: 1023-1, no PR yet.
- Plans on the PR (6):
  - agent/plans/PLAN-plan-per-pr-loop.md -- 15 of 16 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/_done/PLAN-pins-command.md -- 13 of 13 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-w7p5a-real-run-dispatch.md -- 8 of 9 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-stop-hook-rulings-campaign.md -- 3 of 17 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-backup-program.md -- 2 of 190 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-agent-tree-lifecycle.md -- 6 of 7 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
- Work outside the PR's plans (4 epic(s)):
  - epic 6f81c19f, plan agent/plans/PLAN-hostinger-upgrade-followups.md, outside the set, 3 commit(s) on the branch, 0 open item(s): hostinger CVE-response product follow-ups: Traefik v3.7.16, template fixes, /run docker.sock write-up
  - epic e35e767c, plan agent/plans/PLAN-sync-remote-file-ownership.md, outside the set, 10 commit(s) on the branch, 0 open item(s): repo sync upload --remote-file creates parent directories owned by the universal user
  - epic ecc421f7, plan agent/plans/PLAN-telemetry-export.md, outside the set, 19 commit(s) on the branch, 0 open item(s): telemetry export: account Workers and the executor proxy deliver to otlp.rediacc.io per region and channel
  - epic 9ba16177, plan agent/plans/PLAN-renet-bridge-leftovers.md, outside the set, 5 commit(s) on the branch, 0 open item(s): renet bridge and middleware leftovers removed
- Writers: 1 live of writer_cap 15 (session d778be9d): worker:ad8b3c16dfa1551f1.
- Leased items: 3: #831b7e48 (worker:ad8b3c16dfa1551f1, d778be9d), #8cb01693 (worker:b8ufy6ku9, d778be9d), #99580994 (worker:ad8b3c16dfa1551f1, d778be9d).
- Next plan: agent/plans/PLAN-cloudflare-proxy.md, Promoted entry 3; starts after this branch's PR merges.
<!-- queue:inflight:end -->

## Promoted

<!-- queue:progress:begin -->
Promoted: 0 of 17 plans done, 117 of 370 boxes done (31%).

| # | Plan | Boxes done | State |
|---|---|---|---|
| 1 | PLAN-plan-per-pr-loop.md | 15/16 | 1 open |
| 2 | PLAN-backup-program.md | 2/190 | 188 open |
| 3 | PLAN-cloudflare-proxy.md | 18/29 | 11 open |
| 4 | PLAN-sync-remote-file-ownership.md | 5/6 | 1 open |
| 5 | PLAN-telemetry-export.md | 8/19 | 11 open |
| 6 | PLAN-renet-bridge-leftovers.md | 0/14 | 14 open |
| 7 | PLAN-token-ip-rebind.md | 9/10 | 1 open |
| 8 | PLAN-config-sync-hardening.md | 18/19 | 1 open |
| 9 | PLAN-stop-hook-one-plan-scope.md | 14/15 | 1 open |
| 10 | PLAN-w7p5a-real-run-dispatch.md | 8/9 | 1 open |
| 11 | PLAN-pin-awscli-toolchain-python-compatible.md | 6/7 | 1 open |
| 12 | PLAN-plan-preflight.md | 8/9 | 1 open |
| 13 | PLAN-renet-run-docker-sock-isolation.md | 0/3 | 3 open |
| 14 | PLAN-config-networkid-discovery.md | 0/7 | 7 open |
| 15 | PLAN-renet-fetch-retries.md | 0/2 | 2 open |
| 16 | PLAN-cloudflare-spend-guard.md | 0/8 | 8 open |
| 17 | PLAN-dockerd-api-privilege-gate.md | 6/7 | 1 open |
<!-- queue:progress:end -->

1. agent/plans/PLAN-plan-per-pr-loop.md -- operator 2026-10-08 melt-the-list: last box is R1; the nightly red on main is root-caused (the plan_housekeeping selftest's fixed date, fixed by 2031437e7 on this branch) and R1 closes on a green scheduled run after the merge
2. agent/plans/PLAN-backup-program.md -- operator 2026-10-20 ("move agent/plans/PLAN-backup-program.md to the promoted"): one backup program across renet, account, CLI and shared, ending in a live hostinger to eu R2 backup; P1; Depends-On PLAN-shell-sandbox-readonly-view.md and PLAN-account-vm-check.md (done 2026-10-20); released to writers by operator /ask ASKED:2026-10-20T15:14Z ("edit writers to go NOW")
3. agent/plans/PLAN-cloudflare-proxy.md -- operator 2026-10-23 ("move agent/plans/PLAN-cloudflare-proxy.md promoted but investigate to update it"; /ask: "Keep it and finish Phase 2", B5 "A mint command", console "Wire it after Phase 2"): rdc --proxy through the Cloudflare Worker and Container deployed on eu 2026-09-24; P1; Depends-On none; the plan was refreshed against the code the same day and its proven boxes ticked
4. agent/plans/PLAN-sync-remote-file-ownership.md -- operator 2026-10-23 (plan prompt /tmp/prompt-sync-remote-file-ownership.md): rdc repo sync upload --remote-file leaves the parent directories it creates root:root; fix through a skeleton rsync of only the missing segments so they get the universal user and existing directories are never re-owned; P1; Depends-On none; approved by operator /ask 2026-10-23 ("Approve both", "Commit as usual")
5. agent/plans/PLAN-telemetry-export.md -- operator 2026-10-23 (plan prompt /tmp/prompt-telemetry-export-plan.md; /ask: "Approve both", "Accept all defaults", no operator steps): the account Workers and the executor proxy export traces and logs to otlp.rediacc.io through Cloudflare's native OTLP destinations, per region and channel, with a scheduled delivery check; P2; Depends-On none (its proxy box T15 waits on PLAN-cloudflare-proxy.md#P2a)
6. agent/plans/PLAN-renet-bridge-leftovers.md -- operator 2026-10-23 (plan prompt /tmp/prompt-bridge-leftovers.md; /ask: "Commit as usual"): the broken renet ops self-test (bridge once plus three unregistered function names), 65 dead and 20 renamed bridge.* keys, stale renet and console docs, the 12 www policy translations naming the middleware and web app, and the bridge-functions wording; P2; approved with Q1 "(b) Also rename the harness", Q3 "Historical banner", Q4 "Change it" (/ask 2026-10-23)
7. agent/plans/PLAN-token-ip-rebind.md -- pulled in as an unfinished prerequisite of PLAN-config-sync-hardening.md (Depends-On), 2026-10-23
8. agent/plans/PLAN-config-sync-hardening.md -- operator 2026-10-23 ("Pick some new close to finish plans that have progressed, and promote them"): 18/19, closure box T15 left; --promote brings its prerequisites PLAN-token-ip-rebind (9/10), PLAN-config-handoff-relay-only (9/11) and PLAN-app-wide-org-selection (2/3) ahead of it
9. agent/plans/PLAN-stop-hook-one-plan-scope.md -- operator 2026-10-23 ("Pick some new close to finish plans ... promote them"): 14/15, the last box SC13b is evidence from a real run after this PR merges
10. agent/plans/PLAN-w7p5a-real-run-dispatch.md -- operator 2026-10-23 (more writers in parallel wanted, so those plans are promoted as well): promoted for a parallel wave, each plan validated against the tree first
11. agent/plans/PLAN-pin-awscli-toolchain-python-compatible.md -- operator 2026-10-23 (more writers in parallel wanted, so those plans are promoted as well): promoted for a parallel wave, each plan validated against the tree first
12. agent/plans/PLAN-plan-preflight.md -- operator 2026-10-23 (more writers in parallel wanted, so those plans are promoted as well): promoted for a parallel wave, each plan validated against the tree first
13. agent/plans/PLAN-renet-run-docker-sock-isolation.md -- operator 2026-10-23 (more writers in parallel wanted, so those plans are promoted as well): promoted for a parallel wave, each plan validated against the tree first
14. agent/plans/PLAN-config-networkid-discovery.md -- operator /ask 2026-10-23 rewrite of the superseded plan (ruling #0c1cbd0d), validated against the tree
15. agent/plans/PLAN-renet-fetch-retries.md -- operator /ask 2026-10-23 rewrite of the superseded plan (ruling #0c1cbd0d), validated against the tree
16. agent/plans/PLAN-cloudflare-spend-guard.md -- operator /ask 2026-10-23 ("One spend-guard plan, all of it"): usage alerts, observability sampling after measurement, R2 lifecycle on release prefixes, weekly usage report, sampling gate, leftovers report
17. agent/plans/PLAN-dockerd-api-privilege-gate.md -- triage #8cb01693 PLAN+SUBAGENT; follows PLAN-renet-cross-repo-isolation T9 finding

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked)
2. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
3. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, executing, in progress (16 of 17 boxes ticked)
4. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, in progress (2 of 5 boxes ticked)
5. agent/plans/PLAN-stop-hook-rulings-campaign.md -- P3, draft, in progress (3 of 17 boxes ticked)
6. agent/plans/PLAN-deletion-budget.md -- P3 (operator), draft, not started
7. agent/plans/PLAN-hostinger-upgrade-followups.md -- P1, in-progress, not started
8. agent/plans/PLAN-plan-compaction-bindings.md -- P1, approved, not started
9. agent/plans/PLAN-backup-toc-exact-opt-in.md -- P3, proposed, not started
10. agent/plans/PLAN-lessons-registry-followups.md -- P3, draft, not started
11. agent/plans/PLAN-plan-verbs.md -- P3, draft, not started
12. agent/plans/PLAN-retire-bash-oracles.A0.md -- P3, executing, not started
13. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, proposed, not started
<!-- queue:generated:end -->

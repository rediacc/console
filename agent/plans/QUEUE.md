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
effort: smart
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
- Branch: 1023-1, no PR yet.
- Plans on the PR (9):
  - agent/plans/PLAN-plan-per-pr-loop.md -- 16 of 16 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/_done/PLAN-pins-command.md -- 13 of 13 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-w7p5a-real-run-dispatch.md -- 9 of 9 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/_done/PLAN-stop-hook-rulings-campaign.md -- 17 of 17 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-backup-program.md -- 125 of 195 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-agent-tree-lifecycle.md -- 6 of 7 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-cloudflare-proxy.md -- 25 of 29 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-sync-remote-file-ownership.md -- 5 of 6 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-telemetry-export.md -- 15 of 19 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
- Work outside the PR's plans (3 epic(s)):
  - epic 9f92c43e, plan agent/plans/PLAN-stop-hook-rulings-campaign.md, outside the set, 889 commit(s) on the branch, 1 open item(s): agent tooling: ci-trace follows any workflow, /wisdom questions the session own conduct
  - epic 6f81c19f, plan agent/plans/PLAN-hostinger-upgrade-followups.md, outside the set, 3 commit(s) on the branch, 0 open item(s): hostinger CVE-response product follow-ups: Traefik v3.7.16, template fixes, /run docker.sock write-up
  - epic 9ba16177, plan agent/plans/PLAN-renet-bridge-leftovers.md, outside the set, 5 commit(s) on the branch, 0 open item(s): renet bridge and middleware leftovers removed
- Writers: 2 live of writer_cap 15 (session d778be9d): worker:a4ea81bec486e1a4e, worker:a390020fe5a47744e.
- Leased items: 4: #0579bfae (worker:a4ea81bec486e1a4e, d778be9d), #0f1798ee (worker:a390020fe5a47744e, d778be9d), #5b7302fd (worker:a390020fe5a47744e, d778be9d), #dba13629 (worker:a390020fe5a47744e, d778be9d).
- Next plan: agent/plans/PLAN-token-ip-rebind.md, Promoted entry 7; starts after this branch's PR merges.
<!-- queue:inflight:end -->

## Promoted

<!-- queue:progress:begin -->
Promoted: 8 of 27 plans done, 396 of 535 boxes done (74%).

| # | Plan | Boxes done | State |
|---|---|---|---|
| 1 | PLAN-plan-per-pr-loop.md | 16/16 | done |
| 2 | PLAN-backup-program.md | 126/196 | 70 open |
| 3 | PLAN-cloudflare-proxy.md | 25/29 | 4 open |
| 4 | PLAN-sync-remote-file-ownership.md | 5/6 | 1 open |
| 5 | PLAN-telemetry-export.md | 15/19 | 4 open |
| 6 | PLAN-renet-bridge-leftovers.md | 14/14 | done |
| 7 | PLAN-token-ip-rebind.md | 9/10 | 1 open |
| 8 | PLAN-config-sync-hardening.md | 18/19 | 1 open |
| 9 | PLAN-stop-hook-one-plan-scope.md | 14/15 | 1 open |
| 10 | PLAN-w7p5a-real-run-dispatch.md | 9/9 | done |
| 11 | PLAN-pin-awscli-toolchain-python-compatible.md | 6/7 | 1 open |
| 12 | PLAN-plan-preflight.md | 8/9 | 1 open |
| 13 | PLAN-renet-run-docker-sock-isolation.md | 3/3 | done |
| 14 | PLAN-config-networkid-discovery.md | 7/7 | done |
| 15 | PLAN-renet-fetch-retries.md | 2/2 | done |
| 16 | PLAN-cloudflare-spend-guard.md | 7/9 | 2 open |
| 17 | PLAN-renet-runtime-converge.md | 3/4 | 1 open |
| 18 | PLAN-sandbox-tenant-separation.md | 6/7 | 1 open |
| 19 | PLAN-converge-preflight-and-repo-recovery.md | 18/18 | done |
| 20 | PLAN-gpu-device-grants.md | 10/12 | 2 open |
| 21 | PLAN-proxy-cd-six-targets.md | 24/34 | 10 open |
| 22 | PLAN-console-executor-multi-org.md | 14/20 | 6 open |
| 23 | PLAN-executor-durable-object-policy.md | 11/21 | 10 open |
| 24 | PLAN-local-release.md | 14/16 | 2 open |
| 25 | PLAN-config-server-key.md | 6/6 | done |
| 26 | PLAN-tested-on-bench.md | 6/19 | 13 open |
| 27 | PLAN-per-flavor-renet-binary-paths.md | 0/8 | 8 open |
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
17. agent/plans/PLAN-renet-runtime-converge.md -- operator 2026-10-24: asked whether hostinger repos need down/up after the layout change, then ordered autonomous continuation; worklist #d0928775
18. agent/plans/PLAN-sandbox-tenant-separation.md -- live QA on .11 2026-10-24: cross-repo docker socket access, unisolated first sandbox compose, foreign mounts, delete leaks; P1 security, fix this session
19. agent/plans/PLAN-converge-preflight-and-repo-recovery.md -- operator 2026-10-24 (ASKED:2026-10-24T17:45Z after the hostinger converge took down mail, observability and nextcloud): converge preflight with compose/gate parity, per-repo cert export for mail, a machine-level host metrics exporter for observability, Collabora without capabilities, then vm:check, deploy and recovery; P0; Depends-On none
20. agent/plans/PLAN-gpu-device-grants.md -- operator 2026-10-24 (ASKED:2026-10-24T18:05Z): CDI inventory and per-repo device grants for NVIDIA and AMD GPUs, tested on the local WSL RTX 3060 and a fake-device drill; P2; Depends-On PLAN-converge-preflight-and-repo-recovery.md
21. agent/plans/PLAN-proxy-cd-six-targets.md -- operator order 2026-10-25T18:10Z (retire the console mock, CD deploys a proxy and executor per target) with the rulings of 18:18Z and 19:08Z
22. agent/plans/PLAN-console-executor-multi-org.md -- operator /ask 2026-10-26 ~05:30Z ("Plan multi-org now, same branch"): one regional executor serves many orgs, one container per org, per-org issued tokens, an entitlement gate in place of the one-org console gate; code boxes wait on six-targets P1 and M1
23. agent/plans/PLAN-executor-durable-object-policy.md -- operator /ask ASKED:2026-10-26T15:26Z ("Per-org, raise the cap"): move the proxy executor off the @cloudflare/containers Container class, frozen after 2026-12-31, to the durable_object scheduling policy; a bench spike first proves per-instance outbound interception, then a coordinator-enforced cap of 25, per-org sizing and a phased forward-only rollout by 2026-12-15
24. agent/plans/PLAN-local-release.md -- operator ruling ASKED:2026-10-27T06:37Z: with no customers yet, a release may be published from the local machine when local verification is green; one comprehensive change, release:local edge and stable, gated on the ci:quick and vm:check receipts, CD publish path deleted
25. agent/plans/PLAN-config-server-key.md -- security finding #caef1cc3: layer 3 encrypted under a public constant; operator ASKED:2026-10-27T11:05Z refuse at boot, mirror first; two landings with a bounded rewrap
26. agent/plans/PLAN-tested-on-bench.md -- operator request 2026-10-27, four questions answered same day
27. agent/plans/PLAN-per-flavor-renet-binary-paths.md -- finding #950036d0 (2026-10-28, vm:check vmc-10280533-5ddf37 NOT_VERIFIED at A2.3): a plain ./rdc.sh flips the shared bin/renet flavor under the license drill; fix-in-session rule (CLAUDE.md rule 2), triage PLAN+SUBAGENT

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked)
2. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
3. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, executing, in progress (16 of 17 boxes ticked)
4. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, in progress (2 of 5 boxes ticked)
5. agent/plans/PLAN-deletion-budget.md -- P3 (operator), draft, not started
6. agent/plans/PLAN-hostinger-upgrade-followups.md -- P1, in-progress, not started
7. agent/plans/PLAN-plan-compaction-bindings.md -- P1, approved, not started
8. agent/plans/PLAN-backup-toc-exact-opt-in.md -- P3, proposed, not started
9. agent/plans/PLAN-lessons-registry-followups.md -- P3, draft, not started
10. agent/plans/PLAN-plan-verbs.md -- P3, draft, not started
11. agent/plans/PLAN-retire-bash-oracles.A0.md -- P3, executing, not started
12. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, proposed, not started

### Not queued

- agent/plans/PLAN-backup-presign-bucket-require-and-wrangler-vars.md -- all boxes ticked: close it
- agent/plans/PLAN-retired-terms-submodule-scan.md -- all boxes ticked: close it
<!-- queue:generated:end -->

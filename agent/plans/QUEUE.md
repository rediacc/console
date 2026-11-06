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
writer_cap: 25 -- operator 2026-10-23: parallel writers on all Promoted plans
commit_remind_min: 15 -- operator 2026-10-06: PLAN-fast-loop Part 2 default
turbo_push: batch-end -- operator 2026-10-08: turbo completes plans locally, one push per batch
backup_push_h: 4 -- operator 2026-10-08: backup push valve, no PR
```

## In flight

What the loop is working on now, rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` (`refresh_inflight`) on every stop and on every `worklist.py --queue-set` or `--phase`. It is runtime state: rewritten only when it changes, never compared by `npm run check:ci-plan-record`, and a committed copy is a snapshot from its commit.

<!-- queue:inflight:begin -->
- Mode: effort smart; turbo on; turbo_push batch-end; batch_size 3; plan_concurrency 5; writer_cap 25; commit_remind_min 15; backup_push_h 4; judge core; cadence on; agent_hint on; agent_pushback on.
- Phase: merge on PR #602 (branch 1023-1, session 45048a90, since 2026-11-03T09:46:12Z, past its 24-hour limit); babysit on PR #? (branch 1104-1, session d778be9d, since 2026-11-06T19:22:42Z).
- Branch: 1104-1, no PR yet.
- Plans on the PR (10):
  - agent/plans/PLAN-backup-program.md -- 171 of 192 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-cloudflare-proxy.md -- 27 of 29 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-sync-remote-file-ownership.md -- 7 of 7 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-stop-hook-one-plan-scope.md -- 14 of 14 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-renet-run-docker-sock-isolation.md -- 4 of 4 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-telemetry-export.md -- 19 of 19 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-plan-preflight.md -- 8 of 8 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-token-ip-rebind.md -- 10 of 11 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-sandbox-tenant-separation.md -- 6 of 8 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
  - agent/plans/PLAN-gpu-device-grants.md -- 12 of 14 boxes ticked, the queue head, standing in while the PR body names no `Plan:` line
- Work outside the PR's plans (13 epic(s)):
  - epic 9f92c43e, plan agent/plans/PLAN-stop-hook-rulings-campaign.md, outside the set, 11 commit(s) on the branch, 0 open item(s): agent tooling: ci-trace follows any workflow, /wisdom questions the session own conduct
  - epic c6b82e88, plan agent/plans/PLAN-settings-set-verb.md, outside the set, 2 commit(s) on the branch, 0 open item(s): settings set verb: one source for the ceilings
  - epic dbb7de07, plan agent/plans/PLAN-cloudflare-spend-guard.md, outside the set, 47 commit(s) on the branch, 0 open item(s): cloudflare spend guard closure
  - epic 09b8bdfa, plan agent/plans/PLAN-detached-jobs.md, outside the set, 561 commit(s) on the branch, 0 open item(s): detached jobs: proxied poll follow and job kinds
  - epic ec9ba176, plan agent/plans/PLAN-backup-integrity.md, outside the set, 2 commit(s) on the branch, 0 open item(s): backup integrity docs and closure
  - epic d6bb9963, plan agent/plans/PLAN-backup-critical-tier.md, outside the set, 7 commit(s) on the branch, 0 open item(s): backup critical tier proofs
  - epic b21ab2e2, plan agent/plans/PLAN-jobs-backup-real-machine-tests.md, outside the set, 2 commit(s) on the branch, 0 open item(s): real machine tests for jobs and backup
  - epic 92df2f69, plan agent/plans/PLAN-free-license.md, outside the set, 5 commit(s) on the branch, 0 open item(s): free license ladder F6
  - epic 1f877343, plan agent/plans/PLAN-worktree-lease.md, outside the set, 55 commit(s) on the branch, 0 open item(s): guided detached worktree leases
  - epic 2e0e531f, plan agent/plans/PLAN-rediaccfile-unprivileged.md, outside the set, 19 commit(s) on the branch, 0 open item(s): Rediaccfile lifecycle runs unprivileged
  - epic 1d805023, plan agent/plans/PLAN-tick-tracking.md, outside the set, 26 commit(s) on the branch, 0 open item(s): tick tracking: plan-box trailer, landing prints the tick, box audit
  - epic f65726d5, plan agent/plans/PLAN-renet-down-before-kill.md, outside the set, 16 commit(s) on the branch, 0 open item(s): renet runs Rediaccfile down() before repo containers stop
  - epic 53c31db2, plan agent/plans/PLAN-repo-resource-limits.md, outside the set, 20 commit(s) on the branch, 0 open item(s): per-repo resource limits and a renet-managed RAM volume
- Writers: 1 live of writer_cap 25 (session d778be9d): worker:ad1878e64bde02a93.
- Leased items: 11: #11306719 (worker:bkzp9i6q2, d778be9d), #22854bf1 (worker:bkzp9i6q2, d778be9d), #3805e275 (worker:bkzp9i6q2, d778be9d), #815e6225 (worker:bkzp9i6q2, d778be9d), #84e99893 (worker:bkzp9i6q2, d778be9d), #abd56226 (worker:bkzp9i6q2, d778be9d), #b69ea0cf (worker:bkzp9i6q2, d778be9d), #cb61605a (worker:bkzp9i6q2, d778be9d), #de9e7e38 (worker:ad1878e64bde02a93, d778be9d), #e3f4063d (worker:bkzp9i6q2, d778be9d), #eb5c1323 (worker:a766e1a29db4ca9b7, d778be9d).
- Next plan: agent/plans/PLAN-proxy-cd-six-targets.md, Promoted entry 17; starts after this branch's PR merges.
<!-- queue:inflight:end -->

## Promoted

<!-- queue:progress:begin -->
Promoted: 14 of 44 plans done, 726 of 939 boxes done (77%).

| # | Plan | Boxes done | State |
|---|---|---|---|
| 1 | PLAN-backup-program.md | 171/192 | 21 open |
| 2 | PLAN-cloudflare-proxy.md | 27/29 | 2 open |
| 3 | PLAN-sync-remote-file-ownership.md | 7/7 | done |
| 4 | PLAN-telemetry-export.md | 19/19 | done |
| 5 | PLAN-renet-bridge-leftovers.md | 16/16 | done |
| 6 | PLAN-token-ip-rebind.md | 10/11 | 1 open |
| 7 | PLAN-stop-hook-one-plan-scope.md | 14/14 | done |
| 8 | PLAN-plan-preflight.md | 8/8 | done |
| 9 | PLAN-renet-run-docker-sock-isolation.md | 4/4 | done |
| 10 | PLAN-config-networkid-discovery.md | 8/8 | done |
| 11 | PLAN-renet-fetch-retries.md | 3/3 | done |
| 12 | PLAN-cloudflare-spend-guard.md | 10/10 | done |
| 13 | PLAN-renet-runtime-converge.md | 5/5 | done |
| 14 | PLAN-sandbox-tenant-separation.md | 6/8 | 2 open |
| 15 | PLAN-converge-preflight-and-repo-recovery.md | 19/19 | done |
| 16 | PLAN-gpu-device-grants.md | 12/14 | 2 open |
| 17 | PLAN-proxy-cd-six-targets.md | 27/31 | 4 open |
| 18 | PLAN-console-executor-multi-org.md | 17/18 | 1 open |
| 19 | PLAN-executor-durable-object-policy.md | 15/18 | 3 open |
| 20 | PLAN-local-release.md | 14/14 | done |
| 21 | PLAN-tested-on-bench.md | 16/20 | 4 open |
| 22 | PLAN-org-executor-connect-timeout-relocate.md | 16/17 | 1 open |
| 23 | PLAN-backup-restore-path.md | 7/10 | 3 open |
| 24 | PLAN-ssh-key-source-ranges.md | 10/11 | 1 open |
| 25 | PLAN-repo-docker-storage-prune.md | 11/14 | 3 open |
| 26 | PLAN-production-key-only.md | 10/17 | 7 open |
| 27 | PLAN-detached-jobs.md | 30/40 | 10 open |
| 28 | PLAN-snapshot-read-io-cap.md | 12/16 | 4 open |
| 29 | PLAN-backup-meter-orphaned-chunks.md | 6/8 | 2 open |
| 30 | PLAN-backup-local-image.md | 10/14 | 4 open |
| 31 | PLAN-backup-plane-shared-bucket-hardening.md | 4/7 | 3 open |
| 32 | PLAN-jobs-backup-real-machine-tests.md | 8/11 | 3 open |
| 33 | PLAN-cli-tofu-toolchain.md | 10/10 | done |
| 34 | PLAN-backup-download-from-store.md | 6/9 | 3 open |
| 35 | PLAN-settings-set-verb.md | 4/4 | done |
| 36 | PLAN-free-license.md | 7/13 | 6 open |
| 37 | PLAN-backup-integrity.md | 42/56 | 14 open |
| 38 | PLAN-backup-critical-tier.md | 41/51 | 10 open |
| 39 | PLAN-rediaccfile-unprivileged.md | 15/23 | 8 open |
| 40 | PLAN-worktree-lease.md | 15/16 | 1 open |
| 41 | PLAN-tick-tracking.md | 13/15 | 2 open |
| 42 | PLAN-renet-down-before-kill.md | 11/15 | 4 open |
| 43 | PLAN-repo-resource-limits.md | 9/13 | 4 open |
| 44 | PLAN-health-checks-local.md | 1/81 | 80 open |
<!-- queue:progress:end -->

1. agent/plans/PLAN-backup-program.md -- operator 2026-10-20 ("move agent/plans/PLAN-backup-program.md to the promoted"): one backup program across renet, account, CLI and shared, ending in a live hostinger to eu R2 backup; P1; Depends-On PLAN-shell-sandbox-readonly-view.md and PLAN-account-vm-check.md (done 2026-10-20); released to writers by operator /ask ASKED:2026-10-20T15:14Z ("edit writers to go NOW")
2. agent/plans/PLAN-cloudflare-proxy.md -- operator 2026-10-23 ("move agent/plans/PLAN-cloudflare-proxy.md promoted but investigate to update it"; /ask: "Keep it and finish Phase 2", B5 "A mint command", console "Wire it after Phase 2"): rdc --proxy through the Cloudflare Worker and Container deployed on eu 2026-09-24; P1; Depends-On none; the plan was refreshed against the code the same day and its proven boxes ticked
3. agent/plans/PLAN-sync-remote-file-ownership.md -- operator 2026-10-23 (plan prompt /tmp/prompt-sync-remote-file-ownership.md): rdc repo sync upload --remote-file leaves the parent directories it creates root:root; fix through a skeleton rsync of only the missing segments so they get the universal user and existing directories are never re-owned; P1; Depends-On none; approved by operator /ask 2026-10-23 ("Approve both", "Commit as usual")
4. agent/plans/PLAN-telemetry-export.md -- operator 2026-10-23 (plan prompt /tmp/prompt-telemetry-export-plan.md; /ask: "Approve both", "Accept all defaults", no operator steps): the account Workers and the executor proxy export traces and logs to otlp.rediacc.io through Cloudflare's native OTLP destinations, per region and channel, with a scheduled delivery check; P2; Depends-On none (its proxy box T15 waits on PLAN-cloudflare-proxy.md#P2a)
5. agent/plans/PLAN-renet-bridge-leftovers.md -- operator 2026-10-23 (plan prompt /tmp/prompt-bridge-leftovers.md; /ask: "Commit as usual"): the broken renet ops self-test (bridge once plus three unregistered function names), 65 dead and 20 renamed bridge.* keys, stale renet and console docs, the 12 www policy translations naming the middleware and web app, and the bridge-functions wording; P2; approved with Q1 "(b) Also rename the harness", Q3 "Historical banner", Q4 "Change it" (/ask 2026-10-23)
6. agent/plans/PLAN-token-ip-rebind.md -- pulled in as an unfinished prerequisite of PLAN-config-sync-hardening.md (Depends-On), 2026-10-23
7. agent/plans/PLAN-stop-hook-one-plan-scope.md -- operator 2026-10-23 ("Pick some new close to finish plans ... promote them"): 14/15, the last box SC13b is evidence from a real run after this PR merges
8. agent/plans/PLAN-plan-preflight.md -- operator 2026-10-23 (more writers in parallel wanted, so those plans are promoted as well): promoted for a parallel wave, each plan validated against the tree first
9. agent/plans/PLAN-renet-run-docker-sock-isolation.md -- operator 2026-10-23 (more writers in parallel wanted, so those plans are promoted as well): promoted for a parallel wave, each plan validated against the tree first
10. agent/plans/PLAN-config-networkid-discovery.md -- operator /ask 2026-10-23 rewrite of the superseded plan (ruling #0c1cbd0d), validated against the tree
11. agent/plans/PLAN-renet-fetch-retries.md -- operator /ask 2026-10-23 rewrite of the superseded plan (ruling #0c1cbd0d), validated against the tree
12. agent/plans/PLAN-cloudflare-spend-guard.md -- operator /ask 2026-10-23 ("One spend-guard plan, all of it"): usage alerts, observability sampling after measurement, R2 lifecycle on release prefixes, weekly usage report, sampling gate, leftovers report
13. agent/plans/PLAN-renet-runtime-converge.md -- operator 2026-10-24: asked whether hostinger repos need down/up after the layout change, then ordered autonomous continuation; worklist #d0928775
14. agent/plans/PLAN-sandbox-tenant-separation.md -- live QA on .11 2026-10-24: cross-repo docker socket access, unisolated first sandbox compose, foreign mounts, delete leaks; P1 security, fix this session
15. agent/plans/PLAN-converge-preflight-and-repo-recovery.md -- operator 2026-10-24 (ASKED:2026-10-24T17:45Z after the hostinger converge took down mail, observability and nextcloud): converge preflight with compose/gate parity, per-repo cert export for mail, a machine-level host metrics exporter for observability, Collabora without capabilities, then vm:check, deploy and recovery; P0; Depends-On none
16. agent/plans/PLAN-gpu-device-grants.md -- operator 2026-10-24 (ASKED:2026-10-24T18:05Z): CDI inventory and per-repo device grants for NVIDIA and AMD GPUs, tested on the local WSL RTX 3060 and a fake-device drill; P2; Depends-On PLAN-converge-preflight-and-repo-recovery.md
17. agent/plans/PLAN-proxy-cd-six-targets.md -- operator order 2026-10-25T18:10Z (retire the console mock, CD deploys a proxy and executor per target) with the rulings of 18:18Z and 19:08Z
18. agent/plans/PLAN-console-executor-multi-org.md -- operator /ask 2026-10-26 ~05:30Z ("Plan multi-org now, same branch"): one regional executor serves many orgs, one container per org, per-org issued tokens, an entitlement gate in place of the one-org console gate; code boxes wait on six-targets P1 and M1
19. agent/plans/PLAN-executor-durable-object-policy.md -- operator /ask ASKED:2026-10-26T15:26Z ("Per-org, raise the cap"): move the proxy executor off the @cloudflare/containers Container class, frozen after 2026-12-31, to the durable_object scheduling policy; a bench spike first proves per-instance outbound interception, then a coordinator-enforced cap of 25, per-org sizing and a phased forward-only rollout by 2026-12-15
20. agent/plans/PLAN-local-release.md -- operator ruling ASKED:2026-10-27T06:37Z: with no customers yet, a release may be published from the local machine when local verification is green; one comprehensive change, release:local edge and stable, gated on the ci:quick and vm:check receipts, CD publish path deleted
21. agent/plans/PLAN-tested-on-bench.md -- operator request 2026-10-27, four questions answered same day
22. agent/plans/PLAN-org-executor-connect-timeout-relocate.md -- finding #a150016d (edge-us org B's executor never reaches its machine; org C on a new Durable Object passes); operator ASKED:2026-10-28T06:55Z "Ride this PR now"
23. agent/plans/PLAN-backup-restore-path.md -- box N4b of PLAN-backup-program.md; operator ASKED 2026-10-28 "Plan it, ride this PR"; the sealed table of contents gains per-file extents, chunkstore a partial fetch, renet a restore-path verb
24. agent/plans/PLAN-ssh-key-source-ranges.md -- operator ASKED 2026-10-28T11:31Z "make it rdc config based ... define IPv4 on rediacc config too, with IPv6"; the executor key's allowed source ranges live in the rdc config and rdc writes the authorized_keys from=; unblocks bench L0
25. agent/plans/PLAN-repo-docker-storage-prune.md -- operator ASKED 2026-10-28T11:21Z "do not cleanup directly! Maybe we need to improve the prune command/support of rdc"; rdc repo prune classifies and reclaims a repository's Docker storage and the reset stops leaking layers; hostinger gets the dry run only until the operator approves
26. agent/plans/PLAN-production-key-only.md -- operator 2026-10-29 "make the production key primary and get rid of the development key ... promote the new plan at QUEUE.md and start in parallel"; one account keypair for every build, gateway and bench, the six ACCOUNT_*_DEV bws entries parked as __<NAME>, renet builds fail closed without a key
27. agent/plans/PLAN-detached-jobs.md -- operator 2026-10-29 ASKED (all four Recommended) + "Remember we must promote all the new plans!": long verbs always run as machine jobs, proxy returns the ticket and the client polls, a ticket store per config, MCP returns the ticket
28. agent/plans/PLAN-snapshot-read-io-cap.md -- operator 2026-10-29 "Remember we must promote all the new plans!"; hostinger snapshot read/hash phase hit load 11.41 under the 100 Mbps upload cap; a read token bucket and hash worker count bound it before the bulk seed resumes
29. agent/plans/PLAN-backup-meter-orphaned-chunks.md -- operator 2026-10-29 "Remember we must promote all the new plans!"; 6.58 GB of chunks a killed run uploaded are in R2 but not in backup usage; bill them at commit, reconcile verb, repair hostinger
30. agent/plans/PLAN-backup-local-image.md -- operator 2026-10-29 ASKED (all four Recommended) + the operator asking whether the new plans were being promoted: rdc backup download/upload of the encrypted repo image to a local path or external drive, in-place weekly update, fresh snapshot per run, prune fixes
31. agent/plans/PLAN-backup-plane-shared-bucket-hardening.md -- operator 2026-10-29 ASKED (Implement all, promote): size-bounded presigned uploads, the unused R2 JWT minter removed, a per-bucket R2 token with a scope probe
32. agent/plans/PLAN-jobs-backup-real-machine-tests.md -- operator 2026-10-29 "make a new plan for the missing tests": real-machine e2e for jobs and backup, the two gates that cannot fail on them, the expired-session account pin, drill legs p and q
33. agent/plans/PLAN-cli-tofu-toolchain.md -- operator 2026-10-29 ASKED (Install command + doctor, Pin provider hashes, PATH-only fallback): rdc tools install tofu with baked checksums, doctor Tools section, provider lock hashes, shared plugin cache
34. agent/plans/PLAN-backup-download-from-store.md -- operator 2026-10-29 "Go: implement": rdc backup download --store from the R2 chunk store with no machine, a backup:restore token scope, renet backup fetch-image, darwin and windows hole punching
35. agent/plans/PLAN-settings-set-verb.md -- operator /ask 2026-10-30 "Yes, plan it": npm run settings -- set|get|list over a tunables registry, one source per value (the R2 ceiling lived in three places), starting with the spend-guard ceilings
36. agent/plans/PLAN-free-license.md -- operator /ask 2026-10-30 (rulings R1-R13): licensing always enforced incl. CI (production key in CI, one shared renet artifact), FREE plan (48 h, 3 GB, 8 per IP per 72 h per server, 3 per machine, unlimited renewal, no backups), COMMUNITY licenses again
37. agent/plans/PLAN-backup-integrity.md -- operator /ask 2026-11-01: all integrity fixes land in #602
38. agent/plans/PLAN-backup-critical-tier.md -- operator /ask 2026-11-01: critical-system backups land in #602
39. agent/plans/PLAN-rediaccfile-unprivileged.md -- operator /ask 2026-11-03: up() and down() run as the universal user with explicit grants, fixed in #602, tested on hostinger
40. agent/plans/PLAN-worktree-lease.md -- operator order 2026-11-04: promote the new plan and continue until the full worktree solution
41. agent/plans/PLAN-tick-tracking.md -- operator order 2026-11-05 ("let's plan for tick. make it promoted after planning."): a Plan-Box trailer on writer commits, worktree land prints the investigate and tick lines with the landed sha, code and live halves tracked per clause in a sibling ledger without touching a box line, worklist.py --box-audit, report capture keeps only lead-bound sends, a blocking plan-box-owed check, and a live-owed state on release; P1; Depends-On none; epic 1d805023
42. agent/plans/PLAN-renet-down-before-kill.md -- operator task 2026-11-05 ("make renet run Rediaccfile down() before Docker repo containers are killed"; plan first, then implement; hostinger modification and testing allowed): an ExecStop stop hook running down() on every docker unit stop, a rediacc-repo-shutdown unit ordered after the docker units, no restart on a stop-side-only unit change, down() before every planned restart path, bounded up()/down() with a raise-only Rediaccfile directive, and a dev-VM marker drill across restart, unit rewrite, converge and reboot; P1; Depends-On none (shares files with PLAN-rediaccfile-unprivileged); epic f65726d5
43. agent/plans/PLAN-repo-resource-limits.md -- operator follow-up 2026-11-05 ("per-repo resource limits, and a renet-managed RAM volume"; "the new plan should be promoted and implemented on a new sub-agent via worktree"; hostinger testing without asking): memory.max, memory.high, cpu.max and io.max on each repo's cgroup as an operator grant, applied live and inherited by forks, OOM kills confined to one container of the capped repo, up()/down() moved into the repo cgroup, and a tmpfs RAM volume at <mount>/.ram unmounted only after down() and dockerd stop; P1; Depends-On PLAN-renet-down-before-kill.md (RAM-volume half only); epic 53c31db2
44. agent/plans/PLAN-health-checks-local.md -- operator order 2026-11-06 ("promote the new plan when it finishes"): scheduled health pings move to the Stop hook, CI gates and one off-box Cloudflare alerter mailing OPS_ALERT_EMAILS via SES; hostinger health fails on warnings; nightly split into a daily drift job and a weekly fleet; backup-perf harness fixed with a 2 GiB variant; demo-stackoverflow archives move to data.rediacc.com

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked)
2. agent/plans/PLAN-ciquick-reds-1023-1.md -- P1, executing, in progress (9 of 12 boxes ticked)
3. agent/plans/PLAN-docker-pin-digest.md -- P1, executing, in progress (8 of 9 boxes ticked)
4. agent/plans/PLAN-drop-free-license-ip-prefix-hash.md -- P1, executing, in progress (4 of 6 boxes ticked)
5. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
6. agent/plans/PLAN-renet-executor-tiered-license-check.md -- P1, executing, in progress (2 of 4 boxes ticked)
7. agent/plans/PLAN-scope-bws-signing-key-to-consuming-step.md -- P1, executing, in progress (8 of 10 boxes ticked)
8. agent/plans/PLAN-split-cli-files-over-512-line-budget.md -- P1, executing, in progress (5 of 7 boxes ticked)
9. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, executing, in progress (16 of 17 boxes ticked)
10. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, in progress (2 of 5 boxes ticked)
11. agent/plans/PLAN-renet-docker-running-semantics.md -- P2, executing, in progress (11 of 15 boxes ticked)
12. agent/plans/PLAN-backup-toc-exact-opt-in.md -- P3, proposed, in progress (1 of 10 boxes ticked)
13. agent/plans/PLAN-deletion-budget.md -- P3 (operator), draft, not started
14. agent/plans/PLAN-fix-upgrade-drills-flat-daemon-bringup.md -- P1, executing, not started
15. agent/plans/PLAN-hostinger-upgrade-followups.md -- P1, in-progress, not started
16. agent/plans/PLAN-plan-compaction-bindings.md -- P1, approved, not started
17. agent/plans/PLAN-product-domain-rename.md -- P1, proposed, not started
18. agent/plans/PLAN-website-routing-and-mail.md -- P1, proposed, not started, dep-blocked
19. agent/plans/PLAN-enterprise-isolation.md -- P1, proposed, not started, dep-blocked
20. agent/plans/PLAN-first-release-checks.md -- P2, approved, not started
21. agent/plans/PLAN-stop-hook-retro-20261101.md -- P2, ready, not started
22. agent/plans/PLAN-lessons-registry-followups.md -- P3, draft, not started
23. agent/plans/PLAN-plan-verbs.md -- P3, draft, not started
24. agent/plans/PLAN-retire-bash-oracles.A0.md -- P3, executing, not started
25. agent/plans/PLAN-submodule-branch-coordination-guard.md -- P3, proposed, not started

### Not queued

- agent/plans/PLAN-retired-terms-submodule-scan.md -- all boxes ticked: close it
<!-- queue:generated:end -->

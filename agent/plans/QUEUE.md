# Plan queue

The ordered queue of plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). <!-- scope: pr.one-plan-per-pr -->One plan per PR by default; with `turbo: on` in `## Settings` the live PR keeps taking queued plans (agent/plans/PLAN-stop-hook-turbo.md), and with `turbo_push: batch-end` (the default) that batch is built and verified locally, then pushed once with one PR when it completes (agent/plans/PLAN-turbo-local-first.md); before then a push needs a `TURBO_PUSH_REASON` that `block_turbo_early_push` admits, and a `backup_push_h` backup push opens no PR. The first entry is the plan the live `MMDD-N` branch works: `.claude/hooks/post-bash/refresh_pr_body.py` writes it as the PR body's `Plan:` line once, and `rediacc_hooks.plan_gate.plan_merge_refusal` refuses the merge while that plan has an open box, unless the body carries an `Operational-Reason:` line.

Two lists, read in this order. `## Promoted` is hand-ordered by the operator and wins; no tool adds, reorders or edits its entries; an entry leaves when its plan moves (`check_plan_folders.py --move` retires it, and check:ci-plan-record RQ-MOVED refuses an entry that points at a moved stub). `## Generated` is rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` from live tracked plans with at least one open box: prerequisites first (`Depends-On:`, task refs and sub-plans like `PLAN-x.A0.md`, each prerequisite pulled ahead to the rank of what needs it), then held plans after unheld ones, prerequisites excepted, then in-progress plans before not-started ones, then operator Priority, AI Priority and path. Plans with no open box are listed under `### Not queued` with the reason, never as entries. Regenerate with `npm run check:ci-plan-record -- --update`; the same gate fails while the section is stale.

`## In flight`, between `## Settings` and `## Promoted`, says what the loop is working on now: the effective switches, every session's wind-down phase, the live branch and its PR, each plan in the PR's plan set with its box progress and how it joined (the `Plan:` line, a turbo batch claim, an `Operational-Reason:` addition, a prerequisite), the branch's epics outside that set, live writers, leased items, and the next plan with its reason. The Stop hook and the `--queue-set` and `--phase` verbs render it between its markers from runtime state; no gate compares it, and no number in it is a list entry.

The progress block directly under `## Promoted` is generated, between the `queue:progress` markers: an overall line (plans done, boxes done, percentage) and one row per entry, keyed by the entry's own number, with its done/total box ratio. The counts come from the plan files by the merge gate's rule (`rediacc_hooks.plan_gate.open_boxes`, a `Moved-To:` stub followed), which check:ci-plan-boxes holds equal to `.ci/config/plan-boxes.json`. The Stop hook re-renders it on every run, as do `--queue-set`, `--phase` and the plan verbs (`--plan-tick`, `--plan-investigate`, `--plan-compact`, `--plan-revive`); `npm run check:ci-plan-record` fails while it disagrees with the plans, and `npm run check:ci-plan-record -- --update` rewrites it. Edit the entries below the block, never the block.

Entry format: `1. agent/plans/PLAN-<slug>.md`, optionally followed by ` -- <note>`. Only numbered entries inside the two sections are read; the progress block holds table rows, never entries.

## Settings

The switchboard for the Stop hook, read by `.claude/hooks/stop/wl_planqueue.py` (`settings`). One fenced block holding one line, `effort: <level>`, with an optional ` -- <note>` carrying the operator's reason. `effort` is the only setting (agent/plans/PLAN-simple-two-tree-loop.md ruling 11): its bundle in `.claude/config/effort.json` decides the judge, the cadence, the specialist-agent hint and the agent pushback, and any other line is refused by name with the line to delete. A missing or bad `effort:` line is `high`, every check; `npm run check:ci-plan-record` names the problem. Change it with `worklist.py --queue-set <me> effort=<level> [--note "<text>"]`, then commit this file.

The levels, each a superset of the one before:

- `quiet`: the FLOOR only (`.claude/hooks/stop/wl_floor.py`: the hook cannot see, a broken watch, CI red or unreadable, a dead or over-cap writer, an unread report, a wait with no wake-up timer, STATE.md when compaction is due). No judge. There is no off switch; this is the quietest the hook gets.
- `low`: plus the mission: open items, the PR's plan, its finish line, its reviews, the loop orders.
- `smart`: plus owed work and record integrity; `no-remaining` and `out-of-sync` only advise; the judge runs without riders.
- `high`: every check, the full judge with its riders.

`.claude/config/effort.json` gives every check its threshold (`{"block": <level>, "advise": <level>}`, or `floor`); moving a check between levels is an edit there, which the effort-table rule of `npm run check:ci-plan-record` keeps complete.

Fixed in code, not settable: the writer cap is 25 (`wl_roster.WRITER_CAP`; a spawn beyond it is refused by `block_agent_cap`, the Stop hook blocks on a roster above it, and the lease verb caps the trees on disk with it), and the commit reminder speaks after 15 minutes without a commit while this session's own edits are uncommitted (`wl_checks.COMMIT_REMIND_MIN`, a reminder, never a block).

```stop-hook
effort: quiet
```

## In flight

What the loop is working on now, rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` (`refresh_inflight`) on every stop and on every `worklist.py --queue-set` or `--phase`. It is runtime state: rewritten only when it changes, never compared by `npm run check:ci-plan-record`, and a committed copy is a snapshot from its commit.

<!-- queue:inflight:begin -->
- Mode: effort quiet; judge off; cadence on; agent_hint off; agent_pushback off.
- Branch: 1121-1, no PR yet.
- Landing tree: branch 1104-1, PR #605 merged.
- Development tree: branch 1121-1, no PR yet.
- Plans on the PR: none yet. The push that opens this branch's PR writes the queue head, agent/plans/PLAN-ciquick-cpu.md, as its `Plan:` line unless the body names a plan first.
- Work outside the PR's plans (4 epic(s)):
  - epic 79b7e92e, no plan, 243 commit(s) on the branch, 0 open item(s): D1 scaling review fixes: sweep limits, nightly token sweeps, telemetry retention
  - epic 422370f4, no plan, 1 commit(s) on the branch, 0 open item(s): Java4Shell CVE-2026-114938 triage (hostinger + templates)
  - epic 29d3123a, plan agent/plans/PLAN-tooling-speed.md, outside the set, 1 commit(s) on the branch, 0 open item(s): Tooling speed: Stop hook, profiler, lifecycle, watchdog, wrangler lane
  - epic dfaac428, plan agent/plans/PLAN-tooling-code-reduction.md, outside the set, 2 commit(s) on the branch, 0 open item(s): Tooling code reduction: scaffolding, gate generator, env registry, gate tables, hook tables, fire ledger
- Writers: 2 live of writer_cap 25 (session ace763dd): worker:a31b487b485cac860, worker:a260e28357d53e1f8.
- Leased items: 5: #064f9dfc (worker:a260e28357d53e1f8, ace763dd), #3b82cf28 (worker:bs2zwmetr, ace763dd), #47ce3621 (worker:bs2zwmetr, ace763dd), #73b32419 (worker:bs2zwmetr, ace763dd), #ce9966d1 (worker:bs2zwmetr, ace763dd).
- Next plan: agent/plans/PLAN-ciquick-cpu.md, Promoted entry 1; starts when this branch's PR binds it on its first push.
<!-- queue:inflight:end -->

## Promoted

<!-- queue:progress:begin -->
Promoted: 17 of 77 plans done, 1241 of 1562 boxes done (79%).

| # | Plan | Boxes done | State |
|---|---|---|---|
| 1 | PLAN-ciquick-cpu.md | 16/38 | 22 open |
| 2 | PLAN-backup-program.md | 186/192 | 6 open |
| 3 | PLAN-cloudflare-proxy.md | 28/29 | 1 open |
| 4 | PLAN-telemetry-export.md | 19/19 | done |
| 5 | PLAN-token-ip-rebind.md | 11/11 | done |
| 6 | PLAN-cloudflare-spend-guard.md | 10/10 | done |
| 7 | PLAN-sandbox-tenant-separation.md | 7/8 | 1 open |
| 8 | PLAN-converge-preflight-and-repo-recovery.md | 19/19 | done |
| 9 | PLAN-gpu-device-grants.md | 13/14 | 1 open |
| 10 | PLAN-proxy-cd-six-targets.md | 27/31 | 4 open |
| 11 | PLAN-console-executor-multi-org.md | 18/18 | done |
| 12 | PLAN-executor-durable-object-policy.md | 18/18 | done |
| 13 | PLAN-local-release.md | 14/14 | done |
| 14 | PLAN-tested-on-bench.md | 16/20 | 4 open |
| 15 | PLAN-org-executor-connect-timeout-relocate.md | 17/17 | done |
| 16 | PLAN-backup-restore-path.md | 8/10 | 2 open |
| 17 | PLAN-ssh-key-source-ranges.md | 11/11 | done |
| 18 | PLAN-repo-docker-storage-prune.md | 14/14 | done |
| 19 | PLAN-production-key-only.md | 14/17 | 3 open |
| 20 | PLAN-detached-jobs.md | 33/41 | 8 open |
| 21 | PLAN-snapshot-read-io-cap.md | 15/16 | 1 open |
| 22 | PLAN-backup-meter-orphaned-chunks.md | 8/8 | done |
| 23 | PLAN-backup-local-image.md | 11/14 | 3 open |
| 24 | PLAN-backup-plane-shared-bucket-hardening.md | 6/7 | 1 open |
| 25 | PLAN-jobs-backup-real-machine-tests.md | 10/11 | 1 open |
| 26 | PLAN-backup-download-from-store.md | 8/9 | 1 open |
| 27 | PLAN-settings-set-verb.md | 4/4 | done |
| 28 | PLAN-free-license.md | 11/13 | 2 open |
| 29 | PLAN-backup-integrity.md | 49/56 | 7 open |
| 30 | PLAN-backup-critical-tier.md | 48/51 | 3 open |
| 31 | PLAN-rediaccfile-unprivileged.md | 18/23 | 5 open |
| 32 | PLAN-worktree-lease.md | 15/16 | 1 open |
| 33 | PLAN-tick-tracking.md | 13/15 | 2 open |
| 34 | PLAN-renet-down-before-kill.md | 13/15 | 2 open |
| 35 | PLAN-repo-resource-limits.md | 10/13 | 3 open |
| 36 | PLAN-health-checks-local.md | 64/81 | 17 open |
| 37 | PLAN-backup-multi-target.md | 18/21 | 3 open |
| 38 | PLAN-ciquick-reds-1023-1.md | 11/12 | 1 open |
| 39 | PLAN-docker-pin-digest.md | 9/9 | done |
| 40 | PLAN-renet-executor-tiered-license-check.md | 3/4 | 1 open |
| 41 | PLAN-scope-bws-signing-key-to-consuming-step.md | 8/10 | 2 open |
| 42 | PLAN-split-cli-files-over-512-line-budget.md | 7/7 | done |
| 43 | PLAN-renet-docker-running-semantics.md | 13/15 | 2 open |
| 44 | PLAN-product-domain-rename.md | 24/28 | 4 open |
| 45 | PLAN-website-routing-and-mail.md | 15/20 | 5 open |
| 46 | PLAN-enterprise-isolation.md | 26/34 | 8 open |
| 47 | PLAN-renet-restart-cycle-defects.md | 6/7 | 1 open |
| 48 | PLAN-stop-hook-retro-20261101.md | 4/4 | done |
| 49 | PLAN-ciquick-green-then-batch.md | 7/7 | done |
| 50 | PLAN-vmcheck-incremental.md | 2/3 | 1 open |
| 51 | PLAN-ci-vm-image-followups.md | 0/2 | 2 open |
| 52 | PLAN-d1-scaling.md | 19/31 | 12 open |
| 53 | PLAN-experience-feedback.md | 12/16 | 4 open |
| 54 | PLAN-local-first-delivery.md | 14/15 | 1 open |
| 55 | PLAN-account-notices.md | 16/17 | 1 open |
| 56 | PLAN-enterprise-tenants.md | 26/47 | 21 open |
| 57 | PLAN-licence-expiry-notices.md | 6/7 | 1 open |
| 58 | PLAN-onprem-relicence-inbox.md | 10/13 | 3 open |
| 59 | PLAN-signer-bench-stop-binding-reattach.md | 3/3 | done |
| 60 | PLAN-d1-eu-jurisdiction.md | 3/22 | 19 open |
| 61 | PLAN-hostinger-to-bench.md | 12/22 | 10 open |
| 62 | PLAN-multi-region-bench.md | 13/23 | 10 open |
| 63 | PLAN-root-api-token.md | 9/15 | 6 open |
| 64 | PLAN-site-entry-points.md | 7/11 | 4 open |
| 65 | PLAN-root-grants.md | 8/19 | 11 open |
| 66 | PLAN-push-decoupling.md | 18/23 | 5 open |
| 67 | PLAN-stop-hook-store-status.md | 3/9 | 6 open |
| 68 | PLAN-rdc-feedback.md | 18/21 | 3 open |
| 69 | PLAN-account-sidebar-redesign.md | 12/15 | 3 open |
| 70 | PLAN-email-sender-separation.md | 11/18 | 7 open |
| 71 | PLAN-pr-loop-single-source.md | 7/9 | 2 open |
| 72 | PLAN-two-track-merge-dev.md | 38/44 | 6 open |
| 73 | PLAN-simple-two-tree-loop.md | 7/12 | 5 open |
| 74 | PLAN-preview-signer.md | 12/37 | 25 open |
| 75 | PLAN-weekly-lessons.md | 1/8 | 7 open |
| 76 | PLAN-tooling-speed.md | 0/8 | 8 open |
| 77 | PLAN-tooling-code-reduction.md | 1/11 | 10 open |
<!-- queue:progress:end -->

1. agent/plans/PLAN-ciquick-cpu.md -- operator ruling ASKED:2026-11-16T11:35Z (fixes A+B+C) and operator 2026-11-17 ("we should prioritze the plan we haven't started to make the ci quick faster"): sound gate reuse, pytest by impact locally, faster slow tests; first in the queue
2. agent/plans/PLAN-backup-program.md -- operator 2026-10-20 ("move agent/plans/PLAN-backup-program.md to the promoted"): one backup program across renet, account, CLI and shared, ending in a live hostinger to eu R2 backup; P1; Depends-On PLAN-shell-sandbox-readonly-view.md and PLAN-account-vm-check.md (done 2026-10-20); released to writers by operator /ask ASKED:2026-10-20T15:14Z ("edit writers to go NOW")
3. agent/plans/PLAN-cloudflare-proxy.md -- operator 2026-10-23 ("move agent/plans/PLAN-cloudflare-proxy.md promoted but investigate to update it"; /ask: "Keep it and finish Phase 2", B5 "A mint command", console "Wire it after Phase 2"): rdc --proxy through the Cloudflare Worker and Container deployed on eu 2026-09-24; P1; Depends-On none; the plan was refreshed against the code the same day and its proven boxes ticked
4. agent/plans/PLAN-telemetry-export.md -- operator 2026-10-23 (plan prompt /tmp/prompt-telemetry-export-plan.md; /ask: "Approve both", "Accept all defaults", no operator steps): the account Workers and the executor proxy export traces and logs to otlp.rediacc.io through Cloudflare's native OTLP destinations, per region and channel, with a scheduled delivery check; P2; Depends-On none (its proxy box T15 waits on PLAN-cloudflare-proxy.md#P2a)
5. agent/plans/PLAN-token-ip-rebind.md -- pulled in as an unfinished prerequisite of PLAN-config-sync-hardening.md (Depends-On), 2026-10-23
6. agent/plans/PLAN-cloudflare-spend-guard.md -- operator /ask 2026-10-23 ("One spend-guard plan, all of it"): usage alerts, observability sampling after measurement, R2 lifecycle on release prefixes, weekly usage report, sampling gate, leftovers report
7. agent/plans/PLAN-sandbox-tenant-separation.md -- live QA on .11 2026-10-24: cross-repo docker socket access, unisolated first sandbox compose, foreign mounts, delete leaks; P1 security, fix this session
8. agent/plans/PLAN-converge-preflight-and-repo-recovery.md -- operator 2026-10-24 (ASKED:2026-10-24T17:45Z after the hostinger converge took down mail, observability and nextcloud): converge preflight with compose/gate parity, per-repo cert export for mail, a machine-level host metrics exporter for observability, Collabora without capabilities, then vm:check, deploy and recovery; P0; Depends-On none
9. agent/plans/PLAN-gpu-device-grants.md -- operator 2026-10-24 (ASKED:2026-10-24T18:05Z): CDI inventory and per-repo device grants for NVIDIA and AMD GPUs, tested on the local WSL RTX 3060 and a fake-device drill; P2; Depends-On PLAN-converge-preflight-and-repo-recovery.md
10. agent/plans/PLAN-proxy-cd-six-targets.md -- operator order 2026-10-25T18:10Z (retire the console mock, CD deploys a proxy and executor per target) with the rulings of 18:18Z and 19:08Z
11. agent/plans/PLAN-console-executor-multi-org.md -- operator /ask 2026-10-26 ~05:30Z ("Plan multi-org now, same branch"): one regional executor serves many orgs, one container per org, per-org issued tokens, an entitlement gate in place of the one-org console gate; code boxes wait on six-targets P1 and M1
12. agent/plans/PLAN-executor-durable-object-policy.md -- operator /ask ASKED:2026-10-26T15:26Z ("Per-org, raise the cap"): move the proxy executor off the @cloudflare/containers Container class, frozen after 2026-12-31, to the durable_object scheduling policy; a bench spike first proves per-instance outbound interception, then a coordinator-enforced cap of 25, per-org sizing and a phased forward-only rollout by 2026-12-15
13. agent/plans/PLAN-local-release.md -- operator ruling ASKED:2026-10-27T06:37Z: with no customers yet, a release may be published from the local machine when local verification is green; one comprehensive change, release:local edge and stable, gated on the ci:quick and vm:check receipts, CD publish path deleted
14. agent/plans/PLAN-tested-on-bench.md -- operator request 2026-10-27, four questions answered same day
15. agent/plans/PLAN-org-executor-connect-timeout-relocate.md -- finding #a150016d (edge-us org B's executor never reaches its machine; org C on a new Durable Object passes); operator ASKED:2026-10-28T06:55Z "Ride this PR now"
16. agent/plans/PLAN-backup-restore-path.md -- box N4b of PLAN-backup-program.md; operator ASKED 2026-10-28 "Plan it, ride this PR"; the sealed table of contents gains per-file extents, chunkstore a partial fetch, renet a restore-path verb
17. agent/plans/PLAN-ssh-key-source-ranges.md -- operator ASKED 2026-10-28T11:31Z "make it rdc config based ... define IPv4 on rediacc config too, with IPv6"; the executor key's allowed source ranges live in the rdc config and rdc writes the authorized_keys from=; unblocks bench L0
18. agent/plans/PLAN-repo-docker-storage-prune.md -- operator ASKED 2026-10-28T11:21Z "do not cleanup directly! Maybe we need to improve the prune command/support of rdc"; rdc repo prune classifies and reclaims a repository's Docker storage and the reset stops leaking layers; hostinger gets the dry run only until the operator approves
19. agent/plans/PLAN-production-key-only.md -- operator 2026-10-29 "make the production key primary and get rid of the development key ... promote the new plan at QUEUE.md and start in parallel"; one account keypair for every build, gateway and bench, the six ACCOUNT_*_DEV bws entries parked as __<NAME>, renet builds fail closed without a key
20. agent/plans/PLAN-detached-jobs.md -- operator 2026-10-29 ASKED (all four Recommended) + "Remember we must promote all the new plans!": long verbs always run as machine jobs, proxy returns the ticket and the client polls, a ticket store per config, MCP returns the ticket
21. agent/plans/PLAN-snapshot-read-io-cap.md -- operator 2026-10-29 "Remember we must promote all the new plans!"; hostinger snapshot read/hash phase hit load 11.41 under the 100 Mbps upload cap; a read token bucket and hash worker count bound it before the bulk seed resumes
22. agent/plans/PLAN-backup-meter-orphaned-chunks.md -- operator 2026-10-29 "Remember we must promote all the new plans!"; 6.58 GB of chunks a killed run uploaded are in R2 but not in backup usage; bill them at commit, reconcile verb, repair hostinger
23. agent/plans/PLAN-backup-local-image.md -- operator 2026-10-29 ASKED (all four Recommended) + the operator asking whether the new plans were being promoted: rdc backup download/upload of the encrypted repo image to a local path or external drive, in-place weekly update, fresh snapshot per run, prune fixes
24. agent/plans/PLAN-backup-plane-shared-bucket-hardening.md -- operator 2026-10-29 ASKED (Implement all, promote): size-bounded presigned uploads, the unused R2 JWT minter removed, a per-bucket R2 token with a scope probe
25. agent/plans/PLAN-jobs-backup-real-machine-tests.md -- operator 2026-10-29 "make a new plan for the missing tests": real-machine e2e for jobs and backup, the two gates that cannot fail on them, the expired-session account pin, drill legs p and q
26. agent/plans/PLAN-backup-download-from-store.md -- operator 2026-10-29 "Go: implement": rdc backup download --store from the R2 chunk store with no machine, a backup:restore token scope, renet backup fetch-image, darwin and windows hole punching
27. agent/plans/PLAN-settings-set-verb.md -- operator /ask 2026-10-30 "Yes, plan it": npm run settings -- set|get|list over a tunables registry, one source per value (the R2 ceiling lived in three places), starting with the spend-guard ceilings
28. agent/plans/PLAN-free-license.md -- operator /ask 2026-10-30 (rulings R1-R13): licensing always enforced incl. CI (production key in CI, one shared renet artifact), FREE plan (48 h, 3 GB, 8 per IP per 72 h per server, 3 per machine, unlimited renewal, no backups), COMMUNITY licenses again
29. agent/plans/PLAN-backup-integrity.md -- operator /ask 2026-11-01: all integrity fixes land in #602
30. agent/plans/PLAN-backup-critical-tier.md -- operator /ask 2026-11-01: critical-system backups land in #602
31. agent/plans/PLAN-rediaccfile-unprivileged.md -- operator /ask 2026-11-03: up() and down() run as the universal user with explicit grants, fixed in #602, tested on hostinger
32. agent/plans/PLAN-worktree-lease.md -- operator order 2026-11-04: promote the new plan and continue until the full worktree solution
33. agent/plans/PLAN-tick-tracking.md -- operator order 2026-11-05 ("let's plan for tick. make it promoted after planning."): a Plan-Box trailer on writer commits, worktree land prints the investigate and tick lines with the landed sha, code and live halves tracked per clause in a sibling ledger without touching a box line, worklist.py --box-audit, report capture keeps only lead-bound sends, a blocking plan-box-owed check, and a live-owed state on release; P1; Depends-On none; epic 1d805023
34. agent/plans/PLAN-renet-down-before-kill.md -- operator task 2026-11-05 ("make renet run Rediaccfile down() before Docker repo containers are killed"; plan first, then implement; hostinger modification and testing allowed): an ExecStop stop hook running down() on every docker unit stop, a rediacc-repo-shutdown unit ordered after the docker units, no restart on a stop-side-only unit change, down() before every planned restart path, bounded up()/down() with a raise-only Rediaccfile directive, and a dev-VM marker drill across restart, unit rewrite, converge and reboot; P1; Depends-On none (shares files with PLAN-rediaccfile-unprivileged); epic f65726d5
35. agent/plans/PLAN-repo-resource-limits.md -- operator follow-up 2026-11-05 ("per-repo resource limits, and a renet-managed RAM volume"; "the new plan should be promoted and implemented on a new sub-agent via worktree"; hostinger testing without asking): memory.max, memory.high, cpu.max and io.max on each repo's cgroup as an operator grant, applied live and inherited by forks, OOM kills confined to one container of the capped repo, up()/down() moved into the repo cgroup, and a tmpfs RAM volume at <mount>/.ram unmounted only after down() and dockerd stop; P1; Depends-On PLAN-renet-down-before-kill.md (RAM-volume half only); epic 53c31db2
36. agent/plans/PLAN-health-checks-local.md -- operator order 2026-11-06 ("promote the new plan when it finishes"): scheduled health pings move to the Stop hook, CI gates and one off-box Cloudflare alerter mailing OPS_ALERT_EMAILS via SES; hostinger health fails on warnings; nightly split into a daily drift job and a weekly fleet; backup-perf harness fixed with a 2 GiB variant; demo-stackoverflow archives move to data.rediacc.com
37. agent/plans/PLAN-backup-multi-target.md -- operator ruling ASKED:2026-11-07T12:26Z ("Approve and queue"): several backup destinations in one account (one config, one licence, one bill), R1 renet account-server check first, then the store registry, per-destination snapshots, restore --from and a bench proof.
38. agent/plans/PLAN-ciquick-reds-1023-1.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
39. agent/plans/PLAN-docker-pin-digest.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
40. agent/plans/PLAN-renet-executor-tiered-license-check.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
41. agent/plans/PLAN-scope-bws-signing-key-to-consuming-step.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
42. agent/plans/PLAN-split-cli-files-over-512-line-budget.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
43. agent/plans/PLAN-renet-docker-running-semantics.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
44. agent/plans/PLAN-product-domain-rename.md -- operator 2026-11-08 ("let us also promote the three tiers plans" then /writers-now): approves the 2026-11-05 tiers design for execution
45. agent/plans/PLAN-website-routing-and-mail.md -- operator 2026-11-08 ("let us also promote the three tiers plans" then /writers-now): approves the 2026-11-05 tiers design for execution
46. agent/plans/PLAN-enterprise-isolation.md -- operator 2026-11-08 ("let us also promote the three tiers plans" then /writers-now): approves the 2026-11-05 tiers design for execution
47. agent/plans/PLAN-renet-restart-cycle-defects.md -- operator 2026-11-08 ("promote from the Generated review"): code done, only hostinger L1 is open
48. agent/plans/PLAN-stop-hook-retro-20261101.md -- operator 2026-11-08 ("promote from the Generated review")
49. agent/plans/PLAN-ciquick-green-then-batch.md -- operator /ask ASKED:2026-11-08T19:20Z ("Green first, then batch (Recommended)")
50. agent/plans/PLAN-vmcheck-incremental.md -- operator /ask ASKED:2026-11-08T19:20Z ("Green first, then batch (Recommended)"), the vm:check half
51. agent/plans/PLAN-ci-vm-image-followups.md -- lead packaging 2026-11-09 (CB5 of PLAN-plan-compaction-bindings): the B5 live check and B7 measurement ruling #c3a46b36 moved out of PLAN-ci-prebaked-vm-images
52. agent/plans/PLAN-d1-scaling.md -- operator rulings 2026-11-09T12:12Z and 12:39Z on the D1 scaling review (Q1-Q8)
53. agent/plans/PLAN-experience-feedback.md -- operator rulings ASKED:2026-11-10T06:24Z ("One plan, run now in parallel"; retire a lesson once a guard, gate, test, CI check or tool fix enforces it): the ledger audit found experience recorded but never fed back (0 of 125 hint proposals promoted, a retro gate silencing long sessions, 6,465 review findings recurring by class); epic #562ef6c3; P1
54. agent/plans/PLAN-local-first-delivery.md -- operator 2026-11-11T09:0xZ: "Queue the new plan now to prompted and start implementing"
55. agent/plans/PLAN-account-notices.md -- operator 2026-11-12: "Please promote the new plans after planning finishes. Then start to implement them"; rulings ASKED 2026-11-12T05:57Z and 06:01Z
56. agent/plans/PLAN-enterprise-tenants.md -- operator 2026-11-12: "employ a parallel agent to complete the gaps in agent/plans/PLAN-enterprise-isolation.md ASAP"; rulings ASKED 2026-11-12T11:3xZ
57. agent/plans/PLAN-licence-expiry-notices.md -- operator 2026-11-12: "do we have any mechanism to notify sales team and the client for delegation cert exprie dates"; sales inbox sales@rediacc.com, "new plan, start now"
58. agent/plans/PLAN-onprem-relicence-inbox.md -- operator rulings ASKED:2026-11-12T16:30Z, 16:56Z, 19:34Z ("C + banner for all box members"): SSH inbox relicence, strict freshness, boot quarantine; R1-R11 and D1 landed, L1 and LP-hostinger open; P1
59. agent/plans/PLAN-signer-bench-stop-binding-reattach.md -- finding 2026-11-12 proof signer --bench: a signer stop by delete breaks the caller binding and leaves bench signing down; triage PLAN+SUBAGENT on #ffca9706; P1
60. agent/plans/PLAN-d1-eu-jurisdiction.md -- operator rulings 2026-11-13 ("Migrate now (Recommended)" ASKED:2026-11-13T07:11Z; "we should also have eu jurisdiction for all bench objects"; window "NOW"): the production eu account D1 reports jurisdiction None, so EU residency rests on a best-effort hint; bench rehearses first; epic #5eb69cff; P0
61. agent/plans/PLAN-hostinger-to-bench.md -- operator ruling 2026-11-13 (move hostinger to bench on a path that needs no operator present): eu-remote stops agents at the operator authenticator on every IP change; hostinger re-homes to eu-bench with a reset guard, pinned allowlist entries and a credential escrow; rediacc-backups-eu deletion waits on C7; P0
62. agent/plans/PLAN-multi-region-bench.md -- operator ruling ASKED:2026-11-13T13:55Z (always-on us and asia benches, us/asia objects copy production placement, all three hosts named bench-<region>.rediacc.cloud with the eu bench migrated off bench.rediacc.cloud): one bench per production region for region proofs and Cloudflare regional-incident rehearsal; cost $0.00 idle, $0.18 typical, $2.44 heavy per month
63. agent/plans/PLAN-root-api-token.md -- operator ruling ASKED:2026-11-15T17:07Z ("Root API token (Recommended)": agents act as root on stable/edge through a root-scoped, IP-bound, expiring token with a TOTP session; no captcha bypass; one portal mint by the operator)
64. agent/plans/PLAN-site-entry-points.md -- operator /ask ASKED:2026-11-17T09:06Z ("Site fixes now, private later"): portal onboarding docs links on www (they 404 on the portal host), a Downloads link under the home video ("Link under the video", ASKED:2026-11-17T08:46Z), and Linux/macOS + Windows install tabs in the portal ("Tabs, no detection")
65. agent/plans/PLAN-root-grants.md -- operator /ask 2026-11-17 ("Need a better and consistent solution. Maybe we should use the same code with names to IDs, mapping."; "Rediacc, registered"; "Yes: ops tool + ops-health check"): the root email gets user panels, console, admin and partner/sales in every region through one names-to-ids reconcile
66. agent/plans/PLAN-push-decoupling.md -- operator /ask 2026-11-18 ("1 Pinned receipts + locks, 3 Needs: tag, 4 W2.5/W2.6 + W4 + vm per-leg"; not 2, not 5): land work while a receipt builds, lock the shared fleet and bench, route boxes by Needs:.
67. agent/plans/PLAN-stop-hook-store-status.md -- operator plan request 2026-11-18: the Stop hook judges the worklist store, not message prose; `worklist.py --status`, a store freshness check replaces the roster/MISSING IDS rule.
68. agent/plans/PLAN-rdc-feedback.md -- operator /ask 2026-11-18 rulings 1-12: `rdc feedback report|list`, D1 intake with daily limits and fingerprint dedup, AI triage with Haiku screening, critical asks with a 6 h window, PLAN-feedback-<slug> generation, Feedback: plan linkage.
69. agent/plans/PLAN-account-sidebar-redesign.md -- operator 2026-11-19 handoff and /ask answers: one mode's links behind a workspace switcher, one Ctrl+K palette for everyone, confirmed sign-out (P2 first), the seven offer labels in 13 locales plus a raw-key CI gate, both Machines pages kept, a root-grants bench test partner and an automated bench walk-through.
70. agent/plans/PLAN-email-sender-separation.md -- operator 2026-11-19 /ask answers: customer and contact mail from contact@ with Reply-To and [Contact], system mail from alerts@ with [System], urgent alerts instant and the rest in a daily digest, shared mailboxes contact@rediacc.com and alerts@rediacc.io on the hostinger docker-mailserver with Sieve copy lists and loopback-only ManageSieve.
71. agent/plans/PLAN-pr-loop-single-source.md -- operator 2026-11-20 request (#a70fd30e): one file per PR-loop rule, /pr-babysit a launcher over the agent file, scope-mirrors per-clause canonical with ref pointers, and the check:ci-prose-duplication drift gate; starts after PR #605 merges
72. agent/plans/PLAN-two-track-merge-dev.md -- operator 2026-11-20 /ask approval (#688f35df, #527aa5b2): PR freeze guard, plan-implementation fact cache and core priority, prose-style cache, account-server traced inputs, signed CI receipts from one devcontainer image; dev track deferred; inline after PR #605 merges
73. agent/plans/PLAN-simple-two-tree-loop.md -- operator 2026-11-21 ("APPROVED!", rulings on #90129fe7): one always-on two-tree loop (the landing tree babysits, merges, watches the release and hotfixes the one PR; the development tree always builds), turbo, phases and five queue knobs deleted, effort the only setting
74. agent/plans/PLAN-preview-signer.md -- operator 2026-11-22 rulings ASKED:2026-11-22T04:23Z, 05:06Z, 05:23Z (#51fb685e, #5ba0a1ce): preview channel; customers test a PR on their own machines via a random-word preview address; rdc preview use/leave switches account service, rdc and touched servers renet to the PR builds and back; per-preview delegated signer, 7-day licences; operator-created preview accounts.
75. agent/plans/PLAN-weekly-lessons.md -- operator 2026-11-22 ("yes let's make a plan about it", after "maybe we should have a weekly plan to address the issues? The plan should be enforced by stop hook and should be added to queue.md?"): 217 hint proposals, 0 resolved; a weekly curator-made PLAN-lessons-<date>.md, one code-fix box per recurring family, enforced by a lessons-weekly Stop hook check at smart, proposals resolved as boxes land.
76. agent/plans/PLAN-tooling-speed.md -- operator /ask 2026-11-22 (#bc8eb843): two tooling plans, speed first; Stop hook reads once, run_stop registry, profiler fixes, in-process lifecycle members, watchdog repeat-failure rule, wrangler-dev-e2e CI lane
77. agent/plans/PLAN-tooling-code-reduction.md -- operator /ask 2026-11-22 (#bc8eb843): migration scaffolding removal, one declaration per gate (first), one env registry, gate tables, hook write analyser and rule tables, guard fire ledger and retirement report; replaces PLAN-deletion-budget.md

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked)
2. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
3. agent/plans/PLAN-stop-hook-refactor-enforcement.md -- P1, executing, in progress (16 of 17 boxes ticked)
4. agent/plans/PLAN-ci-quick-cpu-scheduling.md -- P2, active, in progress (3 of 5 boxes ticked)
5. agent/plans/PLAN-backup-toc-exact-opt-in.md -- P3, proposed, in progress (2 of 10 boxes ticked)
6. agent/plans/PLAN-rmcp-writeback.md -- P0, approved, not started
7. agent/plans/PLAN-backup-schedule-origin-guard.md -- P1, proposed, not started
8. agent/plans/PLAN-console-private.md -- P1, proposed, not started
9. agent/plans/PLAN-fix-upgrade-drills-flat-daemon-bringup.md -- P1, executing, not started
10. agent/plans/PLAN-nightly-green.md -- P1, proposed, not started
11. agent/plans/PLAN-release-credits-compliance.md -- P1, proposed, not started
12. agent/plans/PLAN-rmcp-executor-hardening.md -- P1, approved, not started, dep-blocked
13. agent/plans/PLAN-rmcp-orphan-recovery.md -- P1, approved, not started, dep-blocked
14. agent/plans/PLAN-rmcp-policy-record.md -- P1, approved, not started
15. agent/plans/PLAN-rmcp-decide.md -- P1, approved, not started, dep-blocked
16. agent/plans/PLAN-rmcp-agent-grants.md -- P1, approved, not started, dep-blocked
17. agent/plans/PLAN-rmcp-config-edit-removal.md -- P1, approved, not started, dep-blocked
18. agent/plans/PLAN-rmcp-local-mcp.md -- P1, approved, not started, dep-blocked
19. agent/plans/PLAN-rmcp-remote-worker.md -- P1, approved, not started, dep-blocked
20. agent/plans/PLAN-rmcp-docs.md -- P1, approved, not started, dep-blocked
21. agent/plans/PLAN-stop-hook-retro-20261117.md -- P1, ready, not started
22. agent/plans/PLAN-terms-region-notice.md -- P1, proposed, not started
23. agent/plans/PLAN-canary-on-clusters.md -- P2, proposed, not started
24. agent/plans/PLAN-cluster-crosssite-transport.md -- P2, proposed, not started
25. agent/plans/PLAN-cluster-live-proofs.md -- P2, proposed, not started
26. agent/plans/PLAN-csi-staging-redesign.md -- P2, proposed, not started
27. agent/plans/PLAN-datastore-migrate-correctness.md -- P2, proposed, not started
28. agent/plans/PLAN-first-release-checks.md -- P2, approved, not started
29. agent/plans/PLAN-ghcr-registry-cleanup.md -- P2, proposed, not started
30. agent/plans/PLAN-kubelet-cgroup-rediacc-slice.md -- P2, proposed, not started
31. agent/plans/PLAN-multicluster-local-suite.md -- P2, proposed, not started, dep-blocked
32. agent/plans/PLAN-portal-analytics.md -- P2, proposed, not started
33. agent/plans/PLAN-pr-path-ephemeral-credentials.md -- P2, proposed, not started
34. agent/plans/PLAN-reggate-debt-collection.md -- P2, proposed, not started
35. agent/plans/PLAN-retire-nightlies-and-mentions.md -- P2, proposed, not started
36. agent/plans/PLAN-stop-hook-retro-20261122.md -- P2, ready, not started
37. agent/plans/PLAN-tutorial-recorder-licence.md -- P2, proposed, not started
38. agent/plans/PLAN-www-funnel-truthfulness.md -- P2, proposed, not started
39. agent/plans/PLAN-cncf-conformance.md -- P3, approved, not started
40. agent/plans/PLAN-elite-to-onprem-rename.md -- P3, proposed, not started, dep-blocked
41. agent/plans/PLAN-family-loop-migrate.md -- P3, proposed, not started, dep-blocked
42. agent/plans/PLAN-partner-sales-track.md -- P3, proposed, not started
43. agent/plans/PLAN-plan-verbs.md -- P3, draft, not started
44. agent/plans/PLAN-release-path-protection-2027.md -- P3, approved, not started
45. agent/plans/PLAN-renet-i18n-baseline-drain.md -- P3, proposed, not started
46. agent/plans/PLAN-tutorial-rerecord.md -- P3, proposed, not started, dep-blocked
47. agent/plans/PLAN-vscode-browser-exposure.md -- P3, proposed, not started
48. agent/plans/PLAN-zot-manifest-list-commit.md -- P3, proposed, not started, dep-blocked
<!-- queue:generated:end -->

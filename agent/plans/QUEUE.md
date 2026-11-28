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

No writer limit (operator ruling #3ca908ee, PLAN-unlimited-writers.md): no guard, Stop-hook check or lease-tool count caps live writers at any effort level; the harness concurrent-subagent ceiling is the only bound, and file ownership (`block_plan_concurrency`) still decides who edits what.

```stop-hook
effort: quiet
```

## In flight

What the loop is working on now, rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` (`refresh_inflight`) on every stop and on every `worklist.py --queue-set` or `--phase`. It is runtime state: rewritten only when it changes, never compared by `npm run check:ci-plan-record`, and a committed copy is a snapshot from its commit.

<!-- queue:inflight:begin -->
- Mode: effort quiet; judge off; cadence on; agent_hint off; agent_pushback off.
- Branch: 1121-1, PR #607 open.
- Landing tree: branch 1104-1, PR #605 merged.
- Development tree: branch 1121-1, draft PR #607 open.
- Plans on the PR (1):
  - agent/plans/PLAN-ciquick-cpu.md -- 30 of 38 boxes ticked, the PR body's `Plan:` line
- Work outside the PR's plans (8 epic(s)):
  - epic 9f92c43e, plan agent/plans/PLAN-stop-hook-rulings-campaign.md, outside the set, 1 commit(s) on the branch, 0 open item(s): agent tooling: ci-trace follows any workflow, /wisdom questions the session own conduct
  - epic 09b8bdfa, plan agent/plans/PLAN-detached-jobs.md, outside the set, 1 commit(s) on the branch, 0 open item(s): detached jobs: proxied poll follow and job kinds
  - epic 79b7e92e, no plan, 2594 commit(s) on the branch, 0 open item(s): D1 scaling review fixes: sweep limits, nightly token sweeps, telemetry retention
  - epic 5c2856d0, plan agent/plans/PLAN-rmcp-writeback.md, outside the set, 44 commit(s) on the branch, 0 open item(s): remote-mcp program: ten plans for hosted MCP, write-back, policy record, key slots, on-premise (agent/programs/remote-mcp)
  - epic 422370f4, no plan, 1 commit(s) on the branch, 0 open item(s): Java4Shell CVE-2026-114938 triage (hostinger + templates)
  - epic 29d3123a, plan agent/plans/PLAN-tooling-speed.md, outside the set, 1 commit(s) on the branch, 0 open item(s): Tooling speed: Stop hook, profiler, lifecycle, watchdog, wrangler lane
  - epic dfaac428, plan agent/plans/PLAN-tooling-code-reduction.md, outside the set, 5 commit(s) on the branch, 0 open item(s): Tooling code reduction: scaffolding, gate generator, env registry, gate tables, hook tables, fire ledger
  - epic dcc5af7a, plan agent/plans/PLAN-console-contract-semantics.md, outside the set, 8 commit(s) on the branch, 0 open item(s): Console rework program: plans and decisions (agent/programs/console-rework)
- Writers: 0 live (session d778be9d).
- Leased items: 4: #018bb2f9 (worker:bkukh4p3i, d778be9d), #1e50223f (worker:3510596, d778be9d), #8786e784 (worker:bw91np302, d778be9d), #cac16822 (worker:bouaan1q5, d778be9d).
- Next plan: agent/plans/PLAN-backup-program.md, Promoted entry 2; starts on the next branch after PR #607 merges.
<!-- queue:inflight:end -->

## Promoted

<!-- queue:progress:begin -->
Promoted: 12 of 128 plans done, 1636 of 2180 boxes done (75%).

| # | Plan | Boxes done | State |
|---|---|---|---|
| 1 | PLAN-ciquick-cpu.md | 30/38 | 8 open |
| 2 | PLAN-backup-program.md | 190/192 | 2 open |
| 3 | PLAN-cloudflare-proxy.md | 29/29 | done |
| 4 | PLAN-sandbox-tenant-separation.md | 7/8 | 1 open |
| 5 | PLAN-gpu-device-grants.md | 13/14 | 1 open |
| 6 | PLAN-proxy-cd-six-targets.md | 30/31 | 1 open |
| 7 | PLAN-tested-on-bench.md | 16/20 | 4 open |
| 8 | PLAN-backup-restore-path.md | 8/10 | 2 open |
| 9 | PLAN-production-key-only.md | 15/17 | 2 open |
| 10 | PLAN-detached-jobs.md | 33/41 | 8 open |
| 11 | PLAN-snapshot-read-io-cap.md | 16/16 | done |
| 12 | PLAN-backup-local-image.md | 12/14 | 2 open |
| 13 | PLAN-backup-plane-shared-bucket-hardening.md | 7/7 | done |
| 14 | PLAN-jobs-backup-real-machine-tests.md | 10/11 | 1 open |
| 15 | PLAN-backup-download-from-store.md | 9/9 | done |
| 16 | PLAN-free-license.md | 12/13 | 1 open |
| 17 | PLAN-backup-integrity.md | 53/56 | 3 open |
| 18 | PLAN-backup-critical-tier.md | 49/51 | 2 open |
| 19 | PLAN-rediaccfile-unprivileged.md | 18/23 | 5 open |
| 20 | PLAN-worktree-lease.md | 15/16 | 1 open |
| 21 | PLAN-tick-tracking.md | 13/15 | 2 open |
| 22 | PLAN-renet-down-before-kill.md | 13/15 | 2 open |
| 23 | PLAN-repo-resource-limits.md | 10/13 | 3 open |
| 24 | PLAN-health-checks-local.md | 67/81 | 14 open |
| 25 | PLAN-backup-multi-target.md | 18/21 | 3 open |
| 26 | PLAN-ciquick-reds-1023-1.md | 12/12 | done |
| 27 | PLAN-renet-executor-tiered-license-check.md | 4/4 | done |
| 28 | PLAN-scope-bws-signing-key-to-consuming-step.md | 9/10 | 1 open |
| 29 | PLAN-renet-docker-running-semantics.md | 14/15 | 1 open |
| 30 | PLAN-product-domain-rename.md | 25/28 | 3 open |
| 31 | PLAN-website-routing-and-mail.md | 15/20 | 5 open |
| 32 | PLAN-enterprise-isolation.md | 27/34 | 7 open |
| 33 | PLAN-renet-restart-cycle-defects.md | 7/7 | done |
| 34 | PLAN-ciquick-green-then-batch.md | 7/7 | done |
| 35 | PLAN-vmcheck-incremental.md | 2/3 | 1 open |
| 36 | PLAN-ci-vm-image-followups.md | 0/2 | 2 open |
| 37 | PLAN-d1-scaling.md | 20/31 | 11 open |
| 38 | PLAN-experience-feedback.md | 12/16 | 4 open |
| 39 | PLAN-local-first-delivery.md | 14/15 | 1 open |
| 40 | PLAN-account-notices.md | 16/17 | 1 open |
| 41 | PLAN-enterprise-tenants.md | 32/47 | 15 open |
| 42 | PLAN-licence-expiry-notices.md | 7/7 | done |
| 43 | PLAN-onprem-relicence-inbox.md | 11/13 | 2 open |
| 44 | PLAN-d1-eu-jurisdiction.md | 5/22 | 17 open |
| 45 | PLAN-hostinger-to-bench.md | 15/22 | 7 open |
| 46 | PLAN-multi-region-bench.md | 18/23 | 5 open |
| 47 | PLAN-root-api-token.md | 13/15 | 2 open |
| 48 | PLAN-site-entry-points.md | 8/11 | 3 open |
| 49 | PLAN-root-grants.md | 11/19 | 8 open |
| 50 | PLAN-push-decoupling.md | 20/23 | 3 open |
| 51 | PLAN-stop-hook-store-status.md | 6/9 | 3 open |
| 52 | PLAN-rdc-feedback.md | 18/21 | 3 open |
| 53 | PLAN-account-sidebar-redesign.md | 12/15 | 3 open |
| 54 | PLAN-email-sender-separation.md | 12/18 | 6 open |
| 55 | PLAN-pr-loop-single-source.md | 7/9 | 2 open |
| 56 | PLAN-two-track-merge-dev.md | 41/44 | 3 open |
| 57 | PLAN-simple-two-tree-loop.md | 10/12 | 2 open |
| 58 | PLAN-preview-signer.md | 24/37 | 13 open |
| 59 | PLAN-weekly-lessons.md | 6/8 | 2 open |
| 60 | PLAN-tooling-speed.md | 7/8 | 1 open |
| 61 | PLAN-tooling-code-reduction.md | 7/11 | 4 open |
| 62 | PLAN-stop-hook-retro-20261123.md | 8/8 | done |
| 63 | PLAN-silent-failure-sweep.md | 9/10 | 1 open |
| 64 | PLAN-console-contract-semantics.md | 11/15 | 4 open |
| 65 | PLAN-console-confirm-stepup.md | 10/11 | 1 open |
| 66 | PLAN-console-audit-r2.md | 11/13 | 2 open |
| 67 | PLAN-console-run-index.md | 13/15 | 2 open |
| 68 | PLAN-console-command-line.md | 14/16 | 2 open |
| 69 | PLAN-console-ia.md | 8/10 | 2 open |
| 70 | PLAN-console-animations.md | 7/9 | 2 open |
| 71 | PLAN-rmcp-policy-record.md | 17/26 | 9 open |
| 72 | PLAN-rmcp-decide.md | 6/9 | 3 open |
| 73 | PLAN-rmcp-writeback.md | 13/17 | 4 open |
| 74 | PLAN-rmcp-executor-hardening.md | 14/21 | 7 open |
| 75 | PLAN-rmcp-agent-grants.md | 15/19 | 4 open |
| 76 | PLAN-console-ai-providers.md | 13/15 | 2 open |
| 77 | PLAN-console-ai-assistant.md | 14/17 | 3 open |
| 78 | PLAN-console-ai-credits.md | 11/15 | 4 open |
| 79 | PLAN-console-ai-feedback.md | 8/9 | 1 open |
| 80 | PLAN-console-ai-in-pages.md | 8/10 | 2 open |
| 81 | PLAN-rmcp-config-edit-removal.md | 5/9 | 4 open |
| 82 | PLAN-rmcp-local-mcp.md | 9/13 | 4 open |
| 83 | PLAN-rmcp-orphan-recovery.md | 4/8 | 4 open |
| 84 | PLAN-rmcp-remote-worker.md | 17/27 | 10 open |
| 85 | PLAN-rmcp-docs.md | 10/20 | 10 open |
| 86 | PLAN-stripe-disable.md | 6/8 | 2 open |
| 87 | PLAN-forensics-capture.md | 10/13 | 3 open |
| 88 | PLAN-forensics-shipping.md | 12/16 | 4 open |
| 89 | PLAN-forensics-detection.md | 12/15 | 3 open |
| 90 | PLAN-forensics-investigation.md | 15/17 | 2 open |
| 91 | PLAN-forensics-alerts-notices.md | 11/15 | 4 open |
| 92 | PLAN-forensics-reports.md | 12/14 | 2 open |
| 93 | PLAN-forensics-docs-legal.md | 12/13 | 1 open |
| 94 | PLAN-unlimited-writers.md | 4/5 | 1 open |
| 95 | PLAN-writers-now-cadence.md | 5/5 | done |
| 96 | PLAN-armed-actions.md | 6/6 | done |
| 97 | PLAN-drain-throughput.md | 8/15 | 7 open |
| 98 | PLAN-native-host-rdc-feedback.md | 7/9 | 2 open |
| 99 | PLAN-host-temp-disposal.md | 16/19 | 3 open |
| 100 | PLAN-cf-token-hardening.md | 0/8 | 8 open |
| 101 | PLAN-nightly-green.md | 7/15 | 8 open |
| 102 | PLAN-backup-schedule-origin-guard.md | 3/4 | 1 open |
| 103 | PLAN-release-credits-compliance.md | 7/10 | 3 open |
| 104 | PLAN-reggate-debt-collection.md | 7/11 | 4 open |
| 105 | PLAN-retire-nightlies-and-mentions.md | 9/16 | 7 open |
| 106 | PLAN-renet-i18n-baseline-drain.md | 4/16 | 12 open |
| 107 | PLAN-datastore-migrate-correctness.md | 7/13 | 6 open |
| 108 | PLAN-backup-toc-exact-opt-in.md | 3/10 | 7 open |
| 109 | PLAN-vscode-browser-exposure.md | 6/10 | 4 open |
| 110 | PLAN-release-notes.md | 4/13 | 9 open |
| 111 | PLAN-pr-path-ephemeral-credentials.md | 4/13 | 9 open |
| 112 | PLAN-plan-verbs.md | 0/3 | 3 open |
| 113 | PLAN-windows-lane.md | 5/32 | 27 open |
| 114 | PLAN-config-sealed-local.md | 1/10 | 9 open |
| 115 | PLAN-proxied-licence-tunnel-auth-fix.md | 1/6 | 5 open |
| 116 | PLAN-executor-account-routes.md | 3/8 | 5 open |
| 117 | PLAN-pricing-plan-model.md | 3/4 | 1 open |
| 118 | PLAN-pricing-partner-directory.md | 3/5 | 2 open |
| 119 | PLAN-pricing-seat-repo-caps.md | 0/5 | 5 open |
| 120 | PLAN-pricing-cpu-ceiling.md | 1/7 | 6 open |
| 121 | PLAN-pricing-free-professional.md | 0/5 | 5 open |
| 122 | PLAN-pricing-billing-upgrade.md | 0/8 | 8 open |
| 123 | PLAN-pricing-coupons.md | 0/5 | 5 open |
| 124 | PLAN-pricing-public-calculator.md | 0/7 | 7 open |
| 125 | PLAN-account-api-health.md | 0/12 | 12 open |
| 126 | PLAN-cloud-inventory.md | 0/7 | 7 open |
| 127 | PLAN-preprod-simulation.md | 0/11 | 11 open |
| 128 | PLAN-ciquick-gate-contract.md | 0/18 | 18 open |
<!-- queue:progress:end -->

1. agent/plans/PLAN-ciquick-cpu.md -- operator ruling ASKED:2026-11-16T11:35Z (fixes A+B+C) and operator 2026-11-17 ("we should prioritze the plan we haven't started to make the ci quick faster"): sound gate reuse, pytest by impact locally, faster slow tests; first in the queue
2. agent/plans/PLAN-backup-program.md -- operator 2026-10-20 ("move agent/plans/PLAN-backup-program.md to the promoted"): one backup program across renet, account, CLI and shared, ending in a live hostinger to eu R2 backup; P1; Depends-On PLAN-shell-sandbox-readonly-view.md and PLAN-account-vm-check.md (done 2026-10-20); released to writers by operator /ask ASKED:2026-10-20T15:14Z ("edit writers to go NOW")
3. agent/plans/PLAN-cloudflare-proxy.md -- operator 2026-10-23 ("move agent/plans/PLAN-cloudflare-proxy.md promoted but investigate to update it"; /ask: "Keep it and finish Phase 2", B5 "A mint command", console "Wire it after Phase 2"): rdc --proxy through the Cloudflare Worker and Container deployed on eu 2026-09-24; P1; Depends-On none; the plan was refreshed against the code the same day and its proven boxes ticked
4. agent/plans/PLAN-sandbox-tenant-separation.md -- live QA on .11 2026-10-24: cross-repo docker socket access, unisolated first sandbox compose, foreign mounts, delete leaks; P1 security, fix this session
5. agent/plans/PLAN-gpu-device-grants.md -- operator 2026-10-24 (ASKED:2026-10-24T18:05Z): CDI inventory and per-repo device grants for NVIDIA and AMD GPUs, tested on the local WSL RTX 3060 and a fake-device drill; P2; Depends-On PLAN-converge-preflight-and-repo-recovery.md
6. agent/plans/PLAN-proxy-cd-six-targets.md -- operator order 2026-10-25T18:10Z (retire the console mock, CD deploys a proxy and executor per target) with the rulings of 18:18Z and 19:08Z
7. agent/plans/PLAN-tested-on-bench.md -- operator request 2026-10-27, four questions answered same day
8. agent/plans/PLAN-backup-restore-path.md -- box N4b of PLAN-backup-program.md; operator ASKED 2026-10-28 "Plan it, ride this PR"; the sealed table of contents gains per-file extents, chunkstore a partial fetch, renet a restore-path verb
9. agent/plans/PLAN-production-key-only.md -- operator 2026-10-29 "make the production key primary and get rid of the development key ... promote the new plan at QUEUE.md and start in parallel"; one account keypair for every build, gateway and bench, the six ACCOUNT_*_DEV bws entries parked as __<NAME>, renet builds fail closed without a key
10. agent/plans/PLAN-detached-jobs.md -- operator 2026-10-29 ASKED (all four Recommended) + "Remember we must promote all the new plans!": long verbs always run as machine jobs, proxy returns the ticket and the client polls, a ticket store per config, MCP returns the ticket
11. agent/plans/PLAN-snapshot-read-io-cap.md -- operator 2026-10-29 "Remember we must promote all the new plans!"; hostinger snapshot read/hash phase hit load 11.41 under the 100 Mbps upload cap; a read token bucket and hash worker count bound it before the bulk seed resumes
12. agent/plans/PLAN-backup-local-image.md -- operator 2026-10-29 ASKED (all four Recommended) + the operator asking whether the new plans were being promoted: rdc backup download/upload of the encrypted repo image to a local path or external drive, in-place weekly update, fresh snapshot per run, prune fixes
13. agent/plans/PLAN-backup-plane-shared-bucket-hardening.md -- operator 2026-10-29 ASKED (Implement all, promote): size-bounded presigned uploads, the unused R2 JWT minter removed, a per-bucket R2 token with a scope probe
14. agent/plans/PLAN-jobs-backup-real-machine-tests.md -- operator 2026-10-29 "make a new plan for the missing tests": real-machine e2e for jobs and backup, the two gates that cannot fail on them, the expired-session account pin, drill legs p and q
15. agent/plans/PLAN-backup-download-from-store.md -- operator 2026-10-29 "Go: implement": rdc backup download --store from the R2 chunk store with no machine, a backup:restore token scope, renet backup fetch-image, darwin and windows hole punching
16. agent/plans/PLAN-free-license.md -- operator /ask 2026-10-30 (rulings R1-R13): licensing always enforced incl. CI (production key in CI, one shared renet artifact), FREE plan (48 h, 3 GB, 8 per IP per 72 h per server, 3 per machine, unlimited renewal, no backups), COMMUNITY licenses again
17. agent/plans/PLAN-backup-integrity.md -- operator /ask 2026-11-01: all integrity fixes land in #602
18. agent/plans/PLAN-backup-critical-tier.md -- operator /ask 2026-11-01: critical-system backups land in #602
19. agent/plans/PLAN-rediaccfile-unprivileged.md -- operator /ask 2026-11-03: up() and down() run as the universal user with explicit grants, fixed in #602, tested on hostinger
20. agent/plans/PLAN-worktree-lease.md -- operator order 2026-11-04: promote the new plan and continue until the full worktree solution
21. agent/plans/PLAN-tick-tracking.md -- operator order 2026-11-05 ("let's plan for tick. make it promoted after planning."): a Plan-Box trailer on writer commits, worktree land prints the investigate and tick lines with the landed sha, code and live halves tracked per clause in a sibling ledger without touching a box line, worklist.py --box-audit, report capture keeps only lead-bound sends, a blocking plan-box-owed check, and a live-owed state on release; P1; Depends-On none; epic 1d805023
22. agent/plans/PLAN-renet-down-before-kill.md -- operator task 2026-11-05 ("make renet run Rediaccfile down() before Docker repo containers are killed"; plan first, then implement; hostinger modification and testing allowed): an ExecStop stop hook running down() on every docker unit stop, a rediacc-repo-shutdown unit ordered after the docker units, no restart on a stop-side-only unit change, down() before every planned restart path, bounded up()/down() with a raise-only Rediaccfile directive, and a dev-VM marker drill across restart, unit rewrite, converge and reboot; P1; Depends-On none (shares files with PLAN-rediaccfile-unprivileged); epic f65726d5
23. agent/plans/PLAN-repo-resource-limits.md -- operator follow-up 2026-11-05 ("per-repo resource limits, and a renet-managed RAM volume"; "the new plan should be promoted and implemented on a new sub-agent via worktree"; hostinger testing without asking): memory.max, memory.high, cpu.max and io.max on each repo's cgroup as an operator grant, applied live and inherited by forks, OOM kills confined to one container of the capped repo, up()/down() moved into the repo cgroup, and a tmpfs RAM volume at <mount>/.ram unmounted only after down() and dockerd stop; P1; Depends-On PLAN-renet-down-before-kill.md (RAM-volume half only); epic 53c31db2
24. agent/plans/PLAN-health-checks-local.md -- operator order 2026-11-06 ("promote the new plan when it finishes"): scheduled health pings move to the Stop hook, CI gates and one off-box Cloudflare alerter mailing OPS_ALERT_EMAILS via SES; hostinger health fails on warnings; nightly split into a daily drift job and a weekly fleet; backup-perf harness fixed with a 2 GiB variant; demo-stackoverflow archives move to data.rediacc.com
25. agent/plans/PLAN-backup-multi-target.md -- operator ruling ASKED:2026-11-07T12:26Z ("Approve and queue"): several backup destinations in one account (one config, one licence, one bill), R1 renet account-server check first, then the store registry, per-destination snapshots, restore --from and a bench proof.
26. agent/plans/PLAN-ciquick-reds-1023-1.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
27. agent/plans/PLAN-renet-executor-tiered-license-check.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
28. agent/plans/PLAN-scope-bws-signing-key-to-consuming-step.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
29. agent/plans/PLAN-renet-docker-running-semantics.md -- operator 2026-11-08 ("close to finish: code done, proof missing. promote them and finish in the background"): only live, pipeline and post-merge proof boxes remain
30. agent/plans/PLAN-product-domain-rename.md -- operator 2026-11-08 ("let us also promote the three tiers plans" then /writers-now): approves the 2026-11-05 tiers design for execution
31. agent/plans/PLAN-website-routing-and-mail.md -- operator 2026-11-08 ("let us also promote the three tiers plans" then /writers-now): approves the 2026-11-05 tiers design for execution
32. agent/plans/PLAN-enterprise-isolation.md -- operator 2026-11-08 ("let us also promote the three tiers plans" then /writers-now): approves the 2026-11-05 tiers design for execution
33. agent/plans/PLAN-renet-restart-cycle-defects.md -- operator 2026-11-08 ("promote from the Generated review"): code done, only hostinger L1 is open
34. agent/plans/PLAN-ciquick-green-then-batch.md -- operator /ask ASKED:2026-11-08T19:20Z ("Green first, then batch (Recommended)")
35. agent/plans/PLAN-vmcheck-incremental.md -- operator /ask ASKED:2026-11-08T19:20Z ("Green first, then batch (Recommended)"), the vm:check half
36. agent/plans/PLAN-ci-vm-image-followups.md -- lead packaging 2026-11-09 (CB5 of PLAN-plan-compaction-bindings): the B5 live check and B7 measurement ruling #c3a46b36 moved out of PLAN-ci-prebaked-vm-images
37. agent/plans/PLAN-d1-scaling.md -- operator rulings 2026-11-09T12:12Z and 12:39Z on the D1 scaling review (Q1-Q8)
38. agent/plans/PLAN-experience-feedback.md -- operator rulings ASKED:2026-11-10T06:24Z ("One plan, run now in parallel"; retire a lesson once a guard, gate, test, CI check or tool fix enforces it): the ledger audit found experience recorded but never fed back (0 of 125 hint proposals promoted, a retro gate silencing long sessions, 6,465 review findings recurring by class); epic #562ef6c3; P1
39. agent/plans/PLAN-local-first-delivery.md -- operator 2026-11-11T09:0xZ: "Queue the new plan now to prompted and start implementing"
40. agent/plans/PLAN-account-notices.md -- operator 2026-11-12: "Please promote the new plans after planning finishes. Then start to implement them"; rulings ASKED 2026-11-12T05:57Z and 06:01Z
41. agent/plans/PLAN-enterprise-tenants.md -- operator 2026-11-12: "employ a parallel agent to complete the gaps in agent/plans/PLAN-enterprise-isolation.md ASAP"; rulings ASKED 2026-11-12T11:3xZ
42. agent/plans/PLAN-licence-expiry-notices.md -- operator 2026-11-12: "do we have any mechanism to notify sales team and the client for delegation cert exprie dates"; sales inbox sales@rediacc.com, "new plan, start now"
43. agent/plans/PLAN-onprem-relicence-inbox.md -- operator rulings ASKED:2026-11-12T16:30Z, 16:56Z, 19:34Z ("C + banner for all box members"): SSH inbox relicence, strict freshness, boot quarantine; R1-R11 and D1 landed, L1 and LP-hostinger open; P1
44. agent/plans/PLAN-d1-eu-jurisdiction.md -- operator rulings 2026-11-13 ("Migrate now (Recommended)" ASKED:2026-11-13T07:11Z; "we should also have eu jurisdiction for all bench objects"; window "NOW"): the production eu account D1 reports jurisdiction None, so EU residency rests on a best-effort hint; bench rehearses first; epic #5eb69cff; P0
45. agent/plans/PLAN-hostinger-to-bench.md -- operator ruling 2026-11-13 (move hostinger to bench on a path that needs no operator present): eu-remote stops agents at the operator authenticator on every IP change; hostinger re-homes to eu-bench with a reset guard, pinned allowlist entries and a credential escrow; rediacc-backups-eu deletion waits on C7; P0
46. agent/plans/PLAN-multi-region-bench.md -- operator ruling ASKED:2026-11-13T13:55Z (always-on us and asia benches, us/asia objects copy production placement, all three hosts named bench-<region>.rediacc.cloud with the eu bench migrated off bench.rediacc.cloud): one bench per production region for region proofs and Cloudflare regional-incident rehearsal; cost $0.00 idle, $0.18 typical, $2.44 heavy per month
47. agent/plans/PLAN-root-api-token.md -- operator ruling ASKED:2026-11-15T17:07Z ("Root API token (Recommended)": agents act as root on stable/edge through a root-scoped, IP-bound, expiring token with a TOTP session; no captcha bypass; one portal mint by the operator)
48. agent/plans/PLAN-site-entry-points.md -- operator /ask ASKED:2026-11-17T09:06Z ("Site fixes now, private later"): portal onboarding docs links on www (they 404 on the portal host), a Downloads link under the home video ("Link under the video", ASKED:2026-11-17T08:46Z), and Linux/macOS + Windows install tabs in the portal ("Tabs, no detection")
49. agent/plans/PLAN-root-grants.md -- operator /ask 2026-11-17 ("Need a better and consistent solution. Maybe we should use the same code with names to IDs, mapping."; "Rediacc, registered"; "Yes: ops tool + ops-health check"): the root email gets user panels, console, admin and partner/sales in every region through one names-to-ids reconcile
50. agent/plans/PLAN-push-decoupling.md -- operator /ask 2026-11-18 ("1 Pinned receipts + locks, 3 Needs: tag, 4 W2.5/W2.6 + W4 + vm per-leg"; not 2, not 5): land work while a receipt builds, lock the shared fleet and bench, route boxes by Needs:.
51. agent/plans/PLAN-stop-hook-store-status.md -- operator plan request 2026-11-18: the Stop hook judges the worklist store, not message prose; `worklist.py --status`, a store freshness check replaces the roster/MISSING IDS rule.
52. agent/plans/PLAN-rdc-feedback.md -- operator /ask 2026-11-18 rulings 1-12: `rdc feedback report|list`, D1 intake with daily limits and fingerprint dedup, AI triage with Haiku screening, critical asks with a 6 h window, PLAN-feedback-<slug> generation, Feedback: plan linkage.
53. agent/plans/PLAN-account-sidebar-redesign.md -- operator 2026-11-19 handoff and /ask answers: one mode's links behind a workspace switcher, one Ctrl+K palette for everyone, confirmed sign-out (P2 first), the seven offer labels in 13 locales plus a raw-key CI gate, both Machines pages kept, a root-grants bench test partner and an automated bench walk-through.
54. agent/plans/PLAN-email-sender-separation.md -- operator 2026-11-19 /ask answers: customer and contact mail from contact@ with Reply-To and [Contact], system mail from alerts@ with [System], urgent alerts instant and the rest in a daily digest, shared mailboxes contact@rediacc.com and alerts@rediacc.io on the hostinger docker-mailserver with Sieve copy lists and loopback-only ManageSieve.
55. agent/plans/PLAN-pr-loop-single-source.md -- operator 2026-11-20 request (#a70fd30e): one file per PR-loop rule, /pr-babysit a launcher over the agent file, scope-mirrors per-clause canonical with ref pointers, and the check:ci-prose-duplication drift gate; starts after PR #605 merges
56. agent/plans/PLAN-two-track-merge-dev.md -- operator 2026-11-20 /ask approval (#688f35df, #527aa5b2): PR freeze guard, plan-implementation fact cache and core priority, prose-style cache, account-server traced inputs, signed CI receipts from one devcontainer image; dev track deferred; inline after PR #605 merges
57. agent/plans/PLAN-simple-two-tree-loop.md -- operator 2026-11-21 ("APPROVED!", rulings on #90129fe7): one always-on two-tree loop (the landing tree babysits, merges, watches the release and hotfixes the one PR; the development tree always builds), turbo, phases and five queue knobs deleted, effort the only setting
58. agent/plans/PLAN-preview-signer.md -- operator 2026-11-22 rulings ASKED:2026-11-22T04:23Z, 05:06Z, 05:23Z (#51fb685e, #5ba0a1ce): preview channel; customers test a PR on their own machines via a random-word preview address; rdc preview use/leave switches account service, rdc and touched servers renet to the PR builds and back; per-preview delegated signer, 7-day licences; operator-created preview accounts.
59. agent/plans/PLAN-weekly-lessons.md -- operator 2026-11-22 ("yes let's make a plan about it", after "maybe we should have a weekly plan to address the issues? The plan should be enforced by stop hook and should be added to queue.md?"): 217 hint proposals, 0 resolved; a weekly curator-made PLAN-lessons-<date>.md, one code-fix box per recurring family, enforced by a lessons-weekly Stop hook check at smart, proposals resolved as boxes land.
60. agent/plans/PLAN-tooling-speed.md -- operator /ask 2026-11-22 (#bc8eb843): two tooling plans, speed first; Stop hook reads once, run_stop registry, profiler fixes, in-process lifecycle members, watchdog repeat-failure rule, wrangler-dev-e2e CI lane
61. agent/plans/PLAN-tooling-code-reduction.md -- operator /ask 2026-11-22 (#bc8eb843): migration scaffolding removal, one declaration per gate (first), one env registry, gate tables, hook write analyser and rule tables, guard fire ledger and retirement report; replaces PLAN-deletion-budget.md
62. agent/plans/PLAN-stop-hook-retro-20261123.md -- standing procedure PLAN-stop-hook-continuity.md P3.1 (band late, session ace763dd): landing-stack blocks while promote refuses, hooks of the onto base during a rebase, STATE.md voiding push receipts, commit-ref reachability, landing-cut leases
63. agent/plans/PLAN-silent-failure-sweep.md -- operator /ask 2026-11-23 ("One plan this branch but start in parallel immediately"): quality scripts refuse unknown flags through one parser, and Stop hook reads name their failure; SF1-SF3 writers started at once
64. agent/plans/PLAN-console-contract-semantics.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: summaries, severity, preview polarity, error origin, content-hash version, lazy contract, MCP reveal drop
65. agent/plans/PLAN-console-confirm-stepup.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: severity dialogs, typed name, server step-up at /console/exec, passkey elevation, org minimum, console reveal
66. agent/plans/PLAN-console-audit-r2.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: R2 audit with nightly compaction and hash chain, paid visibility, admin show-from date, per-plan retention
67. agent/plans/PLAN-console-run-index.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: server run index, keep-awake, block-stream panel, status-bar pills, server history
68. agent/plans/PLAN-console-command-line.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: own core in packages/shared, plain command box, recipes, rdc completion, keyboard and IME tests
69. agent/plans/PLAN-console-ia.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: Variant A labels, runs-where badges and grouping, landing
70. agent/plans/PLAN-console-animations.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: step-driven animations, reduced motion, dead animate-in classes
71. agent/plans/PLAN-rmcp-policy-record.md -- pulled in as an unfinished prerequisite of PLAN-rmcp-decide.md (Depends-On), 2026-11-23
72. agent/plans/PLAN-rmcp-decide.md -- pulled in as an unfinished prerequisite of PLAN-console-ai-providers.md (Depends-On), 2026-11-23
73. agent/plans/PLAN-rmcp-writeback.md -- pulled in as an unfinished prerequisite of PLAN-rmcp-agent-grants.md (Depends-On), 2026-11-23
74. agent/plans/PLAN-rmcp-executor-hardening.md -- pulled in as an unfinished prerequisite of PLAN-rmcp-agent-grants.md (Depends-On), 2026-11-23
75. agent/plans/PLAN-rmcp-agent-grants.md -- pulled in as an unfinished prerequisite of PLAN-console-ai-providers.md (Depends-On), 2026-11-23
76. agent/plans/PLAN-console-ai-providers.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: BYO provider profiles in the encrypted config, loop host in the executor; waits on PLAN-rmcp-decide.md and PLAN-rmcp-agent-grants.md
77. agent/plans/PLAN-console-ai-assistant.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: action timeline, simple view, Ask/Auto/Skip with judge, chips, branching, microphone
78. agent/plans/PLAN-console-ai-credits.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: enterprise credits on Workers AI and Unified Billing, per-org ledger, every guard
79. agent/plans/PLAN-console-ai-feedback.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: feedback offers on Rediacc-origin failures, per-user and owner settings
80. agent/plans/PLAN-console-ai-in-pages.md -- operator /ask 2026-11-23 (#b785e9ff), program agent/programs/console-rework: Ask-about-this bars, inline suggestions, background tasks
81. agent/plans/PLAN-rmcp-config-edit-removal.md -- operator /ask 2026-11-23: promote the whole rmcp program (supersedes D51)
82. agent/plans/PLAN-rmcp-local-mcp.md -- operator /ask 2026-11-23: promote the whole rmcp program (supersedes D51)
83. agent/plans/PLAN-rmcp-orphan-recovery.md -- operator /ask 2026-11-23: promote the whole rmcp program (supersedes D51)
84. agent/plans/PLAN-rmcp-remote-worker.md -- operator /ask 2026-11-23: promote the whole rmcp program (supersedes D51)
85. agent/plans/PLAN-rmcp-docs.md -- operator /ask 2026-11-23: promote the whole rmcp program (supersedes D51)
86. agent/plans/PLAN-stripe-disable.md -- operator /ask 2026-11-23 (#0831560e): one server-enforced BILLING_STRIPE flag, default off, disables checkout, portal, plan switching, webhook and admin Stripe pages on deploy
87. agent/plans/PLAN-forensics-capture.md -- operator /ask 2026-11-23 (#772cfd55), program agent/programs/breach-forensics: renet eBPF flow and file-open capture, three levels and spike trigger, collector and signed sectioned spool
88. agent/plans/PLAN-forensics-shipping.md -- operator /ask 2026-11-23 (#772cfd55), program agent/programs/breach-forensics: licence-minted create-only log shipping, locked evidence bucket, compaction, quotas, FIFO past the 7-day lock, paid-only claim
89. agent/plans/PLAN-forensics-detection.md -- operator /ask 2026-11-23 (#772cfd55), program agent/programs/breach-forensics: Go-native offline detectors on machine and server (WASM), SIMD dispatch, signed model bundles on data.rediacc.com
90. agent/plans/PLAN-forensics-investigation.md -- operator /ask 2026-11-23 (#772cfd55), program agent/programs/breach-forensics: incident timeline, Verify evidence, Declare incident with deadline clocks, step-up access, Ask AI, rdc incident/forensics verbs
91. agent/plans/PLAN-forensics-alerts-notices.md -- operator /ask 2026-11-23 (#772cfd55), program agent/programs/breach-forensics: anomaly notices with offline delivery, Rediacc security-incident notices, security contact, security.txt, CRA intake
92. agent/plans/PLAN-forensics-reports.md -- operator /ask 2026-11-23 (#772cfd55), program agent/programs/breach-forensics: staged signed incident reports as PDF, JSON and STIX with QR verify and the regulatory field map
93. agent/plans/PLAN-forensics-docs-legal.md -- operator /ask 2026-11-23 (#772cfd55), program agent/programs/breach-forensics: forensics docs and the corrected legal and marketing wording, last step of the program
94. agent/plans/PLAN-unlimited-writers.md -- operator ruling #3ca908ee 2026-11-23: remove the writer cap, the lease tree cap and every refusal and doc line built on them, at every effort level
95. agent/plans/PLAN-writers-now-cadence.md -- operator ruling #ac2de21f 2026-11-23: hourly /writers-now enforced at effort high, self-review seeds before each repeat round, stuck shell-waiting agents caught
96. agent/plans/PLAN-armed-actions.md -- operator order 2026-11-24 (agent/ace763dd/order-armed-actions.md): a held item carries its trigger and prepared brief, armed-action-due starts it when the trigger fires, and the survey arms every blocked box
97. agent/plans/PLAN-drain-throughput.md -- operator 2026-11-25 (#ff417210): speedup plan from the drain consult; P1 load-reducing; measure the 3-minute writer stalls, cheaper lease verification, reviews and landing inside the loop, live runners every round; re-measure after the WSL2 to Linux move
98. agent/plans/PLAN-native-host-rdc-feedback.md -- operator 2026-11-25: restore rdc feedback and native-host fixes; libsecret with keyring fallback, VS Code, disk temp, credsStore removal
99. agent/plans/PLAN-host-temp-disposal.md -- operator rulings ASKED:2026-11-26T09:17Z and 09:19Z (request relayed by session developer-09, #0dd9a99d): grace 30 minutes, temp on disk with every leak fixed at its source, hooks-only sweep that deletes after grace and reports what it removed; P1 for SSD wear (755 GB written in 18 h) and /tmp inode exhaustion.
100. agent/plans/PLAN-cf-token-hardening.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
101. agent/plans/PLAN-nightly-green.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
102. agent/plans/PLAN-backup-schedule-origin-guard.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
103. agent/plans/PLAN-release-credits-compliance.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
104. agent/plans/PLAN-reggate-debt-collection.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
105. agent/plans/PLAN-retire-nightlies-and-mentions.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
106. agent/plans/PLAN-renet-i18n-baseline-drain.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
107. agent/plans/PLAN-datastore-migrate-correctness.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
108. agent/plans/PLAN-backup-toc-exact-opt-in.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
109. agent/plans/PLAN-vscode-browser-exposure.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
110. agent/plans/PLAN-release-notes.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
111. agent/plans/PLAN-pr-path-ephemeral-credentials.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
112. agent/plans/PLAN-plan-verbs.md -- operator /ask ASKED:2026-11-27T05:35Z: promoted from Generated to feed writers-now
113. agent/plans/PLAN-windows-lane.md -- operator instruction relayed by console-6c 2026-11-27: promote and implement
114. agent/plans/PLAN-config-sealed-local.md -- operator /ask ASKED:2026-11-27 (four decisions in the plan header): seal remote-enabled local configs by default
115. agent/plans/PLAN-proxied-licence-tunnel-auth-fix.md -- finding fix from bench runner pass r89 (#4222addb): proxied repo create, fork and licence retire refused by the executor egress
116. agent/plans/PLAN-executor-account-routes.md -- operator /ask ASKED:2026-11-27T09:21Z ("promote as approved"): one shared executor account-route table; folds PL1-PL3 licence routes in
117. agent/plans/PLAN-pricing-plan-model.md -- operator /ask 2026-11-27 in session e08d0be9 (plans written first, then promoted in QUEUE.md; "plans will be promoted and approved"): pricing redesign, first plan: per-licence prices from the catalog, CPU ceilings, user and repository caps, COMMUNITY floor without hosted R2, one effective-limit resolver
118. agent/plans/PLAN-pricing-partner-directory.md -- operator /ask 2026-11-27 in session e08d0be9 (plans written first, then promoted in QUEUE.md; "plans will be promoted and approved"): pricing redesign: opt-in public Find-a-partner directory at launch and the /partners value page
119. agent/plans/PLAN-pricing-seat-repo-caps.md -- operator /ask 2026-11-27 in session e08d0be9 (plans written first, then promoted in QUEUE.md; "plans will be promoted and approved"): pricing redesign: member and original-repository caps enforced; Depends-On PLAN-pricing-plan-model.md
120. agent/plans/PLAN-pricing-cpu-ceiling.md -- operator /ask 2026-11-27 in session e08d0be9 (plans written first, then promoted in QUEUE.md; "plans will be promoted and approved"): pricing redesign: logical-CPU ceiling per machine with 30-day grace and large-machine passes; Depends-On PLAN-pricing-plan-model.md
121. agent/plans/PLAN-pricing-free-professional.md -- operator /ask 2026-11-27 in session e08d0be9 (plans written first, then promoted in QUEUE.md; "plans will be promoted and approved"): pricing redesign: self-attested free Professional, startup programme, upgrade popups; Depends-On plan-model and seat-repo-caps
122. agent/plans/PLAN-pricing-billing-upgrade.md -- operator /ask 2026-11-27 in session e08d0be9 (plans written first, then promoted in QUEUE.md; "plans will be promoted and approved"): pricing redesign: billing profile with VIES, instant upgrade, manual invoice 14+7 days, root-token controls, 30-day R2 restore-only; Depends-On plan-model and PLAN-stripe-disable.md
123. agent/plans/PLAN-pricing-coupons.md -- operator /ask 2026-11-27 in session e08d0be9 (plans written first, then promoted in QUEUE.md; "plans will be promoted and approved"): pricing redesign: coupon campaigns with stacking boosts, managed from admin UI and root API tokens; Depends-On plan-model and billing-upgrade
124. agent/plans/PLAN-pricing-public-calculator.md -- operator /ask 2026-11-27 in session e08d0be9 (plans written first, then promoted in QUEUE.md; "plans will be promoted and approved"): pricing redesign: server-only estimate and non-binding quote API, partner lead routing, pricing page with Custom tier and VAT toggle; Depends-On plan-model and partner-directory
125. agent/plans/PLAN-account-api-health.md -- operator 2026-11-28 (ASKED:2026-11-28T10:44Z and 10:49Z; order ~10:55Z: promote all four and implement in parallel) after the account API outage of the 07:13Z edge release
126. agent/plans/PLAN-cloud-inventory.md -- pulled in as an unfinished prerequisite of PLAN-preprod-simulation.md (Depends-On), 2026-11-28
127. agent/plans/PLAN-preprod-simulation.md -- operator 2026-11-28 (ASKED:2026-11-28T10:44Z and 10:49Z; order ~10:55Z: promote all four and implement in parallel) after the account API outage of the 07:13Z edge release
128. agent/plans/PLAN-ciquick-gate-contract.md -- operator 2026-11-28 (ASKED:2026-11-28T10:44Z and 10:49Z; order ~10:55Z: promote all four and implement in parallel) after the account API outage of the 07:13Z edge release

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-agent-tree-lifecycle.md -- P1, mostly-done, in progress (6 of 7 boxes ticked)
2. agent/plans/PLAN-haiku-model-routing.md -- P1, executing, in progress (11 of 20 boxes ticked)
3. agent/plans/PLAN-canary-on-clusters.md -- P2, proposed, in progress (1 of 8 boxes ticked)
4. agent/plans/PLAN-cluster-crosssite-transport.md -- P2, proposed, in progress (1 of 7 boxes ticked)
5. agent/plans/PLAN-cluster-live-proofs.md -- P2, proposed, in progress (1 of 16 boxes ticked)
6. agent/plans/PLAN-csi-staging-redesign.md -- P2, proposed, in progress (1 of 12 boxes ticked)
7. agent/plans/PLAN-first-release-checks.md -- P2, approved, in progress (1 of 30 boxes ticked)
8. agent/plans/PLAN-kubelet-cgroup-rediacc-slice.md -- P2, proposed, in progress (1 of 8 boxes ticked)
9. agent/plans/PLAN-legal-wording-consistency.md -- P2, draft, in progress (8 of 10 boxes ticked)
10. agent/plans/PLAN-stop-hook-retro-20261125.md -- P2, ready, in progress (4 of 6 boxes ticked)
11. agent/plans/PLAN-elite-to-onprem-rename.md -- P3, proposed, in progress (1 of 19 boxes ticked), dep-blocked
12. agent/plans/PLAN-family-loop-migrate.md -- P3, proposed, in progress (1 of 10 boxes ticked), dep-blocked
13. agent/plans/PLAN-zot-manifest-list-commit.md -- P3, proposed, in progress (1 of 9 boxes ticked), dep-blocked
14. agent/plans/PLAN-console-private.md -- P1, proposed, not started
15. agent/plans/PLAN-fix-upgrade-drills-flat-daemon-bringup.md -- P1, executing, not started
16. agent/plans/PLAN-stop-hook-retro-20261117.md -- P1, ready, not started
17. agent/plans/PLAN-terms-region-notice.md -- P1, proposed, not started
18. agent/plans/PLAN-ghcr-registry-cleanup.md -- P2, proposed, not started
19. agent/plans/PLAN-multicluster-local-suite.md -- P2, proposed, not started, dep-blocked
20. agent/plans/PLAN-portal-analytics.md -- P2, proposed, not started
21. agent/plans/PLAN-stop-hook-retro-20261122.md -- P2, ready, not started
22. agent/plans/PLAN-tutorial-recorder-licence.md -- P2, proposed, not started
23. agent/plans/PLAN-www-funnel-truthfulness.md -- P2, proposed, not started
24. agent/plans/PLAN-cncf-conformance.md -- P3, approved, not started
25. agent/plans/PLAN-partner-sales-track.md -- P3, proposed, not started
26. agent/plans/PLAN-release-path-protection-2027.md -- P3, approved, not started
27. agent/plans/PLAN-stripe-removal.md -- P3, active, not started, dep-blocked
28. agent/plans/PLAN-tutorial-rerecord.md -- P3, proposed, not started, dep-blocked
<!-- queue:generated:end -->

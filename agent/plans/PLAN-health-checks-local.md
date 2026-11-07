# PLAN: health checks move local and fix what they safely can: the Stop hook, CI gates and one off-box Cloudflare alerter replace the scheduled GitHub pings; every repo gets Rediaccfile `health()` and `repair()` functions, `rdc machine health` folds in repo health and coded findings, `rdc machine repair` applies the auto-safe fixes, hostinger's checks live in its own repos, and its current warnings are cleared

Status: approved -- operator rulings 2026-11-06 (ten, plus A to D and E1 to E4 of the same day, recorded under "Operator rulings"); every design choice below that the rulings left open carries a stated default and a reason
Owner: d778be9d
Priority: P1 -- a red outside the PR head reaches nobody between sessions, and a red seen inside a session is reported instead of fixed. Hostinger's datastore is at 86% with one repo at 99%, and 20 renet processes run a deleted binary. `*.rediacc.io` and 29 single-host certificates (due 2026-12-03..14) failed renewal from 2026-11-04 until the DNS fix of 2026-11-06, and the renewal is not yet confirmed. The nightly has been red 7 of the last 8 scheduled runs on reds that a PR could have caught
Depends-On: no-dep -- every code box is inside this plan; box K6 records the first result that closes box K10 of agent/plans/PLAN-backup-program.md; telemetry-probe.yml (PLAN-telemetry-export T16, ticked) and cf-usage-report.yml (PLAN-cloudflare-spend-guard T6, ticked) are removed here only after their replacement is verified (R1, R2)
Concurrency: parallel -- nine writers (W, L, C, G, X, N, D, K, R) with disjoint Owns, plus lead-only live queues H (hostinger) and S (demo-stackoverflow); order in "Writer split and order". The wire shapes (D-record, D-ingest, D-repohealth, D-remedy) are fixed in Design so W, L, G and X do not wait on each other to compile
Owns: agent/plans/PLAN-health-checks-local.md, .ci/config/ops-health.json, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json, .ci/config/ci-alerts.json, .ci/config/proof-tiers.json, .ci/config/shards/test-e2e-workers.json, workers/ops-health/**, .ci/rediacc_ci/ops/ops_health.py, .ci/rediacc_ci/ops/deploy_ops_health.py, .ci/rediacc_ci/tests/test_ops_health*.py, .ci/scripts/quality/check_ops_health.py, .claude/hooks/stop/wl_opshealth.py, .claude/hooks/stop/test-opshealth.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_schedred.py, .claude/hooks/stop/worklist_messages.py, .claude/config/effort.json, packages/shared/src/services/machine/parsing-health.ts, packages/shared/src/services/machine/__tests__/parsing-health.test.ts, packages/shared/src/services/machine/findings.ts, packages/shared/src/services/machine/__tests__/findings.test.ts, packages/shared/src/renet-contract/data/functions.schema.ts, packages/shared/src/renet-contract/data/functions.generated.ts, packages/shared/src/renet-contract/data/list-types.generated.ts, packages/cli/src/commands/repo-health.ts, packages/cli/src/commands/repo-repair.ts, packages/cli/src/commands/repo.ts, packages/cli/src/commands/__tests__/repo-health.test.ts, packages/cli/src/commands/__tests__/repo-repair.test.ts, packages/cli/src/commands/machine/health.ts, packages/cli/src/commands/machine/repair.ts, packages/cli/src/commands/machine/index.ts, packages/cli/src/commands/machine/__tests__/health*.test.ts, packages/cli/src/commands/machine/__tests__/repair*.test.ts, packages/cli/src/commands/machine/restart-services.ts, packages/cli/src/commands/machine/__tests__/restart-services*.test.ts, packages/cli/src/services/renet/renet-daemons.ts, packages/cli/src/i18n/locales/*/cli.json, private/renet/cmd/renet/daemons_upgrade*.go, private/renet, packages/www/src/content/docs/en/monitoring.md, packages/www/src/content/docs/en/services.md, packages/www/src/content/docs/en/cli-application.md, scripts/gates/check-quality-complete.ts, .ci/rediacc_ci/tests/test_core_toolchain.py, .ci/rediacc_ci/tests/gates/test_gate_workflow_env_shell_vars.py, .ci/rediacc_ci/ci/ci_diagnose.py, .ci/rediacc_ci/tests/test_ci_diagnose.py, .ci/rediacc_ci/release/drift_job.py, .ci/rediacc_ci/release/check_soak_period.py, .ci/rediacc_ci/release/nightly_tested_edge.py, .ci/rediacc_ci/tests/test_release_*.py, .ci/rediacc_ci/security/ci_workflow_invariants.py, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, package.json, .github/workflows/ci-drift.yml, .github/workflows/ci.yml, .github/workflows/ci-ops-test.yml, .github/workflows/ci-quality.yml, .github/workflows/ct-tests.yml, .github/workflows/ct-backup-perf.yml, .github/workflows/promote-stable.yml, .github/workflows/telemetry-probe.yml, .github/workflows/cf-usage-report.yml, .github/workflows/nightly-status.yml, .ci/scripts/ci/report-nightly-status.cjs, scripts/ci/report-budget-check.cjs, .ci/rediacc_ci/tests/gates/test_gate_nightly_status_report.py, .ci/rediacc_ci/tests/gates/test_gate_budget_check_report.py, .ci/rediacc_ci/tests/test_ci_publish_verdict.py, .ci/rediacc_ci/quality/label_inventory.py, .ci/config/prose-style-baseline.json, scripts/data/doc-registry.md, packages/e2e-tests/tests/31-backup-large-repo.test.ts, packages/e2e-tests/src/utils/backup/largeRepoBudget.ts, packages/e2e-tests/src/utils/backup/withMount.ts, packages/e2e-tests/src/utils/backup/vmEvidence.ts, packages/e2e-tests/src/utils/backup/__tests__/**, agent/ledgers/ops-health.jsonl
Live-Proof: bench, hostinger -- hostinger proves the generic health verdict (red on today's known warnings, green after the fixes), the coded findings and an auto-safe repair with its re-check, the hostinger-side `health()` functions through `rdc repo health` and `rdc machine health`, the branch renet installed after a VERIFIED vm:check, the per-repo restart cycle, the certificate renewal and the archive move. Bench proves only that the branch CLI reads the bench account (cli surface), since nothing here is account-side. The ops-health Worker is not a proof-tiers surface and is proven by its own [live] boxes in production
Epics: 09b8bdfa
Worklist: PR-TASK 09b8bdfa
Updated: 2026-11-06
First-Seen: 2026-11-06

Partial edits inside shared files are scoped in each phase's Owns: wl_checks.py (the ops-health block beside the schedred block only), wl_schedred.py (`_BLOCKS` only), worklist_messages.py (ops-health strings only), effort.json (four new keys only), the cli.json locales (restartServices.repoOption, the new `repo health`, `repo repair` and `machine repair` keys, and the machine health repo-health, certificate and finding strings only), repo.ts (the `health` and `repair` registrations only), machine/index.ts (the `repair` registration only), parsing-health.ts (C1, then G5, then X1, in that order), private/renet (gitlink), ci_workflow_invariants.py (`UPSTREAM_GATES` only), package.json (scripts `ci:drift` and the new ops-health gate (L4) only), ci-quality.yml (the ops-health step and the four lanes' gate-bind regions only), ct-tests.yml (the K10 2 GiB leg only), services.md (the lifecycle and timeout sections only), cli-application.md (regenerated only), test_ci_publish_verdict.py (the nightly-report case only), label_inventory.py (the `nightly-red` creator row only), and prose-style-baseline.json (drain only).

## Operator rulings (2026-11-06, settled)

1. The between-session alarm is AWS SES mail to the comma-separated list in the Bitwarden secret OPS_ALERT_EMAILS, sent with the existing AWS_SES_* credentials, from a runner that does not depend on hostinger and is not a scheduled GitHub ping.
2. telemetry-probe.yml and cf-usage-report.yml migrate to local checks, plus the off-box runner where a probe is outside-only. Their red keeps reaching the Stop hook, so the replacement lands before the workflows are removed.
3. nightly-status.yml and .ci/config/ci-alerts.json are retired.
4. housekeeping.yml keeps all five jobs unchanged.
5. pins-soaked, promote-stable, ci-obs-mirror and ci-vm-bake stay scheduled.
6. ci.yml's nightly is split and tightened: tree-only reds are fixed so PR CI and local gates catch them; the clock-based drift lookups become one cheap daily job that blocks the Stop hook and mails the operator; the 5-OS stock-image fleet moves to weekly; promote-stable's soak re-points to the daily job plus the last weekly fleet run.
7. ct-backup-perf.yml: fix the harness, add a 2 GiB variant to vm:check and to PR CI, move the 50 GiB run to weekly, and seed 20 GiB until K10 records a first result.
8. The hostinger health check fails on warnings and covers every repo plus the mail service; inside-SSH checks run from the local side, outside-only checks run from the off-box runner too. (Amended by A and B: the per-repo and mail checks are each repo's own `health()`, read locally through `rdc machine health`.)
9. Hostinger fixes: prune only anonymous dangling volumes and unused images in four named repos; list named dangling volumes for the operator; keep mail:pre-dms17 until 2026-11-13; move demo-stackoverflow's 371 archives to the public bucket rediacc-public-data at https://data.rediacc.com/stackexchange/; install the branch renet after a VERIFIED fleet run and restart the repos one at a time, observability last and only when free, mail in a quiet window (default 03:00 Europe/Istanbul, 00:00 UTC).
10. The roundcube.rediacc.io wildcard certificate (expiry 2026-12-05) is surfaced. (Root cause and remedy in D, E2 and F17.)

A. The console repo is public, so hostinger's internal checks stay on hostinger. Each repo's Rediaccfile gains a `health()` function next to `up()`, `down()` and `info()`. Console gets only generic product tooling: renet runs `health()` with the same sourcing, privilege and timeout model as the other lifecycle functions; a new `rdc repo health <ref>` returns its exit code (0 ok, 1 warning, 2 error, the convention of `rdc machine health`, packages/cli/src/commands/machine/health.ts:27-31); `rdc machine health` also runs every mounted repo's `health()` and folds the worst code in. A repo without `health()` is "no check", never green-by-error; a `health()` timeout or crash is an error. The function is documented in services.md and the verbs in the CLI docs, with i18n keys in all CLI locales.
B. A dedicated repo on hostinger (not in this git tree, named by E1) holds the cross-repo checks as its own `health()`: TLS expiry for all served hosts, the SMTP banner, DNSBL for the machine IP, and the alert target list as plain files in that repo. Per-repo service checks live in each repo's own `health()` (mail: Postfix queue size and age, ClamAV daily.cld age, volume free space; demo-stackoverflow: disk). These scripts are written on hostinger and recorded here by what they check and their exit codes, not by their content. The repo joins the hostinger backup schedule.
C. The off-box alerter stays a generic Cloudflare Worker plus SES mail to OPS_ALERT_EMAILS, with no D1. The Worker's code and probe kinds (tls, banner-465, https, health-endpoint, dnsbl-over-DoH) carry no hostinger names; .ci/config/ops-health.json holds generic thresholds only, with no hostinger host names or IPs. (How targets reach the Worker and where its state lives: amended by E4.)
D. The H1 prune (F16) and the certificate root-cause fix (F17) are done and recorded as findings. H3 becomes the confirmation of the renewal. A generic product box covers the renet proxy's exposure to the same CNAME class for any customer, plus a certificate-expiry dimension in the generic checks so a failing renewal is seen 21 or more days ahead.

Rulings and corrections of 2026-11-06 via /ask:

E1. The dedicated hostinger repo is named `ops`.
E2. The wildcard DNS change (A 72.61.137.225 plus AAAA in place of the CNAME) is kept and recorded as a fact (F17); it is not reverted.
E3. A warning alone is not enough: errors that have a safe fix are fixed automatically. A remediation layer sits next to the health layer, generic in console. Every check that can fail carries a machine-readable finding code and, where a safe automatic fix exists, a fix action. Machine and product fixes live in renet and the CLI; repo fixes run as a Rediaccfile `repair()` next to `health()`. Fixes are idempotent and logged, and refuse anything data-destructive without an explicit flag. The safety classes are auto-safe (restart a stuck service, trim, renew a certificate, rotate logs, clear a stale lock), auto-with-backup (needs a snapshot first), and operator-only (deletes data, spends money). The off-box Worker never fixes anything; it only alerts. The local side (the Stop hook check and the ops refresher) runs the auto-safe fixes it is allowed and re-checks, so a session that sees a red fixes it instead of reporting it. For the ACME collision, the renet proxy detects a `_acme-challenge.<domain>` CNAME shared by several certificate domains and fixes it automatically, keeping deliberate delegation through an explicit opt-out. Today's hostinger warnings are swept into this model as examples (D-remedy). No prune or remediation may touch hub-owned volumes.
E4. The `ops` repo is an ordinary rediacc repo. Its backups go to the existing backup store through the existing schedule and strategy, like every other repo; there is no new R2 bucket for it, and it publishes nothing. Its plain files hold the alert target list, and its own `health()` is the primary check. The off-box Worker remains, so that a hostinger outage is reported from somewhere that does not depend on hostinger. Its targets reach it at deploy time: `deploy_ops_health` reads the target file out of the `ops` repo from the lead's machine and passes it to the Worker, and re-running the deploy is how a target change reaches the Worker. Its small alert state lives in the Worker's own storage (a single Durable Object or Workers KV; D-runner picks one), with no D1 and no new bucket. `/v1/status` and `/v1/ingest` stay.

## Findings as verified (2026-11-06)

- F1. wl_schedred discovers every workflow with a `schedule:` from the files (.claude/hooks/stop/wl_schedred.py:107), shares one cache with a 900 s TTL (:36), picks one owning session through an O_EXCL claim file, and never raises; it is wired at .claude/hooks/stop/wl_checks.py:4976-5030 under the effort key `scheduled-red` (`{block: high, advise: low}`). A new scheduled workflow (the drift job) is watched the day it lands, with no edit. A removed workflow simply stops being watched.
- F2. The FLOOR set is sealed in .claude/hooks/stop/wl_floor.py:13-28. New checks are non-floor keys in .claude/config/effort.json `checks`, each exactly once, enforced by `check_plan_record.py --effort-table` (.ci/scripts/quality/check_plan_record.py:1598).
- F3. `rdc machine health` already folds container health, service restart loops, backup staleness, verify failures and the stale-binary list into one exit code (packages/cli/src/commands/machine/health.ts:240-277; packages/shared/src/services/machine/parsing-health.ts:468-510). It does NOT judge per-repo filesystem usage, although `RepositoryInfo.disk_space.use_percent` is already in the listing (packages/shared/src/renet-contract/data/list-types.generated.ts:132-161). That is why demo-stackoverflow at 99% raised no issue. A container in a `Restarting` loop is not judged either: `checkServices` (:209-233) looks at systemd units only. An absent `backup_coverage` is silent by design (:346). Its issues are free-text strings with no code (packages/cli/src/commands/machine/health.ts:171-180), so no tool can act on them.
- F4. `rdc repo status` has no verdict exit code (packages/cli/src/commands/repo.ts:314-370); it prints the record. It stays that way; the verdict is the new `rdc repo health` (D-repohealth).
- F5. Installing a new renet runs `renet daemons upgrade --json` on every binary update (packages/cli/src/services/renet/renet-provisioner.ts:557-573, packages/cli/src/services/renet/renet-daemons.ts:228-247): a rolling restart of the router and of the non-docker daemons, at install time. The per-repo `rediacc-docker-N` supervisors restart only with `--include-docker`, and `machine restart-services` has no per-repo scope (packages/cli/src/commands/machine/restart-services.ts:109-113; private/renet/cmd/renet/daemons_upgrade.go:297-307). So a health read without REDIACC_NO_PROVISION=1 installs renet and restarts daemons as a side effect, and ruling 9's one-repo-at-a-time order needs a new `--repo` scope.
- F6. The live check `renet-live` expects `stale_binary == []` after provisioning (.ci/config/proof-tiers.json tiers.live.checks.renet-live). On hostinger it can only pass AFTER the restart cycle, not right after the install. The registry's hostinger target uses config `eu-bench` (tiers.live.targets.hostinger.config); ruling 8 names `eu-remote`. H0 confirms that both configs resolve to the same machine.
- F7. housekeeping's budget-check requires `loadMentions`, `withMentions` and the issue constants from .ci/scripts/ci/report-nightly-status.cjs (scripts/ci/report-budget-check.cjs:12-18), and its @mention list is .ci/config/ci-alerts.json. Deleting either file as part of ruling 3 would break or silence a housekeeping job that ruling 4 keeps unchanged. Decision in D-alerts.
- F8. The pytest FileExistsError on '/bin/grub-ntldr-img' is fixed on this branch by 28bcafd50 (`path_farm_without`, .ci/rediacc_ci/tests/wkloader.py:50-70), which is not yet on main; a control already exists (.ci/rediacc_ci/tests/test_core_local_common.py:503). Only proof on PR CI remains.
- F9. The shim test asserts exactly six MISMATCH rows from the runner's real PATH (.ci/rediacc_ci/tests/test_core_toolchain.py:1141, :1187), so its count depends on which pinned tools the runner image happens to carry.
- F10. Shard receipts prints `OPEN DECISION` for UNDECIDED_LANES (scripts/gates/check-quality-complete.ts:498, :746-760): ci-quick, quality-account, quality-go, quality-packages.
- F11. ci_diagnose classifies a successful Bitwarden retry note as `bitwarden-5xx` in at least one shape that the existing exclusion (.ci/rediacc_ci/tests/test_ci_diagnose.py:511, :571) does not cover: run 42182422300's Security job, where the exit 1 came from `npm audit`.
- F12. OPS Provision passes `CHOWN_PATH: ${{ runner.temp }}/renet` (.github/workflows/ci-ops-test.yml:299) and has failed on every scheduled run since 11-05 with "cannot access '/home/runner/work/_temp/renet'"; the directory is created only on paths that the schedule does not take (hypothesis Y5).
- F13. ct-backup-perf has never been green. The worker VM stops answering SSH 6-12 GiB into the seed, and `withMount`'s `finally` asserts on the unmount, replacing the real error (packages/e2e-tests/tests/31-backup-large-repo.test.ts:147-166). The seed loop has no per-file guard (:200-209). The job sets no VM_RAM_WORKER, while ct-tests uses 2560 MB (.github/workflows/ct-tests.yml:846). `K10_SEED_GB` already sizes everything (:54-63). vm:check already has a `backup` area (proof-tiers.json tiers.vm.areas.backup) with a receipt leg and no `external` leg.
- F14. The SES transport is plain fetch plus SigV4 (private/account/src/services/email-transports/ses.ts, private/account/src/utils/aws-sigv4.ts), so it is usable from a Worker. OPS_ALERT_EMAILS exists in Bitwarden (created 2026-11-06) but is not yet in .ci/config/bws-secret-map.json.
- F15. Cloudflare's own billing-usage alert policies already mail the operator between sessions (.ci/rediacc_ci/ops/cf_notifications.py), so cf_usage_report needs no off-box twin.
- F16. (lead, 2026-11-06, done; replaces box H1) The leftover prune ran: 24.6 GB freed inside miscellaneous, erpnext, nextcloud, gitlab and demo-stackoverflow (.vscode-server), and `rdc repo trim` on nine repos exited 0, but the datastore stayed at 316G used (86%): the bulk is demo-stackoverflow's archives (S). The one named dangling volume left, rediacc-hub-home-muhammed-vscode (7.05 GB, miscellaneous), is a hub user's home (F21) and is never pruned. mail and mail:pre-dms17 were not touched.
- F17. (lead, 2026-11-06, root cause fixed and kept per E2; confirmation is H3) The wildcard record `*.rediacc.io` was a CNAME to www.rediacc.io, so every `_acme-challenge.<host>.rediacc.io` resolved to www, and Traefik's lego, which follows CNAMEs for DNS-01, wrote every challenge TXT at one name. Renewals of `*.rediacc.io` and of 29 single-host certificates (due 2026-12-03..14) failed from 2026-11-04. On 2026-11-06 the wildcard became A 72.61.137.225 plus AAAA, www's addresses, and it stays that way. Traefik retries daily around 07:54 UTC. The earliest expiry, 2026-12-03, crosses a 21-day threshold on 2026-11-12.
- F18. renet already runs `health()`, but as a deploy gate, not a monitor. `renet repository health` (private/renet/cmd/renet/repository_health.go:10-15; function `repository_health`, private/renet/pkg/functions/commands/repository.go:521) dispatches to `DockerRuntime.Health` (private/renet/pkg/reporuntime/docker.go:299-336). There, exit 0 is healthy, 75 warming, 42 "not defined", and any other non-zero exit unhealthy; when no file defines `health()` it falls back to the drift registry, which answers healthy whenever containers exist (green-by-default); and a 30 s per-attempt timer turns a hang into "warming" (:342-366). The timer abandons the process: `functionTimeout` bounds only up() and down() (private/renet/pkg/orchestration/rediaccfile.go:289-308; private/renet/pkg/orchestration/procgroup.go:85-107), so a hung `health()` keeps running with no process-group kill. No CLI command calls `repository_health` today; it is only listed as read-only (packages/cli/src/services/executor/renet-function-access.ts:99). The docs disagree with each other: services.md says a Rediaccfile holds "up to two functions" (packages/www/src/content/docs/en/services.md:31), while packages/www/src/content/docs/en/rules-of-rediacc.md:20-22 names an optional `info()`; neither documents `health()`.
- F19. The renet proxy issues certificates through Traefik's ACME resolver with Cloudflare DNS-01 and the CF_DNS_API_TOKEN it already holds (private/renet/proxy/docker-compose.yml:14, :59-60). lego follows CNAMEs on `_acme-challenge.<domain>` by default, so any customer whose wildcard record is a CNAME hits F17's failure. CNAME delegation is also a deliberate pattern documented in the tree (workers/mta-sts/src/index.ts:20-21), where the target is another `_acme-challenge.` name. renet can already parse the proxy's acme.json into certificates (private/renet/pkg/certexport/acme.go:86). A DNS wildcard matches only names that do not exist, so an explicit record at `_acme-challenge.<host>` takes that name out of the wildcard's reach.
- F20. The Worker cannot read the target file out of the `ops` repo's backups: backups are encrypted, content-addressed chunks, and the repo key never leaves the machine. So the target file reaches the Worker at deploy time, read from the live repo by the lead's machine (E4).
- F21. renet's hub owns the named volumes `rediacc-hub-home-<hub user>-<container user>` (`homeVolumeName`, private/renet/pkg/hub/containers.go:736-738). They are created implicitly by a volume mount, with no label (:787-793), so once the user's container is gone a hub home looks exactly like any named dangling volume. Hub user containers carry the label `rediacc.hub.user` (:46, :303-307). renet's Docker reclaim prunes stopped containers with no filter (private/renet/pkg/prune/docker.go:138), which removes stopped persistent hub containers. With `--docker-volumes` it prunes volumes with an empty filter (:113), so a hub home survives today only because the Docker API's default spares named volumes, not because renet excludes it. Prune and repair logic must recognise hub-owned containers and volumes, by label and by the name prefix, and exclude them.
- F22. Workers in this tree already use SQLite-backed Durable Objects with migrations (workers/proxy/wrangler.template.toml:57-74), so a Durable Object adds no new deploy pattern.

## Design

### D-runner. Where the off-box alerter lives (rulings 1, C and E4)

The `ops` repo's own `health()` is the primary check (B, E4). The Worker is the outside view: it reports a hostinger outage, which no check that runs on hostinger can report.

Recommended: a new Cloudflare Worker `ops-health` (workers/ops-health/) with a cron trigger every 10 minutes, one SQLite-backed Durable Object `OpsState` (a single instance, `idFromName("state")`) for its alert state, the custom domain `ops-health.rediacc.com` (custom-domain route, same pattern as workers/mta-sts/wrangler.toml), and SES mail through the existing SigV4 transport. No D1 and no bucket.

Storage choice: a single Durable Object, not Workers KV. Reason: the dedupe is a read-modify-write (consecutive counts, last-mailed times), and cron runs and ingest POSTs can overlap. A Durable Object gives strongly consistent storage with serialized access, so the cron run and the ingest never race. KV is eventually consistent (a read may lag a write by up to 60 s) and has no atomic update, so two overlapping runs could double-mail or lose a transition. The pattern is already in the tree (F22).

Targets: `deploy_ops_health` reads the `ops` repo's target file from the lead's machine (`rdc term connect <ops ref> -c 'cat <target file>'`, the repo ref and config given as required arguments, never defaults in code). It validates the schema and puts the file over stdin as the Worker secret OPS_HEALTH_TARGETS, with its sha256 as the var OPS_HEALTH_TARGETS_SHA. A secret is the default, not a plain var, so hostinger's host names and IP stay out of the tree and out of the dashboard's plain settings. Re-running the deploy is how a target change reaches the Worker. Its code is generic: probe kinds `tls`, `banner-465`, `https`, `health-endpoint` and `dnsbl-over-DoH`. Every hostinger target comes from OPS_HEALTH_TARGETS. The only build-time targets are the account and proxy `/health` endpoints already public in regions.json. The Worker never fixes anything (E3).

Alternatives weighed:
- AWS Lambda with EventBridge Scheduler: full TLS peer-certificate access and native SES, but no IaC or credentials for it exist in the tree or in Bitwarden (the SES keys are send-only), and port 25 egress is restricted there too.
- A second VPS: full capability, but a new machine to patch and pay for, and it can itself fall silent unnoticed.
- Grafana alerting on hostinger: excluded by ruling 1.
- A scheduled GitHub job: excluded by ruling 1.

Known Worker limits, each settled by W0 before anything is built on it:
- (a) Cloudflare blocks outbound TCP to port 25 from `connect()`. The off-box SMTP check therefore reads the 220 banner on 465 after the implicit TLS handshake. The :25 banner is read from inside hostinger by the `ops` repo's `health()`.
- (b) `connect()` does not expose the peer certificate. A successful `secureTransport: "on"` handshake proves the served chain is valid now. Days to expiry come from Certificate Transparency (certspotter issuances API, crt.sh as a fallback), and an unreadable CT source is `unknown`, never green. Because CT shows the newest issuance, a failed renewal shows as falling days, so the 21-day threshold sees F17's class from outside.
- (c) DNSBL lookups go over DNS-over-HTTPS. Spamhaus answers 127.255.255.x to public resolvers, which is `unknown`, so zen is queried only when an optional SPAMHAUS_DQS_KEY exists.

Who watches the watcher: the Stop hook reds when the state's `last_cron_at` is older than 30 minutes. The Worker mails a Monday 06:00 UTC digest, so a missing Monday mail tells the operator the alerter is dead.

### D-record. The Worker's state (one shape, read by the Stop hook, the CI gate and the mail)

The `OpsState` Durable Object keeps three keys, and every read or write goes through it:
- `alerts`: `{last_cron_at, probes: {<id>: {state, since, checked_at, consecutive, detail, last_mailed_at}}, mail_log: [the last 50 of {at, kind, probes, message_id}]}`.
- `ingest`: `{<source>: {state, at, detail}}`.
- `targets`: `{sha, probe_count, loaded_at}` from the deployed OPS_HEALTH_TARGETS. A missing or unparseable secret is the probe `targets` in state `unknown`, never green; an unknown kind is an `unknown` probe.

Target file schema (plain JSON in the `ops` repo): `{version, probes: [{id, kind, host, port?, path?, expect?}], dnsbl: {ip, zones}}`.

`GET /v1/status` (bearer OPS_HEALTH_READ_TOKEN) answers:

```
{ "last_cron_at": iso, "targets_sha": hex, "probes": [{probe, state, since, checked_at, detail}], "ingest": [{source, state, at, detail}], "verdict": "green|red|unknown" }
```

`?mail=1` adds `mail_log`. The verdict is red when any probe is red, or when any ingest entry is red and younger than its `max_age_h` from the config.

### D-ingest. Results that reach the record from elsewhere

`POST /v1/ingest` (bearer OPS_HEALTH_INGEST_TOKEN) takes `{source, state, detail, at}`. The sources are `drift` (the daily job), `ci-weekly` (the weekly fleet run), and `local-<check>` from the local refresher, including `local-machine-<name>` per checked machine. A local verdict is posted after its auto-repair and re-check (D-remedy), so the mail reports only what is left. Every red that must reach the operator between sessions goes through one mailer and one dedupe.

### D-mail. Dedupe

A probe turns red after 2 consecutive red runs and recovers after 2 green runs. Ingest entries transition on first receipt. One mail per cron run lists every transition. A still-red probe is re-mailed at most once per 24 h. Every send is logged in `mail_log` with the SES MessageId. Recipients come from OPS_ALERT_EMAILS, split on commas and trimmed. An empty list is a setup failure, recorded as an `unknown` probe `mailer`.

### D-config. One generic config

.ci/config/ops-health.json holds only generic values, and no host names or IPs:
- TLS: warning below 21 days, red below 7 days; the transition counts (2 and 2) and the 24 h re-mail;
- the stale limits: `last_cron_at` 30 min;
- the local TTLs: machines 30 min, telemetry and portal-captcha 6 h, cf-usage 7 d, off-box read 15 min;
- the ingest `max_age_h`;
- `auto_repair`: the classes the local side may run (`["auto-safe"]`) and a limit of 3 attempts per finding code per machine per day;
- `github_mentions` (see D-alerts).

The Worker imports it at build time and Python reads it, so no threshold is written twice. Per-service thresholds (Postfix queue, ClamAV age, volume space) live in the hostinger repos' `health()` (B). The repo-disk thresholds (85 and 95) are product constants of C1.

### D-repohealth. `health()` as a product lifecycle function (ruling A)

Contract for a Rediaccfile `health()`: exit 0 ok, 1 warning, 2 error. 75 (EX_TEMPFAIL) keeps meaning "warming" for the deploy gate and counts as a warning when monitoring. 42 stays renet's reserved "not defined". Any other exit, a signal or a timeout is an error. `health()` is sourced, sandboxed and granted exactly as up() and down() are, through the same executor (`RediaccfileExecutor`).

Timeout: `health` joins `MachineFunctionTimeout` with a 30 s default (`RENET_HEALTH_TIMEOUT`, the gate's existing per-attempt budget), and `# rediacc:timeout health=<d>` raises it up to a 300 s cap. `executeFunction`'s bounded run then kills the process group on expiry (F18). The deploy gate keeps mapping a timeout to warming; monitoring maps it to error.

renet: `renet repository health --strict` is the monitoring mode: no drift-registry fallback, so a repo where no file defines `health()` answers `level: none` ("no check"). `--all` evaluates every mounted repo in one call, at most 4 at a time. `HealthReport` gains `level` (ok, warning, error, none) and `files` (`[{file, exit, level, detail}]`); `state` is unchanged, so the deploy-gate caller keeps working. Without `--strict` the behaviour stays as today, apart from the process-group kill.

CLI:
- `rdc repo health <repo>@<machine>` runs `repository_health --strict` and exits 0, 1 or 2 per the worst file. "No check" exits 0, but prints and reports `level: none`, never "healthy". A renet failure is exit 2.
- `rdc machine health` runs `repository_health --all --strict` after its listing job and folds the worst repo level into its exit code (warning 1, error 2), with one finding per repo (`repo.health.warning` or `repo.health.error`). Repos with no check are listed in the repositories section, not as findings. When the remote renet predates `--strict`, the result is one warning (`renet.repo-health.unsupported`), so the result is never green by error. A failed repo-health job is exit 2.

### D-certs. Certificate expiry and the ACME CNAME class (rulings D and E3)

The renet listing gains a `certificates` section read from the proxy's acme.json through `certexport.ParseACME` (F19): `{main, sans, not_after, challenge_cname}`. `challenge_cname` is the end of the CNAME chain of `_acme-challenge.<name>`, resolved through the proxy's resolvers (private/renet/proxy/docker-compose.yml:60), with the leading `*.` stripped. `rdc machine health` reports `cert.expiry.near` (warning below 21 days, error below 7). Traefik renews 30 days ahead, so a certificate under 21 days means at least nine days of failed renewals.

Detection: `acme.challenge.cname-shared` fires when a certificate name's challenge chain ends at a name that does not begin with `_acme-challenge.`, or when two different names share one end. That is exactly the F17 shape.

Automatic fix (auto-safe, `renet proxy acme-fix`, run by `rdc machine repair` and at every proxy converge). Default: for each colliding name, write an explicit anchor TXT record (`rediacc-acme-anchor`) at `_acme-challenge.<name>` through the proxy's CF_DNS_API_TOKEN, which already edits that zone. Per F19, the explicit record takes the name out of the wildcard, so lego writes its challenge where it belongs. Then restart Traefik so it retries now. The fix is additive, idempotent (an existing anchor is a no-op) and needs no process-wide change. Fallback, when the DNS provider is not Cloudflare or the token cannot write the zone: set LEGO_DISABLE_CNAME_SUPPORT=true in the proxy environment, but only when no name on that proxy is a declared delegation, because the variable is process-wide; otherwise the finding stays at operator-only. Deliberate delegation is kept through an explicit opt-out: proxy setting `acme.delegated_names` (a list), whose names are never anchored and never reported. The pattern documented at workers/mta-sts/src/index.ts:20-21 is one such delegation. Default reason: the anchor fixes the colliding names only and leaves every other name's CNAME following intact; the variable is the fallback.

### D-remedy. Coded findings and the repair layer (ruling E3)

Findings: every check that can fail emits `{code, severity, subject, detail, fix?}` in a new `findings` array of the `machine health` and `repo health` JSON, next to the unchanged `issues` strings. `fix` is `{action, class, window_only}`. One table in packages/shared/src/services/machine/findings.ts maps every code to its action and class, so the CLI, the refresher and the docs read one source.

Safety classes:
- auto-safe: restart a stuck service or container, trim, prune anonymous dangling volumes and unused images, renew a certificate, rotate logs, clear a stale lock, the ACME anchor.
- auto-with-backup: runs only with `--with-backup`, after a snapshot of the affected repo through the existing reflink snapshot (`renet backup --snapshot`); a failed snapshot cancels the fix.
- operator-only: never run by any tool; printed as the exact command for the operator. Everything that deletes non-anonymous data or spends money is here.

`window_only` is an attribute on top of the class. Such a fix runs only inside the machine's maintenance window, a new rdc machine config field `maintenance_window` (`HH:MM-HH:MM UTC`); a machine without one never runs window-only fixes automatically.

Machine fixes: `rdc machine repair <m>` is a new verb, not `machine health --fix`, so health stays read-only for the Stop hook, the gate and REDIACC_NO_PROVISION reads. It reads the findings, runs the fixes its flags allow, and re-runs `machine health`. Flags: `--dry-run` (list only), `--code <c>` (repeatable), `--with-backup`, `--window-override` (window-only fixes outside the window, by hand only). Each action re-checks its finding first and does nothing when it is already gone, so a second run reports zero actions. Each action is logged to the machine journal (tag `rediacc-repair`) and in the JSON output (`actions: [{code, action, class, result, before, after}]`). Exit 0 when nothing is left, 1 when warnings or operator-only items are left, 2 when an error is left or an action failed.

Repo fixes: a Rediaccfile `repair()` lifecycle function, sourced, sandboxed and bounded like `health()` (`repair` timeout key, 5 min default, 30 min cap). It receives `REDIACC_HEALTH_LEVEL` and the `health()` output, and declares its class with `# rediacc:repair class=auto-safe|auto-with-backup [window=only]`. An undeclared `repair()` is operator-only, so nothing runs a repo's repair automatically unless the repo says it is safe. `rdc repo repair <repo>@<machine>` runs it and re-runs `health()`; `machine repair` runs it for every repo whose level is not ok and whose class it may run.

Hub exclusion (F21): every prune or reclaim action excludes containers labelled `rediacc.hub.*` and volumes labelled `rediacc.hub.user` or named `rediacc-hub-home-*`. The hub creates each home volume explicitly with the `rediacc.hub.user` label, so future homes are recognised by label; the name prefix covers the existing ones.

Local side: when `ops_health machines` finds a red machine, the refresher runs `rdc machine repair <m>` with only the classes in `auto_repair` (auto-safe), within the daily attempt limit. It then re-checks, ledgers each action and posts only the remaining verdict. The Stop hook's block message lists the remaining findings, the repair command for any auto-safe or window-only fix still due, and each operator-only item as an ask. A session that sees a red therefore runs the fix instead of reporting it.

Today's hostinger warnings in this model:

| Finding | Fix | Class |
|---|---|---|
| `datastore.usage.high` (86%) | trim, then prune anonymous dangling volumes and unused images, hub excluded | auto-safe |
| the same, residual | named volumes (rediacc-hub-home-* never) and demo-stackoverflow's archives (S) | operator-only |
| `repo.disk.high` (demo-stackoverflow 99%) | trim and anonymous prune; archive move is S | auto-safe, then operator-only |
| `renet.binary.replaced` (20 processes) | per-repo `restart-services --include-docker --repo` (C4), observability only when free | auto-safe, window-only; mail always window-only |
| `cert.expiry.near` | restart Traefik so it retries the renewal | auto-safe |
| `acme.challenge.cname-shared` | the anchor of D-certs | auto-safe |
| `container.restart-loop` | restart the container | auto-safe |
| `backup.coverage.absent` | bind a strategy | operator-only (spends storage) |
| `ops.targets.drift` (the Worker's `targets_sha` differs from the `ops` file) | re-run `deploy_ops_health` | operator-only (changes a production Worker) |

### D-verdict. The local machine verdict = exit codes, generic

`ops_health machines` checks every machine the operator's rdc config names, with no name in the tree. The configs come from `RDC_HEALTH_CONFIGS` (a comma list in the operator's environment; unset means the rdc default config), and the machines come from `rdc machine list -o json` in each config. Per machine, all under `REDIACC_NO_PROVISION=1` (F5):
1. `machine health <m> -o json`, which now folds every repo's `health()` (D-repohealth), the certificate dimension (D-certs) and the coded findings (D-remedy). Exit 1 or higher is red, so warnings fail.
2. `machine status <m> --containers --health-check`.
3. `machine status <m> --services --stability-check`.
4. From the same JSON, `backup_coverage` present for every autostart repo, and every repo's age below the stale limit.
5. On red, the auto-repair and re-check of D-remedy.

Exit 0 green, 1 red, 2 setup or unreadable. On hostinger, steps 2 and 3 are red today because of renet skew; that red is honest and clears at H4. C1 adds two checks to the shared parser, as product changes for every machine documented in monitoring.md:
- per-repo filesystem usage: `Repo <name> disk usage high/critical`, over 85 or over 95, from `disk_space.use_percent`;
- containers whose status starts `Restarting`: a restart loop, exit 3.

### D-local. The Stop hook side

wl_opshealth.py reads `.ci/cache/ops-health/state.json`, which is shared and gitignored. When a check is past its TTL, it spawns ONE detached `python3 -m rediacc_ci.ops.ops_health refresh`, claimed through O_EXCL on `.ci/cache/ops-health/refresh.lock`, with a stale lock after 20 min. The hook never waits and never raises.

The refresher:
- runs the due checks: `machines` (D-verdict, with its auto-repair), telemetry_delivery under bws profile `telemetry-probe`, portal_captcha, and cf_usage_report under profile `cf-usage-report`;
- reads the Worker's state through `/v1/status`, and, when `OPS_HEALTH_TARGETS_REF` is set in the operator's environment, compares `targets_sha` with the sha256 of that repo's target file (finding `ops.targets.drift`);
- writes the cache;
- POSTs the local verdicts to `/v1/ingest`;
- appends a row to agent/ledgers/ops-health.jsonl on a state transition and on every repair action.

Ownership reuses wl_schedred's claim helper, so one session is blocked and the others get an advisory.

Effort keys (non-floor, F2):
- `ops-health-red` `{block: smart, advise: low}`
- `ops-health-offbox-stale` `{block: high, advise: low}`
- `ops-health-unreadable` `{advise: smart}`
- `ops-health-peer` `{advise: smart}`

### D-gate. The CI side

the new ops-health gate (L4) (.ci/scripts/quality/check_ops_health.py) reads `/v1/status` and fails on a red verdict or a stale `last_cron_at`. It joins `UPSTREAM_GATES`, so it carries the external-gate guard, honours the `no-external-quality` label, falls inside the drift waiver, and runs in the daily drift job.

### D-drift. One cheap daily job

.ci/rediacc_ci/release/drift_job.py runs `DRIFT_GATE_IDS` (.ci/rediacc_ci/release/nightly_tested_edge.py:32) plus `CLOCK_GATE_IDS`, which are `check:ci-plan-housekeeping`, `check:ci-plan-folders` and `check:ci-docker-image-freshness` where not already in the drift set (Y6). It also runs the two split steps: the OBS upstream check (`rediacc_ci.infra.renet_pkg_matrix upstream --distro opensuse-16.0`) and govulncheck. It writes a per-gate verdict JSON and exits 1 on any red.

`npm run ci:drift` runs it locally. .github/workflows/ci-drift.yml (name `CI - Drift`, cron `15 2 * * *`) runs it daily and POSTs the verdict to `/v1/ingest` source `drift` under `if: always()`. wl_schedred watches it by discovery (F1).

### D-promote. The soak re-pointed (ruling 6)

promote-stable's `workflow_run` trigger moves from "Console CI" to "CI - Drift". A drift run that concluded `success` or `failure` qualifies; `cancelled` and `startup_failure` never do, and drift reds keep today's waiver, since every step of that job is drift by construction.

The test evidence becomes the newest completed scheduled Console CI run on main, which is now weekly. It qualifies when it is green or red on drift steps only, at most 8 days old. `check_soak_period` waives the soak only for an edge whose tag is contained in that run's head; anything else falls back to the 7-day soak, and the 06:00 cron is unchanged.

### D-alerts. Retiring ci-alerts.json without silencing budget-check (F7)

`loadMentions`, `withMentions`, `ISSUE_LABEL`, `ISSUE_TITLE`, `ISSUE_LABELS` and the `nightly-red` label creation move verbatim into scripts/ci/report-budget-check.cjs. Its handle list moves to `github_mentions` in .ci/config/ops-health.json, the one ops alert config. housekeeping.yml is not edited, and budget-check posts and mentions exactly as before.

## Scheduled workflows and their fate

| Workflow | Trigger today | Fate | Box |
|---|---|---|---|
| ci.yml | push, PR, cron `0 1 * * *` | schedule becomes weekly `0 1 * * 0` (the 5-OS stock-image fleet and the full union); push and PR unchanged; a schedule-only `report-schedule` job POSTs the verdict to ingest `ci-weekly` | D3 |
| ci-drift.yml (new) | none | daily `15 2 * * *`, the clock-based drift lookups; mails through ingest; promote-stable's trigger | D2 |
| ct-backup-perf.yml | daily `30 2 * * *` | weekly `30 2 * * 6`, K10_SEED_GB=20 until K10's first result, then 50 | K3, K6 |
| telemetry-probe.yml | `17 */6 * * *` | removed after L5 and W6 are verified | R1 |
| cf-usage-report.yml | `23 6 * * 1` | removed after L5 is verified (between sessions: Cloudflare billing alerts, F15) | R2 |
| nightly-status.yml | workflow_run Console CI | retired | R3 |
| housekeeping.yml | `0 3 * * *` | unchanged, all five jobs; budget-check's imports move (D-alerts) | R3 |
| promote-stable.yml | `0 6 * * *` + workflow_run Console CI | 06:00 unchanged; workflow_run re-pointed to CI - Drift; evidence is the last weekly fleet run | D4 |
| pins-soaked.yml | `30 0 * * *` + workflow_run OBS Mirror | unchanged | none |
| ci-obs-mirror.yml | `23 */6 * * *` | unchanged | none |
| ci-vm-bake.yml | `0 2 1 * *` | unchanged | none |
| obs-ceph-autobump, ci-verdict, claude-review, review-status | workflow_run | unchanged; not scheduled | none |

## Writer split and order

Phase order:
- O1 first. W, L, C, G, X, N, D and K then run in parallel. Within parsing-health.ts the order is C1, then G5, then X1.
- X2 after X1 and G4; X5 after X3 and G6. L7 after X2.
- R1 and R2 after L5 and W6 are VERIFIED. R3 after D2, D3 and W6.
- P1 after C3, C4, G1 to G6, X2 to X5 and K2.
- H0, H2, H3 and H14 (dry run, once X2 is built) any time. H9 to H11 (the hostinger scripts) any time; their acceptance through `rdc repo health` needs H4. H12 after H9. H13 after W5 and H9. H4 only after a VERIFIED P1 on the head that carries C3, C4, G1 to G6 and X2 to X5, then H5 to H8 in order. H15 after H4.
- S is independent of everything except O2's credential.

Writers and their boxes:
- Writer W (Worker): W0 to W6.
- Writer L (local checks, hook, gate): L1 to L7, after O1. L4 codes against D-record without waiting on W; L1 codes against D-repohealth's JSON without waiting on G; L7 codes against D-remedy's JSON.
- Writer C (shared parser, restart scope): C1 to C4.
- Writer G (repo `health()`, certificates): G1 to G7.
- Writer X (remediation): X1 to X6.
- Writer N (nightly tree reds): N1 to N6.
- Writer D (drift, weekly fleet, promotion): D1 to D5.
- Writer K (backup perf): K1 to K5; K6 is post-merge.
- Writer R (retirements): R1 to R3, in that order, each after its gate above.
- Lead only: O2, H, S, P and LP.

Control rule: every new test fails without its fix. The tick note records the test name and rc 1 from the tree with the fix stashed and the test kept.

## Boxes

### O: config and secrets (lead)

- [x] O1: .ci/config/ops-health.json per D-config. OPS_ALERT_EMAILS, OPS_HEALTH_READ_TOKEN, OPS_HEALTH_INGEST_TOKEN and the optional SPAMHAUS_DQS_KEY are registered in bws-secret-map.json. A bws profile `ops-health` is added to secret-supply.json (required: OPS_ALERT_EMAILS, AWS_SES_ACCESS_KEY_ID_EU, AWS_SES_SECRET_ACCESS_KEY_EU, AWS_SES_REGION_EU, AWS_SES_FROM, OPS_HEALTH_READ_TOKEN, OPS_HEALTH_INGEST_TOKEN; optional: SPAMHAUS_DQS_KEY, CF_GLOBAL_API_KEY, CF_EMAIL). The two tokens are minted by the session (`secrets.token_urlsafe(32)`) and stored with `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env store-from-env`.
  (corrected 2026-11-06, operator rulings A to E4) .ci/config/ops-health.json per D-config, with no host name or IP in it. OPS_ALERT_EMAILS, OPS_HEALTH_READ_TOKEN, OPS_HEALTH_INGEST_TOKEN and the optional SPAMHAUS_DQS_KEY are registered in bws-secret-map.json. A bws profile `ops-health` is added to secret-supply.json (required: OPS_ALERT_EMAILS, AWS_SES_ACCESS_KEY_ID_EU, AWS_SES_SECRET_ACCESS_KEY_EU, AWS_SES_REGION_EU, AWS_SES_FROM, OPS_HEALTH_READ_TOKEN, OPS_HEALTH_INGEST_TOKEN; optional: SPAMHAUS_DQS_KEY, CF_GLOBAL_API_KEY, CF_EMAIL). The two tokens are minted by the session (`secrets.token_urlsafe(32)`) and stored with `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env store-from-env`. The target list is not a Bitwarden secret: it is read from the `ops` repo at deploy time (D-runner).
  (corrected 2026-11-06, no key in the store) SPAMHAUS_DQS_KEY is mapped and named in the profile only once a key exists in the store; until then the DNSBL probe uses the public resolvers. The tokens are stored with `store-from-env --create` (ec8a3b28f), since `store-from-env` alone edits existing entries only.
  - Owns: .ci/config/ops-health.json, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json
  - CONTROL: `check:ci-secret-supply` reds on a profile that names a secret absent from the map.
  - Accept: `npm run check:ci-bws-map && npm run check:ci-secret-supply` rc 0; `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile ops-health -- true` rc 0; `git grep -nE "hostinger|rediacc\.io|72\.61\." -- .ci/config/ops-health.json` returns nothing.
    (ticked) 2026-11-06T20:47:38Z by d778be9d: commit:f93b0cd29 (+62774bd83 config, ec8a3b28f create verb); check:ci-secret-supply rc=0; check:ci-bws-map rc=0; bws_env exec --profile ops-health -- true rc=0
- [x] O2 [live]: A bucket-scoped R2 token for rediacc-public-data (Object Read & Write) is minted from the Global API Key through `cf_auth` and stored as R2_PUBLIC_DATA_ACCESS_KEY_ID and R2_PUBLIC_DATA_SECRET_ACCESS_KEY in a profile `public-data`.
  - Accept: `bws_env exec --profile public-data -- true` rc 0.
  - Record 2026-11-06 (review 78fab9ef.2): the token is bucket-scoped, measured with SigV4 list requests under `bws_env exec --profile public-data --profile deploy-workers`: `rediacc-public-data?list-type=2` HTTP 200, `rediacc-www-media?list-type=2` HTTP 403.
    (ticked) 2026-11-06T20:47:39Z by d778be9d: commit:f93b0cd29; bws_env exec --profile public-data -- true rc=0 (2 names bound)

### W: the off-box Worker (writer W)

Owns: workers/ops-health/**, .ci/rediacc_ci/ops/deploy_ops_health.py, .ci/rediacc_ci/tests/test_ops_health_deploy.py, plus the registration rows for a new worker in .ci/rediacc_ci/quality/typecheck_workers.py, .ci/rediacc_ci/quality/lockfile.py, .ci/config/syncpack-source-exclusions.json and .ci/rediacc_ci/tests/gates/test_gate_preview_worker_reaping.py (one row each).

- [x] W0: Spike on a throwaway deploy: `connect()` to port 25 is refused; a `secureTransport: "on"` connect to an expired-certificate host (expired.badssl.com:443) fails while mail.rediacc.io:465 succeeds and yields a `220` line; certspotter answers `not_after` for roundcube.rediacc.io; DoH for `225.137.61.72.zen.spamhaus.org` answers 127.255.255.x. Each result is recorded here. A different result changes D-runner before W1 starts.
  (corrected 2026-11-06, operator rulings A to E4) Spike on a throwaway deploy: `connect()` to port 25 is refused; a `secureTransport: "on"` connect to an expired-certificate host (expired.badssl.com:443) fails while mail.rediacc.io:465 succeeds and yields a `220` line; certspotter answers `not_after` for roundcube.rediacc.io; DoH for `225.137.61.72.zen.spamhaus.org` answers 127.255.255.x; a single SQLite-backed Durable Object is read and written from both the cron handler and a fetch handler. Each result is recorded here. A different result changes D-runner before W1 starts.
  - Accept: `npx wrangler dev --test-scheduled` probe script rc 0 with the five facts printed and recorded here.
  - Record 2026-11-06 (throwaway `ops-health-spike` deployed to workers.dev and deleted, `node workers/ops-health/spike/w0.mjs --deploy ...` under `bws_env exec --profile deploy-workers` rc 0): (1) connect() to :25 refused, "Connections to port 25 are prohibited"; (2a) a secureTransport connect to expired.badssl.com:443 fails; (2b) mail.rediacc.io:465 answers "220 mail.rediacc.io ESMTP"; (3) certspotter answers not_after, but the newest CT entry for the wildcard is Cloudflare's edge certificate (Google Trust Services, 2027-01-31) while the origin serves Let's Encrypt (2026-12-05), so the `tls` probe filters CT by the target's `expect` issuer (D-runner (b) as built in 62774bd83); (4) DoH for 225.137.61.72.zen.spamhaus.org answers 127.255.255.254; (5) one SQLite-backed Durable Object written by both the cron and the fetch handler, writers ["fetch","cron"]. The first run waited 150 s and saw only "fetch": a new Cron Trigger can take up to 15 minutes to propagate, and the spike now waits 16 minutes (c2dbfb7bf).
    (ticked) 2026-11-06T21:03:05Z by d778be9d: commit:c2dbfb7bf (spike 62774bd83); w0.mjs --deploy rc=0, five facts HOLDS on a real workers.dev deploy, recorded under W0
- [x] W1: Probes per D-runner: TLS handshake plus CT days for 465, 993 and roundcube 443; the 465 banner; HTTPS reachability for roundcube.rediacc.io; `/health` for every stable and edge account host and proxy host from regions.json (bundled at build); portal captcha per host, ported from rediacc_ci.ops.portal_captcha steps 1-3; DNSBL over DoH for the configured zones. Every probe returns green, red or unknown, and unknown is never folded into green.
  (corrected 2026-11-06, operator rulings A to E4) The five generic probe kinds per D-runner (`tls` handshake plus CT days, `banner-465`, `https`, `health-endpoint`, `dnsbl-over-DoH`). Targets come from the OPS_HEALTH_TARGETS secret, plus the regions.json account and proxy `/health` endpoints bundled at build. Every probe returns green, red or unknown, and unknown is never folded into green. The source carries no hostinger name or IP, and no code path changes any remote state.
  - CONTROL: unit fixtures for an expired certificate (red), CT at 20 days (red), a banner that does not match the target's `expect` (red), DNSBL 127.0.0.2 (red), DNSBL 127.255.255.254 (unknown), a target list with an unknown kind (that probe unknown), and an absent or unparseable OPS_HEALTH_TARGETS (probe `targets` unknown).
  - Accept: `cd workers/ops-health && npx vitest run && npx tsc --noEmit` rc 0, and `git grep -nE "hostinger|72\.61\." -- workers/ops-health` returns nothing.
    (ticked) 2026-11-06T20:23:49Z by d778be9d: commit:62774bd83560 landed from lease agent-a2c256ab3ae27bba9; W1 package registered, vitest 50 passed rc=0 in the lease
- [x] W2: The D1 schema, the transitions and the dedupe of D-mail, `/v1/status` and `/v1/ingest` with bearer checks.
  (corrected 2026-11-06, operator rulings A to E4) The `OpsState` Durable Object of D-record (keys `alerts`, `ingest`, `targets`), the transitions and the dedupe of D-mail, `/v1/status` and `/v1/ingest` with bearer checks.
  - CONTROL: a single red run mails nothing; a second consecutive red mails once; a third mails nothing; 24 h later it mails once; two greens mail "recovered"; a wrong bearer answers 401; an empty OPS_ALERT_EMAILS yields the `mailer` probe `unknown`; an ingest POST issued during a cron run is serialized by the object, and both writes survive.
  - Accept: same command, rc 0.
    (ticked) 2026-11-06T20:23:50Z by d778be9d: commit:62774bd83560 landed from lease agent-a2c256ab3ae27bba9; W2 five generic probes, vitest 50 passed rc=0, controls fail with fixes reverted
- [x] W3: SES send through private/account/src/utils/aws-sigv4.ts, with the subject `[rediacc ops] <n> red, <m> recovered` and the Monday digest.
  - CONTROL: a mocked SES 400 is logged with its body and leaves the transition unmailed, so the next run retries.
  - Accept: same command, rc 0.
    (ticked) 2026-11-06T20:23:51Z by d778be9d: commit:62774bd83560 landed from lease agent-a2c256ab3ae27bba9; W3 OpsState DO and SES mail, vitest 50 passed rc=0, tsc rc=0
- [x] W4: `deploy_ops_health` creates the D1 database when it is missing, applies the schema, runs `wrangler deploy`, and puts the secrets over stdin. It is idempotent, dry-run by default, and writes only with `--write`.
  (corrected 2026-11-06, operator rulings A to E4) `deploy_ops_health --targets-ref <repo>@<machine> --config <config> --targets-path <file>` (all required, no defaults in code). It reads the target file through `rdc term connect` (falling back to `rdc repo sync download` with `--remote-file`), validates the schema, applies the Durable Object migration, runs `wrangler deploy`, and puts OPS_HEALTH_TARGETS and the other secrets over stdin, with the file's sha256 as OPS_HEALTH_TARGETS_SHA. It is idempotent, dry-run by default, and writes only with `--write`.
  - CONTROL: a second `--write` run with an unchanged target file reports zero changes; an invalid target file exits 2 before any deploy; a changed file changes only the secret and the sha.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_health_deploy.py -q` rc 0.
    (ticked) 2026-11-06T20:23:52Z by d778be9d: commit:d7c95c5d06e6 landed from lease agent-a2c256ab3ae27bba9; W4 deploy_ops_health, pytest test_ops_health_deploy 27 passed rc=0
- [x] W5 [live]: Deploy to production.
  (corrected 2026-11-06, operator rulings A to E4) Deploy to production with the `ops` repo's target file (after H9).
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_ops_health --targets-ref ops@hostinger --config eu-remote --targets-path <file> --write` rc 0; after 20 min, `curl -fsS -H "Authorization: Bearer $OPS_HEALTH_READ_TOKEN" https://ops-health.rediacc.com/v1/status` rc 0 with `last_cron_at` under 11 min old, every regions.json health-endpoint probe present, and one probe per target from the file.
    (ticked) 2026-11-07T01:44:02Z by d778be9d: commit:2c2a4e39c deploy_ops_health --write rc 0 (version d25bf6a6), /v1/status rc 0 at 01:43Z: green, last_cron_at 3.4 min old, 12 regions.json health probes and one probe per target (28) from the ops repo file, targets_sha 26b90fde; check:ci-ops-health rc 0
- [ ] W6 [live]: A forced transition: `POST /v1/ingest {source:"selftest", state:"red"}`, then green. Each mail is logged with an SES MessageId, and the operator's receipt is reported back on the worklist item, without a question.
  - Accept: the two `mail_log` entries read through `/v1/status?mail=1` rc 0.

### L: local checks, Stop hook and CI gate (writer L)

Owns: .ci/rediacc_ci/ops/ops_health.py, .ci/rediacc_ci/tests/test_ops_health.py, .claude/hooks/stop/wl_opshealth.py, .claude/hooks/stop/test-opshealth.py, .claude/hooks/stop/wl_checks.py (ops-health block), .claude/hooks/stop/worklist_messages.py (ops-health strings), .claude/config/effort.json (four keys), .ci/scripts/quality/check_ops_health.py, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .ci/rediacc_ci/security/ci_workflow_invariants.py (UPSTREAM_GATES), .github/workflows/ci-quality.yml (one step), package.json (the new ops-health gate (L4)), agent/ledgers/ops-health.jsonl

- [x] L1: `ops_health hostinger` per D-verdict, with REDIACC_NO_PROVISION=1 forced inside the module (not inherited) and `--config eu-remote` as the default.
  (corrected 2026-11-06, operator rulings A to E4) `ops_health machines` per D-verdict: configs from `RDC_HEALTH_CONFIGS` (default: the rdc default config), machines from `rdc machine list -o json`, REDIACC_NO_PROVISION=1 forced inside the module (not inherited), and no machine or config name in the source.
  - CONTROL: fixtures for health rc 1 (red), health rc 2 from a repo `health()` error (red), status rc 1 (red), coverage absent for an autostart repo (red), a repo at `level: none` (not red, reported as "no check"), an empty machine list (exit 2), an SSH timeout (exit 2), and a test that the subprocess environment carries REDIACC_NO_PROVISION=1 even when the caller unset it.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_health.py -q` rc 0 and `git grep -nE "hostinger|eu-remote" -- .ci/rediacc_ci/ops/ops_health.py` returns nothing.
    (ticked) 2026-11-06T20:28:49Z by d778be9d: commit:172645373e; accept on HEAD 5989f3adec78: L1 pytest test_ops_health rc=0 (36 passed)
- [x] L2: `ops_health refresh`, `ops_health offbox` and the cache, the ledger-on-transition and the POST to ingest. telemetry_delivery, portal_captcha and cf_usage_report run unchanged as subprocesses under their bws profiles, keeping their exit-code contract (0, 1, 2).
  (corrected 2026-11-06, operator rulings A to E4) `ops_health refresh`, `ops_health offbox` and the cache, the ledger-on-transition and the POST to ingest (`local-machine-<name>` and `local-<check>`). telemetry_delivery, portal_captcha and cf_usage_report run unchanged as subprocesses under their bws profiles, keeping their exit-code contract (0, 1, 2). `offbox` reads the Worker's state through `/v1/status` and, when `OPS_HEALTH_TARGETS_REF` is set, reports `ops.targets.drift` on a sha mismatch.
  - CONTROL: an unchanged state appends no ledger row; a 1-to-0 change appends one; a failed ingest POST is recorded in the cache and does not fail the refresh; a target sha mismatch is red, with the deploy command named.
  - Accept: same pytest, rc 0.
    (ticked) 2026-11-06T20:28:50Z by d778be9d: commit:172645373e; accept on HEAD 5989f3adec78: L2 pytest test_ops_health rc=0 incl. ledger/ingest/sha-mismatch controls; fix 9ecea1c6e
- [x] L3: wl_opshealth.py and its wiring beside the schedred block (.claude/hooks/stop/wl_checks.py:4976-5030), plus the four effort keys of D-local.
  - CONTROL: the fixtures cover a red cache, where this session owns the claim and is blocked while a peer gets an advisory; a stale cache, which spawns one refresher, and two concurrent stops, which spawn one; an off-box `last_cron_at` 31 min old (`ops-health-offbox-stale`); and a cache that cannot be parsed (advisory, no raise).
  - Accept: `python3 .claude/hooks/stop/test-opshealth.py` rc 0 and `python3 .ci/scripts/quality/check_plan_record.py --effort-table` rc 0.
    (ticked) 2026-11-06T20:28:51Z by d778be9d: commit:3fe500624; accept on HEAD 5989f3adec78: L3 test-opshealth.py rc=0 (33), check_plan_record --effort-table rc=0; ladder fix 5989f3ade
- [ ] L4: the new ops-health gate (L4) per D-gate: a manifest entry, an UPSTREAM_GATES row, a ci-quality.yml step with `UPSTREAM_GATE_IF`, the secret through the bws-secrets action, and the lock regenerated.
  - CONTROL: a status fixture with one red probe exits 1; `last_cron_at` 31 min old exits 1; an unreadable status exits 2.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_health.py -q -k gate && npm run gen:gates-lock && npm run check:ci-workflow-gates && npm run check:ci-workflow-invariants` rc 0.
- [ ] L5 [live]: The first real local refresh against hostinger, Grafana and Cloudflare. hostinger-inside is red, naming exactly datastore 86%, demo-stackoverflow disk (once C1 is in), 20 replaced-binary processes, and two status rc 1 (renet skew). Telemetry, portal-captcha and cf-usage carry their real rc. The Stop hook shows `ops-health-red` in this session.
  (corrected 2026-11-06, operator rulings A to E4) The first real local refresh with `RDC_HEALTH_CONFIGS=eu-remote` in the lead's environment, plus Grafana and Cloudflare. The hostinger row is red, naming exactly datastore 86%, demo-stackoverflow disk (once C1 is in), 20 replaced-binary processes, two status rc 1 (renet skew), and `renet.repo-health.unsupported` (until H4). Telemetry, portal-captcha and cf-usage carry their real rc. The Stop hook shows `ops-health-red` in this session.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health refresh` rc 1 with that list, recorded here; `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health offbox` rc 0.
- [x] L6: Docs: monitoring.md (en) gains the new health checks and exit codes. A runbook section in workers/ops-health/README.md covers the Worker, the tokens, the dedupe and how to silence a probe (config edit, never a code edit).
  (corrected 2026-11-06, operator rulings A to E4) Docs: a runbook section in workers/ops-health/README.md covers the Worker, the tokens, the Durable Object state, the target file schema, the dedupe, and how a target change reaches the Worker: edit the `ops` repo's file, then re-run `deploy_ops_health`, never a code edit. It says in one sentence why the Worker cannot read the target file out of the repo's backups (F20), and that the Worker only alerts while fixes run locally.
  - Accept: `npm run check:ci-prose-style` rc 0.
    (ticked) 2026-11-06T22:11:23Z by d778be9d: commit:7449f13da; accept on HEAD 1ef66d74f6a6: L6 monitoring.md half 7449f13da + README half 972636d0f; prose rc=0
- [x] L7: The local auto-repair per D-remedy: on a red machine, the refresher runs `rdc machine repair <m>` limited to the `auto_repair` classes and the daily attempt limit, re-checks, ledgers each action and posts only the remaining verdict. The Stop hook's block message lists the remaining findings, the repair command for any fix still due, and each operator-only item as an ask.
  - CONTROL: fixtures where an auto-safe finding is repaired and the re-check is green (no block, one ledger row per action); an operator-only finding is never passed to repair and appears as an ask; a fourth attempt on the same code within a day is skipped with an advisory; a repair exit 2 keeps the red and names the failed action.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_health.py -q -k repair` rc 0 and `python3 .claude/hooks/stop/test-opshealth.py` rc 0.
    (ticked) 2026-11-06T22:11:24Z by d778be9d: commit:1ef66d74f; accept on HEAD 1ef66d74f6a6: L7 6ad84fa82 + alignment with X2's results 1ef66d74f; pytest -k repair rc=0, test-opshealth rc=0

### C: shared parser and restart scope (writer C)

Owns: packages/shared/src/services/machine/parsing-health.ts (C1), packages/shared/src/services/machine/__tests__/parsing-health.test.ts (C1), packages/cli/src/commands/machine/restart-services.ts, packages/cli/src/commands/machine/__tests__/restart-services*.test.ts, packages/cli/src/services/renet/renet-daemons.ts, packages/cli/src/i18n/locales/*/cli.json (restartServices.repoOption), private/renet/cmd/renet/daemons_upgrade*.go, private/renet (gitlink)

- [x] C1: `checkRepositories` judges each repo's `disk_space.use_percent` (warn over 85, critical over 95, naming the repo); `checkContainers` judges a `Restarting` status as a restart loop (exit 3).
  - CONTROL: fixtures with a repo at 86%, a repo at 99% and a container `Restarting (1) 5 seconds ago` each change the exit code; a repo with no `disk_space` (unmounted) adds no issue.
  - Accept: `cd packages/shared && npx vitest run src/services/machine/__tests__/parsing-health.test.ts` rc 0.
    (ticked) 2026-11-06T20:28:34Z by d778be9d: commit:7f09dec9a; accept on HEAD 5989f3adec78: C1 vitest parsing-health rc=0 (fix c8d043f28)
- [x] C2: The CLI's health tests follow C1.
  - Accept: `cd packages/cli && npx vitest run src/commands/machine` rc 0.
    (ticked) 2026-11-06T20:29:09Z by d778be9d: commit:61eedf0f9; accept on HEAD 5989f3adec78: C2 vitest src/commands/machine rc=0
- [x] C3: renet `daemons upgrade --network-id <n>` (repeatable) limits the rolling restart, `--include-docker` included, to those repos' supervisors. Without the flag the behaviour is unchanged.
  - CONTROL: a Go test where two stale supervisors and `--network-id` for one restart exactly one and report the other as `stale` with the reason `not selected`.
  - Accept: `cd private/renet && go test ./cmd/renet/ -run 'DaemonsUpgrade'` rc 0.
    (ticked) 2026-11-06T20:29:10Z by d778be9d: commit:4f43df4b0; accept on HEAD 5989f3adec78: C3 renet 10e2c7e; go test ./cmd/renet/ -run DaemonsUpgrade rc=0
- [x] C4: `rdc machine restart-services <m> --include-docker --repo <name>` maps the repo to its network id and passes C3's flag. With an old remote renet that lacks the flag, it refuses rather than restarting everything.
  - CONTROL: a CLI test where an older renet's "unknown flag" answer exits 1 and runs no unscoped restart.
  - Accept: `cd packages/cli && npx vitest run src/commands/machine/__tests__/restart-services` rc 0.
    (ticked) 2026-11-06T20:29:11Z by d778be9d: commit:345c3ac8b; accept on HEAD 5989f3adec78: C4 renet e50c5b3 job kind; vitest restart-services rc=0

### G: repo `health()` and certificates, generic product (writer G)

Owns: private/renet (gitlink; pkg/orchestration, pkg/rediaccfile, pkg/reporuntime, pkg/list, pkg/certexport, pkg/functions/commands/repository.go, cmd/renet/repository_health*.go), packages/shared/src/renet-contract/data/functions.schema.ts, packages/shared/src/renet-contract/data/functions.generated.ts, packages/shared/src/renet-contract/data/list-types.generated.ts, packages/shared/src/services/machine/parsing-health.ts (certificate checks, after C1), packages/shared/src/services/machine/__tests__/parsing-health.test.ts (certificate cases), packages/cli/src/commands/repo-health.ts, packages/cli/src/commands/repo.ts (health registration), packages/cli/src/commands/__tests__/repo-health.test.ts, packages/cli/src/commands/machine/health.ts, packages/cli/src/commands/machine/__tests__/health*.test.ts, packages/cli/src/i18n/locales/*/cli.json (repo health and machine health strings), packages/www/src/content/docs/en/services.md, packages/www/src/content/docs/en/monitoring.md, packages/www/src/content/docs/en/cli-application.md (regenerated)

- [x] G1: `health` joins the lifecycle timeout model per D-repohealth: `MachineFunctionTimeout` 30 s default with `RENET_HEALTH_TIMEOUT`, the `# rediacc:timeout health=<d>` key capped at 300 s, so a timed-out `health()` gets the process-group SIGTERM and SIGKILL of up() and down(). The deploy gate still maps a timeout to warming.
  - CONTROL: a Go test where `health()` runs `sleep 600` under a 1 s limit leaves no process of its group after the kill grace; on the current tree the process survives.
  - Accept: `cd private/renet && go test ./pkg/orchestration/ ./pkg/rediaccfile/ -run 'Health|Timeout'` rc 0.
    (ticked) 2026-11-06T20:40:15Z by d778be9d: commit:40e625631 (renet 0ff4e51); go test ./pkg/orchestration/ ./pkg/rediaccfile/ -run Health|Timeout rc=0
- [x] G2: `renet repository health --strict` and `--all` per D-repohealth; `HealthReport` gains `level` and `files`; the contract is regenerated (`./build.sh deploy prep`).
  - CONTROL: a table test for each exit (0, 1, 2, 75, 42, 3, a signal, a timeout) mapping to ok, warning, error, warning, none, error, error, error under `--strict`; with no `health()` anywhere, `--strict` answers `none` while the default mode still answers the drift fallback; `--all` over two mounted repos answers two reports.
  - Accept: `cd private/renet && go test ./pkg/reporuntime/ ./cmd/renet/ -run 'Health'` rc 0, and `npm run check:ci-cli-contract` rc 0.
    (ticked) 2026-11-06T20:40:03Z by d778be9d: commit:40e625631; accept on HEAD 30284be02bed: G2 renet a4748b5+7086ebb, contract regenerated in 40e625631; go test ./pkg/reporuntime/ ./cmd/renet/ -run Health rc=0; check:ci-cli-contract rc=0
- [x] G3: `rdc repo health <repo>@<machine>` (`-o json` supported) exits 0, 1 or 2 per D-repohealth, prints "no check" for `level: none`, and exits 2 on a renet failure. i18n keys are added in all 13 CLI locales.
  - CONTROL: CLI tests where a warning file exits 1, an error file exits 2, `none` exits 0 and prints "no check" (never the healthy string), and a renet transport failure exits 2.
  - Accept: `cd packages/cli && npx vitest run src/commands/__tests__/repo-health.test.ts` rc 0; `npm run check:ci-i18n-completeness && npm run check:ci-i18n-command-parity && npm run check:ci-i18n-cli-key-usage` rc 0.
    (ticked) 2026-11-06T20:40:05Z by d778be9d: commit:30284be02; accept on HEAD 30284be02bed: G3 vitest repo-health rc=0; i18n completeness, command-parity, cli-key-usage rc=0
- [x] G4: `rdc machine health` folds `repository_health --all --strict` per D-repohealth: the worst repo level joins the exit code, one finding per repo, "no check" repos listed without a finding, an old remote renet is one warning, and a failed repo-health job is exit 2.
  - CONTROL: tests where one repo warning turns a clean machine to exit 1; one repo error gives 2; all-`none` stays 0; an "unknown flag" answer gives 1 with `renet.repo-health.unsupported`; a job failure gives 2.
  - Accept: `cd packages/cli && npx vitest run src/commands/machine` rc 0.
    (ticked) 2026-11-06T20:40:06Z by d778be9d: commit:30284be02; accept on HEAD 30284be02bed: G4 vitest src/commands/machine rc=0
- [x] G5: The certificate dimension per D-certs: the renet listing reads the proxy acme.json into `certificates` (`certexport.ParseACME`), the contract types are regenerated, and the shared parser reports `cert.expiry.near` (warning below 21 days, error below 7), naming the certificate.
  - CONTROL: parser fixtures at 22 days (no finding), 20 days (warning) and 6 days (error); a Go test that a fixture acme.json yields `not_after` per main name and SAN; a machine without the proxy adds no finding.
  - Accept: `cd private/renet && go test ./pkg/list/ ./pkg/certexport/` rc 0; `cd packages/shared && npx vitest run src/services/machine/__tests__/parsing-health.test.ts` rc 0.
    (ticked) 2026-11-06T20:40:07Z by d778be9d: commit:30284be02; accept on HEAD 30284be02bed: G5 renet 3bef609 + shared 4ca142669, CLI fold 30284be02; go test ./pkg/list/ ./pkg/certexport/ rc=0; vitest parsing-health(+certs) rc=0
- [x] G6: The ACME CNAME detector per D-certs: `challenge_cname` is resolved per certificate name through the proxy's resolvers, and `rdc machine health` reports `acme.challenge.cname-shared` when the chain ends at a name not beginning `_acme-challenge.` or when two names share one end. Names in `acme.delegated_names` are skipped.
  - CONTROL: fixtures for F17's shape (`_acme-challenge.a.example` and `_acme-challenge.b.example` both ending at `www.example`: finding), a deliberate delegation (`_acme-challenge.mail.example.com` to `_acme-challenge.mail.example.io`: no finding), a shared end listed in `acme.delegated_names` (no finding), and no CNAME (no finding).
  - Accept: same two commands, rc 0.
    (ticked) 2026-11-06T20:40:08Z by d778be9d: commit:30284be02; accept on HEAD 30284be02bed: G6 renet feb3997 + shared e87d4b485, CLI fold 30284be02; same commands rc=0
- [x] G7: Docs. services.md: the lifecycle table (packages/www/src/content/docs/en/services.md:29-38) gains `health()` with the 0, 1, 2 contract and "no check" when undefined, the "up to two functions" text is corrected, and the timeout table gains `health` (30 s default, 300 s cap). monitoring.md: `rdc repo health`, the fold into `machine health`, the certificate dimension and the CNAME finding. cli-application.md is regenerated.
  - Accept: `npm run gen:docs` then `npm run check:ci-i18n-www-cli-docs && npm run check:ci-prose-style` rc 0.
    (ticked) 2026-11-06T22:24:07Z by d778be9d: commit:394f8862f (en 342939d5c, 7449f13da); parity, www-cli-docs, prose, check:i18n rc=0

### X: remediation, generic product (writer X)

Owns: packages/shared/src/services/machine/findings.ts, packages/shared/src/services/machine/__tests__/findings.test.ts, packages/shared/src/services/machine/parsing-health.ts (finding codes, after G5), packages/cli/src/commands/machine/repair.ts, packages/cli/src/commands/machine/index.ts (registration), packages/cli/src/commands/machine/__tests__/repair*.test.ts, packages/cli/src/commands/repo-repair.ts, packages/cli/src/commands/repo.ts (repair registration), packages/cli/src/commands/__tests__/repo-repair.test.ts, packages/cli/src/i18n/locales/*/cli.json (repair and finding strings), private/renet (gitlink; pkg/hub, pkg/prune, pkg/trim, proxy, cmd/renet/proxy_acme*.go, cmd/renet/repository_repair*.go, pkg/orchestration and pkg/rediaccfile for `repair`), packages/www/src/content/docs/en/monitoring.md (repair section), packages/www/src/content/docs/en/services.md (`repair()` rows)

- [x] X1: The findings table per D-remedy (packages/shared/src/services/machine/findings.ts): every issue that `machine health` and `repo health` can raise carries a code, a severity, a subject and, where one exists, `fix {action, class, window_only}`, emitted as `findings` next to the unchanged `issues`. The rows of D-remedy's hostinger table are included.
  - CONTROL: a test that walks every issue producer in parsing-health.ts and health.ts with a fixture that triggers it, and fails on any issue without a code or with a code missing from the table.
  - Accept: `cd packages/shared && npx vitest run src/services/machine/__tests__` rc 0.
    (ticked) 2026-11-06T22:11:17Z by d778be9d: commit:0ebab1e9b; accept on HEAD 1ef66d74f6a6: X1 vitest src/services/machine/__tests__ rc=0
- [x] X2: `rdc machine repair <m>` per D-remedy: `--dry-run`, `--code`, `--with-backup`, `--window-override`; classes enforced (operator-only never runs, auto-with-backup only after a successful snapshot, window-only only inside `maintenance_window`); each action re-checks first, is logged to the journal and the JSON, and is followed by a full re-check; exit 0, 1 or 2. The `maintenance_window` machine config field is added.
  (corrected 2026-11-06, as built in 94332990d) The machine config field is `maintenanceWindow` (camelCase, like every machine field), set with `rdc machine repair <m> --set-window HH:MM-HH:MM|off`; H15's `maintenance_window` means this field.
  - CONTROL: tests where a second run reports zero actions; an operator-only finding is printed and not run; an auto-with-backup finding without `--with-backup` is not run, and with it but a failing snapshot is cancelled; a window-only fix outside the window is refused; a machine with no window never runs window-only fixes; a failed action gives exit 2.
  - Accept: `cd packages/cli && npx vitest run src/commands/machine/__tests__/repair` rc 0; `npm run check:ci-i18n-completeness && npm run check:ci-i18n-command-parity` rc 0.
    (ticked) 2026-11-06T22:11:18Z by d778be9d: commit:94332990d; accept on HEAD 1ef66d74f6a6: X2 vitest repair rc=0; the plan's maintenance_window is the camelCase machine field maintenanceWindow (set with machine repair --set-window); live run is H14
- [x] X3: Hub exclusion per F21: renet's Docker reclaim (private/renet/pkg/prune/docker.go) filters out containers labelled `rediacc.hub.*` and volumes labelled `rediacc.hub.user` or named `rediacc-hub-home-*`, and the hub creates each home volume explicitly with the `rediacc.hub.user` label.
  - CONTROL: Go tests where a reclaim with `Volumes: true` over a stopped hub container, an unlabelled `rediacc-hub-home-a-b` volume, a labelled hub volume and one anonymous volume removes only the anonymous volume; a hub start test asserts the created volume carries the label. Both fail on the current tree.
  - Accept: `cd private/renet && go test ./pkg/prune/ ./pkg/hub/ ./pkg/trim/` rc 0.
    (ticked) 2026-11-06T20:28:48Z by d778be9d: commit:fa4146c32; accept on HEAD 5989f3adec78: X3 renet 1cd33b0; go test ./pkg/prune/ ./pkg/hub/ ./pkg/trim/ rc=0
- [x] X4: The Rediaccfile `repair()` lifecycle function per D-remedy: renet `repository repair` (same executor, sandbox and grants as `health()`; `repair` timeout key, 5 min default, 30 min cap; `REDIACC_HEALTH_LEVEL` passed in; the `# rediacc:repair class=... [window=only]` directive, undeclared meaning operator-only), `rdc repo repair <repo>@<machine>` with the same classes and a `health()` re-run, and `machine repair` running it for non-ok repos. The contract is regenerated.
  - CONTROL: Go tests for the directive parse (auto-safe, auto-with-backup, window=only, absent meaning operator-only) and the timeout kill; a CLI test where an undeclared `repair()` is not run by `machine repair` and is run by `rdc repo repair` only after its prompt is answered; a repair that leaves `health()` at 1 exits 1.
  - Accept: `cd private/renet && go test ./pkg/orchestration/ ./pkg/rediaccfile/ ./cmd/renet/ -run 'Repair'` rc 0; `cd packages/cli && npx vitest run src/commands/__tests__/repo-repair.test.ts` rc 0; `npm run check:ci-cli-contract` rc 0.
    (ticked) 2026-11-06T22:11:19Z by d778be9d: commit:08d393c4f; accept on HEAD 1ef66d74f6a6: X4 renet 4b69d7f + CLI 94332990d; go test -run Repair rc=0, vitest repo-repair rc=0; contract regenerated in 08d393c4f
- [x] X5: The ACME automatic fix per D-certs: `renet proxy acme-fix` writes the anchor TXT at each colliding `_acme-challenge.<name>` through the proxy's CF_DNS_API_TOKEN, then restarts Traefik; it falls back to LEGO_DISABLE_CNAME_SUPPORT only when the proxy declares no delegation; it honours `acme.delegated_names`; it runs at proxy converge and as the `acme.challenge.cname-shared` action of `machine repair`.
  - CONTROL: Go tests against a fake DNS API where F17's shape gets one anchor per name and a second run writes nothing; a delegated name gets no anchor; a non-Cloudflare provider with a declared delegation leaves the finding at operator-only and sets no variable; without a delegation it sets the variable once.
  - Accept: `cd private/renet && go test ./cmd/renet/ ./proxy/... -run 'Acme'` rc 0.
    (ticked) 2026-11-06T22:11:21Z by d778be9d: commit:08d393c4f; accept on HEAD 1ef66d74f6a6: X5 renet 4b69d7f (converge, proxy_acme_fix, repair action) + 82badac (machine-exclusive class, one delegated-names parser); go test -run Acme|Converge rc=0
- [x] X6: Docs: monitoring.md gains the repair layer (finding codes, the three classes, `window_only` and `maintenance_window`, `rdc machine repair`, the hub exclusion, the ACME anchor, `acme.delegated_names` and the variable fallback); services.md gains `repair()` with its directive and timeout row; cli-application.md is regenerated.
  - Accept: `npm run gen:docs` then `npm run check:ci-i18n-www-cli-docs && npm run check:ci-prose-style` rc 0.
    (ticked) 2026-11-06T22:11:22Z by d778be9d: commit:7449f13da; accept on HEAD 1ef66d74f6a6: X6 en docs; cli-application.md regenerated; check:ci-i18n-www-cli-docs and prose rc=0; locale copies with the translation writer (#f3346640)

### N: nightly tree-only reds (writer N)

Owns: scripts/gates/check-quality-complete.ts, .github/workflows/ci-quality.yml (gate-bind regions of the four lanes only), .ci/rediacc_ci/tests/test_core_toolchain.py, .github/workflows/ci-ops-test.yml, .ci/rediacc_ci/tests/gates/test_gate_workflow_env_shell_vars.py, .ci/rediacc_ci/ci/ci_diagnose.py, .ci/rediacc_ci/tests/test_ci_diagnose.py, agent/plans/_done/** (moves only)

- [x] N1: The four UNDECIDED_LANES (ci-quick, quality-account, quality-go, quality-packages) each either get a gate-bind region or move to DECLARED_HAND_WRITTEN_LANES with a reason. The gate reds on a non-empty UNDECIDED_LANES, and its `paths` select it on any change to ci-quality.yml or the lock, so a PR sees it.
  - CONTROL: planting a fifth undecided lane exits 1.
  - Accept: `npm run check:ci-quality-complete` rc 0, printing `0 undecided`.
    (ticked) 2026-11-06T20:28:37Z by d778be9d: commit:49c12be61; accept on HEAD 5989f3adec78: N1 check:ci-quality-complete rc=0, 0 undecided
- [ ] N2: The plans the 11-06 F3 and Plan-housekeeping lines named are closed or moved. F3 and plan-age are calendar clocks, so they also join the drift job (D1).
  - Accept: `npm run check:ci-plan-folders && npm run check:ci-plan-housekeeping` rc 0.
- [ ] N3: Proof of 28bcafd50 (F8) on PR CI: Pytest shards 2/5 and 4/5 green on the PR head.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_core_account.py .ci/rediacc_ci/tests/test_core_local_common.py -q` rc 0, plus the two PR CI shard conclusions read with `.ci/scripts/ci/ci-trace.py`.
- [x] N4: The shim test builds its PATH with `path_farm_without` over a fixed tool set, so the MISMATCH count is a property of the pins and not of the runner image.
  - CONTROL: the same test under a farm that adds one extra pinned tool still passes, and restoring the real-PATH form under that farm fails.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_core_toolchain.py -q` rc 0.
    (ticked) 2026-11-06T20:28:38Z by d778be9d: commit:fb9448969; accept on HEAD 5989f3adec78: N4 pytest test_core_toolchain rc=0 (152 passed)
- [x] N5: OPS Provision creates `$RUNNER_TEMP/renet` before the step that chowns it (.github/workflows/ci-ops-test.yml:299), on every event. A gate case asserts that every `CHOWN_PATH` directory is created by an earlier step on every path.
  - CONTROL: a fixture workflow that removes the mkdir reds.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/gates/test_gate_workflow_env_shell_vars.py -q` rc 0. The schedule path is proven only after the merge (post-merge list).
    (ticked) 2026-11-06T20:28:39Z by d778be9d: commit:4f9a1e07d; accept on HEAD 5989f3adec78: N5 pytest test_gate_workflow_env_shell_vars rc=0 (14 passed); schedule path proven only after merge per the box
- [x] N6: ci_diagnose classifies a job whose Bitwarden lines are successes and whose failing exit is `npm audit` as the audit finding, not `bitwarden-5xx`. The fixture is the excerpt of run 42182422300's Security job.
  - CONTROL: the test fails on the current classifier.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ci_diagnose.py -q` rc 0.
    (ticked) 2026-11-06T20:28:40Z by d778be9d: commit:6057b0059; accept on HEAD 5989f3adec78: N6 pytest test_ci_diagnose rc=0 (93 passed, after 6e21c7a66 fixed D3's Report schedule aggregator)

### D: drift job, weekly fleet, promotion (writer D)

Owns: .ci/rediacc_ci/release/drift_job.py, .ci/rediacc_ci/release/check_soak_period.py, .ci/rediacc_ci/release/nightly_tested_edge.py, .ci/rediacc_ci/tests/test_release_*.py, .github/workflows/ci-drift.yml, .github/workflows/ci.yml, .github/workflows/promote-stable.yml, .claude/hooks/stop/wl_schedred.py (`_BLOCKS`), package.json (`ci:drift`)

- [x] D1: drift_job.py and `npm run ci:drift` per D-drift. The set is computed from `DRIFT_GATE_IDS` plus `CLOCK_GATE_IDS` plus the two split steps, never listed twice.
  - CONTROL: a lock missing one drift id exits 2 (DriftSetError); one planted red gate gives exit 1 with that gate named in the JSON.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_release_drift_job.py -q` rc 0; `npm run ci:drift` runs locally with its rc recorded here.
  - Record 2026-11-06 22:30Z: `npm run ci:drift -- --out drift-verdict.json` under `bws_env exec --profile deploy-workers` ran all 15 checks and exited rc=1, red only on check:ci-external-links (`::finding::link:www.ppc.go.jp`, the host does not answer automated clients; the carried red of carried-reds.json). test_release_drift_job.py rc=0 (2f7cc3f07 added the run-budget control).
    (ticked) 2026-11-06T21:20:10Z by d778be9d: commit:bc59d04d2 (+2f7cc3f07); pytest rc=0; local ci:drift rc=1 with the one carried red (www.ppc.go.jp), recorded under D1
- [x] D2: ci-drift.yml (daily `15 2 * * *`, `CI - Drift`, timeout 30 min, permissions contents read, the readonly app token for private/renet, OPS_HEALTH_INGEST_TOKEN through bws-secrets, and the ingest POST under `if: always()`).
  (corrected 2026-11-06, review bc59d04d.1 and .3) timeout 40 min around drift_job's 25-minute RUN_BUDGET_S, so the verdict is always written; OPS_HEALTH_INGEST_TOKEN is fetched in its own `if: always()` bws-secrets step after the drift checks, never visible to them.
  - Accept: `npm run check:ci-workflows && npm run check:ci-workflow-invariants && npm run check:ci-bws-step-scope` rc 0.
    (ticked) 2026-11-06T20:29:24Z by d778be9d: commit:bc59d04d2 + 2f7cc3f07; check:ci-workflows && ci-workflow-invariants && ci-bws-step-scope rc=0; daily cron first fires after merge
- [x] D3: ci.yml cron becomes `0 1 * * 0`, with the header comment rewritten; a schedule-only `report-schedule` job POSTs the run verdict to ingest `ci-weekly`.
  - Accept: same gates, rc 0.
    (ticked) 2026-11-06T20:28:41Z by d778be9d: commit:bc59d04d2; accept on HEAD 5989f3adec78: D3 check:ci-workflows, ci-workflow-invariants, ci-bws-step-scope rc=0
- [x] D4: promote-stable and check_soak_period per D-promote.
  - CONTROL: tests where a cancelled drift run means no promotion; an edge not contained in the weekly head falls back to soak; a weekly run 9 days old falls back to soak; a weekly run red on a non-drift step means no waiver; and a green weekly run containing the edge plus a drift `failure` gives the waiver.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_release_check_soak_period.py .ci/rediacc_ci/tests/test_release_nightly_tested_edge.py -q` rc 0.
    (ticked) 2026-11-06T20:28:42Z by d778be9d: commit:bc59d04d2; accept on HEAD 5989f3adec78: D4 pytest test_release_check_soak_period + nightly_tested_edge rc=0 (71 passed); empty-conclusion hardening 2f7cc3f07
- [x] D5: wl_schedred `_BLOCKS`: `ci` names the weekly fleet; `ci-drift` names "the stable promotion's daily trigger and the operator's drift mail".
  - Accept: `python3 .claude/hooks/stop/test-plandeps.py` and the schedred tests, rc 0.
    (ticked) 2026-11-06T20:28:43Z by d778be9d: commit:c769dcf6e; accept on HEAD 5989f3adec78: D5 test-plandeps.py rc=0; all 24 stop-hook test files rc=0

### K: backup performance (writer K)

Owns: packages/e2e-tests/tests/31-backup-large-repo.test.ts, packages/e2e-tests/src/utils/backup/withMount.ts, packages/e2e-tests/src/utils/backup/vmEvidence.ts, packages/e2e-tests/src/utils/backup/largeRepoBudget.ts, packages/e2e-tests/src/utils/backup/__tests__/**, .github/workflows/ct-backup-perf.yml, .github/workflows/ct-tests.yml (K10 leg), .ci/config/shards/test-e2e-workers.json, .ci/config/proof-tiers.json (backup area leg)

- [x] K1: `withMount` moves to a util. When the body throws, the unmount still runs, and the thrown error names the body error first and the unmount error second.
  - CONTROL: a unit test with a throwing body and a failing unmount fails on the old `finally`.
  - Accept: `cd packages/e2e-tests && npx vitest run src/utils/backup/__tests__` rc 0.
    (ticked) 2026-11-06T20:29:12Z by d778be9d: commit:9a3124033; accept on HEAD 5989f3adec78: K1 vitest src/utils/backup/__tests__ rc=0
- [x] K2: Each seed file runs under its own time guard (a proportional per-GiB limit), and its failure names the file index. On an SSH loss, `vmEvidence` records the runner side (`uptime`, `free -m`, `dmesg | tail -200`, qemu process state, `df` of REDIACC_VM_DISK_DIR), then retries SSH for 120 s and records the worker's `uptime; dmesg | tail -200`. `incrTimeBudgetMs` drops the absolute cap below 20 GiB, so the 2 GiB budget is purely proportional.
  - CONTROL: unit tests for the evidence helper with a fake runner, and for the budget at 2 GiB with no cap applied.
  - Accept: same command, rc 0.
    (ticked) 2026-11-06T20:29:13Z by d778be9d: commit:9a3124033; accept on HEAD 5989f3adec78: K2 vitest src/utils/backup/__tests__ rc=0
- [x] K3: ct-backup-perf.yml: VM_RAM_WORKER 8192, K10_SEED_GB 20, and cron `30 2 * * 6`.
  - Accept: `npm run check:ci-workflows && npm run check:ci-workflow-env-provision` rc 0.
    (ticked) 2026-11-06T20:28:45Z by d778be9d: commit:5383871ce; accept on HEAD 5989f3adec78: K3 check:ci-workflows + ci-workflow-env-provision rc=0
- [x] K4: The vm:check `backup` area gains an `external` leg `backup-large-2g` (fleet `worker`, VM_DSK sized so FREE_GIB_NEEDED=17 holds, `K10_SEED_GB=2 BACKUP_LARGE_REPO_SUITE=1 ... --test 31-backup-large-repo --fail-on-skip`), and suite 31 joins the area's `suites`.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests -q -k proof_tiers` rc 0.
    (ticked) 2026-11-06T20:28:47Z by d778be9d: commit:23b4a200a; accept on HEAD 5989f3adec78: K4 pytest -k proof_tiers rc=0
- [ ] K5: A PR CI leg runs suite 31 at K10_SEED_GB=2 in test-e2e-workers, within the 15 min lane budget.
  - CONTROL: the anchor-deleted step must breach the budget at 2 GiB. A pass of that step fails the leg, which proves the proportional budget still discriminates.
  - Accept: `npm run check:ci-shard-manifest-coverage && npm run check:ci-lane-budget` rc 0, and the leg green on the PR head (P2).

### R: retirements (writer R, each after its gate)

- [ ] R1: Remove telemetry-probe.yml, only after L5 shows telemetry and portal-captcha results and W5 shows the portal-captcha probes live. References in docs/observability are updated; PLAN-telemetry-export's T16 note gains a pointer.
  (corrected 2026-11-06, operator rulings A to E4) Remove telemetry-probe.yml, only after L5 shows telemetry and portal-captcha results and W5 shows the health-endpoint probes live. References in docs/observability are updated; PLAN-telemetry-export's T16 note gains a pointer.
  - Owns: .github/workflows/telemetry-probe.yml, docs/observability/** (references only)
  - Accept: `npm run check:ci-workflows` rc 0 and `git grep -n "telemetry-probe.yml" -- ':!agent/plans'` returns nothing.
- [ ] R2: Remove cf-usage-report.yml, only after L5 shows the cf-usage result.
  - Owns: .github/workflows/cf-usage-report.yml
  - Accept: the same two checks, for cf-usage-report.yml.
- [ ] R3: Retire nightly-status.yml, .ci/scripts/ci/report-nightly-status.cjs and .ci/config/ci-alerts.json per D-alerts, only after D2, D3 and W6. The mention and label tests move to test_gate_budget_check_report.py; the nightly-only cases are deleted (test_gate_nightly_status_report.py, .ci/rediacc_ci/tests/test_ci_publish_verdict.py:367-371); label_inventory's `nightly-red` creator row points at report-budget-check.cjs; the prose baseline row is drained; doc-registry is updated.
  - Owns: those files
  - CONTROL: test_gate_budget_check_report asserts a failing budget post still mentions the `github_mentions` handles.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/gates/test_gate_budget_check_report.py .ci/rediacc_ci/tests/gates/test_gate_label_inventory.py -q && npm run check:ci-label-inventory && .ci/scripts/quality/check_prose_style.py check --drain` rc 0.

### H: hostinger (lead, live; machine hostinger, `./rdc.sh --config eu-remote`, REDIACC_NO_PROVISION=1 unless the box says otherwise)

The hostinger-side scripts are written on hostinger and live only in its repos. Each box below records what a script checks and its exit codes, never its content. No box prunes or repairs a hub-owned container or volume (F21).

- [ ] H0 [live]: Baseline, read-only. eu-remote and eu-bench resolve hostinger to the same host and user (F6); the `ops_health hostinger` verdict is recorded. This box is the check's live CONTROL: today it must exit 1, naming the known warnings.
  (corrected 2026-11-06, operator rulings A to E4) Baseline, read-only. eu-remote and eu-bench resolve hostinger to the same host and user (F6); the `ops_health machines` verdict is recorded. This box is the check's live CONTROL: today it must exit 1, naming the known warnings.
  - Accept: `RDC_HEALTH_CONFIGS=eu-remote PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health machines` rc 1 with the list recorded here.
- [x] H1 [live]: The prune, per repo, in miscellaneous, erpnext, nextcloud and gitlab: unused images and anonymous dangling volumes only; named dangling volumes are listed here for the operator and never removed; mail and mail:pre-dms17 are not touched.
  - Accept: each command rc 0; the reclaimed bytes per repo are recorded here (F16 records the 2026-11-06 run).
    (ticked) 2026-11-06 by d778be9d: nocommit:no-tracked-change the prune ran 2026-11-06 (F16): miscellaneous unused image 5.79 GB, erpnext 614 and nextcloud 266 anonymous dangling volumes 7.9 GB, gitlab old image 3.87 GB, demo-stackoverflow .vscode-server 5.33 GB; named hub volume left; repo list identical before and after; repo trim on nine repos rc 0
- [ ] H2 [live]: `rdc repo trim -m hostinger` returns the freed blocks to the pool.
  (corrected 2026-11-06, operator rulings A to E4) After S7, `rdc repo trim -m hostinger` returns the freed blocks to the pool (the 2026-11-06 trim of nine repos is recorded in F16).
  - Accept: rc 0; `machine health hostinger -o json` shows datastore under 85% (recorded).
- [ ] H3 [live]: The roundcube wildcard (2026-12-05) has its issuer path identified: the renewal client and its DNS-01 credential, in the mail repo or elsewhere. A renewal is forced or the blocker is named before 2026-11-14, when L1's 21-day threshold turns red.
  (corrected 2026-11-06, operator rulings A to E4) Confirm that the first Traefik retry after the 2026-11-06 DNS fix (F17, around 07:54 UTC daily) renewed `*.rediacc.io` and the 29 single-host certificates. If a renewal is still failing on 2026-11-12, when the earliest expiry crosses 21 days, the Traefik log line is recorded and the blocker named with its owner.
  - Accept: `openssl s_client -connect roundcube.rediacc.io:443 -servername roundcube.rediacc.io </dev/null | openssl x509 -noout -enddate` and the same for two single-host names show an expiry after 2027-01-01 (recorded); after H4, `machine health hostinger -o json` has no `cert.expiry.near` and no `acme.challenge.cname-shared` finding.
- [ ] H4 [live]: The branch renet is installed, only after P1 is VERIFIED on the head that carries C3 and C4, at the start of the quiet window (00:00 UTC), by one `machine status hostinger -o json` without REDIACC_NO_PROVISION. Per F5, this restarts the router and the non-docker daemons; docker supervisors stay stale.
  (corrected 2026-11-06, operator rulings A to E4) The branch renet is installed, only after P1 is VERIFIED on the head that carries C3, C4, G1 to G6 and X2 to X5, at the start of the quiet window (00:00 UTC), by one `machine status hostinger -o json` without REDIACC_NO_PROVISION. Per F5, this restarts the router and the non-docker daemons; docker supervisors stay stale.
  - Accept: rc 0, with the remote `renet hash` equal to the local sha256 (recorded).
- [ ] H5 [live]: The restart cycle, one repo at a time, re-reading health after each: `rdc machine restart-services hostinger --include-docker --repo <r>` in the order miscellaneous, demo-stackoverflow, marketing, mautic, hermes, erpnext, nextcloud, gitlab. A repo that does not come back stops the cycle.
  (corrected 2026-11-06, operator rulings A to E4) The restart cycle, one repo at a time, re-reading health after each: `rdc machine restart-services hostinger --include-docker --repo <r>` in the order miscellaneous, demo-stackoverflow, marketing, mautic, hermes, erpnext, nextcloud, gitlab. A repo that does not come back stops the cycle. This is the hand-run form of the window-only `renet.binary.replaced` fix.
  - Accept: each rc 0; the stale count falls by 2 per repo (recorded).
- [ ] H6 [live]: mail inside the quiet window (00:00-01:00 UTC): `--repo mail`, then `ops_health hostinger` mail steps green and the 465 and 993 banners answering.
  (corrected 2026-11-06, operator rulings A to E4) mail inside the quiet window (00:00-01:00 UTC): `--repo mail`, then `rdc repo health mail@hostinger` rc 0 and the 465 and 993 banners answering.
  - Accept: rc 0 for both.
- [ ] H7 [live]: observability last, only when no live lease or STATE.md of another session names its RAM-mode work; otherwise this box waits and says why.
  - Accept: `--repo observability` rc 0.
- [ ] H8 [live]: The final verdict.
  - Accept: `RDC_HEALTH_CONFIGS=eu-remote PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health machines` rc 0; `rdc machine health hostinger` rc 0 with ops, mail and demo-stackoverflow at `level: ok`; `machine status hostinger --containers --health-check` and `--services --stability-check` both rc 0.
- [ ] H9 [live]: The `ops` repo is created on hostinger as an ordinary repo. Its plain files hold the target list in D-record's schema (served hosts with their ports, the SMTP host, the machine IP and the DNSBL zones). Its Rediaccfile `health()` is the primary check. It checks TLS expiry for every served host (exit 1 below 21 days, 2 below 7 days or on a failed handshake), the SMTP banner on :25 and on 465 after TLS (2 when absent or wrong), and DNSBL for the machine IP (2 when listed, 1 when a zone is unanswerable). It publishes nothing anywhere.
  - Accept: after H4, `rdc repo health ops@hostinger` rc 0; one planted condition (a target with a 1-day expiry threshold override) gives rc 1, recorded and reverted.
- [ ] H10 [live]: The mail repo's `health()`: Postfix queue above 50 messages or an oldest message above 60 min (exit 1), ClamAV daily.cld or daily.cvd older than 48 h (exit 1), mail volume free space below 15% (exit 1) or below 5% (exit 2), and an unreadable queue (exit 2). Its `repair()`, if written, declares `window=only`. Written in the quiet window or as a file change that needs no restart.
  - Accept: after H4, `rdc repo health mail@hostinger` rc 0 (recorded).
- [ ] H11 [live]: demo-stackoverflow's `health()`: its volume over 85% used (exit 1) or over 95% (exit 2).
  - Accept: after H4, `rdc repo health demo-stackoverflow@hostinger` rc 2 before S7 and rc 0 after it (both recorded).
- [ ] H12 [live]: The `ops` repo's backups go to the existing backup store through the existing schedule and strategy, like every other repo: `rdc backup strategy bind` only where hostinger's strategy does not already cover new repos, then `rdc backup schedule -m hostinger`.
  - Accept: both rc 0; `machine health hostinger -o json` lists `ops` under `backup_coverage` after its first run (recorded).
- [ ] H13 [live]: The `ops` target file reaches the Worker through the deploy (W5). After any later edit of the file, the deploy is re-run.
  - Accept: `/v1/status` shows `targets_sha` equal to the sha256 of the `ops` target file read through `rdc term connect`, and one probe per target, with no `targets` unknown probe; `ops_health offbox` with `OPS_HEALTH_TARGETS_REF=ops@hostinger` reports no `ops.targets.drift`.
- [ ] H14 [live]: The repair layer's live CONTROL, read-only: `rdc machine repair hostinger --dry-run -o json` lists today's findings with D-remedy's classes: `datastore.usage.high` auto-safe (trim and anonymous prune), demo-stackoverflow's archives operator-only, `renet.binary.replaced` window-only, rediacc-hub-home-muhammed-vscode absent from every prune candidate list.
  - Accept: rc 1 with that list recorded here.
- [ ] H15 [live]: After H4, `maintenance_window` set to `00:00-01:00 UTC` for hostinger, then one auto-safe run, `rdc machine repair hostinger` outside the window. It runs only the auto-safe actions, refuses the window-only ones, and re-checks. A second run reports zero actions.
  - Accept: the first run's actions and re-check recorded; the second run's JSON has an empty `actions`; the hub volume is still present (`docker volume ls` in miscellaneous, recorded).

### S: demo-stackoverflow archives to the public bucket (lead, live; repo guid db315abd-e300-47e4-bbb6-c383d6defe81)

- [x] S1 [live]: Bucket rediacc-public-data, custom domain data.rediacc.com on the rediacc.com zone, a Cache Rule (`public, max-age=31536000, immutable`), CORS GET and HEAD for `*`, all per .ci/docs/r2-media-setup.md sections 2, 5 and 5b. The commands are recorded in a new section of that doc.
  - Record 2026-11-06: bucket rediacc-public-data created (EEUR, default jurisdiction), custom domain data.rediacc.com on the rediacc.com zone, a set_cache_settings rule `(http.host eq "data.rediacc.com")` respecting origin TTL (objects carry `public, max-age=31536000, immutable`), CORS GET and HEAD for `*` (rule public-data-read). The doc's section 5 endpoint answers 405 and is corrected in .ci/docs/r2-media-setup.md.
  - Accept: `curl -sI https://data.rediacc.com/stackexchange/README.txt` answers 200 after S8's upload.
    (ticked) 2026-11-06T22:16:04Z by d778be9d: commit:4e5652933 live run recorded; README HTTP 200 and SHA256SUMS 371 lines re-read
- [x] S2 [live]: `sha256sum data/*.7z > SHA256SUMS` on hostinger, run niced and ionice'd, covering 371 lines.
  - Record 2026-11-06: SHA256SUMS written niced and ionice'd in the demo-stackoverflow repo root, 371 lines (36,270 bytes), basenames only, rc 0.
  - Accept: rc 0, and `wc -l SHA256SUMS` is 371.
    (ticked) 2026-11-06T22:16:05Z by d778be9d: commit:4e5652933 live run recorded; README HTTP 200 and SHA256SUMS 371 lines re-read
- [x] S3 [live]: The upload from hostinger (a throwaway `amazon/aws-cli` container inside the repo, credentials over stdin, a bandwidth limit, multipart) of the 371 files plus SHA256SUMS under `stackexchange/`.
  - Record 2026-11-06: `amazon/aws-cli s3 sync` from inside the repo (--network host, env file removed after, 30 MB/s, 64 MB parts) ran 63 min, rc 0; head-object sizes equal local for 371 of 371; SHA256SUMS uploaded (36,270 bytes, served: 371 lines through https://data.rediacc.com/stackexchange/SHA256SUMS).
  - Accept: rc 0; HEAD sizes equal the local sizes for 371 of 371.
    (ticked) 2026-11-06T22:16:06Z by d778be9d: commit:4e5652933 live run recorded; README HTTP 200 and SHA256SUMS 371 lines re-read
- [x] S4 [live]: Verification by streaming each object back: `curl -fsS https://data.rediacc.com/stackexchange/<f> | sha256sum`, compared with SHA256SUMS.
  - Progress 2026-11-06: 369 of 371 objects streamed back with a matching sha256, no mismatch; stackoverflow.com-Posts.7z (23.0 GB) and stackoverflow.com-PostHistory.7z (37.7 GB) not verified yet (stream about 5 to 28 MB/s); resume with `./pubdata-s4d.sh <file>` in the repo on hostinger. S7 waits for both.
  - Accept: a 371 of 371 OK line, rc 0.
    (ticked) 2026-11-07T03:09:19Z by d778be9d: commit:4e5652933 371 of 371 OK: 369 streamed 2026-11-06, Posts.7z streamed OK 2026-11-07, PostHistory.7z verified through a resumable download then sha256sum (streaming broke on HTTP/2 resets) matching SHA256SUMS dcb0c911...; rc 0
    (correction 2026-11-07) Which command gave each verdict: the 369 objects of 2026-11-06 and stackoverflow.com-Posts.7z (2026-11-07, background task b2h0vztj1, output line `OK stackoverflow.com-Posts.7z`) passed the streaming command itself, `curl -fsS ... | sha256sum` against SHA256SUMS. For stackoverflow.com-PostHistory.7z that command did not pass: three HTTP/2 INTERNAL_ERROR resets made curl's retry re-feed bytes into the pipe (`MISMATCH ... got=188425dd...`). It was verified instead by `curl -fsS --http1.1 -C - -o <file>` resumed four times, then `sha256sum <file>` (task b2uok291n, output line `OK stackoverflow.com-PostHistory.7z size=37747369973`, the SHA256SUMS value dcb0c911...), and the copy deleted. The "rc 0" of the tick is that last command's; the streaming rc 0 holds for 370 of the 371 objects.
- [x] S5 [live]: download/download.sh: BASE_URL is the bucket; the file list comes from SHA256SUMS; `sha256sum -c` runs after `7z t`; `--only <site,...>` is added. The diff is recorded here, since the source lives only on hostinger.
  - Accept: `bash -n download/download.sh` rc 0.
    (record 2026-11-07) The diff, applied on hostinger with `repo sync upload --remote-file download/download.sh` (the source lives only there; old copy at /tmp/m/s5/old.sh, 63 lines): BASE_URL moves from archive.org to `https://data.rediacc.com/stackexchange`; the file list comes from `SHA256SUMS` (fetched with `curl -fsSL --retry 3`) instead of scraping the archive.org index; `--only <site,...>` (or `--only=`) filters SHA256SUMS to the named archives and exits 2 naming any site it does not list; `validate()` runs `7z t` and then `sha256sum -c` against the matching SHA256SUMS line; the success line reads "OK (7z test and sha256 valid)". The upload left the file without its exec bit, so it runs as `bash download/download.sh`.
    (ticked) 2026-11-07T03:43:47Z by d778be9d: commit:62106f7b3 download/download.sh on hostinger: bucket BASE_URL, SHA256SUMS list, sha256sum -c after 7z t, --only; bash -n rc 0; diff recorded under the box
- [ ] S5b [live, optional]: pipeline.py fetch-import-delete per site, so the datastore holds one archive at a time.
  - Accept: one small site imported on the S6 fork, rc 0.
- [x] S6 [live]: A fork test: `repo fork demo-stackoverflow@hostinger --tag fetchtest`, data/*.7z emptied in the fork only, `download.sh --only` for three small sites, `sha256sum -c` passing, one `pipeline.py <site>` import, then the fork deleted.
  - Accept: each rc 0; parent data/ untouched (count 371).
    (ticked) 2026-11-07T03:43:48Z by d778be9d: commit:62106f7b3 fetchtest fork: each step rc 0 (fork, empty data in the fork, download --only three sites, sha256sum -c OK x3, pipeline.py solana.meta import 1699 rows, fork deleted); parent data/ 371 before and after
- [ ] S7 [live]: Only after S4 and S6: delete data/*.7z, run `rdc repo trim demo-stackoverflow@hostinger`, and check that the Postgres container and volume are unaffected (.vscode-server was already removed on 2026-11-06, F16).
  (corrected 2026-11-06, operator rulings A to E4) Only after S4 and S6: delete data/*.7z (the operator-only half of `repo.disk.high`), run `rdc repo trim demo-stackoverflow@hostinger`, and check that the Postgres container and volume are unaffected (.vscode-server was already removed on 2026-11-06, F16).
  - Accept: `machine health hostinger -o json` shows demo-stackoverflow disk under 85%; `docker ps` shows stack-db-1 healthy.
- [x] S8 [live]: `stackexchange/README.txt` with the CC BY-SA 4.0 attribution (Stack Exchange, Inc., source archive.org/details/stackexchange, unmodified).
  - Record 2026-11-06: stackexchange/README.txt (279 bytes) served HTTP 200, text/plain, cache-control immutable, access-control-allow-origin *.
  - Accept: the S1 curl rc 0.
    (ticked) 2026-11-06T22:16:08Z by d778be9d: commit:4e5652933 live run recorded; README HTTP 200 and SHA256SUMS 371 lines re-read

### P: proof before the merge (lead)

- [ ] P1: vm:check on the head carrying C3, C4 and K4: the renet phase plus the backup area's receipt leg and the 2 GiB external leg.
  (corrected 2026-11-06, operator rulings A to E4) vm:check on the head carrying C3, C4, G1 to G6, X2 to X5 and K4: the renet phase plus the backup area's receipt leg and the 2 GiB external leg.
  - Accept: `npm run vm:check -- --changed` VERIFIED, with the receipt admitted by `vm_tier.admit` (block_vm_unverified_push passes).
- [ ] P2: PR CI green on the head, including N1, N3, the K5 leg and the new ops-health gate (L4), read with the ci-watch skill.
  (corrected 2026-11-06, operator rulings A to E4) PR CI green on the head, including N1, N3, the G and X tests, the K5 leg and the new ops-health gate (L4), read with the ci-watch skill.
  - Accept: CI Complete SUCCESS.
- [ ] LP-bench [live]: A fresh bench receipt through worklist.py --live-proof, after the cli boxes land.
  - Accept: live-proof bench cli-bench
- [ ] LP-hostinger [live]: A fresh hostinger receipt through worklist.py --live-proof, after H5 to H7, since renet-live expects `stale_binary == []` (F6).
  - Accept: live-proof hostinger renet-live machine=hostinger

What bench and hostinger prove before the merge:
- Hostinger proves the generic verdict (H0 red, H8 green), the repair layer (H14 classes, H15 auto-safe run and idempotence, hub volume kept), the hostinger-side `health()` functions through `rdc repo health` (H9 to H11), the certificate renewal (H3), the renet install and restart cycle (H4 to H7), the `ops` repo's backups in the existing store (H12), the archive move (S), and the renet-live receipt.
- Bench proves only the cli surface read.
- The Worker proves its cron, Durable Object state, deploy-time targets and mail in production (W5, W6, H13).
- vm:check proves C3, C4, G1 to G6, X2 to X5 and the 2 GiB leg.
- PR CI proves N1 to N4, N6, G1 to G7, X1 to X6, K5 and the gate.

Closes only after the merge (GitHub runs workflow files from main):
- D2: the first scheduled CI - Drift run, its ingest entry and its mail on a real red.
- D3: the first weekly Console CI run and its `ci-weekly` ingest entry.
- D4: the first promote-stable run triggered by CI - Drift.
- N5: the first scheduled OPS Provision green.
- K6: the first weekly 20 GiB ct-backup-perf result, recorded in reports/backup-large-repo-k10; it ticks K10 of PLAN-backup-program.md with the wording corrected from nightly to weekly. When it is green, K10_SEED_GB returns to 50.
- R3's effect: no nightly-red issue post after a weekly red.

The PR's merge rule carries an `Operational-Reason:` naming D2, D3, D4, N5 and K6.

## Hypotheses, each with the box that settles it

- Y1. Workers refuse port 25 and validate peer certificates on `secureTransport: "on"` (W0).
- Y2. certspotter answers without a key at the volume of the deployed targets every 10 min (W0); crt.sh is the fallback.
- Y3. Hostinger has backup coverage for its autostart repos. If not, L1 reds `backup.coverage.absent` by design, and the fix is an operator-only backup strategy, not a threshold (H0).
- Y4. `postqueue -j` exists in the mail image (Postfix 3.1 or later), and ClamAV keeps `daily.cld` or `daily.cvd` under /var/lib/clamav (H10).
- Y5. OPS Provision's chown fails because the schedule path skips the step that creates `$RUNNER_TEMP/renet` (N5 reads the 11-05 and 11-06 logs first).
- Y6. `check:ci-docker-image-freshness` is outside `UPSTREAM_GATES` today, which means the 11-06 Docker red was not waivable (D1 settles membership).
- Y7. The PR worker VM admits FREE_GIB_NEEDED=17 at 2 GiB (K5); if not, the leg sets VM_DSK.
- Y8. A 2 GiB incremental's fixed overhead stays under 10% of its seed time. If not, K2 records the measured overhead, and the operator chooses between a floor (which weakens the control) and a larger PR seed.
- Y9. Traefik's daily retry renews all 30 certificates without hitting Let's Encrypt's failed-validation limit left over from 2026-11-04..06 (H3).
- Y10. The deploy-gate path of `DockerRuntime.Health` keeps its warming behaviour once G1 bounds `health()` through `executeFunction` (G1, G2).
- Y11. lego writes its challenge TXT beside an existing anchor TXT at the same name, and Cloudflare accepts several TXT values there, so the anchor never blocks a challenge (X5's fake-API test, then H3 on a later renewal).
- Y12. The Docker daemons on hostinger answer the volume list with labels, so X3's label filter works on the existing hub volumes too. The name prefix covers them in any case (H15).
- Y13. The target file fits within the 5 KB Worker secret limit (W4 checks the size; a larger list moves to a bundled, deploy-time-generated module that stays out of the tree).

## Risks

- L5 turns `ops-health-red` on in every session at `smart` until H2, H4 to H8, H11 and S7 land. This is intended (ruling 8). The block is claim-owned by one session, and the others get an advisory.
- the new ops-health gate (L4) reds every PR while hostinger is red. The `no-external-quality` label is the escape, and the drift waiver keeps promotion unaffected.
- H4's router restart briefly interrupts every HTTP route on hostinger, which is why it runs at the window start.
- S3 and S4 read and send about 99 GB from hostinger. Both run niced, with a bandwidth limit.
- A dead Worker silences the between-session channel. The 30-min stale block and the Monday digest are the two detectors.
- A target edit in the `ops` repo does not reach the Worker until the deploy is re-run. The local `ops.targets.drift` finding names the deploy command, so the gap is visible in the next session.
- `machine health` now runs every repo's `health()`. Four at a time under a 30 s default bounds the added time, and a slow `health()` is an error, not a hang.
- Automatic repair can loop on a finding it cannot clear. The daily limit of 3 attempts per code per machine stops it, and every attempt is ledgered and visible in the block message.
- Auto-repair runs on every machine in `RDC_HEALTH_CONFIGS`. Only auto-safe actions run, window-only ones need a configured window, and test or bench configs are excluded by leaving them out of that variable.
- The X5 anchor writes DNS through the proxy's token. The write is one additive TXT per colliding name, never a delete or overwrite, and `acme.delegated_names` keeps deliberate delegation untouched.

## What this plan deliberately does not do

- It does not delete mail:pre-dms17 (ruling 9 keeps it until 2026-11-13; a removal is a separate operator call), demo-heartbeat, or any named volume. Hub-owned volumes and containers are excluded from every prune and repair (F21).
- It does not change housekeeping.yml, pins-soaked, ci-obs-mirror or ci-vm-bake.
- It does not port telemetry_delivery, portal_captcha or cf_usage_report to the Worker. Spend between sessions is Cloudflare's billing alert (F15), telemetry delivery depends on hostinger by nature, and portal captcha is not outside-only; none of the three mailed between sessions before.
- It does not put hostinger host names, IPs or service checks in console code or config (ruling A); they live in hostinger's repos.
- It does not let the Worker fix anything, does not have it read repo backups (F20), and gives it no D1 and no bucket (E4).
- It does not give the `ops` repo any special storage or publish step; its backups use the existing store, schedule and strategy (E4).
- It does not run operator-only fixes automatically, ever, and it runs auto-with-backup fixes only with `--with-backup` and a successful snapshot.
- It does not revert the wildcard DNS record (E2).
- It does not give `rdc repo status` a verdict exit code; `rdc repo health` is the verdict.

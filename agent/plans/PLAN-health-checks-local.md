# PLAN: health checks move local: the Stop hook, CI gates and one off-box Cloudflare alerter replace the scheduled GitHub pings; hostinger gets a health check that fails on warnings, and its current warnings are cleared

Status: approved -- operator rulings 2026-11-06 (ten, recorded under "Operator rulings"); every design choice below that the rulings left open carries a stated default and a reason
Owner: d778be9d
Priority: P1 -- a red outside the PR head reaches nobody between sessions, hostinger's datastore is at 87% with one repo at 99%, 20 renet processes run a deleted binary, the roundcube wildcard certificate expires 2026-12-05, and the nightly has been red 7 of the last 8 scheduled runs on reds that a PR could have caught
Depends-On: no-dep -- every code box is inside this plan; box K6 records the first result that closes box K10 of agent/plans/PLAN-backup-program.md; telemetry-probe.yml (PLAN-telemetry-export T16, ticked) and cf-usage-report.yml (PLAN-cloudflare-spend-guard T6, ticked) are removed here only after their replacement is verified (R1, R2)
Concurrency: parallel -- seven writers (W, L, C, N, D, K, R) with disjoint Owns, plus lead-only live queues H (hostinger) and S (demo-stackoverflow); order in "Writer split and order". The wire shapes (D-record, D-ingest) are fixed in Design so W and L do not wait on each other to compile
Owns: agent/plans/PLAN-health-checks-local.md, .ci/config/ops-health.json, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json, .ci/config/ci-alerts.json, .ci/config/proof-tiers.json, .ci/config/shards/test-e2e-workers.json, workers/ops-health/**, .ci/rediacc_ci/ops/ops_health.py, .ci/rediacc_ci/ops/deploy_ops_health.py, .ci/rediacc_ci/tests/test_ops_health*.py, .ci/scripts/quality/check_ops_health.py, .claude/hooks/stop/wl_opshealth.py, .claude/hooks/stop/test-opshealth.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_schedred.py, .claude/hooks/stop/worklist_messages.py, .claude/config/effort.json, packages/shared/src/services/machine/parsing-health.ts, packages/shared/src/services/machine/__tests__/parsing-health.test.ts, packages/cli/src/commands/machine/restart-services.ts, packages/cli/src/commands/machine/__tests__/restart-services*.test.ts, packages/cli/src/services/renet/renet-daemons.ts, packages/cli/src/i18n/locales/*/cli.json, private/renet/cmd/renet/daemons_upgrade*.go, private/renet, packages/www/src/content/docs/en/monitoring.md, scripts/gates/check-quality-complete.ts, .ci/rediacc_ci/tests/test_core_toolchain.py, .ci/rediacc_ci/tests/gates/test_gate_workflow_env_shell_vars.py, .ci/rediacc_ci/ci/ci_diagnose.py, .ci/rediacc_ci/tests/test_ci_diagnose.py, .ci/rediacc_ci/release/drift_job.py, .ci/rediacc_ci/release/check_soak_period.py, .ci/rediacc_ci/release/nightly_tested_edge.py, .ci/rediacc_ci/tests/test_release_*.py, .ci/rediacc_ci/security/ci_workflow_invariants.py, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, package.json, .github/workflows/ci-drift.yml, .github/workflows/ci.yml, .github/workflows/ci-ops-test.yml, .github/workflows/ci-quality.yml, .github/workflows/ct-tests.yml, .github/workflows/ct-backup-perf.yml, .github/workflows/promote-stable.yml, .github/workflows/telemetry-probe.yml, .github/workflows/cf-usage-report.yml, .github/workflows/nightly-status.yml, .ci/scripts/ci/report-nightly-status.cjs, scripts/ci/report-budget-check.cjs, .ci/rediacc_ci/tests/gates/test_gate_nightly_status_report.py, .ci/rediacc_ci/tests/gates/test_gate_budget_check_report.py, .ci/rediacc_ci/tests/test_ci_publish_verdict.py, .ci/rediacc_ci/quality/label_inventory.py, .ci/config/prose-style-baseline.json, scripts/data/doc-registry.md, packages/e2e-tests/tests/31-backup-large-repo.test.ts, packages/e2e-tests/src/utils/backup/largeRepoBudget.ts, packages/e2e-tests/src/utils/backup/withMount.ts, packages/e2e-tests/src/utils/backup/vmEvidence.ts, packages/e2e-tests/src/utils/backup/__tests__/**, agent/ledgers/ops-health.jsonl
Live-Proof: bench, hostinger -- hostinger proves the health check (red on today's known warnings, green after the fixes), the mail probes, the branch renet installed after a VERIFIED vm:check, the per-repo restart cycle, the prune and the archive move; bench proves only that the branch CLI reads the bench account (cli surface), since nothing here is account-side. The ops-health Worker is not a proof-tiers surface and is proven by its own [live] boxes in production
Epics: 09b8bdfa
Worklist: PR-TASK 09b8bdfa
Updated: 2026-11-06
First-Seen: 2026-11-06

Partial edits inside shared files are scoped in each phase's Owns: wl_checks.py (the ops-health block beside the schedred block only), wl_schedred.py (`_BLOCKS` only), worklist_messages.py (ops-health strings only), effort.json (four new keys only), the cli.json locales (restartServices.repoOption only), private/renet (gitlink), ci_workflow_invariants.py (`UPSTREAM_GATES` only), package.json (scripts `ci:drift` and the new ops-health gate (L4) only), ci-quality.yml (the ops-health step and the four lanes' gate-bind regions only), ct-tests.yml (the K10 2 GiB leg only), test_ci_publish_verdict.py (the nightly-report case only), label_inventory.py (the `nightly-red` creator row only), and prose-style-baseline.json (drain only).

## Operator rulings (2026-11-06, settled)

1. The between-session alarm is AWS SES mail to the comma-separated list in the Bitwarden secret OPS_ALERT_EMAILS, sent with the existing AWS_SES_* credentials, from a runner that does not depend on hostinger and is not a scheduled GitHub ping.
2. telemetry-probe.yml and cf-usage-report.yml migrate to local checks, plus the off-box runner where a probe is outside-only. Their red keeps reaching the Stop hook, so the replacement lands before the workflows are removed.
3. nightly-status.yml and .ci/config/ci-alerts.json are retired.
4. housekeeping.yml keeps all five jobs unchanged.
5. pins-soaked, promote-stable, ci-obs-mirror and ci-vm-bake stay scheduled.
6. ci.yml's nightly is split and tightened: tree-only reds are fixed so PR CI and local gates catch them; the clock-based drift lookups become one cheap daily job that blocks the Stop hook and mails the operator; the 5-OS stock-image fleet moves to weekly; promote-stable's soak re-points to the daily job plus the last weekly fleet run.
7. ct-backup-perf.yml: fix the harness, add a 2 GiB variant to vm:check and to PR CI, move the 50 GiB run to weekly, and seed 20 GiB until K10 records a first result.
8. The hostinger health check fails on warnings and covers every repo plus the mail service; inside-SSH checks run from the local side, outside-only checks run from the off-box runner too.
9. Hostinger fixes: prune only anonymous dangling volumes and unused images in four named repos; list named dangling volumes for the operator; keep mail:pre-dms17 until 2026-11-13; move demo-stackoverflow's 371 archives to the public bucket rediacc-public-data at https://data.rediacc.com/stackexchange/; install the branch renet after a VERIFIED fleet run and restart the repos one at a time, observability last and only when free, mail in a quiet window (default 03:00 Europe/Istanbul, 00:00 UTC).
10. The roundcube.rediacc.io wildcard certificate (expiry 2026-12-05) is surfaced.

## Findings as verified (2026-11-06)

- F1. wl_schedred discovers every workflow with a `schedule:` from the files (.claude/hooks/stop/wl_schedred.py:107), shares one cache with a 900 s TTL (:36), picks one owning session through an O_EXCL claim file, and never raises; it is wired at .claude/hooks/stop/wl_checks.py:4976-5030 under the effort key `scheduled-red` (`{block: high, advise: low}`). A new scheduled workflow (the drift job) is watched the day it lands, with no edit. A removed workflow simply stops being watched.
- F2. The FLOOR set is sealed in .claude/hooks/stop/wl_floor.py:13-28. New checks are non-floor keys in .claude/config/effort.json `checks`, each exactly once, enforced by `check_plan_record.py --effort-table` (.ci/scripts/quality/check_plan_record.py:1598).
- F3. `rdc machine health` already folds container health, service restart loops, backup staleness, verify failures and the stale-binary list into one exit code (packages/cli/src/commands/machine/health.ts:240-277; packages/shared/src/services/machine/parsing-health.ts:468-510). It does NOT judge per-repo filesystem usage, although `RepositoryInfo.disk_space.use_percent` is already in the listing (packages/shared/src/renet-contract/data/list-types.generated.ts:132-161). That is why demo-stackoverflow at 99% raised no issue. A container in a `Restarting` loop is not judged either: `checkServices` (:209-233) looks at systemd units only. An absent `backup_coverage` is silent by design (:346).
- F4. `rdc repo status` has no verdict exit code (packages/cli/src/commands/repo.ts:314-370); it prints the record. Decision in D-verdict.
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
- F16. (lead, 2026-11-06) The leftover prune of H1 already ran: 24.6 GB freed inside miscellaneous, erpnext, nextcloud, gitlab and demo-stackoverflow (.vscode-server), and `rdc repo trim` on nine repos exited 0, but the datastore stayed at 316G used (86%): the bulk is demo-stackoverflow's archives (S). One named dangling volume, rediacc-hub-home-muhammed-vscode (7.05 GB, miscellaneous), is left for the operator.

## Design

### D-runner. Where the off-box alerter lives (ruling 1)

Recommended: a new Cloudflare Worker `ops-health` (workers/ops-health/) with a cron trigger every 10 minutes, a D1 database `ops-health`, the custom domain `ops-health.rediacc.com` (custom-domain route, same pattern as workers/mta-sts/wrangler.toml), and SES mail through the existing SigV4 transport.

Alternatives weighed:
- AWS Lambda with EventBridge Scheduler: full TLS peer-certificate access and native SES, but no IaC or credentials for it exist in the tree or in Bitwarden (the SES keys are send-only), and port 25 egress is restricted there too.
- A second VPS: full capability, but a new machine to patch and pay for, and it can itself fall silent unnoticed.
- Grafana alerting on hostinger: excluded by ruling 1.
- A scheduled GitHub job: excluded by ruling 1.

The Worker reuses deployed infrastructure, the account's Cloudflare credentials and an existing deploy pattern.

Known Worker limits, each settled by W0 before anything is built on it:
- (a) Cloudflare blocks outbound TCP to port 25 from `connect()`. The off-box SMTP check therefore reads the 220 banner on 465 after the implicit TLS handshake; the :25 banner is read by the local check.
- (b) `connect()` does not expose the peer certificate. A successful `secureTransport: "on"` handshake proves the served chain is valid now. Days to expiry come from Certificate Transparency (certspotter issuances API, crt.sh as a fallback), and an unreadable CT source is `unknown`, never green. The exact served-certificate days are measured by the local check.
- (c) DNSBL lookups go over DNS-over-HTTPS. Spamhaus answers 127.255.255.x to public resolvers, which is `unknown`, so zen is queried only when an optional SPAMHAUS_DQS_KEY exists.

Who watches the watcher: the Stop hook reds when the record's `last_cron_at` is older than 30 minutes. The Worker mails a Monday 06:00 UTC digest, so a missing Monday mail tells the operator the alerter is dead.

### D-record. The record (one shape, read by the Stop hook, the CI gate and the mail)

D1 tables:
- `probe_state(probe TEXT PK, state TEXT CHECK(state IN ('green','red','unknown')), since TEXT, checked_at TEXT, consecutive INT, detail TEXT)`
- `ingest(source TEXT PK, state TEXT, at TEXT, detail TEXT)`
- `mail_log(id INTEGER PK, at TEXT, kind TEXT, probes TEXT, message_id TEXT)`
- `meta(key TEXT PK, value TEXT)`, which holds `last_cron_at`.

`GET /v1/status` (bearer OPS_HEALTH_READ_TOKEN) answers:

```
{ "last_cron_at": iso, "probes": [{probe, state, since, checked_at, detail}], "ingest": [{source, state, at, detail}], "verdict": "green|red|unknown" }
```

The verdict is red when any probe is red, or when any ingest row is red and younger than its `max_age_h` from the config.

### D-ingest. Results that reach the record from elsewhere

`POST /v1/ingest` (bearer OPS_HEALTH_INGEST_TOKEN) takes `{source, state, detail, at}`. The sources are `drift` (the daily job), `ci-weekly` (the weekly fleet run), and `hostinger-inside` and `local-<check>` (the local refresher). So every red that must reach the operator between sessions goes through one mailer and one dedupe.

### D-mail. Dedupe

A probe turns red after 2 consecutive red runs and recovers after 2 green runs. Ingest rows transition on first receipt. One mail per cron run lists every transition. A still-red probe is re-mailed at most once per 24 h. Every send is logged with the SES MessageId. Recipients come from OPS_ALERT_EMAILS, split on commas and trimmed. An empty list is a setup failure, recorded as an `unknown` probe `mailer`.

### D-config. One config

.ci/config/ops-health.json holds:
- the probe list with host, port and kind;
- thresholds: TLS red below 21 days, the Postfix queue red above 50 messages or an oldest message above 60 min, ClamAV daily.cld red above 48 h, repo or mail volume red above 85% used;
- the DNSBL zones and the target IP 72.61.137.225;
- the local TTLs: hostinger-inside 30 min, telemetry and portal-captcha 6 h, cf-usage 7 d, off-box read 15 min;
- the ingest `max_age_h`;
- `github_mentions` (see D-alerts).

The Worker imports it at build time and Python reads it, so no threshold is written twice.

### D-verdict. Hostinger health = exit codes, no new verb

`rdc machine health` already lists every repo in one read job. C1 adds two checks to the shared parser, so the verdict needs no `repo health` verb and no JSON scraping of `repo status`:
- per-repo filesystem usage: `Repo <name> disk usage high/critical`, over 85 or over 95, from `disk_space.use_percent`;
- containers whose status starts `Restarting`: a restart loop, exit 3.

These are product changes for every machine and are documented in monitoring.md.

`ops_health hostinger` runs, all under `REDIACC_NO_PROVISION=1` (F5) with `./rdc.sh --config eu-remote`:
1. `machine health hostinger -o json`. Exit 1 or higher is red, so warnings fail.
2. `machine status hostinger --containers --health-check`.
3. `machine status hostinger --services --stability-check`.
4. From the same JSON, `backup_coverage` present for every autostart repo, and every repo's age below the stale limit.
5. In the mail repo (`term connect mail@hostinger -c ...`): `postqueue -j` count and oldest arrival, and the mtime of `daily.cld` or `daily.cvd`.
6. From the dev box, outside hostinger: served-cert days for mail.rediacc.io:465 and :993 and roundcube.rediacc.io:443, the :25 banner `220[- ]mail.rediacc.io`, and DNSBL through the dev box resolver.

Exit 0 green, 1 red, 2 setup or unreadable. Steps 2 and 3 are red today because of renet skew; that red is honest and clears at H4.

### D-local. The Stop hook side

wl_opshealth.py reads `.ci/cache/ops-health/state.json`, which is shared and gitignored. When a check is past its TTL, it spawns ONE detached `python3 -m rediacc_ci.ops.ops_health refresh`, claimed through O_EXCL on `.ci/cache/ops-health/refresh.lock`, with a stale lock after 20 min. The hook never waits and never raises.

The refresher:
- runs the due checks: hostinger-inside, telemetry_delivery under bws profile `telemetry-probe`, portal_captcha, and cf_usage_report under profile `cf-usage-report`;
- reads the off-box record;
- writes the cache;
- POSTs the inside verdicts to `/v1/ingest`;
- appends a row to agent/ledgers/ops-health.jsonl only on a state transition.

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
- O first. W and L, C, N, D and K then run in parallel.
- R1 and R2 after L5 and W6 are VERIFIED. R3 after D2, D3 and W6.
- P1 after C3, C4 and K2.
- H0 to H3 any time (read-only, then the prune). H4 only after a VERIFIED P1 on the head that carries C3 and C4, then H5 to H8 in order.
- S is independent of everything except O2's credential.

Writers and their boxes:
- Writer W (Worker): W0 to W6.
- Writer L (local checks, hook, gate): L1 to L6, after O1. L4 codes against D-record without waiting on W.
- Writer C (CLI, shared, renet): C1 to C4.
- Writer N (nightly tree reds): N1 to N6.
- Writer D (drift, weekly fleet, promotion): D1 to D5.
- Writer K (backup perf): K1 to K5; K6 is post-merge.
- Writer R (retirements): R1 to R3, in that order, each after its gate above.
- Lead only: O2, H, S, P and LP.

Control rule: every new test fails without its fix. The tick note records the test name and rc 1 from the tree with the fix stashed and the test kept.

## Boxes

### O: config and secrets (lead)

- [ ] O1: .ci/config/ops-health.json per D-config. OPS_ALERT_EMAILS, OPS_HEALTH_READ_TOKEN, OPS_HEALTH_INGEST_TOKEN and the optional SPAMHAUS_DQS_KEY are registered in bws-secret-map.json. A bws profile `ops-health` is added to secret-supply.json (required: OPS_ALERT_EMAILS, AWS_SES_ACCESS_KEY_ID_EU, AWS_SES_SECRET_ACCESS_KEY_EU, AWS_SES_REGION_EU, AWS_SES_FROM, OPS_HEALTH_READ_TOKEN, OPS_HEALTH_INGEST_TOKEN; optional: SPAMHAUS_DQS_KEY, CF_GLOBAL_API_KEY, CF_EMAIL). The two tokens are minted by the session (`secrets.token_urlsafe(32)`) and stored with `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env store-from-env`.
  - Owns: .ci/config/ops-health.json, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json
  - CONTROL: `check:ci-secret-supply` reds on a profile that names a secret absent from the map.
  - Accept: `npm run check:ci-bws-map && npm run check:ci-secret-supply` rc 0; `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile ops-health -- true` rc 0.
- [ ] O2 [live]: A bucket-scoped R2 token for rediacc-public-data (Object Read & Write) is minted from the Global API Key through `cf_auth` and stored as R2_PUBLIC_DATA_ACCESS_KEY_ID and R2_PUBLIC_DATA_SECRET_ACCESS_KEY in a profile `public-data`.
  - Accept: `bws_env exec --profile public-data -- true` rc 0.

### W: the off-box Worker (writer W)

Owns: workers/ops-health/**, .ci/rediacc_ci/ops/deploy_ops_health.py, .ci/rediacc_ci/tests/test_ops_health_deploy.py, plus the registration rows for a new worker in .ci/rediacc_ci/quality/typecheck_workers.py, .ci/rediacc_ci/quality/lockfile.py, .ci/config/syncpack-source-exclusions.json and .ci/rediacc_ci/tests/gates/test_gate_preview_worker_reaping.py (one row each).

- [ ] W0: Spike on a throwaway deploy: `connect()` to port 25 is refused; a `secureTransport: "on"` connect to an expired-certificate host (expired.badssl.com:443) fails while mail.rediacc.io:465 succeeds and yields a `220` line; certspotter answers `not_after` for roundcube.rediacc.io; DoH for `225.137.61.72.zen.spamhaus.org` answers 127.255.255.x. Each result is recorded here. A different result changes D-runner before W1 starts.
  - Accept: `npx wrangler dev --test-scheduled` probe script rc 0 with the four facts printed and recorded here.
- [ ] W1: Probes per D-runner: TLS handshake plus CT days for 465, 993 and roundcube 443; the 465 banner; HTTPS reachability for roundcube.rediacc.io; `/health` for every stable and edge account host and proxy host from regions.json (bundled at build); portal captcha per host, ported from rediacc_ci.ops.portal_captcha steps 1-3; DNSBL over DoH for the configured zones. Every probe returns green, red or unknown, and unknown is never folded into green.
  - CONTROL: unit fixtures for an expired certificate (red), CT at 20 days (red), a banner without `mail.rediacc.io` (red), DNSBL 127.0.0.2 (red), DNSBL 127.255.255.254 (unknown), a portal bundle without a site key whose login answers 200 (red).
  - Accept: `cd workers/ops-health && npx vitest run && npx tsc --noEmit` rc 0.
- [ ] W2: The D1 schema, the transitions and the dedupe of D-mail, `/v1/status` and `/v1/ingest` with bearer checks.
  - CONTROL: a single red run mails nothing; a second consecutive red mails once; a third mails nothing; 24 h later it mails once; two greens mail "recovered"; a wrong bearer answers 401; an empty OPS_ALERT_EMAILS yields the `mailer` probe `unknown`.
  - Accept: same command, rc 0.
- [ ] W3: SES send through private/account/src/utils/aws-sigv4.ts, with the subject `[rediacc ops] <n> red, <m> recovered` and the Monday digest.
  - CONTROL: a mocked SES 400 is logged with its body and leaves the transition unmailed, so the next run retries.
  - Accept: same command, rc 0.
- [ ] W4: `deploy_ops_health` creates the D1 database when it is missing, applies the schema, runs `wrangler deploy`, and puts the secrets over stdin. It is idempotent, dry-run by default, and writes only with `--write`.
  - CONTROL: a second `--write` run reports zero changes.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_health_deploy.py -q` rc 0.
- [ ] W5 [live]: Deploy to production.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_ops_health --write` rc 0; after 20 min, `curl -fsS -H "Authorization: Bearer $OPS_HEALTH_READ_TOKEN" https://ops-health.rediacc.com/v1/status` rc 0 with `last_cron_at` under 11 min old and every W1 probe present.
- [ ] W6 [live]: A forced transition: `POST /v1/ingest {source:"selftest", state:"red"}`, then green. Each mail is logged with an SES MessageId, and the operator's receipt is reported back on the worklist item, without a question.
  - Accept: the two `mail_log` rows read through `/v1/status?mail=1` rc 0.

### L: local checks, Stop hook and CI gate (writer L)

Owns: .ci/rediacc_ci/ops/ops_health.py, .ci/rediacc_ci/tests/test_ops_health.py, .claude/hooks/stop/wl_opshealth.py, .claude/hooks/stop/test-opshealth.py, .claude/hooks/stop/wl_checks.py (ops-health block), .claude/hooks/stop/worklist_messages.py (ops-health strings), .claude/config/effort.json (four keys), .ci/scripts/quality/check_ops_health.py, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .ci/rediacc_ci/security/ci_workflow_invariants.py (UPSTREAM_GATES), .github/workflows/ci-quality.yml (one step), package.json (the new ops-health gate (L4)), agent/ledgers/ops-health.jsonl

- [ ] L1: `ops_health hostinger` per D-verdict, with REDIACC_NO_PROVISION=1 forced inside the module (not inherited) and `--config eu-remote` as the default.
  - CONTROL: fixtures for health rc 1 (red), status rc 1 (red), a queue of 51 messages (red), an oldest message of 61 min (red), daily.cld 49 h old (red), a certificate at 20 days (red), coverage absent for an autostart repo (red), an SSH timeout (exit 2), and a test that the subprocess environment carries REDIACC_NO_PROVISION=1 even when the caller unset it.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_health.py -q` rc 0.
- [ ] L2: `ops_health refresh`, `ops_health offbox` and the cache, the ledger-on-transition and the POST to ingest. telemetry_delivery, portal_captcha and cf_usage_report run unchanged as subprocesses under their bws profiles, keeping their exit-code contract (0, 1, 2).
  - CONTROL: an unchanged state appends no ledger row; a 1-to-0 change appends one; a failed ingest POST is recorded in the cache and does not fail the refresh.
  - Accept: same pytest, rc 0.
- [ ] L3: wl_opshealth.py and its wiring beside the schedred block (.claude/hooks/stop/wl_checks.py:4976-5030), plus the four effort keys of D-local.
  - CONTROL: the fixtures cover a red cache, where this session owns the claim and is blocked while a peer gets an advisory; a stale cache, which spawns one refresher, and two concurrent stops, which spawn one; an off-box `last_cron_at` 31 min old (`ops-health-offbox-stale`); and a cache that cannot be parsed (advisory, no raise).
  - Accept: `python3 .claude/hooks/stop/test-opshealth.py` rc 0 and `python3 .ci/scripts/quality/check_plan_record.py --effort-table` rc 0.
- [ ] L4: the new ops-health gate (L4) per D-gate: a manifest entry, an UPSTREAM_GATES row, a ci-quality.yml step with `UPSTREAM_GATE_IF`, the secret through the bws-secrets action, and the lock regenerated.
  - CONTROL: a status fixture with one red probe exits 1; `last_cron_at` 31 min old exits 1; an unreadable status exits 2.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_health.py -q -k gate && npm run gen:gates-lock && npm run check:ci-workflow-gates && npm run check:ci-workflow-invariants` rc 0.
- [ ] L5 [live]: The first real local refresh against hostinger, Grafana and Cloudflare. hostinger-inside is red, naming exactly datastore 86%, demo-stackoverflow disk (once C1 is in), 20 replaced-binary processes, and two status rc 1 (renet skew). Telemetry, portal-captcha and cf-usage carry their real rc. The Stop hook shows `ops-health-red` in this session.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health refresh` rc 1 with that list, recorded here; `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health offbox` rc 0.
- [ ] L6: Docs: monitoring.md (en) gains the new health checks and exit codes. A runbook section in workers/ops-health/README.md covers the Worker, the tokens, the dedupe and how to silence a probe (config edit, never a code edit).
  - Accept: `npm run check:ci-prose-style` rc 0.

### C: CLI, shared parser and renet (writer C)

Owns: packages/shared/src/services/machine/parsing-health.ts, packages/shared/src/services/machine/__tests__/parsing-health.test.ts, packages/cli/src/commands/machine/restart-services.ts, packages/cli/src/commands/machine/__tests__/restart-services*.test.ts, packages/cli/src/services/renet/renet-daemons.ts, packages/cli/src/i18n/locales/*/cli.json (one key), private/renet/cmd/renet/daemons_upgrade*.go, private/renet (gitlink), packages/www/src/content/docs/en/monitoring.md

- [ ] C1: `checkRepositories` judges each repo's `disk_space.use_percent` (warn over 85, critical over 95, naming the repo); `checkContainers` judges a `Restarting` status as a restart loop (exit 3).
  - CONTROL: fixtures with a repo at 86%, a repo at 99% and a container `Restarting (1) 5 seconds ago` each change the exit code; a repo with no `disk_space` (unmounted) adds no issue.
  - Accept: `cd packages/shared && npx vitest run src/services/machine/__tests__/parsing-health.test.ts` rc 0.
- [ ] C2: The CLI's health tests follow C1.
  - Accept: `cd packages/cli && npx vitest run src/commands/machine` rc 0.
- [ ] C3: renet `daemons upgrade --network-id <n>` (repeatable) limits the rolling restart, `--include-docker` included, to those repos' supervisors. Without the flag the behaviour is unchanged.
  - CONTROL: a Go test where two stale supervisors and `--network-id` for one restart exactly one and report the other as `stale` with the reason `not selected`.
  - Accept: `cd private/renet && go test ./cmd/renet/ -run 'DaemonsUpgrade'` rc 0.
- [ ] C4: `rdc machine restart-services <m> --include-docker --repo <name>` maps the repo to its network id and passes C3's flag. With an old remote renet that lacks the flag, it refuses rather than restarting everything.
  - CONTROL: a CLI test where an older renet's "unknown flag" answer exits 1 and runs no unscoped restart.
  - Accept: `cd packages/cli && npx vitest run src/commands/machine/__tests__/restart-services` rc 0.

### N: nightly tree-only reds (writer N)

Owns: scripts/gates/check-quality-complete.ts, .github/workflows/ci-quality.yml (gate-bind regions of the four lanes only), .ci/rediacc_ci/tests/test_core_toolchain.py, .github/workflows/ci-ops-test.yml, .ci/rediacc_ci/tests/gates/test_gate_workflow_env_shell_vars.py, .ci/rediacc_ci/ci/ci_diagnose.py, .ci/rediacc_ci/tests/test_ci_diagnose.py, agent/plans/_done/** (moves only)

- [ ] N1: The four UNDECIDED_LANES (ci-quick, quality-account, quality-go, quality-packages) each either get a gate-bind region or move to DECLARED_HAND_WRITTEN_LANES with a reason. The gate reds on a non-empty UNDECIDED_LANES, and its `paths` select it on any change to ci-quality.yml or the lock, so a PR sees it.
  - CONTROL: planting a fifth undecided lane exits 1.
  - Accept: `npm run check:ci-quality-complete` rc 0, printing `0 undecided`.
- [ ] N2: The plans the 11-06 F3 and Plan-housekeeping lines named are closed or moved. F3 and plan-age are calendar clocks, so they also join the drift job (D1).
  - Accept: `npm run check:ci-plan-folders && npm run check:ci-plan-housekeeping` rc 0.
- [ ] N3: Proof of 28bcafd50 (F8) on PR CI: Pytest shards 2/5 and 4/5 green on the PR head.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_core_account.py .ci/rediacc_ci/tests/test_core_local_common.py -q` rc 0, plus the two PR CI shard conclusions read with `.ci/scripts/ci/ci-trace.py`.
- [ ] N4: The shim test builds its PATH with `path_farm_without` over a fixed tool set, so the MISMATCH count is a property of the pins and not of the runner image.
  - CONTROL: the same test under a farm that adds one extra pinned tool still passes, and restoring the real-PATH form under that farm fails.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_core_toolchain.py -q` rc 0.
- [ ] N5: OPS Provision creates `$RUNNER_TEMP/renet` before the step that chowns it (.github/workflows/ci-ops-test.yml:299), on every event. A gate case asserts that every `CHOWN_PATH` directory is created by an earlier step on every path.
  - CONTROL: a fixture workflow that removes the mkdir reds.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/gates/test_gate_workflow_env_shell_vars.py -q` rc 0. The schedule path is proven only after the merge (post-merge list).
- [ ] N6: ci_diagnose classifies a job whose Bitwarden lines are successes and whose failing exit is `npm audit` as the audit finding, not `bitwarden-5xx`. The fixture is the excerpt of run 42182422300's Security job.
  - CONTROL: the test fails on the current classifier.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ci_diagnose.py -q` rc 0.

### D: drift job, weekly fleet, promotion (writer D)

Owns: .ci/rediacc_ci/release/drift_job.py, .ci/rediacc_ci/release/check_soak_period.py, .ci/rediacc_ci/release/nightly_tested_edge.py, .ci/rediacc_ci/tests/test_release_*.py, .github/workflows/ci-drift.yml, .github/workflows/ci.yml, .github/workflows/promote-stable.yml, .claude/hooks/stop/wl_schedred.py (`_BLOCKS`), package.json (`ci:drift`)

- [ ] D1: drift_job.py and `npm run ci:drift` per D-drift. The set is computed from `DRIFT_GATE_IDS` plus `CLOCK_GATE_IDS` plus the two split steps, never listed twice.
  - CONTROL: a lock missing one drift id exits 2 (DriftSetError); one planted red gate gives exit 1 with that gate named in the JSON.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_release_drift_job.py -q` rc 0; `npm run ci:drift` runs locally with its rc recorded here.
- [ ] D2: ci-drift.yml (daily `15 2 * * *`, `CI - Drift`, timeout 30 min, permissions contents read, the readonly app token for private/renet, OPS_HEALTH_INGEST_TOKEN through bws-secrets, and the ingest POST under `if: always()`).
  - Accept: `npm run check:ci-workflows && npm run check:ci-workflow-invariants && npm run check:ci-bws-step-scope` rc 0.
- [ ] D3: ci.yml cron becomes `0 1 * * 0`, with the header comment rewritten; a schedule-only `report-schedule` job POSTs the run verdict to ingest `ci-weekly`.
  - Accept: same gates, rc 0.
- [ ] D4: promote-stable and check_soak_period per D-promote.
  - CONTROL: tests where a cancelled drift run means no promotion; an edge not contained in the weekly head falls back to soak; a weekly run 9 days old falls back to soak; a weekly run red on a non-drift step means no waiver; and a green weekly run containing the edge plus a drift `failure` gives the waiver.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_release_check_soak_period.py .ci/rediacc_ci/tests/test_release_nightly_tested_edge.py -q` rc 0.
- [ ] D5: wl_schedred `_BLOCKS`: `ci` names the weekly fleet; `ci-drift` names "the stable promotion's daily trigger and the operator's drift mail".
  - Accept: `python3 .claude/hooks/stop/test-plandeps.py` and the schedred tests, rc 0.

### K: backup performance (writer K)

Owns: packages/e2e-tests/tests/31-backup-large-repo.test.ts, packages/e2e-tests/src/utils/backup/withMount.ts, packages/e2e-tests/src/utils/backup/vmEvidence.ts, packages/e2e-tests/src/utils/backup/largeRepoBudget.ts, packages/e2e-tests/src/utils/backup/__tests__/**, .github/workflows/ct-backup-perf.yml, .github/workflows/ct-tests.yml (K10 leg), .ci/config/shards/test-e2e-workers.json, .ci/config/proof-tiers.json (backup area leg)

- [ ] K1: `withMount` moves to a util. When the body throws, the unmount still runs, and the thrown error names the body error first and the unmount error second.
  - CONTROL: a unit test with a throwing body and a failing unmount fails on the old `finally`.
  - Accept: `cd packages/e2e-tests && npx vitest run src/utils/backup/__tests__` rc 0.
- [ ] K2: Each seed file runs under its own time guard (a proportional per-GiB limit), and its failure names the file index. On an SSH loss, `vmEvidence` records the runner side (`uptime`, `free -m`, `dmesg | tail -200`, qemu process state, `df` of REDIACC_VM_DISK_DIR), then retries SSH for 120 s and records the worker's `uptime; dmesg | tail -200`. `incrTimeBudgetMs` drops the absolute cap below 20 GiB, so the 2 GiB budget is purely proportional.
  - CONTROL: unit tests for the evidence helper with a fake runner, and for the budget at 2 GiB with no cap applied.
  - Accept: same command, rc 0.
- [ ] K3: ct-backup-perf.yml: VM_RAM_WORKER 8192, K10_SEED_GB 20, and cron `30 2 * * 6`.
  - Accept: `npm run check:ci-workflows && npm run check:ci-workflow-env-provision` rc 0.
- [ ] K4: The vm:check `backup` area gains an `external` leg `backup-large-2g` (fleet `worker`, VM_DSK sized so FREE_GIB_NEEDED=17 holds, `K10_SEED_GB=2 BACKUP_LARGE_REPO_SUITE=1 ... --test 31-backup-large-repo --fail-on-skip`), and suite 31 joins the area's `suites`.
  - Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests -q -k proof_tiers` rc 0.
- [ ] K5: A PR CI leg runs suite 31 at K10_SEED_GB=2 in test-e2e-workers, within the 15 min lane budget.
  - CONTROL: the anchor-deleted step must breach the budget at 2 GiB. A pass of that step fails the leg, which proves the proportional budget still discriminates.
  - Accept: `npm run check:ci-shard-manifest-coverage && npm run check:ci-lane-budget` rc 0, and the leg green on the PR head (P2).

### R: retirements (writer R, each after its gate)

- [ ] R1: Remove telemetry-probe.yml, only after L5 shows telemetry and portal-captcha results and W5 shows the portal-captcha probes live. References in docs/observability are updated; PLAN-telemetry-export's T16 note gains a pointer.
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

- [ ] H0 [live]: Baseline, read-only. eu-remote and eu-bench resolve hostinger to the same host and user (F6); the `ops_health hostinger` verdict is recorded. This box is the check's live CONTROL: today it must exit 1, naming the known warnings.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health hostinger` rc 1 with the list recorded here.
- [ ] H1 [live]: The prune, per repo, in miscellaneous, erpnext, nextcloud and gitlab: unused images and anonymous dangling volumes only; named dangling volumes are listed here for the operator and never removed; mail and mail:pre-dms17 are not touched.
  - Accept: each command rc 0; the reclaimed bytes per repo are recorded here (F16 records the 2026-11-06 run).
- [ ] H2 [live]: `rdc repo trim -m hostinger` returns the freed blocks to the pool.
  - Accept: rc 0; `machine health hostinger -o json` shows datastore under 85% (recorded; after S7 if the archives are the remaining bulk).
- [ ] H3 [live]: The roundcube wildcard (2026-12-05) has its issuer path identified: the renewal client and its DNS-01 credential, in the mail repo or elsewhere. A renewal is forced or the blocker is named before 2026-11-14, when L1's 21-day threshold turns red.
  - Accept: `openssl s_client -connect roundcube.rediacc.io:443 -servername roundcube.rediacc.io </dev/null | openssl x509 -noout -enddate` shows an expiry after 2027-01-01, or the blocker is recorded with its owner.
- [ ] H4 [live]: The branch renet is installed, only after P1 is VERIFIED on the head that carries C3 and C4, at the start of the quiet window (00:00 UTC), by one `machine status hostinger -o json` without REDIACC_NO_PROVISION. Per F5, this restarts the router and the non-docker daemons; docker supervisors stay stale.
  - Accept: rc 0, with the remote `renet hash` equal to the local sha256 (recorded).
- [ ] H5 [live]: The restart cycle, one repo at a time, re-reading health after each: `rdc machine restart-services hostinger --include-docker --repo <r>` in the order miscellaneous, demo-stackoverflow, marketing, mautic, hermes, erpnext, nextcloud, gitlab. A repo that does not come back stops the cycle.
  - Accept: each rc 0; the stale count falls by 2 per repo (recorded).
- [ ] H6 [live]: mail inside the quiet window (00:00-01:00 UTC): `--repo mail`, then `ops_health hostinger` mail steps green and the 465 and 993 banners answering.
  - Accept: rc 0 for both.
- [ ] H7 [live]: observability last, only when no live lease or STATE.md of another session names its RAM-mode work; otherwise this box waits and says why.
  - Accept: `--repo observability` rc 0.
- [ ] H8 [live]: The final verdict.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health hostinger` rc 0, and `machine status hostinger --containers --health-check` and `--services --stability-check` both rc 0.

### S: demo-stackoverflow archives to the public bucket (lead, live; repo guid db315abd-e300-47e4-bbb6-c383d6defe81)

- [ ] S1 [live]: Bucket rediacc-public-data, custom domain data.rediacc.com on the rediacc.com zone, a Cache Rule (`public, max-age=31536000, immutable`), CORS GET and HEAD for `*`, all per .ci/docs/r2-media-setup.md sections 2, 5 and 5b. The commands are recorded in a new section of that doc.
  - Accept: `curl -sI https://data.rediacc.com/stackexchange/README.txt` answers 200 after S8's upload.
- [ ] S2 [live]: `sha256sum data/*.7z > SHA256SUMS` on hostinger, run niced and ionice'd, covering 371 lines.
  - Accept: rc 0, and `wc -l SHA256SUMS` is 371.
- [ ] S3 [live]: The upload from hostinger (a throwaway `amazon/aws-cli` container inside the repo, credentials over stdin, a bandwidth limit, multipart) of the 371 files plus SHA256SUMS under `stackexchange/`.
  - Accept: rc 0; HEAD sizes equal the local sizes for 371 of 371.
- [ ] S4 [live]: Verification by streaming each object back: `curl -fsS https://data.rediacc.com/stackexchange/<f> | sha256sum`, compared with SHA256SUMS.
  - Accept: a 371 of 371 OK line, rc 0.
- [ ] S5 [live]: download/download.sh: BASE_URL is the bucket; the file list comes from SHA256SUMS; `sha256sum -c` runs after `7z t`; `--only <site,...>` is added. The diff is recorded here, since the source lives only on hostinger.
  - Accept: `bash -n download/download.sh` rc 0.
- [ ] S5b [live, optional]: pipeline.py fetch-import-delete per site, so the datastore holds one archive at a time.
  - Accept: one small site imported on the S6 fork, rc 0.
- [ ] S6 [live]: A fork test: `repo fork demo-stackoverflow@hostinger --tag fetchtest`, data/*.7z emptied in the fork only, `download.sh --only` for three small sites, `sha256sum -c` passing, one `pipeline.py <site>` import, then the fork deleted.
  - Accept: each rc 0; parent data/ untouched (count 371).
- [ ] S7 [live]: Only after S4 and S6: delete data/*.7z, run `rdc repo trim demo-stackoverflow@hostinger`, and check that the Postgres container and volume are unaffected (.vscode-server was already removed on 2026-11-06, F16).
  - Accept: `machine health hostinger -o json` shows demo-stackoverflow disk under 85%; `docker ps` shows stack-db-1 healthy.
- [ ] S8 [live]: `stackexchange/README.txt` with the CC BY-SA 4.0 attribution (Stack Exchange, Inc., source archive.org/details/stackexchange, unmodified).
  - Accept: the S1 curl rc 0.

### P: proof before the merge (lead)

- [ ] P1: vm:check on the head carrying C3, C4 and K4: the renet phase plus the backup area's receipt leg and the 2 GiB external leg.
  - Accept: `npm run vm:check -- --changed` VERIFIED, with the receipt admitted by `vm_tier.admit` (block_vm_unverified_push passes).
- [ ] P2: PR CI green on the head, including N1, N3, the K5 leg and the new ops-health gate (L4), read with the ci-watch skill.
  - Accept: CI Complete SUCCESS.
- [ ] LP-bench [live]: A fresh bench receipt through worklist.py --live-proof, after the cli boxes land.
  - Accept: live-proof bench cli-bench
- [ ] LP-hostinger [live]: A fresh hostinger receipt through worklist.py --live-proof, after H5 to H7, since renet-live expects `stale_binary == []` (F6).
  - Accept: live-proof hostinger renet-live machine=hostinger

What bench and hostinger prove before the merge:
- Hostinger proves the health verdict (H0 red, H8 green), the mail probes, the prune, the renet install and restart cycle (H4 to H7), the archive move (S), and the renet-live receipt.
- Bench proves only the cli surface read.
- The Worker proves its cron, record and mail in production (W5, W6).
- vm:check proves C3, C4 and the 2 GiB leg.
- PR CI proves N1 to N4, N6, K5 and the gate.

Closes only after the merge (GitHub runs workflow files from main):
- D2: the first scheduled CI - Drift run, its ingest row and its mail on a real red.
- D3: the first weekly Console CI run and its `ci-weekly` ingest row.
- D4: the first promote-stable run triggered by CI - Drift.
- N5: the first scheduled OPS Provision green.
- K6: the first weekly 20 GiB ct-backup-perf result, recorded in reports/backup-large-repo-k10; it ticks K10 of PLAN-backup-program.md with the wording corrected from nightly to weekly. When it is green, K10_SEED_GB returns to 50.
- R3's effect: no nightly-red issue post after a weekly red.

The PR's merge rule carries an `Operational-Reason:` naming D2, D3, D4, N5 and K6.

## Hypotheses, each with the box that settles it

- Y1. Workers refuse port 25 and validate peer certificates on `secureTransport: "on"` (W0).
- Y2. certspotter answers without a key at this volume of 3 hosts every 10 min (W0); crt.sh is the fallback.
- Y3. Hostinger has backup coverage for its autostart repos. If not, L1 reds `backup-coverage-absent` by design, and the fix is a backup strategy, not a threshold (H0).
- Y4. `postqueue -j` exists in the mail image (Postfix 3.1 or later), and ClamAV keeps `daily.cld` or `daily.cvd` under /var/lib/clamav (H0).
- Y5. OPS Provision's chown fails because the schedule path skips the step that creates `$RUNNER_TEMP/renet` (N5 reads the 11-05 and 11-06 logs first).
- Y6. `check:ci-docker-image-freshness` is outside `UPSTREAM_GATES` today, which means the 11-06 Docker red was not waivable (D1 settles membership).
- Y7. The PR worker VM admits FREE_GIB_NEEDED=17 at 2 GiB (K5); if not, the leg sets VM_DSK.
- Y8. A 2 GiB incremental's fixed overhead stays under 10% of its seed time. If not, K2 records the measured overhead, and the operator chooses between a floor (which weakens the control) and a larger PR seed.

## Risks

- L5 turns `ops-health-red` on in every session at `smart` until H2, H4 to H8 and S7 land. This is intended (ruling 8). The block is claim-owned by one session, and the others get an advisory.
- the new ops-health gate (L4) reds every PR while hostinger is red. The `no-external-quality` label is the escape, and the drift waiver keeps promotion unaffected.
- H4's router restart briefly interrupts every HTTP route on hostinger, which is why it runs at the window start.
- S3 and S4 read and send about 99 GB from hostinger. Both run niced, with a bandwidth limit.
- A dead Worker silences the between-session channel. The 30-min stale block and the Monday digest are the two detectors.

## What this plan deliberately does not do

- It does not delete mail:pre-dms17 (ruling 9 keeps it until 2026-11-13; a removal is a separate operator call), demo-heartbeat, or any named volume.
- It does not change housekeeping.yml, pins-soaked, ci-obs-mirror or ci-vm-bake.
- It does not port telemetry_delivery or cf_usage_report to the Worker. Spend between sessions is Cloudflare's billing alert (F15), and telemetry delivery depends on hostinger by nature.
- It does not add a `repo health` verb (D-verdict).

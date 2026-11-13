# PLAN-hostinger-to-bench: re-home the production machine hostinger from the eu-remote config (production eu account) to eu-bench (bench.rediacc.cloud), so agents run it without the operator and no backup window opens

Status: approved -- operator ruling 2026-11-13 ASKED: "Move hostinger to bench but you must be able to go without me. Feel free to define bws totp etc. in bws. Additionally, there could be need to update IP address restriction to allow hostinger there." The same day's ruling deletes the old Cloudflare objects including rediacc-backups-eu without archive; this plan makes that one delete wait for C7. <!-- style-ok -->
Depends-On: PLAN-d1-eu-jurisdiction.md
Priority: P0 -- every eu-remote login stops at the operator's authenticator whenever the operator's IP changes, so hostinger cannot run unattended, and rediacc-backups-eu (441.7 GB) is the only complete off-site copy.
Concurrency: parallel -- wave 1 has five writers on disjoint files (W1 reset guard, W2 bench_access pins, W3 CLI import verb, W4 rotation config, W5 escrow profile); wave 2 (bench readiness) and wave 3 (cutover) are live boxes in order in the hostinger queue, wave 3 outside 01:45-03:00Z; the writers and P0 do not wait on PLAN-d1-eu-jurisdiction, only C2 does.
Owns: agent/plans/PLAN-hostinger-to-bench.md, .ci/rediacc_ci/ops/reset_bench.py, .ci/rediacc_ci/ops/bench_production.py, .ci/config/bench-production.json, .ci/rediacc_ci/ops/licence_expiry_drill.py, .ci/rediacc_ci/ops/notices_drill.py, .ci/rediacc_ci/ops/bench_access.py, .ci/config/bench-access-pinned.json, .ci/rediacc_ci/tests/test_ops_reset_bench*.py, .ci/rediacc_ci/tests/test_ops_bench_access.py, .ci/rediacc_ci/tests/test_ops_bench_production.py, packages/cli/src/commands/config.ts, packages/cli/src/commands/config-import-machine.ts, packages/cli/src/commands/__tests__/config-import-machine.test.ts, packages/cli/src/i18n/locales/*/cli.json, private/account/scripts/rotation/lib/config.ts, private/account/tests/integration/rotation-observability-restart.test.ts, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, docs/agent-reference/bench-login.md, agent/plans/PLAN-product-domain-rename.md
Live-Proof: bench, hostinger -- bench proves the guards and the WAF pins; hostinger proves the re-licence, the schedule, a verified store, a restore test per repo and one scheduled run of its own timer, all through --config eu-bench.
Owner: d778be9d
Updated: 2026-11-13
First-Seen: 2026-11-13
Worklist: #ad4d5f4e, PR-TASK 79b7e92e

## Context (checked 2026-11-13 by the planning agent; a writer re-reads each before relying on it)

1. hostinger in eu-remote (~/.config/rediacc/eu-remote.json, structure only): account server https://eu.rediacc.cloud, channel edge, remote linked to the eu config store. Machine hostinger at 72.61.137.225:22, user muhammed, datastore /mnt/rediacc, infra baseDomain rediacc.io, publicIPv6 2a02:4780:c:e9b5::1, backupStrategies nightly-hot (hot, `0 2 * * *`, bandwidthLimit 12M, repoTargets mail rpo 5m, retention 7/7/4/6, destination hosted). 12 repos placed (mail with tags latest and pre-dms17, gitlab, nextcloud, erpnext, observability with latest and lab, mautic, marketing, hermes, miscellaneous, demo-heartbeat, demo-stackoverflow with latest and proxytrial, ops).
2. eu-bench.json already holds hostinger (machine equal by hash, plus maintenanceWindow 00:00-01:00, no strategy bound) and 11 of the repos (tags equal by hash; mail lacks pre-dms17, observability lacks lab, ops absent). eu-remote, eu-bench and eu-edge share one remote configId.
3. Licences: a repo licence file is `/var/lib/rediacc/license/repos/<guid>/<keyId>.json` keyed by signer fingerprint (private/renet/pkg/license/store.go:21, :277); bench signs with the production key (docs/agent-reference/bench-login.md), so a bench licence replaces the eu one in place. The renewal and backup-session server is the signed `renewalUrl` (private/renet/pkg/license/renew.go:26-29, :183-205; private/renet/cmd/renet/backup_endpoints.go:26-51). The move is `rdc --config eu-bench subscription refresh -m hostinger --adopt-origin` (packages/cli/src/commands/subscription.ts:538-548, packages/cli/src/commands/subscription-actions.ts:489-514); a plain refresh leaves another server's licences alone.
4. Guards against mixed accounts: the CLI pre-flight refuses a backup verb when an installed licence names another origin (packages/cli/src/services/backup/backup-store-universe.ts:115-176); every unit carries `--expect-account-server` (packages/cli/src/services/backup/backup-schedule-unit-generator.ts:228-235) and renet refuses a mismatch (private/renet/cmd/renet/backup_endpoints.go:155-176); units are named by strategy (packages/cli/src/services/backup/backup-schedule-reconcile.ts:109-114), so a push from eu-bench replaces the eu units in place and a later eu push would put them back (C8).
5. hostinger calls bench itself: the unit's ExecStartPre runs `renet license renew --jitter` (packages/cli/src/services/backup/backup-schedule-unit-generator.ts:355-366), and sessions and reports go to the licence host; chunk uploads go to presigned R2 URLs outside the zone rule.
6. The bench WAF: one zone rule blocks every address not listed except health GETs and the Stripe webhook (.ci/rediacc_ci/ops/bench_access.py:15, :59-63, :136-148); entries expire after 7 days and the list is capped at 5 with oldest-first eviction (:17, :52, :198-221), so without a change hostinger would get 403 within 7 days.
7. The headless login exists: `npm run login:bench` (package.json:420) with profile bench-login (REDIACC_BENCH_EMAIL, _PASSWORD, _TOTP_SEED, _MASTER_PASSWORD; .ci/config/secret-supply.json:528-537); bench config tokens bind to their first IP like eu's (private/account/src/services/config.service.ts:1468-1535), and on bench the remedy is a fresh headless login.
8. Bench dangers: reset_bench drops every bench D1 table and empties configs-bench with no production check (.ci/rediacc_ci/ops/reset_bench.py:5, :36-46); deploy_bench deploys whatever tree is checked out (.ci/rediacc_ci/ops/deploy_bench.py:1-9); the drills delete D1 rows by subscription id (.ci/rediacc_ci/ops/licence_expiry_drill.py:171-181, .ci/rediacc_ci/ops/notices_drill.py:275-278); PLAN-d1-eu-jurisdiction fences bench writes and relocates backups-bench.
9. Bench capacity: objects live under `t/<subscriptionId>/l/<grandGuid>/` (private/account/src/services/backup-chunk-store.ts:46-57); quota is the plan default unless `subscriptions.storage_quota_bytes` is set (private/account/src/db/schema.ts:128); over quota is BACKUP_QUOTA_EXCEEDED (private/account/src/services/backup-storage.service.ts:1472).
10. Config writes go through `updateSyncedConfig` (packages/cli/src/services/config/synced-write.ts:1-13); no verb copies repo GUIDs and credentials between configs; `config remote disable --local --yes` unlinks without the server (packages/cli/src/commands/config-remote.ts:518-533) and `machine remove --force` changes the config only (packages/cli/src/commands/machine/register.ts:157-189).
11. Other eu-remote references: the OTLP rotation restarts observability through `rdcConfig: 'eu-remote'` (private/account/scripts/rotation/lib/config.ts:428, its test :20-21); PLAN-product-domain-rename L10 and L11 use `--config eu-remote` (agent/plans/PLAN-product-domain-rename.md:199-214).

## Design

1. One account per machine, switched in one window: re-licence (adopt-origin), bind, schedule, run the unit at once, outside 01:45-03:00Z and right after a green eu run of hostinger's timer. Until a repo's first bench snapshot commits, its newest copy is the last eu run.
2. The data-loss rule: rediacc-backups-eu, backups-eu and token b38b0881 stay until C7 (first scheduled bench run, verified, after C5 store verify and C6 a restore test of every repo). The Cloudflare cleanup's deletion of rediacc-backups-eu waits on C7.
3. Bench becomes production for one subscription: `.ci/config/bench-production.json` declares the protected subscription id, machine and reason; reset_bench refuses every mode while it declares anything, and also when live D1 holds manifests for a declared subscription; the drills' cleanup refuses a declared id; no override flag.
4. Pinned bench allowlist entries in `.ci/config/bench-access-pinned.json` ({ip, label, reason, plan}) for 72.61.137.225 and 2a02:4780:c:e9b5::/64: never expire, never evicted, outside MAX_IPS, rewritten by every mutating run; `remove`/`clear` refuse them; new read-only `verify-pinned` exits 1 when one is missing.
5. A config import verb: `rdc config import-machine <machine> --from <config> [--dry-run] [-o json]` copies, through `updateSyncedConfig`, the machine entry when absent, every repo placed on it with every tag, and each bound strategy (differing: refused unless `--strategy-from-source`); a same name with a different GUID refuses; output names only; a second run reports 0 changes.
6. A credential escrow outside bench: bws entry `HOSTINGER_REPO_CREDENTIALS_ESCROW` (name -> {repositoryGuid, credential} per tag) under a new `hostinger-escrow` profile, written through the environment only.
7. Retire eu-remote and eu-edge for hostinger locally: `config remote disable --local --yes`, then `machine remove hostinger --force -y`; the files stay as an archive.

## Boxes

### Wave 0: read-only
- [ ] P0 [live] Inventory through eu-bench or SSH: each repo's installed renewalUrl origin (`./rdc.sh --config eu-bench machine status hostinger --licenses -o json`), `repo list -m hostinger -o json` mapping all GUIDs to names, datastore free space, bench `subscription status -o json` and `backup usage -o json`, `bench_access list`, the bench HTTP code from hostinger over IPv4 and IPv6, and the last run of hostinger's backup timer from its journal.
  Local-route: hostinger -- every read runs through eu-bench and term connect; the backup run is hostinger's own systemd timer, read from journalctl.
  Accept: `npm run login:bench` rc 0 plus every read rc 0, recorded in this plan.

### Wave 1: writers
- [x] W1 [writer] The bench production guard (Design 3): `bench_production.py`, `bench-production.json`, reset_bench refusals, drill cleanup refusals.
  Tests: a declared file makes `--yes`, `--d1-only` and `--r2-only` exit 2 before any credential is read; an empty file passes; the D1 check refuses on planted rows; drill cleanup with a declared id exits 1 without deleting.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_bench_production.py -q` rc 0, plus the reset_bench tests rc 0
    (ticked) 2026-11-13T11:06:40Z by d778be9d: commit:07efc580b6 bench_production guard; pytest bench_production + reset_bench names + drills 97 passed
- [x] W2 [writer] bench_access pinned entries and `verify-pinned` (Design 4).
  Tests: a pinned entry survives 30 days and a full rotating list; `remove` and `clear` refuse it; a hand-deleted pin returns on the next `add-current`; `verify-pinned` exits 1 when one is absent.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_ops_bench_access.py -q` rc 0
    (ticked) 2026-11-13T11:01:11Z by d778be9d: commit:e3c2d2ef12 bench_access pins + verify-pinned; pytest test_ops_bench_access 67 passed
- [x] W3 [writer] `rdc config import-machine` (Design 5) with i18n in every locale.
  Tests: absent repos and tags added; equal entries no-op; a same-name repo with a different GUID refuses; a differing strategy refuses without `--strategy-from-source`; no credential, key or GUID value in output; the write goes through `updateSyncedConfig`.
  Accept: `cd packages/cli && npx vitest run src/commands/__tests__/config-import-machine.test.ts` rc 0, plus `npm run check:i18n` rc 0
    (ticked) 2026-11-13T12:02:54Z by d778be9d: commit:3cbf695ba106 vitest passed 11 at rc=0 on the landed tree. DEPS-WAIVED: the import-machine verb is pure CLI code and needs no output of the prerequisite plan
- [x] W4 [writer] The rotation tool `rdcConfig` and its test move to eu-bench. Accept: `cd private/account && npx vitest run tests/integration/rotation-observability-restart.test.ts` rc 0
    (ticked) 2026-11-13T11:01:16Z by d778be9d: commit:df30b6993d rotation rdcConfig eu-bench; vitest rotation-observability-restart 9 passed
- [x] W5 [writer] A `hostinger-escrow` profile in secret-supply.json binding `HOSTINGER_REPO_CREDENTIALS_ESCROW`, mapped in bws-secret-map.json. Accept: `npm run check:ci-secret-supply` rc 0
    (ticked) 2026-11-13T11:06:41Z by d778be9d: commit:a61e7b99cb hostinger-escrow profile; check:ci-secret-supply rc 0

### Wave 2: bench readiness (after W1-W5 land and PLAN-d1-eu-jurisdiction's bench wave is ticked)
- [ ] L1 [live] Pin hostinger with `bench_access add-current` and the pinned file in the tree. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access verify-pinned` rc 0, and P0's two curls from hostinger print a code other than 403
- [ ] L2 [live] Bench capacity: `storage_quota_bytes` on the operator's bench subscription at least 1 TiB (or ENTERPRISE), and the repo-licence issuance cap covers 15 or more repos. Accept: `./rdc.sh --config eu-bench subscription status -o json` shows quota >= 1099511627776 and room in the cap
- [ ] L3 [live] `./rdc.sh --config eu-bench config import-machine hostinger --from eu-remote --dry-run`, then for real. Accept: a second `--dry-run` reports 0 changes, and `repo list -m hostinger -o json` names every repo with no GUID-only row
- [ ] L4 [live] Write `HOSTINGER_REPO_CREDENTIALS_ESCROW` from eu-bench's hostinger tags through the environment. Accept: the profile's JSON entry count equals L3's tag count
- [ ] L5 [live] Fill the protected subscription id in bench-production.json (a reviewed commit) and prove the guard. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.reset_bench --yes` exits 2 with the production refusal before any Cloudflare call

### Wave 3: cutover (one window outside 01:45-03:00Z, right after a green eu run)
- [ ] C1 [live] Confirm the last eu run of hostinger's backup timer committed every repo, from the journal.
  Local-route: hostinger -- `term connect hostinger -c 'journalctl -u rediacc-backup-nightly-hot.service --since -2d'`.
  Accept: the journal tail shows the unit `status=0/SUCCESS` after the last 02:00 start
- [ ] C2 [live] Re-licence: `./rdc.sh --config eu-bench subscription refresh -m hostinger --adopt-origin`. Accept: `machine status hostinger --licenses -o json` shows https://bench.rediacc.cloud for every repo, and `sudo renet license renew --force --output json` on hostinger reports renewed for every blob
- [ ] C3 [live] `./rdc.sh --config eu-bench backup strategy bind nightly-hot -m hostinger`, then `backup schedule -m hostinger`. Accept: `backup schedule -m hostinger --dry-run` reports unchanged, and the unit holds `--expect-account-server https://bench.rediacc.cloud`
- [ ] C4 [live] First bench backups through the scheduled unit (`systemctl start --no-block rediacc-backup-nightly-hot.service`). Accept: `backup status -m hostinger -o json` shows a successful run after C3 for every repo
- [ ] C5 [live] Store verify. Accept: `./rdc.sh --config eu-bench backup verify --store` rc 0, and `backup usage -o json` shows a snapshot per repo in backups-bench
- [ ] C6 [live] A restore test for every repo under a `-rt` name, deleted by GUID by the tool (a repo larger than the free space restores to l1vm). Accept: `backup verify <repo>@hostinger --restore-test -o json` gives `proven` for each, and `repo list -m hostinger -o json` is identical before and after
- [ ] C7 [live] The first scheduled run of hostinger's timer on bench.
  Local-route: hostinger -- the run is hostinger's own systemd timer at 02:00; read through `backup status` and journalctl.
  Accept: `backup status -m hostinger -o json` shows a run after the next 02:00 verified for every repo, the journal shows `license renew` without refused or error, and `bench_access verify-pinned` rc 0
- [ ] C8 [live] Retire eu-remote and eu-edge for hostinger (Design 7). Accept: `machine list -o json` in both lacks hostinger, and hostinger's `systemctl list-timers 'rediacc-backup-*'` is identical before and after
- [ ] D1 [writer] PLAN-product-domain-rename: L10 closes as superseded by this plan; L11 gains a dependency on C7 and its Accept moves to `--config eu-bench`; b38b0881 deactivation waits on C7. docs/agent-reference/bench-login.md gains "bench carries hostinger production data: reset guard, pins, escrow". Accept: `npm run check:ci-plan-record` rc 0

## Risks
1. Bench runs unmerged account code; once rediacc-backups-eu is gone a deployed GC or retention bug could remove the only off-site copy (hostinger still holds the live data). An R2 bucket lock on the protected prefix is a possible follow-up.
2. A restore from the eu buckets after C2 needs an eu licence and the operator's eu login, which is why C5 and C6 cover every repo before C7.
3. A PLAN-d1-eu-jurisdiction write fence after C2 fails renewals and commits while it holds: keep it outside 01:45-03:00Z and short.
4. If hostinger's IP or IPv6 /64 changes, renewals get 403; `verify-pinned` and C2's renew show it.
5. Quota or issuance refusals if L2 is skipped.
6. Any eu-remote or eu-edge command against hostinger between L1 and C8 can push the units back to eu: run nothing through those configs in the window.
7. The planning agent printed the `mail` repo's tags from eu-remote.json (credential, two SSH private keys, GUIDs) into its own local transcript by mistake; rotating them is an operator decision, not a box here.

# Deploy inventory and capability survey (2026-11-28)

Operator order ASKED:2026-11-28T13:41Z, phase 1. Four read-only surveys (inventories, health and alerting, cron and scheduled work, release coverage and gates), each citing file:line. Nothing here was built by the survey.

## Capability by target kind

Legend: Y exists, P partial, N missing.

| Capability | Shared region (eu/us/asia) | Bench (3 regions) | Enterprise company | Ring canary | Preview (PR / release) | Test resource (drill, lab) | Cron job |
|---|---|---|---|---|---|---|---|
| Listed in one inventory | P: regions.json prod names, no signer or control-D1 names | P: regions.json `bench{}` blocks, inconsistent naming (eu `account-bench`, us/asia `-bench-<r>`) | P: control D1 `companies` table (enterprise/registry.py:62-110); per-company tomls gitignored (workers/account/.gitignore:1) | P: rings_run.py:201 ring order, no inventory row | N: names only as cleanup_versions.py:769-790 regexes | N: cloud-inventory.json not built (PLAN-cloud-inventory INV1) | P: crons in tomls (account `17 * * * *`, `0 3 * * *`, `*/5 * * * *`; ops-health `*/10`), no owner field |
| Reconciled against the live account | P: cf_leftovers.py (report only, carried = wrangler globs + regions.json strings, :48-50, :245-259) | P: same | N: companies reported as masked leftovers (cf_leftovers.py:17) | N | P: cleanup_versions reaps `pr-*`/`pv-*` by regex | N: 36 leftovers today, nothing reaps them | N |
| Ongoing probe on a real API route | Y: ops-health `health:account-<r>` /account/api/v1/health (targets.ts:185-203) | N: regionEndpoints reads only `domain`, bench never probed; portal_health --target bench unwired | N | N | n/a | n/a | n/a |
| Alert route | P: SES mail from ai@notify.rediacc.cloud to OPS_ALERT_EMAILS, mixed with routine alerts (the 07:40Z alert was sent and drowned) | N | N | N | n/a | n/a | n/a |
| Release smoke on a real API route | N: verify_edge_endpoints probes only server-info (:401-425); verify_stable only warns (:200) | N: deploy_bench smoke is server-info (:964, :1081) | N: rings_run re-smoke is proxy-smoke only (:408) | N: same | P: PR smoke-test-preview.ts calls /account/api/v1/health (:77) but deploys the www Worker, not the production entry | n/a | n/a |
| Preview stage before deploy | N (planned PLAN-preprod-simulation P1-P3) | N | N | N | itself | n/a | n/a |
| Boot test under its config | N (planned PLAN-account-api-health B1) | N | N | N | N | n/a | n/a |
| Config parity with production | n/a | N: bench tomls lack ACCOUNT_FORENSICS_S3_* (planned B2) | N | N | N | n/a | n/a |
| Owner and TTL | n/a | n/a | n/a | n/a | P: PR number via regex | N | N |
| Teardown | n/a | n/a | n/a | n/a | P: ops-cleanup-preview.yml + reaper | N | n/a |
| Last-run staleness alarm by another party | n/a | n/a | n/a | n/a | n/a | n/a | P: ops-health only (state.ts:387-388, pulled by ops_health.py offbox and wl_opshealth); account crons record no last run; GitHub schedules (except ci-weekly ingest) and local routines have none |
| Gate enforcing the pairing | N: none checks "every region has X" | P: proof-tiers.json live pairing per plan, not per target | P: enterprise-proof is bench-only (proof-tiers.json:509) | N | P: CI Complete needs smoke-test-preview, a skip bypasses it | N | N |

Other deployed Workers with no probe: signer (no smoke in deploy_signer.py), MCP (deploy-time smoke only, deploy_mcp.py:477), www (no ongoing probe), mta-sts. Nothing pushes an alert when ops-health itself stops: every watcher pulls (ops_health.py:913-944, wl_opshealth.py:433-441, check:ci-ops-health).

## Overlaps and disagreements

- At least seven hand-copied region tuples outside regions.json (proof/live_tier.py:54, ops/login_bench.py:55, ops/root_login.py:45, ops/backup_d1.py:30, housekeeping/cf_retire.py:46, quality/backup_credential_isolation.py:72, packages/shared/src/mcp-host/oauth/region.ts:8).
- Signer Workers are carried only by regions.json bench fields; prod signers appear in no inventory, and `secret-supply.json:1099` omits signer-bench-asia.
- `wrangler.dev.toml` (rediacc-proxy-dev) and private/account/wrangler.toml (account-server, account-db) are carried by the glob but by no inventory.
- Two reapers with no shared owner field: cleanup_versions (pr-/pv- regex) and cf_retire.py:46-50 (keeps proof-loss), which disagrees with PLAN-cloud-inventory treating proof-loss as a leftover.
- `private/run_account.py:92` names wrangler.edge-{eu,us,asia}.toml, which do not exist.
- proof-tiers.json has no signer, mcp, ops-health or mta-sts surface.
- wl_schedred.py reads every scheduled workflow's created_at (:175-195) but treats a missing run as no verdict (:205), so a schedule that stops firing is invisible.

## Extend, do not rebuild

- regions.json stays the source for shared and bench rows; the inventory references it rather than copying names.
- The enterprise control D1 stays the company source; the inventory reads it through enterprise/registry.py.
- cf_leftovers.py becomes the live-account reconciler of the inventory (both directions), and PLAN-cloud-inventory INV1-INV5 (registry, gate, reaper, triage, creation guard) carry test resources and previews.
- workers/ops-health targets.ts regionEndpoints grows rows from the inventory (bench, companies, account-api), and its state/mail machinery carries the emergency class of PLAN-account-api-health A1.
- wl_schedred.py grows the scheduled-run staleness check; ops-health ingest carries heartbeats from the account crons.
- PLAN-account-api-health (smoke S1/S2, boot B1, parity B2, coverage P1) and PLAN-preprod-simulation (preview stage) supply the capabilities; the new gate only checks that each target row has them.

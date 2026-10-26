# Cloudflare spend guards

Lookup material for the guards from `agent/plans/PLAN-cloudflare-spend-guard.md`. `.ci/config/cf-spend-guard.json` is the one source of thresholds: the notification limits, the weekly report ceilings and the sampling ceiling each read it. Raising a threshold means editing that file, then running the command named under the guard.

| Guard | Where | Reads | Fails on |
|---|---|---|---|
| Usage notifications | `.ci/rediacc_ci/ops/cf_notifications.py` | `notifications.products` | a product Cloudflare refuses (exit 1) |
| R2 lifecycle backstops | `.ci/rediacc_ci/ops/r2_lifecycle.py` | rules in code | a missing, drifted or planted rule (`--check`, exit 1) |
| Weekly usage report | `.ci/rediacc_ci/ops/cf_usage_report.py`, `.github/workflows/cf-usage-report.yml` | `report` | an item over a ceiling or the maintenance log line (exit 1), an unreadable source (exit 2) |
| Sampling gate | `.ci/scripts/quality/check_worker_observability_budget.py` | `worker_observability` | a Worker over the ceiling or with no explicit rate (exit 1) |
| Leftovers report | `.ci/rediacc_ci/housekeeping/cf_leftovers.py` | none | an unreadable listing or a missing `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` |

## Usage notifications

`cf_notifications` makes the account's `billing_usage_alert` policies match `notifications.products`: one policy per product, named `spend-guard:<product>`, emailed to the operator address (`WK_OPERATOR_EMAIL`). It upserts by name, deletes a `spend-guard:` policy the JSON no longer names, and a second run on an unchanged JSON prints `0 change(s)`.

```bash
PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile rotation -- \
    env PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_notifications --dry-run   # drop --dry-run to write
```

Limits (per billing cycle, in the product's base unit):

| Product | Limit |
|---|---|
| `worker_requests`, `worker_standard_request` | 20,000,000 requests each (both are set because the billed line item is undocumented) |
| `worker_standard_cpu_ms` | 60,000,000 CPU ms |
| `r2_storage` | 200,000,000,000 bytes (operator ruling 2026-10-23: keep 20 release folders, alert at 200 GB) |
| `r2_class_a_operations` | 2,000,000 |
| `r2_class_b_operations` | 20,000,000 |

To raise one, change its `limit` and run the command above without `--dry-run`. The API accepts only the product names it lists (`products_accepted_by_the_api` in the JSON). A name it refuses answers `17106 Invalid product selection.`, prints `UNAVAILABLE <product>` and fails the run.

Two products have no alert: Workers Observability (ingestion and storage) and Containers. Every candidate name was refused on 2026-10-23, and the evidence sits under `notifications.unavailable`. They print `UNAVAILABLE <name> (recorded ...)` on each run without failing it. Their fallbacks:

- The account-level `Default budget alert (auto-created)` (`billing_budget_alert`, 10 USD total spend, not managed here) covers both in dollars.
- Containers: the weekly report below, and the instance cap in `check_proxy_cost_guard.py` (`MAX_INSTANCES_BUDGET`, 25 per deployable config, one config per target).
- Observability: the weekly report's log and sampling checks, and the sampling gate.
- Dashboard path, for a product the API cannot create or to inspect a policy: Dashboard > Notifications > Add > Usage Based Billing. A product Cloudflare starts offering there is added to `notifications.products` and applied with the command above.

## Sampling decision table

Decision T2 of the plan (set `head_sampling_rate` and `persist` per config) is still open: no config has been changed. The measured basis and the ruling in force:

- T4 measured total Worker telemetry at about 0.9 percent of the 50 GB included ingestion allowance (item `c0b8fc69`). Operator ruling `ASKED:2026-10-26T05:02Z`, "Keep 1 everywhere": no Worker samples below 1; revisit if volume crosses 25 percent. This is `sampling_ceiling` 1 with an empty `sampling_exempt` in the JSON.
- Every enabled `logs` and `traces` signal under `workers/*/wrangler*.toml` currently carries `head_sampling_rate = 1` and `persist = false` where checked, with data exported by OTLP destination. No config sets `persist = true`, and `persist_disallowed` lists `workers/*/wrangler*.toml`.
- The plan's earlier target (0.1 for stable account and www traces) was written before the measurement and is superseded by the ruling unless T2 closes otherwise. This table is rewritten when T2 records its per-config decision.

No rate goes below 1 while that ruling stands; lowering one needs a new operator ruling first, after which only the config changes. To raise a rate above `sampling_ceiling`, raise the ceiling in the JSON with a `sampling_ceiling_reason`, or list the config in `sampling_exempt` as `"<config>": {"rate": <n>, "reason": "..."}`. An exemption is never inferred.

## R2 lifecycle backstops

`r2_lifecycle` writes lifecycle rules to `rediacc-releases` (and `rediacc-staging` when the listing shows it). The application decides first (`housekeeping/cleanup_versions.py` Phase 8 deletes `<fmt>/dryrun-*` past 7 days and `<fmt>/pr-N` past 3 days); the rules catch only what it missed:

- `spend-guard-pr-<fmt>` expires `<fmt>/pr-` at 14 days;
- `spend-guard-dryrun-<fmt>` expires `<fmt>/dryrun-` at 21 days;
- `spend-guard-multipart` aborts incomplete multipart uploads after 1 day (platform default is 7).

`<fmt>` is each of `cli npm apt rpm apk archlinux`, which makes 13 rules.

```bash
PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile rotation -- \
    env PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_lifecycle --check   # exit 1 on a missing, drifted or planted rule
PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile rotation -- \
    env PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_lifecycle list
PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_lifecycle apply     # idempotent
```

Auth is `cf_auth.resolve`: a ready `CF_MANAGEMENT_TOKEN`, or the Global API Key pair (bws profile `rotation`), which mints a token with Workers R2 Storage Write and destroys it afterwards. To change a window, edit `PR_EXPIRE_DAYS`, `DRYRUN_EXPIRE_DAYS` or `MULTIPART_ABORT_DAYS` in the module and run `apply`.

**Backup-bucket exclusion.** A bucket matching `PROTECTED_PATTERNS` (`rediacc-backups*`, `*-backups-*`, `rediacc-configs*`, `*-configs-*`) is refused before any call, and only `ALLOWED_BUCKETS` are ever written. The account Worker's chunk GC is authoritative for backups, and a lifecycle expiry would delete a chunk the index still references. `list` and `--check` read the protected buckets and report any rule beyond the platform default as `PLANTED`.

## Weekly usage report

`.github/workflows/cf-usage-report.yml` runs `cf_usage_report` Mondays 06:23 UTC and on `workflow_dispatch`, appending the output to the step summary. It is read-only (GraphQL Analytics reads and one log count). Run locally under the `cf-usage-report` bws profile:

```bash
PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile cf-usage-report -- \
    env PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_usage_report
gh workflow run cf-usage-report.yml
```

Each line is `OK` or `OVER` with the value and its ceiling. Ceilings come from the `report` object of the JSON, key by key, and from `DEFAULT_CEILINGS` in the module otherwise: `workers_requests_month`, `workers_cpu_ms_month`, `r2_storage_bytes`, `r2_class_a_month`, `r2_class_b_month`, `d1_storage_bytes`. Each is compared with the account total.

**Container alarm.** Cloudflare offers no usage alert for Containers, so this is the alarm. Each Containers application (one proxy target) is compared with `containers_memory_gib_seconds_month` (20,000,000) and `containers_vcpu_seconds_month` (2,500,000), each about 50 USD a month at 0.0000025 USD per GiB-second and 0.00002 USD per vCPU-second, so one target at both ceilings estimates about 100 USD. `containers_total_usd_month` (350) bounds the estimated sum over 7 targets. The estimate leaves out the monthly included amounts, so it is an upper bound. Operator ruling `ASKED:2026-10-26T16:35Z`, "Raise to ~$50/target". An application over a ceiling is an `OVER` line naming the estimated cost.

The report also counts the account Worker's `Nightly maintenance is NOT running` line over seven days in Loki (`OBS_GRAFANA_READ_TOKEN`), falling back to the Workers Observability telemetry query, and prints `ALERT maintenance ...` when it was logged.

Exit 0 when nothing is over, 1 on any `OVER` or `ALERT`, 2 when a read came back empty or failed, because a guard that cannot look has not passed. To raise a ceiling, set its key under `report` in the JSON (record the reason in `report_reason`).

## Sampling gate

`check:ci-worker-observability-budget` (lane `quality-static`) reads every `workers/*/wrangler*.toml`, excluding `wrangler.template.toml` and `wrangler.dev.toml`:

- each enabled `logs` or `traces` signal needs an explicit numeric `head_sampling_rate` in (0, 1], at or under `worker_observability.sampling_ceiling` (1 today), or under the rate in `sampling_exempt` for a config named there;
- a config matching a `persist_disallowed` glob never sets `persist = true`, and a signal that does not persist names at least one destination;
- a signal or table with `enabled = false` is not judged.

```bash
npm run check:ci-worker-observability-budget
python3 .ci/scripts/quality/check_worker_observability_budget.py --selftest
```

Exit 1 on findings, 2 when a control fails or no verdict is possible (zero configs parsed, an unreadable config, a missing `worker_observability` object).

## Leftovers report

`cf_leftovers` lists, with GET only, what no PR cleanup owns: Workers scripts named by no wrangler config (PR previews `pr-<n>` excluded), D1 databases matching `edge-*` or `*-bench` that no config binds, Workers routes whose script is absent, and custom domains whose service is absent. It deletes nothing. A finding is a report line and exits 0, so only an unreadable listing or an incomplete environment exits 1. The `cf-leftovers` job of `.github/workflows/housekeeping.yml` runs it daily at 03:00 UTC.

```bash
PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile cf-usage-report -- \
    env PYTHONPATH=.ci python3 -m rediacc_ci.housekeeping.cf_leftovers
```

A reported leftover is deleted by hand after its owner is confirmed; the report never acts.

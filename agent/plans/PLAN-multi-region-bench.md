# PLAN: Multi-region bench

Status: approved -- operator ASKED:2026-11-13T13:55Z: "Approve always-on", Q1 "Copy production", and on naming "make all 3 consistent. bench-eu.rediacc.cloud it should be."
Depends-On: PLAN-d1-eu-jurisdiction.md
Priority: P2 -- draft awaiting an operator cost decision; nothing waits on it today
Concurrency: exclusive -- it adds per-region bench objects and hosts and re-keys the single-bench names (deploy records, bench configs, signer targets) that other plans read while they run bench boxes.
Owns: agent/plans/PLAN-multi-region-bench.md, regions.json, packages/shared/src/regions/data.json, workers/account/wrangler.bench*.toml, workers/proxy/wrangler.bench*.toml, .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/ops/reset_bench.py, .ci/rediacc_ci/ops/bench_preflight.py, .ci/rediacc_ci/ops/bench_production.py, .ci/config/bench-production.json, .ci/rediacc_ci/ops/bench_access.py, .ci/rediacc_ci/ops/login_bench.py, .ci/rediacc_ci/ops/live_proof.py, .ci/rediacc_ci/proof/live_tier.py, .ci/rediacc_ci/deploy/deploy_signer.py, .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/deploy/proxy_configs.py, .ci/rediacc_ci/deploy/console_executor.py, .ci/rediacc_ci/deploy/deploy_record.py, .ci/rediacc_ci/enterprise/*.py, .ci/rediacc_ci/quality/region_consistency_offline.py, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/well-known.env, .ci/config/proof-tiers.json, .ci/config/cf-spend-guard.json, .claude/hooks/trapguard/dispatch.py, .claude/rediacc_hooks/guards/block_settled_questions.py, docs/agent-reference/bench-login.md, .claude/skills/deploy/SKILL.md, .ci/rediacc_ci/tests/**
Live-Proof: bench -- draft for an operator cost decision; once approved, L1-L5 and LP-bench prove each new region on bench
Owner: d778be9d
Updated: 2026-11-13
First-Seen: 2026-11-13

## Ask

One bench per production region (eu, us, asia), so region-scoped behaviour is proven on bench instead of parked as "bench cannot prove", and so a regional Cloudflare incident can be reproduced and rehearsed without touching production. The decision turns on cost, so section *Cost model* is the main deliverable. Research inputs were measured read-only on 2026-11-13; no Cloudflare object was created, deployed or deleted.

## Context (checked 2026-11-13 against the tree; a writer re-reads each before relying on it)

1. Today's bench is eu-only. The account Worker `account-bench` serves `bench.rediacc.cloud` (workers/account/wrangler.bench.toml:12, :18-20) with `REGION = "eu"` (workers/account/wrangler.bench.toml:23), and its header still says "Single non-regional environment (no us / asia siblings)" (workers/account/wrangler.bench.toml:7). The proxy `proxy-bench` serves `proxy.bench.rediacc.cloud` (workers/proxy/wrangler.bench.toml:13, :19-21) with `REGION = "eu"` (workers/proxy/wrangler.bench.toml:25) and binds `account-bench` twice (workers/proxy/wrangler.bench.toml:37-47).
2. regions.json carries no bench entry. Each region row has `d1 {name, location, jurisdiction}`, `r2`, `backupR2`, `r2Jurisdiction`, `workerName`, `proxyWorkerName`, `sesRegion`, `secretSuffix` (regions.json:7-16); the hints are eu `eeur`, us `enam`, asia `apac`, all `jurisdiction: null`, and only eu has `r2Jurisdiction: "eu"` (regions.json:7, :12, :22, :26, :37, :41). packages/shared/src/regions/data.json is held identical by `check:ci-regions-sync` (.ci/rediacc_ci/quality/regions_sync.py:6-8).
3. Two bench signers already exist as targets: `BENCH_REGIONS = ("eu", "us")` (.ci/rediacc_ci/deploy/deploy_signer.py:55), `control-bench-eu` and `control-bench-us` in `CONTROL_DATABASES` (.ci/rediacc_ci/deploy/deploy_signer.py:57-63). Both bench targets render from the same `wrangler.bench.toml` (.ci/rediacc_ci/deploy/deploy_signer.py:136-138), and the signer's `SHARED_HOSTS` is that toml's route list (.ci/rediacc_ci/deploy/deploy_signer.py:142-160, :318, :345), so both bench signers accept only `bench.rediacc.cloud` as a renewal host. No `bench-asia` target exists (workers/signer/.generated/ holds `wrangler.bench-eu.toml` and `wrangler.bench-us.toml` only).
4. The renewal host is enforced in the signer: `sharedHosts` defaults to `<region>.rediacc.cloud` (private/account/src/services/license-signer.service.ts:292) and a mismatch is `SIGNER_WRONG_HOST` (private/account/src/services/license-signer.service.ts:314, :332, :348). The caller stamps `https://<host>/account/api/v1/licenses/renew` (private/account/src/services/signer-probe.service.ts:69).
5. The account binds the eu bench signer by name with props `{tier = "shared", region = "eu"}` (workers/account/wrangler.bench.toml:107-111). WebAuthn is bound to the host: `WEBAUTHN_RP_ID = "bench.rediacc.cloud"` (workers/account/wrangler.bench.toml:26-27).
6. Single-bench assumptions in tooling: `deploy_bench` has one host, Worker and config (.ci/rediacc_ci/ops/deploy_bench.py:64-69), one deploy record `.ci/cache/live-deploys/bench.json` (.ci/rediacc_ci/ops/deploy_bench.py:365), signer targets from `BENCH_REGIONS` (.ci/rediacc_ci/ops/deploy_bench.py:781), `control_db ensure --bench` (.ci/rediacc_ci/ops/deploy_bench.py:800-804), and accepts no argument but `--seed-root`/`--set-root-password` (.ci/rediacc_ci/ops/deploy_bench.py:1024-1033). `reset_bench` confirms with "wipe bench" (.ci/rediacc_ci/ops/reset_bench.py:41-43) and reads names through `bench_names()` (.ci/rediacc_ci/ops/bench_preflight.py:21, :37). The proxy bench target is one hand-written `Target` with `REGION "eu"` (.ci/rediacc_ci/deploy/proxy_configs.py:199-215), and `TARGET_KEYS` is a literal (.ci/rediacc_ci/deploy/proxy_configs.py:65).
7. Hard eu-only refusals: `BENCH_REGION = "eu"` in deploy_proxy (.ci/rediacc_ci/deploy/deploy_proxy.py:65) with "--target bench refuses --region" (.ci/rediacc_ci/deploy/deploy_proxy.py:163); console_executor's `--company-bench refuses --region` (.ci/rediacc_ci/deploy/console_executor.py:45, :197-199); deploy_record's "--target bench refuses --region" (.ci/rediacc_ci/deploy/deploy_record.py:92-93), added by commit a55df8872f. The region-loss bench form hard-codes `signer-bench-eu` and records the cross-region gap (.ci/rediacc_ci/enterprise/proof.py:64-75, :436-447, :493-499).
8. Bench login and guards: `login_bench` pins `SERVER = BENCH_ORIGIN`, `CONFIG = "eu-bench"`, `BENCH_CONFIGS` and the remote config id (.ci/rediacc_ci/ops/login_bench.py:46-50); `live_proof --region` already takes `LT.REGIONS` (.ci/rediacc_ci/ops/live_proof.py:878; .ci/rediacc_ci/proof/live_tier.py:50) while its bench deploy kinds read one file each (.ci/rediacc_ci/proof/live_tier.py:39-40). The trapguard regex is the literal `eu-bench` (.claude/hooks/trapguard/dispatch.py:463), and block_settled_questions' `BENCH_NAMED` would not match `us-bench` because `-` is excluded before `bench` (.claude/rediacc_hooks/guards/block_settled_questions.py:200). `eu-bench` appears in 59 files tree-wide outside agent/ (research sweep).
9. The bench WAF is ONE custom rule found by its description (.ci/rediacc_ci/ops/bench_access.py:52, :61); its host list is every route in `workers/*/wrangler.bench.toml` (.ci/rediacc_ci/ops/bench_access.py:100-113), so a file named `wrangler.bench-us.toml` is not read today. `MAX_IPS = 5` (.ci/rediacc_ci/ops/bench_access.py:55); hostinger's two addresses are pinned in .ci/config/bench-access-pinned.json.
10. The bench production guard refuses every reset mode while any entry is listed (.ci/rediacc_ci/ops/bench_production.py:91), and an entry has no region field (.ci/config/bench-production.json:2-3). Once PLAN-hostinger-to-bench L5 lists hostinger's subscription, a us or asia reset would be refused too unless the entry gains a region.
11. Jurisdiction plumbing landed for bench: `control_db.jurisdiction(bench=True)` takes the jurisdiction the bench toml declares for its buckets, "so the whole bench is one jurisdiction" (.ci/rediacc_ci/enterprise/control_db.py:182-194). agent/plans/PLAN-d1-eu-jurisdiction.md Design 1 (agent/plans/PLAN-d1-eu-jurisdiction.md:30) recreates `account-bench`, `control-bench-eu` and `control-bench-us` as `-j` databases in jurisdiction eu, and the bench buckets in eu (agent/plans/PLAN-d1-eu-jurisdiction.md:62); it gives no rule for a us or asia bench.
12. PLAN-hostinger-to-bench moves the production machine hostinger onto the eu bench now: its licences are re-issued with renewalUrl `https://bench.rediacc.cloud` (agent/plans/PLAN-hostinger-to-bench.md:74) and its backup unit carries `--expect-account-server https://bench.rediacc.cloud` (agent/plans/PLAN-hostinger-to-bench.md:75). From then on the eu bench carries production data, which is the main reason incident rehearsal belongs on us and asia.
13. Spend guard: .ci/config/cf-spend-guard.json has account-wide ceilings (workers 20M requests, 60M CPU ms, R2 5 TB, Class A 2M, Class B 20M, D1 4 GB) and per Containers application `containers_target_usd_month` 50, plus `containers_total_usd_month` 350; there is no bench line. The only dollar alarm is Cloudflare's own `Default budget alert` at 10 USD total spend (.ci/config/cf-spend-guard.json:41).

## Certificates and names

The tree records no ACM or Total TLS configuration. Universal SSL covers the apex and one label only, so `proxy.bench.rediacc.cloud` (two labels under the zone) is not covered by Universal SSL. The Workers Custom Domains page answers which certificate covers it: "Creating a Custom Domain will also generate an Advanced Certificate on your target zone for your target hostname", "This includes multi-level subdomains such as `realms.app.example.com`", and "no separate Advanced Certificate Manager subscription is required" (https://developers.cloudflare.com/workers/configuration/routing/custom-domains/, fetched 2026-11-13). <!-- style-ok -->
So `proxy.bench.rediacc.cloud` is served by the Advanced Certificate its own Custom Domain generated, at no ACM charge; the token needs the certificate permission agent/plans/PLAN-proxy-cd-six-targets.md:81 (U2) records, which the deploy-proxy-bench token already has since proxy.bench is live. The research summary feared an ACM fee for two-level names; the fetched page refutes that for Workers Custom Domains. V0 confirms the live certificate pack read-only.

New names, one label under the zone for the account host (Universal SSL) and the same two-label shape as today for the proxy (Custom Domain certificate):

```
eu    bench.rediacc.cloud        proxy.bench.rediacc.cloud        (unchanged)
us    bench-us.rediacc.cloud     proxy.bench-us.rediacc.cloud
asia  bench-asia.rediacc.cloud   proxy.bench-asia.rediacc.cloud
```

Nothing extra is needed for the new names: each Custom Domain issues its own certificate on creation. The one-label alternative `proxy-bench-us.rediacc.cloud` avoids the generated certificate entirely, but breaks the `proxy.<account host>` pattern proxy_configs checks, so it is not recommended. Each new hostname is published in certificate transparency logs; for bench names that discloses nothing.

### The eu bench moves to bench-eu.rediacc.cloud (operator ruling)

Ruling ASKED:2026-11-13T13:55Z: the three benches are named consistently, `bench-eu.rediacc.cloud`, `bench-us.rediacc.cloud` and `bench-asia.rediacc.cloud`, with proxies at `proxy.bench-<r>.rediacc.cloud`. `bench.rediacc.cloud` is retired after the migration below. The draft's argument for keeping it (re-licensing hostinger and the bench machines, losing bench passkeys, rewriting `--expect-account-server`, touching the 59 `eu-bench` files) is the cost of this ruling, not a reason against it. The rdc config names stay `eu-bench`, `us-bench` and `asia-bench`, already consistent.

Sequencing with PLAN-hostinger-to-bench: hostinger is being re-licensed onto bench now. Steps 1-5 below come before that plan's re-licence step where possible, so hostinger is re-licensed once, straight onto `bench-eu`; if hostinger already renews against `bench.rediacc.cloud`, step 6 re-licences it a second time, outside 01:45-03:00Z and right after a green run of its timer.

The migration order is fixed by two refusals (the signer's host check and renet's account-server check), and each step is reversible until step 7:

```
1. workers/account/wrangler.bench.toml routes gain bench-eu.rediacc.cloud beside bench.rediacc.cloud;
   workers/proxy/wrangler.bench.toml likewise gains proxy.bench-eu.rediacc.cloud.
2. deploy_signer --target bench-eu and --target bench-us: SHARED_HOSTS now lists both hosts, so renewals to either pass.
3. deploy_bench, deploy_proxy --target bench: both hosts serve; bench_access picks up the new routes on its next run.
4. well-known.env WK_BENCH_ORIGIN and WK_PROXY_BENCH_HOST move to the new hosts and the generated twins are regenerated;
   login_bench SERVER follows; WEBAUTHN_RP_ID/ORIGIN move (bench passkeys are lost; login_bench uses TOTP and the master password).
5. ./rdc.sh --config eu-bench subscription login --server https://bench-eu.rediacc.cloud, then
   config remote enable ... --api-url https://bench-eu.rediacc.cloud (same config id 1880812c-2086-4daa-a620-8f84aa3b6e7c).
6. Per machine (hostinger first, outside 01:45-03:00Z, right after a green run of its timer):
   ./rdc.sh --config eu-bench subscription refresh -m <machine> --adopt-origin
   machine status <machine> --licenses -o json   -> every renewalUrl on bench-eu
   then ./rdc.sh --config eu-bench backup schedule -m <machine>   -> units carry --expect-account-server https://bench-eu.rediacc.cloud
   then one scheduled run of the unit on the new host.
7. Only after every licence names bench-eu and one scheduled hostinger run passed: drop bench.rediacc.cloud from both tomls,
   redeploy the signers (SHARED_HOSTS shrinks), then the account and proxy Workers. Old licences still naming the old host now fail renewal.
8. Docs, skill, guards and tests follow in the same commit as step 4.
```

## Jurisdiction and location hint per object

Rule: a bench object of region r takes the same data-location settings production region r has, read from regions.json, so the bench proves the production shape. After agent/plans/PLAN-d1-eu-jurisdiction.md lands, eu is jurisdiction eu for D1 and R2 on both production and bench. The fetched pages list D1 jurisdictions eu, fedramp and us, R2 jurisdictions eu, fedramp and us, and location hints wnam, enam, weur, eeur, apac and oc for both (https://developers.cloudflare.com/d1/configuration/data-location/, https://developers.cloudflare.com/r2/reference/data-location/, fetched 2026-11-13). A `us` jurisdiction is new relative to the research notes; production us does not use it (regions.json:22), so bench us does not either. Both pages say a hint is best effort and a jurisdiction is creation-only.

| Object | us bench | asia bench |
|---|---|---|
| D1 `account-bench-us` / `account-bench-asia` | no jurisdiction, `--location enam` | no jurisdiction, `--location apac` |
| D1 `control-bench-us` / `control-bench-asia` | no jurisdiction, `--location enam` (see Q1) | no jurisdiction, `--location apac` |
| R2 `configs-bench-<r>`, `backups-bench-<r>` | no jurisdiction, location hint `enam` | no jurisdiction, location hint `apac` |
| Queues `backup-replicate-bench-<r>` (+ `-dlq`) | no placement setting | no placement setting |
| Durable Objects (BackupReplicator, OrgExecutor, ExecutorCapacity) | placed near first use; no jurisdiction in code | same |
| Analytics Engine `telemetry_bench_<r>` | no placement setting | same |
| Containers (OrgExecutor) | follows the durable_object policy | same |

The conflict to settle: agent/plans/PLAN-d1-eu-jurisdiction.md:3 records the operator's "eu jurisdiction for all bench objects", which moves `control-bench-us` into eu, and .ci/rediacc_ci/enterprise/control_db.py:182-194 makes "the whole bench one jurisdiction". That ruling predates per-region benches; with them, a us control database in eu would make the us bench prove an eu placement. Q1 asks; the DEFAULT is the rule above.

## Inventory per region

Shared means one object serves all three benches.

| Object | eu (today) | us (new) | asia (new) | Purpose | Per-region or shared |
|---|---|---|---|---|---|
| Account Worker | `account-bench` on bench.rediacc.cloud | `account-bench-us` on bench-us.rediacc.cloud | `account-bench-asia` on bench-asia.rediacc.cloud | account API and portal | per region |
| Proxy Worker + container class | `proxy-bench` on proxy.bench.rediacc.cloud | `proxy-bench-us` on proxy.bench-us.rediacc.cloud | `proxy-bench-asia` on proxy.bench-asia.rediacc.cloud | console executor | per region |
| Signer Worker | `signer-bench-eu` | `signer-bench-us` (exists, re-rendered with its own host) | `signer-bench-asia` | licence signing, no route | per region |
| D1 account | `account-bench` (to `account-bench-j`) | `account-bench-us` | `account-bench-asia` | account data | per region |
| D1 control | `control-bench-eu` (to `-j`) | `control-bench-us` (Q1) | `control-bench-asia` | signer scope rows | per region |
| R2 configs | `configs-bench` | `configs-bench-us` | `configs-bench-asia` | config storage | per region |
| R2 backups | `backups-bench` | `backups-bench-us` | `backups-bench-asia` | backup chunk store | per region |
| Queue + DLQ | `backup-replicate-bench` (+`-dlq`) | `backup-replicate-bench-us` (+`-dlq`) | `backup-replicate-bench-asia` (+`-dlq`) | replicate mode | per region |
| Durable Object namespaces | per Worker script | per Worker script | per Worker script | replicator, executor, capacity | per region (automatic) |
| Analytics Engine dataset | `telemetry_bench` | `telemetry_bench_us` | `telemetry_bench_asia` | telemetry mirror | per region |
| Rate limit namespaces | 1104, 1204 | 1105, 1205 | 1106, 1206 | tenant write caps | per region (ids 1101-1104, 1201-1204, 1301 are taken) |
| OTLP destinations | `otlp-bench-logs`, `otlp-bench-traces` | same | same | telemetry export | shared |
| WAF custom rule | one rule, all bench hosts | same rule | same rule | IP allowlist | shared |
| Turnstile | none (TURNSTILE_ENABLED false) | none | none | n/a | n/a |
| KV | none | none | none | n/a | n/a |
| rdc config | `eu-bench` | `us-bench` | `asia-bench` | operator login per bench | per region |
| bws profiles | deploy-bench, reset-bench, bench-login, backup-push-bench, deploy-proxy-bench, region-smoke-bench | same profiles, region-suffixed entries | same | credentials | per region entries, shared profiles; bench-access shared |

## Cost model

### Quotes (re-fetched 2026-11-13; each matched the research summary unless noted)

- Workers, https://developers.cloudflare.com/workers/platform/pricing/ : "a minimum charge of $5 USD per month for an account"; requests "10 million included per month", "+$0.30 per additional million"; CPU "30 million CPU milliseconds included per month", "+$0.02 per additional million CPU milliseconds". The page names no per-Worker charge. Limits page: "Workers per account" 500 on Paid; custom domains per zone 100; routes per zone 1,000 (https://developers.cloudflare.com/workers/platform/limits/).
- D1, https://developers.cloudflare.com/d1/platform/pricing/ : rows read "First 25 billion / month included + $0.001 / million rows"; rows written "First 50 million / month included + $1.00 / million rows"; storage "First 5 GB included + $0.75 / GB-mo"; "You pay $0.10 per month for each D1 database above the included amount, even when it is empty or receives no traffic."; "The Workers Paid plan includes 100,000 databases per account." <!-- style-ok -->
- R2, https://developers.cloudflare.com/r2/pricing/ : Standard "$0.015 / GB-month"; Class A "$4.50 / million requests"; Class B "$0.36 / million requests"; free "10 GB-month / month", Class A "1 million requests / month", Class B "10 million requests / month"; buckets "First 100,000 included", "$0.10 per additional bucket per month".
- Queues, https://developers.cloudflare.com/queues/platform/pricing/ : "1,000,000 operations/month included", "$0.40/million operations"; "An operation is counted for each 64 KB of data that is written, read, or deleted."; "$0.10 per additional queue per month" after the first 10,000.
- Durable Objects, https://developers.cloudflare.com/durable-objects/platform/pricing/ : requests "1 million / month, + $0.15/million"; duration "400,000 GB-s / month, + $12.50/million GB-s"; SQLite rows as D1; stored data "5 GB-month, + $0.20/ GB-month". The page still says storage billing "will be enabled in January 2026, with a target date of January 7, 2026 (no earlier)" and does not confirm it is live; this model treats it as live.
- Containers, https://developers.cloudflare.com/containers/pricing/ : memory "25 GiB-hours/month included", "+$0.0000025 per additional GiB-second"; CPU "375 vCPU-minutes/month", "+ $0.000020 per additional vCPU-second"; disk "200 GB-hours/month", "+$0.00000007 per additional GB-second"; billed "for every 10ms that they are actively running"; charges stop when the instance sleeps. NEW versus the research summary: egress "$0.025" per GB with 1 TB included for North America and Europe, "$0.05" with 500 GB for Oceania, Korea, Taiwan, "$0.04" with 500 GB elsewhere. Instance sizes (https://developers.cloudflare.com/containers/platform-details/limits/): standard-1 is 1/2 vCPU, 4 GiB, 8 GB disk; the bench light size is 0.25 vCPU, 1024 MiB, 4000 MB (workers/proxy/src/sizing.ts:16-19). Account limits there: 50 GB image storage, 60 TiB concurrent memory, 15,000 concurrent vCPU.
- Analytics Engine, https://developers.cloudflare.com/analytics/analytics-engine/pricing/ : "Currently, you will not be billed for your use of Workers Analytics Engine." <!-- style-ok -->
- WAF, https://developers.cloudflare.com/waf/custom-rules/ : "| Number of rules | 5 | 20 | 100 | 1,000 |" (Free, Pro, Business, Enterprise, per zone).
- Turnstile, https://developers.cloudflare.com/turnstile/plans/ : Free "Up to 20 widgets", unlimited challenges. Not used on bench.
- ACM, https://developers.cloudflare.com/ssl/edge-certificates/advanced-certificate-manager/ : "you must purchase the Advanced Certificate Manager add-on"; the page states no price. ACM price: unknown from any fetched page; get it from the dashboard quote (SSL/TLS > Edge Certificates > Order an advanced certificate) only if a certificate outside a Workers Custom Domain is ever wanted. This plan needs none (section *Certificates and names*). <!-- style-ok -->

### "Few records and little traffic cost close to nothing", per product

| Product | Verdict | Fixed or per-object charge |
|---|---|---|
| Workers | confirmed: inside the 10M requests and 30M CPU ms the account already pays for | none per Worker; the $5 account minimum is already paid |
| D1 | confirmed | $0.10 per database only above 100,000 per account; 88 database ids appear in the account's storage data |
| R2 | confirmed for operations; storage is billed from the first GB because the account stores about 1,101 GB, far past the 10 GB free | $0.10 per bucket only above 100,000 |
| Queues | confirmed | $0.10 per queue only above 10,000 |
| Durable Objects | confirmed | none |
| Containers | confirmed while asleep; a running executor bills memory and disk for every 10 ms awake | none per application; image storage counts toward the 50 GB account limit |
| Analytics Engine | confirmed, unbilled today | none |
| WAF custom rule | no money: one rule already covers all bench hosts | a count cap, 5 rules on a Free zone |
| Custom Domain certificates | no ACM subscription needed per the Workers page | none |
| Turnstile, KV | not used | n/a |

### Measured baseline of today's bench (30 days, 2026-10-14 to 2026-11-13, GraphQL Analytics, raw data /tmp/mrb/out.json)

| Item | Bench | Account-wide | Included |
|---|---|---|---|
| Worker requests | account-bench 5,077 + proxy-bench 40 + signer-bench-eu 22 = 5,139 | 701,042 | 10,000,000 |
| Worker CPU ms | 228,972 + 32 + 35 = 229,039 | 3,214,093 | 30,000,000 |
| D1 rows read / written | 732,132 / 89,854 (account-bench) | 34.89M / 9.85M | 25,000M / 50M |
| D1 storage | 9.27 MB | 0.145 GB | 5 GB |
| R2 storage | configs-bench 0.147 GB + backups-bench 5.895 GB + two leftover buckets under the names retired by agent/plans/PLAN-product-domain-rename.md (5.714 GB and 0.048 GB) = 11.80 GB | 1,101 GB | 10 GB (exceeded) |
| R2 Class A / B | about 6,106 / 25,611 | 270,815 / 1,627,537 | 1M / 10M |
| Containers, DO, Queue | 0 container rows, 5 DO requests, 0 queue operations | 8.6 GiB-h memory, 488 vCPU-s over 11 applications | 25 GiB-h, 22,500 vCPU-s |

Bench at list prices today: everything inside the inclusions except R2 storage, 11.80 GB x $0.015 = $0.18 per month. Deleting the two `rediacc-*-bench` leftovers (5.76 GB, not in the toml) saves 5.76 x $0.015 = $0.09 per month.

### Scenarios for adding us and asia (per month, both regions together, on top of the existing $5)

Typical repeats the measured eu bench once per region; its R2 figure uses only the two buckets the toml names (0.147 + 5.895 = 6.04 GB per region). Heavy adds, per region, a full proof sweep (10x the measured monthly bench volume) and one regional-incident rehearsal day (5 light executors for 8 hours plus 1 standard-1 for 2 hours, CPU 25% busy, 50 GB of restore data held for the month, 100,000 extra R2 Class A and B operations and 50,000 queue operations).

| Line | Idle | Typical | Heavy |
|---|---|---|---|
| Worker requests | crons only: (24 + 1) x 30 x 2 = 1,500; $0 | 5,139 x 2 = 10,278; account 711,320 of 10M; $0 | 51,390 x 2 = 102,780; account 803,822 of 10M; $0 |
| Worker CPU ms | negligible; $0 | 229,039 x 2 = 458,078; account 3.67M of 30M; $0 | 2,290,390 x 2 = 4,580,780; account 7.79M of 30M; $0 |
| D1 rows written | about 0; $0 | 89,854 x 2 = 179,708; account 10.03M of 50M; $0 | 898,540 x 2 = 1,797,080; account 11.65M of 50M; $0 |
| D1 storage + databases | 3 new databases, empty; 91 ids of 100,000; $0 | 9.27 MB x 2 = 18.5 MB; account 0.16 GB of 5 GB; $0 | under 0.3 GB; $0 |
| R2 storage | about 0 GB; $0.00 | 6.04 GB x 2 = 12.08 GB x $0.015 = $0.18 | (6.04 + 50) x 2 = 112.08 GB x $0.015 = $1.68 |
| R2 Class A | 0; $0 | 6,106 x 2 = 12,212; account 283,027 of 1M; $0 | (61,060 + 100,000) x 2 = 322,120; account 592,935 of 1M; $0 |
| R2 Class B | 0; $0 | 25,611 x 2 = 51,222; account 1.68M of 10M; $0 | (256,110 + 100,000) x 2 = 712,220; account 2.34M of 10M; $0 |
| R2 buckets, queues | 4 buckets, 4 queues, far under 100,000 and 10,000; $0 | $0 | 100,000 queue operations of 1M; $0 |
| Containers memory | asleep; $0 | 0 measured; $0 | (5 x 1 GiB x 8 h + 4 GiB x 2 h) x 2 = 96 GiB-h; + 8.6 used - 25 included = 79.6 GiB-h = 286,560 GiB-s x $0.0000025 = $0.72 |
| Containers CPU | $0 | $0 | (5 x 0.25 x 8 h + 0.5 x 2 h) x 3600 x 0.25 x 2 = 19,800 vCPU-s; + 488 used = 20,288 of 22,500; $0 |
| Containers disk | $0 | $0 | (5 x 4 GB x 8 h + 8 GB x 2 h) x 2 = 352 GB-h - 200 included = 152 GB-h = 547,200 GB-s x $0.00000007 = $0.04 (account disk use is not in the dataset; with none of the 200 included left it is $0.09) |
| Containers egress | $0 | $0 | assume 10 GB per region, inside 1 TB (us) and 500 GB (asia); $0 |
| Durable Objects | $0 | 5 x 2 requests; $0 | 10 h x 3600 s x 0.125 GB x 2 = 9,000 GB-s of 400,000; $0 |
| Analytics Engine | unbilled | unbilled | unbilled |
| WAF, certificates | 0 new rules, no ACM; $0 | $0 | $0 |
| **Total** | **$0.00** | **$0.18** | **$2.44** ($1.68 + $0.72 + $0.04) |

What the existing Workers Paid plan already covers: every line above except R2 storage (the account is past its free 10 GB) and container memory above 25 GiB-h. In the typical case the plan covers all but $0.18; in the heavy case all but $2.44.

Container ceiling, not a scenario: the bench cap (`EXECUTOR_CAP = "25"`, `EXECUTOR_HEAVY_CAP = "5"`, workers/proxy/wrangler.bench.toml:27-28) fully busy for 24 hours in both regions costs memory (25 x 1 + 5 x 4) GiB x 86,400 s x 2 x $0.0000025 = $19.44, CPU (25 x 0.25 + 5 x 0.5) x 86,400 x 2 x $0.000020 = $30.24, disk (25 x 4 + 5 x 8) GB x 86,400 x 2 x $0.00000007 = $1.69, total $51.37 per day before inclusions. One region's share, $25.69, stays under the per-application `containers_target_usd_month` of 50.

### Limits and spend guard

- No hard limit is in the way. New objects: Workers +5 (account-bench-us/asia, proxy-bench-us/asia, signer-bench-asia) against 500 per account; custom domains +4 against 100 per zone; D1 +3, R2 buckets +4, queues +4, all far below their inclusions; WAF rules +0 (5 on a Free zone). V0 reads the live Worker and custom-domain counts, because the analytics only show the 16 scripts with traffic.
- Container image storage, 50 GB per account, is the one limit two more proxy applications consume; V0 reads current use.
- Spend guard: no ceiling needs to move for typical or heavy (heavy adds about 1% to the requests ceiling and 8% to the CPU ceiling). One change is worth making in D2: a bench line in cf-spend-guard.json's `report` capping each bench proxy application at 10 USD per month, so a stuck rehearsal executor is an `OVER` line at a fifth of a production target's 50. The 10 USD account budget alert stays as is.

## Code and tooling work list (what `--region` driven by regions.json changes)

The source of truth is a `bench` object per regions.json row (names, hosts, location, jurisdiction, rate-limit ids, dataset, queue, config name). Every tool takes `--region eu|us|asia` (default `eu`, so today's calls keep their meaning) and reads names from that object instead of literals.

| Where | Today | With `--region` |
|---|---|---|
| regions.json:7-16, packages/shared/src/regions/data.json | no bench entry | `bench` object per region; eu carries today's names |
| workers/account/wrangler.bench.toml:12-27, :75-156 | one eu toml | plus `wrangler.bench-us.toml`, `wrangler.bench-asia.toml` with regional names, `REGION`, WebAuthn, rate-limit ids, dataset, queues, signer binding props |
| workers/proxy/wrangler.bench.toml:13-47 | one eu toml | plus two regional tomls; `.ci/rediacc_ci/deploy/proxy_configs.py:65` `TARGET_KEYS` and `:199-215` build one bench `Target` per regions.json row |
| .ci/rediacc_ci/ops/deploy_bench.py:64-69, :365, :781, :800-804, :1024 | single host, record `bench.json`, all bench signers, `--bench` control dbs | host/config/record `bench-<r>.json` per region, that region's signer and control db only; `--region all` loops |
| .ci/rediacc_ci/ops/reset_bench.py:41-43, .ci/rediacc_ci/ops/bench_preflight.py:21, :37 | one toml | the region's toml; confirmation text names the region |
| .ci/rediacc_ci/ops/bench_production.py:91, .ci/config/bench-production.json:3 | any entry refuses every reset | entries carry `region`; a reset refuses only its own region |
| .ci/rediacc_ci/deploy/deploy_signer.py:55-63, :136-138 | `("eu","us")`, one toml | bench regions from regions.json, each target renders from its own region's toml, `control-bench-asia` declared |
| .ci/rediacc_ci/deploy/deploy_proxy.py:63-77, :163; .ci/rediacc_ci/deploy/console_executor.py:45, :197-199; .ci/rediacc_ci/deploy/deploy_record.py:92-93 | eu-only refusals | refusals removed; bench worker, profile and version record keyed by region |
| .ci/rediacc_ci/enterprise/proof.py:64-75, :493-499; .ci/rediacc_ci/enterprise/lab.py:1597, :2216 | region-loss bench form cuts eu signers only; lab defaults to eu-bench | region-loss `--bench` places companies in two regions and cuts one; lab config and origin per region |
| .ci/rediacc_ci/ops/bench_access.py:100-113 | `*/wrangler.bench.toml` | glob `wrangler.bench*.toml`; still one rule |
| .ci/rediacc_ci/ops/login_bench.py:46-50 | eu-bench only | `--region` picks server, config and config id; `BENCH_CONFIGS` lists all three |
| .ci/rediacc_ci/ops/live_proof.py:878, .ci/rediacc_ci/proof/live_tier.py:39-50, .ci/config/proof-tiers.json | bench rows are eu files | bench-cache rows read `bench-<r>.json`; `--target bench --region us` |
| .claude/hooks/trapguard/dispatch.py:463, .claude/rediacc_hooks/guards/block_settled_questions.py:200 | literal `eu-bench` | match `(eu|us|asia)-bench` |
| .ci/config/well-known.env:31, :45 | one origin, one proxy host | eu keys unchanged; us and asia origins derived from regions.json rather than new constants |
| .ci/config/secret-supply.json:339, :386, :416, :427, :533, :543 | `_BENCH` names | `_BENCH_US`, `_BENCH_ASIA` entries in the same profiles; bench-access (:397) stays region-free |
| docs/agent-reference/bench-login.md:3, :21-27; .claude/skills/deploy/SKILL.md:24-26 | eu bench only | rows per region |

## Rehearsal use

Rule: the eu bench carries hostinger's production data (Context 12), so rehearsals take a us or asia bench object offline and keep eu as an observer; cutting `signer-bench-eu` is allowed only outside 01:45-03:00Z and only after a green run of hostinger's timer, because a cut signer only blocks renewal and the current licence keeps working.

A regional incident is rehearsed in four cuts, each followed by the same client flows against all three benches (headless login, `rdc config pull`, licence issue and renew, a backup session, one console executor command):

```
signer   remove signer-bench-us's ED25519 secrets (the existing region-loss method), restore from bws afterwards
D1       fence control-bench-us and then account-bench-us with the d1 fence (PLAN-d1-eu-jurisdiction Design 2), unfence after
Worker   detach the bench-us.rediacc.cloud custom domain (or deploy a 503 stub under account-bench-us), redeploy after
proxy    set EXECUTOR_CAP to 0 on proxy-bench-us, then restore
```

Expected: us flows fail with named errors and keep current licences; asia and eu flows pass unchanged; restoring us renews. Each cut records its time to detect, time to restore, and every unnamed error as a finding. `./run.sh enterprise proof region-loss --bench` gains the two-region form so V2's cross-region clause is proven rather than listed as a gap.

Parked boxes this unblocks (signatures read from `wl_planrec.open_boxes` on 2026-11-13):

| Plan | Box | Signature | Effect |
|---|---|---|---|
| agent/plans/PLAN-first-release-checks.md | Multi-region placement | 357547f9 | unblocked on bench (the us and asia executor placement), before edge |
| agent/plans/PLAN-enterprise-isolation.md | V1 | 532e82c9 | unblocked: per-region bench signers with their own hosts |
| agent/plans/PLAN-enterprise-isolation.md | V2 | cdf29e6f | unblocked including the cross-region placement clause |
| agent/plans/PLAN-signer-bench-stop-binding-reattach.md | LP-bench | 89d70106 | unblocked in its two-region form |
| agent/plans/PLAN-console-executor-multi-org.md | ML2 | 49a68721 | rehearsed on bench-us before edge-us |
| agent/plans/PLAN-executor-durable-object-policy.md | L2, L3 | 81675959, 223d8818 | rehearsed on bench-us and bench-asia before edge |
| agent/plans/PLAN-proxy-cd-six-targets.md | L2 | 8ec6bd76 | first us proxy rehearsed on bench-us |
| agent/plans/PLAN-d1-eu-jurisdiction.md | B0 | 7b8e0ac7 | adjacent: its inventory gains the us control database decision (Q1) |

Not unblocked (production or stable targets): account-notices P1 1d112f39, d1-scaling LE1 5c202953, enterprise-isolation X1 15f5537a, first-release-checks C2 24f82950, L5 7bdbed10, L6 e6aa32d5, L7 5c6a8dc7, ML5 f412766e.

## Recommendation

Build persistent us and asia benches now and rename the eu bench to `bench-eu.rediacc.cloud` (operator ruling ASKED:2026-11-13T13:55Z). Money is not the constraint: $0.00 a month idle, $0.18 typical and about $2.44 heavy on top of the $5 Workers Paid minimum already paid, with no fixed per-object fee, no ACM fee and no hard limit in the way. The real cost is engineering and upkeep: about six writer boxes across 30-odd files, three benches to keep deployed (a `--region all` deploy takes roughly three times today's measured 2 minutes 55 seconds), and per-region bench credentials. In return seven parked boxes become provable on bench, and incident rehearsal gets two regions that carry no production data, which the eu bench no longer offers once hostinger lands.

### Alternative (a): one eu bench, a second region simulated with two eu companies

Cost: $0.00 extra per month; two lab companies on the eu bench add a D1 database and two buckets each, inside every inclusion, and the measured volume does not change. The region-loss bench form was just redesigned this way (lease e703f562: one eu company, cut `signer-bench-us` then `signer-bench-eu`; .ci/rediacc_ci/enterprise/proof.py:436-447). Gain: none beyond LP-bench 89d70106, which the eu-only form already runs. Both companies share `REGION "eu"`, eu placement and the eu bench's account Worker, so 357547f9, V2's cross-region clause, ML2, L2, L3 and six-targets L2 stay parked, and every rehearsal cut lands on the bench that carries hostinger.

### Alternative (b): us and asia brought up on demand by a script and torn down after a run

Cost per run: the heavy month's metered lines prorated to a one-day run, (112.08 GB x $0.015) / 30 = $0.06 storage plus $0.72 + $0.04 containers = about $0.82, against $0.18 to $2.44 a month persistent; since idle objects already cost $0.00, the saving is at most $0.18 a month in the typical case. Time per run: cold start is an ESTIMATE, nothing was created to measure it; today's redeploy of existing objects took 2 minutes 55 seconds (12:58:31 to 13:01:26 CET), and a first creation adds D1, R2 and queue creation, D1 migrations from empty, the container image build and push, signer deploy and secrets, root seeding, and DNS plus certificate issuance for two hostnames, estimated at 15 to 30 minutes per region, plus a teardown. Losses: every run starts from empty data, licences issued by a torn-down bench point at a dead host, each run publishes fresh certificate log entries, and each create and delete of Cloudflare objects needs its own operator clearance under the current ruling. Recommended only if the operator wants zero standing objects.

## Questions

- Q1 [answered ASKED:2026-11-13T13:55Z: copy production] Data location for us and asia bench objects. DEFAULT: mirror production per region (us `enam`, asia `apac`, no jurisdiction), overriding "eu jurisdiction for all bench objects" for us and asia only; `control-bench-us` becomes a us-located database again (the original, kept fenced 30 days by PLAN-d1-eu-jurisdiction, re-used if its R1 has not retired it, otherwise created fresh).
- Q2 [answered ASKED:2026-11-13T13:55Z: always-on] Persistent or on demand. Persistent.

## Boxes

### Phase 0: decision and read-only checks
- [ ] Q0 [lead] Operator cost decision on this plan (persistent us and asia, the eu bench renamed bench-eu, Q1 and Q2 answered), recorded in Status with the ASKED minute; then the plan joins QUEUE.md Promoted. Accept: `npm run check:ci-plan-record` rc 0
- [ ] V0 [live] Read-only Cloudflare inventory, no write: Worker script count, custom domains in the rediacc.cloud zone, the zone plan and WAF custom rule count, the certificate pack covering `proxy.bench.rediacc.cloud` (`GET /zones/<id>/ssl/certificate_packs`), container image storage, and the jurisdiction and location of `control-bench-us`; results go into Context. Accept: each read rc 0 and the six figures are recorded with their date

### Phase 1: writers (file-disjoint groups)
- [ ] W1 [writer] regions.json and packages/shared/src/regions/data.json gain the `bench` object per region (eu = today's names, after the `-j` repoint); .ci/rediacc_ci/quality/region_consistency_offline.py reads bench names from it. Accept: `npm run check:ci-regions-sync` rc 0 and `npm run check:ci-region-consistency` rc 0
- [ ] W2 [writer] workers/account/wrangler.bench-us.toml, wrangler.bench-asia.toml and the two proxy tomls; .ci/rediacc_ci/deploy/proxy_configs.py builds a bench Target per region (TARGET_KEYS `bench-us`, `bench-asia`) and refuses a regional bench toml that disagrees with regions.json; the eu bench header comment at workers/account/wrangler.bench.toml:7 is corrected. Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests -k "proxy_configs or bench_toml" -q` rc 0
- [ ] W3 [writer] `--region` on deploy_bench, reset_bench, bench_preflight; per-region deploy records; bench_production entries gain `region` and refuse only their region; the stale `account-db-bench` docstring at .ci/rediacc_ci/ops/deploy_bench.py:5 fixed. Accept: pytest `-k "deploy_bench or reset_bench or bench_preflight or bench_production"` rc 0
- [ ] W4 [writer] deploy_signer bench regions from regions.json with per-region toml and `control-bench-asia`; deploy_proxy, console_executor and deploy_record drop the eu-only refusals (the test `test_a_bench_company_is_refused_outside_the_bench_region` becomes the per-region acceptance); enterprise proof region-loss `--bench` two-region form, lab per-region config. Accept: pytest `-k "deploy_signer or deploy_proxy or console_executor or deploy_record or enterprise_proof or enterprise_lab"` rc 0
- [ ] W5 [writer] bench_access glob `wrangler.bench*.toml`; login_bench `--region` with `BENCH_CONFIGS` for all three; live_proof and live_tier bench rows per region; proof-tiers.json; the two hook regexes. Accept: pytest `-k "bench_access or login_bench or live_proof or live_tier"` rc 0 and `npm run check:ci-plan-live-proof` rc 0
- [ ] W6 [writer] secret-supply.json and bws-secret-map.json region-suffixed bench entries; well-known.env stays eu-only with us and asia derived from regions.json; docs/agent-reference/bench-login.md and .claude/skills/deploy/SKILL.md rows per region. Accept: `npm run check:ci-secret-supply` rc 0

### Phase 1b: eu host migration (ruling ASKED:2026-11-13T13:55Z)
- [ ] M1 [writer] Steps 1, 4 and 8 of *The migration order*: both eu tomls carry the bench-eu routes beside the old ones, well-known.env WK_BENCH_ORIGIN and WK_PROXY_BENCH_HOST move to bench-eu with the generated twins, login_bench, docs, skill, guards and tests follow. Accept: `npm run ci -- --narrow` rc 0
- [ ] M2 [live] Steps 2, 3 and 5: signers redeployed with both hosts in SHARED_HOSTS, deploy_bench and the bench proxy serve both hosts, the eu-bench config logs in and re-links against bench-eu. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench` rc 0 and `npm run login:bench` rc 0 against bench-eu
- [ ] M3 [live] Step 6 per machine, hostinger first: re-licence with `--adopt-origin`, every renewalUrl on bench-eu, backup units carry `--expect-account-server https://bench-eu.rediacc.cloud`, one scheduled run passes. Accept: `machine status <machine> --licenses -o json` names only bench-eu for every machine
- [ ] M4 [live] Step 7: bench.rediacc.cloud dropped from both tomls, signers then Workers redeployed, a renewal naming the old host refused. Accept: `curl -s -o /dev/null -w "%{http_code}" https://bench.rediacc.cloud/account/api/v1/.well-known/server-info` is not 200 and `bench_access list` names only bench-<r> hosts

### Phase 2: bring-up, us first
- [ ] L1 [live] Create the us objects per *Jurisdiction and location hint* (D1 with `--location enam`, R2 with hint `enam`, queues), write the `_BENCH_US` bws entries, deploy `signer-bench-us` (re-rendered with `bench-us.rediacc.cloud`), the account stub, `proxy-bench-us`, then `account-bench-us`, and seed root; record wall time from first create to green as the measured cold start. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region us` rc 0 and `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target bench --region us` rc 0
- [ ] L2 [live] The same for asia with `apac` and a new `signer-bench-asia`. Accept: both commands with `--region asia` rc 0
- [ ] L3 [live] WAF covers all six hosts. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add-current` rc 0, `list` names six hosts, `verify-pinned` rc 0
- [ ] L4 [live] `us-bench` and `asia-bench` configs logged in headless with their own bws entries. Accept: `npm run login:bench -- --region us` and `-- --region asia` rc 0, then `./rdc.sh --config us-bench subscription status -o json` rc 0
- [ ] L5 [live] Renewal hosts per region: a bench test machine licensed through `us-bench` shows renewalUrl `https://bench-us.rediacc.cloud`, renews, and a `bench.rediacc.cloud` renewal sent to `signer-bench-us` is `SIGNER_WRONG_HOST`; hostinger's licences on eu are unchanged. Accept: `machine status <machine> --licenses -o json` names bench-us and `sudo renet license renew --force --output json` reports renewed
- [ ] LP-bench [live] Fresh bench receipt after the us and asia bring-up (L1-L5), recorded once per region with `--region us` and `--region asia`.
  Accept: live-proof bench account-smoke

### Phase 3: rehearsal
- [ ] R1 [live] Region-loss across regions: companies placed on bench-us and bench-asia, then the four cuts of *Rehearsal use* on us with asia and eu as observers; record detect and restore times and every unnamed error. Accept: `./run.sh enterprise proof region-loss --bench` rc 0 with the two-region form and no `cross-region placement` gap note
- [ ] R2 [live] Run the unblocked boxes on bench: 357547f9 (placement), V1 532e82c9, V2 cdf29e6f, LP-bench 89d70106, and the bench rehearsals of ML2 49a68721, L2 81675959, L3 223d8818 and six-targets L2 8ec6bd76. Accept: each box ticked in its own plan with this plan's receipt ids

### Phase 4: cost check and close
- [ ] D2 [writer] cf-spend-guard.json `report` gains a per-bench-proxy-application ceiling of 10 USD a month. Accept: pytest `-k cf_usage_report` rc 0
- [ ] C1 [live] One month after L2, compare the real bench-us and bench-asia usage with the typical scenario. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_usage_report` rc 0 and the measured figures recorded here beside the model

## Risks

- The R2 storage line is the only one that grows with use: hostinger's backups stay on eu, but a rehearsal that restores large repos on us or asia is billed at $0.015 per GB-month from the first GB; R1 deletes its restore data after the run.
- A rehearsal cut left in place (a fenced D1 or a cut signer) silently breaks the next bench box on that region; each cut has a restore step and R1 verifies all three regions green at the end.
- Q1's DEFAULT reverses the "eu jurisdiction for all bench objects" ruling for us and asia; if the operator keeps the ruling, us and asia bench objects are created `--jurisdiction eu` and the bench no longer proves the production placement of those regions.

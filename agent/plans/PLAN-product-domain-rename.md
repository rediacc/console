# PLAN-product-domain-rename: the product moves to rediacc.cloud, rediacc.com keeps the website, and Cloudflare and GitHub names drop their prefixes

Status: executing -- promoted by operator 2026-11-08; design settled in the operator talk of 2026-11-05 (marketing on rediacc.com, product on rediacc.cloud, one shared Worker set per region, prefixes gone)
Depends-On: no-dep -- the first of three plans; PLAN-website-routing-and-mail.md and PLAN-enterprise-isolation.md build on its hosts and names
Owner: d778be9d
Priority: P1 -- every later plan builds on these hosts and names, and billing opens on the result
Concurrency: parallel -- operator 2026-11-08 ("go in parallel as much as possible", "make queue.md to ultra and try to start again"): every writer runs in its own lease and the rename lands as one batch, so a textual clash with another plan (regions.json, Worker configs, workflows) surfaces as a cherry-pick conflict at landing rather than in a shared tree; a new file that names an old host or resource lands cleanly, and `check:ci-retired-terms` (W11) is what refuses it
Owns: agent/plans/PLAN-product-domain-rename.md, regions.json, packages/shared/src/regions/data.json, .ci/config/well-known.env, .ci/config/well-known.generated.sh, packages/shared/src/config/well-known.generated.ts, scripts/data/literal-sources.json, workers/account/wrangler*.toml, workers/proxy/wrangler*.toml, workers/www/wrangler*.toml, .ci/config/secret-supply.json, .ci/config/bws-unrequested.json, .ci/config/retired-terms.json, .ci/rediacc_ci/deploy/**, .ci/rediacc_ci/ops/**, .ci/rediacc_ci/drills/backup*.py, .ci/rediacc_ci/quality/**, .ci/rediacc_ci/tests/**, scripts/gates/check-backup-bucket-conformance.ts, .claude/rediacc_hooks/guards/block_unasked_release.py, .claude/rediacc_hooks/guards/test-block_unasked_release.py, .claude/skills/deploy/SKILL.md, .github/workflows/**, docs/**, CLAUDE.md, private/account/rotation-manifest.json, private/account/scripts/rotation/**, private/account/src/routes/portal.ts, private/account/src/types/subscription.ts, private/account/web/src/auth/**, private/account/web/src/components/**, private/account/tests/integration/**, private/account (gitlink bump only)
Live-Proof: bench -- bench takes every account, proxy and www rename first; renet and the CLI do not change here, so hostinger's re-point is proven by L9 and L10 rather than a receipt
First-Seen: 2026-11-05

## Rulings (source: operator talk 2026-11-05)

- Ruling 1. "Failures are acceptable and fixed forward. There are no real customers. No downtime avoidance, no compatibility windows, no dual names, no migration phases."
- Ruling 2. "hostinger's backup is not critical: it re-uploads everything to the new target", so no copy of its backup bucket and no freeze. The old bucket goes only after a verify, a restore test and one nightly on the new target. Media videos, the releases bucket and `account-db-eu` stay on the never-lose list.
- Ruling 4. "Edge and stable hold lifts once bench's live boxes pass; then the session deploys new shared regions without asking. Bench first always."
- Ruling 5. "Business and every shared plan ride the fast tier with no soak. Billing opens on it. Edge's 2x limits are removed."
- Ruling 12, the part this plan carries. `cd-release-stable.yml`; internal tier name `enterprise`; channels stay `edge` and `stable`.

## Already done

The zone `rediacc.cloud` is on Cloudflare, active on the Free plan, with nameservers anirban and rose.ns.cloudflare.com, null MX, `v=spf1 -all`, `_dmarc` reject with strict alignment and no A records. Registration stays at Hostinger. Read through DNS-over-HTTPS on 2026-11-05: NS, MX and DMARC match. The apex 301 and the AI bot setting are the only zone items left, and both are in agent/plans/PLAN-website-routing-and-mail.md.

## Names

`<r>` is eu, us or asia. The stable and edge pairs collapse into one shared set, and this table replaces every earlier name table in the talk.

| Thing | Before | After |
|---|---|---|
| Account host | `edge-<r>.rediacc.com`, `<r>.rediacc.com` | `<r>.rediacc.cloud` |
| Proxy host | `proxy.edge-<r>.rediacc.com`, `proxy.<r>.rediacc.com` | `proxy.<r>.rediacc.cloud` |
| Bench hosts | `bench.rediacc.com`, `proxy.bench.rediacc.com` | `bench.rediacc.cloud`, `proxy.bench.rediacc.cloud` |
| Account Worker | `edge-rediacc-account-<r>`, `rediacc-account-<r>` | `account-<r>` |
| Proxy Worker | `edge-rediacc-proxy-<r>`, `rediacc-proxy-<r>` | `proxy-<r>` |
| Website Worker | `edge-rediacc-www`, `rediacc-www` | `www`, on `www.rediacc.com`, built from edge |
| Bench Workers | `rediacc-account-bench`, `rediacc-proxy-bench` | `account-bench`, `proxy-bench` |
| Dev Workers | `rediacc-proxy-dev`, `rediacc-executor-issuer-dev` | `proxy-dev`, `executor-issuer-dev` |
| D1 | `edge-account-db-<r>`, `account-db-<r>`, `account-db-bench`, `account-db-pr-<n>` | `account-<r>`, `account-bench`, `account-pr-<n>` |
| Config bucket | `edge-rediacc-configs-<r>`, `rediacc-configs-<r>`, `-bench`, `-staging` | `configs-<r>`, `configs-bench`, `configs-staging` |
| Backup bucket | `edge-rediacc-backups-<r>`, `rediacc-backups-<r>`, `-bench` | `backups-<r>`, `backups-bench` |
| Other buckets | `rediacc-releases`, `rediacc-www-media`, `rediacc-staging` | `releases`, `media`, `staging` |
| Wrangler config | `wrangler.edge-<r>.toml`, `wrangler.<r>.toml` | `wrangler.<r>.toml` |
| Secret | three schemes, plus `CF_` beside `CLOUDFLARE_` | `<AREA>_<NAME>_<REGION>` with the environment segment gone, `_BENCH` for bench, `CLOUDFLARE_` only |
| Edge release workflow | `cd-v2.yml`, "Release to Edge" | `cd-release-edge.yml`, "CD - Release to Edge" |
| Stable release workflow | `promote-stable.yml`, "Release to Production" | `cd-release-stable.yml`, "CD - Release to Stable" |

Unprefixed workflows gain `ops-`, and `Console CI -` and `Console CT -` display names become `CI -` and `CT -`. Unchanged: `CI Complete`, `Review Complete`, the `releases`, `media` and `mta-sts` hosts, CLI channels, `rediacc-account-server` and `rediacc-proxy-executor` (other things that share the prefix), Traefik's `rediacc-proxy` container in renet, and Elite's local RustFS defaults. renet bakes no account host, since it reads the host from the licence's `renewalUrl` (private/renet/cmd/renet/backup_endpoints.go:26).

`ENVIRONMENT=edge` stays on the shared Workers, because it picks the CLI's update channel (private/account/src/app.ts:234).

## Design

**What seeds `account-eu`.** The stable EU rows from `account-db-eu`, with the backup-plane rows dropped, and `backups-eu` starts empty. hostinger needs a working account on the new host, and those rows are that account: the operator's user and agent login (`eu-remote` tokens are D1 rows, and a login on any other database stops at the human authenticator), the org, the subscription, the machine's activations, and the issuance ledger whose sequence continues renet's per-subscription chain state (private/renet/pkg/license/chain_state.go:15). Edge EU holds test orgs written by direct D1 inserts (.ci/config/secret-supply.json:460), which are re-provisioned, so it is archived and dropped. L2 reads both databases first, and a surprise in the edge rows changes this decision out loud. Licences still change: `renewalUrl` is signed into each blob and comes from the host that issued it (private/account/src/routes/license.ts:41), so L9 re-issues hostinger's. `configs-eu` is copied from `rediacc-configs-eu`, because the seeded rows point at those objects and the EU_STABLE config key travels with them. US and ASIA seed from their edge databases, which hold the live-console orgs.

**Why the backup rows go, and why the re-upload then works.** A manifest row whose object is absent is a false claim. Dropped: `backup_usage`, `backup_lineage_usage`, `backup_manifests`, `backup_upload_leases`, `backup_exists_pins`, `backup_streams`, `backup_sessions`, `backup_stream_status`, `backup_waiting_chunks`, `backup_refset_pending` (from private/account/src/db/schema.ts:1473). Retention and immutability settings stay. A scheduled run is a delta that asks about changed hashes plus a sample of 16 unchanged ones, and a sampled hash the store lacks falls back to the full ask and uploads whatever is gone (private/renet/pkg/chunkstore/uploader.go:656). The commit's parent is then unknown, so the server refuses it and renet commits the full manifest instead (private/renet/pkg/chunkstore/uploader.go:461). No `--reseed` is needed. This is a code read, proven by L10. The report's garbage-collection hazard (private/account/src/services/backup-gc.service.ts:5175) applies to a copied bucket, and an empty one has nothing to collect.

**Never-lose list.** Media videos, the releases bucket and `account-db-eu`, whose archive is taken through `backup_d1` before any delete. `rediacc-backups-eu` is not on it, by ruling 2.

**Copy tool.** `r2_promote` is same-bucket and forces `--metadata-directive REPLACE` (.ci/rediacc_ci/deploy/r2_promote.py:150), so W1 generalizes it rather than writing a second one; no rclone path, per its retirement (agent/plans/PLAN-rclone-decommission.md). Jurisdiction is set at create and does not carry over, and `.eu.` is the only endpoint that sees EU buckets. Without `--jurisdiction eu` a default bucket appears with no error.

**Worker mechanics.** account binds proxy and proxy binds account, and wrangler refuses a missing service, so a stub account Worker comes first, while `check_services` refuses before migrations (.ci/rediacc_ci/deploy/deploy_account.py:237). Secrets do not copy, so each new Worker takes a full push. The backup bucket is named twice, in the toml binding and in `ACCOUNT_BACKUP_S3_BUCKET`. A new script gets an empty Durable Object namespace; the org pins, marks and leases it loses heal themselves. Removing a Wrangler entry leaves the container application behind, so old apps are deleted by id.

**Refusals that go silent.** These match old names only, so a drill pointed at `backups-eu` would write and delete: `PROTECTED_PATTERNS` (.ci/rediacc_ci/ops/r2_lifecycle.py:30), the bare-name refusals in `drills/backup.py`, `backup_local_plane.py`, `backup_cutover_preflight.py` and `probe-s3-delete-semantics.ts`, and the regex in scripts/gates/check-backup-bucket-conformance.ts:209. One guard inverts: any config without `edge`, `bench` or `preview` counts as stable, so `wrangler.eu.toml` would demand a proven ask (.claude/rediacc_hooks/guards/block_unasked_release.py:172). W6 and W7 move them in the same batch as the names.

**Billing.** `billingGuard` answers 403 on edge (private/account/src/routes/portal.ts:33), edge profiles carry no Stripe key, and limits double on edge (private/account/src/types/subscription.ts:270). All three go.

## When a merge applies

The rule from the operator's rulings: live steps do not wait on a merge when a local script runs them (2026-11-04), and a mutating `rdc` verb from an unmerged branch uploads that branch's renet to production (2026-10-24). hostinger has no maintenance window, so nothing here waits for one.

| Box | Waits on merge | Why |
|---|---|---|
| L1, L2, L3, L4, L5 | no | Account objects and bench, deployed from the branch by `rediacc_ci.deploy.*` |
| L6, L7, L8 | no, but after LP-bench | The hold lifts on bench (ruling 4). Proxy images use a published version, whatever the branch (.ci/rediacc_ci/deploy/deploy_proxy.py:12) |
| H1 | no | Read-only |
| M1 | is the merge | `release:local` needs `HEAD` equal to `origin/main` (docs/agent-reference/release-process.md:136) |
| L9, L10 | yes, then at once | Mutating verbs on hostinger need the released renet. `backup schedule` and `strategy bind` run through `eu-remote` only |
| W13, L12 | yes | `workflow_run` reads default-branch code |
| L11 | after L10 and L12 | Deletes only |

M1 merges with these boxes open, so the PR body carries `Operational-Reason: hostinger and workflow boxes need the released code`.

## Tasks

### Prerequisites

  (result 2026-11-08) cf-cd re-minted as rediacc-cd-20261108T150415Z (a52f6c90), rediacc.cloud dns_records and workers/routes answer success true; previous cf-cd in grace until 2026-11-15T15:04Z. R2 migration token rediacc-r2-migration-20261108T150703Z (1897fcf4), account-wide R2 read+write, in bws as CLOUDFLARE_R2_MIGRATION_API_TOKEN, _ACCESS_KEY_ID, _SECRET_ACCESS_KEY (no rotation slug yet; deleted at L11). Turnstile rediacc-console gains rediacc.cloud, none removed. The L1 and L3 accept commands need the migration token: cf-cd carries no R2 permission since the 2026-10-20 ruling (#64dacf21).
- [x] L1 [live] Re-mint cf-cd so it lists the new zone (private/account/scripts/rotation/commands/rotate.ts:566), mint the R2 migration token through bws, and add `rediacc.cloud` to the `rediacc-console` Turnstile widget (private/account/scripts/rotation/platforms/cloudflare-turnstile.ts:94). Whether a listed domain covers its subdomains is unverified until L6.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- npx wrangler r2 bucket list --jurisdiction eu` rc 0.
    (ticked) 2026-11-08T15:16:40Z by d778be9d: live 2026-11-08 (live runner): cf-cd re-minted (a52f6c90) and lists rediacc.cloud (dns_records, workers/routes success true); R2 migration token 1897fcf4 in bws as CLOUDFLARE_R2_MIGRATION_{API_TOKEN,ACCESS_KEY_ID,SECRET_ACCESS_KEY}; Turnstile rediacc-console gains rediacc.cloud, none removed; accept wrangler r2 bucket list --jurisdiction eu rc 0 under the migration token (the deploy-workers form is rc 1 by the 2026-10-20 no-R2 ruling, recorded under the box)
    (corrected 2026-11-09, d778be9d) 330bb019.3: the Accept ran under the R2 migration token, not the `--profile deploy-workers` form printed above: `wrangler r2 bucket list --jurisdiction eu` rc 0 under CLOUDFLARE_R2_MIGRATION_API_TOKEN, as the tick records. The deploy-workers form is rc 1 because cf-cd carries no R2 permission since the 2026-10-20 ruling (#64dacf21), which the Prerequisites result line names; the printed command stands as written and is not what proved the box.
- [x] W1 [writer] Generalize the `r2_promote` plumbing and add `ops/r2_bucket_copy.py`: inventory, cross-bucket copy with metadata preserved, re-runnable delta, count, size and key parity, `--jurisdiction`. Objects over 5 GiB are refused by `check_sizes`, so L2 reports any.
  Owns: .ci/rediacc_ci/deploy/r2_promote.py, .ci/rediacc_ci/ops/r2_bucket_copy.py (new), .ci/rediacc_ci/tests/test_ops_r2_bucket_copy.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_r2_bucket_copy.py .ci/rediacc_ci/tests/test_deploy_r2_promote.py` rc 0.
    (ticked) 2026-11-08T15:45:00Z by d778be9d: commit:865c2f7f23 + commit:c4d2c45a1a r2_promote plumbing takes bucket, src_bucket, preserve_metadata; ops/r2_bucket_copy.py inventory, delta copy, parity (size and single-part ETag), --jurisdiction, refuses objects over 5 GiB and ?versionId= keys; 110 tests rc 0 on the four r2 test files after landing; live inventory rc 0 (L2)
- [x] W2 [writer] `clone_d1` gains per-table row parity, the `regions.json` location in place of the fixed `--location eeur`, and `--drop-tables` for the seed. `deploy_account` gains the stub bootstrap.
  Owns: .ci/rediacc_ci/deploy/clone_d1.py, .ci/rediacc_ci/deploy/deploy_account.py, .ci/rediacc_ci/tests/test_deploy_clone_d1.py, .ci/rediacc_ci/tests/test_deploy_deploy_account.py.
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_deploy_clone_d1.py .ci/rediacc_ci/tests/test_deploy_deploy_account.py` rc 0.
  (result 2026-11-08) R2: rediacc-backups-eu 105,428 objects 441.7 GB; rediacc-configs-eu 53 / 45.8 MB; edge-rediacc-configs-eu 54 / 44.0 MB; rediacc-releases 977 / 103.4 GB; rediacc-public-data 373 / 99.1 GB (no target in the Names table); rediacc-www-media 8,823 / 8.48 GB; rediacc-backups-bench ~1,400 / 5.71 GB; rediacc-configs-bench 79 / 46.6 MB; every other bucket empty or under 12 KB. Nothing over 5 GiB on a copy path (only public-data holds 7, 23 and 37.7 GB archives). rediacc-staging and rediacc-configs-staging do not exist (.ci/rediacc_ci/ops/r2_lifecycle.py:27 names rediacc-staging). D1: account-db-eu 45.2 MB 26,835 rows; edge-account-db-eu 4.2 MB 3,085; account-db-bench 7.9 MB 8,850; us and asia under 2 MB each. Stable and edge EU share 84 tables; backup tables are stable-only; users/orgs/subscriptions stable 9/9/9, edge 15/15/15. Edge EU is NOT test orgs only: 9 users on outside domains and 10 active BUSINESS subscriptions. Operator ruling ASKED:2026-11-08T15:30Z, "Archive, then drop (Recommended)": the edge EU D1 is exported to R2 (backup_d1) and kept, then dropped at L11; its users and subscriptions are not merged.
    (ticked) 2026-11-08T18:03:08Z by d778be9d: commit:69369e9a6e W2 landed as 69369e9a6e: clone_d1 --drop-tables and --row-parity, deploy_account --stub; accept pytest test_deploy_clone_d1.py test_deploy_deploy_account.py 86 passed rc 0 on the batch tip
    (corrected 2026-11-09, d778be9d) 330bb019.7 and f5073b97.3: the (result 2026-11-08) line above, with the R2 and D1 sizes and the edge EU ruling, is L2's inventory and ruling, appended under W2 by position only; L2 below is the box it belongs to and its tick names both. The (result 2026-11-08, ids for W4) line under L2 is L3's id record, not L2's.
- [x] L2 [live] Read-only inventory of every bucket and D1, with stable and edge EU rows compared per table, and the result recorded here. It replaces the size guesses in the talk.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --inventory` rc 0 (built by W1).
  (result 2026-11-08, ids for W4) D1 account-eu cd60532c-cffa-4637-bff0-0b6427f6747b EEUR; account-us 62b71ebb-4dd2-4710-93b3-a719fad87252 ENAM; account-asia a1375747-560d-45c7-b2cb-6b47df20f924 APAC; account-bench 8c260075-db26-4787-b700-b657f21a5f61 EEUR. KV enterprise-lookup 7bbf3025-c293-49f5-b4f8-33c1d47d8eb5 (the API returns it without dashes). R2 configs-eu, backups-eu (eu jurisdiction); configs-us, backups-us ENAM; configs-asia, backups-asia APAC; configs-bench WEUR; backups-bench EEUR; releases ENAM; media EEUR. configs-staging and staging not created (no source).
    (ticked) 2026-11-08T15:32:37Z by d778be9d: live 2026-11-08: accept python3 -m rediacc_ci.ops.r2_bucket_copy --inventory rc 0 (default and eu jurisdiction, built by W1 in 865c2f7f23); every bucket and D1 inventoried, stable vs edge EU compared per table, recorded under the box; only rediacc-public-data holds objects over 5 GiB (three StackExchange archives); edge EU not test-only, operator ruling ASKED:2026-11-08T15:30Z archive then drop
    (corrected 2026-11-09, d778be9d) 5f9da03a.2: the Accept command proves the R2 half only (`r2_bucket_copy --inventory` rc 0). The D1 half, stable and edge EU compared per table (84 shared tables; users, orgs and subscriptions 9/9/9 against 15/15/15; backup tables stable-only), is the live runner's own `wrangler d1 execute` readings, recorded in the result line under W2 with no command output kept in the tree. Owed to prove it: `npx wrangler d1 execute account-db-eu --remote --json --command "select name from sqlite_master where type='table'"` and the same against edge-account-db-eu, whose table lists must match the 84 shared names; the L11 `backup_d1` archive of both old databases carries the same rows.
    (corrected 2026-11-09, d778be9d) f5073b97.4: the quoted label is the option text of the operator's /ask answer, and the tree holds no transcript record of it beyond this line, so the recommended-option suffix is not shown to be a selection here. The drop it drives is not irreversible: L11 archives every old D1 with `backup_d1` before it deletes anything, which holds under either reading of the answer.
- [x] L3 [live] Create the target D1s with their locations, the R2 buckets (EU with `--jurisdiction eu`) and the KV namespace `enterprise-lookup`, all empty, and record the ids for W4.
  Accept: `npx wrangler d1 list --json | jq -e 'map(.name)|contains(["account-eu","account-us","account-asia","account-bench"])'` rc 0 and `npx wrangler r2 bucket list --jurisdiction eu | grep -q backups-eu` rc 0, under the deploy profile.
    (ticked) 2026-11-08T15:17:11Z by d778be9d: live 2026-11-08 by the live runner: D1 account-eu (cd60532c, EEUR), account-us (62b71ebb, ENAM), account-asia (a1375747, APAC), account-bench (8c260075, EEUR); KV enterprise-lookup (7bbf3025); R2 configs and backups for eu (eu jurisdiction), us (ENAM), asia (APAC), configs-bench (WEUR), backups-bench (EEUR), releases (ENAM), media (EEUR), all empty; ids recorded under the box for W4; accept: wrangler d1 list jq contains rc 0, and the eu bucket list rc 0 under the migration token

### Names, one batch

- [x] W3 [writer] Host source. `regions.json` and its twin lose the stable and edge pairs. `well-known.env` gains `WK_PRODUCT_DOMAIN`, because `WK_APEX_DOMAIN` means both products today, sets the `.cloud` hosts and default origin `https://eu.rediacc.cloud`, and drops `WK_EDGE_ORIGIN` and the edge proxy hosts. Regenerate the well-known outputs.
  Owns: regions.json, packages/shared/src/regions/data.json, .ci/config/well-known.env, .ci/config/well-known.generated.sh, packages/shared/src/config/well-known.generated.ts, scripts/data/literal-sources.json, .ci/rediacc_ci/quality/region_consistency_offline.py, .ci/rediacc_ci/quality/literal_sources.py, .ci/rediacc_ci/quality/regions_sync.py.
  Accept: `npm run check:ci-regions-sync && npm run check:ci-literal-sources && npm run check:ci-region-consistency` rc 0.
    (ticked) 2026-11-08T18:46:33Z by d778be9d: commit:116d34faaa W3 landed 116d34faaa; accept regions-sync, literal-sources, region-consistency rc 0 on the batch tip (read 2026-11-08 19:0xZ)
    (corrected 2026-11-09, d778be9d) 703fde3a.2: the tick's "read 2026-11-08 19:0xZ" is an unfinished placeholder and carries no time. The time of record is the tick stamp 18:46:33Z, which follows the accept run on the batch tip; the run itself has no separate stamp.
- [x] W4 [writer] Every Wrangler config, in one owner. Rename to `wrangler.<r>.toml` and `wrangler.bench.toml`, delete the stable and edge files, render the proxies, set routes and `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN` to the new hosts, set the new D1 ids, rename the www Worker to `www` on `www.rediacc.com`, delete `workers/www/wrangler.edge.toml`, and bind KV `ENTERPRISE_LOOKUP` on `www`.
  Owns: workers/account/wrangler*.toml, workers/proxy/wrangler*.toml, workers/www/wrangler*.toml, .ci/rediacc_ci/deploy/proxy_configs.py.
  Accept: `npm run check:ci-proxy-configs && npm run check:ci-proxy-deploy-dry-run` rc 0.
    (ticked) 2026-11-08T18:02:42Z by d778be9d: commit:1a984268fa W4 landed in 1a984268fa: one wrangler config per region and bench on the shared names and L3 ids; accept check:ci-proxy-configs rc 0 and check:ci-proxy-deploy-dry-run rc 0 on the batch tip
    (corrected 2026-11-09, d778be9d) ba72b7d0.2: the Accept proves the configs render and the dry run holds; the clauses it does not name are present in the tree, read 2026-11-09: workers/www/wrangler.toml names the Worker `www` (line 1) and binds KV `ENTERPRISE_LOOKUP` (line 52), and `ls workers/www/wrangler*.toml` lists only wrangler.toml, so wrangler.edge.toml is deleted.
- [x] W5 [writer] Deploy and ops code follows: `deploy_account`, `deploy_proxy` (and its stale claim of a DEV key at .ci/rediacc_ci/deploy/deploy_proxy.py:12, since bench binds the production key per .ci/rediacc_ci/ops/deploy_bench.py:25), `deploy_bench`, `reset_bench`, `backup_d1`, `test_d1_migrations`, `console_executor`, `service_bindings_audit`, `prune_worker_secrets`, `push_backup_credentials`, `mirror_config_store`, `portal_health`, `portal_captcha`, `resolve_www_deploy_target`, `deploy_www`, `release/local.py`, `sync_media_*`, `verify_*`, and `bench_access` on the new zone.
  Owns: the modules named, under .ci/rediacc_ci/deploy/**, .ci/rediacc_ci/ops/** and .ci/rediacc_ci/release/local.py.
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_service_bindings_audit.py .ci/rediacc_ci/tests/test_ops_mirror_config_store.py .ci/rediacc_ci/tests/test_deploy_account_secrets_local.py .ci/rediacc_ci/tests/test_ops_deploy_bench.py` rc 0.
    (ticked) 2026-11-08T18:46:34Z by d778be9d: commit:bb8321d86f W5 landed (f6cf1731aa, 2db29acc1e, 69369e9a6e, bb8321d86f); accept pytest service_bindings_audit, mirror_config_store, account_secrets_local, deploy_bench rc 0 on the batch tip
    (corrected 2026-11-09, d778be9d) 703fde3a.3: the Accept runs four test files, which cover service_bindings_audit, mirror_config_store, the account secrets path and deploy_bench only. The other named modules (portal_health, portal_captcha, resolve_www_deploy_target, deploy_www, release/local.py, sync_media_*, verify_*) are exercised only by the W11 run of `pytest .ci/rediacc_ci/tests -k "deploy or ops"` (2648 passed) where a test for them exists. Owed: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests -k "portal_health or portal_captcha or sync_media or verify or release_local or deploy_www or resolve_www"` rc 0, which needs pytest in the environment that runs it.
- [x] W6 [writer] Move every silent refusal in the Design to the new names, with a plant for each that fails on the old pattern.
  Owns: .ci/rediacc_ci/ops/r2_lifecycle.py, .ci/rediacc_ci/drills/backup*.py, scripts/gates/check-backup-bucket-conformance.ts, the `probe-s3-delete-semantics.ts` line in private/account.
  Accept: `npm run check:ci-backup-bucket-conformance` rc 0 and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_r2_lifecycle.py` rc 0.
    (ticked) 2026-11-08T18:03:09Z by d778be9d: commit:8d5386033c W6 landed as 8d5386033c: refusals on the shared bucket names with a plant each; accept check:ci-backup-bucket-conformance rc 0 and pytest test_ops_r2_lifecycle.py 34 passed rc 0 on the batch tip
- [x] W7 [writer] Flip the guard: `wrangler.<r>.toml` of a shared Worker needs no ask, and no stable Worker config remains. Update the deploy skill.
  Owns: .claude/rediacc_hooks/guards/block_unasked_release.py, .claude/rediacc_hooks/guards/test-block_unasked_release.py, .claude/skills/deploy/SKILL.md.
  Accept: `python3 .claude/rediacc_hooks/guards/test-block_unasked_release.py` rc 0.
    (ticked) 2026-11-08T18:03:10Z by d778be9d: commit:12dc57a0c9 W7 landed as 12dc57a0c9 (merged with W13 renames in 2d47c02363): shared Worker deploys free per operator ruling, only the CLI stable channel asks; accept test-block_unasked_release.py rc 0 (227 cases) on the batch tip
    (corrected 2026-11-09, d778be9d) ba72b7d0.1: the guard test proves the flip only. The other two clauses are present in the tree, read 2026-11-09: no stable or edge Worker config remains (`ls workers/*/wrangler*.toml` lists region, bench, dev and template files only), and .claude/skills/deploy/SKILL.md:13 states there is no stable Worker any more.
- [x] W8 [writer] Submodule first: rotation consumers and bucket scopes follow the names. The email region labels stay with PLAN-website-routing-and-mail.md W6.
  Owns: private/account/rotation-manifest.json, private/account/scripts/rotation/**.
  Accept: `(cd private/account && npx vitest run tests/integration/rotation-r2-backup-scopes.test.ts tests/integration/rotation-worker-consumer.test.ts)` rc 0.
    (ticked) 2026-11-08T18:02:46Z by d778be9d: commit:6387aa3efc W8 landed as account 3f37af2: rotation consumers and bucket scopes follow the shared names; accept vitest rotation-r2-backup-scopes and rotation-worker-consumer rc 0 on the batch tip
- [x] W9 [writer] Submodule first: billing opens. Remove `billingGuard` and the edge doubling, and the web UI's `isEdge` branches. `ENVIRONMENT=edge` stays.
  Owns: private/account/src/routes/portal.ts, private/account/src/types/subscription.ts, private/account/web/src/auth/**, private/account/web/src/components/**, private/account/tests/integration/billing-open-on-shared-tier.test.ts (new).
  Accept: `(cd private/account && npx vitest run tests/integration/billing-open-on-shared-tier.test.ts tests/integration/proxy-binding-wiring.test.ts)` rc 0 and `npm run check:ci-cli-contract` rc 0.
    (ticked) 2026-11-08T18:02:47Z by d778be9d: commit:9900c15aae W9 landed as account 3813ba5 with 6a379a0: billing opens on the shared tier, isEdge gone; accept vitest billing-open-on-shared-tier and proxy-binding-wiring rc 0 (67 passed with W8) and check:ci-cli-contract rc 0 on the batch tip
- [x] W10 [writer] Secrets to the one pattern. `account-secrets-<r>` profiles take the set that carries Stripe, and `ACCOUNT_CONFIG_SERVER_KEY_EU` takes the EU_STABLE value because the seeded config objects need it.
  Owns: .ci/config/secret-supply.json, .ci/config/bws-unrequested.json, .ci/rediacc_ci/deploy/set_account_worker_secrets.py, .ci/rediacc_ci/deploy/account_secrets_local.py.
  Accept: `npm run check:ci-secret-supply && npm run check:ci-backup-credential-isolation` rc 0.
  (result 2026-11-08) No new bws names: the landed profiles already bind every name the shared Workers need (W10 kept the _STABLE names and maps the US/ASIA _EDGE config keys and KEKs under _STABLE local names). Both backup tokens rotated in place: cf-r2-backup-stable to rediacc-backup-stable-20261108T174312Z (60b2af14) scoped to backups-eu, backups-us, backups-asia; cf-r2-backup-bench to rediacc-backup-bench-20261108T174350Z (042add71) scoped to backups-bench. The old stable token b38b0881 stays in grace with no eligibility date, because the live old eu Worker still serves the hostinger nightly backup; L11 deletes it with `rotation deactivate cf-r2-backup-stable` after L9 and L10, and the old bench token 6773e436 if L5 has not.
    (ticked) 2026-11-08T18:46:35Z by d778be9d: commit:73879fe606 W10 landed 73879fe606 with 990a3d9f28 and b5caf6b8dc; accept check:ci-secret-supply and check:ci-backup-credential-isolation rc 0 on the batch tip
    (corrected 2026-11-09, d778be9d) 309bd420.2: the old stable backup token b38b0881 carries no eligibility date by design, because the live old eu Worker still serves the hostinger nightly backup. Its bound is the L11 box, which runs `rotation deactivate cf-r2-backup-stable` only after L9 and L10 are ticked. If those stall the token stays valid, and no calendar expiry is recorded; the check owed at L11 is that deactivation followed by `backup verify --store` rc 0.
- [x] L4 [live] Write the new bws names with their values, ahead of any deploy. Old names stay until L11.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile account-secrets-eu -- true` rc 0.
    (ticked) 2026-11-08T17:46:44Z by d778be9d: live 2026-11-08: no new bws names needed (landed profiles resolve: account-secrets-eu, -us, -asia, deploy-bench rc 0); both backup tokens rotated in place onto backups-<region> and backups-bench (60b2af14, 042add71; account 84f9967 via 49a0a1ae1f); scope probes rc 0 every leg; old stable token held until L11 so the hostinger nightly keeps working
    (corrected 2026-11-09, d778be9d) 309bd420.1: the clause "write the new bws names with their values" had no names to write, since the landed profiles already bind every name the shared Workers need (the result line under W10). The box closes on its Accept, `account-secrets-eu` resolving rc 0, with account-secrets-us, account-secrets-asia and deploy-bench rc 0 in the tick; no value was written.
- [x] W11 [writer] Sweep tests and goldens by a transform with a byte-identical proof, since goldens read by 62 tests can only be rewritten. Add the old names to retired terms.
  Owns: .ci/rediacc_ci/tests/**, .ci/config/retired-terms.json.
  Accept: `npm run check:ci-retired-terms` rc 0 and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests -k "deploy or ops"` rc 0.
    (ticked) 2026-11-08T19:18:19Z by d778be9d: commit:bb0bcb3fbb tests and goldens on the renamed resources; commit:eb599db210 old names in retired-terms (pre-rename-* terms); check:ci-retired-terms rc 0; PYTHONPATH=.ci pytest -q .ci/rediacc_ci/tests -k "deploy or ops" 2648 passed rc 0
- [x] W12 [writer] Sweep docs outside `packages/www`, which belongs to PLAN-website-routing-and-mail.md W5.
  Owns: docs/**, CLAUDE.md, .ci/docs/**.
  Accept: `npm run check:ci-literal-sources && npm run check:ci-doc-region-parity` rc 0.
    (ticked) 2026-11-08T18:46:36Z by d778be9d: commit:0070982315c W12 landed 0070982315; accept check:ci-literal-sources and check:ci-doc-region-parity rc 0 on the batch tip

### Bench

- [x] L5 [live] Bench on the new names: clone `account-db-bench`, copy `rediacc-configs-bench` and `rediacc-backups-bench` to rehearse the tool, deploy stub, proxy, account on `bench.rediacc.cloud`, re-apply bench WAF, edit the bench configs. Proves the binding cycle, the Durable Object replay, the container app and a custom domain on the new zone. Old bench objects go last.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target bench --smoke-only` rc 0 and `./rdc.sh --config eu-bench subscription status` rc 0.
    (ticked) 2026-11-08T21:57:21Z by d778be9d: commit:1a984268fa bench config on bench.rediacc.cloud; live 2026-11-08: deploy_proxy --target bench --smoke-only rc 0 (health 200, server-info 401, ready 200 on 7c0935d6), ./rdc.sh --config eu-bench subscription status rc 0 (BUSINESS active), npm run login:bench rc 0 with remote connected; D1 clone 8850/8850 rows; configs-bench 79 objects and backups-bench 1398 objects verified; old bench objects untouched
- [ ] LP-bench [live] Fresh bench receipts after L5. This lifts the edge and stable hold of ruling 4.
  Accept: live-proof bench account-smoke
  (result 2026-11-09T08:27Z, d778be9d live runner) Blocked. `worklist.py --live-proof d778be9d <plan> 062294e2` was first refused checkout-mismatch (the private/account checkout ahead of its gitlink, cleared by 4093bf923b). It is now refused at the ladder: "no VM receipt admits the head tree (failed: the last vm:check FAILED at K1: K1.7 the worker comes back after systemctl reboot (boot before=1794130621 after=0))" (the live-proof log under .ci/cache/live-proof/, which is not tracked). The last receipt is vmc-11071810-cc310c from 2026-11-07 on tree 05304c60cea4, and none of the six fleet VMs (192.168.111.1, .11, .12, .21, .22, .23) answers on port 22. Owed: `./rdc.sh ops up`, then a VERIFIED `npm run vm:check -- --changed` on the head tree (a fleet run, in the fleet queue), then a rerun of this box. L6, L7 and L8 wait on it.

### Shared regions

- [ ] L6 [live] US and ASIA: clone from edge, copy configs, stub, deploy with secrets, enable the executor, register the Stripe webhook on each new host (registration is unverified, and verify-webhook needs it).
  Accept: `.ci/scripts/quality/check_region_consistency.py --live` rc 0 and `PYTHONPATH=.ci python3 -m rediacc_ci.ops.portal_captcha us.rediacc.cloud asia.rediacc.cloud` rc 0.
- [ ] L7 [live] Copy `rediacc-releases` to `releases` and `rediacc-www-media` to `media` with a final delta, move the R2 custom domains, re-apply media CORS and lifecycle, and deploy the `www` Worker. Taking over the `www` custom domain is unverified.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --verify --from rediacc-www-media --to media` rc 0, the same for `releases`, `PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_lifecycle check` rc 0, and `curl -fsSI https://releases.rediacc.com/cli/edge/install.sh` rc 0.
- [ ] L8 [live] EU, with no freeze: clone `account-db-eu` to `account-eu` with `--drop-tables` for the backup rows, copy `rediacc-configs-eu` to `configs-eu`, reset `require_passkey` stores because passkey RP IDs changed, stub, deploy, push secrets, enable the executor, register the Stripe webhook. `backups-eu` stays empty. The old Worker keeps serving hostinger until L9.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --verify --jurisdiction eu --from rediacc-configs-eu --to configs-eu` rc 0, `curl -fsS https://eu.rediacc.cloud/account/api/v1/.well-known/server-info` rc 0, and `npx wrangler d1 execute account-eu --remote --json --command 'select count(*) n from backup_manifests' | jq -e '.[0].results[0].n==0'` rc 0.
- [x] H1 [live] Read hostinger's schedule: which timers exist, their cadence and last runs, including any faster cadence on a critical repository. Read-only, and it sets L9's timing so a re-point does not land inside a run. A run caught by the re-point fails and is fixed forward. Whether this verb leaves renet alone from an unmerged branch is unverified, so the box runs from a released `rdc` if the read says otherwise.
  Accept: `./rdc.sh --config eu-bench backup status -m hostinger` rc 0, with the listing recorded here.
    (ticked) 2026-11-08T15:06:40Z by d778be9d: eu-remote backup status -m hostinger rc 0 + backup strategy list rc 0 on 2026-11-08: one timer nightly-hot (0 2 * * *, hot, store home), last run 2026-11-08T02:00:46Z success, next 2026-11-09T02:00Z, no faster cadence on any repo; L9 re-point stays outside 01:45-03:00Z; read-only verbs ran the machine's own renet
- [ ] M1 [live] Merge the batch through `/pr-merge` with the `Operational-Reason:` line, then release edge from the merged tree, so CD runs on the new names and hostinger gets a released renet.
  Accept: `npm run release:local -- --channel edge` rc 0.

### hostinger

- [ ] L9 [live] Edit the 17 local config and token files to the new hosts. Through `eu-remote`: re-issue hostinger's licences so `renewalUrl` names `eu.rediacc.cloud`, then re-run `backup schedule` and `backup strategy bind`. If the IP binding has moved, `eu-remote` stops at the authenticator and only the operator rebinds it.
  Accept: `./rdc.sh --config eu-remote machine status hostinger` rc 0 and `./rdc.sh --config eu-remote backup status -m hostinger` rc 0, with one licence's `renewalUrl` recorded here.
- [ ] L10 [live] Let the schedule re-upload to `backups-eu`, then prove it: a verify, one restore test under an `-rt` name with only that copy deleted by GUID, and one nightly on the new target.
  Accept: `./rdc.sh --config eu-remote backup verify --store` rc 0, `./rdc.sh --config eu-remote backup usage -o json` rc 0 with a snapshot per repository, and the restore compared by checksum.

### GitHub and delete

- [x] W13 [writer] Prefixes and display names, and every pin: `workflow_run` names in ci-verdict, claude-review, nightly-status, promote-stable, obs-ceph-autobump and pins-soaked; `publish_ci_verdict`, `resolve_ci_run`, `wl_ci`, `sanctioned`, `dispatch_release`, `ci_workflow_invariants`, the profiler allowlist, the citations baseline and literal-sources carriers. Remove the stable Worker jobs from the stable workflow, and R2 and Docker promotion stay. Live rulesets could not be read; `CI Complete` and `Review Complete` are job contexts, so a file rename leaves them alone.
  Owns: .github/workflows/**, the pins named.
  Accept: `npm run check:ci-workflows && npm run check:ci-workflow-gates && npm run check:ci-workflow-invariants` rc 0.
    (ticked) 2026-11-08T18:02:48Z by d778be9d: commit:2d47c02363 W13 landed (5cc5f4a621, feb749a5, 2d47c02363): cd-release-edge, cd-release-stable, ops- prefix, display names and pins; accept check:ci-workflows, check:ci-workflow-gates, check:ci-workflow-invariants rc 0 on the batch tip
    (corrected 2026-11-09, d778be9d) ba72b7d0.3: the three Accept gates are lint-style and do not show the Worker job removal. It is present in the tree, read 2026-11-09: .github/workflows/cd-release-stable.yml holds no Worker deploy job (`grep -i worker` finds only the comment at lines 164 and 166 about the checkout ref), and R2 and Docker promotion remain.
- [ ] L12 [live] Dispatch both release workflows in dry form on the merged tree.
  Accept: `gh workflow run cd-release-edge.yml -f dry_run=true` rc 0 and `gh workflow run cd-release-stable.yml -f dry_run=true` rc 0, then the ci-watch skill's script reads SUCCESS on each run.
- [ ] L11 [live] Only after L10, L12 and the `edge.rediacc.com` redirect in PLAN-website-routing-and-mail.md Z1: archive every old D1 with `backup_d1`, then delete the old Workers, container apps by id, D1s, buckets and bws names, the Pages project `rediacc`, and the 7 orphaned `*-executorcontainer` apps after a last read.
  (note 2026-11-08, review 3f37af26.1) L11 also revokes the Cloudflare tokens the rename leaves behind: the edge backup token rediacc-backup-edge-20261015T151955Z (Cloudflare token id starting 105d60b9, R2 read/write on the edge backup buckets; its rotation-manifest.json entry left with W8, private/account/src/types/rotation-manifest.ts:393 still knows the slug) and the R2 migration token rediacc-r2-migration-20261108T150703Z (Cloudflare token id starting 1897fcf4) once L10's copy is done, and deletes their bws names.
  Accept: `! npx wrangler r2 bucket list --jurisdiction eu | grep -q rediacc-backups-eu` rc 0, `PYTHONPATH=.ci python3 -m rediacc_ci.ops.service_bindings_audit` rc 0, and `./rdc.sh --config eu-remote backup verify --store` rc 0.
    (corrected 2026-11-09, d778be9d) 9006c29d.1: the Accept does not check the two token revocations the note names. Owed when the box runs: the edge backup token (id 105d60b9...) and the R2 migration token (id 1897fcf4...) read back as absent from the Cloudflare token list, and both bws names gone from `bws secret list`; the box is not done on the three Accept commands alone.

## Not verified

- Live R2 and D1 contents and sizes, and whether edge EU holds anything but test orgs: L2 settles these.
- That the first scheduled run really re-uploads everything: a code read until L10.
- Cross-bucket CopyObject on the `.eu.` endpoint, and objects over 5 GiB.
- wrangler taking over an existing custom domain for `www`.
- Live rulesets, Stripe webhook registration on new hosts, and whether `dry_run` is the input name on both release workflows.
- Durable Object migration replay on a new script: L5 proves it.

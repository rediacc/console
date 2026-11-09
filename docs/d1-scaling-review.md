# D1 scaling review: account database

Measured 2026-11-09 between 09:09Z and 10:10Z by session d778be9d. Phases A and B are complete and Phase C ends in the questions below, which are waiting on the operator. Every production number comes from the D1 REST query API, the GraphQL analytics datasets or the R2 S3 API, run under `bws_env exec --profile mirror-config-store`, `cf-usage-report` or `r2-artifacts` with a scoped token minted and destroyed per run. Scratch scripts lived in `/tmp/d1review/` and are not part of the tree.

## Which databases are live

`regions.json` names `account-eu`, `account-us`, `account-asia` and `account-bench`. The first three were created on 2026-11-08 by PLAN-product-domain-rename L3 and are still empty (12 KB, no tables): L8 has not cloned into them yet. The live data is in the databases that plan retires:

| Database | File size before | Tables / indexes | Role today |
|---|---|---|---|
| `account-db-eu` | 45,293,568 B | 84 / 151 | stable EU, serves hostinger, on the never-lose list |
| `edge-account-db-eu` | 4,202,496 B | 84 / 151 | edge EU, archive-then-drop at L11 |
| `account-db-us`, `account-db-asia` | 1,941,504 B each | 84 / 151 | stable US / ASIA |
| `edge-account-db-us`, `edge-account-db-asia` | 1,847,296 / 1,712,128 B | 84 / 151 | edge US / ASIA, seed of the new US / ASIA |
| `account-bench` | 7,872,512 B | 86 / 153 | bench (cloned 2026-11-08 from `account-db-bench`) |
| `account-eu`, `account-us`, `account-asia` | 12,288 B | 0 | new names, empty until L8 |

All of them were measured. Only `account-db-eu` and `account-bench` carry real volume; the US and ASIA databases are dominated by the static seed rows (`exam_questions` 115 KB, `catalog_versions` 36 KB) and by Stripe invoice events.

## Top 3 risks

1. **`event_log` keeps per-call CLI and config telemetry for 400 days.** It is the largest steady-state consumer by an order of magnitude: about 370 B of values plus 7 indexes per row, one row per `cli.*` command, per `config.pull` and per `config.version.read`. At 60 events/day a typical tenant reaches about 14 MB, so one D1 holds about 650 typical tenants before 10 GB. Retention exists (`private/account/src/services/event-log.service.ts:8`, `DEFAULT_AUDIT_RETENTION_DAYS = 400`) and runs; the window is the problem, not the sweep.
2. **The hourly pin sweep fails whenever more than 100 pins expire at once, and pins are 12.4 KB JSON rows.** `sweepExpired` (`private/account/src/services/backup-gc.service.ts:2270-2305`) deletes with one bound parameter per id; D1 allows 100 bound parameters per query. In the last 7 days the `delete from "backup_exists_pins" where id in (?, ...)` statement ran 122 times and wrote 0 rows, while 2,089 of 2,091 pins were past `expires_at` (oldest expiry 2026-10-30). Today's manual cleanup is relief only: the next day with a full-run burst (355 pins in one hour was the norm 2026-10-31 to 11-04) breaks it again. The same unchunked delete serves `backup_upload_leases` and `backup_sessions`.
3. **No per-tenant write cap, and backups cluster in one hour.** D1 executes one query at a time (Cloudflare limits page: at an average of 1 ms per query a database runs at most 1,000 queries per second). Nothing bounds a tenant's audit ingest, config requests or exists asks, and every backup of the test subscription runs between 02:00 and 02:20 UTC. A misconfigured tenant models at about 105,000 write queries/day; 100,000 typical tenants average 270 writes/s, and if a third of the day's writes land in the backup hour the peak is about 2,100/s, twice the single-writer ceiling.

A fourth risk is scheduling rather than storage: hourly backup maintenance visits every subscription inside one 5-minute, 800-subrequest invocation (`backup-gc.service.ts:296-311`), and it already logged `backup_maintenance_budget_exceeded` 128 times since 2026-10-30 with ONE backing-up subscription.

## Quick fixes done

Bookmarks were read from `GET /accounts/<id>/d1/database/<uuid>/time_travel/bookmark` immediately before each write. Restoring any bookmark rewinds the whole database; the restore form is `wrangler d1 time-travel restore <db> --bookmark=<id>`.

| Database | Bookmark (taken UTC) | Statement | Rows before / expired | Deleted | Rows after | File size after |
|---|---|---|---|---|---|---|
| `account-db-eu` | `00000f18-00000000-0000511e-a07f5903e0b351c3ee81072d380ad54e` (09:41:12Z) | `DELETE FROM backup_exists_pins WHERE expires_at < strftime('%Y-%m-%dT%H:%M:%fZ','now')` | 2,091 / 2,089 | 2,089 | 2 | |
| `account-db-eu` | same | `DELETE FROM config_tokens WHERE expires_at < strftime('%Y-%m-%dT%H:%M:%fZ','now')` | 5,523 / 4,381 | 4,381 | 1,142 | 15,732,736 B (from 45,293,568) |
| `edge-account-db-eu` | `00000afa-00000000-0000511e-fce7a9b7b9aec30f09183a3923f78c9d` (09:41:15Z) | config_tokens, same form | 119 / 67 | 67 | 52 | 4,153,344 B |
| `account-bench` | `00000026-00000000-0000511e-9624c0fe69d9554a98d0d7f010b67280` (09:41:16Z) | config_tokens, same form | 3,086 / 1,025 | 1,025 | 2,061 | 7,434,240 B |
| `edge-account-db-us` | `0000080c-00000000-0000511e-c2650a06dd62714b315747b6e9859437` (09:41:18Z) | config_tokens, same form | 239 / 191 | 191 | 48 | 1,740,800 B |
| `edge-account-db-asia` | `000007f5-00000000-0000511e-35430f5121bfa61739fab19f731c4551` (09:41:20Z) | config_tokens, same form | 104 / 60 | 60 | 44 | 1,667,072 B |

Why both are safe: the only reader of pins is the GC reap, which selects `expires_at > now` (`backup-gc.service.ts:3306-3316`), so an expired pin protects nothing. An expired config token is refused and deleted on presentation (`private/account/src/services/config.service.ts:1338-1341`), and no table references `config_tokens` or `backup_exists_pins` by foreign key (read from `sqlite_master`). The pin delete ran on the other databases too and matched 0 rows. `account-db-eu` dropped from 45.3 MB to 15.7 MB, which also shrinks the L8 clone into `account-eu`.

Not deleted, though equally expired and safe: `refresh_tokens` (23 of 23 in `account-db-eu`), `magic_links` (3), `elevated_sessions` (7), `config_cek_rotations` (2), `passkey_challenges` (1), `two_factor_challenges` (1). Together they are under 10 KB, so they wait for the sweep in the plan instead of a hand delete.

## Hints, verified

| Hint | Verdict | Evidence |
|---|---|---|
| ~95% of size from the test subscription | Confirmed | pins 26.16 MB of 35.71 MB values, all subscription `63284afd`; 10,427 of 12,492 events are its org; 5,485 of 5,523 config tokens are one of its users |
| `backup_exists_pins` 2,091 rows, ~13,401 B/row, 2,089 expired, TTL 24 h | Confirmed | max 13,401 B, mean 12,353 B; 1,197 rows hold exactly 200 hashes (`BACKUP_EXISTS_BATCH_MAX = 200`, `backup-storage.service.ts:168`); TTL 24.00 h on every row |
| Cleanup compares ISO text with epoch numbers | Refuted | every timestamp column in every table is ISO-8601 text and every predicate compares ISO with ISO; the real fault is the 100-parameter delete above |
| One busy lineage ~110 pins/day | Partly | lineage `db315abd` wrote 778 pins in 8 days; full-run days wrote 355/day over 11 lineages, delta days 2-47/day |
| `config_versions` 51 rows, ~22 KB, 50 versions in ~30 h, duplicated in R2 | Mostly | 51 rows, 1,095,989 B, 50 versions of one entry from 11-06 01:13 to 11-07 10:58. Not duplicated: R2 holds the encrypted blob, D1 the envelope with per-field commitments the client needs to open it (`config.service.ts:1090-1113`). The envelope lives only in D1, so it can move |
| `config_tokens` 5,523 rows, 4,381 expired, no cleanup | Confirmed | one new row per authenticated config request (`config.service.ts:1395-1420`), no sweep anywhere |
| `event_log` ~12.5k rows / 2.1 MB data, no retention | Size confirmed, retention refuted | 12,492 rows, 2,110,992 B in `data`, 4,991,095 B all columns; 400-day purge runs nightly (`event-log.service.ts:150-176`, deletes seen in the query log) |
| `backup_waiting_chunks` ~5.4k rows ~136 B | Confirmed, not broken | 5,358 rows, 0 past `delete_after` (11-13 to 11-16); 7-day grace plus recount gate (`backup-gc.service.ts:3112-3118`). The rows stand for 22.47 GB of R2 chunks awaiting deletion |
| `catalog_versions`, `exam_questions` fine | Confirmed | static seeds, 36 KB and 115 KB per database |

## Phase A: findings

### Findings table

Steady state and projections use the typical profile below with the code as written (sweeps as designed, the pin sweep assumed fixed). Bytes include an assumed index and page factor of 1.6 for small rows, chosen between the two factors the file-size deltas measure: before cleanup 45.29 MB file over 35.71 MB values (1.27, dominated by 12 KB pin rows), after cleanup 15.73 MB over about 8.1 MB values (1.94). D1 has no `dbstat`, so per-table index bytes are estimates. Rows and bytes now are `account-db-eu` before the cleanup.

| Table | Owner scope | Write driver | Rows | Bytes now (values) | Bytes/tenant steady state | Writes/day/tenant | Projected 100k / 500k | Retention status | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| `event_log` | org / sub / user | each CLI audit event, each config pull/push/read, each auth and backup action | 12,492 | 4,991,095 | 14.2 MB (heavy 54 MB) | 60 (heavy 230) | 1.42 TB / 7.1 TB | 400-day purge, works | `event-log.service.ts:8,150`; `routes/license.ts:455`; `routes/configs.ts:1422` |
| `backup_exists_pins` | lineage | one row per exists batch with a hit (≤200 hashes) | 2,091 | 26,157,189 | 66 KB (heavy 4.7 MB) live 24 h | 5 (heavy 355) | 6.6 GB / 33 GB | hourly sweep BROKEN above 100 expired | `backup-gc.service.ts:2297-2302`; query log: 122 deletes, 0 rows |
| `config_tokens` | user × store | one insert + one update per config request | 5,523 | 1,817,041 | 111 KB at 7 days (heavy 554 KB) | 60 (heavy 300) | 11 GB / 55 GB | none (fixed by hand today) | `config.service.ts:1366-1420` |
| `config_versions` | config entry | one row per push that replaces a version | 51 | 1,109,908 | 150 KB per 3 KB config (heavy 2.2 MB) | 1 (heavy 8) | 15 GB / 75 GB | keeps 50 per config, works | `config.service.ts:416,1135-1163` |
| `backup_waiting_chunks` | lineage × store | one row per unreferenced chunk after prune or recount | 5,358 | 1,066,242 | 560 KB (heavy 1.7 MB) | bulk, 1-12 statements | 56 GB / 280 GB | reaped after 7 d + recount, works | `backup-gc.service.ts:3109,3956,3322` |
| `backup_manifests` | lineage | one row per committed snapshot | 133 | 68,871 | 83 KB | 5 | 8 GB / 42 GB | retention prune, works | `backup-gc.service.ts:3952` |
| `issuance_ledger` + `repo_license_issuance_slots` | sub | one row each per repo licence issue | 384 + 502 | 263,172 | ~120 KB/year, unbounded | ~1 | grows forever | none (chain record) | `drizzle` 0058-0060; query results above |
| `config_entries` | store / team | upsert per push | 2 | 23,682 | 3-12 KB per config | 1 | 0.3-1.2 GB | cascade only, bounded | `config.service.ts:828` |
| `api_tokens` | sub / team | user create; executor token per renewal | 23 | 8,818 | ~90 KB with executor | ~32 | 9 GB / 45 GB | nightly 7-day-grace purge, works | `api-token.service.ts:207-231` |
| `refresh_tokens`, `magic_links`, `elevated_sessions`, `two_factor_*`, `passkey_challenges`, `reauth_tokens`, `password_resets` | user | per login / auth step | 23 + small | ~10,000 | < 5 KB | < 5 | < 0.5 GB | on use only, no sweep | `session.service.ts:138`; `auth.service.ts` |
| `backup_sessions`, `backup_upload_leases` | machine / lineage | per backup run | 0 / 0 | 0 | < 2 KB | 2 | small | hourly sweep, same 100-param bug | `backup-gc.service.ts:1348-1357` |
| `backup_lineage_usage`, `backup_streams`, `backup_stream_status`, `backup_usage`, `backup_retention_policies` | lineage / sub | upserts per run | 12-14 each | ~12,000 | ~5 KB | 5-10 updates | 0.5 GB / 2.5 GB | lifetime of lineage | schema.ts:1480-1907 |
| core: `users`, `organizations`, `subscriptions`, memberships, `teams`, `subscription_activations` | tenant | signup, login, check-in | 9-15 each | ~16,000 | ~8 KB | ~3 (check-in updates) | 0.8 GB / 4 GB | lifetime | sizes query |
| `webhook_processed`, `rate_limits`, `config_cek_rotations`, `notification_reminder_log` | app / sub | per Stripe event, per limited key, per rotation, per reminder | 9-33 | < 11,000 | < 3 KB | < 1 | small, unbounded | none | table map, sizes query |
| `catalog_versions`, `exam_questions`, `study_modules` | app | migration seeds | 1 / 150 / 23 | 155,024 | 0 | 0 | constant | n/a | sizes query |

Typical tenant total, code as written: about **15.2 MB**, 234 write queries/day (650 tenants per 10 GB). Heavy: about **64 MB**, 1,250 writes/day (156 per 10 GB). Misconfigured: about **900 MB**, 105,600 writes/day (11 per 10 GB).

### Tenant profiles

- **Typical**: 5 repositories with daily backups, one 3 KB config, 30 config requests and 60 audit events a day, one config push a day, 50 chunks of prune churn per lineage per day.
- **Heavy**, calibrated on subscription `63284afd` (internal, so an upper calibration point rather than an average): 12 lineages, every one backed up once a day between 02:00 and 02:20 UTC (`backup_stream_status.next_expected_at`, 11-13 manifests/day), 355 pins/day on full-run days, 150 config requests/day (5,485 tokens in 45 days, 2,808 on 2026-10-29), 230 events/day (10,427 in ~45 active days), 8 pushes/day of a 22 KB envelope, 5,400 waiting chunks.
- **Misconfigured**: 20 lineages on the 5-minute RPO floor (`packages/cli/src/services/backup/backup-strategy-validate.ts:153-157`) with full exists asks (2 pins per run), a config pull every minute, 3,000 events/day, 100 pushes/day.

### Production metrics

From `d1AnalyticsAdaptiveGroups` and `d1QueriesAdaptiveGroups` (30 days daily, 7 days per statement), `account-db-eu`:

- Write queries per day ranged 0-14,197; the November mean is about 1,500 for effectively one tenant. Peak day 2026-10-29: 44,529 reads, 14,197 writes, 61,197 rows written.
- Batch latency p50 0.13-0.37 ms, p90 0.2-1.6 ms; the slowest statement p99 is 13.2 ms (the waiting-chunk page read that scans 277,210 rows over 1,644 calls).
- Rows written over 7 days, by statement: `event_log` inserts 18,000+ (3 variants, 7-8 rows each with index writes), `config_tokens` insert 5,730 plus update 1,177, `backup_exists_pins` insert 2,828, `backup_waiting_chunks` bulk insert 1,908, `api_tokens.last_used_at` update 821, `backup_sessions` insert 892, `backup_manifests` insert 804. That attributes about 75% of writes to audit telemetry and config-token rotation.
- `edge-account-db-eu` and `account-bench` run at 4-1,800 write queries a day.

### Other findings beyond the hints

- **Write amplification per config request: 3 writes** (token insert, old-token update, `config.pull` event) plus reads of `config_stores` four times (`sdk_master`, `server_secret`, `cek_generation`, `org_id`: 1,067-1,322 calls each in 7 days).
- **Stripe events store the whole invoice object** (`invoice.*` 4.8 KB each; `account-db-us` holds 87 events at 361 KB, nearly its whole size). The id and a handful of fields would do.
- **`event_log` has 7 indexes** (timestamp, subscription, user, customer, org, partial idempotency), so each event is 7-8 rows written.
- **`logWithinBudget` exists but has no caller** (`event-log.service.ts:107`): the per-token audit budget was built and never wired.
- **Hex-in-text everywhere**: pin hashes are 64-char hex in JSON (66 B per 32-byte hash plus quotes and commas), waiting-chunk hashes 64-char text keys, ids 36-char UUID text. BLOB storage would halve those columns, but the structural moves below remove more.
- **The executor's `api_tokens.last_used_at` update** runs on every executor request (821 in 7 days); a coarse update (only when older than an hour) removes most of it.
- **`backup_waiting_chunks` select scans**: 1,644 page reads read 277,210 rows in 7 days, the heaviest read path; fine at one tenant, but its cost is per page per lineage.

## Deep-dive: write consolidation

### What a pin guarantees

A pin row says "GC must not reap these hashes in this lineage until `expires_at`" (`backup-storage.service.ts:1993-2003`). It closes one race: renet asks `POST <session>/exists`, the server answers "present" for a chunk that is unreferenced and sits in `backup_waiting_chunks` past `delete_after`, renet skips the upload, GC reaps the chunk, and the commit writes a manifest that points at a hole. The insert is awaited before the answer goes back, so a lost insert means no "skip" answer, never a hole. A late pin would reopen the race. Duplicates are harmless (the reap builds a `Set`).

The only reader is the reap (`backup-gc.service.ts:3306-3316`), once per page of 1,000 due waiting chunks, by `(subscription_id, lineage_guid)` and `expires_at > now`. Upload, verify, quota and metering never read pins. Writers: one row per exists batch with at least one hit (`storage:2001`), batches of 200, 4 upload workers per run but sequential exists asks, and one stream per machine, so several machines can pin one lineage at once. Read/write ratio is far below 1.

### Designs for pins

Per-tenant pin writes per month: typical 150, heavy 10,600, misconfigured 345,000. Prices are Cloudflare list prices read 2026-11-09 (D1 rows written $1.00/M after 50M; R2 Class A $4.50/M, Class B $0.36/M; DO requests $0.15/M after 1M, SQLite rows written $1.00/M after 50M).

| Design | D1 bytes/tenant | D1 writes/day/tenant | Other ops / cost per tenant-month | 100k / 500k per month | Concurrency and crash safety | Upload-path latency | Effort | Migration |
|---|---|---|---|---|---|---|---|---|
| a) D1 rows, sweep fixed | 66 KB typical, 4.7 MB heavy | 5 / 355 (+1 delete per hour) | ~6 row-writes per pin with indexes: $0.0009 typical | 6.6 GB and ~$90 / 33 GB and ~$450; storage alone breaks the budget | safe: insert awaited before answer | one D1 write (~1-2 ms query plus the hop to the primary) | S | one-file fix |
| b) R2 object per lineage, CAS | 0 | 0 | 1 GET + 1 PUT per update × retries: $0.0007 typical, $0.048 heavy | ~$70 / ~$350 typical mix | safe if the answer waits for the 200; measured 412 storms under 4+ writers | measured p50 556 ms, p99 38 s under contention (workstation client) | M | dual-write, reap reads both, cut over |
| c) DO per lineage, alarm expiry | 0 | 0 | 1 request + ~2 row-writes per pin: $0.0003 typical; duration within included | ~$30 / ~$160 | safe: DO storage write is durable before the reply (output gate) | one DO RPC, not measured here | M-L | new DO class in 4 configs, dual-write, reap via RPC |
| d) one D1 row per (lineage, run) + R2 hash object | ~1.5 KB | same count of D1 upserts as a), plus 1 R2 PUT each | as b) plus D1 | ~$160 / ~$800 | as a) | D1 + R2 per batch | M | new table, dual-write |
| e) no pins: reap skips a lineage with a live upload lease or backup session | 0 | 0 | 0 | 0 / 0 | safe only if every exists-to-commit window is inside a live lease/session; needs proof, including resume paths | removes the D1 write from every exists batch | M | ship behind a flag, keep pins written for one release, then drop table |

Design e) came out of the code: the pin's 24 h TTL already cannot protect a run that outlives it (`backup-gc.service.ts` comment at 3270 and the lease TTL), the lease rows already exist per run (`backup_upload_leases`), and the reap already scopes by lineage. Its open point is whether renet ever asks `exists` outside a lease (the sample ask and resume with `PendingHashes`, `private/renet/pkg/chunkstore/uploader.go:622-662`); that is a code-reading task for the backup-storage owner, not a measurement.

### Load test (R2 conditional put, measured)

Scratch keys under `_d1-review-loadtest/` in the retired `rediacc-configs-bench` bucket, deleted after each profile, run 2026-11-09 09:57-10:04Z from the workstation over the S3 API (so latency includes the client's internet hop; a Worker binding would be faster and see fewer conflicts). Each update GETs the object, appends one 200-hash batch (13 KB) and PUTs with `If-Match`.

| Profile | Writers | Successful updates/s | 412 conflicts | 429s | Mean / max attempts per success | Latency p50 / p99 | Object size reached |
|---|---|---|---|---|---|---|---|
| raw PUT, no condition | 1 serial | 3.1 PUT/s | n/a | 0 of 62 | n/a | 322 ms | 13 KB |
| raw PUT, no condition | 8 parallel | 12.5 PUT/s | n/a | 116 of 249 (47%) | n/a | n/a | 13 KB |
| typical (1 update / 5 s) | 1 | 0.18 | 0 | 0 | 1.0 / 1 | 556 / 828 ms | 150 KB |
| heavy | 4 | 1.22 | 203 | 0 | 3.58 / 45 | 844 ms / 38.4 s | 995 KB |
| misconfigured | 16 | 0.90 | 661 | 0 | 7.78 / 37 | 2.1 s / 40.8 s | 736 KB |

Readings: the documented "1 per second" limit binds concurrent writers (47% 429s at 8), not a serial one (3.1/s clean). Under CAS the key saturates at about 1.2 successful updates/s whatever the writer count; more writers only add conflicts, and the tail latency reaches 40 s, which would stall an upload. Every update rewrites the whole object (up to 1 MB here), so Class A ops stay one per batch and bytes moved grow with the object. A per-session object (one writer) avoids conflicts but multiplies objects and the reap must list them.

**Durable Object prototype: not measured.** It needs a new Worker with a DO class deployed to production, which writes outside this task's owned path (`docs/d1-scaling-review.md`) and is a live deploy. Ready brief for a writer plus a live box: a throwaway Worker `d1-review-do-probe` with a SQLite-backed DO class `PinBuffer` (methods `pin(hashes[], ttlMs)` and `live(): hashes[]`, alarm deleting rows past expiry), deployed to bench, driven by the same three profiles from inside a second Worker so latency excludes the internet hop; record p50/p99, requests and rows written from DO analytics, then delete the Worker.

### The same lens on the other tables

- **`config_versions`**: one writer per config, rare pushes, so concurrency is not the issue; size is. Moving `envelope_json` to an R2 sidecar beside `r2_key` leaves ~300 B per version in D1 (version, pointer, hmac) and adds one Class B GET per version read. A per-config R2 object holding all 50 envelopes would hit the CAS ceiling only on push storms; a sidecar per version has one writer and no CAS.
- **`backup_waiting_chunks`**: written in bulk by GC (one statement per up to 20,000 rows), so D1 writes are already consolidated; the bytes are the issue (200 B/row live 7+ days). One row per prune batch with an R2 object of hashes cuts D1 to a few rows per lineage, but the reap deletes chunks individually, so partial-batch bookkeeping moves into the object (a rewrite per reap page). A DO per lineage holding both pins and waiting chunks is the clean end state if c) is chosen.
- **`event_log` telemetry**: `cli.term.session`, `config.pull`, `cli.repo.list` and the other `cli.*` types are 80% of rows. They are counters, not audit evidence: Analytics Engine (write-only from the Worker, SQL API to read, no D1 row) or a per-tenant daily R2 file fed by a Queue removes them from D1 entirely. Security and billing events (auth, api_token, config.push, licence issuance, Stripe) stay in D1 with a shorter window.
- **`config_tokens`**: one chain per device. Deleting the predecessor once its successor is first used keeps the 3-use grace for a lost response and leaves about 2 rows per device; rotating in place leaves 1 but must re-solve the concurrent-claim logic (`config.service.ts:1357-1393`).

## Phase B: plan

| # | Change | Saves (typical / total at 100k) | Rollout | Risk / effort | Status |
|---|---|---|---|---|---|
| 1 | Delete expired pins and config tokens by hand | 29.6 MB in `account-db-eu` today | done, bookmarks above | none / S | done already |
| 2 | Fix `sweepExpired`: one `DELETE ... WHERE expires_at < ?` with `returning`, for pins, leases and sessions | keeps pins at 24 h (prevents unbounded growth) | ordinary deploy; regression test must count bound parameters, since local SQLite allows 32,766 | low / S | safe to do now |
| 3 | Nightly sweep of expired `config_tokens`, `refresh_tokens`, `magic_links`, `elevated_sessions`, `two_factor_challenges`, `passkey_challenges`, `reauth_tokens`, `password_resets`, `config_cek_handoffs` in `runRetentionSweeps` | config_tokens otherwise unbounded; ~111 KB/tenant cap | ordinary deploy | low / S | safe to do now |
| 4 | Trim Stripe `invoice.*` / `checkout.*` event data to ids and amounts | ~4.5 KB per event | new events only; old rows age out | low / S | safe to do now |
| 5 | Wire `logWithinBudget` or a rate-limit binding on audit ingest and config requests | bounds the misconfigured tenant (105k writes/day) | flag, then enforce | medium / M | needs decision (Q6) |
| 6 | Move telemetry types out of `event_log`; shorten audit window | 14 MB to ~0.3 MB per tenant; 1.4 TB to ~30 GB | dual-write one release, switch portal reads, stop D1 writes, let the purge drain | medium / M | needs decision (Q2) |
| 7 | Pins: design e), or c), replacing D1 rows | 66 KB-4.7 MB to 0 per tenant; 6.6 GB at 100k | flag, dual path one release, drop table (SQLite table drop, no rebuild needed) | medium / M | needs decision (Q1) |
| 8 | `config_versions.envelope_json` to R2 sidecar | 150 KB-2.2 MB to ~15 KB per tenant | dual-read (sidecar first, column fallback), backfill 121 rows, null the column, then drop via table rebuild | medium / M | needs decision (Q4) |
| 9 | `config_tokens` predecessor delete on first successor use | 111 KB to ~1 KB per tenant, one write fewer per request | ordinary deploy after 3 | medium / S-M | needs decision (Q3) |
| 10 | `backup_waiting_chunks` compaction | 560 KB to 200-300 KB (A) or ~5 KB (B/C) | table rebuild or new structure | medium / M-L | needs decision (Q5) |
| 11 | Coarse `api_tokens.last_used_at` update (skip when under an hour old) | ~800 writes/week now, per executor | ordinary deploy | low / S | safe to do now |
| 12 | Backup maintenance fan-out: per-subscription work through a Queue instead of one hourly invocation | removes the O(subscriptions) per-hour wall | Queue consumer, cursor kept | medium / M | safe to plan now |

Exact diff for item 2 (`private/account/src/services/backup-gc.service.ts`, end of `sweepExpired`):

```diff
-    await this.db.delete(table).where(
-      inArray(
-        table.id,
-        rows.map((r) => r.id)
-      )
-    );
-    return rows.length;
+    const deleted = await this.db
+      .delete(table)
+      .where(lt(table.expiresAt, now.toISOString()))
+      .returning({ id: table.id });
+    return deleted.length;
```

The early `rows` select can stay as the zero check. Both statements use the same `now`, and new leases expire in the future, so the lease set marked reconcile-due is the set deleted. Item 3 is a sibling of the same class: one `delete(...).where(lt(x.expiresAt, nowIso))` per table, called from `runRetentionSweeps` (`private/account/src/entry/cloudflare.ts:213`). Before landing either, grep for other `inArray(` deletes built from an unbounded select; `inJson` (`backup-gc.service.ts:6762`) is the repo's existing answer.

With items 2-11 done, a typical tenant lands near 200 KB (core 8 KB, manifests 83 KB, audit at 30 days ~90 KB, the rest small), so one D1 holds about 50,000 typical tenants. That is under the 100k target, which is why Q7 asks about sharding now.

### Guardrails

- **Scheduled size and write report.** Extend `rediacc_ci.ops.cf_usage_report` (it already reads `d1StorageAdaptiveGroups`) with `d1QueriesAdaptiveGroups` top statements by rows written, and a per-table row count plus per-subscription top-N from the same D1 query path this review used; alert when a database passes 2 GB or a subscription passes its daily write budget.
- **Per-tenant budget, documented in the repo:** at most 100 KB of D1 and 500 write queries/day for a typical tenant, 1 MB and 5,000 for a heavy one; anything above lives in R2, a DO or Analytics Engine. Location: `private/account/CLAUDE.md` schema section, next to the table list.
- **Review rule:** a migration that adds a per-tenant column able to exceed ~1 KB, or a per-tenant table without a retention sweep and a test that the sweep deletes more than 100 rows in one run, needs a written justification in the migration header. A gate can enforce the second half by listing tables with an `expires_at` column and no `lt(<table>.expiresAt` in a scheduled path.

### Sharding note

Even at ~200 KB/tenant a regional D1 holds ~50,000 tenants. Options, not designed: (1) shard each region by subscription hash across N databases, with a small routing table and global tables (users, email lookup, billing) kept in one database; (2) a D1 per tenant for tenant-scoped tables (Cloudflare allows 1,000,000 databases per account on Workers Paid, the first 100,000 included), with the shared database holding identity and billing; (3) a DO per tenant for the hot, write-heavy state (pins, waiting chunks, config tokens) and D1 for the rest. (1) keeps SQL and migrations simple but needs cross-shard admin queries; (2) isolates noisy tenants completely but multiplies migrations; (3) solves write throughput first and storage second.

## Phase C: questions

Scores: scalability 35%, risk 25% (10 = safest), cost 20% (10 = cheapest), effort 20% (10 = least). Total = weighted sum out of 10. Recommendation marked with **(rec)**. The weights fit; one note: with no customers yet, risk could weigh less (15%) and scalability more (45%), which would move Q1 and Q3 further toward the structural options, but no recommendation below flips.

### Priority 1

**Q1. What replaces `backup_exists_pins` rows?** (item 2 ships regardless)

| Option | Scal | Risk | Cost | Effort | Total |
|---|---|---|---|---|---|
| A. Keep D1 rows, sweep fixed | 2: 66 KB-4.7 MB live per tenant, 6.6 GB at 100k typical (findings table) | 9: one statement, diff above | 6: ~$90/month at 100k | 10: S | 6.15 |
| B. R2 object per lineage with CAS | 7: no D1 bytes, but the key saturates at 1.2 updates/s (load test) | 4: 412 storms, p99 38 s on the upload path (load test) | 7: ~$70/month at 100k | 5: M | 5.85 |
| C. DO per lineage with alarm expiry | 9: per-lineage isolation, no D1 | 6: durable before reply, but unmeasured here | 7: ~$30/month at 100k (DO list prices) | 3: new class, 4 configs, reap via RPC | 6.65 |
| D. No pins: reap skips lineages with a live lease or session **(rec)** | 10: zero bytes, zero writes | 5: changes a data-safety invariant; renet sample and resume paths must be proven inside a lease (`uploader.go:622-662`) | 10: free | 6: M, mostly proof and tests | 7.95 |

**Q2. Where does CLI and config telemetry go?**

| Option | Scal | Risk | Cost | Effort | Total |
|---|---|---|---|---|---|
| A. Stay in D1, per-type retention (telemetry 30 d, audit 400 d) | 4: typical still ~1-3 MB (60 events/day × 30 d × 590 B) | 9: one purge predicate | 8: D1 writes unchanged | 9: S | 7.05 |
| B. Telemetry to Analytics Engine, audit in D1 at 90 days **(rec)** | 8: telemetry leaves D1; audit ~5 events/day × 90 d | 7: portal views that show telemetry need an AE read path | 8: ~180M events/month at 100k, priced per million beyond the included amount | 5: M | 7.15 |
| C. Everything to per-tenant R2 NDJSON through a Queue | 9: no audit in D1 at all | 5: idempotency dedup and portal filters rebuilt | 9: Queue + Class A per batch | 3: L | 6.80 |

### Priority 2

**Q3. How far does config-token rotation shrink?** (item 3, the nightly sweep, ships regardless)

| Option | Scal | Risk | Cost | Effort | Total |
|---|---|---|---|---|---|
| A. Sweep only **(rec)** | 5: 111 KB typical, 5 MB misconfigured; 2 writes per request stay | 10: deletes only refused rows | 7: unchanged writes | 10: S | 7.65 |
| B. Sweep + delete predecessor on successor's first use | 8: ~2 rows per device | 7: must keep the 3-use lost-response grace (`TOKEN_MAX_USAGE`, `config.service.ts:382`) | 8: one write fewer | 7: S-M | 7.55 |
| C. Rotate in place, one row per chain | 9: 1 row, 1 write per request | 5: rewrites the F8 concurrent-claim logic (`config.service.ts:1357-1393`) | 9 | 5: M | 7.20 |

A and B are within 0.1; A is recommended now because it is safe today, and B follows if Q8's growth numbers make config traffic large.

**Q4. Where does `config_versions.envelope_json` live?**

| Option | Scal | Risk | Cost | Effort | Total |
|---|---|---|---|---|---|
| A. Keep in D1, cut history from 50 to 10 | 5: heavy 2.2 MB to 440 KB | 8: users lose older versions | 9 | 10: one constant | 7.55 |
| B. R2 sidecar per version, pointer in D1 **(rec)** | 9: ~300 B per version | 7: one extra GET per version read; 121-row backfill | 8: Class A per push, Class B per read | 6: M | 7.70 |
| C. Both | 10 | 6: both risks | 8 | 5 | 7.60 |

**Q5. What happens to `backup_waiting_chunks`?**

| Option | Scal | Risk | Cost | Effort | Total |
|---|---|---|---|---|---|
| A. Keep rows, compact (BLOB hash, narrower key) **(rec)** | 5: ~40% smaller, still 1k-50k rows per tenant | 8: one table rebuild | 8 | 7: M | 6.75 |
| B. One row per prune batch + R2 hash object | 8: a few rows per lineage | 5: reap bookkeeping moves into a rewritten object | 8 | 4: L | 6.45 |
| C. In the per-lineage DO from Q1-C | 9 | 5 | 7 | 3: only cheap if Q1 is C | 6.40 |

### Priority 3

**Q6. Per-tenant write caps?**

| Option | Scal | Risk | Cost | Effort | Total |
|---|---|---|---|---|---|
| A. None (today) | 2: one misconfigured tenant models at 105,600 writes/day | 3: shared single writer exposed | 10 | 10 | 5.45 |
| B. Per-subscription daily counter row in D1 | 6: adds a write to every capped request | 7 | 7 | 6: M | 6.45 |
| C. Workers rate-limiting binding on audit ingest, config requests and exists asks **(rec)** | 8: no D1 writes; per-colo approximate | 7: a false refusal is a retry, not data loss | 9 | 7: S-M | 7.75 |

**Q7. When to shard a region's account database?**

| Option | Scal | Risk | Cost | Effort | Total |
|---|---|---|---|---|---|
| A. One D1 per region until a region passes ~25,000 tenants, with the Phase B fixes and the size report as the trigger **(rec)** | 3: ~50,000 typical tenants per D1 after fixes | 9: nothing changes now | 9 | 10 | 7.10 |
| B. Shard by subscription hash now | 8 | 5: cross-shard admin, login-by-email and billing queries | 8 | 3: L | 6.25 |
| C. D1 per tenant for tenant-scoped tables (1,000,000 allowed per account) | 10 | 4: per-tenant migrations at scale | 6: per-database overhead beyond 100,000 | 2: XL | 6.10 |

**Q8. Growth assumptions for the "change nothing" dates.** The repo states none. Scoring does not apply; the numbers set the dates. With the code as it stands and pins swept, a region reaches 10 GB at about 650 typical or 156 heavy tenants; with the pin sweep still failing, every heavy tenant adds about 4.6 MB/day on full-run days, so 100 such tenants fill a database in about 22 days. Write throughput (1,000 queries/s at 1 ms, 86.4 million a day) is reached at about 369,000 typical tenants on average (234 writes a day each) and about 48,000 if a third of the day's writes keep landing in the backup hour, so the backup hour, not the average, sets the limit. Needed: expected tenants per region at 6, 12 and 24 months, and whether tenant backup schedules will be spread or left at a fixed hour. DEFAULT if unanswered: 1,000 new tenants a month per region, schedules spread by the CLI with jitter.

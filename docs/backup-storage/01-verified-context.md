# 01. Verified context

Status: verified 2026-08-09 on branch main (console + private/renet + private/account
at that day's HEADs). RE-VERIFY BANNER: every file:line below was confirmed by a
read-only agent on that date; the tree moves, so re-check any line you are about to
build on. Provider facts cite official docs fetched the same day.

## The system being replaced (measured, not theory)

`renet backup sync push` takes a read-only btrfs snapshot of the whole datastore and
runs one rclone process per repo to OneDrive. Every repo is a single LUKS image
(largest 137 GB) re-uploaded in full every run. OneDrive's quotaLimitReached (HTTP
507) is a daily upload budget; rclone has no resume, so a killed 128 GB upload banked
zero bytes. Budget detection, per-repo invocation, and `pkg/backupstate` were bolted
on in production (`cmd/renet/backup_sync_perrepo.go:12-24` records the incident). The
snapshot-lifetime race with `rediacc-storage-maintain` was fixed in renet#94: age is
parsed from the snapshot NAME and a shared flock `.backuplock-<suffix>` is held for
the snapshot's lifetime (`pkg/prune/datastore.go:126-160`).

## Foundation facts the design rests on

- A repo is ONE FILE: `<datastore>/repositories/<guid>`, a LUKS2 image on
  loop-mounted btrfs. Every git-like verb is `cp --archive --reflink=always`, an
  `os.Rename` swap, or a JSON write. Commits are immutable reflink clones; the DAG
  is `CommitParent` in `.rediacc.json`, mirrored at `.interim/state/<guid>/`
  (`pkg/repository/state.go:22-69`). Branches/HEAD live only in the CLI config.
- The delta primitive exists and is metadata-only: `delta.Compare(base, target)`
  walks FIEMAP extents and returns merged `ChangedRange{Offset,Length}`
  (`pkg/delta/compare.go:10-23`), seconds per repo, zero data reads. Wire format
  `FMDELTA` exists (`pkg/delta/format.go`); its footer hashes payloads but NOT
  offsets (`format.go:89-97`), a known weakness.
- Constraints: Compare/Apply refuse mismatched sizes (`compare.go:41-44`), and
  auto-grow makes size changes routine (`cmd/renet/repository_maintain.go`), so
  today's delta path silently degrades to full transfers on growth. The `shared`
  FIEMAP strategy reports zero changes after a btrfs subvolume snapshot; use
  `physical` (`cmd/renet/backup_push_delta.go:36-47`).
- LUKS images are born `fallocate`d (`pkg/storage/luks.go:101`); unwritten regions
  are `FIEMAP_EXTENT_UNWRITTEN` ("space allocated, but no data (i.e. zero)",
  `pkg/fiemap/fiemap.go:34`); `--allow-discards` is always on
  (`pkg/luks/luks.go:399-409`) so trimmed regions become holes. A "zero cell" is
  decided from FIEMAP metadata, never content. Written ciphertext is never zeros.
- aes-xts is length-preserving and sector-local (`pkg/repodiff/types.go:1-19`):
  unchanged plaintext at the same offset yields identical ciphertext, and forks are
  reflink clones sharing offsets and the LUKS header. Content-addressed cells
  therefore dedup across snapshots and across a lineage's forks.
- Cluster tier is the SAME stack: Ceph replaces only the block device under the
  datastore (`pkg/datastore/backend_ceph.go:92-129`); repos and k8s CSI volumes
  (`pkg/kubevolume/csi.go:26-38`) are LUKS files on btrfs either way; FIEMAP works
  unchanged. Gap: scheduled backup hardwires the machine default datastore
  (`backup-schedule.ts:195`, `backup-ops.ts:138`) while every cluster datastore is
  named; enumerate like `repository maintain --all` (`repository_maintain.go:209-223`).

## Verified provider facts (Cloudflare, official docs, 2026-08-09)

- R2 pricing: Standard $0.015/GB-mo, Class A $4.50/M, Class B $0.36/M, zero egress.
  IA: $0.01/GB-mo, $9/M, $0.90/M, $0.01/GB retrieval, 30-day minimum billing; IA was
  announced beta 2024-05-29 and no GA note was found. Ops are noise at our scale
  (137 GB seed at 8 MiB cells is about $0.08 of Class A); storage is the bill.
- Temp credentials: bucket-scoped, prefix-scopable, TTL field required (bounds NOT
  documented). `object-read-write` INCLUDES delete. Write-without-delete exists only
  via LOCAL JWT SIGNING with an `actions` array ("local signing only" per docs), and
  local signing needs no API call, which matters because the R2 REST API is limited
  to 1,200 requests per 5 minutes account-wide.
- Conditional writes: If-None-Match/If-Match supported on PutObject (412 on
  conflict); multipart conditionals unproven. Cells stay single-part (5 GiB cap is
  ample for MiB cells).
- Bucket locks: prefix-scoped retention, up to 1000 rules, removable via API, so NOT
  WORM against a compromised admin credential. Lifecycle: expiry + IA transition,
  prefix-scoped; lifecycle APIs are Cloudflare-side, NOT reachable via the S3 API.
  Event notifications go only to Cloudflare Queues. Per-bucket GraphQL metrics exist
  (31-day retention, undocumented lag): sanity check, never billing truth.
- Limits: 1M buckets/account, unlimited objects, 1 write/sec per object key, bucket
  management ops 50/sec. D1: 10 GB/db, 50k dbs/account, single-threaded writes.
  Workers cron: every-minute allowed, 15-min wall ceiling for scheduled handlers.
- MinIO is archived and read-only (verified via GitHub API): no fallback there.
- RustFS: presigned PUT/GET officially supported (maintainer confirms signed
  Content-Length is validated), Apache-2.0, but its own Docker Hub page says "Do NOT
  use in production environments!", there has never been a stable 1.0.0, and WORM,
  SSE, conditional writes, and lifecycle each shipped broken within the last eight
  months (issues closed since, but the pattern stands). Keep for dev/CI; do not make
  it a production system of record without the conformance probe suite.

## Verified backend facts (private/account)

- Deployed topology is SEVEN regional workers under `workers/account/wrangler.*.toml`
  (eu/us/asia, edge-*, bench) with R2 BINDINGS ONLY, no S3 keys; the root
  `private/account/wrangler.toml` is a stale orphan that misdescribes production.
- No byte metering, no credential minting, no presign code, no data-lifecycle policy,
  no GDPR deletion surface anywhere. Every quota is a count or a client-declared
  number. The `BlobStorageService` interface is fully buffered Uint8Array put/get
  (`src/services/blob-storage.service.ts:15-21`).
- Machines hold NO credentials: the Ed25519-signed license blob is the bearer for the
  one renet-to-account call (`pkg/license/renew.go:261-266`, endpoint comment at
  `src/routes/license.ts:184-191`); the URL is stamped into the blob by the issuing
  server. `config_tokens` (hashed, IP-bound, rotating) is the short-lived-token
  precedent.
- The CLI tunnel seals, base64s, and buffers every request (`account-client.ts:191-268`,
  `app.ts:542-621`, no timeout on the fetch): control plane only, structurally
  unusable for bulk data.
- Delegation certs carry CEILINGS, not consumable budgets (`maxTotalIssuances` is a
  comparison against a server-assigned sequence, `repo-license-verify.service.ts:250`);
  on-prem admin cannot edit subscriptions (no `/admin/*` mounted on-premise); on-prem
  numbers arrive inside the signed cert. Community fallback is the universal end
  state of every subscription ending (`webhook.service.ts:324-378`); the over-quota
  precedent is hard-cap new claims, soft-carry existing with an `over_limit` flag
  (`subscription.service.ts:1477-1548`). 60 days is the shipped "after the money
  stops" number (`subscription.service.ts:83`).
- The quota UI template is complete: `PLAN_LIMITS` defaults + nullable override
  column + usage-adjustment column + per-unit rows + portal route + `ProgressBar`
  (70/90% colors) + admin edit page (see 03-implementation-map.md).

## Findings ledger (about 47 items; ALL get fixed inside this program)

Correctness (wave 0 unless noted):
1. `backup restore` writes a fresh random credential onto a reused GUID
   (`commands/backup.ts:210-216`); the GUID-keyed credential map collides and
   mountability depends on the ALPHABETICAL ordering of the `--as` name; the failing
   case also shadows the live source repo's credential. `repo fork` does it right
   (`repo-fork.ts:182`). No rekey path exists anywhere (only slot-1 keyfile add/kill).
2. `--bwlimit` on `rdc repo push/pull/migrate` is a hard error, live-verified:
   the vault builder appends it (`pkg/functions/commands/backup.go:410-412,535-537`)
   but neither renet verb registers the flag. Documented as working in
   `backup-restore.md:51,72,145`.
3. Scheduled backups are invisible to `rdc backup list`: sync push writes GUIDs to
   the folder ROOT (`backup_sync.go:466`) while repo push writes `hot/|cold/`, and
   the listing merges only hot and cold (`commands/backup.ts:87-102`).
4. `.pull-<guid>` staging leak: SIGKILL mid-pull leaves a full-size image nothing
   reclaims (`backup_sync_pull.go:265`; absent from every pruner scan).
5. `acquireSnapshotLock` degrades to a silent no-op on flock failure
   (`backup_sync.go:357-362`), reintroducing the maintain race it exists to prevent.
6. `backup sync push` holds no `.lock-<guid>`, so `prune.IsRepoBackupActive` answers
   false during a datastore-wide push (`pkg/prune/datastore.go:250`).
7. The `pkg/delta` btrfs round-trip tests NEVER RUN anywhere: `//go:build btrfs`
   with no CI or documented local invocation (proven via `go test -list` both ways).
8. Production cron never wired: seven deployed worker configs lack `[triggers]` and
   the entrypoint re-exports only `fetch`; the nightly `event_log` retention sweep
   has never run in any region and the table grows unbounded.
9. Edge-channel limit doubling is lost on the first plan transition
   (`subscription.service.ts:557-565` uses the non-env-aware limits fn) and never
   returns; untested for transitions.
10. `config_versions` is never pruned: one D1 row + one R2 object per push, forever
    (`config.service.ts:499-518`).
11. `PUT /configs/:id` has no size limit and `routes/configs.ts` validates NO request
    body anywhere (11 bare `c.req.json<T>()` casts); recommended cap about 4 MB
    (largest real config 267 KB).
12. NUL byte in `config.service.ts:1950` makes the 2085-line file invisible to plain
    `grep -r` (binary classification, exit 0, no warning). Any repo-wide grep sweep
    is silently incomplete. Two-character fix.
13. Duplicate hand-maintained `BackupDestinationSchema` in
    `packages/cli/src/utils/config-schema.ts:133-139` shadows the shared schema and
    strips new fields at input validation.
14. `mutation-gate.ts:11` falsely claims to be the chokepoint for every config
    mutation; it covers two commands, and unregistered pointers fail open with an
    audit string that fuses "public or unregistered".
15. Concurrent org-level config seed pushes can insert duplicate rows (NULL teamId
    unique-index gap), self-documented "found, not fixed" at
    `config.service.ts:544-551`.
16. Dead `-w/--watch` flag on five backup commands, advertised in a curated help
    example, read by nothing.
17. The regenerate hint in five generated contract files and two gate scripts points
    at a nonexistent `./build.sh deploy prep` target; the real command is in
    `check-e2e-coverage.sh:90`.
18. CLAUDE.md documents `commandFactory.ts`, which no longer exists; CLI structure
    section stale.
19. Delta `.delta` footer does not cover offsets (see foundation facts).
20. Equal-size + auto-grow silently forces full transfers (see foundation facts).
21. `tailBuffer`/`errWithStderrTail` live in `backup_sync.go:242,270` but are
    consumed by six surviving call sites: rehome before deletion.
22. `backup_license_test.go` is misnamed: two fork-mirror tests inside must move
    before the file is deleted.
23. `CONFIG_KEY_ORDER` contains singular `'backupStrategy'`, never matching the real
    `backupStrategies` key (`packages/cli/src/utils/config-schema.ts:254`).
24. Hot-mode strategy include/exclude is inert: `--include-repo/--exclude-repo`
    filter only the cold-stop set, never uploads (`backup_sync.go:397`).
25. `--tag`, `--state`, `--password-stdin` on backup push/pull are parsed and unused.
26. Unbounded retain-base accumulation: every machine push mints a fresh
    `randomUUID()` retain-base (`commands/repo-delta.ts:48-50`), pruning only the
    immediately-prior one.
27. `rdc backup run` falls back to EVERY strategy in config when none is bound;
    cancel/status do not (asymmetry, `backup-ops.ts:12-20`).
28. In-flight gate does not cover `toCreate` (`backup-schedule-reconcile.ts:410`).
29. `isFileInUse` reads lsof-absent as not-in-use (`backup_safety.go:86-95`).
30. Tutorial promises a fresh-server pull the addressing layer rejects
    (`tutorial-backup-restore.mdx:69-75` vs `resolve-machine.ts:203-213`);
    `backup-restore.md:65` states the pull mount precondition backwards; restore is
    absent from the backup guide and cheat sheet; `backup-restore.md` omits five
    real commands and teaches hand-editing config where `strategy bind` exists.
31. Marketing/legal claims with no implementation behind them: retention engine and
    a "retention report" verb (fake CLI: no such subcommand), daily automatic boot-and-verify restore
    tests, point-in-time recovery tiers, WORM immutability, dedup-on-target,
    a push-with-immutable flag (the immutable flag exists only on fork). `limits.md:140` admits
    no retention enforcement. Full inventory in 05-docs-and-decommission.md.
32. `blackout.md` carries fabricated social proof (a named-sector bank, invented
    percentages) against a real dated event, in 13 locales, no scenario disclaimer.
33. Solution-video narration has no content-freshness gate (narration not hash-tied
    to copy; tutorials are safe via textHash, solutions are not).
34. Per-GUID state leaks in `/var/lib/rediacc` (maintain state, license blobs,
    backup-last-result) with only reconcile owning an orphan sweeper.
35. `rustfs/rustfs:latest` is an unpinned prerelease tag in all three call sites;
    the CI four-volume erasure config is fake durability (all volumes on one disk).
36. `run-account.sh` exits 0 silently when the account submodule is absent.
37. Dead `S3_*` env vars in `.ci/docker/service/docker-compose.yml:26-30`; service-
    mode RustFS is never actually connected to the account server.
38. Storage-health backup-snapshot pinned bytes are JSON-only, never in text output
    (`pkg/list/output.go:394-421`).
39. `repomerge` silently skips non-regular files contrary to its doc comment.
40. CLI tunnel fetch has no timeout (`account-client.ts:225`).
41. `.claude` docs claim an "ops rustfs" subcommand exists; it does not (renet binary only).
42. `check:ci-design-tree` may not be invoked by any workflow job on one path
    (recorded inside `06-cli-reshape.md:82`): verify, possible dead gate.
43. Portal API-token scope list is hardcoded and drifts from the shared type.
44. `limits.md:138` "jobs queue" contradicts `backup-restore.md:220` "dropped
    silently" (code agrees with the latter).
45. Doc/code divergence on `--destination` semantics (prose says storage picker;
    CLI has `--destination` name + required `--storage`).
46. Blog claims `rdc backup status` surfaces cold-backup sidecars; it reads
    systemctl + journal only.
47. `nis2-effectiveness` blog names per-strategy sidecar artifacts as a compliance
    trail; dies with the old path, must be rewritten in wave 4.

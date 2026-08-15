# 03. Implementation map

Status: verified seams, 2026-08-09, branch main. Every file:line is a hypothesis to
re-verify before editing. This file is organized by wave-1/wave-2 writer ownership.

## Writer A (wave 1): private/renet, exclusive ownership

New package (suggested `pkg/chunkstore`): grid chunker + manifest builder + uploader
(grant abstraction: r2-temp-creds | presigned-s3 | direct-https) + journal. Fixture
generators and tests MUST import the same chunker/hasher/serializer (the license
mint-tool principle, `.ci/scripts/private/license-mint/main.go:4-10`; a hand-written
format once left a battery check dormant for its whole life).

- Anchors: `<datastore>/.chunk-anchors/<guid>`, read-only reflinks (NOT
  `.backup-anchors`: that name is matched by three live `.backup-*` scanners, one of
  which deletes matches, so it would be reaped on every `machine prune`; the
  `.chunk-` prefix dodges them, same tactic as `.backuplock-`). Verified safe:
  `pkg/prune` scans only specific dirs/prefixes, `InventorySweep` touches only
  loop/dm devices (`pkg/datastore/inventory.go:30-41`), `validGUIDs` skips
  dot-entries (`pkg/prune/datastore.go:549+`), auto-grow touches only mounted repos.
  Anchor integrity: journal records manifest id + size + spot-hash sample; any doubt
  degrades to a full local rehash (I/O cost, zero corruption).
- Journal: `/var/lib/rediacc/backup-journal/<datastoreID>-<guid>.json`, keyed by
  datastore+GUID (fork GUID-collision incident recorded at `pkg/license/store.go:26-36`),
  written with the ONLY atomic+fsynced pattern in the tree
  (`pkg/backupstate/backupstate.go:116-151`), mode 0700/0600. Extract a shared
  `pkg/atomicjson` (ten sites duplicate the pattern at three quality tiers). Ship an
  orphan sweep mirroring `sweepOrphanReconcileState`
  (`cmd/renet/repository_reconcile.go:239-282`); nothing else has one.
- pkg/delta: lift the equal-size requirement (compare common range, tail = changed);
  keep strategy `physical` for snapshot comparisons.
- New verbs via `RegisterWithSchema` in `pkg/functions/commands/backup.go` (e.g.
  `backup_verify`, snapshot-addressed restore); regenerating the six TS contract
  files is the LEAD's job, single-handed (real command in
  `check-e2e-coverage.sh:90`; the documented `./build.sh deploy prep` target does
  not exist).
- Transient-state skip list before touching a repo: `.merge-in-progress`,
  `.takeover-in-progress`, cold-backup sidecars (`coldbackup.RunningPath`),
  `.pull-<guid>`, merge scratch images, plus the repo flock discipline (shared for
  backup, exclusive for restore, matching push/pull today).
- Cold mode: reuse `backup_sync_cold.go` semantics (sidecars, restart ladder,
  concurrency heuristic, `REDIACC_COLD_BACKUP_CONCURRENCY`) with the new upload
  engine; the watchdog/reconcile consumers of the sidecars survive unchanged.
- Datastores: enumerate default + attached named datastores like
  `repository maintain --all` (`repository_maintain.go:209-223`); cluster repos and
  CSI volumes need nothing else.
- backupstate: the new agent becomes the writer (the old writer dies with sync
  push), keeping `renet list` BackupCoverage truthful.
- Machine-to-server: plain HTTPS like `pkg/license/renew.go` (30s timeout, 1 MiB
  response cap, flock, jitter); session mint by presenting the license blob; all
  machine-facing URLs use ONE host value per run (the `drill_bridge_host` lesson:
  API-token IP binding keys on the Host header, `scripts/drills/lib.sh:648-690`).

## Writer B (wave 1): private/account, exclusive ownership

- Schema (drizzle `0048+`): subscriptions gain `storageQuotaBytes` (nullable
  override) + `storageUsageAdjustment`; new tables: backup ledger (per-subscription
  aggregates + per-repo stored bytes), manifest index, leases, pins, stream ids.
  KEEP D1 LEAN: no per-chunk rows (10 GB cap, single-threaded writes); chunk truth
  is the bucket manifests. Register every table in `src/db/scope-registry.ts`
  (ORG_SCOPED_INDIRECT via subscriptionId) or `scope-audit.test.ts:74-80` hard-fails.
- Plan defaults: `PLAN_LIMITS` in `packages/shared/src/subscription/constants.ts:19-42`
  (community 10 GB) + `PROGRESSIVE_LIMIT_KEYS` monotonicity test. Do NOT add the
  edge-doubling line for storage (deliberate).
- Routes (new group `src/routes/backups.ts`, mounted in `routes/index.ts` AND in
  `src/routes/on-premise-index.ts:21-47`, which is a hand-curated subset where
  omission means silently absent on-prem): session mint (blob exchange), grant mint
  (local JWT signing with `actions`; parent R2 token as a worker secret + rotation
  slug), exists-batch (creates pins), manifest commit (idempotent by snapshot id;
  updates ledger, releases lease), usage, verify/scrub, GC. `responds()` DTOs in
  `src/dto/backup.dto.ts` + dto-conformance entries; the airlock strips undeclared
  fields silently, and the planted-strip control (license drill leg f,
  `scripts/drills/license.sh:996-1006`) is the proof pattern.
- Tunnel: any route in `createRoutes()` is automatically tunnel-reachable; no
  tunnel-side work.
- Cron: revive the seam by adding `[triggers]` to the SEVEN
  `workers/account/wrangler.*.toml` files and re-exporting `scheduled` from
  `workers/account/src/index.ts` (also fixes the dead event_log sweep, finding 8).
  Node/elite side uses the `setInterval` precedents (`app.ts:480-491`,
  `on-premise.ts:197-205`). One reconcile/GC implementation, two invokers.
- Lifecycle: retention-on-cancel sweep (60-day constant beside
  `DEFAULT_AUDIT_RETENTION_DAYS`), over_limit soft-carry on downgrade
  (`touchActivationSoftClaim` shape), refund freeze, GDPR bucket delete
  (config-store `deletePrefix` pattern, `config.service.ts:379-403`).
- Delegation cert: add `storageQuotaBytes` to the payload
  (`packages/shared/src/subscription/types.ts:247-270`), populate from the
  subscription row in `delegation-cert.service.ts:214-217,329-332`, surface on
  `GET /onprem/cert-status`.
- Adjacent fixes riding along: config PUT size cap (request DTO,
  `encryptedBlob: z.string().max(~4MB)`), config_versions keep-last-N prune, NUL
  byte, stale root wrangler.toml, TEST_MODE seams for the battery
  (`/test/seed-backup-ledger`, `/test/corrupt-chunk` behind `testModeGuard`,
  `routes/index.ts:91-99`).
- Elite backend (per decision 2): filesystem BlobStorage-like chunk routes OR RustFS
  wiring + pinned image; either way the conformance probe suite and elite compose/
  env.template packaging.

## Writer A (wave 2): packages/cli + packages/shared config schema

- Commands: `rdc backup usage | manifests [repo] | verify <repo> [--deep] |
  restore <repo> --at <time|snapshot-id> [--as]`. Reads go through
  `accountServerFetch` (ESLint `no-raw-api-calls`) with a new `backup:read` scope;
  restore stays executor-based. The `--at` selector requires the Go-side FunctionDef
  change (wave 1) + regenerated `BackupPullParamsSchema`
  (`functions.schema.ts:34-49`).
- Scope checklist (7 places): shared union `subscription/types.ts:216-230`; zod enum
  `private/account/src/types/api-token.ts:10-28`; optional PRIVILEGED list; portal
  `AVAILABLE_SCOPES` (`web/src/pages/ApiTokens.tsx:15-26`, hardcoded, drifts);
  13-locale label + hash file; `apiTokenAuth('backup:read')` on routes.
- Schema: destination becomes a `kind`-discriminated union (`z.union` +
  `z.literal`, the `DatastoreBackendSchema` precedent at `schemas.ts:303-314`);
  NEVER a new `provider` string (`buildRcloneArgs` emits `:{provider}:` args
  unconditionally, `rclone-args.ts:53-77`). Retention fields on the strategy.
  Sensitivity entries for every new leaf (`sensitivity.ts:176-190` region); union
  variants cost one entry per distinct leaf name; keep credential-bearing field
  names distinct across variants; a service credential bag copies the
  `vaultContent` container-level `secret` pattern (`sensitivity.ts:194`).
  DELETE the duplicate CLI `BackupDestinationSchema` (finding 13) instead of
  double-maintaining it.
- Host-local runtime state: new `state.backupRuns` bucket in `state-schema.ts`
  (precedents `renetProvision`, `licenseRefresh`), written via
  `configFileStorage.updateState()` (no version bump, stripped from push); any
  non-public state leaf MUST set `commit: false` (`sensitivity.ts:250-256`).
- Enablement: NO flag. Swap the generator body; content-hash reconciliation flips
  every machine on its next `rdc backup schedule`, orphan-removes old units.
  Three traps: keep EXACT unit names `rediacc-backup-<strategy>.{service,timer}`
  (`parseStrategyFromPath` regex, `reconcile.ts:100-114`; a new prefix is
  permanently non-idempotent, a suffix parses as a phantom strategy and gets
  orphan-removed); fleet-wide flip needs `--force` past the in-flight gate;
  `verifyPostDeploy` checks only timers, so extend it if the agent is not
  oneshot+timer. Copy the `-` prefix trick on ExecStartPre (old renet exits
  non-zero on unknown verbs). Mirror BOTH ExecStart composers: the reconcile path
  (`backup-schedule-unit-generator.ts:111-153`) and the ad-hoc path
  (`backup-ops.ts:44-104`) or they diverge.
- DR nudge: `hasRemoteConfig(await configFileStorage.load(name))` (offline, cached,
  never prompts; do NOT use `configService.getCurrent()`, it pulls the network);
  warn via the `formatStaleCacheWarning` stderr pattern on backup enablement and on
  restore into an unenrolled config.
- Restore fixes (finding 1): inherit the source credential (as `repo-fork.ts:182`),
  guard two live records sharing a GUID, add a bootstrap path that restores from
  storage + archived record without the target-exists/source-exists catch-22.
- Gates in order: `build:packages`, `export:command-tree` (STALE TREE FAILS OPEN, so
  first), `generate:cli-contract`, `generate:cli-docs`, `i18n:sync` + real
  translations, `i18n:generate-hashes`. Hand edits: `06-cli-reshape.md` tree line
  (design-tree gate), COMMAND_METADATA planes + audit-log entries
  (check-audit-coverage), MCP block or `mcpExcludeReason` (mcp-coverage test),
  `functionRequirements` note (generated, but verify), argv-acceptance test,
  plane-coverage numeric baselines (167 leaves, 82 proxy-capable) re-baselined.
- Mixed-version hazard: nested new config fields are SILENTLY DROPPED by older CLIs
  (proven empirically; only top-level keys survive `.loose()`). Update every rdc
  install before writing new fields, or bump schemaVersion to 4 for a loud error.

## Writer B (wave 2): private/account/web (portal)

Copy the issuance-quota stack file for file: `BackupStorage.tsx` page routed under
`/account` (nav after Machines), `GET /portal/backup-storage` beside `/machines`
(`routes/portal.ts:373` region), `ProgressBar` (70/90% colors, needs a bytes label),
per-repo stored bytes + retention so users see what to trim; admin override field in
`SubscriptionDetail.tsx:102-142` + `adminUpdateSubscriptionSchema` (it is
`.strict()`) + `PUT /admin/subscriptions/:id` branch + plan-change reset branch
(mind `licenseVisibleChanged`, comment at `subscription.service.ts:550-554`).
GUID-to-name resolution via `useSharedConfigSession()` after splitting the
config-session gate from the paid `webConsole` flag (COMMUNITY is the audience);
degrade to bare GUIDs when locked. New i18n namespace across 13 locales.

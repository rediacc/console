# PLAN: add the chunk-store backup verb (`renet backup snapshot` / `rdc backup snapshot`)
Status: draft
Owner: 97604f47
Updated: 2026-08-14

Scope: the missing verb that makes the chunk engine reachable, plus the
prerequisite that makes it able to succeed. Every anchor below was read in this
session against the working tree on branch `backup-storage`.

## 0. Correcting the brief before planning on it

The finding reproduces. From `private/renet`, `grep -rl pkg/chunkstore --include=*.go .`
returns `cmd/renet/backup_verify.go`, `cmd/renet/backup_verify_test.go` (the brief
missed this one), `cmd/renet/backup_churn_cells.go`,
`pkg/chunkstore/pipeline_integration_test.go`, `pkg/chunkstore/zerodetect_linux_test.go`
and `pkg/prune/identifiers.go`. Nothing calls `chunkstore.Upload`
(`pkg/chunkstore/uploader.go:71`). Confirmed.

Three things in the brief need correcting, and two of them change the plan:

1. **Parts of "wave 2 CLI" are already built.** `packages/cli/src/commands/backup-storage.ts`
   exists and registers `backup usage` (:62), `backup manifests` (:119) and
   `backup verify` (:184). `backup_verify` is already a registered renet function
   (`private/renet/pkg/functions/commands/backup.go:205-215`), already in the tier
   map (`private/renet/pkg/license/tiermap.go:54`), already in the generated
   contract (`packages/shared/src/renet-contract/data/functions.generated.ts:785`)
   and already carries a CLI command-metadata entry
   (`packages/cli/src/config/command-metadata.ts:143`). This plan copies that
   trail rather than inventing one.

2. **Restore is not "somewhere to be decided": it is declared and honestly
   stubbed.** `backup_pull` already carries the `at` param
   (`pkg/functions/commands/backup.go:200`), and `cmd/renet/backup_pull.go:195-196`
   returns `--at %q: snapshot-addressed restore from chunk storage is not
   available in this renet build yet`. The download engine does not exist:
   `pkg/chunkstore` exports no `Download`/`Fetch`/`Materialize`-to-disk function
   (full export inventory read this session; `MaterializeManifest`
   at `manifest.go:209` composes a delta with its parent in memory, it does not
   fetch anything). Restore therefore stays where it already is (`backup pull --at`,
   surfaced by `rdc backup restore`, `packages/cli/src/commands/backup.ts:154`) and
   is OUT OF SCOPE here. It needs its own plan, and that plan is roughly the same
   size as this one. Do not let it ride this verb.

3. **"Wiring plus surface, not new logic" is not true, and this is the load-bearing
   correction.** The Go client (`pkg/chunkstore/session.go`) and the account routes
   (`private/account/src/routes/backups.ts`) were built to different contracts. They
   disagree on the auth header, on three of four endpoint paths, on every request
   body, on the polarity of the exists answer, and on what a "commit" even is. A verb
   written today against `SessionControlPlane` cannot complete a single backup
   against a live server. Section 2 is that reconciliation, and it is a prerequisite
   task, not a footnote.

   This is already known to the live session: `scripts/drills/backup.sh:1032-1080`
   (`leg_h_machine_wire_conformance`) exists precisely to probe these four
   divergences against the live server, and its assertions are written to fail today.
   That leg is the acceptance test for section 2.

## 1. Decision: one verb, named `backup snapshot`

**One verb, not several.** Seed, incremental and resume are not user choices, they
are states the engine detects:

- `PlanSnapshot` decides trusted-vs-rehash itself (`pkg/chunkstore/pipeline_linux.go:176-209`)
  and returns `Delta` only when a trusted anchor existed (`:226-242`), reporting its
  reasoning in `Plan.RehashReason` (`:52-54`) rather than asking.
- `Upload` detects resume from the journal's `Upload.SnapshotID`
  (`pkg/chunkstore/uploader.go:83-91`) and returns early when `ManifestCommitted`
  is already set (`:85-89`).

So a `seed` verb and an `incremental` verb would take the same code path and differ
only in a flag the engine ignores. The one genuine user intent that the engine
cannot infer is "distrust the anchor and re-seed on purpose", and that is a flag
(`--reseed`), not a verb.

**Name.** `renet backup snapshot`, function `backup_snapshot`, CLI `rdc backup snapshot`.

- `push` is taken and means machine-to-machine rsync (`cmd/renet/backup_push.go`,
  registered at `pkg/functions/commands/backup.go:141`). Reusing it would make
  `backup push --to <machine>` and `backup push` two unrelated operations.
- `upload` names the transport; `snapshot` names the artifact the run produces and
  the thing the manifest, the journal anchor and `rdc backup manifests` all already
  call a snapshot (`Manifest.SnapshotID`, `AnchorRecord.SnapshotID`).
- The `backup_` prefix is required, not cosmetic: `check-audit-coverage.sh:150-160`
  derives the audit event type from it (`backup_* -> cli.backup.*`).

**Cobra placement.** `cmd/renet/backup_snapshot.go`, attached in
`cmd/renet/backup.go` beside `cmd.AddCommand(backupVerifyCmd)` (:36).

## 2. Task 0 (prerequisite): reconcile the client to the server contract

The server is the side that must win. It holds the ledger, leases, pins, quota and
the object-key derivation; it is mounted in both `routes/index.ts:108` and
`routes/on-premise-index.ts:37`; and legs a-f of `scripts/drills/backup.sh` already
drive its real routes end to end. The renet client was written first against a
sketch. Change `pkg/chunkstore/session.go` and the manifest step of
`pkg/chunkstore/uploader.go`; change nothing in `private/account`.

| Concern | Go client today | Server today | Fix |
|---|---|---|---|
| Session auth | `Authorization: Bearer <token>` (`session.go:124`) | `X-Backup-Session` header (`backups.ts:50`) | Send `X-Backup-Session` |
| Session response | needs `token` + `baseUrl`, else hard error (`session.go:109-111`); also reads `streamId` | returns `{token, expiresAt, subscriptionId, dataPlaneUrl, grantKind}` (`backup.dto.ts` `backupSessionResponse`); no `baseUrl`, no `streamId` | Client keeps its own control-plane root (derived per section 4); `dataPlaneUrl` is the OBJECT store, not the control plane, and must not be treated as `baseUrl` |
| Stream id | expected on the session response; no client for `/streams` | `POST /streams` with `{repositoryGuid, lineageGuid}` -> `{streamId, created}` (`backups.ts:70`, `backup.dto.ts`) | Add `EnsureStream` to the client; persist into `Journal.StreamID` (`journal.go:74`) |
| Exists path/body/polarity | `POST <base>/chunks/exists` `{lineage, hashes}` -> `{missing}` (`session.go:183-198`) | `POST /exists` `{lineageGuid, hashes}` -> `{existing, pinExpiresAt}` (`backups.ts:86`) | Path `/exists`, field `lineageGuid`, and invert: missing = candidates minus `existing` |
| Exists batch size | default 1000 (`uploader.go:64`) | `BACKUP_EXISTS_BATCH_MAX = 200`, 400 above it (`backup-storage.service.ts:51,416-417`) | Default the client to 200 and derive it from one named constant |
| Grant request | `{lineage, hashes}` (`session.go:203`) | requires `{snapshotId, lineageGuid, declaredBytes, hashes?}` (`backup.dto.ts` `backupGrantRequest`) | Thread `snapshotId` and a declared byte count into `grantSource` |
| Grant response | top-level `Grant` with nested `s3`/`presigned`/`https` blocks and `keyPrefix`, kind `presigned-batch` (`grants.go:17-70`) | `{grant: <flat discriminated union>, leaseId, leaseExpiresAt}`, kinds `r2-temp-creds` / `presigned-s3` / `direct-https`, field `prefix`, no `region` | Re-shape `Grant` unmarshalling to the server's union; rename the kind constant; default region `auto` client-side |
| Commit | `POST <base>/manifests` with the whole encoded manifest (`session.go:222-227`) | `POST /commit` with a SUMMARY `{snapshotId, lineageGuid, streamId, parentSnapshotId?, cellSizeBytes, totalBytes, addedBytes, addedChunkCount}` (`backup.dto.ts`), and it 404s the commit unless the manifest OBJECT is already in the bucket (`backup-storage.service.ts:538-542`) | Two steps: PUT the manifest object under the grant (`manifestPutUrl` on the presigned variant, server-derived key otherwise), then POST the summary to `/commit` |

The manifest-object PUT is the one piece of genuinely new engine logic. It belongs
in the uploader, immediately before `CommitManifest`, so the journal's
`ManifestCommitted` flag keeps meaning "the server acknowledged", and a crash
between the object PUT and the summary POST resumes correctly (the object PUT is
idempotent by content).

`GET /manifests` (`backups.ts:113`) is a CLI read and is unrelated to committing.

**Why the existing tests did not catch any of this**: all five pipeline
integration tests drive an in-process fake `ControlPlane`
(`pkg/chunkstore/pipeline_integration_test.go:100,152,326,353,389` against the
`ControlPlane` seam at `uploader.go:18-29`). A fake that implements the Go
interface agrees with the Go client by construction. This is the classic
hermetic-fixture trap and section 6 addresses it directly.

## 3. Flag surface and JSON record

Flags follow `backup_verify.go:63-67` exactly in style (shared `FlagDatastore` /
`DefaultDatastore` / `DescDatastore` constants, repeatable `--repo` filter):

```
--datastore <path>      default DefaultDatastore, DescDatastore
--repo <guid>           repeatable; filter to specific repository GUIDs
--cell-bytes <n>        default 4194304; ignored when the journal already
                        records geometry for the repo (a change re-seeds,
                        see pipeline_linux.go:178-180)
--reseed                distrust the anchor and upload a full inventory
--parallelism <n>       0 = engine default 4 (uploader.go:176-179)
--bwlimit <rate>        bytes/second cap, same spelling as backup push's
                        --bwlimit; 0/empty = unlimited (uploader.go:43-44)
--dry-run               plan only: no session, no grant, no PUT; emit the
                        record with the counts that WOULD move
```

`--cell-bytes` default: there is no `DefaultCellBytes` constant in the tree today
(the only cell-size numbers are the churn probe's sweep,
`cmd/renet/backup_churn_cells.go:27-30`). Introduce one named constant in
`pkg/chunkstore` at 4 MiB, the top of the design's expected 1-4 MiB band
(`docs/backup-storage/02-design.md:56-60`), and cite the churn instrument as the
way to change it per repo. Validation is already enforced by `PlanSnapshot`
(`pipeline_linux.go:111-113`: positive multiple of 4096).

One JSON object per repository on stdout, `json.NewEncoder(os.Stdout)`, exactly the
`backup verify` loop shape (`backup_verify.go:89-99`):

```go
type BackupSnapshotRecord struct {
    GUID   string `json:"guid"`
    Status string `json:"status"`
    Reason string `json:"reason,omitempty"`

    SnapshotID       string `json:"snapshotId,omitempty"`
    ParentSnapshotID string `json:"parentSnapshotId,omitempty"`
    Lineage          string `json:"lineage,omitempty"`
    StreamID         string `json:"streamId,omitempty"`
    CellBytes        int64  `json:"cellBytes,omitempty"`
    ImageBytes       int64  `json:"imageBytes,omitempty"`
    RehashReason     string `json:"rehashReason,omitempty"`

    ChunksAsked    int   `json:"chunksAsked"`
    ChunksMissing  int   `json:"chunksMissing"`
    ChunksUploaded int   `json:"chunksUploaded"`
    BytesUploaded  int64 `json:"bytesUploaded"`
    GrantsMinted   int   `json:"grantsMinted"`
    Resumed        bool  `json:"resumed"`
    DurationMs     int64 `json:"durationMs"`
}
```

Everything from `ChunksAsked` down is a field-for-field copy of `UploadStats`
(`uploader.go:54-62`), so the record cannot drift from what the engine measured.

Status vocabulary, four values, mirroring the verify convention where one status is
information rather than failure (`backup_verify.go:27-32`):

- `stored`: the run completed. `chunksUploaded: 0` IS the unchanged-image case; do
  not add a fifth status for it, the count already says it and a second success
  status doubles every consumer's branching.
- `skipped`: `PlanSnapshot` returned `*SkippedError` (`pipeline_linux.go:98-103`).
  `Reason` carries `TransientReason`'s text verbatim (`:66-80`): merge in progress,
  takeover in flight, cold backup running, `backup sync pull` staging. This is the
  `no-backup` analogue: information, NOT a failure, and it does not affect the exit
  code. Losing one interval to a merge costs nothing.
- `quota-refused`: the server refused at grant-mint time. Distinct from `failed`
  because the operator action is entirely different (prune or upgrade, not debug).
- `failed`: anything else, with `Reason` set.

Every exit path emits a record, including the skips, for the reason spelled out at
`backup_verify.go:106-108`: a reader counting lines would read silence as health.

**Multi-repo and multi-datastore iteration.** Default (no `--repo`) enumerates via
`chunkstore.EnumerateRepoGUIDs(datastorePath)` (`pkg/chunkstore/repos.go:12`),
the same call `backup verify` uses (`backup_verify.go:80`). One `--datastore`
invocation covers one datastore; named datastores are driven by repeating the verb
per datastore path, which is how the scheduled caller already works. Do NOT build
datastore enumeration inside this verb: `repository maintain --all` already owns
that pattern (`cmd/renet/repository_maintain.go:209-223`), and duplicating it here
creates a second source of truth for which datastores are attached. If the scheduled
unit needs all datastores in one shot, that is a follow-up on the unit generator,
not on this verb.

Repos are processed sequentially in enumeration order. The design's furthest-behind-RPO
ordering (`docs/backup-storage/02-design.md:104-106`) is deliberately NOT built here:
it needs per-repo RPO policy that does not exist yet, and shipping a fake ordering is
worse than shipping none. Say so in the verb's `Long` text.

## 4. Session, credentials and exit codes

Per run, once, before the repo loop:

1. **Resolve the license blob and the lineage.** The installed repo license
   (`pkg/license/store.go:120` `loadRepoLicenseAt` / `:139` `listRepoLicensesAt`,
   datastore-scoped) carries `GrandGuid` (`pkg/license/types.go:16`), which IS the
   lineage the object keys namespace on (`PlanOptions.Lineage`,
   `pipeline_linux.go:28-30`), and `RenewalURL` (`types.go:31`). A repo with no
   installed license gets a `failed` record naming that, not a crash.

2. **Derive the session URL from `RenewalURL`.** There is no backup URL in the
   license payload (full struct read, `types.go:10-39`). Both routes are mounted
   under the same API root: `/licenses` at `routes/index.ts:103`, `/backups` at
   `:108`. So `<...>/licenses/renew` -> `<...>/backups/session` by replacing the
   known suffix. **Fail loudly** when `RenewalURL` does not end in `/licenses/renew`
   rather than string-munging a guess. ONE host value for the whole run, per the
   `drill_bridge_host` rule already recorded at `session.go:22-24`.
   Alternative considered and rejected for this plan: add a `backupUrl` field to the
   license payload. It is cleaner, but it is account-side plus shared types plus
   re-issuing every existing blob, and it lands in writer B's territory. Note it as
   a follow-up.

3. **Mint the session.** `chunkstore.MintSession` (`session.go:82`) with the blob and
   the machine id. A 4xx becomes `*SessionError` with `Code` and `Message` parsed
   from the envelope (`session.go:139-155`); the account error handler emits exactly
   `{error, code, ...details}` (`private/account/src/middleware/error-handler.ts`,
   AppError branch), so `SessionError.Code` is reliable to branch on.

4. **Ensure the stream** (`POST /streams`), persist `Journal.StreamID`. Needed
   because `/commit` requires `streamId` (`backup.dto.ts` `backupCommitRequest`).

Then per repo: `PlanSnapshot` -> `Upload` -> `Plan.Commit()`
(`pipeline_linux.go:329`), with `Plan.Abandon()` (`:348`) on any failure so the
staged reflink does not litter. Note the ordering contract at `:321-328`: rename
first, journal second. Do not "improve" it.

**Quota refusal.** Enforced at grant mint, before any I/O
(`backup-storage.service.ts:325-350`): HTTP 403, code `BACKUP_QUOTA_EXCEEDED`
(`private/account/src/errors.ts:53`), details `{retryAfter, usedBytes, quotaBytes}`.
The verb maps it to a `quota-refused` record carrying the server's message verbatim
and does NOT retry: `retryAfter` is measured in the quota being freed, not in
seconds of patience. Two sibling refusals reach the same path and get the same
treatment with their own codes: `SUBSCRIPTION_LAPSED` 403 (`:317-322`, retain-on-cancel
is read-only) and `BACKUP_NOT_CONFIGURED` 503 (`:305-311`).

**Exit codes.** renet has no exit-code table; the mechanism is an `exitCoder`
interface on the returned error, default 1 (`cmd/renet/command_errors.go:12-36`).
Two codes are in use: 10 for license-required (`pkg/license/runtime.go:34-36`) and
11 for ceph-provision-unavailable (`pkg/infra/ceph/provisionstate.go:78`).

- 0: every repo `stored` or `skipped`.
- 1: any `failed`.
- 16: any `quota-refused`, via a new error type in `pkg/chunkstore` implementing
  `ExitCode()`. Pick 16, not 12-15: the CLI propagates renet exit codes verbatim
  in at least one live path (`RENET_LICENSE_REQUIRED_EXIT_CODE = 10`,
  `packages/cli/src/services/renet/renet-license-contract.ts:7`), and the CLI's own
  table already spends 11 through 15 (`packages/cli/src/types/index.ts:75-96`:
  AMBIGUOUS 11, STATE_MISMATCH 12, HEALTH_GATE_FAILED 13, INFRA_FAILED 14, BUSY 15).
  16 is free on both sides.
- Precedence when a multi-repo run mixes outcomes: `quota-refused` wins over
  `failed` wins over success. The quota is the actionable one, and burying it under
  a generic 1 is how an operator ends up debugging a network that is fine.

**CLI mapping.** `rdc backup snapshot` follows `backup verify`'s shape exactly
(`packages/cli/src/commands/backup-storage.ts:184-214`): `executeRepoFunction`,
`recordBackupRun`, and `process.exitCode` rather than a throw, so a CI step sees the
failure (comment at `:205-206`). Add one branch: renet exit 16 becomes a `CliError`
with `ExitCode.PAYMENT_REQUIRED` (8), which is what the CLI already means by "the
plan is the blocker".

## 5. Blast radius beyond the Go file

Nothing generated is hand-edited. Regeneration commands verified this session.

**Renet contract, six generated files, one generator.**
`RegisterWithSchema` in `pkg/functions/commands/backup.go` (registry at
`pkg/functions/commands/registry.go:82-85`), copying the `backup_verify` block at
`:205-215`, plus a `BackupSnapshotCommand.Build` next to
`BackupVerifyCommand.Build` (`:598-627`) emitting
`sudo renet backup snapshot ...`. `Requirements: []string{"machine","team","repository"}`.
Then:

```
cd private/renet && go build -o bin/renet ./cmd/renet
private/renet/bin/renet functions generate-types \
  --output packages/shared/src/renet-contract/data --version dev
```

That one command rewrites all six of `functions.generated.ts`,
`functions.schema.ts`, `license-tiers.generated.ts`, `vault.generated.ts`,
`vault.schema.ts`, `list-types.generated.ts` under
`packages/shared/src/renet-contract/data/`. The gate is
`.ci/scripts/quality/check-renet-types.sh` (file list at :38-49, diff at :57-64).

The brief's `functions.schema.ts:49` resolves to
`packages/shared/src/renet-contract/data/functions.schema.ts`;
`BackupPullParamsSchema` starts at :34 and `BackupVerifyParamsSchema` at :79.
The `Run: ./build.sh deploy prep` header those files carry is stale: there is no
`build.sh` at the repo root and `private/renet/build.sh` has no such target. Both
of the brief's claims here check out; the real command is the one printed at
`.ci/scripts/quality/check-e2e-coverage.sh:90` and
`.ci/scripts/quality/check-renet-types.sh:74-76`.

**Go-side registries, hand-edited, all three fail the build if missed.**

- `private/renet/pkg/license/tiermap.go` (var at :27, `backup_verify` at :54):
  add `backup_snapshot` with `{tier: TierNone}`. No licensing gating in this
  feature, quota is the only lever (`docs/backup-storage/02-design.md:10-12`).
  `TestTierMapCoversRegistry` fails on omission; gate
  `.ci/scripts/quality/check-renet-tier-map.sh`.
- `private/renet/cmd/renet/functions_commands.go:903` `slowFunctionNames`: ADD
  `backup_snapshot`. It currently lists `backup_push` and `backup_pull`, and the
  `slowFunctionPrefixes` at :898 do not cover `backup_`. A first backup of a large
  repo is a long-running I/O job and needs the extended budget.
  `TestSlowFunctionNamesExist` fails on a stale entry.
- `.e2e-coverage-allowlist` (repo root), read by `scripts/check-e2e-coverage.ts:71`,
  enforced by `.ci/scripts/quality/check-e2e-coverage.sh:51`. Every name in
  `RENET_FUNCTIONS` must be exercised by a live Playwright test or carry a
  `# BLOCKER: <reason>` entry, and the list is burn-down enforced
  (`check-e2e-coverage.ts:490-491`: an entry that becomes covered also fails).
  **Live finding, not caused by this plan:** `backup_verify` is in
  `RENET_FUNCTIONS` (`functions.generated.ts:785`), has zero references anywhere
  under `packages/e2e-tests/`, and is not in the allowlist, so that gate fails on
  the tree as it stands today. `packages/e2e-tests/**` is w3-e2e's; report it to
  the lead rather than editing it (section 7).

**Go i18n.** The extractor's patterns are `errors.New` and `fmt.Errorf`, not cobra
`Short`/`Long` (which is why `backup_verify.go`'s plain-English help is fine while
`backup_pull.go:86` uses `i18n.T`). Every `fmt.Errorf` in the new file must either
go through `i18n.Tf` or be added to the baseline via
`./bin/renet i18n extract --baseline pkg/i18n/baseline.json --update-baseline`
(gate `private/renet/.ci/scripts/quality/i18n.sh:62,71`). Note in passing that
`backup_verify.go:74`'s `fmt.Errorf` is not in the baseline either.

**CLI surface, hand-edited.**

- `packages/cli/src/commands/backup-storage.ts`: new `registerBackupSnapshot`,
  modeled on `registerBackupVerify` (:180-214), called from
  `registerBackupStorageCommands` (:219). Placement matters: the module that writes
  the leaf's `.action()` decides its plane (`packages/cli/scripts/check-command-planes.ts:38-50`).
- `packages/cli/src/i18n/locales/en/cli.json`: `commands.backup.snapshot.*`
  (description, option descriptions, starting/completed/failed, examples). English
  first, then the other 12 locales.
- `packages/cli/src/config/command-docs.ts`: `COMMAND_EXAMPLES` entry in the backup
  block (:237-270) and `COMMAND_KEYWORDS` (:431-435). Entry shape at :36-49; each
  `descriptionKey` must resolve in `en/cli.json` or the generator fails. No
  `COMMAND_OUTPUT_HINTS` entry (this is not a list-shaped `-o json` command; the
  deliberate skip list is at :520-526).
- `packages/cli/src/config/command-metadata.ts`: entry in the backup block
  (:114-160). MCP metadata (shape at :12-26) with `destructive: false`,
  `idempotent: true`, `timeout: 'write'`, OR an `mcpExcludeReason`. Enforced by
  `packages/cli/src/commands/mcp/__tests__/mcp-coverage.test.ts:108,128,164,170`.
- `packages/shared/src/audit/event-schema.ts`: add `'cli.backup.snapshot'` to
  `ALL_EVENT_TYPES`. `check-audit-coverage.sh:129+,150-160` derives it from the
  `functionName: 'backup_snapshot'` literal and fails without it.
- `packages/cli/src/config/command-planes.ts`: the `backup` domain default is
  `machine` (:56), which is correct for this verb, so no entry is needed. Verify,
  do not assume.
- `packages/cli/scripts/lib/option-classification.ts` `TIER_OVERRIDES` (:239):
  derivation already promotes mandatory / kinded / choice options to `common`
  (:295-300). `--reseed`, `--parallelism`, `--bwlimit`, `--cell-bytes` and
  `--dry-run` correctly land in `advanced`. Add an override ONLY if a live run of
  the form shows otherwise; a wrong key fails the gate (`checkOverrideKey`, :393-400).
- `docs/design/06-cli-reshape.md:59`: append `snapshot` to the backup command tree
  line. Gate `npm run check:ci-design-tree` (`scripts/check-design-tree.ts:26-27`),
  bidirectional. Warning recorded at `06-cli-reshape.md:82`: it is in `npm run ci`
  but no workflow invokes it, so run it locally.
  **Live finding, not caused by this plan:** that gate is already RED on this tree.
  `npx tsx scripts/check-design-tree.ts` reports "The CLI has commands the doc never
  lists: rdc backup manifests / rdc backup usage / rdc backup verify". The three
  chunk-store read commands shipped into `backup-storage.ts` without the tree line
  being updated. Whoever owns that uncommitted work should add all four names in one
  edit, and §1.1 wants the reason recorded.
- Numeric baselines to re-baseline, all in
  `packages/cli/src/config/__tests__/plane-coverage.test.ts`: `COMMANDS.length` 170
  -> 171 (:153), `counts.machine` 94 -> 95 (:154), `machineNonInteractive.length`
  90 -> 91 (:208). And `packages/shared/src/cli-contract/__tests__/contract.test.ts:153`,
  `proxyCapableCommands().length` 83 -> 84 (its comment block at :146-152 records
  that `backup verify` was the 82 -> 83 bump). The implementation map's "167 leaves,
  82 proxy-capable" (`docs/backup-storage/03-implementation-map.md:145`) is stale;
  trust the test files.

**CLI generated artifacts, in this order** (the tree gate fails OPEN when stale, so
it goes first, per `.ci/scripts/quality/check-command-tree.sh:5-20`):

```
npm run build:packages
npm run export:command-tree -w @rediacc/cli     # packages/cli/scripts/command-tree.json
npm run generate:cli-contract -w @rediacc/cli   # packages/shared/src/cli-contract/data/{contract.generated.ts,contract.json,i18n/*.json}
npm run generate:cli-docs -w @rediacc/www       # packages/www/src/content/docs/<lang>/cli-application.md x13
npm run i18n:sync                                # backfills non-en locales with English placeholders
#   ... replace every placeholder with a real translation (Sonnet) ...
npm run i18n:generate-hashes                     # packages/cli/src/i18n/locales/.translation-hashes.json
```

`cli-application.md` is GENERATED for all 13 locales
(`packages/www/scripts/generate-cli-docs.js`, input :29, output :33, write :559).
Never hand-edit it. Hashes are regenerated LAST, after real translations: running
them earlier launders placeholders as up to date.

## 6. Tests that fire on a planted defect

The existing pipeline suite proves the engine against a fake that implements the Go
interface, so it agrees with the client by construction and cannot see section 2's
divergences. Every test below is chosen to fail on a specific planted defect.

**Go, `private/renet/cmd/renet/backup_snapshot_test.go` (new file, mine).**

1. *The verb actually calls Upload.* Drive `runBackupSnapshot` against a temp
   datastore with a fake control plane, assert `ChunksUploaded > 0` on a first run
   and that the record's counts equal the stats. Plant: stub out the `Upload` call
   and return a synthetic record; the assertion on `chunksUploaded` fails.
   Guard against the emptiest version of this test: assert on a repo that HAS
   non-zero cells, or the test passes with an engine that uploads nothing.
2. *Transient repos are skipped, reported, and do not fail the run.* Create the
   merge marker (`prune.MergeMarkerFile` under `<datastore>/repositories`, per
   `pipeline_linux.go:67`), assert `status: "skipped"`, the reason text, exit 0,
   AND that a record was emitted. Plant: drop the record on the skip path; the
   line-count assertion fails.
3. *Quota refusal is its own outcome.* Fake control plane returns
   `*SessionError{StatusCode: 403, Code: "BACKUP_QUOTA_EXCEEDED"}` from `MintGrant`;
   assert `status: "quota-refused"` and exit code 16. Plant: classify it as
   `failed`; both assertions fail.
4. *Precedence.* Two repos, one failing and one quota-refused; assert 16, not 1.
5. *`--dry-run` opens no session.* Fake control plane panics if any method is
   called; assert the record still carries the planned counts.

**Go, `private/renet/pkg/chunkstore/session_test.go` (existing file, extend).**
For each of the seven rows in section 2's table, one test asserting the exact wire
shape the SERVER expects: the header name, the paths, `lineageGuid`, the
`existing`-to-missing inversion, the batch ceiling of 200, the grant request fields,
the flat grant union with `prefix`, and the two-step commit. These are the tests the
current suite is missing, and each one fails today.

**Drill, `scripts/drills/backup.sh` (w3-drill's file, NOT mine to edit).**
Section 7 covers the handoff. The tests that belong there rather than in Go are the
ones that need the real server: the JSON contract of the verb as the CLI parser
consumes it, and the end-to-end round trip. Specifically, leg h collapses:
its four probes (`backup.sh:1032-1080`) stop being conformance assertions against a
client that cannot connect and become a real run.

**The instrument check.** Before claiming any of these pass, run each one against a
deliberately broken build and confirm it fails. A conformance test that passes
because it never reached the server is the exact failure mode section 2 exists to
correct.

## 7. Sequencing against live work

Two writers are running now and their paths are off limits to this work:

- **w3-drill** owns `scripts/drills/**` and `private/account/tests/**`.
- **w3-e2e** owns `packages/e2e-tests/**` and `private/renet/pkg/chunkstore/*_test.go`.

That second one collides with section 6's `session_test.go` work.
**Resolution: this plan's implementer does not touch
`private/renet/pkg/chunkstore/*_test.go`.** The wire-conformance tests go to w3-e2e
as a written brief (the seven rows of section 2's table, each with its server-side
anchor), or they wait for w3-e2e to finish and land in a follow-up. The new
`cmd/renet/backup_snapshot_test.go` is NOT under `pkg/chunkstore/` and is safely
this plan's own.

Files this plan's implementer owns: `private/renet/cmd/renet/backup_snapshot.go`
(+ its test), `private/renet/pkg/chunkstore/session.go`,
`private/renet/pkg/chunkstore/uploader.go`,
`private/renet/pkg/chunkstore/grants.go`,
`private/renet/pkg/functions/commands/backup.go`,
`private/renet/pkg/license/tiermap.go`,
`private/renet/cmd/renet/functions_commands.go`,
`private/renet/cmd/renet/backup.go`,
`packages/cli/src/commands/backup-storage.ts`,
`packages/cli/src/config/{command-docs,command-metadata}.ts`,
`packages/cli/src/i18n/locales/*/cli.json`,
`packages/shared/src/audit/event-schema.ts`,
`docs/design/06-cli-reshape.md`, the two baseline test files named in section 5,
`.e2e-coverage-allowlist`, and everything the regeneration commands write.

**What w3-drill should adopt once the verb exists.** Its legs b, c and d currently
emulate the machine in `node` and `curl`: `image_js plan` builds a manifest by
hand and `session_api` posts the bodies (`backup.sh:679-756` seed,
`:757-852` incremental, `:853-880` point-in-time). That emulation is exactly the
hazard the implementation map warns about at
`docs/backup-storage/03-implementation-map.md:10-12` (a hand-written format once
left a battery check dormant for its whole life): a hand-built manifest agrees with
the server and proves nothing about the binary the customer runs. Concretely, once
`backup snapshot` lands:

- **Legs b and c**: replace the `image_js plan` + `session_api` sequence with a real
  `renet backup snapshot` invocation against a throwaway datastore (leg g already
  drives the local renet binary that way, `backup.sh:967`), then assert on the
  emitted `BackupSnapshotRecord` JSON. The assertions themselves survive nearly
  unchanged: "exactly one cell transfers" becomes `chunksUploaded == 1`, and the
  exists-pin assertion becomes an assertion about the server's state after a real
  run.
- **Leg d** (point-in-time restore) does NOT get to adopt anything yet. Restore is
  still stubbed (`backup_pull.go:195-196`). Keep it emulated, and add a note saying
  which plan will replace it.
- **Leg e** (quota refusal, `:881-933`) becomes far stronger driven through the
  verb: it can then assert the exit code 16 and the `quota-refused` record, which is
  the contract the CLI depends on and which no curl can exercise.
- **Leg h** (`:1032-1080`) is the acceptance test for section 2. Its four probes are
  written to describe today's divergence; after Task 0 they should be rewritten as
  positive assertions (the header IS `X-Backup-Session`, the path IS `/exists`,
  the grant body carries `snapshotId`, commit posts a summary to `/commit` after the
  manifest object lands). Do not delete the leg: keep it as the standing guard that
  the two sides have not drifted again.
- **Leg i** (`:1082+`, opt-in, needs a machine) is where a real end-to-end
  `rdc backup snapshot` against an ops VM belongs.

Nothing w3-drill is building is wasted. Legs a, e, f and g test the control plane
and the local binary directly and stay as they are; legs b, c and h are the ones
whose emulation is scaffolding with a scheduled removal date.

**Order of work.**

1. Task 0 (section 2): reconcile the client to the server. Nothing downstream can
   be verified before this.
2. The verb itself (sections 1, 3, 4) plus `cmd/renet/backup_snapshot_test.go`.
3. Renet contract registration and regeneration, tier map, slow-function list.
4. CLI surface, metadata, audit event, docs tree, baselines.
5. Regeneration chain in the documented order, English strings first, then the 12
   translations, then hashes.
6. Hand the drill brief to w3-drill and the wire-conformance test brief to w3-e2e.

**Explicitly out of scope, each needing its own plan:** snapshot-addressed restore
(`backup pull --at`, engine missing); swapping the scheduled unit's ExecStart from
`renet backup sync push`
(`packages/cli/src/services/backup/backup-schedule-unit-generator.ts:128`) to the new
verb, which the design treats as a separate flag-free flip with three named traps
(`docs/backup-storage/03-implementation-map.md:124-134`); RPO-ordered scheduling;
cold-mode integration.

## 8. Risks

- **Task 0 is bigger than it reads.** Seven wire changes plus a new manifest-object
  PUT step in the uploader. If it grows past a session, the honest split is Task 0
  as its own change with leg h as its acceptance test, and the verb second. Do not
  ship the verb on top of an unreconciled client: it would produce a command that
  looks complete and cannot work, which is worse than the current honest absence.
- **The fake control plane will keep agreeing with whatever the client does.**
  Every claim about the wire must be checked against `routes/backups.ts` and
  `backup.dto.ts`, or against a live server, never against the fake.
- **`--cell-bytes` is a one-way door per repo.** Changing it re-seeds
  (`pipeline_linux.go:178-180`), which on a large repo means a full re-upload and a
  full quota charge. The help text must say that in those words.

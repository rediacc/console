# 05. Docs reconciliation and decommission

> **SEVEN of this document's premises were verified stale on 2026-08-14.**
> See `07-execution-record.md` section 4 before acting on anything here. Two of
> them would have deleted working code.


Status: verified 2026-08-09, branch main. Two halves: the claims-reconciliation
matrix (wave 4) and the line-level decommission (wave 5). The full 167-claim
inventory and the 81-behavior parity inventory live in the source session's agent
reports; this file carries the dispositions and the checklists.

## Claims reconciliation (wave 4, English first, then Sonnet x12)

The marketing surface already sells THIS system, not the shipped one. Dispositions:

BECOMES TRUE (write with measured numbers from the battery, never invented ones):

**SUPERSEDED 2026-08-16: the hold below is LIFTED. It was correct when written
and is not correct now.** `pkg/chunkstore/download.go:87` exports `Restore`,
`restore.go` assembles a manifest into a sparse image, renet carries a `restore`
verb (`cmd/renet/backup_restore.go:79`), and `backup_pull.go:51` no longer
refuses blindly but POINTS AT `renet backup restore --at <snapshot>`.
`09-local-roundtrip-proof.md` then proves a byte-identical round trip. The
point-in-time tier copy may be written, against measured numbers as ever. The
original hold is kept below rather than deleted, because a reader who finds this
file from an older link needs to see what changed and why.

**BLOCKED, verified 2026-08-14: point-in-time restore is NOT one of them yet.**
`cmd/renet/backup_pull.go:195-196` still refuses `--at` outright, and
`pkg/chunkstore` exports no fetch-to-disk function, so snapshot-addressed
restore from chunk storage does not exist. Writing the "any point in the last
24h" tier copy today would CREATE a new false claim, which is the exact failure
this reconciliation exists to prevent. Hold that copy until restore ships (its
own plan, roughly the size of the verb plan). Note that existing point-in-time
wording about CoW snapshots is about the LOCAL fork mechanism and is true; do not
confuse the two while editing.

Genuinely becoming true now:
retention engine (quota + GFS retention replaces the two fake retention/strategy
CLI spellings this document used to quote verbatim; both are already absent from
the docs, see the verification note below, and they are named without command
syntax here so the cli-docs scanner does not read them as usage);
dedup on target ("30 daily backups share data"); incremental-only transfer
("bandwidth down 98%", zero-cost-backup storage math); quota-driven cleanup.
Verification claims map to `backup verify` levels + the nightly scrub; the "daily
boot-and-health-check restore test" claim is either descoped in copy or built as a
scheduled restore drill (operator call in wave 4).

HONEST WORDING REQUIRED: immutability = create-only PUT + delete-free machine
grants + server-only deletes (+ optional bucket-lock compliance layer); NOT
certified WORM. SEC 17a-4-style claims stay off the table; strict-WORM customers
get the customer-S3/Object Lock path later.

REMOVED: the internal contradictions (queue vs drop, pull mount precondition,
verification cadence day vs week, destination flag semantics).

**VERIFIED 2026-08-14, and two entries on this list were already false. Check
before acting on the rest.**

- Fake CLI commands: ALREADY GONE. The two command spellings this list named
  (a "retention report" verb and a "config backup-strategy" verb) appear in NO
  locale, and the only immutable flag in the docs is on `repo fork`, which is
  REAL and present in the CLI contract. The push-with-immutable spelling appears
  nowhere. Nothing to remove. (Written without command syntax on purpose: the
  cli-docs gate scans these files for CLI usage and would read an example of a
  NON-existent command as a docs defect, which it did on first writing.)
  (The real strategy verb is `rdc backup strategy`, 16 contract occurrences.)
- Fabricated social proof in `blackout.md`: the "no disclaimer" claim was FALSE.
  Line 11 carried one and the section was headed "Potential Outcome". The actual
  defect was invented specifics narrated in the PAST TENSE about a real dated
  event, which reads as a completed case study whatever the disclaimer says.
  FIXED 2026-08-14: English de-fabricated, and 58 fabricated bullets removed
  across all 12 locales. The locales now owe a naturalization delta because
  English reworded where they simply lost the lines.

The lesson for whoever reads this next: this document's dispositions are
HYPOTHESES about a tree that has moved since they were written. Two of the four
in this section were wrong. Verify each against the tree before doing the work,
and correct the entry rather than silently working around it.

Reference-doc wave: full rewrite of `backup-restore.md` (scheduled sections die,
new system documented, restore finally documented in the guide and cheat sheet);
updates to quick-start, cheat sheet, pruning, limits (quota row replaces "no
retention"), monitoring, repositories, autostart-recovery, architecture,
subscription-licensing (backup-renewal framing dies), `.claude/skills/rdc/*`
(reference.md is generated, regenerate); CLAUDE.md backup sections. (The "stale commandFactory line" this list used to
name does NOT EXIST: verified 2026-08-14, `commandFactory` appears in no doc,
no skill file and no source file. Sixth stale disposition in this document.) All x13 via the doc-translation pipeline; the naturalization
gates fire serially inside `check:i18n`. Tutorial cast: **WRONG, corrected 2026-08-16.**
This said the seven recorded commands all survive decommission and that a
re-record was needed only if wave 2 changed their argv. FOUR of the seven were
retired (`rdc storage import`, `repo push --to <storage>`, `backup list
--storage`, `repo pull --from <storage>`), the cast was fully re-recorded, and
it now carries EIGHT markers. This line is the one that would have let the
tutorial ship teaching commands that refuse: it told a reader the expensive
re-record could be skipped. The slide SVG was worse than stale - it taught
`rdc config storage import`, which has never existed in the command tree under
any spelling.

## Decommission (wave 5, after parallel-run verification)

Scope calibration, proven: `backup sync` is cobra-only, NOT a bridge function; the
four registered verbs (`backup_push/pull/list/delete`) and every generated renet
contract artifact survive untouched. `rdc repo push/pull --to/--from` and `storage
browse` stay.

**Corrected 2026-08-15.** This line used to read "rclone stays an embedded asset
(repo sync, storage browse, migrate)". All three consumers named were wrong, and
the error mattered, because it was the stated reason for keeping a 22.8 MB
payload:

- **`repo sync` never touches rclone.** It is plain rsync over SSH with an SFTP
  fallback (`packages/cli/src/commands/repo-sync.ts:121,157,184,253`).
- **`storage browse` spawns the OPERATOR'S OWN rclone from `PATH`**, not the
  embedded copy, and says so when it is absent
  (`packages/cli/src/services/repo/storage-browser.ts:60,89`). Removing the
  embedded asset does not touch it.
- **`migrate` has no rclone reference at all.**

What actually consumes the embedded rclone is the renet storage backup family:
`backup_push/pull/list/delete` with `--source-type storage`, plus
`backup sync push` (`private/renet/cmd/renet/backup_pull.go:598,645`,
`backup_push.go:841`, `backup_list.go:343`, `backup_delete.go:154`,
`backup_sync.go:509`). `getRclonePath()` (`backup_pull.go:59-69`) prefers the
embedded copy, unlike `getRsyncPath()` (`:44-54`) which prefers the system one.

DELETE (renet): `cmd/renet/backup_sync.go`, `backup_sync_perrepo.go`,
`backup_sync_cold.go` + `_other.go`, `backup_sync_pull.go`; `pkg/backupstate` only
if the new agent has not adopted it (it should adopt it: it becomes the journal's
coverage surface); the `.backup-*` half of `pkg/prune`'s GC kept ONE release for
legacy residue, flagged, then removed. TRAPS: rehome `tailBuffer` +
`errWithStderrTail` (`backup_sync.go:242,270`) first, six surviving call sites;
`backup_license_test.go` holds two fork-mirror tests that must move; regenerate the
renet i18n baseline (12 `backup_sync.*` keys x13 locales = 156 strings +
hashes.json).

DELETE (CLI): `services/backup/` five files, `commands/backup-ops.ts`,
`commands/backup-strategy.ts`, `config-strategy-binding.ts`, the machine
`backupStrategies[]` field and `backupStrategies` family (replaced by the new
schema), `check-cli-docs.ts:116` legacy-rename line. Tests: four Go test files
whole (including the budget-exhaustion cluster, obsolete by construction), the
1060-line `backup-schedule.test.ts`, `backup-status-state`, `backup-strategy`,
`config-strategy-binding` tests; delete-partial line lists for eight more files;
re-baseline plane-coverage (167 leaves) and contract counts (82 proxy-capable);
regenerate command-tree/contract/cli-docs/skill-reference in the SAME commit
(command-tree staleness FAILS OPEN). CLI i18n: 44 `commands.backup.*` keys x13
(572 strings) + `.translation-hashes.json`; do NOT allowlist orphans, delete keys.
The licensing gate on backup (`backup_license.go` sync-path halves,
`refreshRepoLicensesBatch` preflight, ExecStartPre renewal in units) dies per the
all-users ruling; the push/pull validation half and the failed-marker READERS
survive.

E2E: suites 10 and 15 do NOT die (they drive surviving verbs); they get replaced by
the real battery on their own merit. Casts: zero scheduled-path content, nothing to
re-record for decommission. `.e2e-coverage-allowlist`: no edits for decommission
(the two entries are surviving verbs; wave 3 deletes them as coverage lands).

Governance: `docs/design/spec/00-gate-review.md:78` ruling R5 ("backup schedule
stays per-machine systemd: CONFIRMED") and `03-cli-contracts.md:2215` get a
superseding note naming this program, never a silent delete; `06-cli-reshape.md:59`
tree line updated with the gate.

## Migration of real machines (wave 5, operator-in-the-loop)

Hostinger first (hourly OneDrive schedule, nolicense renet): enable the service,
parallel-run beside rclone (deltas are cheap, dual-write costs little), N verified
restores including one cross-machine, retire the OneDrive strategy, then the rest
of the fleet. OneDrive stays read-only until the new store holds the agreed history
depth (default 30 days), then decommission with a date. Do NOT migrate the OneDrive
objects (incompatible whole-image layout; the first R2 full upload IS the
migration; no ingress fee, no budget). Deploy order pinned: account servers, then
renet, then CLI; all wire fields additive; update every rdc install before any new
config field is written (nested-strip hazard).

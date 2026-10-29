# PLAN: copy a machine's repo image to a local path or an external drive, and send it back: `rdc backup download` and `rdc backup upload` move the encrypted LUKS image by client rsync from a snapshot that lives only as long as the session, keep one copy updated in place each week, resume after an interruption, and verify the result

Status: approved -- operator rulings 2026-10-29 (ASKED, all four Recommended options), quoted in "Operator rulings (2026-10-29)" below; the operator asked on 2026-10-29 for a full image copy to a local path that resumes over rsync and survives a forgotten interrupted download.
Owner: d778be9d
Priority: P1 -- no backup today lands on a disk the operator controls. Every copy lives on a machine or in R2, and the only verbs that move an image (`repo push --to`, `repo pull --from`) go machine to machine (packages/cli/src/commands/repo-backup.ts:387-440). A weekly offline copy is the last line of recovery when the provider and the bucket are both gone.
Depends-On: no-dep -- each box builds on code already on main: the reflink snapshotter, the repo flock, the client rsync plumbing and the prune scanner. agent/plans/PLAN-detached-jobs.md and agent/plans/PLAN-snapshot-read-io-cap.md are named under "Related plans" as boundaries this plan keeps, not as prerequisites.
Concurrency: parallel -- R1 (renet helper), R2 (prune and status), X1 (rsync.ts), S1 (state and preflight) and T1 (tests, written red first) have disjoint Owns and run at the same time. C1 follows R1, X1, S1 and T1. I1 and D1 follow C1 and R2. V1 follows R1 and R2. L1 follows every code box and V1, and L2 follows L1. C1 waits for any writer of agent/plans/PLAN-detached-jobs.md, agent/plans/PLAN-backup-restore-path.md or agent/plans/PLAN-config-networkid-discovery.md that holds packages/cli/src/commands/backup.ts. C1 also waits for writers of agent/plans/PLAN-detached-jobs.md and agent/plans/PLAN-ssh-key-source-ranges.md on generate-cli-contract.ts or command-metadata.ts, for agent/plans/PLAN-org-executor-connect-timeout-relocate.md on packages/cli/src/remote/sftp/client.ts, and for agent/plans/PLAN-repo-docker-storage-prune.md on command-policy.ts. X1 waits for any writer of agent/plans/PLAN-sync-remote-file-ownership.md on rsync.ts. R1 waits for agent/plans/PLAN-backup-restore-path.md on private/renet/cmd/renet/backup.go. I1 waits for any other plan's writer on the CLI locale files. Each of these edits is one or two lines, so the conflict sits in the concurrency guard, not in the edits.
Owns: agent/plans/PLAN-backup-local-image.md, private/renet/cmd/renet/backup_export.go (new), private/renet/cmd/renet/backup_export_test.go (new), private/renet/cmd/renet/backup_import.go (new), private/renet/cmd/renet/backup_import_test.go (new), private/renet/cmd/renet/backup.go (two AddCommand lines only), private/renet/pkg/i18n/locales/*.go (two help keys only), private/renet/pkg/i18n/locales/hashes.json (two help keys only), private/renet/pkg/prune/datastore.go, private/renet/pkg/prune/identifiers.go, private/renet/pkg/prune/datastore_transfer_test.go (new), private/renet/pkg/list/storage_health.go, private/renet/pkg/list/types.go, private/renet/pkg/list/storage_health_transfer_test.go (new), private/renet (gitlink bump only), packages/shared/src/renet-contract/data/list-types.generated.ts (regenerated only), packages/cli/src/commands/machine/status.ts (renderPoolSummary only), packages/cli/src/commands/datastore-prune-parser.ts, packages/cli/src/commands/__tests__/machine-status-pool.test.ts (new), packages/cli/src/commands/__tests__/datastore-prune-pull-staging.test.ts (new), packages/cli/src/remote/sync/rsync.ts, packages/cli/src/remote/sync/__tests__/rsync-inplace-partial.test.ts (new), packages/cli/src/remote/sync/image-rsync.ts (new), packages/cli/src/remote/sync/__tests__/image-rsync.test.ts (new), packages/cli/src/remote/sftp/client.ts (one execSession method only), packages/cli/src/services/backup-image/state.ts (new), packages/cli/src/services/backup-image/preflight.ts (new), packages/cli/src/services/backup-image/session.ts (new), packages/cli/src/services/backup-image/transfer.ts (new), packages/cli/src/services/backup-image/__tests__/state.test.ts (new), packages/cli/src/services/backup-image/__tests__/preflight.test.ts (new), packages/cli/src/services/backup-image/__tests__/converge.test.ts (new), packages/cli/src/commands/backup-image.ts (new), packages/cli/src/commands/__tests__/backup-image-download.test.ts (new), packages/cli/src/commands/__tests__/backup-image-upload.test.ts (new), packages/cli/src/commands/backup.ts (one register call and the restoredIdentity export only), packages/cli/scripts/generate-cli-contract.ts (two PROXY_EXCLUSIONS entries only), packages/cli/src/config/command-metadata.ts (two mcpExcludeReason entries only), packages/cli/src/utils/command-policy.ts (two CMD entries only), packages/shared/src/cli-contract/data/contract.generated.ts (regenerated only), packages/cli/src/i18n/locales/*/cli.json, packages/www/src/content/docs/*/backup-download.md (new), packages/www/src/content/docs/*/cli-application.md (regenerated only)
Live-Proof: bench, hostinger -- the new verbs under packages/cli/src are the cli surface, live on bench and hostinger; the rsync and SFTP client changes under packages/cli/src/remote are the cli-remote surface, live on hostinger; the export and import helpers, prune and the pool counters are the renet surface, live on hostinger only (.ci/config/proof-tiers.json). The regenerated contract and list types under packages/shared/src are the account surface, live on bench only.
Updated: 2026-10-29
Worklist: #686494c5, PR-TASK 9f92c43e
First-Seen: 2026-10-29

## Context

### The ask (operator 2026-10-29)

"Snapshot remote machine and download them into my external-drive/local-path via rdc directly. It should work with rsync if available to be able to continue on disconnection. ... a prune improvement, why because let's say I started download, disconnected and forget about it for a week. Then snapshot becomes useless. ... This time it's just for full backup. So, chunks are not needed. But of course via rsync I expect to update what I already have locally by overriding. Since I may do it weekly and don't have much space." <!-- style-ok -->

### What already exists (verified 2026-10-29)

- **Image location.** A repository is one file, `<datastore>/repositories/<guid>`, default datastore `/mnt/rediacc` (private/renet/cmd/renet/backup_push.go:179-180). Directory-based repos (`<guid>.dir`, :183-188) are out of scope.
- **Snapshot.** `BtrfsSnapshotter.Create` runs `cp --archive --reflink=always` into `.snapshot-<guid>-<UTC ts>-<pid>-<rand>` beside the image (private/renet/pkg/snapshot/snapshot.go:221-252). A snapshot taken this way is crash-consistent.
  - backup_push takes the shared flock `.lock-<guid>` (private/renet/cmd/renet/backup_push.go:192) and deletes the snapshot in a `defer` (:250-255).
  - `--checkpoint` runs a CRIU checkpoint plus `fsfreeze` before the reflink and thaws after it (`handleCheckpoint`, private/renet/cmd/renet/backup_push.go:770-830; `thawLUKSMount` :832).
- **Image rsync flags.** The machine-to-machine image transfers use `--partial --inplace --no-whole-file`, plus `--sparse` only for a destination that does not exist yet (private/renet/cmd/renet/backup_pull.go:62-71). Over an existing file, `--sparse --inplace` on rsync 3.2.7 seeks past zero runs and leaves the old bytes in place. private/renet/cmd/renet/backup_transfer_rsync_test.go:79 and :95 pin that behaviour.
- **Pull staging and finalize.** Pull writes into `repositories/.<guid>` under an exclusive lock (private/renet/cmd/renet/backup_pull.go:218, :234), checks the LUKS header with `verifyRepositoryIntegrity` (:608-640, `cryptsetup isLuks` at :633), then renames into place (`finalizeTransfer`, :643-680).
- **Transient states.** `chunkstore.TransientReasonForOwner` refuses a repo while a merge, a takeover, a cold backup or a `.restore-<guid>` assembly is in progress (private/renet/pkg/chunkstore/pipeline_linux.go:118-132).
- **Client rsync.**
  - `getRsyncCommand` covers Windows through MSYS2 and refuses when rsync is missing (packages/cli/src/remote/sync/rsync.ts:21-38).
  - `getRsyncSSHCommand` is private (:48-66).
  - The repo-key branch adds `--rsync-path 'sudo rsync'` with `--numeric-ids --no-links --no-D` (:155-171).
  - `buildRsyncArgs` always passes `--inplace --no-whole-file` (:225).
  - `--verify` replaces `--partial` with `--checksum --ignore-times` (:184-188).
- **SFTP fallback.** `executeSyncWithSftpFallback` switches to SFTP when rsync is missing (packages/cli/src/commands/repo-sync.ts:278-305, `isRsyncNotFoundError` at packages/cli/src/commands/repo-sync-helpers.ts:259). The SFTP path has no resume and no delta (packages/cli/src/remote/sync/sftp-fallback.ts).
- **SSH plumbing.**
  - `execStreaming` ends the channel's stdin at once (packages/cli/src/remote/sftp/client.ts:549-596), so no exec channel stays open with stdin today.
  - repo sync builds a temporary key file and known_hosts for the system `ssh` that rsync uses (packages/cli/src/commands/repo-sync.ts:247-263).
- **Privilege.** The machine's SSH user has `NOPASSWD: ALL` (private/renet/cmd/renet/setup_command.go:854). The sandbox gateway governs repo keys only: a repo key's transfer is confined to the repo's mount (private/renet/cmd/renet/sandbox_gateway_transfer.go:17-28). The image under `repositories/` is outside every mount, so the download and the upload use the machine key with `sudo -n`, the same access `renet execute` already has.
- **Prune.** The `.snapshot-*` and `.restore-*` scans treat an entry as in use while any process holds `.lock-<guid>` in either mode (`repoLockHeld` and `isSnapshotInUse`, private/renet/pkg/prune/datastore.go:60-116; `isRestoreStagingInUse` :212-219; scans :652-669). Prune runs only when asked, through `rdc machine prune` (packages/cli/src/commands/machine/prune.ts:382) and `repository_prune` (private/renet/cmd/renet/repository_prune.go:56).
- **Pool counters watch a dead class.** `scanPool` counts only `.backup-*` directories at the datastore root (private/renet/pkg/list/storage_health.go:213-240). No code creates that class any more: the only producer-side reference left is the name parser at private/renet/pkg/prune/identifiers.go:50. `machine status` therefore never shows a leftover `.snapshot-*` or `.restore-*` (packages/cli/src/commands/machine/status.ts:472-490; the type is at packages/shared/src/renet-contract/data/list-types.generated.ts:244).
- **Registering a restored image.** `backup restore` registers the target with `restoredIdentity(lineage)` and the source's credential, then allocates a network id and records a placement (packages/cli/src/commands/backup.ts:189-205, `restoredIdentity` :300). It then re-renders the backup units (`reconcileBackupSchedules`, :237). `postPushDeploy` starts a repo after a transfer (packages/cli/src/commands/repo-backup.ts:171).
- **Client-side transfer verbs are not proxyable.** `repo sync upload|download|status` sit in `PROXY_EXCLUSIONS` (packages/cli/scripts/generate-cli-contract.ts:79-86) and are MCP-excluded (packages/cli/src/config/command-metadata.ts:473-476).
- **Rate strings.** `bandwidthToBytesPerSecond` parses `100Mbps` and similar strings, refuses ambiguous units, and maps `0` to unlimited (packages/cli/src/services/backup/backup-strategy-validate.ts:42).
- **Low-priority prefix.** The scheduled snapshot runs under `nice -n 10 ionice -c 2 -n 7`, each part only where the tool exists (private/renet/pkg/functions/commands/backup.go:766-781).
- **A realistic small repo.** `mail` on hostinger has a 4,294,967,296-byte image (agent/plans/PLAN-backup-program.md:531).

### Findings made while designing (each one is settled below)

1. **The `--verify` partial drop in rsync.ts is not a defect.** rsync documents that `--inplace` implies `--partial`: an interrupted in-place transfer never deletes the file. `buildRsyncArgs` passes `--inplace` on every real run (packages/cli/src/remote/sync/rsync.ts:225), so `--verify` (:184-188) keeps the partial data. X1 records this beside the code and pins it with a test, so that removing `--inplace` later cannot silently reopen the gap.
2. **Prune deletes a held lock file.** The stale-lock scan lists every `.lock-<guid>` whose image is missing and never probes it (private/renet/pkg/prune/datastore.go:640-650); the removal loop then unlinks it (:757-767).
   - During `backup restore` into a new GUID, and during the upload here, the lock is held while `<guid>` does not exist yet.
   - A first prune unlinks the held lock.
   - A second prune then finds no lock file, so the `.restore-<guid>` staging looks unheld and is deleted mid-transfer.
   - R2 fixes this.
3. **An interrupted pull's staging is never reclaimed.** Pull's staging is `repositories/.<guid>` (private/renet/cmd/renet/backup_pull.go:218). The prune scan skips every hidden name except `.lock-`, `.snapshot-` and `.restore-` (private/renet/pkg/prune/datastore.go:606), so a SIGKILLed pull strands a full-size file that nothing reclaims. This verb does not create that class. R2 still adds it, under the same lock rule, because the operator's prune ask is "nothing outlives its session".
4. **A pull's source-side snapshot is unprotected.** `pullFromMachine` creates the snapshot on the source by `ssh ... cp --reflink` and holds no lock there (private/renet/cmd/renet/backup_pull.go:426-470). A prune on the source during a pull can therefore delete the file the pull is reading. That is outside this plan and is filed as a follow-up (Out of scope).

## Operator rulings (2026-10-29)

Asked 2026-10-29, all Recommended:

1. **The local copy is the encrypted LUKS repo image, as the machine stores it.** It restores as a whole repo, and restoring needs the repo credential from the config. The first download is sparse.
2. **A weekly run updates the local copy in place, delta only, using one copy of space.**
   - A state file beside the image records `incomplete` while a run is in flight.
   - When the run finishes it records `complete`, plus the snapshot time, repo GUID, machine and size.
   - An interrupted run resumes on the next invocation.
   - Between an interruption and the resume the copy is not usable, and the state file says so.
3. **Each run takes a fresh snapshot, held only while its session is alive.**
   - The snapshot is deleted when the session ends or dies.
   - Prune already reclaims an unheld `.snapshot-*`. There is no lease.
   - A resume after a week takes a new snapshot, and rsync sends only the differences against the partial local file.
4. **An upload verb is in scope.** `rdc backup upload <file> --to <machine> [--as <name>]` sends a local image back with the same resume. It checks the LUKS header, finalizes atomically and registers the repo in the config.

## Design

### 1. Verb shape

```
rdc backup download <repo[@machine]>... --to <dir> [--all -m <machine>] [--include-forks]
                    [--bwlimit <rate>] [--checkpoint] [--retries <n>] [--skip-verify]
                    [--skip-space-check] [-o json]
rdc backup upload <image-file> --to <machine> [--as <name>] [--datastore <name>]
                  [--from-repo <name>] [--bwlimit <rate>] [--up] [--skip-verify] [-o json]
```

- **Repo references** resolve through `resolveRepoRef` (packages/cli/src/utils/repo-target.ts:99). Without `@machine`, the repo's recorded placement names the machine.
- **`--all -m <machine>`** covers every config repo placed on that machine with no `parentGuid`, which means the grand repos. `--include-forks` adds the forks. Repos run one at a time, gently, never in parallel. A failure moves on to the next repo, and the exit code reports it.
- **`--to <dir>` must already exist and be writable.** The verb never creates it, so a run against an unplugged drive's mount point fails instead of filling the root filesystem. Under it, the verb creates `<dir>/<machine>/` with mode 0700.
- **Local layout:** `<dir>/<machine>/<name>.<tag>.img` (mode 0600), `<name>.<tag>.state.json` (0600) and `<name>.<tag>.lock` while a run is live. Resource names are `[a-z0-9-]` (packages/cli/src/utils/config-schema.ts:17-23), so the dots are unambiguous, and `:` never appears in a file name, which keeps the names legal on Windows.
- **Bandwidth.** `--bwlimit` parses with `bandwidthToBytesPerSecond` and reaches rsync as `--bwlimit=<KiB/s>`. Default is unlimited, matching the operator's 2026-10-29 ruling that `rdc backup snapshot` keeps an unlimited `--bwlimit` default (agent/plans/PLAN-snapshot-read-io-cap.md, second-round rulings); `--bwlimit 100Mbps` is the documented choice for hostinger (Open question 2).
- **Human output.** One progress line per repo, using the existing rsync progress parse (packages/cli/src/remote/sync/rsync.ts:325-340), then a summary row: repo, machine, image path, apparent and allocated size, literal bytes received, matched bytes, sha256 (first 12 characters), state.
- **`-o json` output.** One document: `{ results: [{ repo, tag, machine, guid, image, stateFile, status: complete|incomplete|failed, resumed, snapshotTakenAt, apparentBytes, allocatedBytes, literalBytes, matchedBytes, sha256, verify: "sha256+rsync"|"rsync", durationMs, error? }] }`. Progress goes to stderr only, so the JSON on stdout stays parseable.
- **Exit codes.** 0 when every repo is complete. 1 when any repo failed. 130 on Ctrl-C, after the session is closed and the state file is written.
- **Contract.** Both verbs join `PROXY_EXCLUSIONS` as client-side transfers and are MCP-excluded with the repo sync reason. Not being proxyable, they are never `detachable`, and `-b` is refused as it is for every non-detachable verb.

### 2. The session that holds the snapshot: `renet backup export`

A long-lived renet helper, chosen over a `--rsync-path` wrapper. A wrapper would tie the snapshot's life to one rsync process, so the sha256 step after rsync and the in-run retry could not reuse the snapshot. A wrapper would also have to rewrite rsync's server argv.

- **Invocation.** The client opens one exec channel on its pooled ssh2 connection (`sftpConfigForMachine`, packages/cli/src/services/machine/machine-connection.ts:113): `sudo -n <renet> backup export --name <guid> --datastore <path> [--checkpoint --network-id <n>] [--read-bwlimit <bytes/s>] --idle-timeout 90s`.
  - A new `SFTPClient.execSession` keeps stdin open and hands back a writer, a line reader for stdout and the exit promise. `execStreaming` stays as it is.
- **What the helper does, in order:**
  1. Validate the GUID and the datastore path.
  2. Refuse a directory repo, and refuse whatever `TransientReasonForOwner` names (private/renet/pkg/chunkstore/pipeline_linux.go:118).
  3. Take the shared lock `.lock-<guid>` with the same call as backup_push.
  4. Run the optional checkpoint.
  5. Create the snapshot with `snapshot.GenerateRepositorySnapshotName` and `ValidateSpace: true`.
  6. Thaw. SIGHUP, SIGINT and SIGTERM are deferred until the thaw has run, so no signal can leave a repo frozen.
  7. Print one ready line.
- **Ready line.** `{"event":"ready","snapshot":"<abs path>","guid":"…","takenAt":"<RFC3339>","apparentBytes":N,"allocatedBytes":N,"rsyncPath":"<getRsyncPath()>","lowPriority":["nice","-n","10","ionice","-c","2","-n","7"]}`.
  - `rsyncPath` comes from `getRsyncPath` (private/renet/cmd/renet/backup_pull.go:44), so the embedded rsync fallback works.
  - `lowPriority` lists only the tools present, by the same rule as private/renet/pkg/functions/commands/backup.go:766-781.
- **Stdin protocol, one word per line:**
  - `ping` keeps the session alive.
  - `sha256` hashes the snapshot and answers `{"event":"sha256","sha256":"<hex>","durationMs":N}`. Holes found by `SEEK_DATA`/`SEEK_HOLE` are hashed as in-memory zeros, so they cost no I/O. Data extents are read under `--read-bwlimit`, default 50,000,000 bytes/s, the gentle read default of agent/plans/PLAN-snapshot-read-io-cap.md. The pacing is a small local loop until that plan exports its limiter.
  - `quit` cleans up and answers `{"event":"closed"}`.
- **Cleanup.** Delete the snapshot and release the lock on any of: stdin EOF, `quit`, SIGHUP, SIGTERM, SIGINT, or no line for `--idle-timeout`.
  - The client pings every 20 s. A laptop that sleeps leaves a half-open TCP session that sshd may keep for hours, but the helper deletes the snapshot within 90 s anyway.
  - Only SIGKILL or a machine crash skips the cleanup. The flock dies with the process, so `rdc machine prune` reclaims the file under the existing rule (Design 8).
- **Rsync read.** The client runs the system `ssh` rsync with the source `<user>@<host>:<snapshot>` and `--rsync-path "sudo -n <lowPriority...> <rsyncPath>"`, using the temp key and known_hosts pattern of packages/cli/src/commands/repo-sync.ts:247-263. The snapshot path must match `^[A-Za-z0-9/._-]+$`; anything else is refused, so no quoting question arises.
- **Old renet.** A renet without `backup export` answers `unknown command`. The verb refuses with the upgrade instruction and never replaces renet itself: the download uses read-only access, as repo sync download does.
- **Machine jobs.** The client holds this session; it is not a machine job. agent/plans/PLAN-detached-jobs.md ruling 1 covers detachable verbs only, and these two are not detachable (Design 1). Detaching would be pointless anyway, because the bytes have to land on the client's disk. Its J0 verb audit lists them as client-side transfers outside `JOB_VERBS`.

### 3. The transfer, the resume and the verification

- **Download rsync argv** (`buildImageRsyncArgs`, packages/cli/src/remote/sync/image-rsync.ts, new): `--inplace --partial --no-whole-file --ignore-times --stats --progress --chmod=F600 --timeout=120 -e "<ssh> -o ServerAliveInterval=15 -o ServerAliveCountMax=4 …"`.
  - `--sparse` is added only when the local image does not exist.
  - Upload uses the same argv with `--no-owner --no-group --no-perms`, because the import helper sets the owner and mode.
  - Neither direction passes `-a`, `--times` or `--chown`.
- **Why `--ignore-times`.** It forces the delta algorithm on every run. A run never skips on matching size and mtime, so every run ends with rsync's whole-file checksum check of the reconstructed file. On a single large image the cost is nothing extra: the delta pass reads both files anyway.
- **Convergence against a partial or older local file.** This is the safety argument ruling 3 asked for.
  - rsync uses the destination only as a basis to match blocks against. The receiver rebuilds the file from the sender's stream: literal data plus references to basis blocks, each matched by a weak and a strong per-block checksum.
  - With `--inplace`, the sender refers only to basis blocks at or after the current write offset. Data it still needs has therefore not been overwritten yet.
  - The receiver truncates the file to the sender's length at the end.
  - The receiver checks a whole-file checksum over the rebuilt stream and re-sends the file on a mismatch.
  - The result is byte-identical to the new snapshot whatever the basis held: a prefix of an older snapshot, a complete older snapshot, or garbage. T1's convergence test proves it with the real rsync binary.
- **Why `--sparse` stays off for an existing file.** The hazard at private/renet/cmd/renet/backup_pull.go:62-71 belongs to the receiver's rsync version. For a download the receiver is the client's rsync, whose version is unknown, so the rule is absolute.
  - The cost: a block that became a hole on the machine is written locally as literal zeros. The local allocated size can drift up toward the apparent size over many weeks.
  - Preflight bounds that growth (Design 5). Re-sparsifying with `fallocate --dig-holes` is out of scope.
- **Final verification.** After rsync exits 0, the client sends `sha256` on the session and hashes the local file in parallel with Node's streaming `crypto.createHash('sha256')`.
  - Equal digests: the state becomes `complete`, with `verify: "sha256+rsync"` and the digest.
  - A mismatch: the state stays `incomplete` with `lastError: "sha256 mismatch"`, and the run fails. The next run's `--ignore-times` pass repairs it.
  - `--skip-verify` skips the sha256 step and records `verify: "rsync"`.
- **Retries within one invocation.** rsync exit 10, 12, 30, 35 or 255 is retried up to `--retries` times (default 3), with 10, 30 and 60 s backoff. The retry reuses the live session and its snapshot when that session still answers `ping`. Otherwise it closes the session and opens a new one with a fresh snapshot, which the convergence argument covers. Any other exit code fails the repo at once.
- **Resume on a later invocation.** No special case: the next run finds `incomplete`, reports "resuming", opens a new session and runs the same argv. Only the differences move.

### 4. The state file

Written by `writeImageState`: a temp file in the same directory, `fsync`, `rename`, then `fsync` of the directory. A crash therefore leaves either the old state or the new one.

```json
{
  "schema": 1,
  "kind": "rediacc-repo-image",
  "status": "incomplete",
  "image": "mail.latest.img",
  "config": "eu-remote",
  "machine": "hostinger",
  "repo": { "name": "mail", "tag": "latest", "guid": "<guid>", "grandGuid": "<guid or null>" },
  "run": {
    "startedAt": "<RFC3339>", "snapshotTakenAt": "<RFC3339>", "snapshotName": ".snapshot-…",
    "apparentBytes": 0, "allocatedBytes": 0, "checkpoint": false, "attempts": 1,
    "lastError": null
  },
  "complete": {
    "snapshotTakenAt": "<RFC3339>", "finishedAt": "<RFC3339>", "apparentBytes": 0,
    "sha256": "<hex>", "verify": "sha256+rsync", "literalBytes": 0, "matchedBytes": 0, "durationMs": 0
  },
  "upload": null,
  "history": [ { "startedAt": "…", "finishedAt": "…", "outcome": "complete|failed|interrupted", "literalBytes": 0 } ]
}
```

- **`status` is the single truth.**
  - The run writes `incomplete` with a fresh `run` block before rsync writes its first byte.
  - The run writes `complete` only after the verification.
  - `complete` holds the facts of the last finished run.
  - While `status` is `incomplete`, the `complete` block describes a copy that is no longer on disk, and the human output says so: "the local copy is not usable until a run completes" (ruling 2).
- **`history`** keeps the last 12 runs.
- **No secret enters the file.** No credential, no vault and no key: only identity, sizes and digests.
- **The local lock.** `<stem>.lock` is created with `O_EXCL` and holds `{ pid, host, startedAt }`. A lock from the same host whose pid is dead is taken over. A live one refuses the run, so two invocations never write the same image.

### 5. Disk-space preflight on the local target

The ready line carries the remote apparent size `A` and allocated size `U`.

- **Sparse probe** (`probeSparse(dir)`): truncate a 64 MiB probe file in the target directory, read `stat.blocks`, delete it. If `blocks * 512 < size`, the target keeps holes. On Windows `stat.blocks` is undefined, so the target is treated as non-sparse.
- **Need:**
  - Fresh image: `need = sparse ? U : A`.
  - Existing image, with local allocated size `L` (`blocks * 512`, or the file size when blocks are unknown): `need = max(0, min(sparse ? U : A, A - L))`.
  - Then add a margin of 1 % of `A`, at least 256 MiB.
  - The existing-image bound is safe: in-place writes over allocated blocks cost nothing, and new allocation happens only where the remote has data and the local file has a hole.
- **Free space** comes from Node's `fs.statfs(dir)`: `bavail * bsize`.
- **Refusal.** When `need > free`, the run refuses before rsync writes anything, naming need, free, apparent and allocated sizes. The session is closed, which deletes the snapshot.
- **FAT32.** On Linux, a filesystem type of FAT (statfs type 0x4d44) with `A > 4 GiB - 1` is refused by name. Elsewhere rsync's `EFBIG` error leaves the state `incomplete` with that error.
- **Local copy-on-write filesystems** (btrfs, ZFS and APFS, including Time Machine local snapshots) can need extra space for every overwritten block that a local snapshot still pins. The docs say so; preflight cannot see it.
- **`--skip-space-check`** skips the refusal and keeps the warning.

### 6. rsync availability on the client: Linux, macOS, Windows

- **`assertRsyncCapable`** runs `rsync --version` once per invocation. It refuses openrsync (its banner names it) and refuses any version below 3.1.3, the first that accepts `--sparse` with `--inplace`. The refusal carries a per-platform install hint.
- **Linux:** distribution rsync, 3.1.3 or newer on every supported release.
- **macOS:** Apple's `/usr/bin/rsync` is the old 2.6.9 line on older releases and openrsync on recent ones. Both are refused, and the hint names `brew install rsync`. Homebrew's rsync is found through `PATH`.
- **Windows:** rsync and ssh from bundled or system MSYS2 (packages/cli/src/remote/sync/rsync.ts:21-38), with local paths converted by `prepareRsyncPaths`. NTFS sparseness through MSYS2 is not relied on: the sparse probe decides and usually finds no sparse support, so preflight counts the full apparent size. Without MSYS2 the verb refuses and names the desktop app or an MSYS2 install. WSL users run the Linux CLI.

### 7. No SFTP fallback: refuse when rsync is missing

The verb refuses with the Design 6 hint and never falls back to SFTP. An offset copy over SFTP or an exec stream can resume only within one session, against the same snapshot. Every invocation takes a fresh snapshot (ruling 3), so resuming a byte offset on a later invocation would splice two snapshots into an image that decrypts to garbage. An offset copy also cannot update the weekly copy in place by delta; it would send the whole image every week. Getting both right means rebuilding rsync's block matching. Open question 1 offers a non-resumable full-copy fallback as an alternative.

### 8. Upload: `rdc backup upload` and `renet backup import`

1. **Local checks.**
   - The image's sibling state file must say `complete`; an `incomplete` copy is refused as not usable.
   - Unless `--skip-verify`, the local sha256 must match `complete.sha256`, so a copy that rotted on the drive is not sent.
   - `--from-repo <name>` replaces the state file's identity for an image whose state file is lost.
2. **Credential and identity.** The config repo whose `repositoryGuid` equals the state's `repo.guid` supplies the credential and the lineage (`grandGuid ?? repositoryGuid`). If no such repo exists, the upload refuses and names `--from-repo`.
3. **Target name.** `--as <name>`, defaulting to the state's `repo.name`. A name already in the config is refused with a hint to pass `--as`. The upload always mints a fresh GUID with `randomUUID()`, as `backup restore` and `repo fork` do.
4. **Pending record.** `upload: { machine, name, guid, datastore, startedAt, status: "staging" }` goes into the state file before any byte moves. A later `upload` with the same `--to` and `--as` resumes into the same GUID.
5. **Import session.** `sudo -n <renet> backup import --guid <new> --datastore <path> [--seed <state repo.guid>] --allocated-bytes <U> --idle-timeout 90s`, on the same `execSession`. The helper:
   - refuses when `repositories/<new>` exists;
   - takes the exclusive lock `.lock-<new>`;
   - uses the staging name `repositories/.restore-<new>`. That is the existing prune class, so a staging nobody resumes is reclaimable, and `TransientReasonForOwner` already makes every scheduled snapshot skip it;
   - creates the staging. If it exists, the helper resumes into it. If not, and the seed image `repositories/<seed>` exists on this datastore, it makes a reflink copy, so an upload back to the source machine sends only the delta. Otherwise it creates an empty file, after a space check of `U` against the datastore's free space;
   - prints `{"event":"ready","staging":"…","fresh":bool,"seeded":bool,"existingBytes":N,"rsyncPath":"…"}`.
6. **Transfer.** The client rsyncs the local image to `<user>@<host>:<staging>` with the Design 3 argv. It adds `--sparse` only when `fresh`, because the receiver here is the machine's rsync and 3.2.7 has the hazard.
7. **Finalize.** The client sends `finalize <sha256>`. The helper then:
   - hashes the staging under the read cap and compares the digest;
   - runs `verifyRepositoryIntegrity` (private/renet/cmd/renet/backup_pull.go:608);
   - sets the owner and mode that `repository create` gives a new image (R1 reads the value from the create path and records it under "Live records");
   - `rename`s the staging to `repositories/<new>` in the same directory, which is atomic;
   - answers `{"event":"finalized","path":"…"}`.
   On a mismatch or a header failure, the helper keeps the staging, answers an error, and the client reports it. `discard` deletes the staging. EOF without `finalize` keeps the staging for a resume and releases the lock.
8. **Registration, after a successful finalize only.**
   - `addRepository(compositeKey(name, 'latest'), { ...restoredIdentity(lineage), tag: 'latest', credential, networkId, placement })`, with the network id and placement allocated exactly as packages/cli/src/commands/backup.ts:189-205 does.
   - Then `warnIfConfigStorageUnenrolled`, `reconcileBackupSchedules(machine)`, and with `--up`, `postPushDeploy` (packages/cli/src/commands/repo-backup.ts:171).
   - The state's `upload.status` becomes `finalized`.
   - If registration fails after the finalize, the output names the GUID and the machine and gives `rdc machine prune <m> --orphaned-repos --dry-run` as the way to find the unregistered image.

### 9. Prune coverage and machine status visibility

Every artifact class the two verbs create, and what reclaims it:

| Artifact | Created by | Held by | Reclaimed when the session dies by |
| --- | --- | --- | --- |
| `repositories/.snapshot-<guid>-…` | export | shared `.lock-<guid>` | the helper's cleanup; after SIGKILL, prune's existing rule (private/renet/pkg/prune/datastore.go:652-659) |
| `repositories/.lock-<guid>` of an existing repo | export | the same | never stale while `<guid>` exists (correct) |
| `repositories/.restore-<new>` | import | exclusive `.lock-<new>` | kept on purpose for a resume; prune's existing rule (:662-669) reclaims it when no upload holds the lock |
| `repositories/.lock-<new>` before the image exists | import | the same | **defect today**: prune unlinks it while held (:640-650, :757-767). R2 adds the probe |
| local `.img`, `.state.json`, `.lock` | client | client | the operator's disk; a dead lock is taken over (Design 4) |

R2's changes:

- **Stale-lock rule.** A `.lock-<guid>` with no image is listed only when `repoLockHeld` says it is not held. This closes finding 2 for the upload and for `backup restore` alike.
- **Pull staging.** A hidden `repositories/.<guid>` entry, the pull staging (finding 3), is listed as `StalePullStaging` when its lock is not held, and removed with a re-probe like `pruneStaleSnapshots` (:837). The CLI preview parser gains a `pull-staging` row (packages/cli/src/commands/datastore-prune-parser.ts:84-95).
- **Machine status.** `scanPool` stops scanning the dead `.backup-*` class. It counts `repositories/.snapshot-*` and `repositories/.restore-*` instead, splits them into active (lock held) and stale (not held) with exported wrappers of `isSnapshotInUse` and `isRestoreStagingInUse`, and prices them with the existing batched `btrfs fi du` on the files.
  - The JSON fields are renamed, as a clean break: `active_transfer_snapshots`, `stale_transfer_snapshots`, `transfer_pinned_bytes`, `transfer_pinned_human`.
  - `renderPoolSummary` keeps its i18n key and parameter names `{pinned, active, stale}`, so R2 changes no locale file. C1 rewords the en string to "Transfer snapshots and staging pin …".
  - With this fix, the snapshot left by a week-old interrupted download, or a forgotten upload staging, shows up in `machine status`. The output says that `rdc machine prune` removes it.
- **No age rule is added.** Ruling 3 rejected a lease. A held lock means a live process, and a dead process holds no lock, so age adds nothing.

### 10. Related plans: boundaries kept

- **agent/plans/PLAN-detached-jobs.md:** the two verbs are client-side transfers, outside `JOB_VERBS`, not proxyable and not detachable (Design 2). The only file shared with it is backup.ts (one register call), and generate-cli-contract.ts and command-metadata.ts (two entries each).
- **agent/plans/PLAN-snapshot-read-io-cap.md:**
  - The machine-side read of the delta pass is rsync's own sender, which no in-process token bucket can pace. It runs under the same `nice`/`ionice` prefix that plan keeps, and the network side under `--bwlimit`.
  - The helper's sha256 read uses that plan's 50,000,000 bytes/s default.
  - The residual exposure is named under Risks.
- **agent/plans/PLAN-backup-program.md:** that plan owns the backup docs pages backup-restore.md and pruning.md, so this plan adds a new page, backup-download.md, and only links to them.
- **agent/plans/PLAN-backup-restore-path.md:** that plan shares backup.ts and private/renet/cmd/renet/backup.go, one line each. No behaviour overlaps: path restore reads the chunk store, and this plan reads the live image.

## Tasks

- [ ] P0 [lead] Plan lint. Run the two gates on this file.
  Owns: agent/plans/PLAN-backup-local-image.md. Accept: `python3 .ci/scripts/quality/check_plan_citations.py` rc 0 and `python3 .ci/scripts/quality/check_plan_deps.py` rc 0.

- [x] R1 [writer] renet `backup export` and `backup import` (Design 2, 8).
  - Both are new cobra commands in their own files, registered in private/renet/cmd/renet/backup.go.
  - Both share a session core: the stdin line reader, the idle timer and the signal handling with the deferred-until-thaw rule.
  - export: lock, checkpoint, snapshot, ready line, `sha256` with hole skipping and the read cap, cleanup on every exit path.
  - import: exclusive lock, staging create, resume or seed, space check, `finalize` (hash, `verifyRepositoryIntegrity`, owner and mode, rename), `discard`.
  - Help strings use `i18n.T` keys only if the renet extract baseline test demands them, which brings the locale files into this box.
    (ticked) 2026-10-29T12:43:48Z by d778be9d: commit:12717d20a

  Tests:
  - export against a temp datastore with a fake snapshotter seam prints one parseable ready line and leaves no `.snapshot-*` after each of EOF, `quit`, SIGHUP and a 1-second idle timeout;
  - a SIGHUP during the fake checkpoint runs the thaw before the exit;
  - `sha256` over a sparse fixture equals `sha256sum` of the same file and reads no hole bytes (a counting reader seam);
  - a `.restore-<guid>` present makes export refuse with the transient reason;
  - import resumes an existing staging (`fresh: false`), seeds from an existing image, refuses an existing target, and on a wrong digest keeps the staging and leaves no target;
  - finalize renames, and the target passes the LUKS check (a `cryptsetup` seam);
  - control: without the cleanup defer, the EOF case leaves the snapshot and the test reds.

  Owns: private/renet/cmd/renet/backup_export.go (new), private/renet/cmd/renet/backup_export_test.go (new), private/renet/cmd/renet/backup_import.go (new), private/renet/cmd/renet/backup_import_test.go (new), private/renet/cmd/renet/backup.go (two AddCommand lines only), private/renet/pkg/i18n/locales/*.go (two help keys only), private/renet/pkg/i18n/locales/hashes.json (two help keys only). Accept: `cd private/renet && go test ./cmd/renet/ -run 'TestBackupExport|TestBackupImport' -count=1` rc 0, `cd private/renet && go vet ./cmd/renet/` rc 0, and `cd private/renet && go test ./pkg/i18n/` rc 0.

- [ ] R2 [writer] Prune and pool visibility (Design 9).
  - The stale-lock probe and the `StalePullStaging` class in prune.
  - `scanPool` counts `.snapshot-*` and `.restore-*` with the active and stale split and the pinned bytes, under the renamed fields in private/renet/pkg/list/types.go.
  - The CLI side: `renderPoolSummary` reads the renamed fields with the same i18n parameters, and the prune parser gains `pull-staging`.
  - The lead regenerates packages/shared/src/renet-contract/data/list-types.generated.ts with the command its header names (`./build.sh deploy prep`) after the writer's edit.

  Tests:
  - a held `.lock-<guid>` with no image is NOT listed and an unheld one is;
  - an unheld `.<guid>` is listed as pull staging and a held one is not;
  - `scanPool` over a temp datastore with one held and one unheld snapshot and one unheld staging reports active 1 and stale 2;
  - a `.backup-*` directory is no longer counted;
  - the CLI renders the snapshot line from the new fields and omits it at zero;
  - the parser emits a `pull-staging` row;
  - control: removing the lock probe makes the held-lock test red.

  Owns: private/renet/pkg/prune/datastore.go, private/renet/pkg/prune/identifiers.go, private/renet/pkg/prune/datastore_transfer_test.go (new), private/renet/pkg/list/storage_health.go, private/renet/pkg/list/types.go, private/renet/pkg/list/storage_health_transfer_test.go (new), private/renet (gitlink bump only), packages/shared/src/renet-contract/data/list-types.generated.ts (regenerated only), packages/cli/src/commands/machine/status.ts (renderPoolSummary only), packages/cli/src/commands/datastore-prune-parser.ts, packages/cli/src/commands/__tests__/machine-status-pool.test.ts (new), packages/cli/src/commands/__tests__/datastore-prune-pull-staging.test.ts (new). Accept: `cd private/renet && go test ./pkg/prune/ ./pkg/list/ -count=1` rc 0, and `cd packages/cli && npx vitest run src/commands/__tests__/machine-status-pool.test.ts src/commands/__tests__/datastore-prune-pull-staging.test.ts` rc 0.

- [ ] X1 [writer] rsync.ts sibling (finding 1).
  - Export `getRsyncSSHCommand`.
  - Add `getRsyncVersionText()`, which runs `rsync --version` once and caches the result.
  - Add a comment at the `--verify` branch stating that `--inplace` implies `--partial`.
  - No behaviour change to repo sync.

  Tests: every real-run argv from `buildRsyncArgs`, with and without `verify`, contains `--inplace`, and a dry run contains neither `--inplace` nor `--partial`. Control: a planted `verify` branch that also drops `--inplace` reds the test.

  Owns: packages/cli/src/remote/sync/rsync.ts, packages/cli/src/remote/sync/__tests__/rsync-inplace-partial.test.ts (new). Accept: `cd packages/cli && npx vitest run src/remote/sync/__tests__/rsync-inplace-partial.test.ts` rc 0.

- [ ] S1 [writer] State file and preflight (Design 4, 5). Both are pure modules with no i18n; C1 renders their results.
  - state.ts: `localImagePaths(dir, machine, name, tag)`, `readImageState`, `writeImageState` (atomic), `beginRun`, `completeRun`, `failRun`, `recordUpload`, `acquireLocalLock` and `releaseLocalLock`.
  - preflight.ts: `probeSparse(dir)`, `computeSpaceNeed({ apparent, allocated, localExists, localAllocated, sparse })`, `checkSpace(...)` returning `{ ok, need, free, reason? }`, and the FAT32 rule.

  Tests:
  - a write interrupted between the temp write and the rename leaves the previous state readable;
  - the file is 0600 and its directory 0700;
  - a planted credential field passed in is dropped, never written;
  - a dead-pid lock on the same host is taken over and a live one refuses;
  - `computeSpaceNeed` matches the Design 5 table for fresh sparse, fresh non-sparse, existing partial and existing complete;
  - FAT with an apparent size of 5 GiB refuses;
  - control: `history` caps at 12.

  Owns: packages/cli/src/services/backup-image/state.ts (new), packages/cli/src/services/backup-image/preflight.ts (new), packages/cli/src/services/backup-image/__tests__/state.test.ts (new), packages/cli/src/services/backup-image/__tests__/preflight.test.ts (new). Accept: `cd packages/cli && npx vitest run src/services/backup-image/__tests__/state.test.ts src/services/backup-image/__tests__/preflight.test.ts` rc 0.

- [ ] T1 [writer] Tests that fail without the change, written before C1 against the module API named in Design 2, 3 and 8.
  - **converge.test.ts** runs the real local `rsync` with the C1 argv between two local paths (`--no-whole-file` forces the delta path). A missing rsync binary fails the test; it does not skip. Cases:
    - a 64 MiB fixture with holes and random data, against a 40 % prefix of an older version;
    - a complete older version with scattered changed blocks;
    - a shrunk source;
    - a grown source.
    The sha256 must match in every case, and `--stats` literal bytes for the scattered case must stay under 10 % of the size.
  - **image-rsync.test.ts:** `--sparse` appears only when `freshDest`, `--ignore-times` always, never `-a` or `--times`; `assertRsyncCapable` refuses an openrsync banner and `rsync version 2.6.9` and accepts 3.2.7.
  - **backup-image-download.test.ts**, against a recording session fake and a fake rsync runner:
    - the state is `incomplete` before the first rsync call and `complete` only after an equal sha256;
    - a sha256 mismatch leaves `incomplete`;
    - rsync exit 12 retries on the live session, and a dead session reopens it;
    - Ctrl-C sends `quit` and exits 130;
    - a missing rsync refuses with no SFTP call;
    - a missing `--to` directory refuses without creating it;
    - `-o json` prints one parseable document.
  - **backup-image-upload.test.ts:**
    - an `incomplete` state refuses;
    - a missing credential repo refuses and names `--from-repo`;
    - registration happens only after `finalized`;
    - a resume reuses the pending GUID;
    - `--sparse` is sent only when `fresh`.
  - Control: each file is red on the tree before C1, recorded under "Live records".

  Owns: packages/cli/src/services/backup-image/__tests__/converge.test.ts (new), packages/cli/src/remote/sync/__tests__/image-rsync.test.ts (new), packages/cli/src/commands/__tests__/backup-image-download.test.ts (new), packages/cli/src/commands/__tests__/backup-image-upload.test.ts (new). Accept: `cd packages/cli && npx vitest run src/services/backup-image/__tests__/converge.test.ts src/remote/sync/__tests__/image-rsync.test.ts src/commands/__tests__/backup-image-download.test.ts src/commands/__tests__/backup-image-upload.test.ts` rc 1 recorded before C1 and rc 0 after C1.

- [ ] C1 [writer] CLI verbs. Follows R1, X1, S1 and T1.
  - `rdc backup download` and `rdc backup upload` in packages/cli/src/commands/backup-image.ts (new), registered from `registerBackupCommands` (packages/cli/src/commands/backup.ts:654-665).
  - `SFTPClient.execSession`.
  - The session client (session.ts) and the transfer loop with retries and verification (transfer.ts).
  - `buildImageRsyncArgs`, `parseRsyncStats` and `assertRsyncCapable` in image-rsync.ts.
  - The two `PROXY_EXCLUSIONS` entries, the two `mcpExcludeReason` entries and the two `CMD` entries.
  - `restoredIdentity` exported.
  - The en keys for every new string, plus the reworded `storageHealthPoolSnapshots` (packages/cli/src/i18n/locales/en/cli.json:905).
  - The lead regenerates the contract with `npm run generate:cli-contract -w @rediacc/cli` after the writer's edit.

  Owns: packages/cli/src/commands/backup-image.ts (new), packages/cli/src/services/backup-image/session.ts (new), packages/cli/src/services/backup-image/transfer.ts (new), packages/cli/src/remote/sync/image-rsync.ts (new), packages/cli/src/remote/sftp/client.ts (one execSession method only), packages/cli/src/commands/backup.ts (one register call and the restoredIdentity export only), packages/cli/scripts/generate-cli-contract.ts (two PROXY_EXCLUSIONS entries only), packages/cli/src/config/command-metadata.ts (two mcpExcludeReason entries only), packages/cli/src/utils/command-policy.ts (two CMD entries only), packages/shared/src/cli-contract/data/contract.generated.ts (regenerated only), packages/cli/src/i18n/locales/en/cli.json. Accept: the T1 command above rc 0, `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0, and `npm run check:ci-i18n-cli-key-usage` rc 0.

- [ ] I1 [writer] i18n in the 12 derived CLI locales. Follows C1. The new en keys and the reworded pool line are naturalized per docs/i18n/CONVENTIONS.md.
  Owns: packages/cli/src/i18n/locales/*/cli.json (non-en). Accept: `npm run check:i18n` rc 0.

- [ ] D1 [writer] Docs. Follows C1.
  - A new page, backup-download.md, in English first, then translated into the 12 other languages. It covers:
    - what the copy is (the encrypted image, with the credential kept in the config, which links to config storage enrollment);
    - the weekly in-place update and its one-copy space rule;
    - what `incomplete` means;
    - resume;
    - the per-platform rsync requirement;
    - external drive caveats (FAT32, exFAT without sparse support, local CoW snapshots);
    - upload, and finding stale snapshots with `machine status` and `machine prune`.
  - The lead regenerates cli-application.md with `npm run generate:cli-docs -w @rediacc/www`.
  Owns: packages/www/src/content/docs/*/backup-download.md (new), packages/www/src/content/docs/*/cli-application.md (regenerated only). Accept: `npm run check:i18n` rc 0.

- [ ] V1 [lead] The VM proof for the renet change. `npm run vm:check -- --changed` must report VERIFIED on the tree carrying R1 and R2, as the push guard requires for the renet trigger paths.
  Owns: agent/plans/PLAN-backup-local-image.md. Accept: `npm run vm:check -- --changed` rc 0 with a VERIFIED receipt.

- [ ] L1 [live] An ops VM or bench machine running the branch renet, with one small repo `app` (a LUKS image of at least 2 GiB, a running container) and a local target `/tmp/bdl`. Steps:
  1. `./rdc.sh backup download app@<vm> --to /tmp/bdl`, interrupted with `timeout -s INT 20`. Expect rc 130, state `incomplete`, and no `.snapshot-*` under `repositories/` within 90 s.
  2. Run again. Expect rc 0, state `complete`, and the local sha256 equal to the state's digest. After `repo down app`, a fresh `sudo sha256sum repositories/<guid>` on the machine equals both.
  3. `repo up app`; write 50 MiB inside the repo; run download again. Expect rc 0, `literalBytes` under 10 % of `apparentBytes`, and the sha256 compare passing.
  4. Start a download, then on the machine run `sudo pkill -9 -f 'renet backup export'`. Expect `machine status` to show 1 stale transfer snapshot, `machine prune <vm> --dry-run` to list it, and `machine prune <vm>` to remove it.
  5. Run `rdc machine prune <vm>` while an upload holds `.lock-<new>`. Expect the lock to survive and the upload to finish.
  6. `./rdc.sh backup upload /tmp/bdl/<vm>/app.latest.img --to <vm> --as app-copy --up`. Expect rc 0, a new GUID in the config, and `machine status` showing app-copy's containers running.
  7. Kill the client with `kill -9` during a second upload to another name, then rerun. Expect it to resume into the same GUID.

  Owns: agent/plans/PLAN-backup-local-image.md. Accept: each step's command, rc, timing, `literalBytes` and both sha256 values recorded under "Live records"; step 1 rc 130, every other step rc 0.

- [ ] L2 [live] hostinger, after L1 and with the branch renet provisioned. ASK the operator first: provisioning a branch renet restarts the router and daemons. Steps:
  1. `./rdc.sh backup download mail@hostinger --to /tmp/rdc-bdl --config eu-remote`. Expect rc 0, state `complete`, and the sha256 compare passing.
  2. The same command again. Expect rc 0 and `literalBytes` recorded.
  3. Before, during and after the run: the load and iowait sampler of agent/plans/PLAN-snapshot-read-io-cap.md, and `machine status` showing 0 transfer snapshots after each run.
  No upload runs on production.
  Owns: agent/plans/PLAN-backup-local-image.md. Accept: both runs rc 0, with timings, sizes, `literalBytes`, both digests and the load peak recorded under "Live records".

- [ ] LP-bench [live] Fresh bench receipt (PLAN-tested-on-bench ruling 3): deploy this branch to bench with deploy_bench, then record and tick through worklist.py --live-proof.
  - Accept: `live-proof bench account-smoke`
- [ ] LP-hostinger [live] Fresh hostinger receipt through --config eu-bench (PLAN-tested-on-bench ruling 3), after a VERIFIED npm run vm:check -- --changed on the same tree. ASK the operator first, because provisioning a branch renet restarts the router and daemons.
  - Accept: `live-proof hostinger renet-live`

## Open questions for the operator

1. **No fallback when rsync is missing.** DEFAULT: refuse with the per-platform install hint (Design 7). The alternative is a non-resumable full copy over an exec stream: it restarts from byte 0 after any interruption, sends the whole image every week, and still writes in place and verifies by sha256.
2. **The default `--bwlimit`.** DEFAULT: unlimited, consistent with the 2026-10-29 ruling on `rdc backup snapshot`; `--bwlimit 100Mbps` is documented for hostinger. The alternative is a `100Mbps` default. A 100 GiB first copy at 100 Mbps takes about 2.4 hours.
3. **What `--all` covers.** DEFAULT: grand repos only, with forks behind `--include-forks`, because each fork is a second full image on a drive with little space. The alternative is every repo on the machine.

## Risks

1. **The machine-side read of a weekly delta is not rate-capped.** rsync's sender reads the whole allocated snapshot to find matches, while `--bwlimit` caps only the bytes that cross the network. The read runs under `nice`/`ionice`, which does nothing under `mq-deadline` or `none` (agent/plans/PLAN-snapshot-read-io-cap.md). L2 measures load and iowait on hostinger. If the peak breaks that plan's ceiling, a follow-up serves the snapshot through a paced reader.
2. **The snapshot pins changed blocks on the machine for the life of the session.** A multi-hour download of a busy repo holds as many diverged blocks as the repo writes meanwhile. `ValidateSpace` guards the start; the status fix (Design 9) makes the pinned size visible.
3. **The shared lock held for a whole download blocks exclusive operations on that repo.** Those are `repo pull` into it, `backup restore` onto it and takeover, and each fails fast as busy. backup_push already holds the lock the same way for its whole transfer.
4. **The local copy is not usable between an interruption and the next complete run** (ruling 2). The state file, the human output and the docs say so. One copy of space cannot avoid this.
5. **Local allocated size drifts up over many weekly runs**, because `--sparse` is never passed over an existing file (Design 3). Preflight bounds the growth; re-sparsifying is out of scope.
6. **Platform reach.** macOS needs Homebrew rsync, and Windows needs MSYS2 or the desktop app. Neither platform gets a live proof here; T1 covers the version gate and the argv.
7. **Overlapping owners.** backup.ts, generate-cli-contract.ts, command-metadata.ts, command-policy.ts, sftp/client.ts, rsync.ts and renet's backup.go are held by other live plans (Concurrency line). Each edit here is one or two lines; a refused spawn waits in the queue.

## Out of scope

- The source-side snapshot of `repo pull`, which holds no lock on the source and can be deleted by a prune there mid-pull (finding 4). It is filed as its own worklist item.
- Directory-based repos (`<guid>.dir`).
- Chunk-level or point-in-time selection: this is a full copy of the current image (operator: "chunks are not needed").
- Re-sparsifying the local copy (`fallocate --dig-holes`), local retention of several generations, and encrypting or signing the state file.
- A proxy, MCP or web-console path for either verb.
- Any change to repo sync's SFTP fallback or to `repo push`/`repo pull`.
- Scheduling a weekly run from the CLI. Cron or launchd on the operator's own machine runs the verb as it stands.

## Live records

(empty until T1 records its red run)

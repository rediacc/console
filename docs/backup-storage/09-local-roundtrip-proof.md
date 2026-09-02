# 09. The local round trip: a machine really did restore from a real store

Run 2026-08-15 against the local fleet and a local S3. This document records
what was PROVEN by running it, and the three defects the run found.

Read `07-execution-record.md` first; this file only adds what the machine-level
run settled. Where it contradicts an earlier document, this one was measured.

---

## 1. Verdict

**The hot round trip PASSED, byte for byte. The `--cold` round trip FAILED, and
the failure is structural rather than environmental.**

| Step | Result |
|---|---|
| new repo on a worker, known content | PASS |
| snapshot to a real S3 endpoint | PASS, 893 chunks / 58,523,648 B |
| manifest index shows it | PASS |
| quota ledger increments by exactly the uploaded bytes | PASS |
| restore AS A DIFFERENT REPO, byte-compared | PASS, `cmp` identical |
| incremental snapshot then restore (chain depth 3) | PASS, `cmp` identical |
| `--cold` produces a record with `coldSteps` | **FAIL, see §4.1** |

This closes the gap 07 §1 named: *"no MACHINE has ever restored from a real
bucket, because no bucket exists."* A bucket exists now, locally, and a machine
restored from it. It does NOT close the R2 question: RustFS is not R2, and
`If-None-Match` and lifecycle behaviour stay tier B/C exactly as 07 §6 says.

## 2. What had to be stood up, and why none of it existed

The briefing said a gateway served `rediacc-backups-probe` at
`http://192.168.111.254:4800`. It did not: nothing was listening on 4800, and
`curl` refused the connection. 4800 is the ACCOUNT DEV GATEWAY port
(`.ci/config/constants.sh:59`), not an S3 endpoint, so the two halves had to be
built separately. `programs/backup-storage/start-local-plane.sh` does both:

- the probe bucket on the RustFS `./run.sh account dev` already runs on :9100;
- the account dev gateway on :4800 with `ACCOUNT_BACKUP_S3_*` set, which is what makes
  `createBackupPlane` select the S3 presign minter (the minter the operator
  chose for production, 07 §2.1). It logged
  `Backup chunk storage: http://192.168.111.254:9100/rediacc-backups-probe`.

`rediacc-backups-probe`, never `rediacc-backups`. The local RustFS happens to
carry a bucket literally named `rediacc-backups` from an earlier drill run; the
launcher refuses that name outright rather than trusting the caller.

**The host header names the universe.** `renewalUrlFor`
(`private/account/src/routes/license.ts:36`) derives the licence's renewalUrl
from `envConfig.baseUrl`, which is `PUBLIC_SITE_URL ?? url.host`
(`app.ts:534`), and renet derives the backup SESSION url from that renewalUrl by
suffix swap (`cmd/renet/backup_snapshot.go:540`). Issue a licence over
`localhost:4800` and the machine gets a session address it cannot dial. So every
account call goes to `192.168.111.254:4800`. The same applies to
`ACCOUNT_BACKUP_S3_ENDPOINT`: SigV4 covers the Host header, so a presigned URL is only
usable if the endpoint is spelled exactly as the VM will dial it.

## 3. The evidence

Snapshot, from the worker, stdout captured separately from stderr:

```
{"guid":"a15f7952-...","status":"stored","snapshotId":"20260815T162522Z-0459345d794a88e2",
 "lineage":"a15f7952-...","cellBytes":65536,"imageBytes":268435456,
 "rehashReason":"no journal: first backup of this repo here",
 "chunksAsked":893,"chunksMissing":893,"chunksUploaded":893,
 "bytesUploaded":58523648,"grantsMinted":1,"durationMs":5523}
```

The objects landed at the documented key shape, which is the thing 07 §3 defect
4 got wrong once and would silently get wrong again:

```
t/5ef35df6-.../l/a15f7952-.../c/006a6a63cead71b7...   (893 of these)
t/5ef35df6-.../l/a15f7952-.../m/20260815T162522Z-0459345d794a88e2
```

`GET /backups/usage` then answered `storedBytes: 58523648`, `chunkCount: 893` —
equal to `bytesUploaded` to the byte, so the ledger defect (07 §3 defect 2) is
genuinely gone on a real path rather than only in a fake.

The comparison, which is the only step that proves anything:

```
source   /mnt/rediacc/repositories/a15f7952-...  f777b0bb1aa2c061...  268435456 B
restored /mnt/rediacc/repositories/247e0ecd-...  f777b0bb1aa2c061...  268435456 B
cmp: IDENTICAL
```

**The instrument was proved, twice.** A comparison that cannot fail is not
evidence. Comparing the source against a restore of an EARLIER snapshot reported
`differ: byte 16778241`, and the harness plants a single byte into the restored
image and requires the same `cmp` to notice. Both fired.

Incremental, separately: a second snapshot moved 2 cells of 933
(`chunksMissing: 2`, 131,072 B), and restoring it into a THIRD repo reported
`chainDepth: 3` and again compared identical. So the delta chain composes on
the way back, not just on the way out.

Mounted-content check: the restored image opened with the SOURCE repository's
LUKS passphrase, and `marker.txt`, `nested/dir/deep.txt` and the 8 MiB
`payload.bin` all matched their source digests. The files that differ are the
ones `repository mount` itself rewrites (`.envrc`, `.rediacc.json`,
`daemon.json`, `containerd.toml`, `engine-id`, the buildkit dbs) because the two
repos mount on different network ids — written after the restore, by the mount,
not by the restore.

## 4. Three defects the run found

### 4.1 `renet backup snapshot --cold` can never store a snapshot

**It refuses every repository it selects, by construction.** Three live runs,
three refusals:

```
{"guid":"a15f7952-...","status":"failed","cold":true,
 "reason":"quiesce did not take: containers are still running after the stop
           (a repository with no Rediaccfile is skipped by DownServices, which
           reports success). Refusing rather than shipping a hot snapshot
           labelled cold."}
Cold backup: 1 repositories quiesced, outage 400ms
  (cold_down=132ms cold_sync=37ms cold_verify=88ms cold_stage=0ms cold_up=140ms)
```

`cold_stage=0ms` in every run is the signature: nothing is ever staged.

The chain, all four links verified against the tree:

1. `discoverRunningRepos` (`cmd/renet/backup_sync_cold.go:37`) defines "running"
   as the DOCKER DAEMON being up — `daemon.GetRunningNetworks()`, which is
   `IsServiceActive(nid) || isDaemonSocketResponding(nid)`
   (`pkg/daemon/discovery.go:50`). It is not about containers.
2. `runColdBarrier` selects exactly the repos for which that predicate is TRUE
   (`cmd/renet/backup_snapshot_cold.go:110`).
3. The stop phase calls `DownServices` with `Unmount: false`
   (`backup_sync_cold.go:157`), and the only code in `DownServices` that stops
   the daemon sits behind `if opts.Unmount`
   (`pkg/orchestration/up_down_workflows.go:385`). The stop therefore CANNOT
   make the predicate false. Keeping LUKS mounted is deliberate and correct; the
   consequence for the predicate was not noticed.
4. The verify re-runs THE SAME predicate (`backup_snapshot_cold.go:207`) and
   fails every repo still matching it (`:213`).

So the barrier refuses precisely the set it selected. The function comment at
`backup_sync_cold.go:167` ("Runs Rediaccfile down() and stops Docker") describes
behaviour the code does not have.

**The refusal message misdirects, which is why this could sit unnoticed.** It
blames a missing Rediaccfile. That explanation was tested and is wrong: with a
real Rediaccfile whose `down()` ran to completion (`Found 1 Rediaccfile(s)`,
`Phase: down`, `✓ root down completed`), the run refused with the identical
message, and `systemctl is-active rediacc-docker-2880.service` answered `active`
after the barrier. A reader following the message adds a Rediaccfile and gets
the same failure with the same text.

The rest of the cold path is FINE, which localises the fix. With the daemon
genuinely stopped the barrier no-ops ("0 repositories quiesced, outage 0ms") and
the snapshot STORES, carrying `"cold": true` and a correct incremental (91 of
933 chunks, 5,963,776 B). Only the verify predicate is wrong.

This is the same shape as the defects in 07 §3: the verify was added on
2026-08-15 to catch a real hot-snapshot-labelled-cold bug, and its unit tests
pass because they seam `discoverRunningReposFn` and therefore never observe that
the real one cannot change between the two calls.

**Consequence for the deliverable:** a record carrying `cold: true` AND a
`coldSteps` breakdown is unreachable today. When the barrier runs, the record is
built by the refusal branch (`backup_snapshot.go:305`) as
`{GUID, Status, Reason, Cold: true}` — it drops `ColdWindowMs` and `ColdSteps`,
so an outage that really was paid (400 ms, measured) leaves no machine-readable
trace; the breakdown exists only on stderr. When the barrier no-ops, the record
stores with `cold: true` but the outage is genuinely 0 and `coldSteps` is empty.

This also means 07 §9.7's "cold mode has no chunk-store path" was too kind: the
verb grew a `--cold` flag, and the flag cannot succeed.

### 4.2 Restore reaches for a stranger's licence

First restore attempt, with everything else correct:

```
{"status":"failed","licenseFrom":"0682df0c-...",
 "reason":"restore failed: read grant mint: server refused
           (HTTP 404, BACKUP_MANIFEST_MISSING): No committed manifest for
           snapshot 20260815T162522Z-0459345d794a88e2 in this subscription"}
```

`resolveRestoreLicense` (`cmd/renet/backup_restore.go:360`) is right that the
target repo cannot have its own licence in general — its image does not exist
yet — so it falls back to any installed licence, as both credential and address
book. But the fallback loop returns the FIRST scope with a non-empty
`RenewalURL`, with no preference for a licence whose `grandGuid` matches the
`--lineage` being restored. This machine held licences from an earlier session,
and `0682df0c` belongs to subscription `1b06d44e`, not to the `5ef35df6` that
owns the snapshot. Meanwhile the source repo's OWN licence, matching the lineage
exactly, was installed and `valid` on the same machine.

The error then names the manifest, which is intact, instead of the credential,
which was wrong. On a machine that has ever served two subscriptions — a
migration, a re-provision, a second test account — restore fails with a message
pointing at the wrong thing.

Preferring a licence whose `grandGuid == lineage` before falling back to any
would fix it, and the information is already decoded in the same loop.

### 4.3 `repository delete` leaks its systemd units

After deleting the test repos, `/etc/systemd/system/` still held
`rediacc-docker-2880.{service,socket}` and `rediacc-docker-2944.{service,socket}`
in state `failed`. Not a one-off: the same VM already carried orphaned
`rediacc-docker-4096.*` and `rediacc-docker-4160.*` from an earlier session,
while the live repo on network 2816 has no units at all. Left alone these
accumulate one failed unit pair per deleted repo, and they degrade
`systemctl --failed` into noise on any long-lived machine.

## 5. How to re-run it

```bash
programs/backup-storage/start-local-plane.sh        # bucket + gateway on :4800
programs/backup-storage/local-roundtrip.sh          # the proof, exit 0 = passed
```

The harness creates its own account, subscription, token, repo and licences,
byte-compares, runs the mutation control, and deletes everything it made. It was
run green end to end before being committed, 9 checks, exit 0 — the ordering 07
§8 argues for, since wiring a proof nobody has watched pass makes a red run
indistinguishable from a broken script.

It deliberately does not use `./rdc.sh`: rdc redeploys renet to whatever machine
it touches, and the point is to test the binary you chose. The cost is that the
harness has to issue repo licences itself, over `POST /licenses/activate-repo`.

**`.ci/scripts/private/license-mint` cannot substitute for the server here.** It
never sets `grandGuid` — the string does not occur anywhere in the tool, and the
field is absent from the `license.RepoLicense` literal it marshals
(`main.go:212`) — and `snapshotOneRepo` refuses a licence
without one, because the lineage IS the object-key prefix. Any future offline
backup fixture needs that flag added first.

## 5.1 Which binary was under test

`./build.sh dev` produced `bin/renet-linux-amd64` at sha256 `4096f37e2d55a0d1…`,
and `/usr/bin/renet` on the worker already carried **the same 64 hex digits**.
Nothing was deployed and the fleet's binary was never touched; the build simply
reproduced what was installed.

That matters for reading these results, because `cmd/renet/backup_snapshot.go`
and `backup_snapshot_cold.go` were both edited by another session WHILE this ran
(mtimes two and four minutes after the build). The cold verify block and the
refusal-record construction were re-read afterwards and are unchanged in
substance, so §4.1 still describes the tree; but line numbers in this document
were re-verified at write time and will drift again.

## 6. What this still does not prove

- Nothing about R2. RustFS accepted our SigV4 and our create-only PUT; 07 §6
  tiers B and C are untouched, and RustFS conditional-write behaviour is known
  fragile, so `If-None-Match` parity remains unproven.
- Nothing about the presigned-URL minter under R2's own signing rules; locally
  the same code path signed URLs a local S3 accepted, which is weaker.
- Cross-machine restore. Both restores landed on the same worker (.11). The
  restore verb has no machine affinity, but that is an argument, not a run.
- Corruption injection, retention sweeps and prune against a real store. The
  drill covers them against its own bucket; none ran here.

## Superseding note, 2026-08-16: the `--cold` defect in §4.1 is FIXED

The finding recorded in §4.1 -- that `--cold` could never store a snapshot
because the verify predicate re-ran `discoverRunningRepos` -- no longer holds.
`containersStillUp` (`cmd/renet/backup_snapshot_cold.go:350`) now asks the
repository's OWN Docker socket for running containers and fails CLOSED: an
unreachable socket reports the repo as still up and the run is refused, because
an unverifiable quiesce is exactly the case that must not be labelled cold. The
old bug is documented in that function's comment. `--cold` is therefore
documentable, and the customer guide documents it.

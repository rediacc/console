# PLAN: opt-in exact browse listing (sealed TOC) for password-mounted, non-autostart repositories

Status: proposed -- filed for later; the operator accepted the live-mount listing (renet fb9cf01) as near-exact on 2026-10-21, asked for a plan to make it exact, and ruled the same day that the mechanism must be OPTIONAL, OFF by default, and switched on per repository from rdc
Depends-On: PLAN-chunk-store-browse-toc-and-remote.md
First-Seen: 2026-10-21
Owner: d778be9d
Priority: P3 -- low: restore never reads the index, so restored bytes are already right; only browse-at fidelity improves, and only for repositories whose operator opts in
Concurrency: parallel -- renet and cli files, disjoint from open chunk-store boxes apart from luks.go; take a lease on luks.go before X3
Owns: private/renet/pkg/luks/**, private/renet/pkg/credentials/tockeyring.go, private/renet/pkg/repository/mount.go, private/renet/pkg/repodiff/mountset.go, private/renet/cmd/renet/repository_toc_keyring.go, private/renet/cmd/renet/backup_snapshot_toc.go, private/renet/cmd/renet/backup_snapshot_toc_test.go, private/renet/cmd/renet/repository_autostart.go, private/renet/pkg/functions/commands/repository.go, private/renet/pkg/i18n/locales/*.go, packages/cli/src/commands/repo-extended.ts, packages/cli/src/services/executor/renet-function-access.ts, packages/cli/src/i18n/locales/**, packages/shared/src/cli-contract/data/**, packages/shared/src/renet-contract/data/**, packages/www/src/content/docs/en/cli-application.md, packages/www/src/content/docs/en/rdc-cheat-sheet.md, packages/e2e-tests/tests/25-backup-chunk-store.test.ts
Live-Proof: bench, hostinger -- the LUKS, TOC keyring and autostart code under private/renet is the renet surface (hostinger only), the regenerated contracts under packages/shared/src/cli-contract/data and packages/shared/src/renet-contract/data are the account surface (bench only), and the repo verbs under packages/cli/src are the cli surface, which both admit.

It builds on the chunk-store plan's Stage-2 TOC writer (sealSnapshotTOC, ListingSource) and keeps that plan's rule that the raw volume key is never extracted.

## Finding (checked against the tree, renet at fb9cf01)

1. `snapshotTOCListing` (cmd/renet/backup_snapshot_toc.go) opens the staged reflink only through `repodiff.OpenImageReadOnly` (pkg/repodiff/mountset.go), which needs the slot-1 autostart keyfile. A password-mounted repository falls back to `ListLiveMount`, stamped `ListingSourceLiveMount`, walked just before `PlanSnapshot` on a hot run and after the restart on a cold one. That default stays.
2. The password open is `cryptsetup open --allow-discards` with the password on stdin (pkg/luks/luks.go). On LUKS2, cryptsetup hands the volume key to dm-crypt through the kernel keyring and unlinks it straight after, so nothing user-space can reuse it.
3. Found on the way, and it affects autostart repositories today: the staged copy is mounted `ro,noload`, which skips the ext4 journal. A hot reflink taken after `syncfs` can hold metadata committed to the journal but not checkpointed, so a "staged" listing can differ from a restore whose mount replays the journal. X6 fixes this; the X8 e2e compares against a replayed restore.
4. Re-creating the mapping from `dmsetup table` does not work: it points at a dangling keyring description. The only way round it, `--disable-keyring` plus `--showkeys`, prints the hex key, which is the extraction the parent plan rejects. A plaintext dm-snapshot of the live device needs a suspend and reload of the live table. Rejected.
5. Pattern to copy: `rdc repo autostart enable|disable [ref]` (packages/cli/src/commands/repo-extended.ts) calls `repository_autostart_*` FunctionDefs (private/renet/pkg/functions/commands/repository.go), tier `provision` (`_list` is `read-only`), which shell to `sudo renet repository autostart ...`; the state lives on the machine under `{datastore}/.credentials/keys/`.

## Options

- (A) Kernel-keyring volume key: `cryptsetup open --link-vk-to-keyring @u::rediacc:vk:<guid>` at password mount, then `cryptsetup open --readonly --volume-key-keyring %logon:rediacc:vk:<guid>` on the staged reflink (same LUKS header, same volume key). Exact by construction; reuses the staged-copy path autostart repositories already take.
- (B) Walk the files during the cold outage. Cold runs only, and the outage grows by the walk, breaking "the outage is the reflink". Rejected.
- (C) fanotify change detection on top of the live walk. Not exact (mmap writes, queue overflow, no freeze on hot runs). Rejected.
- Recommended: (A), as an operator opt-in per repository. With it off, renet behaves exactly as fb9cf01 does today.

## What an operator accepts by opting in

- Key residency: today the volume key lives only inside the dm-crypt target while the repository is mounted. Opting in adds a second kernel copy, a `logon` key in root's user keyring, for the same lifetime: linked at mount, unlinked at unmount and on disable, gone at reboot. Nothing on disk, nothing in user space.
- Who can read it: nobody; `keyctl read` refuses `logon` keys, root included. Who can use it: uid-0 processes in the host user namespace that possess @u, which can open a mapping of any local copy of this image (staged reflinks, older copies, chunks restored from storage). Repository containers keep Docker's default seccomp, which blocks keyctl, add_key and request_key.
- What a compromised root gains: on an ordinary kernel, convenience; it could already read the mounted plaintext and pull the key from kernel memory. Under kernel lockdown=confidentiality it is a real new capability (decrypting older image copies), so the docs tell operators of lockdown hosts to leave it off.
- Leftover-key risk: Close unlinks; disable unlinks and fails loudly if the key survives; the reconciler sweep (X5) removes any key with no mapper or no opt-in marker.

## Version requirements (verify in X1)

- cryptsetup >= 2.7.0 for `--link-vk-to-keyring` and `--volume-key-keyring`; kernel >= 4.10. Enabling on an older cryptsetup is refused with the version in the error, and nothing is persisted.
- To confirm on the E2E worker images: Ubuntu 24.04, Debian 12 (expected no), Fedora 41-43, openSUSE Leap 15.6/16.0, Oracle/Rocky 9 (expected from 9.5), CentOS/RHEL 10.
- Gating questions: (a) does `--volume-key-keyring` accept a `logon` key? If only `user`, root could read the key and the plan stops for an operator ruling. (b) Can a mounted repository link its key without a remount (`luksSuspend` plus `luksResume --link-vk-to-keyring`, which pauses I/O)? If not, enabling takes effect at the next mount.

## Design

- rdc surface, a per-repository SETTING rather than a mount flag (a mount flag would be dropped by `repo up` and the reconciler):
  - `rdc repo exact-browse enable <ref> [-m <machine>]`: prints the trade-off, needs `--yes` off a TTY, carries the vault password like autostart enable so renet can check it opens the repository; takes effect at the next mount, or at once if X1(b) allows.
  - `rdc repo exact-browse disable <ref>`; with `-m` and no ref, every repository on the machine (the kill switch).
  - `rdc repo exact-browse status [<ref>]`: enabled, keyActive, cryptsetupOk, and the last snapshot's listing source.
  - Docker repositories only; a cluster ref is refused with the reason, as autostart does.
- How the choice reaches renet: FunctionDefs `repository_exact_browse_enable|_disable|_disable_all|_status` (tier `provision`, status `read-only`), building `sudo renet repository exact-browse ... --json [--password-stdin]`; the renet and cli contracts regenerate.
- What persists, and where: only a root-0600 marker on the machine, `{datastore}/.credentials/exact-browse/<guid>.json` ({enabledAt, cryptsetupVersion}). Nothing in rdc config or the account server, and it is not carried by push, fork, takeover or restore: a copy on another host starts with the setting off.
- Renet when ON: `repository.Mount` sets `Device.LinkVolumeKey` only when the marker exists; `openArgs` adds the link flag; `Close` unlinks; `OpenImageReadOnly` tries the keyfile, then the keyring when marker and key are both present; the TOC predicate becomes "staged copy openable", skipping the live capture.
- Renet when OFF (the default): no marker, no link flag, a stray key is ignored and swept, and the listing is the fb9cf01 live walk.
- Disable: remove the marker, then `keyctl unlink` the key at once (the live mapping keeps its own copy); exit non-zero if the key survives.
- Journal replay for every staged listing (X6): a non-persistent dm-snapshot over the read-only crypt mapping, mounted `ro` without `noload`; the staged image is never written.

## Boxes

- [ ] X1: spike on each E2E worker OS: cryptsetup version; link at open; reopen a reflink from a `logon` key; `keyctl read` refused; link without remount -- acceptance: a table appended here and a go/no-go; a `logon` no-go stops the plan for an operator ruling
- [ ] X2: rdc `repo exact-browse enable|disable|status` with the trade-off prompt, `--yes`, the cluster refusal, access tiers, CLI i18n and regenerated contracts -- acceptance: cli vitest checks dispatch and params per verb, the cluster refusal and the non-TTY refusal; contract and i18n parity gates pass
- [ ] X3: renet keyring helpers, `LinkVolumeKey`, unlink on Close, the marker store, `renet repository exact-browse`, the FunctionDefs, the refusal below 2.7 -- acceptance: go tests check the flag only with a marker at >= 2.7, enable on an old cryptsetup leaves no marker, disable removes the marker, unlinks, and exits non-zero when the key survives; `GOOS=darwin go build ./cmd/renet/` rc 0
- [ ] X4: TOC predicate and the keyring branch in `OpenImageReadOnly` -- acceptance: ON (marker and key) gives ListingSourceStaged with no live capture; OFF (no marker, even with a stray key) gives ListingSourceLiveMount as in fb9cf01; existing TOC and ColdBarrier tests pass with `-race`
- [ ] X5: reconciler sweep removes `rediacc:vk:*` keys with no mapper or no marker -- acceptance: unit test: an orphan and a marker-less key are unlinked, a live opted-in key is kept
- [ ] X6: replayed staged listing (fixes Finding 3, autostart included; can land first) -- acceptance: root test tier: a journal-only change is missing from the `noload` listing and present in the replayed one; the staged file's sha256 is unchanged
- [ ] X7: docs in cli-application.md and rdc-cheat-sheet.md: the verbs, off by default, the opt-in threat model with the lockdown warning, how to turn it off and confirm the key is gone, cryptsetup >= 2.7 -- acceptance: www docs, tutorial-parity and CLI-reference gates pass
- [ ] X8: fleet e2e in 25-backup-chunk-store.test.ts with a password-mounted repository, autostart off, a writer loop running -- acceptance: ON, after enable and a remount, hot then cold snapshots give a `browse --at --json` equal to a restored, replayed mount of the same snapshot in names, sizes and mtimes, listingSource "staged"; OFF (default and after disable), listingSource "live-mount", status keyActive=false, `keyctl search @u logon rediacc:vk:<guid>` fails; the OFF run with the writer loop shows the listings differ (proves the test can fail)
- [ ] LP-bench [live] Fresh bench receipt (PLAN-tested-on-bench ruling 3): deploy this branch to bench with deploy_bench, then record and tick through worklist.py --live-proof.
  - Accept: `live-proof bench account-smoke`
- [ ] LP-hostinger [live] Fresh hostinger receipt through --config eu-bench (PLAN-tested-on-bench ruling 3), after a VERIFIED npm run vm:check -- --changed on the same tree; ASK the operator first, because provisioning a branch renet restarts the router and daemons.
  - Accept: `live-proof hostinger renet-live`

## Rollback

- Per repository or machine: `rdc repo exact-browse disable <ref>` or `-m <machine>` removes the marker and evicts the key at once; snapshots go back to the live listing, which browse-at already reports.
- Full: revert the renet and cli commits and bump the console pointer; leftover markers are then ignored and keys go at the next unmount, sweep or reboot (by hand: `keyctl unlink %logon:rediacc:vk:<guid> @u`). The TOC wire format and account routes do not change, so old and new snapshots stay browsable and restore is unaffected.

# PLAN: `repo sync upload --remote-file` creates parent directories as root:root

Status: approved -- operator /ask 2026-10-23: "Approve both", and "Commit as usual (Recommended)" over the report's keep-uncommitted request
Depends-On: no-dep -- cites no other plan; the fix lives in the CLI sync path, and the renet gateway already admits the transfer shape it needs
Owner: d778be9d
First-Seen: 2026-10-23
Priority: P1 -- a first-time nested `--remote-file` upload leaves a directory the repo's own user cannot delete or modify (`rm -rf` fails with "Permission denied" in `rdc term connect`). The report saw it in two repos, so it is not repo-specific, and the only workaround needs root on the machine.
Concurrency: parallel -- T1 to T3 edit the same CLI files (rsync.ts, repo-sync.ts), so one writer takes T1-T3 and T6 in order; T4 (the VM drill) starts after T3. The one cross-plan overlap is PLAN-renet-bridge-leftovers.md's packages/cli/src/commands/repo-*.ts glob, whose T11 and T14 already wait for this plan, so the guard's overlap rule covers it without a mutex
Owns: packages/cli/src/remote/sync/rsync.ts, packages/cli/src/remote/sync/remote-parents.ts, packages/cli/src/remote/sync/index.ts, packages/cli/src/commands/repo-sync.ts, packages/cli/src/remote/sync/__tests__/remote-parents.test.ts, packages/cli/src/remote/sync/__tests__/rsync-args.test.ts, packages/cli/src/commands/__tests__/repo-sync.test.ts, .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/tests/test_drills_vm_check.py, agent/plans/PLAN-sync-remote-file-ownership.md

## Context

## Operator rulings (2026-10-23, /ask)

- Approved for the parallel implementation wave.
- Commits: the /ask answer was "Commit as usual", but the operator's newer follow-up (2026-10-23, the directory-mode report) says to keep this change in the working tree and not commit unless asked; that newer instruction governs this plan's implementation, and T5 keeps the tree uncommitted.
- Scope grows (same follow-up): directory mode fails when two or more `--remote` levels are missing (`rsync error: error in file IO (code 11) at main.c(800) [Receiver=3.2.7]`, seen with `--local ./icons/ --remote nextcloud/assets/external-icons` while `nextcloud/assets/` was missing; one missing level works). The root cause is shared, rsync creates only the last path component, so one helper serves both modes (T6), and ownership and missing-folder handling cannot drift apart again.
- The operator's own access note (2026-10-23) confirms the bug in passing: `--remote-file` creates missing parents as root.

### The report (operator, 2026-10-23, `/tmp/prompt-sync-remote-file-ownership.md`)

`rdc repo sync upload --remote-file` creates missing parent directories as root:root inside the repository. The uploaded file is owned by the repo's universal user (`rediacc`, uid/gid 7111). That user then cannot delete or modify the directory.

Observed on machine "hostinger" (Ubuntu 24.04):
- `rdc repo sync upload nextcloud --local ./x.py --remote-file .rdc-tmp/x.py`, with `.rdc-tmp/` not yet existing, left `<repo-mount>/.rdc-tmp` as root:root 775 and `<repo-mount>/.rdc-tmp/x.py` as rediacc:rediacc 644.
- Uploading a directory (`--local <dir>/ --remote <path>`) created the directories correctly as rediacc:rediacc.
- A second repo (observability) behaved the same. An existing parent directory kept its correct ownership.

Expected: every directory the sync creates gets the owner and group of the uploaded files, as directory-upload mode does.

Requested work:
1. Reproduce with a unit test of the generated remote command, plus an e2e or VM check where a harness exists.
2. Fix it so created parent directories are owned by the universal user, and only the ones the sync created.
3. Never change the ownership of existing directories.
4. Follow CLAUDE.md for verification.
5. Keep changes in the working tree and do not commit unless asked.

Implementation constraint carried from the report: this plan's writers leave the tree uncommitted. The lead confirms with the operator how that squares with CLAUDE.md section 1 (see Verification notes).

### Root cause

No `mkdir -p` runs anywhere in the rsync path. The remote parents come from rsync's own `--mkpath`, executed by a receiver that runs as root. The universal-user mapping only reaches entries in the transfer list, and `--mkpath` directories are not in the list.

1. File mode sets the flag. `packages/cli/src/commands/repo-sync.ts:370` passes `mkpath: isFileMode` into the upload's `RsyncExecutorOptions`. The destination is `user@host:<mount>/<sub>` with no trailing slash (`buildSyncRemotePaths`, `packages/cli/src/commands/repo-sync-helpers.ts:72-76`). `buildRsyncArgs` turns it into `--mkpath` (`packages/cli/src/remote/sync/rsync.ts:224`).
2. The receiver is root. `addRemoteRsyncArgs` (`packages/cli/src/remote/sync/rsync.ts:155-170`) sets `--rsync-path 'sudo rsync'` whenever a universal user is known. `universalUser` always has a value, because `packages/cli/src/services/state.ts:189` reads `defaults.universalUser` and falls back to `'rediacc'`. The remote rsync therefore runs as root.
3. `--chown rediacc:rediacc` (`packages/cli/src/remote/sync/rsync.ts:164`) reaches the receiver as `--usermap=*:rediacc --groupmap=*:rediacc`. The gateway pins that shape (`private/renet/cmd/renet/sandbox_gateway_transfer.go:272-297`). The mapping rewrites the owner of every entry in the file list.
4. `--mkpath` is handled in the receiver before the file list is consulted. It creates the destination's parent chain as root with the default mode minus umask, which gives the observed 775. Those directories are not entries in the transfer list, so no usermap applies and they stay root:root. The file is in the list, so it is mapped to rediacc. This is rsync behaviour and is not exercised in-repo; T4 confirms it on a real machine.
5. The gateway admits this exact line and pins it in a Go test: `cliFileMkpath = sudo rsync --server ... --usermap=*:rediacc --groupmap=*:rediacc --inplace --mkpath . MOUNT/a/b/f` (`private/renet/cmd/renet/sandbox_gateway_transfer_test.go:34`). `transferPlan` runs `sudo rsync` as root (`private/renet/cmd/renet/sandbox_gateway_transfer.go:207-231`). The sandbox confines paths to the mount but does not chown.

The directory-upload path differs line by line:
- It does not set `mkpath` (the option is file-mode only, `packages/cli/src/commands/repo-sync.ts:370`). The destination is `<mount>/<sub>/` with a trailing slash.
- rsync creates only the final destination component. That component is entry "." of the transfer list, as are all deeper directories, so the usermap applies to every created directory, which matches the report's "directory upload is correct".
- Corollary: a directory upload into a `--remote` path with two or more missing levels fails instead of creating them. That is a separate, pre-existing behaviour and is not changed here.

The SFTP fallback (`packages/cli/src/remote/sync/sftp-fallback.ts:150-157` and `packages/cli/src/remote/sync/sftp-remote-helpers.ts:44-55`) runs `mkdir -p` over `sftp.exec` as the SSH session's user, not root, so it is not the root:root mechanism.

### Sibling sweep

| Path | Same pattern? | Disposition |
|---|---|---|
| `packages/cli/src/commands/repo-sync.ts:370` upload `mkpath: isFileMode` plus `sudo rsync` | Yes, the bug | Fixed by T1 to T3 |
| `packages/cli/src/commands/repo-sync.ts` download file mode | No: rsync's receiver is local, so `--mkpath` does not apply | Unchanged; T2 adds a guard test that download args carry neither `--mkpath` nor `--chown` |
| `packages/cli/src/remote/sync/rsync.ts:431` dry-run `buildRsyncArgs` with `mkpath` | Dry run creates nothing | Unchanged; the skeleton step is skipped on `--dry-run` |
| `packages/cli/src/remote/sync/sftp-fallback.ts` `ensureFileParent` | Different mechanism (session user, no root), and the file itself carries no chown there | Not changed; a known gap on team-key (plain SSH) machines |
| `packages/cli/src/services/renet/renet-binary-transfer.ts:181` `executeRsync` | No `mkpath`, `universalUser` unset | Unaffected |
| `packages/cli/src/commands/vscode.ts:218-220` | Already `sudo mkdir -p` then `sudo chown -R universalUser` on the created path | Correct; the model for the pattern |
| `packages/cli/src/services/core/vscode-server-remote.ts:226` `mkdir -p "$(dirname ...)"` | Runs in the repo shell as the repo user | Unaffected (T3 re-reads and confirms) |
| `packages/cli/src/services/account/license-machine.ts:265` `sudo mkdir -p repoDir` | Root-owned license directory by design | Unaffected |

### Fix design

Recommended approach: a skeleton rsync of exactly the missing segments, before the file transfer.

1. Probe the remote parent chain of the file, top-down from the mount, with SFTP `exists` (`SFTPClient.exists`, `packages/cli/src/remote/sftp/client.ts:365`) on the pooled connection the command already uses. It is read-only and works under both the gateway and plain SSH.
2. The probe stops at the first missing segment; everything below it is missing too. The result is `{ existingAncestor, missing }`. It is empty when the parent exists, and then nothing else runs.
3. When `missing` is non-empty, build a local temp tree holding only those segments (directories 0775, keeping today's group-write) and upload it as a directory with the unchanged privileged args (no `mkpath`, no mirror, no excludes): source `<tmp>/`, destination `user@host:<existingAncestor>/<missing[0]>/`, where the temp tree's top level holds `missing[1..]` (the segments after the first), since the trailing-slash source copies the tree's contents into the destination and rsync creates `missing[0]` itself as the destination directory. That is the verified directory-upload shape, so the usermap applies to every created directory, and the gateway already admits it: no renet change.
4. Then run the existing file rsync unchanged. Its parents now exist, so `--mkpath` is a no-op, kept for races.

Why this satisfies the constraints: only segments the probe found missing are ever sent, so existing directories are never re-owned; it works the same through the gateway and over plain SSH; and it reuses the directory path's universal-user resolution (`ctx.details.universalUser`, sent as `--chown name:name`; the remote resolves the name to uid 7111, `private/renet/pkg/config/constants.go:89`).

Trade-offs: one extra rsync and up to depth-many SFTP stats on the first upload into a new directory; a narrow race when another writer creates the same new segment between probe and skeleton (accepted and stated in the code comment); if the probe cannot run, the step is skipped and the transfer proceeds exactly as today, with a debug line naming the skip.

Rejected: `--relative` with implied dirs (the gateway's flag cluster does not admit `R`, and implied directories would re-own existing ones); chown afterwards over ssh (no sudo in the gateway's shell sandbox); creating as the universal user over ssh (right under the gateway, wrong on plain SSH, and the CLI cannot tell which applies); an unprivileged rsync for file mode (cannot overwrite root-owned or container-uid files); a renet-side chown in the gateway (fixes only gateway machines and needs a submodule deploy; a possible follow-up, not this fix).

## Tasks

T5 is the closure and runs last: T6 (directory mode, added after the first draft) is listed above it so the closure verifies both modes.

- [x] T1 [A] Pure parent-chain planner and skeleton builder in a new `packages/cli/src/remote/sync/remote-parents.ts`: `planMissingParents(baseRemotePath, remoteFileSubPath, exists)` returning `{ existingAncestor, missing }` (stops at the first missing segment, treats a probe error as "exists"), `writeSkeleton(missing)` building the 0775 temp tree, and `skeletonDestination(...)`, exported through `remote/sync/index.ts` -- Owns: packages/cli/src/remote/sync/remote-parents.ts, packages/cli/src/remote/sync/index.ts. Accept: `cd packages/cli && npx vitest run src/remote/sync/__tests__/remote-parents.test.ts` exits 0.
    (ticked) 2026-10-23T15:43:20Z by d778be9d: commit:3bc245d00 packages/cli/src/remote/sync/remote-parents.ts:28 planMissingParents, writeSkeleton and skeletonDestination exported through packages/cli/src/remote/sync/index.ts; vitest src/remote/sync rc=0
- [x] T2 [A] Unit tests in a new `packages/cli/src/remote/sync/__tests__/remote-parents.test.ts` and in `rsync-args.test.ts`: all segments missing yields one skeleton rooted at the mount; `a` existing and `a/b` missing yields only `b` under `a`; all existing yields no skeleton and no rsync call; a probe error yields no skeleton; skeleton args equal the directory-upload args (`--rsync-path sudo rsync` and `--chown rediacc:rediacc`, no `--mkpath`, `--delete` or `--exclude`); the destination ends in `/`; download args carry neither `--mkpath` nor `--chown`; file-transfer args still carry `--mkpath` -- Owns: packages/cli/src/remote/sync/__tests__/remote-parents.test.ts, packages/cli/src/remote/sync/__tests__/rsync-args.test.ts. Accept: `cd packages/cli && npx vitest run src/remote/sync/__tests__` exits 0, and the new cases fail with T3's call removed (one control run, rc 1, then restored).
    (ticked) 2026-10-23T15:43:21Z by d778be9d: commit:3bc245d00 packages/cli/src/remote/sync/__tests__/remote-parents.test.ts and rsync-args.test.ts cases; vitest 145 passed rc=0; planMissingParents sabotage fails 7 tests
- [x] T3 [A] Wire the step into `syncUpload` in `packages/cli/src/commands/repo-sync.ts`: in file mode and not `--dry-run`, run the probe on the pooled SFTP connection and the skeleton rsync inside the rsync attempt of `executeSyncWithSftpFallback`, so a missing local rsync still falls back to SFTP; add a `repo-sync.test.ts` case with a fake rsync runner and a fake SFTP (new parent: two rsync calls, skeleton first; existing parent: one; dry run: none) -- Owns: packages/cli/src/commands/repo-sync.ts, packages/cli/src/commands/__tests__/repo-sync.test.ts. Accept: `cd packages/cli && npx vitest run src/commands/__tests__/repo-sync.test.ts src/remote/sync/__tests__` exits 0; `npx tsc --noEmit --project packages/cli/tsconfig.json` exits 0; `npm run check:lint` exits 0.
    (ticked) 2026-10-23T15:43:21Z by d778be9d: commit:3bc245d00 packages/cli/src/commands/repo-sync.ts:364 ensureRemoteParents inside the rsync attempt, skipped on dry run; repo-sync.test.ts rc=0; npx tsc rc=0
- [x] T4 [B] Real-machine drill in `.ci/rediacc_ci/drills/vm_check.py`, step V1.5 (the existing sync round trip): after the round trip, upload one file with `--remote-file vmc-newdir-<run>/f.txt` and assert the new directory is `rediacc:rediacc`; pre-create `vmc-keep-<run>` as root:root through the drill's raw ssh, upload `--remote-file vmc-keep-<run>/g.txt`, and assert it is still `root:root`; extend the fake host in `.ci/rediacc_ci/tests/test_drills_vm_check.py` so both rows pass and a planted root-owned new directory fails -- Owns: .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/tests/test_drills_vm_check.py. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_drills_vm_check.py` exits 0, and `npm run vm:check -- --changed` ends VERIFIED with the two new V1.5 rows passing.
    (ticked) 2026-10-23T15:43:01Z by d778be9d: commit:3bc245d00 .ci/rediacc_ci/drills/vm_check.py:2208; npm run vm:check -- --changed VERIFIED on a throwaway vmc fork, 52 assertions 0 failed, parents rediacc:rediacc, existing root:root kept; test_drills_vm_check.py 236 passed rc=0
- [x] T6 [A] Directory mode shares the helper: `syncUpload` in directory mode (`--local <dir>/ --remote <path>`) runs the same probe and skeleton step for every missing level of `<path>`, so nested missing folders are created owned by the universal user before the transfer; one helper in `packages/cli/src/remote/sync/remote-parents.ts` serves both modes; check the minimum rsync version rdc supports on target machines (where the CLI or renet states it) before relying on any rsync flag, and record it here. Tests: nested missing folders in directory mode and in `--remote-file` mode, and an existing folder whose owner is unchanged; the vm:check V1.5 rows gain a nested `--remote a/b/c` directory upload -- Owns: packages/cli/src/remote/sync/remote-parents.ts, packages/cli/src/commands/repo-sync.ts, packages/cli/src/remote/sync/__tests__/remote-parents.test.ts, packages/cli/src/commands/__tests__/repo-sync.test.ts, .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/tests/test_drills_vm_check.py. Accept: `cd packages/cli && npx vitest run src/remote/sync/__tests__ src/commands/__tests__/repo-sync.test.ts` exits 0; on a throwaway fork (never a production repo) `rdc repo sync upload <fork> --local ./d/ --remote a/b/c` succeeds and `stat -c '%U:%G'` of `a`, `a/b` and `a/b/c` reads `rediacc:rediacc` each; `npm run vm:check -- --changed` ends VERIFIED.
    (ticked) 2026-10-23T15:43:02Z by d778be9d: commit:3bc245d00 packages/cli/src/commands/repo-sync.ts:364 one helper for both modes; live nested --remote a/b/c upload on a throwaway fork created a, a/b, a/b/c as rediacc:rediacc (vm:check VERIFIED); no rsync flag newer than --mkpath (3.2.3+) is relied on
- [ ] T5 [lead] Closure: run the verification set CLAUDE.md names for this change set, reproduce the bug once on the pre-fix tree (the new V1.5 row fails with `root:root`), re-run after the fix (it passes), and report the exit codes; the tree stays uncommitted per the operator's report unless the operator says otherwise -- Owns: agent/plans/PLAN-sync-remote-file-ownership.md. Accept: `npm run vm:check -- --changed` exits 0 on the fixed tree.

### Acceptance on a real machine

The existing harness covers sync: `npm run vm:check` step V1.5 on the ops VM fleet. Manually, with `<repo>` a fork on a worker and `<mount>` its mount:

```
rdc repo sync upload <repo> --local ./f --remote-file newdir/f
rdc term connect <repo> -c "stat -c '%U:%G' <mount>/newdir <mount>/newdir/f"   # expect rediacc:rediacc twice
rdc repo sync upload <repo> --local ./f --remote-file deep/a/b/f               # two levels at once
rdc term connect <repo> -c "stat -c '%U:%G' <mount>/deep <mount>/deep/a <mount>/deep/a/b"
ssh <vm-user>@<worker-ip> sudo install -d -o root -g root -m 755 <mount>/keep
rdc repo sync upload <repo> --local ./f --remote-file keep/g
ssh <vm-user>@<worker-ip> stat -c '%U:%G %a' <mount>/keep                       # expect root:root 755
```

Production `hostinger` is not used for the reproduction.

## Verification notes

Facts in the report that the code corrects or leaves unconfirmed:
- The report lists `mkdir -p`, `--rsync-path`, `--mkpath`, `--chown` and `--usermap` as candidates. The code uses only `--mkpath` with a root receiver (`sudo rsync`); no `mkdir` runs, and `--chown` works for entries in the transfer list.
- "uid/gid 7111": the CLI never resolves a uid for sync; it sends the name `rediacc` (`packages/cli/src/services/state.ts:189`), and 7111 is renet's `RediaccUID` (`private/renet/pkg/config/constants.go:89`).
- "Directory upload created the directories correctly" holds for the destination root and the tree inside it; a directory upload into two or more missing levels fails.
- Root-cause step 4 is rsync's documented behaviour, not run here; T5's pre-fix run proves it.

Points for the lead to confirm with the operator:
- The report says to keep changes in the working tree and not commit; CLAUDE.md section 1 commits verified work as it lands. The plan follows the report until the operator decides.
- A push touching `packages/cli/src/remote/` needs a VERIFIED `npm run vm:check -- --changed` receipt; T4 and T5 produce it.
- No renet change is expected; a renet-side chown would be a separate plan in the private/renet submodule.

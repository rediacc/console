# PLAN: a repo shell runs in a read-only mount view with an explicit writable set, and refuses to run without Landlock

Status: active -- written 2026-10-14 by d778be9d from code reading at renet 2131e1a; the hypothesis it fixes has not been run yet (box H0 runs it first and can end the plan)
Depends-On: no-dep -- builds on renet 21d1e22 (transfer sandbox, readOnlyExcept) and 3100a4c (sftp-server in the transfer sandbox), both already on the branch
Owner: d778be9d
First-Seen: 2026-10-14
Priority: P1 -- a cross-repo integrity hole on every multi-repo machine: any repo key holder, or an agent in a repo shell, can re-mode or re-time every other repo's files
Concurrency: exclusive -- every renet box edits cmd/renet/sandbox_exec.go or the gateway argv it builds; one writer, boxes in order. E1 and D1 may run in parallel with S3 once S2 has landed. PLAN-inline-suppressions WD2 still holds private/renet/** in its Owns: these boxes add no lint-suppression markers, and WD2 adds no edits to the files below
Owns: private/renet/cmd/renet/sandbox_exec.go, private/renet/cmd/renet/sandbox_readonly_linux.go, private/renet/cmd/renet/sandbox_overlay_linux.go, private/renet/cmd/renet/sandbox_mount_linux.go, private/renet/cmd/renet/sandbox_gateway.go, private/renet/cmd/renet/sandbox_gateway_shell_linux_test.go, private/renet/cmd/renet/sandbox_gateway_race_linux_test.go, private/renet/cmd/renet/sandbox_gateway_test.go, private/renet/cmd/renet/sandbox_exec_test.go, private/renet/cmd/renet/sandbox_exec_workspace_test.go, private/renet/cmd/renet/literals.go, private/renet/pkg/i18n/locales/*.go, private/renet/pkg/i18n/locales/hashes.json, packages/e2e-tests/tests/01-system-checks.test.ts, packages/www/src/content/docs/*/limits.md
Worklist: #b2dd43b3
PR-TASK: 8ed364fe

## Why

A repo key's interactive shell, and its `bash -c` commands, run as `sudo renet sandbox-exec ... --run-as rediacc -- bash` (`private/renet/cmd/renet/sandbox_gateway.go:138-165` for the plan, `:175-205` for the argv). That argv carries Landlock allow-lists and no `--readonly-except`.

Three facts together make the hole:

1. **Every repo's shell runs as the same account.** `resolveGatewayContext` admits only `config.RediaccUser` (`private/renet/cmd/renet/sandbox_gateway.go:223-228`).
2. **That account owns every other repo's files.** A mount's contents are chowned to `RediaccUID` (`private/renet/cmd/renet/repository_mount.go:204`, `private/renet/cmd/renet/repository_apply_template.go:159`), and the datastore subdirectories are created group-writable and owned by the same account (`private/renet/pkg/datastore/directory.go:51-75`).
3. **Landlock does not cover chmod, chown, utimes or xattrs.** The 21d1e22 commit message measured this for chmod, and `private/renet/cmd/renet/sandbox_readonly_linux.go:15-22` says it in code.

**Hypothesis (inferred, never run):** the shell of repo A can run `chmod`, `touch -d` or `setfattr -n user.*` on `/mnt/rediacc/mounts/<guidB>/<file>` and succeed: Landlock refuses the open, and the call never opens the file. On ABI < 3 kernels (Debian 12, kernel 6.1) `truncate(2)` by path is not covered either.

### Why the shell cannot copy the transfer sandbox's call order

`runSandboxExec` builds the read-only view right after the namespace is created (`private/renet/cmd/renet/sandbox_exec.go:113-120`), before every other mount. That order is wrong for a shell:

- **(a) Home overlay.** `setupHomeOverlay` (`private/renet/cmd/renet/sandbox_exec.go:123-127`) needs a writable upper layer under `--sandbox-dir`.
- **(b) eBPF isolation.** `setupRepoEbpf` (`private/renet/cmd/renet/sandbox_exec.go:146`) writes `/sys/fs/cgroup/rediacc.slice/renet-exec-<id>/cgroup.procs` and pins links under `/sys/fs/bpf/rediacc` (`private/renet/pkg/ebpf/manager.go:613-627`, `:30`, `:483`); `JoinExecCgroup` swallows the error (`private/renet/pkg/ebpf/manager.go:621-626`), so the shell would silently lose its network isolation.
- **(c) Private /tmp.** The `/tmp` bind (`private/renet/cmd/renet/sandbox_exec.go:130-135`) only warns when it fails, which under a view that names `/tmp` writable would leave the host's shared `/tmp` writable.

### The writable set

The rw grants in `buildGatewaySandboxArgs` (`private/renet/cmd/renet/sandbox_gateway.go:177`) are the in-production list of places a shell writes: the repo mount, `<ds>/.interim/sandbox/<repo>`, `/dev`, `/tmp` (a per-repo bind), `/home/rediacc` (a per-repo OverlayFS, `private/renet/cmd/renet/sandbox_overlay_linux.go:23-45`) and the docker socket (`private/renet/pkg/sandbox/landlock.go:87-89`). The view takes away only the calls Landlock does not cover outside that set, plus file creation on `/dev/shm`. Device-node writes and unix-socket connects need no writable mount.

The CLI's writes stay inside the set: the VS Code server under `<mount>/.vscode-server` (`packages/cli/src/commands/vscode.ts:158-164,207-219,291-294`, `packages/cli/src/remote/vscode/setup-script.py:96-141`), `~/.docker`, `~/.gitconfig` and `~/.viminfo` in the home overlay, and the bashrc written by root before the drop (`private/renet/cmd/renet/sandbox_exec.go:263-270`).

## Design

**Chosen: A, a read-only view with an explicit writable set.** Generalize the 21d1e22 primitive to a list of writable paths and seal at the end of mount setup, right before `applyLandlockAndDrop`. The writable set is the mount, the sandbox dir, the home overlay, the private `/tmp` and a new private `/dev/shm`. It is an allowlist and fails closed; it also stops cross-repo `truncate` on ABI < 3 kernels. It leaves open same-uid signals, abstract unix sockets, SysV/POSIX IPC, pty nodes under the `/dev` grant and `stat` of other repos' paths (Follow-ups).

**Rejected: B, a uid per repo.** Strongest isolation, but a product-wide migration: the gateway admits one account (`private/renet/cmd/renet/sandbox_gateway.go:223-228`), mounts are chowned to `RediaccUID`, transfers run as `config.RediaccUser` (`private/renet/cmd/renet/sandbox_gateway_transfer.go:57`), backups run `sudo -u rediacc` (`private/renet/cmd/renet/backup_push.go:557`, `private/renet/cmd/renet/backup_pull.go:554`), the CLI chowns the VS Code tree to `universalUser`, and container volumes would need re-owning across fork, takeover, backup and restore.

**Deferred: C, hiding other mounts.** A denylist: every rediacc-owned writable place must be enumerated (backup staging dirs at `private/renet/cmd/renet/backup_push.go:453`, other datastores). Kept as later hardening on top of A.

**Landlock is required as well.** The view only stops metadata writes; Landlock stops reads and writes of contents, and its ptrace rule closes the `/proc/<pid>/cwd` route into another repo's namespace. Today a shell without Landlock gets one warning and runs unconfined (`private/renet/cmd/renet/sandbox_exec.go:207-215`).

### What requiring Landlock breaks

Expected ABI on the CI matrix (`.github/workflows/ct-tests.yml:342-347`): Ubuntu 24.04 (6.8) 4, Debian 13 (6.12) 6, Fedora 43 6+, openSUSE Leap 16.0 6 (inferred), Oracle Linux 10 UEK 8 6. Debian 12 (documented "also works") is ABI 2. A built-in Landlock is not an active one (it must be in `lsm=`), and nothing here measures it: `private/renet/pkg/sandbox/sandbox_test.go:14-29` accepts ABI 0, no e2e suite runs `sandbox-exec --detect`, and `packages/www/src/content/docs/en/limits.md:204` says "yes" with no test behind it. Box E1 measures it.

On a host without active Landlock, repo-key shells refuse with `sandbox_exec.landlock_required` (`rdc term connect -r`, `rdc vscode connect -r`, Remote-SSH through the repo alias). Machine keys are unaffected (`planUnsandboxed`, `private/renet/cmd/renet/sandbox_gateway.go:405-411`), and so are Rediaccfile runs (`private/renet/pkg/orchestration/rediaccfile.go:243`). The same hosts already refuse every transfer since 21d1e22.

### A test gap this plan also closes

CI runs renet's go tests as root (`private/renet/.ci/scripts/test/run-tests.sh:46-50`). `newTransferRace` builds the root path only when NOT root (`private/renet/cmd/renet/sandbox_gateway_race_linux_test.go:68`), so as root it strips the read-only view and skips the mode case (`:251-254`), and `TestRunSandboxExecRefusesWithoutTheReadOnlyView` skips as root (`private/renet/cmd/renet/sandbox_exec_test.go:76-79`). The read-only view has never run in CI. Box S1 fixes this.

## Tasks

- [x] H0: prove the hypothesis on the unchanged sandbox, first.
  - Two test seams in `sandbox_gateway.go` with unchanged defaults: `shellUser = config.RediaccUser` (for `gctx.user` at `:225`) and `shellHomeRoot = "/home"` (for `homeDir` at `:129`).
  - New `cmd/renet/sandbox_gateway_shell_linux_test.go`, reusing `TestMain`'s sandbox-exec dispatch (`private/renet/cmd/renet/sandbox_gateway_race_linux_test.go:20-31`).
  - Fixture under `/var/tmp` (never `t.TempDir()`: the shell overmounts `/tmp`, and a vanished datastore fakes a pass with ENOENT): a datastore with `mounts/<guidA>`, `mounts/<guidB>` and `.interim/sandbox`, directories 0755, victim `mounts/<guidB>/victim` at 0600 with a fixed mtime, owned by the run-as user.
  - As root (CI) run with `shellUser = "nobody"`; as non-root with passwordless sudo, `shellUser` is the current user; otherwise skip with the reason. Skip when `sandbox.LandlockABI() == 0`.
  - Controls that must pass: `stat` of B's victim succeeds inside the sandbox; `chmod 0640` on A's own file succeeds.
  - Cases: `chmod 0777 <B>/victim`, `touch -m -d @0 <B>/victim`, `truncate -s 0 <B>/victim`, and `setfattr -n user.x -v 1 <B>/victim` when setfattr is installed. B's victim keeps its mode, mtime, size and xattrs.
  - If chmod and touch are already refused on 2131e1a, the hypothesis is false: record the errno, tick H0 with it, and collapse the plan to S1, S3 and E1.
  - Acceptance: `cd private/renet && go test -count=1 -run TestShellOfOneRepoCannotChangeAnotherRepo ./cmd/renet` FAILS on 2131e1a plus seams naming chmod and utimes, both as a sudo-capable user and as `sudo -E env PATH=$PATH go test ...`; the failure lines are quoted in the S2 commit message.
    (ticked) 2026-10-14T16:26:08Z by d778be9d: renet 0033236: the H0 test failed on the unchanged sandbox: chmod, touch and xattr on repo B by repo A shell rc=0, quoted in the S2 commit; go test -count=1 ./cmd/renet rc=0 as non-root and the targeted root run PASS; lint.sh and i18n.sh rc=0 (private/renet/cmd/renet/sandbox_gateway_shell_linux_test.go)
- [x] S1: the read-only view runs in CI.
  - `newTransferRace` as uid 0 keeps `--readonly-except`, sets `transferUser = "nobody"`, chowns the fixture to nobody and sets `r.root = true` so the mode case runs.
  - A root sibling of `TestRunSandboxExecRefusesWithoutTheReadOnlyView` builds the view in a child and proves a write outside the writable path fails with EROFS.
  - Acceptance: `sudo -E env PATH=$PATH go test -count=1 -run 'TestTransferLinkSwappedAfterTheCheckCannotEscape|TestRunSandboxExec' -v ./cmd/renet` shows the mode case as PASS, not SKIP; `go test -count=1 ./cmd/renet` as non-root rc 0.
    (ticked) 2026-10-14T16:26:38Z by d778be9d: renet 40febec: as root the transfer race keeps the read-only view and runs the mode case; TestRunSandboxExecBuildsTheReadOnlyView proves EROFS; go test -count=1 ./cmd/renet rc=0 as non-root and the targeted root run PASS; lint.sh and i18n.sh rc=0 (private/renet/cmd/renet/sandbox_gateway_race_linux_test.go:1)
- [x] S2: the shell sandbox seals its mounts read-only except an explicit writable set.
  - `readOnlyExcept(writable []string)`: every path absolute, clean and existing; bind each onto itself with `MS_BIND|MS_REC`; one `MountSetattr(RDONLY, AT_RECURSIVE)` on `/`; clear RDONLY on each path.
  - `--readonly-except` becomes a `StringArray` (not `StringSlice`, which splits on commas). The early refusal without a namespace stays (`private/renet/cmd/renet/sandbox_exec.go:113-117`). The seal MOVES to just before `applyLandlockAndDrop`, after `setupRepoEbpf`, the home overlay and the `/tmp` bind. With `--readonly-except`, a failed `/tmp` or `/dev/shm` bind is fatal.
  - A private `/dev/shm`: `initSandboxWorkspace` creates `<sandboxDir>/shm` chowned to the run-as user, bound over `/dev/shm` after the `/tmp` bind.
  - `buildGatewaySandboxArgs` appends `--readonly-except` for the work dir, sandbox dir, home dir, `/tmp` and `/dev/shm`; the argv golden in `sandbox_gateway_test.go` carries them in that order.
  - i18n: `sandbox_exec.readonly_view` takes the joined list; a new key `sandbox_exec.private_mount` in all 13 locales and hashes.json.
  - The H0 test goes green and gains positive cases inside A's shell: write and chmod in A's mount, `~/f`, `/tmp/f`, `/dev/shm/f`, `/dev/null`, a git commit in the mount when git is installed, a connect to a unix-socket listener outside the writable set; and A's `ls /dev/shm` does not show B's marker.
  - Acceptance: `go test -count=1 ./cmd/renet ./pkg/i18n/...` rc 0 as non-root and as root, with `TestShellOfOneRepoCannotChangeAnotherRepo` PASS in the root run; `GOOS=linux|darwin|windows go build ./...` rc 0; `go vet` rc 0; `bash .ci/scripts/quality/lint.sh` and `bash .ci/scripts/quality/i18n.sh` rc 0; console `npm run check:ci-renet` rc 0.
    (ticked) 2026-10-14T16:26:40Z by d778be9d: renet 0033236: TestShellOfOneRepoCannotChangeAnotherRepo PASS as root, with positive cases for the mount, home, tmp, dev/shm, git and a socket; go test -count=1 ./cmd/renet rc=0 as non-root and the targeted root run PASS; lint.sh and i18n.sh rc=0 (private/renet/cmd/renet/sandbox_readonly_linux.go:1)
    (evidence) 2026-10-14 by d778be9d: go vet ./cmd/renet rc=0 on the landed tree and npm run check:ci-renet rc=0 at f56153c61, the two acceptance commands the tick did not show (review f56153c6.2); the code the ledger rows cite is private/renet/cmd/renet/sandbox_readonly_linux.go readOnlyExcept and private/renet/cmd/renet/sandbox_gateway_shell_linux_test.go TestShellOfOneRepoCannotChangeAnotherRepo (f56153c6.3)
- [x] S3: a shell refuses to run without Landlock.
  - `buildGatewaySandboxArgs` adds `--require-landlock`; the comment at `private/renet/cmd/renet/sandbox_exec.go:200-205` no longer names the shell as the warn-only case.
  - Tests: the shell argv carries `--require-landlock`; with `landlockABI` forced to 0 the shell's sandbox-exec argv refuses and a marker command does not run; as root, repo A's `chmod 0777 /proc/<pid of B's shell>/cwd/victim` fails and the victim is unchanged. If that last case SUCCEEDS, stop and escalate: the view would need a private PID namespace and procfs.
  - Acceptance: `go test -count=1 -run 'TestShellPlan|TestShellOfOneRepo|TestRunSandboxExec' ./cmd/renet` rc 0 as non-root and as root; the S2 build, lint and i18n commands rc 0.
    (ticked) 2026-10-14T16:26:41Z by d778be9d: renet bcb9351: TestShellPlanRefusesWithoutLandlock and TestShellOfOneRepoCannotReachAnotherThroughProc PASS as root; go test -count=1 ./cmd/renet rc=0 as non-root and the targeted root run PASS; lint.sh and i18n.sh rc=0 (private/renet/cmd/renet/sandbox_gateway.go:1)
- [ ] E1: measure, and from then on gate, Landlock on every supported OS.
  - `packages/e2e-tests/tests/01-system-checks.test.ts`: `runner.executeOnWorker('renet sandbox-exec --detect')` prints `Status: AVAILABLE`, and its ABI line is logged.
  - Measure the default image first: `./rdc.sh ops up --basic`, then `ssh 192.168.111.11 renet sandbox-exec --detect`.
  - A leg that shows `NOT AVAILABLE` holds S3; the box becomes `[?]` with DEFAULT: document `lsm=...,landlock` for that OS and keep the refusal.
  - Acceptance: `npx tsc --noEmit -p packages/e2e-tests` rc 0; `npx biome lint packages/e2e-tests --error-on-warnings` rc 0; the PR's bridge-workers legs for ubuntu-24.04, debian-13, fedora-43, opensuse-16.0 and oracle-10 green with the new test passing.
- [x] D1: the docs stop calling Landlock non-gating.
  - `packages/www/src/content/docs/en/limits.md:202` calls the kernel matrix "not a gating criterion"; Landlock is now required for repo-key shells and transfers. Rewrite that sentence and the Landlock column heading (`:204`) in all 13 locales.
  - Acceptance: the www docs and i18n parity gates rc 0.
    (ticked) 2026-10-20T15:40:13Z by d778be9d: commit:67c6bbef2 limits.md in 13 locales; www docs and i18n parity gates rc 0
- [x] V1: live verification on ops VMs with the S2 and S3 renet.
  - `./rdc.sh ops up --basic`; fork `sbxa` and `sbxb` on the worker; `./rdc.sh repo up` both, which deploys the new renet.
  - From an sbxa shell, `chmod 0777` and `touch -d @0` on `/mnt/rediacc/mounts/<guidB>/.rediacc.json` both report `Read-only file system`, and a machine-level `stat` shows mode and mtime unchanged.
  - Inside sbxa: writes to `~`, `/tmp`, `/dev/shm` and the mount, `chmod 600` in the mount, `docker ps`, `renet compose -- ps`, a git commit, `vi -c wq ~/v`, all rc 0; sbxb's `ls /dev/shm` does not show sbxa's file; `cat /proc/self/cgroup` names `renet-exec-<networkId of sbxa>`.
  - `./rdc.sh repo sync upload` then `download` round trip for sbxa, followed by a diff.
  - VS Code: `./rdc.sh vscode check` and the `ensureVSCodeEnvSetup` run through the repo key print "Environment setup complete"; a desktop `vscode connect` is the operator's.
  - Acceptance: every command's output is pasted in the round log; the cross-repo step shows EROFS; the rest rc 0.
  - (evidence 2026-10-20) `npm run vm:check` run vmc-10201403-2d9ea5 (PLAN-vm-check VC6, renet 0eaf033 carrying S2 and S3) rc 0 VERIFIED: V1.1 forks a and b up on the worker; V1.2 from A, `chmod` and `touch` on B's `.rediacc.json` fail read-only and B's stat is unchanged; V1.3 writes to ~, /tmp, /dev/shm and the mount, chmod 600 in the mount, docker ps, `renet compose -- ps`, a git commit, all ok (the image has no vi, so the edit leg rewrites ~/v with sed -i by temp file and rename); V1.4 B's /dev/shm does not show A's marker and A's cgroup names renet-exec-5440; V1.5 `repo sync upload --verify` then `download` ran with the byte-equal check, and V1.6 `vscode connect --url-only` printed a remote URI with `.vscode-server` present (receipt steps V1.5 and V1.6, vm_check.py:2157-2207); the cross-repo refusal text is `Read-only file system` (vm_check.py:108); the receipt records renet built, deployed and pointer all 0eaf033c5 with modified false; `renet sandbox-exec --detect` AVAILABLE (Landlock ABI 4).
    (ticked) 2026-10-20T15:40:10Z by d778be9d: commit:67c6bbef2 vmc-10201403-2d9ea5 V1.1-V1.4 ok: cross-repo chmod/touch refused read-only, own-mount writes and tools ok, /dev/shm isolated, cgroup named, Landlock ABI 4

## Follow-ups (worklist items to open, not in this plan)

- **Signals and abstract unix sockets between repos.** `private/renet/pkg/sandbox/landlock.go:31` calls `RestrictPaths`, which drops the scoped set (go-landlock v0.8.1 `landlock/config.go` lines 425-432), so `LANDLOCK_SCOPE_SIGNAL` and abstract-socket scoping are never applied even on ABI 6+.
- **ptys under the `/dev` rw grant.** Repo A can likely open B's `/dev/pts/N` (inferred); narrow `/dev` or give each session its own devpts.
- **SysV/POSIX IPC.** Shared by uid; consider `CLONE_NEWIPC`.
- **Hiding other repos' mounts** (option C) against `stat` and name leaks.
- **The Rediaccfile sandbox** (`private/renet/pkg/orchestration/rediaccfile.go:243`) runs without `--readonly-except` or `--require-landlock`; measure whether it has the same exposure.

## Risks

- **overlayfs upper on a read-only mount.** With the seal after the overlay, the upper is never read-only at mount time; S2's positive cases and V1 catch a kernel that re-checks it at write time.
- **The recursive bind copies docker's overlay2 mounts** into the namespace, as the transfer sandbox already does: O(mounts) per session, no correctness change.
- **The unprivileged overlay fallback** (`private/renet/cmd/renet/sandbox_overlay_linux.go:37-45`) errors instead of degrading under the view; the gateway always runs sandbox-exec as root.
- **E1 may find an OS without active Landlock.** S3 then waits for the operator.

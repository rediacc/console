# PLAN: per-repository resource limits (memory, CPU, I/O) and a renet-managed RAM volume

Status: approved -- operator order 2026-11-05 ("Follow-up: per-repo resource limits, and a renet-managed RAM volume"; "the new plan should be promoted and implemented on a new sub-agent via worktree"); hostinger modification and testing allowed without an ask-first step (operator 2026-11-05)
Priority: P1 -- the hostinger observability repo takes telemetry from the internet, and its OTLP credentials come from the unauthenticated GET /account/api/v1/telemetry/config. A flood, or any repo using too much RAM, can take down the host and every repo on it, because renet sets no memory, CPU or I/O limit on repo containers.
Owner: d778be9d
Updated: 2026-11-05
First-Seen: 2026-11-05
Depends-On: PLAN-renet-down-before-kill.md
Concurrency: parallel -- one writer in one worktree, box by box; the files shared with PLAN-renet-down-before-kill.md are listed under "Ordering"
Owns: private/renet/pkg/dockergrant/grant.go, private/renet/pkg/dockergrant/limits*.go, private/renet/cmd/renet/daemon_grant*.go, private/renet/pkg/repolimits/**, private/renet/pkg/ramvolume/**, private/renet/pkg/ebpf/lifecycle_cgroup*.go, private/renet/pkg/ebpf/manager.go, private/renet/pkg/ebpf/stub_other.go, private/renet/pkg/ebpf/repo_default_inspect.go, private/renet/pkg/repository/mount.go, private/renet/pkg/list/types.go, private/renet/pkg/list/repositories.go, private/renet/pkg/list/resources*.go, private/renet/pkg/functions/commands/repository.go, private/renet/pkg/functions/commands/repository_limits*.go, private/renet/pkg/license/tiermap.go, private/renet/cmd/renet/repository_fork.go, private/renet/docs/REPO_RESOURCES.md, packages/cli/src/commands/repo-policy.ts, packages/cli/src/commands/machine/status.ts, packages/cli/src/commands/__tests__/repo-policy-limits.test.ts, packages/cli/src/commands/machine/__tests__/status-resources.test.ts, packages/cli/src/i18n/locales/*/cli.json, packages/www/src/content/docs/*/repositories.md, .ci/rediacc_ci/drills/repo_resources.py, .ci/rediacc_ci/tests/test_drills_repo_resources.py, agent/plans/PLAN-repo-resource-limits.md
Live-Proof: hostinger -- the cgroup limits and the RAM volume are renet surface, and hostinger is the only live target. Box H2 runs there through --config eu-bench, on a test fork only; the observability original stays untouched.

## Ordering

Dependencies: PLAN-renet-down-before-kill.md, for the RAM-volume half only. The resource-limit half (R1-R5, K2) depends on nothing. M1 depends on nothing. M2 needs S1 (the docker unit stop side and unit_sides.go), S2 (the down marker) and S3 (rediacc-repo-shutdown.service and the `--all-mounted` sweep). The K3.6 reboot row needs K1 VERIFIED on the same tree. H2's RAM part needs H1 done.

Order and shared files: one writer in one worktree, box by box, in this order: R1, R2, R3, R4, R5, M1, M2, W2, K0b, then K2/K3 [fleet], H2, LP-hostinger. Some files belong to PLAN-renet-down-before-kill and are only shared here: private/renet/pkg/daemon/start_foreground.go (R2, M1), pkg/orchestration/workflows.go (R2, M1), pkg/orchestration/up_down_workflows.go and rediaccfile.go (R3, M1), cmd/renet/repository_reconcile*.go (R2), pkg/daemon/systemd.go and unit_sides*.go (M2), pkg/i18n/locales/** (every renet box), packages/shared/src/renet-contract/data/** (R4) and .ci/rediacc_ci/drills/vm_check.py (one EXTRA_RENET_STEPS line). A box that touches one of these rebases onto the other plan's landed boxes and adds code only through new helper calls, never by rewriting that plan's code. R2 lands after S3 and B1 if they are open when R2 starts. R3 lands after T1, S2 and B3. i18n keys are added by one writer at a time.

## The promise

1. A repo with a memory cap cannot take memory from the host or from other repos. When it reaches the cap, one of its own containers is OOM-killed, and nothing outside the repo is.
2. A repo can be given a RAM volume. Its contents survive a dockerd restart. A planned stop runs down() before the volume is removed. Its pages count against the repo's own cap.

## Why

- The repo containers' cgroup, /rediacc.slice/rediacc-<N>, has no memory.max, cpu.max or io.max (private/renet/pkg/daemon/systemd.go:664; no writer exists in pkg/ or cmd/). Today a single repo can push the whole host into a global OOM.
- Disk is already contained: each repo is a fixed-size LUKS image, and observability's is 16 GB. RAM, CPU and I/O are not contained.
- The observability data is planned to move into RAM (4-8 GB). Today it has no RAM disk to move into, nothing cleans one up in order, and its writes would not be charged to the repo.

## Decisions (lead, under the operator order; recorded for veto)

1. **Limits are an operator grant, not repo state.** They are stored in /etc/rediacc/grants/net-<N>.json (private/renet/pkg/dockergrant/grant.go:10-15) under `limits {memory_max, memory_high, cpu_max, io_max}` and `ram_volume {size}`. The size policy cannot hold them, because it is written into the volume (private/renet/cmd/renet/repository_policy.go:191-201), where the repo's containers can edit it. The grant file is root 0600, is masked in every sandbox, and is bound to the repo mount.
2. **The operator's command is kept.** `rdc repo policy set <ref> --memory-max 10G --memory-high 8G --cpu-max 4 --io-max rbps=200M,wbps=100M --ram-volume 8G`. `--clear-limits` removes the limits and `--force` allows a decrease below current use. The CLI sends the size flags to `repository_policy_set` as before. It sends the limit flags to the new functions `repository_limits_set` and `repository_limits_show`, which run `sudo renet daemon grant --network-id N ... --show`, the same way the gpu and permission functions do (private/renet/pkg/functions/commands/repository.go:384-445). `rdc repo policy get <ref>` adds a limits table. The machine-wide form (no ref, `-m`) refuses limit flags.
3. **Limits are written straight to cgroupfs.** rediacc-<N> is a plain directory, not a unit, so systemctl cannot set them. They are written in four places:
   - `StartForeground`, before containerd starts (private/renet/pkg/daemon/start_foreground.go, between Step 1b :166 and Step 2 :169). Restart-policy containers therefore start capped, including after a reboot.
   - SafeStartup, after step 3d (private/renet/pkg/orchestration/workflows.go:199), for the service-directory settings and the io device.
   - `renet daemon grant`, as soon as the grant changes, with no restart.
   - every `repository reconcile` tick, which writes them again so drift heals.
   Controllers are enabled with the existing `propagateSubtreeControllers` (private/renet/pkg/ebpf/manager.go:395-452). The limits survive a dockerd restart, because rediacc-<N> outlives dockerd.
4. **Values.**
   - memory.max and memory.high take size strings.
   - `--cpu-max` takes cores (`4` or `2.5`), written as `<cores*100000> 100000`. It also accepts `N%`, the systemd CPUQuota form that backup already uses (private/renet/cmd/renet/backup_snapshot.go:311).
   - `--io-max` takes `rbps=,wbps=,riops=,wiops=`, any subset. It is written for the repo's device-mapper device. The major:minor is looked up on every apply, because it changes on every mount.
   - `max` removes a single value.
5. **Defaults: none.** A default cap rolled out onto running repos can OOM them. There is no aggregate cap on rediacc.slice: an OOM there kills the largest task across all repos, which breaks isolation between repos. `machine status` marks every repo that has no memory.max.
6. **Changes apply live, with one guard.** Writing memory.max below memory.current is refused unless `--force` is given, and the refusal names the current usage. memory.high has no such guard.
7. **OOM scope.** rediacc-<N> keeps memory.oom.group=0. Each service directory rediacc-<N>/<svc> gets memory.oom.group=1. When the repo reaches its cap, the kernel picks the largest task inside rediacc-<N> and kills the whole container it belongs to, not the whole repo. A memcg OOM never chooses a task outside that memcg. `memory.events` counts oom_kill for the whole subtree.
8. **Forks inherit limits.** Device and lifecycle grants are not inherited, but limits are: `repo fork` copies the parent's `limits` and `ram_volume` into the fork's grant (cmd/renet/repository_fork.go `forkDockerRepo`, :199-250). A fork of a capped repo must not run uncapped. If the fork's network ID is unknown, the copy is skipped and a warning is logged.
9. **Who may set limits.** Anyone who runs `sudo renet` on the machine, that is, the operator through the CLI. The repo itself (its Rediaccfile, containers and terminal sessions) cannot read or write the grant. When an agent changes the limits of a grand repo, it must pass the ancestry check that `repo permission grant --path` uses (packages/cli/src/commands/repo-permission.ts:48-80). Forks are not checked. Tiers: `repository_limits_set` is TierRepoLicenseOperate and `repository_limits_show` is TierNone.
10. **up() and down() run inside the repo cgroup.** They move to a leaf, /rediacc.slice/rediacc-<N>/@lifecycle. The leaf is created whether or not eBPF is available; when it is, the leaf gets the exec-style map entry. A compose service name cannot contain `@`, so the leaf never collides with a service directory. Effects:
    - A restore written into the RAM volume is charged to the repo.
    - A Rediaccfile cannot run outside the cap.
    - The BPF walk matches the deepest entry first (private/renet/pkg/ebpf/socket_isolation.c:45-82), so the exec-style policy still applies.
    - dockerproxy already maps every path under rediacc-<N> to network N (private/renet/pkg/dockerproxy/peer.go:41-63).
    - SafeShutdown kills whatever up() or down() left in @lifecycle (cgroup.kill), after down() returns.
    - Terminal and VS Code sessions stay in renet-exec-<N> (see open question 3).
11. **RAM volume mount.** `ramvolume.Ensure` mounts a tmpfs at `<mount>/.ram` in the host namespace with `size=<granted>,mode=0770,uid=gid=<RediaccUser>`, and `noswap` where the kernel supports it (6.4 or later). It is idempotent:
    - A size change remounts with the new `size=`.
    - A shrink below current use is refused.
    - A `.ram` directory that is not empty on disk refuses the mount, and `repo up` fails and names it.
    It is called from SafeStartup (a new step 2c, after the mount check at private/renet/pkg/orchestration/workflows.go:93-96 and before dockerd starts at step 3b) and from StartForeground (before the sandbox is built). It writes a root-owned marker, `.ram/.rediacc-ram`, containing `{boot_id, mounted_at, size}`. up() and down() get `REDIACC_RAM_DIR` only while the volume is mounted. Revoking the grant takes effect at the next unmount.
12. **RAM volume removal.** The volume is unmounted in one place: `Repository.Unmount`, just before `Storage.Unmount` (private/renet/pkg/repository/mount.go:262-263). That function is the single point used by SafeShutdown, UnmountWithDocker, the shutdown sweep, resize and delete. The unmount is refused while rediacc-docker-<N> is active. After M2 it is also refused, unless `--force` is given, when the volume holds data and there is no current down marker. The docker unit's stop side gains `After=<systemd-escaped <mount>/.ram>.mount`, so systemd never unmounts the volume at shutdown before dockerd and down() have finished. Without that line, down() could save an empty directory over the good copy. The order is: down() saves, dockerd stops, `.ram` is unmounted, the repo is unmounted, LUKS is closed.
13. **Charging and sizing.**
    - Pages are charged to the cgroup that first writes them. Container writes land under rediacc-<N>/<svc>/…; restore writes land in @lifecycle.
    - When a cgroup is removed, its charges move to its parent and stay inside rediacc-<N>. rediacc-<N> is removed only at repo delete, after the unmount.
    - An OOM kill never frees tmpfs pages, so a volume close to memory.max would OOM-kill containers in a loop. The grant therefore refuses memory.max below RAM size + 1 GiB when both are set.
    - Without memory.max, `size=` alone bounds the volume.

## Loss model of the RAM volume

| Event | What is lost |
| --- | --- |
| dockerd restart (any path, including `systemctl restart rediacc-docker-<N>`) | nothing; the tmpfs is a host mount |
| container OOM kill | nothing |
| `repo down --unmount`, `repo unmount`, planned reboot | whatever down() does not save; down() runs before the unmount (Decision 12; the stop hook and sweep of PLAN-renet-down-before-kill) |
| down() timeout during host shutdown | whatever down() had not saved yet (that plan's documented exception) |
| crash, power loss, unplanned reboot | everything since the last down(), or since the last flush by `backup_prepare` |
| backup snapshot, fork | `.ram` is not in the LUKS image; the fork's up() restores from the parent's last down() save |

## Tasks

### Resource limits (independent of any other plan)

- [x] R1 [renet] Grant schema and the `daemon grant` flags, per Decisions 1, 4, 9 and 13.
  - pkg/dockergrant/limits.go defines `Limits{MemoryMax, MemoryHigh, CPUMax, IOMax}` and `RAMVolume{Size}`, with parse and validate functions. It enforces memory.max ≥ RAM size + 1 GiB.
  - Both fields are added to `Grant` (private/renet/pkg/dockergrant/grant.go:117-146) and to `Empty()` (:159-162).
  - `createDaemonGrantCmd` (private/renet/cmd/renet/daemon_grant.go:56-77) gains `--memory-max`, `--memory-high`, `--cpu-max`, `--io-max`, `--ram-volume`, `--clear-limits` and `--force`. `--show` prints `limits` and `ram_volume`.
  - Accept: `cd private/renet && go test ./pkg/dockergrant/... ./cmd/renet/ -run 'Limits|RAMVolume|DaemonGrant' -count=1` rc 0 and `npm run check:ci-renet` rc 0. The tests cover a limits-only grant that survives a write, the RAM-versus-memory refusal, and `--cpu-max 2.5` stored as `250000 100000`.
  - CONTROL: `TestGrantLimitsOnlyIsKept` fails on today's tree, because `Empty()` ignores the field and the file is removed (private/renet/pkg/dockergrant/grant.go:490-493). `TestDaemonGrantMemoryMaxFlag` fails too, because the flag does not exist.
    (ticked) 2026-11-06T00:23:22Z by d778be9d: commit:3ef7cdd22 (renet 67e2d5f); go test ./pkg/dockergrant/... ./cmd/renet/ -run Limits|RAMVolume|DaemonGrant rc=0; check:ci-renet rc=0
- [x] R2 [renet] pkg/repolimits applies the limits, per Decisions 3, 5, 6 and 7.
  - `Apply(root, netID, grant, dev)` writes memory.max, memory.high, cpu.max and io.max on rediacc-<N>, and memory.oom.group=1 on every existing service directory. Its cgroupfs root is a parameter, so tests run against a temp dir.
  - It is called from StartForeground before Step 2, from SafeStartup after step 3d, from `daemon grant` after a write (live; a decrease below memory.current is refused without `--force`), and from each `repository reconcile` run, for every mounted repo with a grant.
  - The out-of-date comment at private/renet/pkg/daemon/systemd.go:539-549 is corrected.
  - Accept: `cd private/renet && go test ./pkg/repolimits/... ./pkg/daemon/... ./pkg/orchestration/... ./cmd/renet/ -run 'RepoLimits|ApplyLimits|ReconcileLimits|StartForegroundLimits' -count=1` rc 0 and `npm run check:ci-renet` rc 0.
  - CONTROL: `TestStartForegroundAppliesLimitsBeforeContainerd` records no memory.max write before the containerd spawn on today's StartForeground.
    (ticked) 2026-11-06T00:23:23Z by d778be9d: commit:3ef7cdd22 (renet 53dd2f2); go test repolimits/daemon/orchestration/cmd -run RepoLimits|ApplyLimits|ReconcileLimits|StartForegroundLimits rc=0; check:ci-renet rc=0
- [x] R3 [renet] The lifecycle leaf cgroup, per Decision 10. `OpenLifecycleCgroupFD(netID, alias)` lives in pkg/ebpf/lifecycle_cgroup.go, with a stub in stub_other.go. It creates rediacc-<N>/@lifecycle, writes the exec-style entry when the manager exists, and returns an FD. UpServices uses it in place of `OpenExecCgroupFD` (private/renet/pkg/orchestration/up_down_workflows.go:217-228). DownServices sets it as well (:367-369). SafeShutdown step 0 writes `cgroup.kill` on @lifecycle after down(). `repo_default_inspect.go` reports @lifecycle as the repo's lifecycle cgroup.
  - Accept: `cd private/renet && go test ./pkg/ebpf/... ./pkg/orchestration/... ./pkg/dockerproxy/... -run 'Lifecycle|NetworkOfCgroup|SafeShutdown' -count=1` rc 0 and `npm run check:ci-renet` rc 0. The tests check that the executor's FD path lies under `RepoCgroupPath(N)` for both up() and down(), and that `networkOfCgroup("/rediacc.slice/rediacc-7/@lifecycle") == 7`.
  - CONTROL: `TestUpCgroupUnderRepoCgroup` fails on today's tree, because the path is /rediacc.slice/renet-exec-<N> (private/renet/pkg/ebpf/manager.go:270-273), and `TestDownHasCgroupFD` fails as well.
    (ticked) 2026-11-06T00:23:25Z by d778be9d: commit:3ef7cdd22 (renet c123f8d); go test ./pkg/ebpf/... ./pkg/orchestration/... ./pkg/dockerproxy/... -run Lifecycle|NetworkOfCgroup|SafeShutdown rc=0; check:ci-renet rc=0
- [x] R4 [renet] Functions, tier, fork inheritance and status data, per Decisions 2, 8 and 9.
  - `repository_limits_set` and `repository_limits_show` (requirements `destTypeMachine, paramTeam, catRepository`) are defined and built as `renet daemon grant --network-id N ... --show`.
  - Their tier entries go in private/renet/pkg/license/tiermap.go.
  - `forkDockerRepo` copies `limits` and `ram_volume` into the fork's grant.
  - `RepositoryInfo` (private/renet/pkg/list/types.go:261) gains `resources` with: memory current, max and high; oom_kill from memory.events; cpu.max and usage_usec; io.max; ram used and size from statfs of `.ram`. The data is gathered in pkg/list/resources.go.
  - The contract is regenerated into packages/shared/src/renet-contract/data/.
  - Accept: `cd private/renet && go test ./pkg/functions/... ./pkg/license/... ./pkg/list/... ./cmd/renet/ -run 'Limits|Resources|Tier|ForkLimits' -count=1` rc 0 and `npm run check:ci-renet` rc 0.
  - CONTROL: `TestForkCopiesLimits` fails on today's `forkDockerRepo`, which writes no grant.
    (ticked) 2026-11-06T00:23:28Z by d778be9d: commit:3ef7cdd22 (renet 374272d) commit:3a5d92be8; go test functions/license/list/cmd -run Limits|Resources|Tier|ForkLimits rc=0; check:ci-renet rc=0
- [x] R5 [console] The CLI surface, per Decisions 2, 5 and 9.
  - packages/cli/src/commands/repo-policy.ts gains the limit flags. They are routed to `repository_limits_set` through `executeRepoFunction`. `policy get <ref>` adds the limits table. A limit flag without a ref is refused. The agent ancestry guard applies to grand repos.
  - `machine status` (packages/cli/src/commands/machine/status.ts:182-184, :576) gains memory (current / max), oom_kills and ram (used / size), and marks repos that have no memory.max.
  - Locale keys are added in every language.
  - Accept: `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0; `cd packages/cli && npx vitest run src/commands/__tests__/repo-policy-limits.test.ts src/commands/machine` rc 0; `npm run check:i18n` rc 0; `npm run check:ci-cli-contract` rc 0.
  - CONTROL: `rdc repo policy set x --memory-max 1G` exits with commander's unknown-option error on today's tree. The new test asserts that it is accepted and routed.
    (ticked) 2026-11-06T00:23:29Z by d778be9d: commit:8a05322a9 commit:21fb3af37; tsc rc=0; vitest repo-policy-limits.test.ts src/commands/machine rc=0; check:i18n rc=0; check:ci-cli-contract rc=0

### RAM volume (M1 independent; M2 after S1, S2 and S3 of PLAN-renet-down-before-kill)

- [x] M1 [renet] pkg/ramvolume and its lifecycle, per Decisions 11, 12 and 13.
  - pkg/ramvolume provides `Ensure`, `Unmount` and `Usage`, with the mount syscalls behind a seam. Ensure uses `noswap` when the kernel supports it and remounts on a size change.
  - Ensure is called at SafeStartup step 2c and in StartForeground before the sandbox.
  - `Repository.Unmount` (private/renet/pkg/repository/mount.go:262) unmounts `.ram` first, and refuses while the docker unit is active unless forced.
  - `REDIACC_RAM_DIR` is exported to up() and down().
  - A dockerpolicy test pins that a bind of `<mount>/.ram/data` is allowed.
  - Accept: `cd private/renet && go test ./pkg/ramvolume/... ./pkg/repository/... ./pkg/orchestration/... ./pkg/daemon/... ./pkg/dockerpolicy/... -run 'RamVolume|UnmountOrder|RamBind' -count=1` rc 0 and `npm run check:ci-renet` rc 0. Order test: `ramUnmount < storageUnmount`. Other tests: a non-empty `.ram` refuses; an active docker unit refuses; a size change remounts and does not unmount.
  - CONTROL: `TestUnmountRemovesRamVolumeFirst` records `Storage.Unmount` with no submount step on today's `Repository.Unmount`.
    (ticked) 2026-11-06T00:23:30Z by d778be9d: commit:3ef7cdd22 (renet 3ca1a70); go test ramvolume/repository/orchestration/daemon/dockerpolicy -run RamVolume|UnmountOrder|RamBind rc=0; check:ci-renet rc=0
- [ ] M2 [renet] The RAM volume in the shutdown order, after S1, S2 and S3.
  - `renderDockerUnit`'s stop side (S1's unit_sides.go) gains `After=<escaped mount>-.ram.mount`. The line is always present, because ordering against a missing unit does nothing, and it changes only the stop side, so it causes a reload and no restart.
  - `ramvolume.Unmount` refuses when the volume holds data and S2's down marker is not current, unless forced.
  - A test drives S3's `autostart stop --all-mounted` through a fake and records `down < dockerStop < ramUnmount < repoUnmount`.
  - Accept: `cd private/renet && go test ./pkg/daemon/... ./pkg/ramvolume/... ./cmd/renet/ -run 'SystemdDockerUnit|RamVolumeMarker|AllMountedRamOrder' -count=1` rc 0 and `npm run check:ci-renet` rc 0.
  - CONTROL: the updated `TestSystemdDockerUnitGolden` fails against S1's golden, which has no `.ram` line.

### Docs

- [x] W2 [docs] private/renet/docs/REPO_RESOURCES.md (new) and the limits and RAM-volume section of packages/www/src/content/docs/*/repositories.md with its translations. They cover the flags, the grant and who may set it, OOM scope, fork inheritance, the loss model table, and the up()/down() restore-and-save pattern (restore only when `$REDIACC_RAM_DIR/.restored` is missing).
  - Accept: `npm run check:i18n`, `npm run check:ci-i18n-docs-untranslated`, `npm run check:ci-docs-structure-parity` and `npm run check:ci-prose-style` rc 0.
  - CONTROL: none -- docs.
    (ticked) 2026-11-06T00:23:32Z by d778be9d: commit:3ef7cdd22 (renet 73e0aff) commit:ab266526d; check:i18n, check:ci-i18n-docs-untranslated, check:ci-docs-structure-parity, check:ci-prose-style rc=0

### Drill

- [x] K0b [drill code] `.ci/rediacc_ci/drills/repo_resources.py`, with steps K2 and K3 added to `EXTRA_RENET_STEPS` (.ci/rediacc_ci/drills/vm_check.py:269-276), both depending on P5. The pure parsers and verdicts (memory.events, /proc/vmstat, findmnt, statfs) are pinned by `.ci/rediacc_ci/tests/test_drills_repo_resources.py`.
  - K2 rows (limits):
    - K2.0: fork C (`--memory-max 1G --cpu-max 1`) and fork D (no limits) are up on the worker.
    - K2.1: rediacc-<C> has memory.max 1073741824 and cpu.max `100000 100000`, and every service directory has memory.oom.group 1. rediacc-<D> has memory.max `max`.
    - K2.2: C's service `alloc` runs `head -c 2147483648 /dev/zero | tail`. Then: C's memory.events oom_kill rises by at least 1; D's stays the same; the host's /proc/vmstat oom_kill delta equals C's; C's other containers and every D container keep their StartedAt; sshd answers.
    - K2.3: `rdc repo policy set C --memory-max 1536M` changes memory.max, and the MainPID and container start times stay the same.
    - K2.4: `--memory-max 16M` without `--force` is refused, with a non-zero rc.
    - K2.5: `systemctl daemon-reload` and a restart of an unrelated unit leave memory.max in place. After `systemctl restart rediacc-docker-<C>` it is still in place.
    - K2.6: a fork of C inherits memory.max.
  - K3 rows (RAM volume):
    - K3.0: fork E (`--ram-volume 512M --memory-max 1G`) is up. The probe up() logs `findmnt <mount>/.ram`.
    - K3.1: the tmpfs exists, with size 512M, before up() runs.
    - K3.2: a container writes `marker` into `.ram/data` through a bind. This also tests verification row 13.
    - K3.3: up() restores 200 MB into `.ram`. The `shmem` in rediacc-<E>'s memory.stat grows by at least 200 MB; renet-exec-<E> and rediacc.slice outside E do not grow.
    - K3.4: `systemctl restart rediacc-docker-<E>` keeps `marker`.
    - K3.5: `rdc repo down E --unmount` logs a down() line while `.ram` is still mounted, and afterwards findmnt shows no `.ram`. After `rdc repo up E`, `marker` is gone and `.rediacc-ram` has a new mounted_at.
    - K3.6 (needs K1 VERIFIED): reboot. The data saved by down() is restored by up().
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_drills_repo_resources.py -q` rc 0 (toolchain pytest).
  - CONTROL: the verdict test feeds an oom_kill delta that appears in D and expects FAIL. It also feeds a findmnt listing with `.ram` mounted after the unmount and expects FAIL.
    (ticked) 2026-11-06T00:23:33Z by d778be9d: commit:e17477770; test_drills_repo_resources.py 11 passed rc=0
- [ ] K2 [fleet] The K2 rows on the local KVM fleet (192.168.111.*).
  - Accept: `npm run vm:check -- --changed` VERIFIED with every K2 row ok.
  - CONTROL: `npm run vm:check -- --only K2` with the renet pointer at the main commit records FAIL on K2.1 and K2.2 (no cap; the alloc container is not OOM-killed). Quote both rows in the tick.
- [ ] K3 [fleet] The K3 rows, after M2 and K1 VERIFIED.
  - Accept: `npm run vm:check -- --changed` VERIFIED with every K3 row ok.
  - CONTROL: `npm run vm:check -- --only K3` at main records FAIL on K3.1 (no tmpfs).

### Hostinger (no ask needed; the observability original stays untouched)

- [ ] H2 [hostinger] The K2 and K3 proofs on a test fork, after K2 and K3 are VERIFIED on the same tree (and H1 done, for the RAM part).
  - Before: snapshot `./rdc.sh --config eu-bench repo list -m hostinger -o json`, `./rdc.sh --config eu-bench backup usage`, the MainPID and container start times of every rediacc-docker unit, /proc/vmstat oom_kill, and memory.max of every rediacc-<N>.
  - Fork `demo-heartbeat` with `--tag limits`. Upload a compose with an `alloc` service and the probe Rediaccfile with `repo sync upload`. Then run `rdc repo policy set <fork> --memory-max 1G --ram-volume 256M` and `repo up`.
  - Proofs:
    - (a) After provisioning and one reconcile tick, every original still has memory.max `max` and an unchanged MainPID.
    - (b) Only the fork's oom_kill rises, and the host's /proc/vmstat delta equals the fork's.
    - (c) `marker` survives `sudo systemctl restart rediacc-docker-<fork N>` and is gone after `repo down --unmount` followed by `repo up`.
    - (d) `rdc machine status hostinger` shows the fork's limits and usage.
  - After: repeat the snapshot. Everything matches except the fork. Run `repo delete <fork> --dry-run`, read that it names only the fork, then run it with `-y`. No reboot of hostinger.
  - Accept: a tick that quotes the before and after snapshots and the fork's memory.events.
  - CONTROL: before provisioning, `alloc` in the fork reaches 2 GB with no OOM kill. Record that run first.
- [ ] LP-hostinger [live] A fresh hostinger receipt after a VERIFIED `npm run vm:check -- --changed` on the same tree.
  - Accept: `live-proof hostinger renet-live`

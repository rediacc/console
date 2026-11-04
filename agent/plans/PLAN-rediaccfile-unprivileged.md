# PLAN: Rediaccfile up() and down() run as the universal user, and a repository gets more only by an operator's grant

Status: executing -- operator rulings 2026-11-03, below
Depends-On: no-dep -- the hook fix (renet 41554f4) has landed; this plan narrows the sandbox the hook shares
Owner: d778be9d (adopted from 45048a90 2026-11-04)
Updated: 2026-11-04
First-Seen: 2026-11-02
Priority: P0 -- tenant code runs as root on a shared machine. Confirmed for hooks; P0 proves it for up() and down()
Concurrency: parallel -- one writer works U1 to U5 in order, since they edit one call path, and it runs in a lease, so another plan's writer cannot touch its tree; an Owns overlap is still judged at spawn
Owns: private/renet/pkg/sandbox/**, private/renet/cmd/renet/sandbox_exec.go, private/renet/cmd/renet/sandbox_groups.go, private/renet/cmd/renet/sandbox_overlay_linux.go, private/renet/cmd/renet/daemon_grant*.go, private/renet/cmd/renet/daemon_containerd_exec.go, private/renet/cmd/renet/main.go, private/renet/cmd/renet/backup_snapshot_cold.go, private/renet/cmd/renet/backup_sync_cold.go, private/renet/pkg/orchestration/**, private/renet/pkg/backuphook/**, private/renet/pkg/dockergrant/**, private/renet/pkg/compose/exec.go, private/renet/pkg/compose/wrapper.go, private/renet/pkg/gpu/cdi*.go, private/renet/pkg/rediaccfile/**, private/renet/pkg/convergeguard/**, private/renet/pkg/reporuntime/kube*.go, private/renet/pkg/reporuntime/docker.go, private/renet/pkg/functions/commands/repository.go, private/renet/pkg/license/tiermap.go, private/renet/pkg/i18n/**, private/renet/docs/DOCKERD_SANDBOX.md, packages/cli/src/commands/repo-permission.ts, packages/cli/src/commands/repo.ts, packages/cli/src/i18n/locales/*/cli.json, packages/shared/src/renet-contract/data/**, packages/json/templates/networking/cloud-switch/Rediaccfile, packages/json/templates/databases/solr/Rediaccfile, .ci/tutorials/apps/demo-pgadmin/**, packages/www/src/content/docs/*/rediaccfile*.md, packages/www/src/content/docs/*/gpu.md, .ci/rediacc_ci/drills/lifecycle_privilege.py, .ci/rediacc_ci/drills/vm_check.py, packages/e2e-tests/tests/05-rediaccfiles-updown.test.ts, agent/plans/PLAN-rediaccfile-unprivileged.md
Live-Proof: bench, hostinger -- renet sandbox and grant code is the renet surface (hostinger only); the regenerated contract is the account surface (bench); the new CLI verb is the cli surface, which both admit.

## Operator rulings

ASKED:2026-11-03 "Fix it in #602 but test with hostinger machine repos. Don't forget about gpu usage since /dev access may require root. Maybe we should make it adaptive with explicit user permissions?"

ASKED:2026-11-03, on the recommended options: a root tier exists, explicit per repo. A Rediaccfile may declare what it needs, as a request only. A machine without Landlock refuses up() and down().

ASKED:2026-11-03, on forks of mail and mautic: "Directly test with latest tag. No need for forks. Don't forget to check the containers after calling the up from rdc".

Standing, 2026-11-01: never delete, prune, replace or down an original repo on hostinger.

## Findings

Read from code. P0 and P1 prove the ones marked to measure.

### 1. What root does in up() and down() today

| Step | Runs as | Needs root? | Evidence |
| --- | --- | --- | --- |
| Mount, daemon start, `.rediacc.json`, eBPF preseed, `.envrc`, docker config dir | renet, before the sandbox | Yes, and unchanged | private/renet/pkg/orchestration/up_down_workflows.go:126, :194, :203; private/renet/pkg/orchestration/rediaccfile.go:167 |
| Cgroup placement | renet (fd) | Yes, unchanged | private/renet/pkg/orchestration/up_down_workflows.go:168-172; down() stays outside it (:399) |
| Sandbox workspace and mounts | `sandbox-exec`, before the drop | Yes, unchanged | private/renet/cmd/renet/sandbox_exec.go:127, :149, :324 |
| `bash` running `up` | root: `buildSandboxOptions` never sets `RunAs` | **No** | private/renet/pkg/orchestration/up_down_workflows.go:486-513 |
| `renet compose` in up() | root, inside up's Landlock. It never re-wraps because `setIdentityEnv` sets `REDIACC_REPOSITORY` | **No**: the shell path already runs it non-root | private/renet/pkg/compose/exec.go:365; private/renet/pkg/orchestration/up_down_workflows.go:304. The comment at private/renet/cmd/renet/main.go:1126-1130 is wrong for this path |
| Loopback aliases | `sudo ip addr add`, only warns on failure | **No**: all of 1-62 exist since mount | private/renet/pkg/compose/exec.go:61-64; private/renet/pkg/daemon/loopback.go:43 |
| Docker API | root via the socket | **No**: the group is handled | private/renet/cmd/renet/sandbox_groups.go:33-64 |
| Files `up` creates (`.env` in app-postgres) | root, then chowned back | **No**: the universal user creates them directly | packages/cli/templates/app-postgres/Rediaccfile:7-13; private/renet/pkg/orchestration/up_down_workflows.go:266 |
| `chown <uid>` of repo data | root | **Yes**, the one real need in the tree; use a container instead | .ci/tutorials/apps/demo-pgadmin/Rediaccfile:66; solr:11 (has a chmod fallback) |
| `sudo sysctl -w` | root | To measure: `/proc` is read-only to Landlock, so this already fails and bash continues | packages/json/templates/networking/cloud-switch/Rediaccfile:7-8; private/renet/pkg/orchestration/up_down_workflows.go:497 |
| `rediacc.install_as=systemd` | not done in up(); `sudo renet hub install` is separate | No | private/renet/pkg/compose/wrapper.go:562-564 |

Root's reach goes beyond reads. CapEff is full, so `iptables`, signals and module loading are all candidates. P0 records CapEff rather than assuming.

### 2. Traps the drop would spring. Each one needs a box.

- **F1. `sudo` is one failed Landlock call from root.** Setup writes `rediacc ALL=(ALL) NOPASSWD: ALL` (private/renet/cmd/renet/setup_command.go:853-854). Only `PR_SET_NO_NEW_PRIVS` stops it, and Landlock sets that. Without Landlock, `up` continues unconfined (private/renet/cmd/renet/sandbox_exec.go:307-314), so the drop is reversible by `sudo`.
- **F2. Compose failures would be lost silently.** `newComposeStatusFile` creates a root-owned 0600 file in host `/tmp` (private/renet/pkg/orchestration/compose_status.go:74-85). After the drop `RecordComposeFailure` gets EACCES. To measure: the `/tmp` bind (private/renet/cmd/renet/sandbox_exec.go:357-361) may already hide the file, which would make `ENOENT -> nil` (private/renet/pkg/orchestration/compose_status.go:58-62) a live bug that swallows failures today.
- **F3. GPU and bind-root repos would fail at compose.** `applyComposeDelegations` reads `/etc/rediacc/grants/net-<N>.json`, in a 0700 directory. On EPERM it validates with no grant (private/renet/cmd/renet/daemon_grant.go:341-343), so the validator refuses a granted device the gate would admit. The `renet compose` a shell session runs has this bug already.
- **F4. Secrets.** Env-mode secrets arrive as `REDIACC_SECRET_<NAME>` through the parent's environment (private/renet/cmd/renet/repository_up.go:79-80), so a built environment must pass that prefix. File-mode secrets sit under a root 0700 directory (private/renet/pkg/orchestration/secret_files.go:96-101), so an up() that reads them directly stops working after the drop. To measure: whether compose alone needs that read.
- **F5. Landlock doesn't mediate chmod, chown or utimes, and the universal user owns every repo.** A dropped up() could `chmod -R 000` another repo's mount. Sessions close this with the read-only view (private/renet/cmd/renet/sandbox_gateway.go:235-240). The hook has the same hole today.
- **F6. `HOME`.** `dropPrivileges` forces `/home/rediacc` (private/renet/cmd/renet/sandbox_overlay_linux.go:217), which `buildSandboxOptions` doesn't grant. Sessions use a per-repo overlay (private/renet/cmd/renet/sandbox_gateway.go:267).
- **F7. Narrowing `/dev` must name `/dev/shm`.** It is a bind of `<sandbox>/shm` (private/renet/cmd/renet/sandbox_exec.go:360), and Landlock walks mount parents, so the `sandboxDir` rule doesn't cover it.
- **F8. Masking `/etc/rediacc` hides `router.env`.** `GetProxyBaseDomain` then silently returns `example.com` (private/renet/pkg/compose/output.go:22-25). That file holds only BASE_DOMAIN, MACHINE_NAME, TEAM_NAME and PORT (private/renet/pkg/proxy/infra.go:152-156), so a one-file read grant is safe.
- **F9. `down` with no daemon.** A missing socket makes `sandboxGroups` return an error (private/renet/cmd/renet/sandbox_groups.go:53-56), so `sandbox-exec` refuses before down() runs. `repo down` must not turn that into a stuck repo. A pre-epoch-2 socket is refused the same way and named for `rdc machine converge` (:57-59), which is correct.
- **F10. `--owner`.** `UpOptions.Owner` (private/renet/pkg/orchestration/up_down_workflows.go:54, private/renet/cmd/renet/repository_up.go:70) can leave the mount root unwritable to the universal user.
- **F11. Old root-owned state.** Earlier root ups left dirs that a non-root `ensureBuildxDir` can't heal (private/renet/pkg/compose/exec.go:328). The post-up chown skips top-level `.rediacc/` (private/renet/pkg/filesystem/permissions.go:236-239), so it needs a pre-up run too.
- **F12. Environment.** `SetCleanEnvironment` has one caller (private/renet/pkg/backuphook/hook.go:398). Cold barriers call `UpServices` and `DownServices` (private/renet/cmd/renet/backup_sync_cold.go:121, :242), so unit credentials may reach up() by inheritance. To measure in P1.
- **F13. Env not set.** `REDIACC_IMMOVABLE` is read by compose (private/renet/cmd/renet/main.go:1094, :1007) but `setIdentityEnv` doesn't set it (private/renet/pkg/orchestration/up_down_workflows.go:301-311). It only appears when a Rediaccfile sources `.envrc`.
- **F14. The kube arm has no sandbox at all.** Its executor never calls `SetSandboxOptions` (private/renet/pkg/reporuntime/kube.go:641, :220), so up() runs as root and unconfined. `DockerRuntime` has the same gap (private/renet/pkg/reporuntime/docker.go:416) for `Deploy` and `health()` (:335).

### 3. GPU: what touches /dev

| Step in a GPU repo's up() | Goes through | Host /dev from up()? |
| --- | --- | --- |
| `renet compose` with `devices: [nvidia.com/gpu=all]` | dockerd via the gate; only F3 breaks it | No |
| `docker run --device <cdi>` | dockerd; the socket group is enough (PLAN-gpu-device-grants W1, G1) | No |
| CDI hooks | runc under dockerd | No |
| `nvidia-smi` directly in the Rediaccfile | the process itself | **Yes** |

- No template uses a GPU: `nvidia|gpus|cdi` has no hits under `packages/json/templates`.
- `nvidia-smi` as non-root needs a Landlock grant for `/dev/nvidia*`, plus `/proc/driver/nvidia` and `/sys` (already read-only). `/dev/nvidia*` is normally 0666, so no group is needed. That is the driver default and isn't measured here, since no native NVIDIA machine exists. `/dev/dxg` is measured as `crw-rw-rw-` on the WSL host.
- `/dev/dri/renderD*` and `/dev/kfd` are normally `root:render 0660`, so they also need the node's group.
- `specFile` in private/renet/pkg/gpu/cdi.go:135-140 parses device names only. Reading node paths is new work (U5).

### 4. Other callers

- Everything converges on `UpServices`/`DownServices`: private/renet/cmd/renet/repository_up.go:233, private/renet/cmd/renet/repository_up_all.go:401, private/renet/cmd/renet/repository_down.go:116, private/renet/cmd/renet/repository_down_all.go:127, private/renet/cmd/renet/repository_fork.go:499, private/renet/cmd/renet/repository_autostart.go:207 (reconcile through `recoverRepository`), private/renet/cmd/renet/backup_sync_cold.go:121, :242. One default therefore covers them all.
- A dropped up() that fails under autostart or reconcile surfaces through back-off and `/var/lib/rediacc/reconcile/failed/<guid>`, so the failure message must reach the journal.
- `info()`: templates define it, and no `ExecuteFunction` in private/renet calls it (only up, down, health and the backup functions). `renet dev up` (private/renet/cmd/renet/dev_up.go:76) is already non-root inside the sandbox.
- Hub and systemd-installed repos: installed by a separate root command, and reconcile skips them when mounted.
- Templates: of 33 Rediaccfiles outside caches, the root-dependent lines are the three in the table above. Plain `chmod` works once the universal user owns the file; it fails on data dirs owned by a container uid, which H2 tests.
- e2e 05, 07, 13, 28, 30: a pattern grep finds only bridge-side `sudo` (28:85, 30:94-115) and in-container commands (07:188), so no root dependency in a Rediaccfile. T2 confirms it by running them.

## Design

**Default for up() and down(), with no grant.** One function, `lifecycleOptions`, used by both workflows:
- `RunAs` = `config.RediaccUser` when euid is 0, dropped after Landlock. A failed drop doesn't run the function.
- NNP set unconditionally before the drop (F1), and Landlock required, per the ruling.
- Read-only view, excepting the mount, immovable, sandbox dir, home, `/tmp` and `/dev/shm` (F5).
- Home overlay, as sessions have (F6).
- `/etc`: `etcReadOnlyView` moved to pkg/sandbox, with no `/etc/rediacc` beyond the file `router.env` (F8) and the network's own `docker-<N>`. `backup-*.env` is out by Landlock as well as DAC.
- `/proc`: read-only stays. Measure whether a narrower list works; as non-root, kcore and other users' `environ` already fail on DAC and the ptrace rule.
- `/dev`: replace the read-write grant with exactly `null zero full random urandom tty ptmx pts shm fd stdin stdout stderr`, each existing path as a file or dir rule. No block devices.
- Environment: built, as in `BuildEnv`, with `PATH`, `LANG`, the identity set, `REDIACC_IMMOVABLE`, `REDIACC_COMPOSE_DETACH`, the service IPs, Docker vars, and passing only the prefix `REDIACC_SECRET_`.

**Grants: operator-only, machine-side, in the existing file.** `dockergrant.Grant` gains `Lifecycle{Root bool, Paths []BindRoot}`, plus a derived device view. `/etc/rediacc/grants/net-<N>.json` already has what this needs: root-owned 0600 in a 0700 directory, bound to `RepoMountPath`, a fork has a new network id so it starts with nothing, a reused id discards it (private/renet/pkg/dockergrant/grant.go:426), an audit line per change, and it fails closed on read (private/renet/pkg/dockergrant/grant.go:383-393).

Flags on `sudo renet daemon grant`: `--lifecycle-root=true|false`, `--lifecycle-path PATH[:ro|:rw]`, `--revoke-lifecycle-path`.

| Tier | Grant | Effect on up/down |
| --- | --- | --- |
| Default | none | As above |
| Device | the existing `--device <cdi>` | Each CDI node of a granted name is added to Landlock; its group is added when the mode needs one. No second flag: the repo was already given that hardware |
| Path | `--lifecycle-path` | One Landlock grant, validated with the rule that refuses `/etc/rediacc`, other repos and the datastore |
| Root | `--lifecycle-root` | Legacy behaviour: no drop, old grants, still the built environment. Backup hooks ignore it (hook.go keeps `hookUser`), and a cold barrier refuses the repo, because root reads the unit's `/proc/<pid>/environ` |

**A tenant can ask, never confer.** The Rediaccfile may carry `# rediacc:needs root|device=<cdi>|path=<p>`. renet compares it to the grant, and with a mismatch it refuses before running and prints the exact grant line. `pkg/convergeguard` adds `needs_lifecycle_grant`, so converge doesn't restart a repo into a refusal. "Adaptive" means this: the request and the message adapt to what the repo says; permission never does.

**Rejected alternatives:**
- Declaration confers permission, or `.rediacc.json` holds it: the repo is tenant-writable.
- `state.repos` in rdc config: client side, not enforced on the machine.
- Add the universal user to `video` and `render`: every repo gets every GPU.
- Linux capabilities on the drop: `CAP_SYS_ADMIN` and `CAP_PERFMON` are the original hole, and the shape differs per program.
- Private PID namespace for up/down: the lingering init (private/renet/cmd/renet/sandbox_repo_view_linux.go:576) changes when up returns and breaks the hook's group kill; Landlock's ptrace rule covers `environ`.
- Separate GPU permission: duplicates the device grant.
- `--legacy` environment switch or grace period: clean-break rule, and the root tier is the explicit form.
- Auto-detecting root need at runtime and retrying as root: a tenant could trigger it.

**Failure a repo sees (no compatibility shim).** On a failed up() or down() whose Rediaccfile matches `sudo|chown|mknod|mount|sysctl|setcap|/dev/` the journal and CLI print `orchestration.lifecycle_unprivileged_hint`, with the matched line and exact grant command.

| Rediaccfile does | It sees | How it fails |
| --- | --- | --- |
| `sudo x` | `sudo: The "no new privileges" flag is set` | Fails, or falls through if the script ignores it (solr). Hint if up() fails |
| `chown 5050 ...` | EPERM | Same; template moves to a one-shot container |
| `rm` or `mkdir` under a container-uid dir | EACCES | Same; H2 finds these on real data |
| Writes `.env` | Works, now owned by the universal user | No failure |
| Reads `/etc/rediacc/*`, `/proc/kcore`, `/dev/sda` | EACCES | Fails unless granted a path |
| Reads a file secret directly | EACCES | Fails; use compose `secrets:` or env mode |
| `nvidia-smi`, no device grant | Device missing | Fails; hint names `rdc repo permission grant --device` |
| Declares `needs root`, no grant | Refused before any line runs | Clear refusal with the grant line |

## Corrections from the first implementation

- P0's probe lives in `cmd/renet`, as `TestLifecycle_RootProbe`, because a package test cannot reach the real `sandbox-exec` in package main. Its Accept runs from `private/renet/cmd/renet`.
- The universal user is uid 7111 (`private/renet/pkg/config/constants.go:89`), so H2's probe reports 7111.
- F2 is confirmed as a live bug on the unchanged tree: a failing compose left the up reporting success.
- F11 needed more than the plan said. The ownership walk skips `.rediacc/`, so root also creates `.rediacc/compose-tmp`, mode 1777, before the function runs.
- F15, new: after the drop, `> /dev/stderr` fails on a pipe a root parent created, so root-owned stdio pipes are handed to the target user.
- `sudo` already fails under Landlock on the unchanged tree, so the `sudo sysctl` lines in cloud-switch never worked.
- A chown to a container uid is not answerable by a path grant. H0's table says which repos this reaches.

## Boxes

Root test shape: `sudo -n env -i` is what local uid-1000 gates can't replace (the hook hole hid behind them). A SKIP is a failure in every root Accept: each pipes `-test.v` output through `tee` and checks with `! grep -q -- '--- SKIP'`.

### Prove first

- [x] P0 [local root] Failing-first probe `TestLifecycle_RootProbe` in pkg/orchestration, modelled on `TestBackupHook_SandboxConfinesTheHook` (hook_test.go): re-exec with a fake credential in the start environment, the real `sandbox-exec`, the real `buildSandboxOptions`, up() and down() as probes reporting path and verdict only. Probes: parent's `/proc/<pid>/environ`, `/proc/kcore`, `/etc/shadow`, a test-created `/etc/rediacc/backup-probe.env` 0600, the first block device from `/sys/block`, `/etc/rediacc/grants`, another repo's 0644 file, `id -u`, CapEff, chmod of another repo's file, a failing `renet compose` that must fail the up (F2). Evidence must quote rc=1 on the tree before U3.
  Accept: `cd private/renet/pkg/orchestration && go test -c -o /tmp/orch.test . && sudo -n env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin TMPDIR=/tmp /tmp/orch.test -test.run '^TestLifecycle_RootProbe$' -test.count=1 -test.v | tee /tmp/orch.out && ! grep -q -- '--- SKIP' /tmp/orch.out`
    Held back, not a tick (the code or commit is not on this branch; tick when it lands): 2026-11-03T08:00:17Z by 45048a90: commit:private/renet 778834a. P0: TestLifecycle_RootProbe under sudo -n env -i rc=1 on the unchanged tree naming uid 0, kcore, shadow, sda, the credential and chmod, rc=0 now. DEPS-WAIVED: operator /ask 2026-11-03 fix in #602
    (ticked) 2026-11-04T13:53:38Z by d778be9d: commit:2c0c29a90 renet 8af00d1. TestLifecycle_RootProbe under sudo -n env -i rc=0 no SKIP on the landed tree after U3, and rc=1 quoted on the tree before U3 in its commit; it lives in cmd/renet per the plan's correction
- [ ] P1 [fleet] `.ci/rediacc_ci/drills/lifecycle_privilege.py`, step L1 in `EXTRA_RENET_STEPS` (.ci/rediacc_ci/drills/vm_check.py:266), rows asserting the fixed behaviour; a defect is a FAIL row. Real `repo up` and `repo down` of a fork with a probe Rediaccfile on an ops worker, including a cold barrier whose process carries a fake credential (F12). Record the FAIL rows on the pre-fix tree as the proof the operator asked for.
  Accept: `npm run vm:check -- --only L1` before U3 fails on the rows naming uid 0, kcore, the block device and the credential; the output goes in the tick.
- [x] H0 [hostinger, read-only] Classify every repo with read verbs, so no renet is uploaded. From `repo list`, then for each repo `./rdc.sh --config eu-remote term connect <repo>@hostinger -c "..."`: list `Rediaccfile` and first-level subdir copies, grep for F-class lines, `find . -maxdepth 2 ! -user rediacc`, `--build` use, compose mail, cron or webhook senders, `rdc repo secret list`, disk free. Record one row per repo and which forks are safe.
  (note) Runs through `eu-bench`, not `eu-remote`: PLAN-tested-on-bench ruling 1 as extended on 2026-11-04. The text above keeps the old name because a box's first 120 characters are its identity.
  Accept: the table is in this plan under the box, with one row per name from `repo list`, each marked `default`, `needs grant: <kind>`, `no rediaccfile`, or `no up on a fork: <reason>`.
    Held back, not a tick (the code or commit is not on this branch; tick when it lands): 2026-11-03T07:19:08Z by 45048a90: the console commit that carried the plan table (not on this branch, so no sha is cited here); read-only classification of all 11 repos through term connect, table under the box, nothing uploaded. DEPS-WAIVED: read-only
    (ticked) 2026-11-04T12:56:32Z by d778be9d: commit:50cb0ab79 live read rc=0: repo list returns the same 11 names as the table, container counts match, mail spot-checked at its table lines. DEPS-WAIVED: Depends-On is no-dep, nothing written

  H0 result, read-only, 2026-11-03. Remote renet build `fingerprint:2be987228b8d`, nothing uploaded, every `term connect` admitted. Memory 31 GB total with 17 available and no swap; datastore 56 GB free of 365 GB, 85% used; kernel 6.8.0-147. `repo secret list` is empty on all 10 mounted repos, so F4 has no case on this machine today.

  | Repo | Running | Rediaccfile | Classification |
  | --- | --- | --- | --- |
  | mail:latest | 2 | `mail/Rediaccfile` | needs grant: root, `sudo tee`, `mkdir`, `cp`, `sed` at :57, :106-107, :243, :270 (direct test, H4) |
  | mautic:latest | 4 | `mautic/Rediaccfile` | needs grant: path, `chown -R 33:33` at :108, silent through `\|\| true`; reads `router.env` at :15 (F8) (direct test, H4) |
  | nextcloud:latest | 9 | `nextcloud/Rediaccfile` | needs grant: path, `chmod` of `eturnal/tls/live` at :177-178, silent; a fork can renew through the Cloudflare DNS API near expiry |
  | gitlab:latest | 1 | `gitlab/Rediaccfile` | default; `sudo rm` at :77 is in `cleanup()`, and no line selects the GPU runner override |
  | observability:latest | 6 | `observability/Rediaccfile` | needs grant: path, `chmod -R o+rX` of a tree owned by ubuntu and root at :53; `renet compose --unsafe`; alloy sends telemetry |
  | erpnext:latest | 11 | `erpnext/Rediaccfile` | default |
  | marketing:latest | 7 | `listmonk/`, `n8n/`, `plausible/` | default; n8n and listmonk can reach outside, so a fork needs care |
  | demo-stackoverflow:latest | 2 | `stack/Rediaccfile` | needs grant: path, `rm -rf pgadmin-data`, `chown -R 5050:5050` at :41-46 |
  | miscellaneous | 0 | `devbox/Rediaccfile` | default; hub, not forked |
  | hermes | 0 | `hermes/Rediaccfile` | default; retired 2026-10-28, not forked |
  | demo-heartbeat | 0 | none | no rediaccfile |

  Every repo holds root-owned `.rediacc/*`, the F11 case. A chown to a container uid is not answerable by a path grant, since the universal user stays non-root under it: those lines move into a one-shot container, or the repo takes the root tier.

### Code

- [x] U1 [renet] `sandbox.Options` gains `RequireLandlock`, `ReadonlyExcept`; `buildSandboxExecArgs` and `BuildSSHSandboxPrefix` carry them. `applyLandlockAndDrop` sets NNP unconditionally before any drop, and a Landlock-less `up` is refused (F1). Test: with Landlock stubbed off, a dropped child can't `sudo`.
  Accept: `cd private/renet && go test ./pkg/sandbox/... ./cmd/renet/ -run 'Sandbox|RunAs|Landlock|NoNewPrivs' -count=1` rc=0 and the same under `sudo -n env -i`.
    Held back, not a tick (the code or commit is not on this branch; tick when it lands): 2026-11-03T08:00:18Z by 45048a90: commit:private/renet 778834a. U1: Accept rc=0 as the user and as root; removing no-new-privs lets sudo work from a dropped child. DEPS-WAIVED: operator /ask 2026-11-03 fix in #602
    (ticked) 2026-11-04T13:53:40Z by d778be9d: commit:2c0c29a90 renet b16e419. go test ./pkg/sandbox/... ./cmd/renet rc=0, and Lifecycle, NoNewPrivs and Landlock under sudo -n env -i rc=0; a dropped child cannot sudo with Landlock off
- [x] U2 [renet] `lifecycleOptions` and the narrowed `/etc` and `/dev` (F5 to F8); `etcReadOnlyView` moves to pkg/sandbox. `RepoSandboxOptions` adopts the narrowed grants and the view, so the hook closes F5 too, while hook `RunAs` stays its own. Table test: the path lists contain no `/etc/rediacc` except `router.env` and `docker-<N>`, no bare `/dev`, and name `/dev/shm`.
  Accept: `cd private/renet && go test ./pkg/orchestration/... ./pkg/backuphook/... -count=1` rc=0 and hook tests rc=0 under `sudo -n env -i`.
    (ticked) 2026-11-04T13:52:36Z by d778be9d: commit:2c0c29a90 renet 8857c35. go test ./pkg/orchestration/... ./pkg/backuphook/... rc=0, backuphook test binary under sudo -n env -i rc=0
- [x] U3 [renet] Workflows use the drop and built environment (F4, F12, F13). `SetCleanEnvironment` for up and down, including `REDIACC_SECRET_` pass-through. Status file (F2): root creates it O_EXCL in `sandboxDir`, fchowns it, keeps the fd, and reads failures only through that fd, so a tenant's swapped symlink or FIFO can't steer root's read. `DockerSocket` only when the socket exists (F9). Mount owner handled (F10). `ChownRootOwnedToUser` also runs before up (F11); correct the comments at private/renet/pkg/orchestration/up_down_workflows.go:261-264 and private/renet/cmd/renet/main.go:1126-1130. P0 goes green.
  Accept: the P0 Accept rc=0, plus `cd private/renet && go test ./pkg/orchestration/... ./pkg/compose/... ./cmd/renet/ -count=1` rc=0.
    (ticked) 2026-11-04T13:53:43Z by d778be9d: commit:2c0c29a90 renet 8a7e70a. P0 Accept rc=0; go test ./pkg/orchestration/... ./pkg/compose/... ./cmd/renet rc=0
- [x] U4 [renet] Compose knows the grant after the drop (F3). `UpServices` passes `REDIACC_COMPOSE_GRANT` (the `Policy()` projection) and `applyComposeDelegations` uses it when the file is unreadable. A forged value only weakens the client-side check; the gate re-reads the real grant on every request (private/renet/pkg/dockergrant/grant.go:735). Sandbox gateway sets it too, fixing the shell bug. Test: a granted CDI name passes the validator as non-root, an ungranted one is refused, and a forged env value still gets a gate 403.
  Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/compose/... ./pkg/dockerproxy/... -run 'Delegation|Grant|Validate' -count=1` rc=0.
    (ticked) 2026-11-04T13:52:40Z by d778be9d: commit:2c0c29a90 renet 14b40d8. go test ./cmd/renet ./pkg/compose/... ./pkg/dockerproxy/... rc=0 including a forged value getting a gate 403
- [x] U5 [renet] Grant model. `Lifecycle` in `Grant`, `Empty`, `String`, `describeChanges`, `Validate`; flags on `daemon grant`; `pkg/gpu` reads `containerEdits.deviceNodes` incl. `hostPath`; `sandbox-exec --add-group <gid>` feeding `sandboxGroups`, with a group added only when the node's mode requires one. Grant read fails closed to the default tier with a warning. Tests: a fork has none; a reused id has none; an unreadable grant gives the default tier; a tenant-edited Rediaccfile changes nothing; a fake CDI node is reachable with a device grant and unreachable without one.
  Accept: `cd private/renet && go test ./pkg/dockergrant/... ./pkg/gpu/... ./cmd/renet/ -run 'Grant|Lifecycle|CDI|Groups' -count=1` rc=0 and the node test under `sudo -n env -i`.
    Held back, not a tick (the code or commit is not on this branch; tick when it lands): 2026-11-03T08:00:19Z by 45048a90: commit:private/renet 778834a. U5: Accept rc=0; node test rc=0 as root. DEPS-WAIVED: operator /ask 2026-11-03 fix in #602
    (ticked) 2026-11-04T13:52:43Z by d778be9d: commit:2c0c29a90 renet 8323f41. go test ./pkg/dockergrant/... ./pkg/gpu/... ./cmd/renet rc=0; the CDI node test under sudo -n env -i rc=0
- [x] U6 [renet] Root tier and backups: root grant applies no drop for up and down; `hookUser` ignores it; a cold barrier refuses such a repo, naming the grant and offering a hot run. Test with a real unit-shaped environment.
  Accept: `cd private/renet && go test ./pkg/backuphook/... ./cmd/renet/ -run 'Hook|Cold' -count=1` rc=0.
    (ticked) 2026-11-04T13:52:45Z by d778be9d: commit:2c0c29a90 renet 3811980. go test ./pkg/backuphook/... ./cmd/renet rc=0; the cold barrier refuses the root tier
- [x] U7 [renet] Declaration, hint message and `needs_lifecycle_grant` in `pkg/rediaccfile` and `pkg/convergeguard`; i18n in every locale.
  Accept: `cd private/renet && go test ./pkg/rediaccfile/... ./pkg/convergeguard/... ./pkg/i18n/... ./cmd/renet/ -count=1` rc=0.
    (ticked) 2026-11-04T13:53:46Z by d778be9d: commit:2c0c29a90 renet cb9be23. go test ./pkg/rediaccfile/... ./pkg/convergeguard/... ./pkg/i18n/... ./cmd/renet rc=0; renet i18n validate --check-hashes rc=0, translations are drafts
- [ ] U8 [renet] Kube and `DockerRuntime` executors use the same default (F14), with `KUBECONFIG` granted read-only and readable by the universal user.
  Accept: `cd private/renet && go test ./pkg/reporuntime/... -count=1` rc=0 and the kube e2e suite the test map names for `pkg/reporuntime` passes.
- [ ] U9 [console] Templates: delete cloud-switch's `sudo sysctl` lines and state the need in its docs; solr and demo-pgadmin chown through a one-shot `renet compose -- run --rm --user 0 ...`, and demo-pgadmin's `rm -rf` of a uid-5050 tree (Rediaccfile:61) goes the same way. Re-record its cast if its output changed.
  Accept: `grep -rEn '\bsudo\b|^\s*chown' packages/json/templates packages/cli/templates .ci/tutorials/apps --include=Rediaccfile` prints only demo-pgadmin's `chown -R 5050:5050 "$d"`, which runs inside the one-shot root container this box asks for, and the tutorial-parity and cast-output gates pass. (corrected 2026-11-04: the grep as first written also matched that line, and rewording the line to pass it would only hide the same chown.)
- [x] U10 [console and renet] Bridge functions `repository_permission_grant|revoke`; tiermap (grant as `TierRepoLicenseOperate`, revoke `TierNone`, as gpu at private/renet/pkg/license/tiermap.go:278-279); `rdc repo permission grant|revoke|show <ref>` with `--root`, `--path`. `--root` is refused in agent mode with the same ancestry check as `REDIACC_ALLOW_GRAND_REPO`, and `repo list` shows a root grant. Contract regeneration named for the lead.
  Accept: `npx tsc --noEmit --project packages/cli/tsconfig.json` rc=0, `cd packages/cli && npx vitest run src/commands` rc=0, `npm run check:ci-cli-contract` rc=0, `npm run check:i18n` rc=0, `npm run check:cli-examples` rc=0.
    (ticked) 2026-11-04T14:59:10Z by d778be9d: commit:8d1c76b13 tsc rc=0, vitest src/commands in the run rc=0, check:ci-cli-contract rc=0, check:i18n rc=0, check:cli-examples rc=0; translations are drafts
- [ ] U11 [docs] Rediaccfile page: runs as the universal user, the failure table, how to ask for a grant. gpu.md: the host-side tool section. private/renet/docs/DOCKERD_SANDBOX.md: lifecycle grants.
  Accept: `npm run check:i18n` rc=0 and `npm run check:ci-prose-style` rc=0.

### Fleet

- [ ] T1 [drill] L1 complete: uid not 0, every denied probe, `sudo` fails on NNP, `.env` owned by the universal user, a failing compose fails up, down with a stopped daemon reports honestly, fork has no grant, root-grant positive control, fake CDI node with and without a device grant, reboot-shaped path through `repository autostart` and a `reconcile` tick that ends running.
  Accept: `npm run vm:check` VERIFIED with every L1 row ok (`--only L1` alone never reaches VERIFIED).
- [ ] T2 [e2e] `packages/e2e-tests` 05, 07, 13, 28, 30 and 27 on the bridge suite, with 05 gaining "up() file is owned by the universal user" and "sudo in up() is refused".
  Accept: `cd packages/e2e-tests && npx playwright test tests/05-rediaccfiles-updown.test.ts tests/07-container-operations.test.ts tests/13-postgres-fork-isolation.test.ts tests/28-dockerd-privilege-gate.test.ts tests/30-gpu-device-grants.test.ts tests/27-backup-browse-at.test.ts` rc=0.
- [ ] W1 [local GPU] On the WSL host with config `wsl-gpu-test` (PLAN-gpu-device-grants W1): repo with a `nvidia.com/gpu=all` grant whose up() runs `nvidia-smi -L` and `renet compose` with `devices:`; both print the RTX 3060. Without the grant both fail, naming the permission. Native NVIDIA and AMD stay fixture-only until such a machine exists.
  Accept: each command's rc and output in the tick.

### Hostinger (after T1 and T2 are VERIFIED)

Rules: an original is never deleted, pruned, replaced or downed. `mail` and `mautic` run `repo up` directly on tag `latest`, per the ruling, with their containers checked afterwards and no fork. Every other repo is tested on `<repo>:privdrop@hostinger`, one at a time. No `--purge-backups`.

- [ ] H1 [hostinger] Deploy: the renet tree is committed and clean (a dirty one is refused; no `REDIACC_ALLOW_DIRTY_RENET`). The first mutating `./rdc.sh --config eu-remote` verb uploads it once and restarts `rediacc-router`. No `RuntimeEpoch` bump, so no repo restarts by converge; verify with `machine converge hostinger --dry-run`. Before: snapshot `repo list -m hostinger -o json` plus `term connect <repo>@hostinger -c 'docker ps --format json'` for each original. Then grant each `needs grant` repo from H0 at once, since reconcile and any cold barrier now use the new code on originals; old renet rejects the new field, so grants can't be written earlier.
  (note) Runs through `eu-bench`, not `eu-remote`: PLAN-tested-on-bench ruling 1 as extended on 2026-11-04. The text above keeps the old name because a box's first 120 characters are its identity.
  Accept: `live-proof hostinger renet-live` steps pass and the dry run reports 0 restarts.
- [ ] H2 [hostinger] Fork test. Run for `demo-stackoverflow`, `nextcloud`, `observability`, `gitlab`, one at a time, unless H0 removes one. `erpnext` and `marketing` are added if H0 marks them `default`. `miscellaneous` (hub) and `demo-heartbeat` (no Rediaccfile) are not forked. For each `<r>`: (1) baseline from the original, read-only: container names, state and health, route status with `curl -s -o /dev/null -w '%{http_code}'`; (2) `./rdc.sh --config eu-bench repo fork <r>@hostinger --tag privdrop`, without `--up`; (3) upload `privdrop-probe/Rediaccfile` into the fork with `repo sync upload`, whose up() writes `id -u` and the denied-read verdicts; (4) `repo up <r>:privdrop@hostinger`, then `repo down`, then `repo up` again, since the second up runs over files the first created, with no `--build` unless H0 says the repo needs it; (5) detect a broken app against the baseline: `repo up` rc, the same container set running and healthy, restart counts 0 after 2 minutes, route status equal to the original's on the fork's own `*-fork-privdrop.<r>.hostinger.rediacc.io` host, `docker logs --tail 200` with no new `permission denied` or `operation not permitted`, `find . -user root` empty in the repo except what the daemon owns, and the probe reporting uid 1000 and every denial; (6) if it broke: `repo permission grant <r>:privdrop@hostinger --root` and `repo up` again, where passing blames the drop and records the needed grant, and failing both ways is fork-inherent (a fork has no secrets or licence), recorded and not counted against the drop; (7) `repo delete <r>:privdrop@hostinger --dry-run`, read that it names only the fork, then the same with `-y`, and confirm with `repo list`.
  Accept: one row per repo with the seven outputs, and `repo list` shows no `privdrop` at the end.
- [ ] H4 [hostinger] `mail` and `mautic` directly, per the ruling: `./rdc.sh --config eu-remote repo up mail:latest@hostinger`, then the same for `mautic`, one at a time. Before each, the container baseline as in H2, and a backup newer than the run. After each, from rdc: container set, state and health against the baseline, restart counts 0 after 2 minutes, `docker logs --tail 200` with no new `permission denied` or `operation not permitted`, and route status. Each fails forward: a needed grant from H0 is applied and `repo up` runs again; `repo down` is never run on these.
  (note) Runs through `eu-bench`, not `eu-remote`: PLAN-tested-on-bench ruling 1 as extended on 2026-11-04. The text above keeps the old name because a box's first 120 characters are its identity.
  Accept: one row per repo with those outputs, every container back to baseline.
- [ ] H3 [hostinger] Originals unchanged: repeat H1's snapshot. Same network ids and container sets, every H0 grant present via `renet daemon grant --network-id <N> --show`, `/var/lib/rediacc/reconcile/failed/` empty, next `nightly-hot` run reports hooks as expected. Container start times unchanged except `mail` and `mautic`.
  Accept: the diff is empty except uptime and those two, recorded in the tick.
- [ ] LP-bench [live] Fresh bench receipt.
  Accept: `live-proof bench account-smoke`
- [ ] LP-hostinger [live] Fresh hostinger receipt after a VERIFIED `npm run vm:check -- --changed` on the same tree.
  Accept: `live-proof hostinger renet-live`

## Order of work

1. P0, P1 and H0 on the unfixed tree; keep the failing evidence.
2. U1, U2, U3, U4, U5 serially, then U6 and U7.
3. U8, U9, U10, U11 in parallel.
4. T1, T2, W1.
5. H1, H2, H4, H3; LP boxes last.

## Risks

- A fork's up() can act on the outside world (webhooks, scheduled jobs). H0 reads compose for this, each fork lives only for its test, and the runs are serial.
- `gitlab` and `nextcloud` are memory-heavy. H0 records free memory; skip a fork if the machine lacks room and say so.
- Reconcile can bring a down original up as non-root before a grant lands. The H1 window is short, and a failure there goes to back-off with the named hint, not data loss.
- `repo up` on `mail` and `mautic` touches production, and the first new-code run there is the test. H0 checks for root-dependent lines first, and a grant is applied before the run when H0 names one.
- A Landlock rule per `/etc` entry misses files created later. It is already the compose path's behaviour.

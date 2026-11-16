# PLAN: kubepods nested under rediacc.slice by default (kubelet hugetlb controller enablement)

Status: proposed -- converted from console#518 on 2026-11-16 (the operator picked this item of the #518 residue); awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: no-dep -- k3s argv, the k3s unit renderer and suite 17 are outside every open plan's Owns; the zot and datastore plans touch other files
Priority: P2 -- pods run in a top-level kubepods.slice outside the rediacc.slice resource and eBPF envelope (S1 verdict 4), on every cluster node
Concurrency: parallel -- renet k3s distro and unit files plus suite 17; no other plan edits them
Owns: agent/plans/PLAN-kubelet-cgroup-rediacc-slice.md, private/renet/pkg/kube/distro/k3s.go, private/renet/pkg/kube/distro/distro.go, private/renet/pkg/kube/distro/identity.go, private/renet/pkg/kube/distro/k3s_argv_test.go, private/renet/pkg/kube/distro/testdata/**, private/renet/pkg/daemon/k3s_systemd.go, private/renet/pkg/daemon/k3s_systemd_golden_test.go, private/renet/pkg/daemon/testdata/k3s_unit/*.golden, packages/e2e-tests/tests/kube/17-multinode-cluster.test.ts
Live-Proof: hostinger -- the k3s argv and unit renderer under private/renet/pkg are the renet surface, whose only live target is hostinger.
Source: https://github.com/rediacc/console/issues/518

## Ask

console#518 (Ceph + Kubernetes campaign follow-ups, still open after the 2026-07-19 audit) item "KubeletCgroupRootRediaccSlice re-enable": kubelet's cgroup root nesting under `rediacc.slice` is opt-in, and no caller opts in, because kubelet refuses to start on a fresh machine with `cgroup [rediacc] has some missing controllers: hugetlb`. systemd never enables hugetlb on `rediacc.slice` when k3s is the first unit there. The ask: enable the controllers kubelet needs, turn nesting on by default for every k3s node (install, fork, migrate), and prove it on a machine in the fresh state.

No plan covers it: `grep -rlI -E 'KubeletCgroupRoot|hugetlb' agent/plans` hits none (the `_done/PLAN-k3s-137-and-pr-conditions.md` bump does not touch cgroups). The rest of #518's open list (renet `bridge.*` keys, `queue-vault-v2`, the CNI ADR, netns-per-cluster and the external items) is out of scope.

## Context (checked 2026-11-16 against the tree)

1. `private/renet/pkg/kube/distro/k3s.go:31-49`: `KubeletCgroupRootRediaccSlice = "/rediacc"` (systemd driver form, maps to `rediacc.slice`); the comment records the wave-5 VM reproduction and that the per-service form `/rediacc.slice/rediacc-k3s-<id>.service` is rejected by the driver.
2. `k3s.go:101-127` (`applyDefaults`) deliberately leaves `KubeletCgroupRoot` empty; `k3s.go:190-202` (`kubeletArgs`) emits `--kubelet-arg=cgroup-root=` only when set. `InstallOpts.KubeletCgroupRoot` is declared at `private/renet/pkg/kube/distro/distro.go:71-74`. Outside tests nothing sets it (`git -C private/renet grep -n KubeletCgroupRoot` hits only k3s.go, distro.go and `k3s_argv_test.go:228-251`).
3. Sibling found on the way: the fork/migrate identity rewrite builds its own `InstallOpts` at `private/renet/pkg/kube/distro/identity.go:196-209` and never passes through `applyDefaults` (the only call is `k3s.go:256`). Turning the default on in `applyDefaults` alone would leave every forked or migrated node with a different cgroup root from a freshly installed one.
4. Both paths write the unit through `daemon.CreateK3sSystemdService` with `Slice: "rediacc.slice"` (`k3s.go:283`, `identity.go:216`), rendered by `renderK3sUnit` (`private/renet/pkg/daemon/k3s_systemd.go:33-63`): `Delegate=yes`, no `ExecStartPre`. Goldens: `pkg/daemon/testdata/k3s_unit/network-2816-server.service.golden`, `network-2880-agent.service.golden`.
5. renet already writes `cgroup.subtree_control` itself for `rediacc.slice`: `private/renet/pkg/repolimits/repolimits.go:35-37,239-258` enables `cpu io memory pids` when offered. Nothing enables `hugetlb` or `cpuset` anywhere (`git -C private/renet grep -n hugetlb` hits only the k3s.go comment and a filesystem-type regex).
6. Mechanism (reasoned, verified by K6): `rediacc.slice`'s `cgroup.controllers` is the root cgroup's `cgroup.subtree_control`. `Delegate=yes` makes systemd enable every controller it manages down the unit's path, but systemd has no hugetlb controller, so hugetlb reaches `rediacc.slice` only when something else wrote `+hugetlb` at the root (runc does when a docker repo started first). On a machine where k3s is the first workload, nothing has, and kubelet's controller check fails.
7. Live clusters run k3s inside the control datastore; cluster verbs `rdc cluster create/install/fork/migrate` refuse in agent mode unless `REDIACC_ALLOW_CLUSTER_OPS` is set in the launching shell (suite 24 sets it, `packages/e2e-tests/tests/kube/24-cluster-licensing.test.ts:150`). Suite 17 (`packages/e2e-tests/tests/kube/17-multinode-cluster.test.ts:347-660`) covers server plus agent join, whole-cluster fork (identity rewrite) and migrate, so it exercises both unit-writing paths.

## Design

**Controllers before kubelet, on every start.** `renderK3sUnit` gains one `ExecStartPre` that, for each of `cpuset cpu io memory hugetlb pids` offered in `/sys/fs/cgroup/cgroup.controllers`, writes `+<c>` to `/sys/fs/cgroup/cgroup.subtree_control` and to `/sys/fs/cgroup/rediacc.slice/cgroup.subtree_control`. `ExecStartPre` runs inside the unit's own cgroup, so `rediacc.slice` already exists when it runs, and it reruns on `Restart=always` and after a reboot, which an install-time write would miss. A controller the kernel does not offer is skipped, matching kubelet, which only requires controllers the host has. The line has no `-` prefix: a failed write fails the unit start with the shell's error rather than letting kubelet fail later with a vaguer one. Rejected: a new hidden renet subcommand (adds a command-tree and contract surface for a five-controller loop), and a systemd slice drop-in (systemd has no directive that enables hugetlb).

**Nesting is not an option any more.** Delete `InstallOpts.KubeletCgroupRoot`; `kubeletArgs` always emits `--kubelet-arg=cgroup-root=/rediacc`, so install and the identity rewrite (Context 3) cannot diverge. Clean break: an existing node picks up the new argv the next time renet rewrites its unit; kubelet then recreates pod sandboxes under the new root. There are no external users, and the e2e suites cover it.

**One cgroup root per machine is not a new limit.** Two k3s instances on one machine would share `rediacc-kubepods.slice`. That is already impossible (fixed ports 6444/10248/10257/10259 and `/run/k3s`, #518 "same-machine concurrent cluster forks"); the netns-per-cluster work, out of scope here, has to give each cluster its own sub-slice when it lands, and the `KubeletCgroupRootRediaccSlice` comment says so.

**Proof in the fresh state.** The defect only shows where hugetlb is absent from the root's `subtree_control` before k3s starts. K6 records that state on the proving VM before the install, and the e2e asserts the outcome (kubepods under `rediacc.slice` on both nodes, no top-level `kubepods.slice`).

## Boxes

- [ ] K1 [writer] `k3s_argv_test.go`: flip the default-argv case to require `--kubelet-arg=cgroup-root=/rediacc` for server and agent, add an identity-rewrite argv case that requires the same flag, and delete `TestKubeletCgroupRootOptIn`. Accept: `cd private/renet && go test ./pkg/kube/distro -run 'TestK3s|TestKubelet|TestIdentity' -count=1` rc 1 before K2 and rc 0 after
- [ ] K2 [writer] Delete `InstallOpts.KubeletCgroupRoot`; `kubeletArgs` always emits the cgroup root; rewrite the `KubeletCgroupRootRediaccSlice` and `applyDefaults` comments to the new contract (including the one-root-per-machine note). Accept: `cd private/renet && go test ./pkg/kube/... -count=1` rc 0 and `git -C private/renet grep -n 'KubeletCgroupRoot\b'` empty
- [ ] K3 [writer] `renderK3sUnit` emits the controller `ExecStartPre` per Design; regenerate both `k3s_unit` goldens through the golden test's update path and review the diff (one added line each). Accept: `cd private/renet && go test ./pkg/daemon -run TestK3s -count=1` rc 0
- [ ] K4 [writer] Suite 17 test 2 (after the agent joins) asserts on both workers: `/sys/fs/cgroup/rediacc.slice/cgroup.controllers` lists hugetlb when the kernel offers it, `rediacc-kubepods.slice` exists under `rediacc.slice`, no `/sys/fs/cgroup/kubepods.slice` was created by this cluster, and the anchored pod's container cgroup path starts with `/rediacc.slice/`; test 4 (fork) repeats the kubepods assert on the forked node. Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0
- [ ] K5 [live] Suites 15, 16 and 17 on the local KVM fleet with K2-K4 landed. The ops VMs are shared with another agent: use the suites' own machines, no `ops down`, and do not assume exclusive use. Cluster verbs need `REDIACC_ALLOW_CLUSTER_OPS` in the launching shell. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --test tests/kube/17-multinode-cluster.test.ts` rc 0, and the same with `tests/kube/15-k8s-repo.test.ts` and `tests/kube/16-datastore-cluster.test.ts`
- [ ] K6 [live] Fresh-state proof: on the K5 control VM, before the k3s install, record `cat /sys/fs/cgroup/cgroup.subtree_control`; the proof counts only if hugetlb is absent there (else use a VM with no docker repo started since boot, after a reboot). After install, record kubelet Ready, the same file now listing hugetlb, then `systemctl daemon-reload`, a restart of an unrelated unit in `rediacc.slice`, a k3s restart and a reboot, each followed by `kubectl get nodes` Ready. Accept: the before/after file contents and the four Ready checks recorded in the plan's Context with the date
- [ ] V1 [live] VM tier for the renet surface before the live receipt. Accept: `npm run vm:check -- --changed` rc 0 with a VERIFIED receipt
- [ ] LP-hostinger [live] Fresh hostinger receipt after V1 on the same tree; provisioning a branch renet restarts the router and daemons on hostinger.
  Accept: live-proof hostinger renet-live

## Risks

- systemd might strip a controller it does not manage from the root or `rediacc.slice` on a later realization. Context 6 reasons that it only toggles controllers in its own mask; K6's reload, unrelated-unit restart and reboot steps are there to refute that if it is wrong, and the per-start `ExecStartPre` re-applies it on every k3s start either way.
- Pods move into the `rediacc.slice` eBPF scope. The k3s unit already lives there today (`Slice=rediacc.slice`) and S1 proved pod networking under the /26 ACLs, but suites 15-17 in K5 are the gate; a pod-network regression there blocks the plan, it does not get a waiver.
- Existing nodes switch cgroup root on their next unit rewrite, which recreates pod sandboxes once. Acceptable pre-launch; a node mid-fork during the upgrade is covered by suite 17's fork step.
- The ExecStartPre shell runs as root on every k3s start; its input is fixed (the controller list and two fixed paths), and the golden locks the exact line.

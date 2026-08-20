---
name: ops-vms
description: Provisioning and operating the local KVM VM cluster with ./rdc.sh ops (up, up --basic, down, status) plus working on those VMs over SSH. Knows the 6-VM topology and its RAM/disk cost, the incremental provisioning behavior, the build-first trap that fails ops before any VM work, the OS image matrix, SSH access rules, the autostart/reconcile recovery layers, and which operations are agent-blocked by ancestry-verified env overrides. Use when a task needs live machines or a fleet of them: bridge tests, licensing drills, cluster/ceph work, hypervisor or libvirt trouble, or diagnosing why ops up failed.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You provision and drive the local VM fleet. The commands are cheap to type and expensive
to misunderstand; every note below was verified live.

## The fleet

`./rdc.sh ops up --basic`: VM 1 (bridge: registry + harness, 192.168.111.1) + VM 11
(worker, .11). About 4 GB RAM and 16 GB disk each. Enough for plain repo/licensing work
on one machine.

`./rdc.sh ops up` (full): adds VM 12 (worker, .12) and the Ceph trio 21/22/23
(.21-.23). Measured: 1024 + 5x4096 = **21504 MB** RAM at defaults, and disk is
SPARSE -- ~8.9 GB actual across the six system images plus three 32 GB sparse
`cephosd` images, not ~190 GB allocated. Required for: migration between
workers (needs .12), datastore forks and anything RBD (a datastore-level fork is
RBD-only; local-backend forks are refused outright), cluster/kube legs.

Provisioning is INCREMENTAL: a full `ops up` after `--basic` adds the missing VMs and
leaves the existing ones alone. VMs PERSIST across sessions; `./rdc.sh ops down` is the
only teardown and tearing down after tests is a standing post-test step. Probe state
with `rdc ops status -o json` (CLI envelope around the renet payload) or
`virsh list --all`; the licensing drill's preflight is a good model of a loud
availability check.

## The build-first trap

EVERY `./rdc.sh` invocation first ensures deps, rebuilds stale shared packages, the CLI
bundle, and renet, then syncs the renet binary to targets. Consequences:

- A compile error ANYWHERE in packages/cli (including another writer's mid-edit window)
  fails `ops up` before any VM work, with the tsc error buried in the wrapper output.
  Check `npx tsc --noEmit --project packages/cli/tsconfig.json` when ops fails
  instantly and the message is not about VMs.
- A wrapper exit code is the CLI's exit code; "exit 2" from an ops command can be a
  commander usage error, not an infrastructure failure. Read the stderr.
- Once a renet source change exists locally, the next rdc.sh invocation deploys it.
  Never scp/sudo-cp renet binaries yourself; the pre-tool hooks block it anyway.
- NEVER run a bare `go build -o bin/renet` in private/renet: it produces an
  ENFORCING build with NO key baked (every licensed op fails "public key not
  configured") and, until the 2026-08-04 stamp fix, the build cache would keep
  deploying that poisoned binary to every VM. Always build via `./build.sh dev`
  or just let rdc.sh do it. Diagnose flavor with `go version -m bin/renet`:
  nolicense builds carry `-tags=nolicense`, enforcing-with-key builds carry
  `ProductionPublicKey=` in ldflags, a binary with NEITHER is the poison.
- Any rdc.sh invocation is a full CLI startup: with `REDIACC_CONFIG=<name>` exported it
  AUTO-CREATES that config if missing. Even `rdc ops status` in a preflight counts.
  Sequence explicit `config init` BEFORE exporting REDIACC_CONFIG.

## Access

- Raw SSH is allowlisted ONLY for 192.168.111.*; everything else goes through
  `rdc term connect`.
- THE KEY THE VMS ACTUALLY AUTHORIZE is the renet-staged `id_rsa` (path from
  pkg/infra/opsconfig, rooted at RENET_DATA_DIR or ~/.renet), NOT ~/.ssh/id_ed25519.
  A bare `ssh` can STILL succeed with the wrong -i because OpenSSH silently falls
  through to default identities after a refusal, while the CLI (ssh2, one explicit
  key, no fallback) fails with "All configured authentication methods failed": the
  two disagreeing is the signature of this exact situation. When proving which key
  authenticates, use `ssh -F /dev/null -o IdentitiesOnly=yes -o IdentityAgent=none`
  so the answer is about the key you named.
- Repo sandboxes: `./rdc.sh term connect <repo>` presets DOCKER_HOST to the per-repo
  socket and cwd to /mnt/rediacc/mounts/<guid>. `docker compose` inside a repo context
  is blocked; use `renet compose -- <args>`.
- OS matrix: `VM_IMAGE=<ubuntu-24.04|debian-13|fedora-43|opensuse-16.0|oracle-10>`
  reproduces a CI matrix cell. Rocky 10 is excluded on purpose (no btrfs in stock RHEL
  10 kernel); `./bin/renet system check-btrfs` is the per-OS probe.
- `VM_BRIDGE`, `VM_WORKERS`, `VM_CEPH_NODES` (space-separated ids) shape a custom
  topology, AND `VM_CEPH_NODES` is load-bearing beyond topology: Ceph provisioning
  (cephadm bootstrap + client distribution to workers + OSD data disks) happens
  inside `ops up` ONLY when it is set in the environment. A default `ops up` creates
  the Ceph VMs as bare OS images: no ceph/rbd binaries anywhere, and
  `datastore create --backend rbd` dies with `rbd: command not found` (paid for
  live, 2026-08-04).
- **`--force` is NOT required, and the old claim here was wrong about the
  mechanism.** This file used to say bare Ceph VMs "are NOT healed by an
  incremental `ops up`" and prescribed `--force --parallel` to recreate the trio.
  The observation was real; the cause was not. `ops_up.go:184-190` runs
  `orchestrateCluster` on every `ops up`, and the Ceph block at `:415-418`
  depends only on `ProvisionCeph` + `VMCephNodes` -- there is no
  "VMs already exist, skip Ceph" path in the code. What actually happens is that
  `ProvisionCeph` arrives FALSE: `opsconfig.Load` probes `cwd/../.env`
  (`config.go:172`), the CLI spawns renet with no cwd so it inherits the console
  root, and `/home/muhammed/monorepo/.env` carries `PROVISION_CEPH_CLUSTER=false`,
  which `config.go:541` gives precedence over the `VM_CEPH_NODES` inference.
  So: **always set `PROVISION_CEPH_CLUSTER=1` explicitly** -- a real env var
  outranks that stray parent `.env` -- and do not recreate the VMs. The existing
  trio already carries its `cephosd` disk (attached at create time,
  `ops_up.go:294-296`), so `--force` costs ~20 minutes and buys nothing.
- The standalone bootstrap is `PROVISION_CEPH_CLUSTER=1 VM_BRIDGE='1'
  VM_WORKERS='11 12' VM_CEPH_NODES='21 22 23' ./bin/renet ops ceph provision`,
  run from `private/renet` (from the console root the parent `.env` above is on
  the probe path). It works against ALREADY-RUNNING bare VMs: `provision()`
  (`provisioner.go:78-168`) is pure SSH and creates no VMs. **It is DESTRUCTIVE
  and re-runnable, not idempotent** -- `Bootstrap` opens with `CleanupState`
  (`provisioner.go:413`), wiping any existing cluster and rebuilding. ~21 minutes;
  background it. The provisioner creates pool `rediacc_rbd_pool`, not `rbd`: pass
  `--pool rediacc_rbd_pool` to `datastore create --backend rbd`.
- `ops ceph health` only CHECKS: against never-provisioned nodes it polls toward a
  600s timeout (the fail-fast state file exists only after a FAILED provisioning,
  not an absent one). **And health is the WRONG oracle for whether Ceph is
  usable.** HEALTH_OK is silent about client distribution: a cluster with healthy
  mons and every OSD up reports it whether or not a worker ever received
  `/etc/ceph`. Prove Ceph on the WORKERS -- `/etc/ceph/ceph.conf` plus an `rbd`
  binary on each -- never with cluster health and never with VM liveness:

  ```bash
  for ip in 192.168.111.11 192.168.111.12; do
    ssh -i ~/.renet/staging/.ssh/id_rsa ubuntu@$ip 'ls /etc/ceph; command -v rbd'
  done
  ```

  This is not hypothetical. On 2026-08-16 `ceph-common` was SIGKILLed mid-install
  on worker 12 (worker 11 survived the same command at 106s), the failure was
  recorded correctly, and `checkProvisionRecord` then DELETED the record because
  the cluster was HEALTH_OK. The E2E suite ran against a half-configured fleet and
  died six minutes later with "can't open ceph.conf". Both halves are now fixed
  (the record survives a client-side failure; the harness asks the workers), but
  the lesson stands: ask the machine that must do the work.

## Ceph on the local fleet

Nothing here is operator-gated: `REDIACC_ALLOW_CLUSTER_OPS` gates the `rdc cluster` /
`rdc datastore` CLI verbs (`command-policy.ts:197,217`), and the ceph-workers suites
never touch `rdc` -- they drive `renet` on the VMs over SSH through `BridgeTestRunner`.
`renet ops ceph provision` has no policy layer at all. An agent can run every step.

Two ways in, and they cost very differently:

- **Cluster only** (~21 min): the standalone `ops ceph provision` above. Right when the
  VMs are up and you just need Ceph.
- **Whole suite** (~37 min): the harness provisions Ceph itself --
  `bridge-global-setup` -> `resetVMs()` -> `renet ops up --force --parallel`, whose
  Ceph block fires on `ProvisionCeph` + `VMCephNodes`.

```bash
.ci/scripts/env/create-e2e-env.sh \
  --renet-path "$PWD/private/renet/bin/renet" --output packages/e2e-tests/.env \
  --vm-workers "11 12" --vm-ceph-nodes "21 22 23" \
  --vm-ram-worker 2560 --vm-ram-ceph 2560 --ceph-osd-memory-target 1717986918
printf 'RENET_DATA_DIR=%s/.renet\n' "$HOME" >> packages/e2e-tests/.env
.ci/scripts/test/run-e2e.sh --workers 1 --config playwright.ceph-workers.config.ts --fail-on-skip
```

The `RENET_DATA_DIR` line is the local-only delta: the generated `.env` sets `CI=true`,
which sends renet to `/tmp/renet` where the VMs' authorized key does not live.

Three traps worth the ink:

- **Topology comes ONLY from `--vm-workers` / `--vm-ceph-nodes`**
  (`create-e2e-env.sh:66-72`). An env prefix of `VM_CEPH_NODES=...` is INERT here and
  merely appears to work when it matches the defaults. (`VM_RAM_*` and `VM_IMAGE` do
  fall back to env; topology does not.)
- **`--vm-ram-worker` / `--vm-ram-ceph` are mandatory for this topology.**
  `assert_ram_budget` caps at a hardcoded 14848 MB and the default 6-VM fleet computes
  to 21504 MB, so it exits 1 before writing anything. No env override for the ceiling.
- **`KEEP_CLUSTER=1` / `BRIDGE_TEST_SKIP_RESET=1` skip `resetVMs`, and therefore skip
  Ceph provisioning too.** Fine for iterating once the cluster exists; never on a first
  run.

Budget note: the suites themselves take ~61 seconds. Everything else is bootstrap, and
CI's `resetVMs` cap is 1800s against a measured 1800.2s -- a marginally slower run gets
SIGTERM'd mid-Ceph and reports `code: -1`. That is a latent flake, not a mystery.

## Agent-mode guardrails (ancestry-verified, non-negotiable)

`REDIACC_ALLOW_CLUSTER_OPS` (cluster/datastore create, destroy, scale, fork, migrate)
and `REDIACC_ALLOW_GRAND_REPO` (writes to grand repos; machine-level term connect needs
`*`) must be set in the OPERATOR's terminal BEFORE the agent session starts. An export
from inside the session is rejected by design. Do not fight it: structure work so the
operator runs those steps, or fail early with a message naming the override. `rdc run`
stays blocked in agent mode regardless. Fork-then-takeover is the sanctioned path for
grand-repo changes.

## Recovery layers on the VMs

- Boot: rediacc-autostart.service mounts + ups every autostart repo once.
- Continuous: rediacc-autostart-reconcile.timer (~3 min) re-recovers any autostart repo
  that is down; healthy repos, cold-backup holds, and back-off windows are skipped.
- Container-level restarts belong to the router watchdog (3s), not reconcile.
- Persistent failure marker after 5 failed recoveries:
  /var/lib/rediacc/reconcile/failed/<guid> (+ error log). Licensing analogue:
  /var/lib/rediacc/license/failed/<guid>.json for license-blocked backups.
- Common causes in both: expired/untrusted license, missing keyfile, broken
  Rediaccfile. `rdc machine status <m> --licenses` and `--repositories` are the first
  two reads.

## Sleep/polling rules

Foreground sleeps >20s are hook-blocked (lowered from 30). Separately, the Bash tool caps a
FOREGROUND command at 10 minutes, and what happens next VARIES: observed both a SIGTERM at
exit 143 (a recording died mid-flight having run none of its own cleanup) and an automatic
move to background. Never rely on either. Anything that can outlive 10 minutes goes in
run_in_background from the start; the harness notifies on completion. For a CI
run, poll to a terminal state in background -- `gh run watch` has dropped silently on
terminal runs (4/4), so a process exit on terminal state is the reliable notification.

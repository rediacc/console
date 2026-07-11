# 04 — Cluster Fork and Migrate: Anchor + Rejoin

## 1. Principle

The control-plane image IS the cluster (k3s keeps the whole cluster state in its embedded
kine DB; "the cluster image itself is the snapshot"). Agent state is rebuildable. Therefore:
move/fork the ANCHOR (control-plane data-dir, living inside a datastore) and let agents
REJOIN fresh with the CA-derived token that `kube_identity_rewrite` already preserves.
This kills the `dstAgents >= srcAgents` constraint: destination node count is free (1..N).

## 2. Cluster fork (hot, data included by construction)

```
PARENT (keeps running)
 ds-alpha ─┐
 ds-beta  ─┼─ rbd group snap (ONE instant) ─► clone each ─► attach on dest machines
 ds-gamma ─┘                                                  (--writes ceph|local)
            └ CP data-dir inside ds-alpha       ─► CP identity rewrite ─► agents join fresh
```

1. `rbd group snap create` across ALL the cluster's datastore images. No drain, no stop —
   the parent never notices. Crash-consistent = the documented power-cut contract.
   (Current fork drains and stops the whole source cluster; that path is replaced.)
2. Clone each image from the group snap. The `--writes` choice composes here:
   `--writes ceph` = durable second cluster; `--writes local` = **ephemeral throwaway test
   cluster with zero Ceph footprint** (a first-class product capability that falls out).
3. Attach on destination machines (any count; one beefy machine can mount all of them).
4. CP identity rewrite — SPLIT BY OPERATION (review F1/F2, F1 is the program's blocker):
   - **Fork**: new networkID + IP, and **full PKI regeneration** — delete the tls dir so
     k3s re-mints CA + service-account keys on first boot (the forked data-dir otherwise
     carries the parent's CA private key = a permanent parent-admin credential in every
     fork/test-cluster/AI-sandbox). Plus the **secret scrub**: delete rediacc-labeled
     Secrets, scrub-all third-party Secrets by default, sweep legacy SA-token Secrets,
     rewrite the ROLE ConfigMap to `fork|rehearsal`.
   - **Migrate**: CA preserved (same principal — the existing `identity.go` seam, correct
     there), serving leaf regenerated for the new IP, secrets stay.
5. Fresh agent joins (fork: token minted by the NEW CA; migrate: reused CA-derived token);
   stale Node objects deleted from kine.
6. **Mount-path stability trick**: keep `/mnt/rediacc/ds-<name>` identical on the dest even
   though the clone image is renamed → PV objects in kine (which reference mount paths, not
   image names) need ZERO rewriting; only the attach-time node labels change.
7. Same-machine forks stay forbidden (two k3s cannot share a host netns; also avoids
   mount-path collisions). Attach additionally refuses ANY mount-path name collision on a
   dest machine (review F12 — the "one beefy machine mounts all of them" case), and node
   relabeling follows the remove-before-add ordering from 02 §3.
7b. **Built images ride the datastore, not the agent cache** (review F4): locally built
   container images are pushed to a small registry whose backing store is a directory
   INSIDE the repo's datastore folder — so images survive fork/migrate by construction.
   `ctr images import` into agent containerd is rejected: agents are disposable cache, and
   a fork booting fresh agents would ImagePullBackOff on every locally built image.
8. Because every repo's data lives inside some datastore, the "cluster fork doesn't carry
   PVs" gap (01 §5.1) becomes impossible by construction. Capture-side ordering rules
   vanish (one instant); start-side stays CP-first.

## 3. Cluster migrate

- **In-Ceph** (same Ceph reach): pure fenced remap — detach datastores from old nodes,
  attach on new machines, CP identity rewrite (networkID KEPT, IP only), agents join.
  ZERO bytes copied; today's `backup_push` block transfer disappears for this case.
  Node-to-node moves inside a cluster stop being "migrate" at all — just datastore failover.
- **Cross-site**: the 03 §4 pipeline (snapshot → transfer → iterated diffs → down() →
  final diff → up() + health gate). RBD mirroring is the storage-native pre-copy transport
  when both sites run Ceph. Local-tier datastores still push.

## 4. Lifecycle and the health gate (generalizes proven repo-migrate behavior)

`repo migrate` already does down() → final delta → up() with measured downtime, and k8s
repos already deploy through Rediaccfile `up()` (`pkg/kube/deploy.go`: "Apply is the deploy
path a Rediaccfile up() calls"). Cluster operations adopt the same vocabulary:

```
1. (optional) REHEARSE: ephemeral fork on dest, up, health gate, discard
2. PRE-COPY (hot)
3. CUTOVER: per-repo down() → final snap → transfer diff → attach →
   CP identity rewrite + agent joins → per-repo up() [secrets inject from config]
   → HEALTH GATE per repo → source released
4. Rollback = restart the intact source (kept until the gate passes)
```

- **Health contract**: an optional Rediaccfile `health()` function (or an `info()` exit-code
  convention — decide in P0 spec), layered on k8s readiness for cluster repos and the
  distro `healthcheck` for the control plane itself.
- **Secrets policy** (02 §4): migrate re-injects automatically (same principal); fork
  starts empty (new principal). Rehearsal forks therefore run secretless: apps see
  `REDIACC_ROLE=rehearsal` and degrade gracefully; optionally the operator supplies
  throwaway secrets. This is a deliberate, documented behavior.
- CLI symmetry: `cluster fork --up`, `cluster migrate` implies up + gate,
  `cluster rehearse` = boot latest snapshot as throwaway fork on a target, report health,
  discard.

## 5. What changes vs today (summary table)

| | Today | Target |
|---|---|---|
| Fork source impact | drain + stop all nodes | none (hot group snap) |
| Fork data coverage | cluster images only (PV gap) | everything, by construction |
| Consistency | cold (by stopping) | one atomic instant |
| Dest node count | >= source agents | any (1..N) |
| Ephemeral test fork | not a concept | `--writes local`, free, discardable |
| Migrate data plane | backup_push block transfer | in-Ceph remap (zero copy); cross-site rbd-mirror/export-diff |
| Cutover consistency | crash-consistent | clean-shutdown (down() before final snap) |
| Health | none | per-repo gate + rollback window |

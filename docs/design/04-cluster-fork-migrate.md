# 04 — Cluster Fork and Migrate: Anchor + Rejoin

**Status: AS-BUILT and PROVEN LIVE.** The fork orchestrator ran green four independent times
(FU#1, rv1, e2e suite 16, e2e suite 17); the in-Ceph migrate ran green twice with a measured
cutover. Both arms live in product code (`services/cluster/cluster-fork.ts`). The build added
two steps the design did not anticipate; they are marked AS-BUILT below.

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
2b. **AS-BUILT, NEW: prepare the destination, then ferry the datastore RECORD to it.** The
   design assumed a clone in shared Ceph was reachable from any machine that can reach Ceph.
   It is not, and this was the architectural blocker that stopped the first live fork:
   - The destination needs the **source's Ceph client config and tooling** (`ceph-common`/rbd,
     plus `sqlite3`) before it can touch the clone at all. `prepareForkDest` does this now
     (bugs #7 and #15). The fork destination must also be a **bare** machine: forking onto a
     machine that already runs a cluster collides at :6443, and the CLI now refuses that with
     a teaching error rather than corrupting both (bug #8).
   - The datastore RECORD lives in the SOURCE machine's registry only. A cross-machine
     `datastore attach` on the destination therefore failed with "not registered on this
     machine" even though the rbd clone was right there in the pool (bug #14). The fix is the
     new **`datastore adopt`** verb: the fork's record is exported as JSON from the source,
     base64-ferried, and adopted on the destination before attach. `datastore forget` is its
     inverse (registry-only removal, refuses while attached), and it is what keeps the
     single-mounter invariant true across a migrate.
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
6. **Mount-path stability trick**: keep `/mnt/rediacc-ds/<name>` identical on the dest even
   though the clone image is renamed → PV objects in kine (which reference mount paths, not
   image names) need ZERO rewriting; only the attach-time node labels change.
   (The path is the sibling scheme per P0 ruling R1; see 02 §1.)
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

**AS-BUILT: the ordering is load-bearing, and it is not the obvious one.** Migrate hit the
same record-propagation wall as fork (bug #18), and the naive sequence would have been
destructive: detach the source, then discover the destination cannot register the record, and
now the source cluster is down with its datastore detached and nothing able to attach it. The
built sequence closes that failure mode **by construction**:

```
seed dest (ceph config + tooling)   ← the #7/#15 class, migrate arm (bug #19)
adopt --plain on dest               ← register BEFORE anything destructive
VERIFY the dest registry            ← refuse to proceed if the record is not there
down  →  detach  →  attach (fenced) →  identity-rewrite (migrate arm) →  health gate
forget on source                    ← only now; single-mounter restored
```

Rollback on an attach failure re-attaches the source and restarts its control plane, with the
manual path named in the error text.

**Measured cutover: 21.6s** (rv1, orchestrator-reported, down to health-gate-pass; the
client-observed API gap was roughly 12 to 14 seconds at 0.4s polling) and **53 to 56s** in the
e2e suite. The e2e figure is larger and is the honest one to quote for a system under test: it
counts the node-side teardown work (stopping the CSI units, unwinding the mounts) INSIDE the
measured window, because the product's own teardown primitive has to do that work too. No
discount taken.

**Agent orphaning on migrate is design-expected, not a bug.** Migrate moves the control plane
only; the old agents go NotReady and must rejoin. That is the anchor model working as
specified (agents are a disposable cache).

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

## 5. What changes vs the old model (summary table, with measured results)

| | Old model | New model (built) | Proven |
|---|---|---|---|
| Fork source impact | drain + stop all nodes | none (hot group snap) | Parent served 4941/4943 liveness samples over 82 min, zero gaps at the API |
| Fork data coverage | cluster images only (PV gap) | everything, by construction | App-data marker rides the clone on every fork run |
| Consistency | cold (by stopping) | one atomic instant | RBD group snap, 1.2s to 8.7s |
| Dest node count | >= source agents | any (1..N) | Fork onto a single bare dest, live |
| Ephemeral test fork | not a concept | `--writes local`, free, discardable | dm-thin overlay, zero Ceph writes |
| Migrate data plane | backup_push block transfer | in-Ceph remap (zero copy) | Cutover **21.6s** (orchestrator) / **53-56s** (e2e, teardown inside the window) |
| Fork security | CA preserved = fork is a parent-admin credential | full PKI re-mint + secret scrub | Fork CA differs; parent cert 401s on the fork, 200s on the parent. Re-mint ~120s |
| Health | none | per-repo gate + rollback window | Gate runs in both arms |

**Whole-cluster fork wall time: ~85s** (FU#1, single-node dest) and **125 to 161s** (e2e
multinode, which additionally waits for a fresh agent to join the fork's NEW CA). The bulk of
it is the identity rewrite, dominated by the F1-F8 PKI re-mint at roughly 120 seconds. The
storage half (snapshot, clone, adopt, attach) is single-digit seconds and is constant-time in
the size of the data.

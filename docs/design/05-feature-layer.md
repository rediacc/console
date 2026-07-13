# 05 — Feature Layer (v1 scope, on top of the core)

User decision 2026-07-10: the feature layer ships IN this program (not deferred), gated
behind the core (P3 cannot start before the P2 gate).

## Status (as-built, 2026-07-13)

| Feature | State |
|---|---|
| **CSI driver** (§3b) | **BUILT and PROVEN LIVE.** csi-sanity 48/50, dynamic PVC, VolumeSnapshot, point-in-time restore, independent clone, auto-enabled. Spec and as-built record: `spec/09-csi-driver.md`. |
| **PV LUKS** (§3) | **BUILT in P1** as the volume FORMAT (per-volume LUKS images). Honest `df` verified live. |
| `repo replicate` (§1) | **BUILT, NEVER RUN.** Real, complete, wired, unit-tested (13 tests). Zero live executions, zero e2e coverage. |
| `cluster rehearse` (§2 rung 1) | **BUILT, NEVER RUN.** Delegates to the heavily-proven `forkCluster` with `role: rehearsal`, and discards on both the success and failure paths. Its own role/discard semantics have never executed. |
| Release ladder rung 0 + canary (§2) | **BUILT, NEVER RUN.** Undo snapshot and canary weight templating; the renet router's weighted-service backend is real and has a production caller. Zero live executions. |

**The three never-run features are EXIT-BLOCKING as B1** (see 09 §2). This is not
bookkeeping pedantry. P3's single most important empirical result is that **unit-green
predicted nothing about live behavior in this codebase**: four feature-breaking product bugs
survived unit tests and two live campaigns and fell only to end-to-end execution. Three
features that have never been run once are, on this codebase's demonstrated base rate, the
likeliest place for exactly that class of defect. B1 discharges inside one bounded live
window.

## 1. `rdc repo replicate` — instant read replicas (the flagship demo)

```
rdc repo replicate --name sqldb --replicas 10 --refresh 1h [--headless]
  1. datastore snapshot (one instant)
  2. N fork-attaches, --writes local, spread across nodes
  3. N generated `local` PVs (one per node, into each fork mount)
  4. generated StatefulSet/Deployment + pod anti-affinity + REDIACC_ROLE=replica
  5. two Services: <name>-rw → primary pod, <name>-ro → the N replicas
```

- Replicas are WRITABLE point-in-time copies (dm-COW overlay), because database engines
  cannot run on strictly read-only data dirs (they write WAL/temp even for SELECTs); the
  engine does one crash-recovery pass and serves. Throwaway writes.
- Same namespace as the primary → the k8s Service IS the load balancer. Readiness probes
  auto-eject a replica while it is being re-forked → rolling `--refresh` is invisible to
  clients (N-1 keep serving). kube-proxy routes from any node.
- L4 caveat: Service balancing is per-connection; long-lived DB connections can skew.
  `--headless` variant (DNS returns all pod IPs) for multi-host-aware drivers; a pooling
  proxy only on demand.
- Honest limits (document): point-in-time reads, no read-your-writes; overlay sizing × N
  (storage-health watches; the F10 allocation-churn effect applies per replica). The FORK
  is constant-time regardless of DB size; each replica then runs a crash-recovery pass
  proportional to WAL/checkpoint distance with cold caches (review F15) — the "1 TB → 10
  replicas in seconds" demo number holds with a recently-checkpointed primary; say so.
  Service/selector plumbing (`<name>-rw` → primary, weights) is specified precisely in P0,
  not hand-waved.
- **Replicate is managed state with CRUD from birth (R2-F17)**: `repo replicate status` /
  `remove` exist alongside the create form, and `repo status` shows replica sets — never a
  fire-and-forget flag pile ("flags-as-children is how `kubectl run` became a graveyard").

## 2. Release ladder (safe upgrade/release cycle)

```
0. SNAPSHOT   auto group-snap before any release        (universal undo)
1. REHEARSE   fork + run release + health gate          (catches most, costs ~nothing)
2. CANARY     SHARED live data + proxy weighted routing (schema-compatible releases)
3. BLUE/GREEN fork-green + flip                         (schema-BREAKING releases)
```

- Forks make BLUE/GREEN nearly free: green = instant fork of blue INCLUDING data; the flip
  is a Rediacc-proxy weight change (renet owns routing; bundled Traefik/ServiceLB are
  disabled in favor of the Rediacc proxy); rollback = restart the untouched CoW parent.
  Honest caveat to document: the fork moment splits history — post-flip writes do not exist
  in blue; the rollback window is a POLICY. Zero-loss major DB upgrades: fork gives green
  its base instantly + logical replication (Postgres/MySQL native, cross-version) streams
  the delta until flip.
- CANARY deliberately does NOT use forks (canary users on forked data would read stale data
  and write into a doomed copy). Canary = two Deployments behind one Service with proxy
  weights; the expand-contract schema discipline is the application's burden — say so.
- v1 implementation (BUILT, but see the B1 note above): rung 0 (auto-snapshot before release
  verbs) + rung 1 (`cluster rehearse`) + canary weight templating. No heavy `release`
  orchestrator verb; the primitives compose, and rung 3 (blue/green) composes from them with
  no dedicated verb in v1. As-built, the canary overlay emits `rediacc.canary_of` and
  `rediacc.weight` annotations, and renet's router turns them into a Traefik **weighted
  service** splitting stable and canary; that backend is real and has a production caller.
  What has never happened is an end-to-end weight flip against a live cluster.

## 3. PV LUKS (per-repo encryption for k8s data) — DECIDED: per-volume LUKS images

- Review F8 settled the P0 decision on capacity grounds, not just encryption: bare folders
  on shared BTRFS have NO capacity enforcement (any pod can fill the datastore for every
  repo) and kubelet statfs reports the whole datastore to every PVC. **Fixed-size
  per-volume LUKS images** restore real quota + honest metrics + at-rest encryption in one
  primitive — the exact property set the docker world's repo images already have. Reflink
  of a LUKS image works identically; per-repo credential as passphrase.
- Residual P0 detail: verify kubelet volume-stats behavior for `local` PVs over loop-mounted
  images (expected: correct, since each volume is its own filesystem).
- Complements: secrets-from-config (02 §4) + optional k3s `--secrets-encryption` close the
  kine plaintext exposure.

## 3b. Thin node-local CSI driver: BUILT (spec + as-built record: `spec/09-csi-driver.md`)

What the redesign deletes is ceph-csi + RADOS namespaces (the wrong-layer integration),
NOT the CSI interface. The thin node-local CSI driver `csi.rediacc.io` recovers the k8s
ecosystem surface over the identical layout. **It shipped in P3 and is proven live.**
`spec/09-csi-driver.md` is the authority; this is the summary.

- provision = create a per-volume LUKS image at `<ds-mount>/repos/<repo>/volumes/<pvc>.img`
  (mounted outside the repo folder, per the C1 layout in 02 §1)
- topology = the existing `rediacc.io/ds-<name>` node label (no RBD, no RADOS, nothing external)
- snapshot and clone = reflink, exposed through the STANDARD VolumeSnapshot and
  `dataSourceRef` APIs, so velero, operator-integrated backups, and dynamic PVCs work again.
- No novel sidecar was needed: the snapshot and provision paths are the STOCK
  external-snapshotter and external-provisioner in their distributed (`--node-deployment`)
  mode. The only new code is one gRPC server over the existing `pkg/kubevolume` LUKS
  primitives.
- **Deployment shape: EVERYTHING runs host-side under systemd.** The driver is a renet
  subcommand (`renet kube csi-serve`); the provisioner, snapshotter, and snapshot-controller
  are embedded upstream binaries driven with `--kubeconfig`. **Zero container images**, so no
  privileged hostPath system pods and no fork-time ImagePullBackOff. The driver
  **self-registers** with no node-driver-registrar. k3s ships no snapshot machinery, so renet
  installs the VolumeSnapshot v1 CRDs and the snapshot-controller at cluster install.
- **Enablement is automatic and symmetric.** It folds INTO `kube install` (cluster objects)
  and `datastore attach` (node units plus the per-datastore StorageClass), and OUT of
  `datastore detach` and `kube uninstall`. Zero manual steps: a cluster create logs
  "CSI driver enabled" and the driver is there.
- LUKS keys stay in the datastore-side keyfile model, **never in k8s Secrets**, so the fork
  secret scrub can never orphan a volume.
- Volume EXPANSION remains out of v1 (`allowVolumeExpansion: false`; the external-resizer has
  no distributed mode).

**Conformance: csi-sanity 48/50**, with the two residuals ruled as documented deviations:

- **CSI-DEVIATION-1**: an over-long volume name is **cleanly rejected**, not truncated. The
  kernel caps device-mapper names at 128 characters and CSI permits 128-character volume
  names, so the two cannot both be honoured. A loud reject beats a silent truncation
  collision. The relevant csi-sanity spec stays red **by design**; that is the documented
  price, not a bug.
- **CSI-DEVIATION-2**: CreateSnapshot idempotency is a size proxy rather than true
  provenance. Accepted with its mitigation documented.

**Live battery**: dynamic PVC bound in roughly 20 seconds to a LUKS image, pod wrote and read;
VolumeSnapshot reached `readyToUse`; restore proven **point-in-time** (state A restored while
the original had moved on to state B); clone proven **independent**. Three live-only bugs were
caught and fixed in that window (a provisioner NAMESPACE env, an ExtractSidecar ETXTBSY race
fixed with an atomic rename, and an immutable-CSR delete-before-create).

**Two residuals, open:**
1. **Multi-node worker attach** (spec/09 §14 item 12): worker nodes currently no-op on the
   auto-enable fold. P4.
2. **B2: no stock Helm chart has ever been installed against the driver.** The dynamic-PVC
   capability is genuinely proven, but by hand-rolled manifests. A stock chart is what
   exercises a **StatefulSet's `volumeClaimTemplates`** (generated PVC names, ordinal pods)
   against WaitForFirstConsumer and `storageCapacity`, which is materially different plumbing
   and is the entire F6 ecosystem-compatibility claim that justified building CSI. This is
   EXIT-blocking (09 §2).

## 4. RWX shared volumes (researched 2026-07-10; keep out of v1)

- CephFS writable clones are still ASYNC FULL COPIES as of Tentacle v20.2.x (releases only
  added clone management: `pause_cloning`, clone-source info). Snapshots are instant but
  read-only; ceph-csi's snapshot-backed shallow volumes are RO.
- JuiceFS is the only CoW-RWX option found: `juicefs clone` is metadata-only
  (redirect-on-write), seconds regardless of size, CSI with RWX, Apache-2.0, data on object
  storage (could sit on Ceph RGW) — but needs a separate metadata engine (Redis/Postgres/
  TiKV) = new stateful operational surface, close-to-open consistency.
- Verdict: RWX stays OUT of v1. If forkable RWX becomes a requirement, pilot
  JuiceFS-on-RGW as a separate tier next to RBD. Document RWX absence honestly.

## 5. Demo strategy (composes from the above; for marketing later, NOT in program scope)

1. Time machine: boot an ephemeral cluster fork from any retained historical group snap.
2. Drop the production database live on stage; parent untouched (launch hook).
3. Upgrade rehearsal with a stopwatch (practitioner closer).
4. AI agent sandbox: agent on a secretless ROLE=fork clone; repo diff/merge promotion.
5. Twelve month-end forks = year-over-year analytics without a warehouse.
6. Measured datacenter move (stopwatch cutover, rehearsed destination).
7. Per-PR production clones in CI.
Three-beat structure: expensive→instant, dangerous→safe, parent never notices. All numbers
measured live (no fabricated benchmarks — hard rule).

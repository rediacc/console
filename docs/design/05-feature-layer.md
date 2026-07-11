# 05 — Feature Layer (v1 scope, on top of the core)

User decision 2026-07-10: the feature layer ships IN this program (not deferred), gated
behind the core (P3 cannot start before the P2 gate).

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
- v1 implementation: rung 0 (auto-snapshot before release verbs) + rung 1 (`cluster
  rehearse`) + canary weight templating. No heavy `release` orchestrator verb yet; the
  primitives compose; `rdc repo release --strategy` can come later.

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

## 3b. Thin node-local CSI driver (review F6, adopted — P3; spec: spec/09-csi-driver.md)

What the redesign deletes is ceph-csi + RADOS namespaces (the wrong-layer integration),
NOT the CSI interface. A thin, node-local CSI driver (`csi.rediacc.io`) over the identical
layout recovers the k8s ecosystem surface at modest cost:
- provision = create a per-volume LUKS image inside `<ds-mount>/repos/<repo>/volumes/`
- topology = the existing `rediacc.io/ds-<name>` node label (no RBD/RADOS/external anything)
- snapshot = reflink; clone = reflink — exposed through the STANDARD VolumeSnapshot /
  `dataSourceRef` APIs, so velero, operator-integrated backups (CNPG volumeSnapshot), and
  dynamic PVCs work again, and forks get a k8s-native API surface (the best demo surface).
- Research correction (2026-07-11): no novel sidecar is needed — the snapshot path is the
  STOCK external-snapshotter in its distributed (`--node-deployment`) mode, same for
  external-provisioner; the only new code is one gRPC server (~8 real RPCs) over the
  existing `pkg/kubevolume` LUKS primitives. Precedent for the shape: rancher
  local-path-provisioner (size), csi-driver-host-path distributed deployment (mechanics).
- Deployment shape (spec 09 §1): EVERYTHING runs host-side under systemd (driver = a renet
  subcommand; provisioner/snapshotter/snapshot-controller = embedded upstream binaries
  with `--kubeconfig`) — zero container images, so no privileged/hostPath system pods and
  no fork-time ImagePullBackOff. k3s ships NO snapshot machinery: renet installs the
  VolumeSnapshot v1 CRDs + snapshot-controller at cluster install.
- Volume expansion is explicitly OUT of v1 (`allowVolumeExpansion: false`; external-resizer
  has no distributed mode). LUKS keys stay in the datastore-side keyfile model — never in
  k8s Secrets, so the fork scrub can never orphan a volume.
Staging (adopted middle path): static `local` PVs remain the v1 FLOOR (P1); P1 designs the
volume path/naming layout to be CSI-adoptable WITHOUT migration; the driver itself ships in
P3 as a feature-layer citizen (a better one than the release ladder). Ceph stays strictly
below throughout — CSI is only the interface. Cost ~3-5 weeks of Go; the alternative is
permanently telling k8s users their charts and backup tooling do not work here.

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

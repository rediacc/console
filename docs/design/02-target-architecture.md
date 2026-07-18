# 02 — Target Architecture: the Datastore-Centric Model

**Status: AS-BUILT.** This model is implemented and proven live (P1-P3). Where the build
corrected the design, the corrected version is stated here and the original is noted.

Decision (user, 2026-07-10): rebuild the Kubernetes storage layer around the datastore, the
same way the docker world already works. Push Ceph back BELOW the repo layer. One storage
philosophy for both worlds.

## 1. The hierarchy

```
machine  →  DATASTORE (named, mobile, single-mounter)  →  repos
```

- **Datastore** = a self-contained pool: BTRFS inside ONE RBD image (Ceph backend) or a
  local device/loop file (local backend). Exactly ONE node mounts a datastore at a time.
  A machine can mount SEVERAL datastores (tiering: local-NVMe ds next to an RBD ds).
- **A named datastore mounts at `/mnt/rediacc-ds/<name>`** (P0 gate ruling R1). The original
  design said `/mnt/rediacc/ds-<name>`, which nests every named mountpoint inside the DEFAULT
  datastore's own BTRFS mount: named attaches would then require the default mounted,
  `detach default` would hit EBUSY under any named mount, and exhausting the default pool
  would break named attach. That is exactly the blast-radius coupling `ds-control` exists to
  avoid. The sibling scheme keeps every property the design wanted (deterministic from the
  name, identical across machines so kine PV specs never need rewriting, per-machine collision
  refusal).
- **Repos are placed IN a datastore**, not on a node. A repo's home node = whoever currently
  mounts its datastore. Docker repos stay exactly as today (LUKS image file in the
  datastore). K8s repos become **folders in the datastore**, one per-volume LUKS image per
  declared PVC:

  ```
  <ds-mount>/repos/<repo>/volumes/<pvc>.img      the image (inside the forked unit)
  <ds-mount>/mounts/volumes/<repo>/<pvc>/        where it is mounted (OUTSIDE it)
  ```

  **The mounts live OUTSIDE the repo folder** (P0 gate ruling C1). The fork unit is ONE
  reflink of `repos/<repo>`; a live ext4 mountpoint inside that tree makes
  `cp --archive --reflink=always` either fail (reflink cannot cross filesystems) or, under any
  fallback, byte-copy decrypted plaintext into the fork. The invariant is: **no mountpoints
  inside `repos/<repo>/`**. This mirrors the docker world exactly (image files in the pool, a
  `mounts/` tree outside the snapshotted unit) and keeps PV objects stable across cluster
  fork and migrate, since they reference the deterministic mount path.
- **The cluster control-plane's k3s data-dir lives INSIDE a datastore too** — in a
  dedicated `ds-control` **by default** (review F8: if the CP shares a data pool, any repo
  filling its datastore takes the control plane down with it). Agent node dirs are demoted to
  **disposable local cache**: never forked, never transferred, never backed up; agents
  REJOIN after fork/migrate using the CA-derived token (fork mints a fresh one from the NEW
  CA; migrate reuses the preserved one).

  **As-built inconsistency, open for P4 (bug #25).** `cluster create` still builds a per-node
  agent repo (`createNodeImage`) and then passes the CONTROL datastore's mount to that node's
  `kube_join`, so the repo goes unused and the agent's data-dir lands on the root filesystem,
  contradicting its own comment. `cluster join` meanwhile uses the per-node repo. Two join
  paths, two behaviours, dead state. Given that agents ARE a disposable cache, the resolution
  P4 should consider first is **deleting the vestigial repo**, not fixing the mount.

```
CEPH POOL
 |-- RBD image: ds-alpha ─┐   each datastore = ONE RBD image, BTRFS inside,
 |-- RBD image: ds-beta  ─┤   repos as reflink-forkable folders/images within
 `-- RBD image: ds-gamma ─┘

K8S CLUSTER
 node-1 ── mounts ds-alpha ── repos: shop, mail        (+ CP data-dir in ds-alpha)
 node-2 ── mounts ds-beta  ── repos: gitlab
 node-3 ── mounts ds-gamma ── repos: analytics
```

## 2. PV/PVC: keep the interface, delete the machinery

- **PVC stays** (Helm-chart compatibility; Pod Security "restricted" forbids pod-level
  hostPath but allows binding admin-created PVs).
- Renet statically generates **upstream `local`-type PVs** (which REQUIRE nodeAffinity —
  built exactly for node-attached storage) pointing at
  `<ds-mount>/mounts/volumes/<repo>/<pvc>`, with affinity to a node label
  `rediacc.io/ds-<name>`.
  **As-built gap, open for P4 (carry-in 6):** `datastore attach` does NOT stamp that label
  today, so a node-pinned PV will not bind until something else does. The e2e suites had to
  call `kube_node_label` by hand. The fix belongs folded into renet's `datastore attach`
  (mirroring the CSI symmetric fold), with detach stripping it. Not CLI porcelain, which P4's
  reshape would throw away. Do not defer past P4: the failure mode is silent, with pods
  sitting Pending forever and no error naming the missing label.
- Pod placement is automatic: volume-claiming pods pin to the datastore's node via
  volume-topology-aware scheduling; stateless pods float and reach state via Services
  (that IS "write forwarding" — no feature needed).
- Read scaling: app-level replication first; snapshot-based read-only attaches
  (`--writes local`, refreshed on a cadence) for staleness-tolerant reads; productized as
  `repo replicate` (05).
- **Binding mechanics (review F5)**: one `no-provisioner` StorageClass per datastore
  (`rediacc-ds-<name>`, `volumeBindingMode: WaitForFirstConsumer`); every generated PV and
  declared PVC references it. This makes static binding deterministic and scheduler-aware,
  and prevents a default StorageClass from adopting SC-less PVCs into a nonexistent
  provisioner (pods pending forever). Volumes are **per-volume LUKS images**, not bare
  folders (review F8): a fixed-size image restores real capacity enforcement and honest
  kubelet statfs (a folder on shared BTRFS reports the whole datastore's size to every PVC
  and lets one pod fill the pool for all repos). This also resolves the 05 §3 encryption
  decision in the same stroke.
- **Chart-compatibility honesty (review F5/F13), REVISED by the CSI build**: the original
  limits below described the STATIC-ONLY model, and the CSI driver (P3) lifts most of them.
  Stating both, because the exact boundary is what a chart author needs:
  - *Static PVs alone*: plain Deployment+PVC apps work; StatefulSet `volumeClaimTemplates`
    work only with name-coupled pre-created PVCs (`<template>-<sts>-<ordinal>`) and break past
    the declared count; runtime-provisioning operators (CNPG, Strimzi, Elastic) do NOT fit.
  - *With the CSI driver*: dynamic provisioning, VolumeSnapshot, and clone-from-PVC all work,
    so operator workloads and velero-style tooling come back. That is the entire F6 rationale
    and it is why CSI was built.
  - **Still unproven (B2)**: no stock Helm chart has ever been installed against the driver.
    The StatefulSet `volumeClaimTemplates` path specifically (generated PVC names, ordinal
    pods, interacting with WaitForFirstConsumer and `storageCapacity`) is the one that a
    hand-rolled manifest cannot demonstrate by construction. Until B2 runs, treat
    chart-compatibility as expected-but-unverified rather than proven.
  - Unchanged either way: cluster-scoped resources (CRDs, webhooks, ClusterRoles) live outside
    the namespace-repo boundary, and `repo up` warns on cluster-scoped kinds in manifests. The
    documented compatibility matrix remains a P7 deliverable, and it should be written from
    B2's results.
- **CSI path (review F6): BUILT in P3.** Static PVs remain the v1 floor, and the thin
  node-local CSI driver `csi.rediacc.io` now ships alongside them: provision = create a
  per-volume LUKS image in the repo folder; topology = the `rediacc.io/ds-<name>` label;
  snapshot and clone = reflink, exposed through the standard VolumeSnapshot and
  `dataSourceRef` APIs. This recovers dynamic PVCs, operator workloads, and velero-style
  tooling while keeping Ceph strictly below. What got deleted was ceph-csi and RADOS
  namespaces, not the CSI interface. Spec and as-built record: `spec/09-csi-driver.md`;
  summary in 05 §3b. Enablement is automatic (it folds into `kube install` and
  `datastore attach`), and the driver is conformance-tested (csi-sanity 48/50, two ruled
  deviations).

## 3. Datastore mobility = the multi-node story

- **Failover/relocation — the codified sequence (review F3/F12)**. Kubernetes does not
  evict pods on a label change, the unreachable-node taint waits 300 s, and StatefulSet
  pods are deliberately NEVER force-deleted by the controller (they hang Terminating until
  the Node object goes away). The fencing is exactly what makes force-release safe, so the
  order is load-bearing:
  1. planned move: drain (or per-repo `down()`) first; node failure: skip to 2
  2. fence the old node (RBD `exclusive-lock` + osd blocklist)
  3. **delete the stale Node object** (force-releases StatefulSet pods)
  4. remove the `rediacc.io/ds-<name>` label from the old node BEFORE labeling the new one
     (a double-label window schedules pods onto a node with no mounted path)
  5. detach → attach on the new node → add the label; pods reschedule
  Decide repo-pod `tolerationSeconds` defaults in P0. Attach refuses name collisions (a
  machine can never mount two datastores with the same mount-path name — matters for the
  "one beefy dest machine" fork case). Zero data copy; "seconds" applies to the storage
  remap — pod rescheduling adds scheduler latency, stated honestly. This replaces pod-level
  RWO mobility as the product's multi-node answer for stateful workloads (SAN-LUN model).
  Enable `exclusive-lock` (+`layering`) on datastore RBD images so the storage self-defends
  (today's per-PVC images have layering only).
- **THE HOLDER TAXONOMY (as-built; the P3 campaign's cleanest conceptual result).** The
  design assumed releasing a datastore was a matter of unmounting it. It is not. **Four
  distinct classes of thing can hold a datastore open**, each invisible to the others'
  diagnostics, each needing a different remedy. A shared node-side teardown primitive must
  handle all of them, **in this order**, and every storage-releasing verb (`cluster evict`,
  `datastore detach`, `cluster migrate`, `kube uninstall`, `repository down`) must route
  through it. Building that primitive is P4 work; today the handling is scattered.

  1. **Kernel submounts.** And note the trap that cost this program a full diagnostic cycle:
     k3s containerd overlays live at `/run/k3s/...`, **OUTSIDE the datastore path**, and hold
     it busy through their `lowerdir` OPTIONS. A filter that unmounts "everything under
     `<mount>`" misses them entirely, because the busy holder has no mountpoint under the
     datastore at all. Match the mount string **anywhere in the `/proc/mounts` line**, and
     unwind deepest-first.
  2. **Host processes.** The CSI trio (driver, provisioner, snapshotter), whose socket and
     `--kubelet-root` live INSIDE the datastore. This was **bug #26**, and it is the one that
     actually blocked the releases: `kube install` started those units and **nothing ever
     stopped them** (`RemoveNodeUnits` existed with zero callers), so every storage-releasing
     verb was correctly refused by the no-lazy-success guard, with no mount holder to find.
     Fixed by a symmetric fold (detach and `kube uninstall` now stop them), but the primitive
     must own it rather than leaving it in two call sites.
  3. **Device stacks.** A per-volume LUKS loop plus dm-crypt left open, with **no mountpoint
     to find**. Its CAUSE was **bug #28**: `repository down` was dying at the namespace delete
     and never getting as far as releasing the stack. #28 is the cause; this class is the
     symptom.
  4. **An open dm device with no userspace owner**: open-count above zero after a successful
     unmount, with no mount, no loop, and no process. This is **bug #29**, still unexplained
     (btrfs's scanned-device cache was the leading hypothesis and was refuted by controlled
     experiment). A post-failure probe is wired, so the next occurrence names the holder.

  The lesson generalizes past storage: a release path that reports "target is busy" without
  naming the holder is a diagnostic dead end. Make failing diagnostics print what they found.

- Repos in one datastore move/fail over/snapshot TOGETHER (placement = a real decision;
  more, smaller datastores mitigate). Cross-datastore repo moves = `repo push` (copy),
  same rule as cross-machine today.
- Same-datastore repos fork against each other instantly (reflink inside the shared BTRFS);
  cross-datastore forks = push or the dm-COW borrow.
- **Node lifecycle: graceful shutdown/boot (the docker world's mechanism, extended)**.
  The docker world already has down()-hooks + LUKS unmount + systemd-ordered teardown on
  machine restart, and autostart + reconcile on boot. The cluster analog is required work:
  a renet shutdown unit ordered before the mounts that (1) gracefully stops the node's
  pods honoring terminationGracePeriod — NOTE the k3s trap: stopping the k3s service
  deliberately does NOT stop containers (k3s-killall.sh territory), so a naive reboot
  yanks pods in undefined order vs volume unmounts — (2) stops k3s, (3) unmounts
  per-volume LUKS images + detaches loops (03 hygiene rules), (4) detaches datastores
  (btrfs unmount, RBD unmap, exclusive-lock RELEASE — a cleanly rebooted node needs no
  fencing on return). Boot reverses: re-attach from the state bucket, verify locks, stamp
  ds labels, mount volumes, start k3s; the reconcile timer generalizes to clusters (same
  convergent self-heal contract as docker repos). Power loss stays crash-consistent by
  contract; graceful restart buys clean unmounts, no unmap-after-network-loss hangs, and
  fenceless fast rejoin.

## 4. Secrets and the role contract

- **Secrets never live in the image or in kine.** Extend the docker model to k8s: per-repo
  secrets in the CLI config, materialized as k8s Secret objects at `up()` time. Optionally
  enable k3s `--secrets-encryption` for whatever remains in kine.
- Policy: **migrate = same principal → secrets re-inject automatically; fork = new
  principal → empty secret map** (docker rule holds for namespaces and clusters).
- **Making the fork policy TRUE requires two scrub steps (review F1/F2 — F1 is the
  program's only blocker)**:
  1. **PKI regeneration on fork**: the CP data-dir carries the cluster CA private key and
     the service-account signing key; preserving them (as the current identity-rewrite
     does) makes every fork a PERMANENT admin credential for the PARENT cluster — anyone
     holding a fork can mint system:masters certs or valid join tokens the parent accepts.
     CA preservation is correct for MIGRATE only (same principal). Fork identity-rewrite
     deletes the tls dir so k3s re-mints CA + SA keys on first boot (agents rejoin fresh
     anyway; pods restart anyway; stored legacy SA-token Secrets are swept). The k8s analog
     of the docker world regenerating the SSH keypair on fork. P0 blocking spike verifies
     k3s regenerates cleanly from an existing kine DB with tls/ removed.
  2. **Secret scrub on fork**: kine rides the group snapshot with every materialized k8s
     Secret in it (rediacc-injected AND operator-created: cert-manager keys, generated DB
     passwords). Rediacc labels its injected Secrets at up() time so they are enumerable;
     fork identity-rewrite deletes them, and the default for third-party Secrets under
     ROLE=fork|rehearsal is scrub-all. The ROLE ConfigMap is rewritten in the same step
     (otherwise the fork boots claiming role=primary). k3s --secrets-encryption does NOT
     substitute: its key material lives in the same data-dir and forks with it.
  Both scrubs are RepoRuntime contract-test invariants (02 §9), not conventions.
- **REDIACC_ROLE contract** (effect isolation, the thing CoW cannot give):
  `REDIACC_ROLE=primary|fork|rehearsal`, `REDIACC_WRITES=ceph|local`,
  `REDIACC_DATASTORE=<name>` injected into (a) Rediaccfile `up()/down()/health()` env and
  (b) a per-namespace ConfigMap pods can `envFrom`. Apps gate outbound side effects
  (webhooks, emails) on role. Generalizes the existing `IsFork`/`GrandGuid` state.

## 5. Encryption scoping (user decision)

- Datastore itself: UNENCRYPTED (same as docker world; the pool was never the boundary).
- **Repos are the encryption boundary**: docker repos keep LUKS as today; k8s repo data
  gets per-repo LUKS on its PV images (see 05 feature layer); control-plane kine exposure is
  closed by secrets-from-config + optional k3s secrets-encryption. Node dirs stay plain
  (infrastructure).

## 6. Delete / keep ledger

DELETE (from renet + CLI):
- ceph-csi templating and lifecycle, per-namespace StorageClasses + snapshot classes,
  synthetic clusterIDs, RADOS-namespace machinery (EnsureNamespace/CloneNamespace/
  drainRadosNamespace/`NamespaceTeardownLeak` and the 2026-07-10 hardening around it),
  `.rbd-backend.json` markers, the dual PV backend + `resolvePVBackend`,
  per-PVC `.img` files + `pv/` + `pv-mounts/` trees, `materializeAndBindPVs` hostPath path,
  per-node agent images as first-class repos, `config machine set-ceph` (Ceph becomes a
  datastore-backend property), `datastore unfork` (becomes `detach --discard`).

KEEP:
- The docker repo model, branching family, checkpoint/CRIU, push/pull/migrate data planes
  (FIEMAP delta), the manifests layer, `kube_identity_rewrite` + `kube_prep_fork`,
  crash-consistent CoW semantics, BTRFS datastore snapshots, the zot pull-through cache,
  the Rediacc proxy/routing model, guardrails (grandGuard/agentBlocked + ancestry-verified
  overrides).

NEW (all of the following are BUILT):
- Named multi-datastore registry (config + on-machine state), datastore
  create/attach/detach/fork/snapshot verbs with the `--writes` contract (03),
  RBD group snapshots (03), anchor+rejoin cluster fork/migrate (04), lifecycle health gate
  (04), role-env injection, secrets-to-k8s injection, `repo replicate`, `cluster rehearse`,
  release helpers, PV LUKS (05), a datastore-backed registry so locally built images ride the
  datastore rather than the disposable agent cache (04 §7b), and the thin node-local CSI
  driver (05 §3b, spec/09).
- **`datastore adopt` and `datastore forget` (not in the original design; discovered by the
  build).** The design assumed a cloned datastore was reachable from any machine that can
  reach Ceph. It is not: the datastore RECORD lives in the SOURCE machine's registry, so a
  cross-machine `datastore attach` on the destination failed with "not registered on this
  machine" even though the rbd clone sat in shared Ceph (bug #14, the architectural blocker
  that stopped the first live fork). `adopt` registers a record ferried from the source (two
  shapes: a fork record, and a `--plain` arm for migrate); `forget` removes a registry record
  without deleting data, and refuses while the datastore is attached. Together they are what
  makes the single-mounter invariant hold across a fork or a migrate.

## 7. Default datastore: implicit for docker, EXPLICIT for kubernetes

`rdc machine add` + `machine setup` auto-create a `default` datastore (local backend,
`/mnt/rediacc` — the same path as today). Docker `repo create --machine M` lands there.
A single-machine docker user never types, sees, or learns about datastores; their workflow
is identical to today. `datastore create` exists only for ADDITIONAL named datastores
(RBD-backed, tiering, second pool) — explicit opt-in, same philosophy as named configs.

**Kubernetes repos MUST name their datastore explicitly** (user decision 2026-07-10).
Rationale: in a cluster, datastore choice IS the placement decision — home node, failover
blast-radius group, fork-affinity group (same-datastore repos fork instantly against each
other), consistency-snapshot group — and it is nearly immutable (moving = a copy).
Consequential + hard-to-reverse = explicit, the same principle behind the fork-attach
`--writes` requirement and the required KVM net topology. A "default to the only datastore"
rule is rejected: scripts working on a one-datastore cluster would silently change meaning
when a second datastore appears. No cluster-level default-datastore setting in v1 (it would
reintroduce silent co-location; may be added later as a consciously-declared opt-in).

**Placement is a tagged union in the schema (review R2-F1 — blocker fix)**: N machines each
auto-creating a datastore literally named `default` would break the names-unique-per-config
invariant that lets `--datastore` alone determine cluster/node/tier. Resolution: default
datastores are IMPLICIT — they never enter the datastore registry. Placement is stored as
`placement: { datastore: <name> } | { machine: <name> }`, where the machine arm means
"that machine's implicit default datastore". This mirrors the two `repo create` flags
one-to-one, keeps name-uniqueness for NAMED datastores only, and needs a two-arm resolver
instead of string special-casing. `repo create` takes exactly ONE placement flag:
`--machine M` (docker shortcut → machine arm) or `--datastore D` (docker tiering AND the
only k8s form; `--cluster` on create dies — the datastore implies its cluster). Error
message teaches: "a cluster repo needs a home: pick a datastore (rdc datastore list
<cluster>)". Additional refusal (R2-F12): `--machine` pointing at a machine that carries a
cluster membership backref refuses with the same teaching error — otherwise a user
intending a k8s repo gets a silent wrong-world docker repo on that node.

## 8. Repo isolation model in Kubernetes (parity with the docker world)

The docker world isolates repos three ways: processes (per-repo dockerd), filesystem
(per-repo LUKS image + mount), network (per-repo loopback /26 — repos cannot reach each
other). The new k8s design must state its equivalent explicitly:

| Isolation | Docker world | K8s (new design) |
|---|---|---|
| Process | per-repo dockerd, kernel namespaces | pods/containerd (same kernel-namespace class) + k8s namespace boundary |
| Filesystem | LUKS image, own mount | pods receive ONLY volumes their PVCs bind (admin-created `local` PVs); PSA "restricted" forbids pod hostPath, so no pod can reach another repo's folder; at-rest via PV-LUKS (05) |
| Network | loopback /26 per repo | **renet-generated default-deny NetworkPolicy per repo namespace**: allow intra-namespace + DNS + ingress from the Rediacc proxy only. k3s enforces NetworkPolicy natively (kube-router controller with flannel). |
| Secrets | config-injected per repo, tmpfs/env | per-namespace k8s Secrets (config-injected, 02 §4) + namespace-scoped access |

The NetworkPolicy piece is NEW WORK (neither the current nor the draft design had it; k8s
pod networking is flat by default, which silently loses the docker world's guarantee).
It ships in P1 with the repo-as-folder work.

Hardening from review (F7/F9):
- **Scope**: default-deny is INGRESS-only (egress open — the docker /26 analogy is
  ingress-shaped; a deny-egress default breaks most apps). Stated, not implied.
- **The "allow proxy" rule needs a verified datapath** (P0 spike on a real KVM cluster):
  the Rediacc proxy is a HOST process, and flannel masquerades host→pod traffic depending
  on path, so an ipBlock rule either breaks or degrades to "allow all node IPs". Candidate
  fixes: run the proxy's cluster-facing leg as an in-cluster pod (label selector — robust)
  or pin proxy egress to a dedicated ipBlock-able address. Shipping an unverified "proxy
  only" rule would be a CLAIMED-false isolation promise, worse than the flat network.
- **PSA-independent backstop**: a ValidatingAdmissionPolicy in repo namespaces denying
  `hostPath` volumes and `hostNetwork` pods REGARDLESS of the namespace's PSA level. PSA
  `restricted` stays the default, but it breaks a meaningful share of real charts
  (runAsNonRoot, seccomp, drop-ALL), so the opt-down to `baseline` is allowed, audited —
  and the VAP keeps the filesystem/network isolation guarantee intact through it.
  (Whether PSA baseline restricts hostPath at all is a P0 verification item, not assumed.)
- hostNetwork pods bypass NetworkPolicy entirely — hence the VAP denial above.
Optional later: per-namespace ResourceQuota/LimitRange, namespace-scoped kubeconfigs.

## 9. The runtime abstraction: one contract, two implementations

Today the docker/k8s split is a flag-routing seam (CLI branches on `--cluster`;
`renet compose` vs `renet kube`) with no enforced contract — which is how the two worlds
drifted (secrets in config vs in kine; fork semantics diverging). The redesign formalizes
TWO ORTHOGONAL interfaces in renet:

- **`StorageBackend`** (exists half-formed in `pkg/datastore`: local | ceph): where bytes
  live; create/mount/snapshot/fork/attach semantics.
- **`RepoRuntime`** (new): how a repo runs. Contract (P0 spec finalizes):
  `Deploy(up)/Teardown(down)/Fork/Status/InjectSecrets/Health/ProvisionVolumes/
  ApplyIsolation`. Implementations: `DockerRuntime` (compose, per-repo dockerd, loopback,
  compose validation) and `KubeRuntime` (manifests, namespace, local PVs, NetworkPolicy).

Rules: a `RepoRuntime` never touches storage directly — it is handed mounted paths by the
datastore layer (Ceph stays below, invisible). Policy invariants live at the interface,
asserted ONCE for both worlds: fork ⇒ empty secret map; migrate ⇒ secrets re-inject;
ROLE/WRITES/DATASTORE env injected into every lifecycle hook; teardown must be
leak-reporting. **One shared contract-test suite runs against both implementations** — the
"same verb = same semantics" CLI principle (06) becomes mechanically enforced instead of
aspirational. A future runtime (RKE2 is the planned third distro; the distro interface
pattern in `pkg/kube/distro` is the precedent) implements the same contract.

## 10. Honest casualties (documented, accepted by user)

- **Pet nodes and no control-plane HA (review F11)**: datastore pinning is the SAN-LUN
  model — bin-packing for stateful pods is gone, and a hot node is relieved by moving a
  datastore, not a pod. kine/SQLite means a SINGLE-server control plane (k3s HA requires
  embedded etcd): the CP datastore's node is the cluster's availability, mitigated by fast
  fenced failover, not by consensus. Deliberate: kine is the RIGHT choice for this product
  — a single WAL-mode SQLite file is crash-consistent under a group snapshot in a way an
  etcd raft quorum never is. Do not "upgrade" to etcd for fork reasons.
- **k3s version skew (review F14)**: the datastore records the k3s version that wrote the
  CP data-dir; attach preflight enforces same-or-newer within the k8s skew policy; upgrade
  flow = upgrade CP binary in place (kine migrates forward), then agents. `cluster
  rehearse` before a k3s upgrade is the canonical use of the rehearse feature.

- RWX shared volumes: out of scope (see 05 for the CephFS/JuiceFS research verdict).
- Pod-level cross-node mobility for stateful pods: replaced by datastore-level mobility.
- ~~Dynamic PVC provisioning: static declared-PVC model stays~~ **RECOVERED**: the CSI driver
  shipped in P3, so dynamic PVCs, VolumeSnapshot, and clone-from-PVC all work. Static local PVs
  remain as the floor. Volume EXPANSION is still out (`allowVolumeExpansion: false`; the
  external-resizer has no distributed mode).
- Post-flip write loss on blue/green rollback is a policy window, not magic (05).

## 10b. Distro requirements: the `repoEmbeddable` gate survives, with a sharper contract

The old design gated cluster fork/migrate on `repoEmbeddable` for ONE reason (`--data-dir`
binds at start). The new design keeps the gate and widens the contract to FOUR
requirements, each tied to an adopted mechanism:

1. **Relocatable single state root** (`--data-dir`) — the CP data-dir in `ds-control`
   must boot from a different mount/machine after fork/migrate/failover. (kubeadm scatters
   state across /etc/kubernetes, /var/lib/etcd, /var/lib/kubelet: fails.)
2. **File-level crash-consistent state store** — the hot group-snap fork requires
   kine/SQLite (one WAL file, valid at any instant; R1-F11: do NOT switch to etcd).
   Vanilla etcd is identity-bound (member IDs, peer URLs) and a quorum has no atomic
   instant: fails.
3. **PKI re-mintable from the data-dir** — the F1 fork fix (delete tls dir, distro
   re-mints CA + SA keys on boot) is k3s behavior.
4. **Single-binary lifecycle** — renet runs the distro as one per-networkID systemd unit
   it can stop/recompose/start during identity rewrite.

**Terminology guard — provider ≠ distro.** `--provider` (kvm | a configured cloud
provider) is pure IaaS: it decides where MACHINES come from (local libvirt VMs or
OpenTofu-provisioned cloud instances). It never selects a Kubernetes: renet always installs
its own k3s onto the provisioned machines (Ceph pools first, then k8s pools). There is no
managed-Kubernetes (EKS/GKE/LKE) integration and none planned. k3s is to Rediacc what the
per-repo dockerd is in the docker world — an embedded runtime component, not a user
choice — and since k3s is CNCF-certified conformant Kubernetes, "only k3s" does not narrow
the workload surface: standard manifests, charts, and kubectl work identically.

Consequences: **k3s remains the only embeddable distro.** RKE2 (has a data-dir but is
etcd-ONLY, no kine — requirement 2 fails as stated) stays a planned third backend gated on
its own spike (single-server RKE2 with single-member etcd is plausibly crash-consistent
under a group snap, but IP-change restore needs etcd member surgery). The `external`
BYO-kubeconfig distro shrinks further: without renet-managed nodes and datastores it can
join none of the storage model — kubeconfig + healthcheck only, lifecycle verbs return
first-class "not applicable". Cluster fork/migrate/rehearse refuse non-embeddable distros
with a clear error, as today.

## 10c. The cost ledger of the k3s dependency (honest, user-reviewed)

Costs of OUR configuration (self-chosen; k3s merely makes them possible — they are the
price of file-level fork fidelity and are not renegotiable without losing the
differentiator): no control-plane HA ever (kine forbids etcd; external-SQL kine would
break state-in-one-datastore); a kine scale ceiling (dozens of nodes comfort zone, not
hundreds — compounded by datastore pinning); single-process blast radius (one binary =
apiserver+scheduler+controller upgrade/fail together; flip side: atomic, one systemd unit).

Costs of k3s the distribution (define who we cannot sell to, or taxes to budget):
- No FIPS-validated build, weaker CIS-default posture → regulated buyers are RKE2's, and
  §10b just made RKE2 harder (etcd-only). FIPS/CIS answer = "gated on a spike".
- No Windows nodes (RKE2 has them). Windows containers are out.
- ISV support matrices: workloads RUN (conformance), but vendors certify support
  contracts against OpenShift/EKS/AKS/GKE, rarely k3s — "unsupported platform" risk for
  customers running vendor-supported software. Most underrated sales objection.
- Bundled-component drift tax: we disable/replace Traefik/ServiceLB and ride
  flannel+kube-router specifics (the F9 datapath spike exists because of this); every k3s
  upgrade can shuffle that packaging.
- Single-steward risk: Apache-2.0 + CNCF-homed but SUSE/Rancher-driven; forkable = real
  but expensive escape hatch.
- Everything managed-k8s would have given us stays ours to build or skip: cloud IAM
  federation, managed upgrades, cloud LB controllers, autoscaler wiring, spot pools.
Noise tier: kine watch/compaction edges (visible mostly to watch-heavy operators who
already don't fit the static-PV model); "k3s is a toy" perception (sales objection;
conformance + fork demos are the rebuttal).

## 11. Config schema v3 (review round 2, findings folded 2026-07-10)

The redesign's config changes ship as **schemaVersion 3** with exactly ONE migration from
v2 and no v2 tolerance afterward (R2-F6 — "no backward compatibility" cannot mean "no
migration": the operator's live production configs must survive P4; the machinery exists
in `services/config/migrations/` + the `check:ci-config-migrations` gate). v3 contents:

1. **Spec/status split (R2-F2)**: mutable runtime state moves to a top-level `state`
   bucket — datastore attach/mounter, observed k3s versions, `memberIds`, networkId
   allocations, `pushState`, `headCommit`/`branches`/reflog, cert caches. Three documented
   properties: excluded from the version counter and from remote-config push (whole-config
   optimistic-version conflicts and audit noise come from status churn today); rebuildable
   via a new `config reconcile` verb backed by `renet list all --json` (the machine knows
   the truth); and treated as a ROUTING HINT — every derived-machine operation verifies the
   datastore is actually mounted where state says, and errors with a reconcile suggestion
   on mismatch. This is what makes dropping `-m` (06 §6) trustworthy: `config recover`
   restoring stale attach state must degrade to a clear error, never a wrong-host deploy.
   Bonus (R2-F8): with the counter and status out, the spec half becomes git-diffable and
   a future `config apply -f` (GitOps-lite) is nearly free — do not build it now, just do
   not foreclose it.
2. **One resource store, per-field encryption (R2-F3 — fixes a CONFIRMED data-loss bug)**:
   today `LocalResourceState.persist` (master-password branch) writes the encrypted blob
   and sets `resources: undefined`, while clusters/cloudProviders/backupStrategies are
   written plaintext into `cfg.resources` by a second path — so in encrypted mode, any
   repo/machine mutation after `cluster add` DESTROYS the cluster/provider/strategy
   records. The blob is also all-or-nothing and leaves `cloudProviders[].apiToken` and
   `credentials.cfDnsApiToken` outside encryption. v3: single persist path, per-FIELD
   encryption driven by the existing sensitivity registry (`schema/sensitivity.ts`),
   compound blob retired. Fixed within the redesign (user decision) — datastore records
   must be born into the unified store, never into the dual-path world.
3. **Structural repo tags (R2-F5)**: `repositories: Record<name, { tags: Record<tag,
   RepoRecord> }>` replaces composite `"name:tag"` string keys; the `latest` magic
   storage-layer default is retired (the resolver special-case pile — issue #495 lineage —
   stops growing). The 06 §6 grammar becomes data, not string-splitting.
4. **Names are identity — rename verbs dropped (R2-F4)**: repo→datastore→machine→cluster
   references are by name with no referential-integrity machinery; rather than build a
   transactional rename sweep, `machine rename`/`storage rename` are ELIMINATED (delete +
   re-add is the rename, acceptable for the sole-operator market and it kills the
   dangling-reference class outright).
5. **Secrets honesty (R2-F7)**: the write-only ceremony protects the config-file surface
   only — once materialized as k8s Secret objects, values are readable to anything with
   namespace access (docs must say so). File-mode secret size cap drops far below the
   current 10 MB (the config file is atomically rewritten and remote-pushed whole). The
   `UPPER_SNAKE → env|file` model gets a declared k8s mapping (Secret naming; file mode →
   volume mount), and re-running `up()` re-injects idempotently — that IS the rotation
   story, stated.
6. **Residue sweep (R2-F9)**: `DefaultsSchema.machine` (a lingering default-machine
   context contradicting the no-mutable-context decision) and the `team`/`region` keys in
   `config set/clear` (dead cloud-adapter vocabulary) are deleted in P4.
7. Confirmed keeps: the single flat JSON file per named config (locking, atomic writes,
   deterministic ordering — right at this scale), named config FILES over kubeconfig-style
   contexts, write-only secrets with TTY/agent reveal gating, the hash-chained audit log.

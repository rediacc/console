# P3 Spec 09 — Thin Node-Local CSI Driver (`csi.rediacc.io`)

Implementation spec for the P3 feature-layer CSI driver adopted in
`docs/design/05-feature-layer.md` §3b (review F6). It builds on the CSI-adoptable
volume layout ruled in `docs/design/spec/05-k8s-templates-and-fork-hygiene.md` §2,
which the driver adopts UNCHANGED. Code citations are against the current tree
(console worktree `0707-1`, renet submodule as checked out there). Decisions this
document makes are tagged **[CSI-DECIDED]**; unresolved residuals are collected in
§14. Sources for every externally-verified claim are in the dated appendix (§15) —
the builder needs no web access.

Naming: `<ds>` = datastore name, `<repo>` = repo name (= its k8s namespace; a fork
namespace is `<repo>-<tag>`), `<kubelet-root>` = the node's relocated kubelet root
directory. Driver name: **`csi.rediacc.io`** (matches the StorageClass provisioner
name reserved in spec 05 §2).

---

## 0. What this driver is and is not

- It is a **node-local, reflink-native CSI driver over the spec-05 layout**:
  provision = create a per-volume LUKS2 image in `<ds-mount>/repos/<repo>/volumes/`,
  stage = LUKS open + mount, snapshot/clone = `cp --reflink=always`, topology = the
  existing `rediacc.io/ds-<ds>` label. Ceph stays strictly BELOW the datastore; the
  driver never sees RBD, RADOS, or anything ceph-csi touched (delete-ledger guard,
  §11).
- It is **additive**: the static `rediacc-ds-<ds>` no-provisioner class and its
  generated `local` PVs (spec 05 §1c/1d, `pkg/reporuntime/kube_templates.go:230-283`)
  remain the v1 floor and stay valid indefinitely. Repos opt into dynamic
  provisioning by declaring the CSI class `rediacc-csi-<ds>`.
- What it recovers: dynamic PVCs (plain charts AND runtime-provisioning operators),
  `VolumeSnapshot`/`dataSourceRef` as the standard fork/backup API surface (velero,
  CNPG volumeSnapshot backups), and honest per-volume metrics via
  `NodeGetVolumeStats`.
- Out of v1 [CSI-DECIDED]: volume expansion (§3 note E), RWX (05 §4 verdict holds),
  inline ephemeral volumes, volume groups (§14 item 8), ListVolumes/ListSnapshots.

## 1. Architecture [CSI-DECIDED]: everything runs HOST-SIDE; zero container images

The entire CSI deployment is **host processes under systemd**, rendered and
installed by renet exactly like the per-repo zot units
(`pkg/kube/registry/zot.go:210-230, 328-340` — unit render + `writeUnitIfChanged`
pattern) and the per-networkID k3s units. **No component runs as a pod.**

Why this is the only shape that fits (argued, not asserted):

1. **The single-mounter datastore model makes provisioning node-local.** A volume
   image can only be created/opened on the node that currently mounts its
   datastore. The upstream answer for exactly this shape is *distributed
   provisioning*: external-provisioner and csi-snapshotter both ship a
   `--node-deployment` mode where one instance runs next to the driver on every
   node and claims only the PVCs/snapshots whose selected node is its own (§15
   sources 2, 3). No central controller, no leader election, no renet-mediated
   remote exec.
2. **A pod-based deployment contradicts the product's own bans.** CSI node pods
   universally require `hostPath` mounts of the kubelet dir, privileged mode, and
   bidirectional mount propagation — the exact constructs `lintSecurity`
   (`pkg/kube/manifest.go:111-131`) and the PSA/VAP layer (spec 05 §1b) exist to
   deny. Host processes need none of it. (The lint applies to the repo-manifest
   render path, not to renet's own `applyClusterScoped` kubectl seam,
   `pkg/reporuntime/kube.go:435-440` — but nothing renet ships should model the
   anti-pattern it forbids.)
3. **Container images would break on fork.** Agent containerd stores are
   disposable cache (02 §1): a cluster fork boots fresh agents, and every
   system-component image would ImagePullBackOff exactly like the rejected
   ctr-import path for repo images (spec 05 §5). Host binaries embedded in renet
   (`pkg/embed` pattern, `embed.go:30-43`) ride the renet deploy pipeline instead
   and exist by construction on every node.
4. **Precedent for the size claim**: rancher/local-path-provisioner is ~a few
   thousand lines for provision/delete only (not CSI, no snapshots); topolvm and
   openebs/lvm-localpv are full CSI drivers whose node-local shape matches ours
   but who carry an LVM daemon layer we do not need — `pkg/kubevolume` already IS
   our "lvmd". The genuinely new code is one gRPC server exposing ~8 real RPCs
   over existing primitives.

### Process/unit table

| Unit | Binary | Runs on | Started by | Flags (core) |
|---|---|---|---|---|
| `rediacc-csi.service` | renet itself: `renet kube csi-serve` | every node currently mounting ≥1 datastore | datastore attach (restart on attach/detach to re-register topology); removed when last datastore detaches | `--node-name <k8s-node>`, `--kubelet-root <kubelet-root>` |
| `rediacc-csi-provisioner.service` | embedded `csi-provisioner` (external-provisioner **v6.3.0**) | same nodes | same lifecycle | `--csi-address <sock>`, `--node-deployment`, `--enable-capacity`, `--capacity-ownerref-level=-1`, `--extra-create-metadata`, `--default-fstype=ext4`, `--kubeconfig <csi-kubeconfig>`; env `NODE_NAME=<node>` |
| `rediacc-csi-snapshotter.service` | embedded `csi-snapshotter` (external-snapshotter **v8.6.0**) | same nodes | same lifecycle | `--csi-address <sock>`, `--node-deployment`, `--extra-create-metadata`, `--kubeconfig <csi-kubeconfig>`; env `NODE_NAME=<node>` |
| `rediacc-csi-snapshot-controller.service` | embedded `snapshot-controller` (external-snapshotter **v8.6.0**) | CP node only (one per cluster) | cluster install; moves with the CP datastore attach | `--enable-distributed-snapshotting`, `--kubeconfig <csi-kubeconfig>` |

Dropped sidecars, with reasons:

- **node-driver-registrar** — the driver implements kubelet plugin registration
  itself (§2). Fallback: v2.17.0 is the pin if the in-process implementation
  proves brittle (§14 item 1).
- **livenessprobe** — its only job is turning CSI `Probe` into an HTTP endpoint
  for a pod livenessProbe. systemd `Restart=on-failure` (+ optional
  `WatchdogSec`) is the host-side equivalent; kubelet independently notices a
  dead socket.
- **external-attacher** — `CSIDriver.attachRequired: false`; no
  ControllerPublish/VolumeAttachment machinery for node-local storage.
- **external-resizer** — expansion is out of v1 (§3 note E). It also has no
  distributed mode, so admitting it would force a central controller; deferring
  costs nothing (`allowVolumeExpansion: false`).
- **external-health-monitor** — VOLUME_CONDITION is not implemented; storage
  health is the datastore layer's job (`storage-health`, renet#76 work).

All four active processes talk to ONE unix socket served by the driver
(Identity + Controller + Node on the same listener — the csi-driver-host-path
"unified socket" shape, §15 source 6).

### Sidecars as embedded assets

The three upstream binaries are compiled from source in the renet Dockerfile
(same flow that builds CRIU/rsync from source, `private/renet/CLAUDE.md` embedded
assets section) and land as new `pkg/embed` assets
(`AssetCSIProvisioner`, `AssetCSISnapshotter`, `AssetSnapshotController`, gzip,
per-arch, extracted at unit install like `AssetZot` → `zot.ExtractBinary`,
`pkg/kube/registry/zot.go:255`). Apache-2.0; each needs a credits entry (the
embed-credits CI gate enforces the pattern, `pkg/embed/credits.go`).

Honest cost: roughly 15-25 MB gzip per binary ⇒ ~50-70 MB added to the renet
binary. Accepted [CSI-DECIDED]: the k3s asset already set this precedent, and the
alternative (download at install) reintroduces a supply-chain + air-gap surface
the `.npmrc`-hardened repo philosophy rejects. Build with `-ldflags "-s -w"`.

## 2. Sockets, registration, CSINode, topology

### Socket paths — derived from the RELOCATED kubelet root, never hardcoded

renet relocates every kubelet's root dir via `--kubelet-arg=root-dir`
(`pkg/kube/distro/k3s.go:176-183`, emitted for server AND agent;
CP value `<mount>/.rediacc/k3s/kubelet` = `KubeletRootForMount`,
`pkg/kube/distro/distro.go:186-195`). Stock k3s ≥ v0.10 defaults to
`/var/lib/kubelet` (§15 source 8), but on rediacc nodes the root is always the
relocated one, and kubelet derives its plugin directories from it:

```
<kubelet-root>/plugins_registry/                      kubelet plugin watcher dir
<kubelet-root>/plugins_registry/csi.rediacc.io-reg.sock   registration socket (driver-served)
<kubelet-root>/plugins/csi.rediacc.io/csi.sock            CSI socket (driver-served)
```

The unit render takes `--kubelet-root` from the SAME source of truth the k3s unit
used for that node (the distro comment at `distro.go:188-193` records exactly the
bug class — a path keyed off the wrong root leaves kubelet unable to find the
plugin). Implementation must verify `<kubelet-root>/plugins_registry/` exists at
unit start and fail loudly if not (§14 item 5).

### Self-registration [CSI-DECIDED]

The driver serves the kubelet **plugin registration API**
(`k8s.io/kubelet/pkg/apis/pluginregistration/v1`: `GetInfo` →
`{type: CSIPlugin, name: csi.rediacc.io, endpoint: <csi.sock>, supported_versions: [1.0]}`,
plus `NotifyRegistrationStatus`) on the `-reg.sock` itself, instead of shipping
node-driver-registrar. That sidecar's entire function is answering these two RPCs
with static data (§15 source 4); in-process it is ~60 lines against a stable v1
API, and it removes one embedded asset and one unit per node. Serving order
matters: the CSI socket must be live BEFORE the registration socket is created
(kubelet dials the CSI endpoint immediately after `GetInfo`).

After registration kubelet calls `NodeGetInfo` and (a) records the driver +
`topologyKeys` in the node's `CSINode` object, (b) **adds the topology segments
as labels on the Node object** (§15 source 5). Consequences:

- The `rediacc.io/ds-<ds>=true` labels renet stamps at attach (spec 05 §1d) and
  the labels kubelet derives from `NodeGetInfo` are the SAME key/value —
  deliberately, so static `local` PVs and CSI PVs share one topology vocabulary.
  Kubelet never REMOVES labels on re-registration, so the failover
  remove-before-add rule (spec 05 §4 step 3) remains renet's job, unchanged.
- Topology changes (datastore attach/detach) require re-registration: the attach/
  detach flows restart `rediacc-csi.service`, which re-serves `GetInfo` and
  refreshes CSINode. This is the ONLY dynamic-topology mechanism kubelet offers.

`NodeGetInfo` returns:

- `node_id` = the k8s node name (must match `NODE_NAME` given to the sidecars —
  distributed provisioning matches on it);
- `accessible_topology` = one segment carrying `rediacc.io/ds-<ds>: "true"` for
  EVERY datastore currently mounted on this node (a segment is a map; multiple
  keys are legal);
- `max_volumes_per_node` = 0 (unlimited; the practical bound is loop devices,
  which the kernel allocates dynamically).

## 3. Full gRPC surface

CSI spec: the driver pins `github.com/container-storage-interface/spec` v1.x
(≥ v1.9.0 — what external-provisioner v6.3.0 targets; §15 source 2).
`google.golang.org/grpc` is already in renet's module graph (indirect,
`go.mod:70`); it becomes a direct dependency.

### Identity service

| RPC | Disposition |
|---|---|
| `GetPluginInfo` | `name=csi.rediacc.io`, `vendor_version=<renet version>` |
| `GetPluginCapabilities` | `CONTROLLER_SERVICE` + `VOLUME_ACCESSIBILITY_CONSTRAINTS` |
| `Probe` | `ready=true` once the local datastore registry is readable and every registered-mounted datastore's mount is live; `ready=false` while converging; gRPC error only on unrecoverable misconfig |

### Controller service — capabilities: `CREATE_DELETE_VOLUME`, `CREATE_DELETE_SNAPSHOT`, `CLONE_VOLUME`, `GET_CAPACITY`

| RPC | Disposition |
|---|---|
| `CreateVolume` | implement (§4) — fresh, from-snapshot, and from-PVC (clone) via reflink |
| `DeleteVolume` | implement (§4) |
| `CreateSnapshot` / `DeleteSnapshot` | implement (§6) |
| `GetCapacity` | implement (§7) |
| `ValidateVolumeCapabilities` | implement: confirm volume exists + requested caps ⊆ {RWO, mount, ext4} |
| `ControllerGetCapabilities` | implement (the four above) |
| `ControllerPublishVolume` / `ControllerUnpublishVolume` | `Unimplemented` (attachRequired=false) |
| `ListVolumes`, `ListSnapshots`, `GetSnapshot`, `ControllerGetVolume`, `ControllerModifyVolume`, `ControllerExpandVolume` | `Unimplemented`, capabilities not declared |

Note E (expansion, [CSI-DECIDED] out of v1): the mechanical chain exists
(`truncate` → `losetup -c` → `cryptsetup resize` → `resize2fs`) but needs
`ControllerExpandVolume` + `NodeExpandVolume` + external-resizer, and resizer has
no node-deployment mode. `allowVolumeExpansion: false` on the class; restore/clone
requests larger than the source return `OUT_OF_RANGE` (§6).

### Node service — capabilities: `STAGE_UNSTAGE_VOLUME`, `GET_VOLUME_STATS`

| RPC | Disposition |
|---|---|
| `NodeStageVolume` / `NodeUnstageVolume` | implement (§5) |
| `NodePublishVolume` / `NodeUnpublishVolume` | implement (§5) |
| `NodeGetVolumeStats` | implement: statfs on the staged path — this is what closes the 05 §3 residual about kubelet volume metrics for image-backed volumes (kubelet surfaces these as the standard volume metrics) |
| `NodeGetInfo` / `NodeGetCapabilities` | implement (§2) |
| `NodeExpandVolume` | `Unimplemented` |

## 4. Volume model: IDs, layout adoption, keying, provisioning

### volume_id and volume_context [CSI-DECIDED]

- `volume_id` = the **datastore-relative image path**, exactly as spec 05 §2
  ruled: `repos/<repo>/volumes/pvc-<uid>.img` for dynamic volumes (the CSI `name`
  the provisioner sends is `pvc-<PV-uid>`; basename = `<name>.img`). Static v1
  volumes keep human `<pvc>.img` names; both coexist in one directory. Length
  check: `repos/` + ≤63 (namespace) + `/volumes/pvc-` + 36 + `.img` ≤ 122 bytes,
  inside the CSI 128-byte ID bound (§15 source 7).
- `volume_context` (persisted into the PV, echoed to every Node RPC) carries
  `{datastore: <ds>, repo: <repo>}` — **as a routing HINT only**. Every Node/
  Controller RPC resolves the volume by probing `<mount>/<volume_id>` across the
  node's currently-mounted datastores; a hint mismatch is logged, never fatal.
  This is what makes the PV objects survive CLUSTER FORK with **zero rewriting**:
  the forked datastore has a new name and mount root, but the relative
  `volume_id` still resolves on whatever datastore now carries the bytes (the
  same mount-path-stability trick as spec 05 §1d, strengthened — CSI PVs do not
  even embed the absolute mount root the `local` PVs do).

### Which repo owns a dynamic volume

The PVC's namespace IS the repo (02 §8). `--extra-create-metadata` makes the
provisioner pass `csi.storage.k8s.io/pvc/namespace` in `CreateVolume.parameters`
(§15 source 2); the driver maps namespace → repo folder
`<ds-mount>/repos/<namespace>/` and REFUSES (`INVALID_ARGUMENT`) when that folder
does not exist or the namespace lacks the `rediacc.io/repo-namespace` label —
dynamic volumes can only be born into repo folders, never loose in the datastore.
(Coordination item: the fork flow must keep namespace name == repo folder name;
§14 item 3.)

### LUKS keying — the credential seam, stated explicitly

The passphrase model is `pkg/kubevolume`'s, adopted verbatim
(`pkg/kubevolume/provisioner.go:18-21, 119-157`): per-repo keyfile at
`<ds-mount>/.credentials/volkeys/<keyID>.key` (0600, dir 0700, generated on first
use), `keyID` = the repo's grand GUID when forked (so reflinked images open with
the parent key) else the repo GUID. Properties this gives the CSI path for free:

- **The key NEVER exists in Kubernetes.** No `csi.storage.k8s.io/*-secret-name`
  StorageClass parameters, no k8s Secret, nothing in kine — so the fork secret
  scrub (spec 05 §3 F6) cannot orphan a volume, and a stolen kine DB contains no
  volume key material. The driver runs as root on the mounter node and reads the
  keyfile directly through the kubevolume code path.
- The keyfile lives OUTSIDE the repo folder, so it never rides the reflink fork
  unit; a pushed/copied repo folder is ciphertext without the datastore's
  `.credentials/` tree.

The driver needs keyID resolution FROM A PATH (it has no `RepoHandle`):
`kubevolume` grows `ResolveKeyForRepoDir(dsMount, repoDir) (passphrase, error)`
reading `{guid, grandGuid}` from the repo-scoped metadata file
`<ds-mount>/repos/<repo>/.rediacc/repo.json` (the "repo-scoped renet metadata (no
secrets)" slot spec 05 §2 reserved; GUIDs are identifiers, not secrets). The repo
create/fork flows own writing it (§14 item 3).

### CreateVolume / DeleteVolume mapped onto pkg/kubevolume

`kubevolume.Provisioner.Provision` (`provisioner.go:183-232`) currently does
create+open+format+mount in one shot. The CSI split needs finer-grained exported
primitives (refactor, not duplication — the same code paths serve both callers):

| kubevolume primitive (new/extracted) | Used by |
|---|---|
| `EnsureImage(ctx, imagePath, size, passphrase)` — create sparse LUKS2 + format ext4 iff absent; adopt-idempotent exactly like today's fresh/existing branch (`provisioner.go:207-226`) | `CreateVolume`; existing `Provision` |
| `OpenAndMount(ctx, imagePath, mountPath, passphrase)` — open mapper + mount, idempotent | `NodeStageVolume`; existing `Provision` |
| `TeardownVolume(ctx, imagePath, mountPath)` — unmount + close + loop detach, holder-reporting, no lazy umount (today's `Teardown`, `provisioner.go:238-270`) | `NodeUnstageVolume`; existing `Teardown` |
| `ResolveKeyForRepoDir(dsMount, repoDir)` | all CSI RPCs; fork flows |

**CreateVolume** (runs only on the node that mounts the target datastore — the
distributed provisioner guarantees selected-node == this node before calling):

1. Params: `datastore` (from the SC, §9), PVC namespace (extra-create-metadata).
   Verify the named datastore is mounted HERE; verify the repo folder.
2. Capacity: `capacity_range.required_bytes` → image size (Ki/Mi/Gi normalization
   exists, `provisioner.go:49-63`). Zero → 1G default (`provisioner.go:40`).
3. Content source: none → `EnsureImage`; snapshot/volume source → resolve source
   path, verify SAME datastore (cross-datastore → `INVALID_ARGUMENT` with a
   message teaching `repo push`; a reflink cannot cross BTRFS filesystems, and
   k8s allows the clone's SC to differ from the source's — §15 source 9 — so
   this check is load-bearing, not paranoia), verify requested size == source
   apparent size (larger → `OUT_OF_RANGE`, no expansion in v1; smaller →
   `INVALID_ARGUMENT`), then `cp --reflink=always` (the primitive formerly at
   `pkg/kube/pv/provisioner.go:157-168`, now re-homed in kubevolume) + fresh
   LUKS header? — **NO** [CSI-DECIDED]: the clone keeps the source's LUKS header
   and therefore the source repo's key. Same-repo clones (the only k8s-visible
   case: PVC clones are same-namespace-only, §15 source 9; snapshots restore
   into the same namespace's repo folder) share the repo key by design, exactly
   like fork volumes share the grand key.
4. Respond: `volume_id` (relative path), `capacity_bytes`, `volume_context`,
   and **`accessible_topology: [{rediacc.io/ds-<ds>: "true"}]`** — this is what
   the provisioner turns into the PV's `nodeAffinity`, making CSI PVs follow the
   datastore label across failover exactly like the static PVs.

**DeleteVolume**: resolve `volume_id` across local datastores; already-absent →
`OK` (idempotent per spec); image currently open/mounted (staged) →
`FAILED_PRECONDITION`; else `rm` the image file. Snapshots of the volume remain
valid (reflink files are independent extents-sharing copies; BTRFS keeps shared
extents alive) — deleting a volume never cascades to its snapshots.

## 5. Staging/publish split [CSI-DECIDED]

A staged CSI volume has exactly ONE device mount, and it lives at kubelet's
`staging_target_path`. The canonical path from spec 05 §2
(`<ds-mount>/mounts/volumes/<repo>/<volname>`) is a SYMLINK to the staging
mount — visibility without a mount reference. The fork-hygiene invariant holds
(no mountpoints inside `repos/<repo>/`), and the detach/failover sweeps see the
symlink tree at the same well-known place.

**Why not canonical-mount + bind-to-staging (the original ruling, REVERSED by
#98):** kubelet's `GetDeviceMountRefs` safety check refuses to issue
`NodeUnstageVolume` while the staged device is mounted anywhere besides
globalmount. With the canonical device mount alive, unstage was permanently
unreachable — kubelet retried on a 2m2s backoff forever, `DeleteVolume`
correctly kept refusing (`still staged/open`), and the orphaned dm-crypt+loop
stack held the whole datastore against detach. Observed live in suite 15
(teardown reds were a retry-lottery: `repository down`'s CT-07 sweep happened
to strip the canonical mount, and teardown went green only if a kubelet retry
landed in the ~25s window before `csi-node-down`). For k8s-owned volumes the
node's mount tree belongs to kubelet; the product keeps its addressing via the
symlink, not a second mount.

```
NodeStageVolume(volume_id, staging_target_path):
  1. resolve image; ResolveKeyForRepoDir
  2. OpenAndMount → staging_target_path DIRECTLY
     (mapper name: rediacc-vol-<repo>-<volname>, kubevolume convention)
  3. canonical <ds-mount>/mounts/volumes/<repo>/<volname> → symlink to staging
     (a stale symlink/empty dir is replaced; anything else is INTERNAL)
  idempotent: same-args re-call with the mount live → OK

NodePublishVolume(volume_id, staging_target_path, target_path):
  1. FAILED_PRECONDITION unless staged
  2. podInfoOnMount check (§9): csi.storage.k8s.io/pod.namespace must equal the
     volume's repo namespace → else PERMISSION_DENIED (defense-in-depth on the
     02 §8 filesystem-isolation row; claimRef/namespace binding already prevents
     this, the driver just refuses to be the weakest link)
  3. bind (rbind,ro if readonly) staging → target_path

NodeUnpublishVolume: umount target (idempotent, absent → OK)
NodeUnstageVolume:   TeardownVolume on the staging mount (unmount + luksClose +
                     loop detach — deepest-first, NEVER lazy, 03 §2 rules 1-2;
                     surviving holder → INTERNAL with the holder list in the
                     message, so kubelet retries instead of the datastore
                     detaching under a live mount), then remove the canonical
                     symlink
```

## 6. Snapshots and clones over reflink

### Layout [CSI-DECIDED]

```
<ds-mount>/repos/<repo>/snapshots/<snap-name>.img     snapshot_id = repos/<repo>/snapshots/<snap-name>.img
```

A sibling of `volumes/` INSIDE the repo folder — snapshots ride the repo fork
unit (a forked repo carries its snapshot history, constant-time, by
construction) and die with `repo delete`. `<snap-name>` = the CSI `name` from
CreateSnapshot (`snapshot-<VolumeSnapshotContent-uid>` from the sidecar).

### Semantics

- `CreateSnapshot`: resolve source `volume_id`; `cp --reflink=always` source →
  snapshot path; respond `ready_to_use=true` immediately (reflink is O(metadata);
  no async cutting, so the `ABORTED`-pending dance never happens),
  `size_bytes` = source image apparent size, `creation_time` = now. Idempotent:
  same name + same source → `OK` with the existing snapshot; same name +
  DIFFERENT source → `ALREADY_EXISTS`.
- **Crash-consistency, stated honestly (docs + spec):** the source may be
  mounted and in use; the reflink captures a crash-consistent instant of the
  LUKS image (journaled ext4 inside recovers on first mount), the same contract
  as every rediacc fork (02 §6 "crash-consistent CoW semantics"). No fsfreeze in
  v1: freezing would need the mapper paused under a running workload; databases
  already handle crash-consistent restore (this is the product's core thesis).
  Application-coordinated quiesce remains available at a higher layer (operator
  pre-snapshot hooks, CNPG's own backup coordination).
- `DeleteSnapshot`: rm; absent → `OK`.
- **Restore** (CreateVolume from snapshot source) and **clone** (from PVC
  source): §4 step 3. Same-datastore only; requested size must equal source size
  (no expansion in v1).
- k8s-level restrictions the docs must repeat (§15 source 9): PVC clone is
  same-namespace only, same VolumeMode; restore size ≥ snapshot size — with
  our v1 rule tightening "≥" to "==".

### The external-snapshotter contract

- **k3s ships NONE of the snapshot machinery** — no VolumeSnapshot CRDs, no
  snapshot-controller (§15 source 10; the k3s issue asking for bundling is open
  since 2021). Renet installs at CLUSTER INSTALL:
  1. the three v1 CRDs (`volumesnapshots`, `volumesnapshotclasses`,
     `volumesnapshotcontents`) — embedded YAML pinned from external-snapshotter
     v8.6.0 `client/config/crd`, applied via the existing `applyClusterScoped`
     seam;
  2. the `rediacc-csi-snapshot-controller.service` unit (CP node,
     `--enable-distributed-snapshotting` — required for the sidecar's
     node-deployment mode to be routed correctly, §15 source 3);
  3. one cluster-level `VolumeSnapshotClass`:

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: rediacc-csi
  labels: { rediacc.io/injected: "true" }
driver: csi.rediacc.io
deletionPolicy: Delete
```

One class, not per-datastore [CSI-DECIDED]: a snapshot always lands beside its
source image, so there is no datastore parameter to vary.

- Dynamic path (the normal one): user creates `VolumeSnapshot` → controller
  creates `VolumeSnapshotContent` → node-local csi-snapshotter instance (owner
  by NODE_NAME) calls `CreateSnapshot`. Pre-provisioned path (admin-created
  `VolumeSnapshotContent` with `snapshotHandle` = our relative path) is
  supported for free — it is how a fork COULD re-expose parent-era snapshots if
  we ever want that (v1: not done, §10).

## 7. Topology, WFFC, capacity

- StorageClass `rediacc-csi-<ds>` is **WaitForFirstConsumer** (§9). With WFFC +
  distributed provisioning: scheduler picks a node first; the provisioner
  instance on that node sees the `selected-node` annotation and provisions
  locally (§15 source 2). Immediate binding on user-created classes for this
  driver is NOT supported in v1 (`--node-deployment-immediate-binding` unset;
  the race mechanism works but adds no product value over WFFC).
- **`CSIDriver.storageCapacity: true` is load-bearing, not cosmetic**: without
  `CSIStorageCapacity` objects the scheduler has no idea which node can satisfy
  `rediacc-csi-<ds>` and will happily select a node that does not mount `<ds>`,
  wedging the PVC in provision-retry limbo. With it, each provisioner instance
  publishes per-(SC, local-topology-segment) capacity from `GetCapacity` and the
  scheduler filters nodes accordingly (§15 sources 1, 2).
- `GetCapacity`: statfs available bytes on `<ds-mount>` for the requested
  `datastore` parameter/topology (answers only for locally mounted datastores —
  in distributed mode nobody else asks). **Thin-provisioning honesty**: images
  are sparse; reported capacity is the pool's free bytes, not a reservation.
  Overcommit is possible and is the datastore layer's existing story
  (storage-health + F10 allocation churn); the driver reports truth and does not
  pretend to enforce reservations it does not have.
- `--capacity-ownerref-level=-1` [CSI-DECIDED]: the upstream ownerref levels
  assume pod/DaemonSet owners for GC; host processes have none. Consequence
  renet must own: **stale CSIStorageCapacity cleanup** on datastore detach /
  node removal / cluster fork (`kubectl delete csistoragecapacities -n
  rediacc-system -l csi.storage.k8s.io/drivername=csi.rediacc.io` filtered to
  the departing topology) — wired into the detach flow next to label removal
  (verify exact label at build; §14 item 2).

## 8. Idempotency, error codes, concurrency

Per-`volume_id`/`snapshot_id` in-process mutex; a second in-flight operation on
the same ID returns `ABORTED` (the CO retries). All RPCs below are idempotent as
the spec requires (§15 source 7).

| RPC | Condition | Code |
|---|---|---|
| CreateVolume | name exists, compatible size/caps/source | `OK` (return existing) |
| | name exists, incompatible (size/source differ) | `ALREADY_EXISTS` |
| | unsupported capacity (source-size mismatch, absurd range) | `OUT_OF_RANGE` |
| | source snapshot/volume missing | `NOT_FOUND` |
| | datastore full (image create fails ENOSPC) | `RESOURCE_EXHAUSTED` |
| | bad params: unknown datastore/not mounted here/non-repo namespace/cross-ds clone/non-RWO/block mode | `INVALID_ARGUMENT` |
| DeleteVolume | volume absent | `OK` |
| | volume staged/open | `FAILED_PRECONDITION` |
| CreateSnapshot | name exists, same source | `OK` |
| | name exists, different source | `ALREADY_EXISTS` |
| | source volume missing | `NOT_FOUND` |
| | pool full | `RESOURCE_EXHAUSTED` |
| DeleteSnapshot | absent | `OK` |
| NodeStageVolume | image missing | `NOT_FOUND` |
| | staged incompatibly (different mount flags) | `ALREADY_EXISTS` |
| | staged compatibly | `OK` |
| | LUKS open fails (bad key = corrupted keyfile) | `INTERNAL` (with remediation text) |
| NodePublishVolume | not staged | `FAILED_PRECONDITION` |
| | image missing | `NOT_FOUND` |
| | pod namespace ≠ repo namespace | `PERMISSION_DENIED` |
| NodeUnstage/Unpublish | already clean | `OK` |
| | surviving holder after teardown attempt | `INTERNAL` (holder list in message) |
| ValidateVolumeCapabilities | volume missing | `NOT_FOUND` |
| GetCapacity | unknown/unmounted datastore param | zero capacity, `OK` |

## 9. Kubernetes objects and credentials

### CSIDriver object (cluster install, `applyClusterScoped`)

```yaml
apiVersion: storage.k8s.io/v1
kind: CSIDriver
metadata:
  name: csi.rediacc.io
  labels: { rediacc.io/injected: "true" }
spec:
  attachRequired: false          # immutable; no attacher, no VolumeAttachment
  podInfoOnMount: true           # enables the §5 namespace assert (adds
                                 #   csi.storage.k8s.io/pod.* to volume_context)
  storageCapacity: true          # §7 — WFFC scheduling needs it
  fsGroupPolicy: ReadWriteOnceWithFSType   # default; ext4+RWO ⇒ kubelet applies
                                 #   fsGroup, which PSA-restricted non-root
                                 #   charts require; pods can soften recursive
                                 #   chown cost via fsGroupChangePolicy
  volumeLifecycleModes: [Persistent]       # immutable; no inline ephemeral
  seLinuxMount: false
```

(Field semantics + mutability verified against the current API reference, §15
source 11. `attachRequired` and `volumeLifecycleModes` are immutable — getting
them right the first time matters.)

### Per-datastore CSI StorageClass (applied at datastore attach, next to the static class)

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: rediacc-csi-<ds>
  labels:
    rediacc.io/injected: "true"
    rediacc.io/datastore: <ds>
provisioner: csi.rediacc.io
parameters:
  datastore: <ds>
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete            # dynamic volumes die with their PVC (image
                                 #   inside the repo folder; repo delete also
                                 #   reclaims strays)
allowVolumeExpansion: false
```

Applied by the same attach flow that applies `rediacc-ds-<ds>`
(`pkg/reporuntime/kube_templates.go:230-243` render pattern; the `repo up`
storageClassName rejection rule from spec 05 §1c widens to accept EITHER of the
repo's two datastore classes).

### RBAC + sidecar credentials [CSI-DECIDED]: CSR-minted client certs, no SA tokens

Host-side sidecars need API access from nodes that do not hold the admin
kubeconfig (any agent node mounting a datastore). Mechanism:

1. Cluster install applies a `ClusterRole rediacc-csi` (the pinned union of
   external-provisioner v6.3.0 + csi-snapshotter/snapshot-controller v8.6.0
   upstream RBAC files, embedded; includes CSIStorageCapacity write, PV/PVC/SC
   read-write, VolumeSnapshot* read-write, events, leases) bound to **group**
   `rediacc:csi`.
2. At datastore attach (and cluster install for the CP), renet mints a client
   certificate for CN `rediacc-csi:<node>` / O `rediacc:csi` via the Kubernetes
   CSR API (`kubernetes.io/kube-apiserver-client` signer, approved by renet's
   admin kubeconfig on the CP), writes the kubeconfig to
   `/etc/rediacc/csi/<cluster>/kubeconfig` (0600, node-local disk, NOT in any
   datastore), and points the sidecar units at it.
3. Rotation = re-mint at every attach; certs get a bounded TTL (90d default,
   re-minted long before by the reconcile timer).

Why not ServiceAccount tokens: legacy SA-token Secrets are exactly what the fork
scrub sweeps (spec 05 §3 F6 step 3 deletes ALL
`kubernetes.io/service-account-token` Secrets cluster-wide) — CSI creds stored
that way would silently die on every fork; and bound tokens require a running
pod. Client certs interact CORRECTLY with fork instead: the fork PKI re-mint
(F1-F4) invalidates every parent-issued cert, which is the isolation contract
working — and the fork's own attach step re-mints fresh certs against the new CA
(§10). No credential ever rides kine or a datastore.

## 10. Fork / failover / migrate interactions

### Datastore detach & failover (spec 05 §4 sequence — CSI additions in place)

- Step 0/2 (drain / Node delete) already causes kubelet to NodeUnpublish +
  NodeUnstage every CSI volume → the staging mounts clear through
  `TeardownVolume` and the canonical symlinks under
  `<ds-mount>/mounts/volumes/` are removed (§5, #98). The existing
  detach sweep remains the backstop for leaks; a LIVE holder still refuses
  detach (03 hygiene) — CSI changes nothing about that contract.
- Step 4/5 additions: stop (last-ds) or restart (remaining-ds) the three CSI
  units on the OLD node; on the NEW node the attach flow installs/starts them,
  re-registers (fresh topology), re-applies `rediacc-csi-<ds>`, re-mints the
  sidecar cert if absent, and deletes stale CSIStorageCapacity for the departed
  topology (§7).
- CSI PVs need ZERO rewriting on failover: their `nodeAffinity` is the
  label-based topology from `accessible_topology` (§4), and the label moves with
  the datastore exactly as for static PVs.

### Repo fork (namespace-level, same cluster)

The reflink of `repos/<repo>/` carries `volumes/*.img` AND `snapshots/*` at
constant time. The fork flow (extends `KubeRuntime.Fork`,
`pkg/reporuntime/kube.go:295-331`, and the CLI-side `registerFork`) additionally:

1. Enumerates the parent namespace's Bound CSI PVs (driver `csi.rediacc.io`).
2. For each, creates a **pre-provisioned CSI PV** in the fork's world: new PV
   name `rediacc-<fork-ns>-<basename>`, `spec.csi.driver: csi.rediacc.io`,
   `volumeHandle: repos/<fork-folder>/volumes/<same-basename>.img`,
   `volumeAttributes: {datastore, repo: <fork-ns>}`, same capacity/SC,
   `claimRef` to the fork-namespace PVC name,
   `persistentVolumeReclaimPolicy: Retain` [CSI-DECIDED — the image belongs to
   the fork's repo folder; `repo delete` reclaims it; a Delete policy would let
   a PVC deletion inside the fork rip data the folder-level lifecycle owns].
3. Applies the fork's PVCs (from the replayed manifests) — they bind to the
   pre-created PVs by claimRef instead of triggering fresh dynamic provisioning
   (which would silently produce EMPTY volumes: the failure mode this step
   exists to prevent).
4. The fork's LUKS opens work because keyID resolves to the grand GUID
   (`provisioner.go:119-124`) — same key, reflinked images, by design.
5. Parent-era VolumeSnapshot/Content objects are NOT re-exposed in the fork
   namespace in v1 (the .img files are there; pre-provisioned
   VolumeSnapshotContent is the documented escape hatch, §6).

### Cluster fork (group snap + PKI re-mint, spec 05 §3)

- kine rides the snapshot: PVs, PVCs, VolumeSnapshotContents, the CSIDriver
  object, classes — all intact. Relative `volume_id`/`snapshotHandle` resolve on
  the forked datastore via path lookup (§4); no object rewriting. This is the
  strongest single argument for the relative-ID rule.
- The PKI re-mint (F1-F4) kills the parent-issued sidecar certs on the fork —
  REQUIRED behavior (a fork must not hold parent API creds). The fork's attach/
  install flow re-mints certs against the new CA before the units start. Contract
  test: parent sidecar cert is REJECTED by the fork apiserver (same proof style
  as spike d §4-5).
- The F6 secret scrub deletes nothing CSI-related (no CSI Secrets exist — §4
  keying). The F8 stale-Node cleanup also drops stale CSINode objects (owned by
  Node lifecycle); rejoining nodes re-register.
- Stale CSIStorageCapacity objects ride kine into the fork; the attach-time
  sweep (§7) plus the provisioner's own reconcile refresh them (§14 item 2).

### Migrate

Same principal: certs/kubeconfigs are re-minted only because the attach flow
always does; secrets and snapshots persist; `REDIACC_ROLE` stays `primary`.
Nothing CSI-specific beyond failover mechanics.

## 11. Delete-ledger guard (nothing ceph-csi returns)

Explicitly asserted against 02 §6: this driver introduces **no** per-namespace
StorageClasses or snapshot classes (ours are per-datastore + one cluster-level
VSClass), no synthetic clusterIDs, no RADOS/namespace machinery, no
`.rbd-backend.json`, no dual PV backend or `resolvePVBackend`, no per-PVC images
outside repo folders, no `pv/`/`pv-mounts/` trees. The only Ceph the CSI path
ever touches is transitively: the datastore's RBD image, which the datastore
layer mounts BELOW the driver. Grep-gate for the implementation PR: no import of
anything under the deleted ceph-csi paths; `pkg/kube/distro/distro.go:182-189`'s
stale "ceph-csi node-plugin" comment gets rewritten to reference this driver.

## 12. Testing

### csi-sanity [CSI-DECIDED: prescribed, as a root-tagged Go test]

`github.com/kubernetes-csi/csi-test/v5` (v5.5.0+, pin latest v5 at build)
`pkg/sanity` embedded as a Go test in `pkg/kubecsi` behind the existing
root-tag pattern (the repo already runs `go vet -tags "root ebpf_e2e"` for
root-gated files — CLAUDE.md check:ci-renet note): node RPCs do real
cryptsetup/losetup/mount and need root + a scratch BTRFS datastore (loop-backed,
created by the test). Config: `TestVolumeParameters` = `{datastore: <scratch>}`,
staging/target dirs under the scratch tree, snapshot tests enabled (capabilities
declare them). Idempotency + error-code conformance (§8) comes free from the
suite — that is the point of prescribing it rather than hand-written table tests.

### Unit level

- Golden tests for every rendered object + systemd unit (the zot golden-test
  pattern, byte-for-byte).
- The kubevolume refactor keeps the existing recording-fake seam
  (`provisioner.go:69-88`) so the split primitives stay unit-testable without
  root.
- Registration handshake: fake plugin-watcher client against the reg socket.

### E2E (live KVM cluster, bridge-tests loop)

1. **Dynamic PVC via a stock chart**: `groundhog2k/postgres` Helm chart (small,
   dependency-free — deliberately NOT a Bitnami chart post-catalog-gutting) with
   `storageClass: rediacc-csi-<ds>`; write rows; pod lands on the datastore
   node (WFFC+capacity proof).
2. **VolumeSnapshot backup/restore**: snapshot the PVC (class `rediacc-csi`),
   write more rows, restore into a new PVC via `dataSource`, boot a second
   postgres on it, assert point-in-time content.
3. **Clone**: `dataSourceRef` PVC→PVC, assert content + independence.
4. **Failover**: move the datastore per spec 05 §4; pod reschedules to the new
   node; data intact; CSIStorageCapacity refreshed.
5. **Repo fork**: fork a repo with a bound dynamic PVC; assert the fork's PVC
   binds to the pre-provisioned PV (NOT a fresh empty volume), data present,
   ROLE=fork, zero injected secrets.
6. **Cluster fork**: forked cluster serves the same PVCs with zero PV rewrites;
   parent sidecar cert rejected by the fork apiserver.
7. **Negative battery**: oversize PVC (Pending + event), cross-datastore clone
   (event carries the `repo push` teaching error), PVC in a non-repo namespace
   refused, restore-larger refused.
8. Stretch (operator proof, the F6 motivation): CloudNativePG cluster with
   volumeSnapshot backup — documented as the compatibility-matrix headline once
   green.

## 13. Bridge-function / CLI touchpoints

[CSI-DECIDED] **No new user-facing verbs.** Enablement is automatic: cluster
install applies CRDs + CSIDriver + RBAC + VSClass + snapshot-controller unit;
datastore attach installs/starts the per-node units and the per-datastore CSI
class; detach reverses. `renet kube csi-serve` is an internal subcommand (the
systemd ExecStart), NOT a generated bridge function — so the
`check:ci-e2e-coverage` gate (which greps e2e-tests for generated function
names) is untouched. Surfacing: `renet list all --json` and `rdc cluster status`
gain a `csi` health block (driver socket present, units active, CSINode
registered) — read-only additions; exact CLI shape belongs to the P4 reshape
(spec 03 owner).

## 14. OPEN items (could not be fully settled from official docs)

1. **Self-registration vs node-driver-registrar** — the plugin-registration v1
   API is public and stable and the in-process implementation is small, but no
   official doc BLESSES skipping the registrar (it documents the sidecar only).
   Recommendation stands (self-register); fallback pin: registrar v2.17.0 as a
   fourth embedded asset behind the same unit pattern. Decide by the first
   registration e2e.
2. **CSIStorageCapacity in non-pod distributed mode** — `--enable-capacity` with
   `--node-deployment` is documented for DaemonSet owners
   (`--capacity-ownerref-level=1`); `-1` (no owner) is valid but leaves GC to
   us. Verify at build: exact object labels for the detach sweep, and that the
   provisioner reconciles stale objects after cluster fork. Fallback if capacity
   proves unreliable out-of-pod: keep `storageCapacity: true` but have renet
   itself write the CSIStorageCapacity objects (they are plain API objects).
3. **`.rediacc/repo.json` metadata file** (`{guid, grandGuid, name}`) — this
   spec needs it for path-based key resolution (§4); the repo create/fork/push
   flows must write and rewrite it. Coordination with spec 01/02 owners; fork
   identity rewrite must update `guid` while PRESERVING `grandGuid`.
4. **Fork PV pre-provisioning enumeration** — §10 step 1 needs "all Bound CSI
   PVs claimed by namespace X" from the parent cluster at fork time; mechanics
   (kubectl field-selectors vs walking PVCs) settle in implementation.
5. **Plugin watcher under the relocated kubelet root** — kubelet derives
   `plugins_registry`/`plugins` from `--root-dir` (kubelet source; Longhorn's
   k3s guidance corroborates the "drivers must follow the real kubelet dir"
   rule, §15 source 8), but no doc states it for k3s 1.36 verbatim. First
   implementation step: `ls <kubelet-root>/plugins_registry/` on a live node.
6. **csi-test pin** — v5.5.0 (2024) is the newest confirmed release (§15 source
   12); check for a newer v5.x when vendoring.
7. **Sidecar version currency** — external-provisioner v6.3.0 (2026-06-04) and
   external-snapshotter v8.6.0 (2026-05-28) verified current at research time;
   re-check the release pages at build and bump the pins + credits in lockstep.
8. **VolumeGroupSnapshot** (v1beta2 in external-snapshotter v8.6.0) — the
   natural k8s face of the DATASTORE group snap (03). Out of v1; noted so the
   snapshot layout (§6) does not foreclose it (it does not: group snapshots
   would land as N reflinks + one VolumeGroupSnapshotContent).
9. **fsGroup recursive-chown cost on large volumes** — mitigation is the
   pod-level `fsGroupChangePolicy: OnRootMismatch`; document in the chart
   guidance rather than forcing `fsGroupPolicy: None` (which would break
   non-root charts under PSA restricted).

### As-built deviations and residuals (live-validation window, 2026-07-11)

These three items are settled AS-BUILT: surfaced by the prescribed csi-sanity suite
(§12) on a live KVM cluster and ruled by the lead. csi-sanity result at close:
**48/50 specs** (the 2 non-passes are exactly the two documented deviations below;
the 1 Pending is `ListVolumes`, out of v1 by design).

10-11. **CSI-DEVIATION-1 and CSI-DEVIATION-2 are RULED, not open.** Both were
    settled at the P3 live gate and are documented once, in **§16 (As-built
    deviations)**. They are listed here only to keep this section's numbering
    stable; a ruled deviation is by definition no longer an OPEN item. Do not
    re-document them here.

12. **Automatic CSI enablement — agent-node datastore-attach is a deferred residual.**
    Enablement is folded in two halves (§9/§13): cluster install
    (`runKubeInstall` → `deployCSIControlPlane`: CRDs + CSIDriver + RBAC + VSClass +
    snapshot-controller + CP node units) and datastore attach
    (`datastore attach` → `deployCSIForAttachedDatastore`: per-ds StorageClass +
    node units + sidecar-kubeconfig rotation). The attach half derives everything
    from the node's LOCAL k3s admin kubeconfig, so it covers hyperconverged /
    server nodes and cleanly no-ops elsewhere. A **pure agent / data-only node** has
    no local admin kubeconfig, so its attach-time CSI wiring needs cluster-connection
    context that is not mount-derivable — DEFERRED (no CLI touch, no fabricated
    node→CP channel). It rides the multi-node worker-attach design item (P4-or-later).
    Live proof of the covered halves is carried by the next fresh cluster create.

## 15. Sources (research pass dated 2026-07-11)

1. kubernetes-csi.github.io — external-provisioner page
   (https://kubernetes-csi.github.io/docs/external-provisioner.html): settled
   `--extra-create-metadata` semantics (PVC name/namespace/PV name into
   CreateVolume parameters).
2. github.com/kubernetes-csi/external-provisioner README: settled distributed
   provisioning (`--node-deployment` ownership via selected-node annotation,
   WFFC vs immediate-binding race + backoff flags), capacity in node-deployment
   (`--capacity-ownerref-level`), out-of-cluster `--kubeconfig` support
   ("useful only when… not run as a Kubernetes pod"), `--csi-address`, current
   release **v6.3.0 (2026-06-04)**, min k8s 1.20 / CSI spec v1.9.0 target.
3. github.com/kubernetes-csi/external-snapshotter README: settled current
   release **v8.6.0 (2026-05-28)**, CRDs installed once by the cluster admin
   (`client/config/crd`), snapshot-controller separate from the csi-snapshotter
   sidecar, distributed snapshotting (`csi-snapshotter --node-deployment` +
   `snapshot-controller --enable-distributed-snapshotting` + `NODE_NAME`),
   out-of-cluster `--kubeconfig` on both, VolumeSnapshotClass fields.
4. github.com/kubernetes-csi/node-driver-registrar README: settled the two
   socket paths (`plugins_registry/<driver>-reg.sock`,
   `plugins/<driver>/csi.sock`), that the registrar's whole role is the kubelet
   plugin-registration handshake for the driver socket, current release
   **v2.17.0 (2026-05-25)**, non-default kubelet root-dirs require adjusted
   paths.
5. kubernetes-csi.github.io/docs/topology.html: settled that NodeGetInfo
   topology populates CSINode AND adds Node labels automatically, and how the
   provisioner builds `accessibility_requirements` (WFFC: selected node's
   topology first-preferred).
6. csi-driver-host-path deploy docs
   (github.com/kubernetes-csi/csi-driver-host-path): precedent for the unified
   single-socket plugin serving Identity+Controller+Node, and the
   sidecar-per-function catalog a node-local driver ships.
7. container-storage-interface/spec spec.md (raw, master): settled idempotency
   contracts (CreateVolume/DeleteVolume/CreateSnapshot/NodeStage re-call
   semantics), per-RPC error codes (§8 table), capability enums, the 128-byte
   ID bound, Probe `ready` semantics.
8. longhorn.io docs "CSI on K3s" + k3s docs: settled modern k3s kubelet root =
   `/var/lib/kubelet` by default (v0.10+), and that CSI drivers must follow the
   ACTUAL kubelet dir when it is non-default (which on rediacc nodes it always
   is, via `--kubelet-arg=root-dir`).
9. kubernetes.io/docs/concepts/storage/volume-pvc-datasource: settled PVC-clone
   restrictions — same namespace, same VolumeMode, size ≥ source, and **cloning
   MAY target a different StorageClass** (why the cross-datastore rejection in
   §4 is load-bearing).
10. k3s-io/k3s issue #2865 + kubernetes-csi snapshot-controller docs: settled
    that k3s does NOT bundle snapshot CRDs or snapshot-controller; distros/
    admins install them.
11. kubernetes.io API reference, CSIDriver v1: settled every §9 field's
    semantics, defaults, and mutability (attachRequired + volumeLifecycleModes
    immutable; podInfoOnMount volume_context keys; storageCapacity scheduler
    behavior; fsGroupPolicy value semantics).
12. github.com/kubernetes-csi/csi-test releases: csi-sanity ships in csi-test
    **v5.5.0 (2024-07-06)**, usable as a Go library (`pkg/sanity`) or CLI.

## 16. As-built deviations (from live validation, csi-sanity)

**This section is the single home for the two ruled CSI deviations.** (§14 items
10-11 formerly restated them; that duplication was merged here at the P3 gate.
See `spec/10-p3-gate-review.md`.)

Two csi-sanity conformance cases are documented deviations, ruled acceptable at the
P3 live gate rather than reshaping load-bearing design choices. csi-sanity result:
**48/50** — the 2 non-passes are exactly the two deviations below; the 1 Pending is
`ListVolumes`, out of v1 by design.

- **CSI-DEVIATION-1 — maximum-length volume names.** A CSI `name` at the 128-byte
  max makes the path-derived `volume_id` (`repos/<ns>/volumes/<name>.img`) and the
  `rediacc-vol-<repo>-<vol>` dm-mapper name exceed the 128-byte CSI id bound /
  kernel `DM_NAME_LEN`. `CreateVolume` refuses such a name up front with a clean
  `INVALID_ARGUMENT` naming the limit and the wrapper overhead (not a deep
  cryptsetup "Name too long").
  The path-derived `volume_id` is **[CSI-DECIDED]** (§4) precisely because it buys
  zero-PV-rewrite cluster forks; the length ceiling is the price of that choice.
  The alternative, hashed volume ids, was **rejected**: it would break the
  path-probe fork resolution that the whole fork story rests on.
  Real dynamic PVCs use a 40-char `pvc-<uuid>` name and never approach the limit.
  csi-sanity's "create with maximum-length name" spec expects success, so it
  **stays red by design** — the documented price, not a bug.
  Enforced by `TestCreateVolumeRejectsOverlongName`.
- **CSI-DEVIATION-2 — snapshot same-name/different-source idempotency.**
  `CreateSnapshot` distinguishes an existing snapshot's source by IMAGE SIZE, so
  two DIFFERENT sources of the SAME size + SAME snapshot name return `OK` (reusing
  the existing snapshot) instead of `ALREADY_EXISTS`. Accepted: a real provenance
  sidecar beside the snapshot image would have to ride the reflink repo fork and
  carry its own delete-ledger cleanup, which is worse for fork hygiene (§6) than
  the deviation itself.
  Mitigation in practice: external-snapshotter mints unique `snapshot-<uuid>`
  content names in the dynamic flow, so two distinct VolumeSnapshots never collide
  on a name; the collision only arises under a hand-crafted duplicate name, as in
  the sanity suite.

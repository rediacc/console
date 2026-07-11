# P0 Spec 01 — Renet Package Design, Delete Ledger, Multi-Datastore, Bridge Contract

Status: P0 implementation spec (2026-07-10). Expands 02 §6/§7/§9, 03 §2/§2b, 04, 09 §P1/P2
into per-file instructions. Every identifier below was verified against renet `2b13e9d`
(console `0707-1`, HEAD `973763d30`) by grep/read; line numbers are advisory, symbol names
are the contract. Decisions the suite left thin are marked **[P0-DECIDED]**. Claims in the
suite that do not match the tree are collected in §5 (reality deltas).

Gate status: **APPROVED** (`00-gate-review.md` §4b re-review addendum). Rulings applied —
C1 (volume layout: spec 05 wins), C2 (§4 reworked to unified runtime-generic dispatch;
re-review CLEARED), C3 (per-repo zot units), C6 (descriptor path), C7 (`--cluster`
backref at create), C10 (`pkg/reporuntime`), C13 (identity-rewrite fork-arm role/writes),
G2 (health/logs/exec bridge surface), G5 (fork record key + `autoAttach`). R1 (mount
path) APPROVED.

Reading order for an implementer: §3 (the datastore model — everything else hangs off it),
§1 (per-package changes), §2 (delete ledger), §4 (bridge contract diff).

---

## 1. Package-level design

### 1.1 `pkg/datastore` — from "one path, two backends" to a named registry

**Today** (verified): `DatastoreConfig{BasePath, Size, PoolPath, Backend, Ceph}` at
`pkg/datastore/types.go:4` — path-addressed, no names, no state. `DatastoreBackend`
interface at `pkg/datastore/backend.go:109` (Initialize/Mount/Unmount/Expand/Resize/
Cleanup/IsInitialized/GetInfo/Validate/Type) with `LocalBackend`
(`backend_local.go:37`, loop+BTRFS, pool file `<BasePath>.pool`) and `CephBackend`
(`backend_ceph.go`, RBD+BTRFS). `DetectBackend` (`backend.go:30`) infers backend from
/proc/mounts + sysfs. Fork lives in `backend_ceph_fork.go` (`Fork`/`Unfork`, snap →
protect → clone → dm-COW mount via `pkg/rbd.COWClone`; COW backing defaults to
`/tmp/cowdata`, `pkg/rbd/cowclone.go:22`). Loop hygiene: `LoopManager` in `loop.go` with
`FindLoopDevicesFor` (`loop.go:266`, parses `losetup -a` incl. the `" (deleted)"` suffix)
and the `loopController` seam (`backend_local.go:29`) that `sweepStaleLoops`
(`backend_local.go:362`) and the mutation-checked cleanup tests exercise.

**New files**:

| File | Contents |
|---|---|
| `pkg/datastore/registry.go` | The on-machine registry (§3.1): `Registry` type, `Record`, `Load/Save` (flock + atomic temp+rename, mirroring `pkg/repository/state.go` patterns), `Resolve(name) (Record, error)` with the implicit-`default` arm, name/mount-path collision refusal |
| `pkg/datastore/registry_test.go` | Round-trip, collision, implicit-default resolution, corrupt-file recovery |
| `pkg/datastore/attach.go` | `Attach(ctx, name, AttachOpts{Writes, Fence})` / `Detach(ctx, name, DetachOpts{Discard})` state machine (§3.3) over the existing backends; fork-attach `--writes` refusal; fencing steps (§3.4) |
| `pkg/datastore/attach_test.go` | State-machine transitions under MockExecutor + mock loopController; the "fork attach without writes fails with the teaching error" contract test |
| `pkg/datastore/fork.go` | Backend-neutral `Fork(ctx, parent, tag, opts{Snapshot})` — registry bookkeeping + dispatch: ceph = snap+clone (reusing the `backend_ceph_fork.go` rbd sequence, minus its auto-mount; with `opts.Snapshot` set it clones from that EXISTING group-owned snap via the §3.6 snap-id discovery instead of taking a fresh one — the cluster-fork path); local = refused in v1 (a local datastore has no block-level clone primitive; repos inside it fork by reflink instead) **[P0-DECIDED]** |
| `pkg/datastore/snapshot.go` | `SnapshotCreate/List/Delete`: local backend = BTRFS snapshot (reuse `pkg/snapshot`); ceph = `rbd snap`; `--group <cluster>` = `rbd group snap create` across every ceph-backed record labelled with that cluster. Spike (a) PASSED on the live fleet — §3.6 is the verified invocation contract and is HARD (Squid ships no `rbd group info`/`rbd group snap info`; clone format v2 mandatory) |
| `pkg/datastore/inventory.go` | Expected-holders inventory (§3.5): diff registry-declared holders vs `losetup -a` (via `FindLoopDevicesFor`) PLUS `dmsetup ls` (dm devices escape the losetup trick — 03 §2b rule 3); returns leaks; auto-sweeps only provably-stale entries |

**Modified files**:

- `pkg/datastore/types.go`: `DatastoreConfig` gains `Name string` (empty = implicit
  default). `DatastoreInfo` gains `Name`, `Writes` (`""|"local"|"ceph"`), `Fork bool`,
  `K3sVersion string` (attach preflight metadata, 02 §10 F14). `CephDatastoreConfig`
  unchanged.
- `pkg/datastore/backend.go`: interface unchanged in v1 EXCEPT `Mount` grows
  `MountOpts{ExclusiveLock bool}` — plain ceph attach maps with `exclusive-lock`
  (03 §2 hardening; today's images are layering-only). `DetectBackend` stays (attach
  verification + `config reconcile` truth source).
- `pkg/datastore/backend_ceph.go`: enable `--image-feature exclusive-lock,layering` at
  image create; add `FenceHolder(ctx)` (lock break + osd blocklist, §3.4).
- `pkg/infra/ceph/provisioner.go` (spike A hard requirement): the cephadm bootstrap
  (verified: NO `--image` pin at `provisioner.go:201,276` — the release rides the host
  distro's default, Squid 19.2.4 on Ubuntu 24.04) MUST run
  `ceph config set global rbd_default_clone_format 2` as a provisioning step. With
  `require-min-compat-client=luminous`, clone-format `auto` resolves to v1, and a bare
  `rbd clone --snap-id` against a group-owned snapshot fails with "parent snapshot must
  be protected" (group snaps cannot be protected). Every clone call ALSO passes
  `--rbd-default-clone-format 2` explicitly (belt-and-braces; the csi
  `NamespaceManager.cloneArgs` precedent).
- `pkg/datastore/backend_ceph_fork.go`: `Fork` loses its mount step (attach is a separate
  verb now); `Unfork` is DELETED (§2 ledger) — its teardown ordering moves into
  `Detach(--discard)`. `ForkOptions.COWDir` default moves off `/tmp/cowdata` (see
  `pkg/rbd` below).
- `pkg/datastore/backend_local.go`: `sweepStaleLoops` generalizes: it currently sweeps
  only `b.config.PoolPath`; the inventory sweep (new `inventory.go`) covers all registered
  pool files + volume images. The `loopController` seam and `FindLoopDevicesFor` are
  REUSED, not reimplemented (03 §2b rule 1).
- `pkg/datastore/fstab.go`: named datastores get fstab entries exactly like the default
  (`FixFstabEntry` precedent) keyed on the per-name pool path; ceph-backed records get
  NO fstab entry (attach is explicit/fenced, never boot-automatic; boot re-attach is the
  P2 node-lifecycle unit's job driven by the registry).

### 1.2 `pkg/kube` — repo-as-folder, local PVs, isolation; the Ceph half deleted

**Today** (verified): `Wrapper` (`wrapper.go:28`) carries `CephPool/CephCluster/
KubeletDir/cephExec` — the dual-backend seam. Deploy path `Apply`/`Deploy`
(`deploy.go:100/137`) call `EnsureCephBackend` when `CephPool != ""` and
`materializeAndBindPVs` (`deploy.go:58`) for `rediacc-datastore` PVCs —
hostPath PVs pre-bound via claimRef, **no nodeAffinity** (`GenerateLocalPVManifest`,
`deploy.go:33`). Namespace fork dispatches through `resolvePVBackend`
(`namespace.go:157`; the suite cites :154 — see §5) to either `forkNamespaceRBD`
(`ceph_backend.go:482`) or the datastore reflink path (`ForkNamespacePrepare`,
`namespace.go:100`). Teardown: `NamespaceDelete` → `removeCephBackend` →
`drainRadosNamespace` (`ceph_backend.go:268`) with `NamespaceTeardownLeak`
(`ceph_backend.go:46`) — note the leak type ALSO reports local PV-image-dir leaks
(`namespace.go:72`), not only Ceph state.

**The new k8s repo layout** (gate ruling C1 — spec 05 §2's layout is authoritative;
CSI-adoptable per F6; one reflink unit):

```
<ds-mount>/repos/<repo>/
  volumes/<pvc>.img         # per-volume fixed-size LUKS image (F8); passphrase = per-repo credential
  manifests/*.yaml          # rendered-manifest persistence RELOCATED here (was {datastore}/manifests/<cluster>/<ns>/)
  registry/                 # per-repo zot blob store for locally built images (F4, 04 §7b; spec 05 §5)

<ds-mount>/mounts/volumes/<repo>/<pvc>/   # loop+LUKS mounts — the paths PV objects reference
<ds-mount>/.rediacc/datastore.json        # on-datastore descriptor (gate C6; spec 05 §7): name,
                                          # backend, cluster?, writes?, k3sVersion — travels with the datastore
```

**Invariant (load-bearing): no mountpoints inside `repos/<repo>/`.** The fork unit is ONE
reflink of `repos/<repo>`; a live ext4 mountpoint inside that tree would make
`cp --archive --reflink=always` fail (reflink cannot cross filesystems) or, under any
fallback, byte-copy decrypted plaintext into the fork. Mounts live in the `mounts/` tree
OUTSIDE the snapshotted unit — the docker world's exact shape (image files in the pool,
`{datastore}/mounts/<guid>` outside them). The fork procedure this makes executable:
`syncfs` each mounted volume (inner-fs-first, the #440 lesson), then reflink the folder —
no unmount step, the parent keeps serving. PV objects reference
`<ds-mount>/mounts/volumes/<repo>/<pvc>` — deterministic and identical across machines,
so kine-carried PV specs never rewrite on fork/migrate (mount-path stability, 04 §6).

Rationale for relocating manifests INTO the repo folder: 04 §2.8 makes "everything rides
the datastore" true by construction only if ONE folder clone carries volumes + manifests +
built images. The manifests LAYER (persist at deploy, replay on redeploy/fork) is kept
exactly as-is; only `ManifestsDir` changes shape.

**New files**:

| File | Contents |
|---|---|
| `pkg/kube/storageclass.go` | Render the per-datastore `no-provisioner` StorageClass `rediacc-ds-<name>` (`volumeBindingMode: WaitForFirstConsumer`) + the `local`-type PV with `nodeAffinity` on label `rediacc.io/ds-<name>` (02 §2 F5). Pure render funcs + golden tests, replacing `GenerateLocalPVManifest` |
| `pkg/kube/isolation.go` | Render + apply the per-repo-namespace default-deny INGRESS NetworkPolicy and the ValidatingAdmissionPolicy denying hostPath/hostNetwork (02 §8 F7/F9; the allow-proxy rule ships in the shape spike (e) verdicts) |
| `pkg/kube/secrets.go` | `ApplySecrets(ctx, namespace, map[string]SecretSpec)` — materialize config-injected secrets as labelled k8s Secret objects (label `rediacc.io/injected=true` so the fork scrub can enumerate them, 02 §4 F2); values arrive via stdin, never argv |
| `pkg/kube/role.go` | Render the per-namespace ROLE ConfigMap (`REDIACC_ROLE/WRITES/DATASTORE`, 02 §4) |
| `pkg/kube/scrub.go` | Fork-time scrub: delete labelled Secrets, scrub-all third-party Secrets, sweep legacy SA-token Secrets, rewrite the ROLE ConfigMap (02 §4 step 2; invoked from the fork arm of identity rewrite) |
| `pkg/kube/teardown.go` | Runtime-neutral `TeardownLeak` (replaces `NamespaceTeardownLeak`; fields: `Namespace`, `RepoDir`, `Volumes []string`, `Reason` + the whitespace-collapsing `notef`) — the leak-REPORTING contract survives per 02 §9 even though every Ceph field dies |

**Modified files**:

- `pkg/kube/wrapper.go`: DELETE fields `CephPool`, `CephCluster`, `cephExec`,
  `KubeletDir` (sole consumer is ceph-csi facts, `ceph_backend.go:189`; the
  `distro.KubeletRootForMount` stamp in `cmd/renet/kube_root.go:167` goes with it —
  keep the distro function itself, kubelet args still use the relocated root). ADD
  `DatastoreName string` (registry name; `Datastore` stays the resolved mount path).
- `pkg/kube/deploy.go`: `ManifestsDir` → `<ds-mount>/repos/<repo>/manifests`;
  `materializeAndBindPVs` + `GenerateLocalPVManifest` replaced by
  `materializeVolumes` (LUKS image provision via the reworked volume package + loop/LUKS
  mount + `storageclass.go` PV apply); `Apply`/`Deploy` lose the `EnsureCephBackend`
  branch, gain `ApplyIsolation` + ROLE ConfigMap + `ApplySecrets` calls (this is the
  `KubeRuntime.Deploy` body, §1.7).
- `pkg/kube/namespace.go`: DELETE `resolvePVBackend`, `pvBackendRBD`,
  `pvBackendDatastore`, the rbd branch of `ForkNamespace`, the ceph-marker read in
  `NamespaceDelete`. `ForkNamespacePrepare` reworks from per-PV-image glob
  (`pv.NamespacePVDir` + `*.img`) to ONE `cp --archive --reflink=always` of
  `<ds-mount>/repos/<repo>` → `<ds-mount>/repos/<repo>-<tag>` after `syncfs` on each
  mounted volume (inner-fs-first, the #440 lesson) — the data+WAL atomicity bug
  (01 §5.2) dies by construction, and the C1 invariant (no mountpoints inside the
  folder) is what makes this executable with the parent live; the fork's own volume
  mounts are created fresh under `mounts/volumes/<repo>-<tag>/` at its first deploy.
  `cleanupNamespaceState` reworks to repo-folder removal, still leak-reporting via
  `teardown.go` (volumes must pass detach-before-unlink before `os.RemoveAll`).
- `pkg/kube/manifest.go`: KEEP (`RenderManifest`, `ScanPVCs`, `PVCInfo`, router
  annotations, reserved-token checks). PVC scan now also validates every declared PVC's
  StorageClass equals the repo datastore's `rediacc-ds-<name>` and warns on
  cluster-scoped kinds (02 §2 chart-honesty).
- `pkg/kube/exec.go`, `helm.go`, `sandbox.go`: KEEP unchanged (Run/KUBECONFIG/Landlock
  machinery). `captureKubectl` MOVES from `ceph_backend.go:131` into `exec.go` — it is a
  generic read helper the scrub/isolation code needs; do not delete it with its file.

### 1.3 `pkg/kube/pv` → `pkg/kube/volume` (rename + rework)

Today's package (`pv/provisioner.go`, `pv/mount.go`) provisions plain-ext4 sparse images
at `{datastore}/pv/<cluster>/<ns>/<pvc-uid>.img` mounted at
`{datastore}/pv-mounts/<cluster>/<ns>/<pvcUID>` — both trees die (02 §6).

Rename the package to `pkg/kube/volume` (it provisions volumes, not PV objects):

- KEEP with new paths: `Provision` (now: fixed-size file + `cryptsetup luksFormat` +
  loop+LUKS open + `mkfs.ext4` — reuse `pkg/storage/luks.go` primitives rather than
  reimplementing; idempotent on existing image), `Mount`/`Unmount`/`IsMounted`
  (mount.go gains the LUKS open/close steps), `Clone` (reflink; still the fork
  primitive within a repo folder), `Sync`, `Delete` (its detach-before-unlink ordering
  at `provisioner.go:177` is the 03 §2b rule-1 reference implementation — extend it to
  close the LUKS mapping before loop detach), `parseQuantityMB`.
- DELETE: `ClusterPVDir`, `NamespacePVDir`, `ImagePath`, `MountDir`,
  `StorageClassName` const (`"rediacc-datastore"` — replaced by per-datastore
  `rediacc-ds-<name>` from `pkg/kube/storageclass.go`), `MaterializeFromPVCs`
  (deploy drives per-volume calls directly).
- NEW path helpers (C1 layout): `RepoDir(dsMount, repo)`, `ImagePath(dsMount, repo, volume)`
  (`repos/<repo>/volumes/<volume>.img`), `MountPath(dsMount, repo, volume)`
  (`mounts/volumes/<repo>/<volume>` — OUTSIDE the repo folder, never inside it).

### 1.4 `pkg/kube/csi` — deleted entirely (§2 ledger)

### 1.5 `pkg/kube/distro` + `pkg/daemon`

- `pkg/kube/distro/identity.go`: `IdentityRewriteOpts` gains
  `Operation OpFork|OpMigrate` **[P0-DECIDED — one seam, two arms, matching 04 §2.4]**:
  - `OpMigrate` = today's behavior verbatim (CA preserved, leaf serving cert + kubeconfig
    + IP rewrite; networkID kept when `NewNetworkID==0`).
  - `OpFork` = full PKI re-mint + scrub. **Spec 05 §3 is the single owner of the exact
    procedure — do not restate or shortcut it here.** Spike (d) proved the naive
    shorthand ("delete `<data-dir>/server/tls/`") is INSUFFICIENT: kine's `/bootstrap`
    entry restores the parent CA on next boot; the true re-mint is spec 05 §3's
    multi-step scrub (tls + bootstrap-entry handling), followed by `pkg/kube/scrub.go`
    (labelled-Secret delete, third-party scrub, SA-token sweep, ROLE ConfigMap rewrite)
    once the API is Ready, then a fresh join token. New networkID mandatory. The fork
    arm takes `Role` (fork|rehearsal) + `Writes` (local|ceph) inputs (gate C13, matching
    spec 05 §3's `IdentityOp`) — the ROLE ConfigMap is rewritten with both.
- `pkg/kube/distro/prepfork.go`: KEPT (02 §6 keep list) but demoted — the hot group-snap
  fork path (04 §2) never drains; `PrepFork` remains for the cross-site migrate cutover
  (down-before-final-snap) and as the mount-sweep utility.
- `pkg/kube/distro/k3s.go` / `external.go`: KEEP. `external` shrinks per 02 §10b
  (kubeconfig + healthcheck only) — lifecycle methods return a first-class
  `ErrNotApplicable` instead of attempting work.
- `pkg/daemon/storage_maintain_timer.go:31`: the unit hardcodes
  `repository maintain --datastore /mnt/rediacc`. Change ExecStart to a new
  `renet storage maintain --all` that iterates the registry (default + named) and runs
  the §3.5 inventory sweep + overlay-fill check per datastore. Bump
  `storageMaintainTimerVersion`.
- `pkg/daemon/k3s_systemd.go`: KEEP (per-networkID unit = 02 §10b requirement 4). The P2
  node-lifecycle shutdown unit (02 §3) is NEW daemon work
  (`pkg/daemon/node_lifecycle.go`): ordered pods-with-grace → k3s stop → volume
  unmounts → datastore detach/lock-release; boot reverses from the registry. Not P1.

### 1.6 `pkg/functions/commands` — bridge registry

Mechanism (verified): `RegisterWithSchema(&FunctionDef{...}, builder)` in per-family
`init()` (`registry.go:82`); `renet functions generate-types` emits
`packages/shared/src/renet-contract/data/functions.generated.ts`;
`.ci/scripts/quality/check-e2e-coverage.sh` greps packages/e2e-tests for every generated
name (raw `resource_verb` or spaced `resource verb`), with a BLOCKER allowlist. 152
functions registered today (counted per family: repository 33, ceph 34, system 19,
kube 18, daemon 15, container 12, datastore 10, backup+checkpoint 9, kube_registry 2).

Changes: full diff in §4 (reworked to the gate C2 ruling — spec 02 §3.3's unified
dispatch model wins). File-level: `datastore.go` rewritten (new verb set); `kube.go`
loses `KubeCsiTemplateCommand` AND the entire namespace/deploy/pv builder set
(`KubeNamespaceCreateCommand`, `KubeDeployCommand`, `KubeNamespaceForkCommand`,
`KubeNamespaceDeleteCommand`, `KubePVProvisionCommand`, `KubePVCloneCommand`,
`KubePVDeleteCommand` — their bodies fold into `KubeRuntime` behind the runtime-generic
`repository_*` family), keeping only the node-infra verbs (install/join/identity/
prep-fork/node-remove/upgrade/uninstall/kubeconfig/health); `repository.go` renames
`repository_takeover` → `repository_promote` and adds `repository_health`/
`repository_logs`/`repository_exec`. The shared helper `RequireDatastore`
(`registry.go:186`) changes meaning: the `datastore` vault param becomes a NAME resolved
on-machine via the registry, not a path **[P0-DECIDED]** — renet owns path resolution;
the CLI stops shipping `/mnt/rediacc` strings (grep the CLI for `DEFAULTS.DATASTORE` in
P4).

### 1.7 `pkg/reporuntime` — the RepoRuntime home (gate C10)

New top-level package (NOT inside pkg/repository or pkg/kube, so neither world imports
the other). Named `pkg/reporuntime` per the gate ruling — `pkg/runtime` would shadow the
stdlib `runtime` import in any file touching goroutines/GC. The interface definition,
file layout (`env.go`, `leak.go`, `factory.go`, fixtures, `CONTRACT.md`), and the
contract-test suite (CT-01..15) are spec 02's deliverable and its layout stands; this
file's obligations are only: DockerRuntime delegates to `pkg/repository` + `pkg/compose`,
KubeRuntime delegates to `pkg/kube` (§1.2's reworked `Apply`/`Deploy`/fork/teardown are
its method bodies), and implementations never touch storage — they receive mounted paths
from `pkg/datastore` (02 §9). Dispatch selects the implementation via
`reporuntime.Detect` reading the on-datastore descriptor
(`<ds-mount>/.rediacc/datastore.json`, gate C2/C6) — this is what makes the
runtime-generic `repository_*` bridge family (§4) possible.

### 1.8 Other load-bearing packages

- `pkg/rbd` (`cowclone.go`): KEEP — it becomes the `--writes local` engine. Change
  `DefaultCOWDirPath` from `/tmp/cowdata` to `/var/lib/rediacc/cow` (03 §2 hardening;
  tmpfs/reboot loss); overlay-fill monitoring joins `pkg/list/storage_health.go`.
  P0 spike (f) may swap dm-snapshot for dm-thin inside this package; the external
  surface (`COWClone`, `MountOptions`) is designed to survive that swap.
- `pkg/kube/registry` (zot): KEEP, reframed per gate C3 (spec 05 §5 is the design owner).
  TWO distinct zot roles: (a) the machine-level pull-through CACHE keeps its current
  shape and upstream-mirror role — `kube_registry_up`/`kube_registry_wire` unchanged;
  (b) NEW per-repo registry instances for locally built images (F4): one
  `rediacc-registry-<networkID>.service` per opted-in repo, sync disabled, blob store at
  `repos/<repo>/registry/` (so images ride the fork/migrate unit), port range
  21000-28999, logical host `registry.<repo>.rediacc.internal` wired via
  registries.yaml + hosts.toml. The per-repo units are started/stopped by `datastore
  attach`/`detach` (spec 05 §4 step 5) — **no bridge-visible verb**: unit lifecycle is
  internal to attach/detach plus the boot reconcile, exactly like the per-repo dockerd
  units today. `Options.StorageDir` (verified already parameterized, `zot.go:62`) is the
  reuse seam for (b).
- `pkg/list`: extend `renet list all --json` with a `datastores` section (registry dump +
  live mount/holder verification) — this is the truth source for `config reconcile`
  (02 §11 R2-F2). `pkg/list/storage_health.go` gains overlay-fill + expected-vs-actual
  holder diffs.
- `pkg/repository`: mostly untouched in P1 (the docker model is the thing being
  preserved). `lifecycle.go:88` picks `storage.TypeLUKS` vs `TypeDirectory` by
  encryption — unchanged. ROLE derivation for env injection reads the existing fork
  state (`state.go` `IsFork`/grand lineage). `repository.go:97` joins
  `<datastore>/repositories/<name>` — unchanged for docker repos; the datastore ARG is
  what becomes name-resolved.
- `pkg/snapshot`, `pkg/locking`, `pkg/credentials`: KEEP; snapshot is reused by
  `datastore snapshot` (local backend); the keyfile dir (`.credentials/keys`) stays
  per-datastore.

---

## 2. Per-file DELETE ledger

Execution rules: (a) delete in the order listed — leaf packages first, callers already
rewritten by their §1 items; (b) after each area run
`go build ./... && go vet -tags "root ebpf_e2e" ./... && .ci/scripts/quality/deadcode.sh`
— the dead-code gate FAILS ON STALE ALLOWLIST ENTRIES too, so sweep
`.deadcode-allowlist` for any entry whose import path you delete (none of the current
entries reference `pkg/kube/csi` — verified — but re-check after renames since entries
are path-canonical); (c) i18n keys referenced only by deleted cobra commands
(`cmd.kube.csi.*`, `cmd.datastore.unfork.*`, …) are swept by the renet i18n backfill
check.

### 2.1 `pkg/kube/csi/` — DELETE the entire package

| File | Symbols | Depended on by (today) | Replacement |
|---|---|---|---|
| `namespace.go` (465) | `NamespaceManager`, `NewNamespaceManager`, `EnsureNamespace`, `NamespaceExists`, `ListNamespaceImages`, `CloneNamespace`, `cloneImage`, `snapArgs`, `cloneArgs`, `imageWatchers`, `waitImageUnwatched`, `restoreAndRemoveTrash`, `trashEntryStatuses`, `forceUnmapNamespace`, `imageAbsent`, `namespaceSnapshots`, `DeleteNamespace`, `watcherDrainTimeout`, `watcherPollInterval` | `pkg/kube/ceph_backend.go` (`namespaceManager`), `cmd/renet/kube_csi.go` (`namespaceManager` helper + ensure/list/clone/delete cmds) | none — RADOS namespaces leave the model; repo isolation = one folder per repo inside a datastore image |
| `consumer.go` (295) | `SyntheticClusterID`, `StorageClassName`, `SnapshotClassName`, `RenderStorageClass`, `RenderDriverInstall`, `stripDocsByKind`, `RenderStaticRBDPV`, `StaticPVSpec`, `MergeConfigEntry`, `RemoveConfigEntry`, `RenderConfigMap`, `ForkNamespaceLabel` | `ceph_backend.go` (all of them) | `pkg/kube/storageclass.go` (per-ds no-provisioner SC + local PV render) |
| `template.go` (274) | `ClusterFacts`, `RenderManifests`, `renderManifests`, `defaultResourceName`, `GatherClusterFacts`, `parseMonitors`, `DefaultNamespace` | `ceph_backend.go` (`gatherCephFacts`), `cmd/renet/kube_csi.go` (template cmd) | none — no in-cluster driver until the P3 thin CSI (which is NEW code, not a ceph-csi descendant) |
| `embed/csi-rbd.yaml.tmpl` (390), `embed/csi-rbd-storageclass.yaml.tmpl` (32) | templates | template.go | none |
| `namespace_test.go`, `consumer_test.go`, `template_golden_test.go`, `testdata/` | — | — | golden tests for `storageclass.go`/`isolation.go` replace the render coverage |

### 2.2 `pkg/kube/ceph_backend.go` (685) + `ceph_backend_test.go` (298) — DELETE the file

| Symbol | Depended on by | Replacement |
|---|---|---|
| `cephBackendMarker`, `cephMarkerPath`, `writeCephMarker`, `readCephMarker`, `writeForkCephMarker` (`.rbd-backend.json`) | `namespace.go` (`NamespaceDelete`, `resolvePVBackend`), `forkNamespaceRBD` | none — no backend to remember; the dotfile-skip in `readPersistedManifests` (`namespace.go:245`) can stay (harmless, still correct for other sidecars) |
| `NamespaceTeardownLeak`, `notef` | `namespace.go` (`NamespaceDelete` return, `cleanupNamespaceState`), `cmd/renet/kube_namespace.go:114` (JSON payload), bridge callers reading `leaked` | `pkg/kube/teardown.go` `TeardownLeak` — SAME JSON surface minus the Ceph fields (see §5 delta 4: the type today also reports local `PVImageDir` leaks; that half is the survivor) |
| `EnsureCephBackend` | `deploy.go` `Apply`/`Deploy`, `cmd/renet/kube_namespace.go:46` | deploy applies `rediacc-ds-<name>` SC + volumes instead |
| `drainRadosNamespace`, `removeCephBackend`, `radosNamespaceDeleteBudget/RetryInterval` | `NamespaceDelete` | repo-folder teardown (volume detach-verified, then RemoveAll) |
| `gatherCephFacts`, `cephExecutorOrDefault`, `namespaceManager`, `upsertCephCSIConfigEntry`, `cephCSIDriverInstalled`, `cephFSID`, `applyBytesNoNS`, `deleteClusterScoped`, `isUnknownResourceType` | internal + `forkNamespaceRBD` | `applyBytesNoNS`/`deleteClusterScoped`/`isUnknownResourceType` MOVE to `exec.go` (isolation/scrub/SC apply need them — VAP and SC are cluster-scoped); the rest die |
| `forkNamespaceRBD`, `sourcePVCImages`, `sourcePVCImage`, `pvList`, `pvItem`, `renderRBDForkManifest`, `repointStorageClass`, `repointSpecStorageClass` | `ForkNamespace` rbd arm | single reflink of the repo folder + manifest re-render (`RenderManifest` already re-stamps); no SC re-point needed — fork inherits the SAME datastore hence the same `rediacc-ds-<name>` |
| `captureKubectl` | scrub/isolation-to-be, `cephCSIDriverInstalled`, `sourcePVCImages` | MOVE to `exec.go`, keep |
| `forkDstNamespace`, `reservedTokenErr` | both fork paths | KEEP — move `forkDstNamespace` into `namespace.go` |

### 2.3 `pkg/kube/namespace.go` — partial

| Symbol | Depended on by | Replacement |
|---|---|---|
| `resolvePVBackend` (line 157), consts `pvBackendRBD`/`pvBackendDatastore` (149) | `ForkNamespace` (187) | delete; `ForkNamespace(ctx, src, tag)` loses the `pvBackend` param |
| rbd branch in `ForkNamespace` (191-193) | — | single datastore path |
| ceph-marker read in `NamespaceDelete` (40-49) | — | gone with the marker |
| `ForkNamespacePrepare` PV-glob body (110-131: `pv.NamespacePVDir`, `*.img` glob, per-image `prov.Clone`) | fork cmd + tests | one repo-folder reflink + per-volume syncfs (§1.2) |

### 2.4 `pkg/kube/deploy.go` — partial

| Symbol | Depended on by | Replacement |
|---|---|---|
| `GenerateLocalPVManifest` (33; hostPath, claimRef, NO nodeAffinity) | `materializeAndBindPVs` (74), `deploy_test.go` | `storageclass.go` local-PV render (nodeAffinity + `rediacc-ds-<name>` SC) |
| `materializeAndBindPVs` (58) | `Apply` (122), `Deploy` (152), `ForkNamespace` (`namespace.go:219`) | `materializeVolumes` (LUKS volume images + PV objects) |
| `EnsureCephBackend` call sites (114, 147) | — | gone |
| `ManifestsDir` (15) shape `{datastore}/manifests/<cluster>/<ns>` | `namespace.go`, `ceph_backend.go`, callers of persist/replay | `RepoManifestsDir(dsMount, repo)` = `repos/<repo>/manifests` |

### 2.5 `pkg/kube/pv/` — rework to `pkg/kube/volume` (§1.3)

Deleted symbols with external callers: `NamespacePVDir` (used by `namespace.go:70,110,123`),
`MountDir` (`deploy.go:68`), `ImagePath`, `ClusterPVDir`, `StorageClassName`
(`deploy.go:61`, `cmd/renet/kube_pv.go:66`), `MaterializeFromPVCs` (verify remaining
callers at delete time; the deploy path inlines per-volume calls). The `pv/` and
`pv-mounts/` on-disk trees stop being created; the P1 VM validation must confirm no code
path still writes them (grep `"pv-mounts"` → only `pv/provisioner.go:52` today).

### 2.6 `cmd/renet` — command files

| File | Action | Replacement |
|---|---|---|
| `kube_csi.go` | DELETE (csi namespace ensure/list/clone/delete + csi template) | none |
| `kube_pv.go` | REWORK → `kube_volume.go` (provision/delete as MACHINE-LOCAL plumbing verbs — no bridge functions behind them after C2; the rbd refusal branch at `kube_pv.go:59` dies; clone subcommand dies — repo fork covers it) | `renet kube volume provision/delete` (local debugging + KubeRuntime internals) |
| `kube_root.go` | drop `FlagKubeCephPool` (32), `FlagKubePVBackend` (35), the `w.CephPool`/`w.KubeletDir` stamps (108-167) | `--datastore` becomes name-resolved |
| `kube_namespace.go`, `kube_deploy.go` | KEEP as machine-local plumbing (debugging surface), minus the `EnsureCephBackend` arm (45-47) and `--pv-backend` flag; after C2 their bridge functions are RETIRED — the queue path reaches these bodies only through the runtime-generic `repository_*` dispatch | — |
| `datastore_init.go`, `datastore_mount.go`, `datastore_unmount.go`, `datastore_fork.go`, `datastore_unfork.go` | DELETE / REPLACE | new `datastore_create.go`, `datastore_attach.go`, `datastore_detach.go`, `datastore_fork.go` (rewritten), `datastore_snapshot.go`, `datastore_list.go`, `datastore_delete.go` |
| `datastore_status.go`, `datastore_expand.go`, `datastore_resize.go`, `datastore_readme.go` | KEEP, gain `--name` | — |

### 2.7 `pkg/datastore` — partial

| Symbol | Depended on by | Replacement |
|---|---|---|
| `UnforkOptions`, `CephBackend.Unfork` (`backend_ceph_fork.go:38,171`) | `cmd/renet/datastore_unfork.go`, bridge `datastore_ceph_unfork` | `Detach(--discard)`: same strict reverse order (verified unmount → dm remove → unmap → rbd rm clone → snap unprotect+rm), now against registry state instead of caller-supplied names; the no-lazy-success rule (03 §2b rule 2) is a contract test |
| `Fork`'s mount step (`backend_ceph_fork.go:132-153`) | `datastore_fork.go` cmd | `Attach` with `--writes` (fork attach = the only way a fork gets mounted) |

### 2.8 Bridge + generated + CLI-side (executes with §4)

| Item | Where | Replacement |
|---|---|---|
| `kube_csi_template` def + `KubeCsiTemplateCommand` | `pkg/functions/commands/kube.go:146-159` | none |
| `kube_namespace_create`/`kube_deploy`/`kube_namespace_fork`/`kube_namespace_delete`/`kube_pv_provision`/`kube_pv_clone`/`kube_pv_delete` defs + builders (gate C2) | `kube.go:164-260` + `appendKubeTarget`'s `ceph-pool`/`ceph-cluster` tail | runtime-generic `repository_up`/`down`/`fork`/`delete`/`status` dispatch (§4); volume verbs survive only as machine-local `renet kube volume` plumbing |
| `datastore_init`/`datastore_ceph_init`/`datastore_ceph_fork`/`datastore_ceph_unfork`/`datastore_mount`/`datastore_unmount` defs + builders | `pkg/functions/commands/datastore.go` | §4 table |
| `config machine set-ceph` + `MachineConfig.ceph` | `packages/cli/src/commands/config-setup.ts`, consumed at `packages/cli/src/commands/datastore.ts:100-105,216-235` | `datastore create --backend rbd --pool ... --image ...` (P4; config v3 datastore records) |
| Agent-image-as-repo cluster fork (`repository_fork` per member incl. agents; `reflinkAndRewrite`; `kube_prep_fork` drain of every node; `dstAgents >= srcAgents` check) | `packages/cli/src/services/cluster/cluster-kube.ts` (`forkCluster`, `reflinkAndRewrite` at :332) | P2 anchor+rejoin: `datastore_snapshot_create --group` → clone → `datastore_attach` → `kube_identity_rewrite --operation fork` → fresh `kube_join` per agent; agent node dirs become disposable cache (04 §1) |
| `rdc datastore unfork` + `rdc datastore init --backend ceph` handlers | `packages/cli/src/commands/datastore.ts` | `datastore detach --discard` / `datastore create` (P4) |

Deleted-name hygiene: regenerating types removes the eleven deleted names from
`RENET_FUNCTIONS`, so `check:ci-e2e-coverage` stops requiring them; any e2e test STILL
referencing them keeps passing the gate but fails at runtime — grep packages/e2e-tests
for each deleted name and rewrite those suites in the same change (09 §P1 requires it;
`16-k8s-ceph` loses its subject and is rebuilt on the new model).

---

## 3. Named multi-datastore design

### 3.1 Registry — on-machine state **[P0-DECIDED]**

One JSON file per machine: `/var/lib/rediacc/datastores.json` (same directory family as
the reconcile state `/var/lib/rediacc/reconcile/`; NOT inside any datastore — it must be
readable when nothing is mounted). flock + temp+rename writes (the `pkg/locking` /
repository-state pattern). Schema:

```jsonc
{
  "version": 1,
  "datastores": {
    "ds-alpha": {
      "backend": "ceph",                      // "local" | "ceph"
      "mountPath": "/mnt/rediacc-ds/ds-alpha",
      "local":  null,                          // {"poolPath": "..."} for local backend
      "ceph":   { "pool": "rediacc_rbd_pool", "image": "ds-alpha", "clusterName": "ceph" },
      "state":  "attached",                    // "detached" | "attached"
      "writes": "",                            // "" plain | "local" | "ceph" (fork attaches only)
      "fork":   null,                          // {"parentImage","snapshot","cloneImage","cowBacking"} for forks
      "autoAttach": true,                      // false = skip on boot re-attach (`datastore attach --no-auto`, G5)
      "cluster": "prod",                       // k8s cluster backref, "" for docker-only. Set once at
                                               // `datastore create --cluster` (gate C7), immutable; independent
                                               // of backend (local-tier cluster members allowed); drives
                                               // --group snap membership + runtime derivation
      "k3sVersion": "v1.31.4+k3s1",            // written when a CP data-dir lives here; attach preflight (F14)
      "holders": {                             // expected-holders inventory (§3.5)
        "loops": ["/mnt/rediacc-ds/ds-alpha.pool"],
        "dm":    ["ds-alpha-cow"],
        "volumes": ["repos/shop/volumes/data.img"]
      }
    },
    "ds-alpha:test": { /* fork records are full entries keyed `<parent>:<tag>` (G5) —
      `:` is forbidden in datastore names, so the key is unambiguous and reuses the repo
      tag grammar; `fork` is non-null, `writes` set at attach time */ }
  }
}
```

The IMPLICIT `default` datastore never has a record (02 §7 R2-F1: implicit defaults never
enter the registry). `Resolve("default")` and `Resolve("")` return a synthesized
`Record{backend: local, mountPath: "/mnt/rediacc", poolPath: "/mnt/rediacc.pool"}` — byte-
identical to today's `NewLocalBackend` defaults (`backend_local.go:46`), which is the
zero-behavior-change guarantee: a docker user's `repo create -m M` resolves to exactly
today's paths, fstab entry, mounts dir (`/mnt/rediacc/mounts/<guid>` untouched), socket
paths. `datastore list` prints the registry PLUS the synthesized default (marked
`implicit: true`). Reserving the name: `datastore create --name default` refuses.

Two state files, two jobs (gate C2/C6): the MACHINE registry above answers "what can
this machine attach and what is attached now" (readable with nothing mounted); the
ON-DATASTORE descriptor `<ds-mount>/.rediacc/datastore.json` (spec 05 §7's location —
`.rediacc/` is the established metadata-dir convention) travels WITH the datastore and
carries `{name, backend, cluster?, writes?, k3sVersion, k3sVersionWrittenAt}` — it is
what `reporuntime.Detect` reads to dispatch the runtime-generic `repository_*` functions
(§4) and what attach uses to verify it mounted what the registry claimed. `datastore
create` writes the descriptor; `attach` stamps `writes`; both keep the registry row in
sync.

The CLI config v3 `state` bucket MIRRORS the machine registry (attach/mounter per
datastore, holders incl. the optional `volumes` array — gate C14); the machine file is
the truth, `renet list all --json` exports it, `config reconcile` re-syncs (02 §11
R2-F2). Derived `-m` routing verifies `state == attached` on the expected machine before
dispatch and errors with a reconcile suggestion on mismatch.

### 3.2 Mount-path scheme **[P0-DECIDED — refines 02 §1/04 §6, see §5 delta 1]**

Named datastores mount at **`/mnt/rediacc-ds/<name>`** (parent dir on the host rootfs);
local-backend named pools at `/mnt/rediacc-ds/<name>.pool`. The suite wrote
`/mnt/rediacc/ds-<name>`, which nests every named mountpoint INSIDE the default
datastore's BTRFS: named attaches would then require the default mounted, `detach
default` would EBUSY under any named mount, and a full default pool would break named
datastore attach — exactly the blast-radius coupling F8's `ds-control` exists to avoid.
The sibling scheme preserves everything the path was for: deterministic from the name
(mount-path stability across fork/migrate, 04 §6 — kine PV specs reference
`/mnt/rediacc-ds/<name>/repos/...` and need zero rewriting), and per-machine collision
refusal stays name-keyed. `ds-control` (02 §1) is an ordinary named datastore:
`/mnt/rediacc-ds/ds-control`.

### 3.3 Attach / detach / fork state machine (03 §2)

States per record: `detached`, `attached` (plain, writes=""), `attached` (fork,
writes=local|ceph). Transitions — every arrow is idempotent per the R2-F15 table
(re-running against half-broken state converges, 03 §2b rule 4):

| From | Verb | To | Steps |
|---|---|---|---|
| — | `create` | detached | local: allocate pool file + mkfs.btrfs (no mount). ceph: `rbd create --image-feature layering,exclusive-lock` + mkfs.btrfs via temp map. Registry record written LAST (create is complete only when resolvable). Refuses existing name or mount-path collision |
| detached | `attach` (plain) | attached | preflight (k3sVersion skew F14; name/path collision) → fence check: if lock held by a live holder REFUSE, if stale run §3.4 → map with exclusive-lock (ceph) / loop attach (local) → mount → verify mounted (`DetectBackend`) → stamp `rediacc.io/ds-<name>` node label if `cluster != ""` (remove-before-add ordering is the CALLER's job during failover, 02 §3.4) → record holders |
| detached (fork) | `attach` w/o `--writes` | — | REFUSE: "This datastore is a fork; its writes need a home. --writes local = fast, ephemeral, lost on detach. --writes ceph = durable, uses pool space." |
| detached (fork) | `attach --writes local` | attached (local) | map clone read-only → dm-COW overlay (`pkg/rbd.COWClone`; backing under `/var/lib/rediacc/cow`, `--cow-size` prominent) → mount overlay → holders incl. dm name. No fencing (never writes to Ceph) |
| detached (fork) | `attach --writes ceph` | attached (ceph) | plain clone map RW + exclusive-lock + fencing — the promote-to-real path |
| attached | `detach` | detached | plain unmount (NO `-l`; busy ⇒ FAIL loudly naming holders — kubelet still holding volume mounts is the canonical refusal) → verify unmounted → dm remove (verify) → unmap/loop-detach (verify) → lock release → holders cleared. 03 §2b rules 1+2 |
| attached (fork) | `detach --discard` | record deleted | detach as above, THEN: local-writes ⇒ remove overlay backing file (only after dm verifiably gone); both ⇒ `rbd rm` clone, snap unprotect+rm on the parent (the old `Unfork` ordering). Detach-before-unlink everywhere |
| detached | `delete` | record deleted | refuses while attached; local ⇒ verify no loop holds the pool file (`FindLoopDevicesFor`) before unlink; ceph ⇒ `rbd rm` (refuses if clones exist — Ceph enforces) |

N machines may hold independent forks of one parent concurrently (each its own clone +
overlay); the parent keeps single-writer semantics via its own lock.

### 3.4 Fencing (plain attach and `--writes ceph` only)

Executed from the ATTACHING node (any ceph client can fence; the old holder may be dead):
1. `rbd lock ls` / watcher check on the image — live holder + no `--force` ⇒ refuse.
2. `rbd lock rm` (break the exclusive lock).
3. `ceph osd blocklist add <old-client-addr>` — the dead node's in-flight writes can
   never land after the new writer mounts.
4. Map + mount on the new node.
The k8s continuation (delete stale Node object → remove old `rediacc.io/ds-<name>` label
→ attach → add label) is the cluster-layer failover sequence (02 §3) and lives in the P2
orchestration, not in `pkg/datastore`. A cleanly detached datastore released its lock and
needs no fencing on return (02 §3 node lifecycle).

### 3.5 Storage lifecycle hygiene (03 §2b, mechanized)

- **Rule 1 — detach-before-unlink**: single choke point: no code path calls
  `os.Remove` on a pool file, volume image, or COW backing without first getting a
  verified-empty holder list. Reuse `FindLoopDevicesFor` (`loop.go:266`) via the
  `loopController` seam (`backend_local.go:29`); ADD `dmController` beside it (dmsetup
  ls/remove) — dm devices escape the losetup deleted-suffix trick.
- **Rule 2 — no lazy-success**: `umount` without `-l` anywhere in datastore/volume
  teardown; each step re-verifies (findmnt / losetup / dmsetup) before the next.
  Contract-tested with mutation-style tests (the `backend_local_cleanup_test.go`
  pattern).
- **Rule 3 — inventory sweep**: `pkg/datastore/inventory.go` diffs registry
  `holders` vs live `losetup -a` + `dmsetup ls`. Orphans (live but not expected) are
  REPORTED as leaks via storage-health; auto-swept only when provably stale (backing
  file gone — the deleted-suffix case — or registry record deleted). Runs inside the
  retargeted maintain timer (§1.5) and on `datastore attach` (convergent init: a broken
  machine fixes itself on the next attach — rule 4).
- Overlay-fill watch: `--writes local` records expose overlay usage (dmsetup status)
  through `storage_health.go`; threshold warning before the dm-snapshot invalidation
  cliff (until spike (f) potentially swaps in dm-thin).

### 3.6 Group snapshots — verified invocation contract (spike A, PASSED, HARD requirements)

Verified live on the ops fleet 2026-07-10 (Ceph Squid 19.2.4; transcript:
scratchpad `reports/spikes/spike-a-ceph-group-snap.md`). No fallback path is needed —
group-snap clone works on what renet's cephadm flow deploys today. The implementation
MUST follow this exact sequence; the tempting v20 shortcuts do not exist on Squid:

1. **Create**: `rbd group snap create <pool>/<group>@<snap>` — one atomic,
   crash-consistent instant across every member image. Group membership = the cluster's
   ceph-backed datastore images (registry `cluster` label, §3.1).
2. **Discover the snap id** (per member image): `rbd snap ls --all --format json
   <pool>/<img>`, filter entries where `namespace.type == "group"` AND
   `namespace["group snap"] == <snap>`; take that entry's `id`. This is the ONLY
   discovery path on Squid — `rbd group info` and `rbd group snap info` are
   Tentacle (v20)-only and MUST NOT appear anywhere in the implementation.
3. **Clone**: `rbd clone --snap-id <id> --rbd-default-clone-format 2 <pool>/<img>
   <pool>/<clone>`. Clone format v2 is MANDATORY at two layers: the provision-time
   `ceph config set global rbd_default_clone_format 2` (§1.1) and the per-call flag.
   Without it the clone fails ("parent snapshot must be protected") because group-owned
   snapshots cannot be protected and the auto format resolves to v1 under
   `require-min-compat-client=luminous`.
4. **Teardown — P1 verification item**: removing a group snap while v2 clones still
   exist is UNTESTED. Expected v2 behavior is trash-deferral until the last clone is
   flattened/removed, but `datastore_snapshot_delete` and `detach --discard` for
   group-derived forks must VERIFY this on the fleet before the teardown ordering is
   frozen; until then, delete clones before their group snap (the fork-before-base
   order the csi teardown already taught us).

---

## 4. Bridge-function contract diff (reworked per gate ruling C2)

**Dispatch model (C2 — spec 02 §3.3 wins)**: the `repository_*` family is
RUNTIME-GENERIC. The CLI calls ONE function per verb regardless of world;
renet-side, the builder's command (`sudo renet repository <verb> ...`) resolves the
repo's datastore, reads the on-datastore descriptor
(`<ds-mount>/.rediacc/datastore.json`, §3.1), and `reporuntime.Detect` dispatches to
`DockerRuntime` or `KubeRuntime`. The `kube_namespace_*`/`kube_deploy`/`kube_pv_*`
functions RETIRE as CLI-callable seams — keeping them would leave the CLI branching per
runtime when choosing which function to call, the exact flag-routing disease 02 §9
diagnoses, re-keyed from flags to placement. Cluster-layer node-infra functions
(`kube_install/join*/identity_rewrite/prep_fork/node_remove/upgrade/uninstall/
kubeconfig/health`) stay separate: cluster verbs are not dispatched through RepoRuntime
(spec 02 §3.3).

Baseline: 152 registered functions (§1.6). Net after this program: **150**
(−11 deleted, +9 added, 4 renamed, plus param/semantics changes listed). Everything not
listed below is KEEP with unchanged name and schema: all 34 `ceph_*` (Ceph-below
plumbing: ops-fleet bootstrap + the datastore ceph backend consume them), all 12
`container_*` (docker-world plumbing, untouched), all 15 `daemon_*`/`plugin_*`/
`network_*`, all 9 `backup_*`/`checkpoint_*`, all 19 `machine_*`/`setup`/`daemon_nop`,
`kube_registry_up`/`kube_registry_wire` (the machine-level pull-through CACHE role,
unchanged per C3 — per-repo registry units have no bridge verb, §1.8).

### 4.1 Datastore family (10 → 13)

| Today | Disposition | New name / schema notes |
|---|---|---|
| `datastore_init` | DELETE | → `datastore_create` |
| `datastore_ceph_init` | DELETE | → `datastore_create` (`backend=ceph`) |
| — | ADD | `datastore_create` — params: `name` (req), `backend` (local\|ceph, default local), `size` (req), `pool`, `image`, `ceph_cluster` (rbd CLI cluster name, ceph backend only), `cluster` (OPTIONAL k8s cluster backref, either backend — gate C7; recorded immutable in the registry + descriptor, set ⇒ kube repos only); refuses `name=default`; writes the on-datastore descriptor |
| `datastore_mount` | RENAME | `datastore_attach` — params: `name` (req), `writes` (local\|ceph; REQUIRED for fork records, refused for plain), `force` (fence a stale holder), `no_auto` (bool → registry `autoAttach=false`, G5) |
| `datastore_unmount` | RENAME | `datastore_detach` — params: `name` (req), `discard` (bool; forks only) |
| `datastore_ceph_fork` | RENAME | `datastore_fork` — params: `parent` (req), `tag` (req), `cow_size`, `snapshot` (optional: clone from an EXISTING snapshot — the group-snap cluster-fork path, §3.6 step 3 with the discovered `--snap-id`; empty = fresh single-image snap as today); creates the registry record `<parent>:<tag>` DETACHED (attach is separate; the CLI's `--attach-to M --writes W` composes two calls) |
| `datastore_ceph_unfork` | DELETE | → `datastore_detach` `discard=true` |
| — | ADD | `datastore_list` — registry dump incl. synthesized implicit default |
| — | ADD | `datastore_delete` — `name` (req); refuses attached / implicit default |
| — | ADD | `datastore_snapshot_create` — `name` XOR `group` (cluster label → rbd group snap), `snapshot` |
| — | ADD | `datastore_snapshot_list` — `name` \| `group` |
| — | ADD | `datastore_snapshot_delete` — `name` \| `group`, `snapshot` (req); group-snap-delete with live v2 clones is the §3.6.4 P1 verification item — until verified, refuse while clones exist |
| `datastore_status` / `datastore_expand` / `datastore_resize` / `datastore_validate` | PARAM | gain optional `name` (default: implicit default) — `size` semantics unchanged |

### 4.2 Kube family (18 → 10): namespace/deploy/pv seams retire

| Today | Disposition | Notes |
|---|---|---|
| `kube_csi_template` | DELETE | no replacement (ceph-csi leaves the product) |
| `kube_namespace_create` | DELETE (C2) | body folds into `KubeRuntime` behind runtime-generic `repository_create`/first `repository_up` (namespace + isolation objects applied at deploy) |
| `kube_deploy` | DELETE (C2) | → `repository_up` dispatch; the ROLE ConfigMap + env come from descriptor + repo fork-state, not a param |
| `kube_namespace_fork` | DELETE (C2) | → `repository_fork` dispatch (repo-folder reflink, §1.2) |
| `kube_namespace_delete` | DELETE (C2) | → `repository_delete` dispatch; the `leaked` JSON payload rides `repository_delete`'s output in the new `TeardownLeak` shape (Ceph fields gone, `repoDir`/`volumes` added) |
| `kube_pv_provision` / `kube_pv_clone` / `kube_pv_delete` | DELETE (C2) | volume provisioning is `KubeRuntime.ProvisionVolumes` inside deploy; `renet kube volume provision/delete` survive as MACHINE-LOCAL plumbing verbs with no bridge functions (§2.6); single-volume clone returns with the P3 CSI driver |
| `kube_identity_rewrite` | PARAM (C13) | add `operation` (fork\|migrate, REQUIRED — no default: the F1 blocker rides this flag); fork arm additionally takes `role` (fork\|rehearsal) and `writes` (local\|ceph) — F7 rewrites the ROLE ConfigMap with both; fork ⇒ PKI regen + secret scrub + ROLE rewrite + new networkID mandatory |
| `kube_install`, `kube_join_token`, `kube_join`, `kube_prep_fork`, `kube_node_remove`, `kube_upgrade`, `kube_uninstall`, `kube_kubeconfig`, `kube_health` | KEEP | node-infra layer, NOT RepoRuntime-dispatched; `kube_join`/`kube_node_remove` become the P2 `cluster join`/`cluster evict` plumbing; `kube_prep_fork` demoted to the cross-site cutover path; `kube_health` = the DISTRO healthcheck (distinct from `repository_health` below) |

`kube_secrets_apply` (this file's earlier draft) is NOT added: secret injection is
`RepoRuntime.InjectSecrets`, riding `repository_up`'s existing vault/stdin channel —
no caller exists that cannot use that path (gate C2 item 4). `pkg/kube/secrets.go`
(§1.2) remains as the KubeRuntime internal that materializes the labelled Secret
objects.

### 4.3 Repository family (33 → 36): runtime-generic + three additions

| Today | Disposition | Notes |
|---|---|---|
| `repository_up` / `repository_down` / `repository_fork` / `repository_status` / `repository_create` / `repository_delete` / `repository_list` | SEMANTICS (C2) | runtime-generic: dispatch via descriptor + `reporuntime.Detect`. Docker arm = today's behavior verbatim. Kube arm = the §1.2 bodies (deploy/teardown/folder-reflink/status). Schemas unchanged except `datastore` param is a NAME (§1.6); `repository_up`/`down` inject `REDIACC_ROLE/WRITES/DATASTORE` env server-side (derived from repo fork-state + descriptor — no new params) |
| `repository_takeover` | RENAME | `repository_promote` (06 §2); it sits in the e2e ALLOWLIST today — move the allowlist entry or (better) add the missing e2e coverage while touching it |
| — | ADD | `repository_health` (G2 — the health gate had NO bridge surface; `repo migrate`/`cluster migrate`/`rehearse`/`backup restore --up` all need it). Params: `repository` (req), `datastore`. ONE evaluation per the C5 ruled contract: runs the layered probe (runtime readiness → Rediaccfile `health()`), exit 0 ⇒ healthy, hook exit 75 ⇒ "warming" disposition, hook exit 42 ⇒ health() undefined → runtime-readiness fallback → Unknown, other nonzero ⇒ unhealthy; 30 s per-attempt timeout (a timeout = one warming). The RETRY LOOP (default 300 s window) lives in the CLI-side gate caller, never in this function. Verdict transport: renet exits 0 for any COMPLETED evaluation and the verdict rides the JSON output (`HealthReport` state `healthy\|warming\|unhealthy\|unknown`); a nonzero renet exit means infra failure (CLI exit 14) — hook exit codes never propagate to the process exit |
| — | ADD | `repository_logs` (G2/C2 item 3 — `repo logs`, spec 03 §5.4). Params: `repository` (req), `container` (optional; docker = container name, kube = pod[/container]), `lines`. Dispatch: docker → per-repo dockerd logs (the `container_logs` machinery); kube → `kubectl logs -n <ns>`. Follow-mode streaming is CLI-side |
| — | ADD | `repository_exec` (G2/C2 item 3 — `repo exec`). Params: `repository` (req), `container` (optional), `command` (req). Dispatch: docker → per-repo dockerd exec; kube → `kubectl exec -n <ns>`. Same guardrail class as `container_exec` (mutating, grandGuard) |
| `repository_mount` / `repository_unmount` | KEEP | plumbing, even though the CLI folds them into up/down |
| remaining 24 `repository_*` | KEEP | unchanged |

### 4.4 Regen + gate consequences (every P1/P2 task's DoD)

1. `private/renet/bin/renet functions generate-types --output
   packages/shared/src/renet-contract/data --version dev` after each family change.
2. `check:ci-e2e-coverage` greps packages/e2e-tests for EVERY generated name (raw
   `datastore_attach` or spaced `datastore attach`). The 9 added + 4 renamed names each
   need a real reference in packages/e2e-tests — plan the rewritten suites (16-k8s-ceph
   replacement, new datastore-lifecycle suite) to exercise them for real, not as grep
   fodder. The 11 deleted names drop out of the generated array automatically; sweep e2e
   sources for their now-dead references anyway (§2.8).
3. The e2e ALLOWLIST in `.ci/scripts/quality/check-e2e-coverage.sh` currently exempts
   `repository_takeover` — update alongside the rename or the gate fails on the new
   uncovered name.
4. Renet dead-code gate (`private/renet/.ci/scripts/quality/deadcode.sh`): fails on BOTH
   dangling references and stale `.deadcode-allowlist` entries; run per area (§2 rules).

---

## 5. Reality deltas (suite claims vs the tree)

1. **Mount-path scheme conflict (material)**: 02 §1 / 04 §6 write `/mnt/rediacc/ds-<name>`,
   which nests named-datastore mountpoints inside the default datastore's BTRFS (the
   default IS the mount at `/mnt/rediacc` — pool file `<BasePath>.pool`,
   `backend_local.go:46`). That couples every named datastore to the default's health and
   makes `detach default` impossible under any named mount. §3.2 respecifies
   `/mnt/rediacc-ds/<name>` (host-rootfs sibling); the properties the suite wanted from
   the path (deterministic, stable across machines, collision-refusable) all survive.
   **APPROVED at the P0 gate (00-gate-review.md ruling R1)**; suite files 02/04 get the
   one-line edit in the as-built pass.
2. **`resolvePVBackend` line**: cited as `pkg/kube/namespace.go:154`; the function is at
   `namespace.go:157` (the const block starts at 149). Symbol correct, drift only.
3. **`materializeAndBindPVs` at `deploy.go:58`, `FindLoopDevicesFor` at `loop.go:266`,
   `loopController` at `backend_local.go:29`**: all verified exact.
4. **`NamespaceTeardownLeak` is not Ceph-only**: `namespace.go:72` uses it to report
   local PV-image-dir teardown leaks too. The 02 §6 ledger line "delete
   NamespaceTeardownLeak" is therefore refined: the TYPE and its Ceph fields die, the
   leak-reporting CONTRACT (02 §9 "teardown must be leak-reporting") is re-homed in
   `pkg/kube/teardown.go` with the same JSON surfacing through
   `cmd/renet/kube_namespace.go` and the bridge.
5. **F4 (datastore-backed registry)**: `pkg/kube/registry/zot.go:62` already
   parameterizes `StorageDir` with a datastore-path production default — that is the
   reuse seam. This file's first draft concluded "default-value change only"; the gate
   (C3) correctly ruled that a single machine-level instance cannot serve multiple
   repos' folders, so spec 05 §5's per-repo unit design is the implementation (§1.8) —
   the machine-level pull-through CACHE keeps its role unchanged.
6. **Maintain timer hardcodes the default datastore** (not mentioned in the suite):
   `pkg/daemon/storage_maintain_timer.go:31` bakes
   `repository maintain --datastore /mnt/rediacc` into the systemd unit. Multi-datastore
   silently exempts named datastores from trim/auto-grow unless this is retargeted
   (§1.5). Added to P1 scope.
7. **e2e allowlist debt collides with the rename**: `repository_takeover` (among 20+
   legacy names) is exempted in `check-e2e-coverage.sh`; renaming to
   `repository_promote` either needs the allowlist entry moved or real coverage added.
   The suite's e2e notes (09 §3) do not mention the allowlist file.
8. **`kube_prep_fork` keep-vs-obsolete tension**: 02 §6 KEEPs it, but the 04 §2 hot
   group-snap fork explicitly replaces the drain+stop path that is its main caller
   (`cluster-kube.ts:252,406,524`). Resolved in §1.5: kept for cross-site migrate
   cutover + mount sweeping; its per-node role in FORK dies with the agent-image
   mapping.
9. **Suite identifiers confirmed real** (no phantom citations found): `EnsureNamespace`/
   `CloneNamespace` (`csi/namespace.go:94,140`), `drainRadosNamespace`
   (`ceph_backend.go:268`), `.rbd-backend.json` (`ceph_backend.go:72`), synthetic
   clusterID (`csi/consumer.go:30`), `config machine set-ceph`
   (`packages/cli/src/commands/config-setup.ts`), `datastore unfork`
   (`cmd/renet/datastore_unfork.go` + `packages/cli/src/commands/datastore.ts:304`),
   per-networkID k3s unit (`pkg/daemon/k3s_systemd.go:82`), `/tmp/cowdata`
   (`pkg/rbd/cowclone.go:22`).

# 01 — Current Architecture (the "before" picture)

**Status: HISTORICAL RECORD, frozen.** This file describes the system as it stood on
2026-07-10, BEFORE the redesign. It is deliberately not updated: it is the "before" half of
the comparison, and the motivating evidence for the delete ledger in 02 §6. For what exists
now, read 02 through 05.

Everything below was verified against code on 2026-07-10 (console `973763d30`,
renet `8478420`). Line numbers drift; identifiers are the stable reference.

## 1. Storage objects: everything is a CoW-cloneable unit

| On-disk object | Location | Contains | Clone primitive |
|---|---|---|---|
| Docker repo image | `{datastore}/repositories/<guid>` | LUKS-encrypted ext4: app data, per-repo dockerd data-root, compose files | `cp --reflink=always` (BTRFS/XFS, no fallback) |
| Cluster node "image" | same path, but **a plain DIRECTORY** (unencrypted repos use `storage.TypeDirectory`, not a file — `pkg/repository/lifecycle.go` picks type by encryption) | k3s data-dir: kine DB (control plane = ALL k8s objects incl. Secrets in plaintext), containerd store, CA/certs | `cp --archive --reflink=always` per file |
| Datastore PV image | `{datastore}/pv/<cluster>/<ns>/<pvc-uid>.img` | one PersistentVolume (plain ext4, no LUKS) | reflink (`pv/provisioner.go` `Clone`) |
| Ceph RBD image | Ceph pool, RADOS namespace per repo | one PV | `rbd snap create` + `rbd clone` (clone-format v2) |
| Whole datastore (Ceph backend) | one RBD image containing a BTRFS filesystem | ALL repos of a machine | `rbd snap` + clone + local dm-COW overlay (`renet datastore fork`) |

Key layering fact: in the docker world Ceph integrates BELOW the datastore
(datastore = one RBD image; repos inside never know Ceph exists; reflink forks still work
because BTRFS lives inside the image). In the k8s world Ceph was integrated ABOVE the
datastore (per-PVC RBD images + ceph-csi + RADOS namespaces). That inversion is the root
cause of the complexity this redesign removes.

## 2. The five fork methods today

| Method | CLI | Unit | Mechanism | Cost |
|---|---|---|---|---|
| Repo fork | `rdc repo fork --parent P --tag T -m M` | 1 docker repo image | reflink; crash-consistent (targeted `syncfs` inner-fs-first then datastore — the rediacc/console#440 lesson — then reflink, then post-sync). Parent keeps running. `--checkpoint` adds CRIU `--leave-running`. | instant, O(1) |
| Namespace fork | `rdc repo fork --parent P --tag T --cluster C` (routing is FLAG-based: `--cluster/--to-cluster/--provider` = k8s seam, `handleClusterForkSeam` → `kube_namespace_fork`) | 1 namespace + its PVs | datastore backend: sync + reflink each PV `.img` + manifest rewrite to `<repo>-<tag>`; rbd backend: `forkNamespaceRBD` = per-image `rbd snap` + cross-namespace `rbd clone` into a fork RADOS namespace + static-PV rebind + per-ns StorageClass. Backend chosen server-side (`resolvePVBackend`: rbd if CephPool or `.rbd-backend.json` marker). | ~1–5 s |
| Single PV clone | renet `kube_pv_clone` (datastore) / rbd clone (ceph) | 1 PV | reflink or rbd clone | ~5 s |
| Cluster fork | `rdc cluster fork --name C --tag T --cluster DEST` | ALL k8s node images | `kube_prep_fork` (drain, stop k3s, sweep mounts) per node → `repository_fork` control-plane FIRST then agents → mount on dest → `kube_identity_rewrite` | ~46 s (2 nodes, measured) |
| Datastore fork | `rdc datastore fork` → `renet datastore fork` | whole machine (all repos) | rbd snap → protect → clone → map + device-mapper COW overlay (`/dev/mapper/<clone>-cow`) backed by a LOCAL file (default `/tmp/cowdata`); writes never reach Ceph | instant |

Fork identity changes (docker): new repositoryGuid (mount path), new networkId (loopback
`127.0.x.x/26`, docker socket `/run/rediacc/docker-<id>.sock`), new SSH keypair, SAME LUKS
key (one header per reflink lineage), docker runtime state wiped so compose recreates
containers under the fork's project. **Secrets are deliberately NOT copied** (documented
invariant: fork's secret map is empty; secrets are injected at deploy time from config,
never stored in the image; externals see the fork as a different principal).

Cluster-fork identity changes (`pkg/kube/distro/identity.go`, "the seam that powers BOTH
fork and migrate"): new networkID + IP per node, control-plane leaf serving cert dropped and
regenerated (CA PRESERVED, so cluster secrets and the CA-derived join token stay valid),
kubeconfig rewritten, agents rejoin with the reused token. Migrate keeps the networkID
(IP-only rewrite). Ceph fsid/monmap are NEVER touched: Ceph is bootstrapped once by cephadm
outside any cluster; isolation is a RADOS namespace per repo with a synthetic clusterID
`sha256(fsid + "/" + radosNamespace)[:16]` for ceph-csi config.

## 3. Mounting: who mounts what

| Storage | Who mounts | When | Mechanism | Multi-node? |
|---|---|---|---|---|
| Docker repo | renet on the machine | repo up/mount | LUKS open + loop mount | machine-bound |
| Cluster node dir | renet on each node | cluster up | bind mount (directory storage) | each node its own |
| Datastore PV | renet on the node, pre-apply | deploy time, static | loop mount + hostPath PV pre-bound via claimRef (`materializeAndBindPVs`, `GenerateLocalPVManifest`) | NO (hostPath = node-local, no nodeAffinity emitted) |
| Ceph RBD PV | kubelet + ceph-csi node plugin | pod schedule | krbd map + mount | yes, follows the pod |

RBD PVs are `ReadWriteOnce`/`volumeMode: Filesystem`. RBD is a SAN not an NFS: one node
maps+mounts at a time; writes are replicated/durable and follow the pod on reschedule, but
are never concurrently visible across nodes (ext4 is not a cluster FS). Protection is
ORCHESTRATION-level only: k8s RWO + VolumeAttachment. The Ceph-native guard is NOT enabled —
renet's StorageClass template sets `imageFeatures: "layering"` only (no `exclusive-lock`),
so a root operator manually mapping the same image on two machines can corrupt it.

## 4. Encryption today (asymmetric)

| | Docker repo | K8s cluster node | Datastore PV | Ceph RBD PV |
|---|---|---|---|---|
| At rest | LUKS (default; `repository create` refuses without password unless `--unencrypted`) | none (TypeDirectory) | none (plain ext4 .img) | none (no csi encryption configured) |
| On-disk form | one LUKS file | directory | plain .img | RBD image |

Consequence: stealing a k8s machine's disk yields everything, including every k8s Secret in
the kine DB (k3s stores them unencrypted by default). The single-file property and LUKS are
the same feature: the file IS the LUKS container; unencrypted repos degrade to directories.

## 5. Known gaps and complexity evidence (why the redesign)

**Disposition as of 2026-07-13** (each gap below, and where it went):

| Gap | Outcome |
|---|---|
| 1. Whole-cluster fork does not clone PV data | **CLOSED by construction.** Repo data lives inside the datastore that gets group-snapshotted, so the fork carries it. Proven live: the app-data marker rides the clone on every fork run |
| 2. Namespace-fork RBD snapshots are per-image, not atomic | **CLOSED by construction.** One repo = one folder = one snapshot moment. The multi-PV inconsistency cannot occur |
| 3. Cross-machine cluster-fork image transfer is a marked follow-up | **CLOSED.** The clone lives in shared Ceph; the destination adopts a ferried record (`datastore adopt`, 04 §2 step 2b). No image transfer at all |
| 4. Agent-count constraint (`dstAgents >= srcAgents`) | **CLOSED.** The anchor model moves the control plane and lets agents rejoin fresh. Destination node count is free |
| 5. Teardown-leak machinery (~400 lines) | **DELETED** along with the objects it existed to protect |
| 6. hostPath datastore PVs are node-local with no affinity | **CLOSED.** Upstream `local`-type PVs with real nodeAffinity, behind a WaitForFirstConsumer StorageClass |
| 7. No first-class path for a locally built image into a cluster | **CLOSED.** A datastore-backed registry, so images survive fork and migrate by construction (04 §7b) |
| 8. `rdc` surface untested | **PARTLY CLOSED.** The three kube e2e suites (07 §7) now cover the cluster/datastore/repo paths end to end. Full `rdc`-surface CI coverage is still P5/P6's examples work |


1. **Whole-cluster fork does NOT clone PV data.** `forkCluster` runs prep-fork → repository
   fork → mount → identity-rewrite; no PV/RBD clone step exists in that path. PV images live
   OUTSIDE the node images, so the fork's PV objects (carried via kine) point at the PARENT's
   storage. Public docs (`packages/www/src/content/docs/en/kubernetes.md` "the cluster images
   plus every repo PV image"; the fork blog "data included") OVERSTATE the implementation.
2. **Namespace-fork RBD snapshots are per-image in a loop, not atomic** across a repo's
   volumes: a data+WAL two-PVC app can get an inconsistent snapshot pair.
3. **Cross-machine cluster-fork image transfer is a marked follow-up** (comment in
   `cluster-kube.ts` `reflinkAndRewrite`: reflink lands on the source; `backup_push` transfer
   to dest "same as migrate" is not wired in the fork path).
4. **Agent-count constraint**: `cluster fork` requires dest agents >= source agents because
   node images map 1:1. Agents are rebuildable state; the constraint is v1 simplicity.
5. **Teardown-leak machinery**: renet commit `8478420` (2026-07-10) spends ~400 lines + two
   test suites making RADOS-namespace/PV teardown fail gracefully (`NamespaceTeardownLeak`,
   detach-before-unlink ordering, wedge e2e test). This is the maintenance cost of the
   per-PVC/RADOS-ns model; the redesign deletes the underlying objects.
6. **hostPath datastore PVs are node-local with no affinity declared**, an implicit
   single-node assumption.
7. **No first-class path for a locally built container image into a cluster.** The embedded
   zot registry is an upstream pull-through cache ("never state"); the docker world builds
   inside the repo's own daemon. K8s repos have no `rdc` verb for build-and-load.
8. **rdc surface untested**: e2e drives renet over bridge SSH; zero e2e coverage of
   `rdc cluster ...`, `repo fork --cluster`, secrets fork-hygiene, `datastore fork`,
   `repo takeover`.

## 6. What is GOOD and must be preserved

- The docker repo model wholesale (single LUKS file, instant fork, secrets-from-config,
  branching family: commit/branch/checkout/merge = fork + metadata, immutable commits refuse
  to mount).
- The datastore-on-Ceph model (`datastore fork` dm-COW overlay; single writer; zero Ceph
  writes for test forks).
- `kube_identity_rewrite` (the CA-preserving fork/migrate seam) and `kube_prep_fork`.
- The manifests layer (`{datastore}/manifests/<cluster>/<ns>/`) as the declarative source.
- Crash-consistent CoW semantics ("same as a power cycle") as the documented contract.
- BTRFS snapshot backup of a datastore = every repo at one instant (`renet backup`,
  `.backup-*` snapshots).
- The honest-marketing framing itself: every published number is measured, never estimated.
  **The OLD numbers (namespace fork ~1-5s, single RBD ~5s, 2-node cluster fork ~46s, migrate
  ~16s cutover) measured the OLD architecture and are NOT comparable to the new ones.** They
  are kept here as part of the historical record only. The new architecture's measured figures
  are in the README's "What is proven live" table, and those are the ones docs and marketing
  must use (08 §0).

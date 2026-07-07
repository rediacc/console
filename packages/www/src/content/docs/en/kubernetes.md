---
title: "Kubernetes"
description: "Run Kubernetes with the Rediacc repo mentality: fork or move a running cluster, including its data, to another machine or datacenter with a short cutover."
category: "Guides"
order: 6
language: en
---

# Kubernetes

Rediacc brings Kubernetes into the product without giving up the repo mentality that the rest of the platform is built on. The differentiating claim is direct: you can **fork or move a running cluster, including its data, to another machine or datacenter with a short cutover**. This is not stop-and-restore migration and it is not zero-downtime magic. The workloads restart on the destination, the cutover is measured in seconds, and the data rides along.

Kubernetes is powered by [k3s](https://k3s.io/), a certified Kubernetes distribution, embedded in renet the same way the other server-side binaries are.

## The Object Model

Rediacc inverts the usual "cluster wraps everything" picture so that the repo mentality still applies:

- **A cluster is the container.** A machine hosts Docker repos (unchanged) and/or clusters. A single-node cluster on one machine keeps the "one file moves the whole system" story at the cluster level. Cluster state (the k3s data directory: its embedded datastore and containerd) lives in datastore-backed copy-on-write image files, one per node, with the k3s `--data-dir` bound inside the image mount.
- **A Kubernetes repo is a namespace.** `rdc repo create --cluster <name>` creates a repo whose runtime home is the Kubernetes namespace `<repo>` inside that cluster.
- **Persistent volumes are separate copy-on-write units.** PVs are RBD images on Ceph, or small datastore image files via a renet local PV provisioner on the local backend. They are never directories inside one opaque cluster image: the inner filesystem has no reflinks, so independent per-repo forks require independent PV images.

This split is what makes both promises physically possible at once: **always-copy-on-write namespace forks** (each repo's data clones independently) and **whole-cluster portability** (the cluster images plus every PV image move together).

| Concept | Docker repo | Kubernetes repo |
|---|---|---|
| Runtime home | Isolated Docker daemon | Namespace in a cluster |
| Injected env | `DOCKER_HOST` | `KUBECONFIG` |
| Deploy wrapper | `renet compose` | `renet kube` |
| Data unit | One LUKS image | Cluster images plus per-PV images |
| Fork unit | The repo image | The namespace plus its PV clones |
| Whole-place clone | (repo is the place) | `rdc cluster fork` / `rdc cluster migrate` |

## Declaring and Creating a Cluster

A cluster is a named set of node pools on a private network. Declare it in config first, then provision it.

```bash
# Declare a cluster with pools (nothing is provisioned yet)
rdc config cluster add --name prod \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# Provision the pool members, bootstrap renet on each, install components (Ceph first)
rdc cluster create --name prod
```

Pool roles are `ceph`, `k8s-server`, `k8s-agent`, and `hyperconverged` (explicit opt-in, since Ceph memory targets and kubelet eviction thresholds compete for RAM). Each pool carries the hardware asymmetry as per-pool size and disk parameters: disk-heavy Ceph nodes, cpu/ram-heavy Kubernetes nodes.

Pool members materialize into `resources.machines` as `<cluster>-<pool>-<n>` with a backref, so **every existing `-m` command works on them**: `rdc machine query`, `rdc term connect`, repo commands, and backup strategies all see cluster nodes as ordinary machines.

Cloud providers provision through [OpenTofu](https://opentofu.org/), following the same `ProviderMapping` registry that `rdc machine provision` uses, extended with a private-network block (VLAN or VPC, the MTU to stamp, the private NIC naming). Local KVM is the always-available test path via `rdc ops`.

```bash
# Inspect clusters
rdc cluster status                 # list all clusters
rdc cluster status --name prod     # full config for one cluster

# Grow or shrink a pool (adds/removes machines, joins/drains nodes)
rdc cluster scale --name prod --pool k8s --count 5

# Install components on already-provisioned members
rdc cluster install --name prod

# Tear down provisioned members and remove the cluster from config
rdc cluster destroy --name prod
```

### Getting a kubeconfig

The kubeconfig is never stored in your config file (it is large and rotates). It is fetched on demand over SSH and cached locally with `0600` permissions, following the same side-state pattern as OpenTofu workdirs and the cert cache.

```bash
rdc cluster kubeconfig --name prod
# Prints: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Kubernetes Repositories

The target flag decides the runtime. There is no type flag.

```bash
# Docker repo (unchanged): an isolated Docker daemon on a machine
rdc repo create --name shop -m server-1 --size 10G

# Kubernetes repo: namespace "shop" plus its storage, inside a cluster
rdc repo create --name shop --cluster prod --size 10G
```

Repo verbs are the single surface for repo-scoped work. Through the target-resolution funnel, roughly the whole repo command set becomes cluster-capable: `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status`, and `log` all accept `--cluster`. A cluster target resolves to its control node plus the KUBECONFIG context pinned to the repo's namespace, the analog of resolving a machine to `DOCKER_HOST` plus a working directory.

```bash
rdc repo sync upload --cluster prod -r shop --local ./config
rdc cluster kubeconfig --name prod           # export KUBECONFIG, then use kubectl directly
```

Cluster nodes also materialize into `resources.machines`, so you can SSH to a specific node with the ordinary `rdc term connect -m <cluster>-<pool>-<n>`.

### Dual-runtime Rediaccfile

Portability between Docker and Kubernetes rests on a convention, not on automatic manifest conversion. A repo that provides both a `renet compose` path and a `renet kube` path under the same `up()` and `down()` functions migrates freely in both directions, because the data-directory conventions are identical. renet injects `DOCKER_HOST` on a machine target and `KUBECONFIG` on a cluster target; `up()` reads which one is set and dispatches accordingly.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Kubernetes runtime
  else
    renet compose -- up -d             # Docker runtime
  fi
}
```

A repo that lacks the target runtime gets a clear refusal **after** the data transfer stage: the images move, and the deploy step tells you the repo does not declare a Kubernetes (or Docker) path, rather than corrupting state.

## Forking a Repository

`rdc repo fork` on a Kubernetes repo always copies data, always instantly. There is no `--full` flag and no variants.

```bash
rdc repo fork --parent shop --tag joseph --cluster prod
```

This creates namespace `shop-joseph` in the same cluster, clones every volume copy-on-write (an RBD clone on Ceph, a reflink of the PV image files on the local backend), and deploys the workloads there. The fork URL is live instantly under the parent's wildcard certificate, so no new certificate or DNS record is issued.

Destination escalation:

- `--to-cluster <name>` forks into another existing cluster. Same Ceph backend: the RBD clone stays copy-on-write. Different backend: the push machinery moves the images.
- `--provider <p>` provisions a new cluster first, with pool specs defaulting to a mirror of the source cluster's shape (flags override).

Measured in the KVM test lab, a namespace fork completes in roughly one to five seconds with the parent workload untouched and the two namespaces diverging independently.

## Forking or Moving a Whole Cluster

Whole-cluster operations live in the `rdc cluster` group, because they act on a different object (the whole place with all its repos) and cannot be expressed through a command that takes a single repo name. This is the flagship story.

```bash
# Clone an entire cluster, including its repos' data, into a new cluster
rdc cluster fork --name prod --tag staging

# Move an entire cluster, including its repos' data, to another machine or datacenter
rdc cluster migrate --name prod --to server-2
```

Both coordinate a copy-on-write of the cluster images plus every repo PV image, then rewrite node identity so the clone or the relocated cluster comes up healthy on its new addresses. Because k3s stores control-plane state in its embedded datastore, the cluster image itself is the snapshot: the consistency order is control plane first, then PVs, then agents.

The honest numbers, measured end to end in the KVM test lab:

| Operation | What it does | Measured |
|---|---|---|
| Namespace fork | Clone one repo's namespace plus PVs in place | ~1 to 5 s |
| Single-image RBD fork | Copy-on-write one Ceph-backed PV clone | ~5 s |
| Whole 2-node cluster fork | Drain, reflink control plane and agent, rewrite identity to new IPs, parent untouched | ~46 s |
| Cross-machine cluster migrate | Hot pre-copy plus the stop-and-restart cutover | ~16 s cutover |

The default consistency is **crash-consistent and referentially intact**: the same semantics as a power-cycle, which is what the workloads see. Application-consistent snapshots are available when the workload's filesystems are frozen during the copy. This is deliberately **not** presented as zero-downtime. Nobody else ships "fork a running cluster including its data" at all; the honest framing is a short, measured cutover rather than a marketing absolute.

## Storage: ceph-csi and Persistent Volumes

Ceph is provisioned by renet's cephadm flow on the `ceph` pool, **outside** any Kubernetes cluster, and clusters consume it through renet-templated ceph-csi manifests. Each cluster instance (and each fork) gets its own RBD/RADOS namespace, which is the per-tenant isolation primitive. Storage sits below all clusters, so it also backs plain Docker repos and the datastore backend, and a cluster fork clones RBD images beneath Kubernetes rather than forking its own storage backend.

On the local backend (no Ceph), a renet local PV provisioner backs each PV with a small copy-on-write image file in the datastore, reflink-cloned on fork. See [Server Reference](/en/docs/server-reference) for the on-disk layout and the renet commands.

## Choosing a Distribution

The distro is an abstraction with a small, real interface (install, join, kubeconfig, healthcheck, upgrade, and so on):

- **k3s** is the default and the only embedded distribution. It is Apache-2.0, CNCF-certified, a single relocatable binary, and both its bundled Traefik and ServiceLB are disabled in favor of the Rediacc proxy. Its `--data-dir` binds at start time, which is exactly what cluster fork and migrate need when the image mount path changes. k3s is flagged `repoEmbeddable`.
- **external** is bring-your-own-kubeconfig. Only `getKubeconfig` and `healthcheck` do real work; the lifecycle verbs return first-class "not applicable" results rather than errors.
- **RKE2** is the planned third backend for FIPS/CIS customers, not part of this release.

Cluster fork and migrate refuse to run on a non-`repoEmbeddable` distribution with a clear error instead of corrupting state, because embedding cluster state in datastore images requires a data-dir that binds at start.

## Registry

Two distinct image problems, two tools:

- **Upstream pain** (Docker Hub rate limits, denied pulls, offline): an embedded [zot](https://zotregistry.dev/) pull-through cache runs on the control pool with `sync.onDemand` against multiple upstreams (docker.io, ghcr.io, quay.io). It is embedded in renet the same way the other binaries are, and it replaces the ops test registry so every run exercises it.
- **Intra-cluster distribution**: k3s's embedded registry mirror lets nodes share already-pulled images peer to peer.

Wiring is transparent and restart-free through containerd's `certs.d/hosts.toml` and k3s's `registries.yaml`. The per-repo containerd store inside the cluster image remains the source of truth that forks and migrates; the registry is a cache in front of the internet, never state.

## Networking and URLs

Kubernetes repo URLs follow the flat scheme, with the namespace identity folded into the leftmost label and the cluster as the stable second label:

```
{service}--{repo}.{cluster}.{machine}.{base}          Kubernetes repo (namespace = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    fork (namespace = repo-tag)
```

Every namespace and every fork inherits the parent's wildcard certificate and DNS record, so fork URLs are live instantly and new certificates are issued only when a new cluster or repo is created. The router discovers Kubernetes services by polling the cluster for `rediacc.*`-annotated Services, the Kubernetes analog of reading Docker labels. See [Networking](/en/docs/networking) for the routing model and [Architecture](/en/docs/architecture) for the storage backends.

## Attribution

Rediacc conveys several third-party binaries (k3s, zot, and the others renet embeds). Print their versions, SPDX license identifiers, and source-archive URLs at any time:

```bash
rdc credits
rdc credits --licenses    # full THIRD_PARTY_LICENSES text bundled with releases
```

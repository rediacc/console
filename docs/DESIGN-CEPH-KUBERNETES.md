# DESIGN: Ceph Testing, Cluster Provisioning, and Kubernetes Repos

Status: approved v3, campaign in execution (2026-07-05). Execution plan (waves, appendices, test gates): the campaign plan file under ~/.claude/plans/ is authoritative for implementation detail; this doc is authoritative for decisions and rationale.
Revision v3: the Kubernetes object model was inverted after operator review (D6), the fork model simplified (D13), the domain scheme flattened (D12), target polymorphism of existing commands added (D14), the config schema settled (D15). Superseded ideas are not restated; decisions below are current.
Execution constraints: local working tree only. No git commit, no branch, no PR. One big-bang campaign executed by an agent team.
Agent model policy: Fable for challenging design/verification tasks and team lead, Opus for coding tasks (preferable, not strict), Sonnet for translation/naturalization.
Dev/test environment: local KVM (`renet ops` topology, bridge-tests harness) for everything that can run there. Linode (via `LINODE_API_TOKEN`, provided by the operator when needed) for the real cloud provider test and the Kubernetes migration demo.

---

## 1. Goals

1. Make the existing Ceph integration properly tested in CI (GitHub public runners, 16 GB RAM).
2. Generalize cluster provisioning: N machines of chosen sizes plus a private LAN, on local KVM and on cloud providers, behind one abstraction.
3. Bring Kubernetes into the product while keeping the repo mentality: the differentiating claim is "fork/move a running cluster, including its data, to another machine or datacenter with a short cutover".
4. Solve the container image supply problem (rate limits, denied access, offline) with a registry component.
5. Close the third-party license compliance gap and give k3s (and future embeds) a proper attribution home.
6. Clean up the "bridge" naming debt while we are in the area.
7. Extend the subdomain scheme for namespaces and clusters without breaking the fork-URL instant-availability property.

### Non-goals (this campaign)

- Zero-downtime live migration. The honest semantics stay those of `repo migrate`: hot pre-copy, cutover measured in seconds, restart on destination.
- Supporting every cloud provider with live tests. The abstraction is provider-generic; live validation targets KVM (always) and Linode (once).
- GitHub-side external contract changes (required-check names, ghcr image renames): those happen whenever this work eventually lands, recorded in the end-of-campaign issue. Everything in-tree (including the public "Renet Agent" wording and CI job names in workflow files) IS in scope.
- Rook. See decision D7.
- Automatic compose-to-manifest conversion (kompose-style). Repo authors own both runtime definitions (D13).

---

## 2. Background: verified facts this design rests on

File references are to the current working tree (renet submodule at the detached-HEAD refactor state).

### 2.1 Why Ceph CI was blocked, and why it no longer is

- Every non-bridge ops VM is floored at 4096 MB by `VMRAMMin` (`private/renet/pkg/infra/vm/kvm/driver.go:122-136`, comment: "Workers need a minimum amount of RAM for LUKS operations"). Bridge VM gets 1 GB. Full topology (1 bridge + 2 workers + 3 Ceph nodes) needs 21 GB and cannot fit a 16 GB runner. The existing `test-bridge-ceph` job survives by running zero workers (1 + 3x4 = 13 GB).
- The 4 GB justification is obsolete. LUKS2's default Argon2id KDF records its benchmarked memory cost (up to 1 GiB, resident and non-swappable) in the header at format time and replays it at every unlock; concurrent unlocks are additive and a documented OOM class. Renet #78 (`2ce9e11`) switched all repo containers to PBKDF2 with 1000 fixed iterations (`FastKDF`, `pkg/luks/luks.go:44-46`, applied in `pkg/storage/luks.go:47-52`), which needs negligible memory. Slot 0 (the human vault passphrase) intentionally keeps Argon2id; automation opens via keyfile slot 1. Security note: memory-hard KDFs exist to protect low-entropy human passphrases; the keyfile is machine-generated high-entropy, so PBKDF2 on the keyfile slot is sound.
- The Ceph datastore backend itself uses no LUKS (plain BTRFS on the RBD device, `pkg/datastore/backend_ceph.go`). Ceph node RAM is governed by Ceph daemons: `osd_memory_target` defaults to 4 GB, is tunable, and must not go below 2 GB.
- Conclusion: nothing in the current tree exploits the PBKDF2 switch. Lowering the floors is the single lever that unlocks workers + Ceph on one 16 GB runner.

### 2.2 What Ceph coverage exists vs is missing

- Exists (`.github/workflows/ct-tests.yml`): `test-bridge-workers` (5-OS matrix, bridge + 2 workers, no Ceph) and `test-bridge-ceph` (bridge + 3 Ceph nodes, no workers, 45 min budget) running `packages/bridge-tests/playwright.ceph.config.ts` suites `08` (pool/image), `09` (snapshot/clone), `12c` (full ceph stack). Tests gate purely on `VM_CEPH_NODES` being non-empty; nothing is disabled in test source for RAM reasons. VM base image caching landed in console #516.
- Missing (the actual product paths): `datastore init --backend ceph` end to end; `datastore fork`/`unfork` (CLI-only paths in `cmd/renet/datastore_fork.go`, not bridge functions, so the e2e-coverage gate never forced tests); a repo created/up/forked/pushed on a Ceph-backed datastore; the read-only architecture (RBD mapped read-only on a second client machine with local COW overlay, `pkg/rbd/cowclone.go`) across multiple clients.

### 2.3 Provisioning today: three disjoint subsystems

| System | Scope | Providers | Private network |
|---|---|---|---|
| `rdc ops` -> renet `pkg/infra` | local test cluster, role-aware (bridge/workers/ceph via `VM_*` env) | KVM/QEMU/Hyper-V, thin terraform driver (Linode, Vultr only) | flat libvirt NAT 192.168.111.0/24 |
| `rdc machine provision` -> `packages/cli/src/services/tofu/` | one cloud VM, no roles | 30 providers via `ProviderMapping` (`provider-registry.json`) | none |
| `@rediacc/provisioning` (TS) | addressing the ops cluster in tests | n/a | n/a |

`ProviderMapping` (`packages/cli/src/types/index.ts:146-160`) already abstracts instance/region/size/image/ssh/firewall per provider; `tf-generator.ts` is provider-agnostic. What it lacks: private networks and any notion of "a set of machines".

Provider network facts that the abstraction must encode:

| Dimension | Linode | AWS | Hetzner |
|---|---|---|---|
| Private primitive | VLAN (L2) or VPC (L3) | VPC + subnets (L3, mandatory) | Network (L3) or vSwitch (L2) |
| MTU on private NIC | 1500, no jumbo | up to 9001 | 1450 (vSwitch 1400) |
| Max nodes/segment | VPC 500, VLAN undocumented | very high | 100 per network |
| Local disk for OSDs | dedicated-plan local SSD | i3en/i4i NVMe (ephemeral!) | local NVMe RAID10 |

Additional facts: Linode standard LKE nodes cannot join VLANs/VPCs (so self-managed Ceph on Linode means plain dedicated instances); MTU is the single most bite-prone field (a wrong value silently wrecks Ceph replication throughput).

### 2.4 The repo runtime today (what Kubernetes must mirror)

- A repo is one LUKS image file in the datastore; fork is one `cp --reflink=always` (`cmd/renet/repository_fork.go:300-331`).
- The per-repo Docker daemon's data-root lives inside the repo mount (`pkg/daemon/setup.go:102-105`), so images/containers fork and migrate with the repo. `DOCKER_HOST` env is injected into Rediaccfile execution.
- `repo migrate` is three phases (`packages/cli/src/commands/repo-migrate.ts`): hot pre-copy via `backup_push` (rsync over SSH; FIEMAP block delta for repeat transfers, `cmd/renet/backup_push_delta.go`), short cutover (stop, delta push, unmount), start + DNS + cert-cache sync. rclone is used for storage targets. These rsync/rclone/FIEMAP mechanisms operate below the filesystem and are workload-agnostic: they will carry etcd/containerd bytes exactly as they carry Postgres bytes.
- Rediaccfile: bash contract, only `up()` and `down()` are dispatched (`pkg/orchestration/rediaccfile.go`); `renet compose` wraps docker compose and injects env. Precedent for non-Docker execution exists (`rediacc.install_as: systemd`, `pkg/compose/wrapper.go:537-548`).
- Proxy: Go router polls per-repo Docker sockets, reads `rediacc.*` labels, generates Traefik dynamic config. Hostnames `{service}.{repo}.{machine}.{baseDomain}`; forks `{service}-fork-{tag}.{repo}...`. TLS wildcard is anchored exactly one label above the leftmost label (`pkg/router/routes.go:88-101,223-229`), and matching wildcard DNS records are created at repo up (`infra-provision.ts:145-172`). Forks therefore need zero new DNS records and zero new certificates; fork URLs are live instantly.

### 2.5 Kubernetes market facts (verified against 2025-2026 sources)

- Nobody ships "fork a running cluster including data". Velero/Kasten/Trilio are stop-and-restore migrators; Cluster API clones cluster shape without data; RBD/CephFS mirroring is async DR (demote/promote, RPO gap); the only near-zero-RPO options (Ceph stretch, Portworx Metro) require a single stretched cluster within ~10 ms RTT. The niche is genuinely open.
- RBD clone is O(1) COW (ceph-csi flattens deep chains: soft depth 4, hard 8). RBD/RADOS namespaces are the per-tenant isolation primitive and ceph-csi supports them, as well as LUKS-encrypted RBD volumes.
- ingress-nginx retires March 2026; Gateway API is the forward path. We avoid both by reusing the Rediacc proxy.
- k3s v1.36.x: Apache-2.0, CNCF, binary 77.7 MB amd64 / 70.3 MB arm64, `--data-dir` relocatable per start, HA via embedded etcd, first-class airgap, built-in Traefik/ServiceLB both disable-able, embedded Spegel registry mirror GA. Airgap images tarball is 235 MB (3x the binary).
- Installer lifecycle surfaces (k3s, RKE2, k0s, kubespray, managed BYO-kubeconfig) converge on 8 verbs; only `getKubeconfig` and `healthcheck` are universal. k0s fixes data-dir at install time; kubespray spreads state across components.
- vCluster OSS core is Apache-2.0. Rancher's manager UI is trademark/EULA-restricted for redistribution. kind is CI-smoke-only (containerized nodes need the host rbd module and privileged pods).
- CNCF trademark: describing the product as "powered by k3s, a certified Kubernetes distribution" is fine; using the Certified Kubernetes logo requires our own conformance submission.

### 2.6 Embedding and licensing facts

- renet embeds gzipped CRIU 4.2 (GPL-2.0), rsync 3.4.1 (GPL-3.0), rclone 1.73.0 (MIT) for both arches via `//go:embed assets/*` (`pkg/embed/embed.go`); the CLI SEA embeds renet-linux-amd64 + renet-linux-arm64 (plus native renet on mac/win). Linux SEA is ~293 MB. Assets are extracted on target machines at `renet setup`.
- There is no `--license`/`--credits`/attribution surface anywhere: no command, no NOTICE, nothing in release artifacts. This is a live compliance gap independent of k3s: conveying GPL binaries requires shipping the license texts and making the exact corresponding source retrievable (GPLv3 s6d for rsync, GPLv2 s3 for CRIU). Bundling unmodified binaries invoked via exec is mere aggregation, so no copyleft spreads to the CLI itself.

### 2.7 Bridge naming facts

- `pkg/bridge` today is the task executor + function registry behind `renet execute` (the CLI SSHes in and runs `renet execute --executor local`). The name is a two-layer fossil: original C++ bridge, then the middleware polling daemon removed in renet #85. The ops "bridge VM" (id 1, 192.168.111.1) is a different concept: the control node of the test topology (hosts registry + RustFS), named after the agent.
- Dead leftovers found: `QueueItem` queue-polling fields (`BridgeName`, `Priority`, `Status`, `SubscriptionBlob`; no non-test readers), the CLI cloud-adapter `bridge` config field, `Global Bridges`/`bridgesByRegion` constants and the `bridges.*` i18n block (retired web console), stale `docs/observability/signals/renet.md` (cites `pkg/bridge/worker.go` which does not exist), the queue-vault half-rename (`QueueVaultV2*`), orphaned elite plugin image references.
- External contracts a full rename would break: GitHub required-check names ("Bridge Workers (os)", "Bridge Ceph"), completion signals in `.ci/config/matrix.json`, `vm-base-image-bridge-*` cache keys, `ghcr.io/rediacc/elite/bridge` image, `@rediacc/bridge-tests` workspace name, and "Bridge (Renet)" as user-facing legal text in 13 locales.

---

## 3. Decisions and rationale

### D1. Lower the VM RAM floors; add per-role RAM

Lower `VMRAMMin` and introduce per-role knobs (`VM_RAM_WORKER`, `VM_RAM_CEPH`); set `osd_memory_target` (~1.5-2 GB) in the Ceph provisioner's test profile.
Why: the 4 GB floor existed only for Argon2id unlock headroom; PBKDF2 removed that in renet #78 and the floor was never revisited. This one change makes the combined CI topology fit 16 GB. Ceph nodes never open LUKS at all, so their RAM follows Ceph daemon tuning, not KDF math.

### D2. New combined CI job: workers + Ceph; new product-path test suites

Keep `test-bridge-workers` (5-OS, no Ceph) and the cheap low-level `test-bridge-ceph` as-is; add `test-bridge-ceph-workers` (ubuntu only): bridge 1 GB + 1-2 workers ~2.5-3 GB + 3 Ceph nodes ~2.5 GB, inside the 90-minute budget. New suites: `13-ceph-datastore` (backend init/status/expand, repo lifecycle on RBD, `datastore fork`/`unfork`) and `14-ceph-multiclient` (read-only RBD map + local COW overlay on a second client while data originates elsewhere).
Why: the currently green Ceph job proves the plumbing functions, not the product. Fork/unfork and multi-client read-only consumption are the shipped architecture and have zero coverage. Testing is a stated hard requirement of this campaign.

### D3. New `rdc cluster` command group with node pools; do not overload `datastore`

A cluster is a named set of pools; each pool has `{name, role, count, size, disks, labels}`. Roles: `ceph`, `k8s-server`, `k8s-agent`, `hyperconverged` (explicit opt-in). Cluster members materialize into the existing flat `resources.machines`, so every current command works on them. Dynamic scaling is a pool operation: `rdc cluster scale --pool <name> --count N` maps to cephadm `orch host add`/OSD addition for Ceph pools and `joinNode`/drain+`removeNode` for k8s pools.
Why pools: they answer "which machines are Ceph and which are Kubernetes" directly, and they carry the hardware asymmetry (disk-heavy Ceph vs cpu/ram-heavy k8s) as per-pool size/disk parameters. This mirrors how every managed k8s models node groups, so it will not surprise users. Hyperconverged is supported but explicit, because `osd_memory_target` and kubelet eviction thresholds compete for RAM and OSD disks should not share NVMe queues with image pulls; making it a named role keeps the default mental model clean.
Why not extend `datastore`: a datastore is a per-machine storage pool; a cluster is a group of machines plus installed stacks. Different lifecycle, different verbs. `rdc ops` remains the dev/test profile and later becomes a thin alias over the same engine (provider `kvm`, test topology).

### D4. Extend `ProviderMapping` with a network block; KVM becomes a provider

Add to the mapping: network primitive (resource name + layer L2/L3 + whether mandatory), subnet resource, attach method, private NIC device naming, MTU to stamp, max nodes per segment, firewall model, and a disk-class hint (local NVMe / network volume / ephemeral). Implement `linode` (VLAN first, VPC as alternative), `hetzner` (cheap real-cloud validation), and a `kvm` provider that wraps the existing libvirt flow.
Why extend rather than rebuild: the 30-provider registry and generator are proven; the delta is well-bounded. Why KVM-as-provider: it makes CI exercise the identical code path customers use on clouds, which is the campaign's KVM-first rule implemented without a second code path. Why MTU is first-class: 1500 vs 1450 vs 1400 vs 9001 differences silently destroy Ceph replication performance; encoding it per provider is the whole point of the abstraction.

### D5. Kubernetes distro abstraction; k3s is the default and the only embedded distro

Go interface in renet (new `pkg/kube/distro`), modeled on the `DatastoreBackend` precedent: `install(role, opts)`, `getJoinToken()`, `joinNode(role, token, endpoint)`, `removeNode(name)`, `uninstall()`, `upgrade(version)`, `getKubeconfig()`, `healthcheck()`, plus knobs `dataDir` and `airgapBundle`, plus a capability flag `repoEmbeddable`. Backends in this campaign: `k3s` (repoEmbeddable=true) and `external` (BYO kubeconfig; implements only getKubeconfig/healthcheck as real work, the rest as first-class "not applicable" results, never errors). RKE2 is the planned third backend (FIPS/CIS customers), not in this campaign.
Why an abstraction at all: the operator wants users to be able to choose other Kubernetes installations; the verified lifecycle surfaces genuinely converge on these verbs, so the interface is real, not speculative.
Why k3s as default: Apache-2.0/CNCF with a freely redistributable binary; single binary with `--data-dir` settable per start (the feature the whole repo-embedding design hinges on); first-class airgap matching renet's embedded-assets pattern; ~0.5-1 GB per node so it fits both 16 GB CI and small customer VMs; certified Kubernetes upstream.
Why the `repoEmbeddable` flag: cluster fork/migrate changes the image mount path, so embedding cluster state in datastore images requires a distro whose data-dir binds at start time. k3s and RKE2 qualify; k0s (install-time data-dir) and external clusters do not. The CLI refuses fork/migrate of cluster images on non-embeddable distros with a clear error instead of corrupting state.
Why not kubespray: Ansible-shaped, duplicates renet's SSH mesh, slow in CI. Why not Rancher UI: trademark/EULA blocks redistribution. kind: CI smoke only, never product.

### D6 (v3). The cluster is the container; a Kubernetes repo is a namespace inside it

The v3 object model, adopted after operator review (it supersedes the earlier "cluster-in-a-repo" framing, where the repo contained the whole cluster):

- A machine hosts docker repos (unchanged) and/or clusters. A single-node cluster on one machine keeps the "one file moves the whole system" story at the cluster level.
- Cluster state (k3s per node: embedded etcd, containerd) lives in datastore-backed CoW image files, one per node, with `--data-dir` inside the image mount. `KUBECONFIG` is injected as the analog of `DOCKER_HOST`; a new `renet kube` wrapper (analog of `renet compose`) applies manifests/Helm from `up()`.
- A Kubernetes repo = namespace `<repo>` plus its volumes. PVs are SEPARATE CoW units: RBD images on Ceph, or small datastore image files via a renet local PV provisioner on the local backend. Never directories inside one opaque cluster image: the inner filesystem is ext4 with no reflinks, so independent per-repo CoW forks require independent PV images.
- Whole-cluster clone lives at `rdc cluster fork` / `rdc cluster migrate` (coordinated CoW of the cluster images plus every repo PV image). This carries the flagship claim.

Why the inversion: the operator's fork semantics ("fork creates a new space; the namespace is repo-tag") require per-repo data cloning inside a running cluster, which a single opaque cluster image cannot provide. The v3 model gives always-CoW namespace forks AND keeps whole-cluster portability, at the cost of a k8s repo being a set of images instead of one file. Migration machinery is unaffected: it loops the same rsync/FIEMAP delta logic per image, and etcd/containerd bytes ride the same block deltas as any other data.
Multi-node clusters: pools of node machines (D3); cluster-level fork/migrate coordinates per-node image CoW plus identity rewrite. Cross-node snapshot consistency and etcd identity (registration addresses vs `--cluster-reset`) are settled by spike S2 during implementation; the campaign commits to shipping it (operator: "do not defer anything").
vCluster is not a dependency: the "fork into the same cluster" option is implemented natively as a namespace fork.

### D7. Ceph stays external and renet-managed; no Rook; ceph-csi templated by renet

Ceph is provisioned by renet's cephadm flow on the `ceph` pool, outside any Kubernetes cluster. k8s clusters consume it through renet-templated ceph-csi manifests (cluster ID, mon list, keyring secret, StorageClass, VolumeSnapshotClass), with one RBD/RADOS namespace per cluster instance (and per fork).
Why no Rook for running Ceph: (1) layering inversion: Rook needs a cluster before storage exists, but Rediacc's Ceph also backs plain Docker repos and the datastore backend; storage sits below all clusters. (2) fork semantics: we fork clusters by cloning RBD images/namespaces beneath Kubernetes; if a cluster's Ceph lived inside that cluster, forking it would fork its own storage backend, and the fork's storage would die with the fork's control plane. (3) we script directly against RBD primitives (snap/protect/clone/namespaces) that an operator would wrap. Rook's own external-mode docs recommend exactly our topology (one external Ceph, many consuming clusters). ceph-csi deployment is a manifest-templating problem and renet already is a manifest-templating engine (compose, Traefik, systemd); keeping the operator count at zero keeps version skew under our control. Revisit Rook external mode only if ceph-csi lifecycle management proves painful.
RW vs read-only, both supported by existing primitives: RBD clone is writable (fork gets a real read-write PV set via per-fork RBD namespace clones); the existing read-only map + local COW overlay stays for read-mostly scale-out consumers.

### D8. Registry: embedded zot pull-through cache + k3s Spegel for intra-cluster

Two distinct problems, two tools. Upstream pain (Docker Hub rate limits, auth denials, offline): zot (Apache-2.0, single static Go binary) embedded like rclone, running per machine or per cluster on the control pool, with `sync.onDemand` pull-through against multiple upstreams (docker.io, ghcr, quay). Intra-cluster distribution: enable k3s `--embedded-registry` (Spegel, MIT) so nodes share already-pulled images P2P. Wiring is transparent and restart-free via containerd `certs.d/hosts.toml` and k3s `registries.yaml`.
Why zot over alternatives: CNCF Distribution's proxy handles one upstream per instance and leaks upstream-authenticated private images unless separately fronted; Harbor is a 9-container stack. Why both layers: Spegel is not a pull-through cache (an image must already exist on some node); zot is not a P2P distributor.
Migration path with instant CI value: the ops test cluster already runs `registry:2` ("reregistry") at 192.168.111.1:5000; replacing it with zot gives the new component coverage in every bridge run. The per-repo containerd store inside the LUKS image remains the source of truth that forks and migrates; the registry is a cache in front of the internet, never state.

### D9. Embed k3s (both architectures) in renet; never embed the airgap images

Add `k3s-linux-{amd64,arm64}.gz` to `pkg/embed/assets` beside rclone; extract at `renet setup` on k8s-role machines. Both arches stay embedded in every renet binary (operator decision: size is a non-issue; cross-arch provisioning is valued; note the SEA-level embedding of both renet binaries is what actually provides cross-arch, so this also keeps the build simple). zot is embedded the same way.
The 235 MB airgap images tarball is not embedded: online installs pull through zot; true airgap gets an explicit `rdc cluster k8s bundle` prefetch command.
Trademark: describe as "powered by k3s, a certified Kubernetes distribution"; no Certified Kubernetes logo until we run our own conformance submission (cheap, later).

### D10. `rdc credits` + THIRD_PARTY_LICENSES: close the compliance gap

New `rdc credits` command (precedent: `gh licenses`) printing embedded-binary attributions and pointing to a full `THIRD_PARTY_LICENSES` file bundled with releases, generated at build time (go-licenses for renet's Go deps, npm license report for the SEA JS bundle, manual entries for embedded binaries). Mirror exact-version source archives for GPL components (rsync 3.4.1, CRIU 4.2) in the releases R2 bucket and reference those URLs (GPLv3 s6d / GPLv2 s3; linking to moving upstream repos is not strictly compliant). Add a CI gate: a change to `pkg/embed/assets` without a matching credits entry fails.
Why now: the gap is live today with GPL binaries already shipping; k3s/zot widen it. The gate is what keeps every future embed honest.

### D11 (v3). Bridge rename: everything in-tree this campaign; only GitHub-side contracts wait for landing

Operator decision: "renet" stays as the agent name; "bridge" goes everywhere. Chosen names: internals `pkg/bridge` -> `pkg/functions`, TS `BRIDGE_FUNCTIONS` -> `RENET_FUNCTIONS` (and helpers, generate-types output); CI jobs -> `E2E Workers (os)`, `E2E Ceph`, plus new `E2E Ceph Workers`, `E2E K8s`; workspace `@rediacc/bridge-tests` -> `@rediacc/e2e-tests`; ops VM 1 -> "control node" (`VM_CONTROL`, `VM_BRIDGE` kept as env alias); public legal term "Bridge (Renet)" -> "Renet Agent" (English this campaign, 12 locales in the docs/i18n wave).
Sequencing inside the campaign: dead-architecture deletions first (QueueItem queue fields and `BridgeName`; CLI cloud-adapter `bridge` config field; `Global Bridges`/`bridgesByRegion`/`bridges.*` i18n block; stale observability docs describing the removed polling daemon; orphaned elite plugin image refs; stale "middleware-triggered" comments), then the mechanical rename AFTER the feature waves so the tree is not moving under the feature agents (queue-vault/`QueueVaultV2*` naming and the leftover `bridge` FUNCTION_REQUIREMENTS key ride the rename, since both touch the generated contract).
Only truly external contracts wait for the eventual landing (recorded in the end-of-campaign issue): GitHub branch-protection required-check names and the `ghcr.io/rediacc/elite/bridge` image name.
The ops "bridge VM" is a different concept that merely shares the word (the control node of the test topology); it is renamed with the cluster work.

### D12 (v3). Subdomain scheme: flat namespace token, stable cluster label, leftmost-label fork identity

Invariants, in priority order:
1. The TLS wildcard is always anchored exactly one label above the leftmost label (already the router's design).
2. Namespace and fork tag are ONE identity slot, flattened into the leftmost label. Every namespace and every fork therefore inherits its parent's wildcard cert and DNS record: URLs are live instantly, and new certs are issued only when a new cluster or repo is created (operator decision: "less cluster change but more ns/tag" keeps Let's Encrypt issuance flat; LE allows ~50 certs/week per registered domain).
3. The URL shape never encodes infrastructure: the same lineage shape regardless of where a fork physically runs. Machine/cluster labels change only when a workload physically moves, and then the existing migrate machinery (DNS record creation + cert-cache sync across machines) takes over.

Scheme (final):

```
{service}.{repo}.{machine}.{base}                        docker repo (today, unchanged)
{service}-fork-{tag}.{repo}.{machine}.{base}             docker repo fork (today, unchanged)
{service}--{repo}.{cluster}.{machine}.{base}             k8s repo (namespace = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}       k8s fork (namespace = repo-tag)
{service}--{ns}.{cluster}.{base}                         multi-machine cluster (cluster label replaces machine;
                                                          DNS A records point at the ingress nodes)
```

Why flat with a cluster label: the operator judged five nested levels painful and namespaces/tags churn far more than clusters, so the stable second label is the cluster name and the whole namespace identity folds into the leftmost label with `--`. Kubernetes namespace names are `<repo>` for the deployed repo and `<repo>-<tag>` for forks, so the URL token and the actual namespace coincide.
Implementation: extend the Tier-1 auto-route hostname format in `pkg/router/routes.go` (currently hardcoded to repo depth; the `detectDomainBase` re-anchoring already handles arbitrary depth), keep per-cluster wildcard DNS records (generalized `ensureRepoDnsRecords`), and route k8s services by polling the cluster API for `rediacc.*`-annotated Services (the k8s analog of reading Docker labels). `--` and `-fork-` become reserved tokens rejected by the Rediaccfile/compose/kube linters in service and namespace names. Fork-of-fork re-tags; suffixes never stack.

### D13 (v3). Fork semantics: one fork, always CoW; targeting decides the destination

`rdc repo fork --parent shop --tag joseph` on a k8s-hosted repo creates namespace `shop-joseph` in the SAME cluster with every volume CoW-cloned (RBD clone on Ceph; reflink of the PV image files on the local backend) and the workloads deployed there. No `--full` flag, no variants: fork always copies data, always instantly.
Destination escalation: `--cluster <name>` forks into another existing cluster (same Ceph backend: RBD clone stays CoW; different backend: the push machinery moves the images); `--provider <p>` provisions a new cluster first, with pool specs defaulting to a mirror of the source cluster's shape (flags override).
Docker repos keep today's fork semantics unchanged.
Why: the operator asked to keep it simple ("when we fork, create a new space; the namespace should be repo-tag") and to guarantee CoW everywhere, which D6's separate PV images make physically possible.

### D14 (v3). Target polymorphism: repo verbs are the single surface; `rdc cluster` holds only place-lifecycle

Existing repo commands gain cluster targets through the resolution funnel, not per-command rewrites: `resolveRemoteName` (today machine|storage for push/pull) gains `cluster` as a third kind; the `localExecutorService` funnel maps a cluster target to its control node plus KUBECONFIG context; unique names are enforced across machines and clusters so `--to <name>` stays unambiguous. Roughly 35 repo commands become cluster-capable this way (fork, migrate, push, pull, create, up/down, resize, diff, commit/branch/checkout/merge, trim, cat, mount/unmount, sync, term, vscode). Subject-style `--name` flags (the `machine` group) are untouched; the polymorphism applies only to context/destination flags. `--to`/`--from` carry three meanings today (machine; machine-or-storage; fork-name) and were audited per command; fork-name uses are untouched, and `datastore fork --to` is a fork-image suffix, not a machine.
`rdc cluster` holds only place-lifecycle plus access: create/status/scale/install/destroy/fork/migrate/kubeconfig. Cluster fork/migrate operate on a different object (the whole place with all repos on it) and cannot be expressed through a command that takes a repo name; this mirrors the existing `machine` group precedent.
`rdc repo create -m <machine>` is unchanged (docker); `--cluster <name>` creates the namespace repo. The target determines the runtime; there is no type flag, and Ceph is a backend property, never a creation target.
Docker/Kubernetes portability: the dual-runtime Rediaccfile convention. renet injects DOCKER_HOST on machines and KUBECONFIG on clusters; a repo providing both `renet compose` and `renet kube` paths under the same `up()`/`down()` migrates freely in both directions (identical data-directory conventions); a repo lacking the target runtime gets a clear refusal after the data transfer stage.

### D15 (v3). Config schema: the config file is the SSH-reachable inventory; live credentials stay out

New `resources.clusters` section: `{provider (cloudProviders key | "kvm"), network {primitive, cidr, mtu}, pools [{name, role: ceph|k8s-server|k8s-agent|hyperconverged, count, size, disks}], kubernetes {distro, version}, registry {enabled, upstreams}, ceph {pool}, controlNode}`. Pool members materialize into `resources.machines` as `<cluster>-<pool>-<n>` with a `{cluster, pool}` backref, so every existing `-m` command works on them. Kubeconfig is never stored in the config file (large, rotates): fetched on demand over SSH and cached at `~/.config/rediacc/kube/<cluster>.yaml` (0600), following the tofu-workdir and cert-cache side-state precedents; `rdc cluster kubeconfig` exposes it. Ceph keyrings stay on the machines; the config holds only non-secret references. Repos keep explicit targeting with no stored home binding, consistent with today. The schema change is additive (Zod, schemaVersion 2, no migration), and the zero-knowledge config-sync threat model is unchanged because no new secrets enter the file.

---

## 4. Architecture sketches

### 4.1 Config schema additions (CLI, Zod)

```jsonc
"clusters": {
  "prod": {
    "provider": "linode",                  // linode | hetzner | kvm | ... (registry key or custom)
    "network": { "primitive": "vlan", "cidr": "10.0.0.0/24" },
    "pools": [
      { "name": "ceph",  "role": "ceph",       "count": 3, "size": "g6-dedicated-8", "disks": [{ "purpose": "osd", "size": "200G" }] },
      { "name": "k8s",   "role": "k8s-server", "count": 3, "size": "g6-dedicated-16" }
    ],
    "kubernetes": { "distro": "k3s", "version": "v1.36.2+k3s1" },
    "registry": { "enabled": true, "upstreams": ["docker.io", "ghcr.io"] }
  }
}
```

Pool members land in `resources.machines` as `<cluster>-<pool>-<n>` with a backref, so `rdc machine query`, `rdc term connect`, repo commands, and backup strategies all work unchanged. New commands opt into both guardrail layers (grandGuard cmd-policy and MutationGate) and write audit-log entries, per the established convention for new commands.

### 4.2 renet additions

- `pkg/kube/distro`: the interface from D5; `k3s` and `external` backends. k3s backend: binary from embed, systemd unit per cluster node (`rediacc-k3s-<networkID>.service`, mirroring `rediacc-docker-<N>`), `--data-dir` inside the cluster image mount, API bound to the loopback range, bundled traefik/servicelb disabled, `registries.yaml` pointing at the machine/cluster zot, `--embedded-registry` for multi-node pools.
- `renet kube`: compose-analog wrapper injecting `KUBECONFIG` and applying manifests/Helm; the Rediaccfile linter learns the kube variants of the existing rules.
- `pkg/kube/pv`: the local PV provisioner (one CoW image file per PV in the datastore; deploy-time static provisioning in phase 1, an in-cluster CSI driver is explicit later work).
- `pkg/router`: a k8s discovery source (poll annotated Services via the cluster kubeconfig) beside the Docker-socket source; both emit the same route model.
- Ceph provisioner: test profile (`osd_memory_target`, set nowhere today), ceph-csi manifest templating, RBD namespace lifecycle (create per cluster, clone per fork).
- `pkg/embed`: k3s + zot assets; credits metadata per asset.

### 4.3 Port and isolation model for k3s-in-a-repo (spike-gated)

Target: API server on the repo's loopback gateway IP (the /26 block already allocated per networkID), kubelet/node bound via `--node-ip`/`--bind-address` within the block, NodePorts reachable only from the router. Open questions live in section 8; a time-boxed spike validates multiple k3s instances per machine, CNI choice (flannel default vs host-gw) under the eBPF /26 ACLs, and cgroup nesting under `rediacc.slice`. The spike result decides whether pods share the host netns pattern or keep flannel with policy routing.

---

## 5. Testing strategy

Four levels, cheapest first; every wave lands with its tests, and a wave is not done until its tests pass locally on the KVM loop.

1. **Go unit** (mock executor): datastore ceph backend paths, distro interface backends (k3s invocation argv, external no-ops), RBD namespace helpers, credits inventory.
2. **Generator golden tests** (no cloud, no VMs): tofu tf.json rendering per provider (linode VLAN, hetzner network + MTU, kvm), cluster pool expansion to machine specs, ceph-csi manifest templating, registries.yaml/hosts.toml generation, route generation for the flat docker/k8s/fork hostname scheme (table-driven in `pkg/router` alongside the existing driver tests).
3. **Bridge/KVM E2E** (the per-PR tier, all on the 16 GB budget):
   - `test-bridge-ceph-workers` (new): suites 13 (ceph datastore + fork/unfork + repo on RBD) and 14 (multi-client read-only + overlay). RAM: 1 + 2x2.5 + 3x2.5 = 13.5 GB worst case.
   - `test-bridge-k8s` (new): bridge 1 GB + 1 worker 4 GB. Suite 15: k3s repo up/down via Rediaccfile, service routed through proxy, fork with data divergence, migrate worker-to-worker with downtime assertion, `repo diff` across a k8s fork.
   - `test-bridge-k8s-ceph` (new, the flagship): bridge 1 + 2 workers 3 GB + 3 ceph 2.5 GB = 14.5 GB. Suite 16: 2-node k3s pool with ceph-csi PVs in an RBD namespace, fork the cluster instance into a new RBD namespace (RW clones), verify divergence, teardown ordering.
   - e2e-coverage gate: every new bridge function (kube_*, registry_*, cluster_*) needs bridge-tests coverage by name, per the existing gate.
4. **Cloud live** (manual `workflow_dispatch`-style script, cost-gated, run locally since nothing is pushed): `rdc cluster create` on Linode with a VLAN, 3-node ceph pool + 2-node k8s pool, deploy a stateful app, then the demo that motivates the campaign: migrate the Kubernetes repo from the KVM lab to the Linode cluster (cross-DC), assert data integrity and cutover time. Requires `LINODE_API_TOKEN` from the operator; the token stays in env, never in config files or the tree.

Local loop notes for the team: use `./rdc.sh` (never the bundle directly); bridge-tests harness gotchas (TMPDIR/disk, no `--parallel`, `RENET_DATA_DIR`, RustFS prepull, datastore-init ordering) are documented in the agent session playbook and prior-session notes; delete stale test forks before re-forking during iteration.

---

## 6. Implementation waves (agent-team plan)

The authoritative wave breakdown, dependencies, test gates, and per-wave implementation appendices live in the campaign plan file (~/.claude/plans/, mirrored in the session task list). Summary: 0a CI/RAM+Ceph suites, 0b dead-code cleanup, 0c credits (parallel) -> 1 cluster/provider/target layer -> 2 registry, 3 kube distro (parallel) -> S1 spike -> 4 router/DNS -> 5 k8s repo E2E -> 6 ceph-csi/RBD namespaces -> S2 spike -> 7 multi-node + cluster fork/migrate -> 8 dual-KVM-group migration -> 9 bridge rename -> 10 docs+i18n -> L Linode validation -> wrap-up (GitHub issue). Models: lead/spikes = Fable; coding = Opus preferred; translations = Sonnet. All scope committed (operator: "do not defer anything"); spikes settle HOW, not WHETHER.

---

## 7. Docs plan (packages/www)

No new sidebar category (three hardcoded maps + 13 label files make one expensive); reuse existing categories. Concepts: extend `architecture.md` (storage section: local BTRFS vs Ceph RBD backends; the k8s repo model) and `server-reference.md` (Ceph ops). Guides: Ceph backend setup into `setup.md` (fulfilling the existing broken link from `quick-start.md`), new `kubernetes.md` guide. Reference: CLI flags land in `cli.json` and regenerate `cli-application.md` (never hand-edit). Tutorials: one `tutorial-*.mdx` (fork/migrate a running cluster) later, once the feature is demoable. Every English change triggers the 12-locale freshness gate, so docs land as one batch at wave 9 with Sonnet naturalization. Marketing claims obey the no-fabricated-social-proof rule; the differentiation claim is worded as "fork or move a running cluster with a short cutover", never "zero downtime".

---

## 8. Open questions: resolved by the operator (2026-07-05)

1. **Scope**: everything committed, nothing deferred; spikes S1/S2 settle implementation parameters, not whether to ship.
2. **Internal rename**: `pkg/functions` + `RENET_FUNCTIONS` approved.
3. **Public term**: "Bridge" goes; replacement is "Renet Agent" (English this campaign, locales in the docs wave). Only GitHub-side contracts wait for landing.
4. **Default k8s CNI**: spike S1 proposes, operator approves (still the one genuinely open technical parameter).
5. **Registry**: zot default-on for cluster control nodes, opt-in per standalone machine; follow-ups recorded in the end-of-campaign GitHub issue.
6. **Linode**: region de-fra-2 (existing `my-linode` provider entry, token already in config); strictly after KVM work; reuse existing machines, destroy everything created, end with a clean create/destroy cycle.
7. **Domain scheme**: nested option dropped entirely; the flat `--` scheme with the stable cluster label is THE scheme (D12), so no override flag exists.

---

## Appendix A: key file map

CLI: `packages/cli/src/services/tofu/{provider-registry.json,provider-resolver.ts,tf-generator.ts,provision.ts}`, `packages/cli/src/commands/{datastore.ts,ops/,repo-migrate.ts}`, `packages/cli/src/schema/schemas.ts`, `packages/cli/src/services/provision/{infra-provision.ts,cloudflare-dns.ts}`, `packages/cli/src/services/executor/local-executor.ts`, `packages/cli/src/services/account/cert-cache.ts`.
renet: `pkg/infra/{opsconfig/config.go,vm/kvm/driver.go,ceph/provisioner.go,mesh/mesh.go}`, `pkg/datastore/{backend.go,backend_ceph.go,backend_ceph_fork.go}`, `pkg/rbd/{cowclone.go,devices.go}`, `pkg/luks/luks.go`, `pkg/storage/luks.go`, `pkg/embed/embed.go`, `pkg/bridge/` (rename target), `pkg/router/{routes.go,labels.go}`, `pkg/proxy/infra.go`, `pkg/orchestration/rediaccfile.go`, `pkg/compose/{wrapper.go,exec.go}`, `cmd/renet/{ops_up.go,datastore_fork.go,backup_push.go,backup_push_delta.go,repository_fork.go}`.
Tests/CI: `packages/bridge-tests/`, `packages/provisioning/`, `.github/workflows/ct-tests.yml`, `.ci/scripts/quality/check-e2e-coverage.sh`, `.ci/scripts/env/create-bridge-env.sh`.
Docs: `packages/www/src/content/docs/en/{architecture.md,server-reference.md,setup.md,networking.md,quick-start.md}`, `packages/www/scripts/validate-translation-freshness.js`.

## Appendix B: external facts and sources (abridged)

Ceph: RBD layering/namespaces and osd_memory_target (docs.ceph.com, Squid/Tentacle); ceph-csi encryption + clone depth (github.com/ceph/ceph-csi). k3s: sizes/data-dir/airgap/embedded registry (docs.k3s.io, github.com/k3s-io/k3s releases). Spegel MIT (github.com/spegel-org/spegel). zot (zotregistry.dev). Licensing: GPLv3 s5-s6 mere aggregation + corresponding source (gnu.org FAQ), Apache-2.0 s4. CNCF certified-Kubernetes terms (github.com/cncf/k8s-conformance). Providers: Linode VLAN/VPC/LKE (techdocs.akamai.com), Hetzner networks MTU 1450 (docs.hetzner.com). Market: Velero/Kasten/Portworx/CAPI docs as cited in the session research. LUKS: cryptsetup-luksFormat(8), cryptsetup FAQ, Debian #924560, systemd #14168/#19161.

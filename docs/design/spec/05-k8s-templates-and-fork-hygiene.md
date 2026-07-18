# P0 Spec 05 — K8s Templates, Volume Layout, Fork Hygiene, Failover, Registry

Part of the P0 implementation spec for the datastore-centric redesign. Sources:
`docs/design/02-target-architecture.md` (§2/§3/§4/§8/§10b), `03-fork-attach-snapshots.md`,
`04-cluster-fork-migrate.md` (§2/§4/§7b), `05-feature-layer.md` (§3/§3b),
`09-implementation-phases.md` §P0. Code citations are against the current tree
(console worktree `0707-1`, renet submodule as checked out there).

Decisions the review suite already settled are followed; decisions this document makes
are tagged **[P0-DECIDED]**.

Naming conventions used throughout: `<ds>` = datastore name, `<repo>` = repo name
(and its k8s namespace; a fork namespace is `<repo>-<tag>`), `<pvc>` = declared PVC
name. Label/annotation namespace is `rediacc.io/` (precedent:
`pkg/kube/csi/consumer.go:278` `ForkNamespaceLabel = "rediacc.io/fork-namespace"`;
node label `rediacc.io/ds-<name>` per 02 §2).

---

## 1. Manifest templates (verbatim-ready YAML)

All five objects below are rendered and applied by renet, not by the user. They are
stamped at `up()` time (namespace-scoped ones) or at datastore attach (the
StorageClass, PVs, node label). Every renet-generated object carries
`rediacc.io/injected: "true"` in labels so it is enumerable for scrub and teardown.

### 1.0 Namespace (context for everything below)

`NamespaceCreate` (`pkg/kube/namespace.go:17`) today applies a bare Namespace. The
redesign version stamps the labels the policy objects key on:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: <repo>
  labels:
    rediacc.io/injected: "true"
    rediacc.io/repo-namespace: "true"
    rediacc.io/repo: <repo>
    rediacc.io/datastore: <ds>
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
```

PSA `restricted` is the default; the audited opt-down (02 §8) rewrites only the
`pod-security.kubernetes.io/*` values to `baseline`. The VAP in 1b keys on
`rediacc.io/repo-namespace`, NOT on the PSA labels, so the opt-down never weakens
the hostPath/hostNetwork guarantee.

### 1a. Per-repo-namespace default-deny ingress NetworkPolicy

Scope decision restated from 02 §8: default-deny is **INGRESS-only**. Egress stays
open, so pod→DNS (kube-system CoreDNS) and pod→internet need no allow rule: an
ingress-only policy in the repo namespace never blocks the repo's own outbound
connections or their conntrack-tracked replies. An explicit DNS rule appears below
anyway, commented, so the template is ready if a deny-egress option ships later; it
is NOT applied in v1.

```yaml
# rediacc-netpol-default-deny.yaml — applied by renet at up() into <repo>.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rediacc-default-deny-ingress
  namespace: <repo>
  labels:
    rediacc.io/injected: "true"
spec:
  podSelector: {}          # every pod in the repo namespace
  policyTypes: [Ingress]   # ingress-only by design (02 §8): egress stays open
  ingress: []              # deny all ingress; allowances are separate policies
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rediacc-allow-intra-namespace
  namespace: <repo>
  labels:
    rediacc.io/injected: "true"
spec:
  podSelector: {}
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector: {}   # any pod in THIS namespace (same-namespace only:
                            # a bare podSelector never crosses namespaces)
```

**Proxy ingress rule — RESOLVED by spike e
(`reports/spikes/spike-e-netpol-psa.md`): the in-cluster proxy leg, matched by
label selector, is the ONLY correct form; every ipBlock variant is dead.**
The Rediacc proxy today is a host process targeting the host-local ClusterIP
(`pkg/kube/manifest.go:104-110`); spike e measured on k3s v1.36.2 what the policy
controller actually sees for host-originated traffic:

- flannel masquerades host→pod traffic: cross-node arrives as the SENDING node's
  `flannel.1` address (`10.42.<n>.0`), same-node as the local `cni0` gateway
  (`10.42.<n>.1`), NEVER as the node's LAN IP. An ipBlock on the LAN IP matches
  nothing (verified: 000/blocked).
- an ipBlock on the flannel/cni0 address matches mechanically (verified: 200) but
  means "ANY process in that node's host netns" (proxy, root shells, kubelet
  probes alike): proxy precision is unrecoverable at L3.
- **same-node host→pod traffic BYPASSES NetworkPolicy entirely** (verified: 200
  under pure default-deny with zero allow rules; kube-router exempts node-local
  cni0-sourced traffic as the kubelet-probe path). On the datastore node itself a
  host-side "proxy-only" rule is therefore not merely imprecise but unenforceable.

Consequence: the proxy's CLUSTER-FACING leg runs as a pod in `rediacc-system`
(proxy-side work item, P1/P2), and the allow rule ships as:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rediacc-allow-proxy
  namespace: <repo>
  labels:
    rediacc.io/injected: "true"
spec:
  podSelector: {}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: rediacc-system
          podSelector:
            matchLabels:
              app.kubernetes.io/name: rediacc-proxy
```

Docs honesty note: until the in-cluster leg lands, host-side proxy traffic reaches
repo pods via the same-node bypass (or would need a flannel-IP allowance
cross-node); the "proxy only" isolation claim begins when the in-cluster leg does,
and is never claimed before that.

```yaml
# NOT APPLIED IN V1 — kept for a future deny-egress option only.
# apiVersion: networking.k8s.io/v1
# kind: NetworkPolicy
# metadata: { name: rediacc-allow-dns-egress, namespace: <repo> }
# spec:
#   podSelector: {}
#   policyTypes: [Egress]
#   egress:
#     - to:
#         - namespaceSelector:
#             matchLabels: { kubernetes.io/metadata.name: kube-system }
#           podSelector:
#             matchLabels: { k8s-app: kube-dns }
#       ports:
#         - { protocol: UDP, port: 53 }
#         - { protocol: TCP, port: 53 }
```

Enforcement reality: VERIFIED by spike e on stock k3s v1.36.2. The embedded network
policy controller (kube-router lineage) is active with the default flannel backend,
no CNI swap or extra install: default-deny blocked a cross-namespace pod curl
(exit 7) and cross-node host curls (timeout). Two verified boundaries of that
enforcement, both load-bearing for this spec: same-node host traffic is exempt (see
the proxy-rule finding above), and hostNetwork pods bypass NetworkPolicy entirely
(a hostNetwork pod on the target's node curled a default-deny-protected pod, 200),
which is exactly why hostNetwork denial in 1b and PSA stays part of the isolation
story.

### 1b. ValidatingAdmissionPolicy: hostPath/hostNetwork defense-in-depth (F7)

**Status re-framed after spike e: SHIPPED, but as defense-in-depth, not as a
required backstop.** Spike e verified that PSA `baseline` on k3s v1.36 already
DENIES both hostPath volumes ("violates PodSecurity baseline:latest: hostPath
volumes") and hostNetwork pods ("host namespaces (hostNetwork=true)"), and
`restricted` denies both plus more, so the chart-compatibility opt-down ladder
(`restricted → baseline`) keeps every isolation guarantee this design needs with
PSA alone. The VAP stays (lead ruling at the P0 gate) because two realistic paths
around PSA remain: a namespace opted down to `privileged`, and tampering with the
`pod-security.kubernetes.io/*` labels: the VAP keys on `rediacc.io/repo-namespace`
instead and holds through both.

The render-time lint already rejects hostNetwork pods, hostPort, and
NodePort/LoadBalancer Services for manifests that flow through renet
(`pkg/kube/manifest.go:113-131`, `lintSecurity`); the layering is therefore
lint (render) → PSA baseline/restricted (namespace) → VAP (API server,
label-keyed) for objects that never pass through renet's renderer.

Version gate: `admissionregistration.k8s.io/v1` VAP is GA since k8s 1.30; the
embedded k3s is 1.36.2 (`pkg/embed/embed.go:43`), so no beta feature-gating is
needed.

```yaml
# rediacc-vap.yaml — applied ONCE per cluster at cluster install (not per repo).
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: rediacc-repo-namespace-guard
  labels:
    rediacc.io/injected: "true"
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: >-
        !(has(object.spec.hostNetwork) && object.spec.hostNetwork == true)
      message: "hostNetwork pods are not allowed in rediacc repo namespaces (bypasses NetworkPolicy isolation)."
      reason: Forbidden
    - expression: >-
        !(has(object.spec.hostPID) && object.spec.hostPID == true) &&
        !(has(object.spec.hostIPC) && object.spec.hostIPC == true)
      message: "hostPID/hostIPC pods are not allowed in rediacc repo namespaces."
      reason: Forbidden
    - expression: >-
        !has(object.spec.volumes) ||
        object.spec.volumes.all(v, !has(v.hostPath))
      message: "hostPath volumes are not allowed in rediacc repo namespaces; use a declared PVC."
      reason: Forbidden
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: rediacc-repo-namespace-guard
  labels:
    rediacc.io/injected: "true"
spec:
  policyName: rediacc-repo-namespace-guard
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      matchLabels:
        rediacc.io/repo-namespace: "true"
```

Notes:
- hostPID/hostIPC are included beyond F7's letter: they break the process-isolation
  row of the 02 §8 parity table the same way hostPath breaks the filesystem row, the
  CEL is two lines, and the render-time lint should grow the same two checks in P1
  so the two layers stay equivalent.
- The binding matches by namespace label, so `rediacc-system` and `kube-system` are
  untouched (the in-cluster proxy leg pod may itself need host reachability).
- PSA `baseline` vs hostPath is RESOLVED: baseline denies hostPath AND hostNetwork
  (spike e §6, error strings quoted there; plain pods pass, so baseline remains a
  usable opt-down for real charts). The VAP is a policy choice recorded as such,
  not a correctness requirement.

### 1c. Per-datastore no-provisioner StorageClass (F5)

Applied at datastore attach (first attach creates it; idempotent apply after).

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: rediacc-ds-<ds>
  labels:
    rediacc.io/injected: "true"
    rediacc.io/datastore: <ds>
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
allowVolumeExpansion: false
```

Every generated PV and every declared PVC in a repo placed in `<ds>` references
`rediacc-ds-<ds>`. This replaces the single shared class `rediacc-datastore`
(`pkg/kube/pv/provisioner.go:29`), which goes on the delete ledger. `repo up`
rejects a PVC whose storageClassName is empty or names a class that is not this
repo's datastore class (deterministic binding, no default-SC adoption, 02 §2).
The F5 hazard is VERIFIED live, not theoretical: stock k3s ships `local-path` as
the cluster DEFAULT StorageClass (spike b, `reports/spikes/spike-b-local-pv.md`),
so an SC-less PVC would be silently adopted by rancher local-path provisioning
onto the node disk instead of the datastore: the rejection rule is what prevents
that wrong-world bind.

### 1d. Generated `local` PV (per declared PVC)

Replaces the hostPath PV of `GenerateLocalPVManifest` (`pkg/kube/deploy.go:33-52`).
`local` PVs REQUIRE nodeAffinity, which is exactly the property the datastore model
wants; hostPath PVs ignore topology.

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: rediacc-<repo>-<pvc>
  labels:
    rediacc.io/injected: "true"
    rediacc.io/datastore: <ds>
    rediacc.io/repo: <repo>
spec:
  storageClassName: rediacc-ds-<ds>
  capacity:
    storage: <size>              # the PVC's declared size = the LUKS image size
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  volumeMode: Filesystem
  local:
    path: <ds-mount>/mounts/volumes/<repo>/<pvc>   # opened+mounted LUKS mapper (§2)
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: rediacc.io/ds-<ds>
              operator: In
              values: ["true"]
  claimRef:                      # pre-bind: deterministic PVC↔PV pairing
    namespace: <repo>
    name: <pvc>
```

Per-volume LUKS notes (F8, 05 §3): the path above is the mounted filesystem inside
the opened LUKS mapper of `<ds-mount>/repos/<repo>/volumes/<pvc>.img` (§2). The PV
object never references the image file or the mapper; only renet knows those, which
is what keeps the layout CSI-adoptable and keeps PV objects in kine stable across
cluster fork (mount-path stability trick, 04 §6: same `<ds-mount>`, same repo and
PVC names, zero PV rewriting).

Node label contract: `rediacc.io/ds-<ds>=true` is stamped on the mounting node at
attach, removed at detach, and follows the remove-before-add rule in §4.

### 1e. Per-namespace ROLE ConfigMap (02 §4)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: rediacc-role
  namespace: <repo>
  labels:
    rediacc.io/injected: "true"
data:
  REDIACC_ROLE: "primary"        # primary | fork | rehearsal | replica
  REDIACC_WRITES: ""             # empty/omitted on a plain (non-fork) attach;
                                 #   ceph | local ONLY for fork attaches (C12:
                                 #   --writes is the fork-attach disposition,
                                 #   a primary's plain attach has none)
  REDIACC_DATASTORE: "<ds>"
```

- Written at `up()`; REWRITTEN (never deleted) by fork/rehearse identity rewrite
  (§3 step F7) and by migrate (REDIACC_DATASTORE/WRITES may change, ROLE stays
  `primary`).
- Pods consume via `envFrom: [{configMapRef: {name: rediacc-role}}]`; the same
  three variables are injected into Rediaccfile `up()/down()/health()` env
  (extends the existing env injection at
  `pkg/orchestration/up_down_workflows.go:211-216`).
- `replica` is reserved for `repo replicate` pods (05 §1); listed here so the enum
  is defined once.

### 1f. Secret materialization (k8s mapping of the env|file model) [P0-DECIDED]

Declared here because the fork scrub (§3) and example 13 depend on it; the current
CLI-side model it extends is documented in §8.

Two Secret objects per repo namespace, split by mode:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: rediacc-env
  namespace: <repo>
  labels:
    rediacc.io/injected: "true"
type: Opaque
stringData:
  <KEY>: <value>        # one entry per env-mode secret, key stored UNPREFIXED
---
apiVersion: v1
kind: Secret
metadata:
  name: rediacc-files
  namespace: <repo>
  labels:
    rediacc.io/injected: "true"
type: Opaque
stringData:
  <KEY>: <value>        # one entry per file-mode secret
```

Documented consumption conventions (docker-world parity):

```yaml
# env mode: compose parity with REDIACC_SECRET_<KEY> (§8, local-executor.ts:1143)
envFrom:
  - prefix: REDIACC_SECRET_
    secretRef: { name: rediacc-env, optional: true }
# file mode: compose `secrets:` parity, files appear at /run/secrets/<KEY>
volumes:
  - name: rediacc-files
    secret: { secretName: rediacc-files, optional: true }
volumeMounts:
  - { name: rediacc-files, mountPath: /run/secrets, readOnly: true }
```

`optional: true` is the load-bearing detail: it is what lets a scrubbed fork
(ROLE=fork, empty secret map) start its pods at all, so apps can degrade
gracefully on role (04 §4). Apps that hard-require a secret fail their readiness
probe, which the health gate reports honestly.

Re-running `up()` re-applies both Secrets idempotently: that IS the rotation story
(02 §11.5). Size honesty for config v3: the apiserver caps a Secret object at
1 MiB, so the caps drop from today's 10 MiB per value
(`packages/shared/src/config-schema/schemas.ts:155`) to the C11 merged contract
[P0-DECIDED, gate-ruled]: **env 32 KiB per value, file 256 KiB per value,
512 KiB aggregate per repo per mode** (spec 04's `SecretEntrySchema` enforces the
per-value caps, a family-level refine enforces the aggregate; base64/metadata
margin under the 1 MiB object limit).

---

## 2. Volume path and naming layout, CSI-adoptable (F6) [P0-DECIDED]

### On-disk scheme

```
<ds-mount>/                                  # e.g. /mnt/rediacc-ds/alpha (BTRFS root; R1
                                             #   sibling scheme, NEVER nested under the
                                             #   default datastore's /mnt/rediacc)
├── repos/<repo>/                            # THE fork unit: one reflink copies it all
│   ├── volumes/<pvc>.img                    # per-declared-PVC LUKS2 image (sparse)
│   ├── registry/                            # zot backing store for built images (§5)
│   ├── manifests/*.yaml                     # persisted rendered manifests (moves here
│   │                                        #   from {ds}/manifests/<cluster>/<ns>,
│   │                                        #   pkg/kube/deploy.go:15)
│   └── .rediacc/                            # repo-scoped renet metadata (no secrets)
├── mounts/volumes/<repo>/<pvc>/             # host-side LUKS mapper mountpoints;
│                                            #   OUTSIDE repos/ (see invariant below)
└── .rediacc/datastore.json                  # datastore metadata incl. k3sVersion (§7)
```

The control-plane data-dir stays at the existing distro layout inside its own repo
folder in `ds-control`: `<mount>/.rediacc/k3s/data` (`pkg/kube/distro/k3s.go:75-77`,
`distro.go:159-162`), kubelet root at `<mount>/.rediacc/k3s/kubelet`
(`distro.go:179-181`).

**Invariant: no mountpoints inside `repos/<repo>/`.** A reflink fork copies the
repo folder as a plain BTRFS subtree; an ext4 filesystem mounted on a directory
inside it would either break the reflink or be traversed as a foreign filesystem
(the exact bug class `PrepFork` sweeps for the CP image,
`pkg/kube/distro/prepfork.go:29-57`). Volume data reaches the fork through the
`.img` files, which capture everything crash-consistently; mountpoints live under
`<ds-mount>/mounts/`, which is never part of a fork and is rebuilt at attach.

### LUKS keying [P0-DECIDED]

- Format: LUKS2, one keyslot. Passphrase = the repo's existing per-repo
  `credential` (05 §3: "per-repo credential as passphrase"; the same credential the
  docker world's repo image uses, carried in config,
  `packages/shared/src/config-schema/schemas.ts` RepositoryConfigSchema `credential`).
- Mapper name: `rediacc-vol-<repo>-<pvc>` (device `/dev/mapper/rediacc-vol-...`).
- Inner filesystem: ext4 (keeps the current provisioner default,
  `pkg/kube/pv/provisioner.go:32`); fixed-size = the PVC's declared size, which is
  what restores real capacity enforcement and honest kubelet statfs (F8).
- Fork consequence, stated: a repo fork's volumes open with the PARENT credential
  (registerFork copies `credential`, `packages/cli/src/commands/repo-fork.ts:173`).
  Data-at-rest sharing is inherent to reflink CoW; the SECRET map still starts
  empty (the F2 boundary is effects and credentials-to-services, not the CoW data,
  per the fork threat model).

### Naming rules

| Object | Name | Uniqueness argument |
|---|---|---|
| PV image | `<ds-mount>/repos/<repo>/volumes/<pvc>.img` | repo folder is per-repo; PVC names unique within a namespace |
| PV object | `rediacc-<repo>-<pvc>` | namespace+PVC unique per cluster (keeps the shape of `deploy.go:34`) |
| PVC | author-declared `<pvc>`, storageClassName `rediacc-ds-<ds>` | manifest-scoped |
| StorageClass | `rediacc-ds-<ds>` | datastore names unique per config (02 §7 tagged union) |
| Node label | `rediacc.io/ds-<ds>=true` | one mounter at a time |

### StatefulSet volumeClaimTemplates name-coupling rule [P0-DECIDED]

`repo up` scans manifests for StatefulSets with `volumeClaimTemplates`. For each
template `<template>` on StatefulSet `<sts>` with `spec.replicas: N` (default 1),
renet pre-creates N images + N PVs named for the PVCs the controller WILL create:

```
PVC name (created by k8s):  <template>-<sts>-<ordinal>     ordinal in 0..N-1
image:                      volumes/<template>-<sts>-<ordinal>.img
PV:                         rediacc-<repo>-<template>-<sts>-<ordinal>
```

Each template's storageClassName must be `rediacc-ds-<ds>` (same rejection rule as
plain PVCs). Scaling the StatefulSet past the declared N leaves ordinal ≥ N Pending
by design; the honest error surface is `repo status` showing the unbound PVC, and
the fix is editing replicas in the manifest and re-running `repo up` (which
materializes the new ordinals). This is the documented chart-compatibility boundary
from 02 §2; the P7 compatibility matrix cites this rule.

### What the future CSI driver reuses unchanged (F6)

The P3 thin driver (05 §3b) adopts this layout with zero migration:

- Same image directory (`repos/<repo>/volumes/`), same LUKS2-per-volume format,
  same mapper/mount conventions. CSI `volume_id` = the datastore-relative image
  path (e.g. `repos/shop/volumes/pvc-8f1c...img`), so the driver never depends on
  a basename convention; dynamic volumes are keyed on PV name (`pvc-<uid>.img`),
  static v1 volumes keep their human `<pvc>.img` names, both coexist in one dir.
  (The switch-friendly seam already exists: `PVCSpec.UID()` isolates the keying
  decision, `pkg/kube/pv/provisioner.go:64-67`.)
- Same topology key `rediacc.io/ds-<ds>` (becomes the CSI topology domain).
- Same snapshot/clone primitive: `cp --reflink=always`
  (`pkg/kube/pv/provisioner.go:157-168`), exposed through
  VolumeSnapshot/dataSourceRef.
- New in P3, additive only: a per-datastore CSI StorageClass
  `rediacc-csi-<ds>` (provisioner `csi.rediacc.io`). The static
  `rediacc-ds-<ds>` class and its PVs remain valid indefinitely; repos opt into
  dynamic provisioning by declaring the CSI class. No re-format, no data move.

---

## 3. Fork PKI regeneration + secret scrub + ROLE rewrite (F1/F2)

### Reality baseline (verified in code)

`RewriteIdentity` today applies the SAME reset for fork and migrate: it keeps the
CA and only drops the leaf serving cert
(`pkg/kube/distro/identity.go:99-107` calling `ResetServingCert`,
`pkg/kube/distro/reset.go:27-39`, which removes only
`serving-kube-apiserver.{crt,key}` and `dynamic-cert.json` from
`<data-dir>/server/tls` and explicitly keeps `server-ca`/`client-ca`). The fork
case (`NewNetworkID != 0`, `identity.go:81-83`) therefore carries the parent's CA
private key and SA signing key: the F1 blocker, confirmed. The k3s data-dir is
`<mount>/.rediacc/k3s/data` (`k3s.go:75-77`), so the tls dir is
`<mount>/.rediacc/k3s/data/server/tls`.

### The split contract

`IdentityRewriteOpts` gains an explicit operation discriminator [P0-DECIDED]:

```go
type IdentityOp string
const (
    IdentityOpMigrate IdentityOp = "migrate" // same principal: CA preserved
    IdentityOpFork    IdentityOp = "fork"    // new principal: full PKI regen + scrub
)
// plus Role string on the fork arm: "fork" | "rehearsal" (ROLE ConfigMap value)
```

Inferring fork-ness from `NewNetworkID != 0` (the current implicit signal) is
rejected: an in-place re-identity with a networkID change must not silently trigger
a secret scrub. The caller states intent; contract tests assert the pairing.

### MIGRATE path (unchanged seam, restated)

1. `ResetServingCert(dataDir)`: leaf + dynamic-cert cache only, CA kept
   (`reset.go:27-39`).
2. Kubeconfig URL rewrite (`reset.go:45-62`), recompose unit, start
   (`identity.go:135-161`).
3. Agents rejoin with the SAME CA-derived token (`GetJoinToken`, `k3s.go:310-321`,
   reads `<data-dir>/server/node-token`).
4. Secrets stay (same principal, 02 §4). ROLE ConfigMap: `REDIACC_ROLE` stays
   `primary`; `REDIACC_DATASTORE`/`REDIACC_WRITES` rewritten if the attach changed
   them.

### FORK path — the VERIFIED 8-step procedure (spike d, fingerprint-proven)

Rewritten to the scope spike d proved (`reports/spikes/spike-d-pki-remint.md`).
**The decisive finding: removing `server/tls/` ALONE is a TRAP.** k3s keeps an
encrypted CA/SA-key bundle as a kine row (`/bootstrap/<hash>` in
`server/db/state.db`), decryptable with the server token, and RESTORES the parent
CA byte-identical from it on the next boot (spike d §2: server-ca SHA-256
`2F:39:84:…:1F:5F` identical before and after; same SA pubkey `3ffeb4…`). A fork
built with tls-removal-only silently ships the parent's CA and SA signing key,
voiding F1 while appearing to work. The full scrub below produced a genuinely new
PKI (spike d §3: server-ca `2A:6B:48:…:CF:4E`, SA pubkey `3ffeb4…` → `eb0f9b…`,
client-ca `90:13:AB…` → `EF:01:79…`) with the whole kine payload (pre-existing
Secret, workloads, PV objects) intact and serving.

Preconditions: the clone/reflink is placed and attached; k3s for this image is NOT
running (`PrepFork` drained, stopped, and swept nested mounts,
`prepfork.go:29-57`); the caller passed `IdentityOpFork` + target role
(`fork`|`rehearsal`) + `--writes` disposition. Data-dir is
`<mount>/.rediacc/k3s/data` (verified live in spike d:
`/mnt/rediacc/mounts/spike0/.rediacc/k3s/data`).

F1. **Remove `server/tls/`** (CA pairs, SA signing key `service.key`,
   request-header CA, all leaves, dynamic-cert cache). REQUIRED but proven
   insufficient alone (spike d §2). `server/cred/*.kubeconfig` need no manual
   action: they regenerate from the new CA on boot (spike d scrub-scope item 4),
   but must never be shipped as fork identity.

F2. **Delete the kine `/bootstrap/<hash>` row** from `server/db/state.db` (sqlite,
   while k3s is stopped). This is the self-restore path that reproduced the parent
   CA; k3s writes a FRESH `/bootstrap` row keyed to the new token on the clean
   boot (spike d §3). The rest of the kine DB is UNTOUCHED: workloads, PV
   objects, ConfigMaps ride through; that is the anchor model's whole point.

F3. **Rotate `server/token`** (delete; `node-token`/`agent-token` are symlinks to
   it, spike d §0; k3s mints a fresh one on boot). The token is the `/bootstrap`
   decryption key AND the parent's join credential: deleting the row (F2) or
   rotating the token each independently forces a re-mint, and BOTH are done
   (belt-and-suspenders), because the parent join token must change on fork
   regardless so old agents/forks can never rejoin across the principal boundary.

F4. **Wipe agent-side cached client identity**: `data/agent/` caches
   `client-*.crt/key`, `server-ca.crt`, `serving-kubelet.*`, `*.kubeconfig` signed
   by the parent CA (spike d §5: a stale agent spams
   `x509: certificate signed by unknown authority` until wiped + restarted with
   the new token). Under this design agents REJOIN FRESH anyway (04 §2), so this
   is "agents are disposable" made explicit; the wipe applies to any in-place
   agent, including the CP node's own agent side.

   Then **boot under the new identity**: existing recompose flow
   (`identity.go:135-161`) with `--tls-san <newIP>`; gate on `Healthcheck`
   (`k3s.go:401-410`, /readyz); read the NEW join token (`GetJoinToken`,
   `k3s.go:310-321`), which embeds the new CA hash. Positive isolation is proven
   both directions (spike d §4-5): old kubeconfig rejected (x509), old parent
   admin cert rejected at HTTP 401, new ones work; agent rejoined on the new
   token and ran pods.

F5. **Rewrite the `extension-apiserver-authentication` ConfigMap** (kube-system):
   after re-mint its `client-ca-file` bundle contained BOTH the old and new
   client CAs (spike d §6, stale-trust leak). The main apiserver's on-disk
   `--client-ca-file` is only the new CA (the 401 above proves the primary API is
   safe), but an aggregated/extension apiserver reading this ConfigMap for
   delegated client-cert authn would still trust the parent CA. Drop the parent
   cert from the bundle. (The front-proxy `requestheader` CA re-mints cleanly;
   metrics-server kept working, spike d §6.)

F6. **Secret scrub** (embedded kubectl against the fork CP, before any agent joins
   and before any `up()`):
   1. `kubectl delete secrets -A -l rediacc.io/injected=true`
      (all rediacc-materialized Secrets, enumerable by the §1f label).
   2. Default scrub-all third-party (02 §4): for every namespace labeled
      `rediacc.io/repo-namespace=true`: `kubectl delete secrets -n <ns> --all`
      (operator-created material: cert-manager keys, generated DB passwords;
      includes Helm's `helm.sh/release.v1` state Secrets, which orphans
      helm-deployed objects from `helm` tooling on the fork: accepted, renet's
      deploy path is manifests via `up()`).
   3. Legacy SA-token sweep, cluster-wide:
      `kubectl delete secrets -A --field-selector type=kubernetes.io/service-account-token`.
      Spike d §0 verified modern k3s creates NONE (bound/projected tokens only),
      so this is empty on fresh clusters but still runs: forks of older/populated
      clusters can carry them, and they are signed by the deleted SA key.
   4. Escape hatch `cluster fork --keep-third-party-secrets` skips step 2 ONLY
      (steps 1 and 3 always run); documented as consciously re-opening F2 for
      the fork operator's own namespaces.

F7. **Restart ALL pods — REQUIRED, not incidental** (spike d §6): the SA signing
   key change invalidates every already-projected bound SA token. Observed:
   coredns wedged at 0/1 (`plugin/ready: Plugins not ready: "kubernetes"`, its
   cached token rejected) and recovered only on recreation. A fork that does not
   recreate pods boots with broken SA auth until each pod happens to cycle, so
   the procedure deletes pods cluster-wide (controllers recreate them with fresh
   tokens signed by the new key; new SAs mint working tokens, verified).

F8. **ROLE ConfigMap rewrite** in every repo namespace:
   `REDIACC_ROLE=fork|rehearsal` (per caller), `REDIACC_WRITES=<attach --writes>`,
   `REDIACC_DATASTORE=<new ds name>` — else the fork boots claiming
   `role=primary` (02 §4). Rewritten, never deleted, so `envFrom` consumers keep
   resolving. Plus **stale Node cleanup**: delete every Node object except the
   rewritten server's (agents rejoin fresh, 04 §2 step 5; kine carried the
   parent's Node list).

Ordering rationale: F1-F3 happen while k3s is stopped (F2 requires it); F5-F6 must
complete before agents join and before any `up()`, so no pod ever starts on the
fork with a parent secret mounted; running them immediately after the /readyz gate
gives the narrowest window, and pods cannot schedule anyway until agents exist.
F7 runs after agents join (pods need somewhere to land).

### Contract-test invariants (RepoRuntime suite, 02 §9)

- fork: CA fingerprint differs from parent (the spike d proof style: compare
  server-ca SHA-256 before/after); SA pubkey differs; zero Secrets with
  `rediacc.io/injected=true`; zero Secrets of type
  `kubernetes.io/service-account-token`; zero third-party Secrets in repo
  namespaces (unless keep flag); `extension-apiserver-authentication`
  `client-ca-file` contains ONLY the new client CA; parent node-token and
  parent-CA client certs REJECTED by the fork apiserver (x509 / 401);
  `REDIACC_ROLE != primary`.
- migrate: CA fingerprint equal; Secrets present and equal; `REDIACC_ROLE=primary`.

### Spike d disposition (was the blocking cross-reference; now RESOLVED)

Spike d PASSED with the correction folded in above: items 1, 2, 4, 5 of the
original verification list are answered in the transcript (re-mint works against a
live kine DB; the bootstrap hazard was REAL and is now F2; no legacy SA-token
Secrets on modern k3s; positive isolation proven both ways). One residual for P1:
the `--secrets-encryption` interaction was NOT exercised (the spike cluster ran
without it); since this design scrubs Secrets from config-sourced material anyway,
enabling k3s secrets-encryption stays a documented follow-up experiment, not a v1
default.

---

## 4. Codified failover sequence (F3)

Implementable procedure for `datastore failover` (also the tail of `cluster
migrate` in-Ceph and of node-loss recovery). Steps are load-bearing and ordered
(02 §3); each verifies completion before the next (no lazy-success, 03 hygiene
rule 2).

```
 0. PLANNED move only: per-repo down() on the old node (or full node drain);
    node FAILURE: skip to 1.
 1. FENCE the old node: RBD exclusive-lock break + osd blocklist of the old
    client. (--writes local forks: no fencing, nothing on Ceph to protect.)
 2. DELETE the stale Node object(s) for the old mounter:
    kubectl delete node <old>. This is the StatefulSet force-release: STS pods
    stay Terminating FOREVER until the Node object goes away (the controller
    deliberately never force-deletes). Fencing in step 1 is what makes this safe.
 3. REMOVE the label rediacc.io/ds-<ds> from the old Node BEFORE any add
    (only applicable if the old Node object survives, i.e. the node itself is
    staying in the cluster and only the datastore moves; after step 2's delete
    this is a no-op). Rule: at no instant may two nodes carry the label
    (a double-label window schedules pods onto a node with no mounted path).
 4. DETACH on the old node if reachable (btrfs unmount, LUKS closes, loop
    detach, RBD unmap, lock release), verifying each step; unreachable nodes
    were fenced in 1 and detach happens implicitly by blocklist.
 5. ATTACH on the new node: RBD map, BTRFS mount at the SAME
    /mnt/rediacc-ds/<ds> path (mount-path stability, 04 §6, under the R1 sibling
    scheme; attach REFUSES
    mount-path name collisions), open per-volume LUKS images, mount volume
    filesystems under <ds-mount>/mounts/volumes/..., start per-repo registry
    units (§5), preflight k3s version skew (§7).
 6. ADD the label rediacc.io/ds-<ds>=true on the new node. Pods reschedule:
    volume-claiming pods pin here via WFFC + PV nodeAffinity; kube-scheduler
    latency (not storage) dominates from this point, stated honestly.
 7. Health gate: per-repo readiness + optional Rediaccfile health() (§6).
```

k3s-stop trap, now VERIFIED (spike d, "Validation of the k3s-stop trap"): stopping
`rediacc-k3s-<id>.service` does NOT stop pods; containerd-shims and workload
processes keep running. Step 0's per-repo `down()`/drain (and the 02 §3 node
shutdown unit) are therefore load-bearing: a sequence that only stops the k3s unit
would unmount volumes under still-running pods.

### tolerationSeconds default [P0-DECIDED: 60]

Renet's manifest render stamps these tolerations into every pod template that does
not already declare its own for the same keys (author override wins):

```yaml
tolerations:
  - key: node.kubernetes.io/not-ready
    operator: Exists
    effect: NoExecute
    tolerationSeconds: 60
  - key: node.kubernetes.io/unreachable
    operator: Exists
    effect: NoExecute
    tolerationSeconds: 60
```

Justification: the codified sequence does NOT depend on taint eviction (step 2's
Node delete is the force-release), so this default only governs the unattended
window before failover runs. 60 s is chosen over the k8s default 300 s because the
only pods that can usefully reschedule early are stateless ones (volume-claiming
pods just go Pending until step 6, which is harmless and more honest than
Terminating), and over aggressive values (5-15 s) because it clears one
node-monitor grace period (40 s) plus margin, so a k3s single-binary restart or
upgrade bounce never triggers a spurious cluster-wide eviction. Not configurable
per-flag in v1; authors who need different behavior declare their own tolerations,
which the stamp respects.

---

## 5. Datastore-backed registry for built images (F4)

### Decision [P0-DECIDED]: per-repo zot instance, host-side systemd unit

- **Binary**: the already-embedded zot (`pkg/embed` asset; extract/config/unit
  render machinery exists and is golden-tested, `pkg/kube/registry/zot.go`). A
  second embedded binary (`registry:2`) would add supply-chain surface for zero
  capability: the full zot build is a complete push-capable OCI distribution-spec
  registry, not just a pull-through cache.
- **Topology**: one zot process per repo that opts into local builds, run as
  `rediacc-registry-<networkID>.service` on the datastore's current mounter node
  (unit-per-networkID mirrors the per-repo dockerd and k3s unit patterns). It is a
  SEPARATE instance from the machine-level `rediacc-zot` pull-through cache
  (`zot.go:43`), which keeps its role: upstream mirror, sync-enabled; the per-repo
  instance has sync DISABLED (it is an origin, not a cache).
- **Backing store**: `storage.rootDirectory = <ds-mount>/repos/<repo>/registry/`
  (§2). Consequences by construction: images ride every repo fork (reflink of the
  repo folder), every cluster fork (group snap includes the datastore), every
  migrate/push (the folder is the transfer unit), and repo delete reclaims them.
- **In-cluster registry pod REJECTED**: manifests ban NodePort/LoadBalancer and
  hostPort outright (`pkg/kube/manifest.go:104-131`), so a registry pod has no
  node-reachable endpoint for containerd (which pulls from the HOST netns), and it
  would put a chicken-and-egg on fork boot (pods need images before the registry
  pod runs). A host unit renet starts at attach has neither problem.
- **ctr-import REJECTED** (04 §7b, restated): agent containerd stores are
  disposable cache, never forked or transferred; a fork boots fresh agents and
  every locally built image would ImagePullBackOff. Import also has no dedup/GC
  and no multi-node story.

### Naming, port, and reference scheme

- Port: allocated at repo create from the reserved range **21000-28999**, recorded
  in the repo's v3 `state.repos` record next to `networkId` (field added by spec 04
  per gate gap G3) and mirrored in the machine state bucket; attach collision-checks
  per machine. Deterministic-then-recorded, like networkId itself. The
  `REDIACC_REGISTRY`/`REDIACC_REGISTRY_HOST` pair joins spec 02's env contract (G3).
- Push endpoint (build side): `<node-ip>:<port>` where node-ip is the datastore
  mounter's IP. Injected into Rediaccfile `up()` env as:
  - `REDIACC_REGISTRY=<node-ip>:<port>` (push target)
  - `REDIACC_REGISTRY_HOST=registry.<repo>.rediacc.internal` (logical pull host)
- Pull reference (manifest side): images are referenced as
  `registry.<repo>.rediacc.internal/<image>:<tag>`. The logical host is NEVER
  resolved by DNS; renet wires it per node as a containerd mirror:
  - `/etc/rancher/k3s/registries.yaml` entry mapping the logical host to
    `http://<node-ip>:<port>` (survives k3s restarts; k3s regenerates containerd
    config from it at start, `pkg/kube/registry/wiring.go:77-100`), AND
  - a direct `hosts.toml` in k3s's generated certs.d for immediate effect without
    a k3s restart (containerd re-reads hosts.toml per pull). P1 verification note:
    confirm k3s 1.36's generated certs.d dir tolerates renet-written entries
    between restarts; if not, failover falls back to registries.yaml + the k3s
    restart that the moved CP performs anyway, and agent pulls of already-running
    pods are unaffected.
- The indirection is the failover story: image references stored in kine stay
  stable forever; only the per-node mirror endpoint is rewritten when the
  datastore (and its registry unit) moves (§4 step 5).

### `repo up()` build+push flow

```
up() {
  docker build -t "$REDIACC_REGISTRY/app:$TAG" .     # machine-level builder
  docker push  "$REDIACC_REGISTRY/app:$TAG"          # lands in repos/<repo>/registry/
  renet kube -- apply -f manifest.yaml               # manifest says
}                                                    #   registry.<repo>.rediacc.internal/app:$TAG
```

Path identity across the two names: containerd's mirror rewrite preserves the
repository path (`/v2/app/...`), so a push to `<ip:port>/app:tag` and a pull of
`registry.<repo>.rediacc.internal/app:tag` address the same blob store entry.
`repo up` warns when a manifest references the logical host but the repo has no
registry unit configured (typo guard).

---

## 6. health() contract [P0-DECIDED: dedicated Rediaccfile health() function]

Decision: an optional Rediaccfile `health()` function; the `info()` exit-code
convention is REJECTED. Rationale: `info()` is a display hook invoked by status
paths; overloading its exit code makes every status render a health probe (a
formatting failure would read as "unhealthy") and forbids health checks from being
slower or more invasive than a status line. A dedicated function mirrors
`up()/down()` naming, is independently timeout-able, and its ABSENCE is cleanly
detectable.

Exit semantics:

| Exit | Meaning | Gate behavior |
|---|---|---|
| 0 | healthy | pass |
| 42 | RESERVED: renet's function-not-defined sentinel (`pkg/orchestration/rediaccfile.go:213-220`, `ErrFunctionNotDefined`) | treated as "health() undefined": fall back to the runtime-readiness layer, report Unknown. A user health() must NEVER return 42 |
| 75 | warming up (EX_TEMPFAIL) | retry until the gate window expires |
| any other nonzero | unhealthy | fail the gate immediately (rollback window stays open) |

Gate-review reconciliation (C5): the retry LOOP lives in the gate caller (the
cluster/migrate layer); `RepoRuntime.Health` is ONE evaluation whose report carries a
"warming" disposition (Go shape owned by spec 02). Hook exit codes (42, 75) never
propagate to the CLI surface; a failed gate maps to CLI exit 13 (spec 03 §1).

- Per-attempt timeout 30 s (timeout counts as exit 75, one retry consumed); gate
  window default 300 s; both overridable per operation
  (`cluster migrate --health-window`, etc.), exact flags owned by the CLI spec.
- Env: `health()` runs with the same injected env as `up()/down()`, including
  `REDIACC_ROLE/WRITES/DATASTORE` (§1e) and the `REDIACC_REPOSITORY/NETWORK_ID/...`
  set from `pkg/orchestration/up_down_workflows.go:211-216`.

Layering (04 §4), evaluated in order, each gate for the next:

1. **Distro healthcheck**: CP /readyz (`k3s.go:401-410`), cluster-level, runs once.
2. **k8s readiness**: per repo namespace, all workload rollouts complete and pods
   Ready (`kubectl rollout status` per Deployment/StatefulSet + pod Ready
   condition). This is the DEFAULT health gate when `health()` is absent; docker
   repos' default is container running+healthy status, the RepoRuntime contract
   states both.
3. **Rediaccfile `health()`** when defined: application semantics (can the app
   actually serve a query). Runs on the machine like `up()`, so it can reach the
   proxy URL or the repo's services directly.

---

## 7. k3s version-skew metadata (F14)

- **Record**: `<ds-mount>/.rediacc/datastore.json` (the datastore metadata file
  the P1 named-datastore registry introduces; field owned here) gains:

  ```json
  {
    "name": "<ds>",
    "backend": "ceph",
    "cluster": "<cluster-name>",
    "writes": "",
    "k3sVersion": "1.36.2+k3s1",
    "k3sVersionWrittenAt": "<RFC3339>"
  }
  ```

  Field set is the C6 merge (this file's location `<ds-mount>/.rediacc/datastore.json`
  won; spec 02's content list rode in): `name`/`backend` identify the datastore,
  `cluster` is the optional one-world backref (runtime derivation, C7), `writes` is
  the fork-attach disposition (empty on plain attach, C12), plus the k3s skew pair
  below.

  Written at cluster install and at every successful CP start/upgrade from
  `embed.AssetK3sVersion` (`pkg/embed/embed.go:39-43`); the per-install
  `distro.json` already records `Version` per mount (`distro.go:105-116`), which
  stays the per-image truth; the datastore-level copy exists so ATTACH can
  preflight without mounting/booting anything. Mirrored into the config `state`
  bucket (02 §11.1) so the CLI can warn before SSH; the machine-side file is
  authoritative (state = routing hint contract).
- **Attach preflight rule [P0-DECIDED]**: comparing the attaching renet's embedded
  k3s version E against the recorded writer version R (minor-level):
  - E == R: attach.
  - E == R+1 minor: attach, log "kine will migrate forward on first boot"; on
    successful CP start the record is bumped to E (one-way ratchet).
  - E < R: REFUSE ("this datastore was written by k3s <R>; this renet embeds
    <E>; kine/cert state does not migrate backwards, use a renet release
    embedding k3s >= <R>").
  - E > R+1: REFUSE with the stepping instruction (upgrade through intermediate
    renet releases; apiserver/kine minor hops must not be skipped).
- **Upgrade flow note** (02 §10b): upgrade = replace the CP binary in place
  (renet `Upgrade`, `k3s.go:355-367`, embedded version only) and restart; kine
  migrates forward; then agents (which just re-extract the same shared binary,
  `k3s.go:27`). `cluster rehearse` before the upgrade is the canonical rehearsal
  use: fork the cluster, run the NEW renet's attach+boot against the fork,
  health-gate, discard.

---

## 8. Spike c: `repo secret` current surface (code survey)

This is the docker-world model that §1f extends to k8s. Everything below is
verified against the current tree with file:line.

### Storage (CLI config)

- Shape: `RepositoryConfig.secrets: Record<KEY, {mode, value}>` inside the flat
  config JSON. Schema: `packages/shared/src/config-schema/schemas.ts:145-170`
  (`SecretEntrySchema`: `mode: 'env'|'file'`, value 1 byte..10 MiB;
  `SecretKeySchema`: `/^[A-Z][A-Z0-9_]*$/`, max 64 chars, UPPER_SNAKE_CASE).
  Duplicate schema in `packages/cli/src/utils/config-schema.ts:63-83`.
- Store primitives: `packages/cli/src/services/repo/repo-secrets-store.ts`
  (read :22, list-keys-and-modes-never-values :30, write :40, delete :53).

### Write-only ceremony (command surface)

- `packages/cli/src/commands/repo-secret.ts`: `set`/`unset`/`list`/`get`.
  `get` returns `{key, mode, digest}` only, plaintext is NEVER returned to human
  or agent (:140-152). Overwrite/unset requires `--current <old-value>` matching
  via digest precondition, or `--rotate-secret` to skip (audited as
  `rotate_no_knowledge`), both enforced through the shared mutation gate
  (`runMutationGate` :183-218, `evaluateMutations` from
  `services/core/mutation-gate.js`). `--value -` reads stdin (:81-89). Every
  mutation emits a hash-chained audit event (:47-54). No `grandGuard`: with
  write-only there is no read attack to gate (:15-17).

### Injection at up() (docker runtime), by mode

- **env mode**: resolved CLI-side per focal repo and prefixed
  `REDIACC_SECRET_<KEY>` onto the remote renet invocation's shell env
  (`packages/cli/src/services/executor/local-executor.ts:1133-1149`); compose
  files consume via `${REDIACC_SECRET_KEY}` interpolation.
- **file mode**: never touches the shell (no `ps` leak). Values ride the vault
  stdin payload (`local-executor.ts:194-208` extracts file-mode entries into
  `LoadedRepoEntry.secretFiles`; wire shape
  `pkg/functions/context_parser.go:66-81` `RepositoryInfo.SecretFiles`), then
  renet's `repository_up` command builder emits `--secret-file NAME=<base64>`
  tokens (`pkg/functions/commands/repository.go:14-24, 1077-1081`), and the
  orchestration layer materializes each as a tmpfs file
  `/var/run/rediacc/secrets/<networkID>/<KEY>` (0444 files under a 0700 dir,
  atomic temp+rename, clean re-write on every up:
  `pkg/orchestration/secret_files.go:19, 40-42, 68-112`). Compose `secrets:`
  blocks must source from exactly that per-network dir; the compose validator
  rejects anything else, including other repos' network dirs
  (`pkg/compose/validate.go:44, 360-462`). Landlock scopes the sandbox so a repo
  cannot read a sibling's secrets dir
  (`pkg/orchestration/up_down_workflows.go:421-426`). Teardown purges the dir on
  `down --unmount` / delete (`secret_files.go:117-123`); tmpfs means nothing
  persists a reboot.
- Defense-in-depth name check renet-side mirrors the CLI schema
  (`secret_files.go:24` `^[A-Z][A-Z0-9_]{0,63}$`).

### Fork-empty enforcement point

- `registerFork` constructs the fork's config record field-by-field and simply
  never copies `secrets` (`packages/cli/src/commands/repo-fork.ts:152-180`; the
  invariant is documented at `schemas.ts:153` and `repo-secret.ts:17`). Note it
  DOES copy `credential` (:173), which is why §2's LUKS keying note is honest
  about data-at-rest vs secret-map separation.
- Host-side reinforcement: secrets live only on tmpfs outside the LUKS image, so
  a reflink fork of the image cannot inherit them physically
  (`secret_files.go:11-15`).

### What §1f/§3 take from this survey

1. The k8s materialization slots in exactly where `WriteSecretFiles` sits for
   docker: an `InjectSecrets` step of the RepoRuntime contract, executed inside
   `up()` before workload apply; Kube implementation = apply the two Secrets of
   §1f; Docker implementation = env prefix + tmpfs files (existing behavior).
2. Fork-empty is already enforced at the CONFIG layer; §3's scrub is the missing
   RUNTIME-layer half for k8s (kine carries materialized copies that the config
   layer never sees; docker's tmpfs never had this problem).
3. The UPPER_SNAKE key convention and the env|file split carry over 1:1
   (§1f consumption conventions); the 10 MiB value cap must shrink (§1f).
4. Example 13 (secrets example) should demonstrate: set env + file secret,
   deploy, verify pod sees `REDIACC_SECRET_<KEY>` and `/run/secrets/<KEY>`, fork,
   verify BOTH are gone and ROLE=fork, migrate, verify both survive.

---

## 9. Reality deltas (current code vs this spec)

| # | Current code | This spec | Disposition |
|---|---|---|---|
| 1 | Fork identity rewrite preserves the CA (only leaf reset), `identity.go:99-107` + `reset.go:27-39` | Full `server/tls` removal + scrub on fork; leaf-only reset becomes migrate-only | The F1 blocker fix, §3 |
| 2 | Single shared StorageClass `rediacc-datastore` (`pv/provisioner.go:29`) | Per-datastore `rediacc-ds-<name>`, no-provisioner, WFFC | Delete ledger (02 §6) |
| 3 | hostPath PVs with claimRef (`deploy.go:33-52`) | `local` PVs + required nodeAffinity | Delete ledger |
| 4 | PV images at `{ds}/pv/<cluster>/<ns>/<pvc>.img`, mounts at `{ds}/pv-mounts/...` (`pv/provisioner.go:34-53`) | `repos/<repo>/volumes/<pvc>.img`, mounts at `mounts/volumes/<repo>/<pvc>` | §2 layout |
| 5 | PV images are plain ext4 files, no LUKS (`pv/provisioner.go:108-118`) | LUKS2 per volume, repo credential keyed | F8/05 §3, §2 |
| 6 | Manifests persisted at `{ds}/manifests/<cluster>/<ns>` (`deploy.go:15`) | `repos/<repo>/manifests/` (inside the fork unit) | §2 |
| 7 | No NetworkPolicy, no PSA labels, no VAP anywhere in `pkg/kube` (grep-verified) | §1a/1b/1.0 templates | NEW work, P1 |
| 8 | Render-time `lintSecurity` blocks hostNetwork/hostPort/NodePort/LB (`manifest.go:104-131`) but nothing enforces in-cluster | PSA baseline/restricted (verified sufficient, spike e) + VAP defense-in-depth §1b; lint gains hostPID/hostIPC to stay equivalent | P1 |
| 9 | zot = machine-level pull-through cache only (`registry/zot.go`) | second role: per-repo origin registry units (sync disabled) | §5, reuses renderers |
| 10 | `NamespaceDelete` ceph/RADOS teardown + `.rbd-backend.json` markers + `resolvePVBackend` (`namespace.go:33-83, 147-176`) | gone with the ceph-csi layer | Delete ledger (02 §6) |
| 11 | Secrets: 10 MiB per-value cap (`schemas.ts:155`) | 256 KiB value / 512 KiB per repo per mode | §1f, config v3 owner |
| 12 | No cluster/datastore-level k3s version record beyond per-mount `distro.json` (`distro.go:105-116`) | `datastore.json` k3sVersion + attach preflight | §7 |
| 13 | `IsFork` signaled by `--grand-guid` in the up flow (`pkg/functions/commands/repository.go:1073-1076`); no ROLE env | `REDIACC_ROLE/WRITES/DATASTORE` triple, env + ConfigMap | §1e generalizes it |

Coordination notes for the other P0 spec owners: §1f's size cap and the registry
port field land in config schema v3 (spec-configv3); §3's `IdentityOp`
discriminator and §4's sequence are renet package-design items (spec-renet); §6's
gate-window flags and `--keep-third-party-secrets` belong to the CLI contract
tables (spec-cli); §8 item 4 defines example 13's assertions (spec owner for 07).

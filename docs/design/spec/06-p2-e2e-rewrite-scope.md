# P2 e2e rewrite scope — kube suites 15/16/17

Status at end of P1 wave3b: the three kube e2e suites still reference the **deleted**
bridge surface (`kube_namespace_*`, `kube_pv_*`, `kube_deploy`, `renet kube apply
--ceph-pool`). They compile (the harness dispatches by string literal, not the
generated contract union) and the coverage gate is green, but **tsc/coverage green
does not mean runnable** — every one of these suites fails at runtime today because
the functions they call no longer exist. P2 must treat them as **red-until-rewritten**.

This document is the precise per-suite rewrite scope so the P2 cluster-layer work
(anchor+rejoin fork/migrate, health gate, node lifecycle) lands with runnable e2e
coverage. It is intentionally the *contract* for the rewrite, not the rewrite itself:
the datastore-cluster machinery the new proofs need (whole-cluster group-snap fork +
attach orchestration) is P2's deliverable, so writing the suite bodies now would be
speculative against an unbuilt surface.

## Surviving vs deleted surface (as of P1)

Deleted (do not reference): `kube_deploy`, `kube_namespace_create`,
`kube_namespace_delete`, `kube_namespace_fork`, `kube_pv_clone`, `kube_pv_delete`,
`kube_pv_provision`, `renet kube apply` (the `--ceph-pool` apply path),
`repository_takeover` (renamed).

Surviving / new (build the rewrites on these):
- Cluster lifecycle: `kube_install`, `kube_join`, `kube_join_token`, `kube_uninstall`,
  `kube_node_remove`, `kube_upgrade`, `kube_health`, `kube_kubeconfig` — unchanged.
- Node fork/migrate primitives (internal): `kube_identity_rewrite` (new params:
  `operation` fork|migrate, `mode` server|agent, `new_node_ip`, `new_network_id`,
  `role`, `writes`, `server_endpoint`, `token`), `kube_prep_fork`.
- Datastore (the new fork/attach subject): `datastore_create`, `datastore_attach`
  (params `name`, `writes` local|ceph, `force`, `no_auto`), `datastore_detach`
  (`name`, `discard`), `datastore_fork` (`parent`, `tag`, `cow_size`, `snapshot`,
  `group`), `datastore_snapshot_create|list|delete`.
- Runtime-generic repo lifecycle through the datastore dispatch: `repository_up`
  (kube arm now does ApplyIsolation → ProvisionVolumes → InjectSecrets → Deploy),
  `repository_down`, `repository_status`, `repository_health`, `repository_logs`,
  `repository_exec`, `repository_promote`.

## Harness gap to close first (P2)

`packages/e2e-tests/src/utils/bridge/methods/`:
- Add `DatastoreMethods.datastoreCreate/Attach/Detach/Fork/SnapshotCreate` (mirror
  the existing `datastore_*` method pattern; the bridge fns already exist).
- `RepositoryMethods` already gained `repositoryHealth/Logs/Exec/Promote` +
  `repositoryUp/Down/Status` in wave3b — reuse them for the kube arm (same function,
  the datastore placement selects the runtime).
- The `KubeMethods.kubeNamespace*/kubePv*/kubeDeploy` methods are now dead — delete
  them as part of the suite rewrites (nothing else calls them once 15/16/17 move off).

## Per-suite rewrite

### 15-k8s-repo.test.ts — single-node k8s repo (the deliverable-5 shape)
- **Proved (old model):** single-node k3s inside a datastore-backed repo image;
  dedicated non-loopback node IP; router annotation contract; PV-per-CoW-image;
  namespace fork (instant CoW, data divergence, parent unchanged).
- **New proof:** a cluster-attached datastore + a kube repo with a **declared
  volume** → `repository_up` through the new dispatch materializes namespace + PSA
  label + default-deny NetworkPolicy + hostPath/hostNet VAP + no-provisioner SC +
  bound local PV + Running pod + ROLE ConfigMap; a **declared secret** lands as a
  per-namespace Opaque Secret (wave3b transport). Fork = `repository_up` on a
  datastore fork (CoW), data diverges, parent untouched. This is exactly the
  deliverable-5 transcript shape (reports/p1-wave3b-vm.md) — promote it to a suite.
- **Needs:** the datastore-fork harness methods above; the F5 hazard guard
  (stock k3s ships `local-path` as the DEFAULT SC — the PVC MUST name the rediacc SC
  or it gets adopted by local-path).

### 16-k8s-ceph.test.ts → rename to 16-datastore-cluster.test.ts
- **Proved (old model):** `kube_namespace_create --ceph-pool` (ceph-csi + per-ns
  StorageClass + RADOS namespace); `kube_namespace_fork pv_backend=auto` (RBD images
  CoW-cloned into a new RADOS namespace, fork PVCs pre-bind RW, data diverges);
  leak-reporting namespace delete.
- **New subject (CONTRACT.md CT-01k/CT-02k):** a **cluster-attached datastore backed
  by a ceph group**. `datastore_fork` takes a GROUP snapshot (spike-a verified);
  `datastore_attach --writes ceph|local` attaches the fork's group-snap on the node;
  `repository_up` runs the kube repo on the fork. **Proof shape that must survive:**
  group-snap datastore fork + attach + the repo runs on the fork; parent data
  untouched; the fork's kine carries NO parent CA/secret material (CT-01k) and cannot
  auth against the parent CA (CT-02k). The `--writes` disposition (local vs ceph fork
  home) is the new axis to assert.
- **Needs:** P2 whole-datastore group-snap fork + attach orchestration; ceph topology
  (VM_CEPH_NODES); the datastore-fork harness methods.

### 17-multinode-cluster.test.ts — multi-node fork/migrate
- **Proved (old model):** 2-node k3s (server + agent on real NICs, flannel VXLAN);
  whole-cluster fork (drain+prep every node, CoW-reflink control-plane image first
  then agents, `kube_identity_rewrite` server-then-agents onto secondary IPs, kine
  diverges CoW-isolated); whole-cluster migrate (FIEMAP delta + identity rewrite,
  measured cutover). It already uses the SURVIVING `kube_install/kube_join/
  kube_identity_rewrite/kube_prep_fork` primitives for the fork/migrate mechanics —
  only its **repo/PV bring-up** rides the deleted `kube apply --ceph-pool` +
  `kube_namespace_*`.
- **New proof:** keep the multinode fork/migrate PROOF SHAPE (anchor+rejoin, the P2
  cluster-layer subject); replace the repo/PV bring-up with `repository_up`/`down`/
  `status` through the datastore dispatch and declared-volume manifests. The
  `kube_identity_rewrite operation=fork` PKI re-mint + secret scrub is the CT-01k/
  CT-04 half asserted here at cluster scope.
- **Needs:** the P2 anchor+rejoin cluster fork/migrate orchestrator; 2 workers + ceph;
  RAM budget (two k3s cannot co-tenant one host netns — S1 verdict 2 — so parent is
  stopped while the fork runs; the suite already encodes secondary-IP relocation).

## CLI cluster-arm latent references (separate, P2/P4)

Independent of the e2e suites, these CLI commands still string-dispatch deleted
bridge fns (vitest green because the executor is mocked; runtime-broken):
`repo-create-delete.ts` (`kube_namespace_create`/`kube_namespace_delete`),
`repo-fork.ts` (`kube_namespace_fork`), `datastore.ts` (`datastore_ceph_unfork`).
These are the OLD per-namespace kube model; the redesign routes kube repo lifecycle
through `repository_up`/`down` via the datastore dispatch. Rewiring them is
cluster-layer (P2) / CLI-reshape (P4) work, not a mechanical rename.

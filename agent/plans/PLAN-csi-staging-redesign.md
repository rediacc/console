# PLAN: CSI staging redesign (#87) proven against a real kubelet, then CSI on worker nodes through a control-plane signed certificate (#86)

Status: proposed -- converted from console#606 (operator picked this item 2026-11-16); awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: no-dep -- the #87 node-side redesign already landed as #98, so #86 waits on nothing; suite 15 is also in the Owns of PLAN-canary-on-clusters.md and PLAN-zot-manifest-list-commit.md (both proposed), and block_plan_concurrency serialises writers on that one file
Priority: P2 -- every dynamic CSI volume on a worker node stays Pending today, and the one fix that makes dynamic volumes reclaimable has no assertion that would catch it coming back
Concurrency: parallel -- renet csidriver/kube_csi files, one CLI service and two kube e2e suites; Owns decides overlaps
Owns: agent/plans/PLAN-csi-staging-redesign.md, packages/e2e-tests/tests/kube/15-k8s-repo.test.ts, packages/e2e-tests/tests/kube/17-multinode-cluster.test.ts, private/renet/pkg/kube/csidriver/pki.go, private/renet/pkg/kube/csidriver/pki_split_test.go (new), private/renet/pkg/kube/csidriver/install.go, private/renet/cmd/renet/kube_csi.go, private/renet/cmd/renet/kube_csi_worker_test.go (new), private/renet/pkg/functions/commands/kube.go, private/renet/pkg/functions/commands/kube_test.go, private/renet/pkg/i18n/locales/*.go, packages/shared/src/renet-contract/data/**, packages/cli/src/services/cluster/csi-worker-enable.ts (new), packages/cli/src/services/cluster/__tests__/csi-worker-enable.test.ts (new), packages/cli/src/commands/datastore.ts, packages/cli/src/i18n/locales/*/cli.json, docs/design/spec/09-csi-driver.md, docs/design/spec/12-carried-debt.md, docs/design/spec/13-wave2-ledger.md
Live-Proof: bench, hostinger -- the kube_csi verbs and csidriver PKI under private/renet are the renet surface (hostinger only), the regenerated renet contract under packages/shared/src is the account surface (bench only), and the attach orchestration under packages/cli/src is the cli surface, which both admit.
Source: https://github.com/rediacc/console/issues/606

## Ask

Two carried items from the Kubernetes program, sequenced by a standing ruling: #87 (every dynamically provisioned CSI volume leaked its LUKS image because kubelet refused to unstage it) and #86 (CSI enablement on a worker node, which needs a sidecar credential only the control plane can issue). The ruling says #86 ships WITH or after #87's node-side redesign, never before, so CSI is not enabled on more nodes that would all leak.
Search first: no plan covers either item; `grep -rln '#87\|worker-node mint' agent/plans agent/plans/_done` finds only unrelated `#87` strings. The records are `docs/design/spec/12-carried-debt.md`, `docs/design/spec/09-csi-driver.md` and `docs/design/spec/13-wave2-ledger.md`.

## Context (checked 2026-11-16 against the tree)

1. #87's problem, as recorded: `docs/design/spec/12-carried-debt.md:9-15`. kubelet's `UnmountDevice` refuses `NodeUnstageVolume` while `GetDeviceMountRefs` sees a second mount of the staged device, and the driver's own canonical mount was that second reference, so the PV stayed `Released` and the image was never reclaimed (3 of 3 volumes leaked).
2. The node-side redesign has landed, under the number #98. `NodeStageVolume` (`private/renet/pkg/kubecsi/node.go:72`) mounts the LUKS device directly at kubelet's `staging_target_path` (`OpenAndMount`, `:105`) and makes the canonical path a symlink to it (`:108-123`, `os.Symlink` at `:119`); its comment (`:61-71`) records the suite-15 observation.
`NodeUnstageVolume` (`:130`) unmounts staging, tears the stack down, and removes the symlink. `DeleteVolume` refuses only while the volume is open (`private/renet/pkg/kubecsi/controller.go:268`) and then removes the image.
3. Spec 09 §5 already describes the as-built design and the reversal: `docs/design/spec/09-csi-driver.md:197-230` ("REVERSED by #98").
4. Three records are stale against the code. `docs/design/spec/12-carried-debt.md:7-21` still files #87 as EXIT-blocking and states the ruling as "option (a), (b) symlink REJECTED"; `docs/design/spec/13-wave2-ledger.md:64-66` still lists "#87 CSI staging redesign sequencing with #86" as deferred; the package comment `private/renet/pkg/kubecsi/driver.go:5` still says "stage = LUKS open + mount at the canonical path + bind".
5. No test asserts reclaim against a real kubelet. Suite 15's `csiCleanup` (`packages/e2e-tests/tests/kube/15-k8s-repo.test.ts:246-253`) deletes pods and PVCs with `--wait=true`, which waits for the PVC object only, not for the PV or the image. Test 10's no-leak check (`:818-819`) reads mounts under `<data>/repos/` only, and staging mounts live under the kubelet root, so it cannot see a leaked staged volume.
csi-sanity calls `NodeUnstageVolume` directly and cannot see the kubelet precondition (`docs/design/spec/12-carried-debt.md:15`, `:76-77`).
6. #86 today: `deployCSIForAttachedDatastore` (`private/renet/cmd/renet/kube_csi.go:93`) needs a local admin kubeconfig (`findLocalClusterK3sMount`, `:97`); on a worker it warns that attach succeeded but CSI was skipped and returns (`:98-109`, text ending "Attach itself succeeded."). The ledger's "attach now FAILS loudly" was corrected to warn-and-succeed (`docs/design/spec/12-carried-debt.md:49-52`), and that ruling stands.
7. The mint takes the target node already: `MintSidecarKubeconfig(ctx, r, node, cluster, apiServerURL, caPEM)` (`private/renet/pkg/kube/csidriver/pki.go:40`) mints `CN=rediacc-csi:<node>`, `O=rediacc:csi` through the CSR API, bound to the scoped `rediacc-csi` ClusterRole. It generates the private key and writes the kubeconfig on the host that runs it (`generateCSR` `:81`, `renderKubeconfig` and `os.WriteFile` at `:71-73`).
8. `DeployNode` (`private/renet/pkg/kube/csidriver/install.go:37-65`) does SC apply, mint and unit install in one call; `renet kube csi-node-up` (`private/renet/cmd/renet/kube_csi.go:488-547`) is its only verb and is hidden and node-local. No renet FunctionDef exposes it (`grep -rn csi private/renet/pkg/functions/commands` finds none).
9. The ruled #86 design (`docs/design/spec/12-carried-debt.md:79-91`): control-plane-mediated scoped mint; shipping the admin kubeconfig to workers is rejected. Spec 09 carries the same residual as §14 item 12 (`docs/design/spec/09-csi-driver.md:504`), and `docs/design/spec/12-carried-debt.md:57` lists it again as #79 (agent-node CSI).

## Design

**#87 needs proof, not code.** The redesign is in place (Context 2-3). What is missing is the assertion that would fail if a second mount reference came back: after a pod and PVC are deleted, the PV object is gone, the `.img` is gone from `repos/<ns>/volumes/`, the `rediacc-vol-<ns>-<vol>` mapper is closed and the canonical symlink is gone.
The test first asserts all four exist while the pod runs, so the "gone" assertions have something to lose. The stale records are corrected in the same wave. The `private/renet/pkg/kubecsi/driver.go:5` comment sits in the Owns of PLAN-datastore-migrate-correctness.md, so the lead hands that one-line fix to its writer.

**#86: the worker keeps its private key.** The ledger's design moved a minted kubeconfig, private key included, through the executor's secret channel. A CSR split is strictly better: the worker generates the key and the CSR, only the CSR (public) travels to the control plane, only the signed certificate (public) travels back, and the key never leaves the worker. Three renet FunctionDefs:
- `kube_csi_csr` (worker): generate the ECDSA key into `<KubeconfigDir>/<cluster>/key.pem` (0600), print the CSR PEM.
- `kube_csi_sign` (control): read the CSR on stdin, refuse any subject other than `CN=rediacc-csi:<node>`, `O=rediacc:csi` for the named node, apply the per-datastore StorageClass, stamp the node topology label, create and approve the CSR object, and print the certificate, the cluster CA and the API URL as one JSON line.
- `kube_csi_node_install` (worker): read that JSON on stdin, assemble the sidecar kubeconfig with the local key, and install the node units.

`MintSidecarKubeconfig` splits into `GenerateSidecarCSR`, `SignSidecarCSR` and `AssembleSidecarKubeconfig`; the control-plane path calls all three in-process, so the single-node behaviour is unchanged.

**CLI orchestration.** `csi-worker-enable.ts` runs the three hops after `datastore_attach` of a cluster-owned datastore on a node that is not the cluster's control node, and from `rdc datastore attach`. Renet's attach takes a `csi-by-client` flag from the CLI so the warning in Context 6 is not printed beside a success the next hop reports; direct renet use keeps the warning. A failed hop warns with the step name and leaves the attach in place (warn-and-succeed, per the standing ruling).

**Out of scope.** Ceph-backed worker datastores beyond what suite 17 already drives; the router-on-cluster split; seccomp (#84, dropped by the operator on 2026-11-16).

**Lab.** Suite 15 needs one K8S worker and suite 17 needs two workers plus a Ceph set. Machines 21-23 host a live Ceph cluster and machine 11 carries another agent's work at conversion time, so the live boxes run on a free fleet slot or wait for one, never on 21-23 while they host that cluster.

## Boxes

- [ ] S1 [writer] Suite 15: a `csiReclaimed(ns, pvc)` helper and an assertion in tests 7-9b's cleanup that, after pod and PVC deletion, the PV object, the `.img`, the mapper and the canonical symlink are all gone within 120s, each first asserted present while the pod ran. Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0
- [ ] S2 [writer] Correct the stale records: `12-carried-debt.md` #87 moves out of EXIT-blocking with a pointer to spec 09 §5 and #98; `13-wave2-ledger.md` item 11 points at this plan; spec 09 §14 item 12 points at the #86 boxes. Accept: `npm run check:ci-prose-style` rc 0
- [ ] W1 [writer] Split the mint in `pki.go` into `GenerateSidecarCSR`, `SignSidecarCSR` (subject check refuses any CN or O but the node's) and `AssembleSidecarKubeconfig`; `DeployNode` calls the three in-process. `pki_split_test.go` covers a wrong-CN CSR refused, a wrong-O CSR refused, and an assembled kubeconfig whose key matches the signed cert, with the fake Runner. Accept: `cd private/renet && go test ./pkg/kube/csidriver -count=1` rc 0
- [ ] W2 [writer] The three FunctionDefs `kube_csi_csr`, `kube_csi_sign`, `kube_csi_node_install` (registry, tier map, builder, i18n in all renet locales) and the `csi-by-client` attach flag, with `kube_csi_worker_test.go` driving csr then sign then install against fakes. Accept: `cd private/renet && go test ./cmd/renet -run TestKubeCSIWorker -count=1` rc 0, `npm run check:ci-renet` rc 0 and `npm run check:ci-renet-tiers` rc 0
- [ ] W3 [writer] Regenerate the renet contract (`private/renet/bin/renet functions generate-types --output packages/shared/src/renet-contract/data --version dev`) and keep only the three new functions' rows. Accept: `npm run check:ci-renet-types` rc 0 and `npm run check:ci-e2e-coverage` rc 0
- [ ] W4 [writer] `csi-worker-enable.ts` and its call from `rdc datastore attach` for a cluster datastore on a non-control node, with tests for the three-hop order, a sign refusal that leaves the attach in place with a warning naming the step, and the control node path that skips the hops. New strings in all 13 CLI locales. Accept: `cd packages/cli && npx vitest run src/services/cluster/__tests__/csi-worker-enable.test.ts` rc 0 and `npm run check:i18n` rc 0
- [ ] W5 [writer] Suite 17: a test that attaches a cluster-owned datastore on the agent node through the CLI path, then proves a dynamic PVC pinned to the agent binds and runs, the agent's sidecar kubeconfig carries `CN=rediacc-csi:<agent>`, no admin kubeconfig exists on the agent, and deleting the PVC reclaims the image (S1's helper). Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0
- [ ] V1 [live] Suite 15 with S1 on a free K8S worker. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --test tests/kube/15-k8s-repo.test.ts` rc 0 against an e2e env created with the k8s toggle (`K8S_MODE=1` in its .env), the suite not skipped, and the reclaim assertion's log lines quoted
- [ ] V2 [live] Suite 17 with W5 on two free workers and a Ceph set that is not the live cluster on 21-23. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --test tests/kube/17-multinode-cluster.test.ts` rc 0 against a k8s and Ceph e2e env, the suite not skipped
- [ ] V3 [live] VM tier before the live receipts. Accept: `npm run vm:check -- --changed` rc 0 with a VERIFIED receipt
- [ ] LP-bench [live] Fresh bench receipt for the regenerated renet contract under packages/shared.
  Accept: live-proof bench account-smoke
- [ ] LP-hostinger [live] Fresh hostinger receipt after V3 on the same tree.
  Accept: live-proof hostinger renet-live

## Risks

- `kube_csi_sign` is a signing oracle on the control plane: anything that can call it gets a scoped CSI credential. The subject check limits it to the CSI identity for one named node, the ClusterRole limits what that identity can do, and W2 gives the function the same tier as `datastore_attach`; W2's test asserts a CSR for another node name is refused.
- If S1 fails on V1, #98 did not fully close #87 (a mount reference survives somewhere other than the canonical path). That reopens the node-side model, and W1-W5 stop until it is understood, per the sequencing ruling.
- The live boxes wait on fleet capacity (Lab). The writer boxes do not, so the code lands and waits for one fleet window covering V1 and V2.

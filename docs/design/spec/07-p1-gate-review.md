# 07 — P1 Gate Review (renet storage core + config schema v3)

Reviewer: Fable gate agent, 2026-07-10 ~21:05. Fully-autonomous mode (this review
stands in for the user per the approved plan). Subject: the entire P1 phase against
`09-implementation-phases.md` §P1 and specs 01-05 as amended by the 00-gate-review
rulings. Evidence root: scratchpad `checkpoints/` + `reports/` (paths below are
relative to it unless absolute).

## VERDICT: **PASS-WITH-NOTES**

P1 is complete and proven. Every gate criterion is met with executed evidence, and
every top claim I could re-run cheaply I re-ran myself and confirmed green
(`check:ci-renet` exit 0, `go test ./...` exit 0, vitest 1424/1424, tsc 0 errors,
`gofmt -l` clean, e2e-coverage gate green, bridge contract types checked
symbol-by-symbol, HEADs unmoved). Nothing must be *fixed* before P2 starts. The
NOTES are: (1) the three kube e2e suites are **runtime-red-until-rewritten** —
deliberate, contractually scoped in spec 06, and P2 must treat them as red;
(2) three CLI cluster-arm commands string-dispatch deleted bridge functions
(runtime-latent, P2/P4); (3) a benign `package-lock.json` metadata drift and the
206-string i18n baseline grandfathering are recorded debt (housekeeping / P7).

## Per-criterion evidence table

| # | Criterion | Evidence | Verdict |
|---|---|---|---|
| 1 | RepoRuntime + contract tests: 20 docker + 15 kube CTs; spec 02 invariants | `reports/p1-reporuntime-tests.txt` (wave 1: 20/20 docker PASS, 15 kube SKIP-with-named-dependency, `TestNoStoragePackageImports` PASS = compile-level CT-10); `reports/p1-kuberuntime-tests.txt` lines 46-91 (wave 2: all 15 kube CTs PASS incl. CT14 dispositions). CT-01 fork⇒scrubbed secrets, CT-03 ROLE≠primary, CT-06 teardown leak-reporting all in both suites. CT-02k fingerprint-difference explicitly recorded as an e2e leg for `16-datastore-cluster.test.ts` (kuberuntime report line 50). Re-verified: `go test ./...` exit 0 fresh at review time. | **PASS** |
| 2 | Named datastore layer per spec 01 §3 | `reports/p1-datastore-vm.md` — full live transcript on rediacc12 (local) + rediacc21 (Ceph Squid 19.2.4): create/attach/detach/delete state machine, descriptor at `<mount>/.rediacc/datastore.json`, registry, **implicit default synthesized in `list`** (zero docker behavior change), fork+attach `--writes local` (dm-thin overlay, OVERLAY-RW-OK) and `--writes ceph` (fenced RW clone), **group snapshot across two RBD datastores + clone-from-group-snap via `rbd clone --snap-id` + clone-format-2**, live-clone snapshot-delete refusal observed, planted-orphan loop **auto-swept** (detach-before-unlink / no-lazy-success / inventory sweep), zero-residue teardown (HEALTH_OK). `--writes` contract enforced in code: `pkg/datastore/attach.go:114` refuses fork attach without `--writes`, `:66` refuses `--writes` on a plain datastore. Clone-format-2 pinned at provision: `pkg/infra/ceph/provisioner.go:172`. Bonus: 3 pre-existing ceph bugs found+fixed live (findRBDDevice sysfs, watcher-race retry, group-member rm ordering). | **PASS** |
| 3 | KubeRuntime per spec 05 | Templates verified in `pkg/reporuntime/kube_templates.go`: 3 NetworkPolicies incl. `rediacc-allow-proxy` with the **in-cluster leg only** (namespaceSelector+podSelector; zero `ipBlock` — spike-e ruling honored), VAP denying hostNetwork+hostPath (lines 130-141), ROLE ConfigMap trio, labeled Secrets `rediacc-env`/`rediacc-files` via STDIN with `rediacc.io/injected` label; caps enforced per gate ruling in `packages/cli/src/schema/schemas.ts:172-174` (32K env / 256K file / 512K aggregate). Ruled C1 volume layout live-proven: images `repos/<repo>/volumes/<pvc>.img`, mounts at `<ds>/mounts/volumes/<repo>/<pvc>/` — **no mountpoints inside the repo folder** (`reports/p1-wave3b-vm.md`). Per-volume LUKS live (973.7M honest df on the 1Gi volume). WFFC no-provisioner SC + local PV live (checks 4-6). | **PASS** |
| 4 | Delete ledger + check:ci-renet green + bridge diff | `checkpoints/phase-1-renet-status.txt`: `pkg/kube/csi/*`, `pkg/kube/pv/*`, `pkg/kube/namespace.go`, `ceph_backend.go`, `backend_ceph_fork.go`, `cmd/renet/kube_{csi,deploy,namespace,pv}.go`, `datastore_{fork,unfork}.go` all deleted. I checked `packages/shared/src/renet-contract/data` directly: `repository_{health,logs,exec,promote}` present; `kube_deploy`, `kube_namespace_{create,delete,fork}`, `kube_pv_{provision,clone,delete}`, `repository_takeover`, `datastore_ceph_{fork,unfork}` all **0 occurrences**. 81 functions total (matches wave3b claim). **Re-ran `npm run check:ci-renet` myself: exit 0** (fmt, lint 0, deadcode 9-all-allowlisted, security, i18n, hashes) — this also settles the 20:55 gofmt RED in `p1-wave3b-lint-final.txt` (fixed after capture). | **PASS** |
| 5 | Config v3 per spec 04 | `reports/p1-configv3-tests.txt`: **the RED run is captured verbatim** (16:12 UTC, `persist-unification.test.ts` T1 FAIL against v2 persist — ValidationError proving whole-file corruption via malformed encryption blob, a stronger finding than the specced record loss), then GREEN T1-T6 against v3 unified persist. Migration gate `check:ci-config-migrations` PASS (v1/v2/v3 fixtures round-trip); 10-transform v2→v3 with wrong-pw abort + collision/cap refusals. State bucket exclusion verified in code: `config-field-crypto.ts:152-162` strips `state` + `/state/*` pointers from the push view; `config-file-storage.ts:231/290` `updateState` = no version bump. Reconcile service + `verifyRoutingHint` exist with tests (`config-reconcile.ts`, `config-reconcile.test.ts`). tsc/vitest re-verified by me. | **PASS** |
| 6 | KVM collision fix live-verified | `reports/p1-kvmfix-live-verify.md`: group-named `rediacc-kvmfix-*` on renet12 with disks under `/tmp/rediacc-kvmfix/`, fleet networks/VMs byte-identical at baseline/mid/end; **preflight aborted the exact incident condition** ("domain rediacc-kvmfix-1 exists on renet12 but this run targets renet-preflight-probe" → exit 1, nothing created); teardown removed only group VMs + the group storage pool. Live-caught storage-pool define race fixed + re-validated (`p1-kvmfix-tests.txt` round 2). Wave3b's p1gate cluster then **used the fix in anger**: `rediacc-p1gate-{1,11,12}` created and destroyed with the fleet running throughout (`p1-wave3b-vm.md` baseline/create/destroy listings; corroborated by `p1gate-create.log`). Incident item CLOSED. | **PASS** |
| 7 | End-to-end k8s repo up through the NEW dispatch | `reports/p1-wave3b-vm.md`: cluster-attached datastore `p1ds` → `repository_up` dispatched ApplyIsolation → ProvisionVolumes → InjectSecrets → Deploy; **all 9 objects verified** (restricted-PSA namespace with contract labels, 3 netpols, VAP, `rediacc-ds-p1ds` WFFC SC, bound local PV, Running pod, ROLE ConfigMap trio, `rediacc-env` Secret) + `printenv APP_SECRET` **seen in the pod** + PV write + honest volume-stats; PSA correctly denied the first non-compliant pod (isolation working, not a workaround); first `repository_down` leak-REPORTED honestly (CT-06), teardown fix landed, re-run **converged clean** (CT-07, InventorySweep no residue). Two genuine bugs found+fixed live (Gi size unit; teardown volume unmap = detach-before-unlink at the kube seam). | **PASS** |
| 8 | Vitest 1424 / go test / no commits | Re-run by me at review time: vitest **102 files, 1424 tests PASS**; `go test ./...` exit 0; `npx tsc --noEmit` 0 errors. `git log -1`: console `583eae93d`, renet `2b13e9d` — **unchanged, no commits made**. Checkpoints `phase-1-{console,renet}.patch` + `phase-1-untracked.tar.gz` + status/untracked lists all present and consistent with the working tree. | **PASS** |

## Deviation rulings

| # | Deviation | Ruling |
|---|---|---|
| D1 | Spec 01 file-layout partially absorbed into `pkg/reporuntime`; runtime composes orchestration primitives rather than wrapping the Orchestrator god-object | **ACCEPTED.** The contract is behavioral, not structural; CT-10 plus the compile-level `TestNoStoragePackageImports` prove the storage/runtime seam the layout rule existed to protect. Documented in the reporuntime report as a spec refinement. |
| D2 | Legacy path-addressed cobra verbs kept as plumbing; `datastore_*` bridge fns `VisibilityInternal` | **ACCEPTED.** No e2e-coverage impact, no user surface committed prematurely; removal/renaming is P4's CLI-reshape mandate. Same ruling covers `repo-takeover.ts` keeping the CLI verb name while dispatching `repository_promote`. |
| D3 | i18n baseline grandfathering: 2583→2789 (206 P1 strings) via sanctioned `extract --update-baseline` | **ACCEPTED-WITH-DEBT.** baseline.json is git-tracked and reversible; proper keying is explicitly P7 scope. Condition: the baseline must not grow again in P2+ without a gate ruling — new strings get real keys. |
| D4 | E2E suite bodies (15, 16→16-datastore-cluster, 17) deferred to P2 with spec 06 as the contract | **ACCEPTED.** The new proofs require P2's whole-cluster group-snap fork/attach orchestration; writing bodies now would be speculative against an unbuilt surface. Spec 06 is honest ("tsc/coverage green does not mean runnable — red-until-rewritten") and precise per suite, and the plan's P2 gate already requires the rewritten multinode suite passing locally. Not a descope: the P1 bar (types regen + coverage gate + harness methods) was met, and the deliverable-5 transcript already proves the 15-suite shape live. |
| D5 | `package-lock.json` drift found during this review: 27 metadata-only changes (`"dev": true` dropped on `tsx`'s nested `@esbuild/*` optional platform entries; no versions added/removed, platform entries preserved) | **NOTED (housekeeping).** Benign locally; before any eventual push, either revert the hunk or validate with `npx -y npm@10 ci --dry-run` per the repo's lockfile policy. Not gate-blocking for a local-only program. |
| D6 | KubeRuntime drives kubectl via injected `toolexec.Executor` instead of `pkg/kube.Wrapper` | **ACCEPTED.** Wrapper is non-injectable and carries ceph fields the delete ledger removed; the choice is what made the CT suite runnable without root. |

## Contradiction hunt — findings

- `p1-wave3b-lint-final.txt` (20:55) shows a RED gofmt on `pkg/kubevolume/provisioner_test.go` while the wave3b summary claims final green. **Resolved in the work's favor**: my fresh `check:ci-renet` run is exit 0 and `gofmt -l` over the tree is clean — the capture predates the fix by minutes.
- The lockfile drift (D5) is the only working-tree change not attributable to a reported deliverable. All other console/renet status entries map to named P1 work.
- Wave3a's "check:ci-renet FULLY GREEN" claim, wave3b's re-confirmation, the 81-function count, the added/removed bridge symbols, and the "no commits" invariant were each independently re-verified rather than trusted. No claim failed verification.

## Authoritative P2 carry-in list (for the P2 brief)

1. **Datastore node-label at attach** (wave3b BUG #2): nothing labels the hosting
   node `rediacc.io/ds-<name>=true`, so local-PV pods stay Pending until a manual
   `kubectl label`. `datastore attach` on a cluster-attached datastore must apply
   (and detach must remove) the label — the codified remove-before-add relabel from
   the failover sequence is the natural home.
2. **Cluster-kubeconfig wiring for cluster-attached datastores** (wave3b GAP):
   `distro.DetectDistro` only auto-wires an embedded k3s (distro.json at the
   datastore mount); a system k3s from `cluster create` fell back to ambient
   kubectl/KUBECONFIG and needed a manual bridge. P2 must thread the cluster's
   kubeconfig into the dispatch (toolexec stdin+env combo noted by p1-kuberuntime).
3. **E2E suite rewrites per spec 06** (red-until-rewritten): 15-k8s-repo promotes
   the deliverable-5 transcript shape; 16-k8s-ceph → 16-datastore-cluster (group-snap
   fork + CT-01k/CT-02k kine/CA assertions); 17-multinode keeps the fork/migrate
   proof shape, swaps repo bring-up onto `repository_up/down/status`. Plus the
   harness gap: add `DatastoreMethods.datastoreCreate/Attach/Detach/Fork/Snapshot*`,
   delete the dead `KubeMethods.kubeNamespace*/kubePv*/kubeDeploy`.
4. **Cluster-scope fork PKI scrub F1-F7** (8-step scrub, spec 05 §7): P1 landed the
   ns-level F6/F8 halves; `kube_identity_rewrite operation=fork` currently REFUSES
   with a P2 pointer (F1-safe by construction). P2 implements the full scrub inside
   anchor+rejoin cluster fork.
5. **kvm memberIds → state.clusters** (configv3 handoff): cluster VM membership
   belongs in the v3 state bucket; the kvm provisioner still tracks it its old way.
6. **`--secrets-encryption` interaction** (spec 05 residual): k3s secrets-encryption
   flag vs the fork kine scrub is unexercised; verify during the P2 scrub work.
7. **CLI cluster-arm latent references** (P2/P4 split per spec 06 §last):
   `repo-create-delete.ts` (`kube_namespace_create/delete`), `repo-fork.ts`
   (`kube_namespace_fork`), `datastore.ts` (`datastore_ceph_unfork`) string-dispatch
   deleted bridge fns — vitest-green (mocked) but runtime-broken; rewire onto the
   datastore dispatch when P2 builds the cluster arms (final naming is P4).
8. **Live fencing race**: exclusive-lock break + osd-blocklist against a *live*
   second holder is unit-tested (mocked `rbd lock ls`) but never raced on real
   nodes — fold into P2's multinode suite where two nodes exist.
9. **Overlay-fill auto-grow wiring**: dm-thin ships queue-when-full + the
   storage-health hook point; the auto-grow reaction (spike-f recommendation) is
   unwired — P2/P3 alongside the reconcile timer generalization.

P4 reminders recorded here so they aren't lost: latest-magic resolver removal +
retired-stubbed ceph verbs; the flat composite-key config view bridging ~40 command
consumers; `repo-takeover` → promote rename at the CLI surface; D3's baseline
re-keying is P7.

## Checkpoint integrity

`checkpoints/phase-1-console.patch` (238K), `phase-1-renet.patch` (400K),
`phase-1-untracked.tar.gz` + `phase-1-untracked-list.txt`, and both status files
exist and match the live tree. The untracked list correctly captures the new
packages (`pkg/reporuntime/`, `pkg/kubevolume/`, `pkg/datastore/*` new files,
`config-field-crypto.ts`, `state-schema.ts`, `v2-to-v3.ts`, reconcile service).

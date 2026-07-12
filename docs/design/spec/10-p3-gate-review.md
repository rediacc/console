# P3 gate review (feature layer + thin CSI driver)

Reviewer: Fable (adversarial, evidence-first). Date: 2026-07-13.
Subject: the entire P3 phase against `docs/design/09-implementation-phases.md` §P3
and the nine P3 carry-ins in `docs/design/spec/08-p2-gate-review.md`.
Method: every gate re-run by the reviewer from a cold shell; every claimed fix
located in the working tree by file:line; every live claim traced to a transcript.
Nothing in this document is taken from a subordinate report's self-assessment.

HEADs at review: console `9eee3671b`, renet `c7e187a`. Both operator-authored,
therefore sanctioned (the "zero commits" invariant was superseded on 2026-07-11 by
an authorship-based invariant). No agent-authored commits exist. Verified via
`git log --format='%an'`.

---

## VERDICT: PASS-WITH-NOTES (conditional)

P3's hardest and highest-risk deliverable, the thin node-local CSI driver, is proven
live well beyond its bar. All nine P2 carry-ins are discharged or consciously
dispositioned, several of them exceeding what was asked. The full gate set is green
except for one pre-existing, previously-sanctioned red. The bug ledger is accurate,
and it self-corrected a bad generalization rather than defending it.

Two explicit conjuncts of the gate letter are nonetheless **unproven**, and I am not
willing to paper over either:

1. **The P3 feature layer has never been executed.** `repo replicate`, `cluster
   rehearse`, and the release ladder (rung 0 + canary weight templating) are real,
   complete, wired, unit-tested code. Not one of them has ever been run against live
   infrastructure. The gate letter reads "VM transcript **and** unit coverage per
   feature". Unit coverage: met. VM transcript: absent for three of P3's four named
   features.
2. **No stock Helm chart was ever installed.** The gate letter reads "a stock Helm
   chart with a dynamic PVC **and** a velero/VolumeSnapshot backup both work against
   the CSI driver". The VolumeSnapshot arm is proven emphatically. The word "helm"
   appears in zero live transcripts.

These are recorded below as **B1** and **B2**: blocking before program EXIT, not
blocking P4 (P4 is the CLI reshape, orthogonal to both, and is under an operator
hold in any case). They are cheap: both discharge inside one bounded live window.

I considered a clean PASS and rejected it. The single most important empirical result
of this phase is that **unit-green predicts nothing about live behavior in this
codebase**: the e2e leg found four feature-breaking product bugs (#23, #24, #26, #28)
that unit tests and two prior live campaigns all missed, and the CSI live window found
three more. Against that record, signing off three never-executed features on unit
coverage alone would contradict the phase's own central finding.

I also considered FAIL and rejected it. Every deliverable exists as real, wired,
unit-tested code (I verified this specifically, including hunting for stubs and for
the "exported function with zero callers" pattern that produced #26). The phase's
riskiest work is proven. FAIL would misrepresent the state of the tree.

---

## Gate set (re-run by the reviewer, 2026-07-13)

| Gate | Exit | Salient output |
|---|---|---|
| `npx tsc --noEmit --project packages/cli/tsconfig.json` | **0** | clean |
| `cd packages/cli && npx vitest run` | **0** | 109 test files, **1477 tests passed**, 0 failed |
| `npm run check:ci-renet` | **0** | green end to end (gofmt, golangci, i18n baseline grandfathered, type-gen reconciled) |
| `npm run lint:unused` (knip) | **0** | `--treat-config-hints-as-errors`, no unused exports/deps/config hints |
| `npm run check:ci-knip-blockers` | **0** | every knip suppression carries a valid BLOCKER |
| `npm run check:i18n` (repo root) | **1** | **RED. Pre-existing + sanctioned.** See below. |
| `cd private/renet && go build ./...` | **0** | |
| `cd private/renet && go vet ./...` | **0** | |
| `cd private/renet && go test ./...` | **0** | all packages ok |
| `go vet -tags "root ebpf_e2e" ./...` | **0** | tag-gated files compile (OPS CI parity) |
| `gofmt -l .` | clean | no unformatted files |

### The one red, root-caused

`check:i18n` exits 1 with **exactly** 12 locales x 58 untranslated strings (3.3%),
**all on the `cli/<lang>` surface** (`commands.cluster.create.controlDsSizeOption`,
`...controlDsBackendOption`, `...controlDsPoolOption`, and 55 more of the same class).
Zero missing keys. Zero www-surface failures. Zero non-CLI failures of any kind.

This is **precisely** the deferred class recorded in the program manifest ("check:i18n
58 CLI keys/locale un-naturalized, deferred to P7 because P4 reshapes the CLI, so
naturalizing now is throwaway"). The count is 58, unchanged: **the red did not grow
during P3.** It is pre-existing and sanctioned by standing ruling. P4 must not attempt
to clear it; P7 must.

Note for the record: my first attempt ran `check:i18n` from `packages/www`, where the
script does not exist, and the wrapper's exit code masked the failure. The script lives
at the repo root. Reviewers repeating this gate should run it from the root.

### i18n baseline integrity (renet)

Gate reference is **2970**, via the sanctioned chain
2870 -> 2877 -> 2952 -> 2961 -> 2969 -> 2970.

Verified arithmetically against the tree, not taken on trust:

- `private/renet/pkg/i18n/baseline.json` at committed HEAD `c7e187a`: **2726 raw entries**.
- Working tree: **2744 raw entries**. Delta = **+18**.
- The three post-commit sanctioned increments are +9 (rv1 migrate strings, #18/#19),
  +8 (CSI fold/fix strings), +1 (csi-live closure) = **+18**. Exact match.
- Raw-to-tool offset is a constant ~+226 (a known property of the counter), so raw 2744
  corresponds to tool-count **2970**, matching the gate reference exactly.

**No unsanctioned baseline growth occurred.** Every entry added during P3 traces to a
recorded ruling.

---

## Per-criterion evidence table (09 §P3)

| # | Gate criterion | Evidence I personally verified | Verdict |
|---|---|---|---|
| 1 | **`repo replicate`** (05 §1) | Real implementation, not a stub. `repo-replicate.ts` (388 lines) + `repo-replicate-ops.ts` (352 lines); the `dispatch` helper (`repo-replicate.ts:171`) wraps `localExecutorService.execute` and throws on failure; `provisionReplicaDatastores:80`, `provisionOneReplica:111` issue real snapshot/fork/attach calls (:87, :121, :128, :135); `discardReplicaDatastores:153` issues `datastore_detach`; replica sets persist to the config state bucket (`recordReplicaSet:188`). Command wired at `packages/cli/src/commands/repo-replicate.ts:61`. Unit coverage: 6 + 7 = **13 tests**. Zero TODO/stub markers. **VM transcript: NONE.** Zero mentions in any of the four live campaign transcripts; no e2e harness method exists. | **PARTIAL** (unit yes, VM transcript no) |
| 2 | **`cluster rehearse`** | Real, and a genuine composition rather than a parallel path: `rehearseCluster` (`cluster-fork.ts:380`) delegates to the fully-implemented `forkCluster` with `role: 'rehearsal'`, `writes: 'local'`, `up: true` (:391-397), i.e. an ephemeral secretless fork behind a health gate. `discardRehearsal` (:417) runs on both the success path (:407) and inside the failure `catch` (:400), so a failed gate cannot strand state. Command wired at `commands/cluster/index.ts:230`. **VM transcript: NONE.** | **PARTIAL** (risk is LOW: its delegate `forkCluster` is the most heavily live-proven path in the program, but rehearse's own role/discard semantics have never run) |
| 3 | **Release rung 0 + 1 + canary weight templating** (05 §2) | Real. `repo-release.ts` (307 lines), honestly self-scoped at :2 ("v1: rung 0 + canary weight templating") and :7 (rung 3 blue/green "composes; no dedicated verb in v1"). Rung 0 `releaseUndoSnapshot:58` issues a real `datastore_snapshot_create` (:65); canary `createCanary:155` takes the undo snapshot (:166), renders the overlay (`renderCanaryOverlay:94`, emitting `rediacc.canary_of` / `rediacc.weight` at :141-142), applies and records it (:178-179). Unit coverage: **9 tests**. Command wired at `commands/repo-canary.ts:54`. **I specifically checked the backend claim** (the CLI asserts the split is served by renet's router): `private/renet/pkg/router/canary.go` **exists, is real, and is wired**. `applyCanaryWeights:41` parses `rediacc.weight` 0..100, republishes the stable Traefik service as a `weighted` service `{stable: 100-w, canary: w}` (:74-81), and **has a real production caller** at `pkg/router/kube.go:175`, plus 4 unit tests (`canary_test.go:61,98,116,131`). **VM transcript: NONE.** | **PARTIAL** (unit yes, VM transcript no) |
| 4 | **Thin node-local CSI driver** (05 §3b, spec 09) | Overwhelming. Code: `pkg/kubecsi` (24 unit tests, self-registration with no registrar, path-probe volume_id), `pkg/kube/csidriver` (units/objects/CRDs/CSR-PKI renderers, golden-tested), `kubevolume` path-keyed primitives. **csi-sanity (spec 09 §12's own prescribed conformance gate): 21P/58F -> 43P/7F -> 48P/2F**, the 2 residuals ruled as documented deviations. **Live battery on cluster `csi1`:** CSIDriver + StorageClass (WFFC) + CSINode self-registered + VolumeSnapshotClass; dynamic PVC bound ~20s to a LUKS image, pod write/read; VolumeSnapshot `readyToUse`; restore proven **point-in-time** (STATE-A vs STATE-B); clone proven **independent**. **Auto-enablement proven live**: recreate EXIT=0 with `kube_install` logging "CSI driver enabled (cluster objects + node units + snapshot-controller)", zero manual steps. Three live-only bugs caught and fixed (provisioner NAMESPACE env, ExtractSidecar ETXTBSY, immutable-CSR delete-before-create). | **PASS, exceeds** on substance |
| 4a | Gate conjunct: **"a stock Helm chart with a dynamic PVC"** | **NOT DONE.** The string "helm" appears in `docs/design/09-implementation-phases.md:138` (the gate letter) and `spec/09-csi-driver.md:671` (which prescribes `groundhog2k/postgres`) and in the impl report's runbook, and **nowhere in any live transcript**. The live battery used hand-rolled PVC + Deployment manifests in a `pgtest` namespace. | **NOT PROVEN -> B2** |
| 4b | Gate conjunct: **"a velero/VolumeSnapshot backup"** | VolumeSnapshot arm proven (snapshot `readyToUse`, restore point-in-time, clone independent). Velero itself never run; reading the "/" as alternation, the conjunct is satisfied. | **PASS** |

---

## P2 carry-in dispositions (the nine from spec/08)

| # | Carry-in | Evidence | Status |
|---|---|---|---|
| 1 | New-model cluster fork orchestrator **in product code** | `forkCluster` / `cluster-fork.ts`. Proven live **four independent times**: FU#1 (tag f5, EXIT=0, full battery), rv1 (tag v1, EXIT=0, **zero manual seeding**), e2e suite 16 (tests 1-11 green, three separate runs), e2e suite 17 (whole-cluster fork, 125.3s). Battery each time: fork CA != parent, parent admin cert 401 on fork / 200 on parent, injected + third-party secrets ABSENT (F6 scrub), ROLE=fork, app-data marker rode the clone, **parent never stopped** (FU#1: 374/374 liveness samples zero gaps; rv1: 4941 served / gap 2 = 99.96% over 82 min). | **DISCHARGED, exceeds** |
| 2 | New-model migrate (in-Ceph fenced remap, health gate, rollback) | rv1 migrate EXIT=0: CA **equal** (preserved), secrets **present**, ROLE stays primary, `datastore_forget` cleared the source record (single-mounter). **Cutover downtime 21.6s** authoritative. e2e suite 17 test 6 migrate green (59.0s), **cutover 53.0s** (honest: CSI-down + unwind inside the window, no discount). Sequence adopt-plain -> verify -> down -> detach -> attach -> rewrite -> health -> forget ran in product code. Rollback on attach failure = re-attach source + CP restart (code). | **DISCHARGED** |
| 3 | Live ceph group-snap fork battery (FU#1) | `reports/p3-fu1-live-cephfork.md`. Timings (tag f5): group snap 1.2s, `datastore_fork` 0.3s, adopt 37ms, attach dm-thin 0.4s, identity-rewrite 74s, total ~85s. | **DISCHARGED** |
| 4 | Live membership + node-lifecycle (FU#2) | `reports/p3-fu2-join-lifecycle.md`. Evict PASS (backref cleared, verified by **object read**, not a name grep, which was spec/08's specific complaint). Join re-adopt PASS. Lifecycle ordering PASS + graceful reboot leg. Three carrier assertions proven on a fresh create: #16 (mons survive the dockerd bounce; `Restart=always` drop-in on disk with create-time ctime), #17 (exactly ONE `rbd` pool, size2/min1, immediate, no ERANGE), CSI auto-enable. | **DISCHARGED** |
| 5 | E2E suites 15/16/17 rewritten **and passing locally** | Rewritten and run. **Suite 15: 7/7 GREEN, exit 0.** **Suite 16: 11/12** (entire functional battery green, three times; only test 12 teardown red = #29). **Suite 17: 6/7** (entire functional battery green including cluster migrate; only test 7 teardown red = #30). | **PARTIAL.** All functional claims proven; the literal wording ("multinode suite passing locally gates P3") is **not** met. Two teardown-only reds -> **B3** |
| 6 | Attach-time auto node-label | **NOT DONE, and now live-witnessed** (e2e T10: a node-pinned local PV needs the label; the suite must call `kube_node_label` explicitly). `datastore attach` does not auto-label. Disposition below. | **DEFERRED to P4** (recommended, with the fix location named) |
| 7 | Overlay-fill auto-grow wiring | **DONE and properly wired.** `growThinPools` (`cmd/renet/thin_pool_maintain.go:51`) with `NeedsGrow`/`GrowTarget` threshold logic, online grow, convergent no-op on a half-grown pool. **It has a real scheduled caller**: `cmd/renet/repository_maintain.go:185`, and `repository maintain --all --json` is exactly the `ExecStart` of the storage-maintain timer (`pkg/daemon/storage_maintain_timer.go:34`). 5 unit tests (`thin_test.go:142-270`). I checked this specifically for the #26 zero-caller pattern; it does not apply. | **DISCHARGED** |
| 8 | `--secrets-encryption` guidance -> P7 docs | Unchanged, still a P7 docs item. | **CARRIED to P7** |
| 9 | Minor sweeps | `cluster evict --force` now wired (`cluster-membership.ts:186,219-224`: refuses on held datastores unless `--force`, which warns and names the honest manual path). Remainder (stale comment `node_lifecycle_unit.go:87`, `--operation` default, `REDIACC_SKIP_MACHINE_ACTIVATION` teaching error, 2-OSD pool accommodation staying test-only) still open. | **PARTIAL** -> P4 list |

---

## The bug ledger

**Tally = 30. Verified.** #1-6 (P0-P2) + #7-15 (FU#1, nine) + #16-19 (rv1, four) +
#20-22 (FU#2, three) + #23-28 (e2e, six) + #29-30 (e2e teardown reds, two) =
6+9+4+3+6+2 = **30**.

### FIXED + LIVE-VALIDATED (all nine spot-checked in code by the reviewer)

| # | Bug | Fix located at | Verdict |
|---|---|---|---|
| **#10** | Bridge-relay `[fn]` prefix broke every `JSON.parse` of a captured bridge-fn stdout. **Systemic**: the product two-cluster fork could never have run live as written. | `parseCapturedJson`, `services/executor/local-executor.ts:473`. Regex identifier-anchored (`/^\s*\[[A-Za-z_][A-Za-z0-9_]*\]\s?/`, :475) so a bare `[{...}]` array is not eaten; logrus lines filtered (:480). Call sites: `cluster-ceph.ts:91`, `cluster-fork.ts:106,209,637,658`, `repo-replicate-ops.ts:318`. Test `parse-captured-json.test.ts` has the real relay shape (:15), the bare-array regression (:33), and a logrus decoy (:38). | **VERIFIED** |
| **#13** | KVM MAC collision across concurrent topologies. | `pkg/infra/vm/kvm/osquirks.go:61` folds `netOffset&0xff` into the MAC; callers `kvm/driver.go:150,264`. netOffset 0 is byte-identical to the old encoding. | **VERIFIED** |
| **#14** | Fork datastore record registered only in the SOURCE machine registry, so a cross-machine `datastore attach` on the dest failed "not registered on this machine". The architectural blocker. | New `datastore adopt` verb: `pkg/datastore/adopt.go:32`; `--plain` arm (:47-52, this is #18's fix); `Forget` (:88) refuses default (:90) and refuses while attached (:98). Cmd `datastore_named.go:226`; bridge fns `functions/commands/datastore.go:118,131`. CLI ferry: `cluster-fork.ts:210` base64-encodes the record, `:212` adopts on the dest. Tests `adopt_test.go:114,132,152`. | **VERIFIED** |
| **#21** | `CreateK3sSystemdService` never **enabled** the unit, so rebooted nodes never restarted k3s. A production-reboot killer. | `pkg/daemon/k3s_systemd.go:128` `enableK3sService`, called on **both** arms: unchanged-unit (:108, so already-installed nodes self-heal) and fresh-write (:120). | **VERIFIED** |
| **#23** | Path-form `--datastore` discarded the descriptor's authoritative `Name` and hardcoded "default", so namespace/StorageClass/PV-affinity were labelled `ds-default` on named datastores. PVs would never bind. Silent and feature-breaking. | `cmd/renet/reporuntime_dispatch.go:62-63` now prefers `desc.Name` over the `resolveDatastoreMount` fallback (:27,:30). | **VERIFIED** |
| **#24** | `applyPersistedManifests` applied repo manifests RAW, bypassing `kube.RenderManifest`: no Service ever got its router annotations, and `lintSecurity` (hostNetwork/NodePort rejection, spec 05 §1b) was bypassed. The contract survived; its caller had been deleted. | `pkg/reporuntime/kube.go:499` renders via `kube.RenderManifest`, applies `stamped` (:503). | **VERIFIED** |
| **#26** | **The product started host daemons it never stopped.** `kube install` auto-starts the node CSI trio whose socket and `--kubelet-root` live INSIDE the control datastore; `csidriver.RemoveNodeUnits` existed with **ZERO callers**. Every storage-releasing verb (detach, migrate, evict, kube uninstall) was refused, with no mount holder to find. | Callers now exist: **detach** `cmd/renet/kube_csi.go:149-150`, **`kube uninstall`** `cmd/renet/kube_install.go:129-130`, plus the `csi-node-down` verb (:370). Discriminator `NodeUnitsHostedUnder` (`pkg/kube/csidriver/units.go:222`) reads the **installed unit's real `--kubelet-root`** and matches `mount+"/"`; the **trailing separator is load-bearing** (`ds-control-prod` must not match sibling fork `ds-control-prod-f1`, or a parent detach would kill the fork's live CSI). Tested both directions: `units_hosted_test.go:35,64`. | **VERIFIED** |
| **#27** | `dmsetup remove` single-shot, racing udev's open on the umount uevent, stranding the mapping. | `pkg/toolexec/devicemapper/devicemapper.go:107` `RemoveDevice`: 5 attempts (:120), `--retry` (:122), breaks on non-busy (:125-127), linear backoff (:128), returns the real error on exhaustion (:131). No lazy success. | **VERIFIED** |
| **#28** | `repository down` (kube arm) ran `kubectl delete namespace` under the generic **30s** exec timeout, but that call blocks on pod termination gated by the **30s** default grace period, which a PID-1-without-SIGTERM-handler burns entirely. A **guaranteed** collision: `down` failed on essentially any real kube repo, leaving it half-down (services stopped, namespace and volumes live). | `pkg/reporuntime/kube.go:23` `namespaceDeleteTimeout = 5 * time.Minute`; `:28` inner `namespaceDeleteKubectlTimeout = 4 * time.Minute`, applied at :268 inside `Teardown` (:229). Surfaces the real kubectl error instead of a ctx-SIGKILL "exit -1". | **VERIFIED** |

**No NOT-FOUND, no MISMATCH across all nine.** Every claimed fix is present in the
working tree and does what the ledger says.

### DOCUMENTED for P4

| # | Bug | Claimed status | Reviewer finding |
|---|---|---|---|
| **#20** | `cluster evict` does no node-side teardown, so the evicted node's k3s unit keeps running and a same-machine re-join port-collides. | Documented, **restated to its original narrow scope**; the "4-witness submount generalization" **withdrawn**. | **CONFIRMED, and the record says so explicitly.** `reports/p3-e2e-live.md:46`: "The '4-witness submount finding' was a wrong generalization and is withdrawn." The lead logged the over-generalization as **his own error**. The ledger self-corrected rather than defending the tidier story. I count that as a mark in the ledger's favour. |
| **#25** | `cluster create` builds per-node agent repos (`createNodeImage`) then passes the **control** datastore mount to their `kube_join`, so the repo goes unused and the data-dir lands on the root fs; `cluster join` uses the per-node repo instead. Two join paths, two behaviours, dead state. | Documented -> P4 | **CONFIRMED.** Note the P4 framing already flagged: agents are a disposable cache (02 §1), so the vestigial repo may be **deletable** rather than the mount fixed. |
| **F1** | Product CT-11 guard refuses `repository_fork` on cluster-attached-ds repos; design 06 §3 specifies kube repo fork. | Ruled a **design contradiction, not a bug**; suite 15 test 6 flipped to a NEGATIVE test asserting today's refusal. | **CONFIRMED.** Suite 15 test 6 is green as a refusal assertion. P4 must implement the positive path and flip the test. |
| **#29** | Suite 16 test 12: after a clean unmount, `dmsetup remove <fork>-cow` returns EBUSY for 27s of retries. Not a mount, not a process, not a loop, and **not** btrfs's scanned-device cache (refuted by controlled experiment on the fleet). | Documented, unexplained | **CONFIRMED as genuinely unexplained.** A post-failure probe is wired, so the next run names the holder. Honest disclosure: the original pre-detach probe was taken while still attached, so its "Open 1" measured only the live mount and proved nothing. The report says this itself. |
| **#30** | Suite 17 test 7: after a cluster **migrate**, the repo namespace refuses to terminate (`down` ran 240.7s into its own 4-minute bound), while an identical `down` on a never-migrated cluster finishes in seconds (suite 15 green). Migrate-specific, not #28 recurring. | Documented | **CONFIRMED.** Post-failure probe wired (namespace phase + finalizers, pod deletionTimestamp/node, PVC/PV finalizers). |

Also open and minor: **#22** (cluster destroy leaves a stale `state.clusters.<name>.memberIds`
orphan; `removeClusterFromStore`, `config-cluster-logic.ts:150-153`, deletes
`resources.clusters[name]` but not `state.clusters[name]`, so a same-name recreate reuses
the stale memberId ledger). One-line fix, recreate implications untraced.

---

## Deviation rulings carried into the as-built record

- **CSI-DEVIATION-1** (maximum-length volume name is **refused**, not accepted): ratified
  as a clean reject, with `TestCreateVolumeRejectsOverlongName`. The kernel caps
  device-mapper names at 128 chars and CSI permits 128-char volume names, so the two
  cannot both be honoured; a loud reject beats a silent truncation collision.
- **CSI-DEVIATION-2** (CreateSnapshot idempotency is size-proxy, not provenance):
  accepted with its mitigation documented.
- **Agent-node CSI attach**: deferred residual (spec 09 §14 item 12). Workers currently
  no-op on the auto-enable fold.

**Dedup: DONE at this gate.** Both deviations had been documented **twice**, in spec/09 §14
(items 10/11, by csi-live) and again in spec/09 §16 (as-built, by csi-impl), a benign
artifact of two agents converging on the same rulings. I merged them: **§16 is now the
single home**, since §14 is titled "OPEN items" and a *ruled* deviation is by definition no
longer open. §14 items 10-11 collapse to a pointer (numbering preserved), and §14 retains
item 12 (the agent-node attach residual), which is genuinely still open. §16 absorbed the
detail that existed only in §14: the hashed-volume-id alternative was **rejected** because
it would break the path-probe fork resolution, and csi-sanity's max-length-name spec
**stays red by design** (the documented price, not a bug).

---

## Contradiction hunt (what the evidence does NOT support)

I was asked to say plainly what is unproven. Five things.

1. **The stock Helm chart was never installed.** This is the cleanest contradiction of
   the gate letter. The dynamic-PVC capability is genuinely proven, but by hand-rolled
   manifests (a static PVC plus a Deployment). A stock chart would additionally exercise
   the path that actually matters for the F6 motivation: a third-party chart's
   **StatefulSet `volumeClaimTemplates`** (generated PVC names, ordinal pods) interacting
   with WFFC and `storageCapacity`. That is materially different plumbing from a static
   PVC, and ecosystem compatibility is the entire reason the Helm requirement is in the
   gate letter. A hand-rolled manifest cannot demonstrate it, by construction. **-> B2.**

2. **"E2E passes locally" does not hold as written.** Suite 15 is 7/7. Suite 16 is 11/12.
   Suite 17 is 6/7. Every **functional** claim of the redesign is green (and suite 16's
   battery went green three independent times), but spec/08 carry-in 5 says "multinode
   suite passing locally gates P3", and the multinode suite has a red test. The two reds
   are teardown-only, with named causes and self-diagnosing probes already wired, and no
   functional proof depends on either. That is a good position. It is not the same as
   "passing". **-> B3.**

3. **P3's feature layer was overshadowed by the CSI and live campaigns.** This is true
   and it is the finding I would most want the operator to see. `repo replicate`,
   `cluster rehearse`, and the release ladder are P3's *named* deliverables, and they
   received code plus unit tests and then nothing else. Zero live execution. Zero e2e
   harness methods (`grep` for `repoReplicate|repoRelease|rehearseCluster` across
   `packages/e2e-tests/src/` returns nothing). Every "release" hit in the e2e transcript
   is the *storage* sense of the word (release a mount), not the release ladder, and the
   one "replicate" hit in suite 16 is an English verb in a comment. I want to be precise
   about the shape of this risk, because it cuts both ways:
   - The code is **real**, not stubbed. I hunted for stubs and found none; I hunted for
     the #26 "exported but zero callers" pattern in the two nearest analogues and found
     that both `applyCanaryWeights` (caller: `router/kube.go:175`) and `growThinPools`
     (caller: `repository_maintain.go:185`, which is the timer's ExecStart) are properly
     wired.
   - But the phase's own headline result is that **four feature-breaking bugs survived
     unit tests and two live campaigns** and fell only to end-to-end execution. Three
     features that have never been run once are, on this codebase's demonstrated base
     rate, likely to contain exactly that class of defect. **-> B1.**

4. **The raw P0-P2 evidence is gone.** The 2026-07-11 host reboot destroyed the `/tmp`
   scratchpad holding the spike transcripts (a-f) and the P2 VM validation logs. Only
   their verdicts survive, in spec/07 and spec/08. Program state has since moved to a
   durable location, so this cannot recur, but it is an irreducible gap: P0-P2 claims now
   rest on gate reviews rather than on raw artifacts. Noted, not re-litigated.

5. **Two process facts worth banking, because they nearly cost correctness.** (a) A
   `SendMessage` abort cannot preempt a mid-turn agent: two agents shared one live
   environment for roughly 40 minutes, and the manifest records that it was luck, not
   design, that prevented a collision. Replacement agents must HOLD for an explicit GO
   before the first environment mutation. (b) Absence of transcript writes was twice read
   as agent death and twice was wrong, producing two false ownership flips. Liveness must
   be judged from the agent's task output, not from file mtimes.

---

## Carry-in 6 disposition (attach-time auto node-label): **P4**, and here is where the fix goes

The e2e campaign live-witnessed the gap (T10): a node-pinned local PV will not bind
unless the node carries `rediacc.io/ds-<name>`, and `datastore attach` does not stamp it,
so the suite has to call `kube_node_label` by hand. This is the original wave3b symptom,
still reproducible.

Recommendation: **P4, not now**, but with the fix location named so it is not
re-litigated:

- **Fold it into renet's `datastore attach` path**, mirroring the symmetric CSI fold that
  csi-live landed (`deployCSIForAttachedDatastore` on attach, `RemoveNodeUnits` on detach,
  which is #26's fix). Attach is already the seam that installs the per-node CSI units and
  the per-datastore StorageClass; the node label belongs on exactly that seam, and detach
  should strip it. Putting it in CLI porcelain instead would be **thrown away by P4's own
  reshape**.
- Do it in P4 rather than now because it mutates the attach path, and mutating attach
  without a live window to re-validate is precisely how #26 shipped. It needs one live
  re-run: drop the explicit `kubeNodeLabel` call from suite 15 test 3 and assert the label
  appears by itself.
- Do **not** defer it past P4: the failure mode is a **silent** one (pods sit Pending
  forever with no error pointing at the missing label), which is the worst kind for a user
  meeting the product for the first time.

---

## Checkpoint integrity

The newest durable checkpoint at review time (`phase-3-fu1fixes-*`, 2026-07-11 14:14)
**predated the entire P3 tail**: the rv1 fixes (#16-19), the whole CSI driver, and every
e2e fix (#23, #24, #26, #27, #28). The operator's two commits (console `9eee3671b`, renet
`c7e187a`) captured much of the tree, but the working-tree delta carrying most of the
e2e-found product fixes was **not** in any durable checkpoint.

I cut a fresh one before writing this review (patch files, not commits, per the
agents-never-commit rule):

```
~/.claude/projects/-home-muhammed-monorepo-console/checkpoints/
  phase-3-gate-console.patch            (93K, vs HEAD 9eee3671b)
  phase-3-gate-console-status.txt
  phase-3-gate-console-untracked.tar.gz (9.4K, incl. cluster-fork.ts)
  phase-3-gate-renet.patch              (70K, vs HEAD c7e187a)
  phase-3-gate-renet-status.txt
  phase-3-gate-renet-untracked.tar.gz   (2.7K, incl. adopt_test.go, units_hosted_test.go)
```

The patches are far smaller than the pre-commit 17.4M ones because the operator committed
the bulk. The uncommitted delta is now exactly the P3-tail fix set.

---

## AUTHORITATIVE P4 CARRY-IN LIST

P4 is under an **operator hold**. This list is what P4 (and the remaining phases) must be
briefed from.

### Blocking before program EXIT (from the gate letter; not blocking P4's start)

- **B1. Feature-layer live proof.** One bounded live window producing a VM transcript for
  `repo replicate`, `cluster rehearse`, and the release ladder (rung 0 undo-snapshot,
  canary create, weight flip end to end through the renet router's weighted service). This
  is the gate's explicit "VM transcript per feature" requirement and the only P3
  deliverable class with zero live evidence.
- **B2. Stock Helm chart against the CSI driver.** `groundhog2k/postgres` per spec 09
  §12.1, `--set storageClass=rediacc-csi-<ds>`: assert the StatefulSet's
  `volumeClaimTemplates` PVC binds, the pod lands on the datastore node (WFFC +
  `storageCapacity`), and a VolumeSnapshot backup/restore round-trips against it. Same live
  window as B1; the marginal cost over B1 is near zero once a cluster is up.
- **B3. The two teardown reds.** Suite 16 test 12 (#29) and suite 17 test 7 (#30) to green.
  Post-failure probes are already wired in both, so the next run should arrive with the
  holder named rather than costing a blind cycle.

### Design work items

1. **Shared node-side teardown primitive over the HOLDER TAXONOMY.** The campaign's
   cleanest conceptual result. Four distinct things can hold a datastore open, each
   invisible to the others' diagnostics, each needing a different remedy, **in this order**:
   (a) **kernel submounts**, and note the trap: k3s containerd overlays live at
   `/run/k3s/...`, **outside** the datastore path, and hold it busy through their `lowerdir`
   OPTIONS, so an "unmount everything under `<mount>`" filter misses them entirely (match the
   mount string anywhere in the `/proc/mounts` line, deepest-first);
   (b) **host processes** (the CSI trio, socket and state inside the datastore) = #26, now
   fixed, but the primitive must own it;
   (c) **device stacks** (per-volume LUKS loop + dm-crypt left open, with no mountpoint to
   find), whose **cause** was #28, now fixed;
   (d) **an open dm device with no userspace owner** = #29, still unexplained.
   Every storage-releasing verb (`cluster evict`, `datastore detach`, `cluster migrate`,
   `kube uninstall`, `repository down`) must route through this one primitive.
2. **#20 (narrow):** `cluster evict` leaves the evicted node's k3s unit running, so a
   same-machine re-join port-collides. (The 4-witness generalization is withdrawn.)
3. **#25:** the two-join-paths / vestigial per-node agent repo contradiction. Consider
   deleting the repo rather than fixing the mount (agents are a disposable cache, 02 §1).
4. **F1:** implement the kube-arm `repo fork` per design 06 §3, revise the CT-11 error text,
   flip suite 15 test 6 from negative to positive, and fix the spec/06 §15 wording-vs-suite
   mismatch.
5. **#29 / #30:** the two teardown root causes (also B3).
6. **#22:** stale `state.clusters.<name>.memberIds` on destroy (one-line fix; trace the
   same-name-recreate implications first).
7. **Carry-in 6:** attach-time auto node-label, folded into renet's `datastore attach`
   (see the disposition above). Silent-Pending footgun; do not defer past P4.
8. **Multi-node worker-attach CSI wiring** (spec 09 §14 item 12): workers currently no-op on
   the auto-enable fold.
9. **No standalone bare-machine provision.** Fork and migrate destinations require a
   helper-cluster-then-`kube_uninstall` dance to produce a bare machine. Candidate gap from
   the rv1 exit report.
10. **Test-mode dispatcher flag drift.** `functions once --test-mode` flags are hand-listed
    and lagged every redesigned verb (H1, H2, H3 were all this class). Derive the dispatcher
    flags from the bridge `ParamDef` registry so they cannot drift.
11. ~~Spec 09 §14 / §16 deviation dedup~~ **DONE at this gate** (merged into §16; see the
    deviation-rulings section above). No P4 action.
12. **Minor sweeps still open** from spec/08 carry-in 9: stale self-heal comment
    (`node_lifecycle_unit.go:87`); reconsider the `--operation` default (recommend
    required-no-default); teaching error naming `REDIACC_SKIP_MACHINE_ACTIVATION=1` (it has
    now bitten three separate agents); `installCeph`'s 2-OSD `size 2 / min_size 1`
    accommodation must stay test-only and never become a product default.
13. **P6 e2e carry-over:** drop suite 16's now-redundant test-side `csiNodeDown` (since #26,
    the product does it), and expect the two teardown reds until B3 lands.
14. **i18n:** the 12 x 58 CLI-surface naturalization red is deferred to **P7 by standing
    ruling** (P4 reshapes the CLI, so naturalizing now is throwaway). P4 must not try to
    clear it. P7 must.
15. **From spec/07, unchanged:** latest-magic resolver; composite-key view;
    `takeover` -> `promote` CLI rename; D3 baseline re-keying in P7.
16. **CLI-side from config v3:** the command reshape itself is P4's subject (153 leaves per
    spec/03). The one explicit handoff note I could locate is `reports/p3-w7-productionize.md:86`
    (the legacy per-node repo mount "is P4 porcelain for the cluster-repo path"), which is the
    same object as #25 above. I did not find a separate config-v3 handoff document beyond this
    and the program memory; if one exists outside `reports/`, it was not in my evidence set.

---

## Summary

P3 delivered a working, conformance-tested, live-proven CSI driver and, through its live
campaigns, converted the redesign's flagship claims (whole-datastore fork with PKI re-mint
and secret scrub, parent never stopped; whole-cluster fork with anchor plus rejoin;
in-Ceph fenced cluster migrate with a measured cutover) from design assertions into
repeatable end-to-end proofs. It also found and fixed seven product bugs that no unit test
would ever have caught, four of them feature-breaking.

What it did not do is run its own feature layer even once, or install the stock Helm chart
its gate letter names. Neither gap is expensive to close, and neither undermines what was
proven. But they are gaps, they are in the gate letter, and they should be closed with
evidence rather than argued away.

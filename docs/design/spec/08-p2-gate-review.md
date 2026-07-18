# 08 — P2 Gate Review (cluster layer: anchor+rejoin fork/migrate, membership, node lifecycle)

Reviewer: Fable gate agent, 2026-07-11 ~02:45-03:30. Fully-autonomous mode (this review
stands in for the user per the approved plan). Subject: the entire P2 phase against
`09-implementation-phases.md` §P2, `04-cluster-fork-migrate.md`, and specs 00-07.
Evidence root: scratchpad `checkpoints/` + `reports/` + live-run logs. Every cheap
check was re-run by me, not trusted.

## VERDICT: **PASS-WITH-NOTES** — the composed fork/migrate orchestration + e2e rewrite fold into P3 as its mandatory first wave

**Final status: all three pre-P3 blockers identified below were resolved and
re-verified during the review itself** (the F1 fork-verb hazard closed by
p2-forkmigrate, the gate re-greened after two lint rounds, the evidence files
recovered). The only bookkeeping still owed is the checkpoint re-cut. P3 may start.

The P2 **primitive layer is done and strongly proven**: the F1-F8 fork PKI re-mint
(the program's F1 blocker) is implemented with a fail-loud CA-fingerprint refusal and
unit-tested against a real sqlite kine DB; the anchor model (`ds-control-<cluster>`
embedded control plane) is proven live end-to-end (p2b create exit 0, battery ran
kubectl against it); the node-label seam and evict's Node-object deletion are proven
live — join re-adopt and evict's backref-clear are **unit-proven only** (the author
corrected their initial claims when I challenged the evidence; see criterion 4); the
node lifecycle units exist with the re-entrancy deadlock (bug #6) verified fixed;
all four claimed bug fixes are in the diff; gates re-ran green (after two rounds of
lint fixes made during this review); the i18n baseline grew only by the one
sanctioned D3-R2 batch; no commits were made.

What the evidence **contradicts** in the brief: the composed new-model cluster fork
(04 §2 group-snap → clone → attach → fork-rewrite → rejoin) and the new-model migrate
(04 §3 in-Ceph fenced remap; health-gate + rollback pipeline) do **not** exist in
product code. They exist as renet primitives plus the staged battery script
(`scratchpad/p2a-fork-battery.sh`). The user-facing `rdc cluster fork`/`cluster
migrate` verbs still run the pre-program S2 recipe — and `forkCluster` calls
`kube_identity_rewrite` **without** `operation=fork`, which now defaults to the
CA-preserving migrate arm: the verb named "fork" produces a fork carrying the parent
CA, the exact F1 hazard this program exists to close (P1's explicit fork-arm REFUSAL
was effectively replaced by a silent default). *(This hazard was CLOSED during the
review — blocking item 1 below records the verified fix; the paragraph stands as the
review-time finding.)* The phase's own gate letter ("2-node
fork AND migrate proven locally with timings; rewritten multinode e2e suite passes")
is therefore unmet — partly by sanctioned descope (RAM exhaustion), partly because
the p2-e2e wave never ran.

Ruling rationale: FAIL would mandate doing this work before P3 starts; but P3's
features (rehearse, replicate) ARE compositions over fork/migrate, so the same work
happens either way — blocking adds no safety. What must not survive into P3 is the
CA-carrying `cluster fork` verb (cheap fix) and a red gate. Hence PASS-WITH-NOTES
with hard conditions.

### Must be fixed BEFORE P3 work begins (blocking, all cheap)

1. **Close the `cluster fork` F1 hazard** — **RESOLVED during review, re-verified by
   me**: (i) `renet kube identity-rewrite --operation` is now REQUIRED — empty errors
   with "a fork rewritten as migrate would ship the parent CA key"
   (kube_identity.go:28,60-62; the backward-compat migrate default is gone, per this
   review's recommendation); (ii) `forkCluster` REFUSES with a teaching error pointing
   at the P3 anchor+rejoin rebuild and dispatches NOTHING — the new test asserts both
   the rejection and `exec.mock.calls.length === 0` (cluster-kube.test.ts:143-156);
   (iii) `migrateCluster` passes `operation: 'migrate'` explicitly
   (cluster-kube.ts:398). One baseline entry added for the new required-operation
   error-wrap (tool-count 2845; my entry-diff confirms exactly +1 = 2620) —
   **sanctioned by this gate as blocker-1 remediation** (same internal error-wrap
   class as D3-R2); baseline frozen again after it. Post-fix gates re-verified by me:
   check:ci-renet EXIT=0 (gate08-ci-renet4.log), tsc 0, vitest 1432/1432 (the old
   fork-path test replaced by the refusal test).
2. **check:ci-renet green** — **RESOLVED during review, in two rounds**: (i) my first
   re-run was RED on one golangci `modernize` finding in the bug-#3 fix
   (`pkg/infra/ceph/provisioner.go:197`) — p2-forkmigrate fixed it; (ii) the freshly
   pinned golangci-lint v2.9.0 then surfaced nolintlint drift (unused
   `//nolint:ireturn` directives in P1-wave `kubevolume/provisioner.go`,
   `reporuntime/factory.go`, `reporuntime_dispatch.go`) — the lead fixed it
   idiomatically (ireturn `allow` list in `.golangci.yml` + directive removal).
   My final confirmation run: **EXIT=0 GREEN** (gate08-ci-renet3.log).
3. **Bookkeeping**: re-cut `checkpoints/phase-2-{console,renet}.patch` — now stale by
   the two lint-fix rounds AND the blocker-1 fix (provisioner.go, kubevolume, factory,
   reporuntime_dispatch, `.golangci.yml`, kube_identity.go, cluster-kube.ts + its
   test, baseline.json). **Still owed** — the only remaining pre-P3 item. The missing
   membership evidence files are **RESOLVED**: the author had written them to the
   console repo's `reports/` by mistake and has copied all three into the scratchpad
   evidence root, with claims CORRECTED (see criterion 4).

## Per-criterion evidence table

| # | Criterion | Evidence | Verdict |
|---|---|---|---|
| 1 | Fork PKI re-mint F1-F8 per spec 05 §3, fail-loud CA assert, F1-F4 vs real sqlite kine, fork/migrate arm split | `pkg/kube/distro/fork_remint.go` (new): F1 rm `server/tls` (:45), F2 delete kine `/bootstrap/%` rows via sqlite3 with loud-error-if-missing-tool (:84-99 — the spike-d trap), F3 token rotate incl. symlinks (:62), F4 agent identity wipe (:105), F5 extension-apiserver-authentication CA rewrite (:240), F6 three-part secret scrub incl. `--keep-third-party` escape (:261), F7 restart-all-pods AFTER F8 (:231), F8 ROLE rewrite + stale-Node delete (:221-226). Fail-loud assert: `identity.go:272` errors "CA re-mint FAILED — byte-identical to the parent … Refusing to ship" when fingerprints match. Arm split: `IdentityOpFork`/`IdentityOpMigrate` (identity.go:36-48); fork requires server mode + new networkID (:111-114); migrate = leaf-only reset, CA preserved (:238-251). Unit tests re-run by me green (`go test ./pkg/kube/distro/`): `TestForkPreBootScrub` seeds a REAL sqlite kine DB with a `/bootstrap/` row AND an unrelated `/registry/secrets/...` row, asserts bootstrap gone + unrelated kept (fork_remint_test.go:110-160); fingerprint difference + stability + missing-file-errors covered. | **PASS** |
| 2 | Anchor cluster-create proven live; cluster fork orchestration in code | Anchor create: `installControlPlane` (cluster-kube.ts:177-215) dispatches `datastore_create --cluster` → `datastore_attach` → `kube_install --mount-path /mnt/rediacc-ds/ds-control-<c>` — **PROVEN LIVE end-to-end on p2b**: `p2b-create5-lead.log` exits 0, "k3s control plane up (1 server + 1 agent(s))", and the battery then ran kubectl against it (`rediacc-p2b-11 Ready control-plane v1.36.2+k3s1`). p2afork corroborates the anchor portion (`p2a-create2.log` lines 293-393: ds-control-p2afork created/attached/kube_install dispatched) though THAT transcript ends failed at the agent step (license-era) — the report's "Ready" verification was interactive. Fork orchestration: **primitives all in product code** (`datastore_snapshot_create --group`, `datastore_fork --snapshot --group` = pkg/datastore/fork.go:53-62, `datastore_attach --writes`, identity-rewrite fork arm), composed **only in the staged battery script**, NOT in `forkCluster` — see blocking item 1 and P3 carry-in 1. | **PASS on anchor-create; PARTIAL on orchestration** (primitives yes, composition no — contradicts the brief's claim) |
| 3 | Cluster migrate: in-Ceph fenced remap + cross-site pipeline + health gate + rollback in code | NOT composed. `migrateCluster` (cluster-kube.ts:470-548) is the pre-program single-node backup_push relocate: no fenced remap (though datastore fencing primitives landed in P1), no per-repo down()/up() pipeline, no health gate, no rollback window. The health CONTRACT does exist at the runtime layer (`pkg/reporuntime/reporuntime.go:224` `Health` one-evaluation, `Warming`/`HealthUnknown` gate policy per 04 §4 / gate C5) and `repository_health` is a live bridge fn — the composition over it is absent. The battery's migrate leg (§9b) proves only the renet identity-rewrite migrate arm (CA preserved, secrets stay). | **NOT MET as claimed** → P3 carry-in 2 |
| 4 | Membership join/evict proven live; node-label at attach; node lifecycle in code; bug #6 fixed | `cluster-membership.ts`: join = idempotent adopt (same-cluster no-op, other-cluster refusal :108-117), token from anchor mount, backref write (:171); evict = datastore-holder refusal (:216-222) → `kube_node_remove` with `node_ip` resolution → backref clear. **Live evidence, as corrected by the author after my challenge** (`p2b-battery-partial.log` + updated `reports/p2-membership-vm.md` close-out): node-label add/remove idempotent incl. InternalIP→hostname resolution (carry-in 1 primitive) **PROVEN LIVE**; evict **Node-object deletion PROVEN LIVE** ("evicted", post-evict `get nodes` = CP only). **Evict backref-clear: unit-proven only** — the battery's grep-by-machine-name check was invalid (matches regardless of the backref field). **Join re-adopt: FAILED live** — battery env gap (missing `REDIACC_SKIP_MACHINE_ACTIVATION=1` → production license-issuance failure on the agent's `repository_create`, the bug-#5 class), not a join-code failure; unit-proven (cluster-membership.test.ts asserts token→create→join→backref). Both live confirmations fold into FOLLOW-UP #2 with the trivial env fix. Node lifecycle: `cmd/renet/node.go` boot=ReattachAll only / shutdown=stop-k3s-then-DetachAll (lock release, fenceless return); unit installed from `CreateK3sSystemdService` (k3s_systemd.go:92) with `After=rediacc-node-lifecycle.service` in the golden unit; reconcile timer v2 ExecStart=`node boot --json`. **Bug #6 VERIFIED FIXED**: `runNodeBoot` (node.go:42-64) carries the explicit BUG #6 comment and calls ONLY `ReattachAll` — no `EnsureClusterNodeUnits`, no self-heal re-entrancy. | **PASS-WITH-NOTES** (join + evict-backref + boot/reboot cycle live = FOLLOW-UP #2; two nits: stale "self-healed from node boot" comment at node_lifecycle_unit.go:87; `evict --force` flag accepted but unused) |
| 5 | P1 carry-ins 1-9 addressed | Table below. | 6 addressed, 3 deferred-with-owner |
| 6 | Gates green; i18n baseline frozen | Re-run by me 2026-07-11: **tsc 0 errors**; **vitest 103 files / 1433 tests PASS**; **go test ./... exit 0**; **check:ci-renet: two RED rounds during review** (modernize in the bug-#3 fix, then nolintlint drift under the pinned golangci-lint v2.9.0 — see blocking item 2), both fixed (author + lead), **final confirmation run EXIT=0 GREEN** (gate08-ci-renet3.log). i18n baseline: reconstructed the P1-checkpoint baseline and diffed — P2 added exactly **56 entries** (removed 2), ALL in P2-wave files (`distro/fork_remint|identity|k3s|external`, `ceph_config.go`, `kube_node.go`, `node_lifecycle_unit.go`, `provisioner.go`) = the D3-R2 sanctioned one-wave internal-string batch (~50 estimated; the tool's own count 2844 vs P1-gate 2789 agrees at ~55 — the membership report explains an interim clobber-and-regenerate that my entry-level diff independently confirms was faithful). Baseline is hereby FROZEN again; any P2+ growth needs a new gate ruling. CLI-side P2 strings used real i18n keys across all 13 locales (no new debt). | **PASS** |
| 7 | No commits | `git rev-parse HEAD`: console `583eae93d`, renet `2b13e9d` — both unmoved. | **PASS** |
| 8 | Six discovered bugs | Table below. | 4 verified fixed, 2 confirmed process-only |

## P1 carry-in dispositions (spec 07 list)

| # | Carry-in | Status |
|---|---|---|
| 1 | Node-label at attach | **Seam built + proven live** (`kube_node_label` bridge fn, `distro/label.go`, InternalIP resolution, idempotent add/remove in battery step 1; remove-before-add failover semantics documented). **Auto-wiring at `datastore attach`/`detach` NOT done** — explicitly deferred to porcelain (comment in cluster-membership.ts:89-94 says P4). The original wave3b symptom (local-PV pods Pending until labeled) still reproduces unless the primitive is invoked → P3 carry-in 6 (decide P3 vs P4: the CSI driver's topology-by-ds-label may force it in P3). |
| 2 | Cluster-kubeconfig wiring | **DONE**: `wireKubeDeps` + `findClusterControlPlane` (reporuntime_dispatch.go:320-400) — cluster-attached repo with no own CP walks the registry for the sibling same-cluster datastore hosting an embedded distro; temp 0600 kubeconfig; k3s kubectl argv; ambient fallback only for true BYO (`ExternalDistro`, RepoEmbeddable=false so fork/migrate refuse it). |
| 3 | E2E suites 15/16/17 rewrite per spec 06 | **NOT DONE** — the queued p2-e2e wave never ran. `tests/kube/15-k8s-repo`, `16-k8s-ceph` (not renamed), `17-multinode-cluster` unrewritten; only BridgeTestRunner/RepositoryMethods/types touched. Still red-until-rewritten → P3 carry-in 5 (a 09 §P2 gate item, now owed). |
| 4 | Cluster-scope PKI scrub F1-F7 | **DONE** — the P1 refusal stub replaced by the full implementation (criterion 1). |
| 5 | kvm memberIds → state.clusters | **DONE**: `state-schema.ts:86-90` `clusters.<name>.memberIds`; kvm-provisioner.ts:82-87 persists there. |
| 6 | `--secrets-encryption` residual | **ADDRESSED AS DOCUMENTED RESIDUAL** (forkmigrate report §4): the at-rest key rides the fork inside `server/cred/`, cannot be deleted pre-boot (k3s must decrypt kine before F6), but F6 deletes all parent Secret VALUES — only the key is shared, same class as the LUKS credential (spec 05 §2). Remediation `k3s secrets-encrypt rotate-keys` post-fork; not a v1 default. Fold the guidance into P7 docs. |
| 7 | CLI cluster-arm latent refs | **DONE**: repo-create-delete.ts + repo-fork.ts dispatch runtime-generic `repository_create`/`repository_fork` (kube detected from the datastore descriptor); datastore.ts ceph-unfork refuses with a `datastore detach --discard` teaching error. Final porcelain naming P4 as planned. |
| 8 | Live fencing race | **DEFERRED with the multinode suite** (carry-in 3 → P3 carry-in 5). |
| 9 | Overlay-fill auto-grow | **NOT WIRED** (only the grace-window comment in toolexec/devicemapper/thin.go:35) → P3 carry-in 7, as spec 07 anticipated (P2/P3). |

## The six discovered bugs

| # | Bug | Status | Evidence |
|---|---|---|---|
| 1 | Transient SSH exit 255 under concurrent provision load | **Process/infra — confirmed no code fix needed** | Cleared on a quieter host; nothing in the diff pretends otherwise. |
| 2 | `ops up` 600s cap vs cephadm bootstrap + non-convergent force retries | **VERIFIED FIXED** | `OpsVMLifecycle.ts:69-72`: `1_800_000` (30 min) with a comment naming the cephadm cause; proper fix (topology-scaled timeout + convergent retry) recorded as candidate. |
| 3 | `SetRBDCloneFormat` verify used `config get global` (EINVAL on Squid) | **VERIFIED FIXED + unit-tested** | `provisioner.go:176-208`: verify via `config dump` + entity-agnostic `rbdCloneFormatSetTo2` parser; `provisioner_test.go` new. (The fix itself carried the one lint finding — fixed during review.) |
| 4 | Anchor-on-ceph double ceph bootstrap (ops phase + installCeph) aborted create | **VERIFIED FIXED + regression test** | `cluster-provision.ts:238-272`: `cephIsBootstrapped` probes `ceph_health`; when a mon answers, skips prereqs+bootstrap+cluster_create and converges only the pool. Test "skips bootstrap when ceph is already up (ops phase) and converges the pool (BUG #4)" asserts `ceph_bootstrap_cluster` NOT dispatched. |
| 5 | renet license contamination via bare `./build.sh dev` | **Process — confirmed no code fix needed** | Matches the documented feedback_renet_dev_build gotcha; nolicense rebuilt + verified 23:52/23:55. Lesson: agents rebuild renet only via rdc.sh or with `--nolicense`. |
| 6 | `node boot` re-entrant systemd start-job deadlock (D-state, live hazard via reconcile timer) | **VERIFIED FIXED** | `node.go:42-64`: explicit BUG #6 comment; boot = ReattachAll only; unit install relocated to `CreateK3sSystemdService` (k3s_systemd.go:85-92); k3s golden units carry `After=rediacc-node-lifecycle.service`. Live reboot validation = FOLLOW-UP #2. |

## Descope rulings

**(a1) Live ceph group-snap cluster fork (P2-FOLLOW-UP #1): LEGITIMATE.** The blocker
was infrastructure (host RAM exhausted, 14 VMs / 54G, ceph mon OOM-killed, no quorum),
not code; the escalation valve was followed, not unilateral. The non-live evidence is
adequate FOR THE LAYER DESCOPED: F1-F8 unit-proven against a real kine DB including
the decisive /bootstrap trap; the fail-loud fingerprint assert makes a silent parent-CA
fork impossible by construction; anchor create proven live; the battery is staged,
syntax-clean, with both ceph gotchas folded in. **Condition**: the battery MUST run
and pass (parent-vs-fork fingerprints, old-cred 401, secret absence, parent liveness,
timings, migrate leg) before the P3 gate closes, and before `cluster rehearse` — which
composes fork — is declared done. It needs a RAM-adequate host + healthy ceph.

**(a2) Live node graceful shutdown/boot (P2-FOLLOW-UP #2): LEGITIMATE.** The hang was
root-caused to a genuine product hazard (reconcile timer would wedge ANY real cluster),
fixed as a safety fix, and the fix is structural (re-entrancy removed) + unit/golden
covered. Live validation (unit install/ordering, ExecStop→ExecStart cycle, ReattachAll
on already-mounted re-attach — the D-state secondary suspect) folds into the same
fresh-session follow-up as (a1). Lower risk than (a1); does not gate P3 features.

**(b) Are the follow-ups precise enough to execute later? YES for both** — #1 has a
runnable script with exact preconditions; #2 names the three specific things to
validate. Both are anchored here and in the manifest.

**(c) What the evidence contradicts** — recorded honestly:
- The brief's "cluster fork orchestration exists in code" and "migrate … in code":
  true only at the primitive layer; the 04 §2/§3 compositions are battery-script-only
  (criteria 2/3 above). The `cluster fork` verb is actively hazardous (blocking item 1).
- The manifest cited `reports/p2-membership-vm.md`, `-tests.txt`, and
  `p2b-battery-steps0-3.log` which did not exist at review start — **RESOLVED**: the
  author had written them to the console repo's `reports/` by mistake; all three are
  now in the scratchpad evidence root.
- The partial battery log did not show the agent node back after JOIN, and the
  backref-cleared check was grep-by-machine-name (matches regardless). **CONFIRMED
  REAL by the author**: join re-adopt FAILED live (battery env gap — missing
  `REDIACC_SKIP_MACHINE_ACTIVATION=1` → license issuance failure; join code
  unit-proven) and the backref live check was invalid. The manifest's original
  "steps 2-3 PROVEN LIVE (join re-adopt: node back)" was overstated; the author's
  updated report now states the honest evidence level, which criterion 4 reflects.
- `p2a-create2.log` (cited for the p2afork anchor proof) ends `CREATE2 EXIT=1` at the
  agent step; the anchor portion succeeded in-log, the "Ready" verification was
  interactive. Cured by p2b's clean end-to-end create.
- `checkpoints/phase-2-renet.patch` is stale by the during-review lint fix (re-cut).

## AUTHORITATIVE P3 carry-in list

P3 = feature layer (replicate, rehearse, release rung 0+1, thin CSI) **plus, as its
mandatory first wave**:

1. **New-model cluster fork orchestrator in product code** (04 §2: group snap →
   clone-per-member → attach `--writes` → `kube_identity_rewrite --operation fork` →
   fresh agent joins → stale-Node cleanup; mount-path stability; kills the
   `dstAgents >= srcAgents` constraint). Promote the battery's sequence into
   `forkCluster`/its successor. `cluster rehearse` is a thin wrapper over this — build
   it first.
2. **New-model cluster migrate**: in-Ceph fenced remap (detach/attach via the P1
   fencing primitives, networkID kept), cross-site 03 §4 pipeline, per-repo
   **health-gate composition** over `RepoRuntime.Health`/`repository_health`
   (+ `--health-window`/`--health-timeout` per spec 03) with rollback = intact source.
3. **Live ceph group-snap fork battery** (FOLLOW-UP #1) — pass before the P3 gate;
   script `scratchpad/p2a-fork-battery.sh`; needs RAM headroom + healthy ceph.
4. **Live membership + node-lifecycle validation** (FOLLOW-UP #2, one fresh p2b
   session with `REDIACC_SKIP_MACHINE_ACTIVATION=1` set for the whole battery):
   (i) join re-adopt end-to-end (agent Ready + backref SET); (ii) evict backref-clear
   verified by reading the machine's config object, not a name grep; (iii) unit
   install/ordering via kube_install, graceful reboot ExecStop→ExecStart re-attach
   cycle, ReattachAll on already-mounted datastores (the D-state secondary suspect).
5. **E2E suites 15/16/17 rewrite per spec 06** (owed 09 §P2 gate item) + the
   DatastoreMethods harness additions + carry-in 8 (live fencing race) folded into the
   multinode suite; multinode suite passing locally gates P3.
6. **Attach-time auto node-label wiring** (carry-in 1 remainder) — decide P3 (CSI
   topology needs it?) vs P4 porcelain; until wired, local-PV pods on cluster-attached
   datastores need the manual primitive.
7. **Overlay-fill auto-grow wiring** (carry-in 9; spike-f recommendation) alongside the
   maintain/reconcile timer generalization.
8. **`--secrets-encryption` guidance** → P7 docs (`k3s secrets-encrypt rotate-keys`
   post-fork); revisit as a scrub step only if the flag becomes a v1 default.
9. **Minor sweeps**: `cluster evict --force` is accepted but unused (wire to a
   drain-force/skip-drain path or drop it); stale self-heal comment
   `node_lifecycle_unit.go:87`; reconsider the `--operation` default (blocking item 1
   recommends required-no-default); `installCeph`'s 2-OSD test-topology pool
   accommodation (`size 2/min_size 1`) stays test-only, never product default;
   probe the `rdc cluster kubeconfig` success:false observation (p2b-kubeconfig.err
   — possibly a broken product verb, the battery worked around it via the control
   node's embedded k3s); teaching errors for the two recurring KVM-topology footguns
   (license issuance should name `REDIACC_SKIP_MACHINE_ACTIVATION=1` — it has now
   bitten three separate agents; worker `VM_DSK` vs 20G node repo sizing).

P4 reminders unchanged from spec 07 (latest-magic resolver, composite-key view,
takeover→promote CLI rename, D3 baseline re-keying in P7).

## Checkpoint integrity

`phase-2-console.patch` (323K), `phase-2-renet.patch` (481K), `phase-2-untracked.tar.gz`
(282K) exist; the untracked list correctly captures the new P2 files (fork_remint,
node.go, node_lifecycle_unit.go, cluster-membership.ts, ceph_config.go, preflight,
label, kube_node_label_test). One staleness: the checkpoints predate the two
during-review lint-fix rounds (`pkg/infra/ceph/provisioner.go`,
`pkg/kubevolume/provisioner.go`, `pkg/reporuntime/factory.go`,
`cmd/renet/reporuntime_dispatch.go`, `.golangci.yml`) — re-cut before P3
(blocking item 3).

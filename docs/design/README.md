# Datastore-Centric Redesign: Design Suite

Status: **AS-BUILT for P0-P4; forward-looking for P5-P7** (updated 2026-07-13).
Supersedes the deleted `docs/DESIGN-CEPH-KUBERNETES.md`.

This suite began (2026-07-10) as a design. It is no longer one. Phases P0 through P3 are
**built, gate-reviewed, and proven on real infrastructure**; the storage core, the cluster
layer, and the CSI driver all exist in the working tree and have been run live. What
follows describes the system that was built, including the places where the build
contradicted the design and the design lost.

The original conclusion still stands and is now demonstrated rather than argued: the old
Kubernetes storage design integrated Ceph at the wrong layer (per-PVC RBD images, ceph-csi,
RADOS namespaces), and rebuilding it around the philosophy that already works in the
docker world (datastore pools, repos as single CoW-forkable units, Ceph strictly below)
produces a system where whole-cluster fork with data included is true by construction.

The user (sole operator, no backward compatibility required, clean breaks preferred)
approved the maximal scope: core redesign + feature layer + full CLI reshape, with
examples, CI coverage, and rewritten docs built on top of the NEW architecture. P4 (CLI
reshape) is BUILT and awaiting gate review; P5 through P7 remain to be executed.

## What is proven live

Every number below was measured on real KVM infrastructure and traces to a transcript.
None are estimates. See §"Evidence index" for where each came from.

| Claim | Evidence |
|---|---|
| **Whole-cluster fork (anchor + rejoin), parent never stops** | Proven live FOUR independent times: FU#1 (tag f5), rv1 (tag v1, zero manual seeding), e2e suite 16 (11 tests green, three separate runs), e2e suite 17 multinode. Fork wall time **~85s** (FU#1) and **125-161s** (e2e multinode, which includes a fresh agent joining the fork's new CA). |
| **Parent liveness through fork** | rv1: **4941 of 4943 samples served, gap 2, over 82 minutes** (99.96%). FU#1: 374/374 and 185/185, zero gaps. The group snapshot does not stop the parent. |
| **F1 PKI re-mint on fork** (the program's one blocker) | Fork CA differs from parent; the parent's admin cert gets **401 on the fork and 200 on the parent**; injected and third-party Secrets are absent in the fork; ROLE ConfigMap says `fork`. Verified on every fork run. Re-mint costs **~120s** (measured 117.9 / 119.9 / 98.4s across runs). |
| **In-Ceph cluster migrate, fenced remap, zero bytes copied** | Cutover **21.6s** (rv1, orchestrator-reported down-to-health-gate) and **53-56s** (e2e suite 17, which honestly counts the node-side CSI stop and mount unwind inside the window). CA preserved, secrets present, ROLE stays primary. |
| **Storage primitives** | RBD group snapshot **1.2s to 8.7s**; datastore fork (clone) **0.3s to 10.5s**; datastore adopt **37ms**; dm-thin overlay attach **0.4s to 30.1s**. |
| **Thin node-local CSI driver** (`csi.rediacc.io`) | Built, host-side systemd, zero container images, self-registering. csi-sanity conformance **48/50 passing** with 2 ruled deviations. Live: dynamic PVC bound to a LUKS image, VolumeSnapshot `readyToUse`, restore proven point-in-time, clone proven independent. Auto-enabled by `kube install` with zero manual steps. |
| **E2E suites** | Suite 15 (k8s repo): **7/7 green**. Suite 16 (ceph group-snap fork): **11/12**, entire functional battery green three times. Suite 17 (multinode fork + migrate): **6/7**, entire functional battery green. The two reds are teardown-only (#29, #30). |

Also worth stating plainly, because it shaped everything after it: **unit-green predicted
nothing about live behavior in this codebase.** The e2e leg alone found five product bugs
that unit tests and two prior live campaigns had all missed, four of them feature-breaking.
Thirty bugs were found across the program. That result is why P3's gate is
PASS-WITH-NOTES rather than a clean pass, and why B1/B2 (below) block program exit.

## Reading order

| File | Contents | Status |
|---|---|---|
| [01-current-architecture.md](01-current-architecture.md) | The "before" picture: storage objects, all five fork methods, mounting, encryption, known gaps, with code references. | Historical record, frozen |
| [02-target-architecture.md](02-target-architecture.md) | The model: named multi-datastores, k8s repo-as-folder, local PVs, secrets from config, REDIACC_ROLE contract, encryption scoping, the holder taxonomy, delete/keep ledger. | As-built |
| [03-fork-attach-snapshots.md](03-fork-attach-snapshots.md) | Fork semantics across all levels, the `--writes local\|ceph` attach contract, RBD group snapshots, the cross-site migration pipeline. | As-built |
| [04-cluster-fork-migrate.md](04-cluster-fork-migrate.md) | Anchor + rejoin cluster fork/migrate, record propagation, lifecycle hooks, rollback, rehearsal. | As-built |
| [05-feature-layer.md](05-feature-layer.md) | `repo replicate`, release ladder, PV LUKS, the CSI driver, RWX verdict, demo strategy. | As-built for CSI; **built-but-never-run** for replicate/rehearse/release (see B1) |
| [06-cli-reshape.md](06-cli-reshape.md) | The full command mapping: every current rdc command kept / moved / renamed / deleted / new. **The MAPPING is the contract, not a leaf count** (spec/03 §6; the count is retired, §0). Carries the 2026-07-13 rulings: build the positional ref concept as task zero; jobs are executor-born plus a global `--background`/`-b` (R-P4-2v2, merged from two operator rulings); `--detach` becomes `--no-wait`; canary stays under `repo`. **§1 is now an AS-BUILT transcript of the shipped tree, held there in both directions by `scripts/check-design-tree.ts`; §1.1 records the five differences from the tree it used to draw.** | As-built (P4) |
| [07-examples-and-ci.md](07-examples-and-ci.md) | The example catalog, harness design, conventions, CI job topology, and the three kube e2e suites that now exist. | Mixed: e2e suites as-built, examples forward-looking (P5/P6) |
| [08-docs-plan.md](08-docs-plan.md) | Docs rewrite plan, embed plugin, i18n mechanics and costs. | Forward-looking (P7) |
| [09-implementation-phases.md](09-implementation-phases.md) | **The phase map with P0-P3 done and their gate verdicts, the bug ledger, the authoritative P4 carry-in list, program exit criteria.** Start here if you are executing P4 onward. | As-built + forward |

### The spec directory

`spec/` holds the implementation-level specifications produced in P0 and the gate reviews
produced at each phase boundary. The gate reviews are the authoritative record of what was
decided and what was proven; where this suite and a gate review disagree, the gate review
wins.

| File | Contents |
|---|---|
| `spec/00-gate-review.md` | P0 gate. Rulings R1-R6 and contradictions C1-C15. **R1 (mount path) and C1 (volume layout) overrode this suite; both are folded in below.** |
| `spec/01-renet-packages.md` | renet package design, the bridge-function ledger. |
| `spec/02-reporuntime-contract.md` | The `RepoRuntime` interface and its shared contract-test suite. |
| `spec/03-cli-contracts.md` | Per-leaf CLI contracts, exit codes, the §6 disposition table. **The P4 contract.** §2.0 = the ref-concept task zero; §4.9/§4.10/§4.11 = the five path-keyed classification systems (plane, MCP, guardrails, policy globs, ref bindings); §9 = the eleven rulings, all decided. **§10-§13 = the as-built deltas per wave (w1 addressing, w2a config exodus, w2b repo family, w4 surface closure).** |
| `spec/04-config-schema-v3.md` | Config schema v3 and the one v2 to v3 migration. |
| `spec/05-k8s-templates-and-fork-hygiene.md` | K8s templates, the 8-step fork PKI scrub, the failover sequence. |
| `spec/06-p2-e2e-rewrite-scope.md` | The e2e rewrite contract for suites 15/16/17. |
| `spec/07-p1-gate-review.md` | P1 gate: **PASS-WITH-NOTES**. |
| `spec/08-p2-gate-review.md` | P2 gate: **PASS-WITH-NOTES**. Nine carry-ins into P3. |
| `spec/09-csi-driver.md` | The CSI driver spec and its as-built record, including CSI-DEVIATION-1 and -2. |
| `spec/10-p3-gate-review.md` | P3 gate: **PASS-WITH-NOTES (conditional)**. **The authoritative P4 carry-in list lives here.** |

## Evidence index

Program state, campaign transcripts, and checkpoints live outside the git tree in
`~/.claude/projects/-home-muhammed-monorepo-console/`:

- `MANIFEST.md` is the full program narrative: every ruling, all 30 bugs, every phase outcome.
- `reports/p3-fu1-live-cephfork.md`: first live ceph group-snap cluster fork (FU#1).
- `reports/p3-rv1-fork-migrate.md`: fork re-validation with zero manual seeding, plus the in-Ceph migrate leg with timings.
- `reports/p3-fu2-join-lifecycle.md`: join / evict / node-lifecycle battery.
- `reports/p3-csi-impl.md` and `reports/p3-csi-live.md`: the CSI driver, its code and its live conformance window.
- `reports/p3-e2e-live.md`: the e2e campaign, five product bugs, the holder taxonomy.

One honest gap: the 2026-07-11 host reboot destroyed the `/tmp` scratchpad holding the raw
P0 spike transcripts (a-f) and the P2 VM validation logs. Their verdicts survive in
`spec/07` and `spec/08`; the raw artifacts do not. Program state has since moved to the
durable location above, so this cannot recur.

## Ground rules for the implementing session

1. **No commits, no pushes, no PRs, no `git add` by any agent.** The operator commits the
   tree himself. Moving HEADs authored by him are sanctioned and expected; an agent-authored
   commit is an incident. Per-phase safety: `git diff` checkpoints into
   `~/.claude/projects/-home-muhammed-monorepo-console/checkpoints/` (console and
   private/renet separately).
2. **Everything validated locally** (CI is expensive): Go units + vitest + real KVM VM
   sessions + the examples harness. A change without an executed local test is not done.
   P3 demonstrated the stronger version of this rule: a change without an executed *live*
   test is not done either.
3. **Sub-agent models**: Fable for specs, hard seams, and gate reviews; Opus for the bulk of
   coding; Sonnet for all translation and naturalization.
4. Environment prerequisites (must be exported in the shell that LAUNCHES agents, since the
   overrides are ancestry-verified and cannot be set later):
   `REDIACC_ALLOW_GRAND_REPO='*'`, `REDIACC_ALLOW_CLUSTER_OPS='*'`. Plus passwordless sudo
   for virsh/virt-install and roughly 20GB+ free RAM for the 6-VM ops fleet.
   `REDIACC_SKIP_MACHINE_ACTIVATION=1` on every call against ops VMs (they are license-less;
   forgetting this has bitten three separate agents).
5. Renet dev builds stay `--nolicense` (the `./rdc.sh` default). Licensing is out of scope.

## Review history

TWO senior-Kubernetes-engineer review rounds were folded in before implementation began, and
their findings held up under construction. **Round 2** (20 findings: config structure + CLI)
produced the placement tagged union (R2-F1), the config spec/status split plus `config
reconcile` (R2-F2), and a **confirmed data-loss bug in the then-current code** (encrypted-mode
persist destroyed plaintext cluster/provider/strategy records, R2-F3) which was fixed by the
unified persist path with per-field encryption in config schema v3. **Round 1** (16 findings)
hardened the Kubernetes edge. The storage core (datastores, group-snap fork, anchor+rejoin,
kine, the label-affinity trick, `--writes`) passed scrutiny intact.

The ONE blocker was **F1**: preserving the cluster CA on fork makes every fork a permanent
admin credential for the parent cluster. Fork now regenerates the full PKI (CA preserved for
migrate only). **F1 is implemented and proven live** on every fork run: the fork's CA differs
from the parent's, and the parent's admin certificate is rejected by the fork with 401.

Other load-bearing review changes, all now built: fork secret-scrub plus ROLE rewrite (F2),
the codified failover sequence (F3), the datastore-backed image registry (F4), per-volume
LUKS images for real capacity (F8), and the thin node-local CSI driver (F6), which shipped in
P3 and is specified in `spec/09-csi-driver.md`.

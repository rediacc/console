# PLAN: a local-only multi-cluster e2e suite (concurrent `cluster fork`, `cluster rehearse`, cross-site `cluster migrate`) sized for one host

Status: proposed -- converted from console#521 (operator picked this item 2026-11-16); awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: PLAN-cluster-crosssite-transport.md
Priority: P2 -- cross-site cluster migrate is designed, documented and refused at run time, and no run proves the rdc-driven fork, rehearse or migrate across two clusters
Concurrency: parallel -- new files under packages/e2e-tests/tests/multicluster plus one config; check-e2e-coverage.ts takes one dark-suite entry
Owns: agent/plans/PLAN-multicluster-local-suite.md, packages/e2e-tests/tests/multicluster/**, packages/e2e-tests/playwright.multicluster.config.ts, packages/e2e-tests/README.md, .github/workflows/ct-tests.yml (header comment only), scripts/gates/check-e2e-coverage.ts (one PRODUCTION_DARK_SUITES entry), docs/design/03-fork-attach-snapshots.md (section 4 status line only), docs/design/04-cluster-fork-migrate.md (section 3 status line only)
Source: https://github.com/rediacc/console/issues/521

**Operator ruling, 2026-11-16 (AskUserQuestion, session e0f36861):** "we may try to do it locally. We have around 64GB of ram. If it helps we can have a test that work locally only with github deffered."

## Ask

The datastore-centric cluster verbs are concurrent by nature: `cluster fork` proves "the parent never stops" and bidirectional isolation only with parent and fork running together, and a cross-site `cluster migrate` needs two independent Ceph clusters up at once. Two such clusters do not fit a 16 GB GitHub runner. The operator ruled for a local-only suite on the workstation, with GitHub CI deferred. Checking the code showed the cross-site migrate is not built at all; the transport moved to its own plan by operator ruling ASKED:2026-11-16T08:59Z ("Own plan"), PLAN-cluster-crosssite-transport.md, and this plan is its first consumer and its local proof.

## Context (checked 2026-11-16 against the tree)

1. `forkCluster`, `rehearseCluster` and `migrateCluster` live in `packages/cli/src/services/cluster/cluster-fork.ts` (`:140`, `:373`, `:508`), not in `cluster-kube.ts` as the issue says.
2. Cross-site migrate is unbuilt: `migrateCluster` refuses it (`packages/cli/src/services/cluster/cluster-fork.ts:519-525`) and its comment says the transport "is NOT a landed primitive" (`packages/cli/src/services/cluster/cluster-fork.ts:502-507`). PLAN-cluster-crosssite-transport.md builds it (Context 2-8 there). The pipeline is designed in `docs/design/03-fork-attach-snapshots.md:73-95` and marked "NOT LIVE-VALIDATED" there, while `packages/e2e-tests/README.md:27-28` claims it was "Proven live in the P3 batteries". The README is wrong.
3. `packages/e2e-tests/README.md:30-31` says `cluster rehearse` was "Proven live in the B1 window"; the ledger says its fork, PKI, health, discard and #43 legs never ran (`docs/design/spec/13-wave2-ledger.md:118`). Also wrong.
4. What CI already covers: suites 16 and 17 run parent plus fork on one fleet through raw renet over the bridge (`packages/e2e-tests/playwright.k8s-ceph.config.ts:48`, `playwright.k8s-multinode.config.ts`, jobs at `.github/workflows/ct-tests.yml:1989` and `:2224`). Suite 18 (E2E Migrate) is the single-cluster migrate (`README.md:28`). Nothing drives the rdc orchestrator across two declared clusters, and suite 24's rdc-driven VM tier is excluded from CI (`.github/workflows/ct-tests.yml:2196-2224`).
5. Local-only marking: a suite selected by no CI config must sit in `PRODUCTION_DARK_SUITES` with a `BLOCKER:` reason of at least 40 characters (`scripts/gates/check-e2e-coverage.ts:600-618`), which `check:ci-e2e-coverage` enforces; a config no workflow runs stays out of `PRODUCTION_REGISTRY` (`scripts/gates/check-e2e-coverage.ts:85-100`), like `playwright.image.config.ts`. The README section "Deliberately not in CI" carries the reason (`README.md:23-25`), and `.github/workflows/ct-tests.yml:3-7` points to it.
6. KVM clusters: `rdc cluster create --provider kvm` requires `--net-name` and `--net-base` so two clusters never share a network by accident (`packages/cli/src/commands/cluster/declare.ts:63-91`); `--net-offset` places a second cluster on the same net (`packages/cli/src/services/cluster/kvm-topology.ts:40-42`, `:131-132`). Hyperconverged pools are refused on KVM (`packages/cli/src/services/cluster/kvm-topology.ts:120-130`). VM RAM comes from `VM_RAM_WORKER` and `VM_RAM_CEPH` (`private/renet/pkg/infra/opsconfig/config.go:398-416`), which `cluster create` passes through (`docs/design/07-examples-and-ci.md:74`). A Ceph pool on fewer than 3 OSDs is created at size 2 / min_size 1, pg_num 32 (`packages/cli/src/services/cluster/cluster-provision.ts:283-294`).
7. Budgets: the CI single-cluster ceiling is about 14.5 GB modeled (`docs/design/07-examples-and-ci.md:72-74`); CI's proven Ceph sizing is `VM_RAM_CEPH=2560` with `CEPH_OSD_MEMORY_TARGET=1717986918` (`.github/workflows/ct-tests.yml:1128-1130`). Measured host on 2026-11-16 (`free -g`): 56 GiB total, 27 GiB available while the shared ops fleet (VMs 1, 11, 12, 21-23, 15 GiB) runs. libvirt nets in use: `renet11` (ops fleet) and `renet12` (examples convention, `docs/design/07-examples-and-ci.md:40`).
8. Cluster verbs need `REDIACC_ALLOW_CLUSTER_OPS` in the launching shell; suite 24 passes it to the CLI through `CliRunner`'s extra env (`packages/e2e-tests/tests/kube/24-cluster-licensing.test.ts:150`, `packages/e2e-tests/src/utils/CliRunner.ts:76`).
9. No `rdc` verb discards a non-rehearsal cluster fork; `discardRehearsal` does it with `kube_uninstall` plus `datastore_detach --discard` (`packages/cli/src/services/cluster/cluster-fork.ts:434-462`).
10. Coverage search: no live or `_done/` plan covers #521's suite. The cross-site datastore transport is PLAN-cluster-crosssite-transport.md.

## Design

**D1. Two sites on two nets, never the shared fleet.** Site A `mc-a` on `renet13`/`192.168.113`: one control VM (1 GiB), two Ceph VMs at 2560 MiB, one k8s-server and one k8s-agent at 3072 MiB, about 12 GiB. Fork dest `mc-d` on `renet13` at `--net-offset 40`: one control VM and one k8s-server, about 4 GiB, sharing A's network so it reaches A's monitors. Site B `mc-b` on `renet14`/`192.168.114`: one control VM, two Ceph VMs, one k8s-server and one k8s-agent, about 12 GiB, an independent Ceph (own fsid and monitors).

**D2. Phases keep the peak under the measured headroom.** Phase F (fork, isolation, rehearse) holds A plus D, about 16 GiB. Phase X (cross-site migrate there and back) holds A plus B, about 24 GiB; D is destroyed first. The peak fits the 27 GiB available beside the shared fleet. The config's `globalSetup` reads `MemAvailable` from `/proc/meminfo` and refuses to start a phase that would leave under 3 GiB, naming the figure. On a host with the shared fleet down, `MULTICLUSTER_CONCURRENT=1` keeps D alive through phase X (about 28 GiB).

**D3. Proofs are ground truth.** Fork: a 0.5 s `readyz` loop against the parent API runs from before the snapshot to after the fork is up and must show no gap over 2 s; the parent admin client certificate gets 401 from the fork API and 200 from the parent, and the fork's certificate the reverse; a Secret created on the parent before the fork is absent from the fork; a row written on each side after the fork is absent on the other. Rehearse: the five legs of PLAN-cluster-live-proofs.md B1, asserted rather than recorded. Migrate: a marker row survives both legs, the verb's `Cutover downtime` line is parsed and attached to the report, and after each leg the old site holds no attached datastore of the cluster.

**D4. The transport is its own plan.** The `renet datastore send|receive` subcommands, the host-relayed pipe and the fsid routing in `migrateCluster` are designed and built in PLAN-cluster-crosssite-transport.md (its D1-D3); this suite consumes them through `rdc cluster migrate` and is the transport's live proof (M4, M6).

**D5. GitHub CI stays deferred.** The suite is selected by no workflow and named in `PRODUCTION_DARK_SUITES`. Trigger to revisit: a runner with at least 32 GB (a GitHub larger runner or a self-hosted runner on the ops host) is budgeted, or the scaled-down topology (single Ceph VM per site) is shown to keep phase X under 14 GB; either one moves the suite into a workflow and out of the dark list in the same commit.

Out of scope: the transport itself (PLAN-cluster-crosssite-transport.md), same-machine concurrent forks (netns-per-cluster, dropped by the operator), a CLI verb that discards a persistent fork (Context 9; the suite uses the bridge functions and the gap is an operator question below), and the Linode leg (PLAN-cluster-live-proofs.md).

## Boxes

- [ ] M1 [writer] `playwright.multicluster.config.ts` and `tests/multicluster/00-topology.test.ts`: the D2 memory refusal in `globalSetup`, cluster create and destroy for `mc-a`, `mc-d`, `mc-b` through `CliRunner` with `REDIACC_ALLOW_CLUSTER_OPS=mc-a,mc-d,mc-b`, the `MULTICLUSTER_SUITE=1` gate (a red, not a skip, when unset under this config), and an `afterAll` that destroys every `mc-*` cluster it created. Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0.
- [ ] M2 [writer] `tests/multicluster/01-fork-concurrent.test.ts`: the D3 fork proofs on `mc-a` and `mc-d`, then the fork's teardown through `kube_uninstall` and `datastore_detach --discard`, asserting no `:<tag>` record survives. Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0.
- [ ] M3 [writer] `tests/multicluster/02-rehearse.test.ts`: `rdc cluster rehearse mc-a --on mc-d`, with the five legs of D3 asserted from renet state before and after the discard. Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0.
- [ ] M4 [writer] `tests/multicluster/03-cross-site-migrate.test.ts`: destroy `mc-d` (unless `MULTICLUSTER_CONCURRENT=1`), migrate `mc-a` to `mc-b`'s server and back, with the D3 migrate proofs. Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0.
- [ ] M5 [writer] Local-only marking: a `PRODUCTION_DARK_SUITES` entry per new test file with a `BLOCKER:` reason naming the two-cluster memory need and the README item; the README "Deliberately not in CI" items 1 and 2 rewritten to the truth (cross-site and rehearse are proven by this suite, not by past windows) with the run command and the D5 revisit trigger; the `ct-tests.yml` header comment names the suite; the `docs/design/03` section 4 and `04` section 3 status lines updated once M6 passes. Accept: `npm run check:ci-e2e-coverage` rc 0 and `npm run check:ci-workflows` rc 0.
- [ ] M6 [live] Full local run after PLAN-cluster-crosssite-transport.md's T boxes and M1-M5 land and `npm run vm:check -- --changed` is VERIFIED for the tree: `MULTICLUSTER_SUITE=1 PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --config playwright.multicluster.config.ts` from a shell with `REDIACC_ALLOW_CLUSTER_OPS=mc-a,mc-d,mc-b`. Accept: rc 0, the report path, the parent liveness gap maximum, both `Cutover downtime` figures and the peak `MemAvailable` low-water mark recorded under this box, and `virsh -c qemu:///system list --all` showing no `mc-*` VM afterwards.

## Risks

- **The host is 56 GiB, not 64.** Phase X peaks near 24 GiB against 27 GiB available beside the shared fleet. The D2 refusal fails loudly instead of letting the OOM killer pick a Ceph OSD; a session that hits it waits for headroom or asks the fleet's owner, never stops another session's VMs.
- **Relay throughput.** The cross-site stream passes through the host twice; PLAN-cluster-crosssite-transport.md T0 measures it, and a long pre-copy lengthens M6, not the recorded downtime.
- **Shared network with the fork dest.** `mc-d` at `--net-offset 40` on `renet13` relies on the offset support in `kvm-topology.ts`; M1's first run proves it, and a collision there is a finding fixed in this plan.

## Questions for the operator

- Should a persistent cluster fork get its own discard verb (`rdc cluster fork discard <cluster> --tag <t>`), or is teardown through `datastore detach --discard` enough? DEFAULT: no new verb in this plan; the suite tears down through the bridge functions.

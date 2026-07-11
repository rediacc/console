# Datastore-Centric Redesign — Design Suite

Status: **DRAFT for review** (2026-07-10). Supersedes the deleted
`docs/DESIGN-CEPH-KUBERNETES.md`. Nothing here is implemented yet; nothing is committed.

This suite is written to be **self-sufficient for a new session with zero prior context**.
It captures a full discovery conversation (2026-07-10) that concluded: the current
Kubernetes storage design integrates Ceph at the wrong layer (per-PVC RBD images, ceph-csi,
RADOS namespaces) and should be rebuilt around the philosophy that already works in the
docker/single-machine world (datastore pools, repos as single CoW-forkable units, Ceph
strictly below). The user (sole operator, no backward compatibility required, clean breaks
preferred) approved the maximal scope: core redesign + feature layer + full CLI reshape,
with examples, CI coverage, and rewritten docs built on top of the NEW architecture.

## Reading order

| File | Contents |
|---|---|
| [01-current-architecture.md](01-current-architecture.md) | Verified map of what exists today: storage objects, all five fork methods, mounting, encryption, known gaps. The "before" picture, with code references. |
| [02-target-architecture.md](02-target-architecture.md) | The new model: named multi-datastores, k8s repo-as-folder, local PVs, secrets from config, REDIACC_ROLE contract, encryption scoping, delete/keep ledger. |
| [03-fork-attach-snapshots.md](03-fork-attach-snapshots.md) | Fork semantics across all levels, `--writes local\|ceph` attach contract, RBD group snapshots, the safe cross-site migration pipeline. |
| [04-cluster-fork-migrate.md](04-cluster-fork-migrate.md) | Anchor + rejoin cluster fork/migrate, lifecycle hooks (up/down/health), rollback, rehearsal. |
| [05-feature-layer.md](05-feature-layer.md) | `repo replicate` (read replicas), release ladder (canary/blue-green), PV LUKS, RWX verdict (CephFS/JuiceFS research), demo strategy. |
| [06-cli-reshape.md](06-cli-reshape.md) | **The full command mapping: every current rdc command → kept / moved / renamed / deleted / new.** ~150 → ~90 leaves. |
| [07-examples-and-ci.md](07-examples-and-ci.md) | The ~24-example catalog, harness design, conventions (verified footguns included), CI job topology, gate opt-ins. |
| [08-docs-plan.md](08-docs-plan.md) | Docs rewrite plan, embed plugin, i18n mechanics and costs (verified). |
| [09-implementation-phases.md](09-implementation-phases.md) | The phased program P0–P7 with gates, model assignments for sub-agents, verified repo facts, operational rules, risks, prerequisites. |

## Ground rules for the implementing session

1. **No commits, no pushes, no PRs, no `git add`** until the user says otherwise. All work
   stays in the working tree. Safety: per-phase `git diff > <scratchpad>/checkpoints/phase-N.patch`
   (console and private/renet separately).
2. **Everything validated locally** (CI is expensive): Go units + vitest + real KVM VM
   sessions + the examples harness. A change without an executed local test is not done.
3. **Sub-agent models**: Fable for specs/hard seams/reviews, Opus for the bulk of coding,
   Sonnet for all translation/naturalization.
4. **Work locally**: no git commits, no branches, no PRs. Keep a file MANIFEST + per-phase
   patch checkpoints as insurance for the long-running uncommitted tree.
5. Environment prerequisites (must be exported in the shell that LAUNCHES agents, ancestry-
   verified): `REDIACC_ALLOW_GRAND_REPO='*'`, `REDIACC_ALLOW_CLUSTER_OPS='*'`. Plus
   passwordless sudo for virsh/virt-install and ~20+GB free RAM for the 6-VM ops fleet.
6. Renet dev builds stay `--nolicense` (rdc.sh default). Licensing is out of scope.

## Baseline at time of writing

- console branch `0707-1`, HEAD `973763d30` (KVM cluster provisioning for `rdc cluster`
  just landed; it is a building block this design uses).
- `private/renet` HEAD `8478420` (namespace-teardown-leak hardening; ~400 lines of leak
  machinery that this redesign deletes again — kept as motivating evidence, see 01/09).
- The `rdc` CLI surface (cluster verbs, repo fork --cluster, datastore fork, secrets
  fork-hygiene, promote) has ZERO CI e2e coverage today; e2e drives `renet` directly.

## Review status (2026-07-10)

TWO senior-Kubernetes-engineer review rounds are folded in. **Round 2** (20 findings:
config structure + CLI) produced: the placement tagged union fixing the `default`-datastore
name-uniqueness contradiction (R2-F1, blocker), the config spec/status split + `config
reconcile` that makes derived `-m` routing trustworthy (R2-F2), a **confirmed current-code
data-loss bug** — encrypted-mode persist destroys plaintext cluster/provider/strategy
records — fixed via unified persist + per-field encryption in P1 config schema v3 (R2-F3),
the v2→v3 migration plan (R2-F6), structural repo tags + `latest` retirement (R2-F5),
rename verbs dropped (R2-F4), `@place` conflict + term-connect ambiguity rules (R2-F10/11),
`repo logs`/`exec` added (R2-F14), and the CLI conventions section 06 §7 (exit codes,
idempotency, add-vs-create, `-y` vs `--force`). **Round 1** (16 findings) has been folded
in. The storage core
(datastores, group-snap fork, anchor+rejoin, kine, the label-affinity trick, `--writes`)
passed scrutiny intact; every accepted change lives at the Kubernetes-facing edge and is
P0-spec-sized. The ONE blocker is **F1**: preserving the cluster CA on fork makes every
fork a permanent admin credential for the parent cluster — fork now regenerates the full
PKI (CA preserved for migrate only). Other load-bearing changes: fork secret-scrub +
ROLE-rewrite (F2), codified failover sequence (F3), datastore-backed image registry (F4),
per-volume LUKS images for real capacity (F8), a thin node-local CSI driver in P3 to keep
the Helm/operator/velero surface (F6). Findings map to 02 §2-4/§8, 03 §1, 04 §4/§7b,
05 §1/§3/§3b, and the P0 spike list in 09.

# 09 — Implementation Program: Phases, Gates, Operations

This is the execution plan for a fresh session with no prior context. Read README.md first,
then this file; the numbered design files are the spec sources per phase.

## 0. Operating rules (non-negotiable)

1. **NO commits, pushes, PRs, or `git add`** by any agent until the user lifts the rule.
   Work stays in the working tree. Per-phase safety: `git diff > <scratchpad>/checkpoints/
   phase-N-console.patch` and `git -C private/renet diff > .../phase-N-renet.patch`.
2. **Local validation for everything** (CI is expensive): `go test ./...` (renet), vitest
   (packages/cli), real VM sessions, the examples harness. Evidence (transcript/log path)
   required at each gate. Every claim of "works" must have been executed.
3. **Work locally**: no git commits, no branches, no PRs. Keep a MANIFEST (scratchpad) of
   every file the program touches + the per-phase patch checkpoints — cheap insurance for a
   long-running uncommitted tree.
4. **Models**: Fable = P0 spec, group-snap/identity seams, phase reviews, gnarly debugging.
   Opus = bulk Go/TS implementation, examples, CI YAML, harness, English docs.
   Sonnet = ALL naturalization/translation batches.
5. **User prerequisites before launching agents** (ancestry-verified overrides cannot be set
   later): `export REDIACC_ALLOW_GRAND_REPO='*' REDIACC_ALLOW_CLUSTER_OPS='*'`;
   passwordless sudo for virsh/virt-install; ~20+GB free RAM + disk for the 6-VM fleet.
6. Local dev conventions: use `./rdc.sh` (hooks block direct cli-bundle invocation);
   renet builds stay `--nolicense`; ops fleet on `renet11`/192.168.111, cluster work on
   `renet12`/192.168.112; VMs persist — `ops down` at phase ends; sleep >20s is hook-blocked
   (use background watch patterns).

## 1. Phase map

```
P0 spec+spikes → P1 renet storage core → P2 cluster layer → P3 feature layer
              → P4 CLI reshape → P5 examples → P6 CI → P7 docs+i18n
```
Sequential at gate level; WITHIN a phase, Opus agents parallelize per package area /
example batch / locale. Every phase ends: validation evidence + patch checkpoint + Fable
review (+ user review at P0 and P4).

### P0 — Spec + blocking spikes (Fable)
- Expand this design suite into the implementation spec where detail is still thin:
  renet package-level design (exact changes in `pkg/datastore`, `pkg/kube`,
  `pkg/functions/commands`; per-file delete ledger from 02 §6), bridge-function contract
  diff (rename/add/delete list), CLI command contracts for 06 (flags, errors, help text),
  PV-LUKS = per-volume LUKS images (settled by F8, 05 §3), health() contract decision
  (04 §4), image-into-cluster = datastore-backed registry (settled by F4, 04 §7b),
  **the `RepoRuntime` interface definition + shared contract-test suite design (02 §9)**,
  the per-namespace NetworkPolicy + ValidatingAdmissionPolicy templates (02 §8), the
  fork PKI-regeneration + secret-scrub + ROLE-rewrite step (02 §4, the F1 blocker),
  the codified failover sequence (02 §3), the `no-provisioner`/WFFC StorageClass +
  chart-compatibility matrix (02 §2), and the addressing grammar `repo[:tag][@place]`
  incl. the single-placement/unique-name semantic and push-copy-as-backup-artifact
  decision (06 §6).
- Round-2 spec deliverables (config + CLI, all in 02 §11 / 06 §6-7): the placement tagged
  union `{datastore}|{machine}` (R2-F1 — settle before ANY placement code); the
  spec/status split + `config reconcile` + derived-routing verification contract (R2-F2);
  the schemaVersion-3 migration (R2-F6); the `@place` per-verb acceptance table + conflict
  rule (R2-F10); the exit-code/idempotency/`-o json` contract table (R2-F15); replicate
  managed-state CRUD semantics (R2-F17); restore-vs-promote boundary (R2-F16).
- SPIKES (transcripts required):
  a. Ceph version deployed by renet's cephadm flow; verify `rbd group snap create` +
     clone-from-group-snap (needs Squid v19+) on the ops fleet. Fallback spec if older.
  b. k3s `local`-type PV + nodeAffinity + a `no-provisioner`/WaitForFirstConsumer
     StorageClass (02 §2, review F5) binds on a fresh KVM cluster; kubelet volume-stats
     behavior for a `local` PV over a loop-mounted LUKS image (review F8/F16).
  c. `repo secret` current surface (feeds 13-secrets example + k8s secret injection design).
  d. **BLOCKER (review F1)**: k3s re-mints CA + SA keys cleanly when the tls dir is removed
     from an EXISTING kine data-dir (fork PKI regeneration); check SA-key mismatch vs stored
     SA-token Secrets → the scrub scope.
  e. NetworkPolicy datapath (review F9): what source IP does kube-router see for host-proxy
     → pod under flannel? Decides ipBlock-vs-in-cluster-leg. Verify PSA `baseline`'s
     treatment of hostPath (review F7/F16) — determines whether the VAP backstop is required.
  f. dm-thin vs dm-snapshot as the `--writes local` overlay engine on BTRFS (review F10):
     measure overlay growth vs app bytes; confirm dm-thin errors-when-full vs the
     invalidate cliff.
- SPEC-ONLY decisions to record (no spike): the fork secret-scrub + ROLE-ConfigMap-rewrite
  step and its labeling convention (F2); the codified failover sequence + tolerationSeconds
  defaults (F3); built-images-into-a-datastore-backed-registry vs ctr-import (F4); the
  ValidatingAdmissionPolicy template denying hostPath/hostNetwork (F7); k3s-version skew
  metadata + attach preflight (F14); the thin-CSI path/naming layout so P1 volumes are
  CSI-adoptable (F6).
- GATE: user approves the spec deltas; all spikes documented with transcripts.

### P1 — renet storage core (Opus per area; Fable on fork/snapshot seams)
**`RepoRuntime` interface skeleton + contract-test suite first** (02 §9; Docker
implementation = wrap existing behavior, proving the contract against reality before the
Kube implementation is written against it). The contract tests assert the review-hardened
invariants: fork ⇒ empty/scrubbed secrets + regenerated PKI + ROLE!=primary (F1/F2).
`machine setup` auto-creates the `default` datastore (02 §7 — docker UX unchanged).
Per-repo-namespace default-deny (ingress) NetworkPolicy + the hostPath/hostNetwork
ValidatingAdmissionPolicy (02 §8, F7/F9). Named datastore registry (config + on-machine
state); multi-datastore addressing; create/attach/detach with `--writes` (generalize
`datastore fork`'s dm-COW + plain clone attach; refuse fork-attach without --writes;
fencing exclusive-lock+blocklist; codified failover sequence incl. stale-Node delete and
remove-before-add relabel, F3/F12; COW backing out of /tmp; overlay-fill monitoring in
storage-health); `datastore snapshot` (BTRFS local / rbd snap / rbd GROUP snap); k8s
repo-as-folder with **per-volume LUKS images** + static `local` PV generation +
`no-provisioner`/WFFC StorageClass per datastore + ds node labels (F5/F8; layout designed
CSI-adoptable per F6); dedicated `ds-control` default (F8); DELETE ledger (csi/RADOS-ns
machinery etc. — 02 §6); secrets-to-k8s injection; ROLE env injection (Rediaccfile env +
per-ns ConfigMap); k3s-version metadata + attach preflight (F14); **storage lifecycle
hygiene rules from the loop-stranding fix (03 — detach-before-unlink contract-wide, no
lazy-success, inventory-driven sweep via state bucket + dmsetup, convergent init; reuse
FindLoopDevicesFor/loopController from renet 8478420, do not reimplement)**.
**Config schema v3 lands here too** (CLI-side but foundational — datastore records must be
born into the fixed model, 02 §11): placement tagged union (R2-F1), spec/status `state`
bucket + `config reconcile` (R2-F2), **unified persist path + per-field encryption —
fixes the CONFIRMED encrypted-mode data-loss bug** (R2-F3, user decision: within the
redesign, no separate hotfix), structural repo tags replacing `name:tag` keys + `latest`
retirement (R2-F5), the one v2→v3 migration (R2-F6).
Per new/renamed bridge function: regenerate types into packages/shared, update
packages/e2e-tests references (check:ci-e2e-coverage greps per function name — WILL red
otherwise), rewrite affected e2e suites (16-k8s-ceph loses its subject; keep the multinode
fork/migrate proof shape on the new model).
GATE: features work on VMs (transcripts); `go test`, `go vet -tags "root ebpf_e2e"`,
check:ci-renet green.

### P2 — cluster layer (Fable orchestration logic, Opus support)
Anchor+rejoin `cluster fork` (04 §2: group snap → clones → attach → CP identity rewrite →
fresh joins → stale-Node cleanup; mount-path stability; --writes composes); migrate
(in-Ceph fenced remap; cross-site snapshot+export-diff pipeline with down()/final-snap/
diff/up()/health gate; rollback = intact source); Rediaccfile health() contract;
**membership verbs** `cluster join <machine>` (adopt an existing machine as agent — rides
the same CA-token join as anchor+rejoin) and `cluster evict <machine>` (targeted node
removal via the codified drain→fence→delete-Node sequence; replaces today's LIFO-only,
k8s-agent-only, kvm-only `scale` limitations for the remove case — `scale` stays for
pool-count semantics); **node graceful shutdown/boot lifecycle** (02 §3: renet shutdown
unit — pods-with-grace [k3s-stop-doesn't-stop-containers trap] → k3s → volume unmounts →
datastore detach/unmap/lock-release; boot = state-bucket re-attach → labels → k3s;
reconcile timer generalized to clusters).
GATE: 2-node KVM cluster fork AND migrate proven locally with timings; rewritten multinode
e2e suite passes locally.

### P3 — feature layer (Opus; Fable review)
`repo replicate` (05 §1), `cluster rehearse`, release rung 0+1 helpers + canary weight
templating (05 §2), and the **thin node-local CSI driver** (05 §3b, review F6:
provision=LUKS-image, topology=ds label, snapshot/clone=reflink via VolumeSnapshot/
dataSourceRef; adopts P1's already-CSI-adoptable volume layout). NOTE: per-volume LUKS
images landed in P1 as the volume FORMAT (F8), so PV encryption is not a separate P3 item.
GATE: VM transcript + unit coverage per feature; a stock Helm chart with a dynamic PVC and
a velero/VolumeSnapshot backup both work against the CSI driver.

### P4 — full CLI reshape (Opus per noun; Fable owns tree consistency)
Implement 06 (the mapping file is the contract). Re-annotate gating metadata. Regenerate:
renet-contract types, cli-docs, skill reference, validate-cli-examples ground truth; update
every documented rdc snippet (CLAUDE.md, docs, skills) in the same phase. CLI i18n en
strings + 12-locale naturalization (Sonnet, pipeline, delta).
Closing step: **MCP alignment gate** — apply the parked tree-walk coverage patch
(scratchpad `parked/mcp-coverage-gate.patch`; 56 drifted commands found on the old tree)
and classify every leaf of the new tree with `mcp` XOR `mcpExcludeReason`.
GATE: `./rdc.sh --help` tree == 06; MCP coverage test green on the new tree; vitest +
lint + i18n CLI gates green; USER reviews the tree.

### P5 — examples on the new surface (Opus batches)
Full catalog per 07 (§1-2 conventions are locked, incl. the `config init --name` footgun);
harness + gate opt-ins (07 §3-4). Order: harness + 02 + 10 first (proves conventions),
then parallel batches; track 3 after its cluster examples' commands exist; VM access
serialized by harness flock.
GATE: `run-examples.sh --all --continue` full PASS locally (40 manual, 42 n/a),
teardown-verified; per-example timings recorded (feeds CI-set trim).

### P6 — CI (Opus authors, Fable reviews; ci.yml LAST)
`ci-examples.yml` (07 §5) + ci.yml `examples-tests` job + the THREE ci-complete touches;
adjust ct-tests job envs where fleet shapes changed (P1/P2 rewrote suites). Local
validation: `npm run check:ci-workflows`, shfmt/shellcheck, CI-mirror harness runs with
`RDC="node packages/cli/dist/cli-bundle.cjs"`.
GATE: all workflow-affecting local gates green; CI-mirror runs PASS.

### P7 — docs + i18n (Opus en; Sonnet ×12; Fable claim-accuracy review)
Per 08: rewrite en pages track-by-track embedding example files (build the embed plugin
first); concepts page from this suite's 01-03; blog postscript/rewrite; renet datastore
README refresh; regenerate search index + cli reference; Sonnet re-naturalization batches;
restamp sourceHash/sourceCommit.
GATE = program exit: see §2.

## 2. Program exit criteria

1. Full example suite PASS on the new architecture (local + CI-mirror mode).
2. Cluster fork / migrate / rehearse / replicate transcripts with timings.
3. `npm run ci` diff vs the P0-recorded baseline: only pre-existing reds remain. Renet gates
   (check:ci-renet, dead-code, e2e-coverage, types-regen) green. Vitest green. i18n +
   search-index + workflows + cli-examples green.
4. `git status`: all program files present, uncommitted, intact; MANIFEST matches;
   checkpoint patches exist per phase.
5. This design suite updated to as-built; final report with timings, spike outcomes, and
   product gaps discovered en route (candidate issues listed, NOT filed without user ask).

## 3. Verified repo facts a new session must not rediscover the hard way

- `full ops up` = bridge .1 + workers .11/.12 + ceph .21-.23, Ceph auto-provisioned
  (~10 min); `--basic` = bridge + worker 11; VMs persist; renet escalates via `sudo virsh`.
- ops VMs are NOT registered as machines automatically; scripts do it
  (tutorial pattern: `.ci/tutorials/lib/tutorial-helpers.sh`, `tutorial-forking.sh`).
- `config init` ignores `REDIACC_CONFIG`; always `--name examples` (07 §2 footgun).
- Cluster RAM env-tunable through `rdc cluster create` (VM_RAM/VM_RAM_WORKER/VM_RAM_CEPH
  pass through to renet opsconfig; floor 2048; bridge fixed 1024).
- `check:ci-e2e-coverage` greps packages/e2e-tests for every generated renet function name
  (raw `resource_verb` or spaced `resource verb` both count).
- `check:ci-workflows`: SHA-pinned actions, no inline `script:`, secrets via env (no
  actionlint exists). New ci.yml jobs need the ci-complete THREE touches.
- shfmt/shellcheck scopes exclude a bare top-level examples/ (opt-in edits in 07 §4);
  eslint `**/*.ts` glob does NOT exclude it; biome/knip ignore non-workspace dirs.
- Docs freshness: en docs edit → 12 twins + sourceHash; new page → twins or pending list;
  any docs/blog change → regenerate search-index (08 §4).
- Agent hooks: cli-bundle direct invocation blocked (use ./rdc.sh); ssh/docker to
  192.168.111.* allowlisted; sleep >20s blocked; scp/manual renet deploy blocked.
- The i18n pipeline for locales is `private/growth/i18n_pipeline` (ledger-driven,
  delta-only; Sonnet per user's model policy).

## 4. Top risks

| Risk | Mitigation |
|---|---|
| Zero-commit mega-tree across multiple sessions | per-phase patch checkpoints; MANIFEST |
| **Fork = permanent parent-cluster admin credential (CA/token reuse, review F1 — the blocker)** | P0 spike d; fork regenerates PKI, CA preserved for migrate only (02 §4, 04 §4) |
| Fork carries kine Secrets despite "empty map" invariant (F2) | labeled-secret scrub + ROLE rewrite in fork identity-rewrite; RepoRuntime contract test |
| Failover breaks on taint eviction / STS never-force-deleted (F3) | codified fence→delete-Node→attach→relabel sequence (02 §3) |
| Locally built images lost on fork/migrate (F4) | datastore-backed registry, not ctr-import (04 §7b) |
| No CSI/VolumeSnapshot cuts off Helm/operator/velero (F6) | thin node-local CSI in P3; P1 layout CSI-adoptable |
| PSA restricted breaks charts / opt-down reopens hostPath (F7) | ValidatingAdmissionPolicy backstop (02 §8); P0 verify baseline |
| Folders-on-BTRFS = no quota, statfs lies (F8) | per-volume LUKS images (P1); `ds-control` default |
| "proxy-only" NetworkPolicy false under flannel SNAT (F9) | P0 spike e datapath; ingress-only stated |
| `default`-datastore vs name-uniqueness contradiction (R2-F1) | placement tagged union; implicit defaults never enter the registry |
| Derived `-m` routes on stale cached attach state (R2-F2) | spec/status split; state = verified hint; `config reconcile` |
| **Encrypted-mode persist DESTROYS plaintext cluster/provider/strategy records (R2-F3, confirmed in current code)** | unified persist + per-field encryption in P1 config v3; latent until then (avoid master-password mode with clusters) |
| Live configs misread after reshape (R2-F6) | schemaVersion 3 + one migration, P0-specced, P4-shipped |
| Ceph pre-Squid → no group-snap clone | P0 spike a; fsfreeze+per-image fallback or newer cephadm pin |
| e2e-coverage gate reds as bridge functions change | per-function e2e updates inside each P1/P2 task's DoD |
| CLI reshape churn breaks i18n/cli-docs/skill/snippet gates | regen + snippet sweep are P4 gate items |
| Deleted machinery still referenced (renet dead-code gate) | delete ledger executed with `check:ci-renet` after each area |
| examples-docker CI job >60 min | P5 timings; trim 14/17 first |
| Feature-layer scope creep stalls core | P3 blocked on P2 gate |
| BTRFS-in-RBD double-CoW write amplification + dm-snapshot overlay fill on allocation churn (F10) | P0 spike f: dm-thin vs dm-snapshot on BTRFS patterns |

# 09. Implementation Program: Phases, Gates, Operations

This is the execution plan. **P0 through P3 are DONE, gate-reviewed, and proven live.**
P4 through P7 remain. If you are executing P4 onward with no prior context, read
`README.md`, then this file, then `spec/10-p3-gate-review.md` (which carries the
authoritative P4 carry-in list), then `06-cli-reshape.md` and `spec/03-cli-contracts.md`
(which are P4's actual contract).

## 0. Operating rules (non-negotiable)

1. **NO commits, pushes, PRs, or `git add`** by any agent. The operator commits the tree
   himself; HEADs moving under his authorship is sanctioned and expected. Verify authorship
   with `git log --format=%an` if a commit appears. An agent-authored commit is an incident.
   Per-phase safety: `git diff` patches into
   `~/.claude/projects/-home-muhammed-monorepo-console/checkpoints/` (console and
   private/renet separately, plus a tarball of untracked files).
2. **Local validation for everything** (CI is expensive): `go test ./...` (renet), vitest
   (packages/cli), real VM sessions, the examples harness. Evidence (transcript or log path)
   required at each gate. Every claim of "works" must have been executed.
   **P3 sharpened this rule**: unit-green predicts nothing in this codebase. Four
   feature-breaking product bugs survived unit tests AND two live campaigns, and fell only to
   end-to-end execution. Code that has never been run to completion is the highest-risk class
   in the tree, regardless of its test coverage.
3. **Models**: Fable = P0 spec, group-snap/identity seams, phase reviews, gnarly debugging.
   Opus = bulk Go/TS implementation, examples, CI YAML, harness, English docs.
   Sonnet = ALL naturalization/translation batches.
4. **User prerequisites before launching agents** (ancestry-verified overrides cannot be set
   later): `export REDIACC_ALLOW_GRAND_REPO='*' REDIACC_ALLOW_CLUSTER_OPS='*'`;
   passwordless sudo for virsh/virt-install; roughly 20GB+ free RAM and disk for the 6-VM fleet.
   Also `REDIACC_SKIP_MACHINE_ACTIVATION=1` on every call against ops VMs.
5. Local dev conventions: use `./rdc.sh` (hooks block direct cli-bundle invocation);
   renet builds stay `--nolicense`; ops fleet on `renet11`/192.168.111, cluster work on
   `renet12`/192.168.112; VMs persist, so `ops down` at phase ends; sleep >20s is hook-blocked
   (use background watch patterns).
6. **Agent process rules learned the hard way in P3** (recorded because each one nearly cost
   correctness):
   - A `SendMessage` abort **cannot** preempt a mid-turn agent. Two agents shared one live
     environment for roughly 40 minutes and it was luck, not design, that prevented a
     collision. Replacement agents must HOLD for an explicit GO before their first environment
     mutation.
   - Absence of transcript writes is **not** evidence of agent death. It was read that way
     twice and was wrong both times, producing two false ownership flips. Judge liveness from
     the agent's task output, not from file mtimes.
   - Put the exit marker INSIDE the watched log, and write the completion note in the same
     call that launches the follow-up operation. Completion-boundary stalls cost this program
     several hours of wall time.

## 1. Phase map

```
P0 spec+spikes   DONE   APPROVED-WITH-RULINGS    spec/00-gate-review.md
P1 renet core    DONE   PASS-WITH-NOTES          spec/07-p1-gate-review.md
P2 cluster       DONE   PASS-WITH-NOTES          spec/08-p2-gate-review.md
P3 features+CSI  DONE   PASS-WITH-NOTES (cond.)  spec/10-p3-gate-review.md
........................................................................
P4 CLI reshape   NEXT   (under operator hold at time of writing)
P5 examples      TODO
P6 CI            TODO
P7 docs+i18n     TODO
EXIT             TODO   additionally blocked on B1 and B2 (see section 2)
```

Sequential at gate level. WITHIN a phase, Opus agents parallelize per package area, example
batch, or locale. Every phase ends with validation evidence, a patch checkpoint, and a Fable
review.

---

### P0: Spec + blocking spikes [DONE] (APPROVED-WITH-RULINGS)

Produced `spec/01` through `spec/05` plus six spikes (a-f). Review: `spec/00-gate-review.md`.

**Two rulings from that gate overrode this suite and are folded in throughout:**

- **R1: mount path is `/mnt/rediacc-ds/<name>`** (sibling scheme), NOT the suite's original
  `/mnt/rediacc/ds-<name>`. The nested scheme put every named mountpoint inside the default
  datastore's own BTRFS mount, so a named attach would have required the default mounted,
  `detach default` would have hit EBUSY under any named mount, and default-pool exhaustion
  would have broken named attach. Exactly the blast-radius coupling that `ds-control` exists
  to avoid. Every property the suite wanted from the path survives the sibling scheme.
- **R2: the leaf count is 162 current to 153 target**, per spec/03's enumeration. The
  "~90 leaves" figure that appeared in the original README and 06 was **wrong arithmetic and
  is retired**. It was never a target to hit by cutting scope.
  **[SUPERSEDED 2026-07-13 by spec/03 §0 and ruling Q10: the COUNT is retired too.]** R2's
  own replacement numbers failed the same way: the 162 baseline was off by one (spec/03 §6.7's
  header contradicted the table beneath it), and operator commits moved the live tree by 19
  commands within days. **The MAPPING is the contract, not the count**: every command in the
  live tree carries a disposition row in spec/03 §6, and every row resolves to a real command.
  That is mechanically checkable against `command-tree.json` and, unlike a number, cannot be
  satisfied by accident. Descriptive only, no contractual force: ~183 invokable commands today,
  landing near 165. The honest simplification claim does not depend on a number and is
  unchanged: the DAILY surface consolidates (config 57 to 25, repo plumbing under `repo admin`,
  five backup surfaces unified).
- **C1, volume layout**: images at `repos/<repo>/volumes/<pvc>.img`, with mounts **outside**
  the repo folder at `<ds-mount>/mounts/volumes/<repo>/<pvc>/`. A live mountpoint inside the
  reflinked unit would make `cp --archive --reflink=always` either fail or byte-copy decrypted
  plaintext into the fork.

Spike outcomes that changed the design: dm-thin (not dm-snapshot) is the `--writes local`
overlay engine (spike f); the NetworkPolicy allow-proxy rule uses an **in-cluster leg**, not an
ipBlock (spike e); and spike d found that a bare `tls/` removal is **not enough** to re-mint the
PKI, because kine's `/bootstrap` restores the parent CA byte-identical. The real fork PKI
procedure is the **8-step scrub** specified in `spec/05` §3, which is what was built.

Raw spike transcripts were lost in the 2026-07-11 reboot. Their verdicts survive in the specs.

### P1: renet storage core [DONE] (PASS-WITH-NOTES)

Review: `spec/07-p1-gate-review.md`. Delivered the `RepoRuntime` interface plus its shared
contract-test suite (20 docker + 15 kube contract tests), the named multi-datastore registry
with create/attach/detach/fork/snapshot and the `--writes` contract, RBD **group snapshots**
proven live on Ceph Squid 19.2.4, the k8s repo-as-folder model with per-volume LUKS images and
static `local` PVs behind a no-provisioner/WFFC StorageClass, the per-namespace default-deny
NetworkPolicy and the hostPath/hostNetwork ValidatingAdmissionPolicy, the delete ledger
(ceph-csi, RADOS namespaces, per-PVC images, the whole teardown-leak apparatus), and
**config schema v3** including the unified persist path with per-field encryption that fixed
the confirmed encrypted-mode data-loss bug (R2-F3).

### P2: cluster layer [DONE] (PASS-WITH-NOTES)

Review: `spec/08-p2-gate-review.md`. Delivered the F1-F8 fork PKI re-mint with a fail-loud
CA-fingerprint refusal, the anchor model (`ds-control-<cluster>` embedded control plane), the
membership verbs (`cluster join` / `cluster evict`), and the node graceful shutdown/boot
lifecycle.

The review's most valuable finding was a contradiction: the composed new-model fork and migrate
did **not** exist in product code at review time. They existed as renet primitives plus a hand
battery script, while `rdc cluster fork` still ran the pre-program recipe and called
`kube_identity_rewrite` **without** `operation=fork`, silently defaulting to the CA-preserving
migrate arm. The verb named "fork" was producing forks that carried the parent CA: precisely
the F1 hazard this program exists to close. That was fixed during the review, and the composed
orchestrator became P3's mandatory first wave. Nine carry-ins were handed to P3.

### P3: feature layer + thin CSI driver [DONE] (PASS-WITH-NOTES, conditional)

Review: `spec/10-p3-gate-review.md`. This was the largest phase and it is where the design met
reality.

**What shipped:**

1. **The cluster fork/migrate orchestrator in product code** (`services/cluster/cluster-fork.ts`):
   `forkCluster` (group snap, clone, record ferry, adopt on dest, attach, identity rewrite with
   PKI re-mint and secret scrub, fresh agent rejoin) and `migrateCluster` (in-Ceph fenced remap
   with adopt-before-down ordering, dest verify, health gate, and rollback to the intact source).
2. **`cluster rehearse`**: an ephemeral secretless fork behind a health gate, discarded on both
   the success and failure paths, delegating to `forkCluster` with `role: rehearsal`.
3. **`repo replicate`**: full CRUD (create / status / remove), snapshot then N fork-attaches
   with `--writes local`, generated PVs and Services.
4. **The release ladder**: rung 0 (automatic undo snapshot before any release verb) plus canary
   weight templating, served by renet's router as a Traefik weighted service.
5. **dm-thin overlay auto-grow**, wired to the storage-maintain timer.
6. **The thin node-local CSI driver** (`csi.rediacc.io`), specified in `spec/09-csi-driver.md`.
   Host-side systemd everything, **zero container images**, self-registering with no
   node-driver-registrar. csi-sanity conformance went 21/58 to 43/7 to **48/50**, with the two
   residuals ruled as documented deviations (**CSI-DEVIATION-1**: an over-long volume name is
   cleanly rejected rather than truncated, because the kernel caps device-mapper names at 128
   chars and CSI permits 128-char volume names, so the two cannot both be honoured;
   **CSI-DEVIATION-2**: CreateSnapshot idempotency is size-proxy, not provenance). Enablement is
   automatic: it folds into `kube install` (control plane) and `datastore attach` (node units and
   the per-datastore StorageClass), and out of `datastore detach` and `kube uninstall`.
7. **The e2e rewrite**: suites 15, 16, and 17 rebuilt on the new model.

**What P3 proved live** (four independent fork proofs, one dedicated migrate leg, one CSI
conformance window, three e2e suites): see the README's "What is proven live" table. The
headline is that whole-cluster fork with data included, PKI re-mint, secret scrub, and an
undisturbed parent is now a repeatable end-to-end test, not a design assertion.

**The two EXIT-blocking gaps the gate refused to paper over:**

- **B1: P3's own feature layer has never been executed.** `repo replicate`, `cluster rehearse`,
  and the release ladder are real, complete, wired, unit-tested code (the reviewer specifically
  hunted for stubs and for the #26 zero-caller pattern and found neither). But not one of them
  has ever run against live infrastructure. Zero VM transcripts, zero e2e harness methods. The
  gate letter says "VM transcript **and** unit coverage per feature"; three of P3's four named
  features have no transcript. Against this phase's own headline result, never-executed code is
  the highest-risk class in the tree.
- **B2: no stock Helm chart was ever installed against the CSI driver.** The gate letter names
  one; the word "helm" appears in zero live transcripts. The live battery used hand-rolled PVC
  and Deployment manifests. A stock chart is what exercises a **StatefulSet's
  `volumeClaimTemplates`** (generated PVC names, ordinal pods) against WFFC and
  `storageCapacity`, which is materially different plumbing from a static PVC and is the entire
  F6 ecosystem-compatibility claim that justified building CSI at all. A hand-rolled manifest
  cannot demonstrate it, by construction. The VolumeSnapshot arm **is** proven.
- **B3: "e2e passes locally" does not hold as written.** Suite 15 is 7/7, suite 16 is 11/12,
  suite 17 is 6/7. Every functional claim is green. The two reds are teardown-only (#29, #30)
  with self-diagnosing probes already wired, so the next run names the holder rather than costing
  a blind cycle.

Neither B1 nor B2 blocks P4 (the CLI reshape is orthogonal to both). Both are cheap: they
discharge inside one bounded live window, and B2's marginal cost over B1 is near zero once a
cluster is up.

---

### P4: full CLI reshape [BUILT 2026-07-13 — awaiting gate review]

**As-built, measured, not estimated.** The shipped tree is transcribed in `06-cli-reshape.md` §1
(and `scripts/check-design-tree.ts` holds it there, both directions). The per-wave deltas are
`spec/03` §10 (w1, addressing), §11 (w2a, config exodus), §12 (w2b, repo family), §13 (w4,
surface closure).

| Measure | Value |
|---|---|
| Contract commands | **164** (93 machine-plane, 51 config, 20 other) |
| proxyCapable | **82** |
| Interactive | 9 |
| CLI unit tests | 1859 across 132 files |
| Shared unit tests | 533 across 29 files |
| Console coverage | 193 |
| CLI i18n | English FINAL; **225 keys × 12 locales** outstanding (185 missing, 40 reworded) |

**Green at hand-off:** `tsc` 0/0 (shared + cli), shared build, `check:ci-cli-contract`,
`check:ci-command-planes`, `check:ci-console-coverage`, `lint:unused` (knip), `biome format`,
the quality-gate suite, and `check-cli-docs` everywhere except the sanctioned red below.

**Sanctioned red:** `validate-docs-cli-usage` — 309 violations under
`packages/www/src/content/docs/**`, deferred to P7's docs rewrite (editing 60 English + 772
locale files twice is waste; precedent is the P3 i18n deferral). Every other surface the
validator covers is at zero, including `.ci/tutorials` (which was FAILING AT RUNTIME and which
no gate had ever looked at).

**What the phase actually bought, beyond the rename.** Six defects and four broken validators,
every one of them found by refusing to accept a claim that could not fail:

- **#51** (data-loss class): `repo admin archive {list,restore,purge}` was `proxyCapable`. A
  proxied `archive purge` would have permanently deleted the PROXY HOST's archived records.
  Found because a count moved and someone asked why instead of editing the number.
- **The policy deny glob fails OPEN**, demonstrated against the real evaluator: a rule denying
  `repo takeover` silently permits `repo promote` after this phase renames it. The executor now
  refuses such a document.
- **`term_exec` emitted an argv the CLI rejects** and the entire MCP suite stayed green, because
  it asserted the argv a tool BUILDS and never that the CLI ACCEPTS it.
- **32 MCP leaves were unclassified** and structurally invisible to a registry-keyed check.
- **`.ci/tutorials` (337 `rdc` calls) was in no validator glob**, and once globbed, the scanner
  still read no shell line. Covering a file is not reading it.
- **The docs `--fix` map was backwards** and would have rewritten correct docs into broken ones.

Two gates now exist that did not: the per-leaf plane rule (`check-command-planes.ts` Rule 3) and
the stale-policy-glob refusal (`shared/src/policy/stale-globs.ts`). Both were **proven red before
being trusted**.

#### The original plan (kept for the record)

Implement `06-cli-reshape.md`; **`spec/03-cli-contracts.md` §6 is the contract** (the leaf
count is retired: see the R2 correction above and spec/03 §0). Re-annotate gating metadata.
Regenerate renet-contract types, cli-docs, the skill reference, and the validate-cli-examples
ground truth; update every documented `rdc` snippet (CLAUDE.md, docs, skills) in the same
phase. CLI i18n English strings plus 12-locale naturalization (via the delta pipeline; kimi is
the pipeline default, Sonnet only where kimi reads awkward).

#### ★ TASK ZERO, before a single command is renamed: the ref concept

The CLI contract is **options-only** and `walkContractCommands()` **hard-throws** on the first
positional argument, because all three contract consumers (the web console, the `--proxy` thin
client, the executor daemon) serialise a command as flags alone. spec/03 §2.2 makes a
positional the primary name of every leaf, so the first rename would red
`check:ci-cli-contract`, `check:ci-command-planes` and `plane-coverage.test.ts` at once.

**Ruled (R-P4-1): build it.** And the deliverable is a *ref concept*, not just serialisation:
the console's resource pickers and its **computed action-bar buttons** bind through
`machineOption`/`repoOption`, i.e. through `--name` and `--machine`, the exact flags the
reshape deletes. Emit positionals without rebinding those onto the ref and the CLI works while
the GUI silently empties. Five modules across two repos; acceptance test = a positional leaf
that walks the contract, crosses the `--proxy` wire, and renders as a resource picker with
`check:ci-console-coverage` green. Full statement: spec/03 §2.0.

#### The other two rulings that ADD scope (2026-07-13, spec/03 §9)

- **The detached-jobs workstream (R-P4-2v2, twice-ruled and merged).** A job is
  **executor-born**: the serve dispatch sets `ExecuteOptions.detached` itself for detachable
  commands and keeps following (the container tier sleeps after 2-5 minutes idle; client
  disconnect = detach, not cancel). Direct CLI gets a **global `--background`/`-b`**,
  fire-and-forget (job id + resume hint, exit 0; needs a no-follow mode that does not exist).
  `repo up`/`repo fork`'s `--detach` is renamed **`--no-wait`** (reopens and supersedes U6);
  the word "detach" leaves the flag vocabulary. The parallel session's verified handoff
  (`reports/handoff-detached-jobs.md`) supplies the design and an 8-step ordering; its first
  four steps are runtime no-ops touching only executor/job files (they can run in parallel
  with task zero, and step 2 fixes the LIVE `--proxy cluster fork` bug #31), while steps 5-8
  share task zero's contract files and fold into it as one contract-shape change. Two
  silent-corruption bugs (#32 stdout discard, #33 license/identity bypass) must land before
  anything sets `detached`.
- **The policy re-key (spec/03 §4.11).** Org permission policies allow and deny commands by
  **glob on the command path**, inside the encrypted config, evaluated by both the executor and
  the console. P4 renames every path. A stale `allow` fails closed; ⚠ **a stale `deny` fails
  OPEN** and silently stops denying. P4 re-keys every glob and builds the missing gate.

**FIVE-per-leaf classification** (not three — the list grew twice in 2026-07-13's analyses).
Every leaf of the new tree carries five orthogonal, path-keyed classifications, and P4 must set
all five deliberately rather than inheriting them. Ordered by how a mistake fails, worst first:

1. ⚠ **Policy globs** — fails OPEN on a stale `deny`. No gate today.
2. ⚠ **Guardrails** (`grandGuard` / `forkBlocked` / `agentBlocked`) — silently stop enforcing on
   a missed rename. No stale-entry gate.
3. **Plane** (`machine` | `config` | `other`) — inherited by longest path prefix, so **every move
   is an implicit plane re-declaration**; a move into a machine-default noun silently flips
   `proxyCapable` to `true` and every gate stays green.
4. **MCP** (`mcp` XOR `mcpExcludeReason`) — stale entries caught loudly.
5. **Ref binding** — silent: no binding means no resource picker and no action button.

Detail: spec/03 §4.9, §4.10, §4.11, §8.3. Gates that enforce parts of this today:
`check:ci-cli-contract`, `check:ci-command-planes`, `check:ci-console-coverage`.

Closing step: the **MCP alignment gate**: apply the parked tree-walk coverage patch
(`~/.claude/projects/-home-muhammed-monorepo-console/parked/mcp-coverage-gate.patch`; it found
56 drifted commands on the old tree) and classify every leaf of the new tree.

#### The authoritative P4 carry-in list

`spec/10-p3-gate-review.md` §"AUTHORITATIVE P4 CARRY-IN LIST" is the authority; this is the
summary. P4 must be briefed from it.

**1. The shared node-side teardown primitive, over the HOLDER TAXONOMY.** This is the
campaign's cleanest conceptual result and the single most useful thing P4 inherits. Four
distinct classes of thing can hold a datastore open. Each is invisible to the others'
diagnostics, each needs a different remedy, and they must be handled **in this order**:

  - **(a) Kernel submounts.** The trap: k3s containerd overlays live at `/run/k3s/...`,
    **OUTSIDE** the datastore path, and hold it busy through their `lowerdir` OPTIONS. An
    "unmount everything under `<mount>`" filter misses them entirely. Match the mount string
    anywhere in the `/proc/mounts` line, deepest-first.
  - **(b) Host processes.** The CSI trio, whose socket and `--kubelet-root` live INSIDE the
    datastore. This was **#26**, now fixed, but the primitive must own it rather than leaving it
    folded into two call sites.
  - **(c) Device stacks.** A per-volume LUKS loop plus dm-crypt left open, with no mountpoint to
    find. Its **cause** was **#28** (now fixed): `repository down` was dying at the namespace
    delete and never releasing the stack.
  - **(d) An open dm device with no userspace owner** (open-count above zero after a successful
    unmount, no mount, no loop, no process). This is **#29**, still unexplained.

  Every storage-releasing verb (`cluster evict`, `datastore detach`, `cluster migrate`,
  `kube uninstall`, `repository down`) must route through this one primitive.

**2. #20 (narrow scope).** `cluster evict` does no node-side teardown, so the evicted node's k3s
unit keeps running and a same-machine re-join port-collides. Note: the "4-witness submount
generalization" of #20 was **wrong and is withdrawn**; the release refusals were #26.

**3. #25: the dual agent-join paths.** `cluster create` builds per-node agent repos
(`createNodeImage`) and then passes the **control** datastore's mount to their `kube_join`, so
the repo goes unused and the data-dir lands on the root filesystem, contradicting its own
comment. Meanwhile `cluster join` uses the per-node repo. Two join paths, two behaviours, dead
state. Framing already flagged: **agents are a disposable cache** (02 §1), so the vestigial repo
may be **deletable** rather than the mount fixed.

**4. F1: the kube-arm `repo fork`.** The product's CT-11 guard **refuses** `repository_fork` on
a repo whose datastore is cluster-attached, while design 06 §3 specifies kube repo fork. Ruled a
**design contradiction, not a bug**; suite 15 test 6 was flipped to a NEGATIVE test asserting
today's refusal. P4 implements the positive path per 06 §3, revises the CT-11 error text, flips
the test, and fixes the spec/06 §15 wording-vs-suite mismatch.

**5. #29 and #30: the two teardown root causes** (also B3). #29: after a clean unmount,
`dmsetup remove <fork>-cow` returns EBUSY for 27 seconds of retries; not a mount, not a process,
not a loop, and **not** btrfs's scanned-device cache (refuted by controlled experiment). #30:
after a cluster **migrate**, the repo namespace refuses to terminate, while an identical `down`
on a never-migrated cluster finishes in seconds. Migrate-specific, distinct from #28.
Post-failure probes are wired in both.

**6. #22.** `cluster destroy` leaves a stale `state.clusters.<name>.memberIds` orphan, so a
same-name recreate reuses the stale memberId ledger. One-line fix; trace the recreate
implications first.

**7. Carry-in 6: attach-time auto node-label.** A node-pinned `local` PV will not bind unless
the node carries `rediacc.io/ds-<name>`, and `datastore attach` does not stamp it. **Fold the
label into renet's `datastore attach`**, mirroring the symmetric CSI fold, and strip it on
detach. Do NOT put it in CLI porcelain: P4's own reshape would throw that away. Do NOT defer
past P4: the failure mode is **silent** (pods sit Pending forever with no error naming the
missing label).

**8. Multi-node worker-attach CSI wiring** (spec/09 §14 item 12): worker nodes currently no-op
on the auto-enable fold.

**9. No standalone bare-machine provision.** Fork and migrate destinations require a
helper-cluster-then-`kube_uninstall` dance to produce a bare machine.

**10. Test-mode dispatcher flag drift.** `functions once --test-mode` flags are hand-listed and
lagged every redesigned verb (harness bugs H1, H2, and H3 were all this class). Derive the
dispatcher flags from the bridge `ParamDef` registry so they cannot drift.

**11. Minor sweeps still open** (from spec/08 carry-in 9): the stale self-heal comment at
`node_lifecycle_unit.go:87`; reconsider the `--operation` default (recommend required, no
default); a teaching error naming `REDIACC_SKIP_MACHINE_ACTIVATION=1`; and `installCeph`'s 2-OSD
`size 2 / min_size 1` accommodation must stay **test-only** and never become a product default.

**12. i18n.** The 12 locales x 58 untranslated CLI-surface strings are deferred to **P7 by
standing ruling**, because P4 reshapes exactly that surface and naturalizing now is throwaway.
**P4 must not try to clear it. P7 must.**

**13. From spec/07, unchanged:** the latest-magic resolver, the composite-key view, the
`takeover` to `promote` CLI rename, and the D3 baseline re-keying in P7.

**14. Config v3 handoffs.** The command reshape itself is P4's subject. The one located handoff
note is that the legacy per-node repo mount "is P4 porcelain for the cluster-repo path", which is
the same object as #25 above.

#### CLI-reshape prerequisites

Two structural blockers must be settled before the reshape lands: the **positional-argument
blocker** and the **plane model**. Detail lives in `06-cli-reshape.md`.

GATE: `./rdc.sh --help` tree matches 06; MCP coverage test green on the new tree; vitest, lint,
and the CLI i18n gates green; USER reviews the tree.

### P5: examples on the new surface [TODO]

Full catalog per 07 (§1-2 conventions are locked, including the `config init --name` footgun);
harness plus gate opt-ins (07 §3-4). Order: harness + 02 + 10 first (proves conventions), then
parallel batches; track 3 after its cluster examples' commands exist; VM access serialized by
harness flock.

GATE: `run-examples.sh --all --continue` full PASS locally, teardown-verified; per-example
timings recorded (they feed the CI-set trim).

### P6: CI [TODO]

`ci-examples.yml` (07 §5) plus the ci.yml `examples-tests` job and the THREE ci-complete touches;
adjust ct-tests job envs where fleet shapes changed. **The three kube e2e suites (15/16/17) now
exist and pass functionally, and they are P6's CI candidates**. See 07 §7 for their state, the
two known teardown reds, and the harness lessons that must not be re-learned.

Note the ceiling recorded in rediacc/console#521: the concurrent multi-cluster scenarios (fork
with parent and fork live at once; cross-site migrate with two ceph clusters) **do not fit the
16GB GitHub-runner budget**. They fit locally. Deliberate CI design for them is deferred to that
issue and is not a program blocker.

GATE: all workflow-affecting local gates green; CI-mirror runs PASS.

### P7: docs + i18n [TODO]

Per 08: rewrite the English pages track by track, embedding example files (build the embed plugin
first); the concepts page from this suite's 01-03; blog rewrite; renet datastore README refresh;
regenerate the search index and the CLI reference; Sonnet re-naturalization batches; restamp
`sourceHash`/`sourceCommit`. **P7 owns the deferred 12 x 58 CLI-locale naturalization.**

Docs must use the **measured** numbers from the README's evidence table. No estimates, and no
recycling of the pre-program figures in 01 §6.

GATE = program exit: see §2.

## 2. Program exit criteria

1. **B1 discharged**: a VM transcript for `repo replicate`, `cluster rehearse`, and the release
   ladder (rung-0 undo snapshot, canary create, weight flip end to end through the router's
   weighted service). This is the gate's explicit "VM transcript per feature" requirement, and
   it is the only P3 deliverable class with zero live evidence.
2. **B2 discharged**: a stock Helm chart against the CSI driver (`groundhog2k/postgres` per
   spec/09 §12.1, `--set storageClass=rediacc-csi-<ds>`). Assert the StatefulSet's
   `volumeClaimTemplates` PVC binds, the pod lands on the datastore's node (WFFC plus
   `storageCapacity`), and a VolumeSnapshot backup/restore round-trips against it.
3. **B3 discharged**: suite 16 test 12 (#29) and suite 17 test 7 (#30) green.
4. Full example suite PASS on the new architecture (local and CI-mirror mode).
5. Cluster fork / migrate / rehearse / replicate transcripts with timings. (Fork and migrate:
   done. Rehearse and replicate: B1.)
6. `npm run ci` diff versus the P0-recorded baseline: only pre-existing reds remain. Renet gates
   (check:ci-renet, dead-code, e2e-coverage, types-regen) green. Vitest green. i18n,
   search-index, workflows, and cli-examples green.
7. This design suite updated to as-built (this pass), plus a final report with timings, spike
   outcomes, and the product gaps discovered en route (candidate issues listed, NOT filed without
   the user asking).

## 2b. The bug ledger

**30 bugs confirmed**, verified at the P3 gate by file and line. Full narrative in the program
MANIFEST; this is the accounting.

| Class | Count | Bugs |
|---|---|---|
| **Fixed and live-validated** | 23 | #2 (ops-up 600s cap), #3 (rbd clone-format verify), #4 (double ceph bootstrap), #6 (node-boot systemd deadlock), #7 (dest ceph config + tooling), #8 (dest-k3s collision refusal), #9 (ceph pool size/min-size), **#10 (bridge-relay `[fn]` prefix broke every `JSON.parse` of a captured bridge-fn stdout. Systemic: the product two-cluster fork could never have run live as written)**, #11 (stale kubeconfig path), #12 (`repo create --cluster` did not register), #13 (KVM MAC collision), **#14 (fork datastore record registered only in the SOURCE machine registry. The architectural blocker; fixed by the new `datastore adopt` verb)**, #15 (dest prereqs), #16 (dockerd bounce killed the ceph mon), #17 (double pool + pg-budget race), #18 (migrate record propagation), #19 (migrate dest seeding), **#21 (`CreateK3sSystemdService` never ENABLED the unit, so rebooted nodes never restarted k3s. A production-reboot killer)**, **#23 (path-form `--datastore` discarded the descriptor's authoritative Name and hardcoded "default", so PVs would never bind. Silent and feature-breaking)**, **#24 (`applyPersistedManifests` applied repo manifests RAW, bypassing RenderManifest: no Service ever got its router annotations, and the security lint was bypassed)**, **#26 (the product started host CSI daemons it never stopped; `RemoveNodeUnits` existed with ZERO callers, so every storage-releasing verb was refused with no mount holder to find)**, #27 (`dmsetup remove` raced udev), **#28 (`kubectl delete namespace` under a 30s exec timeout against a 30s pod grace period: a guaranteed collision that half-downed essentially any real kube repo)** |
| **Open, documented, handed to P4** | 5 | #20 (evict does no node-side teardown), #22 (stale `state.clusters.memberIds` on destroy), #25 (dual agent-join paths / vestigial per-node agent repo), #29 (fork-discard dm EBUSY, holder unnamed), #30 (post-migrate namespace will not terminate) |
| **Infrastructure / process, not product** | 2 | #1 (SSH under load), #5 (renet license contamination via a bare `build.sh`; the remedy is the `--nolicense` discipline) |

Plus **F1**, ruled a **design contradiction rather than a bug** (the CT-11 guard refuses kube-arm
`repo fork`; design 06 §3 specifies it), carried to P4 as a work item.

The four bold entries in the fixed column (#23, #24, #26, #28) are the feature-breaking ones the
e2e leg found after unit tests and two live campaigns had all missed them. #10 and #14 are the
two that would have shipped a fork that could never run.

## 3. Verified repo facts a new session must not rediscover the hard way

- `npm run ci` is now **54 checks**. Two are new and relevant to P4:
  **`check:ci-cli-contract`** and **`check:ci-command-planes`**. A reshape that ignores them
  reds the gate.
- `full ops up` = bridge .1 + workers .11/.12 + ceph .21-.23, Ceph auto-provisioned
  (roughly 10 min); `--basic` = bridge + worker 11; VMs persist; renet escalates via `sudo virsh`.
- ops VMs are NOT registered as machines automatically; scripts do it
  (tutorial pattern: `.ci/tutorials/lib/tutorial-helpers.sh`, `tutorial-forking.sh`).
- `config init` ignores `REDIACC_CONFIG`; always pass `--name examples` (07 §2 footgun).
- Cluster RAM is env-tunable through `rdc cluster create` (VM_RAM/VM_RAM_WORKER/VM_RAM_CEPH pass
  through to renet opsconfig; floor 2048; bridge fixed 1024).
- `check:ci-e2e-coverage` greps packages/e2e-tests for every generated renet function name (raw
  `resource_verb` or spaced `resource verb` both count). A new bridge function without an e2e
  reference reds it.
- `check:ci-workflows`: SHA-pinned actions, no inline `script:`, secrets via env (no actionlint
  exists). New ci.yml jobs need the ci-complete THREE touches.
- `check:i18n` lives at the **repo root**, not in `packages/www`. Running it from the www
  workspace fails with "Missing script" and a wrapper masks the exit code. This cost the P3 gate
  reviewer a wrong first reading.
- The renet i18n baseline is **grandfathered at 2970** as of the P3 gate. Growth requires a
  sanctioned batch; the gate verifies the count arithmetically against `baseline.json`.
- shfmt/shellcheck scopes exclude a bare top-level `examples/` (opt-in edits in 07 §4); the
  eslint `**/*.ts` glob does NOT exclude it; biome and knip ignore non-workspace dirs.
- Docs freshness: an English docs edit stales 12 twins plus its sourceHash; a new page needs
  twins or a pending-list entry; any docs or blog change requires a search-index regeneration
  (08 §4).
- Agent hooks: direct cli-bundle invocation is blocked (use `./rdc.sh`); ssh/docker to
  192.168.111.* is allowlisted; `sleep` over 20s is blocked; scp and manual renet deploy are
  blocked.
- The i18n pipeline for locales is `private/growth/i18n_pipeline` (ledger-driven, delta-only;
  Sonnet per the model policy).

## 4. Top risks

The P0-P3 risks are discharged; they are kept here with their outcomes, because "the mitigation
worked" is itself evidence a future reader needs.

| Risk | Mitigation | Outcome |
|---|---|---|
| **Fork = permanent parent-cluster admin credential (F1, the program's blocker)** | fork regenerates the PKI; CA preserved for migrate only | **CLOSED, proven live**: fork CA differs, parent cert 401s on the fork. Spike d found the naive `tls/` delete insufficient (kine `/bootstrap` restores the CA); the real fix is the 8-step scrub in spec/05 §3 |
| Fork carries kine Secrets despite the "empty map" invariant (F2) | labeled-secret scrub + ROLE rewrite in fork identity-rewrite; contract test | **CLOSED, proven live**: injected AND third-party Secrets absent in the fork |
| Failover breaks on taint eviction / STS never force-deleted (F3) | codified fence, delete-Node, attach, relabel sequence | Built (02 §3) |
| Locally built images lost on fork/migrate (F4) | datastore-backed registry, not ctr-import | Built |
| No CSI/VolumeSnapshot cuts off Helm/operator/velero (F6) | thin node-local CSI in P3; P1 layout CSI-adoptable | **BUILT and conformance-tested.** Helm arm still unproven = **B2** |
| Folders-on-BTRFS: no quota, statfs lies (F8) | per-volume LUKS images; `ds-control` default | Built, honest `df` observed live |
| "proxy-only" NetworkPolicy false under flannel SNAT (F9) | spike e datapath | **In-cluster leg chosen** (namespaceSelector + podSelector; zero ipBlock) |
| **Encrypted-mode persist DESTROYS plaintext cluster/provider/strategy records (R2-F3)** | unified persist + per-field encryption in config v3 | **FIXED in P1.** Note: its regression guard (`persist-unification.test.ts`) went dark for a window during a later cli-to-shared config move and was restored |
| Ceph pre-Squid = no group-snap clone | spike a | Squid 19.2.4 deployed; group snap + clone-from-group-snap proven |
| BTRFS-in-RBD double-CoW amplification, overlay fill (F10) | spike f: dm-thin vs dm-snapshot | **dm-thin chosen**, with auto-grow wired to the maintain timer |
| **Unit-green does not predict live behavior** | live campaigns per phase | **CONFIRMED THE HARD WAY**: 4 feature-breaking bugs survived unit tests and 2 live campaigns. This is why B1 blocks exit |
| CLI reshape churn breaks i18n/cli-docs/skill/snippet gates | regen + snippet sweep are P4 gate items | Open (P4) |
| Deleted machinery still referenced (renet dead-code gate) | delete ledger executed with `check:ci-renet` after each area | Held green |
| examples-docker CI job over 60 min | P5 timings; trim 14/17 first | Open (P5/P6) |
| Concurrent multi-cluster validation exceeds the 16GB CI runner | rediacc/console#521 | Open, not a program blocker; the scenarios run locally |

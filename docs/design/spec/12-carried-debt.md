# Carried debt into P5 — the durable ledger

**Place this in the repo at `docs/design/spec/12-carried-debt.md` and commit it.** It exists because the P4 gate's finding F5 was that four of these items were recorded in no design doc, no spec, and no committed ledger — only in a session scratch file. Debt that lives only in a session's context is not debt, it is amnesia with a countdown.

Status at the P4 gate (2026-07-14). Bug numbering continues the program ledger, which stands at **87**.

## EXIT-blocking — must be decided before the CSI driver ships

### #87 — every dynamically provisioned CSI volume leaks its LUKS image, permanently
Live-proven, 100% leak rate (3/3 volumes: 3 orphaned `.img`, 3 open dm mappers, 6 live mounts, 0 reclaimed). Delete the pod + PVC and the PV stays `Released` forever; the datastore fills and never reclaims. There is no sweeper that recovers it.

**Root cause is the design, not a defect in it.** spec 09 §5 prescribes staging the LUKS device at a canonical mount (`<ds-mount>/mounts/volumes/<repo>/<vol>/`) *and* bind-mounting that to kubelet's `staging_target_path`. kubelet's `UnmountDevice` refuses to call `NodeUnstageVolume` while `GetDeviceMountRefs` sees a second reference to the same device — and that second reference is the driver's own canonical mount. It retries forever; `DeleteVolume` then correctly returns `FAILED_PRECONDITION`; the image is never reclaimed.

**Invisible by construction:** csi-sanity and the unit tests call `NodeUnstageVolume` directly, bypassing kubelet's precondition. Only a real kubelet refuses. Ruled out as a teardown-ordering artifact by a controlled pod-only probe.

**SPIKED AND DECIDED (see `reports/p87-design-spike.md` for the full consumer enumeration with file:line).**

**Ruling: option (a)** — stage the device ONLY at kubelet's `staging_target_path`; the canonical tree keeps holding volume **images as files**, not mounts. **(b) symlink and (c) reconciler are both REJECTED**: (b) breaks the static-PV path outright and does not even address the failure, whose cause is the *device's* mount-ref count, not the path's type; (c) cannot work from inside the driver at all, because kubelet's precondition runs *before* it calls `NodeUnstageVolume` — a reconciler would have to race kubelet by force-unmounting a reference out from under a live device.

**Why CSI dies and the static path does not** (the asymmetry that decides everything): both double-mount, but static PVs are served by kubelet's **in-tree local-volume plugin**, which never calls `NodeUnstageVolume` and therefore never runs `GetDeviceMountRefs`. Only the CSI flow carries that precondition. Our canonical mount is the one reference too many.

**Exactly two of the seven consumers need a real mountpoint, and NEITHER is CSI. Both are traps that would cause SILENT DATA LOSS if an implementer takes (a) naively:**

- **TRAP 1 — the static PV's `path:` must stay a mount.** `provisioner.go:170` → `kube.go:137` → `kube_templates.go:266` emits `local:\n path: <canonical mountPath>`. If that path stops being a mount, **pods write into an empty directory on the datastore filesystem — outside the LUKS image, in the clear, with no error at any layer.** Therefore (a) is a change to **`pkg/kubecsi/node.go` ONLY** (`MountPath: staging`, delete the bind-mount at `node.go:99`). An implementer who "removes the canonical mount" by editing `kubevolume` ships **unencrypted volume data**.
- **TRAP 2 — `syncParentVolumes` (`cmd/renet/repository_fork_kube.go:130-137`) would silently skip dynamic volumes on fork.** It `syncfs`'s each volume's *inner* ext4 before the reflink (syncing the datastore only flushes the `.img`'s blocks, not the dirty pages inside the volume's own filesystem — this was live-caught by suite 15 t6). Its global-sync fallback fires **only on a `ReadDir` error**. Verified cold: a repo with **any** static volume makes `ReadDir` succeed, so it syncs the static volumes, returns, and **never reaches the fallback** — while a dynamic volume, which under (a) has no canonical directory, is never synced at all. The fork then reflinks a `.img` whose ext4 was never flushed → **stale or empty dynamic-volume data in the fork, silently.** ~20 lines; **must land in the same commit as the staging change.**

**The enumeration (a) needs is already shipping in the sibling path:** `cmd/renet/datastore_volumes.go:81` enumerates volumes with `filepath.Glob(<repoDir>/volumes/*.img)` and never touches the mount tree — and `resolve.go:24` puts dynamic and static images in the *same* directory, so one glob covers both. Consumers 3–7 either enumerate by directory *name* (a glob yields the same names) or use MountPath as an "is it staged?" probe, for which `IsOpen()` on the dm mapper is strictly better: device-level truth, regardless of where the thing is mounted.

**The regression test must go through a REAL kubelet** (create pod → delete pod+PVC → assert the image is gone). Not csi-sanity — csi-sanity calls `NodeUnstageVolume` directly and therefore *cannot* observe this bug, which is exactly why it survived.

**Spec amendment owed:** `spec/09-csi-driver.md:322-327` justifies the canonical mount as letting "the sweeps operate on ONE well-known tree." **That rationale is already obsolete** — `volumes open/close` does not use the tree, and the one sweep that does reads it only for names. Amend it, or the next reader re-derives the double-mount from the spec and reintroduces the leak.

## Blocks the "stock Helm charts work natively" claim

### #84 — repo namespaces enforce PSA `restricted`; stock charts set no `seccompProfile`
Their pods are rejected at admission (`FailedCreate` ×13), even when they otherwise comply (runAsNonRoot, all caps dropped, readOnlyRootFilesystem). **Do not fix by weakening PSA to `baseline`.** Recommended: keep `restricted` and inject `seccompProfile: RuntimeDefault` for pods in repo namespaces via a mutating admission policy — preserves the security posture *and* makes the compatibility claim true. Product security decision; operator's call.

### Spec change owed: `09-csi-driver.md` §12
§12 prescribes proving CSI with the third-party `groundhog2k/postgres` chart. The proof does not need it: §12.1's three mechanisms (volumeClaimTemplates, WFFC + storageCapacity, snapshot → dataSource restore) are fully exercised by a self-authored ~15-line busybox StatefulSet with **zero third-party supply chain**. A third-party chart buys only the *compatibility* headline — and that claim is already falsified chart-agnostically by #83 and #84. Amend §12 to specify the self-authored proof.

## Fixed in the P4 wave (recorded so the fix is not re-litigated)

- **#83** — `repo create` never wrote `.rediacc/repo.json`, so CSI refused **every** dynamic PVC: dynamic provisioning was unreachable through the porcelain. The guard's comment claimed it tested *"is this a rediacc repo"* while it actually tested *"has this repo already been through the static-PV path"* — it measured a **side effect of the thing it meant to measure**. Fixed red-first, live-proven; the fix realigns the predicate with its stated intent and weakens nothing.
- **#85** — 2-OSD Ceph `cluster create` could never succeed: the global `osd_pool_default_size` was never set (so `HEALTH_OK` was unreachable) *and* the health gate's escape hatch was dead code (`grep -c … || echo '0'` emits **two** zeros, so its `== "0"` test can never be true). Note for posterity: fixing only the dead branch would have been **worse than the bug** — it would have converted a loud failure into a silent, permanently degraded cluster.
- **#86 (HALF-fixed).** Attach-time CSI enablement silently no-oped (a `Debugf`) on any node with no admin kubeconfig, while attach reported success.
  **CORRECTION — this ledger previously said "attach now FAILS loudly." That was WRONG, and it is worth keeping the correction visible:** the code does not fail. `cmd/renet/kube_csi.go:96-108` is a `log.Warnf` followed by a bare `return`; the exit code is unchanged and the warning text ends, verbatim, **"Attach itself succeeded."**
  **What P4 actually fixes is the SILENCE, not the outcome:** attach still succeeds and still mounts the datastore, but the skip is now a loud warning naming exactly what was skipped (StorageClass, node CSI units, topology label) and what it costs ("dynamic PVCs on this datastore will stay Pending"). **Ruled: warn-and-succeed is CORRECT** — the attach genuinely worked, and hard-failing would strand a mounted datastore behind a non-zero exit.
  The *feature* — CSI on a worker node — remains P5 (control-plane-mediated scoped mint; see below).
  **The lesson is the correction itself:** a debt ledger that describes behavior the code does not have is the same defect as help text that teaches a deleted command. The author of the rule broke the rule, and an agent reading the code caught it.

## Carried from earlier phases — still open

- **#68 / #82 — the adoption path.** The product can only manage the world it created; `repo replicate` is undriveable on any cluster the CLI did not provision. `replicate refresh` is excluded from MCP for this reason (it cannot run).
- **#79 — agent-node CSI.**
- **#30 — metrics-server APIService blocks namespace discovery.** Root-caused and *refuted* as a storage bug; the fix is one flag.
- **The 16 datastore-declaration bypass sites** (8 correctly silent, 2 design questions) — see `reports/p5-datastore-declaration-residual.md`.
- **kube size-license semantics.**

## P5 items opened by the P4 gate and the babysit

- **renet i18n baseline — THE NUMBER, WITH ITS WINDOW STATED (this ledger previously contradicted itself, and the gate reviewer caught it).**
  **TOTAL DEBT: 41 user-facing strings** (18 `fmt.Printf`, 11 `cobra.Short`, and the rest), measured against the **P3 gate's own baseline commit `c7e187a`** — independently confirmed twice. That is the number the P5 item is scoped to: **internationalize the 41.**
  **OF WHICH THIS PR ADDED 6** (measured against the pre-wave commit); the other **35 are pre-existing debt** this wave did not create and does not own.
  **BOTH numbers are true and they answer different questions. This ledger previously stated only the 6** — which made the debt look settled at ~1/7 its real size, so someone fixes six strings and calls it paid. **A number without its window is folklore; this entry is what that looks like when the folklore is your own.**
  They were baselined as though they were internal error wraps. renet's house style is `i18n.T` (288 vs 52 raw), so these are an anomaly. They are enumerated in the commit that re-based them. **Two P5 items:** internationalize the 41, and — the structural bug — **teach the gate to tell "internal error wrap" from "user-facing"**, because today it is green *because* they were laundered: it cannot fail for this reason by construction.
- **`noUncheckedIndexedAccess` is off**, which makes `map[key]` type as always-present while returning `undefined` at runtime. This made 14 real runtime guards (the exit-5 not-found path, the invalid-config-key rejection, several crash guards) look like dead code to the linter. Enabling it costs 194 type errors in `packages/cli` alone. Until then, "fixing" a `no-unnecessary-condition` warning in this repo can silently delete a load-bearing guard.
- **Deferred refactors** (suppressed with BLOCKERs, not fixed, to avoid refactoring product code inside an unmerged wave): `command-metadata.ts` 820 lines, `datastore.ts` 531, `machine/status.ts` 548 vs a 512 cap; 8 `sonarjs/cognitive-complexity` sites.
- **`runBatchParallel` deleted** — a fully-implemented parallel batch runner (with a Semaphore) that nothing called. If batch-parallel is wanted, wire it deliberately with a contract. It survives in the snapshot commit's history.
- **P7 deferrals, named with counts so they cannot be quietly forgotten:** `validate-docs-cli-usage` — 379 violations under `packages/www/src/content/**`, plus ~30 inherited em dashes; `check:i18n:docs` — 13 www locale doc files referencing CLI i18n keys the reshape deleted (gate scoped with a BLOCKER, not bulk-edited, because P7 rewrites them anyway).

## The thesis this phase kept proving

Every one of #83–#87 is the same species: **code that had never been run.** Not badly written code — *unexecuted* code. Unit tests passed, csi-sanity passed, two prior live campaigns passed, and the bugs sat there until a real user path walked through them. The corollary is now load-bearing for P5: **an assertion that cannot fail for the right reason predicts nothing** — csi-sanity calls `NodeUnstageVolume` directly and therefore *cannot* discover #87, no matter how many times it runs.

## #86 — CSI enablement on worker nodes (P5, design settled, evidence attached)

The silent no-op is fixed in P4 (attach now FAILS LOUDLY on a node it cannot enable, naming why).
The *feature* — CSI datastores actually working on a worker — is P5, and the design is already
decided, with the evidence:

**Why it no-ops today:** the CSI sidecars need Kubernetes API access, hence a kubeconfig, which is
minted via a CSR requiring cluster-admin. A k3s **worker has no admin kubeconfig**; only the control
plane does. So `findLocalClusterK3sMount` finds nothing and the enablement returns silently.

**REJECTED — ship the admin kubeconfig to workers.** It would place cluster-admin credentials on
every data node that mounts a datastore, destroying the exact property spec 09 §4 exists to protect
(the CSI path keeps credentials off the cluster). A security regression bought to make a feature work
is the worst trade available.

**RULED — control-plane-mediated scoped mint.** The code already anticipates it:
`MintSidecarKubeconfig(ctx, r, node, cluster, apiServerURL, caPEM)` takes the **target node** as a
parameter (`pkg/kube/csidriver/pki.go:40`) and mints `CN=rediacc-csi:<node>`, `O=rediacc:csi`
(`pki.go:87`, `objects.go:16`), bound to the scoped `rediacc-csi` ClusterRole — **never admin**. So
the control node can mint a scoped credential *for* a worker; nothing admin ever leaves the control
plane. Work: split `DeployNode` into a control-side half (apply StorageClass, mint the worker's
sidecar kubeconfig, stamp the node label) and a node-side half (install + start units), plus a
transport for the minted kubeconfig through the executor's existing secret channel, plus CLI
orchestration of the two hops.

**Sequencing:** do this WITH #87's node-side staging redesign, not before it. #87 reshapes the
node-side model, and the driver cannot ship while it stands (every dynamic volume leaks). Enabling
CSI on more nodes that would all leak is fixing the second-most-important thing first, and it means
doing the node-side twice.

## The renet i18n baseline is a number nobody can check (P5, instrumentation)

Four sources reported four different values for the SAME "frozen" quantity, and none of them is wrong:

| Source | Reported |
|---|---|
| Lead's briefing (carried from P3) | 2970 |
| P4 gate reviewer | 2818 raw / ~3044 "tool-count" |
| B2 campaign driver | 3053 |
| Lead counting `pkg/i18n/baseline.json` directly | 2819 top-level dict entries |

They are counting different things — unique keys vs. occurrences vs. whatever the tool prints — and
**nobody ever wrote down which one the freeze refers to.** So "the renet i18n baseline is FROZEN at N"
has been, for this entire phase, an assertion **nobody could actually check**. A freeze you cannot
verify is not a freeze; it is a number people quote at each other.

This is very likely part of the mechanism by which **41 user-facing strings walked past the gate**
(see above): the program's own rule is *"a count that moved is a question"* — but a count that is
ambiguous cannot raise a question, because any observed value can be explained as a different
counting convention.

**P5 fix:** make the count single-valued and reproducible — one definition, printed by the tool,
checkable by a human in one command, and asserted by the gate. Until then, treat any baseline number
in any report (including the lead's) as folklore and read the file.

## The npm-11 lockfile prune — and the gate that was supposed to catch it (FIXED in P4)

`private/account/package-lock.json` loses ~512 lines (27 nested `vitest/@esbuild/*` entries npm 10
requires) whenever **any** `npm install` runs there under npm 11. CI runs npm 10 and then dies at install
with `EUSAGE: Missing: esbuild@0.28.1 from lock file` (verified against the live specimen, exit 1).

**Fired four times**, three of them costing real CI rounds: rounds 1, 7 and 26 of the 0707 campaign
(round 7: a `git add -A` swept the pruned lockfile into a fix commit); caught by procedure pre-snapshot
on 2026-07-14; then fired again, unprompted, in the P4 gate reviewer's cold-shell worktree.

### The finding: `check:ci-lockfile` is the EIGHTH broken gate of this program

`.ci/scripts/quality/check-lockfile.sh` ran `lockfile-lint` on **the ROOT `package-lock.json` and nothing
else** — while the repo has **SEVEN** lockfiles (root, `private/account`, `private/account/web`,
`private/account/e2e`, `workers/{account,mta-sts,www}`), and **every single firing was in
`private/account*` — a file the gate never opened.** And what it validated was
`--validate-https --allowed-hosts --validate-package-names --validate-integrity`: **supply-chain
hygiene**, which says nothing about whether npm 10 can *install* the thing. Lockfile↔package.json sync was
never among its properties.

**The name promised "lockfile"; the check delivered "the root lockfile has no malicious URLs."** It was
green through all four firings and would be green on the specimen right now. Same species as the seven
other gates this phase caught: it measured something **adjacent** to what its name implied, and nobody
re-reads a green gate. **A second, unnamed hole fell out of it:** the six unopened lockfiles were not
supply-chain-validated *at all*.

### Two of the three "obvious" fixes were worse than nothing

A **net-negative-diff gate** and a **pure-deletion rejection** both catch this specimen only because it
happens to be `0 added / 512 removed`. They key on the **shape of the diff**, not the **validity of the
lockfile**. A legitimate `check-deps --upgrade` under npm 11 *adds* entries **and** prunes the platform
ones → net-positive mixed diff → both go silent and the prune ships. CLAUDE.md's own quick-fix table tells
agents to run `check-deps --upgrade`, so that is the likely path, not a corner case. **Shipping either
would have been worse than shipping nothing:** it would have *looked* like the lockfile was watched and
thereby retired the human vigilance that had actually been catching it.

### What was done instead

`check-lockfile.sh` now loops **all seven** lockfiles, running `lockfile-lint` on each (closing the
security hole) **plus an installability check with CI's own npm** (`npx -y npm@10 ci --dry-run`) — which
cannot be fooled by diff shape because **it is the command that fails in CI**. CLAUDE.md already
prescribed exactly this, but only as a *manual habit* — and that habit **was** the "an agent remembers to
look" defense. It is now a gate.

**The gate states its own limits, deliberately:** `--dry-run` does not run the reify peer check (the
round-9 `ERESOLVE` lesson), so it proves *"npm 10 can resolve this lockfile,"* not *"npm 10 can install
it."* Said in the script's comment and its log line — because a gate whose name overstates its coverage is
the exact disease being fixed, and the cure must not repeat it.

## REFUTED — group snapshots do NOT need a syncfs (do not "fix" this)

**Recorded so nobody re-discovers it and helpfully breaks it.** During the #87 spike it was observed that
the ceph group-snapshot path performs no `syncfs` at all, while fork/merge/commit/checkpoint all do. It
was chased down and **REFUTED**. It is not a bug, and not even a documentation gap.

- **We promise crash-consistency, explicitly, in the help text the user reads.**
  `commands.cluster.snapshot.description`: *"One **crash-consistent** instant across every rbd-backed
  datastore the cluster owns … **nothing stops and the cluster never notices.**"* — "nothing stops"
  affirmatively rules out a quiesce or pre-snapshot sync. A syncfs sweep is precisely what this command
  promises **not** to do. Code agrees (`pkg/toolexec/ceph/rbd_group.go:62`), as do four design docs
  (`04-cluster-fork-migrate.md:27`: *"Crash-consistent = the documented power-cut contract."*).
- **An e2e test asserts we stop there.** `03-fork-attach-snapshots.md:114-117`: a seeded value was
  snapshotted immediately and the unsynced kine write was correctly **ABSENT** from the point-in-time
  snapshot — *"That is the contract working, not a bug."* **An implementer who added a syncfs here would
  turn that test red, correctly.** The system does not merely decline to over-deliver; it tests that it
  doesn't.
- **The fork/snapshot asymmetry is one rule with two applications, and it is written down**
  (the rediacc/console#440 lesson: *if you need a write to be IN the snapshot, sync it first*).
  `repo fork` syncs because a user expects their fork to hold what they just wrote
  (`01-current-architecture.md:31`); `cluster`/`datastore snapshot` deliberately does not, because its
  entire value is that nothing stops.

**The only actionable residue** (folded into P4's open EN i18n batch at ~zero marginal cost, since the
12-locale cascade was already running): the contract's corollary — *"if you need a write in the snapshot,
sync it first"* — lived in exactly ONE place, an internal design doc. The user is correctly told what they
get; they were not told what to do if they need more. One sentence of help text closes it.

## #88 — audit records VANISHED for twelve datastore verbs (fixed in P4)

`functionNameToEventType` returned **null** for twelve datastore verbs (attach, create, delete, resize,
snapshot_create/delete/list, volumes_open/close, adopt, forget, fork) because their event types were absent
from `ALL_EVENT_TYPES`. A null event type means **the audit record is silently dropped** — on class-D
infrastructure operations, i.e. exactly the ones that most need a trail. This is a hole in the audit log,
not a naming nit.

Fixed by aligning the union to what the code actually dispatches (16 verbs) and pruning 3 dead literals
(`init`, `ceph_init`, `ceph_unfork`).

### The gate that should have caught it is the NINTH broken gate of this program

`check-audit-coverage.sh` **greps for a literal `functionName: '…'`** — but `datastore.ts` dispatches
through a **variable**. So the gate could not see a single datastore verb: it was **green by construction
for the entire family**, and it reported only the two verbs that happened to be written as literals
elsewhere. It measured *source text*, not *dispatches* — the same adjacent-measurement disease as the other
eight.

**P5 fix:** the audit-coverage gate must **walk the dispatch**, not grep the source. A grep-based coverage
check cannot see a variable dispatch, and therefore cannot fail for the reason it exists.

## Numbers that turned out to be folklore (P5, instrumentation)

A pattern worth naming, because it recurred three times in one phase and each time a decision rested on it:

| Number | Claimed | Actual |
|---|---|---|
| renet i18n baseline | "frozen at 2970" | four sources gave four values; nobody wrote down what is counted |
| CLI orphan i18n keys | 408 | **2** real orphans × 12 locales = 24 (408 was a docs gate double-counting 58 stale keys across languages) |
| Stale translator keys | 82 | **130** derived from the hash manifest (120 hash-stale + 4 missing + 8 still-English); `i18n:naturalize-status` reports "all 12 OK" and by its own output cannot fail an individual stale key |

**The lesson is not that people were careless — it is that these numbers had no reproducible oracle.**
A count with no single definition cannot be checked, and the program's own rule ("a count that moved is a
question") is inert against it: any observed value can be explained away as a different counting convention.
**P5: every gated number gets one definition, printed by the tool, reproducible in one command.**

## The `pt` locale is dialect-inconsistent (P7, quality)

Surfaced by the P4 translation wave: the Portuguese translator found two strings written in **Brazilian**
Portuguese ("Gerencia", "registra", "em um") inside a file it described as otherwise European, and
corrected them for consistency.

**The correction is fine, but the premise was overstated, and the real finding is bigger.** Counting
dialect markers across the whole file:

- European: `ficheiro` 88, `Gerir` 30, `regista` 19, `predefinid*` 14, `actual` 25 → **176**
- Brazilian: `arquivo` 20, `padrão` 13, `atual*` 66, `Gerencia` 3, `registra` 1 → **103**

So the file is **genuinely mixed**, not "European with two strays." European markers dominate the
strongest lexical tells (`ficheiro` 88 vs `arquivo` 20; `Gerir` 30 vs `Gerencia` 3), so the translator's
two fixes moved in the right direction — but ~100 Brazilian-leaning usages remain. A `pt` locale that
switches dialect mid-file reads as broken to native speakers of either variant.

**Not fixed in P4** (it is far outside the 130-key delta and touches strings nobody has changed).
**P7 item:** decide whether `pt` is European or Brazilian, state it in the i18n conventions doc, and
normalise the file once. Until that decision exists, every future translator will re-litigate it string by
string — which is exactly what just happened.

## Gates 10 and 11: the i18n key-usage and naturalization gates are blind (P5)

**#10 — `check:i18n:key-usage` has ZERO coverage of the CLI.** Established red-first, not by argument: an
orphan key (`commands.repo.zzTestOrphanKey`, present in English, called by nothing) was planted, and
**every gate stayed green.** The gate only validates the *other* direction (every `t()` call resolves to a
key) and **only scans www source files — it never opens the CLI at all.** The one check that spoke up was
`cross-language-consistency`, complaining about *asymmetry* (key in en, absent in other locales) — a
different property entirely.

**Consequence:** a CLI translation key whose last caller is deleted, but which remains present in all 13
locales, is **completely invisible**. Dead i18n weight accumulates forever and nothing will ever say so.
The `runBatchParallel` key deletion in P4 was only safe because the keys were removed from **English too**,
which converted an orphan into an asymmetry — the one shape something watches.

**#11 — `i18n:naturalize-status` cannot fail for the reason anyone would ask it.** It prints "all 12
locales OK" and, by its own output, fails only when a *whole language* is absent or near-empty; it
explicitly does **not** fail individual un-naturalized or stale keys. It is therefore useless as a
staleness oracle, which is the only question anyone brings to it.

## Correction: the lead's own "130 stale keys" was not a measurement

Recorded because it is the same error this ledger indicts elsewhere, committed by the person writing it.

The CLI's real stale-key oracle is **`npm run check:i18n:hashes`**, which prints *"English values changed
for **82** key(s)"*. The lead instead recomputed crc32 over the English values by hand and got 120, then
staffed the translation wave off a 130-key superset. **The hashing did not match the tool's**, so roughly
38 of those "stale" keys were artifacts of the lead's own arithmetic — **a number with no reproducible
oracle, built while writing the ledger entry condemning numbers with no reproducible oracle.**

**Why the error was free, and it was not luck:** the work set was a *superset* of the truth (130 ⊇ 82), and
the translators were instructed to **verify each key and leave correct translations untouched** rather than
rewrite blind. The false-stale keys cost a few verification reads and changed nothing. Had the instruction
been "these 130 are stale, rewrite them," 38 good translations would have been churned across 12 languages.

**The rule this yields:** when you cannot reach the authoritative oracle, a **superset plus verify-don't-churn**
is safe; a **point estimate plus rewrite** is not. And always look for the tool that already prints the number
before computing your own.

## The English help text taught a CLI that no longer exists (8 lies, fixed in P4)

The single most consequential find of the phase, and **the last thing anyone thought to check**.

**H1 — `help.repo.keyConcepts`, the authoritative repo-addressing document read by users AND agents, still
taught the DELETED `--name` model**, verbatim: *"A bare `--name` resolves to the exact config key, else
falls back to `<repo>:latest`… `--name app` targets the GRAND; `--name app:test` targets that FORK."*
`--name` does not exist on `repo up`/`down`/`delete`/`term`/`sync`. **English contradicted itself inside
one file**: three keys away, `help.agentMode` already said *"A repository ref derives its own machine, so
`-m` is not needed."* Two eras of the CLI side by side.

Also: `machine.description` advertised `query` and **`rename`** as key subcommands (neither exists —
`rename` was deleted outright); `help.machine.keyConcepts` advertised `containers --health-check` /
`services --stability-check` (merged into `machine status --containers/--services`); and
`errors.agent.commandBlocked` — **the error shown to a blocked agent** — recommended the MCP tool
`machine_query`, **which does not exist**. We blocked the agent and handed it a dead tool name.

### Nothing in the repo could ever have caught this — four gates, four blind spots

- **Locale gates** check locales ↔ English. English is the source of truth, so *by construction it can
  never be wrong.*
- **Contract gates** check code ↔ generated artifact — **tautological**: the artifact is generated *from*
  the code.
- **`validate-cli-examples`** parses `rdc …` **syntax**. These lies live in **prose lists**.
- **The i18n hash delta** never fired: English's hash never changed, because English was *always* wrong.

**The instrument that finally noticed was a Japanese translator reading a sentence.**

**P5 gate (highest-value of all of them, ~40 lines):** walk the live Commander tree; for every domain-level
help string, assert every command-ish word it names is a live child of that domain. Same mechanism as the
spec-intent gate; one more axis.

## Doctrine: a sweep that returns zero without a control is a broken instrument reporting good news

Recorded because the gate reviewer caught **itself** with it, and said so unprompted.

Its first sweep of the English-help axis returned **ZERO** — and it nearly reported that as a clean bill of
health. The probe searched for `rdc <cmd>` and backticked forms; **the lies were in prose lists**, so the
instrument was blind to the entire class. It was caught only because the lead had handed it one **known
positive** (`machine.descriptionShort`) to check against.

**Every sweep now carries an explicit control**: a known-positive that MUST appear in the results, or the
run is void. A zero-finding sweep with no control is indistinguishable from a broken sweep — and "no
problems found" is the most dangerous possible output of a broken instrument, because nobody audits good
news.

## Italian accent corruption — CLI fixed; the WEBSITE's Italian is still broken (follow-up PR, NOT this one)

**Fixed in P4 (CLI locale):** 17 accent defects in `packages/cli/src/i18n/locales/it/cli.json`. These were
not typos — they changed meaning. Italian `e` = *and*, `è` = *is*, so `"Il binario corrente e in uso"` reads
as *"the current binary AND in use"*: a broken sentence in a message users see when an update fails.

**Found by tracing the same bad pass into `packages/www/src/i18n/translations/it.json` (9,184 strings) —
NOT FIXED, deliberately:**

- **5 × `e` that should be `è`**, including **`pages.termsOfService.sections.accounts.content[0]`** —
  *"Per accedere alla Piattaforma e gestire gli Abbonamenti **e** necessario…"* — **in the Terms of
  Service.**
- **23 × unaccented words**, many using the typewriter-era **apostrophe-as-accent** workaround
  (`gia'`, `piu'`, `e'`) — concentrated in **`pages.refundPolicy.*`**: *"Ore di servizi professionali
  **gia'** erogate"*, *"Rediacc offre **piu'** livelli"*, *"Se l'utente **e'** un nuovo abbonato"*.
  In published commercial copy this reads as unfinished work.
- **Control fired**: 77 strings retain legitimate `e` (= *and*), so the corruption is real and localised,
  not an artifact of the probe.

**Why it is NOT fixed in the P4 PR, on purpose:** the CLI's Italian was in scope because P4 reshaped the
CLI. The website's Italian is not. Slipping ~28 www-locale edits into a 270-file CLI PR **at the finish
line** risks tripping the www i18n gates at the worst possible moment, and buries a customer-facing legal-copy
fix where no reviewer would ever look for it. **A three-file www-locale fix reviewed on its own is both
safer and more honest than smuggling it in here.**

**Action:** dedicated follow-up PR (or P7's www wave). The keys are enumerated above; the method is proven
(word-list probe → manual context review → reject false positives → control check). **Do not blanket-replace:**
`"la politica effettiva unita"` correctly means *"the effective MERGED policy"* — `unita` is the participle
*merged*, not the noun `unità` (*unit*). A mechanical accent-fixer corrupts that string while "fixing" it.

## H9 — the fork SUCCESS message printed two commands and BOTH failed (fixed in P4)

`commands.repo.fork.completed`, printed after **every single fork** — the flagship operation:

> "Fork created. Deploy locally: `repo up {{repository}} -m {{machine}}`. To migrate fork to another
> machine: `repo push {{repository}} -m {{machine}} --to <target> --up`"

`repo push` has **no `-m` flag at all** (`error: unknown option '-m'`), and **`--up` on push was DELETED**
`[P0-DECIDED]`. **F1 was the front door; this was the exit.** Every fork ended by telling the user two
things to do next, and neither ran.

Plus H10 (`push.description`: teaches the dead `--up`, and *"omit name to push all repos"* — impossible,
the ref is required), H11 (`fork.description` step 2 teaches `push --up`; **it also GENERATES
`.claude/skills/rdc/reference.md:921`** — fix English, regenerate, never hand-edit the skill), H12
(orphan `push.optionUp`; **`repo pull` genuinely still has `--up`** — do not "fix" that one).

## Gate 12 — `validate-cli-examples` cannot see the examples CLAUDE.md is made of

`scripts/validate-cli-examples.ts:293`: `if (!command.startsWith('rdc') …) continue;`. CLAUDE.md's own
convention **mandates `./rdc.sh`**. So the gate scans the file and **walks past every line the file is made
of** — and reported zero. `CLAUDE.md:220` teaches the deleted `repo push … --up` and the gate has never
seen it.

**The damning part: the repo already knew.** `scripts/check-cli-docs.ts:624` carries a comment describing
**this exact bug**, found and fixed *there*: *"failed `startsWith('rdc')`, and WAS SILENTLY DISCARDED. The
scanner reported zero."* Someone hit it, diagnosed it, fixed one scanner — **and never applied it to its
sibling ten lines away.** A fix that is not swept across its own class is half a fix.

## The one surface that is NOT lying, and why

**MCP tool descriptions: CLEAN.** 73 tools walked from the live tree, **0 prose hits**, control carried.
And `argv-acceptance.test.ts` passes **96/96** — it resolves every tool's argv **against the real Commander
tree**, and its header names exactly the rot it exists to catch.

**That is not luck. It is the only surface in the repo whose gate asks the thing that DECIDES.** Every other
surface — help text, skills, CLAUDE.md, docs — is validated against something *adjacent* (a generated
artifact, a syntax pattern, itself), and every one of them was lying. The thesis of this entire phase,
demonstrated by its single counter-example.

## P7's true size, measured

`packages/www/src/content/**`: **4,380 lines across 1,081 files** matching dead-model vocabulary. Counted,
not fixed — so the P7 rewrite knows what it is actually signing up for rather than discovering it midway.

## The wave broke all three doors — and the exam that certifies people on it

**166 hits / 30 files** in `private/account` teach the deleted CLI. **`practice-questions.ts` — THE EXAM —
has 22.** `study-content/` (the certification modules) has 126. We were about to certify people on a CLI
that will not exist, and grade them against answers that are wrong.

**Register the shape of this, because it is the phase in one line:**
- **F1** — `rdc --help`'s own examples errored against the binary printing them. **The front door.**
- **H9** — `repo fork`'s SUCCESS message printed two commands, and **both failed**. **The exit.**
- **onboarding-content.json** — the first-run flow: **all three** commands broken. **The onboarding.**

**The reshape renamed the world and left every sign pointing at the old one.**

### The sequencing rule (learned twice — skill docs, then cert content)

Five constructs (`machine health|prune|provision|deprovision --name`) **match the code today**, because
their positional fixes had not landed yet. Correcting the docs *first* would have made them wrong in the
**other** direction — certifying people against a CLI that exists in **neither** era.

**A doc fix that precedes its code fix is not a fix, it is a different bug.** Land the code, then the docs.

### Why nothing saw it

The cert content is TS/JSON **in another repo**. `validate-cli-examples` scans the console monorepo and
flags **1 of the 166 lines**. It cannot see the exam, the study modules, or **12 of the 13 locale copies**
of a UI string (`machines.json:14`) that names a deleted command — English is checked, the other twelve are
invisible, so fixing English alone would leave 12 live strings teaching `machine query`.

**A wave that renames the CLI invalidates the exam that certifies people on it — and nothing in this
codebase connects those two facts.** The P5 spec-intent gate must run against `private/account/web/src/data/**`
and `.../i18n/**` with the same live-tree oracle.

### Two disciplines worth copying

- **The gate caught a false positive in its OWN detector**: `repo diff --name` is not real — `repo diff` has
  `--name-only`, a **live** flag, and the `\b` matched at the hyphen. It reported the flaw rather than
  shipping a batch that would have deleted a working flag.
- **It checked whether a hit was doc rot or a functional bug**: `contract-context.ts` *comments* mention
  `--name`, but the code reads `entry.machineOption ?? entry.machinePositional` — binding-driven and
  reshape-safe. Comment dead, code correct. The distinction mattered and it went and looked.

## A trap TypeScript cannot see: converting an option to a positional silently shifts action arity

**Found during the positional sweep, and it would have shipped a functional bug with a green type-check.**

**Commander's `.action()` callback arity is untyped.** When a leaf gains a positional argument, Commander
starts passing it **first**: `(options)` becomes `(name, options)`. But the action's declared signature is
not checked against the command's shape — so after converting `machine prune --name` to
`machine prune <name>`, the action **still declared `(options)`** while Commander now handed it
`(name, options)`.

**The machine NAME would have arrived in the variable the code reads options from.** Not a crash — a
silent misbinding, on a *destructive* command.

**`check:types` stayed GREEN through it.** The type system cannot see this, by construction: the arity
contract lives in Commander's runtime, not in the callback's type. It was caught by **reading every action
after the change**, not by any gate.

**Rule:** a positional conversion in Commander is a **silent arity change**. Every `.action()` on a
converted leaf must be re-read. **P5:** an argv-acceptance-style test per converted leaf (the MCP layer
already has this — `argv-acceptance.test.ts` — and it is precisely why the MCP argv builder needed **no**
change during the sweep: it derives argv from the live tree, so it followed automatically).

### And a test that codified the bug

`job cancel`'s unit test **asserted the inconsistency in its own docstring** — *"`cancel` still uses
`--id`"* — while its siblings `job status <job-id>` and `job logs <job-id>` took positionals. **The test was
not missing the bug; it was documenting it as intended behaviour.** A test that encodes a defect as a
contract is worse than no test: it converts a bug into a requirement, and the next person to fix the bug
has to break a green test to do it.

## Diacritic corruption is a CROSS-LOCALE class — and four of the lead's instruments failed to see it

Surfaced only because translators *read* their files. **Every instance below passed every mechanical check
we have** — valid JSON, correct keys, correct placeholders, non-English text.

| locale | defect |
|---|---|
| **it** | **17** accent defects. `"Il binario corrente **e** in uso"` = *"the current binary AND in use"* — `e`=*and*, `è`=*is*. A broken sentence in a live update-failure message. |
| **tr** | `errors.agent.commandBlocked` was **ASCII-only garbage** — every diacritic stripped. Plus `subscription.login.*` (`Guncelleme kanali… ayarlandi` → `Güncelleme kanalı… ayarlandı`) and **two strings still in English**. |
| **de** | umlauts stripped through a live error message (`verfugbar`, `fuhrt`, `benotigen`, `ausfuhren`). |
| **fr** | `"**Ou** vos **donnees** doivent-elles **etre** **stockees** ?"` — four missing accents in one sentence, in the **login flow**, and `Ou` (*or*) vs `Où` (*where*) **changes the meaning**: it reads *"Or your data must-they be stored?"* |
| **es** | `esta` → `está`. |

### The lead's instruments failed FOUR times in one night

1. Accent sweep **cleared French as clean** — French had four missing accents in one sentence.
2. Accent sweep **never checked German at all**.
3. Accent patterns **missed 8 of Italy's 17** defects.
4. English-prose detector returned **six hits, all false positives** — it matched **placeholder names**
   (`{{to}}` contains "to", `{{from}}` contains "from").

**The readers beat the pattern-matcher every single time.** This is the same finding as the twelve broken
gates, arriving from the opposite direction: **the instruments confirm structure; they cannot confirm
meaning.** A `--help` text that taught a deleted command, a fork success message recommending two commands
that both fail, an exam certifying people on a CLI that does not exist, and a login prompt asking *"or your
data must-they be stored"* — **none of it was findable by a machine checking that the pieces were present.**

**Method that does work** (Italian's, adopted by all): word-list probe → **read every hit in context** →
reject false positives → keep a **control** (legitimate unaccented words must survive, or you over-corrected).
Italian's control fired: 53 legitimate `e` (=*and*) survived. And it correctly **refused** one apparent hit —
`"la politica effettiva unita"` means *"the effective MERGED policy"* (participle), not `unità` (*unit*). A
mechanical accent-fixer corrupts that string while "fixing" it.

**P5:** the `check:i18n:untranslated` gate cannot see stale English left in a locale (it only catches values
*byte-identical* to current English). Leftover English from an older source text is invisible to it.

## A hand-assembled delta list is not a delta — it is a memory of one

**Caught before it shipped, and it is the cleanest process failure of the phase.**

The H9 fix rewrote `commands.repo.fork.completed` (the fork success message that printed two commands which
both failed). The fix correctly removed `-m {{machine}}` from both — so English went to `{{repository}}` ×4
with **zero** `{{machine}}`. But that key **was not on the hand-written "final English delta" list** handed to
the 12 translators, so none of them touched it.

**Result: a placeholder mismatch in all 12 locales** (locales still carried `{{machine}}` ×2). Every
translator reported clean — and every one *was* clean **against the list they were given**. The defect was
in the relay, not in any of them.

**The authoritative delta was always available, mechanically:**
`git diff <sha>^..<sha> -- packages/cli/src/i18n/locales/en/cli.json` names **every** changed key, with no
possibility of omission. Instead the list was assembled by hand — twice: the lead's earlier relay also
dropped `commands.repo.push.optionUp` (caught by the German translator) while naming its sibling deletion.

**Rule: never hand-assemble a change list that a diff can generate.** The same principle as everything else
this phase found — *ask the thing that decides*. A human-curated list of what changed is a **memory** of
what changed, and memory is the failure mode.

**Also caught in the same pass:** `docs.sectionTitles.ops` is the ONLY English value still saying
"experimental", while `commands.ops.description(Short)` correctly dropped that framing. **English now
contradicts itself, three keys apart, in the same file** — the exact shape of H1. The Estonian translator
found it independently and flagged it as out of scope; it was not out of scope, it was the same bug.

**New axis for the P5 English-truth gate:** sibling English values for one noun (`description`,
`descriptionShort`, `docs.sectionTitles.*`) must not contradict each other. The hand-run two-axis sweep
found zero dead-command references and **still could not see this**, because both axes compared English to
the *tree* — neither compared English to **itself**.

## #85 — what is PROVEN LIVE, and what is not (scope this precisely in the commit message)

**#85a (the global pin) is LIVE-PROVEN.** From the surviving provisioning transcript:
`"Pinning osd_pool_default_size=2/min_size=1 for a 2-OSD topology"` → `"Ceph health: HEALTH_OK (elapsed: 0s)"`.
**The FIRST health poll returned HEALTH_OK** — stronger than the requirement. The gate did not tolerate a
warning, did not fall through, did not wait out a degraded window: **there was no warning to tolerate,
because the pin removed `TOO_FEW_OSDS`'s cause.** A size-2 `rbd` pool was then created, two rbd datastores
mapped/LUKS-opened/mounted, and `cluster create` **returned 0** — a command that could never succeed before.

**#85b (the repaired dead branch) is UNIT-PROVEN, NOT live-exercised** — and that is the correct outcome,
not a gap: `WaitForHealth` only reaches the repaired predicate inside the `HEALTH_WARN` branch, and a healthy
cluster never enters it. It is covered by 10 tests built from **verbatim live strings** (including the
`"0\n0"` captured with `od -c`). **A commit message claiming "#85b proven live" would be false.**

`active+clean` is **ENTAILED** by HEALTH_OK (any inactive/undersized/degraded PG raises a warning) — but it
was **not directly captured** in the winning run. Entailed, not observed. Say it that way.

**The rewrite is better than the fix it replaced:** the gate no longer substring-matches health against a
benign-warning allowlist; it asserts the property (**every OSD up AND every PG `active+clean`**) and warns
loudly when it proceeds through a warning. The old allowlist had `"pool size"` on its benign list — it would
have **passed a permanently undersized cluster** (the exact size-3-on-2-OSDs hole) while **failing** a
serviceable one whose only complaint was I/O latency.

## #90 — the fix for silence was itself silent (the 9th file)

**Caught at hand-off. Shipping the 8 renet files without the 9th would have shipped #86 broken, reading as done.**

#86 turned a silent `log.Debugf` into a loud `log.Warnf` when CSI enablement is skipped on a node. But
**`local-executor.ts:397` echoes renet's output ONLY on failure or under `--debug`:**

```
if (exitCode === 0 || options.debug || options.captureOutput) return false;
```

And a `datastore attach` on a worker **succeeds** — that is the entire point of #86. **So the new warning was
dropped before the operator could ever see it.** The renet half alone "fixes" the silence *while leaving it
silent*.

**This program's disease, inside this program's own fix, in the very bug whose defect was silence.**

Fix: `surfaceRenetWarnings()` in the CLI executor (+25 lines) — renet's warnings reach the operator on a
**successful** run too. The nine files ship together or #86 is theatre.

## Two holes found in a verification script — by its own author

Recorded because it is the doctrine, self-applied, and because the second one nearly ate the base fleet.

1. **An assertion that COULD NOT FAIL.** The teardown gate's "libvirt disk images" check pointed at
   `/var/lib/libvirt/images` — **a directory that is empty on this host and is not where these VMs keep their
   disks** (they live in `/tmp`). It returned `0` unconditionally and **read as a PASS**. *An assertion that
   cannot fail for the right reason predicts nothing* — written straight into the gate meant to enforce it.
2. **A false positive**: `grep -ci 'b2c'` matched `/tmp/sshconfig-test-<epoch>-<random>` unit-test fixtures
   whose random IDs happened to contain `b2c`, created **before b2c existed**. A gate that goes red for an
   unrelated reason is as useless as one that cannot go red at all.

**Fixed the instrument, not the verdict** — then added a **falsifiability control**: the same search must find
the base fleet's 6 disks, or every zero it reports is declared meaningless. Only then was "clean" claimed.

### ⚠ LIVE FOOTGUN: VM ids OVERLAP between the base fleet and test clusters

Base fleet VM ids: **1, 11, 12, 21, 22, 23**. The b2c cluster's were: **1, 11, 12, 13, 21, 22**. **They
overlap** — and disk paths are keyed by VM id. **A teardown matching on the bare id would have deleted the
base fleet's disks.** Cluster-path matching only, always. This nearly happened.

## Teardown honesty: which step cleaned what

`cluster destroy b2c --force` returned exit 0 — and **did NOT clear the datastores or repos.** The config
file `rm` did. Measured cold on a clean, single-driver destroy with all VMs gone:

| after `cluster destroy` | |
|---|---|
| `resources.clusters` / `machines` / `state.clusters` | **cleared** (#22's fix working) |
| `resources.datastores`, `resources.repositories`, `state.datastores` | **SURVIVED** — three `mounted: true` claims on machines that no longer exist |

**#89 reproduced on a clean single-driver teardown**, so it is not an artifact of the earlier churn. Reporting
"destroy: clean" without naming the config `rm` as the actual cleaner would have laundered #89 through the
teardown proof — precisely the swallowed-error failure B1 was pilloried for.

**Minor systemic leak (P5):** `cluster destroy` leaves its per-cluster scratch dir. `/tmp/rediacc-b2c/`
survived empty — and **nine siblings from earlier campaigns are still there** (`rediacc-b1src`, `-csi1`,
`-fu1src/dst`, `-fu2`, `-rdst`, `-rv1src/dst/mig`). Zero bytes, but the product owns them.

## #89 had THREE sites — and #91 is the same hazard through a different door

The lead ruled on ONE site. The babysitter applied the lead's own rule (*"a fix not swept across its class is
half a fix"*) **to the ruling itself**, and found two more:

1. **`removeClusterFromStore`** — the ruled site. Now clears `state.datastores` for every datastore the
   cluster owned, plus `state.repos` for repos placed on them.
2. **`forgetDatastore`** — **same bug, and it was a TRAP rather than a non-bug.** It drops
   `resources.datastores` and keeps `state.datastores`. It is unreachable today **only because the delete path
   happens to call `setDatastoreState(ref, undefined)` first whenever the datastore is attached.**
   **The invariant held only because every caller remembered.** `forget` now means forget, regardless of caller.
3. **#91 — `removeMachine`. NEW. The same routing hazard through a different door.** It kept `state.machines[m]`
   **and every `state.datastores[*]` hint still naming the removed machine**. `machine remove` + re-add the same
   name = a hint aimed at a brand-new machine that has never heard of that datastore. **Identical to #89,
   arriving via `machine remove` instead of `cluster destroy`.**

**The split is now written into the code at all three sites, with the reason**, so nobody "fixes" it backwards:
`resources.*` is what the operator **declared** (a spec outliving its cluster is defensible intent);
`state.*` is what we **observed**, and an observation of a world that no longer exists is a **lie by
construction**. Explicit: *do not fix this by also deleting the resources.*

**And the max-lines pressure the fix created was paid down by EXTRACTION, not by widening a suppression** —
`dropMachineObservations` moved into the file whose own header says it exists to keep the other under budget.
In the babysitter's words: *"I did not want to answer 'we added a suppression' when you asked what it cost."*

**Third comment this wave that described behavior the code did not have:** the doc promised *"every read here
tolerates a stale hint instead of trusting it blindly"* — it tolerates a **MISSING** hint and **TRUSTS a WRONG
one**. Now corrected to say exactly that, with the read-hardening marked P5. **A comment promising a mitigation
the code does not implement is worse than no comment, because it stops the next person from looking.**

## Nuance: when a `no-unnecessary-condition` guard IS genuinely dead

Recorded so the successor does not over-apply the earlier lesson.

The `noUncheckedIndexedAccess` entry says the linter tries to delete **real** runtime guards, because
`map[key]` is typed as always-present while returning `undefined` at runtime. **That is true for indexed
access — and NOT true for `Object.entries()`.**

`Object.entries()` only ever yields **existing** keys, so **its value type is honest.** Guards derived from it
really are dead, and removing them is correct. The distinction is precise:

> **`map[key]` lies about optionality. `Object.entries()` does not.**

Preserve the guard when the type is lying. Delete it when the type is telling the truth.

## The P7 www deferral was measured wrong — and hidden by a && short-circuit

**CORRECTION, and it invalidates a number this ledger and the PR body both carried.**

The deferral was recorded as **"379 violations under `packages/www/src/content`, not in any CI gate."** Both
halves were wrong.

**It IS a CI gate.** `check:i18n` (`ci-quality.yml:180`) is a **17-link `&&` chain**, and the www validators
sit at links **8, 9 and 16**. **Link 1 — `check-translation-hashes.ts` — was failing the entire time**, so
the chain short-circuited before ever reaching them. Grepping the workflows for the validator script names
found nothing, and the conclusion "not a CI gate" was drawn without following the chain that invokes them.

**A gate that never got to RUN is indistinguishable from a gate that PASSES.** The same disease, this time
inside the diagnosis of the disease. **It surfaced only because `i18n:generate-hashes` was taken LAST, in the
correct order** — that turned link 1 green and let links 2-17 execute for the first time in thirty rounds.
**Correct sequencing produced the evidence.**

**True size: 3355 violations, 24 distinct docs, all 13 locales** (~832 files if bulk-edited: 60 English + 772
locale). The "379" was one narrower validator's count. **Fifth number this program has had to correct.**

### Ruling: a per-FILE frozen baseline, not an exclusion

- **Excluding `packages/www/src/content/docs/**` is not scoping the gate — it is DELETING it** (that directory
  is the validator's entire scan root, exactly as with `check:i18n:docs`).
- **Bulk-editing 832 files is what P7 exists to defer**, and it would land untranslated CLI prose in 12 locales.
- **Dropping the validators from the chain removes them from CI forever** — worse than a baseline that
  self-destructs.

**So: record each of the 24 docs with its EXACT violation count. Per-file, never a global total** — with one
number, a fix in one doc and a regression in another **cancel out silently**; with per-file counts they cannot.
A new doc, or a rising count in a baselined doc, **still fails**. Every entry **must vanish when P7 rewrites the
docs — a count that outlives the rewrite is a bug, not a deferral.**

**And the baseline must be PROVEN to fail before it ships** (red on a rising count, red on a new doc, green
as-is). *We have found twelve gates that were green because they could not fail. Do not build the thirteenth
while fixing the twelfth.*

## A dead-looking name is a hypothesis, not a verdict — grep the callers

**Third time this wave the obvious deletion would have broken something live:**

1. **`repo diff --name-only`** — a sweep's regex matched it as `repo diff --name`; deleting it would have
   removed a **live flag**.
2. **`repo pull --up` / `repo fork --up`** — real, and survive; only `repo push --up` was deleted.
3. **`commands.context.*`** — `context` is the noun the config exodus **retired**, yet it still held **one LIVE
   key** (`pushInfra.installingProxy`, called from `infra-provision.ts:318`). **Deleting it breaks the code;
   keeping it leaves a retired noun waiting to be re-bound.** Correct answer was neither: **relocate** it to the
   command that now owns it (`commands.machine.infra.push.installingProxy`), carrying the value **verbatim**
   across all 13 locales — a relocation, not a re-translation, costing the translators nothing.

**Grep the callers before you delete. A name that looks dead is a hypothesis.**

## The website's STRUCTURED command data: 188 dead commands, covered by NOTHING (P4-caused)

**Found by asking the question the homepage-hero fix raised: do other structured-data surfaces share that
blindness? They do, and it is worse.** These are `"command":` / `"commandFull":` FIELDS, not prose — **no
string-replace sweep can see them, no gate scans them, and the P7 backlog contains ZERO of them.**

| where | count | what it is |
|---|---|---|
| `www/src/i18n/translations/*.json` (13 locales) | **91** | UI/marketing terminal demos |
| `tutorial-storyboard/` | **70** | the commands **TYPED** in the recorded tutorial terminals |
| `tutorial-transcripts/<lang>/` (13 languages) | **26** | the commands **SPOKEN** in the video narration |

Real examples: `"command": "rdc repo mount production -m primary"` (verb deleted);
`"commandFull": "rdc repo fork --parent <x> --detach"` (**all four constructs gone**).

**This is P4-caused** — the reshape deleted these commands — **so it is ours by the scope test** (does this wave
create the problem?). **Deferring is reasonable**: fixing the transcripts and storyboards means **re-recording
the tutorials and re-narrating them in 13 languages**, which is a media pipeline, not a text edit.

**But it needs its own entry with this count, because the P7 backlog LOOKS like it covers the website and does
not.** A deferral that hides inside another deferral is not a deferral; it is an omission.

## N5 — RETRACTED. The gate two reviewers called vacuous is the STRICTEST setting there is

**What was claimed** (by the gate review, and independently by me): `validate-landing-cli-usage`
loads `packages/www/scripts/data/landing-cli-capability-map.json`, that file is 20 bytes —
`{"entries": []}` — so it validates zero commands, prints "✓ valid", exits 0, and is
"structurally incapable of failing." The verdict was **populate it or delete it**.

**Both reviewers were wrong, and the ruling would have destroyed a working gate.**

The map does not list the commands the gate CHECKS. It lists the commands the gate **EXCUSES**
from parsing. Empty therefore excuses **nothing**, and all **31** `rdc` commands on the landing
surfaces must parse against the live CLI. **Empty is the strictest the file can be. Populating it
would have WEAKENED the gate; deleting it would have removed the very check that catches the
homepage hero teaching a deleted command.**

**How it was settled: by running it, not by reading it.** A dead command (`rdc cluster fork --name
prod`) was planted in the homepage hero. The gate went **red**. That single experiment refuted two
careful readings of the source.

Its real defect is much smaller and is now fixed: **its success message understated its own work.**
It said "✓ valid" without saying it had checked 31 commands, and it would have claimed success on
an empty scan. It now prints what it checked, labels the map as EXCUSED commands, and refuses to
report success if it scanned nothing.

**The lesson, and it is the phase's real thesis:** a gate that cannot describe itself is one bad
reading away from deletion — and *"I read the source"* is not evidence about a gate. **Ask the
thing that decides. Run it, and make it fail.**

## The renet i18n baseline: THREE numbers, THREE definitions, all true

`docs/design/spec/10-p3-gate-review.md` records the gate reference as **2970**. `baseline.json`
holds **2822 entries**. CI reports **"3057 grandfathered via baseline"**. None of these is
wrong, and none of them means the same thing:

| number | what it actually counts |
|---|---|
| **2970** | FINDINGS at the P3 gate reference — every extractor hit, occurrence by occurrence |
| **2822** | unique ENTRIES in `baseline.json` — deduplicated (one string used twice is one entry) |
| **3057** | FINDINGS today, i.e. 2970 plus what the waves since have added |

**The P3 verdict is NOT edited to "fix" 2970.** It is a verdict document, its independence is
the point, and its number is correct *for the thing it counts*. The defect was never a wrong
number — it was a number quoted **without its window**, which is how the same figure came to
be read as three different quantities.

**The convention, stated once so it stops recurring: every i18n count in this repo must name
its unit (findings vs entries) and its reference commit.** A count with neither is folklore,
and this program has now had to correct five of them.

### The 188-command deferral now has a LIVE CI RED attached to it

It is no longer theoretical. `Quality / Tutorial Cast Hygiene` went red in CI round 3 on three
recordings — `tutorial-branching`, `tutorial-managing-secrets`, `tutorial-vscode-browser`.

The mechanism is the coupling rule, arriving from a direction nobody was watching. That gate
exempts a command's error output when the tutorial script declares it with
`run_cmd_expect_fail "<command>"`, and it matches the declaration to the recording **by command
text**. P4 rewrote all 22 scripts in `.ci/tutorials` to positional syntax; the `.cast` files
still carry the pre-P4 text. **The labels stopped matching, so three DELIBERATE failure demos
stopped being recognised as deliberate.**

**A script fixed ahead of its recording is not a fix, it is a different bug.**

The scripts are right and must stay right (they are the source for the next recording, and
`.ci/tutorials` is also scanned by `check-cli-docs`, so reverting them would simply move the
failure). **The RECORDINGS are what is stale** — and reconciling them means re-recording with a
live VM lab and re-narrating in 13 languages, which is exactly the work this entry defers.

**Held by a self-destructing per-file backlog** (`packages/www/scripts/tutorial-cast-baseline.json`),
proven red-first: a NEW error in a clean recording still fails. **Every entry must vanish when
the tutorials are re-recorded; an entry that outlives the re-record is a bug, not a deferral.**

**Record this as evidence, not as an inconvenience:** the re-record is real work with a real CI
red behind it, not a tidy-up someone can keep postponing.

### Storyboard ↔ cast ↔ portal: three statements, and only two can be true at once

The same debt surfaced a THIRD time, from the opposite direction, and the third time is the one
that teaches the shape of it.

The account portal's first-run flow (`private/account/web/src/data/onboarding-content.json`) is
GENERATED from four tutorial storyboard scenes' `card.commandFull`. Those scenes still taught the
pre-P4 CLI — `rdc config machine add --name …`, `rdc vscode connect --machine … --repository …`.
**That is the first command a new user ever types, and it no longer exists.** A regeneration had
already silently reverted a hand-edit of the generated file once, and no gate said a word:
`check-account-onboarding` asserted the command was a non-empty STRING, so the correct file and a
file teaching a deleted command both passed. It validated the SHAPE and not the THING.

The durable fix is the storyboard, because the storyboard is the source. But the storyboard is
also **supposed to describe what the video shows** — and the video still shows the old command.
So:

- Fix the storyboard → the PORTAL is right, and `Quality / Tutorial Parity` goes red, because the
  storyboard now disagrees with its recording.
- Leave the storyboard → the RECORDING is consistent, and the portal ships a dead command to
  every new user.
- Re-record → everything agrees. That is the work being deferred.

**A doc, a script, or a storyboard fixed ahead of its recording is not a repair — it is one more
statement of the same stale-recording debt.** The coupling rule, arriving for the third time
tonight and the first time pointing at a source file rather than a derived one.

Resolved by taking the fix that a regeneration cannot erase (the storyboard), and deferring the
parity break in a **per-scene, exact-pair** backlog (`packages/www/scripts/tutorial-parity-baseline.json`):
each entry pins BOTH the storyboard command and the recorded marker, so changing either side, or
drifting any other scene, still goes red. Proven red-first in all four directions. **It
self-destructs mechanically** — an entry that matches no drift is a FAILURE, not a shrug.

These entries clear at the SAME event as `tutorial-cast-baseline.json`: the re-record. **They
clear together or they are a lie.**

The gate was hardened to compare the command TEXT against its storyboard source, so this class
cannot come back silently.

## A gate that CRASHES has not failed — it has gone blind, and it takes a real red down with it

`Quality / i18n` was red on a stack trace, not on a finding:
`ERR_MODULE_NOT_FOUND: @rediacc/provisioning/dist/index.js`.

`check-cli-docs` imports the **live Commander tree** (`packages/cli/src/cli.js`) instead of a
hand-maintained list — which is exactly right, and is why it can see a dead flag at all. But that
import pulls in `kvm-provisioner.ts → @rediacc/provisioning`, whose package main is `./dist/index.js`,
and the job never built it. **Locally it is invisible: `dist/` is always warm.**

The cost was not the crash. **The crash was standing in front of a real defect**: once the package
is built, the gate runs and immediately reports that `commands.repo.delete.cloudBackupHint` — the
hint the CLI prints after deleting a repo, in all 13 languages — tells the user to run
`rdc storage prune --name <storage>`, a flag P4 deleted. **The gate was right, had been right all
along, and could not say so.** A crashing gate is worse than a failing one: a failure names a
defect, a crash names only itself.

Two fixes, both mechanical:
- The job now runs `npm run build:packages` — the repo's single list of what the CLI imports (13
  other sites already use it). The two jobs that instead named the workspaces by hand have been
  converted: **naming them twice is how a third package silently rots a job.**
- The dead flag is fixed at its source (`packages/cli/src/i18n/locales/*/cli.json`, all 13), with
  the generated CLI contract regenerated from it. **A command name is never translated** — so the
  same dead flag was sitting in all twelve non-English catalogues, in parity, undetected.

**Verified the only way that means anything: cold.** `dist/` AND `*.tsbuildinfo` removed (deleting
the output alone is not a cold build — `composite: true` makes `tsc` exit 0 and emit nothing), the
crash reproduced byte-identically, then the fix applied and the gate watched to go from CRASH to a
real finding to green.

## The CSI driver has ZERO e2e coverage — and NO GATE CAN SEE THAT

`packages/e2e-tests` used to carry a `CsiMethods` class that dispatched a bridge verb named
`kube_csi_template`. Three facts about it, in the order they were discovered:

1. **renet never registered that verb.** It is in no registry, no schema, nowhere.
2. **No test ever called it.** Zero. It was wired into `BridgeTestRunner` and nothing else.
3. **Its own header says why it existed**: it dispatched the name *"so the e2e-coverage gate finds
   it once the lead regenerates the renet contract."*

**It was a coverage ANCHOR — a string written to satisfy a gate, for a function that did not
exist.** The one-directional `check-e2e-coverage` (live → e2e only) could never have caught it,
and did not. The bidirectional gate found it on its first run.

Deleting it costs no coverage, **because there never was any.** But deleting it does not close the
question — it OPENS it, and this entry is the record:

★ **The CSI driver is not exercised by any e2e test.** Not one.

★ **No gate can demand that it is.** The surviving surface is the CLI (`renet kube csi-install`,
`csi-node-up`, `csi-serve` — `cmd/renet/kube_csi.go`), and `check-e2e-coverage` governs the BRIDGE
registry. **The gate is not broken; the subject is outside its jurisdiction.** Nothing will ever go
red about this. That is the whole reason it needs writing down.

★ **The only thing that has ever proved CSI works is B2's live campaign** — a hand-driven run
against real infrastructure, whose result is a transcript. **A live campaign is not a regression
test.** It proves the code worked once, on one topology, on one day, under one operator. It cannot
tell you that it still works tomorrow, and nothing else will either.

★ The P3 gate flagged CSI **EXIT-blocking precisely because it had never been exercised**. The
phantom anchor is why the board looked otherwise.

**A deleted fake test must leave a recorded gap, or you have improved the board and degraded the
truth.** The gap is real, it is now visible, and closing it means a real CSI e2e suite driving the
CLI path (the same way `OpsManager` shells out for `renet datastore init`).

## A parameter the schema never accepted — #74's class, in the test harness

The e2e harness called `datastore_expand`, `datastore_resize` and `datastore_validate` with a
`datastorePath` argument. **renet's schema has no such parameter** — `expand`/`resize` take a
`size`, `validate` takes nothing at all. The value was serialized, sent, and **silently discarded**
on every call, in every suite, for as long as those tests have existed.

Nothing failed. Nothing warned. The tests passed, and every one of them was passing a path that
the thing under test never read — so a suite that *believed* it was validating a datastore at
`/mnt/test-datastore` was in fact validating whatever the machine's base pool happened to be.

**This is bug #74's class, arriving through a different door: a declaration the system is free to
ignore is not a declaration.** An argument that no receiver validates is indistinguishable from a
comment — except that a comment does not lie about what the test covered.

Removed with the P1 verb translation. The general defect stands: **the bridge accepts unknown
params without complaint.** Rejecting an unknown param at dispatch would have surfaced this on the
first run, years earlier, for free.

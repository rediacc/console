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
- **#86 (HALF-fixed — read the P5 section below).** Attach-time CSI enablement silently no-oped on any node without a local admin kubeconfig, while attach still reported success. **What P4 fixes is the LIE, not the gap:** attach now fails loudly, naming why. CSI datastores still work only on the control-plane node; the feature itself is P5.

## Carried from earlier phases — still open

- **#68 / #82 — the adoption path.** The product can only manage the world it created; `repo replicate` is undriveable on any cluster the CLI did not provision. `replicate refresh` is excluded from MCP for this reason (it cannot run).
- **#79 — agent-node CSI.**
- **#30 — metrics-server APIService blocks namespace discovery.** Root-caused and *refuted* as a storage bug; the fix is one flag.
- **The 16 datastore-declaration bypass sites** (8 correctly silent, 2 design questions) — see `reports/p5-datastore-declaration-residual.md`.
- **kube size-license semantics.**

## P5 items opened by the P4 gate and the babysit

- **renet i18n baseline: re-based explicitly, not silently.** The wave's baseline growth is **28
  entries, not 41** — measured by diffing `pkg/i18n/baseline.json` against the pre-wave commit. Of
  those, **22 are `fmt.Errorf` internal wraps** (the sanctioned class) and **6 are user-facing**, all
  six enumerated by name in the commit that re-based them (2 × `cobra.Short` and 3 × `fmt.Printf` in
  `cmd/renet/datastore_volumes.go`, 1 × `fmt.Sprintf` in `pkg/nodeteardown/nodeteardown.go`). No
  `renet job` strings appear in this wave's growth at all; if 41 included those, they predate this
  snapshot and are someone else's debt to own. renet's house style is `i18n.T` (288 vs 52 raw), so
  the six are still an anomaly and are owned here. **Two P5 items:** internationalize the six, and —
  the structural bug — **teach the gate to tell "internal error wrap" from "user-facing"**, because
  today it is green *because* they were laundered: it cannot fail for this reason by construction.
  *(This entry is itself an instance of the counting problem below: the ledger arrived saying 41.)*
- **`noUncheckedIndexedAccess` is off, and the linter will tell you to delete real guards.** Because
  the flag is unset, `map[key]` is typed as always-present while returning `undefined` at runtime, so
  every absence check written against it reads as dead code. `no-unnecessary-condition` flagged 14 of
  them in the P4 wave, and **every single one was load-bearing**: `if (!record)` in `getDatastore` IS
  the exit-5 not-found path; `if (!field)` in `resolveDefaultKey` IS what rejects an unknown config
  key; `state[ref]?.attachedTo` crashes without the `?.`. Taking the linter's advice literally would
  have shipped a family of silent bugs — a not-found that returns undefined, a validation that stops
  validating, and several crashes.

  It wears a **second costume that is easier to fall for**: three lines of the form
  `const record = await getDatastore(ref);` where the *binding* is unused but the **call is the
  guard** (`getDatastore` throws exit-5 on a miss). The naive "unused variable" fix deletes the whole
  line and takes the existence check with it. The correct fix is to drop the binding and keep the
  call.

  A trap for whoever pays this down: **annotating the variable does not work.** `const x: T | undefined
  = map[k]` still fails, because TypeScript narrows a `const` straight back to the initializer's
  (lying) type. The lookup must go through a helper whose *declared* return type is `T | undefined`;
  that is what survives narrowing. Enabling the flag properly costs **194 type errors in
  `packages/cli` alone** — hence P5, not a babysit fix.
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

## The TENTH broken gate: nothing can see an orphaned CLI translation key

Found while executing ruling G (delete `runBatchParallel`), which orphaned two i18n keys. The question
"will a gate catch this?" was answered **red-first, not by reading code**: plant
`commands.repo.zzTestOrphanKey` in `en/cli.json` with no caller anywhere, and see who complains.

Nobody does.

- **`check:i18n:key-usage` → exit 0.** It validates the *opposite* direction (every `t()` call resolves
  to a key that exists), and it only scans **www source files** — it never opens the CLI.
- **The `i18n/no-unused-keys` ESLint rule did not fire** on the CLI locales either.
- The only thing that spoke up was **`cross-language-consistency`**, and it complained about
  **asymmetry** (key in `en`, missing in `ar`/`de`/…), not about the key having no caller.

So a CLI translation key whose last caller is deleted, but which remains present in all 13 locales, is
**completely invisible**. Deleting the two `runBatchParallel` keys was only safe because they were removed
from English too — which converted an *orphan* into an *asymmetry*, and asymmetry is the only property
anything watches. Dead i18n weight can accumulate indefinitely and no gate will ever say so.

**P5 fix:** point an unused-key check at the CLI locales with the CLI as its source dir — the rule already
exists, it is simply not aimed at this package.

## F6 is the prerequisite for paying down the size debt, not a nicety

The `command-tree.json` freshness gate added in this wave is what makes the deferred
`command-metadata.ts` / `datastore.ts` / `machine/status.ts` split **safe to attempt** in P5. Splitting a
command-registering module can shift registration order; without a gate that regenerates-and-diffs the
tree, that staleness would land silently beneath four validators and two ESLint rules that all read it.
Do the split *after* F6 exists, never before. (See the BLOCKER text on those three files for the full
failure mode: plane re-attribution, silent tree staleness, and guard orphaning that fails OPEN.)

## Numbers that turned out to be folklore (P5, instrumentation)

A pattern worth naming, because it recurred three times in one phase and each time a decision rested on it:

| Number | Claimed | Actual |
|---|---|---|
| renet i18n baseline | "frozen at 2970"; then "+41 user-facing" | growth is **28** entries: 22 sanctioned `fmt.Errorf` wraps + **6** user-facing. Four sources gave four values; nobody wrote down what is counted |
| CLI orphan i18n keys | 408 | **2** real orphans × 12 locales = 24 (408 was a docs gate double-counting 58 stale keys across languages) |
| Stale translator keys | 82 | **130**, and *both numbers are real* — they answer different questions. 82 is the literal output of `check:i18n:hashes` ("English values changed for 82 key(s)", CLI-only, hash-vs-current). 130 is the hash manifest derivation (120 hash-stale + 4 missing + 8 still-English) and is the safe superset to staff off. The failure here is not a wrong count, it is **two oracles with no stated scope** |

`i18n:naturalize-status` deserves its own line: it reports **"all 12 locales OK"** and, by its own output,
fails only when a *whole language* is absent. It cannot fail an individual stale key — so it cannot fail for
the reason anyone consults it.

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

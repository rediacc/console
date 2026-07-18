# P0 Gate Review — Spec Consistency + Rulings

Reviewer: Fable (P0 pre-gate, fully-autonomous mode; this review stands in for the user
at this gate). Date: 2026-07-10. Subject: `docs/design/spec/01..05` against the
authoritative suite `docs/design/01..09` + README. Spike-dependent items (NetworkPolicy
proxy rule → spike e; PKI file-set detail → spike d) are marked PENDING-SPIKE and were
not re-litigated here.

---

## VERDICT: APPROVED-WITH-RULINGS

The five specs are individually strong (every one verified its code citations and
flagged its own deviations honestly), but they were written in parallel and disagree at
four load-bearing seams. Two of those (volume layout, bridge dispatch model) are
MAJOR: P1 cannot start until spec 01 applies the rulings below. Nothing found requires
re-opening a suite decision beyond the one mount-path override spec 01 itself flagged
for sign-off (approved, R1).

Per-file dispositions:

| File | Disposition |
|---|---|
| `01-renet-packages.md` | **CONDITIONAL — targeted rework before P1**: §1.2 volume layout (loses C1), §1.7 package name (loses C10), §4 bridge ledger (loses C2, counts stale), §1.8/§4 registry rows (loses C3). §3 (registry/attach/fencing/group-snap) approved as written. |
| `02-reporuntime-contract.md` | APPROVED with fixes: C4 (label), C5 (health), C6 (descriptor path), C12 (Role enum), plus the C1 path wording in §1.7. Its §3 dispatch model WINS C2. |
| `03-cli-contracts.md` | APPROVED with fixes: C7 (add `--cluster` to datastore create), C8 (local-fork refusal scope), storage add/remove rename (R3), health-window flags (G6). Exit-code table, @place table, idempotency table, per-leaf contracts all approved. |
| `04-config-schema-v3.md` | APPROVED with fixes: C7 (lift `cluster` out of the backend union), C15 (set-placement ghost verb), G3 (registryPort), C11 (merged secret caps), C14 (holders shape). The persist unification + migration ledger approved as written — the strongest file of the five. |
| `05-k8s-templates-and-fork-hygiene.md` | APPROVED: wins C1, C3, C4, C6 and most of C5. Fixes: mount-path examples must adopt R1 (`/mnt/rediacc-ds/<name>`), C5's exit-42 carve-out, C12's `REDIACC_WRITES` plain-attach example. |

---

## 1. Rulings on the queued gate decisions

**R1 — Mount-path override `/mnt/rediacc-ds/<name>` (spec 01 §3.2 vs suite 02 §1 / 04 §6): APPROVED.**
The suite's `/mnt/rediacc/ds-<name>` nests every named mountpoint inside the default
datastore's own BTRFS mount: named attaches would require the default mounted,
`detach default` would EBUSY under any named mount, and default-pool exhaustion would
break named attach — exactly the blast-radius coupling F8's `ds-control` exists to
avoid. Every property the suite wanted from the path (deterministic from the name,
identical across machines so kine PV specs never rewrite, per-machine collision refusal)
survives the sibling scheme. Consequence: spec 05 must update its `<ds-mount>` examples
(`/mnt/rediacc/ds-alpha` in §2, `/mnt/rediacc/ds-<ds>` in §4 step 5) and the suite
files 02/04 get the one-line edit in the as-built pass.

**R2 — U5 leaf count (153 vs "~90"): the tree-as-drawn is the contract.**
> **[SUPERSEDED 2026-07-13 by spec/03 §0 + ruling Q10.]** R2 correctly retired "~90" as bad
> arithmetic, but its own replacement figures then failed the same way: the 162 baseline was
> off by one (spec/03 §6.7's header contradicted its own table) and operator commits moved the
> live tree by 19 commands within days. **The count is retired entirely. The MAPPING is the
> contract** (spec/03 §6): every live command carries a disposition row, every row resolves to
> a real command, checked mechanically against `command-tree.json`. R2's substance survives
> unchanged: no unnamed scope cuts, and the simplification claim restated honestly.

Spec 03's enumeration (153 target leaves incl. the U1 `machine infra` subtree 06 §1
forgot to draw; 162 current leaves all mapped) is accepted as the P4 contract. The
"~90" prose figure is retired as wrong arithmetic, not a target to hit by cutting
scope — spec 03 was right to refuse unnamed cuts. The simplification claim is restated
honestly: 162 → 153 with the DAILY surface consolidated (config 57 → 25, repo plumbing
under `repo admin`, five backup surfaces unified). README/06 drop the "~90" figure in
the as-built pass.

**R3 — U2 `storage create/delete`: RENAME to `storage add` / `storage remove`.**
A storage record registers an EXISTING external endpoint (S3 bucket, rsync target); by
06 §7.1's own rule that is add/remove. Shipping a violation of the convention in the
same tree that introduces the convention would gut R2-F18's entire value
(predictability). Two-line change in spec 03 §5.7 + §6.2 (`config storage remove` →
`storage remove`). U2b's pick (`storage list <name> [--reveal]` absorbing
`config storage show`) is confirmed.

**R4 — U3 `repo push --up` deletion: APPROVED.**
Follows directly from 06 §6.5: a pushed copy is a backup artifact, not a second live
repo; today's `--up` boots the same GUID under the same name on the destination, which
is precisely the retired two-places behavior. Replacement flows (`backup restore
<ref>@<place> --up`, `repo migrate`) are adequate and better named. P4 must update the
documented CLAUDE.md/docs snippets (`repo push ... --to ... --up`) — already a P4 gate
item (06 §8), no new obligation.

**R5 — U8 backup schedule stays per-machine systemd: CONFIRMED.**
Spec 01 §4 keeps all 9 `backup_*`/`checkpoint_*` bridge functions unchanged and touches
none of the schedule/reconcile machinery; spec 03 §5.6's strategy-records-in-config +
machine-scoped runs model is exactly today's proven shape. No contradiction found.

**R6 — Datastore mutating verbs under `REDIACC_ALLOW_CLUSTER_OPS`: class APPROVED, env
name KEPT for this program.**
The CLASS is coherent: a datastore verb moves/destroys every repo in the pool at once —
cluster-scale blast radius — and one operator unlock is also exactly what an agent
sandbox needs for `--writes local` fork-attaches. The env var's NAME is historical, but
renaming it mid-program is operationally wrong: ancestry-verified overrides must be
exported in the shell that launches agents and CANNOT be set later (09 §0.5 /
README rule 5), so a P4 rename would strand P5/P6 validation runs and CI wiring
(07 §5) for zero behavior change. Semantics addendum: the per-name unlock value matches
the SUBJECT's name — cluster names for cluster verbs, datastore names for datastore
verbs, or `*`. Help text describes the class as "infrastructure operations unlock". A
cosmetic rename (e.g. `REDIACC_ALLOW_INFRA_OPS`) may be revisited after the program,
not during it.

---

## 2. Contradictions (winner, loser, exact fix)

### C1 — Volume layout: THREE layouts → spec 05 §2 WINS. [MAJOR]

- Spec 01 §1.2: `repos/<repo>/{images/<vol>.img, volumes/<vol>/}` — mounts INSIDE the
  repo folder.
- Spec 02 §1.7: image "under `<RepoPath>/volumes/<pvc>/`", sublayout deferred.
- Spec 05 §2: `repos/<repo>/volumes/<pvc>.img` + mounts at
  `<ds-mount>/mounts/volumes/<repo>/<pvc>/`, with the explicit invariant **no
  mountpoints inside `repos/<repo>/`**.

Ruling: spec 05. The fork unit is ONE reflink of `repos/<repo>`; a live ext4 mountpoint
inside that tree makes `cp --archive --reflink=always` either FAIL (reflink cannot
cross filesystems) or, under any fallback, byte-copy decrypted plaintext into the fork —
spec 01's own fork procedure (§1.2 `ForkNamespacePrepare`: one reflink after syncfs, no
unmount step) is unexecutable on spec 01's own layout. Spec 05's scheme mirrors the
docker world exactly (image files in the pool, `mounts/` tree outside the snapshotted
unit), keeps PV objects stable across cluster fork/migrate (paths reference
`<ds-mount>/mounts/volumes/<repo>/<pvc>`, deterministic and unchanged), and carries the
explicit CSI-adoption section (F6). Spec 01's stated reason for its `images/` split
(file-vs-mountpoint name collision) dissolves once mounts leave the repo folder.

Fixes: spec 01 §1.2 layout block + §1.3 path helpers (`ImagePath` →
`repos/<repo>/volumes/<vol>.img`, `MountPath` → `mounts/volumes/<repo>/<vol>`); spec 02
§1.7 `ProvisionVolumes` row and CT-09 wording adopt image-at
`<RepoPath>/volumes/<pvc>.img`, mount under `<ds-mount>/mounts/...`.

### C2 — Bridge dispatch model: spec 02 §3.3 WINS; spec 01 §4 reworked. [MAJOR]

Spec 02 [P0-DECIDED]: `kube_deploy`/`kube_namespace_create`/`kube_namespace_fork`/
`kube_namespace_delete`/`kube_pv_*` RETIRE; `repository_up/down/fork/status/health`
become runtime-generic, dispatching through `reporuntime.Detect` + the on-datastore
descriptor. Spec 01 §4 instead KEEPS all four `kube_namespace_*`/`kube_deploy` with
param changes and renames `kube_pv_*` → `kube_volume_*` — leaving the CLI to branch
per runtime when choosing which function to call, which is the exact "flag-routing seam
with no enforced contract" disease 02 §9 diagnoses, merely re-keyed from flags to
placement. Spec 02 explicitly fixed the DIRECTION and delegated only the ledger to
spec 01; the ledger failed to follow it.

Ruling: unified dispatch (spec 02). Spec 01 §4 rework requirements:
1. Retire `kube_deploy`, `kube_namespace_create`, `kube_namespace_fork`,
   `kube_namespace_delete` as CLI-callable seams (bodies fold into `KubeRuntime` behind
   the runtime-generic `repository_*` family). `kube_volume_provision/delete` become
   internal plumbing or retire the same way.
2. ADD `repository_health` — the health gate (specs 02/03/05 all depend on it) has NO
   bridge surface in the current diff. Orphan found both directions: CLI verbs
   `repo migrate`/`cluster migrate`/`rehearse`/`restore --up` need it; nothing provides it.
3. `repo logs` / `repo exec` (spec 03 §5.4) map to `container_logs`/`container_exec`
   for docker but have NO kube-side bridge function; the rework must give them a
   runtime-generic surface (or per-runtime pair) — second orphan.
4. `kube_secrets_apply` (spec 01's ADD) folds into the unified `InjectSecrets` path
   unless the rework finds a concrete caller that cannot ride `repository_up`'s
   existing vault/stdin channel.
5. The headline numbers (152 → 154; −5/+7/6/5) are stale after the rework; recount.
6. `kube_identity_rewrite` params: align with spec 05 §3 — `operation` (required) PLUS
   `role` (fork|rehearsal) and `writes` on the fork arm (C13).
Cluster-layer functions (`kube_identity_rewrite`, `kube_join`, `kube_node_remove`,
`kube_prep_fork`, `kube_health` as the DISTRO healthcheck) stay separate — spec 02
§3.3 already rules cluster verbs are not dispatched through RepoRuntime. The reworked
§4 table is the one section that returns for gate re-review.

### C3 — Registry: spec 05 §5 WINS (per-repo zot units); spec 01 §1.8/§4 reframed.

Spec 01 frames F4 as "default StorageDir change only" on the machine-level zot — but a
SINGLE machine instance with its store inside ONE repo's folder is incoherent for
multiple repos, and the machine-level pull-through cache must keep its upstream-mirror
role. Spec 05's design (one `rediacc-registry-<networkID>.service` per opted-in repo,
sync disabled, store at `repos/<repo>/registry/`, port range 21000-28999, logical host
`registry.<repo>.rediacc.internal` wired via registries.yaml + hosts.toml, units
started at datastore attach — failover story included) is the only complete solution.
Fixes: spec 01 §1.8 + §4 rows reframe (`kube_registry_up`/`kube_registry_wire` keep the
CACHE role unchanged; the per-repo unit lifecycle is internal to datastore
attach/detach per spec 05 §4 step 5 — state whether that needs a bridge-visible verb);
spec 04 adds the port field (G3).

### C4 — Secret label convention: spec 05 (`rediacc.io/injected=true`) WINS.

Spec 02 §1.5a proposed `app.kubernetes.io/managed-by: renet` + `rediacc.io/repo` but
explicitly deferred to the fork-scrub spec; spec 04 §5.2 copied the managed-by
convention. Spec 05 (the fork-scrub owner) and spec 01 both use
`rediacc.io/injected=true` — on EVERY renet-generated object, which the scrub (F4.1)
and teardown enumerate. Fixes: spec 02 §1.5a + CT-01 kube-leg text ("zero
managed-by=renet Secrets" → "zero rediacc.io/injected=true Secrets"); spec 04 §5.2
label bullet. Additional labels (managed-by, `rediacc.io/repo`) may ride along as
informational; the CONTRACT key is `rediacc.io/injected`.

### C5 — health() contract: reconciled to ONE contract (spec 05 base + spec 02's sentinel).

Both specs independently chose a dedicated `health()` over the `info()` exit-code
convention — that decision is unanimous and CONFIRMED. The mechanics conflict
(spec 02: 0/any-nonzero, 60 s single-shot; spec 05: 0/75/nonzero, 30 s/attempt, 300 s
window). Ruled contract:

- exit 0 ⇒ healthy; **exit 75 (EX_TEMPFAIL) ⇒ warming up, retry**; any other nonzero ⇒
  unhealthy, gate fails immediately. The gate runs right after cutover/boot where
  warm-up is the COMMON case; a single-shot probe would force every app to implement
  its own retry loop inside health().
- **exit 42 is reserved** (the executor's function-not-defined sentinel,
  `rediaccfile.go:220`) ⇒ treated as "health() undefined" → runtime-readiness fallback
  → Unknown. Spec 05 must document this carve-out in its §6 table; a user health()
  must not return 42.
- Per-attempt timeout 30 s (a timeout counts as one 75); gate window default 300 s.
  The retry LOOP lives in the gate caller (cluster/migrate layer); `RepoRuntime.Health`
  is one evaluation — spec 02 adds a "warming" disposition to `HealthReport` (exact Go
  shape is spec 02 owner's call).
- Layering per spec 05 §6 (distro /readyz → k8s readiness / container-health default →
  health()); spec 02's discovery-order + first-unhealthy-wins rule for
  multi-Rediaccfile repos carries over.
Losers: spec 02 §1.8 (timeout + missing 75), spec 05 (42 carve-out). Spec 03 gains the
window flags (G6).

### C6 — On-datastore descriptor file: spec 05 WINS.

Spec 02 §3.3: `<ds-mount>/.rediacc-ds.json`; spec 05 §2/§7:
`<ds-mount>/.rediacc/datastore.json`. One file must exist, carrying
`{name, backend, cluster?, writes?, k3sVersion, k3sVersionWrittenAt}` (merge of both
content lists). Spec 05's location wins — `.rediacc/` is already the metadata-directory
convention (repo-scoped `.rediacc/`, k3s data-dir under `<mount>/.rediacc/k3s`). Fix:
spec 02 §3.3 path.

### C7 — Datastore `cluster` backref: field placement + missing CLI flag.

Spec 02 §3.2 [P0-DECIDED, correct]: runtime derives from the datastore's cluster
backref, set at `datastore create --cluster <name>`, immutable (one-world datastores).
Spec 04 §1.2.2 put `cluster` INSIDE the rbd backend arm (required) and gave the local
arm none — which (a) forbids cluster-attached LOCAL datastores, contradicting suite
02 §1 (local-NVMe tiering next to RBD in a cluster), suite 03 §3 (local-tier members
documented outside the group instant), spec 03's own `--group` local-tier warning, and
spec 01's registry (`cluster` label independent of backend); and (b) forbids
docker-world rbd datastores (the `machine set-ceph` replacement, 06 §2). Spec 03 §5.3
compounds it: `datastore create` has NO `--cluster` flag at all, so the runtime-derivation
keystone has no CLI source (spec 04's own transform-7 warning text uses the flag).

Fixes: spec 04 lifts `cluster?: resourceName` OUT of the backend union to a top-level
optional field on `DatastoreConfigSchema` (both backends may carry it; set ⇒ kube repos
only, unset ⇒ docker repos only, immutable per spec 02). Spec 03 §5.3 adds
`--cluster <c>` to `datastore create` (optional; validated against config clusters;
name recorded as the one-world backref). Spec 01 §3.1 already agrees; no change there.

### C8 — Local-backend datastore fork: spec 01 WINS.

Spec 01 [P0-DECIDED]: `datastore fork` on a local backend is REFUSED in v1 (no
block-level clone primitive; repos inside fork by reflink). Spec 03 §5.3 only refuses
the cross-machine case, implying same-machine local forks work. Fix: spec 03's error
row becomes "local-backend datastore → 2, teaching: repos inside a local datastore
fork individually by reflink (`repo fork`); datastore-level fork needs the rbd backend".

### C9 — Mount-path scheme in spec 05: adopt R1.

Spec 05 §2 example (`/mnt/rediacc/ds-alpha`) and §4 step 5 (`/mnt/rediacc/ds-<ds>`)
use the suite's superseded nested path. Fix: `/mnt/rediacc-ds/<name>` throughout,
including the rendered PV `local.path` values.

### C10 — Package name: `pkg/reporuntime` (spec 02) WINS over `pkg/runtime` (spec 01 §1.7).

`pkg/runtime` shadows the stdlib import in any file touching goroutines/GC — spec 02's
rejection is technically decisive. Spec 02's file layout (adds `env.go`, `leak.go`,
`factory.go`, fixtures, `CONTRACT.md`) is a superset of spec 01's and stands. Fix:
spec 01 §1.7 name + file list.

### C11 — Secret size caps: MERGED contract.

Spec 04: env 32 KiB / file 256 KiB per value. Spec 05: 256 KiB per value + 512 KiB
aggregate per repo per mode (from the 1 MiB apiserver Secret cap). Both rationales are
valid and stack. Ruled: **env 32 KiB per value, file 256 KiB per value, 512 KiB
aggregate per repo per mode.** Both files state all three numbers; spec 04's
`SecretEntrySchema` superRefine enforces per-value, a family-level refine enforces the
aggregate; migration transform 8 re-validates all three.

### C12 — Role enum + REDIACC_WRITES on plain attach.

Spec 05 §1e defines `replica` in the ROLE enum (reserved for `repo replicate`) and
spec 01's `kube_deploy` role param lists it; spec 02 §1.2's Go `Role` consts omit it.
Fix: spec 02 adds `RoleReplica` (documented as P3-consumed). Separately, spec 02 and
spec 01's registry define `writes: ""` for a plain (non-fork) attach, while spec 05
§1e's ConfigMap example shows `REDIACC_WRITES: "ceph"` for a primary — fix the spec 05
comment: plain attach ⇒ empty/omitted, `ceph|local` only for fork attaches.

### C13 — `kube_identity_rewrite` schema: add `role` + `writes` to the fork arm
(spec 01 §4 row), matching spec 05 §3's `IdentityOp` + Role + writes-disposition inputs
(F7 rewrites the ROLE ConfigMap with both).

### C14 — Holders shape: spec 04 `state.datastores.*.holders` has `{loops, dm}`;
spec 01's machine registry has `{loops, dm, volumes}`. Align (spec 04 adds optional
`volumes`), since reconcile mirrors the machine file.

### C15 — Ghost verb `repo set-placement` (spec 04 §3.2 transform 3): REMOVED.

The migration error text offers `rdc repo set-placement`, which exists nowhere in
spec 03's tree. Ruled: do NOT add a new leaf for a one-time migration path —
`config reconcile` fills placement by GUID match (spec 04 §4.2), and the manual escape
hatch for an unreachable machine is `config edit` (schema-validated). Fix the error
text to name those two.

Consistency confirmations (no action): manifests location — all three specs agree on
`repos/<repo>/manifests/` and the death of `{ds}/manifests/<cluster>/<ns>` (suite 02
§6's "KEEP the manifests layer" is honored as the LAYER, path refined; sanctioned).
Secret object names `rediacc-env`/`rediacc-files` — specs 02/04/05 agree. ConfigMap
`rediacc-role` — specs 02/05 agree. `REDIACC_SECRET_` prefix parity — specs 02/04/05
agree. Exit-code layering — no collision: CLI codes 0-15, renet's 10 (the only
cross-layer code, propagated by design), Rediaccfile hook codes (42 sentinel, 75
warming) never propagate to the CLI surface (the gate maps to exit 13); passthrough
verbs (`run`, `repo exec`, `term connect -c`) are documented deviations. Placement
resolution algorithm (spec 03 §2.3) matches spec 04 §1.2.1's resolver and spec 02
§3.2's dispatch. `cluster fork --writes` defaulting to `ceph` (spec 03) deviates from
the datastore-level no-default rule DELIBERATELY and acceptably: porcelain may default
to the durable arm; the plumbing (`datastore attach`) still refuses. `repo replicate`
at gate B (not D) accepted: additive fork-attaches, no disruption to the parent;
overlay budget enforced via storage-health (F10) — tension noted for the P4 MCP gate
record.

---

## 3. Suite-alignment check ([P0-DECIDED] vs explicit suite decisions)

Swept every [P0-DECIDED] in all five files. Only one contradicts an explicit suite
decision: spec 01 §3.2's mount path vs 02 §1/04 §6 — flagged by the spec itself,
APPROVED as R1. Everything else refines rather than contradicts. Notable sanctioned
refinements, recorded: manifests relocation into the repo folder (02 §6 KEEP-list item
honored at the layer level); `PrepFork` demotion to cross-site-cutover-only (02 §6
KEEP honored; the hot fork path replaces its fork role per 04 §2 — spec 01 §5.8
resolved this correctly); `kube_prep_fork`/`kube_join` reuse for P2 verbs; `base` as
the reserved birth tag with `latest` demoted to an ordinary tag (implements R2-F5's
"retire the magic", does not contradict it); `main` as the fresh-create grand tag with
migrated grands keeping literal `latest` (data-not-behavior difference, accepted);
spec 03's deletion of per-command `--json`/`--output` flags (implements the §4.6
single-switch rule). The `two-Deployments-behind-one-Service` canary and release-ladder
items are P3 scope and were correctly left out of P0 files.

---

## 4. Gaps vs 09 §P0's deliverables list (owner-assigned)

All sixteen named P0 deliverables are covered by at least one file: renet package
design (01), bridge diff (01 — reworked per C2), RepoRuntime + contract tests (02),
CLI contracts (03), config v3 (04), k8s templates (05 §1), fork PKI/scrub (05 §3),
failover sequence (05 §4), registry (05 §5), health (02+05, reconciled per C5), skew
(05 §7), CSI layout (05 §2), @place table (03 §3), exit codes (03 §1), replicate CRUD
(03 §4.4), restore-vs-promote (03 §4.3). Residual holes the files jointly leave:

| # | Gap | Owner |
|---|---|---|
| G1 | RepoRuntime sentinel → CLI exit-code mapping is nowhere stated (`ErrHoldersPresent`→14? `ErrWrongRuntime`→12? `ErrRoleViolation`→2, `ErrNotDeployed`→5). One four-row table. | spec 03 (§1 addendum), spec 02 concurs |
| G2 | Health-gate + logs/exec bridge surface (`repository_health`; runtime-generic logs/exec) — absorbed into the C2 rework. | spec 01 |
| G3 | Per-repo registry port: allocated at `repo create`, recorded "next to networkId" (spec 05 §5) — networkId lives in v3 `state.repos`, which has NO port field; `REDIACC_REGISTRY`/`REDIACC_REGISTRY_HOST` also missing from spec 02's env contract. | spec 04 (state.repos field), spec 02 (env note) |
| G4 | `ds-control` creation is unowned: suite 02 §1 makes it the CP default, spec 01 calls it "an ordinary named datastore", but no spec says `cluster create` auto-creates/attaches/sizes it. One behavior paragraph in the cluster-create contract. | spec 03 (§5.5), P2 implements |
| G5 | Datastore-fork records in the machine registry: key shape (`name:tag`? tag grammar reuse), and the `--no-auto` boot-reattach flag (spec 03) has no persistence field in spec 01 §3.1's schema. | spec 01 |
| G6 | Health-window/timeout flags (`--health-window`, per C5 "exact flags owned by the CLI spec") absent from spec 03's `repo migrate`/`cluster migrate`/`cluster rehearse`/`backup restore --up` contracts. Add with defaults (30 s attempt / 300 s window) or state defaults-only-v1 explicitly. | spec 03 |

PENDING-SPIKE (out of scope here, correctly marked in the files): the NetworkPolicy
allow-proxy candidate selection (spike e; spec 05 ships both candidates verbatim), PSA
`baseline` hostPath verification (spike e), the exact `server/cred/`+`agent/` PKI file
set and bootstrap-restore hazard (spike d; spec 05 §3 lists the five verification
items), dm-thin vs dm-snapshot (spike f; spec 01 §1.8 keeps the `COWClone` surface
swap-ready).

---

## 4b. Re-review addendum (2026-07-10, later): spec 01 §4 rework — CLEARED

The one returning item is verified against the file (not the owner's summary):

- C2 applied correctly: runtime-generic `repository_*` dispatch via
  `reporuntime.Detect` + the on-datastore descriptor; `kube_namespace_create`/
  `kube_deploy`/`kube_namespace_fork`/`kube_namespace_delete`/`kube_pv_*` retired as
  bridge functions with bodies folded into `KubeRuntime`; the cobra verbs
  (`kube_namespace.go`, `kube_deploy.go`, `kube_volume.go`) correctly survive as
  machine-local plumbing with no bridge functions behind them (§2.6/§2.8 updated to
  match). Cluster node-infra family correctly left outside RepoRuntime.
- Arithmetic verified: 152 − 11 + 9 = 150; datastore 10→13, kube 18→10,
  repository 33→36 all recount correctly; §4.4's regen numbers (9 adds + 4 renames
  needing e2e refs, 11 deletions swept) match.
- G2 closed: `repository_health` added with the C5 ruled contract verbatim (0 / 75
  warming / 42 sentinel→fallback→Unknown / other nonzero; 30 s per attempt; retry loop
  in the CLI-side gate caller). `repository_logs`/`repository_exec` added
  runtime-generic; exec keeps the grandGuard class.
- C2 item 4 honored: `kube_secrets_apply` not added, with the explicit
  no-caller-outside-repository_up note.
- C7 (top-level `cluster` backref, disambiguated from `ceph_cluster`), C13
  (`kube_identity_rewrite` operation + role + writes), G5 (`no_auto`/`autoAttach`,
  fork records keyed `<parent>:<tag>` with the grammar argument), C3 (two zot roles,
  per-repo units bridge-invisible, lifecycle inside attach/detach), C6 (descriptor at
  `<ds-mount>/.rediacc/datastore.json`, two-files-two-jobs paragraph), C14 (holders
  `volumes` mirror note), C1 (layout + holders example paths), C10 (`pkg/reporuntime`,
  layout deferred to spec 02) — all present and consistent. Residue grep for the old
  draft (images/ split, `.rediacc-ds.json`, 154 count, live `kube_volume_*` bridge
  names, `pkg/runtime`) is clean.

Two non-blocking P1 implementation notes, recorded here so they are not lost:

1. `repository_health`'s row does not state HOW the verdict travels to the CLI. Since
   hook exit codes never propagate to the CLI surface (§2 confirmations), the answer
   is: renet exits 0 for a COMPLETED evaluation and the verdict rides the JSON output
   (a `HealthReport` with state healthy|warming|unhealthy|unknown); renet's own
   nonzero exits remain infrastructure failures (CLI exit 14).
2. Spike d's correction (kine `/bootstrap` restores the parent CA byte-identical after
   a bare `tls/` removal; true re-mint is the 8-step scrub) supersedes the shorthand
   in spec 01 §1.5's `OpFork` arm ("delete `<data-dir>/server/tls/`") and spec 02
   §1.7's cluster-boundary note. Both should point at spec 05 §3's corrected F1 step
   list as the single procedure owner once the dispatched spec 05 rewrite lands — the
   fork-PKI procedure must have exactly one home.

DISPOSITION: spec 01 is now APPROVED. No returning items remain from this review; the
spec set is gate-complete once the spec 05 spike-d rewrite lands (tracked separately,
not a finding of this review).

## 5. Gate instructions

1. Spec owners apply C1-C15 + G1-G6 to their own files (do not cross-edit); spec 01's
   reworked §4 bridge table comes back for a focused re-review — it is the only
   returning item.
2. The suite as-built pass (program exit, 09 §2.5) picks up: R1 path in 02 §1/04 §6,
   R2's "~90" removal in README/06, R3's tree edit in 06 §1, C1's layout in any suite
   mention.
3. Rulings R1-R6 and the C-list are final at this gate; re-litigation only with new
   spike evidence.

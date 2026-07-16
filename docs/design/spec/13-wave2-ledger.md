# Wave-2 ledger — findings, rulings, and carried items (2026-07-16)

The durable record of the wave that drove the 0707-1 stack toward green after the P4
gate. Same contract as `12-carried-debt.md`: debt that lives only in a session's
context is amnesia with a countdown. Where an item is DONE it is recorded so it is not
re-litigated; where it is OPEN it carries an owner-phase. Bug numbering continues the
program ledger.

## Closed this wave (recorded so the fixes are not re-derived)

### #29 — CLOSED at root. The invisible holder was a private mount namespace
The program-long "open dm device with no userspace owner" was a workload pod's process
(`tail -f /dev/null`) orphaned to init when `kube uninstall` killed its containerd-shim
but not the container. Its private mount namespace kept the pod's overlay rootfs and
`/etc/hosts`-class binds mounted off the fork's dm device: open count 1, no host mount,
no fd, no sysfs holder — every probe the program ever ran looked only in the host
namespace. Root-caused live in suite 17 test 5 the moment the fork discard was
un-muffled (`2>/dev/null; true` had hidden the failure on every prior run; the failure
then surfaced three tests away at the group-snapshot delete). Fix (renet `cd414b3`):
`ScanNamespaceHolders` (path AND device matched anywhere in the mountinfo line; the
ns/mnt-differs discriminator is what keeps scope sane — during teardown every HOST
process legitimately shows the target), k3s-killall semantics in `kube uninstall`,
namespace-aware holder probes everywhere (the class-d verdict is structurally
unutterable without the scan having run), destructive arms kill scoped holders and
retry once, non-destructive arms name-and-refuse. Live-verified against the actual
orphan. Suites 16 (12/12) and 17 (7/7) green — **B3 discharged**.

### #30 — guard fixed: it keyed on a condition type no API server emits
The finalize guard required `NamespaceContentRemoved=True`; real controllers emit
`NamespaceContentRemaining` (inverted polarity). The guard failed SAFE forever, exactly
as its own comment predicted, and the raw-conditions log built for that moment caught
it. Predicate now reads the real types (+ `NamespaceDeletionContentFailure!=True`,
absent-condition refuses); the firing unit fixture is the VERBATIM live dump (renet
`8073d0b`). A mock cannot prove its own fidelity — the cluster's actual words are the
fixture now.

### Quiesce scoped to fork paths (supersedes the blanket 6ac94e9 flush)
`SnapshotCreate`/`groupSnapCreate` take an explicit `quiesce` opt-in (renet `bce165d`);
the bare snapshot verbs returned to their documented crash-consistent contract (the
spec/12 REFUTED ruling stands); cluster fork passes `quiesce: true` (#440 one-rule:
a fork carries what you just wrote), with inner repo filesystems flushed FIRST (the
wave-1 round-20 gap). The test-mode dispatcher lost `--quiesce` (its FOURTH lost flag —
carry-in 10's derive-from-registry fix remains open) and was patched (`5a8bdb3`).

### Detach fail-loud + rbd rm deadline
`datastore detach` no longer warn-succeeds a failed `rbd unmap` (bounded retry, then a
holder-naming probe and a HARD failure). `RBD.Remove` grants itself `LongTimeout` when
the caller has no deadline — the 30s default killed a discard at 81% (the #28
"deadline that fits" class, renet `661a743`).

### Suite-17 test debts paid
Group-snapshot delete added to teardown ordering (`3c6febfd6`); the muffled fork
discards asserted (`94ed1d131`). Rule reconfirmed twice in one file: **a `; true` on a
step that can fail converts a product bug into an archaeology project.**

### CLI raw-key i18n gate (new, two halves, red-first)
`rdc machine status --help` printed the literal key `help.machine.containers`; no gate
looked at CLI t() resolution (the www key-usage gate scans www only — spec/12 gates
10/11). New: static t()-resolution gate (prints its own coverage limit; found a second
real leak, the `commands.repo.mount.*` spinner keys) + rendered-help scan over all 198
live Commander nodes (`f2f7d7fad`). Wired into the local `ci` chain AND `check:i18n`
(the Quality/i18n job's vehicle).

### Account e2e 12 reds (`account 640f1c9`)
Two root causes the briefing had as one: the injection helper needed BOTH the
`audit:write` scope and the hardened envelope's required `idempotencyKey`. Console
tests moved to the ref binding; the sidebar separator overflow was a real product bug
(`w-auto!` specificity). The team-test overflow assert was RIGHT all along.

## Rulings recorded (implementation in flight this wave)

Derived-routing family — full design + rulings in the wave's design doc and the round
log; summary: R1 migrate rewrites placement at END of phase 2 (authority transfer); R2
`:tag` migrate exits 2, multi-tag families refuse (family-loop DEFERRED on the
reflink-preservation VM question); R3 source images deleted post-phase-3 with
`--keep-source` opt-out (VM-verify `repository_delete` on an unmounted image first);
R4 `classifyFamilyPlacement` gains the observed-on-declared-PLUS-others duplicate
conflict; R5 `--accept-observed` scoped to unambiguous machine-arm drift; R6
verifyMount = GUID-presence probe injected once in `resolveRepoRef`, fail-open on
probe infrastructure failure. Note for the record: BOTH new flags stale
`check:ci-command-tree` AND `check:ci-cli-contract` — the "flags need no gate"
assumption is wrong; the tree carries per-leaf options.

## OPEN — carried forward with owners

1. **Replicate set-name slug aliasing (new, found by config-shape review).**
   `replicaSetNameFor` slugs `:` to `-`, so fork `shop:test` and a repo literally named
   `shop-test` produce the SAME set name (`shop-test-replicas`) and the same datastore
   fork tags. Repo names allow `-`, so it is reachable. Candidates: create-time refusal
   (names that collide with a sibling's slug) or a collision-proof separator. Fold into
   the **B1 live window** (replicate has never run live; its name handling is
   code-reading, not evidence). Owner: B1 campaign.
2. **B1 (exit blocker, unchanged):** `repo replicate`, `cluster rehearse`, release
   ladder — zero live executions. The slug edge above and the `state.replicaSets`
   lifecycle (refresh discard+re-fork under the same tag; remove cleans forks, labels,
   snapshot, state) are the specific things the live window must prove.
3. **Test-mode dispatcher flag drift (carry-in 10, now 4 instances):** derive the
   dispatcher's flags from the bridge ParamDef registry so the class dies. Owner: P5.
4. **Suite 16 optional cleanup:** replace its test-side `sync` workaround with
   `quiesce: true` on the group-snap call, proving the product mechanism in both
   suites. Owner: P5/P6 (low risk, do with the next suite-16 edit).
5. **Renet i18n baseline growth this wave:** +14 entries (7 detach/probe, 7 namespace
   holders), all internal-error/probe class, attributable per commit. Fold into the
   standing 41-string P5 item's resolution (catalogue-vs-baseline teaching gate).
6. **`machine remove` dangling placement:** removing a machine leaves
   `placement: {machine: <gone>}` families dangling; later verbs fail with a bare
   "machine not found" instead of a teaching error, and reconcile cannot auto-repair
   (declared placements are never auto-edited). Wants a refusal-or-teach at remove
   time. Owner: P5 (small).
7. **Orphan i18n key `commands.repo.migrate.optionFrom`** (the deleted `--from`) — and
   siblings of its class are invisible to every gate (the CLI orphan-key direction is
   spec/12 gate #10's known blind spot; the new static gate checks call-site→key, not
   key→call-site). Either extend the static gate with an orphan direction (respecting
   dynamic-key humility) or sweep with the routing-impl key work. Owner: P5.
8. **WSL2 fleet fatigue (operational note):** back-to-back `ops up --force` cycles
   drive ceph into `HEALTH_WARN: slow BlueStore ops`; the harness health gate then
   times out (~345s) on an otherwise healthy cluster, and the warning can persist while
   a write-path probe succeeds. Practice: after a force-reset, let the host settle or
   gate on the write-path probe rather than HEALTH_OK. Not a product bug.
9. **Vite audit time bomb:** GHSA-fx2h-pf6j-xcff's fix published 2026-07-16;
   freshness-deferred until 2026-07-17 UTC, then DEMANDED. Bump rides the push.
10. **Parked separate-PR work:** the www Italian accent fix
    (`~/.claude/.../parked/www-it-accent-fix.patch`, spec/12 ruling) — land as its own
    PR after this stack is green.
11. **Deferred by standing rulings, unchanged from spec/12:** the family-loop migrate
    (reflink question), #84 PSA/seccomp decision, #87 CSI staging redesign sequencing
    with #86 worker-node mint, the 188-command tutorial re-record debt, P7's docs
    rewrite baselines.

12. **Migrate's phase-1 delta base outlives its own prune (found during the routing
    live-verification).** After a clean `repo migrate`, the temporary phase-1 base
    image (a distinct GUID, unmounted) survived on BOTH machines despite
    `retainBasePrune` — pre-existing lifecycle, not the wave's R3 change (which
    deletes the MIGRATED repo's images and verified live). `machine prune` sweeps it;
    the prune-at-cutover should be made to actually fire. Owner: P5.

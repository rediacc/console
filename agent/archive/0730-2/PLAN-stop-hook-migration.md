# Plan: migrate the Stop hook from the single handover to `.agent/`

Delivered by the `stopplan` Plan agent, 2026-07-30. Recorded here because it
arrived as a message and would otherwise be lost to compaction.

## Verified by me against the artifacts (not taken on report)

- **The vacuity risk is REAL and is the plan's best catch.** `setup()` in
  `test-worklist-v5.sh` leaves the fixture without a usable git repo, so
  `git symbolic-ref --short -q HEAD` returns rc=128. Without the
  `WORKLIST_AGENT_BRANCH` override the new STATE check would be SKIPPED as
  `no-branch` across nearly the whole suite: a gate that never fires in its own
  tests, shipping green. Fixture must export the override.
- `hand_now`: 95 occurrences = 94 call sites + 1 definition. Matches.
- Detached HEAD: `rev-parse --abbrev-ref HEAD` returns the literal `HEAD` in
  `private/renet`, `symbolic-ref --short -q` returns empty. Confirms the choice
  of `symbolic-ref`; `abbrev-ref` would seed a junk `.agent/HEAD/` every rebase.

## Shape of the change

9 handover sites across `wl_store.py`, `worklist.py`, `wl_checks.py`,
`worklist_messages.py`. `--handover` is DELETED (clean break, operator decision);
`--state <me>` replaces it. Freshness gates `STATE.md` only.

New shape verdicts: `thin` (<250) | `bloated` (>4000, up from 1500) | `aimless`
(no `## Next action`) | `ok`. The 3-paragraph guard is DELETED: it was an
explicit proxy for the old 600-char cap, and `split("\n\n")` counts headings as
paragraphs, which is why the old message had to forbid headings. Today's
STATE.md would be `fragmented` under it.

## Three things the agent flagged. Two are now DECIDED; one residual stands.

Items 1 and 3 were operator decisions taken 2026-07-30 and are settled below.
Item 2 is NOT a decision, it is an accepted residual with no clean fix.

1. **The write-time refusal cannot be a hard gate on its own. DECIDED
   2026-07-30: the PreToolUse guard SHIPS WITH the migration, not after.** The
   old document lived at a TMPDIR path nobody would open with `Write`. STATE.md
   is a normal repo path, so any agent reaches for `Write` first and bypasses
   the CLI silently, WITHOUT KNOWING IT HAD. So
   `.claude/hooks/pre-edit/block-agent-state-shape.sh` registers on the existing
   Edit/Write matcher beside `block-suppressions.sh`, in the same change. It also
   enforces rewrite-not-append on STATE.md, which the CLI could never do. Step 8
   of the execution order is therefore NOT optional and must not be deferred.
2. **Per-branch breaks the single-writer invariant** that `worklist.py:311-314`
   depends on. Two sessions are live on this branch right now. Mitigation is
   flock + atomic replace + printing what you replaced. Explicitly NOT a full
   solution: two sessions can still overwrite each other's narrative.
3. **Detached HEAD: DECIDED 2026-07-30, report-only.** A named note says the
   check is blind; the stop is allowed. This is a deliberate, operator-approved
   departure from the `V_PR_UNREADABLE` precedent, which blocks. Rationale: HEAD
   detaches during every interactive rebase and this operator rebase-merges
   everything, so blocking every stop for a rebase is a worse failure than one
   turn of unenforced staleness. Accepted cost, stated so nobody re-derives it:
   a session sitting detached is never told its STATE.md went stale.

## Anti-vacuity control that matters most

T7b: after a `stale` block, running again with an UNCHANGED world must BLOCK
AGAIN. If `state_sig` were adopted on a stale verdict the gate would clear
itself without a rewrite. The adopt must fire only on `ok`.

## Ordering constraint

`state_doc["state_sig"]` and `["agent_boot_told"]` must be written ABOVE
`S.save_state` at `wl_checks.py:915`. `emit()` calls `sys.exit`, so anything
written below is silently dropped.

## Findings the agent surfaced but did not fix

- F2: a CLI write arm hitting a broken sibling prints a Stop-hook JSON block to
  stdout and exits 0, so a caller reads rc=0 and believes the write succeeded.
  Pre-existing; applies to `--state` identically.
- F3: `hand_now` omits `WORKLIST_TASKS_DIR` while case 144 supplies it, so all
  91 setup handovers record a signature against an empty task dir. Latent only
  because no fixture ages past 15 minutes. The plan fixes this.
- F4: cases 44 and 45 share one fixture and 45 has no `setup`; one reorder from
  silently passing on nothing.
- F5: five cases hand-roll `echo "  PASS: "` and `test-hooks.sh:153` counts that
  literal, so the two counters agree by convention rather than construction.

## EXECUTION-ORDER CORRECTION, found by attempting step 1 (2026-07-30)

**Step 1 CANNOT land on its own.** `wl_core.git_branch` was added exactly as
specified, verified across all six paths (real branch, detached, unusable .git,
env override, slash-slugging, explicit empty), and the suite then went
`260 passed, 1 failed`:

    == 143. the dead-code gate: every top-level def is referenced somewhere ==
      FAIL: dead code shipped: orphans=wl_core.py.git_branch

Case 143 requires every top-level `def` in the shipped modules to be referenced
at least twice across them (the def line counts as one). A function with no
caller is an orphan, and the gate is NOT vacuous: its own planted-orphan control
passed in the same run.

So `git_branch` must land in the SAME change as a consumer, which means steps 1,
2 and 5 are one atomic unit, not three. The plan already said step 2 must delete
the handover symbols in its own commit; the same constraint binds step 1 upward.

`git_branch` was REMOVED again rather than left orphaned, and the suite returned
to `261 passed, 0 failed`. The verified implementation is preserved verbatim in
the plan body above, so re-adding it costs nothing.

## Execution order

12 steps, in the agent's plan, SUBJECT TO the correction above. Step 2 must delete the handover symbols in the
SAME commit that adds the new ones: a half-deleted `wl_store` breaks the sibling
probe. Step 7 must confirm `git diff` shows NO change on any of the 91
setup-only `hand_now` lines; if any needed editing, `hand_now` was rewritten
wrongly and all 91 will flip at once.

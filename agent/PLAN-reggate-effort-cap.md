# PLAN: a bounded-effort cap for the stop-gate's regression-gate demands

Status: DESIGNED 2026-09-05, by a Plan agent under operator ruling. Load-bearing
claims re-verified against the source by d1589e0b before acceptance (see §9).

## 1. The problem, with tonight's measurement

The reggate judge (`.claude/hooks/stop/wl_reggate.py`) asks one question on every
stop where an artifact-detected fix landed: does anything stop this defect coming
back? When the answer is "nothing does", `apply_regression_verdict` returns
`("block", ...)` and `wl_checks.run_stop` emits `decision: block`. **There is no
termination condition on that loop.**

Measured in session `d1589e0b` on branch `0903-1`, 2026-09-04/05:

- Roughly **8 consecutive rounds** of "A FIX LANDED AND NO REGRESSION GATE
  PROTECTS IT".
- The chain was **self-generating**: writing gate A produced finding B (gate A's
  selftest tail tripped `check:ci-shape-duplication`; gate A's new file tripped
  `check:ci-gate-manifest` leaf-tracked). The commit fixing B matched
  `FIX_SUBJECT = ^(fix|revert)[(!:]`, so round B demanded a gate, whose fix
  produced C.
- Each round cost a **~15 minute CI run**, because the push superseded the run in
  flight. The PR was already green, Claude-reviewed and threads-resolved.

**No single demand was wrong.** Every one was a real, artifact-verified blind
spot. The defect is structural: the process has no bound, and its marginal cost
is a full CI cycle on work that was otherwise finished.

Two hard constraints, both from the operator's ruling:

1. **The bound is enforced in `.claude/hooks/stop/`.** A session choosing to stop
   complying is exactly the failure this prevents.
2. **It is not an escape hatch.** "A finding is fixed in the session that finds
   it"; a suppression needs a true `BLOCKER:` reason and a liveness oracle.

## 2. Design: three layers, only one of which is the cap

### Layer 1 - Precision (removes most of the loop, hides nothing)

Findings B and C were **defects a CI gate had already caught**. A defect found by
`check:ci-shape-duplication` is by construction covered by it: that gate failed
against the tree before the fix. The correct verdict was `covered`, and
`apply_regression_verdict` already accepts it. The judge was never told to reach
for it.

- `M.REGGATE_PROMPT` gains **(0) WAS THIS DEFECT FOUND BY A GATE?** If a CI gate
  failed and this fix makes it pass, that gate IS the coverage.
- `wl_reggate` computes from `git diff-tree` whether the fix-set is confined to
  gate artifacts, and adds one prompt line saying so. Same class as the existing
  docs-only skip, and artifact-derived for the same reason.

Layer 1 is **not** the cap and must not be sold as one.

### Layer 2 - The cap

A branch gets a **budget of new regression gates**, spent by *writing a gate*,
not by *being asked*. Exhausted, the next demand converts into a **gate debt**.

### Layer 3 - The debt

An append-only, branch-scoped record carrying the judge's exact `blind_spot`,
`surface`, `artifact`, `instruction`, a machine-generated `BLOCKER:` reason and a
**due condition**. When due, the hook materialises it as an ordinary `- [ ]` open
item, which blocks like any other. A CI gate reads the ledger independently.

Three states only: **blocked now**, **debted with a due date**, **discharged
against artifacts**. No code path deletes a debt.

## 3. The five questions

### Q1. What is counted, in what scope

**Counted:** a fix-set this branch resolved by writing a new gate (settle payload
`proven`), plus one for each fix-set the cap deferred.
**Not counted:** demands, blocks, stops, or settles of `covered` / `one-off` /
`not-applicable` / `deferred` - these cost no artifact and no CI round.

Counting *demands* would let a session outwait one legitimate demand by stopping
N times, which is the ignoring the operator ruled out. Counting *cheap settles*
would let a session farm the budget with five honest `one-off`s and buy a pass on
the sixth, real gate.

**Scope: the branch.** `append_events` already stamps `br`, and the branch maps
one-to-one onto one PR, one CI queue, one finish line - which is where the cost
lands. NOT per session: a compaction hands the conversation a new session id and
`reggate_path` is keyed on it, so a per-session budget evaporates exactly when a
long night makes compaction likely. Two sessions sharing a branch share the
budget, correctly, because they share the CI queue.

### Q2. What happens at the cap

The demand converts to a tracked debt with a due date and returns as a hard block
when due. On the capping stop:

1. **The judge is still asked and still answers.** `apply_regression_verdict`
   still verifies every claim against artifacts. The finding is fully computed
   before anything is deferred - a cap that skipped the question would produce a
   debt with no content, indistinguishable from the machinery breaking.
2. `wl_checks` appends a `debt` record instead of emitting the block.
3. The per-session marker records the fix-set as the new verdict `capped` with
   the debt id, so it is not re-asked every stop but the record says plainly it
   was deferred rather than answered.
4. An **unlatched** section is queued to every later stop naming the count,
   branch and due time.

When due, the hook appends `materialize` once and calls `S.add_item`, creating a
real `- [ ]` item tagged `reggate-debt:<sig8>` carrying the blind spot verbatim.
It then blocks like any other open item - no new blocking path, no suppression to
audit, no change to `classify_items`.

**The critical separation: the item is the reminder, the ledger is the truth.**
Ticking the item with prose does not write a `discharge`, so the CI gate still
fails. Only the hook writes `discharge`, only after artifact proof via the
existing `prove_new_gate` / `prove_named_artifact`. There is deliberately **no
CLI verb to discharge a debt.**

Rejected: **advisory** (this repo has measured that a passive finding is "read by
nobody until the operator relayed it BY HAND" - dropping the finding, slowly);
**a `[?]` with an executing DEFAULT** (CLAUDE.md reserves `[?]` for genuinely
operator decisions, the DEFAULT re-imposes the same demand on a timer, and worst,
`apply_regression_verdict` already settles on a `[?]` carrying `reggate:<sig>`,
so producing them at the cap hands the session a copyable self-service exit from
ANY demand); **auto-tick** (forbidden); **defer in the session marker only**
(session-keyed, resets on compaction).

### Q3. How the cap resets

The **counter** resets when the branch lands: `git merge-base --is-ancestor HEAD
origin/main`, or a ledger that does not exist yet. **Debts do not reset.** A
merge resets the counter and simultaneously makes every outstanding debt **due**.
That inversion is the point: merging is what makes you pay, and no ordering
exists in which a merge discharges a debt.

A time ceiling backs it, because a branch may never merge:
`WORKLIST_REGGATE_DEBT_GRACE_MIN`, default 720 (12h);
`due = min(merge_detected, at + grace)`. A failed probe means the grace clock
alone governs - failing *sooner*, never *never*.

Not resets: a new session id, a time window on the counter, a new epic (epics are
prose-scoped labels; a budget keyed on one is a budget you rename your way out
of).

### Q4. How it is kept honest

1. **No suppression path exists.** The materialised debt is an ordinary open item
   on the ordinary blocking path.
2. **The cap has a cap.** `REGGATE_MAX_DEBTS` default 5; past that, demands block
   normally again. "Permanent hatch" is structurally unreachable.
3. **The floor.** `cap = max(1, ...)`. The first gate-demand of a budget can
   never be capped under any configuration.
4. **It only touches demands that would cost a gate**, so it cannot dodge the
   REBUT or operator-deferral exits.
5. **A true `BLOCKER:` reason on every debt**, machine-generated, refused by the
   gate if absent or under the substantive-reason bar.
6. **A liveness oracle enforced in-gate.** `scripts/check-reggate-debt.ts` fails
   on: a debt past due and undischarged; a `sig` naming commits not on this
   branch (fabricated); more than the ceiling outstanding; a discharge with no
   record; and a **stale** debt whose artifact now exists, is wired and green but
   was never discharged - so a dead obligation cannot linger as a fake one.
7. **Visible on every stop, never latched.** A bounded deferral whose reminder
   can be rotated away is a deferral nobody sees.

Every failure direction is **toward asking**: an unreadable ledger yields an
empty budget, the cap does not apply, and the demand blocks.

### Q5. Why not 7

**The evidence does not support 7.** Tonight ran ~8 rounds at ~15 min of CI each.
A cap of 7 fires on round 8, after ~105 minutes of CI is already burnt and the
night is effectively over. A limit that fires once the cost is paid is a record,
not a limit.

For **3**: diminishing return is visible by round 3 (round 1 gates the fix, round
2 gates the gate, round 3 gates the gate that gated the gate); the repo's own
precedent is `SWEEP_MAX_FIRES = 2` for a strictly cheaper demand; and 3 puts the
trigger at ~45 minutes of CI rather than ~105.

**But the sharper answer is cost-based, not count-based.** The dominant term is
that each push superseded a run on a PR already green, reviewed and resolved:

> **The budget is 3 new gates per branch, or 1 once the branch's PR is green +
> Claude-reviewed + threads-resolved.**

`wl_ci` already computes that state. It only ever LOWERS the cap to 1, never 0,
so the floor holds. An unavailable `gh` query must leave the full budget - fail
toward asking.

Knobs: `WORKLIST_REGGATE_CAP=3`, `WORKLIST_REGGATE_CAP_AT_FINISH=1`,
`WORKLIST_REGGATE_MAX_DEBTS=5`, `WORKLIST_REGGATE_DEBT_GRACE_MIN=720`. There is
deliberately no "off" value: a disabled cap must look like a number somebody
chose.

## 4. Where the ledger lives

An append-only JSONL log written through `wl_store._append_lines` under a
blocking flock, folded on read, never edited.

It must **NOT** be a new `ev:` kind in the item store. `wl_epic.py`'s header
records why, and it learned it the hard way: `compact()` rewrites the log down to
the minimal item-reproducing set, so **a novel event kind there is SILENTLY
DESTROYED**. `.requests`, `.intents` and `.epics` are the precedents.

**Location: `agent/reggate/<branch-slug>.jsonl`.** Under the tracked `agent/`
tree so it survives a machine, rides the PR where a reviewer sees the deferrals
in the diff, and is readable by a CI gate; `agent/` is a zero-job module in the
scope map, so this adds no CI jobs. **One file per branch**, following
wl_store's per-writer rule verbatim - both sides of a merge append at EOF, so a
shared file conflicts on every concurrent append.

`wl_store.AGENT_RESERVED_DIRS` **must** gain `"reggate"`, or `agent_session_dirs`
reports a peer session that does not exist. That is the one silent failure this
change can cause.

## 5. Files and functions

**`wl_reggate.py`**: `REGGATE_VERDICTS` gains `"capped"`; module constants for
the four knobs with `CAP` clamped `max(1, ...)`; `debt_dir` / `debt_path`;
`append_ledger`; `read_ledger` returning `(records, forgot)` with the same FAIL
SAFE contract as `load_reggate`; `budget_state`; `charge`; `defer_at_cap`;
`branch_merged`; `due_debts` / `materialize` / `discharge_scan` reusing
`prove_new_gate` and `prove_named_artifact` unchanged; `gate_only_fixset`
feeding the prompt hint only. **`apply_regression_verdict` is unchanged** - the
cap lives at the caller, which keeps it a pure verdict-to-action mapping and
keeps cases 82-95 valid.

**`wl_checks.run_stop`**: read the ledger after `load_reggate`, compute the
budget, run `discharge_scan` then `materialize`; extend the prompt; `charge` on a
`proven` settle; **the cap at the `kind == "block"` site**; and an always-on debt
line while any debt is outstanding.

**`wl_judge.py`: no change**, deliberately. The judge is asked the identical
question under the identical schema whether or not the cap fires. A cap that
changed the question would change the finding rather than its schedule.

**`worklist_messages.py`**: new `R_REGGATE_CAPPED`, `R_REGGATE_DEBT_DUE`,
`V_GATE_DEBT`, `REGGATE_BUDGET`, `REGGATE_GATE_MAINTENANCE`; `REGGATE_PROMPT`
gains question (0); `R_REGGATE_BLOCK` names the remaining budget so a session
sees the bound before hitting it.

**`wl_store.py`**: `AGENT_RESERVED_DIRS` gains `"reggate"`. Nothing else.

**CI gate**, three-point wired as `prove_new_gate` itself requires:
`scripts/check-reggate-debt.ts` (control-first `--selftest`), the
`check:ci-reggate-debt` key, a manifest entry, a workflow step.

**Docs**: a `suppressions.md` row naming the mechanism, its file, its reader and
its in-gate oracle; and one sentence in CLAUDE.md §2 naming the single bounded
exception. An unwritten exception IS the escape hatch.

## 6. Control-first test plan

Home: `worklist-cases/06-regression-gate.sh`, extended in place. New helpers in
`_harness.sh` (the file's own rule forbids copying a helper into a case file):
`debt_ledger`, `age_debt`, `merge_branch`, `shim_judge_capture` - the last
required because the Layer 1 prompt change is otherwise untested.

C1 the cap does not fire early. C2 it fires at the cap. **C3 THE FINDING SURVIVES**:
the ledger holds the blind spot byte-identically. **C4 THE FINDING RETURNS**:
aged past due, the block carries the same string verbatim. **C5 a tick cannot
discharge**. C6 only artifacts discharge. C7 cheap settles do not charge the
budget. C8 not per session. C9 branch-scoped. C10 a merge resets the counter and
makes debts due. C11 the floor. C12 the cap has a cap. C13 the finish line lowers
to 1, never 0. C14 a stale gh answer cannot lower it. C15 corruption fails toward
asking. C16 never latched. C17 the operator-deferral exit is untouched. C18 the
cap cannot be self-served by a hand-written token. C19 Layer 1 reaches the
prompt. C20 the CI gate is itself control-first.

C3, C4, C5, C18 prove **the cap cannot hide a finding**. C7, C11, C12, C17 prove
**it cannot be used as an exit**.

## 7. Risks

**R1 the cap becomes a permanent hatch** - the main risk, closed structurally by
the floor, the cap-on-the-cap, the merge-makes-it-due inversion, artifact-only
discharge and an independent CI gate. **R2 an uncommitted ledger is invisible to
CI** - same exposure `agent/worklist/*.jsonl` already carries; the hook enforces
locally regardless. **R3 rebase/rename could reset the counter** - neither
touches debts, and the gate reports debts across all ledger files. **R4 two
sessions share a budget** - intended; each `spend` carries `by`. **R5
bootstrapping recursion**: writing the gate will itself trip shape-duplication
and gate-manifest, the exact loop being capped - land the hook change and the
gate in ONE wave, converge locally, accept one CI round. **R6 `capped` is a
one-way marker format change** - old code discards the marker and re-asks once,
the fail-safe direction. **R7 the finish-line signal can be stale** - it only
lowers to 1. **R8 a 12h grace can span a night** - due-at-merge fires first in
practice. **R9 `agent/reggate/` must be in AGENT_RESERVED_DIRS** or a phantom
peer session is reported.

## 8. Sequencing

1. Layer 1 alone (prompt question (0) + the gate-artifact hint + C19). Cheap,
   hides nothing, measurable on its own - it may remove most of the loop before
   any cap exists.
2. Ledger primitives + `AGENT_RESERVED_DIRS` + C15, C18.
3. The cap at the block site + C1, C2, C3, C7, C8, C9, C11-C14, C16, C17.
4. Debt materialisation and artifact-only discharge + C4, C5, C6, C10.
5. `check-reggate-debt.ts` three-point wired + C20, and the suppressions row.
6. The CLAUDE.md sentence.

Steps 1-4 are all inside `.claude/hooks/stop/` and satisfy the ruling on their
own. Step 5 makes the deferral honest over time rather than only over one night.

## 9. Verification of the plan's load-bearing claims

Checked against source by d1589e0b before acceptance, because a plan's claim
about code it has not read is a hypothesis:

- `REGGATE_VERDICTS = ("not-applicable", "covered", "one-off", "proven",
  "deferred")` at `wl_reggate.py:38` - confirmed, and `capped` is genuinely new.
- `wl_epic.py:3-5` carries the "SILENTLY DESTROYED" rationale verbatim -
  confirmed, so the sidecar choice rests on a recorded incident, not a guess.
- `AGENT_RESERVED_DIRS = frozenset({"archive", "programs", "worklist"})` at
  `wl_store.py:283`, consumed at `:383` - confirmed, and `reggate` is absent, so
  R9 is real.
- `SWEEP_MAX_FIRES = 2` at `wl_classsweep.py:470` - confirmed, so the "3 is
  already generous against precedent" argument holds.

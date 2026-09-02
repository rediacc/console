Status: draft
Owner: 74de73ca

# Make a handoff carry the ORDER of its work, not just its inventory

Designed 2026-09-02 by a Plan agent against measurements taken on this tree, and written up
here because that agent had no write tool. It adopts the ordering vocabulary already settled
in `agent/PLAN-stop-plan-box-enforcement.md` rather than re-deciding it.

## The ask

The operator, verbatim: *"Then there should be also priority order in the plan. Let's also
update handoff to have better sequence!"*

## What is actually there

- **The corpus.** 4 dirs under `agent/programs/`; **3** carry a `CHECKLIST.md`. **25 waves,
  25 ticked, 26/26 deliverables ticked**, all three at `Status: done`. **Zero `[?]` and zero
  `[>]` marks exist in any checklist, in any state, ever.**
- **`handoff.md`, 152 lines: 5 of them (3.3%) constrain the order of WORK.** The order in
  which the command itself writes is stated three separate times. **The command is meticulous
  about its own write order and nearly silent about the work's.**
- **The one sentence that gives checklist line order meaning gives it away.** L48-49 says wave
  ids go "in the README's wave order", making `CHECKLIST.md` a MIRROR of a prose section
  rather than the authority — so a reader who finds a conflict has no rule for which wins.
- **Measured on `clarity-round6`: its ordering is NOT recoverable by a reader.** Three
  orderings exist, two agree, and neither of those two is the real one. The actual dependency
  graph lives only in `06-execution-guide.md:55-66` as a free-text column ("blocks w8",
  "needs w1") — **document 6 of 6, and precisely the alternative the enforcement plan rejected
  as "a free-text graph nobody validates".**
- **Its only front-door restatement is wrong.** `PROMPT.md:70` states the program's one
  load-bearing constraint in LABEL space, and every wave's label is offset by one from its id
  (`w1` is "Wave 0"). Resolved against the checklist it names **three wrong waves and a wrong
  target**. **21 of 25 waves tree-wide carry a label that differs from their id.**
- **A `[?]` in a checklist today BRICKS the handoff.** `CL_ITEM` accepts only `[ ]` and `[x]`,
  so `- [?] w4 …` is caught as a shape error and the adjudicator returns immediately — a
  fail-closed block on every stop. Meanwhile `wl_planfid.py:1068` already parses `[ x?>]`, so
  the vocabulary is live in two of three modules and missing only here.
- **"Blocked" already exists, in the wrong file.** A door-parked worklist item drives the
  parked-rows report, and its own docstring records the failure: one checklist wave stayed
  visible for a day only because a session hand-copied it into STATE.md, "and that is
  discipline, not a control".

## The design: POSITION IS ORDER, ID IS IDENTITY

1. **Order lives in the line order of `## Waves`, and nowhere else.** No field to type, so
   nothing a human editing markdown can get wrong — the same choice, for the same reason, as
   the enforcement plan's "document order and nothing else". Three consequences: the checklist
   becomes AUTHORITATIVE rather than a mirror; dependency prose becomes commentary that can
   never carry the order; and the front-door block names the next wave, so a fresh session
   reads it automatically with no paste and no read order.
2. **Blocked is `[?]`; in flight is DERIVED.** Widen `CL_ITEM` to `[ x?>]`. `[?]` earns
   storage because a door-parked wave outlives every session. `[>]` is **parsed but never
   written** — "in flight" is already computed from the live worklist item carrying
   `cl:<slug>/wN`, and storing it twice would be the second store to reconcile that the code's
   own comment refuses. **If every remaining wave is `[?]`, the program is BLOCKED** and
   nothing is offered as next.
3. **UPDATE mode: id and position are different axes.** Every existing rule survives
   literally, because "renumber" was never the same word as "reorder". New waves are INSERTED
   among the not-done lines, not appended; a `[x]` line never moves; ids stay monotonic in
   ALLOCATION and stop being monotonic in POSITION. A checklist then reads `w1 w2 w12 w3` —
   **that non-monotonic read is the feature**, the visible proof that the id is a name and the
   line is a rank.
4. **PROMPT.md opens with the next action.** Today it seeds every wave at once. It gains a
   `## Start here` block naming the frontier wave and the single `--add` that claims it, and
   loses the "one per wave through w10" fan-out. Wave LABELS stop appearing entirely: one
   numbering space, the one the `cl:` token uses.
5. **The checklist IS the plan the enforcement mechanism adopts.** `## Waves` is a plan in
   that design's exact sense — an ordered list of four-mark boxes in committed markdown — and
   "first workable box" is the same computation. Two mechanisms would mean a session adopting
   a plan while a checklist demands four unrelated waves, reconciled by hand every stop.

## Rejected alternatives

An explicit `order:`/`prio:` field (a human inserting between two waves gets it wrong the
first time, and 25 lines would need editing); a dependency column (**not hypothetical — it
exists, and it is the measured failure**); renumbering ids to follow order (breaks every
`cl:<slug>/wN` token already written); a separate `## Order` section or `ORDER.md` (a second
copy that drifts with nothing catching it); leaving order in the execution guide (the status
quo, measured unrecoverable); a fifth mark for "blocked on an earlier wave" (a wave blocked on
an earlier one is expressed by being BELOW it); and keeping two marks with blocked expressed
only through worklist doors (that is today, and its own docstring is the evidence it failed).

## Controls

18 named controls across a new `test-checklist-marks` and `test-checklist-order`, plus
additions to the existing checklist cases. The load-bearing ones: the widened `CL_ITEM` must
be **byte-identical** on today's three-checklist corpus; `[?]` and `[>]` must parse as states
while `[!]` stays a shape error (the widening is exactly three characters wide); `next_wave()`
on `w1[x] w7[ ] w2[ ]` must return **w7**, proving position beats id; an all-`[?]` remainder
must return BLOCKED and emit no demand; and a planted `[?]` on a live checklist must visibly
change the front-door text, then change back.

## Migration

**The wave migration is empty, and that is a measurement rather than luck**: all 25 waves are
`[x]`, order ranks only not-done waves, so there are zero lines to reorder. The 21 label/id
collisions are fixed by SUBTRACTION — stop restating human labels — not by editing 21 lines.
Two checklists carry a `file:` token that cannot resolve on this host; that is decision 3.
Ship the frontier-only demand behind a `Status: executing` filter, of which there are **zero
today**, so the first real exercise is a handoff written after the change.

## The three decisions that are the operator's

1. **May a handoff checklist be ADOPTED by the plan mechanism?** It expands the scope of a
   mechanism that is designed and not yet built; the two should ship together or the
   hand-reconciliation this removes will exist for a while first.
2. **Depth over breadth: one demanded wave instead of N?** Today the gate proves every wave is
   claimed; after this it proves the next one is. A genuine reduction in coverage, and the
   operator is the one whose worklist shrinks from 11 items to 1.
3. **Repair or supersede the two drifting done handoffs?** Both are finished work, which is
   why neither is the session's call.

**Ordering itself is deliberately not on that list**: line order is free, already true of all
three checklists, and every alternative costs file edits or an unvalidated graph.

## Status

- [ ] Widen `CL_ITEM` to `[ x?>]`; prove byte-identical on the 3-file corpus
- [ ] Add `next_wave()` and the BLOCKED verdict; wire `[?]`/`[>]` exclusion
- [ ] Change the wave demand to the frontier only; reword its message
- [ ] Name the next wave (or BLOCKED) in the front-door checklist block
- [ ] Write the 18 controls; prove the byte-identical pair and the planted `[?]`
- [ ] Edit `handoff.md`: authoritative checklist order, four marks, insert-not-append, and
      `## Start here` as PROMPT.md's first section
- [ ] Unify with `--adopt` once `agent/PLAN-stop-plan-box-enforcement.md` lands (decision 1)

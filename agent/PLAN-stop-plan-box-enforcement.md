Status: superseded
Superseded-by: agent/PLAN-plan-file-lifecycle.md

SUPERSEDED 2026-09-02. Its analysis was re-verified and holds -- OUTQ_PER_STOP = 1
(wl_checks.py:1562), plan-tasks queued at priority 2 (:3760), outq_drain on the allow
path only (:5823) -- and its diagnosis of `_pf_rows[0]` is correct. What it could not
know is the SECOND cause, which is the larger one: NOT_STARTED_STATES exempts 6 of the 8
box-carrying files, 72 of the 88 boxes, before plan_rows ever opens them, because
`Status: draft` has since become this repo's default header on plans under active
execution. Its "adopt one, in order" rung is also deferred rather than adopted: with the
CI half in place the silenced box is caught at merge anyway, so asking the operator to
let an unclaimed document block an unrelated session can wait until the cheaper changes
have been seen to fire. Its parser refactor IS pulled forward. See the successor.

Owner: 74de73ca

# Make an open `- [ ]` in a committed plan drive the session

Designed 2026-09-02 by a Plan agent for this session, from measurements it took against
this tree. Written up here because that agent had no write tool; every number below is
its measurement, and the ones this session re-checked are marked.

## The complaint

The operator, verbatim: *"there are too much empty [ ] boxes at
agent/PLAN-secret-namespace-migration.md and the our stop hook doesn't come with them!!!
We must fix stop hook. ... fix encourage/enforcement about the [] empty boxes so judge can
HELP us correctly/according-to-the-plan!"*

`.claude/hooks/stop/wl_planfile.py` was written the same morning for the narrower version
of this complaint, and it WORKS — it finds all 16 untracked boxes today. The operator has
still never seen it. **That is a delivery failure, not a detection failure**, and the
distinction is the whole design.

## What is actually there

- **62** plan files; **11** in scope under the existing status blocklist; only **2** carry
  any raw `- [ ]`; **17** open boxes in the entire tree; exactly **1** plan is both in
  scope and has boxes.
- `agent/PLAN-secret-namespace-migration.md`: 16 open / 16 ticked, and it was 18/4 that
  morning — **12 boxes got done while the check stayed silent**.
- **16 of 16 open boxes have no worklist item in any state.** The plan's own preamble
  states the contract ("one `worklist.py --add` item per line"), so that contract has a
  **100% miss rate** — and the work still moved.
- **Why it never landed:** `plan-tasks` sits at drain position **20 of 22** in this
  session's queue with `OUTQ_PER_STOP = 1`, behind 11 priority-1 producers, and
  `outq_drain` runs on the ALLOW path only — so a session that keeps blocking never drains
  at all. It was shown **once, on one of six sessions, all day**. Queue starvation, not the
  6-hour refresh suppression.
- **27 of 62** plans have no parseable `Owner:`, including the one that matters, so
  "unowned" means *everyone's*.
- **9 of 9** distinct `planFilePath` values in the transcripts point at
  `~/.claude/plans/`, never at `agent/` — plan-mode exit cannot scope a committed plan.
- `PRIORITY_LADDER`'s top tier `T_MISSION` is already defined as *"markdown checkboxes that
  already exist"* and already names three families of them. **`agent/PLAN-*.md` boxes were
  simply never added to that frozenset.**

## Was the advisory-only choice right?

Half. It was right that 18 session-owned open items would wedge every turn for weeks. It
was wrong that the alternative was zero: it framed the choice as **18 or 0 and never
considered 1**. And it mispriced the advisory — the queue did not give noise control for
free, it gave silence for free.

## The design: ADOPT ONE, IN ORDER

A session **adopts** one plan with one command; the plan's **first workable open box in
document order** becomes **exactly one** worklist item; the judge is shown that box and
asked whether the session worked it, or why not.

- **Scope is adoption**, not inference: `--adopt <me> <plan>` / `--disown <me> <plan>`,
  stored in the per-session state doc. It is the only candidate that is a statement by the
  session about itself, which is the consent that makes a block legitimate. `Status:`
  describes a document, not an owner; `Owner:` is absent on 27 plans; plan-mode exit is
  measured impossible; newest-mtime changes under you between two stops.
- **Three rungs.** Silent (61 of 62 plans today) → advisory, unchanged and still on the
  starving queue on purpose, because it is now the low-stakes leg → a `T_MISSION` block
  whose only demand is CHOOSE: adopt or disown, both one command, neither any work. **16
  boxes cost one command, not 16 blocks.** It arms only after the advisory was actually
  displayed, so a session is never blocked by a notice it never saw.
- **Order is document order**, and nothing else: the parser already returns it, and the
  target plan is already written in it. An explicit per-line marker breaks the first time a
  human inserts a box; a dependency graph nobody validates goes silently vacuous on one
  typo.
- **Blocked is not not-started.** Teach the parser the four marks it already has a
  vocabulary for: `[ ]` workable, `[x]` done, `[?]` operator-blocked, `[>]` in flight.
  `[?]` and `[>]` are never offered as next. **If every remaining box is `[?]`, the plan is
  BLOCKED and the rung does not fire** — otherwise the check's first act would be to order
  work nobody can do, which is how a gate teaches its reader to skip it.
- **The judge leg**, `wl_plannext.py`, follows the existing optional-object contract
  exactly: prompt marker → schema key required iff the marker is present → read verdict →
  order → cap. It sees the adopted box and asks `worked_on` / `divergence_ok`. A missing or
  malformed object degrades to a reported non-answer and can only ever LOSE a demand,
  never grant an exit.
- **Safety.** Every string handed to a session goes through `names_operator_reserved`
  (added earlier today). Measured: **1 of the 16 boxes trips it** — a box describing what a
  script *pushes*. So a tripped QUOTE degrades to a file+line pointer rather than dropping
  the demand; only a model-authored instruction is dropped outright. Dropping the demand
  would have made that box permanently un-orderable and silent.
- **Reverse the sync contract.** The boxes are the source of truth; the worklist derives
  one item at a time. The 1:1 contract has a 100% miss rate, and the durable document
  should not be derived from the ephemeral one.

## Migration

Ships behind a whitelist, not the blocklist: the blocking rung fires only on
`Status: executing`, which selects exactly one plan today and it is the right one.
**An advisory must fail noisy; a block must fail quiet** — same corpus, two filters,
each pointing the safe way for its own consequence. Nothing in `agent/` needs editing:
the `[?]`/`[>]` marks are opt-in and only 2 such lines exist tree-wide.

## Controls

38 named controls across a new `test-plannext.py` plus additions to `test-judge-schema.py`
and `test-planfile.py`. The load-bearing pairs: the refactored `plan_tasks` must be
**byte-identical** on today's `[ ]`/`[x]` corpus; blindness must be reported even for a
`Status: done` plan (a hole in the current rule — the one blind plan in the tree is hidden
by the status filter); rung 2 must NOT fire when the advisory was never shown; and the
measured false positive must degrade to a pointer rather than vanish.

## The two decisions that are the operator's

1. **May an unadopted, unowned committed plan block any session in the checkout?** Bounded
   here to `Status: executing` — one plan today — and to one command per session per plan.
   It is still the operator choosing to let an unclaimed document interrupt an unrelated
   session.
2. **Do they accept ONE worklist item for a 16-box migration instead of sixteen?** The
   judge prompt already tells sessions *"the operator sees the same list in their app"*, so
   this changes what that view contains. Sixteen items is the deadlock; a rendered
   read-only view of the boxes is a different and larger piece of work.

Ordering is deliberately NOT one of these: document order is free, already true of the
target plan, and every alternative costs 62 file edits or introduces an unvalidated graph.

## Status

- [ ] Implement the parser change (`plan_task_marks`, `plan_tasks` as a filter over it)
- [ ] Implement `--adopt` / `--disown` and the state-doc binding
- [ ] Add the `T_MISSION` rung and its display latch
- [ ] Implement `wl_plannext.py` and register its schema key
- [ ] Write the 38 controls; prove the byte-identical pair and the blindness hole
- [ ] Ship behind the `Status: executing` whitelist, then widen only after the operator has
      seen it fire on the real plan

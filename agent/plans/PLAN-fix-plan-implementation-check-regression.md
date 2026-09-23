# PLAN: retroactive P-A2 evidence backfill for check:ci-plan-implementation

Status: executing
Owner: d778be9d
Updated: 2026-09-23

## Finding

`check:ci-plan-implementation` (`.ci/scripts/quality/check_plan_implementation.py`) is red with P-A2 violations on 316 boxes across 31 plans.
Root cause: dispatched implementation sub-agents flipped plan checkboxes `[ ]` -> `[x]` directly with the Edit tool, doing real, verified work, but skipped the sanctioned `worklist.py --plan-investigate` / `--plan-tick` pipeline that stamps a `(ticked)` evidence line beneath the box and an investigation row in `agent/ledgers/plan-investigation.jsonl`.
The work itself is not in question; this is a process-compliance gap with no audit trail.

Verified live on branch `0923-1`: running `python3 .ci/scripts/quality/check_plan_implementation.py` reproduces exactly 316 boxes across 31 plans, all grouped under 5 distinct closing commits:

| closing commit | date | subject |
|---|---|---|
| `15088b6afa27` | 2026-09-23 07:08 | feat(ci): register the agent-session-archival, plan-implementation and bws-rotation-notice gates |
| `f5007b6495ff` | 2026-09-23 09:50 | fix(ci): 6 independent ci:quick reds surfaced this session |
| `28d8f96e4f5d` | 2026-09-23 10:16 | docs(agent): archive 3 done plans, verified box-complete before moving |
| `8a25a0c4be7a` | 2026-09-23 10:44 | docs(agent): tick PLAN-fix-plan-citation-drift.md's migration-fixability box |
| `def57d384b03` | 2026-09-23 12:36 | docs(agent): fourteen citation-remainder boxes close, one plan at a time |

Of the 316: 221 boxes have no `(ticked)` line at all; the other 95 already carry a well-formed `(ticked) <ts> by <me>: <text>` line citing real commits/`file:line`s but still have no matching row in `plan-investigation.jsonl`. All 316 lack the ledger row -- that is the common thread the gate actually enforces (`check_plan_implementation.py:260`).

## Why the live verbs cannot be re-run on these boxes

`wl_planrec.plan_investigate()` and `wl_planrec.plan_tick()` both call `open_boxes(text)` (`wl_planrec.py:1775-1790`), which only returns boxes whose mark is not `x` (`:1784`); `select_box()` (`:1793-1819`) raises `RecordError` on a selector that matches no open box.
Every one of the 316 boxes is already `[x]` at HEAD, so `--plan-investigate ... present ...` and `--plan-tick ...` both refuse outright today.

Checking out an ancestor commit to find the box still open does not generalize either: for `agent/plans/_done/PLAN-wl-wait-duplicate-listener.md`, the file was born at its current path already `[x]` in the same commit (`3d165a684`) that renamed it in.
All 31 plans are absent at the branch's `origin/main` merge-base at their current paths (a corpus-wide `agent/PLAN-*.md -> agent/plans/**` reorganization happened on this branch), and several are retrospective write-ups authored after the fix already existed, boxes pre-checked at birth. So the backfill needs a purpose-built path, not a worktree replay of the live CLI.

## Why the P-A4 ordering constraint is nonetheless satisfiable

P-A4 (`check_plan_implementation.py:712`) only demands that the investigation row's recorded `head` be an ancestor of `done_commit` (`merge-base --is-ancestor`). Nothing requires `head` to be computed by running the CLI live. Since `done_commit` for all 316 boxes is one of 5 ordinary, single-parent commits, `done_commit^` (the immediate parent) is:

- a real, already-existing commit,
- trivially and unconditionally an ancestor of `done_commit`,
- shared by every box that commit closed.

This needs computing exactly 5 times, not 316 or 31.

## Phase 0 -- narrow code addition (owner: writer sub-agent A)

Files: `.claude/hooks/stop/wl_planrec.py`, `.claude/hooks/stop/worklist.py`.

Add `plan_backfill_investigation(root, rel, sig, me)` plus a `--plan-backfill` CLI mode:

- [ ] Operates only on a box that is already `[x]` (refuses if the selector names an open box, so it can never shortcut a live investigation).
- [ ] Computes `head` from `done_commit^`, never `git rev-parse HEAD` of the live tree -- document this divergence from `plan_investigate` prominently.
- [ ] Hard-codes `verdict="present"` (the only honest verdict for "already closed, only the trail is stale").
- [ ] Builds the row in the same shape `plan_investigate` returns, then calls the existing `append_investigation(root, row)` -- no new ledger-writing code.
- [ ] Inserts the `TICK_EVIDENCE` line (`wl_planrec.py:1766`) beneath the box only if absent (idempotent for the 95 that already have one), using the same 4-space, no-bullet grammar so `BULLET_RE` still can't see it. Never touches the box mark.
- [ ] Asserts `PF.plan_boxes()` open/done sets are byte-identical before/after, the same invariant `plan_tick` checks at `wl_planrec.py:2295-2309`.
- [ ] Refuses loudly (never silently skips) any box where `done_commit_of` returns `""` (abandoned per `wl_planrec.py:90-93` vocabulary) -- must not manufacture a trail for that case.
- [ ] Unit tests: a planted defect (a box missing its evidence line) is caught by the enumeration; a clean box is left alone; the guard refuses an already-open box; the guard refuses an abandoned box.

## Phase 1 -- batch run (owner: writer sub-agent A, after Phase 0 lands)

Thin orchestration, e.g. `.ci/scripts/quality/backfill_plan_implementation.py` (one-off, may be deleted after use or kept as a documented recovery tool):

- [ ] Enumerate the 316 violations using the gate's own functions (`moved_to_done`, `bound_by_the_rule`, `tick_findings` / `_evidence_line`) -- assert the count is 316 across 31 plans; if the corpus moved since this design was written, stop and re-derive rather than working off a stale list.
- [ ] Group by `done_commit` (5 groups), compute `head_i = done_commit_i^` once per group.
- [ ] For every `(rel, sig)`, derive pointers: reuse real hex/`file:line` tokens from an existing `(ticked)` line where present and still resolving; otherwise fall back to `[("commit", commit), ("plan", rel)]`.
- [ ] Compose `note` (>=40 chars) citing the real `commit[:9]`, its subject and date, and this backfill plan's name.
- [ ] Call `plan_backfill_investigation` for all 316, batching each plan file's insertions into one rewrite (top-to-bottom by line index so earlier insertions don't shift later ones), and append all 316 rows to `agent/ledgers/plan-investigation.jsonl` in one pass.
- [ ] Never touch `.ci/config/plan-boxes.json`.

## Verification (owner: session, both phases)

- [ ] `git diff --stat` before committing: only `plan-investigation.jsonl` (316 appended lines) and the 31 plan files, each diff add-only `(ticked)` lines -- `git diff -- agent/plans | grep '^-'` empty beyond hunk headers.
- [ ] `python3 .ci/scripts/quality/check_plan_boxes.py` stays green (ledger still agrees with the tree; insertions did not perturb signatures).
- [ ] `python3 .ci/scripts/quality/check_plan_implementation.py` exits 0 with zero P-A2/P-A3/P-A4 findings; re-run the enumeration script and assert the violation list is empty.
- [ ] `check:ci-plan-record` unaffected -- confirm none of the 31 plans use the compacted-record grammar (`Status: compacted/parked`).
- [ ] Full `npm run ci` quality-branch lane run once, to catch any other gate scanning `(ticked)` line counts or investigation-ledger size.

## Critical files

- `.ci/scripts/quality/check_plan_implementation.py`
- `.claude/hooks/stop/wl_planrec.py`
- `.claude/hooks/stop/worklist.py`
- `.ci/scripts/quality/check_plan_boxes.py`
- `agent/ledgers/plan-investigation.jsonl`

Design produced by a dispatched Plan agent (2026-09-23); load-bearing claims (violation count, closing-commit grouping, the `open_boxes`-refuses-`[x]` mechanism) were verified directly before writing this file.

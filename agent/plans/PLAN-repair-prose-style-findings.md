# PLAN: repair the 171 committed prose-style findings that hold check:ci-prose-style red

Status: draft
Owner: d778be9d
Updated: 2026-09-23

## The finding

`npm run check:ci-prose-style` exits 1 with two separate complaints, measured 2026-09-23 on branch `0923-1`:

- **171 NEW violations.** Committed prose in roughly thirty plan files under `agent/plans/` that `.ci/config/prose-style-baseline.json` has no entry for at all, so every finding in them reads as new.
  The heaviest are `agent/plans/PLAN-secret-namespace-migration.md` (8 shown), `agent/plans/PLAN-plan-implementation-enforcement.md` (7) and `agent/plans/PLAN-ci-watch-enforcement.md` (6).
  The gate prints at most 40, hard-coded at `.ci/rediacc_ci/quality/prose_style.py:1422`, so the full list has to be derived rather than read off one run.
- **144 baselined findings that no longer fire.** The baseline is shrink-only and an entry left in it after the fix hides the next regression.

The rule mix is the ordinary one: `R18` (a line past 384 with a sentence break available before it), `R1` and `R2` (the second and first person), `R11` and `R7`.

## Why this is not a baseline write

`check_prose_style.py check --write-baseline` would absorb all 171, and the gate's own message refuses that in as many words: "Do not add them to the baseline". The 144 stale entries are the other half of the same instrument and DO want draining, but draining them in the same pass as an absorption would make one command do two opposite things.

## Not this session's to start, and why that is a packaging question

Every one of these files is committed and unmodified in the working tree, so the debt predates this session and none of it was introduced here.
Two of the named files are owned by other live sessions in this shared checkout, with `agent/plans/PLAN-plan-implementation-enforcement.md` staged but uncommitted by a peer, and a prose sweep across files another writer is editing is the exact collision this repo's worktree rules exist to prevent.

## Implementation

1. Derive the full 171 rather than the 40 the gate prints: call `prose_style`'s checker directly over `agent/plans/**` and group by file and rule.
2. Split the work by rule class, because the instruments differ. `R18` and `R19` are WIDTH findings and `check_prose_style.py reflow --write <path>` is the sanctioned instrument; it preserves the word sequence, which must be asserted per file rather than assumed.
3. `R1`, `R2`, `R7` and `R11` are wording findings and each needs a judgement rewrite that keeps the sentence's meaning. A plan is a record, so a rewrite that changes what the record says is worse than the finding it clears.
4. Drain the 144 stale baseline entries in a commit of their own, after the repairs, so the shrink is visible as a shrink.
5. Re-run the gate and confirm it exits 0.

## Boxes

- [ ] Derive and group all 171 findings by file and rule, working around the 40-line print cap at `.ci/rediacc_ci/quality/prose_style.py:1422`.
- [ ] Confirm which of the affected files are owned by a live peer session right now, and exclude those from this pass rather than racing them.
- [ ] Repair the width class (`R18`, `R19`) with `check_prose_style.py reflow --write`, asserting per file that the word sequence is unchanged across the rewrite.
- [ ] Repair the wording class (`R1`, `R2`, `R7`, `R11`) by hand, keeping each sentence's meaning intact.
- [ ] Drain the 144 no-longer-firing baseline entries in their own commit, and confirm the baseline only shrank.
- [ ] `npm run check:ci-prose-style` exits 0.

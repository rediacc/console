# PLAN: fix plan-citation and plan-record drift (958 + 161 findings)

Status: executing
Owner: d778be9d
Updated: 2026-09-23

## The finding

check:ci-plan-citations (958) and check:ci-plan-record (161) are both red, spanning dozens of plans this session never authored.

## Root cause (Plan agent a2fd17b15c79c8ceb)

check:ci-plan-citations only judges lines the working tree adds relative to origin/main (check_plan_citations.py:241-266, diffed via git diff against base). To avoid double-counting a plan move as new content, it calls carried_lines(), which trusts a Status: moved / Moved-To: stub left at the old path (plan_lifecycle.py:282-298).

git status --porcelain agent/ on this tree shows 103 plain D (delete) and only 28 R (paired rename) among 165 changed paths in the flat-to-agent/plans/ migration.
Most of that migration was done as delete+add, not the stub convention, so moved_from() returns empty for those files, carried_lines is empty, and every pre-existing citation in every migrated plan scores as "added" today.
This is a plausible major contributor to the backlog's size, not confirmed as the sole cause; the categorized counts below stand regardless of whether it is fixed.

## Categorized findings (Plan agent a2fd17b15c79c8ceb, 100% sampled)

| Gate | Category | Count | Mechanical? |
|---|---|---|---|
| citations | bare basename, exactly 1 match in tree, add dir prefix | 678 | Yes |
| citations | bare basename, 0 matches anywhere (file gone) | 99 | Judgment |
| citations | bare basename, 2+ matches (ambiguous) | 67 | Judgment |
| citations | fileline exists, line stale (file shrank/grew) | 42 | Mostly mechanical (anchor search) |
| citations | object hash resolves to neither blob nor commit | 30 | Judgment |
| citations | check:x gate renamed/removed | 20 | Judgment |
| citations | needs submodule-qualified prefix | 14 | Yes |
| citations | cited plan file renamed/deleted | 8 | Judgment |
| record | done=commit, ledger at that commit lacks the signature | 126 | Mechanical if git log finds an attesting commit, else judgment |
| record | done=abandoned but current ledger attests a signature now | 30 | Mechanical (worklist.py --plan-compact) |
| record | Record-Sig mismatch (hand-edited prose) | 3 | Judgment |
| record | agent/INDEX.md stale vs census | 1 | Mechanical (--update) |
| record | unfilled FILL placeholder | 1 | Judgment |

Estimate: ~730-750 of 1119 (~65-67%) mechanical, ~370-390 need judgment.

## Implementation

1. Script A (citations, mechanical): for each bare-basename/fileline finding, find the basename in the tree; if exactly one match, repoint to that path, printing "unique basename match" as the proof.

   For stale-line findings, extract a quoted/backticked anchor token near the citation, grep the cited file for it; if exactly one line matches, repoint the line number and print the matched anchor text plus the old/new line delta.
2. Script B (record, mechanical): for ABANDONED_BUT_SIG_EXISTS, run worklist.py --plan-compact per plan. For DONE_SIG_NOT_IN_LEDGER, walk git log for the ledger file for a commit that does attest the signature and repoint done= there (check_plan_record.py:145's own rule: done= names the FIRST attesting commit); if none found, defer.
3. Judgment remainder (~370-390): list by plan, not by finding, as a follow-up checklist. Not attempted this pass.

## Verification

- Re-run both gates before and after; the finding-count delta must equal exactly the number of fixes applied.
- Both gates' own selftest() control suites stay 100% pass.
- Byte-diff sanity per touched plan: strip only the matched span from each changed line pre- and post-fix and assert the remainder is byte-identical; git diff --stat's changed-line count must equal citations touched in that file.
- Hand-spot-check roughly 20 mechanical fixes by opening the new file:line and confirming it still supports the plan's claim.

## Boxes

- [ ] Investigate whether the 103-delete/28-rename migration pattern is itself fixable (stub restoration) without a history rewrite, and whether doing so meaningfully shrinks the backlog before per-citation fixes.
- [ ] Script A implemented and run: bare-basename (678) + submodule-qualified (14) + stale-line (42) citation fixes, each with its own printed proof.
- [ ] Script B implemented and run: record findings 126 + 30 + 1 (INDEX.md).
- [ ] Both gates re-run; finding-count delta matches fixes applied exactly.
- [ ] Judgment-remainder checklist written (grouped by plan) for the ~370-390 left, explicitly not attempted this pass.

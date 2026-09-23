# PLAN: fix plan-citation and plan-record drift (958 + 161 findings)

Status: executing -- both mechanical scripts (A and B) and the gate-defect investigation are done.
Two dispatched writers have now each worked the judgment remainder box by box and reported back; the second round repaired 13 more entries (citation corpus 357 -> 250) and closed this plan's own box count from 27 to 14.
No further writer has been dispatched against this plan's own remaining boxes since that second round landed; unrelated worklist activity elsewhere in this session (main-CI-fix, renet retry-loop hardening, three new plan designs) does not change this plan's state. The 14 open boxes are genuine per-plan judgment calls in the "Judgment remainder" section below (line 124) and still need a dedicated pass, not a mechanical fix. A repo-wide plan-box ceiling sweep (worklist #060ffbb6, dispatched 2026-09-23) is still mid-pass on this plan among 22 others (9+ minutes in, sub-workers still cycling as of this update). This plan's own box count has not moved (14 open). Check its report before dispatching a second, overlapping writer here.
Remaining boxes are the "Judgment remainder" section's genuine per-plan calls, not force-closed.
Owner: d778be9d
Updated: 2026-09-23

## The finding

check:ci-plan-citations (958) and check:ci-plan-record (161) are both red, spanning dozens of plans this session never authored.

## Root cause (Plan agent a2fd17b15c79c8ceb)

check:ci-plan-citations only judges lines the working tree adds relative to origin/main (.ci/scripts/quality/check_plan_citations.py:241-266, diffed via git diff against base). To avoid double-counting a plan move as new content, it calls carried_lines(), which trusts a Status: moved / Moved-To: stub left at the old path (.ci/rediacc_ci/quality/plan_lifecycle.py:282-298).

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
2. Script B (record, mechanical): for ABANDONED_BUT_SIG_EXISTS, run worklist.py --plan-compact per plan. For DONE_SIG_NOT_IN_LEDGER, walk git log for the ledger file for a commit that does attest the signature and repoint done= there (.ci/scripts/quality/check_plan_record.py:145's own rule: done= names the FIRST attesting commit); if none found, defer.
3. Judgment remainder (~370-390): list by plan, not by finding, as a follow-up checklist. Not attempted this pass.

## Verification

- Re-run both gates before and after; the finding-count delta must equal exactly the number of fixes applied.
- Both gates' own selftest() control suites stay 100% pass.
- Byte-diff sanity per touched plan: strip only the matched span from each changed line pre- and post-fix and assert the remainder is byte-identical; git diff --stat's changed-line count must equal citations touched in that file.
- Hand-spot-check roughly 20 mechanical fixes by opening the new file:line and confirming it still supports the plan's claim.

## Boxes

- [x] Investigate whether the 103-delete/28-rename migration pattern is itself fixable (stub restoration) without a history rewrite, and whether doing so meaningfully shrinks the backlog before per-citation fixes.
    (ticked) 2026-09-23T08:44:08Z by d778be9d: Investigated and fixed: check_plan_record.py's attested_under_any_path was missing the git-history fallback names_this_record already had, committed d231c8c30, check:ci-plan-record 132 findings -> 4.
- [x] Script A implemented and run: bare-basename (678) + submodule-qualified (14) + stale-line (42) citation fixes, each with its own printed proof.
    (ticked) 2026-09-23T11:19:15Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Script B implemented and run: record findings 126 + 30 + 1 (INDEX.md).
    (ticked) 2026-09-23: the 126 were the gate defect item 1's investigation found and fixed directly (commit d231c8c30, attested_under_any_path's git-history fallback) -- they went green with no record edited, exactly as anticipated below. The 30 + 1 landed in Run 1.
- [x] Both gates re-run; finding-count delta matches fixes applied exactly.
    (ticked) 2026-09-23T11:19:15Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Judgment-remainder checklist written (grouped by plan) for the ~370-390 left, explicitly not attempted this pass.
    (ticked) 2026-09-23T11:19:15Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

## Run 1 (2026-09-23, session d778be9d)

Script B's box stays OPEN on purpose. 30 of its 157 findings are fixed and 126 are refused with the evidence in item 2 below; ticking it would claim a fix that was deliberately not made. It closes when `attested_under_any_path` learns the rename fallback its sibling already has, and the 126 go green without a single record being edited.

Two passes, because a concurrent session's `git stash` swept the first pass's unstaged edits out of 13 plan files between the runs (see item 5 below). Counts for each pass, and the ADDED side of the before/after finding-set diff is EMPTY in both:

| Pass | Gate | Before | After | Delta | Fixes applied |
|---|---|---|---|---|---|
| 1 | `check:ci-plan-citations` | 964 | 351 | 613 | 613 |
| 1 | `check:ci-plan-record` | 161 | 130 | 31 | 31 |
| 2 | `check:ci-plan-citations` | 632 | 352 | 280 | 280 |
| 2 | `check:ci-plan-record` | 131 | 130 | 1 | 1 |

Comparing totals is not the same claim as comparing sets: a fix that lands while an unrelated finding appears shows the same delta. Both passes were diffed as sets and the added side came back empty.

614 citation repoints are live in the tree across 39 plans, by rule:

- `A1-unique-basename`: the basename has exactly one match in the tree, so the path gets its directory prefix back. Proof printed per fix.
- `A2-submodule`: the gate itself named `private/<sub>/<path>` as the real location, and the root path really is absent.
- `A3-anchor` and `A1+A3-anchor`: the nearest OWNED strong anchor matched exactly one line in the cited file, so the line number moved with it. 4 fixes in total, hand-checked one by one.

Script B applied 30 `done=abandoned` to `done=dfabd8052` repoints on `agent/plans/PLAN-remove-autopilot.md`, plus the one `Record-Sig` re-derivation those force, plus `--update` for the stale `agent/INDEX.md` row.

### Five things that did not go as the plan assumed

**1. `worklist.py --plan-compact` cannot run on a compacted record.** The gate prints "Re-run `worklist.py --plan-compact` to pick it up" and the verb answers `agent/plans/PLAN-remove-autopilot.md is already a record.
Use --plan-revive ... first` at exit 2; `compact` then refuses the dirty path `--plan-revive --write` leaves behind, so the advised command needs two intervening commits to run at all. The 30 were fixed surgically instead: the `(record) sig=... done=` token and the `Record-Sig` header that `wl_planrec.record_sig` derives from the box table, and nothing else in the document.

**2. The 126 `done=<commit>` findings are a GATE defect, not a record defect, and repointing them would have destroyed 126 correct pointers.** Every one of the 126 resolves to `fce51e202`, the commit that MOVED 103 plans into `agent/plans/`, because `wl_planrec.done_commit` searches the ledger under the record's CURRENT path and that move re-keyed the ledger.
The signature really is attested, at the commit each record already names, under the plan's OLD flat path:

    git show c6e9c84c2:.ci/config/plan-boxes.json
      -> "agent/PLAN-citation-fragility.md": done_sigs [..., "4237ec1e", ...]

`check_plan_record.attested_under_any_path` already tries the legacy path, but only through `legacy_path_of`, which needs a `Status: moved` stub at the old path, and the 2026-09-22 cleanup deleted every one of those stubs. Its sibling `names_this_record` solved exactly this by falling through to `_named_by_git_history`, which asks git's own rename graph.
Refused and reported rather than baselined into the records.

**3. A citation inside a CHECKBOX line must not be repointed.** 48 of Script A's first-pass fixes landed on `- [x]` lines; a box is keyed on its own text (`wl_planrec.box_sig`), so those repoints renamed 28 boxes and `check:ci-plan-boxes` went from 2 findings to 14 (`done_sigs disagree -- N in the ledger and not the tree`).
Draining that by regenerating `.ci/config/plan-boxes.json` would have orphaned every `done=` proof keyed on the old signatures. All 48 were reverted to their exact previous bytes, `check:ci-plan-boxes` is back to its 2 pre-existing findings, and box-line citations are listed in the remainder below as judgment work.

**4. The gate's own submodule advice can name a file that exists.** `check_plan_citations.unresolved` reaches its submodule branch on ANY unresolved fileline, including one whose path exists at the root and is merely too short, and then prints "does not exist at the repository root, but `private/<sub>/<same basename>` does".
The citation of `README.md` at lines 49 to 54 in `agent/plans/PLAN-printf-echo-pipefail-sweep.md` hit exactly that: the root `README.md` is present with 36 lines, and the advice pointed at `private/renet/README.md`, an unrelated document. Spelled out here rather than quoted verbatim, because quoting it would make this paragraph carry the same dead citation.
The A2 rule trusted the message and produced a wrong pointer; the fix was reverted with the other box-line edits. The branch should distinguish "file missing" from "line out of range" before offering a submodule.

**5.
A concurrent session's `git stash` reverted 280 of the first pass's citation fixes.** `git reflog` shows two commits from another session at 09:41:22 and 09:50:08 and `git stash list` shows `stash@{0}: WIP on 0923-1: b2cf6a071`; `git stash show --name-only stash@{0}` lists exactly the 13 plan files whose fixes vanished, and each was byte-identical to its pre-edit snapshot afterwards.
The stash is another session's and holds this session's work mixed into it, so it was left alone and Script A was simply re-run, which is what makes an idempotent fixer worth writing. The lesson for the next pass is to `git add` each batch as it lands rather than at the end: unstaged work in a shared worktree is one `git stash` away from gone.

### What the mechanical fix does NOT claim

Script A repoints the PATH. The gate only asserts the line is IN RANGE, so a repointed citation can land in the right file on a line whose content has since drifted, and stay green.
Of 20 hand-spot-checked fixes the path is right in 20, and the cited line plainly supports the plan's sentence in 16; the other 4 (`.ci/rediacc_ci/tests/test_core_dockerx.py:489`, `.claude/hooks/stop/wl_checks.py:1115`, `scripts/data/domains.json:119`, `.claude/hooks/stop/wl_checks.py:1685`) land in the right file on a drifted line.
That drift is pre-existing, invisible to this gate, and judgment work.

## Judgment remainder, grouped by plan

Not attempted this pass. 351 citation findings across 41 plans and 130 record findings across 13 records. Each line is one plan, its finding count, and the categories those findings fall into.

Progress, 2026-09-23. The record half is finished: all 13 lines close, nine of them because `attested_under_any_path` now falls through to the rename graph (`.ci/scripts/quality/check_plan_record.py:322`) and the remaining four by re-deriving three Record-Sig lines and writing one record's author slots.
Fourteen of the 41 citation lines close as well. Seven were repaired in the plan text, five in archived plans, and two were never findings: a background agent id and a test's own content fingerprint are both long hex runs the object matcher claimed by coincidence of shape, and `AGENT_ID_RE` and `FINGERPRINT_RE` exempt each class with six controls between them.
The corpus stands at 351 citation findings and no record findings, against 385 and 130 when this section was written.

Second pass, 2026-09-23. Thirteen more citation lines close and the corpus stands at 250, against 351 above and 385 when this section opened. Three classes drained it.
Twelve findings across two plans were never dead pointers: a stop-hook tick id is no more a git object than the background agent id and the content fingerprint the two earlier exemptions cover, so `TICK_ID_RE` and `MARKER_FILE_RE` exempt the class behind its own markers, with a control in both directions on each matcher.
Twenty-one bare basenames across four plans sat on `- [x]` lines, the class item 3 above reverted, and the two hazards that forced that revert were re-measured rather than assumed: `check_plan_boxes.loose_sig` strips directory prefixes, so all seven touched box lines hash identically across the repoint and G-A1 sees no deletion, and `moved_to_done` judges only signatures that were OPEN at the merge base, so a re-keyed done box is never bound by P-A2. The strict signatures do move, and the six backfilled investigation rows that re-keyed with them were re-backfilled in the same pass.
The rest were pointers into bash gates and tests the Python port retired: each names its surviving successor at a line that was read, or, where the code it described was genuinely deleted, says so instead of naming a line that does not exist.

### check:ci-plan-citations, 351 findings across 41 plans

- [x] `agent/plans/PLAN-add-chunkstore-backup-verb.md` -- 1: 1 fileline: right file, stale line, no unambiguous anchor
    (ticked) 2026-09-23T10:35:45Z by d778be9d: check:ci-plan-citations names no finding in PLAN-add-chunkstore-backup-verb.md on a live run; the repaired pointer is at agent/plans/PLAN-add-chunkstore-backup-verb.md:26
- [x] `agent/plans/PLAN-agent-hints-implementation.md` -- 1: 1 fileline: right file, stale line, no unambiguous anchor
    (ticked) 2026-09-23T10:35:45Z by d778be9d: check:ci-plan-citations names no finding in PLAN-agent-hints-implementation.md on a live run; the repaired pointer is at agent/plans/PLAN-agent-hints-implementation.md:32
- [x] `agent/plans/PLAN-agent-hints-in-stop-hook.md` -- 1: 1 gate: no such `check:` script
    (ticked) 2026-09-23T10:35:43Z by d778be9d: check:ci-plan-citations names no finding in PLAN-agent-hints-in-stop-hook.md on a live run; the repaired pointer is at agent/plans/PLAN-agent-hints-in-stop-hook.md:46
- [x] `agent/plans/PLAN-agent-tree-lifecycle.md` -- 5: 5 fileline ON A BOX LINE (editing it re-keys the box signature)
    (ticked) 2026-09-23T12:16:25Z by d778be9d: Investigated at a959e94ad. check:ci-plan-citations names no finding against PLAN-agent-tree-lifecycle.md on a live run; the repaired pointers are on agent/plans/PLAN-agent-tree-lifecycle.md:55 and the box loose_sig is unchanged.
- [ ] `agent/plans/PLAN-commit-author-identity.md` -- 5: 3 fileline: basename matches NOTHING in the tree; 2 fileline: right file, stale line, no unambiguous anchor
- [x] `agent/plans/PLAN-duplication-angle.md` -- 1: 1 gate: no such `check:` script
    (ticked) 2026-09-23T10:35:44Z by d778be9d: check:ci-plan-citations names no finding in PLAN-duplication-angle.md on a live run; the repaired pointer is at agent/plans/PLAN-duplication-angle.md:32
- [ ] `agent/plans/PLAN-env-to-bitwarden-v2.md` -- 14: 7 fileline: basename matches NOTHING in the tree; 4 fileline: unique basename but the line is out of range there too; 1 fileline ON A BOX LINE (editing it re-keys the box signature); 1 fileline: right file, stale line, no unambiguous anchor; 1 gate: no such `check:` script
- [x] `agent/plans/PLAN-fix-plan-citation-drift.md` -- 2: 2 object: neither blob nor reachable commit
    (ticked) 2026-09-23T10:35:45Z by d778be9d: check:ci-plan-citations names no finding in PLAN-fix-plan-citation-drift.md on a live run; the repaired pointer is at agent/plans/PLAN-fix-plan-citation-drift.md:11
- [ ] `agent/plans/PLAN-gh-swallow-gates-audit.md` -- 2: 2 fileline ON A BOX LINE (editing it re-keys the box signature)
- [x] `agent/plans/PLAN-github-actions-to-bitwarden.md` -- 9: 4 fileline: basename matches 2 files, ambiguous; 3 gate: no such `check:` script; 2 fileline ON A BOX LINE (editing it re-keys the box signature)
    (ticked) 2026-09-23T12:18:01Z by d778be9d: Investigated at 45d828cac. check:ci-plan-citations names no finding against PLAN-github-actions-to-bitwarden.md on a live run; the repointed workflow citations resolve, including .github/workflows/ci.yml:1354.
- [x] `agent/plans/PLAN-haiku-model-routing.md` -- 3: 3 gate: no such `check:` script
    (ticked) 2026-09-23T10:35:44Z by d778be9d: check:ci-plan-citations names no finding in PLAN-haiku-model-routing.md on a live run; the repaired pointer is at agent/plans/PLAN-haiku-model-routing.md:41
- [x] `agent/plans/_done/PLAN-migrate-plan-doc-discovery.md` -- 11: 8 fileline: basename matches 2 files, ambiguous; 2 plan: cited plan file gone; 1 gate: no such `check:` script
    (ticked) 2026-09-23T12:30:02Z by d778be9d: Investigated at a20d282f8. check:ci-plan-citations names no finding against PLAN-migrate-plan-doc-discovery.md on a live run; the repointed pointers include .claude/hooks/stop/worklist.py:1167 and .claude/hooks/stop/wl_store.py:1804, both re-read against the claim they carry.
- [x] `agent/plans/PLAN-npm-ci-parallel-parity.md` -- 1: 1 gate: no such `check:` script
    (ticked) 2026-09-23T10:35:44Z by d778be9d: check:ci-plan-citations names no finding in PLAN-npm-ci-parallel-parity.md on a live run; the repaired pointer is at agent/plans/PLAN-npm-ci-parallel-parity.md:35
- [x] `agent/plans/PLAN-pipefail-grep-q-renet-gate.md` -- 14: 11 fileline: basename matches NOTHING in the tree; 2 fileline: right file, stale line, no unambiguous anchor; 1 fileline ON A BOX LINE (editing it re-keys the box signature)
    (ticked) 2026-09-23T12:18:00Z by d778be9d: Investigated at 45d828cac. check:ci-plan-citations names no finding against PLAN-pipefail-grep-q-renet-gate.md on a live run; the repaired pointers start at agent/plans/PLAN-pipefail-grep-q-renet-gate.md:24.
- [ ] `agent/plans/PLAN-plan-file-lifecycle.md` -- 6: 3 fileline: basename matches NOTHING in the tree; 2 fileline: unique basename but the line is out of range there too; 1 plan: cited plan file gone
- [ ] `agent/plans/PLAN-plan-implementation-enforcement.md` -- 11: 9 fileline: basename matches 2 files, ambiguous; 2 fileline ON A BOX LINE (editing it re-keys the box signature)
- [x] `agent/plans/_done/PLAN-plyr-css-on-demand-loading.md` -- 2: 2 fileline: basename matches NOTHING in the tree
    (ticked) 2026-09-23T10:35:46Z by d778be9d: check:ci-plan-citations names no finding in PLAN-plyr-css-on-demand-loading.md on a live run; the repaired pointer is at agent/plans/_done/PLAN-plyr-css-on-demand-loading.md:27
- [x] `agent/plans/PLAN-popup-reminder.md` -- 1: 1 object: neither blob nor reachable commit
    (ticked) 2026-09-23T10:35:45Z by d778be9d: check:ci-plan-citations names no finding in PLAN-popup-reminder.md on a live run; the repaired pointer is at agent/plans/PLAN-popup-reminder.md:11
- [ ] `agent/plans/PLAN-printf-echo-pipefail-sweep.md` -- 5: 5 fileline ON A BOX LINE (editing it re-keys the box signature)
- [ ] `agent/plans/PLAN-remove-autopilot.md` -- 2: 2 gate: no such `check:` script
- [ ] `agent/plans/PLAN-secret-namespace-migration.md` -- 82: 44 fileline: basename matches NOTHING in the tree; 19 fileline ON A BOX LINE (editing it re-keys the box signature); 6 fileline: unique basename but the line is out of range there too; 5 plan: cited plan file gone; 5 object: neither blob nor reachable commit; 2 fileline: right file, stale line, no unambiguous anchor; 1 fileline: basename matches 4 files, ambiguous
- [x] `agent/plans/PLAN-shell-resource-profiling.md` -- 1: 1 gate: no such `check:` script
    (ticked) 2026-09-23T10:35:44Z by d778be9d: check:ci-plan-citations names no finding in PLAN-shell-resource-profiling.md on a live run; the repaired pointer is at agent/plans/PLAN-shell-resource-profiling.md:33
- [ ] `agent/plans/PLAN-stop-hook-overhaul.md` -- 8: 6 fileline: right file, stale line, no unambiguous anchor; 1 fileline: basename matches NOTHING in the tree; 1 fileline ON A BOX LINE (editing it re-keys the box signature)
- [x] `agent/plans/PLAN-stop-hook-refactor-enforcement.md` -- 1: 1 fileline ON A BOX LINE (editing it re-keys the box signature)
    (ticked) 2026-09-23T12:09:46Z by d778be9d: Investigated at d30f418f1. check:ci-plan-citations names no finding against PLAN-stop-hook-refactor-enforcement.md on a live run; the repaired pointer is at agent/plans/PLAN-stop-hook-refactor-enforcement.md:218 and resolves to scripts/gates/check-shape-duplication.ts:1455.
- [x] `agent/plans/PLAN-sweep-obligation-carry-forward.md` -- 10: 10 object: neither blob nor reachable commit
    (ticked) 2026-09-23T12:09:46Z by d778be9d: Investigated at d30f418f1. check:ci-plan-citations names no finding against PLAN-sweep-obligation-carry-forward.md on a live run; all ten were stop-hook tick ids, now exempt behind their own markers at .ci/scripts/quality/check_plan_citations.py:275 with four controls in both directions.
- [ ] `agent/plans/PLAN-tooling-transformation.md` -- 54: 31 fileline: basename matches NOTHING in the tree; 16 fileline: right file, stale line, no unambiguous anchor; 5 fileline ON A BOX LINE (editing it re-keys the box signature); 2 object: neither blob nor reachable commit
- [x] `agent/plans/PLAN-trap-enforcement.md` -- 24: 17 fileline: basename matches NOTHING in the tree; 5 gate: no such `check:` script; 1 object: neither blob nor reachable commit; 1 fileline: basename matches 2 files, ambiguous
    (ticked) 2026-09-23T12:42:00Z by d778be9d: Investigated at 366d414a9. check:ci-plan-citations names no finding against PLAN-trap-enforcement.md on a live run; the last survivor was a dead sweep sha, and agent/plans/PLAN-trap-enforcement.md:319 now carries the run and job ids instead.
- [x] `agent/plans/PLAN-w9p2-script-relocation.md` -- 9: 9 fileline: basename matches NOTHING in the tree
    (ticked) 2026-09-23T12:40:46Z by d778be9d: Investigated at 7c0f2c086. check:ci-plan-citations names no finding against PLAN-w9p2-script-relocation.md on a live run; each retired bash gate now names its Python successor, two of them spot-checked at .ci/rediacc_ci/security/shfmt.py:100 and .ci/rediacc_ci/quality/silent_failure_patterns.py:80.
- [x] `agent/plans/_done/PLAN-agent-session-archival.md` -- 1: 1 fileline: basename matches 38 files, ambiguous
    (ticked) 2026-09-23T10:35:45Z by d778be9d: check:ci-plan-citations names no finding in PLAN-agent-session-archival.md on a live run; the repaired pointer is at agent/plans/_done/PLAN-agent-session-archival.md:14
- [x] `agent/plans/_done/PLAN-archival-tests-python-compliance.md` -- 8: 6 fileline: basename matches NOTHING in the tree; 1 object: neither blob nor reachable commit; 1 fileline ON A BOX LINE (editing it re-keys the box signature)
    (ticked) 2026-09-23T12:16:25Z by d778be9d: Investigated at a959e94ad. check:ci-plan-citations names no finding against PLAN-archival-tests-python-compliance.md on a live run; the repaired pointer is at agent/plans/_done/PLAN-archival-tests-python-compliance.md:121.
- [x] `agent/plans/_done/PLAN-ci-pr-head-ref-trigger-resolution.md` -- 3: 3 fileline: basename matches NOTHING in the tree
    (ticked) 2026-09-23T10:35:46Z by d778be9d: check:ci-plan-citations names no finding in PLAN-ci-pr-head-ref-trigger-resolution.md on a live run; the repaired pointer is at agent/plans/_done/PLAN-ci-pr-head-ref-trigger-resolution.md:152
- [x] `agent/plans/_done/PLAN-ci-vacuity-baseline-registry.md` -- 6: 5 fileline: right file, stale line, no unambiguous anchor; 1 fileline: basename matches NOTHING in the tree
    (ticked) 2026-09-23T12:40:46Z by d778be9d: Investigated at 7c0f2c086. check:ci-plan-citations names no finding against PLAN-ci-vacuity-baseline-registry.md on a live run; the drifted release-key pointer now resolves at .ci/rediacc_ci/quality/release_key_canonical.py:550.
- [x] `agent/plans/_done/PLAN-cleanup-context-state-files.md` -- 1: 1 fileline ON A BOX LINE (editing it re-keys the box signature)
    (ticked) 2026-09-23T12:16:25Z by d778be9d: Investigated at a959e94ad. check:ci-plan-citations names no finding against PLAN-cleanup-context-state-files.md on a live run; the repaired pointer is at agent/plans/_done/PLAN-cleanup-context-state-files.md:27.
- [x] `agent/plans/_done/PLAN-eliminate-worklist-report-per-stop-env.md` -- 14: 14 fileline ON A BOX LINE (editing it re-keys the box signature)
    (ticked) 2026-09-23T12:16:25Z by d778be9d: Investigated at a959e94ad. check:ci-plan-citations names no finding against PLAN-eliminate-worklist-report-per-stop-env.md on a live run; the repaired pointers start at agent/plans/_done/PLAN-eliminate-worklist-report-per-stop-env.md:171.
- [x] `agent/plans/_done/PLAN-fix-stop-hook-completion-evidence-refire.md` -- 4: 4 object: neither blob nor reachable commit
    (ticked) 2026-09-23T12:09:46Z by d778be9d: Investigated at d30f418f1. check:ci-plan-citations names no finding against PLAN-fix-stop-hook-completion-evidence-refire.md on a live run; both survivors were one tick id, marked at agent/plans/_done/PLAN-fix-stop-hook-completion-evidence-refire.md:31.
- [ ] `agent/plans/_done/PLAN-hint-corpus-ci-assertions.md` -- 4: 2 fileline ON A BOX LINE (editing it re-keys the box signature); 1 gate: no such `check:` script; 1 fileline: basename matches NOTHING in the tree
- [x] `agent/plans/_done/PLAN-reflow-comments-boundary-wrapping.md` -- 1: 1 fileline: basename matches NOTHING in the tree
    (ticked) 2026-09-23T10:35:46Z by d778be9d: check:ci-plan-citations names no finding in PLAN-reflow-comments-boundary-wrapping.md on a live run; the repaired pointer is at agent/plans/_done/PLAN-reflow-comments-boundary-wrapping.md:23
- [ ] `agent/plans/_done/PLAN-stop-hook-behavioral-hints.md` -- 5: 4 fileline ON A BOX LINE (editing it re-keys the box signature); 1 fileline: basename matches 2 files, ambiguous
- [ ] `agent/plans/_done/PLAN-stop-hook-plan-backlog-nudge.md` -- 10: 5 fileline ON A BOX LINE (editing it re-keys the box signature); 4 fileline: basename matches 2 files, ambiguous; 1 object: neither blob nor reachable commit
- [ ] `agent/plans/_done/PLAN-stop-hook-task-verification.md` -- 2: 1 fileline: basename matches 2 files, ambiguous; 1 fileline ON A BOX LINE (editing it re-keys the box signature)
- [x] `agent/plans/_done/PLAN-sys-path-canonical-form.md` -- 6: 6 object: neither blob nor reachable commit
    (ticked) 2026-09-23T10:35:46Z by d778be9d: check:ci-plan-citations names no finding in PLAN-sys-path-canonical-form.md on a live run; the repaired pointer is at agent/plans/_done/PLAN-sys-path-canonical-form.md:22

### check:ci-plan-record, 130 findings across 13 records

- [x] `agent/plans/PLAN-citation-fragility.md` -- 7: 6 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT; 1 R7 Record-Sig mismatch: box table hand-edited, re-derive or revive+recompact
    (ticked) 2026-09-23T10:41:27Z by d778be9d: check:ci-plan-record names no finding against this record on a live run; Record-Sig 895f079d now equals the derived spine, and the R4 fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-consolidation-pressure.md` -- 11: 10 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT; 1 R7 Record-Sig mismatch: box table hand-edited, re-derive or revive+recompact
    (ticked) 2026-09-23T10:41:27Z by d778be9d: check:ci-plan-record names no finding against this record on a live run; Record-Sig 98d03a8d now equals the derived spine, and the R4 fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-gh-swallow-gates-audit.md` -- 6: 6 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:46Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-gh-swallow-gates-audit.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-git-ignore-aware-discover.md` -- 10: 10 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:46Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-git-ignore-aware-discover.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-judge-prompt-trap-conflation.md` -- 8: 8 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:46Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-judge-prompt-trap-conflation.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-printf-echo-pipefail-sweep.md` -- 33: 33 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:46Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-printf-echo-pipefail-sweep.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-pytest-parallelism.md` -- 10: 10 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:46Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-pytest-parallelism.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-remove-autopilot.md` -- 1: 1 R6 unfilled <FILL: ...> placeholder: needs an author
    (ticked) 2026-09-23T10:41:27Z by d778be9d: check:ci-plan-record names no unfilled-placeholder finding against this record on a live run; the three slots are written at agent/plans/PLAN-remove-autopilot.md:7
- [x] `agent/plans/PLAN-rest-graphql-guard-parity.md` -- 8: 8 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:47Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-rest-graphql-guard-parity.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-staged-duplication-probe.md` -- 9: 8 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT; 1 R7 Record-Sig mismatch: box table hand-edited, re-derive or revive+recompact
    (ticked) 2026-09-23T10:41:35Z by d778be9d: check:ci-plan-record names no R4 or R7 finding against this record on a live run; Record-Sig b5b343e3 equals the spine derived at .ci/scripts/quality/check_plan_record.py:322 and the record is back to 3329 bytes against a 6747-byte blob
- [x] `agent/plans/PLAN-w7p4w-docker-cutover.md` -- 12: 12 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:47Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-w7p4w-docker-cutover.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-w7p5a-deploy-release-port.md` -- 8: 8 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:47Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-w7p5a-deploy-release-port.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322
- [x] `agent/plans/PLAN-wl-report-liveness-oracle.md` -- 7: 7 R4 done=<commit>: gate is rename-blind (see item 2 above); the record is RIGHT
    (ticked) 2026-09-23T10:19:47Z by d778be9d: check:ci-plan-record now reports 5 problems across 75 records with no finding against PLAN-wl-report-liveness-oracle.md; the R4 rename fallback is at .ci/scripts/quality/check_plan_record.py:322

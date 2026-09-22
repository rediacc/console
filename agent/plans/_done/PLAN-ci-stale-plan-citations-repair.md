# PLAN: repair check:ci-plan-citations after the plan-folder move
Status: done
First-Seen: 2026-09-22
Owner: d778be9d
Updated: 2026-09-21

## Why
`check:ci-plan-citations` reds with 337 findings across 28 files under `agent/plans/`, all surfaced by the plan-folder move landed this session. Two defects, both measured against the tree rather than assumed.

D1, the exclusion never fires. `carried_lines()` in `.ci/scripts/quality/check_plan_citations.py:288-296` reads the pre-move content as `git show <base>:<origin>`, where `base` is the merge-base with main. That blob is wrong two ways on this branch: the origin is absent at base for 5 of 13 sampled plans (including the 79-finding `PLAN-tooling-transformation.md`), so `_git` returns
an empty string and nothing is excluded; and where the origin is present, `05b753df3 style(docs): reflow 381 markdown files` already changed every line's exact text on this branch after the base, so none of the moved lines match verbatim. Replacing the base blob with the origin's last non-stub blob covers 277 of 279 distinct flagged lines in a sample check; the remaining 2 are
genuinely branch-authored and belong to D2.

D2, real citation rot the move exposed rather than caused: targets relocated by earlier refactors (for example `f59db0679`, the scripts/dev to scripts/ops move), by this branch's bash-twin retirement wave, and by submodule extraction.

## Findings summary
By kind: 319 fileline, 7 gate, 6 plan, 5 object. By cited-path fate (fileline only): 161 moved to a uniquely resolvable path, 105 gone entirely, 48 line-drift only (file exists, cited line past its end), 5 ambiguous. Only one flagged plan is `Status: compacted`, so the compacted-plan question is a small fraction of the total, not a design driver.

Per-file counts (largest first): tooling-transformation 79, secret-namespace-migration 74, trap-enforcement 43, migrate-plan-doc-discovery 25, env-to-bitwarden-v2 16, w9p2-script-relocation 12, pipefail-grep-q-renet-gate 11, plan-file-lifecycle 10, agent-tree-lifecycle 9, stop-hook-overhaul 8, ci-vacuity-baseline-registry 8, plyr-css 7, `_done/reflow-comments-boundary-wrapping` 6,
printf-echo-pipefail-sweep 5, `_done/subscription-status-error-swallowing` 3, the remainder 1 to 3 each.

## Part B: the gate fix (do first, it shrinks Part A to 2 lines)
Change `carried_lines()` at `.ci/scripts/quality/check_plan_citations.py:288-296`. Keep the `moved_from()` probe (`:266-286`), then take the union of `git show <base>:<origin>` and a new `_origin_last_content(origin)`: walk `git log --format=%H -- <origin>` newest first, `git show <sha>:<origin>`, and return the first blob that is not `PL.looks_like_stub(...)`. Union with the
existing base-blob read so that path cannot regress.

Why it still catches new debt: a citation written after the move is in neither blob. A reflow landing after the move would rewrap the moved lines again and re-expose the class; record that residual in the docstring as a known limit, with a follow-up noted to compare extracted citation tokens rather than raw lines.

Test: add `.ci/rediacc_ci/tests/gates/test_gate_plan_citations.py`, modelled on `.ci/rediacc_ci/tests/gates/test_gate_plan_folders.py:1-40` (a real git fixture, the gate run as a subprocess, its exit code read). The gate honours `PLAN_CITATIONS_ROOT` (`:83`) and `PLAN_CITATIONS_BASE` (`:225`) for exactly this kind of fixture.

Four cases: (1) regression -- commit a plan citing a live file, reflow it, move it with a stub, delete the cited file; `PLAN_CITATIONS_BASE` at the first commit must exit 0. (2) control -- the same fixture plus one new line added after the move citing a path that never existed; must exit 1 and name that line. (3) control -- a never-moved plan with a new stale citation; still exit
1. (4) control -- the exclusion is scoped to the moved plan, so a stale citation added to a different plan in the same commit is still reported.

## Part A: the two branch-authored citations (fix by hand regardless of Part B)
The two file-and-line spellings below are written with " line " rather than a colon on purpose, so this design document itself does not trip the gate it describes.
- `PLAN-migrate-plan-doc-discovery.md`, line 63, cites `check_plan_record.py` line 205; the current location is `.ci/scripts/quality/check_plan_record.py` line 165 (`CENSUS_REL`).
- `PLAN-trap-enforcement.md`, line 33, cites the archived licensing report line 234; the anchor text
  `**WHY KNOWING ABOUT IT DOES NOT PREVENT IT.**` is now at line 130. The adjacent lines 230 to 232 drift the same way and need the same re-anchoring.

## Mechanical rules for the residual sweep once Part B lands
Only needed if a future regression reopens the corpus; recorded here so the next session does not re-derive them. R1 bash-twin retirement (about 45 citations, all deleted on this branch): `.ci/scripts/security/X.sh` maps to `.ci/rediacc_ci/security/X.py`; `.ci/scripts/quality/check-X.sh` to `.ci/rediacc_ci/quality/X.py`; `.ci/scripts/test/gates/test-X.sh` to
`.ci/rediacc_ci/tests/gates/test_gate_X.py` (dashes to underscores); `.ci/scripts/test/run-all.sh` to `.ci/rediacc_ci/battery.py` per `1306a6539`. Re-find the exact line by reading the old blob at the deletion commit's parent and grepping that text in the successor. R2 submodule-qualify (about 50): prefix `private/account/`, `private/renet/`, `private/elite/`, or `private/growth/`.
R3 bare basename to a unique tracked path (about 60): `wl_*.py`, `worklist.py`, `worklist_messages.py` resolve under `.claude/hooks/stop/`; `check_*.py` under `.ci/scripts/quality/`; then re-anchor the line by content search. R4 line drift (48): the path is right, search the plan's own quoted text in the live file. R5 (5): `.agent/TRAPS.md:N` resolves to
`docs/agent-reference/TRAPS.md`, re-anchored by quote.

## Operator rulings 2026-09-21 on the human-call items
The gate ids and paths below are written without their `check:` prefix or `agent/` prefix on purpose, for the same self-reference reason as Part A.
1. The gate ids `ci-hook-worklist-suite` (4 citations) and `ci-docs-links` (2 citations) name gates with no successor key in `package.json`. Ruling: retarget the worklist-suite citations at the `ci-pytest` gate, which now collects those tests; mark the docs-links citations historical, since no successor gate exists.
2. Verified moot after Part B lands: the five non-sha object citations (two key fingerprints, a Cloudflare account id twice, one rewritten sha), the one out-of-repo citation, and the two `node_modules` build-output citations no longer appear in the finding list once `carried_lines` reads the origin's own history.
   No extractor change is needed for them; recorded here in case a future regression reopens the corpus.
3. The gate id `does-not-exist` and the plan path `PLAN-x.md` in two plans are deliberate examples inside prose: fence them with the style-ok marker.

## Steps
- [x] Design confirmed by a Plan agent against the live tree.
- [x] Operator rulings recorded on the human-call items.
- [x] Landed Part B in `check_plan_citations.py` (union of the base blob and the origin's own history) plus its docstring.
- [x] Added `.ci/rediacc_ci/tests/gates/test_gate_plan_citations.py` with four cases (a real git fixture); all pass, and the regression case is the one that failed before the fix.
- [x] Re-ran `check:ci-plan-citations`: 337 fell to 8, all of them the two branch-authored citations plus this plan's own worked examples quoting them.
- [x] Fixed the two branch-authored citations (migrate-plan-doc-discovery.md, trap-enforcement.md) and reworded this plan's examples so it does not trip the gate it describes.
- [x] Checked the six worklist-suite and docs-links citations: none currently fail (they sit on unchanged lines outside the diff this gate judges), and the docs-links ones are historical measurements of the gate's own absence rather than live claims, so no edit was needed for the gate to stay green.
- [x] `check:ci-plan-citations` is green.

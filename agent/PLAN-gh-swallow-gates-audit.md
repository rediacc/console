# PLAN: gh Swallow-Failure Sweep Across `.ci/scripts` — Registered-Gate False-Green Risks
Status: compacted
Owner: f4da5c2e
Full-Text-Blob: 0bc5643419d3a228acd5a16a7e47c6de6d393e0f
Record-Sig: 1ce764b7

## Why
The gh command swallow pattern (gh ... 2>/dev/null || echo <default>) silently turned failures into fabricated empty responses, creating false-green risks in registered CI gates that block merges. Four quality gates carried defects: check-pr-description, check-submodule-branches, check-label-inventory, and mark-production. A stop-hook judge required a sweep; hand re-deriving found
instances the automated scanner missed (multi-line continuations, warn-then-fail misclassification).

## Outcome
All four registered-gate fixes landed in session [unresolved]. Bash twins and live Python ports both hardened: pr_description.py lines 287-291, submodule_branches.py console_pr_body, label_inventory.py lines 602-621, mark_production.sh lines 102-110. Tests: pr_description 2 new cases (14/14 pass), submodule_branches (35/35), label_inventory (20/20), mark_production (7/7).
Verification: bash -n clean, python3 -m ast clean, gates re-run against real tree. 11 files scoped.

## Lessons
- Ports replicate flaws faithfully: three of four live Python gates inherited bash swallows unchanged in the 2026-09-08 cutover. Post-port inspection or explicit fixing needed, not faith in deferred fixes.
- The swallow-scanner blind spot: warn-then-fail (log_warn; exit 0) reads as safe by its heuristic but is false-green. Hand re-verification of high-stakes findings is non-optional.
- Sentinel patterns need the right consequence: gh ... || echo empty is safe only if empty cannot occur (proven array size, jq reducing to a field that exists). Check must fail hard on failure, not skip.
- Production scripts live outside merge gates but carry highest severity: mark-production tag-move bug corrupts production ref silently and would have shipped undetected in a registered-gates-only scope.

## Boxes
- [x] Fix instance #2 (.ci/scripts/quality/check-pr-description.sh:59-62 + .ci/rediacc_ci/quality/pr_description.py:287-291): a swallowed LATEST_COMMIT_TIME fetch failure now escalates (exit 1 / return 1), not warn-and-skip
    (record) sig=b7697c16 done=6b1a1b060
- [x] Fix instance #8 (check-submodule-branches.sh get_console_pr_body + submodule_branches.py console_pr_body): now routes through gh_retry/gh_probe, distinguishes fetch-failed from empty-body, escalates on failure
    (record) sig=75434b8e done=771a172c5
- [x] Fix instance #9 (.ci/scripts/quality/check-label-inventory.sh:346-351 + .ci/rediacc_ci/quality/label_inventory.py:602-621): a failed live-label API fetch now refuses the drift comparison instead of silently reporting "all agree"
    (record) sig=9b15a996 done=6b1a1b060
- [x] Fix instances #11/#12 (.ci/scripts/release/mark-production.sh:102-110): a failed tag object-type/deref lookup now aborts instead of silently moving the production tag to the wrong object
    (record) sig=518a6b31 done=6b1a1b060
- [x] Add/extend tests for all four fixes: pr_description 2 differential cases flipped/added (14/14 pass), a new console_pr_body gh-stub test pair (35/35 pass total), a label-inventory GitHub-API-branch test (20/20 pass), two mark-production gate-test cases (7/7 pass)
    (record) sig=418da40b done=771a172c5
- [x] Sweep and classify every gh-swallow instance across .ci/scripts (30 verified, 4 registered-gate/production-correctness fixes identified, rest confirmed already-safe or genuine best-effort housekeeping)
    (record) sig=2712c77e done=771a172c5

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:11:05Z
Boxes: 6 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/scripts/quality/check-pr-description.sh, .ci/rediacc_ci/quality/pr_description.py, .ci/scripts/quality/check-label-inventory.sh, .ci/rediacc_ci/quality/label_inventory.py, .ci/scripts/release/mark-production.sh, .ci/rediacc_ci/quality/submodule_branches.py
Gates: check:ci-dead-python, check:ci-label-inventory, check:ci-language-policy, check:ci-parity, check:ci-python-lint
Why-Source: model
Read-History: `git show 0bc5643419d3a228acd5a16a7e47c6de6d393e0f` recovers the text; `git log --find-object=0bc5643419d3a228acd5a16a7e47c6de6d393e0f --all` names the commit

## History
- 2026-09-20T18:11:05Z compacted by d778be9d from `done` (record-sig 1ce764b7)

# PLAN: a stop-hook check for "CI green, Review Complete red" -- the local
Status: compacted
Owner: unowned (branch 0827-1, PR #579)
Full-Text-Blob: bdf12c8a563f86d21082eed7b8475e6204fd2146
Record-Sig: ffab1c90

## Why
When CI was green on a PR but the 'Review Complete' check-run concluded with failure, the local stop hook had zero detection of this condition. The operator encountered this ~4 times in one session and had to notice it only by accident in trace logs or manual `gh pr checks` queries. The check is non-blocking (kept out of the hard/soft CI bucket by `CI_NONBLOCKING_CONTEXTS`), but
that absence from the CI verdict made it invisible to the hook — the problem was not that Review Complete shouldn't block, but that a session with context shouldn't miss the signal.

## Outcome
Landed in commit 4a00daed. The stop hook now runs `review_red()` whenever CI is genuinely clean, detects a red 'Review Complete' conclusion, fetches the check-run's own output.summary (avoiding reimplementation drift), quotes it verbatim, and applies the same bounded-N ceiling + ack escape discipline as `ci_trouble()` uses. Tests: 15 fixture controls in `wl_ci.py --selftest` (was
6), full hook suite 1773/1773, ci:quick clean, two independent reviews with zero new findings.

## Lessons
- Non-blocking ≠ invisible: A context kept out of CI hard/soft by design still needs separate detection. Separate review_gate_row() preserved CI_NONBLOCKING_CONTEXTS while enabling the signal.
- Quote the source of truth, never reimplement: Fetch the check-run's output.summary rather than deriving "unreplied" in Python. Prevents drift, costs one bounded REST call only in positive case.
- Ceiling logic applies to self-clearing conditions: Review Complete can be fixed by the session's own action, but three other failure shapes exist. Uniform bounded-N ceiling necessary because the check cannot distinguish shapes cheaply upfront.
- Re-evaluation commands often already exist: review-status.yml already had workflow_dispatch with pr_number input. Don't invent new mechanisms; search the tree first.
- Dual-shape matching in classifiers: Filter both CheckRun.name (GraphQL) and StatusContext.context (REST), as ci_classify does. Separate logic prevents accidental weakening of CI_NONBLOCKING_CONTEXTS.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:11:54Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: .github/workflows/review-status.yml, .claude/hooks/test-hooks.sh
Gates: none
Why-Source: model
Read-History: `git show bdf12c8a563f86d21082eed7b8475e6204fd2146` recovers the text; `git log --find-object=bdf12c8a563f86d21082eed7b8475e6204fd2146 --all` names the commit

## History
- 2026-09-20T18:11:54Z compacted by d778be9d from `done` (record-sig ffab1c90)

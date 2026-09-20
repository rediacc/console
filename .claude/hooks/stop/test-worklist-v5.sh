#!/bin/bash

# THE RUNNER. The suite itself lives next door in worklist-cases/: one shared
# harness (`_harness.sh`, the ONLY copy of setup/check/run and the counters)
# plus 22 topic files sourced in order. This file owns the ambient scrub, the
# fixture roots, the counters and the summary line, and nothing else.
#
# WHY IT WAS SPLIT, measured 2026-08-25 with the pinned shellcheck 0.10.0:
# as one 11,968-line file it cost **2714 MB** of peak RSS with dataflow
# analysis on, against 199 MB with it off. On a 6.6 GB box that OOM-killed the
# whole shell gate -- 451 files, 3074 MB -- surfacing as a bare "Killed" that
# named neither memory nor the tool. Almost the entire corpus cost was THIS
# file, so a `# shellcheck extended-analysis=false` directive used to sit here
# buying the memory back by DISABLING dataflow analysis, i.e. by giving up real
# checks on the largest test in the tree.
#
# Shellcheck's cost is superlinear in file length, so splitting is not a
# rearrangement of the same total: the largest piece below (896 lines) costs
# 69 MB with dataflow ON. The directive is therefore GONE, and the suite is
# analysed more thoroughly than it was before the split, not less. Keep the
# pieces roughly this size; a file that grows past ~1,500 lines starts paying
# the curve again.

# Controls for worklist.py v5. Every check must FIRE on a planted defect and
# stay silent when clean. Nothing here touches the live worklist: TMPDIR,
# WORKLIST_TASKS_DIR and the project root are all isolated fixtures.
set -uo pipefail

# AMBIENT SCRUB, before a single case runs. The hook reads ~65 WORKLIST_* knobs
# and setup() resets only the ones cases set, so anything exported in the shell
# that launches this suite silently retuned it: a developer who set
# WORKLIST_BG_REPORT_MIN or WORKLIST_QUIET_WAKES while debugging would get a
# different suite from CI's, and the difference would look like flakiness rather
# than like configuration. The fixtures were always isolated on DISK (TMPDIR,
# WORKLIST_TASKS_DIR, the project root); this makes them isolated in the
# ENVIRONMENT too. WORKLIST_AGENT_BRANCH and the rest are exported by setup()
# and the cases themselves, after this point, so nothing the suite needs is lost.
#
# CLAUDE_CODE_SESSION_ID IS SCRUBBED TOO, and it is not decoration -- one
# omission here produced two OPPOSITE failures. Since v19 every `<me>` argument
# is checked against the real session id (wl_core.check_me), which resolves
# WORKLIST_SESSION_ID first and CLAUDE_CODE_SESSION_ID second. Run from inside
# a Claude session with the ambient id live, every fixture prefix mismatches and
# ~110 call sites refuse: mass breakage that looks like a broken feature. Run in
# CI with it unset, check_me takes its silent-pass path and every identity case
# passes VACUOUSLY -- a green suite proving nothing, inside the very change
# meant to close a cannot-fire gap. The second is the dangerous one, because it
# is green. Scrubbing makes the suite behave identically in both places, and
# case 186's meta-control (worklist-cases/18-identity.sh) is what proves the
# scrub actually happened.
while IFS='=' read -r _k _; do
    case "$_k" in
        WORKLIST_* | CLAUDE_CODE_SESSION_ID | CLAUDE_SESSION_ID) unset "$_k" ;;
    esac
done < <(env)
unset _k

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/worklist.py"
BASE="$(mktemp -d)/hookfix"
trap 'rm -rf "$(dirname "$BASE")"' EXIT
SID="deadbeef-1111-2222-3333-444444444444"
# ARMED, suite-wide, immediately after the scrub. Every case that drives the CLI
# passes `deadbeef` as its `<me>`, which is a prefix of SID, so one export arms
# the identity check for all of them instead of ~110 edits that would drift. The
# handful of cases modelling a PEER session declare that peer's id per call (see
# as_peer). Exported, not assigned, because the CLI is a child process.
export WORKLIST_SESSION_ID="$SID"
PASS=0
FAIL=0

CASES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/worklist-cases"

# shellcheck source=/dev/null
source "$CASES/_harness.sh"

# ORDER IS THE CONTRACT, so the list is explicit rather than a glob: cases
# share $BASE and several later groups call helpers that an earlier group
# defines, exactly as they did when this was one file. Sourcing in a different
# order is a different suite.
CASE_FILES=(
    01-core-blocking.sh
    02-state-document.sh
    03-drift-loops-freshness.sh
    04-stuck-and-blockers.sh
    05-requests.sh
    06-regression-gate.sh
    07-idle-and-evidence.sh
    08-poll-and-waiting.sh
    09-ci-status.sh
    10-event-store.sh
    11-guide-and-deferrals.sh
    12-agent-docs-and-focus.sh
    13-ci-queue-and-mail.sh
    14-background-waits.sh
    15-waiter-controls.sh
    16-triage-and-plans.sh
    17-report-queue.sh
    18-identity.sh
    19-checklists.sh
    20-advisories-rotation.sh
    21-cadence.sh
    22-plan-fidelity.sh
    23-priority-ladder.sh
    24-lineage.sh
    25-first-touch.sh
    26-migrate.sh
)

# A case file that nothing sources is an orphan the same way a test file that
# nothing runs is: it passes when invoked by hand and covers nothing in CI.
# The repo has a gate for the second shape (check_test_file_orphans.py) and it
# cannot see these, because they are sourced fragments rather than runnable
# tests. So the runner checks the set itself, both directions -- a file added
# to the directory and forgotten here, or a name here that no longer exists.
_listed=" ${CASE_FILES[*]} "
_missing=""
for _f in "$CASES"/[0-9]*.sh; do
    _b="$(basename "$_f")"
    [[ "$_listed" == *" $_b "* ]] || _missing="$_missing $_b(on-disk-not-sourced)"
done
for _b in "${CASE_FILES[@]}"; do
    [[ -f "$CASES/$_b" ]] || _missing="$_missing $_b(sourced-but-absent)"
done
if [[ -n "$_missing" ]]; then
    echo "  FAIL: worklist-cases/ and CASE_FILES disagree:$_missing"
    echo "  passed=0 failed=1"
    exit 1
fi
unset _listed _missing _b

for _f in "${CASE_FILES[@]}"; do
    # shellcheck source=/dev/null
    source "$CASES/$_f"
done
unset _f

echo
echo "  passed=$PASS failed=$FAIL"
[[ "$FAIL" -eq 0 ]]

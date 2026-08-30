#!/bin/bash
# ci-trace must be able to read a branch that has NO open PR.
#
# WHAT WENT WRONG, measured 2026-08-25 against Console CI run 32903007256
# (b4b5797e on main), while that run was still in_progress:
#
#     $ .ci/scripts/ci/ci-trace.py --ref main --wait --until-final
#     no-verdict: no open PR for ref 'main'
#
# /pr-merge step 5 instructs exactly that command to watch Console CI on main
# after a merge. wl_ci.ci_rollup only ever asked pullRequests(headRefName:...),
# so a branch with no open PR -- which is precisely what main IS after a merge
# -- had no path through the reader at all.
#
# That mattered more than one broken invocation because ci-trace is the ONLY
# sanctioned reader: block-adhoc-sanctioned.sh refuses hand-rolled gh watch
# loops and block-ci-polling.sh refuses sleep+gh-run-view. The post-merge step
# was left with no sanctioned instrument, which pushes a session toward either
# skipping verification of the release path or evading a guard.
#
# THE THREE THINGS THIS GATE HOLDS, and why each is load-bearing:
#
#   1. allow_branch DEFAULTS TO FALSE. The Stop hook (wl_ci.py, ci_watch_armed)
#      reads `no-pr` as a meaningful answer. If the fallback ever became the
#      default, that check would silently change meaning rather than gain a
#      capability. This is the assertion most likely to be "simplified" away.
#   2. A missing ref answers `no-ref`, NOT `unreadable` and NOT a silent ok with
#      zero contexts. A rollup nobody could read and a rollup with no checks look
#      identical downstream; conflating them is how a typo reads as a clean run.
#   3. The emitted line NAMES its source. A branch read and a PR read answer
#      different questions, and one undifferentiated channel is the exact defect
#      2e2179aa fixed in run.sh -- do not reintroduce it one file over.
#
# HERMETIC: gh is shimmed, so this gate never touches the network. A gate that
# needs GitHub to be up is a gate that gets skipped on somebody else's outage.
#
# WHAT THIS GATE CANNOT SEE: it does not prove the GraphQL field selection is
# still valid against the live schema. A deprecation surfaces at runtime as
# `unreadable`, which at least says so, but this gate will stay green through it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WL_CI="$REPO_ROOT/.claude/hooks/stop/wl_ci.py"
TRACE="$REPO_ROOT/.ci/scripts/ci/ci-trace.py"

for f in "$WL_CI" "$TRACE"; do
    [[ -f "$f" ]] || log_fail "subject under test is missing: $f"
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- a gh that answers the two queries DIFFERENTLY ---------------------------
# with_fake_gh in test-helpers.sh cats one file for every call, which cannot
# distinguish the PR query from the branch query -- and telling them apart is
# the entire subject here.
make_fake_gh() {
    local dir="$1" pr_nodes="$2" ref_json="$3"
    mkdir -p "$dir"
    cat >"$dir/gh" <<FAKE
#!/bin/bash
q="\$*"
case "\$q" in
  *pullRequests*) cat <<'JSON'
{"data":{"repository":{"pullRequests":{"nodes":$pr_nodes}}}}
JSON
  ;;
  *qualifiedName*) cat <<'JSON'
{"data":{"repository":{"ref":$ref_json}}}
JSON
  ;;
  *) echo '{"data":{}}' ;;
esac
FAKE
    chmod +x "$dir/gh"
}

ROLLUP_OK='{"target":{"oid":"b4b5797e00000000000000000000000000000000","statusCheckRollup":{"state":"SUCCESS","contexts":{"totalCount":2,"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"__typename":"CheckRun","name":"Quality","status":"COMPLETED","conclusion":"SUCCESS","databaseId":1,"detailsUrl":"","checkSuite":{"workflowRun":{"databaseId":9}}},{"__typename":"CheckRun","name":"Build","status":"COMPLETED","conclusion":"SUCCESS","databaseId":2,"detailsUrl":"","checkSuite":{"workflowRun":{"databaseId":9}}}]}}}}'

# rollup_state <ref> <allow_branch> [module_dir] -- prints "<state> <source> <sha>"
rollup_state() {
    local ref="$1" allow="$2" moddir="${3:-$REPO_ROOT/.claude/hooks/stop}"
    python3 - "$moddir" "$ref" "$allow" <<'PY'
import sys, pathlib
sys.path.insert(0, sys.argv[1])
import wl_ci
state, info = wl_ci.ci_rollup(pathlib.Path("."), sys.argv[2], allow_branch=(sys.argv[3] == "1"))
if isinstance(info, dict):
    print("%s %s %s" % (state, info.get("source"), (info.get("sha") or "")[:8]))
else:
    print("%s - -" % state)
PY
}

# =============================================================================
test_default_still_answers_no_pr() {
    log_test "the DEFAULT must not silently become a branch read"
    make_fake_gh "$WORK/bin" "[]" "$ROLLUP_OK"
    local out
    out="$(PATH="$WORK/bin:$PATH" rollup_state main 0)"
    assert_eq "no-pr - -" "$out" "default allow_branch must yield no-pr, got: $out"
    log_pass "default is unchanged: no-pr"
}

test_opt_in_reads_the_branch() {
    log_test "allow_branch=True reads the branch rollup"
    make_fake_gh "$WORK/bin" "[]" "$ROLLUP_OK"
    local out
    out="$(PATH="$WORK/bin:$PATH" rollup_state main 1)"
    assert_eq "ok branch b4b5797e" "$out" "opt-in must read the branch, got: $out"
    log_pass "opt-in reads the branch and labels its source"
}

test_missing_ref_is_no_ref_not_silence() {
    log_test "a ref that does not exist must answer no-ref"
    make_fake_gh "$WORK/bin" "[]" "null"
    local out
    out="$(PATH="$WORK/bin:$PATH" rollup_state nope 1)"
    assert_eq "no-ref - -" "$out" "missing ref must be no-ref, got: $out"
    log_pass "missing ref is distinguishable from a branch with no checks"
}

test_control_default_flipped_is_caught() {
    log_test "CONTROL: flip the default and the first assertion must go red"
    # Built by CONSTRUCTION -- a copied module plus an APPENDED override. A
    # pattern substitution could silently no-op if the signature were reworded,
    # and the control would then pass against unmutated source.
    local moddir="$WORK/mutant"
    mkdir -p "$moddir"
    cp "$REPO_ROOT/.claude/hooks/stop/"*.py "$moddir/"
    cat >>"$moddir/wl_ci.py" <<'MUT'


_orig_ci_rollup = ci_rollup


def ci_rollup(root, ref, allow_branch=False):  # noqa: F811
    return _orig_ci_rollup(root, ref, allow_branch=True)
MUT
    grep -q "_orig_ci_rollup" "$moddir/wl_ci.py" ||
        log_fail "control was not planted -- the mutant module is unmodified"

    make_fake_gh "$WORK/bin" "[]" "$ROLLUP_OK"
    local out
    out="$(PATH="$WORK/bin:$PATH" rollup_state main 0 "$moddir")"
    if [[ "$out" == "no-pr - -" ]]; then
        log_fail "control did not fire: mutant still answered no-pr"
    fi
    assert_eq "ok branch b4b5797e" "$out" "mutant should have leaked a branch read, got: $out"
    log_pass "control fires: a flipped default is detectable"
}

test_trace_names_its_source() {
    log_test "the emitted line must name which source answered"
    grep -q 'branch %s @ %s (no PR)' "$TRACE" ||
        log_fail "ci-trace.py no longer distinguishes a branch read in its output"
    grep -q 'allow_branch = bool(args.ref)' "$TRACE" ||
        log_fail "ci-trace.py no longer restricts the fallback to an EXPLICIT --ref"
    log_pass "output distinguishes source; fallback stays opt-in"
}

test_every_caller_handles_the_no_pr_state() {
    log_test "EVERY ci_rollup caller must handle no-pr, not let it propagate"
    # The other assertions here test the two callers that exist TODAY. This one
    # is about the caller nobody has written yet: ci_rollup returns a STATE, and
    # a caller that ignores it hands `info` -- which is a plain string, not the
    # payload dict -- to code expecting a rollup. That is the defect this whole
    # gate exists for, one level up.
    #
    # Enumerated, never hardcoded, and from BOTH tracked and untracked files: a
    # caller added but not yet committed is exactly when this slips in.
    local callers=() f
    while IFS= read -r f; do
        [[ -n "$f" && -f "$REPO_ROOT/$f" ]] || continue
        grep -q "ci_rollup(" "$REPO_ROOT/$f" || continue
        # A DEFINITION IS NOT A CALLER. Skipping by filename would need a new
        # hardcoded entry per stub; skipping by shape is self-maintaining and
        # correct. Caught live: worklist-cases/09-ci-status.sh defines a test
        # STUB named ci_rollup and calls nothing -- demanding it handle a state
        # it invents would be the same shape-vs-substance error this branch
        # already hit twice in its detectors.
        grep -qE '\bdef ci_rollup|^[[:space:]]*ci_rollup\(\)[[:space:]]*\{' "$REPO_ROOT/$f" && continue
        # This gate's own fixtures call it deliberately without the state.
        [[ "$f" == ".ci/scripts/test/gates/test-ci-trace-branch.sh" ]] && continue
        callers+=("$f")
    done < <(
        {
            git -C "$REPO_ROOT" ls-files '*.py' '*.sh' 2>/dev/null
            git -C "$REPO_ROOT" ls-files --others --exclude-standard '*.py' '*.sh' 2>/dev/null
        } | sort -u
    )

    # Anti-vacuity: a scan that found no callers proves nothing. ci-trace.py is
    # a caller by construction, so zero means the enumeration broke.
    [[ ${#callers[@]} -ge 1 ]] ||
        log_fail "found ZERO ci_rollup callers -- the enumeration broke, not the code"

    local bad=()
    for f in "${callers[@]}"; do
        grep -q "no-pr" "$REPO_ROOT/$f" || bad+=("$f")
    done
    [[ ${#bad[@]} -eq 0 ]] ||
        log_fail "these call ci_rollup but never handle its no-pr state: ${bad[*]}"
    log_pass "all ${#callers[@]} external caller(s) handle no-pr"
}

test_control_a_blind_caller_is_detected() {
    log_test "CONTROL: a caller that ignores the state must be caught"
    # By construction: a fresh file that calls ci_rollup and never mentions
    # no-pr.
    #
    # WRITTEN TO $WORK, NOT THE REAL TREE. The first version put it under
    # .ci/scripts/quality/ so the untracked half of the enumeration would be
    # exercised for real; check-pool-writer-safety correctly rejected that. A
    # test that writes into the tree while run-all.sh schedules it in the
    # PARALLEL pool corrupts a concurrent reader, and it does not fail cleanly:
    # it surfaces as an unrelated gate going red in a file that parses fine on
    # the serial re-run. Registering it in WRITER_TESTS would also have worked,
    # but the write buys nothing here -- what this control proves is the
    # PREDICATE, and the untracked path is asserted separately below.
    local victim="$WORK/_probe_caller.py"
    printf 'state, info = wl_ci.ci_rollup(root, ref)\nprint(info["verdict"])\n' >"$victim"
    local hit=0
    grep -q "ci_rollup(" "$victim" && ! grep -q "no-pr" "$victim" && hit=1
    rm -f "$victim"
    [[ "$hit" -eq 1 ]] ||
        log_fail "CONTROL DID NOT FIRE: a blind caller read as compliant"

    # The untracked half of the enumeration, asserted at the source rather than
    # by writing into the tree. Stated as a limitation, not hidden: this proves
    # the enumeration ASKS for untracked files, not that it received any.
    grep -q 'ls-files --others --exclude-standard' "$0" ||
        log_fail "the caller enumeration no longer covers UNTRACKED files, which is when a new caller slips in"
    log_pass "control: a blind caller is detectable; untracked coverage asserted at source"
}

test_green_draft_names_the_finish_sequence() {
    log_test "GREEN on a still-draft PR must name the finish sequence"
    # Green is not the finish line: the PR still has to be flipped ready,
    # reviewed, and its threads resolved. That step depended on the agent
    # REMEMBERING it, and agents forget -- the loop reports green, the turn
    # ends, and the PR sits in draft with every check passing. This watch exits
    # exactly when green lands and re-invokes the agent with its output in hand,
    # so it is the one place the reminder cannot be missed.
    #
    # Driven through the REAL _emit in four directions rather than grepping the
    # source for the string: a nudge that never renders is the failure here.
    python3 - "$TRACE" <<'NUDGEPY' || log_fail "the green+draft nudge did not behave in all four directions"
import contextlib
import importlib.util
import io
import sys

spec = importlib.util.spec_from_file_location("t", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
base = {
    "verdict": "green", "detail": "d", "ref": "b", "source": "pr", "owner": "o",
    "name": "n", "head": "abc", "live": False, "waiting": 0, "failing": [],
    "soft": [], "cancelled": [], "truncated": False,
}


def emit(**kw):
    p = dict(base)
    p.update(kw)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m._emit(p, False)
    return "still a DRAFT" in buf.getvalue()


cases = [
    (dict(pr=1, draft=True), True),                        # the case it exists for
    (dict(pr=1, draft=False), False),                      # already flipped ready
    (dict(pr=None, draft=False, source="branch"), False),  # branch read, no PR at all
    (dict(pr=1, draft=True, verdict="red"), False),        # red is not the finish line
]
sys.exit(0 if all(emit(**k) == w for k, w in cases) else 1)
NUDGEPY
    log_pass "green+draft names the next command; ready, branch and red stay quiet"
}

test_default_signature_is_false() {
    log_test "the signature default itself must remain False"
    grep -q 'def ci_rollup(root, ref, allow_branch=False):' "$WL_CI" ||
        log_fail "ci_rollup's allow_branch default is no longer False"
    log_pass "signature default is False"
}

test_dispatched_run_is_traced_by_id() {
    log_test "--run reads a dispatched run, which a branch rollup CANNOT see"
    # WHY THIS EXISTS, measured 2026-08-26 on Release run 32968110599 (head
    # 1c006e53). A branch's statusCheckRollup does NOT contain a
    # workflow_dispatch run's check runs: the REST check-runs API for that exact
    # commit showed `in_progress  Tag & Release`, while the GraphQL rollup for
    # refs/heads/main returned 81 contexts, state SUCCESS, NONE in flight. So
    # `--wait --ref main` printed GREEN and exited 0 while the release was
    # mid-flight -- twice, including with --until-final -- and /pr-merge step 5
    # instructed exactly that. A release could be certified without having run.
    #
    # The three exit codes below are the whole contract. `in_progress -> 2` is
    # the one that was broken; `unreadable -> 2` matters just as much, because a
    # run nobody could read must never read as a pass.
    local shim="$WORK/runshim"
    mkdir -p "$shim"
    cat >"$shim/gh" <<'FAKE'
#!/bin/bash
case "$*" in
  *999999*) echo "failed to get run: HTTP 404: Not Found" >&2; exit 1 ;;
  *inflight*) echo '{"status":"in_progress","conclusion":null,"jobs":[{"name":"Tag & Release","conclusion":null}]}' ;;
  *redrun*)  echo '{"status":"completed","conclusion":"failure","jobs":[{"name":"Publish","conclusion":"failure"}]}' ;;
  *)         echo '{"status":"completed","conclusion":"success","jobs":[{"name":"Tag & Release","conclusion":"success"}]}' ;;
esac
FAKE
    chmod +x "$shim/gh"

    local rc
    PATH="$shim:$PATH" "$TRACE" --run inflight >/dev/null 2>&1 && rc=0 || rc=$?
    [[ "$rc" -eq 2 ]] ||
        log_fail "an IN-FLIGHT dispatched run must exit 2, got $rc (this is the false-green that shipped a release watch)"

    PATH="$shim:$PATH" "$TRACE" --run okrun >/dev/null 2>&1 && rc=0 || rc=$?
    [[ "$rc" -eq 0 ]] ||
        log_fail "a completed/success run must exit 0, got $rc"

    PATH="$shim:$PATH" "$TRACE" --run redrun >/dev/null 2>&1 && rc=0 || rc=$?
    [[ "$rc" -eq 1 ]] ||
        log_fail "a run with a failed job must exit 1, got $rc"

    PATH="$shim:$PATH" "$TRACE" --run 999999 >/dev/null 2>&1 && rc=0 || rc=$?
    [[ "$rc" -eq 2 ]] ||
        log_fail "an UNREADABLE run must exit 2, never 0, got $rc"

    log_pass "--run: in-flight=2, success=0, failed-job=1, unreadable=2"
}

test_control_run_reader_can_fail() {
    log_test "CONTROL: a --run reader that ignores status must be detectable"
    # Built BY CONSTRUCTION, not by sed over the live source: copy ci-trace,
    # replace the status test so `in_progress` falls through to the green path,
    # and require the in-flight case to flip to 0. If it does not flip, the
    # assertion above is decoration.
    local mut="$WORK/ci-trace-mut.py"
    python3 - "$TRACE" "$mut" <<'PY'
import io, sys
src, dst = sys.argv[1], sys.argv[2]
s = io.open(src, encoding="utf-8").read()
needle = 'if status == "completed":'
assert s.count(needle) == 1, "mutation anchor missing or ambiguous"
io.open(dst, "w", encoding="utf-8").write(s.replace(needle, "if True:", 1))
PY
    chmod +x "$mut"
    local rc
    PATH="$WORK/runshim:$PATH" python3 "$mut" --run inflight >/dev/null 2>&1 && rc=0 || rc=$?
    # The assertion is `!= 2`, not `== 0`, and the difference is the control
    # being honest. Deleting the status test does NOT make the in-flight run
    # green: it falls through to the terminal branch, where conclusion is null,
    # which is not in (success, skipped), so it reports RED (1). Either way the
    # run has stopped being reported as in-flight, which is the property under
    # test. An `== 0` control failed here for exactly this reason -- it was
    # asserting a specific wrong answer instead of the absence of the right one.
    [[ "$rc" -ne 2 ]] ||
        log_fail "CONTROL DID NOT FIRE: the mutated reader still reported the in-flight run as in-flight (rc=$rc), so the real assertion proves nothing"
    log_pass "control fires: without the status test, in-flight stops being reported (rc=$rc, not 2)"
}

test_ci_nonblocking_contexts_selftest() {
    log_test "ci-trace.py's own CI_NONBLOCKING_CONTEXTS fixture controls"
    # Review-found live on PR #579: --run reads a run's jobs endpoint DIRECTLY
    # (see test_dispatched_run_is_traced_by_id above), a completely separate
    # path from wl_ci.ci_classify's GraphQL contexts, so the fix landed on the
    # branch-tracing path and never touched this one -- proven by ci-trace.py
    # itself calling a run GitHub scored "success" RED, because "Review
    # Complete" (a check-run whose own summary says it can never block Console
    # CI) showed up as conclusion=failure in --run's jobs list. --selftest
    # unit-tests _trace_run's filter directly against fixtures shaped like
    # that real defect.
    python3 "$TRACE" --selftest || log_fail "ci-trace.py --selftest failed"
    log_pass "ci-trace.py --selftest: 3/3"
}

test_default_still_answers_no_pr
test_opt_in_reads_the_branch
test_dispatched_run_is_traced_by_id
test_control_run_reader_can_fail
test_missing_ref_is_no_ref_not_silence
test_control_default_flipped_is_caught
test_trace_names_its_source
test_default_signature_is_false
test_green_draft_names_the_finish_sequence
test_every_caller_handles_the_no_pr_state
test_control_a_blind_caller_is_detected
test_ci_nonblocking_contexts_selftest

echo
log_pass "ci-trace branch-read gate: 12/12"
echo "  Blind spot: does not validate the GraphQL selection against the live schema,"
echo "  and the --run cases are shimmed, so they do not prove the gh JSON field"
echo "  names are still current -- a rename surfaces as exit 2, which at least says so."

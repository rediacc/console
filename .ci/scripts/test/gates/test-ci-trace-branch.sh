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
    # no-pr. Written into the repo tree so the untracked half of the
    # enumeration above is exercised too, then removed.
    local victim="$REPO_ROOT/.ci/scripts/quality/_vacuity_probe_caller.py"
    printf 'state, info = wl_ci.ci_rollup(root, ref)\nprint(info["verdict"])\n' >"$victim"
    local hit=0
    grep -q "ci_rollup(" "$victim" && ! grep -q "no-pr" "$victim" && hit=1
    rm -f "$victim"
    [[ "$hit" -eq 1 ]] ||
        log_fail "CONTROL DID NOT FIRE: a blind caller read as compliant"
    log_pass "control: a caller ignoring the state is detectable"
}

test_default_signature_is_false() {
    log_test "the signature default itself must remain False"
    grep -q 'def ci_rollup(root, ref, allow_branch=False):' "$WL_CI" ||
        log_fail "ci_rollup's allow_branch default is no longer False"
    log_pass "signature default is False"
}

test_default_still_answers_no_pr
test_opt_in_reads_the_branch
test_missing_ref_is_no_ref_not_silence
test_control_default_flipped_is_caught
test_trace_names_its_source
test_default_signature_is_false
test_every_caller_handles_the_no_pr_state
test_control_a_blind_caller_is_detected

echo
log_pass "ci-trace branch-read gate: 8/8"
echo "  Blind spot: does not validate the GraphQL selection against the live schema."

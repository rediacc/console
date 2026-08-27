#!/bin/bash
# Both-ways test for .ci/scripts/quality/check-swallowed-failures.sh.
#
# THE DEFECT IT POLICES. A gate captures a probe, throws away the probe's exit
# status and its stderr, and reads the captured value. A failed probe yields
# empty, empty is byte-identical to "nothing to report", and the gate prints its
# success message. The live specimen is the pre-fix probe in check-go-deps.sh,
# recovered here from git history rather than paraphrased, so this file tests
# against the bytes that actually shipped.
#
# WHY THE TWO HISTORICAL CASES ARE THE CENTRE OF THIS FILE. A lint of this shape
# is only worth having if it fires on the real defect and stays quiet on the
# real fix. Everything else here is calibration: each remaining case pins one
# exemption, and an exemption that cannot be shown to be load-bearing is just an
# untested branch.
#
# CALIBRATION IS PART OF THE CONTRACT. test_real_tree_is_clean pins the count on
# the live tree at ZERO. The gate opened at 16 findings; all 16 were fixed, none
# waived. Pinning zero is what stops the class regrowing one call site at a time,
# which is how it reached 16 in the first place.
#
# Fixtures are written under a temp dir and driven through the gate's
# SWALLOWED_SCAN_ROOT / SWALLOWED_SCAN_DIRS seams, so no tracked file is ever
# mutated.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check-swallowed-failures.sh"
GO_DEPS="$REPO_ROOT/.ci/scripts/quality/check-go-deps.sh"

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

SCAN="$FIXTURE/tree/.ci/scripts/probe"

LAST_RC=0
LAST_OUT=""

# write_case <basename> <body...>  -- one fixture script per case
write_case() {
    local name="$1"
    shift
    mkdir -p "$SCAN"
    {
        echo "#!/bin/bash"
        echo "set -euo pipefail"
        printf '%s\n' "$@"
    } >"$SCAN/$name.sh"
}

reset_tree() {
    rm -rf "$FIXTURE/tree"
    mkdir -p "$SCAN"
}

# run_gate [scan-dirs] -- sets LAST_RC and LAST_OUT.
#
# Not called inside $(...): a subshell would strand both variables and every
# assert_contains below would silently compare against an empty string.
run_gate() {
    local dirs="${1:-.ci/scripts/probe}"
    LAST_RC=0
    LAST_OUT="$(SWALLOWED_SCAN_ROOT="$FIXTURE/tree" SWALLOWED_SCAN_DIRS="$dirs" \
        bash "$GATE" 2>&1)" || LAST_RC=$?
}

# ---------------------------------------------------------------------------
# The two historical cases. These are the reason the file exists.
# ---------------------------------------------------------------------------

test_fires_on_the_prefix_go_deps_probe() {
    # THE CONTROL. Byte-for-byte the probe that shipped before 2026-07-28,
    # recovered with `git show <commit>^:.ci/scripts/quality/check-go-deps.sh`.
    # It spans three physical lines with 2>/dev/null on the first and || true on
    # the third, which is why a line-based scanner cannot see it at all.
    reset_tree
    write_case prefix-go-deps \
        '    local outdated' \
        '    outdated=$(go list -u -m -json all 2>/dev/null |' \
        "        jq -rs '.[] | select((.Indirect != true) and (.Update != null))" \
        '                | "\(.Path) \(.Version)"'"'"" 2>/dev/null || true)" \
        '    while IFS=" " read -r path current latest uptime; do' \
        '        [[ -z "$path" ]] && continue' \
        '        echo "$path $current $latest minor"' \
        '    done <<<"$outdated"' \
        '    echo "All Go direct dependencies are up-to-date"'
    run_gate
    assert_eq "$LAST_RC" "1" "the pre-fix go-deps probe must FIRE: $LAST_OUT"
    assert_contains "$LAST_OUT" "outdated" "the finding must name the swallowed variable"
    assert_contains "$LAST_OUT" "no test distinguishes" "with the no-downstream-test reason"
    log_pass "fires on the historical pre-fix check-go-deps probe (multi-line shape included)"
}

test_silent_on_the_fixed_go_deps_probe() {
    # The other half of the control, run against the REAL current file rather
    # than a copy of it. The remediated probe captures the status into
    # `status=$?`, keeps stderr in a file, and reports __PROBE_FAILED__ when the
    # module list is empty. None of that may read as a swallowed failure, or the
    # gate punishes the fix it is supposed to reward.
    local rc=0 out
    out="$(SWALLOWED_SCAN_ROOT="$REPO_ROOT" SWALLOWED_SCAN_DIRS=".ci/scripts/quality" \
        bash "$GATE" 2>&1)" || rc=$?
    assert_not_contains "$out" '$raw' "the fixed probe's captured output must not be flagged"
    assert_not_contains "$out" '$seen' "the fixed probe's emptiness guard must not be flagged"
    # Anti-vacuity for this case: the two assertions above are absences, and an
    # absence is also what a deleted file produces. Confirm the remediated probe
    # is still there to be silent about.
    local markers
    markers="$(grep -c 'PROBE_FAILED' "$GO_DEPS")"
    if ((markers < 3)); then
        log_fail "check-go-deps.sh carries only $markers __PROBE_FAILED__ marker(s); the fix this case asserts silence about is gone"
    fi
    log_pass "stays silent on the remediated check-go-deps probe (real file, not a copy)"
}

# ---------------------------------------------------------------------------
# The trigger, one shape at a time.
# ---------------------------------------------------------------------------

test_clean_file_passes() {
    # Baseline. Without it, every silence below could be silence for the wrong
    # reason (a scanner that matches nothing at all).
    reset_tree
    write_case clean \
        'err=$(mktemp)' \
        'raw=$(some-probe 2>"$err") || status=$?' \
        'if ((status != 0)); then log_error "probe failed"; exit 1; fi' \
        'echo "$raw"'
    run_gate
    assert_eq "$LAST_RC" "0" "a properly guarded probe must pass: $LAST_OUT"
    assert_contains "$LAST_OUT" "no gate captures a probe" "and say so"
    log_pass "a capture that keeps its exit status and stderr passes"
}

test_capture_with_bare_or_true_fires() {
    reset_tree
    write_case bare-or-true 'data=$(some-probe --json 2>/dev/null || true)' 'echo "done: $data"'
    run_gate
    assert_eq "$LAST_RC" "1" "an unexamined || true capture must fire"
    assert_contains "$LAST_OUT" "data" "naming the variable"
    log_pass "a capture ending in || true with no downstream test fires"
}

test_quoted_capture_fires() {
    # The recall bug found during calibration: NAME="$(...)" is the commonest
    # spelling in this repo, and the first pattern only matched NAME=$(...).
    # Every quoted capture was invisible, including all five in
    # dependency-inventory.sh.
    reset_tree
    write_case quoted 'tree_all="$(npm ls --all --json 2>/dev/null || true)"' 'echo "$tree_all"'
    run_gate
    assert_eq "$LAST_RC" "1" "a QUOTED capture must fire too"
    assert_contains "$LAST_OUT" "tree_all" "naming the variable"
    log_pass "a quoted capture fires (the shape that was invisible at first)"
}

test_empty_case_that_exits_zero_fires() {
    # The subtlest true positive, and the shape check-review-comments.sh and
    # check-branch.sh BOTH carried before they were repaired: the author DID
    # test for empty, and then treated empty as a pass. Both now fail closed
    # (see the repairs pinned in test_the_repaired_sites_stay_repaired), so this
    # fixture is the only place the shape still lives -- which is exactly why it
    # is pinned here rather than left to be rediscovered in the wild.
    reset_tree
    write_case exits-zero \
        'COMMENTS=$(gh api "repos/x/pulls/1/comments" 2>/dev/null || echo "[]")' \
        'if [[ "$COMMENTS" == "[]" ]]; then' \
        '    echo "No review comments found - OK"' \
        '    exit 0' \
        'fi'
    run_gate
    assert_eq "$LAST_RC" "1" "a tested-but-passed empty case must fire"
    assert_contains "$LAST_OUT" "the empty case exits successfully" "with the de-escalation reason"
    log_pass "an emptiness test whose branch exits 0 fires"
}

test_multiline_continuation_is_joined() {
    # Proves the logical-line folding independently of the go-deps case: the
    # capture and its || true are three physical lines apart.
    reset_tree
    write_case joined \
        'edges=$(go mod graph \' \
        '    --some-flag \' \
        '    2>/dev/null || true)' \
        'echo "$edges" | awk "{print}"'
    run_gate
    assert_eq "$LAST_RC" "1" "a backslash-continued capture must fire"
    assert_contains "$LAST_OUT" "edges" "naming the variable"
    log_pass "backslash continuations are folded before matching"
}

# ---------------------------------------------------------------------------
# The exemptions. Each one must be shown to be load-bearing.
# ---------------------------------------------------------------------------

test_distinguishable_sentinel_is_silent() {
    reset_tree
    write_case sentinel \
        'STATUS=$(docker inspect x --format "{{.State.Status}}" 2>/dev/null || echo "missing")' \
        'echo "$STATUS"'
    run_gate
    assert_eq "$LAST_RC" "0" "a fallback to a real sentinel must not fire: $LAST_OUT"
    log_pass "a distinguishable sentinel (|| echo missing) is not a swallowed failure"
}

test_stderr_folded_in_is_silent() {
    reset_tree
    write_case stderr-in 'output=$("$binary" --version 2>&1 || true)' 'echo "$output"'
    run_gate
    assert_eq "$LAST_RC" "0" "2>&1 keeps the failure in the value, so it must not fire: $LAST_OUT"
    log_pass "a capture that folds stderr into the value is not flagged"
}

test_answer_is_exit_commands_are_silent() {
    # grep and command -v exit non-zero to MEAN "not found". Flagging them cost
    # 8 false positives on the real tree during calibration.
    reset_tree
    write_case answer-is-exit \
        'matches=$(grep -n "pattern" "$file" 2>/dev/null || true)' \
        'found=$(command -v shfmt 2>/dev/null || true)' \
        'echo "$matches $found"'
    run_gate
    assert_eq "$LAST_RC" "0" "grep and command -v must not fire: $LAST_OUT"
    log_pass "commands whose non-zero exit is the answer are exempt"
}

test_bare_command_without_capture_is_silent() {
    # Best-effort cleanup is none of this gate's business, and it is by far the
    # most common `|| true` in the repo. Flagging it is how this class of lint
    # becomes a wall of noise.
    reset_tree
    write_case cleanup \
        'rm -f /tmp/whatever 2>/dev/null || true' \
        'docker rm "$cid" >/dev/null 2>&1 || true' \
        'aws s3 rm "s3://b/k" --quiet 2>/dev/null || true'
    run_gate
    assert_eq "$LAST_RC" "0" "bare best-effort commands must not fire: $LAST_OUT"
    log_pass "an uncaptured || true (cleanup) is not flagged"
}

test_reported_empty_case_is_silent() {
    reset_tree
    write_case reported \
        'seen=$(printf "%s" "$raw" | jq -rs "length" 2>/dev/null || echo 0)' \
        'if [[ "$seen" -eq 0 ]]; then' \
        '    log_error "probe returned no modules at all"' \
        '    return 1' \
        'fi'
    run_gate
    assert_eq "$LAST_RC" "0" "an escalated empty case must not fire: $LAST_OUT"
    log_pass "an emptiness test that reports the problem is not flagged"
}

test_escalation_in_the_next_function_does_not_count() {
    # Found during calibration: the lookahead window ran past the closing brace,
    # so a log_error in the NEXT function counted as handling for this one. That
    # silently cleared r2_count_objects in lib/common.sh, which is a genuine
    # finding AND the helper the sibling gate recommends as a remedy.
    reset_tree
    write_case boundary \
        'count_things() {' \
        '    local count' \
        '    count="$(aws s3api list-objects-v2 --query x --output text 2>/dev/null || echo 0)"' \
        '    if ! [[ "$count" =~ ^[0-9]+$ ]]; then' \
        '        count=0' \
        '    fi' \
        '    printf "%s\n" "$count"' \
        '}' \
        '' \
        'other_function() {' \
        '    log_error "this must not count as handling for count_things"' \
        '    exit 1' \
        '}'
    run_gate
    assert_eq "$LAST_RC" "1" "an escalation past the function boundary must not exempt the capture"
    assert_contains "$LAST_OUT" "count" "naming the variable"
    log_pass "the lookahead window stops at the enclosing function boundary"
}

# ---------------------------------------------------------------------------
# The waiver, held to the BLOCKER bar.
# ---------------------------------------------------------------------------

test_waiver_suppresses() {
    reset_tree
    write_case waived \
        '# swallowed-failure-ok: an absent optional cache file and an unreadable one are the same event for this probe, and both mean rebuild' \
        'cached=$(cat "$cache" 2>/dev/null || true)' \
        'echo "$cached"'
    run_gate
    assert_eq "$LAST_RC" "0" "a properly reasoned waiver must suppress the finding: $LAST_OUT"
    assert_contains "$LAST_OUT" "1 waived" "and be counted in the summary"
    log_pass "a waiver with a substantive reason suppresses the finding"
}

test_low_effort_waiver_is_rejected() {
    # PROVE THE INSTRUMENT. The header claims the waiver is held to the BLOCKER
    # bar. Without this case that claim could be decorative and nothing would
    # say so.
    reset_tree
    write_case bad-waiver \
        '# swallowed-failure-ok: tbd' \
        'cached=$(cat "$cache" 2>/dev/null || true)' \
        'echo "$cached"'
    run_gate
    assert_eq "$LAST_RC" "1" "a banned-phrase waiver must be rejected"
    assert_contains "$LAST_OUT" "low-effort placeholder" "with the shared validator's own diagnostic"
    log_pass "a low-effort waiver reason is rejected by the shared BLOCKER validator"
}

test_waiver_must_be_adjacent() {
    # A waiver that drifts away from its line starts excusing whatever moved
    # underneath it, which nobody re-reads.
    reset_tree
    write_case drifted-waiver \
        '# swallowed-failure-ok: an absent optional cache file and an unreadable one are the same event here, both meaning rebuild' \
        '' \
        '# an unrelated comment that separates the waiver from the line' \
        'cached=$(cat "$cache" 2>/dev/null || true)' \
        'echo "$cached"'
    run_gate
    assert_eq "$LAST_RC" "1" "a non-adjacent waiver must not suppress"
    assert_contains "$LAST_OUT" "cached" "the finding is still reported"
    log_pass "a waiver separated from its line no longer excuses it"
}

# ---------------------------------------------------------------------------
# The gate must not become the thing it polices.
# ---------------------------------------------------------------------------

test_empty_scope_is_blind_not_clean() {
    # Anti-vacuity. A gate that scans zero files reports clean forever. This is
    # the property the repo's test-gate-anti-vacuity.sh harness checks for other
    # validators; that harness cannot check this one, because its fixture COPIES
    # .ci/scripts into the empty tree, so this gate always has input there. The
    # seam makes the same property testable directly.
    reset_tree
    run_gate ".ci/scripts/does-not-exist"
    assert_eq "$LAST_RC" "1" "an empty scan scope must fail, not report clean"
    assert_contains "$LAST_OUT" "scanned nothing" "and say it scanned nothing"
    assert_not_contains "$LAST_OUT" "no gate captures a probe" "it must NOT claim a clean result"
    log_pass "an empty scan scope reports blindness instead of success"
}

test_dead_scanner_is_not_a_clean_scan() {
    # THE GATE'S OWN FIRST BUG, pinned. Its awk program died on all 42 files
    # (backslash escapes are consumed when awk assigns a -v value, so every
    # regex became "Unmatched ("), and it printed "OK: no gate captures a
    # probe..." and exited 0. The empty output of a dead scanner is identical to
    # the empty output of a clean file, which is precisely the defect this gate
    # exists to police.
    reset_tree
    write_case unreadable 'x=1'
    chmod 000 "$SCAN/unreadable.sh"
    run_gate
    chmod 644 "$SCAN/unreadable.sh"
    assert_eq "$LAST_RC" "1" "a file the scanner cannot read must fail the run"
    assert_contains "$LAST_OUT" "Refusing to report a verdict" "rather than reading as clean"
    log_pass "a scanner that cannot read its input refuses to report a verdict"
}

# ---------------------------------------------------------------------------
# The live tree.
# ---------------------------------------------------------------------------

test_real_tree_is_clean() {
    # THE RATCHET. This started at 16 findings, all triaged by hand: 14 gates
    # that could pass vacuously when their probe failed, and 2 that failed safe.
    # All 16 were fixed rather than waived, so the live count is now ZERO and
    # stays that way.
    #
    # Zero is the only bound worth pinning here. A range would let the class
    # regrow one call site at a time, which is exactly how it reached 16: nobody
    # was counting. If this case fails, a new capture is throwing away a probe
    # failure. Fix it or waive it with a real reason, and do not relax this
    # assertion to make the failure go away.
    local rc=0 out count
    out="$(cd "$REPO_ROOT" && bash "$GATE" 2>&1)" || rc=$?
    count="$(printf '%s\n' "$out" | grep -cE '^.*\.sh:[0-9]+: \$' || true)"
    if ((rc != 0)); then
        printf '%s\n' "$out" >&2
        log_fail "the live tree regrew $count swallowed-failure finding(s); see the output above"
    fi
    assert_eq "$count" "0" "no capture may discard a probe failure on the live tree"
    assert_contains "$out" "no gate captures a probe" "and the gate must say so explicitly"
    log_pass "the live tree is clean: 0 swallowed-failure findings across the gate scripts"
}

test_the_repaired_sites_stay_repaired() {
    # Anti-vacuity for the case above: "0 findings" is also what a gate that
    # stopped scanning would report. Assert that the specific repairs are still
    # present in the real files, so a regression shows up as a failure here
    # rather than as a suspiciously quiet clean run.
    # grep -q rather than assert_contains: these needles are searched in whole
    # files, and a failing assert_contains would dump the entire file into the
    # test output, burying the one line that matters.
    local q="$REPO_ROOT/.ci/scripts/quality" l="$REPO_ROOT/.ci/scripts/lib"
    # <file>|<needle>|<what it proves>
    local repairs=(
        "$q/check-review-comments.sh|gh_json|the review-comment gate fetches through the status-checking helper"
        "$q/check-resolved-threads.sh|Failing closed|the resolved-threads gate fails closed on an unreadable API"
        "$q/check-claude-attribution.sh|probe_failed|the attribution gate fails closed on an unreadable API"
        "$q/check-branch.sh|must not be reported as up-to-date|check-branch refuses to guess when rev-list fails"
        "$q/check-no-otlp-creds.sh|cannot inspect for baked credentials|the OTLP gate errors when it cannot read a binary"
        "$q/check-submodule-branches.sh|refusing to report zero unreplied|the submodule gate refuses to fabricate a zero"
        "$REPO_ROOT/.ci/scripts/security/dependency-inventory.sh|refusing to emit an empty dependency graph|the SBOM refuses to ship an empty graph"
        "$l/common.sh|r2_count_objects: list-objects-v2 failed|r2_count_objects reports an unreachable bucket"
        "$l/release-state-validator.sh|THREE STATES, DELIBERATELY|the release-state validator separates empty from unanswerable"
    )
    local entry file needle what
    for entry in "${repairs[@]}"; do
        file="${entry%%|*}"
        needle="${entry#*|}"
        what="${needle#*|}"
        needle="${needle%%|*}"
        [[ -f "$file" ]] || log_fail "$file is gone; the repair it carried cannot be verified"
        grep -qF -- "$needle" "$file" ||
            log_fail "$(basename "$file") lost its fix: $what"
    done
    log_pass "all ${#repairs[@]} repaired sites still carry their fix"
}

test_scope_is_gates_only() {
    # The scope is the justification for the whole design: only a gate can turn
    # a swallowed failure into a false GREEN that lets a merge through. If the
    # default scope silently widened to the whole repo, the false-positive
    # budget calibrated above would be meaningless.
    local body
    body="$(grep -n 'DEFAULT_SCAN_DIRS=' "$GATE")"
    assert_contains "$body" ".ci/scripts/quality" "quality gates are in scope"
    assert_contains "$body" ".ci/scripts/security" "security gates are in scope"
    assert_contains "$body" ".ci/scripts/lib" "the helpers gates call are in scope"
    assert_not_contains "$body" ".ci/scripts/deploy" "deploy scripts are deliberately out of scope"
    log_pass "the default scope is gates and their helpers, nothing wider"
}

log_test "test-swallowed-failures"
test_fires_on_the_prefix_go_deps_probe
test_silent_on_the_fixed_go_deps_probe
test_clean_file_passes
test_capture_with_bare_or_true_fires
test_quoted_capture_fires
test_empty_case_that_exits_zero_fires
test_multiline_continuation_is_joined
test_distinguishable_sentinel_is_silent
test_stderr_folded_in_is_silent
test_answer_is_exit_commands_are_silent
test_bare_command_without_capture_is_silent
test_reported_empty_case_is_silent
test_escalation_in_the_next_function_does_not_count
test_waiver_suppresses
test_low_effort_waiver_is_rejected
test_waiver_must_be_adjacent
test_empty_scope_is_blind_not_clean
test_dead_scanner_is_not_a_clean_scan
test_real_tree_is_clean
test_the_repaired_sites_stay_repaired
test_scope_is_gates_only
echo ""
log_pass "all tests passed"

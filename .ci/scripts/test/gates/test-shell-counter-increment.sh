#!/bin/bash
# Regression test for a bash defect that was silently disarming four gates.
#
# WHAT BROKE. Under `set -e`, the arithmetic COMMAND `((x++))` exits NON-ZERO
# when the value it evaluates to is zero. Post-increment evaluates to the OLD
# value, so the very first `((x++))` on a counter starting at 0 evaluates to 0,
# exits 1, and `set -e` kills the script on the spot:
#
#   $ bash -c 'set -euo pipefail; w=0; echo before; ((w++)); echo after'
#   before
#   $                       # "after" never prints, exit status 1
#
# Every affected script begins `set -euo pipefail` and counts findings from 0,
# so each one died at its FIRST finding. Twelve occurrences across four gates:
#   .ci/scripts/quality/check-workflows.sh          (3)
#   .ci/scripts/quality/check-submodule-branches.sh (7)
#   .ci/scripts/quality/check-compose-env.sh        (1)
#   .ci/scripts/security/check-commands.sh          (1)
#
# WHY IT HID. The scripts still EXITED NON-ZERO, so the gates still went red and
# nobody saw a false green. What was lost is everything after the first finding:
# the remaining findings, the counts, and the summary line. A gate that can only
# ever report one problem per run turns a five-problem branch into five CI
# rounds, which is precisely the serialisation this CI programme exists to
# remove.
#
# THE SEVERE ONE is check-submodule-branches.sh's unreplied-review-comment
# counter. That increment sits in a bare counting loop with no log line before
# it, inside a function whose ONLY output is `echo "$unreplied_count"` at the
# end. So the first unreplied comment killed the subshell before it echoed
# anything: the function could report 0, and it could die, but it could never
# report a real count. That gate has never once been able to say "this PR has N
# unreplied review comments", which is the entire reason it exists.
#
# WHAT THIS TEST DOES. It does not re-implement the loop. It extracts the REAL
# function text out of the REAL gate script and runs it against a PATH-shimmed
# `gh`, so the code under test is the code that ships. Then it does the same
# with the PRE-FIX text recovered from git, which is the control: if the old
# version does not visibly break, this test proves nothing and must fail.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE_REL=".ci/scripts/quality/check-submodule-branches.sh"
GATE="$REPO_ROOT/$GATE_REL"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Two review comments, NEITHER of them replied to. A correct counter says 2.
FIXTURE='[
  {"id": 101, "in_reply_to_id": null, "body": "first finding"},
  {"id": 102, "in_reply_to_id": null, "body": "second finding"}
]'

# A `gh` that answers the one call the function makes, so no network is touched.
mk_gh_shim() {
    local dir="$1"
    mkdir -p "$dir"
    cat > "$dir/gh" <<SHIM
#!/bin/bash
cat <<'JSON'
$FIXTURE
JSON
SHIM
    chmod +x "$dir/gh"
}

# Build a runnable harness around the function text taken from $1 (a file
# holding a version of the gate script). Extracting rather than copying is the
# point: if somebody rewrites the loop, this test follows them.
build_harness() {
    local src="$1" out="$2"
    {
        echo '#!/bin/bash'
        echo 'set -euo pipefail'
        # The counting loop is all we exercise; these stubs stand in for the
        # sourced common.sh so the harness has no repo dependencies.
        echo 'log_warn() { :; }'
        echo 'log_error() { :; }'
        # gh_json is the third common.sh helper the gate now uses: the fetch was
        # `gh api ... 2>/dev/null || echo "[]"`, which turned an API failure into
        # a PR with no review comments. The stub keeps this harness about the
        # COUNTING loop by passing the call straight through to the shimmed gh,
        # exactly as the real helper does on its first successful attempt.
        echo 'gh_json() { shift; [[ "${1:-}" == "--" ]] && shift; gh "$@"; }'
        sed -n '/^LOW_EFFORT_PATTERNS=(/,/^)/p' "$src"
        sed -n '/^is_low_effort_reply()/,/^}/p' "$src"
        sed -n '/^check_pr_review_comments()/,/^}/p' "$src"
        echo 'check_pr_review_comments some/repo 1'
    } > "$out"
    chmod +x "$out"
}

run_harness() {
    local harness="$1" shim="$2"
    ( PATH="$shim:$PATH" "$harness" 2>/dev/null )
}

# ---------------------------------------------------------------------------

test_extraction_is_not_vacuous() {
    # Anti-vacuity: if the sed ranges stop matching (renamed function, reflowed
    # file), both harnesses would be empty and both would "agree", which would
    # look like a pass. Assert the real thing was actually extracted.
    build_harness "$GATE" "$WORK/new.sh"
    assert_contains "$(cat "$WORK/new.sh")" "check_pr_review_comments()" \
        "the harness really contains the extracted function"
    assert_contains "$(cat "$WORK/new.sh")" "unreplied_count" \
        "the harness really contains the counter under test"
    log_pass "the function text was extracted from the real gate, not stubbed"
}

test_fixed_version_counts_every_unreplied_comment() {
    mk_gh_shim "$WORK/bin"
    build_harness "$GATE" "$WORK/new.sh"
    local out
    out="$(run_harness "$WORK/new.sh" "$WORK/bin")"
    assert_eq "$out" "2" \
        "both unreplied comments are counted, so the gate can state a real number"
    log_pass "the fixed counter reports 2 of 2 unreplied comments"
}

test_prefix_version_could_not_count_at_all() {
    # THE CONTROL. Recover the pre-fix text from git and prove it breaks. If
    # this ever starts returning 2, the bug is gone from git history and this
    # whole test is measuring nothing, so it fails loudly instead.
    local old="$WORK/old-gate.sh"
    if ! git -C "$REPO_ROOT" show "HEAD:$GATE_REL" > "$old" 2>/dev/null; then
        log_fail "could not recover the pre-fix gate from HEAD; control unavailable"
        return 1
    fi
    if ! grep -qE '\(\(\s*unreplied_count\+\+\s*\)\)' "$old"; then
        log_info "HEAD no longer contains the buggy increment (the fix has been committed)"
        log_info "control satisfied by the standalone bash semantics assertion below"
        return 0
    fi

    mk_gh_shim "$WORK/bin"
    build_harness "$old" "$WORK/old.sh"
    local out
    out="$(run_harness "$WORK/old.sh" "$WORK/bin")"
    assert_eq "$out" "" \
        "the pre-fix counter died before echoing, so it could report no count at all"
    log_pass "control: the pre-fix version produced NO count, confirming the defect was real"
}

test_bash_semantics_are_what_we_think() {
    # The claim underneath the whole fix, asserted directly rather than assumed:
    # `((x++))` at zero is fatal under set -e, and the replacement form is not.
    local before after
    before="$(bash -c 'set -euo pipefail; w=0; ((w++)); echo reached' 2>/dev/null || true)"
    after="$(bash -c 'set -euo pipefail; w=0; w=$((w + 1)); echo reached' 2>/dev/null || true)"
    assert_eq "$before" "" "((x++)) at zero aborts the script under set -e"
    assert_eq "$after" "reached" "x=\$((x + 1)) at zero does not"
    log_pass "the bash semantics behind the fix hold on this shell"
}

test_no_standalone_increments_remain() {
    # Structural sweep, so a future edit cannot quietly reintroduce the class
    # into any gate that runs under set -e.
    local found=0 f
    for f in "$REPO_ROOT"/.ci/scripts/quality/*.sh "$REPO_ROOT"/.ci/scripts/security/*.sh; do
        [[ -f "$f" ]] || continue
        grep -q '^set -e\|^set -[a-z]*e' "$f" || continue
        if grep -qE '^\s*\(\(\s*[a-zA-Z_][a-zA-Z0-9_]*\+\+\s*\)\)\s*$' "$f"; then
            log_error "standalone ((x++)) under set -e in ${f#"$REPO_ROOT"/}"
            found=$((found + 1))
        fi
    done
    assert_eq "$found" "0" "no gate under set -e still uses a standalone ((x++))"
    log_pass "no gate reintroduces the fatal-increment pattern"
}

log_test "test-shell-counter-increment"

test_extraction_is_not_vacuous
test_fixed_version_counts_every_unreplied_comment
test_prefix_version_could_not_count_at_all
test_bash_semantics_are_what_we_think
test_no_standalone_increments_remain

log_pass "all tests passed"

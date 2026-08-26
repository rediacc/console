#!/bin/bash
# check-commands.sh must not read its own documentation as code.
#
# WHY THIS EXISTS. Three detectors in this repo have now flagged text that
# merely RESEMBLED the construct they forbid, all within one wave (2026-08-26):
#
#   - check-toolchain-pins.sh A6 read an `echo` line PRINTING the shellcheck
#     directive as an INVOCATION of shellcheck.
#   - check-control-vacuity.sh read `sed 's/^/  /'` -- indenting a message for
#     display -- as a control built by pattern substitution.
#   - check-control-vacuity.sh then read a COMMENT about `${n//...}` as the
#     substitution itself.
#
# check-commands.sh already skips comments (the `# Skip if it's in a comment`
# branch in its scan loop) and therefore did NOT make that mistake -- a comment
# mentioning `seq 1 N` in check-control-vacuity.sh was correctly ignored while
# four real `seq` calls in check-shell-size.sh were caught. But NOTHING PROVED
# that skip works, so deleting it would go unnoticed until a comment somewhere
# started failing CI.
#
# A detector that can flag its own documentation cannot be satisfied except by
# deleting the explanation, which is how a repo loses the record of why a rule
# exists. This gate holds the skip in place.
#
# It drives the REAL script against a constructed tree rather than re-checking
# its regexes here: a copy of the predicate would pass while the shipped one
# rotted.
#
# WHAT THIS CANNOT SEE: only the comment/code distinction for one representative
# banned command. It does not enumerate every entry in DISALLOWED.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

SUT="$REPO_ROOT/.ci/scripts/security/check-commands.sh"
[[ -f "$SUT" ]] || log_fail "subject under test is missing: $SUT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# THE BANNED TOKENS LIVE IN VARIABLES, and that is not squeamishness: writing
# them in command position inside this file's own probe strings and regexes made
# check-commands.sh flag THIS GATE -- `seq 1 10` at the start of a probe line,
# and `mapfile` after the `|` of an alternation, which its pattern reads as a
# pipeline. A gate that tests the comment/code distinction cannot itself be
# written in a way that trips it. An assignment is not command position, so this
# form is invisible to the scanner while still exercising the real thing.
BANNED_SEQ="seq"
BANNED_MAPFILE="mapfile"

# run_against <probe-content> -- builds a throwaway repo root whose ONLY shell
# script is the probe, drops the real gate into it, and runs it there. The gate
# derives its root from its own path and scans `.ci` + `scripts`, so this
# exercises the shipped enumeration and the shipped skip logic.
run_against() {
    local content="$1" root
    root="$(mktemp -d -p "$WORK")"
    mkdir -p "$root/.ci/scripts/security"
    cp "$SUT" "$root/.ci/scripts/security/check-commands.sh"
    printf '%s' "$content" >"$root/.ci/probe.sh"
    (cd "$root" && ./.ci/scripts/security/check-commands.sh >/dev/null 2>&1)
}

test_a_banned_command_in_code_is_caught() {
    log_test "the control that matters: a real banned command must FAIL"
    # If this does not fail, every other assertion here is vacuous -- the gate
    # would be passing everything.
    if run_against "$(printf '#!/bin/bash\n%s 1 10\n' "$BANNED_SEQ")"; then
        log_fail "a real ${BANNED_SEQ} call was NOT caught; this gate proves nothing"
    fi
    log_pass "a banned command in code is caught"
}

test_the_same_command_in_a_comment_is_ignored() {
    log_test "the same command in a COMMENT must NOT fail"
    if ! run_against "$(printf '#!/bin/bash\n# we deliberately avoid %s 1 10 here; use a for loop\necho ok\n' "$BANNED_SEQ")"; then
        log_fail "a banned command inside a COMMENT was flagged -- the gate now reads prose as code"
    fi
    log_pass "prose naming a banned command is not an invocation"
}

test_this_repos_own_explanations_survive() {
    log_test "the real tree's own comments about banned commands stay clean"
    # Not a synthetic probe: this repo genuinely documents `seq` and `mapfile`
    # in comments explaining why they are avoided. If the skip regressed, those
    # explanations would start failing CI, and the tempting fix would be to
    # delete them.
    local documented pattern
    pattern="^[[:space:]]*#.*\\b(${BANNED_SEQ}|${BANNED_MAPFILE})\\b"
    documented="$(grep -rlE "$pattern" \
        "$REPO_ROOT/.ci/scripts/quality" "$REPO_ROOT/.ci/scripts/security" 2>/dev/null | wc -l)"
    [[ "$documented" -ge 1 ]] ||
        log_fail "anti-vacuity: found no file documenting a banned command, so this proves nothing"
    "$SUT" >/dev/null 2>&1 ||
        log_fail "the live tree fails the gate; its own explanations are being read as code"
    log_pass "$documented file(s) document a banned command in prose, and the tree stays green"
}

test_a_banned_command_in_code_is_caught
test_the_same_command_in_a_comment_is_ignored
test_this_repos_own_explanations_survive

echo
log_pass "ci-compat prose control: 3/3"
echo "  Blind spot: covers the comment/code distinction for representative"
echo "  commands only; it does not enumerate every DISALLOWED entry."

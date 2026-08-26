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
    # THE PROBE MUST REACH THE SKIP BRANCH, and the obvious probe does not.
    #
    # check-commands.sh's outer scan requires the banned word to be immediately
    # preceded by line-start whitespace, `|`, `&`, `;`, `$(` or `if `. In plain
    # prose ("we deliberately avoid seq 1 10 here") the word follows an ordinary
    # letter, so the outer regex never matches and the comment-skip branch three
    # lines below is never consulted. A probe like that passes identically with
    # the skip branch DELETED -- measured: exit 0 both ways.
    #
    # Putting the word directly after a trigger character makes the outer scan
    # match, so the only thing that can suppress it is the skip branch itself:
    # exit 0 with the branch, exit 1 without. Caught in review of b15995c1; the
    # first version of this test was vacuous in exactly the way it was written
    # to prevent.
    if ! run_against "$(printf '#!/bin/bash\n# equivalent to: cmd | %s 1 10\necho ok\n' "$BANNED_SEQ")"; then
        log_fail "a banned command inside a COMMENT was flagged -- the gate now reads prose as code"
    fi
    log_pass "a comment whose banned word FOLLOWS a trigger char is not an invocation"
}

test_control_the_probe_actually_reaches_the_skip_branch() {
    log_test "CONTROL: delete the skip branch and the probe MUST flip"
    # The definitive control, and the one whose absence let the vacuous version
    # ship: copy the real gate, delete ONLY the comment-skip branch, and require
    # the same probe to change its verdict. If it does not, the probe is not
    # exercising the branch and every assertion above is decoration.
    local root probe rc_intact rc_cut
    root="$(mktemp -d -p "$WORK")"
    mkdir -p "$root/.ci/scripts/security"
    cp "$SUT" "$root/.ci/scripts/security/check-commands.sh"
    probe="$root/.ci/probe.sh"
    printf '#!/bin/bash\n# equivalent to: cmd | %s 1 10\necho ok\n' "$BANNED_SEQ" >"$probe"

    (cd "$root" && ./.ci/scripts/security/check-commands.sh >/dev/null 2>&1) && rc_intact=0 || rc_intact=$?

    python3 - "$root/.ci/scripts/security/check-commands.sh" <<'CUTPY' || log_fail "could not plant the control: the skip branch was not found"
import pathlib
import sys

p = pathlib.Path(sys.argv[1])
s = p.read_text()
needle = "# Skip if it's in a comment"
i = s.find(needle)
if i < 0:
    sys.exit(1)
end = s.index("fi\n", i) + 3
p.write_text(s[:i] + s[end:])
CUTPY

    (cd "$root" && ./.ci/scripts/security/check-commands.sh >/dev/null 2>&1) && rc_cut=0 || rc_cut=$?

    [[ "$rc_intact" -eq 0 ]] ||
        log_fail "the probe already fails WITH the skip branch present (rc=$rc_intact)"
    [[ "$rc_cut" -ne 0 ]] ||
        log_fail "CONTROL DID NOT FIRE: deleting the comment-skip branch changed nothing, so the probe never reaches it"
    log_pass "probe reaches the branch: intact=$rc_intact, branch-deleted=$rc_cut"
}

test_this_repos_own_explanations_survive() {
    log_test "the real tree's own comments about banned commands stay clean"
    # WHAT THIS DOES AND DOES NOT PROVE, corrected in review of b15995c1.
    #
    # It guards against OVER-firing: the live tree must stay green while it
    # genuinely documents banned commands in prose. That is worth holding.
    #
    # It does NOT exercise the comment-skip branch. None of those files mentions
    # a banned command directly after `|`/`&`/`;`/`$(`, so the outer scan never
    # matches their comment lines and the skip branch is never consulted for
    # them. The control above is the only assertion here that reaches it. Do not
    # read this one as coverage of the skip.
    local documented pattern
    pattern="^[[:space:]]*#.*\\b(${BANNED_SEQ}|${BANNED_MAPFILE})\\b"
    documented="$(grep -rlE "$pattern" \
        "$REPO_ROOT/.ci/scripts/quality" "$REPO_ROOT/.ci/scripts/security" 2>/dev/null | wc -l)"
    [[ "$documented" -ge 1 ]] ||
        log_fail "anti-vacuity: found no file documenting a banned command, so this proves nothing"
    "$SUT" >/dev/null 2>&1 ||
        log_fail "the live tree fails the gate; its own explanations are being read as code"
    log_pass "$documented file(s) document a banned command in prose; tree green (over-fire guard, NOT skip-branch coverage)"
}

test_a_banned_command_in_code_is_caught
test_the_same_command_in_a_comment_is_ignored
test_control_the_probe_actually_reaches_the_skip_branch
test_this_repos_own_explanations_survive

echo
log_pass "ci-compat prose control: 4/4"
echo "  Blind spot: covers the comment/code distinction for representative"
echo "  commands only; it does not enumerate every DISALLOWED entry. Only the"
echo "  branch-deletion control reaches the comment-skip branch; the live-tree"
echo "  assertion guards against over-firing and proves nothing about the skip."

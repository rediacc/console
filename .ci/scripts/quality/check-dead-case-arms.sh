#!/bin/bash
# A test assertion must be able to FAIL. This gate catches one mechanically
# detectable way it cannot: a `case` arm that globs for a `field=` token which
# exists nowhere in the code the test exercises.
#
# THE DEFECT THIS COMES FROM, 2026-08-05, written by the session lead while
# auditing other agents for exactly this class. A test proving the CI profiler
# reads a container's ceiling rather than the host's asserted the second half
# like this:
#
#     case "$out" in
#         *"cores=20"* | *"cores=1[0-9]"* | *"cores=[3-9]"*)
#             log_fail "the sampler sized itself from the HOST" ;;
#     esac
#
# The sampler's #META record is TSV. It contains no `cores=` anywhere. All
# three arms were dead, so the "not the host's" half of that test passed
# permanently while proving nothing, and its green was reported as evidence.
#
# WHY THIS SHAPE AND NOT SOMETHING BROADER. "Detect assertions that cannot
# fail" is not decidable in general, and a fuzzy version of it would be noisy
# enough to get suppressed -- which is the failure mode this repo keeps
# finding. So the scope is deliberately narrow and mechanical: a case-arm glob
# is an ASSERTION (unlike a `FOO=` assignment, of which there are ~20 in the
# suite and none are assertions), and a `key=` token in one is a claim about
# the SHAPE of data some other script produced. If that key appears in no
# non-test script, the arm is dead by construction.
#
# It reports zero findings today. That is the point of the control below: a
# gate whose green has never been contrasted with a red is a gate nobody has
# checked, so this one plants its own defect and refuses to pass unless that
# planted defect is caught.
#
# Usage: check-dead-case-arms.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

TEST_DIRS="${DEAD_CASE_TEST_DIRS:-.ci/scripts/test}"
# Where the data-producing code lives. A key must appear in at least one of
# these to be a live reference.
CODE_DIRS="${DEAD_CASE_CODE_DIRS:-.ci/scripts scripts packages/www/scripts}"

# extract_case_keys <dir...>: emit "file:line:key" for every `key=` token that
# appears inside a case-arm glob (a line whose content ends in `)` and carries
# at least one `*"..."*` or `*...*` pattern).
extract_case_keys() {
    # A case-arm line: starts with an optional `*`, carries at least one
    # double-quoted glob segment, and ENDS in `)` (optionally followed by a
    # command on the same line). The earlier attempt anchored on `)$`, which
    # missed the common `... ) ;;` and `... )` -with-trailing-code shapes and
    # made this gate's own control fail -- which is exactly what the control
    # is for.
    grep -rnE '^[[:space:]]*\*[^)]*"[^"]*"[^)]*\)' "$@" 2>/dev/null |
        grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' || true
}

# A key is LIVE when the literal `key=` occurs in any non-test code file AS
# CODE. Comment lines do not count, and that distinction is the whole gate.
#
# WITHOUT IT THIS GATE IS BLIND TO ITS OWN FOUNDING DEFECT, verified 2026-08-05
# with a two-fixture pair: an arm globbing `cores=20` was MISSED (exit 0) while
# an identical arm globbing `zzznosuchkeyq=20` FIRED (exit 1). The only two
# occurrences of `cores=` anywhere in CODE_DIRS were the comment lines in this
# file's own header describing the defect -- one of which is the sentence
# asserting that `cores=` appears nowhere. The gate had immunised itself
# against the bug it exists to catch, by describing it.
#
# The general form is worse than the instance: ANY script that documents a bad
# pattern in prose would vaccinate the whole tree against detecting that
# pattern, so the gate would grow quieter the better anything was commented.
# The sibling of this was already found in the CONTROL below and solved there
# with a generated key; it was left standing here, which is exactly the kind of
# half-fix that leaves a gate green and hollow.
key_is_live() {
    local key="$1"
    # shellcheck disable=SC2086 # CODE_DIRS is deliberately word-split
    grep -rhE --exclude-dir=test "${key}=" $CODE_DIRS 2>/dev/null |
        grep -qvE '^[[:space:]]*(#|//|\*)'
}

scan() {
    local dirs="$1" found=0 line file lineno key
    # shellcheck disable=SC2086 # dirs is deliberately word-split
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        file="${line%%:*}"
        lineno="$(printf '%s' "$line" | cut -d: -f2)"
        # Every `ident=` token inside the arm.
        while IFS= read -r key; do
            [ -n "$key" ] || continue
            key_is_live "$key" && continue
            log_error "$file:$lineno: case arm globs for '${key}=' but no non-test script under $CODE_DIRS emits that field, so this arm is DEAD and the assertion around it cannot fail"
            found=$((found + 1))
        done < <(printf '%s' "$line" | grep -oE '"[^"]*"' |
            grep -oE '[A-Za-z_][A-Za-z0-9_]{2,}=' | sed 's/=$//' | sort -u)
    done < <(extract_case_keys $dirs)
    return "$found"
}

# ---------------------------------------------------------------------------
# CONTROL FIRST. Plant the exact defect this gate exists for and require the
# scanner to catch it. A gate that has never been seen to fire is indisputably
# worthless, and this one would otherwise report a clean tree forever.
# ---------------------------------------------------------------------------
CONTROL_DIR="$(mktemp -d)"
trap 'rm -rf "$CONTROL_DIR"' EXIT
mkdir -p "$CONTROL_DIR/test"
# The planted key is GENERATED, never a literal. A literal placed here would
# live in this very file, which sits inside CODE_DIRS, so key_is_live would
# find it and call the planted arm "live" -- the control would then pass by
# accident and this gate would report a clean tree without ever having caught
# anything. Found by the control failing on its first run, which is the whole
# argument for putting the control before the scan.
PLANTED_KEY="deadarmprobe$$$(date +%s)"
cat >"$CONTROL_DIR/test/planted.sh" <<PLANTED
case "\$out" in
    *"${PLANTED_KEY}=20"* | *"${PLANTED_KEY}=1"*)
        log_fail "planted dead arm" ;;
esac
PLANTED

control_hits=0
scan "$CONTROL_DIR/test" 2>/dev/null || control_hits=$?
if [ "$control_hits" -eq 0 ]; then
    log_error "CONTROL FAILED: the scanner did not catch a planted dead case arm, so its verdict on the real tree means nothing"
    exit 1
fi

# ---------------------------------------------------------------------------
# The real scan.
# ---------------------------------------------------------------------------
real_hits=0
scan "$TEST_DIRS" || real_hits=$?
if [ "$real_hits" -gt 0 ]; then
    log_error "$real_hits dead case arm(s). Parse the data and assert on the PARSED value instead of globbing for a field name that may not exist."
    exit 1
fi

log_info "no dead case arms (control fired on a planted arm, so this verdict is real)"

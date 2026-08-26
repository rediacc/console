#!/bin/bash
# A SHELL FILE CAN GROW UNTIL IT KILLS THE LINTER, and nothing noticed.
#
# WHAT WENT WRONG, measured 2026-08-25: a shellcheck 0.10.0 run over 453 files
# was OOM-KILLED. Batching did not help, because the cause was ONE file --
# .claude/hooks/stop/test-worklist-v5.sh at 11,955 lines -- whose dataflow
# analysis took 2714 MB on its own. With `extended-analysis=false` the same file
# took 199 MB. The fix was to split it into a 135-line runner plus 22 topic
# files, which also took the path-scan gate from 51m02s to 7.9s.
#
# NOTHING PREVENTS IT COMING BACK. Every content-based linter passed that file:
# its own shellcheck findings were clean, shfmt was clean, and the size was
# invisible to all of them by construction -- a linter cannot report a file it
# died on. That is the i18n lesson exactly: fixed by hand, ungated.
#
# THE RULE IS SIZE **OR** THE DIRECTIVE, not size alone. A genuinely large
# generated or table-driven script is legitimate; what is not legitimate is one
# that is both large AND asks shellcheck for the expensive analysis. Carrying
# `# shellcheck extended-analysis=false` is an explicit, reviewable statement
# that the author knows the file is big, so the gate accepts it.
#
# WHY THIS THRESHOLD. Measured on the tree the day this gate was written: the
# largest shell file is run.sh at 2,418 lines, then a 2,373-line gate test. The
# 5,000 limit therefore flags nothing today, sits >2x above the real maximum so
# ordinary growth never trips it, and is <half the 11,955 that actually caused
# the OOM -- it fires long before the failure it exists to prevent.
#
# WHAT THIS GATE CANNOT SEE: lines are a proxy. A 3,000-line file of pathological
# nesting could still be expensive, and a 6,000-line file of flat `case` arms is
# cheap. The proxy is deliberate -- it is mechanical, has no false negatives in
# the direction that hurt us, and the directive is the documented escape.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'
fails=0
pass() { echo "  ok   $*"; }
fail() {
    echo "  ${RED}FAIL${NC} $*"
    fails=$((fails + 1))
}

MAX_LINES="${SHELL_MAX_LINES:-5000}"
MIN_FILES=50

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# over_limit <file> -- echoes the line count when the file breaks the rule
# (too big AND no directive), nothing otherwise.
over_limit() {
    local f="$1" n
    # A FILE THE GATE CANNOT READ MUST NOT READ AS COMPLIANT. This was
    # `|| echo 0`, which gave an unreadable file the same value as an empty one
    # -- so a permission error or a broken symlink passed the size check
    # silently. That is the exact vacuity this gate exists to prevent, sitting
    # inside the gate itself. Caught by check-swallowed-failures.
    n="$(wc -l <"$f" 2>/dev/null)" || n=""
    n="${n//[[:space:]]/}"
    if [[ -z "$n" ]]; then
        echo "UNREADABLE"
        return 0
    fi
    [[ "$n" -le "$MAX_LINES" ]] && return 0
    # The escape must be a real directive line, not prose mentioning it: this
    # gate's own header names the flag several times.
    grep -qE '^[[:space:]]*#[[:space:]]*shellcheck[[:space:]]+.*extended-analysis=false' "$f" && return 0
    echo "$n"
}

# gen_lines <count> -- N trivial shell lines. NOT `seq`: ubuntu-slim does not
# ship it, and check-ci-compat flags it. Same reason mapfile is avoided below.
gen_lines() {
    local i
    for ((i = 1; i <= $1; i++)); do echo "echo $i"; done
}

# DISCOVERED, tracked AND untracked. `git ls-files` alone is blind to a script
# not yet committed, which is exactly when a file is being grown.
FILES=()
while IFS= read -r _rel; do
    [[ -n "$_rel" ]] && FILES+=("$_rel")
done < <(
    {
        git -C "$ROOT" ls-files '*.sh' 2>/dev/null
        git -C "$ROOT" ls-files --others --exclude-standard '*.sh' 2>/dev/null
    } | sort -u
)

scanned=0
offenders=()
for rel in "${FILES[@]}"; do
    [[ -n "$rel" && -f "$ROOT/$rel" ]] || continue
    scanned=$((scanned + 1))
    n="$(over_limit "$ROOT/$rel")"
    if [[ "$n" == "UNREADABLE" ]]; then
        offenders+=("$rel (could not be read -- reporting rather than assuming compliant)")
    elif [[ -n "$n" ]]; then
        offenders+=("$rel ($n lines)")
    fi
done

# --- S1. no shell file is both oversized and asking for the expensive pass ----
if [[ ${#offenders[@]} -eq 0 ]]; then
    pass "S1. no shell file exceeds $MAX_LINES lines without the directive"
else
    fail "S1. these will make shellcheck's dataflow analysis explode:"
    printf '         %s\n' "${offenders[@]}"
    echo "         Fix by splitting the file, or add this line if the size is deliberate:"
    echo "         # shellcheck extended-analysis=false"
fi

# --- S2. anti-vacuity: a scan over nothing passes ----------------------------
if [[ "$scanned" -ge "$MIN_FILES" ]]; then
    pass "S2. $scanned shell file(s) actually scanned"
else
    fail "S2. SCANNED ONLY $scanned FILE(S) -- the enumeration broke, not the tree"
fi

# --- controls, by CONSTRUCTION -----------------------------------------------
# Generated with seq, never by copying and mutating a real file: a substitution
# can silently no-op, and the control then passes against unmutated input.
gen_lines $((MAX_LINES + 10)) >"$TMP/big.sh"
if [[ -n "$(over_limit "$TMP/big.sh")" ]]; then
    pass "control: an oversized file with no directive is detected"
else
    fail "CONTROL DID NOT FIRE: an oversized file went undetected"
fi

{
    echo '#!/bin/bash'
    echo '# shellcheck extended-analysis=false'
    gen_lines $((MAX_LINES + 10))
} >"$TMP/big-ok.sh"
if [[ -n "$(over_limit "$TMP/big-ok.sh")" ]]; then
    fail "IS OVER-BROAD: a file that declared the directive was still flagged"
else
    pass "control: an oversized file carrying the directive is allowed"
fi

gen_lines 10 >"$TMP/small.sh"
if [[ -n "$(over_limit "$TMP/small.sh")" ]]; then
    fail "IS OVER-BROAD: a small file was flagged"
else
    pass "control: a small file is not flagged"
fi

{
    echo '#!/bin/bash'
    echo '# we could add extended-analysis=false here, but we have not'
    gen_lines $((MAX_LINES + 10))
} >"$TMP/prose.sh"
if [[ -n "$(over_limit "$TMP/prose.sh")" ]]; then
    pass "control: prose mentioning the directive does not count as declaring it"
else
    fail "CONTROL DID NOT FIRE: a comment about the flag was accepted as the flag"
fi

echo
if [[ "$fails" -eq 0 ]]; then
    echo "${GREEN}✓${NC} shell size: $scanned file(s), none over $MAX_LINES lines undeclared."
    echo "  Blind spot: lines are a PROXY for analysis cost. Pathological nesting in a"
    echo "  small file is still expensive, and a long flat file is still cheap."
    exit 0
fi
echo "${RED}✗${NC} shell size: $fails failure(s)."
exit 1

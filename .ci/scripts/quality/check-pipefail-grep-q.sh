#!/usr/bin/env bash
# Gate: under `pipefail`, a locally-defined function piped into `grep -q` makes
# the pipeline's exit status a RACE, so a detector built that way can silently
# stop being able to fail.
#
# THE MECHANISM. `grep -q` exits the instant it matches. That closes the pipe,
# the producer gets SIGPIPE, and its status becomes 141. `set -o pipefail` makes
# the RIGHTMOST NON-ZERO status the pipeline's status -- so a pipeline that
# MATCHED reports 141, i.e. false. Whether it happens depends on whether the
# producer has already written everything into the 64 KB pipe buffer and exited,
# which is a function of output size and machine load. The same code returns
# different answers on different days.
#
# WHAT IT COST. `.ci/scripts/quality/check-ci-watch-recipe.sh` had exactly this
# in both of its detectors:
#
#     hands_out_banned() { advice_only "$1" | grep -qE '<banned>'; }
#
# Measured 2026-08-27 against .claude/hooks/test-hooks.sh (1644 lines, hit at
# line 692 of the filtered stream): 8/8 trips WITHOUT pipefail, 0/8 WITH it. The
# gate had been printing "no hand-rolled watch in 124 scanned file(s)" over a
# real offender, and went red exactly once -- under `npm run ci`'s parallel load,
# where the timing flipped. Its own four controls could not have caught it: all
# of them ran on 2-line fixtures, where the producer finishes long before
# `grep -q` exits, so the mechanism does not exist at that size.
#
# WHY A LOCALLY-DEFINED FUNCTION IS THE TEST, and not "any pipe into grep -q".
# There are 115 `| grep -q` sites under pipefail in this repo. What makes the shape
# MOST dangerous is a producer whose output SCALES WITH ITS INPUT -- a function that
# reads a file, filters a corpus, enumerates a tree. Judging "is the producer a
# function this file defines" is a property this gate owns, independent of what the
# code claims, which is the trap gates.md warns about: an assertion that re-asks a
# question the code already answered cannot fire.
#
# THE EXEMPTION BELOW USED TO BE STATED AS SAFETY, AND THAT WAS WRONG.
# This block previously read "almost all are harmless: `printf '%s' "$x" | grep -q`
# has a bounded producer that finishes before anything can race". Falsified on
# 2026-08-31 by CI run 33432878128, job 99628247967:
#
#     .ci/scripts/test/gates/test-run-sh.sh:67
#     if printf '%s' "$QA" | grep -q 'return 1'; then
#
# `$QA` is 1129 bytes, far inside the 64 KB pipe buffer, and the match sits on line
# 23 of ~30. It still raced: the log carries `printf: write error: Broken pipe` and
# the branch took the else, reporting "quality_all has no failure path" against code
# whose `return 1` grep had just FOUND. EPIPE does not depend on the buffer filling.
# It depends on whether `grep -q` has already exited and CLOSED the read end when the
# write syscall lands, and that is pure scheduling. A bounded producer is less likely
# to lose the race, never immune to it.
#
# So the narrow scope here is a matter of BLAST RADIUS, not of safety: the scaling
# producers are converted and gated at zero, and the bounded ones remain a known,
# measured flake source rather than a proven-safe pattern. Do not read this gate's
# green as a claim that a bounded `printf | grep -q` is correct. It is not; it is
# untriaged.
#
# THE FIX IS ALWAYS THE SAME and is a drop-in: command substitution reads the
# producer to completion, so there is no signal to race.
#
#     [ -n "$(producer | grep -E '<pattern>')" ]
#
# NO BASELINE, deliberately. The class was 13 sites and every one was converted,
# so this gate stands at zero with an anti-vacuity floor. A baseline here would
# have recorded ten provably-safe sites as debt and left three real risks
# sitting in a list that says "known, fine" -- and a stale baseline entry is a
# slot where the next regression hides.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

RED='' GREEN='' NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[0;31m' GREEN=$'\033[0;32m' NC=$'\033[0m'
fi
fails=0
fail() {
    echo "${RED}✗${NC} $*" >&2
    fails=$((fails + 1))
}
pass() { echo "${GREEN}ok${NC}   $*"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# offenders <file> -> "<line>:<text>" for each racing pipeline in that file
#
# Only scripts that actually set pipefail can have the bug; without it the
# pipeline reports grep's status and the match stands.
offenders() {
    local f="$1" fns fn
    grep -qE 'set -[a-z]*o pipefail|set -o pipefail' "$f" 2>/dev/null || return 0
    fns="$(grep -oE '^[A-Za-z_][A-Za-z0-9_]*\(\)' "$f" 2>/dev/null | tr -d '()' | sort -u)"
    [ -n "$fns" ] || return 0
    while IFS= read -r fn; do
        [ -n "$fn" ] || continue
        # A CALL to that function, then a pipe, then grep -q -- in CODE.
        #
        # COMMENTS AND STRING LITERALS ARE BOTH STRIPPED FIRST, and the second
        # one was learned the hard way: this gate flagged ITSELF the moment it
        # became a tracked file, because its own message text says
        # "no racing <function> | grep -q ..." and `pass` is a function it
        # defines. Four findings, every one of them prose describing the very
        # bug the gate exists for. That is the mention-as-execution class, this
        # time inside the gate written to catch a different class -- and its own
        # fixture heredoc (`if producer "$2" | grep -q ...`) is real code that
        # must stay quoted-out too, since it is a CONTROL, not a defect.
        #
        # `sed` blanks quoted spans rather than deleting the line, so line
        # numbers stay honest in the report.
        sed -e 's/#.*$//' -e "s/'[^']*'/''/g" -e 's/"[^"]*"/""/g' "$f" 2>/dev/null |
            grep -nE "\b${fn}\b[^|]*\|[[:space:]]*grep -q"
    done <<<"$fns"
}

scan_files() {
    git -C "$ROOT" ls-files \
        '.ci/scripts/**/*.sh' 'scripts/**/*.sh' '.claude/hooks/**/*.sh' 2>/dev/null
}

# ---- controls, by construction ----------------------------------------------
#
# THE FIRST ONE ASKS THE OPERATING SYSTEM, not this gate's regex. Everything
# else here is pattern matching, and pattern matching cannot tell you the
# mechanism is real on the machine the gate runs on. If SIGPIPE-under-pipefail
# ever stops flipping the verdict, this gate is guarding a myth and should say
# so rather than keep passing.
# THE PRODUCER MUST BE ONE THAT DIES ON SIGPIPE, and not every command does.
# Measured on this host (uutils coreutils 0.8.0, ugrep 7.8.4): `grep -v`, `sed`
# and `awk` all exhibit the race; `cat` does NOT -- uutils cat reports success
# on a 300 KB producer that was killed mid-write. The first draft of this
# control used `cat` and therefore could not reproduce the very mechanism the
# gate exists for; the control refused to pass, which is what caught it.
#
# `grep -v` is used here because that is literally what the defect's producer
# was: `advice_only()` in check-ci-watch-recipe.sh is a `grep -vE`.
# THE FIXTURE IS ASSEMBLED AT RUNTIME so this file's own TEXT never carries the
# racing shape contiguously. Written out literally, the gate flagged its own
# control fixture -- correctly, by its rule, since the fixture IS the bad shape
# on purpose. Self-exemption was the wrong answer: a gate that skips its own
# file stops policing the one script most likely to grow this bug next. The
# same runtime-concatenation convention test-hooks.sh uses for banned tokens.
GQ="grep -q"
cat >"$TMP/mech.sh" <<MECH
set -uo pipefail
producer() { grep -v ZZZ_NEVER_MATCHES "\$1"; }
if producer "\$2" | $GQ 'NEEDLE'; then echo MATCHED; else echo MISSED; fi
MECH
{
    echo NEEDLE
    # Well past the 64 KB pipe buffer, so the producer BLOCKS and grep -q's
    # early exit kills it. Under the buffer, nothing races and the control
    # would silently prove nothing -- which is exactly how the first attempt at
    # a large-file control in check-ci-watch-recipe.sh came out vacuous.
    pad="$(printf 'x%.0s' $(seq 1 200))"
    for _i in $(seq 1 1500); do printf '%s\n' "$pad"; done
} >"$TMP/big.txt"
mech_out="$(bash "$TMP/mech.sh" x "$TMP/big.txt" 2>/dev/null)"
if [ "$mech_out" = "MISSED" ]; then
    pass "control: SIGPIPE under pipefail really does flip a matching pipeline to false"
else
    fail "CONTROL DID NOT FIRE: a matching \`producer | grep -q\` reported '$mech_out' on a 300 KB producer. The mechanism this gate exists for did not reproduce, so its green means nothing here."
fi

printf '%s\n' \
    'set -o pipefail' \
    'body() { cat "$1"; }' \
    'if body "$1" | grep -q x; then :; fi' >"$TMP/bad.sh"
if [ -n "$(offenders "$TMP/bad.sh")" ]; then
    pass "control: a local function piped into grep -q is detected"
else
    fail "CONTROL DID NOT FIRE: the racing shape went undetected"
fi

printf '%s\n' \
    'set -o pipefail' \
    'body() { cat "$1"; }' \
    'if [ -n "$(body "$1" | grep x)" ]; then :; fi' >"$TMP/fixed.sh"
if [ -z "$(offenders "$TMP/fixed.sh")" ]; then
    pass "control: the command-substitution form is NOT flagged"
else
    fail "GATE IS OVER-BROAD: the sanctioned fix was flagged"
fi

printf '%s\n' \
    'set -o pipefail' \
    'if printf "%s" "$x" | grep -q y; then :; fi' >"$TMP/bounded.sh"
if [ -z "$(offenders "$TMP/bounded.sh")" ]; then
    pass "control: a bounded producer (printf, not a local function) is not flagged"
else
    fail "GATE IS OVER-BROAD: a bounded builtin producer was flagged"
fi

printf '%s\n' \
    'body() { cat "$1"; }' \
    'if body "$1" | grep -q x; then :; fi' >"$TMP/nopipefail.sh"
if [ -z "$(offenders "$TMP/nopipefail.sh")" ]; then
    pass "control: without pipefail the same shape is harmless and not flagged"
else
    fail "GATE IS OVER-BROAD: flagged a file that never sets pipefail"
fi

printf '%s\n' \
    'set -o pipefail' \
    'body() { cat "$1"; }' \
    '# never write: body "$1" | grep -q x' >"$TMP/comment.sh"
if [ -z "$(offenders "$TMP/comment.sh")" ]; then
    pass "control: prose describing the shape is not committing it"
else
    fail "GATE IS OVER-BROAD: a COMMENT naming the shape was read as code -- the mention-as-execution class"
fi

# ---- the real tree ----------------------------------------------------------
scanned=0
found=()
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    [ -f "$ROOT/$rel" ] || continue
    scanned=$((scanned + 1))
    while IFS= read -r hit; do
        [ -n "$hit" ] || continue
        found+=("$rel:$hit")
    done < <(offenders "$ROOT/$rel")
done < <(scan_files)

# ANTI-VACUITY: scanning nothing must FAIL, never pass quietly.
if [ "$scanned" -eq 0 ]; then
    fail "scanned ZERO files -- the pathspec matched nothing, so a green here would mean nothing"
elif [ ${#found[@]} -eq 0 ]; then
    pass "no racing \`function | grep -q\` under pipefail in $scanned scanned file(s)"
else
    fail "${#found[@]} racing pipeline(s): a local function piped into grep -q under pipefail"
    printf '    %s\n' "${found[@]}" >&2
    echo "" >&2
    echo "  grep -q exits at its first match and SIGPIPEs the producer; pipefail then" >&2
    echo "  makes that 141 the pipeline's status, so a pipeline that MATCHED reports" >&2
    echo "  false. It only bites once the producer outruns the 64 KB pipe buffer, so" >&2
    echo "  it passes on small inputs and flips under load." >&2
    echo "" >&2
    echo "  Fix, a drop-in:  [ -n \"\$(producer | grep -E '<pattern>')\" ]" >&2
fi

echo
if [ "$fails" -eq 0 ]; then
    echo "${GREEN}✓${NC} pipefail/grep -q: $scanned file(s) clean."
    echo "  Blind spot, stated so the green is not read as more than it is: this sees"
    echo "  only LOCALLY-DEFINED producers. A racing pipeline whose producer is an"
    echo "  external command with unbounded output is real and invisible here."
    exit 0
fi
echo "${RED}✗${NC} pipefail/grep -q: $fails failure(s)."
exit 1

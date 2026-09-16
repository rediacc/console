#!/usr/bin/env bash
# HEADER REMOVED 2026-09-08 BY THE W7 P4 CUTOVER, and the FILE deliberately stays.
# check:ci-pipefail-grep-q is now registered to the Python port's entry point,
# .ci/scripts/quality/check_pipefail_grep_q.py, so a header here would declare a
# registration that has moved and gate-bind refuses that by name:
#   package.json runs "...check_pipefail_grep_q.py" but its header derives "...check-pipefail-grep-q.sh"
# This script is NOT dead: it is the differential twin the port is compared
# against, and invariant 5 forbids deleting a twin in the change that ports
# it. Deletion is W7 P5's job, in a later change.

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
# Measured 2026-08-27 against .claude/hooks/test-hooks.sh, 1,644 lines then (hit at
# line 692 of the filtered stream): 8/8 trips WITHOUT pipefail, 0/8 WITH it. The
# gate had been printing "no hand-rolled watch in 124 scanned file(s)" over a
# real offender, and went red exactly once -- under `npm run ci`'s parallel load,
# where the timing flipped. Its own four controls could not have caught it: all
# of them ran on 2-line fixtures, where the producer finishes long before
# `grep -q` exits, so the mechanism does not exist at that size.
#
# THE SUBJECT IS THE SIZE, NOT THAT FILE. It was 1,644 lines the day this was
# measured, 2,774 by 2026-09-09, and it is being ported out of bash into
# .claude/rediacc_hooks/tests/ -- so the citation is dated on purpose and the
# large-file control below is what keeps the measurement reproducible after the
# file it names is gone.
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
# THE BOUNDED PRODUCERS STOPPED BEING EXEMPT ON 2026-09-16, and the deferral that
# used to sit here -- "a separate, larger, still-untriaged class" -- was closed by
# measuring it rather than by arguing about it. The measurement:
# `set -uo pipefail; if printf '%s' "$s" | grep -q NEEDLE; ...` with the NEEDLE on
# line 1, 40 trials per size, this host:
#
#       payload   printf MISSED   echo MISSED
#       1,219 B       0/40           0/40
#       8,289 B       0/40           0/40
#      16,470 B       0/40            --
#      32,832 B       0/40            --
#      49,194 B      32/40            --
#      61,516 B      40/40            --
#      65,556 B      39/40          40/40
#     300,078 B      40/40            --
#
# So the shell BUILTINS reproduce the class outright, and the knee sits between
# 32 KB and 48 KB -- BELOW the nominal 64 KB pipe buffer, because `grep -q` exits
# after its FIRST READ rather than after the buffer fills. This also re-confirms
# the 2026-08-31 datum above from the other side: a 1129-byte printf is 0/80 here
# and still lost the race once in CI under load, so sub-knee is RARE, not SAFE.
#
# The mechanism differs and the effect does not: a BUILTIN takes EPIPE and returns
# non-zero, an EXTERNAL producer is SIGPIPE'd to 141, and under `pipefail` both
# make a pipeline that MATCHED report false. `printf` and `echo` are therefore in
# SCALING_PRODUCERS, and the eleven sites that widening found across eight files
# were converted in the same change.
#
# `.claude/oracles/**` IS EXCLUDED FROM THE CORPUS ON PURPOSE and holds eight of
# the shape. Those files are the FROZEN bash originals for
# `.claude/rediacc_hooks/guards/block_compacted_plan_edit.py` and
# `block_unlinked_commit_author.py`; `.claude/oracles/README.md:49-54` says "They
# are FROZEN. Do not fix a bug here; fix it in the port." Nothing registers them,
# the live code is Python and has no pipe, so the eight are not defects and must
# not be converted. Recorded here so the next sweep does not re-derive 47 files
# and 104 sites and have to work out again why they do not count.
#
# THE PIPEFAIL TEST IS PER-FILE, AND IT IS WRONG IN BOTH DIRECTIONS. It greps the
# whole file for `set -o pipefail` and cannot see an inner shell's options:
#
#   FALSE POSITIVE -- `.ci/scripts/test/test-install-methods.sh:1129`. The file
#   sets `set -euo pipefail` at line 29, but the flagged line lives inside a
#   `docker run ... bash -c "..."` whose INNER shell sets `set -e` only (line 1057,
#   and the same at 800, 886, 925, 965, 1010, 1097). Without pipefail the pipeline
#   reports grep's status and the match stands, so there is no bug at that line.
#   Converted regardless: an allowlist entry would be a suppression, which this
#   repo forbids, and the conversion is defensively correct the day anyone adds
#   `-o pipefail` to those container scripts.
#
#   FALSE NEGATIVE -- `.ci/lib/devbox.sh:1082`, which is the strongest finding the
#   2026-09-16 sweep produced. The file sets no pipefail of its own and INHERITS it
#   from every sourcer: `scripts/dev/worktree.sh:12`, and `.ci/lib/local-common.sh`
#   at 937 and 983, itself sourced by `rdc.sh:11`. It is a live, user-facing
#   detector -- `devbox_identity_ok` hunting "dubious ownership" -- and losing the
#   race makes it return SUCCESS. INHERITS_PIPEFAIL_PREFIXES below is the narrow
#   answer. A general source-graph analyser is not proportionate: measured over
#   every tracked shell file that lacks its own pipefail and is sourced by one that
#   has it, this is the ONLY such site in the repository.
#
# THE FIX IS ALWAYS THE SAME and is a drop-in: command substitution reads the
# producer to completion, so there is no signal to race.
#
#     [ -n "$(producer | grep -E '<pattern>')" ]
#
# THREE CAVEATS ON THAT DROP-IN, each paid for by a site in the 2026-09-16 sweep:
#
#   1. KEEP EVERY GREP FLAG EXCEPT `-q`. The spelling above is an EXAMPLE, not the
#      rule. `proxy-go-unit.sh:124` was `grep -qx` and became `grep -Fx`;
#      `renet .ci/scripts/quality/i18n.sh:229` is `grep -q --` and the `--` is
#      load-bearing, because its pattern starts `--- PASS:`.
#
#   2. `[ -n "$(...)" ]` IS NOT EQUIVALENT WHEN THE PATTERN CAN MATCH AN EMPTY
#      LINE. Command substitution strips trailing newlines, so a matched empty line
#      reads back as no match. Checked against all eleven patterns in that sweep --
#      none can match empty -- and recorded here because the next sweep must check
#      it again rather than inherit the conclusion.
#
#   3. `set -e` BEHAVIOUR IS UNCHANGED as long as the converted test keeps its
#      position in the same `&&`/`||` list. Verify by RUNNING the file, not by
#      reading it.
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
# PRODUCERS WHOSE OUTPUT SCALES WITH THEIR INPUT. The criterion this gate has
# stated since it was written is "a producer whose output SCALES WITH ITS INPUT --
# a function that reads a file, filters a corpus, enumerates a tree". Only the
# FUNCTION half was ever implemented, so a scaling producer that happened to be a
# command was invisible to it.
#
# THE HOLE WAS LIVE. check-control-vacuity.sh:81-83 is three `grep` stages piped
# into `grep -qE`, and it lost the race in 2 of 20 measured runs under suite
# load, returning 141 for a file that MATCHED. That did not merely flake a test:
# the gate moved the file from `checked` to `exempt` and stopped checking one of
# its own controls while still printing a tick.
#
# `printf`/`echo` JOINED THIS LIST ON 2026-09-16, when the deferral the header used
# to carry was closed by measurement: both builtins report MISSED 40/40 at 300 KB
# and the knee is between 32 KB and 48 KB. They are here for the same reason as the
# commands -- their output scales with what is interpolated into them, which is
# routinely a captured command's whole stdout -- not because "printf" is dangerous.
SCALING_PRODUCERS="awk cat comm cut diff echo find git grep jq ls printf sed sort tail tr uniq xargs"

# A SOURCED LIBRARY INHERITS ITS SOURCER'S OPTIONS, and the per-file pipefail test
# cannot see that. These repo-relative prefixes are treated as pipefail-bearing
# whatever the file itself sets; see the header's FALSE NEGATIVE note. One prefix,
# because one site in the whole repository needs it: building a source-graph
# analyser for `.ci/lib/devbox.sh:1082` would be the wrong size of answer.
INHERITS_PIPEFAIL_PREFIXES=".ci/lib/"

# inherits_pipefail <repo-relative-path> -- true if the path is under one of them.
# An EMPTY path is false, so the fixture controls above, which have no repo-relative
# identity, keep testing the ordinary per-file rule.
inherits_pipefail() {
    local rel="${1:-}" prefix
    [ -n "$rel" ] || return 1
    for prefix in $INHERITS_PIPEFAIL_PREFIXES; do
        case "$rel" in
            "$prefix"*) return 0 ;;
        esac
    done
    return 1
}

# Stripped lines, with a pipeline CONTINUED onto the next line joined into one.
#
# A pipeline written across several lines was invisible to a per-line regex, and
# that is exactly how check-control-vacuity.sh survived every run of this gate:
# its three stages sit on three separate lines, so no single line ever held both
# a producer and `grep -q`.
#
# Joined with NO separator -- the next line's own indentation keeps the tokens
# apart, and inserting anything here would break byte-for-byte agreement with the
# port. The emitted number is the line the pipeline STARTED on.
join_logical() {
    local f="$1" n=0 start=0 buf="" line
    while IFS= read -r line; do
        n=$((n + 1))
        if [ -z "$buf" ]; then
            start=$n
            buf="$line"
        else
            buf="$buf$line"
        fi
        if [[ "$buf" =~ \|[[:blank:]]*$ ]]; then
            continue
        fi
        printf '%s:%s\n' "$start" "$buf"
        buf=""
    done < <(sed -e 's/#.*$//' -e "s/'[^']*'/''/g" -e 's/"[^"]*"/""/g' "$f" 2>/dev/null)
    [ -n "$buf" ] && printf '%s:%s\n' "$start" "$buf"
    return 0
}

offenders() {
    local f="$1" rel="${2:-}" fns fn joined
    if ! inherits_pipefail "$rel"; then
        grep -qE 'set -[a-z]*o pipefail|set -o pipefail' "$f" 2>/dev/null || return 0
    fi
    fns="$(
        {
            grep -oE '^[A-Za-z_][A-Za-z0-9_]*\(\)' "$f" 2>/dev/null | tr -d '()'
            printf '%s\n' $SCALING_PRODUCERS
        } | sort -u
    )"
    [ -n "$fns" ] || return 0
    joined="$(join_logical "$f")"
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
        printf '%s\n' "$joined" |
            grep -E "\b${fn}\b[^|]*\|[[:space:]]*grep -q"
    done <<<"$fns"
}

scan_files() {
    # `:(glob)` IS LOAD-BEARING, NOT DECORATION. Without it git reads `**` as
    # DEMANDING a slash, so `scripts/**/*.sh` matches nothing at depth 1 and this
    # corpus silently skipped six tracked shell files -- require-jq.sh,
    # require-python.sh, test-hooks.sh, backup-cutover-preflight.sh,
    # eslint-heap.sh and pre-commit-check.sh. Measured 2026-09-08: 471 files
    # before, 477 after. A corpus that quietly omits its own depth-1 members is
    # the failure this gate exists to catch, one level up.
    #
    # ONE LINE, also deliberately: `check:ci-pathspec-scope` detects a
    # `git ls-files` call and its quoted pathspecs ON ONE LINE, so the backslash
    # continuation this used to carry made both this call and its port invisible
    # to the gate that audits pathspecs. It could not see either live instance of
    # the shape it exists to find.
    #
    # THE LAST THREE ROOTS WERE ADDED 2026-09-16 and cost 26 files for two
    # findings, both real: `.ci/lib/devbox.sh:1082` (a silent-miss detector, and
    # the reason `.ci/lib/` is also in INHERITS_PIPEFAIL_PREFIXES) and
    # `.devcontainer/start-kvm.sh:216`, which offended the rule as it stood and was
    # invisible only because nothing looked there. `.ci/media/**` came in with them
    # and is clean; it is listed so the next shell script written there is covered
    # rather than discovered by the sweep after next.
    git -C "$ROOT" ls-files ':(glob).ci/scripts/**/*.sh' ':(glob)scripts/**/*.sh' ':(glob).claude/hooks/**/*.sh' ':(glob).ci/lib/**/*.sh' ':(glob).devcontainer/**/*.sh' ':(glob).ci/media/**/*.sh' 2>/dev/null
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
    printf -v pad '%*s' 200 ''
    pad=${pad// /x}
    for ((_i = 1; _i <= 1500; _i++)); do printf '%s\n' "$pad"; done
} >"$TMP/big.txt"
mech_out="$(bash "$TMP/mech.sh" x "$TMP/big.txt" 2>/dev/null)"
if [ "$mech_out" = "MISSED" ]; then
    pass "control: SIGPIPE under pipefail really does flip a matching pipeline to false"
else
    fail "CONTROL DID NOT FIRE: a matching \`producer | grep -q\` reported '$mech_out' on a 300 KB producer. The mechanism this gate exists for did not reproduce, so its green means nothing here."
fi

# THE SECOND MECHANISM CONTROL, AND IT IS NOT A DUPLICATE OF THE FIRST. The one
# above kills an EXTERNAL producer with SIGPIPE, and that is a different kernel
# path from the one a BUILTIN takes: bash traps SIGPIPE for its own builtins, so
# `printf` does not die -- it takes EPIPE from write(2) and returns non-zero, which
# `pipefail` then promotes to the pipeline's status. Without this control the two
# builtin controls below would be guarding a claim nothing on this host had
# confirmed, and if bash ever stopped propagating that EPIPE this gate would be
# flagging eleven sites for a mechanism that no longer exists.
#
# THE FIXTURE IS ASSEMBLED AT RUNTIME for the same reason as the first one, so this
# file's own text never carries the racing shape contiguously.
cat >"$TMP/mech-builtin.sh" <<MECHB
set -uo pipefail
payload="\$(cat "\$1")"
if printf '%s\n' "\$payload" | $GQ 'NEEDLE'; then echo MATCHED; else echo MISSED; fi
MECHB
mech_builtin_out="$(bash "$TMP/mech-builtin.sh" "$TMP/big.txt" 2>/dev/null)"
if [ "$mech_builtin_out" = "MISSED" ]; then
    pass "control: a BUILTIN producer takes EPIPE under pipefail and flips a matching pipeline to false"
else
    fail "CONTROL DID NOT FIRE: a matching \`printf | grep -q\` reported '$mech_builtin_out' on a 300 KB payload. The builtin EPIPE path did not reproduce, so the printf/echo half of this gate is guarding a myth here."
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

# THE BUILTIN HALF, ADDED 2026-09-16. These four controls used to be ONE control
# asserting the OPPOSITE -- "a bounded producer (printf, not a local function) is
# not flagged" -- which is why they are spelled out rather than folded into the
# command-producer pair above: the inversion is the change, and a reader diffing
# this file should see it stated, not inferred.
printf '%s\n' \
    'set -o pipefail' \
    'if printf "%s" "$x" | grep -q y; then :; fi' >"$TMP/builtin-printf.sh"
if [ -n "$(offenders "$TMP/builtin-printf.sh")" ]; then
    pass "control: a BUILTIN producer (printf) piped into grep -q is detected"
else
    fail "CONTROL DID NOT FIRE: a builtin printf producer raced and went undetected"
fi

printf '%s\n' \
    'set -o pipefail' \
    'if [ -n "$(printf "%s" "$x" | grep y)" ]; then :; fi' >"$TMP/builtin-printf-fixed.sh"
if [ -z "$(offenders "$TMP/builtin-printf-fixed.sh")" ]; then
    pass "control: the command-substitution form of printf is NOT flagged"
else
    fail "GATE IS OVER-BROAD: the sanctioned fix for a printf producer was flagged"
fi

printf '%s\n' \
    'set -o pipefail' \
    'if echo "$x" | grep -q y; then :; fi' >"$TMP/builtin-echo.sh"
if [ -n "$(offenders "$TMP/builtin-echo.sh")" ]; then
    pass "control: a BUILTIN producer (echo) piped into grep -q is detected"
else
    fail "CONTROL DID NOT FIRE: a builtin echo producer raced and went undetected"
fi

printf '%s\n' \
    'set -o pipefail' \
    'if [ -n "$(echo "$x" | grep y)" ]; then :; fi' >"$TMP/builtin-echo-fixed.sh"
if [ -z "$(offenders "$TMP/builtin-echo-fixed.sh")" ]; then
    pass "control: the command-substitution form of echo is NOT flagged"
else
    fail "GATE IS OVER-BROAD: the sanctioned fix for an echo producer was flagged"
fi

# INHERITED PIPEFAIL, both directions. The SAME bytes are classified twice, once
# under a repo-relative path inside INHERITS_PIPEFAIL_PREFIXES and once outside it,
# so the control cannot pass by accident of the file's own content: the content is
# identical and only the path differs.
printf '%s\n' \
    'lib_detect() { git -C "$1" status --porcelain; }' \
    'if printf "%s" "$out" | grep -q dubious; then :; fi' >"$TMP/inherited.sh"
if [ -n "$(offenders "$TMP/inherited.sh" ".ci/lib/inherited.sh")" ]; then
    pass "control: a file under .ci/lib/ with no pipefail of its OWN is still scanned"
else
    fail "CONTROL DID NOT FIRE: .ci/lib/devbox.sh:1082 is exactly this shape and would be invisible again"
fi
if [ -z "$(offenders "$TMP/inherited.sh" "scripts/dev/inherited.sh")" ]; then
    pass "control: the same bytes OUTSIDE the inheriting prefixes are not flagged"
else
    fail "GATE IS OVER-BROAD: a file that never sets pipefail was flagged on its path alone"
fi

# THE TWO CASES THE 2026-09-16 WIDENING ADDED. Each had a live offender in this
# repo and neither could be seen before, so each gets a control that fails if the
# widening is ever reverted or regressed.
printf '%s\n' \
    'set -o pipefail' \
    'if grep -vE "^x" "$1" | grep -q needle; then :; fi' >"$TMP/cmdprod.sh"
if [ -n "$(offenders "$TMP/cmdprod.sh")" ]; then
    pass "control: a scaling COMMAND producer piped into grep -q is detected"
else
    fail "CONTROL DID NOT FIRE: a command producer raced and went undetected"
fi

# check-control-vacuity.sh:81-83 in miniature: no single LINE holds both the
# producer and grep -q, which is why a per-line regex never saw the real one.
printf '%s\n' \
    'set -o pipefail' \
    'grep -vE "^x" "$1" |' \
    '    grep -qE needle' >"$TMP/multiline.sh"
if [ -n "$(offenders "$TMP/multiline.sh")" ]; then
    pass "control: a pipeline SPANNING LINES is detected"
else
    fail "CONTROL DID NOT FIRE: a multi-line racing pipeline went undetected"
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
    done < <(offenders "$ROOT/$rel" "$rel")
done < <(scan_files)

# ANTI-VACUITY: scanning nothing must FAIL, never pass quietly.
if [ "$scanned" -eq 0 ]; then
    fail "scanned ZERO files -- the pathspec matched nothing, so a green here would mean nothing"
elif [ ${#found[@]} -eq 0 ]; then
    pass "no racing \`producer | grep -q\` under pipefail in $scanned scanned file(s)"
else
    fail "${#found[@]} racing pipeline(s): a producer piped into grep -q under pipefail"
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
    echo "  producers that SCALE with their input -- this file's own functions, and"
    echo "  the commands and builtins in SCALING_PRODUCERS, which since 2026-09-16"
    echo "  includes printf and echo. What it still cannot see is an INNER shell's"
    echo "  options: the pipefail test is per-FILE, so a docker/ssh heredoc that sets"
    echo "  only 'set -e' reads as pipefail-bearing, and a sourced library reads as"
    echo "  clean unless its prefix is in INHERITS_PIPEFAIL_PREFIXES."
    exit 0
fi
echo "${RED}✗${NC} pipefail/grep -q: $fails failure(s)."
exit 1

#!/bin/bash
# HEADER REMOVED 2026-09-08 BY THE W7 P4 CUTOVER, and the FILE deliberately stays.
# check:ci-battery-clean-tree is now registered to the Python port's entry point,
# .ci/scripts/quality/check_battery_clean_tree.py, so a header here would declare a
# registration that has moved and gate-bind refuses that by name:
#   package.json runs "...check_battery_clean_tree.py" but its header derives "...check-battery-clean-tree.sh"
# This script is NOT dead: it is the differential twin the port is compared
# against, and invariant 5 forbids deleting a twin in the change that ports
# it. Deletion is W7 P5's job, in a later change.

# RETARGETED 2026-09-09 (W7P3-BAT), FROM .ci/scripts/test/run-all.sh ONTO
# .ci/rediacc_ci/battery.py, in lockstep with the port. The subject moved because
# battery.py replaces run-all.sh as the runner, and this gate polices the runner's
# tracked-tree snapshot and nothing else. Left pointed at the bash file it would
# have REFUSED the moment that file was deleted (CANNOT VERIFY, exit 1) and read
# as a bug in the deletion. The port's docstring carries the full reasoning; the
# three changes here are the subject path, the extractor's language, and the
# git-status sanity check, which had to be re-keyed because battery.py spells it
# as an argv list and not as two adjacent shell words.

# check:ci-battery-clean-tree -- the runner's tree guard must survive a CLEAN checkout.
#
# WHY THIS EXISTS, and it is a defect this gate's own subject introduced. run-all.sh
# snapshots tracked files before and after the battery so a gate test that rewrites
# one is caught by name. The first version of that snapshot was
#
#     tree_state() { ... git status --porcelain | grep -v '^??' | sort; }
#     TREE_BEFORE="$(tree_state)"
#
# and under `set -euo pipefail` a grep that filters EVERYTHING out exits 1, which the
# command substitution carries straight into an abort. `grep -v '^??'` matches nothing
# exactly when there are no MODIFIED tracked files -- a clean checkout. CI has one.
#
# THE FAILURE WAS INVISIBLE, which is the part worth gating. The abort happened before
# run-all.sh printed its first line, so CI showed the step exiting 1 with no test name,
# no assertion, no output at all. And it passed locally three times running, because a
# developer's tree nearly always carries some edit -- the grep matched, and the bug
# could not be reached from the machine where the code was written.
#
# WHAT THIS DOES NOT DO, stated because the wider rule is tempting and wrong. There are
# 21 other `VAR="$(... | grep ...)"` sites in tracked shell under `set -e`. Nearly all
# are `grep -c` over a fixture the test itself wrote, where an empty match means the
# FIXTURE is broken and aborting is defensible. The property that makes this one a bug
# is that empty is a LEGITIMATE, EXPECTED state. A blanket static rule cannot tell those
# apart and would report 21 findings to fix 1 -- the same shape check_git_history_depth
# records reverting at 89. So this gate asserts the behaviour, not the syntax.
#
# Exit 1 on a guard that cannot survive a clean tree, 2 on a failed control.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${BATTERY_CLEAN_TREE_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
BATTERY="$ROOT_DIR/.ci/rediacc_ci/battery.py"

# The subject is a Python function now, so judging it means DRIVING it. Without
# this probe an absent interpreter surfaces as `command not found` here and as an
# OSError in the port -- a divergence in the one case where the two must agree.
if ! command -v python3 >/dev/null 2>&1; then
    echo "✗ CANNOT VERIFY: python3 is not on PATH, and the subject is a Python" >&2
    echo "  function that has to be DRIVEN to judge it. Install python3." >&2
    exit 1
fi

FAIL=0
pass() { echo "PASS: $1"; }
fail() {
    echo "FAIL: $1"
    [[ -n "${2:-}" ]] && echo "      $2"
    FAIL=$((FAIL + 1))
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- the REAL function, extracted by name -----------------------------------
#
# Extracted rather than copied: a copy keeps passing after battery.py changes, which
# is the failure this whole battery exists to prevent. If the extraction finds
# nothing the gate REFUSES rather than reporting a clean tree guard that it never saw.
#
# THE TERMINATOR IS `^[^ \t]`, THE PYTHON ANALOGUE OF THE BASH `^}`: a def ends
# where the next COLUMN-1 statement begins, including a flush-left comment, which
# is exactly what follows tree_state in battery.py. Trailing blank lines are
# dropped in END so the text ends at the body's last statement.
#
# ONE-LINE OR MULTI-LINE, and the bash draft got this wrong in the direction that
# matters: a range that ran to the next terminator swallowed everything after a
# one-liner. `def tree_state(root): return ...` is legal Python, so the same case
# exists here. The self-closing test is anchored on the CLOSING PAREN, because
# `[^:]*` would otherwise stop at the annotation colon in
# `def tree_state(root: pathlib.Path) -> str:`.
#
# `!inside &&` ON THE FIRST RULE IS LOAD-BEARING, and the differential in
# .ci/rediacc_ci/tests/test_quality_battery_clean_tree.py is what found it
# missing. awk evaluates every rule against every record, so a SECOND
# `def tree_state(` reached while already inside a body re-entered rule 1 and
# kept reading, while the port's terminator stopped at it. The bash predecessor
# never hit this because its `^}` terminator fired first. FIRST DEFINITION WINS,
# on both sides.
GUARD="$(awk '
    !inside && /^def tree_state\(/ {
        buf[++n] = $0
        if ($0 ~ /^def tree_state\(.*\)[^:]*:[ \t]*[^ \t#]/) exit
        inside = 1
        next
    }
    inside {
        if ($0 ~ /^[^ \t]/) exit
        buf[++n] = $0
    }
    END {
        while (n > 0 && buf[n] ~ /^[ \t]*$/) n--
        for (i = 1; i <= n; i++) print buf[i]
    }
' "$BATTERY" 2>/dev/null)"
# `git status` IN EITHER SPELLING. The twin of this line used to be a plain
# `*"git status"*` glob, which is right for a shell pipeline and FALSE for the
# argv list battery.py writes: `["git", "status", "--porcelain"]` separates the
# two words with `", "`. Bash's own ERE is used rather than grep, so the ugrep
# alternated-anchor trap cannot reach this decision.
if [[ -z "$GUARD" ]] || ! [[ "$GUARD" =~ git[^A-Za-z0-9_]{0,8}status ]]; then
    echo "✗ CANNOT VERIFY: no tree_state() reading git status found in $BATTERY." >&2
    echo "  Either the guard was removed -- in which case the battery no longer" >&2
    echo "  notices a gate test rewriting a tracked file -- or it was renamed and" >&2
    echo "  this gate needs to follow it. Refusing rather than passing." >&2
    exit 1
fi

make_repo() { # make_repo <dir> <dirty:0|1>
    local d="$1" dirty="$2"
    git init -q --initial-branch=main "$d"
    git -C "$d" config user.email t@example.com
    git -C "$d" config user.name t
    echo original >"$d/tracked.txt"
    git -C "$d" add tracked.txt
    git -C "$d" commit -q -m init
    if [[ "$dirty" == "1" ]]; then echo changed >"$d/tracked.txt"; fi
    # An UNTRACKED file in both, because the guard filters `??` and that filtering is
    # exactly what makes the clean case produce no output at all.
    echo scratch >"$d/untracked.txt"
}

# drive <guard-source> <repo> -> prints "rc=<n> out=<value>"
#
# THE DRIVER IS HEAD + DEFINITION + TAIL and the port generates the same bytes
# from the same three pieces. The heredoc is QUOTED (`<<'HEAD'`), so nothing in it
# is expanded; the repo arrives as sys.argv[1] rather than as an interpolated
# literal, so a path holding a quote cannot rewrite the driver.
#
# THE TAIL CATCHES AND PRINTS `ERR:<type>: <message>` rather than letting the
# traceback out: a traceback carries the driver's own mktemp path, so the failure
# detail would differ between two runs of the SAME implementation and every twin
# comparison of a red would be noise.
drive() {
    local src="$1" repo="$2"
    cat >"$TMP/drive.py" <<'HEAD'
import pathlib
import subprocess
import sys

HEAD
    printf '%s\n' "$src" >>"$TMP/drive.py"
    cat >>"$TMP/drive.py" <<'TAIL'

try:
    T = tree_state(pathlib.Path(sys.argv[1]))
except BaseException as exc:
    print("ERR:%s: %s" % (type(exc).__name__, exc))
    raise SystemExit(1)
print("OUT:%s" % T)
TAIL
    local out rc=0
    out="$(python3 "$TMP/drive.py" "$repo" 2>&1)" || rc=$?
    printf 'rc=%s out=%s' "$rc" "${out#OUT:}"
}

make_repo "$TMP/clean" 0
make_repo "$TMP/dirty" 1

# --- THE PLANT: the pre-fix form must abort on a clean tree ------------------
#
# Without this the two assertions below could both pass against a guard that cannot
# fail, and this gate would be the thing it was written to catch.
#
# THE SAME DEFECT IN THE NEW LANGUAGE: the pre-fix pipeline handed back to bash
# under check=True. On a CLEAN tree the grep matches nothing, pipefail carries the
# 1 out of bash, and the snapshot aborts. That is not a synthetic failure; it is
# the realistic way a Python rewrite reintroduces the 2026-09-03 incident.
PREFIX_GUARD='def tree_state(root):
    proc = subprocess.run(
        ["bash", "-c", "set -euo pipefail; git status --porcelain | grep -v '"'"'^??'"'"' | sort"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.rstrip("\n")'
plant="$(drive "$PREFIX_GUARD" "$TMP/clean")"
if [[ "$plant" == rc=0* ]]; then
    fail "CONTROL: the pre-fix guard did NOT abort on a clean tree" "$plant"
else
    pass "CONTROL: the pre-fix guard aborts on a clean tree, so the defect is detectable"
fi

# --- the live guard, both trees ---------------------------------------------
live_clean="$(drive "$GUARD" "$TMP/clean")"
if [[ "$live_clean" == "rc=0 out=" ]]; then
    pass "the live guard survives a CLEAN checkout and reports no change"
else
    fail "the live guard does not survive a clean checkout" "$live_clean"
fi

live_dirty="$(drive "$GUARD" "$TMP/dirty")"
if [[ "$live_dirty" == rc=0*tracked.txt* ]]; then
    pass "CONTROL: it still REPORTS a modified tracked file, so the fix did not blind it"
else
    fail "the live guard no longer reports a modified tracked file" "$live_dirty"
fi

echo ""
if ((FAIL > 0)); then
    echo "✗ battery clean-tree guard: $FAIL failure(s)" >&2
    exit 1
fi
echo "✓ battery clean-tree guard: battery.py's snapshot survives a clean checkout and still sees a real change"
echo "  Blind spot: this asserts battery.py's guard only. The general 'a filter that"
echo "  legitimately matches nothing aborts the snapshot' shape is deliberately not"
echo "  gated -- see this file's header."

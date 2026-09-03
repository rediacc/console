#!/bin/bash
# check:ci-battery-clean-tree -- run-all.sh's tree guard must survive a CLEAN checkout.
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
RUN_ALL="$ROOT_DIR/.ci/scripts/test/run-all.sh"

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
# Extracted rather than copied: a copy keeps passing after run-all.sh changes, which
# is the failure this whole battery exists to prevent. If the extraction finds
# nothing the gate REFUSES rather than reporting a clean tree guard that it never saw.
# ONE-LINE OR MULTI-LINE, and the first draft got this wrong in the direction that
# matters: a `sed` range from the definition to the next `^}` swallowed everything
# after a ONE-LINE `tree_state() { ...; }`, including run-all.sh's own `cd
# "$GATES_DIR"`, and the harness then failed on an unbound variable rather than on
# the property under test. Take the definition line, and only keep reading if it did
# not close itself.
GUARD="$(awk '
    /^tree_state\(\) \{/ { print; if ($0 ~ /\}[[:space:]]*$/) exit; inside = 1; next }
    inside { print; if ($0 ~ /^\}/) exit }
' "$RUN_ALL" 2>/dev/null)"
if [[ -z "$GUARD" || "$GUARD" != *"git status"* ]]; then
    echo "✗ CANNOT VERIFY: no tree_state() reading git status found in $RUN_ALL." >&2
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
drive() {
    local src="$1" repo="$2"
    cat >"$TMP/drive.sh" <<DRIVE
set -euo pipefail
BATTERY_REPO_ROOT="$repo"
$src
T="\$(tree_state)"
echo "OUT:\$T"
DRIVE
    local out rc=0
    out="$(bash "$TMP/drive.sh" 2>&1)" || rc=$?
    printf 'rc=%s out=%s' "$rc" "${out#OUT:}"
}

make_repo "$TMP/clean" 0
make_repo "$TMP/dirty" 1

# --- THE PLANT: the pre-fix form must abort on a clean tree ------------------
#
# Without this the two assertions below could both pass against a guard that cannot
# fail, and this gate would be the thing it was written to catch.
PREFIX_GUARD="tree_state() { (cd \"\$BATTERY_REPO_ROOT\" && git status --porcelain 2>/dev/null | grep -v '^??' | sort); }"
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
echo "✓ battery clean-tree guard: run-all.sh's snapshot survives a clean checkout and still sees a real change"
echo "  Blind spot: this asserts run-all.sh's guard only. The general 'empty grep aborts"
echo "  under set -e' shape is deliberately not gated -- see this file's header."

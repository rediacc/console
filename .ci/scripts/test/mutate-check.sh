#!/usr/bin/env bash
#
# Two-direction mutation check: a defect-planted run that must go RED, and a
# clean run that must go GREEN. Design and the incidents behind it:
# agent/PLAN-promote-mutation-runner.md
#
# WHY BOTH DIRECTIONS. On 2026-08-09 two new suite cases went red under a
# mutation that disabled the guard they covered. The signature looked perfect.
# They were ALSO red on the untouched tree, so the mutation had demonstrated
# nothing: a case that can never pass goes red under every mutation, including
# a no-op one. The baseline is the pass that catches a broken fixture, and it
# is also the pass a hurried session skips, because the mutant already
# "proved" the point. This script exists so skipping it takes deliberate
# effort.
#
# WHERE THE MUTATION GOES. Into a full copy of the suite's directory, never
# the live tree. A kill between mutate and restore leaves a disabled guard in
# the working tree behind output that reads like success; that happened once,
# and it is what the trapguard rule `interrupted-cleanup-skipped` warns about.
# The BASELINE deliberately runs against the real tree at its real path,
# because a baseline's green is only meaningful for the tree that will
# actually be committed. The asymmetry is intentional and is printed.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SUITE="$REPO_ROOT/.claude/hooks/stop/test-worklist-v5.sh"
FILE=""
FROM=""
TO=""
EXPECT_RED=()
SANDBOX_ROOT="${TMPDIR:-/tmp}/mutate-check.$$"

# NO KNOWN-ARTIFACT ALLOWLIST, deliberately. The first version carried one for
# case 191, which asserts the anchor is the hook file's OWN repo and therefore
# could not pass in a flat out-of-repo copy. A peer review pointed out that the
# artifact was self-inflicted: the copy has to live at its REPO-RELATIVE path
# under a directory carrying a .git marker, or the repo-root arithmetic in
# wl_core has nothing to resolve against. Measured after the fix: the sandbox
# runs 669 passed / 0 failed with case 191 green. An allowlist you can delete by
# fixing the cause is always better than one you document.

usage() {
    cat >&2 <<'USAGE'
usage: mutate-check.sh --file <path> --from <exact string> --to <replacement>
                       --expect-red <case-id> [--expect-red <case-id> ...]
                       [--suite <path>]

--expect-red takes a CASE ID as the suite prints it after "PASS: " / "FAIL: "
(e.g. 208), never a phrase from the case's message: pass() and fail() word the
same case differently, so a phrase can only ever match one of the two passes.

Exits 0 only when the mutant is RED on every named case AND the
baseline is GREEN. Every other combination is a failure, including "both red",
which proves nothing and is reported as such.
USAGE
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --file)
            FILE="${2:-}"
            shift 2
            ;;
        --from)
            FROM="${2:-}"
            shift 2
            ;;
        --to)
            TO="${2:-}"
            shift 2
            ;;
        --expect-red)
            EXPECT_RED+=("${2:-}")
            shift 2
            ;;
        --suite)
            SUITE="${2:-}"
            shift 2
            ;;
        -h | --help) usage ;;
        *)
            echo "mutate-check.sh: unknown argument '$1'" >&2
            usage
            ;;
    esac
done

[[ -n "$FILE" && -n "$FROM" && -n "$TO" && ${#EXPECT_RED[@]} -gt 0 ]] || usage
[[ -f "$FILE" ]] || {
    echo "mutate-check.sh: --file '$FILE' does not exist" >&2
    exit 2
}
[[ -f "$SUITE" ]] || {
    echo "mutate-check.sh: --suite '$SUITE' does not exist" >&2
    exit 2
}

SUITE_DIR="$(cd "$(dirname "$SUITE")" && pwd)"
SUITE_BASE="$(basename "$SUITE")"
FILE_ABS="$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")"
case "$FILE_ABS" in
    "$SUITE_DIR"/*) ;;
    *)
        echo "mutate-check.sh: --file must live in the suite's directory ($SUITE_DIR)," >&2
        echo "  otherwise the sandbox copy would not contain it and the mutation" >&2
        echo "  would silently apply to nothing. Got: $FILE_ABS" >&2
        exit 2
        ;;
esac

# A start line, immediately. A long run and a wedged run both look like zero
# bytes to a watcher, and telling them apart matters more than tidy output.
echo "mutate-check: mutant in a sandbox copy, baseline on the real tree at its real path"
echo "  suite: $SUITE"
echo "  file:  $FILE_ABS"

# THE SANDBOX MIRRORS THE REPO, it does not flatten it. The suite resolves its
# repo root by walking up for a .git marker and by parents[N] arithmetic, so a
# flat copy silently changes what "the repo" means and reds cases that have
# nothing to do with the mutation.
SUITE_REL="$(realpath --relative-to="$REPO_ROOT" "$SUITE_DIR")"
mkdir -p "$SANDBOX_ROOT/$SUITE_REL"
cp -a "$SUITE_DIR/." "$SANDBOX_ROOT/$SUITE_REL/"
# Working artifacts from previous runs must not ride along into the sandbox.
rm -f "$SANDBOX_ROOT/$SUITE_REL"/.*-run-snapshot.sh 2>/dev/null || true
# A real .git marker, because "outside a repo" is exactly what broke case 191.
if ! git -C "$SANDBOX_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$SANDBOX_ROOT" init -q .
    : >"$SANDBOX_ROOT/.mutate-check-seed"
    git -C "$SANDBOX_ROOT" add .mutate-check-seed >/dev/null 2>&1
    git -C "$SANDBOX_ROOT" -c user.email=mutate@check -c user.name=mutate-check \
        commit -q -m "sandbox seed" >/dev/null 2>&1
fi

SB_FILE="$SANDBOX_ROOT/$SUITE_REL/$(basename "$FILE_ABS")"
if ! FROM="$FROM" TO="$TO" python3 - "$SB_FILE" <<'PY'; then
import os, pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
frm, to = os.environ["FROM"], os.environ["TO"]
if frm not in s:
    sys.stderr.write(
        "MUTATION DID NOT APPLY: the --from string is not present in %s.\n"
        "This is a HARD ERROR, not a warning. A no-op mutation produces a GREEN\n"
        "mutant, which reads exactly like 'the check does not detect this' and\n"
        "would be indistinguishable from a real finding.\n"
        "  wanted: %r\n" % (p, frm[:200])
    )
    sys.exit(1)
p.write_text(s.replace(frm, to, 1))
print("  mutation applied to the sandbox copy")
PY
    rm -rf "$SANDBOX_ROOT"
    exit 2
fi

MUT_LOG="$SANDBOX_ROOT/mutant.log"
REAL_LOG="$SANDBOX_ROOT/baseline.log"

echo "== pass 1: MUTANT (defect planted) =="
bash "$SANDBOX_ROOT/$SUITE_REL/$SUITE_BASE" >"$MUT_LOG" 2>&1
MUT_RC=$?
echo "  mutant exit=$MUT_RC"

echo "== pass 2: BASELINE (untouched real tree) =="
bash "$SUITE" >"$REAL_LOG" 2>&1
REAL_RC=$?
echo "  baseline exit=$REAL_RC"

# `^ *FAIL`, never `^FAIL`. The suite INDENTS its result lines, so the anchored
# form matches nothing and prints an empty failure list under a run that failed.
# That was this tool's own first bug, in the scratch script it replaces.
fails_in() { grep -E '^ *FAIL' "$1" 2>/dev/null; }

STATUS=0

# --expect-red NAMES A CASE, not a line of text, and that is load-bearing.
# The first version matched the caller's pattern against FAIL lines in the
# mutant and the SAME pattern against PASS lines in the baseline. A suite's
# pass() and fail() word the same case differently, so any pattern satisfying
# one check necessarily failed the other: the interface could never be
# satisfied at all. Caught on the tool's second real invocation, which reported
# PROVED NOTHING about a case that was in fact behaving perfectly.
MUT_MISSING=()
for cid in "${EXPECT_RED[@]}"; do
    if ! fails_in "$MUT_LOG" | grep -qE "^ *FAIL: ${cid}\b"; then
        MUT_MISSING+=("$cid")
    fi
done

REAL_NOT_GREEN=()
for cid in "${EXPECT_RED[@]}"; do
    if grep -qE "^ *FAIL: ${cid}\b" "$REAL_LOG" 2>/dev/null ||
        ! grep -qE "^ *PASS: ${cid}\b" "$REAL_LOG" 2>/dev/null; then
        REAL_NOT_GREEN+=("$cid")
    fi
done

echo
if [[ ${#MUT_MISSING[@]} -gt 0 && ${#REAL_NOT_GREEN[@]} -eq 0 ]]; then
    echo "FAIL: the mutant did NOT go red on: ${MUT_MISSING[*]}"
    # BEFORE blaming the check, rule out the likeliest author error. A suite's
    # pass() and fail() emit DIFFERENT text for the same case, and an author
    # naturally writes the label they see when the case is GREEN. The pattern
    # then matches a PASS line in the baseline and no FAIL line in the mutant,
    # which is indistinguishable from "the check does not detect this" unless
    # you say it out loud. Cost this tool's own author one full run on its very
    # first real invocation.
    MISLABEL=0
    for cid in "${MUT_MISSING[@]}"; do
        tok="${cid%% *}"
        [[ -n "$tok" ]] || continue
        hits="$(fails_in "$MUT_LOG" | grep -E "^ *FAIL: ${tok}\b" | head -3)"
        if [[ -n "$hits" && "$tok" != "$cid" ]]; then
            MISLABEL=1
            echo "  YOU PASSED PROSE, NOT A CASE ID. --expect-red names a case, and"
            echo "  the mutant DID red case '$tok':"
            sed 's/^/      /' <<<"$hits" | cut -c1-140
            echo "  Re-run with --expect-red '$tok'."
        fi
    done
    if [[ "$MISLABEL" -eq 0 ]]; then
        echo "  The check does not detect this defect. Either the mutation is not the"
        echo "  one the check guards against, or the check cannot fire at all."
    fi
    STATUS=1
fi

if [[ ${#MUT_MISSING[@]} -eq 0 && ${#REAL_NOT_GREEN[@]} -gt 0 ]]; then
    echo "FAIL: PROVED NOTHING. The mutant went red, but so did the baseline, on:"
    echo "  ${REAL_NOT_GREEN[*]}"
    echo "  A case that can never pass goes red under EVERY mutation, including a"
    echo "  no-op one, so its red is not evidence about the defect. Fix the case"
    echo "  first, then re-run. This is the exact failure this tool exists to catch."
    STATUS=1
fi

if [[ ${#MUT_MISSING[@]} -gt 0 && ${#REAL_NOT_GREEN[@]} -gt 0 ]]; then
    echo "FAIL: neither direction held. Mutant not red on: ${MUT_MISSING[*]}"
    echo "      Baseline not green on: ${REAL_NOT_GREEN[*]}"
    STATUS=1
fi

if [[ "$REAL_RC" -ne 0 ]]; then
    echo "FAIL: the baseline suite exited $REAL_RC on the untouched tree."
    fails_in "$REAL_LOG" | head -10
    STATUS=1
fi

# Everything the mutation reddened BEYOND the expected cases. Reported whether
# or not the run is otherwise fine, because unexpected blast radius is a finding.
OTHER="$(fails_in "$MUT_LOG")"
for pat in "${EXPECT_RED[@]}"; do
    OTHER="$(grep -vE "$pat" <<<"$OTHER")"
done
OTHER="$(grep -vE '^\s*$' <<<"$OTHER")"
if [[ -n "$OTHER" ]]; then
    echo "NOTE: the mutation also reddened cases you did not name. This is not"
    echo "  automatically wrong (a real guard often has more than one case), but"
    echo "  it is blast radius you should have expected:"
    sed 's/^/    /' <<<"$OTHER" | head -10
fi

if [[ "$STATUS" -eq 0 ]]; then
    echo "OK: mutant red on every named case, baseline green. Both directions hold."
    echo "  logs kept at $SANDBOX_ROOT"
    exit 0
fi

echo "  logs kept for inspection: $MUT_LOG and $REAL_LOG"
exit 1

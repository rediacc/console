#!/bin/bash
# What the media gate tests actually EXECUTE, per module, measured rather than believed.
#
#   .ci/media/coverage.sh            report every module
#   .ci/media/coverage.sh --min N    also exit 1 if any module is below N percent
#   .ci/media/coverage.sh --uncovered <module>   list the lines nothing reached
#   .ci/media/coverage.sh --only <test-name>     measure ONE gate test rather than all ten
#
# WHY THIS EXISTS, AND WHAT IT IS NOT. The eight module gate tests were written subject by
# subject, and each one argues in its header for the properties it asserts. What no header
# can say is how much of its module those properties TOUCH. A file can have a confident
# test suite, a green gate and a hundred lines that no test has ever run, and the way that
# is discovered today is that one of those lines is wrong in production.
#
# This is a PROBE, not a gate, and the distinction is deliberate. A coverage percentage is
# the classic metric that gets optimised instead of used: a test that runs a line without
# asserting anything about it moves this number exactly as much as one that pins its
# behaviour, so a threshold here would reward the wrong work. The number is for a person
# deciding where the next test should go. `--min` exists so the driver can pin a floor if
# they decide the trade is worth it; nothing in this repository passes it today.
#
# HOW IT MEASURES. bash's own xtrace, turned on INSIDE the shells that run the modules by
# verify.sh's MEDIA_COVERAGE_FILE seam, with PS4 carrying BASH_SOURCE and LINENO and the
# trace going to its own file descriptor. No external tool, no instrumentation of the
# modules, and nothing that needs docker, node, a GPU or a network.
#
# THE FIRST DESIGN WAS WRONG AND THE REASON IS WORTH KEEPING. It exported SHELLOPTS=xtrace
# around each gate test, which is the obvious way to trace a whole process tree. Measured
# 2026-09-06: EIGHT of the ten media gate tests then failed. Not because tracing broke them,
# but because media_run_module captures merged stdout and stderr into LAST_OUT and the
# behaviour cases assert on that text -- so the probe was writing into the thing being
# measured, and then reporting the resulting truncated coverage as if it were a fact about
# the tests. A probe that perturbs its subject and reports the perturbed number is worse
# than no probe. The seam version writes to a descriptor nothing captures, and
# test-media-docs.sh asserts that a traced run and an untraced one produce the same verdict.
#
# ONLY THE REAL FILES ARE COUNTED, and that is why media-entry.sh reads 0 percent even
# though several tests drive a whole ./run.sh through it. Those tests run a sandbox COPY,
# and media_chain_probe PLANTS A LINE inside the copy before running it, which shifts every
# line number after the plant. Counting the copy would attribute execution to whatever line
# happened to land at that offset in the original -- a number that looks like coverage and
# is not. So a module exercised only through the chain reads zero here, and that reads
# correctly as "no test runs this file itself", which is a true and useful thing to know.
#
# THE DENOMINATOR IS A LOWER BOUND, stated plainly rather than buried. It counts lines that
# are not blank, not comments, and not a lone closing token (`}`, `fi`, `done`, `esac`,
# `else`, `;;`), because those never appear in a trace and counting them would make every
# module look worse than it is. It still over-counts: a function's `name() {` header line
# does not execute when the function is DEFINED, and a `local x` inside a function that is
# never called is unreachable rather than untested. So a module at 70 percent has covered
# at least 70 percent, and probably somewhat more.

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$MEDIA_DIR/../.." && pwd)"
GATES="$ROOT_DIR/.ci/scripts/test/gates"

MIN=""
UNCOVERED=""
# --only exists so the probe's own machinery can be gated cheaply. A full run drives all ten
# media gate tests, which is far too slow for `npm run ci`; test-media-docs.sh measures one
# fast test and asserts that the result is non-vacuous, which is what keeps this file from
# rotting into a script that reports zeroes and is never read.
ONLY="*"
while [ $# -gt 0 ]; do
    case "$1" in
        --min)
            MIN="$2"
            shift 2
            ;;
        --uncovered)
            UNCOVERED="$2"
            shift 2
            ;;
        --only)
            ONLY="$2"
            shift 2
            ;;
        *)
            echo "Usage: .ci/media/coverage.sh [--min <percent>] [--uncovered <module.sh>]" >&2
            exit 1
            ;;
    esac
done

TRACE_DIR="$(mktemp -d)"
trap 'rm -rf "$TRACE_DIR"' EXIT

# THE SUBJECT MODULES, which is not the same as *.sh in this folder. verify.sh is the test
# support library and coverage.sh is this file; measuring either would be measuring the
# instrument. The list is derived rather than typed so a new module is included the day it
# lands, which is the opposite of how a hand-typed list behaves.
modules=()
for f in "$MEDIA_DIR"/*.sh; do
    case "$(basename "$f")" in
        verify.sh | coverage.sh) continue ;;
    esac
    modules+=("$(basename "$f")")
done

# RUN THE SUITE UNDER TRACE. Every media gate test, each into its own trace file, with
# failures tolerated: a red gate still produces a trace, and refusing to report coverage
# because a test is failing would make this useless in exactly the situation where it is
# most wanted. What the run's exit status was is reported at the end.
failed=()
for t in "$GATES"/test-media-$ONLY.sh; do
    [ -f "$t" ] || {
        echo "coverage: no gate test matches --only '$ONLY'" >&2
        exit 1
    }
    name="$(basename "$t" .sh)"
    # ONE TRACE FILE PER TEST, so a failing test's partial trace can be told apart from a
    # module nothing exercises. MEDIA_COVERAGE_FILE is read by verify.sh and by nothing
    # else; a gate test that does not source verify.sh (test-media-helpers.sh, deliberately,
    # since it validates the scaffolding the others stand on) simply contributes nothing.
    if ! MEDIA_COVERAGE_FILE="$TRACE_DIR/$name.trace" "$t" >/dev/null 2>&1; then
        failed+=("$name")
    fi
    : >>"$TRACE_DIR/$name.trace"
done

# executable_lines <file> -- the denominator. See the header for what it over-counts.
# `|| true` ON BOTH, and not out of superstition. Under `set -o pipefail` a grep that
# matches nothing fails the whole pipeline, and "this module has no executable lines" or
# "no test touched this module" are exactly the answers the probe exists to REPORT. Without
# these guards the script exited silently after printing its header, which is what it did
# on the first run.
executable_lines() {
    { grep -nvE '^\s*($|#)' "$1" || true; } |
        { grep -vE '^[0-9]+:\s*(\}|fi|done|esac|else|;;|\{)\s*$' || true; } | cut -d: -f1
}

# covered_lines <module> -- every line number of <module> that appeared in any trace.
covered_lines() {
    { grep -ho "|$MEDIA_DIR/$1|[0-9]*|" "$TRACE_DIR"/*.trace 2>/dev/null || true; } |
        sed 's/.*|\([0-9]*\)|$/\1/' | sort -u
}

total_exec=0
total_cov=0
worst=100
printf '%-16s %8s %8s %8s\n' MODULE LINES COVERED PERCENT
for m in "${modules[@]}"; do
    exec_file="$TRACE_DIR/$m.exec"
    cov_file="$TRACE_DIR/$m.cov"
    # LEXICAL sort, not numeric: `comm` compares byte strings and refuses input that a
    # numeric sort produced, which is not a warning it issues quietly -- it prints "file 1
    # is not in sorted order" and gives a wrong answer. Nothing below depends on the order.
    executable_lines "$MEDIA_DIR/$m" | sort -u >"$exec_file"
    covered_lines "$m" >"$cov_file"
    n_exec="$(wc -l <"$exec_file")"
    # INTERSECT, do not just count the trace. A trace line number can fall on a comment or
    # a closing brace (bash reports the line a compound command STARTED on), and counting
    # those would let coverage exceed 100 percent, which is how a metric loses its meaning
    # in one step.
    n_cov="$(comm -12 "$exec_file" "$cov_file" | wc -l)"
    pct=0
    [ "$n_exec" -gt 0 ] && pct=$((n_cov * 100 / n_exec))
    printf '%-16s %8s %8s %7s%%\n' "$m" "$n_exec" "$n_cov" "$pct"
    total_exec=$((total_exec + n_exec))
    total_cov=$((total_cov + n_cov))
    [ "$pct" -lt "$worst" ] && worst=$pct
    if [ "$UNCOVERED" = "$m" ]; then
        echo ""
        echo "lines of $m that no media gate test executed:"
        comm -23 "$exec_file" "$cov_file" | sort -n | while IFS= read -r ln; do
            printf '  %s:%s: %s\n' "$m" "$ln" "$(sed -n "${ln}p" "$MEDIA_DIR/$m")"
        done
        echo ""
    fi
done
total_pct=0
[ "$total_exec" -gt 0 ] && total_pct=$((total_cov * 100 / total_exec))
printf '%-16s %8s %8s %7s%%\n' TOTAL "$total_exec" "$total_cov" "$total_pct"

if [ "${#failed[@]}" -gt 0 ]; then
    echo ""
    echo "note: these gate tests FAILED during the measured run, so their module's number is" >&2
    echo "      a floor and nothing more: ${failed[*]}" >&2
fi

if [ -n "$MIN" ]; then
    if [ "$worst" -lt "$MIN" ]; then
        echo "coverage: the weakest module is at ${worst}%, below the requested floor of ${MIN}%" >&2
        exit 1
    fi
    echo "coverage: every module is at or above ${MIN}%"
fi

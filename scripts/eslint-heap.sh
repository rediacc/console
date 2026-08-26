#!/usr/bin/env bash
# Run eslint with a heap the machine can actually give it.
#
# WHY THIS EXISTS. `check:lint` hard-coded `--max-old-space-size=8192`. On CI
# that is right and this script keeps it. On a 6.6 GB workstation with no swap it
# is not a tuning choice, it is a guaranteed kill: node grows past what the
# kernel can back, the OOM killer takes it, and eslint dies with exit 137
# ("Killed") after roughly three minutes.
#
# TWO THINGS MADE THAT WORSE THAN A PLAIN FAILURE, both measured 2026-08-26:
#
#   1. It looks like it might work. Unlike the pyyaml/aws/ruff gaps, which exit
#      immediately and say what is missing, this burns three minutes first and
#      then reports a signal that is easy to misread -- the wrapper around it
#      exits 0 unless you check PIPESTATUS, so it can be recorded as a PASS.
#   2. While it climbs, it starves everything else on the box. The Stop hook's
#      judge timed out at 240s in exactly that window and was reported as broken;
#      it answers in 6.5s when memory is free. One resource collision, two
#      symptoms, and the second one pointed at an innocent component.
#
# THE CEILING IS UNCHANGED. This never raises the heap above the requested value,
# so CI -- which has the memory -- gets exactly what it always got, and no lint
# coverage is traded away. It only clamps DOWNWARD on a host that cannot honour
# the request, which turns a guaranteed OOM into a run that completes.
#
# Usage: eslint-heap.sh <requested-mb> <eslint args...>

set -euo pipefail

REQUESTED_MB="${1:?eslint-heap.sh: requested heap in MB is required}"
shift

# KEYED ON MemAvailable, NOT MemTotal, and the first version of this script got
# that wrong. It used 65% of TOTAL, reasoning that `available` fluctuates with
# page cache and that a reproducible OOM is easier to diagnose than an
# intermittent one. That reasoning is fine in the abstract and was wrong in
# effect: on a 6654MB box with ~2900MB already resident, 65% of total is 4325MB,
# which still exceeds what the kernel can hand out -- so it clamped, announced
# that it had protected the run, and was OOM-killed anyway. A clamp that still
# dies is worse than no clamp, because it claims to have solved the problem.
#
# What matters is what is ACTUALLY obtainable now, so this reads MemAvailable and
# leaves a reserve for everything else on the box. Variance across runs is the
# correct trade: a heap that fits usually beats one that never does.
RESERVE_MB="${ESLINT_HEAP_RESERVE_MB:-1200}"

avail_mb=""
if [[ -r /proc/meminfo ]]; then
    # MemAvailable is the kernel's own estimate of what a new allocation can get
    # WITHOUT swapping, which is exactly the question here. MemFree is not: it
    # excludes reclaimable page cache and would clamp far harder than necessary.
    avail_kb="$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo 2>/dev/null || true)"
    [[ "$avail_kb" =~ ^[0-9]+$ ]] && avail_mb=$((avail_kb / 1024))
fi

heap="$REQUESTED_MB"
if [[ "$avail_mb" =~ ^[0-9]+$ ]] && ((avail_mb > 0)); then
    cap=$((avail_mb - RESERVE_MB))
    # Never raise, only lower -- and never below a floor that could not lint
    # anything, because a heap so small it dies on the first file is not an
    # improvement on dying at the end.
    if ((cap < REQUESTED_MB)); then
        if ((cap < 1024)); then
            cap=1024
        fi
        heap="$cap"
        echo "eslint-heap: ${avail_mb}MB available; clamping the requested ${REQUESTED_MB}MB heap to ${heap}MB (reserving ${RESERVE_MB}MB) so eslint is not OOM-killed. CI is unaffected -- the request is never raised." >&2
    fi
fi

# `exec` so eslint's own exit code is this script's, with no wrapper in between
# to swallow a 137 the way the original pipeline did.
exec env NODE_OPTIONS="--max-old-space-size=${heap}" npx eslint "$@"

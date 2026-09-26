#!/bin/bash
# Run every tutorial script sequentially, in the order users encounter them,
# on one shared cluster — and fail on any non-zero exit.
#
# This is the single source of truth for tutorial-sequence validation (CI and
# local): membership and order derive from the website docs' `order:`
# frontmatter (packages/www/src/content/docs/en/tutorial-*.mdx), each mapped to
# its .ci/tutorials/tutorial-<slug>.sh. Adding, removing, or reordering a
# tutorial changes this run automatically; a doc without a script or a script
# without a doc is DRIFT and fails the run before anything executes.
#
# Cross-tutorial machine state is deliberate WITHIN one invocation: nothing is
# reset between tutorials (renet#60 escaped because every command passed alone
# and only the sequence broke). Each script owns its repo-level setup/cleanup;
# the machine, daemons, and eBPF state persist across whatever slice of the
# sequence one invocation runs.
#
# T2.16 (PLAN-ci-time-budget, D-W4): CI no longer runs one invocation over all
# 18 -- it runs `TUTORIAL_SHARD` shards in parallel, each its own freshly
# provisioned machine, so state stops carrying across a shard boundary. That
# is the operator's decision, not a proven property of the scripts: nothing
# here has verified that no tutorial-<slug>.sh still reads state only a
# specific PRECEDING tutorial leaves behind. Two tutorials the same shard's
# contiguous slice keeps adjacent still run back-to-back on one machine
# exactly as before, so an undiscovered dependency between neighbours is
# unaffected either way; one crossing a shard boundary is what a live sharded
# run is what actually proves.
#
# Environment (all optional; defaults in lib/tutorial-helpers.sh and the
# scripts themselves):
#   TUTORIAL_RDC_CMD      rdc invocation (never the bare string "rdc")
#   TUTORIAL_MACHINE_IP/_USER/_NAME, TUTORIAL_SSH_KEY
#   TUTORIAL_BACKUP_HOST/_USER        second worker (ssh-keys, delta, migration)
#   TUTORIAL_LOG_DIR      per-tutorial logs (default: mktemp -d)
#   TUTORIAL_ONLY         space-separated slugs: run just these, sequence order
#   TUTORIAL_SHARD        "i/N" (1-based): run only the i-th of N contiguous
#                          slices of the full sequence, in order. Mutually
#                          exclusive with TUTORIAL_ONLY. Balances by COUNT,
#                          not measured duration (T2.9's approach), since this
#                          lane has no recorded per-tutorial durations yet.
#
# Exit codes: 0 all green; 1 at least one tutorial failed; 2 drift/precheck/
# bad TUTORIAL_SHARD.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOCS_DIR="$CONSOLE_ROOT/packages/www/src/content/docs/en"
LOG_DIR="${TUTORIAL_LOG_DIR:-$(mktemp -d /tmp/tutorial-sequence-XXXXXX)}"
mkdir -p "$LOG_DIR"

# ── Derive the sequence from the docs (single source of truth) ──────────────
declare -a pairs=()
for doc in "$DOCS_DIR"/tutorial-*.mdx; do
    slug="$(basename "$doc" .mdx)"
    slug="${slug#tutorial-}"
    order="$(grep -m1 '^order:' "$doc" | tr -dc '0-9')"
    if [[ -z "$order" ]]; then
        echo "DRIFT: $doc has no 'order:' frontmatter" >&2
        exit 2
    fi
    pairs+=("$(printf '%03d %s' "$order" "$slug")")
done
# while-read, not mapfile: bash 3.2 / minimal-CI compat, enforced by
# .ci/scripts/security/check-commands.sh (same pattern as build-renet.sh).
sequence=()
while IFS= read -r _line; do
    [ -n "$_line" ] || continue
    sequence+=("$_line")
done < <(printf '%s\n' "${pairs[@]}" | sort | awk '{print $2}')

# ── Drift check: docs ↔ scripts must be 1:1 ────────────────────────────────
drift=0
for slug in "${sequence[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/tutorial-$slug.sh" ]]; then
        echo "DRIFT: doc tutorial-$slug.mdx has no script .ci/tutorials/tutorial-$slug.sh" >&2
        drift=1
    fi
done
for script in "$SCRIPT_DIR"/tutorial-*.sh; do
    slug="$(basename "$script" .sh)"
    slug="${slug#tutorial-}"
    if [[ ! -f "$DOCS_DIR/tutorial-$slug.mdx" ]]; then
        echo "DRIFT: script $script has no doc tutorial-$slug.mdx" >&2
        drift=1
    fi
done
[[ $drift -ne 0 ]] && exit 2

# ── Optional shard (contiguous slice of the full sequence) ──────────────────
if [[ -n "${TUTORIAL_SHARD:-}" ]]; then
    if [[ -n "${TUTORIAL_ONLY:-}" ]]; then
        echo "TUTORIAL_SHARD and TUTORIAL_ONLY are mutually exclusive" >&2
        exit 2
    fi
    if [[ ! "$TUTORIAL_SHARD" =~ ^[0-9]+/[0-9]+$ ]]; then
        echo "TUTORIAL_SHARD must be 'i/N' (1-based), got '$TUTORIAL_SHARD'" >&2
        exit 2
    fi
    shard_index="${TUTORIAL_SHARD%%/*}"
    shard_of="${TUTORIAL_SHARD##*/}"
    total=${#sequence[@]}
    if [[ "$shard_of" -lt 1 || "$shard_index" -lt 1 || "$shard_index" -gt "$shard_of" ]]; then
        echo "TUTORIAL_SHARD '$TUTORIAL_SHARD': index must be between 1 and $shard_of" >&2
        exit 2
    fi
    # Contiguous chunks, ceil(total/N): D-W4 treats every tutorial as an
    # independent unit (scripts/ci-runner/unit-enumerators.ts opsTutorialUnits
    # emits none of them with a `needs`), so balancing by COUNT is enough
    # until this lane has recorded per-tutorial durations for T2.9's
    # measured-duration balancing to use.
    chunk=$(((total + shard_of - 1) / shard_of))
    start=$(((shard_index - 1) * chunk))
    if [[ "$start" -ge "$total" ]]; then
        echo "TUTORIAL_SHARD $TUTORIAL_SHARD: shard $shard_index has no tutorials ($total total, chunk size $chunk)" >&2
        exit 2
    fi
    end=$((start + chunk))
    [[ "$end" -gt "$total" ]] && end=$total
    sequence=("${sequence[@]:$start:$((end - start))}")
fi

# ── Optional subset (sequence order preserved) ──────────────────────────────
if [[ -n "${TUTORIAL_ONLY:-}" ]]; then
    declare -a subset=()
    for slug in "${sequence[@]}"; do
        for want in $TUTORIAL_ONLY; do
            [[ "$slug" == "$want" ]] && subset+=("$slug")
        done
    done
    sequence=("${subset[@]}")
fi

# ── Precheck: local ports the selected tutorials bind on this host ──────────
# work-with-repo opens `rdc repo tunnel` on local port 3000. Failing fast with
# the owner beats a FATAL halfway through the sequence. Checked only when the
# port's tutorial is actually in the selected sequence.
declare -A PORT_NEEDED_BY=([3000]="work-with-repo")
for port in "${!PORT_NEEDED_BY[@]}"; do
    slug="${PORT_NEEDED_BY[$port]}"
    [[ " ${sequence[*]} " == *" $slug "* ]] || continue
    if command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -q ":$port "; then
        echo "PRECHECK: local port $port is busy — $slug's tunnel step will fail. Free it first." >&2
        ss -ltnp 2>/dev/null | grep ":$port " >&2 || true
        exit 2
    fi
done

# ── Run ─────────────────────────────────────────────────────────────────────
# Validation runs have no audience: zero the presentation sleeps (recordings
# never go through this driver and keep their timing). Overridable.
export TUTORIAL_FAST="${TUTORIAL_FAST:-1}"

echo "Tutorial sequence (${#sequence[@]}): ${sequence[*]}"
echo "Logs: $LOG_DIR"
overall_start=$(date +%s)
declare -a results=()
failed=0
for slug in "${sequence[@]}"; do
    log="$LOG_DIR/$slug.log"
    start=$(date +%s)
    bash "$SCRIPT_DIR/tutorial-$slug.sh" >"$log" 2>&1
    rc=$?
    dur=$(($(date +%s) - start))
    # A KILLED TUTORIAL IS NOT A TUTORIAL THAT FAILED. Without this the summary
    # table shows `rc=143` beside a normal-looking duration and reads as the
    # script's own verdict.
    if [[ $rc -gt 128 && $rc -lt 160 ]]; then
        rc_text="killed:SIG$((rc - 128))"
    else
        rc_text="$rc"
    fi
    results+=("$(printf '%-20s rc=%-12s %4ss' "$slug" "$rc_text" "$dur")")
    echo "${results[-1]}"
    if [[ $rc -ne 0 ]]; then
        failed=1
        echo "──── $slug failed; last 40 lines of $log ────"
        # Strip ANSI/OSC control sequences so CI logs stay readable.
        tail -40 "$log" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g; s/\x1b\][^\x07]*\x07//g'
        echo "──── end of $slug output ────"
    fi
done

echo
echo "Summary:"
printf '%s\n' "${results[@]}"
echo "TOTAL $(($(date +%s) - overall_start))s"
exit $failed

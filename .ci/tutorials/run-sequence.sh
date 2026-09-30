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
# provisioned machine, so state stops carrying across a shard boundary. Every
# tutorial-<slug>.sh rebuilds the config, machines and repos it uses in its own
# pre-recording setup (audited 2026-09-27), and the first green four-way run
# (CI run 36293027142, OPS Provision linux-amd64 1/4..4/4) is the live proof
# that no tutorial reads state only a preceding one leaves behind. Neighbours
# inside one shard still share a machine, as before.
#
# Environment (all optional; defaults in lib/tutorial-helpers.sh and the
# scripts themselves):
#   TUTORIAL_RDC_CMD      rdc invocation (never the bare string "rdc")
#   TUTORIAL_MACHINE_IP/_USER/_NAME, TUTORIAL_SSH_KEY
#   TUTORIAL_BACKUP_HOST/_USER        second worker (ssh-keys, delta, migration)
#   TUTORIAL_LOG_DIR      per-tutorial logs, <slug>.log and <slug>.setup.log
#                          (default: mktemp -d)
#   TUTORIAL_ONLY         space-separated slugs: run just these, sequence order
#   TUTORIAL_SHARD        "i/N" (1-based): run only the i-th of N contiguous
#                          slices of the full sequence, in order. Mutually
#                          exclusive with TUTORIAL_ONLY. Sliced by
#                          MEASURED_SHARD_SIZES below, sized from measured
#                          per-tutorial durations; by COUNT only as a fallback.
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
    # T2.9 (PLAN-ci-time-budget, spec W L10): contiguous chunks sized by MEASURED
    # duration, not by count. The per-tutorial p90s are lane-durations.json's
    # `tutorial:<slug>` units, and every shard also pays about 4.1 min outside the
    # tutorials (runner setup, ops up, the second worker).
    # scripts/gates/check-lane-budget.ts prices the slices from exactly those numbers (`--table` shows them beside measured p90s), and `--rebalance ops-tutorials` searches every contiguous split.
    # (7 2 6 1 2) over 5 shards is its best (worst leg 10.41 min): no 4-shard split fitted under 12, because the 4-shard best's last leg measured 13.2 min.
    # Regenerate with `npx tsx scripts/gates/check-lane-budget.ts --rebalance ops-tutorials --write` rather than editing the sizes by hand.
    # The sizes apply only while the sequence has exactly the tutorial count they
    # sum to AND shard_of matches; anything else (a tutorial added, removed or
    # reordered by editing the docs, or a different TUTORIAL_SHARD width) falls
    # back to the ceil(total/N) equal-count split rather than silently mis-slicing
    # a changed sequence.
    MEASURED_SHARD_SIZES=(7 2 6 1 2)
    measured_total=0
    for _sz in "${MEASURED_SHARD_SIZES[@]}"; do
        measured_total=$((measured_total + _sz))
    done
    if [[ "$shard_of" -eq "${#MEASURED_SHARD_SIZES[@]}" && "$total" -eq "$measured_total" ]]; then
        start=0
        for ((_i = 0; _i < shard_index - 1; _i++)); do
            start=$((start + MEASURED_SHARD_SIZES[_i]))
        done
        chunk=${MEASURED_SHARD_SIZES[shard_index - 1]}
    else
        chunk=$(((total + shard_of - 1) / shard_of))
        start=$(((shard_index - 1) * chunk))
    fi
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
declare -a json_entries=()
failed=0
for slug in "${sequence[@]}"; do
    log="$LOG_DIR/$slug.log"
    # The silenced pre-recording setup goes beside the cast log, so the uploaded artifact carries it. In /tmp, its default, a slow setup left no trace: run 36476055403's backup-restore spent about 164 s longer outside its push than run 36498407473's, and no file said where.
    export TUTORIAL_SETUP_LOG="$LOG_DIR/$slug.setup.log"
    start=$(date +%s)
    bash "$SCRIPT_DIR/tutorial-$slug.sh" >"$log" 2>&1
    rc=$?
    dur=$(($(date +%s) - start))
    # A KILLED TUTORIAL IS NOT A TUTORIAL THAT FAILED. Without this the summary
    # table shows `rc=143` beside a normal-looking duration and reads as the
    # script's own verdict.
    killed_signal="null"
    if [[ $rc -gt 128 && $rc -lt 160 ]]; then
        killed_signal=$((rc - 128))
        rc_text="killed:SIG$killed_signal"
    else
        rc_text="$rc"
    fi
    results+=("$(printf '%-20s rc=%-12s %4ss' "$slug" "$rc_text" "$dur")")
    echo "${results[-1]}"
    # T1.6 (PLAN-ci-time-budget): the same numbers as the printf line above, as one JSON object per tutorial rather than a column a human reads. `duration_ms` is the field name and unit `budget_report.py`'s own T1.6 producer-contract docstring names for this lane (`{"tutorials": [{"slug": str, "duration_ms": number}, ...]}`); this driver only measures whole seconds, so the value is `dur * 1000` rather than a false claim of millisecond precision. `rc`/`killed_signal` ride along as extra fields the T3.2 reader does not need but a human grepping the file might. Slugs are derived from `tutorial-*.mdx` filenames (checked earlier against the doc-driven sequence above), so none of these fields needs escaping.
    json_entries+=("$(printf '{"slug":"%s","duration_ms":%s,"rc":%s,"killed_signal":%s}' "$slug" "$((dur * 1000))" "$rc" "$killed_signal")")
    if [[ $rc -ne 0 ]]; then
        failed=1
        echo "──── $slug failed; last 40 lines of $log ────"
        # Strip ANSI/OSC control sequences so CI logs stay readable.
        tail -40 "$log" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g; s/\x1b\][^\x07]*\x07//g'
        echo "──── last 40 lines of $TUTORIAL_SETUP_LOG ────"
        tail -40 "$TUTORIAL_SETUP_LOG" 2>/dev/null | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g; s/\x1b\][^\x07]*\x07//g'
        echo "──── end of $slug output ────"
    fi
done

total=$(($(date +%s) - overall_start))
echo
echo "Summary:"
printf '%s\n' "${results[@]}"
echo "TOTAL ${total}s"

# T1.6 (PLAN-ci-time-budget): a machine-readable summary beside the human logs, in the same $LOG_DIR the OPS Provision job uploads whole as `tutorial-sequence-logs-<name>-<shard>-<sha>` (`if: always()`, so a failed or killed run still lands its partial durations). budget_report.py --refresh (T3.2) reads this rather than parsing the printf table above, which stays for a human tailing the job log.
shard_json="null"
[[ -n "${TUTORIAL_SHARD:-}" ]] && shard_json="\"$TUTORIAL_SHARD\""
json_list=""
if [[ ${#json_entries[@]} -gt 0 ]]; then
    json_list="$(
        IFS=,
        echo "${json_entries[*]}"
    )"
fi
printf '{"shard":%s,"total_seconds":%s,"tutorials":[%s]}\n' \
    "$shard_json" "$total" "$json_list" >"$LOG_DIR/tutorial-durations.json"

exit $failed

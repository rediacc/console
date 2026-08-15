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
# Cross-tutorial machine state is deliberate: nothing is reset between
# tutorials (renet#60 escaped because every command passed alone and only the
# sequence broke). Each script owns its repo-level setup/cleanup; the machine,
# daemons, and eBPF state persist across the whole sequence.
#
# Environment (all optional; defaults in lib/tutorial-helpers.sh and the
# scripts themselves):
#   TUTORIAL_RDC_CMD      rdc invocation (never the bare string "rdc")
#   TUTORIAL_MACHINE_IP/_USER/_NAME, TUTORIAL_SSH_KEY
#   TUTORIAL_BACKUP_HOST/_USER        second worker (ssh-keys, delta, migration)
#   TUTORIAL_S3_ENDPOINT/_ACCESS_KEY/_SECRET_KEY/_BUCKET   backup-restore
#   TUTORIAL_LOG_DIR      per-tutorial logs (default: mktemp -d)
#   TUTORIAL_ONLY         space-separated slugs: run just these, sequence order
#
# Exit codes: 0 all green; 1 at least one tutorial failed; 2 drift/precheck.

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

# ── Drafts: a script may declare itself not-yet-runnable ────────────────────
# A tutorial whose feature was removed cannot be run and must not be silently
# deleted either: the docs<->scripts 1:1 drift check above exists precisely to
# stop a tutorial from vanishing unnoticed. A TUTORIAL_DRAFT marker in the
# script is the honest middle: the file stays, the reason stays with it, and
# the sequence skips it LOUDLY rather than reporting a pass it did not earn.
declare -a runnable=()
for slug in "${sequence[@]}"; do
    if grep -q '^# TUTORIAL_DRAFT:' "$SCRIPT_DIR/tutorial-$slug.sh"; then
        echo "SKIP (draft): $slug -- $(grep -m1 '^# TUTORIAL_DRAFT:' "$SCRIPT_DIR/tutorial-$slug.sh" | cut -c19-)" >&2
        continue
    fi
    runnable+=("$slug")
done
sequence=("${runnable[@]}")

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
    results+=("$(printf '%-20s rc=%-3s %4ss' "$slug" "$rc" "$dur")")
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

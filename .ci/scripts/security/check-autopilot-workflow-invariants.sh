#!/bin/bash
# Static invariants over .github/workflows/autopilot.yml, the workflow that
# hands a model a shell over PR-authored code. Each invariant is a structural
# expression of a rule from docs/ci-overhaul/03-v2-autonomy.md; a violation
# means the SECURITY design is broken, not that a style rule is bent.
#
#   wall4-comment-missing        every job's FIRST checkout must be the
#   trusted-checkout-not-first   trusted ref (rediacc/console @ main) with an
#                                explicit WALL 4 comment: on workflow_run the
#                                action's .claude/ restore never fires while
#                                .claude/hooks/** still execute (wall 4).
#   persist-credentials          every checkout must set persist-credentials:
#                                false; a persisted bearer string in
#                                .git/config is exfiltratable by the model.
#   event-interpolation-in-run   no ${{ github.event.* }} inside run: blocks;
#                                untrusted payload text must ride env:.
#   token-in-gate                the gate decides with zero write capability.
#   token-before-model           THE core invariant: no app-token step at or
#                                before the model step, so no write token ever
#                                exists in the model's environment.
#   track-progress-armed         track_progress must stay the literal 'false':
#                                it hard-errors on workflow_run and its
#                                tag-mode fetch is the credentialed path.
#   cancel-in-progress-armed     cancel-in-progress must stay false: never
#                                kill a round mid-push.
#
# Env: WORKFLOW_FILE overrides the target so the gate test can drive every
# invariant against mutated copies. Exit 0 clean, 1 violation, 2 setup error.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

WORKFLOW_FILE="${WORKFLOW_FILE:-$ROOT_DIR/.github/workflows/autopilot.yml}"

# Anti-vacuity: a missing workflow means the gate checked nothing, and that
# must never read as green.
if [[ ! -f "$WORKFLOW_FILE" ]]; then
    log_error "INVARIANT-FAIL: workflow-missing: no file at $WORKFLOW_FILE (nothing to check cannot pass)"
    exit 1
fi

FAILED=0
fail() {
    log_error "INVARIANT-FAIL: $1"
    FAILED=1
}

# The awk below walks the file once and emits structured findings; keeping the
# analysis in one pass means job/step attribution cannot drift between checks.
findings="$(awk '
function stepname() { return (job "/" (current_step == "" ? "<unnamed>" : current_step)) }
BEGIN { job = "<top>"; in_jobs = 0; in_run = 0; run_indent = 0 }
{
    line = $0
    sub(/\r$/, "", line)
    match(line, /^ */)
    indent = RLENGTH
    stripped = substr(line, indent + 1)
    is_comment = (substr(stripped, 1, 1) == "#")

    # Leaving a run block scalar: any line at or above the run: key indent.
    if (in_run && line !~ /^[[:space:]]*$/ && indent <= run_indent) in_run = 0

    # Track the current job (2-space keys under jobs:) and step name.
    if (line ~ /^jobs:/) { in_jobs = 1 }
    else if (in_jobs && line ~ /^  [A-Za-z_][A-Za-z0-9_-]*:[[:space:]]*$/ && !is_comment) {
        job = stripped; sub(/:.*/, "", job)
        current_step = ""; seen_checkout[job] = 0
    }
    if (!is_comment && line ~ /^[[:space:]]*-[[:space:]]+(name|uses):/) {
        current_step = stripped
        marker_indent = indent
    }

    # Inside a run: block, payload interpolation is the injection surface.
    if (in_run && !is_comment && line ~ /github\.event\./) {
        printf "event-interpolation-in-run\t%d\t%s\n", NR, stepname()
    }
    if (!is_comment && line ~ /^[[:space:]]*run:[[:space:]]*[|>]/) { in_run = 1; run_indent = indent }

    # A pending checkout is judged the moment its STEP ends: any new step
    # marker, or any dedent to at or above the marker indent. Step keys
    # (with:, id:) and with-block contents all sit deeper than the marker.
    if (pending && line !~ /^[[:space:]]*$/ && !is_comment) {
        if (indent > step_ind && stripped !~ /^- /) {
            if (line ~ /persist-credentials:[[:space:]]*false/) has_persist = 1
            if (line ~ /repository:[[:space:]]*rediacc\/console/) has_repo = 1
            if (line ~ /ref:[[:space:]]*main[[:space:]]*$/) has_main = 1
            next
        }
        if (!has_persist) printf "persist-credentials\t%d\t%s\n", checkout_line, checkout_job
        if (checkout_first && !(has_repo && has_main)) printf "trusted-checkout-not-first\t%d\t%s\n", checkout_line, checkout_job
        pending = 0
    }

    # Checkout steps: first one per job must be the trusted ref, and every one
    # must carry persist-credentials: false within its with-block.
    if (!is_comment && line ~ /uses:.*actions\/checkout@/) {
        seen_checkout[job]++
        checkout_line = NR; checkout_job = job; checkout_first = (seen_checkout[job] == 1)
        has_persist = 0; has_repo = 0; has_main = 0; pending = 1; step_ind = marker_indent
        next
    }

    # Token ordering: record where app-token and the model action appear.
    if (!is_comment && line ~ /uses:.*\.github\/actions\/app-token/) {
        if (!(job in first_token)) first_token[job] = NR
    }
    if (!is_comment && line ~ /uses:.*claude-code-action@/) {
        if (!(job in model_line)) model_line[job] = NR
    }

    # track_progress: only the quoted or bare literal false is tolerable.
    if (!is_comment && line ~ /track_progress:/ && line !~ /track_progress:[[:space:]]*.false.[[:space:]]*$/ && line !~ /track_progress:[[:space:]]*false[[:space:]]*$/) {
        printf "track-progress-armed\t%d\t%s\n", NR, stepname()
    }
    if (!is_comment && line ~ /cancel-in-progress:/ && line !~ /cancel-in-progress:[[:space:]]*false[[:space:]]*$/) {
        printf "cancel-in-progress-armed\t%d\t%s\n", NR, job
    }
}
END {
    if (pending) {
        if (!has_persist) printf "persist-credentials\t%d\t%s\n", checkout_line, checkout_job
        if (checkout_first && !(has_repo && has_main)) printf "trusted-checkout-not-first\t%d\t%s\n", checkout_line, checkout_job
    }
    for (j in first_token) {
        if (j == "gate") printf "token-in-gate\t%d\t%s\n", first_token[j], j
        if ((j in model_line) && first_token[j] < model_line[j]) printf "token-before-model\t%d\t%s\n", first_token[j], j
    }
    # A model job with NO app-token at all is fine (tokenless job); a gate job
    # is judged above. Emit a marker so the caller can assert coverage.
    printf "scanned-jobs\t0\t%d\n", length(seen_checkout)
}
' "$WORKFLOW_FILE")"

scanned="$(awk -F'\t' '$1 == "scanned-jobs" { print $3 }' <<<"$findings")"
if [[ -z "$scanned" || "$scanned" -eq 0 ]]; then
    fail "workflow-missing: no jobs parsed from $WORKFLOW_FILE (a blind scan cannot pass)"
fi

while IFS=$'\t' read -r kind line where; do
    [[ -z "$kind" || "$kind" == "scanned-jobs" ]] && continue
    fail "$kind: $WORKFLOW_FILE:$line ($where)"
done <<<"$findings"

# The Wall 4 comment is required IN the file: the trusted-first-checkout rule
# above must stay explained at the point of use, not by folklore.
if ! grep -q 'WALL 4' "$WORKFLOW_FILE"; then
    fail "wall4-comment-missing: no 'WALL 4' comment explains the trusted checkout ($WORKFLOW_FILE)"
fi

if ((FAILED != 0)); then
    log_error "autopilot workflow invariants FAILED (docs/ci-overhaul/03-v2-autonomy.md is the design source)"
    exit 1
fi
log_info "autopilot workflow invariants hold: $scanned jobs scanned, trusted checkouts first, no pre-model token, no event interpolation in run blocks"

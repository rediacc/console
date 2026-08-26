#!/usr/bin/env bash
# Nightly retry of workflow runs that failed for reasons a rerun can fix.
#
# WHY THIS EXISTS. Retry today covers Console CI ONLY, dispatched from
# ci.yml:413 into watchdog-monitor.yml, and only for the four patterns in
# WATCHDOG_RETRY_ALLOWLIST_PATTERNS. Every other workflow has none. Measured
# 2026-08-26: `Cleanup PR Preview` run 32903006150 died at the app-token step on
# GitHub's own internal DNS (internal-api.service.iad.github.net, "Name or
# service not known") before checkout, and nothing retried it. Its two cleanups
# were skipped; a human had to notice and rerun by hand.
#
# THE FILTERS ARE THE FEATURE, and the measured baseline is why. Three days of
# runs: 589 success, 230 skipped, 117 cancelled, 64 failure -- and 63 of those 64
# are watchdog-monitor.yml failing BY DESIGN (it cancels the CI run it monitors,
# then core.setFailed()s itself to signal that; the log ends `##[error]PIPELINE
# CANCELLED`). Exactly ONE genuine failure in three days. A naive "retry
# everything failed" would retry 63 deliberate failures and, if it also took
# `cancelled`, revive 117 superseded pipelines, to catch that one.
#
# Each filter below therefore removes a specific measured false positive:
#
#   failure-only     `cancelled` is the SUPERSEDED shape (a push auto-cancels
#                    the previous run). Re-running one resurrects a dead
#                    commit's pipeline.
#   not the watchdog Excluded by PATH. The display name is generated per run
#                    ("Watchdog: run <id> (gen N)"), so a name match is
#                    unwritable. Without this, 63 of 64 candidates are noise.
#   live head        A run whose head_sha is no longer any branch tip is
#                    superseded by a different route.
#   attempt cap      A genuinely broken run must not be retried every night
#                    forever.
#   age floor        So the first execution cannot reach back into history.
#
# SELF-HEALING BY CONSTRUCTION: a rerun updates the run's conclusion IN PLACE
# (verified live -- 32903006150 now reads `success attempt=2`), so a run that has
# since been fixed is simply not in the failure list any more. No state to keep.
#
# EXPECTED YIELD IS ~1 PER NIGHT, AND IT SAYS SO. A sweeper that legitimately
# retries nothing must be distinguishable from one that is broken, so the
# summary always prints what it considered and why it skipped.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: shared log_* helpers used by every housekeeping script
source "$SCRIPT_DIR/../lib/common.sh" 2>/dev/null || {
    log_info() { echo "  $*"; }
    log_warn() { echo "  WARN: $*" >&2; }
    log_step() { echo "==> $*"; }
}

REPO="${RETRY_REPO:-rediacc/console}"
MAX_AGE_HOURS="${RETRY_MAX_AGE_HOURS:-48}"
MAX_ATTEMPT="${RETRY_MAX_ATTEMPT:-3}"
MAX_RETRIES_PER_RUN="${RETRY_MAX_PER_RUN:-5}"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Excluded by PATH, never by display name. Add a path here only with the reason.
EXCLUDED_PATHS=(
    ".github/workflows/watchdog-monitor.yml" # fails by design; see the banner
)

is_excluded() {
    local p="$1" x
    for x in "${EXCLUDED_PATHS[@]}"; do
        [[ "$p" == "$x" ]] && return 0
    done
    return 1
}

log_step "Nightly retry: failed runs in $REPO (last ${MAX_AGE_HOURS}h)"

# Live branch tips, so a superseded head is recognisable. Fail CLOSED: if this
# cannot be read we cannot tell superseded from current, and retrying a
# superseded run is the expensive mistake.
LIVE_HEADS="$(gh api "repos/$REPO/branches?per_page=100" --paginate --jq '.[].commit.sha' 2>/dev/null || true)"
if [[ -z "$LIVE_HEADS" ]]; then
    log_warn "could not list branch tips; skipping rather than retrying on incomplete data"
    exit 0
fi

RUNS="$(gh api "repos/$REPO/actions/runs?status=failure&per_page=100" \
    --jq '[.workflow_runs[] | {id, name, path, head_sha, run_attempt, created_at}]' 2>/dev/null || echo '[]')"

now=$(date -u +%s)
considered=0
skip_excluded=0
skip_old=0
skip_attempt=0
skip_dead_head=0
retried=0

while IFS=$'\t' read -r id name wpath head attempt created; do
    [[ -z "$id" ]] && continue
    considered=$((considered + 1))

    if is_excluded "$wpath"; then
        skip_excluded=$((skip_excluded + 1))
        continue
    fi

    created_epoch="$(date -u -d "$created" +%s 2>/dev/null || echo 0)"
    if [[ "$created_epoch" -eq 0 ]] || ((now - created_epoch > MAX_AGE_HOURS * 3600)); then
        skip_old=$((skip_old + 1))
        continue
    fi

    if [[ "$attempt" -ge "$MAX_ATTEMPT" ]]; then
        skip_attempt=$((skip_attempt + 1))
        log_info "skip $id ($name): already at attempt $attempt; a rerun is not fixing this"
        continue
    fi

    if ! grep -qx "$head" <<<"$LIVE_HEADS"; then
        skip_dead_head=$((skip_dead_head + 1))
        continue
    fi

    if [[ "$retried" -ge "$MAX_RETRIES_PER_RUN" ]]; then
        log_warn "hit RETRY_MAX_PER_RUN=$MAX_RETRIES_PER_RUN; the rest wait for tomorrow"
        break
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] would rerun $id ($name, attempt $attempt, head ${head:0:8})"
        retried=$((retried + 1))
        continue
    fi

    if gh api -X POST "repos/$REPO/actions/runs/$id/rerun-failed-jobs" >/dev/null 2>&1; then
        log_info "reran $id ($name, was attempt $attempt)"
        retried=$((retried + 1))
    else
        # A run still winding down answers 403 "already running" -- not an
        # error worth failing the job over, and it will be picked up tomorrow.
        log_warn "could not rerun $id ($name); likely still in progress"
    fi
done < <(echo "$RUNS" | jq -r '.[] | [.id, .name, .path, .head_sha, .run_attempt, .created_at] | @tsv')

# ALWAYS report the breakdown. "0 retried" is the EXPECTED nightly outcome on
# this repo's measured baseline, and it must not look like a broken sweeper.
log_info "considered=$considered excluded=$skip_excluded too-old=$skip_old \
attempt-capped=$skip_attempt dead-head=$skip_dead_head retried=$retried"
[[ "$retried" -eq 0 ]] && log_info "nothing to retry -- on this repo's baseline that is the normal night"
exit 0

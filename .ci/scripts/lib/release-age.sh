#!/bin/bash
# Release-age freshness deferral — shared rule for the CI dependency gates.
#
# A freshly-published dependency/advisory-fix is not actionable the instant it
# ships: bumping to it churns the tree for a version that is a few hours old.
# Instead of failing a gate the moment a version crosses a flat 24h line (which
# makes fresh releases trickle in one-at-a-time all day), we DEFER a version
# until the next UTC midnight after it has aged the base window. Effect: every
# version that becomes eligible on a given UTC day is released together at the
# following 00:00 UTC, so a day's upgrades surface as one batch, not hourly.
#
#   eligibleAt = startOfNextUtcDay(publishedAt + window)   # window default 24h
#   deferred   = now < eligibleAt          # effective age 24-48h
#
# NOTE: the base window is read from `.npmrc` `minimum-release-age` (minutes).
# That key is our CI-gate knob; it is NOT npm's native install guard (npm's real
# key is `min-release-age`, in days). See .npmrc for the follow-up note.
#
# Consumed by: .ci/scripts/security/audit.sh, .ci/scripts/quality/check-go-deps.sh.
# The TypeScript twin lives in scripts/check-deps.ts (partitionByReleaseAge);
# keep the two in sync.

# Guard against double-sourcing.
[[ -n "${__RELEASE_AGE_SH_SOURCED:-}" ]] && return 0
readonly __RELEASE_AGE_SH_SOURCED=1

# Repo root = three levels up from .ci/scripts/lib/.
__RELEASE_AGE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

# Default base window if .npmrc has no minimum-release-age (24h).
readonly RELEASE_AGE_DEFAULT_WINDOW_SECONDS=86400

# release_age_window_seconds
# Prints the base freshness window in seconds. Reads `minimum-release-age`
# (minutes) from the repo .npmrc; falls back to RELEASE_AGE_DEFAULT_WINDOW_SECONDS.
release_age_window_seconds() {
    local minutes
    minutes=$(grep -E '^[[:space:]]*minimum-release-age[[:space:]]*=[[:space:]]*[0-9]+' \
        "$__RELEASE_AGE_REPO_ROOT/.npmrc" 2>/dev/null | head -1 | grep -oE '[0-9]+' | head -1)
    if [[ -n "$minutes" && "$minutes" -gt 0 ]]; then
        echo $((minutes * 60))
    else
        echo "$RELEASE_AGE_DEFAULT_WINDOW_SECONDS"
    fi
}

# release_eligible_epoch <publish_epoch> [window_seconds]
# Prints the epoch (UTC seconds) at which a version published at <publish_epoch>
# becomes eligible: 00:00:00 UTC of the day AFTER (publish + window).
release_eligible_epoch() {
    local publish_epoch="$1"
    local window="${2:-$(release_age_window_seconds)}"
    local aged=$((publish_epoch + window))
    # Midnight of the day AFTER the day that (publish+window) falls in.
    date -u -d "$(date -u -d "@$aged" +%Y-%m-%d) +1 day" +%s
}

# is_release_deferred <publish_epoch> [now_epoch] [window_seconds]
# Exit 0 (deferred) when now < eligibleAt; exit 1 (eligible/installable) otherwise.
# An empty/unparseable publish_epoch is treated as DEFERRED (fail-closed): a
# lookup hiccup must never turn into a false "must upgrade" gate failure.
is_release_deferred() {
    local publish_epoch="$1"
    local now="${2:-$(date -u +%s)}"
    local window="${3:-$(release_age_window_seconds)}"
    if [[ -z "$publish_epoch" || ! "$publish_epoch" =~ ^[0-9]+$ ]]; then
        return 0
    fi
    local eligible
    eligible=$(release_eligible_epoch "$publish_epoch" "$window")
    ((now < eligible))
}

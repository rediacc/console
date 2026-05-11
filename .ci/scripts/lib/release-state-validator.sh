#!/bin/bash
# Release-state validator library.
#
# Single source of truth for the sentinel-based release-commit contract:
#
#   Committed(v${V}) ⇔
#       cli/v${V}/.released      exists
#     ∧ desktop/v${V}/.released  exists (when desktop artifacts were produced)
#     ∧ git tag v${V}            exists
#
# Channel pointers (latest.json, manifest.json, Packages.gz, etc.) only ever
# reference committed versions. `.released` sentinels are the commit markers;
# they are written LAST, after every CI gate has passed. A prefix that is
# non-empty but missing its sentinel is an orphan from a cancelled run and is
# always safe to scrub.
#
# Sourced by:
#   .ci/scripts/quality/check-release-state.sh           (the BLOCKER drift gate)
#   .ci/scripts/deploy/upload-to-r2.sh                   (pre-upload orphan scrub)
#   .ci/scripts/deploy/write-release-sentinel.sh         (commit-phase writer)
#   .ci/scripts/housekeeping/cleanup-versions.sh         (Phase 8d orphan sweep)
#   .github/workflows/cleanup-on-ci-cancel.yml           (belt-and-suspenders)
#
# The library is pure-bash and makes AWS / git calls lazily. Callers that want
# to test the assertion logic should feed `rsv_assert_bijection` synthetic
# version lists rather than shimming AWS.

[[ -n "${__RELEASE_STATE_VALIDATOR_SH_SOURCED:-}" ]] && return 0
readonly __RELEASE_STATE_VALIDATOR_SH_SOURCED=1

RSV_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"
RSV_SENTINEL_KEY=".released"

# Pre-contract floor: tags strictly older than the oldest CLI sentinel on R2
# are excluded from the bijection check. The sentinel contract was introduced
# in PR #459; everything before the first cli sentinel was sealed by the older
# prefix-based guard and has no `.released` marker.
#
# The floor is data-derived at runtime (see rsv_pre_contract_floor /
# rsv_assert_bijection) so we never need to hand-edit a baseline as releases
# advance. RSV_GRANDFATHER_BEFORE remains as an OVERRIDE-ONLY escape hatch:
# tests pin a synthetic floor with it; in production no one should set it.
# If you find yourself reaching for this knob, the right move is almost
# always to backfill the missing sentinel via
# .github/workflows/backfill-release-sentinel.yml instead.

# =============================================================================
# Live probes (AWS + git)
# =============================================================================

# List every `.released` sentinel under `${product}/v*/` on R2.
# Emits one `v${VERSION}` per line, semver-sorted. Empty stdout when there
# are no sentinels yet (callers under `set -euo pipefail` would otherwise
# trip on grep's exit-1-on-no-match through the pipefail option).
# Requires: AWS env + R2_ENDPOINT.
rsv_list_sentinels() {
    local product="${1:?product (cli|desktop) required}"
    {
        aws s3api list-objects-v2 \
            --bucket "$RSV_BUCKET" \
            --prefix "${product}/v" \
            --endpoint-url "$R2_ENDPOINT" \
            --query "Contents[?ends_with(Key, \`/${RSV_SENTINEL_KEY}\`)].Key" \
            --output text 2>/dev/null |
            tr '\t' '\n' |
            sed -n "s|^${product}/\(v[0-9][0-9.]*\)/${RSV_SENTINEL_KEY}\$|\1|p" |
            grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' |
            sort -uV
    } || true
}

# List every strict-semver git tag (v${X}.${Y}.${Z}); pre-release tags skipped.
# Empty stdout if no semver tags exist (avoids tripping pipefail).
rsv_list_git_tags() {
    {
        git tag -l 'v*' |
            grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' |
            sort -uV
    } || true
}

# `0` if the R2 prefix contains at least one object.
rsv_prefix_nonempty() {
    local prefix="${1:?prefix required}"
    local count
    count="$(aws s3api list-objects-v2 \
        --bucket "$RSV_BUCKET" \
        --prefix "$prefix" \
        --max-items 1 \
        --endpoint-url "$R2_ENDPOINT" \
        --query 'KeyCount' \
        --output text 2>/dev/null || echo 0)"
    [[ "$count" != "0" && "$count" != "None" ]]
}

# `0` if `${product}/${version}/.released` exists on R2.
rsv_sentinel_exists() {
    local product="${1:?product required}"
    local version="${2:?version required}"
    aws s3api head-object \
        --bucket "$RSV_BUCKET" \
        --key "${product}/${version}/${RSV_SENTINEL_KEY}" \
        --endpoint-url "$R2_ENDPOINT" \
        >/dev/null 2>&1
}

# `0` if the versioned prefix is an orphan: bytes present, no sentinel.
# Orphans are always safe to scrub.
rsv_is_orphan() {
    local product="${1:?product required}"
    local version="${2:?version required}"
    rsv_prefix_nonempty "${product}/${version}/" &&
        ! rsv_sentinel_exists "$product" "$version"
}

# Fetch and emit the JSON payload of `${product}/${version}/.released`.
# Empty stdout if the sentinel does not exist.
rsv_get_sentinel_payload() {
    local product="${1:?product required}"
    local version="${2:?version required}"
    aws s3 cp "s3://${RSV_BUCKET}/${product}/${version}/${RSV_SENTINEL_KEY}" - \
        --endpoint-url "$R2_ENDPOINT" 2>/dev/null || true
}

# =============================================================================
# Pre-contract floor (where the sentinel contract starts)
# =============================================================================

# Return the pre-contract floor: the oldest version still subject to the
# bijection check. Versions strictly older than this floor predate the
# sentinel contract (or had their sentinels scrubbed before R2 lifecycle
# could re-seal them) and are excluded from bijection.
#
# Three inputs combine:
#   1. The OBSERVED floor: oldest CLI sentinel in the supplied list. Reflects
#      R2's current state.
#   2. The RATCHET file (.ci/config/release-contract-floor.txt): a monotonic
#      high-water mark stored in git. Every successful release advances it
#      after the sentinel is written; nothing decreases it. Prevents the
#      "operator scrubs the oldest CLI sentinel and the observed floor
#      silently moves up" regression -- the ratchet still pins the floor
#      where it was, and drift fires.
#   3. The OVERRIDE env var RSV_GRANDFATHER_BEFORE: takes precedence over
#      both. Tests pin synthetic floors with it; production should never
#      set it.
#
# Floor = max(observed, ratchet) when both are present.
#
# Why CLI-only for the observed half: every post-contract release writes the
# cli sentinel last (see write-release-sentinel.sh). Desktop is optional;
# git tags include pre-contract history. The cli sentinel is the only signal
# that unambiguously dates the contract's start.
rsv_pre_contract_floor() {
    local cli_versions="${1:-}"
    if [[ -n "${RSV_GRANDFATHER_BEFORE:-}" ]]; then
        printf '%s\n' "$RSV_GRANDFATHER_BEFORE"
        return 0
    fi
    local observed="" ratchet="" floor=""
    observed="$(printf '%s\n' "$cli_versions" |
        grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' |
        sort -uV |
        head -1)"
    local floor_file="${RSV_FLOOR_FILE:-}"
    if [[ -z "$floor_file" ]]; then
        # Try a few candidate locations: repo root (where check-release-state
        # runs), the script's own ../.. (when invoked from another tool).
        local script_dir candidate
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        for candidate in \
            "${REPO_ROOT:-}/.ci/config/release-contract-floor.txt" \
            "${script_dir}/../../config/release-contract-floor.txt" \
            ".ci/config/release-contract-floor.txt"; do
            if [[ -n "$candidate" && -f "$candidate" ]]; then
                floor_file="$candidate"
                break
            fi
        done
    fi
    if [[ -n "$floor_file" && -f "$floor_file" ]]; then
        ratchet="$(grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' "$floor_file" | head -1 || true)"
    fi
    if [[ -z "$observed" ]]; then
        printf '%s\n' "${ratchet:-}"
        return 0
    fi
    if [[ -z "$ratchet" ]]; then
        printf '%s\n' "$observed"
        return 0
    fi
    # max(observed, ratchet) -- only advances, never retreats.
    floor="$(printf '%s\n%s\n' "$observed" "$ratchet" | sort -V | tail -1)"
    printf '%s\n' "$floor"
}

# =============================================================================
# Assertion (pure; no I/O — feed strings)
# =============================================================================

# Assert the bijection: for every strict-semver version seen in any of the
# three inputs, require either all three (committed) or none (absent). Desktop
# sentinel is optional but must not appear without a matching cli sentinel
# (desktop ⇒ cli is an invariant of the writer).
#
# Usage:
#   rsv_assert_bijection <cli_versions> <desktop_versions> <tag_versions> [in_flight]
#
# Each input is a newline-separated list of `v${X}.${Y}.${Z}` values. Callers
# should usually feed the outputs of rsv_list_sentinels / rsv_list_git_tags.
# `in_flight` is the one version currently being built by this CI run; it is
# excluded so the gate does not false-positive on its own in-flight release.
#
# Stdout: human-readable DRIFT lines, one finding per line, followed by an
# `OK` line when there is no drift.
# Exit: 0 on bijection, 1 on any drift finding.
rsv_assert_bijection() {
    local cli_versions="$1"
    local desktop_versions="$2"
    local tag_versions="$3"
    local in_flight="${4:-}"

    # Pre-contract floor: drop every version strictly older than the oldest
    # CLI sentinel (the canonical first-write of the contract). The floor
    # itself stays in scope so its own bijection is checked.
    #
    # If the override env var is set we honour it (tests pin a synthetic
    # floor with it). Otherwise the floor is derived from the actual cli
    # sentinel set we were handed.
    #
    # Empty floor means we have neither sentinels nor an override: the
    # contract isn't in effect for this state at all (e.g. a fresh dev
    # bucket). Short-circuit to OK so we don't false-positive on every old
    # tag in repo history.
    local floor
    floor="$(rsv_pre_contract_floor "$cli_versions")"
    if [[ -z "$floor" ]]; then
        echo "OK: release-state bijection holds — no cli sentinels yet (contract not in effect)"
        return 0
    fi

    rsv_drop_pre_contract() {
        local input="$1"
        local v oldest
        while IFS= read -r v; do
            [[ -z "$v" ]] && continue
            # Keep v iff v sorts equal-or-after floor.
            [[ "$v" == "$floor" ]] && { printf '%s\n' "$v"; continue; }
            oldest="$(printf '%s\n%s\n' "$floor" "$v" | sort -V | head -1)"
            [[ "$oldest" == "$floor" ]] && printf '%s\n' "$v"
        done <<<"$input"
    }
    cli_versions="$(rsv_drop_pre_contract "$cli_versions")"
    desktop_versions="$(rsv_drop_pre_contract "$desktop_versions")"
    tag_versions="$(rsv_drop_pre_contract "$tag_versions")"

    local all drift=0
    all="$(printf '%s\n%s\n%s\n' "$cli_versions" "$desktop_versions" "$tag_versions" |
        grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' |
        sort -uV)"

    # Associative-array sets give O(1) membership tests; grep-per-version
    # scaled as O(N^2) across the full release history.
    declare -A cli_set=() desktop_set=() tag_set=()
    local v
    while IFS= read -r v; do
        [[ -n "$v" ]] && cli_set["$v"]=1
    done <<<"$cli_versions"
    while IFS= read -r v; do
        [[ -n "$v" ]] && desktop_set["$v"]=1
    done <<<"$desktop_versions"
    while IFS= read -r v; do
        [[ -n "$v" ]] && tag_set["$v"]=1
    done <<<"$tag_versions"

    local version has_cli has_desktop has_tag
    while IFS= read -r version; do
        [[ -z "$version" ]] && continue
        [[ -n "$in_flight" && "$version" == "$in_flight" ]] && continue

        has_cli=0
        has_desktop=0
        has_tag=0
        [[ -n "${cli_set[$version]:-}" ]] && has_cli=1
        [[ -n "${desktop_set[$version]:-}" ]] && has_desktop=1
        [[ -n "${tag_set[$version]:-}" ]] && has_tag=1

        if ((has_cli != has_tag)); then
            if ((has_cli)); then
                echo "DRIFT ${version}: cli sentinel present, git tag missing"
                echo "  remediation: re-run CD to tag/release ${version}, or scrub the sentinel via scripts/dev/scrub-sentinel.sh ${version}"
            else
                echo "DRIFT ${version}: git tag present, cli sentinel missing"
                echo "  remediation: re-run CI to produce artifacts for ${version}, or delete tag ${version}"
            fi
            drift=1
        fi

        if ((has_desktop && !has_cli)); then
            echo "DRIFT ${version}: desktop sentinel present, cli sentinel missing"
            echo "  remediation: inspect desktop/${version}/.released payload and reconcile; desktop should never release without cli"
            drift=1
        fi
    done <<<"$all"

    if ((drift == 0)); then
        echo "OK: release-state bijection holds (floor: ${floor}, in-flight: ${in_flight:-<none>})"
        return 0
    fi
    return 1
}

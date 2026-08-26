#!/bin/bash
# Release-state validator library.
#
# Single source of truth for the sentinel-based release-commit contract:
#
#   Committed(v${V}) ⇔
#       cli/v${V}/.released      exists
#     ∧ git tag v${V}            exists
#
# Channel pointers (latest.json, manifest.json, Packages.gz, etc.) only ever
# reference committed versions. `.released` sentinels are the commit markers;
# they are written LAST, after every CI gate has passed. A prefix that is
# non-empty but missing its sentinel is an orphan from a cancelled run. Orphans
# are reaped ONLY by the nightly housekeeping job (off the release path); the
# release-time upload no longer scrubs them — it overwrites in place — so a
# retried/cancelled in-flight release can never have its just-staged binaries
# deleted out from under it.
#
# Sourced by:
#   .ci/scripts/quality/check-release-state.sh           (the BLOCKER drift gate)
#   .ci/scripts/deploy/upload-to-r2.sh                   (idempotent write guard; no scrub)
#   .ci/scripts/deploy/write-release-sentinel.sh         (commit-phase writer; refuses empty)
#   .ci/scripts/test/assert-r2-sentinel.sh               (post-upload binaries-present gate)
#   .ci/scripts/housekeeping/cleanup-versions.sh         (Phase 8d orphan sweep, nightly only)
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
    local product="${1:?product (cli) required}"
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

# `0` if the R2 prefix contains at least one object, `1` if it is empty, and
# `2` if the question could not be answered.
#
# THREE STATES, DELIBERATELY. This used to end in `|| echo 0`, collapsing "the
# prefix is empty" and "R2 is unreachable" into the same answer. Release-state
# validation is exactly the place that must not confuse those two: "no objects
# under this version prefix" is the signal for a scrubbed or corrupt release,
# and reporting it because a credential expired would condemn a healthy release.
rsv_prefix_nonempty() {
    local prefix="${1:?prefix required}"
    local count err rc=0
    err="$(mktemp)"
    count="$(aws s3api list-objects-v2 \
        --bucket "$RSV_BUCKET" \
        --prefix "$prefix" \
        --max-items 1 \
        --endpoint-url "$R2_ENDPOINT" \
        --query 'KeyCount' \
        --output text 2>"$err")" || rc=$?
    if ((rc != 0)); then
        log_error "rsv_prefix_nonempty: list-objects-v2 failed for s3://${RSV_BUCKET}/${prefix} (exit $rc)"
        [[ -s "$err" ]] && sed 's/^/    /' "$err" >&2
        rm -f "$err"
        return 2
    fi
    rm -f "$err"
    [[ "$count" != "0" && "$count" != "None" ]]
}

# Count objects under a versioned prefix EXCLUDING the `.released` sentinel,
# i.e. the actual release binaries. Echoes a non-negative integer (0 when the
# prefix is empty or holds only the sentinel). Used to distinguish a healthy
# sealed release (sentinel + binaries) from the corrupt "sealed-but-empty"
# state (sentinel only, binaries scrubbed). A versioned prefix holds far fewer
# than the 1000-key list page, so no pagination is needed.
#
# Returns non-zero and emits nothing when the count could not be obtained.
# `|| echo 0` here meant an unreachable bucket produced the same "0" as a
# scrubbed prefix, and 0 is precisely the value callers act on: it is the
# "sealed-but-empty" signal that write-release-sentinel.sh and upload-to-r2.sh
# use to refuse a release. Callers run under `set -e`, so a failed probe now
# aborts them instead of feeding them a fabricated zero.
rsv_binary_count() {
    local prefix="${1:?prefix required}"
    local count err rc=0
    err="$(mktemp)"
    count="$(aws s3api list-objects-v2 \
        --bucket "$RSV_BUCKET" \
        --prefix "$prefix" \
        --endpoint-url "$R2_ENDPOINT" \
        --query "length(Contents[?ends_with(Key, \`/${RSV_SENTINEL_KEY}\`) == \`false\`] || \`[]\`)" \
        --output text 2>"$err")" || rc=$?
    if ((rc != 0)); then
        log_error "rsv_binary_count: list-objects-v2 failed for s3://${RSV_BUCKET}/${prefix} (exit $rc)"
        [[ -s "$err" ]] && sed 's/^/    /' "$err" >&2
        rm -f "$err"
        return 1
    fi
    rm -f "$err"
    # "None" is how list-objects-v2 spells a genuinely absent prefix.
    [[ "$count" == "None" ]] && count=0
    if ! [[ "$count" =~ ^[0-9]+$ ]]; then
        log_error "rsv_binary_count: unparseable count '$count' for s3://${RSV_BUCKET}/${prefix}"
        return 1
    fi
    echo "$count"
}

# `0` sealed, `1` genuinely absent, `2` COULD NOT TELL.
#
# The third code is the point. This used to be a bare `>/dev/null 2>&1`, so
# expired credentials, a 5xx, and a DNS failure all returned the same "1" as a
# genuinely missing sentinel -- a confident "this release is not sealed" from a
# probe that never ran. Its two siblings above (rsv_prefix_nonempty:92,
# rsv_binary_count) already return 2 with a logged reason on a probe failure;
# this one was the odd one out.
#
# Bounded consequences TODAY, which is why it survived: write_once_guard fails
# open toward "proceed with the upload", the safe direction. But any caller
# asking "is this sealed?" for a DIFFERENT purpose gets a wrong answer with no
# hint that anything failed, and a `if rsv_sentinel_exists ...` caller is
# unaffected by this change because 2 is falsy just as 1 was.
rsv_sentinel_exists() {
    local product="${1:?product required}"
    local version="${2:?version required}"
    local err rc=0
    err="$(mktemp)"
    aws s3api head-object \
        --bucket "$RSV_BUCKET" \
        --key "${product}/${version}/${RSV_SENTINEL_KEY}" \
        --endpoint-url "$R2_ENDPOINT" \
        >/dev/null 2>"$err" || rc=$?
    if ((rc == 0)); then
        rm -f "$err"
        return 0
    fi
    # A 404 is the only failure that means "absent". Anything else means the
    # question was not answered, and an unanswered question is not a `no`.
    if grep -qiE '404|Not Found|NoSuchKey' "$err"; then
        rm -f "$err"
        return 1
    fi
    log_error "rsv_sentinel_exists: could not determine whether ${product}/${version}/${RSV_SENTINEL_KEY} exists (exit $rc); this is NOT evidence that it is missing"
    [[ -s "$err" ]] && sed 's/^/    /' "$err" >&2
    rm -f "$err"
    return 2
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
#      to the new oldest CLI sentinel; nothing decreases it. The ratchet
#      protects the all-sentinels-empty case (mass scrub or misconfigured
#      probe): when observed is empty but the ratchet remembers a version,
#      bijection still runs against the ratchet floor instead of silently
#      short-circuiting to OK.
#
#      It does NOT catch the "oldest CLI sentinel was scrubbed in isolation"
#      case -- when observed advances past the scrubbed version, max(observed,
#      ratchet) == observed and the scrubbed version falls below the floor
#      (grandfathered). Catching that regression would require recording
#      every cli sentinel ever observed and diffing on every check, not just
#      a single high-water mark; the cost / value trade-off didn't justify
#      that complexity for a tooling we trust to gate manual scrubs already.
#   3. The OVERRIDE env var RSV_GRANDFATHER_BEFORE: takes precedence over
#      both. Tests pin synthetic floors with it; production should never
#      set it.
#
# Floor = max(observed, ratchet) when both are present.
#
# Why CLI-only for the observed half: every post-contract release writes the
# cli sentinel last (see write-release-sentinel.sh). Git tags include
# pre-contract history. The cli sentinel is the only signal that
# unambiguously dates the contract's start.
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

# Assert the bijection: for every strict-semver version seen in either input,
# require both (committed) or neither (absent) — a cli sentinel and its git tag
# must appear together.
#
# Usage:
#   rsv_assert_bijection <cli_versions> <tag_versions> [in_flight]
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
    local tag_versions="$2"
    local in_flight="${3:-}"

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
            [[ "$v" == "$floor" ]] && {
                printf '%s\n' "$v"
                continue
            }
            oldest="$(printf '%s\n%s\n' "$floor" "$v" | sort -V | head -1)"
            [[ "$oldest" == "$floor" ]] && printf '%s\n' "$v"
        done <<<"$input"
    }
    cli_versions="$(rsv_drop_pre_contract "$cli_versions")"
    tag_versions="$(rsv_drop_pre_contract "$tag_versions")"

    local all drift=0
    all="$(printf '%s\n%s\n' "$cli_versions" "$tag_versions" |
        grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' |
        sort -uV)"

    # Associative-array sets give O(1) membership tests; grep-per-version
    # scaled as O(N^2) across the full release history.
    declare -A cli_set=() tag_set=()
    local v
    while IFS= read -r v; do
        [[ -n "$v" ]] && cli_set["$v"]=1
    done <<<"$cli_versions"
    while IFS= read -r v; do
        [[ -n "$v" ]] && tag_set["$v"]=1
    done <<<"$tag_versions"

    local version has_cli has_tag
    while IFS= read -r version; do
        [[ -z "$version" ]] && continue
        [[ -n "$in_flight" && "$version" == "$in_flight" ]] && continue

        has_cli=0
        has_tag=0
        [[ -n "${cli_set[$version]:-}" ]] && has_cli=1
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
    done <<<"$all"

    if ((drift == 0)); then
        echo "OK: release-state bijection holds (floor: ${floor}, in-flight: ${in_flight:-<none>})"
        return 0
    fi
    return 1
}

# Assert that a CHANNEL POINTER names a version that actually got a git tag.
#
# THE RELATION THE BIJECTION DOES NOT COVER. rsv_assert_bijection reconciles
# sentinels against tags -- both of which a `bump-none` merge correctly skips.
# The channel pointer (`cli/<ch>/latest.json` and `cli/<ch>/manifest.json`) was
# advanced ANYWAY, so it could name a version with no tag, no GitHub Release,
# and a 404 release-notes URL, and nothing in this library would notice.
#
# It happened three times (PRs #573, #574, #576, all bump-none, all resolving to
# 1.3.1) and would have half-applied a production release across eu/us/asia on
# 2026-09-01, because promote-stable reads the manifest and then checks out
# `ref: v<version>`.
#
# PURE, deliberately: the caller does the R2 and git reads, this only judges
# them. `aws` is not installable on the maintainer's host or in the devbox, so
# an I/O-coupled assertion here would be untestable locally -- which is how a
# release gate ends up unverified.
#
# Usage:
#   rsv_assert_channel_pointer_tagged <channel> <latest_ver> <manifest_ver> <tag_versions> [in_flight]
#
# Exit: 0 when the pointer is consistent and tagged, 1 on any finding.
rsv_assert_channel_pointer_tagged() {
    local channel="${1:?channel required}"
    local latest_ver="${2-}"
    local manifest_ver="${3-}"
    local tag_versions="${4-}"
    local in_flight="${5-}"
    local drift=0

    # An unreadable pointer is NOT a clean channel. Both files are written
    # seconds apart by the same uploader, so a missing one means the read
    # failed or the write tore -- either way the question was not answered.
    if [[ -z "$latest_ver" || -z "$manifest_ver" ]]; then
        echo "DRIFT ${channel}: could not read the channel pointer (latest='${latest_ver:-<empty>}' manifest='${manifest_ver:-<empty>}'); an unreadable pointer is never a pass"
        return 1
    fi

    # They are written back to back. Disagreement means a torn write, and
    # different consumers then resolve to different versions: install.sh reads
    # latest.json, the updater reads manifest.json.
    if [[ "$latest_ver" != "$manifest_ver" ]]; then
        echo "DRIFT ${channel}: latest.json says '${latest_ver}' but manifest.json says '${manifest_ver}'. They are written seconds apart, so this is a torn write, and install.sh (latest.json) and the auto-updater (manifest.json) will disagree."
        drift=1
    fi

    # The in-flight version legitimately has no tag yet: the pointer for release
    # X is written before X's tag is pushed. Excluding it is what makes this
    # relation safe to run on the release path at all.
    if [[ -n "$in_flight" && "$latest_ver" == "$in_flight" ]]; then
        ((drift == 0)) && echo "OK: ${channel} pointer names the in-flight version ${latest_ver} (tag not expected yet)"
        return "$drift"
    fi

    local v found=0
    while IFS= read -r v; do
        [[ "$v" == "$latest_ver" ]] && {
            found=1
            break
        }
    done <<<"$tag_versions"

    if ((found == 0)); then
        echo "DRIFT ${channel}: the channel pointer names '${latest_ver}', which has NO git tag. Every rdc on this channel auto-updates to a build whose releaseNotesUrl 404s, and promote-stable will later check out 'ref: ${latest_ver}' and fail AFTER the R2 and Docker halves have already succeeded."
        drift=1
    fi

    ((drift == 0)) && echo "OK: ${channel} pointer names ${latest_ver}, which is tagged"
    return "$drift"
}

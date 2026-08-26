#!/bin/bash
# CI Initialization Script
# Consolidates early CI checks: secrets validation, bot detection, submodule init, tag generation
#
# Usage: .ci/scripts/ci/initialize.sh [options]
#
# Options:
#   --check-only    Only run validation checks, skip tag generation
#   --output FILE   Write outputs to file (GitHub Actions format)
#
# Environment variables:
#   GITHUB_PAT          - Token for private repo access (required)
#   GITHUB_EVENT_NAME   - Event type (push, pull_request, etc.)
#   GITHUB_ACTOR        - GitHub username
#   COMMIT_AUTHOR       - Commit author name (for bot detection)
#
# Outputs (written to --output file or stdout):
#   is_bot=true|false
#   renet_tag=<hash>
#   web_tag=<hash>
#   image_tag=<hash>
#   renet_exists=true|false
#   web_exists=true|false

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

CHECK_ONLY="${ARG_CHECK_ONLY:-false}"
OUTPUT_FILE="${ARG_OUTPUT:-}"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Helper to write output
write_output() {
    local key="$1"
    local value="$2"
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "${key}=${value}" >>"$OUTPUT_FILE"
    fi
    echo "${key}=${value}"
}

# =============================================================================
# Step 1: Validate GH_PAT secret
# =============================================================================
log_step "Validating required secrets..."

if [[ -z "${GITHUB_PAT:-}" ]]; then
    log_error "ERROR: GITHUB_PAT is required but not set"
    log_error "This repository requires private submodule access."
    log_error "Configure the GH_PAT secret in: Settings > Secrets and variables > Actions"
    log_error "Required scopes: repo, write:packages"
    exit 1
fi
log_info "GH_PAT secret is configured"

# =============================================================================
# Step 2: Check if commit is from bot
# =============================================================================
log_step "Checking commit author..."

IS_BOT="false"
COMMIT_AUTHOR="${COMMIT_AUTHOR:-}"
EVENT_NAME="${GITHUB_EVENT_NAME:-}"

if [[ "$EVENT_NAME" == "push" ]] && [[ -n "$COMMIT_AUTHOR" ]]; then
    if [[ "$COMMIT_AUTHOR" == "github-actions[bot]" ]] || [[ "$COMMIT_AUTHOR" == "dependabot[bot]" ]]; then
        IS_BOT="true"
        log_info "Commit from bot: $COMMIT_AUTHOR - downstream jobs will be skipped"
    else
        log_info "Commit author: $COMMIT_AUTHOR"
    fi
else
    log_info "Non-push event or no author info, running CI normally"
fi

write_output "is_bot" "$IS_BOT"
# Default for every early-exit path; detect-pointer-bump.sh may overwrite with
# true below (in GITHUB_OUTPUT the last write of a key wins).
write_output "pointer_bump_only" "false"

# Exit early if bot commit or check-only mode
if [[ "$IS_BOT" == "true" ]]; then
    log_info "Bot commit detected, skipping remaining initialization"
    exit 0
fi

if [[ "$CHECK_ONLY" == "true" ]]; then
    log_info "Check-only mode, skipping submodule and tag generation"
    exit 0
fi

# =============================================================================
# Step 3: Initialize submodules
# =============================================================================
log_step "Initializing private submodules..."

# Configure git to use token for GitHub (x-access-token works for both PATs and App tokens)
git config --global url."https://x-access-token:${GITHUB_PAT}@github.com/".insteadOf "https://github.com/"

# Check if submodules are already initialized
if [[ -f "private/renet/.ci/ci.sh" ]]; then
    log_info "Submodules already initialized"
else
    # Initialize submodules
    if ! git submodule update --init --recursive private/ 2>/dev/null; then
        log_error "Failed to initialize submodules"
        exit 1
    fi

    # Verify initialization
    if [[ ! -f "private/renet/.ci/ci.sh" ]]; then
        log_error "Submodule initialization incomplete"
        exit 1
    fi
    log_info "Submodules initialized successfully"
fi

# =============================================================================
# Step 4: Pointer-bump fast-path detection (PR events only)
# =============================================================================
# Runs after submodule init so the token insteadOf rewrite (above) makes git
# fetches authenticated. Fail-safe: any error inside the detector must degrade
# to a normal full run, never fail initialize.
log_step "Detecting pointer-bump-only push..."
if ! .ci/scripts/ci/detect-pointer-bump.sh ${OUTPUT_FILE:+--output "$OUTPUT_FILE"}; then
    log_warn "detect-pointer-bump.sh errored; running full CI"
    write_output "pointer_bump_only" "false"
fi

# =============================================================================
# Step 5: Generate CI tags
# =============================================================================
log_step "Generating CI tags..."

RENET_TAG=$(.ci/scripts/ci/generate-tag.sh --submodule private/renet)
# WEB and RDC are hashed over their PRODUCERS' closure, not the console commit.
#
# `--self` made every commit invalidate BOTH images. Measured: 8b7840ed4 changed
# exactly one file, .ci/scripts/deploy/wait-for-preview-worker.sh, which is
# .dockerignore'd and which no image consumes -- and both images rebuilt, while
# renet's content-hashed tag was correctly reused.
#
# Hashing the build CONTEXT would not work: it is both smaller than the COPY
# list (.ci/scripts is excluded) and larger (.ci/docker/web is NOT excluded),
# and the biggest inputs -- www-assets, account-web-assets, cli-npm, the renet
# binaries -- arrive as downloaded artifacts and are never in the context. So
# each tag covers its artifact PRODUCERS.
#
# $RENET_TAG is folded into both because renet reaches both images as an
# artifact, never as source, so no path can cover it. RDC is NOT renet-free:
# Dockerfile.native COPYs one file, and that file is the musl SEA, which embeds
# renet for both arches.
WEB_TAG=$(.ci/scripts/ci/generate-tag.sh --closure web --extra "$RENET_TAG")
RDC_TAG=$(.ci/scripts/ci/generate-tag.sh --closure rdc --extra "$RENET_TAG")

write_output "renet_tag" "$RENET_TAG"
write_output "web_tag" "$WEB_TAG"
write_output "rdc_tag" "$RDC_TAG"
write_output "image_tag" "$RENET_TAG"

log_info "Renet tag: $RENET_TAG (renet commit)"
log_info "Web tag: $WEB_TAG (console commit)"
log_info "RDC tag: $RDC_TAG (console commit)"

# =============================================================================
# Step 6: Detect bump type and calculate next version
# =============================================================================
log_step "Detecting bump type from PR labels..."
BUMP_TYPE=$(.ci/scripts/version/detect-bump-type.sh --verbose)
log_info "Bump type: $BUMP_TYPE"
write_output "bump_type" "$BUMP_TYPE"

# =============================================================================
# Step 6b: Decide whether this commit earns a release
# =============================================================================
# WHY THE DECISION MOVED HERE. It used to live in finalize-release-sentinel,
# which `needs: ci-complete` -- structurally DOWNSTREAM of stage-artifacts, the
# job that writes R2. So the answer arrived long after the uploader had already
# advanced the edge channel pointer. That is how cli/edge/manifest.json came to
# advertise 1.3.1 with no v1.3.1 tag and a 404 release-notes URL, twice (PR #573
# and PR #574, both bump-none, both resolving to the same version and
# overwriting each other's supposedly immutable bytes).
#
# This is still ONE evaluation, not two. finalize-release-sentinel now READS
# this output instead of asking again; dispatch-release.sh's --dispatch-only
# mode exists for precisely that shape, and its header says why asking twice is
# wrong (a label could move between the two answers).
#
# GITHUB_OUTPUT is deliberately cleared for the call. --decide-only would
# otherwise append skip_release=true to the file itself, making two writers for
# one fact; parsing its guaranteed single `decision:` stdout line -- a contract
# its header states explicitly -- keeps write_output the only writer here.
#
# FAIL-OPEN POLARITY IS PRESERVED. Nothing is written unless the answer is
# explicitly "skip", so a crashed, cancelled or token-starved decision yields an
# absent output, and every consumer's `!= 'true'` guard then RELEASES. A
# silently withheld release is far worse than one unnecessary release.
#
# Push-to-main only: no other event has a release to skip, and the PR lookup
# would be a wasted API call on every PR run.
if [[ "${GITHUB_EVENT_NAME:-}" == 'push' && "${GITHUB_REF:-}" == 'refs/heads/main' ]]; then
    log_step "Deciding whether this commit earns a release..."
    RELEASE_DECISION="$(GITHUB_OUTPUT='' .ci/scripts/ci/dispatch-release.sh --decide-only 2>&1 | grep '^decision:' || true)"
    log_info "Release decision: ${RELEASE_DECISION:-<undecided, will release>}"
    if [[ "$RELEASE_DECISION" == 'decision: skip' ]]; then
        write_output "skip_release" "true"
    fi
fi

log_step "Calculating next version from git tags..."
# Shallow CI checkout has no tags. Fetch ALL tags (not just reachable from HEAD)
# using the app token. The --no-recurse-submodules prevents submodule ref errors.
FETCH_URL="https://x-access-token:${GITHUB_PAT}@github.com/${GITHUB_REPOSITORY}.git"
# A SWALLOWED TAG FETCH IS A WRONG VERSION, NOT A MISSING ONE.
#
# This line used to end in `2>/dev/null || true`. A failed or rate-limited fetch
# left whatever tags the checkout happened to bring, resolve-version.sh cannot
# tell a stale tag list from a current one, and NEXT_VERSION three lines below
# came out plausible and wrong. That is the case assert-artifact-version.sh
# CANNOT catch, because CD's label and CI's label both descend from this one
# command -- they agree with each other and disagree with reality.
#
# So: retry (a rate limit is usually transient), then FAIL. Never continue on a
# tag list we could not refresh.
TAG_FETCH_ERR="$(mktemp)"
TAG_FETCH_OK=false
for attempt in 1 2 3; do
    if git fetch --tags --force --no-recurse-submodules "$FETCH_URL" 2>"$TAG_FETCH_ERR"; then
        TAG_FETCH_OK=true
        break
    fi
    log_warn "Tag fetch attempt ${attempt}/3 failed"
    if [[ "$attempt" -lt 3 ]]; then
        sleep $((attempt * 5))
    fi
done
if [[ "$TAG_FETCH_OK" != "true" ]]; then
    log_error "Could not fetch tags after 3 attempts; refusing to compute a version from a tag list that may be stale."
    # FETCH_URL embeds the app token, and git echoes the remote in its errors,
    # so git's stderr is redacted rather than printed raw.
    sed "s|${GITHUB_PAT:-__no_github_pat_set__}|***|g" "$TAG_FETCH_ERR" >&2
    rm -f "$TAG_FETCH_ERR"
    exit 1
fi
rm -f "$TAG_FETCH_ERR"

# `|| echo 'none'` never fired: git tag -l exits 0 when nothing matches, so an
# untagged repo logged an empty value rather than the intended "none".
LATEST_TAG="$(git tag -l 'v*' --sort=-v:refname | head -1)"
if [[ -z "$LATEST_TAG" ]]; then
    log_error "Tag fetch succeeded but no v* tag exists; tag-based versioning cannot derive a version here."
    log_error "Create the initial tag (git tag -a v0.0.0 -m v0.0.0 && git push origin v0.0.0) before running CI."
    exit 1
fi
log_info "Latest tag: $LATEST_TAG"
NEXT_VERSION=$(.ci/scripts/version/resolve-version.sh --bump-type "$BUMP_TYPE")
write_output "next_version" "$NEXT_VERSION"
log_info "Next version: $NEXT_VERSION (from tag: $(.ci/scripts/version/resolve-version.sh --current))"

# On push-to-main, append version to ALL image tags to invalidate CI cache.
# CI builds (pull_request/schedule events) don't embed version, CD builds
# (push event) do — different tags ensure cache miss and rebuild with correct
# version.
if [[ "${GITHUB_EVENT_NAME:-}" == "push" ]]; then
    local_tags=("RENET" "WEB" "RDC")
    log_parts=()
    for prefix in "${local_tags[@]}"; do
        var_name="${prefix}_TAG"
        new_val="${!var_name}-${NEXT_VERSION}"
        printf -v "$var_name" '%s' "$new_val"
        write_output "${prefix,,}_tag" "$new_val"
        log_parts+=("${prefix}: ${new_val}")
    done
    write_output "image_tag" "$RENET_TAG"
    log_info "Push event: versioned tags - $(
        IFS=', '
        echo "${log_parts[*]}"
    )"
fi

# =============================================================================
# Step 7: Check if images exist in registry (requires Docker)
# =============================================================================
log_step "Checking image cache in registry..."

check_image_path() {
    local path="$1"
    local tag="$2"
    if command -v docker &>/dev/null; then
        if docker manifest inspect "${path}:${tag}" &>/dev/null 2>&1; then
            echo "true"
        else
            echo "false"
        fi
    else
        # Docker not available, assume images don't exist
        echo "false"
    fi
}

# All images publish flat under ghcr.io/rediacc/<name> (renet, rdc, server).
check_image() {
    check_image_path "ghcr.io/rediacc/$1" "$2"
}

RENET_EXISTS=$(check_image "renet" "$RENET_TAG")
WEB_EXISTS=$(check_image "server" "$WEB_TAG")
RDC_EXISTS=$(check_image "rdc" "$RDC_TAG")

write_output "renet_exists" "$RENET_EXISTS"
write_output "web_exists" "$WEB_EXISTS"
write_output "rdc_exists" "$RDC_EXISTS"

log_info "renet:$RENET_TAG exists=$RENET_EXISTS"
log_info "web:$WEB_TAG exists=$WEB_EXISTS"
log_info "rdc:$RDC_TAG exists=$RDC_EXISTS"

log_info "Initialization complete"

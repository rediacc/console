#!/bin/bash
# Pre-pull public Docker base images, with retry.
#
# WHY: buildx occasionally fails to authenticate mid-build when it pulls a base
# image itself. Pulling the bases up front with `docker pull` sidesteps that,
# and a transient registry hiccup retries here instead of failing the build.
#
# This is NOT ci-pull-images.sh: that one authenticates to GHCR and pulls our
# own rediacc images. This pulls public bases and needs no credentials.
#
# Usage:
#   .ci/scripts/infra/docker-prepull.sh <ref>[=<platform>] ...
#
# Examples:
#   .ci/scripts/infra/docker-prepull.sh ubuntu:24.04=linux/amd64
#   .ci/scripts/infra/docker-prepull.sh debian:bookworm=linux/amd64 ubuntu:24.04
#
# Run locally exactly as CI does — it needs nothing but a working docker.
#
# Exits non-zero if any image cannot be pulled after 3 attempts.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

if [[ $# -eq 0 ]]; then
    log_error "No images given."
    log_error "Usage: $0 <ref>[=<platform>] ...   e.g. ubuntu:24.04=linux/amd64"
    exit 1
fi

require_cmd docker

pull_with_retry() {
    local image="$1" platform="${2:-}"
    local -a args=()
    [[ -n "$platform" ]] && args=(--platform "$platform")

    local i
    for i in 1 2 3; do
        if docker pull "${args[@]}" "$image"; then
            return 0
        fi
        if [[ $i -lt 3 ]]; then
            log_warn "Pull failed for $image ${platform:-<default>}, retrying in $((i * 30))s..."
            sleep $((i * 30))
        fi
    done

    log_error "Failed to pull $image ${platform:-<default>} after 3 attempts"
    return 1
}

failed=0
for spec in "$@"; do
    # "<ref>=<platform>" or bare "<ref>"; the ref itself may contain ':' and '/'.
    image="${spec%%=*}"
    platform=""
    [[ "$spec" == *=* ]] && platform="${spec#*=}"
    pull_with_retry "$image" "$platform" || failed=1
done

if [[ $failed -ne 0 ]]; then
    log_error "One or more base images could not be pulled"
    exit 1
fi

log_info "Pre-pulled $# base image(s)"

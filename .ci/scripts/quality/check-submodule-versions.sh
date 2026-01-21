#!/bin/bash
# Verify submodule versions match console package version.
#
# Usage: .ci/scripts/quality/check-submodule-versions.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd jq

REPO_ROOT="$(get_repo_root)"
CONSOLE_VERSION="$(jq -r '.version' "$REPO_ROOT/package.json")"

REN_VERSION_FILE="$REPO_ROOT/private/renet/cmd/renet/version.go"
MID_VERSION_FILE="$REPO_ROOT/private/middleware/middleware.csproj"

if [[ ! -f "$REN_VERSION_FILE" || ! -f "$MID_VERSION_FILE" ]]; then
    if is_ci; then
        log_error "Submodule version files not found. Ensure submodules are initialized."
        exit 1
    fi
    log_warn "Submodule version files not found, skipping check"
    exit 0
fi

REN_VERSION="$(awk -F '\"' '/const Version =/ {print $2; exit}' "$REN_VERSION_FILE")"
MID_VERSION="$(awk -F '[<>]' '/<Version>/ {print $3; exit}' "$MID_VERSION_FILE")"

if [[ -z "$REN_VERSION" || -z "$MID_VERSION" ]]; then
    log_error "Failed to parse submodule version files"
    exit 1
fi

FAILED=false
if [[ "$REN_VERSION" != "$CONSOLE_VERSION" ]]; then
    log_error "Renet version mismatch: console=$CONSOLE_VERSION renet=$REN_VERSION"
    FAILED=true
fi
if [[ "$MID_VERSION" != "$CONSOLE_VERSION" ]]; then
    log_error "Middleware version mismatch: console=$CONSOLE_VERSION middleware=$MID_VERSION"
    FAILED=true
fi

if [[ "$FAILED" == "true" ]]; then
    exit 1
fi

log_info "Submodule versions match console ($CONSOLE_VERSION)"

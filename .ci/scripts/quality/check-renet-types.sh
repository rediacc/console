#!/bin/bash
# Check that renet-generated TypeScript types are up-to-date
#
# Usage:
#   .ci/scripts/quality/check-renet-types.sh
#
# Exit codes:
#   0 - Types are up-to-date
#   1 - Stale types detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
RENET_DIR="$REPO_ROOT/private/renet"
OUTPUT_DIR="$REPO_ROOT/packages/shared/src/renet-contract/data"

cd "$REPO_ROOT"

# Marker is a FILE inside the submodule, not the directory: an uninitialised
# submodule leaves an empty directory behind, which would satisfy a directory
# marker while proving nothing about content.
require_submodule "$RENET_DIR/go.mod" "Renet submodule" || exit 0

# Build renet
log_step "Building renet..."
(cd "$RENET_DIR" && go build -o bin/renet ./cmd/renet)

# Helper function - compare files ignoring version string
compare_ignoring_version() {
    local file1="$1"
    local file2="$2"
    diff -q <(grep -v '_VERSION = ' "$file1") <(grep -v '_VERSION = ' "$file2") >/dev/null 2>&1
}

FILES=(
    "functions.generated.ts"
    "functions.schema.ts"
    "vault.generated.ts"
    "vault.schema.ts"
    "list-types.generated.ts"
    # Adding a generated file to the generator is NOT enough: this list is what
    # the gate actually compares. license-tiers.generated.ts was generated into
    # TEMP_DIR and silently ignored until it was added here, which would have
    # let it go stale forever while the gate reported "up-to-date".
    "license-tiers.generated.ts"
)

# Phase 1: Check types
log_step "Checking types freshness..."
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

VERSION=$(cd "$REPO_ROOT" && git describe --tags --always 2>/dev/null || echo "dev")
"$RENET_DIR/bin/renet" functions generate-types --output "$TEMP_DIR" --version "$VERSION"

STALE=()
for file in "${FILES[@]}"; do
    if [[ -f "$TEMP_DIR/$file" ]] && ! compare_ignoring_version "$OUTPUT_DIR/$file" "$TEMP_DIR/$file"; then
        STALE+=("$file")
    fi
done

if [[ ${#STALE[@]} -eq 0 ]]; then
    log_info "Renet types are up-to-date"
    exit 0
fi

# Check failed
log_error "Stale types detected: ${STALE[*]}"
log_error "Run: ./run.sh deploy prep"
exit 1

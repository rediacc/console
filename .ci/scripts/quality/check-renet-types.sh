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
OUTPUT_DIR="$REPO_ROOT/packages/shared/src/queue-vault/data"

cd "$REPO_ROOT"

if [[ ! -d "$RENET_DIR" ]]; then
    log_warn "Renet submodule not available, skipping"
    exit 0
fi

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
)

# Phase 1: Check types
log_step "Checking types freshness..."
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

VERSION=$(cd "$REPO_ROOT" && git describe --tags --always 2>/dev/null || echo "dev")
"$RENET_DIR/bin/renet" bridge generate-types --output "$TEMP_DIR" --version "$VERSION"

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

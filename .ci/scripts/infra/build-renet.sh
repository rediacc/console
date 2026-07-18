#!/bin/bash
# Build renet from Go source
# Usage: .ci/scripts/infra/build-renet.sh
#
# Builds the renet binary from Go source at private/renet/.
# Skips if the binary already exists. Reusable by CI jobs (ct-tests, ci-ops-test).
#
# Outputs:
#   RENET_BINARY env var (exported, and written to $GITHUB_ENV if in CI)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

source "$SCRIPT_DIR/../lib/common.sh"

# --nolicense is accepted for back-compat with the CI workflow steps that pass
# it, but it is now redundant: build.sh dev defaults to nolicense and reads the
# single knob (RDC_RENET_LICENSE=1 / RDC_BENCH=1) itself. We forward the flag so
# an explicit --nolicense still forces the choice.
BUILD_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --nolicense) BUILD_ARGS+=(--nolicense) ;;
        --license) BUILD_ARGS+=(--license) ;;
    esac
done

RENET_SRC="$CONSOLE_ROOT/private/renet"
RENET_EXT=""
case "$(uname -s)" in
    MINGW* | MSYS* | CYGWIN*) RENET_EXT=".exe" ;;
esac
RENET_BIN="$RENET_SRC/bin/renet${RENET_EXT}"

# Step 1: Verify submodule is present
if [[ ! -d "$RENET_SRC" ]]; then
    log_error "private/renet/ not found — submodule not checked out"
    log_error "Run: git submodule update --init private/renet"
    exit 1
fi

# Step 2: Skip if binary already exists
if [[ -f "$RENET_BIN" ]]; then
    log_info "Renet binary already exists: $RENET_BIN"
else
    # Step 3: Require Go
    if ! command -v go &>/dev/null; then
        log_error "Go is not installed (required for building renet)"
        log_error "Install Go from: https://go.dev/dl/"
        exit 1
    fi

    # Step 4: Build. build.sh dev owns the license decision (nolicense by
    # default; enforce on RDC_RENET_LICENSE=1 / RDC_BENCH=1); we only forward an
    # explicit --nolicense/--license if one was passed.
    log_step "Building renet from source..."
    # Guarded expansion: safe under `set -u` when BUILD_ARGS is empty.
    (cd "$RENET_SRC" && ./build.sh dev ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"})

    # Step 5: Verify binary produced
    if [[ ! -f "$RENET_BIN" ]]; then
        log_error "Renet build failed: binary not found at $RENET_BIN"
        exit 1
    fi
    log_info "Renet built successfully: $RENET_BIN"
fi

# Export RENET_BINARY
export RENET_BINARY="$RENET_BIN"

# Write to GITHUB_ENV for subsequent CI steps
if [[ -n "${GITHUB_ENV:-}" ]]; then
    echo "RENET_BINARY=$RENET_BIN" >>"$GITHUB_ENV"
    log_info "Set RENET_BINARY in GITHUB_ENV"
fi

echo "RENET_BINARY=$RENET_BIN"

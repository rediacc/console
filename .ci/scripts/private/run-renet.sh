#!/bin/bash
# Run renet CI if available
#
# Usage: .ci/scripts/private/run-renet.sh [stage]
#   Stages: all, quality, test, build (default: all)
#
# This is a thin wrapper that delegates to the renet submodule's CI script.
# If the submodule is not available, it exits cleanly with a warning.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STAGE="${1:-all}"
REPO_ROOT="$(get_repo_root)"
RENET_DIR="$REPO_ROOT/private/renet"

require_submodule "$RENET_DIR/.ci/ci.sh" "Renet submodule" || exit 0

log_step "Running renet CI (stage: $STAGE)..."
# `auto` (not a hardcoded version) so private/renet/go.mod's `toolchain`
# directive stays the single source of truth. This used to pin go1.25.10+auto
# while go.mod declared go1.25.12 — already diverged, and masked only because
# the `+auto` suffix silently upgrades. Every sibling renet script already uses
# `auto` (security.sh, deadcode.sh, run-tests.sh).
export GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"
"$RENET_DIR/.ci/ci.sh" "$STAGE"

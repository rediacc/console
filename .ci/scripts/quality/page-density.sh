#!/bin/bash
# Run the page-density gate inside the official Playwright container.
#
# Same reasoning as browser-smoke.sh next door, and deliberately the same shape: the gate
# drives a real browser, so on a bare runner it would need `npx playwright install
# --with-deps chromium` on every run and would fail differently depending on what the
# runner image happens to ship. The official image has the browser and its libraries baked
# in, so the gate behaves identically on a runner, in a devcontainer, and on a laptop.
#
# The image tag is DERIVED from the installed playwright package, never pinned by hand:
# Playwright refuses to run when the package and the browser build disagree, so bumping
# the dependency moves the image with it and cannot drift.
#
# Escape hatch: REDIACC_SMOKE_NO_DOCKER=1 runs it directly against a local Chromium.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

GATE_ARGS=("scripts/check-page-density.ts" "--selftest")

if [ "${REDIACC_SMOKE_NO_DOCKER:-0}" = "1" ] || ! command -v docker >/dev/null 2>&1; then
    if [ "${REDIACC_SMOKE_NO_DOCKER:-0}" != "1" ]; then
        echo "note: docker not found, running the gate directly (needs a local Chromium)"
    fi
    exec npx tsx "${GATE_ARGS[@]}"
fi

PW_VERSION="$(node -p "require('playwright/package.json').version")"
IMAGE="mcr.microsoft.com/playwright:v${PW_VERSION}-noble"
echo "page density: $IMAGE (tag derived from the installed playwright package)"

# --ipc=host: Chromium crashes on the default 64MB /dev/shm in a container.
exec docker run --rm --ipc=host \
    -v "$REPO_ROOT":"$REPO_ROOT" -w "$REPO_ROOT" \
    -e CI=true \
    "$IMAGE" npx tsx "${GATE_ARGS[@]}"

#!/bin/bash
# Run the browser smoke gate inside the official Playwright container.
#
# WHY A CONTAINER. The gate drives a real browser. On a bare GitHub runner that means
# `npx playwright install --with-deps chromium` on every run: slow, and it fails
# differently depending on what the runner image happens to ship. The official image has
# the browser and every system library already baked in, so the gate behaves identically
# on a runner, in a devcontainer, and on the operator's laptop.
#
# WHY mcr.microsoft.com AND NOT DOCKER HUB. Microsoft Container Registry serves this
# image anonymously and does NOT rate limit, so this needs no `docker login` and cannot
# fail with "toomanyrequests" on a busy CI day. Every authenticated pull in this repo
# goes to ghcr.io with `github.token` (see ct-install-methods.yml); neither registry
# needs Docker Hub credentials, and this gate deliberately keeps it that way.
#
# THE IMAGE TAG IS DERIVED, NEVER PINNED BY HAND. Playwright refuses to run when the npm
# package and the browser build disagree, so the tag is read from the installed package
# at run time. Bumping the dependency moves the image with it and cannot drift.
#
# Escape hatch: REDIACC_SMOKE_NO_DOCKER=1 runs it directly against a locally installed
# Chromium, which is what a developer without Docker wants.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

GATE_ARGS=("scripts/check-browser-smoke.ts" "--selftest")

if [ "${REDIACC_SMOKE_NO_DOCKER:-0}" = "1" ] || ! command -v docker >/dev/null 2>&1; then
    if [ "${REDIACC_SMOKE_NO_DOCKER:-0}" != "1" ]; then
        echo "note: docker not found, running the gate directly (needs a local Chromium)"
    fi
    exec npx tsx "${GATE_ARGS[@]}"
fi

PW_VERSION="$(node -p "require('playwright/package.json').version")"
IMAGE="mcr.microsoft.com/playwright:v${PW_VERSION}-noble"
echo "browser smoke: $IMAGE (tag derived from the installed playwright package)"

# --ipc=host: Chromium crashes on the default 64MB /dev/shm in a container.
# The workspace is mounted rather than copied so the gate sees the dist just built.
exec docker run --rm --ipc=host \
    -u "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e npm_config_cache=/tmp/.npm \
    -v "$REPO_ROOT":/work \
    -w /work \
    "$IMAGE" \
    npx tsx "${GATE_ARGS[@]}"

#!/bin/bash
# Build and push one single-arch web image variant.
#
# Single-arch on purpose: amd64 and arm64 are built by separate jobs on native
# runners (emulated arm64 builds of this image were prohibitively slow), then
# joined into a manifest later.
#
# Usage:
#   PLATFORM=linux/amd64 VARIANT=... IMAGE_PATH=... WEB_TAG=... \
#   ACCOUNT_ENTRY=... ACCOUNT_ED25519_PUBLIC_KEY=... \
#     .ci/scripts/build/buildx-push-web.sh
#
# Required env:
#   PLATFORM      linux/amd64 | linux/arm64 (also becomes the tag suffix)
#   VARIANT       Dockerfile --target
#   IMAGE_PATH    registry path, without tag
#   WEB_TAG       base tag; the pushed tag is <WEB_TAG>-<arch>
#   ACCOUNT_ENTRY build arg
# Optional env:
#   ACCOUNT_ED25519_PUBLIC_KEY   build arg (may be empty on non-release builds)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd docker
: "${PLATFORM:?PLATFORM is required (linux/amd64 or linux/arm64)}"
: "${VARIANT:?VARIANT is required}"
: "${IMAGE_PATH:?IMAGE_PATH is required}"
: "${WEB_TAG:?WEB_TAG is required}"
: "${ACCOUNT_ENTRY:?ACCOUNT_ENTRY is required}"

ARCH="${PLATFORM##*/}"

docker buildx build \
    --file Dockerfile \
    --target "$VARIANT" \
    --platform "$PLATFORM" \
    --build-arg "VITE_APP_VERSION=${WEB_TAG}" \
    --build-arg "ACCOUNT_ENTRY=${ACCOUNT_ENTRY}" \
    --build-arg "ACCOUNT_ED25519_PUBLIC_KEY=${ACCOUNT_ED25519_PUBLIC_KEY:-}" \
    --tag "${IMAGE_PATH}:${WEB_TAG}-${ARCH}" \
    --push \
    .

log_info "Pushed ${IMAGE_PATH}:${WEB_TAG}-${ARCH}"

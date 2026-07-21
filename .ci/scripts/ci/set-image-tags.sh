#!/bin/bash
# Derive the Docker image tags for a job and export them to $GITHUB_ENV.
#
# derive-image-tag.sh --env-file writes the base TAG; this then overrides the
# per-image tags with the values the `initialize` job resolved, appending the
# -amd64 suffix used by the fast (single-arch) build path.
#
# Usage:
#   IMAGE_TAG=... WEB_TAG=... RENET_TAG=... .ci/scripts/ci/set-image-tags.sh
#
# Optional env (all may be empty; empty means "leave it to derive-image-tag"):
#   IMAGE_TAG   explicit version for derive-image-tag.sh --version
#   WEB_TAG     web image tag from `initialize` (gets -amd64 appended)
#   RENET_TAG   renet image tag from `initialize` (gets -amd64 appended)
#   GITHUB_ENV  file to append the overrides to; skipped when unset

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

if [[ -n "${IMAGE_TAG:-}" ]]; then
    "$SCRIPT_DIR/derive-image-tag.sh" --version "$IMAGE_TAG" --env-file
else
    "$SCRIPT_DIR/derive-image-tag.sh" --env-file
fi

# Override individual tags from the initialize job (use the -amd64 suffix,
# which is what the fast single-arch build publishes).
if [[ -n "${GITHUB_ENV:-}" ]]; then
    [[ -n "${WEB_TAG:-}" ]] && echo "WEB_TAG=${WEB_TAG}-amd64" >>"$GITHUB_ENV"
    [[ -n "${RENET_TAG:-}" ]] && echo "RENET_TAG=${RENET_TAG}-amd64" >>"$GITHUB_ENV"
fi

log_info "Image tags set (web=${WEB_TAG:-<derived>} renet=${RENET_TAG:-<derived>})"

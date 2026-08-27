#!/usr/bin/env bash
# Run a command inside the web image (Astro + agent-browser). Shape copied deliberately from
# .ci/scripts/quality/browser-smoke.sh, which already solved this problem here.
#
#   REDIACC_NO_DOCKER=1   run on the host instead
#
# Usage: .ci/docker/run-in-web.sh <command...>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="rediacc/web:local"

if [ "${REDIACC_NO_DOCKER:-0}" = "1" ] || ! command -v docker >/dev/null 2>&1; then
    [ "${REDIACC_NO_DOCKER:-0}" = "1" ] || echo "note: docker not found, running on the host" >&2
    exec "$@"
fi

docker image inspect "$IMAGE" >/dev/null 2>&1 || {
    echo "building $IMAGE (first run only)" >&2
    docker build -t "$IMAGE" "$ROOT/.ci/docker/web"
}

case "$PWD" in
    "$ROOT" | "$ROOT"/*) WORKDIR="$PWD" ;;
    *) WORKDIR="$ROOT" ;;
esac

# --ipc=host: Chromium crashes on the default 64MB /dev/shm in a container.
# -u: outputs land owned by the caller, not root.
# The workspace is bind-mounted at its IDENTICAL host path (not /work) so callers can
# pass absolute paths and set cwd exactly as they would on the host; see
# run-in-render.sh for the trap this closes.
exec docker run --rm --ipc=host \
    -u "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e npm_config_cache=/tmp/.npm \
    -v "$ROOT":"$ROOT" \
    -w "$WORKDIR" \
    "$IMAGE" \
    "$@"

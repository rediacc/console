#!/usr/bin/env bash
# Run a command inside the render image. Shape copied deliberately from
# .ci/scripts/quality/browser-smoke.sh, which already solved this problem here.
#
# THE WORKSPACE IS MOUNTED AT ITS IDENTICAL HOST PATH, NOT AT /work. step6000_render.py
# passes ABSOLUTE host paths (the output mp4, --props, and --browser-executable pointing
# at remotion/chrome-cpu-raster.sh) and sets cwd to the remotion dir; a /work mount makes
# every one of those dangle inside the container. The chrome wrapper then resolves
# node_modules/.remotion/chrome-headless-shell relative to itself, so the SAME browser
# binary runs in both paths, against the image's system libraries.
#
# node_modules comes FROM the mounted host tree (T5: never shadow it with an image copy).
# Host and image are both glibc x86_64, and the Remotion compositor + chrome-headless-shell
# binaries are downloaded prebuilt, not compiled against the host, so sharing them across
# the boundary is safe in a way that a Python venv (absolute shebangs) is not.
#
#   REDIACC_NO_DOCKER=1   run on the host instead (needs the five fonts installed locally)
#
# Usage: .ci/docker/run-in-render.sh <command...>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="rediacc/render:local"

if [ "${REDIACC_NO_DOCKER:-0}" = "1" ] || ! command -v docker >/dev/null 2>&1; then
    [ "${REDIACC_NO_DOCKER:-0}" = "1" ] || echo "note: docker not found, running on the host" >&2
    exec "$@"
fi

docker image inspect "$IMAGE" >/dev/null 2>&1 || {
    echo "building $IMAGE (first run only)" >&2
    docker build -t "$IMAGE" "$ROOT/.ci/docker/render"
}

case "$PWD" in
    "$ROOT" | "$ROOT"/*) WORKDIR="$PWD" ;;
    *) WORKDIR="$ROOT" ;;
esac

# --ipc=host: Chromium crashes on the default 64MB /dev/shm in a container.
# -u: outputs land owned by the caller, not root.
# The workspace is bind-mounted rather than copied so the run sees the tree as it is.
exec docker run --rm --ipc=host \
    -u "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e npm_config_cache=/tmp/.npm \
    -v "$ROOT":"$ROOT" \
    -w "$WORKDIR" \
    "$IMAGE" \
    "$@"

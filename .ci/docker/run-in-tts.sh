#!/usr/bin/env bash
# Run a narration command inside the GPU image.
#
# THE SHARED GPU LEASE IS THE WHOLE POINT OF THIS WRAPPER. gpu_lock.py defaults its lease
# to /tmp/rediacc-gpu.lock, and /tmp is PER CONTAINER, so without the bind mount below a
# containerised narration job and a host one each hold their own lease, both load VoxCPM,
# and the card OOMs. Two VoxCPM jobs do not degrade, they fail.
#
# RDC_GPU_LOCK_FILE is documented in gpu_lock.py:20 as existing "for tests". Using it in
# production is a DELIBERATE widening of that contract, made here because the alternative
# is a lease that silently does not hold.
#
# THE WORKSPACE IS MOUNTED AT ITS IDENTICAL HOST PATH, NOT AT /work. The callers
# (step4000_voiceover.py, tts_bridge.py) pass ABSOLUTE host paths for the script, the
# scenes file and the output dir, and set cwd to an absolute host path. The first cut of
# this wrapper mounted the repo at /work, and every one of those paths would have failed
# inside the container with "No such file or directory". Identical-path mounting is also
# what the repo's devbox already does, and for the same reason (a worktree's gitdir link
# is absolute).
#
# ENV IS FORWARDED SELECTIVELY: `docker run` starts from an empty environment, so the
# PYTHONPATH that step4000 sets for the bridge, and any TTS_/QWEN_/VOXCPM_ knob the
# operator exported, silently vanish unless passed with -e. PYTHONPATH's host value is
# valid inside precisely because of the identical-path mount.
#
# MODEL WEIGHTS: the host's ~/.cache/huggingface is preferred when it exists (it already
# holds the ~11 GB VoxCPM2 + Qwen3-ASR + ForcedAligner set), so a containerised run does
# not re-download anything. The named volume is the fallback for a host with no cache.
#
#   REDIACC_NO_DOCKER=1   run on the host instead
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="rediacc/tts:local"
LOCK_DIR="${RDC_GPU_LOCK_DIR:-/var/tmp/rediacc-gpu}"
MODELS_VOL="${RDC_MODELS_VOLUME:-rediacc-hf-models}"
HF_CACHE="${RDC_HF_CACHE:-$HOME/.cache/huggingface}"

if [ "${REDIACC_NO_DOCKER:-0}" = "1" ] || ! command -v docker >/dev/null 2>&1; then
    [ "${REDIACC_NO_DOCKER:-0}" = "1" ] || echo "note: docker not found, running on the host" >&2
    exec "$@"
fi

mkdir -p "$LOCK_DIR"
# The lease file must be writable by the CONTAINER's uid (the caller's, via -u below).
# gpu_lock.py opens it "a+", so a root-owned leftover from a root container turns every
# narration into PermissionError at first model load. Mode 666 is deliberate: whoever
# runs a narration on this box must be able to take the same lease, or the lease
# silently splits into per-user leases and two VoxCPM loads OOM the card.
LOCK_FILE="$LOCK_DIR/rediacc-gpu.lock"
[ -e "$LOCK_FILE" ] || (
    umask 000
    : >"$LOCK_FILE"
) 2>/dev/null || true
if [ ! -w "$LOCK_FILE" ]; then
    echo "FATAL: $LOCK_FILE is not writable by uid $(id -u)." >&2
    echo "       Remove or chown it; a lease this user cannot hold protects nothing." >&2
    exit 1
fi

if [ -d "$HF_CACHE" ]; then
    MODELS_MOUNT=(-v "$HF_CACHE":/models)
else
    docker volume inspect "$MODELS_VOL" >/dev/null 2>&1 || docker volume create "$MODELS_VOL" >/dev/null
    MODELS_MOUNT=(-v "$MODELS_VOL":/models)
fi

docker image inspect "$IMAGE" >/dev/null 2>&1 || {
    echo "building $IMAGE (first run only, several GB)" >&2
    docker build -t "$IMAGE" "$ROOT/.ci/docker/tts"
}

# Only vars that are actually set are forwarded, so an unset knob stays unset inside
# rather than becoming an empty string that shadows a default.
ENV_FWD=()
while IFS= read -r name; do
    ENV_FWD+=(-e "$name")
done < <(compgen -e | grep -E '^(PYTHONPATH$|TTS_|QWEN_|VOXCPM_)' || true)

# cwd inside the container mirrors the caller's cwd when it lives under the mounted
# tree; anything else falls back to the repo root.
case "$PWD" in
    "$ROOT" | "$ROOT"/*) WORKDIR="$PWD" ;;
    *) WORKDIR="$ROOT" ;;
esac

exec docker run --rm --gpus all --ipc=host \
    -u "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e HF_HOME=/models \
    "${ENV_FWD[@]}" \
    -e RDC_GPU_LOCK_FILE=/gpulock/rediacc-gpu.lock \
    -v "$LOCK_DIR":/gpulock \
    "${MODELS_MOUNT[@]}" \
    -v "$ROOT":"$ROOT" \
    -w "$WORKDIR" \
    "$IMAGE" \
    "$@"

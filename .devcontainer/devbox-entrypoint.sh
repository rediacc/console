#!/usr/bin/env bash
# Devbox entrypoint: check that the image's user IS the host user, then drop to it.
#
# The published base bakes `vscode` at UID/GID 7111, and keeps it there because
# renet's hub runs the same image and chowns its workspaces to
# config.RediaccUID (private/renet/pkg/hub/containers.go, resolveUserIDs). A host
# operator is almost never 7111, so devbox_ensure_uid_image (.ci/lib/devbox.sh)
# runs the devbox from a thin local layer,
# rediacc/devbox:uid<UID>-gid<GID>-<base id 12>-<Dockerfile.uid sha256 12>, built
# once per operator per base image and recipe from .devcontainer/Dockerfile.uid.
# When the base's ids already match the host, the base runs as it is.
#
# THIS FILE NO LONGER RENUMBERS, and that is the point. Until 2026-09 it did the
# usermod/groupmod plus a chown of /home/vscode, /opt/openvscode-server and /go
# on every container start. After two real fixes (no mount-crossing walk, no
# unscoped `usermod -u` home chown) the walk was in its optimal form and still
# cost 441 seconds (measured 2026-09-07): overlayfs copy-up of 81,881 entries
# and 1.8 GiB from a lower layer. The readiness probe gives 60, so every fresh
# `./run.sh devbox up` reported "nothing is listening" while the container was
# still chowning. Copy-up is a property of chowning lower-layer files at run
# time, so the work moved to build time, into a layer.
#
# A MISMATCH IS A HARD STOP, not a quiet fallback. It means the container was
# created from an image that was not derived for this host (the base run
# directly, or a derived tag built for other ids), and serving from it would
# EACCES on every extension install, `go install` and the Playwright cache.
#
# The obvious shortcut -- `docker run --user $(id -u)` -- still does NOT work: as
# a uid the image knows nothing about there is no passwd entry, no home, no sudo,
# and the image's ownership is untouched.
#
# Environment (all set by .ci/lib/devbox.sh):
#   HOST_UID, HOST_GID   the operator's numeric ids
#   DOCKER_GID           host docker group gid, for the bound socket (optional)
#   DEVBOX_PORT          port openvscode-server listens on
#   DEVBOX_TERM_PORT     port ttyd listens on (optional; no terminal without it)
#   DEVBOX_WORKSPACE     directory to open (an absolute HOST path, bound 1:1)
#   CONNECTION_TOKEN     optional; when empty the server runs without a token

set -euo pipefail

CONTAINER_USER="${CONTAINER_USER:-vscode}"
HOST_UID="${HOST_UID:?HOST_UID is required}"
HOST_GID="${HOST_GID:?HOST_GID is required}"
DEVBOX_PORT="${DEVBOX_PORT:-8080}"
# No default. Empty means "this container has no terminal", which is exactly the
# state of every container created before the -term route existed, and
# devbox-autostart.sh treats it as such rather than guessing 7681 and colliding
# with whatever else holds that port.
DEVBOX_TERM_PORT="${DEVBOX_TERM_PORT:-}"
DEVBOX_WORKSPACE="${DEVBOX_WORKSPACE:?DEVBOX_WORKSPACE is required}"
CONNECTION_TOKEN="${CONNECTION_TOKEN:-}"

log() { printf '[devbox] %s\n' "$*"; }

current_uid="$(id -u "$CONTAINER_USER" 2>/dev/null || echo '')"
current_gid="$(id -g "$CONTAINER_USER" 2>/dev/null || echo '')"

if [ -z "$current_uid" ]; then
  log "ERROR: no '$CONTAINER_USER' account in this image"
  exit 1
fi

if [ "$current_uid" != "$HOST_UID" ] || [ "$current_gid" != "$HOST_GID" ]; then
  log "ERROR: $CONTAINER_USER is ${current_uid}:${current_gid} in this image, the host is ${HOST_UID}:${HOST_GID}"
  log "This container was not created from the image derived for this host."
  log "The devbox runs the image tagged uid${HOST_UID}-gid${HOST_GID}-<base id>-<recipe hash>, derived from"
  log ".devcontainer/Dockerfile.uid by devbox_ensure_uid_image. Recreate it:"
  log "  ./run.sh devbox remove && ./run.sh devbox up"
  exit 1
fi
log "$CONTAINER_USER matches the host ${HOST_UID}:${HOST_GID}"

# Docker socket access. The gid is passed numerically because docker-ce's
# postinst allocates it dynamically on the host (999, 988, ...); a numeric
# --group-add on the run side needs no matching /etc/group entry, and this
# groupadd is cosmetic so `ls -l` renders a name instead of a number.
if [ -n "${DOCKER_GID:-}" ] && [ -S /var/run/docker.sock ]; then
  if ! getent group "$DOCKER_GID" >/dev/null 2>&1; then
    groupadd -g "$DOCKER_GID" docker-host 2>/dev/null || true
  fi
  usermod -aG "$DOCKER_GID" "$CONTAINER_USER" 2>/dev/null || true
fi

if [ ! -d "$DEVBOX_WORKSPACE" ]; then
  log "ERROR: workspace $DEVBOX_WORKSPACE is not present inside the container"
  log "The repo must be bind-mounted at its identical host path."
  exit 1
fi

token_args="--without-connection-token"
if [ -n "$CONNECTION_TOKEN" ]; then
  token_args="--connection-token $CONNECTION_TOKEN"
fi

log "starting openvscode-server on :$DEVBOX_PORT for $DEVBOX_WORKSPACE"

# HOME and USER must be set explicitly. setpriv changes credentials, NOT the
# environment, so without this the server keeps root's HOME and tries to write
# /root/.openvscode-server as uid 1000 -- which fails with EACCES and leaves the
# container "running" while serving nothing. Observed exactly that.
target_home="$(getent passwd "$HOST_UID" | cut -d: -f6)"
[ -n "$target_home" ] || target_home="/home/$CONTAINER_USER"

# THE WORKSPACE IS AN OPTION, NOT A POSITIONAL ARGUMENT, and it was passed as
# one for a long time. `openvscode-server --help` (1.109.5) prints
# `Usage: openvscode-server [options]` -- there is NO `[paths]` -- so the
# trailing "$DEVBOX_WORKSPACE" was accepted and silently ignored, and every
# browser session opened on $HOME (/home/vscode) instead of the repo. VS Code's
# parser does not warn about arguments it does not understand, which is why this
# looked like it worked.
#
# `--default-folder` is the supported form. It is missing from `--help` in this
# build, so it was verified against the running binary rather than the docs:
# starting with `--default-folder=/tmp/PROBE_MARKER` and fetching `/` yields
#   "folderUri":{"path":"/tmp/PROBE_MARKER","scheme":"vscode-remote",...}
# in the served HTML. That is proof it reaches the client, not just that the
# flag was tolerated.
#
# The path stays $DEVBOX_WORKSPACE -- the host path bound 1:1 into the container
# -- so no username is baked in anywhere.
#
# TELEMETRY IS OFF, explicitly. The same --help says: "If not specified, the
# server will send telemetry until a client connects, it will then use the
# clients telemetry setting." So the default is not "off", it is "on until
# something says otherwise", and a devbox that mostly serves automation may
# never have a client that says otherwise. `--telemetry-level off` is documented
# there as equivalent to --disable-telemetry.
vscode_args="--host 0.0.0.0 --port $DEVBOX_PORT $token_args --telemetry-level off"

# Bring the HTTP services up alongside VS Code. BEFORE the exec, because the
# exec replaces this process -- anything queued after it never runs. Launched as
# the target user, not root, so nothing it writes into the bind-mounted repo
# lands as root-owned (which would then need sudo to clean up on the host).
#
# Deliberately non-fatal and non-blocking: `|| true` plus a background launch,
# so a devbox whose account server cannot start still gives you a working editor.
AUTOSTART="$(dirname "$0")/devbox-autostart.sh"
if [ -x "$AUTOSTART" ]; then
  log "dispatching service autostart (DEVBOX_AUTOSTART=${DEVBOX_AUTOSTART:-1})"
  if command -v setpriv >/dev/null 2>&1; then
    env HOME="$target_home" USER="$CONTAINER_USER" LOGNAME="$CONTAINER_USER" \
      DEVBOX_WORKSPACE="$DEVBOX_WORKSPACE" DEVBOX_TERM_PORT="$DEVBOX_TERM_PORT" \
      setpriv --reuid "$HOST_UID" --regid "$HOST_GID" --init-groups \
      "$AUTOSTART" 2>&1 | while IFS= read -r l; do log "$l"; done || true
  else
    su -s /bin/bash "$CONTAINER_USER" -c \
      "DEVBOX_WORKSPACE='$DEVBOX_WORKSPACE' DEVBOX_TERM_PORT='$DEVBOX_TERM_PORT' '$AUTOSTART'" 2>&1 |
      while IFS= read -r l; do log "$l"; done || true
  fi
fi

# --init-groups so the supplementary groups (docker) actually apply.
if command -v setpriv >/dev/null 2>&1; then
  # shellcheck disable=SC2086
  exec env HOME="$target_home" USER="$CONTAINER_USER" LOGNAME="$CONTAINER_USER" \
    setpriv --reuid "$HOST_UID" --regid "$HOST_GID" --init-groups \
    openvscode-server $vscode_args --default-folder "$DEVBOX_WORKSPACE"
fi

# shellcheck disable=SC2086
exec su -s /bin/bash "$CONTAINER_USER" -c \
  "exec openvscode-server $vscode_args --default-folder '$DEVBOX_WORKSPACE'"

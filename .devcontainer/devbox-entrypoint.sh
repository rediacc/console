#!/usr/bin/env bash
# Devbox entrypoint: make the image's user BE the host user, then drop to it.
#
# The image bakes its `vscode` user at UID/GID 7111 (.devcontainer/Dockerfile:22-24)
# and chowns three trees to it: /home/vscode, /opt/openvscode-server (extensions
# included, Dockerfile:323) and /go (Dockerfile:199). A host operator is almost
# never 7111.
#
# The obvious shortcut -- `docker run --user $(id -u)` -- does NOT work here, and
# that is worth stating because it looks like it should: as a uid the image knows
# nothing about, every extension install is EACCES, `go install` cannot write
# $GOPATH, and the Playwright cache under /home/vscode is unreadable. Overriding
# the user leaves the image's ownership untouched; remapping the user fixes it.
#
# So: start as root, renumber `vscode` to the host's uid/gid, chown exactly those
# three trees, then exec the server as that user. This is what the devcontainer
# CLI's own updateRemoteUserUID does.
#
# THE CHOWN MUST NOT CROSS A MOUNT POINT, and until 2026-09-07 it did. This file
# used to claim the chown was "bounded to three paths and takes seconds"; both
# halves were false, measured here. Six of this container's bind mounts land
# INSIDE /home/vscode (.claude, .claude.json, .config/gh, .config/rediacc,
# .gitconfig, .git-credentials), and `chown -R` walks straight through them into
# the host's home: `stat -c %d` reports 131 for /home/vscode against 2096 for
# .claude, so they are separate filesystems and the recursion descended anyway.
# On this box the host's ~/.claude is 3.9 GB across 130,004 files, all of them
# chowned by root, from inside a container, on every single devbox start.
#
# The cost was not only wasted work. The top directory is chowned on POSTORDER,
# so /home/vscode itself kept the image's 7111:7111 for as long as the walk ran,
# leaving the container user unable to traverse its own HOME: `bash -lc` printed
# "/home/vscode/.bash_profile: Permission denied" and `rdc` could not read
# ~/.config/rediacc. And because the exec of openvscode-server comes after the
# loop, the server had not started minutes in, which surfaced to the operator as
# the entirely unrelated-looking "Devbox started but nothing is listening after
# 60s".
#
# `find -xdev` stops at every mount point, which is exactly the boundary wanted:
# the image's own files get renumbered, and anything bind-mounted from the host
# keeps the ownership the host already gave it (which is already correct, since
# HOST_UID is where we are renumbering TO).
#
# -xdev ALONE IS NOT ENOUGH, and the gap is worth naming because it looks like a
# complete fix. -xdev prunes DIRECTORY descent at a mount boundary; a
# bind-mounted FILE is still an entry in a directory this walk reads, so
# .gitconfig and .git-credentials (both mounted read-only) were still visited
# and still failed. Hence the id predicate: renumber only what currently carries
# the image's ids. The host's files already carry HOST_UID, so they fall out of
# the set by construction rather than by being named, and a restart of an
# already-renumbered container now matches nothing and costs one walk.
#
# ERRORS ARE PRINTED, not discarded. The old form ended `2>/dev/null || true`,
# so the two read-only mounts it could never have chowned failed silently on
# every start; the walk is now scoped to never reach them, and if something else
# fails it needs to be seen rather than hidden.
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
  log "remapping $CONTAINER_USER from ${current_uid}:${current_gid} to ${HOST_UID}:${HOST_GID}"

  # A conflicting account at the target id means the image already has someone
  # there. Renumber ours anyway and let the collision be visible in `id`, rather
  # than silently running as the wrong user.
  if getent group "$HOST_GID" >/dev/null 2>&1; then
    log "note: gid $HOST_GID already exists in this image ($(getent group "$HOST_GID" | cut -d: -f1))"
    usermod -g "$HOST_GID" "$CONTAINER_USER"
  else
    groupmod -g "$HOST_GID" "$CONTAINER_USER"
  fi
  # `usermod -u` DOES ITS OWN RECURSIVE CHOWN of the account's home directory,
  # and that is the single most expensive thing this entrypoint did. Measured
  # 2026-09-07: `usermod -u 1000 vscode` was still running 98 seconds in, the
  # only process in the container, while the loop below had not printed a line.
  # The cause is the same mount-crossing problem the chown had -- the home
  # directory holds six bind mounts from the host, one of which is a 3.9 GB
  # ~/.claude with 130,004 files -- but usermod offers no `-xdev`, no way to
  # scope it, and no way to turn it off.
  #
  # So take the home away for the duration. usermod chowns what it finds at the
  # account's home path; point that at an empty directory and it finds nothing,
  # which leaves the renumbering to the bounded `find -xdev` walk below where it
  # belongs. `-d` without `-m` only rewrites the /etc/passwd field, it moves no
  # files.
  #
  # A failure between the two calls would leave the account pointing at the
  # scratch path, which is harmless: /etc/passwd lives in the container's own
  # writable layer, `set -e` aborts the start, and `devbox up` builds a fresh
  # container from the image rather than reusing this one.
  renumber_home="$(mktemp -d)"
  usermod -d "$renumber_home" "$CONTAINER_USER"
  usermod -u "$HOST_UID" "$CONTAINER_USER"
  usermod -d "/home/$CONTAINER_USER" "$CONTAINER_USER"
  rmdir "$renumber_home" 2>/dev/null || true

  # Bounded, deliberate: exactly the trees the image chowned to 7111, and never
  # past a mount point into the host. -h so a symlink is renumbered rather than
  # its target, which may live on the other side of one of those boundaries.
  for tree in "/home/$CONTAINER_USER" /opt/openvscode-server /go; do
    [ -d "$tree" ] || continue
    log "chown $tree"
    if ! find "$tree" -xdev \( -uid "$current_uid" -o -gid "$current_gid" \) \
         -exec chown -h "$HOST_UID:$HOST_GID" {} +; then
      log "WARNING: chown of $tree reported errors (see above); continuing"
    fi
  done
else
  log "$CONTAINER_USER already matches the host ${HOST_UID}:${HOST_GID}"
fi

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

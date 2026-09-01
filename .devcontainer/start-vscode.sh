#!/usr/bin/env bash
# Start OpenVSCode Server for browser access to this checkout.
#
# Works in three places, which is the point: inside the devcontainer image
# (where the binary is baked into /opt), on a plain Linux host, and on a
# ChromeOS/Crostini box where the browser lives outside the VM. It refuses to
# run inside GitHub Codespaces, which already provides VS Code.
#
# If the binary is missing it can install it (--install), unpacked under
# ~/.local/share/openvscode-server. Nothing is installed without being asked.
#
# Usage:
#   ./start-vscode.sh [OPTIONS] [WORKSPACE]
#
# Options:
#   --install         Download+unpack OpenVSCode Server if it is not present, then start
#   --install-only    Download+unpack and exit without starting
#   --token <token>   Connection token required by the browser (default: none)
#   --port <port>     Port to listen on (default: 8080)
#   --host <addr>     Address to bind (default: 0.0.0.0)
#   --background      Detach, log to ~/.local/state/openvscode-server.log, print the PID
#   --stop            Stop a server previously started with --background
#   --status          Report whether a server is listening on the port
#   --version <v>     Version to install; 'latest' asks GitHub (default: 1.109.5)
#   --force           Run even inside Codespaces
#   --help            Show this help
#
# Environment: PORT, WORKSPACE, HOST, OPENVSCODE_VERSION mirror the flags.
#
# Examples:
#   ./start-vscode.sh --install              # first run on a fresh machine
#   ./start-vscode.sh --background           # start detached on :8080
#   ./start-vscode.sh --port 3080 ~/other    # different port and workspace
#   ./start-vscode.sh --stop

set -euo pipefail

DEFAULT_VERSION="1.109.5"   # keep in sync with OPENVSCODE_VERSION in .devcontainer/Dockerfile
                            # `--version latest` resolves the newest release at run time

PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"
TOKEN=""
WORKSPACE="${WORKSPACE:-}"
FORCE="${FORCE:-false}"
VERSION="${OPENVSCODE_VERSION:-$DEFAULT_VERSION}"
DO_INSTALL=false
INSTALL_ONLY=false
BACKGROUND=false
ACTION=start

INSTALL_ROOT="${OPENVSCODE_HOME:-$HOME/.local/share/openvscode-server}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}"
LOG_FILE="$STATE_DIR/openvscode-server.log"
PID_FILE="$STATE_DIR/openvscode-server.pid"

show_help() { sed -n '2,/^[^#]/p' "$0" | sed '/^[^#]/d; s/^#\( \|$\)//'; }
die() { echo "ERROR: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --install)      DO_INSTALL=true; shift ;;
    --install-only) DO_INSTALL=true; INSTALL_ONLY=true; shift ;;
    --token)        TOKEN="${2:-}"; shift 2 ;;
    --port)         PORT="${2:-}"; shift 2 ;;
    --host)         HOST="${2:-}"; shift 2 ;;
    --version)      VERSION="${2:-}"; shift 2 ;;
    --background|-b) BACKGROUND=true; shift ;;
    --stop)         ACTION=stop; shift ;;
    --status)       ACTION=status; shift ;;
    --force)        FORCE=true; shift ;;
    --help|-h)      show_help; exit 0 ;;
    -*)             echo "Unknown option: $1" >&2; show_help; exit 2 ;;
    *)              WORKSPACE="$1"; shift ;;
  esac
done

# --- where to open ----------------------------------------------------------
if [ -z "$WORKSPACE" ]; then
  if WORKSPACE="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)"; then
    :
  elif [ -d /workspace ]; then
    WORKSPACE=/workspace
  else
    WORKSPACE="$PWD"
  fi
fi
[ -d "$WORKSPACE" ] || die "workspace does not exist: $WORKSPACE"

# --- how the browser reaches this box ---------------------------------------
# On ChromeOS the browser is outside the Crostini VM: localhost is not the same
# machine, but penguin.linux.test resolves to it from ChromeOS.
browser_host() {
  if [ -e /dev/.cros_milestone ] || [ "$(hostname)" = penguin ]; then
    echo "$(hostname).linux.test"
  else
    echo localhost
  fi
}

# --- lifecycle --------------------------------------------------------------
port_pid() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnpH "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1
  fi
}

case "$ACTION" in
  status)
    pid="$(port_pid)"
    if [ -n "$pid" ]; then
      echo "listening on port $PORT (pid $pid)"
      echo "  http://$(browser_host):$PORT"
      exit 0
    fi
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "process $(cat "$PID_FILE") is alive but nothing is listening on $PORT yet"
      exit 0
    fi
    echo "not running on port $PORT"
    exit 1
    ;;
  stop)
    pid=""
    [ -f "$PID_FILE" ] && pid="$(cat "$PID_FILE")"
    [ -z "$pid" ] && pid="$(port_pid)"
    [ -n "$pid" ] || die "no running server found (pid file $PID_FILE, port $PORT)"
    # `bin/openvscode-server` is a shell wrapper that runs node as a CHILD, so
    # signalling the pid we launched leaves the listener alive and the next
    # start then fails with "port already in use". Signal the process GROUP.
    # (--background uses setsid, so the group id equals the launched pid.)
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    if [ -n "$pgid" ]; then kill -TERM -- "-$pgid" 2>/dev/null || true; fi
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do [ -n "$(port_pid)" ] || break; sleep 0.25; done
    if [ -n "$(port_pid)" ]; then
      [ -n "$pgid" ] && kill -9 -- "-$pgid" 2>/dev/null || true
      kill -9 "$(port_pid)" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    if [ -n "$(port_pid)" ]; then die "port $PORT is still in use by pid $(port_pid)"; fi
    echo "stopped (pid $pid)"
    exit 0
    ;;
esac

if [ "${CODESPACES:-}" = "true" ] && [ "$FORCE" != true ]; then
  cat >&2 <<'EOF'
ERROR: running inside GitHub Codespaces.
OpenVSCode Server is redundant there: use VS Code Desktop ("Connect to
Codespace") or github.dev. Re-run with --force if you really want it.
EOF
  exit 1
fi

# --- find the binary --------------------------------------------------------
find_binary() {
  local c
  for c in \
    "${OPENVSCODE_BIN:-}" \
    "$INSTALL_ROOT/bin/openvscode-server" \
    /opt/openvscode-server/bin/openvscode-server \
    /usr/local/bin/openvscode-server; do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return 0; }
  done
  command -v openvscode-server 2>/dev/null && return 0
  return 1
}

resolve_latest_version() {
  local tag TMP_ERR
  TMP_ERR="$(mktemp)"
  # shellcheck disable=SC2064
  trap "rm -f '$TMP_ERR'" RETURN
  local body err
  err="$TMP_ERR"
  body="$(curl -fsS --retry 5 --retry-delay 3 --retry-all-errors https://api.github.com/repos/gitpod-io/openvscode-server/releases/latest 2>"$err")"
  tag="$(printf '%s' "$body" | sed -n 's/.*"tag_name"[^"]*"openvscode-server-v\([^"]*\)".*/\1/p' | head -1)"
  if [ -z "$tag" ]; then
    # Print what curl actually said. "could not resolve the latest release" on
    # its own sends the reader hunting for a version problem when the real
    # answer is usually a proxy, a rate limit, or no DNS.
    [ -s "$err" ] && sed 's/^/  curl: /' "$err" >&2
    die "could not resolve the latest release from the GitHub API; pass --version <x.y.z>"
  fi
  echo "$tag"
}

install_server() {
  local arch asset url tmp
  if [ "$VERSION" = latest ]; then
    VERSION="$(resolve_latest_version)"
    echo "Latest release resolves to v${VERSION}"
  fi
  case "$(uname -m)" in
    x86_64|amd64) arch=x64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) die "unsupported architecture $(uname -m); OpenVSCode Server ships x64 and arm64 only" ;;
  esac
  command -v curl >/dev/null 2>&1 || die "curl is required to install"
  command -v tar  >/dev/null 2>&1 || die "tar is required to install"

  asset="openvscode-server-v${VERSION}-linux-${arch}"
  url="https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v${VERSION}/${asset}.tar.gz"
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  echo "Installing OpenVSCode Server v${VERSION} (${arch}) into $INSTALL_ROOT"
  echo "  $url"
  # No pipe into tar: a 404 page piped to tar fails in a way that is hard to
  # read, and a truncated download must not half-populate the install root.
  curl -fL --retry 5 --retry-delay 3 --retry-all-errors --progress-bar -o "$tmp/server.tar.gz" "$url" \
    || die "download failed — is v${VERSION} a real release for ${arch}?"
  tar -xzf "$tmp/server.tar.gz" -C "$tmp" || die "archive did not unpack"
  [ -x "$tmp/$asset/bin/openvscode-server" ] || die "unpacked tree has no bin/openvscode-server"

  mkdir -p "$(dirname "$INSTALL_ROOT")"
  rm -rf "$INSTALL_ROOT.new"
  mv "$tmp/$asset" "$INSTALL_ROOT.new"
  rm -rf "$INSTALL_ROOT.old"
  [ -e "$INSTALL_ROOT" ] && mv "$INSTALL_ROOT" "$INSTALL_ROOT.old"
  mv "$INSTALL_ROOT.new" "$INSTALL_ROOT"
  rm -rf "$INSTALL_ROOT.old"
  echo "Installed: $INSTALL_ROOT/bin/openvscode-server"
}

BIN="$(find_binary || true)"
if [ -z "$BIN" ]; then
  if [ "$DO_INSTALL" = true ]; then
    install_server
    BIN="$(find_binary || true)"
    [ -n "$BIN" ] || die "install completed but no binary was found"
  else
    cat >&2 <<EOF
ERROR: openvscode-server is not installed on this machine.

Looked in: \$OPENVSCODE_BIN, $INSTALL_ROOT/bin, /opt/openvscode-server/bin,
/usr/local/bin, and \$PATH.

Install it (~200 MB, no root needed) with:
    $0 --install
EOF
    exit 1
  fi
elif [ "$DO_INSTALL" = true ] && [ "$INSTALL_ONLY" = true ]; then
  echo "Already installed: $BIN"
fi

[ "$INSTALL_ONLY" = true ] && exit 0

if [ -n "$(port_pid)" ]; then
  die "port $PORT is already in use (pid $(port_pid)); use --port, or --stop first"
fi

if [ -n "$TOKEN" ]; then
  TOKEN_ARGS=(--connection-token "$TOKEN")
  AUTH_DESC="token required"
else
  TOKEN_ARGS=(--without-connection-token)
  AUTH_DESC="none — anyone who can reach $HOST:$PORT gets a shell in $WORKSPACE"
fi

echo "========================================"
echo "OpenVSCode Server v${VERSION}"
echo "  Binary:    $BIN"
echo "  Workspace: $WORKSPACE"
echo "  Bind:      $HOST:$PORT"
echo "  Auth:      $AUTH_DESC"
echo "========================================"
echo "Open: http://$(browser_host):$PORT"
echo ""

if [ "$BACKGROUND" = true ]; then
  mkdir -p "$STATE_DIR"
  # setsid puts the wrapper and the node process it spawns in one process group,
  # which is what makes --stop able to take the whole thing down.
  setsid nohup "$BIN" --host "$HOST" --port "$PORT" "${TOKEN_ARGS[@]}" "$WORKSPACE" \
    >>"$LOG_FILE" 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"
  # Confirm it actually came up rather than reporting a pid that already died.
  for _ in $(seq 1 40); do
    [ -n "$(port_pid)" ] && { echo "started (pid $pid), log: $LOG_FILE"; exit 0; }
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  echo "server did not start; last log lines:" >&2
  tail -20 "$LOG_FILE" >&2
  rm -f "$PID_FILE"
  exit 1
fi

exec "$BIN" --host "$HOST" --port "$PORT" "${TOKEN_ARGS[@]}" "$WORKSPACE"

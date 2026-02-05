#!/usr/bin/env bash
# Start OpenVSCode Server for self-hosted browser access
#
# NOTE: This script is for SELF-HOSTED deployments only.
# It will exit with an error if run inside GitHub Codespaces.
#
# Usage:
#   ./start-vscode.sh [OPTIONS] [WORKSPACE]
#
# Options:
#   --token <token>   Connection token for authentication (default: none)
#   --port <port>     Port to listen on (default: 8080)
#   --force           Force run even in Codespaces (not recommended)
#   --help            Show this help message
#
# Examples:
#   ./start-vscode.sh                           # Start without auth on port 8080
#   ./start-vscode.sh --port 3080               # Start on custom port
#   ./start-vscode.sh --token mysecret          # Start with token auth
#   ./start-vscode.sh /path/to/project          # Open specific workspace

set -euo pipefail

PORT="${PORT:-8080}"
TOKEN=""
WORKSPACE="${WORKSPACE:-/workspace}"
FORCE="${FORCE:-false}"

# Detect GitHub Codespaces environment
check_codespaces() {
	if [ "${CODESPACES:-}" = "true" ] && [ "$FORCE" != "true" ]; then
		echo "========================================" >&2
		echo "ERROR: Running inside GitHub Codespaces" >&2
		echo "========================================" >&2
		echo "" >&2
		echo "OpenVSCode Server is not needed in Codespaces." >&2
		echo "GitHub already provides VS Code access via:" >&2
		echo "  - VS Code Desktop (Connect to Codespace)" >&2
		echo "  - Browser (github.dev)" >&2
		echo "" >&2
		echo "This script is for self-hosted deployments only." >&2
		echo "" >&2
		echo "To force run anyway: $0 --force" >&2
		exit 1
	fi
}

show_help() {
	cat <<EOF
OpenVSCode Server Launcher (Self-Hosted Only)

Usage: $0 [OPTIONS] [WORKSPACE]

Options:
  --token <token>   Connection token for authentication
  --port <port>     Port to listen on (default: 8080)
  --force           Force run even in Codespaces (not recommended)
  --help            Show this help message

Environment Variables:
  PORT              Default port (overridden by --port)
  WORKSPACE         Default workspace path (overridden by argument)
  CODESPACES        If 'true', script exits (use --force to override)

Examples:
  $0                              # Start without auth on port 8080
  $0 --port 3080                  # Start on custom port
  $0 --token mysecret             # Start with token auth
  $0 /path/to/project             # Open specific workspace
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
	case $1 in
	--token)
		TOKEN="$2"
		shift 2
		;;
	--port)
		PORT="$2"
		shift 2
		;;
	--force)
		FORCE="true"
		shift
		;;
	--help | -h)
		show_help
		exit 0
		;;
	-*)
		echo "Unknown option: $1" >&2
		show_help
		exit 1
		;;
	*)
		WORKSPACE="$1"
		shift
		;;
	esac
done

# Check for Codespaces before starting
check_codespaces

echo "========================================"
echo "OpenVSCode Server"
echo "========================================"
echo "  Port:      $PORT"
echo "  Workspace: $WORKSPACE"

TOKEN_ARG=""
if [ -n "$TOKEN" ]; then
	echo "  Auth:      Token required"
	TOKEN_ARG="--connection-token $TOKEN"
else
	echo "  Auth:      None (use --token for security)"
	TOKEN_ARG="--without-connection-token"
fi

echo "========================================"
echo ""
echo "Access at: http://localhost:$PORT"
echo ""

# shellcheck disable=SC2086
exec openvscode-server \
	--host 0.0.0.0 \
	--port "$PORT" \
	$TOKEN_ARG \
	"$WORKSPACE"

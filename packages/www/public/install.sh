#!/bin/bash
# Rediacc CLI Installer
#
# Install layout: single $INSTALL_DIR/rdc + $BIN_DIR/rdc symlink.
# Rollback slot is $INSTALL_DIR/rdc.old (one file, no per-version dirs).
# Previous layout used $HOME/.local/share/rediacc/versions/<V>/rdc and is
# unconditionally removed on every re-install.
#
# Quick install (downloads and runs this script):
#   curl -fsSL https://www.rediacc.com/install.sh | bash
#
# Safer alternative (download first, inspect, then run):
#   curl -fsSL https://www.rediacc.com/install.sh -o install.sh
#   less install.sh  # inspect the script
#   bash install.sh

set -euo pipefail

# Configuration (can be overridden via environment variables)
RELEASES_URL="${REDIACC_RELEASES_URL:-https://releases.rediacc.com}"
SERVER_URL="${REDIACC_SERVER_URL:-}"

# Channel resolution. Order:
#   1. REDIACC_CHANNEL env var (explicit caller intent — wins).
#   2. Existing server.json::updateChannel (the channel `rdc update` uses).
#   3. Default 'stable'.
# Reading server.json on a re-install avoids the trap where install.sh picks
# `stable` while `rdc update` reads server.json::updateChannel=edge and jumps
# the binary on the very next invocation. Both paths now agree by default.
SERVER_JSON="${XDG_CONFIG_HOME:-$HOME/.config}/rediacc/server.json"
if [[ -z "${REDIACC_CHANNEL:-}" && -f "$SERVER_JSON" ]]; then
    # Best-effort grep+sed (jq not assumed). Matches "updateChannel": "value".
    # Trailing `|| true` keeps a no-match (most users, who never set a channel)
    # from tripping `set -o pipefail`. Empty result falls through to the
    # 'stable' default below.
    EXISTING_CHANNEL=$( { grep -oE '"updateChannel"[[:space:]]*:[[:space:]]*"[^"]+"' "$SERVER_JSON" 2>/dev/null \
        | sed -E 's/.*"([^"]+)"$/\1/' | head -1; } || true)
    if [[ -n "${EXISTING_CHANNEL:-}" ]]; then
        REDIACC_CHANNEL="$EXISTING_CHANNEL"
    fi
fi
CHANNEL="${REDIACC_CHANNEL:-stable}"

# Install layout: single binary at ${INSTALL_PREFIX}/bin/rdc, symlinked from
# ${BIN_DIR}/rdc so ${BIN_DIR} on $PATH reaches it. rdc update replaces the
# binary in place; rollback keeps a single ${INSTALL_PREFIX}/bin/rdc.old
# sibling. No per-version dirs. Historical installs used versions/<V>/rdc
# with a "keep last 5" prune loop; that feature was never surfaced to users
# and caused dir-name / binary-version divergence after each rdc update.
INSTALL_PREFIX="${HOME}/.local/share/rediacc"
INSTALL_DIR="${INSTALL_PREFIX}/bin"
BIN_DIR="${HOME}/.local/bin"
LEGACY_VERSIONS_DIR="${INSTALL_PREFIX}/versions"
STAGED_UPDATE_DIR="${HOME}/.cache/rediacc/staged-update"

# Colors for output (only if terminal supports it)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

error() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

warn() {
    echo -e "${YELLOW}$1${NC}"
}

success() {
    echo -e "${GREEN}$1${NC}"
}

# Detect platform
detect_platform() {
    case "$(uname -s)" in
        Linux) echo "linux" ;;
        Darwin) echo "mac" ;;
        *) echo "unsupported" ;;
    esac
}

# Detect architecture
detect_arch() {
    case "$(uname -m)" in
        x86_64 | amd64) echo "x64" ;;
        arm64 | aarch64) echo "arm64" ;;
        *) echo "unsupported" ;;
    esac
}

# Detect C library (musl vs glibc) on Linux
detect_libc() {
    if [ "$(uname -s)" != "Linux" ]; then
        echo ""
        return
    fi
    # ldd is linked against the system libc -- its --version output identifies it
    if ldd --version 2>&1 | grep -qi musl; then
        echo "musl"
        return
    fi
    echo ""
}

# Check for required commands
check_requirements() {
    local missing=""
    for cmd in curl; do
        if ! command -v "$cmd" &>/dev/null; then
            missing="$missing $cmd"
        fi
    done

    if [ -n "$missing" ]; then
        error "Missing required commands:$missing"
    fi

    # Check for sha256sum or shasum
    if ! command -v sha256sum &>/dev/null && ! command -v shasum &>/dev/null; then
        error "Missing required command: sha256sum or shasum"
    fi
}

# Calculate SHA256 checksum (cross-platform)
sha256() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

# Clean up artefacts from the pre-collapse layout and from any in-flight
# background update the previous install might have staged. This is
# unconditional: a fresh install should always produce exactly the new
# layout. Historical concerns:
#   - ${LEGACY_VERSIONS_DIR} held per-version dirs with stale .old siblings
#     that were never pruned because the old prune loop only touched dirs.
#   - ${STAGED_UPDATE_DIR} can hold a pending binary from a prior channel
#     that applyPendingUpdate() would auto-apply on next CLI launch,
#     silently overwriting the fresh install.
cleanup_legacy_state() {
    if [[ -d "$LEGACY_VERSIONS_DIR" ]]; then
        rm -rf "$LEGACY_VERSIONS_DIR"
        echo "Removed legacy ${LEGACY_VERSIONS_DIR}"
    fi
    if [[ -d "$STAGED_UPDATE_DIR" ]]; then
        rm -rf "$STAGED_UPDATE_DIR"
    fi
}

# Persist channel + server config so `rdc update` honors the channel this
# install came from. We write server.json when EITHER a specific server was
# requested OR the channel differs from the default. Writing on channel-alone
# is the fail-safe for cases where a preview host rewrites CHANNEL but fails
# to rewrite SERVER_URL -- without this, `rdc update` would silently drift
# back to stable on every update.
#
# Reads: CHANNEL, SERVER_URL, RELEASES_URL, REDIACC_CHANNEL, HOME, XDG_CONFIG_HOME
# Writes: ${HOME}/.config/rediacc/server.json (or macOS equivalent)
write_install_config() {
    local default_channel="stable"
    if [[ -z "${SERVER_URL:-}" && "${CHANNEL:-$default_channel}" == "$default_channel" ]]; then
        return 0
    fi

    local config_dir
    case "$(uname -s)" in
        Darwin) config_dir="$HOME/Library/Application Support/rediacc" ;;
        *) config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/rediacc" ;;
    esac
    mkdir -p "$config_dir"

    # Discover E2E public key and update channel from server (only when we
    # have a server to ask).
    local e2e_key=""
    if [[ -n "${SERVER_URL:-}" ]]; then
        local server_info
        if server_info=$(curl -fsSL -A "Rediacc-Installer/1.0" "${SERVER_URL}/account/api/v1/.well-known/server-info" 2>/dev/null); then
            if command -v jq &>/dev/null; then
                e2e_key=$(echo "$server_info" | jq -r '.e2e.keys[0].publicKeySpki // empty')
                # Auto-detect channel from server ONLY when the script is still on
                # the default channel. A channel baked by the worker rewrite (e.g.
                # :-pr-443 on a preview host) or set explicitly via REDIACC_CHANNEL
                # env var must NOT be overwritten by server-info -- the user asked
                # for a specific channel by picking that host or setting the env.
                if [[ -z "${REDIACC_CHANNEL:-}" && "$CHANNEL" == "$default_channel" ]]; then
                    local detected_channel
                    detected_channel=$(echo "$server_info" | jq -r '.updateChannel // empty')
                    if [[ -n "$detected_channel" ]]; then
                        CHANNEL="$detected_channel"
                    fi
                fi
            else
                e2e_key=$(echo "$server_info" | grep -o '"publicKeySpki":"[^"]*"' | head -1 | sed 's/"publicKeySpki":"//;s/"//')
            fi
        fi
    fi

    # accountServer defaults to production when unknown -- matches what
    # `rdc update --channel <x>` writes when no server was previously set
    # (packages/cli/src/commands/update.ts:35).
    local account_server="${SERVER_URL:-https://www.rediacc.com}"
    local server_json="{\"accountServer\":\"$account_server\",\"updateChannel\":\"$CHANNEL\""
    if [[ -n "$e2e_key" ]]; then
        server_json="$server_json,\"e2ePublicKey\":\"$e2e_key\""
    fi
    # Store custom releases URL for on-premise CLI updates
    if [[ "${RELEASES_URL:-https://releases.rediacc.com}" != "https://releases.rediacc.com" ]]; then
        server_json="$server_json,\"releasesUrl\":\"$RELEASES_URL\""
    fi
    server_json="$server_json}"
    echo "$server_json" >"$config_dir/server.json"
    chmod 600 "$config_dir/server.json"

    echo ""
    if [[ -n "${SERVER_URL:-}" ]]; then
        local server_host
        server_host=$(echo "$SERVER_URL" | sed 's|https\?://||;s|/.*||')
        success "Configured for: $server_host (channel: $CHANNEL)"
    else
        success "Channel pinned: $CHANNEL"
    fi
}

# Main installation logic
main() {
    echo "Setting up Rediacc CLI..."
    echo ""

    check_requirements
    cleanup_legacy_state

    PLATFORM=$(detect_platform)
    ARCH=$(detect_arch)

    if [[ "$PLATFORM" == "unsupported" ]]; then
        error "Unsupported platform: $(uname -s). Supported platforms: Linux, macOS"
    fi

    if [[ "$ARCH" == "unsupported" ]]; then
        error "Unsupported architecture: $(uname -m). Supported architectures: x86_64, arm64"
    fi

    LIBC=$(detect_libc)

    if [ -n "$LIBC" ]; then
        echo "Detected: $PLATFORM-$LIBC ($ARCH)"
    else
        echo "Detected: $PLATFORM ($ARCH)"
    fi

    # Get latest version from channel
    echo "Fetching latest version (channel: ${CHANNEL})..."
    LATEST_JSON=$(curl -fsSL -A "Rediacc-Installer/1.0" "${RELEASES_URL}/cli/${CHANNEL}/latest.json") || error "Failed to fetch version information"

    # Extract version - use jq if available, otherwise fall back to grep/sed
    if command -v jq &>/dev/null; then
        VERSION=$(echo "$LATEST_JSON" | jq -r '.version')
    else
        VERSION=$(echo "$LATEST_JSON" | grep -o '"version":"[^"]*"' | sed -E 's/"version":"([^"]+)"/\1/')
    fi

    if [[ -z "$VERSION" ]]; then
        error "Could not determine latest version"
    fi

    echo "Latest version: v$VERSION"

    if [ -n "$LIBC" ]; then
        BINARY_NAME="rdc-${PLATFORM}-${LIBC}-${ARCH}"
    else
        BINARY_NAME="rdc-${PLATFORM}-${ARCH}"
    fi
    # Release channels (stable/edge) serve from the immutable versioned path.
    # PR/preview channels only exist under the channel path (see upload-to-r2.sh).
    if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
        DOWNLOAD_URL="${RELEASES_URL}/cli/v${VERSION}/${BINARY_NAME}"
    else
        DOWNLOAD_URL="${RELEASES_URL}/cli/${CHANNEL}/${BINARY_NAME}"
    fi
    CHECKSUM_URL="${DOWNLOAD_URL}.sha256"

    # Create directories
    mkdir -p "$INSTALL_DIR" "$BIN_DIR"

    # Download binary
    echo "Downloading rdc v$VERSION..."
    TEMP_FILE=$(mktemp)
    curl -fsSL -A "Rediacc-Installer/1.0" "$DOWNLOAD_URL" -o "$TEMP_FILE" || {
        rm -f "$TEMP_FILE"
        error "Failed to download binary from $DOWNLOAD_URL"
    }

    # Download and verify checksum
    echo "Verifying checksum..."
    EXPECTED_SHA=$(curl -fsSL -A "Rediacc-Installer/1.0" "$CHECKSUM_URL" | awk '{print $1}') || {
        rm -f "$TEMP_FILE"
        error "Failed to download checksum from $CHECKSUM_URL"
    }
    ACTUAL_SHA=$(sha256 "$TEMP_FILE")

    if [[ "$EXPECTED_SHA" != "$ACTUAL_SHA" ]]; then
        rm -f "$TEMP_FILE"
        error "Checksum verification failed. Expected: $EXPECTED_SHA, Got: $ACTUAL_SHA"
    fi

    echo "Checksum verified."

    # Install binary atomically. A previous install's .old sibling is removed
    # first so rollback always refers to the binary rdc update itself left
    # behind, never a stale pre-install copy.
    chmod +x "$TEMP_FILE"
    rm -f "${INSTALL_DIR}/rdc.old"
    mv "$TEMP_FILE" "${INSTALL_DIR}/rdc"

    # Refresh the PATH-friendly symlink. Use a relative target so the link
    # survives $HOME being moved (e.g. inside a container with a bind-mounted
    # home). `ln -sf` won't replace an existing regular file (older install
    # layouts stored the binary directly here); rm first to guarantee the
    # symlink lands.
    rm -f "${BIN_DIR}/rdc"
    local rel_target
    if command -v realpath &>/dev/null; then
        rel_target="$(realpath --relative-to="$BIN_DIR" "${INSTALL_DIR}/rdc" 2>/dev/null || echo "${INSTALL_DIR}/rdc")"
    else
        rel_target="${INSTALL_DIR}/rdc"
    fi
    ln -s "$rel_target" "${BIN_DIR}/rdc"

    # Success message
    echo ""
    success "Rediacc CLI successfully installed!"
    echo ""
    echo "  Version:  v$VERSION"
    echo "  Location: ${BIN_DIR}/rdc -> ${INSTALL_DIR}/rdc"
    echo ""
    echo "  Next:   Run 'rdc --help' to get started"
    echo "  Update: Run 'rdc update' to update to the latest version"

    # PATH check
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        echo ""
        warn "Note: $BIN_DIR is not in your PATH"
        echo ""
        echo "  Add it by running:"
        echo ""

        # Detect shell and provide appropriate command
        SHELL_NAME=$(basename "$SHELL")
        case "$SHELL_NAME" in
            zsh)
                echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
                ;;
            fish)
                echo "  fish_add_path ~/.local/bin"
                ;;
            *)
                echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
                ;;
        esac
    fi

    write_install_config

    echo ""
    success "Installation complete!"
}

# Only run main when the script is executed directly (not when sourced by
# tests that want to call write_install_config in isolation).
if [[ -z "${REDIACC_INSTALL_SH_SOURCE_ONLY:-}" ]]; then
    main "$@"
fi

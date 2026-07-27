#!/bin/bash
# Install a PINNED, CHECKSUM-VERIFIED tmate into the session's own bin dir.
#
# NO APT FALLBACK, and that is the point. The deleted
# .github/actions/tmate/scripts/install-tmate.sh tried `apt-get install -y tmate`
# FIRST and only fell back to the pinned GitHub release if apt failed. On every
# Ubuntu runner apt succeeded, so the pinned path was dead code and the binary
# actually running was whatever the distro happened to ship -- unpinned,
# unverified, and different between runner images. A pin that is bypassed on the
# common path is not a pin.
#
# Same no-sudo, install-into-state-dir design as install-cloudflared.sh.
#
# Usage:  install-tmate.sh [--dest <dir>]
# Stdout: absolute path to the tmate binary. Nothing else.
# Exit:   0 ok, 1 download/verify failed, 3 unsupported architecture.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"
# shellcheck source=../versions.sh
source "$(bp_root "$SCRIPT_DIR")/versions.sh"

parse_args "$@"

DEST="${ARG_DEST:-$(bp_state_dir)/bin}"
BIN="$DEST/tmate"
VER="$BREAKPOINT_TMATE_VERSION"

ARCH="$(detect_arch)"
case "$ARCH" in
    x64)
        # Upstream's suffix is `amd64` here but `arm64v8` below; not symmetric.
        ASSET="tmate-${VER}-static-linux-amd64"
        EXPECTED_SHA="$BREAKPOINT_TMATE_SHA256_X64"
        ;;
    arm64)
        ASSET="tmate-${VER}-static-linux-arm64v8"
        EXPECTED_SHA="$BREAKPOINT_TMATE_SHA256_ARM64"
        ;;
    *)
        log_error "unsupported architecture '$ARCH' (need x64 or arm64)"
        exit 3
        ;;
esac

if [[ -x "$BIN" ]]; then
    log_info "tmate ${VER} already present"
    echo "$BIN"
    exit 0
fi

mkdir -p "$DEST"
URL="https://github.com/tmate-io/tmate/releases/download/${VER}/${ASSET}.tar.xz"
TMP="$DEST/${ASSET}.tar.xz"

log_step "downloading tmate ${VER} (${ARCH})..."
if ! curl -fsSL --max-time 300 --retry 3 --retry-delay 5 -o "$TMP" "$URL"; then
    log_error "download failed: $URL"
    rm -f "$TMP"
    exit 1
fi

# VERIFY BEFORE EXTRACT. tar on an attacker-controlled archive is code
# execution's near neighbour; the ordering is asserted by test-breakpoint-pins.sh.
log_step "verifying checksum..."
if ! echo "${EXPECTED_SHA}  ${TMP}" | sha256sum -c - >/dev/null 2>&1; then
    log_error "CHECKSUM MISMATCH for ${ASSET}.tar.xz"
    log_error "  expected: $EXPECTED_SHA"
    log_error "  actual:   $(sha256sum "$TMP" | cut -d' ' -f1)"
    log_error "Refusing to extract."
    rm -f "$TMP"
    exit 1
fi

# The tarball is a single directory containing one binary, hence
# --strip-components=1 and an explicit member name rather than extracting all.
if ! tar -xJf "$TMP" -C "$DEST" --strip-components=1 "${ASSET}/tmate"; then
    log_error "extraction failed"
    rm -f "$TMP"
    exit 1
fi
rm -f "$TMP"

chmod +x "$BIN"
log_info "tmate ${VER} installed at $BIN"
echo "$BIN"

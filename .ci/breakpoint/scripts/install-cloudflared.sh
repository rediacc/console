#!/bin/bash
# Install a PINNED, CHECKSUM-VERIFIED cloudflared into the session's own bin dir.
#
# Two deliberate differences from the deleted .ci/scripts/tunnel/start-cloudflare.sh:
#
#   1. PINNED AND VERIFIED. The old script curled
#        .../releases/latest/download/cloudflared-linux-amd64.deb
#      and piped it straight into `sudo dpkg -i` with no checksum. `latest`
#      means the bytes you reviewed are not the bytes you run, and dpkg runs
#      maintainer scripts as root. Here the version and the per-arch sha256 come
#      from versions.sh and are checked BEFORE the file is made executable.
#
#   2. NO SUDO. The raw binary needs only chmod +x, so it goes in
#      $(bp_state_dir)/bin instead of /usr/local/bin. That makes this work in a
#      container, on a self-hosted runner without passwordless sudo, and on a
#      laptop -- and it means the install leaves nothing behind outside the
#      state dir that teardown already removes.
#
# Idempotent: an existing binary whose checksum matches is left alone.
#
# Usage:  install-cloudflared.sh [--dest <dir>]
# Stdout: absolute path to the cloudflared binary. Nothing else.
# Exit:   0 ok, 1 download/verify failed, 3 unsupported architecture.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"
# shellcheck source=../versions.sh
source "$(bp_root "$SCRIPT_DIR")/versions.sh"

parse_args "$@"

DEST="${ARG_DEST:-$(bp_state_dir)/bin}"
BIN="$DEST/cloudflared"

ARCH="$(detect_arch)"
case "$ARCH" in
    x64)
        ASSET="cloudflared-linux-amd64"
        EXPECTED_SHA="$BREAKPOINT_CLOUDFLARED_SHA256_X64"
        ;;
    arm64)
        ASSET="cloudflared-linux-arm64"
        EXPECTED_SHA="$BREAKPOINT_CLOUDFLARED_SHA256_ARM64"
        ;;
    *)
        log_error "unsupported architecture '$ARCH' (need x64 or arm64)"
        exit 3
        ;;
esac

# Already installed and intact? Do nothing. Checked by hash, not by presence:
# a truncated download from a previous attempt would otherwise be reused.
if [[ -x "$BIN" ]] && echo "${EXPECTED_SHA}  ${BIN}" | sha256sum -c - >/dev/null 2>&1; then
    log_info "cloudflared ${BREAKPOINT_CLOUDFLARED_VERSION} already present and verified"
    echo "$BIN"
    exit 0
fi

mkdir -p "$DEST"
URL="https://github.com/cloudflare/cloudflared/releases/download/${BREAKPOINT_CLOUDFLARED_VERSION}/${ASSET}"
TMP="${BIN}.download"

log_step "downloading cloudflared ${BREAKPOINT_CLOUDFLARED_VERSION} (${ARCH})..."
if ! curl -fsSL --max-time 300 --retry 3 --retry-delay 5 -o "$TMP" "$URL"; then
    log_error "download failed: $URL"
    rm -f "$TMP"
    exit 1
fi

# VERIFY BEFORE USE. This ordering is asserted by test-breakpoint-pins.sh, which
# compares the line number of this check against the chmod below -- a mechanical
# guard against someone "simplifying" the two into the wrong order later.
log_step "verifying checksum..."
if ! echo "${EXPECTED_SHA}  ${TMP}" | sha256sum -c - >/dev/null 2>&1; then
    log_error "CHECKSUM MISMATCH for $ASSET"
    log_error "  expected: $EXPECTED_SHA"
    log_error "  actual:   $(sha256sum "$TMP" | cut -d' ' -f1)"
    log_error "Refusing to install. Either the release was re-tagged upstream, or the"
    log_error "download was tampered with. Do not 'fix' this by updating the constant"
    log_error "without checking why it changed."
    rm -f "$TMP"
    exit 1
fi

chmod +x "$TMP"
mv "$TMP" "$BIN"
log_info "cloudflared ${BREAKPOINT_CLOUDFLARED_VERSION} installed at $BIN"
echo "$BIN"

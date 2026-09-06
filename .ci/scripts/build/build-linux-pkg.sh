#!/bin/bash
# Build Linux packages from CLI binary using nfpm
# Replaces build-deb.sh (dpkg-deb) and build-rpm.sh (rpmbuild) with a unified
# nfpm-based builder that also supports apk (Alpine) and archlinux (pacman).
#
# Usage:
#   build-linux-pkg.sh --binary PATH --version VER --arch ARCH --format FORMAT [--output DIR] [--dry-run]
#
# Options:
#   --binary PATH    Path to the CLI binary
#   --version VER    Package version (e.g., 0.4.44)
#   --arch ARCH      Target architecture: amd64, arm64, x86_64, aarch64
#   --format FORMAT  Package format: deb, rpm, apk, archlinux
#   --output DIR     Output directory (default: dist/packages)
#   --dry-run        Preview without building
#
# Environment:
#   RELEASE_GPG_PRIVATE_KEY       GPG private key for RPM/DEB signing (base64 or armored)
#   RELEASE_GPG_PASSPHRASE        GPG key passphrase (optional)
#   APK_RSA_PRIVATE_KEY   RSA private key for APK signing (PEM format, optional)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# Defaults
BINARY=""
VERSION=""
ARCH=""
FORMAT=""
OUTPUT_DIR=""
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --binary)
            BINARY="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --arch)
            ARCH="$2"
            shift 2
            ;;
        --format)
            FORMAT="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --binary PATH --version VER --arch ARCH --format FORMAT [--output DIR] [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
for arg_name in BINARY VERSION ARCH FORMAT; do
    if [[ -z "${!arg_name}" ]]; then
        log_error "Missing required argument: --$(echo "$arg_name" | tr '[:upper:]' '[:lower:]')"
        exit 1
    fi
done

# Validate format
case "$FORMAT" in
    deb | rpm | apk | archlinux) ;;
    *)
        log_error "Invalid format '$FORMAT'. Must be one of: deb, rpm, apk, archlinux"
        exit 1
        ;;
esac

# =============================================================================
# Architecture Mapping
# =============================================================================
# nfpm uses Go architecture names (GOARCH). Map user-facing names to nfpm names.
# Also compute format-specific arch names for output filenames.
case "$ARCH" in
    amd64 | x86_64)
        NFPM_ARCH="amd64"
        RPM_ARCH="x86_64"
        ARCH_LINUX_ARCH="x86_64"
        DEB_ARCH="amd64"
        ;;
    arm64 | aarch64)
        NFPM_ARCH="arm64"
        RPM_ARCH="aarch64"
        ARCH_LINUX_ARCH="aarch64"
        DEB_ARCH="arm64"
        ;;
    *)
        log_error "Invalid architecture '$ARCH'. Must be one of: amd64, arm64, x86_64, aarch64"
        exit 1
        ;;
esac

# =============================================================================
# Output Filename
# =============================================================================
# Match existing naming conventions for backwards compatibility.
case "$FORMAT" in
    deb)
        PKG_FILE="${PKG_NAME}_${VERSION}_${DEB_ARCH}.deb"
        ;;
    rpm)
        PKG_FILE="${PKG_NAME}-${VERSION}-1.${RPM_ARCH}.rpm"
        ;;
    apk)
        PKG_FILE="${PKG_NAME}-${VERSION}-r1-${NFPM_ARCH}.apk"
        ;;
    archlinux)
        PKG_FILE="${PKG_NAME}-${VERSION}-1-${ARCH_LINUX_ARCH}.pkg.tar.zst"
        ;;
esac

# Set output directory
if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="$(get_repo_root)/dist/packages"
fi

log_step "Building .$FORMAT package: $PKG_FILE"
log_info "  Binary: $BINARY"
log_info "  Version: $VERSION"
log_info "  Arch: $ARCH (nfpm: $NFPM_ARCH)"
log_info "  Format: $FORMAT"
log_info "  Output: $OUTPUT_DIR/$PKG_FILE"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would build $PKG_FILE"
    mkdir -p "$OUTPUT_DIR"
    exit 0
fi

# Validate binary exists (after dry-run check — not needed for validation-only runs)
require_file "$BINARY"

# Require nfpm
require_cmd nfpm

# =============================================================================
# Export environment variables for nfpm.yaml template
# =============================================================================
export PKG_NAME PKG_BINARY_NAME PKG_SECTION PKG_PRIORITY
export PKG_MAINTAINER PKG_DESCRIPTION PKG_HOMEPAGE
export VERSION NFPM_ARCH

# BINARY_PATH must be absolute for nfpm
BINARY_PATH="$(cd "$(dirname "$BINARY")" && pwd)/$(basename "$BINARY")"
export BINARY_PATH

# =============================================================================
# Temp directory for build artifacts
# =============================================================================
BUILD_DIR="$(mktemp -d)"
CLEANUP_DIRS=("$BUILD_DIR")
cleanup() { rm -rf "${CLEANUP_DIRS[@]}"; }
trap cleanup EXIT

# =============================================================================
# Signing Setup (all via YAML config env vars, no CLI flags)
# =============================================================================
SIGNING_CONFIGURED=false

if [[ "$FORMAT" == "rpm" || "$FORMAT" == "deb" ]] && [[ -n "${RELEASE_GPG_PRIVATE_KEY:-}" ]]; then
    log_info "Setting up GPG signing for $FORMAT..."

    # Write GPG key to temp file
    GPG_KEY_FILE="$BUILD_DIR/signing-key.gpg"
    echo "$RELEASE_GPG_PRIVATE_KEY" >"$GPG_KEY_FILE"

    # CANONICALISE THE ARMOR BEFORE nfpm SEES IT.
    #
    # gpg parses armored keys leniently; nfpm decodes them with Go's
    # openpgp.ReadArmoredKeyRing, which does not. A key that gpg reads happily can
    # still fail there, and it fails AFTER the fingerprint check above has printed
    # a tick -- which is exactly how run 33990640584 looked: "Signing key matches
    # the published public key" immediately followed by
    #
    #     signing error: armored detach sign: decoding armored PGP keyring:
    #     openpgp: invalid data: armor invalid
    #
    # Measured against x/crypto v0.56.0 on a throwaway key: trailing whitespace on
    # the base64 lines is read fine by gpg and rejected by Go as "illegal base64
    # data at input byte 0"; a corrupted CRC-24 gives "armor invalid" verbatim.
    # The stored value's exact quirk does not matter, because importing and
    # re-exporting through gpg repairs EVERY variant gpg can read -- and gpg
    # reading it is precisely what the fingerprint check above already proved.
    #
    # The re-export keeps the key passphrase-protected (verified: signing with the
    # right passphrase succeeds, and the wrong one still fails with "private key
    # checksum failure"), so NFPM_*_PASSPHRASE below stays correct.
    GPG_CANON_HOME="$BUILD_DIR/gnupg-canon"
    rm -rf "$GPG_CANON_HOME"
    mkdir -p "$GPG_CANON_HOME"
    chmod 700 "$GPG_CANON_HOME"
    if GNUPGHOME="$GPG_CANON_HOME" gpg --batch --pinentry-mode loopback \
        --passphrase "${RELEASE_GPG_PASSPHRASE:-}" --import "$GPG_KEY_FILE" 2>/dev/null &&
        canon_fpr=$(GNUPGHOME="$GPG_CANON_HOME" gpg --list-secret-keys --with-colons 2>/dev/null |
            awk -F: '$1=="fpr"{print $10; exit}') && [[ -n "$canon_fpr" ]] &&
        GNUPGHOME="$GPG_CANON_HOME" gpg --batch --pinentry-mode loopback \
            --passphrase "${RELEASE_GPG_PASSPHRASE:-}" --armor \
            --export-secret-keys "$canon_fpr" >"$GPG_KEY_FILE.canonical" 2>/dev/null &&
        [[ -s "$GPG_KEY_FILE.canonical" ]]; then
        mv "$GPG_KEY_FILE.canonical" "$GPG_KEY_FILE"
        log_info "Re-exported the signing key through gpg for canonical armor"
    else
        # Not fatal on its own: the original file may already be canonical, and the
        # fingerprint check below still has to pass. Say so rather than proceeding
        # silently, because the next failure would come from inside nfpm.
        log_warn "could not re-export the signing key through gpg; handing nfpm the key as stored"
        rm -f "$GPG_KEY_FILE.canonical"
    fi
    rm -rf "$GPG_CANON_HOME"

    # THE PACKAGE SIGNING KEY MUST BE THE PUBLISHED PUBLIC KEY. Same check as
    # build-pkg-repo.sh, same day, same reason: dnf verifies every rpm against
    # the gpg.key the repository publishes, so a package signed with any other
    # key installs nowhere, and nothing here would have said so. The published
    # key defaults to the committed .asc; RELEASE_GPG_PUBLIC_KEY_FILE overrides
    # it (the package test publishes its throwaway key's public half).
    # DECLARED, because the check below runs it inside a command substitution:
    # under `set -euo pipefail` a missing gpg exits 127 with no message, before
    # any log_error, so the signing check would silently not happen.
    require_cmd gpg
    PUBLIC_KEY_FILE="${RELEASE_GPG_PUBLIC_KEY_FILE:-$(get_repo_root)/.ci/keys/gpg-public.asc}"
    if [[ -f "$PUBLIC_KEY_FILE" ]]; then
        want_fpr=$(gpg --show-keys --with-colons --with-fingerprint "$PUBLIC_KEY_FILE" 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}')
        have_fpr=$(gpg --show-keys --with-colons --with-fingerprint "$GPG_KEY_FILE" 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}')
        if [[ -z "$want_fpr" || -z "$have_fpr" || "$want_fpr" != "$have_fpr" ]]; then
            log_error "signing key ${have_fpr:-<unreadable>} is not the published public key ${want_fpr:-<unreadable>} ($PUBLIC_KEY_FILE); a $FORMAT signed with it would fail verification on every client"
            exit 1
        fi
        log_info "Signing key matches the published public key ($want_fpr)"
    fi

    # nfpm reads key_file from YAML config which references these env vars
    if [[ "$FORMAT" == "rpm" ]]; then
        export NFPM_RPM_KEY_FILE="$GPG_KEY_FILE"
    elif [[ "$FORMAT" == "deb" ]]; then
        export NFPM_DEB_KEY_FILE="$GPG_KEY_FILE"
    fi

    # Set passphrase via nfpm environment variable
    if [[ -n "${RELEASE_GPG_PASSPHRASE:-}" ]]; then
        echo "::add-mask::$RELEASE_GPG_PASSPHRASE"
        export NFPM_RPM_PASSPHRASE="$RELEASE_GPG_PASSPHRASE"
        export NFPM_DEB_PASSPHRASE="$RELEASE_GPG_PASSPHRASE"
    fi

    SIGNING_CONFIGURED=true
elif [[ "$FORMAT" == "apk" ]] && [[ -n "${APK_RSA_PRIVATE_KEY:-}" ]]; then
    log_info "Setting up RSA signing for APK..."

    APK_KEY_FILE="$BUILD_DIR/apk-signing-key.rsa"
    echo "$APK_RSA_PRIVATE_KEY" >"$APK_KEY_FILE"

    export NFPM_APK_KEY_FILE="$APK_KEY_FILE"

    SIGNING_CONFIGURED=true
fi

# =============================================================================
# Build the package
# =============================================================================
NFPM_CONFIG="$(get_repo_root)/.ci/config/nfpm.yaml"

mkdir -p "$OUTPUT_DIR"

nfpm package \
    --config "$NFPM_CONFIG" \
    --packager "$FORMAT" \
    --target "$BUILD_DIR/"

# =============================================================================
# Rename output to match expected filename
# =============================================================================
# nfpm generates filenames using its own convention. Find the output and rename.
BUILT_PKG=$(find "$BUILD_DIR" -maxdepth 1 -type f \
    \( -name "*.deb" -o -name "*.rpm" -o -name "*.apk" -o -name "*.pkg.tar.zst" \) |
    head -1)

if [[ -z "$BUILT_PKG" ]]; then
    log_error "nfpm produced no output file"
    exit 1
fi

cp "$BUILT_PKG" "$OUTPUT_DIR/$PKG_FILE"

# =============================================================================
# Verify
# =============================================================================
if [[ ! -f "$OUTPUT_DIR/$PKG_FILE" ]]; then
    log_error "Package build failed: $PKG_FILE not found"
    exit 1
fi

PACKAGE_SIZE=$(wc -c <"$OUTPUT_DIR/$PKG_FILE")
log_info "Package built: $PKG_FILE ($((PACKAGE_SIZE / 1024))KB)"

if [[ "$SIGNING_CONFIGURED" == "true" ]]; then
    log_info "Package signed with ${FORMAT^^} key"
else
    case "$FORMAT" in
        rpm | deb)
            # AN EMPTY KEY USED TO SHIP AN UNSIGNED PACKAGE, GREEN. The org secret
            # this used to read was deleted on 2026-09-05, so `${{ secrets.X }}`
            # resolved to "" -- and "" is indistinguishable here from "no signing
            # wanted". The build passed, unsigned, and said only "skipping". When
            # the caller declares signing is required, that silence is now a hard
            # failure; local builds are unaffected.
            if [[ "${RELEASE_SIGNING_REQUIRED:-0}" == "1" ]]; then
                log_error "RELEASE_SIGNING_REQUIRED=1 but RELEASE_GPG_PRIVATE_KEY is empty or unset -- refusing to ship an UNSIGNED $FORMAT. An empty value here means the secret resolved to nothing, not that signing was not wanted."
                exit 1
            fi
            log_warn "RELEASE_GPG_PRIVATE_KEY not set, skipping $FORMAT signing"
            ;;
        apk)
            log_warn "APK_RSA_PRIVATE_KEY not set, skipping APK signing"
            ;;
    esac
fi

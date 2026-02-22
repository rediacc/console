#!/bin/bash
# Assemble multi-version APT + RPM + APK + Archlinux package repositories with GPG signing
# Usage:
#   build-pkg-repo.sh --version VER --local-pkgs DIR --output DIR [--max-versions N] [--dry-run]
#
# Options:
#   --version VER       Current version being built
#   --local-pkgs DIR    Directory containing current version .deb, .rpm, .apk, .pkg.tar.zst files
#   --output DIR        Output directory (apt/, rpm/, apk/, archlinux/ will be created here)
#   --max-versions N    Maximum number of versions to include (default: 3)
#   --dry-run           Preview without building
#
# Environment:
#   GH_TOKEN            GitHub token for API access
#   GPG_PRIVATE_KEY     GPG private key for signing (base64 or armored)
#   GPG_PASSPHRASE      GPG key passphrase (optional)
#
# Prerequisites: dpkg-dev, createrepo-c, gnupg, gh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# Defaults
VERSION=""
LOCAL_PKGS=""
OUTPUT_DIR=""
MAX_VERSIONS="$PKG_MAX_VERSIONS"
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --local-pkgs)
            LOCAL_PKGS="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --max-versions)
            MAX_VERSIONS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --version VER --local-pkgs DIR --output DIR [--max-versions N] [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$VERSION" ]]; then
    log_error "Missing required argument: --version"
    exit 1
fi
if [[ -z "$LOCAL_PKGS" ]]; then
    log_error "Missing required argument: --local-pkgs"
    exit 1
fi
if [[ -z "$OUTPUT_DIR" ]]; then
    log_error "Missing required argument: --output"
    exit 1
fi

require_dir "$LOCAL_PKGS"

# Resolve to absolute paths (script uses cd to temp dirs for metadata generation)
LOCAL_PKGS="$(cd "$LOCAL_PKGS" && pwd)"
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

log_step "Building package repositories"
log_info "  Version: $VERSION"
log_info "  Local packages: $LOCAL_PKGS"
log_info "  Output: $OUTPUT_DIR"
log_info "  Max versions: $MAX_VERSIONS"

# =============================================================================
# Phase 1: GPG Setup
# =============================================================================
log_step "Phase 1: GPG setup"

GNUPGHOME_TMP="$(mktemp -d)"
export GNUPGHOME="$GNUPGHOME_TMP"
CLEANUP_DIRS=("$GNUPGHOME_TMP")
cleanup() { rm -rf "${CLEANUP_DIRS[@]}"; }
trap cleanup EXIT

GPG_OPTS=(--batch --yes --no-tty --pinentry-mode loopback)
if [[ -n "${GPG_PASSPHRASE:-}" ]]; then
    GPG_OPTS+=(--passphrase "$GPG_PASSPHRASE")
fi

if [[ -z "${GPG_PRIVATE_KEY:-}" ]]; then
    log_error "GPG_PRIVATE_KEY environment variable is required"
    exit 1
fi

echo "$GPG_PRIVATE_KEY" | gpg "${GPG_OPTS[@]}" --import 2>/dev/null
log_info "GPG private key imported"

# Get the key ID for signing
GPG_KEY_ID=$(gpg --list-keys --with-colons 2>/dev/null | grep '^pub' | head -1 | cut -d: -f5)
log_info "Using GPG key: $GPG_KEY_ID"

# Export public key
REPO_ROOT="$(get_repo_root)"
PUBLIC_KEY_FILE="$REPO_ROOT/.ci/keys/gpg-public.asc"

mkdir -p "$OUTPUT_DIR/apt" "$OUTPUT_DIR/rpm" "$OUTPUT_DIR/apk" "$OUTPUT_DIR/archlinux"

if [[ -f "$PUBLIC_KEY_FILE" ]]; then
    cp "$PUBLIC_KEY_FILE" "$OUTPUT_DIR/apt/gpg.key"
    cp "$PUBLIC_KEY_FILE" "$OUTPUT_DIR/rpm/gpg.key"
    log_info "Copied public key from $PUBLIC_KEY_FILE"
else
    gpg --armor --export "$GPG_KEY_ID" >"$OUTPUT_DIR/apt/gpg.key"
    gpg --armor --export "$GPG_KEY_ID" >"$OUTPUT_DIR/rpm/gpg.key"
    log_warn "No public key file found at $PUBLIC_KEY_FILE, exported from keyring"
fi

# =============================================================================
# Phase 2: Discover Releases
# =============================================================================
log_step "Phase 2: Discovering releases"

VERSIONS=()
if command -v gh &>/dev/null && [[ -n "${GH_TOKEN:-}" ]]; then
    # Get non-draft, non-prerelease releases
    RELEASE_TAGS=$(gh api "repos/${PKG_RELEASE_REPO}/releases" \
        --jq '[.[] | select(.draft == false and .prerelease == false)] | .[:'$MAX_VERSIONS'] | .[].tag_name' \
        2>/dev/null)

    while IFS= read -r tag; do
        [[ -z "$tag" ]] && continue
        # Strip leading 'v' from tag
        ver="${tag#v}"
        if [[ "$ver" != "$VERSION" ]]; then
            VERSIONS+=("$ver")
        fi
    done <<<"$RELEASE_TAGS"

    log_info "Found ${#VERSIONS[@]} historical versions: ${VERSIONS[*]:-none}"
else
    log_warn "GitHub CLI or GH_TOKEN not available, skipping historical versions"
fi

# =============================================================================
# Phase 3: Download Historical Packages
# =============================================================================
log_step "Phase 3: Downloading historical packages"

DOWNLOAD_DIR="$(mktemp -d)"
CLEANUP_DIRS+=("$DOWNLOAD_DIR")

for ver in "${VERSIONS[@]}"; do
    log_info "Downloading packages for v$ver..."

    for arch in amd64 arm64; do
        deb_asset="${PKG_NAME}_${ver}_${arch}.deb"
        if gh release download "v$ver" \
            --repo "$PKG_RELEASE_REPO" \
            --pattern "$deb_asset" \
            --dir "$DOWNLOAD_DIR" 2>/dev/null; then
            log_info "  Downloaded $deb_asset"
        else
            log_warn "  Asset not found: $deb_asset (skipping)"
        fi
    done

    for arch in x86_64 aarch64; do
        rpm_asset="${PKG_NAME}-${ver}-1.${arch}.rpm"
        if gh release download "v$ver" \
            --repo "$PKG_RELEASE_REPO" \
            --pattern "$rpm_asset" \
            --dir "$DOWNLOAD_DIR" 2>/dev/null; then
            log_info "  Downloaded $rpm_asset"
        else
            log_warn "  Asset not found: $rpm_asset (skipping)"
        fi
    done

    for arch in amd64 arm64; do
        apk_asset="${PKG_NAME}-${ver}-r1-${arch}.apk"
        if gh release download "v$ver" \
            --repo "$PKG_RELEASE_REPO" \
            --pattern "$apk_asset" \
            --dir "$DOWNLOAD_DIR" 2>/dev/null; then
            log_info "  Downloaded $apk_asset"
        else
            log_warn "  Asset not found: $apk_asset (skipping)"
        fi
    done

    for arch in x86_64 aarch64; do
        arch_asset="${PKG_NAME}-${ver}-1-${arch}.pkg.tar.zst"
        if gh release download "v$ver" \
            --repo "$PKG_RELEASE_REPO" \
            --pattern "$arch_asset" \
            --dir "$DOWNLOAD_DIR" 2>/dev/null; then
            log_info "  Downloaded $arch_asset"
        else
            log_warn "  Asset not found: $arch_asset (skipping)"
        fi
    done
done

# =============================================================================
# Phase 4: Build APT Repository
# =============================================================================
log_step "Phase 4: Building APT repository metadata"

APT_DIR="$OUTPUT_DIR/apt"
DISTS_DIR="$APT_DIR/dists/stable"

# Use a temp working directory for package files (metadata generation only)
APT_WORK_DIR="$(mktemp -d)"
APT_POOL_DIR="$APT_WORK_DIR/pool/main/r/${PKG_NAME}"
CLEANUP_DIRS+=("$APT_WORK_DIR")

mkdir -p "$APT_POOL_DIR"
mkdir -p "$DISTS_DIR/main/binary-amd64"
mkdir -p "$DISTS_DIR/main/binary-arm64"

# Copy packages to temp pool for metadata generation
find "$LOCAL_PKGS" -name "*.deb" -exec cp {} "$APT_POOL_DIR/" \;
find "$DOWNLOAD_DIR" -name "*.deb" -exec cp {} "$APT_POOL_DIR/" \;

DEB_COUNT=$(find "$APT_POOL_DIR" -name "*.deb" | wc -l)
log_info "APT: generating metadata for $DEB_COUNT packages (packages served via GitHub Releases)"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would generate APT repository metadata"
else
    require_cmd dpkg-scanpackages

    # Generate Packages files for each architecture
    for arch in amd64 arm64; do
        log_info "Generating Packages for $arch..."
        cd "$APT_WORK_DIR"
        dpkg-scanpackages --arch "$arch" pool/ >"$DISTS_DIR/main/binary-${arch}/Packages"
        gzip -9c "$DISTS_DIR/main/binary-${arch}/Packages" >"$DISTS_DIR/main/binary-${arch}/Packages.gz"
        cd - >/dev/null
    done

    # Generate Release file
    log_info "Generating Release file..."

    # Compute date outside the block to avoid shell expansion issues
    if [[ -n "${SOURCE_DATE_EPOCH:-}" ]]; then
        RELEASE_DATE=$(date -u -d "@$SOURCE_DATE_EPOCH" -R 2>/dev/null || date -Ru)
    else
        RELEASE_DATE=$(date -Ru)
    fi

    {
        echo "Origin: Rediacc"
        echo "Label: Rediacc CLI Repository"
        echo "Suite: stable"
        echo "Codename: stable"
        echo "Date: $RELEASE_DATE"
        echo "Architectures: amd64 arm64"
        echo "Components: main"
        echo "Description: Rediacc CLI package repository"
        echo "MD5Sum:"
    } >"$DISTS_DIR/Release"

    # Add checksums for all files in dists
    cd "$DISTS_DIR"
    for f in main/binary-*/Packages main/binary-*/Packages.gz; do
        [[ -f "$f" ]] || continue
        size=$(wc -c <"$f")
        md5=$(md5sum "$f" | cut -d' ' -f1)
        echo " $md5 $size $f" >>Release
    done

    {
        echo "SHA256:"
    } >>Release

    for f in main/binary-*/Packages main/binary-*/Packages.gz; do
        [[ -f "$f" ]] || continue
        size=$(wc -c <"$f")
        sha256=$(sha256sum "$f" | cut -d' ' -f1)
        echo " $sha256 $size $f" >>Release
    done
    cd - >/dev/null

    # Sign Release file
    log_info "Signing APT repository..."
    gpg "${GPG_OPTS[@]}" --default-key "$GPG_KEY_ID" \
        --detach-sign --armor --output "$DISTS_DIR/Release.gpg" "$DISTS_DIR/Release"
    gpg "${GPG_OPTS[@]}" --default-key "$GPG_KEY_ID" \
        --clearsign --output "$DISTS_DIR/InRelease" "$DISTS_DIR/Release"

    log_info "APT repository metadata built (no pool/ in output — served via nginx redirect)"
fi

# =============================================================================
# Phase 5: Build RPM Repository
# =============================================================================
log_step "Phase 5: Building RPM repository metadata"

RPM_DIR="$OUTPUT_DIR/rpm"

# Use a temp working directory for package files (metadata generation only)
RPM_WORK_DIR="$(mktemp -d)"
RPM_WORK_PKG_DIR="$RPM_WORK_DIR/packages"
CLEANUP_DIRS+=("$RPM_WORK_DIR")

mkdir -p "$RPM_WORK_PKG_DIR"

# Copy packages to temp dir for metadata generation
find "$LOCAL_PKGS" -name "*.rpm" -exec cp {} "$RPM_WORK_PKG_DIR/" \;
find "$DOWNLOAD_DIR" -name "*.rpm" -exec cp {} "$RPM_WORK_PKG_DIR/" \;

RPM_COUNT=$(find "$RPM_WORK_PKG_DIR" -name "*.rpm" | wc -l)
log_info "RPM: generating metadata for $RPM_COUNT packages (packages served via GitHub Releases)"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would generate RPM repository metadata"
else
    require_cmd createrepo_c

    # Create repository metadata in temp working dir
    log_info "Running createrepo_c..."
    createrepo_c "$RPM_WORK_DIR"

    # Copy only repodata/ to output (not the actual packages)
    mkdir -p "$RPM_DIR"
    cp -r "$RPM_WORK_DIR/repodata" "$RPM_DIR/"

    # Sign repomd.xml
    log_info "Signing RPM repository..."
    gpg "${GPG_OPTS[@]}" --default-key "$GPG_KEY_ID" \
        --detach-sign --armor --output "$RPM_DIR/repodata/repomd.xml.asc" "$RPM_DIR/repodata/repomd.xml"

    log_info "RPM repository metadata built (no packages/ in output — served via nginx redirect)"
fi

# Write .repo file for DNF/YUM
cat >"$RPM_DIR/rediacc.repo" <<EOF
[rediacc]
name=Rediacc CLI Repository
baseurl=https://www.rediacc.com/rpm/
enabled=1
gpgcheck=1
gpgkey=https://www.rediacc.com/rpm/gpg.key
EOF

# =============================================================================
# Phase 6: Build Alpine APK Repository
# =============================================================================
log_step "Phase 6: Building Alpine APK repository metadata"

APK_DIR="$OUTPUT_DIR/apk"

APK_WORK_DIR="$(mktemp -d)"
CLEANUP_DIRS+=("$APK_WORK_DIR")

# Organize packages by architecture (APK repos are per-arch)
for arch in x86_64 aarch64; do
    nfpm_arch="amd64"
    [[ "$arch" == "aarch64" ]] && nfpm_arch="arm64"

    arch_work="$APK_WORK_DIR/$arch"
    mkdir -p "$arch_work"

    # Copy APK packages for this architecture
    for src_dir in "$LOCAL_PKGS" "$DOWNLOAD_DIR"; do
        find "$src_dir" -name "*-${nfpm_arch}.apk" -exec cp {} "$arch_work/" \; 2>/dev/null || true
    done
done

APK_COUNT_TOTAL=0
for arch in x86_64 aarch64; do
    count=$(find "$APK_WORK_DIR/$arch" -name "*.apk" 2>/dev/null | wc -l)
    APK_COUNT_TOTAL=$((APK_COUNT_TOTAL + count))
done
log_info "APK: generating metadata for $APK_COUNT_TOTAL packages (packages served via GitHub Releases)"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would generate APK repository metadata"
else
    for arch in x86_64 aarch64; do
        arch_work="$APK_WORK_DIR/$arch"
        arch_count=$(find "$arch_work" -name "*.apk" 2>/dev/null | wc -l)

        if [[ "$arch_count" -eq 0 ]]; then
            log_warn "No APK packages found for $arch, skipping"
            continue
        fi

        mkdir -p "$APK_DIR/$arch"

        log_info "Generating APKINDEX for $arch ($arch_count packages)..."
        if command -v docker &>/dev/null; then
            docker run --rm -v "$arch_work:/repo:ro" -v "$APK_DIR/$arch:/out" \
                alpine:latest sh -c \
                "apk add --no-cache alpine-sdk >/dev/null 2>&1 && apk index -o /out/APKINDEX.tar.gz /repo/*.apk 2>/dev/null"
        else
            log_warn "Docker not available, cannot generate APKINDEX for $arch"
        fi
    done

    log_info "APK repository metadata built (unsigned — APK signing uses RSA keys, not GPG)"
fi

# =============================================================================
# Phase 7: Build Arch Linux Repository
# =============================================================================
log_step "Phase 7: Building Arch Linux repository metadata"

ARCHLINUX_DIR="$OUTPUT_DIR/archlinux"

ARCHLINUX_WORK_DIR="$(mktemp -d)"
CLEANUP_DIRS+=("$ARCHLINUX_WORK_DIR")

for arch in x86_64 aarch64; do
    arch_work="$ARCHLINUX_WORK_DIR/$arch"
    mkdir -p "$arch_work"

    # Copy Archlinux packages for this architecture
    for src_dir in "$LOCAL_PKGS" "$DOWNLOAD_DIR"; do
        find "$src_dir" -name "*-${arch}.pkg.tar.zst" -exec cp {} "$arch_work/" \; 2>/dev/null || true
    done
done

ARCH_COUNT_TOTAL=0
for arch in x86_64 aarch64; do
    count=$(find "$ARCHLINUX_WORK_DIR/$arch" -name "*.pkg.tar.zst" 2>/dev/null | wc -l)
    ARCH_COUNT_TOTAL=$((ARCH_COUNT_TOTAL + count))
done
log_info "Archlinux: generating metadata for $ARCH_COUNT_TOTAL packages (packages served via GitHub Releases)"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would generate Archlinux repository metadata"
else
    for arch in x86_64 aarch64; do
        arch_work="$ARCHLINUX_WORK_DIR/$arch"
        arch_count=$(find "$arch_work" -name "*.pkg.tar.zst" 2>/dev/null | wc -l)

        if [[ "$arch_count" -eq 0 ]]; then
            log_warn "No Archlinux packages found for $arch, skipping"
            continue
        fi

        mkdir -p "$ARCHLINUX_DIR/$arch"

        log_info "Generating pacman database for $arch ($arch_count packages)..."
        if command -v docker &>/dev/null; then
            docker run --rm -v "$arch_work:/repo" -v "$ARCHLINUX_DIR/$arch:/out" \
                archlinux:latest bash -c \
                "cp /repo/*.pkg.tar.zst /out/ 2>/dev/null; repo-add /out/rediacc.db.tar.gz /out/*.pkg.tar.zst 2>/dev/null; rm -f /out/*.pkg.tar.zst"
        else
            log_warn "Docker not available, cannot generate pacman database for $arch"
        fi
    done

    # Write pacman.conf snippet
    cat >"$ARCHLINUX_DIR/rediacc.conf" <<EOF
[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch
EOF

    log_info "Archlinux repository metadata built"
fi

# =============================================================================
# Summary
# =============================================================================
log_step "Package repository build complete (metadata only)"
log_info "  APT: $APT_DIR/ (metadata for $DEB_COUNT .deb packages)"
log_info "  RPM: $RPM_DIR/ (metadata for $RPM_COUNT .rpm packages)"
log_info "  APK: $APK_DIR/ (metadata for $APK_COUNT_TOTAL .apk packages)"
log_info "  Archlinux: $ARCHLINUX_DIR/ (metadata for $ARCH_COUNT_TOTAL .pkg.tar.zst packages)"
log_info "  Packages are served via redirect to GitHub Releases"

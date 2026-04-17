#!/bin/bash
# Test all documented installation methods
# Usage:
#   test-install-methods.sh [--dry-run] [--method <method>] [--version <ver>]
#
# Options:
#   --dry-run            Print commands without executing
#   --method <method>    Test specific method: binary, verify, update, promote, docker, apt, dnf, apk, pacman, homebrew, quick, all (default: all)
#   --version <ver>      Version to test (default: latest)
#   --platform <plat>    Platform: linux, mac, win (default: auto-detect)
#   --arch <arch>        Architecture: x64, arm64 (default: auto-detect)
#   --local-artifacts DIR  Test with locally-built artifacts instead of downloading
#
# Examples:
#   ./test-install-methods.sh --dry-run
#   ./test-install-methods.sh --method apt --version 0.4.58
#   ./test-install-methods.sh --method binary --platform linux --arch arm64
#   ./test-install-methods.sh --local-artifacts dist/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# =============================================================================
# Argument Parsing
# =============================================================================

DRY_RUN=false
METHOD="all"
VERSION="latest"
PLATFORM=""
ARCH=""
LOCAL_ARTIFACTS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --method)
            METHOD="${2:-all}"
            shift 2
            ;;
        --version)
            VERSION="${2:-latest}"
            shift 2
            ;;
        --platform)
            PLATFORM="${2:-}"
            shift 2
            ;;
        --arch)
            ARCH="${2:-}"
            shift 2
            ;;
        --local-artifacts)
            LOCAL_ARTIFACTS="${2:-}"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Auto-detect platform and arch if not specified
if [[ -z "$PLATFORM" ]]; then
    case "$(detect_os)" in
        linux) PLATFORM="linux" ;;
        macos) PLATFORM="mac" ;;
        windows) PLATFORM="win" ;;
        *) PLATFORM="linux" ;;
    esac
fi

if [[ -z "$ARCH" ]]; then
    ARCH="$(detect_arch)"
fi

# =============================================================================
# Configuration
# =============================================================================

DOCKER_IMAGE="ghcr.io/rediacc/elite/cli"
SITE_URL="${SITE_URL:-https://www.rediacc.com}"
# RELEASES_BASE_URL is set by constants.sh (sourced via common.sh) as readonly
# REPO_CHANNEL: optional channel path segment (e.g., "stable", "edge", or "" for staging)
REPO_CHANNEL="${REPO_CHANNEL:-}"
# Build repo URL: ${RELEASES_BASE_URL}/apt[/${REPO_CHANNEL}] etc.
if [[ -n "$REPO_CHANNEL" ]]; then
    REPO_URL="${RELEASES_BASE_URL}"
    REPO_CHANNEL_SUFFIX="/${REPO_CHANNEL}"
else
    REPO_URL="${RELEASES_BASE_URL}"
    REPO_CHANNEL_SUFFIX=""
fi
HOMEBREW_TAP="rediacc/tap/rediacc-cli"

# Test counters
PASS=0
FAIL=0
SKIP=0
FAILED_TESTS=()

# Temp directory for test artifacts
TEST_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

# =============================================================================
# Test Helpers
# =============================================================================

run_test() {
    local name="$1"
    shift

    log_step "TEST: $name"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would run: $*"
        ((PASS++)) || true
        return 0
    fi

    local exit_code=0
    "$@" || exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        log_info "PASS: $name"
        ((PASS++)) || true
    elif [[ $exit_code -eq 77 ]]; then
        # Exit code 77 = skip (GNU Automake convention)
        log_warn "SKIP: $name - prerequisites not met"
        ((SKIP++)) || true
    else
        log_error "FAIL: $name"
        ((FAIL++)) || true
        FAILED_TESTS+=("$name")
    fi
}

skip_test() {
    local name="$1"
    local reason="$2"
    log_warn "SKIP: $name - $reason"
    ((SKIP++)) || true
}

docker_run() {
    local image="$1"
    shift
    docker run --rm "$image" bash -c "$*"
}

# Get download URL for binary
get_binary_url() {
    local platform="$1"
    local arch="$2"
    local version="$3"

    local filename
    case "$platform" in
        linux) filename="rdc-linux-${arch}" ;;
        mac) filename="rdc-mac-${arch}" ;;
        win) filename="rdc-win-${arch}.exe" ;;
    esac

    if [[ -n "$REPO_CHANNEL" ]]; then
        echo "${RELEASES_BASE_URL}/cli/${REPO_CHANNEL}/${filename}"
    else
        echo "${RELEASES_BASE_URL}/cli/v${version}/${filename}"
    fi
}

# Verify version output
verify_version() {
    local output="$1"
    local expected="$2"

    if [[ "$expected" == "latest" ]]; then
        # Check that we got some version output - handles v prefix and pre-release suffixes
        [[ -n "$output" ]] && echo "$output" | grep -qE '^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'
    else
        echo "$output" | grep -q "$expected"
    fi
}

# =============================================================================
# Binary Download Tests
# =============================================================================

test_binary_download() {
    local platform="${1:-$PLATFORM}"
    local arch="${2:-$ARCH}"

    local binary_name="rdc"
    [[ "$platform" == "win" ]] && binary_name="rdc.exe"

    local filename
    case "$platform" in
        linux) filename="rdc-linux-${arch}" ;;
        mac) filename="rdc-mac-${arch}" ;;
        win) filename="rdc-win-${arch}.exe" ;;
    esac

    # Local artifacts mode: copy binary directly
    if [[ -n "$LOCAL_ARTIFACTS" ]]; then
        local local_binary="$LOCAL_ARTIFACTS/cli/${filename}"
        if [[ ! -f "$local_binary" ]]; then
            log_warn "Local binary not found: $local_binary"
            return 77
        fi

        local download_dir="$TEST_DIR/binary-${platform}-${arch}"
        mkdir -p "$download_dir"
        cp "$local_binary" "$download_dir/$binary_name"
        chmod +x "$download_dir/$binary_name"

        if [[ "$platform" == "win" ]]; then
            log_info "Local binary copied: $local_binary"
            return 0
        fi

        local output
        output=$("$download_dir/$binary_name" --version 2>&1 || true)
        if ! verify_version "$output" "$VERSION"; then
            log_error "Version mismatch: expected '$VERSION', got '$output'"
            return 1
        fi
        return 0
    fi

    local url
    url="$(get_binary_url "$platform" "$arch" "$VERSION")"

    local test_script
    if [[ "$platform" == "win" ]]; then
        # Windows test requires PowerShell - only available on Windows
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would download and test Windows binary"
            return 0
        fi

        # Check if we're on Windows (where powershell.exe is available)
        # Return special exit code 77 to indicate "skip" (convention from GNU Automake)
        if ! command -v powershell.exe &>/dev/null; then
            return 77
        fi

        test_script="
            \$ErrorActionPreference = 'Stop'
            Invoke-WebRequest -Uri '$url' -OutFile '$binary_name'
            .\\$binary_name --version
        "
        powershell.exe -Command "$test_script"
    else
        # Linux/macOS test
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would run: curl -fsSL '$url' -o '$binary_name' && chmod +x '$binary_name' && ./'$binary_name' --version"
            return 0
        fi

        local download_dir="$TEST_DIR/binary-${platform}-${arch}"
        mkdir -p "$download_dir"
        cd "$download_dir"

        curl -fsSL "$url" -o "$binary_name"
        chmod +x "$binary_name"
        local output
        output=$("./$binary_name" --version 2>&1 || true)
        if ! verify_version "$output" "$VERSION"; then
            log_error "Version mismatch: expected '$VERSION', got '$output'"
            return 1
        fi
    fi
}

# =============================================================================
# Update Check Tests
# =============================================================================

test_update_check() {
    if ! command -v jq &>/dev/null; then
        log_warn "jq not available, skipping update check"
        return 77
    fi

    local manifest_url="${REPO_URL}/cli/${REPO_CHANNEL}/manifest.json"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would fetch manifest from: $manifest_url"
        return 0
    fi

    # Fetch and validate manifest
    local manifest
    manifest=$(curl -fsSL "$manifest_url") || {
        log_error "Failed to fetch manifest from $manifest_url"
        return 1
    }

    if ! echo "$manifest" | jq -e '.version, .binaries' >/dev/null 2>&1; then
        log_error "Invalid manifest structure"
        return 1
    fi

    local manifest_ver
    manifest_ver=$(echo "$manifest" | jq -r '.version')
    log_info "  Manifest version: $manifest_ver"

    # Verify at least one binary URL is reachable
    local binary_url
    binary_url=$(echo "$manifest" | jq -r '.binaries["linux-x64"].url // empty')
    if [[ -n "$binary_url" ]]; then
        if ! curl -fsSL -o /dev/null --head "$binary_url" 2>/dev/null; then
            log_error "Binary URL not reachable: $binary_url"
            return 1
        fi
        log_info "  Binary URL reachable: $binary_url"
    fi
}

# =============================================================================
# Promotion Validation Tests
# =============================================================================

test_promotion_config_fixup() {
    if ! command -v jq &>/dev/null; then
        log_warn "jq not available, skipping promotion test"
        return 77
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would validate promotion config fixup"
        return 0
    fi

    # Fetch .repo file from current channel
    local repo_url="${REPO_URL}/rpm${REPO_CHANNEL_SUFFIX}/rediacc.repo"
    local repo_content
    repo_content=$(curl -fsSL "$repo_url" 2>/dev/null) || {
        log_error "Failed to fetch .repo from $repo_url"
        return 1
    }

    # Verify it contains the current channel
    if ! echo "$repo_content" | grep -q "${REPO_CHANNEL}"; then
        log_error ".repo file does not contain channel '${REPO_CHANNEL}'"
        return 1
    fi
    log_info "  .repo contains channel: ${REPO_CHANNEL}"

    # Simulate promotion: sed-replace channel with 'stable'
    local promoted
    promoted=$(echo "$repo_content" | sed "s|/${REPO_CHANNEL}/|/stable/|g")

    if ! echo "$promoted" | grep -q "/stable/"; then
        log_error "Promotion sed-fix failed: /stable/ not found"
        return 1
    fi
    if echo "$promoted" | grep -q "/${REPO_CHANNEL}/"; then
        log_error "Promotion sed-fix incomplete: /${REPO_CHANNEL}/ still present"
        return 1
    fi
    log_info "  Promotion sed-fix validated: ${REPO_CHANNEL} -> stable"
}

# =============================================================================
# Channel Verification Tests
# =============================================================================

test_channel_verify() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would verify channel configuration"
        return 0
    fi

    # Download binary from channel
    local url
    url="$(get_binary_url "linux" "x64" "$VERSION")"
    local binary="/tmp/rdc-verify-$$"
    curl -fsSL "$url" -o "$binary" || {
        log_error "Failed to download binary from $url"
        return 1
    }
    chmod +x "$binary"

    # Verify binary runs
    local ver_output
    ver_output=$("$binary" --version 2>&1 || true)
    if ! verify_version "$ver_output" "$VERSION"; then
        log_error "Version mismatch: expected '$VERSION', got '$ver_output'"
        rm -f "$binary"
        return 1
    fi
    log_info "  Binary version: $ver_output"

    # Verify channel resolution (via env var, simulating what install.sh configures)
    local doctor_output
    doctor_output=$(RDC_UPDATE_CHANNEL="${REPO_CHANNEL}" "$binary" doctor -o json 2>/dev/null || true)
    if [[ -z "$doctor_output" ]] || ! command -v jq &>/dev/null; then
        log_error "Failed to get doctor output or jq not available"
        rm -f "$binary"
        return 1
    fi

    local channel_value
    channel_value=$(echo "$doctor_output" | jq -r '.Environment[] | select(.name == "Update channel") | .value' 2>/dev/null)
    if [[ "$channel_value" != "${REPO_CHANNEL}" ]]; then
        log_error "Channel mismatch: expected '${REPO_CHANNEL}', got '$channel_value'"
        rm -f "$binary"
        return 1
    fi
    log_info "  Channel verified: $channel_value"

    local server_value
    server_value=$(echo "$doctor_output" | jq -r '.Environment[] | select(.name == "Account server") | .value' 2>/dev/null)
    if [[ -z "$server_value" ]]; then
        log_error "Account server not found in doctor output"
        rm -f "$binary"
        return 1
    fi
    log_info "  Account server: $server_value"

    # Verify manifest URL for this channel is reachable
    local manifest_url="${RELEASES_BASE_URL}/cli/${REPO_CHANNEL}/manifest.json"
    if curl -fsSL -o /dev/null --head "$manifest_url" 2>/dev/null; then
        log_info "  Manifest reachable: $manifest_url"
    else
        log_error "Manifest not reachable: $manifest_url"
        rm -f "$binary"
        return 1
    fi

    rm -f "$binary"
}

# =============================================================================
# Docker Tests
# =============================================================================

test_docker_pull_and_run() {
    # DOCKER_TAG env var overrides version-based tag (for staging images)
    local tag="${DOCKER_TAG:-${VERSION}}"
    local image="${DOCKER_IMAGE}:${tag}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would run: docker pull '$image' && docker run --rm '$image' --version"
        return 0
    fi

    docker pull "$image"
    local output
    output=$(docker run --rm "$image" --version 2>&1 || true)
    if ! verify_version "$output" "$VERSION"; then
        log_error "Version mismatch: expected '$VERSION', got '$output'"
        return 1
    fi
}

# =============================================================================
# APT Tests (Docker-based)
# =============================================================================

test_apt_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test APT install on $label"
        return 0
    fi

    docker run --rm "$distro" bash -c "
        set -e
        # Point apt at the Azure-hosted Ubuntu mirror. The upstream
        # archive.ubuntu.com / security.ubuntu.com mirrors routinely become
        # unreachable from Azure-hosted GitHub runners for 5-30 minute
        # windows, taking down this test even when the Rediacc apt repo is
        # healthy. Azure mirror is co-located with the runners.
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
            [ -f \"\$f\" ] && sed -i \\
                -e 's|http://archive\\.ubuntu\\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\
                -e 's|http://security\\.ubuntu\\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\
                \"\$f\"
        done
        apt-get update -qq
        apt-get install -y -qq curl gnupg ca-certificates >/dev/null 2>&1

        # Add GPG key
        curl -fsSL ${REPO_URL}/apt${REPO_CHANNEL_SUFFIX}/gpg.key | gpg --dearmor -o /usr/share/keyrings/rediacc.gpg

        # Add sources list
        echo 'deb [signed-by=/usr/share/keyrings/rediacc.gpg] ${REPO_URL}/apt${REPO_CHANNEL_SUFFIX} stable main' > /etc/apt/sources.list.d/rediacc.list

        # Install — retry \`apt-get update\` because the Rediacc APT repo
        # is fronted by Cloudflare and edge caches can lag behind the
        # staging artifact upload by up to ~3 minutes (Packages.gz
        # reports 'File has unexpected size' until all CF pops have
        # converged on the newly uploaded checksum).
        for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
            if apt-get update -qq -o Acquire::Retries=0; then
                break
            fi
            if [[ \$attempt -eq 12 ]]; then
                echo 'apt-get update failed after 12 attempts (~3 min); CF cache never converged' >&2
                exit 1
            fi
            echo \"apt-get update attempt \$attempt failed, retrying in 15s...\" >&2
            sleep 15
        done
        apt-get install -y -qq ${PKG_NAME} >/dev/null 2>&1

        # Verify
        ${PKG_BINARY_NAME} --version
    "
}

# =============================================================================
# DNF Tests (Docker-based)
# =============================================================================

test_dnf_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test DNF install on $label"
        return 0
    fi

    docker run --rm "$distro" bash -c "
        set -e
        # Add repo
        curl -fsSL ${REPO_URL}/rpm${REPO_CHANNEL_SUFFIX}/rediacc.repo -o /etc/yum.repos.d/rediacc.repo

        # Install
        dnf install -y ${PKG_NAME} >/dev/null 2>&1

        # Verify
        ${PKG_BINARY_NAME} --version
    "
}

# =============================================================================
# APK Tests (Docker-based)
# =============================================================================

test_apk_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test APK install on $label"
        return 0
    fi

    docker run --rm "$distro" sh -c "
        set -e
        # Add APK repository (apk appends arch automatically)
        echo '${REPO_URL}/apk${REPO_CHANNEL_SUFFIX}' >> /etc/apk/repositories
        apk update --allow-untrusted

        # Install from repo
        apk add --no-cache --allow-untrusted ${PKG_NAME}

        # Verify
        ${PKG_BINARY_NAME} --version
    "
}

# =============================================================================
# Pacman Tests (Docker-based)
# =============================================================================

test_pacman_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test Pacman install on $label"
        return 0
    fi

    docker run --rm "$distro" bash -c "
        set -e
        # Add rediacc repository
        echo '[rediacc]' >> /etc/pacman.conf
        echo 'SigLevel = Optional TrustAll' >> /etc/pacman.conf
        echo 'Server = ${REPO_URL}/archlinux${REPO_CHANNEL_SUFFIX}/\$arch' >> /etc/pacman.conf

        pacman -Sy --noconfirm

        # Install from repo
        pacman -S --noconfirm ${PKG_NAME}

        # Verify
        ${PKG_BINARY_NAME} --version
    "
}

# =============================================================================
# npm Install Tests
# =============================================================================

test_npm_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test npm install on $label"
        return 0
    fi

    local npm_url="${RELEASES_BASE_URL}/npm${REPO_CHANNEL_SUFFIX}/rediacc-cli-latest.tgz"

    docker run --rm "$distro" bash -c "
        set -e
        npm install -g '${npm_url}'
        ${PKG_BINARY_NAME} --version
    "
}

# =============================================================================
# Homebrew Tests
# =============================================================================

test_homebrew_install() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would run: brew tap rediacc/tap && brew install ${HOMEBREW_TAP}"
        return 0
    fi

    # Check if brew is available
    if ! command -v brew &>/dev/null; then
        log_error "Homebrew not available"
        return 1
    fi

    # Tap and install
    brew tap rediacc/tap
    brew install "${HOMEBREW_TAP}"

    # Verify
    local output
    output=$("${PKG_BINARY_NAME}" --version 2>&1 || true)
    verify_version "$output" "$VERSION"
}

test_homebrew_linuxbrew() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test Homebrew install in homebrew/brew:latest container"
        return 0
    fi

    docker run --rm homebrew/brew:latest bash -c "
        set -e
        brew tap rediacc/tap
        brew install ${HOMEBREW_TAP}
        ${PKG_BINARY_NAME} --version
    "
}

# =============================================================================
# Quick Install Tests
# =============================================================================

test_quick_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test quick install on $label"
        return 0
    fi

    local expected_channel="${REPO_CHANNEL:-stable}"

    docker run --rm \
        -e "REDIACC_RELEASES_URL=${RELEASES_BASE_URL}" \
        -e "REDIACC_CHANNEL=${REPO_CHANNEL:-stable}" \
        "$distro" bash -c "
        set -e
        # Point apt at the Azure-hosted Ubuntu mirror. The upstream
        # archive.ubuntu.com / security.ubuntu.com mirrors routinely become
        # unreachable from Azure-hosted GitHub runners for 5-30 minute
        # windows, taking down this test even when the Rediacc apt repo is
        # healthy. Azure mirror is co-located with the runners.
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
            [ -f \"\$f\" ] && sed -i \\
                -e 's|http://archive\\.ubuntu\\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\
                -e 's|http://security\\.ubuntu\\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\
                \"\$f\"
        done
        apt-get update -qq
        apt-get install -y -qq curl ca-certificates >/dev/null 2>&1

        # Fetch install script and verify its baked default channel matches
        # the channel under test. Catches regressions where channel rewriting
        # (worker or R2 upload) silently falls back to 'stable'.
        script=\$(curl -fsSL ${REPO_URL}/cli${REPO_CHANNEL_SUFFIX}/install.sh)
        if ! echo \"\$script\" | grep -q 'REDIACC_CHANNEL:-${expected_channel}'; then
            echo 'FAIL: install.sh default channel is not ${expected_channel}' >&2
            echo \"\$script\" | grep -E 'REDIACC_CHANNEL' >&2 || true
            exit 1
        fi

        # Run install script from channel
        echo \"\$script\" | bash

        # Verify (install.sh puts binary in ~/.local/bin)
        ~/.local/bin/${PKG_BINARY_NAME} --version
    "
}

# =============================================================================
# Main Test Execution
# =============================================================================

# Resolve "latest" version from R2
if [[ "$VERSION" == "latest" && -z "$LOCAL_ARTIFACTS" && "$DRY_RUN" == "false" ]]; then
    LATEST_JSON=$(curl -fsSL "${RELEASES_BASE_URL}/cli/${REPO_CHANNEL:-edge}/latest.json" 2>/dev/null || echo "")
    if [[ -n "$LATEST_JSON" ]] && command -v jq &>/dev/null; then
        RESOLVED=$(echo "$LATEST_JSON" | jq -r '.version' 2>/dev/null)
        if [[ -n "$RESOLVED" && "$RESOLVED" != "null" ]]; then
            VERSION="$RESOLVED"
        fi
    fi
fi

log_step "Installation Method Tests"
log_info "  Method: $METHOD"
log_info "  Version: $VERSION"
log_info "  Platform: $PLATFORM"
log_info "  Arch: $ARCH"
log_info "  Dry-run: $DRY_RUN"
if [[ -n "$LOCAL_ARTIFACTS" ]]; then
    log_info "  Local artifacts: $LOCAL_ARTIFACTS"
fi
echo ""

# Validate requirements
if [[ "$DRY_RUN" == "false" ]]; then
    case "$METHOD" in
        docker | apt | dnf | apk | pacman | quick | all)
            require_cmd docker
            ;;
    esac
fi

# Binary download tests
if [[ "$METHOD" == "binary" || "$METHOD" == "all" ]]; then
    log_step "Binary Download Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "Binary Download (Linux ${ARCH})" test_binary_download linux "$ARCH"
    elif [[ "$PLATFORM" == "mac" ]]; then
        run_test "Binary Download (macOS ${ARCH})" test_binary_download mac "$ARCH"
    elif [[ "$PLATFORM" == "win" ]]; then
        run_test "Binary Download (Windows ${ARCH})" test_binary_download win "$ARCH"
    fi
    echo ""
fi

# Channel verification tests (binary + channel resolution + manifest)
if [[ "$METHOD" == "verify" || "$METHOD" == "all" ]]; then
    if [[ "$PLATFORM" == "linux" && -n "$REPO_CHANNEL" ]]; then
        log_step "Channel Verification Tests"
        run_test "Channel Verify (${REPO_CHANNEL})" test_channel_verify
        echo ""
    fi
fi

# Update check tests (manifest + binary URL reachability)
if [[ "$METHOD" == "update" || "$METHOD" == "all" ]]; then
    log_step "Update Check Tests"
    run_test "Update Check (manifest)" test_update_check
    echo ""
fi

# Promotion validation tests
if [[ "$METHOD" == "promote" || "$METHOD" == "all" ]]; then
    log_step "Promotion Validation Tests"
    run_test "Promotion Config Fixup" test_promotion_config_fixup
    echo ""
fi

# Docker tests
if [[ "$METHOD" == "docker" || "$METHOD" == "all" ]]; then
    log_step "Docker Tests"

    if [[ "$PLATFORM" == "linux" || "$PLATFORM" == "mac" ]]; then
        run_test "Docker Pull and Run" test_docker_pull_and_run
    else
        skip_test "Docker Pull and Run" "Docker tests not supported on Windows runners"
    fi
    echo ""
fi

# APT tests
if [[ "$METHOD" == "apt" || "$METHOD" == "all" ]]; then
    log_step "APT Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "APT Install (Ubuntu 22.04)" test_apt_install "ubuntu:22.04" "Ubuntu 22.04"
        run_test "APT Install (Ubuntu 24.04)" test_apt_install "ubuntu:24.04" "Ubuntu 24.04"
        run_test "APT Install (Debian 12)" test_apt_install "debian:12" "Debian 12"
    else
        skip_test "APT Install" "APT tests require Linux with Docker"
    fi
    echo ""
fi

# DNF tests
if [[ "$METHOD" == "dnf" || "$METHOD" == "all" ]]; then
    log_step "DNF Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "DNF Install (Fedora 40)" test_dnf_install "fedora:40" "Fedora 40"
        run_test "DNF Install (Rocky Linux 9)" test_dnf_install "rockylinux:9" "Rocky Linux 9"
    else
        skip_test "DNF Install" "DNF tests require Linux with Docker"
    fi
    echo ""
fi

# APK tests
if [[ "$METHOD" == "apk" || "$METHOD" == "all" ]]; then
    log_step "APK Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "APK Install (Alpine 3.20)" test_apk_install "alpine:3.20" "Alpine 3.20"
    else
        skip_test "APK Install" "APK tests require Linux with Docker"
    fi
    echo ""
fi

# Pacman tests
if [[ "$METHOD" == "pacman" || "$METHOD" == "all" ]]; then
    log_step "Pacman Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "Pacman Install (Arch Linux)" test_pacman_install "archlinux:latest" "Arch Linux"
    else
        skip_test "Pacman Install" "Pacman tests require Linux with Docker"
    fi
    echo ""
fi

# Homebrew tests
if [[ "$METHOD" == "homebrew" || "$METHOD" == "all" ]]; then
    log_step "Homebrew Tests"

    if [[ "$PLATFORM" == "mac" ]]; then
        run_test "Homebrew Install (macOS)" test_homebrew_install
    elif [[ "$PLATFORM" == "linux" ]]; then
        if command -v brew &>/dev/null; then
            run_test "Homebrew Install (Linuxbrew)" test_homebrew_install
        else
            run_test "Homebrew Install (Linuxbrew Docker)" test_homebrew_linuxbrew
        fi
    else
        skip_test "Homebrew Install" "Homebrew not available on Windows"
    fi
    echo ""
fi

# npm install tests
if [[ "$METHOD" == "npm" || "$METHOD" == "all" ]]; then
    log_step "npm Install Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "npm Install (Node 22)" test_npm_install "node:22" "Node 22"
    else
        skip_test "npm Install" "npm tests require Linux with Docker"
    fi
    echo ""
fi

# Quick install tests
if [[ "$METHOD" == "quick" || "$METHOD" == "all" ]]; then
    log_step "Quick Install Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "Quick Install (Ubuntu 22.04)" test_quick_install "ubuntu:22.04" "Ubuntu 22.04"
        run_test "Quick Install (Ubuntu 24.04)" test_quick_install "ubuntu:24.04" "Ubuntu 24.04"
        run_test "Quick Install (Debian 12)" test_quick_install "debian:12" "Debian 12"
    else
        skip_test "Quick Install" "Quick install tests require Linux with Docker"
    fi
    echo ""
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
log_step "Results: $PASS passed, $FAIL failed, $SKIP skipped (total $((PASS + FAIL + SKIP)))"

if [[ ${#FAILED_TESTS[@]} -gt 0 ]]; then
    log_error "Failed tests:"
    for t in "${FAILED_TESTS[@]}"; do
        log_error "  - $t"
    done
fi

[[ $FAIL -eq 0 ]] || exit 1

#!/bin/bash
# Test all documented installation methods
# Usage:
#   test-install-methods.sh [--dry-run] [--method <method>] [--version <ver>]
#
# Options:
#   --dry-run            Print commands without executing
#   --method <method>    Test specific method: binary, docker, apt, dnf, homebrew, quick, all (default: all)
#   --version <ver>      Version to test (default: latest)
#   --platform <plat>    Platform: linux, mac, win (default: auto-detect)
#   --arch <arch>        Architecture: x64, arm64 (default: auto-detect)
#
# Examples:
#   ./test-install-methods.sh --dry-run
#   ./test-install-methods.sh --method apt --version 0.4.58
#   ./test-install-methods.sh --method binary --platform linux --arch arm64

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

GITHUB_REPO="rediacc/console"
DOCKER_IMAGE="ghcr.io/rediacc/elite/cli"
SITE_URL="https://www.rediacc.com"
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

    if [[ "$version" == "latest" ]]; then
        echo "https://github.com/${GITHUB_REPO}/releases/latest/download/${filename}"
    else
        echo "https://github.com/${GITHUB_REPO}/releases/download/v${version}/${filename}"
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

    local url
    url="$(get_binary_url "$platform" "$arch" "$VERSION")"
    local binary_name="rdc"
    [[ "$platform" == "win" ]] && binary_name="rdc.exe"

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
# Docker Tests
# =============================================================================

test_docker_pull_and_run() {
    local tag="${VERSION}"
    [[ "$tag" == "latest" ]] || tag="$VERSION"

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
        apt-get update -qq
        apt-get install -y -qq curl gnupg ca-certificates >/dev/null 2>&1

        # Add GPG key
        curl -fsSL ${SITE_URL}/apt/gpg.key | gpg --dearmor -o /usr/share/keyrings/rediacc.gpg

        # Add sources list
        echo 'deb [signed-by=/usr/share/keyrings/rediacc.gpg] ${SITE_URL}/apt stable main' > /etc/apt/sources.list.d/rediacc.list

        # Install
        apt-get update -qq
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
        curl -fsSL ${SITE_URL}/rpm/rediacc.repo -o /etc/yum.repos.d/rediacc.repo

        # Install
        dnf install -y ${PKG_NAME} >/dev/null 2>&1

        # Verify
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

    docker run --rm "$distro" bash -c "
        set -e
        apt-get update -qq
        apt-get install -y -qq curl ca-certificates >/dev/null 2>&1

        # Run install script
        curl -fsSL ${SITE_URL}/install.sh | bash

        # Verify (install.sh puts binary in ~/.local/bin)
        ~/.local/bin/${PKG_BINARY_NAME} --version
    "
}

# =============================================================================
# Main Test Execution
# =============================================================================

log_step "Installation Method Tests"
log_info "  Method: $METHOD"
log_info "  Version: $VERSION"
log_info "  Platform: $PLATFORM"
log_info "  Arch: $ARCH"
log_info "  Dry-run: $DRY_RUN"
echo ""

# Validate requirements
if [[ "$DRY_RUN" == "false" ]]; then
    case "$METHOD" in
        docker | apt | dnf | quick | all)
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

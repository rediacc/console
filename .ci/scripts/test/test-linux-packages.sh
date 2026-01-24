#!/bin/bash
# Test Linux package builds using Docker containers
# Usage:
#   test-linux-packages.sh [--dry-run]
#
# Requires: Docker, dpkg-dev, rpm, createrepo-c
# Runs on x86_64 runners only (builds amd64/x86_64 packages)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Test counters
PASS=0
FAIL=0
FAILED_TESTS=()

# Temp directory for all test artifacts
TEST_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TEST_DIR"; }
trap cleanup EXIT

TEST_VERSION="99.0.0-test"
DOCKER_NETWORK=""

# =============================================================================
# Test Helpers
# =============================================================================

run_test() {
    local name="$1"; shift
    log_step "TEST: $name"
    if "$@"; then
        log_info "PASS: $name"
        ((PASS++)) || true
    else
        log_error "FAIL: $name"
        ((FAIL++)) || true
        FAILED_TESTS+=("$name")
    fi
}

docker_run() {
    local image="$1"; shift
    docker run --rm \
        -v "$TEST_DIR:/packages:ro" \
        "$image" \
        bash -c "$*"
}

# =============================================================================
# Phase 1: Package Build Validation
# =============================================================================

phase1_build_dummy_binary() {
    log_step "Phase 1: Package Build Validation"

    # Create a dummy binary (shell script that outputs version)
    local dummy_bin="$TEST_DIR/rdc-dummy"
    cat > "$dummy_bin" <<'SCRIPT'
#!/bin/sh
echo "rdc version 99.0.0-test"
SCRIPT
    chmod +x "$dummy_bin"

    [[ -x "$dummy_bin" ]]
}

phase1_build_deb() {
    "$SCRIPT_DIR/../build/build-deb.sh" \
        --binary "$TEST_DIR/rdc-dummy" \
        --version "$TEST_VERSION" \
        --arch amd64 \
        --output "$TEST_DIR/packages"
}

phase1_build_rpm() {
    "$SCRIPT_DIR/../build/build-rpm.sh" \
        --binary "$TEST_DIR/rdc-dummy" \
        --version "$TEST_VERSION" \
        --arch x86_64 \
        --output "$TEST_DIR/packages"
}

phase1_validate_deb_metadata() {
    local deb_file="$TEST_DIR/packages/${PKG_NAME}_${TEST_VERSION}_amd64.deb"
    [[ -f "$deb_file" ]] || return 1

    local info
    info=$(dpkg-deb --info "$deb_file")

    # Check required fields
    echo "$info" | grep -q "Package: ${PKG_NAME}" || return 1
    echo "$info" | grep -q "Version: ${TEST_VERSION}" || return 1
    echo "$info" | grep -q "Architecture: amd64" || return 1
    echo "$info" | grep -q "Maintainer:" || return 1
    log_info "  DEB fields validated: Package, Version, Architecture, Maintainer"
}

phase1_validate_rpm_metadata() {
    local rpm_file="$TEST_DIR/packages/${PKG_NAME}-${TEST_VERSION}-1.x86_64.rpm"
    [[ -f "$rpm_file" ]] || return 1

    local info
    info=$(rpm -qip "$rpm_file" 2>/dev/null)

    # Check required fields
    echo "$info" | grep -q "Name.*: ${PKG_NAME}" || return 1
    echo "$info" | grep -q "Version.*: ${TEST_VERSION}" || return 1
    echo "$info" | grep -q "Architecture: x86_64" || return 1
    log_info "  RPM fields validated: Name, Version, Architecture"
}

# =============================================================================
# Phase 2: APT Installation (Docker)
# =============================================================================

test_deb_install() {
    local image="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test dpkg install on $label"
        return 0
    fi

    docker_run "$image" "
        dpkg -i /packages/packages/${PKG_NAME}_${TEST_VERSION}_amd64.deb && \
        test -x /usr/local/bin/${PKG_BINARY_NAME} && \
        /usr/local/bin/${PKG_BINARY_NAME} --version 2>/dev/null | grep -q '${TEST_VERSION}' && \
        echo 'Install verified on $label'
    "
}

# =============================================================================
# Phase 3: RPM Installation (Docker)
# =============================================================================

test_rpm_install() {
    local image="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test rpm install on $label"
        return 0
    fi

    docker_run "$image" "
        rpm -i /packages/packages/${PKG_NAME}-${TEST_VERSION}-1.x86_64.rpm && \
        test -x /usr/local/bin/${PKG_BINARY_NAME} && \
        /usr/local/bin/${PKG_BINARY_NAME} --version 2>/dev/null | grep -q '${TEST_VERSION}' && \
        echo 'Install verified on $label'
    "
}

# =============================================================================
# Phase 4: Repository Metadata Validation
# =============================================================================

phase4_build_repo_metadata() {
    # Build repo metadata using the test packages
    "$SCRIPT_DIR/../build/build-pkg-repo.sh" \
        --version "$TEST_VERSION" \
        --local-pkgs "$TEST_DIR/packages" \
        --output "$TEST_DIR/repo" \
        --dry-run
}

phase4_validate_apt_metadata() {
    # Run actual build (non-dry-run) for metadata validation
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would validate APT metadata structure"
        return 0
    fi

    # For real metadata validation, we need GPG — build with temp key
    local repo_out="$TEST_DIR/repo-real"
    mkdir -p "$repo_out"

    # Generate temp GPG key and build
    local gnupg_tmp
    gnupg_tmp="$(mktemp -d)"
    export GNUPGHOME="$gnupg_tmp"
    gpg --batch --yes --no-tty --pinentry-mode loopback --passphrase '' --quick-generate-key "Test <test@test.com>" rsa2048 sign 1d 2>/dev/null
    local key_id
    key_id=$(gpg --list-keys --with-colons 2>/dev/null | grep '^pub' | head -1 | cut -d: -f5)
    GPG_PRIVATE_KEY=$(gpg --armor --export-secret-keys "$key_id" 2>/dev/null)
    export GPG_PRIVATE_KEY

    "$SCRIPT_DIR/../build/build-pkg-repo.sh" \
        --version "$TEST_VERSION" \
        --local-pkgs "$TEST_DIR/packages" \
        --output "$repo_out"

    unset GNUPGHOME GPG_PRIVATE_KEY
    rm -rf "$gnupg_tmp"

    # Validate APT structure
    local release_file="$repo_out/apt/dists/stable/Release"
    [[ -f "$release_file" ]] || { log_error "Release file missing"; return 1; }
    grep -q "Origin: Rediacc" "$release_file" || { log_error "Release missing Origin"; return 1; }
    grep -q "Architectures:" "$release_file" || { log_error "Release missing Architectures"; return 1; }

    local packages_gz="$repo_out/apt/dists/stable/main/binary-amd64/Packages.gz"
    [[ -f "$packages_gz" ]] || { log_error "Packages.gz missing"; return 1; }
    gzip -t "$packages_gz" || { log_error "Packages.gz invalid gzip"; return 1; }

    # Validate Packages content
    local packages_content
    packages_content=$(zcat "$packages_gz")
    echo "$packages_content" | grep -q "Package: ${PKG_NAME}" || { log_error "Packages missing Package field"; return 1; }
    echo "$packages_content" | grep -q "Filename:" || { log_error "Packages missing Filename field"; return 1; }
    echo "$packages_content" | grep -q "SHA256:" || { log_error "Packages missing SHA256 field"; return 1; }

    log_info "  APT metadata validated: Release, Packages.gz, checksums"
}

phase4_validate_rpm_metadata() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would validate RPM metadata structure"
        return 0
    fi

    # Use the real repo built in phase4_validate_apt_metadata
    local repo_out="$TEST_DIR/repo-real"

    # Check repomd.xml
    local repomd="$repo_out/rpm/repodata/repomd.xml"
    [[ -f "$repomd" ]] || { log_error "repomd.xml missing"; return 1; }
    grep -q "<repomd" "$repomd" || { log_error "repomd.xml invalid XML"; return 1; }

    # Check .repo file
    local repo_file="$repo_out/rpm/rediacc.repo"
    [[ -f "$repo_file" ]] || { log_error "rediacc.repo missing"; return 1; }
    grep -q "baseurl=https://www.rediacc.com/rpm/" "$repo_file" || { log_error ".repo baseurl wrong"; return 1; }
    grep -q "gpgkey=https://www.rediacc.com/rpm/gpg.key" "$repo_file" || { log_error ".repo gpgkey wrong"; return 1; }

    # Check gpg.key
    [[ -f "$repo_out/rpm/gpg.key" ]] || { log_error "gpg.key missing"; return 1; }

    log_info "  RPM metadata validated: repomd.xml, rediacc.repo, gpg.key"
}

# =============================================================================
# Phase 5: Full APT Flow with Local Server (Docker)
# =============================================================================

phase5_apt_flow() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test full APT flow with local nginx"
        return 0
    fi

    local repo_out="$TEST_DIR/repo-real"
    [[ -d "$repo_out/apt" ]] || { log_error "APT repo not built (phase 4 must pass first)"; return 1; }

    # Create Docker network for nginx <-> client communication
    DOCKER_NETWORK="pkg-test-$$"
    docker network create "$DOCKER_NETWORK" 2>/dev/null || true

    # Start nginx serving the APT repo
    local nginx_container="pkg-test-nginx-$$"
    docker run -d --rm \
        --name "$nginx_container" \
        --network "$DOCKER_NETWORK" \
        -v "$repo_out/apt:/usr/share/nginx/html/apt:ro" \
        nginx:alpine

    # Wait for nginx to be ready
    local retries=10
    while ! docker exec "$nginx_container" wget -q -O /dev/null http://localhost/ 2>/dev/null; do
        ((retries--)) || { docker stop "$nginx_container" 2>/dev/null; docker network rm "$DOCKER_NETWORK" 2>/dev/null; return 1; }
        sleep 1
    done

    # Run Ubuntu container linked to nginx and test full APT flow
    local result=0
    docker run --rm \
        --network "$DOCKER_NETWORK" \
        -v "$repo_out/apt/gpg.key:/tmp/gpg.key:ro" \
        ubuntu:22.04 \
        bash -c "
            apt-get update -qq && apt-get install -y -qq gnupg ca-certificates >/dev/null 2>&1
            # Add GPG key
            cat /tmp/gpg.key | gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
            # Add sources list pointing to nginx container
            echo 'deb [signed-by=/usr/share/keyrings/rediacc.gpg] http://$nginx_container/apt stable main' > /etc/apt/sources.list.d/rediacc.list
            # Update and verify
            apt-get update -qq 2>&1
            apt-cache show ${PKG_NAME} | grep -q 'Package: ${PKG_NAME}'
            echo 'Full APT flow verified'
        " || result=1

    # Cleanup
    docker stop "$nginx_container" 2>/dev/null || true
    docker network rm "$DOCKER_NETWORK" 2>/dev/null || true
    DOCKER_NETWORK=""

    return $result
}

# =============================================================================
# Main
# =============================================================================

log_step "Linux Package Tests"
log_info "  Test version: $TEST_VERSION"
log_info "  Dry-run: $DRY_RUN"
log_info "  Working dir: $TEST_DIR"

if [[ "$DRY_RUN" == "false" ]]; then
    require_cmd docker
fi
require_cmd dpkg-deb

# Phase 1: Build and validate packages
run_test "Build dummy binary" phase1_build_dummy_binary
run_test "Build .deb package (amd64)" phase1_build_deb
run_test "Build .rpm package (x86_64)" phase1_build_rpm
run_test "Validate .deb metadata" phase1_validate_deb_metadata
run_test "Validate .rpm metadata" phase1_validate_rpm_metadata

# Phase 2: APT installation in Docker
run_test "Install .deb on Ubuntu 22.04" test_deb_install "ubuntu:22.04" "Ubuntu 22.04"
run_test "Install .deb on Ubuntu 24.04" test_deb_install "ubuntu:24.04" "Ubuntu 24.04"
run_test "Install .deb on Debian 12" test_deb_install "debian:12" "Debian 12"

# Phase 3: RPM installation in Docker
run_test "Install .rpm on Fedora 40" test_rpm_install "fedora:40" "Fedora 40"
run_test "Install .rpm on Rocky Linux 9" test_rpm_install "rockylinux:9" "Rocky Linux 9"

# Phase 4: Repository metadata validation
run_test "Build repo metadata (dry-run)" phase4_build_repo_metadata
run_test "Validate APT metadata structure" phase4_validate_apt_metadata
run_test "Validate RPM metadata structure" phase4_validate_rpm_metadata

# Phase 5: Full APT flow
run_test "Full APT flow with local nginx" phase5_apt_flow

# =============================================================================
# Summary
# =============================================================================
echo ""
log_step "Results: $PASS passed, $FAIL failed (total $((PASS + FAIL)))"

if [[ ${#FAILED_TESTS[@]} -gt 0 ]]; then
    log_error "Failed tests:"
    for t in "${FAILED_TESTS[@]}"; do
        log_error "  - $t"
    done
fi

[[ $FAIL -eq 0 ]] || exit 1

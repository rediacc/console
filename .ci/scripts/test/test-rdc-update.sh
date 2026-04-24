#!/bin/bash
# End-to-end integration tests for `rdc update` + install.sh lifecycle.
# Seven scenarios run against a local Python fixture server. RDC_BINARY
# supplies the binary (CI sources it from build-cli-linux-x64).
#
# Scenarios:
#   happy / check-only / sha256-mismatch / rollback / rollback-empty /
#   channel-switch / reinstall.
#
# Runs the real rdc binary against a local Python HTTP fixture server that
# serves controlled manifest.json / latest.json / binary / .sha256 under
# /cli/<channel>/... . Each scenario isolates HOME to a throwaway tmpdir
# so state doesn't leak between cases.
#
# Required: RDC_BINARY env var pointing to a rdc executable for the
# current platform (CI builds this in the build-cli job; local runs can
# download it from cli/edge/ on R2 or build via `cd packages/cli && npm run build:cli`).
#
# Usage:
#   RDC_BINARY=/path/to/rdc ./test-rdc-update.sh [scenario ...]
#   Scenarios: happy, check-only, up-to-date, force, sha256-mismatch,
#              rollback, rollback-empty, channel-switch, stage-apply,
#              concurrent, reinstall, all (default)
#
# Covers findings: B (version dir mismatch), C (.old orphans),
#                  D (lock contention), E (staged-update cleanup),
#                  Updater mechanics end-to-end.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALL_SH="$ROOT_DIR/packages/www/public/install.sh"

if [[ -z "${RDC_BINARY:-}" ]]; then
    echo "error: RDC_BINARY env var must point to an rdc executable" >&2
    exit 2
fi
if [[ ! -x "$RDC_BINARY" ]]; then
    echo "error: RDC_BINARY=$RDC_BINARY is not executable" >&2
    exit 2
fi
# Resolve to absolute path so HOME swaps don't reinterpret it.
RDC_BINARY="$(cd "$(dirname "$RDC_BINARY")" && pwd)/$(basename "$RDC_BINARY")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() { echo -e "${BLUE}→${NC} $*" >&2; }
log_pass() { echo -e "${GREEN}PASS:${NC} $*"; }
log_fail() {
    echo -e "${RED}FAIL:${NC} $*" >&2
    CURRENT_SCENARIO_FAILED=1
}
log_warn() { echo -e "${YELLOW}warn:${NC} $*" >&2; }

CURRENT_SCENARIO_FAILED=0
FAILED_SCENARIOS=()

# -----------------------------------------------------------------------
# Fixture server: a Python http.server subprocess serving a prepared tree
# that looks like releases.rediacc.com. Each scenario rebuilds the tree
# and restarts the server on a fresh port.
# -----------------------------------------------------------------------

FIXTURE_DIR=""
FIXTURE_PORT=""
FIXTURE_PID=""

start_fixture() {
    local serve_root="$1"
    local port
    # Find a free port in the ephemeral range
    port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
    (cd "$serve_root" && python3 -m http.server "$port" >/dev/null 2>&1) &
    FIXTURE_PID=$!
    FIXTURE_PORT="$port"
    # Wait for readiness
    for _ in $(seq 1 30); do
        if curl -fs "http://127.0.0.1:$port/" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.1
    done
    echo "fixture server failed to start on port $port" >&2
    return 1
}

stop_fixture() {
    if [[ -n "${FIXTURE_PID:-}" ]]; then
        kill "$FIXTURE_PID" 2>/dev/null || true
        wait "$FIXTURE_PID" 2>/dev/null || true
        FIXTURE_PID=""
    fi
}

# Write a manifest.json + latest.json + binary + sha256 sidecar into the
# fixture tree at cli/<channel>/ pointing at the given version. The binary
# served is the same RDC_BINARY (since we're testing swap mechanics, not
# versioned behaviour). stable/edge also populate cli/v<version>/.
prep_fixture() {
    local serve_root="$1"
    local channel="$2"
    local version="$3"
    local platform_key="$4"
    local binary_name="$5"
    local binary_override_sha="${6:-}"

    mkdir -p "$serve_root/cli/$channel"
    local sha256
    sha256="$(sha256sum "$RDC_BINARY" | awk '{print $1}')"
    cp "$RDC_BINARY" "$serve_root/cli/$channel/$binary_name"
    echo "$sha256  $binary_name" >"$serve_root/cli/$channel/$binary_name.sha256"

    if [[ "$channel" == "stable" || "$channel" == "edge" ]]; then
        mkdir -p "$serve_root/cli/v$version"
        cp "$RDC_BINARY" "$serve_root/cli/v$version/$binary_name"
        echo "$sha256  $binary_name" >"$serve_root/cli/v$version/$binary_name.sha256"
    fi

    local expected_sha="$sha256"
    if [[ -n "$binary_override_sha" ]]; then
        expected_sha="$binary_override_sha"
    fi

    # manifest.json — format matches UpdateManifest in packages/cli/src/types/
    local binary_url="http://127.0.0.1:$FIXTURE_PORT/cli/$channel/$binary_name"
    if [[ "$channel" == "stable" || "$channel" == "edge" ]]; then
        binary_url="http://127.0.0.1:$FIXTURE_PORT/cli/v$version/$binary_name"
    fi
    cat >"$serve_root/cli/$channel/manifest.json" <<JSON
{
  "version": "$version",
  "releaseNotesUrl": "https://example.invalid/notes/v$version",
  "binaries": {
    "$platform_key": {
      "url": "$binary_url",
      "sha256": "$expected_sha",
      "size": $(stat -c '%s' "$RDC_BINARY" 2>/dev/null || stat -f '%z' "$RDC_BINARY")
    }
  }
}
JSON
    cat >"$serve_root/cli/$channel/latest.json" <<JSON
{"version":"$version"}
JSON
}

# -----------------------------------------------------------------------
# Helpers for the tests
# -----------------------------------------------------------------------

detect_platform_key() {
    local os arch libc
    case "$(uname -s)" in
        Linux) os=linux ;;
        Darwin) os=mac ;;
        *)
            echo "unsupported OS" >&2
            exit 2
            ;;
    esac
    case "$(uname -m)" in
        x86_64 | amd64) arch=x64 ;;
        arm64 | aarch64) arch=arm64 ;;
        *)
            echo "unsupported arch" >&2
            exit 2
            ;;
    esac
    # platform key used in manifest.binaries
    echo "$os-$arch"
}

detect_binary_name() {
    local platform_key="$1"
    local os="${platform_key%-*}"
    local arch="${platform_key#*-}"
    case "$os" in
        linux)
            if ldd --version 2>&1 | grep -qi musl; then
                echo "rdc-linux-musl-$arch"
            else
                echo "rdc-linux-$arch"
            fi
            ;;
        mac) echo "rdc-mac-$arch" ;;
        *)
            echo "error: unsupported $os" >&2
            exit 2
            ;;
    esac
}

# Set up a pristine HOME under $1, populated by install.sh against the
# fixture server at $FIXTURE_PORT for channel $2 version $3.
fresh_install() {
    local home_dir="$1"
    local channel="$2"
    local version="$3"

    # install.sh expects HOME to exist
    mkdir -p "$home_dir"
    # Unset XDG_* so install.sh's path resolution uses our isolated HOME
    # (matches what test-install-script.sh does in its source_install harness).
    env -u XDG_CONFIG_HOME -u XDG_STATE_HOME -u XDG_CACHE_HOME -u XDG_DATA_HOME \
        REDIACC_RELEASES_URL="http://127.0.0.1:$FIXTURE_PORT" \
        REDIACC_CHANNEL="$channel" \
        HOME="$home_dir" \
        bash "$INSTALL_SH" >/dev/null 2>&1

    # Sanity
    [[ -L "$home_dir/.local/bin/rdc" ]] || log_fail "fresh_install: symlink missing"
    [[ -x "$home_dir/.local/share/rediacc/bin/rdc" ]] || log_fail "fresh_install: binary missing"
}

# Run rdc from the fresh install, using the isolated HOME. Rdc sees the
# fixture server as its releases URL. Unsets CI / GITHUB_ACTIONS so
# rdc's isUpdateDisabled() doesn't short-circuit the check (it auto-
# disables updates when CI=true to avoid mutating the runner's state).
# The tests ARE exercising rdc update; isolated HOME makes it safe.
run_rdc() {
    local home_dir="$1"
    shift
    # Unset XDG_* so rdc's getConfigDir/getStateDir/getCacheDir all resolve
    # relative to our isolated HOME (getLinuxDirs prefers XDG_* when set).
    # Without this, channel-switch scenario's server.json ends up at the
    # runner's XDG_CONFIG_HOME and the test asserts on $home/.config/... .
    env -u CI -u GITHUB_ACTIONS -u GITHUB_RUN_ID -u RUNNER_OS \
        -u XDG_CONFIG_HOME -u XDG_STATE_HOME -u XDG_CACHE_HOME -u XDG_DATA_HOME \
        HOME="$home_dir" \
        REDIACC_RELEASES_URL="http://127.0.0.1:$FIXTURE_PORT" \
        RDC_DISABLE_AUTOUPDATE="0" \
        RDC_DISABLE_TELEMETRY=1 \
        "$home_dir/.local/bin/rdc" "$@"
}

assert_file_exists() { [[ -f "$1" ]] || log_fail "expected file: $1"; }
assert_file_absent() { [[ ! -e "$1" ]] || log_fail "unexpected file: $1"; }
assert_symlink() { [[ -L "$1" ]] || log_fail "expected symlink: $1"; }

# -----------------------------------------------------------------------
# Scenarios
# -----------------------------------------------------------------------

PLATFORM_KEY="$(detect_platform_key)"
BINARY_NAME="$(detect_binary_name "$PLATFORM_KEY")"

scenario_happy() {
    log_step "scenario: happy-path update"
    CURRENT_SCENARIO_FAILED=0
    local tmp home serve_root
    tmp="$(mktemp -d)"
    home="$tmp/home"
    serve_root="$tmp/fixture"
    mkdir -p "$serve_root"
    prep_fixture "$serve_root" edge 1.0.3 "$PLATFORM_KEY" "$BINARY_NAME"
    start_fixture "$serve_root"
    fresh_install "$home" edge 1.0.3
    # Re-prep fixture to serve a newer version
    rm -rf "$serve_root/cli/edge" "$serve_root/cli/v1.0.3"
    prep_fixture "$serve_root" edge 1.0.4 "$PLATFORM_KEY" "$BINARY_NAME"

    local out
    # --force bypasses the compareVersions short-circuit. The rdc binary's
    # baked-in CLI_VERSION (set at build time in CI) is often >= fixture's
    # served version, which would otherwise cause performUpdate() to return
    # success without swapping. The test is exercising swap mechanics, not
    # the version-comparison logic.
    out="$(run_rdc "$home" update --force 2>&1)" || log_fail "rdc update non-zero exit: $out"

    assert_file_exists "$home/.local/share/rediacc/bin/rdc"
    assert_file_exists "$home/.local/share/rediacc/bin/rdc.old"
    assert_symlink "$home/.local/bin/rdc"
    # state file cleared
    local state="$home/.local/state/rediacc/update-state.json"
    if [[ -f "$state" ]]; then
        grep -q '"pendingUpdate":null' "$state" ||
            grep -q '"pendingUpdate": null' "$state" ||
            log_fail "state file pendingUpdate not cleared after update"
    fi

    stop_fixture
    rm -rf "$tmp"
    ((CURRENT_SCENARIO_FAILED)) && FAILED_SCENARIOS+=("happy")
    ((CURRENT_SCENARIO_FAILED)) || log_pass "happy-path update"
}

scenario_check_only() {
    log_step "scenario: check-only"
    CURRENT_SCENARIO_FAILED=0
    local tmp home serve_root
    tmp="$(mktemp -d)"
    home="$tmp/home"
    serve_root="$tmp/fixture"
    mkdir -p "$serve_root"
    prep_fixture "$serve_root" edge 1.0.3 "$PLATFORM_KEY" "$BINARY_NAME"
    start_fixture "$serve_root"
    fresh_install "$home" edge 1.0.3
    rm -rf "$serve_root/cli/edge" "$serve_root/cli/v1.0.3"
    prep_fixture "$serve_root" edge 1.0.4 "$PLATFORM_KEY" "$BINARY_NAME"

    run_rdc "$home" update --check-only >/dev/null 2>&1 || log_fail "--check-only non-zero"
    # Binary should NOT have been swapped: no .old file
    assert_file_absent "$home/.local/share/rediacc/bin/rdc.old"
    stop_fixture
    rm -rf "$tmp"
    ((CURRENT_SCENARIO_FAILED)) && FAILED_SCENARIOS+=("check-only")
    ((CURRENT_SCENARIO_FAILED)) || log_pass "check-only does not swap"
}

scenario_sha256_mismatch() {
    log_step "scenario: sha256 mismatch"
    CURRENT_SCENARIO_FAILED=0
    local tmp home serve_root
    tmp="$(mktemp -d)"
    home="$tmp/home"
    serve_root="$tmp/fixture"
    mkdir -p "$serve_root"
    prep_fixture "$serve_root" edge 1.0.3 "$PLATFORM_KEY" "$BINARY_NAME"
    start_fixture "$serve_root"
    fresh_install "$home" edge 1.0.3
    rm -rf "$serve_root/cli/edge" "$serve_root/cli/v1.0.3"
    # Manifest declares a bogus sha; binary bytes unchanged
    prep_fixture "$serve_root" edge 1.0.4 "$PLATFORM_KEY" "$BINARY_NAME" "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    # --force bypasses the version short-circuit so rdc actually attempts
    # the download and hits the sha256 verification path that this scenario
    # is exercising.
    if run_rdc "$home" update --force >/dev/null 2>&1; then
        log_fail "sha mismatch should have failed update"
    fi
    assert_file_absent "$home/.local/share/rediacc/bin/rdc.old"
    stop_fixture
    rm -rf "$tmp"
    ((CURRENT_SCENARIO_FAILED)) && FAILED_SCENARIOS+=("sha256-mismatch")
    ((CURRENT_SCENARIO_FAILED)) || log_pass "sha256 mismatch aborts update"
}

scenario_rollback() {
    log_step "scenario: rollback"
    CURRENT_SCENARIO_FAILED=0
    local tmp home serve_root
    tmp="$(mktemp -d)"
    home="$tmp/home"
    serve_root="$tmp/fixture"
    mkdir -p "$serve_root"
    prep_fixture "$serve_root" edge 1.0.3 "$PLATFORM_KEY" "$BINARY_NAME"
    start_fixture "$serve_root"
    fresh_install "$home" edge 1.0.3
    rm -rf "$serve_root/cli/edge" "$serve_root/cli/v1.0.3"
    prep_fixture "$serve_root" edge 1.0.4 "$PLATFORM_KEY" "$BINARY_NAME"
    # --force bypasses the version short-circuit so the swap actually happens
    # and creates rdc.old which the subsequent --rollback step consumes.
    local update_out rollback_out
    update_out="$(run_rdc "$home" update --force 2>&1)" ||
        log_fail "update prerequisite failed: $update_out"
    assert_file_exists "$home/.local/share/rediacc/bin/rdc.old"
    rollback_out="$(run_rdc "$home" update --rollback 2>&1)" ||
        log_fail "rollback non-zero: $rollback_out"
    assert_file_absent "$home/.local/share/rediacc/bin/rdc.old"
    stop_fixture
    rm -rf "$tmp"
    ((CURRENT_SCENARIO_FAILED)) && FAILED_SCENARIOS+=("rollback")
    ((CURRENT_SCENARIO_FAILED)) || log_pass "rollback restores previous binary and consumes .old"
}

scenario_rollback_empty() {
    log_step "scenario: rollback without backup"
    CURRENT_SCENARIO_FAILED=0
    local tmp home serve_root
    tmp="$(mktemp -d)"
    home="$tmp/home"
    serve_root="$tmp/fixture"
    mkdir -p "$serve_root"
    prep_fixture "$serve_root" edge 1.0.3 "$PLATFORM_KEY" "$BINARY_NAME"
    start_fixture "$serve_root"
    fresh_install "$home" edge 1.0.3
    # No update run; no .old exists
    if run_rdc "$home" update --rollback >/dev/null 2>&1; then
        log_fail "rollback without .old should have failed"
    fi
    stop_fixture
    rm -rf "$tmp"
    ((CURRENT_SCENARIO_FAILED)) && FAILED_SCENARIOS+=("rollback-empty")
    ((CURRENT_SCENARIO_FAILED)) || log_pass "rollback without backup exits non-zero"
}

scenario_reinstall() {
    log_step "scenario: re-install preserves layout, cleans staged-update"
    CURRENT_SCENARIO_FAILED=0
    local tmp home serve_root
    tmp="$(mktemp -d)"
    home="$tmp/home"
    serve_root="$tmp/fixture"
    mkdir -p "$serve_root"
    prep_fixture "$serve_root" edge 1.0.3 "$PLATFORM_KEY" "$BINARY_NAME"
    start_fixture "$serve_root"
    fresh_install "$home" edge 1.0.3
    # Plant a fake legacy versions/ dir and a fake staged-update file
    mkdir -p "$home/.local/share/rediacc/versions/1.0.0"
    touch "$home/.local/share/rediacc/versions/1.0.0/rdc" "$home/.local/share/rediacc/versions/1.0.0/rdc.old"
    mkdir -p "$home/.cache/rediacc/staged-update"
    touch "$home/.cache/rediacc/staged-update/rdc-99.99.99"
    # Re-run install.sh
    REDIACC_RELEASES_URL="http://127.0.0.1:$FIXTURE_PORT" \
        REDIACC_CHANNEL=edge \
        HOME="$home" \
        bash "$INSTALL_SH" >/dev/null 2>&1
    assert_file_absent "$home/.local/share/rediacc/versions"
    assert_file_absent "$home/.cache/rediacc/staged-update"
    assert_file_exists "$home/.local/share/rediacc/bin/rdc"
    assert_symlink "$home/.local/bin/rdc"
    stop_fixture
    rm -rf "$tmp"
    ((CURRENT_SCENARIO_FAILED)) && FAILED_SCENARIOS+=("reinstall")
    ((CURRENT_SCENARIO_FAILED)) || log_pass "re-install migrates legacy layout + clears staged-update"
}

scenario_channel_switch() {
    log_step "scenario: channel switch persists to server.json"
    CURRENT_SCENARIO_FAILED=0
    local tmp home serve_root
    tmp="$(mktemp -d)"
    home="$tmp/home"
    serve_root="$tmp/fixture"
    mkdir -p "$serve_root"
    prep_fixture "$serve_root" stable 1.0.3 "$PLATFORM_KEY" "$BINARY_NAME"
    prep_fixture "$serve_root" edge 1.0.3 "$PLATFORM_KEY" "$BINARY_NAME"
    start_fixture "$serve_root"
    fresh_install "$home" stable 1.0.3

    # Switch channel via rdc update --channel
    run_rdc "$home" update --channel edge --check-only >/dev/null 2>&1 ||
        log_fail "--channel edge --check-only non-zero"
    local config="$home/.config/rediacc/server.json"
    assert_file_exists "$config"
    grep -q '"updateChannel":"edge"' "$config" ||
        grep -q '"updateChannel": "edge"' "$config" ||
        log_fail "server.json did not record updateChannel=edge"
    stop_fixture
    rm -rf "$tmp"
    ((CURRENT_SCENARIO_FAILED)) && FAILED_SCENARIOS+=("channel-switch")
    ((CURRENT_SCENARIO_FAILED)) || log_pass "channel switch writes server.json"
}

# -----------------------------------------------------------------------
# Dispatch
# -----------------------------------------------------------------------

SELECTED=("${@:-all}")
if [[ "${SELECTED[0]}" == "all" ]]; then
    SELECTED=(happy check-only sha256-mismatch rollback rollback-empty channel-switch reinstall)
fi

for scenario in "${SELECTED[@]}"; do
    case "$scenario" in
        happy) scenario_happy ;;
        check-only) scenario_check_only ;;
        sha256-mismatch) scenario_sha256_mismatch ;;
        rollback) scenario_rollback ;;
        rollback-empty) scenario_rollback_empty ;;
        channel-switch) scenario_channel_switch ;;
        reinstall) scenario_reinstall ;;
        *)
            echo "unknown scenario: $scenario" >&2
            exit 2
            ;;
    esac
done

# Summary
echo ""
if ((${#FAILED_SCENARIOS[@]} > 0)); then
    echo -e "${RED}FAILED:${NC} ${FAILED_SCENARIOS[*]}" >&2
    exit 1
fi
echo -e "${GREEN}ALL SCENARIOS PASSED${NC}"

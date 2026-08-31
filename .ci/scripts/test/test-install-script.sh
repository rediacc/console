#!/bin/bash
# Unit tests for packages/www/public/install.sh internals. Sources the
# script with REDIACC_INSTALL_SH_SOURCE_ONLY=1 to skip main() and exercises
# individual functions against a throwaway HOME.
#
# Covers:
#   - detect_platform / detect_arch / detect_libc
#   - write_install_config edge cases
#   - cleanup_legacy_state migration
#   - bin layout structure (no versions/ dir, staged-update cleared)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALL_SH="$ROOT_DIR/packages/www/public/install.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
log_fail() {
    echo -e "${RED}FAIL:${NC} $*" >&2
    exit 1
}
log_pass() { echo -e "${GREEN}PASS:${NC} $*"; }

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

# Each test gets a fresh HOME so install state doesn't leak.
fresh_home() {
    local home_dir
    home_dir="$(mktemp -d "$TEMP/home.XXXXXX")"
    echo "$home_dir"
}

# Source install.sh with source-only mode. Resets variables that were
# already evaluated at source time and re-sources if HOME changed.
# XDG_CONFIG_HOME is unset so every test assertion can look at
# $HOME/.config/rediacc/rediacc.json deterministically (some CI runners
# set XDG_CONFIG_HOME which would redirect the write).
source_install() {
    export HOME="$1"
    export REDIACC_INSTALL_SH_SOURCE_ONLY=1
    unset XDG_CONFIG_HOME
    # BLOCKER: INSTALL_SH is the user-facing install script under test; its path is a dynamic variable by design so shellcheck cannot follow it statically
    # shellcheck disable=SC1090
    source "$INSTALL_SH"
}

test_detect_platform() {
    local h
    h="$(fresh_home)"
    HOME="$h" source_install "$h"
    local got
    got="$(detect_platform)"
    case "$(uname -s)" in
        Linux) [[ "$got" == "linux" ]] || log_fail "detect_platform: expected linux, got $got" ;;
        Darwin) [[ "$got" == "mac" ]] || log_fail "detect_platform: expected mac, got $got" ;;
    esac
    log_pass "detect_platform matches uname"
}

test_detect_arch() {
    local h
    h="$(fresh_home)"
    HOME="$h" source_install "$h"
    local got
    got="$(detect_arch)"
    case "$(uname -m)" in
        x86_64 | amd64) [[ "$got" == "x64" ]] || log_fail "detect_arch: expected x64, got $got" ;;
        arm64 | aarch64) [[ "$got" == "arm64" ]] || log_fail "detect_arch: expected arm64, got $got" ;;
    esac
    log_pass "detect_arch matches uname -m"
}

test_write_install_config_default_noop() {
    HOME="$(fresh_home)"
    source_install "$HOME"
    CHANNEL=stable SERVER_URL="" RELEASES_URL=https://releases.rediacc.com \
        write_install_config >/dev/null 2>&1 || true
    local config="$HOME/.config/rediacc/rediacc.json"
    if [[ -f "$config" ]]; then
        log_fail "write_install_config should not write on default channel + no server (wrote: $(cat "$config"))"
    fi
    log_pass "default channel + no server -> no rediacc.json"
}

test_write_install_config_channel_only() {
    HOME="$(fresh_home)"
    source_install "$HOME"
    CHANNEL=edge SERVER_URL="" RELEASES_URL=https://releases.rediacc.com \
        write_install_config >/dev/null 2>&1
    local config="$HOME/.config/rediacc/rediacc.json"
    [[ -f "$config" ]] || log_fail "write_install_config should write rediacc.json when channel != stable"
    local body
    body="$(cat "$config")"
    grep -q '"updateChannel":"edge"' <<<"$body" || log_fail "updateChannel field not edge: $body"
    grep -q '"accountServer":"https://www.rediacc.com"' <<<"$body" || log_fail "accountServer should default to production: $body"
    # The absent-file branch must produce a valid minimal v3 config, not a bare
    # account blob — the CLI parses this file directly.
    grep -q '"schemaVersion":3' <<<"$body" || log_fail "minimal config must carry schemaVersion 3: $body"
    grep -q '"encryption":{"mode":"plaintext"}' <<<"$body" || log_fail "minimal config must be plaintext: $body"
    local perms
    perms="$(stat -c '%a' "$config" 2>/dev/null || stat -f '%A' "$config")"
    [[ "$perms" == "600" ]] || log_fail "rediacc.json mode must be 600 (got $perms)"
    log_pass "non-default channel writes rediacc.json with correct fields and mode"
}

test_write_install_config_custom_releases() {
    HOME="$(fresh_home)"
    source_install "$HOME"
    CHANNEL=stable SERVER_URL=https://custom.example RELEASES_URL=https://my.r2.example \
        write_install_config >/dev/null 2>&1 || true
    local config="$HOME/.config/rediacc/rediacc.json"
    [[ -f "$config" ]] || log_fail "write_install_config should write when SERVER_URL is set"
    local body
    body="$(cat "$config")"
    grep -q '"releasesUrl":"https://my.r2.example"' <<<"$body" || log_fail "releasesUrl must persist: $body"
    log_pass "custom releases URL persists in rediacc.json"
}

# Present config + no jq: the config is user data; write_install_config must
# leave it byte-for-byte untouched and print a follow-up command instead of
# rewriting it (the no-jq branch of the present-file path).
test_write_install_config_present_no_jq_untouched() {
    HOME="$(fresh_home)"
    source_install "$HOME"
    mkdir -p "$HOME/.config/rediacc"
    local config="$HOME/.config/rediacc/rediacc.json"
    printf '%s' '{"schemaVersion":3,"id":"11111111-1111-4111-a111-111111111111","version":1,"encryption":{"mode":"plaintext"},"machines":{"keep":"yes"},"account":{}}' >"$config"
    local before
    before="$(cat "$config")"
    # Hide jq by running write_install_config with a PATH that lacks it.
    local shim
    shim="$(mktemp -d "$TEMP/nojq.XXXXXX")"
    for t in grep sed awk cat mktemp mv rm chmod od tr uuidgen stat mkdir head curl uname dirname basename env; do
        local p
        p="$(command -v "$t" 2>/dev/null)" && ln -sf "$p" "$shim/$t"
    done
    local out
    out="$(PATH="$shim" CHANNEL=edge SERVER_URL="" RELEASES_URL=https://releases.rediacc.com \
        write_install_config 2>&1 || true)"
    local after
    after="$(cat "$config")"
    [[ "$before" == "$after" ]] || log_fail "no-jq path must not modify the live config (before=$before after=$after)"
    grep -q 'rdc update --channel edge' <<<"$out" || log_fail "no-jq path must print the follow-up command: $out"
    log_pass "present config + no jq -> untouched, prints follow-up command"
}

test_cleanup_legacy_state_removes_versions_dir() {
    HOME="$(fresh_home)"
    source_install "$HOME"
    local legacy="$HOME/.local/share/rediacc/versions"
    mkdir -p "$legacy/1.0.3"
    touch "$legacy/1.0.3/rdc" "$legacy/1.0.3/rdc.old"
    cleanup_legacy_state >/dev/null 2>&1
    [[ -d "$legacy" ]] && log_fail "cleanup_legacy_state must remove ${legacy}"
    log_pass "cleanup_legacy_state removes legacy versions/ dir"
}

test_cleanup_legacy_state_removes_staged_update() {
    HOME="$(fresh_home)"
    source_install "$HOME"
    local staged="$HOME/.cache/rediacc/staged-update"
    mkdir -p "$staged"
    touch "$staged/rdc-1.0.5"
    cleanup_legacy_state >/dev/null 2>&1
    [[ -d "$staged" ]] && log_fail "cleanup_legacy_state must remove ${staged}"
    log_pass "cleanup_legacy_state removes staged-update/ dir"
}

test_no_versions_constant() {
    HOME="$(fresh_home)"
    source_install "$HOME"
    # The dead "5 versions retained" feature must be gone entirely. If
    # someone reintroduces a VERSIONS_DIR or MAX_VERSIONS variable, the
    # layout would diverge from the new single-bin/rdc model.
    ! (
        set +u
        [[ -n "${VERSIONS_DIR+defined}" || -n "${MAX_VERSIONS+defined}" ]]
    ) ||
        log_fail "VERSIONS_DIR / MAX_VERSIONS must not be defined under the new layout"
    log_pass "legacy VERSIONS_DIR / MAX_VERSIONS constants removed"
}

# Channel resolution (env > rediacc.json::account.updateChannel > 'stable').
# Asymmetry between install.sh defaulting to stable and `rdc update` reading
# the config caused a real user-visible bug: stable install followed by an
# immediate "update" jumping to edge. These tests pin the unified contract.

test_channel_default_stable_when_unset() {
    HOME="$(fresh_home)"
    unset REDIACC_CHANNEL
    source_install "$HOME"
    [[ "$CHANNEL" == "stable" ]] || log_fail "no env, no config -> CHANNEL must be stable, got: $CHANNEL"
    log_pass "no env, no config -> stable"
}

test_channel_inherits_from_config() {
    HOME="$(fresh_home)"
    unset REDIACC_CHANNEL
    mkdir -p "$HOME/.config/rediacc"
    cat >"$HOME/.config/rediacc/rediacc.json" <<'EOF'
{"schemaVersion":3,"id":"11111111-1111-4111-a111-111111111111","version":1,"encryption":{"mode":"plaintext"},"account":{"accountServer":"https://eu.rediacc.com","updateChannel":"edge"}}
EOF
    source_install "$HOME"
    [[ "$CHANNEL" == "edge" ]] || log_fail "config account.updateChannel=edge must be inherited, got: $CHANNEL"
    log_pass "no env + config account.updateChannel=edge -> edge"
}

test_channel_env_overrides_config() {
    HOME="$(fresh_home)"
    mkdir -p "$HOME/.config/rediacc"
    cat >"$HOME/.config/rediacc/rediacc.json" <<'EOF'
{"schemaVersion":3,"id":"11111111-1111-4111-a111-111111111111","version":1,"encryption":{"mode":"plaintext"},"account":{"updateChannel":"edge"}}
EOF
    REDIACC_CHANNEL=stable source_install "$HOME"
    [[ "$CHANNEL" == "stable" ]] || log_fail "REDIACC_CHANNEL=stable must override config edge, got: $CHANNEL"
    log_pass "env REDIACC_CHANNEL=stable overrides config edge"
}

test_channel_malformed_config_falls_back() {
    HOME="$(fresh_home)"
    unset REDIACC_CHANNEL
    mkdir -p "$HOME/.config/rediacc"
    printf 'not even valid json {{{' >"$HOME/.config/rediacc/rediacc.json"
    source_install "$HOME"
    [[ "$CHANNEL" == "stable" ]] || log_fail "malformed config must fall back to stable, got: $CHANNEL"
    log_pass "malformed config -> stable fallback"
}

test_channel_config_without_updateChannel() {
    HOME="$(fresh_home)"
    unset REDIACC_CHANNEL
    mkdir -p "$HOME/.config/rediacc"
    cat >"$HOME/.config/rediacc/rediacc.json" <<'EOF'
{"schemaVersion":3,"id":"11111111-1111-4111-a111-111111111111","version":1,"encryption":{"mode":"plaintext"},"account":{"accountServer":"https://eu.rediacc.com","region":"eu"}}
EOF
    source_install "$HOME"
    [[ "$CHANNEL" == "stable" ]] || log_fail "config without updateChannel must default to stable, got: $CHANNEL"
    log_pass "config without updateChannel -> stable"
}

test_detect_platform
test_detect_arch
test_write_install_config_default_noop
test_write_install_config_channel_only
test_write_install_config_custom_releases
test_write_install_config_present_no_jq_untouched
test_cleanup_legacy_state_removes_versions_dir
test_cleanup_legacy_state_removes_staged_update
test_no_versions_constant
test_channel_default_stable_when_unset
test_channel_inherits_from_config
test_channel_env_overrides_config
test_channel_malformed_config_falls_back
test_channel_config_without_updateChannel

echo ""
log_pass "all install.sh unit cases"

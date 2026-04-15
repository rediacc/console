#!/usr/bin/env bash
#
# Unit test for install.sh's write_install_config function.
#
# Covers the four failure modes the worker rewrite can land us in when a user
# runs `curl -fsSL https://<preview>.rediacc.com/install.sh | bash`:
#
#   worker_full         — both CHANNEL and SERVER_URL rewritten → full server.json
#   worker_channel_only — only CHANNEL rewritten → minimal server.json
#                         with accountServer=https://www.rediacc.com (fail-safe
#                         recovery path; rdc update still picks up edge)
#   worker_server_only  — only SERVER_URL rewritten; install.sh's server-info
#                         lookup auto-detects channel (mocked via python)
#   worker_none         — neither rewritten → no server.json written at all
#
# The test sources install.sh with REDIACC_INSTALL_SH_SOURCE_ONLY=1 so that
# `main` does not execute, then calls write_install_config with a fake $HOME
# per case and asserts on the resulting config file.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALL_SH="$REPO_ROOT/packages/www/public/install.sh"

if [[ ! -f "$INSTALL_SH" ]]; then
  echo "FAIL: install.sh not found at $INSTALL_SH" >&2
  exit 1
fi

PASS=0
FAIL=0

fail() {
  FAIL=$((FAIL + 1))
  echo "  ✗ $1" >&2
}

pass() {
  PASS=$((PASS + 1))
  echo "  ✓ $1"
}

run_case() {
  local name="$1"
  local channel="$2"
  local server_url="$3"
  local expect_file="$4"     # "yes" or "no"
  local expect_channel="$5"  # empty if expect_file=no
  local expect_account="$6"  # empty if expect_file=no

  local tmp_home
  tmp_home=$(mktemp -d)
  local config_file="$tmp_home/.config/rediacc/server.json"

  # shellcheck disable=SC1090
  (
    export HOME="$tmp_home"
    export XDG_CONFIG_HOME="$tmp_home/.config"
    # install.sh reads these at top-level, then write_install_config uses the
    # CHANNEL/SERVER_URL globals that result.
    if [[ -n "$channel" && "$channel" != "stable" ]]; then
      export REDIACC_CHANNEL="$channel"
    else
      unset REDIACC_CHANNEL
    fi
    if [[ -n "$server_url" ]]; then
      export REDIACC_SERVER_URL="$server_url"
    else
      unset REDIACC_SERVER_URL
    fi
    unset REDIACC_RELEASES_URL
    export REDIACC_INSTALL_SH_SOURCE_ONLY=1
    # Stub `success` quiet after sourcing so install.sh's own banner logic
    # doesn't clutter test output.
    source "$INSTALL_SH"
    success() { :; }
    write_install_config
  )

  if [[ "$expect_file" == "no" ]]; then
    if [[ -f "$config_file" ]]; then
      fail "$name: expected no server.json, but file was written: $(cat "$config_file")"
    else
      pass "$name: no server.json written"
    fi
  else
    if [[ ! -f "$config_file" ]]; then
      fail "$name: expected server.json, but none was written"
    else
      local got_channel got_account
      got_channel=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['updateChannel'])" "$config_file")
      got_account=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['accountServer'])" "$config_file")
      if [[ "$got_channel" == "$expect_channel" && "$got_account" == "$expect_account" ]]; then
        pass "$name: channel=$got_channel accountServer=$got_account"
      else
        fail "$name: got channel=$got_channel accountServer=$got_account; expected channel=$expect_channel accountServer=$expect_account"
      fi

      # Verify 0o600 mode
      local mode
      mode=$(stat -c '%a' "$config_file" 2>/dev/null || stat -f '%OLp' "$config_file" 2>/dev/null)
      if [[ "$mode" != "600" ]]; then
        fail "$name: expected mode 600, got $mode"
      fi
    fi
  fi

  rm -rf "$tmp_home"
}

echo "install.sh write_install_config matrix:"

# worker_full: both rewrites landed — ideal case
run_case "worker_full" \
  "edge" "https://edge.rediacc.com" \
  "yes" "edge" "https://edge.rediacc.com"

# worker_channel_only: fail-safe recovery path (the gap we closed)
run_case "worker_channel_only" \
  "edge" "" \
  "yes" "edge" "https://www.rediacc.com"

# worker_none: neither rewrite landed — install.sh can't infer origin,
# leaves no config so rdc update falls back to default stable.
run_case "worker_none" \
  "stable" "" \
  "no" "" ""

# worker_server_only: SERVER_URL rewritten but CHANNEL not. install.sh's
# server-info lookup would auto-detect in production; with no reachable
# server, we still write server.json with the accountServer field and
# the default channel. Fail-safe: rdc doctor reveals the channel and
# the user can switch with `rdc update --channel edge`.
run_case "worker_server_only" \
  "stable" "https://unreachable-server.invalid" \
  "yes" "stable" "https://unreachable-server.invalid"

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi

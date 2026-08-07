#!/bin/bash
# drill universe — the config-as-a-universe battery, scripted.
#
#   ./run.sh drill universe [--selftest] [--no-restart] [--keep-work]
#
# WHAT IT PROVES. A config is a whole universe: its own account server, its own
# keys, its own machines, and its own API token beside it as
# api-token-<name>.json. The four properties that make that claim true, and
# that this drill asserts rather than assumes:
#
#   1. SOURCE LABELS.  `rdc config current` reports WHERE each resolved value
#      came from, and the three tiers (env > config > built-in default) are
#      distinguishable in the output. A label that silently says "default" for
#      a value that actually came from the environment is how an operator ends
#      up debugging the wrong server.
#   2. SELECTION PRECEDENCE.  --config beats REDIACC_CONFIG beats the built-in
#      name. Asserted in that order, including the three-way case where the
#      flag has to win against an env var that is also set.
#   3. ISOLATION.  Operating on one config must not touch another's file. The
#      assertion is an md5 of each config file taken before and after work on
#      its neighbour, because "it looked fine" is exactly the check that misses
#      a stray write.
#   4. PER-CONFIG TOKENS.  A login under one config creates that config's token
#      file and no other's, and a logout removes it.
#
# COST. Headless and CI-able: no VMs, no Docker, no privileged operations. It
# does drive a real `./run.sh account dev` gateway, because the token-file
# assertions need a real login against a real server; a mocked one would prove
# nothing about the CLI's own path resolution. Runtime is dominated by the
# gateway restart (roughly a minute).
#
# OUTPUT FORMAT. The drill pins REDIACC_DEFAULT_OUTPUT=table and asks for JSON
# explicitly where it parses JSON. Left alone, a drill measures the wrong
# surface silently: the CLI auto-selects json output whenever stdout is not a
# TTY, and a drill's stdout is never a TTY.
#
# SANDBOX. Everything happens under a throwaway XDG_CONFIG_HOME, so the
# operator's real ~/.config/rediacc is never read or written. That is also why
# this drill does NOT use `./rdc.sh --dev`: that wrapper mode writes its seeded
# dev config to a hard-coded "$HOME/.config/rediacc/dev.json" while the CLI
# itself resolves the directory through XDG_CONFIG_HOME, so under a sandbox the
# two disagree. The drill seeds its own configs with `rdc config init --server`
# instead, which goes through the CLI's own resolution.
#
# SELFTEST. `--selftest` plants exactly one assertion that cannot pass, right
# after setup, and the run must exit non-zero. A --selftest run that exits 0
# means the accounting is broken; drill_summary says so explicitly.

set -euo pipefail

DRILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../../.ci/scripts/lib/common.sh
source "$DRILL_DIR/../../.ci/scripts/lib/common.sh"
# shellcheck source=lib.sh
source "$DRILL_DIR/lib.sh"

RESTART_GATEWAY=1
DRILL_EMAIL="drill-universe@rediacc.io"
DRILL_PASSWORD="DrillUniverse123!"
RDC="$DRILL_ROOT_DIR/rdc.sh"

# Set by setup_sandbox / setup_account.
CONFIG_DIR=""
SERVER_URL=""
API_TOKEN=""

drill_teardown_hook() {
    # Nothing to undo outside the work directory: every config, token and cache
    # this drill writes lives under the sandbox XDG_CONFIG_HOME, which the
    # shared teardown removes with the work dir.
    return 0
}

drill_parse_args() {
    drill_parse_common_args "$@"
    local arg
    for arg in ${DRILL_ARGS_REST+"${DRILL_ARGS_REST[@]}"}; do
        case "$arg" in
            --no-restart) RESTART_GATEWAY=0 ;;
            *)
                log_error "Unknown option: $arg"
                echo "Usage: ./run.sh drill universe [--selftest] [--no-restart] [--keep-work]" >&2
                exit 2
                ;;
        esac
    done
}

setup_sandbox() {
    drill_step "Setup: isolated config directory"
    CONFIG_DIR="$DRILL_WORK/xdg/rediacc"
    export XDG_CONFIG_HOME="$DRILL_WORK/xdg"
    mkdir -p "$CONFIG_DIR"
    drill_note "XDG_CONFIG_HOME=$XDG_CONFIG_HOME"
    # Pin the output format. Without this the drill would measure the WRONG
    # surface without saying so: cli.ts's resolveOutputFormat auto-selects json
    # whenever stdout is not a TTY, which a drill's stdout never is, so every
    # assertion would silently describe the machine-readable path while
    # claiming to describe what an operator sees. `table` is the operator's
    # view; the JSON assertions below opt in with an explicit -o json.
    export REDIACC_DEFAULT_OUTPUT=table
    ssh-keygen -t ed25519 -N '' -q -C drill-universe -f "$DRILL_WORK/id_ed25519"
}

setup_account() {
    if [[ "$RESTART_GATEWAY" == "1" ]]; then
        drill_gateway_restart
    else
        drill_step "Reusing the running dev gateway (--no-restart)"
        if ! drill_gateway_alive; then
            log_error "No healthy dev gateway. Start one: ./run.sh account dev"
            exit 1
        fi
        DRILL_GATEWAY_PORT=$(drill_gateway_port)
    fi

    SERVER_URL="$(drill_server_url)"
    drill_step "Setup: dev login, subscription and API token on $SERVER_URL"
    drill_account_ensure_login "$DRILL_EMAIL" "$DRILL_PASSWORD"
    drill_account_ensure_subscription "$DRILL_EMAIL" PROFESSIONAL

    local jar="$DRILL_WORK/cookies.txt"
    drill_account_session "$DRILL_EMAIL" "$DRILL_PASSWORD" "$jar"
    local sub
    sub=$(drill_account_subscription_id "$jar")
    API_TOKEN=$(drill_account_mint_token "$jar" "$sub" drill-universe \
        '["license:read","subscription:read"]')
    drill_note "subscription $sub, token ${API_TOKEN:0:12}..."
}

# -----------------------------------------------------------------------------
# Phase 1 — the default config and its source labels
# -----------------------------------------------------------------------------
phase_default_config() {
    drill_step "Phase 1: the default config is created on first use, with labelled sources"

    drill_run "$RDC" config current -o json
    assert_exit 0 "config current succeeds on a cold config directory"
    assert_stdout_json 'd.data.name' rediacc "default config is named rediacc"
    assert_stdout_json 'd.data.fileExists' true "its file was created automatically"
    assert_stdout_json 'd.data.accountServerSource' default \
        "accountServer is labelled as coming from the built-in default"
    assert_stdout_json 'd.data.updateChannelSource' default \
        "updateChannel is labelled as coming from the built-in default"
    assert_stdout_json 'd.data.tokenState' missing "no token yet"

    local token_file
    token_file=$(drill_json 'd.data.tokenFile' <"$DRILL_STDOUT")
    assert_equal "$CONFIG_DIR/api-token-rediacc.json" "$token_file" \
        "the default config's token path is api-token-rediacc.json beside it"
}

# -----------------------------------------------------------------------------
# Phase 2 — named configs
# -----------------------------------------------------------------------------
phase_named_configs() {
    drill_step "Phase 2: two named configs, each a self-contained universe"

    drill_run "$RDC" config init drill-a --server "$SERVER_URL"
    assert_exit 0 "config init drill-a succeeds"
    assert_stdout_empty "config init writes nothing to stdout (the success line is stderr)"
    assert_stderr_contains 'Config "drill-a" initialized' \
        "config init reports success on stderr"
    assert_file_exists "$CONFIG_DIR/drill-a.json" "drill-a.json was written"

    # The same failure told twice, because the two renderings are different
    # code paths and only one of them is what a pipeline consumes: in text mode
    # the reason belongs on stderr with stdout left clean, and in json mode it
    # becomes an envelope on stdout with success=false.
    drill_run "$RDC" config init drill-a --server "$SERVER_URL"
    assert_exit 2 "re-initializing an existing config is a validation error (exit 2)"
    assert_stderr_contains 'already exists' "text mode puts the reason on stderr"
    assert_stdout_empty "text mode leaves stdout clean on failure"

    drill_run "$RDC" -o json config init drill-a --server "$SERVER_URL"
    assert_exit 2 "the json rendering keeps the same exit code"
    assert_stdout_json 'd.success' false "json mode reports success=false on stdout"
    assert_stdout_json 'd.errors[0].code' VALIDATION_ERROR \
        "and classifies it as a validation error"

    drill_run "$RDC" config init drill-b --server "$SERVER_URL"
    assert_exit 0 "config init drill-b succeeds"
    assert_file_exists "$CONFIG_DIR/drill-b.json" "drill-b.json was written"
}

# -----------------------------------------------------------------------------
# Phase 3 — source labels and selection precedence
# -----------------------------------------------------------------------------
phase_precedence() {
    drill_step "Phase 3: source labels and --config / REDIACC_CONFIG precedence"

    drill_run env REDIACC_CONFIG=drill-a "$RDC" config current -o json
    assert_exit 0 "REDIACC_CONFIG selects a config"
    assert_stdout_json 'd.data.name' drill-a "REDIACC_CONFIG=drill-a selects drill-a"
    assert_stdout_json 'd.data.accountServerSource' config \
        "a server stored in the config file is labelled source=config"
    assert_stdout_json 'd.data.accountServer' "$SERVER_URL" \
        "and the value is the one config init stored"

    drill_run env REDIACC_CONFIG=drill-a REDIACC_ACCOUNT_SERVER=http://127.0.0.1:1 \
        "$RDC" config current -o json
    assert_stdout_json 'd.data.accountServerSource' 'env REDIACC_ACCOUNT_SERVER' \
        "REDIACC_ACCOUNT_SERVER overrides the config file and is labelled as env"
    assert_stdout_json 'd.data.accountServer' 'http://127.0.0.1:1' \
        "and the env value is the one that wins"

    # The three-way case: the flag must beat an env var that is also set.
    drill_run env REDIACC_CONFIG=drill-a "$RDC" --config drill-b config current -o json
    assert_stdout_json 'd.data.name' drill-b \
        "--config beats REDIACC_CONFIG when both name a config"

    drill_run "$RDC" config current -o json
    assert_stdout_json 'd.data.name' rediacc \
        "with neither flag nor env, the built-in default name applies"
}

# -----------------------------------------------------------------------------
# Phase 4 — isolation
# -----------------------------------------------------------------------------
phase_isolation() {
    drill_step "Phase 4: operating on one config leaves the others byte-identical"

    local a_before b_before a_after b_after
    a_before=$(drill_md5 "$CONFIG_DIR/drill-a.json")
    b_before=$(drill_md5 "$CONFIG_DIR/drill-b.json")
    drill_note "md5 drill-a=$a_before drill-b=$b_before"

    # A real mutation of drill-b: config ssh set writes credentials into the
    # config file and touches no network (the same call .ci/scripts/private/
    # concurrent-fork-isolation-test.sh uses to register a key headlessly).
    drill_run env REDIACC_CONFIG=drill-b "$RDC" config ssh set --key "$DRILL_WORK/id_ed25519"
    assert_exit 0 "config ssh set mutates drill-b"

    b_after=$(drill_md5 "$CONFIG_DIR/drill-b.json")
    a_after=$(drill_md5 "$CONFIG_DIR/drill-a.json")
    assert_not_equal "$b_before" "$b_after" "drill-b.json changed (the write landed)"
    assert_equal "$a_before" "$a_after" "drill-a.json is byte-identical after work on drill-b"
    assert_equal "absent" "$(drill_md5 "$CONFIG_DIR/api-token-drill-a.json")" \
        "no token file appeared for drill-a"
}

# -----------------------------------------------------------------------------
# Phase 5 — per-config token files
# -----------------------------------------------------------------------------
phase_tokens() {
    drill_step "Phase 5: per-config token files"

    local a_before b_before
    a_before=$(drill_md5 "$CONFIG_DIR/drill-a.json")
    b_before=$(drill_md5 "$CONFIG_DIR/drill-b.json")

    drill_run env REDIACC_CONFIG=drill-a "$RDC" subscription login \
        --token "$API_TOKEN" --server "$SERVER_URL"
    assert_exit 0 "subscription login --token succeeds against the dev gateway"
    assert_file_exists "$CONFIG_DIR/api-token-drill-a.json" \
        "the login wrote api-token-drill-a.json"
    assert_file_absent "$CONFIG_DIR/api-token-drill-b.json" \
        "and did NOT write a token for drill-b"
    assert_file_absent "$CONFIG_DIR/api-token-rediacc.json" \
        "nor for the default config"

    local stored_server
    stored_server=$(drill_json 'd.serverUrl' <"$CONFIG_DIR/api-token-drill-a.json")
    assert_equal "$SERVER_URL" "$stored_server" \
        "the token file records the server it was validated against"

    drill_run env REDIACC_CONFIG=drill-a "$RDC" config current -o json
    assert_stdout_json 'd.data.tokenState' ready "drill-a reports tokenState=ready"

    drill_run env REDIACC_CONFIG=drill-b "$RDC" config current -o json
    assert_stdout_json 'd.data.tokenState' missing \
        "drill-b still reports tokenState=missing (tokens do not leak across configs)"

    assert_equal "$b_before" "$(drill_md5 "$CONFIG_DIR/drill-b.json")" \
        "drill-b.json is byte-identical after drill-a logged in"
    assert_not_equal "$a_before" "$(drill_md5 "$CONFIG_DIR/drill-a.json")" \
        "drill-a.json recorded its server identity"

    drill_run env REDIACC_CONFIG=drill-a "$RDC" subscription logout
    assert_exit 0 "subscription logout succeeds"
    assert_file_absent "$CONFIG_DIR/api-token-drill-a.json" \
        "logout removed drill-a's token file"
}

main() {
    drill_parse_args "$@"
    drill_init universe
    setup_sandbox
    drill_selftest_probe
    if [[ "$DRILL_SELFTEST" == "1" ]]; then
        # Stop before the gateway: the selftest proves the accounting, and
        # making it wait a minute for a server it never queries would be a
        # reason not to run it.
        drill_note "selftest mode: skipping the live phases"
        drill_summary
        return
    fi
    setup_account
    phase_default_config
    phase_named_configs
    phase_precedence
    phase_isolation
    phase_tokens
    drill_summary
}

main "$@"

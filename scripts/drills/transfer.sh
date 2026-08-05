#!/bin/bash
# drill transfer — the config-storage ("transfer") battery, scripted.
#
#   ./run.sh drill transfer [--selftest] [--no-restart] [--keep-work]
#
# WHAT IT PROVES. Config storage is the feature an operator trusts with the
# only copy of their universe, so the interesting cases are the ones where the
# server is NOT there:
#
#   1. SEED ON ENABLE.  Enrolling against a store that holds nothing for this
#      config pushes the local config as version 1 and says so.
#   2. OFFLINE READ.    With the server unreachable, reads still succeed from
#      the encrypted local cache, the staleness warning goes to STDERR, and
#      stdout stays clean for whatever is parsing it.
#   3. FAIL-CLOSED WRITE. With the server unreachable, a write REFUSES rather
#      than saving locally and hoping. Asserted with the exact message, the
#      exit code, and a byte-comparison proving the cache was not corrupted on
#      the way out.
#   4. SECOND DEVICE.   A second box enrolls headlessly against the SAME store
#      through the password slot, does NOT re-seed, and pulls the content the
#      first box pushed. The account login on that path goes through the real
#      two-factor challenge, satisfied from the dev-only TOTP route.
#
# COST. Headless and CI-able: no VMs. It needs `./run.sh account dev` including
# its Docker side, because the config store is backed by RustFS; without it the
# store cannot be seeded and the drill fails fast saying so rather than
# reporting a green that skipped everything.
#
# OFFLINE IS SIMULATED WITH A SHIM, not by stopping the gateway. See the
# offline-simulation block in lib.sh: a restart may move the gateway to a
# different port, which would strand configs that recorded the old one.
#
# TWO WORKAROUNDS FOR DEFECTS FOUND WHILE WRITING THIS DRILL. Both are
# reported, neither is silent:
#
#   a. `rdc config init <name> --server <url>` records the server but not that
#      server's E2E public key, and the first tunnelled request then encrypts
#      with the built-in PRODUCTION key. Against any non-production server that
#      fails as a bare `Error: Decryption failed` with no hint. `rdc config
#      current` syncs the key correctly, so the drill runs it once as a warm-up
#      right after init.
#   b. An API token binds to the client IP on FIRST use, and a request that
#      arrives through the E2E tunnel presents a different client IP than a
#      direct one. So nothing here may touch the account token with curl before
#      the CLI does: the drill mints tokens over the SESSION (cookie) API only,
#      and lets the CLI be the token's first user. When that ordering is
#      violated the server answers 403 and the CLI reports "This organization
#      requires a passkey to unlock config storage" — which is not what
#      happened, and cost an hour to see through.
#
# SELFTEST. `--selftest` plants exactly one assertion that cannot pass, right
# after setup, and the run must exit non-zero.

set -euo pipefail

DRILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../../.ci/scripts/lib/common.sh
source "$DRILL_DIR/../../.ci/scripts/lib/common.sh"
# shellcheck source=lib.sh
source "$DRILL_DIR/lib.sh"

RESTART_GATEWAY=1
# A fresh dev user, and therefore a fresh config store, on every run. Reusing
# one across runs does not work today: the second run's `config remote enable
# --password` against the store the first run left behind dies with the raw
# Node WebCrypto text "Error: The operation failed for an operation-specific
# reason" (an OperationError from a failed unwrap, surfaced verbatim). That is
# a real defect and is reported as one; the drill must not depend on it either
# way, so it starts from a store nothing has touched.
DRILL_EMAIL="drill-transfer-$(date +%s)@rediacc.io"
DRILL_PASSWORD="DrillTransfer123!"
# Constant by necessity, not by laziness: an idempotent re-seed of the config
# store cannot re-wrap the CEK without the prior password, so the seeding route
# uses a fixed one and so must anyone unlocking that slot.
STORE_PASSWORD="DrillStore123!"
RDC="$DRILL_ROOT_DIR/rdc.sh"

DEVICE1_HOME=""
DEVICE2_HOME=""
CONFIG_NAME="drill-transfer"
SERVER_URL=""

drill_teardown_hook() {
    # Every artefact lives under the work directory (two sandbox XDG homes and
    # the shim), which the shared teardown removes. The dev user and its store
    # stay in the dev database on purpose: they are idempotent, and wiping them
    # would fight any other session using the same gateway.
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
                echo "Usage: ./run.sh drill transfer [--selftest] [--no-restart] [--keep-work]" >&2
                exit 2
                ;;
        esac
    done
}

# preflight_keyring — every phase below enrolls a device, and enrollment stores
# its unlocked slot secret in the OS keyring: packages/cli/src/utils/secure-storage.ts
# uses `keyctl` against the `@u` user keyring on Linux, for the PASSWORD method as
# much as for passkeys (config-remote-password.ts writes `rdc:pw:<uuid>` there, and
# the shared deriveCek reads it back). A GitHub runner job has no accessible session
# keyring, so the read fails with `keyctl_read_alloc: Permission denied` and the CLI
# reports a missing secret four assertions deep, blaming the store.
#
# Checked here so the drill names the missing dependency instead of failing inside
# an assertion that reads like a config-storage bug. Follows the declared-skip
# discipline the e2e suites and renet already use (E2E_EXPECT_NO_CLUSTER_VMS,
# RENET_EXPECT_NO_ACCOUNT_SERVER): absent WITH a declaration is a loud skip, absent
# WITHOUT one is a red. A silent skip is the failure mode that rule exists to
# prevent, so an undeclared missing keyring must never pass quietly.
preflight_keyring() {
    drill_step "Preflight: an OS keyring the CLI can actually write to"
    # ROUND TRIP, not just a write. A GitHub runner lets `keyctl add` SUCCEED and
    # then denies the read with `keyctl_read_alloc: Permission denied`, so a probe
    # that only adds reports the keyring usable and the drill still dies four
    # assertions deep — which is exactly what the first version of this preflight
    # did. Mirror the two calls secure-storage.ts actually makes on the read path
    # (`keyctl search @u user <key>` then `keyctl pipe <id>`), and require the
    # value to come back intact.
    local probe_key='rediacc-drill-keyring-probe' probe_id='' probe_val=''
    if command -v keyctl >/dev/null 2>&1 &&
        keyctl add user "$probe_key" probe-ok @u >/dev/null 2>&1; then
        probe_id=$(keyctl search @u user "$probe_key" 2>/dev/null || true)
        [[ -n "$probe_id" ]] && probe_val=$(keyctl pipe "$probe_id" 2>/dev/null || true)
        keyctl purge user "$probe_key" >/dev/null 2>&1 || true
        if [[ "$probe_val" == "probe-ok" ]]; then
            drill_note "keyring usable (keyctl @u write+read round trip)"
            return 0
        fi
        drill_note "keyctl add succeeded but the read back did not — treating the keyring as unusable"
    fi

    if [[ -n "${DRILL_EXPECT_NO_KEYRING:-}" ]]; then
        printf '\n'
        log_warn "config-storage enrollment: SKIPPED BY DECLARATION"
        log_warn "  reason (DRILL_EXPECT_NO_KEYRING): ${DRILL_EXPECT_NO_KEYRING}"
        log_warn "  every phase of this drill enrolls a device, and enrollment needs the"
        log_warn "  OS keyring (keyctl @u) that this environment does not provide."
        printf '\n'
        drill_summary
        exit 0
    fi

    log_error "No usable OS keyring: the write+read round trip against @u did not complete."
    log_error "Enrollment stores its slot secret there (secure-storage.ts), so every"
    log_error "phase of this drill would fail four assertions deep, blaming the store."
    log_error "On a machine that genuinely has no keyring, declare it:"
    log_error "  DRILL_EXPECT_NO_KEYRING='<why>' ./run.sh drill transfer"
    exit 1
}

setup_sandbox() {
    drill_step "Setup: two isolated config directories (device 1 and device 2)"
    DEVICE1_HOME="$DRILL_WORK/device1"
    DEVICE2_HOME="$DRILL_WORK/device2"
    mkdir -p "$DEVICE1_HOME/rediacc" "$DEVICE2_HOME/rediacc"
    # See the universe drill: without pinning the format, a drill measures the
    # json surface while describing the human one, because stdout is not a TTY.
    export REDIACC_DEFAULT_OUTPUT=table
    export XDG_CONFIG_HOME="$DEVICE1_HOME"
    drill_note "device 1: $DEVICE1_HOME"
    drill_note "device 2: $DEVICE2_HOME"
    # Two keys: the online write in phase 2 sets the first, the refused offline
    # write in phase 3 tries to set the second. Re-setting the SAME key could
    # be a no-op that never reaches the save path, which would make phase 3
    # pass for the wrong reason.
    ssh-keygen -t ed25519 -N '' -q -C drill-transfer-a -f "$DRILL_WORK/id_ed25519"
    ssh-keygen -t ed25519 -N '' -q -C drill-transfer-b -f "$DRILL_WORK/id_ed25519_b"
}

setup_gateway() {
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
    drill_proxy_start
    SERVER_URL="$(drill_proxy_url)"
}

setup_store() {
    drill_step "Setup: dev user, subscription and a password-unlockable config store"
    drill_account_ensure_login "$DRILL_EMAIL" "$DRILL_PASSWORD"
    drill_account_ensure_subscription "$DRILL_EMAIL" PROFESSIONAL

    local seed
    seed=$(drill_api_post /test/seed-config-store \
        "{\"email\":\"$DRILL_EMAIL\",\"password\":\"$STORE_PASSWORD\"}")
    local store_id
    store_id=$(drill_json 'd.storeId' <<<"$seed")
    if [[ -z "$store_id" ]]; then
        log_error "Could not seed a config store: $seed"
        log_error "Config storage needs the RustFS container from ./run.sh account dev (Docker)."
        exit 1
    fi
    drill_note "store $store_id seeded, password slot provisioned"
}

# mint_token <name> — a fresh account token, minted over the SESSION api only.
# Nothing else may use it before the CLI does (see workaround (b) in the header).
#
# The result lands in the global MINTED_TOKEN rather than on stdout, so the
# caller does not need a command substitution: that would run the whole login
# chain in a subshell and throw away DRILL_2FA_USED, which phase 4 asserts on.
MINTED_TOKEN=""
mint_token() {
    local name="$1"
    local jar="$DRILL_WORK/cookies-$name.txt"
    drill_account_session "$DRILL_EMAIL" "$DRILL_PASSWORD" "$jar"
    local sub
    sub=$(drill_account_subscription_id "$jar")
    MINTED_TOKEN=$(drill_account_mint_token "$jar" "$sub" "$name" \
        '["license:read","subscription:read","config:enroll"]')
}

# init_config <xdg-home> <config-name> — create a config and warm it up.
init_config() {
    local home="$1" name="$2"
    XDG_CONFIG_HOME="$home" "$RDC" config init "$name" --server "$SERVER_URL" >/dev/null 2>&1
    # Workaround (a): sync the target server's E2E public key before anything
    # tunnels. Without this the first tunnelled call dies as "Decryption failed".
    XDG_CONFIG_HOME="$home" REDIACC_CONFIG="$name" "$RDC" config current -o json >/dev/null 2>&1
}

# -----------------------------------------------------------------------------
# Phase 1 — seed on enable
# -----------------------------------------------------------------------------
phase_seed_on_enable() {
    drill_step "Phase 1: enrolling against an empty store seeds it at version 1"

    init_config "$DEVICE1_HOME" "$CONFIG_NAME"
    mint_token drill-transfer-d1

    drill_run env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        REDIACC_TOKEN="$MINTED_TOKEN" REDIACC_CONFIG_PASSWORD="$STORE_PASSWORD" \
        REDIACC_DEFAULT_OUTPUT=table \
        "$RDC" config remote enable --password --api-url "$SERVER_URL"
    assert_exit 0 "headless password enrollment succeeds with no browser"
    assert_stderr_contains 'Store was empty; pushed the local config as version 1.' \
        "the empty store was seeded, and the CLI said so"
    assert_stderr_contains 'Remote config enabled.' "enrollment reported success"
    assert_stdout_empty "enable writes nothing to stdout"

    drill_run env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        "$RDC" config remote status -o json
    assert_exit 0 "config remote status succeeds"
    assert_stdout_json 'd.data.status' connected "the config reports status=connected"
    assert_stdout_json 'd.data.cachedVersion' 1 "the cached version is 1 (the seed)"
    assert_stdout_json 'd.data.apiUrl' "$SERVER_URL" "and it is bound to the drill's server"
}

# -----------------------------------------------------------------------------
# Phase 2 — offline reads served from the cache
# -----------------------------------------------------------------------------
phase_offline_read() {
    drill_step "Phase 2: an online write pushes, then reads survive the server going away"

    # An online write first, so the cache holds something the server produced
    # (version 2) rather than only the seed. config ssh set is the write of
    # choice here because it changes the config and touches nothing outside it;
    # `machine add` would ALSO write an SSH alias into the user's real home
    # (and on WSL into the WINDOWS home), which no sandbox here can contain.
    drill_run env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        REDIACC_DEFAULT_OUTPUT=table \
        "$RDC" config ssh set --key "$DRILL_WORK/id_ed25519"
    assert_exit 0 "a write succeeds while the server is reachable"

    drill_run env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        "$RDC" config remote status -o json
    assert_stdout_json 'd.data.cachedVersion' 2 \
        "the write went to the server: the cached version advanced to 2"

    drill_proxy_stop
    drill_note "offline shim stopped — the config's server is now refusing connections"

    drill_run env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        REDIACC_DEFAULT_OUTPUT=table "$RDC" machine list
    assert_exit 0 "a read still succeeds while the server is unreachable"
    assert_stderr_contains 'is unreachable; serving config' \
        "the staleness warning names the unreachable server"
    assert_stderr_contains 'from the offline cache' "and says the answer came from the cache"
    assert_stderr_contains 'Changes cannot be saved until the server is reachable.' \
        "and warns that writes will not work"
    assert_stdout_not_contains 'offline cache' \
        "the warning stays on stderr and does not corrupt stdout"

    # The json path, on a command that emits an envelope: the cached state is
    # served intact with the server gone.
    drill_run env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        "$RDC" config remote status -o json
    assert_exit 0 "the json read also succeeds offline"
    assert_stdout_json 'd.success' true "the envelope reports success"
    assert_stdout_json 'd.data.cachedVersion' 2 \
        "and still reports version 2, served from the cache"
}

# -----------------------------------------------------------------------------
# Phase 3 — writes fail closed while offline
# -----------------------------------------------------------------------------
phase_fail_closed_write() {
    drill_step "Phase 3: while offline, a write refuses instead of saving locally"

    local config_file="$DEVICE1_HOME/rediacc/$CONFIG_NAME.json"
    local before
    before=$(drill_md5 "$config_file")

    drill_run env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        REDIACC_DEFAULT_OUTPUT=table \
        "$RDC" config ssh set --key "$DRILL_WORK/id_ed25519_b"
    assert_exit 1 "the write fails (exit 1)"
    assert_stderr_contains 'Cannot save: config' "the refusal names the config and the server"
    assert_stderr_contains 'The change was NOT saved.' \
        "and states plainly that nothing was written"
    assert_equal "$before" "$(drill_md5 "$config_file")" \
        "the cached config file is byte-identical (no torn or partial write)"
}

# -----------------------------------------------------------------------------
# Phase 4 — a second device enrolls against the same store
# -----------------------------------------------------------------------------
phase_second_device() {
    drill_step "Phase 4: a second device enrolls headlessly and pulls, without re-seeding"
    drill_proxy_start
    drill_note "server reachable again"

    # Prove the read path recovered before drawing conclusions from device 2.
    drill_run env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        REDIACC_DEFAULT_OUTPUT=table "$RDC" machine list
    assert_exit 0 "device 1 reads again once the server is back"
    assert_stderr_not_contains 'from the offline cache' \
        "and no longer warns about the cache"

    init_config "$DEVICE2_HOME" "$CONFIG_NAME"
    mint_token drill-transfer-d2
    DRILL_LAST_CMD="POST /auth/login + /auth/2fa/verify for $DRILL_EMAIL"
    assert_equal 1 "$DRILL_2FA_USED" \
        "the second device's account login went through the two-factor challenge"

    drill_run env XDG_CONFIG_HOME="$DEVICE2_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        REDIACC_TOKEN="$MINTED_TOKEN" REDIACC_CONFIG_PASSWORD="$STORE_PASSWORD" \
        REDIACC_DEFAULT_OUTPUT=table \
        "$RDC" config remote enable --password --api-url "$SERVER_URL"
    assert_exit 0 "the second device enrolls with the same password slot"
    assert_stderr_not_contains 'Store was empty' \
        "and does NOT re-seed: the store already holds this config"
    assert_stderr_contains 'Remote config enabled.' "enrollment reported success"

    drill_run env XDG_CONFIG_HOME="$DEVICE2_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        "$RDC" config remote status -o json
    assert_exit 0 "device 2 reports its remote status"
    assert_stdout_json 'd.data.status' connected "device 2 is connected"
    assert_stdout_json 'd.data.cachedVersion' 2 \
        "device 2 pulled version 2 — the version device 1's write produced"

    local d1_status d2_store d2_config
    d1_status=$(env XDG_CONFIG_HOME="$DEVICE1_HOME" REDIACC_CONFIG="$CONFIG_NAME" \
        "$RDC" config remote status -o json 2>/dev/null)
    d2_store=$(drill_json 'd.data.storeId' <"$DRILL_STDOUT")
    d2_config=$(drill_json 'd.data.configId' <"$DRILL_STDOUT")
    assert_equal "$(drill_json 'd.data.storeId' <<<"$d1_status")" "$d2_store" \
        "both devices point at the same store"
    assert_equal "$(drill_json 'd.data.configId' <<<"$d1_status")" "$d2_config" \
        "and at the same config inside it (device 2 joined, it did not fork a new one)"
}

main() {
    drill_parse_args "$@"
    drill_init transfer
    setup_sandbox
    drill_selftest_probe
    if [[ "$DRILL_SELFTEST" == "1" ]]; then
        drill_note "selftest mode: skipping the live phases"
        drill_summary
        return
    fi
    # After the selftest gate: --selftest proves the harness without touching a
    # gateway or a keyring, so it must stay runnable where enrollment cannot be.
    preflight_keyring
    setup_gateway
    setup_store
    phase_seed_on_enable
    phase_offline_read
    phase_fail_closed_write
    phase_second_device
    drill_summary
}

main "$@"

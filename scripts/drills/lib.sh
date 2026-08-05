#!/bin/bash
# Shared harness for the campaign drills dispatched by `./run.sh drill <name>`.
#
# Sourced by scripts/drills/universe.sh, scripts/drills/transfer.sh and
# scripts/drills/license.sh. It exists because the three drills used to be
# prose in a design doc: a list of commands a human ran by hand, whose
# "expected" column was a sentence rather than an assertion. This turns them
# into scripts with explicit setup, numbered assertions, teardown, and a
# non-zero exit on any failure.
#
# WHAT THE ASSERTIONS CAPTURE. Every command under test runs through
# drill_run, which sends stdout and stderr to SEPARATE files and records the
# exit code. That separation is the point: this campaign's surfaces put the
# machine-readable answer on stdout and the human warning on stderr (the
# offline staleness warning is the clearest case), so a merged capture cannot
# tell a correct implementation from one that writes the warning onto stdout
# and corrupts every `-o json` consumer downstream.
#
# THE TWO DEV-GATEWAY FOOTGUNS, baked in rather than documented:
#   1. `npx tsx src/entry/dev-gateway.ts` does NOT hot-reload. A gateway that
#      has been up since before the last server edit serves STALE code, and the
#      drill then measures the previous revision. So the drills RESTART the
#      gateway themselves (drill_gateway_restart) instead of trusting one they
#      find running.
#   2. A restart rotates every dev password (.ci/lib/account.sh's
#      account_dev_credentials mints fresh ones with `openssl rand`) and may
#      land on a DIFFERENT port (account_allocate_ports scans for 3 consecutive
#      free ports from the preferred base). Nothing here may remember a port or
#      a credential between runs: drill_gateway_port re-reads .account-state and
#      drill_account_env re-reads private/account/.env on every call, and the
#      drills mint their own logins through the dev-only /test routes rather
#      than scraping the credentials banner.
#
# PROVE THE INSTRUMENT. Every drill accepts --selftest, which plants exactly one
# assertion that cannot pass. A --selftest run MUST exit non-zero; if it does
# not, the accounting is broken and drill_summary fails the run for that reason
# specifically, rather than reporting a green that means nothing.
#
# Shell conventions: sourced after .ci/scripts/lib/common.sh, which supplies
# log_step/log_info/log_error (all on stderr), the colour variables and
# `set -euo pipefail`.

# =============================================================================
# STATE
# =============================================================================

DRILL_NAME=""
DRILL_WORK=""
DRILL_STDOUT=""
DRILL_STDERR=""
DRILL_GATEWAY_LOG=""
DRILL_GATEWAY_PGID=""
DRILL_GATEWAY_PORT=""
DRILL_CODE=0
DRILL_SELFTEST=0
DRILL_STARTED_AT=0

DRILL_COUNT=0
DRILL_FAILURES=0
DRILL_ROWS=()

# Description of the command drill_run last executed, for failure diagnostics.
DRILL_LAST_CMD=""

DRILL_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# =============================================================================
# LIFECYCLE
# =============================================================================

# drill_init <name>
# Creates the per-run work directory and installs the teardown trap. Each drill
# defines its own drill_teardown_hook; the shared teardown calls it first, then
# stops any gateway this run started and removes the work directory.
drill_init() {
    DRILL_NAME="$1"
    DRILL_STARTED_AT=$(date +%s)
    DRILL_WORK="$(mktemp -d "${TMPDIR:-/tmp}/rediacc-drill-${DRILL_NAME}-XXXXXX")"
    DRILL_STDOUT="$DRILL_WORK/stdout.txt"
    DRILL_STDERR="$DRILL_WORK/stderr.txt"
    DRILL_GATEWAY_LOG="$DRILL_WORK/gateway.log"
    : >"$DRILL_STDOUT"
    : >"$DRILL_STDERR"
    trap drill_teardown EXIT
    printf '\n=== drill %s ===\n' "$DRILL_NAME"
    printf 'work dir : %s\n' "$DRILL_WORK"
    printf 'selftest : %s\n\n' "$([[ "$DRILL_SELFTEST" == "1" ]] && echo "ON (one planted failure expected)" || echo off)"
}

# Shared EXIT trap. Every step is best-effort: a teardown that aborts halfway
# leaves the gateway or the sandbox behind, which is worse than a noisy exit.
drill_teardown() {
    local rc=$?
    if declare -F drill_teardown_hook >/dev/null 2>&1; then
        drill_teardown_hook || true
    fi
    drill_proxy_stop || true
    drill_gateway_stop || true
    if [[ -n "$DRILL_WORK" && -d "$DRILL_WORK" && "${DRILL_KEEP_WORK:-0}" != "1" ]]; then
        rm -rf "$DRILL_WORK" || true
    elif [[ -n "$DRILL_WORK" ]]; then
        printf 'work dir kept: %s\n' "$DRILL_WORK"
    fi
    return $rc
}

# drill_step <text> — a phase header, on stdout with the assertion stream.
drill_step() {
    printf '\n-- %s\n' "$*"
}

# drill_note <text> — an aside that is neither a phase nor an assertion.
drill_note() {
    printf '   %s\n' "$*"
}

# =============================================================================
# COMMAND EXECUTION
# =============================================================================

# drill_run <cmd> [args...]
# Runs a command with stdout and stderr captured to SEPARATE files and the exit
# code recorded in DRILL_CODE. Never aborts the drill: an assertion, not the
# shell, decides whether a non-zero exit is a failure.
drill_run() {
    DRILL_LAST_CMD="$*"
    : >"$DRILL_STDOUT"
    : >"$DRILL_STDERR"
    DRILL_CODE=0
    "$@" >"$DRILL_STDOUT" 2>"$DRILL_STDERR" || DRILL_CODE=$?
    return 0
}

# drill_setup_run <cmd...> — a SETUP command that must succeed. Unlike the bare
# `cmd >/dev/null 2>&1` pattern this replaces, a failure here prints both
# captured streams and the exit code before aborting, so a dying setup step can
# never take its diagnosis to the grave with the work dir (that exact silent
# death cost a live debugging session on 2026-08-04).
drill_setup_run() {
    drill_run "$@"
    if [[ "$DRILL_CODE" -ne 0 ]]; then
        log_error "setup command failed (exit $DRILL_CODE): $DRILL_LAST_CMD"
        log_error "--- captured stdout ---"
        drill_stdout >&2
        log_error "--- captured stderr ---"
        drill_stderr >&2
        exit 2
    fi
}

# drill_stdout / drill_stderr — the captured streams of the last drill_run.
drill_stdout() {
    cat "$DRILL_STDOUT"
}

drill_stderr() {
    cat "$DRILL_STDERR"
}

# drill_json <js-expression>
# Reads JSON on stdin and prints one field. The expression is evaluated against
# `d`, e.g. `drill_json 'd.data.name' <file.json`. node rather than jq: node is
# already a hard requirement of every wrapper in this repo, jq is not.
drill_json() {
    node -e '
      const raw = require("fs").readFileSync(0, "utf8");
      let d;
      try { d = JSON.parse(raw || "{}"); } catch { process.exit(3); }
      let v;
      try {
        v = new Function("d", "return (" + process.argv[1] + ");")(d);
      } catch {
        // An expression that walks into a missing branch yields "", the same
        // as an absent field. A stack trace here would be noise: the assertion
        // that called this is the thing that should report the failure.
        process.exit(4);
      }
      process.stdout.write(v === undefined || v === null ? "" : String(v));
    ' "$1"
}

# =============================================================================
# ASSERTIONS
# =============================================================================
#
# Assertions are numbered automatically in call order. Hand-assigned ids drift
# the moment a step is inserted; the summary table carries the description, and
# the number exists only to point at a row.

_drill_record() {
    local status="$1" desc="$2"
    DRILL_COUNT=$((DRILL_COUNT + 1))
    DRILL_ROWS+=("$(printf '%02d\t%s\t%s' "$DRILL_COUNT" "$status" "$desc")")
    if [[ "$status" == "PASS" ]]; then
        printf '  %02d  %bPASS%b  %s\n' "$DRILL_COUNT" "$GREEN" "$NC" "$desc"
    else
        DRILL_FAILURES=$((DRILL_FAILURES + 1))
        printf '  %02d  %bFAIL%b  %s\n' "$DRILL_COUNT" "$RED" "$NC" "$desc"
    fi
}

# _drill_fail <desc> <detail...> — records a failure and dumps the evidence to
# stderr, so a piped stdout stays a readable table while the diagnosis survives.
_drill_fail() {
    local desc="$1"
    shift
    _drill_record FAIL "$desc"
    {
        printf '\n--- assertion %02d FAILED: %s\n' "$DRILL_COUNT" "$desc"
        printf '    command : %s\n' "${DRILL_LAST_CMD:-<none>}"
        printf '    exit    : %s\n' "$DRILL_CODE"
        local line
        for line in "$@"; do
            printf '    %s\n' "$line"
        done
        if [[ -s "$DRILL_STDOUT" ]]; then
            printf '    stdout  |\n'
            sed 's/^/    | /' "$DRILL_STDOUT" | tail -20
        else
            printf '    stdout  | <empty>\n'
        fi
        if [[ -s "$DRILL_STDERR" ]]; then
            printf '    stderr  |\n'
            sed 's/^/    | /' "$DRILL_STDERR" | tail -20
        else
            printf '    stderr  | <empty>\n'
        fi
    } >&2
}

# assert_exit <expected-code> <description>
assert_exit() {
    local expected="$1" desc="$2"
    if [[ "$DRILL_CODE" == "$expected" ]]; then
        _drill_record PASS "$desc"
    else
        _drill_fail "$desc" "expected exit $expected, got $DRILL_CODE"
    fi
}

# assert_stdout_contains <needle> <description>
assert_stdout_contains() {
    local needle="$1" desc="$2"
    if grep -qF -- "$needle" "$DRILL_STDOUT"; then
        _drill_record PASS "$desc"
    else
        _drill_fail "$desc" "stdout does not contain: $needle"
    fi
}

# assert_stdout_not_contains <needle> <description>
# The other half of the stream-placement rule: a human warning that leaks onto
# stdout corrupts every consumer that parses stdout.
assert_stdout_not_contains() {
    local needle="$1" desc="$2"
    if grep -qF -- "$needle" "$DRILL_STDOUT"; then
        _drill_fail "$desc" "stdout unexpectedly contains: $needle"
    else
        _drill_record PASS "$desc"
    fi
}

# assert_stderr_contains <needle> <description>
assert_stderr_contains() {
    local needle="$1" desc="$2"
    if grep -qF -- "$needle" "$DRILL_STDERR"; then
        _drill_record PASS "$desc"
    else
        _drill_fail "$desc" "stderr does not contain: $needle"
    fi
}

# assert_stderr_not_contains <needle> <description>
assert_stderr_not_contains() {
    local needle="$1" desc="$2"
    if grep -qF -- "$needle" "$DRILL_STDERR"; then
        _drill_fail "$desc" "stderr unexpectedly contains: $needle"
    else
        _drill_record PASS "$desc"
    fi
}

# assert_stdout_empty <description>
# The stream-placement assertion: a command whose whole answer is a success
# message must leave stdout clean for the next pipe stage.
assert_stdout_empty() {
    local desc="$1"
    if [[ -s "$DRILL_STDOUT" ]]; then
        _drill_fail "$desc" "stdout is not empty"
    else
        _drill_record PASS "$desc"
    fi
}

# assert_stdout_json <js-expression> <expected> <description>
assert_stdout_json() {
    local expr="$1" expected="$2" desc="$3"
    local actual=""
    actual=$(drill_json "$expr" <"$DRILL_STDOUT" 2>/dev/null) || actual="<unparseable>"
    if [[ "$actual" == "$expected" ]]; then
        _drill_record PASS "$desc"
    else
        _drill_fail "$desc" "$expr: expected \"$expected\", got \"$actual\""
    fi
}

# assert_equal <expected> <actual> <description>
assert_equal() {
    local expected="$1" actual="$2" desc="$3"
    if [[ "$expected" == "$actual" ]]; then
        _drill_record PASS "$desc"
    else
        _drill_fail "$desc" "expected \"$expected\", got \"$actual\""
    fi
}

# assert_not_equal <unexpected> <actual> <description>
assert_not_equal() {
    local unexpected="$1" actual="$2" desc="$3"
    if [[ "$unexpected" != "$actual" ]]; then
        _drill_record PASS "$desc"
    else
        _drill_fail "$desc" "expected a value different from \"$unexpected\""
    fi
}

# assert_file_exists <path> <description>
assert_file_exists() {
    local path="$1" desc="$2"
    if [[ -f "$path" ]]; then
        _drill_record PASS "$desc"
    else
        _drill_fail "$desc" "file missing: $path"
    fi
}

# assert_file_absent <path> <description>
assert_file_absent() {
    local path="$1" desc="$2"
    if [[ -e "$path" ]]; then
        _drill_fail "$desc" "file unexpectedly present: $path"
    else
        _drill_record PASS "$desc"
    fi
}

# drill_md5 <path> — a content fingerprint, or the sentinel "absent". A distinct
# sentinel rather than an empty string: the isolation assertions compare two
# fingerprints, and "the file vanished" must not read as "unchanged".
drill_md5() {
    local path="$1"
    if [[ -f "$path" ]]; then
        md5sum "$path" | cut -d' ' -f1
    else
        echo "absent"
    fi
}

# =============================================================================
# SELFTEST (prove the instrument)
# =============================================================================

# drill_selftest_probe
# No-op unless --selftest was passed, in which case it plants exactly one
# assertion that cannot pass. Call it once, after setup, so a --selftest run is
# cheap and does not depend on the drill's live prerequisites.
drill_selftest_probe() {
    [[ "$DRILL_SELFTEST" == "1" ]] || return 0
    drill_step "selftest: planting one assertion that cannot pass"
    DRILL_LAST_CMD="<selftest control: no command>"
    assert_equal "this-value-is-planted" "and-this-one-differs" \
        "selftest control (planted failure — this drill MUST exit non-zero)"
}

# =============================================================================
# SUMMARY
# =============================================================================

# drill_summary — prints the table and returns non-zero on any failure. Under
# --selftest it ALSO fails a run in which nothing failed: a planted defect the
# harness cannot see means the harness is not measuring anything.
drill_summary() {
    local elapsed=$(($(date +%s) - DRILL_STARTED_AT))
    local passed=$((DRILL_COUNT - DRILL_FAILURES))
    printf '\n=== drill %s summary ===\n' "$DRILL_NAME"
    printf '  %-4s %-6s %s\n' "##" "RESULT" "ASSERTION"
    local row
    for row in "${DRILL_ROWS[@]}"; do
        printf '  %-4s %-6s %s\n' \
            "$(cut -f1 <<<"$row")" "$(cut -f2 <<<"$row")" "$(cut -f3- <<<"$row")"
    done
    printf '  %s\n' "-------------------------------------------------------------"
    printf '  %d assertions: %d passed, %d failed  (%ds)\n' \
        "$DRILL_COUNT" "$passed" "$DRILL_FAILURES" "$elapsed"

    if [[ "$DRILL_SELFTEST" == "1" ]]; then
        if [[ "$DRILL_FAILURES" -eq 0 ]]; then
            printf '  %bSELFTEST DID NOT FIRE%b: a planted failure went unnoticed, so this\n' "$RED" "$NC"
            printf '  harness is not measuring anything. Fix the accounting before trusting a green run.\n'
            return 1
        fi
        printf '  %bselftest fired as designed%b (exit is non-zero on purpose)\n' "$GREEN" "$NC"
        return 1
    fi

    if [[ "$DRILL_FAILURES" -gt 0 ]]; then
        printf '  %bdrill %s FAILED%b\n' "$RED" "$DRILL_NAME" "$NC"
        return 1
    fi

    # A run that asserted NOTHING is not a pass, and must not print the word a
    # dashboard or a grep for PASSED will find. A declared skip exits 0 on
    # purpose -- the caller has said in advance why the environment cannot host
    # this drill -- but "0 assertions: 0 passed, 0 failed / PASSED" reads as
    # proof to anyone who did not scroll up to the declaration, which is the
    # vacuous-green shape these drills exist to catch. Say SKIPPED instead and
    # keep the exit code.
    if [[ "$DRILL_COUNT" -eq 0 ]]; then
        printf '  %bdrill %s SKIPPED%b (0 assertions ran — nothing was proven)\n' \
            "$YELLOW" "$DRILL_NAME" "$NC"
        return 0
    fi

    printf '  %bdrill %s PASSED%b\n' "$GREEN" "$DRILL_NAME" "$NC"
    return 0
}

# =============================================================================
# DEV GATEWAY
# =============================================================================

# drill_gateway_port — the CURRENT port, re-read from .account-state every call.
# Never cache this in a drill: a restart may move the gateway (see the header).
drill_gateway_port() {
    local state="$DRILL_ROOT_DIR/.account-state"
    [[ -f "$state" ]] || return 1
    local port
    port=$(grep '^gateway_port=' "$state" 2>/dev/null | cut -d= -f2)
    [[ -n "$port" ]] || return 1
    printf '%s' "$port"
}

# drill_account_env <KEY> — read one value out of private/account/.env by grep.
# Deliberately never `source`: that file also holds ED25519_PRIVATE_KEY,
# X25519_PRIVATE_KEY, JWT_SECRET and API_KEY, and sourcing would push all four
# into the environment of every command the drill runs. Same rule rdc.sh follows.
drill_account_env() {
    local key="$1" env_file="$DRILL_ROOT_DIR/private/account/.env"
    [[ -f "$env_file" ]] || return 1
    grep -E "^${key}=" "$env_file" 2>/dev/null | tail -1 | cut -d= -f2-
}

# drill_gateway_alive — true when the recorded port answers /health.
drill_gateway_alive() {
    local port
    port=$(drill_gateway_port) || return 1
    curl -sf -m 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1
}

# drill_gateway_restart
# Stops whatever is running and starts a fresh `./run.sh account dev`, then
# waits for it to be healthy and caches the port for THIS run only.
#
# setsid puts the gateway in its own process group. Without it the tsx child
# survives a kill of the run.sh wrapper (account_cleanup only tracks the vite
# and astro PIDs, not the foreground gateway) and keeps the port bound, which
# breaks the offline leg of `drill transfer`: the server would still answer
# after the drill believed it had stopped it.
drill_gateway_restart() {
    drill_step "Restarting the dev gateway (tsx does not hot-reload — a long-running gateway serves stale server code)"
    drill_gateway_stop
    local t0
    t0=$(date +%s)
    setsid "$DRILL_ROOT_DIR/run.sh" account dev >"$DRILL_GATEWAY_LOG" 2>&1 &
    DRILL_GATEWAY_PGID=$!
    drill_note "gateway log: $DRILL_GATEWAY_LOG"
    drill_gateway_wait_started "$t0"
}

# drill_gateway_wait_started <epoch-seconds>
# Waits for a state file NEWER than the given timestamp (account_dev writes
# `started=<epoch>` last), then for /health. Comparing against a timestamp is
# what distinguishes the new instance from the stale state file the previous one
# left behind.
drill_gateway_wait_started() {
    local since="$1" waited=0 started=""
    while [[ $waited -lt 300 ]]; do
        if [[ -f "$DRILL_ROOT_DIR/.account-state" ]]; then
            started=$(grep '^started=' "$DRILL_ROOT_DIR/.account-state" 2>/dev/null | cut -d= -f2)
            if [[ -n "$started" ]] && [[ "$started" -ge "$since" ]] && drill_gateway_alive; then
                DRILL_GATEWAY_PORT=$(drill_gateway_port)
                drill_note "gateway healthy on port $DRILL_GATEWAY_PORT after ${waited}s"
                return 0
            fi
        fi
        if [[ -n "$DRILL_GATEWAY_PGID" ]] && ! kill -0 "$DRILL_GATEWAY_PGID" 2>/dev/null; then
            log_error "The dev gateway exited during startup. Last 40 lines of $DRILL_GATEWAY_LOG:"
            tail -40 "$DRILL_GATEWAY_LOG" >&2 || true
            return 1
        fi
        sleep 2
        waited=$((waited + 2))
    done
    log_error "Dev gateway did not become healthy within ${waited}s. Last 40 lines of $DRILL_GATEWAY_LOG:"
    tail -40 "$DRILL_GATEWAY_LOG" >&2 || true
    return 1
}

# drill_gateway_stop
# Stops the gateway this run started, and only that one: the process group
# first, then a port sweep for anything that outlived the signal (the same
# belt-and-braces account_dev itself uses on its previous instance).
drill_gateway_stop() {
    local port="${DRILL_GATEWAY_PORT:-}"
    if [[ -n "$DRILL_GATEWAY_PGID" ]]; then
        kill -TERM -- "-$DRILL_GATEWAY_PGID" 2>/dev/null || kill -TERM "$DRILL_GATEWAY_PGID" 2>/dev/null || true
        local waited=0
        while [[ $waited -lt 15 ]] && kill -0 "$DRILL_GATEWAY_PGID" 2>/dev/null; do
            sleep 1
            waited=$((waited + 1))
        done
        kill -KILL -- "-$DRILL_GATEWAY_PGID" 2>/dev/null || true
        wait "$DRILL_GATEWAY_PGID" 2>/dev/null || true
        DRILL_GATEWAY_PGID=""
    fi
    if [[ -n "$port" ]] && command -v lsof >/dev/null 2>&1; then
        local offset survivors
        for offset in 0 1 2; do
            survivors=$(lsof -ti:$((port + offset)) 2>/dev/null || true)
            [[ -n "$survivors" ]] && echo "$survivors" | xargs -r kill -9 2>/dev/null || true
        done
    fi
    return 0
}

# drill_gateway_wait_down — waits for the recorded port to stop answering, so
# the offline leg cannot race a socket that is still draining.
drill_gateway_wait_down() {
    local waited=0
    while [[ $waited -lt 30 ]]; do
        drill_gateway_alive || return 0
        sleep 1
        waited=$((waited + 1))
    done
    log_error "Gateway port ${DRILL_GATEWAY_PORT:-?} still answering after ${waited}s"
    return 1
}

# =============================================================================
# OFFLINE SIMULATION (a TCP shim in front of the gateway)
# =============================================================================
#
# WHY NOT JUST STOP THE GATEWAY. A config records the server URL it is bound
# to, and `./run.sh account dev` does not guarantee the same port twice: it
# scans for three consecutive free ports from a preferred base, so a restart
# can land somewhere else and strand every config the drill wrote. Pointing the
# configs at a shim the drill owns decouples "the config's address" from "where
# the gateway happens to be listening": going offline is stopping the shim, and
# a gateway that comes back on a different port needs only drill_proxy_retarget.
#
# The shim re-reads the target port from a file on every connection, so it
# survives a restart with no restart of its own.

DRILL_PROXY_PORT=""
DRILL_PROXY_PID=""

# drill_free_port — a TCP port that is free right now (bind to 0, read, close).
drill_free_port() {
    node -e '
      const net = require("net");
      const s = net.createServer();
      s.listen(0, "127.0.0.1", () => {
        const p = s.address().port;
        s.close(() => process.stdout.write(String(p)));
      });
    '
}

# drill_proxy_url — the address configs should be pointed at.
drill_proxy_url() {
    printf 'http://127.0.0.1:%s' "$DRILL_PROXY_PORT"
}

# drill_proxy_retarget — repoint the shim at the gateway's CURRENT port.
drill_proxy_retarget() {
    drill_gateway_port >"$DRILL_WORK/gateway-port"
}

# drill_proxy_start — start (or restart) the shim on its stable port.
drill_proxy_start() {
    [[ -n "$DRILL_PROXY_PORT" ]] || DRILL_PROXY_PORT=$(drill_free_port)
    drill_proxy_retarget
    cat >"$DRILL_WORK/proxy.js" <<'PROXY_JS'
// Minimal TCP shim: accept on argv[2], forward to the port named in argv[3].
// The target is re-read per connection so a gateway restart on a different
// port needs no restart here.
const net = require('net');
const fs = require('fs');
const listenPort = Number(process.argv[2]);
const targetFile = process.argv[3];
net
  .createServer((client) => {
    let target;
    try {
      target = Number(fs.readFileSync(targetFile, 'utf8').trim());
    } catch {
      client.destroy();
      return;
    }
    const upstream = net.connect(target, '127.0.0.1');
    upstream.on('error', () => client.destroy());
    client.on('error', () => upstream.destroy());
    client.pipe(upstream).pipe(client);
  })
  .listen(listenPort, '127.0.0.1');
PROXY_JS
    node "$DRILL_WORK/proxy.js" "$DRILL_PROXY_PORT" "$DRILL_WORK/gateway-port" \
        >"$DRILL_WORK/proxy.log" 2>&1 &
    DRILL_PROXY_PID=$!
    local waited=0
    while [[ $waited -lt 20 ]]; do
        if curl -sf -m 2 "$(drill_proxy_url)/health" >/dev/null 2>&1; then
            drill_note "offline shim listening on $(drill_proxy_url) -> gateway :$(drill_gateway_port)"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done
    log_error "Offline shim did not come up on port $DRILL_PROXY_PORT"
    return 1
}

# drill_proxy_stop — take the shim down; connections are then refused, which is
# the shape of "server unreachable" the CLI classifies as RemoteUnreachableError.
drill_proxy_stop() {
    if [[ -n "$DRILL_PROXY_PID" ]]; then
        kill "$DRILL_PROXY_PID" 2>/dev/null || true
        wait "$DRILL_PROXY_PID" 2>/dev/null || true
        DRILL_PROXY_PID=""
    fi
    return 0
}

# =============================================================================
# ACCOUNT SERVER (dev-only /test routes + the headless auth chain)
# =============================================================================

# DRILL_HOST — the address the gateway is ADVERTISED at, which is not always the
# address it is reached at from here.
#
# The account server stamps a license blob's `renewalUrl` from the request's own
# Host header (private/account/src/app.ts, envConfig.baseUrl falls back to
# `${url.protocol}//${url.host}` because PUBLIC_SITE_URL is unset in dev). So a
# drill that talks to the gateway on 127.0.0.1 mints blobs whose renewalUrl is
# 127.0.0.1 — and on the MACHINE that address is the machine itself, so renewal
# dies with `connection refused` and the drill reports it as a licensing defect.
#
# It is ONE variable rather than two because the API-token IP binding
# (middleware/api-token.ts) keys on the same Host header: a token first used
# against one host name and then against another is refused with "Token is bound
# to a different IP address". Every caller in a run must therefore agree on the
# host, which is exactly what a single global buys.
#
# Default 127.0.0.1 — the drills whose subjects never leave this box keep the
# behaviour they had.
DRILL_HOST="${DRILL_HOST:-127.0.0.1}"

# drill_bridge_host <net-base> — this workstation's own address on a VM network,
# e.g. `drill_bridge_host 192.168.111` -> 192.168.111.254 (the renet11 bridge).
# Prints nothing and fails when no interface sits on that network, so a caller
# can fall back rather than advertise an address nothing can reach.
drill_bridge_host() {
    local net_base="$1" addr
    addr=$(ip -4 -o addr show 2>/dev/null |
        awk '{print $4}' | cut -d/ -f1 |
        grep -m1 "^${net_base}\.") || return 1
    [[ -n "$addr" ]] || return 1
    printf '%s' "$addr"
}

# drill_api_base — the account API root of the running gateway.
drill_api_base() {
    printf 'http://%s:%s/account/api/v1' "$DRILL_HOST" "$(drill_gateway_port)"
}

# drill_server_url — what a config's accountServer should point at.
drill_server_url() {
    printf 'http://%s:%s' "$DRILL_HOST" "$(drill_gateway_port)"
}

# drill_api_post <path> <json-body> [curl-args...] — prints the response body.
# Exits non-zero on a transport failure but NOT on an HTTP error status; the
# caller inspects the body, which is where the account server puts its reason.
drill_api_post() {
    local path="$1" body="$2"
    shift 2
    curl -sS -X POST "$(drill_api_base)$path" \
        -H 'Content-Type: application/json' -d "$body" "$@"
}

# drill_account_ensure_login <email> <password>
# Mints (or repoints) a dev login with a password the drill chooses. The drills
# never scrape the credentials banner: those passwords rotate on every restart,
# and /test/ensure-login is idempotent, so choosing the password is both simpler
# and immune to the rotation footgun.
drill_account_ensure_login() {
    local email="$1" password="$2"
    drill_api_post /test/ensure-login \
        "{\"email\":\"$email\",\"password\":\"$password\"}" >/dev/null
}

# drill_account_ensure_subscription <email> <plan-code> [max-activations]
#
# maxActivations is optional and, when given, seeds the activation cap at
# creation (integer 1..10000; the route defaults to 5). Pass it whenever a
# drill asserts anything about the cap, so the assertion pins a value the drill
# chose rather than a constant living in the dev server.
#
# It is a SEEDING lever only: the route deletes the customer's existing
# subscriptions and creates a new one, so calling it again mid-drill would
# orphan every licence already issued under the old subscription id. Lowering a
# cap on a LIVE subscription is drill_account_patch_subscription's job.
drill_account_ensure_subscription() {
    local email="$1" plan="$2" max="${3:-}"
    local body="{\"email\":\"$email\",\"planCode\":\"$plan\"}"
    if [[ -n "$max" ]]; then
        body="{\"email\":\"$email\",\"planCode\":\"$plan\",\"maxActivations\":$max}"
    fi
    drill_api_post /test/ensure-subscription "$body" >/dev/null
}

# drill_account_session <email> <password> <cookie-jar>
# The headless browser-less auth chain: POST /auth/login, and when the account
# has TOTP enabled (POST /test/seed-config-store turns it on — it never relaxes
# the 2FA gate) complete the challenge with a code from the dev-only
# /test/totp-code route. Sets DRILL_2FA_USED to 1 or 0 so a drill can assert
# that the two-factor leg was genuinely exercised rather than skipped.
DRILL_2FA_USED=0
drill_account_session() {
    local email="$1" password="$2" jar="$3"
    local base body challenge code
    base=$(drill_api_base)
    DRILL_2FA_USED=0
    body=$(curl -sS -c "$jar" -X POST "$base/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$email\",\"password\":\"$password\"}")
    challenge=$(drill_json 'd.challengeToken' <<<"$body")
    if [[ -n "$challenge" ]]; then
        DRILL_2FA_USED=1
        code=$(curl -sS -G "$base/test/totp-code" --data-urlencode "email=$email" |
            drill_json 'd.code')
        if [[ -z "$code" ]]; then
            log_error "No TOTP code for $email (is the config store seeded?)"
            return 1
        fi
        body=$(curl -sS -b "$jar" -c "$jar" -X POST "$base/auth/2fa/verify" \
            -H 'Content-Type: application/json' \
            -d "{\"challengeToken\":\"$challenge\",\"code\":\"$code\"}")
    fi
    if [[ -z "$(drill_json 'd.user && d.user.id' <<<"$body")" ]]; then
        log_error "Headless login failed for $email: $body"
        return 1
    fi
    return 0
}

# drill_account_subscription_id <cookie-jar>
drill_account_subscription_id() {
    curl -sS -b "$1" "$(drill_api_base)/portal/subscription" | drill_json 'd.id'
}

# drill_account_mint_token <cookie-jar> <subscription-id> <name> <scopes-json>
# Prints the bearer token. Scopes are a JSON array literal, e.g.
# '["license:read","config:enroll"]'.
drill_account_mint_token() {
    local jar="$1" sub="$2" name="$3" scopes="$4"
    local body
    body=$(curl -sS -b "$jar" -X POST "$(drill_api_base)/api-tokens" \
        -H 'Content-Type: application/json' \
        -d "{\"subscriptionId\":\"$sub\",\"name\":\"$name\",\"scopes\":$scopes}")
    local token
    token=$(drill_json 'd.token' <<<"$body")
    if [[ -z "$token" ]]; then
        log_error "API token mint failed: $body"
        return 1
    fi
    printf '%s' "$token"
}

# drill_account_admin_session <email> <password> <cookie-jar>
# A root session with an elevated window, which is what the admin subscription
# routes require. There is no /test route that lapses a subscription or moves
# its activation cap, so the licensing drill reaches those states the only way
# available: promote to root, elevate, then PUT /admin/subscriptions/:id.
drill_account_admin_session() {
    local email="$1" password="$2" jar="$3"
    drill_api_post /test/promote-admin "{\"email\":\"$email\"}" >/dev/null
    drill_api_post /test/elevate "{\"email\":\"$email\"}" >/dev/null
    drill_account_session "$email" "$password" "$jar"
}

# drill_account_patch_subscription <cookie-jar> <subscription-id> <json-patch>
# Prints the response body. Accepts any field of adminUpdateSubscriptionSchema,
# e.g. '{"status":"suspended"}' or '{"maxActivations":1}'.
drill_account_patch_subscription() {
    local jar="$1" sub="$2" patch="$3"
    curl -sS -b "$jar" -X PUT "$(drill_api_base)/admin/subscriptions/$sub" \
        -H 'Content-Type: application/json' -d "$patch"
}

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

# drill_parse_common_args "$@" — consumes the flags every drill shares and
# leaves the remainder in DRILL_ARGS_REST for the drill's own parser.
#
# It writes globals rather than printing, because the obvious alternative
# (printing the remainder and reading it through a pipe or a process
# substitution) runs this function in a SUBSHELL, where --selftest would set
# DRILL_SELFTEST in a child that then exits: the flag would parse cleanly and
# do nothing.
DRILL_ARGS_REST=()
# Honour an inherited DRILL_KEEP_WORK. A bare `DRILL_KEEP_WORK=0` here clobbered
# the environment, so exporting the variable silently deleted the work dir
# anyway -- a missing convenience rather than a broken promise, since only
# `--keep-work` was ever documented. DRILL_HOST below already uses this idiom.
# The flag still works and still wins.
#
# Do NOT "simplify" the `${DRILL_KEEP_WORK:-0}` at the drill_teardown read site
# to a bare `$DRILL_KEEP_WORK`. It looks redundant now -- this assignment runs
# while lib.sh is sourced, and the EXIT trap is only installed later, inside
# drill_init -- but it is the cheap guard that keeps the trap from aborting
# under `set -u` if that order ever changes. A teardown that dies half-way
# leaves the gateway and the sandbox behind.
DRILL_KEEP_WORK=${DRILL_KEEP_WORK:-0}
drill_parse_common_args() {
    DRILL_ARGS_REST=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --selftest)
                DRILL_SELFTEST=1
                ;;
            --keep-work)
                DRILL_KEEP_WORK=1
                ;;
            *)
                DRILL_ARGS_REST+=("$1")
                ;;
        esac
        shift
    done
}

#!/bin/bash
# Shared contract for the heavy-job local proxies in this directory.
#
# WHAT A PROXY IS. A heavy CI job (linux packages, rdc update, license e2e, the
# ops host check, the docker infra scripts) runs in a workflow OUTSIDE the parity
# surface, so `npm run ci` never exercises it. A proxy is the local stand-in: it
# runs the SAME script CI runs, on a reduced input, so a developer can find the
# breakage before the push instead of after it.
#
# THE ONE RULE THAT MAKES A PROXY HONEST
# --------------------------------------
# It returns 77 when its toolchain is absent, NEVER 0. 77 is the automake
# cannot-run convention, and scripts/ci-runner/pool.ts already maps it to the
# `blocked` status: counted in the footer, recorded in the receipt, WARNED on by
# the pre-push guard. A proxy that exits 0 on a machine without docker is worse
# than no proxy at all, because it converts an unmeasured surface into a green
# one and nothing downstream can tell the difference.
#
# So the exit alphabet is exactly three symbols:
#   0    the real subject ran and passed
#   77   the subject could not be run here; NOT a verdict
#   any other non-zero   the subject ran and there is a real finding
#
# ANTI-VACUITY. proxy_finish REFUSES to exit 0 when zero assertions were made.
# A proxy whose subject silently no-opped, or whose loop matched nothing, is a
# gate that cannot fail, so it is reported as a failure rather than a pass. The
# PASS/CHECK counts are printed on the success line for the same reason: a
# reader can see a number collapse, and cannot see "OK" collapse.
#
# A MISSING TOOL IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE. Every
# proxy_need_* call carries the exact command that installs what is missing, and
# proxy_preflight prints all of them together rather than dying on the first.
#
# Sourced, not executed: no exec bit by design.

# shellcheck shell=bash

PROXY_CANNOT_RUN=77

PROXY_NAME=""
PROXY_SUBJECT=""
PROXY_CHECKS=0
PROXY_FAILURES=0
PROXY_REQS=0
PROXY_MISSING=()

if [[ -t 1 ]]; then
    PROXY_RED=$'\033[0;31m'
    PROXY_GREEN=$'\033[0;32m'
    PROXY_YEL=$'\033[1;33m'
    PROXY_OFF=$'\033[0m'
else
    PROXY_RED="" PROXY_GREEN="" PROXY_YEL="" PROXY_OFF=""
fi

proxy_init() {
    PROXY_NAME="$1"
    PROXY_SUBJECT="$2"
    PROXY_CHECKS=0
    PROXY_FAILURES=0
    PROXY_REQS=0
    PROXY_MISSING=()
    echo "proxy ${PROXY_NAME}: local stand-in for ${PROXY_SUBJECT}"
}

# proxy_need_cmd <command> <fix hint>
proxy_need_cmd() {
    PROXY_REQS=$((PROXY_REQS + 1))
    command -v "$1" >/dev/null 2>&1 || PROXY_MISSING+=("$1 is not on PATH -- fix: $2")
}

# proxy_need_file <path> <fix hint>
proxy_need_file() {
    PROXY_REQS=$((PROXY_REQS + 1))
    [[ -e "$1" ]] || PROXY_MISSING+=("$1 does not exist -- fix: $2")
}

# proxy_need_exec <path> <fix hint>
proxy_need_exec() {
    PROXY_REQS=$((PROXY_REQS + 1))
    [[ -x "$1" ]] || PROXY_MISSING+=("$1 is not an executable file -- fix: $2")
}

proxy_need_passwordless_sudo() {
    PROXY_REQS=$((PROXY_REQS + 1))
    sudo -n true >/dev/null 2>&1 ||
        PROXY_MISSING+=("passwordless sudo is unavailable -- fix: run this on a host where 'sudo -n true' succeeds")
}

# proxy_need_url <url> <fix hint>: a registry or CDN the subject must reach.
# Unreachable is CANNOT-RUN, never a verdict: a proxy must not go red because a
# developer is on a train.
proxy_need_url() {
    PROXY_REQS=$((PROXY_REQS + 1))
    if ! command -v curl >/dev/null 2>&1; then
        PROXY_MISSING+=("curl is not on PATH -- fix: install curl")
        return
    fi
    curl -sS -m 10 -o /dev/null "$1" >/dev/null 2>&1 ||
        PROXY_MISSING+=("$1 is unreachable -- fix: $2")
}

# Refuses on ZERO declared requirements: a preflight that checked nothing would
# green-light every proxy on every host, which is the vacuity this file exists
# to stop.
proxy_preflight() {
    if [[ $PROXY_REQS -eq 0 ]]; then
        echo "${PROXY_RED}proxy ${PROXY_NAME}: declared ZERO requirements${PROXY_OFF}" >&2
        echo "  A preflight that checks nothing cannot report cannot-run, so its" >&2
        echo "  green would mean nothing. Declare what the subject needs." >&2
        exit 2
    fi
    if [[ ${#PROXY_MISSING[@]} -gt 0 ]]; then
        echo "${PROXY_YEL}proxy ${PROXY_NAME}: CANNOT RUN (${#PROXY_MISSING[@]} of ${PROXY_REQS} requirement(s) missing)${PROXY_OFF}" >&2
        local m
        for m in "${PROXY_MISSING[@]}"; do
            echo "  - $m" >&2
        done
        echo "  Exiting ${PROXY_CANNOT_RUN} (cannot-run). This is NOT a pass and NOT a verdict:" >&2
        echo "  ${PROXY_SUBJECT} was not exercised on this host." >&2
        exit "$PROXY_CANNOT_RUN"
    fi
    echo "proxy ${PROXY_NAME}: toolchain complete, ${PROXY_REQS} requirement(s) satisfied"
}

proxy_pass() {
    PROXY_CHECKS=$((PROXY_CHECKS + 1))
    echo "${PROXY_GREEN}PASS:${PROXY_OFF} $1"
}

proxy_fail() {
    PROXY_CHECKS=$((PROXY_CHECKS + 1))
    PROXY_FAILURES=$((PROXY_FAILURES + 1))
    echo "${PROXY_RED}FAIL:${PROXY_OFF} $1" >&2
}

# proxy_expect_exit <expected> <label> -- <command...>
# Runs the command, prints its streams separately on a surprise, and records one
# check either way. `expected` may be a single code or a comma list.
proxy_expect_exit() {
    local expected="$1" label="$2"
    shift 2
    [[ "${1:-}" == "--" ]] && shift
    local out err rc
    out="$(mktemp)"
    err="$(mktemp)"
    set +e
    "$@" >"$out" 2>"$err"
    rc=$?
    set -e
    if [[ ",$expected," == *",$rc,"* ]]; then
        proxy_pass "$label (exit $rc)"
    else
        proxy_fail "$label: expected exit ${expected}, got ${rc}"
        echo "  --- subject stdout (last 40 lines) ---" >&2
        tail -40 "$out" >&2
        echo "  --- subject stderr (last 40 lines) ---" >&2
        tail -40 "$err" >&2
    fi
    PROXY_LAST_STDOUT="$(cat "$out")"
    PROXY_LAST_STDERR="$(cat "$err")"
    PROXY_LAST_RC=$rc
    rm -f "$out" "$err"
    return 0
}

# proxy_expect_contains <haystack> <needle> <label>
proxy_expect_contains() {
    if [[ "$1" == *"$2"* ]]; then
        proxy_pass "$3"
    else
        proxy_fail "$3: expected output to contain '$2'"
    fi
}

proxy_finish() {
    if [[ $PROXY_CHECKS -eq 0 ]]; then
        echo "${PROXY_RED}proxy ${PROXY_NAME}: made ZERO checks${PROXY_OFF}" >&2
        echo "  The proxy is not seeing its subject; its green would mean nothing." >&2
        exit 1
    fi
    if [[ $PROXY_FAILURES -gt 0 ]]; then
        echo "${PROXY_RED}proxy ${PROXY_NAME}: ${PROXY_FAILURES} of ${PROXY_CHECKS} check(s) FAILED${PROXY_OFF}" >&2
        echo "  Subject: ${PROXY_SUBJECT}" >&2
        exit 1
    fi
    echo "${PROXY_GREEN}proxy ${PROXY_NAME}: ${PROXY_CHECKS} check(s) passed, ${PROXY_REQS} requirement(s) present${PROXY_OFF}"
    exit 0
}

# ---------------------------------------------------------------------------
# The library's own both-directions selftest.
#
# It is a REAL PATH removal, not a simulated one: the negative case runs a
# throwaway probe script with PATH pointing at an empty directory, so
# `command -v` genuinely fails the way it would on a host without the tool. A
# selftest that set a "pretend it is missing" flag would prove only that the
# flag works.
#
# BOTH directions, because a preflight that always says cannot-run is as broken
# as one that never does: case 1 must exit 0 with everything present, case 2
# must exit 77 with the tool gone, case 3 must exit 1 when a proxy asserts
# nothing, and case 4 must exit 2 when it declares no requirements at all.
# ---------------------------------------------------------------------------
proxy_lib_selftest() {
    local lib="${BASH_SOURCE[0]}"
    local tmp bin rc fails=0 cases=0
    tmp="$(mktemp -d)"
    bin="$tmp/emptybin"
    mkdir -p "$bin"

    cat >"$tmp/probe.sh" <<PROBE
#!/bin/bash
set -euo pipefail
source "$lib"
proxy_init selftest-probe "a fixture subject"
proxy_need_cmd bash "install bash"
proxy_preflight
proxy_pass "the fixture asserted something"
proxy_finish
PROBE
    cat >"$tmp/vacuous.sh" <<VACUOUS
#!/bin/bash
set -euo pipefail
source "$lib"
proxy_init selftest-vacuous "a fixture subject that asserts nothing"
proxy_need_cmd bash "install bash"
proxy_preflight
proxy_finish
VACUOUS
    cat >"$tmp/noreqs.sh" <<NOREQS
#!/bin/bash
set -euo pipefail
source "$lib"
proxy_init selftest-noreqs "a fixture subject with no declared toolchain"
proxy_preflight
proxy_finish
NOREQS
    chmod +x "$tmp/probe.sh" "$tmp/vacuous.sh" "$tmp/noreqs.sh"

    _case() {
        local want="$1" label="$2"
        shift 2
        cases=$((cases + 1))
        set +e
        "$@" >/dev/null 2>&1
        rc=$?
        set -e
        if [[ $rc -eq $want ]]; then
            echo "${PROXY_GREEN}PASS:${PROXY_OFF} selftest $label (exit $rc)"
        else
            echo "${PROXY_RED}FAIL:${PROXY_OFF} selftest $label: expected $want, got $rc" >&2
            fails=$((fails + 1))
        fi
    }

    _case 0 "toolchain present -> 0" bash "$tmp/probe.sh"
    _case 77 "toolchain removed from PATH -> 77" env -i "PATH=$bin" "$BASH" "$tmp/probe.sh"
    _case 1 "zero checks -> 1, never 0" bash "$tmp/vacuous.sh"
    _case 2 "zero declared requirements -> 2" bash "$tmp/noreqs.sh"

    rm -rf "$tmp"
    if [[ $fails -gt 0 ]]; then
        echo "proxy-lib selftest: $fails of $cases case(s) FAILED" >&2
        return 1
    fi
    echo "proxy-lib selftest: $cases case(s) passed"
    return 0
}

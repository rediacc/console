#!/bin/bash
# Behavioural gate for the dev-stack liveness probes in .ci/lib/account.sh.
#
# WHY THIS EXISTS. On 2026-08-04 `account_rustfs_alive` reported ALIVE for a
# port with nothing on it, and shipped that way long enough to reach CI. The
# capture was:
#
#     code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$url" 2>/dev/null || echo 000)
#     [[ "$code" != "000" ]]
#
# On a refused connection curl PRINTS `000` (that is what %{http_code} yields)
# AND exits non-zero, so `|| echo 000` appended a SECOND one: the captured value
# was `000000`, which is `!= "000"`, so the probe said alive. Downstream,
# account_dev announced "Reusing RustFS already serving on port ..." , never
# started the container, exported CONFIG_R2_* anyway, and the gateway then
# advertised a config store that did not exist.
#
# WHY NO EXISTING GATE COULD HAVE CAUGHT IT. The absence branch of a probe that
# guards a heavy external dependency never executes on a developer machine,
# because the dependency is always present there (RustFS genuinely listens on
# 9100 on the operator's box). It is untested BY CONSTRUCTION, and reading the
# code does not help: the code is not wrong on the path anyone runs. The only
# cure is to exercise the absent case deliberately, which is what this does.
#
# CONTROL-FIRST. Three assertions, and the gate FAILS ITSELF if its own control
# cannot fire:
#   1. closed port  -> the probe must say DEAD   (the defect)
#   2. live port    -> the probe must say ALIVE  (the CONTROL: without this, a
#                      probe hard-wired to `false` would pass assertion 1)
#   3. the historical implementation, re-run inline, MUST say ALIVE on the same
#      closed port — proving this test targets the real bug and is not green by
#      accident against an unrelated code path.
#
# Usage: check-account-probes.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

PROBE_LIB=".ci/lib/account.sh"

log_step "Checking dev-stack liveness probes in $PROBE_LIB..."

if [[ ! -f "$PROBE_LIB" ]]; then
    log_error "$PROBE_LIB not found — this gate has nothing to check, which is a"
    log_error "failure, not a pass: a probe library that vanished cannot be verified."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    log_error "python3 is required to bind the control listener. Refusing to report"
    log_error "green from a run where the control could not fire."
    exit 1
fi

# A port that is definitely free: bind :0, read what the kernel handed out, close.
free_port() {
    python3 -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()'
}

# account.sh sources siblings through $CI_LIB_DIR (account.sh:12), so that MUST
# be exported before sourcing or the load half-fails and the function never
# exists. Sourcing in a subshell keeps its state out of this script.
#
# The load is verified explicitly rather than assumed: without the check below,
# a failed source makes `account_rustfs_alive` missing, the subshell returns
# non-zero, and "not alive" reads as "correctly dead" — assertion 1 would pass
# while testing nothing at all. That is the exact vacuous-green this gate exists
# to prevent, and it happened while writing it.
export CI_LIB_DIR="$SCRIPT_DIR/../../lib"

probe_says_alive() {
    local port="$1"
    (
        # `set +eu` is REQUIRED, and both letters were paid for separately
        # while writing this. account.sh is not safe to source under the strict
        # flags this gate runs with: errexit trips on its re-source guard
        # (account.sh:8, `[[ -n "${ACCOUNT_LIB_LOADED:-}" ]] && return 0`, whose
        # && list returns NON-ZERO on a first load), and nounset trips on the
        # unset variables it and find-port.sh reference. Either one aborts the
        # source part-way, leaving every function below undefined — and a probe
        # that cannot be called reads as "not alive", i.e. the gate would report
        # a PASS on assertion 1 while testing nothing at all. run.sh does not
        # hit this because it does not source the library under strict flags.
        set +eu
        # shellcheck disable=SC1090
        source "$PROBE_LIB" >/dev/null 2>&1
        declare -F account_rustfs_alive >/dev/null || exit 3
        account_rustfs_alive "$port"
    )
}

# Fail loudly if the library cannot be loaded at all: a gate that cannot reach
# its subject must not report on it. `|| load_rc=$?` is required, not stylistic:
# a healthy probe returns non-zero here (port 1 is closed) and `set -e` would
# abort the whole gate before a single assertion ran.
load_rc=0
probe_says_alive 1 >/dev/null 2>&1 || load_rc=$?
if [[ "$load_rc" -eq 3 ]]; then
    log_error "Could not load account_rustfs_alive from $PROBE_LIB (CI_LIB_DIR=$CI_LIB_DIR)."
    log_error "Refusing to report on a probe this gate cannot actually call."
    exit 1
fi

failures=0

# --- 1. THE DEFECT: a closed port must read as dead -------------------------
dead_port="$(free_port)"
if probe_says_alive "$dead_port"; then
    log_error "account_rustfs_alive reported ALIVE for closed port $dead_port."
    log_error "This is the 2026-08-04 defect: check for a reintroduced"
    log_error "\`|| echo 000\` in the curl capture — curl already prints 000 on a"
    log_error "refused connection, so the fallback concatenates to 000000 and"
    log_error "defeats the comparison. Use \`|| true\` INSIDE the substitution."
    failures=$((failures + 1))
else
    log_info "closed port $dead_port reads as dead"
fi

# --- 2. THE CONTROL: a live port must read as alive -------------------------
# Without this, a probe that always returned false would satisfy assertion 1.
live_port="$(free_port)"
python3 -m http.server "$live_port" --bind 127.0.0.1 >/dev/null 2>&1 &
listener_pid=$!
# shellcheck disable=SC2317
cleanup() { kill "$listener_pid" 2>/dev/null || true; }
trap cleanup EXIT

listener_up=0
for _ in $(seq 1 50); do
    if curl -s -o /dev/null -m 1 "http://127.0.0.1:${live_port}/" 2>/dev/null; then
        listener_up=1
        break
    fi
    sleep 0.1
done

if [[ "$listener_up" != "1" ]]; then
    log_error "CONTROL COULD NOT FIRE: no listener came up on $live_port, so a green"
    log_error "result here would prove nothing. Failing rather than reporting a"
    log_error "pass from an assertion that could not fail."
    failures=$((failures + 1))
elif probe_says_alive "$live_port"; then
    log_info "live port $live_port reads as alive (control fired)"
else
    log_error "CONTROL FAILED: account_rustfs_alive reported DEAD for port"
    log_error "$live_port, which is serving. The probe now under-reports — it can"
    log_error "never say yes, which makes assertion 1 meaningless."
    failures=$((failures + 1))
fi

# --- 3. PLANTED DEFECT: the old shape must still be detectable --------------
# Re-run the historical implementation against the same closed port. If it does
# NOT report alive, this gate is no longer testing the bug it was written for
# (curl changed its behaviour, or the port is not actually closed).
old_code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "http://127.0.0.1:${dead_port}/" 2>/dev/null || echo 000)
if [[ "$old_code" != "000" ]]; then
    log_info "planted defect reproduces (old capture = '$old_code' on a closed port)"
else
    log_error "PLANTED DEFECT NO LONGER REPRODUCES: the historical capture yielded"
    log_error "'$old_code' rather than a concatenated value. This gate can no longer"
    log_error "prove it is testing the original defect — re-derive it before trusting"
    log_error "a green run."
    failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
    log_error "$failures probe check(s) failed"
    exit 1
fi

log_info "Dev-stack liveness probes behave correctly (dead, alive, and planted-defect controls all fired)"

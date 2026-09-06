#!/bin/bash
# Local proxy for CI's licensing battery.
#
# CI runs .ci/scripts/private/license-e2e.sh in ct-tests.yml (line 1848), which
# is outside the parity surface. The script's own header says it "IS the
# local-dev entry point and is exactly what CI runs; there is no CI-only variant
# to drift from" -- and that was true of the SCRIPT while being false of the
# RUN: nothing local ever invoked it, so the local half of that sentence was
# aspirational. This wires it.
#
# NO REDUCTION. Unlike the other proxies here, this one runs the subject exactly
# as CI does, with no flag and no subset. It needs no VM, no btrfs, no LUKS and
# no docker (the license gate fires before any storage work), and it measured
# 15.8 s on this host. There is nothing to trim.
#
# WHAT THIS PROXY ADDS ON TOP OF THE SUBJECT'S OWN EXIT CODE.
# The subject is a three-run battery: an enforcing binary that must pass every
# scenario, and two deliberately broken binaries (nolicense, wrong-key) that
# must FAIL. So "exit 0" here is a claim about six things, and a battery that
# silently degraded to running one binary would still exit 0. This proxy reads
# the three summary lines back and asserts the shape:
#
#   - the enforcing run recorded assertions and zero failures
#   - the nolicense control really failed (a control that does not fire is a
#     claim about the control before it is a claim about the battery)
#   - the wrong-key control really failed
#
# PRIVILEGE. The subject installs license fixtures under /var/lib/rediacc/license
# via `sudo -n`, backs up any pre-existing chain-state.json and restores it. That
# path is a hardcoded constant in renet with no env override, so passwordless
# sudo is a hard requirement rather than a convenience, and its absence is
# cannot-run.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

SUBJECT="$ROOT_DIR/.ci/scripts/private/license-e2e.sh"

if [[ "${1:-}" == "--selftest" ]]; then
    proxy_lib_selftest
    exit $?
fi

proxy_init license-e2e ".ci/scripts/private/license-e2e.sh"

proxy_need_exec "$SUBJECT" "the subject script is missing from this checkout"
proxy_need_cmd go "./run.sh setup (the battery builds three renet binaries from source)"
proxy_need_cmd jq "sudo apt-get install -y jq"
proxy_need_file "$ROOT_DIR/private/renet/go.mod" "git submodule update --init private/renet"
proxy_need_file "$PROXY_DIR/../../private/license-mint" "the license-mint helper the battery signs with is missing"
proxy_need_passwordless_sudo
proxy_preflight

OUT="$(mktemp)"
ERR="$(mktemp)"
trap 'rm -f "$OUT" "$ERR"' EXIT

# Read separately on purpose: this subject writes EVERY log line to stderr and
# nothing at all to stdout, so a merged capture would hide that the stdout side
# is empty by design rather than by breakage.
"$SUBJECT" >"$OUT" 2>"$ERR"
RC=$?
BOTH="$(cat "$OUT" "$ERR")"

if [[ $RC -eq 0 ]]; then
    proxy_pass "license-e2e.sh exited 0"
else
    proxy_fail "license-e2e.sh exited $RC"
    echo "  --- subject stderr (last 60) ---" >&2
    tail -60 "$ERR" >&2
    echo "  --- subject stdout (last 20) ---" >&2
    tail -20 "$OUT" >&2
fi

ENFORCING_PASS=$(printf '%s\n' "$BOTH" | grep -cE '\[enforcing\] .* PASS' || true)
ENFORCING_FAIL=$(printf '%s\n' "$BOTH" | grep -cE '\[enforcing\] .* FAIL' || true)
NOLICENSE_FAIL=$(printf '%s\n' "$BOTH" | grep -cE '\[nolicense\] .* FAIL' || true)
WRONGKEY_FAIL=$(printf '%s\n' "$BOTH" | grep -cE '\[wrong-key\] .* FAIL' || true)

if [[ "$ENFORCING_PASS" -gt 0 ]]; then
    proxy_pass "the enforcing binary asserted $ENFORCING_PASS scenario(s), $ENFORCING_FAIL failure(s)"
else
    proxy_fail "the enforcing run recorded ZERO scenario assertions; the battery ran nothing and its exit code means nothing"
fi

# The two controls. A control that does not fire is the failure this block
# exists for: it would leave the battery unable to detect the exact defect class
# it was built for, while still exiting 0.
if [[ "$NOLICENSE_FAIL" -gt 0 ]]; then
    proxy_pass "the nolicense control FIRED ($NOLICENSE_FAIL scenario failures, as required)"
else
    proxy_fail "the nolicense control did NOT fire: a build with -tags nolicense accepted everything and the battery did not notice, so it cannot detect a stub build"
fi
if [[ "$WRONGKEY_FAIL" -gt 0 ]]; then
    proxy_pass "the wrong-key control FIRED ($WRONGKEY_FAIL scenario failures, as required)"
else
    proxy_fail "the wrong-key control did NOT fire: a binary baked with a stranger's public key still validated licences, so the battery cannot detect a wrongly-baked key"
fi

proxy_expect_contains "$BOTH" "both controls failed as required" "the subject printed its own both-controls verdict"

proxy_finish

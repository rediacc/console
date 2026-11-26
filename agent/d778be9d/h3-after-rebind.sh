#!/usr/bin/env bash
# PLAN-backup-integrity.md H3 (b472cb77): re-deploy the hostinger backup schedule through
# eu-remote once its login is rebound to this IP. backup schedule runs through eu-remote by
# ruling (ASKED:2026-11-05T07:06Z), never through eu-bench.
#
# Two passes, run from the console root:
#   REDIACC_IP_REBIND_CODE=<code> agent/d778be9d/h3-after-rebind.sh
#       rebinds, then stops after the schedule dry run so the units can be read first;
#   agent/d778be9d/h3-after-rebind.sh --apply
#       deploys the schedule, reads the status, and fails unless the deployed schedule output
#       names a verify unit (a *verify*.service or *verify*.timer) and an OnFailure= line.
# rdc reads REDIACC_IP_REBIND_CODE from the environment on the first call that meets the
# IP-rebind refusal (packages/cli/src/services/account/token-ip-rebind.ts), so the code is
# only needed for the first pass. Each step stops the script on a non-zero exit.
# agent/d778be9d/test-h3-after-rebind.sh tests check_units against fixtures.
set -euo pipefail

# check_units <schedule output file>: 0 when it names a verify unit and an OnFailure= line.
check_units() {
	local out=$1 ok=0
	if ! grep -Eq '[A-Za-z0-9@_.-]*verify[A-Za-z0-9@_.-]*\.(service|timer)' "$out"; then
		echo "FAIL: the deployed schedule names no verify unit (see $out)" >&2
		ok=1
	fi
	if ! grep -Eq '^[[:space:]]*OnFailure=[^[:space:]]' "$out"; then
		echo "FAIL: the deployed schedule has no OnFailure= line (see $out)" >&2
		ok=1
	fi
	return "$ok"
}

# Sourced by the test: define the function, run nothing.
[ "${BASH_SOURCE[0]}" != "$0" ] && return 0

cd "$(git rev-parse --show-toplevel)"
# A private directory per run; the path is printed, never guessed.
log=$(mktemp -d "${TMPDIR:-/tmp}/h3-after-rebind.XXXXXX")

if [ "${1:-}" != "--apply" ]; then
	: "${REDIACC_IP_REBIND_CODE:?set REDIACC_IP_REBIND_CODE to the authenticator code for this IP}"
	./rdc.sh --config eu-remote subscription status >"$log/1-subscription.out" 2>"$log/1-subscription.err"
	echo "1 subscription status rc=0 (eu-remote rebound)"
	./rdc.sh --config eu-remote backup schedule -m hostinger --dry-run >"$log/2-dry-run.out" 2>"$log/2-dry-run.err"
	echo "2 schedule dry run rc=0; read $log/2-dry-run.out, then run again with --apply"
	exit 0
fi

./rdc.sh --config eu-remote backup schedule -m hostinger >"$log/3-schedule.out" 2>"$log/3-schedule.err"
echo "3 schedule rc=0"
./rdc.sh --config eu-remote backup status -m hostinger >"$log/4-status.out" 2>"$log/4-status.err"
echo "4 status rc=0 (in $log/4-status.out)"
check_units "$log/3-schedule.out"
echo "5 verify unit and OnFailure= present; evidence in $log"

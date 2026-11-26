#!/usr/bin/env bash
# PLAN-backup-integrity.md H3 (b472cb77): re-deploy the hostinger backup schedule through
# eu-remote once its login is rebound to this IP. backup schedule runs through eu-remote by
# ruling (ASKED:2026-11-05T07:06Z), never through eu-bench.
#
# Two passes, run from the console root:
#   REDIACC_IP_REBIND_CODE=<code> agent/d778be9d/h3-after-rebind.sh
#       rebinds, then stops after the schedule dry run so the units can be read first;
#   agent/d778be9d/h3-after-rebind.sh --apply
#       deploys the schedule, reads the status, and fails unless the deployed units name
#       verify and OnFailure=.
# rdc reads REDIACC_IP_REBIND_CODE from the environment on the first call that meets the
# IP-rebind refusal (packages/cli/src/services/account/token-ip-rebind.ts), so the code is
# only needed for the first pass. Each step stops the script on a non-zero exit.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

log=/tmp/h3-after-rebind
mkdir -p "$log"

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
echo "4 status rc=0"

# The box asks for verify units and OnFailure= on the deployed units; either one missing fails the run.
for want in verify 'OnFailure='; do
	if ! grep -q -- "$want" "$log/3-schedule.out"; then
		echo "5 FAIL: the deployed schedule names no '$want' (see $log/3-schedule.out)" >&2
		exit 1
	fi
done
echo "5 verify and OnFailure= present; evidence in $log"

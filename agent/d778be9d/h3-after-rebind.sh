#!/usr/bin/env bash
# PLAN-backup-integrity.md H3 (b472cb77): re-deploy the hostinger backup schedule through
# eu-remote once its login is rebound to this IP. backup schedule runs through eu-remote by
# ruling (ASKED:2026-11-05T07:06Z), never through eu-bench.
#
# Run from the console root after the operator's rebind:
#   REDIACC_IP_REBIND_CODE=<authenticator code> agent/d778be9d/h3-after-rebind.sh
# Each step stops the script on a non-zero exit; the dry run shows the units before any write.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
: "${REDIACC_IP_REBIND_CODE:?set REDIACC_IP_REBIND_CODE to the authenticator code for this IP}"

log=/tmp/h3-after-rebind-$(date -u +%Y%m%dT%H%MZ)
mkdir -p "$log"

./rdc.sh --config eu-remote subscription status >"$log/1-subscription.out" 2>"$log/1-subscription.err"
echo "1 subscription status rc=0"

./rdc.sh --config eu-remote backup schedule -m hostinger --dry-run >"$log/2-dry-run.out" 2>"$log/2-dry-run.err"
echo "2 schedule dry run rc=0 (units in $log/2-dry-run.out)"

./rdc.sh --config eu-remote backup schedule -m hostinger >"$log/3-schedule.out" 2>"$log/3-schedule.err"
echo "3 schedule rc=0"

./rdc.sh --config eu-remote backup status -m hostinger >"$log/4-status.out" 2>"$log/4-status.err"
echo "4 status rc=0"

# The box also asks for verify units and OnFailure= on the deployed units.
grep -E 'verify|OnFailure=' "$log/2-dry-run.out" "$log/3-schedule.out" >"$log/5-units.txt" || true
echo "5 verify/OnFailure lines: $(wc -l <"$log/5-units.txt") (in $log/5-units.txt)"
echo "evidence: $log"

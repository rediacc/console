#!/usr/bin/env bash
# Tests check_units of agent/d778be9d/h3-after-rebind.sh against fixture schedule outputs.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=h3-after-rebind.sh
. "$here/h3-after-rebind.sh"
# The sourced script sets -e; an expected failure must not end the test.
set +e

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
fails=0
expect() { # expect <rc> <label> <fixture text>
	printf '%s\n' "$3" >"$dir/out"
	check_units "$dir/out" 2>/dev/null
	local rc=$?
	if [ "$rc" -ne "$1" ]; then echo "FAIL: $2 (rc $rc, want $1)"; fails=$((fails + 1)); else echo "ok: $2"; fi
}

expect 0 "a verify timer and an OnFailure= line pass" $'installed rediacc-backup-verify@mail.timer\nOnFailure=rediacc-backup-alert@%n.service'
expect 1 "prose mentioning verify is not a unit" $'will verify later\nOnFailure=rediacc-backup-alert@%n.service'
expect 1 "a missing OnFailure= fails" $'installed rediacc-backup-verify@mail.timer'
expect 1 "OnFailure= inside prose is not a unit line" $'installed rediacc-backup-verify@mail.timer\nthe unit lacks OnFailure= today'
expect 1 "an empty output fails" ''

if [ "$fails" -ne 0 ]; then
	echo "$fails failed"
	exit 1
fi
echo "all passed"

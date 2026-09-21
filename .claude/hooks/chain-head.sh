#!/usr/bin/env bash
# The ONE command .claude/settings.json registers for a guarded (event, matcher) pattern: the two toolchain checks, then the Python runner that carries the rest of the pattern.
#
# WHY IT IS BASH, and it is the only new bash file the language policy admits for this. require-python.sh is the check that python3 EXISTS, and its own header (lines 5-12) argues it may never be ported: written in Python it cannot run in the one condition it exists to report. A chain head that leads it therefore cannot be Python either. The allowlist entry for this file is in .ci/policy/.language-policy-allowlist.
#
# IT DOES NOTHING ELSE. Every decision this pattern makes belongs to a member, and the members are the table in .claude/rediacc_hooks/lifecycle.py. Logic added here would be logic no reader of that table can see.
#
# THE READ IS BOUNDED, for the reason require-python.sh records at its own read: `INPUT=$(cat)` on a stdin that stays open and silent blocks forever, and a hang in a PreToolUse hook is not a slow check but a tool call that never returns. `-d ''` reads to NUL, that is to EOF, so only a status above 128 is the deadline firing, and the deadline REFUSES rather than allows.
set -u

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

PAYLOAD=""
IFS= read -r -d "" -t 10 PAYLOAD
if [ "$?" -gt 128 ]; then
    printf 'no payload arrived on stdin within 10s; refusing rather than hanging the tool call.\n' >&2
    exit 2
fi

for check in require-jq.sh require-python.sh; do
    printf '%s' "$PAYLOAD" | bash "$HERE/$check"
    rc=$?
    if [ "$rc" -ne 0 ]; then
        exit "$rc"
    fi
done

# `exec` on the right of the pipe replaces the subshell the pipeline already costs, so the runner is not a second process on top of one.
printf '%s' "$PAYLOAD" | exec python3 "$HERE/../rediacc_hooks/lifecycle.py" "$@"

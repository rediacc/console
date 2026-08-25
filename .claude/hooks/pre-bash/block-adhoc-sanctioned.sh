#!/usr/bin/env bash
# Refuse an ad-hoc command when a sanctioned tool exists for it.
#
# The rules live in .claude/hooks/lib/sanctioned.py, one row per class, so a new
# class is a row rather than a 22nd copy of this file. See that module's header
# for why a table replaced per-guard scripts, and for the deliberately-kept
# false positive on prose that merely DESCRIBES a banned shape (operator ruling
# 2026-08-25, worklist #6a2c9652).
#
# Fails OPEN on its own breakage: if python3 or the registry is unavailable this
# exits 0 rather than blocking every command in the session. A guard that bricks
# the shell when it breaks gets deleted, and then nothing is guarded.
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command' 2>/dev/null) || exit 0
[ -n "$CMD" ] || exit 0

# DERIVED FROM THIS SCRIPT'S OWN LOCATION, not from CLAUDE_PROJECT_DIR.
# That variable is set by the agent harness and is ABSENT in CI and in a bare
# shell, where the fallback `.` made the registry unfindable -- and this guard
# fails open by design, so it silently allowed every banned command. Its own
# controls caught it, but only once they ran somewhere without the variable.
LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)"
[ -f "$LIB/sanctioned.py" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# Both values go in the ENV PREFIX. An earlier draft passed LIB= as a python
# ARGUMENT, so os.environ["LIB"] raised, `|| exit 0` swallowed it, and the guard
# exited 0 for every command in both directions -- a guard that cannot fail.
# Caught only because the controls assert the BLOCK direction too.
MSG=$(CMD="$CMD" LIB="$LIB" python3 -c '
import os, sys
sys.path.insert(0, os.environ["LIB"])
try:
    import sanctioned as S
except Exception:
    sys.exit(0)
row = S.match(os.environ.get("CMD", ""))
if row:
    print(S.message(row))
' 2>/dev/null) || exit 0

if [ -n "$MSG" ]; then
    printf '%s\n' "$MSG" >&2
    exit 2
fi
exit 0

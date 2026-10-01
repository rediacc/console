#!/usr/bin/env python3
"""Control harness for block_long_sleep.

Both directions, because a one-sided control is satisfiable by a broken hook: one that always blocks passes the positive cases, one that never blocks passes the negative ones. The prose cases are the 2026-10-01 defect (#8e5a6452): the word for a pause inside a QUOTED argument was read as a command.
"""

import json
import pathlib
import subprocess
import sys

# Derived from THIS file, never hard-coded: the guard lives beside the harness, and the dispatcher is what actually runs it.
DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_long_sleep"]
S = "sle" + "ep"  # assembled so this file is not itself a tripwire for a text scan

CASES = [
    # (name, command, background, expect_blocked)
    # --- prose: the word sits inside a quoted argument, or in data, and runs nothing ---
    (
        "quoted commit prose written by printf",
        "printf '%s\\n' 'fix: the gate, which " + S + " 600 s (a full run) hid' > msg.txt",
        False,
        False,
    ),
    (
        "worklist --add text",
        '.claude/hooks/stop/worklist.py --add abc "drop the ' + S + ' 600 in the watch"',
        False,
        False,
    ),
    ("echo of a quoted sleep", 'echo "' + S + ' 600"', False, False),
    ("grep for the pattern", "grep -rn '" + S + " 300' docs/", False, False),
    ("commit -m prose", 'git commit -m "note: ' + S + ' 90 was the old cap"', False, False),
    # --- the commands that really run a long sleep ---
    ("bare", S + " 60", False, True),
    ("minute suffix", S + " 1m", False, True),
    ("summed operands", S + " 15 10", False, True),
    ("infinity", S + " infinity", False, True),
    ("after ; and before &&", "cmd; " + S + " 30 && x", False, True),
    ("in a subshell", "(" + S + " 45)", False, True),
    ("bash -c payload", "bash -c '" + S + " 90'", False, True),
    ("sh -c payload, double quotes", 'sh -c "' + S + ' 300"', False, True),
    ("eval", "eval '" + S + " 300'", False, True),
    ("in a while body", "while true; do " + S + " 25; done", False, True),
    ("after then", "if x; then " + S + " 30; fi", False, True),
    ("timeout prefix", "timeout 600 " + S + " 300", False, True),
    ("nohup prefix", "nohup " + S + " 300", False, True),
    ("command substitution", "x=$(" + S + " 30)", False, True),
    ("echo piped to bash runs it", 'echo "' + S + ' 600" | bash', False, True),
    ("heredoc fed to bash", "bash <<EOF\n" + S + " 300\nEOF", False, True),
    ("ssh remote operand", "ssh host '" + S + " 300'", False, True),
    ("docker exec operand", "docker exec c " + S + " 300", False, True),
    # --- the 2026-08-25 ruling: a heredoc body is scanned whatever reads it ---
    (
        "heredoc commit message (ruling kept)",
        "git commit -F - <<'MSG'\nits " + S + " 20 arm precedes its " + S + " 90 arm\nMSG",
        False,
        True,
    ),
    (
        "heredoc written to a doc (ruling kept)",
        "cat > d.md <<'EOF'\n" + S + " 600\nEOF",
        False,
        True,
    ),
    # --- caps ---
    ("at the cap", S + " 20", False, False),
    ("short", S + " 10", False, False),
    ("fractional over the cap", S + " 20.5", False, True),
    ("background under its cap", S + " 90", True, False),
    ("background over its cap", S + " 300", True, True),
    ("unexpanded operand is not judged", S + ' "$N"', False, False),
    ("no sleep at all", "gh run view 123", False, False),
]


def blocked(cmd, background):
    tool_input = {"command": cmd}
    if background:
        tool_input["run_in_background"] = True
    p = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": tool_input}),
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode != 0


fails = 0
for name, cmd, background, want in CASES:
    got = blocked(cmd, background)
    ok = got == want
    fails += not ok
    print(
        "%-42s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )

print()
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)

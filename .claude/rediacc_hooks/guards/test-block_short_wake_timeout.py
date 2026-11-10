#!/usr/bin/env python3
"""Control harness for block_short_wake_timeout.

WHY THIS FILE IS LOAD-BEARING. The guard declares `OWN_SUITE = True` (it was never bash: the arm it refuses was found live, 2026-11-10), so it has no golden and `test_guards_differential.py` REQUIRES a `test-<stem>.py` beside it. `check:ci-hook-integrity` and `check:ci-trap-registry` credit the guard with both directions because of this file.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, so the module that actually runs is the one judged. Each refusing case names the rule it exercises by a needle from that rule's own sentence, so a case that is refused for some OTHER reason does not count as the rule firing: removing one rule turns exactly its cases red, which is the control the brief asked for (each rule removed by hand once, 2026-11-10).

NO FIXTURE NEEDED. The guard reads the command, `run_in_background` and `timeout`, and imports `.claude/hooks/stop/wl_wake.py` for its numbers; it touches no file and no lock.
"""

import json
import pathlib
import subprocess
import sys

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_short_wake_timeout"]

ARM = "python3 .claude/hooks/stop/wl_wake.py d778be9d"
INCIDENT = "python3 .claude/hooks/stop/wl_wake.py d778be9d --minutes 30 >/dev/null 2>&1 & true"
OK = {"run_in_background": True, "timeout": 2400000}

AMP = "shell `&`"
SHARES = "shares the call"
FG = "run_in_background is not true"
SHORT = "below "
INVALID = "not a valid number of milliseconds"

CASES = [
    # (name, command, extra tool_input, needles the refusal must carry; [] means admitted)
    # ---- the refusing direction, one rule at a time where the shape allows it ----
    (
        "the 2026-11-10 incident, as run",
        INCIDENT,
        {"run_in_background": False},
        [AMP, SHARES, FG, SHORT],
    ),
    ("the incident appended to unrelated work", "npm test; " + INCIDENT, {}, [AMP, SHARES]),
    ("& alone, with a correct background call", ARM + " &", OK, [AMP]),
    ("& inside a subshell", "(" + ARM + " &)", OK, [AMP]),
    ("chained after another command with ;", "git status; " + ARM, OK, [SHARES]),
    ("chained after another command with &&", "cd /tmp && " + ARM, OK, [SHARES]),
    ("chained before another command with ||", ARM + " || echo failed", OK, [SHARES]),
    ("piped into another command", ARM + " | tee /tmp/wake.log", OK, [SHARES]),
    ("run through a nested bash -c", "bash -c '" + ARM + "'", OK, [SHARES]),
    ("a heredoc fed to bash runs it", "bash <<'E'\n" + ARM + "\nE", OK, [SHARES]),
    ("foreground, correct timeout", ARM, {"timeout": 2400000}, [FG]),
    ("foreground spelled false", ARM, {"run_in_background": False, "timeout": 2400000}, [FG]),
    ("background, no timeout (the harness default)", ARM, {"run_in_background": True}, [SHORT]),
    (
        "background, timeout at the sleep",
        ARM,
        {"run_in_background": True, "timeout": 1800000},
        [SHORT],
    ),
    (
        "background, --minutes 60 under its harness_timeout_ms",
        ARM + " --minutes 60",
        {"run_in_background": True, "timeout": 2400000},
        [SHORT, "4200000"],
    ),
    (
        "an unreadable --minutes needs the ceiling",
        ARM + " --minutes $M",
        {"run_in_background": True, "timeout": 4200000},
        [SHORT, "7200000"],
    ),
    (
        "a session prefix from a variable still arms",
        "python3 .claude/hooks/stop/wl_wake.py $ME",
        {"run_in_background": True},
        [SHORT],
    ),
    ("run by path, not through python3", ".claude/hooks/stop/wl_wake.py d778be9d", {}, [FG, SHORT]),
    (
        "a numeric-string timeout below the floor",
        ARM,
        {"run_in_background": True, "timeout": "60000"},
        [SHORT],
    ),
    (
        "a missing timeout is named absent",
        ARM,
        {"run_in_background": True},
        ["absent (the harness default"],
    ),
    (
        "timeout nan is invalid",
        ARM,
        {"run_in_background": True, "timeout": "nan"},
        [INVALID, "'nan'"],
    ),
    (
        "timeout inf is invalid",
        ARM,
        {"run_in_background": True, "timeout": "inf"},
        [INVALID, "'inf'"],
    ),
    ("a negative timeout is short", ARM, {"run_in_background": True, "timeout": -5}, [SHORT, "-5"]),
    (
        "timeout true is invalid",
        ARM,
        {"run_in_background": True, "timeout": True},
        [INVALID, "True"],
    ),
    (
        "timeout abc is invalid",
        ARM,
        {"run_in_background": True, "timeout": "abc"},
        [INVALID, "'abc'"],
    ),
    # ---- the admitting direction ----
    ("the correct arm", ARM, OK, []),
    ("the correct arm with a trailing newline", ARM + "\n", OK, []),
    (
        "--minutes 60 with its own timeout",
        ARM + " --minutes 60",
        {"run_in_background": True, "timeout": 4200000},
        [],
    ),
    (
        "--minutes 110 at the ceiling",
        ARM + " --minutes 110",
        {"run_in_background": True, "timeout": 7200000},
        [],
    ),
    (
        "an unreadable --minutes at the ceiling",
        ARM + " --minutes $M",
        {"run_in_background": True, "timeout": 7200000},
        [],
    ),
    ("the usage line", "python3 .claude/hooks/stop/wl_wake.py --help", {}, []),
    ("no arguments prints usage", "python3 .claude/hooks/stop/wl_wake.py", {}, []),
    ("a heredoc read by cat that names the arm", "cat <<'E'\n" + INCIDENT + "\nE", {}, []),
    ("an echo naming the arm", "echo '" + INCIDENT + "'", {}, []),
    ("a grep for the file", "grep -n wl_wake.py .claude/hooks/stop/wl_checks.py", {}, []),
    (
        "a test run that imports it",
        "python3 -m pytest .claude/rediacc_hooks/tests/test_wl_wake.py -q",
        {},
        [],
    ),
    ("an inline program naming it", "python3 -c 'print(\"wl_wake.py d778be9d &\")'", {}, []),
    (
        "a worklist note naming it",
        ".claude/hooks/stop/worklist.py --update d778be9d 1 'armed wl_wake.py d778be9d &'",
        {},
        [],
    ),
    ("no timer at all", "git status", {}, []),
    ("an empty command", "", {}, []),
]


def run(command, extra):
    payload = {"tool_name": "Bash", "tool_input": dict({"command": command}, **extra)}
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stderr


fails = 0
blocked = 0
for name, command, extra, needles in CASES:
    rc, err = run(command, extra)
    want = bool(needles)
    got = rc == 2
    blocked += got
    missing = [n for n in needles if n not in err]
    ok = got == want and not missing and rc in (0, 2)
    fails += not ok
    print(
        "%-56s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else ("allowed" if rc == 0 else "rc=%d" % rc),
            "ok" if ok else "*** FAIL ***",
        )
    )
    if missing:
        print("    the refusal does not name: %s" % missing)
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:4])

print()
# ANTI-VACUITY: a guard that answers one way on every input passes half of any suite.
if blocked == 0 or blocked == len(CASES):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every "
        "input, so this suite compared it against a constant." % (blocked, len(CASES)),
        file=sys.stderr,
    )
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)

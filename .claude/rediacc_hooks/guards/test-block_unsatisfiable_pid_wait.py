#!/usr/bin/env python3
"""Control harness for block_unsatisfiable_pid_wait.

WHY THIS FILE IS LOAD-BEARING. The guard declares `TWIN = None` (it was never bash: the trap it catches was only found live, 2026-09-21/22), so `test_guards_differential.py` has no bash oracle for it and instead REQUIRES a `test-<stem>.py` beside it -- see `guards.twin_of` and `test_every_port_has_a_present_twin`.
This is that file, and `check-hook-integrity.sh` credits the guard with coverage under both directions because of it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, for the reason the P7 cutover exists: a suite driving anything else keeps passing while the thing that actually runs goes unchecked.

NO GIT FIXTURE NEEDED. Unlike `test-block_push_to_protected_branch.py`, none of these cases depend on which branch the checkout is on -- the guard reasons purely about the command text, so every case's `cwd` is `None`.
"""

import json
import os
import pathlib
import subprocess
import sys

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_unsatisfiable_pid_wait"]

CASES = [
    # (name, command, cwd-or-None, expect_blocked) ---- the block direction ------------------
    (
        "the incident's own shape",
        (
            'until grep -q "ci-dead-bash" out.log && [ "$(tail -c 200 out.log | wc -c)" -gt 0 ] '
            "&& ! [ -e /proc/$(cat out.log.pid 2>/dev/null || echo 1) ]; do sleep 5; done"
        ),
        None,
        True,
    ),
    (
        "minimal fire, unnegated",
        "until [ -e /proc/$(cat x.pid 2>/dev/null || echo 1) ]; do sleep 5; done",
        None,
        True,
    ),
    (
        "$$ fallback",
        "until ! [ -e /proc/$(cat x.pid 2>/dev/null || echo $$) ]; do sleep 5; done",
        None,
        True,
    ),
    (
        "quoted path form",
        'until ! [ -e "/proc/$(cat x.pid 2>/dev/null || echo 1)" ]; do sleep 5; done',
        None,
        True,
    ),
    (
        "-d instead of -e",
        "until ! [ -d /proc/$(cat x.pid || echo 1) ]; do sleep 5; done",
        None,
        True,
    ),
    (
        "while form fires the same as until",
        "while ! [ -e /proc/$(cat x.pid 2>/dev/null || echo 1) ]; do sleep 5; done",
        None,
        True,
    ),
    # ---- the allow direction ------------------------------------------
    (
        "a fallback of 0 is safe",
        "until ! [ -e /proc/$(cat x.pid 2>/dev/null || echo 0) ]; do sleep 5; done",
        None,
        False,
    ),
    (
        "an arbitrary literal PID is a documented gap",
        "until ! [ -e /proc/$(cat x.pid || echo 54321) ]; do sleep 5; done",
        None,
        False,
    ),
    (
        "a variable fallback is unexaminable",
        'until ! [ -e /proc/$(cat x.pid 2>/dev/null || echo "$FALLBACK_PID") ]; do sleep 5; done',
        None,
        False,
    ),
    (
        "a one-shot check is out of scope",
        "if [ -e /proc/$(cat x.pid 2>/dev/null || echo 1) ]; then echo dead; fi",
        None,
        False,
    ),
    (
        "a semicolon join is a different bug",
        "until [ -e /proc/$(cat x.pid 2>/dev/null; echo 1) ]; do sleep 5; done",
        None,
        False,
    ),
    (
        "an && join is not a fallback",
        "until [ -e /proc/$(cat x.pid 2>/dev/null && echo 1) ]; do sleep 5; done",
        None,
        False,
    ),
    (
        "the pidfile-first remedy",
        "until [ -s out.pid ] && ! [ -e /proc/$(cat out.pid) ]; do sleep 5; done",
        None,
        False,
    ),
    (
        "the not-started-yet remedy",
        "until [ ! -s out.pid ] || ! [ -e /proc/$(cat out.pid) ]; do sleep 5; done",
        None,
        False,
    ),
    (
        "kill -0 form is a documented v1 gap",
        "until ! kill -0 $(cat x.pid 2>/dev/null || echo 1) 2>/dev/null; do sleep 5; done",
        None,
        False,
    ),
    (
        "a non-proc default is not this bug",
        "until [ -e $(cat config_path.txt 2>/dev/null || echo default.conf) ]; do sleep 2; done",
        None,
        False,
    ),
    (
        "prose mention is not the trap",
        'echo "never write /proc/$(cat x.pid || echo 1) into a wait loop"',
        None,
        False,
    ),
    (
        "an unparseable substitution",
        "until ! [ -e /proc/$(cat x.pid || echo 1 ; do sleep 5; done",
        None,
        False,
    ),
    (
        "a pipeline on the left is not a bare cat",
        "until ! [ -e /proc/$(cat x.pid | grep -q 1 || echo 1) ]; do sleep 5; done",
        None,
        False,
    ),
    ("a loop with no /proc/ check at all", "until [ -s out.txt ]; do sleep 5; done", None, False),
    ("an empty command", "", None, False),
]


def run(command, cwd):
    env = dict(os.environ)
    if cwd is not None:
        env["CLAUDE_PROJECT_DIR"] = cwd
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, command, cwd, want in CASES:
    got, err = run(command, cwd)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-58s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])

print()
# ANTI-VACUITY: see the sibling harness. This guard's only control is this file.
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

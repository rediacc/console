#!/usr/bin/env python3
"""Control harness for block_unsatisfiable_pid_wait.

WHY THIS FILE IS LOAD-BEARING. The guard declares `OWN_SUITE = True` (it was never bash: the trap it catches was only found live, 2026-09-21/22), so it has no golden either and `test_guards_differential.py` instead REQUIRES a `test-<stem>.py` beside it -- see `test_every_port_has_goldens`.
This is that file, and `check-hook-integrity.sh` credits the guard with coverage under both directions because of it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, for the reason the P7 cutover exists: a suite driving anything else keeps passing while the thing that actually runs goes unchecked.

NO GIT FIXTURE NEEDED. Unlike `test-block_push_to_protected_branch.py`, none of these cases depend on which branch the checkout is on -- the guard reasons purely about the command text, so every case's `cwd` is `None`.
"""

import json
import os
import pathlib
import sys

import _hookpath

from rediacc_hooks.guards import _harness
from rediacc_hooks.tests.fixtures.guards.loader import load_table

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_unsatisfiable_pid_wait"]

CASES = load_table("block_unsatisfiable_pid_wait", "CASES")


def run(command, cwd):
    env = dict(os.environ)
    if cwd is not None:
        env["CLAUDE_PROJECT_DIR"] = cwd
    proc = _harness.run(
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

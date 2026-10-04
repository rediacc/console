#!/usr/bin/env python3
"""Control harness for block_missing_npm_script.

Both directions, because a one-sided control is satisfiable by a broken guard: one that always refuses passes the missing-name cases, one that never refuses passes the controls. The last section plants the plan's mutation (the lookup always says "present") in-process and requires the missing-name case to stop being refused, so this harness can tell a working guard from a constant.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
DISPATCH = str(HERE.parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_missing_npm_script"]
MISSING = "does-not-exist-example"

CASES = [
    # (name, command, expect_blocked)
    ("a name no package.json defines", "npm run " + MISSING, True),
    ("run-script spelling", "npm run-script " + MISSING, True),
    ("a manifest id with no root script", "npm run gate-test:trap-registry", True),
    ("a root script typed into a package", "cd packages/cli && npm run check:ci-python-lint", True),
    ("--prefix governs", "npm --prefix packages/cli run check:ci-python-lint", True),
    ("-w by path governs", "npm -w packages/cli run check:ci-python-lint", True),
    ("behind a pipe and a redirect", "npm run --silent " + MISSING + " 2>&1 | tail -5", True),
    ("inside bash -c", "bash -c 'npm run " + MISSING + "'", True),
    # --- controls: each must be allowed ---
    ("a real script in the cd'd package", "cd packages/cli && npm run test", False),
    ("a computed name fails open", 'npm run "$GATE"', False),
    ("a real root script", "npm run check:ci-python-lint", False),
    ("a real script under -w by name", "npm -w @rediacc/cli run test", False),
    ("--if-present exits 0 on a miss", "npm run --if-present " + MISSING, False),
    ("--workspaces fails open", "npm run --workspaces " + MISSING, False),
    ("an unresolvable directory fails open", "cd /nonexistent-dir && npm run " + MISSING, False),
    ("a backtick name fails open", "npm run `echo x`", False),
    ("prose is not a run", "echo 'npm run " + MISSING + "'", False),
    ("a commit message is not a run", 'git commit -m "npm run ' + MISSING + '"', False),
    ("a remote operand is not this tree", "ssh host 'npm run " + MISSING + "'", False),
    ("a bare npm run only lists", "npm run", False),
]


def answer(cmd):
    p = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": {"command": cmd}, "cwd": str(ROOT)}),
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    return p.returncode, p.stderr


fails = 0
for name, cmd, want in CASES:
    rc, err = answer(cmd)
    got = rc == 2
    ok = got == want and rc in (0, 2)
    fails += not ok
    print(
        "%-42s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed (rc=%d)" % rc,
            "ok" if ok else "*** FAIL ***",
        )
    )

# The refusal must name the resolved file and a real neighbour, or it is a silent red with extra steps.
rc, err = answer("npm run gate-test:trap-registry")
named = "package.json" in err and "check:ci-trap-registry" in err
fails += not named
print("%-42s %s" % ("message names file and nearest script", "ok" if named else "*** FAIL ***"))

# MUTATION: the lookup always answers "present". The missing-name case must stop being refused, or the cases above never depended on the lookup at all.
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parents[1] / "syspath.py"
)
_syspath = importlib.util.module_from_spec(_SYSPATH)  # type: ignore[arg-type]
_SYSPATH.loader.exec_module(_syspath)  # type: ignore[union-attr]
_syspath.on_sys_path(str(HERE.parents[2]))
from rediacc_hooks import hookio  # noqa: E402
from rediacc_hooks.guards import block_missing_npm_script as guard  # noqa: E402

real = guard.lookup
guard.lookup = lambda pkg, name: (True, real(pkg, name)[1])
try:
    event = hookio.Event(
        json.dumps({"tool_input": {"command": "npm run " + MISSING}, "cwd": str(ROOT)}),
        cwd=str(ROOT),
    )
    mutated = guard.run(event)
finally:
    guard.lookup = real
red = mutated == hookio.ALLOW
fails += not red
print("%-42s %s" % ("mutation: lookup stubbed present goes red", "ok" if red else "*** FAIL ***"))

print()
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)

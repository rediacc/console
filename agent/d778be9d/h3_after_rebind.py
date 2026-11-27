#!/usr/bin/env python3
"""PLAN-backup-integrity.md H3 (b472cb77): re-deploy the hostinger backup schedule through eu-remote.

backup schedule runs through eu-remote by ruling (ASKED:2026-11-05T07:06Z), never through eu-bench, and eu-remote
needs its login rebound to this IP first. Two passes, run from the console root:

    REDIACC_IP_REBIND_CODE=<code> python3 agent/d778be9d/h3_after_rebind.py
        rebinds (rdc reads REDIACC_IP_REBIND_CODE from the environment on the first call that meets the IP-rebind
        refusal, packages/cli/src/services/account/token-ip-rebind.ts), then stops after the schedule dry run so the
        units can be read first;
    python3 agent/d778be9d/h3_after_rebind.py --apply
        deploys the schedule, reads the status, and fails unless the deployed schedule output names a verify unit
        (a *verify*.service or *verify*.timer) and an OnFailure= line;
    python3 agent/d778be9d/h3_after_rebind.py --selftest
        checks check_units against fixtures.

Each pass writes its output to a private per-run directory it prints, and stops on the first non-zero exit.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile

VERIFY_UNIT = re.compile(r"[A-Za-z0-9@_.-]*verify[A-Za-z0-9@_.-]*\.(service|timer)")
ON_FAILURE_LINE = re.compile(r"^\s*OnFailure=\S", re.MULTILINE)


def check_units(text: str) -> list[str]:
    """The reasons the schedule output fails the H3 accept; empty when it names a verify unit and an OnFailure= line."""
    problems = []
    if not VERIFY_UNIT.search(text):
        problems.append("the deployed schedule names no verify unit")
    if not ON_FAILURE_LINE.search(text):
        problems.append("the deployed schedule has no OnFailure= line")
    return problems


def step(log: pathlib.Path, name: str, argv: list[str]) -> str:
    """Run one rdc call, keep stdout and stderr apart in the log, and stop the run on a non-zero exit."""
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    (log / f"{name}.out").write_text(proc.stdout, encoding="utf-8")
    (log / f"{name}.err").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        sys.exit(f"{name} rc={proc.returncode}; see {log}/{name}.err")
    print(f"{name} rc=0")
    return proc.stdout


def selftest() -> int:
    cases = [
        (
            [],
            "installed rediacc-backup-verify@mail.timer\nOnFailure=rediacc-backup-alert@%n.service",
        ),
        (
            ["the deployed schedule names no verify unit"],
            "will verify later\nOnFailure=x@%n.service",
        ),
        (
            ["the deployed schedule has no OnFailure= line"],
            "installed rediacc-backup-verify@mail.timer",
        ),
        (
            ["the deployed schedule has no OnFailure= line"],
            "rediacc-backup-verify@mail.timer\nthe unit lacks OnFailure= today",
        ),
        (
            [
                "the deployed schedule names no verify unit",
                "the deployed schedule has no OnFailure= line",
            ],
            "",
        ),
    ]
    failed = sum(1 for want, text in cases if check_units(text) != want)
    print(f"{len(cases) - failed} of {len(cases)} cases passed")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    ).stdout.strip()
    os.chdir(root)
    log = pathlib.Path(tempfile.mkdtemp(prefix="h3-after-rebind."))
    rdc = ["./rdc.sh", "--config", "eu-remote"]
    if argv != ["--apply"]:
        if not os.environ.get("REDIACC_IP_REBIND_CODE"):
            sys.exit("set REDIACC_IP_REBIND_CODE to the authenticator code for this IP")
        step(log, "1-subscription", [*rdc, "subscription", "status"])
        step(log, "2-dry-run", [*rdc, "backup", "schedule", "-m", "hostinger", "--dry-run"])
        print(f"read {log}/2-dry-run.out, then run again with --apply")
        return 0
    schedule = step(log, "3-schedule", [*rdc, "backup", "schedule", "-m", "hostinger"])
    step(log, "4-status", [*rdc, "backup", "status", "-m", "hostinger"])
    problems = check_units(schedule)
    for problem in problems:
        print(f"FAIL: {problem} (see {log}/3-schedule.out)", file=sys.stderr)
    if problems:
        return 1
    print(f"verify unit and OnFailure= present; evidence in {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

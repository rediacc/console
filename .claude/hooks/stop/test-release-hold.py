#!/usr/bin/env python3
"""release_local_running: a live release:local of THIS checkout holds the unlanded-lease block; another checkout's, an absent one or an unreadable /proc do not."""

import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
wl_checks = importlib.import_module("wl_checks")

FAILURES: list[str] = []


def check(label, got, want):
    if got != want:
        FAILURES.append("%s: got %r, want %r" % (label, got, want))


def fake_proc(base, pid, argv, cwd):
    d = os.path.join(base, str(pid))
    os.makedirs(d)
    with open(os.path.join(d, "cmdline"), "wb") as f:
        f.write(b"\0".join(a.encode() for a in argv) + b"\0")
    os.symlink(cwd, os.path.join(d, "cwd"))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "console")
        other = os.path.join(tmp, "other")
        os.makedirs(root)
        os.makedirs(other)
        release = ["python3", "-m", "rediacc_ci.release.local", "--channel", "edge"]

        proc = os.path.join(tmp, "proc-live")
        fake_proc(proc, 101, release, root)
        check(
            "a release:local of this checkout holds",
            wl_checks.release_local_running(root, proc=proc),
            True,
        )

        proc = os.path.join(tmp, "proc-other")
        fake_proc(proc, 102, release, other)
        check(
            "a release:local of another checkout does not hold",
            wl_checks.release_local_running(root, proc=proc),
            False,
        )

        proc = os.path.join(tmp, "proc-none")
        fake_proc(proc, 103, ["python3", "-m", "rediacc_ci.release.local_gates"], root)
        fake_proc(proc, 104, ["bash", "/tmp/ent2.sh", "release"], root)
        check(
            "no release:local process does not hold",
            wl_checks.release_local_running(root, proc=proc),
            False,
        )

        check(
            "an unreadable /proc does not hold",
            wl_checks.release_local_running(root, proc=os.path.join(tmp, "missing")),
            False,
        )

    if FAILURES:
        print("FAILURES: %d" % len(FAILURES))
        for f in FAILURES:
            print("  " + f)
        return 1
    print("4 case(s); FAILURES: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())

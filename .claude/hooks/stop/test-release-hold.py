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


def stub(value):
    """A callable that ignores its arguments and answers `value`."""

    def answer(*_args, **_kwargs):
        return value

    return answer


def worktree_check_cases():
    """Review 90118fb6.2: `worktree_check` routes an unlanded lease to the note of the first hold that applies (vm:check, ci:quick, release:local, then the unpushed green receipt) and blocks only when none does."""
    import types
    from unittest import mock

    import wl_worktrees
    import worklist_messages as M

    got = {"unlanded": [{"id": "lease1"}], "cache": {}}

    def drive(vm, ciq, rel, rcpt):
        notes, blocks = [], []

        def queue(_wl, _sid, _state, _key, text, _prio, **_kw):
            notes.append(text)

        def block(key, *_args, **_kw):
            blocks.append(key)

        with (
            mock.patch.object(wl_worktrees, "survey", stub(got)),
            mock.patch.object(wl_worktrees, "report_lines", stub("")),
            mock.patch.object(wl_worktrees, "unlanded_lines", stub("lease1")),
            mock.patch.object(wl_checks, "vm_check_running", stub(vm)),
            mock.patch.object(wl_checks, "ci_quick_running", stub(ciq)),
            mock.patch.object(wl_checks, "release_local_running", stub(rel)),
            mock.patch.object(wl_checks, "green_receipt_on_unpushed_head", stub(rcpt)),
            mock.patch.object(wl_checks, "outq_add", queue),
        ):
            wl_checks.worktree_check(
                None,
                "s",
                {},
                types.SimpleNamespace(items={}),
                None,
                {"cwd": os.getcwd()},
                block,
            )
        return notes, blocks

    notes, blocks = drive(False, False, True, False)
    check("a running release:local reports the lease and blocks nothing", blocks, [])
    check("...with the release note", notes, [M.N_WORKTREE_RELEASE % "lease1"])
    notes, blocks = drive(False, False, True, True)
    check("release:local outranks the unpushed receipt", notes, [M.N_WORKTREE_RELEASE % "lease1"])
    check("...and still blocks nothing", blocks, [])
    notes, blocks = drive(False, False, False, True)
    check(
        "control: the receipt hold applies once release:local is gone",
        notes,
        [M.N_WORKTREE_RECEIPT % "lease1"],
    )
    check("...and still blocks nothing", blocks, [])
    notes, blocks = drive(False, True, True, False)
    check("ci:quick outranks release:local", notes, [M.N_WORKTREE_CIQUICK % "lease1"])
    notes, blocks = drive(False, False, False, False)
    check("control: with no hold the unlanded lease blocks", blocks, ["worktree-unlanded"])
    check("...and queues no hold note", notes, [])


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

    worktree_check_cases()

    if FAILURES:
        print("FAILURES: %d" % len(FAILURES))
        for f in FAILURES:
            print("  " + f)
        return 1
    print("case(s) passed; FAILURES: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())

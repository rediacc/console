#!/usr/bin/env python3
"""release_local_running: a live release:local of THIS checkout holds the unlanded-lease block; another checkout's, an absent one or an unreadable /proc do not.

pinned_vm_check_cases (agent/plans/PLAN-push-decoupling.md R7): a real child process named as a vm:check run holds a real fleet lock file; a payload naming a pinned commit keeps a landing order, one with no pin (or an unreadable pin) rewrites it as before."""

import importlib
import os
import sys
import tempfile

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
    """Review 90118fb6.2: `worktree_check` routes an unlanded lease to the note of the first hold that applies (vm:check, release:local, then the unpushed green receipt) and blocks only when none does."""
    import types
    from unittest import mock

    import wl_worktrees
    import worklist_messages as M

    got = {"unlanded": [{"id": "lease1"}], "cache": {}}

    def drive(vm, rel, rcpt):
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
            mock.patch.object(wl_checks, "release_local_running", stub(rel)),
            mock.patch.object(wl_checks, "green_receipt_on_unpushed_head", stub(rcpt)),
            mock.patch.object(wl_checks, "staged_index_paths", stub([])),
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

    notes, blocks = drive(False, True, False)
    check("a running release:local reports the lease and blocks nothing", blocks, [])
    check("...with the release note", notes, [M.N_WORKTREE_RELEASE % "lease1"])
    notes, blocks = drive(False, True, True)
    check("release:local outranks the unpushed receipt", notes, [M.N_WORKTREE_RELEASE % "lease1"])
    check("...and still blocks nothing", blocks, [])
    notes, blocks = drive(False, False, True)
    check(
        "control: the receipt hold applies once release:local is gone",
        notes,
        [M.N_WORKTREE_RECEIPT % "lease1"],
    )
    check("...and still blocks nothing", blocks, [])
    notes, blocks = drive(True, True, True)
    check(
        "vm:check outranks release:local and the receipt",
        notes,
        [M.N_WORKTREE_VMCHECK % "lease1"],
    )
    check("...and blocks nothing", blocks, [])
    notes, blocks = drive(False, False, False)
    check("control: with no hold the unlanded lease blocks", blocks, ["worktree-unlanded"])
    check("...and queues no hold note", notes, [])


# The child holds the lock the way vm_check.Lock.acquire does: an exclusive flock, then the payload written at offset 0. It prints "held" once the payload is on disk and sleeps until killed. Its file name ends in drills/vm_check.py, so wl_checks.argv_runs reads it as a vm:check run.
HOLDER_SRC = """
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
os.ftruncate(fd, 0)
os.pwrite(fd, sys.argv[2].replace("PID", str(os.getpid())).encode(), 0)
print("held", flush=True)
time.sleep(120)
"""


def pinned_vm_check_cases(tmp):
    """R7: the receipt-in-flight hold stands down for a pinned vm:check and stays for an unpinned one, read end to end from a held lock through `_judge_receipt_run` into `wl_judge.sanitize_next_action`, and through `worktree_check`'s routing."""
    import subprocess
    import types
    from unittest import mock

    import wl_judge
    import wl_worktrees
    import worklist_messages as M

    script = os.path.join(tmp, "drills", "vm_check.py")
    os.makedirs(os.path.dirname(script))
    with open(script, "w") as f:
        f.write(HOLDER_SRC)
    order = "land the two pending commits in the main checkout now"
    sha = "a" * 40

    def under_lock(payload, label):
        """Hold a fresh lock with `payload` (PID is the child's pid) and answer (receipt_run, next_action after the sanitiser, worktree_check's notes, its blocks)."""
        path = os.path.join(tmp, "%s.lock" % label)
        child = subprocess.Popen(
            [sys.executable, script, path, payload], stdout=subprocess.PIPE, text=True
        )
        try:
            held_line = child.stdout.readline() if child.stdout is not None else ""
            if held_line.strip() != "held":
                FAILURES.append("%s: the holder child never took the lock" % label)
                return None, order, [], []
            with mock.patch.object(wl_checks, "vm_check_lock_path", stub(path)):
                run = wl_checks._judge_receipt_run()
                out = wl_judge.sanitize_next_action({"next_action": order}, receipt_run=run)
                notes, blocks = [], []
                with (
                    mock.patch.object(
                        wl_worktrees, "survey", stub({"unlanded": [{"id": "l"}], "cache": {}})
                    ),
                    mock.patch.object(wl_worktrees, "report_lines", stub("")),
                    mock.patch.object(wl_worktrees, "unlanded_lines", stub("l")),
                    mock.patch.object(wl_checks, "release_local_running", stub(False)),
                    mock.patch.object(wl_checks, "green_receipt_on_unpushed_head", stub(False)),
                    mock.patch.object(wl_checks, "staged_index_paths", stub([])),
                    mock.patch.object(
                        wl_checks,
                        "outq_add",
                        lambda _w, _s, _st, _k, text, _p, **_kw: notes.append(text),
                    ),
                ):
                    wl_checks.worktree_check(
                        None,
                        "s",
                        {},
                        types.SimpleNamespace(items={}),
                        None,
                        {"cwd": tmp},
                        lambda key, *_a, **_kw: blocks.append(key),
                    )
            return run, out["next_action"], notes, blocks
        finally:
            child.kill()
            child.wait()

    run, action, notes, blocks = under_lock(
        '{"pid": PID, "session": "s", "commit": "%s"}' % sha, "pinned"
    )
    check("a pinned vm:check sets no receipt_run", run, None)
    check("...and the landing order is kept", action, order)
    check("...and the unlanded lease is not held for it (it blocks)", blocks, ["worktree-unlanded"])
    check("...with no vm:check note", notes, [])

    run, action, notes, blocks = under_lock('{"pid": PID, "session": "s"}', "unpinned")
    check("control: an unpinned vm:check sets receipt_run", run, "vm:check")
    check(
        "...and the landing order is rewritten as before",
        action,
        M.V_JUDGE_RECEIPT_ORDER_REJECTED % ("vm:check", order[:120]),
    )
    check(
        "...and the unlanded lease is held with the vm:check note",
        notes,
        [M.N_WORKTREE_VMCHECK % "l"],
    )
    check("...and blocks nothing", blocks, [])

    for label, value in (("short", '"abc1234"'), ("number", "42"), ("upper", '"%s"' % ("A" * 40))):
        run, action, _notes, _blocks = under_lock(
            '{"pid": PID, "commit": %s}' % value, "pin-" + label
        )
        check("an unreadable pin (%s) counts as unpinned" % label, run, "vm:check")

    for raw, label in (
        (b"", "empty"),
        (b"not json", "garbage"),
        (b"[1]", "list"),
        (b'{"commit": 7}', "number"),
        (('{"commit": "%s\\n"}' % sha).encode(), "trailing newline"),
    ):
        check(
            "vm_check_pin: an unreadable payload (%s) reads no pin" % label,
            wl_checks.vm_check_pin(raw),
            "",
        )
    check(
        "vm_check_pin: a full sha reads as the pin",
        wl_checks.vm_check_pin(('{"commit": "%s"}' % sha).encode()),
        sha,
    )


def staged_index_cases(tmp):
    """staged_index_paths: a real repo answers its staged path, a clean one answers [], and a path that is no repo answers [] (worktree land refuses on a staged index, so the unlanded-lease block is held while it is non-empty)."""
    import subprocess

    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)

    def run(*a):
        return subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)

    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
    check("clean index", wl_checks.staged_index_paths(repo), [])
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("x")
    run("add", "a.txt")
    check("staged path", wl_checks.staged_index_paths(repo), ["a.txt"])
    check("not a repo", wl_checks.staged_index_paths(os.path.join(tmp, "absent")), [])


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
    with tempfile.TemporaryDirectory() as tmp:
        pinned_vm_check_cases(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        staged_index_cases(tmp)

    if FAILURES:
        print("FAILURES: %d" % len(FAILURES))
        for f in FAILURES:
            print("  " + f)
        return 1
    print("case(s) passed; FAILURES: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())

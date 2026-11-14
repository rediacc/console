"""The judge does not order a main-checkout commit while a receipt is being built (agent/plans/PLAN-stop-hook-retro-20261110.md R20261110.3, D3).

12 judge blocks in the 2026-11-09/10 window drew a lead reply explaining that a commit would void the receipt a running vm:check or ci:quick was building, and the prompt itself told the judge "unpushed work cannot disturb a run in flight". The hook already knew such a run was live (`wl_checks.vm_check_running`, `ci_quick_running`, which hold the unlanded-lease block); now the judge is told (JUDGE_RECEIPT_IN_FLIGHT) and a main-checkout commit, edit, land or cherry-pick order is rewritten (`wl_judge.RECEIPT_ORDERS`).

The fixture holds the real fleet lock with a process whose argv is a vm:check run, the way vm_check.Lock.acquire writes it; its inverse is the same lock free.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import types

import pytest

from rediacc_hooks.tests import wlfix

J = wlfix.import_wl("wl_judge")
CK = wlfix.import_wl("wl_checks")
M = wlfix.import_wl("worklist_messages")

# The 23:12:05 order, with the held edits it was about.
ORDER = "Commit the held #313e832f records in the main checkout now."
CONTINUE = {
    "verdict": "continue",
    "reason": "That is a reason to work elsewhere, not a reason to stop.",
    "next_action": ORDER,
}

STAND_IN = (
    "import fcntl, json, os, sys\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "os.ftruncate(fd, 0)\n"
    "os.pwrite(fd, json.dumps({'pid': os.getpid()}).encode(), 0)\n"
    "print('held', flush=True)\n"
    "sys.stdin.read()\n"
)


@pytest.fixture
def locks(tmp_path, monkeypatch):
    """A private runtime dir for the fleet lock and a private ci:quick clone path, so neither reads the operator's."""
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("CI_QUICK_CLONE_DIR", str(tmp_path / "ciq-clone"))
    lock = CK.vm_check_lock_path()
    assert lock.startswith(str(runtime)), lock
    return types.SimpleNamespace(root=tmp_path, lock=lock)


@pytest.fixture
def vm_check(locks):
    """A process named like the vm:check script holding the fleet lock."""
    script = locks.root / "standins" / "drills" / "vm_check.py"
    script.parent.mkdir(parents=True)
    script.write_text(STAND_IN, encoding="utf-8")
    holder = subprocess.Popen(
        [sys.executable, str(script), locks.lock],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdin is not None
    try:
        assert holder.stdout.readline().strip() == "held"
        yield holder
    finally:
        holder.stdin.close()
        holder.stdout.close()
        holder.wait(timeout=30)


@pytest.mark.usefixtures("vm_check")
def test_a_held_vm_check_lock_is_the_receipt_run(locks):
    assert CK._judge_receipt_run(locks.root) == "vm:check"


def test_inverse_a_free_lock_is_no_receipt_run(locks):
    with open(locks.lock, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"pid": os.getpid()}))
    assert CK._judge_receipt_run(locks.root) is None


def test_a_live_ci_quick_of_this_checkout_is_the_receipt_run(locks, monkeypatch):
    monkeypatch.setattr(CK, "ci_quick_running", lambda root: root == locks.root)
    assert CK._judge_receipt_run(locks.root) == "ci:quick"


def test_a_failed_read_is_no_receipt_run(locks, monkeypatch):
    def boom():
        raise OSError("unreadable")

    monkeypatch.setattr(CK, "vm_check_running", boom)
    assert CK._judge_receipt_run(locks.root) is None


# ---- the prompt and the sanitiser, through a canned claude ---------------------------------------


@pytest.fixture
def judge(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    seen = tmp_path / "argv.json"
    reply = tmp_path / "reply.json"
    script = bindir / "claude"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        "open(%r, 'w').write(json.dumps(sys.argv[1:]))\n"
        "print(open(%r).read())\n" % (str(seen), str(reply)),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % bindir)
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    def answer(out):
        reply.write_text(json.dumps({"is_error": False, "structured_output": out}), "utf-8")

    def prompt():
        got = json.loads(seen.read_text(encoding="utf-8"))
        return got[got.index("-p") + 1]

    return types.SimpleNamespace(answer=answer, prompt=prompt)


def ask(receipt_run):
    return J.run_judge(
        ["[ ] (deadbeef) #313e832f the held records"],
        0,
        "vm:check is building its receipt; the #313e832f records wait for it.",
        0,
        "none declared",
        with_riders=False,
        receipt_run=receipt_run,
    )


@pytest.mark.usefixtures("vm_check")
def test_a_running_receipt_puts_the_paragraph_in_and_rewrites_the_order(locks, judge):
    judge.answer(dict(CONTINUE))
    verdict, err = ask(CK._judge_receipt_run(locks.root))
    assert err is None, err
    assert "RECEIPT IN FLIGHT: a vm:check run" in judge.prompt()
    assert verdict["next_action"].startswith("[rejected by the stop gate"), verdict
    assert "vm:check run is building its receipt" in verdict["next_action"]


def test_inverse_a_free_lock_lets_the_order_pass(locks, judge):
    judge.answer(dict(CONTINUE))
    verdict, err = ask(CK._judge_receipt_run(locks.root))
    assert err is None, err
    assert "RECEIPT IN FLIGHT:" not in judge.prompt()
    assert verdict["next_action"] == ORDER


def test_the_cidwait_sentence_is_qualified():
    assert "unpushed work cannot\ndisturb a run in flight, except while a vm:check or ci:quick" in (
        M.JUDGE_PROMPT
    )


@pytest.mark.parametrize(
    "order",
    [
        ORDER,
        "Edit the plan text under agent/plans and record the #63c8f457 finding.",
        "Land the writer's commits with the printed cherry-pick lines.",
        "cherry-pick 1a2b3c4 onto the branch",
    ],
)
def test_main_checkout_orders_are_rewritten_while_a_receipt_runs(order):
    got = J.sanitize_next_action({"next_action": order}, receipt_run="ci:quick")
    assert got["next_action"].startswith("[rejected by the stop gate"), got
    assert "ci:quick" in got["next_action"]


@pytest.mark.parametrize(
    "order",
    [
        "Start a writer in a lease tree to commit the #313e832f records.",
        "Have the worktree writer edit wl_judge.py.",
        "Read the vm:check log for the V1.1 step.",
    ],
)
def test_lease_orders_and_non_edits_pass_while_a_receipt_runs(order):
    got = J.sanitize_next_action({"next_action": order}, receipt_run="vm:check")
    assert got["next_action"] == order


def test_control_no_receipt_run_rewrites_nothing():
    got = J.sanitize_next_action({"next_action": ORDER})
    assert got["next_action"] == ORDER


def test_settle_by_effort_hands_back_the_order_sanitized_for_the_receipt(monkeypatch):
    table = {"checks": {"out-of-sync": {"block": "high", "advise": "smart"}}}
    monkeypatch.setattr(J.wl_effort, "load", lambda *_a: (table, ""))
    out = dict(CONTINUE, basis="out-of-sync")
    got = J.settle_by_effort(out, "smart", table=table, receipt_run="vm:check")
    [(_key, text)] = got["effort_advised"]
    assert "rejected by the stop gate" in text
    assert ORDER not in text.split("Its original text was")[0]

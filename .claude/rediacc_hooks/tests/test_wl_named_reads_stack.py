"""Named read failures in `wl_stack` and `wl_bgsweep` (SF7 of agent/plans/PLAN-silent-failure-sweep.md).

THE CLASS: a broad handler that turned a failed read into the same value as "nothing there". Here:
  * `wl_stack.main_checkout_tasks` raises StackReadError when git cannot list the trees, instead of answering "not the main checkout"; the stop's existing `landing-stack-tasks` handler names it.
  * `wl_stack.notify_line` still answers "" without a message, and `wl_stack.notify_problem` names why when a record exists and does not read, so a caller never latches a failed read as a sent message (D6).
  * `wl_bgsweep.findings` keeps every finding it could make when the owner read fails, and names the loss in `unread`.

Every red case has a silent twin, so the naming is seen not to fire on a clean read.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest
import wl_bgsweep as B
import wl_roster
import wl_stack as WS

DEV, PR = "1120-1", "1120-2"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(directory, *args) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_ENV)
    proc = subprocess.run(
        ["git", "-C", str(directory), *args], check=True, capture_output=True, env=env
    )
    return proc.stdout.decode().strip()


@pytest.fixture
def world(tmp_path):
    """`(dev, landing, record_file)`: a main tree on DEV, a linked tree on PR, no record yet."""
    dev = tmp_path / "console"
    dev.mkdir()
    _git(dev, "init", "-q", "-b", "main")
    (dev / "f").write_text("x\n", encoding="utf-8")
    _git(dev, "add", "f")
    _git(dev, "commit", "-q", "-m", "init")
    _git(dev, "branch", DEV)
    _git(dev, "branch", PR)
    _git(dev, "symbolic-ref", "HEAD", "refs/heads/" + DEV)
    landing = tmp_path / "console-landing"
    _git(dev, "worktree", "add", "-q", str(landing), PR)
    dev, landing = pathlib.Path(os.path.realpath(dev)), pathlib.Path(os.path.realpath(landing))
    return dev, landing, dev / ".git" / "rediacc-landing.json"


LIVE = [
    {"id": "b1", "type": "shell", "description": "npm run vm:check"},
    {"id": "a2", "type": "subagent", "description": "lease writer"},
]
METAS = {"a2": {"worktree": "/elsewhere"}}


# ---- wl_stack.main_checkout_tasks ----------------------------------------------


def test_main_checkout_tasks_raises_when_git_cannot_list_the_trees(world, monkeypatch):
    """The defect: a failed `git worktree list` read as "not the main checkout", so a task that holds promote went missing."""
    dev, _landing, _rec = world
    monkeypatch.setattr(WS, "_git_full", lambda _cwd, *_a: (128, "", "fatal: sf7-injected"))
    with pytest.raises(WS.StackReadError, match=r"could not list the trees .*sf7-injected"):
        WS.main_checkout_tasks(dev, LIVE, METAS)


def test_a_directory_with_no_checkout_is_not_the_main_checkout(tmp_path):
    """CONTROL: git saying "not a git repository" is an answer (no checkout), not a failed read: no `.git` at all, or the hook fixtures' plain empty `.git` directory."""
    assert WS.main_checkout_tasks(tmp_path, LIVE, METAS) == []
    (tmp_path / ".git").mkdir()
    assert WS.main_checkout_tasks(tmp_path, LIVE, METAS) == []


def test_main_checkout_tasks_lists_the_main_checkout_tasks(world):
    dev, _landing, _rec = world
    assert WS.main_checkout_tasks(dev, LIVE, METAS) == ["npm run vm:check"]


def test_main_checkout_tasks_is_empty_in_another_tree(world):
    _dev, landing, _rec = world
    assert WS.main_checkout_tasks(landing, LIVE, METAS) == []


# ---- wl_stack.notify_line / notify_problem -------------------------------------


def test_no_record_is_nothing_to_send_and_no_problem(world):
    dev, landing, _rec = world
    assert WS.notify_line(landing, "cd-done", pr=7, sha="abc1234") == ""
    assert WS.notify_problem(landing) == ""
    assert WS.notify_problem(dev) == ""


def test_an_unreadable_record_leaves_no_message_and_names_the_defect(world):
    """The cd-done defect's input: a defective record used to read as "no record", and a caller could not tell the two apart."""
    _dev, landing, rec = world
    rec.write_text("{ not json\n", encoding="utf-8")
    assert WS.notify_line(landing, "cd-done", pr=7, sha="abc1234") == ""
    problem = WS.notify_problem(landing)
    assert problem.startswith("the landing record binds nothing: ")
    assert "is unreadable" in problem
    assert "rediacc-landing.json" in problem


def test_an_unloadable_reader_is_named(world, monkeypatch):
    _dev, landing, _rec = world

    def broken():
        raise ImportError("sf7-injected")

    monkeypatch.setattr(WS, "_hooks_pkg", broken)
    assert WS.notify_line(landing, "cd-done") == ""
    assert "sf7-injected" in WS.notify_problem(landing)


def test_a_valid_record_gives_the_message_and_no_problem(world):
    dev, landing, rec = world
    rec.write_text(json.dumps({"path": str(landing), "branch": PR}), encoding="utf-8")
    text = WS.notify_line(landing, "cd-done", pr=7, sha="abc1234def")
    assert text.startswith("CD DONE: the landing branch %s (PR #7)" % PR)
    assert str(dev) in text
    assert WS.notify_problem(landing) == ""


def test_an_unlisted_main_checkout_is_named_inside_the_message(world, monkeypatch):
    """The message still goes out (the record read), and the tree it names says why it is generic."""
    _dev, landing, rec = world
    rec.write_text(json.dumps({"path": str(landing), "branch": PR}), encoding="utf-8")
    real = WS._git_full
    monkeypatch.setattr(
        WS,
        "_git_full",
        lambda cwd, *a: (128, "", "fatal: sf7") if a[:2] == ("worktree", "list") else real(cwd, *a),
    )
    text = WS.notify_line(landing, "merged", pr=7)
    assert "the main checkout (git could not list the trees" in text


# ---- wl_bgsweep.findings -------------------------------------------------------

WRAP = (
    "/bin/bash -B -c source /home/u/.claude/shell-snapshots/snap.sh 2>/dev/null || true && "
    "eval '%s' < /dev/null && pwd -P >| /tmp/claude-1a2b-cwd /bin/bash"
)
LIM = B.BGSWEEP_AGE_MIN * 60
# An undeclared orphan (pid 2) and a declared stub old enough for the owner read (pid 50).
ROWS = [
    (2, 1, WRAP % "sleep 99999", LIM + 60),
    (50, 1, WRAP % "cd /tmp/pxprobe && node stub.mjs", LIM + 600),
]
STDOUT = {50: "bstub1"}


def _run(monkeypatch, owners, rows=ROWS):
    monkeypatch.setenv("WORKLIST_HARNESS_PID", "1")
    table = [(1, 0, "claude", 0), *rows]
    return B.findings(
        table,
        [(p, pp, c) for p, pp, c, _a in table],
        live_ids={"bstub1"},
        stdout_task=STDOUT.get,
        owners=owners,
        pgid_of=lambda _p: None,
        target_note=lambda _t: "",
    )


def test_a_failed_owner_read_keeps_the_other_findings_and_is_named(monkeypatch):
    def boom(_ages):
        raise OSError("sf7-owner")

    got = _run(monkeypatch, boom)
    assert [(f.pid, f.kind) for f in got] == [(2, B.ORPHAN)]
    assert "the owner read failed (OSError: sf7-owner)" in got.unread
    assert "1 declared shell(s)" in got.unread


def test_a_clean_owner_read_names_nothing(monkeypatch):
    got = _run(monkeypatch, lambda _ages: ({"bstub1": "awriter1"}, {"awriter1"}, {"awriter1": 98}))
    assert sorted((f.pid, f.kind) for f in got) == [(2, B.ORPHAN), (50, B.FINISHED_AGENT)]
    assert got.unread == ""


def test_an_empty_process_table_is_a_failed_read():
    got = B.findings([], [], live_ids=set(), owners=None)
    assert list(got) == []
    assert "process table" in got.unread


def test_owner_context_lets_a_failed_read_raise(monkeypatch, tmp_path):
    def boom(*_a, **_k):
        raise OSError("sf7-metas")

    monkeypatch.setattr(wl_roster, "load_metas", boom)
    with pytest.raises(OSError, match="sf7-metas"):
        B.owner_context({}, str(tmp_path), "deadbeef", {"bstub1": LIM + 600})

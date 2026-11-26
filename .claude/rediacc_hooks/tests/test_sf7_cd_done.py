"""SF7's cd-done clause, for the lead to land with the wl_checks change: an unreadable landing record is named in the cd-done step, and a readable one latches once."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import types

import wl_checks
import wl_prscope

PR = "1120-2"


def _git(directory, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@e.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@e.invalid",
    )
    subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, env=env)


def _world(tmp_path):
    dev = tmp_path / "console"
    dev.mkdir()
    _git(dev, "init", "-q", "-b", "main")
    (dev / "f").write_text("x\n")
    _git(dev, "add", "f")
    _git(dev, "commit", "-q", "-m", "init")
    _git(dev, "branch", PR)
    landing = tmp_path / "console-landing"
    _git(dev, "worktree", "add", "-q", str(landing), PR)
    return pathlib.Path(os.path.realpath(dev)), pathlib.Path(os.path.realpath(landing))


def _step(monkeypatch):
    step = types.SimpleNamespace(release=True, sha="abc1234", text="STEP", blocks=False, pr=7)
    monkeypatch.setattr(wl_checks.wl_ci, "pr_link", lambda *_a, **_k: ([], ""))
    monkeypatch.setattr(wl_prscope, "landing_loop", lambda *_a, **_k: step)
    monkeypatch.setattr(wl_checks, "ci_verdict", lambda *_a, **_k: "green")


def test_an_unreadable_record_is_named_in_the_cd_done_step(tmp_path, monkeypatch):
    dev, landing = _world(tmp_path)
    (dev / ".git" / "rediacc-landing.json").write_text("{ not json\n")
    _step(monkeypatch)
    wl_checks.READ_FAILURES.clear()
    state_doc: dict = {}
    got = wl_checks.landing_next_text(
        types.SimpleNamespace(branch="b"), str(landing), "wl", "deadbeef", state_doc, {}, {}, []
    )
    assert got == ("STEP", False)
    assert "landing" not in state_doc
    named = wl_checks.READ_FAILURES["cd-done-message"]
    assert "the landing record binds nothing" in named
    assert "rediacc-landing.json" in named


def test_a_readable_record_latches_once(tmp_path, monkeypatch):
    dev, landing = _world(tmp_path)
    (dev / ".git" / "rediacc-landing.json").write_text(
        json.dumps({"path": str(landing), "branch": PR})
    )
    _step(monkeypatch)
    wl_checks.READ_FAILURES.clear()
    state_doc: dict = {}
    got = wl_checks.landing_next_text(
        types.SimpleNamespace(branch="b"), str(landing), "wl", "deadbeef", state_doc, {}, {}, []
    )
    assert got[1] is True
    assert "CD DONE" in got[0]
    assert state_doc["landing"] == {"cd_done": "abc1234"}
    assert "cd-done-message" not in wl_checks.READ_FAILURES
    # 1cd88702.6: the second stop on the same sha, with the latched state, says CD DONE no more.
    again = wl_checks.landing_next_text(
        types.SimpleNamespace(branch="b"), str(landing), "wl", "deadbeef", state_doc, {}, {}, []
    )
    assert "CD DONE" not in again[0], again
    assert state_doc["landing"] == {"cd_done": "abc1234"}

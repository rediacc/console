"""`wl_checks.green_receipt_on_unpushed_head`: a lease waits while a passing receipt for exactly HEAD still owes its push.

The control row is the one that holds (green receipt, HEAD unpushed); every other row turns one condition off and must not hold, so a False below is that condition's doing.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from rediacc_hooks.tests import wlfix

CK = wlfix.import_wl("wl_checks")


def _git(repo, *args) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A checkout with a bare upstream, one pushed commit, and one commit on top of it."""
    bare = tmp_path / "up.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    _git(work, "config", "user.email", "t@example.org")
    _git(work, "config", "user.name", "t")
    (work / "a").write_text("1", encoding="utf-8")
    _git(work, "add", "a")
    _git(work, "commit", "-q", "-m", "one")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "-u", "origin", "main")
    (work / "a").write_text("2", encoding="utf-8")
    _git(work, "commit", "-q", "-am", "two")
    (work / ".ci" / "cache").mkdir(parents=True)
    return work


def _receipt(repo, **fields):
    path = repo / ".ci" / "cache" / "prepush-receipt.json"
    path.write_text(json.dumps(fields), encoding="utf-8")


def test_control_a_green_receipt_for_an_unpushed_head_holds(repo):
    _receipt(repo, exitCode=0, head=_git(repo, "rev-parse", "HEAD"))
    assert CK.green_receipt_on_unpushed_head(str(repo)) is True


def test_a_red_receipt_does_not_hold(repo):
    _receipt(repo, exitCode=1, head=_git(repo, "rev-parse", "HEAD"))
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_a_receipt_for_another_commit_does_not_hold(repo):
    _receipt(repo, exitCode=0, head=_git(repo, "rev-parse", "HEAD~1"))
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_a_pushed_head_does_not_hold(repo):
    _receipt(repo, exitCode=0, head=_git(repo, "rev-parse", "HEAD"))
    _git(repo, "push", "-q", "origin", "main")
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_a_missing_or_malformed_receipt_does_not_hold(repo):
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False
    (repo / ".ci" / "cache" / "prepush-receipt.json").write_text("{not json", encoding="utf-8")
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_no_upstream_is_a_doubt_and_does_not_hold(repo):
    _git(repo, "branch", "--unset-upstream")
    _receipt(repo, exitCode=0, head=_git(repo, "rev-parse", "HEAD"))
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False

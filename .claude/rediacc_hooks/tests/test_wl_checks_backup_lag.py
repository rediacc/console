"""The `backup-lag` Stop advisory (box G6 of agent/plans/PLAN-local-first-delivery.md): `wl_checks.backup_lag` asks `backup_ref status --cached` and speaks only at exit 1 (more than 50 commits or 6 h ahead of the live backup ref), and the check sits in the effort table at advise level, never a block.

REAL GIT: each case builds a throwaway repository on a feature branch whose `.ci` is a link to this tree's `.ci`, records the oid the last sync left in `rediacc-backup/last-live`, and runs the function the Stop hook runs. Controls: 50 commits ahead is silent, 51 speaks, `main` and a repository with no record are silent.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import time

import pytest
import wl_checks
import wl_standdown

from rediacc_hooks.tests import wlfix

REAL_ROOT = pathlib.Path(__file__).resolve().parents[3]
ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **ENV},
    ).stdout.strip()


def make_repo(
    tmp_path: pathlib.Path,
    ahead: int,
    record: bool = True,
    branch: str = "1104-1",
    record_branch: str | None = None,
):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a").write_text("seed\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    if branch != "main":
        git(root, "checkout", "-q", "-b", branch)
    live = git(root, "rev-parse", "HEAD")
    for i in range(ahead):
        git(root, "commit", "-q", "--allow-empty", "-m", "c%d" % i)
    if record:
        state = pathlib.Path(git(root, "rev-parse", "--absolute-git-dir")) / "rediacc-backup"
        state.mkdir()
        # The record names its branch (5936542865): "<branch> <oid>".
        (state / "last-live").write_text(
            "%s %s\n" % (record_branch or branch, live), encoding="utf-8"
        )
    (root / ".ci").symlink_to(REAL_ROOT / ".ci")
    return root


def test_fifty_commits_ahead_is_silent(tmp_path):
    assert wl_checks.backup_lag(make_repo(tmp_path, 50)) is None


@pytest.mark.parametrize(("age_h", "speaks"), [(5.9, False), (6.1, True)])
def test_the_oldest_unbacked_commit_is_judged_against_six_hours(
    tmp_path, monkeypatch, age_h, speaks
):
    root = make_repo(tmp_path, 0)
    stamp = int(time.time() - age_h * 3600)
    monkeypatch.setenv("GIT_COMMITTER_DATE", "%d +0000" % stamp)
    git(root, "commit", "-q", "--allow-empty", "-m", "old")
    monkeypatch.delenv("GIT_COMMITTER_DATE")
    text = wl_checks.backup_lag(root)
    assert (text is not None) == speaks
    if speaks:
        assert text.startswith("BACKUP LAG: 1104-1 is 1 commits ahead")


def test_fifty_one_commits_ahead_speaks(tmp_path):
    text = wl_checks.backup_lag(make_repo(tmp_path, 51))
    assert text is not None
    assert text.startswith("BACKUP LAG: 1104-1 is 51 commits ahead")
    assert "backup-ref sync" in text


@pytest.mark.parametrize("case", ["main", "no-record"])
def test_nothing_to_judge_is_silent(tmp_path, case):
    if case == "main":
        root = make_repo(tmp_path, 60, branch="main")
    else:
        root = make_repo(tmp_path, 60, record=False)
    assert wl_checks.backup_lag(root) is None


def test_a_broken_module_is_silence_not_a_traceback(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    root = make_repo(tmp_path, 60)
    (root / ".ci").unlink()
    assert wl_checks.backup_lag(root) is None


def test_the_advisory_rides_the_allow_queue_at_advise_level():
    source = (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
    assert 'vadd("backup-lag"' not in source
    assert re.search(r'"backup-lag",\s*_bl,', source)
    table = json.loads((wlfix.STOP_DIR.parent.parent / "config" / "effort.json").read_text("utf-8"))
    assert table["checks"]["backup-lag"] == {"advise": "low"}
    assert "block" not in table["checks"]["backup-lag"]
    assert "backup-lag" not in wl_standdown.CORE


def test_a_record_naming_another_branch_is_silent(tmp_path):
    """CONTROL: a cached live oid recorded for another branch says nothing about this one."""
    assert wl_checks.backup_lag(make_repo(tmp_path, 51, record_branch="0101-1")) is None


# ---- the verdict is cached by repository state (PLAN-tooling-speed.md SP2, D3) ----


def _count_children(monkeypatch):
    calls = []
    real = wl_checks._backup_lag_ask

    def counting(root):
        calls.append(str(root))
        return real(root)

    monkeypatch.setattr(wl_checks, "_backup_lag_ask", counting)
    return calls


def test_backup_lag_second_call_on_unchanged_state_starts_no_child(tmp_path, monkeypatch):
    root = make_repo(tmp_path, 51)
    calls = _count_children(monkeypatch)
    first = wl_checks.backup_lag(root)
    assert first is not None
    assert wl_checks.backup_lag(root) == first
    assert len(calls) == 1


def test_backup_lag_new_commit_asks_again(tmp_path, monkeypatch):
    """Control: a commit moves the key, so the cache cannot serve a stale verdict."""
    root = make_repo(tmp_path, 51)
    calls = _count_children(monkeypatch)
    first = wl_checks.backup_lag(root)
    git(root, "commit", "-q", "--allow-empty", "-m", "one more")
    second = wl_checks.backup_lag(root)
    assert len(calls) == 2
    assert second is not None
    assert second != first


def test_backup_lag_new_sync_record_asks_again(tmp_path, monkeypatch):
    """Control: a sync rewrites last-live without moving a ref, and the verdict clears."""
    root = make_repo(tmp_path, 51)
    calls = _count_children(monkeypatch)
    assert wl_checks.backup_lag(root) is not None
    state = pathlib.Path(git(root, "rev-parse", "--absolute-git-dir")) / "rediacc-backup"
    (state / "last-live").write_text(
        "1104-1 %s\n" % git(root, "rev-parse", "HEAD"), encoding="utf-8"
    )
    assert wl_checks.backup_lag(root) is None
    assert len(calls) == 2


def test_backup_lag_expires_by_age(tmp_path, monkeypatch):
    root = make_repo(tmp_path, 51)
    calls = _count_children(monkeypatch)
    wl_checks.backup_lag(root)
    later = time.time() + wl_checks.BACKUP_LAG_CACHE_TTL_S + 1
    monkeypatch.setattr(wl_checks.time, "time", lambda: later)
    wl_checks.backup_lag(root)
    assert len(calls) == 2


def test_backup_lag_failed_child_is_not_cached(tmp_path, monkeypatch):
    """Control: a timeout or crash is asked again, never remembered as 'no lag'."""
    root = make_repo(tmp_path, 51)
    outcomes = iter([(None, False), ("BACKUP LAG: x", True)])
    monkeypatch.setattr(wl_checks, "_backup_lag_ask", lambda _root: next(outcomes))
    assert wl_checks.backup_lag(root) is None
    assert wl_checks.backup_lag(root) == "BACKUP LAG: x"

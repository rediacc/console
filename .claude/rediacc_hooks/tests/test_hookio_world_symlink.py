"""hookio.ensure_world_symlink: create once, accept a concurrent creator's identical link, replace a link to anything else, and survive both thread contention and a stale temporary name (reviews 0279aff2.1-.3)."""

from __future__ import annotations

import os
import stat
import threading

import pytest

from rediacc_hooks import hookio


def _dirs(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    link = tmp_path / "world"
    os.symlink(old, link)
    return old, new, link


def test_threads_racing_on_the_replace_path_all_succeed(tmp_path):
    _old, new, link = _dirs(tmp_path)
    errors: list[OSError] = []
    gate = threading.Barrier(16)

    def run() -> None:
        gate.wait()
        try:
            hookio.ensure_world_symlink(new, link)
        except OSError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert os.readlink(link) == str(new)
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_a_link_to_another_target_is_replaced(tmp_path):
    _old, new, link = _dirs(tmp_path)
    hookio.ensure_world_symlink(new, link)
    assert os.readlink(link) == str(new)


def test_a_stale_temporary_name_is_cleared(tmp_path):
    old, new, link = _dirs(tmp_path)
    stale = "%s.%d.%d.tmp" % (link, os.getpid(), threading.get_ident())
    os.symlink(old, stale)
    hookio.ensure_world_symlink(new, link)
    assert os.readlink(link) == str(new)
    assert not os.path.lexists(stale)


def test_golden_world_creates_a_private_directory(tmp_path, monkeypatch):
    """0c9a169c.4 control: a fresh name becomes a 0700 directory this user owns, and a second call admits it."""
    monkeypatch.setattr(hookio, "GOLDEN_TEMP_DIR", str(tmp_path))
    path = hookio.golden_world("rediacc-guard-fresh")
    st = os.lstat(path)
    assert path == str(tmp_path / "rediacc-guard-fresh")
    assert stat.S_ISDIR(st.st_mode)
    assert st.st_uid == os.getuid()
    assert stat.S_IMODE(st.st_mode) == 0o700
    assert hookio.golden_world("rediacc-guard-fresh") == path


def test_golden_world_refuses_a_planted_symlink(tmp_path, monkeypatch):
    """0c9a169c.4: a symlink pre-planted at the predictable path is refused, so no fixture write follows it."""
    monkeypatch.setattr(hookio, "GOLDEN_TEMP_DIR", str(tmp_path))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, tmp_path / "rediacc-guard-planted")
    with pytest.raises(RuntimeError, match="not a directory this user"):
        hookio.golden_world("rediacc-guard-planted")


def test_golden_world_refuses_a_plain_file(tmp_path, monkeypatch):
    """0c9a169c.4: a non-directory at the path is refused rather than written into."""
    monkeypatch.setattr(hookio, "GOLDEN_TEMP_DIR", str(tmp_path))
    (tmp_path / "rediacc-guard-file").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not a directory this user"):
        hookio.golden_world("rediacc-guard-file")

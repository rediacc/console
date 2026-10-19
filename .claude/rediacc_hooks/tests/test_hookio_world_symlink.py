"""hookio.ensure_world_symlink: create once, accept a concurrent creator's identical link, replace a link to anything else, and survive both thread contention and a stale temporary name (reviews 0279aff2.1-.3)."""

from __future__ import annotations

import os
import threading

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

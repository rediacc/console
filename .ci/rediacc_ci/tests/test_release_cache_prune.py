"""`rediacc_ci.release.cache_prune`: which release-cache paths a prune keeps, deletes and reports, on temp directories."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.release import cache_prune, local

if TYPE_CHECKING:
    import pathlib

NOW = 2_000_000_000.0
DAY = cache_prune.DAY


def _age(path: pathlib.Path, days: float) -> None:
    stamp = NOW - days * DAY
    os.utime(path, (stamp, stamp))


def _clone(store: pathlib.Path, char: str, days: float) -> pathlib.Path:
    clone = store / (char * 40)
    (clone / "node_modules").mkdir(parents=True)
    (clone / "node_modules" / "f").write_text("x")
    _age(clone, days)
    return clone


@pytest.fixture
def store(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "release"
    path.mkdir()
    return path


def test_clone_dir_matches_the_local_constant():
    assert cache_prune.CLONE_REL == local.CLONE_REL


def test_newest_clone_kept_and_older_deleted(store):
    old, mid, new = _clone(store, "a", 30), _clone(store, "b", 20), _clone(store, "c", 1)
    deleted, stuck = cache_prune.prune(store, now=NOW)
    assert sorted(deleted) == sorted([old, mid])
    assert not stuck
    assert new.is_dir()
    assert not old.exists()
    assert not mid.exists()


def test_old_out_and_records_deleted_recent_kept(store):
    _clone(store, "c", 1)
    old_out, new_out = store / "out-old", store / "out-new"
    old_rec, new_rec = store / "run-old.json", store / "run-new.json"
    for path in (old_out, new_out):
        path.mkdir()
    for path in (old_rec, new_rec):
        path.write_text("{}")
    _age(old_out, 15)
    _age(old_rec, 15)
    _age(new_out, 13)
    _age(new_rec, 13)
    deleted, _stuck = cache_prune.prune(store, now=NOW)
    assert sorted(deleted) == sorted([old_out, old_rec])
    assert new_out.is_dir()
    assert new_rec.is_file()


def test_running_release_keeps_everything(store):
    old, _new = _clone(store, "a", 30), _clone(store, "c", 1)
    with cache_prune.run_lock(store), pytest.raises(cache_prune.PruneRefusedError):
        cache_prune.prune(store, now=NOW)
    assert old.is_dir()


def test_root_owned_path_is_reported_with_the_sudo_line(store):
    old, _new = _clone(store, "a", 30), _clone(store, "c", 1)

    def cannot(path: pathlib.Path) -> None:
        del path

    deleted, stuck = cache_prune.prune(store, now=NOW, remover=cannot)
    assert not deleted
    assert stuck == [old]
    assert cache_prune.sudo_line(old) == "sudo rm -rf %s" % old


def test_main_reports_stuck_with_rc_1_and_dry_run_deletes_nothing(store, tmp_path, capsys):
    root = tmp_path
    clones = root / cache_prune.CLONE_REL
    clones.parent.mkdir(parents=True, exist_ok=True)
    store.rename(clones)
    old = _clone(clones, "a", 30)
    _clone(clones, "c", 1)
    assert cache_prune.main(["--dry-run"], root=root) == 0
    assert old.is_dir()
    assert "would delete" in capsys.readouterr().out
    assert cache_prune.main([], root=root) == 0
    assert not old.exists()


def test_main_exits_1_and_prints_the_sudo_line_for_a_path_it_cannot_delete(
    store, tmp_path, capsys, monkeypatch
):
    """05003da0.3: the stuck branch of main, which the dry-run test above never reaches."""
    root = tmp_path
    clones = root / cache_prune.CLONE_REL
    clones.parent.mkdir(parents=True, exist_ok=True)
    store.rename(clones)
    old = _clone(clones, "a", 30)
    _clone(clones, "c", 1)
    # prune() bound the default remover at definition time, so pass it through the same seam.
    monkeypatch.setattr(
        cache_prune.prune,
        "__kwdefaults__",
        {**(cache_prune.prune.__kwdefaults__ or {}), "remover": lambda _path: None},
    )
    assert cache_prune.main([], root=root) == 1
    out = capsys.readouterr().out
    assert "cannot delete %s; run: %s" % (old, cache_prune.sudo_line(old)) in out
    assert "1 stuck" in out
    assert old.is_dir()


def test_missing_store_is_a_noop(tmp_path):
    assert cache_prune.candidates(tmp_path / "none", NOW) == []

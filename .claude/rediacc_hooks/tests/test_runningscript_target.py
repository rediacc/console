"""`runningscript._same_script` and `live_shells`: the resolved-path match that replaced the basename-only scan (reviews 87264541.3 to .5)."""

import os

import pytest

from rediacc_hooks import proc, runningscript


def test_an_unreadable_cwd_still_counts_as_a_match(monkeypatch):
    """A relative argv word whose process directory cannot be read fails safe: the guard refuses rather than guess."""
    monkeypatch.setattr(proc, "cwd", lambda _pid: None)
    assert runningscript._same_script("bash run.sh", "run.sh", "/tmp/elsewhere/run.sh", "/", 1)


def test_a_readable_cwd_that_differs_is_not_a_match(monkeypatch):
    """CONTROL for the case above: the same word with a readable, different directory is another script."""
    monkeypatch.setattr(proc, "cwd", lambda _pid: "/tmp/other")
    assert not runningscript._same_script("bash run.sh", "run.sh", "/tmp/elsewhere/run.sh", "/", 1)


def test_a_tilde_target_matches_the_expanded_argv_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    argv = "bash %s/run.sh" % tmp_path
    assert runningscript._same_script(argv, "run.sh", "~/run.sh", "/", 1)
    assert not runningscript._same_script(argv, "run.sh", "~/other/run.sh", "/", 1)


def test_a_tilde_argv_word_matches_an_absolute_target(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert runningscript._same_script(
        "bash ~/run.sh", "run.sh", os.path.join(str(tmp_path), "run.sh"), "/", 1
    )


def test_live_shells_requires_a_target():
    with pytest.raises(TypeError):
        runningscript.live_shells("x", 2)

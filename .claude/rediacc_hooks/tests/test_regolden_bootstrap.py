"""regolden.py's bootstrap message (finding b0d7fcf0.3): a venv that exists but cannot import pytest is reported as incomplete, never as missing."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import venv

from rediacc_hooks.tests import goldenio

SCRIPT = pathlib.Path(__file__).resolve().parent / "regolden.py"


def test_a_present_but_incomplete_venv_is_not_called_missing(tmp_path):
    root = tmp_path / "root"
    script_dir = root / "a" / "b" / "c"
    script_dir.mkdir(parents=True)
    shutil.copy(SCRIPT, script_dir / "regolden.py")
    env_dir = root / ".ci" / "cache" / "toolchain" / "uv-tools" / "pytest"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(env_dir)
    got = subprocess.run(
        [str(env_dir / "bin" / "python"), str(script_dir / "regolden.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert got.returncode != 0, got.stdout
    assert "incomplete" in got.stderr, got.stderr
    assert "is missing" not in got.stderr, got.stderr


def test_control_a_tree_without_the_venv_is_called_missing(tmp_path):
    root = tmp_path / "root"
    script_dir = root / "a" / "b" / "c"
    script_dir.mkdir(parents=True)
    shutil.copy(SCRIPT, script_dir / "regolden.py")
    got = subprocess.run(
        [sys.executable, "-S", str(script_dir / "regolden.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert got.returncode != 0, got.stdout
    assert "is missing" in got.stderr, got.stderr


# ---- queued item #c2a39bea: a recording is independent of TMPDIR, and the summary counts every rewritten line ----

# The two guards whose fixture world lives under `tempfile.gettempdir()` and whose goldens moved with TMPDIR, and the two whose "running" cases quote a live PID (`GOLDEN_UNSTABLE_ENVS`) and were rewritten on every regolden although the differential never compares them.
TMPDIR_STEMS = (
    "block_plan_without_tasks",
    "block_roundlog_write",
    "block_bash_write_to_running_script",
    "block_edit_of_running_script",
)


def _regolden(stem, tmpdir, out_dir):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env["TMPDIR"] = str(tmpdir)
    return subprocess.run(
        [sys.executable, str(SCRIPT), stem, "--reason", "tmpdir probe", "--out-dir", str(out_dir)],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        env=env,
    )


def test_the_fixture_world_goldens_are_byte_identical_under_two_tmpdirs(tmp_path):
    """Each of `TMPDIR_STEMS` records the SAME golden bytes under two different TMPDIRs, and those bytes are the committed golden's. Before the fold, a second TMPDIR moved every key whose payload names the world; before the carry, a live PID moved the running-script records on every run."""
    outs = {}
    # One foreign TMPDIR against the committed golden, which the default TMPDIR recorded, is already two TMPDIRs; a second foreign recording only doubled the cost (review a8945e6f.2).
    for name in ("a",):
        tmpdir = tmp_path / ("tmp-" + name)
        tmpdir.mkdir()
        outs[name] = tmp_path / ("out-" + name)
        for stem in TMPDIR_STEMS:
            got = _regolden(stem, tmpdir, outs[name])
            assert got.returncode == 0, got.stderr[-2000:]
            assert "(0 changed, 0 line(s) rewritten," in got.stdout, got.stdout
    for stem in TMPDIR_STEMS:
        a = (outs["a"] / ("%s.jsonl" % stem)).read_bytes()
        assert a == goldenio.golden_path(stem).read_bytes(), stem


def test_the_fold_moves_only_the_fixture_world_prefix():
    """Control first: under the default temp root the fold is the identity; under another root only `<root>/rediacc-guard-` is respelled."""
    text = "/tmp/rediacc-guard-plans/agent/x.md and /srv/t/rediacc-guard-plans/agent/x.md and /srv/t/other"
    assert goldenio.fold_temp_worlds(text, "/tmp") == text
    assert goldenio.fold_temp_worlds(text, "/srv/t") == (
        "/tmp/rediacc-guard-plans/agent/x.md and /tmp/rediacc-guard-plans/agent/x.md and /srv/t/other"
    )
    # A path that only ENDS in the root's spelling is another path, not the world (review a8945e6f.1).
    assert goldenio.fold_temp_worlds("/home/u/t/rediacc-guard-x and /t/rediacc-guard-x", "/t") == (
        "/home/u/t/rediacc-guard-x and /tmp/rediacc-guard-x"
    )


def test_every_rewritten_line_is_counted():
    """A moved key is one line out and one in (counted once); an added and a dropped record count too; identical text counts zero."""
    old = "h\ns\n{a}\n{b}\n{c}\n"
    assert goldenio.rewritten_lines(old, old) == 0
    assert goldenio.rewritten_lines(old, "h\ns\n{a}\n{B}\n{c}\n") == 1
    assert goldenio.rewritten_lines(old, "h\ns\n{a}\n{c}\n") == 1
    assert goldenio.rewritten_lines(old, "h\ns\n{a}\n{b}\n{c}\n{d}\n") == 1
    assert goldenio.rewritten_lines("", old) == 5

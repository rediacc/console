"""regolden.py's bootstrap message (finding b0d7fcf0.3): a venv that exists but cannot import pytest is reported as incomplete, never as missing."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import venv

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

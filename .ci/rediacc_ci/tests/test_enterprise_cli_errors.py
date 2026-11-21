"""The enterprise CLI turns an expected package error into one stderr line and rc 1; an unexpected exception keeps its traceback."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.enterprise import cli, control_db


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != cli.CF_API_ENV}
    env["PYTHONPATH"] = str(pathlib.Path(paths.__file__).resolve().parent.parent)
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.enterprise.cli", *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )


def test_list_bench_without_the_token_is_one_line_not_a_traceback():
    done = _run("list", "--bench")
    assert done.returncode != 0
    assert "Traceback" not in done.stderr
    assert cli.CF_API_ENV in done.stderr
    assert "bws_env exec --profile" in done.stderr


def test_main_turns_a_control_db_error_into_rc_1(monkeypatch, capsys):
    def boom(*_a: object, **_k: object) -> int:
        raise control_db.ControlDbError("%s is not set" % cli.CF_API_ENV)

    monkeypatch.setattr(cli, "lifecycle_main", boom)
    assert cli.main(["list"]) == 1
    err = capsys.readouterr().err
    assert cli.CF_API_ENV in err
    assert "Traceback" not in err
    assert err.count("\n") == 1


def test_an_unexpected_exception_keeps_its_traceback(monkeypatch):
    def boom(*_a: object, **_k: object) -> int:
        raise KeyError("unexpected")

    monkeypatch.setattr(cli, "lifecycle_main", boom)
    with pytest.raises(KeyError):
        cli.main(["list"])

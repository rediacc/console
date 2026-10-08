"""regolden's re-exec under the interpreter that owns pytest (review findings b0d7fcf0.1 and b0d7fcf0.2)."""

from __future__ import annotations

import subprocess

from rediacc_ci.tests import regolden


def _exe(path, text="#!/bin/sh\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _world(tmp_path, monkeypatch):
    monkeypatch.setattr(regolden, "ROOT", tmp_path)
    calls = []

    def fake_run(argv, **_kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(regolden.subprocess, "run", fake_run)
    return calls


def test_an_explicit_pytest_bin_wins_over_the_tool_venv(tmp_path, monkeypatch):
    calls = _world(tmp_path, monkeypatch)
    _exe(tmp_path / ".ci/cache/toolchain/uv-tools/pytest/bin/python")
    own = _exe(tmp_path / "elsewhere/python3")
    override = _exe(tmp_path / "elsewhere/pytest", "#!%s\n" % own)
    monkeypatch.setenv("PYTEST_BIN", str(override))
    assert regolden._reexec_under_pytest() == 0
    assert calls[0][0] == str(own)


def test_without_an_override_the_tool_venv_is_used(tmp_path, monkeypatch):
    calls = _world(tmp_path, monkeypatch)
    venv = _exe(tmp_path / ".ci/cache/toolchain/uv-tools/pytest/bin/python")
    monkeypatch.delenv("PYTEST_BIN", raising=False)
    assert regolden._reexec_under_pytest() == 0
    assert calls[0][0] == str(venv)


def test_a_missing_interpreter_names_every_path_it_looked_at(tmp_path, monkeypatch, capsys):
    calls = _world(tmp_path, monkeypatch)
    monkeypatch.delenv("PYTEST_BIN", raising=False)
    _exe(tmp_path / ".ci/cache/toolchain/uv-tools/bin/pytest", "#!/usr/bin/env bash\n")
    assert regolden._reexec_under_pytest() == 77
    assert calls == []
    err = capsys.readouterr().err
    assert "uv-tools/pytest/bin/python" in err, err
    assert "uv-tools/bin/pytest" in err, err


def test_an_override_that_names_no_python_is_refused_not_replaced(tmp_path, monkeypatch, capsys):
    calls = _world(tmp_path, monkeypatch)
    _exe(tmp_path / ".ci/cache/toolchain/uv-tools/pytest/bin/python")
    override = _exe(tmp_path / "elsewhere/pytest", "#!/usr/bin/env bash\n")
    monkeypatch.setenv("PYTEST_BIN", str(override))
    assert regolden._reexec_under_pytest() == 77
    assert calls == []
    assert "PYTEST_BIN" in capsys.readouterr().err

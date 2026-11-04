"""`lease_pytest.py`: the pytest wrapper found from a lease-shaped tree without a clone verb in the command."""

from __future__ import annotations

import stat

from rediacc_ci.dev import lease_pytest as lp


def _fake_wrapper(root, body='#!/bin/sh\necho ran "$@"\n'):
    path = root / lp.PYTEST_REL
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_find_pytest_prefers_this_tree(tmp_path):
    wrapper = _fake_wrapper(tmp_path)
    assert lp.find_pytest(tmp_path) == wrapper


def test_find_pytest_none_when_absent(tmp_path):
    assert lp.find_pytest(tmp_path) is None


def test_find_pytest_skips_a_non_executable_file(tmp_path):
    wrapper = _fake_wrapper(tmp_path)
    wrapper.chmod(0o644)
    assert lp.find_pytest(tmp_path) is None


def test_run_pytest_passes_arguments_and_status(tmp_path, capfd):
    _fake_wrapper(tmp_path, '#!/bin/sh\necho got "$@"\nexit 3\n')
    assert lp.run(["pytest", "-q", "x"], tmp_path) == 3
    assert "got -q x" in capfd.readouterr().out


def test_run_pytest_missing_is_a_named_failure(tmp_path, capsys):
    assert lp.run(["pytest"], tmp_path) == 1
    assert "no .ci/cache/toolchain/uv-tools/bin/pytest" in capsys.readouterr().err


def test_run_without_a_verb_is_usage(tmp_path, capsys):
    assert lp.run([], tmp_path) == 2
    assert "Usage" in capsys.readouterr().err

"""A missing program answers 127 in `_run` and `_capture`, as the shell twin does, instead of raising.

`ensure_docker_installed` probes `docker version` first; on a host without docker that probe raised FileNotFoundError and `./run.sh setup` crashed before reaching its install branch (native Ubuntu, 2026-11-25).
"""

import pytest

from rediacc_ci.core import local_common as lc

MISSING = "rediacc-no-such-program-7f3a"


def test_run_answers_127_for_a_missing_program(capsys):
    assert lc._run([MISSING, "--version"]) == 127
    assert f"{MISSING}: command not found" in capsys.readouterr().err


def test_run_stays_quiet_when_asked(capsys):
    assert lc._run([MISSING], quiet_err=True) == 127
    assert capsys.readouterr().err == ""


def test_capture_answers_127_with_empty_output():
    proc = lc._capture([MISSING], quiet_err=True)
    assert proc.returncode == 127
    assert proc.stdout == ""


def test_control_a_present_program_keeps_its_status():
    assert lc._run(["true"]) == 0
    assert lc._run(["false"]) == 1
    assert lc._capture(["echo", "x"]).stdout == "x\n"


def test_docker_probe_reaches_the_install_branch_without_docker(monkeypatch):
    calls = []
    monkeypatch.setattr(lc.shutil, "which", lambda _name: None)
    real_run = lc._run

    def fake_run(argv, **kwargs):
        calls.append(argv[:2])
        if argv[0] == "docker":
            return real_run([MISSING, *argv[1:]], **kwargs)
        return 1

    monkeypatch.setattr(lc, "_run", fake_run)
    try:
        lc.ensure_docker_installed({})
    except SystemExit:
        pass
    except FileNotFoundError as exc:  # the crash this test pins
        raise AssertionError(f"ensure_docker_installed crashed: {exc}") from exc
    assert ["docker", "version"] in calls


def test_a_missing_cwd_raises_instead_of_reporting_the_program_missing(tmp_path, capsys):
    """Review 5fb9ea9e.1 and .2: the program exists, the directory does not, and "command not found" would hide that."""
    gone = str(tmp_path / "no-such-dir")
    with pytest.raises(FileNotFoundError):
        lc._run(["true"], cwd=gone)
    with pytest.raises(FileNotFoundError):
        lc._capture(["true"], cwd=gone)
    assert "command not found" not in capsys.readouterr().err
    # CONTROL: a real cwd with a missing program still answers 127.
    assert lc._run([MISSING], cwd=str(tmp_path), quiet_err=True) == 127

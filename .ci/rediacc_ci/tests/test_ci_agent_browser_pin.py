"""`rediacc_ci.ci.agent_browser_pin`, driven through `main` and as a real subprocess.

Review 741eae84 named three holes in the workflow bash this module replaced: the compare had no test, two empty values compared equal, and a missing ARG line aborted with no message. Each has a case below, and the empty/empty one asserts the refusal rather than a pass.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci.ci import agent_browser_pin as pin

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _df(tmp_path: pathlib.Path, body: str) -> str:
    path = tmp_path / "Dockerfile"
    path.write_text(body, encoding="utf-8")
    return str(path)


def _read(tmp_path, value_line: str, capsys) -> tuple[int, str, str]:
    rc = pin.main(["read", "--dockerfile", _df(tmp_path, "FROM x\n" + value_line + "\nRUN y\n")])
    out = capsys.readouterr()
    return rc, out.out, out.err


@pytest.mark.parametrize(
    ("line", "want"),
    [
        ("ARG AGENT_BROWSER_VERSION=0.39.4", "0.39.4"),
        ('ARG AGENT_BROWSER_VERSION="0.39.4"', "0.39.4"),
        ("ARG AGENT_BROWSER_VERSION='0.39.4'", "0.39.4"),
        ("ARG AGENT_BROWSER_VERSION=0.39.4   \t", "0.39.4"),
        ("ARG AGENT_BROWSER_VERSION=0.40.0-beta.1", "0.40.0-beta.1"),
        ("ARG AGENT_BROWSER_VERSION=1.0.0+b.1", "1.0.0+b.1"),
    ],
)
def test_read_accepts(tmp_path, capsys, line, want):
    rc, out, err = _read(tmp_path, line, capsys)
    assert (rc, out, err) == (0, want + "\n", "")


def test_read_missing_arg_line_is_loud(tmp_path, capsys):
    rc, out, err = _read(tmp_path, "ARG OTHER=1", capsys)
    assert rc == 1
    assert out == ""
    assert "AGENT_BROWSER_VERSION" in err
    assert "no `ARG" in err


@pytest.mark.parametrize(
    "line",
    ["ARG AGENT_BROWSER_VERSION=", 'ARG AGENT_BROWSER_VERSION=""', "ARG AGENT_BROWSER_VERSION=  "],
)
def test_read_empty_value_is_loud(tmp_path, capsys, line):
    rc, out, err = _read(tmp_path, line, capsys)
    assert rc == 1
    assert out == ""
    assert "empty value" in err


def test_read_unreadable_dockerfile_is_loud(tmp_path, capsys):
    rc = pin.main(["read", "--dockerfile", str(tmp_path / "nope")])
    assert rc == 1
    assert "cannot read" in capsys.readouterr().err


def _verify(tmp_path, arg_line: str, version_output: str, capsys) -> tuple[int, str, str]:
    rc = pin.main(
        [
            "verify",
            "--dockerfile",
            _df(tmp_path, arg_line + "\n"),
            "--version-output",
            version_output,
        ]
    )
    out = capsys.readouterr()
    return rc, out.out, out.err


def test_verify_match_takes_last_token(tmp_path, capsys):
    rc, _, err = _verify(
        tmp_path, "ARG AGENT_BROWSER_VERSION=0.39.4", "agent-browser 0.39.4\n", capsys
    )
    assert rc == 0
    assert err == ""


def test_verify_bare_version_output_matches(tmp_path, capsys):
    assert _verify(tmp_path, "ARG AGENT_BROWSER_VERSION=0.39.4", "0.39.4", capsys)[0] == 0


def test_verify_mismatch_names_both(tmp_path, capsys):
    rc, _, err = _verify(
        tmp_path, "ARG AGENT_BROWSER_VERSION=0.39.4", "agent-browser 0.39.2", capsys
    )
    assert rc == 1
    assert "0.39.2" in err
    assert "0.39.4" in err


def test_verify_is_exact_not_prefix(tmp_path, capsys):
    rc, _, _ = _verify(
        tmp_path, "ARG AGENT_BROWSER_VERSION=0.39.4", "agent-browser 0.39.40", capsys
    )
    assert rc == 1


def test_verify_empty_installed_fails(tmp_path, capsys):
    rc, _, err = _verify(tmp_path, "ARG AGENT_BROWSER_VERSION=0.39.4", "", capsys)
    assert rc == 1
    assert "no version" in err


def test_verify_empty_pin_fails(tmp_path, capsys):
    rc, _, err = _verify(tmp_path, "ARG AGENT_BROWSER_VERSION=", "agent-browser 0.39.4", capsys)
    assert rc == 1
    assert "empty" in err


def test_verify_empty_and_empty_does_not_pass():
    """Review finding .2: both values empty must be a refusal, not equality."""
    with pytest.raises(pin.PinError):
        pin.compare("", "")


def test_verify_missing_arg_line_fails(tmp_path, capsys):
    rc, _, err = _verify(tmp_path, "FROM x", "agent-browser 0.39.4", capsys)
    assert rc == 1
    assert "no `ARG" in err


def test_verify_command_failure_is_loud(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))  # no agent-browser anywhere
    rc = pin.main(["verify", "--dockerfile", _df(tmp_path, "ARG AGENT_BROWSER_VERSION=0.39.4\n")])
    assert rc == 1
    assert "agent-browser --version failed" in capsys.readouterr().err


def test_verify_nonzero_exit_is_loud(tmp_path, capsys, monkeypatch):
    fake = tmp_path / "agent-browser"
    fake.write_text("#!/bin/sh\necho 'agent-browser 0.39.4'\nexit 3\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    rc = pin.main(["verify", "--dockerfile", _df(tmp_path, "ARG AGENT_BROWSER_VERSION=0.39.4\n")])
    assert rc == 1
    assert "rc=3" in capsys.readouterr().err


def test_verify_runs_the_command_when_no_override(tmp_path, monkeypatch):
    fake = tmp_path / "agent-browser"
    fake.write_text("#!/bin/sh\necho 'agent-browser 0.39.4'\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert (
        pin.main(["verify", "--dockerfile", _df(tmp_path, "ARG AGENT_BROWSER_VERSION=0.39.4\n")])
        == 0
    )


def test_default_dockerfile_resolves_against_repo_root_not_cwd(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert pin.main(["read"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == pin.read_pin(ROOT / ".devcontainer" / "Dockerfile")
    assert out


def test_module_entry_point_prints_the_real_pin():
    env = dict(os.environ, PYTHONPATH=str(ROOT / ".ci"))
    done = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.ci.agent_browser_pin", "read"],
        capture_output=True,
        text=True,
        cwd="/",
        env=env,
        check=False,
    )
    assert done.returncode == 0
    assert done.stdout.strip()
    assert done.stderr == ""

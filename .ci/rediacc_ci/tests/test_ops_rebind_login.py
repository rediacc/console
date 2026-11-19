"""rediacc_ci.ops.rebind_login with a fake seed, a frozen clock and a stub rdc: the child gets the right code in its environment only, never on argv or in output, and a missing seed refuses with rc 2."""

from __future__ import annotations

import os
import stat
import subprocess

import pytest

from rediacc_ci.ops import rebind_login, totp

SEED = "JBSWY3DPEHPK3PXP"
CLOCK = 1_700_000_010.0  # the start of a 30 s step


@pytest.fixture
def bound(monkeypatch):
    """The root-login profile already bound, so main does not re-execute under bws."""
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "root-login")
    monkeypatch.setenv(rebind_login.SEED_ENV, SEED)
    monkeypatch.delenv(rebind_login.CODE_ENV, raising=False)


def _freeze(monkeypatch, start: float) -> list[float]:
    clock = [start]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(rebind_login, "_clock", lambda: (lambda: clock[0], sleep))
    return slept


def _stub_rdc(tmp_path, monkeypatch):
    """A stub `rdc.sh` that records its argv and the code it saw, and prints its argv."""
    root = tmp_path / "repo"
    root.mkdir()
    seen = tmp_path / "seen"
    script = root / "rdc.sh"
    script.write_text(
        '#!/bin/sh\nprintf "%%s\\n" "$*" > "%s.argv"\nprintf "%%s" "$%s" > "%s.code"\n'
        'printf "%%s" "$%s" > "%s.seed"\necho "rdc ran: $*"\n'
        % (seen, rebind_login.CODE_ENV, seen, rebind_login.SEED_ENV, seen)
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(rebind_login.paths, "repo_root", lambda: root)
    return seen


def _capturing_runner(sink: list[str]):
    def run(argv, env):
        done = subprocess.run(
            list(argv), env=dict(env), capture_output=True, text=True, check=False
        )
        sink.append(done.stdout + done.stderr)
        print(done.stdout, end="")
        return done.returncode

    return run


def _recording(calls: list[list[str]], rc: int = 0):
    """A runner that records each argv and returns `rc` without running anything."""

    def run(argv, _env):
        calls.append(list(argv))
        return rc

    return run


@pytest.mark.usefixtures("bound")
def test_child_sees_the_code_in_its_environment_only(tmp_path, monkeypatch, capfd):
    _freeze(monkeypatch, CLOCK)
    _stub_rdc(tmp_path, monkeypatch)
    out: list[str] = []
    rc = rebind_login.main(
        ["--", "--config", "eu-remote", "subscription", "status"], run=_capturing_runner(out)
    )
    expected = totp.code(SEED, at=CLOCK)
    assert rc == 0
    assert (tmp_path / "seen.code").read_text() == expected
    argv = (tmp_path / "seen.argv").read_text()
    assert argv.strip() == "--config eu-remote subscription status"
    assert expected not in argv
    assert (tmp_path / "seen.seed").read_text() == ""  # the seed never reaches the child
    captured = capfd.readouterr()
    for text in (captured.out, captured.err, *out):
        assert expected not in text
        assert SEED not in text
    assert "rdc ran: --config eu-remote subscription status" in captured.out


@pytest.mark.usefixtures("bound")
def test_waits_for_the_next_step_near_its_end(tmp_path, monkeypatch):
    start = CLOCK + 27  # 3 s left
    slept = _freeze(monkeypatch, start)
    _stub_rdc(tmp_path, monkeypatch)
    rc = rebind_login.main(["--", "subscription", "status"], run=_capturing_runner([]))
    assert rc == 0
    assert slept
    assert slept[0] > 3
    assert (tmp_path / "seen.code").read_text() == totp.code(SEED, at=start + slept[0])
    assert (tmp_path / "seen.code").read_text() != totp.code(SEED, at=start)


@pytest.mark.usefixtures("bound")
def test_child_exit_status_is_returned(tmp_path, monkeypatch):
    _freeze(monkeypatch, CLOCK)
    _stub_rdc(tmp_path, monkeypatch)
    assert rebind_login.main(["--", "x"], run=_recording([], rc=7)) == 7


@pytest.mark.usefixtures("bound")
def test_missing_seed_refuses_with_rc_2_before_running(monkeypatch, capfd):
    monkeypatch.delenv(rebind_login.SEED_ENV)
    calls: list[list[str]] = []
    rc = rebind_login.main(["--", "subscription", "status"], run=_recording(calls))
    assert rc == 2
    assert calls == []
    assert rebind_login.SEED_ENV in capfd.readouterr().err


@pytest.mark.usefixtures("bound")
@pytest.mark.parametrize("value", [rebind_login.PLACEHOLDER, "not base32 !!"])
def test_placeholder_or_bad_seed_refuses_with_rc_2(monkeypatch, value):
    monkeypatch.setenv(rebind_login.SEED_ENV, value)
    calls: list[list[str]] = []
    assert rebind_login.main(["--", "x"], run=_recording(calls)) == 2
    assert calls == []


@pytest.mark.usefixtures("bound")
@pytest.mark.parametrize("argv", [[], ["--"], ["subscription", "status"]])
def test_usage_refuses_with_rc_2(argv):
    assert rebind_login.main(argv, run=_recording([])) == 2


def test_reexecutes_under_the_root_login_profile(monkeypatch):
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    monkeypatch.delenv(rebind_login.SEED_ENV, raising=False)
    calls: list[list[str]] = []
    rc = rebind_login.main(["--", "subscription", "status"], run=_recording(calls))
    assert rc == 0
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[1:6] == ["-m", "rediacc_ci.core.bws_env", "exec", "--profile", "root-login"]
    assert cmd[-5:] == ["-m", "rediacc_ci.ops.rebind_login", "--", "subscription", "status"]


def test_default_runner_gives_the_child_no_stdin(tmp_path):
    """REGRESSION (409d37af.1): a child that inherits a terminal's stdin makes the CLI prompt instead of reading REDIACC_IP_REBIND_CODE. Fd 0 is pointed at a file holding bytes; the child must read none."""
    fed = tmp_path / "fed"
    fed.write_bytes(b"leak")
    got = tmp_path / "got"
    saved = os.dup(0)
    fd = os.open(fed, os.O_RDONLY)
    try:
        os.dup2(fd, 0)
        rc = rebind_login._subprocess_runner(
            ["sh", "-c", 'cat > "$1"', "sh", str(got)], {"PATH": os.environ["PATH"]}
        )
    finally:
        os.dup2(saved, 0)
        os.close(saved)
        os.close(fd)
    assert rc == 0
    assert got.read_bytes() == b""

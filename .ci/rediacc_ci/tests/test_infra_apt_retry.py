"""`rediacc_ci.infra.apt_retry`: bounded retry, last error named, mirror fallback on a stall; plus the ec2 regional rewrite."""

from __future__ import annotations

import subprocess
import typing

import pytest

from rediacc_ci.infra import apt_mirror, apt_retry


class Script:
    """A runner that plays back results: an int is an exit code, an exception is raised."""

    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.calls = 0

    def __call__(self, cmd: list[str], **_kw: typing.Any) -> subprocess.CompletedProcess[str]:
        self.calls += 1
        r = self.results.pop(0)
        if isinstance(r, BaseException):
            raise r
        return subprocess.CompletedProcess(cmd, typing.cast("int", r))


def go(script: Script, fb: list[int], **kw: typing.Any) -> apt_retry.Outcome:
    return apt_retry.run_with_retry(
        ["apt-get", "install", "x"],
        runner=script,
        sleep=lambda _s: None,
        fallback=lambda: fb.append(1),
        **kw,
    )


def test_first_try_success_is_silent_control(capsys: pytest.CaptureFixture[str]) -> None:
    fb: list[int] = []
    out = go(Script(0), fb)
    assert (out.attempts, out.fell_back, fb) == (1, False, [])
    assert capsys.readouterr().out == ""


def test_a_failed_fallback_is_not_reported_as_used() -> None:
    t = subprocess.TimeoutExpired("apt-get", 1)
    out = apt_retry.run_with_retry(
        ["apt-get", "install", "x"],
        runner=Script(t, t, 0),
        sleep=lambda _s: None,
        fallback=lambda: False,
    )
    assert (out.attempts, out.fell_back) == (3, False)


def test_retry_then_success() -> None:
    fb: list[int] = []
    s = Script(100, 0)
    out = go(s, fb)
    assert (out.attempts, s.calls, fb) == (2, 2, [])


def test_all_attempts_fail_names_the_last_error() -> None:
    s = Script(100, 101, 102)
    with pytest.raises(apt_retry.AptRetryError, match=r"all 3 attempts; last error: exited 102"):
        go(s, [])
    assert s.calls == 3


def test_stall_triggers_the_fallback_before_the_final_attempt_only() -> None:
    fb: list[int] = []
    t = subprocess.TimeoutExpired("apt-get", 1)
    s = Script(t, t, 0)
    out = go(s, fb)
    assert (out.attempts, out.fell_back, fb) == (3, True, [1])


def test_plain_failures_do_not_trigger_the_fallback() -> None:
    fb: list[int] = []
    with pytest.raises(apt_retry.AptRetryError):
        go(Script(1, 1, 1), fb)
    assert fb == []


def test_every_attempt_stalling_fails_with_timeout_named() -> None:
    fb: list[int] = []
    t = subprocess.TimeoutExpired("apt-get", 1)
    with pytest.raises(apt_retry.AptRetryError, match="timed out after"):
        go(Script(t, t, t), fb, timeout=1)
    assert fb == [1]


def test_cli_exit_codes() -> None:
    assert apt_retry.main(["--attempts", "1", "--", "true"]) == 0
    assert apt_retry.main(["--attempts", "2", "--backoff", "0", "--", "false"]) == 1
    assert apt_retry.main([]) == 2


def test_ec2_regional_mirror_is_rewritten_to_the_global_archive() -> None:
    arch = apt_mirror.GLOBAL_HOST
    text = "URIs: http://us-east-2.ec2.archive.ubuntu.com/ubuntu/\n"
    out = apt_mirror.rewrite_text(text)
    assert "ec2" not in out
    assert f"URIs: http://{arch}/ubuntu/" in out
    # control: the security host is untouched
    keep = "deb http://security.ubuntu.com/ubuntu noble-security main\n"
    assert apt_mirror.rewrite_text(keep) == keep


def test_retries_dropin_written_once_on_hosted_only(tmp_path: typing.Any) -> None:
    hosted = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"}
    assert apt_mirror.ensure_retries(tmp_path, {}) is False
    assert not (tmp_path / apt_mirror.RETRIES_FILE).exists()
    assert apt_mirror.ensure_retries(tmp_path, hosted) is True
    assert apt_mirror.ensure_retries(tmp_path, hosted) is False
    assert "Acquire::Retries" in (tmp_path / apt_mirror.RETRIES_FILE).read_text()

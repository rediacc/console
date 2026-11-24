"""`rediacc_ci.setup.aws_cli`: the pin step of `.github/actions/setup-aws`, moved out of the action's YAML by the inline-run cap."""

import subprocess

import pytest

from rediacc_ci.setup import aws_cli


def test_linux_x64_resolves_version_and_its_own_sha() -> None:
    lines = aws_cli.pin_outputs("Linux", "X64")
    assert [ln.split("=", 1)[0] for ln in lines] == ["version", "sha"]
    assert all(ln.split("=", 1)[1] for ln in lines)


def test_each_supported_platform_has_a_distinct_or_shared_pin_key() -> None:
    shas = {key: aws_cli.pin_outputs(*key)[1] for key in aws_cli.SHA_KEYS}
    assert shas[("macOS", "X64")] == shas[("macOS", "ARM64")]
    assert shas[("Linux", "X64")] != shas[("Linux", "ARM64")]


def test_unsupported_platform_is_refused_by_name() -> None:
    with pytest.raises(aws_cli.RefusalError, match="Windows-X64"):
        aws_cli.pin_outputs("Windows", "X64")


def test_main_rejects_an_unknown_verb(capsys: pytest.CaptureFixture[str]) -> None:
    assert aws_cli.main(["frobnicate"]) == 2
    assert "usage" in capsys.readouterr().err


def test_main_turns_a_refusal_into_an_error_annotation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path
) -> None:
    monkeypatch.setenv("RUNNER_OS", "Windows")
    monkeypatch.setenv("RUNNER_ARCH", "X64")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    assert aws_cli.main(["pin"]) == 1
    assert capsys.readouterr().out.startswith("::error::no pinned aws CLI installer")


def _install_env(monkeypatch: pytest.MonkeyPatch, tmp_path, export: str, config: str = ""):
    """Fake the bootstrap calls, point the GitHub files at tmp_path and return the fake binary."""
    binary = tmp_path / "aws"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    def fake_run(argv, **_kw):
        return subprocess.CompletedProcess(argv, 0, stdout=str(binary) + "\n", stderr="")

    monkeypatch.setattr(aws_cli.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("EXPORT_ENV", export)
    if config:
        monkeypatch.setenv("AWS_CONFIG_FILE", config)
    else:
        monkeypatch.delenv("AWS_CONFIG_FILE", raising=False)
    return binary


def test_install_without_export_env_only_writes_the_output(monkeypatch, tmp_path) -> None:
    binary = _install_env(monkeypatch, tmp_path, "false")
    aws_cli.run_install()
    assert (tmp_path / "out").read_text(encoding="utf-8") == "aws-bin=%s\n" % binary
    assert not (tmp_path / "env").exists()


def test_install_with_export_env_writes_the_classic_config(monkeypatch, tmp_path) -> None:
    binary = _install_env(monkeypatch, tmp_path, "true")
    aws_cli.run_install()
    env = (tmp_path / "env").read_text(encoding="utf-8")
    assert "AWS_BIN=%s\n" % binary in env
    assert "AWS_CONFIG_FILE=%s\n" % (tmp_path / "aws-cli.cfg") in env
    assert (tmp_path / "aws-cli.cfg").read_text(encoding="utf-8") == aws_cli.CLASSIC_CFG


def test_install_keeps_a_config_the_job_already_names(monkeypatch, tmp_path, capsys) -> None:
    _install_env(monkeypatch, tmp_path, "true", config="/etc/own.cfg")
    aws_cli.run_install()
    env = (tmp_path / "env").read_text(encoding="utf-8")
    assert "AWS_CONFIG_FILE" not in env
    assert not (tmp_path / "aws-cli.cfg").exists()
    assert "kept as is" in capsys.readouterr().out


def test_install_refuses_a_binary_that_is_not_executable(monkeypatch, tmp_path) -> None:
    binary = _install_env(monkeypatch, tmp_path, "true")
    binary.chmod(0o644)
    with pytest.raises(aws_cli.RefusalError, match="not executable"):
        aws_cli.run_install()


@pytest.mark.parametrize("failing", ["install", "which"])
def test_a_failed_bootstrap_is_an_error_annotation_and_exit_1(
    monkeypatch, tmp_path, capsys, failing
) -> None:
    """7d0ce757.3: a failing bootstrap.sh is a refusal, not a CalledProcessError traceback."""
    _install_env(monkeypatch, tmp_path, "false")

    def fake_run(argv, **_kw):
        return subprocess.CompletedProcess(argv, 3 if failing in argv else 0, stdout="", stderr="")

    monkeypatch.setattr(aws_cli.subprocess, "run", fake_run)
    assert aws_cli.main(["install"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("::error::")
    assert "exited 3" in out

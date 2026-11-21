"""`rediacc_ci.setup.aws_cli`: the pin step of `.github/actions/setup-aws`, moved out of the action's YAML by the inline-run cap."""

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

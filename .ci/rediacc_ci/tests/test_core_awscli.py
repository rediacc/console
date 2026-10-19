"""`rediacc_ci.core.awscli`: the rung order, the refusals, the pinned cache, and the finding that started it.

Every `aws` here is a fake script that prints a version line; nothing reaches a network. The cache rung is pointed at a scratch file through `awscli.cache_binary`, so the repo's own `.ci/cache` install (when one exists) never answers a case.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci.core import awscli, common
from rediacc_ci.ops import scrub_sentinel

PIN = awscli.pin()
FAKE = "#!/bin/sh\necho 'aws-cli/{version} Python/3.13.7 Linux/6.8.0 exe/x86_64.ubuntu.24'\n"


def _fake(path: pathlib.Path, version: str = PIN) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FAKE.format(version=version), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, pathlib.Path]:
    """An empty PATH directory, a cache path that does not exist yet, and no AWS_BIN."""
    empty = tmp_path / "path"
    empty.mkdir()
    cache = tmp_path / "cache" / PIN / "bin" / "aws"
    monkeypatch.setattr(awscli, "cache_binary", lambda _version=None, _root=None: cache)
    monkeypatch.delenv(awscli.ENV_KEY, raising=False)
    monkeypatch.setenv("PATH", str(empty))
    awscli._PROBED.clear()
    return {"path": empty, "cache": cache, "tmp": tmp_path}


def test_aws_bin_beats_path_and_cache(world: dict[str, pathlib.Path], monkeypatch) -> None:
    explicit = _fake(world["tmp"] / "explicit" / "aws")
    _fake(world["path"] / "aws")
    _fake(world["cache"])
    monkeypatch.setenv(awscli.ENV_KEY, str(explicit))
    assert awscli.resolve() == str(explicit)


def test_path_beats_cache_and_is_not_probed(world: dict[str, pathlib.Path]) -> None:
    """A PATH aws OFF the pin still answers: the PATH rung takes the binary as found, because the recording fakes on PATH must not gain a --version call."""
    on_path = _fake(world["path"] / "aws", version="1.0.0")
    _fake(world["cache"])
    assert awscli.resolve() == str(on_path)


def test_the_cache_answers_at_the_pin(world: dict[str, pathlib.Path]) -> None:
    cached = _fake(world["cache"])
    assert awscli.resolve() == str(cached)


def test_an_off_pin_cache_binary_is_rejected(world: dict[str, pathlib.Path]) -> None:
    _fake(world["cache"], version="2.0.0")
    assert awscli.resolve() is None
    with pytest.raises(awscli.AwsCliMissingError):
        awscli.require()


@pytest.mark.usefixtures("world")
def test_nothing_resolves_and_the_refusal_is_the_one_callers_already_print() -> None:
    """The message stays byte-identical to `common.require_cmd("aws")`, which the twins' goldens pin; the exception is a RefusalError, which every caller already catches."""
    assert awscli.resolve() is None
    with pytest.raises(common.RefusalError) as caught:
        awscli.require()
    assert str(caught.value) == "Required command 'aws' is not available"
    assert awscli.INSTALL_HINT in caught.value.hint


def test_an_aws_bin_that_is_not_executable_refuses_rather_than_falling_through(
    world: dict[str, pathlib.Path], monkeypatch
) -> None:
    _fake(world["path"] / "aws")
    monkeypatch.setenv(awscli.ENV_KEY, str(world["tmp"] / "absent"))
    with pytest.raises(awscli.AwsCliMissingError):
        awscli.resolve()
    plain = world["tmp"] / "not-executable"
    plain.write_text("x", encoding="utf-8")
    monkeypatch.setenv(awscli.ENV_KEY, str(plain))
    with pytest.raises(awscli.AwsCliMissingError):
        awscli.resolve()


def test_argv_swaps_only_an_aws_head(world: dict[str, pathlib.Path]) -> None:
    cached = _fake(world["cache"])
    assert awscli.argv([awscli.AWS, "s3", "ls"]) == [str(cached), "s3", "ls"]
    assert awscli.argv(["gh", "api", "x"]) == ["gh", "api", "x"]
    assert awscli.argv([]) == []


@pytest.mark.usefixtures("world")
def test_argv_is_unchanged_when_nothing_resolves() -> None:
    """The exec then fails the way it did before the resolver, which the not-found arms of the callers handle."""
    assert awscli.argv([awscli.AWS, "s3", "ls"]) == [awscli.AWS, "s3", "ls"]


def test_run_execs_the_resolved_binary(world: dict[str, pathlib.Path]) -> None:
    _fake(world["cache"])
    proc = awscli.run([awscli.AWS, "--version"], capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.stdout.startswith("aws-cli/%s " % PIN)


def test_run_resolves_through_the_env_it_is_given(world: dict[str, pathlib.Path]) -> None:
    """A caller passing `env=` (the sync_media tools) gets that env's PATH, not this process's."""
    elsewhere = world["tmp"] / "elsewhere"
    _fake(elsewhere / "aws", version="9.9.9")
    env = {**os.environ, "PATH": str(elsewhere)}
    proc = awscli.run([awscli.AWS, "--version"], capture_output=True, text=True, env=env)
    assert proc.stdout.startswith("aws-cli/9.9.9 ")


def test_probe_version_reads_the_aws_cli_line(world: dict[str, pathlib.Path]) -> None:
    assert awscli.probe_version(str(_fake(world["cache"]))) == PIN
    assert awscli.probe_version(str(world["tmp"] / "absent")) is None


def test_the_findings_repro_passes_preflight(
    world: dict[str, pathlib.Path], monkeypatch, capsys
) -> None:
    """The 2026-10-19 finding: `scrub_sentinel v1.3.2` on a host with no aws on PATH refused with "Required command 'aws' is not available". With the pinned install in the cache it passes the aws check and stops at the first missing credential instead."""
    for name in (
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    assert scrub_sentinel.main(["v1.3.2"]) == 1
    assert "Required command 'aws' is not available" in capsys.readouterr().err
    _fake(world["cache"])
    assert scrub_sentinel.main(["v1.3.2"]) == 1
    err = capsys.readouterr().err
    assert "Required command 'aws'" not in err
    assert "CLOUDFLARE_R2_ACCESS_KEY_ID" in err


def test_the_cli_names_the_binary_and_the_pin(world: dict[str, pathlib.Path]) -> None:
    root = pathlib.Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(root / ".ci"), "PATH": str(world["path"])}
    _fake(world["path"] / "aws")
    which = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.awscli", "which"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert which.returncode == 0, which.stderr
    assert which.stdout.strip() == str(world["path"] / "aws")
    pin = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.awscli", "pin"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert pin.returncode == 0, pin.stderr
    assert pin.stdout.split()[0] == PIN
    assert pin.stdout.split()[1].endswith("/.ci/cache/toolchain/aws-cli/%s/bin/aws" % PIN)


def test_a_reinstall_at_the_same_mtime_is_probed_again(tmp_path, monkeypatch) -> None:
    """The probe cache keys on inode and size as well as mtime, so a binary replaced inside one mtime tick is probed afresh (review 092a91ac.2)."""
    calls: list[str] = []

    def probe(binary: str, **_kw: object) -> str:
        calls.append(binary)
        return "2.0.0"

    monkeypatch.setattr(awscli, "probe_version", probe)
    binary = tmp_path / "aws"
    binary.write_text("one")
    stamp = binary.stat().st_mtime_ns
    assert awscli._cached_version(binary) == "2.0.0"
    assert awscli._cached_version(binary) == "2.0.0"
    assert len(calls) == 1
    fresh = tmp_path / "aws.new"
    fresh.write_text("a longer second build")
    os.utime(fresh, ns=(stamp, stamp))
    os.replace(fresh, binary)
    assert binary.stat().st_mtime_ns == stamp
    assert awscli._cached_version(binary) == "2.0.0"
    assert len(calls) == 2

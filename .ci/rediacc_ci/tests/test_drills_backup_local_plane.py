"""`rediacc_ci.drills.backup_local_plane`, the port of `programs/backup-storage/start-local-plane.sh`.

THE BASH WAS RETIRED WITH THIS FILE (PLAN-retire-bash-oracles B5, W10). The real run needs docker, a RustFS and Bitwarden, so what is pinned is the wiring it exists to get right: the production bucket name is refused, the gateway is started under the `backup-plane` profile in `private/account`, the bucket wiring is forced while the committed defaults only fill what the shell lacks, and the one deliberate delta from the bash (Rule T) -- a bucket creation that fails for a reason other than "already exists" is reported.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths, well_known
from rediacc_ci.core import bws_env
from rediacc_ci.drills import backup_local_plane as plane

if TYPE_CHECKING:
    import pathlib

DOCKER_STUB = """#!/bin/sh
echo "$@" >> "$DOCKER_LOG"
echo "env AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-} AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}" >> "$DOCKER_LOG"
echo "$STUB_STDERR" >&2
exit "${STUB_RC:-0}"
"""


@pytest.fixture
def docker(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "docker"
    stub.write_text(DOCKER_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", "%s:/usr/local/bin:/usr/bin:/bin" % bindir)
    monkeypatch.setenv("DOCKER_LOG", str(tmp_path / "docker.log"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logdir"))
    return tmp_path / "docker.log"


def test_knobs_default_to_the_documented_values() -> None:
    k = plane.knobs({})
    assert k["BRIDGE_HOST"] == "192.168.111.254"
    assert k["GATEWAY_PORT"] == str(well_known.ACCOUNT_DEV_PORT)
    assert k["RUSTFS_PORT"] == "9100"
    assert k["PROBE_BUCKET"] == "rediacc-backups-probe"
    assert plane.knobs({"GATEWAY_PORT": "4999"})["GATEWAY_PORT"] == "4999"


def test_the_production_bucket_name_is_refused(
    docker: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PROBE_BUCKET", "rediacc-backups")
    assert plane.main([]) == 1
    assert (
        "REFUSING bucket 'rediacc-backups': that is the production name." in capsys.readouterr().err
    )
    assert not docker.exists()


def test_the_bucket_command_targets_the_local_rustfs_only() -> None:
    cmd = plane.bucket_command(plane.knobs({}))
    assert cmd[:6] == ["docker", "run", "--rm", "--network", "host", "-e"]
    assert "--bucket" in cmd
    assert cmd[cmd.index("--bucket") + 1] == "rediacc-backups-probe"
    assert cmd[cmd.index("--endpoint-url") + 1] == "http://127.0.0.1:9100"


def test_the_rustfs_keys_reach_docker_through_its_environment_not_argv(
    docker: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worklist #3a8d1f46. `-e NAME` with no value: the keys are on no docker argv, and docker's environment carries them for the container."""
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    k = plane.knobs({**os.environ, "RUSTFS_KEY": "rk-id-0123", "RUSTFS_SECRET": "rk-secret-0123"})
    assert plane.create_bucket(k) is None
    argv, env_line = docker.read_text(encoding="utf-8").splitlines()[:2]
    assert "rk-id-0123" not in argv, argv
    assert "rk-secret-0123" not in argv, argv
    assert "-e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_DEFAULT_REGION=us-east-1" in argv
    assert env_line == "env AWS_ACCESS_KEY_ID=rk-id-0123 AWS_SECRET_ACCESS_KEY=rk-secret-0123"


def test_an_existing_bucket_is_not_a_problem(
    docker: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUB_RC", "254")
    monkeypatch.setenv("STUB_STDERR", "An error occurred (BucketAlreadyOwnedByYou) when calling")
    assert plane.create_bucket(plane.knobs(dict(os.environ))) is None
    assert docker.exists()


@pytest.mark.usefixtures("docker")
def test_a_bucket_failure_is_reported_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule T: the bash sent the whole call to /dev/null with `|| true`."""
    monkeypatch.setenv("STUB_RC", "1")
    monkeypatch.setenv("STUB_STDERR", "Could not connect to the endpoint URL")
    problem = plane.create_bucket(plane.knobs(dict(os.environ)))
    assert problem == "Could not connect to the endpoint URL"


def test_missing_docker_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    problem = plane.create_bucket(plane.knobs(dict(os.environ)))
    assert problem is not None
    assert problem.startswith("cannot run docker")


def test_gateway_environment_forces_the_bucket_wiring_and_lets_the_shell_win_elsewhere() -> None:
    k = plane.knobs({"RUSTFS_PORT": "9101", "PROBE_BUCKET": "my-probe", "BRIDGE_HOST": "10.0.0.9"})
    child = plane.gateway_environment(
        k,
        {
            "ACCOUNT_BACKUP_S3_BUCKET": "stale",
            "PORT": "4999",
            "PATH": "/usr/bin",
        },
    )
    assert child["ACCOUNT_BACKUP_S3_BUCKET"] == "my-probe"
    assert child["ACCOUNT_BACKUP_S3_ENDPOINT"] == "http://10.0.0.9:9101"
    assert child["CONFIG_R2_ENDPOINT"] == "http://127.0.0.1:9101"
    assert child["CONFIG_R2_BUCKET"] == "rediacc-configs"
    assert child["TEST_MODE"] == "true"
    assert child["GATEWAY_PORT"] == k["GATEWAY_PORT"]
    # The committed defaults fill what the shell lacks and never replace what it has.
    assert child["PORT"] == "4999"
    assert child["PATH"] == "/usr/bin"


def test_main_runs_the_gateway_under_the_backup_plane_profile_in_the_account_dir(
    docker: pathlib.Path, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    account = paths.repo_root() / "private" / "account"
    if not account.is_dir():
        pytest.skip("private/account is not checked out")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, "environ", os.environ.copy())
    seen: dict[str, object] = {}

    def fake_exec(argv: list[str]) -> int:
        seen["argv"] = argv
        seen["cwd"] = os.getcwd()
        seen["bucket"] = os.environ.get("ACCOUNT_BACKUP_S3_BUCKET")
        return 0

    monkeypatch.setattr(bws_env, "main", fake_exec)
    for name in ("ACCOUNT_BACKUP_S3_BUCKET", "ACCOUNT_BACKUP_S3_ENDPOINT", "TEST_MODE"):
        os.environ.pop(name, None)
    assert plane.main([]) == 0
    assert seen["argv"] == [
        "exec",
        "--profile",
        "backup-plane",
        "--",
        "npx",
        "--no-install",
        "tsx",
        "src/entry/dev-gateway.ts",
    ]
    assert seen["cwd"] == str(paths.repo_root() / "private" / "account")
    assert seen["bucket"] == "rediacc-backups-probe"
    assert docker.exists()


def test_help_exits_zero_without_starting_anything(
    docker: pathlib.Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plane.bws_env, "main", lambda *_a, **_k: pytest.fail("gateway started"))
    with pytest.raises(SystemExit) as exc:
        plane.main(["--help"])
    assert exc.value.code == 0
    assert "environment variable" in capsys.readouterr().out
    assert not docker.exists()


def test_unknown_argument_is_refused_before_any_side_effect(
    docker: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plane.bws_env, "main", lambda *_a, **_k: pytest.fail("gateway started"))
    with pytest.raises(SystemExit) as exc:
        plane.main(["--bogus"])
    assert exc.value.code == 2
    assert not docker.exists()

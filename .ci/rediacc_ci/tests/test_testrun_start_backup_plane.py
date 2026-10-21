"""`rediacc_ci.testrun.start_backup_plane`: the wiring, with docker, ip, ssh and the account start replaced by seams. The real run needs docker, the VM network and a worker VM."""

from __future__ import annotations

import os
import subprocess

import pytest

from rediacc_ci.testrun import start_backup_plane as plane

K = {
    "RUSTFS_PORT": "9100",
    "RUSTFS_KEY": "kk",
    "RUSTFS_SECRET": "ss",
    "PROBE_BUCKET": "rediacc-backups-probe",
    "BRIDGE_HOST": "x",
    "GATEWAY_PORT": "1",
    "LOG_DIR": "/tmp/x",
}


def done(rc: int, err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, "", err)


def test_account_env_is_spelled_as_the_vm_dials_it() -> None:
    env = plane.account_env(K, "192.168.111.254")
    assert env["ACCOUNT_BACKUP_S3_ENDPOINT"] == "http://192.168.111.254:9100"
    assert env["ACCOUNT_BACKUP_S3_BUCKET"] == "rediacc-backups-probe"
    assert env["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"] == "kk"
    assert env["ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"] == "ss"


def test_parse_defaults_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACCOUNT_API_PORT", raising=False)
    assert plane.parse([]) == {"port": "4900", "worker": "11"}
    assert plane.parse(["--port", "4911", "--worker", "12"]) == {"port": "4911", "worker": "12"}
    with pytest.raises(ValueError, match="Unknown option"):
        plane.parse(["--x"])
    assert plane.main(["--port"]) == 2
    assert plane.main(["--port", "4900; rm -rf /"]) == 2
    assert plane.main(["--worker", "11 x"]) == 2


def test_bucket_failure_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plane.account_lifecycle, "start_rustfs", lambda: None)
    monkeypatch.setattr(plane.account, "rustfs_alive", lambda _port: True)
    monkeypatch.setattr(plane.backup_local_plane, "create_bucket", lambda _k: "denied")
    with pytest.raises(plane.PlaneError, match="denied"):
        plane.start_storage(K)


def test_dead_rustfs_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plane.account_lifecycle, "start_rustfs", lambda: None)
    monkeypatch.setattr(plane.account, "rustfs_alive", lambda _port: False)
    with pytest.raises(plane.PlaneError, match="RustFS does not answer"):
        plane.start_storage(K)


def test_production_bucket_is_refused() -> None:
    with pytest.raises(plane.PlaneError, match="production"):
        plane.start_storage({**K, "PROBE_BUCKET": "rediacc-backups"})


def test_probe_runs_curl_on_the_worker() -> None:
    seen: list[list[str]] = []

    def fake(argv, **_):
        seen.append(argv)
        return done(0)

    plane.probe_from_vm("11", "http://192.168.111.254:4900/health", fake)
    plane.probe_from_vm("11", "http://192.168.111.254:9100/", fake, http_ok=False)
    assert seen[0][-2].endswith("@192.168.111.11")
    assert seen[0][-1] == "curl -fsS --max-time 10 http://192.168.111.254:4900/health"
    assert seen[1][-1] == "curl -sS -o /dev/null --max-time 10 http://192.168.111.254:9100/"


@pytest.mark.parametrize(("rc", "needle"), [(255, "cannot ssh"), (7, "cannot reach")])
def test_probe_failures_are_loud(rc: int, needle: str) -> None:
    with pytest.raises(plane.PlaneError, match=needle):
        plane.probe_from_vm("11", "http://h:1", lambda _argv, **_: done(rc, "boom"))


def test_probe_timeout_is_loud() -> None:
    def fake(argv, **_):
        raise subprocess.TimeoutExpired(argv, 1)

    with pytest.raises(plane.PlaneError, match="did not complete"):
        plane.probe_from_vm("11", "http://h:1", fake)


def drive(monkeypatch: pytest.MonkeyPatch, bridge: str | None, probe_ok: bool = True):
    calls: dict[str, object] = {"stopped": False}
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setattr(plane, "start_storage", lambda _k: None)
    monkeypatch.setattr(plane.wire, "bridge_host", lambda _base: bridge)

    def fake_start(argv):
        calls["argv"] = argv
        return 0

    monkeypatch.setattr(plane.start_account, "main", fake_start)

    def fake_probe(worker, url, *, http_ok=True):
        calls.setdefault("probes", []).append((worker, url, http_ok))
        if not probe_ok:
            raise plane.PlaneError("unreachable")

    monkeypatch.setattr(plane, "probe_from_vm", fake_probe)
    monkeypatch.setattr(plane, "stop_account", lambda: calls.update(stopped=True))
    monkeypatch.setattr(plane, "export_credentials", lambda _k: calls.update(exported=True))
    return calls


def test_run_wires_scopes_advertise_host_and_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = drive(monkeypatch, "192.168.111.254")
    assert plane.run({"port": "4900", "worker": "11"}) == 0
    argv = calls["argv"]
    assert argv[argv.index("--advertise-host") + 1] == "192.168.111.254"
    assert "backup:read" in argv[argv.index("--scopes") + 1].split(",")
    assert calls["probes"] == [
        ("11", "http://192.168.111.254:4900/health", True),
        ("11", "http://192.168.111.254:9100/", False),
    ]
    assert calls["exported"] is True


def test_run_fails_clearly_without_a_bridge(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    calls = drive(monkeypatch, None)
    assert plane.run({"port": "4900", "worker": "11"}) == 1
    assert "argv" not in calls
    assert "VM network is not up" in capsys.readouterr().err


def test_failed_probe_stops_the_account_and_exports_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = drive(monkeypatch, "192.168.111.254", probe_ok=False)
    assert plane.run({"port": "4900", "worker": "11"}) == 1
    assert calls["stopped"] is True
    assert "exported" not in calls


def test_stop_account_kills_the_recorded_listener(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(plane.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    plane.stop_account()
    assert killed == []
    (tmp_path / "account-for-e2e.pid").write_text("4242\n")
    plane.stop_account()
    assert killed == [(4242, plane.signal.SIGTERM)]


def test_credentials_go_to_github_env_masked(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(gh))
    plane.export_credentials(K)
    assert gh.read_text() == "E2E_BACKUP_S3_KEY=kk\nE2E_BACKUP_S3_SECRET=ss\n"


def test_credential_values_are_not_printed_locally(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    plane.export_credentials({**K, "RUSTFS_KEY": "KEYVAL", "RUSTFS_SECRET": "SECVAL"})
    out = capsys.readouterr()
    assert "export E2E_BACKUP_S3_KEY\n" in out.out
    assert "KEYVAL" not in out.out + out.err
    assert "SECVAL" not in out.out + out.err

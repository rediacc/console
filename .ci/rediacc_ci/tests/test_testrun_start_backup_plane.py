"""`rediacc_ci.testrun.start_backup_plane`: the wiring, with docker, ip, ssh and the account start replaced by seams. The real run needs docker, the VM network and a worker VM."""

from __future__ import annotations

import base64
import hashlib
import os
import signal
import subprocess
import sys
import tempfile
from typing import Any

import pytest

from rediacc_ci.testrun import start_backup_plane as plane
from rediacc_ci.well_known import RENET_REPO

K = {
    "RUSTFS_PORT": "9100",
    "RUSTFS_KEY": "kk",
    "RUSTFS_SECRET": "ss",
    "PROBE_BUCKET": "rediacc-backups-probe",
    "BRIDGE_HOST": "x",
    "GATEWAY_PORT": "1",
    "LOG_DIR": "/tmp/x",
}


def done(rc: int, err: str = "", out: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out, err)


def spki(seed: bytes) -> str:
    """A well-formed SPKI ED25519 public key, base64 (the 32 key bytes are arbitrary)."""
    return base64.b64encode(plane.SPKI_ED25519_HEADER + hashlib.sha256(seed).digest()).decode()


def fp(key: str) -> str:
    raw = base64.b64decode(key)[-32:]
    return hashlib.sha256(raw).hexdigest()[:16]


PUB = spki(b"signer")
OTHER = spki(b"baked")
PRIV_SENTINEL = "PRIVATE-KEY-SENTINEL"
OPTS = plane.Options("4900", "11", rebuild_renet=True)


def test_account_env_is_spelled_as_the_vm_dials_it() -> None:
    env = plane.account_env(K, "192.168.111.254")
    assert env["ACCOUNT_BACKUP_S3_ENDPOINT"] == "http://192.168.111.254:9100"
    assert env["ACCOUNT_BACKUP_S3_BUCKET"] == "rediacc-backups-probe"
    assert env["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"] == "kk"
    assert env["ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"] == "ss"


def test_rebuild_defaults_off_under_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert plane.parse([]).rebuild_renet is False
    assert plane.parse(["--rebuild-renet"]).rebuild_renet is True


def test_parse_defaults_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACCOUNT_API_PORT", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert plane.parse([]) == plane.Options("4900", "11", True, [])
    assert plane.parse(["--port", "4911", "--worker", "12"]) == plane.Options("4911", "12", True)
    assert plane.parse(["--no-rebuild-renet"]).rebuild_renet is False
    assert plane.parse(["--verify-renet", "/b1", "--verify-renet", "/b2"]).verify == ["/b1", "/b2"]
    assert plane.main(["--verify-renet"]) == 2
    with pytest.raises(ValueError, match="Unknown option"):
        plane.parse(["--x"])
    assert plane.main(["--port"]) == 2
    assert plane.main(["--port", "4900; rm -rf /"]) == 2
    assert plane.main(["--worker", "11 x"]) == 2
    assert plane.main(["--port", "\u00b2"]) == 2


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


def drive(
    monkeypatch: pytest.MonkeyPatch,
    bridge: str | None,
    probe_ok: bool = True,
    *,
    baked: str | None = None,
) -> dict[str, Any]:
    """`run()` with every outside effect stubbed. `baked` is the key the rebuilt renet reports (default: the generated public half)."""
    calls: dict[str, Any] = {"stopped": False, "keygens": [], "builds": []}
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setattr(plane, "start_storage", lambda _k: None)
    monkeypatch.setattr(plane.wire, "bridge_host", lambda _base: bridge)

    def fake_keygen() -> dict[str, str]:
        calls["keygens"].append(1)
        return {"edPriv": PRIV_SENTINEL, "edPub": PUB, "xPriv": "x", "xPub": "y"}

    monkeypatch.setattr(plane.start_account, "generate_keys", fake_keygen)
    monkeypatch.setattr(plane, "rebuild_renet", calls["builds"].append)
    staged = tempfile.mkdtemp(prefix="staged-")
    for name in ("renet", "renet-linux-amd64"):
        with open(os.path.join(staged, name), "w", encoding="utf-8") as handle:
            handle.write(name)
    monkeypatch.setattr(
        plane,
        "staged_renets",
        lambda: [os.path.join(staged, n) for n in ("renet", "renet-linux-amd64")],
    )
    monkeypatch.setattr(plane, "baked_public_key", lambda _b, *_a: PUB if baked is None else baked)

    def fake_start(argv):
        calls["argv"] = argv
        # A snapshot of the (patched, dict) environment the account start would inherit.
        handed = dict(os.environ)
        calls["env_pair"] = (handed.get(plane.PRIVATE_KEY_ENV), handed.get(plane.PUBLIC_KEY_ENV))
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
    assert plane.run(OPTS) == 0
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
    assert plane.run(OPTS) == 1
    assert "argv" not in calls
    assert "VM network is not up" in capsys.readouterr().err


def test_failed_probe_stops_the_account_and_exports_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = drive(monkeypatch, "192.168.111.254", probe_ok=False)
    assert plane.run(OPTS) == 1
    assert calls["stopped"] is True
    assert "exported" not in calls


def test_stop_account_kills_the_recorded_listener(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    plane.stop_account()
    assert killed == []
    (tmp_path / "account-for-e2e.pid").write_text("4242\n")
    plane.stop_account()
    assert killed == [(4242, signal.SIGTERM)]


def test_credentials_go_to_github_env_masked(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    gh = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(gh))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    plane.export_credentials(K)
    assert gh.read_text() == "E2E_BACKUP_S3_KEY=kk\nE2E_BACKUP_S3_SECRET=ss\n"
    assert capsys.readouterr().out.splitlines() == ["::add-mask::kk", "::add-mask::ss"]


def test_credentials_are_not_masked_or_printed_off_actions(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The control for the test above: the same GITHUB_ENV file, but no Actions runner to consume a mask."""
    gh = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(gh))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    plane.export_credentials({**K, "RUSTFS_KEY": "KEYVAL", "RUSTFS_SECRET": "SECVAL"})
    out = capsys.readouterr()
    assert gh.read_text() == "E2E_BACKUP_S3_KEY=KEYVAL\nE2E_BACKUP_S3_SECRET=SECVAL\n"
    assert "add-mask" not in out.out + out.err
    assert "KEYVAL" not in out.out + out.err
    assert "SECVAL" not in out.out + out.err


def test_credential_values_are_not_printed_locally(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    plane.export_credentials({**K, "RUSTFS_KEY": "KEYVAL", "RUSTFS_SECRET": "SECVAL"})
    out = capsys.readouterr()
    assert "export E2E_BACKUP_S3_KEY\n" in out.out
    assert "KEYVAL" not in out.out + out.err
    assert "SECVAL" not in out.out + out.err


def test_run_generates_one_pair_and_hands_both_halves_to_the_account(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = drive(monkeypatch, "192.168.111.254")
    assert plane.run(OPTS) == 0
    assert calls["keygens"] == [1]
    assert calls["env_pair"] == (PRIV_SENTINEL, PUB)
    out = capsys.readouterr()
    assert PRIV_SENTINEL not in out.out + out.err


def test_local_mode_rebuilds_with_the_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = drive(monkeypatch, "192.168.111.254")
    assert plane.run(OPTS) == 0
    assert calls["builds"] == [PUB]
    assert calls["exported"] is True


def test_ci_mode_does_not_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = drive(monkeypatch, "192.168.111.254")
    assert plane.run(plane.Options("4900", "11", rebuild_renet=False)) == 0
    assert calls["builds"] == []
    assert calls["env_pair"] == (PRIV_SENTINEL, PUB)


def test_a_rebuilt_renet_with_another_key_is_refused_before_the_account_starts(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = drive(monkeypatch, "192.168.111.254", baked=OTHER)
    assert plane.run(OPTS) == 1
    assert "argv" not in calls
    err = capsys.readouterr().err
    assert fp(PUB) in err
    assert fp(OTHER) in err


def test_rebuild_passes_the_public_key_and_withholds_the_private_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs["env"]
        return done(0)

    monkeypatch.setenv("ACCOUNT_ED25519_PRIVATE_KEY", PRIV_SENTINEL)
    plane.rebuild_renet(PUB, fake)
    assert seen["argv"][1:] == ["-m", "rediacc_ci.infra.build_renet"]
    assert seen["env"]["ACCOUNT_ED25519_PUBLIC_KEY"] == PUB
    assert "ACCOUNT_ED25519_PRIVATE_KEY" not in seen["env"]
    assert PRIV_SENTINEL not in " ".join(seen["argv"])
    with pytest.raises(plane.PlaneError, match="exited 2"):
        plane.rebuild_renet(PUB, lambda _argv, **_: done(2))


def buildinfo(key: str | None) -> str:
    ldflag = (
        f" -X github.com/{RENET_REPO}/pkg/license/keys.ProductionPublicKey={key}" if key else ""
    )
    return (
        f"/r/renet: go0.0.0-test\n\tpath\tgithub.com/{RENET_REPO}/cmd/renet\n"
        f'\tbuild\t-ldflags="-s -w -X main.Version=0.0.0-dev{ldflag}"\n'
    )


def test_preflight_accepts_a_matching_key() -> None:
    plane.verify_renet("/r/renet", PUB, lambda _argv, **_: done(0, out=buildinfo(PUB)))


def test_preflight_refuses_a_mismatch_with_both_fingerprints() -> None:
    with pytest.raises(plane.PlaneError) as caught:
        plane.verify_renet("/r/renet", PUB, lambda _argv, **_: done(0, out=buildinfo(OTHER)))
    assert fp(PUB) != fp(OTHER)
    assert fp(PUB) in str(caught.value)
    assert fp(OTHER) in str(caught.value)


def test_preflight_refuses_a_keyless_or_unreadable_binary() -> None:
    with pytest.raises(plane.PlaneError, match="bakes no licence key"):
        plane.verify_renet("/r/renet", PUB, lambda _argv, **_: done(0, out=buildinfo(None)))
    with pytest.raises(plane.PlaneError, match="cannot read the build info"):
        plane.verify_renet("/r/renet", PUB, lambda _argv, **_: done(1, err="not a Go binary"))


def test_fingerprint_matches_renet_for_raw_and_spki_keys() -> None:
    raw = base64.b64encode(base64.b64decode(PUB)[-32:]).decode()
    assert plane.key_fingerprint(PUB) == plane.key_fingerprint(raw) == fp(PUB)
    with pytest.raises(plane.PlaneError):
        plane.key_fingerprint("bm90IGEga2V5")


def test_verify_mode_needs_the_public_key(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("ACCOUNT_ED25519_PUBLIC_KEY", raising=False)
    assert plane.main(["--verify-renet", "/r/renet"]) == 1
    assert "ACCOUNT_ED25519_PUBLIC_KEY is not set" in capsys.readouterr().err


def test_verify_mode_checks_every_binary_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    monkeypatch.setenv("ACCOUNT_ED25519_PUBLIC_KEY", PUB)
    monkeypatch.setattr(plane, "start_storage", lambda _k: pytest.fail("verify mode ran storage"))
    monkeypatch.setattr(plane, "verify_renet", lambda binary, _key: seen.append(binary))
    assert plane.main(["--verify-renet", "/a", "--verify-renet", "/b"]) == 0
    assert seen == ["/a", "/b"]


@pytest.fixture(autouse=True)
def _private_tmp(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every directory `pin_renet` or a test makes lands under the test's own tmp_path."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


def test_pin_copies_the_three_names_and_verifies_the_copies(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "bin"
    src.mkdir()
    names = ("renet", "renet-linux-amd64", "renet-linux-arm64")
    for name in names:
        (src / name).write_text(name)
    checked: list[str] = []

    def baked(binary, *_a):
        checked.append(binary)
        return PUB

    monkeypatch.setattr(plane, "baked_public_key", baked)
    host = plane.pin_renet([str(src / n) for n in names], PUB)
    pinned = os.path.dirname(host)
    assert os.path.basename(host) == "renet"
    assert pinned != str(src)
    assert sorted(os.listdir(pinned)) == sorted(names)
    # The copies were verified, not the shared originals.
    assert sorted(checked) == sorted(os.path.join(pinned, n) for n in names)


def test_pin_refuses_a_renet_that_bakes_another_key(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the same call with a mismatched key raises, naming both fingerprints."""
    (tmp_path / "renet").write_text("r")
    monkeypatch.setattr(plane, "baked_public_key", lambda _b, *_a: OTHER)
    with pytest.raises(plane.PlaneError) as exc:
        plane.pin_renet([str(tmp_path / "renet")], PUB)
    assert fp(PUB) in str(exc.value)
    assert fp(OTHER) in str(exc.value)


def test_pin_needs_the_host_binary(tmp_path) -> None:
    (tmp_path / "renet-linux-amd64").write_text("r")
    with pytest.raises(plane.PlaneError, match="host `renet`"):
        plane.pin_renet([str(tmp_path / "renet-linux-amd64")], PUB)


def test_renet_path_goes_to_github_env_or_stdout(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    gh = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(gh))
    plane.export_renet_path("/p/renet")
    assert gh.read_text() == "RENET_BINARY_PATH=/p/renet\n"
    monkeypatch.delenv("GITHUB_ENV")
    plane.export_renet_path("/p/renet")
    assert "export RENET_BINARY_PATH=/p/renet" in capsys.readouterr().out


def test_run_pins_and_exports_the_renet_path(monkeypatch: pytest.MonkeyPatch) -> None:
    drive(monkeypatch, "192.168.111.254")
    exported: list[str] = []
    monkeypatch.setattr(plane, "export_renet_path", exported.append)
    assert plane.run(OPTS) == 0
    assert len(exported) == 1
    assert os.path.basename(exported[0]) == "renet"
    assert os.environ["RENET_BINARY_PATH"] == exported[0]


def test_ci_mode_pins_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    drive(monkeypatch, "192.168.111.254")
    exported: list[str] = []
    monkeypatch.setattr(plane, "export_renet_path", exported.append)
    assert plane.run(plane.Options("4900", "11", rebuild_renet=False)) == 0
    assert exported == []


def test_parse_splits_the_follow_on_command_after_a_bare_dash_dash() -> None:
    opts = plane.parse(["--port", "4911", "--", "npm", "run", "e2e", "--", "--test", "31"])
    assert opts.port == "4911"
    assert opts.command == ["npm", "run", "e2e", "--", "--test", "31"]
    assert plane.parse([]).command == []
    assert plane.main(["--"]) == 2


def test_exec_follow_on_hands_the_plane_environment_to_the_command(monkeypatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(os, "environ", {"REDIACC_ACCOUNT_SERVER": "http://b:4900"})
    plane.exec_follow_on(["cmd", "a"], K, lambda f, argv, env: seen.update(f=f, argv=argv, env=env))
    assert seen["f"] == "cmd"
    assert seen["argv"] == ["cmd", "a"]
    assert seen["env"]["E2E_BACKUP_S3_KEY"] == "kk"
    assert seen["env"]["E2E_BACKUP_S3_SECRET"] == "ss"
    assert seen["env"]["REDIACC_ACCOUNT_SERVER"] == "http://b:4900"


def test_a_real_follow_on_process_sees_the_variables_and_nothing_is_printed() -> None:
    """Fails without the fix: a local run exported nothing, so the chained command saw neither variable."""
    check = 'test "$E2E_BACKUP_S3_KEY" = kk && test "$E2E_BACKUP_S3_SECRET" = ss'
    code = (
        "from rediacc_ci.testrun import start_backup_plane as p;"
        f"p.exec_follow_on(['sh', '-c', {check!r}], {K!r})"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("E2E_BACKUP_S3")}
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "kk" not in result.stdout + result.stderr


def test_run_execs_the_follow_on_only_after_the_plane_is_up(monkeypatch) -> None:
    drive(monkeypatch, "192.168.111.254")
    ran: list[list[str]] = []
    monkeypatch.setattr(plane, "exec_follow_on", lambda cmd, _k: ran.append(list(cmd)))
    assert plane.run(plane.Options("4900", "11", True, [], ["true"])) == 0
    assert ran == [["true"]]
    ran.clear()
    drive(monkeypatch, "192.168.111.254", probe_ok=False)
    assert plane.run(plane.Options("4900", "11", True, [], ["true"])) == 1
    assert ran == []

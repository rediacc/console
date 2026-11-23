"""Tests for `rediacc_ci.testrun.onprem_image` against a fake Docker: no image, no network. The controls are a container that dials out (the run must fail), a detector that cannot see a dial (the run must fail), and the cleanup on every failure path."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.testrun import onprem_image as mod
from rediacc_ci.testrun import onprem_stack

if TYPE_CHECKING:
    import pathlib


def done(argv: list[str], rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, rc, out, err)


class FakeDocker(onprem_stack.Runtime):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self.proxy_log = ""
        self.account_log = "listening on 4910\n"
        self.probe_logged = True
        self.fail_on = ""
        self.health = 200
        self.slept = 0.0

    def run(self, argv, env=None, **_unused) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        self.envs.append(env)
        joined = " ".join(argv)
        if self.fail_on and self.fail_on in joined:
            return done(argv, 1, "", "boom")
        if argv[:2] == ["docker", "logs"]:
            return done(
                argv, 0, "", self.proxy_log if argv[2] == mod.PROXY_NAME else self.account_log
            )
        if "--rm" in argv and mod.PROBE_HOST in joined and self.probe_logged:
            self.proxy_log += "EGRESS GET http://%s/\n" % mod.PROBE_HOST
        return done(argv)

    def http_get(self, *_unused) -> tuple[int, str]:
        return self.health, ""

    def sleep(self, seconds: float) -> None:
        self.slept += seconds


def _go(rt: FakeDocker, root: pathlib.Path, *extra: str) -> int:
    return mod.main(["--airgapped", "--no-build", "--window", "3", *extra], runtime=rt, root=root)


def _removed(rt: FakeDocker) -> list[str]:
    return [a[-1] for a in rt.calls if a[:3] == ["docker", "rm", "-f"]]


def test_a_clean_window_passes_and_everything_is_removed(tmp_path: pathlib.Path) -> None:
    rt = FakeDocker()
    assert _go(rt, tmp_path) == 0
    assert rt.slept >= 3
    assert set(_removed(rt)) == {mod.PROXY_NAME, mod.ACCOUNT_NAME, mod.FORWARDER_NAME}
    assert ["docker", "network", "rm", mod.NETWORK] in rt.calls


def test_the_network_is_internal_and_the_image_gets_the_proxy(tmp_path: pathlib.Path) -> None:
    rt = FakeDocker()
    assert _go(rt, tmp_path) == 0
    assert ["docker", "network", "create", "--internal", mod.NETWORK] in rt.calls
    run = next(a for a in rt.calls if a[:2] == ["docker", "run"] and mod.IMAGE in a)
    assert mod.IMAGE in run
    assert "%s=http://%s:%d" % ("HTTPS_PROXY", mod.PROXY_NAME, mod.PROXY_PORT) in run
    assert run[run.index("--network") + 1] == mod.NETWORK
    # The account server's keys travel by name, never by value.
    assert "ACCOUNT_ED25519_PRIVATE_KEY" in run
    assert not any(part.startswith("ACCOUNT_ED25519_PRIVATE_KEY=") for part in run)


def test_a_container_that_dials_out_fails_the_run_the_control(tmp_path: pathlib.Path) -> None:
    rt = FakeDocker()
    rt.proxy_log = "EGRESS CONNECT telemetry.example.com:443\n"
    assert _go(rt, tmp_path) == 1
    assert set(_removed(rt)) == {mod.PROXY_NAME, mod.ACCOUNT_NAME, mod.FORWARDER_NAME}


def test_the_probes_own_dial_is_not_a_finding() -> None:
    log_text = "EGRESS GET http://%s/\n" % mod.PROBE_HOST
    assert mod.find_egress(log_text) == []
    assert mod.probe_seen(log_text)
    assert mod.find_egress(log_text + "EGRESS GET http://other.example/\n") == [
        "EGRESS GET http://other.example/"
    ]


def test_a_resolution_error_in_the_images_log_fails_the_run(tmp_path: pathlib.Path) -> None:
    rt = FakeDocker()
    rt.account_log = "Error: getaddrinfo ENOTFOUND api.stripe.com\n"
    assert _go(rt, tmp_path) == 1


def test_a_detector_that_cannot_see_a_dial_fails_the_run(tmp_path: pathlib.Path) -> None:
    rt = FakeDocker()
    rt.probe_logged = False
    assert _go(rt, tmp_path) == 1
    assert not any(mod.IMAGE in a for a in rt.calls if a[:2] == ["docker", "run"])
    assert _removed(rt) == [mod.PROXY_NAME]
    assert ["docker", "network", "rm", mod.NETWORK] in rt.calls


@pytest.mark.parametrize(
    ("fail_on", "expected_removed"),
    [
        ("network create", set()),
        ("--name %s" % mod.PROXY_NAME, {mod.PROXY_NAME}),
        ("--name %s" % mod.ACCOUNT_NAME, {mod.PROXY_NAME, mod.ACCOUNT_NAME}),
        ("--name %s" % mod.FORWARDER_NAME, {mod.PROXY_NAME, mod.ACCOUNT_NAME, mod.FORWARDER_NAME}),
        ("network connect", {mod.PROXY_NAME, mod.ACCOUNT_NAME, mod.FORWARDER_NAME}),
    ],
)
def test_a_failing_step_removes_what_it_had_started(
    tmp_path: pathlib.Path, fail_on: str, expected_removed: set[str]
) -> None:
    rt = FakeDocker()
    rt.fail_on = fail_on
    assert _go(rt, tmp_path) == 1
    removed = set(_removed(rt))
    assert removed == expected_removed
    assert ["docker", "network", "rm", mod.NETWORK] in rt.calls


def test_an_unhealthy_server_fails_the_run(tmp_path: pathlib.Path) -> None:
    rt = FakeDocker()
    rt.health = 503
    assert _go(rt, tmp_path) == 1
    assert mod.ACCOUNT_NAME in _removed(rt)


def test_a_failed_build_stops_before_anything_starts(tmp_path: pathlib.Path) -> None:
    rt = FakeDocker()
    rt.fail_on = "build_server"
    assert mod.main(["--airgapped", "--window", "1"], runtime=rt, root=tmp_path) == 1
    assert not any(a[:2] == ["docker", "network"] for a in rt.calls)


def test_the_build_names_the_onprem_target(tmp_path: pathlib.Path) -> None:
    rt = FakeDocker()
    assert mod.main(["--airgapped", "--window", "1"], runtime=rt, root=tmp_path) == 0
    build = rt.calls[0]
    assert build[-3:] == ["-m", "rediacc_ci.ops.build_server", "onprem"]
    assert build[-1] == "onprem"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--no-build"],
        ["--airgapped", "--window"],
        ["--airgapped", "--window", "x"],
        ["--airgapped", "--bogus"],
    ],
)
def test_bad_usage_exits_2(argv: list[str], tmp_path: pathlib.Path) -> None:
    assert mod.main(argv, runtime=FakeDocker(), root=tmp_path) == 2

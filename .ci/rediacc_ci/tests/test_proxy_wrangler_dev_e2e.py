"""`check:ci-proxy-wrangler-dev-e2e` (`.ci/scripts/quality/check_proxy_wrangler_dev_e2e.py`): the proxy Worker under `wrangler dev` routes a valid bearer into its container and refuses the rest (agent/plans/PLAN-cloudflare-proxy.md box A6).

OFFLINE ONLY. The gate's real run needs docker and the Containers runtime of `wrangler dev`, so it is `local-only`; this module runs wherever pytest runs and proves the parts that decide its verdict: the dev-config parity check against the REAL wrangler.toml and wrangler.dev.toml, the verdict over observations, the fake account server, the log parsers, and that the real-run entry refuses (exit 1) or cannot-runs (exit 77) instead of passing when it cannot see a Worker.

EVERY PLANT GOES INTO A COPY. The two wrangler configs are copied under `tmp_path`, planted there, and the gate is pointed at the copy as its root; the real files are hashed before and after the module.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import typing
import urllib.error

import pytest

from rediacc_ci import paths
from rediacc_ci.core import https
from rediacc_ci.quality import proxy_wrangler_dev_e2e as gate
from rediacc_ci.well_known import PROXY_EU_HOST

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
ENTRY = ROOT / ".ci" / "scripts" / "quality" / "check_proxy_wrangler_dev_e2e.py"
WORKER = ROOT.joinpath(*gate.WORKER_DIR)
CONFIGS = (gate.DEV_CONFIG, gate.DEPLOY_CONFIG)


def _digest() -> str:
    h = hashlib.sha256()
    for name in CONFIGS:
        h.update((WORKER / name).read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="module", autouse=True)
def real_configs_untouched():
    before = _digest()
    yield
    assert _digest() == before, "a test changed the real workers/proxy wrangler configs"


@pytest.fixture
def root_copy(tmp_path: pathlib.Path) -> pathlib.Path:
    worker = tmp_path.joinpath(*gate.WORKER_DIR)
    worker.mkdir(parents=True)
    for name in CONFIGS:
        shutil.copyfile(WORKER / name, worker / name)
    return tmp_path


def test_selftest_controls_pass(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.selftest() is False
    out = capsys.readouterr().out
    assert out.count("PASS") >= 30, "the selftest's controls stopped running"


def test_entry_selftest_exits_zero() -> None:
    r = subprocess.run(
        [sys.executable, str(ENTRY), "--selftest"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert "control(s)" in r.stdout


def test_real_dev_config_mirrors_the_deployed_one() -> None:
    assert gate.static_findings(ROOT) == []


@pytest.mark.parametrize(
    ("label", "plant", "needle"),
    [
        (
            "services",
            '\n[[services]]\nbinding = "ACCOUNT"\nservice = "rediacc-account-eu"\n',
            "[[services]]",
        ),
        (
            "routes",
            f'\nroutes = [{{ pattern = "{PROXY_EU_HOST}", custom_domain = true }}]\n',
            "routes",
        ),
    ],
)
def test_planted_dev_config_is_refused_before_docker(
    root_copy: pathlib.Path, label: str, plant: str, needle: str, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = root_copy.joinpath(*gate.WORKER_DIR, gate.DEV_CONFIG)
    text = dev.read_text()
    # A top-level key has to precede the first table, or TOML files it under that table.
    dev.write_text(plant + text if label == "routes" else text + plant)
    found = gate.static_findings(root_copy)
    assert len(found) == 1, found
    assert needle in found[0]
    assert gate.run(root_copy) == 1
    assert needle in capsys.readouterr().err


def test_drifted_compatibility_date_is_refused(root_copy: pathlib.Path) -> None:
    dev = root_copy.joinpath(*gate.WORKER_DIR, gate.DEV_CONFIG)
    dev.write_text(
        dev.read_text().replace('compatibility_date = "', 'compatibility_date = "1999-', 1)
    )
    found = gate.static_findings(root_copy)
    assert len(found) == 1, found
    assert "compatibility_date" in found[0]


def test_faithful_copy_without_wrangler_cannot_run_rather_than_pass(
    root_copy: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.static_findings(root_copy) == []
    assert gate.cannot_run(root_copy) is not None
    assert gate.run(root_copy) == gate.CANNOT_RUN
    assert "Nothing was checked" in capsys.readouterr().err


def test_unexecutable_staged_renet_cannot_run_rather_than_traceback(
    root_copy: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = root_copy.joinpath(*gate.proxy_image_smoke.STAGE_DIR)
    stage.mkdir(parents=True, exist_ok=True)
    stage.joinpath(gate.executor_artifacts.MANIFEST).write_text("{}")
    renet = stage.joinpath(gate.executor_artifacts.RENET)
    renet.write_bytes(b"not run")
    renet.chmod(0o644)
    monkeypatch.setattr(gate, "cannot_run", lambda _root: None)
    assert gate.run(root_copy) == gate.CANNOT_RUN
    assert "cannot be executed" in capsys.readouterr().err


def test_hung_node_on_the_staged_bundle_cannot_run_rather_than_traceback(
    root_copy: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = root_copy.joinpath(*gate.proxy_image_smoke.STAGE_DIR)
    stage.mkdir(parents=True, exist_ok=True)
    stage.joinpath(gate.executor_artifacts.MANIFEST).write_text("{}")
    renet = stage.joinpath(gate.executor_artifacts.RENET)
    renet.write_text("#!/bin/sh\necho renet 1.2.3\n")
    renet.chmod(0o755)
    real_run = gate.subprocess.run

    def fake_run(cmd: list[str], **kwargs: typing.Any) -> subprocess.CompletedProcess[str]:
        if cmd and cmd[0] == "node":
            raise subprocess.TimeoutExpired(cmd, 60)
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(gate, "cannot_run", lambda _root: None)
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    monkeypatch.setattr(gate.proxy_image_smoke, "parse_renet_version", lambda _t: "1.2.3")
    assert gate.run(root_copy) == gate.CANNOT_RUN
    assert "node cannot run the staged bundle" in capsys.readouterr().err


def test_healthy_observation_passes() -> None:
    assert gate.verdict(gate.HEALTHY) == []


@pytest.mark.parametrize(("label", "patch"), gate.PLANTS, ids=[p[0] for p in gate.PLANTS])
def test_each_plant_is_exactly_one_finding(label: str, patch: dict) -> None:
    assert len(gate.verdict({**gate.HEALTHY, **patch})) == 1, label


def test_missing_observations_are_findings_not_a_pass() -> None:
    found = gate.verdict({})
    assert any("no bearer" in f for f in found)
    assert any("valid proxy:exec bearer" in f for f in found)


def test_log_parsers() -> None:
    log = (
        "#28 naming to docker.io/cloudflare-dev/executorcontainer:1008f582 0.0s done\n"
        "[wrangler:info] Ready on http://127.0.0.1:18932\n"
    )
    assert gate.dev_image_tags(log) == {"cloudflare-dev/executorcontainer:1008f582"}
    assert gate.dev_image_tags("naming to docker.io/library/node:24") == set()
    assert gate.ready_url(log) == "http://127.0.0.1:18932"
    assert gate.ready_url("⎔ Starting local server...") is None


def _introspect(fake: gate.FakeAccount, executor: str, token: str) -> tuple[int, dict]:
    req = https.build_request(
        fake.url + gate.INTROSPECT_PATH,
        data=json.dumps({"token": token}).encode(),
        headers={"authorization": "Bearer " + executor},
        method="POST",
        http="loopback",
    )
    try:
        with https.urlopen(req, timeout=5, http="loopback") as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            return e.code, {}


def test_fake_account_answers_both_ways() -> None:
    t = gate.mint_tokens()
    assert len(set(t.values())) == 3
    with gate.FakeAccount(t["executor"], t["caller"]) as fake:
        status, body = _introspect(fake, t["executor"], t["caller"])
        assert status == 200
        assert body["active"] is True
        assert body["orgId"]
        assert "proxy:exec" in body["scopes"]
        assert _introspect(fake, t["executor"], t["stranger"]) == (200, {"active": False})
        assert _introspect(fake, "not-the-executor", t["caller"])[0] == 401
        assert fake.asked_with_executor_token(t["caller"])
        assert fake.asked_with_executor_token(t["stranger"])
        assert fake.count() == 3


@pytest.mark.parametrize(
    ("plant", "who", "active"),
    [("active-all", "stranger", True), ("inactive-all", "caller", False)],
)
def test_fake_account_plants_flip_the_answer(plant: str, who: str, active: bool) -> None:
    t = gate.mint_tokens()
    with gate.FakeAccount(t["executor"], t["caller"], plant=plant) as fake:
        assert _introspect(fake, t["executor"], t[who])[1].get("active") is active


def test_unknown_plant_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown plant"):
        gate.FakeAccount("e", "c", plant="sometimes")

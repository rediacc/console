"""One lock per bench region for the four bench runners (PLAN-push-decoupling.md L3): `deploy_bench`, `deploy_proxy --target bench`, `reset_bench` and the enterprise-proof runner each wait on a held `bench-<region>` and name the holder, before any credential is read.

Each test points `XDG_RUNTIME_DIR` at its own directory and holds the lock from a separate process, so the pid in the refusal is provably the holder's. The step after the lock (the Cloudflare credential, or the proof lab) is a recording fake: a refused run never reaches it, and the CONTROL with the lock free does.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
from typing import Any, cast

import pytest

from rediacc_ci.core import resource_lock
from rediacc_ci.deploy import deploy_proxy
from rediacc_ci.enterprise import proof
from rediacc_ci.ops import deploy_bench, reset_bench
from rediacc_ci.tests.test_deploy_deploy_proxy import _fixture_root
from rediacc_ci.tests.test_ops_reset_bench_region import _world

CI_ROOT = pathlib.Path(__file__).resolve().parents[2]

HOLD_SCRIPT = """
import sys, time
from rediacc_ci.core import resource_lock
lock = resource_lock.ResourceLock(sys.argv[1])
lock.acquire("test holder", 5.0, session="bench-t1")
print("held", flush=True)
time.sleep(60)
"""


class ReachedError(Exception):
    """The step after the lock ran."""


@pytest.fixture
def runtime(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run_dir))
    monkeypatch.setenv("PYTHONPATH", str(CI_ROOT))
    monkeypatch.setenv("BENCH_LOCK_WAIT_S", "1")
    return run_dir


class Holder:
    def __init__(self, resource: str) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-c", HOLD_SCRIPT, resource], stdout=subprocess.PIPE, text=True
        )
        assert self.proc.stdout is not None
        assert self.proc.stdout.readline().strip() == "held"

    @property
    def pid(self) -> int:
        return self.proc.pid

    def stop(self) -> None:
        self.proc.kill()
        self.proc.wait()
        if self.proc.stdout is not None:
            self.proc.stdout.close()


@pytest.fixture
def hold():
    holders: list[Holder] = []

    def start(resource: str) -> Holder:
        holders.append(Holder(resource))
        return holders[-1]

    yield start
    for holder in holders:
        holder.stop()


def _names_holder(text: str, holder: Holder) -> None:
    assert "pid %d" % holder.pid in text
    assert "purpose test holder" in text


# --------------------------------------------------------------------------- deploy_bench


def _deploy_bench_world(monkeypatch: pytest.MonkeyPatch, reached: list[str]) -> None:
    monkeypatch.setattr(deploy_bench, "_reexec_under_profile", lambda _argv, _region="eu": None)
    monkeypatch.setattr(deploy_bench.shutil, "which", lambda _c: "/usr/bin/true")

    def resolve(_account: str) -> Any:
        reached.append("cf_auth.resolve")
        raise deploy_bench.cf_auth.CfAuthError("credential step reached")

    monkeypatch.setattr(deploy_bench.cf_auth, "resolve", resolve)


def test_deploy_bench_waits_on_its_region_and_names_the_holder(hold, monkeypatch, capsys) -> None:
    holder = hold("bench-eu")
    reached: list[str] = []
    _deploy_bench_world(monkeypatch, reached)
    assert deploy_bench.main(["--region", "eu"]) == 1
    _names_holder(capsys.readouterr().err, holder)
    assert reached == []


def test_deploy_bench_is_not_blocked_by_another_region(hold, monkeypatch, capsys) -> None:
    """A reset of us does not hold an eu deploy back: with bench-us held the eu deploy reaches its credential."""
    hold("bench-us")
    reached: list[str] = []
    _deploy_bench_world(monkeypatch, reached)
    assert deploy_bench.main(["--region", "eu"]) == 1
    assert reached == ["cf_auth.resolve"]
    assert "busy" not in capsys.readouterr().err


def test_deploy_bench_seed_also_waits(hold, monkeypatch, capsys) -> None:
    holder = hold("bench-eu")
    reached: list[str] = []
    _deploy_bench_world(monkeypatch, reached)
    monkeypatch.setattr(
        deploy_bench, "seed_root", lambda *_a, **_k: reached.append("seed") or "exists"
    )
    assert deploy_bench.main(["--seed-root"]) == 1
    _names_holder(capsys.readouterr().err, holder)
    assert reached == []


# --------------------------------------------------------------------------- reset_bench


def test_reset_bench_waits_on_its_region_and_names_the_holder(hold, monkeypatch, capsys) -> None:
    holder = hold("bench-us")
    asked: list[tuple] = []
    _world(monkeypatch, [], asked)

    def resolve(_account: str) -> Any:
        raise ReachedError

    monkeypatch.setattr(reset_bench.cf_auth, "resolve", resolve)
    assert reset_bench.main(["--region", "us", "--yes"]) == 1
    _names_holder(capsys.readouterr().err, holder)
    assert asked == []


def test_reset_of_one_region_does_not_wait_on_another(hold, monkeypatch) -> None:
    hold("bench-eu")
    asked: list[tuple] = []
    _world(monkeypatch, [], asked)
    assert reset_bench.main(["--region", "us", "--yes"]) == 0
    assert ("wipe_d1", "us") in asked


# --------------------------------------------------------------------------- deploy_proxy --target bench


@pytest.fixture
def proxy_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    root = _fixture_root(tmp_path)
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    return root


@pytest.mark.usefixtures("proxy_root")
def test_proxy_bench_deploy_waits_and_names_the_holder(hold, monkeypatch, capsys) -> None:
    holder = hold("bench-eu")
    monkeypatch.setenv("REDIACC_BWS_PROFILES", deploy_proxy.BENCH_PROFILE)
    assert deploy_proxy.main(["--target", "bench"]) == 1
    err = capsys.readouterr().err
    _names_holder(err, holder)
    # Refused at the lock: the credential check after it never ran.
    assert deploy_proxy.MISSING_AUTH_MSG not in err


@pytest.mark.usefixtures("runtime", "proxy_root")
def test_proxy_bench_deploy_passes_a_free_lock(monkeypatch, capsys) -> None:
    """Control: with the lock free the same run gets past it to the credential check."""
    monkeypatch.setenv("REDIACC_BWS_PROFILES", deploy_proxy.BENCH_PROFILE)
    assert deploy_proxy.main(["--target", "bench"]) == 1
    assert deploy_proxy.MISSING_AUTH_MSG in capsys.readouterr().err


def _record_bench_held(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    taken: list[object] = []
    real = resource_lock.bench_held

    def spy(regions: Any, purpose: str) -> Any:
        taken.append(regions)
        return real(regions, purpose)

    monkeypatch.setattr(resource_lock, "bench_held", spy)
    return taken


@pytest.mark.usefixtures("proxy_root")
def test_proxy_stable_deploy_takes_no_bench_lock(hold, monkeypatch, capsys) -> None:
    hold("bench-eu")
    taken = _record_bench_held(monkeypatch)
    monkeypatch.setenv("REDIACC_BWS_PROFILES", deploy_proxy.PROFILE)
    assert deploy_proxy.main(["--target", "stable", "--region", "eu", "--version", "1.2.3"]) == 1
    assert taken == []
    assert deploy_proxy.MISSING_AUTH_MSG in capsys.readouterr().err


def test_proxy_bench_dry_run_takes_no_bench_lock(hold, proxy_root, monkeypatch) -> None:
    hold("bench-eu")
    taken = _record_bench_held(monkeypatch)
    monkeypatch.setattr(deploy_proxy, "_run", lambda _argv, **_kw: 0)
    monkeypatch.chdir(proxy_root)
    assert deploy_proxy.main(["--target", "bench", "--dry-run"]) == 0
    assert taken == []


# --------------------------------------------------------------------------- the enterprise-proof runner


class FakeLab:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        self.calls.append(name)
        raise ReachedError(name)


@pytest.mark.parametrize("region", ["eu", "us"])
def test_bench_proof_waits_on_either_region_it_acts_on(
    region: str, hold, monkeypatch, capsys
) -> None:
    holder = hold("bench-%s" % region)
    ran: list[str] = []
    monkeypatch.setattr(proof, "run_verb", lambda verb, _lab, **_kw: ran.append(verb) or 0)
    assert proof.main(["signer", "--bench"], lab=cast("proof.Lab", FakeLab())) == 1
    _names_holder(capsys.readouterr().err, holder)
    assert ran == []


@pytest.mark.usefixtures("runtime")
def test_bench_proof_runs_under_both_locks(monkeypatch) -> None:
    """Control: with both free the verb runs, and holds both regions while it does."""
    seen: list[str] = []

    def run_verb(verb: str, _lab: Any, **_kw: object) -> int:
        for region in ("eu", "us"):
            probe = resource_lock.ResourceLock("bench-%s" % region, say=lambda _l: None)
            with pytest.raises(resource_lock.ResourceBusyError):
                probe.acquire("probe", 0.0, nest=False)
        seen.append(verb)
        return 0

    monkeypatch.setattr(proof, "run_verb", run_verb)
    assert proof.main(["signer", "--bench"], lab=cast("proof.Lab", FakeLab())) == 0
    assert seen == ["signer"]


def test_production_proof_takes_no_bench_lock(hold, monkeypatch) -> None:
    hold("bench-eu")
    taken = _record_bench_held(monkeypatch)
    monkeypatch.setattr(proof, "run_verb", lambda *_a, **_kw: 0)
    assert proof.main(["keys"], lab=cast("proof.Lab", FakeLab())) == 0
    assert taken == []

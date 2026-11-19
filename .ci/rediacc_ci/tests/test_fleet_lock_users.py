"""Every fleet user takes the `fleet` resource lock (PLAN-push-decoupling.md L2): `./rdc.sh ops up|down`, the drill harness before its first VM command, and the e2e bridge setup before its VM reset.

Each test points `XDG_RUNTIME_DIR` at its own directory, so nothing here meets a live vm:check's lock, and no test runs a VM command: the busy cases stop before one by design, and the free case runs a copy of the wrapper whose CLI half is replaced by a probe.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import time
import types
from typing import Any, cast

import pytest

from rediacc_ci.core import resource_lock
from rediacc_ci.drills import lib
from rediacc_ci.drills import license as lic

CI_ROOT = pathlib.Path(__file__).resolve().parents[2]
REPO_ROOT = CI_ROOT.parent
RDC_SH = REPO_ROOT / "rdc.sh"
SETUP_TS = REPO_ROOT / "packages" / "e2e-tests" / "src" / "base" / "bridge-global-setup.ts"

HOLD_SCRIPT = """
import sys, time
from rediacc_ci.core import resource_lock
lock = resource_lock.ResourceLock("fleet")
lock.acquire("test holder", 5.0, session="fleet-t1")
print("held", flush=True)
time.sleep(60)
"""


@pytest.fixture
def runtime(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run_dir))
    monkeypatch.setenv("PYTHONPATH", str(CI_ROOT))
    monkeypatch.delenv("RDC_FLEET_LOCKED", raising=False)
    return run_dir


@pytest.fixture
def holder(runtime: pathlib.Path):
    # Depends on `runtime`: the holder takes the lock in the test's private directory, with PYTHONPATH set, never the operator's real fleet lock.
    assert runtime.is_dir()
    proc = subprocess.Popen([sys.executable, "-c", HOLD_SCRIPT], stdout=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "held"
    yield proc
    proc.kill()
    proc.wait()
    proc.stdout.close()


def _env(runtime: pathlib.Path, tmp_path: pathlib.Path, **extra: str) -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "XDG_RUNTIME_DIR": str(runtime),
        "NO_COLOR": "1",
        **extra,
    }


# --------------------------------------------------------------------------- ./rdc.sh ops up|down


@pytest.mark.parametrize("verb", ["down", "up"])
def test_rdc_ops_waits_on_a_held_fleet_and_names_the_holder(
    verb: str, runtime: pathlib.Path, tmp_path: pathlib.Path, holder: subprocess.Popen
) -> None:
    started = time.monotonic()
    done = subprocess.run(
        ["bash", str(RDC_SH), "--config", "fleet-test", "ops", verb],
        env=_env(runtime, tmp_path, RESOURCE_LOCK_WAIT_S="2"),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == resource_lock.EXIT_BUSY, done.stderr
    assert time.monotonic() - started >= 2.0
    assert "pid %d" % holder.pid in done.stderr
    assert "purpose test holder" in done.stderr
    # Nothing past the lock ran: no CLI preparation, so no CLI and no VM command.
    assert "Preparing CLI" not in done.stderr
    assert done.stdout == ""


def _probe_wrapper(tmp_path: pathlib.Path) -> pathlib.Path:
    """rdc.sh up to and including its fleet-lock block, then a probe in place of the CLI half: the lock block under test is the real text."""
    text = RDC_SH.read_text()
    marker = text.index("# THE FLEET LOCK")
    end = text.index("\nfi\n", marker) + len("\nfi\n")
    probe = (
        'echo "CLI $* locked=${RDC_FLEET_LOCKED:-}"\n'
        'PYTHONPATH="%s" python3 -m rediacc_ci.core.resource_lock holder --resource fleet\n'
        % CI_ROOT
    )
    root = tmp_path / "root"
    root.mkdir()
    (root / ".ci").symlink_to(CI_ROOT)
    wrapper = root / "rdc.sh"
    wrapper.write_text(text[:end] + probe)
    wrapper.chmod(0o755)
    return wrapper


def test_rdc_ops_down_runs_under_the_lock_when_free(
    runtime: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    wrapper = _probe_wrapper(tmp_path)
    done = subprocess.run(
        ["bash", str(wrapper), "--dev", "ops", "down"],
        env=_env(runtime, tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[0] == "CLI --dev ops down locked=1"
    assert "purpose rdc.sh ops down" in lines[1]


@pytest.mark.usefixtures("holder")
def test_rdc_other_verbs_take_no_lock(runtime: pathlib.Path, tmp_path: pathlib.Path) -> None:
    """Control: `ops status` and a `--config ops` value are not `ops up|down`, so they pass a held lock untouched."""
    wrapper = _probe_wrapper(tmp_path)
    for argv in (["ops", "status"], ["--config", "ops", "up"], ["repo", "up", "ops"]):
        done = subprocess.run(
            ["bash", str(wrapper), *argv],
            env=_env(runtime, tmp_path, RESOURCE_LOCK_WAIT_S="0"),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert done.returncode == 0, (argv, done.stderr)
        assert done.stdout.splitlines()[0] == "CLI %s locked=" % " ".join(argv)


# --------------------------------------------------------------------------- the drill harness


@pytest.mark.usefixtures("runtime")
def test_drill_hold_fleet_refuses_a_held_fleet_naming_the_holder(
    holder: subprocess.Popen, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DRILL_FLEET_WAIT_S", "2")
    drill = lib.Drill("fleet-test")
    started = time.monotonic()
    assert drill.hold_fleet("upload renet") is False
    assert time.monotonic() - started >= 2.0
    err = capsys.readouterr().err
    assert "pid %d" % holder.pid in err
    assert "purpose test holder" in err
    assert drill.fleet_lock is None


@pytest.mark.usefixtures("runtime")
def test_drill_hold_fleet_holds_until_teardown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRILL_FLEET_WAIT_S", "0")
    drill = lib.Drill("fleet-test")
    assert drill.hold_fleet("upload renet") is True
    other = resource_lock.ResourceLock("fleet", say=lambda _line: None)
    # Held: another process-level holder (nesting off, since this is the same pid) is refused.
    with pytest.raises(resource_lock.ResourceBusyError) as exc:
        other.acquire("x", 0.0, nest=False)
    assert "purpose drill fleet-test: upload renet" in str(exc.value)
    drill.teardown()
    assert drill.fleet_lock is None
    other.acquire("after", 0.0, nest=False)
    other.release()


def _license_fake(calls: list[str]) -> Any:
    opts = lic.Options()
    opts.legs = "c,d,e,f"
    drill = lib.Drill("license")
    fake = types.SimpleNamespace(o=opts, d=drill)
    for name in ("announce_cost", "preflight_tools"):
        setattr(fake, name, lambda name=name: calls.append(name))
    for name in ("preflight_vms", "preflight_ssh", "preflight_ceph", "preflight_agent_overrides"):
        setattr(fake, name, lambda name=name: calls.append(name))
    fake.setup_sandbox = lambda: (_ for _ in ()).throw(SystemExit(5))
    return fake


PREFLIGHTS = [
    "announce_cost",
    "preflight_tools",
    "preflight_vms",
    "preflight_ssh",
    "preflight_ceph",
    "preflight_agent_overrides",
]


@pytest.mark.usefixtures("runtime", "holder")
def test_license_drill_stops_before_any_vm_write_on_a_held_fleet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the read-only preflights run; the refusal comes before the sandbox, the gateway and `machine setup` (the renet upload)."""
    monkeypatch.setenv("DRILL_FLEET_WAIT_S", "1")
    calls: list[str] = []
    fake = _license_fake(calls)
    assert lic.License.run_all(cast("Any", fake)) == 1
    assert calls == PREFLIGHTS


@pytest.mark.usefixtures("runtime")
def test_license_drill_takes_the_fleet_then_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Control: with the fleet free the same run takes the lock and goes on to the sandbox."""
    monkeypatch.setenv("DRILL_FLEET_WAIT_S", "0")
    calls: list[str] = []
    fake = _license_fake(calls)
    with pytest.raises(SystemExit):
        lic.License.run_all(cast("Any", fake))
    assert calls == PREFLIGHTS
    assert fake.d.fleet_lock is not None
    fake.d.release_fleet()


@pytest.mark.usefixtures("runtime")
def test_license_drill_rechecks_the_vm_preflights_after_a_real_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding cdc29044.1: the preflights ran before the wait, so a wait of minutes leaves them describing a fleet that may be gone. The control above (no wait) runs each exactly once."""
    monkeypatch.setenv("DRILL_FLEET_WAIT_S", "0")
    calls: list[str] = []
    fake = _license_fake(calls)
    real_hold = fake.d.hold_fleet

    def waited(purpose: str) -> bool:
        taken = real_hold(purpose)
        fake.d.fleet_waited = lic.FLEET_REWAIT_S + 4
        return taken

    monkeypatch.setattr(fake.d, "hold_fleet", waited)
    with pytest.raises(SystemExit):
        lic.License.run_all(cast("Any", fake))
    assert calls == [*PREFLIGHTS, "preflight_vms", "preflight_ssh", "preflight_ceph"]
    fake.d.release_fleet()


@pytest.mark.usefixtures("runtime", "holder")
def test_license_drill_with_no_vm_leg_takes_no_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--legs f` touches no machine, so a held fleet does not stop it."""
    monkeypatch.setenv("DRILL_FLEET_WAIT_S", "0")
    calls: list[str] = []
    fake = _license_fake(calls)
    fake.o.legs = "f"
    with pytest.raises(SystemExit):
        lic.License.run_all(cast("Any", fake))
    assert fake.d.fleet_lock is None


# --------------------------------------------------------------------------- the e2e bridge setup


def _setup_body() -> str:
    text = SETUP_TS.read_text()
    start = text.index("async function bridgeGlobalSetup(")
    return text[start:]


def test_e2e_setup_takes_the_fleet_before_the_reset_even_without_one() -> None:
    body = _setup_body()
    take = body.index("await holdFleetLock(")
    assert take < body.index("opsManager.resetVMs()")
    # Before the skip branch, so BRIDGE_TEST_SKIP_RESET=1 takes it too, and before any VM-touching step.
    assert take < body.index("if (skipReset)")
    assert take < body.index("ensureInfrastructure(")
    # Held for the suite: the release is the setup's return value (Playwright runs it as teardown), and a failed setup releases it.
    assert re.search(r"return releaseFleet;", body)
    assert re.search(r"await releaseFleet\(\);\s*throw error;", body)


def test_e2e_hold_takes_the_fleet_resource() -> None:
    text = SETUP_TS.read_text()
    fn = text[text.index("export async function holdFleetLock(") :]
    fn = fn[: fn.index("\n}\n")]
    # Biome wraps the argv one item per line, so compare the items, not the spelling.
    assert re.search(r"'rediacc_ci\.core\.resource_lock',\s*'run',\s*'--resource',\s*'fleet'", fn)

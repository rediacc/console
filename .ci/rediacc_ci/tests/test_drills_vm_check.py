"""`rediacc_ci.drills.vm_check`: the whole flow driven through a fake host and a fake account, so no case reaches a VM.

`World` answers every command the check issues (git, go, `./rdc.sh`, the ssh probes, `sftp -b`) from an in-memory fleet. Each verdict class is produced by bending one thing in that world. The four MUTANTS are source edits of the module; each one must turn its scenario red, which proves the scenario can fail.
"""

from __future__ import annotations

import fcntl
import importlib.util
import io
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci import paths
from rediacc_ci.core import run_verbs
from rediacc_ci.drills import vm_check
from rediacc_ci.drills import vm_check_receipt as receipt_mod

if TYPE_CHECKING:
    import types

TREE = "a" * 40
HEAD = "e" * 40
PTR = "c" * 40
HASH = "f" * 64
DIGEST = "d" * 64
TOKEN = "tok-PLANTED-7f3a9c2e1b5d4a60"
NET = "192.168.111"
BRIDGE = NET + ".1"
WORKER = NET + ".11"
PARENT = "vmcheck-base"
# 2026-10-14T18:00:00Z
NOW = 1792000800.0

MUTANTS = {
    "skip-teardown": ("            self._teardown()\n", "            pass\n"),
    "pass-on-zero-steps": ("    if assertions == 0:\n", "    if False:\n"),
    "print-token": (
        '% (ACCOUNT_LOGIN, ",".join(TOKEN_SCOPES))\n',
        '% (token, ",".join(TOKEN_SCOPES))\n',
    ),
    "down-reused-fleet": (
        "        if self.fleet_mode == COLD and self.fleet_started:\n",
        "        if self.fleet_mode:\n",
    ),
}


class World(vm_check.Host):
    """An in-memory fleet answering every command the check issues."""

    def __init__(self, root: pathlib.Path, **over: Any) -> None:
        self.root = root
        self.rdc_path = str(root / "rdc.sh")
        self.running = list(over.pop("running", (BRIDGE, WORKER)))
        self.kvm = over.pop("kvm", True)
        self.built = over.pop("built", PTR)
        self.modified = over.pop("modified", False)
        self.rebuild_fixes = over.pop("rebuild_fixes", True)
        self.ops_up_rc = over.pop("ops_up_rc", 0)
        self.machines = over.pop("machines", [{"name": "vm11", "ip": WORKER}])
        self.os_release = over.pop("os_release", "ubuntu 24.04")
        self.stored_ok = over.pop("stored_ok", False)
        self.repos: dict[str, str] = {g: "guid-" + g for g in over.pop("grands", (PARENT,))}
        for name in over.pop("extra_repos", ()):
            self.repos[name] = "guid-" + name.replace(":", "-")
        self.ro_breach = over.pop("ro_breach", False)
        self.vscode = over.pop("vscode", True)
        self.refuse_fork = over.pop("refuse_fork", False)
        self.undeletable_suffix = over.pop("undeletable_suffix", "")
        self.crash_on = over.pop("crash_on", "")
        self.signal_on = over.pop("signal_on", "")
        assert not over, over
        self.store = root / "remote-store"
        self.calls: list[list[str]] = []
        self.forked: list[str] = []
        self.envs: list[dict[str, str]] = []
        self.mono = 0.0

    # ------------------------------------------------------------------ Host

    def exists(self, path: str) -> bool:
        return self.kvm if path == "/dev/kvm" else os.path.exists(path)

    def which(self, name: str) -> str | None:
        return "/usr/bin/virsh" if name == "virsh" and self.kvm else None

    def sha256(self, path: pathlib.Path) -> str | None:
        return HASH if path.name == "renet" else None

    def now(self) -> float:
        return NOW

    def monotonic(self) -> float:
        self.mono += 0.001
        return self.mono

    def sleep(self, seconds: float) -> None:
        self.mono += seconds

    def run(self, argv, env=None, timeout=None) -> vm_check.Result:
        del timeout
        argv = list(argv)
        self.calls.append(argv)
        self.envs.append(dict(env or {}))
        joined = " ".join(argv)
        if self.crash_on and self.crash_on in joined:
            raise RuntimeError("planted crash")
        if self.signal_on and self.signal_on in joined:
            os.kill(os.getpid(), signal.SIGTERM)
        if argv[0] == "git":
            if argv[2].endswith("private/renet"):
                return vm_check.Result(0, PTR + "\n")
            return self._git(argv[3:])
        if argv[0] == "go":
            text = "\tbuild\tvcs.revision=%s\n\tbuild\tvcs.modified=%s\n" % (
                self.built,
                "true" if self.modified else "false",
            )
            return vm_check.Result(0, text)
        if argv[0] == "ssh":
            if argv[-1] == vm_check.PROBE_RENET_HASH:
                return vm_check.Result(0, HASH + "\n")
            if argv[-1] == vm_check.PROBE_OS_RELEASE:
                return vm_check.Result(0, self.os_release + "\n")
            return vm_check.Result(255, "", "unexpected probe")
        if argv[0] == "sftp":
            return self._sftp(pathlib.Path(argv[-2]).read_text())
        if argv[0] == self.rdc_path:
            return self._rdc(argv[1:], env or {})
        return vm_check.Result(127, "", "unknown command %s" % argv[0])

    # ------------------------------------------------------------------ answers

    def _git(self, args: list[str]) -> vm_check.Result:
        answers: dict[tuple[str, ...], str] = {
            ("rev-parse", "HEAD^{tree}"): TREE,
            ("rev-parse", "HEAD"): HEAD,
            ("rev-parse", "HEAD:private/renet"): PTR,
        }
        return vm_check.Result(0, answers.get(tuple(args), PTR) + "\n")

    def guid(self, tag: str) -> str:
        return self.repos.get("%s:%s" % (PARENT, tag), "")

    def _rdc(self, args: list[str], env: dict[str, str]) -> vm_check.Result:
        ok = vm_check.Result(0)
        head = tuple(args[:2])
        if args == ["--version"]:
            if self.rebuild_fixes:
                self.built, self.modified = PTR, False
            return ok
        if head == ("ops", "status"):
            vms = [{"ip": ip, "status": "running"} for ip in self.running]
            return vm_check.Result(0, json.dumps({"success": True, "data": {"vms": vms}}))
        if head == ("ops", "up"):
            if self.ops_up_rc:
                return vm_check.Result(
                    self.ops_up_rc, "", "booting\nlibvirt: domain failed to start"
                )
            self.running = [BRIDGE, WORKER]
            return ok
        if head == ("ops", "down"):
            self.running = []
            return ok
        if head == ("machine", "list"):
            return vm_check.Result(0, json.dumps({"success": True, "data": self.machines}))
        if head == ("subscription", "status"):
            if self.stored_ok or env.get("REDIACC_TOKEN") == TOKEN:
                return vm_check.Result(0, '{"success":true}')
            return vm_check.Result(1, "", "Unauthorized")
        if head == ("repo", "list"):
            data = [
                {"name": n, "guid": g, "networkId": "29%02d" % i}
                for i, (n, g) in enumerate(sorted(self.repos.items()))
            ]
            return vm_check.Result(0, json.dumps({"success": True, "data": data}))
        if head == ("repo", "fork"):
            if self.refuse_fork:
                return vm_check.Result(
                    1, "", 'Cannot create a new grand repository "x" in agent mode.\nmore'
                )
            name = "%s:%s" % (args[2], args[4])
            self.repos[name] = "guid-" + args[4]
            self.forked.append(args[4])
            return ok
        if head == ("repo", "delete"):
            if self.undeletable_suffix and args[2].endswith(self.undeletable_suffix):
                return vm_check.Result(1, "", "device busy")
            self.repos.pop(args[2], None)
            return ok
        if head == ("term", "connect"):
            return self._shell(args[2], args[4])
        if args[:3] == ["repo", "sync", "upload"]:
            local = pathlib.Path(args[args.index("--local") + 1])
            target = self.store / args[args.index("--remote") + 1]
            shutil.copytree(local, target, symlinks=True, dirs_exist_ok=True)
            return ok
        if args[:3] == ["repo", "sync", "download"]:
            local = pathlib.Path(args[args.index("--local") + 1])
            source = self.store / args[args.index("--remote") + 1]
            shutil.copytree(source, local, symlinks=True, dirs_exist_ok=True)
            return ok
        if head == ("vscode", "connect"):
            if not self.vscode:
                return vm_check.Result(
                    1,
                    "",
                    "VS Code not found.\n\nPlease install from: https://code.visualstudio.com/",
                )
            alias = "rediacc-default-vm11-" + args[2].replace(":", "-")
            return vm_check.Result(0, "%s%s/mnt/rediacc/mounts/x\n" % (vm_check.URI_PREFIX, alias))
        return ok

    def _shell(self, ref: str, command: str) -> vm_check.Result:
        tag = ref.split(":", 1)[1]
        mine = self.guid(tag)
        foreign = [g for n, g in self.repos.items() if g != mine and g in command]
        if command.startswith(("chmod 0777", "touch -m")) and foreign and not self.ro_breach:
            return vm_check.Result(1, "", "chmod: changing permissions: Read-only file system")
        if command.startswith("stat "):
            return vm_check.Result(0, "644 1700000000\n")
        if command == "ls /dev/shm":
            return vm_check.Result(0, "\n")
        if command == "cat /proc/self/cgroup":
            nid = json.loads(self._rdc(["repo", "list"], {}).out)["data"]
            mine_nid = next(e["networkId"] for e in nid if e["name"] == ref)
            return vm_check.Result(0, "0::/renet-exec-%s.scope\n" % mine_nid)
        if command == "renet sandbox-exec --detect":
            return vm_check.Result(0, "Status: enforced\nABI: 6\n")
        return vm_check.Result(0)

    def _sftp(self, batch: str) -> vm_check.Result:
        a = "guid-" + next(t for t in self.forked if t.endswith("-a"))
        line = batch.strip()
        if line.startswith("put") and "/%s/" % a in line:
            return vm_check.Result(0)
        return vm_check.Result(1, "", "remote open: Permission denied")

    # ------------------------------------------------------------------ views

    def rdc_calls(self) -> list[list[str]]:
        return [c[1:] for c in self.calls if c[0] == self.rdc_path]

    def forks_left(self) -> list[str]:
        return [n for n in self.repos if ":vmc-" in n]


class FakeAccount:
    def __init__(self, healthy: bool = True, token: str = TOKEN) -> None:
        self.healthy = healthy
        self.token = token
        self.minted = 0

    def gateway_healthy(self) -> bool:
        return self.healthy

    def mint(self, password: str) -> str:
        assert len(password) >= 24
        self.minted += 1
        return self.token


@pytest.fixture(autouse=True)
def _tmp_workdirs(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = tmp_path / "tmp"
    work.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(work))
    monkeypatch.delenv("DRILL_KEEP_WORK", raising=False)


def run_check(
    tmp_path: pathlib.Path,
    world: World,
    *argv: str,
    m: types.ModuleType = vm_check,
    account: FakeAccount | None = None,
) -> tuple[int, str, dict[str, Any]]:
    out = io.StringIO()
    environ = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ.get("PATH", ""),
        "VM_NET_BASE": NET,
    }
    rc = m.main(
        [*argv, "--keep-work", "--wait", "0"],
        root=world.root,
        host=world,
        account=account or FakeAccount(),
        lock=m.Lock(tmp_path / "vm-check.lock"),
        out=out,
        environ=environ,
        inputs_fn=lambda _root: DIGEST,
    )
    latest = world.root / receipt_mod.CACHE_DIR / receipt_mod.LATEST
    receipt = json.loads(latest.read_text()) if latest.exists() else {}
    return rc, out.getvalue(), receipt


def make_world(tmp_path: pathlib.Path, **over: Any) -> World:
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    return World(root, **over)


def lock_is_free(tmp_path: pathlib.Path) -> bool:
    fd = os.open(tmp_path / "vm-check.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    finally:
        os.close(fd)
    return True


# --------------------------------------------------------------------------- scenarios shared with the mutants


def scenario_crash_mid_v13(m: types.ModuleType, tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, crash_on="docker ps")
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt
    assert receipt["reason"]["class"] == "crashed"
    deletes = [c for c in world.rdc_calls() if c[:2] == ["repo", "delete"]]
    assert len(deletes) == 2, world.rdc_calls()
    assert world.forks_left() == []
    assert all(f["deleted"] for f in receipt["forks"])
    assert lock_is_free(tmp_path)


def scenario_zero_assertions_is_not_verified(m: types.ModuleType, _tmp_path: pathlib.Path) -> None:
    status, reason = m.verdict(0, [], None, [])
    assert status == receipt_mod.NOT_VERIFIED
    assert reason["class"] == "no-assertions"


def scenario_token_never_written(
    m: types.ModuleType, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str] | None = None
) -> None:
    world = make_world(tmp_path)
    account = FakeAccount()
    rc, out, receipt = run_check(tmp_path, world, m=m, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert account.minted == 1
    assert TOKEN not in out
    if capsys is not None:
        captured = capsys.readouterr()
        assert TOKEN not in captured.out
        assert TOKEN not in captured.err
    for argv in world.calls:
        assert all(TOKEN not in a for a in argv), argv
    rdc_envs = [e for c, e in zip(world.calls, world.envs, strict=True) if c[0] == world.rdc_path]
    assert any(e.get("REDIACC_TOKEN") == TOKEN for e in rdc_envs)
    assert TOKEN not in json.dumps(receipt)
    for path in tmp_path.rglob("*"):
        if path.is_file() and not path.is_symlink():
            assert TOKEN.encode() not in path.read_bytes(), path


def scenario_reused_fleet_is_never_downed(m: types.ModuleType, tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["fleet"]["mode"] == vm_check.REUSED
    assert not [c for c in world.rdc_calls() if c[:2] == ["ops", "down"]]
    assert not [c for c in world.rdc_calls() if c[:2] == ["ops", "up"]]
    assert world.running == [BRIDGE, WORKER]


SCENARIOS = {
    "skip-teardown": scenario_crash_mid_v13,
    "pass-on-zero-steps": scenario_zero_assertions_is_not_verified,
    "print-token": scenario_token_never_written,
    "down-reused-fleet": scenario_reused_fleet_is_never_downed,
}


def load_mutant(name: str, where: pathlib.Path) -> types.ModuleType:
    """The module with one source edit applied, imported from a copy under `where`."""
    source = pathlib.Path(vm_check.__file__).read_text()
    old, new = MUTANTS[name]
    assert source.count(old) == 1, "mutant %s no longer matches exactly one place" % name
    module_name = "vm_check_mutant_%s" % name.replace("-", "_")
    path = where / ("%s.py" % module_name)
    path.write_text(source.replace(old, new))
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- the flow


def test_a_clean_run_is_verified_and_its_receipt_admits_the_tree(tmp_path: pathlib.Path) -> None:
    world = make_world(
        tmp_path,
        extra_repos=(
            "%s:vmc-10141500-abcdef-a" % PARENT,
            "%s:vmc-10141750-abcdef-b" % PARENT,
            "other:vmc-10141500-abcdef-a",
            "%s:keepme" % PARENT,
        ),
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert "vm:check VERIFIED" in out
    assert receipt
    assert receipt_mod.validate(receipt) == []
    assert receipt["status"] == receipt_mod.VERIFIED
    assert receipt["renet"] == {
        "pointer": PTR,
        "checkout": PTR,
        "built": PTR,
        "modified": False,
        "deployed": PTR,
    }
    assert receipt["fleet"]["landlock"] == {"status": "enforced", "abi": "6"}
    assert receipt["teardown"] == {"ok": True, "leftovers": []}
    assert receipt_mod.admit(world.root, TREE, DIGEST).ok
    ids = {s["id"] for s in receipt["steps"]}
    assert {
        "P0",
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "V1.1",
        "V1.2",
        "V1.3",
        "V1.4",
        "V1.5",
        "V1.6",
        "V1.7",
        "T",
    } <= ids
    # P5 swept only the parent's stale fork; the fresh one, the other parent's and a non-vmc tag stay.
    deleted = [c[2] for c in world.rdc_calls() if c[:2] == ["repo", "delete"]]
    assert deleted[0] == "%s:vmc-10141500-abcdef-a" % PARENT
    assert "%s:vmc-10141750-abcdef-b" % PARENT in world.repos
    assert "other:vmc-10141500-abcdef-a" in world.repos
    assert "%s:keepme" % PARENT in world.repos
    # This run's two forks are gone, the vscode alias cleaned, the lock free.
    assert [f for f in world.repos if f.startswith(PARENT + ":vmc-1014180")] == []
    assert any(c[:2] == ["vscode", "cleanup"] for c in world.rdc_calls())
    assert lock_is_free(tmp_path)
    # Nothing touched the agent-mode variables.
    for env in world.envs:
        for name in ("REDIACC_AGENT", "CLAUDECODE"):
            assert name not in env
        assert not [k for k in env if k.startswith("REDIACC_ALLOW_")]


def test_a_writable_neighbour_fails_v12_and_still_tears_down(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, ro_breach=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    assert receipt["status"] == receipt_mod.FAILED
    assert receipt["reason"]["class"] == "step-failed"
    assert receipt["reason"]["detail"].startswith("V1.2")
    assert world.forks_left() == []
    assert not receipt_mod.admit(world.root, TREE, DIGEST).ok


def test_an_exception_mid_v13_still_deletes_both_forks_and_releases_the_lock(
    tmp_path: pathlib.Path,
) -> None:
    scenario_crash_mid_v13(vm_check, tmp_path)


def test_a_reused_fleet_never_receives_ops_down(tmp_path: pathlib.Path) -> None:
    scenario_reused_fleet_is_never_downed(vm_check, tmp_path)


def test_the_minted_token_is_absent_from_every_byte_written(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_token_never_written(vm_check, tmp_path, capsys)


def test_a_valid_stored_token_mints_nothing(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, stored_ok=True)
    account = FakeAccount()
    rc, out, _ = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert account.minted == 0
    assert all("REDIACC_TOKEN" not in e for e in world.envs)


def test_a_cold_fleet_is_started_with_the_image_and_brought_down(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, running=())
    rc, out, receipt = run_check(tmp_path, world, "--os", "ubuntu-24.04")
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["fleet"]["mode"] == vm_check.COLD
    calls = world.rdc_calls()
    assert ["ops", "up", "--basic", "--os", "ubuntu-24.04"] in calls
    assert calls[-1] == ["ops", "down"]
    assert world.running == []


def test_zero_assertions_is_never_verified(tmp_path: pathlib.Path) -> None:
    scenario_zero_assertions_is_not_verified(vm_check, tmp_path)


def hold_lock(tmp_path: pathlib.Path) -> int:
    fd = os.open(tmp_path / "vm-check.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.pwrite(fd, json.dumps({"pid": 4242, "session": "peer0001", "since": "x"}).encode(), 0)
    return fd


NOT_VERIFIED_CASES: dict[str, dict[str, Any]] = {
    "renet-build-mismatch": {"modified": True, "rebuild_fixes": False},
    "no-kvm": {"kvm": False},
    "fleet-unavailable": {"running": (BRIDGE,)},
    "fleet-os-mismatch": {"os_release": "ubuntu 22.04"},
    "worker-not-in-config": {"machines": []},
    "account-unavailable": {},
    "parent-grand-missing": {"grands": ("other-grand",)},
    "agent-policy-refused": {"refuse_fork": True},
    "vscode-absent": {"vscode": False},
    "teardown-failed": {"undeletable_suffix": "-b"},
    "interrupted": {"signal_on": "cat /proc/self/cgroup"},
}


@pytest.mark.parametrize("cls", sorted(NOT_VERIFIED_CASES))
def test_each_not_verified_class(tmp_path: pathlib.Path, cls: str) -> None:
    over = dict(NOT_VERIFIED_CASES[cls])
    argv: list[str] = []
    account = FakeAccount()
    if cls == "fleet-os-mismatch":
        argv = ["--os", "ubuntu-24.04"]
    if cls == "account-unavailable":
        account = FakeAccount(healthy=False)
    world = make_world(tmp_path, **over)
    rc, out, receipt = run_check(tmp_path, world, *argv, account=account)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["status"] == receipt_mod.NOT_VERIFIED
    assert receipt["reason"]["class"] == cls, receipt["reason"]
    assert "NOT VERIFIED (%s)" % cls in out
    assert lock_is_free(tmp_path)
    if cls == "teardown-failed":
        assert receipt["teardown"]["ok"] is False
        assert any(x.endswith("-b") for x in receipt["teardown"]["leftovers"])
    else:
        assert world.forks_left() == []
    if cls == "renet-build-mismatch":
        assert ["--version"] in world.rdc_calls()
    if cls == "parent-grand-missing":
        assert "other-grand" in receipt["reason"]["detail"]
        assert not [c for c in world.rdc_calls() if c[:2] == ["repo", "create"]]
    if cls == "agent-policy-refused":
        assert "agent mode" in receipt["reason"]["detail"]


def test_fleet_busy_names_the_holder_and_creates_nothing(tmp_path: pathlib.Path) -> None:
    fd = hold_lock(tmp_path)
    try:
        world = make_world(tmp_path)
        rc, out, receipt = run_check(tmp_path, world)
    finally:
        os.close(fd)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "fleet-busy"
    assert "pid 4242, session peer0001" in receipt["reason"]["detail"]
    assert world.rdc_calls() == []
    assert "nothing to tear down" in out


def test_a_failed_cold_start_quotes_the_exit_and_downs_what_it_started(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, running=(), ops_up_rc=3)
    rc, _, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED
    assert receipt["reason"]["class"] == "fleet-unavailable"
    assert "rc=3" in receipt["reason"]["detail"]
    assert "domain failed to start" in receipt["reason"]["detail"]
    assert world.rdc_calls()[-1] == ["ops", "down"]


def test_the_selftest_fires_and_touches_nothing(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, "--selftest")
    assert rc != 0
    assert "selftest fired as designed" in out
    assert receipt == {}
    assert world.calls == []


def test_the_selftest_reports_an_instrument_that_does_not_fire(tmp_path: pathlib.Path) -> None:
    mutant = load_mutant("pass-on-zero-steps", tmp_path)
    out = io.StringIO()
    assert mutant.selftest(out) != 0
    assert "SELFTEST DID NOT FIRE" in out.getvalue()


# --------------------------------------------------------------------------- --changed against a real git tree


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def fixture_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "README.md").write_text("x\n")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "init")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def test_changed_with_no_hit_prints_the_no_op_line_and_writes_no_receipt(
    tmp_path: pathlib.Path,
) -> None:
    root = fixture_repo(tmp_path)
    (root / "docs.md").write_text("only docs\n")
    world = World(root)
    rc, out, receipt = run_check(tmp_path, world, "--changed")
    assert rc == 0
    assert (
        "vm:check: no trigger path changed since origin/main (via origin/<branch>); nothing to verify"
        in out
    )
    assert receipt == {}
    assert not (root / receipt_mod.CACHE_DIR).exists()
    assert world.rdc_calls() == []
    assert lock_is_free(tmp_path)


def test_changed_with_a_hit_runs_and_records_the_hits(tmp_path: pathlib.Path) -> None:
    root = fixture_repo(tmp_path)
    remote = root / "packages/cli/src/remote"
    remote.mkdir(parents=True)
    (remote / "sync.ts").write_text("export {};\n")
    world = World(root)
    rc, out, receipt = run_check(tmp_path, world, "--changed")
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["trigger"]["base"] == "origin/main"
    assert receipt["trigger"]["hits"] == ["packages/cli/src/remote/sync.ts"]


# --------------------------------------------------------------------------- mutants


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_mutant_turns_its_scenario_red(tmp_path: pathlib.Path, name: str) -> None:
    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir()
    mutant = load_mutant(name, mutant_dir)
    try:
        with pytest.raises(AssertionError):
            SCENARIOS[name](mutant, tmp_path)
    finally:
        sys.modules.pop(mutant.__name__, None)


# --------------------------------------------------------------------------- helpers


def test_go_buildinfo_reads_revision_and_modified() -> None:
    text = (
        "bin/renet: go1.24\n\tpath\tx\n\tbuild\tvcs.revision=%s\n\tbuild\tvcs.modified=true\n" % PTR
    )
    assert vm_check.go_buildinfo(text) == (PTR, True)
    assert vm_check.go_buildinfo("") == ("", None)


@pytest.mark.parametrize(
    ("image", "os_id", "version", "ok"),
    [
        ("ubuntu-24.04", "ubuntu", "24.04", True),
        ("ubuntu-24.04", "ubuntu", "22.04", False),
        ("rocky-9", "rocky", "9.4", True),
        ("oracle-9", "ol", "9.3", True),
        ("debian-13", "ubuntu", "13", False),
        ("noversion", "ubuntu", "24.04", False),
    ],
)
def test_os_matches(image: str, os_id: str, version: str, ok: bool) -> None:
    assert vm_check.os_matches(image, os_id, version) is ok


def test_fork_tags_fit_the_label_grammar() -> None:
    for tag in vm_check.fork_tags("10141800", "abcdef"):
        assert vm_check.FORK_TAG.match(tag)
        assert len(tag) <= 63
        assert tag == tag.lower()


def test_stamp_age_takes_the_year_that_puts_the_stamp_in_the_past() -> None:
    assert vm_check.stamp_age_s("10141700", NOW) == 3600
    # 31 Dec read on 14 Oct is last year's.
    age = vm_check.stamp_age_s("12312300", NOW)
    assert age is not None
    assert age > 200 * 86400
    assert vm_check.stamp_age_s("13401200", NOW) is None


def test_lock_path_prefers_an_owned_runtime_dir(tmp_path: pathlib.Path) -> None:
    assert vm_check.lock_path({"XDG_RUNTIME_DIR": str(tmp_path)}) == tmp_path / vm_check.LOCK_NAME
    fallback = vm_check.lock_path({"XDG_RUNTIME_DIR": str(tmp_path / "absent")})
    assert fallback.name in (vm_check.LOCK_NAME, "rediacc-vm-check-%d.lock" % os.getuid())


def test_the_npm_script_and_the_drill_table_name_this_module() -> None:
    root = paths.repo_root()
    scripts = json.loads((root / "package.json").read_text())["scripts"]
    assert scripts["vm:check"] == "PYTHONPATH=.ci python3 -m rediacc_ci.drills.vm_check"
    assert run_verbs.DRILL_MODULES["vmcheck"] == "rediacc_ci.drills.vm_check"
    assert "id: 'vm:check'" in (root / "scripts/ci-runner/manifest.ts").read_text()

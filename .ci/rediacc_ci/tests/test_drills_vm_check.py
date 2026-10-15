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
import re
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
PROD_IP = "203.0.113.7"
GATEWAY = "http://localhost:48123"
TOKEN_REQUIRED = (
    "Subscription token required. Either set REDIACC_SUBSCRIPTION_TOKEN env var, "
    "or run `rdc subscription login` in your terminal."
)
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
    "create-on-any-worker": (
        "            if not is_ops_vm_ip(ip):\n",
        "            if False:\n",
    ),
    "mint-under-default-config": (
        "        self.dev_config = True\n",
        "        self.dev_config = False\n",
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
        # Two configs, as on the host: the operator's default one and the dev one `./rdc.sh` selects under RDC_DEV=1. `machines` and `cli_key` describe the default config; the dev config starts as a freshly seeded dev.json (no machine, no key) unless `dev_machines` and `dev_key` say otherwise.
        self.machines = over.pop("machines", [{"name": "vm11", "ip": WORKER}])
        self.dev_machines = list(over.pop("dev_machines", ()))
        # A `machine list` refusal in the dev config only, e.g. "Decryption failed".
        self.dev_list_err = over.pop("dev_list_err", "")
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
        self.sftp_refusal = over.pop("sftp_refusal", "remote open: Permission denied")
        self.minted_check_err = over.pop("minted_check_err", "")
        # The `repo create` answer: rc and the CLI's JSON error message when it fails.
        self.create_rc = over.pop("create_rc", 0)
        self.create_err = over.pop("create_err", "")
        # False: the worker has no BTRFS datastore until `machine setup` runs; `setup_rc` is that command's answer.
        self.datastore = over.pop("datastore", True)
        self.setup_rc = over.pop("setup_rc", 0)
        self.gateway = over.pop("gateway", GATEWAY)
        # "yes" (the config holds a key the VMs authorize), "no" (empty credentials) or "wrong" (a key they reject).
        self.cli_key = over.pop("cli_key", "yes")
        self.dev_key = over.pop("dev_key", "no")
        self.key_set: list[str] = []
        # The config each `config ssh set` and `machine add` wrote, in call order.
        self.written_in: list[str] = []
        self.add_rc = over.pop("add_rc", 0)
        # "ok", "fail" (show exits non-zero) or "nodata" (show exits 0 with no data.embedded).
        self.key_show = over.pop("key_show", "ok")
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

    @staticmethod
    def config_of(env: dict[str, str]) -> str:
        """The config `./rdc.sh` selects: RDC_DEV=1 is the dev one, anything else the default."""
        return "dev" if env.get("RDC_DEV") == "1" else "default"

    def _machines(self, env: dict[str, str]) -> list[dict[str, str]]:
        return self.dev_machines if self.config_of(env) == "dev" else self.machines

    def _key(self, env: dict[str, str]) -> str:
        return self.dev_key if self.config_of(env) == "dev" else self.cli_key

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
            if self.dev_list_err and self.config_of(env) == "dev":
                return self._json_error(1, self.dev_list_err)
            return vm_check.Result(0, json.dumps({"success": True, "data": self._machines(env)}))
        if head == ("machine", "add"):
            if self.add_rc:
                return self._json_error(self.add_rc, "config is locked")
            self.written_in.append(self.config_of(env))
            self._machines(env).append({"name": args[2], "ip": args[args.index("--ip") + 1]})
            return ok
        if head == ("machine", "scan-keys"):
            if args[2] not in [m["name"] for m in self._machines(env)]:
                return vm_check.Result(1, "", 'Machine "%s" not found' % args[2])
            return ok
        if head == ("machine", "setup"):
            if self.setup_rc:
                return self._json_error(self.setup_rc, "renet install failed")
            self.datastore = True
            return ok
        if head == ("subscription", "status"):
            if self._undecryptable(env):
                return vm_check.Result(1, "", "Decryption failed")
            if self.stored_ok or (self._minted(env) and not self.minted_check_err):
                return vm_check.Result(0, '{"success":true}')
            return vm_check.Result(1, "", self.minted_check_err or "Unauthorized")
        if head == ("repo", "create"):
            # The CLI's provisioning pre-flight: a token from the env or the config, checked on the server it names.
            if self._undecryptable(env):
                return self._json_error(1, "Decryption failed")
            if not (self.stored_ok or self._minted(env)):
                return self._json_error(2, TOKEN_REQUIRED)
            if not self.datastore:
                return self._json_error(
                    1,
                    "Machine '%s' datastore at /mnt/rediacc is not BTRFS (found: ). Run 'rdc machine setup <name>' to initialize the BTRFS datastore."
                    % WORKER,
                )
            if self.create_rc:
                return self._json_error(self.create_rc, self.create_err)
            self.repos[args[2]] = "guid-" + args[2]
            return vm_check.Result(0, json.dumps({"success": True, "data": {"name": args[2]}}))
        if head == ("config", "ssh") and args[2:3] == ["show"]:
            if self.key_show == "fail":
                return vm_check.Result(1, "", "config is locked")
            if self.key_show == "nodata":
                return vm_check.Result(0, json.dumps({"success": True, "data": {}}))
            if self.key_show == "notjson":
                return vm_check.Result(0, "config ssh: ok\n")
            embedded = "no" if self._key(env) == "no" else "yes"
            return vm_check.Result(0, json.dumps({"success": True, "data": {"embedded": embedded}}))
        if head == ("config", "ssh") and args[2:3] == ["set"]:
            self.key_set.append(args[args.index("--key") + 1])
            self.written_in.append(self.config_of(env))
            if self.config_of(env) == "dev":
                self.dev_key = "yes"
            else:
                self.cli_key = "yes"
            return ok
        if head == ("repo", "list") and self._key(env) != "yes":
            envelope = {
                "success": False,
                "errors": [
                    {
                        "code": "LOCAL_EXECUTION_FAILED",
                        "message": "SSH connection error: All configured authentication methods failed",
                    }
                ],
            }
            return vm_check.Result(1, json.dumps(envelope), "Listing repositories...\n")
        if head == ("repo", "list"):
            return vm_check.Result(0, json.dumps({"success": True, "data": self._repo_data()}))
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

    def _repo_data(self) -> list[dict[str, str]]:
        return [
            {"name": n, "guid": g, "networkId": "29%02d" % i}
            for i, (n, g) in enumerate(sorted(self.repos.items()))
        ]

    def _minted(self, env: dict[str, str]) -> bool:
        """The minted token counts only on the gateway that minted it, read under the dev config that carries that gateway's E2E key."""
        return (
            env.get("REDIACC_TOKEN") == TOKEN
            and env.get("REDIACC_ACCOUNT_SERVER") == self.gateway
            and self.config_of(env) == "dev"
        )

    def _undecryptable(self, env: dict[str, str]) -> bool:
        """The live 05:4xZ failure: a dev-gateway response read under the default config, whose E2E key is the production server's."""
        return env.get("REDIACC_ACCOUNT_SERVER") == self.gateway and self.config_of(env) != "dev"

    @staticmethod
    def _json_error(rc: int, message: str) -> vm_check.Result:
        envelope = {"success": False, "errors": [{"code": "ERROR", "message": message}]}
        return vm_check.Result(rc, json.dumps(envelope), "Creating repository...\n")

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
            mine_nid = next(e["networkId"] for e in self._repo_data() if e["name"] == ref)
            return vm_check.Result(0, "0::/renet-exec-%s.scope\n" % mine_nid)
        if command == "renet sandbox-exec --detect":
            return vm_check.Result(0, "Status: enforced\nABI: 6\n")
        return vm_check.Result(0)

    def _sftp(self, batch: str) -> vm_check.Result:
        a = "guid-" + next(t for t in self.forked if t.endswith("-a"))
        line = batch.strip()
        if line.startswith("put") and "/%s/" % a in line:
            return vm_check.Result(0)
        return vm_check.Result(1, "", self.sftp_refusal)

    # ------------------------------------------------------------------ views

    def rdc_calls(self) -> list[list[str]]:
        return [c[1:] for c in self.calls if c[0] == self.rdc_path]

    def forks_left(self) -> list[str]:
        return [n for n in self.repos if ":vmc-" in n]


class FakeAccount:
    def __init__(
        self,
        healthy: bool = True,
        token: str = TOKEN,
        mint_error: str = "",
        server: str = GATEWAY,
    ) -> None:
        self.mint_error = mint_error
        self.server = server
        self.password = ""
        self.healthy = healthy
        self.token = token
        self.minted = 0

    def gateway_healthy(self) -> bool:
        return self.healthy

    def mint(self, password: str) -> str:
        assert len(password) >= 24
        self.minted += 1
        self.password = password
        if self.mint_error:
            raise OSError(self.mint_error % password)
        return self.token

    def server_url(self) -> str:
        return self.server


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


NON_OPS_MACHINES = [{"name": "vm11", "ip": WORKER}, {"name": "prod-1", "ip": PROD_IP}]


def scenario_a_non_ops_worker_never_gets_a_grand_created(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    world = make_world(tmp_path, grands=("other-grand",), machines=NON_OPS_MACHINES, stored_ok=True)
    rc, out, receipt = run_check(tmp_path, world, "--machine", "prod-1", m=m)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "parent-grand-missing", receipt["reason"]
    assert not [c for c in world.rdc_calls() if c[:2] == ["repo", "create"]]
    assert "the operator creates it once" in receipt["reason"]["detail"]
    assert PROD_IP in receipt["reason"]["detail"]


def scenario_minted_token_runs_under_the_dev_config(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """The 05:4xZ failure, rebuilt: a token minted on the dev gateway is checked under the default config, whose E2E key is production's, and `subscription status` fails "Decryption failed"."""
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["status"] == receipt_mod.VERIFIED


SCENARIOS = {
    "create-on-any-worker": scenario_a_non_ops_worker_never_gets_a_grand_created,
    "mint-under-default-config": scenario_minted_token_runs_under_the_dev_config,
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


def test_a_refused_minted_token_check_never_echoes_the_token(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, minted_check_err="bad credential %s rejected" % TOKEN)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-unavailable"
    assert "refused the minted token" in receipt["reason"]["detail"]
    assert TOKEN not in out
    assert TOKEN not in json.dumps(receipt)


def test_a_failed_mint_never_echoes_the_password(tmp_path: pathlib.Path) -> None:
    account = FakeAccount(mint_error="login failed for password %s")
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-unavailable"
    assert account.password
    assert account.password not in out
    assert account.password not in json.dumps(receipt)


def test_a_negative_sftp_leg_needs_a_denial_not_just_a_non_zero_exit(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, sftp_refusal="Connection closed")
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    refused = [
        s
        for s in receipt["steps"]
        if s["id"] == "V1.7" and "refused" in s["desc"] and s["verdict"] == "FAIL"
    ]
    assert len(refused) == 2, receipt["steps"]


def test_a_failed_ssh_login_is_not_a_refusal(tmp_path: pathlib.Path) -> None:
    ssh_failure = (
        "rediacc@10.0.0.7: Permission denied (publickey,password,keyboard-interactive).\n"
        "Connection closed"
    )
    world = make_world(tmp_path, sftp_refusal=ssh_failure)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    refused = [
        s
        for s in receipt["steps"]
        if s["id"] == "V1.7" and "refused" in s["desc"] and s["verdict"] == "FAIL"
    ]
    assert len(refused) == 2, receipt["steps"]


# The searches run in a child under a generous deadline: a linear pattern answers in milliseconds even on a loaded runner, while a backtracking one does not finish "a" * 40 in hours, so the deadline separates the two without timing a single call against a tight bound.
LINEAR_DEADLINE_S = 60
LINEAR_CHILD = (
    "import re, sys\n"
    "pat = re.compile(sys.argv[1], re.IGNORECASE)\n"
    "for tail in ('a' * 40, 'a-' * 2000, 'ab,' * 2000, 'a' * 20000, '-,' * 2000):\n"
    "    if pat.search('user@host: Permission denied (' + tail):\n"
    "        sys.exit('matched an unterminated list: ' + tail[:8])\n"
    "print('linear')\n"
)


def test_ssh_auth_failure_pattern_is_linear_on_an_unterminated_method_list() -> None:
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", LINEAR_CHILD, vm_check.SSH_AUTH_FAILURE.pattern],
            capture_output=True,
            text=True,
            timeout=LINEAR_DEADLINE_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "SSH_AUTH_FAILURE backtracks: an unterminated method list did not finish in %d s"
            % LINEAR_DEADLINE_S
        )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "linear", proc.stdout
    assert vm_check.SSH_AUTH_FAILURE.search(
        "u@h: Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password)."
    )
    assert vm_check.SSH_AUTH_FAILURE.search("Permission denied (keyboard-interactive).")


# The method-list grammar the backtracking pattern accepted, kept small enough for it to answer at once: words of letters and hyphens, each optionally followed by a comma.
BACKTRACKING_METHOD_LIST = r"permission denied \((?:[a-z-]+,?)+\)"


def _short_lists(alphabet: str, longest: int) -> list[str]:
    out = [""]
    frontier = [""]
    for _ in range(longest):
        frontier = [s + c for s in frontier for c in alphabet]
        out += frontier
    return out


def test_ssh_auth_failure_accepts_every_method_list_the_old_grammar_did() -> None:
    old = re.compile(BACKTRACKING_METHOD_LIST, re.IGNORECASE)
    lists = _short_lists("a-,", 6)
    differ = [
        body
        for body in lists
        if bool(old.fullmatch("permission denied (%s)" % body))
        != bool(vm_check.SSH_AUTH_FAILURE.fullmatch("permission denied (%s)" % body))
    ]
    assert not differ, differ[:10]
    for line in ("u@h: Permission denied (publickey,).", "u@h: Permission denied (-x)."):
        assert vm_check.SSH_AUTH_FAILURE.search(line), line
        assert not vm_check.sftp_refused(line), line
    for line in ("u@h: Permission denied ().", "u@h: Permission denied (a,,b)."):
        assert not vm_check.SSH_AUTH_FAILURE.search(line), line


def test_sftp_refused_tells_a_server_refusal_from_an_ssh_login_failure() -> None:
    assert vm_check.sftp_refused('remote open("/mnt/x"): Permission denied')
    assert vm_check.sftp_refused('Couldn\'t setstat on "/x": Operation not permitted')
    assert vm_check.sftp_refused("remote open: Read-only file system")
    assert not vm_check.sftp_refused("u@h: Permission denied (publickey).")
    assert not vm_check.sftp_refused("Received disconnect: Too many authentication failures")
    assert not vm_check.sftp_refused("Connection closed")
    assert not vm_check.sftp_refused("")
    assert vm_check.sftp_refused(
        'u@h: Permission denied (publickey).\nremote open("/x"): Permission denied'
    )


def test_a_valid_stored_token_mints_nothing_and_keeps_the_default_config(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, stored_ok=True)
    account = FakeAccount()
    rc, out, _ = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert account.minted == 0
    assert all("REDIACC_TOKEN" not in e for e in world.envs)
    assert all("RDC_DEV" not in e for e in world.envs), (
        "a stored token never selects the dev config"
    )
    assert world.dev_machines == []
    assert "dev" not in world.written_in
    assert ["machine", "scan-keys", "vm11"] in world.rdc_calls()


def _rdc_envs(world: World) -> list[tuple[list[str], dict[str, str]]]:
    return [
        (c[1:], e) for c, e in zip(world.calls, world.envs, strict=True) if c[0] == world.rdc_path
    ]


def test_a_minted_token_runs_every_later_cli_call_under_the_dev_config(
    tmp_path: pathlib.Path,
) -> None:
    """2026-10-15T05:4xZ: the token minted on the dev gateway met the default config's production E2E key and `subscription status` failed "Decryption failed"."""
    world = make_world(tmp_path)
    default_machines = [dict(m) for m in world.machines]
    rc, out, _ = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    calls = _rdc_envs(world)
    first_status = next(i for i, (a, _e) in enumerate(calls) if a[:2] == ["subscription", "status"])
    # The stored-token probe reads the default config; everything after it reads the dev one.
    assert "RDC_DEV" not in calls[first_status][1]
    later = calls[first_status + 1 :]
    assert later
    assert all(e.get("RDC_DEV") == "1" for _a, e in later), [
        a for a, e in later if e.get("RDC_DEV") != "1"
    ]
    # The dev config got the worker and the key the ops VMs authorize; the default config is untouched.
    assert [
        "machine",
        "add",
        vm_check.OPS_WORKER_NAME,
        "--ip",
        WORKER,
        "--user",
        vm_check.vm_ssh.default_user({"HOME": str(tmp_path / "home")}),
    ] in [a for a, _e in later]
    assert ["machine", "scan-keys", vm_check.OPS_WORKER_NAME] in [a for a, _e in later]
    assert world.written_in == ["dev", "dev"], world.written_in
    assert world.dev_key == "yes"
    assert world.cli_key == "yes"
    assert world.machines == default_machines
    assert "registered it as %s" % vm_check.OPS_WORKER_NAME in out, out


def test_a_dev_config_already_holding_the_worker_registers_nothing(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, dev_machines=[{"name": "vm11", "ip": WORKER}], dev_key="yes")
    rc, out, _ = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert not [c for c in world.rdc_calls() if c[:2] == ["machine", "add"]]
    assert world.key_set == []
    assert ["machine", "scan-keys", "vm11"] in world.rdc_calls()


def test_a_machine_named_and_present_in_the_dev_config_is_used_as_is(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, dev_machines=[{"name": "devw", "ip": WORKER}], dev_key="yes")
    rc, out, _ = run_check(tmp_path, world, "--machine", "devw")
    assert rc == vm_check.EXIT_VERIFIED, out
    assert not [c for c in world.rdc_calls() if c[:2] == ["machine", "add"]]
    assert ["machine", "scan-keys", "devw"] in world.rdc_calls()
    assert _creates(world) == []


def test_an_unreadable_dev_config_is_account_unavailable_not_a_registration(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, dev_list_err="Decryption failed")
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-unavailable", receipt["reason"]
    assert "rc=1: Decryption failed" in receipt["reason"]["detail"]
    assert "machine add" not in receipt["reason"]["detail"]
    assert not [c for c in world.rdc_calls() if c[:2] == ["machine", "add"]]


def test_a_failed_dev_registration_is_worker_not_in_config(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, add_rc=1)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "worker-not-in-config", receipt["reason"]
    detail = receipt["reason"]["detail"]
    assert "./rdc.sh --dev machine add %s" % vm_check.OPS_WORKER_NAME in detail, detail
    assert "rc=1: config is locked" in detail, detail
    assert TOKEN not in out


def test_a_machine_named_but_absent_from_the_dev_config_names_the_command(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, "--machine", "vm11")
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "worker-not-in-config", receipt["reason"]
    assert "./rdc.sh --dev machine add vm11 --ip %s" % WORKER in receipt["reason"]["detail"]
    assert not [c for c in world.rdc_calls() if c[:2] == ["machine", "add"]]


def test_the_non_ops_scenario_is_green_unmutated(tmp_path: pathlib.Path) -> None:
    """A mutant scenario that fails for another reason proves nothing, so each one also passes on the real module."""
    scenario_a_non_ops_worker_never_gets_a_grand_created(vm_check, tmp_path)


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
    "worker-not-in-config": {"machines": [], "stored_ok": True},
    "account-unavailable": {},
    "parent-grand-missing": {
        "grands": ("other-grand",),
        "machines": NON_OPS_MACHINES,
        "stored_ok": True,
    },
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
    if cls == "parent-grand-missing":
        argv = ["--machine", "prod-1"]
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


def test_an_rdc_failure_is_named_by_its_json_error_not_its_progress_lines() -> None:
    """`-o json` puts the error on stdout and progress on stderr; the reason read stderr alone (2026-10-14T23:53Z)."""
    envelope = json.dumps(
        {
            "success": False,
            "errors": [{"code": "LOCAL_EXECUTION_FAILED", "message": "SSH connection error"}],
        }
    )
    res = vm_check.Result(1, envelope, 'Starting CLI\nListing repositories on "w"...\n')
    assert vm_check.rdc_failure(res) == "SSH connection error"
    assert vm_check.rdc_failure(vm_check.Result(1, "", "a\nb\nboom\n")) == "a | b | boom"
    assert vm_check.rdc_failure(vm_check.Result(1, "plain failure\n", "")) == "plain failure"
    empty = vm_check.Result(3, json.dumps({"success": False, "data": {"x": 1}}), "")
    assert vm_check.rdc_failure(empty) == "rc=3 with no error in the CLI's JSON envelope"


def test_a_config_with_no_ssh_key_gets_the_key_the_vms_authorize(tmp_path: pathlib.Path) -> None:
    """Empty credentials made the CLI offer ~/.ssh/id_ed25519 and repo list fail auth (2026-10-15)."""
    world = make_world(tmp_path, cli_key="no", stored_ok=True)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert len(world.key_set) == 1, world.key_set
    assert world.written_in == ["default"], world.written_in
    assert world.key_set[0].endswith("/.renet/staging/.ssh/id_rsa"), world.key_set
    assert "the config had no SSH key; set %s," % world.key_set[0] in out, out


def test_a_config_holding_another_key_is_not_overwritten_and_names_the_fix(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, cli_key="wrong", stored_ok=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc != vm_check.EXIT_VERIFIED, out
    assert world.key_set == [], "a config with a key of its own is never overwritten"
    assert "NOT VERIFIED (worker-ssh-key)" in out, out
    assert "All configured authentication methods failed" in out, out
    assert "config ssh set --key" in out, out
    assert receipt.get("status") == "NOT_VERIFIED", receipt


def test_a_cold_run_missing_the_grand_on_another_worker_says_to_leave_a_warm_fleet(
    tmp_path: pathlib.Path,
) -> None:
    """A cold run's fresh VMs never hold the grand, and `ops down` removes them (2026-10-15T00:27Z); off the ops network the step stays the operator's."""
    world = make_world(tmp_path, running=(), grands=(), machines=NON_OPS_MACHINES, stored_ok=True)
    rc, out, _receipt = run_check(tmp_path, world, "--machine", "prod-1")
    assert rc != vm_check.EXIT_VERIFIED, out
    assert "NOT VERIFIED (parent-grand-missing)" in out, out
    assert "leave the fleet up for vm:check to reuse" in out, out
    assert "ops up --basic, then ./rdc.sh repo create" in out, out
    (tmp_path / "warm").mkdir(exist_ok=True)
    warm = make_world(tmp_path / "warm", grands=(), machines=NON_OPS_MACHINES, stored_ok=True)
    rc, out, _receipt = run_check(tmp_path / "warm", warm, "--machine", "prod-1")
    assert "NOT VERIFIED (parent-grand-missing)" in out, out
    assert "leave the fleet up" not in out, out


def _creates(world: World) -> list[list[str]]:
    return [c for c in world.rdc_calls() if c[:2] == ["repo", "create"]]


@pytest.mark.parametrize("stored_ok", [False, True])
def test_a_missing_grand_on_the_ops_worker_is_created_and_the_run_is_verified(
    tmp_path: pathlib.Path, stored_ok: bool
) -> None:
    """Operator ruling 2026-10-15: the ops VMs are development-only, so creating the grand there is the check's own step."""
    world = make_world(tmp_path, grands=(), stored_ok=stored_ok)
    account = FakeAccount()
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    # A minted token runs under the dev config, where the worker is registered as ops-worker.
    worker = "vm11" if stored_ok else vm_check.OPS_WORKER_NAME
    assert _creates(world) == [["repo", "create", PARENT, "-m", worker, "--size", "2G"]]
    assert PARENT in world.repos
    assert account.minted == (0 if stored_ok else 1)
    credential = "the config's stored token" if stored_ok else "the minted token"
    assert (
        "creating it with ./rdc.sh repo create %s -m %s --size 2G under %s"
        % (
            PARENT,
            worker,
            credential,
        )
        in out
    ), out
    rows = [r for r in receipt["steps"] if r["id"] == "P5"]
    assert len(rows) == 1, rows
    assert rows[0]["verdict"] == "ok"
    assert "created on %s (ops VM %s)" % (worker, WORKER) in rows[0]["desc"], rows[0]
    assert "operator" not in out
    assert TOKEN not in out
    assert TOKEN not in json.dumps(receipt)


def test_a_cold_ops_run_creates_the_grand_and_still_downs_its_fleet(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, running=(), grands=())
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert len(_creates(world)) == 1
    assert world.rdc_calls()[-1] == ["ops", "down"]
    assert "leave the fleet up" not in out, out


def test_a_failed_grand_create_is_not_verified_and_names_the_cli_error(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(
        tmp_path, grands=(), create_rc=1, create_err="Machine slot limit reached for this plan"
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "parent-grand-missing"
    detail = receipt["reason"]["detail"]
    assert "creating it on the ops VM failed" in detail, detail
    assert "rc=1: Machine slot limit reached for this plan" in detail, detail
    assert "Creating repository..." not in detail, detail
    assert world.forks_left() == []
    assert not [c for c in world.rdc_calls() if c[:2] == ["repo", "fork"]]


def test_a_worker_without_a_datastore_is_set_up_then_the_grand_is_created(
    tmp_path: pathlib.Path,
) -> None:
    """The 2026-10-15 live run: repo create refused 'datastore at /mnt/rediacc is not BTRFS' on a fresh ops VM."""
    world = make_world(tmp_path, grands=(), datastore=False)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    worker = vm_check.OPS_WORKER_NAME
    setups = [c for c in world.rdc_calls() if c[:2] == ["machine", "setup"]]
    assert setups == [["machine", "setup", worker]], setups
    assert len(_creates(world)) == 2
    assert PARENT in world.repos


def test_a_failed_datastore_setup_is_not_verified_and_names_it(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, grands=(), datastore=False, setup_rc=1)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "parent-grand-missing"
    assert "machine setup %s failed rc=1" % vm_check.OPS_WORKER_NAME in receipt["reason"]["detail"]
    assert len(_creates(world)) == 1


def test_a_minted_token_sent_to_the_wrong_server_never_creates(tmp_path: pathlib.Path) -> None:
    """The 05:00Z failure, rebuilt: a dev-minted token without its gateway is no credential, and P4 says so before P5 tries a create."""
    world = make_world(tmp_path, grands=())
    rc, out, receipt = run_check(
        tmp_path, world, account=FakeAccount(server="https://eu.rediacc.com")
    )
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-unavailable", receipt["reason"]
    assert _creates(world) == []


def test_the_minted_token_rides_with_its_gateway(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path)
    rc, out, _ = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    rdc_envs = [e for c, e in zip(world.calls, world.envs, strict=True) if c[0] == world.rdc_path]
    minted = [e for e in rdc_envs if e.get("REDIACC_TOKEN") == TOKEN]
    assert minted
    assert all(e.get("REDIACC_ACCOUNT_SERVER") == GATEWAY for e in minted)


def test_an_unknown_gateway_address_is_account_unavailable(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, account=FakeAccount(server=""))
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-unavailable"
    assert "address is unknown" in receipt["reason"]["detail"]


@pytest.mark.parametrize(
    ("ip", "ok"),
    [
        ("192.168.111.11", True),
        ("192.168.111.1", True),
        ("192.168.112.11", False),
        ("203.0.113.7", False),
        ("192.168.111.11.example.com", False),
        ("192.168.111", False),
        ("192.168.111.256", False),
        ("192.168.111.x", False),
        ("", False),
        ("::ffff:192.168.111.11", False),
    ],
)
def test_is_ops_vm_ip(ip: str, ok: bool) -> None:
    assert vm_check.is_ops_vm_ip(ip) is ok


@pytest.mark.parametrize(
    ("key_show", "says"),
    [
        ("fail", "config ssh show gave no key state (rc=1: config is locked)"),
        ("nodata", "config ssh show gave no key state (its JSON has no data.embedded)"),
        ("notjson", "config ssh show gave no key state (its output is not JSON)"),
    ],
)
def test_an_unreadable_key_state_changes_nothing_and_p5_judges(
    tmp_path: pathlib.Path, key_show: str, says: str
) -> None:
    world = make_world(tmp_path, key_show=key_show, stored_ok=True)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert world.key_set == [], "an unreadable key state must not set a key"
    assert says in out, out


def test_an_unreadable_key_state_on_a_keyless_config_sets_nothing_and_p5_names_the_key(
    tmp_path: pathlib.Path,
) -> None:
    """Review edb5f14e.2: with a config that really has no key, the early return must set nothing, so the run reaches P5 and stops at the ssh refusal with the fix named."""
    world = make_world(tmp_path, key_show="fail", cli_key="no", stored_ok=True)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc != vm_check.EXIT_VERIFIED, out
    assert world.key_set == [], "an unreadable key state must not set a key"
    assert "NOT VERIFIED (worker-ssh-key)" in out, out
    assert "config ssh set --key" in out, out

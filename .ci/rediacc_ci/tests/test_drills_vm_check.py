"""`rediacc_ci.drills.vm_check`: the whole flow driven through a fake host and a fake account, so no case reaches a VM.

`World` answers every command the check issues (git, go, `./rdc.sh`, the ssh probes, `sftp -b`, the four A1 npm suites and the three A2 drills) from an in-memory fleet and scripted `(rc, stdout)` answers. `FakeAccount` is the dev gateway, with the A0 verbs `gateway_state`, `restart` and `detach`; the A0 record lives under tmp_path. Each verdict class is produced by bending one thing in that world. The MUTANTS are source edits of the module; each one must turn its scenario red, which proves the scenario can fail, and each scenario also passes on the real module.
"""

from __future__ import annotations

import fcntl
import importlib.util
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest

from rediacc_ci import paths, well_known
from rediacc_ci.core import run_verbs
from rediacc_ci.drills import vm_check
from rediacc_ci.drills import vm_check_receipt as receipt_mod

if TYPE_CHECKING:
    import types

TREE = "a" * 40
HEAD = "e" * 40
PTR = "c" * 40
APTR = "b" * 40
HASH = "f" * 64
DIGEST = "d" * 64
ADIGEST = "9" * 64
OTHER_ADIGEST = "8" * 64
GATEWAY_PORT = "48123"
GATEWAY_STARTED = "1792000000"
DRILL_ENV_SCRUB = ("REDIACC_TOKEN", "REDIACC_ACCOUNT_SERVER", "RDC_DEV", "DRILL_EXPECT_NO_KEYRING")
DRILL_NAMES = ("universe", "transfer", "license")
A_STEPS = ("A1.1", "A1.2", "A1.3", "A1.4", "A0", "A2.1", "A2.2", "A2.3")
V_STEPS = ("P5", "V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "U1")


def stub_u1(check: Any) -> None:
    """The U1 step a fake-driven run gets: one ok assertion row and no VM call. The live step is `upgrade_converge.run`, and its CLI-free helpers are tested directly in test_drills_upgrade_converge.py."""
    check.check("U1", "stub U1: a renet upgrade converges the fleet", True)


def drill_passed(name: str, count: int = 12) -> tuple[int, str]:
    """A drill's real PASSED tail, colour escapes included (lib.Drill.summary on a tty)."""
    return (
        0,
        "  %d assertions: %d passed, 0 failed  (3s)\n  \x1b[0;32mdrill %s PASSED\x1b[0m\n"
        % (count, count, name),
    )


TOKEN = "tok-PLANTED-7f3a9c2e1b5d4a60"
NET = "192.168.111"
# The CLI's redirect pattern (packages/cli/src/utils/repo-context-guard.ts FILE_WRITE_PATTERNS).
FILE_WRITE = re.compile(r"\b(cat|echo|printf|base64)\b[^|;&]*>>?\s*(?!/dev/null\b)(?!&)\S")
BRIDGE = NET + ".1"
WORKER = NET + ".11"
PROD_IP = "203.0.113.7"
# This host's address on the VM network (wire.bridge_host), the one the worker reaches the gateway at; the minted token must name it.
HOST_ADDR = NET + ".254"
GATEWAY = "http://%s:48123" % HOST_ADDR
TOKEN_REQUIRED = (
    "Subscription token required. Either set REDIACC_SUBSCRIPTION_TOKEN env var, "
    "or run `rdc subscription login` in your terminal."
)
PARENT = "vmcheck-base"
# 2026-10-14T18:00:00Z
NOW = 1792000800.0

MUTANTS = {
    "only-writes-receipt-json": (
        "        if self.tree and (self.lock_lost or self.opts.only):\n",
        "        if self.tree and self.lock_lost:\n",
    ),
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
    # The 2026-10-15 V-step harness defects, one mutant per rule.
    "skip-write-guard-globally": (
        '            env["RDC_DEV"] = "1"\n',
        '            env["RDC_DEV"] = "1"\n        env[SKIP_FILE_WRITE_GUARD] = "1"\n',
    ),
    "write-guard-not-passed": (
        "            self._positive(ref, desc, command, WRITE_ROW_ENV)\n",
        "            self._positive(ref, desc, command)\n",
    ),
    "evidence-stdout-first": (
        '        return self.check("V1.3", "A: %s" % desc, ok, res, "" if ok else self.remote_evidence(res))\n',
        '        return self.check("V1.3", "A: %s" % desc, ok, res)\n',
    ),
    "no-compose-upload": (
        "        if self._upload_compose(ref):\n",
        "        if True:\n",
    ),
    "vi-assumed": (
        "        if probe.rc == 0 and probe.out.strip():\n",
        "        if True:\n",
    ),
    "link-expected-back": (
        "        expected = {k: v for k, v in sent.items() if k not in SYNC_DROPPED}\n",
        "        expected = dict(sent)\n",
    ),
    "sftp-alias-from-home": (
        '                [*SFTP_BATCH, "-F", str(config), "-b", str(batch), self.connection],\n',
        '                [*SFTP_BATCH, "-b", str(batch), self.connection],\n',
    ),
    "sftp-identity-not-copied": (
        "                value = str(copy)\n",
        "                value = str(identity)\n",
    ),
    "sftp-no-drive-translation": (
        "                identity = pathlib.Path(drive_path(value, drive_root))\n",
        "                identity = pathlib.Path(value)\n",
    ),
    "sftp-failure-not-denial": (
        "    if not path:\n        return False\n",
        "    if True:\n        return False\n",
    ),
    "file-write-refusal-unknown": ('    "File write detected",\n', ""),
    # PLAN-account-vm-check.md AV4: one mutant per account-phase rule.
    "skip-account-phase": (
        '        account = self.phases[SIDE_ACCOUNT]["required"]\n',
        "        account = False\n",
    ),
    "skipped-drill-passes": (
        '        return DRILL_SKIP, "rc=%d, a SKIPPED line or 0 assertions: %s" % (res.rc, last_lines(text))\n',
        '        return DRILL_OK, "rc=%d, a SKIPPED line or 0 assertions: %s" % (res.rc, last_lines(text))\n',
    ),
    "reuse-stale-gateway": (
        '        if record.get("account") != account:\n',
        "        if False:\n",
    ),
    "drill-env-leaks-token": (
        "        env = {k: v for k, v in self.environ.items() if k not in DRILL_ENV_SCRUB}\n",
        "        env = self.child_env()\n",
    ),
    "renet-steps-on-account-only": (
        '        renet = self.phases[SIDE_RENET]["required"]\n',
        "        renet = True\n",
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
        # This host's address on the VM network, None while no interface sits on it; `vm_net_after_up` is the address once `ops up` ran (a cold fleet creates the bridge).
        self.vm_net_addr = over.pop("vm_net_addr", HOST_ADDR)
        self.vm_net_after_up = over.pop("vm_net_after_up", HOST_ADDR)
        # Two configs, as on the host: the operator's default one and the dev one `./rdc.sh` selects under RDC_DEV=1. `machines` and `cli_key` describe the default config; the dev config starts as a freshly seeded dev.json (no machine, no key) unless `dev_machines` and `dev_key` say otherwise.
        self.machines = over.pop("machines", [{"name": "vm11", "ip": WORKER}])
        self.dev_machines = list(over.pop("dev_machines", ()))
        # A `machine list` refusal in the dev config only, e.g. "Decryption failed".
        self.dev_list_err = over.pop("dev_list_err", "")
        self.os_release = over.pop("os_release", "ubuntu 24.04")
        self.stored_ok = over.pop("stored_ok", False)
        self.repos: dict[str, str] = {g: "guid-" + g for g in over.pop("grands", (PARENT,))}
        # True: forks (made here or listed as extra repos) get real UUID guids (renet's shape), so T and the P5 sweep purge their licence state; `purge_rc` and `purge_out` are that purge's answer, and `purges` the scripts it was sent.
        self.uuid_forks = over.pop("uuid_forks", False)
        for name in over.pop("extra_repos", ()):
            self.repos[name] = (
                str(uuid.uuid5(uuid.NAMESPACE_OID, name))
                if self.uuid_forks
                else "guid-" + name.replace(":", "-")
            )
        self.ro_breach = over.pop("ro_breach", False)
        self.purge_rc = over.pop("purge_rc", 0)
        self.purge_out = over.pop("purge_out", "PURGED\n")
        self.purges: list[str] = []
        self.vscode = over.pop("vscode", True)
        self.refuse_fork = over.pop("refuse_fork", False)
        self.undeletable_suffix = over.pop("undeletable_suffix", "")
        # A delete that answers rc 0 and leaves the fork listed, and a repo list that fails once any delete ran (review a6e93fb9.2).
        self.sticky_suffix = over.pop("sticky_suffix", "")
        self.list_fails_after_delete = over.pop("list_fails_after_delete", False)
        self.deleted_any = False
        self.crash_on = over.pop("crash_on", "")
        self.signal_on = over.pop("signal_on", "")
        # None: sftp-server's real answer to a refused leg, the bare `Failure` status line naming the path (2026-10-15 live run); a string replaces it.
        self.sftp_refusal = over.pop("sftp_refusal", None)
        # The live ops VM image: the CLI's file-write guard refuses `echo x > f` through `term connect` unless REDIACC_SKIP_FILE_WRITE_GUARD=1 (False: a CLI that no longer honours the variable), vi is absent, and the grand holds no compose file.
        self.write_guard_honours_skip = over.pop("write_guard_honours_skip", True)
        self.vi = over.pop("vi", False)
        # The vi probe's exit when vi is absent: 1 is `command -v` saying so, anything else a probe that failed.
        self.vi_probe_rc = over.pop("vi_probe_rc", 1)
        # A planted remote failure for `chmod 600` in the mount: (stdout, stderr), stdout being the CLI's JSON envelope.
        self.chmod_fail = over.pop("chmod_fail", None)
        # "wsl": `vscode connect` writes the alias into the Windows home under the drive mounts with C:/ paths and a 0777 key, as getSSHHome() does on WSL; "linux": into $HOME with a 0600 key.
        self.alias_home = over.pop("alias_home", "wsl")
        # False: `vscode connect` printed its URI but wrote no alias block.
        self.alias_written = over.pop("alias_written", True)
        # True: a sync that carries symlinks across, the confinement property V1.5 asserts lost.
        self.sync_keeps_links = over.pop("sync_keeps_links", False)
        # Directory owners by (fork tag, path under the mount); an absent entry is whatever the sync created. `root_parents` plants the bug: a sync that leaves the directories it creates root-owned.
        self.owners: dict[tuple[str, str], str] = {}
        self.root_parents = over.pop("root_parents", False)
        self.written: set[str] = set()
        self.minted_check_err = over.pop("minted_check_err", "")
        # The `repo create` answer: rc and the CLI's JSON error message when it fails.
        self.create_rc = over.pop("create_rc", 0)
        self.create_err = over.pop("create_err", "")
        # True: the local config still lists the grand although the worker has none (`ops down` destroyed the VM); `repo create` then refuses "already exists in config" until `repo delete --archive-config` archives the entry. `forget_rc` is that delete's answer.
        self.config_has_parent = over.pop("config_has_parent", False)
        self.forget_rc = over.pop("forget_rc", 0)
        self.forget_keeps = over.pop("forget_keeps", False)
        # False: the worker has no BTRFS datastore until `machine setup` runs; `setup_rc` is that command's answer.
        self.datastore = over.pop("datastore", True)
        self.setup_rc = over.pop("setup_rc", 0)
        self.gateway = over.pop("gateway", GATEWAY)
        # Further addresses the same gateway answers at (its loopback one), for the cold-fleet path that mints on localhost first.
        self.gateways = {self.gateway, *over.pop("also_gateways", ())}
        # "yes" (the config holds a key the VMs authorize), "no" (empty credentials) or "wrong" (a key they reject).
        self.cli_key = over.pop("cli_key", "yes")
        self.dev_key = over.pop("dev_key", "no")
        self.key_set: list[str] = []
        # The config each `config ssh set` and `machine add` wrote, in call order.
        self.written_in: list[str] = []
        self.add_rc = over.pop("add_rc", 0)
        # "ok", "fail" (show exits non-zero), "nodata" (show exits 0 with no data.embedded), "notjson", or the JSON of the wrong shape "array" ([]) and "datastr" ({"data": "x"}).
        self.key_show = over.pop("key_show", "ok")
        # The A1 suites by step id and the A2 drills by name: scripted (rc, stdout); absent is a green answer.
        self.suites: dict[str, tuple[int, str]] = dict(over.pop("suites", {}))
        self.drills: dict[str, tuple[int, str]] = dict(over.pop("drills", {}))
        # The private/account checkout: initialized or not, and its HEAD.
        self.account_checked_out = over.pop("account_checked_out", True)
        self.account_checkout = over.pop("account_checkout", APTR)
        assert not over, over
        self.store = root / "remote-store"
        self.mnt = root / "mnt"
        self.calls: list[list[str]] = []
        self.forked: list[str] = []
        self.envs: list[dict[str, str]] = []
        self.mono = 0.0

    # ------------------------------------------------------------------ Host

    def exists(self, path: str) -> bool:
        if path == "/dev/kvm":
            return self.kvm
        if path.endswith("private/account/.git"):
            return self.account_checked_out
        return os.path.exists(path)

    def which(self, name: str) -> str | None:
        return "/usr/bin/virsh" if name == "virsh" and self.kvm else None

    def sha256(self, path: pathlib.Path) -> str | None:
        return HASH if path.name == "renet" else None

    def drive_root(self) -> str:
        return str(self.mnt)

    def vm_net_address(self, net_base: str) -> str | None:
        assert net_base == NET
        return self.vm_net_addr

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
            if argv[2].endswith("private/account"):
                return vm_check.Result(0, self.account_checkout + "\n")
            return self._git(argv[3:])
        if argv[0] == "npm":
            step = next(s for s, script, _p in vm_check.ACCOUNT_SUITES if script == argv[4])
            rc, out = self.suites.get(step, (0, "suite %s green\n" % argv[4]))
            return vm_check.Result(rc, out, "", 61000)
        if argv[1:2] == ["-m"] and argv[2].startswith("rediacc_ci.drills."):
            name = argv[2].rsplit(".", 1)[1]
            rc, out = self.drills.get(name, drill_passed(name))
            return vm_check.Result(rc, out, "", 42000)
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
            if argv[-1].startswith("sudo install -d -o root -g root -m 755 "):
                path = shlex.split(argv[-1])[-1]
                guid, rel = path[len(vm_check.MOUNTS) + 1 :].split("/", 1)
                tag = next(n for n, g in self.repos.items() if g == guid).split(":", 1)[1]
                (self.store / tag / rel).mkdir(parents=True, exist_ok=True)
                self.owners[(tag, rel)] = "root:root"
                return vm_check.Result(0)
            return vm_check.Result(255, "", "unexpected probe")
        if argv[0] == "sftp":
            return self._sftp(argv)
        if argv[0] == self.rdc_path:
            return self._rdc(argv[1:], env or {})
        return vm_check.Result(127, "", "unknown command %s" % argv[0])

    # ------------------------------------------------------------------ answers

    def _git(self, args: list[str]) -> vm_check.Result:
        answers: dict[tuple[str, ...], str] = {
            ("rev-parse", "HEAD^{tree}"): TREE,
            ("rev-parse", "HEAD"): HEAD,
            ("rev-parse", "HEAD:private/renet"): PTR,
            ("rev-parse", "HEAD:private/account"): APTR,
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
            self.vm_net_addr = self.vm_net_after_up
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
            if self.config_has_parent and args[2] == PARENT:
                return self._json_error(1, 'Repository "%s" already exists in config' % args[2])
            if not self.datastore:
                return self._json_error(
                    1,
                    "Machine '%s' datastore at %s is not BTRFS (found: ). Run 'rdc machine setup <name>' to initialize the BTRFS datastore."
                    % (WORKER, well_known.DATASTORE_PATH),
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
            if self.key_show == "array":
                return vm_check.Result(0, "[]")
            if self.key_show == "datastr":
                return vm_check.Result(0, json.dumps({"success": True, "data": "x"}))
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
        if head == ("repo", "list") and self.list_fails_after_delete and self.deleted_any:
            return vm_check.Result(1, "", "list unavailable")
        if head == ("repo", "list"):
            return vm_check.Result(0, json.dumps({"success": True, "data": self._repo_data()}))
        if head == ("repo", "fork"):
            if self.refuse_fork:
                return vm_check.Result(
                    1, "", 'Cannot create a new grand repository "x" in agent mode.\nmore'
                )
            name = "%s:%s" % (args[2], args[4])
            self.repos[name] = (
                str(uuid.uuid5(uuid.NAMESPACE_OID, args[4]))
                if self.uuid_forks
                else "guid-" + args[4]
            )
            self.forked.append(args[4])
            return ok
        if head == ("repo", "delete") and "--archive-config" in args:
            if self.forget_rc:
                return vm_check.Result(self.forget_rc, "", "forget refused")
            self.config_has_parent = self.forget_keeps
            return ok
        if head == ("repo", "delete"):
            self.deleted_any = True
            if self.undeletable_suffix and args[2].endswith(self.undeletable_suffix):
                return vm_check.Result(1, "", "device busy")
            if self.sticky_suffix and args[2].endswith(self.sticky_suffix):
                return ok
            self.repos.pop(args[2], None)
            return ok
        if head == ("term", "connect"):
            if ":" not in args[2]:
                # A machine-level shell: only the licence purge goes there.
                self.purges.append(args[4])
                return vm_check.Result(self.purge_rc, self.purge_out)
            return self._shell(args[2], args[4], env)
        if args[:3] == ["repo", "sync", "upload"] and "--remote-file" in args:
            local = pathlib.Path(args[args.index("--local") + 1])
            rel = args[args.index("--remote-file") + 1]
            self._create_parents(args[3], rel.rsplit("/", 1)[0])
            shutil.copy(local, self.store / args[3].split(":", 1)[1] / rel)
            return ok
        if args[:3] == ["repo", "sync", "upload"] and "--remote" in args:
            self._create_parents(args[3], args[args.index("--remote") + 1])
        if args[:3] == ["repo", "sync", "upload"]:
            local = pathlib.Path(args[args.index("--local") + 1])
            # A privileged sync passes --no-links and the renet gateway refuses symlinks, so none lands.
            shutil.copytree(
                local,
                self._remote_dir(args[3], args),
                symlinks=True,
                ignore=lambda d, names: (
                    []
                    if self.sync_keeps_links
                    else [n for n in names if os.path.islink(os.path.join(d, n))]
                ),
                dirs_exist_ok=True,
            )
            return ok
        if args[:3] == ["repo", "sync", "download"]:
            local = pathlib.Path(args[args.index("--local") + 1])
            shutil.copytree(
                self._remote_dir(args[3], args), local, symlinks=True, dirs_exist_ok=True
            )
            return ok
        if head == ("vscode", "connect"):
            if not self.vscode:
                return vm_check.Result(
                    1,
                    "",
                    "VS Code not found.\n\nPlease install from: https://code.visualstudio.com/",
                )
            alias = "rediacc-default-vm11-" + args[2].replace(":", "-")
            if self.alias_written:
                self._write_alias(alias, env)
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
            and env.get("REDIACC_ACCOUNT_SERVER") in self.gateways
            and self.config_of(env) == "dev"
        )

    def _undecryptable(self, env: dict[str, str]) -> bool:
        """The live 05:4xZ failure: a dev-gateway response read under the default config, whose E2E key is the production server's."""
        return env.get("REDIACC_ACCOUNT_SERVER") == self.gateway and self.config_of(env) != "dev"

    @staticmethod
    def _json_error(rc: int, message: str) -> vm_check.Result:
        envelope = {"success": False, "errors": [{"code": "ERROR", "message": message}]}
        return vm_check.Result(rc, json.dumps(envelope), "Creating repository...\n")

    def _create_parents(self, ref: str, rel: str) -> None:
        """Every missing level of `rel` is created and takes the owner the sync gives it; an existing level keeps its own."""
        tag = ref.split(":", 1)[1]
        parts = rel.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            sub = "/".join(parts[:i])
            if not (self.store / tag / sub).exists():
                self.owners[(tag, sub)] = "root:root" if self.root_parents else "rediacc:rediacc"
        (self.store / tag / rel).mkdir(parents=True, exist_ok=True)

    def _remote_dir(self, ref: str, args: list[str]) -> pathlib.Path:
        """A repo's mount in the fake store; `--remote` absent is the mount root, as in buildSyncRemotePaths."""
        sub = args[args.index("--remote") + 1] if "--remote" in args else ""
        return self.store / ref.split(":", 1)[1] / sub

    def _write_alias(self, alias: str, env: dict[str, str]) -> None:
        if self.alias_home == "wsl":
            ssh_dir = self.mnt / "c" / "Users" / "dev" / ".ssh"
            spelled = "C:/Users/dev/.ssh"
            mode = 0o777
        else:
            ssh_dir = pathlib.Path(env["HOME"]) / ".ssh"
            spelled = str(ssh_dir)
            mode = 0o600
        ssh_dir.mkdir(parents=True, exist_ok=True)
        key = ssh_dir / "rediacc_key"
        key.write_text("PRIVATE KEY\n")
        key.chmod(mode)
        block = (
            "Host %s\n  HostName %s\n  User rediacc\n  Port 22\n"
            "  IdentityFile %s/rediacc_key\n  UserKnownHostsFile %s/known_hosts_rediacc\n"
            "  IdentitiesOnly yes\n  SetEnv REDIACC_REPOSITORY=x\n\n"
            % (alias, WORKER, spelled, spelled)
        )
        (ssh_dir / vm_check.ALIAS_CONFIG).write_text(block)

    def _shell(self, ref: str, command: str, env: dict[str, str]) -> vm_check.Result:
        tag = ref.split(":", 1)[1]
        mine = self.guid(tag)
        skip = env.get(vm_check.SKIP_FILE_WRITE_GUARD) == "1" and self.write_guard_honours_skip
        if FILE_WRITE.search(command) and not skip:
            return vm_check.Result(
                1,
                json.dumps({"success": False, "errors": [{"code": "VALIDATION", "message": "x"}]}),
                "File write detected (redirect). Use rdc repo sync instead:\n"
                "  rdc repo sync upload <repo-ref> --local FILE --remote PATH\n",
            )
        foreign = [g for n, g in self.repos.items() if g != mine and g in command]
        if command.startswith(("chmod 0777", "touch -m")) and foreign and not self.ro_breach:
            return vm_check.Result(1, "", "chmod: changing permissions: Read-only file system")
        written = re.fullmatch(r"echo vmc > (\S+)", command)
        if written:
            self.written.add(written.group(1))
            return vm_check.Result(0)
        if command.startswith("chmod 600 "):
            if self.chmod_fail:
                return vm_check.Result(1, *self.chmod_fail)
            path = command.split(" ", 2)[2]
            if path not in self.written:
                return vm_check.Result(
                    1, "", "chmod: cannot access '%s': No such file or directory" % path
                )
            return vm_check.Result(0)
        if command.endswith("renet compose -- ps"):
            if not (self.store / tag / vm_check.COMPOSE_FILE).is_file():
                return vm_check.Result(1, "", "Error: no compose file found")
            return vm_check.Result(0, "NAME IMAGE COMMAND SERVICE CREATED STATUS PORTS\n")
        if command == vm_check.VI_PROBE:
            return (
                vm_check.Result(0, "/usr/bin/vi\n")
                if self.vi
                else vm_check.Result(self.vi_probe_rc)
            )
        if command == vm_check.VI_WRITE:
            return vm_check.Result(0) if self.vi else vm_check.Result(127, "", "vi: not found")
        if command.startswith("test ! -L "):
            path = shlex.split(command)[3]
            rel = path.split("%s/%s/" % (vm_check.MOUNTS, mine), 1)[1]
            local = self.store / tag / rel
            return vm_check.Result(1 if local.is_symlink() or local.exists() else 0)
        if command.startswith("stat -c %U:%G -- "):
            path = shlex.split(command)[-1]
            rel = path.split("%s/%s/" % (vm_check.MOUNTS, mine), 1)[1]
            owner = self.owners.get((tag, rel))
            if owner is None:
                return vm_check.Result(
                    1, "", "stat: cannot statx '%s': No such file or directory" % path
                )
            return vm_check.Result(0, owner + "\n")
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

    def _sftp(self, argv: list[str]) -> vm_check.Result:
        alias = argv[-1]
        if "-F" not in argv:
            # A plain `sftp <alias>` reads ~/.ssh/config, which never holds the alias.
            return vm_check.Result(
                255,
                "",
                "ssh: Could not resolve hostname %s: Name or service not known\r\nConnection closed"
                % alias,
            )
        config = pathlib.Path(argv[argv.index("-F") + 1]).read_text()
        block = vm_check.alias_block(config, alias) or []
        identity = next((ln.split(" ", 1)[1] for ln in block if ln.startswith("IdentityFile ")), "")
        key = pathlib.Path(identity)
        if not identity or not key.is_file() or key.stat().st_mode & 0o077:
            return vm_check.Result(
                255, "", 'Load key "%s": bad permissions\nConnection closed' % identity
            )
        line = pathlib.Path(argv[argv.index("-b") + 1]).read_text().strip()
        echo = "sftp> %s\n" % line
        a = self.guid(next(t for t in self.forked if t.endswith("-a")))
        if line.startswith("put") and "/%s/" % a in line:
            return vm_check.Result(0, echo)
        if self.sftp_refusal is not None:
            return vm_check.Result(1, echo, self.sftp_refusal)
        verb = "dest open" if line.startswith("put") else "remote setstat"
        return vm_check.Result(1, echo, '%s "%s": Failure' % (verb, line.split()[-1]))

    # ------------------------------------------------------------------ views

    def rdc_calls(self) -> list[list[str]]:
        return [c[1:] for c in self.calls if c[0] == self.rdc_path]

    def suite_calls(self) -> list[tuple[list[str], dict[str, str]]]:
        """Every A1 npm argv and A2 drill argv, with its environment."""
        return [
            (c, e)
            for c, e in zip(self.calls, self.envs, strict=True)
            if c[0] == "npm" or (c[1:2] == ["-m"] and c[2].startswith("rediacc_ci.drills."))
        ]

    def drill_calls(self) -> list[list[str]]:
        return [c for c, _e in self.suite_calls() if c[0] != "npm"]

    def npm_calls(self) -> list[list[str]]:
        return [c for c, _e in self.suite_calls() if c[0] == "npm"]

    def forks_left(self) -> list[str]:
        return [n for n in self.repos if ":vmc-" in n]


class FakeAccount:
    def __init__(
        self,
        healthy: bool = True,
        token: str = TOKEN,
        mint_error: str = "",
        server: str | None = None,
        started: str = GATEWAY_STARTED,
        restart_error: str = "",
        healthy_after_restart: bool = True,
    ) -> None:
        self.mint_error = mint_error
        self.server = server
        self.password = ""
        self.healthy = healthy
        self.token = token
        self.minted = 0
        # Every host `server_url` was asked for, in order.
        self.hosts: list[str] = []
        self.note = "subscription kept (3 of 2000 issuances used this month)"
        # The A0 side: `.account-state`'s started= and gateway_port=, and what restart and detach were asked.
        self.port = GATEWAY_PORT
        self.started = started
        self.restart_error = restart_error
        self.healthy_after_restart = healthy_after_restart
        self.restarts: list[pathlib.Path] = []
        self.detached = 0

    def gateway_healthy(self) -> bool:
        return self.healthy

    def gateway_state(self) -> dict[str, Any]:
        return {"healthy": self.healthy, "port": self.port, "started": self.started}

    def restart(self, log_path: pathlib.Path) -> None:
        self.restarts.append(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("> account dev\nstarting gateway\nlistening on %s\n" % self.port)
        if self.restart_error:
            log_path.write_text("> account dev\nError: CRYPTO_KEYS is not set\nexit 1\n")
            raise vm_check.lib.GatewayError(self.restart_error)
        self.started = str(int(self.started or "0") + 600)
        self.healthy = self.healthy_after_restart

    def detach(self) -> None:
        self.detached += 1

    def mint(self, password: str) -> str:
        assert len(password) >= 24
        self.minted += 1
        self.password = password
        if self.mint_error:
            raise OSError(self.mint_error % password)
        return self.token

    def subscription_note(self) -> str:
        return self.note

    def server_url(self, host: str) -> str:
        """The gateway at `host`, as DrillAccount spells it; `server` replaces the answer."""
        self.hosts.append(host)
        if self.server is not None:
            return self.server
        return "http://%s:%s" % (host, GATEWAY_PORT)


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
    env: dict[str, str] | None = None,
    modified: bool | None = False,
    digest: str | None = ADIGEST,
) -> tuple[int, str, dict[str, Any]]:
    out = io.StringIO()
    environ = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ.get("PATH", ""),
        "VM_NET_BASE": NET,
        **(env or {}),
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
        account_modified_fn=lambda _root: modified,
        account_digest_fn=lambda _root: digest,
        u1_fn=stub_u1,
    )
    latest = world.root / receipt_mod.CACHE_DIR / receipt_mod.LATEST
    receipt = json.loads(latest.read_text()) if latest.exists() else {}
    # Case 12: every receipt a run leaves is one the guard can read.
    if receipt:
        assert receipt_mod.validate(receipt) == [], receipt_mod.validate(receipt)
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


def _rows(receipt: dict[str, Any], step: str) -> list[dict[str, Any]]:
    return [r for r in receipt["steps"] if r["id"] == step]


def scenario_only_write_rows_skip_the_file_write_guard(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """2026-10-15: every `echo vmc > ...` row was refused "File write detected (redirect)". The override rides those rows' children alone."""
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    carried = []
    for args, env in _rdc_envs(world):
        has = env.get(vm_check.SKIP_FILE_WRITE_GUARD) == "1"
        is_write = args[:2] == ["term", "connect"] and bool(FILE_WRITE.search(args[4]))
        assert has == is_write, (args, has)
        carried += [args[4]] if has else []
    assert len(carried) == 5, carried
    for desc in (
        "write ~",
        "write /tmp",
        "write /dev/shm",
        "write the mount",
        "chmod 600 in the mount",
    ):
        assert [r["verdict"] for r in _rows(receipt, "V1.3") if r["desc"] == "A: " + desc] == ["ok"]


def scenario_remote_stderr_reaches_the_evidence(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    envelope = json.dumps({"success": False, "errors": [{"code": "REMOTE", "message": "x" * 300}]})
    world = make_world(
        tmp_path,
        chmod_fail=(
            envelope,
            "chmod: changing permissions of 'vmc-mount': Operation not permitted",
        ),
    )
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_FAILED, out
    row = next(r for r in _rows(receipt, "V1.3") if r["desc"] == "A: chmod 600 in the mount")
    assert row["verdict"] == "FAIL"
    assert "Operation not permitted" in row["evidence"], row


def scenario_compose_file_is_uploaded_into_fork_a_only(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """2026-10-15: the empty grand made `renet compose -- ps` say "no compose file found"."""
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    uploads = [
        c
        for c in world.rdc_calls()
        if c[:3] == ["repo", "sync", "upload"] and "--remote" not in c and "--remote-file" not in c
    ]
    assert len(uploads) == 1, uploads
    assert uploads[0][3] == "%s:%s" % (PARENT, world.forked[0]), uploads
    assert world.forked[0].endswith("-a")
    assert not (world.store / PARENT).exists(), "the grand is never written"
    rows = {r["desc"]: r["verdict"] for r in _rows(receipt, "V1.3")}
    assert rows["A: renet compose -- ps"] == "ok", rows


def scenario_vi_absent_writes_with_sed_and_says_so(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """2026-10-15: the ops VM image (Ubuntu 24.04) ships no vi."""
    world = make_world(tmp_path, vi=False)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    commands = [c[4] for c in world.rdc_calls() if c[:2] == ["term", "connect"]]
    assert vm_check.VI_WRITE not in commands
    assert vm_check.SED_WRITE in commands
    row = next(r for r in _rows(receipt, "V1.3") if "sed -i" in r["desc"])
    assert row["verdict"] == "ok"
    assert "vi absent on ubuntu-24.04" in row["evidence"], row


def scenario_the_link_is_left_out_and_absent_on_the_remote(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """2026-10-15: `differ: link`; a privileged sync passes --no-links and the gateway refuses symlinks."""
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    rows = {r["desc"]: r["verdict"] for r in _rows(receipt, "V1.5")}
    assert rows["round trip is byte-identical (3 entries; link left out, never synced)"] == "ok", (
        rows
    )
    assert (
        rows["the link is absent on the remote (a privileged sync carries no symlink)"] == "ok"
    ), rows


def scenario_sftp_runs_on_the_alias_config_vscode_wrote(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """2026-10-15: plain `sftp <alias>` never read config_rediacc, which on WSL sits in the Windows home with C:/ paths and a 0777 key."""
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    legs = [c for c in world.calls if c[0] == "sftp"]
    assert len(legs) == 3, legs
    for argv in legs:
        assert "-q" not in argv
        config = pathlib.Path(argv[argv.index("-F") + 1])
        text = config.read_text()
        assert "C:/" not in text, text
        assert "UserKnownHostsFile %s/c/Users/dev/.ssh/known_hosts_rediacc" % world.mnt in text, (
            text
        )
        assert "SetEnv REDIACC_REPOSITORY=x" in text, text
        identity = text.split("IdentityFile ", 1)[1].split("\n", 1)[0]
        assert oct(os.stat(identity).st_mode & 0o777) == oct(0o600), identity
    assert all(r["verdict"] == "ok" for r in _rows(receipt, "V1.7")), _rows(receipt, "V1.7")


def scenario_sftp_failure_status_on_b_is_a_refusal(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """2026-10-15: sftp-server answers a refused put with `dest open "...": Failure` and a refused chmod with `remote setstat "...": Failure`."""
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    refused = [r for r in _rows(receipt, "V1.7") if "refused" in r["desc"]]
    assert [r["verdict"] for r in refused] == ["ok", "ok"], refused


def scenario_an_unhonoured_write_override_is_agent_policy_refused(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    world = make_world(tmp_path, write_guard_honours_skip=False)
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "agent-policy-refused", receipt["reason"]
    assert "File write detected" in receipt["reason"]["detail"]
    assert world.forks_left() == []


def account_only_world(tmp_path: pathlib.Path, **over: Any) -> World:
    """A real git tree whose only change is an account-side console path (D5: license.py selects the account phase)."""
    root = fixture_repo(tmp_path)
    drills = root / ".ci/rediacc_ci/drills"
    drills.mkdir(parents=True)
    (drills / "license.py").write_text("# changed\n")
    return World(root, **over)


def renet_only_world(tmp_path: pathlib.Path, **over: Any) -> World:
    """A real git tree whose only change is a renet-side console path."""
    root = fixture_repo(tmp_path)
    remote = root / "packages/cli/src/remote"
    remote.mkdir(parents=True)
    (remote / "sync.ts").write_text("export {};\n")
    return World(root, **over)


def _ids(receipt: dict[str, Any]) -> list[str]:
    return [s["id"] for s in receipt["steps"]]


def scenario_account_only_runs_the_account_phase_and_no_renet_step(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """Case 2: an account-only `--changed` runs A1, A0 and A2, creates and forks nothing, and its receipt admits the account side."""
    world = account_only_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, "--changed", m=m)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["trigger"]["sides"] == ["account"], receipt["trigger"]
    assert receipt["phases"] == {
        "account": {"required": True, "ran": True},
        "renet": {"required": False, "ran": False},
    }, receipt["phases"]
    calls = world.rdc_calls()
    assert not [c for c in calls if c[:2] in (["repo", "fork"], ["repo", "create"])], calls
    ids = _ids(receipt)
    for step in A_STEPS:
        assert [r["verdict"] for r in _rows(receipt, step)] == ["ok"], (step, ids)
    assert not [i for i in ids if i in V_STEPS], ids
    # P1 still ran, so the receipt's renet build is the pointer.
    assert receipt["renet"]["built"] == receipt["renet"]["pointer"] == PTR
    assert receipt["account"]["pointer"] == receipt["account"]["checkout"] == APTR
    assert receipt["account"]["modified"] is False
    assert receipt_mod.admit(world.root, TREE, DIGEST, {"account"}).ok
    refused = receipt_mod.admit(world.root, TREE, DIGEST, {"renet", "account"})
    assert refused.code == "phase-missing", refused


def scenario_a_skipped_drill_is_not_verified(m: types.ModuleType, tmp_path: pathlib.Path) -> None:
    """Case 7: universe exits 0 with SKIPPED, which proved nothing."""
    tail = "  \x1b[1;33mdrill universe SKIPPED\x1b[0m (0 assertions ran, so nothing was proven)\n"
    skipped = (0, "  0 assertions: 0 passed, 0 failed  (0s)\n" + tail)
    world = make_world(tmp_path, drills={"universe": skipped})
    rc, out, receipt = run_check(tmp_path, world, m=m)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-drill-skipped", receipt["reason"]
    assert "A2.1 drill universe" in receipt["reason"]["detail"], receipt["reason"]
    assert receipt["phases"]["account"]["ran"] is False
    # All three drills ran before the run stopped, and no renet step followed.
    assert len(world.drill_calls()) == 3, world.drill_calls()
    assert not [c for c in world.rdc_calls() if c[:2] == ["repo", "fork"]]


def write_gateway_record(root: pathlib.Path, account: str, started: str = GATEWAY_STARTED) -> None:
    folder = root / receipt_mod.CACHE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / vm_check.GATEWAY_RECORD).write_text(
        json.dumps({"port": GATEWAY_PORT, "started": started, "account": account})
    )


def read_gateway_record(root: pathlib.Path) -> dict[str, Any]:
    return json.loads((root / receipt_mod.CACHE_DIR / vm_check.GATEWAY_RECORD).read_text())


def scenario_a_gateway_older_than_the_account_worktree_is_restarted(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """Case 8, restarted: the running gateway is the recorded one, but private/account changed since it started, so it serves old code."""
    world = make_world(tmp_path)
    write_gateway_record(world.root, OTHER_ADIGEST)
    account = FakeAccount()
    rc, out, receipt = run_check(tmp_path, world, m=m, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert len(account.restarts) == 1, account.restarts
    assert account.restarts[0] == world.root / receipt_mod.CACHE_DIR / vm_check.GATEWAY_LOG
    assert account.detached == 1
    gateway = receipt["account"]["gateway"]
    assert gateway["mode"] == "restarted", gateway
    assert gateway["started"] == int(GATEWAY_STARTED) + 600, gateway
    assert gateway["port"] == int(GATEWAY_PORT), gateway
    assert "private/account changed since the recorded gateway started" in out, out
    assert "every dev password rotated" in out, out
    assert read_gateway_record(world.root) == {
        "port": GATEWAY_PORT,
        "started": str(int(GATEWAY_STARTED) + 600),
        "account": ADIGEST,
    }


def scenario_no_drill_or_suite_env_carries_a_credential(
    m: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """Case 9: an inherited credential, the dev-config switch and a declared keyring skip are planted in the parent environment; none reaches a suite or a drill, and the minted token is in no byte written."""
    planted = {
        "REDIACC_TOKEN": "inherited-planted-token",
        "REDIACC_ACCOUNT_SERVER": "http://elsewhere.invalid:1",
        "RDC_DEV": "1",
        "DRILL_EXPECT_NO_KEYRING": "declared by the parent",
    }
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, m=m, env=planted)
    assert rc == vm_check.EXIT_VERIFIED, out
    children = world.suite_calls()
    assert len(children) == 7, [c for c, _e in children]
    for argv, env in children:
        leaked = [k for k in DRILL_ENV_SCRUB if k in env]
        assert not leaked, (argv, leaked)
        assert TOKEN not in json.dumps(env), argv
        assert env["PYTHONPATH"].split(os.pathsep)[0] == str(world.root / ".ci"), env["PYTHONPATH"]
    # The minted token still reached rdc, and nowhere else.
    assert any(e.get("REDIACC_TOKEN") == TOKEN for _a, e in _rdc_envs(world))
    assert TOKEN not in out
    assert TOKEN not in json.dumps(receipt)
    for path in tmp_path.rglob("*"):
        if path.is_file() and not path.is_symlink():
            assert TOKEN.encode() not in path.read_bytes(), path


def scenario_only_writes_no_receipt_json(m: types.ModuleType, tmp_path: pathlib.Path) -> None:
    """A `--only` run judges just the named steps, so it must write a run record, never receipt.json."""
    world = make_world(tmp_path, stored_ok=True)
    out = io.StringIO()
    environ = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ.get("PATH", ""),
        "VM_NET_BASE": NET,
    }
    m.main(
        ["--only", "U1", "--keep-work", "--wait", "0"],
        root=world.root,
        host=world,
        account=FakeAccount(),
        lock=m.Lock(tmp_path / "vm-check.lock"),
        out=out,
        environ=environ,
        inputs_fn=lambda _root: DIGEST,
        account_modified_fn=lambda _root: False,
        account_digest_fn=lambda _root: ADIGEST,
        u1_fn=lambda check: check.check("U1", "stub U1", True),
    )
    latest = world.root / receipt_mod.CACHE_DIR / receipt_mod.LATEST
    assert not latest.exists(), "a --only run must not write receipt.json"


SCENARIOS = {
    "only-writes-receipt-json": scenario_only_writes_no_receipt_json,
    "skip-account-phase": scenario_account_only_runs_the_account_phase_and_no_renet_step,
    "renet-steps-on-account-only": scenario_account_only_runs_the_account_phase_and_no_renet_step,
    "skipped-drill-passes": scenario_a_skipped_drill_is_not_verified,
    "reuse-stale-gateway": scenario_a_gateway_older_than_the_account_worktree_is_restarted,
    "drill-env-leaks-token": scenario_no_drill_or_suite_env_carries_a_credential,
    "skip-write-guard-globally": scenario_only_write_rows_skip_the_file_write_guard,
    "write-guard-not-passed": scenario_only_write_rows_skip_the_file_write_guard,
    "evidence-stdout-first": scenario_remote_stderr_reaches_the_evidence,
    "no-compose-upload": scenario_compose_file_is_uploaded_into_fork_a_only,
    "vi-assumed": scenario_vi_absent_writes_with_sed_and_says_so,
    "link-expected-back": scenario_the_link_is_left_out_and_absent_on_the_remote,
    "sftp-alias-from-home": scenario_sftp_runs_on_the_alias_config_vscode_wrote,
    "sftp-identity-not-copied": scenario_sftp_runs_on_the_alias_config_vscode_wrote,
    "sftp-no-drive-translation": scenario_sftp_runs_on_the_alias_config_vscode_wrote,
    "sftp-failure-not-denial": scenario_sftp_failure_status_on_b_is_a_refusal,
    "file-write-refusal-unknown": scenario_an_unhonoured_write_override_is_agent_policy_refused,
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
    # Case 3: no --changed runs both phases, and the receipt admits either side and both.
    assert receipt["trigger"]["sides"] == ["account", "renet"]
    assert receipt["phases"] == {
        "account": {"required": True, "ran": True},
        "renet": {"required": True, "ran": True},
    }
    for sides in ({"renet"}, {"account"}, {"renet", "account"}):
        assert receipt_mod.admit(world.root, TREE, DIGEST, sides).ok, sides
    ids = _ids(receipt)
    assert {"P0", "P1", "P2", "P3", "P4", *A_STEPS, *V_STEPS, "T"} <= set(ids)
    # Run order: A1 before P0, A0 after P1 and before P4, A2 after P3 and before P5.
    order = [ids.index(s) for s in ("A1.4", "P0", "P1", "A0", "P4", "P2", "P3", "A2.3", "P5")]
    assert order == sorted(order), ids
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


def _run_only(tmp_path: pathlib.Path, world: World, only: str) -> tuple[int, str, dict[str, Any]]:
    out = io.StringIO()
    environ = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ.get("PATH", ""),
        "VM_NET_BASE": NET,
    }
    recorded: list[str] = []

    def stub(check: Any) -> None:
        recorded.append("U1")
        check.check("U1", "stub U1", True)

    rc = vm_check.main(
        ["--only", only, "--keep-work", "--wait", "0"],
        root=world.root,
        host=world,
        account=FakeAccount(),
        lock=vm_check.Lock(tmp_path / "vm-check.lock"),
        out=out,
        environ=environ,
        inputs_fn=lambda _root: DIGEST,
        account_modified_fn=lambda _root: False,
        account_digest_fn=lambda _root: ADIGEST,
        u1_fn=stub,
    )
    latest = world.root / receipt_mod.CACHE_DIR / receipt_mod.LATEST
    receipt = json.loads(latest.read_text()) if latest.exists() else {}
    return rc, out.getvalue(), receipt


def test_only_u1_runs_the_infra_and_u1_and_writes_no_receipt_json(tmp_path: pathlib.Path) -> None:
    """`--only U1` runs P0-P4 plus U1, skips P5 and the V-steps, and writes a run record, never receipt.json, so it can never be VERIFIED."""
    world = make_world(tmp_path, stored_ok=True)
    _rc, out, receipt = _run_only(tmp_path, world, "U1")
    assert receipt == {}, "no receipt.json"
    assert not (world.root / receipt_mod.CACHE_DIR / receipt_mod.LATEST).exists()
    assert "--only U1" in out
    assert "vm:check VERIFIED" not in out
    ids = [ln.split()[0] for ln in out.splitlines() if ln.strip().startswith(("P", "U1"))]
    assert "U1" in ids
    # No P5, no V-steps, no account suites.
    assert not [c for c in world.rdc_calls() if c[:2] == ["repo", "fork"]]
    assert not world.npm_calls()


def test_only_writes_a_run_record_under_its_run_id(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, stored_ok=True)
    rc, out, _ = _run_only(tmp_path, world, "U1")
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    runs = list((world.root / receipt_mod.CACHE_DIR / receipt_mod.RUNS_DIR).glob("vmc-*"))
    records = [p / "receipt.json" for p in runs if (p / "receipt.json").exists()]
    assert records, "a run record under the run id"
    doc = json.loads(records[0].read_text())
    # Never VERIFIED: either the named set left a required phase un-run, or (every phase run)
    # the explicit `only-partial` downgrade.
    assert doc["status"] == receipt_mod.NOT_VERIFIED, doc
    assert doc["reason"]["class"] in ("phase-not-run", "only-partial"), doc["reason"]


def test_only_v13_drags_in_p5_and_v11(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, stored_ok=True)
    _rc, text, _ = _run_only(tmp_path, world, "V1.3")
    assert "P5" in text
    assert "V1.1" in text
    assert "V1.3" in text
    # V1.3 forks exist (V1.1 ran); U1 was not named, so the stub U1 row is absent.
    assert [c for c in world.rdc_calls() if c[:2] == ["repo", "fork"]]
    assert "stub U1" not in text


def test_a_writable_neighbour_fails_v12_and_still_tears_down(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, ro_breach=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    assert receipt["status"] == receipt_mod.FAILED
    assert receipt["reason"]["class"] == "step-failed"
    assert receipt["reason"]["detail"].startswith("V1.2")
    assert world.forks_left() == []
    assert not receipt_mod.admit(world.root, TREE, DIGEST, {"renet"}).ok


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


def test_a_key_copy_that_cannot_be_written_names_the_work_directory(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review bf6289c7.2: a write error on the identity copy is its own row, not "the alias's identity is readable"."""
    real_open = vm_check.os.open

    def failing_open(path, flags, *args):
        if str(path).endswith("sftp_identity"):
            raise OSError(28, "No space left on device")
        return real_open(path, flags, *args)

    monkeypatch.setattr(vm_check.os, "open", failing_open)
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    rows = [s for s in receipt["steps"] if s["id"] == "V1.7" and s["verdict"] == "FAIL"]
    assert [s["desc"] for s in rows] == ["the alias's identity is copied into the work directory"]
    assert "No space left on device" in rows[0]["evidence"]


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


def test_a_teardown_leftover_names_the_delete_error_and_the_run_says_it_judged(
    tmp_path: pathlib.Path,
) -> None:
    """2026-10-15 live: a teardown left both forks and the receipt named neither cause, and the summary claimed nothing was judged after 32 assertions ran."""
    world = make_world(tmp_path, undeletable_suffix="-b")
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "teardown-failed"
    assert "delete rc=1: device busy" in receipt["reason"]["detail"], receipt["reason"]
    assert "assertion(s) ran, and the run still does not count" in out, out
    assert "Nothing on the VMs was judged" not in out, out


class _GatewayDiesBeforeTeardown(FakeAccount):
    """P4 asks `gateway_healthy` once; the second ask is teardown's, by which time a stopped run's gateway is gone (2026-10-21)."""

    def __init__(self, *, revive_error: str = "", remint_error: str = "") -> None:
        super().__init__()
        self.revive_error = revive_error
        self.remint_error = remint_error
        self.healthy_calls = 0

    def gateway_healthy(self) -> bool:
        self.healthy_calls += 1
        if self.healthy_calls == 2:
            self.healthy = False
            self.restart_error = self.revive_error
            self.mint_error = self.remint_error
        return self.healthy


def test_teardown_revives_a_gateway_that_died_and_deletes_the_forks(tmp_path: pathlib.Path) -> None:
    account = _GatewayDiesBeforeTeardown()
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert account.healthy_calls == 2, account.healthy_calls
    assert len(account.restarts) >= 1, account.restarts
    assert account.minted == 2, (
        "the token is re-minted after the revival, never trusted across a restart"
    )
    assert "teardown: the dev gateway was gone" in out, out
    assert receipt["teardown"] == {"ok": True, "leftovers": []}


def test_a_gateway_teardown_cannot_revive_is_a_named_leftover(tmp_path: pathlib.Path) -> None:
    account = _GatewayDiesBeforeTeardown(revive_error="gateway did not come up")
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "teardown-failed"
    assert any(
        "dev gateway gone before teardown and not revived (gateway did not come up)" in x
        for x in receipt["teardown"]["leftovers"]
    ), receipt["teardown"]


def test_a_revived_gateway_that_refuses_the_new_token_is_a_named_leftover(
    tmp_path: pathlib.Path,
) -> None:
    account = _GatewayDiesBeforeTeardown(remint_error="login refused (%s)")
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert len(account.restarts) >= 1, "the restart ran before the mint failed"
    left = receipt["teardown"]["leftovers"]
    assert any("dev gateway gone before teardown and not revived" in x for x in left), left
    assert account.password not in out, "the per-run password never reaches the output"
    assert account.password not in json.dumps(receipt), "nor the receipt"


def test_a_live_gateway_is_not_restarted_by_teardown(tmp_path: pathlib.Path) -> None:
    account = FakeAccount()
    world = make_world(tmp_path)
    rc, out, _receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert account.minted == 1, account.minted
    assert "teardown: the dev gateway was gone" not in out, out


def test_a_delete_that_answers_rc0_and_stays_listed_is_named(tmp_path: pathlib.Path) -> None:
    """Review a6e93fb9.2: a fork the delete reported gone but the list still shows is a leftover with its own wording."""
    world = make_world(tmp_path, sticky_suffix="-b")
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "teardown-failed"
    assert any("-b (delete rc=0, still listed)" in x for x in receipt["teardown"]["leftovers"]), (
        receipt["teardown"]
    )


def test_an_unreadable_list_still_names_the_delete_error(tmp_path: pathlib.Path) -> None:
    """Review a6e93fb9.1: when the repo list fails after the deletes, each leftover still carries its delete's own error."""
    world = make_world(tmp_path, undeletable_suffix="-b", list_fails_after_delete=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    left = receipt["teardown"]["leftovers"]
    assert any("-b (repo list unreadable; delete rc=1: device busy)" in x for x in left), left
    assert any(x.endswith("-a (repo list unreadable)") for x in left), left


@pytest.mark.parametrize("cls", sorted(NOT_VERIFIED_CASES))
def test_each_not_verified_class(tmp_path: pathlib.Path, cls: str) -> None:
    over = dict(NOT_VERIFIED_CASES[cls])
    argv: list[str] = []
    account = FakeAccount()
    if cls == "fleet-os-mismatch":
        argv = ["--os", "ubuntu-24.04"]
    if cls == "account-unavailable":
        # A0 heals an unhealthy gateway on a both-phase run, so the refusal comes from the mint; the renet-only path with no gateway is its own test.
        account = FakeAccount(mint_error="login refused (%s)")
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
        assert any("-b (delete rc=1: device busy)" in x for x in receipt["teardown"]["leftovers"])
    else:
        assert world.forks_left() == []
    if cls == "renet-build-mismatch":
        assert ["--version"] in world.rdc_calls()
    if cls == "parent-grand-missing":
        assert "other-grand" in receipt["reason"]["detail"]
        assert not [c for c in world.rdc_calls() if c[:2] == ["repo", "create"]]
    if cls == "agent-policy-refused":
        assert "agent mode" in receipt["reason"]["detail"]


def run_busy(tmp_path: pathlib.Path) -> tuple[int, str, World]:
    """One run that loses the fleet lock to a peer holding it (pid 4242, session peer0001)."""
    fd = hold_lock(tmp_path)
    try:
        world = make_world(tmp_path)
        rc, out, _ = run_check(tmp_path, world)
    finally:
        os.close(fd)
    return rc, out, world


def run_record(world: World, out: str) -> tuple[pathlib.Path, dict[str, Any]]:
    """The record a run archived under its own run id, found from the run id its banner printed."""
    found = re.search(r"=== \S+ (vmc-\d{8}-[0-9a-f]{6}) ===", out)
    assert found, out
    path = receipt_mod.receipt_dir(world.root) / "runs" / found.group(1) / receipt_mod.LATEST
    assert path.is_file(), out
    record = json.loads(path.read_text())
    assert receipt_mod.validate(record) == [], receipt_mod.validate(record)
    return path, record


def receipt_bytes(world: World) -> dict[str, bytes]:
    """receipt.json and every tree archive, by name, as raw bytes."""
    return {p.name: p.read_bytes() for p in receipt_mod.receipt_files(world.root)}


def test_fleet_busy_names_the_holder_and_creates_nothing(tmp_path: pathlib.Path) -> None:
    rc, out, world = run_busy(tmp_path)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    _, receipt = run_record(world, out)
    assert receipt["reason"]["class"] == "fleet-busy"
    assert "pid 4242, session peer0001" in receipt["reason"]["detail"]
    assert world.rdc_calls() == []
    assert "nothing to tear down" in out


def test_a_fleet_busy_run_leaves_a_verified_receipt_byte_identical(tmp_path: pathlib.Path) -> None:
    """VC7(a), 2026-10-20: a busy loser (`--wait 5`, vmc-10201456-eec456) rewrote receipt.json while the holder still ran; had it finished last, the holder's VERIFIED receipt would have been replaced."""
    rc, out, receipt = run_check(tmp_path, make_world(tmp_path))
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["status"] == receipt_mod.VERIFIED
    before = receipt_bytes(make_world(tmp_path))
    assert sorted(before) == sorted([receipt_mod.LATEST, TREE + ".json"])
    rc, out, world = run_busy(tmp_path)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt_bytes(world) == before


def test_a_fleet_busy_run_archives_its_own_record_under_its_run_id_and_says_where(
    tmp_path: pathlib.Path,
) -> None:
    rc, out, world = run_busy(tmp_path)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    path, record = run_record(world, out)
    assert record["status"] == receipt_mod.NOT_VERIFIED
    assert record["reason"]["class"] == "fleet-busy"
    assert record["tree"] == TREE
    assert record["runDir"] == str(path.parent.relative_to(world.root))
    assert str(path.relative_to(world.root)) in out
    assert "never held the fleet lock" in out
    # Nothing a later push is judged by: no receipt.json, no tree archive.
    assert receipt_mod.receipt_files(world.root) == []


def test_a_lock_holder_still_writes_receipt_json_after_a_busy_loser(tmp_path: pathlib.Path) -> None:
    _, busy_out, _ = run_busy(tmp_path)
    _, loser = run_record(make_world(tmp_path), busy_out)
    rc, out, receipt = run_check(tmp_path, make_world(tmp_path))
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["status"] == receipt_mod.VERIFIED
    assert receipt["runId"] != loser["runId"]
    archived = receipt_mod.read_archive(make_world(tmp_path).root, TREE)
    assert archived is not None
    assert archived["runId"] == receipt["runId"]


def test_the_guard_admits_the_push_after_a_busy_loser_ran_later(tmp_path: pathlib.Path) -> None:
    rc, out, _ = run_check(tmp_path, make_world(tmp_path))
    assert rc == vm_check.EXIT_VERIFIED, out
    root = make_world(tmp_path).root
    assert receipt_mod.admit(root, TREE, DIGEST, {"renet", "account"}).ok
    run_busy(tmp_path)
    got = receipt_mod.admit(root, TREE, DIGEST, {"renet", "account"})
    assert (got.ok, got.code) == (True, "ok"), got.message


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
    assert receipt["trigger"]["sides"] == ["renet"]


# --------------------------------------------------------------------------- the account phase (PLAN-account-vm-check.md AV4)


def test_a_renet_only_change_runs_no_suite_and_no_drill(tmp_path: pathlib.Path) -> None:
    """Case 1."""
    world = renet_only_world(tmp_path)
    account = FakeAccount()
    rc, out, receipt = run_check(tmp_path, world, "--changed", account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert world.suite_calls() == []
    assert receipt["phases"] == {
        "account": {"required": False, "ran": False},
        "renet": {"required": True, "ran": True},
    }
    assert not [i for i in _ids(receipt) if i.startswith("A")], _ids(receipt)
    assert receipt["account"]["gateway"] == {"mode": None, "port": None, "started": None}
    assert account.restarts == []
    assert "A1-A2 not run" in out
    assert receipt_mod.admit(world.root, TREE, DIGEST, {"renet"}).ok
    refused = receipt_mod.admit(world.root, TREE, DIGEST, {"account"})
    assert refused.code == "phase-missing", refused


def test_a_renet_only_run_with_no_gateway_and_no_stored_token_is_account_unavailable(
    tmp_path: pathlib.Path,
) -> None:
    """The renet phase alone never starts a gateway; P4 still says it needs one."""
    world = renet_only_world(tmp_path)
    account = FakeAccount(healthy=False)
    rc, out, receipt = run_check(tmp_path, world, "--changed", account=account)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-unavailable", receipt["reason"]
    assert account.restarts == []


def test_an_account_only_change_is_verified_with_the_account_phase_alone(
    tmp_path: pathlib.Path,
) -> None:
    """Case 2."""
    scenario_account_only_runs_the_account_phase_and_no_renet_step(vm_check, tmp_path)


def test_a_red_suite_stops_the_run_before_any_vm_is_touched(tmp_path: pathlib.Path) -> None:
    """Case 4."""
    world = make_world(
        tmp_path, suites={"A1.1": (1, "running 412 tests\nFAIL src/licenses.test.ts\n3 failed\n")}
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    assert receipt["status"] == receipt_mod.FAILED
    detail = receipt["reason"]["detail"]
    assert detail.startswith("A1.1: npm run check:ci-account-server (61 s)"), detail
    assert "rc=1: running 412 tests | FAIL src/licenses.test.ts | 3 failed" in detail, detail
    # All four suites ran, then nothing else: no lock row, no fleet, no drill.
    assert [r["verdict"] for r in receipt["steps"] if r["id"].startswith("A1")] == [
        "FAIL",
        "ok",
        "ok",
        "ok",
    ]
    assert world.rdc_calls() == []
    assert ["ops", "status", "-o", "json"] not in world.rdc_calls()
    assert world.drill_calls() == []
    assert "P0" not in _ids(receipt)
    assert receipt["phases"]["account"]["ran"] is False
    assert lock_is_free(tmp_path)


def test_the_suites_run_from_their_packages(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    root = str(world.root)
    account = str(world.root / "private/account")
    assert world.npm_calls() == [
        ["npm", "--prefix", root, "run", "check:ci-account-server"],
        ["npm", "--prefix", root, "run", "check:ci-test-account-web"],
        ["npm", "--prefix", account, "run", "typecheck"],
        ["npm", "--prefix", account, "run", "typecheck:web"],
    ]


def test_a_failed_license_assertion_is_failed_naming_the_drill(tmp_path: pathlib.Path) -> None:
    """Case 5."""
    failed = (1, "  10 assertions: 9 passed, 1 failed  (40s)\n  drill license FAILED\n")
    world = make_world(tmp_path, drills={"license": failed})
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    detail = receipt["reason"]["detail"]
    assert detail.startswith("A2.3: drill license"), detail
    assert "1 of 10 assertions failed" in detail, detail
    # A red account phase stops before the renet steps.
    assert not [i for i in _ids(receipt) if i in V_STEPS], _ids(receipt)
    assert world.forks_left() == []


def test_a_drill_that_stops_in_its_preflight_is_account_drill_setup(
    tmp_path: pathlib.Path,
) -> None:
    """Case 6: transfer's missing keyring is a SystemExit(1) before any summary."""
    world = make_world(
        tmp_path,
        drills={"transfer": (1, "-- Setup: two isolated config directories\n   keyring probe\n")},
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-drill-setup", receipt["reason"]
    assert "A2.2 drill transfer: rc=1 with no summary line" in receipt["reason"]["detail"]
    # The license drill still ran after it; nothing was asserted against the renet side.
    assert len(world.drill_calls()) == 3
    assert not [c for c in world.rdc_calls() if c[:2] == ["repo", "fork"]]


def test_a_skipped_drill_is_account_drill_skipped(tmp_path: pathlib.Path) -> None:
    """Case 7."""
    scenario_a_skipped_drill_is_not_verified(vm_check, tmp_path)


def test_a_failed_drill_outranks_a_skipped_one(tmp_path: pathlib.Path) -> None:
    world = make_world(
        tmp_path,
        drills={
            "universe": (0, "  0 assertions: 0 passed, 0 failed  (0s)\n  drill universe SKIPPED\n"),
            "license": (1, "  4 assertions: 3 passed, 1 failed  (9s)\n"),
        },
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    assert receipt["reason"]["detail"].startswith("A2.3"), receipt["reason"]


def test_with_no_record_the_gateway_is_started_recorded_and_left_running(
    tmp_path: pathlib.Path,
) -> None:
    """Case 8, started: nothing answers and no record exists."""
    world = make_world(tmp_path)
    account = FakeAccount(healthy=False)
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert len(account.restarts) == 1
    assert account.detached == 1
    assert receipt["account"]["gateway"]["mode"] == "started"
    assert read_gateway_record(world.root)["account"] == ADIGEST
    assert "no healthy dev gateway answers; starting it" in out, out
    assert "dev gateway: started on port %s, left running" % GATEWAY_PORT in out, out


def test_a_matching_record_reuses_the_gateway(tmp_path: pathlib.Path) -> None:
    """Case 8, reused: the running gateway is the recorded one and the account worktree is unchanged."""
    world = make_world(tmp_path)
    write_gateway_record(world.root, ADIGEST)
    account = FakeAccount()
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert account.restarts == []
    assert account.detached == 0
    assert receipt["account"]["gateway"] == {
        "mode": "reused",
        "port": int(GATEWAY_PORT),
        "started": int(GATEWAY_STARTED),
    }
    assert [r["desc"] for r in _rows(receipt, "A0")] == [
        "dev gateway reused on port %s (started=%s; its record matches the account worktree)"
        % (GATEWAY_PORT, GATEWAY_STARTED)
    ]


def test_a_gateway_another_writer_restarted_is_restarted_once(tmp_path: pathlib.Path) -> None:
    """Case 8, restarted: the record names an earlier start, so the running gateway is not provably fresh (D4)."""
    world = make_world(tmp_path)
    write_gateway_record(world.root, ADIGEST, started="1791999000")
    account = FakeAccount()
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert len(account.restarts) == 1
    assert receipt["account"]["gateway"]["mode"] == "restarted"
    assert "is not the recorded one (started=1791999000" in out, out


def test_a_gateway_older_than_the_account_worktree_is_restarted(tmp_path: pathlib.Path) -> None:
    """Case 8, restarted (the reuse-stale-gateway scenario)."""
    scenario_a_gateway_older_than_the_account_worktree_is_restarted(vm_check, tmp_path)


@pytest.mark.parametrize(
    ("account_kwargs", "digest", "says"),
    [
        (
            {"restart_error": "the dev gateway exited during startup"},
            ADIGEST,
            "CRYPTO_KEYS is not set",
        ),
        ({"healthy": False, "healthy_after_restart": False}, ADIGEST, "does not answer"),
        ({}, None, "worktree is unreadable"),
    ],
)
def test_a_gateway_that_cannot_be_proven_fresh_is_account_gateway(
    tmp_path: pathlib.Path, account_kwargs: dict[str, Any], digest: str | None, says: str
) -> None:
    """Case 8, account-gateway: a failed start (with the log tail), a start that never answers, and an account worktree the freshness key cannot read."""
    world = make_world(tmp_path)
    account = FakeAccount(**account_kwargs)
    rc, out, receipt = run_check(tmp_path, world, account=account, digest=digest)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "account-gateway", receipt["reason"]
    assert says in receipt["reason"]["detail"], receipt["reason"]
    assert "NOT VERIFIED (account-gateway)" in out
    # Stopped before any fleet step, and no record names a gateway that is not fresh.
    assert not [c for c in world.rdc_calls() if c[:2] == ["ops", "status"]]
    assert not (world.root / receipt_mod.CACHE_DIR / vm_check.GATEWAY_RECORD).exists()
    assert lock_is_free(tmp_path)


def test_no_drill_or_suite_env_carries_a_credential(tmp_path: pathlib.Path) -> None:
    """Case 9."""
    scenario_no_drill_or_suite_env_carries_a_credential(vm_check, tmp_path)


def test_the_drill_argvs_are_exact(tmp_path: pathlib.Path) -> None:
    """Case 10."""
    world = make_world(tmp_path)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    calls = world.drill_calls()
    assert [c[1:] for c in calls] == [
        ["-m", "rediacc_ci.drills.universe", "--no-restart"],
        ["-m", "rediacc_ci.drills.transfer", "--no-restart"],
        [
            "-m",
            "rediacc_ci.drills.license",
            "--legs",
            "c,d,e,f",
            "--no-restart",
            "--seed-repo",
            "--vm",
            "192.168.111.11",
        ],
    ]
    assert calls[0][0] == sys.executable


def test_a_required_phase_whose_steps_never_ran_is_phase_not_run(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Case 11: A2 planted to do nothing and report success, so the account phase never reaches its drills."""
    monkeypatch.setattr(vm_check.VmCheck, "a2_drills", lambda _self: True)
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "phase-not-run", receipt["reason"]
    assert "account" in receipt["reason"]["detail"], receipt["reason"]
    assert receipt["phases"]["account"] == {"required": True, "ran": False}
    assert receipt["phases"]["renet"] == {"required": True, "ran": True}
    assert "account NOT RUN" in out, out


def _class_of(verdict: tuple[str, dict[str, str] | None]) -> str:
    reason = verdict[1]
    assert reason is not None, verdict
    return reason["class"]


def test_verdict_orders_phase_not_run_after_reason_and_before_no_assertions() -> None:
    both = {"renet": {"required": True, "ran": True}, "account": {"required": True, "ran": False}}
    assert _class_of(vm_check.verdict(3, [], None, [], both)) == "phase-not-run"
    assert _class_of(vm_check.verdict(0, [], None, [], both)) == "phase-not-run"
    assert _class_of(vm_check.verdict(3, [], ("fleet-busy", "x"), [], both)) == "fleet-busy"
    assert vm_check.verdict(3, ["V1.2: x"], None, [], both)[0] == receipt_mod.FAILED
    # A phase that is not required may stay unrun; one that ran needs nothing more.
    renet_only = {
        "renet": {"required": True, "ran": True},
        "account": {"required": False, "ran": False},
    }
    assert vm_check.verdict(3, [], None, [], renet_only) == (receipt_mod.VERIFIED, None)
    assert _class_of(vm_check.verdict(0, [], None, [], renet_only)) == "no-assertions"


@pytest.mark.parametrize(
    ("rc", "out", "outcome"),
    [
        (0, drill_passed("universe")[1], vm_check.DRILL_OK),
        (0, "  3 assertions: 3 passed, 0 failed  (1s)\n  drill x PASSED\n", vm_check.DRILL_OK),
        (1, "  3 assertions: 2 passed, 1 failed  (1s)\n  drill x FAILED\n", vm_check.DRILL_FAILED),
        # A failed count wins even over an rc 0 that should not happen.
        (0, "  3 assertions: 2 passed, 1 failed  (1s)\n", vm_check.DRILL_FAILED),
        (
            0,
            "  0 assertions: 0 passed, 0 failed  (0s)\n  drill x SKIPPED (0 ran)\n",
            vm_check.DRILL_SKIP,
        ),
        (0, "  0 assertions: 0 passed, 0 failed  (0s)\n", vm_check.DRILL_SKIP),
        (0, "config-storage enrollment: SKIPPED BY DECLARATION\n", vm_check.DRILL_SKIP),
        (0, "", vm_check.DRILL_SKIP),
        (1, "No usable OS keyring\n", vm_check.DRILL_SETUP),
        (2, "", vm_check.DRILL_SETUP),
        (1, "  3 assertions: 3 passed, 0 failed  (1s)\n  drill x PASSED\n", vm_check.DRILL_SETUP),
        (0, "  3 assertions: 3 passed, 0 failed  (1s)\n", vm_check.DRILL_SETUP),
        # The last summary is the drill's own; an earlier one quoted in its output is not.
        (
            0,
            "  1 assertions: 0 passed, 1 failed\n  5 assertions: 5 passed, 0 failed\n  drill x PASSED\n",
            vm_check.DRILL_OK,
        ),
    ],
)
def test_classify_drill(rc: int, out: str, outcome: str) -> None:
    assert vm_check.classify_drill(vm_check.Result(rc, out))[0] == outcome


def test_an_account_checkout_off_its_pointer_is_said_and_its_receipt_does_not_admit(
    tmp_path: pathlib.Path,
) -> None:
    world = account_only_world(tmp_path, account_checkout="1" * 40)
    rc, out, receipt = run_check(tmp_path, world, "--changed", modified=True)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert "is not the pointer %s" % APTR[:12] in out, out
    assert "worktree is modified" in out, out
    assert receipt["account"] == {
        "pointer": APTR,
        "checkout": "1" * 40,
        "modified": True,
        "gateway": receipt["account"]["gateway"],
    }
    assert receipt_mod.admit(world.root, TREE, DIGEST, {"account"}).code == "account-mismatch"


def test_an_uninitialized_account_submodule_records_no_checkout(tmp_path: pathlib.Path) -> None:
    """git -C on an empty submodule directory would answer the console's HEAD."""
    world = make_world(tmp_path, account_checked_out=False)
    rc, out, receipt = run_check(tmp_path, world, modified=None)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["account"]["checkout"] == ""
    assert receipt["account"]["modified"] is None
    assert not [c for c in world.calls if c[0] == "git" and c[2].endswith("private/account")]
    assert receipt_mod.admit(world.root, TREE, DIGEST, {"account"}).code == "account-mismatch"


def test_receipts_of_an_earlier_schema_are_said_to_no_longer_count(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path)
    folder = world.root / receipt_mod.CACHE_DIR
    folder.mkdir(parents=True)
    (folder / ("0" * 40 + ".json")).write_text(json.dumps({"schema": 1, "status": "VERIFIED"}))
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert "1 receipt(s) of an earlier schema in .ci/cache/vm-check no longer count" in out, out
    (tmp_path / "again").mkdir()
    world2 = make_world(tmp_path / "again")
    rc, out, _receipt = run_check(tmp_path / "again", world2)
    assert "earlier schema" not in out, out


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


STALE_FORK = "%s:vmc-10141500-abcdef-a" % PARENT
FRESH_FORK = "%s:vmc-10141750-abcdef-b" % PARENT


def test_stale_forks_beside_a_missing_grand_are_swept_when_it_is_created(
    tmp_path: pathlib.Path,
) -> None:
    """Review 8b3374e0.2: the create path returned before the sweep, so a stale fork beside a missing grand survived the run."""
    world = make_world(tmp_path, grands=(), extra_repos=(STALE_FORK, FRESH_FORK))
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert len(_creates(world)) == 1
    deleted = [c[2] for c in world.rdc_calls() if c[:2] == ["repo", "delete"]]
    assert deleted[0] == STALE_FORK, deleted
    assert STALE_FORK not in world.repos
    assert FRESH_FORK in world.repos
    rows = [r for r in receipt["steps"] if r["id"] == "P5"]
    assert len(rows) == 1, rows
    assert "created on" in rows[0]["desc"], rows[0]
    assert "1 stale fork(s) swept" in rows[0]["desc"], rows[0]
    assert "stale forks: swept %s" % STALE_FORK in out, out


def test_stale_forks_beside_a_missing_grand_are_swept_when_its_create_fails(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(
        tmp_path,
        grands=(),
        extra_repos=(STALE_FORK, FRESH_FORK),
        create_rc=1,
        create_err="Machine slot limit reached for this plan",
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "parent-grand-missing"
    assert STALE_FORK not in world.repos
    assert FRESH_FORK in world.repos


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


def _forgets(world: World) -> list[list[str]]:
    return [c for c in world.rdc_calls() if c[:2] == ["repo", "delete"] and "--archive-config" in c]


def test_a_grand_only_in_config_is_forgotten_then_created(tmp_path: pathlib.Path) -> None:
    """VC7(b), 2026-10-20: `ops down` destroyed the VM, the config kept the grand, and `repo create` refused 'already exists in config'."""
    world = make_world(tmp_path, grands=(), config_has_parent=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert _forgets(world) == [["repo", "delete", PARENT, "--archive-config", "-y"]]
    assert len(_creates(world)) == 2
    assert PARENT in world.repos
    row = next(r for r in receipt["steps"] if r["id"] == "P5")
    assert row["verdict"] == "ok"
    assert "stale config entry forgotten" in row["evidence"], row


def test_a_grand_present_on_the_worker_is_never_forgotten(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, config_has_parent=True)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert _forgets(world) == []
    assert _creates(world) == []


def test_a_missing_grand_absent_from_config_is_created_without_a_forget(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, grands=())
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert _forgets(world) == []


def test_a_failed_forget_is_not_verified_and_names_both_commands(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, grands=(), config_has_parent=True, forget_rc=1)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "parent-grand-missing"
    detail = receipt["reason"]["detail"]
    assert "forgetting it failed" in detail, detail
    assert "--archive-config" in detail, detail
    assert "forget refused" in detail, detail
    assert "already exists in config" in detail, detail
    assert "repo create" in detail, detail
    assert len(_creates(world)) == 1


def test_a_create_still_failing_after_the_forget_names_both_commands(
    tmp_path: pathlib.Path,
) -> None:
    # The archive answers rc 0 but the entry stays: the second create refuses again.
    world = make_world(tmp_path, grands=(), config_has_parent=True, forget_keeps=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    detail = receipt["reason"]["detail"]
    assert "forgot the stale config entry, but creating it still failed" in detail, detail
    assert "--archive-config" in detail, detail
    assert "already exists in config" in detail, detail


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


def test_a_stale_config_entry_on_a_worker_without_a_datastore_is_forgotten_set_up_and_created(
    tmp_path: pathlib.Path,
) -> None:
    """After the forget, the second create's NO_DATASTORE refusal still reaches `machine setup` instead of ending the run."""
    world = make_world(tmp_path, grands=(), config_has_parent=True, datastore=False)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert len(_forgets(world)) == 1
    setups = [c for c in world.rdc_calls() if c[:2] == ["machine", "setup"]]
    assert setups == [["machine", "setup", vm_check.OPS_WORKER_NAME]], setups
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
        tmp_path, world, account=FakeAccount(server=well_known.ACCOUNT_DEFAULT_ORIGIN)
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


LOOPBACK_GATEWAY = "http://localhost:%s" % GATEWAY_PORT


def _issuing_envs(world: World) -> list[dict[str, str]]:
    """The environment of every call that makes the CLI issue a licence: the grand's create and the forks."""
    return [e for c, e in _rdc_envs(world) if c[:2] in (["repo", "create"], ["repo", "fork"])]


def test_the_token_names_the_gateway_at_the_address_the_worker_reaches(
    tmp_path: pathlib.Path,
) -> None:
    """Worklist #efddc775: minted over localhost, every fork's and the grand's blob carried a renewalUrl the worker cannot reach. The token names the gateway at this host's VM-network address, so that address is what the account stamps."""
    world = make_world(tmp_path, grands=())
    account = FakeAccount()
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert account.hosts == [HOST_ADDR]
    assert account.minted == 1
    issuing = _issuing_envs(world)
    assert len(issuing) == 3, [c for c, _e in _rdc_envs(world)]
    assert {e.get("REDIACC_ACCOUNT_SERVER") for e in issuing} == {GATEWAY}
    p4 = [r for r in receipt["steps"] if r["id"] == "P4"]
    assert len(p4) == 1
    assert GATEWAY in p4[0]["desc"]
    assert "subscription kept" in p4[0]["desc"]


def test_a_cold_fleet_mints_on_localhost_then_on_the_bridge_before_any_issuance(
    tmp_path: pathlib.Path,
) -> None:
    """No interface on the VM network before `ops up`: the token P4 mints on localhost serves the fleet steps only, and is replaced by one minted on the bridge address right after P2."""
    world = make_world(
        tmp_path, running=(), vm_net_addr=None, also_gateways=(LOOPBACK_GATEWAY,), grands=()
    )
    account = FakeAccount()
    rc, out, receipt = run_check(tmp_path, world, account=account)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert account.hosts == ["localhost", HOST_ADDR]
    assert account.minted == 2
    assert "re-minted on this host's VM-network address" in out
    issuing = _issuing_envs(world)
    assert issuing
    assert {e.get("REDIACC_ACCOUNT_SERVER") for e in issuing} == {GATEWAY}
    p4 = [r["desc"] for r in receipt["steps"] if r["id"] == "P4"]
    assert len(p4) == 2
    assert LOOPBACK_GATEWAY in p4[0]
    assert GATEWAY in p4[1]


def test_a_fleet_up_with_no_vm_network_address_never_issues(tmp_path: pathlib.Path) -> None:
    world = make_world(
        tmp_path,
        running=(),
        vm_net_addr=None,
        vm_net_after_up=None,
        also_gateways=(LOOPBACK_GATEWAY,),
        grands=(),
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "fleet-unavailable"
    assert "no licence this run issues could renew" in receipt["reason"]["detail"]
    assert _issuing_envs(world) == []


def _subscription(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "sub-1",
        "planCode": vm_check.ACCOUNT_PLAN,
        "status": "inactive",
        "expiresAt": None,
        "repoLicenseIssuances": {"used": 12, "limit": 2000},
        "maxActivations": 5,
        "machineSlots": {"active": 1, "max": 5},
    }
    body.update(over)
    return body


@pytest.mark.parametrize(
    ("over", "why"),
    [
        ({}, ""),
        ({"status": "active"}, ""),
        ({"expiresAt": "2027-01-01T00:00:00Z"}, ""),
        ({"id": ""}, "no subscription"),
        ({"planCode": "COMMUNITY"}, "plan COMMUNITY"),
        ({"status": "suspended"}, "status suspended"),
        ({"status": "grace"}, "status grace"),
        ({"expiresAt": "2026-01-01T00:00:00Z"}, "expired at"),
        ({"expiresAt": "soon"}, "unreadable expiresAt"),
        ({"repoLicenseIssuances": {"used": 1960, "limit": 2000}}, "1960 of 2000"),
        ({"repoLicenseIssuances": None}, "no repoLicenseIssuances"),
        ({"machineSlots": {"active": 5, "max": 5}}, "machine slots full (5 of 5)"),
    ],
)
def test_subscription_reuse_refusal(over: dict[str, Any], why: str) -> None:
    got = vm_check.subscription_reuse_refusal(_subscription(**over), NOW)
    assert (got == "") if not why else (why in got), got


def test_a_404_answer_is_no_subscription() -> None:
    assert vm_check.subscription_reuse_refusal({"error": "No subscription linked"}, NOW)
    assert vm_check.subscription_reuse_refusal(None, NOW) == "no subscription"


class _MintDrill:
    """The lib.Drill surface DrillAccount uses, answering `/portal/subscription` with `body`."""

    def __init__(self, body: Any, port: str = GATEWAY_PORT) -> None:
        self.body = body
        self.port = port
        self.gateway_port_cached = ""
        self.ensured: list[str] = []
        self.minted_for: list[str] = []

    def gateway_port(self) -> str:
        return self.port

    def api_base(self) -> str:
        return "http://127.0.0.1:%s/account/api/v1" % GATEWAY_PORT

    def account_ensure_login(self, email: str, password: str) -> None:
        assert email == vm_check.ACCOUNT_LOGIN
        assert password

    def account_session(self, _email: str, _password: str, _jar: Any) -> bool:
        return True

    def _request(self, method: str, url: str, data: Any, _jar: Any) -> str:
        assert (method, url, data) == ("GET", self.api_base() + "/portal/subscription", None)
        return json.dumps(self.body)

    def account_ensure_subscription(self, email: str, plan: str) -> None:
        assert email == vm_check.ACCOUNT_LOGIN
        self.ensured.append(plan)
        self.body = _subscription(id="sub-new", repoLicenseIssuances={"used": 0, "limit": 2000})

    def account_subscription_id(self, _jar: Any) -> str:
        return str(self.body["id"])

    def account_mint_token(self, _jar: Any, subscription: str, name: str, scopes: list[str]) -> str:
        assert name == vm_check.MINT_LABEL
        assert scopes == list(vm_check.TOKEN_SCOPES)
        self.minted_for.append(subscription)
        return "tok"


def _drill_account(drill: _MintDrill) -> vm_check.DrillAccount:
    return vm_check.DrillAccount(cast("vm_check.lib.Drill", drill))


def test_mint_keeps_a_subscription_that_can_carry_the_run() -> None:
    drill = _MintDrill(_subscription())
    account = _drill_account(drill)
    assert account.mint("p" * 24) == "tok"
    assert drill.ensured == []
    assert drill.minted_for == ["sub-1"]
    assert account.subscription_note() == "subscription kept (12 of 2000 issuances used this month)"


def test_mint_recreates_a_subscription_short_of_issuances() -> None:
    drill = _MintDrill(_subscription(repoLicenseIssuances={"used": 1999, "limit": 2000}))
    account = _drill_account(drill)
    assert account.mint("p" * 24) == "tok"
    assert drill.ensured == [vm_check.ACCOUNT_PLAN]
    assert drill.minted_for == ["sub-new"]
    assert account.subscription_note().startswith("subscription recreated (1999 of 2000")


def test_mint_creates_the_subscription_a_login_lacks() -> None:
    drill = _MintDrill({"error": "No subscription linked"})
    account = _drill_account(drill)
    account.mint("p" * 24)
    assert drill.ensured == [vm_check.ACCOUNT_PLAN]
    assert drill.minted_for == ["sub-new"]


@pytest.mark.parametrize(
    ("host", "port", "want"),
    [
        (HOST_ADDR, GATEWAY_PORT, GATEWAY),
        ("localhost", GATEWAY_PORT, LOOPBACK_GATEWAY),
        ("", GATEWAY_PORT, ""),
        (HOST_ADDR, "", ""),
    ],
)
def test_drill_account_server_url_names_the_host(host: str, port: str, want: str) -> None:
    assert _drill_account(_MintDrill(None, port=port)).server_url(host) == want


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
        ("array", "config ssh show gave no key state (its JSON is a list, not an object)"),
        ("datastr", "config ssh show gave no key state (its JSON data is a str, not an object)"),
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


@pytest.mark.parametrize(
    ("raw", "state"),
    [
        ('{"data": {"embedded": "no"}}', ("no", "")),
        ('{"data": {}}', (None, "its JSON has no data.embedded")),
        ('{"data": null}', (None, "its JSON has no data.embedded")),
        ("{}", (None, "its JSON has no data.embedded")),
        ("[]", (None, "its JSON is a list, not an object")),
        ('"x"', (None, "its JSON is a str, not an object")),
        ('{"data": "x"}', (None, "its JSON data is a str, not an object")),
        ('{"data": []}', (None, "its JSON data is a list, not an object")),
        ("config ssh: ok", (None, "its output is not JSON")),
        ("", (None, "its output is not JSON")),
    ],
)
def test_key_state_tells_not_json_from_json_of_the_wrong_shape(
    raw: str, state: tuple[Any, str]
) -> None:
    """Review e9309c59.1: `[]` and `{"data": "x"}` are JSON, and were reported as not JSON."""
    assert vm_check.key_state(raw) == state


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


# --------------------------------------------------------------------------- the 2026-10-15 V-step harness defects


@pytest.mark.parametrize("name", sorted(set(SCENARIOS) - {"pass-on-zero-steps"}))
def test_each_mutant_scenario_is_green_unmutated(tmp_path: pathlib.Path, name: str) -> None:
    """A mutant scenario that fails for another reason proves nothing, so each one also passes on the real module."""
    SCENARIOS[name](vm_check, tmp_path)


def test_a_present_vi_is_used_and_sed_is_not(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, vi=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    commands = [c[4] for c in world.rdc_calls() if c[:2] == ["term", "connect"]]
    assert vm_check.VI_WRITE in commands
    assert vm_check.SED_WRITE not in commands
    assert [r["verdict"] for r in _rows(receipt, "V1.3") if r["desc"] == "A: vi writes ~/v"] == [
        "ok"
    ]


def test_sync_created_directories_are_owned_and_existing_ones_keep_their_owner(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    rows = {r["desc"]: r["verdict"] for r in _rows(receipt, "V1.5")}
    run = receipt.get("run_id", "")
    owned = [d for d in rows if d.startswith("created by --remote")]
    assert len(owned) == 8, rows
    assert all(rows[d] == "ok" for d in owned), rows
    kept = [d for d in rows if d.startswith("an existing directory") and d.endswith("root:root")]
    assert len(kept) == 1, (rows, run)
    assert rows[kept[0]] == "ok", (rows, run)


def test_a_root_owned_new_directory_fails_v15(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, root_parents=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    failed = [r["desc"] for r in _rows(receipt, "V1.5") if r["verdict"] == "FAIL"]
    assert any(d.startswith("created by --remote-file") for d in failed), failed
    assert any(d.startswith("created by --remote:") for d in failed), failed
    assert not any(d.startswith("an existing directory") for d in failed), failed


def test_a_symlink_that_reaches_the_remote_fails_v15(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, sync_keeps_links=True)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    failed = [r["desc"] for r in _rows(receipt, "V1.5") if r["verdict"] == "FAIL"]
    assert "the link is absent on the remote (a privileged sync carries no symlink)" in failed, (
        failed
    )


def test_a_linux_alias_in_home_is_found_too(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, alias_home="linux")
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    built = next(r for r in _rows(receipt, "V1.7") if r["desc"].startswith("ssh config for"))
    assert str(tmp_path / "home" / ".ssh" / vm_check.ALIAS_CONFIG) in built["desc"], built


def test_a_missing_alias_block_fails_v17_naming_where_it_looked(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path, alias_written=False)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    row = next(r for r in _rows(receipt, "V1.7") if r["verdict"] == "FAIL")
    assert "is in a config_rediacc" in row["desc"], row
    assert "searched" in row["evidence"], row
    assert not [c for c in world.calls if c[0] == "sftp"]


def test_sftp_refused_reads_failure_status_lines_only_for_the_named_path() -> None:
    b = well_known.DATASTORE_PATH + "/mounts/guid-b"
    assert vm_check.sftp_refused('dest open "%s/vmc-sftp": Failure' % b, b)
    assert vm_check.sftp_refused('remote setstat "%s/.rediacc.json": Failure' % b, b)
    assert vm_check.sftp_refused('sftp> put x\nremote setstat "%s": Failure\n' % b, b)
    # Another path, a prefix look-alike, no path, and connection-level failures are not refusals.
    a = well_known.DATASTORE_PATH + "/mounts/guid-a"
    assert not vm_check.sftp_refused('dest open "%s/x": Failure' % a, b)
    assert not vm_check.sftp_refused('dest open "%sx/y": Failure' % b, b)
    assert not vm_check.sftp_refused('dest open "%s/x": Failure' % b)
    assert not vm_check.sftp_refused("Connection closed", b)
    assert not vm_check.sftp_refused(
        "ssh: Could not resolve hostname rediacc-x: Name or service not known\r\nConnection closed",
        b,
    )
    assert not vm_check.sftp_refused("u@h: Permission denied (publickey).\nConnection closed", b)


@pytest.mark.parametrize(
    ("value", "spelled"),
    [
        ("C:/Users/dev/.ssh/k", "/mnt/c/Users/dev/.ssh/k"),
        ('"D:\\Users\\a b\\.ssh\\k"', "/mnt/d/Users/a b/.ssh/k"),
        ("/home/dev/.ssh/k", "/home/dev/.ssh/k"),
        ("~/.ssh/k", "~/.ssh/k"),
    ],
)
def test_drive_path_spells_windows_drives_for_wsl(value: str, spelled: str) -> None:
    assert vm_check.drive_path(value) == spelled


def test_a_failed_vi_probe_is_a_failed_row_not_an_absence(tmp_path: pathlib.Path) -> None:
    """Review 5a9861e8.2: an ssh failure answering the probe (rc 255) established nothing about vi, so no sed fallback runs and nothing claims vi is absent."""
    world = make_world(tmp_path, vi=False, vi_probe_rc=255)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    rows = [s for s in receipt["steps"] if "vi probe answered" in s["desc"]]
    assert len(rows) == 1
    assert rows[0]["verdict"] == "FAIL"
    assert not [s for s in receipt["steps"] if "vi absent" in s["desc"]]


def test_a_vi_probe_that_exits_0_with_nothing_is_a_failed_row(tmp_path: pathlib.Path) -> None:
    """Review f434e6dc.3: `command -v vi` printing nothing at rc 0 answered neither present nor absent, so it is a failed row and no sed fallback claims vi absent."""
    world = make_world(tmp_path, vi=False, vi_probe_rc=0)
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    assert [s["verdict"] for s in receipt["steps"] if "vi probe answered" in s["desc"]] == ["FAIL"]
    assert not [s for s in receipt["steps"] if "vi absent" in s["desc"]]


def test_alias_block_finds_a_later_pattern_and_stops_at_match() -> None:
    """Review 5a9861e8.4: a Host line lists several patterns, and a Match block's directives are not the alias's."""
    text = "Host other want\n  HostName 2\nMatch host x\n  User root\n"
    assert vm_check.alias_block(text, "want") == ["HostName 2"]


def test_alias_block_reads_only_the_named_host() -> None:
    text = "Host other\n  HostName 1\n\nHost want extra\n  HostName 2\n\n  # note\n  Port 22\nHost z\n  X 1\n"
    assert vm_check.alias_block(text, "want") == ["HostName 2", "Port 22"]
    assert vm_check.alias_block(text, "missing") is None
    assert vm_check.alias_block(text, "z") == ["X 1"]


# --------------------------------------------------------------------------- licence state of deleted forks


def test_teardown_purges_the_licence_state_of_this_runs_deleted_forks(
    tmp_path: pathlib.Path,
) -> None:
    """renet keeps a deleted repo's blobs and `license renew` retries every one: on 2026-10-20 21 of 22 blobs on the ops worker were vm:check forks deleted days before."""
    world = make_world(tmp_path, uuid_forks=True, extra_repos=[STALE_FORK])
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    stale = world.repos.get(STALE_FORK) or str(uuid.uuid5(uuid.NAMESPACE_OID, STALE_FORK))
    forks = [f["guid"] for f in receipt["forks"]]
    assert len(world.purges) == 2, world.purges
    # The P5 sweep purges the stale fork it deleted; T purges this run's two forks, and nothing else.
    assert stale in world.purges[0]
    assert all(g in world.purges[1] for g in forks)
    assert world.repos["%s" % PARENT] not in "".join(world.purges)
    assert receipt["teardown"] == {"ok": True, "leftovers": []}


def test_a_purge_that_keeps_a_guid_is_a_teardown_leftover(tmp_path: pathlib.Path) -> None:
    world = make_world(
        tmp_path, uuid_forks=True, purge_rc=1, purge_out="KEPT x: renet still lists it\n"
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "teardown-failed"
    assert "licence state of this run's forks" in receipt["reason"]["detail"]
    assert "KEPT x" in receipt["reason"]["detail"]


def test_a_sweep_purge_that_fails_is_a_teardown_leftover(tmp_path: pathlib.Path) -> None:
    """A stale fork whose licence blob the P5 sweep could not purge keeps the run off VERIFIED, as a teardown purge does."""
    world = make_world(
        tmp_path,
        uuid_forks=True,
        extra_repos=[STALE_FORK],
        purge_rc=1,
        purge_out="KEPT x: renet still lists it\n",
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "teardown-failed"
    assert "licence state of the swept forks" in receipt["reason"]["detail"]


def test_a_fork_guid_that_is_not_a_uuid_is_left_alone_and_said(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path)
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert world.purges == []
    assert "is not a repository guid" in out


# --------------------------------------------------------------------------- drill evidence

LICENSE_FAILED_OUT = (
    "  01  PASS  the installed blob carries a renewalUrl\n"
    "  02  FAIL  the machine can reach that URL (a localhost baseUrl would fail here)\n"
    "\n=== drill license summary ===\n"
    "  ##   RESULT ASSERTION\n"
    "  01   PASS   the installed blob carries a renewalUrl\n"
    "  02   \x1b[0;31mFAIL\x1b[0m   the machine can reach that URL (a localhost baseUrl would fail here)\n"
    "  03   FAIL   the machine holds no rdc config and no account token\n"
    "  -------------------------------------------------------------\n"
    "  3 assertions: 1 passed, 2 failed  (41s)\n"
    "  drill license FAILED\n"
)
PAYLOAD_TAIL = '    | {"license":{"payload":"eyJ2ZXJzaW9uIjoyLCJzdWJzY3JpcHRpb25JZCI6IjFm"}}\n'


def test_failed_assertions_reads_only_the_summary_table() -> None:
    assert vm_check.failed_assertions(LICENSE_FAILED_OUT) == [
        "02 the machine can reach that URL (a localhost baseUrl would fail here)",
        "03 the machine holds no rdc config and no account token",
    ]
    assert vm_check.failed_assertions("  02  FAIL  x\n") == []


def test_a_failed_drill_names_its_assertions_not_the_last_dump() -> None:
    """2026-10-20: the detail was the tail of the last failure dump, a base64 licence payload."""
    outcome, detail = vm_check.classify_drill(vm_check.Result(1, LICENSE_FAILED_OUT, PAYLOAD_TAIL))
    assert outcome == vm_check.DRILL_FAILED
    assert detail.startswith("2 of 3 assertions failed: 02 the machine can reach that URL")
    assert "03 the machine holds no rdc config" in detail
    assert "payload" not in detail


def test_a_failed_drill_keeps_its_full_output_and_the_receipt_names_the_assertions(
    tmp_path: pathlib.Path,
) -> None:
    world = make_world(tmp_path, drills={"license": (1, LICENSE_FAILED_OUT)})
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    row = next(r for r in receipt["steps"] if r["id"] == "A2.3")
    assert row["failedAssertions"] == [
        "02 the machine can reach that URL (a localhost baseUrl would fail here)",
        "03 the machine holds no rdc config and no account token",
    ]
    log_file = world.root / row["log"]
    assert log_file.is_file()
    assert "drill license summary" in log_file.read_text()
    assert row["log"].startswith(receipt["runDir"] + "/")
    assert receipt["runDir"] == "%s/runs/%s" % (receipt_mod.CACHE_DIR, receipt["runId"])
    assert "FAIL 02 the machine can reach that URL" in out
    assert "02 the machine can reach that URL" in receipt["reason"]["detail"]
    # Every suite and drill keeps its log, green ones included.
    assert all(r.get("log") for r in receipt["steps"] if r["id"] in ("A1.1", "A2.1", "A2.2"))


def test_the_kept_log_is_scrubbed_of_the_minted_token(tmp_path: pathlib.Path) -> None:
    world = make_world(
        tmp_path, drills={"universe": (0, "echo %s\n" % TOKEN + drill_passed("universe")[1])}
    )
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    row = next(r for r in receipt["steps"] if r["id"] == "A2.1")
    text = (world.root / row["log"]).read_text()
    assert TOKEN not in text
    assert "<token>" in text


def test_only_the_newest_run_directories_are_kept(tmp_path: pathlib.Path) -> None:
    world = make_world(tmp_path)
    runs = world.root / receipt_mod.CACHE_DIR / vm_check.RUNS_DIR
    for i in range(vm_check.RUNS_KEEP + 5):
        old = runs / ("vmc-old-%02d" % i)
        old.mkdir(parents=True)
        os.utime(old, (1000 + i, 1000 + i))
    rc, out, receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    kept = sorted(d.name for d in runs.iterdir())
    assert len(kept) == vm_check.RUNS_KEEP
    assert receipt["runId"] in kept
    assert "vmc-old-00" not in kept


def test_the_gateway_record_is_not_counted_as_an_old_receipt(tmp_path: pathlib.Path) -> None:
    """Review 2fa7d53d.1: gateway.json has no schema key and was counted as an earlier-schema receipt."""
    world = make_world(tmp_path)
    folder = world.root / receipt_mod.CACHE_DIR
    folder.mkdir(parents=True)
    (folder / vm_check.GATEWAY_RECORD).write_text(
        json.dumps({"port": str(well_known.ACCOUNT_DEV_PORT), "started": "1"})
    )
    rc, out, _receipt = run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert "earlier schema" not in out, out

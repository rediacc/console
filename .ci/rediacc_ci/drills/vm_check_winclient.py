"""Tier B of `npm run vm:check` (agent/plans/PLAN-windows-lane.md D14): `--windows-client <ip>` routes a named set of CLI calls through a Windows client VM, each one an `rdc` run on Windows over Linux ssh, recorded as a `WC-` row beside the Linux battery's own rows.

    npm run vm:check -- --windows-client 192.168.111.31 [--rdc-exe <path>]

THE ROWS. WC-P3 `machine scan-keys <worker>`, right after the Linux P3. After V1.7, against fork A of the run: WC-V1.5 `repo sync upload --verify` and `repo sync download` of a small fixture (a nested file, a name with a space and 1 MiB of random bytes), judged byte-identical after the download is copied back; WC-V1.6 `vscode connect --url-only`; WC-TERM `term connect -c` echoing a per-run nonce; WC-DOCTOR `doctor --output json`, which must exit 0 with a JSON object naming no error. The Linux rows stay whole (V1.7 still needs the alias the Linux V1.6 wrote), so Tier B adds rows and replaces none, and the worker side, the forks and the teardown stay on Linux.

THE CLIENT. The CLI runs as `rdc.exe` when `--rdc-exe <path>` stages one (a downloaded `rdc-win-x64.exe`, say), else as the staged bundle `packages/cli/dist/cli-bundle.cjs` through `node`. Everything lives in a per-run directory `rdc-vmcheck\\<run id>` under the ssh user's home (WINDOWS_CLIENT_USER, default `rdc`, the image's administrator), reached with the fleet key the overlay authorizes (`vm_ssh.default_key`). Each call stages the run's config (`upgrade_converge.run_config_name`, `renetPath` dropped, the stored token file beside it when the run minted none) into `<run dir>\\appdata\\rediacc` and runs one generated PowerShell script with `APPDATA` pointed there, so the user's own `%APPDATA%\\rediacc` is never read or written. A minted token travels in `token.txt` in the run directory, read by the script: never on an argv, never in a script. `REDIACC_NO_PROVISION=1` holds the worker's renet (the Linux run uploaded it), and the agent markers this process carries (CLAUDECODE, REDIACC_AGENT, REDIACC_ALLOW_*) are mirrored into the script, never added. Every file reaches the VM with Linux `scp`, never through stdin (D6).

VERDICTS. A client ssh cannot reach, checked before any fleet work, is NOT_VERIFIED `windows-client-unreachable`; a CLI or config that cannot be staged is `windows-client-stage`; a failing `WC-` row is a failed assertion, so the run is FAILED; a run that reached its end with no finding and without every `WC-` row is NOT_VERIFIED `windows-client-not-run`. T runs `vscode cleanup` on the client for the WC-V1.6 connection and removes the run directory (it holds the config's keys and the token); either one left is a teardown leftover.
"""

from __future__ import annotations

import hashlib
import importlib
import ipaddress
import json
import os
import pathlib
import re
import secrets
import shutil
from typing import TYPE_CHECKING, Any

from rediacc_ci.drills import upgrade_converge, vm_ssh

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from rediacc_ci.drills.vm_check import Result, VmCheck

PREFIX = "WC-"
ROW_P3 = PREFIX + "P3"
ROW_SYNC = PREFIX + "V1.5"
ROW_VSCODE = PREFIX + "V1.6"
ROW_TERM = PREFIX + "TERM"
ROW_DOCTOR = PREFIX + "DOCTOR"
# Every row a Tier B run must record; `complete` refuses a run that reached its end without one of them.
ROWS = (ROW_P3, ROW_SYNC, ROW_VSCODE, ROW_TERM, ROW_DOCTOR)

UNREACHABLE = "windows-client-unreachable"
STAGE = "windows-client-stage"
NOT_RUN = "windows-client-not-run"
VSCODE_ABSENT = "windows-client-vscode-absent"

USER_ENV = "WINDOWS_CLIENT_USER"
DEFAULT_USER = "rdc"
# The per-run directories, relative to the ssh user's home: OpenSSH for Windows starts both the session and the sftp side of scp there, so no drive letter or profile path is spelled here, and the profile's ACL keeps the token from other users.
REMOTE_BASE = "rdc-vmcheck"
BUNDLE = pathlib.Path("packages") / "cli" / "dist" / "cli-bundle.cjs"
EXE_NAME = "rdc.exe"
# The file in the run directory the minted token travels in.
CARRIER_FILE = "token.txt"
# A trivial command both cmd.exe and PowerShell answer with exit 0: the reachability probe.
PROBE = "hostname"
POWERSHELL = "powershell -NoProfile -NonInteractive"
# The agent markers mirrored from this process's environment into each call, so the Windows CLI's agent guard sees what the Linux one sees; nothing here sets one that is absent.
MIRRORED_ENV = ("CLAUDECODE", "REDIACC_AGENT")
MIRRORED_PREFIX = "REDIACC_ALLOW_"
CALL_TIMEOUT_S = 600
SYNC_TIMEOUT_S = 900
SYNC_BIG_BYTES = 1024 * 1024
# What a run-relative path may hold: it is spelled inside a double-quoted PowerShell string, where `"`, `$` and the backtick would be live.
SAFE_REL = re.compile(r"^[A-Za-z0-9 ._\\-]+$")


class RemotePath(str):
    """An argument naming a path under the client's run directory, given relative to it; the script spells it from `$PSScriptRoot`."""

    __slots__ = ()


def _vmc() -> Any:
    """`rediacc_ci.drills.vm_check`, looked up where it is used: vm_check imports this module while it loads."""
    return importlib.import_module("rediacc_ci.drills.vm_check")


def parse_ip(value: str) -> str:
    """The client's address as a literal IPv4 (D6: never a host name, never IPv6), or ValueError."""
    text = value.strip()
    addr = ipaddress.ip_address(text)
    if addr.version != 4:
        msg = "%s is not an IPv4 address" % text
        raise ValueError(msg)
    return str(addr)


def ps_quote(text: str) -> str:
    """A PowerShell single-quoted literal: nothing inside is expanded, and `'` doubles."""
    return "'" + text.replace("'", "''") + "'"


def ps_run_path(rel: str) -> str:
    """`"$run\\<rel>"`, a path under the run directory the script sits in."""
    if not SAFE_REL.match(rel):
        msg = "run-relative path %r holds a character PowerShell would expand" % rel
        raise ValueError(msg)
    return '"$run\\%s"' % rel


def ps_arg(arg: str) -> str:
    """One native-command argument. Windows PowerShell 5.1 hands an argument holding `"` to the program mangled, so none may carry one."""
    if '"' in arg:
        msg = "argument %r holds a double quote, which PowerShell 5.1 passes on mangled" % arg
        raise ValueError(msg)
    return ps_run_path(str(arg)) if isinstance(arg, RemotePath) else ps_quote(arg)


def call_script(
    program: Sequence[str],
    args: Sequence[str],
    env: Mapping[str, str],
    config_name: str,
) -> str:
    """The PowerShell script one routed call runs: the run directory is the script's own folder, APPDATA points into it, the token (when staged) is read from `token.txt`, and the script exits with the CLI's code."""
    lines = [
        "$ErrorActionPreference = 'Continue'",
        "$ProgressPreference = 'SilentlyContinue'",
        "$run = $PSScriptRoot",
        '$env:APPDATA = "$run\\appdata"',
        "$env:REDIACC_CONFIG = %s" % ps_quote(config_name),
        "$env:REDIACC_NO_PROVISION = '1'",
        "$env:PYTHONIOENCODING = 'utf-8'",
    ]
    lines += ["$env:%s = %s" % (key, ps_quote(value)) for key, value in sorted(env.items())]
    lines += [
        '$tokenFile = "$run\\%s"' % CARRIER_FILE,
        (
            "if (Test-Path -LiteralPath $tokenFile) {"
            " $env:REDIACC_TOKEN = (Get-Content -Raw -LiteralPath $tokenFile).Trim() }"
        ),
        "& %s" % " ".join([*(ps_arg(p) for p in program), *(ps_arg(a) for a in args)]),
        "exit $LASTEXITCODE",
    ]
    return "\r\n".join(lines) + "\r\n"


def tree_of(base: pathlib.Path) -> dict[str, str]:
    """`<relative path>: <sha256>` of every regular file under `base`."""
    return {
        path.relative_to(base).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(base.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def doctor_errors(out: str) -> tuple[bool, list[str]]:
    """(stdout held a JSON object, the `<section>/<check>` names whose status is `error`) of `doctor --output json`."""
    start, end = out.find("{"), out.rfind("}")
    try:
        doc = json.loads(out[start : end + 1]) if 0 <= start < end else None
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        return False, []
    bad = [
        "%s/%s" % (section, check.get("name") or check.get("label") or "?")
        for section, checks in doc.items()
        if isinstance(checks, list)
        for check in checks
        if isinstance(check, dict) and check.get("status") == "error"
    ]
    return True, bad


def _write_private(path: pathlib.Path, text: str) -> None:
    """Write `text` at mode 0600 from the first byte: the config copy carries keys and the token file the token."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


class WindowsClient:
    """The Tier B seam: the routed rows, their staging and their teardown, for one VmCheck run. Every effect goes through the run's `Host`, so the fake host of the tests answers it."""

    def __init__(self, ctx: VmCheck, ip: str, rdc_exe: str = "") -> None:
        self.ctx = ctx
        self.ip = ip
        self.rdc_exe = rdc_exe
        self.user = ctx.environ.get(USER_ENV) or DEFAULT_USER
        self.key = ctx.ssh_key
        # True once the probe answered: from then on T removes the run directory.
        self.made = False
        self.staged = False
        self.connection = ""
        self.calls = 0
        self.local = ctx.work / "windows-client"

    # ------------------------------------------------------------------ transport

    @property
    def remote(self) -> str:
        """The run directory, relative to the client user's home, spelled with `/` as scp takes it."""
        return "%s/%s" % (REMOTE_BASE, self.ctx.run_id)

    @property
    def remote_win(self) -> str:
        return self.remote.replace("/", "\\")

    def _target(self, rel: str) -> str:
        return "%s@%s:%s/%s" % (self.user, self.ip, self.remote, rel)

    def ssh(self, command: str, timeout: float = CALL_TIMEOUT_S) -> Result:
        return self.ctx.host.run(
            vm_ssh.ssh_argv(self.user, self.key, self.ip, command),
            env=self.ctx.environ,
            timeout=timeout,
        )

    def _scp_options(self) -> list[str]:
        """The options of `vm_ssh.ssh_argv` (one identity, no agent, no ~/.ssh/config, no host-key bookkeeping), between its program and its destination."""
        return vm_ssh.ssh_argv(self.user, self.key, self.ip, "")[1:-2]

    def upload(
        self, sources: Sequence[pathlib.Path], rel: str, *, recursive: bool = False
    ) -> Result:
        argv = ["scp", *self._scp_options(), *(["-r"] if recursive else [])]
        return self.ctx.host.run(
            [*argv, *(str(s) for s in sources), self._target(rel)],
            env=self.ctx.environ,
            timeout=CALL_TIMEOUT_S,
        )

    def download(self, rel: str, local: pathlib.Path) -> Result:
        return self.ctx.host.run(
            ["scp", *self._scp_options(), "-r", self._target(rel), str(local)],
            env=self.ctx.environ,
            timeout=CALL_TIMEOUT_S,
        )

    def powershell(self, command: str) -> Result:
        return self.ssh('%s -Command "%s"' % (POWERSHELL, command))

    # ------------------------------------------------------------------ staging

    def preflight(self) -> None:
        """Before any fleet work: the client answers ssh, and the run directory exists. NOT_VERIFIED `windows-client-unreachable` otherwise."""
        vmc = _vmc()
        self.ctx.say(
            "vm:check: Tier B through the Windows client %s@%s (%s)"
            % (
                self.user,
                self.ip,
                "rdc.exe from " + self.rdc_exe if self.rdc_exe else "the staged bundle on node",
            )
        )
        res = self.ssh(PROBE, timeout=60)
        if res.rc != 0:
            raise vmc.NotVerifiedError(
                UNREACHABLE,
                "ssh %s@%s %s rc=%d: %s"
                % (self.user, self.ip, PROBE, res.rc, vmc.last_lines(res.err) or "<no stderr>"),
            )
        self.made = True
        res = self.powershell(
            "New-Item -ItemType Directory -Force -Path %s | Out-Null"
            % ps_quote(self.remote_win + "\\appdata\\rediacc")
        )
        if res.rc != 0:
            raise vmc.NotVerifiedError(
                UNREACHABLE,
                "the run directory %s was not created on %s (rc=%d): %s"
                % (self.remote_win, self.ip, res.rc, vmc.last_lines(res.err) or "<no stderr>"),
            )
        self.local.mkdir(parents=True, exist_ok=True)

    def _program(self) -> list[str]:
        if self.rdc_exe:
            return [RemotePath(EXE_NAME)]
        return ["node", RemotePath(BUNDLE.name)]

    def stage(self) -> None:
        """The CLI (rdc.exe or the bundle) and the minted token into the run directory, once. NOT_VERIFIED `windows-client-stage` when either cannot be."""
        if self.staged:
            return
        vmc = _vmc()
        source = pathlib.Path(self.rdc_exe) if self.rdc_exe else self.ctx.root / BUNDLE
        if not self.ctx.host.exists(str(source)):
            raise vmc.NotVerifiedError(STAGE, "the CLI to stage is absent: %s" % source)
        res = self.upload([source], EXE_NAME if self.rdc_exe else BUNDLE.name)
        if res.rc != 0:
            raise vmc.NotVerifiedError(
                STAGE,
                "scp %s rc=%d: %s" % (source, res.rc, vmc.last_lines(res.err) or "<no stderr>"),
            )
        if self.ctx.token:
            token = self.local / CARRIER_FILE
            _write_private(token, self.ctx.token)
            res = self.upload([token], CARRIER_FILE)
            token.unlink(missing_ok=True)
            if res.rc != 0:
                raise vmc.NotVerifiedError(
                    STAGE,
                    "the token was not staged (scp rc=%d): %s"
                    % (res.rc, vmc.last_lines(res.err) or "<no stderr>"),
                )
        self.staged = True

    def config_name(self) -> str:
        return upgrade_converge.run_config_name(self.ctx.environ, self.ctx.dev_config)

    def config_dir(self) -> pathlib.Path:
        env = self.ctx.environ
        base = env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME", "~"), ".config")
        return pathlib.Path(base) / "rediacc"

    def stage_config(self) -> None:
        """The run's config as it stands now (forks included), `renetPath` dropped (a Linux path), and its stored token file when the run minted none, into `<run dir>\\appdata\\rediacc`."""
        vmc = _vmc()
        name = self.config_name()
        source = self.config_dir() / ("%s.json" % name)
        try:
            doc = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise vmc.NotVerifiedError(
                STAGE, "the run's config %s does not read: %s" % (source, exc)
            ) from exc
        if not isinstance(doc, dict):
            raise vmc.NotVerifiedError(STAGE, "the run's config %s is not a JSON object" % source)
        doc.pop("renetPath", None)
        folder = self.local / "appdata"
        folder.mkdir(parents=True, exist_ok=True)
        staged = folder / source.name
        _write_private(staged, json.dumps(doc, indent=2) + "\n")
        files = [staged]
        token = source.with_name("api-token-%s.json" % name)
        if not self.ctx.token and token.is_file():
            copy = folder / token.name
            _write_private(copy, token.read_text(encoding="utf-8"))
            files.append(copy)
        res = self.upload(files, "appdata/rediacc/")
        for path in files:
            path.unlink(missing_ok=True)
        if res.rc != 0:
            raise vmc.NotVerifiedError(
                STAGE,
                "the config was not staged (scp rc=%d): %s"
                % (res.rc, vmc.last_lines(res.err) or "<no stderr>"),
            )

    def mirrored_env(self) -> dict[str, str]:
        """The environment each script sets beyond its fixed lines: the agent markers this process carries, and the account server a minted token names."""
        env = {
            k: v
            for k, v in self.ctx.environ.items()
            if k in MIRRORED_ENV or k.startswith(MIRRORED_PREFIX)
        }
        if self.ctx.token and self.ctx.account_server:
            env["REDIACC_ACCOUNT_SERVER"] = self.ctx.account_server
        return env

    # ------------------------------------------------------------------ the routed call

    def rdc(self, *args: str, timeout: float = CALL_TIMEOUT_S, refuse: bool = True) -> Result:
        """One CLI call on the client: the config is staged afresh, one script is uploaded and run. A refusal by the agent guard ends the run as a Linux one does; a connection that is gone is `windows-client-unreachable`."""
        vmc = _vmc()
        self.stage()
        self.stage_config()
        self.calls += 1
        name = "call-%d.ps1" % self.calls
        script = self.local / name
        _write_private(
            script, call_script(self._program(), args, self.mirrored_env(), self.config_name())
        )
        res = self.upload([script], name)
        if res.rc != 0:
            raise vmc.NotVerifiedError(
                UNREACHABLE,
                "scp %s rc=%d: %s" % (name, res.rc, vmc.last_lines(res.err) or "<no stderr>"),
            )
        res = self.ssh(
            "%s -ExecutionPolicy Bypass -File %s\\%s" % (POWERSHELL, self.remote_win, name),
            timeout=timeout,
        )
        if res.rc == vm_ssh.SSH_FAILED and not res.out.strip():
            raise vmc.NotVerifiedError(
                UNREACHABLE,
                "rdc %s on %s: ssh rc=%d: %s"
                % (" ".join(args[:3]), self.ip, res.rc, vmc.last_lines(res.err) or "<no stderr>"),
            )
        if refuse and res.rc != 0 and any(m in res.err for m in vmc.AGENT_REFUSALS):
            raise vmc.NotVerifiedError(
                "agent-policy-refused",
                "rdc %s on the Windows client: %s" % (" ".join(args[:3]), vmc.first_line(res.err)),
            )
        return res

    # ------------------------------------------------------------------ rows

    def p3(self) -> None:
        """WC-P3, right after the Linux P3 pinned the worker's keys for the Linux config."""
        res = self.rdc("machine", "scan-keys", self.ctx.machine)
        self.ctx.check(
            ROW_P3,
            "machine scan-keys %s on the Windows client" % self.ctx.machine,
            res.rc == 0,
            res,
        )

    def v_rows(self) -> None:
        """WC-V1.5, WC-V1.6, WC-TERM and WC-DOCTOR, after V1.7, against fork A."""
        self.sync()
        self.vscode()
        self.term()
        self.doctor()

    def _fixture(self) -> pathlib.Path:
        up = self.local / "wc-sync-up"
        (up / "nested" / "deeper").mkdir(parents=True, exist_ok=True)
        (up / "nested" / "deeper" / "leaf.txt").write_text("vm:check %s\n" % self.ctx.run_id)
        (up / "with space.txt").write_text("a name with a space\n")
        (up / "big.bin").write_bytes(secrets.token_bytes(SYNC_BIG_BYTES))
        return up

    def sync(self) -> None:
        vmc = _vmc()
        ref = self.ctx.ref(self.ctx.tags[0])
        up = self._fixture()
        res = self.upload([up], "wc-sync-up", recursive=True)
        if not self.ctx.check(
            ROW_SYNC,
            "the fixture reaches the Windows client",
            res.rc == 0,
            res,
            "" if res.rc == 0 else "scp rc=%d: %s" % (res.rc, vmc.last_lines(res.err)),
        ):
            return
        remote = "vmc-wcsync-%s" % self.ctx.run_id
        upload = ("repo", "sync", "upload", ref, "--local", RemotePath("wc-sync-up\\"))
        res = self.rdc(*upload, "--remote", remote, "--verify", timeout=SYNC_TIMEOUT_S)
        if not self.ctx.check(
            ROW_SYNC, "sync upload --verify on the Windows client", res.rc == 0, res
        ):
            return
        download = ("repo", "sync", "download", ref, "--local", RemotePath("wc-sync-down"))
        res = self.rdc(*download, "--remote", remote, timeout=SYNC_TIMEOUT_S)
        if not self.ctx.check(ROW_SYNC, "sync download on the Windows client", res.rc == 0, res):
            return
        down = self.local / "wc-sync-down"
        shutil.rmtree(down, ignore_errors=True)
        res = self.download("wc-sync-down", down)
        sent = tree_of(up)
        got = tree_of(down) if res.rc == 0 and down.is_dir() else {}
        differ = sorted(k for k in set(sent) | set(got) if sent.get(k) != got.get(k))
        if res.rc != 0:
            why = "scp back rc=%d: %s" % (res.rc, vmc.last_lines(res.err) or "<no stderr>")
        else:
            why = "differ: %s" % ", ".join(differ)
        self.ctx.check(
            ROW_SYNC,
            "the Windows round trip is byte-identical (%d files)" % len(sent),
            res.rc == 0 and not differ,
            res,
            why,
        )

    def vscode(self) -> None:
        vmc = _vmc()
        res = self.rdc("vscode", "connect", self.ctx.ref(self.ctx.tags[0]), "--url-only")
        if res.rc != 0 and vmc.VSCODE_ABSENT in res.text():
            raise vmc.NotVerifiedError(
                VSCODE_ABSENT,
                "vscode connect on the Windows client refused before any setup: %s"
                % vmc.first_line(res.text()),
            )
        uri = next(
            (ln.strip() for ln in res.out.splitlines() if ln.strip().startswith(vmc.URI_PREFIX)),
            "",
        )
        if uri:
            self.connection = uri[len(vmc.URI_PREFIX) :].split("/", 1)[0]
        self.ctx.check(
            ROW_VSCODE,
            "vscode connect --url-only on the Windows client prints a remote URI",
            res.rc == 0 and bool(self.connection),
            res,
            evidence=uri,
        )

    def term(self) -> None:
        nonce = "vmc-wc-%s" % secrets.token_hex(4)
        res = self.rdc("term", "connect", self.ctx.ref(self.ctx.tags[0]), "-c", "echo " + nonce)
        self.ctx.check(
            ROW_TERM,
            "term connect -c on the Windows client runs the command on the fork",
            res.rc == 0 and nonce in res.out,
            res,
        )

    def doctor(self) -> None:
        res = self.rdc("doctor", "--output", "json")
        parsed, errors = doctor_errors(res.out)
        ok = res.rc == 0 and parsed and not errors
        if ok:
            why = ""
        elif errors:
            why = "rc=%d, errors: %s" % (res.rc, ", ".join(errors))
        elif not parsed:
            why = "rc=%d, no JSON object on stdout: %s" % (res.rc, _vmc().remote_evidence(res))
        else:
            why = _vmc().remote_evidence(res)
        self.ctx.check(ROW_DOCTOR, "doctor on the Windows client reports no error", ok, res, why)

    # ------------------------------------------------------------------ the end

    def complete(self) -> None:
        """At the end of the battery: a run with no finding yet that lacks a `WC-` row is NOT_VERIFIED `windows-client-not-run`, since Tier B was asked for and not proven."""
        if self.ctx.failures or self.ctx.reason is not None:
            return
        seen = {row.get("id") for row in self.ctx.steps}
        missing = [row for row in ROWS if row not in seen]
        if missing:
            raise _vmc().NotVerifiedError(NOT_RUN, "Tier B recorded no %s row" % ", ".join(missing))

    def teardown(self) -> list[str]:
        """`vscode cleanup` of the WC-V1.6 connection and the run directory's removal; the leftover lines."""
        leftovers: list[str] = []
        if not self.made:
            return leftovers
        vmc = _vmc()
        if self.connection:
            try:
                res = self.rdc("vscode", "cleanup", "-c", self.connection, refuse=False)
            except vmc.NotVerifiedError as exc:
                leftovers.append(
                    "Windows client vscode connection %s (%s)" % (self.connection, exc.detail)
                )
            else:
                if res.rc != 0:
                    leftovers.append(
                        "Windows client vscode connection %s (cleanup rc=%d)"
                        % (self.connection, res.rc)
                    )
        res = self.powershell(
            "Remove-Item -Recurse -Force -LiteralPath %s" % ps_quote(self.remote_win)
        )
        if res.rc != 0:
            leftovers.append(
                "Windows client run directory %s on %s (remove rc=%d)"
                % (self.remote_win, self.ip, res.rc)
            )
        shutil.rmtree(self.local, ignore_errors=True)
        return leftovers

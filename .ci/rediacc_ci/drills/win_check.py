"""`npm run win:check`: drive `rdc` on a Windows VM over SSH, judge the `RDC-STEP` lines its PowerShell suites print, and write a receipt (agent/plans/PLAN-windows-lane.md D7, D8).

    npm run win:check [-- --vm <ip>] [--user <name>] [--key <path>] [--domain <libvirt domain>]
                      [--suite keys,guard,term,dpapi,vscode,sync,gotest] [--target fleet|hostinger --fork <repo:tag> --remote-config <name>]
                      [--worker <ip>] [--worker-name <name>] [--worker-user <name>] [--wait <s>] [--skip-build] [--dry-run] [--selftest]

THE FLOW, in order. Everything outside this process goes through one `Host`, which the tests replace whole.
  LOCK     the `fleet` resource of `rediacc_ci.core.resource_lock` (the file vm:check and `./rdc.sh ops up|down` take), waited for up to `--wait` seconds. A run that gives up there judged nothing: NOT_VERIFIED `fleet-busy`, recorded only under `runs/<run id>/`, never as `receipt.json`.
  REACH    one SSH probe of the Windows VM (`--vm`, default 192.168.111.31, the first id of the Windows client range D11 reserves). SSH's own failure (exit 255) or a probe that prints no answer is NOT_VERIFIED `win-vm-unavailable`. A VM that answers without `node` on its PATH is NOT_VERIFIED `win-bake-missing`: the bake (D3) installs the toolchain, the harness does not. `C:\\rediacc-image.json`, when the bake wrote one, rides into the receipt as `image`.
  WORKER   `ssh-keyscan` of the fleet worker (`--worker`, default 192.168.111.11) from this host. No key is NOT_VERIFIED `worker-unavailable`. The keys are what the keys suite compares the Windows config's stored host keys against.
  BUILD    `./rdc.sh --version` (the CLI bundle and the Linux renet, `local_common.prepare_cli`), then `renet-windows-amd64.exe` through renet's own `build.sh _go_build` with the licence key `local_common.resolve_renet_account_key` resolves. A failure is NOT_VERIFIED `build-failed`. `--skip-build` stages what is already built.
  STAGE    over scp: the bundle as `C:\\rdc\\cli-bundle.cjs`, `renet.exe` and `renet-linux-amd64` into `C:\\rdc\\renet`, the fleet key as `<profile>\\.ssh\\fleet_rsa` (owner-only ACL), and every file of `.ci/rediacc_ci/drills/windows/` plus this run's `params.json` into `C:\\rdc\\suites`. A failure is NOT_VERIFIED `stage-failed`.
  SUITES   each requested suite runs as `powershell -NoProfile -ExecutionPolicy Bypass -File C:\\rdc\\suites\\<suite>.ps1` over SSH, in SUITE_ORDER. guard, term and vscode use the config the keys suite creates, so asking for one of them adds keys. `--target hostinger` adds sync and a term step against the hostinger fork, both under `--remote-config`, a config already present on the VM; `REDIACC_NO_PROVISION=1` holds for every call, and the sync suite writes only under the fork's `winspike-test/` and removes it.
  EVIDENCE each suite's stdout and stderr are kept in `.ci/cache/win-check/runs/<run id>/<suite>.log|.err`, beside `params.json`; after the vscode suite a `virsh screenshot` of `--domain` is kept as `vscode.png` (evidence only, never judged). The newest RUNS_KEEP run directories are kept.

THE JUDGE reads lines, never prose. A suite step prints `RDC-STEP {"id": "<suite>.<step>", "rc": <int>, "expect": <int>|"nonzero", "ok": <bool>, ...}`, optionally with `"match": <bool>` when the step also asserted a pattern of its output. The driver re-derives `ok` from `rc` and `expect` (and `match`); a step whose own `ok` disagrees, a malformed line, a step id outside its suite and a repeated id are each a failed row. A suite that ran to its end prints `RDC-SUITE {"suite": "<suite>", "steps": <n>}` with `n` equal to the step lines it printed; a suite without that line, with another count, or with a non-zero exit after it did not complete. SSH failing (255) during a suite is `win-vm-unavailable`.

VERDICTS follow vm:check. VERIFIED exit 0: steps ran, none failed, every requested suite completed. FAILED exit 1: a step failed. NOT_VERIFIED exit 77: the check could not judge (`fleet-busy`, `win-vm-unavailable`, `win-bake-missing`, `worker-unavailable`, `build-failed`, `stage-failed`, `no-assertions` when no step line came back at all, `phase-not-run` when a requested suite did not complete). A failed step outranks every could-not-judge class.

THE RECEIPT is `.ci/cache/win-check/receipt.json`: the envelope of `rediacc_ci.proof.receipt` (identity of the `cli`, `cli-remote` and `renet` surfaces) with `tier` `win`, plus `reason`, `runId`, `runDir`, `vm`, `target`, `suites`, `steps`, `assertions`, `image`, `bundleSha256` and `renetExeSha256`. Nothing reads it to admit a push (D9: `win:check` is a local runner, not a push gate).

`--dry-run` prints the plan and touches nothing. `--selftest` touches nothing: it feeds one planted failing step line through the same judge and verdict and exits 1, printing "selftest fired as designed" only when the verdict came out FAILED.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
from functools import partial
from typing import TYPE_CHECKING, Any

from rediacc_ci.core import local_common, resource_lock
from rediacc_ci.drills import vm_ssh
from rediacc_ci.proof import receipt as receipt_mod

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

NAME = "win:check"
VERIFIED = receipt_mod.VERIFIED
FAILED = receipt_mod.FAILED
NOT_VERIFIED = receipt_mod.NOT_VERIFIED
EXIT_CODES = {VERIFIED: 0, FAILED: 1, NOT_VERIFIED: 77}

TIER = "win"
SCHEMA = 1
SURFACES = ("cli", "cli-remote", "renet")
CACHE_DIR = ".ci/cache/win-check"
LATEST = "receipt.json"
RUNS_DIR = "runs"
RUNS_KEEP = 20
SUITES_DIR = ".ci/rediacc_ci/drills/windows"

DEFAULT_VM = "192.168.111.31"
DEFAULT_WIN_USER = "rdc"
DEFAULT_WORKER = "192.168.111.11"
DEFAULT_WORKER_NAME = "rediacc11"
DEFAULT_CONFIG = "wincheck"
DEFAULT_REMOTE_CONFIG = "winprod"
DEFAULT_WAIT_S = 600.0
GUARD_HOST = "fleet-guard-probe"
WIN_CLIENT_NET = "192.168.111."
WIN_CLIENT_IDS = range(31, 40)

SUITE_ORDER = ("keys", "guard", "term", "sync", "dpapi", "vscode", "gotest")
FLEET_SUITES = ("keys", "guard", "term", "dpapi", "vscode")
SUITE_NEEDS = {"guard": ("keys",), "term": ("keys",), "vscode": ("keys",)}

REMOTE_ROOT = "C:/rdc"
REMOTE_SUITES = REMOTE_ROOT + "/suites"
REMOTE_RENET = REMOTE_ROOT + "/renet"
REMOTE_BUNDLE = REMOTE_ROOT + "/cli-bundle.cjs"
REMOTE_GOTEST = REMOTE_ROOT + "/gotest"

BUNDLE = "packages/cli/dist/cli-bundle.cjs"
RENET_LINUX = "private/renet/bin/renet-linux-amd64"
RENET_EXE = "private/renet/bin/renet-windows-amd64.exe"
# The renet packages whose tests run on Windows (the gotest suite): binary name -> package under private/renet.
GOTEST_PKGS = {"sshexec": "./pkg/infra/sshexec"}

SSH_FAILED = vm_ssh.SSH_FAILED
TIMED_OUT = 124
PROBE_TIMEOUT_S = 60
STAGE_TIMEOUT_S = 600
BUILD_TIMEOUT_S = 1800
SUITE_TIMEOUT_S = 1800

STEP_LINE = re.compile(r"^RDC-STEP (\{.*\})\s*$")
SUITE_LINE = re.compile(r"^RDC-SUITE (\{.*\})\s*$")
PROBE_LINE = re.compile(r"^RDC-PROBE (\w+)=(.*?)\s*$")
EVIDENCE_MAX = 300

# The probe the REACH phase runs on the VM: who the SSH user is, where node is, and the bake's image record when there is one.
PROBE_PS = (
    "$n = (Get-Command node -ErrorAction SilentlyContinue).Source; "
    "'RDC-PROBE node=' + $n; "
    "'RDC-PROBE user=' + $env:USERNAME; "
    "'RDC-PROBE profile=' + $env:USERPROFILE; "
    "$i = 'C:\\rediacc-image.json'; "
    "if (Test-Path $i) { 'RDC-PROBE image=' + ((Get-Content $i -Raw) -replace '\\s+', ' ') }"
)


# --------------------------------------------------------------------------- outcomes


class NotVerifiedError(Exception):
    """The check could not judge: `cls` is the class the receipt quotes."""

    def __init__(self, cls: str, detail: str) -> None:
        super().__init__("%s: %s" % (cls, detail))
        self.cls = cls
        self.detail = detail


@dataclasses.dataclass(frozen=True)
class Result:
    rc: int
    out: str = ""
    err: str = ""

    def text(self) -> str:
        return (self.out + "\n" + self.err).strip()


@dataclasses.dataclass
class SuiteOutcome:
    """What one suite's output proved: its judged rows, the failures among them, and whether it ran to its end."""

    name: str
    rows: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    failures: list[str] = dataclasses.field(default_factory=list)
    completed: bool = False
    detail: str = ""


def clip(text: str, limit: int = EVIDENCE_MAX) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


# --------------------------------------------------------------------------- the judge


def judge_step(suite: str, payload: str) -> tuple[dict[str, Any], str | None]:
    """One `RDC-STEP` payload of `suite` as a receipt row, with the failure it records (None when the step is ok). The driver's own reading of `rc` and `expect` decides; the suite's `ok` must agree with it."""
    try:
        data = json.loads(payload)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        bad: dict[str, Any] = {
            "id": suite + ".?",
            "suite": suite,
            "verdict": "failed",
            "evidence": clip(payload),
        }
        return bad, "%s: malformed RDC-STEP line: %s" % (suite, clip(payload, 120))
    step_id, rc, expect, said = data.get("id"), data.get("rc"), data.get("expect"), data.get("ok")
    row = {
        "id": step_id if isinstance(step_id, str) and step_id else suite + ".?",
        "suite": suite,
        "rc": rc,
        "expect": expect,
        "ok": said,
        "ms": data.get("ms"),
        "evidence": clip(str(data.get("detail") or "")),
        "verdict": "failed",
    }
    problems: list[str] = []
    if not (
        isinstance(step_id, str)
        and step_id.startswith(suite + ".")
        and len(step_id) > len(suite) + 1
    ):
        problems.append("step id %r is not <%s>.<step>" % (step_id, suite))
    if not isinstance(rc, int) or isinstance(rc, bool):
        problems.append("rc %r is not an integer" % (rc,))
    expect_ok = expect == "nonzero" or (isinstance(expect, int) and not isinstance(expect, bool))
    if not expect_ok:
        problems.append('expect %r is neither an integer nor "nonzero"' % (expect,))
    if not isinstance(said, bool):
        problems.append("ok %r is not a boolean" % (said,))
    if "match" in data and not isinstance(data["match"], bool):
        problems.append("match %r is not a boolean" % (data["match"],))
    if problems:
        return row, "%s: %s" % (row["id"], "; ".join(problems))
    want = (rc != 0) if expect == "nonzero" else (rc == expect)
    if data.get("match") is False:
        want = False
    if said != want:
        return row, "%s: the suite says ok=%s, rc %s against expect %s says %s" % (
            step_id,
            str(said).lower(),
            rc,
            expect,
            str(want).lower(),
        )
    if not want:
        why = "rc %s, expected %s" % (rc, expect)
        if data.get("match") is False:
            why += ", output did not match"
        return row, "%s: %s%s" % (
            step_id,
            why,
            (": " + row["evidence"]) if row["evidence"] else "",
        )
    row["verdict"] = "ok"
    return row, None


def parse_suite(suite: str, res: Result) -> SuiteOutcome:
    """Judge one suite's raw output. Only `RDC-STEP` and `RDC-SUITE` lines at the start of a line count; prose is ignored."""
    outcome = SuiteOutcome(suite)
    seen: set[str] = set()
    end: dict[str, Any] | None = None
    for raw in res.out.splitlines():
        line = raw.strip("\r")
        step = STEP_LINE.match(line)
        if step:
            row, failure = judge_step(suite, step.group(1))
            if row["id"] in seen and not row["id"].endswith(".?"):
                failure = failure or "%s: the step id was printed twice" % row["id"]
                row["verdict"] = "failed"
            seen.add(row["id"])
            outcome.rows.append(row)
            if failure:
                outcome.failures.append(failure)
            continue
        tail = SUITE_LINE.match(line)
        if tail:
            try:
                parsed = json.loads(tail.group(1))
            except ValueError:
                parsed = None
            end = parsed if isinstance(parsed, dict) else {}
    steps = len(outcome.rows)
    if res.rc == TIMED_OUT:
        outcome.detail = "%s timed out after %d step line(s)" % (suite, steps)
    elif end is None:
        outcome.detail = "%s printed no RDC-SUITE end line (exit %d, %d step line(s)): %s" % (
            suite,
            res.rc,
            steps,
            clip(res.err or res.out, 160),
        )
    elif end.get("suite") != suite or end.get("steps") != steps:
        outcome.detail = "%s ended as %r but printed %d step line(s)" % (suite, end, steps)
    elif res.rc != 0:
        outcome.detail = "%s exited %d after its end line" % (suite, res.rc)
    else:
        outcome.completed = True
    return outcome


def verdict(
    outcomes: Sequence[SuiteOutcome],
    requested: Sequence[str],
    reason: tuple[str, str] | None,
) -> tuple[str, dict[str, str] | None]:
    """(status, reason) of a run. A failed step is the strongest finding, then a could-not-judge class, then an empty ledger, then a requested suite that did not complete."""
    failures = [f for o in outcomes for f in o.failures]
    if failures:
        detail = failures[0]
        if len(failures) > 1:
            detail += " (and %d more)" % (len(failures) - 1)
        return FAILED, {"class": "step-failed", "detail": detail}
    if reason is not None:
        return NOT_VERIFIED, {"class": reason[0], "detail": reason[1]}
    if not any(o.rows for o in outcomes):
        return NOT_VERIFIED, {
            "class": "no-assertions",
            "detail": "no suite printed an RDC-STEP line, so nothing was judged",
        }
    done = {o.name for o in outcomes if o.completed}
    missing = [s for s in requested if s not in done]
    if missing:
        details = [o.detail for o in outcomes if o.name in missing and o.detail]
        never = [s for s in missing if s not in {o.name for o in outcomes}]
        if never:
            details.append("never ran: " + ", ".join(never))
        return NOT_VERIFIED, {
            "class": "phase-not-run",
            "detail": "requested suite(s) %s did not complete: %s"
            % (", ".join(missing), "; ".join(details)),
        }
    return VERIFIED, None


# --------------------------------------------------------------------------- the plan


@dataclasses.dataclass(frozen=True)
class Options:
    vm: str = DEFAULT_VM
    user: str = DEFAULT_WIN_USER
    key: str = ""
    domain: str = ""
    suites: tuple[str, ...] = FLEET_SUITES
    target: str = "fleet"
    fork: str = ""
    remote_config: str = DEFAULT_REMOTE_CONFIG
    worker: str = DEFAULT_WORKER
    worker_name: str = DEFAULT_WORKER_NAME
    worker_user: str = ""
    fleet_key: str = ""
    wait_s: float = DEFAULT_WAIT_S
    skip_build: bool = False


def plan_suites(asked: Sequence[str] | None, target: str) -> tuple[str, ...]:
    """The suites a run executes, in SUITE_ORDER: the asked ones (default FLEET_SUITES, plus sync on the hostinger target) with what they need."""
    wanted = set(asked) if asked else set(FLEET_SUITES)
    if target == "hostinger" and not asked:
        wanted.add("sync")
    for suite in list(wanted):
        wanted.update(SUITE_NEEDS.get(suite, ()))
    return tuple(s for s in SUITE_ORDER if s in wanted)


def default_domain(vm: str) -> str:
    """The libvirt domain of a Windows client in the reserved range (`rediacc<id>`), else empty (no screenshot)."""
    if vm.startswith(WIN_CLIENT_NET):
        tail = vm[len(WIN_CLIENT_NET) :]
        if tail.isdigit() and int(tail) in WIN_CLIENT_IDS:
            return "rediacc%s" % tail
    return ""


def params_for(
    opts: Options, run_id: str, host_keys: Sequence[str], profile: str
) -> dict[str, Any]:
    """The `params.json` every suite reads through common.ps1."""
    return {
        "runId": run_id,
        "bundle": REMOTE_BUNDLE.replace("/", "\\"),
        "renetDir": REMOTE_RENET.replace("/", "\\"),
        "gotestDir": REMOTE_GOTEST.replace("/", "\\"),
        "config": DEFAULT_CONFIG,
        "key": profile + "\\.ssh\\fleet_rsa",
        "worker": {"ip": opts.worker, "name": opts.worker_name, "user": opts.worker_user},
        "guardHost": GUARD_HOST,
        "expectedHostKeys": sorted(host_keys),
        "target": opts.target,
        "fork": opts.fork,
        "remoteConfig": opts.remote_config if opts.target == "hostinger" else "",
        "remoteDir": "winspike-test",
    }


def gotest_rel(name: str) -> str:
    """The repo-relative path of the cross-compiled test binary for one GOTEST_PKGS entry."""
    return "private/renet/bin/%s.test.exe" % name


def keyscan_keys(out: str) -> list[str]:
    """`<type> <key>` of each `ssh-keyscan` line, without the host field and comments."""
    keys: set[str] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and not parts[0].startswith("#"):
            keys.add("%s %s" % (parts[1], parts[2]))
    return sorted(keys)


def encoded(ps: str) -> str:
    """A PowerShell command line that survives either default shell of Windows OpenSSH (cmd or PowerShell): `-EncodedCommand` with base64 UTF-16LE."""
    return "powershell -NoProfile -NonInteractive -EncodedCommand " + base64.b64encode(
        ps.encode("utf-16-le")
    ).decode("ascii")


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# --------------------------------------------------------------------------- the host


class Host:
    """Every effect outside this process. The tests replace it whole."""

    def __init__(self, root: pathlib.Path, environ: Mapping[str, str] | None = None) -> None:
        self.root = root
        self.environ = dict(os.environ if environ is None else environ)

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        try:
            done = subprocess.run(
                list(argv),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env={**self.environ, **(env or {})},
                cwd=str(self.root),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout
            out = (
                partial.decode("utf-8", "replace")
                if isinstance(partial, bytes)
                else (partial or "")
            )
            return Result(TIMED_OUT, out, "timed out after %ds" % int(timeout))
        except OSError as exc:
            return Result(127, "", str(exc))
        return Result(done.returncode, done.stdout, done.stderr)

    @contextlib.contextmanager
    def fleet_lock(self, wait_s: float) -> Iterator[None]:
        lock = resource_lock.ResourceLock("fleet", environ=self.environ)
        try:
            lock.acquire("win:check", wait_s)
        except resource_lock.ResourceBusyError as exc:
            raise NotVerifiedError("fleet-busy", str(exc)) from None
        try:
            yield
        finally:
            lock.release()

    def account_key(self) -> str:
        return local_common.resolve_renet_account_key(
            str(self.root / "private" / "renet"), self.environ
        )

    def identity(self) -> dict[str, Any]:
        return receipt_mod.identity(self.root, SURFACES)

    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


# --------------------------------------------------------------------------- the run


class Check:
    def __init__(self, opts: Options, host: Host, say: Callable[[str], None] | None = None) -> None:
        self.opts = opts
        self.host = host
        self.root = host.root
        self.say = say or _print
        stamp = host.now().strftime("%Y%m%d-%H%M%S")
        self.run_id = "winc-%s-%s" % (stamp, secrets.token_hex(3))
        self.run_dir = self.root / CACHE_DIR / RUNS_DIR / self.run_id
        self.outcomes: list[SuiteOutcome] = []
        self.image: str = ""
        self.profile = ""
        self.hashes: dict[str, str] = {}

    @property
    def suites(self) -> tuple[str, ...]:
        return self.opts.suites

    # ---- transport

    def ssh(self, command: str, timeout: float = PROBE_TIMEOUT_S) -> Result:
        argv = vm_ssh.ssh_argv(self.opts.user, self.opts.key, self.opts.vm, command)
        return self.host.run(argv, timeout=timeout)

    def scp(self, sources: Sequence[str], dest: str) -> Result:
        argv = [
            "scp",
            "-q",
            "-F",
            "/dev/null",
            "-i",
            self.opts.key,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "IdentityAgent=none",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "LogLevel=ERROR",
            *sources,
            "%s@%s:%s" % (self.opts.user, self.opts.vm, dest),
        ]
        return self.host.run(argv, timeout=STAGE_TIMEOUT_S)

    def scp_gotest(self, name: str) -> Result:
        return self.scp(
            [str(self.root / gotest_rel(name))], "%s/%s.test.exe" % (REMOTE_GOTEST, name)
        )

    # ---- phases

    def reach(self) -> None:
        res = self.ssh(encoded(PROBE_PS))
        probe = {m.group(1): m.group(2) for m in map(PROBE_LINE.match, res.out.splitlines()) if m}
        if res.rc in (SSH_FAILED, TIMED_OUT) or "user" not in probe:
            raise NotVerifiedError(
                "win-vm-unavailable",
                "ssh %s@%s answered rc %d without the probe: %s"
                % (self.opts.user, self.opts.vm, res.rc, clip(res.text(), 160)),
            )
        if not probe.get("node"):
            raise NotVerifiedError(
                "win-bake-missing",
                "%s answers but has no node on its PATH; bake the image (renet ops windows bake) or fetch it"
                % self.opts.vm,
            )
        self.profile = probe.get("profile") or "C:\\Users\\" + probe["user"]
        self.image = probe.get("image", "")
        self.say(
            "win:check: %s answers as %s, node %s" % (self.opts.vm, probe["user"], probe["node"])
        )

    def worker_keys(self) -> list[str]:
        res = self.host.run(
            ["ssh-keyscan", "-T", "10", "-p", "22", self.opts.worker], timeout=PROBE_TIMEOUT_S
        )
        keys = keyscan_keys(res.out)
        if not keys:
            raise NotVerifiedError(
                "worker-unavailable",
                "ssh-keyscan of the worker %s returned no key (rc %d): %s"
                % (self.opts.worker, res.rc, clip(res.err, 160)),
            )
        return keys

    def build(self) -> None:
        if self.opts.skip_build:
            self.say("win:check: --skip-build, staging what is already built")
        else:
            res = self.host.run(["./rdc.sh", "--version"], timeout=BUILD_TIMEOUT_S)
            if res.rc != 0:
                raise NotVerifiedError(
                    "build-failed",
                    "./rdc.sh --version exited %d: %s" % (res.rc, clip(res.err, 200)),
                )
            try:
                account_key = self.host.account_key()
            except local_common.LocalCommonError as exc:
                raise NotVerifiedError("build-failed", "no renet licence key: %s" % exc) from None
            script = (
                'cd private/renet && ./build.sh _go_build -ldflags "-s -w -X main.Version=0.0.0-dev '
                '$(./build.sh key-ldflags)$(./build.sh model-key-ldflags)" '
                "-o bin/renet-windows-amd64.exe ./cmd/renet"
            )
            res = self.host.run(
                ["bash", "-c", "set -euo pipefail; " + script],
                timeout=BUILD_TIMEOUT_S,
                env={
                    "ACCOUNT_ED25519_PUBLIC_KEY": account_key,
                    "GOOS": "windows",
                    "GOARCH": "amd64",
                    "CGO_ENABLED": "0",
                },
            )
            if res.rc != 0:
                raise NotVerifiedError(
                    "build-failed",
                    "the windows renet build exited %d: %s" % (res.rc, clip(res.err, 200)),
                )
            if "gotest" in self.suites:
                for name, pkg in GOTEST_PKGS.items():
                    res = self.host.run(
                        [
                            "bash",
                            "-c",
                            "set -euo pipefail; cd private/renet && go test -c -o %s %s"
                            % ("bin/%s.test.exe" % name, pkg),
                        ],
                        timeout=BUILD_TIMEOUT_S,
                        env={"GOOS": "windows", "GOARCH": "amd64", "CGO_ENABLED": "0"},
                    )
                    if res.rc != 0:
                        raise NotVerifiedError(
                            "build-failed",
                            "the windows %s test binary build exited %d: %s"
                            % (name, res.rc, clip(res.err, 200)),
                        )
        needed = [BUNDLE, RENET_LINUX, RENET_EXE]
        if "gotest" in self.suites:
            needed += [gotest_rel(name) for name in GOTEST_PKGS]
        for rel in needed:
            path = self.root / rel
            if not path.is_file():
                raise NotVerifiedError("build-failed", "%s is missing after the build" % rel)
            self.hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    def stage(self, host_keys: Sequence[str]) -> None:
        suites_dir = self.root / SUITES_DIR
        suite_files = (
            sorted(p for p in suites_dir.glob("*") if p.is_file()) if suites_dir.is_dir() else []
        )
        lacking = [s + ".ps1" for s in self.suites if not (suites_dir / (s + ".ps1")).is_file()]
        if not (suites_dir / "common.ps1").is_file():
            lacking.append("common.ps1")
        if lacking:
            raise NotVerifiedError("stage-failed", "%s lacks %s" % (SUITES_DIR, ", ".join(lacking)))
        params = self.run_dir / "params.json"
        params.write_text(
            json.dumps(params_for(self.opts, self.run_id, host_keys, self.profile), indent=2)
            + "\n",
            encoding="utf-8",
        )
        ssh_dir = self.profile + "\\.ssh"
        prep = (
            "$ErrorActionPreference = 'Stop'; "
            "foreach ($d in 'C:\\rdc\\suites', 'C:\\rdc\\work', 'C:\\rdc\\gotest') { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }; "
            "New-Item -ItemType Directory -Force 'C:\\rdc\\renet', 'C:\\rdc\\suites', 'C:\\rdc\\work', 'C:\\rdc\\gotest', %s | Out-Null; "
            "'RDC-PROBE staged=1'"
        ) % ps_quote(ssh_dir)
        acl = (
            "icacls %s /inheritance:r /grant ($env:USERNAME + ':F') | Out-Null; "
            "'RDC-PROBE acl=' + $LASTEXITCODE"
        ) % ps_quote(ssh_dir + "\\fleet_rsa")
        key_dest = self.profile.replace("\\", "/") + "/.ssh/fleet_rsa"
        steps: list[tuple[str, Callable[[], Result], str]] = [
            ("prepare C:\\rdc", lambda: self.ssh(encoded(prep)), "RDC-PROBE staged=1"),
            ("bundle", lambda: self.scp([str(self.root / BUNDLE)], REMOTE_BUNDLE), ""),
            (
                "renet.exe",
                lambda: self.scp([str(self.root / RENET_EXE)], REMOTE_RENET + "/renet.exe"),
                "",
            ),
            (
                "renet-linux-amd64",
                lambda: self.scp(
                    [str(self.root / RENET_LINUX)], REMOTE_RENET + "/renet-linux-amd64"
                ),
                "",
            ),
            (
                "suites",
                lambda: self.scp(
                    [*(str(p) for p in suite_files), str(params)], REMOTE_SUITES + "/"
                ),
                "",
            ),
            ("fleet key", lambda: self.scp([self.opts.fleet_key], key_dest), ""),
            ("fleet key ACL", lambda: self.ssh(encoded(acl)), "RDC-PROBE acl=0"),
        ]
        if "gotest" in self.suites:
            steps.extend(
                ("%s.test.exe" % name, partial(self.scp_gotest, name), "") for name in GOTEST_PKGS
            )
        for label, act, marker in steps:
            res = act()
            if res.rc != 0 or (marker and marker not in res.out):
                cls = "win-vm-unavailable" if res.rc == SSH_FAILED else "stage-failed"
                raise NotVerifiedError(
                    cls, "staging %s failed (rc %d): %s" % (label, res.rc, clip(res.text(), 160))
                )
        self.say("win:check: staged bundle, renet and %d suite file(s)" % len(suite_files))

    def run_suite(self, suite: str) -> SuiteOutcome:
        self.say("win:check: suite %s" % suite)
        res = self.ssh(
            "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\rdc\\suites\\%s.ps1" % suite,
            timeout=SUITE_TIMEOUT_S,
        )
        (self.run_dir / (suite + ".log")).write_text(res.out, encoding="utf-8")
        (self.run_dir / (suite + ".err")).write_text(res.err, encoding="utf-8")
        outcome = parse_suite(suite, res)
        self.outcomes.append(outcome)
        for row in outcome.rows:
            self.say("  %-6s %s" % ("ok" if row["verdict"] == "ok" else "FAILED", row["id"]))
        if res.rc == SSH_FAILED and not outcome.completed:
            raise NotVerifiedError(
                "win-vm-unavailable",
                "ssh failed during the %s suite: %s" % (suite, clip(res.err, 160)),
            )
        if suite == "vscode" and self.opts.domain:
            shot = self.run_dir / "vscode.png"
            self.host.run(
                ["virsh", "-c", "qemu:///system", "screenshot", self.opts.domain, str(shot)],
                timeout=PROBE_TIMEOUT_S,
            )
        return outcome

    def execute(self) -> tuple[str, dict[str, str] | None]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        reason: tuple[str, str] | None = None
        try:
            self.reach()
            host_keys = self.worker_keys()
            self.build()
            self.stage(host_keys)
            for suite in self.suites:
                self.run_suite(suite)
        except NotVerifiedError as exc:
            reason = (exc.cls, exc.detail)
        return verdict(self.outcomes, self.suites, reason)

    # ---- the record

    def receipt(self, status: str, reason: dict[str, str] | None) -> dict[str, Any]:
        rows = [r for o in self.outcomes for r in o.rows]
        body = {
            "reason": reason,
            "runId": self.run_id,
            "runDir": str(self.run_dir.relative_to(self.root)),
            "vm": {"ip": self.opts.vm, "user": self.opts.user, "domain": self.opts.domain or None},
            "target": self.opts.target,
            "suites": {
                name: {
                    "completed": any(o.name == name and o.completed for o in self.outcomes),
                    "steps": sum(len(o.rows) for o in self.outcomes if o.name == name),
                }
                for name in self.suites
            },
            "steps": rows,
            "assertions": len(rows),
            "image": self.image or None,
            "bundleSha256": self.hashes.get(BUNDLE),
            "renetExeSha256": self.hashes.get(RENET_EXE),
        }
        rec = {**self.host.identity(), **body, "tier": TIER, "schema": SCHEMA, "status": status}
        # The shared envelope names only the vm and live tiers (receipt.TIERS); every other envelope rule holds.
        errors = [e for e in receipt_mod.envelope_errors(rec) if not e.startswith("tier ")]
        if errors:
            raise ValueError("invalid win:check receipt: " + "; ".join(errors))
        return rec

    def write(self, rec: dict[str, Any], *, latest: bool) -> pathlib.Path:
        data = json.dumps(rec, indent=2, sort_keys=True) + "\n"
        path = self.run_dir / LATEST
        receipt_mod.write_atomic(path, data)
        if latest:
            path = self.root / CACHE_DIR / LATEST
            receipt_mod.write_atomic(path, data)
        prune_runs(self.root / CACHE_DIR / RUNS_DIR)
        return path


def _print(line: str) -> None:
    print(line, flush=True)


def prune_runs(runs: pathlib.Path, keep: int = RUNS_KEEP) -> None:
    """Keep the newest `keep` run directories (their names sort by time)."""
    if not runs.is_dir():
        return
    dirs = sorted((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.name)
    for old in dirs[: max(0, len(dirs) - keep)]:
        shutil.rmtree(old, ignore_errors=True)


def run_check(opts: Options, host: Host, say: Callable[[str], None] | None = None) -> int:
    check = Check(opts, host, say)
    try:
        with host.fleet_lock(opts.wait_s):
            status, reason = check.execute()
            latest = True
    except NotVerifiedError as exc:
        status, reason, latest = NOT_VERIFIED, {"class": exc.cls, "detail": exc.detail}, False
        check.run_dir.mkdir(parents=True, exist_ok=True)
    path = check.write(check.receipt(status, reason), latest=latest)
    line = "%s: %s" % (NAME, status)
    if reason:
        line += " (%s: %s)" % (reason["class"], reason["detail"])
    check.say(line)
    check.say(
        "%s: receipt %s, evidence %s"
        % (NAME, path.relative_to(host.root), check.run_dir.relative_to(host.root))
    )
    return EXIT_CODES[status]


def selftest(say: Callable[[str], None]) -> int:
    planted = Result(
        0,
        'RDC-STEP {"id": "keys.planted", "rc": 1, "expect": 0, "ok": false}\n'
        'RDC-SUITE {"suite": "keys", "steps": 1}\n',
    )
    status, reason = verdict([parse_suite("keys", planted)], ("keys",), None)
    if status == FAILED:
        say("%s: selftest fired as designed (%s)" % (NAME, reason["detail"] if reason else ""))
        return 1
    say("%s: SELFTEST DID NOT FIRE: a planted failing step came out %s" % (NAME, status))
    return 2


def dry_run(opts: Options, say: Callable[[str], None]) -> int:
    say("%s plan (touches nothing):" % NAME)
    shot = ", screenshot of " + opts.domain if opts.domain else ""
    say("  vm        %s@%s (key %s)%s" % (opts.user, opts.vm, opts.key, shot))
    say(
        "  worker    %s %s@%s (fleet key %s)"
        % (opts.worker_name, opts.worker_user, opts.worker, opts.fleet_key)
    )
    fork = (
        " fork %s under config %s" % (opts.fork, opts.remote_config)
        if opts.target == "hostinger"
        else ""
    )
    say("  target    %s%s" % (opts.target, fork))
    say(
        "  build     %s"
        % ("skipped" if opts.skip_build else "./rdc.sh --version, then " + RENET_EXE)
    )
    say("  stage     %s, %s, %s, %s/*" % (BUNDLE, RENET_EXE, RENET_LINUX, SUITES_DIR))
    if "gotest" in opts.suites:
        say("  gotest    GOOS=windows go test -c: %s" % ", ".join(sorted(GOTEST_PKGS.values())))
    say("  suites    %s" % ", ".join(opts.suites))
    say("  receipt   %s/%s; best verdict VERIFIED (exit 0)" % (CACHE_DIR, LATEST))
    return 0


def parse_args(
    argv: Sequence[str] | None, environ: Mapping[str, str]
) -> tuple[argparse.Namespace, Options]:
    p = argparse.ArgumentParser(
        prog="npm run win:check --",
        description="Drive rdc on a Windows VM over SSH and judge its RDC-STEP lines.",
    )
    p.add_argument(
        "--vm", default=DEFAULT_VM, help="the Windows VM's address (default %(default)s)"
    )
    p.add_argument(
        "--user", default=DEFAULT_WIN_USER, help="the Windows SSH user (default %(default)s)"
    )
    p.add_argument(
        "--key", default="", help="the key that reaches the Windows VM (default the fleet key)"
    )
    p.add_argument("--domain", default=None, help="the libvirt domain for the vscode screenshot")
    p.add_argument(
        "--suite", default="", help="comma-separated suites (%s)" % ", ".join(SUITE_ORDER)
    )
    p.add_argument("--target", choices=("fleet", "hostinger"), default="fleet")
    p.add_argument(
        "--fork", default="", help="the hostinger fork <repo:tag> (with --target hostinger)"
    )
    p.add_argument(
        "--remote-config",
        default=DEFAULT_REMOTE_CONFIG,
        help="the VM-side config that knows the fork (default %(default)s)",
    )
    p.add_argument("--worker", default=DEFAULT_WORKER)
    p.add_argument("--worker-name", default=DEFAULT_WORKER_NAME)
    p.add_argument(
        "--worker-user", default="", help="the worker's SSH user (default the ops VM user)"
    )
    p.add_argument(
        "--wait", type=float, default=DEFAULT_WAIT_S, help="seconds to wait for the fleet lock"
    )
    p.add_argument("--skip-build", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--selftest", action="store_true")
    ns = p.parse_args(argv)
    asked = [s.strip() for s in ns.suite.split(",") if s.strip()]
    unknown = [s for s in asked if s not in SUITE_ORDER]
    if unknown:
        p.error("unknown suite(s) %s; known: %s" % (", ".join(unknown), ", ".join(SUITE_ORDER)))
    suites = plan_suites(asked, ns.target)
    if ("sync" in suites or ns.target == "hostinger") and not (
        ns.target == "hostinger" and ns.fork
    ):
        p.error("the sync suite and --target hostinger need --target hostinger --fork <repo:tag>")
    fleet_key = vm_ssh.default_key(environ)
    opts = Options(
        vm=ns.vm,
        user=ns.user,
        key=ns.key or fleet_key,
        domain=default_domain(ns.vm) if ns.domain is None else ns.domain,
        suites=suites,
        target=ns.target,
        fork=ns.fork,
        remote_config=ns.remote_config,
        worker=ns.worker,
        worker_name=ns.worker_name,
        worker_user=ns.worker_user or vm_ssh.default_user(environ),
        fleet_key=fleet_key,
        wait_s=ns.wait,
        skip_build=ns.skip_build,
    )
    return ns, opts


def repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3]


def main(argv: Sequence[str] | None = None) -> int:
    ns, opts = parse_args(argv, os.environ)
    if ns.selftest:
        return selftest(_print)
    if ns.dry_run:
        return dry_run(opts, _print)
    return run_check(opts, Host(repo_root()), _print)


if __name__ == "__main__":
    sys.exit(main())

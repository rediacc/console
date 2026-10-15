"""`npm run vm:check`: drive the repo shell, sync, SFTP and VS Code paths of `rdc` against the ops VMs, and write the receipt the push guard reads.

    npm run vm:check [-- --changed] [--os <image>] [--parent <grand>] [--machine <name>] [--wait <s>] [--selftest] [--keep-work]
    ./run.sh drill vmcheck [same flags]

Design 2 of agent/plans/PLAN-vm-check.md is the specification; each step below carries its id there.

  P0  an exclusive flock on `rediacc-vm-check.lock` in the per-user runtime directory, waited for up to `--wait` seconds (`fleet-busy`).
  P1  `go version -m private/renet/bin/renet` must carry the submodule HEAD as `vcs.revision` and `vcs.modified=false`; one `./rdc.sh --version` rebuild is tried before `renet-build-mismatch`.
  P2  `/dev/kvm` and `virsh` (`no-kvm`); `rdc ops status -o json`: the bridge (.1) and the worker (.11) both running is REUSE, neither is COLD (`ops up --basic`), anything else is `fleet-unavailable`. The worker's machine name comes from `machine list` (`worker-not-in-config`).
  P3  `machine scan-keys <worker>` before any other ssh, then the worker's /etc/os-release, which under `--os` must match a reused fleet (`fleet-os-mismatch`). A config with no SSH key (`config ssh show` says `embedded: no`) gets the key the ops VMs authorize (`config ssh set --key`, the license drill's step), since the CLI would otherwise offer ~/.ssh/id_rsa or id_ed25519, which the VMs reject; a config holding another key is never overwritten, and a failing `config ssh show` leaves the config alone and lets P5 judge. P3's own os-release probe uses the drill's key, not the CLI's, so its failure stays `fleet-unavailable`; the CLI's key is first used at P5, where an ssh authentication refusal is `worker-ssh-key`.
  P4  the stored token is used when `subscription status` accepts it. Otherwise a token is minted on the running dev gateway for the dedicated login ACCOUNT_LOGIN, with a password generated per run and held in memory (`account-unavailable`). The token reaches `rdc` only as REDIACC_TOKEN in the child environment: never on argv, never in the config, never printed, never in the receipt.
  P5  the parent must be a grand on the worker (`parent-grand-missing`); stale `vmc-` forks of it older than an hour are deleted, nothing else is touched.
  V1.1-V1.7  two forks, cross-repo read-only denial, the positive set, isolation, sync round trip, VS Code URL and SFTP confinement.
  T   in `finally`, also after SIGINT and SIGTERM (a handler raises `RunInterruptedError`): `vscode cleanup`, `repo delete` of this run's forks, a `repo list` proving neither tag remains, `ops down` only for a fleet this run started, then the lock. Leftovers turn a VERIFIED run into NOT_VERIFIED `teardown-failed`; a FAILED run stays FAILED and its detail lists them.

THE RULES. Every VM action goes through `./rdc.sh`. Nothing here sets or clears REDIACC_AGENT, CLAUDECODE or REDIACC_ALLOW_*: a verb the CLI's agent guard refuses ends the run NOT_VERIFIED `agent-policy-refused` with the refusal's first line. The raw `ssh` probes and the `sftp -b` leg are built from the constants below. Nothing is uploaded with scp.

VERDICTS. VERIFIED exit 0 (assertions ran, none failed, teardown clean); FAILED exit 1 (a V-step assertion failed); NOT_VERIFIED exit 77 (the check could not judge). A run that recorded no assertion is never VERIFIED. `--selftest` touches no machine: it feeds one planted failing assertion through the same `verdict` the real run uses and exits non-zero, printing "selftest fired as designed" only when that verdict came out FAILED.

`--changed` evaluates `vm_check_trigger` against the push base in worktree mode; with no hit it prints the no-op line, writes no receipt and exits 0.

The whole flow runs through `Host`, so the tests drive it with a fake host and a fake account and never reach a VM.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import fcntl
import hashlib
import http.cookiejar
import json
import os
import pathlib
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import time
import traceback
from typing import TYPE_CHECKING, Any, Protocol

from rediacc_ci import log, paths
from rediacc_ci.drills import lib, vm_ssh, wire
from rediacc_ci.drills import vm_check_receipt as receipt_mod
from rediacc_ci.drills import vm_check_trigger as trigger
from rediacc_ci.well_known import DATASTORE_PATH

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

NAME = "vm:check"
EXIT_VERIFIED = 0
EXIT_FAILED = 1
EXIT_NOT_VERIFIED = 77
EXIT_CODES = {
    receipt_mod.VERIFIED: EXIT_VERIFIED,
    receipt_mod.FAILED: EXIT_FAILED,
    receipt_mod.NOT_VERIFIED: EXIT_NOT_VERIFIED,
}

LOCK_NAME = "rediacc-vm-check.lock"
DEFAULT_WAIT_S = 600
DEFAULT_PARENT = "vmcheck-base"
DEFAULT_NET_BASE = "192.168.111"
BRIDGE_SUFFIX = ".1"
WORKER_SUFFIX = ".11"
REUSED = "reused"
COLD = "cold"

ACCOUNT_LOGIN = "vm-check@rediacc.dev"
ACCOUNT_PLAN = "PROFESSIONAL"
MINT_LABEL = "vm-check"
TOKEN_SCOPES = ("license:read", "license:activate", "subscription:read")

TAG_PREFIX = "vmc"
STALE_FORK_S = 3600
FORK_TAG = re.compile(r"^vmc-(\d{8})-([0-9a-f]{6})-[ab]$")
MOUNTS = DATASTORE_PATH + "/mounts"
GUARDED_FILE = ".rediacc.json"
READ_ONLY = "Read-only file system"
VSCODE_ABSENT = "VS Code not found"
URI_PREFIX = "vscode-remote://ssh-remote+"
SYNC_BIG_BYTES = 1024 * 1024

# The raw probes: read-only, and the only ssh/sftp argv this module builds besides `sftp -b` below.
PROBE_RENET_HASH = "renet hash"
PROBE_OS_RELEASE = '. /etc/os-release && printf "%s %s\\n" "$ID" "$VERSION_ID"'
SFTP_BATCH = ("sftp", "-q", "-o", "BatchMode=yes", "-b")
# A refused sftp leg counts as confinement only when the server says so; a dropped connection or a missing path is not a refusal.
SFTP_DENIAL = re.compile(
    r"permission denied|read-only file system|operation not permitted", re.IGNORECASE
)
# ssh's own failed login (`user@host: Permission denied (publickey,password).`) is not a server-side refusal: the connection never authenticated, so nothing was confined. The method list is hyphenated words joined by single commas, with an optional trailing comma: the comma is the only separator, so each character has one way to match and a line with no closing paren fails in linear time.
SSH_AUTH_FAILURE = re.compile(
    r"permission denied \([a-z-]+(?:,[a-z-]+)*,?\)|too many authentication failures",
    re.IGNORECASE,
)


def sftp_refused(output: str) -> bool:
    """True when the sftp output holds a refusal from the server's side of an authenticated session. Lines that report an ssh authentication failure are set aside before the denial is looked for."""
    lines = [ln for ln in output.splitlines() if not SSH_AUTH_FAILURE.search(ln)]
    return bool(SFTP_DENIAL.search("\n".join(lines)))


# First-line markers of a refusal by the CLI's agent guard (packages/cli/src/utils/agent-guard.ts, command-policy.ts).
AGENT_REFUSALS = (
    "agent mode",
    "agent environments",
    "Agents cannot",
    "Agent-initiated overrides",
    "not available on fork repositories",
    "origin could not be verified",
)

# What a step can raise that still ends in a receipt and a teardown; anything else propagates after the teardown in `finally`.
CRASHES = (
    OSError,
    RuntimeError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    subprocess.SubprocessError,
)

# The image names `ops up --os` accepts are `<distro>-<version>`; /etc/os-release spells a few distros differently.
OS_ALIASES = {"oracle": "ol", "opensuse": "opensuse-leap"}


# --------------------------------------------------------------------------- outcomes


class NotVerifiedError(Exception):
    """The check could not judge: `cls` is the class the receipt and the guard quote."""

    def __init__(self, cls: str, detail: str) -> None:
        super().__init__("%s: %s" % (cls, detail))
        self.cls = cls
        self.detail = detail


class RunInterruptedError(Exception):
    """SIGINT or SIGTERM arrived; `finally` still tears down."""


@dataclasses.dataclass(frozen=True)
class Result:
    rc: int
    out: str = ""
    err: str = ""
    ms: int = 0

    def text(self) -> str:
        return (self.out + "\n" + self.err).strip()


def verdict(
    assertions: int,
    failures: list[str],
    reason: tuple[str, str] | None,
    leftovers: Sequence[str],
) -> tuple[str, dict[str, str] | None]:
    """(status, reason) of a run. A failed assertion is the strongest finding, then a could-not-judge class, then an empty ledger, then the teardown."""
    if failures:
        detail = failures[0]
        if leftovers:
            detail += "; teardown left: " + ", ".join(leftovers)
        return receipt_mod.FAILED, {"class": "step-failed", "detail": detail}
    if reason is not None:
        cls, detail = reason
        if leftovers:
            detail += "; teardown left: " + ", ".join(leftovers)
        return receipt_mod.NOT_VERIFIED, {"class": cls, "detail": detail}
    if assertions == 0:
        return receipt_mod.NOT_VERIFIED, {
            "class": "no-assertions",
            "detail": "the run recorded no assertion, so nothing was judged",
        }
    if leftovers:
        return receipt_mod.NOT_VERIFIED, {
            "class": "teardown-failed",
            "detail": "teardown left: " + ", ".join(leftovers),
        }
    return receipt_mod.VERIFIED, None


# --------------------------------------------------------------------------- the outside world


class Host:
    """Every effect the check has outside this process. The tests replace it whole."""

    def run(
        self,
        argv: Sequence[str],
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Result:
        started = time.monotonic()
        try:
            proc = subprocess.run(
                list(argv),
                capture_output=True,
                text=True,
                env=dict(env) if env is not None else None,
                timeout=timeout,
                check=False,
            )
        except OSError as exc:
            return Result(127, "", "%s: %s" % (argv[0], exc.strerror or exc), self._ms(started))
        except subprocess.TimeoutExpired as exc:
            err = exc.stderr if isinstance(exc.stderr, str) else ""
            return Result(124, "", err + "\ntimed out after %ss" % timeout, self._ms(started))
        return Result(proc.returncode, proc.stdout, proc.stderr, self._ms(started))

    @staticmethod
    def _ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def sha256(self, path: pathlib.Path) -> str | None:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class Account(Protocol):
    def gateway_healthy(self) -> bool: ...

    def mint(self, password: str) -> str: ...


class DrillAccount:
    """The dev gateway through `lib.Drill`'s helpers. Never starts or restarts the gateway: every start re-randomizes the dev passwords."""

    def __init__(self, drill: lib.Drill) -> None:
        self.drill = drill

    def gateway_healthy(self) -> bool:
        return self.drill.gateway_alive()

    def mint(self, password: str) -> str:
        d = self.drill
        d.gateway_port_cached = d.gateway_port()
        d.account_ensure_login(ACCOUNT_LOGIN, password)
        d.account_ensure_subscription(ACCOUNT_LOGIN, ACCOUNT_PLAN)
        jar = http.cookiejar.CookieJar()
        if not d.account_session(ACCOUNT_LOGIN, password, jar):
            raise lib.GatewayError("no session for %s" % ACCOUNT_LOGIN)
        subscription = d.account_subscription_id(jar)
        if not subscription:
            raise lib.GatewayError("no subscription for %s" % ACCOUNT_LOGIN)
        return d.account_mint_token(jar, subscription, MINT_LABEL, list(TOKEN_SCOPES))


# --------------------------------------------------------------------------- the lock


def lock_path(environ: Mapping[str, str] | None = None) -> pathlib.Path:
    """`$XDG_RUNTIME_DIR`, then `/run/user/<uid>`, each only when it is this user's directory, then a per-user name in the literal /tmp (the order rediacc_ci.core_lease uses)."""
    env = os.environ if environ is None else environ
    uid = os.getuid()
    for runtime in ((env.get("XDG_RUNTIME_DIR") or "").strip(), "/run/user/%d" % uid):
        with contextlib.suppress(OSError):
            if runtime and os.path.isdir(runtime) and os.stat(runtime).st_uid == uid:
                return pathlib.Path(runtime) / LOCK_NAME
    return pathlib.Path("/tmp") / ("rediacc-vm-check-%d.lock" % uid)


class Lock:
    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.fd: int | None = None

    def acquire(self, host: Host, wait_s: float, session: str) -> float:
        """Seconds waited. Raises NotVerifiedError `fleet-busy` naming the holder when the wait runs out."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        started = host.monotonic()
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                waited = host.monotonic() - started
                if waited >= wait_s:
                    holder = self._holder(fd)
                    os.close(fd)
                    raise NotVerifiedError(
                        "fleet-busy",
                        "another vm:check holds %s after %ds: %s"
                        % (self.path, int(waited), holder),
                    ) from None
                host.sleep(min(1.0, max(0.0, wait_s - waited)))
        self.fd = fd
        os.ftruncate(fd, 0)
        os.pwrite(
            fd,
            json.dumps(
                {"pid": os.getpid(), "session": session, "since": _iso(host.now())}
            ).encode(),
            0,
        )
        return host.monotonic() - started

    @staticmethod
    def _holder(fd: int) -> str:
        try:
            raw = os.pread(fd, 4096, 0).decode(errors="replace")
            data = json.loads(raw)
        except (OSError, ValueError):
            return "holder unknown"
        return "pid %s, session %s, since %s" % (
            data.get("pid"),
            data.get("session"),
            data.get("since"),
        )

    def release(self) -> None:
        if self.fd is None:
            return
        with contextlib.suppress(OSError):
            os.ftruncate(self.fd, 0)
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)
        self.fd = None


# --------------------------------------------------------------------------- parsing helpers


def _iso(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _data_list(raw: str) -> list[dict[str, Any]]:
    """The array of a CLI `-o json` envelope (`data`), or a bare array."""
    parsed = wire.parse(raw)
    data = wire.lookup(parsed, "data")
    if not isinstance(data, list):
        data = parsed
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict)]


def go_buildinfo(text: str) -> tuple[str, bool | None]:
    """(vcs.revision, vcs.modified) of `go version -m`; ("", None) for what it does not carry."""
    revision = ""
    modified: bool | None = None
    for line in text.splitlines():
        field = line.strip().split("\t")[-1].strip()
        if field.startswith("vcs.revision="):
            revision = field.split("=", 1)[1]
        elif field.startswith("vcs.modified="):
            modified = field.split("=", 1)[1] == "true"
    return revision, modified


def os_matches(image: str, os_id: str, version: str) -> bool:
    """`ubuntu-24.04` against /etc/os-release's `ubuntu 24.04`; `rocky-9` against `rocky 9.4`."""
    distro, _, wanted = image.rpartition("-")
    if not distro:
        return False
    return os_id in (distro, OS_ALIASES.get(distro, distro)) and (
        version == wanted or version.startswith(wanted + ".")
    )


def fork_tags(stamp: str, nonce: str) -> tuple[str, str]:
    return ("%s-%s-%s-a" % (TAG_PREFIX, stamp, nonce), "%s-%s-%s-b" % (TAG_PREFIX, stamp, nonce))


def stamp_age_s(stamp: str, now: float) -> float | None:
    """Seconds since an MMDDHHMM UTC stamp, taking the year that puts it in the past; None for a stamp that is no date."""
    current = datetime.datetime.fromtimestamp(now, datetime.UTC)
    for year in (current.year, current.year - 1):
        try:
            when = datetime.datetime.strptime("%d%s" % (year, stamp), "%Y%m%d%H%M").replace(
                tzinfo=datetime.UTC
            )
        except ValueError:
            continue
        if when.timestamp() <= now + 60:
            return now - when.timestamp()
    return None


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def last_lines(text: str, count: int = 3) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " | ".join(lines[-count:])


def rdc_failure(res: Result) -> str:
    """Why an `rdc` call failed. With `-o json` the CLI puts its errors in the JSON envelope on stdout and only progress lines on stderr, so a reason read from stderr alone named "Listing repositories..." and dropped `SSH connection error: connect EHOSTUNREACH` (2026-10-14T23:53Z)."""
    try:
        doc = json.loads(res.out)
    except (ValueError, TypeError):
        doc = None
    if isinstance(doc, dict):
        msgs = [
            str(e.get("message") or e.get("code") or e)
            for e in (doc.get("errors") or [])
            if isinstance(e, dict)
        ]
        if msgs:
            return " | ".join(msgs[:3])
        # An envelope with no error entry is data, not a diagnosis; its raw tail would read as one.
        return last_lines(res.err) or "rc=%d with no error in the CLI's JSON envelope" % res.rc
    return last_lines(res.err) or last_lines(res.out)


# --------------------------------------------------------------------------- options


@dataclasses.dataclass
class Options:
    changed: bool = False
    os_image: str = ""
    parent: str = DEFAULT_PARENT
    machine: str = ""
    wait_s: float = DEFAULT_WAIT_S
    selftest: bool = False
    keep_work: bool = False
    net_base: str = DEFAULT_NET_BASE


def parse_args(argv: Sequence[str], environ: Mapping[str, str] | None = None) -> Options:
    env = os.environ if environ is None else environ
    selftest, keep_work, rest = lib.parse_common_args(list(argv))
    parser = argparse.ArgumentParser(
        prog="npm run vm:check --", description=__doc__.split("\n", 1)[0]
    )
    parser.add_argument("--changed", action="store_true")
    parser.add_argument("--os", dest="os_image", default="")
    parser.add_argument("--parent", default=env.get("VM_CHECK_PARENT") or DEFAULT_PARENT)
    parser.add_argument("--machine", default="")
    parser.add_argument("--wait", dest="wait_s", type=float, default=DEFAULT_WAIT_S)
    ns = parser.parse_args(rest)
    return Options(
        changed=ns.changed,
        os_image=ns.os_image,
        parent=ns.parent,
        machine=ns.machine,
        wait_s=ns.wait_s,
        selftest=selftest,
        keep_work=keep_work,
        net_base=env.get("VM_NET_BASE") or DEFAULT_NET_BASE,
    )


# --------------------------------------------------------------------------- the check


class VmCheck:
    def __init__(
        self,
        root: pathlib.Path,
        opts: Options,
        host: Host,
        account: Account,
        work: pathlib.Path,
        lock: Lock,
        out=None,
        environ: Mapping[str, str] | None = None,
        inputs_fn: Callable[[pathlib.Path], str | None] = trigger.inputs,
    ) -> None:
        self.root = root
        self.opts = opts
        self.host = host
        self.account = account
        self.work = work
        self.lock = lock
        self.out = out if out is not None else sys.stdout
        self.environ = dict(os.environ if environ is None else environ)
        self.inputs_fn = inputs_fn
        self.rdc_sh = str(root / "rdc.sh")
        self.renet_bin = root / trigger.RENET_SUBMODULE / "bin" / "renet"
        self.ssh_user = vm_ssh.default_user(self.environ)
        self.ssh_key = vm_ssh.default_key(self.environ)
        self.bridge_ip = opts.net_base + BRIDGE_SUFFIX
        self.worker_ip = opts.net_base + WORKER_SUFFIX
        # Ledger
        self.steps: list[dict[str, Any]] = []
        self.assertions = 0
        self.failures: list[str] = []
        self.reason: tuple[str, str] | None = None
        self.leftovers: list[str] = []
        # Run state
        self.token: str | None = None
        self.password: str | None = None
        self.locked = False
        self.fleet_mode = ""
        self.fleet_started = False
        self.fleet_os = ""
        self.ips: list[str] = []
        self.machine = opts.machine
        self.landlock: dict[str, str] = {}
        self.forks: list[dict[str, Any]] = []
        self.guids: dict[str, str] = {}
        self.network_ids: dict[str, str] = {}
        self.connection = ""
        self.renet: dict[str, Any] = {
            "pointer": "",
            "checkout": "",
            "built": "",
            "modified": None,
            "deployed": None,
        }
        self.trigger_info: dict[str, Any] = {"base": None, "via": "always", "hits": []}
        self.tree = ""
        self.head = ""
        self.inputs: str | None = None
        self.run_id = ""
        self.started_at = 0.0
        self.started_mono = 0.0
        self.b_stat = ""
        self.tags: tuple[str, str] = ("", "")

    # ------------------------------------------------------------------ output

    def say(self, text: str = "") -> None:
        print(text, file=self.out)
        self.out.flush()

    def scrub(self, text: str) -> str:
        """`text` with the minted token and the login password removed, should a child or an exception ever echo them."""
        if self.token:
            text = text.replace(self.token, "<token>")
        if self.password:
            text = text.replace(self.password, "<password>")
        return text

    def _clean(self, text: str) -> str:
        """Evidence from a child's output, clipped and scrubbed."""
        return receipt_mod.clip_evidence(" ".join(self.scrub(text).split()))

    def record(
        self,
        step_id: str,
        desc: str,
        ok: bool | None,
        res: Result | None = None,
        evidence: str = "",
        *,
        assertion: bool = False,
    ) -> bool:
        """One ledger row. `ok` None is a skip; `assertion` counts it towards the verdict's ledger."""
        verdict_text = "skip" if ok is None else ("ok" if ok else "FAIL")
        row = {
            "id": step_id,
            "desc": desc,
            "rc": res.rc if res is not None else 0,
            "verdict": verdict_text,
            "ms": res.ms if res is not None else 0,
            "evidence": self._clean(evidence or (res.text() if res is not None and not ok else "")),
        }
        self.steps.append(row)
        if assertion and ok is not None:
            self.assertions += 1
            if not ok:
                self.failures.append("%s: %s (%s)" % (step_id, desc, row["evidence"]))
        self.say("  %-5s %-5s %s" % (step_id, verdict_text, desc))
        return bool(ok)

    def check(
        self, step_id: str, desc: str, ok: bool, res: Result | None = None, evidence: str = ""
    ) -> bool:
        return self.record(step_id, desc, ok, res, evidence, assertion=True)

    # ------------------------------------------------------------------ commands

    def child_env(self) -> dict[str, str]:
        env = dict(self.environ)
        if self.token:
            env["REDIACC_TOKEN"] = self.token
        return env

    def git(self, *args: str, cwd: pathlib.Path | None = None) -> str:
        res = self.host.run(["git", "-C", str(cwd or self.root), *args], env=self.environ)
        return res.out.strip() if res.rc == 0 else ""

    def rdc(self, *args: str, timeout: float | None = None, refuse: bool = True) -> Result:
        """`./rdc.sh <args>` with the child environment. A refusal by the agent guard ends the run (unless `refuse` is False, as in teardown)."""
        res = self.host.run([self.rdc_sh, *args], env=self.child_env(), timeout=timeout)
        if refuse and res.rc != 0 and any(m in res.err for m in AGENT_REFUSALS):
            raise NotVerifiedError(
                "agent-policy-refused",
                "rdc %s: %s" % (" ".join(args[:3]), first_line(res.err)),
            )
        return res

    def shell(self, fork: str, command: str) -> Result:
        return self.rdc("term", "connect", fork, "-c", command)

    def probe(self, command: str) -> Result:
        return self.host.run(
            vm_ssh.ssh_argv(self.ssh_user, self.ssh_key, self.worker_ip, command),
            env=self.environ,
            timeout=60,
        )

    def ref(self, tag: str) -> str:
        return "%s:%s" % (self.opts.parent, tag)

    def mount(self, tag: str) -> str:
        return "%s/%s" % (MOUNTS, self.guids.get(tag, "<unknown>"))

    def repo_list(self) -> tuple[Result, list[dict[str, Any]]]:
        res = self.rdc("repo", "list", "-m", self.machine, "-o", "json", refuse=False)
        return res, _data_list(res.out) if res.rc == 0 else []

    # ------------------------------------------------------------------ the run

    def run(self) -> int:
        self.started_at = self.host.now()
        self.started_mono = self.host.monotonic()
        stamp = datetime.datetime.fromtimestamp(self.started_at, datetime.UTC).strftime("%m%d%H%M")
        nonce = secrets.token_hex(3)
        self.tags = fork_tags(stamp, nonce)
        self.run_id = "vmc-%s-%s" % (stamp, nonce)
        self.say("\n=== %s %s ===" % (NAME, self.run_id))
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.head = self.git("rev-parse", "HEAD")
        if self.opts.changed and not self._evaluate_trigger():
            return EXIT_VERIFIED
        self.inputs = self.inputs_fn(self.root)
        previous = self._install_signals()
        try:
            self._steps()
        except NotVerifiedError as exc:
            self.reason = (exc.cls, self.scrub(exc.detail))
            self.record("--", "stopped: %s" % exc.cls, False, evidence=exc.detail)
        except RunInterruptedError as exc:
            self.reason = ("interrupted", self.scrub(str(exc)))
            self.record("--", "stopped: interrupted", False, evidence=str(exc))
        except CRASHES as exc:
            self.reason = ("crashed", self.scrub("%s: %s" % (type(exc).__name__, exc)))
            log.error("vm:check crashed:\n%s" % self.scrub(traceback.format_exc().rstrip()))
            self.record("--", "stopped: crashed", False, evidence=self.reason[1])
        finally:
            self._quiet_signals()
            self._teardown()
            self._restore_signals(previous)
        return self._finish()

    def _evaluate_trigger(self) -> bool:
        """True when the trigger fires (or cannot be evaluated); False after printing the no-op line."""
        git = trigger.make_git(self.root)
        branch = git(["rev-parse", "--abbrev-ref", "HEAD"])
        base = trigger.push_base(git, branch if branch and branch != "HEAD" else None)
        for warning in base.warnings:
            self.say("vm:check: %s" % warning)
        if base.merge_base is None:
            self.say(
                "vm:check: no push base resolved (tried %s); running the full check"
                % ", ".join(base.tried)
            )
            self.trigger_info = {"base": None, "via": "unresolved", "hits": []}
            return True
        changed = trigger.changed_paths(self.root, base.merge_base, "worktree")
        self.trigger_info = {
            "base": base.ref,
            "via": base.via,
            "hits": [*changed.hits, *("unknown " + u for u in changed.unknown)],
        }
        if not changed.touched:
            self.say(
                "vm:check: no trigger path changed since %s (via %s); nothing to verify"
                % (base.ref, base.via)
            )
            return False
        self.say(
            "vm:check: %d trigger path(s) changed since %s (via %s):"
            % (len(self.trigger_info["hits"]), base.ref, base.via)
        )
        for hit in self.trigger_info["hits"][:10]:
            self.say("  %s" % hit)
        return True

    def _steps(self) -> None:
        self.p0_lock()
        self.p1_renet()
        self.p2_fleet()
        self.p3_keys()
        self.p4_account()
        self.p5_parent()
        if not self.v1_1_forks():
            return
        self.v1_2_cross_repo()
        self.v1_3_positive()
        self.v1_4_isolation()
        self.v1_5_sync()
        self.v1_6_vscode()
        self.v1_7_sftp()

    # ------------------------------------------------------------------ P

    def p0_lock(self) -> None:
        session = (self.environ.get("CLAUDE_CODE_SESSION_ID") or "-")[:8]
        waited = self.lock.acquire(self.host, self.opts.wait_s, session)
        self.locked = True
        self.record("P0", "lock acquired (waited %d s)" % int(waited), True)

    def _read_build(self) -> tuple[str, bool | None]:
        res = self.host.run(["go", "version", "-m", str(self.renet_bin)], env=self.environ)
        return go_buildinfo(res.out) if res.rc == 0 else ("", None)

    def p1_renet(self) -> None:
        self.renet["pointer"] = self.git("rev-parse", "HEAD:%s" % trigger.RENET_SUBMODULE)
        checkout = self.git("rev-parse", "HEAD", cwd=self.root / trigger.RENET_SUBMODULE)
        self.renet["checkout"] = checkout
        built, modified = self._read_build()
        rebuilt = False
        if not checkout or built != checkout or modified is not False:
            self.say(
                "        renet build %s (modified=%s) is not the checkout %s; rebuilding through ./rdc.sh --version"
                % (built[:12] or "<none>", modified, checkout[:12] or "<none>")
            )
            self.rdc("--version", timeout=1800)
            built, modified = self._read_build()
            rebuilt = True
        self.renet["built"] = built
        self.renet["modified"] = modified
        if not checkout or built != checkout or modified is not False:
            raise NotVerifiedError(
                "renet-build-mismatch",
                "bin/renet carries vcs.revision=%s vcs.modified=%s, the private/renet checkout is %s"
                % (built[:12] or "<none>", modified, checkout[:12] or "<none>"),
            )
        self.record(
            "P1", "renet %s built clean%s" % (built[:12], " (rebuilt)" if rebuilt else ""), True
        )

    def p2_fleet(self) -> None:
        if not self.host.exists("/dev/kvm") or not self.host.which("virsh"):
            raise NotVerifiedError("no-kvm", "/dev/kvm or virsh is missing on this host")
        status = self.rdc("ops", "status", "-o", "json")
        if status.rc != 0:
            raise NotVerifiedError(
                "fleet-unavailable", "ops status rc=%d: %s" % (status.rc, rdc_failure(status))
            )
        running = lib.running_ips(status.out)
        have = {self.bridge_ip in running, self.worker_ip in running}
        if have == {True}:
            self.fleet_mode = REUSED
        elif have == {False}:
            self.fleet_mode = COLD
            self._cold_start()
            running = lib.running_ips(self.rdc("ops", "status", "-o", "json").out)
            if self.bridge_ip not in running or self.worker_ip not in running:
                raise NotVerifiedError(
                    "fleet-unavailable",
                    "ops up --basic exited 0 but %s and %s are not both running"
                    % (self.bridge_ip, self.worker_ip),
                )
        else:
            raise NotVerifiedError(
                "fleet-unavailable",
                "partial fleet: running %s, need %s and %s"
                % (" ".join(running) or "<none>", self.bridge_ip, self.worker_ip),
            )
        self.ips = running
        if not self.machine:
            machines = _data_list(self.rdc("machine", "list", "-o", "json").out)
            names = [str(m.get("name")) for m in machines if str(m.get("ip")) == self.worker_ip]
            if not names:
                raise NotVerifiedError(
                    "worker-not-in-config",
                    "no machine in the active config has ip %s; register it once: ./rdc.sh machine add <name> --ip %s --user %s"
                    % (self.worker_ip, self.worker_ip, self.ssh_user),
                )
            self.machine = names[0]
        self.record(
            "P2",
            "fleet %s (%s), worker %s" % (self.fleet_mode, " ".join(running), self.machine),
            True,
        )

    def _cold_start(self) -> None:
        image = self.opts.os_image or self.environ.get("VM_IMAGE") or ""
        args = ["ops", "up", "--basic"] + (["--os", image] if image else [])
        # Set before the call, so an interrupt mid-boot still brings the half-started fleet down; a refusal started nothing.
        self.fleet_started = True
        try:
            res = self.rdc(*args, timeout=1800)
        except NotVerifiedError:
            self.fleet_started = False
            raise
        if res.rc != 0:
            raise NotVerifiedError(
                "fleet-unavailable",
                "./rdc.sh %s rc=%d after %d s: %s"
                % (" ".join(args), res.rc, res.ms // 1000, rdc_failure(res)),
            )
        self.say("        cold start: ./rdc.sh %s took %d s" % (" ".join(args), res.ms // 1000))

    def _ensure_cli_key(self) -> None:
        """Give a config with no SSH key the key the ops VMs authorize (2026-10-15: an empty `credentials` made the CLI offer ~/.ssh/id_ed25519, and `repo list` failed `All configured authentication methods failed`). An unreadable `config ssh show` changes nothing and is said; P5's repo list then judges the key."""
        show = self.rdc("config", "ssh", "show", "-o", "json")
        parsed = True
        try:
            embedded = (json.loads(show.out).get("data") or {}).get("embedded")
        except (ValueError, AttributeError):
            embedded, parsed = None, False
        if show.rc != 0 or embedded is None:
            why = (
                ("its JSON has no data.embedded" if parsed else "its output is not JSON")
                if show.rc == 0
                else "rc=%d: %s" % (show.rc, rdc_failure(show))
            )
            self.say(
                "        config ssh show gave no key state (%s); the config is left as it is" % why
            )
            return
        if embedded != "no":
            return
        res = self.rdc("config", "ssh", "set", "--key", self.ssh_key)
        if res.rc != 0:
            raise NotVerifiedError(
                "worker-ssh-key",
                "config ssh set --key %s rc=%d: %s" % (self.ssh_key, res.rc, rdc_failure(res)),
            )
        self.say(
            "        the config had no SSH key; set %s, the key the ops VMs authorize"
            % self.ssh_key
        )

    def p3_keys(self) -> None:
        res = self.rdc("machine", "scan-keys", self.machine)
        if res.rc != 0:
            raise NotVerifiedError(
                "fleet-unavailable",
                "machine scan-keys %s rc=%d: %s" % (self.machine, res.rc, rdc_failure(res)),
            )
        self._ensure_cli_key()
        probe = self.probe(PROBE_OS_RELEASE)
        parts = probe.out.split()
        if probe.rc != 0 or len(parts) < 2:
            raise NotVerifiedError(
                "fleet-unavailable",
                "the worker's /etc/os-release is unreadable over ssh (rc=%d): %s"
                % (probe.rc, last_lines(probe.err)),
            )
        self.fleet_os = "%s-%s" % (parts[0], parts[1])
        if (
            self.opts.os_image
            and self.fleet_mode == REUSED
            and not os_matches(self.opts.os_image, parts[0], parts[1])
        ):
            raise NotVerifiedError(
                "fleet-os-mismatch",
                "--os %s asked, the reused fleet runs %s" % (self.opts.os_image, self.fleet_os),
            )
        self.record("P3", "host keys pinned for %s (%s)" % (self.machine, self.fleet_os), True)

    def p4_account(self) -> None:
        stored = self.rdc("subscription", "status", "-o", "json")
        if stored.rc == 0:
            self.record("P4", "the config's stored token is valid; nothing minted", True)
            return
        if not self.account.gateway_healthy():
            raise NotVerifiedError(
                "account-unavailable",
                "the stored token is refused and no healthy dev gateway answers; start one with ./run.sh account dev",
            )
        password = secrets.token_urlsafe(24)
        self.password = password
        try:
            token = self.account.mint(password)
        except (lib.GatewayError, OSError) as exc:
            raise NotVerifiedError(
                "account-unavailable", "minting a token for %s failed: %s" % (ACCOUNT_LOGIN, exc)
            ) from None
        self.token = token
        self.say(
            "        "
            + "minted a token for %s (scopes %s)" % (ACCOUNT_LOGIN, ",".join(TOKEN_SCOPES))
        )
        check = self.rdc("subscription", "status", "-o", "json")
        if check.rc != 0:
            raise NotVerifiedError(
                "account-unavailable",
                "subscription status refused the minted token: %s" % rdc_failure(check),
            )
        self.record("P4", "token minted for %s, passed as REDIACC_TOKEN only" % ACCOUNT_LOGIN, True)

    def p5_parent(self) -> None:
        res, entries = self.repo_list()
        if res.rc != 0:
            why = rdc_failure(res)
            raise NotVerifiedError(
                "worker-ssh-key" if "authentication methods failed" in why else "fleet-unavailable",
                "repo list -m %s rc=%d: %s%s"
                % (
                    self.machine,
                    res.rc,
                    why,
                    "; the worker refused the CLI's SSH key, and the key the ops VMs authorize is "
                    "%s (./rdc.sh config ssh set --key %s)" % (self.ssh_key, self.ssh_key)
                    if "authentication methods failed" in why
                    else "",
                ),
            )
        names = [str(e.get("name", "")) for e in entries]
        if self.opts.parent not in names:
            grands = sorted(n for n in names if n and ":" not in n)
            raise NotVerifiedError(
                "parent-grand-missing",
                "no grand %s on %s (grands present: %s); the operator creates it once, outside agent mode: %s./rdc.sh repo create %s -m %s --size 2G%s"
                % (
                    self.opts.parent,
                    self.machine,
                    ", ".join(grands) or "none",
                    # A cold run boots fresh VMs and `ops down` removes them, so its worker can never hold the grand (2026-10-15T00:27Z); the fleet comes up first, then the grand is created on it.
                    "./rdc.sh ops up --basic, then " if self.fleet_started else "",
                    self.opts.parent,
                    self.machine,
                    ", and leave the fleet up for vm:check to reuse (this run started it cold, "
                    "and fresh VMs never hold a grand)"
                    if self.fleet_started
                    else "",
                ),
            )
        swept: list[str] = []
        kept: list[str] = []
        for name in names:
            parent, _, tag = name.partition(":")
            match = FORK_TAG.match(tag)
            if parent != self.opts.parent or not match:
                continue
            age = stamp_age_s(match.group(1), self.host.now())
            if age is None or age <= STALE_FORK_S:
                continue
            gone = self.rdc("repo", "delete", name, "-y", refuse=False)
            (swept if gone.rc == 0 else kept).append(name)
        evidence = "swept %s" % ", ".join(swept) if swept else ""
        if kept:
            evidence += "; could not delete %s" % ", ".join(kept)
        self.record(
            "P5",
            "parent grand %s present; %d stale fork(s) swept" % (self.opts.parent, len(swept)),
            True,
            evidence=evidence.strip("; "),
        )

    # ------------------------------------------------------------------ V

    def v1_1_forks(self) -> bool:
        for tag in self.tags:
            self.forks.append({"tag": tag, "guid": "", "created": True, "deleted": False})
            res = self.rdc("repo", "fork", self.opts.parent, "--tag", tag, "--up", timeout=1800)
            if not self.check("V1.1", "fork %s --up" % self.ref(tag), res.rc == 0, res):
                return False
        res, entries = self.repo_list()
        for entry in entries:
            for tag in self.tags:
                if entry.get("name") == self.ref(tag):
                    self.guids[tag] = str(entry.get("guid", ""))
                    nid = entry.get("networkId", entry.get("network_id"))
                    if nid is not None:
                        self.network_ids[tag] = str(nid)
        for fork in self.forks:
            fork["guid"] = self.guids.get(fork["tag"], "")
        if not self.check(
            "V1.1",
            "both forks listed with a guid",
            all(self.guids.get(t) for t in self.tags),
            res,
            evidence="guids %s" % self.guids,
        ):
            return False
        local = {
            h
            for h in (
                self.host.sha256(self.renet_bin),
                self.host.sha256(self.renet_bin.with_name("renet-linux-amd64")),
            )
            if h
        }
        probe = self.probe(PROBE_RENET_HASH)
        deployed = probe.out.split()[0] if probe.rc == 0 and probe.out.split() else ""
        ok = bool(deployed) and deployed in local
        self.renet["deployed"] = self.renet["built"] if ok else None
        self.check(
            "V1.1",
            "the worker runs the renet built at %s" % self.renet["built"][:12],
            ok,
            probe,
            evidence="deployed hash %s" % (deployed[:16] or "<none>"),
        )
        return ok

    def v1_2_cross_repo(self) -> None:
        a, b = self.tags
        target = "%s/%s" % (self.mount(b), GUARDED_FILE)
        stat = "stat -c '%%a %%Y' %s" % shlex.quote(target)
        before = self.shell(self.ref(b), stat)
        self.b_stat = before.out.strip()
        self.check(
            "V1.2",
            "B reads its own %s (stat %s)" % (GUARDED_FILE, self.b_stat or "<none>"),
            before.rc == 0 and bool(self.b_stat),
            before,
        )
        for command in (
            "chmod 0777 %s" % shlex.quote(target),
            "touch -m -d @0 %s" % shlex.quote(target),
        ):
            res = self.shell(self.ref(a), command)
            self.check(
                "V1.2",
                "A: `%s` on B's file fails read-only" % command.split()[0],
                res.rc != 0 and READ_ONLY in res.text(),
                res,
                evidence=res.text(),
            )
        after = self.shell(self.ref(b), stat)
        self.check(
            "V1.2",
            "B's stat unchanged after A's attempts",
            after.rc == 0 and after.out.strip() == self.b_stat,
            after,
            evidence="before %s after %s" % (self.b_stat, after.out.strip()),
        )

    def v1_3_positive(self) -> None:
        a = self.tags[0]
        mnt = shlex.quote(self.mount(a))
        marker = "vmc-shm-%s" % self.run_id
        commands = (
            ("write ~", "echo vmc > ~/vmc-home"),
            ("write /tmp", "echo vmc > /tmp/vmc-tmp"),
            ("write /dev/shm", "echo vmc > /dev/shm/%s" % marker),
            ("write the mount", "echo vmc > %s/vmc-mount" % mnt),
            ("chmod 600 in the mount", "chmod 600 %s/vmc-mount" % mnt),
            ("docker ps", "docker ps"),
            ("renet compose -- ps", "cd %s && renet compose -- ps" % mnt),
            (
                "git commit in the mount",
                "cd %s && rm -rf vmc-git && mkdir vmc-git && cd vmc-git && git init -q && git -c user.email=vm@check -c user.name=vmcheck commit -q --allow-empty -m vmcheck"
                % mnt,
            ),
            ("vi writes ~/v", "vi -es -c wq ~/v"),
        )
        for desc, command in commands:
            res = self.shell(self.ref(a), command)
            self.check("V1.3", "A: %s" % desc, res.rc == 0, res)

    def v1_4_isolation(self) -> None:
        a, b = self.tags
        marker = "vmc-shm-%s" % self.run_id
        res = self.shell(self.ref(b), "ls /dev/shm")
        self.check(
            "V1.4",
            "B's /dev/shm does not show A's marker",
            res.rc == 0 and marker not in res.out.split(),
            res,
            evidence=res.out,
        )
        cgroup = self.shell(self.ref(a), "cat /proc/self/cgroup")
        nid = self.network_ids.get(a)
        wanted = "renet-exec-%s" % nid if nid else "renet-exec-"
        self.check(
            "V1.4",
            "A's cgroup names %s" % wanted,
            cgroup.rc == 0 and wanted in cgroup.out,
            cgroup,
            evidence=cgroup.out,
        )
        detect = self.shell(self.ref(a), "renet sandbox-exec --detect")
        for line in detect.out.splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() in ("status", "abi"):
                self.landlock[key.strip().lower()] = value.strip()
        self.check(
            "V1.4",
            "renet sandbox-exec --detect (status %s, abi %s)"
            % (self.landlock.get("status", "?"), self.landlock.get("abi", "?")),
            detect.rc == 0 and "status" in self.landlock,
            detect,
            evidence=detect.out,
        )

    def _fixture(self) -> pathlib.Path:
        up = self.work / "sync-up"
        (up / "nested" / "deeper").mkdir(parents=True, exist_ok=True)
        (up / "nested" / "deeper" / "leaf.txt").write_text("vm:check %s\n" % self.run_id)
        secret = up / "private.txt"
        secret.write_text("mode 0600\n")
        secret.chmod(0o600)
        (up / "big.bin").write_bytes(secrets.token_bytes(SYNC_BIG_BYTES))
        link = up / "link"
        if not link.is_symlink():
            link.symlink_to("nested/deeper/leaf.txt")
        return up

    @staticmethod
    def _tree_of(base: pathlib.Path) -> dict[str, str]:
        found: dict[str, str] = {}
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(base).as_posix()
            if path.is_symlink():
                found[rel] = "link:" + os.readlink(path)
            elif path.is_file():
                found[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return found

    def v1_5_sync(self) -> None:
        a = self.tags[0]
        up = self._fixture()
        down = self.work / "sync-down"
        down.mkdir(exist_ok=True)
        remote = "vmc-sync-%s" % self.run_id
        res = self.rdc(
            "repo",
            "sync",
            "upload",
            self.ref(a),
            "--local",
            str(up) + "/",
            "--remote",
            remote,
            "--verify",
        )
        if not self.check("V1.5", "sync upload --verify", res.rc == 0, res):
            return
        res = self.rdc(
            "repo", "sync", "download", self.ref(a), "--local", str(down), "--remote", remote
        )
        if not self.check("V1.5", "sync download", res.rc == 0, res):
            return
        sent, got = self._tree_of(up), self._tree_of(down)
        differ = sorted(k for k in set(sent) | set(got) if sent.get(k) != got.get(k))
        self.check(
            "V1.5",
            "round trip is byte-identical (%d entries)" % len(sent),
            not differ,
            evidence="differ: %s" % ", ".join(differ),
        )

    def v1_6_vscode(self) -> None:
        a = self.tags[0]
        res = self.rdc("vscode", "connect", self.ref(a), "--url-only")
        if res.rc != 0 and VSCODE_ABSENT in res.text():
            raise NotVerifiedError(
                "vscode-absent",
                "vscode connect refused before any setup: %s" % first_line(res.text()),
            )
        uri = next(
            (ln.strip() for ln in res.out.splitlines() if ln.strip().startswith(URI_PREFIX)), ""
        )
        if uri:
            self.connection = uri[len(URI_PREFIX) :].split("/", 1)[0]
        if not self.check(
            "V1.6",
            "vscode connect --url-only prints a remote URI",
            res.rc == 0 and bool(self.connection),
            res,
            evidence=uri,
        ):
            return
        server = self.shell(self.ref(a), "test -d %s/.vscode-server" % shlex.quote(self.mount(a)))
        self.check("V1.6", "%s/.vscode-server exists" % self.mount(a), server.rc == 0, server)

    def v1_7_sftp(self) -> None:
        if not self.connection:
            self.record("V1.7", "sftp not run: V1.6 wrote no ssh alias", None)
            return
        a, b = self.tags
        payload = self.work / "sftp-payload.txt"
        payload.write_text("vm:check sftp %s\n" % self.run_id)
        own = "%s/vmc-sftp" % self.mount(a)
        other_dir = self.mount(b)
        legs = (
            ("put into A's mount succeeds", "put %s %s" % (payload, own), True),
            ("put into B's mount is refused", "put %s %s/vmc-sftp" % (payload, other_dir), False),
            (
                "chmod on B's %s is refused" % GUARDED_FILE,
                "chmod 777 %s/%s" % (other_dir, GUARDED_FILE),
                False,
            ),
        )
        for index, (desc, line, allowed) in enumerate(legs):
            batch = self.work / ("sftp-%d.batch" % index)
            batch.write_text(line + "\n")
            res = self.host.run(
                [*SFTP_BATCH, str(batch), self.connection], env=self.environ, timeout=120
            )
            ok = res.rc == 0 if allowed else res.rc != 0 and sftp_refused(res.text())
            self.check("V1.7", "sftp: %s" % desc, ok, res, evidence=res.text())
        after = self.shell(
            self.ref(b), "stat -c '%%a %%Y' %s" % shlex.quote("%s/%s" % (other_dir, GUARDED_FILE))
        )
        self.check(
            "V1.7",
            "B's stat unchanged after the sftp legs",
            after.rc == 0 and after.out.strip() == self.b_stat,
            after,
            evidence="before %s after %s" % (self.b_stat, after.out.strip()),
        )

    # ------------------------------------------------------------------ T

    def _install_signals(self) -> dict[int, Any]:
        def handler(signum: int, _frame: object) -> None:
            raise RunInterruptedError("signal %s" % signal.Signals(signum).name)

        previous: dict[int, Any] = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(ValueError):
                previous[sig] = signal.signal(sig, handler)
        return previous

    def _quiet_signals(self) -> None:
        """During teardown a second Ctrl-C must not abandon the forks: it is noted and ignored."""

        def handler(signum: int, _frame: object) -> None:
            log.warn(
                "%s during teardown: ignored until the forks are deleted"
                % signal.Signals(signum).name
            )

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(ValueError):
                signal.signal(sig, handler)

    @staticmethod
    def _restore_signals(previous: dict[int, Any]) -> None:
        for sig, old in previous.items():
            with contextlib.suppress(ValueError, TypeError):
                signal.signal(sig, old)

    def _teardown(self) -> None:
        leftovers: list[str] = []
        try:
            leftovers = self._teardown_steps()
        except CRASHES as exc:
            leftovers.append(self.scrub("teardown crashed: %s: %s" % (type(exc).__name__, exc)))
        finally:
            self.lock.release()
            self.locked = False
        self.leftovers = leftovers
        if not self.forks and not self.fleet_started and not self.connection:
            self.record("T", "nothing to tear down (no fork created, no fleet started)", True)
        elif leftovers:
            self.record(
                "T",
                "teardown left %d item(s)" % len(leftovers),
                False,
                evidence=", ".join(leftovers),
            )
        else:
            self.record("T", "teardown clean", True)

    def _teardown_steps(self) -> list[str]:
        leftovers: list[str] = []
        if self.connection:
            res = self.rdc("vscode", "cleanup", "-c", self.connection, refuse=False)
            if res.rc != 0:
                leftovers.append("vscode connection %s (cleanup rc=%d)" % (self.connection, res.rc))
        for fork in self.forks:
            res = self.rdc("repo", "delete", self.ref(fork["tag"]), "-y", refuse=False)
            fork["deleted"] = res.rc == 0
        if self.forks:
            res, entries = self.repo_list()
            names = {str(e.get("name", "")) for e in entries}
            if res.rc != 0:
                leftovers.extend(
                    "fork %s (repo list unreadable)" % self.ref(f["tag"]) for f in self.forks
                )
            for fork in self.forks:
                if self.ref(fork["tag"]) in names:
                    fork["deleted"] = False
                    leftovers.append("fork %s" % self.ref(fork["tag"]))
                elif res.rc == 0:
                    fork["deleted"] = True
        if self.fleet_mode == COLD and self.fleet_started:
            res = self.rdc("ops", "down", refuse=False, timeout=600)
            if res.rc != 0:
                leftovers.append("cold fleet still up (ops down rc=%d)" % res.rc)
        return leftovers

    # ------------------------------------------------------------------ summary and receipt

    def _finish(self) -> int:
        status, reason = verdict(self.assertions, self.failures, self.reason, self.leftovers)
        receipt = self._receipt(status, reason)
        path: pathlib.Path | None = None
        if self.tree:
            path = receipt_mod.write(self.root, receipt)
        else:
            log.error("HEAD^{tree} is unreadable, so no receipt was written")
        self._summary(status, reason, path)
        return EXIT_CODES[status]

    def _receipt(self, status: str, reason: dict[str, str] | None) -> dict[str, Any]:
        finished = self.host.now()
        return {
            "schema": receipt_mod.SCHEMA,
            "status": status,
            "reason": reason,
            "tree": self.tree,
            "head": self.head,
            "inputs": self.inputs,
            "renet": dict(self.renet),
            "trigger": dict(self.trigger_info),
            "fleet": {
                "mode": self.fleet_mode or None,
                "os": self.fleet_os or None,
                "ips": list(self.ips),
                "landlock": dict(self.landlock),
            },
            "forks": [dict(f) for f in self.forks],
            "steps": [dict(s) for s in self.steps],
            "teardown": {"ok": not self.leftovers, "leftovers": list(self.leftovers)},
            "runId": self.run_id,
            "startedAt": _iso(self.started_at),
            "finishedAt": _iso(finished),
            "wallMs": int((self.host.monotonic() - self.started_mono) * 1000),
        }

    def _summary(
        self, status: str, reason: dict[str, str] | None, path: pathlib.Path | None
    ) -> None:
        self.say("\n=== %s summary ===" % NAME)
        self.say("  %-5s %-6s %s" % ("##", "RESULT", "STEP"))
        for row in self.steps:
            self.say("  %-5s %-6s %s" % (row["id"], row["verdict"], row["desc"]))
        if not any(r["id"].startswith("V") for r in self.steps):
            self.say("  %-5s %-6s %s" % ("--", "skip", "V1.1-V1.7 not run"))
        self.say("  %d assertion(s), %d failed" % (self.assertions, len(self.failures)))
        if status == receipt_mod.VERIFIED:
            self.say("  vm:check VERIFIED")
        elif reason is not None:
            label = "FAILED" if status == receipt_mod.FAILED else "NOT VERIFIED"
            self.say("  vm:check %s (%s): %s" % (label, reason["class"], reason["detail"]))
            if status == receipt_mod.NOT_VERIFIED:
                self.say(
                    "  Nothing on the VMs was judged. The push guard treats this tree as NOT verified."
                )
        if path is not None:
            self.say(
                "  receipt: %s (status %s, tree %s, renet %s)"
                % (
                    path.relative_to(self.root) if path.is_relative_to(self.root) else path,
                    status,
                    self.tree[:12],
                    str(self.renet.get("built") or "")[:12] or "<none>",
                )
            )


# --------------------------------------------------------------------------- selftest and entry


def selftest(out=None) -> int:
    """The planted control: one failing assertion through `verdict`. Always non-zero; the message says whether the instrument noticed."""
    stream = out if out is not None else sys.stdout
    status, _ = verdict(1, ["SELFTEST: planted failure (this run MUST exit non-zero)"], None, [])
    empty, _ = verdict(0, [], None, [])
    if status == receipt_mod.FAILED and empty != receipt_mod.VERIFIED:
        print("  vm:check selftest fired as designed (exit is non-zero on purpose)", file=stream)
    else:
        print(
            "  vm:check SELFTEST DID NOT FIRE: a planted failure came out %s and an empty ledger %s, so this instrument is not measuring anything"
            % (status, empty),
            file=stream,
        )
    return EXIT_FAILED


def main(
    argv: Sequence[str],
    *,
    root: pathlib.Path | None = None,
    host: Host | None = None,
    account: Account | None = None,
    lock: Lock | None = None,
    out=None,
    environ: Mapping[str, str] | None = None,
    inputs_fn: Callable[[pathlib.Path], str | None] = trigger.inputs,
) -> int:
    opts = parse_args(argv, environ)
    if opts.selftest:
        return selftest(out)
    drill = lib.Drill("vmcheck", keep_work=opts.keep_work, stdout=out)
    drill.init()
    check = VmCheck(
        root=root or paths.repo_root(),
        opts=opts,
        host=host or Host(),
        account=account or DrillAccount(drill),
        work=drill.work if drill.work is not None else pathlib.Path(drill.root),
        lock=lock or Lock(lock_path(environ)),
        out=out,
        environ=environ,
        inputs_fn=inputs_fn,
    )
    try:
        return check.run()
    finally:
        drill.teardown()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

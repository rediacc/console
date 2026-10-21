"""`npm run vm:check`: prove the renet side (the repo shell, sync, SFTP and VS Code paths of `rdc` on the ops VMs) and the account side (private/account's suites and the account drills against a fresh dev gateway), and write the receipt the push guard reads.

    npm run vm:check [-- --changed] [--os <image>] [--parent <grand>] [--machine <name>] [--wait <s>] [--selftest] [--keep-work]
    ./run.sh drill vmcheck [same flags]

Design 2 of agent/plans/PLAN-vm-check.md and Design 3 of agent/plans/PLAN-account-vm-check.md are the specification; each step below carries its id there.

PHASES. There are two sides, the trigger's `renet` and `account` (`vm_check_trigger.SIDES`). With `--changed` the sides of `Changed.sides` are required; with no `--changed`, or a push base that cannot be resolved, both are. The renet phase is P5 and V1.1-V1.7; the account phase is A1.1-A1.4, A0 and A2.1-A2.3. P0-P4 and T run on every run, P1 included, because the license drill deploys renet too and the receipt check needs `renet.built == renet.pointer` even on an account-only receipt. `phases.<side>.ran` is true only when every step of that phase recorded a row and every such row is ok. The steps, in run order:

  A1  account only, before P0, so the fleet lock is not held for the suites: A1.1 `npm run check:ci-account-server`, A1.2 `npm run check:ci-test-account-web`, A1.3 `npm --prefix private/account run typecheck`, A1.4 `npm --prefix private/account run typecheck:web`. Each is one assertion row with its rc and ms; a non-zero rc is a failed row carrying the last three output lines. All four run, and any failure ends the run FAILED before any VM is touched.
  P0  an exclusive flock on `rediacc-vm-check.lock` in the per-user runtime directory, waited for up to `--wait` seconds (`fleet-busy`). A run that gives up there judged nothing while a holder may still be running, so it writes neither `receipt.json` nor the tree archive: its record goes to `runs/<run id>/receipt.json` (`vm_check_receipt.write_run_record`), and the summary prints where.
  P1  `go version -m private/renet/bin/renet` must carry the submodule HEAD as `vcs.revision` and `vcs.modified=false`; one `./rdc.sh --version` rebuild is tried before `renet-build-mismatch`.
  A0  account only. The dev gateway does not hot-reload, so it is reused only when it is healthy, the `started=` and `gateway_port=` of `.account-state` equal the record `.ci/cache/vm-check/gateway.json` this runner wrote when it last started one, and that record's `account` equals `vm_check_trigger.account_worktree_digest`. Otherwise `lib.Drill.restart_gateway` starts it with its log at `.ci/cache/vm-check/gateway.log`, the record is rewritten (mode `started`, or `restarted` when a gateway was already answering), and `detach_gateway` leaves it running after the run for the next one to reuse. A restart rotates every dev password and may move the port, and the run says so. A start that fails, or a gateway still unhealthy after it, is `account-gateway` with the log tail.
  P4  chooses the config every later CLI call runs under. The stored token is used when `subscription status` accepts it; that verb exits non-zero when the config holds no token at all (before 2026-10-15 it exited 0 printing "Not logged in", so P4 read an absent token as a valid one and `repo create` then refused with "Subscription token required"). Otherwise a token is minted on the running dev gateway for the dedicated login ACCOUNT_LOGIN, with a password generated per run and held in memory (`account-unavailable`). The token reaches `rdc` only as REDIACC_TOKEN in the child environment, beside REDIACC_ACCOUNT_SERVER naming the gateway that minted it: never on argv, never in the config, never printed, never in the receipt, never in a suite's or a drill's environment. A minted token also puts every later CLI call under the dev config (RDC_DEV=1, which makes `./rdc.sh` seed ~/.config/rediacc/dev.json with the gateway's address and E2E key and select it), since the default config carries the production server's E2E key and a dev-gateway response then fails "Decryption failed" (2026-10-15T05:4xZ). The operator's default config is never written on that path; a valid stored token keeps it. The minted token names the gateway at this host's address on the VM network (`wire.bridge_host`, 192.168.111.254), never localhost: the CLI sends every licence request there and the account stamps each licence's renewalUrl from that request, so a localhost token left every fork's and the grand's blob unrenewable from the worker (2026-10-20). With no interface on that network yet (a cold fleet) the token is minted on localhost for the fleet steps and re-minted on the bridge address right after P2, before anything issues a licence. The subscription of ACCOUNT_LOGIN is kept across runs (`subscription_reuse_refusal` names when it is recreated instead), since `/test/ensure-subscription` deletes it and with it every licence an earlier run issued.
  P2  `/dev/kvm` and `virsh` (`no-kvm`); `rdc ops status -o json`: the bridge (.1) and the worker (.11) both running is REUSE, neither is COLD (`ops up --basic`), anything else is `fleet-unavailable`. The worker's machine name comes from `machine list` (`worker-not-in-config`). Under the dev config a worker absent from it is registered as OPS_WORKER_NAME (`machine add`), and a `--machine` name absent from it is `worker-not-in-config` naming the command; a dev config that cannot be listed ("Decryption failed") is `account-unavailable`.
  P3  `machine scan-keys <worker>` before any other ssh, then the worker's /etc/os-release, which under `--os` must match a reused fleet (`fleet-os-mismatch`). A config with no SSH key (`config ssh show` says `embedded: no`) gets the key the ops VMs authorize (`config ssh set --key`, the license drill's step), since the CLI would otherwise offer ~/.ssh/id_rsa or id_ed25519, which the VMs reject; a config holding another key is never overwritten, and a failing `config ssh show` leaves the config alone and lets P5 judge. P3's own os-release probe uses the drill's key, not the CLI's, so its failure stays `fleet-unavailable`; the CLI's key is first used at P5, where an ssh authentication refusal is `worker-ssh-key`.
  A2  account only, against the worker: A2.1 `PYTHONPATH=.ci python3 -m rediacc_ci.drills.universe --no-restart`, A2.2 `PYTHONPATH=.ci python3 -m rediacc_ci.drills.transfer --no-restart`, A2.3 `PYTHONPATH=.ci python3 -m rediacc_ci.drills.license --legs c,d,e,f --no-restart --seed-repo --vm <worker ip>`. Each drill is judged by its summary line (`%d assertions: %d passed, %d failed`, `classify_drill`): a failed assertion is a failed row naming the drill and the failed assertions by number and description (the row's `failedAssertions`, and the head of its evidence); rc 0 with a positive count and the PASSED line is ok; a SKIPPED line, 0 assertions, or rc 0 with no summary line at all is `account-drill-skipped`; anything else, such as a non-zero rc with no summary (a preflight `SystemExit`), is `account-drill-setup`. All three run; a failed row ends the run FAILED, otherwise the first could-not-judge class ends it NOT_VERIFIED. A2 runs before P5 because the license drill deploys its enforcing renet build to the worker, and the first plain `./rdc.sh` of P5 deploys the default build of the same commit back before the V-steps.
  P5  renet only. The parent must be a grand on the worker. When it is missing and the worker's configured address is on the ops VM network (OPS_VM_NETWORK, the predicate of packages/cli/src/utils/ops-vm.ts), the check creates it with `repo create <parent> -m <worker> --size 2G` under P4's credential, says so and records the creation as a P5 row: the ops VMs are development-only (operator ruling 2026-10-15, .claude/agents/ops-vms.md), so that step is never an operator's. A failed create is `parent-grand-missing` naming the CLI's error; on any other worker a missing grand stays `parent-grand-missing` naming the command for the operator. Stale `vmc-` forks of the parent older than an hour are deleted on every path once `repo list` answers, before the grand is judged (a missing grand that is then created included), nothing else is touched.
  V1.1-V1.7  renet only: two forks, cross-repo read-only denial, the positive set, isolation, sync round trip, VS Code URL and SFTP confinement.
  T   in `finally`, also after SIGINT and SIGTERM (a handler raises `RunInterruptedError`): `vscode cleanup`, `repo delete` of this run's forks, a `repo list` proving neither tag remains, the purge of the deleted forks' licence state (`lib.purge_license_state_script` through `term connect <worker> -c`, which first proves renet no longer lists the guid: renet keeps a deleted repo's blobs and `license renew` retries every one), `ops down` only for a fleet this run started, then the lock. The P5 sweep purges the licence state of the stale forks it deletes the same way. Leftovers turn a VERIFIED run into NOT_VERIFIED `teardown-failed`; a FAILED run stays FAILED and its detail lists them. A gateway A0 started is detached and stays up.

THE RULES. Every VM action goes through `./rdc.sh`. Nothing here sets or clears REDIACC_AGENT, CLAUDECODE or REDIACC_ALLOW_*: a verb the CLI's agent guard refuses ends the run NOT_VERIFIED `agent-policy-refused` with the refusal's first line. The one guard variable set is REDIACC_SKIP_FILE_WRITE_GUARD=1, and only on the child of a V1.3 write row: the CLI's file-write guard (packages/cli/src/utils/repo-context-guard.ts) refuses `echo x > f` through `term connect` in an agent session with "File write detected", and that variable is its documented usability override (docs/environment-variables.md), not a security boundary. The raw `ssh` probes and the `sftp -b` leg are built from the constants below, the leg under `-F` with a config built from the alias block `vscode connect` wrote. Nothing is uploaded with scp. Suites and drills run under this process's environment with DRILL_ENV_SCRUB removed, never under `child_env()`, so a declared keyring skip (DRILL_EXPECT_NO_KEYRING) cannot turn into a pass and the minted token never reaches a drill.

VERDICTS. VERIFIED exit 0 (assertions ran, none failed, every required phase ran, teardown clean); FAILED exit 1 (an assertion failed); NOT_VERIFIED exit 77 (the check could not judge). A required phase whose steps did not all run ok, with no other finding, is NOT_VERIFIED `phase-not-run`. A run that recorded no assertion is never VERIFIED. `--selftest` touches no machine: it feeds one planted failing assertion through the same `verdict` the real run uses and exits non-zero, printing "selftest fired as designed" only when that verdict came out FAILED.

EVIDENCE. Each A1 suite's and A2 drill's full stdout and stderr is kept in `.ci/cache/vm-check/runs/<run id>/<step>-<name>.log` (the newest RUNS_KEEP run directories are kept), its row carries that path as `log`, and the receipt carries the directory as `runDir`. A row's `evidence` stays clipped to 200 bytes, so the log is where a failure is read in full.

`--changed` evaluates `vm_check_trigger` against the push base in worktree mode; with no hit it prints the no-op line, writes no receipt and exits 0. The receipt is schema 2 (`vm_check_receipt`): `phases`, `account` (`pointer`, `checkout`, `modified`, `gateway`) and `trigger.sides` beside the renet fields. Receipts of an earlier schema no longer count, and a run that finds some says so once.

The whole flow runs through `Host` and `Account`, so the tests drive it with a fake host and a fake account and never reach a VM, a gateway or a suite.
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
# The name the worker is registered under in the dev config when that config does not hold it yet.
OPS_WORKER_NAME = "ops-worker"
TOKEN_SCOPES = ("license:read", "license:activate", "subscription:read")
# Issuances a kept ACCOUNT_LOGIN subscription must still have this month (`maxRepoLicenseIssuancesPerMonth` minus `repoLicenseIssuances.used`, private/account subscription.service.ts claimRepoLicenseIssuanceSlot) before P4 reuses it: a run issues its two forks' licences and at most a reissue of the grand, so 50 covers many runs, and a subscription short of it is recreated rather than left to refuse a fork mid-run.
ISSUANCE_HEADROOM = 50
# The statuses the account's issuance path (resolveEntitledSubscription) entitles at the subscription's own plan; `grace` falls back to COMMUNITY, `suspended` and `expired` refuse.
REUSABLE_STATUSES = ("active", "inactive")

# The development-only ops VM network, the /24 packages/cli/src/utils/ops-vm.ts exempts from the agent-mode grand guards (VM_NETWORK.BRIDGE_IP in @rediacc/shared). Like that predicate it ignores VM_NET_BASE: an environment variable cannot widen what counts as disposable.
OPS_VM_NETWORK = "192.168.111"
GRAND_SIZE = "2G"
# The CLI's refusal when the worker's datastore was never prepared ("Machine '<ip>' datastore at /mnt/rediacc is not BTRFS").
NO_DATASTORE = "is not BTRFS"
# The CLI's refusal when the config still lists the repo: `ops down` destroys the VMs (and the grand with them) but the local config keeps the entry (VC7(b), 2026-10-20).
STALE_CONFIG_ENTRY = "already exists in config"

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
# No `-q`: an alias that does not resolve or a key ssh refuses must reach the row's evidence.
SFTP_BATCH = ("sftp", "-o", "BatchMode=yes")
# A refused sftp leg counts as confinement only when the server says so; a dropped connection or a missing path is not a refusal.
SFTP_DENIAL = re.compile(
    r"permission denied|read-only file system|operation not permitted", re.IGNORECASE
)
# sftp-server answers a refused write with the bare SSH2_FX_FAILURE status, which sftp prints as `dest open "<path>": Failure` (put) or `remote setstat "<path>": Failure` (chmod). Such a line is a refusal only when its path is the neighbour's; the 2026-10-15 run's legs were confined but read as "not refused".
SFTP_STATUS_FAILURE = re.compile(
    r'^\s*[a-z][a-z ]*"([^"\n]+)":\s*Failure\s*$', re.IGNORECASE | re.MULTILINE
)
# ssh's own failed login (`user@host: Permission denied (publickey,password).`) is not a server-side refusal: the connection never authenticated, so nothing was confined. The method list is hyphenated words joined by single commas, with an optional trailing comma: the comma is the only separator, so each character has one way to match and a line with no closing paren fails in linear time.
SSH_AUTH_FAILURE = re.compile(
    r"permission denied \([a-z-]+(?:,[a-z-]+)*,?\)|too many authentication failures",
    re.IGNORECASE,
)


def sftp_refused(output: str, path: str = "") -> bool:
    """True when the sftp output holds a refusal from the server's side of an authenticated session: a denial, or a `Failure` status line naming `path` or a file under it. Lines that report an ssh authentication failure are set aside first, so a connection-level failure is never a refusal."""
    text = "\n".join(ln for ln in output.splitlines() if not SSH_AUTH_FAILURE.search(ln))
    if SFTP_DENIAL.search(text):
        return True
    if not path:
        return False
    prefix = path.rstrip("/") + "/"
    return any(
        m.group(1) == path or m.group(1).startswith(prefix)
        for m in SFTP_STATUS_FAILURE.finditer(text)
    )


# The CLI's file-write guard, and the one override the V1.3 write rows pass (see THE RULES).
SKIP_FILE_WRITE_GUARD = "REDIACC_SKIP_FILE_WRITE_GUARD"
WRITE_ROW_ENV = {SKIP_FILE_WRITE_GUARD: "1"}
# `renet compose -- ps` needs a compose file in the mount, and the grand is empty; the smallest valid one is uploaded into fork A, never into the grand.
COMPOSE_FILE = "docker-compose.yml"
COMPOSE_BODY = "services: {}\n"
# vi is absent on the ops VM image (Ubuntu 24.04 ships no editor). The same temp-file-plus-rename write vi does is then asserted with `sed -i`: the content changes and the inode is new.
VI_PROBE = "command -v vi"
VI_WRITE = "vi -es -c wq ~/v"
SED_WRITE = (
    "printf 'vmc\\n' > ~/v && before=$(stat -c %i ~/v) && sed -i 's/^vmc$/vmc-sed/' ~/v"
    ' && test "$(cat ~/v)" = vmc-sed && test "$(stat -c %i ~/v)" != "$before"'
)
# Fixture entries a privileged sync never carries: it passes --no-links (packages/cli/src/remote/sync/rsync.ts) and the renet gateway refuses symlinks by design, so the link must be ABSENT on the remote rather than equal.
SYNC_DROPPED = ("link",)
# Where `vscode connect` writes its aliases: getSSHHome()/.ssh/config_rediacc (packages/cli/src/remote/vscode/sshConfig.ts), which on WSL is the Windows home under the drive mounts, never read by a plain `sftp <alias>`.
ALIAS_CONFIG = "config_rediacc"
WINDOWS_DRIVE_PATH = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def alias_block(text: str, alias: str) -> list[str] | None:
    """The directive lines of the `Host <alias>` block in an ssh config, stripped; None when no block names it."""
    block: list[str] | None = None
    for line in text.splitlines():
        words = line.split()
        # A Host line lists several patterns, and a Match line ends a Host block as surely as another Host does (review 5a9861e8.4).
        if words and words[0].lower() in ("host", "match"):
            if block is not None:
                return block
            if words[0].lower() == "host" and alias in words[1:]:
                block = []
            continue
        if block is not None and line.strip() and not line.strip().startswith("#"):
            block.append(line.strip())
    return block


def drive_path(value: str, drive_root: str = "/mnt") -> str:
    """A config value with its quotes stripped and a Windows drive path (`C:/Users/x`, `C:\\Users\\x`) spelled as the WSL mount sees it (`/mnt/c/Users/x`); any other value unchanged."""
    value = value.strip().strip('"')
    match = WINDOWS_DRIVE_PATH.match(value)
    if not match:
        return value
    return "%s/%s/%s" % (
        drive_root.rstrip("/"),
        match.group(1).lower(),
        match.group(2).replace("\\", "/"),
    )


# First-line markers of a refusal by the CLI's agent guard (packages/cli/src/utils/agent-guard.ts, command-policy.ts).
AGENT_REFUSALS = (
    "agent mode",
    "agent environments",
    "Agents cannot",
    "Agent-initiated overrides",
    "not available on fork repositories",
    "origin could not be verified",
    # The file-write guard (packages/cli/src/commands/term.ts enforceFileWriteGuard); the write rows pass its override, so seeing it means the CLI no longer honours that.
    "File write detected",
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

# --------------------------------------------------------------------------- the two phases

SIDE_RENET = trigger.SIDE_RENET
SIDE_ACCOUNT = trigger.SIDE_ACCOUNT
# Every step id of a phase; the phase ran only when each recorded a row and every such row is ok.
PHASE_STEPS: dict[str, tuple[str, ...]] = {
    SIDE_RENET: ("P5", "V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7"),
    SIDE_ACCOUNT: ("A1.1", "A1.2", "A1.3", "A1.4", "A0", "A2.1", "A2.2", "A2.3"),
}
# The account suites of A1: (step id, npm script, the package that holds it, None for the console root).
ACCOUNT_SUITES: tuple[tuple[str, str, str | None], ...] = (
    ("A1.1", "check:ci-account-server", None),
    ("A1.2", "check:ci-test-account-web", None),
    ("A1.3", "typecheck", trigger.ACCOUNT_SUBMODULE),
    ("A1.4", "typecheck:web", trigger.ACCOUNT_SUBMODULE),
)
SUITE_TIMEOUT_S = 1800
DRILL_TIMEOUT_S = 1800
LICENSE_LEGS = "c,d,e,f"
# Removed from every suite's and drill's environment: a minted or inherited credential, the dev-config switch, and the declared keyring skip that would turn the transfer drill's red into a SKIPPED exit 0.
DRILL_ENV_SCRUB = ("REDIACC_TOKEN", "REDIACC_ACCOUNT_SERVER", "RDC_DEV", "DRILL_EXPECT_NO_KEYRING")
# `lib.Drill.summary`'s count line and verdict words; colour escapes are stripped before either is read.
DRILL_SUMMARY = re.compile(r"(\d+) assertions: (\d+) passed, (\d+) failed")
DRILL_SKIPPED = re.compile(r"\bSKIPPED\b")
DRILL_PASSED = re.compile(r"drill \S+ PASSED\b")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
# A failed row of `lib.Drill.summary`'s table (`  02   FAIL   <description>`), read only after the summary header.
DRILL_FAIL_ROW = re.compile(r"^\s*(\d{2,})\s+FAIL\s+(.+?)\s*$", re.MULTILINE)
DRILL_SUMMARY_HEADER = " summary ==="
# The per-run evidence directory under the receipt folder, and how many of them are kept.
RUNS_DIR = receipt_mod.RUNS_DIR
RUNS_KEEP = 20
DRILL_OK = "ok"
DRILL_FAILED = "failed"
DRILL_SKIP = "skipped"
DRILL_SETUP = "setup"
DRILL_CLASSES = {DRILL_SKIP: "account-drill-skipped", DRILL_SETUP: "account-drill-setup"}
# The A0 record of the last gateway this runner started, and that gateway's log; both outlive the run.
GATEWAY_RECORD = "gateway.json"
GATEWAY_LOG = "gateway.log"
GATEWAY_REUSED = "reused"
GATEWAY_STARTED = "started"
GATEWAY_RESTARTED = "restarted"


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
    phases: Mapping[str, Mapping[str, bool]] | None = None,
) -> tuple[str, dict[str, str] | None]:
    """(status, reason) of a run. A failed assertion is the strongest finding, then a could-not-judge class, then a required phase that did not run, then an empty ledger, then the teardown."""
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
    missing = [
        side
        for side, phase in sorted((phases or {}).items())
        if phase.get("required") and not phase.get("ran")
    ]
    if missing:
        return receipt_mod.NOT_VERIFIED, {
            "class": "phase-not-run",
            "detail": "the required %s phase did not run every step to an ok row (steps %s)"
            % (
                " and ".join(missing),
                "; ".join("%s: %s" % (s, ", ".join(PHASE_STEPS.get(s, ()))) for s in missing),
            ),
        }
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

    def drive_root(self) -> str:
        """Where WSL mounts the Windows drives."""
        return "/mnt"

    def vm_net_address(self, net_base: str) -> str | None:
        """This host's own address on the ops VM network (`wire.bridge_host`), None while no interface sits on it."""
        return wire.bridge_host(net_base)

    def alias_configs(self, environ: Mapping[str, str]) -> list[pathlib.Path]:
        """Every file `vscode connect` may have written its alias to: the Windows home's under the drive mounts first (getSSHHome() on WSL), then $HOME's."""
        found = sorted(pathlib.Path(self.drive_root()).glob("*/Users/*/.ssh/" + ALIAS_CONFIG))
        home = (environ.get("HOME") or "").strip()
        if home:
            found.append(pathlib.Path(home) / ".ssh" / ALIAS_CONFIG)
        return found

    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class Account(Protocol):
    def gateway_healthy(self) -> bool: ...

    def gateway_state(self) -> dict[str, Any]: ...

    def restart(self, log_path: pathlib.Path) -> None: ...

    def detach(self) -> None: ...

    def mint(self, password: str) -> str: ...

    def subscription_note(self) -> str: ...

    def server_url(self, host: str) -> str: ...


def subscription_reuse_refusal(body: Any, now: float) -> str:
    """Why the ACCOUNT_LOGIN subscription `GET /portal/subscription` answered cannot be kept for this run, or "" when it can.

    KEEPING IT IS THE DEFAULT. `/test/ensure-subscription` deletes the customer's subscriptions and creates a new one, so every licence an earlier run issued (the grand's above all) then belongs to a deleted subscription and its renewal is refused. It is still called when the subscription is absent or cannot carry a run: another plan, a status the issuance path does not entitle at that plan, an `expiresAt` in the past, fewer than ISSUANCE_HEADROOM repo-licence issuances left this month, or a machine-slot meter that is full (a new issuance blocks hard at `maxActivations`)."""
    if not isinstance(body, dict) or not body.get("id"):
        return "no subscription"
    if body.get("planCode") != ACCOUNT_PLAN:
        return "plan %s, not %s" % (body.get("planCode"), ACCOUNT_PLAN)
    if body.get("status") not in REUSABLE_STATUSES:
        return "status %s" % body.get("status")
    expires = body.get("expiresAt")
    if expires:
        try:
            ends = datetime.datetime.fromisoformat(str(expires)).timestamp()
        except ValueError:
            return "unreadable expiresAt %r" % expires
        if ends <= now:
            return "expired at %s" % expires
    usage = body.get("repoLicenseIssuances")
    if not isinstance(usage, dict):
        return "no repoLicenseIssuances usage"
    used, limit = usage.get("used"), usage.get("limit")
    if not isinstance(used, int) or not isinstance(limit, int):
        return "unreadable issuance usage %r" % usage
    if limit - used < ISSUANCE_HEADROOM:
        return "%d of %d repo-licence issuances used this month" % (used, limit)
    slots = body.get("machineSlots")
    if isinstance(slots, dict) and isinstance(slots.get("active"), int):
        cap = body.get("maxActivations")
        if isinstance(cap, int) and slots["active"] >= cap:
            return "machine slots full (%d of %d)" % (slots["active"], cap)
    return ""


class DrillAccount:
    """The dev gateway through `lib.Drill`'s helpers. Only A0 starts or restarts it (`restart`), since every start re-randomizes the dev passwords, and a gateway it started is detached so that it outlives the run."""

    def __init__(self, drill: lib.Drill) -> None:
        self.drill = drill
        self.note = ""

    def gateway_healthy(self) -> bool:
        return self.drill.gateway_alive()

    def gateway_state(self) -> dict[str, Any]:
        """`healthy`, plus the `gateway_port=` and `started=` lines of `.account-state` (the last of each, as rdc.sh reads them)."""
        try:
            text = (self.drill.root / ".account-state").read_text(errors="replace")
        except OSError:
            text = ""
        return {
            "healthy": self.drill.gateway_alive(),
            "port": state_value(text, "gateway_port"),
            "started": state_value(text, "started"),
        }

    def restart(self, log_path: pathlib.Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.drill.restart_gateway(log_path=log_path)

    def detach(self) -> None:
        self.drill.detach_gateway()

    def mint(self, password: str) -> str:
        """A token for ACCOUNT_LOGIN on the subscription it already holds, recreated only when `subscription_reuse_refusal` says so (`subscription_note` names which). The session calls go over loopback; the token's first use, and with it its IP binding, is the CLI's."""
        d = self.drill
        d.gateway_port_cached = d.gateway_port()
        d.account_ensure_login(ACCOUNT_LOGIN, password)
        jar = http.cookiejar.CookieJar()
        if not d.account_session(ACCOUNT_LOGIN, password, jar):
            raise lib.GatewayError("no session for %s" % ACCOUNT_LOGIN)
        raw = d._request("GET", d.api_base() + "/portal/subscription", None, jar)
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        refusal = subscription_reuse_refusal(body, time.time())
        if refusal:
            d.account_ensure_subscription(ACCOUNT_LOGIN, ACCOUNT_PLAN)
            subscription = d.account_subscription_id(jar)
            self.note = "subscription recreated (%s)" % refusal
        else:
            subscription = str(body["id"])
            usage = body["repoLicenseIssuances"]
            self.note = "subscription kept (%d of %d issuances used this month)" % (
                usage["used"],
                usage["limit"],
            )
        if not subscription:
            raise lib.GatewayError("no subscription for %s" % ACCOUNT_LOGIN)
        return d.account_mint_token(jar, subscription, MINT_LABEL, list(TOKEN_SCOPES))

    def subscription_note(self) -> str:
        return self.note

    def server_url(self, host: str) -> str:
        """The minting gateway at `host`; empty when no port is recorded. A licence's renewalUrl is stamped from the Host of the request that issued it (private/account src/app.ts baseUrl, routes/license.ts renewalUrlFor), so `host` must be an address the worker reaches."""
        port = self.drill.gateway_port_cached or self.drill.gateway_port()
        return "http://%s:%s" % (host, port) if port and host else ""


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


def key_state(raw: str) -> tuple[Any, str]:
    """`data.embedded` of a `config ssh show -o json` envelope, or None with what the output was instead: not JSON, JSON that is not an object, a `data` that is not an object (review e9309c59.1: those two JSON shapes were reported as not JSON), or no `data.embedded`."""
    try:
        doc = json.loads(raw)
    except ValueError:
        return None, "its output is not JSON"
    if not isinstance(doc, dict):
        return None, "its JSON is a %s, not an object" % type(doc).__name__
    data = doc.get("data")
    if data is not None and not isinstance(data, dict):
        return None, "its JSON data is a %s, not an object" % type(data).__name__
    embedded = (data or {}).get("embedded")
    return embedded, "" if embedded is not None else "its JSON has no data.embedded"


def is_ops_vm_ip(ip: str) -> bool:
    """True only for a dotted IPv4 literal inside OPS_VM_NETWORK/24: a hostname, an IPv6 form or a look-alike such as `192.168.111.11.example.com` is not an ops VM."""
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isascii() and p.isdigit() and int(p) <= 255 for p in parts):
        return False
    return ".".join(parts[:3]) == OPS_VM_NETWORK


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


def failed_assertions(text: str) -> list[str]:
    """`<number> <description>` of every FAIL row in the drill's summary table; empty when there is no summary. The live assertion lines above the summary are not read, so a row is counted once."""
    clean = ANSI_ESCAPE.sub("", text)
    start = clean.rfind(DRILL_SUMMARY_HEADER)
    if start < 0:
        return []
    return ["%s %s" % row for row in DRILL_FAIL_ROW.findall(clean[start:])]


def classify_drill(res: Result) -> tuple[str, str]:
    """(outcome, detail) of one account drill, read from its last summary line: DRILL_FAILED when an assertion failed, DRILL_SKIP for a SKIPPED line or 0 assertions or rc 0 with no summary, DRILL_OK for rc 0 with a positive count and the PASSED line, DRILL_SETUP for anything else (a non-zero rc with no summary is a preflight that stopped the drill)."""
    text = ANSI_ESCAPE.sub("", res.text())
    counts = DRILL_SUMMARY.findall(text)
    total, passed, failed = (int(n) for n in counts[-1]) if counts else (-1, -1, -1)
    if failed > 0:
        # The assertion names, not the tail: the tail is the last failure dump, which on 2026-10-20 was a base64 licence payload.
        names = failed_assertions(text)
        return DRILL_FAILED, "%d of %d assertions failed: %s" % (
            failed,
            total,
            "; ".join(names) if names else last_lines(text),
        )
    if DRILL_SKIPPED.search(text) or total == 0:
        return DRILL_SKIP, "rc=%d, a SKIPPED line or 0 assertions: %s" % (res.rc, last_lines(text))
    if total < 0:
        if res.rc == 0:
            return DRILL_SKIP, "rc=0 with no summary line, so nothing was proven"
        return DRILL_SETUP, "rc=%d with no summary line: %s" % (res.rc, last_lines(text))
    if res.rc != 0 or not DRILL_PASSED.search(text):
        return DRILL_SETUP, "rc=%d, %d assertions and 0 failed, but no PASSED line: %s" % (
            res.rc,
            total,
            last_lines(text),
        )
    return DRILL_OK, "%d assertions passed" % passed


def state_value(text: str, key: str) -> str:
    """The LAST `<key>=` value of a `.account-state` text, as rdc.sh reads it (`grep ... | tail -1`); empty when absent."""
    values = [ln.split("=", 1)[1].strip() for ln in text.splitlines() if ln.startswith(key + "=")]
    return values[-1] if values else ""


def _as_int(value: object) -> int | None:
    text = str(value).strip() if value is not None else ""
    return int(text) if text.isdigit() else None


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
        account_modified_fn: Callable[[pathlib.Path], bool | None] = trigger.account_modified,
        account_digest_fn: Callable[[pathlib.Path], str | None] = trigger.account_worktree_digest,
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
        self.account_modified_fn = account_modified_fn
        self.account_digest_fn = account_digest_fn
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
        # Licence state a P5 sweep could not purge: carried into the T row like a teardown purge, so the run cannot reach VERIFIED over a dead blob.
        self.sweep_leftovers: list[str] = []
        # Run state
        self.token: str | None = None
        self.account_server = ""
        # True while the token was minted on localhost because no interface sat on the VM network yet (a cold fleet): P2 re-mints it on the bridge address once the fleet is up (`p4_rebind`).
        self.minted_on_loopback = False
        # True once P4 minted on the dev gateway: every later `./rdc.sh` call then runs with RDC_DEV=1.
        self.dev_config = False
        # The host `_mint_on` last routed the token to, so a teardown that has to revive the gateway re-mints on the same address.
        self.mint_host = ""
        self.password: str | None = None
        self.machine_ip = ""
        self.grand_created = False
        self.locked = False
        # True when P0 gave up on the fleet lock (`fleet-busy`): the run judged nothing and a holder may still be running, so `_finish` keeps its record under its run id and never touches receipt.json.
        self.lock_lost = False
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
        self.trigger_info: dict[str, Any] = {
            "base": None,
            "via": "always",
            "hits": [],
            "sides": sorted(trigger.SIDES),
        }
        # Both phases unless `--changed` narrows them.
        self.phases: dict[str, dict[str, bool]] = {
            side: {"required": True, "ran": False} for side in trigger.SIDES
        }
        self.account_info: dict[str, Any] = {
            "pointer": "",
            "checkout": "",
            "modified": None,
            "gateway": {"mode": None, "port": None, "started": None},
        }
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
        log_path: str = "",
        failed: Sequence[str] = (),
    ) -> bool:
        """One ledger row. `ok` None is a skip; `assertion` counts it towards the verdict's ledger. `log_path` (the kept full output) and `failed` (a drill's failed assertions) are added to the row only when given."""
        verdict_text = "skip" if ok is None else ("ok" if ok else "FAIL")
        row = {
            "id": step_id,
            "desc": desc,
            "rc": res.rc if res is not None else 0,
            "verdict": verdict_text,
            "ms": res.ms if res is not None else 0,
            "evidence": self._clean(evidence or (res.text() if res is not None and not ok else "")),
        }
        if log_path:
            row["log"] = log_path
        if failed:
            row["failedAssertions"] = [self.scrub(f) for f in failed]
        self.steps.append(row)
        if assertion and ok is not None:
            self.assertions += 1
            if not ok:
                self.failures.append("%s: %s (%s)" % (step_id, desc, row["evidence"]))
        self.say("  %-5s %-5s %s" % (step_id, verdict_text, desc))
        return bool(ok)

    def check(
        self,
        step_id: str,
        desc: str,
        ok: bool,
        res: Result | None = None,
        evidence: str = "",
        *,
        log_path: str = "",
        failed: Sequence[str] = (),
    ) -> bool:
        return self.record(
            step_id, desc, ok, res, evidence, assertion=True, log_path=log_path, failed=failed
        )

    # ------------------------------------------------------------------ evidence

    def run_dir(self) -> pathlib.Path:
        return receipt_mod.receipt_dir(self.root) / RUNS_DIR / self.run_id

    def keep_log(self, step_id: str, name: str, argv: Sequence[str], res: Result) -> str:
        """Write `res`'s full stdout and stderr (scrubbed) to the run directory and return its path relative to the repo root; empty when it cannot be written, which is said."""
        folder = self.run_dir()
        path = folder / ("%s-%s.log" % (step_id, re.sub(r"[^A-Za-z0-9_.-]+", "-", name)))
        body = "$ %s\nrc=%d ms=%d\n--- stdout\n%s\n--- stderr\n%s\n" % (
            " ".join(argv),
            res.rc,
            res.ms,
            res.out,
            res.err,
        )
        try:
            fresh = not folder.is_dir()
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(self.scrub(body), encoding="utf-8")
            if fresh:
                self._prune_runs()
        except OSError as exc:
            self.say("        could not keep the output of %s: %s" % (step_id, exc))
            return ""
        return str(path.relative_to(self.root)) if path.is_relative_to(self.root) else str(path)

    def _prune_runs(self) -> None:
        """Keep the newest RUNS_KEEP run directories."""
        runs = self.run_dir().parent
        dirs = sorted(
            (d for d in runs.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True
        )
        for old in dirs[RUNS_KEEP:]:
            shutil.rmtree(old, ignore_errors=True)

    # ------------------------------------------------------------------ commands

    def child_env(self) -> dict[str, str]:
        env = dict(self.environ)
        if self.token:
            env["REDIACC_TOKEN"] = self.token
            env["REDIACC_ACCOUNT_SERVER"] = self.account_server
        if self.dev_config:
            env["RDC_DEV"] = "1"
        return env

    def drill_env(self) -> dict[str, str]:
        """The environment of an A1 suite or an A2 drill: this process's, never `child_env()`, with DRILL_ENV_SCRUB removed and `.ci` on PYTHONPATH by absolute path."""
        env = {k: v for k, v in self.environ.items() if k not in DRILL_ENV_SCRUB}
        ci = str(self.root / ".ci")
        rest = [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p and p != ci]
        env["PYTHONPATH"] = os.pathsep.join([ci, *rest])
        return env

    def git(self, *args: str, cwd: pathlib.Path | None = None) -> str:
        res = self.host.run(["git", "-C", str(cwd or self.root), *args], env=self.environ)
        return res.out.strip() if res.rc == 0 else ""

    def rdc(
        self,
        *args: str,
        timeout: float | None = None,
        refuse: bool = True,
        extra_env: Mapping[str, str] | None = None,
    ) -> Result:
        """`./rdc.sh <args>` with the child environment, plus `extra_env` for this one call. A refusal by the agent guard ends the run (unless `refuse` is False, as in teardown)."""
        env = self.child_env()
        env.update(extra_env or {})
        res = self.host.run([self.rdc_sh, *args], env=env, timeout=timeout)
        if refuse and res.rc != 0 and any(m in res.err for m in AGENT_REFUSALS):
            raise NotVerifiedError(
                "agent-policy-refused",
                "rdc %s: %s" % (" ".join(args[:3]), first_line(res.err)),
            )
        return res

    def shell(self, fork: str, command: str, extra_env: Mapping[str, str] | None = None) -> Result:
        return self.rdc("term", "connect", fork, "-c", command, extra_env=extra_env)

    def remote_evidence(self, res: Result) -> str:
        """A failed remote command's evidence, stderr first: `term connect` puts the remote stderr on stderr and a JSON envelope on stdout, and the envelope alone filled the 200-byte evidence (2026-10-15)."""
        return "rc=%d stderr: %s | stdout: %s" % (
            res.rc,
            last_lines(res.err) or "<empty>",
            last_lines(res.out) or "<empty>",
        )

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
        self._read_account()
        self._note_old_receipts()
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
                "vm:check: no push base resolved (tried %s); running the full check, both phases"
                % ", ".join(base.tried)
            )
            self.trigger_info = {
                "base": None,
                "via": "unresolved",
                "hits": [],
                "sides": sorted(trigger.SIDES),
            }
            return True
        changed = trigger.changed_paths(self.root, base.merge_base, "worktree")
        # A touched change always names a side (a hit carries its side, an unknown range its submodule's); none at all would be a trigger defect, so it costs both phases rather than none.
        sides = set(changed.sides) or set(trigger.SIDES)
        self.trigger_info = {
            "base": base.ref,
            "via": base.via,
            "hits": [*changed.hits, *("unknown " + u for u in changed.unknown)],
            "sides": sorted(sides),
        }
        if not changed.touched:
            self.say(
                "vm:check: no trigger path changed since %s (via %s); nothing to verify"
                % (base.ref, base.via)
            )
            return False
        for side in trigger.SIDES:
            self.phases[side]["required"] = side in sides
        self.say(
            "vm:check: %d trigger path(s) changed since %s (via %s), sides %s:"
            % (len(self.trigger_info["hits"]), base.ref, base.via, ", ".join(sorted(sides)))
        )
        for hit in self.trigger_info["hits"][:10]:
            self.say("  %s" % hit)
        return True

    def _read_account(self) -> None:
        """The account pointer, checkout and worktree state the receipt records; an account phase on a checkout that is not the pointer, or modified, is said up front, since its receipt cannot admit a push."""
        info = self.account_info
        info["pointer"] = self.git("rev-parse", "HEAD:%s" % trigger.ACCOUNT_SUBMODULE)
        sub = self.root / trigger.ACCOUNT_SUBMODULE
        # An uninitialized submodule is an empty directory, and git would walk up and answer the console's HEAD.
        info["checkout"] = (
            self.git("rev-parse", "HEAD", cwd=sub) if self.host.exists(str(sub / ".git")) else ""
        )
        info["modified"] = self.account_modified_fn(self.root)
        if not self.phases[SIDE_ACCOUNT]["required"]:
            return
        if not info["checkout"] or info["checkout"] != info["pointer"]:
            self.say(
                "vm:check: the %s checkout %s is not the pointer %s, so this receipt cannot admit a push of the account side (account-mismatch)"
                % (
                    trigger.ACCOUNT_SUBMODULE,
                    info["checkout"][:12] or "<none>",
                    info["pointer"][:12] or "<none>",
                )
            )
        if info["modified"] is not False:
            self.say(
                "vm:check: the %s worktree is %s, so this receipt cannot admit a push of the account side (modified-account)"
                % (
                    trigger.ACCOUNT_SUBMODULE,
                    "unreadable" if info["modified"] is None else "modified",
                )
            )

    def _note_old_receipts(self) -> None:
        """One line when the receipt folder holds receipts of an earlier schema, which no longer count."""
        old = 0
        for path in receipt_mod.receipt_files(self.root):
            with contextlib.suppress(OSError, ValueError):
                doc = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(doc, dict) and doc.get("schema") != receipt_mod.SCHEMA:
                    old += 1
        if old:
            self.say(
                "vm:check: %d receipt(s) of an earlier schema in %s no longer count; this run writes schema %d"
                % (old, receipt_mod.CACHE_DIR, receipt_mod.SCHEMA)
            )

    def _steps(self) -> None:
        renet = self.phases[SIDE_RENET]["required"]
        account = self.phases[SIDE_ACCOUNT]["required"]
        self.say(
            "vm:check: phases %s"
            % ", ".join(
                "%s %s" % (side, "required" if self.phases[side]["required"] else "not required")
                for side in trigger.SIDES
            )
        )
        # A1 before P0: the suites hold no fleet lock, and a red suite stops the run before any VM is touched.
        if account and not self.a1_suites():
            return
        self.p0_lock()
        self.p1_renet()
        if account:
            self.a0_gateway()
        # P4 before P2: the account decides which config the fleet, machine and key steps read and write.
        self.p4_account()
        self.p2_fleet()
        self.p4_rebind()
        self.p3_keys()
        # A2 before P5: the license drill deploys its enforcing renet build, and P5's first plain ./rdc.sh deploys the default one back.
        if account and not self.a2_drills():
            return
        if not renet:
            return
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
        try:
            waited = self.lock.acquire(self.host, self.opts.wait_s, session)
        except NotVerifiedError:
            self.lock_lost = True
            raise
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
        if self.dev_config:
            self._ensure_dev_machine()
        elif not self.machine:
            machines = _data_list(self.rdc("machine", "list", "-o", "json").out)
            names = [str(m.get("name")) for m in machines if str(m.get("ip")) == self.worker_ip]
            if not names:
                raise NotVerifiedError(
                    "worker-not-in-config",
                    "no machine in the active config has ip %s; register it once: ./rdc.sh machine add <name> --ip %s --user %s"
                    % (self.worker_ip, self.worker_ip, self.ssh_user),
                )
            self.machine = names[0]
            self.machine_ip = self.worker_ip
        self.record(
            "P2",
            "fleet %s (%s), worker %s" % (self.fleet_mode, " ".join(running), self.machine),
            True,
        )

    def _ensure_dev_machine(self) -> None:
        """Find the worker in the dev config, registering it as OPS_WORKER_NAME when the config does not hold it; the operator's default config is never read or written here."""
        listed = self.rdc("machine", "list", "-o", "json")
        if listed.rc != 0:
            # An unreadable dev config ("Decryption failed" against a gateway whose E2E key it does not carry) is the account side, not a missing registration.
            raise NotVerifiedError(
                "account-unavailable",
                "machine list in the dev config rc=%d: %s" % (listed.rc, rdc_failure(listed)),
            )
        machines = _data_list(listed.out)
        if self.machine:
            ips = [str(m.get("ip", "")) for m in machines if str(m.get("name")) == self.machine]
            if not ips:
                raise NotVerifiedError(
                    "worker-not-in-config",
                    "--machine %s is not in the dev config; register it once: ./rdc.sh --dev machine add %s --ip %s --user %s"
                    % (self.machine, self.machine, self.worker_ip, self.ssh_user),
                )
            self.machine_ip = ips[0]
            return
        names = [str(m.get("name")) for m in machines if str(m.get("ip")) == self.worker_ip]
        if names:
            self.machine = names[0]
            self.machine_ip = self.worker_ip
            return
        args = ("machine", "add", OPS_WORKER_NAME, "--ip", self.worker_ip, "--user", self.ssh_user)
        res = self.rdc(*args)
        if res.rc != 0:
            raise NotVerifiedError(
                "worker-not-in-config",
                "the dev config has no machine at %s, and ./rdc.sh --dev %s failed rc=%d: %s"
                % (self.worker_ip, " ".join(args), res.rc, rdc_failure(res)),
            )
        self.machine = OPS_WORKER_NAME
        self.machine_ip = self.worker_ip
        self.say(
            "        the dev config had no machine at %s; registered it as %s"
            % (self.worker_ip, OPS_WORKER_NAME)
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
        embedded, shape = key_state(show.out)
        if show.rc != 0 or embedded is None:
            why = shape if show.rc == 0 else "rc=%d: %s" % (show.rc, rdc_failure(show))
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
        addr = self.host.vm_net_address(self.opts.net_base) or ""
        self.minted_on_loopback = not addr
        if not addr:
            self.say(
                "        no interface on %s.0/24 yet, so the token is minted on localhost for the fleet steps and re-minted on this host's VM-network address once P2 has the fleet up"
                % self.opts.net_base
            )
        self._mint_on(addr or "localhost")

    def _mint_on(self, host: str) -> None:
        """Mint a token, check it, and route every later CLI call to the gateway at `host`. The CLI names that server on every licence request, and the account stamps the licence's renewalUrl from it, so `host` is the address the worker reaches it at (wire.bridge_host: measured 2026-10-20, the worker reaches http://192.168.111.254:<port> and every blob minted over localhost carried a renewalUrl it could not)."""
        password = secrets.token_urlsafe(24)
        self.password = password
        try:
            token = self.account.mint(password)
        except (lib.GatewayError, OSError) as exc:
            raise NotVerifiedError(
                "account-unavailable", "minting a token for %s failed: %s" % (ACCOUNT_LOGIN, exc)
            ) from None
        server = self.account.server_url(host)
        if not server:
            raise NotVerifiedError(
                "account-unavailable",
                "a token was minted but the dev gateway's address is unknown (no gateway_port in .account-state)",
            )
        self.token = token
        self.account_server = server
        self.dev_config = True
        self.mint_host = host
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
        self.record(
            "P4",
            "token minted for %s on %s (%s), passed as REDIACC_TOKEN only; later CLI calls run under the dev config"
            % (
                ACCOUNT_LOGIN,
                server,
                self.account.subscription_note() or "subscription unreported",
            ),
            True,
        )

    def p4_rebind(self) -> None:
        """After P2: a token P4 minted on localhost is replaced by one minted on the VM-network address, before anything issues a licence. A fleet that is up with no such address is `fleet-unavailable`, since every licence the run issued would carry a renewalUrl the worker cannot reach."""
        if not self.minted_on_loopback:
            return
        addr = self.host.vm_net_address(self.opts.net_base)
        if not addr:
            raise NotVerifiedError(
                "fleet-unavailable",
                "the fleet is up but this host has no address on %s.0/24, so no licence this run issues could renew from the worker"
                % self.opts.net_base,
            )
        self.minted_on_loopback = False
        self._mint_on(addr)

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
        # The sweep runs before the grand is judged, so stale forks beside a missing grand go too (review 8b3374e0.2: the create path returned before it).
        swept, sweep = self._sweep_stale_forks(
            names, {str(e.get("name", "")): str(e.get("guid", "")) for e in entries}
        )
        if self.opts.parent not in names:
            grands = sorted(n for n in names if n and ":" not in n)
            ip = self._machine_ip()
            if not is_ops_vm_ip(ip):
                raise NotVerifiedError(
                    "parent-grand-missing",
                    "no grand %s on %s (%s, not the ops VM network %s.0/24; grands present: %s); the operator creates it once, outside agent mode: %s./rdc.sh repo create %s -m %s --size %s%s"
                    % (
                        self.opts.parent,
                        self.machine,
                        ip or "address unknown",
                        OPS_VM_NETWORK,
                        ", ".join(grands) or "none",
                        # A cold run boots fresh VMs and `ops down` removes them, so its worker can never hold the grand (2026-10-15T00:27Z); the fleet comes up first, then the grand is created on it.
                        "./rdc.sh ops up --basic, then " if self.fleet_started else "",
                        self.opts.parent,
                        self.machine,
                        GRAND_SIZE,
                        ", and leave the fleet up for vm:check to reuse (this run started it cold, "
                        "and fresh VMs never hold a grand)"
                        if self.fleet_started
                        else "",
                    ),
                )
            self._create_grand(ip, grands, swept, sweep)
            return
        self.record(
            "P5",
            "parent grand %s present; %d stale fork(s) swept" % (self.opts.parent, len(swept)),
            True,
            evidence=sweep,
        )

    def _sweep_stale_forks(
        self, names: Sequence[str], guids: Mapping[str, str] | None = None
    ) -> tuple[list[str], str]:
        """Delete the parent's `vmc-` forks older than STALE_FORK_S, nothing else, and purge the licence state of the ones deleted (`guids` maps a listed name to its guid); returns the deleted names and the evidence line, which is also said when it is not empty."""
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
        unpurged = self.purge_licences(
            [(guids or {}).get(name, "") for name in swept], "the swept forks"
        )
        if unpurged:
            evidence += "; %s" % unpurged
            self.sweep_leftovers.append(unpurged)
        evidence = evidence.strip("; ")
        if evidence:
            self.say("        stale forks: %s" % evidence)
        return swept, evidence

    def purge_licences(self, guids: Sequence[str], what: str) -> str:
        """Purge the licence state of deleted repositories on the worker through `term connect <worker> -c` (`lib.purge_license_state_script`, which proves renet no longer lists each guid first). Returns "" when every guid was purged, else the leftover line. A value that is not a repository guid is said and left alone."""
        valid = [g for g in guids if lib.is_repo_guid(g)]
        odd = [g for g in guids if g and not lib.is_repo_guid(g)]
        if odd:
            self.say(
                "        licence state of %s left alone: %s is not a repository guid"
                % (what, ", ".join(repr(g) for g in odd))
            )
        if not valid or not self.machine:
            return ""
        res = self.rdc(
            "term",
            "connect",
            self.machine,
            "-c",
            lib.purge_license_state_script(valid),
            refuse=False,
        )
        if res.rc == 0:
            return ""
        return "licence state of %s (%s; purge rc=%d: %s)" % (
            what,
            ", ".join(valid),
            res.rc,
            last_lines(res.out) or last_lines(res.err) or "no output",
        )

    def _machine_ip(self) -> str:
        """The worker's configured address: known from P2 when the worker was found by its ip, read from `machine list` when `--machine` named it."""
        if not self.machine_ip:
            machines = _data_list(self.rdc("machine", "list", "-o", "json").out)
            ips = [str(m.get("ip", "")) for m in machines if str(m.get("name")) == self.machine]
            self.machine_ip = ips[0] if ips else ""
        return self.machine_ip

    def _create_grand(
        self, ip: str, grands: Sequence[str], swept: Sequence[str], sweep: str
    ) -> None:
        """Create the missing parent grand on an ops VM worker, under P4's credential; the ops VMs are development-only (operator ruling 2026-10-15), so this is never an operator's step."""
        args = ("repo", "create", self.opts.parent, "-m", self.machine, "--size", GRAND_SIZE)
        credential = "the minted token" if self.token else "the config's stored token"
        self.say(
            "        no grand %s on %s (%s, a development-only ops VM; grands present: %s); creating it with ./rdc.sh %s under %s"
            % (
                self.opts.parent,
                self.machine,
                ip,
                ", ".join(grands) or "none",
                " ".join(args),
                credential,
            )
        )
        res = self.rdc(*args, timeout=1800)
        forgot = ""
        if res.rc != 0 and STALE_CONFIG_ENTRY in rdc_failure(res):
            # The grand is absent on the worker but the config still lists it. `repo delete --archive-config` converges to absent: with the image gone it skips the machine, archives the config entry (freeing the name) and removes the repo's SSH config entry and key.
            first = res
            forget_args = ("repo", "delete", self.opts.parent, "--archive-config", "-y")
            self.say(
                "        config still lists %s though %s has no such grand; forgetting it with ./rdc.sh %s"
                % (self.opts.parent, self.machine, " ".join(forget_args))
            )
            forget = self.rdc(*forget_args, timeout=600)
            if forget.rc != 0:
                raise NotVerifiedError(
                    "parent-grand-missing",
                    "no grand %s on %s, the config lists it, and forgetting it failed: ./rdc.sh %s rc=%d: %s (after ./rdc.sh %s rc=%d: %s)"
                    % (
                        self.opts.parent,
                        self.machine,
                        " ".join(forget_args),
                        forget.rc,
                        rdc_failure(forget),
                        " ".join(args),
                        first.rc,
                        rdc_failure(first),
                    ),
                )
            forgot = "stale config entry forgotten with ./rdc.sh %s rc=0" % " ".join(forget_args)
            res = self.rdc(*args, timeout=1800)
            if res.rc != 0 and NO_DATASTORE not in rdc_failure(res):
                raise NotVerifiedError(
                    "parent-grand-missing",
                    "no grand %s on %s; ./rdc.sh %s rc=0 forgot the stale config entry, but creating it still failed: ./rdc.sh %s rc=%d: %s"
                    % (
                        self.opts.parent,
                        self.machine,
                        " ".join(forget_args),
                        " ".join(args),
                        res.rc,
                        rdc_failure(res),
                    ),
                )
        if res.rc != 0 and NO_DATASTORE in rdc_failure(res):
            # A fresh ops VM has renet but no BTRFS datastore (2026-10-15 live run); preparing it is the same development-only step as the grand.
            self.say(
                "        %s has no datastore; preparing it with ./rdc.sh machine setup %s"
                % (self.machine, self.machine)
            )
            setup = self.rdc("machine", "setup", self.machine, timeout=1800)
            if setup.rc != 0:
                raise NotVerifiedError(
                    "parent-grand-missing",
                    "no grand %s on %s, its datastore is missing, and ./rdc.sh machine setup %s failed rc=%d: %s"
                    % (self.opts.parent, self.machine, self.machine, setup.rc, rdc_failure(setup)),
                )
            res = self.rdc(*args, timeout=1800)
        if res.rc != 0:
            raise NotVerifiedError(
                "parent-grand-missing",
                "no grand %s on %s, and creating it on the ops VM failed: ./rdc.sh %s rc=%d: %s"
                % (self.opts.parent, self.machine, " ".join(args), res.rc, rdc_failure(res)),
            )
        listed, entries = self.repo_list()
        if self.opts.parent not in [str(e.get("name", "")) for e in entries]:
            raise NotVerifiedError(
                "parent-grand-missing",
                "./rdc.sh %s exited 0 but repo list -m %s (rc=%d) does not show %s"
                % (" ".join(args), self.machine, listed.rc, self.opts.parent),
            )
        self.grand_created = True
        self.record(
            "P5",
            "parent grand %s created on %s (ops VM %s) under %s; %d stale fork(s) swept"
            % (self.opts.parent, self.machine, ip, credential, len(swept)),
            True,
            res,
            evidence="; ".join(
                e
                for e in (
                    forgot,
                    "./rdc.sh %s rc=0 in %d s" % (" ".join(args), res.ms // 1000),
                    sweep,
                )
                if e
            ),
        )

    # ------------------------------------------------------------------ A

    def a1_suites(self) -> bool:
        """The four account suites, each an assertion row; True when all four exited 0."""
        env = self.drill_env()
        green = True
        for step_id, script, package in ACCOUNT_SUITES:
            prefix = self.root / package if package else self.root
            res = self.host.run(
                ["npm", "--prefix", str(prefix), "run", script], env=env, timeout=SUITE_TIMEOUT_S
            )
            ok = res.rc == 0
            spelled = "npm %srun %s" % ("--prefix %s " % package if package else "", script)
            self.check(
                step_id,
                "%s (%d s)" % (spelled, res.ms // 1000),
                ok,
                res,
                "" if ok else "rc=%d: %s" % (res.rc, last_lines(res.text())),
                log_path=self.keep_log(step_id, script, ["npm", "run", script], res),
            )
            green = green and ok
        if not green:
            self.say("        an account suite is red; no VM is touched")
        return green

    def _gateway_paths(self) -> tuple[pathlib.Path, pathlib.Path]:
        folder = receipt_mod.receipt_dir(self.root)
        return folder / GATEWAY_RECORD, folder / GATEWAY_LOG

    def _read_gateway_record(self, path: pathlib.Path) -> dict[str, Any] | None:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return doc if isinstance(doc, dict) else None

    @staticmethod
    def gateway_stale(
        state: Mapping[str, Any], record: Mapping[str, Any] | None, account: str
    ) -> str:
        """Why the running gateway cannot be reused, or "" when it can: it answers, it is the one the record names (same `started` and port), and it was started on the account worktree digest `account`."""
        if not state.get("healthy"):
            return "no healthy dev gateway answers"
        if record is None:
            return "no record of a gateway this runner started"
        now = (str(state.get("started") or ""), str(state.get("port") or ""))
        then = (str(record.get("started") or ""), str(record.get("port") or ""))
        if not now[0] or now != then:
            return (
                "the running gateway (started=%s, port %s) is not the recorded one (started=%s, port %s)"
                % (now[0] or "?", now[1] or "?", then[0] or "?", then[1] or "?")
            )
        if record.get("account") != account:
            return "private/account changed since the recorded gateway started"
        return ""

    def a0_gateway(self) -> None:
        """Reuse the dev gateway only when its record matches the account worktree; otherwise start it, record it and leave it running."""
        record_path, log_path = self._gateway_paths()
        digest = self.account_digest_fn(self.root)
        if digest is None:
            raise NotVerifiedError(
                "account-gateway",
                "the %s worktree is unreadable (not checked out, or git failed), so the gateway's freshness cannot be judged"
                % trigger.ACCOUNT_SUBMODULE,
            )
        state = self.account.gateway_state()
        stale = self.gateway_stale(state, self._read_gateway_record(record_path), digest)
        if not stale:
            mode = GATEWAY_REUSED
            desc = "dev gateway reused on port %s (started=%s; its record matches the account worktree)"
        else:
            mode = GATEWAY_RESTARTED if state.get("healthy") else GATEWAY_STARTED
            self.say(
                "        dev gateway: %s; %s it with ./run.sh account dev (log %s)"
                % (stale, "restarting" if mode == GATEWAY_RESTARTED else "starting", log_path)
            )
            state = self._start_gateway(log_path, state)
            self._write_gateway_record(record_path, state, digest)
            self.say(
                "        dev gateway %s on port %s (was %s): every dev password rotated, and configs pinned to the old port lose their writes"
                % (mode, state.get("port") or "?", state.get("port_before") or "none")
            )
            desc = "dev gateway %s on port %%s (started=%%s), recorded and left running" % mode
        self.account_info["gateway"] = {
            "mode": mode,
            "port": _as_int(state.get("port")),
            "started": _as_int(state.get("started")),
        }
        self.record("A0", desc % (state.get("port") or "?", state.get("started") or "?"), True)

    def _start_gateway(self, log_path: pathlib.Path, before: Mapping[str, Any]) -> dict[str, Any]:
        """Start the gateway, detach it, and return its new state; `account-gateway` with the log tail when it does not come up healthy."""
        try:
            self.account.restart(log_path)
        except (lib.GatewayError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise NotVerifiedError(
                "account-gateway",
                "./run.sh account dev did not bring a healthy gateway up: %s; log tail: %s"
                % (exc, self._log_tail(log_path)),
            ) from None
        # Detached before anything else can fail, so the next run reuses it rather than this run's teardown killing it.
        self.account.detach()
        state = dict(self.account.gateway_state())
        if not state.get("healthy") or not state.get("port") or not state.get("started"):
            raise NotVerifiedError(
                "account-gateway",
                "the dev gateway started but does not answer (port %s, started=%s); log tail: %s"
                % (state.get("port") or "?", state.get("started") or "?", self._log_tail(log_path)),
            )
        state["port_before"] = before.get("port") or ""
        return state

    @staticmethod
    def _log_tail(path: pathlib.Path) -> str:
        try:
            return last_lines(path.read_text(errors="replace")) or "<empty log>"
        except OSError as exc:
            return "<no log at %s: %s>" % (path, exc.strerror or exc)

    @staticmethod
    def _write_gateway_record(path: pathlib.Path, state: Mapping[str, Any], account: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(".%s.%d" % (path.name, os.getpid()))
        tmp.write_text(
            json.dumps(
                {
                    "port": str(state.get("port") or ""),
                    "started": str(state.get("started") or ""),
                    "account": account,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def drill_argvs(self) -> tuple[tuple[str, str, list[str]], ...]:
        """(step id, drill, argv) of A2, in run order."""
        python = sys.executable or "python3"
        worker = self.machine_ip or self.worker_ip
        return (
            ("A2.1", "universe", [python, "-m", "rediacc_ci.drills.universe", "--no-restart"]),
            ("A2.2", "transfer", [python, "-m", "rediacc_ci.drills.transfer", "--no-restart"]),
            (
                "A2.3",
                "license",
                [
                    python,
                    "-m",
                    "rediacc_ci.drills.license",
                    "--legs",
                    LICENSE_LEGS,
                    "--no-restart",
                    "--seed-repo",
                    "--vm",
                    worker,
                ],
            ),
        )

    def a2_drills(self) -> bool:
        """The three account drills, each judged by `classify_drill`. False after a failed row; a could-not-judge drill raises once all three ran."""
        env = self.drill_env()
        pending: tuple[str, str] | None = None
        green = True
        for step_id, name, argv in self.drill_argvs():
            res = self.host.run(argv, env=env, timeout=DRILL_TIMEOUT_S)
            outcome, detail = classify_drill(res)
            desc = "drill %s (%d s): %s" % (name, res.ms // 1000, outcome)
            kept = self.keep_log(step_id, name, argv, res)
            where = " (full output: %s)" % kept if kept else ""
            if outcome in (DRILL_OK, DRILL_FAILED):
                ok = outcome == DRILL_OK
                self.check(
                    step_id,
                    desc,
                    ok,
                    res,
                    "" if ok else "drill %s: %s%s" % (name, detail, where),
                    log_path=kept,
                    failed=failed_assertions(res.text()),
                )
                if not ok:
                    for line in failed_assertions(res.text()):
                        self.say("          FAIL %s" % line)
                    if kept:
                        self.say("          full output: %s" % kept)
                green = green and ok
                continue
            self.record(
                step_id, desc, False, res, "drill %s: %s%s" % (name, detail, where), log_path=kept
            )
            if pending is None:
                pending = (DRILL_CLASSES[outcome], "%s drill %s: %s" % (step_id, name, detail))
        if not green:
            return False
        if pending is not None:
            raise NotVerifiedError(*pending)
        return True

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
        ref = self.ref(a)
        mnt = shlex.quote(self.mount(a))
        marker = "vmc-shm-%s" % self.run_id
        for desc, command in (
            ("write ~", "echo vmc > ~/vmc-home"),
            ("write /tmp", "echo vmc > /tmp/vmc-tmp"),
            ("write /dev/shm", "echo vmc > /dev/shm/%s" % marker),
            ("write the mount", "echo vmc > %s/vmc-mount" % mnt),
        ):
            self._positive(ref, desc, command, WRITE_ROW_ENV)
        self._positive(ref, "chmod 600 in the mount", "chmod 600 %s/vmc-mount" % mnt)
        self._positive(ref, "docker ps", "docker ps")
        if self._upload_compose(ref):
            self._positive(ref, "renet compose -- ps", "cd %s && renet compose -- ps" % mnt)
        else:
            self.record(
                "V1.3", "A: renet compose -- ps not run: no compose file in the mount", None
            )
        self._positive(
            ref,
            "git commit in the mount",
            "cd %s && rm -rf vmc-git && mkdir vmc-git && cd vmc-git && git init -q && git -c user.email=vm@check -c user.name=vmcheck commit -q --allow-empty -m vmcheck"
            % mnt,
        )
        self._editor_write(ref)

    def _positive(
        self, ref: str, desc: str, command: str, extra_env: Mapping[str, str] | None = None
    ) -> bool:
        res = self.shell(ref, command, extra_env)
        ok = res.rc == 0
        return self.check("V1.3", "A: %s" % desc, ok, res, "" if ok else self.remote_evidence(res))

    def _upload_compose(self, ref: str) -> bool:
        """The minimal compose file, synced into fork A's mount root; the grand stays as it is."""
        up = self.work / "compose-up"
        up.mkdir(parents=True, exist_ok=True)
        (up / COMPOSE_FILE).write_text(COMPOSE_BODY)
        res = self.rdc("repo", "sync", "upload", ref, "--local", str(up) + "/")
        return self.check(
            "V1.3", "A: %s uploaded into the mount by sync" % COMPOSE_FILE, res.rc == 0, res
        )

    def _editor_write(self, ref: str) -> None:
        probe = self.shell(ref, VI_PROBE)
        if probe.rc == 0 and probe.out.strip():
            self._positive(ref, "vi writes ~/v", VI_WRITE)
            return
        # `command -v` exits 1 for a missing command; any other failure (an ssh drop, a refused shell) established nothing about vi (review 5a9861e8.2).
        if probe.rc != 1:
            self.check(
                "V1.3",
                "A: the vi probe answered (present or absent)",
                False,
                probe,
                "%s rc=%d; %s" % (VI_PROBE, probe.rc, self.remote_evidence(probe)),
            )
            return
        res = self.shell(ref, SED_WRITE, WRITE_ROW_ENV)
        ok = res.rc == 0
        absent = "vi absent on %s (%s rc=%d)" % (self.fleet_os or "the worker", VI_PROBE, probe.rc)
        self.check(
            "V1.3",
            "A: sed -i rewrites ~/v by temp file and rename (vi absent)",
            ok,
            res,
            absent if ok else absent + "; " + self.remote_evidence(res),
        )

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
        expected = {k: v for k, v in sent.items() if k not in SYNC_DROPPED}
        differ = sorted(k for k in set(expected) | set(got) if expected.get(k) != got.get(k))
        self.check(
            "V1.5",
            "round trip is byte-identical (%d entries; %s left out, never synced)"
            % (len(expected), ", ".join(SYNC_DROPPED)),
            not differ,
            evidence="differ: %s" % ", ".join(differ),
        )
        for name in SYNC_DROPPED:
            target = shlex.quote("%s/%s/%s" % (self.mount(a), remote, name))
            res = self.shell(self.ref(a), "test ! -L %s && test ! -e %s" % (target, target))
            self.check(
                "V1.5",
                "the %s is absent on the remote (a privileged sync carries no symlink)" % name,
                res.rc == 0,
                res,
                "" if res.rc == 0 else self.remote_evidence(res),
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
        config = self._sftp_config()
        if config is None:
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
                [*SFTP_BATCH, "-F", str(config), "-b", str(batch), self.connection],
                env=self.environ,
                timeout=120,
            )
            ok = res.rc == 0 if allowed else res.rc != 0 and sftp_refused(res.text(), other_dir)
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

    def _sftp_config(self) -> pathlib.Path | None:
        """An ssh config holding only the alias block `vscode connect` wrote, with Windows drive paths spelled for WSL and the identity copied to a 0600 file (a key under /mnt/c reads as 0777, which ssh refuses). None after a failed row when no block or no identity can be read."""
        drive_root = self.host.drive_root()
        searched = self.host.alias_configs(self.environ)
        source: pathlib.Path | None = None
        block: list[str] | None = None
        for path in searched:
            try:
                block = alias_block(path.read_text(errors="replace"), self.connection)
            except OSError:
                continue
            if block is not None:
                source = path
                break
        if source is None or block is None:
            self.check(
                "V1.7",
                "the alias %s is in a %s vscode connect wrote" % (self.connection, ALIAS_CONFIG),
                False,
                evidence="searched %s" % (", ".join(map(str, searched)) or "<no candidate>"),
            )
            return None
        lines = ["Host %s" % self.connection]
        for line in block:
            key, _, value = line.partition(" ")
            if key.lower() == "identityfile":
                identity = pathlib.Path(drive_path(value, drive_root))
                copy = self.work / "sftp_identity"
                try:
                    key_bytes = identity.read_bytes()
                except OSError as exc:
                    self.check(
                        "V1.7",
                        "the alias's identity is readable",
                        False,
                        evidence="%s (from %s): %s" % (identity, source, exc),
                    )
                    return None
                try:
                    # Created 0600 and exclusively, never widened then narrowed: a umask-mode copy of a private key is readable by other local users until a chmod, and an existing file would keep its own mode through O_CREAT (review 5a9861e8.3, f434e6dc.4).
                    copy.unlink(missing_ok=True)
                    fd = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "wb") as out:
                        out.write(key_bytes)
                except OSError as exc:
                    self.check(
                        "V1.7",
                        "the alias's identity is copied into the work directory",
                        False,
                        evidence="%s: %s" % (copy, exc),
                    )
                    return None
                value = str(copy)
            elif key.lower() == "userknownhostsfile":
                value = drive_path(value, drive_root)
                value = '"%s"' % value if " " in value else value
            lines.append("  %s %s" % (key, value.strip()))
        config = self.work / "ssh_config"
        config.write_text("\n".join(lines) + "\n")
        config.chmod(0o600)
        self.check(
            "V1.7",
            "ssh config for %s built from %s" % (self.connection, source),
            True,
            evidence="%d directive(s)" % len(block),
        )
        return config

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
        leftovers: list[str] = list(self.sweep_leftovers)
        try:
            leftovers.extend(self._teardown_steps())
        except CRASHES as exc:
            leftovers.append(self.scrub("teardown crashed: %s: %s" % (type(exc).__name__, exc)))
        finally:
            self.lock.release()
            self.locked = False
        self.leftovers = leftovers
        if not self.forks and not self.fleet_started and not self.connection and not leftovers:
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

    def _revive_gateway_for_teardown(self) -> str | None:
        """Bring the dev gateway back when teardown needs it and it is gone; a leftover note when that fails, else None.

        A stopped run can lose the gateway it started detached: the harness kills by process tree, the `run.sh account dev` wrapper then removes `.account-state`, and every `repo delete` under RDC_DEV=1 fails "no running dev gateway recorded" (2026-10-21, forks vmc-10210020-1b0ebe-a/-b left behind). A restart rotates the dev passwords and may move the port, so the token is minted again on the same host rather than trusted.
        """
        if not (self.dev_config and self.forks) or self.account.gateway_healthy():
            return None
        record_path, log_path = self._gateway_paths()
        try:
            self.account.restart(log_path)
            self.account.detach()
            digest = self.account_digest_fn(self.root)
            if digest is not None:
                self._write_gateway_record(record_path, self.account.gateway_state(), digest)
            self._mint_on(self.mint_host or "localhost")
        except (
            NotVerifiedError,
            lib.GatewayError,
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as exc:
            return "dev gateway gone before teardown and not revived (%s)" % exc
        self.say(
            "        teardown: the dev gateway was gone, so it was restarted and the token re-minted before the deletes"
        )
        return None

    def _teardown_steps(self) -> list[str]:
        leftovers: list[str] = []
        revive_failure = self._revive_gateway_for_teardown()
        if revive_failure:
            leftovers.append(revive_failure)
        if self.connection:
            res = self.rdc("vscode", "cleanup", "-c", self.connection, refuse=False)
            if res.rc != 0:
                leftovers.append("vscode connection %s (cleanup rc=%d)" % (self.connection, res.rc))
        delete_errors: dict[str, str] = {}
        for fork in self.forks:
            res = self.rdc("repo", "delete", self.ref(fork["tag"]), "-y", refuse=False)
            fork["deleted"] = res.rc == 0
            if res.rc != 0:
                # The delete's own answer, so a leftover says why it stayed (2026-10-15: a teardown left both forks and the receipt named neither cause).
                delete_errors[self.ref(fork["tag"])] = "delete rc=%d: %s" % (
                    res.rc,
                    rdc_failure(res),
                )
        if self.forks:
            res, entries = self.repo_list()
            names = {str(e.get("name", "")) for e in entries}
            if res.rc != 0:
                # The delete's own error rides along when the list cannot confirm it (review a6e93fb9.1): an unreadable list must not hide why a delete failed.
                leftovers.extend(
                    "fork %s (repo list unreadable%s)"
                    % (
                        self.ref(f["tag"]),
                        "; " + delete_errors[self.ref(f["tag"])]
                        if self.ref(f["tag"]) in delete_errors
                        else "",
                    )
                    for f in self.forks
                )
            for fork in self.forks:
                if self.ref(fork["tag"]) in names:
                    fork["deleted"] = False
                    why = delete_errors.get(self.ref(fork["tag"]), "delete rc=0, still listed")
                    leftovers.append("fork %s (%s)" % (self.ref(fork["tag"]), why))
                elif res.rc == 0:
                    fork["deleted"] = True
            gone = [str(f.get("guid") or "") for f in self.forks if f.get("deleted")]
            leftover = self.purge_licences(gone, "this run's forks")
            if leftover:
                leftovers.append(leftover)
        if self.fleet_mode == COLD and self.fleet_started:
            res = self.rdc("ops", "down", refuse=False, timeout=600)
            if res.rc != 0:
                leftovers.append("cold fleet still up (ops down rc=%d)" % res.rc)
        return leftovers

    # ------------------------------------------------------------------ summary and receipt

    def phase_ran(self, side: str) -> bool:
        """True only when every step of the phase recorded a row and every such row is ok."""
        wanted = PHASE_STEPS[side]
        rows = [r for r in self.steps if r["id"] in wanted]
        return {r["id"] for r in rows} == set(wanted) and all(r["verdict"] == "ok" for r in rows)

    def _finish(self) -> int:
        for side in trigger.SIDES:
            self.phases[side]["ran"] = self.phase_ran(side)
        status, reason = verdict(
            self.assertions, self.failures, self.reason, self.leftovers, self.phases
        )
        path: pathlib.Path | None = None
        if self.tree and self.lock_lost:
            # A lock loser's record is for the record only (VC7(a)): the holder's receipt.json and tree archive stay as they are.
            fresh = not self.run_dir().is_dir()
            self.run_dir().mkdir(parents=True, exist_ok=True)
            if fresh:
                self._prune_runs()
            path = receipt_mod.write_run_record(self.root, self._receipt(status, reason))
        elif self.tree:
            path = receipt_mod.write(self.root, self._receipt(status, reason))
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
            "phases": {side: dict(phase) for side, phase in self.phases.items()},
            "account": {**self.account_info, "gateway": dict(self.account_info["gateway"])},
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
            "runDir": (
                str(self.run_dir().relative_to(self.root))
                if self.run_id and self.run_dir().is_dir()
                else None
            ),
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
        if not any(r["id"].startswith("A") for r in self.steps):
            self.say("  %-5s %-6s %s" % ("--", "skip", "A1-A2 not run"))
        if not any(r["id"].startswith("V") for r in self.steps):
            self.say("  %-5s %-6s %s" % ("--", "skip", "V1.1-V1.7 not run"))
        self.say(
            "  %d assertion(s), %d failed; phases: %s"
            % (
                self.assertions,
                len(self.failures),
                ", ".join(
                    "%s %s"
                    % (
                        side,
                        ("ran" if phase["ran"] else "NOT RUN")
                        if phase["required"]
                        else "not required",
                    )
                    for side, phase in sorted(self.phases.items())
                ),
            )
        )
        gateway = self.account_info["gateway"]
        if gateway["mode"]:
            self.say(
                "  dev gateway: %s on port %s, left running for the next run"
                % (gateway["mode"], gateway["port"])
            )
        if status == receipt_mod.VERIFIED:
            self.say("  vm:check VERIFIED")
        elif reason is not None:
            label = "FAILED" if status == receipt_mod.FAILED else "NOT VERIFIED"
            self.say("  vm:check %s (%s): %s" % (label, reason["class"], reason["detail"]))
            if status == receipt_mod.NOT_VERIFIED:
                # Teardown runs after the assertions, so a run that only failed to clean up did judge the VMs.
                judged = (
                    "%d assertion(s) ran, and the run still does not count" % self.assertions
                    if self.assertions
                    else "Nothing on the VMs was judged"
                )
                self.say("  %s. The push guard treats this tree as NOT verified." % judged)
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
            if self.lock_lost:
                self.say(
                    "  this run never held the fleet lock, so %s and the tree archives were left as they were"
                    % receipt_mod.LATEST
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
    account_modified_fn: Callable[[pathlib.Path], bool | None] = trigger.account_modified,
    account_digest_fn: Callable[[pathlib.Path], str | None] = trigger.account_worktree_digest,
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
        account_modified_fn=account_modified_fn,
        account_digest_fn=account_digest_fn,
    )
    try:
        return check.run()
    finally:
        drill.teardown()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

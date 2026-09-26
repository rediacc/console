"""`rediacc_ci.infra.wait_for_vm_ssh`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/infra/wait-for-vm-ssh.sh` and the port over one stubbed PATH and compared FIVE things per case: exit code, stdout, stderr, the call SEQUENCE and the bytes of `~/.ssh/known_hosts`. The K=5 ledger `.ci/shadow/w7p6-wait-for-vm-ssh.observations.jsonl` recorded that comparison over five distinct trees.

THE TWIN HAS NOW BEEN DELETED, and every case compares against `goldens/wait-for-vm-ssh/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree. Each provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

ALL FIVE CHANNELS ARE STILL COMPARED, which is why the recorded shape carries two sections beyond the two streams. `--- calls ---` holds the stubbed argv log, because the interesting failures are invisible in the text: a port that probed with different ssh options, or that ran `ssh-keyscan` before the guest answered, prints exactly what a correct one prints. `--- known hosts ---`
holds the file the run leaves behind, because it is the subject's only durable side effect and the one thing a later step depends on; a port that announced "SSH-ready" and never ran `ssh-keyscan` would pass every stream comparison and leave every subsequent ssh in the job failing host-key verification.

THE STUBS ARE UNCHANGED FROM THE DIFFERENTIAL. Stub `ssh` and `ssh-keyscan` sit on a scratch PATH that REPLACES rather than prepends, `$HOME` is per run, and `sleep`, `cut` and `nproc` are stubbed too. The PATH rule is carried over from the sibling `verify-ssh` fixture, where a prepend let the "no ssh on PATH" case silently reach the machine's real ssh and try to resolve a hostname
on the network while the comparison stayed green. The 36-attempt budget is driven in full, not shortened, because there is no knob to shorten it with and inventing one would be a feature wearing a port's clothes; it costs milliseconds only because both implementations resolve `sleep` through PATH.

WHAT IS NORMALISED, and it is the fixture's own directories. The run directory and the per-run `$HOME` are named in the stub log and can appear in a diagnostic, and a recording is compared against directories built under a different tempdir name months later, so they become `<work>` and `<home>`. Nothing else is touched.

TWO REFUSALS DIVERGE IN TEXT AND ARE COMPARED BY SHAPE, exactly as they were while both copies existed: `${VM_NET_BASE:?...}` and the `set -u` death on `$USER`. Both are bash diagnostics carrying the twin's path and LINE NUMBER, which no port can reproduce and no recording should demand.

Exit code, stdout, the call sequence and the words the caller can act on are compared, and the twin's recorded wording stays in the golden as the evidence of what it said.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import wait_for_vm_ssh as w
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "wait_for_vm_ssh.py"
SLUG = "wait-for-vm-ssh"

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

CALLS_MARKER = "--- calls ---\n"
HOSTS_MARKER = "--- known hosts ---\n"

BASE_ENV = {
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

FAKE_SSH = """#!%(python)s
import os, sys
LOG = %(log)r
COUNTER = %(counter)r
SUCCEED_ON = %(succeed_on)r
OUT = %(out)r
ERR = %(err)r
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("ssh\\t" + "\\t".join(sys.argv[1:]) + "\\n")
# THE COUNTER IS PER TARGET, not per run: the subject waits for each VM in
# turn, so "answers on the third try" has to mean the third try FOR THAT VM.
# Keying the counter on the target is what lets a case make one VM answer and
# another never answer.
target = [a for a in sys.argv[1:] if "@" in a]
key = target[0] if target else "?"
path = COUNTER + "." + key.replace("/", "_")
n = 0
if os.path.exists(path):
    n = int(open(path).read() or "0")
n += 1
open(path, "w").write(str(n))
want = SUCCEED_ON.get(key.split("@")[-1], SUCCEED_ON.get("*", 0))
if OUT:
    sys.stdout.write(OUT)
if ERR:
    sys.stderr.write(ERR)
sys.exit(0 if want and n >= want else 255)
"""

FAKE_TOOL = """#!%(python)s
import sys
LOG = %(log)r
NAME = %(name)r
OUT = %(out)r
RC = %(rc)d
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write(NAME + "\\t" + "\\t".join(sys.argv[1:]) + "\\n")
if OUT:
    sys.stdout.write(OUT)
sys.exit(RC)
"""

# See the module docstring's note on the replaced PATH. `ssh` and `ssh-keyscan` are deliberately absent.
ALLOWED_REAL_TOOLS = (
    "dirname",
    "basename",
    "cat",
    "mkdir",
    "rm",
    "env",
    "uname",
    "id",
    "tr",
    "head",
    "wc",
    "sed",
    "grep",
)

USER = {"SSH_USER": "fixtureuser"}

# name -> argv, environment, which attempt each target answers on, and the stub wiring
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "immediate": {"argv": ["10.0.0.1"], "env": USER, "succeed_on": {"*": 1}},
    "keyscan-after": {"argv": ["10.0.0.1"], "env": USER, "succeed_on": {"*": 3}},
    "exhausted": {"argv": ["10.0.0.1"], "env": USER, "succeed_on": {"*": 0}},
    "diag-fallbacks": {
        "argv": ["10.0.0.1"],
        "env": USER,
        "succeed_on": {"*": 0},
        "stub": {"cut_rc": 1, "nproc_rc": 1},
    },
    "second-vm-dead": {
        "argv": ["10.0.0.1", "10.0.0.11"],
        "env": USER,
        "succeed_on": {"10.0.0.1": 1, "10.0.0.11": 0},
    },
    "both-vms": {"argv": ["10.0.0.1", "10.0.0.11"], "env": USER, "succeed_on": {"*": 1}},
    "net-base": {
        "argv": [],
        "env": {**USER, "VM_NET_BASE": "192.168.111"},
        "succeed_on": {"*": 1},
    },
    "keyscan-fails": {
        "argv": ["10.0.0.1", "10.0.0.11"],
        "env": USER,
        "succeed_on": {"*": 1},
        "stub": {"keyscan_rc": 4},
    },
    "no-ssh": {
        "argv": ["10.0.0.1"],
        "env": USER,
        "succeed_on": {"*": 1},
        "stub": {"with_ssh": False},
    },
    "no-keyscan": {
        "argv": ["10.0.0.1"],
        "env": USER,
        "succeed_on": {"*": 1},
        "stub": {"with_keyscan": False},
    },
    "no-targets-no-base": {"argv": [], "env": USER, "succeed_on": {"*": 1}},
    "user-unbound": {"argv": ["10.0.0.1"], "env": {}, "succeed_on": {"*": 1}},
    "user-fallback": {"argv": ["10.0.0.1"], "env": {"USER": "envuser"}, "succeed_on": {"*": 1}},
    "ssh-user-wins": {
        "argv": ["10.0.0.1"],
        "env": {"USER": "envuser", "SSH_USER": "chosen"},
        "succeed_on": {"*": 1},
    },
    "ssh-user-empty": {
        "argv": ["10.0.0.1"],
        "env": {"USER": "envuser", "SSH_USER": ""},
        "succeed_on": {"*": 1},
    },
    "ssh-stderr-dropped": {
        "argv": ["10.0.0.1"],
        "env": USER,
        "succeed_on": {"*": 0},
        "stub": {"ssh_stderr": "ssh: connect to host 10.0.0.1 port 22: Connection refused\n"},
    },
}

CASES = tuple(CASE_KW)

# The two cases whose refusal text is a bash diagnostic. Compared by shape, in their own tests.
DIVERGENT = ("no-targets-no-base", "user-unbound")


def sysbin(where: pathlib.Path) -> pathlib.Path:
    where.mkdir(parents=True, exist_ok=True)
    for name in ALLOWED_REAL_TOOLS:
        real = shutil.which(name)
        if real is None:
            continue
        link = where / name
        if not link.exists():
            link.symlink_to(real)
    assert (where / "dirname").exists(), "the subject cannot start without dirname"
    assert not (where / "ssh").exists(), "a real ssh leaked onto the fixture PATH"
    return where


def stubs(
    where: pathlib.Path,
    log: pathlib.Path,
    counter: pathlib.Path,
    *,
    succeed_on: dict[str, int],
    ssh_stdout: str = "ready\n",
    ssh_stderr: str = "",
    keyscan_rc: int = 0,
    keyscan_out: str = "vm ssh-ed25519 AAAAFIXTUREKEY\n",
    cut_rc: int = 0,
    nproc_rc: int = 0,
    with_ssh: bool = True,
    with_keyscan: bool = True,
) -> pathlib.Path:
    where.mkdir(parents=True, exist_ok=True)
    if with_ssh:
        ssh = where / "ssh"
        ssh.write_text(
            FAKE_SSH
            % {
                "python": PYTHON,
                "log": str(log),
                "counter": str(counter),
                "succeed_on": succeed_on,
                "out": ssh_stdout,
                "err": ssh_stderr,
            },
            encoding="utf-8",
        )
        ssh.chmod(0o755)
    tools = [
        ("sleep", "", 0),
        # `cut -d' ' -f1-3 /proc/loadavg` and `nproc`, stubbed so the failure line is deterministic. A non-zero rc drives the `|| echo unavailable` / `|| echo unknown` fallbacks, which are otherwise unreachable on any machine with a /proc.
        ("cut", "" if cut_rc else "0.10 0.20 0.30\n", cut_rc),
        ("nproc", "" if nproc_rc else "8\n", nproc_rc),
    ]
    if with_keyscan:
        tools.append(("ssh-keyscan", keyscan_out, keyscan_rc))
    for name, out, rc in tools:
        tool = where / name
        tool.write_text(
            FAKE_TOOL % {"python": PYTHON, "log": str(log), "name": name, "out": out, "rc": rc},
            encoding="utf-8",
        )
        tool.chmod(0o755)
    return where


def run(subject: pathlib.Path, workdir: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    """One subject, once, over this case's own scratch PATH and HOME."""
    kw = CASE_KW[name]
    stub = dict(kw.get("stub") or {})
    workdir.mkdir(parents=True, exist_ok=True)
    log = workdir / "calls.log"
    log.write_text("", encoding="utf-8")
    home = workdir / "home"
    home.mkdir(parents=True, exist_ok=True)
    binder = stubs(
        workdir / "bin", log, workdir / "counter", succeed_on=dict(kw["succeed_on"]), **stub
    )
    env = dict(BASE_ENV)
    env["HOME"] = str(home)
    env.update(kw["env"])
    env["PATH"] = "%s:%s" % (binder, sysbin(workdir / "sysbin"))
    resolved = shutil.which("ssh", path=env["PATH"])
    if stub.get("with_ssh", True):
        assert resolved == str(binder / "ssh"), "the stub ssh is not what PATH resolves"
    else:
        assert resolved is None, "the 'no ssh on PATH' case can still see an ssh: %r" % resolved
    runner = [BASH] if subject.suffix == ".sh" else [PYTHON]
    proc = subprocess.run(
        [*runner, str(subject), *kw["argv"]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(workdir),
        timeout=180,
    )
    known_hosts = home / ".ssh" / "known_hosts"
    mask = lambda text: text.replace(str(workdir), "<work>").replace(str(home), "<home>")  # noqa: E731
    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(log.read_text(encoding="utf-8")),
        mask(known_hosts.read_text(encoding="utf-8")) if known_hosts.exists() else "<absent>",
    )


def render(code: int, stdout: str, stderr: str, calls: str, known_hosts: str) -> str:
    return "%s%s%s%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        calls,
        HOSTS_MARKER,
        known_hosts,
    )


def recorded(name: str) -> tuple[int, str, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(CALLS_MARKER, 1)
    calls, known_hosts = rest.split(HOSTS_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        calls,
        known_hosts.removesuffix("\n"),
    )


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    return run(PORT, tmp_path / name, name)


def verbs(calls: str) -> list[str]:
    return [line.split("\t")[0] for line in calls.splitlines() if line]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the call SEQUENCE", "~/.ssh/known_hosts")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


def compare_by_shape(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    """Everything but the wording of the refusal, for the two bash diagnostics."""
    want = recorded(name)
    got = port(tmp_path, name)
    for index, label in (
        (0, "exit code"),
        (1, "stdout"),
        (3, "the call SEQUENCE"),
        (4, "known_hosts"),
    ):
        assert want[index] == got[index], "%s: %s diverged: %r vs %r" % (
            name,
            label,
            want[index],
            got[index],
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_immediate_success() -> None:
    code, stdout, stderr, calls, known_hosts = recorded("immediate")
    assert code == 0
    assert stdout == "ready\n", "the guest's stdout must reach the caller unredirected"
    assert "VM 10.0.0.1 is SSH-ready" in stderr
    assert verbs(calls) == ["ssh", "ssh-keyscan"], calls
    assert known_hosts == "vm ssh-ed25519 AAAAFIXTUREKEY\n"


def test_keyscan_runs_only_after_the_vm_answers() -> None:
    """The central ordering claim, asserted rather than assumed: a half-booted guest must never get its key into known_hosts."""
    _, _, _, calls, known_hosts = recorded("keyscan-after")
    order = verbs(calls)
    assert order == ["ssh", "sleep", "ssh", "sleep", "ssh", "ssh-keyscan"], order
    assert order.index("ssh-keyscan") == len(order) - 1
    assert "FIXTUREKEY" in known_hosts


def test_exhausted_budget() -> None:
    """36 attempts, then one refusal and one diagnostic line. Nothing is written to known_hosts, because the VM never answered."""
    code, _, stderr, calls, known_hosts = recorded("exhausted")
    assert code == 1
    assert "VM 10.0.0.1 SSH not ready after 180s" in stderr
    assert "load average (1m 5m 15m): 0.10 0.20 0.30, cores: 8" in stderr
    order = verbs(calls)
    assert order.count("ssh") == 36, order.count("ssh")
    assert order.count("sleep") == 36, order.count("sleep")
    assert "ssh-keyscan" not in order
    # `mkdir -p ~/.ssh` still ran, so the directory exists and the file does not.
    assert known_hosts == "<absent>"
    assert "(36/36)" in stderr


def test_diagnostic_fallbacks() -> None:
    """The `|| echo unavailable` / `|| echo unknown` arms, driven by making the two diagnostic programs fail. Unreachable on any machine with a /proc, which is exactly why they are worth a stub."""
    assert "load average (1m 5m 15m): unavailable, cores: unknown" in recorded("diag-fallbacks")[2]


def test_every_vm_must_answer() -> None:
    """The quantifier, and the difference from `verify-ssh`: this subject waits for EVERY target, and one unreachable VM fails the run even though an earlier one answered."""
    code, _, stderr, calls, known_hosts = recorded("second-vm-dead")
    assert code == 1
    assert "VM 10.0.0.1 is SSH-ready" in stderr
    assert "VM 10.0.0.11 SSH not ready" in stderr
    # The first VM's key IS recorded before the second one fails.
    assert "FIXTUREKEY" in known_hosts
    assert verbs(calls).count("ssh-keyscan") == 1


def test_all_vms_answer() -> None:
    code, _, _, calls, known_hosts = recorded("both-vms")
    assert code == 0
    assert verbs(calls) == ["ssh", "ssh-keyscan", "ssh", "ssh-keyscan"], calls
    assert known_hosts.count("FIXTUREKEY") == 2, "both keys must be APPENDED, not overwritten"


def test_vm_net_base_default_targets() -> None:
    """With no arguments the target list is `<base>.1` and `<base>.11`."""
    _, _, stderr, calls, _ = recorded("net-base")
    assert "Waiting for 192.168.111.1 as fixtureuser..." in stderr
    assert "Waiting for 192.168.111.11 as fixtureuser..." in stderr
    # The login target is the field carrying `@`, NOT a fixed index: the argv ends `<user>@<vm> echo ready`, so `[-2]` is the literal `echo`.
    hosts = [
        field
        for line in calls.splitlines()
        if line.startswith("ssh\t")
        for field in line.split("\t")
        if "@" in field
    ]
    assert hosts == ["fixtureuser@192.168.111.1", "fixtureuser@192.168.111.11"], hosts


def test_keyscan_failure_aborts_the_whole_run() -> None:
    """HAZARD 2, pinned. `ssh-keyscan` is the last command in the success branch and is unguarded, so under `set -e` a non-zero exit kills the run: after "SSH-ready" has already been printed, with no message of its own, and without waiting for the remaining VM."""
    code, _, stderr, calls, _ = recorded("keyscan-fails")
    assert code == 4, "the run must die with ssh-keyscan's own status"
    assert "VM 10.0.0.1 is SSH-ready" in stderr
    assert "10.0.0.11" not in stderr, "the second VM must never be reached"
    assert verbs(calls) == ["ssh", "ssh-keyscan"], calls


def test_missing_binaries() -> None:
    """`require_cmd ssh` then `require_cmd ssh-keyscan`, in that order."""
    code, _, stderr, calls, _ = recorded("no-ssh")
    assert code == 1
    assert "Required command 'ssh' is not available" in stderr
    assert verbs(calls) == []

    code, _, stderr, calls, _ = recorded("no-keyscan")
    assert code == 1
    assert "Required command 'ssh-keyscan' is not available" in stderr
    assert verbs(calls) == [], "the binary check must happen before any probe"


def test_user_env_is_the_fallback() -> None:
    """`${SSH_USER:-$USER}`: SSH_USER wins, USER is the fallback, and an EMPTY SSH_USER falls through rather than logging in as nobody."""
    assert "envuser@10.0.0.1" in recorded("user-fallback")[3].splitlines()[0]
    assert "chosen@10.0.0.1" in recorded("ssh-user-wins")[3].splitlines()[0]
    assert "envuser@10.0.0.1" in recorded("ssh-user-empty")[3].splitlines()[0]


def test_ssh_stderr_is_discarded() -> None:
    """`2>/dev/null` on the probe: ssh's own chatter must NOT reach the caller, unlike `verify-ssh`, which lets it through. The two twins disagreed here on purpose and both ports keep their own side of it."""
    assert "Connection refused" not in recorded("ssh-stderr-dropped")[2]


def test_pure_helpers_are_exercised_directly() -> None:
    assert w.default_targets("192.168.111") == ["192.168.111.1", "192.168.111.11"]
    assert w.ATTEMPTS == 36
    assert w.BUDGET_LABEL == "180s"
    # The label and the loop must agree: 36 x 5 = 180.
    assert "%ds" % (w.ATTEMPTS * int(w.RETRY_SLEEP)) == w.BUDGET_LABEL


# --------------------------------------------------------------------------- The two divergences, pinned rather than papered over ---------------------------------------------------------------------------


def test_divergence_no_targets_and_no_net_base(tmp_path: pathlib.Path) -> None:
    """`${VM_NET_BASE:?...}` is a bash diagnostic carrying the twin's path and line number. Everything a caller can act on is compared, and the port must still name the variable."""
    code, stdout, stderr, calls, _ = compare_by_shape(tmp_path, "no-targets-no-base")
    assert code == 1
    assert stdout == ""
    assert "VM_NET_BASE" in stderr
    assert "VM_NET_BASE" in recorded("no-targets-no-base")[2]
    assert verbs(calls) == []


def test_divergence_neither_ssh_user_nor_user_is_set(tmp_path: pathlib.Path) -> None:
    """HAZARD 1: with neither SSH_USER nor USER exported the subject dies before printing anything of its own, under `set -u`."""
    code, _, stderr, calls, _ = compare_by_shape(tmp_path, "user-unbound")
    assert code == 1
    assert "USER" in stderr
    assert "USER" in recorded("user-unbound")[2]
    assert verbs(calls) == []


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_change_to_the_keyscan_argv_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `ssh-keyscan <vm>` records every key type the guest offers; `ssh-keyscan -t rsa <vm>` records one, and on a guest with no RSA key it records nothing at all while still exiting 0. The stub answers the same bytes either way, so exit code, stdout, stderr and `~/.ssh/known_hosts` are identical and only the `--- calls ---` section sees the change. The mutation runs from a throwaway
    copy of the module, and the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '                        ["ssh-keyscan", vm],\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant_source = original.replace(
        anchor, '                        ["ssh-keyscan", "-t", "rsa", vm],\n'
    )

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutant_source, encoding="utf-8")

    name = "immediate"
    planted = run(mutant, tmp_path / "planted", name)
    want = recorded(name)
    assert "ssh-keyscan\t10.0.0.1" in want[3], "the recorded corpus moved"
    assert planted[3] != want[3], "the plant did not change the call sequence"
    assert "ssh-keyscan\t-t\trsa\t10.0.0.1" in planted[3]
    for index in (0, 1, 2, 4):
        assert planted[index] == want[index], "the plant was supposed to be invisible here"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original

"""Differential: `rediacc_ci.infra.wait_for_vm_ssh` against its twin
`.ci/scripts/infra/wait-for-vm-ssh.sh`.

SAME TECHNIQUE AS `test_infra_verify_ssh.py`, and for the same reason: the subject is a retry loop around a network call, so requiring a reachable VM would mean the differential never ran anywhere. Stub `ssh` and `ssh-keyscan` sit on a scratch PATH, every external program records its argv into one shared log, and each case compares FIVE things -- exit code, stdout, stderr, the call
SEQUENCE, and the bytes of `~/.ssh/known_hosts`.

`known_hosts` IS COMPARED, not just the exit code, because it is the subject's only durable side effect and the one thing a later step depends on. A port that announced "SSH-ready" and never ran `ssh-keyscan` would pass every stream comparison and leave every subsequent ssh in the job failing host-key verification.

PATH IS REPLACED, NEVER PREPENDED, and `$HOME` is per side. The PATH rule is carried over from the sibling file, where a prepend let the "no ssh on PATH"
case silently reach the machine's real ssh and try to resolve a hostname on the
network while the comparison stayed green. `$HOME` has to be per side because both implementations APPEND to `~/.ssh/known_hosts`: one shared home would let the first side's key become part of the second side's expected file.

THE 36-ATTEMPT BUDGET IS DRIVEN IN FULL, not shortened, because there is no knob to shorten it with and inventing one would be a feature wearing a port's clothes. It costs milliseconds only because both implementations resolve `sleep` through PATH (the port EXECS it rather than calling `time.sleep`), so one stub serves both.

TWO REFUSALS DIVERGE IN TEXT AND ARE COMPARED BY SHAPE: `${VM_NET_BASE:?...}`
and the `set -u` failure on `$USER`. Both are bash diagnostics carrying the
twin's path and LINE NUMBER; exit code, stream, ordering and call sequence are
compared exactly.

K=5 LEDGER: `.ci/shadow/w7p6-wait-for-vm-ssh.observations.jsonl`, recorded
against a disposable scratch git repository built outside this checkout.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.infra import wait_for_vm_ssh as w

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "wait-for-vm-ssh.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "wait_for_vm_ssh.py"

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

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

# See the sibling file's note. `ssh` and `ssh-keyscan` are deliberately absent.
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


def _sysbin(where: pathlib.Path) -> pathlib.Path:
    where.mkdir(parents=True, exist_ok=True)
    for name in ALLOWED_REAL_TOOLS:
        real = shutil.which(name)
        if real is None:
            continue
        link = where / name
        if not link.exists():
            link.symlink_to(real)
    assert (where / "dirname").exists(), "the twin cannot start without dirname"
    assert not (where / "ssh").exists(), "a real ssh leaked onto the fixture PATH"
    return where


def _bin(
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
        # `cut -d' ' -f1-3 /proc/loadavg` and `nproc`, stubbed so the failure line is deterministic. A non-zero rc drives the twin's `|| echo unavailable` / `|| echo unknown` fallbacks, which are otherwise unreachable on any machine with a /proc.
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


def _run(
    subject: pathlib.Path,
    workdir: pathlib.Path,
    argv: list[str],
    env_extra: dict[str, str],
    *,
    succeed_on: dict[str, int],
    with_ssh: bool = True,
    with_keyscan: bool = True,
    **stub: object,
) -> tuple[int, str, str, list[str], str]:
    log = workdir / "calls.log"
    log.write_text("", encoding="utf-8")
    home = workdir / "home"
    home.mkdir(parents=True, exist_ok=True)
    binder = _bin(
        workdir / "bin",
        log,
        workdir / "counter",
        succeed_on=succeed_on,
        with_ssh=with_ssh,
        with_keyscan=with_keyscan,
        **stub,
    )
    env = dict(BASE_ENV)
    env["HOME"] = str(home)
    env.update(env_extra)
    env["PATH"] = "%s:%s" % (binder, _sysbin(workdir / "sysbin"))
    resolved = shutil.which("ssh", path=env["PATH"])
    if with_ssh:
        assert resolved == str(binder / "ssh"), "the stub ssh is not what PATH resolves"
    else:
        assert resolved is None, "the 'no ssh on PATH' case can still see an ssh: %r" % resolved
    runner = [BASH] if subject.suffix == ".sh" else [PYTHON]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(workdir),
        timeout=180,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    kh = home / ".ssh" / "known_hosts"
    return (
        proc.returncode,
        proc.stdout,
        proc.stderr,
        calls,
        (kh.read_text(encoding="utf-8") if kh.exists() else "<absent>"),
    )


def _compare(
    name: str,
    argv: list[str],
    env_extra: dict[str, str] | None = None,
    *,
    succeed_on: dict[str, int] | None = None,
    exact_stderr: bool = True,
    **stub: object,
) -> tuple[int, str, str, list[str], str]:
    with tempfile.TemporaryDirectory() as td:
        results = []
        for subject in (TWIN, PORT):
            workdir = pathlib.Path(td) / subject.stem
            workdir.mkdir(parents=True)
            results.append(
                _run(
                    subject,
                    workdir,
                    argv,
                    dict(env_extra or {}),
                    succeed_on=dict(succeed_on or {"*": 1}),
                    **stub,
                )
            )
        old, new = results
    labels = ("exit code", "stdout", "stderr", "the call SEQUENCE", "~/.ssh/known_hosts")
    # `strict=True`: the tuple and the labels must stay the same length, and a
    # silently truncated zip is how a comparison stops checking its last field.
    for i, (label, a, b) in enumerate(zip(labels, old, new, strict=True)):
        if i == 2 and not exact_stderr:
            continue
        assert a == b, "%s: %s diverged:\n--- twin ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return old


USER = {"SSH_USER": "fixtureuser"}


def test_immediate_success() -> None:
    exit_code, stdout, stderr, calls, kh = _compare(
        "immediate", ["10.0.0.1"], USER, succeed_on={"*": 1}
    )
    assert exit_code == 0
    assert stdout == "ready\n", "the guest's stdout must reach the caller unredirected"
    assert "VM 10.0.0.1 is SSH-ready" in stderr
    assert [c.split("\t")[0] for c in calls] == ["ssh", "ssh-keyscan"], calls
    assert kh == "vm ssh-ed25519 AAAAFIXTUREKEY\n"


def test_keyscan_runs_only_after_the_vm_answers() -> None:
    """The twin's central ordering claim, asserted rather than assumed: a
    half-booted guest must never get its key into known_hosts."""
    _, _, _, calls, kh = _compare("keyscan-after", ["10.0.0.1"], USER, succeed_on={"*": 3})
    verbs = [c.split("\t")[0] for c in calls]
    assert verbs == ["ssh", "sleep", "ssh", "sleep", "ssh", "ssh-keyscan"], verbs
    assert verbs.index("ssh-keyscan") == len(verbs) - 1
    assert "FIXTUREKEY" in kh


def test_exhausted_budget() -> None:
    """36 attempts, then one refusal and one diagnostic line. Nothing is
    written to known_hosts, because the VM never answered."""
    exit_code, _, stderr, calls, kh = _compare("exhausted", ["10.0.0.1"], USER, succeed_on={"*": 0})
    assert exit_code == 1
    assert "VM 10.0.0.1 SSH not ready after 180s" in stderr
    assert "load average (1m 5m 15m): 0.10 0.20 0.30, cores: 8" in stderr
    verbs = [c.split("\t")[0] for c in calls]
    assert verbs.count("ssh") == 36, verbs.count("ssh")
    assert verbs.count("sleep") == 36, verbs.count("sleep")
    assert "ssh-keyscan" not in verbs
    # `mkdir -p ~/.ssh` still ran, so the directory exists and the file does not.
    assert kh == "<absent>"
    assert "(36/36)" in stderr


def test_diagnostic_fallbacks() -> None:
    """The `|| echo unavailable` / `|| echo unknown` arms, driven by making the
    two diagnostic programs fail. Unreachable on any machine with a /proc,
    which is exactly why they are worth a stub."""
    _, _, stderr, _, _ = _compare(
        "diag-fallbacks",
        ["10.0.0.1"],
        USER,
        succeed_on={"*": 0},
        cut_rc=1,
        nproc_rc=1,
    )
    assert "load average (1m 5m 15m): unavailable, cores: unknown" in stderr


def test_every_vm_must_answer() -> None:
    """The quantifier, and the difference from `verify-ssh.sh`: this subject
    waits for EVERY target, and one unreachable VM fails the run even though an
    earlier one answered."""
    exit_code, _, stderr, calls, kh = _compare(
        "second-vm-dead",
        ["10.0.0.1", "10.0.0.11"],
        USER,
        succeed_on={"10.0.0.1": 1, "10.0.0.11": 0},
    )
    assert exit_code == 1
    assert "VM 10.0.0.1 is SSH-ready" in stderr
    assert "VM 10.0.0.11 SSH not ready" in stderr
    # The first VM's key IS recorded before the second one fails.
    assert "FIXTUREKEY" in kh
    assert [c.split("\t")[0] for c in calls].count("ssh-keyscan") == 1


def test_all_vms_answer() -> None:
    exit_code, _, _, calls, kh = _compare(
        "both-vms", ["10.0.0.1", "10.0.0.11"], USER, succeed_on={"*": 1}
    )
    assert exit_code == 0
    assert [c.split("\t")[0] for c in calls] == ["ssh", "ssh-keyscan", "ssh", "ssh-keyscan"], calls
    assert kh.count("FIXTUREKEY") == 2, "both keys must be APPENDED, not overwritten"


def test_vm_net_base_default_targets() -> None:
    """With no arguments the target list is `<base>.1` and `<base>.11`."""
    _, _, stderr, calls, _ = _compare(
        "net-base", [], {**USER, "VM_NET_BASE": "192.168.111"}, succeed_on={"*": 1}
    )
    assert "Waiting for 192.168.111.1 as fixtureuser..." in stderr
    assert "Waiting for 192.168.111.11 as fixtureuser..." in stderr
    # The login target is the field carrying `@`, NOT a fixed index: the argv ends `<user>@<vm> echo ready`, so `[-2]` is the literal `echo`.
    hosts = [f for c in calls if c.startswith("ssh\t") for f in c.split("\t") if "@" in f]
    assert hosts == ["fixtureuser@192.168.111.1", "fixtureuser@192.168.111.11"], hosts


def test_keyscan_failure_aborts_the_whole_run() -> None:
    """HAZARD 2, pinned. `ssh-keyscan` is the last command in the success
    branch and is unguarded, so under `set -e` a non-zero exit kills the run -- after "SSH-ready" has already been printed, with no message of its own, and
    without waiting for the remaining VM."""
    exit_code, _, stderr, calls, _ = _compare(
        "keyscan-fails",
        ["10.0.0.1", "10.0.0.11"],
        USER,
        succeed_on={"*": 1},
        keyscan_rc=4,
    )
    assert exit_code == 4, "the run must die with ssh-keyscan's own status"
    assert "VM 10.0.0.1 is SSH-ready" in stderr
    assert "10.0.0.11" not in stderr, "the second VM must never be reached"
    assert [c.split("\t")[0] for c in calls] == ["ssh", "ssh-keyscan"], calls


def test_missing_binaries() -> None:
    """`require_cmd ssh` then `require_cmd ssh-keyscan`, in that order."""
    exit_code, _, stderr, calls, _ = _compare(
        "no-ssh", ["10.0.0.1"], USER, succeed_on={"*": 1}, with_ssh=False
    )
    assert exit_code == 1
    assert "Required command 'ssh' is not available" in stderr
    assert calls == [], calls

    exit_code, _, stderr, calls, _ = _compare(
        "no-keyscan", ["10.0.0.1"], USER, succeed_on={"*": 1}, with_keyscan=False
    )
    assert exit_code == 1
    assert "Required command 'ssh-keyscan' is not available" in stderr
    assert calls == [], "the binary check must happen before any probe"


def test_refusals_that_diverge_only_in_text() -> None:
    """`${VM_NET_BASE:?...}` and the `set -u` death on `$USER`. Compared on
    exit code, stream, call sequence and shape; see the module docstring."""
    exit_code, stdout, stderr, calls, _ = _compare(
        "no-targets-no-base", [], USER, succeed_on={"*": 1}, exact_stderr=False
    )
    assert exit_code == 1
    assert stdout == ""
    assert "VM_NET_BASE" in stderr
    assert calls == [], calls

    exit_code, _, stderr, calls, _ = _compare(
        "user-unbound", ["10.0.0.1"], {}, succeed_on={"*": 1}, exact_stderr=False
    )
    assert exit_code == 1, (
        "HAZARD 1: with neither SSH_USER nor USER exported the subject dies "
        "before printing anything of its own"
    )
    assert "USER" in stderr
    assert calls == [], calls


def test_user_env_is_the_fallback() -> None:
    """`${SSH_USER:-$USER}`: SSH_USER wins, USER is the fallback, and an EMPTY
    SSH_USER falls through rather than logging in as nobody."""
    _, _, _, calls, _ = _compare(
        "user-fallback", ["10.0.0.1"], {"USER": "envuser"}, succeed_on={"*": 1}
    )
    assert "envuser@10.0.0.1" in calls[0]
    _, _, _, calls, _ = _compare(
        "ssh-user-wins",
        ["10.0.0.1"],
        {"USER": "envuser", "SSH_USER": "chosen"},
        succeed_on={"*": 1},
    )
    assert "chosen@10.0.0.1" in calls[0]
    _, _, _, calls, _ = _compare(
        "ssh-user-empty",
        ["10.0.0.1"],
        {"USER": "envuser", "SSH_USER": ""},
        succeed_on={"*": 1},
    )
    assert "envuser@10.0.0.1" in calls[0]


def test_ssh_stderr_is_discarded() -> None:
    """`2>/dev/null` on the probe: ssh's own chatter must NOT reach the caller,
    unlike `verify-ssh.sh`, which lets it through. The two twins disagree here
    on purpose and both ports must keep their own side of it."""
    _, _, stderr, _, _ = _compare(
        "ssh-stderr-dropped",
        ["10.0.0.1"],
        USER,
        succeed_on={"*": 0},
        ssh_stderr="ssh: connect to host 10.0.0.1 port 22: Connection refused\n",
    )
    assert "Connection refused" not in stderr


def test_pure_helpers_are_exercised_directly() -> None:
    assert w.default_targets("192.168.111") == ["192.168.111.1", "192.168.111.11"]
    assert w.ATTEMPTS == 36
    assert w.BUDGET_LABEL == "180s"
    # The label and the loop must agree: 36 x 5 = 180.
    assert "%ds" % (w.ATTEMPTS * int(w.RETRY_SLEEP)) == w.BUDGET_LABEL

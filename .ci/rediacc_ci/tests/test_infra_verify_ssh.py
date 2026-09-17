"""Differential: `rediacc_ci.infra.verify_ssh` against its twin
`.ci/scripts/infra/verify-ssh.sh`.

SSH IS MOCKED, NOT REQUIRED. The subject's whole job is a retry loop around a
network call, so the interesting behaviour is entirely in HOW it calls ssh and
how many times: a differential that needed a reachable host would be skipped on
every developer machine and would then be no differential at all. The seam is
PATH. A recording stub `ssh` on a scratch PATH lets every case assert the ARGV
SEQUENCE both implementations produced, which is the half a stdout comparison
cannot see -- a port that printed "SSH connection successful" without ever
running ssh would pass a stdout-only check.

`sleep` IS STUBBED FOR THE SAME REASON AND IT IS WHY THIS FILE IS FAST. The
twin waits 5 real seconds between passes and so does the port, because the port
EXECS `sleep` rather than calling `time.sleep` (see the port's docstring). One
stub therefore serves both sides identically, an exhaustion case costs
milliseconds instead of a minute, and -- the part that matters -- the stub's
own log records every sleep, so the comparison can assert the two
implementations slept the same number of times. A `time.sleep` port would have
left the bash side stubbed and the Python side sleeping for real, which is two
differently-timed programs being called equivalent.

`whoami`, `sudo`, `cut` AND `nproc` ARE STUBBED TOO, so the login name, the
chown and the diagnostics are deterministic rather than dependent on who ran
the suite.

THREE OUTCOMES ARE DRIVEN, as the box requires: immediate success, success
after N retries, and exhausted retries. Each is compared on exit code, stdout,
stderr and the full argv log.

TWO REFUSALS DIVERGE IN TEXT AND ARE COMPARED BY SHAPE, both named in the
port's docstring: `${SSH_KEY:?...}` is a bash diagnostic carrying the twin's
path and LINE NUMBER, and the usage line interpolates `$0`, which cannot be the
same string for a `.sh` and a `.py`. Exit code, stream and ordering are
compared exactly in both cases.

K=5 LEDGER: `.ci/shadow/w7p6-verify-ssh.observations.jsonl`, recorded against a
disposable scratch git repository built outside this checkout, since
`shadow-gate.ts --record` refuses a dirty tree and this checkout never is.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.infra import verify_ssh as vs

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "verify-ssh.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "verify_ssh.py"

# ABSOLUTE INTERPRETERS, resolved once from the SUITE's environment. Every case below hands the subject a PATH holding nothing but the stub directory, so `bash`, `python3` and even the stubs' own `#!/usr/bin/env python3` would be unresolvable if any of them went through PATH.
BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

BASE_ENV = {
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

# The recording stub. Written as Python (new instruments are Python, not bash) and generated per case so its configuration lives in its OWN text rather than in an environment two processes deep.
#
# The counter file is what makes "succeeds on the Nth call" expressible: ssh is a fresh process every attempt, so the attempt number cannot live in a variable. It is per-CASE and per-SIDE, so the two implementations each get their own count and neither can consume the other's budget.
FAKE_SSH = """#!%(python)s
import os, sys, time
LOG = %(log)r
COUNTER = %(counter)r
SUCCEED_ON = %(succeed_on)d
OUT = %(out)r
ERR = %(err)r
DELAY = %(delay)f
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("ssh\\t" + "\\t".join(sys.argv[1:]) + "\\n")
n = 0
if os.path.exists(COUNTER):
    n = int(open(COUNTER).read() or "0")
n += 1
open(COUNTER, "w").write(str(n))
if DELAY:
    time.sleep(DELAY)
if OUT:
    sys.stdout.write(OUT)
if ERR:
    sys.stderr.write(ERR)
# 255 is ssh's own "could not connect", not a made-up number.
sys.exit(0 if SUCCEED_ON and n >= SUCCEED_ON else 255)
"""

# Every other external program the subject reaches for. Each records its argv into the same log, so the comparison sees the whole call SEQUENCE in order, not just the ssh calls.
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


# The real programs a subject may still reach for, symlinked into a second scratch directory. PATH is then exactly `<stubs>:<allowed real tools>` and nothing else, so "not on PATH" means it, and a tool nobody listed cannot quietly appear.
#
# `dirname` is on the list because the TWIN needs it before it does anything
# else: `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` is line 29,
# and with a stubs-only PATH the twin died there with `dirname: command not found` while the port ran perfectly -- which the comparison correctly reported as a divergence, and which was the test's fault rather than the port's.
#
# `ssh` and `ssh-keyscan` are DELIBERATELY ABSENT: they are the two the stubs own, and a symlink to a real one here would defeat every case in this file.
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
    succeed_on: int,
    ssh_stdout: str = "SSH OK\n",
    ssh_stderr: str = "",
    delay: float = 0.0,
    sudo_rc: int = 0,
    with_ssh: bool = True,
) -> pathlib.Path:
    """A scratch bin directory holding the stubs, returned for prepending."""
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
                "delay": delay,
            },
            encoding="utf-8",
        )
        ssh.chmod(0o755)
    for name, out, rc in (
        ("sleep", "", 0),
        ("whoami", "fixtureuser\n", 0),
        ("sudo", "", sudo_rc),
        # Deterministic diagnostics: the real ones report live kernel data, and two runs a second apart can legitimately differ.
        ("cut", "0.10 0.20 0.30\n", 0),
        ("nproc", "8\n", 0),
    ):
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
    succeed_on: int,
    with_ssh: bool = True,
    **stub: object,
) -> tuple[int, str, str, list[str]]:
    log = workdir / "calls.log"
    log.write_text("", encoding="utf-8")
    counter = workdir / "counter"
    binder = _bin(workdir / "bin", log, counter, succeed_on=succeed_on, with_ssh=with_ssh, **stub)
    env = dict(BASE_ENV)
    env.update(env_extra)
    # PATH IS REPLACED, NOT PREPENDED, and the difference is not pedantry. The
    # first version of this file prepended, and `with_ssh=False` -- the case
    # that is supposed to prove `require_cmd ssh` fires -- silently fell through to the machine's REAL ssh and tried to resolve a hostname on the network. Both sides agreed, so the comparison stayed green while the case tested nothing it claimed to. A replaced PATH cannot do that.
    env["PATH"] = "%s:%s" % (binder, _sysbin(workdir / "sysbin"))
    resolved = shutil.which("ssh", path=env["PATH"])
    if with_ssh:
        assert resolved == str(binder / "ssh"), (
            "the stub ssh is not what PATH resolves; this file would be probing real hosts"
        )
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
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


def _compare(
    name: str,
    argv: list[str],
    env_extra: dict[str, str] | None = None,
    *,
    succeed_on: int = 1,
    exact_stderr: bool = True,
    **stub: object,
) -> tuple[int, str, str, list[str]]:
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
                    succeed_on=succeed_on,
                    **stub,
                )
            )
        old, new = results
    assert new[0] == old[0], "%s: exit diverged %r vs %r\n twin stderr: %s\n port stderr: %s" % (
        name,
        old[0],
        new[0],
        old[2],
        new[2],
    )
    assert new[1] == old[1], "%s: stdout diverged:\n%r\n%r" % (name, old[1], new[1])
    if exact_stderr:
        assert new[2] == old[2], "%s: stderr diverged:\n--- twin ---\n%s\n--- port ---\n%s" % (
            name,
            old[2],
            new[2],
        )
    assert new[3] == old[3], "%s: the call SEQUENCE diverged:\n twin: %s\n port: %s" % (
        name,
        old[3],
        new[3],
    )
    return old


KEY = {"SSH_KEY": "/fixture/id_rsa"}


def test_immediate_success() -> None:
    """Outcome 1 of 3: the first probe answers."""
    exit_code, stdout, stderr, calls = _compare("immediate", ["host-a"], KEY, succeed_on=1)
    assert exit_code == 0
    assert stdout == "SSH OK\n", "ssh's own stdout must reach the caller unredirected"
    assert "SSH connection successful via host-a on attempt 1" in stderr
    assert [c.split("\t")[0] for c in calls] == ["whoami", "ssh"], calls
    assert "sleep" not in stderr, "a run that succeeded on the first probe must not sleep"
    assert not any(c.startswith("sleep") for c in calls), (
        "a run that succeeded on the first probe must not exec sleep"
    )


def test_success_after_retries() -> None:
    """Outcome 2 of 3: the third probe answers, with two full passes first."""
    exit_code, _, stderr, calls = _compare(
        "eventual", ["host-a"], {**KEY, "ATTEMPTS": "5"}, succeed_on=3
    )
    assert exit_code == 0
    assert "on attempt 3" in stderr
    verbs = [c.split("\t")[0] for c in calls]
    assert verbs == ["whoami", "ssh", "sleep", "ssh", "sleep", "ssh"], verbs


def test_exhausted_retries() -> None:
    """Outcome 3 of 3, and THE DEFECT THIS PORT PRESERVES.

    `succeed_on=0` means the stub never answers. Note the trailing `sleep` in
    the expected sequence: the twin prints "retrying in 5s..." and sleeps AFTER
    the final attempt, when there is nothing left to retry. The port reproduces
    it; this assertion is what pins the defect so a future cutover cannot fix
    one side and quietly diverge from the other.
    """
    exit_code, _, stderr, calls = _compare(
        "exhausted", ["host-a"], {**KEY, "ATTEMPTS": "2"}, succeed_on=0
    )
    assert exit_code == 1
    assert "SSH connection failed for all targets after 2 attempts" in stderr
    verbs = [c.split("\t")[0] for c in calls]
    assert verbs == ["whoami", "ssh", "sleep", "ssh", "sleep"], verbs
    assert stderr.count("retrying in 5s") == 2, (
        "the twin's final pass announces a retry that never happens; if this is "
        "ever fixed, both files must change together"
    )


def test_any_target_is_enough() -> None:
    """The quantifier: the loop is over attempts, and within one attempt over
    every target, and the FIRST target to answer ends the run."""
    exit_code, _, stderr, calls = _compare(
        "second-target-answers",
        ["host-a", "host-b"],
        {**KEY, "ATTEMPTS": "3"},
        succeed_on=2,
    )
    assert exit_code == 0
    assert "via host-b on attempt 1" in stderr
    assert [c.split("\t")[0] for c in calls] == ["whoami", "ssh", "ssh"], calls


def test_target_parsing() -> None:
    """`host`, `host:port`, and the `a:b:c` shape the twin's two substitutions
    genuinely produce (first colon for the host, LAST for the port)."""
    for name, target, want_host, want_port in (
        ("bare", "host-a", "fixtureuser@host-a", "22"),
        ("host-port", "localhost:2201", "fixtureuser@localhost", "2201"),
        ("three-parts", "a:b:c", "fixtureuser@a", "c"),
        ("empty-both", ":", "fixtureuser@", ""),
    ):
        _, _, _, calls = _compare("target-%s" % name, [target], KEY, succeed_on=1)
        fields = calls[-1].split("\t")
        assert fields[fields.index("-p") + 1] == want_port, (name, calls)
        assert want_host in fields, (name, calls)


def test_ssh_user_and_chown() -> None:
    """SSH_USER replaces `whoami` for the login name; CHOWN_PATH adds a
    `sudo chown -R` that still resolves the name through `whoami`."""
    _, _, _, calls = _compare("ssh-user", ["h"], {**KEY, "SSH_USER": "someone"}, succeed_on=1)
    assert [c.split("\t")[0] for c in calls] == ["ssh"], "whoami must not run when SSH_USER is set"
    assert "someone@h" in calls[0]

    _, _, _, calls = _compare(
        "chown", ["h"], {**KEY, "SSH_USER": "someone", "CHOWN_PATH": "/fixture/keys"}, succeed_on=1
    )
    assert calls[0] == "whoami\t", calls
    assert calls[1] == "sudo\tchown\t-R\tfixtureuser\t/fixture/keys", calls


def test_chown_failure_aborts() -> None:
    """`set -e` on a failing `sudo chown`: the run stops with sudo's status and
    never reaches ssh."""
    exit_code, _, _, calls = _compare(
        "chown-fails",
        ["h"],
        {**KEY, "SSH_USER": "someone", "CHOWN_PATH": "/fixture/keys"},
        succeed_on=1,
        sudo_rc=3,
    )
    assert exit_code == 3
    assert not any(c.startswith("ssh") for c in calls), calls


def test_ssh_streams_pass_through() -> None:
    """The twin redirects NEITHER of ssh's streams, so a banner on stderr and
    the command's output on stdout both reach the caller."""
    _, stdout, stderr, _ = _compare(
        "streams",
        ["h"],
        {**KEY, "ATTEMPTS": "1"},
        succeed_on=0,
        ssh_stdout="partial output\n",
        ssh_stderr="ssh: connect to host h port 22: Connection refused\n",
    )
    assert "partial output" in stdout
    assert "Connection refused" in stderr


def test_attempts_zero_makes_no_probe() -> None:
    """ATTEMPTS=0: the loop body never runs, so the script fails without ever
    calling ssh. A port that used `range(1, max(1, n))` would probe once."""
    exit_code, _, stderr, calls = _compare(
        "attempts-zero", ["h"], {**KEY, "ATTEMPTS": "0"}, succeed_on=1
    )
    assert exit_code == 1
    assert "after 0 attempts" in stderr
    assert not any(c.startswith("ssh") for c in calls), calls


def test_missing_ssh_binary() -> None:
    """`require_cmd ssh`, byte-identical on both sides."""
    exit_code, _, stderr, calls = _compare("no-ssh", ["h"], KEY, succeed_on=1, with_ssh=False)
    assert exit_code == 1
    assert "Required command 'ssh' is not available" in stderr
    assert calls == [], calls


def test_refusals_that_diverge_only_in_text() -> None:
    """The two bash-diagnostic refusals. Exit code, stream and call sequence
    are compared exactly; the text is compared by shape, for the reasons in the
    module docstring."""
    exit_code, stdout, stderr, calls = _compare(
        "no-key", ["h"], {}, succeed_on=1, exact_stderr=False
    )
    assert exit_code == 1
    assert stdout == ""
    assert "SSH_KEY" in stderr
    assert "is required" in stderr
    assert calls == [], "nothing may run before the key check"

    exit_code, _, stderr, calls = _compare("no-targets", [], KEY, succeed_on=1, exact_stderr=False)
    assert exit_code == 1
    assert "<host[:port]> ..." in stderr
    assert calls == [], calls

    exit_code, _, stderr, calls = _compare(
        "attempts-junk", ["h"], {**KEY, "ATTEMPTS": "abc"}, succeed_on=1, exact_stderr=False
    )
    assert exit_code == 1
    # `whoami` HAS run by this point on both sides: bash does not evaluate ATTEMPTS arithmetically until the loop header, which is after the USER_NAME assignment. That ordering is asserted here rather than assumed.
    assert [c.split("\t")[0] for c in calls] == ["whoami"], calls


def test_pure_helpers_are_exercised_directly() -> None:
    assert vs.split_target("host") == ("host", "22")
    assert vs.split_target("host:2201") == ("host", "2201")
    assert vs.split_target("a:b:c") == ("a", "c")
    assert vs.parse_attempts("15") == 15
    assert vs.parse_attempts("0") == 0
    assert vs.parse_attempts("-2") == -2
    assert vs.parse_attempts("0x10") == 16
    assert vs.parse_attempts("010") == 8
    # BOTH DIRECTIONS: junk must be rejected, not coerced to a default. A port that fell back to 15 here would probe a host fifteen times where the twin refuses outright.
    assert vs.parse_attempts("abc") is None
    assert vs.parse_attempts("3x") is None
    assert vs.parse_attempts("") is None

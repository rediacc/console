"""`rediacc_ci.infra.verify_ssh`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/infra/verify-ssh.sh` and the port over one stubbed PATH and compared four things per case: exit code, stdout, stderr and the call SEQUENCE.

The K=5 ledger `.ci/shadow/w7p6-verify-ssh.observations.jsonl` recorded that comparison over five distinct trees, against a disposable scratch git repository outside this checkout, since `shadow-gate.ts --record` refuses a dirty tree and this checkout never is.

Every case now compares against `goldens/verify-ssh/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

FOUR CHANNELS, NOT FIVE, AND THE MISSING ONE IS THE POINT OF THE SUBJECT. The sibling recording `goldens/wait-for-vm-ssh/` carries a `--- known hosts ---` section because that subject LEARNS host keys and appending them is its durable side effect.

This one refuses to learn them: `StrictHostKeyChecking=no` with `UserKnownHostsFile=/dev/null` is deliberate, because these are ephemeral CI VMs whose keys are regenerated on every provision and pinning them would fail on the second run.

There is no durable artifact to freeze, and a section recording an empty `$HOME` every time would be decoration rather than evidence, so the policy is asserted where it is visible: in the recorded ssh argv under `--- calls ---`.

WHERE THIS SUBJECT DIFFERS FROM ITS SIBLING, each difference driven by its own case here rather than inherited from that file: an identity is REQUIRED and passed as `-i "$SSH_KEY"`, and a missing one is a refusal before any probe; a target may carry a port, split with the twin's own two substitutions (first colon for the host, LAST for the port, so `a:b:c` is host `a` port `c`);
the budget is the env-tunable `ATTEMPTS`, default 15, and a non-numeric value is refused in the loop header rather than before the chown above it; ANY one target answering ends the run, so a second target that answers on the first pass is a success rather than a partial one; and ssh's own stderr is NOT redirected, so a banner or a connection refusal reaches the caller.

THE SEAM IS PATH, and it REPLACES rather than prepends. A recording stub `ssh` lets every case assert the argv sequence, which is the half a stdout comparison cannot see: a port that printed "SSH connection successful" without ever running ssh would pass a stream-only check. The first version of the differential prepended instead, and the `no-ssh-on-path` case fell through to the
machine's REAL ssh and tried to resolve a hostname on the network while both sides agreed and the comparison stayed green.

`sleep` IS STUBBED FOR THE SAME REASON AND IT IS WHY THIS FILE IS FAST. The twin waits 5 real seconds between passes and so did the port, because the port EXECS `sleep` rather than calling `time.sleep`, so one stub served both sides identically and the stub's log records every sleep. A `time.sleep` port would have left the bash side stubbed and the Python side sleeping for real,
which is two differently-timed programs being called equivalent. `whoami`, `sudo`, `cut` and `nproc` are stubbed too, so the login name, the chown and the diagnostics are deterministic rather than dependent on who ran the suite.

WHAT IS MASKED, and it is three paths. The run directory and the per-run `$HOME` are rebuilt under a different tempdir name every run, so they become `<work>` and `<home>`. The checkout root becomes `<repo>`, because all three divergent refusals below are bash diagnostics or `$0` interpolations carrying the subject's own absolute path, and a golden naming this worktree would be
unreadable from any other. Nothing else is touched.

THREE REFUSALS DIVERGE IN TEXT AND ARE COMPARED BY SHAPE, exactly as they were while both copies existed, and all three are named in the port's docstring: `${SSH_KEY:?...}` is a bash diagnostic carrying the twin's path and LINE NUMBER, the usage line interpolates `$0` and the two files cannot have the same name, and a non-integer `ATTEMPTS` is a bash ARITHMETIC error.

Exit code, stdout and the call sequence are compared exactly in all three, and the twin's recorded wording stays in the golden as the evidence of what it said.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import verify_ssh as vs
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "verify_ssh.py"
SLUG = "verify-ssh"

# ABSOLUTE INTERPRETERS, resolved once from the SUITE's environment. Every case hands the subject a PATH holding nothing but the stub directory and a curated set of real tools, so `bash`, `python3` and even the stubs' own shebang would be unresolvable if any of them went through PATH.
BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

CALLS_MARKER = "--- calls ---\n"

BASE_ENV = {
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

# The recording stub. Written as Python and generated per case so its configuration lives in its OWN text rather than in an environment two processes deep.
#
# The counter file is what makes "succeeds on the Nth call" expressible: ssh is a fresh process every attempt, so the attempt number cannot live in a variable.
FAKE_SSH = """#!%(python)s
import os, sys
LOG = %(log)r
COUNTER = %(counter)r
SUCCEED_ON = %(succeed_on)d
OUT = %(out)r
ERR = %(err)r
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("ssh\\t" + "\\t".join(sys.argv[1:]) + "\\n")
n = 0
if os.path.exists(COUNTER):
    n = int(open(COUNTER).read() or "0")
n += 1
open(COUNTER, "w").write(str(n))
if OUT:
    sys.stdout.write(OUT)
if ERR:
    sys.stderr.write(ERR)
# 255 is ssh's own "could not connect", not a made-up number.
sys.exit(0 if SUCCEED_ON and n >= SUCCEED_ON else 255)
"""

# Every other external program the subject reaches for. Each records its argv into the same log, so the comparison sees the whole call SEQUENCE in order.
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

# The real programs a subject may still reach for, symlinked into a second scratch directory. PATH is then exactly `<stubs>:<allowed real tools>` and nothing else, so "not on PATH" means it.
#
# `dirname` is on the list because the TWIN needed it before it did anything else: `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` was line 29, and with a stubs-only PATH the twin died there with `dirname: command not found` while the port ran perfectly, which the comparison correctly reported as a divergence and which was the test's fault rather than the port's.
#
# `ssh` is DELIBERATELY ABSENT: it is the one the stubs own, and a symlink to a real one here would defeat every case in this file.
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

KEY = {"SSH_KEY": "/fixture/id_rsa"}

# name -> argv, environment, which attempt ssh answers on, and the stub wiring
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "an-immediate-success": {"argv": ["host-a"], "env": KEY, "succeed_on": 1},
    "a-success-after-retries": {
        "argv": ["host-a"],
        "env": {**KEY, "ATTEMPTS": "5"},
        "succeed_on": 3,
    },
    "an-exhausted-budget": {
        "argv": ["host-a"],
        "env": {**KEY, "ATTEMPTS": "2"},
        "succeed_on": 0,
    },
    "any-target-is-enough": {
        "argv": ["host-a", "host-b"],
        "env": {**KEY, "ATTEMPTS": "3"},
        "succeed_on": 2,
    },
    "a-host-and-port-target": {"argv": ["localhost:2201"], "env": KEY, "succeed_on": 1},
    "a-three-part-target": {"argv": ["a:b:c"], "env": KEY, "succeed_on": 1},
    "an-empty-target": {"argv": [":"], "env": KEY, "succeed_on": 1},
    "ssh-user-replaces-whoami": {
        "argv": ["h"],
        "env": {**KEY, "SSH_USER": "someone"},
        "succeed_on": 1,
    },
    "a-chown-path": {
        "argv": ["h"],
        "env": {**KEY, "SSH_USER": "someone", "CHOWN_PATH": "/fixture/keys"},
        "succeed_on": 1,
    },
    "a-failing-chown": {
        "argv": ["h"],
        "env": {**KEY, "SSH_USER": "someone", "CHOWN_PATH": "/fixture/keys"},
        "succeed_on": 1,
        "stub": {"sudo_rc": 3},
    },
    "ssh-streams-pass-through": {
        "argv": ["h"],
        "env": {**KEY, "ATTEMPTS": "1"},
        "succeed_on": 0,
        "stub": {
            "ssh_stdout": "partial output\n",
            "ssh_stderr": "ssh: connect to host h port 22: Connection refused\n",
        },
    },
    "zero-attempts": {"argv": ["h"], "env": {**KEY, "ATTEMPTS": "0"}, "succeed_on": 1},
    "no-ssh-on-path": {
        "argv": ["h"],
        "env": KEY,
        "succeed_on": 1,
        "stub": {"with_ssh": False},
    },
    "a-missing-ssh-key": {"argv": ["h"], "env": {}, "succeed_on": 1},
    "no-targets": {"argv": [], "env": KEY, "succeed_on": 1},
    "a-non-numeric-attempts": {
        "argv": ["h"],
        "env": {**KEY, "ATTEMPTS": "abc"},
        "succeed_on": 1,
    },
}

CASES = tuple(CASE_KW)

# The three refusals whose text is a bash diagnostic or a `$0` interpolation. Compared by shape, in their own tests.
DIVERGENT = ("a-missing-ssh-key", "no-targets", "a-non-numeric-attempts")


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
    succeed_on: int,
    ssh_stdout: str = "SSH OK\n",
    ssh_stderr: str = "",
    sudo_rc: int = 0,
    with_ssh: bool = True,
) -> pathlib.Path:
    """A scratch bin directory holding the stubs, returned for the front of PATH."""
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


def run(subject: pathlib.Path, workdir: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once, over this case's own scratch PATH and HOME."""
    kw = CASE_KW[name]
    stub = dict(kw.get("stub") or {})
    workdir.mkdir(parents=True, exist_ok=True)
    log = workdir / "calls.log"
    log.write_text("", encoding="utf-8")
    home = workdir / "home"
    home.mkdir(parents=True, exist_ok=True)
    binder = stubs(workdir / "bin", log, workdir / "counter", succeed_on=kw["succeed_on"], **stub)
    env = dict(BASE_ENV)
    env["HOME"] = str(home)
    env.update(kw["env"])
    env["PATH"] = "%s:%s" % (binder, sysbin(workdir / "sysbin"))
    resolved = shutil.which("ssh", path=env["PATH"])
    if stub.get("with_ssh", True):
        assert resolved == str(binder / "ssh"), (
            "the stub ssh is not what PATH resolves; this file would be probing real hosts"
        )
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
        timeout=120,
    )

    def mask(text: str) -> str:
        return (
            text.replace(str(workdir), "<work>")
            .replace(str(home), "<home>")
            .replace(str(ROOT), "<repo>")
        )

    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(log.read_text(encoding="utf-8")),
    )


def render(code: int, stdout: str, stderr: str, calls: str) -> str:
    return "%s%s%s" % (frozen.render(code, stdout, stderr), CALLS_MARKER, calls)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    return run(PORT, tmp_path / name, name)


def verbs(calls: str) -> list[str]:
    return [line.split("\t")[0] for line in calls.splitlines() if line]


def fields(calls: str, index: int = -1) -> list[str]:
    """One recorded call's argv, split back into fields. The last call by default."""
    lines = [line for line in calls.splitlines() if line]
    return lines[index].split("\t")


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the call SEQUENCE")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


def compare_by_shape(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """Everything but the wording of the refusal, for the three bash diagnostics."""
    want = recorded(name)
    got = port(tmp_path, name)
    for index, label in ((0, "exit code"), (1, "stdout"), (3, "the call SEQUENCE")):
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
    """Outcome 1 of 3: the first probe answers, and nothing sleeps."""
    code, stdout, stderr, calls = recorded("an-immediate-success")
    assert code == 0
    assert stdout == "SSH OK\n", "ssh's own stdout must reach the caller unredirected"
    assert "SSH connection successful via host-a on attempt 1" in stderr
    assert verbs(calls) == ["whoami", "ssh"], calls
    assert "sleep" not in stderr, "a run that succeeded on the first probe must not sleep"
    assert "sleep" not in verbs(calls), (
        "a run that succeeded on the first probe must not exec sleep"
    )


def test_success_after_retries() -> None:
    """Outcome 2 of 3: the third probe answers, with two full passes first."""
    code, _, stderr, calls = recorded("a-success-after-retries")
    assert code == 0
    assert "on attempt 3" in stderr
    assert verbs(calls) == ["whoami", "ssh", "sleep", "ssh", "sleep", "ssh"], calls


def test_exhausted_retries() -> None:
    """Outcome 3 of 3, and THE DEFECT THIS RECORDING PINS.

    Note the trailing `sleep` in the recorded sequence: the twin printed "retrying in 5s..." and slept AFTER the final attempt, when there was nothing left to retry. The port reproduces it, and this assertion is what stops a future cutover fixing one side and quietly diverging from the other.
    """
    code, _, stderr, calls = recorded("an-exhausted-budget")
    assert code == 1
    assert "SSH connection failed for all targets after 2 attempts" in stderr
    assert verbs(calls) == ["whoami", "ssh", "sleep", "ssh", "sleep"], calls
    assert stderr.count("retrying in 5s") == 2, (
        "the twin's final pass announced a retry that never happened; if this is "
        "ever fixed, both files must change together"
    )


def test_any_target_is_enough() -> None:
    """THE QUANTIFIER, and the difference from `wait-for-vm-ssh`: the loop is over attempts and, within one attempt, over every target, and the FIRST target to answer ends the run with a zero exit. The sibling demands that EVERY target answer."""
    code, _, stderr, calls = recorded("any-target-is-enough")
    assert code == 0
    assert "via host-b on attempt 1" in stderr
    assert verbs(calls) == ["whoami", "ssh", "ssh"], calls


def test_host_key_checking_is_refused_in_the_argv() -> None:
    """THE HOST-KEY POLICY, asserted where it is visible.

    These are ephemeral CI VMs whose keys change on every provision, so the twin pinned nothing and wrote nothing: `StrictHostKeyChecking=no` with `UserKnownHostsFile=/dev/null`, on every probe. A port that hardened this, or that borrowed the sibling's `accept-new`, would break every caller on provision two, and the recorded argv is the only channel that would notice.
    """
    argv = fields(recorded("an-immediate-success")[3])
    assert argv[:2] == ["ssh", "-i"]
    assert argv[2] == "/fixture/id_rsa", "the identity is REQUIRED here, unlike the sibling"
    assert "StrictHostKeyChecking=no" in argv
    assert "UserKnownHostsFile=/dev/null" in argv
    assert "ConnectTimeout=5" in argv
    assert argv[-1] == "echo 'SSH OK'"


def test_target_parsing() -> None:
    """`host`, `host:port`, and the `a:b:c` shape the twin's two substitutions genuinely produced: FIRST colon for the host, LAST for the port. Not a sensible parse, and recorded rather than corrected."""
    for name, want_host, want_port in (
        ("an-immediate-success", "fixtureuser@host-a", "22"),
        ("a-host-and-port-target", "fixtureuser@localhost", "2201"),
        ("a-three-part-target", "fixtureuser@a", "c"),
        ("an-empty-target", "fixtureuser@", ""),
    ):
        argv = fields(recorded(name)[3])
        assert argv[argv.index("-p") + 1] == want_port, (name, argv)
        assert want_host in argv, (name, argv)


def test_ssh_user_and_chown() -> None:
    """SSH_USER replaces `whoami` for the login name; CHOWN_PATH adds a `sudo chown -R` that still resolves the name through `whoami`."""
    calls = recorded("ssh-user-replaces-whoami")[3]
    assert verbs(calls) == ["ssh"], "whoami must not run when SSH_USER is set"
    assert "someone@h" in fields(calls)

    calls = recorded("a-chown-path")[3]
    lines = [line for line in calls.splitlines() if line]
    assert lines[0] == "whoami\t", lines
    assert lines[1] == "sudo\tchown\t-R\tfixtureuser\t/fixture/keys", lines


def test_chown_failure_aborts() -> None:
    """`set -e` on a failing `sudo chown`: the run stopped with sudo's status and never reached ssh."""
    code, _, _, calls = recorded("a-failing-chown")
    assert code == 3
    assert "ssh" not in verbs(calls), calls


def test_ssh_streams_pass_through() -> None:
    """NEITHER of ssh's streams is redirected, so a banner on stderr and the command's output on stdout both reach the caller. The sibling sends ssh's stderr to /dev/null; the two twins disagreed here on purpose and each port keeps its own side of it."""
    _, stdout, stderr, _ = recorded("ssh-streams-pass-through")
    assert "partial output" in stdout
    assert "Connection refused" in stderr


def test_attempts_zero_makes_no_probe() -> None:
    """ATTEMPTS=0: the loop body never ran, so the script failed without ever calling ssh. A port that used `range(1, max(1, n))` would probe once."""
    code, _, stderr, calls = recorded("zero-attempts")
    assert code == 1
    assert "after 0 attempts" in stderr
    assert "ssh" not in verbs(calls), calls


def test_missing_ssh_binary() -> None:
    """`require_cmd ssh`, byte-identical on both sides, and FIRST: a caller with no ssh, no key and no arguments is told about ssh."""
    code, _, stderr, calls = recorded("no-ssh-on-path")
    assert code == 1
    assert "Required command 'ssh' is not available" in stderr
    assert verbs(calls) == [], calls


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
    assert vs.DEFAULT_ATTEMPTS == 15
    assert vs.RETRY_SLEEP == "5"


# --------------------------------------------------------------------------- The three divergences, pinned rather than papered over ---------------------------------------------------------------------------


def test_divergence_a_missing_ssh_key(tmp_path: pathlib.Path) -> None:
    """`${SSH_KEY:?SSH_KEY is required}` is a bash diagnostic carrying the twin's path and line number. Everything a caller can act on is compared, and the port must still name the variable on the same stream, after the ssh check and before anything else runs."""
    code, stdout, stderr, calls = compare_by_shape(tmp_path, "a-missing-ssh-key")
    assert code == 1
    assert stdout == ""
    assert "SSH_KEY" in stderr
    assert "is required" in stderr
    assert "SSH_KEY is required" in recorded("a-missing-ssh-key")[2]
    assert verbs(calls) == [], "nothing may run before the key check"


def test_divergence_no_targets(tmp_path: pathlib.Path) -> None:
    """The usage line interpolates `$0`, and a `.sh` and a `.py` cannot be the same string. The text is otherwise identical, and the recorded line still names the twin."""
    code, _, stderr, calls = compare_by_shape(tmp_path, "no-targets")
    assert code == 1
    assert "<host[:port]> ..." in stderr
    assert "verify-ssh.sh <host[:port]> ..." in recorded("no-targets")[2]
    assert verbs(calls) == [], calls


def test_divergence_a_non_numeric_attempts(tmp_path: pathlib.Path) -> None:
    """A non-integer `ATTEMPTS` is a bash ARITHMETIC error, refused in the loop header rather than at assignment.

    `whoami` HAS run by that point on both sides, because bash does not evaluate ATTEMPTS arithmetically until the `for ((...))` header, which is after the USER_NAME assignment. That ordering is asserted rather than assumed: a port that validated eagerly would skip work the twin performs.
    """
    code, _, _, calls = compare_by_shape(tmp_path, "a-non-numeric-attempts")
    assert code == 1
    assert verbs(calls) == ["whoami"], calls


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_change_to_the_host_key_policy_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `StrictHostKeyChecking=no` accepts an unknown host key without recording it; `accept-new` is the sibling's setting and LEARNS it, which is exactly the policy this subject must not have on a fleet whose keys are regenerated every provision. The stub answers the same bytes either way, so exit code, stdout and stderr are identical and only the `--- calls ---` section sees the
    change. The mutation runs from a throwaway copy of the module, and the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '                    "StrictHostKeyChecking=no",\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant_source = original.replace(
        anchor, '                    "StrictHostKeyChecking=accept-new",\n'
    )

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutant_source, encoding="utf-8")

    name = "an-immediate-success"
    planted = run(mutant, tmp_path / "planted", name)
    want = recorded(name)
    assert "StrictHostKeyChecking=no" in want[3], "the recorded corpus moved"
    assert planted[3] != want[3], "the plant did not change the call sequence"
    assert "StrictHostKeyChecking=accept-new" in planted[3]
    for index in (0, 1, 2):
        assert planted[index] == want[index], "the plant was supposed to be invisible here"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original

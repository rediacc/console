"""Differential: `.ci/rediacc_ci/private/concurrent_fork_isolation_test.py` against its twin `.ci/scripts/private/concurrent-fork-isolation-test.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that.

-----------------------------------------------------------------------------
NOTHING REAL IS EVER INVOKED, AND THE VM IS NOT THE OBSTACLE PEOPLE EXPECT
-----------------------------------------------------------------------------
The twin drives a worker VM: `rdc machine setup`, `rdc repo create/fork/up`, a CRIU checkpoint, and eight `ssh` payloads that read `ss`, `bpftool` and per-repository docker sockets. None of that runs here, and skipping it costs less than it looks like it should, because EVERY FACT THE SCRIPT ACTS ON ARRIVES AS A CHILD PROCESS'S STDOUT. The VM decides what those strings ARE; it
decides nothing about what the script DOES with them. So `ssh`, `rdc`, `sleep` and `whoami` are canned recording fakes, `cat`, `sort`, `head`, `tail`, `grep`, `tee` and `rm` are recording PASSTHROUGHS to the real tools (so a pipeline still behaves like a pipeline), and `mktemp` is a deterministic fake, because a random `tmp.XXXXXXXX` would put two different absolute paths into two
subjects' call logs and read as a divergence.

WHAT THIS DELIBERATELY DOES NOT PROVE: that a real `ss -Hltnp4` prints what the fixture prints, or that CRIU restores anything. Neither subject can prove that without hardware, and the twin exists to be run by hand against hardware.

-----------------------------------------------------------------------------
WHAT IS COMPARED, AND WHY THE CALL LOG IS THE MOST IMPORTANT OF THE FOUR
-----------------------------------------------------------------------------
Exit code, stdout, stderr, and the CALL LOG of every external, plus the exact bytes of the two sidecar files as the `rdc repo sync upload` fake received them. The call log carries what no stream can: that the compose file was written by a real `cat` through a real redirection rather than by `pathlib.write_text`, that `sort -u` and `head -1` are separate processes, that the
checkpoint fork is taken with `--tag cpchild --checkpoint` in that order, and that the wait loop sleeps thirty times.

-----------------------------------------------------------------------------
THE ONE NORMALISATION, AND THE EVIDENCE THAT IT IS NOT HIDING A DIVERGENCE
-----------------------------------------------------------------------------
THE RIGHT-HAND MEMBER OF A PIPELINE HAS NO POSITION IN THIS LOG. A shell forks both members before either reaches `exec`, so which one appends its line first is a scheduling outcome. Measured 2026-09-14 on the TWIN ALONE, one fixture, twelve consecutive runs: `grep` before `tail` seven times, `tail` before `grep` five times. Under a loaded machine (`pytest -n 8`) `head` was
observed drifting TWO slots, past a command that causally precedes its own pipeline. And `sort -u` is worse than merely racy: the twin runs it inside a PROCESS SUBSTITUTION (`done < <(printf ... | sort -u)`), which the shell never waits for at all, so its line may land arbitrarily late.

So the call log is split rather than reordered. `_split_drifting` removes every record produced by one of the FOUR right-hand tools -- `sort`, `head`, `tail`, `tee`, none of which this script invokes in any other position -- and returns them SORTED, as a multiset. The remaining forty-one records of a passing run keep their exact order and are compared as a sequence, which is the
whole of the phase ordering.

The LEFT-hand members (`ssh`, `rdc`, `grep`) stay in the ordered list on purpose: a shell waits for a pipeline before starting the next command, so a left member's line is bounded on both sides by the commands around the pipeline. Only its position relative to its own partner is free, and its partner is the thing that was removed.

`test_the_drift_split_removes_only_the_four_right_hand_tools` pins that the split is not a general sort, and the anti-vacuity test asserts the drifting multiset by count and argv so nothing is merely discarded.

-----------------------------------------------------------------------------
THE ONE KNOWN DIVERGENCE, ASSERTED RATHER THAN HIDDEN
-----------------------------------------------------------------------------
`common.sh` logs with `echo -e`, which INTERPRETS backslash escapes in the message; `rediacc_ci.log` formats the message as data. Nine of the twin's messages interpolate remote output, so a bind address containing `\\t` prints differently on the two sides. That is a pre-existing, deliberate ruling of this tree (`rediacc_ci/log.py`, "A SECOND DIVERGENCE, and this one is a bug being
dropped rather than a decision"), and `test_backslashes_in_remote_output_are_the_one_known_divergence` asserts BOTH sides of it so nobody "fixes" the Python to match a bug.

-----------------------------------------------------------------------------
THE ONE MASK
-----------------------------------------------------------------------------
Bash prefixes its own diagnostics with `<$0>: line <n>: `, naming the file it is running; the port composes the same prefix from `sys.argv[0]` and its own live frame. Those can never be equal, so `_mask` collapses exactly that prefix on both sides. `test_the_mask_does_not_hide_the_message` pins it.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.core import bash_dialect
from rediacc_ci.private import concurrent_fork_isolation_test as port

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "concurrent-fork-isolation-test.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "concurrent_fork_isolation_test.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/concurrent-fork-isolation-test.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/concurrent_fork_isolation_test.py")

# The four tools whose real behaviour needs hardware or a network. Each returns canned bytes chosen by the FIRST rule whose `match` is a substring of its NUL-joined argv, and each rule's `responses` are consumed in order with the last one repeating, which is how the counter-wait loop is driven to a value.
CANNED_TOOLS = ("ssh", "rdc", "sleep", "whoami")

# The tools whose real behaviour is hermetic and IS wanted: a passthrough records the argv and then `execv`s the real binary, so `grep -q` still returns a real status and `tee` still writes a real file. Recording a fake here would make the pipeline arms untestable, and stubbing them would make the file contents unobservable.
PASSTHROUGH_TOOLS = ("cat", "sort", "head", "tail", "grep", "tee", "rm")

# Everything both subjects need once PATH is rebuilt from scratch. NAMED rather than derived, because a PATH built by copying "everything except the fakes" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject rather than a hole in the harness.
#
# `uname` IS DELIBERATELY REAL AND UNRECORDED. `common.sh:509` runs
# `CI_OS="$(detect_os)"` at source time, which is the library probing its host;
# the port does not source common.sh and so does not probe. A recording fake would turn that into a call-log divergence about something neither subject does on purpose, and a MISSING `uname` would put two `command not found` lines on the twin's stderr that the port has no way to produce.
NEEDED = ("bash", "sh", "python3", "uname", "env", "dirname", "ls", "cut")

FAKE_CANNED = """#!/usr/bin/env python3
import json, pathlib, sys
NAME = %(name)r
RULES = %(rules)r
with pathlib.Path(%(log)r).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join([NAME, *sys.argv[1:]]) + "\\n")
state_path = pathlib.Path(%(state)r)
state = json.loads(state_path.read_text()) if state_path.exists() else {}
joined = "\\x00".join(sys.argv[1:])
out, err, rc = "", "", 0
for index, rule in enumerate(RULES):
    if rule["match"] in joined:
        key = "%%s:%%d" %% (NAME, index)
        seen = state.get(key, 0)
        state[key] = seen + 1
        chosen = rule["responses"][min(seen, len(rule["responses"]) - 1)]
        out, err, rc = chosen.get("out", ""), chosen.get("err", ""), chosen.get("rc", 0)
        break
state_path.write_text(json.dumps(state))
sys.stdout.write(out)
sys.stdout.flush()
sys.stderr.write(err)
sys.stderr.flush()
%(extra)s
sys.exit(rc)
"""

# `rdc repo sync upload --local <dir>` is the ONLY moment the two sidecar files are observable: the twin `rm -rf`s the directory on the very next line. The fake snapshots them so the differential can compare the bytes that would have reached the VM, which is the whole point of writing them through `cat`.
RDC_UPLOAD_SNAPSHOT = """
if "upload" in sys.argv and "--local" in sys.argv:
    src = pathlib.Path(sys.argv[sys.argv.index("--local") + 1])
    seen_files = []
    for entry in sorted(src.rglob("*")):
        if entry.is_file():
            seen_files.append("%s\\n%s" % (entry.relative_to(src), entry.read_text()))
    pathlib.Path(UPLOAD).write_text("\\n----\\n".join(seen_files), encoding="utf-8")
"""

FAKE_PASSTHROUGH = """#!/usr/bin/env python3
import os, pathlib, sys
with pathlib.Path(%(log)r).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join([%(name)r, *sys.argv[1:]]) + "\\n")
os.execv(%(real)r, [%(name)r, *sys.argv[1:]])
"""

# `mktemp` and `mktemp -d`, made deterministic. A real one returns a fresh random path per call, and the twin then puts it into `rdc repo sync upload --local <path>` and `rm -rf <path>`; two subjects would record two different absolute paths and the differential would fail on the randomness. `%(missing)s` makes it print a path it did NOT create, which is the only way to reach the
# heredoc-redirection failure arm.
FAKE_MKTEMP = """#!/usr/bin/env python3
import pathlib, sys
with pathlib.Path(%(log)r).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join(["mktemp", *sys.argv[1:]]) + "\\n")
base = pathlib.Path(%(base)r)
target = base / ("mkt.d" if "-d" in sys.argv[1:] else "mkt.f")
if %(missing)r:
    target = base / "never-created" / "mkt"
elif "-d" in sys.argv[1:]:
    target.mkdir(parents=True, exist_ok=True)
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("")
print(target)
"""

# The rules every case starts from: a run in which all four assertions hold. The counter reaches 20 on the parent's SECOND reading (so the wait loop is exercised rather than short-circuited), the fork's restored counter is 25, and the parent's two post-fork readings advance 30 -> 40.
HEALTHY_RULES: dict[str, list[dict]] = {
    "ssh": [
        {"match": "ss -Hltnp4", "responses": [{"out": "127.0.1.1:5432\n127.0.2.1:5432\n"}]},
        {"match": "com.docker.compose.project", "responses": [{"out": "0\n"}]},
        # MATCHED ON `grep counter`, not `grep -q counter`: counter_sockets was converted to the `[ -n "$(... | grep ...)" ]` form on 2026-09-16 when `docker` joined SCALING_PRODUCERS. Still unique -- the only other remote
        # payload using grep is counter_value, whose pattern is `count=[0-9]*`.
        {
            "match": "grep counter",
            "responses": [
                {"out": "/var/run/rediacc/docker-aaa.sock\n"},
                {"out": "/var/run/rediacc/docker-aaa.sock\n/var/run/rediacc/docker-bbb.sock\n"},
            ],
        },
        {"match": "docker-bbb.sock", "responses": [{"out": "25\n"}]},
        {
            "match": "docker-aaa.sock",
            "responses": [{"out": "10\n"}, {"out": "20\n"}, {"out": "30\n"}, {"out": "40\n"}],
        },
    ],
    "rdc": [
        {
            "match": "--debug",
            "responses": [{"out": "up: starting\ncounter restored from checkpoint ok\ndone\n"}],
        }
    ],
    "whoami": [{"match": "", "responses": [{"out": "harness-user\n"}]}],
}

# The four right-hand pipeline members. In THIS script each of these tools is invoked in exactly one place and always as the receiving end of a pipe: printf ... | sort -u counter_sockets | head -1 grep -iE ... | tail -20 rdc repo up ... | tee "$log" See the module docstring: their position in the log is a scheduling outcome, so they are compared as a multiset instead of in
# sequence.
DRIFTING_TOOLS = ("sort", "head", "tail", "tee")

# A recorded call starts with one of these names followed by a TAB or a line end; anything else is a continuation line of a multi-line `ssh` payload.
RECORD_START = re.compile(
    r"^(%s)(\t|$)" % "|".join(sorted({*CANNED_TOOLS, *PASSTHROUGH_TOOLS, "mktemp"}))
)

SHELL_PREFIX = re.compile(r"^[^\n]*?: line \d+: ", re.MULTILINE)


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    text = SHELL_PREFIX.sub("<shell>: ", text)
    return text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")


def _records(raw: str) -> list[str]:
    """Split the call log into records. `ssh` payloads span many lines, so a naive `splitlines()` would shred five of the eight remote scripts."""
    records: list[str] = []
    current: str | None = None
    # ONE trailing newline is the last record's TERMINATOR, not part of it. Any newline INSIDE a record is kept, because `PROJECTS_CMD` genuinely ends
    # with one and the empty continuation line it leaves is real.
    raw = raw.removesuffix("\n")
    for line in raw.split("\n"):
        if RECORD_START.match(line):
            if current is not None:
                records.append(current)
            current = line
        elif current is not None:
            current = "%s\n%s" % (current, line)
    if current is not None:
        records.append(current)
    return records


def _split_drifting(records: list[str]) -> tuple[list[str], list[str]]:
    """Separate the ordered spine from the four unordered right-hand members.

    Deliberately NOT a global sort and NOT a whole-log multiset: the order of everything that is not concurrent is exactly what this differential exists to compare, and sorting it would throw away the phase ordering along with the race. The removed records are returned sorted so they can still be compared for presence and argv.
    """
    ordered = [r for r in records if r.split("\t")[0] not in DRIFTING_TOOLS]
    drifting = sorted(r for r in records if r.split("\t")[0] in DRIFTING_TOOLS)
    return ordered, drifting


def _fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because the twin sources `common.sh` through `$BASH_SOURCE/../lib` and would otherwise reach the tracked one, and because a subject run out of the real checkout could touch it.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)
    return root


def _binder(
    tmp_path: pathlib.Path,
    *,
    absent: tuple[str, ...] = (),
    rules: dict[str, list[dict]] | None = None,
    mktemp_missing: bool = False,
) -> str:
    """The COMPLETE PATH for one case: named real tools, plus the twelve fakes.

    `absent` names fakes to LEAVE OUT, which is how every `command not found` arm is driven. Each exclusion is asserted, because a probe that cannot fire is indistinguishable from a subject that cannot fail.
    """
    merged = json.loads(json.dumps(HEALTHY_RULES))
    for name, extra in (rules or {}).items():
        merged[name] = extra + merged.get(name, [])

    binder = tmp_path.resolve() / "bin"
    if binder.exists():
        shutil.rmtree(binder)
    binder.mkdir(parents=True)
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is not None:
            (binder / tool).symlink_to(target)

    log = str(tmp_path.resolve() / "calls.log")
    state = str(tmp_path.resolve() / "fake-state.json")
    upload = str(tmp_path.resolve() / "uploaded.txt")

    for name in CANNED_TOOLS:
        if name in absent:
            continue
        extra = "UPLOAD = %r%s" % (upload, RDC_UPLOAD_SNAPSHOT) if name == "rdc" else ""
        fake = binder / name
        fake.write_text(
            FAKE_CANNED
            % {
                "name": name,
                "rules": merged.get(name, []),
                "log": log,
                "state": state,
                "extra": extra,
            },
            encoding="utf-8",
        )
        fake.chmod(0o755)

    for name in PASSTHROUGH_TOOLS:
        if name in absent:
            continue
        real = shutil.which(name)
        assert real is not None, "the host has no %s; the harness cannot pass through to it" % name
        fake = binder / name
        fake.write_text(
            FAKE_PASSTHROUGH % {"name": name, "real": real, "log": log}, encoding="utf-8"
        )
        fake.chmod(0o755)

    if "mktemp" not in absent:
        fake = binder / "mktemp"
        fake.write_text(
            FAKE_MKTEMP
            % {"log": log, "base": str(tmp_path.resolve() / "scratch"), "missing": mktemp_missing},
            encoding="utf-8",
        )
        fake.chmod(0o755)

    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    for name in absent:
        assert shutil.which(name, path=str(binder)) is None, (
            "the probe cannot fire: %s is still reachable on the scratch PATH" % name
        )
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    binder: str,
    argv: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
) -> dict[str, object]:
    """Drive one subject from a NEUTRAL cwd and collect all five observables.

    The fakes' state file and call log are removed FIRST, so the second subject sees the same canned sequence as the first rather than continuing it.
    """
    cwd = tmp_path.resolve() / "elsewhere"
    cwd.mkdir(exist_ok=True)
    for leftover in ("calls.log", "fake-state.json", "uploaded.txt"):
        (tmp_path.resolve() / leftover).unlink(missing_ok=True)
    scratch = tmp_path.resolve() / "scratch"
    if scratch.exists():
        shutil.rmtree(scratch)

    env = {
        "PATH": binder,
        "HOME": str(tmp_path.resolve() / "home"),
        "USER": "harness-user",
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    for name, value in (env_extra or {}).items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value

    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        env=env,
        cwd=str(cwd),
        check=False,
        timeout=600,
    )
    log = tmp_path.resolve() / "calls.log"
    raw = log.read_text(encoding="utf-8") if log.exists() else ""
    calls, drifting = _split_drifting(_records(raw))
    uploaded = tmp_path.resolve() / "uploaded.txt"
    decode = lambda raw_bytes: raw_bytes.decode("utf-8", "surrogateescape")  # noqa: E731
    mask = lambda line: _mask(line, root, tmp_path.resolve())  # noqa: E731
    return {
        "exit": proc.returncode,
        "stdout": _mask(decode(proc.stdout), root, tmp_path.resolve()),
        "stderr": _mask(decode(proc.stderr), root, tmp_path.resolve()),
        "calls": [mask(line) for line in calls],
        "drifting": [mask(line) for line in drifting],
        "uploaded": uploaded.read_text(encoding="utf-8") if uploaded.exists() else None,
    }


def _ssh_rule(match: str, *responses: dict) -> dict[str, list[dict]]:
    """One overriding `ssh` rule, prepended so it wins over the healthy one."""
    return {"ssh": [{"match": match, "responses": list(responses)}]}


def _rdc_rule(match: str, *responses: dict) -> dict[str, list[dict]]:
    """One overriding `rdc` rule, matched against the NUL-joined argv."""
    return {"rdc": [{"match": match, "responses": list(responses)}]}


CASES = [
    pytest.param({}, {}, id="all-four-assertions-hold"),
    pytest.param({}, {"argv": ("--anything",)}, id="arguments-are-ignored-entirely"),
    # -- phase 2: the fork's `up` is the renet#60 failure -------------------
    pytest.param(
        {
            "rules": _rdc_rule(
                "up\x00bindrace-parent:child@worker-1", {"out": "o\n", "err": "e\n", "rc": 9}
            )
        },
        {},
        id="fork-up-fails-and-dumps-five-diagnostics",
    ),
    # -- phase 3: bind isolation -------------------------------------------
    pytest.param(
        {"rules": _ssh_rule("ss -Hltnp4", {"out": "127.0.1.1:5432\n"})},
        {},
        id="one-listener-is-not-enough",
    ),
    pytest.param(
        {"rules": _ssh_rule("ss -Hltnp4", {"out": ""})},
        {},
        id="no-listeners-still-prints-one-blank-indented-line",
    ),
    pytest.param(
        {"rules": _ssh_rule("ss -Hltnp4", {"out": "127.0.1.1:5432\n0.0.0.0:5432\n"})},
        {},
        id="a-wildcard-bind-is-renet60-regressed",
    ),
    pytest.param(
        {"rules": _ssh_rule("ss -Hltnp4", {"out": "*:5432\n127.0.1.1:5432\n"})},
        {},
        id="the-star-spelling-of-the-wildcard-too",
    ),
    pytest.param(
        {"rules": _ssh_rule("ss -Hltnp4", {"out": "127.0.1.1:5432\n10.0.0.5:5432\n"})},
        {},
        id="a-non-loopback-bind-is-refused-by-the-regex",
    ),
    pytest.param(
        {"rules": _ssh_rule("ss -Hltnp4", {"out": "127.0.1.1:5432\n127.0.1.1:5432\n"})},
        {},
        id="two-listeners-on-one-address-is-isolation-violated",
    ),
    pytest.param(
        {"rules": _ssh_rule("ss -Hltnp4", {"out": "127.0.1.1:5432\n", "err": "x\n", "rc": 255})},
        {},
        id="a-failing-binds-ssh-is-swallowed-by-the-inner-or-true",
    ),
    pytest.param(
        {"rules": _ssh_rule("ss -Hltnp4", {"out": "\n\n127.0.1.1:5432\n\n127.0.2.1:5432\n\n\n"})},
        {},
        id="blank-lines-in-the-bind-list-are-dropped",
    ),
    # -- phase 4: renet#59, and bash arithmetic on the answer ---------------
    pytest.param(
        {
            "rules": _ssh_rule(
                "com.docker.compose.project", {"out": "2\n", "err": "/x.sock owns 2\n"}
            )
        },
        {},
        id="two-projects-on-one-daemon-is-renet59-regressed",
    ),
    pytest.param(
        {"rules": _ssh_rule("com.docker.compose.project", {"out": "", "err": "no\n", "rc": 255})},
        {},
        id="a-failing-projects-ssh-ENDS-the-run-there-is-no-or-true-here",
    ),
    pytest.param(
        {"rules": _ssh_rule("com.docker.compose.project", {"out": ""})},
        {},
        id="an-empty-project-count-is-arithmetic-zero",
    ),
    pytest.param(
        {"rules": _ssh_rule("com.docker.compose.project", {"out": "1 2\n"})},
        {},
        id="a-two-field-project-count-is-a-bash-arithmetic-syntax-error",
    ),
    pytest.param(
        {"rules": _ssh_rule("com.docker.compose.project", {"out": "abc\n"})},
        {},
        id="a-word-project-count-is-a-NOUNSET-abort",
    ),
    pytest.param(
        {"rules": _ssh_rule("com.docker.compose.project", {"out": "08\n"})},
        {},
        id="a-zero-padded-eight-is-value-too-great-for-base",
    ),
    pytest.param(
        {"rules": _ssh_rule("com.docker.compose.project", {"out": "  7  \n"})},
        {},
        id="surrounding-whitespace-is-skipped-by-the-arithmetic-lexer",
    ),
    # -- phase 5: console#440 -----------------------------------------------
    pytest.param(
        {"rules": _ssh_rule("grep counter", {"out": ""})},
        {},
        id="the-parent-has-no-counter-container-at-all",
    ),
    pytest.param(
        {"rules": _ssh_rule("docker-aaa.sock", {"out": "1\n"})},
        {},
        id="the-counter-never-reaches-fifteen-so-the-loop-runs-out",
    ),
    pytest.param(
        {"rules": _ssh_rule("docker-aaa.sock", {"out": ""})},
        {},
        id="an-empty-counter-reading-is-reported-as-zero",
    ),
    pytest.param(
        {
            "rules": _ssh_rule(
                "docker-aaa.sock", {"out": "0x1f\n"}, {"out": "0x20\n"}, {"out": "0x21\n"}
            )
        },
        {},
        id="a-hex-counter-reading-is-read-in-base-sixteen",
    ),
    pytest.param(
        {
            "rules": _ssh_rule(
                "docker-aaa.sock", {"out": "016\n"}, {"out": "017\n"}, {"out": "020\n"}
            )
        },
        {},
        id="a-zero-padded-counter-reading-is-read-as-OCTAL",
    ),
    pytest.param(
        {"rules": _rdc_rule("--debug", {"out": "up: starting\nnothing was restored\n"})},
        {},
        id="the-fork-came-up-without-restoring-console440-regressed",
    ),
    pytest.param(
        {"rules": _rdc_rule("--debug", {"out": "bad\n", "rc": 4})},
        {},
        id="the-checkpoint-forks-up-failed-outright",
    ),
    pytest.param(
        {"rules": _ssh_rule("grep counter", {"out": "/var/run/rediacc/docker-aaa.sock\n"})},
        {},
        id="no-second-socket-means-no-counter-in-the-forks-daemon",
    ),
    pytest.param(
        {"rules": _ssh_rule("docker-bbb.sock", {"out": "3\n"})},
        {},
        id="a-fork-counter-behind-the-parent-means-a-fresh-start-not-a-restore",
    ),
    pytest.param(
        {
            "rules": _ssh_rule(
                "docker-aaa.sock",
                {"out": "10\n"},
                {"out": "20\n"},
                {"out": "30\n"},
                {"out": "30\n"},
            )
        },
        {},
        id="a-parent-counter-that-stopped-advancing-was-disturbed",
    ),
    # -- phase 0 and 1 ------------------------------------------------------
    pytest.param(
        {"rules": _rdc_rule("machine\x00add", {"out": "already\n", "err": "conflict\n", "rc": 1})},
        {},
        id="a-machine-that-is-already-registered-only-warns",
    ),
    pytest.param(
        {"rules": _rdc_rule("config\x00ssh\x00set", {"out": "noise\n", "err": "bad\n", "rc": 3})},
        {},
        id="a-failing-config-ssh-set-ends-the-run-with-its-own-status",
    ),
    pytest.param(
        {"rules": _rdc_rule("machine\x00setup", {"err": "no\n", "rc": 2})},
        {},
        id="a-failing-machine-setup-ends-the-run-before-any-cleanup-debris",
    ),
    pytest.param(
        {"rules": _rdc_rule("repo\x00create", {"err": "exists\n", "rc": 5})},
        {},
        id="a-failing-repo-create-ends-the-run",
    ),
    pytest.param({"mktemp_missing": True}, {}, id="mktemp-named-a-directory-that-does-not-exist"),
    # -- the environment ----------------------------------------------------
    pytest.param(
        {},
        {
            "env_extra": {
                "VM_NET_BASE": "10.9.8",
                "VM_WORKERS": "42 43",
                "SSH_USER": "bob",
                "SSH_KEY": "/k/ey",
                "MACHINE_NAME": "w9",
            }
        },
        id="all-five-overrides-are-honoured-and-only-the-first-worker-is-used",
    ),
    pytest.param(
        {},
        {
            "env_extra": {
                "VM_NET_BASE": "",
                "VM_WORKERS": "",
                "SSH_USER": "",
                "SSH_KEY": "",
                "MACHINE_NAME": "",
            }
        },
        id="an-empty-override-takes-the-default-not-the-empty-string",
    ),
    pytest.param(
        {}, {"env_extra": {"VM_WORKERS": "   "}}, id="a-blank-VM_WORKERS-is-an-unbound-array-abort"
    ),
    pytest.param(
        {},
        {"env_extra": {"VM_WORKERS": "7 8\n9"}},
        id="read--ra-consumes-ONE-line-so-a-second-line-is-unreachable",
    ),
    pytest.param({}, {"env_extra": {"USER": ""}}, id="no-USER-falls-through-to-whoami"),
    pytest.param({}, {"env_extra": {"USER": None}}, id="an-unset-USER-does-the-same"),
    pytest.param(
        {},
        {"env_extra": {"SSH_KEY": "/has a space/key"}},
        id="an-ssh-key-path-with-a-space-stays-one-argument",
    ),
    # -- missing tools ------------------------------------------------------
    pytest.param({"absent": ("ssh",)}, {}, id="ssh-is-not-on-path"),
    pytest.param({"absent": ("rdc",)}, {}, id="rdc-is-not-on-path"),
    pytest.param({"absent": ("sort",)}, {}, id="sort-is-not-on-path"),
    pytest.param({"absent": ("head",)}, {}, id="head-is-not-on-path"),
    pytest.param({"absent": ("tee",)}, {}, id="tee-is-not-on-path"),
    pytest.param({"absent": ("grep",)}, {}, id="grep-is-not-on-path"),
    pytest.param({"absent": ("tail",)}, {}, id="tail-is-not-on-path"),
    pytest.param({"absent": ("mktemp",)}, {}, id="mktemp-is-not-on-path"),
    pytest.param({"absent": ("cat",)}, {}, id="cat-is-not-on-path"),
    pytest.param({"absent": ("rm",)}, {}, id="rm-is-not-on-path"),
    pytest.param(
        {"absent": ("sleep",), "rules": _ssh_rule("docker-aaa.sock", {"out": "1\n"})},
        {},
        id="sleep-is-not-on-path-during-the-wait-loop",
    ),
    pytest.param(
        {"absent": ("grep",), "rules": _rdc_rule("--debug", {"out": "no restore here\n"})},
        {},
        id="a-missing-grep-STILL-runs-tail-because-bash-forks-both",
    ),
]


@pytest.mark.parametrize(("binder_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, binder_kw, run_kw):
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, **binder_kw)

    old = _run(TWIN_REL, root, tmp_path, binder, **run_kw)
    new = _run(PORT_REL, root, tmp_path, binder, **run_kw)

    for field in ("exit", "stdout", "stderr", "calls", "drifting", "uploaded"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_every_external_is_reached_in_order_on_the_passing_run(tmp_path):
    """ANTI-VACUITY, and the strongest claim in the file. Every comparison above is worthless if the run never orchestrated anything, and a port that printed the same twenty-four log lines while spawning nothing would satisfy a stdout-only comparison exactly."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    out = _run(PORT_REL, root, tmp_path, binder)
    assert out["exit"] == 0, out

    names = [line.split("\t")[0] for line in out["calls"]]
    assert len(out["calls"]) == 41, names
    # Nine remote payloads: binds, projects, two `counter_sockets`, and five `counter_value` readings (two while waiting, one on the fork, two after).
    assert names.count("ssh") == 9, names
    # Twenty-three CLI calls: three in phase 0, twelve across the two cleanups, and eight doing the actual work.
    assert names.count("rdc") == 23, names
    assert names.count("cat") == 2, "the two sidecar files are written by a real cat"
    assert names.count("sleep") == 2, "one 2s wait in the counter loop, one 3s after the fork"
    assert names.count("mktemp") == 2, names
    assert names.count("rm") == 2, "the sidecar directory and the debug log"
    assert names.count("grep") == 1, "the one `grep -q restored from checkpoint`"

    # The three drifting members that a passing run reaches, by exact argv, so the multiset comparison in the parametrized cases is not merely discarding them. `tail -20` belongs to the console#440 FAILURE report and is absent.
    drifting = [line.split("\t") for line in out["drifting"]]
    assert [line[:2] for line in drifting] == [
        ["head", "-1"],
        ["sort", "-u"],
        ["tee", "<tmp>/scratch/mkt.f"],
    ], out["drifting"]

    # The phase order, reduced to the six commands that define it.
    spine = [
        line.split("\t")[1:4]
        for line in out["calls"]
        if line.startswith("rdc\t") and line.split("\t")[1] in ("repo", "machine")
    ]
    assert ["machine", "setup", "worker-1"] in spine
    assert spine.index(["machine", "setup", "worker-1"]) < spine.index(
        ["repo", "create", "bindrace-parent"]
    ), spine

    forks = [line.split("\t")[1:] for line in out["calls"] if line.startswith("rdc\trepo\tfork")]
    assert forks == [
        ["repo", "fork", "bindrace-parent@worker-1", "--tag", "child"],
        ["repo", "fork", "bindrace-parent@worker-1", "--tag", "cpchild", "--checkpoint"],
    ], forks


def test_the_two_sidecar_files_reach_the_upload_byte_for_byte(tmp_path):
    """THE CONTRACT NO STREAM CAN SHOW. The compose file's `$$((i+1))` and
    `count=$$i` come from a QUOTED heredoc and must arrive UNEXPANDED: the
    doubled `$$` is compose's own escape, and a port that let a shell or an
    f-string touch them would upload `count=<pid>` and the checkpoint phase
    would compare two numbers that never existed. The twin `rm -rf`s the directory on the line after the upload, so the fake snapshot is the only place either subject's bytes can be read."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    snapshots = {}
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        snapshots[subject.name] = out["uploaded"]

    body = snapshots[TWIN_REL.name]
    assert body is not None, "the upload fake never fired; the sidecar was not written"
    assert (
        "command: sh -c 'i=0; while true; do i=$$((i+1)); echo \"count=$$i\"; sleep 1; done'"
        in body
    )
    assert '- "rediacc.checkpoint=true"' in body
    assert "renet compose -- up -d" in body
    assert "docker-compose.yml" in body, body
    assert "Rediaccfile" in body, body
    assert snapshots[PORT_REL.name] == body, "the port uploaded different bytes"


def test_the_double_tick_is_a_defect_pinned_rather_than_repaired(tmp_path):
    """A COSMETIC DEFECT IN THE TWIN. Four `log_info` calls open their message
    with a literal U+2713 and `log_info` already prefixes one, so the twin
    prints two. Reproduced exactly; the day the twin drops one of them this goes red and names the decision instead of letting a port drift."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert "✓ ✓ 2 distinct loopback binds" in out["stderr"], out["stderr"]
        assert "✓ ✓ each per-network daemon hosts at most one compose project" in out["stderr"]
        assert out["stderr"].count("✓ ✓") == 4, out["stderr"]
        # ...and the one message that is correctly single-ticked stays that way.
        assert "✓ parent counter at 20 before checkpoint" in out["stderr"]


def test_the_wait_loop_burns_all_thirty_sleeps_when_the_counter_never_moves(tmp_path):
    """A SECOND DEFECT IN THE TWIN, PINNED. `sleep 2` comes AFTER the `&& break`, so a counter that never reaches 15 does thirty readings and THIRTY sleeps: the thirtieth waits two seconds after the last reading the loop will ever take. Thirty `sleep 2` calls is the shape, and a port that broke out early would be friendlier and would not be the same script."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, rules=_ssh_rule("docker-aaa.sock", {"out": "1\n"}))
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1
        sleeps = [line for line in out["calls"] if line.startswith("sleep\t")]
        assert sleeps == ["sleep\t2"] * 30, "%s slept %d time(s)" % (subject.name, len(sleeps))
        assert "parent counter stuck at '1'" in out["stderr"], out["stderr"]


def test_a_healthy_run_is_not_refused(tmp_path):
    """THE NEGATIVE CONTROL on all four assertions. A gate with only positive controls will happily refuse a run where nothing is wrong."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 0, "%s refused a healthy run" % subject.name
        assert "✗" not in out["stderr"], out["stderr"]
        assert (
            "PASS: parent + fork running, distinct binds, no foreign containers,"
            " checkpoint fork restored" in out["stderr"]
        )


def test_the_wildcard_bind_is_the_reason_the_script_exists(tmp_path):
    """renet#60 IS `0.0.0.0:5432`. If this stops firing the script is certifying nothing, whichever subject runs it."""
    root = _fixture(tmp_path)
    binder = _binder(
        tmp_path, rules=_ssh_rule("ss -Hltnp4", {"out": "0.0.0.0:5432\n127.0.1.1:5432\n"})
    )
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, "%s accepted a wildcard bind" % subject.name
        assert "found wildcard bind '0.0.0.0:5432'" in out["stderr"], out["stderr"]
        assert "renet#60 regressed" in out["stderr"]
        # And the run stops THERE: phase 4 must never be reached.
        assert "renet#59" not in out["stderr"], out["stderr"]


def test_the_cleanup_trap_runs_on_every_path_including_the_early_aborts(tmp_path):
    """`trap cleanup EXIT` is the twin's only guarantee that a failed run leaves no repos behind. A port that put the cleanup after the last statement rather than in a `finally` would pass every happy-path comparison."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, rules=_ssh_rule("ss -Hltnp4", {"out": ""}))
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1
        deletes = [line for line in out["calls"] if line.startswith("rdc\trepo\tdelete")]
        # Six: three from the pre-clean in phase 0, three from the EXIT trap.
        assert len(deletes) == 6, "%s ran %d delete(s)" % (subject.name, len(deletes))
        assert out["stderr"].count("Cleanup (best-effort)") == 2, out["stderr"]


def test_the_unbound_array_abort_runs_no_cleanup_whatsoever(tmp_path):
    """THE ONE PATH WITH NO TRAP. `${WORKER_IDS[0]}` is read on line 36 and
    `trap cleanup EXIT` is installed on line 67, so a whitespace-only `VM_WORKERS` dies before any handler exists. A port that installed its `finally` around the whole of `main` would run six `rdc` calls the twin never runs."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, env_extra={"VM_WORKERS": "   "})
        assert out["exit"] == 1, "%s exited %r" % (subject.name, out["exit"])
        assert out["calls"] == [], "%s ran %r before dying" % (subject.name, out["calls"])
        assert "WORKER_IDS[0]: unbound variable" in out["stderr"], out["stderr"]
        assert "Cleanup" not in out["stderr"], out["stderr"]


def test_backslashes_in_remote_output_are_the_one_known_divergence(tmp_path):
    """A DELIBERATE, PRE-EXISTING RULING, ASSERTED SO NOBODY "FIXES" IT.

    `common.sh` logs with `echo -e`, which interprets backslash escapes IN THE MESSAGE; `rediacc_ci.log` formats the message as data. That decision is recorded in `rediacc_ci/log.py` and pinned by `tests/test_log.py`. Nine of this script's messages interpolate remote output, so the difference is reachable here, and it is asserted from BOTH sides: the twin turns the `\\t` into a
    tab, the port keeps the two characters.

    Nothing else in the file drives a backslash, which is why the parametrized cases above can compare stderr byte for byte.
    """
    root = _fixture(tmp_path)
    binder = _binder(
        tmp_path, rules=_ssh_rule("ss -Hltnp4", {"out": "127.0.1.1:5432\n127.0.2.1:5432\\tX\n"})
    )
    twin = _run(TWIN_REL, root, tmp_path, binder)
    new = _run(PORT_REL, root, tmp_path, binder)

    assert twin["exit"] == new["exit"] == 1, (twin["exit"], new["exit"])
    assert "unexpected bind '127.0.2.1:5432\tX'" in twin["stderr"], repr(twin["stderr"])
    assert "unexpected bind '127.0.2.1:5432\\tX'" in new["stderr"], repr(new["stderr"])
    assert twin["stderr"] != new["stderr"], (
        "the two agree, so this divergence is gone and the test should be deleted"
    )


def test_the_drift_is_real_and_the_split_survives_repetition(tmp_path):
    """A CONTROL ON THE NORMALISATION. `_split_drifting` exists because a shell does not fix the order in which two members of one pipeline reach their `exec`. If that were untrue the split would be discarding four records for nothing, so both halves are re-derived here rather than trusted: the twin is run repeatedly on one fixture, the ordered spine must be IDENTICAL every time,
    and the port must match it.

    The instability itself was measured 2026-09-14: on the raw log, `grep` before `tail` seven times and `tail` before `grep` five times out of twelve, and under `pytest -n 8` a `head` line landed two slots ahead of a command that causally precedes its own pipeline.
    """
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, rules=_rdc_rule("--debug", {"out": "nothing restored\n"}))
    spines = set()
    for _ in range(6):
        old = _run(TWIN_REL, root, tmp_path, binder)
        new = _run(PORT_REL, root, tmp_path, binder)
        assert new["calls"] == old["calls"], "the ordered spine diverged"
        assert new["drifting"] == old["drifting"], "the drifting multiset diverged"
        # All four right-hand members are reached on this path: the console#440 failure report is what brings `tail -20` in beside the other three.
        assert [line.split("\t")[0] for line in old["drifting"]] == [
            "head",
            "sort",
            "tail",
            "tee",
        ], old["drifting"]
        spines.add(tuple(old["calls"]))
    assert len(spines) == 1, "the ordered spine is not stable across runs of the twin"


def test_the_drift_split_removes_only_the_four_right_hand_tools():
    """A CONTROL ON THE CONTROL. If `_split_drifting` removed more it would hide the phase ordering that every case above depends on."""
    sample = ["rdc\tx", "head\t-1", "ssh\ty", "sort\t-u", "grep\t-q", "tee\tf", "tail\t-20"]
    ordered, drifting = _split_drifting(sample)
    assert ordered == ["rdc\tx", "ssh\ty", "grep\t-q"], ordered
    assert drifting == ["head\t-1", "sort\t-u", "tail\t-20", "tee\tf"], drifting
    # An empty log splits into two empty halves rather than raising.
    assert _split_drifting([]) == ([], [])


def test_the_record_splitter_keeps_multiline_ssh_payloads_whole():
    """Five of the eight remote scripts span many lines, and one of them opens
    with a newline. A splitter that used `splitlines()` would turn one call into
    fourteen records and every call-log comparison would be comparing noise."""
    raw = "rdc\trepo\tup\nssh\t-i\tk\tsudo bash -c '\n  for x; do\n  done\n'\nsleep\t2\n"
    assert _records(raw) == [
        "rdc\trepo\tup",
        "ssh\t-i\tk\tsudo bash -c '\n  for x; do\n  done\n'",
        "sleep\t2",
    ]
    # A payload whose own last character is a newline (PROJECTS_CMD is one) leaves an empty continuation line, and that line is part of the record.
    assert _records("ssh\tpayload\n\nrm\t-f\tx\n") == ["ssh\tpayload\n", "rm\t-f\tx"]


def test_the_mask_does_not_hide_the_message(tmp_path):
    """A CONTROL ON THE MASK. `_mask` collapses the `<$0>: line <n>: ` prefix on both sides; if it were greedier it would hide real divergences and every
    case above would pass for the wrong reason."""
    sample = "/a/b/twin.sh: line 73: rdc: command not found\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: rdc: command not found\nkept: line noise\n", masked

    root = _fixture(tmp_path)
    binder = _binder(tmp_path, absent=("mktemp",))
    raw = {}
    for subject in (TWIN_REL, PORT_REL):
        proc = subprocess.run(
            ["bash" if subject.suffix == ".sh" else "python3", str(root / subject)],
            capture_output=True,
            text=True,
            env={
                "PATH": binder,
                "HOME": str(tmp_path / "home"),
                "USER": "harness-user",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / ".ci"),
            },
            cwd=str(tmp_path),
            check=False,
            timeout=600,
        )
        raw[subject.name] = proc.stderr
    assert raw[TWIN_REL.name] != raw[PORT_REL.name], (
        "the two prefixes are identical, so the mask is unnecessary and should be deleted"
    )
    for name, text in raw.items():
        assert "mktemp: command not found" in text, "%s said %r" % (name, text)


# --------------------------------------------------------------------------- The arithmetic helper, exercised directly. These are the eight shapes the module docstring names as the driven boundary; each was measured against bash 5 on 2026-09-14 and the parametrized cases above drive five of them through both subjects end to end.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("   ", 0),
        ("7", 7),
        ("  7  ", 7),
        ("010", 8),
        ("0x1f", 31),
        ("0X1F", 31),
        ("+5", 5),
        ("-3", -3),
        ("0", 0),
    ],
)
def test_arith_reads_the_literals_bash_reads(text, expected):
    assert port.arith(text) == expected


def test_arith_reports_an_unset_name_as_fatal_and_a_bad_shape_as_not_fatal():
    """The two failure modes are NOT interchangeable, and conflating them is the mistake a port makes here: a nounset error kills the shell even from inside an `if` condition, while a syntax error prints and leaves `[[ ]]` false."""
    with pytest.raises(port._ArithError) as unset:
        port.arith("abc")
    assert unset.value.fatal is True
    assert unset.value.message == "abc: unbound variable"

    with pytest.raises(port._ArithError) as unset_first:
        port.arith("abc def")
    assert unset_first.value.message == "abc: unbound variable", (
        "bash evaluates the FIRST token and dies before it sees the second"
    )

    with pytest.raises(port._ArithError) as two_fields:
        port.arith("1 2")
    assert two_fields.value.fatal is False
    assert two_fields.value.message == (
        '[[: 1 2: %s in expression (error token is "2")' % bash_dialect.arith_syntax_error()
    )

    with pytest.raises(port._ArithError) as bad_base:
        port.arith("08")
    assert bad_base.value.fatal is False
    assert bad_base.value.message == '[[: 08: value too great for base (error token is "08")'

"""Differential: `.ci/rediacc_ci/private/renet_root_tests.py` against its twin
`.ci/scripts/private/renet-root-tests.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new
code is correct", it is "the new code says what the old code said". Only running
BOTH, on the same fixture, in the same run, can support that.

NO REAL `go` IS EVER INVOKED. The subject's whole job is to run root-tagged Go
tests that need `sudo`, a BTRFS mount and a compiled `private/renet`; a suite
that shelled out to the real toolchain would take minutes, would need root, and
would SKIP on any machine that lacked one of those, which is the exact vacuity
this campaign exists to avoid. `go` is a recording fake on a scratch PATH: it
appends its cwd and full argv to a log, writes canned bytes to stdout AND
stderr, and exits with a canned status. Every case below therefore drives a
`go test` outcome that could not otherwise be produced on this machine at all,
including "the run passed but one named test never appeared".

WHAT IS COMPARED, AND WHY IT IS FOUR THINGS. Every case compares:

  1. the exit code;
  2. stdout, which carries BOTH the whole go transcript and the `::error::`
     annotation, because the twin puts them there;
  3. stderr, which carries only the two `log_step`/`log_info` lines;
  4. the CALL LOG: every `go` invocation, its cwd AND its argv. A port that
     printed the same transcript while dropping `-tags root`, or running from
     the wrong directory, passes a stdout-only comparison and compiles nothing.

PATH IS REPLACED, NEVER PREPENDED, and this host HAS a real `go`
(`/home/developer/.local/bin/go`, go1.26.6, verified with `which go`). A prepend would leave the "go is missing"
case silently consulting the real toolchain. `_binder` therefore builds the
ENTIRE PATH out of named tools and asserts that what it was asked to exclude
really is absent, because a probe that cannot fire looks exactly like a subject
that cannot fail.

ONE FIXTURE TREE PER CASE, BOTH SUBJECTS IN IT. Unlike `test_infra_build_renet
.py`, neither subject here mutates the tree, so a second copy would only make
the two runs disagree about their own root path for no reason. The binder is
shared for the same reason: the `Permission denied` case prints the RESOLVED
path of the fake `go`, and two per-subject binders would put two different
paths into that message.

THE ONE MASK, AND WHY IT IS NOT A LOOPHOLE. Bash prefixes its own diagnostics
with `<$0>: line <n>: `, and `$0` is the path of the file bash is running: the
twin. The port composes the same prefix from `sys.argv[0]` and its own live
frame. Those two prefixes can never be equal, because they name two different
files, so `_mask` collapses exactly that prefix on both sides and compares
everything after it byte for byte. `test_the_mask_does_not_hide_the_message`
pins the mask itself, so it cannot quietly grow into something that hides a real
divergence.
"""

import os
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "renet-root-tests.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "renet_root_tests.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/renet-root-tests.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/renet_root_tests.py")

# The recording `go`. Configured by its own TEXT rather than through the
# environment: the subject advertises "No env vars", and a fixture that added
# three would make any env-shaped divergence unattributable.
#
# BOTH STREAMS ARE WRITTEN AS RAW BYTES AND EACH IS FLUSHED IMMEDIATELY. Bytes,
# because one case drives output that is not valid UTF-8 and a `str` write would
# raise inside the fake instead of reaching the subject. The subject merges the
# two streams with `2>&1`, so this is what proves the merge happens; the flushes
# make the interleaving deterministic, which an unflushed pair would not be.
FAKE_GO = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
RC = %(rc)d
OUT = %(out)r
ERR = %(err)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join(["go", os.path.relpath(os.getcwd(), ROOT), *sys.argv[1:]]) + "\\n")
sys.stdout.buffer.write(OUT)
sys.stdout.buffer.flush()
sys.stderr.buffer.write(ERR)
sys.stderr.buffer.flush()
sys.exit(RC)
"""

# Everything both subjects need once PATH is rebuilt from scratch. Named rather
# than derived: a PATH built by copying "everything except go" is a PATH nobody
# can state, and the first tool it forgot would look like a divergence in the
# subject rather than a hole in the harness.
NEEDED = (
    "bash",
    "sh",
    "python3",
    "uname",
    "dirname",
    "cat",
    "grep",
    "sed",
    "rm",
    "mkdir",
    "env",
    "ls",
)

# The three names the twin guards, and a full transcript in which all three
# pass. `go test -v` really does print these lines in this shape.
NAMES = (
    "TestSaveState_SetsOwnership",
    "TestSaveState_OwnershipMatchesMountDir",
    "TestLoadState_PreservesData",
)


def _transcript(*passing: str, ok: bool = True) -> str:
    lines = []
    for name in NAMES:
        lines.append("=== RUN   %s" % name)
        if name in passing:
            lines.append("--- PASS: %s (0.01s)" % name)
        else:
            lines.append("--- FAIL: %s (0.01s)" % name)
            lines.append("    state_test.go:41: not running as root")
    lines.append("PASS" if ok else "FAIL")
    lines.append("%s\tgithub.com/rediacc/renet/pkg/repository\t0.042s" % ("ok" if ok else "FAIL"))
    return "\n".join(lines) + "\n"


ALL_PASS = _transcript(*NAMES).encode("utf-8")

# `<$0>: line <n>: ` -- the only thing masked, on both sides. See the module
# docstring; `test_the_mask_does_not_hide_the_message` pins it.
SHELL_PREFIX = re.compile(r"^[^\n]*?: line \d+: ", re.MULTILINE)


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    text = SHELL_PREFIX.sub("<shell>: ", text)
    return text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")


def _fixture(tmp_path: pathlib.Path, *, submodule: str = "dir") -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location
    (`BASH_SOURCE`/`__file__`, then three directories up). Driving the tracked
    files with a `cwd` would point both at the REAL repository, and the go fake
    would then be invoked in the real `private/renet`.

    `.resolve()` on the root is load-bearing: bash's `cd X && pwd` reports the
    LOGICAL path it was handed while `pathlib.resolve()` follows symlinks, and
    the root string appears in the `cd` diagnostic. Handing both subjects an
    already-resolved root makes them agree for the right reason.

    `submodule` takes the three shapes the `cd` can meet: a directory, nothing
    at all, and a plain FILE where the directory should be (an uninitialised
    submodule that somebody replaced), which bash reports differently.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    if submodule == "dir":
        (root / "private" / "renet" / "pkg" / "repository").mkdir(parents=True)
    elif submodule == "file":
        (root / "private").mkdir(parents=True)
        (root / "private" / "renet").write_text("gitlink\n", encoding="utf-8")
    return root


def _binder(
    tmp_path: pathlib.Path,
    *,
    go: str = "ok",
    rc: int = 0,
    out: bytes = ALL_PASS,
    err: bytes = b"",
) -> str:
    """The COMPLETE PATH for one case: named real tools, plus the fake `go`.

    `go` is one of "ok" (a recording fake), "missing" (absent from PATH
    entirely) and "noexec" (present, not executable) -- the third is the only
    shape for which bash names the resolved path instead of the bare word.
    """
    binder = tmp_path.resolve() / "bin"
    binder.mkdir(parents=True, exist_ok=True)
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is None:
            continue
        link = binder / tool
        if not link.exists():
            link.symlink_to(target)

    gob = binder / "go"
    if go != "missing":
        gob.write_text(
            FAKE_GO
            % {
                "log": str(tmp_path.resolve() / "calls.log"),
                "root": str(tmp_path.resolve() / "tree"),
                "rc": rc,
                "out": out,
                "err": err,
            },
            encoding="utf-8",
        )
        gob.chmod(0o755 if go == "ok" else 0o644)

    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    if go == "missing":
        assert shutil.which("go", path=str(binder), mode=os.F_OK) is None, (
            "the restricted PATH still resolves go; the missing-go case would be vacuous"
        )
    if go == "noexec":
        assert shutil.which("go", path=str(binder)) is None, (
            "the fake go is still executable; the Permission denied case would be vacuous"
        )
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    binder: str,
    argv: tuple[str, ...] = (),
) -> dict[str, object]:
    """Drive one subject and collect all four observables."""
    env = {
        "PATH": binder,
        "HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what
        # runs, so the package has to come from the real checkout. This is the
        # only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        timeout=120,
        # BYTES, not text: one case drives output that is not valid UTF-8, and
        # `text=True` would decode it before the comparison could see it.
    )
    log = tmp_path.resolve() / "calls.log"
    calls: list[str] = []
    if log.exists():
        calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        log.unlink()
    return {
        "exit": proc.returncode,
        "stdout": _mask(proc.stdout.decode("utf-8", "backslashreplace"), root, tmp_path.resolve()),
        "stderr": _mask(proc.stderr.decode("utf-8", "backslashreplace"), root, tmp_path.resolve()),
        "calls": calls,
    }


CASES = [
    pytest.param({}, {}, id="all-three-pass"),
    pytest.param(
        {},
        {"argv": ("--unexpected", "arguments")},
        id="arguments-are-ignored-entirely",
    ),
    pytest.param(
        {"out": _transcript(NAMES[1], NAMES[2], ok=False).encode(), "rc": 1},
        {},
        id="go-fails-first-test-did-not-pass",
    ),
    pytest.param(
        {"out": _transcript(*NAMES, ok=True).encode(), "rc": 1},
        {},
        id="go-fails-despite-a-passing-transcript",
    ),
    pytest.param(
        {"out": _transcript(NAMES[1], NAMES[2]).encode()},
        {},
        id="green-run-missing-the-first-name",
    ),
    pytest.param(
        {"out": _transcript(NAMES[0], NAMES[2]).encode()},
        {},
        id="green-run-missing-the-second-name",
    ),
    pytest.param(
        {"out": _transcript(NAMES[0], NAMES[1]).encode()},
        {},
        id="green-run-missing-the-third-name",
    ),
    pytest.param({"out": b""}, {}, id="green-run-with-no-output-at-all"),
    pytest.param(
        {"out": b"testing: warning: no tests to run\nPASS\nok  \t0.001s\n"},
        {},
        id="run-pattern-matched-nothing",
    ),
    pytest.param({"out": ALL_PASS + b"\n\n\n"}, {}, id="trailing-blank-lines-collapse"),
    pytest.param({"out": b"", "err": ALL_PASS}, {}, id="go-wrote-only-to-stderr"),
    pytest.param(
        {"out": ALL_PASS[: ALL_PASS.index(b"PASS\n")], "err": b"PASS\nok\t0.042s\n"},
        {},
        id="both-streams-interleaved",
    ),
    pytest.param(
        {"out": b"ok \xffbad-utf8\n" + ALL_PASS},
        {},
        id="output-that-is-not-valid-utf8",
    ),
    pytest.param({"go": "missing"}, {}, id="go-is-not-installed"),
    pytest.param({"go": "noexec"}, {}, id="go-is-not-executable"),
    pytest.param({}, {"submodule": "none"}, id="submodule-not-checked-out"),
    pytest.param({}, {"submodule": "file"}, id="submodule-path-is-a-file"),
]


@pytest.mark.parametrize(("binder_kw", "fixture_kw"), CASES)
def test_port_and_twin_agree(tmp_path, binder_kw, fixture_kw):
    root = _fixture(tmp_path, **{k: v for k, v in fixture_kw.items() if k == "submodule"})
    binder = _binder(tmp_path, **binder_kw)
    argv = fixture_kw.get("argv", ())

    old = _run(TWIN_REL, root, tmp_path, binder, argv=argv)
    new = _run(PORT_REL, root, tmp_path, binder, argv=argv)

    for field in ("exit", "stdout", "stderr", "calls"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_the_recording_go_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if `go` never ran.

    The argv is asserted ELEMENT BY ELEMENT rather than as a blob, because
    `-tags root` is the one flag without which the three subject tests do not
    compile, and a port that dropped it would still print a green transcript.
    """
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    out = _run(PORT_REL, root, tmp_path, binder)
    assert out["calls"], "the recording go was never invoked; this file proves nothing"
    assert len(out["calls"]) == 1, "go ran %d times, not once" % len(out["calls"])
    fields = out["calls"][0].split("\t")
    assert fields[0] == "go"
    assert fields[1] == "private/renet", "go ran in %r, not the renet source dir" % fields[1]
    assert fields[2:] == [
        "test",
        "-tags",
        "root",
        "-run",
        (
            "TestSaveState_SetsOwnership|TestSaveState_OwnershipMatchesMountDir"
            "|TestLoadState_PreservesData"
        ),
        "./pkg/repository/",
        "-v",
        "-count=1",
        "-timeout",
        "300s",
    ], "go argv was %r" % (fields[2:],)
    assert out["exit"] == 0, "the happy path must succeed: %r" % out


def test_the_guard_fires_on_a_green_run_that_skipped_everything(tmp_path):
    """THE POSITIVE CONTROL for the reason this script exists.

    `go test` exits 0 when every test skipped. Without the guard both subjects
    would report success having verified nothing at all.
    """
    root = _fixture(tmp_path)
    skipped = "=== RUN   %s\n--- SKIP: %s (0.00s)\nPASS\nok\t0.001s\n" % (NAMES[0], NAMES[0])
    binder = _binder(tmp_path, rc=0, out=skipped.encode())
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, "%s went green on an all-skips run" % subject.name
        assert "::error::%s did not PASS" % NAMES[0] in out["stdout"], out["stdout"]


def test_the_guard_does_not_fire_on_a_real_pass(tmp_path):
    """THE NEGATIVE CONTROL. A gate with only positive controls will happily
    flag a tree in which nothing is wrong."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 0, "%s failed a run in which all three passed" % subject.name
        assert "::error::" not in out["stdout"]
        assert "Root-tagged repository tests passed" in out["stderr"]


def test_only_the_first_missing_name_is_reported(tmp_path):
    """The twin's loop exits on the FIRST miss, so a run in which all three are
    absent names one test, not three. Reproduced rather than improved: a port
    that listed all three would be a different gate, and the difference would
    show up in CI annotations."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, out=b"PASS\nok\t0.001s\n")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["stdout"].count("::error::") == 1, out["stdout"]
        assert NAMES[0] in out["stdout"]
        assert NAMES[1] not in out["stdout"]


def test_a_substring_match_satisfies_the_guard(tmp_path):
    """A TWIN DEFECT, PINNED IN BOTH: `grep -q -- "--- PASS: $t"` is a substring
    test, so `--- PASS: TestLoadState_PreservesDataAndMore` satisfies the guard
    for `TestLoadState_PreservesData`. A renamed test would therefore keep the
    guard green while the test it names no longer exists.

    Reported, not fixed: anchoring the pattern would change what the gate
    accepts, which is a cutover-box decision, and a port that anchored it would
    no longer be equivalent to the script it claims to replace.
    """
    root = _fixture(tmp_path)
    renamed = "".join(
        "=== RUN   %sAndMore\n--- PASS: %sAndMore (0.01s)\n" % (name, name) for name in NAMES
    )
    binder = _binder(tmp_path, out=(renamed + "PASS\nok\t0.05s\n").encode())
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 0, "%s: expected the defect to be reproduced" % subject.name
        assert "::error::" not in out["stdout"]


def test_the_mask_does_not_hide_the_message(tmp_path):
    """A CONTROL ON THE CONTROL. `_mask` collapses the `<$0>: line <n>: ` prefix
    on both sides; if it were greedier than that it would hide real divergences
    and every case above would pass for the wrong reason."""
    sample = "/a/b/twin.sh: line 20: go: command not found\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: go: command not found\nkept: line noise\n", masked
    # And the thing it is masking really is different between the two subjects,
    # which is the whole reason the mask exists.
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, go="missing")
    raw = {}
    for subject in (TWIN_REL, PORT_REL):
        env = {
            "PATH": binder,
            "HOME": str(tmp_path),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT / ".ci"),
        }
        runner = "bash" if subject.suffix == ".sh" else "python3"
        proc = subprocess.run(
            [runner, str(root / subject)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=120,
        )
        raw[subject.name] = proc.stdout
    assert raw[TWIN_REL.name] != raw[PORT_REL.name], (
        "the two prefixes are identical, so the mask is unnecessary and should be deleted"
    )
    assert "go: command not found" in raw[TWIN_REL.name]
    assert "go: command not found" in raw[PORT_REL.name]

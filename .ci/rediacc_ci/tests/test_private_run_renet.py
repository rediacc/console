"""Differential: `.ci/rediacc_ci/private/run_renet.py` against its twin
`.ci/scripts/private/run-renet.sh`, the registered gate `check:ci-renet`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new
code is correct", it is "the new code says what the old code said". Only running
BOTH, on the same fixture, in the same run, can support that.

THE REAL `private/renet/.ci/ci.sh` IS NEVER INVOKED. It is the submodule's whole
CI: govulncheck, golangci-lint, deadcode and `go test ./...` under root. A suite
that reached it would take many minutes, would need a Go toolchain and root, and
would SKIP on a checkout without the submodule -- and a skip here is exactly the
failure `common.sh`'s CI arm exists to prevent. The fixture supplies its own
recording `ci.sh`, which appends its cwd, its argv AND the `GOTOOLCHAIN` it
inherited to a log and exits with a canned status.

WHAT IS COMPARED, AND WHY `GOTOOLCHAIN` IS ONE OF THE FOUR. Every case compares
the exit code, stdout, stderr, and the CALL LOG. That log carries the exported
`GOTOOLCHAIN` because the export is the only thing this script does that a
downstream tool can see and no stream can show: `export
GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"` is what keeps `private/renet/go.mod`'s
`toolchain` directive the single source of truth, and the twin's own comment
records the incident where a hard pin had already diverged from it. A port that
set it in a per-call `env=` dict instead of exporting would pass a stdout-only
comparison and would stop covering `ci.sh`'s own children.

NO `cd` HAPPENS IN EITHER SUBJECT, so the recorded cwd is the CALLER's, and the
cases below are driven from a neutral directory that is neither the fixture root
nor this checkout. That is what makes the absence of a `cd` observable.

THE THREE ARMS OF THE SUBMODULE GUARD ARE ALL DRIVEN. Present, absent-under-CI
(three errors, exit 1) and absent-locally (one warning, exit 0). The middle one
is the arm that stops this gate from reporting success while checking nothing,
and `test_the_ci_arm_is_the_reason_the_guard_exists` fails if it ever stops
exiting non-zero.

THE ONE MASK. Bash prefixes its own diagnostics with `<$0>: line <n>: `, naming
the file it is running; the port composes the same prefix from `sys.argv[0]` and
its own live frame. Those can never be equal, so `_mask` collapses exactly that
prefix on both sides. `test_the_mask_does_not_hide_the_message` pins it.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "run-renet.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "run_renet.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/run-renet.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/run_renet.py")

# The recording `ci.sh`, standing in for the renet submodule's entire CI. It
# records the one environment variable the subject exports, which is the only
# way that export is observable at all.
FAKE_CI_SH = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
RC = %(rc)d
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join([
        "ci.sh",
        os.getcwd(),
        "GOTOOLCHAIN=%%s" %% os.environ.get("GOTOOLCHAIN", "<unset>"),
        *sys.argv[1:],
    ]) + "\\n")
sys.stdout.write("renet ci stage output\\n")
sys.stdout.flush()
sys.stderr.write("renet ci stage warning\\n")
sys.stderr.flush()
sys.exit(RC)
"""

# Everything both subjects need once PATH is rebuilt from scratch. Named rather
# than derived: a PATH built by copying "everything except X" is a PATH nobody
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

SHELL_PREFIX = re.compile(r"^[^\n]*?: line \d+: ", re.MULTILINE)


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    text = SHELL_PREFIX.sub("<shell>: ", text)
    return text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")


def _fixture(tmp_path: pathlib.Path, *, marker: str = "script", rc: int = 0) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    `marker` is the shape of `private/renet/.ci/ci.sh`, and there are four
    because the guard tests EXISTENCE (`-e`) while the invocation needs an
    executable file:

      "script"  a working recording fake
      "none"    absent, so the guard decides
      "noexec"  present, not executable  -> bash exits 126, Permission denied
      "dir"     a DIRECTORY named ci.sh  -> passes `-e`, then exits 126,
                Is a directory. This is the case that shows the guard's `-e` is
                not an executability test.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    renet_ci = root / "private" / "renet" / ".ci"
    renet_ci.mkdir(parents=True)
    target = renet_ci / "ci.sh"
    if marker == "dir":
        target.mkdir()
    elif marker in ("script", "noexec"):
        target.write_text(
            FAKE_CI_SH % {"log": str(tmp_path.resolve() / "calls.log"), "rc": rc},
            encoding="utf-8",
        )
        target.chmod(0o755 if marker == "script" else 0o644)
    return root


def _binder(tmp_path: pathlib.Path) -> str:
    """The COMPLETE PATH for one case. Nothing the subject calls lives on it:
    `ci.sh` is invoked by absolute path, so this only has to carry the two
    interpreters and what `common.sh` asks at source time."""
    binder = tmp_path.resolve() / "bin"
    binder.mkdir(parents=True, exist_ok=True)
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is None:
            continue
        link = binder / tool
        if not link.exists():
            link.symlink_to(target)
    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    binder: str,
    argv: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
) -> dict[str, object]:
    """Drive one subject from a NEUTRAL cwd and collect all four observables."""
    cwd = tmp_path.resolve() / "elsewhere"
    cwd.mkdir(exist_ok=True)
    env = {
        "PATH": binder,
        "HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log` and `rediacc_ci.core.common`; the
        # COPY under the fixture is what runs, so the package has to come from
        # the real checkout. This is the only thing the fixture borrows from
        # outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    env.update(env_extra or {})
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        check=False,
        timeout=120,
    )
    log = tmp_path.resolve() / "calls.log"
    calls: list[str] = []
    if log.exists():
        calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        log.unlink()
    return {
        "exit": proc.returncode,
        "stdout": _mask(proc.stdout, root, tmp_path.resolve()),
        "stderr": _mask(proc.stderr, root, tmp_path.resolve()),
        "calls": [_mask(line, root, tmp_path.resolve()) for line in calls],
    }


CASES = [
    pytest.param({}, {}, id="no-argument-means-stage-all"),
    pytest.param({}, {"argv": ("quality",)}, id="stage-quality"),
    pytest.param({}, {"argv": ("test",)}, id="stage-test"),
    pytest.param({}, {"argv": ("",)}, id="empty-stage-becomes-all"),
    pytest.param({}, {"argv": ("quality", "test")}, id="extra-arguments-are-dropped"),
    pytest.param({}, {"argv": ("no-such-stage",)}, id="unknown-stage-is-forwarded"),
    pytest.param({}, {"argv": ("--help",)}, id="a-flag-is-just-a-stage-name"),
    pytest.param({"rc": 7}, {"argv": ("quality",)}, id="stage-failure-status-is-passed-through"),
    pytest.param({"rc": 1}, {}, id="stage-failure-status-one"),
    pytest.param({"marker": "none"}, {}, id="submodule-absent-locally"),
    pytest.param(
        {"marker": "none"},
        {"env_extra": {"CI": "true"}},
        id="submodule-absent-in-ci-is-fatal",
    ),
    pytest.param(
        {"marker": "none"},
        {"env_extra": {"CI": "false"}},
        id="submodule-absent-ci-false",
    ),
    pytest.param(
        {"marker": "none"},
        {"env_extra": {"CI": "1"}},
        id="ci-is-tested-against-the-literal-true",
    ),
    pytest.param(
        {"marker": "none"},
        {"env_extra": {"GITHUB_ACTIONS": "true"}},
        id="github-actions-alone-takes-the-local-arm",
    ),
    pytest.param({"marker": "noexec"}, {}, id="ci-sh-is-not-executable"),
    pytest.param({"marker": "dir"}, {}, id="ci-sh-is-a-directory"),
    pytest.param(
        {},
        {"env_extra": {"GOTOOLCHAIN": "go1.25.12"}},
        id="a-preset-gotoolchain-survives",
    ),
    pytest.param(
        {},
        {"env_extra": {"GOTOOLCHAIN": ""}},
        id="an-empty-gotoolchain-becomes-auto",
    ),
    pytest.param(
        {},
        {"env_extra": {"GOTOOLCHAIN": "local"}},
        id="gotoolchain-local-survives",
    ),
]


@pytest.mark.parametrize(("fixture_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, fixture_kw, run_kw):
    root = _fixture(tmp_path, **fixture_kw)
    binder = _binder(tmp_path)

    old = _run(TWIN_REL, root, tmp_path, binder, **run_kw)
    new = _run(PORT_REL, root, tmp_path, binder, **run_kw)

    for field in ("exit", "stdout", "stderr", "calls"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_the_recording_stage_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if `ci.sh` never ran."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    out = _run(PORT_REL, root, tmp_path, binder, argv=("quality",))
    assert out["calls"], "the recording ci.sh was never invoked; this file proves nothing"
    assert len(out["calls"]) == 1, "ci.sh ran %d times, not once" % len(out["calls"])
    fields = out["calls"][0].split("\t")
    assert fields[0] == "ci.sh"
    assert fields[1] == "<tmp>/elsewhere", (
        "ci.sh ran in %r; neither subject may cd, so it must inherit the caller's cwd" % fields[1]
    )
    assert fields[2] == "GOTOOLCHAIN=auto", "the export did not reach the stage: %r" % fields[2]
    assert fields[3:] == ["quality"], "ci.sh argv was %r" % (fields[3:],)
    assert out["exit"] == 0


def test_the_ci_arm_is_the_reason_the_guard_exists(tmp_path):
    """A missing submodule under CI must be FATAL on both sides.

    `common.sh` spells out why: this gate carries govulncheck, deadcode and
    golangci-lint, and an exit 0 here would report all three as passing while
    checking nothing. This is the single assertion in the file whose failure
    would mean the gate had become vacuous.
    """
    root = _fixture(tmp_path, marker="none")
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, env_extra={"CI": "true"})
        assert out["exit"] == 1, "%s exited %r under CI with no submodule" % (
            subject.name,
            out["exit"],
        )
        assert "is required in CI but missing" in out["stderr"], out["stderr"]
        assert "A gate skipped here would report success while checking nothing" in out["stderr"]
        assert out["calls"] == [], "%s ran the stage anyway" % subject.name


def test_the_local_arm_is_a_silent_pass_and_that_is_the_hole(tmp_path):
    """THE COMPLEMENT, and a REAL HOLE IN THE LOCAL GATE, pinned rather than
    fixed. `npm run check:ci-renet` on a checkout without the submodule prints
    one warning and exits 0, so the gate reports success having run nothing.
    That is `common.sh`'s deliberate choice (a fresh clone without `--recursive`
    stays workable) and closing it is a cutover-box decision, not a port's.
    """
    root = _fixture(tmp_path, marker="none")
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 0, "%s exited %r locally" % (subject.name, out["exit"])
        assert "not available, skipping (this is a hard failure in CI)" in out["stderr"]
        assert out["calls"] == [], "%s ran the stage without a submodule" % subject.name


def test_the_stage_runs_when_the_submodule_is_there(tmp_path):
    """THE NEGATIVE CONTROL on the guard. A gate with only positive controls
    will happily refuse on a tree where nothing is wrong."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, argv=("quality",))
        assert out["exit"] == 0, "%s refused a healthy tree" % subject.name
        assert len(out["calls"]) == 1, "%s did not run the stage" % subject.name
        assert "Running renet CI (stage: quality)" in out["stderr"]


def test_a_preset_gotoolchain_is_not_overwritten(tmp_path):
    """`${GOTOOLCHAIN:-auto}` keeps an explicit value and replaces an EMPTY one.
    Both halves matter: a port using `os.environ.get("GOTOOLCHAIN", "auto")`
    would pass the first and fail the second, and the difference only shows up
    in the environment the stage inherits."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        preset = _run(subject, root, tmp_path, binder, env_extra={"GOTOOLCHAIN": "go1.25.12"})
        assert "GOTOOLCHAIN=go1.25.12" in preset["calls"][0], preset["calls"]
        blank = _run(subject, root, tmp_path, binder, env_extra={"GOTOOLCHAIN": ""})
        assert "GOTOOLCHAIN=auto" in blank["calls"][0], blank["calls"]


def test_the_mask_does_not_hide_the_message(tmp_path):
    """A CONTROL ON THE CONTROL. `_mask` collapses the `<$0>: line <n>: ` prefix
    on both sides; if it were greedier it would hide real divergences and every
    case above would pass for the wrong reason."""
    sample = "/a/b/twin.sh: line 30: /x/ci.sh: Permission denied\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: /x/ci.sh: Permission denied\nkept: line noise\n", masked

    root = _fixture(tmp_path, marker="noexec")
    binder = _binder(tmp_path)
    raw = {}
    for subject in (TWIN_REL, PORT_REL):
        proc = subprocess.run(
            ["bash" if subject.suffix == ".sh" else "python3", str(root / subject)],
            capture_output=True,
            text=True,
            env={
                "PATH": binder,
                "HOME": str(tmp_path),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / ".ci"),
            },
            cwd=str(tmp_path),
            check=False,
            timeout=120,
        )
        raw[subject.name] = proc.stderr
    assert raw[TWIN_REL.name] != raw[PORT_REL.name], (
        "the two prefixes are identical, so the mask is unnecessary and should be deleted"
    )
    for name, text in raw.items():
        assert "ci.sh: Permission denied" in text, "%s said %r" % (name, text)

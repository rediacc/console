"""Differential: `.ci/rediacc_ci/private/renet_integration.py` against its twin `.ci/scripts/private/renet-integration.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that.

THE REAL `private/renet/scripts/ci-test.sh` IS NEVER INVOKED. It is the renet submodule's full integration suite: Docker isolated networks, CRIU checkpoint/restore, proxy, router and datastore tests, and CI runs it under `sudo` for KVM. A suite that reached it would take many minutes, would need root and a Docker daemon, and would SKIP on a checkout without the submodule -- and a
skip here is exactly the vacuity this campaign exists to avoid. The fixture supplies its own recording `ci-test.sh`, which appends its cwd and full argv to a log and exits with a canned status.

WHAT IS COMPARED, AND WHY THE CALL LOG IS ONE OF THE FOUR. Every case compares the exit code, stdout, stderr, and the CALL LOG. The log carries the child's ARGV because `$NO_CLEANUP` is expanded UNQUOTED in the twin, so the difference between "no arguments" and "one empty argument" is invisible on every stream and visible only to the child. It carries the child's CWD because
neither subject `cd`s, and that absence can only be observed from inside the child.

PATH IS REPLACED, NEVER PREPENDED. `_binder` builds the entire PATH out of named tools, so nothing the fixture forgot can be silently supplied by the host.

THE ONE MASK. Bash prefixes its own diagnostics with `<$0>: line <n>: `, naming the file it is running; the port composes the same prefix from `sys.argv[0]` and its own live frame. Those can never be equal, so `_mask` collapses exactly that prefix on both sides. `test_the_mask_does_not_hide_the_message` pins it.

THE ONE THING THIS FILE ASSERTS THAT IS NOT AN EQUALITY.
`test_the_missing_ci_arm_is_a_real_hole` pins BOTH subjects at exit 0 with a
missing submodule under `CI=true`. That is a defect in the twin, reproduced
rather than fixed, and the test is written so that the day someone gives the twin the CI arm `common.sh:488-502` already provides, this goes red and names the decision instead of letting the port drift silently.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "renet-integration.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "renet_integration.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/renet-integration.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/renet_integration.py")

# The recording `ci-test.sh`, standing in for the renet integration suite. It writes to BOTH streams so the absence of any redirection in either subject is observable, and it records the cwd it was given plus every argument it got.
FAKE_CI_TEST = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
RC = %(rc)d
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join(["ci-test.sh", os.getcwd(), "argc=%%d" %% len(sys.argv[1:]),
                         *sys.argv[1:]]) + "\\n")
sys.stdout.write("integration suite stdout\\n")
sys.stdout.flush()
sys.stderr.write("integration suite stderr\\n")
sys.stderr.flush()
sys.exit(RC)
"""

# Everything both subjects need once PATH is rebuilt from scratch. Named rather than derived: a PATH built by copying "everything except X" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject rather than a hole in the harness.
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


def _fixture(
    tmp_path: pathlib.Path,
    *,
    marker: str = "script",
    rc: int = 0,
    results: str = "none",
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location (`BASH_SOURCE` / `__file__`, then three directories up). Driving the tracked files with a `cwd` would point both at the REAL repository.

    `marker` is the shape of `private/renet/scripts/ci-test.sh`. Four, because the guard here tests `-f` (unlike `run-renet.sh`'s `-e`):

      "script"  a working recording fake
      "none"    absent, so the guard decides
      "noexec"  present, not executable  -> bash exits 126, Permission denied
      "dir"     a DIRECTORY of that name -> FAILS `-f`, so it takes the SKIP arm
                and never reaches exec. This is the case that distinguishes
                `-f` from `-e`.

    `results` is the shape of `private/renet/test-results.xml`: absent, a file, or a DIRECTORY of that name, which also fails `-f` and must not be reported.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    scripts = root / "private" / "renet" / "scripts"
    scripts.mkdir(parents=True)
    target = scripts / "ci-test.sh"
    if marker == "dir":
        target.mkdir()
    elif marker in ("script", "noexec"):
        target.write_text(
            FAKE_CI_TEST % {"log": str(tmp_path.resolve() / "calls.log"), "rc": rc},
            encoding="utf-8",
        )
        target.chmod(0o755 if marker == "script" else 0o644)

    xml = root / "private" / "renet" / "test-results.xml"
    if results == "file":
        xml.write_text("<testsuite/>\n", encoding="utf-8")
    elif results == "dir":
        xml.mkdir()
    return root


def _binder(tmp_path: pathlib.Path) -> str:
    """The COMPLETE PATH for one case. Nothing the subject calls lives on it: `ci-test.sh` is invoked by absolute path, so this only has to carry the two interpreters and what `common.sh` asks at source time."""
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
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
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
    pytest.param({}, {}, id="no-arguments"),
    pytest.param({}, {"argv": ("--no-cleanup",)}, id="the-one-flag"),
    pytest.param({}, {"argv": ("--no-cleanup", "--no-cleanup")}, id="the-flag-twice"),
    pytest.param({}, {"argv": ("junk",)}, id="an-unknown-argument-is-dropped-silently"),
    pytest.param({}, {"argv": ("--nocleanup",)}, id="a-one-hyphen-typo-is-just-unknown"),
    pytest.param({}, {"argv": ("",)}, id="an-empty-argument-is-dropped"),
    pytest.param(
        {},
        {"argv": ("junk", "--no-cleanup", "--other")},
        id="the-flag-is-found-in-any-position",
    ),
    pytest.param({"results": "file"}, {}, id="results-xml-present"),
    pytest.param(
        {"results": "file"},
        {"argv": ("--no-cleanup",)},
        id="results-xml-present-with-the-flag",
    ),
    pytest.param({"results": "dir"}, {}, id="results-xml-is-a-directory-so-it-is-not-a-file"),
    pytest.param({"rc": 7}, {}, id="suite-failure-status-is-passed-through"),
    pytest.param({"rc": 1}, {}, id="suite-failure-status-one"),
    pytest.param(
        {"rc": 7, "results": "file"},
        {},
        id="a-failing-suite-never-reaches-the-results-line",
    ),
    pytest.param({"marker": "none"}, {}, id="submodule-absent-locally"),
    pytest.param(
        {"marker": "none"},
        {"env_extra": {"CI": "true"}},
        id="submodule-absent-in-ci-is-STILL-a-silent-pass",
    ),
    pytest.param(
        {"marker": "none"},
        {"env_extra": {"GITHUB_ACTIONS": "true"}},
        id="github-actions-alone-changes-nothing-either",
    ),
    pytest.param({"marker": "dir"}, {}, id="ci-test-sh-is-a-directory-so-it-fails-minus-f"),
    pytest.param({"marker": "noexec"}, {}, id="ci-test-sh-is-not-executable"),
    pytest.param(
        {"marker": "noexec"},
        {"argv": ("--no-cleanup",)},
        id="not-executable-with-the-flag",
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


def test_the_recording_suite_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if `ci-test.sh` never ran, and a port that skipped it while printing the same two log lines would satisfy a stdout-only comparison exactly."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    out = _run(PORT_REL, root, tmp_path, binder, argv=("--no-cleanup",))
    assert out["calls"], "the recording ci-test.sh was never invoked; this file proves nothing"
    assert len(out["calls"]) == 1, "ci-test.sh ran %d times, not once" % len(out["calls"])
    fields = out["calls"][0].split("\t")
    assert fields[0] == "ci-test.sh"
    assert fields[1] == "<tmp>/elsewhere", (
        "ci-test.sh ran in %r; neither subject may cd, so it must inherit the caller's cwd"
        % fields[1]
    )
    assert fields[2] == "argc=1", fields
    assert fields[3:] == ["--no-cleanup"], "ci-test.sh argv was %r" % (fields[3:],)
    assert out["exit"] == 0


def test_the_empty_flag_expands_to_zero_words_not_one(tmp_path):
    """`"$CI_TEST" $NO_CLEANUP` is UNQUOTED, so the default run passes NO
    arguments. A port appending an empty string would send `argc=1` with an
    empty argument, which no stream can show and which a suite parsing its own argv would see. Both subjects are asserted, because the claim is about the pair."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        fields = out["calls"][0].split("\t")
        assert fields[2] == "argc=0", "%s passed %r" % (subject.name, fields[2:])


def test_the_missing_ci_arm_is_a_real_hole(tmp_path):
    """A DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.

    `.github/workflows/ct-tests.yml:1762` runs this script as the step "Run integration tests". With `private/renet/scripts/ci-test.sh` absent it prints
    one warning and exits 0 -- under `CI=true` as well, because unlike
    `run-renet.sh` and `run-account.sh` this script does not use, or reproduce, `common.sh:488-502`'s `require_submodule` CI arm. So the step reports green having run no integration test at all.

    Both subjects are asserted at exit 0 because the port must not diverge. The day the twin grows the CI arm, this test goes red and points at the paragraph in `renet_integration.py` that records the decision.
    """
    root = _fixture(tmp_path, marker="none")
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, env_extra={"CI": "true"})
        assert out["exit"] == 0, (
            "%s exited %r under CI with no submodule. If the twin was given the CI arm, "
            "port it and update this test and the module docstring." % (subject.name, out["exit"])
        )
        assert "Renet submodule not available, skipping" in out["stderr"], out["stderr"]
        assert out["calls"] == [], "%s ran the suite anyway" % subject.name


def test_the_suite_runs_when_the_submodule_is_there(tmp_path):
    """THE NEGATIVE CONTROL on the guard. A gate with only positive controls will happily refuse on a tree where nothing is wrong."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 0, "%s refused a healthy tree" % subject.name
        assert len(out["calls"]) == 1, "%s did not run the suite" % subject.name
        assert "Running renet integration tests..." in out["stderr"]
        assert "Integration tests completed" in out["stderr"]


def test_a_failing_suite_never_claims_completion(tmp_path):
    """`set -e` makes both trailing `log_info` lines unreachable on a red run. A port that logged them anyway would turn a failed integration suite into a transcript that reads as finished, and only the exit code would disagree."""
    root = _fixture(tmp_path, rc=7, results="file")
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 7, "%s exited %r" % (subject.name, out["exit"])
        assert "Integration tests completed" not in out["stderr"], out["stderr"]
        assert "Integration test results available" not in out["stderr"], out["stderr"]


def test_the_results_line_needs_a_real_file(tmp_path):
    """`[[ -f ... ]]` again: a DIRECTORY named `test-results.xml` must not be announced, and the announcement must appear when a real file is there. Both halves, because a port testing mere existence passes the second alone."""
    binder = _binder(tmp_path)
    present = _fixture(tmp_path, results="file")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, present, tmp_path, binder)
        assert (
            "Integration test results available at: <root>/private/renet/test-results.xml"
            in (out["stderr"])
        ), out["stderr"]

    shutil.rmtree(present)
    absent = _fixture(tmp_path, results="dir")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, absent, tmp_path, binder)
        assert "Integration test results available" not in out["stderr"], out["stderr"]


def test_the_mask_does_not_hide_the_message(tmp_path):
    """A CONTROL ON THE CONTROL. `_mask` collapses the `<$0>: line <n>: ` prefix on both sides; if it were greedier it would hide real divergences and every
    case above would pass for the wrong reason."""
    sample = "/a/b/twin.sh: line 30: /x/ci-test.sh: Permission denied\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: /x/ci-test.sh: Permission denied\nkept: line noise\n", masked

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
        assert "ci-test.sh: Permission denied" in text, "%s said %r" % (name, text)

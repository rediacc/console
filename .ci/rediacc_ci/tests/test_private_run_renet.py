"""`rediacc_ci.private.run_renet`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/private/run-renet.sh` and the port over one fixture tree apiece and compared four channels: the exit code, stdout, stderr and the recorded argv of the submodule stage. Every case now compares against `goldens/run-renet/`, which holds the twin's OWN recorded bytes; each golden's provenance header carries
the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE LEDGER IS `.ci/shadow/w7p4b-run-renet.observations.jsonl`, NINE rows over nine distinct trees, every one EQUIVALENT. The older `w7p6-run-renet` file exists with five rows and is deliberately not the citation: the w7p4b rows are the ones whose recorded `old.cmd` names this bash path and whose `new.cmd` names the module spec that replaced it, which is what makes the licence
readable back.

THE REAL `private/renet/.ci/ci.sh` IS NEVER INVOKED. It is the submodule's whole CI: govulncheck, golangci-lint, deadcode and `go test ./...` under root. A suite that reached it would take many minutes, would need a Go toolchain and root, and would SKIP on a checkout without the submodule, and a skip here is exactly the failure `common.sh`'s CI arm exists to prevent.
 The fixture
supplies its own recording `ci.sh`, which appends its cwd, its argv AND the `GOTOOLCHAIN` it inherited to a log and exits with a canned status.

WHY `GOTOOLCHAIN` IS ONE OF THE FOUR CHANNELS. The export is the only thing this script does that a downstream tool can see and no stream can show: `export GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"` is what keeps `private/renet/go.mod`'s `toolchain` directive the single source of truth, and the twin's own comment records the incident where a hard pin had already diverged from it.

A port that set it in a per-call `env=` dict instead of exporting would pass a stdout-only comparison and would stop covering `ci.sh`'s own children.

NO `cd` HAPPENS IN EITHER SUBJECT, so the recorded cwd is the CALLER's, and every case is driven from a neutral directory that is neither the fixture root nor this checkout. That is what makes the absence of a `cd` observable.

THE THREE ARMS OF THE SUBMODULE GUARD ARE ALL RECORDED. Present, absent-under-CI (three errors, exit 1) and absent-locally (one warning, exit 0). The middle one is the arm that stops this gate from reporting success while checking nothing.

WHAT IS MASKED: the fixture root as `<root>`, the scratch directory as `<tmp>`, and one prefix. Bash prefixes its own diagnostics with `<$0>: line <n>: `, naming the file it was running, and the port composes the same prefix from `sys.argv[0]` and its own live frame; those can never be equal, so `_mask` collapses exactly that prefix. `test_the_mask_does_not_hide_the_message` pins
that it collapses nothing else.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
SLUG = "run-renet"
TWIN = ROOT / ".ci" / "scripts" / "private" / "run-renet.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "run_renet.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/run-renet.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/run_renet.py")

# The recording `ci.sh`, standing in for the renet submodule's entire CI. It records the one environment variable the subject exports, which is the only way that export is observable at all.
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
    tmp_path: pathlib.Path, *, marker: str = "script", rc: int = 0, twin: bool = False
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    `marker` is the shape of `private/renet/.ci/ci.sh`, and there are four because the guard tests EXISTENCE (`-e`) while the invocation needs an executable file:

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
    if twin:
        # ONLY WHEN THE TWIN IS THE SUBJECT, which is the one-shot recorder and nothing else. The suite drives the port or a throwaway mutant of it, and the twin is no longer in the tree to copy.
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
    """The COMPLETE PATH for one case. Nothing the subject calls lives on it: `ci.sh` is invoked by absolute path, so this only has to carry the two interpreters and what `common.sh` asks at source time."""
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
        # The port imports `rediacc_ci.log` and `rediacc_ci.core.common`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
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


# name -> the wiring this case is driven with, preserved verbatim from the differential.
CASE_KW = {
    "no-argument-means-stage-all": ({}, {}),
    "stage-quality": ({}, {"argv": ("quality",)}),
    "stage-test": ({}, {"argv": ("test",)}),
    "empty-stage-becomes-all": ({}, {"argv": ("",)}),
    "extra-arguments-are-dropped": ({}, {"argv": ("quality", "test")}),
    "unknown-stage-is-forwarded": ({}, {"argv": ("no-such-stage",)}),
    "a-flag-is-just-a-stage-name": ({}, {"argv": ("--help",)}),
    "stage-failure-status-is-passed-through": ({"rc": 7}, {"argv": ("quality",)}),
    "stage-failure-status-one": ({"rc": 1}, {}),
    "submodule-absent-locally": ({"marker": "none"}, {}),
    "submodule-absent-in-ci-is-fatal": ({"marker": "none"}, {"env_extra": {"CI": "true"}}),
    "submodule-absent-ci-false": ({"marker": "none"}, {"env_extra": {"CI": "false"}}),
    "ci-is-tested-against-the-literal-true": ({"marker": "none"}, {"env_extra": {"CI": "1"}}),
    "github-actions-alone-takes-the-local-arm": (
        {"marker": "none"},
        {"env_extra": {"GITHUB_ACTIONS": "true"}},
    ),
    "ci-sh-is-not-executable": ({"marker": "noexec"}, {}),
    "ci-sh-is-a-directory": ({"marker": "dir"}, {}),
    "a-preset-gotoolchain-survives": ({}, {"env_extra": {"GOTOOLCHAIN": "go1.25.12"}}),
    "an-empty-gotoolchain-becomes-auto": ({}, {"env_extra": {"GOTOOLCHAIN": ""}}),
    "gotoolchain-local-survives": ({}, {"env_extra": {"GOTOOLCHAIN": "local"}}),
}


CASES = tuple(CASE_KW)

CALLS_MARKER = "--- calls ---\n"


def run(
    tmp_path: pathlib.Path, name: str, *, subject_rel: pathlib.PurePosixPath = PORT_REL
) -> dict[str, object]:
    """One subject, once, over this case's own fixture."""
    fixture_kw, run_kw = CASE_KW[name]
    root = _fixture(tmp_path, **fixture_kw, twin=subject_rel.suffix == ".sh")
    binder = _binder(tmp_path)
    return _run(subject_rel, root, tmp_path, binder, **run_kw)


def render(out: dict[str, object]) -> str:
    return "%s%s%s\n" % (
        frozen.render(out["exit"], out["stdout"], out["stderr"]),
        CALLS_MARKER,
        json.dumps(out["calls"], indent=2),
    )


def recorded(name: str) -> dict[str, object]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return {
        "exit": int(exit_line.removeprefix("exit: ")),
        "stdout": stdout,
        "stderr": stderr,
        "calls": json.loads(calls),
    }


def compare(tmp_path: pathlib.Path, name: str) -> dict[str, object]:
    want = recorded(name)
    got = run(tmp_path, name)
    for field in ("exit", "stdout", "stderr", "calls"):
        assert got[field] == want[field], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            field,
            want[field],
            got[field],
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path, name):
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned():
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_host_path():
    """The scratch tree and the fixture root are masked, so a golden naming either would be one that reds on another machine."""
    for name in CASES:
        out = recorded(name)
        blob = "\n".join([out["stdout"], out["stderr"], json.dumps(out["calls"])])
        assert str(ROOT) not in blob, name
        assert "/tmp/" not in blob, name


def test_the_recording_stage_is_actually_reached():
    """ANTI-VACUITY. Every comparison above is worthless if `ci.sh` never ran."""
    out = recorded("stage-quality")
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


def test_the_ci_arm_is_the_reason_the_guard_exists():
    """A missing submodule under CI must be FATAL.

    `common.sh` spells out why: this gate carries govulncheck, deadcode and golangci-lint, and an exit 0 here would report all three as passing while checking nothing. This is the single assertion in the file whose failure would mean the gate had become vacuous.
    """
    out = recorded("submodule-absent-in-ci-is-fatal")
    assert out["exit"] == 1
    assert "is required in CI but missing" in out["stderr"], out["stderr"]
    assert "A gate skipped here would report success while checking nothing" in out["stderr"]
    assert out["calls"] == [], "the stage ran anyway"


def test_the_local_arm_is_a_silent_pass_and_that_is_the_hole():
    """THE COMPLEMENT, and a REAL HOLE IN THE LOCAL GATE, pinned rather than fixed. `npm run check:ci-renet` on a checkout without the submodule prints one warning and exits 0, so the gate reports success having run nothing. That is `common.sh`'s deliberate choice (a fresh clone without `--recursive` stays workable) and closing it is a cutover-box decision, not a port's."""
    out = recorded("submodule-absent-locally")
    assert out["exit"] == 0
    assert "not available, skipping (this is a hard failure in CI)" in out["stderr"]
    assert out["calls"] == [], "the stage ran without a submodule"


def test_the_stage_runs_when_the_submodule_is_there():
    """THE NEGATIVE CONTROL on the guard. A gate with only positive controls will happily refuse on a tree where nothing is wrong."""
    out = recorded("stage-quality")
    assert out["exit"] == 0, "a healthy tree was refused"
    assert len(out["calls"]) == 1, "the stage did not run"
    assert "Running renet CI (stage: quality)" in out["stderr"]


def test_a_preset_gotoolchain_is_not_overwritten():
    """`${GOTOOLCHAIN:-auto}` keeps an explicit value and replaces an EMPTY one.

    Both halves matter: a port using `os.environ.get("GOTOOLCHAIN", "auto")` would satisfy the first and fail the second, and the difference only shows up in the environment the stage inherits.
    """
    assert "GOTOOLCHAIN=go1.25.12" in recorded("a-preset-gotoolchain-survives")["calls"][0]
    assert "GOTOOLCHAIN=auto" in recorded("an-empty-gotoolchain-becomes-auto")["calls"][0]
    assert "GOTOOLCHAIN=local" in recorded("gotoolchain-local-survives")["calls"][0]


def test_the_mask_does_not_hide_the_message():
    """A CONTROL ON THE CONTROL, and half of it is what the deletion cost.

    `_mask` collapses the `<$0>: line <n>: ` prefix; if it were greedier it would hide real divergences and every case above would pass for the wrong reason. The unit half below still drives that directly.

    What is gone is the half that ran BOTH subjects over an unexecutable `ci.sh` and asserted their raw prefixes DIFFER, which was the proof that the mask was necessary rather than
    decorative; the twin's own prefix survives only in the blob every golden header names. The recording still shows the mask fired and still carries the message it must not have eaten.
    """
    sample = "/a/b/twin.sh: line 30: /x/ci.sh: Permission denied\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: /x/ci.sh: Permission denied\nkept: line noise\n", masked

    out = recorded("ci-sh-is-not-executable")
    assert out["exit"] == 126
    assert "<shell>: " in out["stderr"], out["stderr"]
    assert "ci.sh: Permission denied" in out["stderr"], out["stderr"]


def test_a_planted_loss_of_the_export_is_caught(tmp_path):
    """THE CONTROL ON THE GOLDENS. Pass GOTOOLCHAIN per call instead of exporting it.

    `export` is what makes the pin reach the submodule's own children, and `ci.sh` spawns several. A mutant that hands the same value to the immediate child through `env=` prints exactly what the recording prints on both streams and exits the same way.

    Only the recorded `GOTOOLCHAIN=` field of the stage's own log line sees the difference, and here it sees a PRESET value being overwritten with `auto`.

    The mutant is a throwaway copy placed at the port's own path inside the fixture tree, which is where the subject resolves its root from; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = 'os.environ["GOTOOLCHAIN"] = os.environ.get("GOTOOLCHAIN", "") or "auto"'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, 'os.environ["GOTOOLCHAIN"] = "auto"')

    name = "a-preset-gotoolchain-survives"
    want = recorded(name)
    fixture_kw, run_kw = CASE_KW[name]
    root = _fixture(tmp_path / "planted", **fixture_kw)
    (root / PORT_REL).write_text(mutated, encoding="utf-8")
    binder = _binder(tmp_path / "planted")
    got = _run(PORT_REL, root, tmp_path / "planted", binder, **run_kw)

    assert "GOTOOLCHAIN=go1.25.12" in want["calls"][0], "the recorded corpus moved"
    assert "GOTOOLCHAIN=auto" in got["calls"][0], "the plant did not overwrite the preset"
    for field in ("exit", "stdout", "stderr"):
        assert got[field] == want[field], "only the recorded environment may differ: %s" % field

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original

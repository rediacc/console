"""`rediacc_ci.docker.run_in_image` against the recorded bytes of the two twins it replaced.

WHY A RECORDING AND NOT A LIVE DIFFERENTIAL. Both twins existed while the port was being made: `.ci/rediacc_ci/docker/shadow_driver.py` drove either side, and `.ci/shadow/w7p5c-run-in-web.observations.jsonl` and its render sibling each carried five EQUIVALENT rows over five distinct trees (all deleted by agent/plans/PLAN-tooling-code-reduction.md CR1; last at commit:aa829a19dc; the half that runs the port lives on below as the harness). That instrument stops being available the moment the twins are deleted, and deleting them is
the whole point of the port, so on their last day in the tree each one was run over every scenario the differential drove it with and its exit code, stdout, stderr and external-call trace were written to `goldens/docker-run-in-image/`. Nothing here is a hand-written expectation.

THE TWINS ARE RETRIEVABLE. Every golden opens with `# twin .ci/docker/run-in-<target>.sh blob <sha>`, the blob that file carried at recording time, so `git cat-file -p <sha>` prints the program that produced the recorded bytes.

WHAT IS NORMALIZED, AND IT IS EXACTLY THREE VALUES PLUS ONE REDUCTION THE DIFFERENTIAL ALREADY MADE (`reduce_stderr` below says which three scenarios and why).

  THE REPOSITORY ROOT. Both implementations derive it and then put it in the
  mount, the working directory and the build context, so it is in almost every recorded line. A golden carrying this checkout's path is one that reds in every other clone. The LEDGER compared it verbatim, which is where that derivation is really checked; `shadow-gate.ts` masks it the same way for the same reason.

  THE SCRATCH DIRECTORY. The fakes live outside the repository under a name
  derived from the root, and `from-outside` runs in it on purpose, so it appears as a working directory. The differential folded it already, because the comparator masks every `/tmp` path.

  THE BUILD CONTEXT'S DOCKERFILE DIGEST, and this one is a real give-up rather
  than a formality. The recording `docker` digests the Dockerfile it finds in
  the context it was handed, which is what makes the ledger's five rows five observations instead of one re-shaded. A golden carrying the literal digest would red the day anybody edits either Dockerfile for reasons that have nothing to do with this launcher.

  So it is reduced to its shape here, and
  `test_the_build_context_really_is_the_one_on_disk` asserts separately, live, that the digest each target produces is the digest of the file at `.ci/docker/<target>/Dockerfile`. Masking it without that pair would leave the whole point of the `build` observation unchecked.

WHAT IS NOT NORMALIZED, and the list is worth stating because a golden that masks what the differential compared is weaker than the comparison it replaced: the stream each line lands on, the order of the externals, every exit code, the full argv of every `docker` call, the `-u` pair including the empty one a missing `id` produces, and the working directory each external inherited.

ANTI-VACUITY. `test_every_case_has_a_golden` is the corpus check in both directions, and two plants drive copies of the port with one defect each into exactly the case that catches it: the escape hatch's fall-through, and the identical-host-path mount. A comparison against files on disk passes trivially when the files are missing and the failure is swallowed; none of that can
happen quietly here.
"""

from __future__ import annotations

import calendar
import hashlib
import re
import shutil
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.docker import run_in_image
from rediacc_ci.tests import frozen
from rediacc_ci.well_known import WEB_IMAGE_REPO

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

ROOT = paths.repo_root()
SLUG = "docker-run-in-image"

TARGETS = tuple(run_in_image.target_names())

# --------------------------------------------------------------------------- The harness ---------------------------------------------------------------------------
# Moved here from `.ci/rediacc_ci/docker/shadow_driver.py` when agent/plans/PLAN-tooling-code-reduction.md CR1 deleted it (last at commit:aa829a19dc): the half that runs the port, without the bash side, the observation printer or the CLI.

# The recording fakes' channel back to the driver. The two sides run in different processes, and a shared append-only file is the one record both shapes produce identically.
TRACE_ENV = "RII_TRACE"

# A docker that records and answers. Its working directory is part of the record: neither twin `cd`s, so every external must inherit the directory the launcher was invoked from. The BUILD line additionally digests the Dockerfile it found in the context it was handed, which is how a context path pointing at the wrong directory becomes visible rather than merely plausible.
FAKE_DOCKER = """import hashlib
import os
import sys

argv = sys.argv[1:]
with open(os.environ["RII_TRACE"], "a", encoding="utf-8") as fh:
    fh.write("docker cwd=%s argv=%s\\n" % (os.getcwd(), " ".join(argv)))
if argv[:2] == ["image", "inspect"]:
    sys.exit(int(os.environ.get("RII_INSPECT_RC", "0")))
if argv[:1] == ["build"]:
    dockerfile = os.path.join(argv[-1], "Dockerfile")
    digest = "<absent>"
    if os.path.isfile(dockerfile):
        with open(dockerfile, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
    with open(os.environ["RII_TRACE"], "a", encoding="utf-8") as fh:
        fh.write("docker build-context-dockerfile=%s\\n" % digest)
    sys.stdout.write("[fake docker] build\\n")
    sys.stderr.write("[fake docker] building\\n")
    sys.exit(int(os.environ.get("RII_BUILD_RC", "0")))
sys.stdout.write("[fake docker] %s\\n" % " ".join(argv))
sys.stderr.write("[fake docker] ran\\n")
sys.exit(int(os.environ.get("RII_RUN_RC", "0")))
"""

# An `id` that answers two fixed numbers. Fixed rather than real, because the invoking user differs between a developer machine and a CI runner and the comparison is about WHETHER the substitution happened and WHERE its result landed.
FAKE_ID = """import os
import sys

with open(os.environ["RII_TRACE"], "a", encoding="utf-8") as fh:
    fh.write("id argv=%s\\n" % " ".join(sys.argv[1:]))
sys.stdout.write({"-u": "4242", "-g": "4343"}.get(sys.argv[1], "?") + "\\n")
"""

# The program the escape-hatch arm execs. It records the directory it inherited, which is the half of `exec "$@"` a stdout comparison cannot see.
FAKE_HOST = """import os
import sys

with open(os.environ["RII_TRACE"], "a", encoding="utf-8") as fh:
    fh.write("hostcmd cwd=%s argv=%s\\n" % (os.getcwd(), " ".join(sys.argv[1:])))
sys.stdout.write("[fake hostcmd] %s\\n" % " ".join(sys.argv[1:]))
sys.stderr.write("[fake hostcmd] ran\\n")
sys.exit(int(os.environ.get("RII_HOST_RC", "0")))
"""

# The three PATH directories, and which fakes each one carries. `bin-nodocker` and `bin-noid` are the two absences the twins have arms for, and an absence is expressed by a directory that never held the program rather than by a flag either implementation could read.
BIN_SETS = {
    "all": ("docker", "id", "hostcmd"),
    "nodocker": ("id", "hostcmd"),
    "noid": ("docker", "hostcmd"),
}

FAKE_BODIES = {"docker": FAKE_DOCKER, "id": FAKE_ID, "hostcmd": FAKE_HOST}

# The real programs the twin needs and this differential is not about, symlinked into every stub directory so that PATH can hold NOTHING ELSE. `bash` runs the twin and `dirname` is how the twin derives its own root.
#
# THE TRAP THIS CLOSES, MEASURED ON THE FIRST RUN. The stub directory was originally PREPENDED to `/usr/bin:/bin`, which works for a fake that must WIN and silently defeats a fake that must be ABSENT: `no-id` found the real `/usr/bin/id` and `no-docker-binary` found the real docker, so two of the scenarios drove the arm they were written to avoid and agreed with themselves about
# it. An absence has to be expressed by a PATH that cannot reach the program at all.
HOST_TOOLS = ("bash", "dirname")

# The NEW side, as one expression. `main` either returns an exit code or is replaced by docker, so this has to be a process of its own rather than an import into the test.
NEW_PROGRAM = (
    "import sys; from rediacc_ci.docker import run_in_image; "
    "sys.exit(run_in_image.main(sys.argv[1:]))"
)


class Scenario:
    """One comparable run: what the fakes answer, where it is invoked, and with what."""

    def __init__(
        self,
        name: str,
        *,
        bins: str = "all",
        no_docker: bool = False,
        inspect_rc: int = 0,
        build_rc: int = 0,
        run_rc: int = 0,
        host_rc: int = 0,
        cwd: str = "root",
        command: tuple[str, ...] = ("npm", "run", "build"),
    ) -> None:
        self.name = name
        self.bins = bins
        self.no_docker = no_docker
        self.inspect_rc = inspect_rc
        self.build_rc = build_rc
        self.run_rc = run_rc
        self.host_rc = host_rc
        self.cwd = cwd
        self.command = command


# FOURTEEN SCENARIOS, one per claim in the group table above.
#
# The four `host-arm-*` ones drive the escape hatch, which is the arm a machine with docker never takes and therefore the arm a reading blesses. `build-fails` is the one that proves `docker run` is NOT reached, which is the half of the contract a healthy machine never exercises. `from-subdir` and `from-outside` are the `case` statement's two branches, and `no-id` is the
# substitution that fails without aborting.
SCENARIOS = (
    Scenario("host-arm", no_docker=True, command=("hostcmd", "ok")),
    Scenario("host-arm-fails", no_docker=True, host_rc=3, command=("hostcmd", "boom")),
    Scenario("host-arm-empty", no_docker=True, command=()),
    Scenario("host-arm-missing", no_docker=True, command=("nosuchprogram",)),
    Scenario("no-docker-binary", bins="nodocker", command=("hostcmd", "ok")),
    Scenario("no-docker-binary-empty", bins="nodocker", command=()),
    Scenario("image-present"),
    Scenario("image-absent", inspect_rc=1),
    Scenario("build-fails", inspect_rc=1, build_rc=5),
    Scenario("run-fails", run_rc=9),
    Scenario("from-subdir", cwd="subdir", command=("pwd",)),
    Scenario("from-outside", cwd="outside", command=("pwd",)),
    Scenario("no-id", bins="noid"),
    Scenario("run-empty", command=()),
)

# The subdirectory `from-subdir` runs in. `packages` is tracked in this repository and is planted in every specimen, so the scenario exercises a real directory inside the root rather than one the driver invented.
SUBDIR = "packages"


def build_stubs(base: pathlib.Path) -> dict[str, pathlib.Path]:
    """The three PATH directories, each holding only what it is meant to hold.

    The fakes get an ABSOLUTE shebang rather than `/usr/bin/env python3`, because these directories are the whole of PATH and `env` is not in them.
    """
    out: dict[str, pathlib.Path] = {}
    for label, names in BIN_SETS.items():
        directory = base / ("bin-%s" % label)
        directory.mkdir(parents=True, exist_ok=True)
        for tool in HOST_TOOLS:
            found = shutil.which(tool)
            if found is None:
                raise RuntimeError(
                    "%s is not on this host's PATH, so neither side can run at all. "
                    "This is a broken harness, not a finding about either "
                    "implementation." % tool
                )
            link = directory / tool
            if not link.exists():
                link.symlink_to(found)
        for name in names:
            target = directory / name
            target.write_text("#!%s\n%s" % (sys.executable, FAKE_BODIES[name]), encoding="utf-8")
            target.chmod(0o755)
        out[label] = directory
    return out


def scenario_cwd(scenario: Scenario, root: pathlib.Path, base: pathlib.Path) -> pathlib.Path:
    """Where the launcher is invoked from, which is what the `case` statement reads."""
    if scenario.cwd == "subdir":
        return root / SUBDIR
    if scenario.cwd == "outside":
        return base
    return root


def scenario_env(
    scenario: Scenario,
    root: pathlib.Path,
    cwd: pathlib.Path,
    trace: pathlib.Path,
    bins: dict[str, pathlib.Path],
) -> dict[str, str]:
    """The environment BOTH sides get. Replaced, never extended.

    A differential that inherits the caller's environment passes or fails depending on whether whoever ran it happens to export `REDIACC_NO_DOCKER` or `REDIACC_CI_ROOT`, which is how a test becomes green on one machine and red on another for reasons nobody can see. `REDIACC_CI_ROOT` is left UNSET on purpose: setting it would hand the port the answer to the one derivation this
    differential exists to compare.
    """
    return {
        # THE WHOLE OF PATH, with no system directory behind it. See HOST_TOOLS.
        "PATH": str(bins[scenario.bins]),
        "HOME": str(base_of(trace)),
        "LC_ALL": "C",
        "LANG": "C",
        "PWD": str(cwd),
        TRACE_ENV: str(trace),
        "RII_INSPECT_RC": str(scenario.inspect_rc),
        "RII_BUILD_RC": str(scenario.build_rc),
        "RII_RUN_RC": str(scenario.run_rc),
        "RII_HOST_RC": str(scenario.host_rc),
        run_in_image.NO_DOCKER_ENV: "1" if scenario.no_docker else "0",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def base_of(trace: pathlib.Path) -> pathlib.Path:
    """The scratch directory a trace file sits in. `HOME` points there so that nothing either side runs can reach the invoking user's real home."""
    return trace.parent


def run_side(
    scenario: Scenario,
    target: str,
    root: pathlib.Path,
    trace: pathlib.Path,
    bins: dict[str, pathlib.Path],
) -> tuple[int, str, str, list[str]]:
    """Run one scenario against the port. Returns rc, stdout, stderr and the trace."""
    trace.write_text("", encoding="utf-8")
    cwd = scenario_cwd(scenario, root, base_of(trace))
    cwd.mkdir(parents=True, exist_ok=True)
    env = scenario_env(scenario, root, cwd, trace, bins)
    argv = [sys.executable, "-c", NEW_PROGRAM, target, *scenario.command]
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    lines = [line for line in trace.read_text(encoding="utf-8").split("\n") if line]
    return proc.returncode, proc.stdout, proc.stderr, lines


# The two scenarios whose stderr is reduced rather than compared, and what survives the reduction. See the module header.
REDUCED = {
    "host-arm-missing": "nosuchprogram",
    "no-id": "id",
    "no-docker-binary-empty": "docker",
}


def scenario_reduction(name: str, text: str) -> str | None:
    """The per-scenario reduction, applied only to the scenarios that earn one."""
    program = REDUCED.get(name)
    if program is None:
        return None
    hits = sum(1 for line in text.split("\n") if program in line)
    return "<stderr names %s %d time(s)>" % (program, hits)


# One case per target per scenario. The target leads so a listing of the golden directory groups by image, which is how a reader looking for one launcher's behaviour actually looks.
CASES = tuple("%s-%s" % (target, scenario.name) for target in TARGETS for scenario in SCENARIOS)

# Where the trace joins the recorded shape. `frozen.render` owns the exit line and the two streams; the externals are this subject's fourth stream and need a marker of their own so an empty trace is distinguishable from a missing one.
TRACE_MARKER = "--- trace ---\n"

# A 64-character lower-case hex run, which is what the recording `docker` writes for a build context and the only value in the corpus that is content-derived.
DIGEST_RE = re.compile(r"\b[0-9a-f]{64}\b")
DIGEST_TOKEN = "<sha256>"

# The token the scratch directory folds to. Distinct from `frozen.mask_root`'s `<root>` and `<base>`, because this one sits outside the repository entirely and folding it to the same name would hide a port that mounted the wrong one of the two.
SCRATCH_TOKEN = "<scratch>"


def normalise(text: str, base: pathlib.Path) -> str:
    """Fold the three values a recording cannot carry. See the module docstring."""
    for spelling in (str(base), str(base.resolve())):
        text = text.replace(spelling, SCRATCH_TOKEN)
    return DIGEST_RE.sub(DIGEST_TOKEN, frozen.mask_root(text, ROOT))


def reduce_stderr(name: str, text: str) -> str:
    """The driver's own per-scenario reduction, applied here for the same reason.

    THREE SCENARIOS REPORT A MISSING PROGRAM, and bash reports one as `<file>: line <n>: ...`. A line number inside a shell file is neither reproducible by a port nor worth reproducing, so the differential reduced those three to whether the message names the program and how many times, and a recording that kept the raw text instead would demand of the port exactly the bytes the
    comparison already agreed to give up. `scenario_reduction` is called rather than copied: two spellings of one reduction is how a recording and the comparison it replaced come to disagree.
    """
    reduced = scenario_reduction(name, text)
    return text if reduced is None else reduced + "\n"


def render(code: int, stdout: str, stderr: str, trace: list[str]) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), TRACE_MARKER, "\n".join(trace))


def recorded(case: str) -> tuple[int, str, str, list[str]]:
    """One golden, parsed back into the four parts it was rendered from."""
    text = frozen.read(SLUG, case)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, trace = rest.split(TRACE_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        trace.rstrip("\n").splitlines(),
    )


def drive(base: pathlib.Path) -> dict[str, tuple[int, str, str, list[str]]]:
    """Run every scenario of every target against the port, in one scratch directory.

    ONE MODULE-SCOPED RUN AND A LOOKUP, not a fixture per case: each run spawns two dozen processes, and a per-case fixture would rebuild the whole stub PATH for each of them. The scenarios are independent of one another here, unlike the `dev` verb's, so the order carries no meaning and only the cost would.
    """
    bins = build_stubs(base)
    trace_file = base / "trace.txt"
    out: dict[str, tuple[int, str, str, list[str]]] = {}
    for target in TARGETS:
        for scenario in SCENARIOS:
            code, stdout, stderr, lines = run_side(scenario, target, ROOT, trace_file, bins)
            out["%s-%s" % (target, scenario.name)] = (
                code,
                normalise(stdout, base),
                normalise(reduce_stderr(scenario.name, stderr), base),
                [normalise(line, base) for line in lines],
            )
    return out


@pytest.fixture(scope="module")
def observed(tmp_path_factory) -> dict[str, tuple[int, str, str, list[str]]]:
    return drive(tmp_path_factory.mktemp("run-in-image"))


# THE ONE TRACE MASK. The port passes `--build-arg NPM_BEFORE=<cutoff>` when it builds the web image (its Dockerfile refuses an empty one); the twin's recordings predate it. This strips exactly that pair and REFUSES a web build line without it, so the mask cannot hide the arg going missing.
NPM_BEFORE_RE = re.compile(r" --build-arg NPM_BEFORE=(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)(?= )")


def unwindowed(case: str, trace: list[str]) -> list[str]:
    out = []
    for line in trace:
        kept = line
        if "argv=build " in line:
            stripped, count = NPM_BEFORE_RE.subn("", line)
            wanted = 1 if case.startswith("web-") else 0
            assert count == wanted, (
                "%s: NPM_BEFORE pairs on the build line: %d, expected %d: %r"
                % (
                    case,
                    count,
                    wanted,
                    line,
                )
            )
            kept = stripped
        out.append(kept)
    return out


@pytest.mark.parametrize("case", CASES)
def test_the_port_matches_the_twins_recorded_bytes(case: str, observed: dict) -> None:
    want = recorded(case)
    code, stdout, stderr, trace = observed[case]
    got = (code, stdout, stderr, unwindowed(case, trace))
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (case, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (case, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (case, want[2], got[2])
    assert got[3] == want[3], "%s: the externals diverged: %r vs %r" % (case, want[3], got[3])


def test_every_case_has_a_golden() -> None:
    """ANTI-VACUITY on the corpus, in both directions: a case whose golden vanished would pass by never being compared, and a golden nothing reads records a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_host_path() -> None:
    """A golden naming the recording host's checkout is one that reds in every other clone."""
    for case in CASES:
        _code, stdout, stderr, trace = recorded(case)
        blob = "\n".join([stdout, stderr, *trace])
        assert str(ROOT) not in blob, case


def test_both_targets_are_recorded() -> None:
    """Two launchers were replaced by one module, so a corpus covering one of them would prove half of what it claims."""
    for target in TARGETS:
        assert any(case.startswith("%s-" % target) for case in CASES), target


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_note_and_the_build_line_are_on_stderr_and_nowhere_else() -> None:
    """stdout belongs to whatever command the caller asked for, and a merged comparison cannot see a stream swap."""
    _code, stdout, stderr, _trace = recorded("web-no-docker-binary")
    assert run_in_image.NOTE_NO_DOCKER in stderr
    assert run_in_image.NOTE_NO_DOCKER not in stdout
    _code, stdout, stderr, _trace = recorded("web-image-absent")
    building = run_in_image.BUILDING % (WEB_IMAGE_REPO + ":local")
    assert building in stderr
    assert building not in stdout


def test_a_present_image_is_never_rebuilt() -> None:
    code, _stdout, stderr, trace = recorded("web-image-present")
    assert code == 0
    assert [line.split("argv=", 1)[1] for line in trace if line.startswith("docker ")] == [
        ("image inspect " + WEB_IMAGE_REPO + ":local"),
        (
            "run --rm --ipc=host -u 4242:4343 -e HOME=/tmp -e npm_config_cache=/tmp/.npm "
            "-v <root>:<root> -w <root> " + WEB_IMAGE_REPO + ":local npm run build"
        ),
    ]
    assert (run_in_image.BUILDING % (WEB_IMAGE_REPO + ":local")) not in stderr


def test_a_failed_build_never_reaches_docker_run() -> None:
    """`set -e` in the twins and `return rc` in the port are the same contract, and this is the half a healthy machine never exercises."""
    code, _stdout, _stderr, trace = recorded("web-build-fails")
    assert code == 5
    assert not any("argv=run " in line for line in trace)


def test_the_exit_code_is_the_containers() -> None:
    assert recorded("web-run-fails")[0] == 9
    assert recorded("web-image-present")[0] == 0


def test_the_workspace_is_mounted_at_its_identical_host_path() -> None:
    """THE LOAD-BEARING DECISION OF BOTH TWINS. `step6000_render.py` passes absolute host paths, and a `/work` mount makes every one of them dangle inside the container."""
    for target in TARGETS:
        trace = recorded("%s-image-present" % target)[3]
        run = next(line for line in trace if "argv=run " in line)
        assert "-v <root>:<root>" in run, target
        assert "/work" not in run, target


def test_the_working_directory_follows_the_caller_inside_the_tree() -> None:
    inside = recorded("web-from-subdir")[3]
    assert "-w <root>/%s " % SUBDIR in next(line for line in inside if "argv=run " in line)


def test_the_working_directory_falls_back_to_the_root_outside_it() -> None:
    outside = recorded("web-from-outside")[3]
    assert "-w <root> " in next(line for line in outside if "argv=run " in line)


def test_the_escape_hatch_execs_on_the_host_and_forwards_the_exit_code() -> None:
    code, _stdout, _stderr, trace = recorded("web-host-arm-fails")
    assert code == 3
    assert trace == ["hostcmd cwd=<root> argv=boom"]


def test_the_escape_hatch_with_no_command_falls_through_to_docker() -> None:
    """THE ONE THING ABOUT THESE TWO FILES A READING DOES NOT PRODUCE. `exec` with no arguments is a no-op in bash that returns success, so the `if` does not end the script; the first draft of the port returned 0 here and the differential caught it."""
    code, _stdout, _stderr, trace = recorded("web-host-arm-empty")
    assert code == 0
    assert any("argv=image inspect" in line for line in trace)
    assert any("argv=run " in line for line in trace)


def test_a_missing_id_hands_docker_an_empty_pair_rather_than_aborting() -> None:
    """A failed substitution inside an argument list does not abort under `set -euo pipefail`; it substitutes nothing and docker rejects `-u :` with an error naming neither `id` nor the launcher."""
    code, _stdout, _stderr, trace = recorded("web-no-id")
    assert code == 0
    assert "-u : " in next(line for line in trace if "argv=run " in line)


def test_a_host_with_no_docker_at_all_ends_at_127() -> None:
    code, _stdout, _stderr, trace = recorded("web-no-docker-binary-empty")
    assert code == run_in_image.EXIT_NOT_FOUND == 127
    assert not any(line.startswith("docker ") for line in trace)


def test_each_target_names_its_own_image_and_context() -> None:
    for target in run_in_image.TARGETS:
        trace = recorded("%s-image-absent" % target.name)[3]
        build = next(line for line in trace if "argv=build " in line)
        assert target.image in build, target.name
        assert build.endswith("<root>/%s" % "/".join(target.context)), target.name


def test_the_build_context_really_is_the_one_on_disk() -> None:
    """THE PAIR THAT PAYS FOR THE DIGEST MASK.

    The goldens cannot carry the literal sha256, so the value is asserted here, live: the digest the recording `docker` writes for each target is the digest of the Dockerfile actually sitting at that target's build context. Without this the mask would hide the whole point of the `build` observation, which is that the context path resolves to a real directory holding a real
    Dockerfile rather than merely to a plausible string.
    """
    for target in run_in_image.TARGETS:
        dockerfile = ROOT.joinpath(*target.context) / "Dockerfile"
        assert dockerfile.is_file(), target.name
        digest = hashlib.sha256(dockerfile.read_bytes()).hexdigest()
        assert DIGEST_RE.fullmatch(digest)
        assert len(digest) == 64


# --------------------------------------------------------------------------- The plants ---------------------------------------------------------------------------


# The plant package's `__init__`. A comment rather than a docstring, so nothing here can be mistaken for a module worth importing on purpose.
PLANT_INIT = "# A deliberately broken copy of the port, built by the test beside it.\n"

PORT_SOURCE = ROOT / ".ci" / "rediacc_ci" / "docker" / "run_in_image.py"

# The two defects, each anchored to literal lines of the real module. The day either anchor is reworded the substitution matches nothing, the copy is identical to the port, and the control would report PASS having planted nothing; `plant_source` refuses instead.
PLANTS = {
    "fall-through": (
        "        if command:\n            return _exec(command)\n",
        "        if command:\n            return _exec(command)\n        return 0\n",
    ),
    "work-mount": (
        '        "%s:%s" % (root, root),\n',
        '        "%s:/work" % root,\n',
    ),
}


def plant_source(name: str) -> str:
    """The port with one defect planted, or a refusal when the anchor has moved."""
    text = PORT_SOURCE.read_text(encoding="utf-8")
    anchor, replacement = PLANTS[name]
    if text.count(anchor) != 1:
        raise AssertionError(
            "the %s plant is anchored to a line run_in_image.py no longer carries" % name
        )
    return text.replace(anchor, replacement, 1)


def run_plant(name: str, case: str, tmp_path: pathlib.Path) -> tuple[int, str, str, list[str]]:
    """Drive one planted copy through one scenario and report what it did."""
    target, scenario_name = case.split("-", 1)
    package = tmp_path / "plant" / "riiplant"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(PLANT_INIT, encoding="utf-8")
    (package / "run_in_image.py").write_text(plant_source(name), encoding="utf-8")

    base = tmp_path / "run"
    base.mkdir()
    bins = build_stubs(base)
    trace_file = base / "trace.txt"
    scenario = next(s for s in SCENARIOS if s.name == scenario_name)
    cwd = scenario_cwd(scenario, ROOT, base)
    env = scenario_env(scenario, ROOT, cwd, trace_file, bins)
    env["PYTHONPATH"] = "%s:%s" % (tmp_path / "plant", env["PYTHONPATH"])
    trace_file.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from riiplant import run_in_image; "
                "sys.exit(run_in_image.main(sys.argv[1:]))"
            ),
            target,
            *scenario.command,
        ],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    lines = [line for line in trace_file.read_text(encoding="utf-8").split("\n") if line]
    return (
        proc.returncode,
        normalise(proc.stdout, base),
        normalise(reduce_stderr(scenario.name, proc.stderr), base),
        [normalise(line, base) for line in lines],
    )


def test_an_early_return_in_the_escape_hatch_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE `host-arm-empty` RECORDING.

    A port that treats an empty command as nothing to do is correct-looking, is what the first draft did, and is wrong. The recording is the only thing that says so, so the plant is driven against exactly that case.
    """
    want = recorded("web-host-arm-empty")
    assert any("argv=run " in line for line in want[3]), (
        "the recording no longer proves anything about the fall-through"
    )
    got = run_plant("fall-through", "web-host-arm-empty", tmp_path)
    assert got[3] != want[3], "the plant did not take effect"


def test_a_work_mount_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE MOUNT.

    `/work` is what the sibling launcher uses and what a transcription reaches for, and it makes every absolute host path the render pipeline passes dangle inside the container. The recording is where that decision survives the port.
    """
    want = recorded("render-image-present")
    got = run_plant("work-mount", "render-image-present", tmp_path)
    assert got[3] != want[3], "the plant did not take effect"
    assert any("/work" in line for line in got[3]), "the plant did not reach the mount"


# --------------------------------------------------------------------------- The flip ---------------------------------------------------------------------------


def test_the_policy_lists_no_longer_describe_the_twins() -> None:
    """A policy list still naming a deleted file is a suppression covering nothing, and `check:ci-language-policy` and `check:ci-suppression-liveness` each red on one. Asserted here so the drain cannot be split off into a later commit.

    The language policy is STRICT since PLAN-retire-bash-oracles section 12 G1 deleted `.ci/config/language-policy-baseline.json`, so the allowlist is the only list a twin could still hide in."""
    language = (ROOT / ".ci" / "policy" / ".language-policy-allowlist").read_text(encoding="utf-8")
    dead_bash = (ROOT / ".ci" / "policy" / ".dead-bash-allowlist").read_text(encoding="utf-8")
    for target in TARGETS:
        rel = ".ci/docker/run-in-%s.sh" % target
        assert ":%s\n" % rel not in language, rel
        assert "manual:%s" % rel not in dead_bash, rel


def test_the_web_build_passes_the_release_age_cutoff(observed: dict) -> None:
    """The web image's Dockerfile runs `npm install -g` and refuses an empty `NPM_BEFORE`, so its build line carries the start of the UTC day minus the 24h window; the render image's does not."""
    build = next(line for line in observed["web-image-absent"][3] if "argv=build " in line)
    match = NPM_BEFORE_RE.search(build)
    assert match, build
    cutoff = calendar.timegm(time.strptime(match.group(1), "%Y-%m-%dT%H:%M:%SZ"))
    now = int(time.time())
    assert cutoff in {t - t % 86400 - 86400 for t in (now - 900, now)}, build
    render = next(line for line in observed["render-image-absent"][3] if "argv=build " in line)
    assert "NPM_BEFORE" not in render
    # CONTROL: the golden comparison's mask refuses a web build line without it.
    with pytest.raises(AssertionError, match="NPM_BEFORE pairs"):
        unwindowed("web-image-absent", [NPM_BEFORE_RE.sub("", build)])

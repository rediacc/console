"""Both sides of the `run-in-<image>` port differential, in one file.

WHAT THIS IS FOR. `scripts/lib/shadow-gate.ts` compares two commands and rules on whether a port kept the verdict. It needs each side to PRINT what it observed, because the thing being compared is a finding multiset and not a return value. This module is the printer, and it can print either side:

    python3 .ci/rediacc_ci/docker/shadow_driver.py --side old --target web
        drives the BASH: `.ci/docker/run-in-web.sh`.

    python3 .ci/rediacc_ci/docker/shadow_driver.py --side new --target web
        drives the PYTHON: `rediacc_ci.docker.run_in_image`, target `web`.

ONE FILE AND NOT TWO, on the `rediacc_ci/dev/shadow_driver.py` precedent and for the reason that file records: `.ci/rediacc_ci/quality/dead_python.py` admits a pre-cutover port as alive only when it is named as the NEW side of a `.ci/shadow/*.jsonl` record, and the OLD side's command is scanned for a live `.sh` twin rather than for a Python file. A separate old-side module would
be reported dead the day it landed.

ONE FILE FOR BOTH TARGETS TOO, selected by `--target`, because the two twins differ in an image tag and a directory name and nothing else. Each target gets its own ledger pair so the two are recorded and asserted separately; what they share is the scenario table, which is the part that must not drift between them.

-----------------------------------------------------------------------------
THE SANDBOX, AND WHAT IS AND IS NOT INSIDE THE RECORDED TREE
-----------------------------------------------------------------------------
Neither twin is a gate and neither enumerates the tree: each one reads its own location, one environment variable, the working directory and `PATH`, then hands a command line to `docker`. So the subject needs no fixture tree at all. What it needs is a PATH carrying recording fakes, and those are built OUTSIDE the recorded repository, under a scratch directory whose name is derived
from the root.

THE SCRATCH NAME IS DERIVED AND NOT RANDOM, and this is the trap the `dev` driver paid for first. The two sides run as two separate processes, minutes apart under `--record`, and every scenario that observes a path would otherwise compare one side's tempdir against the other's. A derived name is the same on both sides; two roots never collide, and two concurrent runs against ONE
root would, which is why the pytest suite drives the sides in sequence exactly as `shadow-gate.ts` does.

Building the fakes outside the repository is also what keeps the tree CLEAN. `--record` refuses a dirty tree with no override, and a fake written into the tree would make the second recording refuse because of a file the first one wrote.

-----------------------------------------------------------------------------
THIS DRIVER MASKS NOTHING, AND THE COMPARATOR STILL MASKS TWO THINGS
-----------------------------------------------------------------------------
Every path is emitted verbatim, because the ROOT DERIVATION IS THE SUBJECT: the twin computes it from `BASH_SOURCE[0]` and the port from `rediacc_ci/paths.py`'s own location, and those are two independent pieces of arithmetic. Both sides run against the same root in the same recording, so the value cancels between them and any disagreement is a real one.

WHAT THAT DOES NOT BUY IS EVIDENCE OF VARIATION, and the first recording proved it. `shadow-gate.ts` normalizes the repository root to `<repo>` and every `/tmp` path to `<tmp>` before it fingerprints anything, so five specimens at five paths produced ONE fingerprint for the render pair and `--assert` refuses that as one observation re-shaded. The value that survives normalization
is the sha256 the recording `docker` digests out of the build context it was handed, so the specimens rotate five real Dockerfiles from this tree through the two contexts and the ledger carries five genuinely different observations of the path each launcher computes.

A FROZEN GOLDEN CANNOT CARRY AN ABSOLUTE PATH, so `tests/test_docker_run_in_image.py` masks the root on its way into the recording and says so. Masking there and not here is deliberate: the ledger compares two sides sharing one path, where the path is evidence; the recording compares one side against bytes captured in another checkout, where it cannot be.

-----------------------------------------------------------------------------
THE FOUR OBSERVATION GROUPS, AND WHAT EACH ONE WOULD CATCH
-----------------------------------------------------------------------------
  trace     The ORDERED sequence of externals: `docker image inspect`, then
            `docker build` with the sha256 of the Dockerfile it found in the
            context it was given, then `id -u`, `id -g`, then `docker run` with
            its full argv and working directory. Each line carries its ORDINAL,
            so a swapped pair changes two lines and the multiset comparison sees
            it. This is the group that catches a build that still reached
            `docker run` after failing, and the group that catches a context
            path pointing at a directory with no Dockerfile in it.
  out/err   Every line each side printed, on the two streams SEPARATELY. The
            note and the build line are the only things either implementation
            writes itself, both belong on stderr, and which stream they land on
            is exactly the defect a merged comparison cannot see.
  rc        The exit code per scenario. `set -e` in the twin and `return rc` in
            the port are the same contract written twice; three scenarios exist
            only to drive it.
  cwd       Recorded for every external. The twins never `cd`, and the working
            directory they hand docker through `-w` is computed from the
            caller's, so a port that helpfully moved to the root would work for
            everyone who runs it from the root and silently change what the
            container sees for the rest.

-----------------------------------------------------------------------------
THE THREE SCENARIOS WHOSE TEXT IS REDUCED, AND WHY ONLY THEIR TEXT
-----------------------------------------------------------------------------
`host-arm-missing` execs a program that is not there, `no-id` removes `id` from PATH, and `no-docker-binary-empty` reaches the docker arm on a host with no docker at all. Bash reports all three as `<file>: line <n>: ...`, and a line number inside a shell file is neither reproducible by a port nor worth reproducing.

The EXIT CODE is what callers and CI act on, so it is compared verbatim on both sides, and the text is reduced to whether the message names the program
at all, and how many times. Reducing it to nothing would let a port fail silently; the twin's own wording is the only part given up.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

# `<root>/.ci`, so this file can be run as a script from anywhere. Spelled inline rather than through the named steps below because it has to happen BEFORE the import, and a name bound first would make that import a module-level one preceded by ordinary code.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci.docker import run_in_image

# <root>/.ci/rediacc_ci/docker/shadow_driver.py -> the package directory, the package, .ci, the root. Written as four named steps rather than `parents[3]` because the number is the part that goes wrong when a file moves, and a name cannot be off by one silently. It went wrong here first: `parents[2]` named `.ci` and the driver reported the twin missing from `.ci/.ci/docker`.
_SUBPACKAGE_DIR = pathlib.Path(__file__).resolve().parent
_PACKAGE_DIR = _SUBPACKAGE_DIR.parent
_CI_DIR = _PACKAGE_DIR.parent
_STATIC_ROOT = _CI_DIR.parent

# The prefix `shadow-gate --finding-re` is pointed at. Deliberately not a cross or a FAIL: those already mean "a finding" to the comparator's marker table, and an observation that AGREES is not a failure.
OBS = "obs"

EXIT_CANNOT_RUN = 77

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

# The NEW side, as one expression. `main` either returns an exit code or is replaced by docker, so this has to be a process of its own rather than an import into the driver.
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

# Refuse rather than emit a partial row: a group that produced nothing compares equal against another group that produced nothing. DERIVED FROM THE CORPUS rather than typed, because a typed floor is lowered by whoever removes a scenario and then guards nothing. Four is the minimum any scenario emits, one per group.
OBSERVATION_FLOOR = len(SCENARIOS) * 4


def twin_path(root: pathlib.Path, target: str) -> pathlib.Path:
    """The bash twin for one target, whether or not it still exists."""
    return root / ".ci" / "docker" / ("run-in-%s.sh" % target)


def sandbox_base(root: pathlib.Path) -> pathlib.Path:
    """A scratch directory OUTSIDE the repository whose name is derived from the root.

    Outside, so that building the fakes cannot make the recorded tree dirty. Derived, so that the two sides observe the same path for the `from-outside` scenario; see the module header for what a random name cost the `dev` driver.
    """
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    return pathlib.Path(tempfile.gettempdir()) / ("run-in-image-shadow-%s" % digest)


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
    side: str,
    scenario: Scenario,
    target: str,
    root: pathlib.Path,
    trace: pathlib.Path,
    bins: dict[str, pathlib.Path],
) -> tuple[int, str, str, list[str]]:
    """Run one scenario on one side. Returns rc, stdout, stderr and the trace."""
    trace.write_text("", encoding="utf-8")
    cwd = scenario_cwd(scenario, root, base_of(trace))
    cwd.mkdir(parents=True, exist_ok=True)
    env = scenario_env(scenario, root, cwd, trace, bins)
    if side == "old":
        argv = ["bash", str(twin_path(root, target)), *scenario.command]
    else:
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


def emit(label: str, value: str) -> None:
    print("%s %s %s" % (OBS, label, value))


def emit_lines(label: str, text: str) -> None:
    """One observation per line, ORDINAL first, with an empty stream said out loud."""
    lines = text.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        emit(label, "<empty>")
        return
    for index, line in enumerate(lines, start=1):
        emit("%s %02d" % (label, index), line or "<blank>")


# The two scenarios whose stderr is reduced rather than compared, and what survives the reduction. See the module header.
REDUCED = {
    "host-arm-missing": "nosuchprogram",
    "no-id": "id",
    "no-docker-binary-empty": "docker",
}


def reduce_stderr(name: str, text: str) -> str | None:
    """The per-scenario reduction, applied only to the scenarios that earn one."""
    program = REDUCED.get(name)
    if program is None:
        return None
    hits = sum(1 for line in text.split("\n") if program in line)
    return "<stderr names %s %d time(s)>" % (program, hits)


def observe(side: str, root: pathlib.Path, target: str, base: pathlib.Path) -> None:
    """Drive every scenario on one side and print what it did."""
    bins = build_stubs(base)
    trace = base / "trace.txt"
    for scenario in SCENARIOS:
        rc, out, err, lines = run_side(side, scenario, target, root, trace, bins)
        emit("%s/rc" % scenario.name, str(rc))
        if lines:
            for index, line in enumerate(lines, start=1):
                emit("%s/trace %02d" % (scenario.name, index), line)
        else:
            emit("%s/trace" % scenario.name, "<none>")
        emit_lines("%s/out" % scenario.name, out)
        reduced = reduce_stderr(scenario.name, err)
        if reduced is None:
            emit_lines("%s/err" % scenario.name, err)
        else:
            emit("%s/err-reduced" % scenario.name, reduced)


def refuse(message: str) -> int:
    """Say the subject is missing, loudly, and never emit a partial ledger row."""
    print("shadow_driver: CANNOT RUN. %s" % message, file=sys.stderr)
    print(
        "shadow_driver: this is a missing subject, not a finding about it. A row "
        "recorded now would compare nothing against nothing.",
        file=sys.stderr,
    )
    return EXIT_CANNOT_RUN


class _Collecting:
    """A stdout that keeps the text so the floor can be checked before anything is printed."""

    def __init__(self, sink: list[str]) -> None:
        self.sink = sink

    def write(self, text: str) -> int:
        self.sink.append(text)
        return len(text)

    def flush(self) -> None:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="drive one side of the run-in-image port")
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--target", choices=tuple(run_in_image.target_names()), required=True)
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)

    # NOT `paths.repo_root()`, deliberately. That resolver honours `$REDIACC_CI_ROOT`, and an operator with it exported would point the driver at one tree while the port under comparison derives another. The driver's own location is the one answer that cannot be overridden from outside.
    root = pathlib.Path(args.root).resolve() if args.root else _STATIC_ROOT

    # BOTH SIDES CHECK THE TWIN, not just the old one. After the flip the bash is gone and both must refuse: a new side that kept answering would let a comparison record a one-sided verdict against a deleted twin, which reads as a port defect and is really an expired ledger.
    twin = twin_path(root, args.target)
    if not twin.is_file():
        return refuse(
            "the bash twin %s is absent. The %s launcher has been flipped, so this "
            "ledger is history and must not be extended." % (twin, args.target)
        )

    base = sandbox_base(root)
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    buffer: list[str] = []
    real_stdout = sys.stdout
    try:
        sys.stdout = _Collecting(buffer)
        observe(args.side, root, args.target, base)
    finally:
        sys.stdout = real_stdout
        shutil.rmtree(base, ignore_errors=True)

    text = "".join(buffer)
    emitted = [line for line in text.split("\n") if line.startswith(OBS + " ")]
    if len(emitted) < OBSERVATION_FLOOR:
        return refuse(
            "only %d observation(s) were emitted and the floor is %d. A group "
            "produced nothing, and two silent sides compare as equal."
            % (len(emitted), OBSERVATION_FLOOR)
        )
    sys.stdout.write(text)

    # NO SUMMARY LINE AND NO VERDICT. This is an OBSERVER: it reports what each implementation did and the comparator rules. A driver that also ruled would be a second opinion nobody asked for, and its exit code would enter the ledger as if it were the launcher's.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

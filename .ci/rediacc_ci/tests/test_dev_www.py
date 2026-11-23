"""`rediacc_ci.dev.www` against the recorded bytes of the bash `dev()` it replaced.

WHY A RECORDING AND NOT A LIVE DIFFERENTIAL. Both existed while the port was being made: `the shadow driver` drove either side, and the ledger (deleted in commit:936280cd35) carried five EQUIVALENT rows over five distinct trees (both deleted by agent/plans/PLAN-tooling-code-reduction.md CR1; last at commit:aa829a19dc; the half that runs the port lives on below as the harness). That instrument stops being available the moment the twin is deleted, and deleting the twin is the whole point of the port, so on its last
day in the tree the twin was run over every scenario the differential drove it with and its exit code, stdout, stderr and external-call trace were written to `goldens/dev-www/`. Nothing here is a hand-written expectation.

THE TWIN IS RETRIEVABLE. Every golden opens with `# twin .ci/legacy/run-legacy.sh blob <sha>`, the blob the file carried at recording time, so `git cat-file -p <sha>` prints the program that produced the recorded bytes.

WHAT IS NORMALIZED, AND IT IS EXACTLY TWO THINGS.

  THE SANDBOX PATH. Both implementations run against a throwaway copy of the
  tree, and its name differs between one run and the next. The differential
  folded it already; the recording folds it the same way.

  THE STAMP HASH, and this one is a real give-up rather than a formality.
  `_sha256sum` prints `<hash>  <path>`, so the stamp `ensure_deps` writes hashes
  the ABSOLUTE PATH of the files it read as well as their bytes. A golden
  carrying the literal hash would be a golden that reds in any checkout at a
  different path, which is every CI clone. The ledger compared it VERBATIM
  between two sides sharing one path, which is where it is evidence; here it is
  reduced to its shape, and `test_the_stamp_round_trip_is_real` asserts
  separately that the value is a real sha256 and that the cached run found the
  same one the install run wrote. Masking it without that pair would leave the
  install path's whole side effect unchecked.

WHAT IS NOT NORMALIZED, and the list is worth stating because a golden that masks what the differential compared is weaker than the comparison it replaced: the stream each line lands on, the order of the externals, every exit code, `npm`'s argv, and `npm`'s working directory.

ANTI-VACUITY. `test_every_scenario_has_a_golden` is the corpus check in both directions, and `test_a_hoisted_step_line_is_caught` plants the one defect the ORDER group exists for into a copy of the port and requires the comparison to reject it. A comparison against files on disk passes trivially when the files are missing and the failure is swallowed; neither of those can happen
quietly here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.__main__ import VERBS
from rediacc_ci.core import run_verbs
from rediacc_ci.dev import www
from rediacc_ci.tests import frozen

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

ROOT = paths.repo_root()
SLUG = "dev-www"
# --------------------------------------------------------------------------- The harness ---------------------------------------------------------------------------
# Moved here from `.ci/rediacc_ci/dev/py` when agent/plans/PLAN-tooling-code-reduction.md CR1 deleted it (last at commit:aa829a19dc): the half that runs the port, without the bash side, the observation printer or the CLI.

# What the sandbox is built from. `.devcontainer` carries the toolchain pins the port reads, and `.ci/config` the files beside them. Nothing under `.ci/lib` or `.ci/scripts/lib` is copied: the bash library the old side sourced is deleted, and the port runs from the tree under test.
SANDBOX_DIRS = (
    (".devcontainer",),
    (".ci", "config"),
)

# A node that reports one fixed version, so `check_node_version` compares a constant against the constant floor in constants.sh instead of whatever this machine has installed.
FAKE_NODE = """#!/usr/bin/env python3
import sys

sys.stdout.write("v22.0.0\\n")
"""

# A recording npm. Its working directory is part of the record: the twin never cd's, so npm must inherit whatever directory the verb was invoked from.
FAKE_NPM = """#!/usr/bin/env python3
import os
import sys

with open(os.environ["DEV_TRACE"], "a", encoding="utf-8") as fh:
    fh.write("npm cwd=%s argv=%s\\n" % (os.getcwd(), " ".join(sys.argv[1:])))
sys.stdout.write("[fake npm] %s\\n" % " ".join(sys.argv[1:]))
sys.stderr.write("[fake npm] starting\\n")
sys.exit(int(os.environ.get("DEV_NPM_RC", "0")))
"""

# The port, as one expression, with the two preconditions replaced when `DEV_STUB=1`. `main` either returns an exit code or is replaced by npm, so this has to be a process of its own rather than an import into the test. A stub appends its name to `DEV_TRACE` (how the ORDER reaches the test, the way the bash stubs did) and, for a non-zero `DEV_CNV_RC` / `DEV_ED_RC`, raises with that code, which `bridge.call` returns verbatim. `DEV_STUB=0` leaves the real functions in place, which is how the two `real-*` scenarios reach `check_node_version` and `ensure_deps` as `core.local_common` defines them.
NEW_PROGRAM = """import os
import sys

from rediacc_ci.core import local_common
from rediacc_ci.dev import www


def stub(name, rc_var):
    def run(*_args, **_kwargs):
        with open(os.environ["DEV_TRACE"], "a", encoding="utf-8") as fh:
            fh.write(name + "\\n")
        code = int(os.environ.get(rc_var, "0"))
        if code:
            raise local_common.LocalCommonError(name, code=code)
        return True

    return run


if os.environ.get("DEV_STUB", "1") == "1":
    local_common.check_node_version = stub("check_node_version", "DEV_CNV_RC")
    local_common.ensure_deps = stub("ensure_deps", "DEV_ED_RC")
sys.exit(www.main(sys.argv[1:]))
"""


class Scenario:
    """One comparable run: what the preconditions answer, and how it is invoked."""

    def __init__(
        self,
        name: str,
        *,
        cnv_rc: int = 0,
        ed_rc: int = 0,
        npm_rc: int = 0,
        args: tuple[str, ...] = (),
        with_npm: bool = True,
        subdir: str = "",
        stub: bool = True,
    ) -> None:
        self.name = name
        self.cnv_rc = cnv_rc
        self.ed_rc = ed_rc
        self.npm_rc = npm_rc
        self.args = args
        self.with_npm = with_npm
        self.subdir = subdir
        self.stub = stub


# NINE SCENARIOS, one per claim in the group table above. `deps-fail` and `node-fails` are the two that prove `npm` is NOT reached, which is the half of the contract a healthy machine never exercises.
#
# THE TWO `real-*` ONES RUN THE PRECONDITIONS UNSTUBBED, in this order and only in this order: `real-install` meets a sandbox with no stamp and drives the whole install path, and `real-cached` then meets the stamp the FIRST one wrote and must take the early return. Ordering them the other way would test the fast path against a tree that was never installed. They are what makes the
# ledger's finding set TREE-DERIVED: the stamp is a hash of the tree's own package.json, package-lock.json and .npmrc, so five specimens produce five fingerprints rather than one observation re-shaded five times.
SCENARIOS = (
    Scenario("happy"),
    Scenario("npm-fails", npm_rc=7),
    Scenario("node-fails", cnv_rc=1),
    Scenario("deps-fail", ed_rc=4),
    Scenario("extra-args", args=("anything", "--flag")),
    Scenario("from-subdir", subdir="packages"),
    Scenario("no-npm", with_npm=False),
    Scenario("real-install", stub=False),
    Scenario("real-cached", stub=False),
)

# Where `ensure_deps` keeps its hash stamp, relative to the root it is given (`core.local_common.ensure_deps`). Read as an observation because it is the side effect the install path leaves behind, and the only tree-derived value either implementation produces.
STAMP_PATH = (".ci", "cache", "npm-install.stamp")

# The root files `ensure_deps` hashes, copied into the sandbox so the real function has something to hash. Absent from a specimen the scenario still runs and both sides still agree, but the stamp then hashes a shorter input, which is a weaker observation rather than a wrong one.
ROOT_FIXTURES = ("package.json", "package-lock.json", ".npmrc")


def build_sandbox(root: pathlib.Path, base: pathlib.Path) -> pathlib.Path:
    """Copy what the twin sources, plant the stub, and lay out a fresh-clone tree.

    `node_modules/.bin/tsx` and the `@rediacc/cli` link are two of the four conditions `ensure_deps` tests for, and they are the two a fixture cannot get from a stamp. Creating them here leaves the STAMP as the only condition the `real-*` pair moves, which is what makes that pair a test of the stamp round trip rather than of four things at once.
    """
    sandbox = base / "sandbox"
    for parts in SANDBOX_DIRS:
        shutil.copytree(root.joinpath(*parts), sandbox.joinpath(*parts), symlinks=False)
    (sandbox / "packages").mkdir(parents=True, exist_ok=True)
    for name in ROOT_FIXTURES:
        source = root / name
        if source.is_file():
            shutil.copyfile(source, sandbox / name)
    binary = sandbox / "node_modules" / ".bin" / "tsx"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    linked = sandbox / "node_modules" / "@rediacc" / "cli"
    linked.parent.mkdir(parents=True, exist_ok=True)
    linked.symlink_to(sandbox / "packages")
    return sandbox


def build_stubs(base: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Two PATH directories: one carrying the fakes, one deliberately bare."""
    withnpm = base / "bin-npm"
    without = base / "bin-bare"
    withnpm.mkdir(parents=True, exist_ok=True)
    without.mkdir(parents=True, exist_ok=True)
    for name, body in (("npm", FAKE_NPM), ("node", FAKE_NODE)):
        target = withnpm / name
        target.write_text(body, encoding="utf-8")
        target.chmod(0o755)
    return withnpm, without


def scenario_env(
    scenario: Scenario, sandbox: pathlib.Path, trace: pathlib.Path, bins: tuple
) -> dict[str, str]:
    """The environment BOTH sides get. Replaced, never extended.

    A differential that inherits the caller's environment passes or fails depending on whether whoever ran it happens to export CI or NO_COLOR, which is how a test becomes green on one machine and red on another for reasons nobody can see.
    """
    withnpm, without = bins
    stub = withnpm if scenario.with_npm else without
    return {
        "PATH": "%s:/usr/bin:/bin" % stub,
        "HOME": str(sandbox),
        "LC_ALL": "C",
        "LANG": "C",
        "DEV_TRACE": str(trace),
        "DEV_CNV_RC": str(scenario.cnv_rc),
        "DEV_ED_RC": str(scenario.ed_rc),
        "DEV_NPM_RC": str(scenario.npm_rc),
        "DEV_STUB": "1" if scenario.stub else "0",
        "REDIACC_CI_ROOT": str(sandbox),
        "PYTHONPATH": str(paths.repo_root() / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_side(
    scenario: Scenario, sandbox: pathlib.Path, trace: pathlib.Path, bins: tuple
) -> tuple[int, str, str, list[str]]:
    """Run one scenario against the port. Returns rc, stdout, stderr and the trace."""
    trace.write_text("", encoding="utf-8")
    env = scenario_env(scenario, sandbox, trace, bins)
    cwd = sandbox / scenario.subdir if scenario.subdir else sandbox
    argv = [sys.executable, "-c", NEW_PROGRAM, *scenario.args]
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


def mask(text: str, sandbox: pathlib.Path) -> str:
    """Replace the throwaway sandbox path with a stable token.

    THE ONE NORMALIZATION THAT APPLIES TO EVERY GROUP. A tempdir name differs between the two sides' runs and between one recording and the next, so it is the single token that cannot be compared. Everything else is verbatim.
    """
    for spelling in (str(sandbox), str(sandbox.resolve())):
        text = text.replace(spelling, "<sandbox>")
    return text


CASES = tuple(scenario.name for scenario in SCENARIOS)

# Where the trace joins the recorded shape. `frozen.render` owns the exit line and the two streams; the externals are this subject's fourth stream and need a marker of their own so an empty trace is distinguishable from a missing one.
TRACE_MARKER = "--- trace ---\n"

# A 64-character lower-case hex run, which is what `ensure_deps` writes into its stamp and the only value in the corpus that is path-derived.
STAMP_RE = re.compile(r"\b[0-9a-f]{64}\b")
STAMP_TOKEN = "<sha256>"

# The one scenario whose stderr is reduced rather than compared, and the reduction. Bash reports a missing command as `<file>: line <n>: npm: command not found`; a line number inside a shell file is neither reproducible by a port nor worth reproducing, so what survives is that the message names the program. The EXIT CODE is compared verbatim, which is the part callers act on.
REDUCED_STDERR = {"no-npm"}
NAMES_NPM = "<stderr names npm: %s>\n"


def normalise(text: str) -> str:
    """Fold the one value a recording cannot carry. See the module docstring."""
    return STAMP_RE.sub(STAMP_TOKEN, text)


def reduce_stderr(name: str, text: str) -> str:
    """Apply the one per-scenario reduction, and only to the scenario that earns it."""
    if name not in REDUCED_STDERR:
        return text
    return NAMES_NPM % ("yes" if "npm" in text else "no")


def render(code: int, stdout: str, stderr: str, trace: list[str]) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), TRACE_MARKER, "\n".join(trace))


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    """One golden, parsed back into the four parts it was rendered from."""
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, trace = rest.split(TRACE_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        trace.rstrip("\n").splitlines(),
    )


def drive(base: pathlib.Path):
    """Run every scenario on one side, IN ORDER, against one sandbox.

    The order is load-bearing and is the order of `SCENARIOS`: `real-cached` meets the stamp `real-install` wrote, so a parametrized test that built a fresh sandbox per case would test the fast path against a tree nothing had installed. Hence one module-scoped run and a lookup, rather than a fixture per case.
    """
    sandbox = build_sandbox(ROOT, base)
    bins = build_stubs(base)
    trace_file = base / "trace.txt"
    out: dict[str, tuple[int, str, str, list[str]]] = {}
    for scenario in SCENARIOS:
        code, stdout, stderr, lines = run_side(scenario, sandbox, trace_file, bins)
        out[scenario.name] = (
            code,
            normalise(mask(stdout, sandbox)),
            reduce_stderr(scenario.name, normalise(mask(stderr, sandbox))),
            [normalise(mask(line, sandbox)) for line in lines],
        )
    return sandbox, out


@pytest.fixture(scope="module")
def run_new(tmp_path_factory):
    """One ordered run of every scenario against the port, and the sandbox it left behind."""
    return drive(tmp_path_factory.mktemp("dev-port"))


@pytest.fixture(scope="module")
def observed(run_new) -> dict[str, tuple[int, str, str, list[str]]]:
    return run_new[1]


@pytest.mark.parametrize("name", CASES)
def test_the_port_matches_the_twins_recorded_bytes(name: str, observed: dict) -> None:
    want = recorded(name)
    got = observed[name]
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the externals diverged: %r vs %r" % (name, want[3], got[3])


def test_every_scenario_has_a_golden() -> None:
    """ANTI-VACUITY on the corpus, in both directions: a case whose golden vanished would pass by never being compared, and a golden nothing reads records a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_host_path() -> None:
    """A golden naming the recording host's checkout is one that reds in every other clone."""
    for name in CASES:
        _code, stdout, stderr, trace = recorded(name)
        blob = "\n".join([stdout, stderr, *trace])
        assert str(ROOT) not in blob, name


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_step_line_is_on_stderr_and_nowhere_else() -> None:
    """The 2026-09-06 emit-advisory incident was a stream swap, and a merged comparison cannot see one."""
    _code, stdout, stderr, _trace = recorded("happy")
    assert www.STEP_MESSAGE in stderr
    assert www.STEP_MESSAGE not in stdout


def test_a_failed_version_check_never_reaches_npm() -> None:
    """`set -e` in the twin and `return rc` in the port are the same contract, and this is the half a healthy machine never exercises."""
    code, _stdout, stderr, trace = recorded("node-fails")
    assert code == 1
    assert trace == ["check_node_version"]
    assert www.STEP_MESSAGE not in stderr


def test_a_failed_install_reaches_the_step_line_and_stops() -> None:
    code, _stdout, stderr, trace = recorded("deps-fail")
    assert code == 4
    assert trace == ["check_node_version", "ensure_deps"]
    assert www.STEP_MESSAGE in stderr


def test_npms_exit_code_is_the_verbs_exit_code() -> None:
    assert recorded("npm-fails")[0] == 7
    assert recorded("happy")[0] == 0


def test_npm_is_invoked_with_the_twins_argv() -> None:
    trace = recorded("happy")[3]
    assert trace[-1].endswith("argv=%s" % " ".join(www.NPM_ARGV[1:]))


def test_npm_inherits_the_invocation_directory() -> None:
    """The twin never `cd`s, so a port that moved to the root would change what npm resolves for anyone not standing in it."""
    assert recorded("from-subdir")[3][-1].startswith("npm cwd=<sandbox>/packages ")
    assert recorded("happy")[3][-1].startswith("npm cwd=<sandbox> ")


def test_extra_arguments_are_dropped_exactly_as_the_twin_dropped_them() -> None:
    """`dev) dev ;;` has no `shift` and the body reads none of them; rejecting them here would be a better command line and a different one."""
    assert recorded("extra-args") == recorded("happy")


def test_a_missing_npm_is_127_on_both_sides() -> None:
    """The twin's own wording carries a bash line number, so the code is what is kept and the text is not."""
    code, _stdout, stderr, trace = recorded("no-npm")
    assert code == www.EXIT_NOT_FOUND == 127
    assert trace == ["check_node_version", "ensure_deps"]
    assert "npm" in stderr


def test_the_install_path_runs_both_npm_steps_in_order() -> None:
    """`.ci/lib/local-common.sh:302-303` is emphatic that both run and in this order, so the recording is where that survives the port."""
    trace = recorded("real-install")[3]
    assert [line.split("argv=", 1)[1] for line in trace] == [
        "install",
        "run install:natives",
        "run dev -w @rediacc/www",
    ]


def test_the_cached_path_installs_nothing() -> None:
    trace = recorded("real-cached")[3]
    assert [line.split("argv=", 1)[1] for line in trace] == ["run dev -w @rediacc/www"]


def test_the_stamp_round_trip_is_real(run_new) -> None:
    """THE PAIR THAT PAYS FOR THE MASK. The golden cannot carry the stamp's value, so the value is asserted here, live, where it is path-independent: the install run writes a real sha256, and the cached run that follows it takes the early return rather than installing again.

    Without this the mask would hide the entire side effect of the install path, which is the thing the `real-*` scenarios exist to observe.
    """
    sandbox, results = run_new
    stamp = sandbox.joinpath(*STAMP_PATH)
    assert stamp.is_file(), "the install path wrote no stamp"
    assert STAMP_RE.fullmatch(stamp.read_text(encoding="utf-8").strip()), (
        "the stamp is not a sha256"
    )
    assert results["real-install"][0] == 0
    assert results["real-cached"][0] == 0


# --------------------------------------------------------------------------- The plant ---------------------------------------------------------------------------


# The plant package's `__init__`. A comment rather than a docstring, so nothing here can be mistaken for a module worth importing on purpose.
PLANT_INIT = "# A deliberately broken copy of the port, built by the test beside it.\n"


def plant_source() -> str:
    """The port with its step line hoisted above the version check.

    THE SUBSTITUTION IS ASSERTED TO HAVE LANDED, because it is anchored to two literal lines of the real module. The day either is reworded the pattern matches nothing, the copy is identical to the port, and the control below would report PASS having planted nothing.
    """
    text = (ROOT / ".ci" / "rediacc_ci" / "dev" / "www.py").read_text(encoding="utf-8")
    step = "    log.step(STEP_MESSAGE)\n"
    check = '    rc = bridge.call("check_node_version", root)\n'
    if step not in text or check not in text:
        raise AssertionError("the plant is anchored to lines www.py no longer carries")
    return text.replace(step, "", 1).replace(check, step + check, 1)


def test_a_hoisted_step_line_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Announce the server before deciding whether to start it.

    A port with the step line first is correct on every machine with a working node, which is where it would be written and where it would be reviewed. The `node-fails` recording is the only thing that says otherwise, so the plant is driven against exactly that scenario.
    """
    package = tmp_path / "plant" / "devplant"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(PLANT_INIT, encoding="utf-8")
    (package / "www.py").write_text(plant_source(), encoding="utf-8")

    base = tmp_path / "run"
    base.mkdir()
    sandbox = build_sandbox(ROOT, base)
    bins = build_stubs(base)
    trace_file = base / "trace.txt"
    scenario = next(s for s in SCENARIOS if s.name == "node-fails")
    env = scenario_env(scenario, sandbox, trace_file, bins)
    env["PYTHONPATH"] = "%s:%s" % (tmp_path / "plant", env["PYTHONPATH"])
    trace_file.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from devplant import www; sys.exit(www.main(sys.argv[1:]))",
        ],
        cwd=str(sandbox),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    want = recorded("node-fails")
    assert www.STEP_MESSAGE not in want[2], "the recording no longer proves anything about order"
    assert www.STEP_MESSAGE in proc.stderr, "the plant did not take effect"


# --------------------------------------------------------------------------- The flip ---------------------------------------------------------------------------


def test_the_verb_is_served_once_and_only_by_python() -> None:
    """The partition `tests/gates/test_gate_run_sh.py` asserts, from this side.

    An OVERLAP is the failure the whole split exists to prevent: a verb served by two implementations is answered by whichever the router reaches first, so the port appears to work while the code it replaced is what actually ran. The router has no `dev` arm and no table row; the package's VERBS table is the only server, and the bash dispatcher that once held `dev()` is deleted.
    """
    router = (ROOT / "run.sh").read_text(encoding="utf-8")
    assert not re.search(r"^        dev\)", router, re.MULTILINE), "the router serves `dev` itself"
    assert "run_ported" in router, "run.sh does not forward verbs to this package"
    assert not (ROOT / ".ci" / "legacy" / "run-legacy.sh").exists(), (
        "the bash body outlived the port"
    )


def test_the_help_text_still_documents_the_verb() -> None:
    """`help` is the one inventory a person reads, and the gate test compares both halves against it. A ported verb that vanished from it reads as unreachable."""
    assert re.search(r"^  dev\s{2,}\S", run_verbs.help_text(), re.MULTILINE)


def test_the_verb_table_names_this_module() -> None:
    row = next((verb for verb in VERBS if verb.name == "dev"), None)
    assert row is not None, "run.sh forwards `dev` here and the table does not serve it"
    assert row.module == "rediacc_ci.dev.www"

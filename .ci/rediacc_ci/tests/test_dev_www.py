"""`rediacc_ci.dev.www` against the recorded bytes of the bash `dev()` it replaced.

WHY A RECORDING AND NOT A LIVE DIFFERENTIAL. Both existed while the port was being made: `.ci/rediacc_ci/dev/shadow_driver.py` drives either side, and `.ci/shadow/e2-dev.observations.jsonl` carries five EQUIVALENT rows over five distinct trees. That instrument stops being available the moment the twin is deleted, and deleting the twin is the whole point of the port, so on its last
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

import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.__main__ import VERBS
from rediacc_ci.dev import shadow_driver, www
from rediacc_ci.tests import frozen

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

ROOT = paths.repo_root()
SLUG = "dev-www"
LEDGER = ROOT / ".ci" / "shadow" / "e2-dev.observations.jsonl"

# The K the recipe requires of a port's ledger, and the same number `rediacc_ci/setup/port_parity.py` asserts for `e1-setup`.
LEDGER_K = 5

CASES = tuple(scenario.name for scenario in shadow_driver.SCENARIOS)

# Where the trace joins the recorded shape. `frozen.render` owns the exit line and the two streams; the externals are this subject's fourth stream and need a marker of their own so an empty trace is distinguishable from a missing one.
TRACE_MARKER = "--- trace ---\n"

# A 64-character lower-case hex run, which is what `ensure_deps` writes into its stamp and the only value in the corpus that is path-derived.
STAMP_RE = re.compile(r"\b[0-9a-f]{64}\b")
STAMP_TOKEN = "<sha256>"  # noqa: S105 -- a mask token, not a credential

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


def drive(side: str, base: pathlib.Path):
    """Run every scenario on one side, IN ORDER, against one sandbox.

    The order is load-bearing and is the driver's, not this file's: `real-cached` meets the stamp `real-install` wrote, so a parametrized test that built a fresh sandbox per case would test the fast path against a tree nothing had installed. Hence one module-scoped run and a lookup, rather than a fixture per case.
    """
    sandbox = shadow_driver.build_sandbox(ROOT, base)
    bins = shadow_driver.build_stubs(base)
    trace_file = base / "trace.txt"
    out: dict[str, tuple[int, str, str, list[str]]] = {}
    for scenario in shadow_driver.SCENARIOS:
        code, stdout, stderr, lines = shadow_driver.run_side(
            side, scenario, sandbox, trace_file, bins
        )
        out[scenario.name] = (
            code,
            normalise(shadow_driver.mask(stdout, sandbox)),
            reduce_stderr(scenario.name, normalise(shadow_driver.mask(stderr, sandbox))),
            [normalise(shadow_driver.mask(line, sandbox)) for line in lines],
        )
    return sandbox, out


@pytest.fixture(scope="module")
def run_new(tmp_path_factory):
    """One ordered run of every scenario against the port, and the sandbox it left behind."""
    return drive("new", tmp_path_factory.mktemp("dev-port"))


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
    stamp = sandbox.joinpath(*shadow_driver.STAMP_PATH)
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
    sandbox = shadow_driver.build_sandbox(ROOT, base)
    bins = shadow_driver.build_stubs(base)
    trace_file = base / "trace.txt"
    scenario = next(s for s in shadow_driver.SCENARIOS if s.name == "node-fails")
    env = shadow_driver.scenario_env(scenario, sandbox, trace_file, bins)
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


# --------------------------------------------------------------------------- The ledger ---------------------------------------------------------------------------


def test_the_ledger_carries_five_equivalent_distinct_trees() -> None:
    """THE EVIDENCE THE GOLDENS CANNOT REPLACE, and the reason it is asserted rather than cited.

    A recording proves the port still says what the twin said on the day the twin was read. The ledger proves the two ran side by side over five distinct clean trees and agreed every time. A ledger that is emptied, truncated or hand-edited is exactly as bad as one that was never recorded, so the file is read here rather than pointed at.
    """
    assert LEDGER.is_file(), "no ledger at %s" % LEDGER
    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line]
    equivalent = [row for row in rows if row.get("verdict") == "EQUIVALENT"]
    trees = {row["tree"]["id"] for row in equivalent if row["tree"].get("clean")}
    assert len(trees) >= LEDGER_K, "%d distinct clean tree(s), %d required" % (
        len(trees),
        LEDGER_K,
    )
    assert len(equivalent) == len(rows), "a non-EQUIVALENT row is in the ledger"
    fingerprints = {row["old"]["fingerprint"] for row in equivalent}
    assert len(fingerprints) > 1, "one observation re-shaded, not %d of them" % len(trees)


# --------------------------------------------------------------------------- The flip ---------------------------------------------------------------------------


def test_the_verb_is_served_once_and_only_by_python() -> None:
    """The partition `.ci/scripts/test/gates/test-run-sh.sh` section 6 asserts, from this side.

    An OVERLAP is the failure the whole split exists to prevent: a verb left in both halves is served by whichever the router reaches first, so the port appears to work while the code it replaced is what actually ran.
    """
    router = (ROOT / "run.sh").read_text(encoding="utf-8")
    legacy = (ROOT / ".ci" / "legacy" / "run-legacy.sh").read_text(encoding="utf-8")
    assert re.search(r"^PORTED_VERBS=\(.*\bdev\b.*\)$", router, re.MULTILINE), (
        "run.sh does not forward `dev` to this package"
    )
    assert "\ndev() {\n" not in legacy, "the bash body outlived the port"
    assert "\n        dev) dev ;;\n" not in legacy, "the legacy dispatch arm outlived the port"


def test_the_help_text_still_documents_the_verb() -> None:
    """`show_help` is the one inventory a person reads, and the gate test compares both halves against it. A ported verb that vanished from it reads as unreachable."""
    legacy = (ROOT / ".ci" / "legacy" / "run-legacy.sh").read_text(encoding="utf-8")
    assert re.search(r"^  dev\s{2,}\S", legacy, re.MULTILINE)


def test_the_verb_table_names_this_module() -> None:
    row = next((verb for verb in VERBS if verb.name == "dev"), None)
    assert row is not None, "run.sh forwards `dev` here and the table does not serve it"
    assert row.module == "rediacc_ci.dev.www"


def test_the_old_side_refuses_now_that_the_body_is_gone() -> None:
    """The refusal is REACHABLE, which is what makes it a guard rather than a comment.

    After the flip there is no bash to drive, and a driver that answered anyway would let a new row be recorded against a twin that no longer exists.
    """
    assert shadow_driver.twin_body(ROOT) == ""
    assert shadow_driver.main(["--side", "old"]) == shadow_driver.EXIT_CANNOT_RUN

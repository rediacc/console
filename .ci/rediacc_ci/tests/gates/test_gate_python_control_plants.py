"""The gate test for `check:ci-python-control-plants`, which has no bash twin.

NEW GATE, NOT A PORT, so there is no `.ci/scripts/test/gates/test-*.sh` to name here and no byte-for-byte parity to hold. What this file drives is the half the gate's own selftest structurally cannot reach: the gate as a PROCESS, invoked the way CI invokes it, against COPIES of the REAL Python quality estate it is meant to police.

WHY THE DISTINCTION IS NOT PEDANTRY. The selftest asserts `findings_for()` against eight synthetic module strings, each hand-written to contain exactly the shape under test. A fixture written to be caught will be caught.
It says nothing about whether the gate still fires when the mutation is one line inside a 450-line module beside 131 other plant sites, nor whether the process exits 1 rather than printing a finding and returning 0, nor whether the message names the file a reader has to open.
Those are the three things a green CI step actually rests on, and all three are invisible from inside the selftest.

THE THREE CASES THIS FILE OWES, and they are one design and not three:

  1. A REAL `plant()` rewritten back to a raw substitution, in a copy, reds and
     names the file. That is the regression the gate exists to stop.
  2. The HISTORICAL identity mutation reds. `review_turn_capacity.py` really did
     carry `_FIXTURE_HEALTHY.replace("max_turns=140", "max_turns=140")` at line
     480 of commit f8af6d092, chained ahead of a live `.replace`, inside the port
     of the very gate `control_vacuity` uses as its own control. It moved no
     verdict then and it is the founding defect now, so it is driven as a plant
     rather than remembered as a paragraph.
  3. The UNMODIFIED copy exits 0. Without it the first two are satisfied by a
     gate that reds on everything, which is why it is a case here and not an
     assumption.

NOTHING TRACKED IS EVER MUTATED. Every plant lands in a scratch tree holding copies, reached through `PY_CONTROL_PLANTS_ROOT`. Other sessions share this worktree.
"""

import importlib.util
import pathlib
import re
import shutil
import sys
from typing import Any

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_python_control_plants.py")

# The gate resolves its own root at CALL time from this variable, which is what makes a starved tree drivable from outside. Named here rather than typed at four call sites.
ROOT_ENV = "PY_CONTROL_PLANTS_ROOT"

# The subject of both plants. It is the module the founding defect lived in, and it carries five real `plant()` sites inside one `selftest()`, so a finding here is a finding among neighbours rather than in an empty file.
SUBJECT = ".ci/rediacc_ci/quality/review_turn_capacity.py"

# CASE 1. A genuine converted plant, put back the way it was written before the harness existed.
REAL_PLANT = 'plant(_FIXTURE_HEALTHY, "per_kloc=25", "per_kloc=8"),'
REAL_PLANT_RAW = '_FIXTURE_HEALTHY.replace("per_kloc=25", "per_kloc=8"),'

# CASE 2. Lifted VERBATIM from f8af6d092:.ci/rediacc_ci/quality/review_turn_capacity.py:480, which is why the indentation and the trailing argument line are carried with it: the historical shape is a chain, and the chain is the point.
HISTORICAL_PLANT = """            plant(
                _FIXTURE_HEALTHY,
                '[[ "$turns" -gt "$max_turns" ]] && turns="$max_turns"',
"""

HISTORICAL_IDENTITY = """            _FIXTURE_HEALTHY.replace("max_turns=140", "max_turns=140").replace(
                '[[ "$turns" -gt "$max_turns" ]] && turns="$max_turns"',
"""

_COUNTS = re.compile(r"(\d+) Python gate module\(s\) scanned, (\d+) plant\(\) call site\(s\)")

# FLOORS UNDER THE SHAPE, not equality with it. Measured 2026-09-22: 240 modules and 132 plant sites. Equality would red on every port that lands under the two globs, which is exactly the traffic this gate is designed to welcome; these numbers are set to catch a corpus that COLLAPSED, and nothing finer.
MIN_MODULES = 100
MIN_SITES = 40

# The gate's own declared control floor. A selftest that runs fewer controls than it declares has stopped executing rather than stopped being needed.
MIN_CONTROLS = 19

# The gate, loaded once per process. A dict rather than a module-level rebind so no `global` statement is needed, which is the shape the repo-root `conftest.py` uses for the same reason; the key names why the entry exists rather than being a bare index.
_CACHE: dict[str, Any] = {}


def _gate_module() -> Any:
    """The gate, imported BY PATH, purely to borrow its own `SCOPE` globs.

    The mirror has to copy exactly what the gate scans. Re-typing the two globs here would let the two drift apart in silence, and a mirror that had quietly stopped copying half the estate would still pass every case that expects a green, which is the vacuity this whole file is about. Importing under a name other than `__main__` runs no `SystemExit`.
    """
    if "subject" not in _CACHE:
        if not GATE.is_file():
            raise harness.GateAssertionError("subject under test is missing: %s" % GATE)
        sys.path.insert(0, str(GATE.parent))
        try:
            spec = importlib.util.spec_from_file_location("py_control_plants_subject", GATE)
            if spec is None or spec.loader is None:
                raise harness.GateAssertionError(
                    "python built no import spec for %s, so this file cannot read the gate's "
                    "own SCOPE and every mirror below would be copied from a guess" % GATE
                )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(GATE.parent))
        _CACHE["subject"] = module
    return _CACHE["subject"]


def _run(root, *args):
    return harness.run(
        [sys.executable, str(GATE), *args],
        cwd=paths.repo_root(),
        env={ROOT_ENV: str(root)},
    )


def _counts(text):
    """`(modules, sites)` off the success line, or a refusal naming what was read.

    Parsed rather than assumed. The success line is the only place the gate says how much it looked at, so a case that asserts exit 0 without reading it cannot tell a full scan from a scan of nothing.
    """
    found = _COUNTS.search(text)
    if not found:
        raise harness.GateAssertionError(
            "the success line carrying the module and plant-site counts is absent, so "
            'this case cannot tell a full scan from an empty one. Got: "%s"' % text[-400:]
        )
    return int(found.group(1)), int(found.group(2))


def _mirror(tmp):
    """A scratch tree holding copies of every module the gate scans."""
    root = pathlib.Path(tmp) / "mirror"
    copied = 0
    for pattern in _gate_module().SCOPE:
        parent, _, glob = pattern.rpartition("/")
        for source in sorted(paths.from_root(*parent.split("/")).glob(glob)):
            target = root / parent / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)
            copied += 1
    if copied < MIN_MODULES:
        raise harness.GateAssertionError(
            "the mirror copied only %d file(s) from %s. Every plant below would land "
            "in a tree the gate barely reads, so a red here would prove nothing about "
            "the real one" % (copied, " and ".join(_gate_module().SCOPE))
        )
    return root


def _edit(root, rel, old, new):
    """Plant in the COPY, and refuse when the needle has moved.

    A plant whose needle is gone mutates nothing, so the case scans a clean tree and passes for free. That is precisely the class the gate under test exists to catch, arriving in the gate's own test.
    """
    path = root / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise harness.GateAssertionError(
            "the plant's needle is GONE from %s, so this case would scan an unmutated "
            "copy and pass for free. Re-read the subject and re-cut the needle; do not "
            "relax the case" % rel
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_the_gate_is_green_on_the_real_tree(gate):
    gate.log_test("the real tree, through the real entry point")
    result = _run(paths.repo_root())
    gate.assert_exit(0, result, "clean tree")
    modules, sites = _counts(result.combined)
    # THE SHAPE, NOT THE VERDICT. A corpus that collapsed to one module would still print a tick, and these two numbers are the only thing that says it did not.
    if modules < MIN_MODULES or sites < MIN_SITES:
        gate.log_fail(
            "%d module(s) and %d plant site(s) scanned, against floors of %d and %d. "
            "The globs have stopped matching the estate, so the green above is a "
            "statement about almost nothing" % (modules, sites, MIN_MODULES, MIN_SITES)
        )
    gate.log_pass("green over %d module(s) and %d plant site(s)" % (modules, sites))


def test_the_unmodified_mirror_is_green_and_reads_the_same_estate(gate):
    """The MUST-NOT-FIRE case, and the one that gives the other two their meaning.

    It also compares the mirror's counts against the real tree's. Exit 0 alone would be satisfied by a mirror that copied four files, and every plant below would then be landing in a tree unlike the one the gate really reads.
    """
    gate.log_test("NEGATIVE: an untouched copy of the whole estate")
    real_modules, real_sites = _counts(_run(paths.repo_root()).combined)
    with harness.temp_dir() as tmp:
        result = _run(_mirror(tmp))
        gate.assert_exit(0, result, "the copy is clean")
        modules, sites = _counts(result.combined)
        gate.assert_eq(modules, real_modules, "the mirror holds every module the real tree does")
        gate.assert_eq(sites, real_sites, "and every plant site")
    gate.log_pass("the untouched mirror is green over the same %d module(s)" % modules)


def test_rewriting_a_real_plant_back_to_a_raw_substitution_reds(gate):
    gate.log_test("PLANT: turn a REAL plant() back into a raw substitution, in a copy")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit(0, _run(root), "the untouched mirror is green first")
        _edit(root, SUBJECT, REAL_PLANT, REAL_PLANT_RAW)
        result = _run(root)
        gate.assert_exit(1, result, "a raw substitution in a control region is a finding")
        gate.assert_contains(result.combined, "review_turn_capacity.py", "names the file")
        gate.assert_contains(result.combined, "line 406", "and the line")
        gate.assert_contains(result.combined, "raw substitution", "says what is wrong")
        gate.assert_contains(result.combined, "plant() from rediacc_ci.controls", "and the fix")
        # ONE finding and not five. The other four sites in the same `selftest()` are untouched plants, so a gate that reported them too would be flagging the harness it is asking for.
        gate.assert_contains(result.combined, "1 control plant(s)", "and only the planted site")
    gate.log_pass("the real-tree plant reds, names the file and line, and hands over the fix")


def test_the_historical_max_turns_identity_reds(gate):
    """The founding defect, driven rather than recalled.

    `_FIXTURE_HEALTHY.replace("max_turns=140", "max_turns=140")` is an IDENTITY: `old == new`, so the mutant is byte-for-byte the clean fixture. It sat chained ahead of a live `.replace` at f8af6d092:480, which is why it moved no verdict and why nothing ever noticed it. `plant()` now refuses that construction outright, proven at `.ci/rediacc_ci/tests/test_controls.py:289`; this
    case proves the other half, that the gate reds on the SHAPE before anyone has to rely on the harness being reached at all.
    """
    gate.log_test("PLANT: reintroduce the historical max_turns=140 identity, in a copy")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit(0, _run(root), "the untouched mirror is green first")
        _edit(root, SUBJECT, HISTORICAL_PLANT, HISTORICAL_IDENTITY)
        result = _run(root)
        gate.assert_exit(1, result, "the identity mutation is a finding")
        gate.assert_contains(result.combined, "review_turn_capacity.py", "names the file")
        gate.assert_contains(result.combined, "_FIXTURE_HEALTHY.replace", "and the receiver")
        # ONE finding, from a chain of TWO substitutions. The second one's receiver is the first call's result, not a bare name, and a parsing receiver is deliberately invisible here. Asserting the count is what pins that: a gate that flagged both would be flagging the shape its own exemption exists to allow.
        gate.assert_contains(result.combined, "1 control plant(s)", "once, not once per link")
    gate.log_pass("the founding defect reds on its shape, chain and all")


def test_an_empty_root_refuses_on_the_module_arm(gate):
    gate.log_test("ANTI-VACUITY: point the gate at a tree with no gate modules at all")
    with harness.temp_dir() as tmp:
        gate.assert_vacuous_tree_fails(
            _run, tmp, "no Python gate module found", "an empty tree is a refusal"
        )


def test_a_tree_with_no_plant_site_refuses_on_the_site_arm(gate):
    """The SECOND refusal, and the one that outranks the first.

    The day the harness is renamed and this gate is not updated, every module looks compliant and a green here would mean nothing. The two arms overlap on an empty tree, so this case starves only the sites: one real module, parsed, discovered, carrying no plant at all.
    """
    gate.log_test("ANTI-VACUITY: modules discovered, ZERO plant() sites among them")
    with harness.temp_dir() as tmp:
        root = pathlib.Path(tmp) / "starved"
        (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
        (root / ".ci" / "rediacc_ci" / "quality" / "m.py").write_text("x = 1\n", encoding="utf-8")
        result = _run(root)
        gate.assert_exit(1, result, "no plant site anywhere is a refusal")
        gate.assert_contains(result.combined, "ZERO plant() call sites", "says which arm fired")
        gate.assert_contains(result.combined, "scanned 1 module(s)", "and that it DID see the tree")
        # The arms must stay distinguishable. If this printed the module-arm message the two would be one check, and deleting either would leave the suite green.
        gate.assert_not_contains(
            result.combined, "no Python gate module found", "not the module arm's message"
        )
    gate.log_pass("a renamed harness reds with its own message, distinct from an empty tree")


def test_the_selftest_runs_as_a_process_and_is_not_trivially_small(gate):
    gate.log_test("--selftest, as a process, with a floor under how much it asserts")
    result = _run(paths.repo_root(), "--selftest", "--verbose")
    gate.assert_exit(0, result, "every control passes")
    passes = len([ln for ln in result.combined.splitlines() if ln.startswith("ok ")])
    if passes < MIN_CONTROLS:
        gate.log_fail(
            "only %d control(s) ran against a declared floor of %d; a collapse there "
            "means controls stopped executing, not that they stopped being needed"
            % (passes, MIN_CONTROLS)
        )
    gate.log_pass("%d controls ran, both directions on every rule and both exemptions" % passes)

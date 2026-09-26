"""Subject: `.ci/scripts/quality/check_python_types.py` and `rediacc_ci.quality.python_types`.

THE CLAIM BEING TESTED, and therefore what has to be proven in BOTH directions: the Python this repo ships is type-checked by a mypy AT THE PIN under this repo's own config, today's findings are frozen as ids that survive a MOVE, a NEW finding fails, a FIXED one demands a drain, and a reseed that would absorb anything is refused.

WHAT IS HERE AND WHAT IS ELSEWHERE, stated so a reader does not conclude the coverage is thinner than it is:

  * The pure halves -- the parser, the id, the fold, the partition, the control
    verdict, the comparison -- are exercised by the subject's own `--selftest`,
    which `test_the_selftest_runs_through_the_entry_point` drives as a
    SUBPROCESS through the registered entry point rather than by importing it.
    That is the difference between "the functions work" and "the file CI runs
    works", and the `_cipath` hop is exactly the thing an import-based test
    would skip.
  * The empty-tree refusal is registered in
    `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py`, whose harness
    copies the gate into a tree with no git index and requires the words VACUOUS
    INPUT. Asserting it a second time here would be a second answer to one
    question.
  * A full real-tree run is NOT here. It takes about 40 seconds cold, and the
    thing it would prove -- that the gate is green on this tree -- is what CI
    runs the gate for.

WHAT THIS FILE OWNS is the committed ARTIFACT and the CONFIGURATION the control depends on, neither of which any of those reach. A baseline row whose id no longer hashes its own text is the re-keying hazard made real: it looks like a normal row, it compares against nothing, and it silently stops being drainable.
"""

import json
import pathlib
import subprocess
import sys
import tomllib

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.quality import python_types

ROOT = paths.repo_root()
GATE = ROOT / ".ci" / "scripts" / "quality" / "check_python_types.py"
BASELINE = ROOT / ".ci" / "config" / "python-types-baseline.json"
PYPROJECT = ROOT / "pyproject.toml"

# The baseline held 581 ids over 936 occurrences on the day it was seeded. A floor rather than an equality, because the whole point of the file is that it shrinks; and a real number rather than 1, because a baseline that collapsed to a handful would make every one of today's findings look brand new and would red the tree rather than this test.
MIN_BASELINE_ROWS = 100


def rows() -> list[dict]:
    """The committed baseline rows."""
    return json.loads(BASELINE.read_text(encoding="utf-8"))["findings"]


def test_the_selftest_runs_through_the_entry_point():
    """The registered path, as a subprocess, which is what CI executes."""
    proc = subprocess.run(
        [sys.executable, str(GATE), "--selftest"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, "selftest failed:\n%s\n%s" % (proc.stdout, proc.stderr)
    assert "control(s) passed" in proc.stdout, proc.stdout


def test_the_entry_point_refuses_an_argument_it_does_not_understand():
    """CONTROL for the case above: a gate that exits 0 on anything is not a gate.

    A typo'd flag must NOT be silently ignored. `--write-baselines` reading as a plain run is how a drain that was meant to happen quietly does not.
    """
    proc = subprocess.run(
        [sys.executable, str(GATE), "--write-baselines"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "unknown argument" in proc.stderr, proc.stderr


def test_every_baseline_row_hashes_its_own_text():
    """THE RE-KEYING HAZARD, made a test rather than a hope.

    An id is the hash of (file, code, message). A row hand-edited in the message but not in the id keys nothing: the real finding reads as brand new and the stale row reads as fixed, forever, and both halves of that are silent. This recomputes every id from the row's own three fields.
    """
    bad = []
    for row in rows():
        want = python_types.Finding(row["file"], row["code"], row["message"]).id
        if want != row["id"]:
            bad.append(
                "%s [%s]: id %s, text hashes to %s" % (row["file"], row["code"], row["id"], want)
            )
    assert not bad, "baseline rows whose id does not match their text:\n  " + "\n  ".join(bad)


def test_the_baseline_is_not_trivially_small():
    """A collapsed baseline reds the whole tree, which reads as a code problem."""
    assert len(rows()) >= MIN_BASELINE_ROWS, len(rows())


def test_every_baseline_row_carries_the_four_fields_and_a_positive_count():
    """A row missing a field compares against nothing and drains nothing."""
    for row in rows():
        for field in ("id", "file", "code", "message", "count"):
            assert field in row, row
        assert isinstance(row["count"], int), row
        assert row["count"] >= 1, row


def test_baseline_ids_are_unique():
    """CONTROL on the fold: two rows with one id means the count is a lie."""
    ids = [row["id"] for row in rows()]
    assert len(ids) == len(set(ids)), "duplicate id(s) in the baseline"


def test_no_baseline_row_names_a_path_outside_the_checked_corpus():
    """A row naming `private/` or an absolute path cannot fire again.

    Such a row sits in the file as permanent undrainable debt, and the one thing this baseline promises is that it shrinks.
    """
    bad = [r["file"] for r in rows() if r["file"].startswith(("/", "private/"))]
    assert not bad, bad


def test_the_mypy_config_the_control_depends_on_is_present():
    """The four keys the planted control asserts against, pinned where they live.

    The control catches their loss at RUN time and refuses to judge the tree, which is the right behaviour for a gate; this catches it at TEST time and names the key, which is the right behaviour for a suite. `check_untyped_defs` is the one that matters most: without it mypy skips the body of every unannotated function, and almost every function in this repo is one.
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["mypy"]
    assert config["check_untyped_defs"] is True, config
    assert config["ignore_missing_imports"] is True, config
    assert config["no_site_packages"] is True, config
    assert config["python_version"] == "3.12", config


def test_the_config_does_not_turn_strict_on():
    """CONTROL for the case above. The baseline is not a strict-mode baseline.

    Measured when this gate was written: `--strict` on this tree reports 1061 errors, 96.7% of them no-untyped-def/no-untyped-call. Turning any of these on would invalidate every row in the committed baseline at once.
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["mypy"]
    for key in ("strict", "disallow_untyped_defs", "disallow_untyped_calls"):
        assert config.get(key, False) is False, "%s is on; the baseline assumes it is not" % key


def test_the_pin_is_read_from_the_pins_file_and_not_written_here():
    """One definition per pin, which `check:ci-toolchain-pins` A1 also enforces.

    This asserts the KEY resolves rather than asserting a version literal: a test carrying the number would itself be the second place the pin is written down.
    """
    value = toolchain.pin(python_types.PIN_KEY)
    assert value, value
    assert value[0].isdigit(), value


def test_the_partition_covers_the_real_corpus_exactly():
    """Every tracked-or-untracked .py lands in exactly one group, on the REAL tree.

    The fixture cases in the subject's selftest prove the rule; this proves it holds over the corpus the gate actually judges, which is where a module-name collision nobody anticipated would show up. A file dropped here is a file nobody type-checks, and the gate would still print a green over what remained.
    """
    files = python_types.enumerate_py(str(ROOT))
    assert len(files) >= python_types.MIN_PY_FILES, len(files)
    groups = python_types.partition(ROOT, files)
    flat = [f for group in groups for f in group]
    assert sorted(flat) == sorted(files)
    assert len(flat) == len(set(flat)), "a file landed in more than one group"
    for group in groups:
        names = [python_types.module_name(ROOT, f) for f in group]
        assert len(names) == len(set(names)), "a group holds two files with one module name"


def test_the_gate_is_wired_into_all_three_places():
    """package.json, the lock, and a real workflow step whose name matches.

    `check:ci-parity` asserts this across the whole estate and is the authority; this is the local copy that fails with THIS gate's name in the message rather than as one line of a 345-entry report.
    """
    scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert scripts["check:ci-python-types"] == ".ci/scripts/quality/check_python_types.py"

    lock = json.loads((ROOT / "scripts/ci-runner/gates.lock.json").read_text(encoding="utf-8"))
    entry = next(e for e in lock if e["id"] == "check:ci-python-types")
    assert entry["gate"] is True, entry
    assert entry["leaves"] == [".ci/scripts/quality/check_python_types.py"], entry
    step = entry["ci"]["step"]

    workflow = (ROOT / entry["ci"]["workflow"]).read_text(encoding="utf-8")
    assert ("- name: %s" % step) in workflow, step
    assert ".ci/scripts/quality/check_python_types.py" in workflow


def test_the_gate_script_is_executable_and_has_a_shebang():
    """`check:ci-python-lint`'s EXE001 half, applied to this gate's own entry point."""
    mode = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-s", "--", str(GATE.relative_to(ROOT))],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    # `GATE.open("rb").read(2)` LEAKS THE HANDLE, and this suite runs under `filterwarnings = error`, so the finaliser's unraisable turns into a test failure rather than into nothing. The same spelling sits in `python_lint.mode_findings`, where it leaks once per tracked .py and nothing complains because that gate is not run under pytest.
    head = GATE.read_bytes()[:2]
    assert head == b"#!", "the entry point has no shebang"
    if mode:
        assert mode[0] == "100755", "git mode is %s; CI lints a fresh checkout" % mode[0]


def test_the_baseline_note_says_it_shrinks():
    """A generated file read without its own header is a file nobody understands.

    The note is what a reader meets first when a diff to this file shows up in a review, and it is the only place the drain command appears inside the artifact itself.
    """
    note = json.loads(BASELINE.read_text(encoding="utf-8"))["note"]
    assert "SHRINK-ONLY" in note
    assert "write-baseline" in note


def test_the_baseline_path_the_subject_writes_is_the_one_committed():
    """CONTROL against a subject that quietly writes somewhere else.

    A gate whose `--write-baseline` lands beside the file CI reads is a gate whose green is about a file nobody looks at. The label and the real path are checked against each other rather than both being read from the subject.
    """
    assert str(BASELINE.relative_to(ROOT)) == python_types.BASELINE_LABEL
    assert BASELINE.is_file()


def test_the_gate_module_reaches_the_shared_composition_guard():
    """`gate-test:shrink-only-composition`'s rule, asserted by this gate's own suite.

    Not a duplicate of that meta-gate: it asks the question of every writer in the tree and would name this file among several, while this one fails with this gate's name and this gate's reason. The import is the load-bearing half -- a local re-derivation of the decision is a second implementation that can drift from the one every other baseline uses.
    """
    text = pathlib.Path(python_types.__file__).read_text(encoding="utf-8")
    assert "from rediacc_ci.quality.shrink_only import" in text
    assert "baseline_additions(" in text
    assert "write_verdict(" in text

"""`rediacc_ci.xdist_groups`, and the repo-root conftest that consumes it.

WHAT IS ACTUALLY AT RISK HERE, because the obvious assertion is the wrong one. The derivation returns ZERO groups on this tree today (29 of 29 ported modules resolve against the lock and none of them is in `mutex | reads`), so a floor saying "at least one group exists" would be red the day it was written and would be suppressed the week after. It is deliberately absent.

What CAN go silently wrong, and is therefore what these tests hold:

  * the JOIN going empty, which would make `test_twin_parity`'s real-tree refusal
    admit every twin. Both sources going quiet at once is the state that must not
    read as "nothing needs isolating";
  * the two readers DRIFTING, now that `test_twin_parity.real_tree_tests` and the
    scheduler ask the same question. They are asserted to give the same answer;
  * the marker never actually reaching an item. Every unit assertion below can
    pass while the repo-root conftest is not loaded at all, so the last two tests
    drive a REAL pytest and ask it, in both directions, whether the items came
    out marked.

EVERY FIXTURE IS BUILT BY CONSTRUCTION, never by substituting into real source, so rewording run-all.sh or the lock cannot silently void a control.
"""

import json
import subprocess
import sys

import pytest

from rediacc_ci import paths, xdist_groups
from rediacc_ci.tests import test_core_ports
from rediacc_ci.tests.gates import test_twin_parity

REAL_LOCK = xdist_groups.lock_path()

# A lock shaped exactly like the real one: a list of entries whose `run` names a script under .ci/scripts/test/gates/ and which may carry `mutex` / `reads`.
FIXTURE_LOCK = [
    {"id": "a", "run": "bash .ci/scripts/test/gates/test-writes.sh", "mutex": ["tree:repo"]},
    {"id": "b", "run": "bash .ci/scripts/test/gates/test-scans.sh", "reads": ["tree:repo"]},
    {"id": "c", "run": "bash .ci/scripts/test/gates/test-quiet.sh"},
    {"id": "d", "run": "npx tsx scripts/check-elsewhere.ts", "mutex": ["tree:repo"]},
]

FIXTURE_RUNNER = """#!/usr/bin/env bash
WRITER_FALLBACK=(
    test-from-runner.sh
    # a comment, which is not a test name
)
EXTRA_TOOLS=(
    test-must-not-be-read.sh
)
"""


class _Module:
    """A stand-in for an imported test module. `group_for` reads attributes, so
    the smallest honest fixture is an object with attributes."""

    def __init__(self, **attrs) -> None:
        self.__dict__.update(attrs)


def _write(tmp_path, lock=FIXTURE_LOCK, runner=FIXTURE_RUNNER):
    lock_file = tmp_path / "gates.lock.json"
    lock_file.write_text(json.dumps(lock), encoding="utf-8")
    runner_file = tmp_path / "run-all.sh"
    runner_file.write_text(runner, encoding="utf-8")
    return lock_file, runner_file


# --------------------------------------------------------------------------- real_tree_twins: the union, both directions ---------------------------------------------------------------------------


def test_the_union_takes_both_claims_from_the_lock_and_the_runner_arrays(tmp_path) -> None:
    lock, runner = _write(tmp_path)
    assert xdist_groups.real_tree_twins(lock, runner) == {
        "test-writes.sh",
        "test-scans.sh",
        "test-from-runner.sh",
    }


def test_a_gate_declaring_no_tree_resource_is_not_in_the_union(tmp_path) -> None:
    """CONTROL. Without this the union could be "every gate in the lock" and
    every assertion above would still pass."""
    lock, runner = _write(tmp_path)
    assert "test-quiet.sh" not in xdist_groups.real_tree_twins(lock, runner)


def test_a_tree_claim_outside_the_gates_directory_is_not_a_gate_test(tmp_path) -> None:
    """CONTROL. Entry `d` claims `tree:repo` and is not a gate test at all."""
    lock, runner = _write(tmp_path)
    assert "check-elsewhere.ts" not in xdist_groups.real_tree_twins(lock, runner)


def test_only_fallback_arrays_are_read_from_the_runner(tmp_path) -> None:
    """CONTROL. The runner declares other arrays; reading them all would inflate
    the union with names that are not gate tests.

    THE FIRST SPELLING OF THIS FIXTURE WAS BROKEN, AND IT IS WORTH THE LINE. The non-fallback array was named `NOT_A_FALLBACK`, which `endswith("_FALLBACK")` is perfectly happy with, so the control fired against the control rather than against the reader. The name here must not end in `_FALLBACK` for the same reason a probe file must not be named so the glob matches it.
    """
    lock, runner = _write(tmp_path)
    assert "test-must-not-be-read.sh" not in xdist_groups.real_tree_twins(lock, runner)


def test_an_unreadable_lock_leaves_the_runner_half_standing(tmp_path) -> None:
    """A broken lock must not empty the answer. It contributes nothing and does
    not raise, which is `classify_from_lock`'s documented contract."""
    _lock, runner = _write(tmp_path)
    assert xdist_groups.real_tree_twins(tmp_path / "absent.json", runner) == {"test-from-runner.sh"}


def test_an_absent_runner_leaves_the_lock_half_standing(tmp_path) -> None:
    lock, _runner = _write(tmp_path)
    assert xdist_groups.real_tree_twins(lock, tmp_path / "absent.sh") == {
        "test-writes.sh",
        "test-scans.sh",
    }


def test_both_sources_absent_yields_an_empty_union_rather_than_an_exception(tmp_path) -> None:
    """The empty case is REACHABLE and returns cleanly, because the refusal
    belongs to the callers -- who can tell an empty union apart from a crash and
    say which one happened."""
    assert xdist_groups.real_tree_twins(tmp_path / "no.json", tmp_path / "no.sh") == set()


# --------------------------------------------------------------------------- The real tree ---------------------------------------------------------------------------


def test_the_real_join_is_not_empty() -> None:
    """ANTI-VACUITY, and it is the one floor that is honest today.

    An empty union makes `test_no_ported_twin_is_a_real_tree_writer_or_scanner` admit every twin including the four that rewrite tracked files, and makes the group derivation unable to serialise anything. Zero GROUPS is the correct answer on this tree; zero KNOWN REAL-TREE TESTS is a broken reader.
    """
    assert xdist_groups.real_tree_twins(REAL_LOCK) != set()


def test_the_parity_test_and_the_scheduler_read_the_same_union() -> None:
    """THE NO-DRIFT CLAIM, asserted rather than assumed.

    `test_twin_parity.real_tree_tests` is now a call into this module. If someone reinstates a local copy there, the two will agree on the day it is written and diverge later, which is the failure mode that made moving it worth doing.
    """
    assert test_twin_parity.real_tree_tests() == xdist_groups.real_tree_twins(REAL_LOCK)


def test_the_ported_corpus_agrees_with_the_parity_test_about_who_is_unsafe() -> None:
    """SET-BASED, and green whether the answer is empty or not.

    `test_twin_parity` fails the port when a ported module's twin is in the union; the scheduler sends exactly those modules to one worker. The two sets are computed here from opposite ends and must be equal -- so this stays true the day the first real-tree twin is ported, instead of being a hardcoded 0 that would have to be edited then.
    """
    unsafe = xdist_groups.real_tree_twins(REAL_LOCK)
    from_parity = {
        name
        for name, _path, twin, _timeout in test_twin_parity.MODULES
        if twin.rsplit("/", 1)[-1] in unsafe
    }
    from_scheduler = set()
    for name, _path, twin, _timeout in test_twin_parity.MODULES:
        module = _Module(BASH_TWIN=twin)
        if xdist_groups.group_for(module, unsafe) == xdist_groups.REAL_TREE_GROUP:
            from_scheduler.add(name)
    assert from_scheduler == from_parity


def test_the_port_scan_module_still_declares_its_group() -> None:
    """The one escape hatch in use, pinned by name.

    `find_consecutive_free_ports(7, 20000, 30000)` returns the FIRST free run, so every worker picks 20000. No lock entry can express that -- the resource is the host's port space, not the tree -- so the declaration lives in the module and this is what stops it being tidied away.
    """
    assert test_core_ports.XDIST_GROUP == "ports"


# --------------------------------------------------------------------------- group_for: both directions ---------------------------------------------------------------------------


def test_an_explicit_group_attribute_is_the_group() -> None:
    assert xdist_groups.group_for(_Module(XDIST_GROUP="ports"), set()) == "ports"


def test_an_explicit_group_beats_the_lock_join() -> None:
    """Precedence, stated in the module docstring and asserted here: a module may
    name its own resource without also being a real-tree twin."""
    module = _Module(XDIST_GROUP="ports", BASH_TWIN=".ci/scripts/test/gates/test-writes.sh")
    assert xdist_groups.group_for(module, {"test-writes.sh"}) == "ports"


def test_a_twin_in_the_union_gets_the_shared_real_tree_group() -> None:
    module = _Module(BASH_TWIN=".ci/scripts/test/gates/test-writes.sh")
    assert xdist_groups.group_for(module, {"test-writes.sh"}) == xdist_groups.REAL_TREE_GROUP


def test_two_real_tree_twins_get_the_same_group_not_two_groups() -> None:
    """Two groups may run on two workers at once, so a reader and a writer in
    different groups is exactly the collision being prevented. One name."""
    unsafe = {"test-writes.sh", "test-scans.sh"}
    first = xdist_groups.group_for(_Module(BASH_TWIN="a/test-writes.sh"), unsafe)
    second = xdist_groups.group_for(_Module(BASH_TWIN="b/test-scans.sh"), unsafe)
    assert first == second


def test_a_twin_outside_the_union_is_ungrouped() -> None:
    """CONTROL, and the important one: ungrouped items distribute FREELY. A
    derivation that grouped everything would be green and serial."""
    module = _Module(BASH_TWIN=".ci/scripts/test/gates/test-quiet.sh")
    assert xdist_groups.group_for(module, {"test-writes.sh"}) is None


def test_a_module_declaring_neither_is_ungrouped() -> None:
    assert xdist_groups.group_for(_Module(), {"test-writes.sh"}) is None


def test_an_empty_group_string_is_not_a_group() -> None:
    """CONTROL. `XDIST_GROUP = ""` would otherwise become a real group named the
    empty string, silently serialising the module against every other module that
    got it wrong the same way."""
    assert xdist_groups.group_for(_Module(XDIST_GROUP=""), set()) is None


def test_a_non_string_group_is_ignored_rather_than_stringified() -> None:
    assert xdist_groups.group_for(_Module(XDIST_GROUP=3), set()) is None


# --------------------------------------------------------------------------- The conftest, end to end. Everything above can pass while it is never loaded. ---------------------------------------------------------------------------


def _collect(target: str, expr: str) -> subprocess.CompletedProcess:
    """`pytest --collect-only -q -m <expr>` on one module, as a subprocess.

    A SUBPROCESS because the question is whether the REPO-ROOT CONFTEST attaches the marker during collection, and the collection that is running this test already happened. `-m` is pytest's own marker expression, so the answer comes
    from pytest's item store rather than from re-reading the file.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", expr, target],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.repo_root()),
        timeout=300,
    )


def _collected(proc: subprocess.CompletedProcess) -> int:
    return len([line for line in proc.stdout.splitlines() if "::" in line])


PORTS_MODULE = ".ci/rediacc_ci/tests/test_core_ports.py"
UNGROUPED_MODULE = ".ci/rediacc_ci/tests/test_setup_tools.py"


@pytest.mark.parametrize(
    ("target", "expr", "want_any"),
    [
        (PORTS_MODULE, "xdist_group", True),
        (PORTS_MODULE, "not xdist_group", False),
        (UNGROUPED_MODULE, "xdist_group", False),
        (UNGROUPED_MODULE, "not xdist_group", True),
    ],
    ids=["ports-marked", "ports-nothing-unmarked", "plain-unmarked", "plain-all-unmarked"],
)
def test_the_root_conftest_marks_exactly_the_declaring_module(target, expr, want_any) -> None:
    """FOUR CELLS, so neither direction can be satisfied by an accident.

    A conftest that marked EVERYTHING would pass cells 1 and 2 and fail 3 and 4. A conftest that was never loaded would pass 3 and 4 and fail 1 and 2. Only a conftest that marks the declaring module and nothing else passes all four.
    """
    proc = _collect(target, expr)
    assert proc.returncode in (0, 5), proc.stdout + proc.stderr
    assert (_collected(proc) > 0) is want_any, proc.stdout + proc.stderr

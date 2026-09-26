"""`rediacc_ci.xdist_groups`, and the repo-root conftest that consumes it.

WHAT IS ACTUALLY AT RISK HERE, because the obvious assertion is the wrong one. The derivation returns ZERO groups on this tree today (29 of 29 ported modules resolve against the lock and none of them is in `mutex | reads`), so a floor saying "at least one group exists" would be red the day it was written and would be suppressed the week after. It is deliberately absent.

What CAN go silently wrong, and is therefore what these tests hold:

  * the DERIVATION going empty, which would make `test_twin_parity`'s real-tree
    refusal admit every twin. A lock that has gone quiet, or has stopped being
    readable, is the state that must not read as "nothing needs isolating".
    That risk GREW when the shell runner's `*_FALLBACK` arrays were retired as a
    second source: the lock is now the only source, so nothing else is left to
    keep the answer non-empty when it fails;
  * the two readers DRIFTING, now that `test_twin_parity.real_tree_tests` and the
    scheduler ask the same question. They are asserted to give the same answer;
  * the marker never actually reaching an item. Every unit assertion below can
    pass while the repo-root conftest is not loaded at all, so the last two tests
    drive a REAL pytest and ask it, in both directions, whether the items came
    out marked.

EVERY FIXTURE IS BUILT BY CONSTRUCTION, never by substituting into real source, so rewording the lock cannot silently void a control.
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


class _Module:
    """A stand-in for an imported test module. `group_for` reads attributes, so the smallest honest fixture is an object with attributes."""

    def __init__(self, **attrs) -> None:
        self.__dict__.update(attrs)


def _write(tmp_path, lock=FIXTURE_LOCK):
    lock_file = tmp_path / "gates.lock.json"
    lock_file.write_text(json.dumps(lock), encoding="utf-8")
    return lock_file


# --------------------------------------------------------------------------- real_tree_twins: both claims, and what is excluded ---------------------------------------------------------------------------


def test_both_claims_are_taken_from_the_lock(tmp_path) -> None:
    """`mutex` (exclusive) and `reads` (shared) both put a twin in the set, and a reader overlapping a writer is the collision being prevented."""
    lock = _write(tmp_path)
    assert xdist_groups.real_tree_twins(lock) == {"test-writes.sh", "test-scans.sh"}


def test_a_gate_declaring_no_tree_resource_is_not_in_the_set(tmp_path) -> None:
    """CONTROL. Without this the set could be "every gate in the lock" and every assertion above would still pass."""
    lock = _write(tmp_path)
    assert "test-quiet.sh" not in xdist_groups.real_tree_twins(lock)


def test_a_tree_claim_outside_the_gates_directory_is_not_a_gate_test(tmp_path) -> None:
    """CONTROL. Entry `d` claims `tree:repo` and is not a gate test at all."""
    lock = _write(tmp_path)
    assert "check-elsewhere.ts" not in xdist_groups.real_tree_twins(lock)


def test_an_unreadable_lock_empties_the_set_cleanly_rather_than_raising(tmp_path) -> None:
    """THE CASE THAT CHANGED WHEN THE SHELL RUNNER WAS RETIRED, and it is stated here rather than dropped.

    A broken lock used to leave the runner's `*_FALLBACK` arrays standing, so the answer stayed non-empty. The lock is the only source now, so a broken one empties the set -- and the contract that matters is that it does so CLEANLY: `classify_from_lock` contributes nothing and does not raise, which leaves the callers able to tell "nothing is declared" from "the reader crashed"
    and to refuse on the first. `test_the_real_derivation_is_not_empty` below is that refusal, and this case is what makes it reachable.
    """
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert xdist_groups.real_tree_twins(broken) == set()
    assert xdist_groups.real_tree_twins(tmp_path / "absent.json") == set()


# --------------------------------------------------------------------------- The real tree ---------------------------------------------------------------------------


def test_the_real_derivation_is_not_empty() -> None:
    """ANTI-VACUITY, and it is the one floor that is honest today.

    An empty set makes `test_no_ported_twin_is_a_real_tree_writer_or_scanner` admit every twin including the four that rewrite tracked files, and makes the group derivation unable to serialise anything. Zero GROUPS is the correct answer on this tree; zero KNOWN REAL-TREE TESTS is a broken reader.
    """
    assert xdist_groups.real_tree_twins(REAL_LOCK) != set()


def test_the_parity_test_and_the_scheduler_read_the_same_set() -> None:
    """THE NO-DRIFT CLAIM, asserted rather than assumed.

    `test_twin_parity.real_tree_tests` is now a call into this module. If someone reinstates a local copy there, the two will agree on the day it is written and diverge later, which is the failure mode that made moving it worth doing.
    """
    assert test_twin_parity.real_tree_tests() == xdist_groups.real_tree_twins(REAL_LOCK)


def test_the_ported_corpus_agrees_with_the_parity_test_about_who_is_unsafe() -> None:
    """SET-BASED, and green whether the answer is empty or not.

    `test_twin_parity` fails the port when a ported module's twin is in the set; the scheduler sends exactly those modules to one worker. The two sets are computed here from opposite ends and must be equal -- so this stays true the day the first real-tree twin is ported, instead of being a hardcoded 0 that would have to be edited then.
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
    """Precedence, stated in the module docstring and asserted here: a module may name its own resource without also being a real-tree twin."""
    module = _Module(XDIST_GROUP="ports", BASH_TWIN=".ci/scripts/test/gates/test-writes.sh")
    assert xdist_groups.group_for(module, {"test-writes.sh"}) == "ports"


def test_a_twin_in_the_real_tree_set_gets_the_shared_group() -> None:
    module = _Module(BASH_TWIN=".ci/scripts/test/gates/test-writes.sh")
    assert xdist_groups.group_for(module, {"test-writes.sh"}) == xdist_groups.REAL_TREE_GROUP


def test_two_real_tree_twins_get_the_same_group_not_two_groups() -> None:
    """Two groups may run on two workers at once, so a reader and a writer in different groups is exactly the collision being prevented. One name."""
    unsafe = {"test-writes.sh", "test-scans.sh"}
    first = xdist_groups.group_for(_Module(BASH_TWIN="a/test-writes.sh"), unsafe)
    second = xdist_groups.group_for(_Module(BASH_TWIN="b/test-scans.sh"), unsafe)
    assert first == second


def test_a_twin_outside_the_real_tree_set_is_ungrouped() -> None:
    """CONTROL, and the important one: ungrouped items distribute FREELY. A derivation that grouped everything would be green and serial."""
    module = _Module(BASH_TWIN=".ci/scripts/test/gates/test-quiet.sh")
    assert xdist_groups.group_for(module, {"test-writes.sh"}) is None


def test_a_module_declaring_neither_is_ungrouped() -> None:
    assert xdist_groups.group_for(_Module(), {"test-writes.sh"}) is None


def test_an_empty_group_string_is_not_a_group() -> None:
    """CONTROL. `XDIST_GROUP = ""` would otherwise become a real group named the
    empty string, silently serialising the module against every other module that got it wrong the same way."""
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

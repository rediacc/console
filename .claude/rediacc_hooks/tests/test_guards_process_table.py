"""The guards differential's PROCESS-TABLE half: the only cases that must share one xdist worker.

WHY THIS FILE EXISTS (agent/plans/PLAN-prepush-full-cpu.md PF11). Until 2026-10-05 `test_guards_differential.py` declared `XDIST_GROUP = "hooks-guards"` at module level, and the repo-root conftest groups whole MODULES, so all of its roughly 6,900 items (461 s of test time, measured from the 2026-10-03 junit) ran on ONE worker. That was the floor of check:ci-pytest: no core count could move it. The reason for the group was narrow:

  * three guards read the REAL process table (`PROCESS_TABLE_READERS` in the
    differential): `block_self_matching_pgrep`, `block_bash_write_to_running_script`
    and `block_edit_of_running_script`;
  * `test_hooks_procs.py` spawns real `sleep 8` processes visible to that same
    table, and two workers building the fixed-path running-script world killed
    each other's shells (#af1d1d05).

No other guard reads the process table, so only those three guards' cases need the group. They live here now, with `XDIST_GROUP = "hooks-guards"`, beside `test_hooks_procs.py`'s marked cases; everything else in the differential distributes per item.

THE ASSERTIONS ARE THE DIFFERENTIAL'S OWN, UNCHANGED. Every test below calls the differential's helpers (`python_fields`, `golden_for`, `case_env`, ...) through the module object, never by importing a `test_*` name into this namespace (pytest would collect it a second time here). The two anti-vacuity controls are parametrised per guard in both files: a guard's verdict depends only on its own cases, so splitting the loop by stem changes scheduling and nothing else. `test_the_partition_covers_every_guard` is what proves the two halves together still cover every guard exactly once.
"""

import pytest

from rediacc_hooks import guards
from rediacc_hooks.tests import test_guards_differential as gd

# The group name `test_hooks_procs.py` imports. One spelling: two would be two groups, which may run concurrently.
XDIST_GROUP = "hooks-guards"

READER_STEMS = sorted(gd.PROCESS_TABLE_READERS)


@pytest.fixture(scope="session")
def fixture_work(tmp_path_factory):
    """This module's own world root; the differential's fixture of the same name is the same shape, built by the same helpers."""
    return tmp_path_factory.mktemp("guard-process-table-fixtures")


def test_the_partition_covers_every_guard():
    """CONTROL. The readers are real guards, and the two files' per-guard controls together cover every guard exactly once.

    A reader renamed or deleted would otherwise leave its stem in `PROCESS_TABLE_READERS` with no cases here, and this file would go green having run nothing.
    """
    stems = set(guards.stems())
    missing = sorted(gd.PROCESS_TABLE_READERS - stems)
    assert not missing, "PROCESS_TABLE_READERS names guards that do not exist: %s" % missing
    assert set(gd.SPREAD_STEMS) | set(READER_STEMS) == stems
    assert not set(gd.SPREAD_STEMS) & set(READER_STEMS)
    assert [c for c in gd.GOLDEN_CASES if c[0] in gd.PROCESS_TABLE_READERS], (
        "no golden case belongs to a process-table reader, so this file compares nothing"
    )


def test_a_dead_process_world_is_rebuilt(fixture_work):
    """A running-script world whose shells died comes back before the next case (#af1d1d05)."""
    stem = "block_bash_write_to_running_script"
    module = guards.load(stem)
    extra = {label: env for label, env, _ in gd.environments(module)}["running"]
    gd.case_env(stem, extra, {}, fixture_work)
    assert module._CHILDREN, "the world spawned no shells, so there is nothing to revive"
    assert not gd._revive_process_world(stem), "a live world was rebuilt for no reason"
    module._reap()
    for child in module._CHILDREN:
        child.wait(timeout=10)
    gd.case_env(stem, extra, {}, fixture_work)
    assert module._CHILDREN
    assert all(c.poll() is None for c in module._CHILDREN)
    payload = gd.edge_payload(module, "echo x > %s" % module.LIVE_SCRIPT)
    assert gd.python_fields(stem, payload, extra, {}, fixture_work)["rc"] == "2"


@pytest.mark.parametrize(
    ("stem", "label", "payload", "extra", "stubs"),
    [
        pytest.param(c[0], c[1], c[2], c[4], c[5], id="%s|%s" % (c[0], c[1]))
        for c in gd.GOLDEN_CASES
        if c[0] in gd.PROCESS_TABLE_READERS
    ],
)
def test_guard_matches_golden(fixture_work, stem, label, payload, extra, stubs):
    gd.assert_matches_golden(fixture_work, stem, label, payload, extra, stubs)


@pytest.mark.parametrize("stem", READER_STEMS)
def test_every_guard_discriminates(fixture_work, stem):
    """The differential's discrimination control, for one process-table reader (see its docstring)."""
    gd.assert_discriminates(fixture_work, stem)


@pytest.mark.parametrize("stem", READER_STEMS)
def test_the_differential_can_fail(tmp_path, fixture_work, stem):
    """The differential's planted-defect control, for one process-table reader (see its docstring)."""
    gd.assert_defect_is_caught(tmp_path, fixture_work, stem)

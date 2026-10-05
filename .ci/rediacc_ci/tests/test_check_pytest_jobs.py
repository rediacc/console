"""`check_pytest.jobs()`: the worker count is sized from the cores granted at launch, never from a constant.

Operator ruling 2026-10-05 (agent/plans/PLAN-prepush-full-cpu.md, PF4): no static worker counts in any local or CI lane. The pytest lane used to run `min(8, os.cpu_count())` workers (`PYTEST_JOBS_CAP = 8`) with a matching `weight: 8` in the manifest; it now reads `core_lease.granted_cores()`, which is the runner's `CI_RUNNER_CORES` grant when one was made, else the CPUs this process may run on.

THE PLANTED DEFECT these tests were written against, red before the fix and green after: restoring `PYTEST_JOBS_CAP = 8` and `min(PYTEST_JOBS_CAP, ...)` makes the 12-core grant come out as 8 and the 24-core affinity as 8, and both tests below red.

The host's real core count is never assumed: every case pins the affinity mask and the cpu count it is judged against, so the controls fire the same way on a 2-core CI runner as on a 24-core workstation.
"""

import os

import pytest

from rediacc_ci import battery, check_pytest, core_lease, log
from rediacc_ci.quality import literal_sources

#: Larger than the old cap of 8 on purpose, so a cap restored anywhere in the chain is visible as a smaller number.
WIDE = 24


@pytest.fixture
def wide_host(monkeypatch):
    """A host that lets this process run on WIDE cores, with no grant and no override in the environment."""
    monkeypatch.delenv("PYTEST_JOBS", raising=False)
    monkeypatch.delenv(core_lease.ENV, raising=False)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _pid: set(range(WIDE)), raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: WIDE)
    return monkeypatch


def test_a_runner_grant_of_twelve_gives_twelve_workers(wide_host) -> None:
    """The scheduler granted 12 cores at launch, so pytest runs exactly 12 workers: not the old cap of 8, and not every core on the host."""
    wide_host.setenv(core_lease.ENV, "12")
    assert check_pytest.jobs() == 12


@pytest.mark.usefixtures("wide_host")
def test_no_grant_gives_the_affinity_count() -> None:
    """Run standalone (no runner, as in a CI leg's own step), pytest sizes itself to the cores this process may run on."""
    assert check_pytest.jobs() == WIDE


def test_the_affinity_mask_wins_over_the_host_count(wide_host) -> None:
    """A container or taskset mask of 3 cores on a 24-core host means 3 workers; `os.cpu_count()` would have claimed all 24."""
    wide_host.setattr(os, "sched_getaffinity", lambda _pid: {0, 1, 2}, raising=False)
    assert check_pytest.jobs() == 3


def test_pytest_jobs_still_overrides_the_grant(wide_host) -> None:
    """`PYTEST_JOBS` is the caller's own number (1 is serial) and wins over any grant."""
    wide_host.setenv(core_lease.ENV, "12")
    wide_host.setenv("PYTEST_JOBS", "1")
    assert check_pytest.jobs() == 1


def test_a_malformed_override_falls_back_to_the_grant(wide_host) -> None:
    """CONTROL in the other direction: a non-numeric or zero `PYTEST_JOBS` is not an override, so it must not become a worker count of its own."""
    wide_host.setenv(core_lease.ENV, "12")
    for bad in ("eight", "0", ""):
        wide_host.setenv("PYTEST_JOBS", bad)
        assert check_pytest.jobs() == 12, bad


def test_no_static_cap_survives_in_the_module() -> None:
    """The constant is gone, not merely unused, so nothing can re-adopt it by name."""
    assert not hasattr(check_pytest, "PYTEST_JOBS_CAP")


# --------------------------------------------------------------------------- PF6: the two other gate-side pools read the same grant ---------------------------------------------------------------------------


def test_battery_default_width_is_the_grant(wide_host) -> None:
    """`battery._default_jobs()` was `min(8, os.cpu_count())`; restoring that cap makes 12 come out as 8."""
    wide_host.setenv(core_lease.ENV, "12")
    assert battery._default_jobs() == 12
    wide_host.delenv(core_lease.ENV)
    assert battery._default_jobs() == WIDE


def test_literal_sources_pool_width_is_the_grant(wide_host) -> None:
    """`literal_sources.classify_all`'s pool was `min(8, os.cpu_count())`; it is the grant now."""
    wide_host.setenv(core_lease.ENV, "12")
    assert literal_sources.pool_width() == 12
    wide_host.delenv(core_lease.ENV)
    assert literal_sources.pool_width() == WIDE


_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="5">
<testcase classname=".ci.rediacc_ci.tests.test_a" name="test_ok" time="0.1"/>
<testcase classname=".ci.rediacc_ci.tests.test_a" name="test_broken[db]@some-group" time="0.1"><failure message="boom"/></testcase>
<testcase classname=".ci.rediacc_ci.tests.test_a" name="test_erred" time="0.1"><error message="setup"/></testcase>
<testcase classname=".ci.rediacc_ci.tests.test_b" name="test_host_only[x y]" time="0"><skipped message="ruff disables EXE001 under WSL"/></testcase>
<testcase classname=".ci.rediacc_ci.tests.test_b" name="test_proxy" time="0"><skipped message="proxy p: CANNOT RUN (1 of 2 requirement(s) missing)"/></testcase>
</testsuite></testsuites>
"""


def test_a_red_run_keys_each_failure_and_each_uncontracted_skip(tmp_path):
    """check:ci-pytest emitted no finding keys, so its carry had to be `*`, and the wildcard carried seven real failures through a push (2026-10-05)."""
    junit = tmp_path / "junit.xml"
    junit.write_text(_JUNIT, encoding="utf-8")
    assert check_pytest.junit_finding_keys(junit) == [
        "pytest-fail:.ci.rediacc_ci.tests.test_a::test_broken#db#",
        "pytest-fail:.ci.rediacc_ci.tests.test_a::test_erred",
        "pytest-skip:.ci.rediacc_ci.tests.test_b::test_host_only#x#y#",
    ]


def test_every_key_is_in_the_finding_alphabet_and_an_unreadable_junit_keys_nothing(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text(_JUNIT.replace("test_erred", "test_" + "x" * 300), encoding="utf-8")
    keys = check_pytest.junit_finding_keys(junit)
    assert all(log.FINDING_KEY_RE.match(k) for k in keys), keys
    assert check_pytest.junit_finding_keys(tmp_path / "absent.xml") == []

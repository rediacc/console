"""A pytest plugin that writes each test's phase durations (setup, call, teardown) and the share of its setup spent in shared fixtures to a JSON file, for the slow-test ratchet.

WHY (2026-11-18). junit records one `time` per test, the sum of its setup, call and teardown, so a module-scoped fixture's setup lands on whichever test of the module runs first: `test_githook_generated_artifacts::test_enrolled_artifact_against_the_real_hook[enrolled_allowed-skill-reference]` read 16.9 s as a median of three runs while its own call took 2-4 s, the other ~13 s being the module's `world` fixture. The ratchet judges the test, not the fixture it happened to be first to request, so it needs the phases apart.

LOADED BY `-p rediacc_ci.quality.pytest_phase_timing --phase-timing <path>` (`check_pytest.phase_args`). Without `--phase-timing` the plugin records nothing and writes nothing. Under xdist the plugin runs in every worker, where it measures the shared-fixture share of each setup and carries it on the setup report (`shared_setup_s`, an extra report attribute xdist serialises to the controller), and the controller, the one process that is not a worker, collects the reports and writes the file once at the end of the session.

SHARED MEANS ANY SCOPE BUT `function`. `pytest_fixture_setup` is timed per fixture, and pytest resolves a fixture's dependencies before that hook runs (`FixtureDef.execute`), so each timing is the fixture's own, never its dependencies'. A module, class, package or session fixture set up during a test's setup is that test's `shared_setup_s`; everything else in the setup phase (function-scoped fixtures, autouse ones, the setup machinery) stays the test's own.

THE FILE: `{"version": 1, "tests": {<junit node>: {"nodeid", "setup", "call", "teardown", "shared_setup", "shared_teardown"}}}`, keyed by the `<classname>::<name>` junit node `pytest_slow_ratchet.node_of` reads, so a junit case and its phases join on one key. `shared_setup` and `shared_teardown` are null when no worker measured them (the plugin was not loaded there), which the ratchet reads as zero: an unmeasured share is charged to the test, never excused. A wider-scoped fixture's teardown lands on the last test of its scope, so it is timed the same way as setup (the gap between finalizers, `pytest_fixture_post_finalizer`).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import resource
import tempfile
import time
import typing

import pytest

if typing.TYPE_CHECKING:
    from collections.abc import Generator

VERSION = 1
OPTION = "--phase-timing"
SHARED_ATTR = "shared_setup_s"
SHARED_TEARDOWN_ATTR = "shared_teardown_s"
CPU_ATTR = "cpu_s"
SHARED_CPU_ATTR = "shared_setup_cpu_s"
SHARED_TEARDOWN_CPU_ATTR = "shared_teardown_cpu_s"
_PY_SUFFIX_RE = re.compile(r"\.py$")
# Kept equal to `pytest_slow_ratchet.GROUP_SUFFIX_RE` (a test pins the parity): the trailing xdist `@group`, never an `@` inside a `[...]` parameter id.
GROUP_SUFFIX_RE = re.compile(r"@[^@\]]*$")


def cpu_seconds() -> float:
    """CPU seconds of this process plus every child it has waited for (user + system).

    The slow-test ratchet judges CPU rather than wall time (PLAN-ciquick-gate-contract K4): on 2026-11-28 the wall clock reddened a different set of 10.1-16 s tests on every ci:quick run while the machine ran the rest of the lane. Most slow tests here drive git, tsx or python subprocesses, so a waited child's CPU is the test's own work and counts.
    """
    me = resource.getrusage(resource.RUSAGE_SELF)
    kids = resource.getrusage(resource.RUSAGE_CHILDREN)
    return me.ru_utime + me.ru_stime + kids.ru_utime + kids.ru_stime


def junit_node(nodeid: str) -> str:
    """The `<classname>::<name>` junit names a pytest node id by, the xdist `@group` suffix dropped.

    The same mangling `_pytest.junitxml.mangle_test_address` applies (the file path dotted, `.py` dropped, the dotted parts past the file being test classes), so the key matches the junit case of the same test.
    """
    path, bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = _PY_SUFFIX_RE.sub("", names[0].replace("/", "."))
    names[-1] += bracket + params
    name = GROUP_SUFFIX_RE.sub("", names[-1])
    return "%s::%s" % (".".join(names[:-1]), name)


class PhaseTiming:
    """The plugin object `pytest_configure` registers, one per process. Each hook takes only the arguments it reads, which pluggy allows."""

    def __init__(self, out: pathlib.Path | None) -> None:
        self.out = out
        self.tests: dict[str, dict[str, typing.Any]] = {}
        self._shared = 0.0
        self._shared_teardown = 0.0
        self._mark = 0.0
        self._shared_cpu = 0.0
        self._shared_teardown_cpu = 0.0
        self._mark_cpu = 0.0
        self._phase_cpu: dict[str, float] = {}

    def _timed_phase(self, when: str) -> Generator[None, object, object]:
        started = cpu_seconds()
        try:
            return (yield)
        finally:
            self._phase_cpu[when] = cpu_seconds() - started

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_call(self) -> Generator[None, object, object]:
        return (yield from self._timed_phase("call"))

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_teardown(self) -> Generator[None, object, object]:
        self._shared_teardown = 0.0
        self._shared_teardown_cpu = 0.0
        self._mark = time.perf_counter()
        self._mark_cpu = cpu_seconds()
        return (yield from self._timed_phase("teardown"))

    def pytest_fixture_post_finalizer(self, fixturedef) -> None:
        # Finalizers run one after another, so the gap since the last one (or the start of teardown) is this fixture's own finish.
        now = time.perf_counter()
        now_cpu = cpu_seconds()
        if fixturedef.scope != "function":
            self._shared_teardown += now - self._mark
            self._shared_teardown_cpu += now_cpu - self._mark_cpu
        self._mark = now
        self._mark_cpu = now_cpu

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_setup(self) -> Generator[None, object, object]:
        self._shared = 0.0
        self._shared_cpu = 0.0
        self._phase_cpu = {}
        return (yield from self._timed_phase("setup"))

    @pytest.hookimpl(wrapper=True)
    def pytest_fixture_setup(self, fixturedef) -> Generator[None, object, object]:
        started = time.perf_counter()
        started_cpu = cpu_seconds()
        try:
            return (yield)
        finally:
            if fixturedef.scope != "function":
                self._shared += time.perf_counter() - started
                self._shared_cpu += cpu_seconds() - started_cpu

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(self, call) -> Generator[None, object, object]:
        report = yield
        if call.when in self._phase_cpu:
            setattr(report, CPU_ATTR, self._phase_cpu[call.when])
        if call.when == "setup":
            setattr(report, SHARED_ATTR, self._shared)
            setattr(report, SHARED_CPU_ATTR, self._shared_cpu)
        elif call.when == "teardown":
            setattr(report, SHARED_TEARDOWN_ATTR, self._shared_teardown)
            setattr(report, SHARED_TEARDOWN_CPU_ATTR, self._shared_teardown_cpu)
        return report

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if self.out is None:
            return
        entry = self.tests.setdefault(
            junit_node(report.nodeid),
            {
                "nodeid": report.nodeid,
                "setup": 0.0,
                "call": 0.0,
                "teardown": 0.0,
                "shared_setup": None,
                "shared_teardown": None,
            },
        )
        entry[report.when] = float(report.duration)
        cpu = getattr(report, CPU_ATTR, None)
        if cpu is not None:
            entry[report.when + "_cpu"] = float(cpu)
        if report.when == "setup":
            shared = getattr(report, SHARED_ATTR, None)
            entry["shared_setup"] = float(shared) if shared is not None else None
            shared_cpu = getattr(report, SHARED_CPU_ATTR, None)
            if shared_cpu is not None:
                entry["shared_setup_cpu"] = float(shared_cpu)
        elif report.when == "teardown":
            shared = getattr(report, SHARED_TEARDOWN_ATTR, None)
            entry["shared_teardown"] = float(shared) if shared is not None else None
            shared_cpu = getattr(report, SHARED_TEARDOWN_CPU_ATTR, None)
            if shared_cpu is not None:
                entry["shared_teardown_cpu"] = float(shared_cpu)

    def pytest_sessionfinish(self) -> None:
        if self.out is None:
            return
        self.out.parent.mkdir(parents=True, exist_ok=True)
        # Written beside the target and renamed over it, so a reader never sees half a file.
        fd, tmp = tempfile.mkstemp(prefix=self.out.name + ".", dir=self.out.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"version": VERSION, "tests": self.tests}, handle, sort_keys=True)
        pathlib.Path(tmp).replace(self.out)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        OPTION,
        default=None,
        metavar="PATH",
        help="write each test's setup/call/teardown seconds and its shared-fixture setup to PATH (JSON)",
    )


def pytest_configure(config: pytest.Config) -> None:
    raw = config.getoption(OPTION)
    # Only the controller writes: an xdist worker carries `workerinput`, and its reports reach the controller's logreport anyway.
    out = pathlib.Path(raw) if raw and not hasattr(config, "workerinput") else None
    config.pluginmanager.register(PhaseTiming(out), "rediacc-phase-timing")

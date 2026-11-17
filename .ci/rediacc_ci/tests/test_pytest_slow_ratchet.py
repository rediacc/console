"""`pytest_slow_ratchet`: a test over 10 s fails unless the allowlist lists it with a reason.

The fixtures write junit files in pytest's own shape, so the 11 s test is a recorded duration rather than a sleep: a test that slept 11 s would itself be the thing this ratchet refuses.
"""

import json
import pathlib

import pytest

from rediacc_ci.policy_paths import policy_path
from rediacc_ci.quality import pytest_slow_ratchet as ratchet


def _junit(
    path: pathlib.Path, times: dict[str, float], skipped: tuple[str, ...] = ()
) -> pathlib.Path:
    cases = []
    for name, seconds in times.items():
        body = "<skipped/>" if name in skipped else ""
        cases.append(
            '<testcase classname="pkg.test_mod" name="%s" time="%s">%s</testcase>'
            % (name, seconds, body)
        )
    path.write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="pytest">%s</testsuite></testsuites>'
        % "".join(cases),
        encoding="utf-8",
    )
    return path


def _allow(path: pathlib.Path, entries: list[dict]) -> pathlib.Path:
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def _run(tmp_path, capsys, junits, entries, *extra):
    allow = _allow(tmp_path / "allow.json", entries)
    argv = [a for j in junits for a in ("--junit", str(j))]
    rc = ratchet.main([*argv, "--allow", str(allow), *extra])
    return rc, capsys.readouterr()


def test_a_test_over_ten_seconds_fails_the_check(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_fast": 0.2, "test_slept_eleven": 11.0})
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 1
    assert "pkg.test_mod::test_slept_eleven took 11.0 s" in out.err
    assert "::finding::pytest-slow:pkg.test_mod::test_slept_eleven" in out.err
    assert "test_fast" not in out.err


def test_control_a_test_at_exactly_ten_seconds_passes(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_edge": 10.0, "test_fast": 0.1})
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 0, out.err


def test_control_the_same_slow_test_passes_once_listed_with_a_reason(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_slept_eleven": 11.0})
    entry = {"test": "pkg.test_mod::test_slept_eleven", "reason": "drives a real build"}
    rc, out = _run(tmp_path, capsys, [junit], [entry])
    assert rc == 0, out.err


def test_an_entry_without_a_reason_does_not_admit_the_test(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_slept_eleven": 11.0})
    rc, out = _run(
        tmp_path, capsys, [junit], [{"test": "pkg.test_mod::test_slept_eleven", "reason": "  "}]
    )
    assert rc == 1
    assert "carries no reason" in out.err
    assert "::finding::pytest-slow:pkg.test_mod::test_slept_eleven" in out.err


def test_the_median_of_three_runs_is_judged_not_the_worst(tmp_path, capsys):
    runs = [
        _junit(tmp_path / ("r%d.xml" % i), {"test_noisy": t})
        for i, t in enumerate((4.0, 4.5, 30.0))
    ]
    rc, out = _run(tmp_path, capsys, runs, [])
    assert rc == 0, out.err
    slow = [
        _junit(tmp_path / ("s%d.xml" % i), {"test_noisy": t})
        for i, t in enumerate((12.0, 11.0, 3.0))
    ]
    rc, out = _run(tmp_path, capsys, slow, [])
    assert rc == 1
    assert "test_noisy took 11.0 s" in out.err


def test_a_stale_entry_is_reported_and_fails_only_when_strict(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_now_fast": 0.3})
    entry = {"test": "pkg.test_mod::test_now_fast", "reason": "was slow"}
    rc, out = _run(tmp_path, capsys, [junit], [entry])
    assert rc == 0
    assert "now runs under 10 s; drop the entry" in out.err
    rc, out = _run(tmp_path, capsys, [junit], [entry], "--strict-stale")
    assert rc == 1
    assert "::finding::pytest-slow-stale:pkg.test_mod::test_now_fast" in out.err


def test_a_skipped_slow_test_is_not_judged(tmp_path, capsys):
    junit = _junit(
        tmp_path / "j.xml", {"test_skipped": 99.0, "test_ok": 0.1}, skipped=("test_skipped",)
    )
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 0, out.err


@pytest.mark.parametrize(
    "content", [None, "<not xml", '<testsuites><testsuite name="x"/></testsuites>']
)
def test_no_readable_test_case_is_no_verdict_not_a_pass(tmp_path, capsys, content):
    junit = tmp_path / "j.xml"
    if content is not None:
        junit.write_text(content, encoding="utf-8")
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 2
    assert "no verdict" in out.err


def test_the_real_allowlist_is_well_formed_and_every_entry_has_a_reason():
    allow = policy_path(ratchet.ALLOW_NAME)
    allowed, problems = ratchet.read_allow(allow)
    assert not problems, problems
    assert allowed, "an empty allowlist would make the baseline claim nothing"
    assert all(reason.strip() for reason in allowed.values())


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    for rel in (".ci/pkg/tests/test_hidden.py", "pkg/test_mod.py"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("node", "nodeid"),
    [
        (".ci.pkg.tests.test_hidden::test_a[x/y z]", ".ci/pkg/tests/test_hidden.py::test_a[x/y z]"),
        ("pkg.test_mod.TestCls::test_b", "pkg/test_mod.py::TestCls::test_b"),
        ("pkg.test_mod::test_c", "pkg/test_mod.py::test_c"),
    ],
)
def test_a_junit_node_maps_to_the_pytest_node_id_of_its_file(tmp_path, node, nodeid):
    assert ratchet.nodeid_of(node, _tree(tmp_path)) == nodeid


def test_control_a_node_with_no_file_under_the_root_maps_to_nothing(tmp_path):
    assert ratchet.nodeid_of("pkg.test_gone::test_c", _tree(tmp_path)) is None


def test_the_confirm_candidates_are_the_unlisted_slow_tests_with_a_file(tmp_path):
    root = _tree(tmp_path)
    junit = _junit(tmp_path / "j.xml", {"test_slow": 11.0, "test_listed": 12.0, "test_fast": 2.0})
    allow = _allow(
        tmp_path / "allow.json", [{"test": "pkg.test_mod::test_listed", "reason": "real build"}]
    )
    assert ratchet.confirm_candidates(junit, root, allow) == ["pkg/test_mod.py::test_slow"]
    (root / "pkg" / "test_mod.py").unlink()
    assert ratchet.confirm_candidates(junit, root, allow) == []


# A module-scoped fixture's setup lands on the first test of its module in junit; the phase file beside the junit separates it.
HEAVY_FIRST = {"setup": 14.0, "call": 2.9, "teardown": 0.0, "shared_setup": 13.0}


def _phases(junit: pathlib.Path, tests: dict[str, dict]) -> pathlib.Path:
    path = ratchet.phases_path(junit)
    doc = {"version": 1, "tests": {"pkg.test_mod::%s" % n: dict(p) for n, p in tests.items()}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_the_phase_file_sits_beside_its_junit(tmp_path):
    assert ratchet.phases_path(tmp_path / "junit.xml") == tmp_path / "junit.phases.json"


def test_a_fixture_heavy_first_test_with_a_fast_call_passes(tmp_path, capsys):
    """THE BEHAVIOUR: junit reads 16.9 s, 13 s of it the module fixture's setup; the test's own time is 1 + 2.9 s. Judged on junit time alone it failed."""
    junit = _junit(tmp_path / "j.xml", {"test_first": 16.9, "test_second": 0.2})
    _phases(junit, {"test_first": HEAVY_FIRST})
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 0, out.err
    assert "1 test(s) in" in out.out, "test_second has no phase entry and is named as such"
    assert (
        "info: pkg.test_mod spent 13.0 s in shared (module, class or session) fixture setup"
        in out.out
    )


def test_control_a_genuinely_slow_call_still_fails(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_slow_call": 11.2})
    _phases(
        junit,
        {"test_slow_call": {"setup": 0.1, "call": 11.0, "teardown": 0.1, "shared_setup": 0.0}},
    )
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 1
    assert "pkg.test_mod::test_slow_call took 11.2 s" in out.err


def test_control_a_slow_function_scoped_setup_stays_the_tests_own(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_own_fixture": 11.5})
    _phases(
        junit,
        {"test_own_fixture": {"setup": 11.0, "call": 0.5, "teardown": 0.0, "shared_setup": 0.0}},
    )
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 1
    assert "test_own_fixture took 11.5 s" in out.err


def test_an_unmeasured_shared_setup_is_charged_to_the_test(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_first": 16.9})
    _phases(junit, {"test_first": {**HEAVY_FIRST, "shared_setup": None}})
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 1
    assert "test_first took 16.9 s" in out.err


@pytest.mark.parametrize("content", [None, "{not json", '{"version": 1}'])
def test_no_usable_phase_file_falls_back_to_junit_time_and_says_so(tmp_path, capsys, content):
    junit = _junit(tmp_path / "j.xml", {"test_first": 16.9})
    if content is not None:
        ratchet.phases_path(junit).write_text(content, encoding="utf-8")
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 1, "a missing measurement must not pass the test"
    assert "test_first took 16.9 s" in out.err
    assert "note:" in out.out
    assert "judged on their junit time" in out.out


def test_a_case_missing_from_its_phase_file_is_judged_on_junit_time_and_counted(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_first": 16.9, "test_unphased": 12.0})
    _phases(junit, {"test_first": HEAVY_FIRST})
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 1
    assert "test_unphased took 12.0 s" in out.err
    assert "1 test(s) in %s have no entry" % junit in out.out


def test_the_median_is_taken_over_own_times_across_runs(tmp_path, capsys):
    """Each run's own time joins the median: the parallel run's junit-only 16.9 s is outvoted by two phased re-times."""
    runs = [_junit(tmp_path / ("r%d.xml" % i), {"test_first": 16.9}) for i in range(3)]
    for run in runs[1:]:
        _phases(run, {"test_first": HEAVY_FIRST})
    rc, out = _run(tmp_path, capsys, runs, [])
    assert rc == 0, out.err
    assert "no phase file at %s" % ratchet.phases_path(runs[0]) in out.out


def test_the_confirm_candidates_skip_a_test_whose_own_time_is_fast(tmp_path):
    root = _tree(tmp_path)
    junit = _junit(tmp_path / "j.xml", {"test_first": 16.9, "test_slow": 11.0})
    _phases(junit, {"test_first": HEAVY_FIRST, "test_slow": {"setup": 0.0, "call": 11.0}})
    allow = _allow(tmp_path / "allow.json", [])
    assert ratchet.confirm_candidates(junit, root, allow) == ["pkg/test_mod.py::test_slow"]


def test_a_slow_own_teardown_is_judged_as_the_tests_own(tmp_path, capsys):
    """Finding 7d7ecd77.1: a function-scoped fixture's own 12 s teardown is the test's time."""
    junit = _junit(tmp_path / "j.xml", {"test_td": 12.2})
    _phases(
        junit,
        {
            "test_td": {
                "setup": 0.1,
                "call": 0.1,
                "teardown": 12.0,
                "shared_setup": 0.0,
                "shared_teardown": 0.0,
            }
        },
    )
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 1
    assert "pkg.test_mod::test_td took 12.2 s" in out.err


def test_control_a_module_fixtures_teardown_on_the_last_test_is_not_its_own(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_last": 12.2})
    _phases(
        junit,
        {
            "test_last": {
                "setup": 0.1,
                "call": 0.1,
                "teardown": 12.0,
                "shared_setup": 0.0,
                "shared_teardown": 11.9,
            }
        },
    )
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 0, out.err


def test_control_an_unmeasured_shared_teardown_is_charged_to_the_test(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_last": 12.2})
    _phases(junit, {"test_last": {"setup": 0.1, "call": 0.1, "teardown": 12.0}})
    rc, _out = _run(tmp_path, capsys, [junit], [])
    assert rc == 1


def test_a_malformed_phase_entry_is_named_malformed_not_missing(tmp_path, capsys):
    """Finding 7d7ecd77.4: the entry exists but holds no usable number, so the note must not say it has no entry."""
    junit = _junit(tmp_path / "j.xml", {"test_bad": 1.0})
    _phases(junit, {"test_bad": {"setup": "x", "call": 1.0}})
    rc, out = _run(tmp_path, capsys, [junit], [])
    assert rc == 0
    assert "malformed entry" in out.out
    assert "have no entry" not in out.out


def test_control_a_missing_phase_entry_is_still_named_missing(tmp_path, capsys):
    junit = _junit(tmp_path / "j.xml", {"test_bad": 1.0, "test_other": 1.0})
    _phases(junit, {"test_other": {"setup": 0.0, "call": 1.0}})
    _rc, out = _run(tmp_path, capsys, [junit], [])
    assert "have no entry" in out.out
    assert "malformed" not in out.out


def test_the_shared_report_groups_by_classname_including_the_class_part():
    """Finding 7d7ecd77.3: the rows are per junit classname, which carries a test class, as the docstring says."""
    rows = ratchet.shared_by_file({"t.test_heavy.TestSlow::a": 3.0, "t.test_heavy::b": 2.0})
    assert rows == [("t.test_heavy.TestSlow", 3.0), ("t.test_heavy", 2.0)]

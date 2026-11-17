"""`pytest_slow_ratchet`: a test over 10 s fails unless the allowlist lists it with a reason.

The fixtures write junit files in pytest's own shape, so the 11 s test is a recorded duration rather than a sleep: a test that slept 11 s would itself be the thing this ratchet refuses.
"""

import json
import pathlib

import pytest

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
    allow = ratchet.paths.repo_root() / ratchet.ALLOW_RELPATH
    allowed, problems = ratchet.read_allow(allow)
    assert not problems, problems
    assert allowed, "an empty allowlist would make the baseline claim nothing"
    assert all(reason.strip() for reason in allowed.values())

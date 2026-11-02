"""`check_pytest.main()` emits a `pytest-fail` finding only for a junit this run wrote.

On 2026-10-31 a `ci:quick` run hit the whole-corpus timeout, so pytest was killed before it wrote `.ci/cache/quality-pytest/junit.xml`, and the gate emitted 30 `::finding::pytest-fail:` keys read from the junit an earlier run had left there three days before. Those named tests passed when they were run alone. `main()` now removes the junit before pytest runs.

THE PLANTED DEFECT: delete the junit `unlink(missing_ok=True)` line before the unsharded `run_pytest` call, and the first test below reds with the stale key; delete the one before the sharded call, and the sharded test reds the same way. The second test is the control: a junit the run itself writes still yields its finding, so the first test cannot pass just because findings went away.
"""

import pathlib

import pytest

from rediacc_ci import check_pytest, log

STALE_NODE = "stale.module::test_from_an_earlier_run"
FRESH_NODE = "fresh.module::test_from_this_run"


def _junit(node: str) -> str:
    classname, name = node.split("::")
    return (
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
        '<testcase classname="%s" name="%s"><failure message="boom"/></testcase>'
        "</testsuite></testsuites>" % (classname, name)
    )


@pytest.fixture
def gate(tmp_path: pathlib.Path, monkeypatch):
    """A scratch root with one test path, a resolved pytest and passing controls; `run_pytest` and the emitted findings are the test's to set and read."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["t"]\n', encoding="utf-8"
    )
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "test_one.py").write_text("def test_one():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(check_pytest.paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(check_pytest, "resolve_pytest", lambda _root: "pytest")
    monkeypatch.setattr(check_pytest, "selftest", lambda *_a, **_k: True)
    emitted: list[str] = []
    monkeypatch.setattr(log, "emit_finding", lambda key, *_a, **_k: emitted.append(key))
    junit = check_pytest.junit_xml_path(tmp_path)
    junit.parent.mkdir(parents=True)
    junit.write_text(_junit(STALE_NODE), encoding="utf-8")
    return monkeypatch, junit, emitted


def test_a_timed_out_run_emits_no_finding_from_an_earlier_junit(gate) -> None:
    monkeypatch, _junit_path, emitted = gate
    monkeypatch.setattr(
        check_pytest,
        "run_pytest",
        lambda *_a, **_k: (1, "check_pytest: the suite did not finish within 1s.\n"),
    )
    assert check_pytest.main([]) == check_pytest.EXIT_FAIL
    assert emitted == []


def test_control_a_junit_this_run_writes_still_yields_its_finding(gate) -> None:
    monkeypatch, junit_path, emitted = gate

    def writes_junit(*_a, **_k):
        junit_path.write_text(_junit(FRESH_NODE), encoding="utf-8")
        return 1, "1 failed\n"

    monkeypatch.setattr(check_pytest, "run_pytest", writes_junit)
    assert check_pytest.main([]) == check_pytest.EXIT_FAIL
    assert emitted == ["pytest-fail:%s" % FRESH_NODE]


def test_a_timed_out_shard_leg_emits_no_finding_from_an_earlier_leg_junit(gate) -> None:
    """The sharded path (`--shard-manifest`/`--shard`) keeps its own `junit-shard-<N>.xml`; a leg killed before writing it must not read the one an earlier run left."""
    monkeypatch, junit_path, emitted = gate
    root = junit_path.parent.parent.parent.parent
    manifest = root / "manifest.json"
    manifest.write_text(
        '{"lane": "quality-pytest", "of": 1, "legs": [{"index": 1, "ids": ["pytest:t/test_one.py"]}]}',
        encoding="utf-8",
    )
    leg_junit = check_pytest.junit_xml_path(root, shard_index=1)
    leg_junit.write_text(_junit(STALE_NODE), encoding="utf-8")
    monkeypatch.setattr(
        check_pytest,
        "run_pytest",
        lambda *_a, **_k: (1, "check_pytest: the suite did not finish within 1s.\n"),
    )
    check_pytest.main(["--shard-manifest", str(manifest), "--shard", "1/1"])
    assert emitted == []

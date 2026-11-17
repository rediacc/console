"""`check_pytest.main()` fails a passing run that holds a test over 10 s the allowlist does not list.

Wired in `check_pytest.slow_ratchet`, called after the verdict on the full, sharded and impact paths. The fixture junit is written the way pytest writes it (a recorded `time`), so no test here sleeps 11 s.

THE PLANTED DEFECT: make `slow_ratchet` return 0 unconditionally (the wiring disabled) and every 11 s case reds (the full, the shard and the impact path each have one), and so does the no-junit case, because it goes green too; the 2 s control and the listed case stay green either way, so they cannot be what makes those pass.
"""

import json
import pathlib
import types

import pytest

from rediacc_ci import check_pytest, log
from rediacc_ci.policy_paths import policy_path

SLOW = "slow.module::test_sleeps_eleven"


@pytest.fixture
def gate(tmp_path: pathlib.Path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["t"]\n', encoding="utf-8"
    )
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "test_one.py").write_text("def test_one():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(check_pytest.paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(check_pytest, "resolve_pytest", lambda _root: "pytest")
    monkeypatch.setattr(check_pytest, "selftest", lambda *_a, **_k: True)
    monkeypatch.setattr(check_pytest, "verdict", lambda **_k: None)
    emitted: list[str] = []
    monkeypatch.setattr(log, "emit_finding", lambda key, *_a, **_k: emitted.append(key))
    allow = policy_path("pytest-slow-allow.json", tmp_path)
    allow.parent.mkdir(parents=True, exist_ok=True)
    allow.write_text(json.dumps({"entries": []}), encoding="utf-8")
    return tmp_path, monkeypatch, emitted, allow


def _run_writing(
    gate, node: str, seconds: float, *, shard: bool = False, impact: bool = False
) -> int:
    root, monkeypatch, _emitted, _allow = gate
    classname, name = node.split("::")
    junit = check_pytest.junit_xml_path(root, shard_index=1 if shard else None)

    def writes(*_a, **_k):
        junit.write_text(
            '<?xml version="1.0"?><testsuites><testsuite name="pytest">'
            '<testcase classname="%s" name="%s" time="%s"/></testsuite></testsuites>'
            % (classname, name, seconds),
            encoding="utf-8",
        )
        return 0, "1 passed\n"

    monkeypatch.setattr(check_pytest, "run_pytest", writes)
    if impact:
        selection = types.SimpleNamespace(
            files=["t/test_one.py"], total=1, why={}, reason="fixture", digest="d"
        )
        return check_pytest.run_impact("pytest", root, selection)
    if shard:
        (root / "shard.json").write_text(
            json.dumps(
                {
                    "lane": "quality-pytest",
                    "of": 1,
                    "legs": [{"index": 1, "ids": ["pytest:t/test_one.py"]}],
                }
            ),
            encoding="utf-8",
        )
        return check_pytest.main(["--shard-manifest", "shard.json", "--shard", "1/1"])
    return check_pytest.main([])


def test_a_passing_run_with_an_eleven_second_test_fails_the_gate(gate) -> None:
    assert _run_writing(gate, SLOW, 11.0) == check_pytest.EXIT_FAIL
    assert gate[2] == ["pytest-slow:%s" % SLOW]


def test_control_a_two_second_test_passes(gate) -> None:
    assert _run_writing(gate, SLOW, 2.0) == check_pytest.EXIT_OK
    assert gate[2] == []


def test_control_an_allowlisted_slow_test_passes(gate) -> None:
    gate[3].write_text(
        json.dumps({"entries": [{"test": SLOW, "reason": "fixture: cannot be made fast"}]}),
        encoding="utf-8",
    )
    assert _run_writing(gate, SLOW, 11.0) == check_pytest.EXIT_OK
    assert gate[2] == []


def test_a_run_that_wrote_no_junit_cannot_go_green_past_the_ratchet(gate) -> None:
    _root, monkeypatch, _emitted, _allow = gate
    monkeypatch.setattr(check_pytest, "run_pytest", lambda *_a, **_k: (0, "1 passed\n"))
    assert check_pytest.main([]) == check_pytest.EXIT_FAIL


def test_a_sharded_leg_with_an_eleven_second_test_fails_the_gate(gate) -> None:
    assert _run_writing(gate, SLOW, 11.0, shard=True) == check_pytest.EXIT_FAIL
    assert gate[2] == ["pytest-slow:%s" % SLOW]


def test_control_a_sharded_leg_with_a_two_second_test_passes(gate) -> None:
    assert _run_writing(gate, SLOW, 2.0, shard=True) == check_pytest.EXIT_OK


def test_an_impact_run_with_an_eleven_second_test_fails_the_gate(gate) -> None:
    assert _run_writing(gate, SLOW, 11.0, impact=True) == check_pytest.EXIT_FAIL
    assert gate[2] == ["pytest-slow:%s" % SLOW]


def test_control_an_impact_run_with_a_two_second_test_passes(gate) -> None:
    assert _run_writing(gate, SLOW, 2.0, impact=True) == check_pytest.EXIT_OK


# A node whose file exists in the fixture (`t/test_one.py`), so the gate can re-time it.
ON_DISK = "t.test_one::test_one"


def _run_retimed(gate, parallel: float, serial: float) -> tuple[int, list[list[str]]]:
    """The full run writes `parallel` for ON_DISK; each serial re-run writes `serial` to the junit it was handed. Returns the exit code and every run's argv."""
    _root, monkeypatch, _emitted, _allow = gate
    calls: list[list[str]] = []

    def writes(_bin, _cwd, args=None, **_k):
        args = list(args or [])
        calls.append(args)
        junit = pathlib.Path(args[args.index("--junitxml") + 1])
        seconds = serial if "slow-confirm" in junit.name else parallel
        junit.write_text(
            '<?xml version="1.0"?><testsuites><testsuite name="pytest">'
            '<testcase classname="t.test_one" name="test_one" time="%s"/></testsuite></testsuites>'
            % seconds,
            encoding="utf-8",
        )
        return 0, "1 passed\n"

    monkeypatch.setattr(check_pytest, "run_pytest", writes)
    return check_pytest.main([]), calls


def test_a_test_slow_only_in_the_parallel_run_passes_on_its_serial_re_times(gate) -> None:
    """THE BEHAVIOUR: 11 s under the parallel run, 2 s in both serial re-runs, median 2 s. Before the re-timing the parallel 11 s alone failed the gate."""
    rc, calls = _run_retimed(gate, 11.0, 2.0)
    assert rc == check_pytest.EXIT_OK
    assert gate[2] == []
    confirms = calls[1:]
    assert len(confirms) == check_pytest.SLOW_CONFIRM_RUNS
    for args in confirms:
        assert args[:2] == ["-n", "0"], "a re-time must be serial, or it measures contention again"
        assert args[-1] == "t/test_one.py::test_one"


def test_control_a_test_slow_in_its_serial_re_times_too_still_fails(gate) -> None:
    rc, calls = _run_retimed(gate, 11.0, 11.5)
    assert rc == check_pytest.EXIT_FAIL
    assert gate[2] == ["pytest-slow:%s" % ON_DISK]
    assert len(calls) == 1 + check_pytest.SLOW_CONFIRM_RUNS


def test_control_a_fast_parallel_run_re_times_nothing(gate) -> None:
    rc, calls = _run_retimed(gate, 2.0, 11.0)
    assert rc == check_pytest.EXIT_OK
    assert len(calls) == 1

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

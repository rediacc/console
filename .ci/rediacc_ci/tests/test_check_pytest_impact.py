"""check_pytest's impact/full switch (PLAN-ciquick-cpu W4.2, B5).

`CI=true` and `--full` run the whole suite, asserted on what reaches pytest and on the collected count the verdict reads; a local run with an impact selection hands pytest exactly the selected files and judges them against their own corpus. Each run writes its scope record, and a red run leaves none behind.

THE PLANTED DEFECT: make `wants_full` return None unconditionally and the two full-suite tests red, because an impact selection reaches pytest under CI=true. Drop the `select_impact` call and the impact test reds, because the whole suite runs.
"""

import json
import pathlib

import pytest

from rediacc_ci import check_pytest, log, pytest_impact

SELECTED = "t/test_one.py"
OTHER = "t/test_two.py"


@pytest.fixture
def gate(tmp_path: pathlib.Path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["t"]\n', encoding="utf-8"
    )
    (tmp_path / "t").mkdir()
    (tmp_path / SELECTED).write_text(
        "def test_one():\n    pass\n\ndef test_one_b():\n    pass\n", encoding="utf-8"
    )
    # The full corpus must clear MIN_TESTS, or a full run fails floor 1 before the switch is judged.
    body = "".join("def test_n%d():\n    pass\n" % i for i in range(check_pytest.MIN_TESTS))
    (tmp_path / OTHER).write_text(body, encoding="utf-8")
    monkeypatch.setattr(check_pytest.paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(check_pytest, "resolve_pytest", lambda _root: "pytest")
    monkeypatch.setattr(check_pytest, "selftest", lambda *_a, **_k: True)
    monkeypatch.setattr(log, "emit_finding", lambda *_a, **_k: None)
    monkeypatch.delenv("CI", raising=False)
    calls: list[list[str]] = []

    def fake_run(_bin, _root, args=None, **_kw):
        calls.append(list(args or []))
        files = [a for a in (args or []) if a.endswith(".py")]
        n = 2 if files == [SELECTED] else 2 + check_pytest.MIN_TESTS
        return 0, "collected %d items\n%d passed in 0.1s\n" % (n, n)

    monkeypatch.setattr(check_pytest, "run_pytest", fake_run)
    impact = pytest_impact.Selection(
        "impact",
        "1 changed file(s)",
        files=[SELECTED],
        total=2,
        smoke=1,
        digest="ab" * 32,
        why={SELECTED: "smoke"},
    )
    asked: list[int] = []

    def fake_select(_root, base=None):
        asked.append(base or 1)
        return impact

    monkeypatch.setattr(check_pytest, "select_impact", fake_select)
    return tmp_path, calls, asked


def scope(root: pathlib.Path) -> dict:
    return json.loads((root / str(check_pytest.SCOPE_RELPATH)).read_text(encoding="utf-8"))


def test_ci_true_runs_the_full_suite(gate, monkeypatch, capsys):
    root, calls, asked = gate
    monkeypatch.setenv("CI", "true")
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert asked == [], "an impact selection was computed under CI=true"
    assert len(calls) == 1, calls
    assert not [a for a in calls[0] if a.endswith(".py")], calls
    rec = scope(root)
    assert rec["pytestScope"] == "full"
    assert rec["reason"] == "CI=true"
    assert rec["collected"] == 2 + check_pytest.MIN_TESTS, (
        "the full run must collect the whole corpus"
    )
    assert "pytest-scope: full" in capsys.readouterr().out


def test_full_flag_runs_the_full_suite(gate):
    root, calls, asked = gate
    assert check_pytest.main(["--full"]) == check_pytest.EXIT_OK
    assert asked == []
    assert not [a for a in calls[0] if a.endswith(".py")]
    assert scope(root)["reason"] == "--full"


def test_a_local_run_judges_only_the_impact_selection(gate, capsys):
    root, calls, asked = gate
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert asked == [1]
    assert [a for a in calls[0] if a.endswith(".py")] == [SELECTED]
    rec = scope(root)
    assert rec["pytestScope"] == "impact"
    assert rec["selectedFiles"] == 1
    assert rec["totalFiles"] == 2
    assert rec["collected"] == 2
    assert rec["mapDigest"] == "ab" * 32
    out = capsys.readouterr().out
    assert "pytest-impact: IMPACT 1 of 2" in out
    assert "pytest-scope: impact files=1 collected=2" in out


def test_a_full_selection_falls_back_to_the_whole_suite(gate, monkeypatch):
    root, calls, _asked = gate
    monkeypatch.setattr(
        check_pytest,
        "select_impact",
        lambda _r, _b=None: pytest_impact.full("pyproject.toml changed", total=2),
    )
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert not [a for a in calls[0] if a.endswith(".py")]
    assert scope(root)["reason"] == "pytest-impact: pyproject.toml changed"


def test_an_impact_run_that_collects_less_than_its_corpus_is_red(gate, monkeypatch):
    root, _calls, _asked = gate
    monkeypatch.setattr(
        check_pytest, "run_pytest", lambda *_a, **_k: (0, "collected 1 item\n1 passed\n")
    )
    assert check_pytest.main([]) == check_pytest.EXIT_FAIL
    assert not (root / str(check_pytest.SCOPE_RELPATH)).exists(), "a red run left a scope record"


def test_a_red_run_removes_a_previous_scope_record(gate, monkeypatch):
    root, _calls, _asked = gate
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert (root / str(check_pytest.SCOPE_RELPATH)).exists()
    monkeypatch.setattr(
        check_pytest, "run_pytest", lambda *_a, **_k: (1, "collected 2 items\n1 failed, 1 passed\n")
    )
    assert check_pytest.main([]) == check_pytest.EXIT_FAIL
    assert not (root / str(check_pytest.SCOPE_RELPATH)).exists()


def test_a_shard_leg_records_full(gate):
    root, _calls, asked = gate
    manifest = root / "m.json"
    manifest.write_text(
        '{"lane": "quality-pytest", "of": 1, "legs": [{"index": 1, "ids": ["pytest:%s", "pytest:%s"]}]}'
        % (SELECTED, OTHER),
        encoding="utf-8",
    )
    assert (
        check_pytest.main(["--shard-manifest", "m.json", "--shard", "1/1"]) == check_pytest.EXIT_OK
    )
    assert asked == []
    assert scope(root)["pytestScope"] == "full"


def test_base_reaches_the_selection_and_is_not_refused(gate):
    _root, _calls, asked = gate
    assert check_pytest.unknown_args(["--base", "origin/main"]) == []
    assert check_pytest.main(["--base", "origin/main"]) == check_pytest.EXIT_OK
    assert asked == ["origin/main"]

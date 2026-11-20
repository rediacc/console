"""check_pytest's impact/full switch (PLAN-ciquick-cpu W4.2, B5).

`CI=true` and `--full` run the whole suite, asserted on what reaches pytest and on the collected count the verdict reads; a local run with an impact selection hands pytest exactly the selected files and judges them against their own corpus. Each run writes its scope record, and a red run leaves none behind.

THE PLANTED DEFECT: make `wants_full` return None unconditionally and the two full-suite tests red, because an impact selection reaches pytest under CI=true. Drop the `select_impact` call and the impact test reds, because the whole suite runs.
"""

import json
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import check_pytest, log, pytest_impact
from rediacc_ci.policy_paths import policy_path

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
    allow = policy_path("pytest-slow-allow.json", tmp_path)
    allow.parent.mkdir(parents=True, exist_ok=True)
    allow.write_text('{"entries": []}', encoding="utf-8")
    monkeypatch.setattr(check_pytest.paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(check_pytest, "resolve_pytest", lambda _root: "pytest")
    monkeypatch.setattr(check_pytest, "selftest", lambda *_a, **_k: True)
    monkeypatch.setattr(log, "emit_finding", lambda *_a, **_k: None)
    monkeypatch.delenv("CI", raising=False)
    calls: list[list[str]] = []

    def fake_run(_bin, _root, args=None, **_kw):
        calls.append(list(args or []))
        if "--junitxml" in (args or []):
            junit = pathlib.Path(args[args.index("--junitxml") + 1])
            junit.parent.mkdir(parents=True, exist_ok=True)
            junit.write_text(
                '<?xml version="1.0"?><testsuites><testsuite name="pytest">'
                '<testcase classname="t.fast" name="test_fast" time="0.1"/></testsuite></testsuites>',
                encoding="utf-8",
            )
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
        smoke_files=[SELECTED],
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


def test_a_bare_trailing_base_is_refused_not_read_as_no_base():
    """Finding a3548fda.1: `--base` with no ref used to select by the push base without a word."""
    assert check_pytest.unknown_args(["--base"]) == ["--base (needs a value)"]
    assert check_pytest.unknown_args(["--shard", "1/2", "--base"]) == ["--base (needs a value)"]
    assert check_pytest.unknown_args(["--base", "origin/main"]) == []


def test_a_bare_trailing_base_fails_the_run(gate, capsys):
    _root, calls, asked = gate
    assert check_pytest.main(["--base"]) == check_pytest.EXIT_FAIL
    assert asked == []
    assert not calls
    assert "needs a value" in capsys.readouterr().err


def test_a_failed_control_removes_a_previous_scope_record(gate, monkeypatch):
    """Finding 755fd65e.2: the selftest fails before any run, and a scope record from the last green must not outlive it."""
    root, _calls, _asked = gate
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert (root / str(check_pytest.SCOPE_RELPATH)).exists()
    monkeypatch.setattr(check_pytest, "selftest", lambda *_a, **_k: False)
    assert check_pytest.main([]) == check_pytest.EXIT_FAIL
    assert not (root / str(check_pytest.SCOPE_RELPATH)).exists()


def test_a_bad_shard_manifest_removes_a_previous_scope_record(gate):
    """Finding 4851c274.1: the manifest failure returns before any run, and the last green's scope must not outlive it."""
    root, _calls, _asked = gate
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert (root / str(check_pytest.SCOPE_RELPATH)).exists()
    assert (
        check_pytest.main(["--shard-manifest", "missing.json", "--shard", "1/1"])
        == check_pytest.EXIT_FAIL
    )
    assert not (root / str(check_pytest.SCOPE_RELPATH)).exists()


def test_selftest_leaves_the_previous_scope_record_alone(gate, monkeypatch):
    """Finding 4851c274.2: `--selftest` records no scope, so deleting the last run's receipt was a side effect."""
    root, _calls, _asked = gate
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    monkeypatch.setattr(check_pytest, "selftest", lambda *_a, **_k: True)
    assert check_pytest.main(["--selftest"]) == check_pytest.EXIT_OK
    assert (root / str(check_pytest.SCOPE_RELPATH)).exists()


@pytest.mark.usefixtures("gate")
def test_the_impact_floor_counts_a_smoke_file_a_change_also_reached(monkeypatch):
    """Finding 755fd65e.1: a change reaching a smoke file replaces its `why` label, but the file is still smoke."""
    seen: list[int] = []
    real = check_pytest.impact_floor

    def spy(n):
        seen.append(n)
        return real(n)

    monkeypatch.setattr(check_pytest, "impact_floor", spy)
    impact = pytest_impact.Selection(
        "impact",
        "1 changed file(s)",
        files=[SELECTED],
        total=2,
        smoke=1,
        digest="ab" * 32,
        why={SELECTED: "imports pkg/mod.py"},
        smoke_files=[SELECTED],
    )
    monkeypatch.setattr(check_pytest, "select_impact", lambda _r, _b=None: impact)
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert seen == [2], "the smoke file's two tests were not counted toward floor 1"


def test_a_local_run_diffs_against_the_last_green_commit(gate, monkeypatch, capsys):
    _root, _calls, asked = gate
    monkeypatch.setattr(check_pytest, "last_green_base", lambda _root: "c0ffee" * 6 + "c0ff")
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert asked == ["c0ffee" * 6 + "c0ff"], (
        "the impact selection did not use the last green commit"
    )
    assert "base = the last green commit c0ffeec0ffee" in capsys.readouterr().out


def test_an_explicit_base_wins_over_the_last_green_commit(gate, monkeypatch):
    _root, _calls, asked = gate
    consulted: list[bool] = []
    monkeypatch.setattr(
        check_pytest, "last_green_base", lambda _root: consulted.append(True) or "abc"
    )
    assert check_pytest.main(["--base", "origin/main"]) == check_pytest.EXIT_OK
    assert asked == ["origin/main"]
    assert consulted == [], "--base must decide alone"


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _green_repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "fixture")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "green")
    green = _git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("2\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "next")
    return repo, green


def _record(repo: pathlib.Path, head: str, python: str) -> None:
    target = repo / str(check_pytest.SCOPE_RELPATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"pytestScope": "full", "head": head, "python": python}), encoding="utf-8"
    )


def test_last_green_base_is_the_recorded_ancestor(tmp_path):
    repo, green = _green_repo(tmp_path)
    assert check_pytest.last_green_base(repo) is None, "no record must leave the push base"
    _record(repo, green, sys.version)
    assert check_pytest.last_green_base(repo) == green
    _record(repo, green, "2.7.0 (an older interpreter)")
    assert check_pytest.last_green_base(repo) is None, "another Python is another suite"
    orphan = _git(repo, "commit-tree", _git(repo, "rev-parse", "HEAD^{tree}"), "-m", "elsewhere")
    _record(repo, orphan, sys.version)
    assert check_pytest.last_green_base(repo) is None, (
        "a head HEAD does not descend from is no base"
    )


def test_a_green_scope_records_the_head_it_was_green_at(tmp_path):
    repo, _green = _green_repo(tmp_path)
    check_pytest.write_scope(repo, {"pytestScope": "impact", "collected": 1})
    head = _git(repo, "rev-parse", "HEAD")
    assert check_pytest.last_green_base(repo) == head

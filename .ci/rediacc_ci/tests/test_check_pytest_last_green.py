"""check_pytest's last-green record (PLAN-ciquick-cpu W11).

The impact base is the commit the suite was last GREEN at. It used to live in scope.json, which every run deletes at its start, so after any red run the base fell back to the push base and the next run printed `pytest-impact: FULL`. The record now lives in `.ci/cache/quality-pytest/last-green.json`, written only by a green whole-suite or impact run over a clean tree and never deleted at run start; scope.json stays the per-run receipt. With no record, the base is the newest green ci:quick receipt this root judged, then the push base.

THE PLANTED DEFECT: delete last-green.json beside scope.json at run start, and `test_a_red_run_keeps_the_record_and_the_next_base_is_its_head` reds, because the post-red run is handed no base. Point `last_green_base` back at scope.json and the same test reds. The scope.json control stays green under both: a run still removes the previous run's scope at its start.
"""

import json
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import check_pytest, log, pytest_impact
from rediacc_ci.policy_paths import policy_path

SELECTED = "t/test_one.py"
OTHER = "t/test_two.py"
CLEAN = check_pytest.CLEAN_DIRTY_DIGEST


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _init(repo: pathlib.Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "fixture")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit(repo: pathlib.Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


class Gate:
    """A committed fixture repo with check_pytest's seams faked: `red` makes the next pytest run fail, `asked` holds each base the impact selection was handed."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.red = False
        self.asked: list[str | None] = []
        self.calls: list[list[str]] = []

    @property
    def record_path(self) -> pathlib.Path:
        return self.root / str(check_pytest.LAST_GREEN_RELPATH)

    @property
    def scope_path(self) -> pathlib.Path:
        return self.root / str(check_pytest.SCOPE_RELPATH)

    def record(self) -> dict:
        return json.loads(self.record_path.read_text(encoding="utf-8"))

    def next_commit(self, msg: str) -> str:
        (self.root / "pkg.txt").write_text(msg + "\n", encoding="utf-8")
        return _commit(self.root, msg)


@pytest.fixture
def gate(tmp_path: pathlib.Path, monkeypatch) -> Gate:
    root = tmp_path / "repo"
    _init(root)
    (root / ".gitignore").write_text(".ci/cache/\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["t"]\n', encoding="utf-8"
    )
    (root / "t").mkdir()
    (root / SELECTED).write_text(
        "def test_one():\n    pass\n\ndef test_one_b():\n    pass\n", encoding="utf-8"
    )
    body = "".join("def test_n%d():\n    pass\n" % i for i in range(check_pytest.MIN_TESTS))
    (root / OTHER).write_text(body, encoding="utf-8")
    allow = policy_path("pytest-slow-allow.json", root)
    allow.parent.mkdir(parents=True, exist_ok=True)
    allow.write_text('{"entries": []}', encoding="utf-8")
    _commit(root, "fixture")
    g = Gate(root)

    monkeypatch.setattr(check_pytest.paths, "repo_root", lambda: root)
    monkeypatch.setattr(check_pytest, "resolve_pytest", lambda _root: "pytest")
    monkeypatch.setattr(check_pytest, "selftest", lambda *_a, **_k: True)
    monkeypatch.setattr(log, "emit_finding", lambda *_a, **_k: None)
    monkeypatch.delenv("CI", raising=False)

    def fake_run(_bin, _root, args=None, **_kw):
        args = list(args or [])
        g.calls.append(args)
        if "--junitxml" in args:
            junit = pathlib.Path(args[args.index("--junitxml") + 1])
            junit.parent.mkdir(parents=True, exist_ok=True)
            junit.write_text(
                '<?xml version="1.0"?><testsuites><testsuite name="pytest">'
                '<testcase classname="t.fast" name="test_fast" time="0.1"/></testsuite></testsuites>',
                encoding="utf-8",
            )
        files = [a for a in args if a.endswith(".py")]
        n = 2 if files == [SELECTED] else 2 + check_pytest.MIN_TESTS
        if g.red:
            return 1, "collected %d items\n1 failed, %d passed in 0.1s\n" % (n, n - 1)
        return 0, "collected %d items\n%d passed in 0.1s\n" % (n, n)

    monkeypatch.setattr(check_pytest, "run_pytest", fake_run)

    def fake_select(_root, base=None):
        g.asked.append(base)
        return pytest_impact.Selection(
            "impact",
            "1 changed file(s)",
            files=[SELECTED],
            total=2,
            smoke=1,
            digest="cd" * 32,
            why={SELECTED: "smoke"},
            smoke_files=[SELECTED],
        )

    monkeypatch.setattr(check_pytest, "select_impact", fake_select)
    return g


def test_a_green_run_writes_the_record(gate: Gate, capsys):
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    rec = gate.record()
    assert rec["head"] == _git(gate.root, "rev-parse", "HEAD")
    assert rec["python"] == sys.version
    assert rec["mapDigest"] == "cd" * 32
    assert "pytest-last-green: " in capsys.readouterr().out


def test_a_red_run_keeps_the_record_and_the_next_base_is_its_head(gate: Gate, capsys):
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    green = gate.record()["head"]
    gate.next_commit("red")
    gate.red = True
    assert check_pytest.main([]) == check_pytest.EXIT_FAIL
    assert gate.record_path.is_file(), "a red run deleted the last-green record"
    assert gate.record()["head"] == green, "a red run rewrote the last-green record"
    gate.next_commit("fix")
    gate.red = False
    capsys.readouterr()
    gate.asked.clear()
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    out = capsys.readouterr().out
    assert gate.asked == [green], "the run after a red was not based on the last green head"
    assert "FULL" not in out, out
    assert "base = the last green commit %s" % green[:12] in out


def test_control_scope_json_is_still_removed_at_run_start(gate: Gate):
    assert check_pytest.main([]) == check_pytest.EXIT_OK
    assert gate.scope_path.is_file()
    gate.red = True
    assert check_pytest.main([]) == check_pytest.EXIT_FAIL
    assert not gate.scope_path.exists(), "a red run left the previous green's scope.json"


def test_a_shard_leg_green_writes_no_record(gate: Gate):
    manifest = gate.root / "shards.json"
    manifest.write_text(
        json.dumps(
            {"lane": "quality-pytest", "of": 1, "legs": [{"index": 1, "ids": ["pytest:" + OTHER]}]}
        ),
        encoding="utf-8",
    )
    rc = check_pytest.main(["--shard-manifest", "shards.json", "--shard", "1/1"])
    assert rc == check_pytest.EXIT_OK
    assert gate.scope_path.is_file(), "the shard leg was not green, so this proves nothing"
    assert not gate.record_path.exists(), "one shard leg proves its leg, not the suite at head"


def test_write_scope_shard_flag_leaves_the_record_alone(gate: Gate):
    check_pytest.write_scope(gate.root, {"pytestScope": "full", "collected": 1}, whole=False)
    assert gate.scope_path.is_file()
    assert not gate.record_path.exists(), "a shard-leg scope wrote a last-green record"


def test_a_green_run_over_uncommitted_edits_keeps_the_previous_record(gate: Gate):
    check_pytest.write_scope(gate.root, {"pytestScope": "impact", "collected": 1})
    green = gate.record()["head"]
    gate.next_commit("next")
    (gate.root / "pkg.txt").write_text("edited, not committed\n", encoding="utf-8")
    check_pytest.write_scope(gate.root, {"pytestScope": "impact", "collected": 1})
    assert gate.record()["head"] == green, "a dirty green named a commit it did not prove"
    assert check_pytest.last_green_base(gate.root) == green


def _write_record(root: pathlib.Path, head: str, python: str) -> None:
    target = root / str(check_pytest.LAST_GREEN_RELPATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"head": head, "python": python}), encoding="utf-8")


def _receipt(
    receipts: pathlib.Path,
    name: str,
    *,
    head: str,
    judged: pathlib.Path,
    finished: str,
    verdict: str = "ok",
    dirty: str = CLEAN,
    stable: bool = True,
) -> None:
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / ("%s.json" % name)).write_text(
        json.dumps(
            {
                "schema": 2,
                "head": head,
                "judgedRoot": str(judged),
                "finishedAt": finished,
                "dirtyDigest": dirty,
                "stable": stable,
                "gates": {"check:ci-pytest": {"verdict": verdict}},
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def history(tmp_path: pathlib.Path):
    repo = tmp_path / "repo"
    _init(repo)
    (repo / "a.txt").write_text("1\n", encoding="utf-8")
    first = _commit(repo, "first")
    (repo / "a.txt").write_text("2\n", encoding="utf-8")
    second = _commit(repo, "second")
    (repo / "a.txt").write_text("3\n", encoding="utf-8")
    _commit(repo, "third")
    return repo, first, second


def test_the_record_wins_and_its_guards_hold(history):
    repo, first, second = history
    receipts = repo / ".ci" / "cache" / "receipts"
    _receipt(receipts, "r2", head=second, judged=repo, finished="2026-11-22T02:00:00Z")
    _write_record(repo, first, sys.version)
    assert check_pytest.last_green_base(repo) == first, "the record must win over a receipt"
    _write_record(repo, first, "2.7.0 (an older interpreter)")
    assert check_pytest.last_green_base(repo) is None, (
        "another Python is another suite, and a receipt cannot say which Python it ran"
    )
    orphan = _git(repo, "commit-tree", _git(repo, "rev-parse", "HEAD^{tree}"), "-m", "elsewhere")
    _write_record(repo, orphan, sys.version)
    assert check_pytest.last_green_base(repo) is None, (
        "a head HEAD does not descend from is no base"
    )


def test_with_no_record_the_newest_green_receipt_of_this_root_is_the_base(history, tmp_path):
    repo, first, second = history
    receipts = repo / ".ci" / "cache" / "receipts"
    assert check_pytest.last_green_base(repo) is None, (
        "no record and no receipt leave the push base"
    )
    _receipt(receipts, "old", head=first, judged=repo, finished="2026-11-22T01:00:00Z")
    assert check_pytest.last_green_base(repo) == first
    _receipt(receipts, "green", head=second, judged=repo, finished="2026-11-22T02:00:00Z")
    assert check_pytest.last_green_base(repo) == second, "the newest green receipt is the base"
    _receipt(
        receipts, "red", head=second, judged=repo, finished="2026-11-22T03:00:00Z", verdict="fail"
    )
    _receipt(
        receipts, "dirty", head=second, judged=repo, finished="2026-11-22T04:00:00Z", dirty="ab" * 8
    )
    _receipt(
        receipts, "moved", head=second, judged=repo, finished="2026-11-22T05:00:00Z", stable=False
    )
    _receipt(
        receipts,
        "other",
        head=_git(repo, "rev-parse", "HEAD"),
        judged=tmp_path / "another-root",
        finished="2026-11-22T06:00:00Z",
    )
    (receipts / "garbage.json").write_text("not json", encoding="utf-8")
    assert check_pytest.last_green_base(repo) == second, (
        "a red, dirty, unstable or foreign-root receipt was taken as the green base"
    )


def test_a_kept_clone_reads_the_receipts_of_the_checkout_its_toolchain_links_to(tmp_path):
    live = tmp_path / "live"
    (live / ".ci" / "cache" / "toolchain").mkdir(parents=True)
    clone = tmp_path / "clone"
    _init(clone)
    (clone / "a.txt").write_text("1\n", encoding="utf-8")
    green = _commit(clone, "green")
    (clone / "a.txt").write_text("2\n", encoding="utf-8")
    _commit(clone, "next")
    (clone / ".ci" / "cache").mkdir(parents=True)
    os.symlink(live / ".ci" / "cache" / "toolchain", clone / ".ci" / "cache" / "toolchain")
    _receipt(
        live / ".ci" / "cache" / "receipts",
        "tree",
        head=green,
        judged=clone,
        finished="2026-11-22T01:00:00Z",
    )
    assert check_pytest.last_green_base(clone) == green, (
        "the clone did not find the receipts its live checkout keeps"
    )

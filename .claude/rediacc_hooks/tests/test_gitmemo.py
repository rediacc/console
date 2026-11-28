"""`_gitmemo.chain_memo`: one answer per read-only git question for the life of one guard chain run (PR-TASK 79b7e92e).

Both directions are driven. A repeated `rev-parse` in one directory reaches git once; a question that is not read-only, a different directory, a different `GIT_*` environment, stdin data or `check=True` each reach git every time. The planted `DEFECT` (key on argv alone) must make two repositories share one `--show-toplevel`, and the real pre-bash chain must start fewer processes with the memo than without it on an `echo hi` payload, or the memo is not what `run_chain` runs under.
"""

import importlib.util
import json
import os
import pathlib
import subprocess

import pytest

from rediacc_hooks import _gitmemo, dispatch

GITMEMO = pathlib.Path(_gitmemo.__file__)


def _git_init(path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    return path


def _toplevel(cwd):
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


@pytest.fixture
def counting(monkeypatch):
    """Replace the REAL subprocess.run under the memo with a counter that still runs the command."""
    real = subprocess.run
    calls = []

    def run(*args, **kwargs):
        calls.append(list(args[0] if args else kwargs["args"]))
        return real(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_repeated_rev_parse_reaches_git_once(counting, tmp_path):
    repo = _git_init(tmp_path / "r")
    counting.clear()
    with _gitmemo.chain_memo() as memo:
        outs = {_toplevel(repo) for _ in range(5)}
    assert len(counting) == 1, counting
    assert (memo.hits, memo.misses) == (4, 1)
    assert outs == {str(repo.resolve())}


def test_two_repositories_never_share_an_answer(tmp_path):
    a = _git_init(tmp_path / "a")
    b = _git_init(tmp_path / "b")
    with _gitmemo.chain_memo():
        got_a, got_b = _toplevel(a), _toplevel(b)
    assert got_a == str(a.resolve())
    assert got_b == str(b.resolve())


def test_planted_defect_shares_one_answer_across_repositories(tmp_path):
    """Red-once control: keyed on argv alone, the second repository is told the first one's toplevel."""
    old, new = _gitmemo.DEFECT
    source = GITMEMO.read_text(encoding="utf-8")
    assert source.count(old) == 1, "the DEFECT anchor moved; this control would plant nothing"
    planted = tmp_path / "gitmemo_planted.py"
    planted.write_text(source.replace(old, new), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("gitmemo_planted", planted)
    assert spec is not None, planted
    assert spec.loader is not None, planted
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    a = _git_init(tmp_path / "a")
    b = _git_init(tmp_path / "b")
    with module.chain_memo():
        got_a, got_b = _toplevel(a), _toplevel(b)
    assert got_b == got_a == str(a.resolve())


def test_git_env_is_part_of_the_key(counting, tmp_path):
    repo = _git_init(tmp_path / "r")
    env = dict(os.environ, GIT_DIR=str(repo / ".git"))
    counting.clear()
    with _gitmemo.chain_memo():
        subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=repo, capture_output=True, check=False
        )
        subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=repo, capture_output=True, env=env, check=False
        )
    assert len(counting) == 2


@pytest.mark.parametrize(
    ("argv", "kwargs"),
    [
        (["git", "status", "--porcelain"], {"capture_output": True}),
        (["git", "symbolic-ref", "HEAD", "refs/heads/elsewhere"], {"capture_output": True}),
        (["git", "symbolic-ref", "-d", "HEAD"], {"capture_output": True}),
        (["git", "symbolic-ref", "--delete", "-q", "HEAD"], {"capture_output": True}),
        (["git", "symbolic-ref", "-m", "why", "HEAD"], {"capture_output": True}),
        (["git", "rev-parse", "--show-toplevel"], {"capture_output": True, "check": True}),
        (["git", "rev-parse", "--stdin"], {"capture_output": True, "input": b"HEAD\n"}),
        (["git", "rev-parse", "--show-toplevel"], {}),
        (["echo", "rev-parse"], {"capture_output": True}),
    ],
)
def test_anything_else_passes_through_every_time(counting, tmp_path, argv, kwargs):
    repo = _git_init(tmp_path / "r")
    counting.clear()
    with _gitmemo.chain_memo():
        for _ in range(2):
            rest = dict(kwargs)
            subprocess.run(argv, cwd=repo, check=rest.pop("check", False), **rest)
    assert len(counting) == 2, (argv, kwargs, counting)


def test_reading_symbolic_ref_and_dash_c_forms_are_memoized(counting, tmp_path):
    repo = _git_init(tmp_path / "r")
    counting.clear()
    with _gitmemo.chain_memo():
        for _ in range(3):
            subprocess.run(
                ["git", "-C", str(repo), "symbolic-ref", "--short", "-q", "HEAD"],
                capture_output=True,
                check=False,
            )
    assert len(counting) == 1


def test_a_deleted_working_directory_reaches_git_unmemoized(counting, tmp_path, monkeypatch):
    """Review ed6cdfea.2: with the process's own directory gone and no `cwd`, `os.getcwd()` raised out of the key before git ran. The question now passes through, git's own failure comes back as a result, and nothing is stored."""
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    counting.clear()
    with _gitmemo.chain_memo() as memo:
        for _ in range(2):
            got = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, check=False
            )
            assert got.returncode != 0
    assert len(counting) == 2
    assert memo.table == {}
    assert memo.hits == 0


def test_control_a_live_working_directory_is_still_memoized_with_no_cwd(
    counting, tmp_path, monkeypatch
):
    repo = _git_init(tmp_path / "r")
    monkeypatch.chdir(repo)
    counting.clear()
    with _gitmemo.chain_memo():
        for _ in range(2):
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, check=False
            )
    assert len(counting) == 1


def test_an_exception_is_never_stored(monkeypatch):
    calls = []

    def boom(*args, **_kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(subprocess, "run", boom)
    with _gitmemo.chain_memo():
        for _ in range(2):
            with pytest.raises(subprocess.TimeoutExpired):
                subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, timeout=30, check=False
                )
    assert len(calls) == 2


def test_the_memo_ends_with_the_with():
    real = subprocess.run
    with _gitmemo.chain_memo():
        assert subprocess.run is not real
        with _gitmemo.chain_memo() as inner:
            assert subprocess.run == inner.run
    assert subprocess.run is real


class _NullMemo:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def _spawns(monkeypatch, repo, memo):
    """Processes one real pre-bash chain run starts over `echo hi` in a real repository."""
    if not memo:
        monkeypatch.setattr(dispatch._gitmemo, "chain_memo", _NullMemo)
    started = []
    real_init = subprocess.Popen.__init__

    def init(self, *args, **kwargs):
        started.append(args[0] if args else kwargs.get("args"))
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", init)
    payload = json.dumps(
        {
            "session_id": "x",
            "cwd": str(repo),
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
        }
    )
    rc, _out, err = dispatch.run_chain("pre-bash", payload, cwd=str(repo))
    monkeypatch.undo()
    return rc, err, len(started)


def test_the_real_chain_runs_under_the_memo(monkeypatch, tmp_path):
    repo = _git_init(tmp_path / "r")
    rc_on, err_on, with_memo = _spawns(monkeypatch, repo, memo=True)
    rc_off, err_off, without = _spawns(monkeypatch, repo, memo=False)
    assert (rc_on, rc_off) == (0, 0), (err_on, err_off)
    assert without > 0, "the control chain started no process; this comparison would prove nothing"
    assert with_memo * 3 <= without, "memo %d spawns against %d without" % (with_memo, without)

"""The session tripwire in the repo-root conftest: a test that changes a tracked path fails the run, naming the path.

WHY IT EXISTS (agent/plans/PLAN-prepush-full-cpu.md PF15, 2026-10-05). Until then three gate tests planted into the real tree, and the suite bought that off with the `real-tree` xdist group (one worker) and an exclusive `tree:repo` claim on check:ci-pytest (six other gates held out of the pool for the whole pytest wall). The plants moved into copies and both serialisations were dropped. The tripwire is what keeps them dropped: it records `git status` of the testpaths roots and the directories the gate tests scan before collection, compares after the session, and fails the run on any difference, so a test that goes back to writing the tree is caught in the run that does it rather than by the next concurrent reader's flake.

EVERY CASE DRIVES A REAL NESTED PYTEST against a scratch git repository carrying a copy of the real conftest, so what is proved is the hook as pytest runs it (session start before collection, finish after the last report, the controller rather than the workers under xdist), not a helper called by hand.

THE PLANTED DEFECTS these were written against, red before the hook existed and red again with it disabled: a test appending to a tracked file passes the nested session (rc 0), so `test_a_test_that_writes_a_tracked_file_fails_the_session` and its xdist twin red.

ATTRIBUTION (2026-10-07). In a SHARED tree (a tracked path already modified at start) a change no test of the run wrote in-process is a peer's edit or commit, reported as a warning with rc 0, while the run's own write still fails naming the test. In a STRICT tree (clean, as the push clone and CI are) every change still fails. The peer is driven for real: the
outer test edits the scratch tree while the nested session is parked inside its one test, so the nested pytest never touches that file.
"""

import pathlib
import shutil
import subprocess
import sys
import time

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
CONFTEST = ROOT / "conftest.py"

PYPROJECT = """[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
"""

WRITER = """import pathlib

def test_appends_to_a_tracked_file():
    path = pathlib.Path(__file__).with_name("data.txt")
    path.write_text(path.read_text() + "planted\\n")
"""

UNTRACKED = """import pathlib

def test_leaves_a_new_file():
    pathlib.Path(__file__).with_name("stray.txt").write_text("x\\n")
"""

READER = """import pathlib

def test_only_reads():
    assert pathlib.Path(__file__).with_name("data.txt").read_text()
"""


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        },
    )


@pytest.fixture
def repo(tmp_path):
    """A scratch repository whose pytest rootdir carries the REAL conftest, with one tracked data file under its testpath."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    shutil.copy2(CONFTEST, root / "conftest.py")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "tests" / "data.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    return root


def _env(root: pathlib.Path, **extra: str) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(root),
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        **extra,
    }


def _argv(*extra: str) -> list[str]:
    return [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:randomly", *extra]


def _pytest(root: pathlib.Path, test_body: str, *extra: str) -> tuple[int, str]:
    (root / "tests" / "test_planted.py").write_text(test_body, encoding="utf-8")
    proc = subprocess.run(
        _argv(*extra),
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
        env=_env(root),
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_a_test_that_writes_a_tracked_file_fails_the_session(repo) -> None:
    """THE CONTROL. The planted test passes on its own terms; the session must still fail and name the path."""
    rc, out = _pytest(repo, WRITER)
    assert rc != 0, out
    assert "1 passed" in out, out
    assert "TREE TRIPWIRE" in out, out
    assert "tests/data.txt" in out, out


def test_the_tripwire_fires_from_the_controller_under_xdist(repo) -> None:
    """Under `-n 2` the workers run the test and the CONTROLLER compares, so the run fails once, naming the path."""
    rc, out = _pytest(repo, WRITER, "-n", "2")
    assert rc != 0, out
    assert "tests/data.txt" in out, out


def test_an_untracked_file_left_behind_fails_the_session(repo) -> None:
    """A new file under a scanned root is a difference too."""
    rc, out = _pytest(repo, UNTRACKED)
    assert rc != 0, out
    assert "tests/stray.txt" in out, out


def test_a_further_edit_to_an_already_dirty_file_is_caught(repo) -> None:
    """The comparison is on CONTENT, not on git's status letter: a file already modified before the run reads ` M` before and after, and only its bytes tell the two apart."""
    (repo / "tests" / "data.txt").write_text("dirty before the run\n", encoding="utf-8")
    rc, out = _pytest(repo, WRITER)
    assert rc != 0, out
    assert "tests/data.txt" in out, out


def test_a_clean_run_passes(repo) -> None:
    """CONTROL in the other direction: a test that only reads leaves the session green, and a file that was dirty BEFORE the run is not blamed on the run."""
    (repo / "tests" / "data.txt").write_text("dirty before the run\n", encoding="utf-8")
    rc, out = _pytest(repo, READER)
    assert rc == 0, out
    assert "TREE TRIPWIRE" not in out, out


PARKED = """import os, pathlib, time

def test_parked_while_a_peer_edits():
    pathlib.Path(os.environ["PEER_READY"]).write_text("x")
    done = pathlib.Path(os.environ["PEER_DONE"])
    deadline = time.monotonic() + 120
    while not done.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert done.exists(), "the peer never edited"
"""

CHILD = """import subprocess

def test_a_child_process_appends():
    subprocess.run(["sh", "-c", "echo child >> tests/data.txt"], check=True)
"""


def _share(repo: pathlib.Path) -> None:
    """Make the scratch tree SHARED: a tracked file outside every watched root, modified before the run, as a peer's work in progress is."""
    (repo / "peer" / "notes.txt").parent.mkdir()
    (repo / "peer" / "notes.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "peer")
    (repo / "peer" / "notes.txt").write_text("a peer's uncommitted edit\n", encoding="utf-8")


def _with_a_peer(repo: pathlib.Path, tmp_path: pathlib.Path, edit, *extra: str) -> tuple[int, str]:
    """Run PARKED in a nested session and call `edit(repo)` from THIS process while the nested test is parked: a real concurrent writer the nested run never was."""
    (repo / "tests" / "test_planted.py").write_text(PARKED, encoding="utf-8")
    ready, done = tmp_path / "peer-ready", tmp_path / "peer-done"
    proc = subprocess.Popen(
        _argv(*extra),
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=_env(repo, PEER_READY=str(ready), PEER_DONE=str(done)),
    )
    try:
        deadline = time.monotonic() + 240
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "the nested session never reached its test"
        edit(repo)
        done.write_text("x", encoding="utf-8")
        out, _ = proc.communicate(timeout=300)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
    return proc.returncode, out


def _peer_edits_a_tracked_file(repo: pathlib.Path) -> None:
    (repo / "tests" / "data.txt").write_text("a peer's edit\n", encoding="utf-8")


def _peer_commits(repo: pathlib.Path) -> None:
    _peer_edits_a_tracked_file(repo)
    _git(repo, "commit", "-q", "-am", "a peer's commit")


def _peer_drops_a_stray(repo: pathlib.Path) -> None:
    (repo / "peer-stray.txt").write_text("x\n", encoding="utf-8")


def test_the_run_own_write_fails_a_shared_tree_naming_the_test(repo) -> None:
    """THE CONTROL for attribution: in a shared tree the in-process write still fails, now naming the test that made it."""
    _share(repo)
    rc, out = _pytest(repo, WRITER)
    assert rc != 0, out
    assert "1 passed" in out, out
    assert "TREE TRIPWIRE" in out, out
    assert "shared:" in out, out
    assert "written by tests/test_planted.py::test_appends_to_a_tracked_file" in out, out


def test_the_run_own_write_fails_a_shared_tree_under_xdist(repo) -> None:
    """The worker's record reaches the controller (workeroutput); without it the write would read as a peer's and pass."""
    _share(repo)
    rc, out = _pytest(repo, WRITER, "-n", "2")
    assert rc != 0, out
    assert "written by tests/test_planted.py::test_appends_to_a_tracked_file" in out, out


def test_the_run_own_stray_fails_a_shared_tree(repo) -> None:
    """The untracked-file snapshot judges the same way: a stray the test wrote fails the shared tree too."""
    _share(repo)
    rc, out = _pytest(repo, UNTRACKED)
    assert rc != 0, out
    assert "tests/stray.txt" in out, out


@pytest.mark.parametrize("extra", [(), ("-n", "2")], ids=["serial", "xdist"])
@pytest.mark.parametrize(
    ("edit", "path"),
    [
        (_peer_edits_a_tracked_file, "tests/data.txt"),
        (_peer_commits, "tests/data.txt"),
        (_peer_drops_a_stray, "peer-stray.txt"),
    ],
    ids=["edit", "commit", "stray"],
)
def test_a_peer_writing_a_shared_tree_mid_run_is_a_warning_not_a_failure(
    repo, tmp_path, edit, path, extra
) -> None:
    """THE FIX: another session's edit, commit or new file during the run no longer fails it; the path is still printed. `tests/data.txt` is the peer's work in progress before the run, so its commit moves it from ` M` to clean, a real difference."""
    _share(repo)
    (repo / "tests" / "data.txt").write_text("a peer's work in progress\n", encoding="utf-8")
    rc, out = _with_a_peer(repo, tmp_path, edit, *extra)
    assert rc == 0, out
    assert "1 passed" in out, out
    assert "TREE TRIPWIRE:" not in out, out
    assert path in out, out


@pytest.mark.parametrize(
    "edit", [_peer_edits_a_tracked_file, _peer_drops_a_stray], ids=["edit", "stray"]
)
def test_a_peer_writing_a_strict_tree_mid_run_still_fails(repo, tmp_path, edit) -> None:
    """THE PROTECTION KEPT: in a clean tree (the push clone, CI) nothing else may write, so any change fails exactly as before."""
    rc, out = _with_a_peer(repo, tmp_path, edit)
    assert rc != 0, out
    assert "strict:" in out, out


def test_a_child_process_write_fails_a_strict_tree(repo) -> None:
    """A write by a CHILD process is invisible to the audit hook; the strict tree is what still catches it."""
    rc, out = _pytest(repo, CHILD)
    assert rc != 0, out
    assert "tests/data.txt" in out, out
    assert "no in-process write" in out, out


def test_the_mode_is_printed_on_a_clean_run(repo) -> None:
    """Print the shape: a reader can see which mode judged the run and how many in-tree writes were recorded."""
    rc, out = _pytest(repo, READER)
    assert rc == 0, out
    assert "tree tripwire: 0 of" in out, out
    assert "strict:" in out, out
    assert "in-tree write(s) recorded" in out, out


def _conftest():
    import importlib.util  # noqa: PLC0415 -- only the pure-helper cases load the conftest as a module

    spec = importlib.util.spec_from_file_location("root_conftest_under_test", CONFTEST)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_write_to_an_ancestor_name_attributes_nothing_below_it() -> None:
    """THE REGRESSION from the first full hooks run: `mkdir(exist_ok=True)` on `.ci` raised a write event for an existing directory, and an ancestor match made that test the author of every peer edit under `.ci`. Only a subtree event (`<dir>/`) attributes below itself."""
    c = _conftest()
    writes = {".ci": "t::mkdir"}
    assert c.attributed(".ci/rediacc_ci/tests/test_x.py", writes) is None
    assert c.judge([".ci/rediacc_ci/tests/test_x.py"], writes, strict=False) == (
        [],
        [".ci/rediacc_ci/tests/test_x.py"],
    )


def test_a_renamed_or_removed_subtree_attributes_every_path_below_it() -> None:
    c = _conftest()
    writes: dict[str, str] = {}
    c.record_write("/r", "/r/scripts/gates", "t::rename", writes, subtree=True)
    c.record_write("/r", "/r/scripts/one.ts", "t::open", writes)
    c.record_write("/r", "/r/scripts/__pycache__/x.pyc", "t::pyc", writes)
    c.record_write("/r", "/elsewhere/file", "t::tmp", writes)
    assert writes == {
        "scripts/gates": "t::rename",
        "scripts/gates/": "t::rename",
        "scripts/one.ts": "t::open",
    }
    assert c.attributed("scripts/gates/check-a.ts", writes) == "t::rename"
    assert c.attributed("scripts/one.ts", writes) == "t::open"
    assert c.attributed("scripts/two.ts", writes) is None


def test_judge_fails_everything_in_a_strict_tree_and_only_own_writes_in_a_shared_one() -> None:
    c = _conftest()
    writes = {"a": "t::w"}
    assert c.judge(["a", "b"], writes, strict=True) == ([("a", "t::w"), ("b", None)], [])
    assert c.judge(["a", "b"], writes, strict=False) == ([("a", "t::w")], ["b"])

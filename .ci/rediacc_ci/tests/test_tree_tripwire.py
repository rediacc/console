"""The session tripwire in the repo-root conftest: a test that changes a tracked path fails the run, naming the path.

WHY IT EXISTS (agent/plans/PLAN-prepush-full-cpu.md PF15, 2026-10-05). Until then three gate tests planted into the real tree, and the suite bought that off with the `real-tree` xdist group (one worker) and an exclusive `tree:repo` claim on check:ci-pytest (six other gates held out of the pool for the whole pytest wall). The plants moved into copies and both serialisations were dropped. The tripwire is what keeps them dropped: it records `git status` of the testpaths roots and the directories the gate tests scan before collection, compares after the session, and fails the run on any difference, so a test that goes back to writing the tree is caught in the run that does it rather than by the next concurrent reader's flake.

EVERY CASE DRIVES A REAL NESTED PYTEST against a scratch git repository carrying a copy of the real conftest, so what is proved is the hook as pytest runs it (session start before collection, finish after the last report, the controller rather than the workers under xdist), not a helper called by hand.

THE PLANTED DEFECTS these were written against, red before the hook existed and red again with it disabled: a test appending to a tracked file passes the nested session (rc 0), so `test_a_test_that_writes_a_tracked_file_fails_the_session` and its xdist twin red.
"""

import pathlib
import shutil
import subprocess
import sys

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


def _pytest(root: pathlib.Path, test_body: str, *extra: str) -> tuple[int, str]:
    (root / "tests" / "test_planted.py").write_text(test_body, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:randomly", *extra],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(root),
            "PYTHONPATH": str(ROOT / ".ci"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
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

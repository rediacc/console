"""`rediacc_ci.tests.gates.run_bare`: the pytest-free runner for a ported gate-test module.

Every case drives the runner as a child process against a throwaway module, because the runner's contract is an exit status plus text on two streams, and because the "no pytest" claim is only worth anything in a process that has never imported it.
"""

import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths

CI_DIR = str(paths.repo_root() / ".ci")

# Blocks pytest the way a bare runner lacks it: `sys.modules[name] = None` makes `import pytest` raise ImportError.
BLOCK_PYTEST = "import sys; sys.modules['pytest'] = None; sys.modules['_pytest'] = None; "


def run_bare(tmp_path: pathlib.Path, source: str, *, block_pytest: bool = False):
    (tmp_path / "bare_subject.py").write_text(source, encoding="utf-8")
    program = (
        (BLOCK_PYTEST if block_pytest else "")
        + "import sys; from rediacc_ci.tests.gates import run_bare; sys.exit(run_bare.main(['bare_subject']))"
    )
    return subprocess.run(
        [sys.executable, "-c", program],
        cwd=str(tmp_path),
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "%s:%s" % (CI_DIR, tmp_path)},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


PASSING = """
def test_one(gate):
    gate.log_pass("one")

def test_two(gate):
    gate.ok("two")
    gate.tally_finish("two")
"""


def test_a_passing_module_exits_zero_and_names_each_test(tmp_path) -> None:
    proc = run_bare(tmp_path, PASSING)
    assert proc.returncode == 0, proc.stderr
    assert "ok   test_one" in proc.stdout
    assert "ok   test_two" in proc.stdout
    assert "2 test(s), 0 failed" in proc.stdout


def test_it_imports_and_runs_with_pytest_blocked(tmp_path) -> None:
    """The reason the module exists: ubuntu-slim has no pytest."""
    proc = run_bare(tmp_path, PASSING, block_pytest=True)
    assert proc.returncode == 0, proc.stderr
    # The control: the block really makes pytest unimportable in this interpreter.
    check = subprocess.run(
        [sys.executable, "-c", BLOCK_PYTEST + "import pytest"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode != 0
    assert "ImportError" in check.stderr or "ModuleNotFoundError" in check.stderr


def test_a_failed_assertion_exits_one_and_the_rest_still_run(tmp_path) -> None:
    proc = run_bare(
        tmp_path,
        "def test_bad(gate):\n    gate.assert_eq(1, 2, 'one is not two')\n\n"
        "def test_good(gate):\n    gate.log_pass('fine')\n",
    )
    assert proc.returncode == 1
    assert "FAIL test_bad" in proc.stderr
    assert "ok   test_good" in proc.stdout


def test_a_recorded_no_without_tally_finish_is_a_failure(tmp_path) -> None:
    proc = run_bare(tmp_path, "def test_quiet(gate):\n    gate.ok('a')\n    gate.no('b')\n")
    assert proc.returncode == 1
    assert "gate.tally_finish()" in proc.stderr


def test_a_test_that_proves_nothing_is_a_failure(tmp_path) -> None:
    proc = run_bare(tmp_path, "def test_empty(gate):\n    pass\n")
    assert proc.returncode == 1
    assert "no assertions" in proc.stderr


def test_a_module_with_no_tests_is_a_failure(tmp_path) -> None:
    proc = run_bare(tmp_path, "def helper(gate):\n    pass\n")
    assert proc.returncode == 1
    assert "defines no test_* function" in proc.stderr


@pytest.mark.parametrize(
    "signature",
    ["tmp_path", "", "gate, monkeypatch", "gate, tmp_path, monkeypatch", "tmp_path, gate"],
)
def test_a_test_taking_anything_but_gate_is_refused(tmp_path, signature) -> None:
    proc = run_bare(tmp_path, "def test_odd(%s):\n    pass\n" % signature)
    assert proc.returncode == 1
    assert "refused" in proc.stderr
    assert "only `gate` and `tmp_path`" in proc.stderr


TMP_PATH_MODULE = """
import os, pathlib

def test_scratch(gate, tmp_path):
    assert isinstance(tmp_path, pathlib.Path) and tmp_path.is_dir()
    (tmp_path / "f").write_text("x")
    with open(os.environ["SEEN_FILE"], "w") as out:
        out.write(str(tmp_path))
    gate.log_pass("scratch")
"""


@pytest.mark.parametrize("block", [False, True])
def test_tmp_path_is_supplied_as_a_directory_and_removed_after(tmp_path, block) -> None:
    seen = tmp_path / "seen.txt"
    (tmp_path / "bare_subject.py").write_text(TMP_PATH_MODULE, encoding="utf-8")
    program = (
        (BLOCK_PYTEST if block else "")
        + "import sys; from rediacc_ci.tests.gates import run_bare; sys.exit(run_bare.main(['bare_subject']))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        cwd=str(tmp_path),
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": "%s:%s" % (CI_DIR, tmp_path),
            "SEEN_FILE": str(seen),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    scratch = pathlib.Path(seen.read_text(encoding="utf-8"))
    assert scratch != tmp_path
    assert not scratch.exists()


def test_imported_test_functions_are_not_collected(tmp_path) -> None:
    """A `from helper import test_x` is the other module's test; running it here would double-count it."""
    (tmp_path / "bare_other.py").write_text(
        "def test_foreign(gate):\n    raise AssertionError('must not run')\n", encoding="utf-8"
    )
    proc = run_bare(
        tmp_path,
        "from bare_other import test_foreign\n\ndef test_own(gate):\n    gate.log_pass('own')\n",
    )
    assert proc.returncode == 0, proc.stderr
    assert "test_foreign" not in proc.stdout


def test_a_bad_command_line_exits_two(tmp_path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.tests.gates.run_bare"],
        cwd=str(tmp_path),
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": CI_DIR},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 2

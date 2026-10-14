"""The repo-root conftest refuses a named test path that does not exist, under xdist too.

Serial pytest answers a misspelled path with rc 4 and "file or directory not found"; under `-n` the run used to end "no tests ran" at rc 5 with no word of which path (worklist #f0bad09d). These drive a REAL nested `pytest -n 2` through the root conftest: the plant names a path that is not there, and the control is the identical command naming one that is.
"""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).relative_to(ROOT)


def _nested_pytest(cache: pathlib.Path, target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "cache_dir=%s" % cache,
            "-n",
            "2",
            "--collect-only",
            "-q",
            target,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_a_missing_path_under_xdist_is_refused_with_the_path_named(tmp_path):
    missing = str(HERE.with_name("test_no_such_file_named_here.py"))
    planted = _nested_pytest(tmp_path, missing)
    assert planted.returncode == 4, (
        planted.returncode,
        planted.stdout[-400:],
        planted.stderr[-400:],
    )
    assert "file or directory not found: %s" % missing in planted.stderr, planted.stderr[-600:]


def test_a_missing_node_id_names_its_file(tmp_path):
    missing = "%s::test_x" % HERE.with_name("test_no_such_file_named_here.py")
    planted = _nested_pytest(tmp_path, missing)
    assert planted.returncode == 4, (planted.returncode, planted.stderr[-400:])
    assert missing in planted.stderr, planted.stderr[-600:]


def test_an_existing_path_still_collects(tmp_path):
    """THE CONTROL: the same command naming a file that exists collects it."""
    control = _nested_pytest(tmp_path, "%s::test_an_existing_path_still_collects" % HERE)
    assert control.returncode == 0, (
        control.returncode,
        control.stdout[-400:],
        control.stderr[-400:],
    )
    assert "test_an_existing_path_still_collects" in control.stdout

"""wl_core's profiler import guard never changes the exit code of the hook it measures.

A stub wl_resprofile whose install() raises stands in for a broken profiler. The red case closes stderr before wl_core imports: the guard's own line cannot be written, and the import must still finish. The control keeps stderr open and reads the one named line.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"

SNIPPET = r"""
import sys, types
sys.path.insert(0, sys.argv[1])
stub = types.ModuleType("wl_resprofile")
def install():
    raise RuntimeError("boom")
stub.install = install
sys.modules["wl_resprofile"] = stub
if sys.argv[2] == "closed":
    sys.stderr.close()
import wl_core
sys.stdout.write("imported")
"""


def run(mode):
    return subprocess.run(
        [sys.executable, "-c", SNIPPET, str(STOP_DIR), mode],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_a_failed_profiler_names_itself_once_on_stderr_and_the_import_finishes():
    got = run("open")
    assert got.returncode == 0, got.stderr
    assert got.stdout == "imported"
    assert got.stderr.count("resprofile profiler not armed (RuntimeError: boom)") == 1


def test_a_closed_stderr_cannot_change_the_exit_code():
    got = run("closed")
    assert got.returncode == 0
    assert got.stdout == "imported"

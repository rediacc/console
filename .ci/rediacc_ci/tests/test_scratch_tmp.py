"""`scratch_tmp.install`: the umask and TMPDIR it changes for a run are put back, and a TMPDIR outside the system temp base is replaced by a private scratch directory (reviews b49f597f.3, .4, .5)."""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import seams
from rediacc_ci.tests import scratch_tmp


class _Config:
    def __init__(self) -> None:
        self.option = SimpleNamespace(basetemp=None)
        self.cleanups: list = []

    def add_cleanup(self, func) -> None:
        self.cleanups.append(func)

    def teardown(self) -> None:
        while self.cleanups:
            self.cleanups.pop()()


@pytest.fixture(name="umask_back")
def _umask_back():
    before = os.umask(0o002)
    try:
        yield
    finally:
        os.umask(before)


@pytest.mark.usefixtures("umask_back")
def test_install_clears_group_write_and_teardown_restores_the_umask(monkeypatch) -> None:
    # Review ee688bc8.1: TMPDIR and tempfile.tempdir go through monkeypatch, so the real values come back even when an assertion fails before teardown, and the scratch directory install made is asserted gone (and removed in a finally) on every host.
    original = os.environ.get("TMPDIR", tempfile.gettempdir())
    monkeypatch.setenv("TMPDIR", original)
    monkeypatch.setattr(tempfile, "tempdir", None)
    config = _Config()
    scratch_tmp.install(config)
    scratch = os.environ["TMPDIR"]
    cleared = os.umask(0o000)
    os.umask(cleared)
    try:
        config.teardown()
        assert os.environ["TMPDIR"] == original, "TMPDIR must be put back at teardown"
        assert not os.path.exists(scratch) or scratch == original, scratch
    finally:
        if scratch != original:
            shutil.rmtree(scratch, ignore_errors=True)
    restored = os.umask(0o000)
    os.umask(restored)
    assert cleared & 0o022 == 0o022, "group and other write must be cleared for the run"
    assert restored == 0o002, "the umask in force before install must come back"


@pytest.mark.usefixtures("umask_back")
def test_a_tmpdir_outside_the_base_is_replaced_then_restored(monkeypatch) -> None:
    base = seams.system_temp_base()
    if base is None:
        pytest.skip("no system temp base on this host")
    outside = paths.repo_root()
    monkeypatch.setenv("TMPDIR", str(outside))
    monkeypatch.setattr(tempfile, "tempdir", None)
    assert not seams.inside_temp(tempfile.gettempdir()), (
        "the fixture TMPDIR must sit outside the base"
    )
    config = _Config()
    scratch_tmp.install(config)
    scratch = os.environ["TMPDIR"]
    try:
        assert seams.inside_temp(scratch)
        assert config.option.basetemp == os.path.join(scratch, "basetemp")
        config.teardown()
        assert os.environ["TMPDIR"] == str(outside), "TMPDIR must be put back at teardown"
        assert not os.path.exists(scratch), (
            "the run's scratch directory must be removed at teardown"
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


@pytest.mark.usefixtures("umask_back")
def test_a_tmpdir_already_inside_the_base_is_replaced_and_restored(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", None)
    config = _Config()
    scratch_tmp.install(config)
    scratch = os.environ["TMPDIR"]
    try:
        assert scratch != str(tmp_path)
        assert seams.inside_temp(scratch)
        assert config.option.basetemp == os.path.join(scratch, "basetemp")
        config.teardown()
        assert os.environ["TMPDIR"] == str(tmp_path)
        assert not os.path.exists(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


_CHILD = """
import sys, time
from types import SimpleNamespace
from rediacc_ci.tests import scratch_tmp

class Config:
    option = SimpleNamespace(basetemp=None)
    def add_cleanup(self, func):
        pass

scratch_tmp.install(Config())
import os
print(os.environ["TMPDIR"], flush=True)
time.sleep(600)
"""


@pytest.mark.usefixtures("umask_back")
def test_a_killed_runs_scratch_is_removed_by_the_next_install(monkeypatch) -> None:
    base = seams.system_temp_base()
    if base is None:
        pytest.skip("no system temp base on this host")
    outside = paths.repo_root()
    monkeypatch.setenv("TMPDIR", str(outside))
    monkeypatch.setattr(tempfile, "tempdir", None)
    child_env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    child = subprocess.Popen(
        [sys.executable, "-c", _CHILD],
        stdout=subprocess.PIPE,
        text=True,
        env=child_env,
    )
    orphan = ""
    try:
        assert child.stdout is not None
        orphan = child.stdout.readline().strip()
        assert os.path.isdir(orphan), "the child's scratch directory must exist before the kill"
        child.send_signal(signal.SIGKILL)
    finally:
        child.kill()
        child.wait()
        if child.stdout is not None:
            child.stdout.close()
    config = _Config()
    scratch_tmp.install(config)
    scratch = os.environ["TMPDIR"]
    try:
        assert not os.path.exists(orphan), (
            "the next run's install must remove the killed run's scratch"
        )
    finally:
        config.teardown()
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(orphan, ignore_errors=True)

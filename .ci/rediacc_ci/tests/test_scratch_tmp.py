"""`scratch_tmp.install`: the umask and TMPDIR it changes for a run are put back, and a TMPDIR outside the system temp base is replaced by a private scratch directory (reviews b49f597f.3, .4, .5)."""

import os
import shutil
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
def test_install_clears_group_write_and_teardown_restores_the_umask() -> None:
    config = _Config()
    scratch_tmp.install(config)
    cleared = os.umask(0o000)
    os.umask(cleared)
    config.teardown()
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
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


@pytest.mark.usefixtures("umask_back")
def test_a_tmpdir_already_inside_the_base_is_left_alone(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", None)
    config = _Config()
    scratch_tmp.install(config)
    assert os.environ["TMPDIR"] == str(tmp_path)
    assert config.option.basetemp is None
    config.teardown()

"""block_binary_deploy and a recursive scp to an ops VM (review fe6ccbbb.2): `scp -r bin vm:/tmp/` sends bin/renet though no source is named renet. The directory is read on disk, so these cases live here and not in the guard's EDGE_CASES, whose golden is replayed wherever it runs."""

import json
import pathlib
import subprocess
import sys

import pytest

from rediacc_hooks.guards import block_binary_deploy as G

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")


def _rc(cmd, cwd):
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)}
    p = subprocess.run(
        [sys.executable, DISPATCH, "block_binary_deploy"],
        input=json.dumps(payload),
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=60,
    )
    return p.returncode


@pytest.fixture
def world(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "renet").write_bytes(b"\x7fELF")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.txt").write_text("x")
    return tmp_path


@pytest.mark.parametrize(
    "cmd",
    [
        "scp -r bin 192.168.111.22:/tmp/",
        "scp -rp bin developer@192.168.111.22:/tmp/",
        "scp -r . 192.168.111.22:/tmp/",
        "scp -P 22 -r bin/ 192.168.111.22:/tmp/",
    ],
)
def test_a_recursive_source_holding_renet_is_a_deploy(world, cmd):
    assert _rc(cmd, world) == 2


@pytest.mark.parametrize(
    "cmd",
    [
        "scp -r docs 192.168.111.22:/tmp/",
        # Without -r scp refuses a directory source, so nothing inside it is sent.
        "scp bin 192.168.111.22:/tmp/",
        # A source that is not on disk sends nothing.
        "scp -r missing 192.168.111.22:/tmp/",
    ],
)
def test_a_recursive_source_without_renet_is_dev_work(world, cmd):
    """CONTROL: the same shapes without renet inside stay allowed, so the refusal above is the directory's content and not `-r` alone."""
    assert _rc(cmd, world) == 0


def test_a_tree_past_the_walk_cap_is_judged_as_carrying_renet(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "_WALK_CAP", 3)
    for i in range(5):
        (tmp_path / ("f%d" % i)).write_text("x")
    assert G._tree_carries_renet(str(tmp_path))
    monkeypatch.setattr(G, "_WALK_CAP", 50)
    assert not G._tree_carries_renet(str(tmp_path))


def test_recursive_reads_bundles_and_stops_at_a_value_letter():
    assert G._recursive(["-rp", "a", "h:/p"])
    assert G._recursive(["-pr", "a", "h:/p"])
    assert not G._recursive(["-P", "r", "a", "h:/p"])
    assert not G._recursive(["-Pr", "a", "h:/p"])
    assert not G._recursive(["--", "-r", "h:/p"])

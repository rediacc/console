"""A full regolden refuses to lose committed case ids unless `--allow-shrink` (finding #569a06ac).

The three recorders (`_record_guard`, `_record_shellscan`, `_record_post_bash`) enumerate the cases that exist now and write only those, so a committed record they no longer ask for used to vanish silently. Each test seeds a golden holding one id the run cannot produce, then drives `regolden.main` in a child process (importing `regolden` sets `REDIACC_GUARD_DIFF_FULL`, which must not leak into this process). The control neuters `refuse_shrink` and shows the id disappearing, so the refusal tests can fail.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import textwrap

import pytest

from rediacc_hooks.tests import goldenio

HERE = pathlib.Path(__file__).resolve().parent
GONE = "case-that-no-longer-exists"
ROW = {"rc": "2", "out": "", "err": goldenio.encode_field("BLOCKED\n")}

DRIVER = textwrap.dedent(
    """
    import importlib.util, pathlib, sys
    spec = importlib.util.spec_from_file_location("regolden_under_test", sys.argv[1])
    rg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rg)
    rg.goldenio.GOLDEN_DIR = pathlib.Path(sys.argv[2])
    target, neuter = sys.argv[3], sys.argv[4] == "neuter"
    if neuter:
        rg.goldenio.refuse_shrink = lambda *a, **k: None
    if target == "post-bash":
        rg.pd.CASES = rg.pd.CASES[:1]
    elif target == "shellscan":
        rg.sd.CASES = rg.sd.CASES[:1]
        rg.sd.JSON_CASES = []
    else:
        first = [c for c in rg.gd.CASES if c[0] == target][:1]
        rg.gd.CASES = first
    sys.exit(rg.main([target, "--reason", "r", *sys.argv[5:]]))
    """
)


def _guard_stem():
    # One guard stem with a committed golden; the child only reads its cases, the seeded golden is a tmp file.
    return min(p.stem for p in goldenio.GOLDEN_DIR.glob("block_*.jsonl"))


def _run(tmp_path, target, *extra, neuter=False):
    (tmp_path / "driver.py").write_text(DRIVER, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(tmp_path / "driver.py"),
            str(HERE / "regolden.py"),
            str(tmp_path / "goldens"),
            target,
            "neuter" if neuter else "real",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def _seed(tmp_path, target):
    """A golden for `target` holding only GONE, in the child's redirected golden directory."""
    path = tmp_path / "goldens" / ("%s.jsonl" % target)
    if target.startswith("block_"):
        goldenio.write_golden(path, {"source": "port"}, {GONE}, {})
    else:
        goldenio.write_golden(path, {"source": "port"}, set(), {GONE: dict(ROW)})
    return path


def _targets():
    return ["post-bash", "shellscan", _guard_stem()]


@pytest.mark.parametrize("target", _targets())
def test_a_full_rerecord_that_loses_a_case_is_refused_and_writes_nothing(tmp_path, target):
    path = _seed(tmp_path, target)
    before = path.read_bytes()
    got = _run(tmp_path, target)
    assert got.returncode == 1, (got.stdout, got.stderr)
    assert GONE in got.stderr
    assert "--allow-shrink" in got.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("target", _targets())
def test_allow_shrink_drops_the_lost_case(tmp_path, target):
    path = _seed(tmp_path, target)
    got = _run(tmp_path, target, "--allow-shrink")
    assert got.returncode == 0, (got.stdout, got.stderr)
    _header, silent, records = goldenio.read_golden(path)
    assert GONE not in silent
    assert GONE not in records


@pytest.mark.parametrize("target", _targets())
def test_control_without_the_refusal_the_case_vanishes_silently(tmp_path, target):
    """CONTROL: the pre-fix write path rc=0 and the id is gone, so the refusal tests above can fail."""
    path = _seed(tmp_path, target)
    got = _run(tmp_path, target, neuter=True)
    assert got.returncode == 0, (got.stdout, got.stderr)
    _header, silent, records = goldenio.read_golden(path)
    assert GONE not in silent
    assert GONE not in records


def test_refuse_shrink_unit():
    goldenio.refuse_shrink("x", {"a"}, {"b": {}}, {"a"}, {"b": {}, "c": {}})
    with pytest.raises(goldenio.ShrinkRefusedError, match="2 case"):
        goldenio.refuse_shrink("x", {"a"}, {"b": {}}, set(), {})
    goldenio.refuse_shrink("x", {"a"}, {"b": {}}, set(), {}, allow_shrink=True)

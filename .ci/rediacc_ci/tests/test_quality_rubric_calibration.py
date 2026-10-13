"""`check:ci-rubric-calibration`, driven for real.

The npm script runs the gate on the tree and never its `selftest()`, so before this file the gate's plants (a stale sha, an orphaned entry, and since review 18700a76 a stale ride-along hash and a fixture quoting its rubric) executed nowhere in CI. This file runs them, runs the gate on the real tree, and runs the calibrator's offline controls, which prove the on-disk `already` exclusion the SHAPE fixtures lean on.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import rubric_calibration as gate


def test_the_real_tree_is_green(capsys) -> None:
    assert gate.main([]) == 0
    out = capsys.readouterr().out
    # The shape, not just the verdict: a collapsed fixture count or ride table would still exit 0 only if the floors failed open.
    assert "ride-along hash(es) current" in out, out
    match = re.search(r"; (\d+) fixture\(s\) across 3 list\(s\)", out)
    assert match, out
    scanned = int(match.group(1))
    assert scanned >= 15, "the held-out check compared only %d fixture(s)" % scanned


def test_the_controls_run_and_pass() -> None:
    assert gate.selftest() == 0, "a control failed; see the ok/FAIL lines above"


def test_every_rider_names_a_real_rubric() -> None:
    for rider, ridden in gate.RIDES.items():
        assert rider in gate.SOURCES, rider
        assert ridden, rider
        for other in ridden:
            assert other in gate.SOURCES, (rider, other)
            assert other != rider, rider


def test_quoted_finds_a_shared_run_and_ignores_a_short_one() -> None:
    rubrics = {"R": "Examples: DEFAULT: leave it on its branch. Then more."}
    leak = {"L": [("label", ["x? DEFAULT: leave it on its branch."])]}
    short = {"L": [("label", ["x? DEFAULT: keep carrying it."])]}
    assert [f[3] for f in gate.quoted(rubrics, leak)] == ["default leave it on its"]
    assert gate.quoted(rubrics, short) == []


def test_the_calibrator_offline_controls_pass() -> None:
    script = paths.repo_root() / ".claude/hooks/stop/calibrate-judge-rules.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--selftest"], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    match = re.search(r"^(\d+)/(\d+) offline control\(s\) passed$", proc.stdout, re.MULTILINE)
    assert match, proc.stdout
    assert match.group(1) == match.group(2), proc.stdout
    assert int(match.group(1)) >= 8, proc.stdout


# Review fdb82cba.2: `fixtures()` kept only tuple entries, so a fixture written as a list was never scanned, and a quote in it passed.
RUBRIC = {"R": "Examples: DEFAULT: leave it on its branch. Then more."}
LEAK = "x? DEFAULT: leave it on its branch."


def test_a_list_shaped_fixture_is_scanned() -> None:
    cases = gate.fixtures("SWEEP_CASES = [\n    ['as a list', 'fire', %r],\n]\n" % LEAK)
    assert cases == {"SWEEP_CASES": [("as a list", [LEAK])]}
    assert [f[1] for f in gate.quoted(RUBRIC, cases)] == ["as a list"]


def test_a_tuple_shaped_fixture_is_still_scanned() -> None:
    cases = gate.fixtures("BRAVE_CASES = [\n    ('as a tuple', 'fire', %r),\n]\n" % LEAK)
    assert cases == {"BRAVE_CASES": [("as a tuple", [LEAK])]}


@pytest.mark.parametrize(
    "entry", ["{'label': 'x', 'sends': %r}" % LEAK, repr(LEAK), "('label only', 'fire')"]
)
def test_an_unknown_fixture_shape_is_refused_loudly(entry: str) -> None:
    with pytest.raises(gate.FixtureShapeError, match=r"SHAPE_CASES\[0\]"):
        gate.fixtures("SHAPE_CASES = [\n    %s,\n]\n" % entry)


def test_the_gate_refuses_an_unknown_fixture_shape_on_a_copy(tmp_path, capsys) -> None:
    real = paths.repo_root()
    source = (real / gate.CALIBRATOR).read_text(encoding="utf-8")
    planted = source.replace(
        "SHAPE_CASES = [\n", "SHAPE_CASES = [\n    {'not': 'a sequence'},\n", 1
    )
    assert planted != source, "the plant did not apply; SHAPE_CASES moved"
    (tmp_path / gate.CALIBRATOR).parent.mkdir(parents=True)
    (tmp_path / gate.CALIBRATOR).write_text(planted, encoding="utf-8")
    rc, _ = gate.check_held_out(tmp_path, gate.texts(real))
    assert rc == 1
    assert "SHAPE_CASES[0]" in capsys.readouterr().err

"""The drill-leg half of `.ci/scripts/quality/check_test_file_orphans.py` (box J5 of agent/plans/PLAN-backup-program.md): a leg a drill declares must be run by a workflow or named with a `BLOCKER:` reason.

Both directions per helper: a leg a workflow runs is reached and one it does not run is reported; an exemption for a reached leg, for an undeclared leg, or without a BLOCKER reason is a problem. The last case runs the real gate on the live tree, so the production exemption table is judged against the real workflows.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
GATE = REPO / ".ci" / "scripts" / "quality" / "check_test_file_orphans.py"
_SPEC = importlib.util.spec_from_file_location("orphans_gate_under_test", GATE)
assert _SPEC is not None
assert _SPEC.loader is not None
ORPHANS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ORPHANS)

REASON = "BLOCKER: this leg needs an ops VM that no CI job provides, so it runs by hand"
DRILLS = {"backup": (["a", "b", "i"], ["a", "b"]), "license": (["a", "b"], ["a", "b"])}


def test_module_legs_reads_known_and_default(tmp_path):
    path = tmp_path / "d.py"
    path.write_text('KNOWN_LEGS = ["a", "b", "i"]\nDEFAULT_LEGS = "a,b"\n', encoding="utf-8")
    assert ORPHANS._module_legs(path) == (["a", "b", "i"], ["a", "b"])
    path.write_text('KNOWN_LEGS = ["a"]\n', encoding="utf-8")
    assert ORPHANS._module_legs(path) == (["a"], ["a"])
    path.write_text("LEGS = 1\n", encoding="utf-8")
    assert ORPHANS._module_legs(path) is None


def test_ci_drill_runs_reads_default_and_named_legs():
    text = (
        "      - run: ./run.sh drill backup --keep-work\n"
        "      # ./run.sh drill license is prose, not a run\n"
        "      - run: PYTHONPATH=.ci python3 -m rediacc_ci.drills.license \\\n"
        "          --legs b --no-restart\n"
    )
    assert ORPHANS.ci_drill_runs(text, DRILLS) == {"backup": {"a", "b"}, "license": {"b"}}


def test_a_comment_is_not_a_run():
    assert ORPHANS.ci_drill_runs("# ./run.sh drill backup\n", DRILLS) == {}


def test_an_unreached_leg_is_reported():
    unreached, problems, exempted = ORPHANS.drill_leg_findings(DRILLS, {"backup": {"a", "b"}}, {})
    assert unreached == ["backup:i", "license:a", "license:b"]
    assert (problems, exempted) == ([], 0)


def test_an_exempt_leg_passes_and_is_counted():
    exempt = {"backup": {"i": REASON}, "license": {"a": REASON, "b": REASON}}
    assert ORPHANS.drill_leg_findings(DRILLS, {"backup": {"a", "b"}}, exempt) == ([], [], 3)


def test_an_exemption_for_a_reached_leg_is_stale():
    _, problems, _ = ORPHANS.drill_leg_findings(
        DRILLS, {"backup": {"a", "b", "i"}}, {"backup": {"i": REASON}}
    )
    assert any("debt paid" in p for p in problems)


def test_an_exemption_for_an_undeclared_leg_is_stale():
    _, problems, _ = ORPHANS.drill_leg_findings(DRILLS, {}, {"backup": {"z": REASON}})
    assert any("declares no leg z" in p for p in problems)


def test_an_exemption_without_a_blocker_is_refused():
    _, problems, _ = ORPHANS.drill_leg_findings(DRILLS, {}, {"backup": {"i": "local only"}})
    assert any("BLOCKER" in p for p in problems)


def test_the_real_gate_passes_on_the_live_tree():
    done = subprocess.run(
        [sys.executable, str(GATE)], capture_output=True, text=True, check=False, cwd=REPO
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "drill leg(s) of" in done.stdout
    # The backup drill's default legs are reached by the CI drill job, so leg i is the only backup exemption.
    assert set(ORPHANS.DRILL_LEG_EXEMPT["backup"]) == {"i"}

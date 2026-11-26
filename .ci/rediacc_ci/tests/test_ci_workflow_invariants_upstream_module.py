"""An upstream gate run as its registered Python module counts as its step (9edc242388 moved check:ci-ops-health off npm)."""

from rediacc_ci.security import ci_workflow_invariants as inv


def _doc(run: str) -> dict:
    return {"jobs": {"quality-go": {"steps": [{"name": "ops health", "run": run}]}}}


def test_the_registered_module_counts_as_the_gate_step() -> None:
    found = inv.upstream_gate_steps(_doc("PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health"))
    assert [(job, i) for job, i, _ in found["check:ci-ops-health"]] == [("quality-go", 0)]


def test_control_the_npm_form_still_counts() -> None:
    found = inv.upstream_gate_steps(_doc("npm run check:ci-ops-health"))
    assert len(found["check:ci-ops-health"]) == 1


def test_control_another_module_does_not_count() -> None:
    found = inv.upstream_gate_steps(
        _doc("PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health_extra")
    )
    assert found["check:ci-ops-health"] == []


def test_a_gate_named_only_in_an_echo_or_a_comment_does_not_count() -> None:
    """ee21aba7.1: text that mentions the module or the npm script without running it is not the step."""
    for run in (
        "echo PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health",
        "# PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health\ntrue",
        "true # npm run check:ci-ops-health",
        'printf "%s" "npm run check:ci-ops-health"',
    ):
        assert inv.upstream_gate_steps(_doc(run))["check:ci-ops-health"] == [], run


def test_a_gate_run_after_other_lines_still_counts() -> None:
    found = inv.upstream_gate_steps(
        _doc("echo start\nPYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health\n")
    )
    assert len(found["check:ci-ops-health"]) == 1


def test_a_gate_chained_after_an_echo_on_one_line_still_counts() -> None:
    """17f9d3d7.2: `echo start && npm run <gate>` runs the gate, so the echo prefix does not hide it; text chained after an echo stays text."""
    for run in (
        "echo start && npm run check:ci-ops-health",
        "echo a; echo b && PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health",
    ):
        assert len(inv.upstream_gate_steps(_doc(run))["check:ci-ops-health"]) == 1, run
    for run in (
        "echo start && echo npm run check:ci-ops-health",
        "echo start && true # npm run check:ci-ops-health",
    ):
        assert inv.upstream_gate_steps(_doc(run))["check:ci-ops-health"] == [], run

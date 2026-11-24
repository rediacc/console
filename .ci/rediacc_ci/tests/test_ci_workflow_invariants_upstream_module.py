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

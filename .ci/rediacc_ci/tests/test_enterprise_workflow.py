"""The Enterprise release workflow (PLAN-enterprise-isolation.md G1): the mask comes first and nothing deletes a company."""

from __future__ import annotations

from rediacc_ci import paths, workflows

WORKFLOWS = paths.repo_root() / ".github" / "workflows"
RELEASE = WORKFLOWS / "cd-enterprise-release.yml"


def _steps() -> list[dict]:
    return workflows.load(RELEASE)["jobs"]["release"]["steps"]


def test_no_workflow_calls_enterprise_remove() -> None:
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text()
        assert "enterprise remove" not in text, wf.name
        assert "enterprise_remove" not in text, wf.name


def test_release_is_dispatch_only_with_no_delete_input() -> None:
    doc = workflows.load(RELEASE)
    triggers = doc.get("on", doc.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert "company" in inputs
    assert not [k for k in inputs if "delete" in k or "remove" in k]


def test_mask_step_comes_first_and_masks_the_company_input() -> None:
    first = _steps()[0]
    assert "::add-mask::" in first["run"]
    assert "inputs.company" in first["env"]["COMPANY"]
    assert "uses" not in first


def test_company_input_reaches_only_env_never_a_run_line() -> None:
    for step in _steps():
        assert "inputs.company" not in step.get("run", ""), step.get("name")

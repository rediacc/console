"""The Enterprise release workflow (PLAN-enterprise-isolation.md G1): the mask comes first and nothing deletes a company."""

from __future__ import annotations

import io
import json

from rediacc_ci import paths, workflows
from rediacc_ci.release import redacted_tee

WORKFLOWS = paths.repo_root() / ".github" / "workflows"
RELEASE = WORKFLOWS / "cd-enterprise-release.yml"


def _steps() -> list[dict]:
    return workflows.load(RELEASE)["jobs"]["release"]["steps"]


def test_no_workflow_calls_enterprise_remove() -> None:
    for wf in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
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
        rest = {k: v for k, v in step.items() if k != "env"}
        assert "inputs.company" not in json.dumps(rest), step.get("name")


def test_step_summary_copy_goes_through_the_redacting_tee() -> None:
    """`::add-mask::` never covers the step-summary file, so the release step pipes the runner through redacted_tee."""
    step = next(s for s in _steps() if s.get("name") == "Release the rings")
    assert "GITHUB_STEP_SUMMARY" not in step["run"]
    assert "| tee" not in step["run"]
    assert "rediacc_ci.release.redacted_tee" in step["run"]
    assert step["shell"] == "bash"


def test_redacted_tee_replaces_the_company_in_the_summary_only(
    tmp_path, monkeypatch, capsys
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("COMPANY", "c0123456789abcdef")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr("sys.stdin", io.StringIO("deploy c0123456789abcdef ok\nno id\n"))
    assert redacted_tee.main() == 0
    assert "c0123456789abcdef" in capsys.readouterr().out
    assert summary.read_text() == "deploy *** ok\nno id\n"


def test_redacted_tee_with_no_company_passes_text_through() -> None:
    assert redacted_tee.redact("x c0123456789abcdef", "") == "x c0123456789abcdef"

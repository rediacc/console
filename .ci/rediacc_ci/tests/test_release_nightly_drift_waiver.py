"""The nightly waiver on a drift-red nightly (PLAN-plan-per-pr-loop R1).

The scheduled Console CI went red every night from 2026-09-07 on, mostly because upstream published something (an advisory, a newer dependency), so the "a green nightly waives the soak" rule never fired. `nightly_failures_are_drift_only` accepts a failed run only when every failed step is in `DRIFT_STEPS`. The fake runs below carry the shape `actions/runs/<id>/jobs` returns, with the job and step names the real nightlies used (runs 36827121342, 36974916837).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.release import check_soak_period, nightly_tested_edge
from rediacc_ci.release.nightly_tested_edge import nightly_failures_are_drift_only
from rediacc_ci.well_known import GH_REPO

if TYPE_CHECKING:
    import pathlib


def step(name: str, conclusion: str | None = "success") -> dict[str, Any]:
    return {"name": name, "status": "completed", "conclusion": conclusion}


def job(
    name: str,
    conclusion: str | None = "success",
    steps: list[dict[str, Any]] | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "steps": steps or [step("Set up job")],
    }


def green_jobs() -> list[dict[str, Any]]:
    return [
        job("Initialize"),
        job(
            "Quality / Security",
            steps=[step("Tracked credentials"), step("Audit"), step("Suppression liveness")],
        ),
        job(
            "Quality / Content", steps=[step("External dependency freshness"), step("Prose style")]
        ),
        job("Quality / Pytest (2/3)", steps=[step("Python package tests")]),
        job("Tests + Infra / Unit", steps=[step("Run unit tests")]),
        job("Tests + Infra / Linux Packages", steps=[step("Run Linux package tests")]),
        job("Build (Docker) / CLI Docker", "skipped"),
        job("CI Complete", steps=[step("Check all jobs passed")]),
    ]


def with_job(jobs: list[dict[str, Any]], replacement: dict[str, Any]) -> list[dict[str, Any]]:
    return [replacement if j["name"] == replacement["name"] else j for j in jobs]


def audit_failed(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The audit step fails, the steps after it in that job are skipped, and the aggregator fails with it."""
    jobs = with_job(
        jobs,
        job(
            "Quality / Security",
            "failure",
            [
                step("Tracked credentials"),
                step("Audit", "failure"),
                step("Suppression liveness", "skipped"),
            ],
        ),
    )
    return with_job(jobs, job("CI Complete", "failure", [step("Check all jobs passed", "failure")]))


def test_only_the_audit_gate_failing_is_accepted() -> None:
    accepted, reason = nightly_failures_are_drift_only(audit_failed(green_jobs()))
    assert accepted, reason
    assert "Quality / Security / Audit" in reason


def test_both_drift_gates_failing_is_accepted() -> None:
    jobs = with_job(
        audit_failed(green_jobs()),
        job(
            "Quality / Content",
            "failure",
            [step("External dependency freshness", "failure"), step("Prose style", "skipped")],
        ),
    )
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert accepted, reason


def test_a_failed_test_lane_is_refused() -> None:
    jobs = with_job(
        green_jobs(),
        job("Quality / Pytest (2/3)", "failure", [step("Python package tests", "failure")]),
    )
    jobs = with_job(jobs, job("CI Complete", "failure", [step("Check all jobs passed", "failure")]))
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert not accepted
    assert "Python package tests" in reason


def test_a_cancelled_job_is_refused() -> None:
    jobs = with_job(
        audit_failed(green_jobs()),
        job("Tests + Infra / Unit", "cancelled", [step("Run unit tests", "cancelled")]),
    )
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert not accepted
    assert "cancelled" in reason


def test_drift_plus_a_test_failure_is_refused() -> None:
    jobs = with_job(
        audit_failed(green_jobs()),
        job("Tests + Infra / Unit", "failure", [step("Run unit tests", "failure")]),
    )
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert not accepted
    assert "Run unit tests" in reason


def test_a_non_drift_step_failing_inside_the_security_job_is_refused() -> None:
    """Step level, not job level: Quality / Security also runs real checks beside the audit."""
    jobs = with_job(
        green_jobs(),
        job(
            "Quality / Security",
            "failure",
            [step("Tracked credentials", "failure"), step("Audit", "failure")],
        ),
    )
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert not accepted
    assert "Tracked credentials" in reason


def test_a_failed_job_with_no_failed_step_is_refused() -> None:
    """A runner loss or a job timeout fails the job with every step still green; that is not a drift gate's failure."""
    jobs = with_job(
        audit_failed(green_jobs()), job("Tests + Infra / Unit", "failure", [step("Run unit tests")])
    )
    accepted, _ = nightly_failures_are_drift_only(jobs)
    assert not accepted


def test_a_test_lane_skipped_by_the_quality_failure_is_refused() -> None:
    """`Tests + Infra / Linux Packages` must run on a scheduled nightly; skipped is not passed."""
    jobs = with_job(audit_failed(green_jobs()), job("Tests + Infra / Linux Packages", "skipped"))
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert not accepted
    assert "Linux Packages" in reason


def test_a_job_still_running_is_refused() -> None:
    jobs = with_job(
        audit_failed(green_jobs()), job("Tests + Infra / Unit", None, status="in_progress")
    )
    accepted, _ = nightly_failures_are_drift_only(jobs)
    assert not accepted


def test_an_empty_job_list_is_refused() -> None:
    assert nightly_failures_are_drift_only([]) == (False, "the run's job list is empty")


def test_fetch_run_jobs_merges_every_page() -> None:
    calls: list[str] = []

    def api(path: str, **_: object) -> object:
        calls.append(path)
        return [
            {"total_count": 3, "jobs": [job("a"), job("b")]},
            {"total_count": 3, "jobs": [job("c")]},
        ]

    jobs = nightly_tested_edge.fetch_run_jobs("o/r", "42", api=api)
    assert [j["name"] for j in jobs] == ["a", "b", "c"]
    assert calls == ["repos/o/r/actions/runs/42/jobs?filter=latest&per_page=100"]


# --- check_soak_period on a failed nightly ------------------------------------
#
# In process, with the job read and the git ancestry proof replaced: the claims under test are what the soak check DECIDES from a verdict, and both of those inputs have their own tests (above, and test_release_check_soak_period.py against a real repository).


@pytest.fixture
def soak_env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    out = tmp_path / "output.txt"
    for name in ("FORCE", "EDGE_RELEASES", "STABLE_VERSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv(
        "EDGE_DATE", "2020-01-01T00:00:00"
    )  # long soaked, so a soak fallback WOULD promote
    monkeypatch.setenv("SOAK_DAYS", "7")
    monkeypatch.setenv("EDGE_VERSION", "1.2.3")
    monkeypatch.setenv("PROMOTE_TRIGGER", "workflow_run")
    monkeypatch.setenv("NIGHTLY_HEAD_SHA", "a" * 40)
    monkeypatch.setenv("NIGHTLY_CONCLUSION", "failure")
    monkeypatch.setenv("NIGHTLY_RUN_ID", "36827121342")
    monkeypatch.setenv("GITHUB_REPOSITORY", GH_REPO)
    monkeypatch.setattr(
        check_soak_period,
        "edge_tested_by_nightly",
        lambda version, *_: (True, f"edge v{version} contained"),
    )
    return out


def outputs(out: pathlib.Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())


def test_soak_check_waives_on_a_drift_only_failed_nightly(
    soak_env: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        nightly_tested_edge, "fetch_run_jobs", lambda *_: audit_failed(green_jobs())
    )
    assert check_soak_period.main([]) == 0
    got = outputs(soak_env)
    assert (got["ready"], got["path"], got["version"]) == ("true", "nightly", "1.2.3")


def test_soak_check_refuses_a_nightly_with_a_test_failure_even_when_soaked(
    soak_env: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = with_job(
        audit_failed(green_jobs()),
        job("Tests + Infra / Unit", "failure", [step("Run unit tests", "failure")]),
    )
    monkeypatch.setattr(nightly_tested_edge, "fetch_run_jobs", lambda *_: jobs)
    assert check_soak_period.main([]) == 0
    got = outputs(soak_env)
    assert (got["ready"], got["path"], got["version"]) == ("false", "nightly", "")


def test_soak_check_refuses_a_cancelled_nightly(
    soak_env: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NIGHTLY_CONCLUSION", "cancelled")
    monkeypatch.setattr(
        nightly_tested_edge,
        "fetch_run_jobs",
        lambda *_: pytest.fail("a cancelled run is never read"),
    )
    assert check_soak_period.main([]) == 0
    assert outputs(soak_env)["ready"] == "false"


def test_soak_check_refuses_when_the_jobs_cannot_be_read(
    soak_env: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: str) -> list[dict[str, Any]]:
        raise nightly_tested_edge.ghx.GhError(["gh", "api"], 1, "HTTP 502", "server")

    monkeypatch.setattr(nightly_tested_edge, "fetch_run_jobs", broken)
    assert check_soak_period.main([]) == 0
    assert outputs(soak_env)["ready"] == "false"

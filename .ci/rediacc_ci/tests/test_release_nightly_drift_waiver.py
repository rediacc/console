"""The nightly waiver on a drift-red nightly (PLAN-plan-per-pr-loop R1).

The scheduled Console CI went red every night from 2026-09-07 on, mostly because upstream published something (an advisory, a newer dependency), so the "a green nightly waives the soak" rule never fired. `nightly_failures_are_drift_only` accepts a failed run only when every failed step is a drift step (`drift_steps()`). The fake runs below carry the shape `actions/runs/<id>/jobs` returns, with the job and step names the real nightlies used (runs 36827121342, 36974916837), and one is the real run 39551246836 itself (fixtures/nightly_39551246836_attempt1.json).

The drift set is held to the workflows from three sides: it equals the workflows' own external steps (so a new external gate cannot be missed), each of its names is unique across `.github/workflows` (so a step elsewhere cannot borrow one), and every step after one in its job runs under `!cancelled()` (so a drift failure cannot skip a real check into a "skipped" the waiver reads as passed). PyYAML is importable by the system `python3` only, not by pytest's interpreter, so the workflows are parsed there and handed over as JSON (the pattern of test_security_ci_workflow_invariants).
"""

from __future__ import annotations

import copy
import functools
import json
import pathlib
import re
import subprocess
from typing import Any

import pytest

from rediacc_ci.core import ghx
from rediacc_ci.release import check_soak_period, nightly_tested_edge
from rediacc_ci.release.nightly_tested_edge import (
    GOVULNCHECK_STEP,
    OBS_UPSTREAM_STEP,
    DriftSetError,
    drift_steps,
    nightly_failures_are_drift_only,
)
from rediacc_ci.security import ci_workflow_invariants
from rediacc_ci.well_known import GH_REPO

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
REAL_RUN = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "nightly_39551246836_attempt1.json"
)


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
    assert calls == ["repos/o/r/actions/runs/42/jobs?filter=latest&per_page=30"]


# --- the real nightly 39551246836 (2026-10-21) ---------------------------------
#
# Attempt 1 failed in five jobs: Quality / Go (govulncheck, inside `Run renet quality`), Quality / Code (1) (Pin upstream freshness), Quality / Content (External dependency freshness), Renet pkg matrix (opensuse-16.0) (the OBS upstream check, inside `Run the package matrix`) and Quality / Shard receipts (because Code (1) failed). Promote job 119079428885 refused it on `Run renet quality`.


def real_run() -> list[dict[str, Any]]:
    return json.loads(REAL_RUN.read_text(encoding="utf-8"))["jobs"]


def split_steps(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The run as the split workflow records it: each mixed step passes, and the drift it carried fails in its own step after it.

    Exactly what the logs show: `Run renet quality` failed on govulncheck alone (GO-2026-6809), and `Run the package matrix` passed 13 of 14 checks, the 14th being `upstream: OBS still serves the pin`.
    """
    jobs = copy.deepcopy(jobs)
    split = {"Run renet quality": GOVULNCHECK_STEP, "Run the package matrix": OBS_UPSTREAM_STEP}
    for job in jobs:
        steps = []
        for st in job["steps"]:
            if st["name"] in split and st["conclusion"] == "failure":
                steps += [
                    {**st, "conclusion": "success"},
                    {"name": split[st["name"]], "conclusion": "failure"},
                ]
            else:
                steps.append(st)
        job["steps"] = steps
    return jobs


def test_the_fixture_is_the_real_attempt() -> None:
    """Anti-vacuity for the two tests below: the fixture holds the whole run and its five real failures."""
    jobs = real_run()
    assert len(jobs) == 205
    failed = sorted(j["name"] for j in jobs if j["conclusion"] == "failure")
    assert failed == [
        "CI Complete",
        "Quality / Code (1)",
        "Quality / Content",
        "Quality / Go",
        "Quality / Shard receipts",
        "Tests + Infra / Renet pkg matrix (opensuse-16.0)",
    ]


def test_the_real_nightly_under_the_split_is_accepted() -> None:
    accepted, reason = nightly_failures_are_drift_only(split_steps(real_run()))
    assert accepted, reason
    for named in (
        f"Quality / Go / {GOVULNCHECK_STEP}",
        "Quality / Code (1) / Pin upstream freshness",
        "Quality / Content / External dependency freshness",
        f"Tests + Infra / Renet pkg matrix (opensuse-16.0) / {OBS_UPSTREAM_STEP}",
    ):
        assert named in reason


def test_the_real_nightly_as_recorded_is_refused_on_the_mixed_step() -> None:
    """Why the split exists: before it, govulncheck failed inside a step that also lints, and the step verdict cannot tell the two apart."""
    accepted, reason = nightly_failures_are_drift_only(real_run())
    assert not accepted
    assert "'Run renet quality' failed and is not a drift gate" in reason


def test_a_real_failure_beside_the_real_drift_is_refused() -> None:
    """The control on the real shape: a lint failure in `Run renet quality` beside the same drift."""
    jobs = split_steps(real_run())
    go = next(j for j in jobs if j["name"] == "Quality / Go")
    next(st for st in go["steps"] if st["name"] == "Run renet quality")["conclusion"] = "failure"
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert not accepted
    assert "Run renet quality" in reason


@pytest.mark.parametrize("shard", [1, 2, 3, 4])
def test_pin_freshness_is_drift_under_any_code_shard(shard: int) -> None:
    """Keyed on the step, not the job: gate-bind moved Pin upstream freshness from shard 1 (main) to shard 4 (1020-1)."""
    code = f"Quality / Code ({shard})"
    jobs = [
        *green_jobs(),
        job(code, "failure", [step("Gates lock"), step("Pin upstream freshness", "failure")]),
        job("Quality / Shard receipts", "failure", [step("Quality shard receipts", "failure")]),
    ]
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert accepted, reason
    assert f"{code} / Pin upstream freshness" in reason


def test_shard_receipts_without_a_failed_shard_is_refused() -> None:
    """Shard receipts is derived only from a failed Code shard; failing with every shard green means one never reported, a wiring defect."""
    jobs = [
        *audit_failed(green_jobs()),
        job("Quality / Code (1)", steps=[step("Pin upstream freshness")]),
        job("Quality / Shard receipts", "failure", [step("Quality shard receipts", "failure")]),
    ]
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert not accepted
    assert "Shard receipts" in reason


def test_a_stray_failure_inside_shard_receipts_is_refused() -> None:
    """Only the receipts echo is derived: another failed step in the same job is judged like any step, beside a drift-failed shard too."""
    jobs = [
        *green_jobs(),
        job("Quality / Code (1)", "failure", [step("Pin upstream freshness", "failure")]),
        job(
            "Quality / Shard receipts",
            "failure",
            [step("Download shard receipts", "failure"), step("Quality shard receipts", "failure")],
        ),
    ]
    accepted, reason = nightly_failures_are_drift_only(jobs)
    assert not accepted
    assert "Download shard receipts" in reason


def test_an_unreadable_lock_refuses(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Could not tell is never a yes: no lock, no drift set, no waiver."""
    absent = tmp_path / "absent.json"
    monkeypatch.setattr(nightly_tested_edge, "drift_steps", lambda: drift_steps(absent))
    accepted, reason = nightly_failures_are_drift_only(audit_failed(green_jobs()))
    assert not accepted
    assert "drift set could not be derived" in reason


def test_a_lock_missing_a_drift_gate_raises(tmp_path: pathlib.Path) -> None:
    lock = tmp_path / "gates.lock.json"
    lock.write_text(
        json.dumps([{"id": "check:deps", "ci": {"kind": "step", "step": "x"}}]), encoding="utf-8"
    )
    with pytest.raises(DriftSetError, match="check:ci-security-audit"):
        drift_steps(lock)


# --- the drift set against the workflows ------------------------------------------


@functools.cache
def workflow_jobs() -> dict[str, dict[str, Any]]:
    """file name -> its `jobs`, parsed by the system python3 (the one with PyYAML)."""
    program = (
        "import json,pathlib,sys,yaml;"
        "print(json.dumps({p.name: (yaml.safe_load(p.read_text(encoding='utf-8')) or {}).get('jobs') or {}"
        " for p in sorted(pathlib.Path(sys.argv[1]).glob('*.yml'))}))"
    )
    proc = subprocess.run(
        ["python3", "-c", program, str(WORKFLOWS)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    jobs = json.loads(proc.stdout)
    assert len(jobs) > 10, (
        "the workflow directory read as nearly empty, so nothing below would be checked"
    )
    return jobs


def steps_running(workflow: str, job_id: str, pattern: str) -> list[str]:
    return [
        st.get("name", "")
        for st in workflow_jobs()[workflow][job_id].get("steps") or []
        if re.search(pattern, str(st.get("run", "")))
    ]


def test_the_drift_set_is_every_external_step_in_the_workflows() -> None:
    """Parity: the lock-derived set equals what the workflows run, so a new external gate (UPSTREAM_GATES) cannot be missed, and a renamed step cannot leave a stale name behind."""
    quality = {"jobs": workflow_jobs()["ci-quality.yml"]}
    upstream = {
        st["name"]
        for sites in ci_workflow_invariants.upstream_gate_steps(quality).values()
        for _job, _i, st in sites
    }
    assert len(upstream) == len(ci_workflow_invariants.UPSTREAM_GATES)
    audit = steps_running(
        "ci-quality.yml",
        "quality-security",
        r"(?:\bnpm run check:ci-security-audit|-m rediacc_ci\.security\.audit)(?![\w.:-])",
    )
    govuln = steps_running(
        "ci-quality.yml", "quality-go", r"rediacc_ci\.private\.run_renet govulncheck\b"
    )
    obs = steps_running(
        "ct-tests.yml", "renet-pkg-matrix", r"rediacc_ci\.infra\.renet_pkg_matrix upstream\b"
    )
    assert (len(audit), govuln, obs) == (1, [GOVULNCHECK_STEP], [OBS_UPSTREAM_STEP])
    assert drift_steps() == upstream | set(audit) | {GOVULNCHECK_STEP, OBS_UPSTREAM_STEP}


def test_every_drift_step_name_is_unique_across_the_workflows() -> None:
    """The waiver keys on the step name alone, so the same name on a real check anywhere would be excused as drift."""
    where: dict[str, list[str]] = {}
    for workflow, jobs in workflow_jobs().items():
        for job_id, body in jobs.items():
            for st in body.get("steps") or []:
                where.setdefault(str(st.get("name", "")), []).append(f"{workflow}:{job_id}")
    shared = {name: where.get(name, []) for name in drift_steps() if len(where.get(name, [])) != 1}
    assert shared == {}


_GUARDED = re.compile(r"\b(?:cancelled|always|failure)\(\)")


def test_no_step_after_a_drift_step_can_be_skipped_by_it() -> None:
    """A step after a drift step must run when it fails (`!cancelled()`, `always()` or `failure()` in its `if:`). Otherwise the drift failure SKIPS it, and the waiver reads skipped as passed: on run 39551246836 `PR epic block matches the published worklist` and `Every commit names its epic` were skipped behind Pin upstream freshness."""
    drift = drift_steps()
    unguarded = []
    seen: set[str] = set()
    for workflow, jobs in workflow_jobs().items():
        for job_id, body in jobs.items():
            after = None
            for st in body.get("steps") or []:
                name = str(st.get("name") or st.get("uses") or st.get("id"))
                if after is not None and not _GUARDED.search(str(st.get("if", ""))):
                    unguarded.append(f"{workflow}:{job_id}: {name!r} after {after!r}")
                if name in drift:
                    seen.add(name)
                    after = after or name
    assert seen == drift, (
        "a drift step was not found in any job, so its followers were never checked"
    )
    assert unguarded == []


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
        raise ghx.GhError(["gh", "api"], 1, "HTTP 502", "server")

    monkeypatch.setattr(nightly_tested_edge, "fetch_run_jobs", broken)
    assert check_soak_period.main([]) == 0
    assert outputs(soak_env)["ready"] == "false"


# --- gh_retry (PLAN-gh-retry G12): a transient read fault is retried, a non-transient one is not ---


class _FakeGh:
    """Scripted `gh` outcomes (rc, stdout, stderr), one per attempt, the last repeating. Patched in as the `runner` and `sleep` of `gh_retry.gh`, so nothing touches the network or the clock."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.slept = []

    def install(self, monkeypatch, module):
        real = module.gh_retry.gh
        fake = self

        def runner(args, **_kw):
            fake.calls.append(list(args))
            rc, out, err = fake.outcomes[min(len(fake.calls), len(fake.outcomes)) - 1]
            return module.gh_retry.ghx.GhResult(["gh", *args], rc, out, err)

        monkeypatch.setattr(
            module.gh_retry,
            "gh",
            lambda args, **kw: real(args, runner=runner, **{**kw, "sleep": fake.slept.append}),
        )
        return self


def test_fetch_run_jobs_retries_a_502_then_merges_pages(monkeypatch) -> None:
    pages = '[{"jobs":[{"name":"a"}]},{"jobs":[{"name":"b"}]}]'
    fake = _FakeGh((1, "", "gh: Server Error (HTTP 502)"), (0, pages, ""))
    fake.install(monkeypatch, nightly_tested_edge)
    jobs = nightly_tested_edge.fetch_run_jobs("o/r", "42")
    assert [j["name"] for j in jobs] == ["a", "b"]
    assert fake.slept == [5.0]
    assert fake.calls[0][-2:] == ["--paginate", "--slurp"]


def test_fetch_run_jobs_persistent_5xx_raises(monkeypatch) -> None:
    fake = _FakeGh((1, "", "gh: Server Error (HTTP 502)"))
    fake.install(monkeypatch, nightly_tested_edge)
    with pytest.raises(Exception, match="502"):
        nightly_tested_edge.fetch_run_jobs("o/r", "42")
    assert len(fake.calls) == 3


def test_fetch_run_jobs_404_is_not_retried(monkeypatch) -> None:
    fake = _FakeGh((1, "", "gh: Not Found (HTTP 404)"))
    fake.install(monkeypatch, nightly_tested_edge)
    with pytest.raises(Exception, match="404"):
        nightly_tested_edge.fetch_run_jobs("o/r", "42")
    assert len(fake.calls) == 1
    assert fake.slept == []

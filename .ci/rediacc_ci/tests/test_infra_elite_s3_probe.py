"""PLAN-backup-program A4d: the elite job runs the S3 conformance probe, and a non-conformant store turns it red.

Two things are held here, because either can rot alone:

1. The probe's own controls. `selftest` starts a conformant stub that must pass every probe and a stub that ignores
   `If-None-Match` that must fail `create-only-conflict`. A probe that cannot fail would make the wiring below worthless.
2. The wiring. The job that starts elite in `.github/workflows/ci.yml` must run `rediacc_ci.infra.elite_s3_probe`
   (selftest first, then live) after `rediacc_ci.infra.ci_start_elite`, in that same job, with no `if:` or `continue-on-error` that would keep a red probe from failing it. A copy of the workflow with the
   probe step removed, or moved before the start, must be judged unwired, so the check cannot pass on any workflow.

The live run against RustFS needs the CI job's container, so it is not run here: it runs in that job, which this wiring pins.
"""

from __future__ import annotations

import copy
import pathlib
import re

import pytest
import yaml

from rediacc_ci.infra import elite_s3_probe

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
START = "rediacc_ci.infra.ci_start_elite"
PROBE = "rediacc_ci.infra.elite_s3_probe"


def _step_runs(job: dict) -> list[str]:
    return [str(step.get("run", "")) for step in job.get("steps", [])]


def _calls(run: str) -> list[str]:
    """The probe invocations of one step's `run`, in order: the commands joined by `&&`, `;` or a newline that name the probe."""
    return [part for part in re.split(r"&&|;|\n", run) if PROBE in part]


def _can_fail(holder: dict, *, gated: bool = False) -> bool:
    """False when a step carries an `if:`, or a step or job is marked `continue-on-error`, either of which keeps a red probe from failing the job. A job's own `if:` is a legitimate skip gate (the suite switch), so `gated` refuses only one that is a constant false."""
    skipped = str(holder.get("if", "")).strip().lower() in {"false", "0"}
    conditional = skipped if gated else "if" in holder
    return not conditional and str(holder.get("continue-on-error", False)).lower() != "true"


def probe_wiring(workflow: dict) -> list[str]:
    """The jobs that start elite and do not run the probe after it (empty when every such job is wired).

    Wired means: a live probe call (no `--selftest`) in a step after the start, that step and the job carry no `if:` and no `continue-on-error`, the call does not end in `|| true`, and a `--selftest` call comes before it, in the same step or an earlier one.
    """
    unwired = []
    starters = 0
    for name, job in workflow.get("jobs", {}).items():
        runs = _step_runs(job)
        starts = [i for i, run in enumerate(runs) if START in run]
        if not starts:
            continue
        starters += 1
        steps = job["steps"]
        calls = [(i, n, call) for i, run in enumerate(runs) for n, call in enumerate(_calls(run))]
        live = [
            (i, n)
            for i, n, call in calls
            if "--selftest" not in call and "|| true" not in runs[i] and _can_fail(steps[i])
        ]
        selftests = [(i, n) for i, n, call in calls if "--selftest" in call]
        ok = (
            _can_fail(job, gated=True)
            and bool(live)
            and min(live) > (starts[0], 99)
            and bool(selftests)
            and min(selftests) < min(live)
        )
        if not ok:
            unwired.append(name)
    if starters == 0:
        unwired.append("<no job starts elite>")
    return unwired


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def test_the_probe_script_exists() -> None:
    assert (ROOT / "private" / "elite" / "scripts" / "s3-conformance-probe.sh").is_file()


def test_selftest_conformant_stub_passes_and_non_conformant_stub_is_red() -> None:
    probe = ROOT / "private" / "elite" / "scripts" / "s3-conformance-probe.sh"
    assert elite_s3_probe.selftest(probe) == 0


def test_the_job_that_starts_elite_probes_it_after_the_start(workflow: dict) -> None:
    assert probe_wiring(workflow) == []


def test_control_a_workflow_without_the_probe_step_is_unwired(workflow: dict) -> None:
    mutated = copy.deepcopy(workflow)
    for job in mutated["jobs"].values():
        job["steps"] = [s for s in job.get("steps", []) if PROBE not in str(s.get("run", ""))]
    assert probe_wiring(mutated) != []


def test_control_a_probe_step_before_the_start_is_unwired(workflow: dict) -> None:
    mutated = copy.deepcopy(workflow)
    for job in mutated["jobs"].values():
        runs = _step_runs(job)
        if not any(START in run for run in runs):
            continue
        steps = job["steps"]
        probe_step = next((s for s in steps if PROBE in str(s.get("run", ""))), None)
        assert probe_step is not None, "the job that starts elite has no probe step"
        steps.remove(probe_step)
        steps.insert(0, probe_step)
    assert probe_wiring(mutated) != []


def test_control_a_probe_step_without_the_selftest_is_unwired(workflow: dict) -> None:
    mutated = copy.deepcopy(workflow)
    for job in mutated["jobs"].values():
        for step in job.get("steps", []):
            if PROBE in str(step.get("run", "")):
                step["run"] = f"PYTHONPATH=.ci python3 -m {PROBE}"
    assert probe_wiring(mutated) != []


def _probe_steps(workflow: dict) -> list[dict]:
    return [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if PROBE in str(step.get("run", ""))
    ]


def test_control_a_probe_step_that_cannot_fail_the_job_is_unwired(workflow: dict) -> None:
    for key, value in (("continue-on-error", True), ("if", "false")):
        mutated = copy.deepcopy(workflow)
        for step in _probe_steps(mutated):
            step[key] = value
        assert probe_wiring(mutated) != [], key
    mutated = copy.deepcopy(workflow)
    for step in _probe_steps(mutated):
        step["run"] += " || true"
    assert probe_wiring(mutated) != []


def test_control_a_job_that_cannot_fail_is_unwired(workflow: dict) -> None:
    for key, value in (("continue-on-error", True), ("if", "false")):
        mutated = copy.deepcopy(workflow)
        for job in mutated["jobs"].values():
            if any(START in run for run in _step_runs(job)):
                job[key] = value
        assert probe_wiring(mutated) != [], key


def test_a_selftest_in_its_own_earlier_step_is_wired(workflow: dict) -> None:
    """The wiring is the order and the live call, not the shape of one `run` string."""
    mutated = copy.deepcopy(workflow)
    for job in mutated["jobs"].values():
        steps = job.get("steps", [])
        for i, step in enumerate(steps):
            if PROBE in str(step.get("run", "")):
                live = f"PYTHONPATH=.ci python3 -m {PROBE}"
                selftest = {"name": "selftest", "run": f"{live} --selftest"}
                steps[i : i + 1] = [selftest, {**step, "run": live}]
                break
    assert probe_wiring(mutated) == []

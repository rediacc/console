"""PLAN-backup-program A4d: the elite job runs the S3 conformance probe, and a non-conformant store turns it red.

Two things are held here, because either can rot alone:

1. The probe's own controls. `selftest` starts a conformant stub that must pass every probe and a stub that ignores
   `If-None-Match` that must fail `create-only-conflict`. A probe that cannot fail would make the wiring below worthless.
2. The wiring. The job that starts elite in `.github/workflows/ci.yml` must run `rediacc_ci.infra.elite_s3_probe`
   (selftest first, then live) after `rediacc_ci.infra.ci_start_elite`, in that same job. A copy of the workflow with the
   probe step removed, or moved before the start, must be judged unwired, so the check cannot pass on any workflow.

The live run against RustFS needs the CI job's container, so it is not run here: it runs in that job, which this wiring pins.
"""

from __future__ import annotations

import copy
import pathlib

import pytest
import yaml

from rediacc_ci.infra import elite_s3_probe

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
START = "rediacc_ci.infra.ci_start_elite"
PROBE = "rediacc_ci.infra.elite_s3_probe"


def _step_runs(job: dict) -> list[str]:
    return [str(step.get("run", "")) for step in job.get("steps", [])]


def probe_wiring(workflow: dict) -> list[str]:
    """The jobs that start elite and do not run the probe after it (empty when every such job is wired)."""
    unwired = []
    starters = 0
    for name, job in workflow.get("jobs", {}).items():
        runs = _step_runs(job)
        starts = [i for i, run in enumerate(runs) if START in run]
        if not starts:
            continue
        starters += 1
        probes = [i for i, run in enumerate(runs) if PROBE in run]
        selftest_first = any(
            "--selftest" in runs[i] and runs[i].index("--selftest") < runs[i].rindex(PROBE)
            for i in probes
        )
        if not probes or min(probes) < starts[0] or not selftest_first:
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
        probe_step = next(s for s in steps if PROBE in str(s.get("run", "")))
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

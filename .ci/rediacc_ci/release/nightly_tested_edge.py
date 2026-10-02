"""Whether the green nightly that triggered `promote-stable.yml` actually tested the edge release it would promote.

Operator ruling 2026-09-30: a green scheduled `Console CI` run also releases edge to stable, alongside the 7-day soak. The nightly vouches only for the commit it ran on (`github.event.workflow_run.head_sha`), so the soak is waived only when the edge version's own tagged commit is that commit or one of its ancestors: `git merge-base --is-ancestor <edge commit> <head_sha>`.
An edge built from anything the nightly did not contain (a later push, a hotfix branch) is not vouched for.

"COULD NOT TELL" IS NEVER A YES. A tag that does not resolve, a malformed SHA, a SHA the checkout does not hold, or any git error returns `False` with the reason, and the caller falls back to the ordinary soak rule. The waiver exists only where the ancestry was positively proven. The checkout must hold full history and tags (`fetch-depth: 0`) for the proof to be possible at all.

A DRIFT-RED NIGHTLY STILL TESTED ITS COMMIT (PLAN-plan-per-pr-loop R1). The scheduled Console CI on main went red every night from 2026-09-07 on, mostly because upstream published something (an npm/OSV advisory, a newer dependency release), which says nothing about whether the tests passed on the commit. `nightly_failures_are_drift_only` reads the run's jobs and steps and accepts a `failure` run only when every failed
step is in `DRIFT_STEPS`, no job ended in anything but a pass or such a failure, and no test lane was skipped because of the drift failure. The drift gates keep failing the run, so the nightly-red issue still opens; they only stop vetoing the waiver.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from rediacc_ci.core import ghx

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$")

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]

# THE DRIFT SET: (job name, step name) pairs whose failure reports that UPSTREAM moved, not that the commit's tests failed. Chosen from the nightlies that actually failed (runs 36677534431, 36827121342, 36974916837: these two steps failed every night, beside genuine test failures).
DRIFT_STEPS: frozenset[tuple[str, str]] = frozenset(
    {
        # `npm audit` / OSV against advisories published AFTER the commit landed; the same commit goes red overnight with no change of its own.
        ("Quality / Security", "Audit"),
        # The dependency-freshness window: a new upstream release makes a pinned version "must upgrade" with no change to the commit.
        ("Quality / Content", "External dependency freshness"),
    }
)

# Jobs whose verdict is a function of the other jobs, each of which is judged here on its own: `CI Complete` fails whenever any job fails, and the `ci-verdict.yml` observers can appear in a run's job list after the fact (see `rediacc_ci.ci.budget_report.CRITICAL_PATH_EXCLUDE`).
DERIVED_JOBS: frozenset[str] = frozenset({"CI Complete", "CI Verdict", "Publish CI Verdict"})

# Test lanes ci.yml SKIPS when the Quality job fails (`package-tests`' `if:` requires `needs.quality.result` success or skipped), so a drift failure in Quality means they never ran. Skipped is not passed: while one of these is skipped the waiver refuses.
DRIFT_SKIPPED_TEST_LANES: frozenset[str] = frozenset({"Tests + Infra / Linux Packages"})

_PASSING_JOB = frozenset({"success", "skipped", "neutral"})
_PASSING_STEP = frozenset({"success", "skipped", "neutral", None})

ApiJson = Callable[..., object]


def _git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def edge_tested_by_nightly(version: str, head_sha: str, run: Runner = _git) -> tuple[bool, str]:
    """Return (proven, reason). `proven` is True only when the edge tag's commit is `head_sha` or an ancestor of it."""
    version = version.strip()
    head_sha = head_sha.strip().lower()
    if not VERSION_RE.match(version):
        return False, f"edge version {version!r} is not a release version"
    if not SHA_RE.match(head_sha):
        return False, f"nightly head_sha {head_sha!r} is not a full commit SHA"
    tag = version if version.startswith("v") else f"v{version}"

    resolved = run(["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"])
    edge_commit = resolved.stdout.strip()
    if resolved.returncode != 0 or not SHA_RE.match(edge_commit):
        return False, f"tag {tag} does not resolve to a commit in this checkout"

    present = run(["cat-file", "-e", f"{head_sha}^{{commit}}"])
    if present.returncode != 0:
        return False, f"nightly head {head_sha} is not in this checkout"

    ancestry = run(["merge-base", "--is-ancestor", edge_commit, head_sha])
    if ancestry.returncode == 0:
        return (
            True,
            f"edge {tag} ({edge_commit[:12]}) is contained in the green nightly head {head_sha[:12]}",
        )
    if ancestry.returncode == 1:
        return (
            False,
            f"edge {tag} ({edge_commit[:12]}) is NOT contained in the green nightly head {head_sha[:12]}",
        )
    return False, f"git merge-base failed (exit {ancestry.returncode}): {ancestry.stderr.strip()}"


def nightly_failures_are_drift_only(jobs: Sequence[Mapping[str, Any]]) -> tuple[bool, str]:
    """Return (accepted, reason) for a FAILED nightly's jobs: accepted only when its failures are all drift (`DRIFT_STEPS`).

    Judged at STEP level, because one job (Quality / Security) mixes drift steps with real checks. A cancelled or timed-out job or step is never a pass, a failed job with no failed step (a runner loss, a timeout) is never drift, and a run with no failed drift step at all is not this case.
    """
    if not jobs:
        return False, "the run's job list is empty"
    drift: list[str] = []
    for job in jobs:
        name = str(job.get("name", ""))
        if name in DERIVED_JOBS:
            continue
        status = job.get("status")
        conclusion = job.get("conclusion")
        if status != "completed":
            return False, f"job {name!r} is {status}, not completed"
        if conclusion == "skipped" and name in DRIFT_SKIPPED_TEST_LANES:
            return (
                False,
                f"test lane {name!r} was skipped (ci.yml skips it when Quality fails), so it never ran",
            )
        if conclusion in _PASSING_JOB:
            continue
        if conclusion != "failure":
            return False, f"job {name!r} concluded {conclusion}, which is not a pass"
        failed_steps = 0
        for step in job.get("steps") or []:
            step_name = str(step.get("name", ""))
            step_conclusion = step.get("conclusion")
            if step_conclusion in _PASSING_STEP:
                continue
            if step_conclusion != "failure":
                return (
                    False,
                    f"step {name!r} / {step_name!r} concluded {step_conclusion}, which is not a pass",
                )
            if (name, step_name) not in DRIFT_STEPS:
                return False, f"step {name!r} / {step_name!r} failed and is not a drift gate"
            failed_steps += 1
            drift.append(f"{name} / {step_name}")
        if failed_steps == 0:
            return (
                False,
                f"job {name!r} failed with no failed step, so the failure is not a drift gate's",
            )
    if not drift:
        return False, "the run failed without any failed drift step"
    return True, "the only failures are drift gates: " + ", ".join(drift)


def fetch_run_jobs(repo: str, run_id: str, api: ApiJson = ghx.api_json) -> list[dict[str, Any]]:
    """Every job (with its steps) of the latest attempt of `run_id`, across all pages. Raises `ghx.GhError` on a failed read."""
    pages = api(
        f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100",
        paginate=True,
        attempts=3,
    )
    jobs: list[dict[str, Any]] = []
    for page in pages if isinstance(pages, list) else []:
        if isinstance(page, dict) and isinstance(page.get("jobs"), list):
            jobs.extend(page["jobs"])
    return jobs

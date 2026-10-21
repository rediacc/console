"""Whether the green nightly that triggered `promote-stable.yml` actually tested the edge release it would promote.

Operator ruling 2026-09-30: a green scheduled `Console CI` run also releases edge to stable, alongside the 7-day soak. The nightly vouches only for the commit it ran on (`github.event.workflow_run.head_sha`), so the soak is waived only when the edge version's own tagged commit is that commit or one of its ancestors: `git merge-base --is-ancestor <edge commit> <head_sha>`.
An edge built from anything the nightly did not contain (a later push, a hotfix branch) is not vouched for.

"COULD NOT TELL" IS NEVER A YES. A tag that does not resolve, a malformed SHA, a SHA the checkout does not hold, or any git error returns `False` with the reason, and the caller falls back to the ordinary soak rule. The waiver exists only where the ancestry was positively proven. The checkout must hold full history and tags (`fetch-depth: 0`) for the proof to be possible at all.

A DRIFT-RED NIGHTLY STILL TESTED ITS COMMIT (PLAN-plan-per-pr-loop R1). The scheduled Console CI on main went red every night from 2026-09-07 on, mostly because upstream published something (an npm/OSV advisory, a newer dependency release), which says nothing about whether the tests passed on the commit. `nightly_failures_are_drift_only` reads the run's jobs and steps and accepts a `failure` run only when every failed
step is a drift step (`drift_steps()`), no job ended in anything but a pass or such a failure, and no test lane was skipped because of the drift failure. The drift gates keep failing the run, so the nightly-red issue still opens; they only stop vetoing the waiver.

THE DRIFT SET IS DERIVED, NOT LISTED, AND KEYED ON THE STEP NAME ALONE. Until 2026-10-21 it was a hand list of two (job, step) pairs, so the waiver never fired: nine more steps ask upstream (`ci_workflow_invariants.UPSTREAM_GATES`), and gate-bind moves a step between `Quality / Code (n)` shards, which re-keys a pair on the job name. Now it is every step of `UPSTREAM_GATES` plus the audit (`DRIFT_GATE_IDS`), mapped to its step name through `scripts/ci-runner/gates.lock.json`, plus the two steps split out of mixed ones for this purpose (`SPLIT_DRIFT_STEPS`: govulncheck out of `Run renet quality`, the OBS upstream check out of `Run the package matrix`). A lock that cannot be read, or a drift id it does not carry as a step, refuses the waiver: could not tell is never a yes. The tests hold the set equal to the workflows' own external steps, each name unique across `.github/workflows`, and every step after one guarded by `!cancelled()`, so a drift failure can never skip a real check into a "skipped" the waiver reads as a pass.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from rediacc_ci.core import gh_retry
from rediacc_ci.security.ci_workflow_invariants import UPSTREAM_GATES

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$")

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]

# THE DRIFT SET, by gate id: every gate that asks a host outside the repository (the single list `ci_workflow_invariants` holds fail-closed on every cadence), plus `npm audit`/OSV, whose advisories are published after the commit landed.
DRIFT_GATE_IDS: tuple[str, ...] = (*UPSTREAM_GATES, "check:ci-security-audit")

# Steps that exist only to separate drift from defects, each split out of a step that mixed the two (PLAN-plan-per-pr-loop R1 B). By name, because neither is reached through the lock: the first is a hand-registered gate, the second a test-job step. The tests pin both names to their workflows.
GOVULNCHECK_STEP = "Renet govulncheck"  # ci-quality.yml quality-go, out of `Run renet quality`
OBS_UPSTREAM_STEP = (
    "OBS upstream serves the pin"  # ct-tests.yml renet-pkg-matrix, out of `Run the package matrix`
)
SPLIT_DRIFT_STEPS: frozenset[str] = frozenset({GOVULNCHECK_STEP, OBS_UPSTREAM_STEP})

GATES_LOCK = (
    pathlib.Path(__file__).resolve().parents[3] / "scripts" / "ci-runner" / "gates.lock.json"
)

# Jobs whose verdict is a function of the other jobs, each of which is judged here on its own: `CI Complete` fails whenever any job fails, and the `ci-verdict.yml` observers can appear in a run's job list after the fact (see `rediacc_ci.ci.budget_report.CRITICAL_PATH_EXCLUDE`).
DERIVED_JOBS: frozenset[str] = frozenset({"CI Complete", "CI Verdict", "Publish CI Verdict"})

# Jobs derived from ONE sharded job: `Quality / Shard receipts` fails when a `Quality / Code (n)` shard reported anything but success (run 39551246836). Skipped only when such a shard really failed, since the same job also fails when a shard never reported at all, which is a wiring defect and never drift.
SHARD_DERIVED_JOBS: Mapping[str, str] = {"Quality / Shard receipts": "Quality / Code ("}

# Test lanes that must have RUN on a scheduled nightly. ci.yml's `package-tests` used to skip whenever Quality failed, so a drift-only red never tested the Linux packages; it now runs on `schedule` regardless of Quality's result. A skip here therefore means the lane did not run for some other reason, and skipped is not passed: the waiver refuses.
MUST_RUN_TEST_LANES: frozenset[str] = frozenset({"Tests + Infra / Linux Packages"})

# One page of a run's jobs. 100 made GitHub time out (502/504 at ~55 s) on a re-run 205-job run, which refused promote run 119123448102; 30 answered in ~4 s. `--paginate` still reads every page.
JOBS_PER_PAGE = 30


class DriftSetError(Exception):
    """The drift set could not be derived, so no failed step can be shown to be drift."""


def drift_steps(lock_path: pathlib.Path = GATES_LOCK) -> frozenset[str]:
    """Every step name whose failure says upstream moved: the lock's step for each `DRIFT_GATE_IDS` id, plus `SPLIT_DRIFT_STEPS`. Raises DriftSetError when the lock cannot be read or does not carry one of the ids as a CI step."""
    try:
        entries = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DriftSetError(f"{lock_path} cannot be read: {exc}") from exc
    steps: dict[str, str] = {}
    for entry in entries if isinstance(entries, list) else []:
        ci = entry.get("ci") if isinstance(entry, dict) else None
        if isinstance(ci, dict) and ci.get("kind") == "step" and isinstance(ci.get("step"), str):
            steps[str(entry.get("id"))] = ci["step"]
    missing = [gate for gate in DRIFT_GATE_IDS if gate not in steps]
    if missing:
        raise DriftSetError(
            f"{lock_path} carries no CI step for drift gate(s) {', '.join(missing)}"
        )
    return frozenset(steps[gate] for gate in DRIFT_GATE_IDS) | SPLIT_DRIFT_STEPS


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


def nightly_failures_are_drift_only(
    jobs: Sequence[Mapping[str, Any]], drift: frozenset[str] | None = None
) -> tuple[bool, str]:
    """Return (accepted, reason) for a FAILED nightly's jobs: accepted only when its failures are all drift steps (`drift_steps()` unless `drift` is given).

    Judged at STEP level and by step NAME, because one job mixes drift steps with real checks (Quality / Security) and gate-bind moves a step between shards of one lane. A cancelled or timed-out job or step is never a pass, a failed job with no failed step (a runner loss, a timeout) is never drift, and a run with no failed drift step at all is not this case.
    """
    if not jobs:
        return False, "the run's job list is empty"
    if drift is None:
        try:
            drift = drift_steps()
        except DriftSetError as exc:
            return (
                False,
                f"the drift set could not be derived, so no failure can be shown to be drift: {exc}",
            )
    failed_jobs = {
        str(job.get("name", "")) for job in jobs if job.get("conclusion") not in _PASSING_JOB
    }
    found: list[str] = []
    for job in jobs:
        name = str(job.get("name", ""))
        if name in DERIVED_JOBS:
            continue
        status = job.get("status")
        conclusion = job.get("conclusion")
        if status != "completed":
            return False, f"job {name!r} is {status}, not completed"
        if conclusion == "skipped" and name in MUST_RUN_TEST_LANES:
            return (
                False,
                f"test lane {name!r} was skipped on a scheduled nightly, so it never ran",
            )
        if conclusion in _PASSING_JOB:
            continue
        if conclusion != "failure":
            return False, f"job {name!r} concluded {conclusion}, which is not a pass"
        source = SHARD_DERIVED_JOBS.get(name)
        if source is not None:
            if any(other.startswith(source) for other in failed_jobs):
                continue
            unreported = (
                f"job {name!r} failed while no {source}...) shard did, so a shard did not report"
            )
            return False, unreported + ": a wiring defect, not drift"
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
            if step_name not in drift:
                return False, f"step {name!r} / {step_name!r} failed and is not a drift gate"
            failed_steps += 1
            found.append(f"{name} / {step_name}")
        if failed_steps == 0:
            return (
                False,
                f"job {name!r} failed with no failed step, so the failure is not a drift gate's",
            )
    if not found:
        return False, "the run failed without any failed drift step"
    return True, "the only failures are drift gates: " + ", ".join(found)


def _api_json(
    path: str,
    *,
    paginate: bool = False,
    attempts: int = gh_retry.ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
) -> object:
    """`gh api <path>` (paged into one list of pages with `paginate`), retried on a 5xx or connection fault only; 4xx raises at once."""
    args = ["api", path]
    if paginate:
        args += ["--paginate", "--slurp"]
    return gh_retry.gh(args, attempts=attempts, sleep=sleep).json()


def fetch_run_jobs(repo: str, run_id: str, api: ApiJson = _api_json) -> list[dict[str, Any]]:
    """Every job (with its steps) of the latest attempt of `run_id`, across all pages. Raises `ghx.GhError` on a failed read, after the transient retries."""
    pages = api(
        f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page={JOBS_PER_PAGE}",
        paginate=True,
        attempts=3,
    )
    jobs: list[dict[str, Any]] = []
    for page in pages if isinstance(pages, list) else []:
        if isinstance(page, dict) and isinstance(page.get("jobs"), list):
            jobs.extend(page["jobs"])
    return jobs

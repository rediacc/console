#!/usr/bin/env python3
"""CI time budget report (operator spec W, `agent/plans/PLAN-ci-time-budget.md` T1.1): "every CI job finishes in 15 minutes or less, and the whole pipeline in 20 minutes or less."

Read-only against the Actions API, run as `PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report` (a package.json key would grow check:ci-package-key-budget's shrink-only set). No twin: this is P1's measurement instrument, not a port of an existing script, so there is nothing to be differential against.

WHAT IT PRODUCES, per run class (`pr-full`, `main-push`, `schedule`):
  - per-job median / p90 / max wall time (successful jobs only, matching how
    section 1 of the plan was measured);
  - queue-time median / p90 / max (`started_at - created_at`, per job);
  - runner-minutes and peak concurrency, across every job regardless of
    conclusion -- a failed job still bills runner time and still occupies a
    concurrency slot;
  - a best-effort CRITICAL PATH for one representative run of the class,
    walked backward over the REAL `needs:` graph of `ci.yml` plus whichever
    reusable workflow each job `uses:`, aliased "caller name / callee name"
    the same way `check_job_timeout_headroom.py`'s `refresh()` aliases a job
    the API reports through a reusable call (see `build_display_graph`).

The plan's own acceptance for this box is "within +/-10% of section 1", which is a claim about a LIVE run against the real repo, not something this module can pin with a fixture -- the network IS the subject. What is pinned here is the arithmetic (median/p90/max, the sweep-line concurrency count, the backward-walk critical path), each in its own small pure function so a future gate can drive them without a network call, the same shape `check_job_timeout_headroom.py` splits `verdicts()` from `refresh()` for.

WHY REGEX AND NOT `yaml.safe_load` FOR THE NEEDS GRAPH, the same choice `check_job_timeout_headroom.job_timeouts` already made and says why: the shape read is two fixed indentation levels, and it keeps this module free of a PyYAML dependency `.ci/scripts/quality/check-python-lint.sh` would then have to provision everywhere this runs. `build_display_graph` is best-effort on purpose -- a workflow reformatted onto different indentation yields a thinner graph, not a crash, because this is a REPORT and a critical path with holes in it still beats no report at all.

WHY `ghx` AND NOT A HAND-ROLLED `gh api` CALL: `ghx.api_json` is this repo's typed answer to the 28-site trap the module's own header documents -- a failed call surfacing as an EMPTY answer rather than as a raised error. A budget report that read "0 runs" from a rate-limited token would print a misleadingly small table instead of refusing one.

USAGE:
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report [--repo OWNER/NAME]
        [--workflow ci.yml] [--branch main] [--limit 15] [--status success]
        [--json-out PATH] [--markdown-out PATH]

Markdown goes to stdout (or `--markdown-out`), then the full JSON report to stdout (or `--json-out`) -- both printed by default so a plain invocation is still useful piped straight into a PR comment or a file.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from rediacc_ci import log, paths
from rediacc_ci.core import ghx

DEFAULT_REPO = "rediacc/console"
DEFAULT_WORKFLOW = "ci.yml"
DEFAULT_BRANCH = "main"
DEFAULT_LIMIT = 15
DEFAULT_STATUS = "success"

# One entry per run class this report covers (plan section 1's four samples collapse to three LIVE classes: sample A is main-push, B/B1 is pr-full, and the schedule runs inside B become their own class here rather than being folded into pr-full, since D-W5 treats the nightly as a separate ceiling).
RUN_CLASS_EVENTS = {"pr-full": "pull_request", "main-push": "push", "schedule": "schedule"}
RUN_CLASSES = tuple(RUN_CLASS_EVENTS)

# Timestamps and arithmetic -- pure, no network, unit-testable in isolation.


def _iso_to_epoch(value: str | None) -> float | None:
    """An Actions API timestamp ("2026-09-24T10:00:00Z") to a Unix epoch second."""
    if not value:
        return None
    return datetime.fromisoformat(value).timestamp()


def job_wall_minutes(job: dict[str, Any]) -> float | None:
    """`completed_at - started_at`, successful jobs only (plan section 1a's basis)."""
    if job.get("conclusion") != "success":
        return None
    start = _iso_to_epoch(job.get("started_at"))
    end = _iso_to_epoch(job.get("completed_at"))
    if start is None or end is None:
        return None
    return (end - start) / 60.0


def job_queue_minutes(job: dict[str, Any]) -> float | None:
    """`started_at - created_at`, successful jobs only, same basis as wall time."""
    if job.get("conclusion") != "success":
        return None
    created = _iso_to_epoch(job.get("created_at"))
    start = _iso_to_epoch(job.get("started_at"))
    if created is None or start is None:
        return None
    return max(0.0, (start - created) / 60.0)


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (numpy's default method) over a sorted copy."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def stats(values: Sequence[float | None]) -> dict[str, float] | None:
    """median / p90 / max / n, or None for an empty sample -- never a zero that reads as measured."""
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return {
        "median": round(statistics.median(clean), 1),
        "p90": round(_percentile(clean, 90), 1),
        "max": round(max(clean), 1),
        "n": len(clean),
    }


def _ran(job: dict[str, Any]) -> bool:
    """Did this job actually occupy a runner, ever?

    A `skipped` job never runs at all -- its `if:` was false -- and GitHub's own timestamps for one are not measurements: MEASURED live on run 35098378649, "Tests + Infra / Renet" (skipped) reports `started_at` 13:35:06 and `completed_at` 13:02:53, i.e. it STARTED AFTER IT FINISHED, by over 32 minutes. Every skipped job in that run showed the same inversion, and feeding these into a sum or a concurrency sweep produced a runner-minutes total of -956.8 for a real run -- caught by running this module against the live API rather than trusting the arithmetic on inspection alone. `cancelled` is kept: a job that started and was then cancelled genuinely occupied a runner for real time.
    """
    return job.get("conclusion") != "skipped"


def runner_minutes(jobs: list[dict[str, Any]]) -> float:
    """Sum of every job's wall time, whatever its conclusion, EXCEPT skipped (see `_ran`)."""
    total = 0.0
    for job in jobs:
        if not _ran(job):
            continue
        start = _iso_to_epoch(job.get("started_at"))
        end = _iso_to_epoch(job.get("completed_at"))
        if start is not None and end is not None:
            total += (end - start) / 60.0
    return total


def peak_concurrency(jobs: list[dict[str, Any]]) -> int:
    """The most jobs ever running at once, by a sweep over (started_at, completed_at).

    Ends are ordered BEFORE starts at an identical timestamp, so a job ending exactly when the next begins is not counted as an overlap -- the natural reading of "at once", and the one that matches how a runner slot actually frees up. Skipped jobs are excluded; see `_ran`.
    """
    events: list[tuple[float, int]] = []
    for job in jobs:
        if not _ran(job):
            continue
        start = _iso_to_epoch(job.get("started_at"))
        end = _iso_to_epoch(job.get("completed_at"))
        if start is None or end is None:
            continue
        events.append((start, 1))
        events.append((end, -1))
    events.sort()
    running = 0
    peak = 0
    for _, delta in events:
        running += delta
        peak = max(peak, running)
    return peak


# The Actions API, through ghx (TRAP 1/2/3-safe: a failed call raises).


def fetch_runs(
    repo: str, workflow: str, event: str, branch: str | None, status: str, limit: int
) -> list[dict[str, Any]]:
    """The last `limit` runs of `event`, newest first (the API's own default order)."""
    query = "event=%s&status=%s&per_page=%d" % (event, status, min(limit, 100))
    if branch:
        query += "&branch=%s" % branch
    data = ghx.api_json("repos/%s/actions/workflows/%s/runs?%s" % (repo, workflow, query))
    if not isinstance(data, dict):
        raise ghx.GhBadOutputError(
            [], 0, "expected a JSON object from the workflow-runs endpoint", ghx.FAILURE_FAILED
        )
    runs = data.get("workflow_runs")
    return list(runs)[:limit] if isinstance(runs, list) else []


def fetch_jobs(repo: str, run_id: int) -> list[dict[str, Any]]:
    """Every job of one run.

    Capped at 100 (one page): every measured run in the plan's own section 1c tops out at 80 jobs, so a second page is not expected in practice, and this is a report rather than a gate that must prove completeness.
    """
    data = ghx.api_json("repos/%s/actions/runs/%s/jobs?per_page=100" % (repo, run_id))
    if not isinstance(data, dict):
        return []
    jobs = data.get("jobs")
    return list(jobs) if isinstance(jobs, list) else []


# The needs graph, aliased the way check_job_timeout_headroom.refresh() is.

_JOB_HEADER_RE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
_FIELD_NAME_RE = re.compile(r"^    name:\s*(.+?)\s*$")
_FIELD_USES_RE = re.compile(r"^    uses:\s*(\./\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml)")
_FIELD_NEEDS_INLINE_RE = re.compile(r"^    needs:\s*\[(.*)\]\s*$")
_FIELD_NEEDS_SCALAR_RE = re.compile(r"^    needs:\s*([A-Za-z0-9_.-]+)\s*$")
_NEEDS_ITEM_RE = re.compile(r"^      - ([A-Za-z0-9_.-]+)\s*$")


def parse_workflow_jobs(text: str) -> dict[str, dict[str, Any]]:
    """`{job_id: {"name", "needs": [job_id...], "uses"}}` for one workflow file's TOP-LEVEL `jobs:` mapping.

    Regex, not `yaml.safe_load` -- see the module docstring. Best-effort: a line shape this does not recognise is simply skipped, which thins the graph rather than raising, because a partial critical path is still more informative than none for a REPORT.
    """
    jobs: dict[str, dict[str, Any]] = {}
    current: str | None = None
    in_jobs_block = False
    collecting_needs_list = False
    for line in text.splitlines():
        if line == "jobs:":
            in_jobs_block = True
            continue
        if not in_jobs_block:
            continue
        if line and not line.startswith(" "):
            break  # left the top-level `jobs:` mapping entirely
        header = _JOB_HEADER_RE.match(line)
        if header:
            current = header.group(1)
            jobs[current] = {"name": current, "needs": [], "uses": None}
            collecting_needs_list = False
            continue
        if current is None:
            continue
        if collecting_needs_list:
            item = _NEEDS_ITEM_RE.match(line)
            if item:
                jobs[current]["needs"].append(item.group(1))
                continue
            collecting_needs_list = False
        name_m = _FIELD_NAME_RE.match(line)
        if name_m:
            jobs[current]["name"] = name_m.group(1).strip("\"'")
            continue
        uses_m = _FIELD_USES_RE.match(line)
        if uses_m:
            jobs[current]["uses"] = uses_m.group(1)
            continue
        inline_m = _FIELD_NEEDS_INLINE_RE.match(line)
        if inline_m:
            jobs[current]["needs"] = [
                item.strip().strip("\"'") for item in inline_m.group(1).split(",") if item.strip()
            ]
            continue
        scalar_m = _FIELD_NEEDS_SCALAR_RE.match(line)
        if scalar_m:
            jobs[current]["needs"] = [scalar_m.group(1)]
            continue
        if line.strip() == "needs:":
            collecting_needs_list = True
    return jobs


def build_display_graph(root: Path, workflow: str = DEFAULT_WORKFLOW) -> dict[str, set[str]]:
    """`{display_name: {needed display_name, ...}}` across `workflow` plus every reusable callee it `uses:`.

    ALIASING. A job called through a reusable workflow is reported by the API as "<caller job's name> / <called job's name>" -- the same fact `check_job_timeout_headroom.refresh()` records at its own aliasing call site. A root job inside the called file (nothing in ITS OWN `needs:`) also inherits whatever the caller job itself needed, so the graph stays connected across the reusable-workflow boundary rather than stopping at it.
    """
    ci_path = root / ".github" / "workflows" / workflow
    ci_jobs = parse_workflow_jobs(ci_path.read_text(encoding="utf-8"))
    display_of = {job_id: rec["name"] for job_id, rec in ci_jobs.items()}

    graph: dict[str, set[str]] = {}
    for rec in ci_jobs.values():
        caller_display = rec["name"]
        needs_displays = {display_of.get(n, n) for n in rec["needs"]}
        callee = rec["uses"]
        callee_path = root / callee.removeprefix("./") if callee else None
        if callee_path is not None and callee_path.is_file():
            callee_jobs = parse_workflow_jobs(callee_path.read_text(encoding="utf-8"))
            sub_display_of = {cid: crec["name"] for cid, crec in callee_jobs.items()}
            for crec in callee_jobs.values():
                node = "%s / %s" % (caller_display, crec["name"])
                sub_needs = {
                    "%s / %s" % (caller_display, sub_display_of.get(n, n)) for n in crec["needs"]
                }
                graph.setdefault(node, set()).update(sub_needs or needs_displays)
            continue
        graph.setdefault(caller_display, set()).update(needs_displays)
    return graph


def _alias_set(name: str) -> set[str]:
    """{full name, first segment, last segment} -- check_job_timeout_headroom's own alias set."""
    parts = name.split(" / ")
    return {name, parts[0], parts[-1]}


# `Review Complete` is not a job of `ci.yml` at all -- it is posted by the SEPARATE `review-status.yml` workflow (watchdog-monitor.yml:140 documents the same fact for the watchdog's own exclusion) -- yet `actions/runs/{id}/jobs` returns it alongside ci.yml's own jobs, timestamped by whenever the human review actually finished, hours after the pipeline itself. MEASURED live: run 35128695736 reports `Review Complete` completing at 2026-09-17T07:11:28Z against a run created 2026-09-16T17:31:16Z, 13+ hours later, which critical_path's plain "latest completed_at wins" sink rule mistook for the run's true finish line before this exclusion existed. `CI Complete` is NOT excluded here: unlike `Review Complete` it is a genuine ci.yml job and the plan's own section 1b ends its sample critical path there.
CRITICAL_PATH_EXCLUDE = ("Review Complete",)


def critical_path(graph: dict[str, set[str]], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One run's critical path: walk `graph` backward from its last-finishing job.

    At each step, follow whichever `needs` predecessor finished LATEST -- the one that actually gated the current job's start, which is the definition of a critical path. Best-effort: a job the graph does not mention, or a run whose job list does not match any node, simply ends the walk there instead of raising -- this is a report, not a gate, and a partial path is still evidence.
    """
    by_alias: dict[str, dict[str, Any]] = {}
    for job in jobs:
        name = job.get("name", "")
        if name in CRITICAL_PATH_EXCLUDE:
            continue
        start = _iso_to_epoch(job.get("started_at"))
        end = _iso_to_epoch(job.get("completed_at"))
        if start is None or end is None:
            continue
        for alias in _alias_set(name):
            existing = by_alias.get(alias)
            if existing is None or end > existing["end"]:
                by_alias[alias] = {"name": job["name"], "start": start, "end": end}

    if not by_alias:
        return []
    origin = min(rec["start"] for rec in by_alias.values())
    sink = max(by_alias.values(), key=lambda rec: rec["end"])["name"]

    path: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: str | None = sink
    while current is not None and current not in seen:
        seen.add(current)
        rec = by_alias.get(current)
        if rec is None:
            break
        path.append(
            {
                "name": rec["name"],
                "start_min": round((rec["start"] - origin) / 60, 1),
                "end_min": round((rec["end"] - origin) / 60, 1),
            }
        )
        needs = graph.get(current) or graph.get(rec["name"]) or set()
        candidates = [(n, by_alias[n]["end"]) for n in needs if n in by_alias]
        current = max(candidates, key=lambda c: c[1])[0] if candidates else None
    path.reverse()
    return path


# Assembling the report.


def collect_class(
    repo: str, workflow: str, event: str, branch: str | None, status: str, limit: int
) -> dict[str, Any]:
    """One run class's full measurement: per-job stats, queue, runner-minutes, peak concurrency."""
    runs = fetch_runs(repo, workflow, event, branch, status, limit)
    per_job: dict[str, list[float]] = {}
    queue_values: list[float] = []
    runner_values: list[float] = []
    peak_values: list[int] = []
    representative_jobs: list[dict[str, Any]] = []
    for index, run in enumerate(runs):
        jobs = fetch_jobs(repo, run["id"])
        if index == 0:
            representative_jobs = jobs
        for job in jobs:
            name = job.get("name") or "?"
            wall = job_wall_minutes(job)
            if wall is not None:
                per_job.setdefault(name, []).append(wall)
            queue = job_queue_minutes(job)
            if queue is not None:
                queue_values.append(queue)
        runner_values.append(runner_minutes(jobs))
        peak_values.append(peak_concurrency(jobs))
    return {
        "runs_sampled": len(runs),
        "jobs": {name: stats(vals) for name, vals in per_job.items()},
        "queue": stats(queue_values),
        "runner_minutes": stats(runner_values),
        "peak_concurrency": max(peak_values) if peak_values else None,
        "representative_jobs": representative_jobs,
    }


def build_report(
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    branch: str = DEFAULT_BRANCH,
    limit: int = DEFAULT_LIMIT,
    status: str = DEFAULT_STATUS,
) -> dict[str, Any]:
    graph: dict[str, set[str]] = {}
    try:
        graph = build_display_graph(paths.repo_root(), workflow)
    except OSError as exc:
        log.warn("could not build the needs graph (critical path will be empty): %s" % exc)

    report: dict[str, Any] = {"repo": repo, "workflow": workflow, "branch": branch, "classes": {}}
    for run_class, event in RUN_CLASS_EVENTS.items():
        branch_filter = branch if run_class == "main-push" else None
        data = collect_class(repo, workflow, event, branch_filter, status, limit)
        jobs = data.pop("representative_jobs")
        data["critical_path"] = critical_path(graph, jobs) if jobs else []
        report["classes"][run_class] = data
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# CI time budget report",
        "",
        "`%s` / `%s` (branch `%s`)" % (report["repo"], report["workflow"], report["branch"]),
        "",
    ]
    for run_class in RUN_CLASSES:
        data = report["classes"].get(run_class)
        if not data:
            continue
        lines.append("## %s (%d run(s) sampled)" % (run_class, data["runs_sampled"]))
        lines.append("")
        if data["jobs"]:
            lines.append("| Job | median | p90 | max | n |")
            lines.append("| --- | --- | --- | --- | --- |")
            ranked = sorted(
                data["jobs"].items(), key=lambda kv: kv[1]["max"] if kv[1] else 0, reverse=True
            )
            for name, s in ranked:
                if s is None:
                    continue
                lines.append(
                    "| %s | %.1f | %.1f | %.1f | %d |"
                    % (name, s["median"], s["p90"], s["max"], s["n"])
                )
            lines.append("")
        if data["queue"]:
            lines.append(
                "Queue: median %.1fm, p90 %.1fm, max %.1fm"
                % (data["queue"]["median"], data["queue"]["p90"], data["queue"]["max"])
            )
        if data["runner_minutes"]:
            lines.append(
                "Runner-minutes: median %.1f, max %.1f"
                % (data["runner_minutes"]["median"], data["runner_minutes"]["max"])
            )
        if data["peak_concurrency"] is not None:
            lines.append("Peak concurrency: %d" % data["peak_concurrency"])
        if data["critical_path"]:
            lines.append("")
            lines.append("Critical path (one representative run):")
            lines.extend(
                "  1. `%s` %.1f -> %.1f" % (step["name"], step["start_min"], step["end_min"])
                for step in data["critical_path"]
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="budget_report",
        description=(
            "Read-only CI time budget report (operator spec W, T1.1): per-job "
            "median/p90/max, queue time, runner-minutes, peak concurrency and a "
            "best-effort critical path, per run class."
        ),
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="green runs sampled per class"
    )
    parser.add_argument("--status", default=DEFAULT_STATUS)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        report = build_report(args.repo, args.workflow, args.branch, args.limit, args.status)
    except ghx.GhError as exc:
        print("budget_report: %s" % exc, file=sys.stderr)
        return 1

    markdown = render_markdown(report)
    if args.markdown_out:
        args.markdown_out.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        args.json_out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

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
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report --refresh [--dry-run]
        [--refresh-limit 10]
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report --check [--refresh-limit 10]

Markdown goes to stdout (or `--markdown-out`), then the full JSON report to stdout (or `--json-out`) -- both printed by default so a plain invocation is still useful piped straight into a PR comment or a file.

------------------------------------------------------------------------------
T3.2/T3.3/T3.4 (PLAN-ci-time-budget spec W): `.ci/config/lane-durations.json`'s SCHEMA.
------------------------------------------------------------------------------
`--refresh` is the ONLY writer of this file; `--check` reads it read-only and never writes. Both are read here so the schema is defined ONCE, next to the code that actually produces it, rather than duplicated into a comment that can drift from the real shape -- the same reason `check_job_timeout_headroom.job_timeouts` keeps its parsing rules in one function rather than restating them in a docstring a reader could trust instead of the code.

    {
      "$comment": [...],                    # free-form, preserved across --refresh
      "refreshed_at": "2026-09-27T00:00:00Z" | null,   # stamped by budget_report --refresh
      "concurrency": 20,                    # operator ruling D-W1; --refresh never touches it
      "jobs": {"<lane id>": <fixed-cost p90, MINUTES>},
      "units": {"<unit id>": <p90, MILLISECONDS>},
      "defaultUnitMs": {"<lane id>": <ms>},  # optional, hand-authored, --refresh preserves it
      "unitParallelism": {"<lane id>": <workers>},  # optional, hand-authored, --refresh preserves it
      "job_p90_minutes": {"<job DISPLAY name>": <p90, MINUTES>},  # T3.1; see below
      "job_max_seconds": {
        "refreshed_at": "..." | null,        # OWN timestamp -- see WHY TWO refreshed_at BELOW
        "jobs": {"<job display name>": {"observed_max_seconds": <int>, "samples": <int>}}
      }
    }

`jobs` and `units` (plus `concurrency` and `defaultUnitMs`) are `scripts/gates/check-lane-budget.ts`'s `LaneDurations` interface EXACTLY -- that file is the consumer, already written and NOT owned by this box, so its existing `Record<string, number>` shapes are the contract this module writes TO rather than a schema invented here. A "lane id" is a job's YAML KEY (`quality-code`, `test-e2e-workers`, ...), the same string `scripts/ci-runner/lanes.ts`'s `laneCapabilities`/`TEST_LANE_WORKFLOWS` and `gates.lock.json`'s `ci.job` use -- NOT the Actions API's own job display name (`"Quality / Code (1)"`). `lane_display_patterns` below is what bridges the two.

`job_p90_minutes` is T3.1's own addition, for check 2's 63 unpriced non-lane jobs (the gate's own `LaneDurations.job_p90_minutes` field exists and says "nothing writes it yet"). Keyed by Actions API DISPLAY NAME, not a lane id: unlike `jobs`/`units`, most of these jobs have no YAML-key alias to look one up by without re-walking `ci.yml`'s own `needs:`/`uses:` graph a second time. The CONSUMER maps names back to job ids: `check-lane-budget.ts`'s `displayNamePattern` walks `ci.yml` and its callees per call site and matches these keys, judging a priced lane's matrix legs in their lane and every other job in check 2. `--refresh` writes it from success-only wall-time samples over the SAME PR-full runs `jobs`/`units` already sample.
A "unit id" is keyed exactly as `scripts/ci-runner/unit-enumerators.ts`'s `LANE_ENUMERATORS` name it (`e2e-workers:<file>`, `account-e2e:<file>`, a bare Go import path, `renet-integration:<file>`, `pytest:<file>`, `battery:<name>`, `tutorial:<slug>`) -- read-only there too.

WHY `units` STAYS SCOPED TO THE SEVEN T2.7/T2.8 TEST LANES, NOT `quality-code`'s OWN CHECK IDS. T1.6, whose artifacts feed `units` here, names exactly five sources -- Playwright JSON, pytest junit, gotestsum junit, the battery's own per-test timings, and an OPS tutorial JSON summary -- and every one of them is a TEST-RUNNER'S OWN report. `quality-code` has no such report: its "units" are individual `npm run check:*` invocations, each its OWN named workflow step, and T2.9's existing control
("`shardPlan(durations: {})` is byte-identical to `shardPlan()` with no durations
argument") is what keeps that lane's shard plan stable on exactly that absence. Giving `quality-code` per-check-id costs is a DIFFERENT instrument (the steps API, not a test report) that no box here asks for; `--refresh` never populates it, and that is not a gap in this box, it is the box's stated scope.

WHY TWO `refreshed_at` FIELDS, NOT ONE (D-W2/T3.4). `job_max_seconds` retires `.ci/scripts/quality/job-timeout-baseline.json` into this file, and `check_job_timeout_headroom.py` keeps its OWN independent `--refresh` (`npm run check:ci-timeout-headroom -- --refresh`), sampling MAIN PUSH runs for exactly the two jobs the lane-budget gate does not cover (`Validate Promotion`, `Stage Artifacts` -- direct `ci.yml` jobs, never lane-sharded).
If that refresh stamped the file's TOP-LEVEL `refreshed_at`, it would silently tell `check-lane-budget.ts`'s check 5 that `jobs`/`units` were just re-measured when only `job_max_seconds` was, and the reverse: a `budget_report --refresh` that never touches `Validate Promotion`/`Stage Artifacts` would silently un-stale a headroom baseline nothing re-measured. One shared timestamp for two independently-refreshed halves is exactly the kind of "missing counts as infinitely stale" trap `check_job_timeout_headroom.py` already refuses for a baseline nobody refreshed -- so each half keeps its own.

THE UNIT-DURATION ARTIFACT CONTRACT (T1.6's producer side, defined HERE because this is the first and only consumer while T1.6 itself has not landed). Named `unit-durations-<lane>-...-<sha>` (matched here by the `unit-durations-<lane>-` PREFIX alone -- a lane id itself contains hyphens, so decomposing the rest of the name would be ambiguous; the prefix match is unambiguous because `LANE_IDS` is a closed, known set). One artifact holds ONE member file, matched by extension:

  - `test-e2e-workers`, `test-account-e2e`: a `*.json` member, Playwright's own
    `--reporter=json` shape (`suites[].specs[].file` + `specs[].tests[].results[].duration`,
    ms, summed per file -- matching `e2eWorkersUnits`/`accountE2eUnits`'s file-level units).
  - `test-renet-integration`, `quality-pytest`: a `*.xml` member, pytest's own
    `--junitxml` shape (`<testcase classname=... file=... time=...>`, `time` in SECONDS).
  - `test-renet-go`: a `*.xml` member, `gotestsum --junitfile`'s shape (`<testcase
    classname=<go import path> time=...>`, seconds) -- keyed by the BARE package path,
    matching `renetGoUnits`.
  - `quality-gate-tests`: a `*.json` member shaped `{"drivers": [{"name": str,
    "duration_ms": number}, ...]}`, one entry per `battery.py --list` driver.
  - `ops-tutorials`: a `*.json` member shaped `{"tutorials": [{"slug": str,
    "duration_ms": number}, ...]}`, one entry per tutorial.

A lane with zero matching artifacts across every sampled run is REPORTED (a warning naming the lane, plus `--refresh`'s own printed summary), never silently absent from that report -- the exact anti-vacuity failure mode `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py` exists to catch elsewhere in this tree.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

from rediacc_ci import log, paths
from rediacc_ci.core import ghx

DEFAULT_REPO = "rediacc/console"
DEFAULT_WORKFLOW = "ci.yml"
DEFAULT_BRANCH = "main"
DEFAULT_LIMIT = 15
DEFAULT_STATUS = "success"
# THE PR SAMPLE FOR --refresh/--check IS COMPLETED RUNS, NOT SUCCESSFUL ONES (operator default #32e66d3b, 2026-09-27). check:ci-plan-implementation reds every PR run until spec W's last box closes (zero threshold, 2026-09-26 ruling) and main pushes skip the full suite, so a run-level `success` filter left NO qualifying run and W could never close its own budget boxes. Durations stay clean because every job sample below is success-only; a red Quality / Branch does not change how long a green test leg took. Unit artifacts are uploaded always(), so a failed leg's per-test times can enter the unit p90.
REFRESH_PR_STATUS = "completed"
# T3.2: how many completed PR-full runs `--refresh`/`--check` sample (see REFRESH_PR_STATUS). Separate from DEFAULT_LIMIT (15, the read-only report's own default) because the plan's box names 10 explicitly, and the two commands have different costs -- --refresh/--check also list and download artifacts per run, which --limit 15's report path never does.
DEFAULT_REFRESH_LIMIT = 10

# EVERY READ HERE RETRIES, because one report makes dozens of calls and a single transient failure used to abort all of them: on 2026-09-27 a `--refresh --dry-run` died on `stream error: stream ID 1; CANCEL; received from peer` for one run's jobs, and the identical rerun succeeded. `ghx.gh` defaults to one attempt on purpose (an auth failure should not cost backoff); a report over many runs is the caller that wants three.
GH_ATTEMPTS = 3
LANE_DURATIONS_REL_PATH = ".ci/config/lane-durations.json"
PER_LEG_BUDGET_MINUTES = 12.0
DRIFT_THRESHOLD = 0.25
# D-W2/T3.4: the two direct (non-lane-sharded) ci.yml jobs job-timeout-baseline.json used to cover, now `job_max_seconds`' own baseline. See check_job_timeout_headroom.py.
HEADROOM_JOBS = ("Validate Promotion", "Stage Artifacts")

# T3.1: a sampled run older than this no longer describes today's CI -- the same "the same call once returned August runs and, a minute later, September ones" defect this guards against, and the same 14-day figure check-lane-budget.ts's own check 5 (MAX_STALENESS_DAYS) applies to the OUTPUT file, applied here to the INPUT sample.
SAMPLE_MAX_AGE_DAYS = 14

# Actions API pagination: one page at a time, `per_page` capped at the API's own 100 maximum. `fetch_jobs`/`fetch_artifacts` walk pages explicitly with this cap rather than `ghx.api_json(..., paginate=True)`: `--paginate` without `--jq` only auto-merges a response whose BODY IS a bare top-level JSON array (MEASURED: `repos/.../labels` does); `.../runs/{id}/jobs` and `.../runs/{id}/artifacts` are both a JSON OBJECT with one array field inside (`{"total_count", "jobs": [...]}`), and gh's own `--paginate` help text says a multi-page object response is printed as one JSON document PER PAGE, not merged -- MEASURED live (run 36358238015, 158 jobs, two pages): `gh api --paginate` printed two back-to-back `{"total_count":158,"jobs":[...]}` objects, and `ghx.api_json`'s `.json()` (a plain `json.loads`) raised `GhBadOutputError` ("Extra data") on the concatenation. `--slurp` would wrap those into an array of page-objects, still needing this module to merge their `jobs` arrays itself, so a manual `page=` loop is no more code and stays inside `ghx.api_json`'s existing, already-tested single-document contract.
_PAGE_SIZE = 100

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


def stale_sample_findings(runs: list[dict[str, Any]], now: float | None = None) -> list[str]:
    """A warning per run older than `SAMPLE_MAX_AGE_DAYS`, by `created_at` -- never raises. MEASURED 2026-09-27: the identical `fetch_runs` call for `--refresh` returned a set of August runs and, one minute later, a set from September, so the sample age is checked on every read rather than trusted from a single observation. Pure and `now`-injectable so a test can pin the clock; `fetch_runs` calls it with the real time."""
    now_epoch = time.time() if now is None else now
    findings: list[str] = []
    for run in runs:
        created = _iso_to_epoch(run.get("created_at"))
        if created is None:
            continue
        age_days = (now_epoch - created) / 86_400.0
        if age_days > SAMPLE_MAX_AGE_DAYS:
            findings.append(
                "run %s (created %s) is %.1f day(s) old, over the %d-day sample limit."
                % (run.get("id"), run.get("created_at"), age_days, SAMPLE_MAX_AGE_DAYS)
            )
    return findings


def fetch_runs(
    repo: str, workflow: str, event: str, branch: str | None, status: str, limit: int
) -> list[dict[str, Any]]:
    """The `limit` newest runs of `event`, by `created_at` DESCENDING -- explicitly, never the API's own order. MEASURED 2026-09-27: the identical query returned an August-dated page and then, a minute later, a September-dated one, so "the API's own default order" is not trustworthy enough to slice on directly. A run older than `SAMPLE_MAX_AGE_DAYS` is warned about loudly (never refused: this is a report, and a thin or stale sample is still evidence), via `stale_sample_findings`."""
    query = "event=%s&status=%s&per_page=%d" % (event, status, min(limit, _PAGE_SIZE))
    if branch:
        query += "&branch=%s" % branch
    data = ghx.api_json(
        "repos/%s/actions/workflows/%s/runs?%s" % (repo, workflow, query), attempts=GH_ATTEMPTS
    )
    if not isinstance(data, dict):
        raise ghx.GhBadOutputError(
            [], 0, "expected a JSON object from the workflow-runs endpoint", ghx.FAILURE_FAILED
        )
    runs = data.get("workflow_runs")
    if not isinstance(runs, list):
        return []
    ordered = sorted(runs, key=lambda r: r.get("created_at") or "", reverse=True)
    selected = ordered[:limit]
    for finding in stale_sample_findings(selected):
        log.warn("budget_report: %s" % finding)
    return selected


def fetch_jobs(repo: str, run_id: int) -> list[dict[str, Any]]:
    """Every job of one run, across every page the Actions API needs.

    MEASURED 2026-09-27: run 36358238015 alone carries 158 jobs, and a single `per_page=100` page silently dropped the last 58 -- not "every measured run tops out at 80" as this function's own comment used to claim. Paged explicitly with `page=`; see `_PAGE_SIZE`'s own comment for why not `ghx.api_json(..., paginate=True)`.
    """
    jobs: list[dict[str, Any]] = []
    page = 1
    while True:
        data = ghx.api_json(
            "repos/%s/actions/runs/%s/jobs?per_page=%d&page=%d" % (repo, run_id, _PAGE_SIZE, page),
            attempts=GH_ATTEMPTS,
        )
        if not isinstance(data, dict):
            break
        page_jobs = data.get("jobs")
        if not isinstance(page_jobs, list) or not page_jobs:
            break
        jobs.extend(page_jobs)
        total_count = data.get("total_count")
        if isinstance(total_count, int) and len(jobs) >= total_count:
            break
        if len(page_jobs) < _PAGE_SIZE:
            break
        page += 1
    return jobs


# The needs graph, aliased the way check_job_timeout_headroom.refresh() is.

_JOB_HEADER_RE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
_FIELD_NAME_RE = re.compile(r"^    name:\s*(.+?)\s*$")
_FIELD_USES_RE = re.compile(r"^    uses:\s*(\./\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml)")
_FIELD_NEEDS_INLINE_RE = re.compile(r"^    needs:\s*\[(.*)\]\s*$")
_FIELD_NEEDS_SCALAR_RE = re.compile(r"^    needs:\s*([A-Za-z0-9_.-]+)\s*$")
_NEEDS_ITEM_RE = re.compile(r"^      - ([A-Za-z0-9_.-]+)\s*$")
# T3.2: does this job declare a `strategy: / matrix:` block? Two fixed indentation levels, the same style as every other field this parser reads. Needed to build
# `lane_display_patterns` below: a matrixed job whose `name:` carries no `${{ matrix.* }}`
# reference gets its combination auto-appended by the Actions API as `<name> (<values>)`, and a display-name pattern that does not allow for that suffix would never match a real
# leg (MEASURED: `quality-code`'s `name: Code` plus `matrix: {shard: [1,2,3,4]}` reports
# as `"Code (1)"`, `"Code (2)"`, ... on the live API).
_STRATEGY_RE = re.compile(r"^    strategy:\s*$")
_MATRIX_RE = re.compile(r"^      matrix:\s*$")


def parse_workflow_jobs(text: str) -> dict[str, dict[str, Any]]:
    """`{job_id: {"name", "needs": [job_id...], "uses", "has_matrix"}}` for one workflow file's TOP-LEVEL `jobs:` mapping.

    Regex, not `yaml.safe_load` -- see the module docstring. Best-effort: a line shape this does not recognise is simply skipped, which thins the graph rather than raising, because a partial critical path is still more informative than none for a REPORT.
    """
    jobs: dict[str, dict[str, Any]] = {}
    current: str | None = None
    in_jobs_block = False
    collecting_needs_list = False
    in_strategy_block = False
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
            jobs[current] = {"name": current, "needs": [], "uses": None, "has_matrix": False}
            collecting_needs_list = False
            in_strategy_block = False
            continue
        if current is None:
            continue
        if collecting_needs_list:
            item = _NEEDS_ITEM_RE.match(line)
            if item:
                jobs[current]["needs"].append(item.group(1))
                continue
            collecting_needs_list = False
        if _STRATEGY_RE.match(line):
            in_strategy_block = True
            continue
        if in_strategy_block:
            if _MATRIX_RE.match(line):
                jobs[current]["has_matrix"] = True
            elif line and not line.startswith("      "):
                in_strategy_block = False  # left the `strategy:` block
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


# T3.2: mapping a LANE (a job's YAML key, e.g. "quality-pytest") to the regex that matches its REAL Actions API display name, and computing each lane's fixed setup cost.

_TEMPLATE_RE = re.compile(r"\$\{\{.*?\}\}")


def _display_name_pattern(name: str, has_matrix: bool) -> re.Pattern[str]:
    """A job's raw `name:` field (e.g. `"E2E Workers (${{ matrix.os-image }}, ${{ matrix.shard }}/8)"`) to a compiled, anchored pattern matching the real API display name.

    A `${{ ... }}` template segment becomes a non-greedy wildcard: the workflow names the SHAPE, the API fills in the real matrix values. A job with NO template but a real `strategy: matrix:` (`has_matrix`) instead gets an OPTIONAL `" (<anything>)"` tail, because that is what the Actions API auto-appends when a matrixed job's name does not already vary per combination -- see `_STRATEGY_RE`'s own comment for the measured example. A job with neither matches its name VERBATIM, so an unsharded lane like `quality-content` is never accidentally satisfied by a same-prefixed sharded one.
    """
    if _TEMPLATE_RE.search(name):
        pattern = ".+?".join(re.escape(part) for part in _TEMPLATE_RE.split(name))
    else:
        pattern = re.escape(name)
        if has_matrix:
            pattern += r"(?: \([^)]*\))?"
    return re.compile("^%s$" % pattern)


def lane_display_patterns(
    root: Path, workflow: str = DEFAULT_WORKFLOW
) -> dict[str, re.Pattern[str]]:
    """`{lane id: pattern matching its real Actions API display name}`, for every job inside a reusable workflow `workflow` calls (one level -- the same reach `build_display_graph` gives the critical path).

    A LANE NOT YET SPLIT INTO ITS OWN JOB (T2.12/T2.14/T2.16) HAS NO ENTRY HERE, on purpose: `scripts/gates/check-lane-budget.ts`'s own comment calls that state "not an error at this layer" for the identical reason, and `--refresh` below treats a lane absent from this map the same way -- its `jobs`/fixed-cost entry is simply not written, never guessed.
    """
    ci_path = root / ".github" / "workflows" / workflow
    ci_jobs = parse_workflow_jobs(ci_path.read_text(encoding="utf-8"))
    patterns: dict[str, re.Pattern[str]] = {}
    for rec in ci_jobs.values():
        caller_display = rec["name"]
        callee = rec["uses"]
        if not callee:
            continue
        callee_path = root / callee.removeprefix("./")
        if not callee_path.is_file():
            continue
        callee_jobs = parse_workflow_jobs(callee_path.read_text(encoding="utf-8"))
        for callee_id, callee_rec in callee_jobs.items():
            base = "%s / %s" % (caller_display, callee_rec["name"])
            patterns[callee_id] = _display_name_pattern(base, callee_rec["has_matrix"])
    return patterns


# T3.2: the "runner step" a lane's fixed cost is measured UP TO -- see the module docstring's "SETUP STEPS UP TO THE RUNNER STEP" phrase from the plan itself. Best-effort and hand-verified against the real step names in ct-tests.yml/ci-quality.yml/ci-ops-test.yml as of 2026-09-27 (see the per-entry comment); a lane absent here, or whose real step gets renamed, simply keeps no fixed-cost estimate rather than a wrong one -- the same "thinner rather than wrong" choice the needs-graph parser makes.
RUNNER_STEP_PATTERNS: dict[str, re.Pattern[str]] = {
    "test-e2e-workers": re.compile(
        r"(?i)^run e2e tests\b"
    ),  # ct-tests.yml "Run E2E Tests (Workers)"
    "test-account-e2e": re.compile(r"(?i)^run account portal e2e tests\b"),
    "test-renet-go": re.compile(r"(?i)^run renet tests\b"),  # ct-tests.yml "Run renet tests"
    "test-renet-integration": re.compile(
        r"(?i)^run integration tests\b"
    ),  # ct-tests.yml "Run integration tests"
    "quality-pytest": re.compile(r"(?i)^python package tests\b"),
    "quality-gate-tests": re.compile(r"(?i)^quality-gate unit tests\b"),
    "ops-tutorials": re.compile(
        r"(?i)^tutorial sequence\b"
    ),  # ci-ops-test.yml "Tutorial sequence (shard ...)"
}


def job_fixed_cost_minutes(job: dict[str, Any], runner_step_re: re.Pattern[str]) -> float | None:
    """Minutes from this job's own start to the START of its first step matching `runner_step_re` -- "setup steps up to the runner step". `None` when no step matches: never a guessed 0, never the whole job."""
    job_start = _iso_to_epoch(job.get("started_at"))
    if job_start is None:
        return None
    for step in job.get("steps") or []:
        if not runner_step_re.search(step.get("name") or ""):
            continue
        step_start = _iso_to_epoch(step.get("started_at"))
        return None if step_start is None else max(0.0, (step_start - job_start) / 60.0)
    return None


# T3.2: the seven T2.7/T2.8 test lanes -- kept equal by hand to `scripts/ci-runner/unit-enumerators.ts`'s `LANE_ENUMERATORS` keys, read-only there.
LANE_IDS: tuple[str, ...] = (
    "test-e2e-workers",
    "test-account-e2e",
    "test-renet-go",
    "test-renet-integration",
    "quality-pytest",
    "quality-gate-tests",
    "ops-tutorials",
)

# Which unit-duration artifact FORMAT each lane's T1.6 artifact carries -- see the module docstring's "THE UNIT-DURATION ARTIFACT CONTRACT".
LANE_ARTIFACT_FORMAT: dict[str, str] = {
    "test-e2e-workers": "playwright",
    "test-account-e2e": "playwright",
    "test-renet-go": "gotestsum-junit",
    "test-renet-integration": "pytest-junit",
    "quality-pytest": "pytest-junit",
    "quality-gate-tests": "battery-json",
    "ops-tutorials": "tutorial-json",
}

_ARTIFACT_MEMBER_SUFFIX: dict[str, str] = {
    "playwright": ".json",
    "pytest-junit": ".xml",
    "gotestsum-junit": ".xml",
    "battery-json": ".json",
    "tutorial-json": ".json",
}


# T3.2: the five T1.6 unit-duration formats, each a pure `text -> {unit id: milliseconds}`.


def _walk_playwright_suite(
    suite: dict[str, Any],
    totals: dict[str, float],
    bucket_of_title: Mapping[str, str],
    bucket: str | None,
) -> None:
    for spec in suite.get("specs") or []:
        file = spec.get("file")
        if not file:
            continue
        key = "%s#%s" % (file, bucket) if bucket else file
        for test in spec.get("tests") or []:
            for result in test.get("results") or []:
                duration = result.get("duration")
                if isinstance(duration, int | float):
                    totals[key] = totals.get(key, 0.0) + float(duration)
    for child in suite.get("suites") or []:
        child_bucket = bucket_of_title.get(child.get("title") or "", bucket)
        _walk_playwright_suite(child, totals, bucket_of_title, child_bucket)


def parse_playwright_unit_ms(
    text: str, lane: str, *, bucket_titles: Mapping[str, str] | None = None
) -> dict[str, float]:
    """Playwright `--reporter=json`: per-spec-FILE total duration (ms), summed across every test and attempt under that file -- the file IS the unit `e2eWorkersUnits`/`accountE2eUnits` enumerate, UNLESS `bucket_titles` (`{describe title: bucket id}`, from `_e2e_shard_bucket_titles`) names the test's own immediate describe block, in which case the file splits into `<file>#<bucket>` sub-units matching the shard manifest's own `#partN` ids (T2.12) -- the same describe-name split `run-e2e.sh`'s `E2E_SHARD_GREP_BUCKETS` uses to build that leg's `--grep`, read here rather than duplicated, so a bucket rename in one place cannot silently drift from the other.

    MEASURED live (run 36358238015, 13-postgres-fork-isolation.test.ts): the Playwright JSON nests one suite per top-level `test.describe` directly under the file-level suite, with each spec's own `results[].duration` beneath it, so the bucket lookup happens exactly one level below the file. A file whose describe titles match nothing in `bucket_titles` keeps its own whole-file id, unsplit.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("playwright artifact for lane %r is not JSON: %s" % (lane, exc)) from exc
    totals: dict[str, float] = {}
    bucket_of_title = bucket_titles or {}
    for suite in parsed.get("suites") or []:
        _walk_playwright_suite(suite, totals, bucket_of_title, None)
    prefix = "e2e-workers" if lane == "test-e2e-workers" else "account-e2e"
    return {"%s:%s" % (prefix, key): ms for key, ms in totals.items()}


_CLASS_SEGMENT_RE = re.compile(r"^[A-Z]")


def _classname_to_module_relpath(classname: str) -> str:
    """A junit `classname` with no `file` attribute back to the `.py` file it came from -- MEASURED live (2026-09-28) against real artifacts for both lanes this feeds, neither of which pytest's own `--junitxml` writer gives a `file` attribute at all: run 36358238015's quality-pytest shard reports `classname=".ci.rediacc_ci.tests.test_housekeeping_cleanup_versions"`, and run 36332059919's test-renet-integration shard reports `classname="tests.integration.test_config_autosync.TestPortAutoSync"`. A blind `classname.replace(".", "/")` gets both wrong, and the wrong ids (`pytest:/ci/...`, `renet-integration:TestX.py`) are exactly what `scripts/gates/check-lane-budget.ts`'s BLOCKER named:

    - `quality-pytest`'s testpaths (`.ci/rediacc_ci/tests`, `.claude/rediacc_hooks/tests`) both live under a DOT-PREFIXED directory, so pytest's own dotted classname starts with an EMPTY segment before the first real dot (splitting `".ci.rediacc_ci..."` on `.` yields `["", "ci", "rediacc_ci", ...]`). A blind replace turns that leading emptiness into a leading SLASH ("/ci/...") instead of the directory's own leading dot (".ci/..." -- the exact relpath `qualityPytestUnits` and the committed manifest already use).
    - `test-renet-integration`'s own files (every one of them, `private/renet/tests/integration/test_*.py`) put each test inside a `class TestXxx:`, so pytest's classname carries the CLASS as one more dotted segment after the module. A blind replace turns that into an extra path component and an extra `.py` on the class name itself ("TestX.py") rather than the file the class lives in.

    Pytest's own naming convention is what tells the two kinds of segment apart without needing a directory listing: a module is snake_case (`test_x`), a class is PascalCase (`TestX`, this repo's own style -- `grep -rln '^class Test'` finds zero classes under either quality-pytest testpath, so this rule never misfires there). The module is therefore the classname with every trailing PascalCase segment dropped, the leading dot re-attached to whatever directory it prefixed, and every remaining `.` read as a path separator.
    """
    parts = classname.split(".")
    if len(parts) > 1 and parts[0] == "":
        parts = ["." + parts[1], *parts[2:]]
    while len(parts) > 1 and _CLASS_SEGMENT_RE.match(parts[-1]):
        parts.pop()
    return "/".join(parts) + ".py"


def parse_pytest_junit_unit_ms(text: str, lane: str) -> dict[str, float]:
    """pytest `--junitxml`: per-`<testcase>` `time` (seconds -> ms), aggregated by the `file` attribute (falling back to `_classname_to_module_relpath` -- neither lane's real artifact carries `file`, see that function's own docstring) into a `pytest:<relpath>` id (`quality-pytest`) or a `renet-integration:<basename>` id (`test-renet-integration`, matching `renetIntegrationUnits`'s bare-filename shape)."""
    try:
        root = ET.fromstring(text)  # noqa: S314 -- this repo's own pytest --junitxml artifact, not third-party input
    except ET.ParseError as exc:
        raise ValueError("pytest junit artifact for lane %r is not XML: %s" % (lane, exc)) from exc
    totals: dict[str, float] = {}
    for case in root.iter("testcase"):
        time_attr = case.get("time")
        if time_attr is None:
            continue
        try:
            ms = float(time_attr) * 1000.0
        except ValueError:
            continue
        file_attr = case.get("file")
        classname = case.get("classname") or ""
        if file_attr:
            relpath = file_attr
        elif classname:
            relpath = _classname_to_module_relpath(classname)
        else:
            continue
        unit_id = (
            "renet-integration:%s" % os.path.basename(relpath)
            if lane == "test-renet-integration"
            else "pytest:%s" % relpath
        )
        totals[unit_id] = totals.get(unit_id, 0.0) + ms
    return totals


def parse_gotestsum_junit_unit_ms(text: str) -> dict[str, float]:
    """`gotestsum --junitfile`: per-`<testcase>` `time` (seconds -> ms), aggregated by the BARE `classname` -- gotestsum writes the Go package import path there, the exact id `renetGoUnits` (`go list`) already uses, so no prefix is added.

    A PACKAGE WITH NO TEST FUNCTIONS STILL COSTS SOMETHING, and gotestsum measures it. `go test ./pkg/... ./cmd/...` compiles every package `go list` names, and one with no `_test.go` reports as `<testsuite tests="0" name="<import path>" time="0.763">` with no `<testcase>` at all (measured on run 36366933791's `unit-durations-test-renet-go-s1-*`: 7 such suites, 0.000-0.763 s). Keyed by `testcase` alone, those packages never got a sample and `check-lane-budget.ts` reported 12 enumerated units as unmeasured. The suite's own `time` is that package's real cost, so a suite with no testcase contributes it under its `name`; a suite WITH testcases keeps the per-testcase sum, unchanged."""
    try:
        root = ET.fromstring(text)  # noqa: S314 -- this repo's own gotestsum --junitfile artifact, not third-party input
    except ET.ParseError as exc:
        raise ValueError("gotestsum junit artifact is not XML: %s" % exc) from exc
    totals: dict[str, float] = {}
    for suite in root.iter("testsuite"):
        name = suite.get("name")
        suite_time = suite.get("time")
        if not name or suite_time is None or suite.find("testcase") is not None:
            continue
        try:
            totals[name] = totals.get(name, 0.0) + float(suite_time) * 1000.0
        except ValueError:
            continue
    for case in root.iter("testcase"):
        classname = case.get("classname")
        time_attr = case.get("time")
        if not classname or time_attr is None:
            continue
        try:
            ms = float(time_attr) * 1000.0
        except ValueError:
            continue
        totals[classname] = totals.get(classname, 0.0) + ms
    return totals


def _summary_unit_ms(text: str, list_key: str, name_key: str, id_prefix: str) -> dict[str, float]:
    """The shared shape behind the battery and tutorial JSON summaries: `{list_key: [{name_key: str, "duration_ms": number}, ...]}` -> `{"<id_prefix>:<name>": ms}`."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("%r summary is not JSON: %s" % (list_key, exc)) from exc
    entries = data.get(list_key)
    if not isinstance(entries, list):
        raise TypeError("summary carries no %r array" % list_key)
    out: dict[str, float] = {}
    for rec in entries:
        if not isinstance(rec, dict):
            continue
        name = rec.get(name_key)
        ms = rec.get("duration_ms")
        if isinstance(name, str) and isinstance(ms, int | float):
            out["%s:%s" % (id_prefix, name)] = float(ms)
    return out


def parse_battery_summary_unit_ms(text: str) -> dict[str, float]:
    """`{"drivers": [{"name": str, "duration_ms": number}, ...]}` -> `battery:<name>` ids, matching `qualityGateTestsUnits`."""
    return _summary_unit_ms(text, "drivers", "name", "battery")


def parse_tutorial_summary_unit_ms(text: str) -> dict[str, float]:
    """`{"tutorials": [{"slug": str, "duration_ms": number}, ...]}` -> `tutorial:<slug>` ids, matching `opsTutorialUnits`."""
    return _summary_unit_ms(text, "tutorials", "slug", "tutorial")


def _parse_unit_duration_text(
    fmt: str, lane: str, text: str, bucket_titles: Mapping[str, str] | None = None
) -> dict[str, float]:
    """One member's text, already sliced out of the zip, to `{unit id: ms}` by `fmt`."""
    if fmt == "playwright":
        return parse_playwright_unit_ms(text, lane, bucket_titles=bucket_titles)
    if fmt == "pytest-junit":
        return parse_pytest_junit_unit_ms(text, lane)
    if fmt == "gotestsum-junit":
        return parse_gotestsum_junit_unit_ms(text)
    if fmt == "battery-json":
        return parse_battery_summary_unit_ms(text)
    if fmt == "tutorial-json":
        return parse_tutorial_summary_unit_ms(text)
    raise AssertionError(
        "unreachable: LANE_ARTIFACT_FORMAT declared unknown format %r" % fmt
    )  # pragma: no cover


def parse_unit_duration_artifact(
    lane: str, blob: bytes, *, bucket_titles: Mapping[str, str] | None = None
) -> dict[str, float]:
    """One downloaded `unit-durations-<lane>-...` artifact zip to `{unit id: p90 candidate ms}`, by the format `LANE_ARTIFACT_FORMAT` declares for `lane`. `bucket_titles` (playwright only; see `parse_playwright_unit_ms`) is threaded straight through.

    A sharded E2E leg's own `run-e2e.sh` invocation writes ONE `unit-durations*.json` member per Playwright process it starts (T1.6's own per-invocation-file shape), so a single artifact can legitimately carry several members with the format's suffix -- not just the one a prior version of this function picked with `next(...)`. EVERY matching member is read and its per-unit-id milliseconds SUMMED: a unit split across invocations (e.g. a retried spec re-run as its own process) sums back to the file's total duration, the same total a single, unsplit invocation would have reported directly. A single matching member is therefore unchanged: the sum of one dict is that dict."""
    fmt = LANE_ARTIFACT_FORMAT.get(lane)
    if fmt is None:
        raise ValueError("no unit-duration artifact format declared for lane %r" % lane)
    suffix = _ARTIFACT_MEMBER_SUFFIX[fmt]
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        members = [n for n in names if n.endswith(suffix)]
        if not members:
            raise ValueError(
                "unit-durations artifact for lane %r carries no %r member (has: %s)"
                % (lane, suffix, names)
            )
        texts = [archive.read(member).decode("utf-8", "replace") for member in members]
    totals: dict[str, float] = {}
    for text in texts:
        for unit_id, ms in _parse_unit_duration_text(fmt, lane, text, bucket_titles).items():
            totals[unit_id] = totals.get(unit_id, 0.0) + ms
    return totals


# T3.2: the artifact API. `fetch_artifacts` goes through `ghx` like every other read here; the zip DOWNLOAD cannot, because `ghx.gh()` is text-only (TRAP-safe `.stdout` is a `str`) and a zip is binary -- the same reason `rediacc_ci.review.review_status.artifact_pr` shells out to `gh api .../zip` directly rather than through `ghx`.


def fetch_artifacts(repo: str, run_id: int) -> list[dict[str, Any]]:
    """Every artifact of one run (id, name, ...), across every page -- paged exactly like `fetch_jobs`; see `_PAGE_SIZE`'s own comment for why a manual `page=` loop and not `ghx.api_json(..., paginate=True)`."""
    artifacts: list[dict[str, Any]] = []
    page = 1
    while True:
        data = ghx.api_json(
            "repos/%s/actions/runs/%s/artifacts?per_page=%d&page=%d"
            % (repo, run_id, _PAGE_SIZE, page),
            attempts=GH_ATTEMPTS,
        )
        if not isinstance(data, dict):
            break
        page_artifacts = data.get("artifacts")
        if not isinstance(page_artifacts, list) or not page_artifacts:
            break
        artifacts.extend(page_artifacts)
        total_count = data.get("total_count")
        if isinstance(total_count, int) and len(artifacts) >= total_count:
            break
        if len(page_artifacts) < _PAGE_SIZE:
            break
        page += 1
    return artifacts


def download_artifact_zip(repo: str, artifact_id: Any) -> bytes:
    """One artifact's raw zip bytes. Raises `ghx.GhBadOutputError` on a non-zero exit, the same failure class every other call in this module raises -- TRAP 1 stays closed even off the `ghx.gh()` path."""
    argv = ["gh", "api", "repos/%s/actions/artifacts/%s/zip" % (repo, artifact_id)]
    result = subprocess.run(argv, capture_output=True, check=False, timeout=60)
    for attempt in range(1, GH_ATTEMPTS):
        if result.returncode == 0:
            break
        time.sleep(2**attempt)
        result = subprocess.run(argv, capture_output=True, check=False, timeout=60)
    if result.returncode != 0:
        raise ghx.GhBadOutputError(
            argv, result.returncode, result.stderr.decode("utf-8", "replace"), ghx.FAILURE_FAILED
        )
    return result.stdout


def collect_unit_durations(
    repo: str,
    run_ids: Sequence[int],
    lanes: Sequence[str] = LANE_IDS,
    *,
    list_artifacts: Callable[[str, int], list[dict[str, Any]]] = fetch_artifacts,
    download: Callable[[str, Any], bytes] = download_artifact_zip,
    bucket_titles: Mapping[str, str] | None = None,
) -> tuple[dict[str, dict[str, list[float]]], list[str]]:
    """`({lane: {unit id: [ms, ...]}}, [lane with ZERO matching artifacts across every run_id])`.

    `list_artifacts`/`download` are injectable so this is testable with zero network -- the same seam `check_job_timeout_headroom.refresh()` lacks and this module's own `fetch_runs`/`fetch_jobs` lack, taken here because artifact plumbing is the one part of T3.2 with no live data to verify against yet (T1.6 has not landed): a fixture-driven test is the only kind possible, so the function is built to take one. `bucket_titles` (see `parse_playwright_unit_ms`) is threaded straight through to every playwright artifact parsed.
    """
    per_lane: dict[str, dict[str, list[float]]] = {lane: {} for lane in lanes}
    hits: dict[str, int] = dict.fromkeys(lanes, 0)
    for run_id in run_ids:
        try:
            artifacts = list_artifacts(repo, run_id)
        except ghx.GhError as exc:
            log.warn("budget_report: could not list artifacts for run %s: %s" % (run_id, exc))
            continue
        for lane in lanes:
            prefix = "unit-durations-%s-" % lane
            for artifact in artifacts:
                name = artifact.get("name")
                if not isinstance(name, str) or not name.startswith(prefix):
                    continue
                try:
                    parsed = parse_unit_duration_artifact(
                        lane, download(repo, artifact.get("id")), bucket_titles=bucket_titles
                    )
                except (ghx.GhError, ValueError, TypeError, OSError) as exc:
                    log.warn(
                        "budget_report: could not read artifact %r on run %s: %s"
                        % (name, run_id, exc)
                    )
                    continue
                hits[lane] += 1
                for unit_id, ms in parsed.items():
                    per_lane[lane].setdefault(unit_id, []).append(ms)
    missing = [lane for lane in lanes if hits[lane] == 0]
    return per_lane, missing


# T3.1: the shard manifest's own "bucket greps" (a job display name for check 2's now-empty `job_p90_minutes`, and a describe-block split for the three `#partN` units this box's BLOCKER named as unsampled).

_SHARD_BUCKET_ARRAY_RE = re.compile(r"declare -A E2E_SHARD_GREP_BUCKETS=\((.*?)\n\)", re.DOTALL)
_SHARD_BUCKET_ENTRY_RE = re.compile(r'\["([^"]+)"\]="([^"]*)"')


def _e2e_shard_bucket_titles(root: Path, workflow_script: str = "run-e2e.sh") -> dict[str, str]:
    """`{describe title: bucket id}`, read from `.ci/scripts/test/run-e2e.sh`'s own `E2E_SHARD_GREP_BUCKETS` associative array (T2.12) -- the SAME table `run-e2e.sh` itself uses to build a bucketed leg's `--grep`, so `parse_playwright_unit_ms` can bucket a downloaded artifact's per-test data the identical way the real leg that produced it was scoped, rather than a second, drifting copy of the describe titles living here. Best-effort: a script this regex does not recognise yields an empty map (every spec falls back to whole-file grouping), never a crash -- this is a report."""
    script_path = root / ".ci" / "scripts" / "test" / workflow_script
    try:
        text = script_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    array_m = _SHARD_BUCKET_ARRAY_RE.search(text)
    if array_m is None:
        return {}
    titles: dict[str, str] = {}
    for bucket, pattern in _SHARD_BUCKET_ENTRY_RE.findall(array_m.group(1)):
        for title in pattern.split("|"):
            if title:
                titles[title] = bucket
    return titles


# T3.2: assembling `.ci/config/lane-durations.json`'s three measured sections.


def compute_lane_durations(
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    branch: str = DEFAULT_BRANCH,
    limit: int = DEFAULT_REFRESH_LIMIT,
    *,
    root: Path | None = None,
    list_artifacts: Callable[[str, int], list[dict[str, Any]]] = fetch_artifacts,
    download: Callable[[str, Any], bytes] = download_artifact_zip,
) -> dict[str, Any]:
    """The FRESH numbers `--refresh` writes and `--check` compares against: `{"jobs", "units", "job_max_seconds", "job_p90_minutes", "missing_artifact_lanes"}`. Never touches `refreshed_at` or `concurrency` -- the caller's job, since `--check` must compute this WITHOUT stamping anything."""
    tree_root = root if root is not None else paths.repo_root()

    pr_runs = fetch_runs(repo, workflow, "pull_request", None, REFRESH_PR_STATUS, limit)
    pr_jobs_by_run = [fetch_jobs(repo, run["id"]) for run in pr_runs]

    patterns = lane_display_patterns(tree_root, workflow)
    jobs_minutes: dict[str, float] = {}
    for lane, pattern in patterns.items():
        runner_re = RUNNER_STEP_PATTERNS.get(lane)
        if runner_re is None:
            continue
        samples: list[float] = []
        for run_jobs in pr_jobs_by_run:
            for job in run_jobs:
                if job.get("conclusion") != "success":
                    continue
                if not pattern.match(job.get("name") or ""):
                    continue
                cost = job_fixed_cost_minutes(job, runner_re)
                if cost is not None:
                    samples.append(cost)
        s = stats(samples)
        if s is not None:
            jobs_minutes[lane] = s["p90"]

    # T3.1: check 2's own gap -- a whole-job p90 (success-only wall time, MINUTES) by Actions API DISPLAY NAME (e.g. "Tests + Infra / E2E K8s Ceph"), for every job seen in the same PR-full sample `jobs_minutes` above already walks. `check-lane-budget.ts` reads it by display name (`displayNamePattern`, one pattern per call site), so this writes the number under the one name `--refresh` can derive without re-parsing `ci.yml` a second time.
    job_wall_by_name: dict[str, list[float]] = {}
    for run_jobs in pr_jobs_by_run:
        for job in run_jobs:
            name = job.get("name") or "?"
            wall = job_wall_minutes(job)
            if wall is not None:
                job_wall_by_name.setdefault(name, []).append(wall)
    job_p90_minutes: dict[str, float] = {}
    for name, walls in job_wall_by_name.items():
        s = stats(walls)
        if s is not None:
            job_p90_minutes[name] = s["p90"]

    bucket_titles = _e2e_shard_bucket_titles(tree_root)
    run_ids = [run["id"] for run in pr_runs]
    unit_samples, missing_lanes = collect_unit_durations(
        repo,
        run_ids,
        LANE_IDS,
        list_artifacts=list_artifacts,
        download=download,
        bucket_titles=bucket_titles,
    )
    units_ms: dict[str, float] = {}
    for per_unit in unit_samples.values():
        for unit_id, ms_list in per_unit.items():
            s = stats(ms_list)
            if s is not None:
                units_ms[unit_id] = s["p90"]

    main_runs = fetch_runs(repo, workflow, "push", branch, DEFAULT_STATUS, limit)
    main_jobs_by_run = [fetch_jobs(repo, run["id"]) for run in main_runs]
    job_max_seconds: dict[str, dict[str, Any]] = {}
    for name in HEADROOM_JOBS:
        wall_minutes = [
            wall
            for run_jobs in main_jobs_by_run
            for job in run_jobs
            if job.get("name") == name and (wall := job_wall_minutes(job)) is not None
        ]
        if wall_minutes:
            job_max_seconds[name] = {
                "observed_max_seconds": round(max(wall_minutes) * 60),
                "samples": len(wall_minutes),
            }

    return {
        "jobs": jobs_minutes,
        "units": units_ms,
        "job_max_seconds": job_max_seconds,
        "job_p90_minutes": job_p90_minutes,
        "missing_artifact_lanes": missing_lanes,
        # T3.1: the PR sample's own age findings, carried out so `--refresh` can REFUSE to stamp a fresh `refreshed_at` on them (see refresh_lane_durations).
        "stale_sample": stale_sample_findings(pr_runs),
    }


def leg_over_budget_finding(name: str, minutes: float) -> str | None:
    """T3.3's first trigger: a measured leg's own p90 over the 12-minute per-leg budget."""
    if minutes > PER_LEG_BUDGET_MINUTES:
        return "%s: measured p90 %.1fm, over the %gm per-leg budget." % (
            name,
            minutes,
            PER_LEG_BUDGET_MINUTES,
        )
    return None


def drift_finding(label: str, committed: float | None, measured: float | None) -> str | None:
    """T3.3's second trigger: a committed estimate more than 25% away from what was just measured. `None` (never a finding) when either side is unmeasured -- an absent number is `leg_over_budget_finding`'s or `--refresh`'s concern, not a drift."""
    if committed is None or measured is None:
        return None
    if committed == 0:
        return (
            None
            if measured == 0
            else "%s: committed estimate is 0 but measured %.4g -- cannot express as a ratio, treating as drifted."
            % (label, measured)
        )
    ratio = abs(measured - committed) / committed
    if ratio > DRIFT_THRESHOLD:
        return "%s: committed %.4g drifts %.0f%% from measured %.4g (over the %.0f%% limit)." % (
            label,
            committed,
            ratio * 100,
            measured,
            DRIFT_THRESHOLD * 100,
        )
    return None


# Unit-id prefix -> the lane whose committed shard manifest owns it. A bare id (no ":") is a Go import path of test-renet-go.
UNIT_PREFIX_MANIFEST = {
    "pytest": "quality-pytest",
    "account-e2e": "test-account-e2e",
    "e2e-workers": "test-e2e-workers",
    "renet-integration": "test-renet-integration",
    "": "test-renet-go",
}


def prune_units_to_manifests(units: dict[str, Any], root: Path) -> dict[str, Any]:
    """Drop a unit id its lane's committed manifest no longer names.

    The merge keeps every earlier unit so a lane missing from one sample is not zeroed, but that also kept ids nothing produces any more: on 2026-09-28 572 junit-classname keys (`pytest:/ci/...`, `renet-integration:TestX.py`) sat beside their corrected twins, and a deleted Go package (pkg/infra/vmsnapshot) kept its p90. A lane with no manifest (battery, tutorial) is left as it is.
    """
    owned: dict[str, set[str]] = {}
    for prefix, lane in UNIT_PREFIX_MANIFEST.items():
        manifest = root / ".ci" / "config" / "shards" / ("%s.json" % lane)
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        owned[prefix] = {i for leg in data.get("legs", []) for i in leg.get("ids", [])}
    kept: dict[str, Any] = {}
    for unit_id, value in units.items():
        prefix = unit_id.split(":", 1)[0] if ":" in unit_id else ""
        if prefix in owned and unit_id not in owned[prefix]:
            continue
        kept[unit_id] = value
    return kept


def refresh_lane_durations(
    path: Path,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    branch: str = DEFAULT_BRANCH,
    limit: int = DEFAULT_REFRESH_LIMIT,
    *,
    dry_run: bool = False,
    compute: Callable[..., dict[str, Any]] = compute_lane_durations,
) -> int:
    """T3.2: rewrite `path` from `limit` completed PR-full runs (success-only jobs; see REFRESH_PR_STATUS). `concurrency`, `$comment` and `defaultUnitMs` are PRESERVED verbatim -- this never guesses the operator's D-W1 ruling or hand-authored fallbacks; only `jobs`, `units`, `job_max_seconds`, `job_p90_minutes` and `refreshed_at` move. `--dry-run` computes and prints without writing, the one network call this box's own instructions permit running for real."""
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}

    computed = compute(repo, workflow, branch, limit)
    # A STALE SAMPLE IS REFUSED HERE, NOT WARNED. MEASURED 2026-09-28: one `--refresh` drew a sample whose Quality / Security p90 read 9.9m (1.8m the minute before) and whose lanes all had NO unit-duration artifacts, then stamped `refreshed_at` = now over it. check-lane-budget.ts's check 5 reads that stamp as "measured today", so a fresh stamp on old runs silently defeats it. A report may warn and carry on; the one writer of the stamp may not.
    stale = computed.get("stale_sample") or []
    if stale:
        for finding in stale:
            log.error("budget_report --refresh: %s" % finding)
        log.error(
            "budget_report --refresh: %d sampled run(s) are older than %d days; refusing to stamp "
            "refreshed_at on them. Re-run: the Actions API has served a stale page before."
            % (len(stale), SAMPLE_MAX_AGE_DAYS)
        )
        return 1
    for lane in computed["missing_artifact_lanes"]:
        log.warn(
            "budget_report --refresh: lane %r has NO unit-duration artifacts in the last "
            "%d sampled PR-full run(s); its units are UNCHANGED, not zeroed." % (lane, limit)
        )
    if (
        not computed["jobs"]
        and not computed["units"]
        and not computed["job_max_seconds"]
        and not computed["job_p90_minutes"]
    ):
        log.error(
            "budget_report --refresh: matched nothing at all across %d sampled run(s); "
            "refusing to stamp refreshed_at on numbers nothing verified." % limit
        )
        return 1

    updated: dict[str, Any] = {}
    if "$comment" in existing:
        updated["$comment"] = existing["$comment"]
    updated["refreshed_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated["concurrency"] = existing.get("concurrency", 20)
    updated["jobs"] = {**existing.get("jobs", {}), **computed["jobs"]}
    updated["units"] = prune_units_to_manifests(
        # the manifests beside THIS file (.ci/config/lane-durations.json -> the repo root three levels up), so a fixture path prunes against its own tree
        {**existing.get("units", {}), **computed["units"]},
        path.resolve().parent.parent.parent,
    )
    if "defaultUnitMs" in existing:
        updated["defaultUnitMs"] = existing["defaultUnitMs"]
    # T3.1: how many units a lane's leg runs at once (quality-pytest's `-n`), hand-authored beside defaultUnitMs and preserved the same way; dropping it would silently turn a parallel lane back into a serial estimate.
    if "unitParallelism" in existing:
        updated["unitParallelism"] = existing["unitParallelism"]
    updated["job_p90_minutes"] = {
        **existing.get("job_p90_minutes", {}),
        **computed["job_p90_minutes"],
    }
    if isinstance(existing.get("job_max_seconds"), dict):
        updated["job_max_seconds"] = existing["job_max_seconds"]
    if computed["job_max_seconds"]:
        section = dict(updated.get("job_max_seconds") or {})
        section["jobs"] = {**section.get("jobs", {}), **computed["job_max_seconds"]}
        updated["job_max_seconds"] = section

    payload = json.dumps(updated, indent=2) + "\n"
    if dry_run:
        print(payload)
        print("DRY RUN: %s was NOT written." % path, file=sys.stderr)
        return 0
    path.write_text(payload, encoding="utf-8")
    print(
        "lane-durations.json refreshed from %d sampled run(s): %d job(s), %d unit(s), "
        "%d headroom job(s), %d other job p90(s)."
        % (
            limit,
            len(computed["jobs"]),
            len(computed["units"]),
            len(computed["job_max_seconds"]),
            len(computed["job_p90_minutes"]),
        )
    )
    return 0


def check_lane_durations(
    path: Path,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    branch: str = DEFAULT_BRANCH,
    limit: int = DEFAULT_REFRESH_LIMIT,
    *,
    compute: Callable[..., dict[str, Any]] = compute_lane_durations,
) -> int:
    """T3.3: freshly measure, then compare against the COMMITTED file -- never writes. Fails (1) when any leg's measured p90 exceeds 12m, or a committed estimate drifts more than 25% from what was just measured."""
    try:
        committed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("budget_report --check: %s does not parse: %s" % (path, exc), file=sys.stderr)
        return 1
    if not isinstance(committed, dict):
        print("budget_report --check: %s is not a JSON object" % path, file=sys.stderr)
        return 1

    computed = compute(repo, workflow, branch, limit)
    findings: list[str] = [
        "lane %r has NO unit-duration artifacts in the last %d sampled run(s)." % (lane, limit)
        for lane in computed["missing_artifact_lanes"]
    ]
    findings.extend("stale sample: %s" % f for f in computed.get("stale_sample") or [])

    committed_jobs = committed.get("jobs") or {}
    for lane, minutes in sorted(computed["jobs"].items()):
        f = leg_over_budget_finding(lane, minutes)
        if f:
            findings.append(f)
        d = drift_finding("job %r fixed cost" % lane, committed_jobs.get(lane), minutes)
        if d:
            findings.append(d)

    committed_units = committed.get("units") or {}
    for unit_id, ms in sorted(computed["units"].items()):
        d = drift_finding("unit %r p90" % unit_id, committed_units.get(unit_id), ms)
        if d:
            findings.append(d)

    # DRIFT ONLY for job_max_seconds -- NOT leg_over_budget_finding's 12-minute ceiling. Validate Promotion/Stage Artifacts are the two jobs D-W2 keeps OUTSIDE the lane-budget gate precisely because they are not lane-sharded; their own ceiling is check_job_timeout_headroom.py's 1.5x-headroom-under-timeout-minutes rule, a different policy this check must not silently double up on.
    committed_headroom = (committed.get("job_max_seconds") or {}).get("jobs") or {}
    for name, rec in sorted(computed["job_max_seconds"].items()):
        minutes = rec["observed_max_seconds"] / 60.0
        prior = committed_headroom.get(name) or {}
        prior_seconds = prior.get("observed_max_seconds")
        d = drift_finding(
            "job %r observed max" % name,
            None if prior_seconds is None else prior_seconds / 60.0,
            minutes,
        )
        if d:
            findings.append(d)

    if findings:
        print("CI time budget check found %d issue(s):" % len(findings), file=sys.stderr)
        for f in findings:
            print("  - %s" % f, file=sys.stderr)
        return 1
    print(
        "CI time budget check: %d job lane(s), %d unit(s), %d headroom job(s) sampled "
        "from %d run(s), all within budget and within %.0f%% of committed."
        % (
            len(computed["jobs"]),
            len(computed["units"]),
            len(computed["job_max_seconds"]),
            limit,
            DRIFT_THRESHOLD * 100,
        )
    )
    return 0


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
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="T3.2: rewrite .ci/config/lane-durations.json from --refresh-limit green "
        "PR-full runs (network write, unless --dry-run)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="T3.3: compare the committed lane-durations.json against freshly measured "
        "data; exit 1 on a leg over 12m or a >25%% drift (network read, never writes)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --refresh: compute and print without writing the file (the one live "
        "network call this box's own instructions permit running directly)",
    )
    parser.add_argument(
        "--refresh-limit",
        type=int,
        default=DEFAULT_REFRESH_LIMIT,
        help="completed PR-full runs sampled by --refresh/--check (success-only jobs)",
    )
    parser.add_argument(
        "--lane-durations",
        type=Path,
        default=None,
        help="override .ci/config/lane-durations.json's path (tests)",
    )
    args = parser.parse_args(argv)

    if args.refresh or args.check:
        lane_path = args.lane_durations or (paths.repo_root() / LANE_DURATIONS_REL_PATH)
        try:
            if args.refresh:
                return refresh_lane_durations(
                    lane_path,
                    args.repo,
                    args.workflow,
                    args.branch,
                    args.refresh_limit,
                    dry_run=args.dry_run,
                )
            return check_lane_durations(
                lane_path, args.repo, args.workflow, args.branch, args.refresh_limit
            )
        except ghx.GhError as exc:
            print("budget_report: %s" % exc, file=sys.stderr)
            return 1

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

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
      "unitParallelism": {"<lane id>": <workers>},  # optional, DERIVED by --refresh (see UNIT PARALLELISM below)
      "job_p90_minutes": {"<job DISPLAY name>": <p90, MINUTES>},  # T3.1; see below
      "gate_step_p90_seconds": {"<gate id>": <p90, SECONDS>},  # CI-representative tiers; see below
      "job_max_seconds": {
        "refreshed_at": "..." | null,        # OWN timestamp -- see WHY TWO refreshed_at BELOW
        "jobs": {"<job display name>": {"observed_max_seconds": <int>, "samples": <int>}}
      }
    }

`jobs` and `units` (plus `concurrency` and `defaultUnitMs`) are `scripts/gates/check-lane-budget.ts`'s `LaneDurations` interface EXACTLY -- that file is the consumer, already written and NOT owned by this box, so its existing `Record<string, number>` shapes are the contract this module writes TO rather than a schema invented here. A "lane id" is a job's YAML KEY (`quality-code`, `test-e2e-workers`, ...), the same string `scripts/ci-runner/lanes.ts`'s `laneCapabilities`/`TEST_LANE_WORKFLOWS` and `gates.lock.json`'s `ci.job` use -- NOT the Actions API's own job display name (`"Quality / Code (1)"`). `lane_display_patterns` below is what bridges the two.

`job_p90_minutes` is T3.1's own addition, for check 2's 63 unpriced non-lane jobs (the gate's own `LaneDurations.job_p90_minutes` field exists and says "nothing writes it yet"). Keyed by Actions API DISPLAY NAME, not a lane id: unlike `jobs`/`units`, most of these jobs have no YAML-key alias to look one up by without re-walking `ci.yml`'s own `needs:`/`uses:` graph a second time. The CONSUMER maps names back to job ids: `check-lane-budget.ts`'s `displayNamePattern` walks `ci.yml` and its callees per call site and matches these keys, judging a priced lane's matrix legs in their lane and every other job in check 2. `--refresh` writes it from success-only wall-time samples over the SAME PR-full runs `jobs`/`units` already sample. A job that ran in NO sampled PR run (the main-push-only release chain) takes its p90 from the main-push runs the same refresh already samples for `job_max_seconds` (`main_push_only_p90`); a PR job's number never comes from main.
A "unit id" is keyed exactly as `scripts/ci-runner/unit-enumerators.ts`'s `LANE_ENUMERATORS` name it (`e2e-workers:<file>`, `account-e2e:<file>`, a bare Go import path, `renet-integration:<file>`, `pytest:<file>`, `battery:<name>`, `tutorial:<slug>`) -- read-only there too.

`gate_step_p90_seconds` is CI-representative timing for `scripts/gates/check-gate-manifest.ts`'s slow/pre-push tier verdict, keyed by a `scripts/ci-runner/gates.lock.json` gate `id`, SECONDS not minutes. A gate the lock marks `"ci": {"kind": "step", ...}` runs as its own named workflow step (`ci.job` a YAML job key, `ci.step` that job's own step `name`), and `--refresh` times it the same way `job_p90_minutes` times a whole job: success-only, over the SAME PR-full sample `jobs`/`units`/`job_p90_minutes` already walk (`load_gate_ci_steps` reads the lock, `lane_display_patterns` -- already general over every job inside a reusable workflow, not only the seven test lanes -- maps `ci.job` to the display-name pattern its own job matches, and the step is found by exact-name match inside that job's `steps` array, already present in `fetch_jobs`'s payload with no extra network call). A gate whose `ci.kind` is not `"step"` (`local-only`, a gate a `test` drives) carries no entry, matching WHY `units` stays scoped above: this is a different instrument for a different set of gates, not a gap. Nor does a gate whose step is a COMPOSITE shared with other gates (`ci-quality.yml`'s `i18n` step alone chains 27 gates' npm scripts into one hand-written `npm run check:i18n`): its wall time is their SUM, not any one gate's own cost, so `_exclusive_ci_steps` excludes every id sharing a `(job, step)` pair with another rather than mis-attributing the whole step's time to each. This is what lets `check-gate-manifest.ts` judge a gate's tier from CI's own timing instead of the local, checkout-dependent `.ci/cache/gate-durations.json` (large gitignored assets present in one checkout and not another used to give the identical gate contradictory verdicts, since CI itself keeps no such cache and never judged a tier at all).

UNIT PARALLELISM (`unitParallelism`) IS DERIVED, NOT HAND-AUTHORED. quality-pytest's legs run `pytest -n <granted cores> --dist loadgroup` (check_pytest.py `jobs()`), so the worker count is the leg runner's core count. The measured source would be pytest-xdist's `N workers [M items]` header, but a PASSING leg never prints it (check_pytest.py echoes pytest's output only on a failure) and the junit artifact carries no per-worker field, so no measured source is reachable from the job payloads, step lists or artifacts this refresh already reads. `--refresh` therefore derives the count from the lane job's `runs-on` label (`lane_runner_labels`) and the label's documented vCPU count (`RUNNER_VCPUS`: GitHub-hosted standard runners of a public repository). A lane whose label is not in that table, or a refresh that finds no such lane, measures nothing and KEEPS the prior value, named on stderr: dropping the key would make check-lane-budget.ts price the lane as serial.

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
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

from rediacc_ci import log, paths
from rediacc_ci.core import gh_retry, ghx
from rediacc_ci.well_known import GH_REPO

DEFAULT_REPO = GH_REPO
DEFAULT_WORKFLOW = "ci.yml"
DEFAULT_BRANCH = "main"
DEFAULT_LIMIT = 15
DEFAULT_STATUS = "success"
# THE PR SAMPLE FOR --refresh/--check IS COMPLETED RUNS, NOT SUCCESSFUL ONES (operator default #32e66d3b, 2026-09-27). check:ci-plan-implementation reds every PR run until spec W's last box closes (zero threshold, 2026-09-26 ruling) and main pushes skip the full suite, so a run-level `success` filter left NO qualifying run and W could never close its own budget boxes. Durations stay clean because every job sample below is success-only; a red Quality / Branch does not change how long a green test leg took. Unit artifacts are uploaded always(), so a failed leg's per-test times can enter the unit p90.
REFRESH_PR_STATUS = "completed"
# T3.2: how many completed PR-full runs `--refresh`/`--check` sample (see REFRESH_PR_STATUS). Separate from DEFAULT_LIMIT (15, the read-only report's own default) because the plan's box names 10 explicitly, and the two commands have different costs -- --refresh/--check also list and download artifacts per run, which --limit 15's report path never does.
DEFAULT_REFRESH_LIMIT = 10

# EVERY READ HERE RETRIES, because one report makes dozens of calls and a single transient failure used to abort all of them: on 2026-09-27 a `--refresh --dry-run` died on `stream error: stream ID 1; CANCEL; received from peer` for one run's jobs, and the identical rerun succeeded. `ghx.gh` defaults to one attempt on purpose (an auth failure should not cost backoff); a report over many runs is the caller that wants three, and wants them only for a TRANSIENT failure: every read goes through `gh_retry`, which retries a 5xx or a connection fault with a 5 s / 15 s backoff and raises a 4xx at once (2026-10-06: CI job 112158906504 died on a `gh: Server Error (HTTP 502)` that the old immediate 2 s / 4 s retries all landed inside).
GH_ATTEMPTS = 3

# How many times `fetch_runs` reads the run list before sampling the union of what came back (see there).
RUN_LIST_READS = 3
LANE_DURATIONS_REL_PATH = ".ci/config/lane-durations.json"
GATES_LOCK_REL_PATH = "scripts/ci-runner/gates.lock.json"
PER_LEG_BUDGET_MINUTES = 12.0
DRIFT_THRESHOLD = 0.25
# A UNIT's drift counts only when the absolute move is at least this many milliseconds. Unit p90s are sampled from 10 runs, so a small unit swings by large percentages on runner noise alone: an hour after a refresh, check:ci-budget-freshness failed PR #594 (run 37190043363) on 16 -> 124.5 ms, 2119 -> 1566 ms and 5967 -> 7620 ms, none of which moves a leg's wall enough to matter. Job-level drift keeps the pure ratio. Same reasoning as gate_costs.MIN_DRIFT_CPU_S.
# WHY 5 s AND NOT 2 s (#ce346f22). The 10-run sample is repo-wide PR runs, so every push on the open PR replaces one sampled run, and 2 s still sat inside that churn: on 2026-10-04/05 branch 1004-2 refreshed lane-durations.json four times in a day for 5-15 s units moving 2.1-3.4 s (test_wl_hints 5278 -> 7377 ms, test_review_standing_orders_brief 9068 -> 6681, test_wl_loop_next 9688 -> 13070, test_shape_probe_agreement 10067 -> 13002, e2e 16-setup-installation-params 5967 -> 8335), each refresh a 45-minute pre-push plus a commit that fed the sample again. Replayed over the last 20 refreshes, 5 s clears every same-day move and still fires on each days-apart refresh that held real movement (account-e2e +21% on 2026-10-04: 55 units; 12-01-subscription-renewal 22838 -> 38369 ms, which kept climbing to 42544). Against a 12-minute leg, 5 s is under 0.7%.
MIN_UNIT_DRIFT_MS = 5000
# WHICH STATISTIC A UNIT IS JUDGED ON (#d901ba82). A unit's measured p90 over the ~7 samples a 10-run window gives it is the 2nd-slowest sample or the slowest, so ONE slow runner moves it past 25% while the unit's typical run never moved: on 2026-10-05/06 check:ci-budget-freshness went red four times on tutorial:branching 65 -> 83 s (samples 56 58 60 62 67 99 101 s: five runs unchanged, two outliers), tutorial:installation 13 -> 18.5 s (median 9 s), test_gate_doc_region_parity 120 -> 152 s (+27%, median 96 s) and a 105 -> 78 s pytest p90 that was a real 105 -> 57 s step change still rolling through the window, one red per refresh. Each red cost a ~1,600-line rewrite of lane-durations.json and a 16-minute pre-push.
# So the committed p90 is held against the measured sample's own spread instead of against its p90 alone:
#   - SLOWER: the measured MEDIAN must clear the committed p90 by 25% (and MIN_UNIT_DRIFT_MS). Outliers cannot move a median, a real doubling moves it 2x (any unit whose committed p90 sits under 1.6x its median, which the 2026-10-06 sample showed for over 90% of units at 10 s and up), and a step change reds once, when half the window carries it, not once per refresh.
#   - FASTER: the measured MAX, the slowest sample of the window, must fall 25% under the committed p90. A stale over-estimate only over-provisions a leg, so it reds once the WHOLE window agrees, never mid-roll.
# Without per-unit stats (an old caller) both sides fall back to the p90 and the rule is the plain 25% ratio it always was. The per-lane sum below stays on p90: summing averages the outliers away (no same-day refresh moved a lane sum past 3.4%) and it is the backstop for a lane-wide slowdown.
UNIT_SLOWER_STAT = "median"
UNIT_FASTER_STAT = "max"
# D-W2/T3.4: the two direct (non-lane-sharded) ci.yml jobs job-timeout-baseline.json used to cover, now `job_max_seconds`' own baseline. See check_job_timeout_headroom.py.
HEADROOM_JOBS = ("Validate Promotion", "Stage Artifacts")

# T3.1: a sampled run older than this no longer describes today's CI -- the same "the same call once returned August runs and, a minute later, September ones" defect this guards against, and the same 14-day figure check-lane-budget.ts's own check 5 (MAX_STALENESS_DAYS) applies to the OUTPUT file, applied here to the INPUT sample.
SAMPLE_MAX_AGE_DAYS = 14

# Actions API pagination: one page at a time, `per_page` capped at the API's own 100 maximum. `fetch_jobs`/`fetch_artifacts` walk pages explicitly with this cap rather than `gh_retry.api_json(..., paginate=True)`: `--paginate` without `--jq` only auto-merges a response whose BODY IS a bare top-level JSON array (MEASURED: `repos/.../labels` does); `.../runs/{id}/jobs` and `.../runs/{id}/artifacts` are both a JSON OBJECT with one array field inside (`{"total_count", "jobs": [...]}`), and gh's own `--paginate` help text says a multi-page object response is printed as one JSON document PER PAGE, not merged -- MEASURED live (run 36358238015, 158 jobs, two pages): `gh api --paginate` printed two back-to-back `{"total_count":158,"jobs":[...]}` objects, and `ghx.api_json`'s `.json()` (a plain `json.loads`) raised `GhBadOutputError` ("Extra data") on the concatenation. `--slurp` would wrap those into an array of page-objects, still needing this module to merge their `jobs` arrays itself, so a manual `page=` loop is no more code and stays inside `ghx.api_json`'s existing, already-tested single-document contract.
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


def sample_window_param(now: float | None = None) -> str:
    """`created=>=<date>` (URL-encoded) bounding a runs query to the last `SAMPLE_MAX_AGE_DAYS` days.

    WHY THE QUERY CARRIES A DATE AND NOT ONLY A POST-HOC WARNING. MEASURED 2026-09-28: `workflows/ci.yml/runs?event=pull_request&status=completed&per_page=10` (no `branch`) answered `total_count` 102 and ten runs from 2026-08-28..30 while the same repo had PR runs from that very morning; `...&status=success` answered 17 runs from August. The identical query with `created=>=2026-09-14` added answered 120 runs, newest first, from today -- on every retry. GitHub serves an `event`/`status`-only listing from a stale index; a `created` bound forces the fresh one. Sorting and `stale_sample_findings` cannot repair a page that never contained a fresh run, so the window goes INTO the request."""
    now_epoch = time.time() if now is None else now
    since = datetime.fromtimestamp(now_epoch - SAMPLE_MAX_AGE_DAYS * 86_400.0, tz=UTC)
    return "created=%%3E%%3D%s" % since.strftime("%Y-%m-%d")


def fetch_runs(
    repo: str,
    workflow: str,
    event: str,
    branch: str | None,
    status: str,
    limit: int,
    *,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """The `limit` newest runs of `event` created inside the `SAMPLE_MAX_AGE_DAYS` window (`sample_window_param`), by `created_at` DESCENDING -- explicitly, never the API's own order. MEASURED 2026-09-27: the identical query returned an August-dated page and then, a minute later, a September-dated one, so "the API's own default order" is not trustworthy enough to slice on directly. A run older than `SAMPLE_MAX_AGE_DAYS` is still warned about loudly (never refused: this is a report, and a thin or stale sample is still evidence), via `stale_sample_findings` -- with the window in the query that warning now means the API ignored the bound, not that the sample drifted."""
    query = "event=%s&status=%s&per_page=%d&%s" % (
        event,
        status,
        min(limit, _PAGE_SIZE),
        sample_window_param(now),
    )
    if branch:
        query += "&branch=%s" % branch
    # ONE READ IS NOT A SAMPLE. MEASURED 2026-09-28, after the date window landed: the identical `branch=0923-1` query that answered ten runs from that day, 25 times in a row, answered once with six runs from 2026-09-23/24. Those sit inside the 14-day window, so `stale_sample_findings` stayed silent, and a `--refresh` built on them rewrote nothing for E2E Workers or OPS Provision while stamping `refreshed_at`. `RUN_LIST_READS` reads are merged by run id, so one stale page cannot hide the fresh runs another read returns, and pages that disagree are named.
    path = "repos/%s/actions/workflows/%s/runs?%s" % (repo, workflow, query)
    by_id: dict[Any, dict[str, Any]] = {}
    page_ids: list[tuple[Any, ...]] = []
    for _ in range(RUN_LIST_READS):
        data = gh_retry.api_json(path, attempts=GH_ATTEMPTS)
        if not isinstance(data, dict):
            raise ghx.GhBadOutputError(
                [], 0, "expected a JSON object from the workflow-runs endpoint", ghx.FAILURE_FAILED
            )
        page = data.get("workflow_runs")
        if not isinstance(page, list):
            page = []
        page_ids.append(tuple(sorted(r.get("id") for r in page if isinstance(r, dict))))
        for run in page:
            if isinstance(run, dict):
                by_id.setdefault(run.get("id"), run)
    if len(set(page_ids)) > 1:
        log.warn(
            "budget_report: %d reads of the %s run list disagreed (%s run(s) each); sampling their union."
            % (len(page_ids), event, "/".join(str(len(ids)) for ids in page_ids))
        )
    runs = list(by_id.values())
    ordered = sorted(runs, key=lambda r: r.get("created_at") or "", reverse=True)
    selected = ordered[:limit]
    for finding in stale_sample_findings(selected, now):
        log.warn("budget_report: %s" % finding)
    return selected


def fetch_jobs(repo: str, run_id: int) -> list[dict[str, Any]]:
    """Every job of one run, across every page the Actions API needs.

    MEASURED 2026-09-27: run 36358238015 alone carries 158 jobs, and a single `per_page=100` page silently dropped the last 58 -- not "every measured run tops out at 80" as this function's own comment used to claim. Paged explicitly with `page=`; see `_PAGE_SIZE`'s own comment for why not `gh_retry.api_json(..., paginate=True)`.
    """
    jobs: list[dict[str, Any]] = []
    page = 1
    while True:
        data = gh_retry.api_json(
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
_FIELD_RUNS_ON_RE = re.compile(r"^    runs-on:\s*(.+?)\s*$")
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
    """`{job_id: {"name", "needs": [job_id...], "uses", "has_matrix", "runs_on"}}` for one workflow file's TOP-LEVEL `jobs:` mapping.

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
            jobs[current] = {
                "name": current,
                "needs": [],
                "uses": None,
                "has_matrix": False,
                "runs_on": None,
            }
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
        runs_on_m = _FIELD_RUNS_ON_RE.match(line)
        if runs_on_m:
            jobs[current]["runs_on"] = runs_on_m.group(1).strip("\"'")
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


# `CI Verdict` is not a job of `ci.yml` at all -- it is posted by the SEPARATE `ci-verdict.yml` workflow once the run completes, together with its `Publish CI Verdict` job -- yet `actions/runs/{id}/jobs` can return such an after-the-fact observer alongside ci.yml's own jobs, timestamped after the pipeline itself, and critical_path's plain "latest completed_at wins" sink rule would mistake it for the run's true finish line (measured on run 35128695736 with an earlier observer, 13+ hours late). `CI Complete` is NOT excluded here: it is a genuine ci.yml job and the plan's own section 1b ends its sample critical path there.
# `Review Complete`, `Review Status` and `Claude Review` are the PR review (PLAN-github-pr-review-restore), posted by `claude-review.yml` and `review-status.yml` against the head SHA, finishing whenever the review does: observers of the same kind. Review Complete being a required check on main again (operator ruling 2026-10-03) puts it on the merge path, not on Console CI's critical path, which is what this list times.
CRITICAL_PATH_EXCLUDE = (
    "CI Verdict",
    "Publish CI Verdict",
    "Review Complete",
    "Review Status",
    "Claude Review",
)


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


# vCPUs of a GitHub-hosted standard runner in a PUBLIC repository (docs.github.com "GitHub-hosted runners": ubuntu-latest, ubuntu-24.04, ubuntu-22.04 are 4 vCPU / 16 GB; a private repository gets 2). The repo is public (`gh repo view --json isPrivate`, 2026-10-05). A label absent here has no derivable count.
RUNNER_VCPUS: dict[str, int] = {"ubuntu-latest": 4, "ubuntu-24.04": 4, "ubuntu-22.04": 4}
# Lanes whose legs run `pytest -n <granted cores>`: their `unitParallelism` is the runner's core count.
CORE_SIZED_LANES: tuple[str, ...] = ("quality-pytest",)


def lane_runner_labels(root: Path, workflow: str = DEFAULT_WORKFLOW) -> dict[str, str]:
    """`{lane id: its job's `runs-on` label}` for every callee job of `workflow` that declares a literal one, read the way `lane_display_patterns` reads the same files."""
    ci_jobs = parse_workflow_jobs((root / ".github" / "workflows" / workflow).read_text("utf-8"))
    labels: dict[str, str] = {}
    for rec in ci_jobs.values():
        callee = rec["uses"]
        if not callee:
            continue
        callee_path = root / callee.removeprefix("./")
        if not callee_path.is_file():
            continue
        for callee_id, callee_rec in parse_workflow_jobs(
            callee_path.read_text(encoding="utf-8")
        ).items():
            if callee_rec["runs_on"]:
                labels[callee_id] = callee_rec["runs_on"]
    return labels


def derive_unit_parallelism(root: Path, workflow: str = DEFAULT_WORKFLOW) -> dict[str, int]:
    """`{lane id: workers}` for each `CORE_SIZED_LANES` lane whose `runs-on` label has a documented vCPU count; a lane with no such label is absent (the caller keeps the prior value). See the module docstring's UNIT PARALLELISM."""
    try:
        labels = lane_runner_labels(root, workflow)
    except OSError:
        return {}
    return {
        lane: RUNNER_VCPUS[labels[lane]]
        for lane in CORE_SIZED_LANES
        if labels.get(lane) in RUNNER_VCPUS
    }


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


# T3.2: the artifact API. `fetch_artifacts` goes through `ghx` like every other read here; the zip DOWNLOAD cannot, because `ghx.gh()` is text-only (TRAP-safe `.stdout` is a `str`) and a zip is binary -- so the download shells out to `gh api .../zip` directly rather than through `ghx`.


def fetch_artifacts(repo: str, run_id: int) -> list[dict[str, Any]]:
    """Every artifact of one run (id, name, ...), across every page -- paged exactly like `fetch_jobs`; see `_PAGE_SIZE`'s own comment for why a manual `page=` loop and not `gh_retry.api_json(..., paginate=True)`."""
    artifacts: list[dict[str, Any]] = []
    page = 1
    while True:
        data = gh_retry.api_json(
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
    result = gh_retry.retry_transient(
        lambda: subprocess.run(argv, capture_output=True, check=False, timeout=60),
        lambda r: None if r.returncode == 0 else r.stderr.decode("utf-8", "replace") or "failed",
        attempts=GH_ATTEMPTS,
        sleep=time.sleep,
    )
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
    wanted: list[tuple[int, str, str, Any]] = []
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
                if isinstance(name, str) and name.startswith(prefix):
                    wanted.append((run_id, lane, name, artifact.get("id")))

    def read(item: tuple[int, str, str, Any]) -> tuple[dict[str, float] | None, Exception | None]:
        _run_id, lane, _name, artifact_id = item
        try:
            return (
                parse_unit_duration_artifact(
                    lane, download(repo, artifact_id), bucket_titles=bucket_titles
                ),
                None,
            )
        except (ghx.GhError, ValueError, TypeError, OSError) as exc:
            return None, exc

    log.info(
        "budget_report: reading %d unit-duration artifact(s) from %d run(s), %d at a time"
        % (len(wanted), len(run_ids), ARTIFACT_DOWNLOAD_WORKERS)
    )
    # `map` yields in submission order, so the merge below is the same walk the serial loop made: run, then lane, then artifact.
    with ThreadPoolExecutor(max_workers=ARTIFACT_DOWNLOAD_WORKERS) as pool:
        results = list(pool.map(read, wanted))
    for (run_id, lane, name, _artifact_id), (parsed, failure) in zip(wanted, results, strict=True):
        if parsed is None:
            log.warn(
                "budget_report: could not read artifact %r on run %s: %s" % (name, run_id, failure)
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


# CI-representative gate-step timing (see the module docstring's `gate_step_p90_seconds` paragraph): judging `check-gate-manifest.ts`'s slow/pre-push tier from CI's own step timing rather than the local, checkout-dependent `.ci/cache/gate-durations.json`.


def load_gate_ci_steps(root: Path) -> dict[str, tuple[str, str]]:
    """`{gate id: (job id, step name)}` for every `"ci": {"kind": "step", ...}` gate in `scripts/ci-runner/gates.lock.json` -- the lock's own `ci.job`/`ci.step`, read-only here (this module writes `lane-durations.json`, never the lock). A gate whose `ci.kind` is `"local-only"` or `"test"`, or that carries no `ci` block at all, names no single CI step to time and is simply absent -- the same "thinner rather than wrong" choice `lane_display_patterns` already makes for a lane not split out yet. A lock that fails to parse yields an empty map rather than raising, because this feeds a REPORT/refresh, not a gate that must fail loudly on a malformed lock (`check:ci-parity` already owns that)."""
    try:
        data = json.loads((root / GATES_LOCK_REL_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, list):
        return {}
    out: dict[str, tuple[str, str]] = {}
    for gate in data:
        if not isinstance(gate, dict):
            continue
        ci = gate.get("ci")
        if not isinstance(ci, dict) or ci.get("kind") != "step":
            continue
        gate_id, job_id, step_name = gate.get("id"), ci.get("job"), ci.get("step")
        if isinstance(gate_id, str) and isinstance(job_id, str) and isinstance(step_name, str):
            out[gate_id] = (job_id, step_name)
    return out


def _exclusive_ci_steps(root: Path) -> dict[str, tuple[str, str]]:
    """`load_gate_ci_steps`, MINUS any gate id whose `(job, step)` pair is shared by more than one gate id.

    A SHARED PAIR IS A COMPOSITE STEP, and its wall time is the SUM of every gate chained into it, not any one gate's own cost.
    MEASURED 2026-09-28: `ci-quality.yml`'s `quality-i18n` job runs 27 gates' npm scripts through one hand-written `npm run check:i18n` step (its own comment: "composite npm chains with no gate file to carry a header") that measured 36.1s in CI, while five of those 27 ids' OWN standalone local costs (`.ci/cache/gate-durations.json`) were 2-9s each.
    Attributing the WHOLE step's time to each of them would have told every fast one to mark `slow: true`, pulling it out of the default pre-push lane for a cost it does not actually have.
    Six other (job, step) pairs share the same shape (`quality-code`'s `Lint`, `quality-i18n`'s `i18n cross-locale`, `quality-www-build`'s `SEO` and `Redirects`, `quality-content`'s `Dead CSS`, `quality-gate-tests`'s `Quality-gate unit tests`).
    A pair occupied by exactly one gate has no such ambiguity: its own wall time IS that gate's cost, which is the premise `gate_step_seconds` needs to hold.
    """
    all_steps = load_gate_ci_steps(root)
    occupancy: dict[tuple[str, str], int] = {}
    for job_step in all_steps.values():
        occupancy[job_step] = occupancy.get(job_step, 0) + 1
    return {
        gate_id: job_step for gate_id, job_step in all_steps.items() if occupancy[job_step] == 1
    }


def gate_step_seconds(
    root: Path,
    patterns: Mapping[str, re.Pattern[str]],
    jobs_by_run: Sequence[list[dict[str, Any]]],
) -> dict[str, float]:
    """`{gate id: p90 seconds}`, each gate's OWN step (`_exclusive_ci_steps` -- see there for why a step SHARED by several gates is excluded rather than mis-attributed), timed by `completed_at - started_at`, success-only (both the job and the step), over `jobs_by_run` -- the SAME PR-full sample `jobs`/`units`/`job_p90_minutes` already walk, so this costs no extra network call and inherits the same 14-day sample-age refusal `refresh_lane_durations` already applies to that sample.
    `patterns` is `lane_display_patterns`'s own map (already general over every job inside a reusable workflow, not only the seven test lanes), keyed by the job's YAML id -- the same key `ci.job` names.
    A gate whose job has no pattern yet, or whose named step never appears success-only in the sample, contributes no entry -- never a guessed number."""
    samples: dict[str, list[float]] = {}
    for gate_id, (job_id, step_name) in _exclusive_ci_steps(root).items():
        pattern = patterns.get(job_id)
        if pattern is None:
            continue
        for run_jobs in jobs_by_run:
            for job in run_jobs:
                if job.get("conclusion") != "success" or not pattern.match(job.get("name") or ""):
                    continue
                for step in job.get("steps") or []:
                    if step.get("name") != step_name or step.get("conclusion") != "success":
                        continue
                    start = _iso_to_epoch(step.get("started_at"))
                    end = _iso_to_epoch(step.get("completed_at"))
                    if start is not None and end is not None:
                        samples.setdefault(gate_id, []).append(max(0.0, end - start))
    result: dict[str, float] = {}
    for gate_id, secs in samples.items():
        s = stats(secs)
        if s is not None:
            result[gate_id] = s["p90"]
    return result


def prune_gate_steps_to_lock(gate_steps: dict[str, Any], root: Path) -> dict[str, Any]:
    """Drop a gate id no longer eligible for a CI-sourced p90 in the committed lock -- retired, retyped, renamed-step, OR moved into a step now SHARED with another gate (`_exclusive_ci_steps`) -- the same reasoning as `prune_units_to_manifests`: an ADD-only merge would keep a stale, or now-mis-attributed, entry forever."""
    valid = set(_exclusive_ci_steps(root))
    return {gate_id: value for gate_id, value in gate_steps.items() if gate_id in valid}


# `variantCosts`: per-matrix-variant leg pricing, MEASURED from job logs rather than hand-derived (6a94a96a9 derived it by hand from 386 logs of 9 runs, and a `--refresh` that did not write it dropped it, which reds check-lane-budget.ts).
# Shape, read by check-lane-budget.ts's `VariantCost`: `{lane: {variant: {fixedMinutes, legExtraMinutes?: {leg index: minutes}, units: {unit id: ms}}}}`, the variant being the first matrix value in the job's display name ("fedora-43" in "E2E Workers (fedora-43, 1/8)", the same `(<variant>, i/N)` suffix `variantOf` reads). A leg costs fixedMinutes + its legExtraMinutes entry + the sum of its units, each read from the variant's `units` first and the top-level `units` second.
# test-e2e-workers: a unit's cost is its WALL span in the log (its first test's start to the next unit's first test, the last unit to the reporter's `E2E_SKIPPED=` line), not the artifact's summed test durations, which leave out beforeAll/afterAll work. A span whose file the committed shard manifest does not name is a `--also` suite (ct-tests.yml's 12a/12b/12d/13b on leg 1 of the full-integration distros) and goes to that leg's legExtraMinutes. fixedMinutes = job wall - every span: the steps before the runner step, the globalSetup VM reset, the setup after it, and the post steps.
# ops-tutorials (job ops-vm-provision): fixedMinutes = job wall - the run-sequence.sh `TOTAL <n>s` line, the same on every leg, so the variant carries no legExtraMinutes; the tutorials' own costs stay the top-level `tutorial:*` units, so the variant's `units` is empty.
# Every figure is a p90 by linear interpolation over success-only jobs of the same PR-full sample every other section uses.
VARIANT_E2E_LANE = "test-e2e-workers"
VARIANT_OPS_LANE = "ops-tutorials"
# The lane id `check-lane-budget.ts` prices under -> the ci.yml callee job id `lane_display_patterns` keys it by.
VARIANT_LANE_JOBS: dict[str, str] = {
    VARIANT_E2E_LANE: "test-e2e-workers",
    VARIANT_OPS_LANE: "ops-vm-provision",
}
# BOUNDED: 9-10 runs x (40 E2E Workers + 4 OPS Provision legs) is ~440 logs; the cap stops a mis-scoped sample from fetching thousands, and says so when it bites.
VARIANT_LOG_MAX_JOBS = 600
VARIANT_LOG_WORKERS = 8
# The unit-duration artifacts of a 10-run sample are several hundred zips; fetched one after another with no output, a `--refresh` ran past 15 minutes (2026-09-29, interrupted inside download_artifact_zip). The pool matches VARIANT_LOG_WORKERS.
ARTIFACT_DOWNLOAD_WORKERS = 8
# CACHED: a completed job's log never changes, so each is fetched once per machine. Only the lines the derivation reads are kept (a few KB instead of ~200 KB), under the untracked `.ci/cache`.
VARIANT_LOG_CACHE_REL_PATH = ".ci/cache/budget-report/job-logs"

_LEG_SUFFIX_RE = re.compile(r"\(([^,()]+), (\d+)/(\d+)\)$")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_LOG_TS = r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z)"
# `2026-09-28T14:01:24.9305467Z [2026-09-28T14:01:24.061Z]  > test-01 > 01-system-checks.test.ts > <describe> > <test> (0.8s, passed)`: the bracketed stamp is the test's START (the line's own stamp is when it printed, at its end).
_E2E_TEST_LINE_RE = re.compile(
    r"^" + _LOG_TS + r" \[" + _LOG_TS + r"\]\s+> [^>]*?> ([^\s>]+\.test\.ts) > (.*)$"
)
_E2E_END_LINE_RE = re.compile(r"^" + _LOG_TS + r" .*\bE2E_SKIPPED=\d+")
_OPS_TOTAL_LINE_RE = re.compile(r"^" + _LOG_TS + r" TOTAL (\d+)s\s*$")


def job_leg(name: str) -> tuple[str, int] | None:
    """`("fedora-43", 1)` from "... E2E Workers (fedora-43, 1/8)"; None for a job with no `(<variant>, i/N)` suffix -- the same shape check-lane-budget.ts's `variantOf` reads."""
    m = _LEG_SUFFIX_RE.search(name)
    if m is None:
        return None
    return m.group(1).strip(), int(m.group(2))


def filter_variant_log(text: str) -> str:
    """The only lines the variantCosts derivation reads, ANSI-stripped: E2E test lines, the reporter's `E2E_SKIPPED=` line, and run-sequence.sh's `TOTAL <n>s` line. What the cache stores."""
    kept = []
    for raw in text.splitlines():
        line = _ANSI_RE.sub("", raw)
        if (
            _E2E_TEST_LINE_RE.match(line)
            or _E2E_END_LINE_RE.match(line)
            or _OPS_TOTAL_LINE_RE.match(line)
        ):
            kept.append(line)
    return "\n".join(kept) + ("\n" if kept else "")


def parse_e2e_log_spans(
    text: str, bucket_titles: Mapping[str, str] | None = None
) -> dict[str, float] | None:
    """`{unit key: wall ms}` from one E2E Workers log, the key being the test file, or `<file>#<bucket>` when the test's top-level describe title is in `bucket_titles` (the `#partN` split `parse_playwright_unit_ms` makes). A unit's span runs from its first test's start to the next unit's first test's start; the last unit's to the `E2E_SKIPPED=` line. A key that recurs later sums its spans. None when the log has no test line or no end line: a truncated log prices nothing rather than a short last unit."""
    titles = bucket_titles or {}
    segments: list[tuple[str, float]] = []
    end: float | None = None
    for raw in text.splitlines():
        line = _ANSI_RE.sub("", raw)
        m = _E2E_TEST_LINE_RE.match(line)
        if m is not None:
            file, rest = m.group(3), m.group(4)
            bucket = titles.get(rest.split(" > ", 1)[0].strip())
            key = "%s#%s" % (file, bucket) if bucket else file
            if not segments or segments[-1][0] != key:
                start = _iso_to_epoch(m.group(2))
                if start is None:  # pragma: no cover - the regex guarantees a stamp
                    continue
                segments.append((key, start))
            continue
        e = _E2E_END_LINE_RE.match(line)
        if e is not None:
            end = _iso_to_epoch(e.group(1))
    if not segments or end is None:
        return None
    spans: dict[str, float] = {}
    for i, (key, start) in enumerate(segments):
        stop = segments[i + 1][1] if i + 1 < len(segments) else end
        spans[key] = spans.get(key, 0.0) + max(0.0, stop - start) * 1000.0
    return spans


def parse_ops_tutorial_total_seconds(text: str) -> float | None:
    """run-sequence.sh's `TOTAL <n>s` (the sum of the leg's tutorial durations), or None when the log has none."""
    total: float | None = None
    for raw in text.splitlines():
        m = _OPS_TOTAL_LINE_RE.match(_ANSI_RE.sub("", raw))
        if m is not None:
            total = float(m.group(2))
    return total


def e2e_variant_measurement(
    job: dict[str, Any],
    log_text: str,
    manifest_ids: set[str],
    bucket_titles: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    """One E2E Workers leg's `{variant, leg, fixed_minutes, extra_minutes, units: {unit id: ms}}`, or None when its name, wall time or log cannot price it. A span whose `e2e-workers:<key>` id the manifest does not name is an `--also` suite, counted as the leg's extra."""
    leg = job_leg(job.get("name") or "")
    wall = job_wall_minutes(job)
    spans = parse_e2e_log_spans(log_text, bucket_titles)
    if leg is None or wall is None or spans is None:
        return None
    units: dict[str, float] = {}
    extra_ms = 0.0
    for key, ms in spans.items():
        unit_id = "e2e-workers:%s" % key
        if unit_id in manifest_ids:
            units[unit_id] = ms
        else:
            extra_ms += ms
    return {
        "variant": leg[0],
        "leg": leg[1],
        "fixed_minutes": wall - sum(spans.values()) / 60000.0,
        "extra_minutes": extra_ms / 60000.0 if extra_ms > 0 else None,
        "units": units,
    }


def ops_variant_measurement(job: dict[str, Any], log_text: str) -> dict[str, Any] | None:
    """One OPS Provision leg's `{variant, leg, fixed_minutes, extra_minutes, units: {}}`, or None when its name, wall time or `TOTAL` line is missing."""
    leg = job_leg(job.get("name") or "")
    wall = job_wall_minutes(job)
    total = parse_ops_tutorial_total_seconds(log_text)
    if leg is None or wall is None or total is None:
        return None
    return {
        "variant": leg[0],
        "leg": leg[1],
        "fixed_minutes": wall - total / 60.0,
        "extra_minutes": None,
        "units": {},
    }


def aggregate_variant_costs(
    measurements: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """`{lane: [per-leg measurement]}` -> the `variantCosts` shape, each figure the p90 over that variant's legs (minutes to 2 places, units to whole ms). legExtraMinutes carries only the leg indexes that measured an extra."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for lane, rows in measurements.items():
        by_variant: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            by_variant.setdefault(row["variant"], []).append(row)
        lane_out: dict[str, dict[str, Any]] = {}
        for variant, vrows in sorted(by_variant.items()):
            cost: dict[str, Any] = {
                "fixedMinutes": round(_percentile([r["fixed_minutes"] for r in vrows], 90), 2)
            }
            extras: dict[int, list[float]] = {}
            unit_samples: dict[str, list[float]] = {}
            for r in vrows:
                if r.get("extra_minutes"):
                    extras.setdefault(int(r["leg"]), []).append(float(r["extra_minutes"]))
                for unit_id, ms in (r.get("units") or {}).items():
                    unit_samples.setdefault(unit_id, []).append(float(ms))
            if extras:
                cost["legExtraMinutes"] = {
                    str(leg): round(_percentile(vals, 90), 2)
                    for leg, vals in sorted(extras.items())
                }
            cost["units"] = {
                unit_id: round(_percentile(vals, 90))
                for unit_id, vals in sorted(unit_samples.items())
            }
            lane_out[variant] = cost
        if lane_out:
            out[lane] = lane_out
    return out


def fetch_job_log(repo: str, job_id: int) -> str:
    """One job's raw log text through `ghx.gh` (a failed call raises on `.stdout`). `--allow-escape-sequences`: gh 2.98 REFUSES a response carrying terminal escapes without it ("the response contains terminal escape sequences; pass --allow-escape-sequences to output it anyway", measured 2026-09-28 on job 108948938590), and every E2E log carries colour codes."""
    return gh_retry.gh(
        ["api", "--allow-escape-sequences", "repos/%s/actions/jobs/%s/logs" % (repo, job_id)],
        attempts=GH_ATTEMPTS,
    ).stdout


def cached_variant_log(
    repo: str,
    job_id: int,
    cache_dir: Path | None,
    fetch: Callable[[str, int], str] = fetch_job_log,
) -> str:
    """The filtered log for `job_id`, from `cache_dir` when present, else fetched, filtered and cached. A fetch failure raises and caches nothing."""
    cache_file = cache_dir / ("%s.txt" % job_id) if cache_dir is not None else None
    if cache_file is not None:
        try:
            return cache_file.read_text(encoding="utf-8")
        except OSError:
            pass
    filtered = filter_variant_log(fetch(repo, job_id))
    if cache_file is not None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(filtered, encoding="utf-8")
        except OSError as exc:
            log.warn("budget_report: could not cache job %s's log: %s" % (job_id, exc))
    return filtered


def _manifest_unit_ids(root: Path, lane: str) -> set[str]:
    try:
        data = json.loads(
            (root / ".ci" / "config" / "shards" / ("%s.json" % lane)).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return set()
    return {i for leg in data.get("legs", []) for i in leg.get("ids", [])}


def collect_variant_costs(
    repo: str,
    jobs_by_run: Sequence[list[dict[str, Any]]],
    patterns: Mapping[str, re.Pattern[str]],
    root: Path,
    *,
    bucket_titles: Mapping[str, str] | None = None,
    fetch_log: Callable[[str, int], str] = fetch_job_log,
    cache_dir: Path | None = None,
    max_jobs: int = VARIANT_LOG_MAX_JOBS,
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, int]]:
    """`(variantCosts measured from `jobs_by_run`'s success legs, {lane: legs priced})`. A leg whose log cannot be fetched or parsed is skipped with a warning; a lane that prices no leg is simply absent, which `merge_variant_costs` turns into "kept the prior value" rather than a dropped one."""
    manifest_ids = _manifest_unit_ids(root, VARIANT_E2E_LANE)
    candidates: list[tuple[str, dict[str, Any]]] = []
    for lane, job_id in VARIANT_LANE_JOBS.items():
        pattern = patterns.get(job_id)
        if pattern is None:
            log.warn(
                "budget_report: no display pattern for job %r; variantCosts[%r] is not measured"
                % (job_id, lane)
            )
            continue
        for run_jobs in jobs_by_run:
            for job in run_jobs:
                name = job.get("name") or ""
                if job.get("conclusion") == "success" and pattern.match(name) and job_leg(name):
                    candidates.append((lane, job))
    if len(candidates) > max_jobs:
        log.warn(
            "budget_report: %d variant legs in the sample; reading the logs of the first %d only"
            % (len(candidates), max_jobs)
        )
        candidates = candidates[:max_jobs]

    def read(item: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any], str | None]:
        lane, job = item
        try:
            return lane, job, cached_variant_log(repo, job["id"], cache_dir, fetch_log)
        except (ghx.GhError, OSError) as exc:
            log.warn(
                "budget_report: could not read the log of job %s (%s): %s"
                % (job.get("id"), job.get("name"), exc)
            )
            return lane, job, None

    with ThreadPoolExecutor(max_workers=VARIANT_LOG_WORKERS) as pool:
        results = list(pool.map(read, candidates))

    measurements: dict[str, list[dict[str, Any]]] = {}
    unpriced = 0
    for lane, job, text in results:
        if text is None:
            continue
        row = (
            e2e_variant_measurement(job, text, manifest_ids, bucket_titles)
            if lane == VARIANT_E2E_LANE
            else ops_variant_measurement(job, text)
        )
        if row is None:
            unpriced += 1
            continue
        measurements.setdefault(lane, []).append(row)
    if unpriced:
        log.warn(
            "budget_report: %d variant leg log(s) carried no parseable timing; skipped" % unpriced
        )
    return aggregate_variant_costs(measurements), {
        lane: len(rows) for lane, rows in measurements.items()
    }


def merge_variant_costs(
    existing: Mapping[str, Any], computed: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """`(merged variantCosts, [one note per value KEPT from `existing` because this sample did not measure it])`. NEVER A SILENT DROP: a lane, a variant, a leg extra or a unit the sample did not measure keeps its prior value and is named in the notes; a measured one replaces it."""
    merged: dict[str, Any] = {}
    notes: list[str] = []
    for lane in sorted(set(existing) | set(computed)):
        old_lane = existing.get(lane) or {}
        new_lane = computed.get(lane) or {}
        if not new_lane:
            merged[lane] = old_lane
            notes.append(
                "variantCosts[%s]: no leg measured; every variant KEPT from the prior file" % lane
            )
            continue
        lane_out: dict[str, Any] = {}
        for variant in sorted(set(old_lane) | set(new_lane)):
            old = old_lane.get(variant) or {}
            new = new_lane.get(variant)
            if new is None:
                lane_out[variant] = old
                notes.append(
                    "variantCosts[%s][%s]: not measured; KEPT from the prior file" % (lane, variant)
                )
                continue
            cost: dict[str, Any] = {"fixedMinutes": new["fixedMinutes"]}
            extras = {**(old.get("legExtraMinutes") or {}), **(new.get("legExtraMinutes") or {})}
            notes.extend(
                "variantCosts[%s][%s].legExtraMinutes[%s]: not measured; KEPT %s from the prior file"
                % (lane, variant, leg, extras[leg])
                for leg in sorted(
                    set(old.get("legExtraMinutes") or {}) - set(new.get("legExtraMinutes") or {})
                )
            )
            if extras:
                cost["legExtraMinutes"] = dict(sorted(extras.items()))
            old_units = old.get("units") or {}
            new_units = new.get("units") or {}
            kept_units = sorted(set(old_units) - set(new_units))
            if kept_units:
                notes.append(
                    "variantCosts[%s][%s]: %d unit(s) not measured, KEPT from the prior file: %s"
                    % (lane, variant, len(kept_units), ", ".join(kept_units))
                )
            cost["units"] = dict(sorted({**old_units, **new_units}.items()))
            lane_out[variant] = cost
        merged[lane] = lane_out
    return merged, notes


# T3.2: assembling `.ci/config/lane-durations.json`'s three measured sections.


def main_push_only_p90(
    pr_jobs_by_run: list[list[dict[str, Any]]],
    main_jobs_by_run: list[list[dict[str, Any]]],
) -> dict[str, float]:
    """`{display name: p90 wall MINUTES}` for every job that ran successfully in a main-push run and RAN in no sampled PR run (skipped or absent there, `_ran`).

    WHY. `job_p90_minutes` is built from the PR-full sample, and the release chain (`Check Release State`, `Finalize Release Sentinel`, `Pipeline Sentinel`, `Build (Devcontainer) / Devcontainer Manifest`) is skipped on every PR by its own `if:`, so check-lane-budget.ts check 2 reported those four UNCHECKED forever (operator ruling on #5a954657: unknown is red). They are measured where they run. A job that RAN on a PR, whatever its conclusion, is the PR sample's to measure -- even with no success sample -- so this never substitutes a main-push number for a PR job, and the PR measurement is unchanged. Success-only walls (`job_wall_minutes`), the same basis as the PR sample. Pure, so a test can drive it without the network.
    """
    ran_on_pr = {
        job.get("name") or "?" for run_jobs in pr_jobs_by_run for job in run_jobs if _ran(job)
    }
    walls: dict[str, list[float]] = {}
    for run_jobs in main_jobs_by_run:
        for job in run_jobs:
            name = job.get("name") or "?"
            if name in ran_on_pr:
                continue
            wall = job_wall_minutes(job)
            if wall is not None:
                walls.setdefault(name, []).append(wall)
    out: dict[str, float] = {}
    for name, values in walls.items():
        s = stats(values)
        if s is not None:
            out[name] = s["p90"]
    return out


def compute_lane_durations(
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    branch: str = DEFAULT_BRANCH,
    limit: int = DEFAULT_REFRESH_LIMIT,
    *,
    root: Path | None = None,
    list_artifacts: Callable[[str, int], list[dict[str, Any]]] = fetch_artifacts,
    download: Callable[[str, Any], bytes] = download_artifact_zip,
    fetch_log: Callable[[str, int], str] = fetch_job_log,
    log_cache_dir: Path | None = None,
) -> dict[str, Any]:
    """The FRESH numbers `--refresh` writes and `--check` compares against: `{"jobs", "units", "job_max_seconds", "job_p90_minutes", "gate_step_p90_seconds", "variant_costs", "variant_legs", "unit_parallelism", "missing_artifact_lanes"}`. `fetch_log`/`log_cache_dir` feed `collect_variant_costs` (the cache defaults to `VARIANT_LOG_CACHE_REL_PATH` under the repo root). Never touches `refreshed_at` or `concurrency` -- the caller's job, since `--check` must compute this WITHOUT stamping anything."""
    tree_root = root if root is not None else paths.repo_root()

    # THE PR SAMPLE HONOURS `--branch`, AS THE REPORT'S DOES SINCE 34ac34c13. `--refresh --branch 0923-1` still sampled PR runs with NO branch filter, so the durations it wrote came from whichever branches' runs the listing served, not the branch named. `class_branch_filter` keeps a default-branch refresh repo-wide.
    pr_runs = fetch_runs(
        repo,
        workflow,
        "pull_request",
        class_branch_filter("pr-full", branch),
        REFRESH_PR_STATUS,
        limit,
    )
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
    variant_costs, variant_legs = collect_variant_costs(
        repo,
        pr_jobs_by_run,
        patterns,
        tree_root,
        bucket_titles=bucket_titles,
        fetch_log=fetch_log,
        cache_dir=log_cache_dir
        if log_cache_dir is not None
        else tree_root / VARIANT_LOG_CACHE_REL_PATH,
    )
    units_ms: dict[str, float] = {}
    unit_stats: dict[str, dict[str, float]] = {}
    for per_unit in unit_samples.values():
        for unit_id, ms_list in per_unit.items():
            s = stats(ms_list)
            if s is not None:
                units_ms[unit_id] = s["p90"]
                unit_stats[unit_id] = s

    # THE HEADROOM SAMPLE IS ALWAYS THE DEFAULT BRANCH: `ci.yml` runs on `push` to `main` only, so a `--branch` naming a PR branch would sample zero push runs and leave `job_max_seconds` unmeasured.
    main_runs = fetch_runs(repo, workflow, "push", DEFAULT_BRANCH, DEFAULT_STATUS, limit)
    main_jobs_by_run = [fetch_jobs(repo, run["id"]) for run in main_runs]
    # A job that never runs on a PR (the release chain) takes its p90 from the SAME main-push sample; a job the PR sample ran keeps its PR number, untouched. See `main_push_only_p90`.
    main_only = main_push_only_p90(pr_jobs_by_run, main_jobs_by_run)
    for name in sorted(main_only):
        log.info(
            "budget_report: job_p90_minutes %r = %.1f from %d main-push run(s) (it ran in no sampled PR run)"
            % (name, main_only[name], len(main_runs))
        )
    job_p90_minutes.update(main_only)
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
        # The spread behind each unit's p90 (median/max/n), read by `--check` only and never written: see `UNIT_SLOWER_STAT`.
        "unit_stats": unit_stats,
        "job_max_seconds": job_max_seconds,
        "job_p90_minutes": job_p90_minutes,
        # CI-representative gate-step timing for check-gate-manifest.ts's tier verdict; see gate_step_seconds.
        "gate_step_p90_seconds": gate_step_seconds(tree_root, patterns, pr_jobs_by_run),
        # Per-matrix-variant leg pricing measured from the same sample's job logs; see `collect_variant_costs`.
        "variant_costs": variant_costs,
        "variant_legs": variant_legs,
        "missing_artifact_lanes": missing_lanes,
        # Derived from the runner label, not sampled; see derive_unit_parallelism.
        "unit_parallelism": derive_unit_parallelism(tree_root, workflow),
        # T3.1: the PR sample's own age findings, carried out so `--refresh` can REFUSE to stamp a fresh `refreshed_at` on them (see refresh_lane_durations).
        "stale_sample": stale_sample_findings(pr_runs),
        # Which PR runs the numbers came from, so a refresh names its sample rather than only its size.
        "sampled_runs": [_run_summary(run) for run in pr_runs],
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


# Unit-id prefix -> lane, for `unit_drift_findings`' per-lane sum. UNIT_PREFIX_MANIFEST names only the lanes with a shard manifest; battery and tutorial units are priced too, so they are named here.
UNIT_PREFIX_LANE = {"battery": "quality-gate-tests", "tutorial": "ops-tutorials"}


def unit_lane(unit_id: str) -> str:
    """The lane a unit id belongs to, from its prefix (a bare id is a Go import path of test-renet-go). An unknown prefix is its own group, never dropped."""
    prefix = unit_id.split(":", 1)[0] if ":" in unit_id else ""
    return UNIT_PREFIX_MANIFEST.get(prefix) or UNIT_PREFIX_LANE.get(prefix) or prefix


def unit_drift_findings(
    committed_units: Mapping[str, float],
    measured_units: Mapping[str, float],
    measured_stats: Mapping[str, Mapping[str, float]] | None = None,
) -> tuple[list[str], int]:
    """`(findings, lanes compared)` for T3.3's drift trigger on `units`, two ways, each needing BOTH the 25% ratio AND a `MIN_UNIT_DRIFT_MS` absolute move:

    - PER UNIT: one unit whose typical run moved enough to unbalance its leg (a 160 s spec doubling). Judged on the measured sample's spread, not its p90 alone: slower needs the MEDIAN past the committed p90, faster needs the MAX under it (see `UNIT_SLOWER_STAT`). `measured_stats` maps a unit id to `stats()`' dict; a unit with none is judged on its p90 both ways.
    - PER LANE: the SUM of a lane's unit p90s, over the ids both sides price. The backstop for the hole the floor opens: a lane-wide slowdown made of units that each move under 5 s passes unit by unit, and the sum still reds once it moves the lane by 25%. MEASURED 2026-10-05: units under 5 s are at most 10% of any lane's sum except battery's 9 s, so sub-floor noise cannot carry a lane past 25% on its own, and over the last 20 refreshes no same-day refresh moved a lane sum by more than 3.4%.

    Pure, so the selftest-style tests drive it without the network.
    """
    findings: list[str] = []
    committed_sum: dict[str, float] = {}
    measured_sum: dict[str, float] = {}
    stats_by_unit = measured_stats or {}
    for unit_id, ms in sorted(measured_units.items()):
        was = committed_units.get(unit_id)
        if was is None or ms is None:
            continue
        lane = unit_lane(unit_id)
        committed_sum[lane] = committed_sum.get(lane, 0.0) + was
        measured_sum[lane] = measured_sum.get(lane, 0.0) + ms
        f = _unit_spread_finding(unit_id, was, ms, stats_by_unit.get(unit_id) or {})
        if f:
            findings.append(f)
    for lane in sorted(committed_sum):
        was, ms = committed_sum[lane], measured_sum[lane]
        if abs(ms - was) < MIN_UNIT_DRIFT_MS:
            continue
        d = drift_finding("lane %r summed unit p90" % lane, was, ms)
        if d:
            findings.append(d)
    return findings, len(committed_sum)


def _unit_spread_finding(
    unit_id: str, was: float, p90: float, unit_stats: Mapping[str, float]
) -> str | None:
    """One unit's drift under `UNIT_SLOWER_STAT`/`UNIT_FASTER_STAT`, or None."""
    label = "unit %r p90" % unit_id
    if was == 0:
        return drift_finding(label, was, p90) if abs(p90) >= MIN_UNIT_DRIFT_MS else None
    typical = unit_stats.get(UNIT_SLOWER_STAT, p90)
    slowest = unit_stats.get(UNIT_FASTER_STAT, p90)
    n = unit_stats.get("n")
    sample = "" if n is None else " of %d sample(s)" % n
    if typical - was >= MIN_UNIT_DRIFT_MS and (typical - was) / was > DRIFT_THRESHOLD:
        return (
            "%s: committed %.4g, and the measured %s%s is %.4g, %.0f%% slower (over the %.0f%% limit; measured p90 %.4g)."
            % (
                label,
                was,
                UNIT_SLOWER_STAT,
                sample,
                typical,
                (typical - was) / was * 100,
                DRIFT_THRESHOLD * 100,
                p90,
            )
        )
    if was - slowest >= MIN_UNIT_DRIFT_MS and (was - slowest) / was > DRIFT_THRESHOLD:
        return (
            "%s: committed %.4g, and the measured %s%s is %.4g, %.0f%% faster (over the %.0f%% limit; measured p90 %.4g)."
            % (
                label,
                was,
                UNIT_FASTER_STAT,
                sample,
                slowest,
                (was - slowest) / was * 100,
                DRIFT_THRESHOLD * 100,
                p90,
            )
        )
    return None


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
    """T3.2: rewrite `path` from `limit` completed PR-full runs (success-only jobs; see REFRESH_PR_STATUS). `concurrency`, `$comment` and `defaultUnitMs` are PRESERVED verbatim -- this never guesses the operator's D-W1 ruling or hand-authored fallbacks; only `jobs`, `units`, `variantCosts` (measured from job logs, merged so an unmeasured entry keeps its prior value, named on stderr), `job_max_seconds`, `job_p90_minutes`, `gate_step_p90_seconds`, `unitParallelism` (derived from the runner label, prior value kept when underivable) and `refreshed_at` move. `--dry-run` computes and prints without writing, the one network call this box's own instructions permit running for real."""
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}

    computed = compute(repo, workflow, branch, limit)
    # A STALE SAMPLE IS REFUSED HERE, NOT WARNED. MEASURED 2026-09-28: one `--refresh` drew a sample whose Quality / Security p90 read 9.9m (1.8m the minute before) and whose lanes all had NO unit-duration artifacts, then stamped `refreshed_at` = now over it. check-lane-budget.ts's check 5 reads that stamp as "measured today", so a fresh stamp on old runs silently defeats it. A report may warn and carry on; the one writer of the stamp may not.
    for run in computed.get("sampled_runs") or []:
        print(
            "budget_report --refresh: sampled run %s (%s, %s, %s)"
            % (run.get("id"), run.get("created_at"), run.get("head_branch"), run.get("conclusion")),
            file=sys.stderr,
        )
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
        and not computed["gate_step_p90_seconds"]
        and not computed.get("variant_costs")
    ):
        log.error(
            "budget_report --refresh: matched nothing at all across %d sampled run(s); "
            "refusing to stamp refreshed_at on numbers nothing verified." % limit
        )
        return 1

    # .ci/config/lane-durations.json -> the repo root, three levels up, so a fixture path prunes against its own tree.
    repo_root_for_pruning = path.resolve().parent.parent.parent

    updated: dict[str, Any] = {}
    if "$comment" in existing:
        updated["$comment"] = existing["$comment"]
    updated["refreshed_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated["concurrency"] = existing.get("concurrency", 20)
    updated["jobs"] = {**existing.get("jobs", {}), **computed["jobs"]}
    updated["units"] = prune_units_to_manifests(
        {**existing.get("units", {}), **computed["units"]}, repo_root_for_pruning
    )
    if "defaultUnitMs" in existing:
        updated["defaultUnitMs"] = existing["defaultUnitMs"]
    # How many units a lane's leg runs at once (quality-pytest's `-n`) is DERIVED from the runner label (see the module docstring's UNIT PARALLELISM). A lane this refresh could not derive keeps its prior value and is named: dropping it would silently turn a parallel lane back into a serial estimate.
    parallelism = dict(existing.get("unitParallelism") or {})
    derived_parallelism = computed.get("unit_parallelism") or {}
    for lane, workers in sorted(derived_parallelism.items()):
        print(
            "budget_report --refresh: unitParallelism[%s] = %d derived from the runner label's vCPU count"
            % (lane, workers),
            file=sys.stderr,
        )
    parallelism.update(derived_parallelism)
    for lane in sorted(set(parallelism) - set(derived_parallelism)):
        log.warn(
            "budget_report --refresh: unitParallelism[%s] not derivable from the runner label; KEPT %r from the prior file"
            % (lane, parallelism[lane])
        )
    if parallelism:
        updated["unitParallelism"] = parallelism
    # The declared placement rules `check-lane-budget.ts --rebalance` honours (18/19 on one leg, backup-restore on OPS shard 3), hand-authored and preserved the same way; dropping them would let a rebalance write a plan the runner cannot run.
    if "rebalanceConstraints" in existing:
        updated["rebalanceConstraints"] = existing["rebalanceConstraints"]
    # variantCosts is MEASURED (collect_variant_costs) and merged so nothing the sample missed is dropped: an unmeasured lane, variant, leg extra or unit keeps its prior value, and every such keep is printed.
    variant_costs, variant_notes = merge_variant_costs(
        existing.get("variantCosts") or {}, computed.get("variant_costs") or {}
    )
    for note in variant_notes:
        log.warn("budget_report --refresh: %s" % note)
    for lane, legs in sorted((computed.get("variant_legs") or {}).items()):
        print(
            "budget_report --refresh: variantCosts[%s] measured from %d leg log(s)" % (lane, legs),
            file=sys.stderr,
        )
    if variant_costs:
        updated["variantCosts"] = {
            lane: {
                variant: {
                    **cost,
                    "units": prune_units_to_manifests(
                        cost.get("units") or {}, repo_root_for_pruning
                    ),
                }
                for variant, cost in variants.items()
            }
            for lane, variants in variant_costs.items()
        }
    updated["job_p90_minutes"] = {
        **existing.get("job_p90_minutes", {}),
        **computed["job_p90_minutes"],
    }
    updated["gate_step_p90_seconds"] = prune_gate_steps_to_lock(
        {**existing.get("gate_step_p90_seconds", {}), **computed["gate_step_p90_seconds"]},
        repo_root_for_pruning,
    )
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
        "%d headroom job(s), %d other job p90(s), %d gate step p90(s)."
        % (
            limit,
            len(computed["jobs"]),
            len(computed["units"]),
            len(computed["job_max_seconds"]),
            len(computed["job_p90_minutes"]),
            len(computed["gate_step_p90_seconds"]),
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

    unit_findings, unit_lanes = unit_drift_findings(
        committed.get("units") or {}, computed["units"], computed.get("unit_stats")
    )
    findings.extend(unit_findings)

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
        "CI time budget check: %d job lane(s), %d unit(s) in %d unit lane sum(s), %d headroom job(s) sampled "
        "from %d run(s), all within budget and within %.0f%% of committed (unit moves under %.0f s ignored; a unit reds slower on its %s, faster on its %s)."
        % (
            len(computed["jobs"]),
            len(computed["units"]),
            unit_lanes,
            len(computed["job_max_seconds"]),
            limit,
            DRIFT_THRESHOLD * 100,
            MIN_UNIT_DRIFT_MS / 1000,
            UNIT_SLOWER_STAT,
            UNIT_FASTER_STAT,
        )
    )
    return 0


# Assembling the report.


def class_branch_filter(run_class: str, branch: str) -> str | None:
    """The `branch=` filter one run class is sampled with, given the report's `--branch`.

    MEASURED 2026-09-28: `--branch 0923-1 --limit 10 --status completed` printed a `pr-full` table with no E2E job at all, because `pr-full` was sampled with NO branch (only `main-push` got one) and so drew ten other branches' runs from August (13 over-age warnings). A PR run's `head_branch` IS its PR branch, so a `--branch` naming a PR branch scopes `pr-full` to it. `--branch` left at the default branch keeps `pr-full` repo-wide (no PR is ever opened FROM `main`), and `schedule` is never branch-filtered: the nightly only ever runs on the default branch, whatever `--branch` names."""
    if run_class == "main-push":
        return branch
    if run_class == "pr-full" and branch != DEFAULT_BRANCH:
        return branch
    return None


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    """The identity of one sampled run, so the report says WHICH runs it measured, not only how many."""
    return {
        key: run.get(key)
        for key in ("id", "created_at", "head_branch", "event", "conclusion", "run_attempt")
    }


def collect_class(
    repo: str, workflow: str, event: str, branch: str | None, status: str, limit: int
) -> dict[str, Any]:
    """One run class's full measurement: the sampled runs themselves, per-job stats, queue, runner-minutes, peak concurrency."""
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
        "branch_filter": branch,
        "runs": [_run_summary(run) for run in runs],
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
        data = collect_class(
            repo, workflow, event, class_branch_filter(run_class, branch), status, limit
        )
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
        lines.append("Branch filter: `%s`" % (data.get("branch_filter") or "(any)"))
        sampled = data.get("runs") or []
        if sampled:
            lines.append(
                "Runs: %s"
                % ", ".join(
                    "%s (%s, %s)"
                    % (r.get("id"), (r.get("created_at") or "?")[:10], r.get("conclusion"))
                    for r in sampled
                )
            )
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
        # tree-write: safe only with an explicit --markdown-out, which check:ci-budget-freshness never passes
        args.markdown_out.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        # tree-write: safe only with an explicit --json-out, which check:ci-budget-freshness never passes
        args.json_out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

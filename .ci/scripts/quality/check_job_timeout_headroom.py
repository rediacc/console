#!/usr/bin/env python3
"""A long-running CI job must keep real headroom under its own timeout-minutes.

WHY THIS EXISTS. On 2026-08-07 `Validate Promotion` hit `timeout-minutes: 30` at 30m13s and the 0804-1 release did not ship. The chain is worth stating, because no part of it says the word "timeout":

    job exceeds timeout-minutes
      -> GitHub marks its conclusion `cancelled` (NOT `failure`)
      -> assert-ci-complete.sh forgives `skipped` but not `cancelled`
      -> `CI Complete` fails, `Pipeline Sentinel` fails
      -> finalize never dispatches cd-v2.yml
      -> NO RELEASE RUN IS EVER CREATED

The job log's only clue is `The operation was canceled.` The fix was to raise the number by hand, and by itself a raised number protects nothing: the job had already timed out once on 2026-07-28, and the ceiling was approached silently
for weeks -- 21m57s, 27m20s, CANCELLED 31m03s, 28m35s, 24m09s, 24m56s, 24m01s,
CANCELLED 30m51s. Nothing was watching the MARGIN, only pass/fail.

WHAT IT CHECKS. For every job named in `.ci/config/lane-durations.json`'s `job_max_seconds.jobs`, the workflow's declared `timeout-minutes` must exceed the observed worst case by MIN_HEADROOM. It fails when a timeout is lowered, when a job silently loses its `timeout-minutes`, when a baseline job is renamed out of the workflow, and -- after a `--refresh` -- when real durations have crept toward the ceiling.

WHY A COMMITTED BASELINE INSTEAD OF A LIVE QUERY. `npm run ci` must work offline and deterministically, so the gate reads committed numbers only. The network lives in `--refresh`, which rewrites the baseline from the Actions API. That split is deliberate: a gate that needs a token is a gate that silently degrades to "passed" on the machine that lacks one.

WHAT IT DOES NOT DO. It does not predict duration, and it cannot: promotion cost scales with the `edge` channel, which grows with every release. It only asserts that the margin between measured reality and the declared ceiling has not closed. Catching the creep still requires refreshing the baseline; the `stale baseline` check below is what stops that from being forgotten quietly.

RETIRED INTO `.ci/config/lane-durations.json` (D-W2/T3.4, `agent/plans/PLAN-ci-time-budget.md`). `job-timeout-baseline.json` used to hold this gate's ONLY baseline; it is gone, folded into that file's `job_max_seconds` section, `{"refreshed_at": ..., "jobs": {name: {"observed_max_seconds", "samples"}}}` -- the exact shape `verdicts()`/`controls()` already expected, so neither changed. `job_max_seconds` carries its OWN `refreshed_at`, separate from the file's top-level one: `budget_report.py --refresh` (T3.2) stamps the top-level field for `jobs`/`units`, this script's OWN `--refresh` stamps `job_max_seconds.refreshed_at`, and a shared single timestamp would let either refresh silently un-stale the other half.

D-W2: THE LANE BUDGET SUPERSEDES THIS RULE FOR BUDGETED JOBS (2026-09-30). `scripts/gates/check-lane-budget.ts` budgets every job of ci.yml and its callees: its check 2 holds the measured p90 at 12 minutes (or a ruled cap) and its check 7 holds `timeout-minutes` at 15 (or the ruled timeout), which leaves no room for a 1.5x margin over the worst case and makes the two rules contradict. A baseline job whose display name that graph reaches (`lane_budgeted_names`) is printed as superseded and not judged here; a baseline job outside it (a workflow ci.yml does not call) keeps the 1.5x rule and the freshness check. `Validate Promotion` and `Stage Artifacts`, the two jobs the baseline names today, are both inside it.

---- gate ----
step: CI job timeout headroom
needs: none
id: check:ci-timeout-headroom
selftest: true
---- end gate ----
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

# A job must be allowed to take at least this multiple of its observed worst
# case before the timeout fires. 1.5 is not arbitrary: Validate Promotion's
# 28m35s worst case under a 30m ceiling was a ratio of 1.05, and it blew up twice. At 1.5 that ceiling would have had to be 43m, which would have carried both timeouts.
MIN_HEADROOM = 1.5

# A baseline nobody refreshes stops describing reality. Loud, not silent. Tightened from 45 to 14 by D-W2 (PLAN-ci-time-budget): the file this baseline now lives in, `.ci/config/lane-durations.json`, is also `scripts/gates/check-lane-budget.ts`'s own `MAX_STALENESS_DAYS`, and one committed file keeps one freshness discipline even though `job_max_seconds` carries its own separate `refreshed_at` field.
MAX_BASELINE_AGE_DAYS = 14

# Vacuity floor. An empty baseline makes every comparison vacuous and the gate would exit 0 reading exactly like full coverage.
MIN_BASELINE_JOBS = 2

WORKFLOW = ".github/workflows/ci.yml"
# D-W2/T3.4: retired from its own `job-timeout-baseline.json` into this shared file's `job_max_seconds` section (see the module docstring).
LANE_DURATIONS_REL_PATH = ".ci/config/lane-durations.json"


class WorkflowUnreadableError(Exception):
    """The workflow could not be parsed, so no verdict is possible."""


def job_timeouts(root):
    """Map a job's display `name:` to its `timeout-minutes`, across ALL workflows.

    EVERY workflow file, not just ci.yml, because a caller job that `uses:` a reusable workflow cannot carry `timeout-minutes` at all -- GitHub rejects it there, and the real ceiling lives on the job inside the called file. Reading only ci.yml made this gate accuse `Stage Artifacts` of having lost its timeout when the truth was worse and different: it never had one anywhere, in
    either file. A checker that cannot see where the answer lives will confidently give the wrong reason.

    Deliberately regex-based rather than yaml.safe_load: the shape being read is two fixed keys at one indentation level, and this keeps the gate free of a PyYAML dependency. A parse that finds nothing raises rather than returning
    {} -- an empty map would make every downstream comparison vacuous.
    """
    found = {}
    files = sorted((root / ".github/workflows").glob("*.yml"))
    for path in files:
        name = None
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^    name:\s*(.+?)\s*$", line)
            if m:
                name = m.group(1).strip("\"'")
                continue
            m = re.match(r"^    timeout-minutes:\s*(\d+)\s*$", line)
            if m and name:
                # Lowest wins: whichever ceiling fires first is the real one.
                found[name] = min(int(m.group(1)), found.get(name, 1 << 30))
    if not found:
        raise WorkflowUnreadableError(
            "parsed 0 job name/timeout-minutes pairs out of %d workflow file(s) -- "
            "they moved, were reformatted, or the indentation assumption is wrong. "
            "Refusing a verdict rather than reporting that every job is fine." % len(files)
        )
    return found


def lane_budgeted_names(root):
    """Every job display name `scripts/gates/check-lane-budget.ts` budgets: each job of ci.yml and, transitively, of every reusable workflow it calls (`uses: ./.github/workflows/<file>`), by its `name:` (its id when it has none).

    D-W2 (PLAN-ci-time-budget, Operator rulings): for a budgeted job the lane gate SUPERSEDES the 1.5x headroom rule. That gate walks exactly this graph for its check 2 (measured p90 at 12 minutes or its ruled cap) and check 7 (timeout-minutes at 15 or its ruled cap), so a job it reaches is judged there and skipped here. The walk mirrors its `workflowJobs` parse: jobs at two spaces, `name:`/`uses:` at four. A ci.yml that parses to no job raises, because an empty set would silently put every baseline job back under this gate and hide a broken reader.
    """
    names = set()
    seen = set()

    def walk(rel):
        if rel in seen:
            return
        seen.add(rel)
        path = root / rel
        if not path.is_file():
            return
        in_jobs = False
        current = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"^jobs:\s*$", line):
                in_jobs = True
                continue
            if not in_jobs:
                continue
            if line and not line[0].isspace() and not line.startswith("#"):
                break
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                if current is not None:
                    names.add(current["name"] or current["id"])
                current = {"id": m.group(1), "name": None}
                continue
            if current is None:
                continue
            m = re.match(r"^    name:\s*(.+?)\s*$", line)
            if m:
                current["name"] = m.group(1).strip("\"'")
                continue
            m = re.match(r"^    uses:\s*\./(\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml)", line)
            if m:
                walk(m.group(1))
        if current is not None:
            names.add(current["name"] or current["id"])

    walk(WORKFLOW)
    if not names:
        raise WorkflowUnreadableError(
            "%s parsed to zero jobs, so which jobs check:ci-lane-budget covers cannot be "
            "told; refusing to hand every baseline job back to this gate on an empty read"
            % WORKFLOW
        )
    return names


def split_budgeted(baseline_jobs, budgeted):
    """(judged here, superseded by the lane budget): D-W2's partition of the baseline. Pure, so the controls can drive it."""
    judged = {k: v for k, v in baseline_jobs.items() if k not in budgeted}
    superseded = sorted(k for k in baseline_jobs if k in budgeted)
    return judged, superseded


def verdicts(baseline_jobs, timeouts):
    """Every complaint about this baseline. Pure, so the controls can drive it."""
    out = []
    for job, rec in sorted(baseline_jobs.items()):
        observed = rec["observed_max_seconds"]
        limit = timeouts.get(job)
        if limit is None:
            out.append(
                "%s: no `timeout-minutes` found for this job in %s. Either it was "
                "renamed (update the baseline key) or it has NO ceiling anywhere -- "
                "note a job that `uses:` a reusable workflow cannot carry "
                "timeout-minutes itself, so check the CALLED file too. With none, "
                "it runs to GitHub's 360-minute default." % (job, "any workflow")
            )
            continue
        needed = observed * MIN_HEADROOM
        if limit * 60 < needed:
            out.append(
                "%s: timeout-minutes=%d (%ds) but observed worst case is %ds, so the "
                "margin is %.2fx and the floor is %.2fx. Raise it to at least %d "
                "minutes, or make the job cheaper. A job that overruns is reported "
                "as `cancelled`, which assert-ci-complete.sh does NOT forgive, so "
                "this blocks the release rather than just failing a check."
                % (
                    job,
                    limit,
                    limit * 60,
                    observed,
                    (limit * 60) / observed,
                    MIN_HEADROOM,
                    -(-int(needed) // 60),
                )
            )
    return out


def controls(timeouts):
    """Prove the detector can fire, in BOTH directions, before any real read.

    A one-directional control is satisfiable by a broken checker: one that always complains passes the positive control, one that never complains passes the negative. Refusing a verdict when the instrument cannot be demonstrated is the whole point -- this gate exists because something ran for weeks while reporting nothing.
    """
    probe_job, probe_limit = next(iter(sorted(timeouts.items())))
    tight = {probe_job: {"observed_max_seconds": probe_limit * 60}}  # ratio 1.0
    if not verdicts(tight, timeouts):
        return "planted a job at exactly 1.00x headroom and the detector stayed silent"
    roomy = {probe_job: {"observed_max_seconds": int(probe_limit * 60 / (MIN_HEADROOM * 4))}}
    if verdicts(roomy, timeouts):
        return "planted a job with 4x the required headroom and the detector complained anyway"
    missing = {"a job name that is not in the workflow": {"observed_max_seconds": 1}}
    if not verdicts(missing, timeouts):
        return "planted a baseline job absent from the workflow and the detector stayed silent"
    # D-W2 in both directions: a budgeted job leaves this gate, a non-budgeted one stays under it.
    rec = {"observed_max_seconds": 1}
    judged, superseded = split_budgeted({"budgeted": rec, "not budgeted": rec}, {"budgeted"})
    if superseded != ["budgeted"] or list(judged) != ["not budgeted"]:
        return "the D-W2 split did not move exactly the lane-budgeted job out of this gate"
    return None


def refresh(root, lane_durations_path, limit):
    """Rewrite `job_max_seconds.jobs[*].observed_max_seconds` from the Actions API. Network lives HERE.

    Reads and rewrites the WHOLE `.ci/config/lane-durations.json`, but touches only its `job_max_seconds` section -- `budget_report.py --refresh`'s own `jobs`/`units`/`concurrency`/`$comment`/`defaultUnitMs` pass through unchanged, and `job_max_seconds` keeps its OWN `refreshed_at` rather than the file's top-level one (see the module docstring's "RETIRED INTO" section for why the two must stay independent).
    """
    runs = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            "rediacc/console",
            "--branch",
            "main",
            "--workflow",
            "Console CI",
            "--event",
            "push",
            "--limit",
            str(limit),
            "--json",
            "databaseId",
            "--jq",
            ".[].databaseId",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    ids = [x for x in runs.stdout.split() if x.isdigit()]
    if not ids:
        print("refresh found no main push runs; baseline untouched", file=sys.stderr)
        return 1
    data = json.loads(lane_durations_path.read_text(encoding="utf-8"))
    section = data.get("job_max_seconds")
    if not isinstance(section, dict):
        section = {"refreshed_at": None, "jobs": {}}
    baseline_jobs = section.get("jobs")
    if not isinstance(baseline_jobs, dict):
        baseline_jobs = {}
    seen = {}
    for run_id in ids:
        out = subprocess.run(
            [
                "gh",
                "api",
                "repos/rediacc/console/actions/runs/%s/jobs?per_page=100" % run_id,
                "--jq",
                '.jobs[]|select(.conclusion=="success")|"\\(.name)\\t\\(.started_at)\\t\\(.completed_at)"',
            ],
            capture_output=True,
            text=True,
            cwd=str(root),
            check=False,
        )
        for line in out.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            name, start, end = parts
            try:
                secs = int(
                    (
                        dt.datetime.fromisoformat(end) - dt.datetime.fromisoformat(start)
                    ).total_seconds()
                )
            except ValueError:
                continue
            # A job called through a REUSABLE workflow is reported by the API as "<caller job name> / <called job name>", while the workflow files know it by the bare name. Record every alias, or the baseline key silently never matches and the refresh leaves a stale number behind while reporting success -- which is exactly what happened the first time this ran.
            for alias in {name, name.split(" / ")[-1], name.split(" / ")[0]}:
                if secs > seen.get(alias, 0):
                    seen[alias] = secs
    updated = 0
    for name, rec in baseline_jobs.items():
        if name in seen and seen[name] > 0:
            rec["observed_max_seconds"] = seen[name]
            rec["samples"] = len(ids)
            # The old note described the old number; keeping it would leave a comment that contradicts the value directly beneath it.
            rec.pop("observed_note", None)
            updated += 1
        else:
            print(
                "  WARNING: %r matched no job in the sampled runs; its number is "
                "UNCHANGED and may be stale" % name,
                file=sys.stderr,
            )
    if not updated:
        print(
            "refresh matched NONE of the baseline jobs; refusing to stamp "
            "refreshed_at on numbers nothing verified",
            file=sys.stderr,
        )
        return 1
    section["jobs"] = baseline_jobs
    section["refreshed_at"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["job_max_seconds"] = section
    lane_durations_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("baseline refreshed from %d run(s); %d job duration(s) observed" % (len(ids), len(seen)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--refresh", action="store_true", help="rewrite the baseline from the Actions API (network)"
    )
    ap.add_argument(
        "--runs", type=int, default=8, help="how many main push runs to sample when refreshing"
    )
    args = ap.parse_args(argv)

    root = pathlib.Path(__file__).resolve().parents[3]
    lane_durations_path = root / LANE_DURATIONS_REL_PATH
    workflow_path = root / WORKFLOW

    if not lane_durations_path.is_file() or not workflow_path.is_file():
        print(
            "VACUOUS INPUT: baseline or workflow missing, so nothing can be compared",
            file=sys.stderr,
        )
        return 1

    if args.refresh:
        return refresh(root, lane_durations_path, args.runs)

    lane_durations = json.loads(lane_durations_path.read_text(encoding="utf-8"))
    section = lane_durations.get("job_max_seconds")
    baseline = section if isinstance(section, dict) else {}
    jobs = baseline.get("jobs", {})
    if len(jobs) < MIN_BASELINE_JOBS:
        print(
            "VACUOUS INPUT: baseline names %d job(s), expected at least %d. A headroom\n"
            "check over an empty baseline exits 0 and reads exactly like full coverage."
            % (len(jobs), MIN_BASELINE_JOBS),
            file=sys.stderr,
        )
        return 1

    try:
        timeouts = job_timeouts(root)
        budgeted = lane_budgeted_names(root)
    except WorkflowUnreadableError as exc:
        print("CANNOT READ THE WORKFLOWS, so no verdict is possible:\n  %s" % exc, file=sys.stderr)
        return 1

    broken = controls(timeouts)
    if broken:
        print(
            "CONTROL FAILED, so nothing below is meaningful: %s.\n"
            "  This gate refuses a verdict when it cannot demonstrate its own\n"
            "  detector, because the defect it exists for is precisely a check\n"
            "  that reports success while examining nothing." % broken,
            file=sys.stderr,
        )
        return 1

    judged, superseded = split_budgeted(jobs, budgeted)
    for name in superseded:
        print(
            "  %s: superseded by check:ci-lane-budget (D-W2), which budgets its p90 and its "
            "timeout-minutes; not judged against %.1fx here" % (name, MIN_HEADROOM)
        )

    # Freshness guards the numbers this gate judges; a baseline whose every job the lane budget took over has none left to go stale (that gate's own check 5 guards its data).
    stale = None
    if judged:
        try:
            age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(baseline["refreshed_at"])
            if age.days > MAX_BASELINE_AGE_DAYS:
                stale = age.days
        except (KeyError, ValueError, TypeError):
            stale = -1

    problems = verdicts(judged, timeouts)
    if stale is not None:
        problems.append(
            "the baseline itself is stale (%s), so these numbers no longer describe\n"
            "  reality. Refresh it: npm run check:ci-timeout-headroom -- --refresh"
            % (
                "refreshed_at is missing or unparseable"
                if stale < 0
                else "%d days old, limit %d" % (stale, MAX_BASELINE_AGE_DAYS)
            )
        )

    if problems:
        print("CI job timeout headroom is insufficient:", file=sys.stderr)
        for p in problems:
            print("  - %s" % p, file=sys.stderr)
        return 1

    print(
        "%d job(s) keep at least %.2fx headroom under their timeout-minutes, "
        "%d superseded by check:ci-lane-budget (D-W2) "
        "(controls fired in both directions)" % (len(judged), MIN_HEADROOM, len(superseded))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

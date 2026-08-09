#!/usr/bin/env python3
"""A job the profiler says fits ubuntu-slim must actually be on ubuntu-slim.

WHY THIS EXISTS. Standard runners are free and unlimited on this public repo,
which is precisely what makes oversizing invisible: a job using ~1 core on a
4-vCPU ubuntu-latest VM burns four cores' worth of electricity to do one core's
work and no bill ever says so. The profiler
(.ci/scripts/ci/profiler/) turns that into a MEASUREMENT and prints an advisory
into the job summary -- and an advisory nobody is obliged to read is a habit,
not an invariant. Advisories decay the same way coverage does: the first one
gets acted on, the tenth gets scrolled past, and six months later the panel says
MOVE TO ubuntu-slim on twelve jobs that nobody has moved.

This closes that half. The measurement is committed
(runner-sizing-baseline.json), the verdict is re-derived from it offline, and a
job whose own profile says it fits slim while its `runs-on:` says otherwise is
RED until it is either moved or written down in .runner-advice-allowlist with a
reason.

FOUR RELATIONS:
  (a) COST         -- a MOVE_TO_SLIM verdict on a job that is not on slim.
  (b) RELIABILITY  -- a job ON slim that is at its time cap or saturating its
                      1 core / 5 GB. This is the opposite direction and it is
                      NOT allowlist-suppressible: (a) costs electricity, while
                      (b) is a job about to start failing, and a waiver for a
                      thing that is about to break is a waiver for the outage.
  (c) DRIFT        -- a baseline job that matches no job in any workflow. Its
                      number is unfalsifiable from here on, so it is a defect,
                      not a comment.
  (d) LIVENESS     -- an allowlist entry that suppresses nothing. Enforced in
                      this gate rather than by an external probe, because the
                      oracle IS the comparison the gate already performs, which
                      makes the list shrink-only.

VERDICTS ARE RE-DERIVED, NOT READ. classify() below mirrors report.awk's
advise() exactly, and the row's own `verdict=` token is used only as a CONTROL:
--refresh warns when the two disagree, which is what turns a silent divergence
between the two implementations into a visible one. The gate test
(.ci/scripts/test/gates/test-runner-advice.sh) drives real awk output through
classify() for three profiles to pin the agreement.

KNOWN COUPLING. classify() uses the DEFAULT thresholds report.awk assumes
(840 s declared, 900 s hard cap). panel.sh can forward per-job overrides via
PROFILER_DECLARED_S / PROFILER_HARD_S, and a job that does so would have its
row computed against different numbers than this file re-derives. Nothing
forwards them today; the --refresh disagreement warning is what would surface
it on the day something does.

WHAT IT DOES NOT DO. It does not predict cost or duration, and it never edits a
workflow. It asserts one thing: that a measured, repeatedly-observed fit is
either taken or justified.
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys

# --- The thresholds. These MIRROR .ci/scripts/ci/profiler/report.awk's advise()
# --- and its BEGIN block. Changing one without the other is what the gate
# --- test's awk/python parity case exists to catch.
CPU_KEEP_MILLI = 1000
MEM_KEEP_BYTES = 4831838208
DECLARED_S = 840
HARD_S = 900
SLACK_S = 120
SLIM_CPU_CEIL_MILLI = 1500
SLIM_MEM_CEIL_BYTES = 6442450944

SLIM_LABEL = "ubuntu-slim"

# `runs-on: ${{ ... }}` resolves at dispatch time and no static parse can say
# what it will be. Recorded rather than guessed, and NEVER fired on: a job whose
# runner is chosen per run cannot be "on the wrong runner" from here.
DYNAMIC = "DYNAMIC"

# One observation is an anecdote. A job is only told to move once the same
# verdict has survived this many distinct runs, because the cheapest way to
# discredit this gate is to move a job on the strength of one unusually quiet
# afternoon.
MIN_OBSERVED_RUNS = 3

# Vacuity floor. An empty baseline makes every comparison vacuous and the gate
# would exit 0 reading exactly like full coverage.
MIN_BASELINE_JOBS = 5

# A baseline nobody refreshes stops describing reality. Loud, not silent.
MAX_BASELINE_AGE_DAYS = 45

REPO = "rediacc/console"
ROW_MARKER = "PROFILER_BASELINE_V1 "
INT_FIELDS = (
    "cpu_peak_milli",
    "mem_peak_bytes",
    "wall_s",
    "cpu_ceil_milli",
    "mem_ceil_bytes",
)


class WorkflowUnreadableError(Exception):
    """The workflows could not be parsed, so no verdict is possible."""


def runs_on(workflow_dir):
    """Map (workflow basename, job id) -> its `runs-on:` label, across every workflow.

    Deliberately regex-based rather than yaml.safe_load, for the same reason
    check_job_timeout_headroom.py is: the shape being read is two keys at two
    fixed indentation levels, and this keeps the gate free of a PyYAML
    dependency it would otherwise need on every runner. A parse that finds
    nothing RAISES rather than returning {} -- an empty map would make every
    comparison below vacuous while the gate printed a clean line.
    """
    found = {}
    files = sorted(pathlib.Path(workflow_dir).glob("*.yml"))
    for path in files:
        in_jobs = False
        job = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"^jobs:\s*$", line):
                in_jobs = True
                job = None
                continue
            if in_jobs and re.match(r"^[^\s#]", line):
                in_jobs = False
                job = None
                continue
            if not in_jobs:
                continue
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                job = m.group(1)
                continue
            m = re.match(r"^    runs-on:\s*(.+?)\s*$", line)
            if m and job:
                value = re.sub(r"\s+#.*$", "", m.group(1)).strip().strip("\"'")
                if "${{" in value:
                    value = DYNAMIC
                found.setdefault((path.name, job), value)
    if not found:
        raise WorkflowUnreadableError(
            "parsed 0 job/runs-on pairs out of %d workflow file(s) -- they moved, were "
            "reformatted, or the indentation assumption is wrong. Refusing a verdict "
            "rather than reporting that every job is sized correctly." % len(files)
        )
    return found


def classify(rec):
    """The verdict report.awk's advise() would reach from the same numbers.

    The PROC_HOST-plus-container-fingerprint branch of advise() is deliberately
    absent: it yields NONE, and --refresh drops NONE rows, so a record carrying
    that shape never reaches this function.
    """
    tier = rec.get("tier", "")
    label = rec.get("runner_label", "")
    cpu_peak = int(rec.get("cpu_peak_milli", 0))
    mem_peak = int(rec.get("mem_peak_bytes", 0))
    wall = int(rec.get("wall_s", 0))
    cpu_ceil = int(rec.get("cpu_ceil_milli", 0))
    mem_ceil = int(rec.get("mem_ceil_bytes", 0))

    if tier == "HOST_LEAK":
        return "NONE"
    if tier == "PROC_HOST" and label in ("", "unknown"):
        return "NONE"
    if tier == "PROC_HOST" and "slim" in label:
        return "NONE"

    # A label is a claim; an enforced quota is a fact, and the fact wins. See
    # the long comment above advise() in report.awk for why this is restricted
    # to cgroup tiers.
    on_slim = "slim" in label or (
        tier != "PROC_HOST"
        and 0 < cpu_ceil <= SLIM_CPU_CEIL_MILLI
        and 0 < mem_ceil <= SLIM_MEM_CEIL_BYTES
    )
    if on_slim:
        if wall >= DECLARED_S:
            return "SLIM_OVER_TIME"
        if cpu_peak > CPU_KEEP_MILLI or mem_peak > MEM_KEEP_BYTES:
            return "SLIM_SATURATED"
        return "SLIM_FIT"
    if wall >= HARD_S - SLACK_S:
        return "KEEP"
    if cpu_peak > CPU_KEEP_MILLI:
        return "KEEP"
    if mem_peak > MEM_KEEP_BYTES:
        return "KEEP"
    return "MOVE_TO_SLIM"


def verdicts(jobs, pairs, allowed):
    """Every complaint about this baseline, plus the advisories. Pure, so the controls can drive it."""
    problems = []
    advisories = []
    for key, rec in sorted(jobs.items()):
        workflow, _, job = key.partition(":")
        declared = pairs.get((workflow, job))
        if declared is None:
            problems.append(
                "%s: names no job in any workflow. Either it was renamed (update the "
                "baseline key) or it was deleted (drop the record). Its measurement can "
                "no longer be checked against anything." % key
            )
            continue
        if rec.get("workflow") not in (None, workflow):
            problems.append(
                "%s: the record's workflow field says %r, which disagrees with its own "
                "key. One of the two is wrong and neither can be trusted."
                % (key, rec.get("workflow"))
            )
            continue
        verdict = classify(rec)
        observed = int(rec.get("observed_runs", 0))

        if verdict == "MOVE_TO_SLIM" and declared not in (SLIM_LABEL, DYNAMIC):
            if key in allowed:
                continue
            if observed < MIN_OBSERVED_RUNS:
                advisories.append(
                    "%s: fits slim (peak %s millicores / %s bytes over %ss) but has only "
                    "been observed %d time(s); %d are needed before this becomes a "
                    "failure."
                    % (
                        key,
                        rec.get("cpu_peak_milli"),
                        rec.get("mem_peak_bytes"),
                        rec.get("wall_s"),
                        observed,
                        MIN_OBSERVED_RUNS,
                    )
                )
                continue
            problems.append(
                "%s: runs-on %s but its own profile fits %s -- peak %s millicores (slim "
                "gives 1000) and %s bytes (slim gives 5 GB), finishing in %ss, observed "
                "over %d run(s). On a 4-vCPU VM that is roughly 4x the core-minutes the "
                "job needs. Move it, or add '%s' to the allowlist with a '# BLOCKER:' "
                "saying why it cannot go."
                % (
                    key,
                    declared,
                    SLIM_LABEL,
                    rec.get("cpu_peak_milli"),
                    rec.get("mem_peak_bytes"),
                    rec.get("wall_s"),
                    observed,
                    key,
                )
            )
        elif verdict in ("SLIM_OVER_TIME", "SLIM_SATURATED") and declared == SLIM_LABEL:
            problems.append(
                "%s: is on %s and %s (peak %s millicores / %s bytes over %ss). slim is "
                "1 vCPU / 5 GB with a hard %d-minute cap, and a job at that edge fails as "
                "`cancelled`, which assert-ci-complete.sh does not forgive. Move it UP. "
                "This direction is not allowlistable: a waiver here waives the outage."
                % (
                    key,
                    SLIM_LABEL,
                    "is at or past its declared timeout"
                    if verdict == "SLIM_OVER_TIME"
                    else "is saturating the box",
                    rec.get("cpu_peak_milli"),
                    rec.get("mem_peak_bytes"),
                    rec.get("wall_s"),
                    HARD_S // 60,
                )
            )
    return problems, advisories


def stale_allowlist(allowed, jobs, pairs):
    """Allowlist entries that suppress nothing. This list is only ever allowed to shrink."""
    out = []
    for key in sorted(allowed):
        workflow, _, job = key.partition(":")
        declared = pairs.get((workflow, job))
        if declared is None:
            out.append("'%s' names no job in any workflow; it suppresses nothing" % key)
            continue
        rec = jobs.get(key)
        if rec is None:
            out.append(
                "'%s' has no measurement in the baseline, so there is no finding for it to "
                "suppress; drop the entry" % key
            )
            continue
        if declared == SLIM_LABEL:
            out.append("'%s' is ALREADY on %s; drop the entry" % (key, SLIM_LABEL))
            continue
        verdict = classify(rec)
        if verdict != "MOVE_TO_SLIM":
            out.append(
                "'%s' now classifies as %s, not MOVE_TO_SLIM; the exemption exempts nothing "
                "and hides the next real one" % (key, verdict)
            )
    return out


def controls(pairs):
    """Prove the detector can fire, in BOTH directions, before any real read.

    A one-directional control is satisfiable by a broken checker: one that always
    complains passes the positive control, one that never complains passes the
    negative. Refusing a verdict when the instrument cannot be demonstrated is
    the whole point -- an advisory that quietly stopped being enforced is the
    very thing this gate replaces.
    """
    workflow = min(wf for wf, _ in pairs)
    probe = dict(pairs)
    probe[(workflow, "__control_move__")] = "ubuntu-latest"
    probe[(workflow, "__control_slim__")] = SLIM_LABEL
    fits_slim = {
        "workflow": workflow,
        "runner_label": "ubuntu-latest",
        "tier": "PROC_HOST",
        "cpu_peak_milli": 200,
        "mem_peak_bytes": 943718400,
        "wall_s": 120,
        "cpu_ceil_milli": 4000,
        "mem_ceil_bytes": 16000000000,
        "observed_runs": MIN_OBSERVED_RUNS,
    }

    on_latest = {"%s:__control_move__" % workflow: fits_slim}
    problems, _ = verdicts(on_latest, probe, set())
    if not problems:
        return "planted a job that fits slim on ubuntu-latest and the detector stayed silent"

    already_moved = {"%s:__control_slim__" % workflow: dict(fits_slim, runner_label=SLIM_LABEL)}
    problems, _ = verdicts(already_moved, probe, set())
    if problems:
        return "planted the same job already on ubuntu-slim and the detector complained anyway"

    orphan = {"no-such-workflow.yml:no-such-job": fits_slim}
    problems, _ = verdicts(orphan, probe, set())
    if not problems:
        return "planted a baseline job absent from every workflow and the detector stayed silent"

    under_observed = {"%s:__control_move__" % workflow: dict(fits_slim, observed_runs=1)}
    problems, advisories = verdicts(under_observed, probe, set())
    if problems or not advisories:
        return (
            "planted a one-run MOVE and it was reported as a failure (or not reported at "
            "all) rather than as an advisory"
        )

    suppressed = verdicts(on_latest, probe, {"%s:__control_move__" % workflow})[0]
    if suppressed:
        return "planted an allowlisted MOVE job and the detector complained anyway"

    if not stale_allowlist({"no-such-workflow.yml:no-such-job"}, {}, probe):
        return "planted an allowlist entry naming no job and the liveness check stayed silent"

    return None


def parse_allowlist(path):
    """Entries with their BLOCKER reason. Same grammar as .profiler-coverage-allowlist.

    Structure only: presence of a reason, and the shrink-only liveness above.
    The PROSE quality bar is the shared validator's
    (.ci/scripts/lib/blocker-validator.sh), applied to this file by the gate
    test, so the banned-phrase list lives in exactly one place.
    """
    entries = {}
    if not os.path.isfile(path):
        return entries
    reason = ""
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                reason = ""
                continue
            m = re.match(r"^#\s*BLOCKER:\s*(.+)$", line)
            if m:
                reason = m.group(1).strip()
                continue
            if line.startswith("#"):
                continue
            entries[line.split()[0]] = reason
    return entries


def gh_json(args, root):
    """One `gh` call returning parsed lines. Network lives only in --refresh."""
    out = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    return out.stdout.splitlines()


def parse_row(message):
    """A PROFILER_BASELINE_V1 annotation body -> its key/value dict, or None."""
    idx = message.find(ROW_MARKER)
    if idx < 0:
        return None
    fields = {}
    for token in message[idx + len(ROW_MARKER) :].split():
        key, sep, value = token.partition("=")
        if sep:
            fields[key] = value
    if "job" not in fields or "verdict" not in fields:
        return None
    return fields


def harvest(root, branch, event, limit):
    """Every usable PROFILER_BASELINE_V1 row from the last `limit` runs on `branch`."""
    args = [
        "run",
        "list",
        "--repo",
        REPO,
        "--branch",
        branch,
        "--limit",
        str(limit),
        "--json",
        "databaseId",
        "--jq",
        ".[].databaseId",
    ]
    if event:
        args[6:6] = ["--event", event]
    run_ids = [x for x in gh_json(args, root) if x.isdigit()]
    if not run_ids:
        return None, []

    rows = []
    for run_id in run_ids:
        # .jobs[].id IS the check-run id, which is what the annotations
        # endpoint is keyed by. There is no separate lookup.
        job_ids = gh_json(
            [
                "api",
                "repos/%s/actions/runs/%s/jobs?per_page=100" % (REPO, run_id),
                "--jq",
                ".jobs[].id",
            ],
            root,
        )
        for check_id in job_ids:
            if not check_id.isdigit():
                continue
            for message in gh_json(
                [
                    "api",
                    "repos/%s/check-runs/%s/annotations" % (REPO, check_id),
                    "--jq",
                    ".[].message",
                ],
                root,
            ):
                fields = parse_row(message)
                if fields:
                    rows.append((run_id, fields))
    return run_ids, rows


def refresh(root, baseline_path, workflow_dir, branch, event, limit):
    """Rewrite the baseline from harvested annotations. Network lives HERE."""
    try:
        pairs = runs_on(workflow_dir)
    except WorkflowUnreadableError as exc:
        print("CANNOT READ THE WORKFLOWS: %s" % exc, file=sys.stderr)
        return 1

    where = {}
    for workflow, job in pairs:
        where.setdefault(job, set()).add(workflow)

    run_ids, rows = harvest(root, branch, event, limit)
    if run_ids is None:
        print("refresh found no runs on branch %r; baseline untouched" % branch, file=sys.stderr)
        return 1

    merged = {}
    contributing = {}
    for run_id, fields in rows:
        if fields["verdict"] == "NONE" or fields.get("tier") == "HOST_LEAK":
            continue
        if fields.get("findings", "0") != "0":
            continue
        job = fields["job"]
        candidates = where.get(job, set())
        if len(candidates) != 1:
            print(
                "  WARNING: job %r resolves to %d workflow file(s); skipped, because a "
                "measurement filed under the wrong workflow is worse than a missing one"
                % (job, len(candidates)),
                file=sys.stderr,
            )
            continue
        workflow = next(iter(candidates))
        key = "%s:%s" % (workflow, job)
        rec = merged.setdefault(
            key,
            {
                "workflow": workflow,
                "runner_label": fields.get("runner_label", "unknown"),
                "tier": fields.get("tier", "UNKNOWN"),
                "cpu_peak_milli": 0,
                "mem_peak_bytes": 0,
                "wall_s": 0,
                "cpu_ceil_milli": 0,
                "mem_ceil_bytes": 0,
                "observed_runs": 0,
            },
        )
        for name in INT_FIELDS:
            try:
                value = int(fields.get(name, 0))
            except ValueError:
                value = 0
            rec[name] = max(rec[name], value)
        rec["runner_label"] = fields.get("runner_label", rec["runner_label"])
        rec["tier"] = fields.get("tier", rec["tier"])
        contributing.setdefault(key, set()).add(run_id)
        # The row's own token against this file's re-derivation. Disagreement is
        # the two implementations of advise() having drifted apart, which is
        # invisible at every other moment.
        if classify(rec) != fields["verdict"]:
            print(
                "  WARNING: %s reported verdict=%s but classify() re-derives %s from the "
                "merged maxima; report.awk and check_runner_advice.py may have drifted"
                % (key, fields["verdict"], classify(rec)),
                file=sys.stderr,
            )

    if not merged:
        print(
            "refresh matched NONE of the %d run(s) sampled: no usable PROFILER_BASELINE_V1 "
            "annotation was found. Refusing to stamp refreshed_at on numbers nothing "
            "verified." % len(run_ids),
            file=sys.stderr,
        )
        return 1

    for key, rec in merged.items():
        rec["observed_runs"] = len(contributing[key])

    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    data["jobs"] = dict(sorted(merged.items()))
    data["refreshed_at"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    baseline_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        "baseline refreshed from %d run(s): %d job(s) measured, %d row(s) parsed"
        % (len(run_ids), len(merged), len(rows))
    )
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Runner sizing advice, enforced.")
    ap.add_argument("--refresh", action="store_true", help="rewrite the baseline (network)")
    ap.add_argument("--branch", default="main", help="branch to harvest annotations from")
    ap.add_argument("--event", default="", help="restrict the harvest to one trigger event")
    ap.add_argument("--runs", type=int, default=8, help="how many runs to sample when refreshing")
    ap.add_argument("--baseline", default="", help="baseline path (test seam)")
    ap.add_argument("--workflow-dir", default="", help="workflow directory (test seam)")
    ap.add_argument("--allowlist", default="", help="allowlist path (test seam)")
    args = ap.parse_args(argv)

    root = pathlib.Path(__file__).resolve().parents[3]
    baseline_path = pathlib.Path(
        args.baseline
        or os.environ.get("RUNNER_ADVICE_BASELINE")
        or root / ".ci/scripts/quality/runner-sizing-baseline.json"
    )
    workflow_dir = pathlib.Path(
        args.workflow_dir
        or os.environ.get("RUNNER_ADVICE_WORKFLOW_DIR")
        or root / ".github/workflows"
    )
    allowlist_path = pathlib.Path(
        args.allowlist
        or os.environ.get("RUNNER_ADVICE_ALLOWLIST")
        or root / ".runner-advice-allowlist"
    )

    if not baseline_path.is_file() or not workflow_dir.is_dir():
        print(
            "VACUOUS INPUT: baseline (%s) or workflow directory (%s) missing, so nothing can "
            "be compared" % (baseline_path, workflow_dir),
            file=sys.stderr,
        )
        return 1

    if args.refresh:
        return refresh(root, baseline_path, workflow_dir, args.branch, args.event, args.runs)

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    jobs = baseline.get("jobs", {})
    if len(jobs) < MIN_BASELINE_JOBS:
        print(
            "VACUOUS INPUT: baseline names %d job(s), expected at least %d. A sizing check\n"
            "over an empty baseline exits 0 and reads exactly like full coverage. Seed it:\n"
            "  npm run check:ci-runner-advice -- --refresh --branch main"
            % (len(jobs), MIN_BASELINE_JOBS),
            file=sys.stderr,
        )
        return 1

    try:
        pairs = runs_on(workflow_dir)
    except WorkflowUnreadableError as exc:
        print("CANNOT READ THE WORKFLOWS, so no verdict is possible:\n  %s" % exc, file=sys.stderr)
        return 1

    broken = controls(pairs)
    if broken:
        print(
            "CONTROL FAILED, so nothing below is meaningful: %s.\n"
            "  This gate refuses a verdict when it cannot demonstrate its own detector,\n"
            "  because the defect it exists for is precisely an advisory that stopped\n"
            "  being acted on while still being printed." % broken,
            file=sys.stderr,
        )
        return 1

    allow = parse_allowlist(str(allowlist_path))
    missing_reason = sorted(k for k, v in allow.items() if not v)
    problems, advisories = verdicts(jobs, pairs, set(allow))
    problems.extend(
        "%s: %s" % (allowlist_path.name, msg) for msg in stale_allowlist(set(allow), jobs, pairs)
    )
    problems.extend(
        "%s: entry '%s' is missing a '# BLOCKER: <reason>' comment above it"
        % (allowlist_path.name, key)
        for key in missing_reason
    )

    stale = None
    try:
        age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(baseline["refreshed_at"])
        if age.days > MAX_BASELINE_AGE_DAYS:
            stale = age.days
    except (KeyError, TypeError, ValueError):
        stale = -1
    if stale is not None:
        problems.append(
            "the baseline itself is stale (%s), so these numbers no longer describe\n"
            "  reality. Refresh it: npm run check:ci-runner-advice -- --refresh --branch main"
            % (
                "refreshed_at is missing or unparseable"
                if stale < 0
                else "%d days old, limit %d" % (stale, MAX_BASELINE_AGE_DAYS)
            )
        )

    for line in advisories:
        print("ADVISORY (not yet a failure): %s" % line)

    if problems:
        print("Runner sizing is wrong on %d count(s):" % len(problems), file=sys.stderr)
        for problem in problems:
            print("  - %s" % problem, file=sys.stderr)
        return 1

    print(
        "runner sizing: %d measured job(s) sit on the runner their own profile justifies, "
        "%d allowlisted, %d advisory (controls fired in both directions)"
        % (len(jobs), len(allow), len(advisories))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

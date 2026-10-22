"""The CI time budget verdict in `.ci/scripts/ci/watchdog-monitor.cjs` (operator spec W, `agent/plans/_done/PLAN-ci-time-budget.md` T1.1-T1.5, T4.2, T4.3): every job finishes in 15 minutes or less (two ruled caps: E2E K8s Ceph 25, E2E K8s Multinode 30), and the whole pipeline in ~35 minutes (D-W1).

P4 split the one mode switch in two (#a631eaf1): the PER-JOB budget is enforced (a live job over its budget force-cancels the run through `forceCancel`), and the RUN-level budget stays report-only until the wall-time p90 is at or under 35. A job cancelled at or past its budget was killed by its own timeout and is never auto-retried (T4.3).

`evaluateBudget` is the pure decision function this suite drives directly, the same way `evaluateSupersession` and `evaluateCancelExemption` are already driven elsewhere in this family -- NOT a mirror of the boolean, but the exported function itself, so a reordered branch or a renamed field fails here rather than in a copy that agrees with itself by construction.

BOTH DIRECTIONS MATTER, same as every sibling in this family:
  - Too quiet: a job or the whole pipeline blows its budget and nobody is told.
  - Too loud: `report` mode itself asks for a force-cancel, the run-level budget cancels while it is ruled report-only, or a cancel-exempt (scheduled) run is rewritten to `cancelled`.

The first half drives the pure `evaluateBudget`; the second half drives the REAL `monitor()` with a mocked GitHub client, because "goes through forceCancel with this annotation text" and "a timeout-killed leg is not retried" are claims about the whole loop, not about the verdict.

NO `xdist_group`. Every case is a short-lived `node` subprocess reading one tracked file and one JSON blob on argv; nothing is bound, no port is opened and no module global moves. The monitor cases replace `setTimeout` inside their own subprocess so a poll interval costs milliseconds, not 30 seconds.
"""

import json
import pathlib
import re
from datetime import UTC, datetime, timedelta

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")
WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")
LANE_BUDGET = paths.from_root("scripts", "gates", "check-lane-budget.ts")
CT_TESTS = paths.from_root(".github", "workflows", "ct-tests.yml")

# One fixed anchor instant so every case can express its inputs as plain
# offsets from it rather than repeating ISO timestamps.
T0 = "2026-01-01T00:00:00Z"


_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _iso(minutes: float) -> str:
    """`T0` plus `minutes`, as the ISO string the real API would send."""
    return (_BASE + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ms(minutes: int, seconds: int) -> float:
    """Milliseconds from `T0` -- readable call sites (`_ms(15, 1)` = 15m01s)."""
    return (_BASE + timedelta(minutes=minutes, seconds=seconds)).timestamp() * 1000


VERDICT_JS = """
const w = require(process.argv[1]);
process.stdout.write(JSON.stringify(w.evaluateBudget(JSON.parse(process.argv[2]))));
"""


def subject(gate):
    return harness.watchdog_subject(gate, WATCHDOG)


def evaluate(gate, **kwargs) -> dict:
    """Drive the real `evaluateBudget`, returning its parsed JSON verdict."""
    result = harness.run(["node", "-e", VERDICT_JS, str(subject(gate)), json.dumps(kwargs)])
    if result.rc != 0:
        gate.log_fail(
            "evaluateBudget could not be driven (rc=%d): %s" % (result.rc, result.err.strip())
        )
    return json.loads(result.out)


def test_the_function_is_exported(gate):
    """Anti-vacuity: every case below throws rather than silently passing if this is missing, but a typo in the export name would fail in a quieter way than a thrown error further down. Read it directly."""
    result = harness.run(
        [
            "node",
            "-e",
            "process.stdout.write(typeof require(process.argv[1]).evaluateBudget)",
            str(subject(gate)),
        ]
    )
    gate.assert_exit(0, result, "the typeof probe must run")
    gate.assert_eq(result.out, "function", "evaluateBudget must be exported as a function")
    gate.log_pass("evaluateBudget is exported")


def test_job_just_under_budget_does_not_fire(gate):
    verdict = evaluate(
        gate,
        jobs=[
            {
                "name": "Tests + Infra / E2E Migrate (fedora-43)",
                "status": "in_progress",
                "started_at": T0,
            }
        ],
        run=None,
        nowMs=int(_ms(14, 59)),
        jobBudgetMin=15,
        runBudgetMin=None,
    )
    gate.assert_eq(verdict["jobViolations"], [], "14m59s against a 15m budget must not fire")
    gate.log_pass("a job at 14:59 against a 15m budget does not fire")


def test_job_just_over_budget_fires(gate):
    verdict = evaluate(
        gate,
        jobs=[
            {
                "name": "Tests + Infra / E2E Migrate (fedora-43)",
                "status": "in_progress",
                "started_at": T0,
            }
        ],
        run=None,
        nowMs=int(_ms(15, 1)),
        jobBudgetMin=15,
        runBudgetMin=None,
    )
    gate.assert_eq(
        len(verdict["jobViolations"]), 1, "15m01s against a 15m budget must fire exactly once"
    )
    gate.assert_eq(
        verdict["jobViolations"][0]["name"],
        "Tests + Infra / E2E Migrate (fedora-43)",
        "the violation names the offending job",
    )
    gate.log_pass("a job at 15:01 against a 15m budget fires (%s)" % verdict["jobViolations"])


def test_a_job_that_already_completed_over_budget_still_fires(gate):
    """T1.2: "a job that finished over budget between polls" must still be caught, not only one still running when a poll happens to land."""
    verdict = evaluate(
        gate,
        jobs=[
            {
                "name": "Tests + Infra / Concurrent Fork Isolation",
                "status": "completed",
                "started_at": T0,
                "completed_at": _iso(22.0),
            }
        ],
        run=None,
        nowMs=int(_ms(90, 0)),  # long after completion; must not matter
        jobBudgetMin=15,
        runBudgetMin=None,
    )
    gate.assert_eq(
        len(verdict["jobViolations"]), 1, "a completed 22m job against a 15m budget fires"
    )
    gate.log_pass("a job that finished over budget is still reported, even polled long after")


def test_excluded_job_never_fires(gate):
    """WATCHDOG_EXCLUDE_PATTERNS (Watchdog, CI Complete, CI Verdict): aggregators and observers are not budgeted work, and without this exclusion the watchdog's own chain generations would budget-flag themselves."""
    verdict = evaluate(
        gate,
        jobs=[{"name": "CI Watchdog", "status": "in_progress", "started_at": T0}],
        run=None,
        nowMs=int(_ms(45, 0)),
        jobBudgetMin=15,
        runBudgetMin=None,
        excludePatterns=["Watchdog", "CI Complete", "CI Verdict"],
    )
    gate.assert_eq(
        verdict["jobViolations"], [], "an excluded job never fires, however long it runs"
    )
    gate.log_pass("CI Watchdog itself never budget-fires")


def test_run_clock_just_under_budget_does_not_fire(gate):
    verdict = evaluate(
        gate,
        jobs=[],
        run={"run_started_at": T0},
        nowMs=int(_ms(19, 59)),
        jobBudgetMin=None,
        runBudgetMin=20,
    )
    gate.assert_eq(verdict["runViolation"], None, "19m59s against a 20m run budget must not fire")
    gate.log_pass("the run clock at 19:59 against a 20m budget does not fire")


def test_run_clock_fires_at_20_01(gate):
    verdict = evaluate(
        gate,
        jobs=[],
        run={"run_started_at": T0},
        nowMs=int(_ms(20, 1)),
        jobBudgetMin=None,
        runBudgetMin=20,
    )
    gate.assert_eq(verdict["jobViolations"], [], "no job violations were supplied")
    gate.assert_eq(
        verdict["runViolation"] is None, False, "20m01s against a 20m run budget must fire"
    )
    gate.log_pass("the run clock fires at 20:01 (%s)" % verdict["runViolation"])


def test_a_queued_job_is_not_over_budget(gate):
    """Run 36709808117: jobs queued behind the 20-job concurrency limit carried started_at = created_at and zero steps, and enforce mode cancelled the run on "ran 15.3m (budget 15m)" for jobs that never ran. The real API shape (an empty `steps` array) must read as not running; a job whose first step started 5 minutes ago is 5 minutes in, whatever its started_at says."""
    queued = {"name": "Quality / Gate tests", "status": "queued", "started_at": T0, "steps": []}
    running = {
        "name": "Quality / Wiring",
        "status": "in_progress",
        "started_at": T0,
        "steps": [{"name": "Set up job", "started_at": _iso(25)}],
    }
    verdict = evaluate(
        gate,
        jobs=[queued, running],
        run={"run_started_at": T0},
        nowMs=int(_ms(30, 0)),
        jobBudgetMin=15,
        runBudgetMin=None,
        jobMode="enforce",
    )
    gate.assert_eq(
        verdict["jobViolations"], [], "a queued job and a 5-minute-old job are both within budget"
    )
    gate.assert_eq(verdict["forceCancelRequested"], False, "nothing to cancel")
    # Control: the same running job whose first step started at T0 is 30 minutes in and must fire.
    running_long = dict(running, steps=[{"name": "Set up job", "started_at": T0}])
    control = evaluate(
        gate,
        jobs=[running_long],
        run={"run_started_at": T0},
        nowMs=int(_ms(30, 0)),
        jobBudgetMin=15,
        runBudgetMin=None,
        jobMode="enforce",
    )
    gate.assert_eq(
        len(control["jobViolations"]), 1, "control: 30 minutes from the first step fires"
    )
    gate.log_pass("queue time is not runtime; the first step's start is the job's start")


def test_report_mode_never_requests_force_cancel(gate):
    verdict = evaluate(
        gate,
        jobs=[{"name": "Tests + Infra / E2E Ceph", "status": "in_progress", "started_at": T0}],
        run={"run_started_at": T0},
        nowMs=int(_ms(30, 0)),
        jobBudgetMin=15,
        runBudgetMin=20,
        jobMode="report",
        runMode="report",
    )
    gate.assert_eq(
        verdict["hasViolation"], True, "the fixture must genuinely violate, or this proves nothing"
    )
    gate.assert_eq(
        verdict["forceCancelRequested"], False, "report mode must never request a force-cancel"
    )
    gate.log_pass("report mode never requests a force-cancel, even with real violations present")


def test_control_enforce_mode_requests_force_cancel_exactly_once(gate):
    """The control for the case above: the SAME fixture, only `jobMode` flipped, must request the cancel. Without this control, a `evaluateBudget` that always returned `forceCancelRequested: false` would pass the report-mode test for the wrong reason."""
    fixture = {
        "jobs": [{"name": "Tests + Infra / E2E Ceph", "status": "in_progress", "started_at": T0}],
        "run": {"run_started_at": T0},
        "nowMs": int(_ms(30, 0)),
        "jobBudgetMin": 15,
        "runBudgetMin": 20,
    }
    report_verdict = evaluate(gate, jobMode="report", **fixture)
    enforce_verdict = evaluate(gate, jobMode="enforce", **fixture)
    gate.assert_eq(report_verdict["forceCancelRequested"], False, "report mode: no request")
    gate.assert_eq(
        enforce_verdict["forceCancelRequested"], True, "enforce mode: exactly one request"
    )
    gate.log_pass(
        "enforce mode requests the cancel that report mode withholds, on the identical fixture"
    )


def test_a_rerun_resets_the_run_clock(gate):
    """GitHub resets a run's `run_started_at` to the CURRENT ATTEMPT's own start on every rerun, so the same run id genuinely violating on attempt 1 must read as fresh once `run_started_at` reflects attempt 2 -- with no attempt-tracking of evaluateBudget's own, since it is pure and stateless."""
    attempt_1 = evaluate(
        gate,
        jobs=[],
        run={"run_started_at": T0},
        nowMs=int(_ms(25, 0)),
        jobBudgetMin=None,
        runBudgetMin=20,
    )
    gate.assert_eq(
        attempt_1["runViolation"] is None,
        False,
        "attempt 1, 25m in against a 20m budget, must fire",
    )

    attempt_2_start = _iso(25.0)
    attempt_2 = evaluate(
        gate,
        jobs=[],
        run={"run_started_at": attempt_2_start},
        nowMs=int(_ms(30, 0)),  # 5m after attempt 2 started, not 30m after attempt 1
        jobBudgetMin=None,
        runBudgetMin=20,
    )
    gate.assert_eq(
        attempt_2["runViolation"],
        None,
        "5m into the rerun attempt must not carry attempt 1's clock",
    )
    gate.log_pass(
        "a rerun's run_started_at resets the run clock (attempt 1 fired, attempt 2 did not)"
    )


# --- the ruled exemption caps (pure) -----------------------------------------


def test_an_exempt_job_under_its_cap_does_not_fire(gate):
    """E2E K8s Ceph is ruled a 25-minute cap (2026-09-28). At 24m it is over the ordinary 15 but under its own cap, so enforce mode must leave it alone."""
    verdict = evaluate(
        gate,
        jobs=[{"name": "Tests + Infra / E2E K8s Ceph", "status": "in_progress", "started_at": T0}],
        run=None,
        nowMs=int(_ms(24, 0)),
        jobBudgetMin=15,
        runBudgetMin=None,
        jobMode="enforce",
    )
    gate.assert_eq(verdict["jobViolations"], [], "24m is under E2E K8s Ceph's 25m cap")
    gate.assert_eq(verdict["forceCancelRequested"], False, "no cancel for a job under its cap")
    gate.log_pass("an exempt job under its cap (K8s Ceph at 24m, cap 25) does not fire")


def test_control_an_exempt_job_over_its_own_cap_fires_at_its_cap(gate):
    """The control for the case above: the same job at 25m01s fires, and against 25 rather than 15, so the cap is really being read rather than the job being skipped."""
    verdict = evaluate(
        gate,
        jobs=[
            {
                "name": "Tests + Infra / E2E K8s Multinode",
                "status": "in_progress",
                "started_at": T0,
            },
            {"name": "Tests + Infra / E2E K8s Ceph", "status": "in_progress", "started_at": T0},
        ],
        run=None,
        nowMs=int(_ms(25, 1)),
        jobBudgetMin=15,
        runBudgetMin=None,
        jobMode="enforce",
    )
    names = {v["name"]: v["budgetMin"] for v in verdict["jobViolations"]}
    gate.assert_eq(
        names,
        {"Tests + Infra / E2E K8s Ceph": 25},
        "K8s Ceph fires at 25m01s against its 25m cap; K8s Multinode (cap 30) does not",
    )
    gate.assert_eq(verdict["forceCancelRequested"], True, "an enforced live violation cancels")
    gate.log_pass("K8s Ceph fires against its own 25m cap; K8s Multinode (30) stays quiet")


def test_a_prefix_sibling_of_an_exempt_job_keeps_the_ordinary_budget(gate):
    """Exact base-name matching: `E2E K8s` is a prefix of both capped names and left the exemption list on 2026-09-28, so a substring match would silently lend it a 25-minute budget."""
    verdict = evaluate(
        gate,
        jobs=[{"name": "Tests + Infra / E2E K8s", "status": "in_progress", "started_at": T0}],
        run=None,
        nowMs=int(_ms(16, 0)),
        jobBudgetMin=15,
        runBudgetMin=None,
        jobMode="enforce",
    )
    gate.assert_eq(len(verdict["jobViolations"]), 1, "E2E K8s at 16m is over the ordinary 15")
    gate.assert_eq(verdict["jobViolations"][0]["budgetMin"], 15, "and judged against 15")
    gate.log_pass("E2E K8s is judged at 15, not at a capped sibling's budget")


def test_a_capped_matrix_leg_is_judged_against_its_cap(gate):
    """Ruling #fc4f34f8 caps a MATRIX job, whose legs carry a " (<distro>)" suffix. The base-name match must see through it: 19m under the 20m cap is quiet, 20m01s fires against 20."""
    leg = "Tests + Infra / E2E Ceph Workers non-apt (fedora-43)"
    quiet = evaluate(
        gate,
        jobs=[{"name": leg, "status": "in_progress", "started_at": T0}],
        run=None,
        nowMs=int(_ms(19, 0)),
        jobBudgetMin=15,
        runBudgetMin=None,
        jobMode="enforce",
    )
    gate.assert_eq(quiet["jobViolations"], [], "19m is under the leg's 20m cap")
    loud = evaluate(
        gate,
        jobs=[{"name": leg, "status": "in_progress", "started_at": T0}],
        run=None,
        nowMs=int(_ms(20, 1)),
        jobBudgetMin=15,
        runBudgetMin=None,
        jobMode="enforce",
    )
    gate.assert_eq([v["budgetMin"] for v in loud["jobViolations"]], [20], "20m01s fires against 20")
    gate.log_pass("a capped matrix leg is judged against its cap, suffix and all")


def test_a_completed_over_budget_job_is_reported_but_never_enforced(gate):
    """Only a LIVE job is enforced: one already finished has nothing left to stop, and cancelling the run for it would kill every other job's work for no reclaimed minute."""
    verdict = evaluate(
        gate,
        jobs=[
            {
                "name": "Tests + Infra / E2E Migrate (fedora-43, 1/8)",
                "status": "completed",
                "started_at": T0,
                "completed_at": _iso(16.0),
            }
        ],
        run=None,
        nowMs=int(_ms(20, 0)),
        jobBudgetMin=15,
        runBudgetMin=None,
        jobMode="enforce",
    )
    gate.assert_eq(len(verdict["jobViolations"]), 1, "the completed overrun is still reported")
    gate.assert_eq(verdict["forceCancelRequested"], False, "but never cancels the run")
    gate.log_pass("a completed over-budget job is reported, not enforced")


def test_run_level_stays_report_only_while_job_level_enforces(gate):
    """#a631eaf1: "enforce per-job budgets first, run-level cancel report-only until wall-time p90 is at or under 35". A run at 40m with every job inside its budget must not cancel, even with the per-job switch on enforce."""
    fixture = {
        "jobs": [
            {"name": "Quality / Code (1/4)", "status": "in_progress", "started_at": _iso(30.0)}
        ],
        "run": {"run_started_at": T0},
        "nowMs": int(_ms(40, 0)),
        "jobBudgetMin": 15,
        "runBudgetMin": 35,
        "jobMode": "enforce",
    }
    report = evaluate(gate, runMode="report", **fixture)
    gate.assert_eq(report["runViolation"] is None, False, "40m against 35 is a run violation")
    gate.assert_eq(report["forceCancelRequested"], False, "run-level report mode: no cancel")
    enforce = evaluate(gate, runMode="enforce", **fixture)
    gate.assert_eq(
        enforce["forceCancelRequested"], True, "control: the run switch alone flips the cancel"
    )
    gate.log_pass("the run-level budget reports only; its own switch (not the job one) enforces")


def test_a_cap_matches_the_full_segment_before_the_base_name(gate):
    """`Renet (Full)` is capped by its whole segment: dropping its literal parenthesis would give `Renet`, and every other Renet job would inherit the 20. Matrix jobs still match by base name."""
    names = {
        "Build (Renet) / Renet (Full)": 20,
        "Tests + Infra / Renet (go, 1/2)": 15,
        "Build (Renet) / Renet (cross-compile smoke)": 15,
        "Tests + Infra / E2E Workers (fedora-43, 1/8)": 20,
        "Tests + Infra / E2E Ceph Workers": 20,
        "Tests + Infra / E2E Ceph Workers non-apt (oracle-10)": 20,
        "Tests + Infra / E2E Migrate (fedora-43)": 15,
    }
    result = harness.run(
        [
            "node",
            "-e",
            (
                "const m=require(process.argv[1]);"
                "process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map((n)=>m.jobBudgetFor(n,15))))"
            ),
            str(subject(gate)),
            json.dumps(list(names)),
        ]
    )
    gate.assert_exit(0, result, "jobBudgetFor must be exported")
    gate.assert_eq(json.loads(result.out), list(names.values()), "each job's budget")
    gate.log_pass("segment-first cap lookup: %s" % names)


def test_watchdog_caps_agree_with_the_lane_budget_gate(gate):
    """One ruling, two copies: `JOB_BUDGET_CAPS` in the watchdog (by display name) and `JOB_BUDGET_CAPS[].timeoutMinutes` in scripts/gates/check-lane-budget.ts (by job id). Map the ids to display names through ct-tests.yml and require the numbers to agree, so a revised cap cannot land in one copy only."""
    result = harness.run(
        [
            "node",
            "-e",
            "process.stdout.write(JSON.stringify(require(process.argv[1]).JOB_BUDGET_CAPS))",
            str(subject(gate)),
        ]
    )
    gate.assert_exit(0, result, "JOB_BUDGET_CAPS must be exported")
    watchdog_caps = {c["job"]: c["budgetMin"] for c in json.loads(result.out)}

    lane_text = LANE_BUDGET.read_text(encoding="utf-8")
    block = lane_text[lane_text.index("export const JOB_BUDGET_CAPS") :]
    block = block[: block.index("];")]
    pairs = re.findall(r"job:\s*'([^']+)'.*?timeoutMinutes:\s*(\d+)", block, re.DOTALL)
    if not pairs:
        gate.log_fail("no JOB_BUDGET_CAPS entries parsed from %s" % LANE_BUDGET)
    # A job's display name is the `name:` line directly under its two-space-indented id, in whichever workflow defines it (build-renet lives in ci-build-renet.yml; no YAML parser in the gate-test interpreter).
    workflow_texts = [p.read_text(encoding="utf-8") for p in sorted(CT_TESTS.parent.glob("*.yml"))]
    gate_caps = {}
    job_timeouts = {}
    for job_id, minutes in pairs:
        pattern = re.compile(r"^  %s:\n    name: (.+)$" % re.escape(job_id), re.MULTILINE)
        match = next((m for m in (pattern.search(t) for t in workflow_texts) if m), None)
        if match is None:
            gate.log_fail("check-lane-budget.ts caps job %s, which no workflow defines" % job_id)
            continue
        # The THIRD copy: the job's own `timeout-minutes:`. GitHub ends the job there whatever the watchdog allows, so 86580a281 raised validate-promote's cap to 20 in the two tables while ci.yml still killed it at 15.
        timeout = re.search(
            r"^  %s:\n(?:    .*\n|\s*\n)*?    timeout-minutes: (\d+)(?:[ \t]*#.*)?$"
            % re.escape(job_id),
            next(t for t in workflow_texts if pattern.search(t)),
            re.MULTILINE,
        )
        job_timeouts[job_id] = int(timeout.group(1)) if timeout else None
        # The watchdog keys a matrix job by its base name, so only a " (${{ matrix.x }})" suffix is dropped; a literal one such as "Renet (Full)" is part of the name.
        gate_caps[re.sub(r" \([^()]*\$\{\{[^()]*\)$", "", match.group(1).strip())] = int(minutes)
    gate.assert_eq(
        watchdog_caps, gate_caps, "the watchdog caps equal the lane gate's ruled timeouts"
    )
    gate.assert_eq(
        job_timeouts,
        {job_id: int(minutes) for job_id, minutes in pairs},
        "each capped job's workflow timeout-minutes equals its ruled cap",
    )
    gate.log_pass("watchdog JOB_BUDGET_CAPS agree with check-lane-budget.ts (%s)" % gate_caps)


# --- the real monitor, end to end ---------------------------------------------

# Argv: <watchdog> <fixture JSON>. The fixture names jobs by offsets in minutes from NOW, so the monitor's own Date.now() reads them as the test intends. Prints one JSON line: the actions taken, the step outputs, and the error/warning annotations.
MONITOR_JS = r"""
const realSetTimeout = setTimeout;
global.setTimeout = (fn, _ms, ...args) => realSetTimeout(fn, 5, ...args);
const monitor = require(process.argv[2]);
const fx = JSON.parse(process.argv[3]);
const now = Date.now();
const ago = (m) => new Date(now - m * 60000).toISOString();
// `steps` on a fixture job (optional) are offsets like the job's own; absent keeps the job step-less, the shape every pre-#f8b7f499 case was written against.
const jobs = fx.jobs.map((j, i) => ({
  id: 100 + i, name: j.name, status: j.status, conclusion: j.conclusion || null,
  started_at: ago(j.startedAgoMin),
  completed_at: j.status === 'completed' ? ago(j.startedAgoMin - j.durationMin) : null,
  ...(j.steps ? { steps: j.steps.map((s) => ({ name: s.name, status: s.status,
    conclusion: s.conclusion || null, started_at: ago(s.startedAgoMin),
    completed_at: s.status === 'completed' ? ago(s.startedAgoMin - s.durationMin) : null })) } : {}),
}));
const actions = [], outputs = {}, errors = [], warnings = [], annotationReads = [];
// `labels` on the fixture is one entry PER READ of the PR's labels, the last entry repeating: a list of names, or the string "ERROR" to make that read throw. Absent means every read answers "no labels".
const labelScript = fx.labels || [[]];
let labelReads = 0;
const github = {
  hook: { before: () => {} },
  paginate: async () => jobs,
  request: async (route) => {
    actions.push(route.includes('force-cancel') ? 'force-cancel'
      : route.includes('rerun-failed-jobs') ? 'rerun' : route);
    return {};
  },
  rest: {
    actions: {
      getWorkflowRun: async () => ({ data: { id: 999, status: fx.run.status, conclusion: null,
        run_attempt: fx.run.attempt || 1, event: fx.run.event, run_started_at: ago(fx.run.startedAgoMin),
        head_branch: 'b', workflow_id: 1, run_number: 1 } }),
      listJobsForWorkflowRun: () => {},
      // `newerRun` on the fixture run makes a newer run of the same workflow and branch exist.
      listWorkflowRuns: async () => ({ data: { workflow_runs: fx.run.newerRun ? [{ id: 1000, run_number: 2 }] : [] } }),
      downloadJobLogsForWorkflowRun: async () => ({ data: 'log line\n' }),
      cancelWorkflowRun: async () => { actions.push('cancel'); return {}; },
    },
    issues: {
      listLabelsOnIssue: async () => {
        const entry = labelScript[Math.min(labelReads, labelScript.length - 1)];
        labelReads += 1;
        if (entry === 'ERROR') throw new Error('labels unreadable');
        return { data: entry.map((name) => ({ name })) };
      },
    },
    // A job's check-run annotations: `annotations` (messages) on the fixture job, or `annotationsError` to make the read throw.
    checks: {
      listAnnotations: async ({ check_run_id }) => {
        const j = fx.jobs[check_run_id - 100];
        annotationReads.push(j.name);
        if (j.annotationsError) throw new Error(j.annotationsError);
        return { data: (j.annotations || []).map((message) => ({ annotation_level: 'failure', message })) };
      },
    },
  },
};
const summary = { addRaw() { return summary; }, write: async () => {} };
const core = {
  setFailed: (m) => actions.push('setFailed'),
  warning: (m) => warnings.push(String(m)),
  error: (m) => errors.push(String(m)),
  notice: () => {},
  setOutput: (k, v) => { outputs[k] = String(v); },
  info: () => {},
  summary,
};
const context = { repo: { owner: 'rediacc', repo: 'console' }, runId: 1, payload: {} };
Object.assign(process.env, fx.env);
monitor({ github, context, core })
  .then(() => console.log(JSON.stringify({ actions, outputs, errors, warnings, annotationReads, labelReads })))
  .catch((e) => { console.log(JSON.stringify({ threw: e.message })); process.exitCode = 3; });
"""

MONITOR_ENV = {
    "WATCHDOG_TARGET_RUN_ID": "999",
    "WATCHDOG_EXCLUDE_PATTERNS": "Watchdog,CI Complete,CI Verdict",
    "WATCHDOG_NO_RETRY_PATTERNS": "Quality,Review Gate",
    "WATCHDOG_INSTALL_VALIDATION_PATTERNS": "Validate Install Methods / Linux",
    "WATCHDOG_RETRY_ALLOWLIST_PATTERNS": "E2E,OPS,Fork Isolation,Migration Test",
    "WATCHDOG_WAIT_PATTERNS": "",
    "WATCHDOG_DEADLINE_SECONDS": "1",
    "WATCHDOG_JOB_BUDGET_MIN": "15",
    "WATCHDOG_RUN_BUDGET_MIN": "35",
    "WATCHDOG_BUDGET_MODE": "enforce",
    "WATCHDOG_RUN_BUDGET_MODE": "report",
    "CLOUDFLARE_API_TOKEN": "",
    "CLOUDFLARE_ACCOUNT_ID": "",
    "ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN": "",
}

LEG = "Tests + Infra / E2E Migrate (fedora-43, 1/8)"
# Healthy siblings, so a single cancelled job never trips the mass-cancellation guard (`cancelled >= completed / 2`).
SIBLINGS = [
    {
        "name": "Quality / Code (1/4)",
        "status": "completed",
        "conclusion": "success",
        "startedAgoMin": 20,
        "durationMin": 5,
    },
    {
        "name": "Quality / Static",
        "status": "completed",
        "conclusion": "success",
        "startedAgoMin": 20,
        "durationMin": 4,
    },
]


def run_monitor(
    gate, tmp_path: pathlib.Path, jobs, run, labels=None, watchdog=None, **env_overrides
) -> dict:
    """Drive the real monitor once; returns its trace plus the budget-violations.json it wrote (or None). `labels` scripts the PR's label reads (see MONITOR_JS) and makes the run a PR's. `watchdog` points at a mutant copy for a control; absent is the real module."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    script = tmp_path / "monitor.cjs"
    script.write_text(MONITOR_JS, encoding="utf-8")
    budget_dir = tmp_path / "budget"
    env = dict(MONITOR_ENV)
    env["WATCHDOG_BUDGET_DIR"] = str(budget_dir)
    env.update(env_overrides)
    fixture = {"jobs": jobs + SIBLINGS, "run": run, "env": env}
    if labels is not None:
        fixture["labels"] = labels
        env.setdefault("WATCHDOG_PR_NUMBER", "600")
    result = harness.run(
        ["node", str(script), str(watchdog or subject(gate)), json.dumps(fixture)], timeout=120
    )
    lines = [ln for ln in result.out.splitlines() if ln.startswith("{")]
    if not lines:
        gate.log_fail(
            "the monitor printed no trace (rc=%d); stderr: %s" % (result.rc, result.err[:400])
        )
    trace = json.loads(lines[-1])
    if "threw" in trace:
        gate.log_fail("the monitor threw: %s" % trace["threw"])
    report = budget_dir / "budget-violations.json"
    trace["budget"] = json.loads(report.read_text()) if report.is_file() else None
    trace["stdout"] = result.out
    return trace


def _live(name: str, minutes: float) -> dict:
    return {"name": name, "status": "in_progress", "startedAgoMin": minutes}


PR_RUN = {"status": "in_progress", "event": "pull_request", "startedAgoMin": 20}


def test_monitor_per_job_over_budget_force_cancels_with_the_annotation(gate, tmp_path):
    trace = run_monitor(gate, tmp_path, [_live(LEG, 16)], PR_RUN)
    gate.assert_eq(trace["actions"].count("force-cancel"), 1, "one force-cancel request")
    reason = trace["outputs"].get("by_design_reason", "")
    gate.assert_contains(
        reason,
        "CI BUDGET VIOLATION: '%s' ran 16.0m (budget 15m)" % LEG,
        "the roster annotation carries the T4.2 text",
    )
    gate.assert_eq(trace["outputs"].get("by_design_kind"), "pipeline-cancelled", "run cancelled")
    entries = trace["budget"]["violations"]
    gate.assert_eq(
        [(e["name"], e["enforced"]) for e in entries], [(LEG, True)], "JSON records it enforced"
    )
    gate.assert_contains(entries[0]["message"], "CI BUDGET VIOLATION: '", "with the same text")
    gate.assert_eq(trace["budget"]["jobMode"], "enforce", "and names the per-job mode")
    gate.log_pass("a live job over budget force-cancels the run with the T4.2 annotation")


def test_monitor_rollback_report_mode_cancels_nothing(gate, tmp_path):
    """The rollback is one env value: WATCHDOG_BUDGET_MODE back to 'report'. The SAME fixture as the case above must then cancel nothing and only warn."""
    trace = run_monitor(gate, tmp_path, [_live(LEG, 16)], PR_RUN, WATCHDOG_BUDGET_MODE="report")
    gate.assert_not_contains(" ".join(trace["actions"]), "force-cancel", "report mode: no cancel")
    gate.assert_not_contains(" ".join(trace["actions"]), "cancel", "not even a plain cancel")
    gate.assert_eq(trace["outputs"].get("continue"), "true", "the chain simply hands off")
    gate.assert_contains(
        " ".join(trace["warnings"]),
        "CI BUDGET VIOLATION (report-only): '%s'" % LEG,
        "the violation is still warned",
    )
    gate.assert_eq(trace["budget"]["violations"][0]["enforced"], False, "and recorded unenforced")
    gate.log_pass("rollback to report mode cancels nothing and still reports")


def test_monitor_exempt_job_under_its_cap_is_not_cancelled(gate, tmp_path):
    trace = run_monitor(gate, tmp_path, [_live("Tests + Infra / E2E K8s Multinode", 29)], PR_RUN)
    gate.assert_not_contains(" ".join(trace["actions"]), "cancel", "29m is under the 30m cap")
    gate.assert_eq(trace["budget"], None, "and no violation is recorded at all")
    gate.assert_eq(trace["outputs"].get("continue"), "true", "monitoring continues")
    gate.log_pass("E2E K8s Multinode at 29m (cap 30) is not cancelled")


def test_monitor_run_over_35_is_reported_not_cancelled(gate, tmp_path):
    """#a631eaf1: the whole pipeline at 40m, every job inside its budget, the per-job switch on enforce: warned and recorded, never cancelled."""
    run = {"status": "in_progress", "event": "pull_request", "startedAgoMin": 40}
    trace = run_monitor(gate, tmp_path, [_live(LEG, 5)], run)
    gate.assert_not_contains(" ".join(trace["actions"]), "cancel", "run-level is report-only")
    gate.assert_contains(
        " ".join(trace["warnings"]),
        "CI BUDGET VIOLATION (report-only): 'whole pipeline'",
        "the run overrun is warned",
    )
    entries = trace["budget"]["violations"]
    gate.assert_eq(
        [(e["kind"], e["enforced"], e["budgetMin"]) for e in entries],
        [("run", False, 35)],
        "recorded as an unenforced run violation against 35",
    )
    gate.log_pass("a 40m run is reported against 35, not cancelled")


def test_monitor_scheduled_run_is_recorded_never_cancelled(gate, tmp_path):
    """CANCEL_EXEMPT_EVENTS: a nightly over budget, per-job switch on enforce, is recorded and left to conclude -- cancelling would rewrite its conclusion to `cancelled`."""
    run = {"status": "in_progress", "event": "schedule", "startedAgoMin": 40}
    trace = run_monitor(gate, tmp_path, [_live(LEG, 16)], run)
    gate.assert_not_contains(" ".join(trace["actions"]), "cancel", "a scheduled run never cancels")
    gate.assert_eq(trace["outputs"].get("by_design_kind"), "left-uncancelled", "recorded as such")
    gate.assert_eq(trace["outputs"].get("continue"), "true", "and monitoring continues")
    kinds = sorted(e["kind"] for e in trace["budget"]["violations"])
    gate.assert_eq(kinds, ["job", "run"], "both overruns are in budget-violations.json")
    gate.log_pass("a scheduled run over budget is recorded, never cancelled")


def _cancelled_leg(minutes: float, **extra) -> dict:
    return {
        "name": LEG,
        "status": "completed",
        "conclusion": "cancelled",
        "startedAgoMin": minutes + 1,
        "durationMin": minutes,
        **extra,
    }


# GitHub's real wording, read 2026-09-30 from
# `gh api repos/rediacc/console/check-runs/106268923515/annotations`
# (Quality / Branch, run 35571489498, killed at its 12-minute timeout), with the
# duration swapped for the case at hand. The second line follows it there too.
TIMEOUT_ANNOTATIONS = [
    "The job has exceeded the maximum execution time of 5m0s",
    "The operation was canceled.",
]
# What a cancel by a newer push, a person or the watchdog leaves instead (read from job 109841885871 of run 36701282219).
FORCED_CANCEL_ANNOTATIONS = ["The run was canceled forcefully by @github-actions[bot]."]


def test_monitor_timeout_killed_leg_is_not_retried(gate, tmp_path):
    """T4.3, with STUCK_THRESHOLD_MIN UNSET so the module default is what is tested: a leg cancelled at 15m was killed by its timeout. At the old default of 60 it read as a flaky cancellation and was re-run."""
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    trace = run_monitor(gate, tmp_path, [_cancelled_leg(15)], run)
    gate.assert_not_contains(" ".join(trace["actions"]), "rerun", "a timeout kill is never retried")
    gate.assert_eq(trace["actions"].count("force-cancel"), 1, "it ends the run as a violation")
    gate.assert_contains(
        " ".join(trace["errors"]),
        "CI BUDGET VIOLATION: '%s' ran 15.0m (budget 15m)" % LEG,
        "annotated as a budget violation",
    )
    gate.assert_eq(trace["budget"]["violations"][0]["kind"], "timeout", "recorded as a timeout")
    gate.log_pass("a leg killed at its 15m timeout is a budget violation, not retried")


def test_control_an_early_cancellation_is_still_retried(gate, tmp_path):
    """The control: the same leg cancelled at 5m is an infra flake and IS retried. Without it, a monitor that never retried anything would pass the case above."""
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    trace = run_monitor(gate, tmp_path, [_cancelled_leg(5)], run)
    gate.assert_contains(" ".join(trace["actions"]), "rerun", "a 5m cancellation is retried")
    gate.assert_not_contains(" ".join(trace["actions"]), "force-cancel", "and nothing cancels")
    gate.log_pass("a leg cancelled at 5m is still retried")


def test_the_timeout_annotation_is_recognised_in_every_measured_spelling(gate):
    """The pure matcher against the durations GitHub actually wrote on this repo's jobs (12m0s, 15m0s, 20m0s, 45m0s, 6h0m0s) plus the older "running on runner" spelling; a forced cancel and an ordinary failure line must not match."""
    cases = {
        "The job has exceeded the maximum execution time of 5m0s": 5,
        "The job has exceeded the maximum execution time of 12m0s": 12,
        "The job has exceeded the maximum execution time of 45m0s": 45,
        "The job has exceeded the maximum execution time of 6h0m0s": 360,
        "The job running on runner GitHub Actions 7 has exceeded the maximum execution time of 30 minutes.": 30,
        "The run was canceled forcefully by @github-actions[bot].": None,
        "The operation was canceled.": None,
        "Process completed with exit code 1.": None,
    }
    result = harness.run(
        [
            "node",
            "-e",
            (
                "const m=require(process.argv[1]);"
                "process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map("
                "(message)=>{const k=m.findTimeoutKillAnnotation([{message}]);return k?k.timeoutMin:null;})))"
            ),
            str(subject(gate)),
            json.dumps(list(cases)),
        ]
    )
    gate.assert_exit(0, result, "findTimeoutKillAnnotation must be exported")
    gate.assert_eq(json.loads(result.out), list(cases.values()), "each message's parsed timeout")
    gate.log_pass("the timeout annotation matcher: %s" % cases)


def test_monitor_a_leg_killed_by_a_short_timeout_is_not_retried(gate, tmp_path):
    """The gap T4.3's threshold left: since ce8ac0ad5 a job may declare a 5-minute timeout, so a leg GitHub killed at 5 minutes and change (6m here) is under the 15-minute threshold. Its check run's timeout annotation, not its minutes, makes it a budget violation judged against the declared 5."""
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    trace = run_monitor(gate, tmp_path, [_cancelled_leg(6, annotations=TIMEOUT_ANNOTATIONS)], run)
    gate.assert_eq(trace["annotationReads"], [LEG], "the leg's annotations were read")
    gate.assert_not_contains(" ".join(trace["actions"]), "rerun", "a timeout kill is never retried")
    gate.assert_eq(trace["actions"].count("force-cancel"), 1, "it ends the run as a violation")
    gate.assert_contains(
        " ".join(trace["errors"]),
        "CI BUDGET VIOLATION: '%s' ran 6.0m (budget 5m)" % LEG,
        "annotated against the declared 5-minute timeout",
    )
    gate.assert_contains(
        " ".join(trace["errors"]),
        "The job has exceeded the maximum execution time of 5m0s",
        "quoting GitHub's own line",
    )
    gate.assert_eq(
        [(v["kind"], v["budgetMin"]) for v in trace["budget"]["violations"]],
        [("timeout", 5)],
        "recorded as a timeout against 5",
    )
    gate.log_pass("a 6m leg killed by a 5m timeout is a budget violation, not retried")


def test_control_a_short_leg_cancelled_by_a_newer_push_is_still_retried(gate, tmp_path):
    """The control: the SAME 6-minute leg, its annotations the forced-cancel line a newer push leaves instead of the timeout line, is a cancellation and IS retried. Without it, a monitor that read every annotated cancellation as a timeout would pass the case above."""
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    trace = run_monitor(
        gate, tmp_path, [_cancelled_leg(6, annotations=FORCED_CANCEL_ANNOTATIONS)], run
    )
    gate.assert_eq(trace["annotationReads"], [LEG], "the leg's annotations were read")
    gate.assert_contains(" ".join(trace["actions"]), "rerun", "a forced cancel is retried")
    gate.assert_not_contains(" ".join(trace["actions"]), "force-cancel", "and nothing cancels")
    gate.assert_eq(trace["budget"], None, "no budget violation is recorded")
    gate.log_pass("a 6m leg cancelled with no timeout annotation is still retried")


def test_monitor_a_failed_annotation_read_falls_back_to_the_threshold(gate, tmp_path):
    """A read that throws (no `checks: read`, an API error) must not become a verdict: the monitor logs it and falls back to STUCK_THRESHOLD_MIN. Driven both ways so the fallback is shown to be the threshold rather than a fixed answer: under the default 15 a 6m leg is retried; with the threshold at 5, the identical leg and failing read is a violation."""
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    leg = _cancelled_leg(
        6, annotations=TIMEOUT_ANNOTATIONS, annotationsError="Resource not accessible"
    )
    under = run_monitor(gate, tmp_path / "under", [leg], run)
    gate.assert_eq(under["annotationReads"], [LEG], "the read was attempted")
    gate.assert_contains(
        under["stdout"],
        'could not read "%s"\'s check-run annotations (Resource not accessible); '
        "falling back to the 15m stuck-threshold" % LEG,
        "the failed read is logged with the fallback it takes",
    )
    gate.assert_contains(" ".join(under["actions"]), "rerun", "under the threshold: retried")

    over = run_monitor(gate, tmp_path / "over", [leg], run, STUCK_THRESHOLD_MIN="5")
    gate.assert_eq(over["annotationReads"], [], "at or over the threshold nothing is read")
    gate.assert_not_contains(" ".join(over["actions"]), "rerun", "over the threshold: not retried")
    gate.assert_contains(
        " ".join(over["errors"]),
        "CI BUDGET VIOLATION: '%s' ran 6.0m (budget 5m)" % LEG,
        "the threshold path judges it",
    )
    gate.log_pass("a failed annotation read is logged and falls back to the stuck-threshold")


def test_watchdog_workflow_wires_the_p4_budget_env(gate):
    """Anti-vacuity against the real workflow: per-job enforce, run-level report against 35 (D-W1), and the 15-minute stuck threshold (T4.3)."""
    if not WORKFLOW.is_file():
        gate.log_fail(
            "the workflow that drives the watchdog is missing: %s"
            % paths.relative_to_root(WORKFLOW)
        )
    text = WORKFLOW.read_text(encoding="utf-8")
    gate.assert_contains(text, "WATCHDOG_BUDGET_MODE: 'enforce'", "T4.2: per-job budget enforced")
    gate.assert_contains(
        text, "WATCHDOG_RUN_BUDGET_MODE: 'report'", "#a631eaf1: run-level stays report-only"
    )
    gate.assert_contains(text, "WATCHDOG_JOB_BUDGET_MIN: '15'", "the per-job budget is 15")
    gate.assert_contains(text, "WATCHDOG_RUN_BUDGET_MIN: '35'", "D-W1: the pipeline target is 35")
    gate.assert_contains(text, "STUCK_THRESHOLD_MIN: '15'", "T4.3: the stuck threshold is 15")
    gate.log_pass("watchdog-monitor.yml wires per-job enforce, run-level report at 35, stuck 15")


_WATCHDOG_DISPATCH_RE = re.compile(
    r"rediacc_ci\.ci\.dispatch_watchdog\s+--run-id\s+\"\$(\w+)\"", re.MULTILINE
)
HOUSEKEEPING = paths.from_root(".github", "workflows", "housekeeping.yml")


def _watchdog_targets(text: str) -> list[str]:
    """The shell variable each `dispatch_watchdog --run-id "$VAR"` call in one workflow passes."""
    return _WATCHDOG_DISPATCH_RE.findall(text)


def test_the_watchdog_never_watches_housekeeping(gate):
    """Housekeeping's gate-costs-capture job is allowed 50 minutes (784c0c80e: bounded quick phase 12 + slow-gate rotation 32; operator ruling 2026-10-07, "Keep 50 min + rotation"), far over the 15-minute per-job budget.
    It needs no JOB_BUDGET_CAPS entry ONLY because the watchdog never monitors a housekeeping run: the chain is started by ci.yml's CI Watchdog job on ci.yml's own run ($GITHUB_RUN_ID) and re-dispatched by watchdog-monitor.yml on the same target ($TARGET_RUN_ID), and `monitor()` reads and cancels jobs of that target run alone.
    If anything starts the chain from another workflow, or ci.yml calls housekeeping.yml as a reusable workflow (its jobs would then sit inside the monitored run), the 50-minute job falls under the 15-minute budget and this reds."""
    gate.assert_eq(
        _watchdog_targets(
            '  PYTHONPATH=.ci python3 -m rediacc_ci.ci.dispatch_watchdog --run-id "$X" \\\n'
        ),
        ["X"],
        "CONTROL: the matcher finds a dispatch and the variable it targets",
    )
    starters = {}
    for wf in sorted(WORKFLOW.parent.glob("*.yml")):
        found = _watchdog_targets(wf.read_text(encoding="utf-8"))
        if found:
            starters[wf.name] = found
    gate.assert_eq(
        starters,
        {"ci.yml": ["GITHUB_RUN_ID"], "watchdog-monitor.yml": ["TARGET_RUN_ID"]},
        "the watchdog chain starts only on ci.yml's own run and re-targets only that run",
    )
    ci_text = paths.from_root(".github", "workflows", "ci.yml").read_text(encoding="utf-8")
    gate.assert_eq(
        "housekeeping.yml" in "".join(re.findall(r"^\s*uses:\s*(\S+)", ci_text, re.MULTILINE)),
        False,
        "ci.yml does not call housekeeping.yml as a reusable workflow",
    )
    hk = HOUSEKEEPING.read_text(encoding="utf-8")
    gate.assert_eq(_watchdog_targets(hk), [], "housekeeping.yml does not start the watchdog chain")
    timeout = re.search(
        r"^  gate-costs-capture:\n(?:    .*\n|\s*\n)*?    timeout-minutes: (\d+)", hk, re.MULTILINE
    )
    gate.assert_eq(
        int(timeout.group(1)) if timeout else None,
        50,
        "gate-costs-capture keeps its ruled 50-minute timeout (784c0c80e)",
    )
    gate.log_pass(
        "watchdog starters %s; housekeeping's 50-minute capture sits outside every watched run"
        % starters
    )


# --- the hold-open label (`no-auto-cancel`) against the real monitor ----------
#
# WHAT THE LABEL IS FOR. A PR run is cancelled at its first real job failure. Twice on 2026-10-13 a `Quality / Secure Storage` leg failed within seconds on PR 600 and the other 87 jobs were cancelled with no verdict, so each fix cost a full extra round. With the label on the PR a FAILED job cancels nothing: the run finishes and concludes `failure` by itself.
#
# WHAT IT MUST NOT DO, and these are the controls: hold a run open without the label; hold back a LIVE job over its time budget; start a rerun the `no-auto-retry` label forbids. It is read at the decision, so a label added to (or taken off) a PR whose run already started counts at the next failure.

HOLD = "no-auto-cancel"
# The leg that failed within seconds on 2026-10-13. `Quality` is a no-retry pattern, so this takes the fast-fail branch.
QUALITY_LEG = "Quality / Secure Storage (macos-latest)"
# Neither no-retry nor on the retry allowlist: with the classifier absent it fails fast (branch 4).
BUILD_LEG = "Build (CLI) / Cross Compile"
# A long leg still running when the failure lands: the job a cancel would silence.
RUNNING_LEG = "Tests + Infra / E2E K8s"


def _failed(name: str) -> dict:
    return {
        "name": name,
        "status": "completed",
        "conclusion": "failure",
        "startedAgoMin": 3,
        "durationMin": 1,
    }


def _cancels(trace: dict) -> int:
    """Every cancel the monitor asked for: the force-cancel request and its plain-cancel fallback."""
    return sum(1 for a in trace["actions"] if a in ("force-cancel", "cancel"))


def test_control_without_the_label_a_first_failure_still_cancels_the_run(gate, tmp_path):
    """THE CONTROL the label cases stand on: the same fixtures, no label, cancel exactly as before. Without it a monitor that never cancelled anything would pass every hold-open case below."""
    for leg in (QUALITY_LEG, BUILD_LEG):
        trace = run_monitor(
            gate, tmp_path / leg[:5], [_failed(leg), _live(RUNNING_LEG, 5)], PR_RUN, labels=[[]]
        )
        gate.assert_eq(trace["actions"], ["force-cancel"], "%s: one cancel, nothing else" % leg)
        gate.assert_eq(trace["outputs"].get("by_design_kind"), "pipeline-cancelled", "recorded")
        gate.assert_eq(trace["outputs"].get("continue"), None, "and the chain ends")
    gate.log_pass("without the label a first failure cancels the run (2 legs)")


def test_with_the_label_a_first_failure_leaves_the_other_jobs_running(gate, tmp_path):
    """A failed job, a long leg still running, the label on the PR: no cancel of any kind, no rerun, the failure still named, and the chain keeps monitoring. No cancel is what keeps the verdict red: the run concludes `failure` from its own failed job instead of `cancelled`."""
    for leg in (QUALITY_LEG, BUILD_LEG):
        trace = run_monitor(
            gate, tmp_path / leg[:5], [_failed(leg), _live(RUNNING_LEG, 5)], PR_RUN, labels=[[HOLD]]
        )
        gate.assert_eq(trace["actions"], [], "%s: no cancel, no rerun, no setFailed" % leg)
        gate.assert_eq(trace["outputs"].get("by_design_kind"), "left-uncancelled", "recorded")
        gate.assert_contains(
            trace["outputs"].get("by_design_reason", ""),
            'Job failed: "%s"' % leg,
            "the failed job is still named in the annotation",
        )
        gate.assert_eq(trace["outputs"].get("continue"), "true", "and monitoring continues")
        gate.assert_contains(trace["stdout"], "NOT cancelling run 999", "the banner says why")
    gate.log_pass("with the label a first failure cancels nothing and is still annotated (2 legs)")


def test_the_label_does_not_hold_back_a_live_job_over_its_budget(gate, tmp_path):
    """Budgets are enforced under the label: the fixture of the first monitor case, plus the label, still force-cancels with the T4.2 text."""
    trace = run_monitor(gate, tmp_path, [_live(LEG, 16)], PR_RUN, labels=[[HOLD]])
    gate.assert_eq(trace["actions"], ["force-cancel"], "a live job at 16m of 15 cancels the run")
    gate.assert_contains(
        trace["outputs"].get("by_design_reason", ""),
        "CI BUDGET VIOLATION: '%s' ran 16.0m (budget 15m)" % LEG,
        "with the budget annotation",
    )
    gate.assert_eq(trace["outputs"].get("by_design_kind"), "pipeline-cancelled", "run cancelled")
    gate.log_pass("the label does not exempt a live job over its budget")


def test_control_the_label_holds_a_job_inside_its_budget_and_a_failure_beside_it(gate, tmp_path):
    """The other direction of the case above: a failed job beside a live job INSIDE its budget is held open, so the budget cancel is the budget's doing and not a label that stopped working."""
    trace = run_monitor(
        gate, tmp_path, [_failed(BUILD_LEG), _live(LEG, 14)], PR_RUN, labels=[[HOLD]]
    )
    gate.assert_eq(_cancels(trace), 0, "14m of 15 is inside the budget: nothing cancels")
    gate.assert_eq(trace["budget"], None, "and no violation is recorded")
    gate.log_pass("a failure beside a job inside its budget is held open")


def test_a_label_added_after_the_run_started_is_honoured(gate, tmp_path):
    """The first read (generation start) finds no label, every later read finds it: the failure is judged on the labels as they are AT THE DECISION. One read per generation cancelled this run."""
    trace = run_monitor(
        gate, tmp_path, [_failed(BUILD_LEG), _live(RUNNING_LEG, 5)], PR_RUN, labels=[[], [HOLD]]
    )
    if trace["labelReads"] < 2:
        gate.log_fail(
            "the monitor read the PR labels %d time(s); a label added mid-run needs a read at the decision"
            % trace["labelReads"]
        )
    gate.assert_eq(_cancels(trace), 0, "the label added mid-run holds the run open")
    gate.assert_eq(trace["outputs"].get("by_design_kind"), "left-uncancelled", "recorded as held")
    gate.log_pass(
        "a label added after the first read holds the run (%d reads)" % trace["labelReads"]
    )


def test_a_label_removed_after_the_run_started_stops_holding(gate, tmp_path):
    """The mirror: on the PR at start, gone by the failure. The run cancels, which is how taking the label off to drive a branch to green takes effect without a new push."""
    trace = run_monitor(
        gate, tmp_path, [_failed(BUILD_LEG), _live(RUNNING_LEG, 5)], PR_RUN, labels=[[HOLD], []]
    )
    gate.assert_eq(trace["actions"], ["force-cancel"], "the label is gone, so the run cancels")
    gate.log_pass("a label removed after the first read no longer holds the run")


def test_an_unreadable_label_list_keeps_the_last_one_read(gate, tmp_path):
    """A failed read at the decision must not read as "no labels": the list from the last good read stands, in both directions."""
    held = run_monitor(
        gate, tmp_path / "held", [_failed(BUILD_LEG)], PR_RUN, labels=[[HOLD], "ERROR"]
    )
    gate.assert_eq(_cancels(held), 0, "label read once, then unreadable: still held")
    gate.assert_contains(held["stdout"], "keeping the last list read", "and the fallback is said")
    plain = run_monitor(
        gate, tmp_path / "plain", [_failed(BUILD_LEG)], PR_RUN, labels=[[], "ERROR"]
    )
    gate.assert_eq(plain["actions"], ["force-cancel"], "CONTROL: no label read, then unreadable")
    gate.log_pass("an unreadable label list keeps the last list read, held or not")


def test_the_label_holds_a_run_past_a_timeout_killed_leg_without_retrying_it(gate, tmp_path):
    """A leg GitHub already killed at its timeout is dead: cancelling reclaims nothing from it. Under the label the run stays open, the violation is still annotated, and the leg is still never retried."""
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    trace = run_monitor(gate, tmp_path, [_cancelled_leg(15)], run, labels=[[HOLD]])
    gate.assert_eq(trace["actions"], [], "no cancel and no rerun")
    gate.assert_contains(
        " ".join(trace["errors"]),
        "CI BUDGET VIOLATION: '%s' ran 15.0m (budget 15m)" % LEG,
        "still annotated as a budget violation",
    )
    gate.log_pass("a timeout-killed leg under the label: held open, annotated, not retried")


def test_auto_retry_under_the_label_reruns_failed_jobs_and_never_cancels(gate, tmp_path):
    """Auto-retry is unchanged by the label: an allowlisted leg's failure holds a pending rerun, and once the held-open run completes its failed jobs are rerun. No cancel is part of it."""
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    trace = run_monitor(gate, tmp_path, [_failed(RUNNING_LEG)], run, labels=[[HOLD]])
    gate.assert_eq(trace["actions"], ["rerun"], "the failed jobs are rerun, nothing is cancelled")
    gate.assert_eq(trace["outputs"].get("rerun_executed"), "true", "and the chain follows it")
    gate.log_pass("under the label a retryable failure is rerun after the run completes")


def test_no_auto_retry_beside_the_label_neither_reruns_nor_cancels(gate, tmp_path):
    """Both labels: `no-auto-retry` turns the rerun off and the hold-open label turns the cancel off, so the run simply finishes red. The control half is `no-auto-retry` alone, which cancels."""
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    both = run_monitor(
        gate, tmp_path / "both", [_failed(RUNNING_LEG)], run, labels=[[HOLD, "no-auto-retry"]]
    )
    gate.assert_eq(both["actions"], [], "no rerun and no cancel")
    alone = run_monitor(
        gate, tmp_path / "alone", [_failed(RUNNING_LEG)], run, labels=[["no-auto-retry"]]
    )
    gate.assert_eq(alone["actions"], ["force-cancel"], "CONTROL: no-auto-retry alone cancels")
    gate.log_pass("no-auto-retry beside the label: the run finishes red, untouched")


# --- ruling #f8b7f499: an infra-step stall is retried, a test-step stall is not --------
#
# Run 39766647743 (PR #601) lost three attempts with nothing failing, each one a budget overrun in a step that was slow because the RUNNER was: 'Setup KVM Host', 'Install clang for BPF compilation' (apt) and 'Build and push'. The ruling sends a stall in such a step down the transient retry path, capped by MAX_ATTEMPTS, and leaves a slow TEST step on T4.3's no-retry cancel.
#
# THE CONTROLS ARE A MUTANT, not a second fixture. `_mutant` writes a copy of the watchdog whose `isInfraStep` always answers false -- the module as it was before the ruling, as far as these paths can tell -- and the retry cases are driven against it too: each must then cancel the pipeline. A case that passes against the mutant was never testing the new branch.

OBSERVED_INFRA_STEPS = ["Setup KVM Host", "Install clang for BPF compilation", "Build and push"]
TEST_STEPS = [
    "Run E2E Tests",
    "Python package tests",
    "Test APT Installation",
    "Install-script tests",
    "Install table",
    "Create E2E Test Environment",
    "",
]
INFRA_RETURN = "return patterns.some((re) => re.test(stepName));"
WELL_KNOWN = paths.from_root("scripts", "ci", "well-known.cjs")


def _step_sources() -> list[pathlib.Path]:
    """Every workflow and composite action, read as DATA (the step names a pattern must still match). A function, not a module-level glob: nothing here is run per file, so this module is not a fan-out driver (test_gate_fanout_timeout_declarable.is_fanout_driver keys on an import-time glob)."""
    return [
        *sorted(paths.from_root(".github", "workflows").glob("*.yml")),
        *sorted(paths.from_root(".github", "actions").glob("*/action.yml")),
    ]


_STEP_NAME_RE = re.compile(r"^\s*-\s+name:\s*(.+?)\s*$", re.MULTILINE)


def _mutant(gate, tmp_path: pathlib.Path) -> pathlib.Path:
    """A copy of the watchdog with `isInfraStep` answering false, laid out so its relative `require` of well-known.cjs still resolves."""
    text = subject(gate).read_text(encoding="utf-8")
    gate.assert_eq(text.count(INFRA_RETURN), 1, "the mutation anchor exists exactly once")
    target = tmp_path / "mutant" / ".ci" / "scripts" / "ci" / "watchdog-monitor.cjs"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.replace(INFRA_RETURN, "return false;"), encoding="utf-8")
    link = tmp_path / "mutant" / "scripts" / "ci" / "well-known.cjs"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(WELL_KNOWN)
    return target


def _node_eval(gate, js: str, *args: str):
    result = harness.run(["node", "-e", js, str(subject(gate)), *args])
    gate.assert_exit(0, result, "the watchdog's exports must be drivable")
    return json.loads(result.out)


def _stalled_live(name: str, step: str, minutes: float = 15.1) -> dict:
    """A live job `minutes` in, its current step `step` started 6.6 minutes ago (run 39766647743, gen 2)."""
    return {
        "name": name,
        "status": "in_progress",
        "startedAgoMin": minutes,
        "steps": [
            {
                "name": "Set up job",
                "status": "completed",
                "conclusion": "success",
                "startedAgoMin": minutes,
                "durationMin": 0.2,
            },
            {"name": step, "status": "in_progress", "startedAgoMin": 6.6},
        ],
    }


def _killed(name: str, step: str, minutes: float = 15) -> dict:
    """A job GitHub killed at its timeout in `step`; the runner still ran the post steps after it."""
    return {
        "name": name,
        "status": "completed",
        "conclusion": "cancelled",
        "startedAgoMin": minutes + 1,
        "durationMin": minutes,
        "steps": [
            {
                "name": "Set up job",
                "status": "completed",
                "conclusion": "success",
                "startedAgoMin": minutes + 1,
                "durationMin": 0.2,
            },
            {
                "name": step,
                "status": "completed",
                "conclusion": "cancelled",
                "startedAgoMin": minutes - 5,
                "durationMin": minutes - 5.9,
            },
            {
                "name": "Post Run actions/checkout",
                "status": "completed",
                "conclusion": "success",
                "startedAgoMin": 1.05,
                "durationMin": 0.02,
            },
            {
                "name": "Complete job",
                "status": "completed",
                "conclusion": "success",
                "startedAgoMin": 1.02,
                "durationMin": 0.01,
            },
        ],
    }


PROBE_LEG = "E2E Dependency Probe / E2E Probe (18-ops-workflow.test.ts)"


def _assert_retried_not_cancelled(gate, trace: dict, step: str) -> None:
    gate.assert_not_contains(" ".join(trace["actions"]), "cancel", "the pipeline is not cancelled")
    gate.assert_eq(trace["outputs"].get("by_design_kind"), "rerun-pending", "a rerun is held")
    gate.assert_contains(" ".join(trace["errors"]), "INFRA STALL, RETRIED", "loudly annotated")
    gate.assert_contains(" ".join(trace["errors"]), "'%s'" % step, "naming the stalled step")


def _assert_cancelled_without_retry(gate, trace: dict) -> None:
    gate.assert_eq(trace["actions"].count("force-cancel"), 1, "the pipeline is cancelled")
    gate.assert_not_contains(" ".join(trace["actions"]), "rerun", "and nothing is re-run")
    gate.assert_not_contains(" ".join(trace["errors"]), "INFRA STALL, RETRIED", "no retry claim")
    gate.assert_eq(trace["outputs"].get("pending_rerun"), None, "no pending rerun handed on")


def test_infra_step_classifier_on_the_observed_and_the_test_steps(gate):
    verdict = _node_eval(
        gate,
        "const m=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map((s)=>m.isInfraStep(s))))",
        json.dumps(OBSERVED_INFRA_STEPS + TEST_STEPS),
    )
    gate.assert_eq(
        verdict,
        [True] * len(OBSERVED_INFRA_STEPS) + [False] * len(TEST_STEPS),
        "the three steps of run 39766647743 are infra; test and gate steps are not",
    )
    gate.log_pass("isInfraStep: %s infra, %s not" % (OBSERVED_INFRA_STEPS, TEST_STEPS))


def test_every_infra_pattern_names_a_step_that_exists(gate):
    """Anti-drift: a pattern no workflow step matches is a rename the list did not follow, and its stall is silently back on the no-retry cancel."""
    names = sorted(
        {
            m.group(1).strip("'\"")
            for f in _step_sources()
            for m in _STEP_NAME_RE.finditer(f.read_text(encoding="utf-8"))
        }
    )
    gate.assert_eq(len(names) > 100, True, "the workflow step names were read (%d)" % len(names))
    unmatched = _node_eval(
        gate,
        "const m=require(process.argv[1]);const names=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(m.INFRA_STEP_PATTERNS"
        ".filter((re)=>!names.some((n)=>re.test(n))).map((re)=>re.source)))",
        json.dumps(names),
    )
    gate.assert_eq(unmatched, [], "every INFRA_STEP_PATTERNS entry matches a real step name")
    gate.log_pass("every infra pattern names a step in .github/workflows or .github/actions")


def test_the_stalled_step_of_a_killed_job_is_the_cancelled_one_not_the_teardown(gate):
    names = _node_eval(
        gate,
        "const m=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map((j)=>m.stalledStep(j)?.name ?? null)))",
        json.dumps(
            [
                {"steps": [{"name": "a", "conclusion": "success", "started_at": T0}]},
                {
                    "steps": [
                        {"name": "Setup KVM Host", "conclusion": "cancelled", "started_at": T0},
                        {"name": "Complete job", "conclusion": "success", "started_at": T0},
                    ]
                },
                {"steps": []},
            ]
        ),
    )
    gate.assert_eq(names, ["a", "Setup KVM Host", None], "the cancelled step, not 'Complete job'")
    gate.log_pass("stalledStep names the step the timeout cancelled")


def test_monitor_live_infra_stall_at_attempt_1_is_retried_not_cancelled(gate, tmp_path):
    trace = run_monitor(gate, tmp_path, [_stalled_live(PROBE_LEG, "Setup KVM Host")], PR_RUN)
    _assert_retried_not_cancelled(gate, trace, "Setup KVM Host")
    gate.assert_eq(trace["outputs"].get("pending_rerun"), "true", "handed to the next generation")
    gate.assert_eq(
        [(v["name"], v["enforced"]) for v in trace["budget"]["violations"]],
        [(PROBE_LEG, True)],
        "the overrun is still recorded as an enforced violation",
    )
    gate.log_pass("a live overrun in 'Setup KVM Host' at attempt 1 holds a rerun, cancels nothing")


def test_control_live_infra_stall_cancels_when_the_classifier_is_disabled(gate, tmp_path):
    mutant = _mutant(gate, tmp_path)
    trace = run_monitor(
        gate, tmp_path, [_stalled_live(PROBE_LEG, "Setup KVM Host")], PR_RUN, watchdog=mutant
    )
    _assert_cancelled_without_retry(gate, trace)
    gate.log_pass("CONTROL: with isInfraStep disabled the same fixture cancels the pipeline")


def test_monitor_live_infra_stall_at_attempt_2_cancels_without_retry(gate, tmp_path):
    run = dict(PR_RUN, attempt=2)
    trace = run_monitor(gate, tmp_path, [_stalled_live(PROBE_LEG, "Setup KVM Host")], run)
    _assert_cancelled_without_retry(gate, trace)
    gate.assert_contains(trace["stdout"], "already at attempt 2/2", "the cap is the reason")
    gate.log_pass("at attempt 2 (MAX_ATTEMPTS) an infra stall cancels without retry")


def test_monitor_live_infra_stall_with_a_newer_run_cancels_without_retry(gate, tmp_path):
    run = dict(PR_RUN, newerRun=True)
    trace = run_monitor(gate, tmp_path, [_stalled_live(PROBE_LEG, "Setup KVM Host")], run)
    _assert_cancelled_without_retry(gate, trace)
    gate.log_pass("a superseded head is never re-run for an infra stall")


def test_monitor_live_infra_stall_under_no_auto_retry_cancels(gate, tmp_path):
    trace = run_monitor(
        gate,
        tmp_path,
        [_stalled_live(PROBE_LEG, "Install clang for BPF compilation")],
        PR_RUN,
        labels=[["no-auto-retry"]],
    )
    _assert_cancelled_without_retry(gate, trace)
    gate.log_pass("the no-auto-retry label keeps an infra stall on the cancel path")


def test_monitor_live_test_step_overrun_at_attempt_1_cancels_without_retry(gate, tmp_path):
    """T4.3 preserved. Its control is the infra case above: the same job, attempt and minutes, only the step differs."""
    trace = run_monitor(gate, tmp_path, [_stalled_live(PROBE_LEG, "Run E2E Tests")], PR_RUN)
    _assert_cancelled_without_retry(gate, trace)
    gate.log_pass("a live overrun in a test step at attempt 1 still cancels without retry")


def test_monitor_live_mixed_infra_and_test_overruns_cancel(gate, tmp_path):
    jobs = [
        _stalled_live(PROBE_LEG, "Setup KVM Host"),
        _stalled_live("E2E Dependency Probe / E2E Probe (04)", "Run E2E Tests"),
    ]
    trace = run_monitor(gate, tmp_path, jobs, PR_RUN)
    _assert_cancelled_without_retry(gate, trace)
    gate.log_pass("one test-step overrun beside an infra stall keeps the pipeline cancel")


def test_monitor_pending_rerun_still_cancels_a_later_test_step_overrun(gate, tmp_path):
    """Review 8aaf3a8e.1: a generation that inherits a pending rerun (an infra hold, or a transient classification) skipped enforcement entirely, so a test-step overrun arriving later was recorded as enforced and never cancelled."""
    trace = run_monitor(
        gate,
        tmp_path,
        [_stalled_live(PROBE_LEG, "Run E2E Tests")],
        PR_RUN,
        WATCHDOG_PENDING_RERUN="true",
    )
    _assert_cancelled_without_retry(gate, trace)
    gate.log_pass("a pending rerun does not shield a later test-step overrun from the cancel")


def test_monitor_pending_rerun_keeps_holding_for_a_later_infra_stall(gate, tmp_path):
    """The other half: a second infra stall during the hold is already covered by the pending rerun, so it cancels nothing."""
    trace = run_monitor(
        gate,
        tmp_path,
        [_stalled_live(PROBE_LEG, "Setup KVM Host")],
        PR_RUN,
        WATCHDOG_PENDING_RERUN="true",
    )
    gate.assert_eq(trace["outputs"].get("pending_rerun"), "true", "the hold is handed on")
    gate.assert_not_contains(trace["stdout"], "Budget enforcement:", "no enforcement fires")
    gate.log_pass("a later infra stall during a pending rerun keeps holding")


def test_monitor_timeout_kill_in_an_infra_step_is_retried(gate, tmp_path):
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    trace = run_monitor(gate, tmp_path, [_killed(LEG, "Install clang for BPF compilation")], run)
    gate.assert_contains(" ".join(trace["actions"]), "rerun", "the killed job is re-run")
    _assert_retried_not_cancelled(gate, trace, "Install clang for BPF compilation")
    gate.assert_eq(trace["budget"]["violations"][0]["kind"], "timeout", "still recorded")
    gate.log_pass("a timeout kill in an infra step goes to the retry path")


def test_control_timeout_kill_in_an_infra_step_cancels_when_the_classifier_is_disabled(
    gate, tmp_path
):
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    mutant = _mutant(gate, tmp_path)
    trace = run_monitor(
        gate,
        tmp_path,
        [_killed(LEG, "Install clang for BPF compilation")],
        run,
        watchdog=mutant,
    )
    _assert_cancelled_without_retry(gate, trace)
    gate.log_pass("CONTROL: with isInfraStep disabled the same timeout kill is not retried")


def test_monitor_timeout_kill_in_a_test_step_is_not_retried(gate, tmp_path):
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20}
    trace = run_monitor(gate, tmp_path, [_killed(LEG, "Run E2E Tests")], run)
    _assert_cancelled_without_retry(gate, trace)
    gate.assert_contains(
        " ".join(trace["errors"]), "in step 'Run E2E Tests'", "the error names the stalled step"
    )
    gate.log_pass("a timeout kill in a test step is still a no-retry cancel")


def test_monitor_timeout_kill_in_an_infra_step_at_attempt_2_is_not_retried(gate, tmp_path):
    run = {"status": "completed", "event": "pull_request", "startedAgoMin": 20, "attempt": 2}
    trace = run_monitor(gate, tmp_path, [_killed(LEG, "Setup KVM Host")], run)
    _assert_cancelled_without_retry(gate, trace)
    gate.log_pass("at attempt 2 a timeout kill in an infra step is not retried")

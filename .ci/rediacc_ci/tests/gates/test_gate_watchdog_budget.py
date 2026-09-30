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
    """WATCHDOG_EXCLUDE_PATTERNS (Watchdog, CI Complete, Review Complete): aggregators and observers are not budgeted work, and without this exclusion the watchdog's own chain generations would budget-flag themselves."""
    verdict = evaluate(
        gate,
        jobs=[{"name": "CI Watchdog", "status": "in_progress", "started_at": T0}],
        run=None,
        nowMs=int(_ms(45, 0)),
        jobBudgetMin=15,
        runBudgetMin=None,
        excludePatterns=["Watchdog", "CI Complete", "Review Complete"],
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
        "Tests + Infra / E2E Workers (fedora-43, 1/8)": 18,
        "Tests + Infra / E2E Ceph Workers": 18,
        "Tests + Infra / E2E Ceph Workers non-apt (oracle-10)": 20,
        "Tests + Infra / E2E Migrate (fedora-43)": 15,
    }
    result = harness.run(
        [
            "node",
            "-e",
            "const m=require(process.argv[1]);"
            "process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map((n)=>m.jobBudgetFor(n,15))))",
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
    for job_id, minutes in pairs:
        pattern = re.compile(r"^  %s:\n    name: (.+)$" % re.escape(job_id), re.MULTILINE)
        match = next((m for m in (pattern.search(t) for t in workflow_texts) if m), None)
        if match is None:
            gate.log_fail("check-lane-budget.ts caps job %s, which no workflow defines" % job_id)
            continue
        # The watchdog keys a matrix job by its base name, so only a " (${{ matrix.x }})" suffix is dropped; a literal one such as "Renet (Full)" is part of the name.
        gate_caps[re.sub(r" \([^()]*\$\{\{[^()]*\)$", "", match.group(1).strip())] = int(minutes)
    gate.assert_eq(
        watchdog_caps, gate_caps, "the watchdog caps equal the lane gate's ruled timeouts"
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
const jobs = fx.jobs.map((j, i) => ({
  id: 100 + i, name: j.name, status: j.status, conclusion: j.conclusion || null,
  started_at: ago(j.startedAgoMin),
  completed_at: j.status === 'completed' ? ago(j.startedAgoMin - j.durationMin) : null,
}));
const actions = [], outputs = {}, errors = [], warnings = [];
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
        run_attempt: 1, event: fx.run.event, run_started_at: ago(fx.run.startedAgoMin),
        head_branch: 'b', workflow_id: 1, run_number: 1 } }),
      listJobsForWorkflowRun: () => {},
      listWorkflowRuns: async () => ({ data: { workflow_runs: [] } }),
      downloadJobLogsForWorkflowRun: async () => ({ data: 'log line\n' }),
      cancelWorkflowRun: async () => { actions.push('cancel'); return {}; },
    },
    issues: { listLabelsOnIssue: async () => ({ data: [] }) },
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
  .then(() => console.log(JSON.stringify({ actions, outputs, errors, warnings })))
  .catch((e) => { console.log(JSON.stringify({ threw: e.message })); process.exitCode = 3; });
"""

MONITOR_ENV = {
    "WATCHDOG_TARGET_RUN_ID": "999",
    "WATCHDOG_EXCLUDE_PATTERNS": "Watchdog,CI Complete,Review Complete",
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


def run_monitor(gate, tmp_path: pathlib.Path, jobs, run, **env_overrides) -> dict:
    """Drive the real monitor once; returns its trace plus the budget-violations.json it wrote (or None)."""
    script = tmp_path / "monitor.cjs"
    script.write_text(MONITOR_JS, encoding="utf-8")
    budget_dir = tmp_path / "budget"
    env = dict(MONITOR_ENV)
    env["WATCHDOG_BUDGET_DIR"] = str(budget_dir)
    env.update(env_overrides)
    fixture = {"jobs": jobs + SIBLINGS, "run": run, "env": env}
    result = harness.run(
        ["node", str(script), str(subject(gate)), json.dumps(fixture)], timeout=120
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


def _cancelled_leg(minutes: float) -> dict:
    return {
        "name": LEG,
        "status": "completed",
        "conclusion": "cancelled",
        "startedAgoMin": minutes + 1,
        "durationMin": minutes,
    }


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

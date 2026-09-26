"""The CI time budget verdict in `.ci/scripts/ci/watchdog-monitor.cjs` (operator spec W, `agent/plans/PLAN-ci-time-budget.md` T1.1-T1.5): every job finishes in 15 minutes or less, and the whole pipeline in 20 minutes or less.

`evaluateBudget` is the pure decision function this suite drives directly, the same way `evaluateSupersession` and `evaluateCancelExemption` are already driven elsewhere in this family -- NOT a mirror of the boolean, but the exported function itself, so a reordered branch or a renamed field fails here rather than in a copy that agrees with itself by construction.

BOTH DIRECTIONS MATTER, same as every sibling in this family:
  - Too quiet: a job or the whole pipeline blows its budget and nobody is told.
  - Too loud: `report` mode itself asks for a force-cancel, which is exactly the behaviour change P1 must NOT make yet ("Exit P1: 7 days of report-only data ... no behaviour change").

NO `xdist_group`. Every case is a short-lived `node -e` subprocess reading one tracked file and one JSON blob on argv; nothing is bound, no port is opened and no module global moves.
"""

import json
from datetime import UTC, datetime, timedelta

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")
WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")

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
                "name": "Tests + Infra / E2E Workers (fedora-43)",
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
                "name": "Tests + Infra / E2E Workers (fedora-43)",
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
        "Tests + Infra / E2E Workers (fedora-43)",
        "the violation names the offending job",
    )
    gate.log_pass("a job at 15:01 against a 15m budget fires (%s)" % verdict["jobViolations"])


def test_a_job_that_already_completed_over_budget_still_fires(gate):
    """T1.2: "a job that finished over budget between polls" must still be caught, not only one still running when a poll happens to land."""
    verdict = evaluate(
        gate,
        jobs=[
            {
                "name": "Tests + Infra / E2E Ceph Workers",
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
        mode="report",
    )
    gate.assert_eq(
        verdict["hasViolation"], True, "the fixture must genuinely violate, or this proves nothing"
    )
    gate.assert_eq(
        verdict["forceCancelRequested"], False, "report mode must never request a force-cancel"
    )
    gate.log_pass("report mode never requests a force-cancel, even with real violations present")


def test_control_enforce_mode_requests_force_cancel_exactly_once(gate):
    """The control for the case above: the SAME fixture, only `mode` flipped, must request the cancel. Without this control, a `evaluateBudget` that always returned `forceCancelRequested: false` would pass the report-mode test for the wrong reason."""
    fixture = {
        "jobs": [{"name": "Tests + Infra / E2E Ceph", "status": "in_progress", "started_at": T0}],
        "run": {"run_started_at": T0},
        "nowMs": int(_ms(30, 0)),
        "jobBudgetMin": 15,
        "runBudgetMin": 20,
    }
    report_verdict = evaluate(gate, mode="report", **fixture)
    enforce_verdict = evaluate(gate, mode="enforce", **fixture)
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


def test_watchdog_workflow_wires_report_only_budget_env(gate):
    """Anti-vacuity against the real workflow: T1.3's env block must actually be set, and in `report` mode -- P1 is measurement only, no behaviour change."""
    if not WORKFLOW.is_file():
        gate.log_fail(
            "the workflow that drives the watchdog is missing: %s"
            % paths.relative_to_root(WORKFLOW)
        )
    text = WORKFLOW.read_text(encoding="utf-8")
    gate.assert_contains(text, "WATCHDOG_BUDGET_MODE: 'report'", "P1 stays report-only")
    gate.assert_contains(text, "WATCHDOG_JOB_BUDGET_MIN:", "the 15-minute per-job ceiling is wired")
    gate.assert_contains(
        text, "WATCHDOG_RUN_BUDGET_MIN:", "the 20-minute pipeline ceiling is wired"
    )
    gate.log_pass("watchdog-monitor.yml wires the report-only budget env block")

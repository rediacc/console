"""Port of `.ci/scripts/test/gates/test-watchdog-binary-exec-guard.sh`, retired in W7 P5.

The binary-exec override in `.ci/scripts/ci/watchdog-monitor.cjs`.

The classifier prompt allows a non-executable downloaded binary to be called transient (CDN flake). The guard exists so a genuinely corrupt cross-platform build cannot be auto-retried away: when EVERY install-validation job in the run failed that way, the AI verdict is overridden to code-change. While the matrix is still running the guard DEFERS, so the first platform to fail
cannot spend the run's one retry before the other platforms report.

THE PATTERNS UNDER TEST ARE THE ONES CI ACTUALLY SETS, not a copy. A guard that works on invented job names while the real config never matches is the exact failure this gate exists to catch, so `WATCHDOG_INSTALL_VALIDATION_PATTERNS` is read out of watchdog-monitor.yml -- the workflow the monitor step moved to from ci.yml with the ubuntu-slim generations -- and a missing value is a
REFUSAL rather than an empty list.

WHAT THE PORT REIMPLEMENTS, and it is the one place the two languages had to say the same thing differently. The twin extracts the patterns with

    sed -n "s/^ *WATCHDOG_INSTALL_VALIDATION_PATTERNS: *'\\(.*\\)'$/\\1/p"

which is: the key at any indentation, a single-quoted value, captured without the quotes. The Python regex below is that expression transcribed, anchored the same way with MULTILINE, and it refuses on no match for the same reason the twin exits 1 there. Its `test_deferred_job_is_not_marked_handled` uses
`awk '/if \\(guard\\?\\.defer\\)/,/^      \\}/'` to slice the defer block, which is
awk's RANGE form: from the first line matching the opening pattern through the first subsequent line matching the closing one. That is reimplemented literally below rather than approximated, because the case is a COUNT inside a WINDOW and a window off by one line would change the count silently.

NO `xdist_group`. Every case is a short-lived `node -e` subprocess or a file read; nothing is bound and no module global moves.
"""

import json
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")
CI_WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")

PATTERNS_KEY = "WATCHDOG_INSTALL_VALIDATION_PATTERNS:"
PATTERNS_RE = re.compile(r"^ *WATCHDOG_INSTALL_VALIDATION_PATTERNS: *'(.*)'$", re.MULTILINE)

GUARD_JS = """
const guard = require(process.argv[1]).evaluateBinaryExecGuard;
const result = guard({
  job: { name: process.argv[2] },
  logTail: process.argv[3],
  jobs: JSON.parse(process.argv[4]),
  installPatterns: process.argv[5].split(",").map(s => s.trim()).filter(Boolean),
});
if (result === null) console.log("null");
else if (result.defer) console.log(`defer|${result.reason}`);
else console.log(`${result.override}|${result.reason}`);
"""

ROSTER_JS = """
const fmt = require(process.argv[1]).formatFailureRoster;
const { lines, summary } = fmt(JSON.parse(process.argv[2]), {
  owner: "rediacc", repo: "console", runId: 42,
});
console.log(summary);
console.log(lines.join("\\n"));
"""

WINDOWS_LOG = (
    "rdc.exe : The term is not recognized\n"
    "Program rdc.exe is not a valid application for this OS platform.\n"
    "Error: Process completed with exit code 1."
)

LINUX_LOG = "+ ./rdc --version\n./rdc: cannot execute binary file: Exec format error"


def job(name: str, status: str, conclusion: str | None) -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


# Mirrors a real run: the six platform legs plus the aggregator, which downloads no binary and reports skipped once its needs fail.
ALL_FAILED = [
    job("Validate Install Methods / Linux (x64)", "completed", "failure"),
    job("Validate Install Methods / Linux (arm64)", "completed", "failure"),
    job("Validate Install Methods / Windows (x64)", "completed", "failure"),
    job("Validate Install Methods / Windows (arm64)", "completed", "failure"),
    job("Validate Install Methods / macOS (x64)", "completed", "failure"),
    job("Validate Install Methods / macOS (ARM64)", "completed", "failure"),
    job("Validate Install Methods / Install Methods Complete", "completed", "skipped"),
    job("Quality", "completed", "success"),
]

ONE_FAILED = [
    job("Validate Install Methods / Linux (x64)", "completed", "success"),
    job("Validate Install Methods / Windows (x64)", "completed", "failure"),
    job("Validate Install Methods / macOS (ARM64)", "completed", "success"),
]

STILL_RUNNING = [
    job("Validate Install Methods / Linux (x64)", "completed", "failure"),
    job("Validate Install Methods / Windows (x64)", "in_progress", None),
]

QUEUED_SIBLING = [
    job("Validate Install Methods / Linux (x64)", "completed", "failure"),
    job("Validate Install Methods / macOS (ARM64)", "completed", "failure"),
    job("Validate Install Methods / Windows (arm64)", "queued", None),
]

SKIPPED_SIBLING = [
    job("Validate Install Methods / Linux (x64)", "completed", "failure"),
    job("Validate Install Methods / Windows (x64)", "completed", "skipped"),
]


def install_patterns(gate) -> str:
    if not CI_WORKFLOW.is_file():
        gate.log_fail("watchdog-monitor.yml is missing at %s" % paths.relative_to_root(CI_WORKFLOW))
    match = PATTERNS_RE.search(CI_WORKFLOW.read_text(encoding="utf-8"))
    if not match or not match.group(1):
        gate.log_fail(
            "could not read WATCHDOG_INSTALL_VALIDATION_PATTERNS from %s. The guard is "
            "driven with the patterns CI ACTUALLY SETS, so an empty read is a refusal and "
            "never an empty list: a guard matching nothing would report the AI verdict "
            "unchanged for every case below." % paths.relative_to_root(CI_WORKFLOW)
        )
    return match.group(1)


def node_eval(gate, script: str, *args: str) -> str:
    harness.require_tool("node", "install Node 22 (see .devcontainer/Dockerfile)")
    if not WATCHDOG.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(WATCHDOG))
    result = harness.run(["node", "-e", script, str(WATCHDOG), *args])
    if result.rc != 0:
        gate.log_fail(
            "node refused to evaluate the watchdog export (rc=%d).\n--- stdout ---\n%s\n"
            "--- stderr ---\n%s" % (result.rc, result.out, result.err)
        )
    return result.out


def run_guard(gate, job_name: str, log_tail: str, jobs: list[dict]) -> str:
    return node_eval(
        gate, GUARD_JS, job_name, log_tail, json.dumps(jobs), install_patterns(gate)
    ).strip()


def run_roster(gate, failed: list[dict]) -> str:
    return node_eval(gate, ROSTER_JS, json.dumps(failed))


def test_module_still_callable_from_github_script(gate):
    gate.log_test("the github-script entrypoint must still be the module's export")
    shape = node_eval(gate, "console.log(typeof require(process.argv[1]))").strip()
    gate.assert_eq(shape, "function", "watchdog must still export the github-script entrypoint")
    gate.log_pass("module.exports is still the callable monitor function")


def test_deferred_job_is_not_marked_handled(gate):
    gate.log_test("a deferred job must stay in newFailures for the next poll")
    # The guard can only work if a deferred job is left UNHANDLED: marking it handled drops it from newFailures forever, so the matrix never gets re-evaluated and the corrupt build slips through on a retry. That lives in the monitor's closure, out of reach of the guard unit tests, so it is pinned at the source level.
    #
    # The window is awk's RANGE form, reimplemented literally: from the first line matching the opening pattern through the first later line matching the closing one. An approximation here would change a COUNT silently.
    lines = WATCHDOG.read_text(encoding="utf-8").splitlines()
    open_re = re.compile(r"if \(guard\?\.defer\)")
    close_re = re.compile(r"^      \}")
    window: list[str] = []
    inside = False
    for line in lines:
        if not inside and open_re.search(line):
            inside = True
            window.append(line)
            continue
        if inside:
            window.append(line)
            if close_re.search(line):
                break
    if not window:
        gate.log_fail(
            "could not find the `if (guard?.defer)` block in %s, so the count below "
            "would be over an empty window and would pass for the wrong reason"
            % paths.relative_to_root(WATCHDOG)
        )
    in_defer_block = sum(1 for line in window if "handledJobs.add" in line)
    gate.assert_eq(in_defer_block, 0, "a deferred job must not be added to handledJobs")

    adds = sum(1 for line in lines if "handledJobs.add" in line)
    gate.assert_eq(
        adds,
        1,
        "handledJobs.add must have exactly one call site (on the job actually handled)",
    )
    gate.log_pass("deferred jobs stay in newFailures for the next poll")


def test_all_platforms_failed_overrides_to_code_change(gate):
    gate.log_test("a fully failed install matrix is a corrupt build, not a CDN flake")
    out = run_guard(gate, "Validate Install Methods / Windows (x64)", WINDOWS_LOG, ALL_FAILED)
    gate.assert_contains(out, "true|", "a fully failed install matrix must override to code-change")
    gate.assert_contains(
        out, "corrupt cross-platform build", "override reason names the corrupt build"
    )
    gate.log_pass("every install-validation job failing the same way overrides to code-change")


def test_one_platform_failed_stays_transient(gate):
    gate.log_test("CONTROL: one platform failing while others pass is still a flake")
    out = run_guard(gate, "Validate Install Methods / Windows (x64)", WINDOWS_LOG, ONE_FAILED)
    gate.assert_contains(
        out, "false|", "a single-platform failure must not override the transient verdict"
    )
    gate.assert_contains(
        out, "install-validation job(s) passed", "reason explains that other platforms passed"
    )
    gate.log_pass("one platform failing while others pass stays transient")


def test_unfinished_matrix_defers(gate):
    gate.log_test("an unfinished matrix must DEFER, not spend the run's one retry")
    out = run_guard(gate, "Validate Install Methods / Linux (x64)", LINUX_LOG, STILL_RUNNING)
    gate.assert_contains(out, "defer|", "an unfinished matrix must defer, not settle the verdict")
    gate.assert_contains(out, "have not finished", "reason explains the missing evidence")
    gate.log_pass("running install sibling defers the decision")


def test_queued_sibling_defers(gate):
    gate.log_test("queued is as unfinished as in_progress")
    out = run_guard(gate, "Validate Install Methods / Linux (x64)", LINUX_LOG, QUEUED_SIBLING)
    gate.assert_contains(
        out, "defer|", "a queued install sibling must defer, not settle the verdict"
    )
    gate.log_pass("queued install sibling defers the decision")


def test_skipped_sibling_stays_transient(gate):
    gate.log_test("CONTROL: a finished-but-not-failed sibling is not evidence")
    out = run_guard(gate, "Validate Install Methods / Linux (x64)", LINUX_LOG, SKIPPED_SIBLING)
    gate.assert_contains(
        out, "false|", "a finished-but-not-failed sibling is not evidence of a corrupt build"
    )
    gate.assert_contains(out, "did not fail", "reason names the non-failing sibling")
    gate.log_pass("completed sibling that did not fail stays transient")


def test_non_install_job_is_ignored(gate):
    gate.log_test("CONTROL: the guard must not apply outside install-validation jobs")
    out = run_guard(gate, "Tests / Unit", LINUX_LOG, ALL_FAILED)
    gate.assert_eq(out, "null", "the guard must not apply outside install-validation jobs")
    gate.log_pass("non install-validation job is left to the AI verdict")


def test_other_failure_signature_is_ignored(gate):
    gate.log_test("CONTROL: a download failure without the exec signature is not this")
    out = run_guard(
        gate,
        "Validate Install Methods / Linux (x64)",
        "curl: (56) Recv failure: Connection reset by peer",
        ALL_FAILED,
    )
    gate.assert_eq(out, "null", "a download failure without the exec signature must not override")
    gate.log_pass("install job failing without the binary-exec signature is left to the AI verdict")


def test_workflow_sets_the_required_env_var(gate):
    gate.log_test("the wiring: the watchdog THROWS without this variable")
    if not CI_WORKFLOW.is_file():
        gate.log_fail("watchdog-monitor.yml is missing at %s" % paths.relative_to_root(CI_WORKFLOW))
    if PATTERNS_KEY not in CI_WORKFLOW.read_text(encoding="utf-8"):
        gate.log_fail(
            "watchdog-monitor.yml must set WATCHDOG_INSTALL_VALIDATION_PATTERNS "
            "(the watchdog throws without it)"
        )
    gate.log_pass("watchdog-monitor.yml wires WATCHDOG_INSTALL_VALIDATION_PATTERNS")


def test_roster_lists_every_failed_job(gate):
    gate.log_test("the whole point of the roster: a poll must name ALL failures")
    out = run_roster(
        gate,
        [
            {"name": "Quality / Code", "id": 111},
            {"name": "Quality / Content", "id": 222},
            {"name": "Tests / Unit", "id": 333},
        ],
    )
    gate.assert_contains(out, "3 jobs failed:", "summary must count all failures")
    gate.assert_contains(out, '"Quality / Code"', "summary/banner names the first failure")
    gate.assert_contains(out, '"Quality / Content"', "the second failure must not be dropped")
    gate.assert_contains(out, '"Tests / Unit"', "the third failure must not be dropped")
    gate.assert_contains(out, "runs/42/job/222", "each failed job carries its direct job URL")
    gate.log_pass("roster enumerates every failed job in the poll")


def test_roster_single_failure_reads_naturally(gate):
    gate.log_test("a single failure keeps the original, unpluralized phrasing")
    out = run_roster(gate, [{"name": "Quality / Code", "id": 111}])
    gate.assert_contains(
        out, 'Job failed: "Quality / Code"', "single failure keeps the singular message"
    )
    gate.log_pass("single-failure roster reads naturally")

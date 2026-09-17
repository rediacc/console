"""Port of `.ci/scripts/test/gates/test-watchdog-supersession.sh`.

The supersession verdict in `.ci/scripts/ci/watchdog-monitor.cjs`.

WHAT BROKE. Measured on real traffic 2026-07-30, watchdog run 30534675663 monitoring console run 30530991847 on branch 0730-2:

  [0m] Run: in_progress | Jobs: 10 done, 7 running, 0 queued, 0 failed, 2 cancelled
  [logs] captured the full log for "Quality / Content" (61415 bytes) before any retry
  Retrying: classifier returned transient at confidence 0.8 -- treating as transient
  ##[error]Job cancelled (likely manual / supersession): "Quality / Content"
  [1m] Run: in_progress | Jobs: 19 done, 1 running, 0 queued, 0 failed, 11 cancelled
  Workflow externally cancelled (11/19 jobs cancelled) - exiting

A push created run 30534726467 fifteen seconds before that first poll, which cancelled 30530991847 by concurrency group. The watchdog treated the superseded jobs as failures: it spent a billed Workers AI classification and called core.setFailed, so step 4 concluded FAILURE for a run nobody broke.

WHY THE EXISTING GUARD COULD NOT SAVE IT. The mass-cancellation check only fires
once `cancelled >= completed / 2`. During a supersession the jobs flip a few at a
time, so on the first poll the ratio is nowhere near met (2 of 10 here), and by the time it is met setFailed has already stuck to the step. A ratio cannot express "something newer replaced me".

BOTH DIRECTIONS MATTER, and this gate is deliberately lopsided about which is worse:
  - Too loud (the old behaviour): every superseded run reports red, and the
    classifier is billed for it.
  - Too quiet (the danger the fix introduces): a genuine failure gets waved
    through as "just a supersession" and nobody ever sees it. That is strictly
    worse, which is why the verdict requires ALL THREE conditions and why the
    unreadable-lookup case below must resolve to NOT superseded.

READ-ONLY against the subject: node `require`s it and two cases read its text.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-watchdog-supersession.sh"

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")

VERDICT_JS = """
const w = require(process.argv[1]);
const newer = process.argv[4] === "missing" ? undefined : process.argv[4] === "true";
const v = w.evaluateSupersession({
  failedCount: Number(process.argv[2]),
  normalCancelledCount: Number(process.argv[3]),
  newerRunExists: newer,
});
process.stdout.write(v.superseded ? "superseded" : "normal");
"""

TRUTHY_JS = """
const w = require(process.argv[1]);
const v = w.evaluateSupersession({ failedCount: 0, normalCancelledCount: 2, newerRunExists: "yes" });
process.stdout.write(v.superseded ? "superseded" : "normal");
"""


def subject(gate):
    # The four lines this used to hold were byte-identical in three watchdog gate tests;
    # they live in `harness` now. See harness.watchdog_subject for why this one is extractable where an assertion message is not.
    return harness.watchdog_subject(gate, WATCHDOG)


def node(gate, script: str, *args: str) -> harness.RunResult:
    return harness.run(["node", "-e", script, str(subject(gate)), *args], timeout=120)


def verdict(gate, failed: int, cancelled: int, newer: str) -> str:
    """ "superseded" or "normal". `newer` is "true", "false" or "missing"."""
    result = node(gate, VERDICT_JS, str(failed), str(cancelled), newer)
    if result.rc != 0:
        gate.log_fail(
            "evaluateSupersession could not be driven (rc=%d): %s" % (result.rc, result.err.strip())
        )
    return result.out


def first_line_with(gate, needle: str) -> int:
    """1-based line number of the LAST line containing `needle`, or 0.

    The twin takes `| tail -1` for both anchors, so the comparison is between the last call site of each. Same choice here.
    """
    found = 0
    for index, line in enumerate(subject(gate).read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            found = index
    return found


def test_the_predicate_is_real(gate):
    """Anti-vacuity: if evaluateSupersession were not exported, every verdict below would throw rather than silently pass, but a typo in the export name would make the whole module meaningless in a quieter way. Read it."""
    result = node(
        gate, "process.stdout.write(typeof require(process.argv[1]).evaluateSupersession)"
    )
    gate.assert_eq(result.out, "function", "watchdog-monitor.cjs must export evaluateSupersession")
    gate.log_pass("reading the real evaluateSupersession from the module")


def test_the_measured_incident_is_now_quiet(gate):
    """THE CONTROL, SILENT DIRECTION. The exact numbers from the [0m] poll of watchdog run 30534675663: zero failed, two cancelled, and run 30534726467 already existing. Before the fix this reached the classifier and setFailed."""
    gate.assert_eq(
        verdict(gate, 0, 2, "true"),
        "superseded",
        "0 failed + 2 cancelled + a newer run is the measured supersession signature",
    )
    gate.log_pass("the 2026-07-30 incident (run 30530991847) is now recognised as supersession")


def test_a_real_failure_still_fires_even_with_a_newer_run(gate):
    """THE CONTROL, FIRE DIRECTION, and the single most important case in this module. Pushing a fix while the old run is still red is the NORMAL way this situation arises, so "a newer run exists" must never on its own excuse a failure. If this ever returns "superseded", the watchdog has gone blind."""
    gate.assert_eq(
        verdict(gate, 1, 2, "true"),
        "normal",
        "one genuinely failed job must still report, even though a newer run exists",
    )
    gate.log_pass("a real failure is never laundered as supersession")


def test_cancellations_without_a_newer_run_still_fire(gate):
    """A manual cancel, or a job hitting its own timeout, produces cancellations
    with NO newer run. That is not supersession."""
    gate.assert_eq(
        verdict(gate, 0, 2, "false"),
        "normal",
        "cancellations with no newer run are not supersession",
    )
    gate.log_pass("cancellation without a newer run still reports normally")


def test_a_healthy_run_is_not_superseded(gate):
    """No failures and no cancellations is simply a healthy run. It must not match, or the watchdog would exit early on every poll of every green run."""
    gate.assert_eq(
        verdict(gate, 0, 0, "true"),
        "normal",
        "a run with nothing cancelled is not superseded, however new the neighbour",
    )
    gate.log_pass("a healthy run is never treated as superseded")


def test_unreadable_lookup_fails_closed(gate):
    """hasNewerRun returns false on any API error. Prove the predicate treats a MISSING answer as NOT superseded, so an outage costs a spurious red rather than a swallowed failure."""
    gate.assert_eq(
        verdict(gate, 0, 2, "missing"),
        "normal",
        "an unknown newer-run answer must fail closed to NOT superseded",
    )
    gate.log_pass("an unreadable newer-run lookup fails closed")


def test_truthiness_is_not_accepted_for_newer_run(gate):
    """`newerRunExists === true` is a strict comparison on purpose: hasNewerRun
    returns a real boolean, and a truthy-but-not-true value (a string, an object
    from a refactored return shape) must not be read as a yes."""
    result = node(gate, TRUTHY_JS)
    gate.assert_eq(result.out, "normal", "a truthy non-boolean must not satisfy newerRunExists")
    gate.log_pass("newerRunExists is compared strictly, not for truthiness")


def test_verdict_is_checked_before_classification(gate):
    """ORDERING IS THE WHOLE FIX. Reaching classifyFailure is what spends the billed AI request and what leads to core.setFailed; a supersession check placed after it would be decorative."""
    check_line = first_line_with(gate, "evaluateSupersession({")
    classify_line = first_line_with(gate, "classifyFailure(")
    if not check_line or not classify_line:
        gate.log_fail(
            "could not locate both the supersession check and classifyFailure in %s"
            % paths.relative_to_root(WATCHDOG)
        )
    if check_line >= classify_line:
        gate.log_fail(
            "supersession is checked at line %d, at or after classifyFailure at line %d"
            % (check_line, classify_line)
        )
    gate.log_pass(
        "supersession is checked at line %d, before classifyFailure at line %d"
        % (check_line, classify_line)
    )


def test_the_api_lookup_fails_closed_in_source(gate):
    """The predicate cannot protect itself from hasNewerRun throwing. Assert the catch arm exists and returns false, because a `throw` escaping there would crash the poll loop and a `return true` would swallow failures wholesale."""
    body = harness.block_from(
        subject(gate).read_text(encoding="utf-8"), "async function hasNewerRun"
    )
    text = "\n".join(body)
    if not text:
        gate.log_fail("hasNewerRun could not be located, so its failure mode is unchecked")
    gate.assert_contains(text, "catch", "hasNewerRun must catch lookup errors")
    gate.assert_contains(text, "return false", "hasNewerRun must resolve an error to false")
    gate.log_pass("hasNewerRun fails closed on an unreadable lookup")

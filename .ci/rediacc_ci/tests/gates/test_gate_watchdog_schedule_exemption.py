"""Port of `.ci/scripts/test/gates/test-watchdog-schedule-exemption.sh`.

The cancel-exemption in `.ci/scripts/ci/watchdog-monitor.cjs`.

WHAT BROKE. Cancelling a run REWRITES ITS CONCLUSION. A run whose job genuinely failed reports `conclusion: failure`; the same run, force-cancelled by the watchdog, reports `conclusion: cancelled` -- and every reader treats `cancelled` as "superseded by a newer push, ignore me". On a PR that is survivable, because a human is watching and the next push supersedes the run anyway. On
the NIGHTLY it
is fatal: `full_suite` is `github.event_name != 'push'`, so push-to-main runs no
tests at all and the nightly is the ONLY thing validating main. Every one of the twelve measured nights had a real, fixable gate failure. None were noticed, because the rollup said `cancelled`, and that laundering is why they survived twelve days.

WHY A LABEL COULD NOT SAVE IT. Labels are read from the PR, and a `schedule` run has no PR: `prNumber` is null and the whole label block is skipped. The nightly is structurally incapable of wearing a PR-side escape hatch, so the exemption has to live in code.

WHY A UNIT TEST AND NOT A MIRROR. Re-implementing the boolean here would prove nothing about the watchdog. This calls the EXPORTED decision, reads the exempt list out of the REAL module, and checks the real ci.yml still has the schedule trigger the exemption exists for.

Both directions matter. Too quiet: the nightly keeps laundering failures into `cancelled`. Too loud: a PR run stops being cancellable, so one red would burn the full E2E fleet instead of being killed at the first failure.

WHAT THE PORT REIMPLEMENTS. The twin locates the two ordering anchors with `grep -n ... | head -1 | cut -d: -f1` and counts chokepoints with `grep -c`; this enumerates the same anchors with Python line numbering. They agree because both are plain SUBSTRING searches over the same file with no anchors or alternation involved -- and Python is deliberate here, since the house note
about ugrep's silent false zeros bites the alternated-anchor shape a hand-translation reaches
for, and a false zero in `test_single_chokepoint` would read as "the call site is
gone" rather than as "nobody looked".

NO `xdist_group`. Every case is a short-lived `node -e` subprocess or a file read; nothing is bound and no module global moves.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-watchdog-schedule-exemption.sh"

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")
CI_WORKFLOW = paths.from_root(".github", "workflows", "ci.yml")

# The two anchors the ordering guard reads. ANCHORED ON THE CALL SITE, not the definition, and that is the trap the twin records: the first draft grepped
# `evaluateCancelExemption({ runEvent`, which ALSO matches
# `function evaluateCancelExemption({ runEvent })`, so it measured the
# definition's position and would have passed with the call site AFTER the cancel. It proved nothing at all, and was caught by reading the line number it reported (97, the definition) instead of trusting the green.
CHECK_ANCHOR = "const exemption = evaluateCancelExemption("
CANCEL_ANCHOR = "actions/runs/{run_id}/force-cancel"
FALLBACK_ANCHOR = "cancelWorkflowRun"


def node_eval(gate, script: str, *args: str) -> str:
    """Run `node -e` against the REAL module and return its stdout."""
    harness.require_tool("node", "install Node 22 (see .devcontainer/Dockerfile)")
    if not WATCHDOG.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(WATCHDOG))
    result = harness.run(["node", "-e", script, str(WATCHDOG), *args])
    if result.rc != 0:
        gate.log_fail(
            "node refused to evaluate the watchdog's exported decision (rc=%d).\n"
            "--- stdout ---\n%s\n--- stderr ---\n%s" % (result.rc, result.out, result.err)
        )
    return result.out


EXEMPT_JS = """
const w = require(process.argv[1]);
const v = w.evaluateCancelExemption({ runEvent: process.argv[2] });
process.stdout.write(v.exempt ? "exempt" : "cancel");
"""

# `null` and `undefined` are DIFFERENT states to a JavaScript reader and the twin drives both, so the port does too rather than folding them into one case.
EXEMPT_MISSING_JS = """
const w = require(process.argv[1]);
const v = w.evaluateCancelExemption({
  runEvent: process.argv[2] === "null" ? null : undefined,
});
process.stdout.write(v.exempt ? "exempt" : "cancel");
"""


def exempt(gate, run_event: str) -> str:
    return node_eval(gate, EXEMPT_JS, run_event)


def exempt_missing(gate, which: str) -> str:
    return node_eval(gate, EXEMPT_MISSING_JS, which)


def line_of(needle: str) -> int:
    """1-based line number of the FIRST line containing `needle`, or 0."""
    for index, line in enumerate(WATCHDOG.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return index
    return 0


def count_of(needle: str) -> int:
    """Lines containing `needle`, matching `grep -c` semantics (lines, not hits)."""
    return sum(1 for line in WATCHDOG.read_text(encoding="utf-8").splitlines() if needle in line)


def test_exempt_list_is_real(gate):
    gate.log_test("ANTI-VACUITY #1: read the exempt list out of the module itself")
    # If `schedule` were dropped from it, every case below would pass for the wrong reason.
    listing = node_eval(
        gate,
        "process.stdout.write(require(process.argv[1]).CANCEL_EXEMPT_EVENTS.join(','))",
    )
    gate.assert_contains(
        listing, "schedule", "watchdog-monitor.cjs still exempts the schedule event"
    )
    gate.log_pass("reading the real CANCEL_EXEMPT_EVENTS from the module (%s)" % listing)


def test_ci_still_has_a_schedule_trigger(gate):
    gate.log_test("ANTI-VACUITY #2: the exemption is dead code if ci.yml has no nightly")
    # This catches "the nightly was quietly removed" as loudly as it catches "the exemption was quietly removed".
    if not CI_WORKFLOW.is_file():
        gate.log_fail("ci.yml is missing at %s" % paths.relative_to_root(CI_WORKFLOW))
    gate.assert_contains(
        CI_WORKFLOW.read_text(encoding="utf-8"),
        "schedule:",
        "ci.yml still has a schedule trigger for the exemption to protect",
    )
    gate.log_pass("ci.yml still defines the nightly the exemption exists for")


def test_schedule_is_exempt(gate):
    gate.log_test("THE FIX: this returned 'cancel' on all twelve measured nights")
    gate.assert_eq(
        exempt(gate, "schedule"),
        "exempt",
        "a scheduled run must never be cancelled, so its failure reports as failure",
    )
    gate.log_pass("schedule runs are exempt from force-cancel")


def test_pull_request_still_cancels(gate):
    gate.log_test("CONTROL: the PR path must be byte-identical")
    # Force-cancelling a red PR run is what stops a lint error from burning the 44-minute E2E fleet.
    gate.assert_eq(
        exempt(gate, "pull_request"),
        "cancel",
        "pull_request runs must still be cancellable (unchanged behaviour)",
    )
    gate.log_pass("pull_request runs still force-cancel")


def test_push_still_cancels(gate):
    gate.log_test("CONTROL: push-to-main must still be cancellable")
    gate.assert_eq(
        exempt(gate, "push"),
        "cancel",
        "push-to-main runs must still be cancellable (unchanged behaviour)",
    )
    gate.log_pass("push runs still force-cancel")


def test_workflow_dispatch_is_exempt(gate):
    gate.log_test("the dispatch rehearsal stands in for the nightly, so it reports like one")
    # THIS REVERSES AN EARLIER DECISION IN THE TWIN, and the reasoning is recorded rather than silently swapped. The first version asserted the opposite on two grounds: that a dispatch is something a human just asked
    # for and is watching, and that cancelling saves the fleet from burning on a
    # failure the first red already proved. The second is wrong on its own measured terms -- machine-minutes are flat at roughly 500 per run and FREE on a public repo. INFORMATION PER ROUND is the scarce resource: the nightly stayed broken for twelve nights partly because each round surfaced one gate at a time, and a force-cancel stops at the FIRST failure. The first is wrong
    # because ci.yml calls the dispatch path "schedule-equivalent BY CONSTRUCTION", and a tool built to prove the nightly's conclusion is honest must not launder its own.
    gate.assert_eq(
        exempt(gate, "workflow_dispatch"),
        "exempt",
        "the dispatch rehearsal must report failure as failure, like the nightly it stands in for",
    )
    gate.log_pass("workflow_dispatch (the nightly rehearsal) is exempt from force-cancel")


def test_unknown_event_fails_closed(gate):
    gate.log_test("an event nobody anticipated must behave like today, not like the nightly")
    gate.assert_eq(exempt(gate, "merge_group"), "cancel", "an unanticipated event must fail closed")
    gate.assert_eq(exempt(gate, ""), "cancel", "an empty event must fail closed")
    gate.assert_eq(exempt_missing(gate, "null"), "cancel", "a null event must fail closed")
    gate.assert_eq(exempt_missing(gate, "undefined"), "cancel", "a missing event must fail closed")
    gate.log_pass("unknown, empty, null and missing events all fail closed to cancel")


def test_matching_is_exact_not_fuzzy(gate):
    gate.log_test("guards against somebody 'improving' this into a fuzzy match")
    # A substring or case-insensitive match would silently exempt events nobody vetted.
    gate.assert_eq(exempt(gate, "Schedule"), "cancel", "matching is case-sensitive")
    gate.assert_eq(exempt(gate, "schedules"), "cancel", "matching is exact, not a prefix")
    gate.assert_eq(exempt(gate, "pre-schedule"), "cancel", "matching is exact, not a substring")
    gate.log_pass("the exempt match is exact, not fuzzy")


def test_exemption_is_checked_before_the_cancel_api_call(gate):
    gate.log_test("THE ORDERING GUARD, and why this is not just a boolean check")
    # The exemption is only worth anything if forceCancel consults it BEFORE it calls the cancel API. A sibling gate test exists because of a pure ordering bug of exactly this shape: a branch returned before the check that was supposed to govern it, and the log cheerfully asserted the opposite of the behaviour.
    check_line = line_of(CHECK_ANCHOR)
    cancel_line = line_of(CANCEL_ANCHOR)
    if not check_line or not cancel_line:
        gate.log_fail(
            "could not locate both the exemption check and the force-cancel API call in %s "
            "(check=%d cancel=%d)" % (paths.relative_to_root(WATCHDOG), check_line, cancel_line)
        )
    if check_line >= cancel_line:
        gate.log_fail(
            "the exemption check (line %d) must precede the force-cancel API call (line %d)"
            % (check_line, cancel_line)
        )
    gate.log_pass(
        "the exemption is consulted at line %d, before the cancel API call at line %d"
        % (check_line, cancel_line)
    )


def test_single_chokepoint(gate):
    gate.log_test("cancellation must have ONE chokepoint the exemption governs")
    # The exemption lives inside forceCancel precisely so every call site inherits it, including the no-drain Review Gate path. A direct cancel API call elsewhere in the file would bypass it entirely.
    gate.assert_eq(
        count_of(CANCEL_ANCHOR),
        1,
        "exactly one force-cancel API call, so the exemption cannot be bypassed",
    )
    gate.assert_eq(
        count_of(FALLBACK_ANCHOR),
        1,
        "exactly one fallback cancel API call, inside the same guarded function",
    )
    gate.log_pass("cancellation has a single chokepoint that the exemption governs")

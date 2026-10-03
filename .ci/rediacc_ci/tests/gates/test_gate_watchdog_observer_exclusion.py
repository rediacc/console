"""Port of `.ci/scripts/test/gates/test-watchdog-observer-exclusion.sh`, retired in W7 P5.

The watchdog must never read an OBSERVER check as a failed CI job.

WHY: on 2026-07-31 (run 30660765759) a push deadlocked on an observer check (the since-retired review status check). Its check-run FAILED, correctly; it landed in the same github-actions check suite as the CI jobs; the watchdog's failure scan counted it and force-cancelled the run whose green the observer was waiting for. `CI Verdict` (ci-verdict.yml) is an
observer of the same kind. The fix is one config line (`WATCHDOG_EXCLUDE_PATTERNS` in watchdog-monitor.yml), and this gate is what stops that line from quietly losing an entry and reintroducing the cycle.

CONTROL-FIRST, per the house rule: the checker is proven to FIRE on a planted copy missing one exclusion BEFORE it is run against the real workflow.

THE TWIN IS A FLAT SCRIPT with no `test_*()` functions, so the port chooses the split. Its five `PASS:` lines become five tests: the control, the control's own anti-vacuity clause, and one per required exclusion name -- which is strictly better than the twin's loop, because a missing name now reds as its own test rather than aborting the loop at the first one.
"""

import pathlib
import re

from rediacc_ci import paths

WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")

# The names an observer check can carry. Each is a check that lands in the same check suite as the CI jobs and is NOT one of them.
# `Review Complete`, `Review Status` and `Claude Review` are the PR review's checks (PLAN-github-pr-review-restore), posted by their own workflows after Console CI: observers of the run, never part of it. Review Complete is a required check on main again (operator ruling 2026-10-03), which ci-trace and the Stop hook enforce; the watchdog must still never cancel Console CI over it.
REQUIRED = (
    "Watchdog",
    "CI Complete",
    "CI Verdict",
    "Review Complete",
    "Review Status",
    "Claude Review",
)

EXCLUSIONS_RE = re.compile(r"WATCHDOG_EXCLUDE_PATTERNS: '(.*)'")


def exclusions_of(text: str) -> str:
    """The value of `WATCHDOG_EXCLUDE_PATTERNS`, or empty. The twin's sed."""
    match = EXCLUSIONS_RE.search(text)
    return match.group(1) if match else ""


def excludes(text: str, name: str) -> bool:
    """True when `name` is a comma-separated MEMBER, not merely a substring.

    The comma padding is the whole trick and it survives the port verbatim: a bare `in` test would report "Complete" as present because "CI Complete" is, and the gate would then pass a list that had lost the entry it names.
    """
    return ",%s," % name in ",%s," % exclusions_of(text)


def workflow_text(gate) -> str:
    if not WORKFLOW.is_file():
        gate.log_fail("subject under test is missing: %s" % WORKFLOW)
    return WORKFLOW.read_text(encoding="utf-8")


def planted(gate) -> str:
    """The real workflow with 'CI Verdict' cut out of the exclusion list."""
    return workflow_text(gate).replace(",CI Verdict'", "'")


def test_control_the_checker_fires_on_a_planted_copy(gate):
    if excludes(planted(gate), "CI Verdict"):
        gate.log_fail("CONTROL failed: the checker passed a copy missing the exclusion")
    gate.log_pass("CONTROL: the checker fires on a planted copy missing 'CI Verdict'")


def test_control_is_not_vacuous(gate):
    """The plant must remove ONE entry, not the whole env line.

    A plant that deleted the line would make the control above fire for a reason that has nothing to do with membership, and the gate would look proven while testing that an absent list has no members.
    """
    value = exclusions_of(planted(gate))
    if not value:
        gate.log_fail("CONTROL is vacuous: the planted copy lost the whole env line")
    gate.log_pass(
        "the planted copy still carries a list (%d other entry-ish token(s))"
        % len(value.split(","))
    )


def test_watchdog_is_excluded(gate):
    require_member(gate, "Watchdog")


def test_ci_complete_is_excluded(gate):
    require_member(gate, "CI Complete")


def test_ci_verdict_is_excluded(gate):
    require_member(gate, "CI Verdict")


def test_review_complete_is_excluded(gate):
    require_member(gate, "Review Complete")


def test_review_status_is_excluded(gate):
    require_member(gate, "Review Status")


def test_claude_review_is_excluded(gate):
    require_member(gate, "Claude Review")


def test_control_review_gate_is_not_excluded(gate):
    """The watchdog matches its patterns as SUBSTRINGS, so no pattern may hide inside `Review Gate`, a real Console CI job whose failure the watchdog must still see."""
    hits = [p for p in exclusions_of(workflow_text(gate)).split(",") if p and p in "Review Gate"]
    if hits:
        gate.log_fail("WATCHDOG_EXCLUDE_PATTERNS swallows 'Review Gate' via %r" % hits)
    gate.log_pass("no watchdog exclusion pattern matches 'Review Gate'")


def require_member(gate, name: str) -> None:
    if not excludes(workflow_text(gate), name):
        gate.log_fail(
            "WATCHDOG_EXCLUDE_PATTERNS lost '%s'; the observer-check deadlock "
            "(run 30660765759) returns without it" % name
        )
    gate.log_pass("watchdog exclusion list carries '%s'" % name)


def test_every_required_name_has_its_own_case(gate):
    """ANTI-VACUITY on the port's own split.

    The twin loops over the three names, so adding a fourth to the loop covers it automatically. The port has one test per name instead -- better diagnostics, and a new hazard: a name added to `REQUIRED` with no test beside it would be silently uncovered while the module still reported green. This reads THIS FILE'S OWN SOURCE and requires a `require_member` call site per name.
    """
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    driven = {name for name in REQUIRED if 'require_member(gate, "%s")' % name in source}
    missing = sorted(set(REQUIRED) - driven)
    if missing:
        gate.log_fail(
            "%d required exclusion(s) have no case of their own: %s. Add a "
            "test_..._is_excluded calling require_member for each; a name in REQUIRED "
            "that nothing drives is a name nothing checks." % (len(missing), ", ".join(missing))
        )
    gate.log_pass("all %d required exclusion name(s) have a dedicated case" % len(REQUIRED))

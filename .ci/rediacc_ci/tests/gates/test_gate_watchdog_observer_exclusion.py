"""Port of `.ci/scripts/test/gates/test-watchdog-observer-exclusion.sh`.

The watchdog must never read an OBSERVER check as a failed CI job.

WHY: minutes after "Review Complete" became a ruleset-required check (2026-07-31, run 30660765759), a push deadlocked. The not-yet-re-reviewed head's Review Complete check-run FAILED, correctly; it lands in the same github-actions check suite as the CI jobs; the watchdog's failure scan counted it and force-cancelled the run; and the re-review that would flip the check green only
starts on a GREEN run. The fix is one config line (`WATCHDOG_EXCLUDE_PATTERNS` in watchdog-monitor.yml), and this gate is what stops that line from quietly losing an entry and reintroducing the cycle.

CONTROL-FIRST, per the house rule: the checker is proven to FIRE on a planted copy missing one exclusion BEFORE it is run against the real workflow.

THE TWIN IS A FLAT SCRIPT with no `test_*()` functions, so the port chooses the split. Its five `PASS:` lines become five tests: the control, the control's own anti-vacuity clause, and one per required exclusion name -- which is strictly better than the twin's loop, because a missing name now reds as its own test rather than aborting the loop at the first one.
"""

import pathlib
import re

from rediacc_ci import paths

BASH_TWIN = ".ci/scripts/test/gates/test-watchdog-observer-exclusion.sh"

WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")

# The names an observer check can carry. Each is a check that lands in the same check suite as the CI jobs and is NOT one of them.
REQUIRED = ("Watchdog", "CI Complete", "Review Complete")

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
    """The real workflow with 'Review Complete' cut out of the exclusion list."""
    return workflow_text(gate).replace(",Review Complete'", "'")


def test_control_the_checker_fires_on_a_planted_copy(gate):
    if excludes(planted(gate), "Review Complete"):
        gate.log_fail("CONTROL failed: the checker passed a copy missing the exclusion")
    gate.log_pass("CONTROL: the checker fires on a planted copy missing 'Review Complete'")


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


def test_review_complete_is_excluded(gate):
    require_member(gate, "Review Complete")


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

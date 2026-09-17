"""Port of `.ci/scripts/test/gates/test-watchdog-designed-failure.sh`.

The watchdog's by-design failure must SAY it is by design.

THE PROBLEM, measured 2026-08-26 across three days of rediacc/console runs: 589 success, 230 skipped, 117 cancelled, 64 failure -- and 63 of those 64 failures are this one code path. The watchdog cancels the CI run it monitors, then `core.setFailed()`s to signal that it did. That is its SUCCESS mode.

Nothing said so. To a human scanning the Actions tab, to any dashboard, and to any sweeper keyed on `conclusion`, a working watchdog and a broken one are indistinguishable. It is also the direct reason the nightly retry (`.ci/scripts/housekeeping/retry-failed-runs.sh`) must exclude this workflow by path: without that exclusion, 63 of its 64 candidates are deliberate.

WHY THE RUN NAME IS NOT THE FIX, worth recording because the obvious design does not work: GitHub evaluates `run-name` at run CREATION from the dispatch inputs, before the monitored run's outcome exists. It CANNOT carry a verdict decided mid-run. The step summary is the earliest surface that can, so that is where the explanation lives.

WHAT THIS GATE CANNOT SEE: it asserts the marker and the ordering in the source. It cannot prove GitHub renders the summary, and it deliberately does NOT assert the exact prose -- only that the by-design claim and the monitored run id are present, so the wording stays editable.
"""

import re

from rediacc_ci import paths

BASH_TWIN = ".ci/scripts/test/gates/test-watchdog-designed-failure.sh"

SUT = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")
SWEEPER = paths.from_root(".ci", "scripts", "housekeeping", "retry-failed-runs.sh")

# Three by-design paths, one real-error setFailed. These are COUNTS OF A KNOWN SET rather than thresholds: the twin asserts equality both ways for the same reason, because a fourth by-design site is as much a change as a lost one.
BY_DESIGN_SITES = 3
REAL_SETFAILED_SITES = 1

SETFAILED_RE = re.compile(r"^ *core\.setFailed\(", re.MULTILINE)
SIGNAL_FN_RE = re.compile(r"^async function signalByDesign\(.*?^\}", re.MULTILINE | re.DOTALL)

REAL_ERROR_LINE = (
    "core.setFailed(`Run ${targetRunId} completed but the pending rerun could not be triggered`)"
)

# The PRE-FIX annotation, written out rather than derived. A mutation of the current line drifts with the subject; this is the shape that actually shipped.
PRE_FIX_ANNOTATION = "core.setFailed('PIPELINE CANCELLED: ' + failureMsg);"


def source(gate) -> str:
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUT)
    return SUT.read_text(encoding="utf-8")


def signal_by_design_body(gate) -> str:
    """`signalByDesign`'s body, by anchor. Empty means the anchor moved."""
    match = SIGNAL_FN_RE.search(source(gate))
    if not match:
        gate.log_fail(
            "could not find `async function signalByDesign(` in %s. The extraction is "
            "by anchor on purpose: a rename must red HERE rather than leave the two "
            "cases below asserting over an empty string, which every `in` test passes "
            "against by accident." % paths.relative_to_root(SUT)
        )
    return match.group(0)


def test_by_design_paths_do_not_fail_the_step(gate):
    gate.log_test("every BY-DESIGN path must exit 0, not setFailed")
    # Phase 3b, operator-approved 2026-08-26. Three paths were failing the step
    # while the watchdog had worked perfectly: it cancelled the run, it
    # deliberately did NOT cancel an exempt run, or it is holding a pending rerun. 63 of 64 repo-wide `failure` conclusions were these.
    found = source(gate).count("await signalByDesign(")
    gate.assert_eq(
        found,
        BY_DESIGN_SITES,
        "expected %d by-design signal sites -- a path regressed to setFailed" % BY_DESIGN_SITES,
    )
    gate.log_pass("all %d by-design paths signal without failing" % BY_DESIGN_SITES)


def test_a_real_error_still_fails(gate):
    gate.log_test("a REAL error must still setFailed -- 3b must not mute everything")
    # The whole value of 3b is that `failure` regains meaning. If the genuine error path were converted too, the workflow could never report one.
    body = source(gate)
    if REAL_ERROR_LINE not in body:
        gate.log_fail(
            "the genuine-error setFailed is gone; nothing can report a real watchdog failure"
        )
    gate.assertions += 1
    gate.assert_eq(
        len(SETFAILED_RE.findall(body)),
        REAL_SETFAILED_SITES,
        "expected exactly %d real-error setFailed" % REAL_SETFAILED_SITES,
    )
    gate.log_pass("exactly one setFailed remains, and it is the real error")


def test_summary_failure_does_not_swallow_the_verdict(gate):
    gate.log_test("a summary that cannot be written must NOT suppress the failure")
    # The write is diagnostics; the annotation is the signal. If a throw from core.summary could escape, the watchdog would exit 0 having cancelled a pipeline -- a false green on the one path that matters most.
    body = signal_by_design_body(gate)
    gate.assert_contains(
        body,
        "catch",
        "the summary write is unguarded; a throw would abort a path that had just worked",
    )
    gate.assert_contains(
        body,
        "typeof core.notice === 'function'",
        "core.notice is called unguarded; an older @actions/core would throw",
    )
    gate.log_pass("summary and annotation are both guarded")


def test_summary_names_the_monitored_run(gate):
    gate.log_test("the summary must point at the run that actually failed")
    gate.assert_contains(
        signal_by_design_body(gate),
        "targetRunId",
        "the summary does not name the monitored run, so a reader cannot follow it",
    )
    gate.log_pass("summary names the monitored run")


def test_retry_sweeper_still_excludes_this_workflow(gate):
    gate.log_test("the marker is an explanation, NOT a substitute for the path exclusion")
    # A reader might reasonably think a self-describing failure makes the sweeper's exclusion redundant. It does not: `conclusion` is still `failure`, and that is what the API returns.
    if not SWEEPER.is_file():
        gate.log_fail("the nightly retry sweeper is missing")
    gate.assertions += 1
    gate.assert_contains(
        SWEEPER.read_text(encoding="utf-8"),
        ".github/workflows/watchdog-monitor.yml",
        "the sweeper no longer excludes the watchdog by path",
    )
    gate.log_pass("path exclusion still in place alongside the marker")


def test_control_marker_removal_is_detectable(gate, tmp_path):
    gate.log_test("CONTROL: a plain annotation must be caught")
    # BY CONSTRUCTION: write the OLD annotation form, not a mutation of the new one, and require the detector to say it is unmarked.
    mutant = tmp_path / "pre-fix.cjs"
    mutant.write_text(PRE_FIX_ANNOTATION + "\n", encoding="utf-8")
    if "await signalByDesign(" in mutant.read_text(encoding="utf-8"):
        gate.log_fail("CONTROL DID NOT FIRE: the pre-fix annotation read as marked")
    gate.assertions += 1
    # And the other half, which the twin leaves implicit: the pre-fix form is exactly what `test_a_real_error_still_fails` counts, so it must be seen by that regex. A control that fires for BOTH reasons proves neither.
    gate.assert_eq(
        len(SETFAILED_RE.findall(mutant.read_text(encoding="utf-8"))),
        1,
        "the pre-fix annotation must still register as a setFailed site",
    )
    gate.log_pass("control: the pre-fix annotation is detectable")


def test_the_subject_is_reachable_from_the_workflow(gate):
    """PORT-ONLY. Everything above reads a FILE; nothing so far proves that file is the one the workflow runs. A subject nobody invokes is a subject whose assertions cost nothing to satisfy."""
    workflow = paths.from_root(".github", "workflows", "watchdog-monitor.yml")
    if not workflow.is_file():
        gate.log_fail("watchdog-monitor.yml is missing, so the subject has no caller")
    gate.assertions += 1
    gate.assert_contains(
        workflow.read_text(encoding="utf-8"),
        "watchdog-monitor.cjs",
        "watchdog-monitor.yml no longer names the script every case above reads",
    )
    gate.log_pass("the workflow still invokes %s" % paths.relative_to_root(SUT))

"""Port of `.ci/scripts/test/gates/test-watchdog-no-retry-cancel.sh`, retired in W7 P5.

The no-retry force-cancel decision in `.ci/scripts/ci/watchdog-monitor.cjs`: WHICH failures kill the run immediately, and WHAT the kill waits for.

HISTORY. The twin was `test-watchdog-cancel-label.sh` and existed for the `no-cancel-failure` label, which suppressed the force-cancel so a run could finish and report every red at once. The label was removed 2026-08-05: holding a known-red run open makes every CI iteration wait out the expensive legs (E2E, OPS) for information the drain already delivers for the deterministic
lanes. What remains under test is the part that outlived it -- the branch ordering and the drain.

WHY A UNIT TEST AND NOT A MIRROR. It would be easy to re-implement the boolean here and assert on the copy; that proves nothing about the watchdog. This calls the EXPORTED decision and reads `WATCHDOG_NO_RETRY_PATTERNS` out of the REAL `watchdog-monitor.yml`, so a renamed pattern or a reordered branch fails here.

Both directions matter:
  - Too quiet: a deterministic Quality failure stops killing the run, and one lint
    error burns the whole 44-minute fleet.
  - Too loud: a Quality CANCELLATION (a runner flake, not a code verdict) kills a
    run with zero failed jobs.

THE PATTERN READ IS REIMPLEMENTED, and the two spellings agree by construction. The twin lifts the value with

    sed -n "s/^ *WATCHDOG_NO_RETRY_PATTERNS: *'\\(.*\\)'$/\\1/p"

and this module uses the same expression as a Python regex under `re.MULTILINE`. Both are greedy on `.*` and both anchor the closing quote at end of line, so a value containing a quote resolves identically in either. The port then REFUSES an empty result exactly as the twin does, because a pattern list that read as empty would make every case below pass for the wrong reason.

NO `xdist_group`. Every case is a short-lived `node -e` subprocess that reads two tracked files and writes nothing; nothing is bound and no module global is mutated.
"""

import json
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")
# The WATCHDOG_* env block lives with the monitor step, which moved from ci.yml to the chained watchdog-monitor.yml (ubuntu-slim generations).
CI_WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")

PATTERN_LINE = re.compile(r"^ *WATCHDOG_NO_RETRY_PATTERNS: *'(.*)'$", re.MULTILINE)


def no_retry_patterns(gate) -> str:
    """The comma-joined list CI actually sets, or a loud refusal.

    A guard that works on invented job names while the real config never matches is the exact failure this gate exists to catch, so the value is READ rather than typed. An empty read is a failure and never a default: every case below would pass for the wrong reason against an empty pattern list.
    """
    if not CI_WORKFLOW.is_file():
        gate.log_fail(
            "the workflow carrying the real pattern list is missing at %s"
            % paths.relative_to_root(CI_WORKFLOW)
        )
    matches = PATTERN_LINE.findall(CI_WORKFLOW.read_text(encoding="utf-8"))
    if not matches:
        gate.log_fail(
            "could not read WATCHDOG_NO_RETRY_PATTERNS from %s -- with no pattern list "
            "every case in this module would pass for the wrong reason"
            % paths.relative_to_root(CI_WORKFLOW)
        )
    # `sed -n ...p` prints EVERY match and the twin takes the whole stream; there is one line today, and taking the last preserves the twin's behaviour if a second ever appears.
    return matches[-1]


def node_probe(gate, program: str, *argv: str) -> str:
    """One `node -e` against the REAL module, stdout only.

    stdout ALONE and not `.combined`, deliberately: the probe writes its verdict word to stdout and node writes deprecation notices and stack traces to stderr, so merging them would let a warning turn `"cancel"` into something that merely contains it.
    """
    if not WATCHDOG.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(WATCHDOG))
    node = harness.require_tool("node", "install node; the subject is a CommonJS module")
    result = harness.run([node, "-e", program, str(WATCHDOG), *argv])
    if result.rc != 0:
        gate.log_fail(
            "the node probe exited %d rather than answering (stderr: %s)"
            % (result.rc, result.err.strip())
        )
    return result.out


VERDICT_JS = """
const w = require(process.argv[1]);
const v = w.evaluateNoRetryCancel({
  jobName: process.argv[2],
  isFailure: process.argv[3] === "1",
  noRetryPatterns: process.argv[4].split(",").map(s => s.trim()),
});
process.stdout.write(v.cancel ? "cancel" : "continue");
"""

DRAIN_JS = """
const w = require(process.argv[1]);
const v = w.evaluateNoRetryCancel({
  jobName: process.argv[2],
  isFailure: true,
  noRetryPatterns: process.argv[3].split(",").map(s => s.trim()),
});
process.stdout.write(v.noDrain ? "instant" : "drain");
"""

SUPPRESSION_JS = """
const w = require(process.argv[1]);
const patterns = process.argv[2].split(",").map(s => s.trim());
const v = w.evaluateNoRetryCancel({
  jobName: "Quality / Packages",
  isFailure: true,
  skipCancellationOnFailure: true,
  noRetryPatterns: patterns,
});
process.stdout.write(v.cancel ? "cancel" : "continue");
"""

PENDING_JS = """
const w = require(process.argv[1]);
const out = w.pendingNoRetryJobs({
  jobs: JSON.parse(process.argv[2]),
  noRetryPatterns: process.argv[3].split(",").map(s => s.trim()),
  excludePatterns: (process.argv[4] || "").split(",").map(s => s.trim()).filter(Boolean),
});
process.stdout.write(out.map(j => j.name).join(","));
"""


def verdict(gate, job_name: str, is_failure: str) -> str:
    return node_probe(gate, VERDICT_JS, job_name, is_failure, no_retry_patterns(gate))


def drain_mode(gate, job_name: str) -> str:
    return node_probe(gate, DRAIN_JS, job_name, no_retry_patterns(gate))


def pending(gate, jobs: list[dict], exclude: str = "") -> str:
    return node_probe(gate, PENDING_JS, json.dumps(jobs), no_retry_patterns(gate), exclude)


def test_patterns_are_real(gate):
    """ANTI-VACUITY. If the pattern list stopped covering Quality, every case below would pass for the wrong reason."""
    patterns = no_retry_patterns(gate)
    gate.assert_contains(
        patterns, "Quality", "watchdog-monitor.yml still lists Quality as no-retry"
    )
    gate.assert_contains(
        patterns, "Review Gate", "watchdog-monitor.yml still lists Review Gate as no-retry"
    )
    gate.log_pass(
        "reading the real WATCHDOG_NO_RETRY_PATTERNS from watchdog-monitor.yml (%s)" % patterns
    )


def test_quality_failure_cancels(gate):
    gate.assert_eq(
        verdict(gate, "Quality / Packages", "1"),
        "cancel",
        "a Quality failure must force-cancel: a lint or type error is deterministic",
    )
    gate.log_pass("a Quality failure force-cancels the run")


def test_review_gate_cancels(gate):
    gate.assert_eq(
        verdict(gate, "Review Gate", "1"),
        "cancel",
        "Review Gate fails immediately and force-cancels (CLAUDE.md)",
    )
    gate.log_pass("a Review Gate failure force-cancels the run")


def test_no_suppression_hatch_remains(gate):
    """The point of the 2026-08-05 removal, asserted rather than assumed.

    The decision takes NO argument that can hold the cancel back. Passing the old suppression flag must not change the answer, so a half-reverted removal -- the branch restored, the plumbing not -- cannot pass silently.
    """
    gate.assert_eq(
        node_probe(gate, SUPPRESSION_JS, no_retry_patterns(gate)),
        "cancel",
        "no ignored/leftover flag may suppress the force-cancel",
    )
    gate.log_pass("the force-cancel has no suppression hatch left")


def test_non_no_retry_job_is_unaffected(gate):
    """A job outside the no-retry list never took this branch; it falls through to AI classification downstream."""
    gate.assert_eq(
        verdict(gate, "Build (Renet) / Renet (Full)", "1"),
        "continue",
        "a non-no-retry failure must not be force-cancelled by this branch",
    )
    gate.log_pass("jobs outside the no-retry list fall through to classification")


def test_cancellation_is_not_a_failure(gate):
    """Branch 1 is gated on `failed.includes(job)` on purpose: a non-stuck CANCELLATION of a Quality job is an infra flake, and nuking a 0-failure run for it is wrong."""
    gate.assert_eq(
        verdict(gate, "Quality / Packages", "0"),
        "continue",
        "a cancelled (not failed) Quality job must not force-cancel the run",
    )
    gate.log_pass("a cancellation is not treated as a failure")


def test_review_gate_skips_the_drain(gate):
    """CLAUDE.md: Review Gate fails immediately, full stop. There is no sibling verdict worth collecting when the red means "reply to the review"."""
    gate.assert_eq(
        drain_mode(gate, "Review Gate"), "instant", "Review Gate kills the run without draining"
    )
    gate.assert_eq(
        drain_mode(gate, "Quality / Review Gate"),
        "instant",
        "a job matching both lists must still skip the drain",
    )
    gate.assert_eq(
        drain_mode(gate, "Quality / Packages"), "drain", "a Quality lane waits for its siblings"
    )
    gate.log_pass("Review Gate skips the drain; Quality lanes wait for theirs")


def test_drain_waits_for_running_quality_lanes(gate):
    jobs = [
        {"name": "Quality / Code", "status": "completed"},
        {"name": "Quality / Content", "status": "in_progress"},
        {"name": "Quality / Go", "status": "queued"},
    ]
    gate.assert_eq(
        pending(gate, jobs),
        "Quality / Content,Quality / Go",
        "a running and a queued lane both hold the cancel",
    )
    gate.log_pass("the force-cancel is held while sibling lanes are still running")


def test_drain_releases_when_all_terminal(gate):
    jobs = [
        {"name": "Quality / Code", "status": "completed"},
        {"name": "Quality / Content", "status": "completed"},
    ]
    gate.assert_eq(pending(gate, jobs), "", "with every lane terminal, nothing holds the cancel")
    gate.log_pass("the force-cancel fires once every no-retry job is terminal")


def test_drain_ignores_expensive_jobs(gate):
    """The whole point of force-cancelling is to stop the expensive legs. Those are NOT in the no-retry list, so they must never hold the cancel open -- otherwise a lint error would wait 50 minutes for the E2E matrix."""
    jobs = [
        {"name": "Tests + Infra / E2E Workers (fedora-43)", "status": "in_progress"},
        {"name": "OPS Tests / OPS Provision (linux-amd64)", "status": "in_progress"},
    ]
    gate.assert_eq(pending(gate, jobs), "", "E2E and OPS jobs must not delay the cancel")
    gate.log_pass("expensive non-quality jobs do not hold the cancel open")


def test_drain_never_waits_on_review_gate(gate):
    jobs = [{"name": "Review Gate", "status": "in_progress"}]
    gate.assert_eq(pending(gate, jobs), "", "Review Gate is excluded from the drain set")
    gate.log_pass("Review Gate never holds the cancel open")


def test_drain_honours_exclude_patterns(gate):
    """The watchdog's own job is excluded from monitoring; it must not be able to hold its own cancel open forever."""
    jobs = [
        {"name": "Quality / Watchdog Helper", "status": "in_progress"},
        {"name": "Quality / Code", "status": "in_progress"},
    ]
    gate.assert_eq(
        pending(gate, jobs, "Watchdog Helper"),
        "Quality / Code",
        "excluded jobs are dropped from the drain set",
    )
    gate.log_pass("excluded jobs do not hold the cancel open")

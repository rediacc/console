"""Port of `.ci/scripts/test/gates/test-gate-skip-announcer.sh`.

`.ci/scripts/quality/announce-gate-skips.sh` is the step that makes a label-held gate VISIBLE.

The thing under test is an INSTRUMENT, so every case here is really a question about the instrument rather than about the gates it announces: can it fire (skip), can it stay quiet when it should (hard), does it fail closed when the wiring breaks (unset), and does it refuse rather than guess when the wiring is wrong (unknown mode)? An announcer that silently announced nothing would
restore exactly the invisible skip it exists to remove, so the QUIET-direction cases are the load-bearing ones here, not filler.

STREAMS ARE MERGED, matching the twin's `2>&1`. The announcer writes its annotation to stdout and its refusals to stderr, and every case asserts on "what a reader of the step log sees", which is the merged text. Splitting them would change the claim rather than sharpen it.

THE WORKFLOW SEAM IS PRESERVED. `test_workflow_wiring_covers_every_held_gate` reads `$GATE_SKIP_WORKFLOW` when set, exactly as the twin does, so the wiring assertion can be proven able to fire against a mutated COPY. Mutating the real workflow to test the test is how a shared tree loses somebody's uncommitted work.

WHAT THE PORT REIMPLEMENTS. The twin counts wiring with `grep -c` and extracts announced gate names with `grep -oE ... | sed`. This does both in Python `re`. The two agree because the patterns are literal substrings and one bounded character class, with no anchors involved -- and Python is used rather than grep deliberately, since the house note about ugrep's silent false zeros
bites exactly the alternated-anchor shape a hand-translated version would reach for.

NO `xdist_group`. Nothing is bound, nothing module-global is mutated: the two environment variables the cases vary are passed per-subprocess through the harness's env OVERLAY rather than set on this process.
"""

import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-gate-skip-announcer.sh"

ANNOUNCER = paths.from_root(".ci", "scripts", "quality", "announce-gate-skips.sh")
DEFAULT_WORKFLOW = paths.from_root(".github", "workflows", "ci-quality.yml")

# The wiring floors, both of them counts of a KNOWN SET rather than thresholds picked for comfort: a third announcer is as much a change as a lost one, and the twin asserts the same two numbers.
MIN_HELD_STEPS = 3
EXPECTED_ANNOUNCERS = 2

HELD_MARKER = "inputs.media_quality != 'skip'"
ANNOUNCE_MARKER = "announce-gate-skips.sh no-media-quality"
ANNOUNCE_RE = re.compile(r"announce-gate-skips\.sh no-media-quality([a-zA-Z0-9:._ -]*)")


def run_announcer(gate, mode: str | None, expected: int, label: str, *args: str) -> str:
    """Drive the announcer and refuse an unexpected exit code. Returns merged output.

    `mode=None` IS the twin's `env -u GATE_SKIP_MODE` case, which is the whole
    point of that case: a wiring break where the variable never reaches the step must read as "the gates ran", never as "the gates were held". The variable is removed from the overlay rather than set to the empty string, because those are different states to the script under test.
    """
    if not (ANNOUNCER.is_file() and os.access(ANNOUNCER, os.X_OK)):
        gate.log_fail(
            "announcer not found or not executable: %s" % paths.relative_to_root(ANNOUNCER)
        )
    env = {k: v for k, v in os.environ.items() if k != "GATE_SKIP_MODE"}
    if mode is not None:
        env["GATE_SKIP_MODE"] = mode
    result = harness.run([str(ANNOUNCER), *args], env=env, env_replace=True)
    if result.rc != expected:
        gate.log_fail(
            "%s: expected exit %d, got %d (output: %s)"
            % (label, expected, result.rc, result.combined)
        )
    return result.combined


def test_skip_announces_every_gate_by_name(gate):
    gate.log_test("skip mode must name the label and every gate it held")
    out = run_announcer(
        gate, "skip", 0, "skip announces", "no-media-quality", "gate-alpha", "gate-beta"
    )
    gate.assert_contains(out, "::warning::", "skip must emit a ::warning:: annotation")
    # Naming the gates is the whole point: "2 gates skipped" would not tell a reader which coverage they lost.
    gate.assert_contains(out, "gate-alpha", "skip must name gate-alpha")
    gate.assert_contains(out, "gate-beta", "skip must name gate-beta")
    gate.assert_contains(out, "no-media-quality", "skip must name the label responsible")
    gate.log_pass("skip mode: exits 0, warns, names the label and every held gate")


def test_hard_is_quiet_but_not_silent(gate):
    gate.log_test("CONTROL: hard mode must not warn, but must not go silent either")
    # If this warned, the announcement would be noise on every green run and would stop meaning anything.
    out = run_announcer(
        gate,
        "hard",
        0,
        "hard announces nothing held",
        "no-media-quality",
        "gate-alpha",
        "gate-beta",
    )
    gate.assert_not_contains(out, "::warning::", "hard mode must not warn")
    # But it must still say something: a completely silent announcer and a MISSING announcer look identical in a log.
    gate.assert_contains(out, "2 gate(s) enforced", "hard mode must report the enforced count")
    gate.log_pass("hard mode: exits 0, no warning, still prints the enforced count")


def test_unset_mode_fails_closed_to_hard(gate):
    gate.log_test("a wiring break must read as 'the gates ran', never 'they were held'")
    out = run_announcer(gate, None, 0, "unset is hard", "no-media-quality", "gate-alpha")
    gate.assert_not_contains(out, "::warning::", "unset must not announce a skip")
    gate.assert_contains(out, "1 gate(s) enforced", "unset must behave as hard")
    gate.log_pass("unset GATE_SKIP_MODE fails closed to hard")


def test_unknown_mode_refuses(gate):
    gate.log_test("a typo'd mode must refuse loudly rather than fall through to hard")
    # The step `if:` treats any unrecognised value as "run", which is safe but silent. This is the only place a typo'd mode is ever reported.
    out = run_announcer(
        gate, "sideways", 2, "unknown mode refuses", "no-media-quality", "gate-alpha"
    )
    gate.assert_contains(out, "unknown GATE_SKIP_MODE", "unknown mode must name itself")
    gate.assert_contains(out, "sideways", "refusal must echo the bad value")
    gate.log_pass("unknown mode refuses (exit 2) and echoes the bad value")


def test_zero_gates_refuses(gate):
    gate.log_test("an announcer with nothing to announce is miswired, not clean")
    # Exiting 0 here would let a job drop its whole gate list and still look announced.
    out = run_announcer(gate, "skip", 2, "no gates refuses", "no-media-quality")
    gate.assert_contains(out, "usage", "empty gate list must print usage")
    run_announcer(gate, "skip", 2, "no args at all refuses")
    gate.log_pass("zero gate names refuses with usage in both modes of emptiness")


def test_skip_writes_step_summary(gate):
    gate.log_test("skip writes a step summary; hard must write none")
    with harness.temp_dir() as work:
        summary = work / "summary.md"
        summary.write_text("", encoding="utf-8")
        result = harness.run(
            [str(ANNOUNCER), "no-media-quality", "gate-alpha"],
            env={"GATE_SKIP_MODE": "skip", "GITHUB_STEP_SUMMARY": str(summary)},
        )
        gate.assert_exit_code(0, result.rc, "skip with summary should still exit 0")
        written = summary.read_text(encoding="utf-8")
        gate.assert_contains(written, "Gates skipped by", "step summary not written")
        gate.assert_contains(written, "gate-alpha", "step summary must name the gate")

        # CONTROL: hard must not write a summary at all, or every green run would carry a "gates skipped" heading.
        summary.write_text("", encoding="utf-8")
        harness.run(
            [str(ANNOUNCER), "no-media-quality", "gate-alpha"],
            env={"GATE_SKIP_MODE": "hard", "GITHUB_STEP_SUMMARY": str(summary)},
        )
        gate.assert_eq(
            summary.read_text(encoding="utf-8"), "", "hard mode must write no step summary"
        )
    gate.log_pass("skip writes the step summary, hard writes none")


def test_workflow_wiring_covers_every_held_gate(gate):
    gate.log_test("the wiring itself, because a gate held in a job with no announcer is invisible")
    # The announcer is wired into BOTH jobs that hold a media gate, so the wiring is asserted rather than assumed. $GATE_SKIP_WORKFLOW is the seam that lets this assertion be proven able to fire against a COPY.
    override = os.environ.get("GATE_SKIP_WORKFLOW")
    workflow = paths.from_root(override) if override else DEFAULT_WORKFLOW
    if not workflow.is_file():
        gate.log_fail("ci-quality.yml not found at %s" % workflow)
    text = workflow.read_text(encoding="utf-8")

    held = text.count(HELD_MARKER)
    announced = text.count(ANNOUNCE_MARKER)
    if held < MIN_HELD_STEPS:
        gate.log_fail("expected at least %d media-held steps, found %d" % (MIN_HELD_STEPS, held))
    if announced != EXPECTED_ANNOUNCERS:
        gate.log_fail(
            "expected %d announcer invocations (content + i18n), found %d"
            % (EXPECTED_ANNOUNCERS, announced)
        )

    # Every gate named in an announcer invocation must be a gate that is actually held somewhere, and vice versa. Otherwise the announcement drifts into fiction the first time a gate is added or removed.
    for tail in ANNOUNCE_RE.findall(text):
        for name in tail.split():
            if not re.search(r"^.*run: npm run %s$" % re.escape(name), text, re.MULTILINE):
                gate.log_fail(
                    "announcer names '%s' but no step in %s runs it"
                    % (name, paths.relative_to_root(workflow))
                )
    gate.log_pass(
        "wiring: %d held steps, %d announcers, every announced gate exists" % (held, announced)
    )

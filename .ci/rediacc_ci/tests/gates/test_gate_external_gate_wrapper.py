"""Port of `.ci/scripts/test/gates/test-external-gate-wrapper.sh`.

Tests for `.ci/scripts/quality/run-external-gate.sh`, the wrapper that gives
externally-dependent quality gates their three-state behaviour: hard on a normal
PR, absent on a labelled PR via the step `if:`, soft on schedule.

Every direction is exercised with a REAL child process, and both failure
directions are proven able to fire: a soft failure that exits non-zero, or a hard
failure that exits zero, would each silently break the design in the dangerous
direction -- a red nightly nobody wanted, or a green PR that should have blocked.

THE ONE THING THE PORT DOES THAT THE TWIN CANNOT. `env -u EXTERNAL_QUALITY_MODE`
is how the twin unsets the variable for one call. Here the unset is expressed by
passing `None` through `run_wrapper`, which deletes the key from the OVERLAY
before it reaches `harness.run`. Same effect, and it cannot leak into a later
case because the overlay is rebuilt per call rather than mutated in place.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-external-gate-wrapper.sh"

WRAPPER = paths.from_root(".ci", "scripts", "quality", "run-external-gate.sh")

UNSET = object()


def run_wrapper(gate, mode, expected: int, label: str, *argv: str) -> str:
    """Drive the wrapper, assert its exit code, return its merged output.

    `mode` is a string, or `UNSET` for "the variable never reached the step",
    which is the wiring break the fail-closed case exists for.
    """
    if not os.access(WRAPPER, os.X_OK):
        gate.log_fail("wrapper not found or not executable: %s" % WRAPPER)
    env = dict(os.environ)
    env.pop("EXTERNAL_QUALITY_MODE", None)
    if mode is not UNSET:
        env["EXTERNAL_QUALITY_MODE"] = mode
    proc = harness.run([str(WRAPPER), *argv], env=env)
    out = proc.combined
    if proc.rc != expected:
        gate.log_fail("%s: expected exit %d, got %d (output: %s)" % (label, expected, proc.rc, out))
    gate.assertions += 1
    return out


def test_soft_failure_is_green_with_warning(gate):
    out = run_wrapper(gate, "soft", 0, "soft mode swallows a failure", "false")
    gate.assert_contains(out, "::warning::", "soft failure must emit a ::warning:: annotation")
    gate.log_pass("soft mode: failing command exits 0 and warns")


def test_hard_failure_blocks_with_original_code(gate):
    # CONTROL for the case above: the same failing command must still fail in
    # hard mode, and with ITS exit code, not a generic 1.
    out = run_wrapper(gate, "hard", 3, "hard mode preserves the exit code", "bash", "-c", "exit 3")
    gate.assert_not_contains(out, "::warning::", "hard failure must not emit the soft warning")
    gate.log_pass("hard mode: failing command keeps exit code 3, no warning")


def test_success_is_silent_in_both_modes(gate):
    out = run_wrapper(gate, "soft", 0, "soft mode passes a success through", "true")
    gate.assert_not_contains(out, "::warning::", "a passing command must not warn in soft mode")
    run_wrapper(gate, "hard", 0, "hard mode passes a success through", "true")
    gate.log_pass("success exits 0 with no warning in both modes")


def test_unset_mode_fails_closed_to_hard(gate):
    # A wiring break (env var never reaches the step) must behave as HARD:
    # silently going soft would disable a blocking gate with no visible trace.
    run_wrapper(gate, UNSET, 1, "unset mode is hard", "false")
    gate.log_pass("unset EXTERNAL_QUALITY_MODE fails closed to hard")


def test_unknown_mode_refuses(gate):
    # Same fail-closed logic one step further: an unknown value is a wiring bug
    # and must refuse loudly even when the wrapped command SUCCEEDS.
    out = run_wrapper(gate, "sideways", 2, "unknown mode refuses", "true")
    gate.assert_contains(
        out, "unknown EXTERNAL_QUALITY_MODE", "unknown mode must name itself in the refusal"
    )
    gate.log_pass("unknown mode refuses (exit 2) even around a passing command")


def test_no_command_refuses(gate):
    run_wrapper(gate, "hard", 2, "no command refuses")
    gate.log_pass("missing command refuses with usage")


def test_soft_failure_writes_step_summary(gate, tmp_path):
    summary = tmp_path / "step-summary.md"
    summary.write_text("", encoding="utf-8")
    proc = harness.run(
        [str(WRAPPER), "false"],
        env={"EXTERNAL_QUALITY_MODE": "soft", "GITHUB_STEP_SUMMARY": str(summary)},
    )
    gate.assert_exit_code(0, proc.rc, "soft failure with summary should still exit 0")
    gate.assert_contains(
        summary.read_text(encoding="utf-8"), "External gate soft-failed", "step summary not written"
    )
    gate.log_pass("soft failure writes the step summary when GITHUB_STEP_SUMMARY is set")

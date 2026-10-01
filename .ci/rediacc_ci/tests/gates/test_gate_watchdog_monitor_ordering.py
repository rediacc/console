"""Port of `.ci/scripts/test/gates/test-watchdog-monitor-ordering.sh`, retired in W7 P5.

CHECK 6 of the workflow-gates gate (`rediacc_ci.security.workflow_gates.check6`; the bash original `check-workflow-gates.sh` was retired under PLAN-retire-bash-oracles B3) had never been proven able to fail.

WHY IT NEEDS A TEST. CHECK 6 is the rule that keeps the watchdog watching: no step ahead of "Monitor jobs and cancel on failure" may be able to stop the job. It was written after run 33704079162 reported "failure" having monitored NOTHING, and until this file its only evidence of working was that it was green -- which is also exactly what it looks like when its anchor moves, its
allowlist swallows the case, or its verdict is computed off the wrong list.

It also got LOOSER in one direction and STRICTER in another: a step carrying BOTH `continue-on-error: true` and a small `timeout-minutes` is admitted regardless of its name, because those two properties are what the name was ever standing in
for. A rule with a new door in it is precisely the rule that needs a test walking
through the door and then trying the wall beside it.

HOW. The checker is the LIVE GATE's own function, driven against a fixture root, rather than restated here. A restated copy keeps passing after the original changes, which is the failure this file exists to detect. (It used to be a heredoc lifted out of the bash gate; the port is the gate now.)

THE TWIN IS A FLAT SCRIPT, so the port chooses the split: one test per plant, plus the extraction, plus one the twin does not have -- a check that the plant really lands AHEAD of the monitor step, because a plant that landed after it would make every refusal below fire for the wrong reason.
"""

import inspect

from rediacc_ci import paths
from rediacc_ci.security import workflow_gates
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "rediacc_ci", "security", "workflow_gates.py")
WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")

MONITOR_STEP = "      - name: Monitor jobs and cancel on failure"
ANCHOR = "Monitor jobs and cancel on failure"

RUNNER = """import sys
sys.path.insert(0, %r)
import yaml
from rediacc_ci.security import workflow_gates
sys.exit(workflow_gates.check6(yaml, sys.argv[1]))
"""


def check6_source(gate) -> str:
    """CHECK 6, the live gate's own function."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE)
    body = inspect.getsource(workflow_gates.check6)
    if ANCHOR not in inspect.getsource(workflow_gates):
        gate.log_fail(
            "%s no longer names %r, so CHECK 6 has no monitor to order against and this test "
            "now tests NOTHING; fix the anchor, do not delete the test."
            % (paths.relative_to_root(GATE), ANCHOR)
        )
    return body


def run_check(gate, tmp_path, workflow_text: str) -> harness.RunResult:
    """CHECK 6 over a one-file fixture tree holding `workflow_text`."""
    check6_source(gate)
    script = tmp_path / "check6.py"
    script.write_text(RUNNER % str(paths.from_root(".ci")), encoding="utf-8")
    root = tmp_path / "root"
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / "watchdog-monitor.yml").write_text(
        workflow_text, encoding="utf-8"
    )
    python3 = harness.require_tool(
        "python3",
        "install python3; CHECK 6 runs under the interpreter CI gives the gate, "
        "and without one this case is UNRUN rather than fine",
    )
    # CALLING check6 DIRECTLY BYPASSES THE GATE'S OWN pyyaml BOOTSTRAP (`_ensure_yaml`: "pyyaml is absent from ubuntu-slim by default"). Nothing re-establishes it here, so probe and say so.
    harness.require_python_module(
        python3,
        "yaml",
        'python3 -m pip install --user "PyYAML==${PYYAML_VERSION}" -- and if this '
        "fired inside CI, the `Python package tests` step in ci-quality.yml's "
        "quality-static job runs BEFORE the steps that install PyYAML, so the "
        "install belongs ahead of it rather than after",
    )
    return harness.run([python3, str(script), str(root)])


def real_workflow(gate) -> str:
    if not WORKFLOW.is_file():
        gate.log_fail("the real watchdog-monitor.yml is missing")
    return WORKFLOW.read_text(encoding="utf-8")


def plant(gate, *extra: str) -> str:
    """The real workflow with one step inserted immediately AHEAD of the monitor.

    TEXT EDITING, because that is the kind of edit a human makes; a round-trip through pyyaml would normalise away the very shape being judged.
    """
    lines = real_workflow(gate).split("\n")
    step = ["      - name: Planted step"] + ["        " + a for a in extra]
    index = next((i for i, ln in enumerate(lines) if ln.startswith(MONITOR_STEP)), None)
    if index is None:
        gate.log_fail(
            "the monitor step %r is not in watchdog-monitor.yml, so nothing could be "
            "planted ahead of it and every refusal below would prove nothing" % MONITOR_STEP
        )
    lines[index:index] = [*step, ""]
    return "\n".join(lines)


def expect(gate, tmp_path, want: int, label: str, workflow_text: str) -> harness.RunResult:
    result = run_check(gate, tmp_path, workflow_text)
    if result.rc != want:
        gate.log_fail("%s: CHECK 6 exited %d, expected %d" % (label, result.rc, want), result)
    gate.assertions += 1
    gate.log_pass("%s (rc=%d)" % (label, result.rc))
    return result


def test_check6_is_extracted_from_the_live_gate(gate):
    body = check6_source(gate)
    gate.assert_contains(body, "watchdog-monitor.yml", "CHECK 6 must read the watchdog workflow")
    gate.log_pass("CHECK 6 found in the live gate (%d lines)" % len(body.splitlines()))


def test_the_plant_lands_ahead_of_the_monitor(gate):
    """PORT-ONLY ANTI-VACUITY on the instrument, not the subject.

    Every refusal below is "a step ahead of the monitor is refused". If the plant landed AFTER the monitor, CHECK 6 would still refuse it for a different rule and each case would read green having proved the wrong thing.
    """
    planted = plant(gate, "run: exit 1").split("\n")
    where_plant = next(i for i, ln in enumerate(planted) if "name: Planted step" in ln)
    where_monitor = next(i for i, ln in enumerate(planted) if ln.startswith(MONITOR_STEP))
    if where_plant >= where_monitor:
        gate.log_fail(
            "the planted step landed at line %d, at or AFTER the monitor at line %d"
            % (where_plant, where_monitor)
        )
    gate.log_pass(
        "the plant lands at line %d, ahead of the monitor at line %d" % (where_plant, where_monitor)
    )


def test_the_real_workflow_passes(gate, tmp_path):
    expect(gate, tmp_path, 0, "the real watchdog-monitor.yml passes", real_workflow(gate))


def test_a_can_fail_step_is_refused(gate, tmp_path):
    result = expect(
        gate,
        tmp_path,
        1,
        "CONTROL: a can-fail step ahead of the monitor is refused",
        plant(gate, "run: exit 1"),
    )
    gate.assert_contains(
        result.combined,
        "Planted step",
        "the refusal did not name the planted step, so it fired for another reason",
    )
    gate.log_pass("the refusal names the planted step, not something else")


def test_continue_on_error_alone_is_not_enough(gate, tmp_path):
    # It can still HANG, and a hung step ahead of the monitor is a monitor that never starts.
    expect(
        gate,
        tmp_path,
        1,
        "CONTROL: continue-on-error WITHOUT a timeout is still refused",
        plant(gate, "continue-on-error: true", "run: exec cat"),
    )


def test_timeout_alone_is_not_enough(gate, tmp_path):
    # It can still FAIL, and a failed step ahead of the monitor stops the job.
    expect(
        gate,
        tmp_path,
        1,
        "CONTROL: timeout-minutes WITHOUT continue-on-error is still refused",
        plant(gate, "timeout-minutes: 2", "run: exit 1"),
    )


def test_an_expression_continue_on_error_is_refused(gate, tmp_path):
    # An EXPRESSION is not a literal and must not be trusted: its value is not knowable from the YAML, so reading it as true is a guess.
    expect(
        gate,
        tmp_path,
        1,
        "CONTROL: an expression continue-on-error is refused, not read as true",
        plant(
            gate,
            'continue-on-error: ${{ github.event_name == "push" }}',
            "timeout-minutes: 2",
            "run: exit 1",
        ),
    )


def test_both_literals_together_are_admitted(gate, tmp_path):
    expect(
        gate,
        tmp_path,
        0,
        "a step carrying BOTH properties is admitted regardless of its name",
        plant(gate, "continue-on-error: true", "timeout-minutes: 2", "run: exit 1"),
    )


def test_a_renamed_monitor_step_is_refused(gate, tmp_path):
    # Anti-vacuity: a renamed monitor leaves CHECK 6 with nothing to order against, and "nothing to check" must never read as "checked and fine".
    expect(
        gate,
        tmp_path,
        1,
        "CONTROL: a renamed monitor step is refused, never passed vacuously",
        real_workflow(gate).replace(ANCHOR, "Monitor jobs"),
    )

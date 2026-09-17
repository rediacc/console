"""Port of `.ci/scripts/test/gates/test-watchdog-monitor-ordering.sh`.

CHECK 6 of `check-workflow-gates.sh` had never been proven able to fail.

WHY IT NEEDS A TEST. CHECK 6 is the rule that keeps the watchdog watching: no
step ahead of "Monitor jobs and cancel on failure" may be able to stop the job.
It was written after run 33704079162 reported "failure" having monitored NOTHING,
and until this file its only evidence of working was that it was green -- which
is also exactly what it looks like when its anchor moves, its allowlist swallows
the case, or its verdict is computed off the wrong list.

It also got LOOSER in one direction and STRICTER in another: a step carrying BOTH
`continue-on-error: true` and a small `timeout-minutes` is admitted regardless of
its name, because those two properties are what the name was ever standing in
for. A rule with a new door in it is precisely the rule that needs a test walking
through the door and then trying the wall beside it.

HOW. The checker is EXTRACTED FROM THE LIVE GATE rather than restated here. A
restated copy keeps passing after the original changes, which is the failure this
file exists to detect.

THE TWIN IS A FLAT SCRIPT, so the port chooses the split: one test per plant,
plus the extraction, plus one the twin does not have -- a check that the plant
really lands AHEAD of the monitor step, because a plant that landed after it
would make every refusal below fire for the wrong reason.
"""

import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-watchdog-monitor-ordering.sh"

GATE = paths.from_root(".ci", "scripts", "security", "check-workflow-gates.sh")
WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")

MONITOR_STEP = "      - name: Monitor jobs and cancel on failure"
ANCHOR = "Monitor jobs and cancel on failure"

# `python3 - "$ROOT_DIR" <<'PYEOF'` .. `PYEOF`, the awk range the twin uses. Two heredocs in the gate match that opener, which is why the body is selected BY CONTENT below rather than by being the first one found.
HEREDOC_RE = re.compile(
    r"^python3 - \"\$ROOT_DIR\" <<'PYEOF'\n(.*?)^PYEOF$", re.MULTILINE | re.DOTALL
)


def check6_source(gate) -> str:
    """CHECK 6's Python body, lifted out of the live gate."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE)
    bodies = [b for b in HEREDOC_RE.findall(GATE.read_text(encoding="utf-8")) if ANCHOR in b]
    if len(bodies) != 1:
        gate.log_fail(
            "could not extract CHECK 6 from %s: %d heredoc(s) mention %r, expected exactly "
            "1. It was renamed or restructured. This test now tests NOTHING; fix the "
            "extraction, do not delete the test."
            % (paths.relative_to_root(GATE), len(bodies), ANCHOR)
        )
    return bodies[0]


def run_check(gate, tmp_path, workflow_text: str) -> harness.RunResult:
    """CHECK 6 over a one-file fixture tree holding `workflow_text`."""
    script = tmp_path / "check6.py"
    script.write_text(check6_source(gate), encoding="utf-8")
    root = tmp_path / "root"
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / "watchdog-monitor.yml").write_text(
        workflow_text, encoding="utf-8"
    )
    python3 = harness.require_tool(
        "python3",
        "install python3; CHECK 6's body is a python3 program lifted out of the gate, "
        "and without an interpreter this case is UNRUN rather than fine",
    )
    # LIFTING THE BODY BYPASSES THE GATE'S OWN pyyaml BOOTSTRAP, which is the first thing check-workflow-gates.sh does ("pyyaml is absent from ubuntu-slim by default", line 112). Nothing re-establishes it here, so probe and say so.
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

    TEXT EDITING, because that is the kind of edit a human makes; a round-trip
    through pyyaml would normalise away the very shape being judged.
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
        gate.log_fail(
            "%s: CHECK 6 exited %d, expected %d\n%s" % (label, result.rc, want, result.combined)
        )
    gate.assertions += 1
    gate.log_pass("%s (rc=%d)" % (label, result.rc))
    return result


def test_check6_is_extracted_from_the_live_gate(gate):
    body = check6_source(gate)
    gate.assert_contains(body, ANCHOR, "the extracted body must be the one that names the monitor")
    gate.log_pass("CHECK 6 extracted from the live gate (%d lines)" % len(body.splitlines()))


def test_the_plant_lands_ahead_of_the_monitor(gate):
    """PORT-ONLY ANTI-VACUITY on the instrument, not the subject.

    Every refusal below is "a step ahead of the monitor is refused". If the plant
    landed AFTER the monitor, CHECK 6 would still refuse it for a different rule
    and each case would read green having proved the wrong thing.
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

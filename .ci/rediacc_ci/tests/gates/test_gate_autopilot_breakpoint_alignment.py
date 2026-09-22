r"""Port of `.ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh`, retired in W7 P5.

Tests for `.ci/scripts/quality/check_autopilot_breakpoint_alignment.py`, the gate that holds autopilot.yml's copied debug inputs to breakpoint.yml's originals.

THE METHOD IS THE POINT (same doctrine as test_gate_autopilot_workflow_invariants.py): a comparison that has only ever been seen to pass is indistinguishable from `true`. So every direction is proven: the REAL tree passes, unmutated COPIES of the real files still pass (which is what proves the env seams point somewhere real rather than at nothing), and a copy with ONE option
removed must exit 1 with the pinned diagnostic.

The anti-vacuity cases matter as much as the drift case here: this gate's whole failure mode is comparing an empty extraction to an empty extraction and calling that alignment.

WHY NO PERL. The twin edits fixture YAML with `perl -pi -e`/`perl -0pi -e` regex surgery. Python's `re.sub` over the same files, read and rewritten whole, is the same mutation without a second interpreter as a test dependency -- and each mutation is checked against the untouched original with `assert_mutated`, exactly as the twin's own check does, so a regex that stopped matching
cannot pass silently.
"""

import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_autopilot_breakpoint_alignment.py")
REAL_BP = paths.from_root(".ci", "breakpoint", "workflow", "breakpoint.yml")
REAL_AP = paths.from_root(".github", "workflows", "autopilot.yml")


def run_gate(bp_file=None, ap_file=None) -> harness.RunResult:
    env = {
        "AUTOPILOT_BP_ALIGN_BREAKPOINT_FILE": str(bp_file or REAL_BP),
        "AUTOPILOT_BP_ALIGN_AUTOPILOT_FILE": str(ap_file or REAL_AP),
    }
    return harness.run(["python3", str(GATE)], env=env)


def assert_mutated(gate, original, copy) -> None:
    """A mutation that produced an identical file would make the failure case a re-run of the control."""
    if original.read_text(encoding="utf-8") == copy.read_text(encoding="utf-8"):
        gate.log_fail(
            "mutation produced an identical file: %s (the workflow's shape drifted; "
            "fix the mutation)" % copy
        )


def fresh_fixtures(directory):
    """Unmutated copies of both real files."""
    directory.mkdir(parents=True, exist_ok=True)
    bp = directory / "bp.yml"
    ap = directory / "ap.yml"
    bp.write_text(REAL_BP.read_text(encoding="utf-8"), encoding="utf-8")
    ap.write_text(REAL_AP.read_text(encoding="utf-8"), encoding="utf-8")
    return bp, ap


def test_real_tree_passes(gate):
    result = run_gate()
    gate.assert_eq(result.rc, 0, "the real breakpoint.yml and autopilot.yml agree")
    gate.assert_contains(
        result.err, "autopilot debug inputs match breakpoint", "and the gate says so"
    )
    gate.assert_contains(result.err, "300", "naming the option list it actually compared")
    gate.log_pass("control: the real tree is aligned")


def test_unmutated_copies_pass(gate, tmp_path):
    bp, ap = fresh_fixtures(tmp_path / "control")
    result = run_gate(bp, ap)
    gate.assert_eq(result.rc, 0, "unmutated copies pass through the env seams")
    gate.log_pass("control: the env seams read the files they are pointed at")


def test_removed_duration_option_fires(gate, tmp_path):
    bp, ap = fresh_fixtures(tmp_path / "drift")
    # Drop the longest hold from breakpoint's ladder. Nothing else changes, so a green here would mean the comparison is not happening at all.
    text = bp.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("        options: ['5', '10'"):
            lines[i] = line.replace(", '300']", "]")
            break
    mutated = "".join(lines)
    bp.write_text(mutated, encoding="utf-8")
    assert_mutated(gate, REAL_BP, bp)
    result = run_gate(bp, ap)
    gate.assert_eq(result.rc, 1, "one removed duration option must fail")
    gate.assert_contains(
        result.err,
        "AUTOPILOT/BREAKPOINT DRIFT: hold-duration options differ",
        "with the drift class named",
    )
    gate.assert_contains(
        result.err,
        "frozen in MANIFEST.sha256",
        "and the fix direction stated: breakpoint is canonical, autopilot follows",
    )
    gate.log_pass("an option removed on either side is caught, proven by mutation")


def test_boolean_default_flip_fires(gate, tmp_path):
    bp, ap = fresh_fixtures(tmp_path / "boolflip")
    # send-email defaulting to false on one side only: the drift that would print a bearer-credential URL into a public log while the operator believes both tools behave the same.
    text = ap.read_text(encoding="utf-8")
    mutated = re.sub(
        r"(      send-email:.*?\n        default: )true", r"\1false", text, count=1, flags=re.DOTALL
    )
    ap.write_text(mutated, encoding="utf-8")
    assert_mutated(gate, REAL_AP, ap)
    result = run_gate(bp, ap)
    gate.assert_eq(result.rc, 1, "a flipped send-email default must fail")
    gate.assert_contains(result.err, "send-email.default differs", "naming the exact field")
    gate.assert_contains(result.err, "bearer credential", "and why that default is not cosmetic")
    gate.log_pass("type/default drift on the booleans is caught field by field")


def test_missing_file_fails_closed(gate, tmp_path):
    result = run_gate(tmp_path / "never-written.yml")
    gate.assert_eq(result.rc, 1, "a missing breakpoint file must fail")
    gate.assert_contains(result.err, "nothing to compare cannot pass", "as an anti-vacuity refusal")
    bp, _ap = fresh_fixtures(tmp_path / "half")
    result = run_gate(bp, tmp_path / "also-never-written.yml")
    gate.assert_eq(result.rc, 1, "a missing autopilot file must fail too")
    gate.log_pass("anti-vacuity: a missing side is a failure, never a pass")


def test_missing_input_block_fails_closed(gate, tmp_path):
    bp, ap = fresh_fixtures(tmp_path / "noblock")
    # Rename the autopilot input so the block cannot be found. The gate must refuse rather than compare its value against an empty string.
    text = ap.read_text(encoding="utf-8")
    mutated = re.sub(r"(?m)^      hold-duration:", "      renamed-duration:", text, count=1)
    ap.write_text(mutated, encoding="utf-8")
    assert_mutated(gate, REAL_AP, ap)
    result = run_gate(bp, ap)
    gate.assert_eq(result.rc, 1, "a renamed input block must fail")
    gate.assert_contains(
        result.err,
        "could not extract autopilot hold-duration options",
        "naming what it failed to find",
    )
    gate.assert_contains(result.err, "refuses to pass blind", "and refusing explicitly")
    gate.log_pass("a lost extraction target is a failure, not an empty-equals-empty pass")


def test_extractor_floor_fires(gate, tmp_path):
    bp, ap = fresh_fixtures(tmp_path / "floor")
    # A two-entry list is the shape a half-broken extractor produces. The floor
    # exists because "" != "" comparisons are not the only vacuous pass: a list of
    # one or two entries would compare fine and mean nothing.
    pattern = re.compile(r"(?m)^        options: \['5', '10'.*$")
    for path in (bp, ap):
        text = path.read_text(encoding="utf-8")
        mutated = pattern.sub("        options: ['5', '10']", text, count=1)
        path.write_text(mutated, encoding="utf-8")
    assert_mutated(gate, REAL_BP, bp)
    result = run_gate(bp, ap)
    gate.assert_eq(result.rc, 1, "two IDENTICAL but implausibly short lists must still fail")
    gate.assert_contains(result.err, "fewer than 5 options", "on the floor, not on equality")
    gate.log_pass("the floor catches a broken extractor that equality alone would pass")

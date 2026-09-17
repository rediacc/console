"""Port of `.ci/scripts/test/gates/test-dead-case-arms.sh`.

Tests for `.ci/scripts/quality/check-dead-case-arms.sh`, the scanner that catches a
`case` arm globbing for a `field=` token no non-test script emits. An arm like that
is an assertion that cannot fail, and the gate exists because one of them passed permanently while proving nothing.

THE SUBJECT IS CONTROL-FIRST, so the FIRST case here is the seam-free one: the real invocation over the real tree, asserting both that it is clean AND that its own planted-arm control fired. A gate that reported "clean" without its control firing would be reporting on a scanner nobody had seen work.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. `check-dead-case-arms.sh` reads `.ci/scripts/test`, `.ci/media`, `.ci/scripts`, `scripts` and `packages/www/scripts`
with recursive greps over the working tree, and every case below reaches the real
tree at least through `DEAD_CASE_MEDIA_DIRS`, which the twin never overrides. So it is a real-tree SCANNER: a battery step rewriting a scanned file mid-grep is the `grep: ... No such file or directory` flake that would be blamed on this port.
`REAL_TREE_TWIN = True` is what buys the serialisation, and it is only honoured
because this module declares no `XDIST_GROUP` of its own -- see `real_tree_admission` in `test_twin_parity.py`, which refuses the combination.

WHAT IS DELIBERATELY NOT RE-IMPLEMENTED. The scanner is never reproduced in Python. Every case drives the real `bash check-dead-case-arms.sh` with the same two environment overrides the twin uses, so the code under test is the code that ships.
"""

import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-dead-case-arms.sh"

# The twin reads the real tree (`.ci/media` is scanned on every invocation, and the default CODE_DIRS greps `.ci/scripts`, `scripts` and `packages/www/scripts`), so this module must be serialised against the battery. See the module docstring.
REAL_TREE_TWIN = True

GATE = paths.from_root(".ci", "scripts", "quality", "check-dead-case-arms.sh")

# The twin's `run_gate` default. Repeated rather than imported because it IS the twin's declaration, and a port that quietly widened it would be testing a different corpus than its original.
DEFAULT_CODE_DIRS = ".ci/scripts scripts"


def require_gate(gate) -> str:
    """The subject, proved present and executable before anything is claimed.

    The twin asserts `[ -x "$GATE" ]` at load time and dies there. Doing it per
    case is the same claim made at the point of use, and it keeps a missing
    subject from arriving as a bare `Permission denied` from subprocess.
    """
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    if not os.access(GATE, os.X_OK):
        gate.log_fail(
            "subject under test is not executable: %s. Fix: chmod +x %s"
            % (paths.relative_to_root(GATE), paths.relative_to_root(GATE))
        )
    return harness.require_tool("bash", "install bash; the subject IS a bash script")


def run_gate(gate, test_dirs, code_dirs: str = DEFAULT_CODE_DIRS) -> harness.RunResult:
    """`run_gate` from the twin: the real scanner, two env overrides, merged streams.

    The twin captures `2>&1` into `$LAST` and asserts on the merged text, so the callers below read `.combined` for the same reason.
    """
    bash = require_gate(gate)
    return harness.run(
        [bash, os.fspath(GATE)],
        cwd=paths.repo_root(),
        env={
            "DEAD_CASE_TEST_DIRS": os.fspath(test_dirs),
            "DEAD_CASE_CODE_DIRS": code_dirs,
        },
    )


def test_real_tree_is_clean_and_the_control_fired(gate):
    """Seam-free: the real invocation over the real tree, no overrides at all.

    This is the line the manifest's BLOCKER names, and it is why the subject is registered as a real-tree reader in the lock.
    """
    bash = require_gate(gate)
    result = harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root())
    gate.assert_exit_code(
        0, result.rc, "the real tree must have no dead case arms (output: %s)" % result.combined
    )
    gate.assert_contains(
        result.combined,
        "control fired",
        "the verdict must state its control fired, not just 'clean'",
    )
    gate.log_pass("real tree clean, and the gate says its control fired")


def test_a_dead_arm_is_caught(gate):
    with harness.temp_dir() as d:
        tests = d / "test"
        tests.mkdir(parents=True, exist_ok=True)
        # A key that exists in no code directory: the arm can never match.
        (tests / "dead.sh").write_text(
            'case "$out" in\n    *"zzznosuchfield=20"*)\n        log_fail "x" ;;\nesac\n',
            encoding="utf-8",
        )
        result = run_gate(gate, tests)
        gate.assert_exit_code(1, result.rc, "a case arm globbing for a nonexistent field must fail")
        gate.assert_contains(result.combined, "zzznosuchfield", "names the dead field")
        gate.assert_contains(result.combined, "DEAD", "says the arm is dead")
        gate.log_pass("a dead case arm is caught and named")


def test_a_live_arm_passes(gate):
    """CONTROL for the case above. Same shape, but the field DOES exist in the code under test, so the arm can match and must not be reported. Without this, a scanner that flagged every case arm would look correct."""
    with harness.temp_dir() as d:
        tests = d / "test"
        code = d / "code"
        tests.mkdir(parents=True, exist_ok=True)
        code.mkdir(parents=True, exist_ok=True)
        (code / "emit.sh").write_text('printf "livefield=%s\\n" "$x"\n', encoding="utf-8")
        (tests / "live.sh").write_text(
            'case "$out" in\n    *"livefield=20"*)\n        log_fail "x" ;;\nesac\n',
            encoding="utf-8",
        )
        result = run_gate(gate, tests, os.fspath(code))
        gate.assert_exit_code(
            0,
            result.rc,
            "an arm whose field is emitted by real code must pass (output: %s)" % result.combined,
        )
        gate.log_pass("a live arm is not flagged (the scanner is not a blanket refusal)")


def test_the_founding_defect_fires(gate):
    """THE case this gate was built from, kept as a permanent fixture. `cores=` is
    special precisely because the subject's own header describes the defect in prose, and the first implementation grepped comments too -- so the only two
    occurrences of `cores=` in the whole tree were its own comment lines, and it
    ruled the arm live and MISSED the bug it exists to catch. Verified 2026-08-05: exit 0 on this exact fixture before the fix, exit 1 after. If `key_is_live` ever stops filtering comments, this case goes red."""
    with harness.temp_dir() as d:
        tests = d / "test"
        tests.mkdir(parents=True, exist_ok=True)
        (tests / "founding.sh").write_text(
            'case "$1" in\n    *"cores=20"*)\n        log_fail "host leak" ;;\nesac\n',
            encoding="utf-8",
        )
        result = run_gate(gate, tests)
        gate.assert_exit_code(
            1, result.rc, "the founding defect (cores= documented only in comments) must FIRE"
        )
        gate.assert_contains(result.combined, "cores", "names the field the dead arm globs for")
        gate.log_pass(
            "the founding defect fires: prose describing a bad pattern no longer immunises the tree"
        )


def test_comments_are_not_assertions(gate):
    """A commented-out arm is prose, not a claim, and flagging it would make the gate noisy enough to be suppressed."""
    with harness.temp_dir() as d:
        tests = d / "test"
        tests.mkdir(parents=True, exist_ok=True)
        (tests / "commented.sh").write_text(
            '# case "$out" in\n#     *"zzznosuchfield=20"*)\n', encoding="utf-8"
        )
        result = run_gate(gate, tests)
        gate.assert_exit_code(
            0,
            result.rc,
            "a commented arm must not be reported (output: %s)" % result.combined,
        )
        gate.log_pass("commented-out arms are prose, not assertions")


def test_the_scanned_media_root_is_not_empty(gate):
    """ADDED BY THE PORT, and it is the anti-vacuity claim the twin leaves implicit.

    The subject refuses when `DEAD_CASE_MEDIA_DIRS` holds no shell files, because a scan root that has stopped matching reports clean forever and that green is indistinguishable from a clean tree. The twin never asserts the refusal exists, so a subject that lost it would keep every twin case green. This drives the subject at an EMPTY media root and requires the loud refusal.
    """
    bash = require_gate(gate)
    with harness.temp_dir() as d:
        tests = d / "test"
        empty_media = d / "media"
        tests.mkdir(parents=True, exist_ok=True)
        empty_media.mkdir(parents=True, exist_ok=True)
        result = harness.run(
            [bash, os.fspath(GATE)],
            cwd=paths.repo_root(),
            env={
                "DEAD_CASE_TEST_DIRS": os.fspath(tests),
                "DEAD_CASE_CODE_DIRS": DEFAULT_CODE_DIRS,
                "DEAD_CASE_MEDIA_DIRS": os.fspath(empty_media),
            },
        )
        gate.assert_exit_code(1, result.rc, "an empty media scan root must FAIL, not pass")
        gate.assert_contains(result.combined, "VACUOUS", "says the scan root proves nothing")
        gate.log_pass("an empty media scan root is refused (anti-vacuity), not reported clean")

    # And the real root is non-trivial, printed so a collapse is visible.
    real_media = pathlib.Path(paths.from_root(".ci", "media"))
    count = len(sorted(real_media.glob("*.sh"))) if real_media.is_dir() else 0
    if count == 0:
        gate.log_fail(
            ".ci/media holds no shell files, so the media half of every case above "
            "scanned nothing. The subject's own VACUOUS refusal should have fired first; "
            "that it did not means this port and the subject disagree about the root."
        )
    gate.log_pass("the real media scan root holds %d shell file(s)" % count)

"""`rediacc_ci.quality.script_exec_bit`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-script-exec-bit.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-script-exec-bit.observations.jsonl`, which licensed the port at K=5; the twin was retired in W7 P5 and the
fixture cases were retired with it.

WHAT THAT CORPUS COVERED, so the shape of the argument survives the deletion: an offender (must fire), an executable script (must stay quiet), a reference inside a comment (must stay quiet), and a `../decoy.sh` in a subdirectory (must stay quiet, and is the case whose first version in the twin could not fail because the correct and the broken behaviour deduped to the same
set). The fixture was a REAL git repository, because this gate reads the INDEX mode rather than the filesystem mode. Each of those is a control in the port's own `--selftest`, whose count the last case below refuses to let collapse.

WHAT IS ASSERTED HERE AND NOWHERE ELSE: that the port's REFUSAL status is 2 and not 1. The twin distinguished "the control could not fire" from "the tree has offenders", and a port that collapsed them would make an unrunnable gate read as a failing tree, which is the direction that gets a gate deleted.
"""

from rediacc_ci.quality import script_exec_bit as gate
from rediacc_ci.tests import differential as diff

MODULE = "script_exec_bit"


def test_colour_is_unconditional():
    """The twin coloured with no tty test, so the port does too.

    This is the ONE place the difference would have been invisible: `rediacc_ci.log` decides colour by `isatty`, and a port that used it would emit no escapes off a terminal. Every retired differential ran off a pipe, so it would have agreed with a twin that also emitted none. The twin emitted them ANYWAY, which is why this asserts the escape count is non-zero rather than
    merely equal.
    """
    assert gate.RED.startswith("\033[")
    assert gate.RED == "\033[31m", "the twin used 31m, not common.sh's 0;31m"
    assert gate.GREEN == "\033[32m"


def test_refusal_status_is_two():
    """2 is "the control could not fire". 1 is "the tree has offenders"."""
    assert gate.EXIT_REFUSE == 2
    assert gate.EXIT_REFUSE != 1


def test_dirname_of_a_root_file_is_a_dot():
    """The one-character difference that made every root reference unmatchable.

    `dirname caller.yml` is `.` in the shell and `""` in Python, so the naive port produced `/victim.sh`, an absolute path matching nothing in any index. The gate would then have reported a clean tree for exactly the class of file the 2026-08-20 incident was about. Pinned here as well as in the selftest because it is a silent-blindness defect, and those are the ones worth two
    controls.
    """
    assert gate.resolve("caller.yml", "./victim.sh") == "victim.sh"
    assert gate.resolve("a/b.yml", "./victim.sh") == "a/victim.sh"


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    assert int(out.split(" control(s)")[0].strip()) >= 14

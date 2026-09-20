"""`rediacc_ci.quality.probe_parity`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-probe-parity.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-probe-parity.observations.jsonl`, which licensed the port at K=5; the twin was retired in W7 P5 and the fixture
cases were retired with it, because a specimen holding one implementation compares nothing.

WHAT THAT CORPUS COVERED, so the shape of the argument survives the deletion. This gate is a SET COVERAGE question with two symmetrical ways to be wrong: forgive everything (report parity always) or forgive nothing (report every verb missing). The corpus therefore carried a clean pair, a gap, the exemption being honoured, the exemption NOT being over-applied, and both
empty-extraction controls, which are the branches the twin's missing `|| true` made unreachable until 96355d3b5 on 2026-09-06. Every one of those is a control in the port's own `--selftest`, which the count below refuses to let collapse.
"""

import shutil
import subprocess

import pytest

from rediacc_ci.quality import probe_parity as gate
from rediacc_ci.tests import differential as diff

MODULE = "probe_parity"


def test_selftest_exits_zero_and_prints_a_count():
    """`--selftest` is a real run, not an import.

    EXIT 0 WITH ZERO PASS LINES IS A FAILURE, so the count line is asserted as well as the status. A selftest whose cases stopped executing would still exit 0, and the `Controls` floor is what turns that into a red; this asserts the floor is actually reported.
    """
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    ran = int(out.split(" control(s)")[0].strip())
    assert ran >= 15, "the control corpus collapsed to %d assertions" % ran


def test_consumer_extractor_rejects_a_different_binary():
    """The negative half of the consumer extractor, called directly.

    Exported helpers exist so a case can drive the decision without shelling out;
    this is the one that would silently pass if the pattern were loosened to `\\['[a-z]+`.
    """
    assert gate.consumer_verbs("execFileSync('gpg', ['add', k])") == []
    assert gate.consumer_verbs("execFileSync('keyctl', ['add', k])") == ["add"]


def test_probe_extractor_respects_the_word_boundary():
    """`xkeyctl` and `re-keyctl` are different commands, and must not contribute."""
    assert gate.probe_verbs("xkeyctl show @u") == []
    assert gate.probe_verbs("re-keyctl add @u") == []
    assert gate.probe_verbs("keyctl show @u") == ["show"]


def test_bash_is_available():
    """The port's own selftest shells out, so the case above needs a shell.

    A missing tool is a LOUD failure with the fix in the message, never a stack trace read as flake.
    """
    if shutil.which("bash") is None:  # pragma: no cover - defensive
        pytest.fail("bash is not on PATH; install it (apt-get install bash)")
    assert subprocess.run(["bash", "-c", "true"], check=False).returncode == 0

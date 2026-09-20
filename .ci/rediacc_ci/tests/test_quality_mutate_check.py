"""`rediacc_ci.quality.mutate_check`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-mutate-check.sh` over a fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. The twin had no environment seam -- it resolved its root from its OWN location -- so it was copied into the fixture along with the real mutation runner and its miniature suite.
Same recipe as the committed ledger, `.ci/shadow/w7p2-mutate-check.observations.jsonl`, which licensed the port at K=5.

THE TWIN WAS RETIRED IN W7 P5 and the byte comparison went with it. What that comparison bought over the ledger is worth recording, because it is what is gone: `bad()` prints ` FAIL <label>` with ONE space, and `scripts/lib/shadow-gate.ts`'s marker needs `FAIL:` or two spaces, so every per-scenario failure line is CHATTER to the comparator and the only compared finding is the
final count. The ledger therefore pins how many scenarios failed and not WHICH. The decision functions below are driven directly instead, both directions for every rule, and the gate's own selftest carries the controls.
"""

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import mutate_check as gate

FIXDIR = ".ci/scripts/test/fixtures/mutate-check"


# --------------------------------------------------------------------------- The decision functions, driven directly. Both directions for every rule. ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "rc", "ok"),
    [
        pytest.param(gate.RC_ZERO, 0, True, id="zero-hits"),
        pytest.param(gate.RC_ZERO, 1, False, id="zero-misses"),
        pytest.param(gate.RC_NONZERO, 1, True, id="nonzero-hits"),
        pytest.param(gate.RC_NONZERO, 0, False, id="nonzero-misses"),
        pytest.param(gate.RC_TWO, 2, True, id="two-hits"),
        pytest.param(gate.RC_TWO, 1, False, id="two-is-not-any-nonzero"),
    ],
)
def test_rc_ok(mode: str, rc: int, ok: bool) -> None:
    assert gate.rc_ok(mode, rc) is ok


def test_an_unknown_rc_mode_raises_rather_than_answering_false() -> None:
    with pytest.raises(ValueError, match="unknown rc mode"):
        gate.rc_ok("nope", 0)


@pytest.mark.parametrize(
    ("text", "indented"),
    [
        pytest.param('    echo "  PASS: 900 x"\n', True, id="pass-line"),
        pytest.param('    echo "  FAIL: 900 x"\n', True, id="fail-line"),
        pytest.param('echo "  PASS: 900 x"\n', False, id="flush-left"),
        pytest.param('    echo "PASS: 900 x"\n', False, id="wrong-inner-spacing"),
        pytest.param("", False, id="empty"),
    ],
)
def test_indented_result_lines(text: str, indented: bool) -> None:
    assert gate.indented_result_lines(text) is indented


def test_the_needle_is_a_fixed_string_not_a_pattern() -> None:
    """`grep -qF`. A metacharacter in the needle is literal in both directions."""
    assert gate.scenario_passed(gate.RC_NONZERO, 1, "a.c", "a.c") is True
    assert gate.scenario_passed(gate.RC_NONZERO, 1, "abc", "a.c") is False


def test_the_real_fixture_suite_still_indents() -> None:
    """Scenario 5 over the LIVE fixture: the reason it indents must not be lost."""
    suite = paths.from_root(FIXDIR, "fixture-suite.sh")
    assert gate.indented_result_lines(suite.read_text(encoding="utf-8"))


def test_selftest_passes_and_is_not_vacuous(capsys) -> None:
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert "control(s) passed" in out
    assert int(out.strip().split("\n")[-1].split()[0]) >= 18

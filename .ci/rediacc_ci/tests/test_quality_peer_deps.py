"""`rediacc_ci.quality.peer_deps`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-peer-deps.sh` over a fixture, with stdout and stderr captured SEPARATELY, and the bytes it produced were compared against the port's over the same fixture. That shape is what `.ci/scripts/quality/check-python-lint.sh` uses for its own control: build a specimen, run the instrument, compare.

THE COMMITTED LEDGER IS WHAT CARRIES THE CLAIM NOW. `.ci/shadow/w7p2-peerdeps.observations.jsonl` records the verdict over K distinct trees and licensed the port at K=5; the twin was retired in W7 P5 and the cases that ran it were retired with it, because a fixture holding one implementation compares nothing. What remains is the substring rule the whole verdict turns on and the
gate's own controls.
"""

from rediacc_ci.quality import peer_deps


def test_invalid_lines_is_a_substring_test() -> None:
    """`grep -q "invalid"`: substring, case-sensitive, both directions."""
    assert peer_deps.invalid_lines("a invalid b\nclean\n") == ["a invalid b"]
    assert peer_deps.invalid_lines("cache invalidate\n") == ["cache invalidate"]
    assert peer_deps.invalid_lines("Invalid capitalised\n") == []
    assert peer_deps.invalid_lines("") == []


def test_selftest_passes() -> None:
    """The gate's own controls, driven in-process."""
    assert peer_deps.selftest() == 0

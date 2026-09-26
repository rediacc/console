"""`rediacc_ci.quality.host_toolchain_coverage` against the pipelines it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. Both extractors are five-stage shell pipelines -- `grep -oE | sed -E | tr | sed | sort -u` -- and three of those stages have edges a "sensible" rewrite loses: `grep -o` prints the MATCH rather than the line (which is why the `$` anchor in the following sed always fires), `tr ' '` splits on a space and on nothing else, and
`sort -u` de-duplicates as well as ordering. A table of expected strings would be a table of what the port does, asserted against itself.

The bash fragments below are lifted from `.ci/scripts/quality/check-host-toolchain-coverage.sh` lines 57-69 with the parameters substituted, and nothing else changed. They are NOT the whole gate: the whole gate is what the committed shadow ledger `.ci/shadow/w7p2-hosttoolchain.observations.jsonl` compares over five distinct trees. This file covers the seams that ledger cannot
isolate.
"""

import pathlib

import pytest

from rediacc_ci.quality import host_toolchain_coverage as htc
from rediacc_ci.tests import differential as diff

# Every shape the GATED_TOOLS extractor has to survive.
GATED_CASES = [
    "GATED_TOOLS='shfmt|shellcheck|ruff|actionlint'\n",  # the ordinary one
    "GATED_TOOLS='a'\n",  # one member
    "GATED_TOOLS=''\n",  # empty literal
    "GATED_TOOLS='a||b'\n",  # an empty alternation member is dropped
    "GATED_TOOLS='b|a|b'\n",  # duplicates collapse, order is SORTED
    "GATED_TOOLS='a|b' # a trailing comment\n",  # grep -o keeps only the match
    "  GATED_TOOLS='a|b'\n",  # indented: the ^ anchor makes it invisible
    "local GATED_TOOLS='a|b'\n",  # prefixed: invisible for the same reason
    "OTHER_TOOLS='a|b'\n",  # a different name
    "GATED_TOOLS='a'\nGATED_TOOLS='b'\n",  # two lines, both contribute
    "echo hi\n",  # no literal at all
    "",  # an empty file
]

# Every shape the ARRAY extractor has to survive.
ARRAY_CASES = [
    "NPX_TOOLS=(ruff go shfmt)\n",
    "NPX_TOOLS=()\n",  # empty
    "NPX_TOOLS=(a  b)\n",  # a double space yields no empty member
    "NPX_TOOLS=(b a b)\n",  # duplicates collapse, order is SORTED
    "NPX_TOOLS=(ruff\tgo)\n",  # a TAB does not split: one pseudo-tool
    "NPX_TOOLS=(a b) # trailing\n",  # grep -o keeps only the match
    "  NPX_TOOLS=(a b)\n",  # indented: invisible
    "NPX_TOOLS=(\n  a\n)\n",  # multi-line: invisible, the documented blind spot
    "BARE_TOOLS=(a b)\n",  # the other name
    "echo hi\n",
]


def _bash_gated(text: str, tmp_path: pathlib.Path) -> list[str]:
    (tmp_path / "f").write_text(text, encoding="utf-8")
    script = (
        "grep -oE \"^GATED_TOOLS='[^']*'\" f 2>/dev/null | "
        "sed -E \"s/^GATED_TOOLS='([^']*)'$/\\1/\" | "
        "tr '|' '\\n' | sed '/^$/d' | sort -u"
    )
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code in (0, 1), err
    return [line for line in out.split("\n") if line]


def _bash_array(text: str, name: str, tmp_path: pathlib.Path) -> list[str]:
    (tmp_path / "f").write_text(text, encoding="utf-8")
    script = (
        'grep -oE "^%s=\\([^)]*\\)" f 2>/dev/null | '
        'sed -E "s/^%s=\\(([^)]*)\\)$/\\1/" | '
        "tr ' ' '\\n' | sed '/^$/d' | sort -u"
    ) % (name, name)
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code in (0, 1), err
    return [line for line in out.split("\n") if line]


@pytest.mark.parametrize("text", GATED_CASES)
def test_gated_extractor_matches_bash(text: str, tmp_path: pathlib.Path) -> None:
    assert htc.extract_gated_tools(text) == _bash_gated(text, tmp_path)


@pytest.mark.parametrize("text", ARRAY_CASES)
@pytest.mark.parametrize("name", ["NPX_TOOLS", "BARE_TOOLS"])
def test_array_extractor_matches_bash(text: str, name: str, tmp_path: pathlib.Path) -> None:
    assert htc.extract_array(text, name) == _bash_array(text, name, tmp_path)


DIFF_CASES = [
    (["a", "b"], ["a"]),  # one missing
    (["a"], ["a", "b"]),  # a SUPERSET is fine: the documented `go` case
    ([], ["a"]),  # nothing pinned
    (["a"], []),  # nothing covered
    (["a", "b", "c"], ["b"]),  # several missing, order is SORTED
]


@pytest.mark.parametrize(("gated", "covered"), DIFF_CASES)
def test_set_difference_matches_comm(
    gated: list[str], covered: list[str], tmp_path: pathlib.Path
) -> None:
    """`comm -23 <(sorted gated) <(sorted covered)`, run for real.

    `comm` is the stage a port most easily gets backwards: `-23` suppresses columns 2 and 3, leaving lines UNIQUE TO THE FIRST FILE. A port that computed the other direction would report the guard's superset members as findings and would look like a much stricter gate.
    """
    (tmp_path / "g").write_text("".join(t + "\n" for t in sorted(gated)), encoding="utf-8")
    (tmp_path / "c").write_text("".join(t + "\n" for t in sorted(covered)), encoding="utf-8")
    code, out, err = diff.bash_streams("comm -23 g c", cwd=str(tmp_path))
    assert code == 0, err
    assert htc.missing_from(gated, covered) == [line for line in out.split("\n") if line]


def test_the_multi_line_array_blind_spot_is_a_refusal_not_a_pass(tmp_path: pathlib.Path) -> None:
    """THE BLIND SPOT, AND THE THING THAT SAVES IT.

    A `NPX_TOOLS=(` array written one tool per line is invisible to the
    extractor. That could have made the gate report full coverage over a guard it could not read; instead the empty result trips the "arrays moved or were renamed" branch and the gate refuses. Both halves are asserted, because the second is the only reason the first is survivable.
    """
    guard = "NPX_TOOLS=(\n  ruff\n)\nBARE_TOOLS=(ruff)\n"
    assert htc.extract_array(guard, "NPX_TOOLS") == []
    assert htc.extract_array(guard, "NPX_TOOLS") == _bash_array(guard, "NPX_TOOLS", tmp_path)
    assert htc.missing_from(["ruff"], []) == ["ruff"]


def test_selftest_is_green() -> None:
    """The gate's own controls, driven in-process. Exit 0 or the port is broken."""
    assert htc.selftest() == 0

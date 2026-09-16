"""`rediacc_ci.quality.shell_size` against `wc -l` and the twin's grep.

WHY A DIFFERENTIAL. The interesting half of this gate is a three-valued probe --
a count, UNREADABLE, or "" -- built on `wc -l` and one `grep -qE`. Both are
external tools whose edges (a missing final newline, an indented directive, a
directive with extra flags) are decided by them and not by anything a reader
could infer. Running them and comparing is the only form of this test that can
fail for the right reason.

The whole gate, its enumeration and its S1/S2 assertions are covered by
`.ci/shadow/w7p2-shell-size.observations.jsonl` over five distinct trees.
"""

import pathlib

import pytest

from rediacc_ci.quality import shell_size as mod
from rediacc_ci.tests import differential as diff

# The shapes `wc -l` and Python disagree about if a port is careless.
COUNT_CASES = [
    "echo 1\necho 2\n",  # the ordinary one
    "echo 1\necho 2",  # NO trailing newline: wc says 1, splitlines says 2
    "",  # empty file
    "\n",  # one empty line
    "\n\n\n",  # only newlines
]


@pytest.mark.parametrize("content", COUNT_CASES)
def test_line_count_matches_wc(tmp_path: pathlib.Path, content: str) -> None:
    target = tmp_path / "f.sh"
    target.write_text(content, encoding="utf-8")
    code, out, err = diff.bash_streams("wc -l <f.sh", cwd=str(tmp_path))
    assert code == 0, err
    assert content.count("\n") == int(out.strip())


# Every spelling of the escape hatch, and every near-miss.
DIRECTIVE_CASES = [
    "# shellcheck extended-analysis=false\n",  # the documented form
    "#shellcheck extended-analysis=false\n",  # no space after #
    "  # shellcheck shell=bash extended-analysis=false\n",  # indented, extra flags
    "\t#\tshellcheck\textended-analysis=false\n",  # tabs
    "# extended-analysis=false\n",  # the flag WITHOUT the shellcheck token
    "# shellcheck disable=SC2086\n",  # a directive, but not this one
    "# we could add extended-analysis=false here\n",  # prose about the flag
    "echo '# shellcheck extended-analysis=false'\n",  # an echoed string, not a line
    "",  # nothing at all
]


@pytest.mark.parametrize("content", DIRECTIVE_CASES)
def test_directive_detection_matches_grep(tmp_path: pathlib.Path, content: str) -> None:
    """The port's matcher and the twin's `grep -qE` reach the same verdict."""
    target = tmp_path / "f.sh"
    target.write_text(content, encoding="utf-8")
    script = (
        "grep -qE '^[[:space:]]*#[[:space:]]*shellcheck[[:space:]]+.*extended-analysis=false' f.sh"
    )
    code, _out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    assert mod.has_directive(content) is (code == 0)


def test_over_limit_is_three_valued(tmp_path: pathlib.Path) -> None:
    """A count, UNREADABLE, or "". Collapsing the last two is the defect."""
    small = tmp_path / "s.sh"
    small.write_text(mod.gen_lines(3), encoding="utf-8")
    assert mod.over_limit(small, 10) == ""
    big = tmp_path / "b.sh"
    big.write_text(mod.gen_lines(30), encoding="utf-8")
    assert mod.over_limit(big, 10) == "30"
    assert mod.over_limit(tmp_path / "gone.sh", 10) == mod.UNREADABLE

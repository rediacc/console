"""`rediacc_ci.quality.tracked_sidecars` against the python heredoc it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. This gate's parser IS a
Python heredoc inside the bash twin, so the two implementations can be run
against the same input and compared for real rather than against a table of what
the port happens to do. That is the strongest form this test can take, and it is
available only because the twin already shelled out to python3.

What this file does NOT cover, because the committed shadow ledger
`.ci/shadow/w7p2-tracked-sidecars.observations.jsonl` covers it over five
distinct trees: the whole gate, the `git ls-files` enumeration and the output
shape. This file covers the seams that ledger cannot isolate.
"""

import subprocess

import pytest

from rediacc_ci.quality import tracked_sidecars as mod

# The heredoc from `.ci/scripts/quality/check-tracked-sidecars.sh`, lifted verbatim. Nothing is changed, so a divergence here is a divergence in the port.
TWIN_PARSER = """
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"The sidecars \\((.*?)\\)", src, re.S)
if not m:
    sys.exit(0)
for tok in re.split(r"[,\\s]+", m.group(1)):
    tok = tok.strip()
    if tok.startswith("."):
        print(tok)
"""

# Every shape the docstring has taken or could take. The comment on each is the
# property it is here for; a case with no property gets deleted the first time
# someone tidies this file.
DOCSTRINGS = [
    '"""The sidecars (.requests, .sessions)"""',  # the ordinary one
    '"""The sidecars (.a,\n.b,\n.c)"""',  # spans lines: re.S is required
    '"""The sidecars (.a) and later (.b)"""',  # non-greedy: stop at the first )
    '"""The sidecars (.a, and, .b)"""',  # a non-dotted token is prose
    '"""The sidecars ()"""',  # present but empty
    '"""No such phrase here."""',  # absent entirely
    "",  # empty file
    '"""The sidecars (.events.*, .waiter-*)"""',  # dots and globs inside tokens
    '"""The sidecars (\n.only-one\n)"""',  # leading and trailing newlines
]


@pytest.mark.parametrize("source", DOCSTRINGS)
def test_parser_matches_the_twins_heredoc(tmp_path, source: str) -> None:
    """The port's parser and the twin's heredoc agree, token for token."""
    target = tmp_path / "wl_store.py"
    target.write_text(source, encoding="utf-8")
    proc = subprocess.run(
        ["python3", "-", str(target)],
        input=TWIN_PARSER,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    expected = [line for line in proc.stdout.split("\n") if line != ""]
    assert mod.parse_patterns(source) == expected


def test_control_is_an_or_not_an_and() -> None:
    """One dud pattern must not disarm the whole control.

    The twin sets `control_hit=1` if ANY pattern self-matches. An AND looks
    stronger and would be a different gate: a single unbalanced bracket would
    then fail the control rather than being the one dud it is.
    """
    assert mod.control_fires([".waiter-*"]) is True
    assert mod.control_fires([]) is False


def test_ls_files_status_is_returned_not_swallowed(tmp_path) -> None:
    """A failed enumeration must be distinguishable from an empty one.

    This is the whole point of the function: `2>/dev/null || true` there would
    make a broken index read exactly like a clean tree.
    """
    status, text = mod.ls_files(".claude/hooks/stop/.sessions", tmp_path)
    assert status != 0, "a directory that is not a git repo must not report success"
    assert text != "", "git's complaint is DATA on this path, not a stream to discard"

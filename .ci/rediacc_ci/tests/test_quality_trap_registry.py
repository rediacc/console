"""`rediacc_ci.quality.trap_registry` against the awk parser it replaces.

WHY A DIFFERENTIAL ON THE PARSER. It is a fence-tracking state machine whose whole reason for existing is that a `## ` inside a fenced example in a trap body must not become a phantom entry, and trap bodies routinely carry markdown examples. A table of expected entries would be a table of what the port does. Running the twin's awk on the same corpus is the only comparison that can
fail
for the right reason.

The whole gate, including F6's twenty-one planted controls, is covered by `.ci/shadow/w7p2-trap-registry.observations.jsonl` over five distinct trees.
"""

import pathlib
import subprocess

import pytest

from rediacc_ci.quality import trap_registry as mod

TWIN = pathlib.Path(".ci/scripts/quality/check-trap-registry.sh")


def _awk_program() -> str:
    """The `parse_corpus` awk body, extracted from the twin at run time.

    Extracted rather than copied so this test breaks LOUDLY when the twin's parser is edited, which is exactly when it should be re-read. Sliced between markers rather than by line number, because a line number churns when a paragraph moves above it.
    """
    text = TWIN.read_text(encoding="utf-8")
    start = text.index("parse_corpus() {")
    body_start = text.index("awk '", start) + len("awk '")
    end = text.index('\n    \' "$1"', body_start)
    return text[body_start:end]


CORPORA = [
    "## first\nTrap-Id: a-trap\nEnforced-By: JUDGMENT-ONLY\nResidue: nothing.\n\nbody\n",
    "## one\nTrap-Id: one\nEnforced-By: gate:check:x\nResidue:\n",  # empty Residue
    "## no trailer at all\n\nbody\n",
    "### not an entry\n",
    (
        "## r\nTrap-Id: r\nEnforced-By: JUDGMENT-ONLY\nResidue: x.\n\n"
        "```markdown\n## Not A Trap\n```\n"
    ),  # a fenced example
    "## r\nTrap-Id: r\n\n~~~\n## Also Not A Trap\n~~~\n",  # the tilde fence
    "## t\nTrap-Id: t\n\nResidue: this is body prose\n",  # trailer ends at the blank line
    "## a\nTrap-Id: a\nEnforced-By: x\nResidue: y\n## b\nTrap-Id: b\n",  # back to back
    "",  # empty corpus
    "no headings at all\n",
]


@pytest.mark.parametrize("corpus", CORPORA)
def test_parser_matches_the_twins_awk(tmp_path: pathlib.Path, corpus: str) -> None:
    target = tmp_path / "TRAPS.md"
    target.write_text(corpus, encoding="utf-8")
    proc = subprocess.run(
        ["awk", _awk_program(), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    expected = []
    for line in proc.stdout.split("\n"):
        if line == "":
            continue
        # US (0x1f), not TAB: tab is IFS whitespace in bash, so a run of two tabs COLLAPSES and an empty Residue silently reads as no Residue LINE.
        fields = line.split("\x1f")
        expected.append((int(fields[0]), fields[1], fields[2], fields[3], fields[4] == "1"))
    got = [
        (e.line, e.trap_id, e.enforced_by, e.residue, e.residue_seen)
        for e in mod.parse_corpus(corpus)
    ]
    assert got == expected


def test_the_floor_is_the_twins_number() -> None:
    """A divergence here is invisible to the differential.

    Every fixture in the shadow ledger sets `TRAP_FLOOR` explicitly, so the DEFAULT is the one value the two implementations can disagree about without any recorded row noticing. It moved 75 -> 76 -> 77 within one session on 2026-09-06, which is precisely why this assertion exists.
    """
    text = TWIN.read_text(encoding="utf-8")
    marker = 'TRAP_FLOOR="${TRAP_FLOOR:-'
    start = text.index(marker) + len(marker)
    twin_floor = int(text[start : text.index('}"', start)])
    assert twin_floor == mod.TRAP_FLOOR_DEFAULT


def test_the_summary_count_is_the_twins_boolean() -> None:
    """The twin prints a BOOLEAN where its message says "finding(s)".

    `scan` in bash ends with `[ "$errors" -eq 0 ]` on purpose (a shell return is mod 256), and `main` then prints that status as the count. The port carries the bug rather than the intent, because a port that changed it would be non-equivalent to the gate CI runs. This assertion is the record of that
    decision; delete it in the same change that fixes both files.
    """
    text = TWIN.read_text(encoding="utf-8")
    assert '[ "$errors" -eq 0 ]' in text
    assert '"$found trap-registry finding(s) in $TRAP_CORPUS' in text


def test_id_grammar() -> None:
    assert mod.ID_RE.match("mark-done-all-stale-is-a-bulk-verb")
    assert mod.ID_RE.match("abc")
    assert not mod.ID_RE.match("ab")
    assert not mod.ID_RE.match("Not_Kebab_Case")
    assert not mod.ID_RE.match("-abc")

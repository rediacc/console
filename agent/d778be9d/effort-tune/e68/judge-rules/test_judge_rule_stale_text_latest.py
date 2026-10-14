"""Proposed judge rule stale-text-latest (observation 2, e68, row eo-d33d0af0). Self-contained."""


def judged_text(notes):
    """notes: [original, update1, ...]. The text the judge reads: the latest note when it begins STALE TEXT ABOVE."""
    return (
        notes[-1]
        if len(notes) > 1 and notes[-1].lstrip().startswith("STALE TEXT ABOVE")
        else "\n".join(notes)
    )


def matches(reason, notes, ref):
    """True when the reason cites the item's original text as open work although the latest note retires it."""
    latest = notes[-1].lstrip()
    return latest.startswith("STALE TEXT ABOVE") and ref in reason and ref in notes[0]


def test_flags_stale_citation():
    notes = ["#97a7ced2 four low findings open", "STALE TEXT ABOVE: findings closed"]
    assert matches("#97a7ced2 (four low findings) can be fixed locally", notes, "#97a7ced2")
    assert judged_text(notes) == notes[-1]


def test_control_no_stale_note():
    notes = ["#97a7ced2 four low findings open", "progress"]
    assert not matches("#97a7ced2 (four low findings) can be fixed", notes, "#97a7ced2")

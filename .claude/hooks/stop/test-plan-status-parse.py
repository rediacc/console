#!/usr/bin/env python3
"""Controls for wl_checks.plan_records -- how a PLAN-*.md states its status.

Why this exists. The stop hook nags about plans whose status is draft,
executing, or UNKNOWN, and UNKNOWN is deliberately loud. So a parser that
cannot see a status a plan plainly states does not fail quietly: it sends a
session to rewrite accurate plans, sometimes plans belonging to OTHER sessions,
to satisfy a regex. That happened twice.

Round one is recorded in wl_checks.py's own comment: requiring a bare
`Status: word` line missed `**Status: DESIGNED, not started.**` and five of
twelve real plans read UNKNOWN. Round two, 2026-08-25: the anchored form still
required `Status:` to START a line, and two real plans state it mid-line --
`Owner: b7baf3ee - 2026-08-24 - status: BUILT` and
`Branch: 0815-1. Status: design only, no code written.`

Every control below is a PAIR. Asserting that the inline form parses proves
nothing on its own, because a parser returning the first word it ever sees
would pass it; the paired assertion is that a plan with NO status still reads
UNKNOWN, and that a real leading `Status:` line still wins over inline text.
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wl_checks as C


class Tally:
    """Counters as attributes, so `control` mutates state without `global`."""

    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print(f"FAIL  {label}: got {got!r}, wanted {want!r}", file=sys.stderr)


def status_of(body):
    """Parse one plan body through the REAL plan_records, not a re-derivation."""
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "agent").mkdir()
        (root / "agent" / "PLAN-fixture.md").write_text(body, encoding="utf-8")
        rows = C.plan_records(root)
        return rows[0][1] if rows else None


# 1. The two real-world inline shapes that read UNKNOWN before 2026-08-25.
control(
    "metadata line, dot-separated, lowercase key",
    status_of("# PLAN: a thing\nOwner: b7baf3ee - 2026-08-24 - status: BUILT\n"),
    "built",
)
control(
    "prose line, status after a sentence",
    status_of("# PLAN: a thing\nBranch: `0815-1`. Status: design only, no code written.\n"),
    "design",
)

# 1b. THE PAIR. A plan that states no status at all must still read UNKNOWN, or
#     the fallback above is just "match any word" wearing a regex.
control(
    "CONTROL: no status anywhere still reads UNKNOWN",
    status_of("# PLAN: a thing\nOwner: someone\nBranch: 0815-1\nSome prose.\n"),
    "UNKNOWN",
)

# 2. Precedence is unchanged: a real leading Status line wins over inline text
#    that appears EARLIER in the header.
control(
    "an anchored Status line wins over an earlier inline one",
    status_of("# PLAN: a thing\nNote: old status: superseded\nStatus: executing\n"),
    "executing",
)

# 2b. THE PAIR for precedence: with the anchored line removed, the inline one is
#     what remains, so the case above is really testing precedence and not just
#     "executing happens to be found".
control(
    "CONTROL: drop the anchored line and the inline one is used",
    status_of("# PLAN: a thing\nNote: old status: superseded\n"),
    "superseded",
)

# 3. The forms that already worked must keep working.
control("bare anchored line", status_of("# P\nStatus: draft\n"), "draft")
control("markdown-emphasised", status_of("# P\n**Status: DESIGNED, not started.**\n"), "designed")

# 4. A status below the header window is NOT the file's status. The window is
#    what keeps a mention deep in a plan's prose from being read as its state.
below = (
    "# P\n" + "\n".join(f"line {i}" for i in range(C.PLAN_HEADER_LINES + 3)) + "\nStatus: done\n"
)
control("CONTROL: a status past the header window does not count", status_of(below), "UNKNOWN")

if Tally.fails:
    print(f"FAIL: {Tally.fails} of {Tally.count} control(s) failed", file=sys.stderr)
    sys.exit(1)
print(f"{Tally.count} control(s) passed")

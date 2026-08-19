"""wl_roundlog: replace a pr-babysit round log's STATUS block WITHOUT eating the
history underneath it.

THE DEFECT THIS CLOSES, and it is a real one from 2026-08-19. The round log's
contract (`.claude/agents/pr-babysitter.md`, the round-log section) is three
parts in a fixed order:

    ## Wave header      immutable; superseded by a dated addendum, never rewritten
    ## STATUS           ONE screen, overwritten in place every round
    <history>           the appendix: every round's narrative, appended forever

Two of those three are load-bearing after a compaction: the wave header and
STATUS are what a warm-start reads first, and in delegated mode the lead's
watchdog judges the babysitter alive by STATUS's timestamp.

"Overwritten in place" is the trap. A session refreshing STATUS reaches for the
obvious splice -- find the old block, write everything before it, then the new
block -- and `text[:i] + new` is exactly that thought, one keystroke away from
correct and silently destructive: it replaces from the STATUS heading to
END OF FILE, taking the entire history appendix with it. That is not a
hypothetical. It happened on this wave, in a heartbeat tick whose whole purpose
was keeping the log current, and there was no backup of that file anywhere.

The fix is not "be careful". The splice is now a verb that CANNOT express the
truncation: it parses the document into (head, status, tail), replaces only the
middle, and REPORTS the tail's size back to the caller. A caller who reads
"appendix 4,812 bytes kept" learns the thing a silent success would hide.

WHY THE TOOL STAMPS THE TIME, and the caller does not. STATUS's timestamp is a
liveness signal that something else reads to decide whether this session is
wedged. A hand-typed stamp can be copied forward from the previous round without
anything noticing, which turns the one instrument watching for a stuck loop into
a copy of the loop's own optimism. `os.time` cannot be copy-pasted.

WHY IT REFUSES TO CREATE THE FILE. A round log with no wave header is missing
the half a warm-start needs most (intent, sanctioned reds, frozen surfaces,
baselines and the commands that measure them). Creating one on demand would let
a session write STATUS into an empty document and see success, having produced a
log that answers none of the questions it exists to answer.
"""

import re
import sys
import time
from pathlib import Path

# The STATUS heading, and any level-2 heading. Level 2 exactly: the block's own
# `### Round N fixes` subsections belong TO the block, and a boundary that
# stopped at `###` would leave them stranded above the replacement.
STATUS_RE = re.compile(r"^## STATUS\b.*$", re.MULTILINE)
H2_RE = re.compile(r"^## .*$", re.MULTILINE)
ROUND_RE = re.compile(r"^## STATUS\s*\(\s*round\s+(\d+)", re.MULTILINE | re.IGNORECASE)
WAVE_HEADER_RE = re.compile(r"^## Wave header\b", re.MULTILINE)

MIN_BODY_CHARS = 40


def stamp(now=None):
    """UTC, minute resolution, matching the round log's existing headings."""
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(now if now is not None else time.time()))


def roundlog_path(projects_dir, branch):
    """<projects>/reports/pr-babysit-<branch>.md, the path the skill already uses."""
    return Path(projects_dir) / "reports" / ("pr-babysit-%s.md" % branch)


def split(current):
    """(head, status, tail) -- the three parts, concatenating back to `current`.

    `status` is "" when the document has no STATUS block yet, and `head`/`tail`
    then describe where one belongs: directly after the wave-header section.

    The round trip is the property that matters, and `splice` asserts it rather
    than trusting this docstring.
    """
    m = STATUS_RE.search(current)
    if m is None:
        # No STATUS yet. It goes directly under the wave header, so the boundary
        # is the next level-2 heading after it; failing that, end of document.
        wave = WAVE_HEADER_RE.search(current)
        if wave is not None:
            nxt = H2_RE.search(current, wave.end())
            cut = nxt.start() if nxt else len(current)
        else:
            cut = len(current)
        return current[:cut], "", current[cut:]
    nxt = H2_RE.search(current, m.end())
    end = nxt.start() if nxt else len(current)
    return current[: m.start()], current[m.start() : end], current[end:]


def previous_round(status):
    """The round number in an existing STATUS heading, or 0 when there is none."""
    m = ROUND_RE.search(status or "")
    return int(m.group(1)) if m else 0


def shape(body):
    """('ok'|reason, detail). Refuses what the round log cannot use."""
    if not body.strip():
        return "empty", "nothing on stdin"
    if len(body.strip()) < MIN_BODY_CHARS:
        return "too-short", "%d chars, floor %d" % (len(body.strip()), MIN_BODY_CHARS)
    if STATUS_RE.search(body):
        # The tool writes the heading. A body carrying its own would produce two,
        # and the second would silently become the boundary for the NEXT splice.
        return "own-heading", "the body carries its own '## STATUS' heading"
    return "ok", ""


def splice(current, body, round_no=None, now=None):
    """Return (new_text, report). Replaces ONLY the STATUS block.

    `report` carries the byte counts of the parts that were KEPT, which is the
    point of the whole module: a caller that can see the appendix survived
    cannot mistake a truncation for a success.
    """
    head, status, tail = split(current)
    if head + status + tail != current:
        # Not an assert: `python -O` strips those, and this is the one invariant
        # the whole module exists to uphold. If the parse ever loses a byte, the
        # caller must hear about it instead of silently writing the loss to disk.
        raise RuntimeError(
            "roundlog split lost bytes: %d + %d + %d != %d"
            % (len(head), len(status), len(tail), len(current))
        )
    n = round_no if round_no is not None else previous_round(status) + 1
    block = "## STATUS (round %d, %s)\n\n%s" % (n, stamp(now), body.strip("\n"))
    # Exactly one blank line before the appendix, whatever the caller sent.
    new = head + block + ("\n\n" + tail.lstrip("\n") if tail.strip() else "\n")
    return new, {
        "round": n,
        "head_bytes": len(head),
        "replaced_bytes": len(status),
        "tail_bytes": len(tail),
        "had_status": bool(status),
        "wave_header": bool(WAVE_HEADER_RE.search(head)),
    }


def _selftest():
    """Controls for the splice. Run: wl_roundlog.py --selftest

    Every one of these is a property the 2026-08-19 truncation violated, or a
    way a naive fix for it would break something else.
    """
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        if not cond:
            ok = False
        print("  %s  %s%s" % ("PASS" if cond else "FAIL", label, "" if cond else "  <- " + detail))

    doc = (
        "# t\n\n## Wave header (immutable)\n\n### Intent\nwhy.\n\n"
        "## STATUS (round 7, 2026-01-01T00:00Z)\n\nold body\n\n"
        "### Round 7 fixes\nbelongs to the block.\n\n"
        "## Round 6\n\nAPPENDIX.\n"
    )
    new, rep = splice(doc, "fresh body")

    # THE defect: the appendix must survive.
    check("the history appendix survives", "APPENDIX." in new)
    check("the wave header survives", "## Wave header (immutable)" in new)
    check("the old STATUS body is gone", "old body" not in new)
    check(
        "a level-3 subsection goes WITH the block",
        "belongs to the block." not in new,
        "### sections under STATUS are part of it, not the appendix",
    )
    check("the round auto-increments", "## STATUS (round 8," in new, rep)
    check("exactly one STATUS heading", new.count("## STATUS") == 1)
    check("the tail is reported, not just preserved", rep["tail_bytes"] > 0, rep)

    # The naive splice, kept here as a CONTROL: this is what the verb replaced,
    # and it must still visibly destroy the appendix, or this test is measuring
    # nothing.
    i = doc.index("## STATUS")
    naive = doc[:i] + "## STATUS (round 8)\n\nfresh body\n"
    check(
        "control: the naive splice DOES destroy the appendix",
        "APPENDIX." not in naive,
        "if this fails the fixture no longer reproduces the bug",
    )

    # No STATUS block yet: it belongs directly under the wave header, and
    # whatever follows must still survive.
    doc2 = "# t\n\n## Wave header\n\nintent.\n\n## Round 1\n\nKEEP ME.\n"
    new2, rep2 = splice(doc2, "first status")
    check(
        "a first STATUS is inserted, not appended",
        new2.index("## STATUS") < new2.index("## Round 1"),
    )
    check("insertion still preserves what follows", "KEEP ME." in new2)
    check("first round is 1", rep2["round"] == 1, rep2)

    # Shape refusals.
    check("an empty body is refused", shape("")[0] == "empty")
    check("a thin body is refused", shape("tiny")[0] == "too-short")
    check(
        "a body carrying its own STATUS heading is refused",
        shape("## STATUS (round 9, x)\n\n" + "y" * 60)[0] == "own-heading",
        "two headings would make the second the next splice's boundary",
    )
    check("a real body is accepted", shape("x" * 60)[0] == "ok")

    # Round-trip: split must not lose bytes, whatever the shape.
    for name, d in (
        ("full", doc),
        ("no-status", doc2),
        ("empty", ""),
        ("header-only", "## Wave header\n"),
    ):
        h, s, t = split(d)
        check("split round-trips (%s)" % name, h + s + t == d)

    print("  %s" % ("all roundlog controls passed" if ok else "*** FAILURES ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else 0)

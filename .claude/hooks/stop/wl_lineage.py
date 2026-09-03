"""wl_lineage: is session B the same conversation as session A, continued after a compaction?

WHY THIS EXISTS. The store refuses to let one session tick another's items, and that
rule is right: two sessions sharing this worktree must not resolve each other's
tracking. But a compaction can give one continuous conversation a NEW session id, and
then the rule fires against the session's own work. On 2026-09-02 that left four
settled decisions open for a whole night, reported to the operator every stop as a
peer's, while the session reasoned about a peer that did not exist. The operator had
to say "I've never switched to another window."

WHAT IS AND IS NOT EVIDENCE. Everything here is written by the harness into the
transcripts under ~/.claude/projects/<slug>/, and nothing here is a heuristic:

  E1  the predecessor's transcript ends with {"type":"continued-in", ...,
      "continuedInSessionId": <me>}. Explicit and directional. NOT available
      immediately: in the real case it was written 2h21m AFTER the compaction, which
      is why E2 exists.
  E2  my transcript's first conversational record is a compact_boundary with
      parentUuid null, and its uuid AND logicalParentUuid both appear in the
      candidate's transcript. One event, dual-written, naming both sessions.
  E3  MANDATORY, and it is the concurrency refutation. The two transcripts must share
      at least one conversational record uuid. Two genuinely concurrent sessions share
      ZERO -- there is no mechanism by which one conversation's message uuid lands in
      another's file. E3 is checked even when E1 fires, because E1 is a single line
      and a single line is the easiest thing to forge.

THERE IS NO HEURISTIC RUNG, and that is the load-bearing decision. The obvious
fallback is "same cwd + same branch + time-adjacency". Measured on this machine, four
sessions all carry cwd=/home/developer/console and gitBranch=main with overlapping
times: concurrent sessions in one worktree on one branch are ROUTINE here. So that
heuristic's false-positive rate is highest on exactly the population it would judge,
and its failure mode is one session silently resolving another's tracking -- the thing
the ownership rule exists to prevent. When E1/E2 find nothing the answer is "cannot
establish", and the operator's WORKLIST_SESSION_ID override remains the way a human
declares it, recorded as a human's declaration.

Bounded reads only: a tail window per candidate and two mmap scans. Measured on the
live directory (52 transcripts, 192 MB): 19 ms for the E1 sweep, 7 ms for E2.
"""

from __future__ import annotations

import json
import mmap
import os
import pathlib

# The preamble records a transcript opens with; the first record NOT of these types is
# the one that says how the session began.
PREAMBLE = {
    "mode",
    "bridge-session",
    "ai-title",
    "agent-name",
    "permission-mode",
    "atis-latch",
    "file-history-snapshot",
    "summary",
}
HEAD_BYTES = 128 * 1024
TAIL_BYTES = 256 * 1024


def _head_records(path, limit=HEAD_BYTES):
    try:
        with open(path, "rb") as fh:
            blob = fh.read(limit)
    except OSError:
        return []
    out = []
    for line in blob.split(b"\n"):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a truncated final line in the window is expected
    return out


def _tail_text(path, limit=TAIL_BYTES):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - limit))
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _contains(path, needles):
    """Does the file contain every needle? mmap so a 16 MB transcript is not read in."""
    try:
        size = os.path.getsize(path)
        if size == 0:
            return False
        with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            return all(mm.find(n.encode()) != -1 for n in needles if n)
    except (OSError, ValueError):
        return False


def _record_uuids(records):
    return {r.get("uuid") for r in records if isinstance(r, dict) and r.get("uuid")}


def boundary_of(transcript):
    """My compact_boundary head record, or None when I did not arrive by compaction.

    GATE 1, and it is the cheap one: a session that did not arrive by a compaction can
    never adopt anything, so this is asked before any candidate is opened.
    """
    for rec in _head_records(transcript):
        if not isinstance(rec, dict):
            continue
        if rec.get("type") in PREAMBLE:
            continue
        if (
            rec.get("type") == "system"
            and rec.get("subtype") == "compact_boundary"
            and rec.get("parentUuid") is None
        ):
            return rec
        return None  # the first conversational record was something else
    return None


def resolve(session_id, transcript, projects, claimed_prev=None):
    """(prev_full_id, evidence) when continuity is PROVEN, else (None, reason)."""
    if not (session_id and transcript and projects):
        return None, "no session id, transcript or projects directory"

    boundary = boundary_of(transcript)
    if boundary is None:
        return (
            None,
            "not a compaction successor: this transcript does not open with a compact_boundary",
        )

    me_uuid = boundary.get("uuid")
    logical = boundary.get("logicalParentUuid")
    mine = _record_uuids(_head_records(transcript))

    try:
        candidates = [
            p
            for p in pathlib.Path(projects).glob("*.jsonl")
            if p.name != pathlib.Path(transcript).name
        ]
    except OSError as exc:
        return None, "cannot list %s (%s)" % (projects, exc)
    if claimed_prev:
        candidates = [p for p in candidates if p.name.startswith(claimed_prev)]
    if not candidates:
        return None, "no candidate transcript%s" % (
            " matching %s" % claimed_prev if claimed_prev else ""
        )
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    hits = []
    for cand in candidates:
        via = None
        if session_id in _tail_text(cand) and '"continued-in"' in _tail_text(cand):
            via = "continued-in"
        elif me_uuid and logical and _contains(cand, [me_uuid, logical]):
            via = "compact-boundary"
        if not via:
            continue

        # E3, and it is checked even when E1 fired.
        shared = mine & _record_uuids(_head_records(cand, HEAD_BYTES * 8))
        if not shared and not (me_uuid and _contains(cand, [me_uuid])):
            return None, (
                "%s names me but shares no conversational record: that is not one "
                "conversation, and a single line is the easiest thing to forge" % cand.stem[:8]
            )
        hits.append((cand, via, len(shared)))

    if not hits:
        return None, "no candidate carries a continued-in line or my boundary uuid"
    if len(hits) > 1:
        return None, "ambiguous: %s all claim me; refusing rather than guessing" % ", ".join(
            h[0].stem[:8] for h in hits
        )

    cand, via, shared = hits[0]
    return cand.stem, {
        "via": via,
        "ev_id": me_uuid,
        "shared": shared,
        "prev_tx": cand.name,
        "next_tx": pathlib.Path(transcript).name,
    }

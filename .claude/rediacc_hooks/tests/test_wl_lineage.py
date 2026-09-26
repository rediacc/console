"""Ported from `.claude/hooks/stop/worklist-cases/24-lineage.sh`.

A compaction must not cost a session its own items.

THE INCIDENT. A compaction can hand one continuous conversation a NEW session id. The ownership rule then refuses to let it resolve items its earlier self opened, correct by the letter of the rule and catastrophic in effect: on 2026-09-02 four settled decisions sat open all night, reported to the operator every stop as a peer's, while the session reasoned about a peer that did not
exist. The operator had to say that no other window had ever been switched to.

WHAT IS TESTED is that the fix is an EVIDENCE GATE and not a new way to take someone else's work. `plant_chain` writes the records a real compaction leaves behind; `plant_concurrent` writes two sessions alike in every way a heuristic would check (same cwd, same branch, overlapping times) sharing no conversational record. The second is the one that matters: measured on this machine,
four live sessions all carried the same cwd and branch with overlapping times, so "same cwd plus time-adjacent" is the WRONG discriminator on exactly the population it would judge.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_hooks.tests.wlfix import wl  # noqa: F401

if TYPE_CHECKING:
    import pathlib

BOUNDARY_UUID = "bde8bb05-0000-0000-0000-000000000001"
LOGICAL_UUID = "bde8bb05-0000-0000-0000-000000000002"


@pytest.fixture
def lineage(wl):  # noqa: F811
    """The transcript corpus `WORKLIST_PROJECTS_DIR` points at.

    UNDER THE SANDBOX ROOT, as the bash put it under `$BASE/lineage`, so the corpus is torn down with the rest of the fixture world rather than outliving it.
    """
    projects = wl.base / "lineage" / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    return projects


def plant_chain(projects: pathlib.Path, nxt: str, prev: str, shared: str) -> None:
    """The records a real compaction leaves behind.

    The successor: gate 1 requires the head record to be a `compact_boundary` with a null parentUuid, so this shape is what makes a session eligible to adopt at all. The predecessor: the same shared record (E3), the boundary pair (E2), and the continued-in tail the harness writes when it finally closes the file (E1).
    """
    (projects / ("%s.jsonl" % nxt)).write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in [
                {"type": "mode", "mode": "default"},
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "parentUuid": None,
                    "uuid": BOUNDARY_UUID,
                    "logicalParentUuid": LOGICAL_UUID,
                },
                {
                    "type": "user",
                    "uuid": shared,
                    "message": {"role": "user", "content": "carried over"},
                },
            ]
        ),
        encoding="utf-8",
    )
    (projects / ("%s.jsonl" % prev)).write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in [
                {
                    "type": "user",
                    "uuid": shared,
                    "message": {"role": "user", "content": "carried over"},
                },
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "uuid": BOUNDARY_UUID,
                    "logicalParentUuid": LOGICAL_UUID,
                },
                {"type": "continued-in", "continuedInSessionId": nxt},
            ]
        ),
        encoding="utf-8",
    )


def plant_concurrent(projects: pathlib.Path, first: str, second: str) -> None:
    """Real peers: everything alike, uuids disjoint."""
    for sid, uuid in (
        (first, "aaaa1111-0000-0000-0000-00000000000a"),
        (second, "bbbb2222-0000-0000-0000-00000000000b"),
    ):
        (projects / ("%s.jsonl" % sid)).write_text(
            json.dumps(
                {
                    "type": "user",
                    "uuid": uuid,
                    "cwd": "/home/developer/console",
                    "gitBranch": "main",
                    "timestamp": "2026-09-03T04:00:00Z",
                    "message": {"role": "user", "content": "hello"},
                }
            )
            + "\n",
            encoding="utf-8",
        )


def linrun(fix, projects: pathlib.Path, sid: str, *argv: str):
    """One CLI call as `sid`, with its own stdin closed.

    Closing stdin is not decoration. The bash suite was driven by a harness that passed no stdin redirect, so it inherited a pipe nobody ever closes: a verb that reads stdin then blocks forever, and the symptom is indistinguishable from a slow suite. Every case helper must close its own stdin rather than trust the caller's.
    """
    env = dict(fix.env)
    env.update(
        {
            "CLAUDE_PROJECT_DIR": str(fix.proj),
            "WORKLIST_JUDGE": "off",
            "WORKLIST_PUBLISH_ROOT": str(fix.base),
            "WORKLIST_PROJECTS_DIR": str(projects),
            "CLAUDE_CODE_SESSION_ID": sid,
            "WORKLIST_SESSION_ID": sid,
        }
    )
    proc = subprocess.run(
        [sys.executable, str(fix.hook), *argv],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


NEXT = "cafe9911-1111-2222-3333-444444444444"
PREV = "beef7722-5555-6666-7777-888888888888"
SHARED = "11111111-2222-3333-4444-555555555555"


def test_24_an_ancestors_items_are_invisible_then_adopted_then_survive_compaction(wl, lineage):  # noqa: F811
    """BEFORE, FIRE and COMPACT in one sequence, because each arm depends on the one before it: the BEFORE half is what stops every later assertion passing on an empty store."""
    plant_chain(lineage, NEXT, PREV, SHARED)
    for label in ("lin-a", "lin-b", "lin-c"):
        linrun(wl, lineage, PREV, "--add", "beef7722", label)
    _, listing = linrun(wl, lineage, PREV, "--list", "--open", "beef7722")
    tickme = ""
    for line in listing.splitlines():
        if "lin-a" in line:
            found = re.search(r"#([0-9a-f]{8})", line)
            if found:
                tickme = found.group(1)
                break
    assert tickme, "the fixture planted no tickable item: %s" % listing[:300]

    _, out = linrun(wl, lineage, NEXT, "--list", "--open", "cafe9911")
    assert "lin-a" not in out, (
        "BEFORE: the ancestor's items were visible with no edge, so this case proves nothing"
    )
    rc, out = linrun(wl, lineage, NEXT, "--tick", "cafe9911", tickme, "https://ci.invalid/x")
    assert rc != 0, "BEFORE: ticked an ancestor's item with no edge (rc=%d): %s" % (rc, out[:200])
    assert "owned by" in out, "BEFORE: ticked an ancestor's item with no edge (rc=%d): %s" % (
        rc,
        out[:200],
    )

    rc, out = linrun(wl, lineage, NEXT, "--adopt", "cafe9911", "beef7722")
    assert rc == 0, "FIRE: refused a genuine compaction chain (rc=%d): %s" % (
        rc,
        out[:200],
    )
    assert "adopted" in out, "FIRE: refused a genuine compaction chain (rc=%d): %s" % (
        rc,
        out[:200],
    )
    _, out = linrun(wl, lineage, NEXT, "--list", "--open", "cafe9911")
    assert "lin-a" in out, "FIRE: adopted, but the items are still invisible: %s" % out[:200]
    rc, out = linrun(wl, lineage, NEXT, "--tick", "cafe9911", tickme, "https://ci.invalid/run/24")
    assert rc == 0, "FIRE: still refused after adoption (rc=%d): %s" % (
        rc,
        out[:200],
    )
    assert "ticked" in out, "FIRE: still refused after adoption (rc=%d): %s" % (
        rc,
        out[:200],
    )

    linrun(wl, lineage, NEXT, "--compact")
    _, out = linrun(wl, lineage, NEXT, "--list", "--open", "cafe9911")
    assert "lin-b" in out, (
        "COMPACT: --compact ate the edge, so adoptions revert to a peer's: %s" % out[:200]
    )


def test_24_two_concurrent_sessions_are_not_adoptable_however_alike(wl, lineage):  # noqa: F811
    """THE REFUSAL, and this is the one that matters."""
    first = "dddd3311-1111-1111-1111-111111111111"
    second = "eeee4422-2222-2222-2222-222222222222"
    plant_concurrent(lineage, first, second)
    rc, out = linrun(wl, lineage, first, "--adopt", "dddd3311", "eeee4422")
    lowered = out.lower()
    assert rc != 0, "adopted a peer on same-cwd and same-branch resemblance (rc=%d): %s" % (
        rc,
        out[:200],
    )
    assert "cannot prove" in lowered or "refused" in lowered, (
        "adopted a peer on same-cwd and same-branch resemblance (rc=%d): %s" % (rc, out[:200])
    )
    # A CONTROL ON THE CONTROL: the SAME pair, once real evidence exists.
    plant_chain(lineage, first, second, "99999999-8888-7777-6666-555555555555")
    rc, out = linrun(wl, lineage, first, "--adopt", "dddd3311", "eeee4422")
    assert rc == 0, (
        "CONTROL: refused even with a planted chain, so the gate is a blanket no: %s" % out[:200]
    )


def test_24_e3_alone_cannot_be_defeated(wl, lineage):  # noqa: F811
    """KEEP continued-in (E1, the easiest line to forge) and STRIP every shared record and the boundary. If this adopts, one hand-written line takes another session's work."""
    successor = "ffff5533-1111-1111-1111-111111111111"
    predecessor = "ffff6644-2222-2222-2222-222222222222"
    plant_chain(lineage, successor, predecessor, "77777777-6666-5555-4444-333333333333")
    (lineage / ("%s.jsonl" % predecessor)).write_text(
        json.dumps({"type": "continued-in", "continuedInSessionId": successor}) + "\n",
        encoding="utf-8",
    )
    rc, out = linrun(wl, lineage, successor, "--adopt", "ffff5533", "ffff6644")
    assert rc != 0, "one forged line was enough to adopt: %s" % out[:200]


def test_24_additive_a_session_with_no_lineage_behaves_exactly_as_before(wl, lineage):  # noqa: F811
    solo = "0a0a0a0a-1111-1111-1111-111111111111"
    (lineage / ("%s.jsonl" % solo)).write_text(
        json.dumps(
            {
                "type": "user",
                "uuid": "0a0a0a0a-0000-0000-0000-000000000001",
                "message": {"role": "user", "content": "solo"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rc, out = linrun(wl, lineage, solo, "--add", "0a0a0a0a", "lin-solo")
    assert rc == 0, "lineage broke the no-edge path (rc=%d): %s" % (
        rc,
        out[:200],
    )
    assert "added #" in out, "lineage broke the no-edge path (rc=%d): %s" % (
        rc,
        out[:200],
    )

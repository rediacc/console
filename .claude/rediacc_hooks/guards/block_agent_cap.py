"""Refuse a writer-class Agent spawn while WRITER_CAP writers are already live.

THE ASK (operator, 2026-09-24): a hard limit of 4 parallel writers, with no escape hatches. Plan: agent/plans/PLAN-parallel-writer-roster.md, "Enforcing the cap".

TWO LAYERS, AND THIS IS THE PRIMARY. The Stop hook's `roster-cap` block is authoritative, because only a Stop event carries the harness's running list; but by the time a Stop sees a fifth writer it has already run and edited files for a whole turn, and the only remedy left is to stop it and waste that work. So the spawn itself is refused here, before the writer exists.

WHAT IS COUNTED. `wl_roster.live_writers_estimate`: the running subagents of the last Stop event, plus every agent spawned since that event (its meta is newer than the event), minus any whose transcript is proven finished, keeping only the types that write. The constants are imported from `wl_roster`, so the two layers cannot disagree about the number or about which types are readers.

WHAT IS NEVER REFUSED. A Plan or Explore spawn, or any custom type whose `tools:` line names no edit tool: read-only work does not count toward the cap, and routing it there is the remedy this message prints. A payload that is not an Agent or Task call.

FAILS OPEN WHEN IT CANNOT COUNT, and says so on stderr. That is not an escape hatch, because the Stop hook recounts from the authoritative event on the next stop and blocks there; a guard that refused every spawn whenever its estimate was blind would be a bootstrap deadlock instead.

ITS EVIDENCE. `TWIN = None` (never bash), so the dedicated suite `.claude/rediacc_hooks/guards/test-block_agent_cap.py` drives this guard through the dispatcher in both directions, and `.claude/rediacc_hooks/tests/test_wl_roster.py` drives the Stop half.

NO ENVIRONMENT READ. This file is a sealed module in `.ci/policy/worklist-env-registry.json`: an environment read added here is CI red. The payload's own `cwd` and `session_id` are what locate the session.
"""

import pathlib
import sys

from rediacc_hooks import hookio

CHAIN = "pre-agent"
TWIN = None
ORDER = 3

# The planted defect for the differential: a guard that stops exempting read-only spawns tries to count them, and speaks where it used to stay silent.
DEFECT = ("if kind in read_only:", "if False:")

# The payload shapes the differential feeds this guard beyond the cross-fed corpus. A session id that resolves to no session directory is the "cannot count" branch; the Explore spawn is the read-only exemption.
EDGE_CASES = [
    (
        "writer-spawn-uncountable",
        {
            "tool_name": "Agent",
            "session_id": "zz-no-such-session",
            "cwd": "/nonexistent-agent-cap-fixture",
            "tool_input": {"subagent_type": "general-purpose", "description": "x"},
        },
    ),
    (
        "reader-spawn",
        {
            "tool_name": "Agent",
            "session_id": "zz-no-such-session",
            "cwd": "/nonexistent-agent-cap-fixture",
            "tool_input": {"subagent_type": "Explore", "description": "x"},
        },
    ),
]

STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"

REFUSED = (
    "BLOCKED: %d writer agent(s) are already live and the cap is %d.\n"
    "\n"
    "A %r spawn is a writer, so this would be writer number %d. The live writers:\n"
    "%s\n"
    "\n"
    "Do one of these instead:\n"
    "  - wait for a writer to finish, or stop one (TaskStop <id>) and release or re-lease its items\n"
    "  - dispatch read-only work as subagent_type Plan or Explore, which the cap does not count\n"
    "  - do the work inline in this session\n"
    "\n"
    "The count is the last Stop event's running writers plus every agent spawned since, minus\n"
    "any whose transcript is proven finished; it refreshes on the next stop. The Stop hook's\n"
    "roster-cap check enforces the same number from the authoritative event.\n"
)

UNCOUNTABLE = (
    "agent-cap: could not count the live writers for session %r (no session directory under the\n"
    "projects store), so this %r spawn was ALLOWED unchecked. The Stop hook's roster-cap check\n"
    "recounts from the harness's own event on the next stop and blocks there if the cap is exceeded.\n"
)


def run(event):
    doc = event.doc
    if not isinstance(doc, dict) or doc.get("tool_name") not in ("Agent", "Task"):
        return hookio.ALLOW
    tool_input = doc.get("tool_input") if isinstance(doc.get("tool_input"), dict) else {}
    kind = str(tool_input.get("subagent_type") or "general-purpose")
    cwd = str(doc.get("cwd") or event.cwd)
    session_id = str(doc.get("session_id") or "")
    if str(STOP_DIR) not in sys.path:
        sys.path.insert(0, str(STOP_DIR))
    import wl_core as C  # noqa: PLC0415 -- loaded only for an Agent call, never for the other chains
    import wl_roster  # noqa: PLC0415

    read_only = wl_roster.read_only_types(C.project_root(C.project_start({"cwd": cwd})))
    if kind in read_only:
        return hookio.ALLOW
    rows = wl_roster.live_writers_estimate(cwd, session_id)
    if rows is None:
        event.warn_raw(UNCOUNTABLE % (session_id, kind))
        return hookio.ALLOW
    if len(rows) >= wl_roster.WRITER_CAP:
        listed = "\n".join("  %s (%s) %r" % (r["id"], r["type"], r["desc"]) for r in rows)
        event.warn_raw(REFUSED % (len(rows), wl_roster.WRITER_CAP, kind, len(rows) + 1, listed))
        return hookio.DENY
    return hookio.ALLOW

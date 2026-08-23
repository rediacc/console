#!/usr/bin/env python3
"""Controls for wl_liveness.teammate_state -- the subagent idle/liveness verdict.

Every control here is a RED/GREEN PAIR or it is not a control. The one that
matters most is Control 1, the mutation pair: an idle fixture asserting `idle`
proves nothing on its own, because a function that returned "idle"
unconditionally would pass it. Flipping the single `stop_reason` field to
`tool_use` and asserting the claim STOPS is what makes the first assertion mean
something. See agent/PLAN-subagent-idle-detection.md.
"""

import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wl_liveness as L

TMP = pathlib.Path(tempfile.mkdtemp())
SUB = TMP / "sess" / "subagents"
SUB.mkdir(parents=True)

IDLE = {
    "type": "assistant",
    "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]},
}
TOOL = {
    "type": "assistant",
    "message": {"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "Bash"}]},
}
STREAM = {
    "type": "assistant",
    "message": {"stop_reason": None, "content": [{"type": "text", "text": "..."}]},
}
# An ended turn whose content still carries a tool_use block. stop_reason alone
# would call this idle; the content check is what refuses.
MIXED = {
    "type": "assistant",
    "message": {"stop_reason": "end_turn", "content": [{"type": "tool_use", "name": "Bash"}]},
}

# A counter OBJECT rather than two module globals. `global` in a test harness
# is the shape that lets a helper silently stop counting -- rebind the name in
# one branch and the tally goes quiet while every case still prints PASS.
TALLY = {"ok": 0, "fail": 0}


def check(label, got, want):
    if got == want:
        TALLY["ok"] += 1
        print("  PASS: %s" % label)
    else:
        TALLY["fail"] += 1
        print("  FAIL: %s  got=%r want=%r" % (label, got, want))


def make(name, last, age_min=0.0):
    meta = SUB / ("agent-a%s.meta.json" % name)
    meta.write_text(json.dumps({"name": name, "taskKind": "in_process_teammate"}))
    j = meta.with_name(meta.name[: -len(".meta.json")] + ".jsonl")
    j.write_text(json.dumps({"type": "user"}) + "\n" + json.dumps(last) + "\n")
    t = time.time() - age_min * 60
    os.utime(j, (t, t))
    return j


def run():
    orig_meta, orig_edge = L._teammate_meta, L.idle_edge
    L._teammate_meta = lambda _cwd, _sid, name: (
        (SUB / ("agent-a%s.jsonl" % name), name)
        if (SUB / ("agent-a%s.jsonl" % name)).exists()
        else (None, None)
    )
    L.idle_edge = lambda _cwd, _sid, _name: None
    try:
        print("== 1. the mutation pair: the assertion that makes the others mean something ==")
        make("m1", IDLE)
        check("an ended turn classifies idle", L.teammate_state("/x", "sess", "m1")[0], "idle")
        make("m1", TOOL)
        check(
            "flipping stop_reason to tool_use STOPS the idle claim",
            L.teammate_state("/x", "sess", "m1")[0],
            "working",
        )
        make("m1", STREAM)
        check(
            "stop_reason None (streaming) is working, never idle",
            L.teammate_state("/x", "sess", "m1")[0],
            "working",
        )
        make("m1", MIXED)
        check(
            "end_turn carrying a tool_use block is NOT idle",
            L.teammate_state("/x", "sess", "m1")[0],
            "working",
        )

        print("== 2. a stall is SUSPECT, never dead ==")
        make("s1", TOOL, age_min=60)
        v = L.teammate_state("/x", "sess", "s1")[0]
        check("mid-turn + 60m quiet is stalled", v, "stalled")
        check("the verdict word is neither dead nor gone", ("dead" in v or "gone" in v), False)

        print("== 3. unverifiable is never accused ==")
        check(
            "no such worker -> unverifiable",
            L.teammate_state("/x", "sess", "no-such-agent-name")[0],
            "unverifiable",
        )

        print("== 4. a resumed teammate flips back: the false-death regression guard ==")
        j = make("r1", IDLE)
        check("idle first", L.teammate_state("/x", "sess", "r1")[0], "idle")
        with j.open("a") as fh:
            fh.write(json.dumps(TOOL) + "\n")
        os.utime(j, None)
        check(
            "appending a tool_use record flips back to working",
            L.teammate_state("/x", "sess", "r1")[0],
            "working",
        )

        print("== 5. blocking_rung_due learns the idle key (the poll/latch deadlock guard) ==")
        check(
            "the idle rung is due once",
            L.blocking_rung_due({"ladder": {}}, "k", 200, "s1", idle=True),
            True,
        )
        latched = {"ladder": {"k": {"idle": "s1"}}}
        check(
            "it latches (fire_once)", L.blocking_rung_due(latched, "k", 200, "s1", idle=True), False
        )
        check(
            "a moved stamp re-arms it",
            L.blocking_rung_due(latched, "k", 200, "s2", idle=True),
            True,
        )
        check("WORKER_IDLE_BLOCK_MIN is the operator's 15", L.WORKER_IDLE_BLOCK_MIN, 15)

        print("== 6. the sidecar SHARPENS the number and never manufactures the verdict ==")
        L.idle_edge = lambda _cwd, _sid, _name: time.time() - 3600
        make("g1", TOOL)
        check(
            "sidecar entry + mid-turn transcript -> working, NOT idle",
            L.teammate_state("/x", "sess", "g1")[0],
            "working",
        )
        make("g2", IDLE, age_min=1)
        v, q, _, _ = L.teammate_state("/x", "sess", "g2")
        check("idle + sidecar -> idle", v, "idle")
        check("quiet_min comes from the 60m edge, not the 1m mtime", round(q), 60)
        L.idle_edge = lambda _cwd, _sid, _name: None
        make("g3", IDLE, age_min=7)
        v, q, _, _ = L.teammate_state("/x", "sess", "g3")
        check(
            "with NO sidecar it still works, quiet from the transcript", (v, round(q)), ("idle", 7)
        )

        print("== 7. the edge resolves a tail the transcript CANNOT read ==")
        # Found by live probe, not by reasoning: a finished agent's last record
        # was `assistant / stop_reason: None / ['text']` -- a streaming partial,
        # which classifies as working. Without the edge it reads as working
        # forever, which is this item's own blindness in a safer-looking hat.
        j = make("e1", STREAM, age_min=5)
        L.idle_edge = lambda _cwd, _sid, _name: None
        check(
            "a streaming tail with NO edge stays working (the safe default)",
            L.teammate_state("/x", "sess", "e1")[0],
            "working",
        )
        edge_at = j.stat().st_mtime + 0.1
        L.idle_edge = lambda _cwd, _sid, _name: edge_at
        check(
            "the SAME tail plus an edge after it resolves to idle",
            L.teammate_state("/x", "sess", "e1")[0],
            "idle",
        )
        # THE GUARD THAT MAKES TRUSTING THE EDGE SAFE. A teammate that resumes
        # writes, so its mtime moves past the edge. Without this arm the two
        # assertions above would pass just as well for code that ignored the
        # resume entirely -- which is the false-death this design refuses.
        L.idle_edge = lambda _cwd, _sid, _name: edge_at - 600
        check(
            "an edge OLDER than the last write means it resumed -> working",
            L.teammate_state("/x", "sess", "e1")[0],
            "working",
        )
    finally:
        L._teammate_meta, L.idle_edge = orig_meta, orig_edge
    print("\npassed=%d failed=%d" % (TALLY["ok"], TALLY["fail"]))
    return 1 if TALLY["fail"] else 0


if __name__ == "__main__":
    sys.exit(run())

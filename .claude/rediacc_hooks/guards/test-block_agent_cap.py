#!/usr/bin/env python3
"""Control harness for block_agent_cap, the PreToolUse half of the parallel-writer cap.

BOTH DIRECTIONS. A guard that refused every spawn would pass the refusal cases and a guard that refused none would pass the allow cases, so each refusal below has an allow twin differing by one planted fact: one writer fewer, a reader instead of a writer, a transcript that ended its turn.

LOAD-BEARING, NOT OPTIONAL. The guard declares `OWN_SUITE = True` (it was never bash, so it has no golden either), so `test_guards_differential.py` requires this file beside it, and `test_hooks_delegates.py` discovers and runs it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER against a real fixture on disk: a projects store with subagent metas and transcripts (`CLAUDE_CONFIG_DIR`), a project root (`CLAUDE_PROJECT_DIR`) and a worklist directory (`TMPDIR`) where the last Stop event is written. The fixture lives in ONE pid-stamped directory that is removed on exit.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
SID = "cafe0000-1111-2222-3333-444444444444"
BASE = pathlib.Path(tempfile.gettempdir()) / ("agentcap-%d" % os.getpid())


def munged(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def world(writers=0, readers=0, finished=0, lastevent=None, custom_ro=False, age_min=0):
    """A fresh fixture: `writers` live general-purpose agents, `readers` live Explore agents, `finished` general-purpose agents whose transcript ended its turn."""
    if BASE.exists():
        shutil.rmtree(BASE)
    proj = BASE / "proj"
    (proj / ".git").mkdir(parents=True)
    (BASE / "tmp").mkdir()
    sub = BASE / "claude" / "projects" / munged(proj.resolve()) / SID / "subagents"
    sub.mkdir(parents=True)
    if custom_ro:
        (proj / ".claude" / "agents").mkdir(parents=True)
        (proj / ".claude" / "agents" / "looker.md").write_text(
            "---\nname: looker\ndescription: reads\ntools: Bash, Read, Grep\n---\nbody\n",
            encoding="utf-8",
        )
    working = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}}
    done = {
        "type": "assistant",
        "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]},
    }
    rows = []
    n = 0
    for kind, count, rec in (
        ("general-purpose", writers, working),
        ("Explore", readers, working),
        ("general-purpose", finished, done),
    ):
        for _ in range(count):
            n += 1
            aid = "a%016d" % n
            (sub / ("agent-%s.meta.json" % aid)).write_text(
                json.dumps({"agentType": kind, "description": "fixture %d" % n, "spawnDepth": 1}),
                encoding="utf-8",
            )
            tx = sub / ("agent-%s.jsonl" % aid)
            tx.write_text(json.dumps(rec) + "\n", encoding="utf-8")
            old = time.time() - age_min * 60 - 10
            os.utime(tx, (old, old))
            os.utime(sub / ("agent-%s.meta.json" % aid), (old, old))
            rows.append({"id": aid, "type": "subagent", "status": "running", "agent_type": kind})
    if lastevent:
        slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(proj.resolve())).lstrip("_")
        side = BASE / "tmp" / "claude-worklist" / ("%s.lastevent-%s.json" % (slug, SID[:8]))
        side.parent.mkdir(parents=True, exist_ok=True)
        side.write_text(json.dumps({"session_id": SID, "background_tasks": rows}), encoding="utf-8")
    return proj


def spawn(proj, kind, session=SID, tool="Agent"):
    env = {k: v for k, v in os.environ.items() if not k.startswith("WORKLIST_")}
    env.update(
        {
            "CLAUDE_CONFIG_DIR": str(BASE / "claude"),
            "CLAUDE_PROJECT_DIR": str(proj),
            "TMPDIR": str(BASE / "tmp"),
        }
    )
    payload = {
        "tool_name": tool,
        "session_id": session,
        "cwd": str(proj),
        "tool_input": {"subagent_type": kind, "description": "probe", "prompt": "p"},
    }
    proc = subprocess.run(
        [sys.executable, DISPATCH, "block_agent_cap"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stderr


# (name, world kwargs, spawn kwargs, want_rc, stderr needle or "" for silence)
CASES = [
    ("a fifth writer is refused", {"writers": 4}, {"kind": "general-purpose"}, 2, "cap is 4"),
    (
        "the refusal names every live writer",
        {"writers": 4},
        {"kind": "gate-author"},
        2,
        "a0000000000000004",
    ),
    ("a fourth writer is allowed", {"writers": 3}, {"kind": "general-purpose"}, 0, ""),
    ("an Explore spawn at the cap is allowed", {"writers": 4}, {"kind": "Explore"}, 0, ""),
    ("a Plan spawn at the cap is allowed", {"writers": 5}, {"kind": "Plan"}, 0, ""),
    (
        "readers do not count toward the cap",
        {"writers": 3, "readers": 3},
        {"kind": "general-purpose"},
        0,
        "",
    ),
    (
        "a finished writer does not count",
        {"writers": 3, "finished": 2},
        {"kind": "general-purpose"},
        0,
        "",
    ),
    (
        "the last Stop event's writers count even when their transcripts are old",
        {"writers": 4, "lastevent": True, "age_min": 90},
        {"kind": "general-purpose"},
        2,
        "cap is 4",
    ),
    (
        "without an event, old transcripts are not counted as live",
        {"writers": 4, "age_min": 90},
        {"kind": "general-purpose"},
        0,
        "",
    ),
    (
        "a custom agent with no edit tool is a reader",
        {"writers": 4, "custom_ro": True},
        {"kind": "looker"},
        0,
        "",
    ),
    (
        "an uncountable session is allowed, and says so",
        {"writers": 4},
        {"kind": "general-purpose", "session": "zzzz9999"},
        0,
        "could not count",
    ),
    (
        "a non-Agent payload is ignored",
        {"writers": 9},
        {"kind": "general-purpose", "tool": "Bash"},
        0,
        "",
    ),
    (
        "the Task tool name is guarded too",
        {"writers": 4},
        {"kind": "general-purpose", "tool": "Task"},
        2,
        "cap is 4",
    ),
]


def main():
    fails = 0
    refused = 0
    try:
        for name, wkw, skw, want_rc, needle in CASES:
            proj = world(**wkw)
            rc, err = spawn(proj, **skw)
            refused += rc == 2
            ok = rc == want_rc and ((needle in err) if needle else (err == ""))
            fails += not ok
            print("%-70s want=%d got=%d %s" % (name, want_rc, rc, "ok" if ok else "FAIL"))
            if not ok:
                print("    stderr: %r" % err[:300])
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
    print("block_agent_cap: %d case(s), %d refused, %d failure(s)" % (len(CASES), refused, fails))
    if refused == 0:
        print("VACUOUS: not one case was refused, so the refusal direction proved nothing")
        return 1
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

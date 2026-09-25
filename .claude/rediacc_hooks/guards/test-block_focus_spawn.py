#!/usr/bin/env python3
"""Control harness for block_focus_spawn, the PreToolUse half of focus mode (agent/plans/PLAN-stop-hook-focus-mode.md section 5).

BOTH DIRECTIONS. A guard that refused every spawn would pass the refusal cases and one that refused none would pass the allow cases, so each refusal has an allow twin differing by one planted fact: focus off, a reader instead of a writer, the fix item carrying the PR token, the babysit mode instead of merge.

LOAD-BEARING, NOT OPTIONAL. The guard declares `OWN_SUITE = True`, so `test_guards_differential.py` requires this file beside it, and `test_hooks_delegates.py` discovers and runs it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER against a real store on disk (`WORKLIST_STORE_DIR`) and a worklist directory (`TMPDIR`), in ONE pid-stamped directory removed on exit.
"""

import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
SID = "cafe0000-1111-2222-3333-444444444444"
ME = SID[:8]
PEER = "beef9999"
BASE = pathlib.Path(tempfile.gettempdir()) / ("focusspawn-%d" % os.getpid())


def stamp(minutes_ago=0.0):
    t = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


OLD = "0dd5e55a-9999-8888-7777-666666666666"


def world(focus="babysit", focus_age_min=1.0, off=False, fix_state=" ", owner=ME, lineage=False):
    """A fresh store: an optional focus on PR 543 for this session (optionally ended), a linked fix item, an unlinked item, and a peer's linked item."""
    if BASE.exists():
        shutil.rmtree(BASE)
    proj = BASE / "proj"
    (proj / ".git").mkdir(parents=True)
    (BASE / "tmp").mkdir()
    store = BASE / "store"
    store.mkdir()
    rows = [
        {"ev": "add", "id": "aa11aa11", "at": stamp(5), "by": ME, "s": fix_state, "o": ME, "t": "(%s) fix it pr:543/fix" % ME},
        {"ev": "add", "id": "bb22bb22", "at": stamp(5), "by": ME, "s": " ", "o": ME, "t": "(%s) a plan box" % ME},
        {"ev": "add", "id": "cc33cc33", "at": stamp(5), "by": PEER, "s": " ", "o": PEER, "t": "(%s) peer fix pr:543/fix" % PEER},
        {"ev": "add", "id": "dd44dd44", "at": stamp(5), "by": ME, "s": " ", "o": ME, "t": "(%s) other PR pr:5430/fix" % ME},
    ]  # fmt: skip
    if focus:
        rows.append(
            {
                "ev": "focus",
                "at": stamp(focus_age_min),
                "by": owner,
                "o": owner,
                "mode": focus,
                "branch": "0925-1",
                "pr": 543,
                "why": "operator",
            }
        )
    if lineage:
        # A proven compaction edge: the predecessor's focus is this session's.
        rows.append({"ev": "lineage", "at": stamp(2), "by": ME, "prev": OLD, "next": SID, "via": "compact"})  # fmt: skip
    if off:
        rows.append(
            {
                "ev": "focus",
                "at": stamp(0),
                "by": ME,
                "o": ME,
                "mode": "off",
                "branch": "0925-1",
                "pr": 543,
                "why": "operator",
            }
        )
    (store / ("%s.jsonl" % ME)).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return proj


def spawn(proj, kind, prompt="p", session=SID, tool="Agent", tmpdir=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("WORKLIST_")}
    env.update(
        {
            "CLAUDE_PROJECT_DIR": str(proj),
            "TMPDIR": tmpdir or str(BASE / "tmp"),
            "WORKLIST_STORE_DIR": str(BASE / "store"),
        }
    )
    payload = {
        "tool_name": tool,
        "session_id": session,
        "cwd": str(proj),
        "tool_input": {"subagent_type": kind, "description": "probe", "prompt": prompt},
    }
    proc = subprocess.run(
        [sys.executable, DISPATCH, "block_focus_spawn"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stderr


def refused_rows():
    return sum(
        len(p.read_text(encoding="utf-8").splitlines())
        for p in (BASE / "tmp").rglob("*.focusrefused-%s.jsonl" % ME)
    )


# (name, world kwargs, spawn kwargs, want_rc, stderr needle or "" for silence)
CASES: list[tuple[str, dict[str, Any], dict[str, Any], int, str]] = [
    ("a writer spawn in focus is refused", {}, {"kind": "general-purpose"}, 2, "focus mode is on"),
    ("the refusal names the three exits", {}, {"kind": "gate-author"}, 2, "--focus cafe0000 off"),
    ("no focus: the writer is allowed", {"focus": ""}, {"kind": "general-purpose"}, 0, ""),
    ("focus ended by off: allowed", {"off": True}, {"kind": "general-purpose"}, 0, ""),
    ("an expired focus (25h) is not enforced", {"focus_age_min": 1500}, {"kind": "general-purpose"}, 0, ""),
    ("an Explore spawn in focus is allowed", {}, {"kind": "Explore"}, 0, ""),
    ("a Plan spawn in focus is allowed", {}, {"kind": "Plan"}, 0, ""),
    ("pr-babysitter in babysit focus is allowed", {}, {"kind": "pr-babysitter"}, 0, ""),
    ("pr-babysitter in merge focus is refused", {"focus": "merge"}, {"kind": "pr-babysitter"}, 2, "focus mode is on"),
    ("declared fix work on a linked owned item is allowed", {}, {"kind": "general-purpose", "prompt": "focus-fix:#aa11aa11 go"}, 0, ""),
    ("fix work on an in-flight item is allowed", {"fix_state": ">"}, {"kind": "general-purpose", "prompt": "focus-fix:aa11aa11"}, 0, ""),
    ("fix label on an unlinked item is refused", {}, {"kind": "general-purpose", "prompt": "focus-fix:#bb22bb22"}, 2, "does not carry pr:543"),
    ("fix label on another PR's token is refused", {}, {"kind": "general-purpose", "prompt": "focus-fix:#dd44dd44"}, 2, "does not carry pr:543"),
    ("fix label on a peer's item is refused", {}, {"kind": "general-purpose", "prompt": "focus-fix:#cc33cc33"}, 2, "does not own"),
    ("fix label on a ticked item is refused", {"fix_state": "x"}, {"kind": "general-purpose", "prompt": "focus-fix:#aa11aa11"}, 2, "not open or in flight"),
    ("fix label on an unknown id is refused", {}, {"kind": "general-purpose", "prompt": "focus-fix:#abcdef99"}, 2, "no item in the store"),
    ("a predecessor's focus binds this session through lineage", {"owner": OLD[:8], "lineage": True}, {"kind": "general-purpose"}, 2, "focus mode is on"),
    ("a predecessor's focus with no lineage edge does not bind", {"owner": OLD[:8]}, {"kind": "general-purpose"}, 0, ""),
    ("another session's spawn sees no focus", {}, {"kind": "general-purpose", "session": "feed1234-0000"}, 0, ""),
    ("a non-Agent payload is ignored", {}, {"kind": "general-purpose", "tool": "Bash"}, 0, ""),
    ("the Task tool name is guarded too", {}, {"kind": "general-purpose", "tool": "Task"}, 2, "focus mode is on"),
]  # fmt: skip


def main():
    fails = 0
    refused = 0
    try:
        for name, wkw, skw, want_rc, needle in CASES:
            proj = world(**wkw)
            rc, err = spawn(proj, **skw)
            refused += rc == 2
            ok = rc == want_rc and ((needle in err) if needle else (err == ""))
            if ok and rc == 2 and refused_rows() != 1:
                ok = False
                err = "refused, but the .focusrefused ledger has %d row(s)" % refused_rows()
            fails += not ok
            print("%-62s want=%d got=%d %s" % (name, want_rc, rc, "ok" if ok else "FAIL"))
            if not ok:
                print("    stderr: %r" % err[:300])
        # FAILS OPEN, and says so: a worklist directory that cannot be created is an unreadable store.
        proj = world()
        blocker = BASE / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        rc, err = spawn(proj, "general-purpose", tmpdir=str(blocker))
        ok = rc == 0 and "ALLOWED unchecked" in err
        fails += not ok
        print("%-62s want=0 got=%d %s" % ("an unreadable store fails open and says so", rc, "ok" if ok else "FAIL"))  # fmt: skip
        if not ok:
            print("    stderr: %r" % err[:300])
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
    total = len(CASES) + 1
    print("block_focus_spawn: %d case(s), %d refused, %d failure(s)" % (total, refused, fails))
    if refused == 0:
        print("VACUOUS: not one case was refused, so the refusal direction proved nothing")
        return 1
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

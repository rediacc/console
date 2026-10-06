#!/usr/bin/env python3
"""PostToolUse (every tool): after an Edit, Write, MultiEdit or NotebookEdit, remind the session to commit its verified unit when it holds uncommitted edits and the branch has gone `commit_remind_min` minutes without a commit (agent/plans/PLAN-fast-loop.md, Part 2).

ADVISORY, ALWAYS. The reminder is `additionalContext` on a tool call that already ran; nothing is refused and the exit status is 0 whatever happens (operator 2026-10-06: a reminder, never a block).

CHEAP EXIT FIRST. Every other tool name leaves before any import of the Stop modules, any file read or any git call. For an edit tool the work is `wl_uncommitted.evaluate`: a transcript tail read behind a byte cursor, one `git log -1`, and `git status` at most every ten minutes. The reminder itself is throttled to once per `THROTTLE_S` per session through a sidecar beside the session state (`.commitremind-<sid8>`), so a long run of edits is told once and then left alone.

SHARED STATE. The cursor and the edited-file union live in the session state doc (`uc_*` keys) the Stop hook reads too: this member rewrites only those keys, on a fresh read of the doc, so it cannot clobber the Stop hook's own fields.
"""

import contextlib
import importlib.util
import json
import os
import pathlib
import sys
import time

HOOKS = pathlib.Path(__file__).resolve().parents[1]
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
#: At most one reminder per session per this many seconds.
THROTTLE_S = 300
UC_KEYS = ("uc_cursor", "uc_files", "uc_git")


def _load_syspath():
    """The canonical `.claude` hop, loaded BY PATH: this hook runs as a script, so `rediacc_hooks` is not importable by name until the hop has run."""
    hop_file = HOOKS.parent / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop_file)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render(text):
    return (
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
        )
        + "\n"
    )


def throttled(sidecar, now):
    """True when a reminder went out less than THROTTLE_S ago."""
    try:
        last = float(sidecar.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return 0 <= now - last < THROTTLE_S


def remind(doc, now=None):
    """The reminder text for this PostToolUse payload, or "" (not an edit tool, throttled, nothing owed or any failure)."""
    if doc.get("tool_name") not in EDIT_TOOLS:
        return ""
    now = time.time() if now is None else now
    syspath = _load_syspath()
    syspath.on_sys_path(syspath.STOP_DIR)
    import wl_core as C  # noqa: PLC0415 -- only an edit tool needs the Stop modules
    import wl_store as S  # noqa: PLC0415
    import wl_uncommitted as U  # noqa: PLC0415

    session = str(doc.get("session_id") or "")
    root = C.project_root(C.project_start(doc))
    worklist = C.worklist_for(C.project_start(doc))
    sidecar = worklist.with_suffix(".commitremind-%s" % (session or "unknown")[:8])
    if throttled(sidecar, now):
        return ""
    state = S.load_state(worklist, session)
    facts = U.evaluate(root, doc.get("transcript_path"), state, now=now)
    # Persist only the uc_* keys, on a fresh read: the Stop hook owns every other field of the doc.
    fresh = S.load_state(worklist, session)
    fresh.update({k: state[k] for k in UC_KEYS if k in state})
    S.save_state(worklist, session, fresh)
    if not facts:
        return ""
    with contextlib.suppress(OSError):
        sidecar.write_text("%d" % now, encoding="utf-8")
    return U.render(facts)


def main(stdin=None, stdout=None):
    if os.environ.get("COMMIT_REVIEW_CHILD") or os.environ.get("STOPHOOK_CHILD"):
        return 0
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        doc = json.loads(stdin.read() or "{}")
        if not isinstance(doc, dict) or doc.get("tool_name") not in EDIT_TOOLS:
            return 0
        text = remind(doc)
        if text:
            stdout.write(render(text))
    except Exception:  # noqa: BLE001 -- advisory: never fail the chain
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Refuse a writer-class Agent spawn while this session is in focus mode, except declared babysit/merge fix work.

THE ASK (operator, 2026-09-25, spec Y): "Finish, don't start. Running writers and in-flight items are allowed to finish. No new writers are spawned: the pre-agent guard refuses, except for babysit/merge fix work." Plan: agent/plans/PLAN-stop-hook-focus-mode.md section 5. Focus is switched on with `worklist.py --focus <me> babysit|merge` and ends on `--focus <me> off`, when the PR merges or closes, or after 24 hours.

THE DECISION, for an Agent or Task call:
  1. no active focus for this session (the store's newest `focus` event over every owner the session owns is `off`, absent, or older than the 24-hour cap) -> ALLOW;
  2. a read-only type (`wl_roster.read_only_types`, as the cap guard) -> ALLOW;
  3. focus mode `babysit` and subagent_type `pr-babysitter` -> ALLOW: that is the `/pr-babysit bg` loop itself;
  4. `focus-fix:#<item-id>` in the description or prompt, naming a store item this session owns (a non-empty owner), in state `[ ]` or `[>]`, whose text carries the focus PR's `pr:<n>` -> ALLOW. A bare label is not enough: the item is a store fact the Stop guide shows;
  5. anything else -> DENY, with the three exits (declare fix work, park it on `worker:queue`, `--focus off`), and one row appended to `.focusrefused-<me8>.jsonl` beside the worklist, which the Stop hook's parked summary counts.

The writer cap still applies to an allowed spawn: `block_agent_cap` runs first (ORDER 3).

IT READS ONLY THE FOCUS AND LINEAGE LINES of the store (`wl_store.focus_fold`) on every Agent call, and pays for a full fold only for a `focus-fix` spawn while focused: a full fold measured ~0.75 s per call against ~0.2 s for the cap guard (the plan's 200 ms threshold, section 10).

FAILS OPEN WHEN IT CANNOT READ THE STORE, and says so on stderr, the same contract as the cap guard's UNCOUNTABLE: the Stop hook reads the same store on the next stop.

NO ENVIRONMENT READ. This file is a sealed module in `.ci/policy/worklist-env-registry.json`. The payload's own `cwd` and `session_id` locate the session; the store directory is resolved by wl_store.

ITS EVIDENCE. `OWN_SUITE = True`, so `.claude/rediacc_hooks/guards/test-block_focus_spawn.py` drives it through the dispatcher in both directions, and `.claude/rediacc_hooks/tests/test_wl_focus.py` drives it beside the Stop half.
"""

import datetime
import json
import os
import pathlib
import tempfile

from rediacc_hooks import hookio, syspath

CHAIN = "pre-agent"
OWN_SUITE = True
ORDER = 4

# The planted defect for the differential: any owned item counts as fix work, whatever PR it is about.
DEFECT = ("if not wl_standdown.pr_linked(", "if False and not wl_standdown.pr_linked(")

STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"

# ---- the differential's world: one store with a focus on PR 543 and three items ------------------
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-focus-world")
_SID = "f0c05e55-1111-2222-3333-444444444444"
_PEER = "0fee0fee"


def _focus_world(_unused):
    """A store at WORLD/store: focus on for `_SID`, a linked fix item, an unlinked item, and a peer's linked item."""
    store = pathlib.Path(WORLD) / "store"
    store.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(WORLD) / "tmp").mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    me8 = _SID[:8]
    rows = [
        {"ev": "add", "id": "f1a1f1a1", "at": now, "by": me8, "s": " ", "o": me8, "t": "(%s) fix the red job pr:543/fix" % me8},
        {"ev": "add", "id": "f2b2f2b2", "at": now, "by": me8, "s": " ", "o": me8, "t": "(%s) unrelated plan box" % me8},
        {"ev": "add", "id": "f3c3f3c3", "at": now, "by": _PEER, "s": " ", "o": _PEER, "t": "(%s) a peer's fix pr:543/fix" % _PEER},
        {"ev": "focus", "at": now, "by": me8, "o": me8, "mode": "babysit", "branch": "0925-1", "pr": 543, "why": "operator"},
    ]  # fmt: skip
    (store / ("%s.jsonl" % me8)).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return WORLD


FIXTURES = {"focus-world": _focus_world}

# The variables are read by wl_store / wl_core, never by this guard; resolving the token is what builds the world before any case runs.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (
        "focus",
        {
            "WORKLIST_STORE_DIR": "{FIXTURE:focus-world}/store",
            "TMPDIR": "{FIXTURE:focus-world}/tmp",
        },
        {},
    )
]


def _spawn(kind, text):
    return {
        "tool_name": "Agent",
        "session_id": _SID,
        "cwd": "/nonexistent-focus-spawn-fixture",
        "tool_input": {"subagent_type": kind, "description": "fixture", "prompt": text},
    }


EDGE_CASES = [
    ("writer-spawn-in-focus", _spawn("general-purpose", "do a thing")),
    ("reader-spawn-in-focus", _spawn("Explore", "look")),
    ("babysitter-spawn-in-focus", _spawn("pr-babysitter", "babysit")),
    ("declared-fix-work", _spawn("general-purpose", "focus-fix:#f1a1f1a1 fix the red job")),
    ("fix-label-on-an-unlinked-item", _spawn("general-purpose", "focus-fix:#f2b2f2b2")),
    ("fix-label-on-a-peer-item", _spawn("general-purpose", "focus-fix:#f3c3f3c3")),
    (
        "another-session-has-no-focus",
        dict(_spawn("general-purpose", "x"), session_id="0ddba11-no-focus"),
    ),
]

REFUSED_FOCUS = (
    "BLOCKED: focus mode is on (%s, PR #%s on %s, since %s). Finish, don't start: running writers\n"
    "and in-flight items finish, and a new %r writer is not spawned.\n"
    "\n"
    "Do one of these:\n"
    "  - if this IS the PR's fix work, declare it: add an item carrying the PR token,\n"
    '      .claude/hooks/stop/worklist.py --add %s "<what> pr:%s/fix"\n'
    "    then put focus-fix:#<id> in the spawn's description or prompt\n"
    "  - park it for after the PR: --add it, then\n"
    "      .claude/hooks/stop/worklist.py --lease %s <id> +120 worker:queue\n"
    "  - end focus: .claude/hooks/stop/worklist.py --focus %s off\n"
    "\n"
    "Read-only spawns (Plan, Explore, and custom types with no edit tool) are never refused.\n"
)

REFUSED_FIX = "focus-fix:#%s names %s, so it does not declare fix work for PR #%s.\n"

UNREADABLE = (
    "focus-spawn: could not read the worklist store for session %r (%s), so this %r spawn was\n"
    "ALLOWED unchecked. The Stop hook reads the same store on the next stop.\n"
)


def _fix_problem(owned, wl_standdown, rec, focus):
    """ "" when store record `rec` is declared fix work for `focus`, else why not."""
    if rec is None:
        return "no item in the store"
    owner = rec.get("owner")
    if not owner or not owned(owner):
        return "an item this session does not own"
    if rec.get("state") not in (" ", ">"):
        return "an item that is not open or in flight"
    if not wl_standdown.pr_linked(rec.get("text") or "", focus):
        return "an item that does not carry %s" % (wl_standdown.pr_token(focus) or "the PR token")
    return ""


def _ledger(worklist, me8, kind, desc):
    row = {
        "at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "desc": str(desc)[:120],
    }
    try:
        with open(
            worklist.with_suffix(".focusrefused-%s.jsonl" % me8), "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def run(event):
    doc = event.doc
    if not isinstance(doc, dict) or doc.get("tool_name") not in ("Agent", "Task"):
        return hookio.ALLOW
    raw_input = doc.get("tool_input")
    tool_input = raw_input if isinstance(raw_input, dict) else {}
    kind = str(tool_input.get("subagent_type") or "general-purpose")
    cwd = str(doc.get("cwd") or event.cwd)
    session_id = str(doc.get("session_id") or "")
    syspath.on_sys_path(STOP_DIR)
    try:
        import wl_core as C  # noqa: PLC0415 -- loaded only for an Agent call, never for the other chains
        import wl_standdown  # noqa: PLC0415
        import wl_store as S  # noqa: PLC0415

        root = C.project_root(C.project_start({"cwd": cwd}))
        worklist = C.worklist_for(C.project_start({"cwd": cwd}))
        # THE LIGHT READ: only focus and lineage lines are parsed (a full fold costs ~0.5 s on this repo's log, on every Agent call). The lineage binding is for the PAYLOAD's session, so a compacted session keeps its focus.
        light = S.focus_fold(worklist, root)
        C.bind_lineage(session_id, light.aliases_of(session_id))
        owned = lambda o: C.owned_by_me(o, session_id)  # noqa: E731
        focus = wl_standdown.active_focus(light.focus, owned)
    except Exception as exc:  # noqa: BLE001 -- fail open, and say so
        event.warn_raw(
            UNREADABLE % (session_id, "%s: %s" % (type(exc).__name__, str(exc)[:120]), kind)
        )
        return hookio.ALLOW
    if focus is None or wl_standdown.expired(focus):
        return hookio.ALLOW
    import wl_roster  # noqa: PLC0415

    if kind in wl_roster.read_only_types(root):
        return hookio.ALLOW
    if focus.get("mode") == "babysit" and kind == "pr-babysitter":
        return hookio.ALLOW
    text = "%s\n%s" % (tool_input.get("description") or "", tool_input.get("prompt") or "")
    m = wl_standdown.FOCUS_FIX_RE.search(text)
    why_not = ""
    if m:
        # The full fold, paid only for a declared fix-work spawn while focused.
        try:
            rec = S.load(worklist, sync=False).by_id.get(m.group(1))
        except Exception as exc:  # noqa: BLE001 -- fail open, and say so
            event.warn_raw(UNREADABLE % (session_id, "%s: %s" % (type(exc).__name__, exc), kind))
            return hookio.ALLOW
        C.bind_lineage(session_id, light.aliases_of(session_id))
        why_not = _fix_problem(owned, wl_standdown, rec, focus)
        if not why_not:
            return hookio.ALLOW
    me8 = (session_id or "unknown")[:8]
    msg = REFUSED_FOCUS % (
        focus.get("mode"),
        focus.get("pr") or "?",
        focus.get("branch"),
        focus.get("at"),
        kind,
        me8,
        focus.get("pr") or "<n>",
        me8,
        me8,
    )
    if m and why_not:
        msg = REFUSED_FIX % (m.group(1), why_not, focus.get("pr") or "?") + msg
    _ledger(worklist, me8, kind, tool_input.get("description") or "")
    event.warn_raw(msg)
    return hookio.DENY

"""Refuse a writer spawn that would break a live plan's mutex, or claim files a live plan already owns.

THE ASK (operator, 2026-09-25, section X): "The concurrency field is really about files. 'Exclusive' is only needed when two plans touch the same files, like today's A3 and scanner collision. Declaring the owned paths lets the hook decide instead of relying on a label." Plan: agent/plans/PLAN-plan-priority-concurrency.md section 5a (T5).

THE DECISION, for an Agent or Task call (the rules are `wl_planconc.spawn_verdict`, shared with the roster's queue):
  1. not a spawn, or a read-only type (`wl_roster.read_only_types`, as the cap guard) -> ALLOW;
  2. S = the plans the spawn serves (`spawn_plans`: a `Plan: PLAN-x.md` line, else the `#<id>` items it names, else a bare
     `PLAN-x.md [<8hex>]`); L = the plans live writers serve (`live_plans`: this session's live writers through their first
     prompts, every session's fresh leases on plan-linked items), minus S;
  3. DENY when a plan in L is `Concurrency: exclusive` (the mutex);
  4. DENY when a plan in S is exclusive and L is not empty (decision D5: a mutex taken while others hold files is no mutex);
  5. DENY when S's Owns and L's Owns share a path, naming both globs and one witness path;
  6. a planless spawn is judged on its own `Owns:` line when it declares one, refused under a live exclusive plan unless that
     line is disjoint, and ALLOWED with a stderr note when it declares nothing (decision D4).

The writer cap still applies first: `block_agent_cap` is ORDER 3 and `block_focus_spawn` ORDER 4 on the same chain.

UNTIL THE MIGRATION. While `wl_plandeps.X_FIELDS_REQUIRED` is False a plan with no Owns is not judged for overlap (stderr note); once it is True a missing Owns fails closed as `**` and a spawn for such a plan is refused.

FAILS OPEN, LOUDLY, when it cannot see: a module that will not import, a store that will not fold, or a writer estimate that is blind with no cross-session lease visible either. The Stop hook's roster recounts from the authoritative event (PLAN-plan-priority-concurrency T8, `roster-concurrency`).

NO ENVIRONMENT READ. This file is a sealed module in `.ci/policy/worklist-env-registry.json`. The payload's own `cwd` and `session_id` locate the session.

ITS EVIDENCE. `OWN_SUITE = True`, so `.claude/rediacc_hooks/guards/test-block_plan_concurrency.py` drives it through the dispatcher in both directions against fixture trees and stores; `.claude/hooks/stop/test-plandeps.py` covers `spawn_verdict` and the overlap engine it calls.
"""

import datetime
import json
import os
import pathlib
import tempfile

from rediacc_hooks import hookio, syspath

CHAIN = "pre-agent"
OWN_SUITE = True
ORDER = 5

# The mutex refusal, planted away: the differential's mutex EDGE_CASE must then stop speaking.
DEFECT = ("return _refuse(event, verdict, kind, MUTEX_EXITS)", "return hookio.ALLOW")

STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"

# ---- the differential's world: a tree with an exclusive plan E held by a peer's fresh lease ------
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-planconc-world")
_SID = "c0ffee11-1111-2222-3333-444444444444"
_PEER = "0dd0dd00"
_PLAN = "# PLAN: %s\n\nStatus: in-progress\nOwner: %s\nDepends-On: no-dep -- a fixture plan for the concurrency guard\nPriority: P2\nConcurrency: %s\nOwns: %s\n\n## Tasks\n\n- [ ] T1 a box\n"


def _conc_world(_unused):
    """WORLD/tree (a plan tree: E exclusive, F parallel) and WORLD/store (a peer's fresh lease on an E-linked item)."""
    tree = pathlib.Path(WORLD) / "tree"
    plans = tree / "agent" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (tree / ".git").mkdir(exist_ok=True)
    (plans / "PLAN-e.md").write_text(
        _PLAN % ("e", _PEER, "exclusive -- regenerates every golden file", "docs/e/**"),
        encoding="utf-8",
    )
    (plans / "PLAN-f.md").write_text(
        _PLAN % ("f", _SID[:8], "parallel", "docs/f/**"), encoding="utf-8"
    )
    store = pathlib.Path(WORLD) / "store"
    store.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(WORLD) / "tmp").mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.UTC)
    at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    until = (now + datetime.timedelta(minutes=100)).strftime("%Y-%m-%dT%H:%MZ")
    rows = [
        {"ev": "add", "id": "e0e0e0e0", "at": at, "by": _PEER, "s": " ", "o": _PEER, "t": "(%s) regenerate goldens PLAN-e.md [e1e1e1e1]" % _PEER},
        {"ev": "lease", "id": "e0e0e0e0", "at": at, "by": _PEER, "until": until, "worker": "a9e9e9e9e9", "note": "", "worker_verified": True},
        {"ev": "add", "id": "f0f0f0f0", "at": at, "by": _SID[:8], "s": " ", "o": _SID[:8], "t": "(%s) edit docs PLAN-f.md [f1f1f1f1]" % _SID[:8]},
    ]  # fmt: skip
    (store / ("%s.jsonl" % _PEER)).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return WORLD


FIXTURES = {"planconc-world": _conc_world}

# The variables are read by wl_core / wl_store, never by this guard.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (
        "planconc",
        {
            "CLAUDE_PROJECT_DIR": "{FIXTURE:planconc-world}/tree",
            "WORKLIST_STORE_DIR": "{FIXTURE:planconc-world}/store",
            "TMPDIR": "{FIXTURE:planconc-world}/tmp",
        },
        {},
    )
]


def _spawn(kind, text, session=_SID):
    return {
        "tool_name": "Agent",
        "session_id": session,
        "cwd": "/nonexistent-plan-concurrency-fixture",
        "tool_input": {"subagent_type": kind, "description": "fixture", "prompt": text},
    }


EDGE_CASES = [
    ("writer-for-another-plan-under-a-live-mutex", _spawn("general-purpose", "work #f0f0f0f0")),
    ("writer-for-the-exclusive-plan-itself", _spawn("general-purpose", "Plan: PLAN-e.md")),
    ("reader-under-a-live-mutex", _spawn("Explore", "Plan: PLAN-f.md")),
    (
        "planless-writer-with-disjoint-owns",
        _spawn("general-purpose", "fix a typo\nOwns: docs/zz/**"),
    ),
    (
        "the-holder-session-itself",
        _spawn("general-purpose", "Plan: PLAN-f.md", session=_PEER + "-aaaa"),
    ),
    ("not-a-spawn", {"tool_name": "Bash", "tool_input": {"command": "true"}}),
]

MUTEX_EXITS = """
Do one of these:
  - queue the work until the holder finishes; queue-slot names it then:
      .claude/hooks/stop/worklist.py --lease <me> <id> +120 worker:queue
  - dispatch read-only work as subagent_type Plan or Explore, which is never refused
  - stop the holder (TaskStop <id>) and release its lease
"""

OVERLAP_EXITS = """
Do one of these:
  - queue the work until the holder finishes:
      .claude/hooks/stop/worklist.py --lease <me> <id> +120 worker:queue
  - if a plan over-claims, narrow its Owns (visible in the diff):
      .ci/scripts/quality/check_plan_deps.py --set-x <plan> "Owns: ..." --write
  - dispatch read-only work as subagent_type Plan or Explore
  - stop the holder (TaskStop <id>) and release its lease
"""

HEAD = {
    "mutex": "BLOCKED: a live plan holds the mutex, so this %r writer does not start.",
    "mutex-own": "BLOCKED: this %r writer serves an exclusive plan, and other plans are live.",
    "overlap": "BLOCKED: this %r writer would edit files a live plan already owns.",
    "no-owns": "BLOCKED: this %r writer serves a plan that declares no Owns, which fails closed.",
    "owns-none": "BLOCKED: this %r writer serves a plan that declares it edits nothing.",
}

UNEXAMINED = (
    "plan-concurrency: %s, so this %r spawn was ALLOWED unchecked. The Stop hook's roster\n"
    "recounts plan concurrency from the authoritative event on the next stop.\n"
)


def _refuse(event, verdict, kind, exits):
    head = HEAD.get(
        verdict.kind, "BLOCKED: this %r writer breaks plan concurrency (" + verdict.kind + ")."
    )
    event.warn_raw(
        "%s\n\n%s\n%s" % (head % kind, "\n".join("  " + ln for ln in verdict.lines), exits)
    )
    return hookio.DENY


def run(event):
    doc = event.doc
    if not isinstance(doc, dict) or doc.get("tool_name") not in ("Agent", "Task"):
        return hookio.ALLOW
    raw_input = doc.get("tool_input")
    tool_input = raw_input if isinstance(raw_input, dict) else {}
    kind = str(tool_input.get("subagent_type") or "general-purpose")
    cwd = str(doc.get("cwd") or event.cwd)
    session_id = str(doc.get("session_id") or "")
    text = "%s\n%s" % (tool_input.get("description") or "", tool_input.get("prompt") or "")
    syspath.on_sys_path(STOP_DIR)
    try:
        import wl_core as C  # noqa: PLC0415 -- loaded only for an Agent call, never for the other chains
        import wl_leasehelp as LH  # noqa: PLC0415
        import wl_planconc as X  # noqa: PLC0415
        import wl_roster  # noqa: PLC0415

        root = C.project_root(C.project_start({"cwd": cwd}))
        if kind in wl_roster.read_only_types(root):
            return hookio.ALLOW
        declared = X.declared_owns(text)
        names_work = bool(X.spawn_plans(text) or LH.item_refs(text))
        # THE CHEAP PATH: a spawn that names no plan, no item and no Owns can only be refused by a live mutex, and there is none anywhere unless some plan declares one. Reading ~40 plan heads costs milliseconds; a full fold costs ~0.5 s.
        if not names_work and declared is None and not X.exclusive_plans(root):
            event.warn_raw(
                "plan-concurrency: a planless %r writer declares no `Owns:` line, so its files are not "
                "checked against live plans (add `Plan: PLAN-x.md` or `Owns: <globs>` to the prompt).\n"
                % kind
            )
            return hookio.ALLOW
        import wl_store as S  # noqa: PLC0415

        fold = S.load(C.worklist_for(C.project_start({"cwd": cwd})), sync=False)
        by_id = {r["id"]: r for r in fold.items if isinstance(r, dict) and r.get("id")}
        serving = X.spawn_plans(text, by_id)
        live = X.live_plans(cwd, session_id, fold)
    except Exception as exc:  # noqa: BLE001 -- fail open, and say so
        event.warn_raw(
            UNEXAMINED
            % (
                "the plan state could not be read (%s: %s)" % (type(exc).__name__, str(exc)[:160]),
                kind,
            )
        )
        return hookio.ALLOW
    if live is None:
        event.warn_raw(
            UNEXAMINED
            % (
                "no live writer could be counted for session %r and no lease is visible"
                % session_id,
                kind,
            )
        )
        return hookio.ALLOW
    verdict = X.spawn_verdict(serving, live, lambda base: X.plan_x(root, base), declared)
    if verdict.kind in ("mutex", "mutex-own"):
        return _refuse(event, verdict, kind, MUTEX_EXITS)
    if not verdict.allow:
        return _refuse(event, verdict, kind, OVERLAP_EXITS)
    if verdict.note:
        event.warn_raw("plan-concurrency: %s.\n" % verdict.note)
    return hookio.ALLOW

"""The handover contract between the landing and the development tree (agent/plans/PLAN-simple-two-tree-loop.md D5, box B7).

ONE EVENT KIND, `handover`, in the worklist store both trees share (LT14), addressed by TREE ROLE rather than session id: the landing session cannot know which session the development tree runs today, and either session may restart. Two shapes ride the kind:

  open    {"ev": "handover", "id", "at", "by", "kind": stuck|churn|lesson, "check", "evidence"}   written by `worklist.py --handover`
  answer  {"ev": "handover", "id", "at", "by", "answer": lease:<id>|keep|change|undo|done}          written by `worklist.py --handover-answer`

The fold here reads only these lines (the light read of wl_store.phase_fold), so the main fold never parses them and ignores the kind. A later answer replaces an earlier one.

WHO IS OWED WHAT, per stop (`stop_findings`):

  development  an unanswered `stuck` or `churn` BLOCKS (`handover-open`): the landing session paused on it. An unanswered `lesson` ADVISES (`handover-lesson`): a CI-only failure the local quick checks could learn to catch (ruling 7).
  landing      an answer `lease:<id>` BLOCKS (`handover-land`) until that lease is landed (`./run.sh worktree land <id>`, then the push), or until a `done` answer closes it.

`keep`, `change`, `undo` and `done` close a handover for both trees. A tree with no landing record has no role and owes nothing here.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

import wl_core as C
import wl_store as S

EVENT = "handover"
KINDS = ("stuck", "churn", "lesson")
BLOCKING_KINDS = frozenset({"stuck", "churn"})
CLOSING_ANSWERS = ("keep", "change", "undo", "done")
LEASE_PREFIX = "lease:"
ROLE_LANDING = "landing"
ROLE_DEVELOPMENT = "development"
KEY_OPEN = "handover-open"
KEY_LESSON = "handover-lesson"
KEY_LAND = "handover-land"
KEY_BUG = "handover-bug"
ID_RE = re.compile(r"^[0-9a-f]{8}$")
LEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_LINE = re.compile(r'"ev":\s*"handover"')


def valid_answer(answer: str) -> bool:
    """True for `keep|change|undo|done` or `lease:<id>` with a plausible lease id."""
    answer = str(answer or "")
    if answer in CLOSING_ANSWERS:
        return True
    return answer.startswith(LEASE_PREFIX) and bool(LEASE_ID_RE.match(answer[len(LEASE_PREFIX) :]))


def open_event(by: str, kind: str, check: str, evidence: str, hid: str | None = None) -> dict:
    """The `open` payload; raises ValueError on a kind outside KINDS or an empty check or evidence."""
    if kind not in KINDS:
        raise ValueError("a handover kind is one of %s, not %r" % ("|".join(KINDS), kind))
    if not str(check or "").strip() or not str(evidence or "").strip():
        raise ValueError("a handover needs a check and evidence")
    return {
        "ev": EVENT,
        "id": hid or secrets.token_hex(4),
        "at": C.stamp_now(),
        "by": str(by)[:8],
        "kind": kind,
        "check": str(check).strip(),
        "evidence": str(evidence).strip(),
    }


def answer_event(by: str, hid: str, answer: str) -> dict:
    """The `answer` payload; raises ValueError on an answer valid_answer refuses."""
    if not valid_answer(answer):
        raise ValueError(
            "a handover answer is lease:<id>, %s, not %r" % ("|".join(CLOSING_ANSWERS), answer)
        )
    return {"ev": EVENT, "id": str(hid), "at": C.stamp_now(), "by": str(by)[:8], "answer": answer}


def write(worklist, payload: dict, root=None) -> None:
    S.append_events(worklist, [payload], root=root)


def _events(worklist, root=None) -> list[dict]:
    texts = S._store_texts(root)
    legacy = S.events_path(worklist)
    if legacy.exists():
        text = S._read_text(legacy)
        if text is not None:
            texts.append(text)
    out: list[dict] = []
    for text in texts:
        out.extend(S._parse_events("\n".join(ln for ln in text.splitlines() if _LINE.search(ln))))
    out.sort(key=S.event_order)
    return [e for e in out if isinstance(e, dict) and e.get("ev") == EVENT]


def fold(worklist, root=None, events: list[dict] | None = None) -> dict[str, dict[str, Any]]:
    """{id: {"id", "kind", "check", "evidence", "at", "by", "answer", "answered_at", "answered_by"}}. An answer for an id never opened is dropped; a later answer wins."""
    out: dict[str, dict[str, Any]] = {}
    for ev in events if events is not None else _events(worklist, root):
        hid = str(ev.get("id") or "")
        if not hid:
            continue
        if "kind" in ev:
            if ev.get("kind") not in KINDS or hid in out:
                continue
            out[hid] = {
                "id": hid,
                "kind": ev.get("kind"),
                "check": str(ev.get("check") or ""),
                "evidence": str(ev.get("evidence") or ""),
                "at": str(ev.get("at") or ""),
                "by": str(ev.get("by") or ""),
                "answer": "",
                "answered_at": "",
                "answered_by": "",
            }
        elif "answer" in ev and hid in out and valid_answer(answer := str(ev.get("answer") or "")):
            out[hid].update(
                answer=answer,
                answered_at=str(ev.get("at") or ""),
                answered_by=str(ev.get("by") or ""),
            )
    return out


def lease_of(record: dict) -> str:
    answer = str(record.get("answer") or "")
    return answer[len(LEASE_PREFIX) :] if answer.startswith(LEASE_PREFIX) else ""


# Why a lease's state could not be read, by lease id: lease_landed records it, `stop_findings` names it in the land text it already emits. Per process, which is per stop.
UNREADABLE: dict[str, str] = {}


def lease_landed(root, lease_id: str) -> bool | None:
    """True when the lease holds nothing to land (its record stays but `worktree gc` removed the tree, which GC does only for a landed one; or no dirty path and no unlanded commit), False when it does, None when it cannot be read or no such lease is known. Read through wl_worktrees, the reading the `worktree-unlanded` check uses."""
    UNREADABLE.pop(lease_id, None)
    try:
        import wl_worktrees

        world = wl_worktrees.read_world(root)
        repos = world["leases"].get(lease_id)
        if lease_id not in world["leases"] and lease_id not in world["dirs"]:
            return True if lease_id in world["records"] else None
        if not repos:
            return None
        record = world["records"].get(lease_id) or {}
        got = wl_worktrees.figures(
            repos, world["tips"], world["pins"].get(lease_id) or {}, record.get("base") or {}
        )
        if "doubt" in got:
            return None
        return not (got.get("dirty") or got.get("commits"))
    except Exception as exc:
        UNREADABLE[lease_id] = "%s: %s" % (type(exc).__name__, exc)
        return None


def stop_findings(records: dict[str, dict], role: str, landed=None, me8: str = "<me>"):
    """[(key, blocks, text)] this tree owes. `landed(lease_id)` answers lease_landed (injected so a test plants it); an unreadable lease (None) still blocks, since an unread lease is not a landed one."""
    out = []
    if role == ROLE_DEVELOPMENT:
        for rec in sorted(records.values(), key=lambda r: r["at"]):
            if rec["answer"]:
                continue
            if rec["kind"] in BLOCKING_KINDS:
                out.append((KEY_OPEN, True, open_text(rec, me8)))
            else:
                out.append((KEY_LESSON, False, lesson_text(rec, me8)))
    elif role == ROLE_LANDING:
        for rec in sorted(records.values(), key=lambda r: r["at"]):
            lease = lease_of(rec)
            if not lease:
                continue
            state = landed(lease) if landed is not None else False
            if state is True:
                continue
            text = land_text(rec, lease, me8)
            if state is None and lease in UNREADABLE:
                text += "\n  (the lease's state could not be read: %s)" % UNREADABLE[lease]
            out.append((KEY_LAND, True, text))
    return out


def open_text(rec: dict, me8: str) -> str:
    what = (
        "a check survived 3 fixes aimed at it"
        if rec["kind"] == "stuck"
        else "landing fixes broke previously green checks"
    )
    act = (
        "cut a lease on the landing tip (`./run.sh worktree lease --tree landing`), brief a writer on the stuck check (a brief naming `Plan:` or `Owns:` for the landing fix; handover #%s is the record), then answer `lease:<lease-id>`"
        % rec["id"]
        if rec["kind"] == "stuck"
        else "decide keep, change or undo"
    )
    return (
        "HANDOVER #%s FROM THE LANDING TREE (%s on %s, since %s): %s, and the landing session waits on this tree.\n"
        "  evidence: %s\n"
        "  next: %s, then: python3 .claude/hooks/stop/worklist.py --handover-answer %s %s <answer>"
        % (
            rec["id"],
            rec["kind"],
            rec["check"],
            rec["at"],
            what,
            rec["evidence"],
            act,
            me8,
            rec["id"],
        )
    )


def lesson_text(rec: dict, me8: str) -> str:
    return (
        "HANDOVER LESSON #%s (%s, since %s): a CI-only failure the local quick checks could learn to catch, where that is possible and cheap (ruling 7).\n"
        "  evidence: %s\n"
        "  close it: python3 .claude/hooks/stop/worklist.py --handover-answer %s %s done"
        % (rec["id"], rec["check"], rec["at"], rec["evidence"], me8, rec["id"])
    )


def land_text(rec: dict, lease: str, me8: str) -> str:
    return (
        "HANDOVER #%s ANSWERED WITH LEASE %s (%s on %s): the development tree's fix waits for this tree to land it once.\n"
        "  next: ./run.sh worktree land %s (submodules first, then the gitlink), push, then the block clears; "
        "or close it: python3 .claude/hooks/stop/worklist.py --handover-answer %s %s done"
        % (rec["id"], lease, rec["kind"], rec["check"], lease, me8, rec["id"])
    )

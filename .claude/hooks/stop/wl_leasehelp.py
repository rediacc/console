"""wl_leasehelp: lease continuity without hand bookkeeping (agent/plans/PLAN-stop-hook-continuity.md P2.1-P2.4).

WHAT WAS DONE BY HAND. Every new background shell needed a fresh `--lease` on the same items; a successor agent spawned for the same items inherited nothing; an open item waiting on another had no way to say so, so the only way to quiet `open-items` for it was a lease on an unrelated shell. Each of those is a fact the hook can see for itself, so each is answered here from facts, and
every state still FAILS CLOSED to an ordinary open item.

  worker:lead       the lead drives the item inline. Covered while any of this session's background tasks is live (something will
                    wake the lead), renewed by the hook while covered, at most LEAD_MAX at once, and open the moment nothing is live.
  auto-lease        an open item named `#<id>` in a live agent's first prompt, or in a live shell's description, is leased to that task.
  BLOCKED_BY:#id    an open item waiting on others is reported `waiting`, not `open`, until every blocker closes; the chain's root still blocks.

Pure helpers only: no environment reads, no store writes. The callers (worklist.py, wl_store.classify_items, wl_checks) own the effects.
"""

import json
import re

# The in-session lead's own worker name. Not a background task id, so the roster never counts it as a writer.
LEAD_WORKER = "lead"
# The placeholder worker of a queued item: writer work the cap forbids starting (wl_roster.QUEUE_WORKER re-exports it). Here so wl_store.classify_items can tell a queued item waiting on a BLOCKED_BY blocker from a dead lease without importing the roster.
QUEUE_WORKER = "queue"
# How many items the lead may hold inline at once. A sealed literal: more than this is not "driving it inline", it is a parking bay.
LEAD_MAX = 3
# How far ahead a hook-written lease (an auto-lease or a lead renewal) reaches. Inside wl_core.MAX_LEASE_MIN.
AUTO_LEASE_MIN = 60
# A lead lease is renewed once fewer than this many minutes remain, so a renewal is not appended on every stop.
LEAD_RENEW_BELOW_MIN = 30
# How much of an agent transcript's head is read for its first prompt.
PROMPT_HEAD_BYTES = 65536

ITEM_REF = re.compile(r"#([0-9a-f]{8}(?:[0-9a-f]{4})?)\b")
BLOCKED_BY = re.compile(r"\bBLOCKED_BY:[ \t]*(#?[0-9a-f]{8,12}(?:[ \t]*,[ \t]*#?[0-9a-f]{8,12})*)")
# The states an item has left for good: done, or tombstoned.
CLOSED_STATES = ("x", "~")


def item_refs(text):
    """Every `#<8 or 12 hex>` item reference in `text`, in order, without repeats."""
    out = []
    for ref in ITEM_REF.findall(str(text or "")):
        if ref not in out:
            out.append(ref)
    return out


def blocked_by(text):
    """The item ids a `BLOCKED_BY:#a,#b` token in `text` names, in order, without repeats."""
    out = []
    for m in BLOCKED_BY.finditer(str(text or "")):
        for raw in re.split(r"[ \t]*,[ \t]*", m.group(1)):
            ref = raw.lstrip("#")
            if ref and ref not in out:
                out.append(ref)
    return out


def resolve(ref, by_id):
    """The item id `ref` names: exact, else a UNIQUE prefix either way round (ids are 8 or 12 hex). None when unknown or ambiguous."""
    if ref in by_id:
        return ref
    hits = [i for i in by_id if i.startswith(ref) or ref.startswith(i)]
    return hits[0] if len(hits) == 1 else None


def waiting_on(rec, by_id):
    """The blocker ids of an item that are still NOT closed, or [] when it is not waiting."""
    out = []
    for ref in blocked_by(rec.get("text") or ""):
        rid = resolve(ref, by_id)
        if rid is not None and by_id[rid].get("state") not in CLOSED_STATES:
            out.append(rid)
    return out


def blocker_error(item_id, text, by_id):
    """Why a BLOCKED_BY token in `text` is refused for `item_id`, or "". Refused: an unknown or ambiguous blocker, a closed one, the item itself, and a cycle through existing items."""
    for ref in blocked_by(text):
        rid = resolve(ref, by_id)
        if rid is None:
            return "BLOCKED_BY names #%s, which is no item here (or is ambiguous)" % ref
        if item_id and rid == item_id:
            return "BLOCKED_BY names the item itself"
        if by_id[rid].get("state") in CLOSED_STATES:
            return "BLOCKED_BY names #%s, which is already closed; nothing is waiting" % rid
        seen, stack = set(), [rid]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in blocked_by((by_id.get(cur) or {}).get("text") or ""):
                nid = resolve(nxt, by_id)
                if nid is None:
                    continue
                if item_id and nid == item_id:
                    return "BLOCKED_BY #%s would close a cycle back to this item" % rid
                stack.append(nid)
    return ""


def lead_covered(running, verdicts=None):
    """True when at least one of this session's background tasks is live, i.e. something will wake the lead: any running task that is not a shell, or a shell the OS did not flag `suspect` -- the same test the roster applies to a shell lease."""
    for b in running or []:
        if not isinstance(b, dict) or b.get("status", "running") != "running":
            continue
        if b.get("type") != "shell":
            return True
        if (verdicts or {}).get(str(b.get("id") or "")) != "suspect":
            return True
    return False


def first_prompt(jsonl):
    """The text of an agent transcript's first user record, or ""."""
    try:
        with open(jsonl, "rb") as fh:
            head = fh.read(PROMPT_HEAD_BYTES)
    except (OSError, TypeError):
        return ""
    for raw in head.splitlines():
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "user":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                str(b.get("text") or "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        return ""
    return ""


def auto_lease_candidates(items, owned, named, live_ids):
    """[(item_id, task_id)] to lease: an item owned by this session that is open (and not waiting) or leased to a worker no longer live, named by exactly one live task.

    `items` is the fold's item list, `owned(rec)` the ownership predicate, `named` {task_id: text naming items}, `live_ids` the live worker ids. An item named by two tasks is left alone: which one is working it is not a fact the hook has.
    """
    by_id = {r["id"]: r for r in items}
    claims: dict[str, set[str]] = {}
    for tid, text in named.items():
        for ref in item_refs(text):
            rid = resolve(ref, by_id)
            if rid is not None:
                claims.setdefault(rid, set()).add(tid)
    out = []
    for rid, tids in sorted(claims.items()):
        rec = by_id[rid]
        if len(tids) != 1 or not owned(rec):
            continue
        tid = next(iter(tids))
        open_now = rec.get("state") == " " and not waiting_on(rec, by_id)
        orphaned_lease = (
            rec.get("state") == ">"
            and rec.get("worker") not in (tid, LEAD_WORKER)
            and rec.get("worker") not in live_ids
        )
        if open_now or orphaned_lease:
            out.append((rid, tid))
    return out

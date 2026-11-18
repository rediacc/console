"""wl_storestatus: the store's own status, rendered by the hook rather than retyped in the message (agent/plans/PLAN-stop-hook-store-status.md D1, D2).

WHY THIS EXISTS. The judge and the `out-of-sync` check asked the final message to list every open item by id, so a status table copied from data the hook already holds was retyped on nearly every stop. A copy can drift from the store and proves nothing the store does not. This module answers the same question from the store: what moved since the last stop, and which open item has gone quiet with nobody on it.

PURE. No I/O beyond the arguments, no environment reads, no store writes. Thresholds come from wl_liveness (read at call time, so a test that retunes them is honoured), and every message text is a module constant, so the boxes that wire this in (S2, S3) never edit worklist_messages.py for it.

THE SNAPSHOT IS NOT A BYTE OFFSET. The store is one file per writer, folded in `(at, ns)` order, and compact_store rewrites files, so an offset into one file points at the wrong event after any compaction. The snapshot keeps the `(at, ns)` high-water mark plus a per-item digest `[state, upd, worker, lease_at, note8]`. Compaction carries `upd`, `lastnote`, the worker and the state forward, so a compacted store matches the digest. Two fields a compaction legitimately rewrites are read with that in mind: `lease_at` (the re-emitted lease is stamped at `upd`) is never compared, because every real lease also moves `upd`; and `upd` counts as moved only when it moves FORWARD, because a compaction can only carry a stamp or pull it back to the item's first stamp, never advance it.
"""

import datetime
import hashlib
import re

import wl_core as C
import wl_leasehelp as LH
import wl_liveness as L

# The item states a snapshot covers: open, in flight, deferred.
OPEN_STATES = (" ", ">", "?")

# Default caps (plan D3): the table in the operator's systemMessage, the change list in the block reason.
TABLE_CAP = 40
CHANGES_CAP = 15
NOTE_WIDTH = 60

# Freshness classes, in first-match order. `orphaned` is tested before `quiet`, because an orphaned item is quiet by definition and its threshold (LADDER_INVESTIGATE_MIN) sits below quiet's ceiling (LADDER_RESOLVE_MIN).
CLASSES = ("moved", "live", "waiting", "queued", "deferred", "orphaned", "quiet", "stale")
BLOCKING_CLASSES = frozenset({"stale", "orphaned"})
# The block key the blocking classes raise (S3 wires it).
STALE_KEY = "wl-stale"

# Change kinds, in the priority one item's single row is labelled by.
CHANGE_KINDS = ("retired", "ticked", "deferred", "reopened", "new", "leased", "unleased", "note")

# Worker states shown in the table's worker column.
W_LIVE, W_SUSPECT, W_GONE, W_QUEUE, W_LEAD, W_NONE = "live", "suspect", "gone", "queue", "lead", "-"
# Inside a turn (`worklist.py --status`, plan D4) there is no Stop event, so a worker the roster's estimate cannot see (a shell, a teammate) is never called live or gone.
W_UNVERIFIED = "unverified (no stop event)"

TABLE_HEADER = (
    "STORE STATUS (hook-rendered from the worklist store; the message need not repeat it)"
)
TABLE_ROW = "#%s  [%s]  %s  %dm  %-8s %s"
MORE_TAIL = "+%d more: worklist.py --status %s"
CHANGES_HEADER = "CHANGES SINCE LAST STOP:"
CHANGES_NONE = "CHANGES SINCE LAST STOP: none"
CHANGES_ROW = "#%s  %-8s %s"
CHANGES_MORE_TAIL = "+%d more: worklist.py --status %s --since-last-stop"
NO_SNAPSHOT = "CHANGES SINCE LAST STOP: no snapshot yet (first stop of this session id); every item is listed as current"
COUNT_LINE = "STORE STATUS: %d open (%s); full table: worklist.py --status %s"
VERB_EMPTY = "STORE STATUS: no open, in-flight or deferred item is owned by %s"
STALE_WHY = "quiet %dm with no live verified worker and no blocker"
ORPHANED_WHY = "quiet %dm and its worker %s is found by no oracle"
V_STALE = (
    "WL-STALE: %d open item(s) of this session went quiet with nobody on them, and no other check "
    "names them this stop:\n%s\n"
    "Each exit is one the session completes alone: advance the item and record it with "
    "`worklist.py --update %s <id> <note>`, lease it to a live worker, add `BLOCKED_BY:#<id>` "
    "through --update, park it with --defer and a DEFAULT, or --tick it with evidence."
)
STALE_ROW = "    #%s  [%s]  %s  %s"
# The ids a ladder label or a covering line leads with (`#<id> ...`); a harness task (`task #7`) does not match.
_LEAD_ID = re.compile(r"^#([0-9A-Za-z_-]+)")


def _epoch(now):
    """Seconds since the epoch from a number or an aware datetime."""
    if isinstance(now, datetime.datetime):
        return now.timestamp()
    return float(now)


def _stamp_epoch(stamp):
    when = C.parse_stamp(str(stamp or ""))
    return when.timestamp() if when is not None else None


def note8(text):
    """The first 8 hex of the sha1 of an item's latest note; "" for no note."""
    text = str(text or "")
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8] if text else ""


def digest(rec):
    """`[state, upd, worker, lease_at, note8]` for one fold record."""
    return [
        str(rec.get("state") or " "),
        str(rec.get("upd") or ""),
        str(rec.get("worker") or ""),
        str(rec.get("lease_at") or ""),
        note8(rec.get("lastnote")),
    ]


def same(old, new):
    """True when two digests describe no real change. `lease_at` is ignored and `upd` must move forward to count; see the module docstring for why a compaction rewrites both."""
    if not old or not new:
        return False
    return (
        old[0] == new[0]
        and old[2] == new[2]
        and old[4] == new[4]
        and not (str(new[1]) > str(old[1]))
    )


def _items(fold):
    if isinstance(fold, dict):
        return list(fold.values())
    return list(getattr(fold, "items", None) or [])


def _by_id(fold):
    by_id = getattr(fold, "by_id", None)
    if isinstance(by_id, dict):
        return by_id
    return {r["id"]: r for r in _items(fold) if r.get("id")}


def _owned_open(fold, session_id):
    return [
        r
        for r in _items(fold)
        if r.get("id")
        and r.get("state") in OPEN_STATES
        and C.owned_by_me(r.get("owner"), session_id)
    ]


def high_water(events):
    """The newest event's `(at, ns)` key, as a list, or ["", 0] for no events."""
    import wl_store as S

    best = ("", 0)
    for ev in events or ():
        if isinstance(ev, dict):
            key = S.event_order(ev)
            best = max(best, key)
    return [best[0], best[1]]


def snapshot(fold, session_id, now, queued=None):
    """`{"at": [stamp, ns], "stop_at": epoch, "items": {id: digest}}` over every item this session owns in states ` `, `>` and `?`.

    `at` is `fold.high_water` when the caller set it (from `high_water(events)`), else the newest `upd` of any item with ns 0: the fold itself keeps no events.

    `queued` (the Stop hook passes the ids classify_items put in `queued`) is kept as a sorted `"queued"` list, so the `--status` verb, which cannot compute the live PR scope inside a turn, classes those items as the last stop did."""
    hw = getattr(fold, "high_water", None)
    if isinstance(hw, list | tuple) and len(hw) == 2:
        at = [str(hw[0]), int(hw[1] or 0)]
    else:
        newest = max((str(r.get("upd") or "") for r in _items(fold)), default="")
        at = [newest, 0]
    snap = {
        "at": at,
        "stop_at": _epoch(now),
        "items": {r["id"]: digest(r) for r in _owned_open(fold, session_id)},
    }
    if queued is not None:
        snap["queued"] = sorted(queued)
    return snap


def _note(rec):
    return " ".join(str(rec.get("lastnote") or "").split())[:NOTE_WIDTH]


def changes(prev, fold, session_id):
    """Change rows `{"id", "kind", "state", "detail"}` between a snapshot and the fold, one per item, labelled by CHANGE_KINDS priority.

    No snapshot (`prev` falsy) gives []; the renderer says so (NO_SNAPSHOT). An item added and closed between two stops was never open at either, so it gives no row."""
    if not prev or not isinstance(prev.get("items"), dict):
        return []
    old_items = prev["items"]
    since = str((prev.get("at") or [""])[0] or "")
    by_id = _by_id(fold)
    rows = []

    for rid, old in old_items.items():
        rec = by_id.get(rid)
        if (
            rec is None
            or rec.get("state") == "~"
            or not C.owned_by_me(rec.get("owner"), session_id)
        ):
            rows.append({"id": rid, "kind": "retired", "state": "~", "detail": ""})
            continue
        new = digest(rec)
        if same(old, new):
            continue
        state = new[0]
        if state == "x":
            kind, detail = "ticked", _note(rec)
        elif state == "?" and old[0] != "?":
            kind, detail = "deferred", _note(rec)
        elif old[0] == "?" and state != "?":
            kind, detail = "reopened", _note(rec)
        elif new[2] and new[2] != old[2]:
            kind, detail = "leased", "worker:%s" % new[2]
        elif old[2] and not new[2]:
            kind, detail = "unleased", "worker:%s released" % old[2]
        else:
            kind, detail = "note", _note(rec) or "updated"
        rows.append({"id": rid, "kind": kind, "state": state, "detail": detail})

    for rec in _owned_open(fold, session_id):
        rid = rec["id"]
        if rid in old_items:
            continue
        # STRICT: stamps are second-resolution, so an item first stamped in the snapshot's own second may have been added after it; it reads `new`, never `reopened` (review e8329fa3.1).
        existed = since and str(rec.get("first") or "") < since
        kind = "reopened" if existed else "new"
        rows.append(
            {
                "id": rid,
                "kind": kind,
                "state": rec.get("state"),
                "detail": _note(rec)
                or str(rec.get("basetext") or rec.get("text") or "")[:NOTE_WIDTH],
            }
        )

    rank = {k: i for i, k in enumerate(CHANGE_KINDS)}
    rows.sort(key=lambda r: (rank.get(r["kind"], len(rank)), r["id"]))
    return rows


def worker_state(rec, live, verdicts, roster_live, unverified=()):
    """One of W_LIVE, W_SUSPECT, W_GONE, W_QUEUE, W_LEAD, W_NONE for an item's worker. Live means listed live AND verified: a shell `confirmed` by verify_background, or an agent the roster calls LIVE (`roster_live`, which also carries a teammate with a fresh transcript)."""
    worker = str(rec.get("worker") or "")
    if rec.get("state") != ">" or not worker:
        return W_NONE
    if worker == LH.LEAD_WORKER:
        return W_LEAD
    if worker == LH.QUEUE_WORKER:
        return W_QUEUE
    if worker in (roster_live or ()) or (
        worker in (live or ()) and (verdicts or {}).get(worker) == "confirmed"
    ):
        return W_LIVE
    if worker in (live or ()):
        return W_SUSPECT
    if worker in (unverified or ()):
        return W_UNVERIFIED
    return W_GONE


def _covered_key(covered, rid):
    if isinstance(covered, dict):
        return str(covered.get(rid) or "")
    return "covered" if rid in (covered or ()) else ""


def freshness(
    fold,
    session_id,
    prev,
    live,
    verdicts,
    roster_live,
    queued_ids,
    covered,
    now,
    graph=None,
    unverified=(),
):
    """One row per owned open, in-flight or deferred item: `{"id", "state", "worker", "wstate", "age", "cls", "why", "note", "covered", "blocks"}`.

    Arguments: `live` the live worker ids (wl_liveness.live_worker_ids); `verdicts` {worker: verdict} from verify_background, where a value of "waiting" marks an agent waiting on a shell it armed; `roster_live` the agent ids the roster verifies LIVE; `queued_ids` the ids classify_items put in `queued`; `covered` the ids another check names this stop, as {id: key} or a set; `graph` the optional plan graph `waiting_on` reads; `unverified` the workers no oracle can judge without a Stop event (the `--status` verb's shells), shown as W_UNVERIFIED and never orphaned.

    First match wins in CLASSES order. With no snapshot every item is judged by age alone, so the first stop of a fresh session id can still name a stale item. A blocking row (`stale`, `orphaned`) that `covered` names keeps its class, carries the covering key, and has `blocks` False: no double block."""
    t_now = _epoch(now)
    old_items = (prev or {}).get("items") if isinstance((prev or {}).get("items"), dict) else None
    by_id = _by_id(fold)
    resolve_min = L.LADDER_RESOLVE_MIN
    investigate_min = L.LADDER_INVESTIGATE_MIN
    rows = []
    for rec in _owned_open(fold, session_id):
        rid = rec["id"]
        state = rec.get("state")
        worker = str(rec.get("worker") or "") if state == ">" else ""
        wstate = worker_state(rec, live, verdicts, roster_live, unverified)
        upd = _stamp_epoch(rec.get("upd"))
        age = max(0, int((t_now - upd) // 60)) if upd is not None else 0
        quiet = old_items is None or same(old_items.get(rid), digest(rec))
        why = ""
        if not quiet:
            cls = "moved"
        elif wstate == W_LIVE:
            cls = "live"
        elif (
            LH.waiting_on(rec, by_id, graph)
            or wstate == W_QUEUE
            or (worker and (verdicts or {}).get(worker) == "waiting")
        ):
            cls = "waiting"
        elif rid in (queued_ids or ()):
            cls = "queued"
        elif state == "?":
            cls = "deferred"
        elif wstate == W_GONE and age >= investigate_min:
            cls, why = "orphaned", ORPHANED_WHY % (age, worker)
        elif age < resolve_min:
            cls = "quiet"
        else:
            cls, why = "stale", STALE_WHY % age
        cover = _covered_key(covered, rid)
        rows.append(
            {
                "id": rid,
                "state": state,
                "worker": worker,
                "wstate": wstate,
                "age": age,
                "cls": cls,
                "why": why,
                "note": _note(rec),
                "covered": cover,
                "blocks": cls in BLOCKING_CLASSES and not cover,
            }
        )
    rank = {k: i for i, k in enumerate(CLASSES)}
    rows.sort(key=lambda r: (-int(r["blocks"]), rank.get(r["cls"], len(rank)), r["id"]))
    return rows


def blocking(rows):
    """The ids `wl-stale` blocks on: stale or orphaned rows no other check covers."""
    return [r["id"] for r in rows if r.get("blocks")]


def count_line(rows, me="<me>"):
    """`STORE STATUS: n open (a moved, b live, ...)` with the --status pointer; one line for the block reason."""
    counts = dict.fromkeys(CLASSES, 0)
    for r in rows:
        counts[r["cls"]] = counts.get(r["cls"], 0) + 1
    parts = ", ".join(
        "%d %s" % (counts[k], k)
        for k in CLASSES
        if counts[k] or k in ("moved", "live", "waiting", "queued", "quiet", "stale")
    )
    return COUNT_LINE % (len(rows), parts, me)


def _wcol(row):
    if row["wstate"] == W_NONE:
        return W_NONE
    if row["wstate"] == W_LIVE:
        return "%s (live, verified)" % row["worker"]
    return "%s (%s)" % (row["worker"], row["wstate"])


def render_table(rows, cap=TABLE_CAP, me="<me>"):
    """The table: a header and one row per item, cut at `cap` with a `+N more` tail. No rows renders "" (an allow with nothing owned stays silent)."""
    if not rows:
        return ""
    lines = [TABLE_HEADER]
    for r in rows[:cap]:
        cls = r["cls"] + ("[%s]" % r["covered"] if r.get("covered") else "")
        lines.append(TABLE_ROW % (r["id"], r["state"], _wcol(r), r["age"], cls, r["note"]))
    if len(rows) > cap:
        lines.append(MORE_TAIL % (len(rows) - cap, me))
    return "\n".join(lines)


def render_changes(rows, cap=CHANGES_CAP, me="<me>", first=False):
    """The change summary, cut at `cap` with a `+N more` tail. `first` (no snapshot) renders NO_SNAPSHOT; no rows renders CHANGES_NONE."""
    if first:
        return NO_SNAPSHOT
    if not rows:
        return CHANGES_NONE
    lines = [CHANGES_HEADER]
    lines.extend(CHANGES_ROW % (r["id"], r["kind"], r.get("detail") or "") for r in rows[:cap])
    if len(rows) > cap:
        lines.append(CHANGES_MORE_TAIL % (len(rows) - cap, me))
    return "\n".join(lines)


def open_item_ids(fold, session_id, in_flight_ids, queued_ids):
    """The ids the `open-items` check names this stop: owned `[ ]` items that wait on nothing and sit in the PR scope, plus owned `[>]` items classify_items failed closed (not in flight). Read after classify_items, which stamps `waiting_on` and `waiting_plans` on each record."""
    out = set()
    for r in _owned_open(fold, session_id):
        if r.get("state") == " ":
            if r.get("waiting_on") or r.get("waiting_plans") or r["id"] in (queued_ids or ()):
                continue
            out.add(r["id"])
        elif r.get("state") == ">" and r["id"] not in (in_flight_ids or ()):
            out.add(r["id"])
    return out


def covering(fold, session_id, open_ids=(), ladder=None, roster=None):
    """{item id: key} for every owned item another check names this stop (plan D2, no double block).

    `open_ids` the ids `open-items` names (open_item_ids, empty when that check does not fire); `ladder` {key: [label, ...]} for the ladder's lists, each label leading with `#<id>`; `roster` the wl_roster verdict, whose `leased_dead` rows are `(item, worker, coverer)` and whose `silent` and `status_due` lists are worker ids."""
    cover = {}
    for rid in sorted(open_ids or ()):
        cover.setdefault(rid, "open-items")
    for key, labels in sorted((ladder or {}).items()):
        for label in labels or ():
            m = _LEAD_ID.match(str(label))
            if m:
                cover.setdefault(m.group(1), key)
    if roster:
        for row in roster.get("leased_dead") or ():
            cover.setdefault(str(row[0]), "roster-dead")
        quiet = set(roster.get("silent") or ()) | set(roster.get("status_due") or ())
        if quiet:
            for r in _owned_open(fold, session_id):
                if r.get("state") == ">" and str(r.get("worker") or "") in quiet:
                    cover.setdefault(r["id"], "roster-silent")
    return cover


def render_stale(rows, me="<me>"):
    """The `wl-stale` block text over the blocking rows, or "" when none blocks."""
    hit = [r for r in rows if r.get("blocks")]
    if not hit:
        return ""
    body = "\n".join(
        STALE_ROW % (r["id"], r["state"], _wcol(r), "%s: %s" % (r["cls"], r["why"])) for r in hit
    )
    return V_STALE % (len(hit), body, me)


def stop_texts(rows, change_rows, first, me="<me>"):
    """(system, reason) for one stop (plan D3): the table and the change summary for the operator's systemMessage, the count line and the change summary for a block reason. Both "" when the session owns no open, in-flight or deferred item and nothing changed."""
    if not rows and not change_rows:
        return "", ""
    summary = render_changes(change_rows, CHANGES_CAP, me, first=first)
    system = "\n\n".join(t for t in (render_table(rows, TABLE_CAP, me), summary) if t)
    return system, count_line(rows, me) + "\n" + summary


def render_verb(rows, change_rows, first, me="<me>", since_last_stop=False):
    """The `worklist.py --status <me> [--since-last-stop]` output (plan D4), uncapped: the verb is where a capped table points. `--since-last-stop` prints only the change rows, and with no snapshot it says so and lists every item."""
    whole = len(rows) + len(change_rows) + 1
    summary = render_changes(change_rows, whole, me, first=first)
    if since_last_stop and not first:
        return summary
    table = render_table(rows, whole, me) or VERB_EMPTY % me
    return table + "\n\n" + summary

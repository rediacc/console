"""wl_retro: the stop-hook retro before compaction, from the ledger row to the saved plan.

agent/plans/PLAN-stop-hook-retro-20260924.md section 8 (boxes R20260924.11 to R.13, standing procedure P3.1 of PLAN-stop-hook-continuity.md). Two places ORDER a retro and write an `ordered` row to agent/ledgers/stop-hook-retros.jsonl: the band notice, after STATE.md is rewritten past an early or late crossing, and `wl_checks.handle_post_compact`. This module carries the order from there to a saved plan:

  sync      every stop: an `ordered` row with no `tracked` row gets an owned item, which the
            ordinary open-items check then enforces; a tracked item leased to a worker gets a
            `dispatched` row; a ticked one gets a `saved` row with the plan's task counts.
  brief     `worklist.py --retro-brief <me> <band>`: the Plan agent's prompt, carrying `#<item>`
            so the P2.2 auto-lease links the item to that agent.

THE LEDGER HELPERS ARE NOT COPIED HERE. They live in `.claude/hooks/context/ctx_budget.py`, which the band notice already imports, and this module loads that file by path on first use. Loading it lazily keeps this module importable from a stop directory copied without its `context/` sibling (the LKG snapshot, the post-edit check's copies), where every caller already treats a missing ledger as nothing to do.

THE DEDUPE KEY IS `(session, band)`, the plan's Decision: a session gets at most three retros, one per band in `ctx_budget.RETRO_BANDS`, and each covers the transcript bytes since the previous one.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
import re

import worklist_messages as M

_CTX_PATH = pathlib.Path(__file__).resolve().parents[1] / "context" / "ctx_budget.py"
_CTX: dict = {}

# The retro plan a tick names; its path is the tick evidence and the `saved` row's subject.
PLAN_RE = re.compile(r"agent/plans/PLAN-stop-hook-retro-\d{8}\.md")
# Every checkbox a plan's task list can carry, and the open one.
BOX_RE = re.compile(r"^\s*- \[([ xX?>~])\] ", re.MULTILINE)
# A box id in a PLAN-stop-hook-* file: `- [ ] **R20260924.11** text` or `- [x] **P2.6** text`.
BOX_ID_RE = re.compile(r"^\s*- \[([ xX?>~])\] \*\*([A-Za-z0-9._-]+)\*\*\s*(.*)$")
# Bounds on the brief, so a long session cannot turn a prompt into a transcript.
ROWS_PER_SECTION = 40
TEXT_CAP = 200


def ctx():
    """ctx_budget, loaded once by path. Raises when the context directory is absent; callers treat that as no ledger."""
    if "mod" not in _CTX:
        spec = importlib.util.spec_from_file_location("_wl_retro_ctx_budget", _CTX_PATH)
        if spec is None or spec.loader is None:
            raise ImportError("no ctx_budget beside %s" % _CTX_PATH.parent)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CTX["mod"] = mod
    return _CTX["mod"]


def today():
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")


def _row_for(rows, ev, me8, band):
    for row in rows:
        if row.get("ev") == ev and row.get("session") == me8 and row.get("band") == band:
            return row
    return None


def _has(rows, ev, item):
    return any(r.get("ev") == ev and r.get("item") == item for r in rows)


def _date_of(ordered):
    """The ordered row's own date, so the item, the brief and the plan path agree even when the brief is printed a day later."""
    at = str(ordered.get("at") or "")
    return at[:10].replace("-", "") if len(at) >= 10 else today()


def ensure_tracked(worklist, root, me8, band, store):
    """The tracking item's id for (me8, band), adding it and its `tracked` row on first call. None when no retro was ordered for that pair."""
    cb = ctx()
    rows = cb.retro_live(cb.retro_rows(root))
    ordered = cb.retro_ordered(rows, me8, band)
    if ordered is None:
        return None
    tracked = _row_for(rows, "tracked", me8, band)
    if tracked is not None:
        return tracked.get("item")
    date = _date_of(ordered)
    rid = store.add_item(worklist, me8, M.RETRO_ITEM % {"me8": me8, "band": band, "date": date})
    cb.retro_append(
        root, {"ev": "tracked", "at": cb.utc_stamp(), "session": me8, "band": band, "item": rid}
    )
    return rid


def plan_counts(root, plan_rel):
    """(open, total) task boxes in the saved retro plan, or (0, 0) when it is unreadable."""
    try:
        text = (pathlib.Path(root) / plan_rel).read_text(encoding="utf-8")
    except OSError:
        return 0, 0
    marks = BOX_RE.findall(text)
    return sum(1 for m in marks if m == " "), len(marks)


def sync(worklist, root, session_id, store):
    """Carry this session's retro rows one step forward. Runs on every stop; a session with no `ordered` row reads one small file and does nothing else."""
    cb = ctx()
    if not cb.retro_ledger_path(root).is_file():
        return
    me8 = cb.session_slug(session_id)
    # Live rows only: a `voided` pair gets no tracking item, and its old tracked row is not carried forward (R20260924.17).
    rows = cb.retro_live(cb.retro_rows(root))
    for row in rows:
        if row.get("ev") == "ordered" and row.get("session") == me8:
            ensure_tracked(worklist, root, me8, row.get("band"), store)
    rows = cb.retro_live(cb.retro_rows(root))
    fold = None
    for row in rows:
        if row.get("ev") != "tracked" or row.get("session") != me8:
            continue
        item = row.get("item")
        if _has(rows, "saved", item):
            continue
        if fold is None:
            fold = store.load(worklist, sync=False)
        rec = fold.by_id.get(item)
        if rec is None:
            continue
        base = {"at": cb.utc_stamp(), "session": me8, "band": row.get("band"), "item": item}
        if rec.get("state") == ">" and rec.get("worker") and not _has(rows, "dispatched", item):
            cb.retro_append(root, dict(base, ev="dispatched", agent=rec["worker"]))
        if rec.get("state") == "x":
            found = PLAN_RE.search(
                str(rec.get("lastnote") or "") + " " + str(rec.get("text") or "")
            )
            plan = found.group(0) if found else ""
            n_open, n_total = plan_counts(root, plan) if plan else (0, 0)
            cb.retro_append(
                root, dict(base, ev="saved", plan=plan, tasks_open=n_open, tasks_total=n_total)
            )


def _stamp_of(row):
    """A row's time as an ISO8601Z stamp, whichever of the logs' two spellings it uses."""
    at = row.get("at") or row.get("ts")
    if isinstance(at, (int, float)):
        return ctx().utc_stamp(at)
    return str(at or "")


def _jsonl_since(path, since):
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and _stamp_of(row) > since:
            out.append(row)
    return out


def _lines(rows, render):
    if not rows:
        return "  (none)"
    shown = rows[-ROWS_PER_SECTION:]
    head = (
        []
        if len(shown) == len(rows)
        else ["  (%d older rows not shown)" % (len(rows) - len(shown))]
    )
    return "\n".join(head + ["  " + render(r)[: TEXT_CAP + 80] for r in shown])


def _block_counts(rows):
    if not rows:
        return "  (none)"
    lead: dict = {}
    named: dict = {}
    judge = {"sweep": 0, "proof": 0, "continue": 0}
    for row in rows:
        lead[row.get("key")] = lead.get(row.get("key"), 0) + 1
        for key in row.get("named") or []:
            named[key] = named.get(key, 0) + 1
        flags = row.get("judge") or {}
        judge["sweep"] += bool(flags.get("sweep"))
        judge["proof"] += bool(flags.get("proof"))
        judge["continue"] += flags.get("verdict") == "continue"
    out = ["  %d blocked stops" % len(rows)]
    out += [
        "  led by %s: %d (also named on %d)" % (k, n, named.get(k, 0))
        for k, n in sorted(lead.items(), key=lambda kv: -kv[1])
    ]
    out += [
        "  named only, %s: %d" % (k, n)
        for k, n in sorted(named.items(), key=lambda kv: -kv[1])
        if k not in lead
    ]
    out.append(
        "  judge flags: %(continue)d continue, %(sweep)d sweep demands, %(proof)d proof demands"
        % judge
    )
    return "\n".join(out)


def box_census(root):
    """Every box of every agent/plans/PLAN-stop-hook-*.md, one line each: the do-not-re-propose list."""
    out = []
    for plan in sorted((pathlib.Path(root) / "agent" / "plans").glob("PLAN-stop-hook-*.md")):
        try:
            text = plan.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = BOX_ID_RE.match(line)
            if m:
                out.append(
                    "  %s [%s] %s: %s" % (plan.name, m.group(1), m.group(2), m.group(3)[:100])
                )
    return "\n".join(out) or "  (none)"


def brief(worklist, root, me8, band, item):
    """The Plan agent's prompt for (me8, band): the transcript range, the logs since the previous REVIEWED retro, and the boxes it must not re-propose.

    The window starts after the newest earlier retro that reached `saved` (else `dispatched`), not after the newest `ordered` row: an order nobody reviewed covered nothing (R20260924.17). `from_off` is recomputed here for the same reason rather than read from the row, which recorded the start as it looked when the order was written.
    """
    cb = ctx()
    rows = cb.retro_live(cb.retro_rows(root))
    ordered = cb.retro_ordered(rows, me8, band) or {}
    start = cb.retro_window_start(rows, me8, before=ordered or None)
    since = str(start.get("at") or "") if start else ""
    to_off = int(ordered.get("to_off") or 0)
    from_off = min(int(start.get("to_off") or 0), to_off) if start else 0
    date = _date_of(ordered)
    wl = pathlib.Path(worklist)
    blocklog = wl.with_suffix(".blocklog-%s.jsonl" % me8)
    judgelog = wl.with_suffix(".judge-%s.jsonl" % me8)
    admitlog = pathlib.Path(str(wl) + ".admissions-%s.jsonl" % me8)
    ticklog = wl.with_suffix(".tick-refusals-%s.jsonl" % me8)
    hintlog = pathlib.Path(root) / "agent" / "ledgers" / "hint-proposals.jsonl"
    return M.RETRO_BRIEF % {
        "me8": me8,
        "band": band,
        "date": date,
        "item": item,
        "plan": "agent/plans/PLAN-stop-hook-retro-%s.md" % date,
        "transcript": ordered.get("transcript") or "(not recorded)",
        "from_off": from_off,
        "to_off": to_off,
        "blocklog": blocklog,
        "blocks": _block_counts(_jsonl_since(blocklog, since)),
        "hints": _lines(
            [r for r in _jsonl_since(hintlog, since) if str(r.get("by") or "")[:8] == me8],
            lambda r: "%s %s" % (_stamp_of(r), r.get("text")),
        ),
        "judgelog": judgelog,
        "judge": _lines(
            _jsonl_since(judgelog, since),
            lambda r: (
                "%s %s: %s" % (_stamp_of(r), r.get("verdict"), r.get("reason") or r.get("error"))
            ),
        ),
        "admitlog": admitlog,
        "admit": _lines(
            _jsonl_since(admitlog, since),
            lambda r: (
                "%s %s %s" % (_stamp_of(r), r.get("families"), " | ".join(r.get("spans") or []))
            ),
        ),
        "ticklog": ticklog,
        "ticks": _lines(
            _jsonl_since(ticklog, since),
            lambda r: (
                "%s #%s %s: %s" % (_stamp_of(r), r.get("id"), r.get("why"), r.get("evidence"))
            ),
        ),
        "boxes": box_census(root),
    }
